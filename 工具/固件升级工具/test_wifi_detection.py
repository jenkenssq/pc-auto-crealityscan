"""
WiFi模组检测功能测试
用于验证各种WiFi模组的连接检测逻辑

支持的WiFi模组:
- Sermoon X1 WiFi
- Sermoon S1 WiFi
- Otter系列WiFi（可扩展）
"""

import sys
import io
# 设置标准输出编码为UTF-8，解决Windows控制台编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.append('.')

from utils.log_manager import LogManager
from unittest.mock import Mock, patch, MagicMock
from io import StringIO


# ============================================================
# 测试数据：模拟各种WiFi模组的日志内容
# ============================================================

SAMPLE_LOGS = {
    # Sermoon X1 WiFi（X1模组 + WiFi手柄）
    'x1wifi_connected': '''
[2024-01-15 10:01:05.123] [INFO] OnDeviceConnect: scannerPid:SCANNER_SERMOON_X1, scannerName:Sermoon X1
[2024-01-15 10:01:05.456] [INFO] wifiBridgePid:SCAN_BRIDGE, wifiBridgeName:WiFi Handle
[2024-01-15 10:01:06.000] [INFO] Device connected successfully
''',

    # Sermoon X1 WiFi - X1模组断开后（WiFi手柄仍在线）
    'x1wifi_x1_disconnected': '''
[2024-01-15 10:02:26.123] [INFO] OnDeviceDisconnect: scannerPid:UNKNOWN, scannerName:Wifi Handle
[2024-01-15 10:02:26.456] [INFO] wifiBridgePid:SCAN_BRIDGE, wifiBridgeName:WiFi Handle
''',

    # Sermoon X1 WiFi - X1模组重连后
    'x1wifi_reconnected': '''
[2024-01-15 10:02:57.123] [INFO] OnDeviceConnect: scannerPid:SCANNER_SERMOON_X1, scannerName:Sermoon X1
[2024-01-15 10:02:57.456] [INFO] wifiBridgePid:SCAN_BRIDGE, wifiBridgeName:WiFi Handle
[2024-01-15 10:02:58.000] [INFO] Device reconnected successfully
''',

    # Sermoon S1 WiFi
    's1wifi_connected': '''
[2024-01-15 10:01:05.123] [INFO] OnDeviceConnect: scannerPid:SCANNER_SERMOON_S1, scannerName:Sermoon S1
[2024-01-15 10:01:05.456] [INFO] wifiBridgePid:SCAN_BRIDGE, wifiBridgeName:WiFi Handle
[2024-01-15 10:01:06.000] [INFO] Device connected successfully
''',

    # Otter Lite WiFi
    'otter_wifi_connected': '''
[2024-01-15 10:01:05.123] [INFO] OnDeviceConnect: scannerPid:SCANNER_OTTER_LITE_BASIC, scannerName:Otter Lite
[2024-01-15 10:01:05.456] [INFO] wifiBridgePid:SCAN_BRIDGE, wifiBridgeName:WiFi Handle
[2024-01-15 10:01:06.000] [INFO] Device connected successfully
''',

    # USB连接（无wifiBridgePid）
    'usb_connected': '''
[2024-01-15 10:01:05.123] [INFO] OnDeviceConnect: scannerPid:SCANNER_SERMOON_X1, scannerName:Sermoon X1
[2024-01-15 10:01:06.000] [INFO] Device connected via USB
''',

    # 设备断开
    'disconnected': '''
[2024-01-15 10:02:26.123] [INFO] OnDeviceDisconnect: scannerPid:UNKNOWN, scannerName:Unknown
''',

    # 完整升级场景：初始连接 -> 断开（X1模组） -> 重连
    'x1wifi_upgrade_flow': '''
[2024-01-15 10:01:05.123] [INFO] OnDeviceConnect: scannerPid:SCANNER_SERMOON_X1, scannerName:Sermoon X1
[2024-01-15 10:01:05.456] [INFO] wifiBridgePid:SCAN_BRIDGE, wifiBridgeName:WiFi Handle
[2024-01-15 10:02:26.123] [INFO] OnDeviceDisconnect: scannerPid:UNKNOWN, scannerName:Wifi Handle
[2024-01-15 10:02:26.456] [INFO] wifiBridgePid:SCAN_BRIDGE, wifiBridgeName:WiFi Handle
[2024-01-15 10:02:57.123] [INFO] OnDeviceConnect: scannerPid:SCANNER_SERMOON_X1, scannerName:Sermoon X1
[2024-01-15 10:02:57.456] [INFO] wifiBridgePid:SCAN_BRIDGE, wifiBridgeName:WiFi Handle
''',

    # 空日志
    'empty': '',
}


class MockLogManager(LogManager):
    """Mock LogManager，用于测试"""

    def __init__(self, log_content: str = ''):
        """初始化Mock LogManager

        Args:
            log_content: 模拟的日志内容
        """
        # 不调用父类初始化，避免文件系统操作
        self._mock_content = log_content
        self.app_log_path = None

    def read_app_log(self, encoding: str = 'utf-8') -> str:
        """返回模拟的日志内容"""
        return self._mock_content


