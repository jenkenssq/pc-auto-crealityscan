from __future__ import annotations

import re
import shutil
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from airtest.core.api import auto_setup  # type: ignore
from airtest.core.api import connect_device  # type: ignore

from engine.defaults import DEFAULT_KEYWORDS
from engine.executor import execute_case
from engine.fps_stat_xlsx import WORKBOOK_NAME as FPS_STAT_WORKBOOK_NAME
from engine.io import dump_json, load_json
from engine.logs import copy_logs, extract_device_info, extract_fps_metrics_by_phase, extract_sdk_fps_sessions, scan_keywords
from engine.report_html import render_report_html
from engine.scan_fps_xlsx import write_scan_fps_workbook
from engine.system_env import collect_environment_info
from jens_runtime import get_app_root, get_resource_root


_LIGHTWEIGHT_KEYWORD_MAX_MATCHES = 30
_LIGHTWEIGHT_LOG_TAIL_BYTES = 256 * 1024


def _safe_dir_name(name: str) -> str:
    name = name.strip() or "case"
    name = re.sub(r'[<>:"/\\\\|?*]+', "_", name)
    return name


def _safe_file_name_part(text: str, default: str) -> str:
    value = (text or "").strip()
    value = re.sub(r'[<>:"/\\\\|?*]+', "_", value)
    value = re.sub(r"\s+", "_", value)
    value = value.strip("._ ")
    return value or default


def _install_airtest_image_naming_patch() -> None:
    import airtest.core.api as airtest_api  # type: ignore
    import airtest.core.cv as airtest_cv  # type: ignore
    from airtest.aircv import aircv  # type: ignore
    from airtest.core.cv import G, ST  # type: ignore

    counter = {"value": 0}

    def _next_image_name(ext: str = ".jpg") -> str:
        counter["value"] += 1
        step_index = _safe_file_name_part(str(os.environ.get("JENS_CURRENT_STEP_INDEX") or ""), "step000")
        step_name = _safe_file_name_part(
            str(os.environ.get("JENS_CURRENT_STEP_NAME_SAFE") or os.environ.get("JENS_CURRENT_STEP_NAME") or ""),
            "unknown_step",
        )
        attempt = _safe_file_name_part(str(os.environ.get("JENS_CURRENT_STEP_ATTEMPT") or ""), "1")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{step_index}_{step_name}_attempt{attempt}_{stamp}_{counter['value']:03d}{ext}"

    def _patched_try_log_screen(screen=None, quality=None, max_size=None, depth=None):
        if not ST.LOG_DIR or not ST.SAVE_IMAGE:
            return None
        if not quality:
            quality = ST.SNAPSHOT_QUALITY
        if not max_size:
            max_size = ST.IMAGE_MAXSIZE
        if screen is None:
            screen = G.DEVICE.snapshot(quality=quality)
        if screen is None:
            return None

        filename = _next_image_name(".jpg")
        Path(ST.LOG_DIR).mkdir(parents=True, exist_ok=True)
        filepath = os.path.join(ST.LOG_DIR, filename)
        aircv.imwrite(filepath, screen, quality, max_size=max_size)
        return {"screen": filename, "resolution": aircv.get_resolution(screen)}

    airtest_cv.try_log_screen = _patched_try_log_screen
    airtest_api.try_log_screen = _patched_try_log_screen


def _status_text(all_passed: bool) -> str:
    return "passed" if all_passed else "failed"


def _failed_step_name(step_results: list[dict]) -> str:
    for item in step_results:
        if str(item.get("status") or "").lower() != "failed":
            continue
        return str(item.get("name") or item.get("id") or "").strip()
    return ""


def _device_info_from_env() -> dict[str, str]:
    info = {
        "camera_name": str(os.environ.get("JENS_DEVICE_CAMERA_NAME") or "").strip(),
        "camera_serial_number": str(os.environ.get("JENS_DEVICE_CAMERA_SN") or "").strip(),
        "camera_connection_type": str(os.environ.get("JENS_DEVICE_CONNECTION_TYPE") or "").strip(),
        "camera_firmware_version": str(os.environ.get("JENS_DEVICE_FIRMWARE_VERSION") or "").strip(),
    }
    return {key: value for key, value in info.items() if value}


