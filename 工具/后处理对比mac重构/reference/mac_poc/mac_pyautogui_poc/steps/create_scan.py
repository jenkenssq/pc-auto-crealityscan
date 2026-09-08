from __future__ import annotations

from typing import Any, Dict

from ._common import confidence_from_params, desktop_from_ctx, template_path


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    desktop = desktop_from_ctx(ctx)
    confidence = confidence_from_params(params)
    first_click = desktop.click_point(130, 50)
    desktop.sleep(0.2)
    image_path = template_path("crealityscan", "create_scan", "tpl1772628772383.png")
    second_click = desktop.click_image(image_path, confidence=confidence, timeout_sec=10.0)
    return {
        "toolbar_click": list(first_click),
        "used_template": image_path,
        "template_click": list(second_click),
    }

