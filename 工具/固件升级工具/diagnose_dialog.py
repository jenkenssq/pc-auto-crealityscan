"""
文件对话框诊断脚本
用于查看当前所有窗口的标题和属性

使用方法：
1. 运行 CrealityScan
2. 点击"选择文件"按钮，让文件对话框弹出
3. 运行此脚本：python diagnose_dialog.py
4. 查看输出，找到文件对话框的实际标题
"""

import win32gui
import win32con

print("=" * 60)
print("文件对话框诊断工具")
print("=" * 60)
print("\n请确保文件选择对话框已经打开，然后按回车继续...")
input()

print("\n正在扫描所有窗口...\n")

windows_list = []

def enum_windows_callback(hwnd, _):
    """枚举所有窗口"""
    if win32gui.IsWindowVisible(hwnd):
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if title:  # 只显示有标题的窗口
            windows_list.append({
                'hwnd': hwnd,
                'title': title,
                'class': class_name
            })
    return True

try:
    # 枚举所有窗口
    win32gui.EnumWindows(enum_windows_callback, None)

    print(f"找到 {len(windows_list)} 个可见窗口：\n")

    for i, win in enumerate(windows_list, 1):
        print(f"窗口 {i}:")
        print(f"  标题: {win['title']}")
        print(f"  类名: {win['class']}")

        # 检查是否可能是文件对话框
        title_lower = win['title'].lower()
        if any(keyword in title_lower for keyword in ['select', '选择', 'file', 'firmware', 'please', 'open']):
            print(f"  ⭐ 可能是文件对话框！")

        print()

    print("=" * 60)
    print("诊断完成")
    print("=" * 60)

    # 查找最可能的文件对话框
    print("\n最可能的文件对话框：\n")

    for win in windows_list:
        title_lower = win['title'].lower()
        if any(keyword in title_lower for keyword in ['select', '选择', 'firmware']):
            print(f"✓ 标题: {win['title']}")
            print(f"  类名: {win['class']}")
            print()

except Exception as e:
    print(f"\n错误: {e}")
    import traceback
    traceback.print_exc()

print("\n按回车退出...")
input()
