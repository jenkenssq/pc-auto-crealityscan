# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def _bool(params: Dict[str, Any], key: str, default: bool = False) -> bool:
    value = params.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _int(params: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        return default


def _num(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return default


def _load_presets() -> list[Dict[str, Any]]:
    fp = Path(__file__).resolve().with_name("presets.json")
    raw = json.loads(fp.read_text(encoding="utf-8-sig"))
    presets = raw.get("presets") if isinstance(raw, dict) else None
    if not isinstance(presets, list):
        raise ValueError("presets.json 缺少 presets 列表")
    return [p for p in presets if isinstance(p, dict)]


def _resolve_preset(value: Any) -> Dict[str, Any]:
    needle = str(value or "").strip()
    if not needle:
        raise ValueError("缺少 params.preset，请选择滑轨位置 preset")

    for preset in _load_presets():
        candidates = [preset.get("key"), preset.get("name")]
        aliases = preset.get("aliases")
        if isinstance(aliases, list):
            candidates.extend(aliases)
        if any(str(x or "").strip().lower() == needle.lower() for x in candidates):
            return preset
    raise ValueError(f"未知滑轨位置 preset: {needle!r}")


def _motion_client_module_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "滑轨"


def _create_client(use_mock: bool, host: str, port: int):
    module_dir = str(_motion_client_module_dir())
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    from motion_client import create_motion_client  # type: ignore

    return create_motion_client(use_mock=use_mock, host=host, port=port)


def _write_position_log(ctx: Dict[str, Any], params: Dict[str, Any], record: Dict[str, Any]) -> str:
    run_dir = Path(str(ctx.get("run_dir") or ".")).resolve()
    raw_log_dir = str(params.get("position_log_dir") or "").strip()
    log_dir = Path(raw_log_dir).resolve() if raw_log_dir else run_dir / "slide_rail_position_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"slide_rail_position_{datetime.now():%Y%m%d}.jsonl"
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")
    return str(log_path)


def _ensure_success(response: Any, action: str) -> Dict[str, Any]:
    if not isinstance(response, dict):
        raise RuntimeError(f"{action} 返回非对象结果: {response!r}")
    if response.get("status") != "success":
        raise RuntimeError(str(response.get("message") or response.get("error") or f"{action} 失败"))
    return response


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    preset = _resolve_preset(params.get("preset"))
    target_position = int(preset.get("position"))
    lift_up_seconds_after_move = max(0.0, _num(preset, "lift_up_seconds_after_move", 0.0))
    host = str(params.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    port = _int(params, "port", 5000)
    use_mock = _bool(params, "use_mock", False)
    connect_controller = _bool(params, "connect_controller", False)
    reset_to_zero_first = _bool(params, "reset_to_zero_first", False)
    lift_bottom_safety_margin = max(0.0, _num(params, "lift_bottom_safety_margin", 1.0))

    print(
        f"[JENS][slide_rail] switch_position preset={preset.get('name')} "
        f"target={target_position} host={host} port={port} mock={use_mock}"
    )
    client = _create_client(use_mock=use_mock, host=host, port=port)
    if not client.connect():
        last_error = getattr(client, "last_error", "") or "无法连接到滑轨 motion_service"
        print(f"[JENS][slide_rail] connect service failed: {last_error}")
        raise RuntimeError(last_error)
    print("[JENS][slide_rail] service connected")

    try:
        if connect_controller:
            print("[JENS][slide_rail] connecting controller")
            _ensure_success(
                client.connect_controller(
                    dll_path=str(params.get("dll_path") or "zauxdll.dll"),
                    ip=str(params.get("controller_ip") or "192.168.0.11"),
                ),
                "连接滑轨控制器",
            )
            print("[JENS][slide_rail] controller connected")

        print(
            "[JENS][slide_rail] lowering lift platform to bottom before horizontal move "
            f"safety_margin={lift_bottom_safety_margin}s"
        )
        lower_lift_result = _ensure_success(
            client.lift_down_to_bottom(lift_bottom_safety_margin),
            "升降台下降到扫描最低位",
        )
        print(f"[JENS][slide_rail] lower_lift_result={lower_lift_result}")

        before_position = _ensure_success(client.get_position(), "读取移动前位置")
        print(f"[JENS][slide_rail] before_position={before_position}")
        reset_result: Dict[str, Any] = {}
        if reset_to_zero_first:
            print("[JENS][slide_rail] reset to soft zero")
            reset_result = _ensure_success(client.reset_to_zero(), "回软零点")
            print(f"[JENS][slide_rail] reset_result={reset_result}")

        print(f"[JENS][slide_rail] move_absolute target={target_position}")
        move_result = _ensure_success(client.move_absolute(target_position), "移动到滑轨目标位置")
        print(f"[JENS][slide_rail] move_result={move_result}")
        final_position = _ensure_success(client.get_position(), "读取移动后位置")
        print(f"[JENS][slide_rail] final_position={final_position}")

        lift_up_result: Dict[str, Any] = {}
        if lift_up_seconds_after_move > 0:
            print(
                "[JENS][slide_rail] raising lift platform after horizontal move "
                f"duration={lift_up_seconds_after_move}s"
            )
            lift_up_result = _ensure_success(
                client.lift_up_duration(lift_up_seconds_after_move),
                "水平换位后升降台上升",
            )
            print(f"[JENS][slide_rail] lift_up_result={lift_up_result}")

        record = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "step_id": "slide_rail.switch_position",
            "preset": preset.get("key"),
            "preset_name": preset.get("name"),
            "target_position": target_position,
            "lift_bottom_safety_margin": lift_bottom_safety_margin,
            "lower_lift_result": lower_lift_result,
            "before_position": before_position,
            "reset_result": reset_result,
            "move_result": move_result,
            "final_position": final_position,
            "lift_up_seconds_after_move": lift_up_seconds_after_move,
            "lift_up_result": lift_up_result,
        }
        log_path = _write_position_log(ctx, params, record)
        print(f"[JENS][slide_rail] position_log={log_path}")

        return {
            "preset": preset.get("key"),
            "preset_name": preset.get("name"),
            "target_position": target_position,
            "lift_bottom_safety_margin": lift_bottom_safety_margin,
            "lower_lift_result": lower_lift_result,
            "before_position": before_position,
            "move_result": move_result,
            "final_position": final_position,
            "lift_up_seconds_after_move": lift_up_seconds_after_move,
            "lift_up_result": lift_up_result,
            "position_log": log_path,
        }
    finally:
        client.disconnect()
        print("[JENS][slide_rail] service disconnected")
