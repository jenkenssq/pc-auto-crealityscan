from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


PROJECT_IMPORT_SUCCESS_KEY = b"OB_SCAN_MESSAGE_ID_PROJECT_IMPORT_SUCCESS"


def _path_mtime(path: Path) -> float:
    try:
        return float(path.stat().st_mtime)
    except OSError:
        return 0.0


def _path_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _latest_scan_log(log_root: Path) -> Optional[Path]:
    if log_root.is_file():
        return log_root
    try:
        files = [path for path in log_root.rglob("scan_log_*.txt") if path.is_file()]
    except OSError:
        return None
    return max(files, key=lambda path: (_path_mtime(path), path.name)) if files else None


def _read_new_bytes(path: Path, position: int) -> Tuple[bytes, int]:
    with path.open("rb") as handle:
        size = _path_size(path)
        if position < 0 or position > size:
            position = 0
        handle.seek(position)
        data = handle.read()
        return data, handle.tell()


def _wait_project_import_success(
    log_root: Path,
    baseline_log: Optional[Path],
    baseline_position: int,
    timeout_sec: float,
    poll_interval_sec: float,
) -> Tuple[Path, float]:
    deadline = time.time() + timeout_sec
    current_log = baseline_log
    position = baseline_position
    buffer = b""
    started = time.time()
    print(
        f"[JENS][import_project] wait_success log_root={log_root} "
        f"baseline_log={baseline_log} baseline_position={baseline_position} "
        f"timeout_sec={timeout_sec}"
    )
    last_beat = started

    while time.time() < deadline:
        candidate = _latest_scan_log(log_root)
        if candidate is not None:
            if current_log is None:
                current_log = candidate
                # 日志可能在点击导入后才创建；从头读取，避免成功标识已写入后才首次轮询时被跳过。
                position = 0
                buffer = b""
            elif candidate != current_log and _path_mtime(candidate) >= _path_mtime(current_log):
                current_log = candidate
                position = 0
                buffer = b""
                print(f"[JENS][import_project] log_switched={current_log}")

            try:
                data, position = _read_new_bytes(current_log, position)
            except OSError:
                data = b""
            if data:
                buffer = (buffer + data)[-512 * 1024 :]
                if PROJECT_IMPORT_SUCCESS_KEY in data or PROJECT_IMPORT_SUCCESS_KEY in buffer:
                    elapsed = round(time.time() - started, 3)
                    print(
                        f"[JENS][import_project] success_marker={PROJECT_IMPORT_SUCCESS_KEY.decode()} "
                        f"log_file={current_log} elapsed_sec={elapsed}"
                    )
                    return current_log, elapsed
        time.sleep(max(0.1, poll_interval_sec))
        now = time.time()
        if now - last_beat >= 30.0:
            print(
                f"[JENS][import_project] 仍在等待导入成功日志... "
                f"已等待{now - started:.0f}s / 上限{timeout_sec:.0f}s，"
                f"log_file={current_log}"
            )
            last_beat = now

    raise RuntimeError(
        f"等待导入工程成功日志超时：{PROJECT_IMPORT_SUCCESS_KEY.decode()}，"
        f"log_file={current_log}，timeout_sec={timeout_sec}"
    )


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, touch, sleep  # type: ignore
        from pywinauto import Desktop  # type: ignore
        from pywinauto.findwindows import ElementNotFoundError  # type: ignore
        from pywinauto.timings import TimeoutError as PywinautoTimeoutError  # type: ignore
    except ImportError as exc:
        raise RuntimeError("未安装 Airtest 或 pywinauto，无法执行导入工程 Step。") from exc

    project_file = Path(str(params.get("project_file_path") or "")).expanduser().resolve()
    if not project_file.is_file() or project_file.name.casefold() != "project.obp":
        raise RuntimeError(f"无效的 CrealityScan 工程文件：{project_file}")

    process_id = int(ctx.get("process_id") or 0)
    if process_id <= 0:
        raise RuntimeError("导入工程 Step 缺少 CrealityScan 进程 ID")

    base = Path(__file__).resolve().parent / "templates"
    click_delay_sec = max(0.0, float(params.get("click_delay_sec", 1.0) or 1.0))
    log_dir_value = str(params.get("log_dir") or "").strip()
    case = ctx.get("case") if isinstance(ctx.get("case"), dict) else {}
    app = case.get("app") if isinstance(case.get("app"), dict) else {}
    log_root = Path(
        log_dir_value
        or str(app.get("log_dir") or "").strip()
        or (Path.home() / "AppData" / "Local" / "Creality" / "CrealityScan" / "Logs")
    )
    import_success_timeout_sec = max(
        1.0, float(params.get("import_success_timeout_sec", 600) or 600)
    )
    poll_interval_sec = max(0.1, float(params.get("poll_interval_sec", 0.2) or 0.2))
    baseline_log = _latest_scan_log(log_root)
    baseline_position = _path_size(baseline_log) if baseline_log is not None else 0

    # 来自你现有的 .air 用例（导入工程.air/导入工程.py）
    sleep(click_delay_sec)
    touch(Template(str(base / "tpl1772543115770.png"), record_pos=(0.054, -0.219), resolution=(1920, 1080)))
    sleep(click_delay_sec)
    touch(Template(str(base / "tpl1772543123954.png"), record_pos=(0.037, -0.172), resolution=(1920, 1080)))
    sleep(click_delay_sec)

    dialog_timeout_sec = max(1.0, float(params.get("dialog_timeout_sec", 15) or 15))
    try:
        dialog = Desktop(backend="win32").window(process=process_id, class_name="#32770")
        dialog.wait("exists visible enabled ready", timeout=dialog_timeout_sec)

        file_name_edit = dialog.child_window(control_id=1148, class_name="Edit")
        file_name_edit.wait("exists visible enabled ready", timeout=dialog_timeout_sec)
        file_name_edit.set_edit_text(str(project_file))
        sleep(click_delay_sec)

        open_button = dialog.child_window(control_id=1, class_name="Button")
        open_button.wait("exists visible enabled ready", timeout=dialog_timeout_sec)
        open_button.click_input()
        open_method = "click_input"
        try:
            dialog.wait_not("visible", timeout=3.0)
        except PywinautoTimeoutError:
            file_name_edit.set_focus()
            file_name_edit.type_keys("{ENTER}")
            open_method = "enter"
            dialog.wait_not("visible", timeout=dialog_timeout_sec)
    except (ElementNotFoundError, PywinautoTimeoutError, RuntimeError) as exc:
        raise RuntimeError(f"在工程选择窗口输入路径失败：{exc}") from exc

    success_log, import_elapsed_sec = _wait_project_import_success(
        log_root,
        baseline_log,
        baseline_position,
        import_success_timeout_sec,
        poll_interval_sec,
    )

    return {
        "project_file_path": str(project_file),
        "open_method": open_method,
        "success_marker": PROJECT_IMPORT_SUCCESS_KEY.decode(),
        "success_log_file": str(success_log),
        "import_elapsed_sec": import_elapsed_sec,
    }
