from __future__ import annotations

from typing import Any, Dict

from ._common import confidence_from_params, desktop_from_ctx, template_path


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    desktop = desktop_from_ctx(ctx)
    confidence = confidence_from_params(params)
    used = []
    for filename in ("tpl1772625196696.png", "tpl1772625206617.png"):
        path = template_path("crealityscan", "create_project", filename)
        desktop.click_image(path, confidence=confidence, timeout_sec=10.0)
        used.append(path)
        desktop.sleep(0.2)
    return {"used_templates": used}

