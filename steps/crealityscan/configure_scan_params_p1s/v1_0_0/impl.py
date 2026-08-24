from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.window import activate_window
from engine.mouse import move_mouse_smooth


@dataclass(frozen=True)
class TemplateSpec:
    file: str
    record_pos: Optional[Tuple[float, float]] = None
    resolution: Optional[Tuple[int, int]] = None


def _coerce_bool(v: Any, default: bool) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"true", "1", "yes", "y", "on"}:
            return True
        if s in {"false", "0", "no", "n", "off"}:
            return False
    return default


def _num(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        v = params.get(key, default)
        return float(v)
    except Exception:
        return float(default)


def _int(params: Dict[str, Any], key: str, default: int) -> int:
    try:
        v = params.get(key, default)
        return int(v)
    except Exception:
        return int(default)


def _reset_mouse_hover(params: Dict[str, Any], move_to, sleep) -> None:
    """
    选择“物体/人脸/人体”等选项后，鼠标停留在控件上可能触发 hover 态，
    导致后续模板/坐标点击对应的 UI 发生变化而失败。
    """
    safe_x = _int(params, "mouse_safe_x", 10)
    safe_y = _int(params, "mouse_safe_y", 10)
    move_duration_sec = _num(params, "mouse_safe_move_duration_sec", 0.35)
    move_steps = _int(params, "mouse_safe_move_steps", 12)
    sleep_sec = _num(params, "mouse_safe_sleep_sec", 0.3)
    try:
        ok = move_mouse_smooth((safe_x, safe_y), duration_sec=move_duration_sec, steps=move_steps)
        if not ok:
            move_to((safe_x, safe_y))
    except Exception:
        return
    try:
        sleep(max(0.0, sleep_sec))
    except Exception:
        pass


def _normalize_preset(s: str) -> str:
    s = (s or "").strip()
    s = " ".join(s.split())
    return s.lower()


def _load_presets() -> List[dict]:
    fp = Path(__file__).resolve().parent / "presets.json"
    raw = json.loads(fp.read_text(encoding="utf-8"))
    presets = raw.get("presets") if isinstance(raw, dict) else None
    return presets if isinstance(presets, list) else []


def _resolve_preset(preset_input: str, presets: List[dict]) -> dict:
    needle = _normalize_preset(preset_input)
    if not needle:
        raise RuntimeError("params.preset 不能为空（支持中文名称或 key）。")

    alias_map: Dict[str, dict] = {}
    for p in presets:
        if not isinstance(p, dict):
            continue
        key = str(p.get("key") or "").strip()
        name = str(p.get("name") or "").strip()
        aliases = p.get("aliases") if isinstance(p.get("aliases"), list) else []

        for a in [key, name, *aliases]:
            a = str(a or "").strip()
            if not a:
                continue
            alias_map.setdefault(_normalize_preset(a), p)

    hit = alias_map.get(needle)
    if hit:
        return hit

    # 兜底：包含匹配（用户可能只输入“中物体”）
    for k, p in alias_map.items():
        if needle and needle in k:
            return p

    available = sorted({str(p.get("name") or p.get("key") or "") for p in presets if isinstance(p, dict)})
    raise RuntimeError("未找到 preset：%r。可选示例：%s" % (preset_input, " / ".join(available[:12])))


def _template_spec_from_action(raw: Any) -> Optional[TemplateSpec]:
    if not isinstance(raw, dict):
        return None
    f = str(raw.get("file") or "").strip()
    if not f:
        return None

    rp = raw.get("record_pos")
    res = raw.get("resolution")

    record_pos: Optional[Tuple[float, float]] = None
    if isinstance(rp, (list, tuple)) and len(rp) == 2 and all(isinstance(x, (int, float)) for x in rp):
        record_pos = (float(rp[0]), float(rp[1]))

    resolution: Optional[Tuple[int, int]] = None
    if isinstance(res, (list, tuple)) and len(res) == 2 and all(isinstance(x, (int, float)) for x in res):
        resolution = (int(res[0]), int(res[1]))

    return TemplateSpec(file=f, record_pos=record_pos, resolution=resolution)


def _resolve_template_path(project_root: Path, step_dir: Path, filename: str) -> Path:
    fp = step_dir / "templates" / filename
    if fp.exists():
        return fp
    return fp


def _build_template(project_root: Path, step_dir: Path, spec: TemplateSpec):
    from airtest.core.api import Template  # type: ignore

    fp = _resolve_template_path(project_root, step_dir, spec.file)
    if not fp.exists():
        raise FileNotFoundError(f"缺少模板文件：{fp}")

    kwargs: Dict[str, Any] = {}
    if spec.record_pos is not None:
        kwargs["record_pos"] = spec.record_pos
    if spec.resolution is not None:
        kwargs["resolution"] = spec.resolution
    return Template(str(fp), **kwargs)


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import device, sleep, touch, wait  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "无法导入 Airtest（airtest.core.api）。请先安装依赖：python -m pip install -r requirements.txt"
        ) from e

    # 兼容：部分 Airtest 版本不再提供 api.move_to（例如 1.4.3）。
    try:
        from airtest.core.api import move_to as _move_to  # type: ignore
    except Exception:
        _move_to = None

    def move_to(pos) -> None:
        if _move_to is not None:
            _move_to(pos)
            return
        dev = device()
        if hasattr(dev, "move"):
            dev.move(pos)
            return
        if hasattr(dev, "mouse_move"):
            dev.mouse_move(pos)
            return
        raise RuntimeError("当前设备不支持鼠标移动（缺少 move/mouse_move）。")

    case = ctx.get("case") if isinstance(ctx.get("case"), dict) else {}
    app = case.get("app") if isinstance(case.get("app"), dict) else {}
    title_contains = str(params.get("window_title_contains") or app.get("window_title_contains") or "CrealityScan")
    fullscreen = _coerce_bool(params.get("fullscreen"), default=True)

    if title_contains:
        ok = activate_window(title_contains, fullscreen=fullscreen)
        if not ok:
            raise RuntimeError(f"未找到窗口（title_contains={title_contains!r}），请确认 CrealityScan 已打开且未最小化。")

    presets = _load_presets()
    preset_input = str(params.get("preset") or "")
    preset = _resolve_preset(preset_input, presets)

    delay_sec = _num(params, "delay_sec", 0.1) or 0.1
    reset_mouse_after_touch_default = _coerce_bool(params.get("reset_mouse_after_touch"), default=True)
    actions = preset.get("actions") if isinstance(preset.get("actions"), list) else []
    if not actions:
        raise RuntimeError("preset 未包含 actions")

    step_dir = Path(__file__).resolve().parent
    project_root = step_dir.parents[4]

    def _touch_action(action: Dict[str, Any]) -> bool:
        pos = action.get("pos")
        tpl_raw = action.get("template")
        if isinstance(pos, list) and len(pos) == 2:
            x, y = int(pos[0]), int(pos[1])
            touch((x, y))
            return True
        if tpl_raw is not None:
            spec = _template_spec_from_action(tpl_raw)
            if not spec:
                raise RuntimeError("touch.template 解析失败")
            touch(_build_template(project_root, step_dir, spec))
            return True
        return False

    executed = 0
    for a in actions:
        if not isinstance(a, dict):
            continue
        op = str(a.get("op") or "").strip().lower()

        if op == "sleep":
            sec = a.get("sleep_sec")
            if isinstance(sec, (int, float)):
                sleep(float(sec))
                executed += 1
            continue

        if op == "touch":
            if _touch_action(a):
                executed += 1
                reset_this = _coerce_bool(a.get("reset_mouse_after_touch"), default=reset_mouse_after_touch_default)
                if reset_this:
                    _reset_mouse_hover(params, move_to, sleep)
                if delay_sec > 0:
                    sleep(delay_sec)
            continue

        if op == "wait":
            tpl_raw = a.get("template")
            spec = _template_spec_from_action(tpl_raw)
            if not spec:
                raise RuntimeError("wait.template 解析失败")

            timeout = a.get("timeout")
            interval = a.get("interval")
            kw: Dict[str, Any] = {}
            if isinstance(timeout, (int, float)):
                kw["timeout"] = float(timeout)
            if isinstance(interval, (int, float)):
                kw["interval"] = float(interval)

            wait(_build_template(project_root, step_dir, spec), **kw)
            executed += 1

            if delay_sec > 0:
                sleep(delay_sec)
            continue


        raise RuntimeError(f"不支持的 action.op：{op!r}")

    return {
        "preset_input": preset_input,
        "preset_key": str(preset.get("key") or ""),
        "preset_name": str(preset.get("name") or ""),
        "executed_actions": executed,
        "fullscreen": fullscreen,
        "title_contains": title_contains,
    }
