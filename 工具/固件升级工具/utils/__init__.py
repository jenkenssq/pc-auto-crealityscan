"""
工具模块初始化文件
"""

import sys
import yaml
from pathlib import Path
from .logger import Logger
from .screenshot import ScreenshotHelper

__all__ = ['Logger', 'ScreenshotHelper', 'get_resource_path', 'get_base_dir', 'load_app_config']


def get_resource_path(relative_path: str) -> str:
    """
    获取资源文件的绝对路径，兼容源码运行和打包运行

    Args:
        relative_path: 相对路径，如 'resources/images/home/new_project.png'

    Returns:
        str: 资源文件的绝对路径
    """
    # 打包后资源目录
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).parent.parent

    return str(base_dir / relative_path)


def get_base_dir() -> Path:
    """
    获取基础目录，兼容源码运行和打包运行
    打包后返回 exe 所在目录，源码运行返回项目根目录

    Returns:
        Path: 基础目录路径
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent


def load_app_config(config_name: str = "app_config.yaml") -> dict:
    """
    加载配置文件，优先从外部目录读取，打包后可直接修改无需重打包

    加载顺序：
    1. exe同级的 config/ 目录（外部配置，优先级最高）
    2. 打包内部的 config/ 目录（默认配置）

    Args:
        config_name: 配置文件名，默认 app_config.yaml

    Returns:
        dict: 配置字典
    """
    base_dir = get_base_dir()

    # 外部配置文件路径（exe同级目录）
    external_config = base_dir / config_name
    # 打包内部配置文件路径
    internal_config_dir = base_dir / "config"
    if getattr(sys, 'frozen', False):
        internal_config = Path(sys._MEIPASS) / "config" / config_name
    else:
        internal_config = internal_config_dir / config_name

    # 优先使用外部配置
    if external_config.exists():
        with open(external_config, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        print(f"[配置] 使用外部配置文件: {external_config}")
        return config

    # 其次使用内部打包配置
    if internal_config.exists():
        with open(internal_config, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        print(f"[配置] 使用内置配置文件: {internal_config}")
        return config

    raise FileNotFoundError(f"配置文件未找到: {external_config} 或 {internal_config}")
