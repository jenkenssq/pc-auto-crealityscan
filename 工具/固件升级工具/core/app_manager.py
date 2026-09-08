"""
CrealityScan应用管理模块
负责应用的启动、窗口管理等操作
"""

import sys
import time
import subprocess
from pathlib import Path
from airtest.core.api import connect_device, auto_setup

if sys.platform == "win32":
    from airtest.core.win.win import Windows


class AppManager:
    """CrealityScan应用管理器"""

    def __init__(self, app_config, logger):
        """
        初始化应用管理器

        Args:
            app_config: 应用配置字典
            logger: 日志记录器
        """
        self.app_config = app_config
        self.logger = logger
        self.app_name = app_config['app']['name']
        self.exe_path = app_config['app']['exe_path']
        self.window_title = app_config['app']['window_title']
        self.launch_timeout = app_config['app']['launch_timeout']
        self.device = None

    def connect_device(self):
        """连接本地设备（Windows / Mac）"""
        try:
            self.logger.info("正在连接本地设备...")
            auto_setup(__file__)

            if sys.platform == "darwin":
                self.device = connect_device("Mac:///")
                platform_name = "Mac"
            else:
                self.device = connect_device("Windows:///")
                platform_name = "Windows"

            self.logger.result(f"{platform_name}设备连接成功", success=True)
            return True
        except Exception as e:
            self.logger.error(f"设备连接失败: {e}")
            return False

    def connect_windows(self):
        """连接Windows设备（兼容旧版调用）"""
        return self.connect_device()

    def is_app_running(self):
        """
        检查应用是否正在运行

        Returns:
            bool: 应用是否运行中
        """
        try:
            if sys.platform == "darwin":
                result = subprocess.run(
                    ['pgrep', '-f', self.app_name],
                    capture_output=True,
                    text=True
                )
                return result.returncode == 0
            else:
                result = subprocess.run(
                    ['tasklist', '/FI', f'IMAGENAME eq {self.app_name}.exe'],
                    capture_output=True,
                    text=True
                )
                return self.app_name in result.stdout
        except Exception as e:
            self.logger.warning(f"检查应用状态失败: {e}")
            return False

    def launch_app(self):
        """
        启动CrealityScan应用

        Returns:
            bool: 启动是否成功
        """
        try:
            # 检查应用是否已运行
            if self.is_app_running():
                self.logger.info(f"{self.app_name}已在运行中")
                return True

            # 检查可执行文件是否存在
            exe_path = Path(self.exe_path)
            if not exe_path.exists():
                self.logger.error(f"应用可执行文件不存在: {self.exe_path}")
                return False

            self.logger.step(f"正在启动{self.app_name}...")

            if sys.platform == "darwin":
                # Mac .app 启动方式
                subprocess.Popen(["open", "-a", self.app_name])
            else:
                subprocess.Popen([self.exe_path])

            # 等待应用启动
            start_time = time.time()
            while time.time() - start_time < self.launch_timeout:
                if self.is_app_running():
                    time.sleep(2)  # 额外等待窗口完全加载
                    self.logger.result(f"{self.app_name}启动成功", success=True)
                    return True
                time.sleep(1)

            self.logger.error(f"{self.app_name}启动超时")
            return False

        except Exception as e:
            self.logger.error(f"启动应用失败: {e}")
            return False

    def close_app(self):
        """
        关闭CrealityScan应用

        Returns:
            bool: 关闭是否成功
        """
        try:
            if not self.is_app_running():
                self.logger.info(f"{self.app_name}未运行")
                return True

            self.logger.step(f"正在关闭{self.app_name}...")

            if sys.platform == "darwin":
                subprocess.run(['pkill', '-9', self.app_name], capture_output=True)
            else:
                subprocess.run(
                    ['taskkill', '/F', '/IM', f'{self.app_name}.exe'],
                    capture_output=True
                )
            time.sleep(2)

            if not self.is_app_running():
                self.logger.result(f"{self.app_name}已关闭", success=True)
                return True
            else:
                self.logger.error(f"{self.app_name}关闭失败")
                return False

        except Exception as e:
            self.logger.error(f"关闭应用失败: {e}")
            return False
