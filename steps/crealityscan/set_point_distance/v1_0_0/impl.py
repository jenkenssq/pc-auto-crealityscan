from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple


def _coerce_pos(v: Any, default: Tuple[int, int]) -> Tuple[int, int]:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        try:
            return int(v[0]), int(v[1])
        except Exception:
            return default
    return default


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import sleep, text, touch  # type: ignore
    except Exception as e:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from e

    distance_mm = str(params.get("distance_mm", "0.45") or "0.45").strip()
    delay_sec = float(params.get("delay_sec", 0.2) or 0.2)
    input_pos = _coerce_pos(params.get("input_pos"), default=(300, 450))

    # 采用硬坐标点击文本框（需要 1920x1080、100% 缩放、窗口最大化）
    touch(input_pos)

    sleep(delay_sec)

    text(distance_mm)
    return {"distance_mm": distance_mm, "input_pos": list(input_pos)}
