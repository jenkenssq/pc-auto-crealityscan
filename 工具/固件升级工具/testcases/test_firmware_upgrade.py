"""
固件升级测试用例
测试流程：第一次开流 -> 固件升级 -> 第二次开流
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from utils import Logger, ScreenshotHelper
from utils.test_reporter import TestReporter
from core.app_manager import AppManager
from core.stream_handler import StreamHandler
from core.firmware_handler import FirmwareHandler


class TestFirmwareUpgrade:
    """固件升级测试类"""

    def __init__(self):
        """初始化测试"""
        # 加载配置
        self.app_config = self._load_config('app_config.yaml')
        self.device_config = self._load_config('device_config.yaml')
        self.test_config = self._load_config('test_config.yaml')

        # 初始化工具
        log_level = self.test_config['test']['logging']['level']
        self.logger = Logger(level=getattr(__import__('logging'), log_level))
        self.screenshot = ScreenshotHelper()

        # 初始化管理器
        self.app_manager = AppManager(self.app_config, self.logger)
        self.stream_handler = StreamHandler(self.app_config, self.logger, self.screenshot)
        self.firmware_handler = FirmwareHandler(
            self.app_config, self.device_config, self.logger, self.screenshot
        )

        # 初始化测试报告生成器
        self.reporter = TestReporter()

        # 确认日志目录配置
        log_dir = self.app_config.get('app', {}).get('log_dir', '')
        if log_dir:
            self.logger.info(f"已配置日志目录: {log_dir}")
        else:
            self.logger.warning("未配置 log_dir，帧率统计和版本验证功能将不可用")

        # 测试结果
        self.test_result = {
            'first_stream': False,
            'firmware_upgrade': False,
            'second_stream': False,
            'overall': False
        }

        # 测试数据收集
        self.test_metrics = {
            'start_time': None,
            'end_time': None,
            'before_upgrade': {},
            'after_upgrade': {},
            'frame_data': {},
            'screenshots': {}
        }

    def _load_config(self, config_name):
        """加载配置文件，优先从外部目录读取，打包后可直接修改无需重打包"""
        from utils import get_base_dir

        base_dir = get_base_dir()
        config_path = Path(config_name)

        # 外部配置文件路径（exe同级目录）
        external_config = base_dir / config_name
        # 打包内部配置文件路径
        if getattr(sys, 'frozen', False):
            internal_config = Path(sys._MEIPASS) / config_name
        else:
            internal_config = base_dir / config_name

        # 优先使用外部配置
        if external_config.exists():
            with open(external_config, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)

        # 其次使用内部打包配置
        if internal_config.exists():
            with open(internal_config, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)

        raise FileNotFoundError(f"配置文件未找到: {external_config} 或 {internal_config}")

    def setup(self):
        """测试前置准备"""
        self.logger.info("=" * 60)
        self.logger.info("开始固件升级测试")
        self.logger.info("=" * 60)

        # 记录测试开始时间
        self.test_metrics['start_time'] = datetime.now()

        # 连接Windows设备
        if not self.app_manager.connect_windows():
            self.logger.error("Windows设备连接失败，测试终止")
            return False

        # 启动应用
        if not self.app_manager.launch_app():
            self.logger.error("应用启动失败，测试终止")
            return False

        # 收集升级前数据
        self._collect_before_upgrade_data()

        return True

    def teardown(self):
        """测试后置清理"""
        self.logger.info("=" * 60)
        self.logger.info("测试结束，生成测试报告")
        self.logger.info("=" * 60)

        # 记录测试结束时间
        self.test_metrics['end_time'] = datetime.now()

        # 收集升级后数据
        self._collect_after_upgrade_data()

        # 生成详细报告
        self._generate_detailed_report()

        self._print_test_result()

    def _collect_before_upgrade_data(self):
        """收集升级前的测试数据"""
        try:
            # 获取当前固件版本
            if self.firmware_handler.log_manager:
                current_version = self.firmware_handler.log_manager.get_device_firmware_version()
                self.test_metrics['before_upgrade']['firmware_version'] = current_version or "Unknown"
            else:
                self.test_metrics['before_upgrade']['firmware_version'] = "Not Available"

            # 记录设备连接状态
            if self.firmware_handler.log_manager:
                is_connected = self.firmware_handler.log_manager.is_device_connected()
                self.test_metrics['before_upgrade']['device_connected'] = is_connected
            else:
                self.test_metrics['before_upgrade']['device_connected'] = True

            self.logger.info(f"升级前固件版本: {self.test_metrics['before_upgrade']['firmware_version']}")

        except Exception as e:
            self.logger.error(f"收集升级前数据失败: {e}")

    def _collect_after_upgrade_data(self):
        """收集升级后的测试数据"""
        try:
            # 获取升级后固件版本
            if self.firmware_handler.log_manager:
                new_version = self.firmware_handler.log_manager.get_device_firmware_version()
                self.test_metrics['after_upgrade']['firmware_version'] = new_version or "Unknown"
            else:
                self.test_metrics['after_upgrade']['firmware_version'] = "Not Available"

            # 记录设备连接状态
            if self.firmware_handler.log_manager:
                is_connected = self.firmware_handler.log_manager.is_device_connected()
                self.test_metrics['after_upgrade']['device_connected'] = is_connected
            else:
                self.test_metrics['after_upgrade']['device_connected'] = True

            self.logger.info(f"升级后固件版本: {self.test_metrics['after_upgrade']['firmware_version']}")

        except Exception as e:
            self.logger.error(f"收集升级后数据失败: {e}")

    def _generate_detailed_report(self):
        """生成详细测试报告"""
        try:
            # 设置测试基本信息
            self.reporter.set_test_info(
                firmware_path=str(self.test_metrics.get('firmware_path', 'Unknown')),
                test_start_time=self.test_metrics['start_time'],
                test_end_time=self.test_metrics['end_time']
            )

            # 设置执行摘要
            self.reporter.set_execution_summary(
                overall_result=self.test_result['overall'],
                steps_results=self.test_result
            )

            # 添加固件版本对比
            self.reporter.add_comparison_data(
                comparison_type="固件版本",
                before_data=self.test_metrics['before_upgrade'],
                after_data=self.test_metrics['after_upgrade'],
                analysis=self._analyze_version_comparison()
            )

            # 添加帧数性能数据
            if self.test_metrics['frame_data']:
                self.reporter.add_metrics("帧数性能", self.test_metrics['frame_data'])

            # 添加改进建议
            self._add_recommendations()

            # 添加测试截图
            screenshots = self.test_metrics.get('screenshots', {})
            if 'first_stream' in screenshots:
                self.reporter.add_screenshot(
                    screenshots['first_stream'], "第一次开流成功截图", "第一次开流"
                )
            if 'firmware_upgrade' in screenshots:
                self.reporter.add_screenshot(
                    screenshots['firmware_upgrade'], "固件升级成功截图", "固件升级"
                )
            if 'second_stream' in screenshots:
                self.reporter.add_screenshot(
                    screenshots['second_stream'], "第二次开流成功截图", "第二次开流"
                )

            # 生成性能图表
            self.reporter.generate_performance_charts()

            # 构造报告名称：设备名_升级前版本-升级后版本
            report_name = self._build_report_name()

            # 生成HTML报告
            html_report_path = self.reporter.generate_html_report(report_name=report_name)
            self.logger.info(f"详细测试报告已生成: {html_report_path}")

            # 生成JSON数据报告
            json_report_path = self.reporter.generate_json_report(report_name=report_name)
            self.logger.info(f"测试数据报告已生成: {json_report_path}")

        except Exception as e:
            self.logger.error(f"生成测试报告失败: {e}")

    def _analyze_version_comparison(self) -> str:
        """分析版本对比结果"""
        before_version = self.test_metrics['before_upgrade'].get('firmware_version')
        after_version = self.test_metrics['after_upgrade'].get('firmware_version')

        if before_version == "Unknown" or after_version == "Unknown":
            return "无法获取完整的版本信息，建议检查日志配置"

        if before_version == after_version:
            return f"警告：升级前后版本号相同 ({before_version})，可能升级未成功"
        else:
            return f"固件版本成功从 {before_version} 升级到 {after_version}"

    def _build_report_name(self) -> str:
        """构造报告文件名：设备名_升级前版本-升级后版本"""
        import re
        firmware_path = str(self.test_metrics.get('firmware_path', ''))
        before_version = self.test_metrics['before_upgrade'].get('firmware_version', 'Unknown')
        after_version = self.test_metrics['after_upgrade'].get('firmware_version', 'Unknown')

        # 从固件文件名提取设备名，去掉 Creality_ 前缀、版本号及后缀
        filename = Path(firmware_path).stem  # 去掉 .zip
        # 移除 Creality_ 前缀
        filename = re.sub(r'^Creality_', '', filename)
        # 移除版本号及其后内容（如 _app1_1.0.2 或 _1.0.2）
        filename = re.sub(r'_(?:app\d+_)?\d+\.\d+\.\d+.*$', '', filename)
        # 去掉下划线拼接成驼峰风格
        device_name = ''.join(word.capitalize() for word in filename.split('_'))

        return f"{device_name}_{before_version}-{after_version}_测试报告_{self.test_metrics['start_time'].strftime('%Y%m%d%H%M')}"

    def _add_recommendations(self):
        """添加改进建议"""
        # 根据测试结果添加建议
        if not self.test_result['first_stream']:
            self.reporter.add_recommendation(
                category="开流功能",
                message="第一次开流失败，建议检查设备连接和驱动状态",
                priority="HIGH"
            )

        if not self.test_result['firmware_upgrade']:
            self.reporter.add_recommendation(
                category="固件升级",
                message="固件升级失败，建议检查固件文件完整性和设备兼容性",
                priority="HIGH"
            )

        if not self.test_result['second_stream']:
            self.reporter.add_recommendation(
                category="开流功能",
                message="第二次开流失败，建议验证升级后的设备功能",
                priority="HIGH"
            )

        # 版本升级建议
        before_version = self.test_metrics['before_upgrade'].get('firmware_version')
        after_version = self.test_metrics['after_upgrade'].get('firmware_version')
        if before_version == after_version and before_version != "Unknown":
            self.reporter.add_recommendation(
                category="版本验证",
                message=f"升级前后版本号未变化 ({before_version})，建议重新执行升级操作",
                priority="MEDIUM"
            )

    def run(self, firmware_path):
        """
        执行完整测试流程

        Args:
            firmware_path: 固件文件路径
        """
        # 记录固件路径
        self.test_metrics['firmware_path'] = firmware_path

        # 前置准备
        if not self.setup():
            return False

        try:
            # 步骤1: 第一次开流
            self.logger.info("\n" + "=" * 60)
            self.logger.info("步骤1: 执行第一次开流操作")
            self.logger.info("=" * 60)
            first_stream_result, first_stream_screenshot, first_frame_data = self.stream_handler.start_stream(phase="第一次")
            self.test_result['first_stream'] = first_stream_result
            if first_stream_screenshot:
                self.test_metrics['screenshots']['first_stream'] = first_stream_screenshot
            if first_frame_data:
                self.test_metrics['frame_data']['第一次'] = first_frame_data

            if not self.test_result['first_stream']:
                self.logger.error("第一次开流失败，测试终止")
                return False

            # 步骤2: 固件升级
            self.logger.info("\n" + "=" * 60)
            self.logger.info("步骤2: 执行固件升级")
            self.logger.info("=" * 60)
            firmware_result, firmware_screenshot = self.firmware_handler.upgrade_firmware(firmware_path)
            self.test_result['firmware_upgrade'] = firmware_result
            if firmware_screenshot:
                self.test_metrics['screenshots']['firmware_upgrade'] = firmware_screenshot

            if not self.test_result['firmware_upgrade']:
                self.logger.error("固件升级失败，测试终止")
                return False

            # 步骤3: 第二次开流
            self.logger.info("\n" + "=" * 60)
            self.logger.info("步骤3: 执行第二次开流操作")
            self.logger.info("=" * 60)
            second_stream_result, second_stream_screenshot, second_frame_data = self.stream_handler.start_stream(phase="第二次")
            self.test_result['second_stream'] = second_stream_result
            if second_stream_screenshot:
                self.test_metrics['screenshots']['second_stream'] = second_stream_screenshot
            if second_frame_data:
                self.test_metrics['frame_data']['第二次'] = second_frame_data

            if not self.test_result['second_stream']:
                self.logger.error("第二次开流失败")
                return False

            # 所有步骤成功
            self.test_result['overall'] = True
            self.logger.result("固件升级测试全部通过！", success=True)
            return True

        except Exception as e:
            self.logger.error(f"测试执行异常: {e}")
            return False

        finally:
            self.teardown()

    def _print_test_result(self):
        """打印测试结果摘要"""
        self.logger.info("\n测试结果摘要:")
        self.logger.info("-" * 60)
        self.logger.result(f"第一次开流: {'通过' if self.test_result['first_stream'] else '失败'}",
                          self.test_result['first_stream'])
        self.logger.result(f"固件升级: {'通过' if self.test_result['firmware_upgrade'] else '失败'}",
                          self.test_result['firmware_upgrade'])
        self.logger.result(f"第二次开流: {'通过' if self.test_result['second_stream'] else '失败'}",
                          self.test_result['second_stream'])
        self.logger.info("-" * 60)
        self.logger.result(f"总体结果: {'通过' if self.test_result['overall'] else '失败'}",
                          self.test_result['overall'])
