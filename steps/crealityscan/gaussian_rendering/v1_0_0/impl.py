from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict


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
