"""
截图工具模块
提供截图保存和管理功能
"""

import os
from datetime import datetime
from pathlib import Path
from airtest.core.api import snapshot


class ScreenshotHelper:
    """截图辅助类"""

    def __init__(self, screenshot_dir="screenshots"):
        """
        初始化截图助手

        Args:
            screenshot_dir: 截图保存目录
        """
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def take_screenshot(self, name="screenshot", description=""):
        """
        截取当前屏幕并保存

        Args:
            name: 截图文件名（不含扩展名）
            description: 截图描述

        Returns:
            str: 截图文件路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{name}_{timestamp}.png"
        filepath = self.screenshot_dir / filename

        try:
            # 使用Airtest的snapshot功能截图
            snapshot(filename=str(filepath), msg=description)
            return str(filepath)
        except Exception as e:
            print(f"截图失败: {e}")
            return None

    def take_step_screenshot(self, step_name):
        """
        截取测试步骤截图

        Args:
            step_name: 步骤名称

        Returns:
            str: 截图文件路径
        """
        return self.take_screenshot(name=f"step_{step_name}", description=f"测试步骤: {step_name}")
