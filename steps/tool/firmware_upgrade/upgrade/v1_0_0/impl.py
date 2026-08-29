"""固件升级操作 Step（tool.firmware_upgrade.upgrade）。

沉淀自 工具/固件升级工具/core/firmware_handler.py：
进入设置→设备管理→选择固件文件→确认升级，按设备模组/连接方式等待升级成功
（UI 气泡 + 日志版本验证）并验证固件版本，最后关闭设置页返回首页。
实现复用源工具 FirmwareHandler，本文件只在 run() 内导入 Airtest 依赖。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from ..._tool_loader import build_upgrade_handler  # type: ignore
    except ImportError as exc:  # pragma: no cover - 包结构异常
        raise RuntimeError(f"固件升级 Step 加载失败：{exc}") from exc

    firmware_path = str(params.get("firmware_path") or "").strip()
    if not firmware_path:
        raise ValueError("缺少参数 firmware_path（固件文件路径）")
    if not Path(firmware_path).is_file():
        raise FileNotFoundError(f"固件文件不存在：{firmware_path}")

    handler = build_upgrade_handler(ctx, params)
    print(f"[JENS][firmware.upgrade] start firmware={firmware_path}")

    success, screenshot_path = handler.upgrade_firmware(firmware_path)
    if not success:
        raise RuntimeError(f"固件升级失败：{firmware_path}")

    return {
        "success": True,
        "firmware_path": firmware_path,
        "screenshot": screenshot_path,
    }