def _write_summary_json(
    run_dir: Path,
    case_name: str,
    started_at: str,
    finished_at: str,
    all_passed: bool,
    step_results: list[dict],
    keyword_hits: dict[str, list[str]],
    device_info: dict[str, str],
    report_path: Path,
    has_airtest_ocr_debug: bool,
    scan_fps_xlsx_path: str = "",
    scan_fps_xlsx_error: str = "",
    fps_stat_xlsx_path: str = "",
    fps_stat_xlsx_error: str = "",
    ) -> None:
    retained_items = (
        (
            ["report.html", "result.json", "summary.json", "airtest/ocr_fps_*"]
            if has_airtest_ocr_debug
            else ["report.html", "result.json", "summary.json"]
        )
        if all_passed
        else ["report.html", "result.json", "summary.json", "airtest/", "logs/", "screenshots/"]
    )
    if scan_fps_xlsx_path:
        retained_items.append("scan_fps_summary.xlsx")
    if fps_stat_xlsx_path:
        retained_items.append(FPS_STAT_WORKBOOK_NAME)
    dump_json(
        str(run_dir / "summary.json"),
        {
            "case_name": case_name,
            "status": _status_text(all_passed),
            "artifact_mode": ("lightweight" if all_passed else "debug"),
            "started_at": started_at,
            "finished_at": finished_at,
            "step_counts": {
                "total": len(step_results),
                "passed": sum(1 for item in step_results if item.get("status") == "passed"),
                "failed": sum(1 for item in step_results if item.get("status") == "failed"),
            },
            "failed_step_name": _failed_step_name(step_results),
            "keyword_hit_counts": {key: len(lines) for key, lines in keyword_hits.items()},
            "device_info": device_info,
            "report_path": str(report_path),
            "result_path": str(run_dir / "result.json"),
            "scan_fps_xlsx_path": scan_fps_xlsx_path,
            "scan_fps_xlsx_error": scan_fps_xlsx_error,
            "fps_stat_xlsx_path": fps_stat_xlsx_path,
            "fps_stat_xlsx_error": fps_stat_xlsx_error,
            "retained_items": retained_items,
        },
    )


def _attach_sdk_fps_stats(step_results: list[dict], case: dict) -> None:
    app = case.get("app", {}) if isinstance(case.get("app"), dict) else {}
    logs_root = str(app.get("log_dir") or "").strip()
    scan_steps: list[tuple[dict, datetime, Optional[datetime]]] = []

    for item in step_results:
        if str(item.get("id") or "") != "crealityscan.scan_until_frames_then_stop":
            continue
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        extra = dict(extra)
        for key in (
            "avg_fps",
            "peak_fps",
            "min_fps",
            "fps_seconds_count",
            "sdk_fps_sessions_count",
            "sdk_fps_session_start_at",
            "sdk_fps_session_stop_at",
        ):
            extra.pop(key, None)
        item["extra"] = extra
        if str(item.get("status") or "") != "passed":
            continue

        start_text = str(extra.get("scan_started_log_at") or "").strip()
        if not start_text:
            continue
        try:
            scan_started_at = datetime.fromisoformat(start_text)
        except ValueError:
            continue

        stop_text = str(extra.get("stop_click_log_at") or "").strip()
        try:
            stop_clicked_at = datetime.fromisoformat(stop_text) if stop_text else None
        except ValueError:
            stop_clicked_at = None
        scan_steps.append((item, scan_started_at, stop_clicked_at))

        if not logs_root:
            log_file = str(extra.get("log_file") or "").strip()
            if log_file:
                logs_root = str(Path(log_file).parent)

    if not logs_root or not scan_steps:
        return

    sdk_sessions = extract_sdk_fps_sessions(logs_root, year_hint=scan_steps[0][1].year)
    if not sdk_sessions:
        return

    parsed_sessions: list[tuple[int, datetime, datetime, dict]] = []
    for index, session in enumerate(sdk_sessions):
        try:
            session_started_at = datetime.fromisoformat(str(session.get("start_at") or ""))
            session_stopped_at = datetime.fromisoformat(str(session.get("stop_at") or ""))
        except ValueError:
            continue
        parsed_sessions.append((index, session_started_at, session_stopped_at, session))

    used_session_indexes: set[int] = set()
    tolerance_sec = 5.0
    for item, scan_started_at, stop_clicked_at in scan_steps:
        scan_end = stop_clicked_at or scan_started_at
        candidates = [
            session
            for session in parsed_sessions
            if session[0] not in used_session_indexes
            and session[1].timestamp() <= scan_started_at.timestamp() + tolerance_sec
            and session[2].timestamp() >= scan_end.timestamp() - tolerance_sec
        ]
        if not candidates:
            continue

        matched = min(candidates, key=lambda session: abs((scan_started_at - session[1]).total_seconds()))
        session_index, session_started_at, session_stopped_at, sdk_stats = matched
        used_session_indexes.add(session_index)

        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        extra = dict(extra)
        extra["avg_fps"] = sdk_stats.get("avg_fps")
        extra["peak_fps"] = sdk_stats.get("peak_fps")
        extra["min_fps"] = sdk_stats.get("min_fps")
        extra["fps_seconds_count"] = sdk_stats.get("samples")
        extra["sdk_fps_sessions_count"] = 1
        extra["sdk_fps_session_start_at"] = session_started_at.isoformat(timespec="microseconds")
        extra["sdk_fps_session_stop_at"] = session_stopped_at.isoformat(timespec="microseconds")
        item["extra"] = extra


