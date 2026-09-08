from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, touch  # type: ignore
    except Exception as e:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from e

    base = Path(__file__).resolve().parent / "templates"

    # 来自你现有的 .air 用例（新建项目.air/新建项目.py）
    touch(Template(str(base / "tpl1772625196696.png"), record_pos=(-0.062, -0.167), resolution=(1920, 1080)))
    touch(Template(str(base / "tpl1772625206617.png"), record_pos=(0.084, 0.052), resolution=(1920, 1080)))
    return {}

