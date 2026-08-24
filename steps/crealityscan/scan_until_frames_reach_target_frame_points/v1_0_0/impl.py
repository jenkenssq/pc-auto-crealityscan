from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from engine.mouse import move_mouse_smooth
from engine.slide_rail_scan_motion import SlideRailScanMotion


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


def _click_template(wait, touch, tpl, timeout_sec: float, retry: int, reset_hover) -> None:
    last_err: Optional[Exception] = None
    for _ in range(max(0, retry) + 1):
        reset_hover()
        try:
            pos = wait(tpl, timeout=timeout_sec)
            touch(pos)
            return
        except Exception as e:
            last_err = e
    raise RuntimeError(f"未找到按钮模板：{tpl.filename}") from last_err


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, device, sleep, touch, wait  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "无法导入 Airtest（airtest.core.api）。请先安装依赖：python -m pip install -r requirements.txt"
        ) from e

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
    wait_before_pause_sec = max(0.0, _num(params, "wait_before_pause_sec", 5))

    start_btn_timeout_sec = _num(params, "start_btn_timeout_sec", 10)
    start_btn_retry = _int(params, "start_btn_retry", 1)
    start_btn_threshold = _num(params, "start_btn_threshold", 0.7)
    pause_btn_timeout_sec = _num(params, "pause_btn_timeout_sec", 10)
    pause_btn_retry = _int(params, "pause_btn_retry", 1)
    pause_btn_threshold = _num(params, "pause_btn_threshold", 0.7)

    start_tpl = Template(
        str(base / "tpl1773309569794.png"),
        record_pos=(-0.412, -0.227),
        resolution=(1920, 1080),
        threshold=start_btn_threshold,
    )
    pause_tpl = Template(
        str(base / "tpl1773230381539.png"),
        record_pos=(-0.41, -0.224),
        resolution=(1920, 1080),
        threshold=pause_btn_threshold,
    )

    def reset_hover() -> None:
        _reset_mouse_hover(params, move_to, sleep)

    _click_template(wait, touch, start_tpl, start_btn_timeout_sec, start_btn_retry, reset_hover)
    print("[JENS] frame_points start clicked")

    slide_motion = SlideRailScanMotion(params)
    slide_motion.start()
    try:
        sleep(wait_before_pause_sec)
    finally:
        slide_motion.stop()

    _click_template(wait, touch, pause_tpl, pause_btn_timeout_sec, pause_btn_retry, reset_hover)
    print("[JENS] frame_points pause clicked")

    return {
        "wait_before_pause_sec": wait_before_pause_sec,
        "slide_rail_scan_motion": slide_motion.to_extra(),
    }
