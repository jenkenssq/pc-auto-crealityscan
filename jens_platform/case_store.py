from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _safe_file_stem(name: str) -> str:
    name = (name or "case").strip()
    name = re.sub(r'[<>:"/\\\\|?*]+', "_", name)
    return name or "case"


@dataclass
class CaseStep:
    step_id: str
    version: str
    name: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    on_fail: Dict[str, Any] = field(default_factory=lambda: {"action": "abort"})


@dataclass
class CaseModel:
    case_id: str = "case"
    name: str = "新用例"
    app_window_title_contains: str = "CrealityScan"
    app_log_dir: str = ""
    app_device_uri: str = "Windows:///"
    keywords: List[str] = field(default_factory=list)
    steps: List[CaseStep] = field(default_factory=list)
    # 任务生成元信息（供运行器识别任务类型与连接方式，如“帧率统计”写 G/H 列）
    task_kind: str = ""
    connection_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "name": self.name,
            "app": {
                "window_title_contains": self.app_window_title_contains,
                "device_uri": self.app_device_uri,
                "log_dir": self.app_log_dir,
            },
            "keywords": list(self.keywords),
            "task_kind": self.task_kind,
            "connection_type": self.connection_type,
            "steps": [
                {
                    "id": s.step_id,
                    "version": s.version,
                    "name": s.name or s.step_id,
                    "params": s.params or {},
                    "on_fail": s.on_fail or {"action": "abort"},
                }
                for s in self.steps
            ],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CaseModel":
        m = CaseModel()
        m.case_id = str(d.get("case_id") or "case")
        m.name = str(d.get("name") or m.case_id)
        app = d.get("app") if isinstance(d.get("app"), dict) else {}
        m.app_window_title_contains = str(app.get("window_title_contains") or "CrealityScan")
        m.app_log_dir = str(app.get("log_dir") or "")
        m.app_device_uri = str(app.get("device_uri") or "Windows:///")
        m.keywords = [x for x in (d.get("keywords") or []) if isinstance(x, str)]
        m.task_kind = str(d.get("task_kind") or "")
        m.connection_type = str(d.get("connection_type") or "")

        steps = d.get("steps") if isinstance(d.get("steps"), list) else []
        m.steps = []
        for s in steps:
            if not isinstance(s, dict):
                continue
            step_id = str(s.get("id") or "")
            version = str(s.get("version") or "")
            if not step_id or not version:
                continue
            m.steps.append(
                CaseStep(
                    step_id=step_id,
                    version=version,
                    name=str(s.get("name") or step_id),
                    params=s.get("params") if isinstance(s.get("params"), dict) else {},
                    on_fail=s.get("on_fail") if isinstance(s.get("on_fail"), dict) else {"action": "abort"},
                )
            )
        return m


def save_case_json(project_root: Path, model: CaseModel, path: Optional[Path] = None) -> Path:
    """
    保存用例编排 JSON。默认保存到 cases/user/ 下。
    """
    if path is None:
        base = project_root / "cases" / "user"
        base.mkdir(parents=True, exist_ok=True)
        stem = _safe_file_stem(model.case_id or model.name)
        path = base / f"{stem}.json"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_temp_case_json(project_root: Path, model: CaseModel) -> Path:
    """
    为“运行”生成临时 JSON（避免覆盖用户保存的用例）。
    """
    base = project_root / "cases" / "_generated"
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = _safe_file_stem(model.case_id or model.name)
    path = base / f"{stem}_{ts}.json"
    path.write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_case_json(path: Path) -> CaseModel:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("用例 JSON 顶层必须是对象")
    return CaseModel.from_dict(raw)


def save_task_json(project_root: Path, model: CaseModel, path: Optional[Path] = None) -> Path:
    """
    保存 Task（任务）JSON：本质上就是“保存一份当前编排”。

    默认保存到 tasks/ 下（与 cases/user/ 分离，便于批量选择执行）。
    """
    if path is None:
        base = project_root / "tasks"
        base.mkdir(parents=True, exist_ok=True)
        stem = _safe_file_stem(model.case_id or model.name)
        path = base / f"{stem}.json"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_task_json(path: Path) -> CaseModel:
    # Task 与 Case 结构一致，复用解析
    return load_case_json(path)


def list_task_jsons(project_root: Path) -> List[Path]:
    base = project_root / "tasks"
    if not base.exists():
        return []
    files = [p for p in base.glob("*.json") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files

