from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from engine.mouse import move_mouse_smooth


# 预览成功判定关键字：满足任一即视为预览成功。
# - OB_SCAN_MESSAGE_ID_SCANNING_PREVIEW_SUCCESS：多数机型/版本会输出的进程消息。
# - change to preview success：部分版本（如 Raptor Pro USB）仅输出该行，不含上方进程消息。
PREVIEW_SUCCESS_KEYS = (
    b"OB_SCAN_MESSAGE_ID_SCANNING_PREVIEW_SUCCESS",
    b"change to preview success",
)


def _num(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except Exception:
        return float(default)


def _int(params: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except Exception:
        return int(default)


def _read_new_bytes(fp: Path, pos: int) -> Tuple[bytes, int]:
    with fp.open("rb") as f:
        try:
            size = int(fp.stat().st_size)
        except Exception:
            size = 0
        if pos < 0 or pos > size:
            pos = 0
        f.seek(pos)
        data = f.read()
        return data, f.tell()


def _path_mtime(fp: Path) -> float:
    try:
        return float(fp.stat().st_mtime)
    except Exception:
        return 0.0


def _path_size(fp: Path) -> int:
    try:
        return int(fp.stat().st_size)
    except Exception:
        return 0


def _scan_log_sort_key(fp: Path) -> Tuple[float, str]:
    return (_path_mtime(fp), fp.name)


def _latest_session_dir(log_root: Path) -> Optional[Path]:
    try:
        dirs = [p for p in log_root.iterdir() if p.is_dir()]
    except Exception:
        return None
    if not dirs:
        return None
    return max(dirs, key=_path_mtime)


def _latest_scan_log_in_dir(session_dir: Path) -> Optional[Path]:
    try:
        files = [p for p in session_dir.glob("scan_log_*.txt") if p.is_file()]
    except Exception:
        return None
    if not files:
        return None
    return max(files, key=_scan_log_sort_key)


def _try_pick_scan_log(log_root: Path) -> Optional[Path]:
    if log_root.is_file():
        return log_root

    session = _latest_session_dir(log_root)
    if session:
        fp = _latest_scan_log_in_dir(session)
        if fp:
            return fp

    try:
        files = [p for p in log_root.rglob("scan_log_*.txt") if p.is_file()]
    except Exception:
        files = []
    if not files:
        return None
    return max(files, key=_scan_log_sort_key)


def _should_switch_scan_log(current_fp: Optional[Path], candidate: Optional[Path], pos: int) -> bool:
    if candidate is None:
        return False
    if current_fp is None:
        return True
    if candidate == current_fp:
        return False
    if _path_mtime(candidate) > _path_mtime(current_fp):
        return True
    current_size = _path_size(current_fp)
    if current_size > 0 and pos >= current_size:
        return True
    return False


def _read_live_scan_log(log_root: Path, current_fp: Optional[Path], pos: int) -> Tuple[Optional[Path], bytes, int, bool]:
    candidate = _try_pick_scan_log(log_root)
    switched = False
    if _should_switch_scan_log(current_fp, candidate, pos):
        current_fp = candidate
        pos = 0
        switched = True
    if current_fp is None:
        return None, b"", pos, switched
    data, pos = _read_new_bytes(current_fp, pos)
    return current_fp, data, pos, switched


def _wait_scan_log(log_root: Path, timeout_sec: float, poll_interval_sec: float) -> Path:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        cand = _try_pick_scan_log(log_root)
        if cand and cand.exists():
            return cand
        time.sleep(max(0.2, poll_interval_sec))
    raise RuntimeError(f"未找到 scan_log_*.txt：{log_root}")


def _first_key_in(buf: bytes, keys: Sequence[bytes]) -> Optional[bytes]:
    for key in keys:
        if key in buf:
            return key
    return None


def _wait_log_contains(
    log_root: Path, fp: Path, start_pos: int, keys: Sequence[bytes], timeout_sec: float, poll_interval_sec: float
) -> Tuple[Path, int, bytes]:
    deadline = time.time() + timeout_sec
    current_fp = fp
    pos = start_pos
    buf = b""
    while time.time() < deadline:
        data, pos = _read_new_bytes(current_fp, pos)
        if data:
            buf += data
            if len(buf) > 512 * 1024:
                buf = buf[-512 * 1024 :]
            matched = _first_key_in(buf, keys)
            if matched is not None:
                return current_fp, pos, matched

        candidate = _try_pick_scan_log(log_root)
        if _should_switch_scan_log(current_fp, candidate, pos) and candidate is not None:
            current_fp = candidate
            pos = 0
            buf = b""
            print(f"[JENS] preview log_file={current_fp}")

            data, pos = _read_new_bytes(current_fp, pos)
            if data:
                buf = data[-512 * 1024 :]
                matched = _first_key_in(buf, keys)
                if matched is not None:
                    return current_fp, pos, matched
        time.sleep(max(0.2, poll_interval_sec))
    raise RuntimeError(f"等待预览成功日志超时：{keys!r} in {current_fp}")


def _reset_mouse_hover(params: Dict[str, Any], move_to, sleep) -> None:
    safe_x = _int(params, "mouse_safe_x", 10)
    safe_y = _int(params, "mouse_safe_y", 10)
    move_duration_sec = _num(params, "mouse_safe_move_duration_sec", 0.35)
    move_steps = _int(params, "mouse_safe_move_steps", 12)
    sleep_sec = _num(params, "mouse_safe_sleep_sec", 0.35)
    try:
        ok = move_mouse_smooth((safe_x, safe_y), duration_sec=move_duration_sec, steps=move_steps)
        if not ok:
            move_to((safe_x, safe_y))
    except Exception:
        return
    try:
        sleep(max(0.0, sleep_sec))
    except Exception:
        pass


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, device, sleep, touch  # type: ignore
    except Exception as e:
        raise RuntimeError("无法导入 Airtest（airtest.core.api）。请先安装依赖：python -m pip install -r requirements.txt") from e

    try:
        from airtest.core.api import move_to as _move_to  # type: ignore
    except Exception:
        _move_to = None

    def move_to(pos) -> None:
        if _move_to is not None:
            _move_to(pos)
            return
        dev = device()
        if hasattr(dev, "move"):
            dev.move(pos)
            return
        if hasattr(dev, "mouse_move"):
            dev.mouse_move(pos)
            return
        raise RuntimeError("当前设备不支持鼠标移动（缺少 move/mouse_move）。")

    case = ctx.get("case") if isinstance(ctx.get("case"), dict) else {}
    app = case.get("app") if isinstance(case.get("app"), dict) else {}

    log_dir_param = str(params.get("log_dir") or "").strip()
    log_dir_case = str(app.get("log_dir") or "").strip()
    if log_dir_param or log_dir_case:
        log_root = Path(log_dir_param or log_dir_case)
    else:
        log_root = Path.home() / "AppData" / "Local" / "Creality" / "CrealityScan" / "Logs"

    timeout_sec = _num(params, "timeout_sec", 60)
    wait_log_file_timeout_sec = _num(params, "wait_log_file_timeout_sec", 15)
    poll_interval_sec = _num(params, "poll_interval_sec", 0.5)
    after_click_sleep_sec = _num(params, "after_click_sleep_sec", 0.3)

    base = Path(__file__).resolve().parent / "templates"
    preview_tpl = Template(str(base / "tpl1772635127022.png"), record_pos=(-0.41, -0.227), resolution=(1920, 1080))

    current_fp = _try_pick_scan_log(log_root)
    start_pos = _path_size(current_fp) if current_fp is not None else 0
    if current_fp is not None:
        print(f"[JENS] preview log_file={current_fp}")

    print("[JENS] preview click")
    _reset_mouse_hover(params, move_to, sleep)
    touch(preview_tpl)
    if after_click_sleep_sec > 0:
        sleep(max(0.0, after_click_sleep_sec))

    if current_fp is None:
        current_fp = _wait_scan_log(log_root, max(0.2, wait_log_file_timeout_sec), poll_interval_sec)
        start_pos = 0
        print(f"[JENS] preview log_file={current_fp}")

    current_fp, end_pos, matched_key = _wait_log_contains(
        log_root,
        current_fp,
        start_pos,
        PREVIEW_SUCCESS_KEYS,
        max(0.2, timeout_sec),
        poll_interval_sec,
    )
    print(f"[JENS] preview success log matched: {matched_key.decode('utf-8', errors='ignore')}")
    return {
        "log_file": str(current_fp),
        "success_key": matched_key.decode("utf-8", errors="ignore"),
        "end_pos": end_pos,
    }