def _cleanup_lightweight_artifacts(run_dir: Path) -> bool:
    airtest_dir = run_dir / "airtest"
    kept_airtest_debug = False
    if airtest_dir.is_dir():
        keep_files = {p.resolve() for p in airtest_dir.glob("ocr_fps_*") if p.is_file()}
        if keep_files:
            kept_airtest_debug = True
            for p in sorted(airtest_dir.rglob("*"), reverse=True):
                try:
                    if p.is_file():
                        if p.resolve() in keep_files:
                            continue
                        p.unlink()
                    elif p.is_dir():
                        p.rmdir()
                except Exception:
                    continue
            # 如果目录被清空则删除；否则保留用于 OCR 调试
            try:
                if not any(airtest_dir.iterdir()):
                    airtest_dir.rmdir()
                    kept_airtest_debug = False
            except Exception:
                pass
        else:
            shutil.rmtree(airtest_dir, ignore_errors=True)
    elif airtest_dir.exists():
        try:
            airtest_dir.unlink()
        except Exception:
            pass

    for name in ("logs", "screenshots"):
        path = run_dir / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            try:
                path.unlink()
            except Exception:
                pass
    return kept_airtest_debug


def _fps_stat_connection(case: dict, device_info: Optional[dict]) -> str:
    """返回归一化连接方式：Wi-Fi / USB / 空串（优先任务配置，回退设备信息）。"""
    from jens_platform.task_generator import CONNECTION_USB, CONNECTION_WIFI

    raw = str(case.get("connection_type") or "").strip().lower().replace("_", "-")
    if raw in {"wifi", "wi-fi", "wlan"}:
        return CONNECTION_WIFI
    if raw in {"usb"}:
        return CONNECTION_USB
    info = device_info if isinstance(device_info, dict) else {}
    device_conn = str(info.get("camera_connection_type") or "").lower()
    if "usb" in device_conn:
        return CONNECTION_USB
    if "wifi" in device_conn or "wi-fi" in device_conn:
        return CONNECTION_WIFI
    return ""


def _fps_stat_fallback_mode_name(preset_key: str) -> str:
    key = preset_key.lower()
    if "with_marker" in key:
        # Pika 等机型的“有标志点”线激光分 标准/均衡/快速 三种。
        if key.rstrip(".").endswith("standard"):
            return "有标志点-标准"
        if key.rstrip(".").endswith("balanced"):
            return "有标志点-均衡"
        if key.rstrip(".").endswith("fast"):
            return "有标志点-快速"
        return "有标志点"
    if "no_marker" in key:
        # P1/P1S 等机型无标记点分“交叉线/平行线”两种。
        if key.rstrip(".").endswith("cross"):
            return "无标记点-交叉线"
        if key.rstrip(".").endswith("parallel"):
            return "无标记点-平行线"
        return "无标记点"
    for token, name in (
        ("face", "人脸"),
        ("body", "人体"),
        ("large", "大物体"),
        ("medium", "中物体"),
        ("small", "小物体"),
        ("cross", "交叉"),
        ("parallel", "平行线"),
        ("single", "单线"),
    ):
        if token in key:
            return name
    return preset_key


