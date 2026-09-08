from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, sleep, touch  # type: ignore
    except ImportError as exc:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from exc

    base = Path(__file__).resolve().parent / "templates"

    touch(
        Template(
            str(base / "tpl1772721639120.png"),
            record_pos=(-0.349, -0.273),
            resolution=(1920, 1080),
        )
    )
    touch(
        Template(
            str(base / "tpl1772721648947.png"),
            record_pos=(0.053, 0.021),
            resolution=(1920, 1080),
        )
    )
    # 点击确认后等待首页切换完成，再允许后续 Step 继续执行。
    sleep(3)
    return {"ready_wait_sec": 3}
