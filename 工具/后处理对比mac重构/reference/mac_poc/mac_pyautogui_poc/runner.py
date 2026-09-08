from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

if __package__ in {None, ""}:
    _CURRENT = Path(__file__).resolve()
    _OUTPUT_ROOT = _CURRENT.parents[1]
    _PROJECT_ROOT = _CURRENT.parents[2]
    if str(_OUTPUT_ROOT) not in sys.path:
        sys.path.insert(0, str(_OUTPUT_ROOT))
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    from mac_pyautogui_poc.desktop_api import DesktopConfig, PyAutoGuiDesktop
    from mac_pyautogui_poc.registry import resolve_step
    from mac_pyautogui_poc.runtime import artifacts_root, project_root
else:
    from .desktop_api import DesktopConfig, PyAutoGuiDesktop
    from .registry import resolve_step
    from .runtime import artifacts_root, project_root


def _ensure_project_importable() -> None:
    root = str(project_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _safe_name(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(text or "case"))
    return cleaned.strip("_") or "case"


def _load_case(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("case json must be an object")
    return data


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_report(
    case_name: str,
    started_at: str,
    finished_at: str,
    step_results: List[Dict[str, Any]],
    device_info: Dict[str, str],
) -> str:
    _ensure_project_importable()
    from engine.report_html import render_report_html

    return render_report_html(
        case_name=case_name,
        started_at=started_at,
        finished_at=finished_at,
        step_results=step_results,
        keyword_hits={},
        device_info=device_info,
    )


def _preflight(case: Dict[str, Any], desktop: PyAutoGuiDesktop) -> Dict[str, str]:
    app = case.get("app") if isinstance(case.get("app"), dict) else {}
    expected = app.get("expected_resolution")
    expected_tuple = None
    if isinstance(expected, list) and len(expected) == 2:
        expected_tuple = (int(expected[0]), int(expected[1]))
    info = desktop.check_environment(expected_tuple)
    pause_before_start = float(app.get("pause_before_start_sec", 3.0) or 0.0)
    manual_hint = str(
        app.get("manual_foreground_hint")
        or "Before start, bring CrealityScan to the foreground on the primary monitor and keep it visible."
    ).strip()
    print(f"[POC] {manual_hint}")
    if pause_before_start > 0:
        print(f"[POC] Starting in {pause_before_start:.1f}s ...")
        time.sleep(pause_before_start)
    info["camera_name"] = "macOS Desktop"
    info["camera_connection_type"] = "PyAutoGUI"
    info["camera_serial_number"] = "-"
    info["camera_firmware_version"] = f"{info['screen_width']}x{info['screen_height']}"
    return info


def execute_case(case_path: Path) -> Tuple[Path, List[Dict[str, Any]], bool]:
    case = _load_case(case_path)
    case_name = str(case.get("name") or case_path.stem)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = artifacts_root() / f"{_safe_name(case_name)}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    desktop = PyAutoGuiDesktop(
        DesktopConfig(
            default_confidence=float(os.environ.get("PYAUTO_POC_CONFIDENCE", "0.9") or 0.9),
            pause_sec=float(os.environ.get("PYAUTO_POC_PAUSE", "0.1") or 0.1),
            fail_safe=True,
        )
    )
    env_info = _preflight(case, desktop)

    steps = case.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("case.steps must be a non-empty list")

    step_results: List[Dict[str, Any]] = []
    started_at = datetime.now().isoformat(timespec="seconds")
    all_passed = True

    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"step[{idx}] must be an object")
        step_id = str(step.get("id") or "")
        name = str(step.get("name") or step_id)
        version = str(step.get("version") or "pyautogui-poc")
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        fn = resolve_step(step_id)
        started = time.time()
        failure_shot = None
        try:
            extra = fn(
                {
                    "case": case,
                    "run_dir": str(run_dir),
                    "step_index": idx,
                    "desktop": desktop,
                    "env_info": env_info,
                },
                params,
            )
            screenshot = ""
            if isinstance(extra, dict) and extra.get("snapshot"):
                screenshot = str(extra.get("snapshot") or "")
            step_results.append(
                {
                    "id": step_id,
                    "version": version,
                    "name": name,
                    "status": "passed",
                    "duration_sec": round(time.time() - started, 3),
                    "attempt": 1,
                    "screenshot": screenshot,
                    "extra": extra if isinstance(extra, dict) else {},
                }
            )
        except Exception:
            all_passed = False
            failure_shot = run_dir / "screenshots" / f"step{idx:03d}_failed.png"
            failure_shot.parent.mkdir(parents=True, exist_ok=True)
            try:
                desktop.screenshot(str(failure_shot))
            except Exception:
                failure_shot = None
            step_results.append(
                {
                    "id": step_id,
                    "version": version,
                    "name": name,
                    "status": "failed",
                    "duration_sec": round(time.time() - started, 3),
                    "attempt": 1,
                    "screenshot": str(failure_shot) if failure_shot else "",
                    "error": traceback.format_exc(),
                }
            )
            break

    finished_at = datetime.now().isoformat(timespec="seconds")
    report_path = run_dir / "report.html"
    report_path.write_text(
        _render_report(case_name, started_at, finished_at, step_results, env_info),
        encoding="utf-8",
    )
    _write_json(
        run_dir / "result.json",
        {
            "case_path": str(case_path),
            "case_name": case_name,
            "started_at": started_at,
            "finished_at": finished_at,
            "all_passed": all_passed,
            "env_info": env_info,
            "step_results": step_results,
        },
    )
    return run_dir, step_results, all_passed


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PyAutoGUI macOS POC runner")
    parser.add_argument(
        "--case",
        default=str(Path(__file__).resolve().parent / "example_case.json"),
        help="Path to case json",
    )
    args = parser.parse_args(argv)

    run_dir, _, all_passed = execute_case(Path(args.case).resolve())
    print(f"[POC] run_dir={run_dir}")
    print(f"[POC] report={run_dir / 'report.html'}")
    print(f"[POC] status={'PASSED' if all_passed else 'FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