def _fps_stat_module_and_modes(case: dict, connection_type: str) -> tuple[str, str, list[str]]:
    """从任务步骤推导模组名与模式业务短名（按执行顺序）。"""
    from jens_platform.task_generator import MODULE_PRESET_SOURCES, fps_stat_mode_plan

    prefix = "crealityscan.configure_scan_params_"
    module_key = ""
    preset_keys: list[str] = []
    for step in case.get("steps", []):
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id") or "")
        if not step_id.startswith(prefix):
            continue
        suffix = step_id[len(prefix):]
        if not module_key:
            by_lower = {key.lower(): key for key in MODULE_PRESET_SOURCES}
            module_key = by_lower.get(suffix.replace("_", " ").lower(), "")
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        preset = str(params.get("preset") or "").strip()
        if preset:
            preset_keys.append(preset)
    if not module_key:
        return "", "", []
    source = MODULE_PRESET_SOURCES[module_key]
    reverse = {key: name for name, key in fps_stat_mode_plan(module_key, connection_type)}
    mode_names = [reverse.get(key) or _fps_stat_fallback_mode_name(key) for key in preset_keys]
    return source.module_name, source.display_name, mode_names


def _write_fps_stat_workbook(
    case: dict,
    run_dir: Path,
    device_info: Optional[dict],
    started_at: str = "",
    finished_at: str = "",
) -> str:
    """帧率统计任务运行后，按模板把各模式预览/扫描/稳定帧率写入 帧率统计.xlsx。"""
    app = case.get("app") if isinstance(case.get("app"), dict) else {}
    logs_root = str(app.get("log_dir") or "").strip()
    if not logs_root:
        return ""
    connection = _fps_stat_connection(case, device_info)
    if not connection:
        return ""
    _module_key, module_display, mode_names = _fps_stat_module_and_modes(case, connection)
    if not mode_names:
        return ""

    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None
    try:
        start_dt = datetime.fromisoformat(started_at) if started_at else None
    except ValueError:
        pass
    try:
        end_dt = datetime.fromisoformat(finished_at) if finished_at else None
    except ValueError:
        pass
    blocks = extract_fps_metrics_by_phase(logs_root, start_at=start_dt, end_at=end_dt)
    if not blocks:
        return ""

    from engine.fps_stat_xlsx import build_fps_rows, write_fps_stat_workbook

    env = collect_environment_info(logs_root)
    info = device_info if isinstance(device_info, dict) else {}
    firmware = str(info.get("camera_firmware_version") or "").strip()
    rows = build_fps_rows(mode_names, blocks)
    out_path = run_dir / FPS_STAT_WORKBOOK_NAME
    return write_fps_stat_workbook(
        out_path,
        software_version=str(env.get("software_version") or ""),
        module_display_name=module_display,
        connection_type=connection,
        system_info=env,
        firmware_version=firmware,
        wifi_handle_version=str(env.get("wifi_handle_version") or ""),
        wifi_band=str(env.get("wifi_band") or ""),
        fps_rows=rows,
    )


