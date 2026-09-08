from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from engine.mouse import move_mouse_smooth


# 切点云成功需依次出现的日志标志。每个位置可命中其任一候选字节串：
# 第 0 位是“标定框架优化成功”：
#   旧固件输出 OB_SCAN_MESSAGE_ID_MARKER_FRAMEWORK_OPTIMIZATION_SUCCESS，
#   Sermoon S1 等新固件不输出该行，而改为输出 marker_opt progress 1.000000（优化进度 100%）。
POINT_CLOUD_SWITCH_READY_KEY_GROUPS = (
    (
        b"OB_SCAN_MESSAGE_ID_MARKER_FRAMEWORK_OPTIMIZATION_SUCCESS",
        b"marker_opt progress 1.000000",
    ),
    (b"obscan_scan_reconfig_scan_mode_config",),
    (b"scan_type: OB_SCAN_CLOUD_FUSED",),
    (b"start stream done.",),
    (b"config property ex done.",),
)
POINT_CLOUD_SWITCH_TIMEOUT_SEC = 120.0
LOG_POLL_INTERVAL_SEC = 0.5


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


def _latest_scan_log(log_root: Path) -> Path:
    if log_root.is_file():
        return log_root
    try:
        files = [p for p in log_root.rglob("scan_log_*.txt") if p.is_file()]
    except OSError as exc:
        raise RuntimeError(f"读取 CrealityScan 日志目录失败：{log_root}") from exc
    if not files:
        raise RuntimeError(f"未找到 scan_log_*.txt：{log_root}")
    return max(files, key=lambda p: p.stat().st_mtime)


def _first_group_match(buf: bytes, group: tuple[bytes, ...]) -> tuple[bytes, int] | None:
    """返回 buf 中 group 里最早命中的候选字节串及其位置，未命中返回 None。"""
    best_key = None
    best_pos = -1
    for key in group:
        pos = buf.find(key)
        if pos >= 0 and (best_pos < 0 or pos < best_pos):
            best_key = key
            best_pos = pos
    return (best_key, best_pos) if best_key is not None else None


def _wait_point_cloud_switch_success(log_file: Path, start_pos: int) -> None:
    deadline = time.monotonic() + POINT_CLOUD_SWITCH_TIMEOUT_SEC
    pos = start_pos
    buf = b""
    read_failures = 0
    next_group_index = 0

    while time.monotonic() < deadline:
        try:
            size = log_file.stat().st_size
            if pos > size:
                pos = 0
            with log_file.open("rb") as fp:
                fp.seek(pos)
                data = fp.read()
                pos = fp.tell()
            read_failures = 0
        except OSError as exc:
            read_failures += 1
            if read_failures > 2:
                raise RuntimeError(f"读取扫描日志失败（已重试 2 次）：{log_file}") from exc
            time.sleep(LOG_POLL_INTERVAL_SEC)
            continue

        if data:
            buf += data
            while next_group_index < len(POINT_CLOUD_SWITCH_READY_KEY_GROUPS):
                group = POINT_CLOUD_SWITCH_READY_KEY_GROUPS[next_group_index]
                match = _first_group_match(buf, group)
                if match is None:
                    break
                matched_key, match_pos = match
                print(f"[JENS] point_cloud_switch log matched: {matched_key.decode('ascii')}")
                buf = buf[match_pos + len(matched_key) :]
                next_group_index += 1
            if next_group_index == len(POINT_CLOUD_SWITCH_READY_KEY_GROUPS):
                return
            buf = buf[-4096:]
        time.sleep(LOG_POLL_INTERVAL_SEC)

    next_group = POINT_CLOUD_SWITCH_READY_KEY_GROUPS[next_group_index]
    next_keys = b" | ".join(next_group)
    raise RuntimeError(
        f"等待切换点云成功日志超时，下一标志：{next_keys!r} in {log_file}"
    )


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
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from e

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

    base = Path(__file__).resolve().parent / "templates"

    # 来自你现有的 .air 用例（暂停切点云扫描.air/暂停切点云扫描.py）
    # 这里仅保留“切点云”动作；暂停动作已交给其他步骤处理。
    _reset_mouse_hover(params, move_to, sleep)
    touch(Template(str(base / "tpl1773230391353.png"), record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
    _reset_mouse_hover(params, move_to, sleep)

    case = ctx.get("case") if isinstance(ctx.get("case"), dict) else {}
    app = case.get("app") if isinstance(case.get("app"), dict) else {}
    log_dir = str(app.get("log_dir") or "").strip()
    log_root = (
        Path(log_dir)
        if log_dir
        else Path.home() / "AppData" / "Local" / "Creality" / "CrealityScan" / "Logs"
    )
    log_file = _latest_scan_log(log_root)
    start_pos = log_file.stat().st_size

    touch(Template(str(base / "tpl1773230445234.png"), record_pos=(0.055, 0.02), resolution=(1920, 1080)))
    _wait_point_cloud_switch_success(log_file, start_pos)
    ready_stable_sec = max(0.0, _num(params, "ready_stable_sec", 1.0))
    if ready_stable_sec > 0:
        sleep(ready_stable_sec)
    return {}
