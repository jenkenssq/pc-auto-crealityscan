from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from engine.stress_runner import (
    ROUND_DIR_PREFIX,
    SUMMARY_HTML_NAME,
    SUMMARY_JSON_NAME,
    StressRoundResult,
    StressRunSummary,
    _FileStopFlag,
    _RoundMonitor,
    _build_summary,
    _execute_round,
    _render_stress_summary_html,
    main_stress_round,
    main_stress_run,
    parse_stress_round_args,
    parse_stress_run_args,
    run_stress_round,
    _write_stress_summary,
)


class _FakeProc:
    def __init__(self, lines=None, poll_result=None, pid=1234):
        self._lines = list(lines or [])
        self._poll = poll_result
        self.pid = pid
        self.stdout = _FakeStdout(self._lines)

    def poll(self):
        return self._poll


class _FakeStdout:
    def __init__(self, lines):
        self._iter = iter(lines)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopIteration

    def close(self):
        pass


class _FakeMonitor:
    def __init__(self, frozen=False, poll=None):
        self._frozen = frozen
        self._poll = poll
        self.check_interval_sec = 0.001
        self.closed = False

    def poll(self):
        return self._poll

    def is_frozen(self):
        return self._frozen

    def close(self):
        self.closed = True


class FileStopFlagTests(unittest.TestCase):
    def test_file_stop_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flag_file = Path(tmp) / "stop.flag"
            flag = _FileStopFlag(stop_file=str(flag_file))
            self.assertFalse(flag.is_set())
            flag_file.write_text("stop", encoding="utf-8")
            self.assertTrue(flag.is_set())

    def test_event_stop_flag(self) -> None:
        event = mock.Mock()
        event.is_set.return_value = False
        flag = _FileStopFlag(stop_event=event)
        self.assertFalse(flag.is_set())
        event.is_set.return_value = True
        self.assertTrue(flag.is_set())

    def test_none_flag_not_set(self) -> None:
        self.assertFalse(_FileStopFlag().is_set())


class RoundMonitorTests(unittest.TestCase):
    def test_freezes_after_silence(self) -> None:
        proc = _FakeProc(lines=[])
        monitor = _RoundMonitor(proc, log_root=None, freeze_timeout_sec=0.3, check_interval_sec=0.01)
        self.assertFalse(monitor.is_frozen())
        time.sleep(0.4)
        monitor.poll()
        self.assertTrue(monitor.is_frozen())
        monitor.close()

    def test_not_frozen_after_output_activity(self) -> None:
        proc = _FakeProc(lines=["[JENS] heartbeat\n"] * 3)
        monitor = _RoundMonitor(proc, log_root=None, freeze_timeout_sec=5.0, check_interval_sec=0.01)
        # 等待 reader 线程消费输出并刷新活动时间
        time.sleep(0.2)
        self.assertFalse(monitor.is_frozen())
        self.assertTrue(any("[JENS] heartbeat" in line for line in monitor.output_lines()))
        monitor.close()

    def test_log_advance_refreshes_activity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_root = Path(tmp)
            scan_log = log_root / "scan_log_20260907-000000.txt"
            scan_log.write_text("line1\n", encoding="utf-8")
            proc = _FakeProc(lines=[])
            monitor = _RoundMonitor(proc, log_root=str(log_root), freeze_timeout_sec=0.1, check_interval_sec=0.01)
            # 静默超过冻结阈值：若日志无推进，此刻应判卡死
            time.sleep(0.12)
            monitor.poll()
            self.assertTrue(monitor.is_frozen())
            # 写入新日志 -> 活动刷新，不再判卡死
            with scan_log.open("a", encoding="utf-8") as f:
                f.write("new frame 100\n")
            monitor.poll()
            self.assertFalse(monitor.is_frozen())
            monitor.close()