def run_case(case_path: Optional[str] = None) -> int:
    app_root = get_app_root()
    resource_root = get_resource_root()
    resolved_case_path = str(case_path or (resource_root / "cases" / "example_case.json"))
    case = load_json(resolved_case_path)

    case_name = str(case.get("name") or case.get("case_id") or "case")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = app_root / "artifacts" / f"{_safe_dir_name(case_name)}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    _install_airtest_image_naming_patch()
    auto_setup(str(resource_root / "jens_runner.air" / "main.py"), logdir=str(run_dir / "airtest"))

    app = case.get("app", {}) if isinstance(case.get("app"), dict) else {}
    device_uri = str(app.get("device_uri") or "Windows:///")
    connect_device(device_uri)

    started_at = datetime.now().isoformat(timespec="seconds")
    step_results, all_passed = execute_case(case, str(run_dir))
    _attach_sdk_fps_stats(step_results, case)
    finished_at = datetime.now().isoformat(timespec="seconds")

    creality_logs_dir = str(app.get("log_dir") or "")
    keywords = case.get("keywords")
    if not isinstance(keywords, list) or not all(isinstance(x, str) for x in keywords):
        keywords = DEFAULT_KEYWORDS
    device_info = _device_info_from_env()
    if not device_info and creality_logs_dir:
        device_info = extract_device_info(creality_logs_dir, max_bytes_per_file=_LIGHTWEIGHT_LOG_TAIL_BYTES)
    scan_fps_xlsx_path = ""
    scan_fps_xlsx_error = ""
    try:
        scan_fps_xlsx_path = write_scan_fps_workbook(case, step_results, run_dir, device_info=device_info) or ""
        if scan_fps_xlsx_path:
            print(f"[JENS] scan_fps_xlsx={scan_fps_xlsx_path}")
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        scan_fps_xlsx_error = str(exc)
        print(f"[JENS] scan_fps_xlsx_failed error={scan_fps_xlsx_error}")

    is_fps_stat = (
        str(case.get("task_kind") or "") == "帧率统计" or "帧率统计" in case_name
    )
    fps_stat_xlsx_path = ""
    fps_stat_xlsx_error = ""
    if is_fps_stat:
        try:
            fps_stat_xlsx_path = (
                _write_fps_stat_workbook(case, run_dir, device_info, started_at=started_at, finished_at=finished_at) or ""
            )
            if fps_stat_xlsx_path:
                print(f"[JENS] fps_stat_xlsx={fps_stat_xlsx_path}")
        except Exception as exc:
            fps_stat_xlsx_error = str(exc)
            print(f"[JENS] fps_stat_xlsx_failed error={fps_stat_xlsx_error}")
    keyword_hits = (
        scan_keywords(
            creality_logs_dir,
            keywords=list(keywords),
            max_matches=_LIGHTWEIGHT_KEYWORD_MAX_MATCHES,
            max_bytes_per_file=_LIGHTWEIGHT_LOG_TAIL_BYTES,
        )
        if creality_logs_dir
        else {}
    )

    dump_json(
        str(run_dir / "result.json"),
        {
            "case": case,
            "step_results": step_results,
            "all_passed": all_passed,
            "started_at": started_at,
            "finished_at": finished_at,
            "device_info": device_info,
            "scan_fps_xlsx_path": scan_fps_xlsx_path,
            "scan_fps_xlsx_error": scan_fps_xlsx_error,
            "fps_stat_xlsx_path": fps_stat_xlsx_path,
            "fps_stat_xlsx_error": fps_stat_xlsx_error,
        },
    )

    task_steps = case.get("steps") if isinstance(case.get("steps"), list) else []
    total_mode_count = sum(
        1
        for step in task_steps
        if str(step.get("id") or "").startswith("crealityscan.configure_scan_params_")
    )

    report_path = run_dir / "report.html"
    report_path.write_text(
        render_report_html(
            case_name=case_name,
            started_at=started_at,
            finished_at=finished_at,
            step_results=step_results,
            keyword_hits=keyword_hits,
            device_info=device_info,
            total_mode_count=total_mode_count,
        ),
        encoding="utf-8",
    )
    has_airtest_ocr_debug = any((run_dir / "airtest").glob("ocr_fps_*"))

    if all_passed:
        kept_airtest_ocr_debug = _cleanup_lightweight_artifacts(run_dir)
        has_airtest_ocr_debug = bool(kept_airtest_ocr_debug)
    elif creality_logs_dir:
        copied_logs_dir = run_dir / "logs" / "crealityscan"
        copy_logs(creality_logs_dir, str(copied_logs_dir))

    _write_summary_json(
        run_dir=run_dir,
        case_name=case_name,
        started_at=started_at,
        finished_at=finished_at,
        all_passed=all_passed,
        step_results=step_results,
        keyword_hits=keyword_hits,
        device_info=device_info,
        report_path=report_path,
        has_airtest_ocr_debug=has_airtest_ocr_debug,
        scan_fps_xlsx_path=scan_fps_xlsx_path,
        scan_fps_xlsx_error=scan_fps_xlsx_error,
        fps_stat_xlsx_path=fps_stat_xlsx_path,
        fps_stat_xlsx_error=fps_stat_xlsx_error,
    )

    print(f"[JENS] run_dir={run_dir}")
    print(f"[JENS] report={report_path}")
    print(f"[JENS] status={'PASSED' if all_passed else 'FAILED'}")
    return 0 if all_passed else 1
