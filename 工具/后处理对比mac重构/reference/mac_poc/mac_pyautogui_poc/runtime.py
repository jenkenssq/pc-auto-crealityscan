from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def poc_root() -> Path:
    return Path(__file__).resolve().parent


def artifacts_root() -> Path:
    return poc_root() / "artifacts"


def original_step_root(step_group: str, step_name: str, version: str = "v1_0_0") -> Path:
    return project_root() / "steps" / step_group / step_name / version


def original_template_path(step_group: str, step_name: str, filename: str, version: str = "v1_0_0") -> Path:
    return original_step_root(step_group, step_name, version) / "templates" / filename


def original_file(path: str) -> Path:
    return project_root() / path

