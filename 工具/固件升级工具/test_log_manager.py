"""
LogManager功能测试脚本
用于验证日志管理器的各项功能
"""

import sys
sys.path.append('.')

from utils.log_manager import LogManager

def test_log_manager():
    """测试LogManager的基本功能"""

    print("=" * 60)
    print("LogManager 功能测试")
    print("=" * 60)

    # 初始化LogManager
    log_dir = r"C:\Users\zengx\AppData\Local\Creality\CrealityScan\Logs"
    log_manager = LogManager(log_dir)

    # 测试1: 刷新并定位最新日志目录
    print("\n[测试1] 刷新并定位最新日志目录")
    success = log_manager.refresh_latest_log_dir()
    if success:
        info = log_manager.get_log_dir_info()
        print(f"✓ 成功定位日志目录")
        print(f"  - 当前日志目录: {info['current_log_dir']}")
        print(f"  - app.log路径: {info['app_log_path']}")
        print(f"  - scan_log路径: {info['scan_log_path']}")
    else:
        print("✗ 未能定位日志目录")
        return

    # 测试2: 获取最新帧数
    print("\n[测试2] 获取最新帧数")
    frame_count = log_manager.get_latest_frame_count()
    if frame_count is not None:
        print(f"✓ 当前帧数: {frame_count}")
    else:
        print("✗ 未找到帧数信息")

    # 测试3: 检测彩色相机
    print("\n[测试3] 检测彩色相机")
    has_color = log_manager.has_color_camera()
    print(f"{'✓' if has_color else '✗'} 彩色相机: {'存在' if has_color else '不存在'}")

    # 测试4: 检查设备连接状态
    print("\n[测试4] 检查设备连接状态")
    is_connected = log_manager.is_device_connected()
    print(f"{'✓' if is_connected else '✗'} 设备状态: {'已连接' if is_connected else '未连接'}")

    # 测试5: 获取当前扫描状态
    print("\n[测试5] 获取当前扫描状态")
    scan_status = log_manager.get_current_scan_status()
    if scan_status:
        print(f"✓ 扫描状态: {scan_status}")
    else:
        print("✗ 未找到扫描状态信息")

    # 测试6: 搜索app.log中的关键字
    print("\n[测试6] 搜索app.log中的升级相关信息")
    upgrade_results = log_manager.search_in_app_log("Upgrade", use_regex=False)
    if upgrade_results:
        print(f"✓ 找到 {len(upgrade_results)} 条升级相关记录")
        # 显示最后3条
        for line_num, line in upgrade_results[-3:]:
            print(f"  行{line_num}: {line[:80]}...")
    else:
        print("✗ 未找到升级相关信息")

    # 测试7: 读取最后几行日志
    print("\n[测试7] 读取app.log最后10行")
    last_lines = log_manager.tail_app_log(lines=10)
    if last_lines:
        print(f"✓ 成功读取最后 {len(last_lines)} 行")
        for i, line in enumerate(last_lines[-3:], 1):
            print(f"  {i}. {line[:80]}...")
    else:
        print("✗ 未能读取日志")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_log_manager()
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
