from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class CursorPos:
    x: int
    y: int


def _get_set_cursor_funcs():
    """
    返回 (get_pos, set_pos) 或 (None, None)。

    仅在 Windows 下可用；使用标准库 ctypes，避免额外依赖（KISS/YAGNI）。
    """
    if os.name != "nt":
        return None, None
    try:
        import ctypes
        from ctypes import wintypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        user32 = ctypes.WinDLL("user32", use_last_error=True)

        def get_pos() -> Optional[CursorPos]:
            pt = POINT()
            ok = user32.GetCursorPos(ctypes.byref(pt))
            if not ok:
                return None
            return CursorPos(int(pt.x), int(pt.y))

        def set_pos(x: int, y: int) -> bool:
            return bool(user32.SetCursorPos(int(x), int(y)))

        return get_pos, set_pos
    except Exception:
        return None, None


def move_mouse_smooth(
    pos: Tuple[int, int],
    *,
    duration_sec: float = 0.35,
    steps: int = 12,
) -> bool:
    """
    平滑移动鼠标到指定坐标。

    目的：让 hover 态/tooltip/动画有机会稳定，避免“移动过快导致后续模板识别失败”。
    """
    get_pos, set_pos = _get_set_cursor_funcs()
    if get_pos is None or set_pos is None:
        return False

    try:
        target_x, target_y = int(pos[0]), int(pos[1])
    except Exception:
        return False

    cur = get_pos()
    if cur is None:
        return False

    steps = int(steps) if isinstance(steps, int) else int(steps or 0)
    if steps <= 1 or duration_sec <= 0:
        return set_pos(target_x, target_y)

    dt = max(0.0, float(duration_sec)) / float(max(1, steps))
    x0, y0 = cur.x, cur.y
    dx, dy = target_x - x0, target_y - y0

    # 逐段移动，尽量减少“瞬移”
    for i in range(1, steps + 1):
        x = x0 + round(dx * i / steps)
        y = y0 + round(dy * i / steps)
        if not set_pos(x, y):
            return False
        if dt > 0:
            time.sleep(dt)
    return True

