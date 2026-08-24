from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from engine.mouse import move_mouse_smooth


def _num(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _int(params: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        return int(default)


def _reset_mouse_hover(params: Dict[str, Any], move_to, sleep) -> None:
    """
    选择操作按钮后，鼠标停留在控件上可能触发 hover 态，
    导致后续模板/坐标点击对应的 UI 发生变化而失败。
    """
    safe_x = _int(params, "mouse_safe_x", 10)
    safe_y = _int(params, "mouse_safe_y", 10)
    move_duration_sec = _num(params, "mouse_safe_move_duration_sec", 0.35)
    move_steps = _int(params, "mouse_safe_move_steps", 12)
    sleep_sec = _num(params, "mouse_safe_sleep_sec", 0.3)
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
        from airtest.core.api import Template, device, exists, snapshot, touch, wait, sleep  # type: ignore
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

    # 来自你现有的 .air 用例（进行融合操作.air/进行融合操作.py）
    operation_started = time.time()
    touch(Template(str(base / "tpl1772612713234.png"), record_pos=(-0.18, -0.134), resolution=(1920, 1080)))
    _reset_mouse_hover(params, move_to, sleep)
    touch(Template(str(base / "tpl1772612725223.png"), record_pos=(-0.306, 0.009), resolution=(1920, 1080)))
    _reset_mouse_hover(params, move_to, sleep)

    progress = Template(str(base / "tpl1772613138515.png"), record_pos=(-0.016, 0.052), resolution=(1920, 1080))
    wait(progress)

    timeout_sec = float(params.get("timeout_sec", 300) or 300)
    progress_started = time.time()
    while time.time() - progress_started < timeout_sec:
        if not exists(progress):
            break
        sleep(0.5)
    else:
        raise RuntimeError("等待进度条超时")

    operation_elapsed_sec = round(time.time() - operation_started, 3)
    run_dir = Path(str(ctx.get("run_dir") or "."))
    shot = run_dir / "screenshots" / f"step{int(ctx.get('step_index') or 0):03d}_fusion_operation.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    snapshot(filename=str(shot))
    return {
        "snapshot": str(shot),
        "operation_elapsed_sec": operation_elapsed_sec,
        "operation_elapsed_label": "融合耗时",
    }