def test_x1wifi_detection():
    """测试X1 WiFi设备检测"""
    print("\n" + "=" * 60)
    print("测试1: X1 WiFi设备检测")
    print("=" * 60)

    test_cases = [
        ('x1wifi_connected', True, 'X1 WiFi已连接'),
        ('x1wifi_x1_disconnected', False, 'X1模组断开（WiFi手柄在线）'),
        ('x1wifi_reconnected', True, 'X1 WiFi重连后'),
        ('x1wifi_upgrade_flow', True, '完整升级流程（断开+重连）'),
        ('s1wifi_connected', False, 'S1 WiFi（应为False）'),
        ('usb_connected', False, 'USB连接（无WiFi）'),
        ('disconnected', False, '设备断开'),
        ('empty', False, '空日志'),
    ]

    passed = 0
    failed = 0

    for log_key, expected, description in test_cases:
        mock_manager = MockLogManager(SAMPLE_LOGS[log_key])
        result = mock_manager.is_x1wifi_connected()

        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
            print(f"  {status} {description}: {result} (预期: {expected})")
        else:
            failed += 1
            print(f"  {status} {description}: {result} (预期: {expected}) - 失败!")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_wifi_device_connected():
    """测试通用WiFi设备检测方法"""
    print("\n" + "=" * 60)
    print("测试2: 通用WiFi设备检测")
    print("=" * 60)

    # 测试各种设备模式的WiFi检测
    test_patterns = [
        ('x1wifi_connected', 'SERMOON_X1', True),
        ('x1wifi_connected', 'SERMOON_S1', False),
        ('s1wifi_connected', 'SERMOON_X1', False),
        ('s1wifi_connected', 'SERMOON_S1', True),
        ('otter_wifi_connected', 'OTTER', True),
        ('usb_connected', 'SERMOON_X1', False),
    ]

    passed = 0
    failed = 0

    for log_key, pattern, expected in test_patterns:
        mock_manager = MockLogManager(SAMPLE_LOGS[log_key])
        result = mock_manager.is_wifi_device_connected(pattern)

        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
            print(f"  {status} {log_key} + {pattern}: {result} (预期: {expected})")
        else:
            failed += 1
            print(f"  {status} {log_key} + {pattern}: {result} (预期: {expected}) - 失败!")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_device_connection_info():
    """测试设备连接信息解析"""
    print("\n" + "=" * 60)
    print("测试3: 设备连接信息解析")
    print("=" * 60)

    test_cases = [
        ('x1wifi_connected', {
            'scanner_pid': 'SCANNER_SERMOON_X1',
            'wifi_bridge_pid': 'SCAN_BRIDGE',
            'is_wifi_mode': True,
            'device_type': 'SERMOON_X1'
        }),
        ('x1wifi_upgrade_flow', {
            'scanner_pid': 'SCANNER_SERMOON_X1',  # 应该取最后一个（重连后）
            'wifi_bridge_pid': 'SCAN_BRIDGE',
            'is_wifi_mode': True,
            'device_type': 'SERMOON_X1'
        }),
        ('x1wifi_x1_disconnected', {
            'scanner_pid': 'UNKNOWN',  # 只有断开记录
            'wifi_bridge_pid': 'SCAN_BRIDGE',
            'is_wifi_mode': True,
            'device_type': None
        }),
        ('s1wifi_connected', {
            'scanner_pid': 'SCANNER_SERMOON_S1',
            'wifi_bridge_pid': 'SCAN_BRIDGE',
            'is_wifi_mode': True,
            'device_type': 'SERMOON_S1'
        }),
        ('usb_connected', {
            'scanner_pid': 'SCANNER_SERMOON_X1',
            'wifi_bridge_pid': None,
            'is_wifi_mode': False,
            'device_type': 'SERMOON_X1'
        }),
        ('empty', {
            'scanner_pid': None,
            'wifi_bridge_pid': None,
            'is_wifi_mode': False,
            'device_type': None
        }),
    ]

    passed = 0
    failed = 0

    for log_key, expected in test_cases:
        mock_manager = MockLogManager(SAMPLE_LOGS[log_key])
        result = mock_manager.get_device_connection_info()

        # 比较所有字段
        match = all(
            result.get(k) == v
            for k, v in expected.items()
        )

        status = "✓" if match else "✗"
        if match:
            passed += 1
            print(f"  {status} {log_key}: 解析正确")
            print(f"      {result}")
        else:
            failed += 1
            print(f"  {status} {log_key}: 解析错误")
            print(f"      预期: {expected}")
            print(f"      实际: {result}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_real_log_manager():
    """测试真实的LogManager（如果有日志文件）"""
    print("\n" + "=" * 60)
    print("测试4: 真实LogManager测试")
    print("=" * 60)

    try:
        log_dir = r"C:\Users\zengx\AppData\Local\Creality\CrealityScan\Logs"
        log_manager = LogManager(log_dir)

        if not log_manager.refresh_latest_log_dir():
            print("  ⚠ 未找到日志目录，跳过此测试")
            return True

        # 获取设备连接信息
        info = log_manager.get_device_connection_info()
        print(f"  设备连接信息:")
        print(f"    - scanner_pid: {info['scanner_pid']}")
        print(f"    - wifi_bridge_pid: {info['wifi_bridge_pid']}")
        print(f"    - is_wifi_mode: {info['is_wifi_mode']}")
        print(f"    - device_type: {info['device_type']}")

        # 测试X1 WiFi检测
        x1_result = log_manager.is_x1wifi_connected()
        print(f"    - X1 WiFi已连接: {x1_result}")

        return True

    except Exception as e:
        print(f"  ⚠ 测试跳过: {e}")
        return True


def main():
    """运行所有测试"""
    print("=" * 60)
    print("WiFi模组检测功能测试")
    print("=" * 60)

    results = []

    # 运行各测试
    results.append(("X1 WiFi检测", test_x1wifi_detection()))
    results.append(("通用WiFi设备检测", test_wifi_device_connected()))
    results.append(("设备连接信息解析", test_device_connection_info()))
    results.append(("真实LogManager", test_real_log_manager()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过!")
    else:
        print("存在失败的测试!")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)