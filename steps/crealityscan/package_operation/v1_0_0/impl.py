from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, exists, snapshot, touch, wait, sleep  # type: ignore
    except Exception as e:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from e

    base = Path(__file__).resolve().parent / "templates"

    # 只保留当前 UI 仍然有效的 3 张模板；旧模板 tpl1772624677862.png 已废弃。
    entry = Template(str(base / "tpl1772613488033.png"), record_pos=(-0.343, -0.134), resolution=(1920, 1080))
    confirm = Template(str(base / "tpl1772613496430.png"), record_pos=(-0.307, 0.131), resolution=(1920, 1080))
    progress = Template(str(base / "tpl1772613590748.png"), record_pos=(-0.004, 0.017), resolution=(1920, 1080))

    operation_started = time.time()
    touch(entry)
    touch(confirm)
    wait(progress)

    timeout_sec = float(params.get("timeout_sec", 60) or 60)
    progress_started = time.time()
    while time.time() - progress_started < timeout_sec:
        if not exists(progress):
            break
        sleep(0.5)
    else:
        raise RuntimeError("等待进度条超时")

    operation_elapsed_sec = round(time.time() - operation_started, 3)
    run_dir = Path(str(ctx.get("run_dir") or "."))
    shot = run_dir / "screenshots" / f"step{int(ctx.get('step_index') or 0):03d}_package_operation.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    snapshot(filename=str(shot))
    return {
        "snapshot": str(shot),
        "operation_elapsed_sec": operation_elapsed_sec,
        "operation_elapsed_label": "封装耗时",
    }
