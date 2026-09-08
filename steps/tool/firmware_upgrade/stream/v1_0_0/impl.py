"""固件开流操作 Step（tool.firmware_upgrade.stream）。

沉淀自 工具/固件升级工具/core/stream_handler.py：
按设备模组自动路由开流流程（Pika 专用 / 蓝色线激光双流 / 散斑单流），
等待开流、帧数达标并返回首页。实现复用源工具 StreamHandler，
本文件只在 run() 内导入 Airtest 依赖。
"""

from __future__ import annotations

from typing import Any, Dict


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from ..._tool_loader import build_stream_handler  # type: ignore
    except ImportError as exc:  # pragma: no cover - 包结构异常
        raise RuntimeError(f"固件升级 Step 加载失败：{exc}") from exc

    phase = str(params.get("phase") or "第一次").strip() or "第一次"
    handler = build_stream_handler(ctx, params)
    print(f"[JENS][firmware.stream] start phase={phase}")

    success, screenshot_path, frame_data = handler.start_stream(phase=phase)
    if not success:
        raise RuntimeError(f"开流操作失败（phase={phase}）")

    result: Dict[str, Any] = {
        "success": True,
        "phase": phase,
        "screenshot": screenshot_path,
    }
    if isinstance(frame_data, dict) and frame_data:
        result["frame_data"] = frame_data
    return result
