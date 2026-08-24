"""
使用 Windows SendKeys 的简单文件选择方案
这个方案不依赖 pywinauto 的复杂查找逻辑
"""

import time
import win32gui
import win32con
import win32api

def select_file_simple(file_path, logger):
    """
    使用简单的 Windows API 选择文件

    Args:
        file_path: 文件路径
        logger: 日志记录器

    Returns:
        bool: 是否成功
    """
    try:
        logger.info("使用简单方法选择文件")

        # 等待文件对话框出现
        time.sleep(2)

        # 查找文件对话框窗口
        hwnd = None
        def enum_windows_callback(window_hwnd, _):
            nonlocal hwnd
            if win32gui.IsWindowVisible(window_hwnd):
                title = win32gui.GetWindowText(window_hwnd)
                if any(keyword in title.lower() for keyword in ['select', '选择', 'file', 'firmware']):
                    hwnd = window_hwnd
                    return False  # 停止枚举
            return True

        win32gui.EnumWindows(enum_windows_callback, None)

        if hwnd:
            logger.info(f"找到文件对话框: {win32gui.GetWindowText(hwnd)}")

            # 激活窗口
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.5)

            # 使用剪贴板和快捷键
            import pyperclip

            # 复制文件路径到剪贴板
            pyperclip.copy(file_path)
            time.sleep(0.2)

            # Ctrl+L 聚焦地址栏
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord('L'), 0, 0, 0)
            win32api.keybd_event(ord('L'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.3)

            # Ctrl+V 粘贴路径
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord('V'), 0, 0, 0)
            win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.5)

            # 按回车
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(1)

            logger.info("文件选择完成")
            return True
        else:
            logger.error("未找到文件对话框")
            return False

    except Exception as e:
        logger.error(f"简单文件选择失败: {e}")
        return False