class ExecuteRoundTests(unittest.TestCase):
    def test_passed(self) -> None:
        with mock.patch("engine.stress_runner._kill_process_tree") as kill:
            status, code = _execute_round(_FakeProc(poll_result=0), _FakeMonitor())
            self.assertEqual((status, code), ("passed", 0))
            kill.assert_not_called()

    def test_failed(self) -> None:
        with mock.patch("engine.stress_runner._kill_process_tree") as kill:
            status, code = _execute_round(_FakeProc(poll_result=1), _FakeMonitor())
            self.assertEqual((status, code), ("failed", 1))
            kill.assert_not_called()

    def test_frozen_kills_process(self) -> None:
        with mock.patch("engine.stress_runner._kill_process_tree") as kill:
            monitor = _FakeMonitor(frozen=True)
            status, code = _execute_round(_FakeProc(poll_result=None), monitor)
            self.assertEqual((status, code), ("frozen", None))
            kill.assert_called_once()


class SummaryTests(unittest.TestCase):
    def test_build_summary_counts(self) -> None:
        results = [
            StressRoundResult(1, "passed", duration_sec=1.0),
            StressRoundResult(2, "failed", reason="步骤失败", duration_sec=2.0),
            StressRoundResult(3, "frozen", reason="软件卡死", duration_sec=3.0),
            StressRoundResult(4, "skipped", duration_sec=0.0),
        ]
        summary = _build_summary("任务A", "C:/x/CrealityScan.exe", 4, Path("."), "s", "e", results, stopped=False)
        self.assertEqual(summary.passed_count, 1)
        self.assertEqual(summary.failed_count, 1)
        self.assertEqual(summary.frozen_count, 1)
        self.assertEqual(summary.skipped_count, 1)
        self.assertEqual(summary.duration_sec, 3.0)
        self.assertEqual(summary.pass_rate, 33.33)

    def test_write_stress_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            results = [
                StressRoundResult(1, "passed", duration_sec=1.0, report_path="r1/report.html"),
                StressRoundResult(2, "frozen", reason="软件卡死", duration_sec=2.0),
            ]
            summary = _build_summary("任务A", "C:/x/CrealityScan.exe", 2, run_dir, "s", "e", results, stopped=False)
            _write_stress_summary(summary)
            json_path = run_dir / SUMMARY_JSON_NAME
            html_path = run_dir / SUMMARY_HTML_NAME
            self.assertTrue(json_path.is_file())
            self.assertTrue(html_path.is_file())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["counts"]["passed"], 1)
            self.assertEqual(payload["counts"]["frozen"], 1)
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["rounds"][1]["status"], "frozen")
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("压测汇总报告", html)
            self.assertIn("卡死", html)
            self.assertIn("通过率", html)

    def test_render_html_escapes_reason(self) -> None:
        results = [StressRoundResult(1, "failed", reason="<脚本>失败", duration_sec=1.0)]
        summary = _build_summary("任务A", "C:/x/CrealityScan.exe", 1, Path("."), "s", "e", results, stopped=False)
        html = _render_stress_summary_html(summary, json.loads(json.dumps({
            "case_name": summary.case_name,
            "status": "failed",
            "total_rounds": 1,
            "started_at": "s",
            "finished_at": "e",
        })))
        self.assertIn("&lt;脚本&gt;失败", html)


