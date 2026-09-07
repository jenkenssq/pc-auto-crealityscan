from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from ..desktop_api import PyAutoGuiDesktop
from ..runtime import original_file, original_template_path


def desktop_from_ctx(ctx: Dict[str, Any]) -> PyAutoGuiDesktop:
    desktop = ctx.get("desktop")
    if not isinstance(desktop, PyAutoGuiDesktop):
        raise RuntimeError("desktop is missing from context")
    return desktop


def run_dir_from_ctx(ctx: Dict[str, Any]) -> Path:
    run_dir = Path(str(ctx.get("run_dir") or ".")).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def screenshot_path(ctx: Dict[str, Any], stem: str) -> Path:
    step_index = int(ctx.get("step_index") or 0)
    path = run_dir_from_ctx(ctx) / "screenshots" / f"step{step_index:03d}_{stem}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def template_path(step_group: str, step_name: str, filename: str) -> str:
    return str(original_template_path(step_group, step_name, filename))


def confidence_from_params(params: Dict[str, Any], default: float = 0.9) -> float:
    raw = params.get("confidence", default)
    return float(raw if raw is not None else default)


def bool_param(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return default


def float_param(params: Dict[str, Any], key: str, default: float) -> float:
    value = params.get(key, default)
    try:
        return float(value)
    except Exception:
        return float(default)


def int_param(params: Dict[str, Any], key: str, default: int) -> int:
    value = params.get(key, default)
    try:
        return int(value)
    except Exception:
        return int(default)


def normalize_preset(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def load_presets() -> List[dict]:
    raw = json.loads(original_file("steps/crealityscan/configure_scan_params/v1_0_0/presets.json").read_text(encoding="utf-8"))
    presets = raw.get("presets") if isinstance(raw, dict) else None
    return presets if isinstance(presets, list) else []


def resolve_preset(preset_input: str, presets: List[dict]) -> dict:
    needle = normalize_preset(preset_input)
    if not needle:
        raise RuntimeError("params.preset is required")
    alias_map: Dict[str, dict] = {}
    for preset in presets:
        if not isinstance(preset, dict):
            continue
        aliases = preset.get("aliases") if isinstance(preset.get("aliases"), list) else []
        for value in [preset.get("key"), preset.get("name"), *aliases]:
            key = normalize_preset(str(value or ""))
            if key:
                alias_map.setdefault(key, preset)
    if needle in alias_map:
        return alias_map[needle]
    for key, preset in alias_map.items():
        if needle and needle in key:
            return preset
    raise RuntimeError(f"Preset not found: {preset_input}")


def reset_mouse_hover(ctx: Dict[str, Any], params: Dict[str, Any]) -> None:
    desktop = desktop_from_ctx(ctx)
    safe_x = int_param(params, "mouse_safe_x", 10)
    safe_y = int_param(params, "mouse_safe_y", 10)
    move_duration_sec = float_param(params, "mouse_safe_move_duration_sec", 0.35)
    sleep_sec = float_param(params, "mouse_safe_sleep_sec", 0.3)
    desktop.move_mouse(safe_x, safe_y, duration_sec=move_duration_sec)
    desktop.sleep(sleep_sec)

