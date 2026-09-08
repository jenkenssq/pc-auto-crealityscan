from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict


def _reset_mouse_hover(params: Dict[str, Any], sleep) -> None:
    import ctypes

    safe_x = int(params.get("mouse_safe_x", 10) or 10)
    safe_y = int(params.get("mouse_safe_y", 10) or 10)
    sleep_sec = max(0.0, float(params.get("mouse_safe_sleep_sec", 0.3) or 0.3))
    ctypes.windll.user32.SetCursorPos(safe_x, safe_y)
    sleep(sleep_sec)


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, exists, snapshot, touch, wait, sleep  # type: ignore
    except ImportError as exc:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from exc

    base = Path(__file__).resolve().parent / "templates"

    # 来自你现有的 .air 用例（进行贴图操作.air/进行贴图操作.py）
    operation_started = time.time()
    touch((160, 285))
    touch(Template(str(base / "tpl1774270225446.png"), record_pos=(-0.277, -0.254), resolution=(1920, 1080)))
    touch(Template(str(base / "tpl1772613788279.png"), record_pos=(-0.089, -0.177), resolution=(1920, 1080)))

    progress = Template(str(base / "tpl1772613816094.png"), record_pos=(-0.07, 0.008), resolution=(1920, 1080))
    wait(progress)

    timeout_sec = float(params.get("timeout_sec", 180) or 180)
    progress_started = time.time()
    while time.time() - progress_started < timeout_sec:
        if not exists(progress):
            break
        sleep(0.5)
    else:
        raise RuntimeError("等待进度条超时")

    operation_elapsed_sec = round(time.time() - operation_started, 3)
    run_dir = Path(str(ctx.get("run_dir") or "."))
    shot = run_dir / "screenshots" / f"step{int(ctx.get('step_index') or 0):03d}_texture_operation.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    _reset_mouse_hover(params, sleep)
    snapshot(filename=str(shot))
    return {
        "snapshot": str(shot),
        "operation_elapsed_sec": operation_elapsed_sec,
        "operation_elapsed_label": "贴图耗时",
    }