class CliWiringTests(unittest.TestCase):
    def test_parse_stress_run_args(self) -> None:
        ns = parse_stress_run_args(["--case", "c.json", "--exe", "e.exe", "--rounds", "50"])
        self.assertEqual(ns.case, "c.json")
        self.assertEqual(ns.exe, "e.exe")
        self.assertEqual(ns.rounds, 50)
        self.assertEqual(ns.freeze_timeout, 180.0)
        self.assertIsNone(ns.stop_file)

    def test_parse_stress_run_args_stop_file(self) -> None:
        ns = parse_stress_run_args(
            ["--case", "c.json", "--exe", "e.exe", "--rounds", "50", "--stop-file", "C:/tmp/stop.flag"]
        )
        self.assertEqual(ns.stop_file, "C:/tmp/stop.flag")

    def test_parse_stress_round_args(self) -> None:
        ns = parse_stress_round_args(["--case", "c.json", "--round-dir", "rd"])
        self.assertEqual(ns.case, "c.json")
        self.assertEqual(ns.round_dir, "rd")

    def test_main_stress_run_delegates(self) -> None:
        with mock.patch("engine.stress_runner.run_stress_case", return_value=0) as run:
            code = main_stress_run(["--case", "c.json", "--exe", "e.exe", "--rounds", "3", "--freeze-timeout", "99"])
            self.assertEqual(code, 0)
            run.assert_called_once_with(
                "c.json", "e.exe", 3,
                freeze_timeout_sec=99.0,
                launch_timeout_sec=120.0,
                popup_timeout_sec=40.0,
                stop_file=None,
            )

    def test_main_stress_run_passes_stop_file(self) -> None:
        with mock.patch("engine.stress_runner.run_stress_case", return_value=0) as run:
            code = main_stress_run(
                ["--case", "c.json", "--exe", "e.exe", "--rounds", "3", "--stop-file", "C:/tmp/stop.flag"]
            )
            self.assertEqual(code, 0)
            run.assert_called_once_with(
                "c.json", "e.exe", 3,
                freeze_timeout_sec=180.0,
                launch_timeout_sec=120.0,
                popup_timeout_sec=40.0,
                stop_file="C:/tmp/stop.flag",
            )

    def test_run_stress_round_delegates_to_run_case_with_run_dir(self) -> None:
        with mock.patch("jens_runner_entry.run_case", return_value=0) as run:
            code = run_stress_round("c.json", "round01")
            self.assertEqual(code, 0)
            run.assert_called_once_with("c.json", run_dir="round01")

    def test_main_stress_round_delegates(self) -> None:
        with mock.patch("engine.stress_runner.run_stress_round", return_value=1) as run:
            code = main_stress_round(["--case", "c.json", "--round-dir", "rd"])
            self.assertEqual(code, 1)
            run.assert_called_once_with("c.json", "rd")


