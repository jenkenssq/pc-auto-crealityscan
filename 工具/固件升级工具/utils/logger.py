"""
日志管理模块
提供统一的日志记录功能，支持控制台和文件输出
"""

import os
import logging
from datetime import datetime
from pathlib import Path
import colorlog


class Logger:
    """日志管理器"""

    def __init__(self, name="CrealityScan_Test", log_dir="logs", level=logging.INFO):
        """
        初始化日志管理器

        Args:
            name: 日志记录器名称
            log_dir: 日志文件保存目录
            level: 日志级别
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.handlers.clear()  # 清除已有的处理器

        # 创建日志目录
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 生成日志文件名（按日期）
        log_filename = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.log_file = self.log_dir / log_filename

        # 配置控制台处理器（带颜色）
        self._setup_console_handler()

        # 配置文件处理器
        self._setup_file_handler()

    def _setup_console_handler(self):
        """配置控制台日志处理器（彩色输出）"""
        console_handler = colorlog.StreamHandler()
        console_handler.setLevel(logging.DEBUG)

        # 彩色日志格式
        color_formatter = colorlog.ColoredFormatter(
            '%(log_color)s[%(asctime)s] [%(levelname)s]%(reset)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        console_handler.setFormatter(color_formatter)
        self.logger.addHandler(console_handler)

    def _setup_file_handler(self):
        """配置文件日志处理器"""
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        # 文件日志格式
        file_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

    def debug(self, message):
        """记录DEBUG级别日志"""
        self.logger.debug(message)

    def info(self, message):
        """记录INFO级别日志"""
        self.logger.info(message)

    def warning(self, message):
        """记录WARNING级别日志"""
        self.logger.warning(message)

    def error(self, message):
        """记录ERROR级别日志"""
        self.logger.error(message)

    def critical(self, message):
        """记录CRITICAL级别日志"""
        self.logger.critical(message)

    def step(self, message):
        """记录测试步骤（INFO级别，带特殊标记）"""
        self.logger.info(f"【步骤】 {message}")

    def result(self, message, success=True):
        """记录测试结果"""
        if success:
            self.logger.info(f"✓ {message}")
        else:
            self.logger.error(f"✗ {message}")
