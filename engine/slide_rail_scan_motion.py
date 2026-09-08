from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional


def _number(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _integer(params: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        return int(default)


def _boolean(params: Dict[str, Any], key: str, default: bool) -> bool:
    raw = params.get(key, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return bool(default)


def _motion_client_module_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "滑轨"


def _create_motion_client(host: str, port: int):
    module_dir = str(_motion_client_module_dir())
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    from motion_client import create_motion_client  # type: ignore

    return create_motion_client(use_mock=False, host=host, port=port)


class SlideRailScanMotion:
    def __init__(self, params: Dict[str, Any]):
        self.enabled = _boolean(params, "slide_rail_scan_motion_enabled", True)
        self.host = str(params.get("slide_rail_host") or "127.0.0.1").strip() or "127.0.0.1"
        self.port = _integer(params, "slide_rail_port", 5000)
        self.scan_cycle_seconds = max(0.1, _number(params, "slide_rail_lift_cycle_seconds", 4.0))
        self.horizontal_pulse = _integer(params, "slide_rail_horizontal_pulse", 10000)
        self.horizontal_speed = max(1, _integer(params, "slide_rail_horizontal_speed", 2000))
        self.client = None
        self.thread: Optional[threading.Thread] = None
        self.started = False
        self.stop_sent = False
        self.skipped_reason = ""
        self.start_result: Dict[str, Any] = {}
        self.stop_result: Dict[str, Any] = {}

    def start(self) -> None:
        if self.started:
            return
        if not self.enabled:
            self.skipped_reason = "disabled"
            print("[JENS][slide_rail_scan] disabled")
            return

        try:
            self.client = _create_motion_client(self.host, self.port)
            if not self.client.connect():
                self.skipped_reason = getattr(self.client, "last_error", "") or "motion_service not connected"
                print(f"[JENS][slide_rail_scan] skip: {self.skipped_reason}")
                self._disconnect_client()
                return
            if not self.client.is_controller_connected():
                self.skipped_reason = "controller not connected"
                print(f"[JENS][slide_rail_scan] skip: {self.skipped_reason}")
                self._disconnect_client()
                return

            print(
                "[JENS][slide_rail_scan] start continuous scan motion "
                f"lift_cycle={self.scan_cycle_seconds}s horizontal_pulse={self.horizontal_pulse} "
                f"speed={self.horizontal_speed}"
            )
            self.started = True
            self.thread = threading.Thread(target=self._run_cycle, name="jens_slide_rail_scan", daemon=True)
            self.thread.start()
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            self.skipped_reason = str(exc)
            print(f"[JENS][slide_rail_scan] skip: {self.skipped_reason}")
            self._disconnect_client()

    def _run_cycle(self) -> None:
        try:
            if self.client is None:
                return
            result = self.client.continuous_scan_cycle(
                scan_cycle_seconds=self.scan_cycle_seconds,
                horizontal_pulse=self.horizontal_pulse,
                horizontal_speed=self.horizontal_speed,
            )
            self.start_result = result if isinstance(result, dict) else {"result": result}
            print(f"[JENS][slide_rail_scan] cycle ended: {self.start_result}")
        except (OSError, RuntimeError, ValueError) as exc:
            self.start_result = {"status": "error", "message": str(exc)}
            print(f"[JENS][slide_rail_scan] cycle error: {exc}")
        finally:
            self._disconnect_client()

    def stop(self) -> None:
        if not self.started or self.stop_sent:
            return
        self.stop_sent = True
        stop_client = None
        try:
            stop_client = _create_motion_client(self.host, self.port)
            if stop_client.connect():
                result = stop_client.stop_continuous()
                self.stop_result = result if isinstance(result, dict) else {"result": result}
                print(f"[JENS][slide_rail_scan] stop requested: {self.stop_result}")
            else:
                self.stop_result = {
                    "status": "error",
                    "message": getattr(stop_client, "last_error", "") or "motion_service not connected",
                }
                print(f"[JENS][slide_rail_scan] stop failed: {self.stop_result}")
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            self.stop_result = {"status": "error", "message": str(exc)}
            print(f"[JENS][slide_rail_scan] stop error: {exc}")
        finally:
            try:
                if stop_client is not None:
                    stop_client.disconnect()
            except (OSError, RuntimeError):
                pass

        if self.thread is not None:
            self.thread.join(timeout=self.scan_cycle_seconds + 1.0)

    def _disconnect_client(self) -> None:
        try:
            if self.client is not None:
                self.client.disconnect()
        except (OSError, RuntimeError):
            pass
        finally:
            self.client = None

    def to_extra(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "started": self.started,
            "stop_sent": self.stop_sent,
            "skipped_reason": self.skipped_reason,
            "host": self.host,
            "port": self.port,
            "scan_cycle_seconds": self.scan_cycle_seconds,
            "horizontal_pulse": self.horizontal_pulse,
            "horizontal_speed": self.horizontal_speed,
            "start_result": self.start_result,
            "stop_result": self.stop_result,
        }
