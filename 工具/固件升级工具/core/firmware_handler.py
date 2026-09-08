"""
固件升级操作处理模块
封装固件升级相关的UI操作和验证逻辑
"""

import time
import re
import sys
from typing import Optional
from airtest.core.api import touch, wait, exists, sleep, text, keyevent
from airtest.core.cv import Template
from pathlib import Path
if sys.platform == "win32":
    import pywinauto
    from pywinauto.application import Application
from utils.log_manager import LogManager
from utils import get_resource_path


class FirmwareHandler:
    """固件升级处理器"""

    def __init__(self, app_config, device_config, logger, screenshot_helper, log_dir: Optional[str] = None, connection_mode: Optional[str] = None):
        """
        初始化固件升级处理器

        Args:
            app_config: 应用配置
            device_config: 设备配置
            logger: 日志记录器
            screenshot_helper: 截图助手
            log_dir: CrealityScan 日志目录（可选，优先于配置文件）
            connection_mode: 强制指定连接模式，"usb" 禁用WiFi自动检测，"wifi" 强制WiFi方案，None 自动检测
        """
        self.app_config = app_config
        self.device_config = device_config
        self.logger = logger
        self.screenshot = screenshot_helper
        self.threshold = app_config['image_recognition']['threshold']
        self.timeout = app_config['image_recognition']['timeout']
        self.click_delay = app_config['image_recognition']['click_delay']
        self.upgrade_timeout = app_config['timeouts']['firmware_upgrade']
        self.connection_mode = connection_mode  # "usb" / "wifi" / None

        # 初始化日志管理器（优先使用外部传入的 log_dir）
        if log_dir:
            self.log_manager = LogManager(log_dir)
            self.logger.info(f"使用GUI传入的日志目录: {log_dir}")
        else:
            log_dir = app_config.get('app', {}).get('log_dir')
            if log_dir:
                self.log_manager = LogManager(log_dir)
                self.logger.info(f"使用配置文件中的日志目录: {log_dir}")
            else:
                self.logger.warning("未配置日志目录")
        if self.log_manager:
            self.log_manager.refresh_latest_log_dir()

        # UI元素图片路径
        self.images = {
            'settings_btn': get_resource_path('resources/images/home/settings.png'),
            'device_mgmt_btn': get_resource_path('resources/images/settings/device_management.png'),
            'select_file_btn': get_resource_path('resources/images/settings/select_file.png'),
            'file_dialog_open_btn': get_resource_path('resources/images/settings/file_dialog_open_btn.png'),
            'upgrade_confirm_btn': get_resource_path('resources/images/settings/upgrade_confirm_btn.png'),
            'upgrade_success': get_resource_path('resources/images/settings/upgrade_success.png'),
            'close_settings_btn': get_resource_path('resources/images/settings/close_settings.png'),
        }

    def upgrade_firmware(self, firmware_path):
        """
        执行完整的固件升级流程

        Args:
            firmware_path: 固件文件路径

        Returns:
            bool: 升级是否成功
        """
        self.logger.step("开始固件升级操作")

        # 重置内部状态（避免循环升级时状态污染）
        self._upgrade_success_time = None

        try:
            # 验证固件文件存在
            if not Path(firmware_path).exists():
                self.logger.error(f"固件文件不存在: {firmware_path}")
                return False, None

            # 步骤1: 点击设置按钮
            if not self._click_settings():
                return False, None

            # 步骤2: 点击设备管理
            if not self._click_device_management():
                return False, None

            # 步骤3: 选择固件文件
            if not self._select_firmware_file(firmware_path):
                return False, None

            # 步骤4: 确认升级
            if not self._confirm_upgrade():
                return False, None

            # 记录点击升级确认按钮的时间，用于后续日志版本验证
            upgrade_confirm_time = time.strftime('%Y-%m-%d %H:%M:%S')
            self.logger.info(f"已记录升级确认时间: {upgrade_confirm_time}")

            # 步骤5: 检测设备型号，判断使用哪种等待方式
            device_model = self._get_device_model()
            self.logger.info(f"当前设备型号: {device_model}")

            # 根据连接模式决定检测策略
            is_sermoon = self._is_sermoon_device(device_model)
            is_pika = self._is_pika_device(device_model)
            if self.connection_mode == "usb":
                # USB模式：强制禁用所有WiFi检测，走普通升级方案
                is_x1wifi = False
                is_s1wifi = False
                is_raptorwifi = False
                is_otterwifi = False
                is_ferretwifi = False
                is_pikawifi = False
                self.logger.info("[USB模式] 已强制禁用WiFi自动检测")
            elif self.connection_mode == "wifi":
                # WiFi模式：强制启用所有WiFi检测（由具体的WiFi方法判断）
                is_x1wifi = self._is_x1wifi_device(device_model)
                is_s1wifi = self._is_s1wifi_device(device_model)
                is_raptorwifi = self._is_raptorwifi_device(device_model)
                is_otterwifi = self._is_otterwifi_device(device_model)
                is_ferretwifi = self._is_ferretwifi_device(device_model)
                is_pikawifi = self._is_pikawifi_device(device_model)
                self.logger.info("[WiFi模式] 强制启用WiFi自动检测")
            else:
                # 自动检测模式（默认）
                is_x1wifi = self._is_x1wifi_device(device_model)
                is_s1wifi = self._is_s1wifi_device(device_model)
                is_raptorwifi = self._is_raptorwifi_device(device_model)
                is_otterwifi = self._is_otterwifi_device(device_model)
                is_ferretwifi = self._is_ferretwifi_device(device_model)
                is_pikawifi = self._is_pikawifi_device(device_model)

            if is_raptorwifi:
                # Raptor系列WiFi设备使用专用重连检测
                self.logger.info("检测到 Raptor 系列WiFi设备，使用专用重连检测模式")
                if not self._wait_for_upgrade_by_ui_and_log(firmware_path, device_model, upgrade_confirm_time, is_raptorwifi=is_raptorwifi):
                    return False, None
            elif is_ferretwifi:
                # Ferret系列WiFi设备使用专用重连检测
                self.logger.info("检测到 Ferret 系列WiFi设备，使用专用重连检测模式")
                if not self._wait_for_upgrade_by_ui_and_log(firmware_path, device_model, upgrade_confirm_time, is_ferretwifi=is_ferretwifi):
                    return False, None
            elif is_otterwifi:
                # Otter系列WiFi设备使用专用重连检测
                self.logger.info("检测到 Otter 系列WiFi设备，使用专用重连检测模式")
                if not self._wait_for_upgrade_by_ui_and_log(firmware_path, device_model, upgrade_confirm_time, is_otterwifi=is_otterwifi):
                    return False, None
            elif is_pikawifi:
                # Pika系列WiFi设备使用专用重连检测
                self.logger.info("检测到 Pika 系列WiFi设备，使用专用重连检测模式")
                if not self._wait_for_upgrade_by_ui_and_log(firmware_path, device_model, upgrade_confirm_time, is_pikawifi=is_pikawifi):
                    return False, None
            elif is_sermoon:
                # Sermoon 系列使用UI检测优先+日志验证模式
                self.logger.info("检测到 Sermoon 系列设备，使用UI检测+日志验证模式")
                if not self._wait_for_upgrade_by_ui_and_log(firmware_path, device_model, upgrade_confirm_time, is_x1wifi=is_x1wifi, is_s1wifi=is_s1wifi):
                    return False, None
            elif is_pika:
                # Creality Pika 使用USB升级方案（与Sermoon类似的UI+日志验证）
                self.logger.info("检测到 Creality Pika 设备，使用Pika升级方案")
                if not self._wait_for_pika_upgrade(firmware_path, device_model, upgrade_confirm_time):
                    return False, None
            else:
                # 其他设备：图像检测 + 等待设备重新上线
                self.logger.info("非Sermoon/Raptor/Otter/Pika设备，使用图像检测+重连验证模式")
                if not self._wait_for_upgrade_with_reconnect():
                    return False, None

            # 步骤6: 验证固件版本号
            # Sermoon 和 Pika 都使用升级时间点验证，只读取升级后的日志
            if not self._verify_firmware_version(firmware_path, is_sermoon or is_pika):
                return False, None

            # 步骤7: 截图（关闭设置页前，保留升级成功状态）
            self.logger.result("固件升级成功", success=True)
            screenshot_path = self.screenshot.take_step_screenshot("firmware_upgrade_success")

            # 步骤8: 关闭设置页，返回首页
            if not self._close_settings():
                return False

            return True, screenshot_path

        except Exception as e:
            self.logger.error(f"固件升级失败: {e}")
            self.screenshot.take_step_screenshot("firmware_upgrade_failed")
            return False, None

    def _click_settings(self):
        """点击设置按钮"""
        self.logger.info("点击'设置'按钮")
        return self._click_element('settings_btn', "设置按钮")

    def _click_device_management(self):
        """点击设备管理按钮"""
        self.logger.info("点击'设备管理'按钮")
        return self._click_element('device_mgmt_btn', "设备管理按钮")

    def _select_firmware_file(self, firmware_path):
        """
        选择固件文件
        处理Windows文件选择对话框

        Args:
            firmware_path: 固件文件路径

        Returns:
            bool: 选择是否成功
        """
        self.logger.info("选择固件文件")

        try:
            # 点击选择文件按钮
            if not self._click_element('select_file_btn', "选择文件按钮"):
                return False

            # 等待文件选择对话框出现
            sleep(3)

            # 获取绝对路径
            abs_path = str(Path(firmware_path).absolute())
            self.logger.info(f"文件路径: {abs_path}")

            # 输入文件路径
            self.logger.info("输入文件路径")
            text(abs_path)
            sleep(1)

            # 显式点击"打开"按钮（使用图像识别）
            self.logger.info("点击文件对话框的'打开'按钮")
            if self._click_element('file_dialog_open_btn', "文件对话框打开按钮"):
                self.logger.info("成功点击打开按钮")
                sleep(2)  # 等待对话框关闭
                return True
            else:
                # 如果图像识别失败，尝试使用Enter键作为备选方案
                self.logger.warning("图像识别失败，尝试使用Enter键")
                text("\n")
                sleep(2)
                self.logger.info("已发送Enter键")
                return True

        except Exception as e:
            self.logger.error(f"选择固件文件失败: {e}")
            return False

    def _confirm_upgrade(self):
        """
        确认开始升级
        处理"是否立即升级"的确认弹窗

        Returns:
            bool: 确认是否成功
        """
        self.logger.info("等待升级确认弹窗出现")

        # 等待升级确认弹窗出现（给一些时间让对话框完全加载）
        sleep(2)

        # 尝试多次点击升级确认按钮（因为对话框可能需要一些时间才能完全渲染）
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            self.logger.info(f"第{attempt}次尝试点击升级确认按钮")

            if self._click_element('upgrade_confirm_btn', "升级确认按钮"):
                self.logger.info("成功点击升级确认按钮")
                sleep(1)

                # 验证对话框是否已关闭（通过检查按钮是否还存在）
                upgrade_confirm_template = Template(
                    self.images['upgrade_confirm_btn'],
                    threshold=self.threshold
                )
                if not exists(upgrade_confirm_template):
                    self.logger.result("升级确认对话框已关闭", success=True)
                    return True
                else:
                    self.logger.warning("对话框仍然存在，可能点击未生效")

            # 如果不是最后一次尝试，等待一下再重试
            if attempt < max_attempts:
                sleep(1)

        # 如果多次尝试都失败，记录错误
        self.logger.error("多次尝试后仍无法点击升级确认按钮")
        return False

    def _wait_for_upgrade_complete(self):
        """
        等待固件升级完成
        使用 concurrent.futures 给每次 exists() 调用加超时保护，
        防止设备刷机重启期间截图接口阻塞导致线程死锁

        Returns:
            bool: 升级是否成功完成
        """
        import concurrent.futures

        self.logger.info(f"等待固件升级完成（最长{self.upgrade_timeout}秒）...")

        start_time = time.time()
        upgrade_success_template = Template(self.images['upgrade_success'], threshold=self.threshold)

        while time.time() - start_time < self.upgrade_timeout:
            try:
                # 每次 exists() 最多等 8 秒，超时则跳过本轮继续轮询
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(exists, upgrade_success_template)
                    result = future.result(timeout=8)

                if result:
                    self.logger.result("检测到升级成功提示", success=True)
                    return True

            except concurrent.futures.TimeoutError:
                self.logger.info("截图超时（设备可能正在重启），继续等待...")
            except Exception as e:
                self.logger.info(f"截图异常（{e}），继续等待...")

            sleep(5)  # 每5秒检查一次

        self.logger.error("固件升级超时")
        return False

    def _wait_for_upgrade_with_reconnect(self):
        """
        等待固件升级完成并验证设备重新上线（非Sermoon设备使用）

        流程：
        1. 检测升级成功的气泡（UI）
        2. 等待设备重新上线（日志中检测OnDeviceConnect）
        3. 返回成功

        Returns:
            bool: 升级是否成功完成
        """
        import concurrent.futures

        self.logger.info(f"等待固件升级完成并验证重连（最长{self.upgrade_timeout}秒）...")

        start_time = time.time()
        last_check_time = start_time
        upgrade_success_template = Template(self.images['upgrade_success'], threshold=self.threshold)
        ui_detected = False  # UI气泡是否已检测到
        device_online = False  # 设备是否已重新上线

        while time.time() - start_time < self.upgrade_timeout:
            # 步骤1: 检测UI气泡
            if not ui_detected:
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(exists, upgrade_success_template)
                        result = future.result(timeout=5)
                    if result:
                        ui_detected = True
                        self.logger.info("检测到升级成功气泡（UI）")
                except concurrent.futures.TimeoutError:
                    pass
                except Exception as e:
                    self.logger.warning(f"UI检测异常: {e}")

            # 步骤2: 如果UI已检测到，等待设备重新上线
            if ui_detected and not device_online:
                self.log_manager.refresh_latest_log_dir()

                # 检查设备是否已重新上线
                if self.log_manager.is_device_connected():
                    device_online = True
                    self.logger.info("检测到设备重新上线（日志），等待UI同步...")

                    # 等待UI同步（日志显示上线后，UI需要额外时间显示）
                    sleep(5)
                    self.logger.info("UI同步等待完成")

                # 检查是否有升级失败的日志
                content = self.log_manager.read_app_log()
                if content:
                    fail_keywords = ['UpgradeFailed', 'Upgrade failed', 'upgrade failed']
                    for kw in fail_keywords:
                        if kw in content:
                            self.logger.error(f"日志检测到升级失败: {kw}")
                            return False

            # 步骤3: UI检测到 + 设备已上线，认为升级成功
            if ui_detected and device_online:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result("UI检测到升级成功 + 设备已重新上线", success=True)
                return True

            # 每 10 秒输出一次等待状态
            elapsed = time.time() - start_time
            if time.time() - last_check_time >= 10:
                remaining = self.upgrade_timeout - elapsed
                status = []
                if ui_detected:
                    status.append("UI OK")
                if device_online:
                    status.append("设备在线")
                status_str = ", ".join(status) if status else "等待中"
                self.logger.info(f"升级进行中 [{status_str}]，已等待 {int(elapsed)}s，剩余 {int(remaining)}s...")
                last_check_time = time.time()

            sleep(3)

        self.logger.error("固件升级超时或设备未重新上线")
        return False

    def _verify_device_reconnect(self):
        """
        验证设备重新连接
        通过监控日志文件判断设备掉线和上线

        Returns:
            bool: 设备是否成功重连
        """
        self.logger.info("等待设备重新连接...")

        if not self.log_manager:
            self.logger.warning("未配置日志管理器，使用简单等待方式")
            sleep(10)  # 给设备一些时间重启
            self.logger.info("等待完成，假设设备已重连")
            return True

        return self._monitor_device_reconnect_by_log()

    def _monitor_device_reconnect_by_log(self):
        """
        通过监控日志文件来判断设备掉线和上线

        Returns:
            bool: 设备是否成功重连
        """
        self.logger.info("开始监控日志文件...")

        # 根据LOG_ANALYSIS.md中的实际日志关键字
        offline_keywords = ["Device disconnected", "OnDeviceDisconnect", "isActiveDeviceDisconnect = True"]
        online_keywords = ["OnDeviceConnect", "Device connected"]

        device_offline = False
        device_online = False
        start_time = time.time()
        timeout = self.app_config['timeouts']['device_reconnect']

        try:
            while time.time() - start_time < timeout:
                # 刷新日志目录
                self.log_manager.refresh_latest_log_dir()

                # 检查设备连接状态
                is_connected = self.log_manager.is_device_connected()

                # 检测设备掉线
                if not device_offline and not is_connected:
                    self.logger.info("检测到设备掉线")
                    device_offline = True

                # 检测设备上线
                if device_offline and is_connected:
                    self.logger.result("检测到设备重新上线", success=True)
                    device_online = True
                    return True

                sleep(1)  # 每秒检查一次

            if not device_offline:
                self.logger.warning("未检测到设备掉线，可能升级过程中设备未断开连接")
                # 如果设备一直在线，也认为是成功的
                return True
            elif not device_online:
                self.logger.error("设备掉线后未能重新上线")
                return False

        except Exception as e:
            self.logger.error(f"监控日志文件失败: {e}")
            return False

    def _verify_firmware_version(self, firmware_path, is_sermoon: bool = False):
        """
        验证升级后的固件版本号是否与固件文件名中的版本一致
        轮询等待日志刷新，直到读到预期版本或超时

        Args:
            firmware_path: 固件文件路径
            is_sermoon: 是否为Sermoon/Pika系列设备（使用升级时间点验证）

        Returns:
            bool: 版本验证是否通过
        """
        self.logger.info("开始验证固件版本号")

        if not self.log_manager:
            self.logger.warning("未配置日志管理器，跳过版本验证")
            return True

        # 从固件文件名中提取预期版本号（兼容 V1.4.3 和 1.0.2 两种格式）
        filename = Path(firmware_path).name
        match = re.search(r'(\d+\.\d+\.\d+)', filename)
        if not match:
            self.logger.warning(f"无法从文件名提取版本号: {filename}，跳过验证")
            return True

        expected_version = match.group(1)
        self.logger.info(f"预期固件版本: {expected_version}")

        # Sermoon/Pika系列：升级成功后等待10秒，让日志稳定
        if is_sermoon:
            self.logger.info("Sermoon/Pika系列：等待日志稳定...")
            sleep(10)

        # 轮询等待日志中出现预期版本号（最多等待60秒，每3秒检查一次）
        start_time = time.time()
        actual_version = None

        # Sermoon/Pika系列：获取升级成功的时间点
        upgrade_time = None
        if is_sermoon:
            upgrade_time = getattr(self, '_upgrade_success_time', None)
            if upgrade_time:
                self.logger.info(f"使用升级成功时间点: {upgrade_time} 作为版本验证参考")

        while time.time() - start_time < 60:
            self.log_manager.refresh_latest_log_dir()

            # Sermoon/Pika系列：使用新方法，只读取升级后的版本信息
            if is_sermoon and upgrade_time:
                actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_time)
            else:
                actual_version = self.log_manager.get_device_firmware_version()

            self.logger.info(f"实际固件版本: {actual_version}")

            if actual_version == expected_version:
                self.logger.result(f"固件版本验证通过: {actual_version}", success=True)
                return True

            sleep(3)

        self.logger.error(f"固件版本验证超时！预期: {expected_version}，最后读到: {actual_version}")
        return False

    def _close_settings(self):
        """
        关闭设置页，返回首页

        Returns:
            bool: 关闭是否成功
        """
        self.logger.info("关闭设置页")

        try:
            # 点击关闭设置按钮（可能是X按钮或返回按钮）
            if not self._click_element('close_settings_btn', "关闭设置按钮"):
                # 如果没有专门的关闭按钮，可以尝试使用ESC键
                self.logger.info("尝试使用ESC键关闭设置页")
                keyevent("Escape")
                sleep(1)

            self.logger.result("设置页已关闭", success=True)
            return True

        except Exception as e:
            self.logger.error(f"关闭设置页失败: {e}")
            return False

    def _click_element(self, element_key, element_name):
        """
        点击UI元素（通用方法）

        Args:
            element_key: 元素在images字典中的键
            element_name: 元素名称（用于日志）

        Returns:
            bool: 点击是否成功
        """
        image_path = self.images.get(element_key)

        if not Path(image_path).exists():
            self.logger.error(f"{element_name}图片不存在: {image_path}")
            self.logger.warning("请先截取UI元素图片并保存到对应路径")
            return False

        try:
            # 创建Template对象，设置识别阈值
            template = Template(image_path, threshold=self.threshold)

            # 等待元素出现
            if wait(template, timeout=self.timeout):
                touch(template)
                sleep(self.click_delay)
                self.logger.info(f"成功点击{element_name}")
                return True
            else:
                self.logger.error(f"未找到{element_name}")
                return False
        except Exception as e:
            self.logger.error(f"点击{element_name}失败: {e}")
            return False

    def _get_device_model(self) -> Optional[str]:
        """
        获取当前连接的设备型号

        Returns:
            str: 设备型号 (如 "SCANNER_SERMOON_S1")，未找到返回 None
        """
        if not self.log_manager:
            self.logger.warning("未配置日志管理器，无法获取设备型号")
            return None

        try:
            self.log_manager.refresh_latest_log_dir()
            model = self.log_manager.get_device_model()
            return model
        except Exception as e:
            self.logger.warning(f"获取设备型号失败: {e}")
            return None

    def _is_sermoon_device(self, model: Optional[str]) -> bool:
        """
        判断是否为 Sermoon 系列设备

        Args:
            model: 设备型号

        Returns:
            bool: 是否为 Sermoon 系列
        """
        if not model:
            return False

        model_upper = model.upper()
        sermoon_patterns = ['SERMOON_S1', 'SERMOON_X1', 'SERMOON']
        return any(pattern in model_upper for pattern in sermoon_patterns)

    def _is_x1wifi_device(self, model: Optional[str]) -> bool:
        """
        判断是否为 Sermoon X1 WiFi 设备

        X1 WiFi特征：
        - scannerPid:SCANNER_SERMOON_X1
        - wifiBridgePid:SCAN_BRIDGE（WiFi手柄保持连接）

        Args:
            model: 设备型号

        Returns:
            bool: 是否为 X1 WiFi 设备
        """
        if not model or 'SERMOON_X1' not in model.upper():
            return False

        # 额外检查wifiBridgePid存在（WiFi模式下才有）
        if not self.log_manager:
            return False

        self.log_manager.refresh_latest_log_dir()
        return self.log_manager.is_x1wifi_connected()

    def _is_s1wifi_device(self, model: Optional[str]) -> bool:
        """
        判断是否为 Sermoon S1 WiFi 设备

        S1 WiFi特征：
        - scannerPid:SCANNER_SERMOON_S1
        - wifiBridgePid:SCAN_BRIDGE（WiFi手柄保持连接）

        Args:
            model: 设备型号

        Returns:
            bool: 是否为 S1 WiFi 设备
        """
        if not model or 'SERMOON_S1' not in model.upper():
            return False

        # 额外检查wifiBridgePid存在（WiFi模式下才有）
        if not self.log_manager:
            return False

        self.log_manager.refresh_latest_log_dir()
        return self.log_manager.is_s1wifi_connected()

    def _is_raptorwifi_device(self, model: Optional[str]) -> bool:
        """
        判断是否为 Raptor 系列 WiFi 设备（包括 Raptor, Raptor X, Raptor Pro）

        Raptor WiFi特征：
        - scannerPid:SCANNER_RAPTOR* (RAPTOR, RAPTORPRO, RAPTORX)
        - wifiBridgePid:SCAN_BRIDGE（WiFi手柄保持连接）

        Args:
            model: 设备型号

        Returns:
            bool: 是否为 Raptor WiFi 设备
        """
        if not model or 'RAPTOR' not in model.upper():
            return False

        # 额外检查wifiBridgePid存在（WiFi模式下才有）
        if not self.log_manager:
            return False

        self.log_manager.refresh_latest_log_dir()
        return self.log_manager.is_raptorwifi_connected()

    def _is_otterwifi_device(self, model: Optional[str]) -> bool:
        """
        判断是否为 Otter 系列 WiFi 设备

        Otter WiFi特征：
        - scannerPid:SCANNER_OTTER
        - wifiBridgePid:SCAN_BRIDGE（WiFi手柄保持连接）

        Args:
            model: 设备型号

        Returns:
            bool: 是否为 Otter WiFi 设备
        """
        if not model or 'OTTER' not in model.upper():
            return False

        # 额外检查wifiBridgePid存在（WiFi模式下才有）
        if not self.log_manager:
            return False

        self.log_manager.refresh_latest_log_dir()
        return self.log_manager.is_otterwifi_connected()

    def _is_ferretwifi_device(self, model: Optional[str]) -> bool:
        """
        判断是否为 Ferret 系列 WiFi 设备

        Ferret WiFi特征：
        - scannerPid:SCANNER_FERRET
        - wifiBridgePid:WIFI_BRIDGE（WiFi手柄保持连接）

        Args:
            model: 设备型号

        Returns:
            bool: 是否为 Ferret WiFi 设备
        """
        if not model or 'FERRET' not in model.upper():
            return False

        # 额外检查wifiBridge存在（WiFi模式下才有）
        if not self.log_manager:
            return False

        self.log_manager.refresh_latest_log_dir()
        return self.log_manager.is_ferretwifi_connected()

    def _is_pika_device(self, model: Optional[str]) -> bool:
        """
        判断是否为 Creality Pika 设备

        Pika 特征：
        - scannerPid:SCANNER_RAPTOR_PIKA

        Args:
            model: 设备型号

        Returns:
            bool: 是否为 Pika 设备
        """
        if not model:
            return False
        return 'RAPTOR_PIKA' in model.upper()

    def _is_pikawifi_device(self, model: Optional[str]) -> bool:
        """
        判断是否为 Creality Pika WiFi 设备

        Pika WiFi特征：
        - scannerPid:SCANNER_RAPTOR_PIKA
        - wifiBridgePid:SCAN_BRIDGE（WiFi手柄保持连接）

        Args:
            model: 设备型号

        Returns:
            bool: 是否为 Pika WiFi 设备
        """
        if not model or 'RAPTOR_PIKA' not in model.upper():
            return False

        if not self.log_manager:
            return False

        self.log_manager.refresh_latest_log_dir()
        return self.log_manager.is_pikawifi_connected()

    def _wait_for_upgrade_by_ui_and_log(self, firmware_path: str, device_model: str = None, upgrade_confirm_time: str = None, timeout: int = None, is_x1wifi: bool = False, is_s1wifi: bool = False, is_raptorwifi: bool = False, is_otterwifi: bool = False, is_ferretwifi: bool = False, is_pikawifi: bool = False):
        """
        通过UI检测+日志验证（适用于 Sermoon S1/X1 等长耗时设备）

        流程：
        - S1模组：0-70秒检测日志失败字段，70-85秒检测UI气泡，85秒后日志版本兜底
        - X1模组：0-90秒检测日志失败字段，90-105秒检测UI气泡，105秒后日志版本兜底
        - X1 WiFi：使用专用重连检测逻辑，等待scannerPid从UNKNOWN变回SCANNER_SERMOON_X1
        - S1 WiFi：使用专用重连检测逻辑，等待scannerPid从UNKNOWN变回SCANNER_SERMOON_S1
        - Raptor WiFi：使用专用重连检测逻辑，等待设备重连
        - Otter WiFi：使用专用重连检测逻辑，等待设备重连
        - Ferret WiFi：使用专用重连检测逻辑，等待设备重连
        - Pika WiFi：使用专用重连检测逻辑，等待设备重连
        - 其他Sermoon：保持原有逻辑

        Args:
            firmware_path: 固件文件路径（用于兜底方案获取预期版本）
            device_model: 设备型号
            upgrade_confirm_time: 点击升级确认按钮的时间（用于日志版本验证）
            timeout: 超时时间（秒），默认使用配置中的 sermon_upgrade 或 360秒
            is_x1wifi: 是否为X1 WiFi设备（使用专用重连检测）
            is_s1wifi: 是否为S1 WiFi设备（使用专用重连检测）
            is_raptorwifi: 是否为Raptor WiFi设备（使用专用重连检测）
            is_otterwifi: 是否为Otter WiFi设备（使用专用重连检测）
            is_ferretwifi: 是否为Ferret WiFi设备（使用专用重连检测）
            is_pikawifi: 是否为Pika WiFi设备（使用专用重连检测）

        Returns:
            bool: 升级是否成功完成
        """
        import concurrent.futures

        # Raptor WiFi 使用专用重连超时
        if is_raptorwifi:
            timeout = self.app_config['timeouts'].get('raptorwifi_reconnect', 30)
            # 获取设备友好名称
            device_name = device_model.replace('SCANNER_', '').replace('_', ' ') if device_model else 'Raptor'
            self.logger.info(f"{device_name} WiFi设备检测到，使用专用重连超时: {timeout}秒")
            return self._wait_for_raptorwifi_reconnect(firmware_path, upgrade_confirm_time, timeout, device_model)

        # Ferret WiFi 使用专用重连超时
        if is_ferretwifi:
            timeout = self.app_config['timeouts'].get('ferretwifi_reconnect', 30)
            # 获取设备友好名称
            device_name = device_model.replace('SCANNER_', '').replace('_', ' ') if device_model else 'Ferret'
            self.logger.info(f"{device_name} WiFi设备检测到，使用专用重连超时: {timeout}秒")
            return self._wait_for_ferretwifi_reconnect(firmware_path, upgrade_confirm_time, timeout, device_model)

        # Otter WiFi 使用专用重连超时
        if is_otterwifi:
            timeout = self.app_config['timeouts'].get('otterwifi_reconnect', 30)
            # 获取设备友好名称
            device_name = device_model.replace('SCANNER_', '').replace('_', ' ') if device_model else 'Otter'
            self.logger.info(f"{device_name} WiFi设备检测到，使用专用重连超时: {timeout}秒")
            return self._wait_for_otterwifi_reconnect(firmware_path, upgrade_confirm_time, timeout, device_model)

        # Pika WiFi 使用专用重连超时
        if is_pikawifi:
            timeout = self.app_config['timeouts'].get('pikawifi_reconnect', 30)
            device_name = device_model.replace('SCANNER_', '').replace('_', ' ') if device_model else 'Pika'
            self.logger.info(f"{device_name} WiFi设备检测到，使用专用重连超时: {timeout}秒")
            return self._wait_for_pikawifi_reconnect(firmware_path, upgrade_confirm_time, timeout, device_model)

        # X1 WiFi 使用专用重连超时
        if is_x1wifi:
            timeout = self.app_config['timeouts'].get('x1wifi_reconnect', 90)
            self.logger.info(f"X1 WiFi设备检测到，使用专用重连超时: {timeout}秒")
            return self._wait_for_x1wifi_reconnect(firmware_path, upgrade_confirm_time, timeout)

        # S1 WiFi 使用专用重连超时
        if is_s1wifi:
            timeout = self.app_config['timeouts'].get('s1wifi_reconnect', 60)
            self.logger.info(f"S1 WiFi设备检测到，使用专用重连超时: {timeout}秒")
            return self._wait_for_s1wifi_reconnect(firmware_path, upgrade_confirm_time, timeout)

        if timeout is None:
            timeout = self.app_config['timeouts'].get('sermoon_upgrade', 360)

        # 记录升级确认时间
        if upgrade_confirm_time:
            self.logger.info(f"使用升级确认时间: {upgrade_confirm_time} 作为日志版本验证起点")

        # 判断设备类型
        is_s1 = device_model and 'SERMOON_S1' in device_model.upper()
        is_x1 = device_model and 'SERMOON_X1' in device_model.upper()

        # 从配置读取各阶段时间阈值（提供默认值）
        upgrade_stages = self.app_config.get('upgrade_stages', {})
        s1_config = upgrade_stages.get('sermons1', {})
        x1_config = upgrade_stages.get('sermonx1', {})

        if is_s1:
            log_check_end = s1_config.get('log_check_end', 70)
            ui_check_end = s1_config.get('ui_check_end', 85)
            fallback_time = s1_config.get('fallback_time', 85)
            log_stable_wait = s1_config.get('log_stable_wait', 10)
        elif is_x1:
            log_check_end = x1_config.get('log_check_end', 90)
            ui_check_end = x1_config.get('ui_check_end', 105)
            fallback_time = x1_config.get('fallback_time', 105)
            log_stable_wait = x1_config.get('log_stable_wait', 10)
        else:
            # 其他Sermoon保持原有逻辑
            log_check_end = 0
            ui_check_end = 360
            fallback_time = 360
            log_stable_wait = 10

        self.logger.info(f"开始检测升级状态（UI优先+日志验证，超时: {timeout}秒）...")
        if is_s1:
            self.logger.info(f"S1模组：0-{log_check_end}秒日志检测，{log_check_end}-{ui_check_end}秒UI气泡，{fallback_time}秒后兜底")
        elif is_x1:
            self.logger.info(f"X1模组：0-{log_check_end}秒日志检测，{log_check_end}-{ui_check_end}秒UI气泡，{fallback_time}秒后兜底")

        # 记录开始时间
        start_time = time.time()
        last_check_time = start_time
        self._upgrade_success_time = None  # 用于版本验证
        ui_detected = False  # UI气泡是否已检测到
        fallback_triggered = False  # 是否已触发兜底方案

        # 重置日志位置，记录当前日志大小，后续只读取新增内容
        self.log_manager.refresh_latest_log_dir()
        self.log_manager.reset_log_position()
        self.logger.info("已记录日志位置，后续只检测新增日志内容")

        # 获取预期版本号（用于兜底方案）
        expected_version = None
        if is_s1 or is_x1:
            match = re.search(r'(\d+\.\d+\.\d+)', Path(firmware_path).name)
            if match:
                expected_version = match.group(1)
                self.logger.info(f"兜底方案预期版本: {expected_version}")

        # UI气泡检测模板
        upgrade_success_template = Template(self.images['upgrade_success'], threshold=self.threshold)

        # 升级失败关键字
        fail_keywords = ['UpgradeFailed', 'Upgrade failed', 'upgrade failed']

        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            self.log_manager.refresh_latest_log_dir()
            # 只读取新增的日志内容，避免检测历史日志
            content = self.log_manager.read_new_app_log()

            # 步骤1: 检测日志失败关键字（适用于S1/X1的日志检测阶段）
            if (is_s1 or is_x1) and content:
                if is_s1 and elapsed < log_check_end:
                    # S1: 0-70秒检测日志失败
                    for kw in fail_keywords:
                        if kw in content:
                            self.logger.error(f"S1模组日志检测到升级失败: {kw}")
                            return False
                elif is_x1 and elapsed < log_check_end:
                    # X1: 0-90秒检测日志失败
                    for kw in fail_keywords:
                        if kw in content:
                            self.logger.error(f"X1模组日志检测到升级失败: {kw}")
                            return False

            # 步骤2: 检测UI气泡（适用于S1/X1的UI检测阶段）
            if (is_s1 or is_x1) and not ui_detected:
                if is_s1 and log_check_end <= elapsed < ui_check_end:
                    # S1: 70-85秒检测UI气泡
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(exists, upgrade_success_template)
                            ui_result = future.result(timeout=3)
                        if ui_result:
                            ui_detected = True
                            self.logger.info("检测到升级成功气泡（UI）")
                    except concurrent.futures.TimeoutError:
                        pass
                    except Exception as e:
                        self.logger.warning(f"UI检测异常: {e}")
                elif is_x1 and log_check_end <= elapsed < ui_check_end:
                    # X1: 90-105秒检测UI气泡
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(exists, upgrade_success_template)
                            ui_result = future.result(timeout=3)
                        if ui_result:
                            ui_detected = True
                            self.logger.info("检测到升级成功气泡（UI）")
                    except concurrent.futures.TimeoutError:
                        pass
                    except Exception as e:
                        self.logger.warning(f"UI检测异常: {e}")

            # 非S1/X1设备，保持原有的UI检测逻辑
            if not is_s1 and not is_x1 and not ui_detected:
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(exists, upgrade_success_template)
                        ui_result = future.result(timeout=3)
                    if ui_result:
                        ui_detected = True
                        self.logger.info("检测到升级成功气泡（UI）")
                except concurrent.futures.TimeoutError:
                    pass
                except Exception as e:
                    self.logger.warning(f"UI检测异常: {e}")

            # 步骤3: 兜底方案（适用于S1/X1）
            if (is_s1 or is_x1) and not ui_detected and not fallback_triggered and elapsed >= fallback_time:
                device_name = "S1" if is_s1 else "X1"
                self.logger.info(f"{device_name}模组：{fallback_time}秒未检测到气泡，启用日志版本验证兜底方案...")
                fallback_triggered = True

                if expected_version:
                    # 只读取升级确认时间之后的日志内容来验证版本号
                    actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
                    self.logger.info(f"{device_name}兜底方案 - 实际版本: {actual_version}, 预期版本: {expected_version}")

                    if actual_version == expected_version:
                        self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                        self.logger.result(f"{device_name}日志兜底确认：固件版本匹配", success=True)
                        return True

                    # 检查升级确认时间之后的日志中是否有升级失败关键字
                    new_content = self.log_manager.read_new_app_log()
                    for kw in fail_keywords:
                        if kw in new_content:
                            self.logger.error(f"{device_name}日志兜底检测到升级失败: {kw}")
                            return False

            # 步骤4: 如果UI已检测到，检测日志版本确认
            if ui_detected:
                if content:
                    # 记录升级成功的时间点
                    sermon_success_keywords = [
                        "SermoonS1UpgradeCompletedSuccess or Failed",
                        "SermoonUpgradeCompletedSuccess",
                        "OnDeviceUpgradeSuccess called"
                    ]
                    for keyword in sermon_success_keywords:
                        if keyword in content:
                            lines = content.splitlines()
                            for line in reversed(lines):
                                if keyword in line:
                                    time_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                                    if time_match:
                                        self._upgrade_success_time = time_match.group(1)
                                        self.logger.info(f"记录升级时间点: {self._upgrade_success_time}")
                                    break
                            break

                    # 检查升级失败关键字
                    for kw in fail_keywords:
                        if kw in content:
                            self.logger.error(f"日志检测到升级失败: {kw}")
                            return False

                # UI已检测到，日志时间点也已记录，认为升级成功
                self._upgrade_success_time = self._upgrade_success_time or time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result("UI检测到升级成功，气泡已出现", success=True)
                return True

            # 每 10 秒输出一次等待状态
            if time.time() - last_check_time >= 10:
                remaining = timeout - elapsed
                if is_s1:
                    if elapsed < log_check_end:
                        status = "S1日志检测中..."
                    elif elapsed < ui_check_end:
                        status = "S1等待UI气泡..."
                    else:
                        status = "S1兜底方案已触发"
                elif is_x1:
                    if elapsed < log_check_end:
                        status = "X1日志检测中..."
                    elif elapsed < ui_check_end:
                        status = "X1等待UI气泡..."
                    else:
                        status = "X1兜底方案已触发"
                else:
                    status = "等待UI气泡..." if not ui_detected else "已检测到UI"
                self.logger.info(f"升级进行中 [{status}]，已等待 {int(elapsed)}s，剩余 {int(remaining)}s...")
                last_check_time = time.time()

            sleep(2)

        self.logger.error(f"升级检测超时（{timeout}秒）")
        return False

    def _wait_for_x1wifi_reconnect(self, firmware_path: str, upgrade_confirm_time: str = None, timeout: int = 90):
        """
        等待X1 WiFi设备重新连接

        X1 WiFi升级过程中：
        - WiFi手柄(wifiBridgePid)保持连接
        - X1模组(scannerPid)会断开并重新连接
        - 重连后：scannerPid从UNKNOWN变回SCANNER_SERMOON_X1

        流程：
        1. 检测UI升级成功气泡
        2. 等待X1模组重连 (scannerPid变回SCANNER_SERMOON_X1)
        3. 验证wifiBridgePid存在
        4. 使用日志版本验证兜底

        Args:
            firmware_path: 固件文件路径（用于兜底方案获取预期版本）
            upgrade_confirm_time: 点击升级确认按钮的时间（用于日志版本验证）
            timeout: 超时时间（秒），默认90秒

        Returns:
            bool: 升级是否成功完成
        """
        import concurrent.futures

        self.logger.info(f"开始X1 WiFi重连检测（超时: {timeout}秒）...")

        start_time = time.time()
        last_check_time = start_time
        self._upgrade_success_time = None

        # 重置日志位置，记录当前日志大小，后续只读取新增内容
        self.log_manager.refresh_latest_log_dir()
        self.log_manager.reset_log_position()

        # 获取预期版本号（用于兜底方案）
        expected_version = None
        match = re.search(r'(\d+\.\d+\.\d+)', Path(firmware_path).name)
        if match:
            expected_version = match.group(1)
            self.logger.info(f"预期版本: {expected_version}")

        # UI气泡检测模板
        upgrade_success_template = Template(self.images['upgrade_success'], threshold=self.threshold)

        # 升级失败关键字
        fail_keywords = ['UpgradeFailed', 'Upgrade failed', 'upgrade failed']

        # X1 WiFi重连状态
        ui_detected = False  # UI气泡是否已检测到
        x1_reconnected = False  # X1模组是否已重连
        current_scanner = None  # 当前scanner状态
        current_wifi_bridge = None  # 当前wifiBridge状态

        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time

            # 刷新日志目录
            self.log_manager.refresh_latest_log_dir()
            content = self.log_manager.read_new_app_log()

            # 步骤1: 检测日志失败关键字
            if content:
                for kw in fail_keywords:
                    if kw in content:
                        self.logger.error(f"日志检测到升级失败: {kw}")
                        return False

            # 步骤2: 检测UI气泡（只要没检测到就继续检测）
            ui_detect_time = None  # 记录UI检测到的时间
            if not ui_detected:
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(exists, upgrade_success_template)
                        ui_result = future.result(timeout=3)
                    if ui_result:
                        ui_detected = True
                        ui_detect_time = time.time()
                        self.logger.info("检测到升级成功气泡（UI），等待10秒后检查模组重连...")
                except concurrent.futures.TimeoutError:
                    pass
                except Exception as e:
                    self.logger.warning(f"UI检测异常: {e}")

            # 步骤3: 检测X1模组重连
            # 只有在UI检测到后等待至少10秒才检查重连（给设备时间重连）
            should_check_reconnect = False
            if ui_detected:
                # 记录首次UI检测到的时间
                if not hasattr(self, '_ui_detected_time'):
                    self._ui_detected_time = time.time()

                # 等待至少10秒后再检查重连
                if time.time() - self._ui_detected_time >= 10:
                    should_check_reconnect = True
                    self.logger.info(f"开始检查X1模组重连（已等待{int(time.time() - self._ui_detected_time)}秒）...")

            if should_check_reconnect:
                self.log_manager.refresh_latest_log_dir()

                # 调试：读取日志，检查最后几个scannerPid
                log_content = self.log_manager.read_app_log()
                scanner_pids = re.findall(r'scannerPid:([A-Za-z_0-9]+)', log_content)
                wifi_bridge_pids = re.findall(r'wifiBridgePid:([A-Za-z_0-9]+)', log_content)

                device_info = self.log_manager.get_device_connection_info()
                current_scanner = device_info.get('scanner_pid')
                current_wifi_bridge = device_info.get('wifi_bridge_pid')

                # 调试：每10秒打印当前设备状态和日志中的scannerPid列表
                if int(elapsed) % 10 == 0:
                    last_5_scanners = scanner_pids[-5:] if scanner_pids else []
                    last_5_bridges = wifi_bridge_pids[-5:] if wifi_bridge_pids else []
                    self.logger.info(f"调试 - 日志中最后的scannerPids: {last_5_scanners}")
                    self.logger.info(f"调试 - 日志中最后的wifiBridgePids: {last_5_bridges}")
                    self.logger.info(f"调试 - ui_detected={ui_detected}, x1_reconnected={x1_reconnected}, scanner={current_scanner}, wifi_bridge={current_wifi_bridge}")

                # X1模组和手柄都上线才认为重连成功
                if not x1_reconnected:
                    if current_scanner == 'SCANNER_SERMOON_X1' and current_wifi_bridge:
                        x1_reconnected = True
                        self.logger.info(f"检测到X1模组和手柄都已重新连接")
            else:
                # UI已检测但还没到10秒，继续等待
                if ui_detected and not hasattr(self, '_ui_detected_time'):
                    self._ui_detected_time = time.time()

                if ui_detected and hasattr(self, '_ui_detected_time'):
                    wait_time = time.time() - self._ui_detected_time
                    if int(wait_time) % 10 == 0:
                        self.logger.info(f"等待重连中，已等待{int(wait_time)}秒...")

            # 步骤4: UI检测到 + X1模组已重连，认为升级成功
            if ui_detected and x1_reconnected:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result("X1 WiFi：UI检测成功 + X1模组已重连", success=True)
                return True

            # 步骤5: 兜底方案 - UI未检测到或重连未检测到时，超时前启用
            # 不管UI是否检测到，只要超时前没完成重连就用兜底
            if not x1_reconnected and elapsed >= timeout - 10:
                self.logger.info("X1 WiFi：超时前启用日志版本验证兜底方案...")

                if expected_version and upgrade_confirm_time:
                    actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
                    self.logger.info(f"兜底方案 - 实际版本: {actual_version}, 预期版本: {expected_version}")

                    if actual_version == expected_version:
                        self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                        self.logger.result("X1 WiFi日志兜底确认：固件版本匹配", success=True)
                        return True

            # 每 10 秒输出一次等待状态
            if time.time() - last_check_time >= 10:
                remaining = timeout - elapsed
                status = []
                if ui_detected:
                    status.append("UI OK")
                if x1_reconnected:
                    status.append("X1已重连")
                status_str = ", ".join(status) if status else "等待中"
                self.logger.info(f"X1 WiFi升级进行中 [{status_str}]，已等待 {int(elapsed)}s，剩余 {int(remaining)}s...")
                last_check_time = time.time()

            sleep(2)

        # 超时后最后一次兜底尝试
        self.logger.warning("X1 WiFi重连检测超时，尝试日志版本验证...")
        if expected_version and upgrade_confirm_time:
            actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
            if actual_version == expected_version:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result("X1 WiFi超时后兜底：固件版本匹配", success=True)
                return True

        self.logger.error(f"X1 WiFi升级检测超时（{timeout}秒）")
        return False

    def _wait_for_s1wifi_reconnect(self, firmware_path: str, upgrade_confirm_time: str = None, timeout: int = 60):
        """
        等待S1 WiFi设备重新连接

        S1 WiFi升级过程中：
        - WiFi手柄(wifiBridgePid)保持连接
        - S1模组(scannerPid)会断开并重新连接
        - 重连后：scannerPid从UNKNOWN变回SCANNER_SERMOON_S1
        - 关键日志：`检测到升级后设备重新上线，准备恢复参数`

        流程：
        1. 检测UI升级成功气泡
        2. 检测S1模组重连 (scannerPid变回SCANNER_SERMOON_S1)
        3. 验证wifiBridgePid存在
        4. 检测关键日志：`检测到升级后设备重新上线` 或 `firmware_upgrade_completed`
        5. 使用日志版本验证兜底

        Args:
            firmware_path: 固件文件路径（用于兜底方案获取预期版本）
            upgrade_confirm_time: 点击升级确认按钮的时间（用于日志版本验证）
            timeout: 超时时间（秒），默认60秒

        Returns:
            bool: 升级是否成功完成
        """
        import concurrent.futures

        self.logger.info(f"开始S1 WiFi重连检测（超时: {timeout}秒）...")

        start_time = time.time()
        last_check_time = start_time
        self._upgrade_success_time = None

        # 重置日志位置，记录当前日志大小，后续只读取新增内容
        self.log_manager.refresh_latest_log_dir()
        self.log_manager.reset_log_position()

        # 获取预期版本号（用于兜底方案）
        expected_version = None
        match = re.search(r'(\d+\.\d+\.\d+)', Path(firmware_path).name)
        if match:
            expected_version = match.group(1)
            self.logger.info(f"预期版本: {expected_version}")

        # UI气泡检测模板
        upgrade_success_template = Template(self.images['upgrade_success'], threshold=self.threshold)

        # 升级失败关键字
        fail_keywords = ['UpgradeFailed', 'Upgrade failed', 'upgrade failed']

        # S1 WiFi重连状态
        ui_detected = False  # UI气泡是否已检测到
        s1_reconnected = False  # S1模组是否已重连
        current_scanner = None  # 当前scanner状态
        current_wifi_bridge = None  # 当前wifiBridge状态

        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time

            # 刷新日志目录
            self.log_manager.refresh_latest_log_dir()
            content = self.log_manager.read_new_app_log()

            # 步骤1: 检测日志失败关键字
            if content:
                for kw in fail_keywords:
                    if kw in content:
                        self.logger.error(f"日志检测到升级失败: {kw}")
                        return False

            # 步骤2: 检测关键日志（S1 WiFi特有）
            # `检测到升级后设备重新上线，准备恢复参数` 或 `firmware_upgrade_completed`
            if '检测到升级后设备重新上线' in content or 'firmware_upgrade_completed' in content:
                self.logger.info("检测到S1 WiFi升级完成关键日志")
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result("S1 WiFi：日志确认升级完成", success=True)
                return True

            # 步骤3: 检测UI气泡（只要没检测到就继续检测）
            ui_detect_time = None
            if not ui_detected:
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(exists, upgrade_success_template)
                        ui_result = future.result(timeout=3)
                    if ui_result:
                        ui_detected = True
                        ui_detect_time = time.time()
                        self.logger.info("检测到升级成功气泡（UI），等待10秒后检查模组重连...")
                except concurrent.futures.TimeoutError:
                    pass
                except Exception as e:
                    self.logger.warning(f"UI检测异常: {e}")

            # 步骤4: 检测S1模组重连
            # 只有在UI检测到后等待至少10秒才检查重连（给设备时间重连）
            should_check_reconnect = False
            if ui_detected:
                # 记录首次UI检测到的时间
                if not hasattr(self, '_s1_ui_detected_time'):
                    self._s1_ui_detected_time = time.time()

                # 等待至少10秒后再检查重连
                if time.time() - self._s1_ui_detected_time >= 10:
                    should_check_reconnect = True
                    self.logger.info(f"开始检查S1模组重连（已等待{int(time.time() - self._s1_ui_detected_time)}秒）...")

            if should_check_reconnect:
                self.log_manager.refresh_latest_log_dir()

                # 调试：读取日志，检查最后几个scannerPid
                log_content = self.log_manager.read_app_log()
                scanner_pids = re.findall(r'scannerPid:([A-Za-z_0-9]+)', log_content)
                wifi_bridge_pids = re.findall(r'wifiBridgePid:([A-Za-z_0-9]+)', log_content)

                device_info = self.log_manager.get_device_connection_info()
                current_scanner = device_info.get('scanner_pid')
                current_wifi_bridge = device_info.get('wifi_bridge_pid')

                # 调试：每10秒打印当前设备状态和日志中的scannerPid列表
                if int(elapsed) % 10 == 0:
                    last_5_scanners = scanner_pids[-5:] if scanner_pids else []
                    last_5_bridges = wifi_bridge_pids[-5:] if wifi_bridge_pids else []
                    self.logger.info(f"调试 - 日志中最后的scannerPids: {last_5_scanners}")
                    self.logger.info(f"调试 - 日志中最后的wifiBridgePids: {last_5_bridges}")
                    self.logger.info(f"调试 - ui_detected={ui_detected}, s1_reconnected={s1_reconnected}, scanner={current_scanner}, wifi_bridge={current_wifi_bridge}")

                # S1模组和手柄都上线才认为重连成功
                if not s1_reconnected:
                    if current_scanner == 'SCANNER_SERMOON_S1' and current_wifi_bridge:
                        s1_reconnected = True
                        self.logger.info(f"检测到S1模组和手柄都已重新连接")
            else:
                # UI已检测但还没到10秒，继续等待
                if ui_detected and not hasattr(self, '_s1_ui_detected_time'):
                    self._s1_ui_detected_time = time.time()

                if ui_detected and hasattr(self, '_s1_ui_detected_time'):
                    wait_time = time.time() - self._s1_ui_detected_time
                    if int(wait_time) % 10 == 0:
                        self.logger.info(f"等待重连中，已等待{int(wait_time)}秒...")

            # 步骤5: UI检测到 + S1模组已重连，认为升级成功
            if ui_detected and s1_reconnected:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result("S1 WiFi：UI检测成功 + S1模组已重连", success=True)
                return True

            # 步骤6: 兜底方案 - UI未检测到或重连未检测到时，超时前启用
            # 不管UI是否检测到，只要超时前没完成重连就用兜底
            if not s1_reconnected and elapsed >= timeout - 10:
                self.logger.info("S1 WiFi：超时前启用日志版本验证兜底方案...")

                if expected_version and upgrade_confirm_time:
                    actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
                    self.logger.info(f"兜底方案 - 实际版本: {actual_version}, 预期版本: {expected_version}")

                    if actual_version == expected_version:
                        self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                        self.logger.result("S1 WiFi日志兜底确认：固件版本匹配", success=True)
                        return True

            # 每 10 秒输出一次等待状态
            if time.time() - last_check_time >= 10:
                remaining = timeout - elapsed
                status = []
                if ui_detected:
                    status.append("UI OK")
                if s1_reconnected:
                    status.append("S1已重连")
                status_str = ", ".join(status) if status else "等待中"
                self.logger.info(f"S1 WiFi升级进行中 [{status_str}]，已等待 {int(elapsed)}s，剩余 {int(remaining)}s...")
                last_check_time = time.time()

            sleep(2)

        # 超时后最后一次兜底尝试
        self.logger.warning("S1 WiFi重连检测超时，尝试日志版本验证...")
        if expected_version and upgrade_confirm_time:
            actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
            if actual_version == expected_version:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result("S1 WiFi超时后兜底：固件版本匹配", success=True)
                return True

        self.logger.error(f"S1 WiFi升级检测超时（{timeout}秒）")
        return False

    def _wait_for_raptorwifi_reconnect(self, firmware_path: str, upgrade_confirm_time: str = None, timeout: int = 30, device_model: str = None):
        """
        等待Raptor系列WiFi设备重新连接

        Raptor WiFi升级过程中：
        - WiFi手柄(wifiBridgePid)保持连接
        - Raptor模组(scannerPid)会断开并重新连接
        - 重连后：scannerPid变回SCANNER_RAPTOR*
        - 关键日志：`firmware_upgrade_completed`

        流程：
        1. 检测UI升级成功气泡
        2. 检测Raptor模组重连 (scannerPid变回SCANNER_RAPTOR*)
        3. 验证wifiBridgePid存在
        4. 检测关键日志：`firmware_upgrade_completed`

        Args:
            firmware_path: 固件文件路径（用于兜底方案获取预期版本）
            upgrade_confirm_time: 点击升级确认按钮的时间（用于日志版本验证）
            timeout: 超时时间（秒），默认30秒
            device_model: 设备型号（如SCANNER_RAPTORPRO）

        Returns:
            bool: 升级是否成功完成
        """
        import concurrent.futures

        # 获取设备友好名称
        if device_model:
            device_name = device_model.replace('SCANNER_', '').replace('_', ' ')
        else:
            device_info = self.log_manager.get_device_connection_info()
            device_name = device_info.get('device_type') or 'Raptor'

        self.logger.info(f"开始{device_name} WiFi重连检测（超时: {timeout}秒）...")

        start_time = time.time()
        last_check_time = start_time
        self._upgrade_success_time = None

        # 重置日志位置，记录当前日志大小，后续只读取新增内容
        self.log_manager.refresh_latest_log_dir()
        self.log_manager.reset_log_position()

        # 获取预期版本号（用于兜底方案）
        expected_version = None
        match = re.search(r'(\d+\.\d+\.\d+)', Path(firmware_path).name)
        if match:
            expected_version = match.group(1)
            self.logger.info(f"预期版本: {expected_version}")

        # UI气泡检测模板（使用较低的阈值提高识别灵敏度）
        raptor_threshold = 0.75  # Raptor升级较快，降低阈值提高识别率
        upgrade_success_template = Template(self.images['upgrade_success'], threshold=raptor_threshold)

        # 升级失败关键字
        fail_keywords = ['UpgradeFailed', 'Upgrade failed', 'upgrade failed']

        # Raptor WiFi重连状态
        ui_detected = False  # UI气泡是否已检测到
        raptor_reconnected = False  # Raptor模组是否已重连
        current_scanner = None  # 当前scanner状态
        current_wifi_bridge = None  # 当前wifiBridge状态

        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time

            # 刷新日志目录
            self.log_manager.refresh_latest_log_dir()
            content = self.log_manager.read_new_app_log()

            # 步骤1: 检测日志失败关键字
            if content:
                for kw in fail_keywords:
                    if kw in content:
                        self.logger.error(f"日志检测到升级失败: {kw}")
                        return False

            # 步骤2: 检测关键日志（Raptor WiFi）
            # 检测升级完成关键日志
            if 'firmware_upgrade_completed' in content:
                self.logger.info(f"检测到{device_name} WiFi升级完成关键日志: firmware_upgrade_completed")
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi：日志确认升级完成", success=True)
                return True

            # 检测设备重连关键日志 - 和S1/X1一致，检测到设备重新上线日志后直接确认成功
            reconnect_log_patterns = [
                'OnDeviceConnect',
                'Device connected:1 scannerpid=SCANNER_RAPTOR',
                'Device connected:2 SCANNER_RAPTOR',
            ]
            if any(pattern in content for pattern in reconnect_log_patterns):
                self.logger.info(f"检测到{device_name} WiFi设备重连关键日志: OnDeviceConnect/Device connected")
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi：日志确认设备已重连", success=True)
                return True

            # 步骤3: 检测UI气泡（只要没检测到就继续检测）
            ui_detect_time = None
            if not ui_detected:
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(exists, upgrade_success_template)
                        ui_result = future.result(timeout=3)
                    if ui_result:
                        ui_detected = True
                        ui_detect_time = time.time()
                        self.logger.info("检测到升级成功气泡（UI），等待设备重连...")
                except concurrent.futures.TimeoutError:
                    pass
                except Exception as e:
                    self.logger.warning(f"UI检测异常: {e}")

            # 步骤4: 检测Raptor模组重连
            should_check_reconnect = False
            if ui_detected:
                # 记录首次UI检测到的时间
                if not hasattr(self, '_raptor_ui_detected_time'):
                    self._raptor_ui_detected_time = time.time()

                # 等待至少10秒后再检查重连（和X1/S1保持一致）
                if time.time() - self._raptor_ui_detected_time >= 10:
                    should_check_reconnect = True
                    self.logger.info(f"开始检查{device_name}模组重连（已等待{int(time.time() - self._raptor_ui_detected_time)}秒）...")

            if should_check_reconnect:
                self.log_manager.refresh_latest_log_dir()

                # 重点：只读取新增的日志内容（升级确认时间之后的），避免历史日志干扰
                if upgrade_confirm_time:
                    # 使用升级确认时间作为起点，读取之后的新日志
                    new_log_content = self.log_manager.read_log_since_time(upgrade_confirm_time)
                else:
                    new_log_content = self.log_manager.read_new_app_log()

                # 步骤4.1: 检测新增日志中的关键日志 - 设备重连日志
                # 日志特征: "OnDeviceConnect" 或 "Device connected:1 scannerpid=SCANNER_RAPTORPRO"
                reconnect_log_patterns = [
                    'OnDeviceConnect',
                    'Device connected:1 scannerpid=SCANNER_RAPTOR',
                    'Device connected:2 SCANNER_RAPTOR',
                ]
                # 只检测新增日志中是否有重连日志
                has_reconnect_log = any(pattern in new_log_content for pattern in reconnect_log_patterns)

                # 步骤4.2: 检测新增日志中的断开日志，判断是否还在升级过程中
                disconnect_patterns = ['OnDeviceDisconnect', 'No device found']
                has_disconnect_log = any(pattern in new_log_content for pattern in disconnect_patterns)

                # 步骤4.3: 从新增日志中提取最新的设备状态
                # 只从新增日志中提取，避免历史数据干扰
                new_scanner_pids = re.findall(r'scannerPid:([A-Za-z_0-9]+)', new_log_content)
                new_wifi_bridge_pids = re.findall(r'wifiBridgePid:([A-Za-z_0-9]+)', new_log_content)
                current_scanner = new_scanner_pids[-1] if new_scanner_pids else None
                current_wifi_bridge = new_wifi_bridge_pids[-1] if new_wifi_bridge_pids else None

                # 只有当新增日志中有重连关键日志时，才认为重连成功
                if not raptor_reconnected:
                    if has_reconnect_log:
                        raptor_reconnected = True
                        self.logger.info(f"✓ 检测到{device_name} WiFi设备重连")
                    elif has_disconnect_log:
                        # 设备还在断开状态，继续等待
                        pass

            # 步骤5: UI检测到 + Raptor模组已重连，认为升级成功
            if ui_detected and raptor_reconnected:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi：UI检测成功 + {device_name}模组已重连", success=True)
                return True

            # 步骤6: 兜底方案 - UI未检测到或重连未检测到时，超时前启用
            if not raptor_reconnected and elapsed >= timeout - 5:
                self.logger.info(f"{device_name} WiFi：超时前启用日志版本验证兜底方案...")

                if expected_version and upgrade_confirm_time:
                    actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
                    self.logger.info(f"兜底方案 - 实际版本: {actual_version}, 预期版本: {expected_version}")

                    if actual_version == expected_version:
                        self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                        self.logger.result(f"{device_name} WiFi日志兜底确认：固件版本匹配", success=True)
                        return True

            # 每 5 秒输出一次等待状态
            if time.time() - last_check_time >= 5:
                remaining = timeout - elapsed
                status = []
                if ui_detected:
                    status.append("UI OK")
                if raptor_reconnected:
                    status.append("已重连")
                status_str = ", ".join(status) if status else "等待中"
                self.logger.info(f"{device_name} WiFi升级进行中 [{status_str}]，已等待 {int(elapsed)}s，剩余 {int(remaining)}s...")
                last_check_time = time.time()

            sleep(1)  # Raptor升级较快，使用1秒间隔检测

        # 超时后最后一次兜底尝试
        self.logger.warning(f"{device_name} WiFi重连检测超时，尝试日志版本验证...")
        if expected_version and upgrade_confirm_time:
            actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
            if actual_version == expected_version:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi超时后兜底：固件版本匹配", success=True)
                return True

        self.logger.error(f"{device_name} WiFi升级检测超时（{timeout}秒）")
        return False

    def _wait_for_ferretwifi_reconnect(self, firmware_path: str, upgrade_confirm_time: str = None, timeout: int = 30, device_model: str = None):
        """
        等待Ferret系列WiFi设备重新连接

        Ferret WiFi升级过程中：
        - WiFi手柄(wifiBridgePid)保持连接
        - Ferret模组(scannerPid)会断开并重新连接
        - 重连后：scannerPid变回SCANNER_FERRET
        - 关键日志：`firmware_upgrade_completed`

        流程：
        1. 检测UI升级成功气泡
        2. 检测Ferret模组重连 (scannerPid变回SCANNER_FERRET)
        3. 验证wifiBridgePid存在
        4. 检测关键日志：`firmware_upgrade_completed`

        Args:
            firmware_path: 固件文件路径（用于兜底方案获取预期版本）
            upgrade_confirm_time: 点击升级确认按钮的时间（用于日志版本验证）
            timeout: 超时时间（秒），默认30秒
            device_model: 设备型号（如SCANNER_FERRET）

        Returns:
            bool: 升级是否成功完成
        """
        import concurrent.futures

        # 获取设备友好名称
        if device_model:
            device_name = device_model.replace('SCANNER_', '').replace('_', ' ')
        else:
            device_info = self.log_manager.get_device_connection_info()
            device_name = device_info.get('device_type') or 'Ferret'

        self.logger.info(f"开始{device_name} WiFi重连检测（超时: {timeout}秒）...")

        start_time = time.time()
        last_check_time = start_time
        self._upgrade_success_time = None

        # 重置日志位置，记录当前日志大小，后续只读取新增内容
        self.log_manager.refresh_latest_log_dir()
        self.log_manager.reset_log_position()

        # 获取预期版本号（用于兜底方案）
        expected_version = None
        match = re.search(r'(\d+\.\d+\.\d+)', Path(firmware_path).name)
        if match:
            expected_version = match.group(1)
            self.logger.info(f"预期版本: {expected_version}")

        # UI气泡检测模板（使用较低的阈值提高识别灵敏度）
        ferret_threshold = 0.75  # Ferret升级较快，降低阈值提高识别率
        upgrade_success_template = Template(self.images['upgrade_success'], threshold=ferret_threshold)

        # 升级失败关键字
        fail_keywords = ['UpgradeFailed', 'Upgrade failed', 'upgrade failed']

        # Ferret WiFi重连状态
        ui_detected = False  # UI气泡是否已检测到
        ferret_reconnected = False  # Ferret模组是否已重连
        current_scanner = None  # 当前scanner状态
        current_wifi_bridge = None  # 当前wifiBridge状态

        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time

            # 刷新日志目录
            self.log_manager.refresh_latest_log_dir()
            content = self.log_manager.read_new_app_log()

            # 步骤1: 检测日志失败关键字
            if content:
                for kw in fail_keywords:
                    if kw in content:
                        self.logger.error(f"日志检测到升级失败: {kw}")
                        return False

            # 步骤2: 检测关键日志（Ferret WiFi）
            # 检测升级完成关键日志
            if 'firmware_upgrade_completed' in content:
                self.logger.info(f"检测到{device_name} WiFi升级完成关键日志: firmware_upgrade_completed")
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi：日志确认升级完成", success=True)
                return True

            # 检测设备重连关键日志 - 和S1/X1一致，检测到设备重新上线日志后直接确认成功
            reconnect_log_patterns = [
                'OnDeviceConnect',
                'Device connected:1 scannerpid=SCANNER_FERRET',
                'Device connected:2 SCANNER_FERRET',
            ]
            if any(pattern in content for pattern in reconnect_log_patterns):
                self.logger.info(f"检测到{device_name} WiFi设备重连关键日志: OnDeviceConnect/Device connected")
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi：日志确认设备已重连", success=True)
                return True

            # 步骤3: 检测UI气泡（只要没检测到就继续检测）
            ui_detect_time = None
            if not ui_detected:
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(exists, upgrade_success_template)
                        ui_result = future.result(timeout=3)
                    if ui_result:
                        ui_detected = True
                        ui_detect_time = time.time()
                        self.logger.info("检测到升级成功气泡（UI），等待设备重连...")
                except concurrent.futures.TimeoutError:
                    pass
                except Exception as e:
                    self.logger.warning(f"UI检测异常: {e}")

            # 步骤4: 检测Ferret模组重连
            should_check_reconnect = False
            if ui_detected:
                # 记录首次UI检测到的时间
                if not hasattr(self, '_ferret_ui_detected_time'):
                    self._ferret_ui_detected_time = time.time()

                # 等待至少10秒后再检查重连（和X1/S1保持一致）
                if time.time() - self._ferret_ui_detected_time >= 10:
                    should_check_reconnect = True
                    self.logger.info(f"开始检查{device_name}模组重连（已等待{int(time.time() - self._ferret_ui_detected_time)}秒）...")

            if should_check_reconnect:
                self.log_manager.refresh_latest_log_dir()

                # 重点：只读取新增的日志内容（升级确认时间之后的），避免历史日志干扰
                if upgrade_confirm_time:
                    # 使用升级确认时间作为起点，读取之后的新日志
                    new_log_content = self.log_manager.read_log_since_time(upgrade_confirm_time)
                else:
                    new_log_content = self.log_manager.read_new_app_log()

                # 步骤4.1: 检测新增日志中的关键日志 - 设备重连日志
                # 日志特征: "OnDeviceConnect" 或 "Device connected:1 scannerpid=SCANNER_FERRET"
                reconnect_log_patterns = [
                    'OnDeviceConnect',
                    'Device connected:1 scannerpid=SCANNER_FERRET',
                    'Device connected:2 SCANNER_FERRET',
                ]
                # 只检测新增日志中是否有重连日志
                has_reconnect_log = any(pattern in new_log_content for pattern in reconnect_log_patterns)

                # 步骤4.2: 检测新增日志中的断开日志，判断是否还在升级过程中
                disconnect_patterns = ['OnDeviceDisconnect', 'No device found']
                has_disconnect_log = any(pattern in new_log_content for pattern in disconnect_patterns)

                # 步骤4.3: 从新增日志中提取最新的设备状态
                # 只从新增日志中提取，避免历史数据干扰
                new_scanner_pids = re.findall(r'scannerPid:([A-Za-z_0-9]+)', new_log_content)
                new_wifi_bridge_pids = re.findall(r'wifiBridgePid:([A-Za-z_0-9]+)', new_log_content)
                current_scanner = new_scanner_pids[-1] if new_scanner_pids else None
                current_wifi_bridge = new_wifi_bridge_pids[-1] if new_wifi_bridge_pids else None

                # 只有当新增日志中有重连关键日志时，才认为重连成功
                if not ferret_reconnected:
                    if has_reconnect_log:
                        ferret_reconnected = True
                        self.logger.info(f"✓ 检测到{device_name} WiFi设备重连")
                    elif has_disconnect_log:
                        # 设备还在断开状态，继续等待
                        pass

            # 步骤5: UI检测到 + Ferret模组已重连，认为升级成功
            if ui_detected and ferret_reconnected:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi：UI检测成功 + {device_name}模组已重连", success=True)
                return True

            # 步骤6: 兜底方案 - UI未检测到或重连未检测到时，超时前启用
            if not ferret_reconnected and elapsed >= timeout - 5:
                self.logger.info(f"{device_name} WiFi：超时前启用日志版本验证兜底方案...")

                if expected_version and upgrade_confirm_time:
                    actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
                    self.logger.info(f"兜底方案 - 实际版本: {actual_version}, 预期版本: {expected_version}")

                    if actual_version == expected_version:
                        self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                        self.logger.result(f"{device_name} WiFi日志兜底确认：固件版本匹配", success=True)
                        return True

            # 每 5 秒输出一次等待状态
            if time.time() - last_check_time >= 5:
                remaining = timeout - elapsed
                status = []
                if ui_detected:
                    status.append("UI OK")
                if ferret_reconnected:
                    status.append("已重连")
                status_str = ", ".join(status) if status else "等待中"
                self.logger.info(f"{device_name} WiFi升级进行中 [{status_str}]，已等待 {int(elapsed)}s，剩余 {int(remaining)}s...")
                last_check_time = time.time()

            sleep(1)  # Ferret升级较快，使用1秒间隔检测

        # 超时后最后一次兜底尝试
        self.logger.warning(f"{device_name} WiFi重连检测超时，尝试日志版本验证...")
        if expected_version and upgrade_confirm_time:
            actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
            if actual_version == expected_version:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi超时后兜底：固件版本匹配", success=True)
                return True

        self.logger.error(f"{device_name} WiFi升级检测超时（{timeout}秒）")
        return False

    def _wait_for_otterwifi_reconnect(self, firmware_path: str, upgrade_confirm_time: str = None, timeout: int = 30, device_model: str = None):
        """
        等待Otter系列WiFi设备重新连接

        Otter WiFi升级过程中：
        - WiFi手柄(wifiBridgePid)保持连接
        - Otter模组(scannerPid)会断开并重新连接
        - 重连后：scannerPid变回SCANNER_OTTER
        - 关键日志：`firmware_upgrade_completed`

        流程：
        1. 检测UI升级成功气泡
        2. 检测Otter模组重连 (scannerPid变回SCANNER_OTTER)
        3. 验证wifiBridgePid存在
        4. 检测关键日志：`firmware_upgrade_completed`

        Args:
            firmware_path: 固件文件路径（用于兜底方案获取预期版本）
            upgrade_confirm_time: 点击升级确认按钮的时间（用于日志版本验证）
            timeout: 超时时间（秒），默认30秒
            device_model: 设备型号（如SCANNER_OTTER）

        Returns:
            bool: 升级是否成功完成
        """
        import concurrent.futures

        # 获取设备友好名称
        if device_model:
            device_name = device_model.replace('SCANNER_', '').replace('_', ' ')
        else:
            device_info = self.log_manager.get_device_connection_info()
            device_name = device_info.get('device_type') or 'Otter'

        self.logger.info(f"开始{device_name} WiFi重连检测（超时: {timeout}秒）...")

        start_time = time.time()
        last_check_time = start_time
        self._upgrade_success_time = None

        # 重置日志位置，记录当前日志大小，后续只读取新增内容
        self.log_manager.refresh_latest_log_dir()
        self.log_manager.reset_log_position()

        # 获取预期版本号（用于兜底方案）
        expected_version = None
        match = re.search(r'(\d+\.\d+\.\d+)', Path(firmware_path).name)
        if match:
            expected_version = match.group(1)
            self.logger.info(f"预期版本: {expected_version}")

        # UI气泡检测模板（使用较低的阈值提高识别灵敏度）
        otter_threshold = 0.75  # Otter升级较快，降低阈值提高识别率
        upgrade_success_template = Template(self.images['upgrade_success'], threshold=otter_threshold)

        # 升级失败关键字
        fail_keywords = ['UpgradeFailed', 'Upgrade failed', 'upgrade failed']

        # Otter WiFi重连状态
        ui_detected = False  # UI气泡是否已检测到
        otter_reconnected = False  # Otter模组是否已重连
        current_scanner = None  # 当前scanner状态
        current_wifi_bridge = None  # 当前wifiBridge状态

        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time

            # 刷新日志目录
            self.log_manager.refresh_latest_log_dir()
            content = self.log_manager.read_new_app_log()

            # 步骤1: 检测日志失败关键字
            if content:
                for kw in fail_keywords:
                    if kw in content:
                        self.logger.error(f"日志检测到升级失败: {kw}")
                        return False

            # 步骤2: 检测关键日志（Otter WiFi）
            # 检测升级完成关键日志
            if 'firmware_upgrade_completed' in content:
                self.logger.info(f"检测到{device_name} WiFi升级完成关键日志: firmware_upgrade_completed")
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi：日志确认升级完成", success=True)
                return True

            # 检测设备重连关键日志 - 和S1/X1一致，检测到设备重新上线日志后直接确认成功
            reconnect_log_patterns = [
                'OnDeviceConnect',
                'Device connected:1 scannerpid=SCANNER_OTTER',
                'Device connected:2 SCANNER_OTTER',
            ]
            if any(pattern in content for pattern in reconnect_log_patterns):
                self.logger.info(f"检测到{device_name} WiFi设备重连关键日志: OnDeviceConnect/Device connected")
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi：日志确认设备已重连", success=True)
                return True

            # 步骤3: 检测UI气泡（只要没检测到就继续检测）
            ui_detect_time = None
            if not ui_detected:
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(exists, upgrade_success_template)
                        ui_result = future.result(timeout=3)
                    if ui_result:
                        ui_detected = True
                        ui_detect_time = time.time()
                        self.logger.info("检测到升级成功气泡（UI），等待设备重连...")
                except concurrent.futures.TimeoutError:
                    pass
                except Exception as e:
                    self.logger.warning(f"UI检测异常: {e}")

            # 步骤4: 检测Otter模组重连
            should_check_reconnect = False
            if ui_detected:
                # 记录首次UI检测到的时间
                if not hasattr(self, '_otter_ui_detected_time'):
                    self._otter_ui_detected_time = time.time()

                # 等待至少10秒后再检查重连（和X1/S1保持一致）
                if time.time() - self._otter_ui_detected_time >= 10:
                    should_check_reconnect = True
                    self.logger.info(f"开始检查{device_name}模组重连（已等待{int(time.time() - self._otter_ui_detected_time)}秒）...")

            if should_check_reconnect:
                self.log_manager.refresh_latest_log_dir()

                # 重点：只读取新增的日志内容（升级确认时间之后的），避免历史日志干扰
                if upgrade_confirm_time:
                    # 使用升级确认时间作为起点，读取之后的新日志
                    new_log_content = self.log_manager.read_log_since_time(upgrade_confirm_time)
                else:
                    new_log_content = self.log_manager.read_new_app_log()

                # 步骤4.1: 检测新增日志中的关键日志 - 设备重连日志
                # 日志特征: "OnDeviceConnect" 或 "Device connected:1 scannerpid=SCANNER_OTTER"
                reconnect_log_patterns = [
                    'OnDeviceConnect',
                    'Device connected:1 scannerpid=SCANNER_OTTER',
                    'Device connected:2 SCANNER_OTTER',
                ]
                # 只检测新增日志中是否有重连日志
                has_reconnect_log = any(pattern in new_log_content for pattern in reconnect_log_patterns)

                # 步骤4.2: 检测新增日志中的断开日志，判断是否还在升级过程中
                disconnect_patterns = ['OnDeviceDisconnect', 'No device found']
                has_disconnect_log = any(pattern in new_log_content for pattern in disconnect_patterns)

                # 步骤4.3: 从新增日志中提取最新的设备状态
                # 只从新增日志中提取，避免历史数据干扰
                new_scanner_pids = re.findall(r'scannerPid:([A-Za-z_0-9]+)', new_log_content)
                new_wifi_bridge_pids = re.findall(r'wifiBridgePid:([A-Za-z_0-9]+)', new_log_content)
                current_scanner = new_scanner_pids[-1] if new_scanner_pids else None
                current_wifi_bridge = new_wifi_bridge_pids[-1] if new_wifi_bridge_pids else None

                # 只有当新增日志中有重连关键日志时，才认为重连成功
                if not otter_reconnected:
                    if has_reconnect_log:
                        otter_reconnected = True
                        self.logger.info(f"✓ 检测到{device_name} WiFi设备重连")
                    elif has_disconnect_log:
                        # 设备还在断开状态，继续等待
                        pass

            # 步骤5: UI检测到 + Otter模组已重连，认为升级成功
            if ui_detected and otter_reconnected:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi：UI检测成功 + {device_name}模组已重连", success=True)
                return True

            # 步骤6: 兜底方案 - UI未检测到或重连未检测到时，超时前启用
            if not otter_reconnected and elapsed >= timeout - 5:
                self.logger.info(f"{device_name} WiFi：超时前启用日志版本验证兜底方案...")

                if expected_version and upgrade_confirm_time:
                    actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
                    self.logger.info(f"兜底方案 - 实际版本: {actual_version}, 预期版本: {expected_version}")

                    if actual_version == expected_version:
                        self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                        self.logger.result(f"{device_name} WiFi日志兜底确认：固件版本匹配", success=True)
                        return True

            # 每 5 秒输出一次等待状态
            if time.time() - last_check_time >= 5:
                remaining = timeout - elapsed
                status = []
                if ui_detected:
                    status.append("UI OK")
                if otter_reconnected:
                    status.append("已重连")
                status_str = ", ".join(status) if status else "等待中"
                self.logger.info(f"{device_name} WiFi升级进行中 [{status_str}]，已等待 {int(elapsed)}s，剩余 {int(remaining)}s...")
                last_check_time = time.time()

            sleep(1)  # Otter升级较快，使用1秒间隔检测

        # 超时后最后一次兜底尝试
        self.logger.warning(f"{device_name} WiFi重连检测超时，尝试日志版本验证...")
        if expected_version and upgrade_confirm_time:
            actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
            if actual_version == expected_version:
                self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result(f"{device_name} WiFi超时后兜底：固件版本匹配", success=True)
                return True

        self.logger.error(f"{device_name} WiFi升级检测超时（{timeout}秒）")
        return False

    def _wait_for_pika_upgrade(self, firmware_path: str, device_model: str = None, upgrade_confirm_time: str = None):
        """
        等待 Creality Pika 固件升级完成（USB 方案）

        Pika 升级流程与 Sermoon 类似，使用 UI 检测优先 + 日志验证模式。
        根据 skill 方案：0-60秒日志检测，60-160秒UI气泡，160秒后兜底

        Args:
            firmware_path: 固件文件路径（用于兜底方案获取预期版本）
            device_model: 设备型号
            upgrade_confirm_time: 点击升级确认按钮的时间（用于日志版本验证）

        Returns:
            bool: 升级是否成功完成
        """
        import concurrent.futures

        timeout = self.app_config['timeouts'].get('sermoon_upgrade', 360)

        self.logger.info(f"开始 Pika 升级检测（超时: {timeout}秒）...")

        start_time = time.time()
        last_check_time = start_time
        self._upgrade_success_time = None

        # 重置日志位置
        self.log_manager.refresh_latest_log_dir()
        self.log_manager.reset_log_position()

        # 获取预期版本号
        expected_version = None
        match = re.search(r'(\d+\.\d+\.\d+)', Path(firmware_path).name)
        if match:
            expected_version = match.group(1)
            self.logger.info(f"预期版本: {expected_version}")

        # UI气泡检测模板
        upgrade_success_template = Template(self.images['upgrade_success'], threshold=self.threshold)

        # 升级失败关键字
        fail_keywords = ['UpgradeFailed', 'Upgrade failed', 'upgrade failed']

        # 从配置读取Pika各阶段时间阈值（提供默认值）
        pika_config = self.app_config.get('upgrade_stages', {}).get('pika', {})
        log_check_end = pika_config.get('log_check_end', 60)
        ui_check_end = pika_config.get('ui_check_end', 160)
        fallback_time = pika_config.get('fallback_time', 160)
        log_stable_wait = pika_config.get('log_stable_wait', 10)

        self.logger.info(f"Pika模组：0-{log_check_end}秒日志检测，{log_check_end}-{ui_check_end}秒UI气泡，{fallback_time}秒后兜底")

        ui_detected = False
        fallback_triggered = False

        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            self.log_manager.refresh_latest_log_dir()
            content = self.log_manager.read_new_app_log()

            # 步骤1: 检测日志失败关键字
            if elapsed < log_check_end and content:
                for kw in fail_keywords:
                    if kw in content:
                        self.logger.error(f"Pika日志检测到升级失败: {kw}")
                        return False

            # 步骤2: 检测UI气泡
            if not ui_detected and log_check_end <= elapsed < ui_check_end:
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(exists, upgrade_success_template)
                        ui_result = future.result(timeout=3)
                    if ui_result:
                        ui_detected = True
                        self.logger.info("检测到升级成功气泡（UI）")
                except concurrent.futures.TimeoutError:
                    pass
                except Exception as e:
                    self.logger.warning(f"UI检测异常: {e}")

            # 步骤3: 兜底方案
            if not ui_detected and not fallback_triggered and elapsed >= fallback_time:
                self.logger.info(f"Pika模组：{fallback_time}秒未检测到气泡，启用日志版本验证兜底方案...")
                fallback_triggered = True

                if expected_version and upgrade_confirm_time:
                    actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
                    self.logger.info(f"Pika兜底方案 - 实际版本: {actual_version}, 预期版本: {expected_version}")

                    if actual_version == expected_version:
                        self._upgrade_success_time = time.strftime('%Y-%m-%d %H:%M:%S')
                        self.logger.result("Pika日志兜底确认：固件版本匹配", success=True)
                        return True

            # 步骤4: UI已检测到，等待日志稳定后再验证
            if ui_detected:
                self.logger.info("Pika：UI检测到升级成功，等待日志稳定...")

                # 等待日志稳定
                for i in range(log_stable_wait):
                    sleep(1)

                # 刷新日志并重新读取
                self.log_manager.refresh_latest_log_dir()
                self.log_manager.reset_log_position()
                content = self.log_manager.read_new_app_log()

                # 查找升级成功关键字
                if content:
                    sermon_success_keywords = [
                        "UpgradeCompletedSuccess",
                        "Upgrade Success",
                        "OnDeviceUpgradeSuccess"
                    ]
                    for keyword in sermon_success_keywords:
                        if keyword in content:
                            lines = content.splitlines()
                            for line in reversed(lines):
                                if keyword in line:
                                    time_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                                    if time_match:
                                        self._upgrade_success_time = time_match.group(1)
                                        self.logger.info(f"记录升级时间点: {self._upgrade_success_time}")
                                    break
                            break

                    # 检查升级失败关键字
                    for kw in fail_keywords:
                        if kw in content:
                            self.logger.error(f"Pika日志检测到升级失败: {kw}")
                            return False

                # 验证版本号
                if expected_version and upgrade_confirm_time:
                    actual_version = self.log_manager.get_firmware_version_after_upgrade(upgrade_confirm_time)
                    self.logger.info(f"Pika版本验证 - 实际版本: {actual_version}, 预期版本: {expected_version}")
                    if actual_version != expected_version:
                        self.logger.error("Pika版本验证失败")
                        return False

                self._upgrade_success_time = self._upgrade_success_time or time.strftime('%Y-%m-%d %H:%M:%S')
                self.logger.result("Pika：UI检测到升级成功，日志验证通过", success=True)
                return True

            # 每 10 秒输出一次等待状态
            if time.time() - last_check_time >= 10:
                remaining = timeout - elapsed
                if elapsed < log_check_end:
                    status = "Pika日志检测中..."
                elif elapsed < ui_check_end:
                    status = "Pika等待UI气泡..."
                else:
                    status = "Pika兜底方案已触发"
                self.logger.info(f"Pika升级进行中 [{status}]，已等待 {int(elapsed)}s，剩余 {int(remaining)}s...")
                last_check_time = time.time()

            sleep(2)

        self.logger.error(f"Pika升级检测超时（{timeout}秒）")
        return False

    def _wait_for_pikawifi_reconnect(self, firmware_path: str, upgrade_confirm_time: str = None, timeout: int = 150, device_model: str = None):
        """
        等待 Pika 系列 WiFi 设备重新连接

        Pika WiFi 升级方案与 USB 一致，使用 UI 检测优先 + 日志验证。

        Args:
            firmware_path: 固件文件路径
            upgrade_confirm_time: 点击升级确认按钮的时间
            timeout: 超时时间（秒），默认150秒
            device_model: 设备型号

        Returns:
            bool: 升级是否成功完成
        """
        # Pika WiFi 方案与 USB 一致，直接复用 _wait_for_pika_upgrade
        self.logger.info("Pika WiFi 设备检测到，使用 Pika 升级方案")
        return self._wait_for_pika_upgrade(firmware_path, device_model, upgrade_confirm_time)
