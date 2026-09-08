"""
项目环境检查脚本
检查依赖、配置和UI截图是否准备就绪
"""

import sys
from pathlib import Path


def check_dependencies():
    """检查Python依赖包"""
    print("检查依赖包...")
    required_packages = [
        'airtest',
        'pywinauto',
        'PIL',
        'yaml',
        'colorlog'
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package} - 未安装")
            missing.append(package)

    if missing:
        print(f"\n缺少依赖包: {', '.join(missing)}")
        print("请运行: pip install -r requirements.txt")
        return False
    return True


def check_config_files():
    """检查配置文件"""
    print("\n检查配置文件...")
    config_files = [
        'config/app_config.yaml',
        'config/device_config.yaml',
        'config/test_config.yaml'
    ]

    all_exist = True
    for config_file in config_files:
        if Path(config_file).exists():
            print(f"  ✓ {config_file}")
        else:
            print(f"  ✗ {config_file} - 不存在")
            all_exist = False

    return all_exist


def check_ui_images():
    """检查UI元素截图"""
    print("\n检查UI元素截图...")
    required_images = [
        'resources/images/home/new_project.png',
        'resources/images/home/confirm.png',
        'resources/images/home/settings.png',
        'resources/images/scan/preview.png',
        'resources/images/scan/scan.png',
        'resources/images/settings/device_management.png',
        'resources/images/settings/select_file.png',
        'resources/images/settings/confirm.png',
        'resources/images/settings/upgrade_success.png',
    ]

    missing = []
    for image_path in required_images:
        if Path(image_path).exists():
            print(f"  ✓ {image_path}")
        else:
            print(f"  ✗ {image_path} - 不存在")
            missing.append(image_path)

    if missing:
        print(f"\n缺少 {len(missing)} 个UI截图")
        print("请参考 UI_SCREENSHOT_GUIDE.md 完成截图")
        return False
    return True


def check_directories():
    """检查必要的目录"""
    print("\n检查目录结构...")
    required_dirs = [
        'logs',
        'reports',
        'screenshots',
        'resources/firmware'
    ]

    for dir_path in required_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {dir_path}")

    return True


def main():
    """主函数"""
    print("=" * 60)
    print("CrealityScan 固件升级测试框架 - 环境检查")
    print("=" * 60)

    checks = [
        ("依赖包", check_dependencies),
        ("配置文件", check_config_files),
        ("目录结构", check_directories),
        ("UI截图", check_ui_images),
    ]

    results = []
    for name, check_func in checks:
        result = check_func()
        results.append((name, result))

    print("\n" + "=" * 60)
    print("检查结果汇总:")
    print("=" * 60)

    all_passed = True
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name}: {status}")
        if not result:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✓ 所有检查通过！可以开始测试。")
        print("\n运行测试:")
        print("  python run_test.py -f resources/firmware/your_firmware.bin")
        return 0
    else:
        print("\n✗ 部分检查未通过，请先完成准备工作。")
        print("\n参考文档:")
        print("  - README.md: 项目说明")
        print("  - UI_SCREENSHOT_GUIDE.md: UI截图指南")
        return 1


if __name__ == '__main__':
    sys.exit(main())
