from __future__ import annotations

import ast
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


_STEP_ID_RE = re.compile(r"^[A-Za-z_][0-9A-Za-z_]*(\.[A-Za-z_][0-9A-Za-z_]*)+$")


@dataclass(frozen=True)
class AirStepImportRequest:
    air_dir: Path
    step_id: str
    name: str
    version: str = "1.0.0"
    description: str = ""


@dataclass(frozen=True)
class TemplateSpec:
    filename: str
    record_pos: Optional[Tuple[float, float]] = None
    resolution: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class ActionSpec:
    op: str  # touch | wait | swipe | sleep
    template: Optional[TemplateSpec] = None
    sleep_sec: Optional[float] = None
    vector: Optional[Sequence[float]] = None
    wait_timeout: Optional[float] = None
    wait_interval: Optional[float] = None


def validate_step_id(step_id: str) -> None:
    if not _STEP_ID_RE.fullmatch(step_id or ""):
        raise ValueError("step_id 不合法：仅允许字母/数字/下划线/点，且必须包含至少一个 '.'")


def suggest_step_id(air_dir_name: str, prefix: str = "crealityscan") -> str:
    raw = (air_dir_name or "").replace(".air", "")
    slug = re.sub(r"[^0-9A-Za-z]+", "_", raw).strip("_").lower()
    if not slug:
        slug = f"air_{int(time.time())}"
    if slug[0].isdigit():
        slug = f"air_{slug}"
    return f"{prefix}.{slug}"


def _literal_eval(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _get_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _kw(call: ast.Call, name: str) -> Optional[ast.AST]:
    for k in call.keywords or []:
        if k.arg == name:
            return k.value
    return None


def _parse_template(call: ast.Call) -> Optional[TemplateSpec]:
    if _get_call_name(call.func) != "Template":
        return None
    if not call.args:
        return None
    filename = _literal_eval(call.args[0])
    if not isinstance(filename, str) or not filename.lower().endswith(".png"):
        return None
    rp = _literal_eval(_kw(call, "record_pos") or ast.Constant(value=None))
    res = _literal_eval(_kw(call, "resolution") or ast.Constant(value=None))

    record_pos = rp if (isinstance(rp, tuple) and len(rp) == 2) else None
    resolution = res if (isinstance(res, tuple) and len(res) == 2) else None
    return TemplateSpec(filename=filename, record_pos=record_pos, resolution=resolution)


def parse_air_script(air_script_path: Path) -> Tuple[List[ActionSpec], List[str]]:
    """
    解析 .air 脚本为平台 Step 所需的最小动作序列。

    支持：touch/wait/swipe/sleep + Template(...)。
    其他复杂控制流不会被迁移（会返回 warnings）。
    """
    text = air_script_path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text)
    actions: List[ActionSpec] = []
    warnings: List[str] = []

    for st in tree.body:
        if not isinstance(st, ast.Expr) or not isinstance(st.value, ast.Call):
            # 常见：import/赋值/循环/条件等，导入器不迁移
            if not isinstance(st, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)):
                warnings.append(f"未迁移语句类型：{type(st).__name__}")
            continue

        call = st.value
        fn = _get_call_name(call.func)

        if fn == "sleep" and call.args:
            sec = _literal_eval(call.args[0])
            if isinstance(sec, (int, float)):
                actions.append(ActionSpec(op="sleep", sleep_sec=float(sec)))
            else:
                warnings.append("sleep() 参数无法解析，已忽略")
            continue

        if fn in {"touch", "wait", "swipe"}:
            if not call.args:
                warnings.append(f"{fn}() 缺少参数，已忽略")
                continue
            tpl_call = call.args[0]
            if not isinstance(tpl_call, ast.Call):
                warnings.append(f"{fn}() 第一个参数不是 Template(...)，已忽略")
                continue
            tpl = _parse_template(tpl_call)
            if not tpl:
                warnings.append(f"{fn}() Template 解析失败，已忽略")
                continue

            if fn == "touch":
                actions.append(ActionSpec(op="touch", template=tpl))
                continue

            if fn == "wait":
                timeout = _literal_eval(_kw(call, "timeout") or ast.Constant(value=None))
                interval = _literal_eval(_kw(call, "interval") or ast.Constant(value=None))
                actions.append(
                    ActionSpec(
                        op="wait",
                        template=tpl,
                        wait_timeout=float(timeout) if isinstance(timeout, (int, float)) else None,
                        wait_interval=float(interval) if isinstance(interval, (int, float)) else None,
                    )
                )
                continue

            # swipe
            vector_node = _kw(call, "vector")
            vector = _literal_eval(vector_node) if vector_node else None
            if vector is not None and not isinstance(vector, (list, tuple)):
                warnings.append("swipe() vector 参数无法解析，已忽略 vector")
                vector = None
            actions.append(ActionSpec(op="swipe", template=tpl, vector=list(vector) if vector is not None else None))
            continue

        # 其他调用不迁移
        warnings.append(f"未迁移调用：{fn or 'unknown'}()")

    return actions, warnings


def _render_template_ctor(tpl: TemplateSpec) -> str:
    parts: List[str] = [f'str(base / "{tpl.filename}")']
    if tpl.record_pos is not None:
        parts.append(f"record_pos={tuple(tpl.record_pos)!r}")
    if tpl.resolution is not None:
        parts.append(f"resolution={tuple(tpl.resolution)!r}")
    return "Template(" + ", ".join(parts) + ")"


