from typing import Any, Dict


def _num(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return default


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    import time

    seconds = max(0.0, _num(params, "seconds", 1.0))
    time.sleep(seconds)
    return {"seconds": seconds}
