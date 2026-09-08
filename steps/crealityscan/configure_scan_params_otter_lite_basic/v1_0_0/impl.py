from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.mouse import move_mouse_smooth
from engine.window import activate_window


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


def _normalize_preset(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("－", "-").replace("—", "-")
    s = " ".join(s.split())
    return s.lower()


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


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import device, sleep, touch  # type: ignore
    except Exception as e:
        raise RuntimeError("未安装 Airtest（无法导入 airtest.core.api）。请先安装依赖后再运行。") from e

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
        activate_window(title_contains, fullscreen=fullscreen)

    presets = _load_presets()
    preset_input = str(params.get("preset") or "")
    preset = _resolve_preset(preset_input, presets)

    delay_sec = _num(params, "delay_sec", 0.1) or 0.1
    reset_mouse_after_touch = _coerce_bool(params.get("reset_mouse_after_touch"), default=True)
    actions = preset.get("actions") if isinstance(preset.get("actions"), list) else []
    if not actions:
        raise RuntimeError("preset 未包含 actions")

    executed = 0
    for a in actions:
        if not isinstance(a, dict):
            continue
        if str(a.get("op") or "") != "touch":
            continue
        pos = a.get("pos")
        if not (isinstance(pos, list) and len(pos) == 2):
            continue
        x, y = int(pos[0]), int(pos[1])
        touch((x, y))
        executed += 1
        reset_this = _coerce_bool(a.get("reset_mouse_after_touch"), default=reset_mouse_after_touch)
        if reset_this:
            _reset_mouse_hover(params, move_to, sleep)
        if delay_sec > 0:
            sleep(delay_sec)

    return {
        "preset_input": preset_input,
        "preset_key": str(preset.get("key") or ""),
        "preset_name": str(preset.get("name") or ""),
        "executed_actions": executed,
        "fullscreen": fullscreen,
        "title_contains": title_contains,
    }
