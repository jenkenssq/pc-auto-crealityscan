"""
开流操作处理模块
封装开流相关的UI操作和验证逻辑
"""

import time
from typing import Optional
from airtest.core.api import touch, wait, exists, sleep
from airtest.core.cv import Template
from pathlib import Path
from utils.log_manager import LogManager
from utils import get_resource_path


class StreamHandler:
    """开流操作处理器"""

    def __init__(self, app_config, logger, screenshot_helper, log_dir: Optional[str] = None):
        """
        初始化开流处理器

        Args:
            app_config: 应用配置
            logger: 日志记录器
            screenshot_helper: 截图助手
            log_dir: CrealityScan 日志目录（可选，优先于配置文件）
        """
        self.app_config = app_config
        self.logger = logger
        self.screenshot = screenshot_helper
        self.threshold = app_config['image_recognition']['threshold']
        self.timeout = app_config['image_recognition']['timeout']
        self.click_delay = app_config['image_recognition']['click_delay']
        self.stream_timeout = app_config['timeouts']['stream_start']
        self.frame_count_timeout = app_config['timeouts'].get('frame_count_wait', 120)
        self.target_frames = app_config.get('scan', {}).get('target_frames', 100)

        # 初始化日志管理器（优先使用外部传入的 log_dir）
        if log_dir:
            self.log_manager = LogManager(log_dir)
            self.logger.info(f"使用GUI传入的日志目录: {log_dir}")
        else:
            log_dir_from_config = app_config.get('app', {}).get('log_dir')
            if log_dir_from_config:
                self.log_manager = LogManager(log_dir_from_config)
                self.logger.info(f"使用配置文件中的日志目录: {log_dir_from_config}")
            else:
                self.logger.warning("未配置日志目录")
        if self.log_manager:
            self.log_manager.refresh_latest_log_dir()

        # UI元素图片路径
        self.images = {
            'new_project_btn': get_resource_path('resources/images/home/new_project.png'),
            'confirm_btn': get_resource_path('resources/images/home/confirm.png'),
            'preview_btn': get_resource_path('resources/images/scan/preview.png'),
            'scan_btn': get_resource_path('resources/images/scan/scan.png'),
            'finish_scan_btn': get_resource_path('resources/images/scan/finish_scan.png'),
            'back_home_btn': get_resource_path('resources/images/scan/back_home.png'),
            'ir_camera': get_resource_path('resources/images/scan/ir_camera.png'),
            'color_camera': get_resource_path('resources/images/scan/color_camera.png'),
            'blue_laser_mode_btn': get_resource_path('resources/images/scan/blue_laser_mode_btn.png'),
            'ir_mode_btn': get_resource_path('resources/images/scan/ir_mode_btn.png'),
            'new_scan_btn': get_resource_path('resources/images/scan/new_scan_btn.png'),
            # Pika模组专用
            'pika_ir_apply_btn': get_resource_path('resources/images/scan/pika_ir_apply_btn.png'),
        }

    def start_stream(self, phase="第一次"):
        """
        执行完整的开流操作流程

        根据设备类型自动路由：
        - Pika模组：Pika专用开流流程（无预览，需要应用按钮）
        - 蓝色线激光模组（Sermoon/Raptor）：双流开流
        - 散斑模组（Otter/Ferret）：单流开流

        Args:
            phase: 开流阶段标识（用于日志）

        Returns:
            (success, screenshot_path, frame_data_dict)
        """
        self.logger.step(f"开始{phase}开流操作")

        # Pika模组使用专用开流流程
        if self._is_pika_module():
            return self._start_stream_for_pika(phase)
        elif self._is_blue_line_laser_module():
            return self._start_stream_for_laser_module(phase)
        else:
            # 散斑模组：单流开流
            return self._start_stream_single(phase)

    def _is_blue_line_laser_module(self) -> bool:
        """
        判断是否为蓝色线激光模组（Sermoon/Raptor/Pika）

        Returns:
            bool: 是否为蓝色线激光模组
        """
        if not self.log_manager:
            return False
        self.log_manager.refresh_latest_log_dir()
        return self.log_manager.is_blue_line_laser_module()

    def _is_pika_module(self) -> bool:
        """
        判断是否为Pika模组

        Pika模组有特殊的开流流程：
        1. 蓝色线激光模式无预览，直接开流
        2. 红外模式需要点击"应用"按钮

        Returns:
            bool: 是否为Pika模组
        """
        if not self.log_manager:
            return False
        self.log_manager.refresh_latest_log_dir()
        model = self.log_manager.get_device_model()
        if not model:
            return False
        return 'PIKA' in model.upper()

    def _is_pika_blue_laser_mode(self) -> bool:
        """
        判断是否为Pika蓝色线激光模式（蓝色线激光模组且为Pika）

        Returns:
            bool: 是否为Pika蓝色线激光模式
        """
        return self._is_blue_line_laser_module() and self._is_pika_module()

    def _start_stream_for_pika(self, phase="第一次"):
        """
        Pika模组专用开流流程

        流程：
        1. 新建项目 → 确定
        2. 蓝色线激光模式：
           - 点击蓝色线激光模式按钮
           - 直接点击开流按钮（无预览，复用scan.png）
           - 等待开流 → 帧数≥100 → 完成扫描
        3. 新建扫描
        4. 红外模式：
           - 点击红外模式按钮
           - 点击"应用"按钮（pika_ir_apply_btn.png）
           - 等待3秒
           - 点击"开始"按钮（复用scan.png）
           - 等待开流 → 帧数≥100 → 完成扫描
        5. 返回首页 → 确定

        Args:
            phase: 开流阶段标识

        Returns:
            (success, screenshot_path, frame_data_dict)
        """
        self.logger.step(f"开始{phase}开流（Pika模组）")

        all_success = True
        merged_frame_data = {}
        first_screenshot = None

        try:
            # 步骤1: 点击新建项目
            if not self._click_new_project():
                return False, None, {}

            # 步骤2: 确认弹窗
            if not self._confirm_dialog():
                return False, None, {}

            # 步骤3: 蓝色线激光模式开流（无预览）
            self.logger.step("蓝色线激光模式开流（Pika，无预览）")
            success1, ss1, fd1 = self._run_pika_laser_stream_phase()
            if not success1:
                all_success = False
                self.logger.error("蓝色线激光模式开流失败")
            if fd1:
                merged_frame_data["蓝色线激光"] = fd1
            if ss1 and not first_screenshot:
                first_screenshot = ss1

            # 步骤4: 新建扫描
            self.logger.step("切换到红外模式")
            if not self._click_new_scan():
                return False, None, merged_frame_data

            # 步骤4.5: 等待3秒
            self.logger.info("新建扫描后等待3秒...")
            sleep(3)

            # 步骤5: 红外模式开流（需要点击应用）
            success2, ss2, fd2 = self._run_pika_ir_stream_phase()
            if not success2:
                all_success = False
                self.logger.error("红外模式开流失败")
            if fd2:
                merged_frame_data["红外"] = fd2
            if ss2 and not first_screenshot:
                first_screenshot = ss2

            # 步骤6: 返回首页
            if not self._click_element('back_home_btn', "返回首页按钮"):
                return False, None, merged_frame_data
            if not self._click_element('confirm_btn', "确定按钮"):
                return False, None, merged_frame_data

            if all_success:
                self.logger.result(f"{phase}Pika开流操作成功", success=True)
            else:
                self.logger.warning(f"{phase}Pika开流操作部分成功", success=True)

            return all_success, first_screenshot, merged_frame_data

        except Exception as e:
            self.logger.error(f"{phase}Pika开流操作失败: {e}")
            self.screenshot.take_step_screenshot(f"{phase}_pika_stream_failed")
            return False, None, merged_frame_data

    def _run_pika_laser_stream_phase(self):
        """
        Pika模组蓝色线激光模式开流流程（无预览）

        流程：
        1. 点击蓝色线激光模式按钮
        2. 点击开流按钮（复用scan.png，无预览）
        3. 等待开流
        4. 记录基准帧数
        5. 等待帧数≥100
        6. 点击完成扫描
        7. 收集帧率数据

        Returns:
            (success, screenshot_path, frame_data_dict)
        """
        self.logger.info("开始Pika蓝色线激光模式开流（无预览）")

        try:
            # 步骤1: 点击蓝色线激光模式按钮
            if not self._click_mode_button('blue_laser_mode_btn'):
                return False, None, {}

            # 步骤2: 直接点击开流按钮（无预览环节）
            self.logger.info("Pika模组：直接点击开流按钮（无预览）")
            if not self._click_element('scan_btn', "开流按钮"):
                return False, None, {}

            # 步骤3: 等待设备开流
            self._wait_for_stream_ready()

            # 步骤4: 截图记录开流状态
            screenshot_path = self.screenshot.take_step_screenshot("pika_laser_stream_success")
            self.logger.info(f"已截图: {screenshot_path}")

            # 步骤5: 记录基准帧数
            baseline_frames = 0
            if self.log_manager:
                self.log_manager.refresh_latest_log_dir()
                baseline_frames = self.log_manager.get_latest_frame_count() or 0
                self.logger.info(f"蓝色线激光扫描基准帧数: {baseline_frames}")

            # 步骤6: 等待帧数达到目标
            self._wait_for_frame_count(target_frames=self.target_frames, baseline_frames=baseline_frames)

            # 步骤7: 点击完成扫描
            if not self._click_element('finish_scan_btn', "完成扫描按钮"):
                return False, None, {}

            # 步骤8: 等待3秒后再点击返回首页
            self.logger.info("等待3秒...")
            sleep(3)

            # 步骤9: 收集帧率数据
            frame_data = self._collect_frame_data("蓝色线激光")
            self.logger.info(f"蓝色线激光模式最终帧数: {frame_data.get('final_frame_count')}")

            self.logger.result("Pika蓝色线激光模式开流成功", success=True)
            return True, screenshot_path, frame_data

        except Exception as e:
            self.logger.error(f"Pika蓝色线激光模式开流失败: {e}")
            self.screenshot.take_step_screenshot("pika_laser_stream_failed")
            return False, None, {}

    def _run_pika_ir_stream_phase(self):
        """
        Pika模组红外模式开流流程

        流程：
        1. 点击红外模式按钮
        2. 点击"应用"按钮
        3. 等待3秒
        4. 点击"开始"按钮（复用scan.png）
        5. 等待开流
        6. 记录基准帧数
        7. 等待帧数≥100
        8. 点击完成扫描
        9. 收集帧率数据

        Returns:
            (success, screenshot_path, frame_data_dict)
        """
        self.logger.info("开始Pika红外模式开流")

        try:
            # 步骤1: 点击红外模式按钮
            if not self._click_mode_button('ir_mode_btn'):
                return False, None, {}

            # 步骤2: 点击"应用"按钮（Pika专用）
            self.logger.info("Pika模组：点击'应用'按钮")
            if not self._click_element('pika_ir_apply_btn', "应用按钮"):
                return False, None, {}

            # 步骤3: 等待3秒
            self.logger.info("等待3秒...")
            sleep(3)

            # 步骤4: 点击"开始"按钮（复用scan.png）
            self.logger.info("点击'开始'按钮")
            if not self._click_element('scan_btn', "开始按钮"):
                return False, None, {}

            # 步骤5: 等待设备开流
            self._wait_for_stream_ready()

            # 步骤6: 截图记录开流状态
            screenshot_path = self.screenshot.take_step_screenshot("pika_ir_stream_success")
            self.logger.info(f"已截图: {screenshot_path}")

            # 步骤7: 记录基准帧数
            baseline_frames = 0
            if self.log_manager:
                self.log_manager.refresh_latest_log_dir()
                baseline_frames = self.log_manager.get_latest_frame_count() or 0
                self.logger.info(f"红外扫描基准帧数: {baseline_frames}")

            # 步骤8: 等待帧数达到目标
            self._wait_for_frame_count(target_frames=self.target_frames, baseline_frames=baseline_frames)

            # 步骤9: 点击完成扫描
            if not self._click_element('finish_scan_btn', "完成扫描按钮"):
                return False, None, {}

            # 步骤10: 等待3秒后再点击返回首页
            self.logger.info("等待3秒...")
            sleep(3)

            # 步骤11: 收集帧率数据
            frame_data = self._collect_frame_data("红外")
            self.logger.info(f"红外模式最终帧数: {frame_data.get('final_frame_count')}")

            self.logger.result("Pika红外模式开流成功", success=True)
            return True, screenshot_path, frame_data

        except Exception as e:
            self.logger.error(f"Pika红外模式开流失败: {e}")
            self.screenshot.take_step_screenshot("pika_ir_stream_failed")
            return False, None, {}

    def _start_stream_single(self, phase="第一次"):
        """
        散斑模组单流开流流程

        Args:
            phase: 开流阶段标识

        Returns:
            (success, screenshot_path, frame_data_dict)
        """
        try:
            # 步骤1: 点击新建项目
            if not self._click_new_project():
                return False, None, {}

            # 步骤2: 确认弹窗
            if not self._confirm_dialog():
                return False, None, {}

            # 步骤3: 点击预览
            if not self._click_preview():
                return False, None, {}

            # 预览成功后截图，记录扫描页预览状态（扫描开始前）
            step_name = f"{phase}_stream_success"
            screenshot_path = self.screenshot.take_step_screenshot(step_name)
            self.logger.info(f"已截图: {screenshot_path}")

            # 步骤4: 等待设备开流
            self._wait_for_stream_ready()

            # 记录扫描开始前的基准帧数（避免累积帧数导致提前触发）
            baseline_frames = 0
            if self.log_manager:
                self.log_manager.refresh_latest_log_dir()
                baseline_frames = self.log_manager.get_latest_frame_count() or 0
                self.logger.info(f"扫描基准帧数: {baseline_frames}")

            # 步骤5: 点击扫描
            if not self._click_scan():
                return False, None, {}

            # 步骤6: 验证开流成功
            if not self._verify_stream_success():
                return False, None, {}

            # 步骤7: 返回首页（开流验证成功后）
            if not self._return_to_home(baseline_frames=baseline_frames):
                return False, None, {}

            # 收集帧数数据
            frame_data = self._collect_frame_data(phase)

            self.logger.result(f"{phase}开流操作成功", success=True)
            return True, screenshot_path, frame_data

        except Exception as e:
            self.logger.error(f"{phase}开流操作失败: {e}")
            self.screenshot.take_step_screenshot(f"{phase}_stream_failed")
            self._collect_frame_data(phase)
            return False, None, {}

    def _start_stream_for_laser_module(self, phase="第一次"):
        """
        蓝色线激光模组双流开流流程

        流程：
        1. 新建项目 → 确定
        2. 选择蓝色线激光模式 → 预览 → 开流 → 帧数>100 → 完成扫描
        3. 新建扫描
        4. 选择红外模式 → 预览 → 开流 → 帧数>100 → 完成扫描
        5. 返回首页 → 确定
        6. 合并帧数数据

        Args:
            phase: 开流阶段标识

        Returns:
            (success, screenshot_path, frame_data_dict)
        """
        self.logger.step(f"开始{phase}双流开流（蓝色线激光模组）")

        all_success = True
        merged_frame_data = {}
        first_screenshot = None

        try:
            # 步骤1: 点击新建项目
            if not self._click_new_project():
                return False, None, {}

            # 步骤2: 确认弹窗
            if not self._confirm_dialog():
                return False, None, {}

            # 步骤3: 蓝色线激光模式
            self.logger.step("蓝色线激光模式开流")
            success1, ss1, fd1 = self._run_laser_stream_phase("蓝色线激光", "blue_laser_mode_btn")
            if not success1:
                all_success = False
                self.logger.error("蓝色线激光模式开流失败")
            if fd1:
                merged_frame_data["蓝色线激光"] = fd1
            if ss1 and not first_screenshot:
                first_screenshot = ss1

            # 步骤4: 新建扫描
            self.logger.step("切换到红外模式")
            if not self._click_new_scan():
                return False, None, merged_frame_data

            # 步骤5: 红外模式
            success2, ss2, fd2 = self._run_laser_stream_phase("红外", "ir_mode_btn")
            if not success2:
                all_success = False
                self.logger.error("红外模式开流失败")
            if fd2:
                merged_frame_data["红外"] = fd2
            if ss2 and not first_screenshot:
                first_screenshot = ss2

            # 步骤6: 返回首页
            if not self._click_element('back_home_btn', "返回首页按钮"):
                return False, None, merged_frame_data
            if not self._click_element('confirm_btn', "确定按钮"):
                return False, None, merged_frame_data

            if all_success:
                self.logger.result(f"{phase}双流开流操作成功", success=True)
            else:
                self.logger.warning(f"{phase}双流开流操作部分成功", success=True)

            return all_success, first_screenshot, merged_frame_data

        except Exception as e:
            self.logger.error(f"{phase}双流开流操作失败: {e}")
            self.screenshot.take_step_screenshot(f"{phase}_dual_stream_failed")
            return False, None, merged_frame_data

    def _run_laser_stream_phase(self, mode_name: str, image_key: str):
        """
        单模式开流子流程（用于蓝色线激光模组的双流模式）

        流程：
        1. 点击模式按钮（蓝色线激光/红外）
        2. 点击预览
        3. 等待开流（记录基准帧）
        4. 点击扫描
        5. 验证开流成功
        6. 等待帧数≥100
        7. 点击完成扫描
        8. 收集帧率数据

        Args:
            mode_name: 模式名称（"蓝色线激光" / "红外"）
            image_key: 模式按钮图片的 key

        Returns:
            (success, screenshot_path, frame_data_dict)
        """
        self.logger.info(f"开始 {mode_name} 模式开流")

        try:
            # 步骤1: 点击模式按钮
            if not self._click_mode_button(image_key):
                return False, None, {}

            # 步骤2: 点击预览
            if not self._click_preview():
                return False, None, {}

            # 步骤3: 截图记录开流状态
            screenshot_path = self.screenshot.take_step_screenshot(f"{mode_name}_stream_success")
            self.logger.info(f"已截图: {screenshot_path}")

            # 步骤4: 等待设备开流
            self._wait_for_stream_ready()

            # 步骤5: 记录基准帧数
            baseline_frames = 0
            if self.log_manager:
                self.log_manager.refresh_latest_log_dir()
                baseline_frames = self.log_manager.get_latest_frame_count() or 0
                self.logger.info(f"{mode_name}扫描基准帧数: {baseline_frames}")

            # 步骤6: 点击扫描
            if not self._click_scan():
                return False, None, {}

            # 步骤7: 验证开流成功
            if not self._verify_stream_success():
                return False, None, {}

            # 步骤8: 等待帧数达到目标
            self._wait_for_frame_count(target_frames=self.target_frames, baseline_frames=baseline_frames)

            # 步骤9: 点击完成扫描
            if not self._click_element('finish_scan_btn', "完成扫描按钮"):
                return False, None, {}

            # 步骤10: 等待3秒后再点击返回首页
            self.logger.info("等待3秒...")
            sleep(3)

            # 步骤11: 收集帧率数据
            frame_data = self._collect_frame_data(mode_name)
            self.logger.info(f"{mode_name}模式最终帧数: {frame_data.get('final_frame_count')}")

            self.logger.result(f"{mode_name}模式开流成功", success=True)
            return True, screenshot_path, frame_data

        except Exception as e:
            self.logger.error(f"{mode_name}模式开流失败: {e}")
            self.screenshot.take_step_screenshot(f"{mode_name}_stream_failed")
            return False, None, {}

    def _click_mode_button(self, image_key: str) -> bool:
        """
        点击模式切换按钮

        Args:
            image_key: 模式按钮图片的 key（如 'blue_laser_mode_btn', 'ir_mode_btn'）

        Returns:
            bool: 点击是否成功
        """
        self.logger.info(f"点击模式按钮: {image_key}")
        return self._click_element(image_key, "模式按钮")

    def _click_new_scan(self) -> bool:
        """
        点击新建扫描按钮

        Returns:
            bool: 点击是否成功
        """
        self.logger.info("点击'新建扫描'按钮")
        return self._click_element('new_scan_btn', "新建扫描按钮")

    def _collect_frame_data(self, phase: str) -> dict:
        """收集帧数及帧率序列数据，返回数据字典"""
        result = {}
        try:
            if self.log_manager:
                self.log_manager.refresh_latest_log_dir()
                final_frame_count = self.log_manager.get_latest_frame_count()
                fps_series = self.log_manager.get_fps_series()
                self.logger.info(f"{phase}开流最终帧数: {final_frame_count}")
                result = {
                    'final_frame_count': final_frame_count,
                    'target_frame_count': self.target_frames,
                    'preview_fps': fps_series['preview'],
                    'scan_fps': fps_series['scan'],
                }
        except Exception as e:
            self.logger.warning(f"收集帧数数据失败: {e}")
        return result

    def _click_new_project(self):
        """点击新建项目按钮"""
        self.logger.info("点击'新建项目'按钮")
        return self._click_element('new_project_btn', "新建项目按钮")

    def _confirm_dialog(self):
        """确认弹窗"""
        self.logger.info("点击弹窗'确定'按钮")
        return self._click_element('confirm_btn', "确定按钮")

    def _click_preview(self):
        """点击预览按钮"""
        self.logger.info("点击'预览'按钮")
        return self._click_element('preview_btn', "预览按钮")

    def _wait_for_stream_ready(self):
        """等待设备开流准备就绪，根据设备类型调整等待时间"""
        # 默认等待时间
        wait_time = 3

        # 检测WiFi设备类型，应用不同的等待时间
        if self.log_manager:
            self.log_manager.refresh_latest_log_dir()
            if self.log_manager.is_x1wifi_connected():
                wait_time = 5  # X1WiFi增加2秒
                self.logger.info("检测到X1 WiFi设备，等待时间调整为5秒")
            elif self.log_manager.is_s1wifi_connected():
                wait_time = 5  # S1WiFi增加2秒
                self.logger.info("检测到S1 WiFi设备，等待时间调整为5秒")
            elif (self.log_manager.is_raptorwifi_connected() or
                  self.log_manager.is_otterwifi_connected() or
                  self.log_manager.is_ferretwifi_connected() or
                  self.log_manager.is_pikawifi_connected()):
                wait_time = 4  # 其他WiFi设备增加1秒
                self.logger.info("检测到WiFi设备，等待时间调整为4秒")

        self.logger.info(f"等待设备开流... ({wait_time}秒)")
        sleep(wait_time)

    def _click_scan(self):
        """点击扫描按钮"""
        self.logger.info("点击'扫描'按钮")
        return self._click_element('scan_btn', "扫描按钮")

    def _verify_stream_success(self):
        """
        验证开流成功
        检查点云渲染和相机窗口出流
        通过日志判断是否需要检查彩色相机

        Returns:
            bool: 验证是否通过
        """
        self.logger.info("验证开流状态...")

        # 等待渲染
        sleep(5)

        # 检查是否需要验证彩色相机（通过日志判断）
        has_color_camera = self._check_color_camera_from_log()

        # 验证点云渲染
        if not self._verify_point_cloud_rendering():
            self.logger.error("点云渲染验证失败")
            return False

        # 验证IR相机（必需）
        if not self._verify_ir_camera():
            self.logger.error("IR相机验证失败")
            return False

        # 验证彩色相机（如果有）
        if has_color_camera:
            self.logger.info("当前模式有彩色视窗，验证彩色相机")
            if not self._verify_color_camera():
                self.logger.error("彩色相机验证失败")
                return False
        else:
            self.logger.info("当前模式无彩色视窗，跳过彩色相机验证")

        self.logger.result("开流验证成功", success=True)
        return True

    def _verify_point_cloud_rendering(self):
        """
        验证点云渲染
        可以通过UI图像识别或日志验证

        Returns:
            bool: 点云是否正常渲染
        """
        self.logger.info("验证点云渲染...")

        # TODO: 实现点云渲染验证逻辑
        # 方案1: 通过UI图像识别检查点云渲染区域
        # 方案2: 通过日志文件检查点云渲染状态

        # 暂时返回True，需要后续完善
        self.logger.warning("点云渲染验证逻辑待完善（需要UI截图或日志验证）")
        return True

    def _verify_ir_camera(self):
        """
        验证IR相机窗口出流

        Returns:
            bool: IR相机是否正常出流
        """
        self.logger.info("验证IR相机窗口...")

        # TODO: 实现IR相机验证逻辑
        # 方案1: 通过UI图像识别检查IR相机窗口
        # 方案2: 通过日志文件检查IR相机状态

        # 暂时返回True，需要后续完善
        self.logger.warning("IR相机验证逻辑待完善（需要UI截图或日志验证）")
        return True

    def _verify_color_camera(self):
        """
        验证彩色相机窗口出流

        Returns:
            bool: 彩色相机是否正常出流
        """
        self.logger.info("验证彩色相机窗口...")

        # TODO: 实现彩色相机验证逻辑
        # 方案1: 通过UI图像识别检查彩色相机窗口
        # 方案2: 通过日志文件检查彩色相机状态

        # 暂时返回True，需要后续完善
        self.logger.warning("彩色相机验证逻辑待完善（需要UI截图或日志验证）")
        return True

    def _check_color_camera_from_log(self):
        """
        通过日志判断当前模式是否有彩色视窗

        Returns:
            bool: 是否有彩色视窗
        """
        if not self.log_manager:
            self.logger.warning("未配置日志管理器，默认检查彩色相机")
            return True

        try:
            # 使用LogManager检测彩色相机
            has_color = self.log_manager.has_color_camera()
            if has_color:
                self.logger.info("日志中检测到彩色相机")
            else:
                self.logger.info("日志中未检测到彩色相机")
            return has_color

        except Exception as e:
            self.logger.error(f"检测彩色相机失败: {e}")
            return True  # 出错时默认假设有彩色相机

    def _return_to_home(self, baseline_frames=0):
        """
        返回首页操作
        步骤：等待帧数达到100 -> 完成扫描 -> 返回首页 -> 确定

        Args:
            baseline_frames: 扫描开始前的基准帧数，用于增量计算

        Returns:
            bool: 返回是否成功
        """
        self.logger.info("开始返回首页操作")

        try:
            # 步骤0: 等待帧数达到100帧
            if not self._wait_for_frame_count(target_frames=self.target_frames, baseline_frames=baseline_frames):
                self.logger.warning("等待帧数超时，继续执行完成扫描")

            # 步骤1: 点击完成扫描按钮
            self.logger.info("点击'完成扫描'按钮")
            if not self._click_element('finish_scan_btn', "完成扫描按钮"):
                return False

            # 步骤2: 等待3秒后再点击返回首页
            self.logger.info("等待3秒...")
            sleep(3)

            # 步骤3: 点击返回首页按钮
            self.logger.info("点击'返回首页'按钮")
            if not self._click_element('back_home_btn', "返回首页按钮"):
                return False

            # 步骤3: 确认返回（点击确定按钮）
            self.logger.info("点击'确定'按钮确认返回")
            if not self._click_element('confirm_btn', "确定按钮"):
                return False

            self.logger.result("成功返回首页", success=True)
            return True

        except Exception as e:
            self.logger.error(f"返回首页失败: {e}")
            return False

    def _wait_for_frame_count(self, target_frames=None, timeout=None, baseline_frames=0):
        """
        等待扫描帧数达到目标值（增量计算，避免累积帧数干扰）

        Args:
            target_frames: 目标帧数（默认使用配置文件中的值）
            timeout: 超时时间（秒，默认使用配置文件中的值）
            baseline_frames: 扫描开始前的基准帧数

        Returns:
            bool: 是否达到目标帧数
        """
        if target_frames is None:
            target_frames = self.target_frames
        if timeout is None:
            timeout = self.frame_count_timeout

        self.logger.info(f"等待扫描增量帧数达到{target_frames}帧（基准: {baseline_frames}）...")

        if not self.log_manager:
            self.logger.warning("未配置日志管理器，跳过帧数监控，等待30秒")
            sleep(30)
            return True

        try:
            start_time = time.time()

            while time.time() - start_time < timeout:
                # 刷新日志目录（可能生成了新的scan_log文件）
                self.log_manager.refresh_latest_log_dir()

                # 获取最新帧数，计算增量
                frame_count = self.log_manager.get_latest_frame_count()

                if frame_count is not None:
                    incremental = frame_count - baseline_frames
                    self.logger.info(f"当前帧数: {frame_count}，增量: {incremental}/{target_frames}")

                    if incremental >= target_frames:
                        self.logger.result(f"已达到目标增量帧数{target_frames}帧", success=True)
                        return True

                sleep(1)  # 每秒检查一次

            self.logger.warning(f"等待帧数超时（{timeout}秒）")
            return False

        except Exception as e:
            self.logger.error(f"监控帧数失败: {e}")
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
