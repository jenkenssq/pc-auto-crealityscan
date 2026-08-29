from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _select_head_front_images(process_id: int, img_dir: Path, params: Dict[str, Any], sleep) -> None:
    try:
        from pywinauto import Desktop  # type: ignore
        from pywinauto.findwindows import ElementNotFoundError  # type: ignore
        from pywinauto.timings import TimeoutError as PywinautoTimeoutError  # type: ignore
    except ImportError as exc:
        raise RuntimeError("未安装 pywinauto，无法在图片选择弹窗中选择图片。") from exc

    dialog_timeout_sec = max(1.0, float(params.get("dialog_timeout_sec", 15) or 15))
    click_delay_sec = max(0.0, float(params.get("click_delay_sec", 0.5) or 0.5))

    # 与 AI重贴图一致：#32770 + 标题定位弹窗（同进程可能有多个 #32770，用标题消歧）
    try:
        dialog = Desktop(backend="win32").window(
            process=process_id, class_name="#32770", title_re="Select Head Front Image"
        )
        dialog.wait("exists visible enabled ready", timeout=dialog_timeout_sec)
    except (ElementNotFoundError, PywinautoTimeoutError, RuntimeError):
        dialog = Desktop(backend="win32").window(title_re="Select Head Front Image")
        dialog.wait("exists visible enabled ready", timeout=dialog_timeout_sec)

    file_name_edit = dialog.child_window(control_id=1148, class_name="Edit")
    file_name_edit.wait("exists visible enabled ready", timeout=dialog_timeout_sec)
    file_name_edit.set_edit_text(str(img_dir))
    sleep(click_delay_sec)

    open_button = dialog.child_window(control_id=1, class_name="Button")
    open_button.wait("exists visible enabled ready", timeout=dialog_timeout_sec)
    open_button.click_input()
    sleep(click_delay_sec)

    # 文件名框填入目录路径并点“打开”会导航进入该目录；点击文件列表获取键盘焦点后 Ctrl+A 全选，再点“打开”确认导入
    shell_view = dialog.child_window(class_name="SHELLDLL_DefView")
    shell_view.wait("exists visible enabled ready", timeout=dialog_timeout_sec)
    for attempt in range(3):
        try:
            shell_view.click_input()
            sleep(click_delay_sec)
            shell_view.type_keys("^a")
            sleep(click_delay_sec)
            open_button.wait("exists visible enabled ready", timeout=dialog_timeout_sec)
            open_button.click_input()
            dialog.wait_not("visible", timeout=3.0)
            return
        except (ElementNotFoundError, PywinautoTimeoutError, RuntimeError) as exc:
            if attempt >= 2:
                raise RuntimeError(f"在图片选择弹窗中全选并确认失败：{exc}") from exc
            sleep(1.0)


def _reset_mouse_hover(params: Dict[str, Any], sleep) -> None:
    import ctypes

    safe_x = int(params.get("mouse_safe_x", 10) or 10)
    safe_y = int(params.get("mouse_safe_y", 10) or 10)
    sleep_sec = max(0.0, float(params.get("mouse_safe_sleep_sec", 0.3) or 0.3))
    ctypes.windll.user32.SetCursorPos(safe_x, safe_y)
    sleep(sleep_sec)


def _wait_progress_disappear(template: Any, label: str, params: Dict[str, Any], exists, sleep) -> None:
    timeout_sec = max(1.0, float(params.get("timeout_sec", 600) or 600))
    started = time.time()
    deadline = started + timeout_sec
    last_beat = started
    while time.time() < deadline:
        if exists(template):
            break
        now = time.time()
        if now - last_beat >= 30.0:
            print(
                f"[人体补全] 等待{label}进度条出现中... "
                f"已等待{now - started:.0f}s / 上限{timeout_sec:.0f}s"
            )
            last_beat = now
        sleep(0.5)
    else:
        raise RuntimeError(f"等待{label}进度条出现超时（{timeout_sec:.0f} 秒）")

    last_beat = started
    while time.time() < deadline:
        if not exists(template):
            return
        now = time.time()
        if now - last_beat >= 30.0:
            print(
                f"[人体补全] {label}进度条仍在显示，继续等待消失... "
                f"已等待{now - started:.0f}s / 上限{timeout_sec:.0f}s"
            )
            last_beat = now
        sleep(0.5)
    raise RuntimeError(f"等待{label}进度条消失超时（{timeout_sec:.0f} 秒）")


def _creality_scan_dir() -> Path:
    """返回 CrealityScan 本地数据根目录（%LOCALAPPDATA%\\Creality\\CrealityScan）。"""
    local_appdata = os.environ.get("LOCALAPPDATA")
    base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
    return base / "Creality" / "CrealityScan"


def _download_package_version_file() -> Path:
    return _creality_scan_dir() / "Extensions" / "AIBodyComplete" / "version.txt"


def _download_package_ready() -> bool:
    """人体补全下载包是否已就绪（version.txt 存在即视为已下载完成）。"""
    return _download_package_version_file().is_file()


