from __future__ import annotations

from typing import Any, Dict

from ._common import bool_param, desktop_from_ctx, load_presets, resolve_preset, reset_mouse_hover


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    desktop = desktop_from_ctx(ctx)
    presets = load_presets()
    preset_input = str(params.get("preset") or "")
    preset = resolve_preset(preset_input, presets)
    delay_sec = float(params.get("delay_sec", 0.1) or 0.1)
    reset_after_touch = bool_param(params.get("reset_mouse_after_touch"), True)

    actions = preset.get("actions") if isinstance(preset.get("actions"), list) else []
    executed = []
    for action in actions:
        if not isinstance(action, dict) or str(action.get("op") or "") != "touch":
            continue
        pos = action.get("pos")
        if not (isinstance(pos, list) and len(pos) == 2):
            continue
        x, y = int(pos[0]), int(pos[1])
        desktop.click_point(x, y)
        executed.append([x, y])
        reset_this = bool_param(action.get("reset_mouse_after_touch"), reset_after_touch)
        if reset_this:
            reset_mouse_hover(ctx, params)
        if delay_sec > 0:
            desktop.sleep(delay_sec)

    if not executed:
        raise RuntimeError("Preset resolved but no touch actions were executed")

    return {
        "preset_input": preset_input,
        "preset_key": str(preset.get("key") or ""),
        "preset_name": str(preset.get("name") or ""),
        "executed_actions": executed,
    }

