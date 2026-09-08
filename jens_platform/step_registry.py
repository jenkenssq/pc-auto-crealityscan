from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from jens_runtime import iter_existing_resource_roots


@dataclass(frozen=True)
class StepMeta:
    step_id: str
    name: str
    version: str
    description: str = ""
    params_schema: dict = None
    source_path: str = ""


def scan_steps(project_root: Path) -> List[StepMeta]:
    """
    扫描 steps/**/step.json。
    约定：step.json 使用 UTF-8 编码。
    """
    metas: List[StepMeta] = []
    seen_step_files: set[str] = set()
    roots: list[Path] = [project_root]
    for root in iter_existing_resource_roots():
        if root not in roots:
            roots.append(root)

    for root in roots:
        steps_dir = root / "steps"
        if not steps_dir.exists():
            continue

        for fp in steps_dir.rglob("step.json"):
            normalized = str(fp.resolve())
            if normalized in seen_step_files:
                continue
            seen_step_files.add(normalized)
            try:
                raw = json.loads(fp.read_text(encoding="utf-8-sig"))
                if not isinstance(raw, dict):
                    continue
                step_id = str(raw.get("id") or "").strip()
                version = str(raw.get("version") or "").strip()
                name = str(raw.get("name") or step_id).strip()
                if not step_id or not version:
                    continue
                metas.append(
                    StepMeta(
                        step_id=step_id,
                        name=name,
                        version=version,
                        description=str(raw.get("description") or ""),
                        params_schema=raw.get("params_schema") if isinstance(raw.get("params_schema"), dict) else {},
                        source_path=str(fp),
                    )
                )
            except Exception:
                continue

    # 稳定排序：先 id，再 version
    metas.sort(key=lambda m: (m.step_id, m.version))
    return metas


def group_steps_by_id(metas: List[StepMeta]) -> Dict[str, List[StepMeta]]:
    grouped: Dict[str, List[StepMeta]] = {}
    for m in metas:
        grouped.setdefault(m.step_id, []).append(m)
    return grouped
