from __future__ import annotations

from typing import Any, Dict

from ._common import confidence_from_params, desktop_from_ctx, template_path


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    desktop = desktop_from_ctx(ctx)
    confidence = confidence_from_params(params)
    first_path = template_path("crealityscan", "import_project", "tpl1772543115770.png")
    second_path = template_path("crealityscan", "import_project", "tpl1772543123954.png")
    desktop.click_image(first_path, confidence=confidence, timeout_sec=10.0)
    desktop.sleep(0.3)
    desktop.click_image(second_path, confidence=confidence, timeout_sec=10.0)
    return {"used_templates": [first_path, second_path]}

