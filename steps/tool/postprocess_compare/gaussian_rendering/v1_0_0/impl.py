from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _creality_scan_dir() -> Path:
    """返回 CrealityScan 本地数据根目录（%LOCALAPPDATA%\Creality\CrealityScan）。"""
    local_appdata = os.environ.get("LOCALAPPDATA")
    base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
    return base / "Creality" / "CrealityScan"


def _download_package_version_file() -> Path:
    # 高斯渲染与AI重贴图共用 AITextureRestore 下载包
    return _creality_scan_dir() / "Extensions" / "AITextureRestore" / "version.txt"


def _download_package_ready() -> bool:
    """高斯渲染下载包是否已就绪（version.txt 存在即视为已下载完成）。"""
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
    """处理测试版缺少高斯渲染下载包时的下载弹窗，并等待下载完成。

    流程：等待下载弹窗出现 -> 点击“下载”按钮 -> 等待 AITextureRestore/version.txt 出现。
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

    print(f"[高斯渲染] 缺少下载包，等待下载弹窗出现（{popup_timeout_sec:.0f} 秒）...")
    deadline = time.time() + popup_timeout_sec
    while time.time() < deadline:
        if exists(download_button):
            break
        sleep(0.5)
    else:
        raise RuntimeError(f"等待高斯渲染下载弹窗出现超时（{popup_timeout_sec:.0f} 秒）")

    print("[高斯渲染] 已找到下载弹窗，点击“下载”按钮。")
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
            print(f"[高斯渲染] 下载包下载完成：AITextureRestore {version}")
            return
        now = time.time()
        if now - last_log_time >= 15.0:
            progress = _latest_download_progress(app_log)
            print(f"[高斯渲染] 下载进度：{progress if progress else '等待进度输出...'}")
            last_log_time = now
        sleep(2.0)
    raise RuntimeError(f"等待高斯渲染下载包下载完成超时（{download_timeout_sec:.0f} 秒）")


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, exists, sleep, snapshot, touch, wait  # type: ignore
    except ImportError as exc:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from exc

    base = Path(__file__).resolve().parent / "templates"
    timeout_sec = max(1.0, float(params.get("timeout_sec", 900) or 900))
    operation_started = time.time()

    # 来自现有 Airtest 用例：进行高斯渲染操作.air/进行高斯渲染操作.py
    touch(Template(str(base / "tpl1774270225446.png"), record_pos=(-0.277, -0.254), resolution=(1920, 1080)))
    touch(Template(str(base / "tpl1786174242991.png"), record_pos=(-0.118, -0.224), resolution=(1920, 1080)))
    touch(Template(str(base / "tpl1786174282206.png"), record_pos=(-0.358, -0.133), resolution=(1920, 1080)))

    # 测试版 + 本地无高斯渲染下载包时，点击“应用”后 CrealityScan 会弹窗要求下载；自动点击下载并等待完成
    if str(ctx.get("version_label") or "") == "测试版" and not _download_package_ready():
        _handle_download_package(base, params, Template, exists, touch, sleep)

    progress = Template(str(base / "tpl1786174502310.png"), record_pos=(-0.001, 0.12), resolution=(1920, 1080))
    progress_started = time.time()
    try:
        wait(progress, timeout=timeout_sec)
    except Exception as exc:
        raise RuntimeError(f"等待高斯渲染进度条出现超时（{timeout_sec:.0f} 秒）") from exc

    while time.time() - progress_started < timeout_sec:
        if not exists(progress):
            break
        sleep(0.5)
    else:
        raise RuntimeError(f"等待高斯渲染进度条消失超时（{timeout_sec:.0f} 秒）")

    operation_elapsed_sec = round(time.time() - operation_started, 3)
    run_dir = Path(str(ctx.get("run_dir") or "."))
    shot = run_dir / "screenshots" / f"step{int(ctx.get('step_index') or 0):03d}_gaussian_rendering.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    snapshot(filename=str(shot))
    return {
        "snapshot": str(shot),
        "operation_elapsed_sec": operation_elapsed_sec,
        "operation_elapsed_label": "高斯渲染耗时",
    }