def build_step_impl(actions: Iterable[ActionSpec], air_script_name: str) -> str:
    need_touch = any(a.op == "touch" for a in actions)
    need_wait = any(a.op == "wait" for a in actions)
    need_swipe = any(a.op == "swipe" for a in actions)
    need_sleep = any(a.op == "sleep" for a in actions)

    api_imports = ["Template"]
    if need_touch:
        api_imports.append("touch")
    if need_wait:
        api_imports.append("wait")
    if need_swipe:
        api_imports.append("swipe")
    if need_sleep:
        api_imports.append("sleep")

    lines: List[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from pathlib import Path")
    lines.append("from typing import Any, Dict")
    lines.append("")
    lines.append("")
    lines.append("def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:")
    lines.append("    try:")
    lines.append(f"        from airtest.core.api import {', '.join(api_imports)}  # type: ignore")
    lines.append("    except Exception as e:")
    lines.append("        raise RuntimeError(\"未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。\") from e")
    lines.append("")
    lines.append("    base = Path(__file__).resolve().parent / \"templates\"")
    lines.append("")
    lines.append(f"    # 来自你现有的 .air 用例（{air_script_name}）")

    for a in actions:
        if a.op == "sleep" and a.sleep_sec is not None:
            lines.append(f"    sleep({a.sleep_sec})")
            continue
        if not a.template:
            continue
        tpl_ctor = _render_template_ctor(a.template)
        if a.op == "touch":
            lines.append(f"    touch({tpl_ctor})")
        elif a.op == "wait":
            extra: List[str] = []
            if a.wait_timeout is not None:
                extra.append(f"timeout={a.wait_timeout}")
            if a.wait_interval is not None:
                extra.append(f"interval={a.wait_interval}")
            suffix = (", " + ", ".join(extra)) if extra else ""
            lines.append(f"    wait({tpl_ctor}{suffix})")
        elif a.op == "swipe":
            if a.vector:
                lines.append(f"    swipe({tpl_ctor}, vector={list(a.vector)!r})")
            else:
                lines.append(f"    swipe({tpl_ctor})")

    lines.append("    return {}")
    lines.append("")
    return "\n".join(lines)


def import_air_step(project_root: Path, req: AirStepImportRequest) -> Dict[str, Any]:
    """
    把 .air 用例导入为平台 Step：生成 steps/**/step.json + impl.py + templates。

    返回：{step_dir, created_files, warnings}
    """
    validate_step_id(req.step_id)
    air_dir = Path(req.air_dir).resolve()
    if not air_dir.exists() or not air_dir.is_dir():
        raise FileNotFoundError(f".air 目录不存在：{air_dir}")
    if air_dir.suffix.lower() != ".air":
        raise ValueError("请选择以 .air 结尾的目录（Airtest 用例目录）")

    # 找到脚本文件：优先与目录同名
    preferred = air_dir / f"{air_dir.stem}.py"
    py_files = [preferred] if preferred.exists() else list(air_dir.glob("*.py"))
    if not py_files:
        raise FileNotFoundError(f"在 .air 目录内未找到 .py：{air_dir}")
    air_py = py_files[0]

    actions, warnings = parse_air_script(air_py)
    if not actions:
        raise RuntimeError("未能从 .air 脚本解析出可迁移动作（仅支持 touch/wait/swipe/sleep + Template）。")

    parts = req.step_id.split(".")
    ver_dir = "v" + req.version.replace(".", "_")
    step_dir = project_root / "steps" / Path(*parts) / ver_dir
    if step_dir.exists():
        raise FileExistsError(f"步骤已存在：{step_dir}")

    templates_dir = step_dir / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    # 写入 __init__.py（逐级确保包可 import）
    created_files: List[str] = []
    pkg_root = project_root / "steps"
    for i in range(1, len(parts) + 1):
        pkg = pkg_root / Path(*parts[:i])
        pkg.mkdir(parents=True, exist_ok=True)
        init_fp = pkg / "__init__.py"
        if not init_fp.exists():
            init_fp.write_text("", encoding="utf-8")
            created_files.append(str(init_fp))
    (step_dir / "__init__.py").write_text("", encoding="utf-8")
    created_files.append(str(step_dir / "__init__.py"))

    # step.json
    step_json = {
        "id": req.step_id,
        "name": req.name,
        "version": req.version,
        "description": req.description or f"来自现有 Airtest 用例：{air_dir.name}",
        "params_schema": {},
    }
    step_json_fp = step_dir / "step.json"
    step_json_fp.write_text(json.dumps(step_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    created_files.append(str(step_json_fp))

    # impl.py
    impl_fp = step_dir / "impl.py"
    impl_fp.write_text(build_step_impl(actions, f"{air_dir.name}/{air_py.name}"), encoding="utf-8")
    created_files.append(str(impl_fp))

    # 复制模板
    used_templates = sorted({a.template.filename for a in actions if a.template and a.template.filename})
    for fn in used_templates:
        src = air_dir / fn
        if not src.exists():
            raise FileNotFoundError(f"缺少模板文件：{src}")
        (templates_dir / fn).write_bytes(src.read_bytes())
        created_files.append(str(templates_dir / fn))

    return {"step_dir": str(step_dir), "created_files": created_files, "warnings": warnings}
