from __future__ import annotations

from typing import Any, Dict

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


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    app = ctx.get("case", {}).get("app", {}) if isinstance(ctx.get("case", {}).get("app"), dict) else {}
    title_contains = str(params.get("window_title_contains") or app.get("window_title_contains") or "CrealityScan")
    fullscreen = _coerce_bool(params.get("fullscreen"), default=True)
    ok = activate_window(title_contains, fullscreen=fullscreen)
    if not ok:
        raise RuntimeError(f"未找到窗口（title_contains={title_contains!r}），请确认 CrealityScan 已打开且未最小化。")
    return {"activated": True, "fullscreen": fullscreen, "title_contains": title_contains}
