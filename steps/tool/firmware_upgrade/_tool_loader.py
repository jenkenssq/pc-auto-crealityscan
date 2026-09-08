"""固件升级工具加载辅助模块（平台内部 Step 共用）。

固件升级工具体量较大（Airtest 框架 + 日志分析 + 多设备分阶段升级逻辑），
平台 Step 采用“内部封装 + 复用源工具实现”的方式沉淀：
- Step 位于 steps/tool/firmware_upgrade，具备平台 Step 的标准接口（run(ctx, params)）
- 运行时定位 工具/固件升级工具 目录（与平台侧边栏工具一致），加载其
  app_config.yaml / device_config.yaml 与 core 模块
- 本模块只在 run() 内做重量级导入（yaml / airtest / core），保证未安装
  Airtest 时 steps 仍可被平台扫描与 import

定位优先级：JENS_FIRMWARE_UPGRADE_ROOT 环境变量 > 项目根 工具/固件升级工具。
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def resolve_tool_root() -> Path:
    """定位固件升级工具根目录（工具/固件升级工具）。"""
    configured = os.getenv("JENS_FIRMWARE_UPGRADE_ROOT", "").strip()
    candidates = [Path(configured).expanduser()] if configured else []
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        candidates.append(parent / "工具" / "固件升级工具")
        candidates.append(parent / "固件升级工具")
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate.is_dir():
                return candidate.resolve()
        except OSError:
            continue
    raise RuntimeError(
        "未找到固件升级工具目录（工具/固件升级工具）。"
        "请确认该目录存在，或设置环境变量 JENS_FIRMWARE_UPGRADE_ROOT。"
    )


def _find_config(tool_root: Path, name: str) -> Dict[str, Any]:
    import yaml  # 工具依赖；仅在运行时导入

    for candidate in (tool_root / name, tool_root / "config" / name):
        try:
            if candidate.is_file():
                data = yaml.safe_load(candidate.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (OSError, yaml.YAMLError) as exc:  # type: ignore[attr-defined]
            raise RuntimeError(f"固件升级工具配置解析失败：{candidate}（{exc}）") from exc
    raise RuntimeError(f"固件升级工具缺少配置文件：{name}")


def _pick_log_dir(ctx: Dict[str, Any], params: Dict[str, Any]) -> Optional[str]:
    """日志目录优先级：params.log_dir > 用例 case.app.log_dir > None（交给工具配置）。"""
    value = str(params.get("log_dir") or "").strip()
    if value:
        return value
    case = ctx.get("case") if isinstance(ctx.get("case"), dict) else {}
    app = case.get("app") if isinstance(case.get("app"), dict) else {}
    value = str(app.get("log_dir") or "").strip()
    return value or None


class _StepLogger:
    """轻量日志器：把工具内部日志转发到平台 stdout（工具 Logger 依赖 colorlog，此处不引入）。"""

    def __init__(self, prefix: str = "[JENS][firmware]") -> None:
        self._prefix = prefix

    def _emit(self, level: str, message: str) -> None:
        print(f"{self._prefix}[{level}] {message}", flush=True)

    def debug(self, message: str) -> None:
        self._emit("DEBUG", message)

    def info(self, message: str) -> None:
        self._emit("INFO", message)

    def warning(self, message: str) -> None:
        self._emit("WARNING", message)

    def error(self, message: str) -> None:
        self._emit("ERROR", message)

    def step(self, message: str) -> None:
        self._emit("STEP", message)

    def result(self, message: str, success: bool = True) -> None:
        self._emit("RESULT" if success else "FAIL", message)


class _StepScreenshot:
    """轻量截图助手：把工具截图输出到平台运行目录 screenshots/。"""

    def __init__(self, run_dir: Path) -> None:
        self._dir = Path(run_dir) / "screenshots"
        self._dir.mkdir(parents=True, exist_ok=True)

    def take_step_screenshot(self, step_name: str) -> Optional[str]:
        try:
            from airtest.core.api import snapshot  # type: ignore
        except Exception as exc:  # pragma: no cover - 依赖缺失
            print(f"[JENS][firmware] 截图失败（未安装 Airtest？）：{exc}", flush=True)
            return None
        safe = re.sub(r"[^\w\-.]+", "_", str(step_name or "screenshot"))
        path = self._dir / f"{safe}_{datetime.now():%Y%m%d_%H%M%S}.png"
        try:
            snapshot(filename=str(path), msg=str(step_name))
            return str(path)
        except Exception as exc:  # pragma: no cover - 截图接口异常
            print(f"[JENS][firmware] 截图失败：{exc}", flush=True)
            return None


def _ensure_tool_importable(tool_root: Path) -> None:
    root = str(tool_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def build_stream_handler(ctx: Dict[str, Any], params: Dict[str, Any]):
    """构建开流处理器 StreamHandler（在 run() 内调用，Airtest 依赖此时才加载）。"""
    tool_root = resolve_tool_root()
    app_config = _find_config(tool_root, "app_config.yaml")
    _ensure_tool_importable(tool_root)

    from core.stream_handler import StreamHandler  # 工具内部依赖，运行时导入

    run_dir = Path(str(ctx.get("run_dir") or Path.cwd()))
    handler = StreamHandler(
        app_config,
        _StepLogger(),
        _StepScreenshot(run_dir),
        log_dir=_pick_log_dir(ctx, params),
    )
    return handler


def build_upgrade_handler(ctx: Dict[str, Any], params: Dict[str, Any]):
    """构建固件升级处理器 FirmwareHandler（在 run() 内调用，Airtest 依赖此时才加载）。"""
    tool_root = resolve_tool_root()
    app_config = _find_config(tool_root, "app_config.yaml")
    device_config = _find_config(tool_root, "device_config.yaml")
    _ensure_tool_importable(tool_root)

    from core.firmware_handler import FirmwareHandler  # 工具内部依赖，运行时导入

    run_dir = Path(str(ctx.get("run_dir") or Path.cwd()))
    connection_mode = str(params.get("connection_mode") or "").strip() or None
    handler = FirmwareHandler(
        app_config,
        device_config,
        _StepLogger(),
        _StepScreenshot(run_dir),
        log_dir=_pick_log_dir(ctx, params),
        connection_mode=connection_mode,
    )
    return handler
