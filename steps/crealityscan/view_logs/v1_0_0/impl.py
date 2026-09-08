from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, touch, sleep, snapshot  # type: ignore
    except Exception as e:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from e

    base = Path(__file__).resolve().parent / "templates"

    # 来自你现有的 .air 用例（查看日志.air/查看日志.py）
    touch(Template(str(base / "tpl1772543502314.png"), record_pos=(0.314, -0.273), resolution=(1920, 1080)))
    sleep(0.3)
    touch(Template(str(base / "tpl1772543522896.png"), record_pos=(0.19, -0.029), resolution=(1920, 1080)))
    sleep(0.8)

    # 验收：打开后截图定位（先按你给的标准：打开成功即可）
    run_dir = Path(str(ctx.get("run_dir") or "."))
    shot = run_dir / "screenshots" / f"step{int(ctx.get('step_index') or 0):03d}_view_logs.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    snapshot(filename=str(shot))
    return {"snapshot": str(shot)}