def _latest_app_log() -> Optional[Path]:
    """返回当前最新写入的 CrealityScan app.log（按修改时间取最新的一个）。"""
    logs_dir = _creality_scan_dir() / "Logs"
    try:
        candidates = sorted(
            (p for p in logs_dir.glob("*/app.log") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    return candidates[0] if candidates else None


def _latest_download_progress(app_log: Optional[Path]) -> Optional[str]:
    """从 app.log 中解析最近一次下载进度（兼容 CrealityScan 日志里状态名不一致的情况）。"""
    if app_log is None or not app_log.is_file():
        return None
    try:
        with app_log.open("r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError:
        return None
    matches = re.findall(r"Download progress:\s*([\d.]+)%", content)
    if not matches:
        return None
    return f"{matches[-1]}%"


def _handle_download_package(base: Path, params: Dict[str, Any], Template, exists, touch, sleep) -> None:
    """处理测试版缺少人体补全下载包时的下载弹窗，并等待下载完成。

    流程：等待下载弹窗出现 -> 点击“下载”按钮 -> 等待 AIBodyComplete/version.txt 出现。
    下载进度从 app.log 读取用于日志展示。
    """
    download_button = Template(
        str(base / "tpl1787980361255.png"),
        record_pos=(0.035, 0.02),
        resolution=(1920, 1080),
    )
    popup_timeout_sec = max(1.0, float(params.get("download_popup_timeout_sec", 15) or 15))
    download_timeout_sec = max(30.0, float(params.get("download_timeout_sec", 1800) or 1800))
    app_log = _latest_app_log()

    print(f"[人体补全] 缺少下载包，等待下载弹窗出现（{popup_timeout_sec:.0f} 秒）...")
    deadline = time.time() + popup_timeout_sec
    while time.time() < deadline:
        if exists(download_button):
            break
        sleep(0.5)
    else:
        raise RuntimeError(f"等待人体补全下载弹窗出现超时（{popup_timeout_sec:.0f} 秒）")

    print("[人体补全] 已找到下载弹窗，点击“下载”按钮。")
    touch(download_button)
    sleep(1.0)

    version_file = _download_package_version_file()
    deadline = time.time() + download_timeout_sec
    last_log_time = 0.0
    while time.time() < deadline:
        if version_file.is_file():
            try:
                version = version_file.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                version = "未知版本"
            print(f"[人体补全] 下载包下载完成：AIBodyComplete {version}")
            return
        now = time.time()
        if now - last_log_time >= 15.0:
            progress = _latest_download_progress(app_log)
            print(f"[人体补全] 下载进度：{progress if progress else '等待进度输出...'}")
            last_log_time = now
        sleep(2.0)
    raise RuntimeError(f"等待人体补全下载包下载完成超时（{download_timeout_sec:.0f} 秒）")


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, exists, snapshot, touch, sleep  # type: ignore
    except ImportError as exc:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from exc

    base = Path(__file__).resolve().parent / "templates"
    click_delay_sec = max(0.0, float(params.get("click_delay_sec", 0.5) or 0.5))

    # 来自现有 Airtest 用例（进行人体补全操作.air/进行人体补全操作.py）
    operation_started = time.time()
    touch(Template(str(base / "tpl1774270225446.png"), record_pos=(-0.277, -0.254), resolution=(1920, 1080)))
    touch(Template(str(base / "tpl1787753200875.png"), record_pos=(0.024, -0.224), resolution=(1920, 1080)))

    # 测试版 + 本地无人体补全下载包时，CrealityScan 会弹窗要求下载；自动点击下载并等待完成
    if str(ctx.get("version_label") or "") == "测试版" and not _download_package_ready():
        _handle_download_package(base, params, Template, exists, touch, sleep)

    touch(Template(str(base / "tpl1787753248187.png"), record_pos=(-0.409, -0.096), resolution=(1920, 1080)))

    process_id = int(ctx.get("process_id") or 0)
    if process_id <= 0:
        raise RuntimeError("人体补全 Step 缺少 CrealityScan 进程 ID")
    project_dir = Path(str(ctx.get("run_dir") or ".")).parent
    img_dir_name = str(params.get("img_dir_name", "img") or "img")
    img_dir = project_dir / img_dir_name
    if not img_dir.is_dir():
        raise RuntimeError(f"未找到人体补全导入图片目录：{img_dir}")
    _select_head_front_images(process_id, img_dir, params, sleep)

    if bool(params.get("enable_hd_geometry", False)):
        touch((320, 465))
        sleep(click_delay_sec)
    touch(Template(str(base / "tpl1787754024750.png")))
    touch(Template(str(base / "tpl1787754262949.png")))

    progress = Template(str(base / "tpl1787754339537.png"))
    _wait_progress_disappear(progress, "创建人体模型", params, exists, sleep)

    touch((140, 720))  # 选择模型底座
    base_wait_sec = max(0.0, float(params.get("base_wait_sec", 20) or 20))
    sleep(base_wait_sec)

    touch(Template(str(base / "tpl1787755269508.png")))  # 预览
    preview_progress = Template(str(base / "tpl1787755313908.png"))
    _wait_progress_disappear(preview_progress, "AI人体补全", params, exists, sleep)

    touch(Template(str(base / "tpl1787755544549.png")))  # 应用
    sleep(click_delay_sec)

    run_dir = Path(str(ctx.get("run_dir") or "."))
    shot = run_dir / "screenshots" / f"step{int(ctx.get('step_index') or 0):03d}_human_body_completion.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    _reset_mouse_hover(params, sleep)
    snapshot(filename=str(shot))

    operation_elapsed_sec = round(time.time() - operation_started, 3)
    return {
        "snapshot": str(shot),
        "operation_elapsed_sec": operation_elapsed_sec,
        "operation_elapsed_label": "人体补全耗时",
    }
