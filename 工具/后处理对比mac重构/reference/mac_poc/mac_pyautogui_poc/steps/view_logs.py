from __future__ import annotations

from typing import Any, Dict

from ._common import confidence_from_params, desktop_from_ctx, screenshot_path, template_path


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    desktop = desktop_from_ctx(ctx)
    confidence = confidence_from_params(params)
    first_path = template_path("crealityscan", "view_logs", "tpl1772543502314.png")
    second_path = template_path("crealityscan", "view_logs", "tpl1772543522896.png")
    desktop.click_image(first_path, confidence=confidence, timeout_sec=10.0)
    desktop.sleep(0.3)
    desktop.click_image(second_path, confidence=confidence, timeout_sec=10.0)
    desktop.sleep(0.8)
    shot = screenshot_path(ctx, "view_logs")
    desktop.screenshot(str(shot))
    return {"used_templates": [first_path, second_path], "snapshot": str(shot)}