class RunStressCaseTests(unittest.TestCase):
    def test_round_loop_and_recovery(self) -> None:
        """端到端（打桩）：2 轮，第 1 轮通过，第 2 轮失败 -> 触发 recover -> 汇总落盘。"""
        from engine import stress_runner as sr

        case = {
            "case_id": "t",
            "name": "压测任务",
            "app": {"log_dir": ""},
            "steps": [{"id": "common.sleep", "version": "1.0.0", "params": {"seconds": 0}}],
        }

        manager = mock.Mock()
        manager.ensure_running.return_value = 1
        manager.recover.return_value = 1

        outcomes = iter([("passed", 0), ("failed", 1)])

        def fake_execute(proc, monitor):
            status, code = next(outcomes)
            monitor.close()
            return status, code

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(sr, "get_app_root", return_value=Path(tmp)), \
                mock.patch.object(sr, "_load_case", return_value=case), \
                mock.patch.object(sr, "StressProcessManager", return_value=manager), \
                mock.patch.object(sr, "_spawn_round_process", return_value=_FakeProc()), \
                mock.patch.object(sr, "_RoundMonitor", return_value=_FakeMonitor()), \
                mock.patch.object(sr, "_execute_round", side_effect=fake_execute):
            code = sr.run_stress_case("c.json", "C:/x/CrealityScan.exe", 2)

            self.assertEqual(code, 1)
            # 初始启动 + 每轮启动前共 1+rounds=3 次
            self.assertEqual(manager.ensure_running.call_count, 3)
            manager.recover.assert_called_once()

            # 汇总产物
            artifacts = Path(tmp) / "artifacts"
            stress_dirs = [p for p in artifacts.iterdir() if "压测" in p.name]
            self.assertEqual(len(stress_dirs), 1)
            run_dir = stress_dirs[0]
            self.assertTrue((run_dir / SUMMARY_JSON_NAME).is_file())
            self.assertTrue((run_dir / SUMMARY_HTML_NAME).is_file())
            self.assertTrue((run_dir / f"{ROUND_DIR_PREFIX}01").is_dir())
            self.assertTrue((run_dir / f"{ROUND_DIR_PREFIX}02").is_dir())
            payload = json.loads((run_dir / SUMMARY_JSON_NAME).read_text(encoding="utf-8"))
            self.assertEqual(payload["counts"]["passed"], 1)
            self.assertEqual(payload["counts"]["failed"], 1)

    def test_round_spawn_exception_does_not_abort_whole_run(self) -> None:
        """轮次子进程启动抛异常：本轮记失败、尝试恢复、继续下一轮并落汇总。"""
        from engine import stress_runner as sr

        case = {
            "case_id": "t",
            "name": "压测任务",
            "app": {"log_dir": ""},
            "steps": [],
        }
        manager = mock.Mock()
        manager.ensure_running.return_value = 1

        # 第 1 轮启动抛异常，第 2 轮正常通过
        spawn_errors = 1

        def fake_spawn(*args, **kwargs):
            nonlocal spawn_errors
            if spawn_errors > 0:
                spawn_errors -= 1
                raise RuntimeError("cannot launch round process")
            return _FakeProc()

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(sr, "get_app_root", return_value=Path(tmp)), \
                mock.patch.object(sr, "_load_case", return_value=case), \
                mock.patch.object(sr, "StressProcessManager", return_value=manager), \
                mock.patch.object(sr, "_spawn_round_process", side_effect=fake_spawn), \
                mock.patch.object(sr, "_RoundMonitor", return_value=_FakeMonitor()), \
                mock.patch.object(sr, "_execute_round", return_value=("passed", 0)):
            code = sr.run_stress_case("c.json", "C:/x/CrealityScan.exe", 2)

            self.assertEqual(code, 1)  # 有失败轮 -> 整体 FAILED
            # 第 1 轮异常后也触发一次恢复
            self.assertEqual(manager.recover.call_count, 1)
            artifacts = Path(tmp) / "artifacts"
            run_dir = next(p for p in artifacts.iterdir() if "压测" in p.name)
            payload = json.loads((run_dir / SUMMARY_JSON_NAME).read_text(encoding="utf-8"))
            self.assertEqual(payload["counts"]["passed"], 1)
            self.assertEqual(payload["counts"]["failed"], 1)
            self.assertEqual(payload["rounds"][0]["status"], "failed")
            self.assertEqual(payload["rounds"][0]["reason"], "轮次执行异常")

    def test_stop_file_stops_after_current_round(self) -> None:
        """stop-file 出现后：当前轮照常跑完，之后不再启动下一轮，并落汇总（stopped）。"""
        from engine import stress_runner as sr

        case = {
            "case_id": "t",
            "name": "压测任务",
            "app": {"log_dir": ""},
            "steps": [],
        }
        manager = mock.Mock()
        manager.ensure_running.return_value = 1

        with tempfile.TemporaryDirectory() as tmp:
            stop_file = Path(tmp) / "stop.flag"
            with mock.patch.object(sr, "get_app_root", return_value=Path(tmp)), \
                    mock.patch.object(sr, "_load_case", return_value=case), \
                    mock.patch.object(sr, "StressProcessManager", return_value=manager), \
                    mock.patch.object(sr, "_spawn_round_process", return_value=_FakeProc()), \
                    mock.patch.object(sr, "_RoundMonitor", return_value=_FakeMonitor()), \
                    mock.patch.object(sr, "_execute_round", return_value=("passed", 0)):
                # 第 1 轮运行期间写入停止标志
                def _create_stop_on_first_spawn(*args, **kwargs):
                    stop_file.write_text("stop", encoding="utf-8")
                    return _FakeProc()

                with mock.patch.object(sr, "_spawn_round_process", side_effect=_create_stop_on_first_spawn):
                    code = sr.run_stress_case(
                        "c.json", "C:/x/CrealityScan.exe", 5,
                        stop_file=str(stop_file),
                    )

                # 第 1 轮通过后检测到停止 -> 不再启动第 2 轮
                self.assertEqual(code, 1)  # stopped 视为非全通过
                artifacts = Path(tmp) / "artifacts"
                run_dir = next(p for p in artifacts.iterdir() if "压测" in p.name)
                payload = json.loads((run_dir / SUMMARY_JSON_NAME).read_text(encoding="utf-8"))
                self.assertTrue(payload["stopped"])
                self.assertEqual(payload["counts"]["passed"], 1)
                self.assertEqual(payload["total_rounds"], 5)
                self.assertEqual(len(payload["rounds"]), 1)
                self.assertFalse((run_dir / f"{ROUND_DIR_PREFIX}02").exists())


if __name__ == "__main__":
    unittest.main()
