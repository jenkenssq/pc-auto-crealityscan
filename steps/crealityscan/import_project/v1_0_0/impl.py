from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, touch, sleep  # type: ignore
    except Exception as e:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from e

    base = Path(__file__).resolve().parent / "templates"

    # 来自你现有的 .air 用例（导入工程.air/导入工程.py）
    touch(Template(str(base / "tpl1772543115770.png"), record_pos=(0.054, -0.219), resolution=(1920, 1080)))
    sleep(0.3)
    touch(Template(str(base / "tpl1772543123954.png"), record_pos=(0.037, -0.172), resolution=(1920, 1080)))
    return {}

