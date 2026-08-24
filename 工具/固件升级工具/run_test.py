"""
测试入口文件
- 无参数：启动 GUI 窗口
- 有 -f 参数：命令行模式（兼容旧用法）
"""

import sys
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="CrealityScan固件升级自动化测试",
        add_help=True,
    )
    parser.add_argument("-f", "--firmware", type=str, help="固件文件路径（命令行模式）")
    args, _ = parser.parse_known_args()

    if args.firmware:
        # 命令行模式：保持原有行为
        from testcases.test_firmware_upgrade import TestFirmwareUpgrade
        firmware_path = Path(args.firmware)
        if not firmware_path.exists():
            print(f"错误: 固件文件不存在: {firmware_path}")
            sys.exit(1)
        test = TestFirmwareUpgrade()
        success = test.run(str(firmware_path))
        sys.exit(0 if success else 1)
    else:
        # GUI 模式
        from gui.main_window import MainWindow
        MainWindow().run()


if __name__ == "__main__":
    main()

