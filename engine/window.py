"""
Windows 窗口激活/置顶工具。

说明：
- 为了提升纯图像识别（Template）点击的稳定性，在每个步骤执行前
  都尽量把 CrealityScan 窗口拉到前台并激活焦点。
- 不引入第三方依赖，使用 ctypes 调用 Win32 API。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional, Tuple


user32 = ctypes.WinDLL("user32", use_last_error=True)


EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _get_window_text(hwnd: wintypes.HWND) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


def _is_window_visible(hwnd: wintypes.HWND) -> bool:
    return bool(user32.IsWindowVisible(hwnd))


def find_window_by_title_contains(title_substring: str) -> Optional[int]:
    if not title_substring:
        return None

    title_substring_lower = title_substring.lower()
    found_hwnd: Optional[int] = None

    def _callback(hwnd: wintypes.HWND, lparam: wintypes.LPARAM) -> wintypes.BOOL:
        nonlocal found_hwnd
        if found_hwnd is not None:
            return False
        if not _is_window_visible(hwnd):
            return True
        title = _get_window_text(hwnd)
        if title and title_substring_lower in title.lower():
            found_hwnd = int(hwnd)
            return False
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    return found_hwnd


def activate_window(title_contains: str, fullscreen: bool = False) -> bool:
    """
    尝试激活并置顶包含指定标题片段的窗口。
    返回是否找到窗口并尝试激活。
    """
    hwnd = find_window_by_title_contains(title_contains)
    if hwnd is None:
        return False

    # ShowWindow:
    # - 3 = SW_MAXIMIZE（最大化，便于硬坐标点击稳定）
    # - 5 = SW_SHOW（保持当前大小状态显示；避免把“已最大化窗口”还原成窗口化）
    # - 9 = SW_RESTORE（仅在最小化时用于恢复）
    if fullscreen:
        user32.ShowWindow(hwnd, 3)
    else:
        # 仅当窗口最小化时才 restore；否则 show 保持当前状态（最大化/正常）
        if bool(user32.IsIconic(hwnd)):
            user32.ShowWindow(hwnd, 9)
        else:
            user32.ShowWindow(hwnd, 5)

    # 先置顶再取消置顶，通常能把窗口拉到最前
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_SHOWWINDOW = 0x0040
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

    user32.SetForegroundWindow(hwnd)
    return True


def get_primary_screen_size() -> Tuple[int, int]:
    # GetSystemMetrics: 0=SM_CXSCREEN, 1=SM_CYSCREEN
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def get_window_dpi(hwnd: int) -> Optional[int]:
    """
    获取窗口 DPI（用于推算缩放比例）。不同 Windows 版本 API 可用性不同，失败则返回 None。
    """
    try:
        fn = user32.GetDpiForWindow  # type: ignore[attr-defined]
        fn.restype = wintypes.UINT
        fn.argtypes = [wintypes.HWND]
        return int(fn(hwnd))
    except Exception:
        try:
            fn = user32.GetDpiForSystem  # type: ignore[attr-defined]
            fn.restype = wintypes.UINT
            fn.argtypes = []
            return int(fn())
        except Exception:
            return None


def get_window_status(title_contains: str) -> dict:
    """
    返回窗口状态摘要，用于 UI 运行前检查。
    """
    hwnd = find_window_by_title_contains(title_contains)
    if hwnd is None:
        return {"found": False}
    try:
        minimized = bool(user32.IsIconic(hwnd))
    except Exception:
        minimized = False
    try:
        maximized = bool(user32.IsZoomed(hwnd))
    except Exception:
        maximized = False
    dpi = get_window_dpi(hwnd)
    scale_percent = int(round(dpi / 96 * 100)) if dpi else None
    return {
        "found": True,
        "hwnd": int(hwnd),
        "title": _get_window_text(hwnd),
        "minimized": minimized,
        "maximized": maximized,
        "dpi": dpi,
        "scale_percent": scale_percent,
    }
