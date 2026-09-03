from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.logs import extract_device_info
from engine.logs import extract_sdk_fps_stats
from jens_runner_entry import _attach_sdk_fps_stats
from steps.crealityscan.scan_until_frames_then_stop.v1_0_0 import impl as scan_impl
from steps.crealityscan.preview_scan.v1_0_0.impl import (
    PREVIEW_SUCCESS_KEYS,
    _wait_log_contains as _wait_preview_log_contains,
)
from steps.crealityscan.scan_until_frames_then_stop.v1_0_0.impl import (
    START_KEY,
    STOP_SUCCESS_KEY,
    _poll_scan_start_from_logs,
    _should_switch_scan_log,
    _try_pick_stalled_scan_log,
    _wait_frames_ge,
    _wait_log_contains,
    _wait_log_contains_any,
)


def _write_text(fp: Path, text: str) -> None:
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(text, encoding="utf-8")


def _append_text(fp: Path, text: str) -> None:
    with fp.open("a", encoding="utf-8") as f:
        f.write(text)



def _set_mtime(fp: Path, ts: float) -> None:
    os.utime(fp, (ts, ts))


class LogRolloverTests(unittest.TestCase):
    def test_extract_device_info_prefers_latest_device_info_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            older_session = logs_root / "20260417095500"
            latest_session = logs_root / "20260417095626"

            older_session.mkdir(parents=True, exist_ok=True)
            latest_session.mkdir(parents=True, exist_ok=True)

            (older_session / "device_info.json").write_text(
                json.dumps(
                    {
                        "camera_name": "OldCam",
                        "camera_serial_number": "OLD-SN",
                        "camera_connection_type": "USB",
                        "camera_firmware_version": "0.9.0",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (latest_session / "device_info.json").write_text(
                json.dumps(
                    {
                        "camera_name": "LatestCam",
                        "camera_serial_number": "LATEST-SN",
                        "camera_connection_type": "WiFi",
                        "camera_firmware_version": "1.2.3",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            now = time.time()
            _set_mtime(older_session, now - 10)
            _set_mtime(latest_session, now)

            info = extract_device_info(str(logs_root))

            self.assertEqual(info["camera_name"], "LatestCam")
            self.assertEqual(info["camera_serial_number"], "LATEST-SN")
            self.assertEqual(info["camera_connection_type"], "WiFi")
            self.assertEqual(info["camera_firmware_version"], "1.2.3")

    def test_extract_device_info_prefers_newest_scan_log_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            older = session_dir / "scan_log_0001.txt"
            newer = session_dir / "scan_log_0002.txt"
            now = time.time()

            _write_text(
                older,
                "\n".join(
                    [
                        "camera name: OldCam",
                        "camera serial number: OLD-SN",
                        "camera connection type: WiFi",
                        "camera firmware version: 1.0.0",
                    ]
                ),
            )
            _set_mtime(older, now - 10)

            _write_text(
                newer,
                "\n".join(
                    [
                        "camera name: NewCam",
                        "camera serial number: NEW-SN",
                    ]
                ),
            )
            _set_mtime(newer, now)

            info = extract_device_info(str(logs_root))

            self.assertEqual(info["camera_name"], "NewCam")
            self.assertEqual(info["camera_serial_number"], "NEW-SN")
            self.assertEqual(info["camera_connection_type"], "WiFi")
            self.assertEqual(info["camera_firmware_version"], "1.0.0")

    def test_wait_frames_ge_switches_to_new_scan_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            first_log = session_dir / "scan_log_0001.txt"
            second_log = session_dir / "scan_log_0002.txt"
            _write_text(first_log, "frame 10\nframe 20\n")
            _set_mtime(first_log, time.time() - 1)

            def create_new_log() -> None:
                time.sleep(0.2)
                _write_text(second_log, "frame 80\nconvert index 120 to file index 120\n")
                _set_mtime(second_log, time.time())

            worker = threading.Thread(target=create_new_log, daemon=True)
            worker.start()
            try:
                active_log, max_frame, pos = _wait_frames_ge(
                    logs_root, first_log, 0, target_frames=100, timeout_sec=2, poll_interval_sec=0.05
                )
            finally:
                worker.join(timeout=1)

            self.assertEqual(active_log, second_log)
            self.assertEqual(max_frame, 120)
            self.assertGreater(pos, 0)

    def test_should_switch_scan_log_requires_effective_signal_in_newer_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            first_log = session_dir / "scan_log_0001.txt"
            second_log = session_dir / "scan_log_0002.txt"
            _write_text(first_log, "frame 10\n")
            _set_mtime(first_log, time.time() - 2)
            _write_text(second_log, "noise only\n")
            _set_mtime(second_log, time.time() - 1)

            self.assertFalse(_should_switch_scan_log(first_log, second_log, pos=0))

            _write_text(second_log, "convert index 42 to file index 42\n")
            _set_mtime(second_log, time.time())

            self.assertTrue(_should_switch_scan_log(first_log, second_log, pos=0))

    def test_stalled_scan_log_selection_prefers_newer_filename_when_old_mtime_is_later(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            first_log = session_dir / "scan_log_20260814-113524.txt"
            second_log = session_dir / "scan_log_20260814-114118.txt"
            now = time.time()

            _write_text(first_log, "frame 138\n")
            _set_mtime(first_log, now)
            _write_text(second_log, "blae run begin\nframe 1622\n")
            _set_mtime(second_log, now - 1)

            candidate = _try_pick_stalled_scan_log(logs_root, first_log)

            self.assertEqual(candidate, second_log)
            self.assertTrue(_should_switch_scan_log(first_log, second_log, pos=0))

    def test_wait_frames_ge_switches_by_filename_when_old_log_mtime_is_later(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            first_log = session_dir / "scan_log_20260814-113524.txt"
            second_log = session_dir / "scan_log_20260814-114118.txt"
            now = time.time()

            _write_text(first_log, "frame 138\n")
            _set_mtime(first_log, now)
            _write_text(second_log, "blae run begin\nframe 1622\n")
            _set_mtime(second_log, now - 1)

            active_log, reached_frame, pos = _wait_frames_ge(
                logs_root,
                first_log,
                first_log.stat().st_size,
                target_frames=200,
                timeout_sec=1,
                poll_interval_sec=0.05,
            )

            self.assertEqual(active_log, second_log)
            self.assertEqual(reached_frame, 1622)
            self.assertGreater(pos, 0)

    def test_wait_frames_ge_retries_stalled_log_switch_on_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            first_log = session_dir / "scan_log_20260814-113524.txt"
            second_log = session_dir / "scan_log_20260814-114118.txt"
            _write_text(first_log, "frame 10\n")

            def create_new_log_after_first_attempt() -> None:
                time.sleep(0.12)
                _write_text(second_log, "blae run begin\nframe 120\n")

            worker = threading.Thread(target=create_new_log_after_first_attempt, daemon=True)
            worker.start()
            try:
                with patch.object(scan_impl, "_try_pick_scan_log", return_value=first_log):
                    active_log, reached_frame, pos = _wait_frames_ge(
                        logs_root,
                        first_log,
                        0,
                        target_frames=100,
                        timeout_sec=1,
                        frame_stall_timeout_sec=0.6,
                        poll_interval_sec=0.02,
                        stalled_log_switch_interval_sec=0.1,
                    )
            finally:
                worker.join(timeout=1)

            self.assertEqual(active_log, second_log)
            self.assertEqual(reached_frame, 120)
            self.assertGreater(pos, 0)

    def test_wait_frames_ge_returns_first_threshold_hit_in_same_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            scan_log = session_dir / "scan_log_0001.txt"
            _write_text(scan_log, "frame 80\nframe 101\nframe 150\n")
            _set_mtime(scan_log, time.time())

            active_log, reached_frame, pos = _wait_frames_ge(
                logs_root, scan_log, 0, target_frames=100, timeout_sec=1, poll_interval_sec=0.05
            )

            self.assertEqual(active_log, scan_log)
            self.assertEqual(reached_frame, 101)
            self.assertGreater(pos, 0)

    def test_wait_frames_ge_handles_split_frame_tokens_across_polls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            scan_log = session_dir / "scan_log_0001.txt"
            _write_text(scan_log, "frame 19")
            _set_mtime(scan_log, time.time())

            def append_split_frame() -> None:
                time.sleep(0.2)
                _append_text(scan_log, "8\nframe 200\n")
                _set_mtime(scan_log, time.time())

            worker = threading.Thread(target=append_split_frame, daemon=True)
            worker.start()
            try:
                active_log, reached_frame, pos = _wait_frames_ge(
                    logs_root, scan_log, 0, target_frames=200, timeout_sec=2, poll_interval_sec=0.05
                )
            finally:
                worker.join(timeout=1)

            self.assertEqual(active_log, scan_log)
            self.assertEqual(reached_frame, 200)
            self.assertGreater(pos, 0)

    def test_wait_frames_ge_supports_convert_index_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            scan_log = session_dir / "scan_log_0001.txt"
            _write_text(
                scan_log,
                "\n".join(
                    [
                        "[2026-05-21 15:34:07.714100][INFO ][6092][::0] frame 0",
                        "[2026-05-21 15:34:07.714599][INFO ][6092][::0] convert index 104 to file index 104",
                        "[2026-05-21 15:34:07.715200][INFO ][6092][::0] frame 0",
                    ]
                ),
            )
            _set_mtime(scan_log, time.time())

            active_log, reached_frame, pos = _wait_frames_ge(
                logs_root, scan_log, 0, target_frames=100, timeout_sec=1, poll_interval_sec=0.05
            )

            self.assertEqual(active_log, scan_log)
            self.assertEqual(reached_frame, 104)
            self.assertGreater(pos, 0)

    def test_wait_log_contains_switches_to_new_scan_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            first_log = session_dir / "scan_log_0001.txt"
            second_log = session_dir / "scan_log_0002.txt"
            _write_text(first_log, "frame 10\n")
            _set_mtime(first_log, time.time() - 1)

            def create_new_log() -> None:
                time.sleep(0.2)
                _write_text(second_log, STOP_SUCCESS_KEY.decode("utf-8", errors="ignore"))
                _set_mtime(second_log, time.time())

            worker = threading.Thread(target=create_new_log, daemon=True)
            worker.start()
            try:
                active_log, pos = _wait_log_contains(
                    logs_root, first_log, 0, STOP_SUCCESS_KEY, timeout_sec=2, poll_interval_sec=0.05
                )
            finally:
                worker.join(timeout=1)

            self.assertEqual(active_log, second_log)
            self.assertGreater(pos, 0)

    def test_poll_scan_start_ignores_preexisting_log_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            scan_log = session_dir / "scan_log_0001.txt"
            _write_text(scan_log, START_KEY.decode("utf-8", errors="ignore") + "\nframe 12\n")
            step_started_at = time.time()
            pre_log_size = scan_log.stat().st_size

            current_fp, pos, scan_buf, scan_origin_py_ts, fallback_start_py_ts, started, log_changed = (
                _poll_scan_start_from_logs(
                    log_root=logs_root,
                    current_fp=None,
                    pos=0,
                    scan_buf=b"",
                    pre_log=scan_log,
                    pre_log_size=pre_log_size,
                    step_started_at=step_started_at,
                    start_keys=(START_KEY,),
                    scan_origin_py_ts=None,
                    fallback_start_py_ts=None,
                    allow_frame_fallback=False,
                )
            )

            self.assertEqual(current_fp, scan_log)
            self.assertEqual(pos, pre_log_size)
            self.assertEqual(scan_buf, b"")
            self.assertFalse(started)
            self.assertTrue(log_changed)
            self.assertIsNone(scan_origin_py_ts)
            self.assertIsNone(fallback_start_py_ts)

            _append_text(scan_log, "frame 13\n")
            _set_mtime(scan_log, time.time())

            current_fp, pos, scan_buf, scan_origin_py_ts, fallback_start_py_ts, started, log_changed = (
                _poll_scan_start_from_logs(
                    log_root=logs_root,
                    current_fp=current_fp,
                    pos=pos,
                    scan_buf=scan_buf,
                    pre_log=scan_log,
                    pre_log_size=pre_log_size,
                    step_started_at=step_started_at,
                    start_keys=(START_KEY,),
                    scan_origin_py_ts=scan_origin_py_ts,
                    fallback_start_py_ts=fallback_start_py_ts,
                    allow_frame_fallback=False,
                )
            )

            self.assertEqual(current_fp, scan_log)
            self.assertFalse(log_changed)
            self.assertFalse(started)
            self.assertIn(b"frame 13", scan_buf)
            self.assertIsNone(scan_origin_py_ts)
            self.assertIsNone(fallback_start_py_ts)

    def test_extract_sdk_fps_stats_uses_latest_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs" / "20260417095626"
            sdk_log = logs_root / "ScannerStreamSDK.log"
            _write_text(
                sdk_log,
                "\n".join(
                    [
                        "[05/19 14:32:38.084454][info][31372][Pipeline.cpp:232] Pipeline start done!",
                        "[05/19 14:32:43.224327][debug][16672][Pipeline.cpp:271] Pipeline streaming... frameset output rate=47.070507fps",
                        "[05/19 14:32:47.978790][debug][30512][Pipeline.cpp:271] Pipeline streaming... frameset output rate=47.590481fps",
                        "[05/19 14:32:46.421767][info][16524][Pipeline.cpp:373] Stop pipeline done!",
                        "[05/19 15:14:24.062611][info][22728][Pipeline.cpp:232] Pipeline start done!",
                        "[05/19 15:14:29.322267][debug][32500][Pipeline.cpp:271] Pipeline streaming... frameset output rate=48.059875fps",
                        "[05/19 15:14:34.323893][debug][32500][Pipeline.cpp:271] Pipeline streaming... frameset output rate=47.590481fps",
                        "[05/19 15:14:35.626463][info][16524][Pipeline.cpp:373] Stop pipeline done!",
                    ]
                ),
            )

            stats = extract_sdk_fps_stats(str(logs_root.parent))

            self.assertEqual(stats["sdk_avg_fps"], 47.825)
            self.assertEqual(stats["sdk_peak_fps"], 48.06)
            self.assertEqual(stats["sdk_min_fps"], 47.59)
            self.assertEqual(stats["sdk_fps_samples"], 2)

    def test_attach_sdk_fps_stats_matches_each_passed_step_to_its_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs" / "20260417095626"
            sdk_log = logs_root / "ScannerStreamSDK.log"
            scan_log = logs_root / "scan_log_20260529-101010.txt"
            _write_text(
                sdk_log,
                "\n".join(
                    [
                        "[05/19 15:14:24.062611][info][22728][Pipeline.cpp:232] Pipeline start done!",
                        "[05/19 15:14:29.322267][debug][32500][Pipeline.cpp:271] Pipeline streaming... frameset output rate=48.059875fps",
                        "[05/19 15:14:34.323893][debug][32500][Pipeline.cpp:271] Pipeline streaming... frameset output rate=47.590481fps",
                        "[05/19 15:14:35.626463][info][16524][Pipeline.cpp:373] Stop pipeline done!",
                        "[05/19 15:15:00.062611][info][22728][Pipeline.cpp:232] Pipeline start done!",
                        "[05/19 15:15:05.322267][debug][32500][Pipeline.cpp:271] Pipeline streaming... frameset output rate=30.000000fps",
                        "[05/19 15:15:10.323893][debug][32500][Pipeline.cpp:271] Pipeline streaming... frameset output rate=31.000000fps",
                        "[05/19 15:15:11.626463][info][16524][Pipeline.cpp:373] Stop pipeline done!",
                    ]
                ),
            )
            _write_text(scan_log, "frame 100\n")

            step_results = [
                {
                    "id": "crealityscan.scan_until_frames_then_stop",
                    "status": "skipped",
                    "extra": {"reason": "start_step_index=5"},
                },
                {
                    "id": "crealityscan.scan_until_frames_then_stop",
                    "status": "passed",
                    "extra": {
                        "log_file": str(scan_log),
                        "scan_started_log_at": "2026-05-19T15:14:25.000000",
                        "stop_click_log_at": "2026-05-19T15:14:34.000000",
                    },
                },
                {
                    "id": "crealityscan.scan_until_frames_then_stop",
                    "status": "passed",
                    "extra": {
                        "log_file": str(scan_log),
                        "scan_started_log_at": "2026-05-19T15:15:01.000000",
                        "stop_click_log_at": "2026-05-19T15:15:10.000000",
                    },
                },
                {
                    "id": "crealityscan.scan_until_frames_then_stop",
                    "status": "failed",
                    "extra": {},
                },
            ]
            case = {"app": {"log_dir": ""}}

            _attach_sdk_fps_stats(step_results, case)

            self.assertNotIn("avg_fps", step_results[0]["extra"])
            self.assertEqual(step_results[1]["extra"]["avg_fps"], 47.825)
            self.assertEqual(step_results[1]["extra"]["peak_fps"], 48.06)
            self.assertEqual(step_results[1]["extra"]["min_fps"], 47.59)
            self.assertEqual(step_results[1]["extra"]["fps_seconds_count"], 2)
            self.assertEqual(step_results[2]["extra"]["avg_fps"], 30.5)
            self.assertEqual(step_results[2]["extra"]["peak_fps"], 31.0)
            self.assertEqual(step_results[2]["extra"]["min_fps"], 30.0)
            self.assertNotEqual(step_results[1]["extra"]["avg_fps"], step_results[2]["extra"]["avg_fps"])
            self.assertNotIn("avg_fps", step_results[3]["extra"])

    def test_poll_scan_start_switches_to_recent_new_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            first_log = session_dir / "scan_log_0001.txt"
            second_log = session_dir / "scan_log_0002.txt"
            _write_text(first_log, "warmup\n")
            _set_mtime(first_log, time.time() - 2)
            step_started_at = time.time()

            _write_text(second_log, "frame 88\n")
            _set_mtime(second_log, step_started_at + 0.1)

            current_fp, pos, scan_buf, scan_origin_py_ts, fallback_start_py_ts, started, log_changed = (
                _poll_scan_start_from_logs(
                    log_root=logs_root,
                    current_fp=None,
                    pos=0,
                    scan_buf=b"",
                    pre_log=first_log,
                    pre_log_size=first_log.stat().st_size,
                    step_started_at=step_started_at,
                    start_keys=(START_KEY,),
                    scan_origin_py_ts=None,
                    fallback_start_py_ts=None,
                )
            )

            self.assertEqual(current_fp, second_log)
            self.assertTrue(log_changed)
            self.assertTrue(started)
            self.assertGreater(pos, 0)
            self.assertIn(b"frame 88", scan_buf)
            self.assertIsNone(scan_origin_py_ts)
            self.assertIsNotNone(fallback_start_py_ts)

    def test_poll_scan_start_switches_to_recent_new_log_regardless_of_previous_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            first_log = session_dir / "scan_log_0001.txt"
            second_log = session_dir / "scan_log_0002.txt"
            _write_text(first_log, "historical frame 12\n")
            _set_mtime(first_log, time.time() - 2)
            step_started_at = time.time()

            _write_text(second_log, "obscan_scan_start\nframe 88\n")
            _set_mtime(second_log, step_started_at + 0.1)

            current_fp, pos, scan_buf, scan_origin_py_ts, fallback_start_py_ts, started, log_changed = (
                _poll_scan_start_from_logs(
                    log_root=logs_root,
                    current_fp=None,
                    pos=0,
                    scan_buf=b"",
                    pre_log=first_log,
                    pre_log_size=first_log.stat().st_size,
                    step_started_at=step_started_at,
                    start_keys=(START_KEY,),
                    scan_origin_py_ts=None,
                    fallback_start_py_ts=None,
                )
            )

            self.assertEqual(current_fp, second_log)
            self.assertTrue(log_changed)
            self.assertTrue(started)
            self.assertGreater(pos, 0)
            self.assertIn(b"frame 88", scan_buf)

    def test_preview_wait_log_contains_switches_to_new_scan_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            first_log = session_dir / "scan_log_0001.txt"
            second_log = session_dir / "scan_log_0002.txt"
            _write_text(first_log, "preview warmup\n")
            _set_mtime(first_log, time.time() - 1)

            def create_new_log() -> None:
                time.sleep(0.2)
                _write_text(second_log, PREVIEW_SUCCESS_KEYS[0].decode("utf-8", errors="ignore"))
                _set_mtime(second_log, time.time())

            worker = threading.Thread(target=create_new_log, daemon=True)
            worker.start()
            try:
                active_log, pos, matched = _wait_preview_log_contains(
                    logs_root, first_log, 0, PREVIEW_SUCCESS_KEYS, timeout_sec=2, poll_interval_sec=0.05
                )
            finally:
                worker.join(timeout=1)

            self.assertEqual(active_log, second_log)
            self.assertGreater(pos, 0)
            self.assertEqual(matched, PREVIEW_SUCCESS_KEYS[0])

    def test_preview_wait_log_contains_drains_old_log_before_switch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            first_log = session_dir / "scan_log_0001.txt"
            second_log = session_dir / "scan_log_0002.txt"
            _write_text(first_log, "preview baseline\n")
            start_pos = first_log.stat().st_size
            _set_mtime(first_log, time.time() - 1)

            with first_log.open("ab") as stream:
                stream.write(PREVIEW_SUCCESS_KEYS[0] + b"\n")
            _write_text(second_log, "new log started\n")
            _set_mtime(second_log, time.time())

            active_log, pos, matched = _wait_preview_log_contains(
                logs_root,
                first_log,
                start_pos,
                PREVIEW_SUCCESS_KEYS,
                timeout_sec=1,
                poll_interval_sec=0.05,
            )

            self.assertEqual(active_log, first_log)
            self.assertEqual(pos, first_log.stat().st_size)
            self.assertEqual(matched, PREVIEW_SUCCESS_KEYS[0])

    def test_preview_success_matches_change_to_preview_success_keyword(self) -> None:
        """部分版本（如 Raptor Pro USB）仅输出 change to preview success，也应判定预览成功。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "Logs"
            session_dir = logs_root / "session_001"
            log_file = session_dir / "scan_log_0001.txt"
            _write_text(
                log_file,
                "[2026-09-03 09:40:55.007014][INFO ][4176][::0] change to preview success !\n",
            )

            active_log, pos, matched = _wait_preview_log_contains(
                logs_root, log_file, 0, PREVIEW_SUCCESS_KEYS, timeout_sec=1, poll_interval_sec=0.05
            )

            self.assertEqual(active_log, log_file)
            self.assertGreater(pos, 0)
            self.assertEqual(matched, b"change to preview success")


if __name__ == "__main__":
    unittest.main()
