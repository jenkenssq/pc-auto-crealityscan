from __future__ import annotations

from typing import Callable, Dict

from .steps import configure_scan_params, create_project, create_scan, import_project, view_logs
from .steps import slide_rail


StepFn = Callable[[dict, dict], dict]


STEP_REGISTRY: Dict[str, StepFn] = {
    "crealityscan.create_project": create_project.run,
    "crealityscan.create_scan": create_scan.run,
    "crealityscan.configure_scan_params_otter_lite": configure_scan_params.run,
    "crealityscan.import_project": import_project.run,
    "crealityscan.view_logs": view_logs.run,
    "crealityscan.slide_rail_step": slide_rail.run,
}


def resolve_step(step_id: str) -> StepFn:
    if step_id not in STEP_REGISTRY:
        available = ", ".join(sorted(STEP_REGISTRY))
        raise KeyError(f"Unknown step_id: {step_id}. Available: {available}")
    return STEP_REGISTRY[step_id]

