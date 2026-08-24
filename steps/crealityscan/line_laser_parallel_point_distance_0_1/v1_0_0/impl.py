from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, swipe, touch  # type: ignore
    except Exception as e:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from e

    base = Path(__file__).resolve().parent / "templates"

    # 来自你现有的 .air 用例（线激光-平行线-点距0.1.air/线激光-平行线-点距0.1.py）
    touch(Template(str(base / "tpl1772617230089.png"), record_pos=(-0.418, -0.128), resolution=(1920, 1080)))
    swipe(
        Template(str(base / "tpl1772617298274.png"), record_pos=(-0.393, -0.02), resolution=(1920, 1080)),
        vector=[-0.04, -0.0009],
    )
    touch(Template(str(base / "tpl1772617363649.png"), record_pos=(-0.436, 0.028), resolution=(1920, 1080)))
    touch(Template(str(base / "tpl1772617391149.png"), record_pos=(-0.378, -0.174), resolution=(1920, 1080)))
    return {}

