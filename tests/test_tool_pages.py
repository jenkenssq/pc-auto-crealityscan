from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets  # type: ignore

from jens_platform.main import MainWindow
from jens_platform.tool_pages import (
    CalibrationScorePage,
    FirmwareUpgradePage,
    PostprocessComparePage,
    ToolErrorPage,
)


class ToolPageIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @staticmethod
    def _write_tool_fixtures(base_dir: Path) -> Path:
        project_root = base_dir / "pc自动化工具"
        project_root.mkdir()
        tools_root = project_root / "工具"
        tools_root.mkdir()
        score_root = tools_root / "标定分数查看工具"
        score_root.mkdir()
        (score_root / "parser.py").write_text(
            textwrap.dedent(
                """
                from pathlib import Path

                def get_latest_log_file():
                    return Path(__file__)

                def parse_log_file(_path):
                    return {
                        "device_name": "Otter",
                        "sn_code": "SN001",
                        "calibration_board": "BOARD001",
                        "calibration_score": "93.50",
                        "firmware_version": "1.0.0",
                        "log_file": "scan_log.txt",
                    }
                """
            ),
            encoding="utf-8",
        )
        firmware_case = tools_root / "固件升级工具" / "testcases"
        firmware_case.mkdir(parents=True)
        (firmware_case / "test_firmware_cycle.py").write_text(
            textwrap.dedent(
                """
                class TestFirmwareCycle:
                    def __init__(self, **_kwargs):
                        pass

                    def run(self, **_kwargs):
                        return True, None
                """
            ),
            encoding="utf-8",
        )
        return project_root

    def test_three_tool_navigation_items_open_embedded_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._write_tool_fixtures(Path(temp_dir))
            window = MainWindow(project_root)

            window.nav_postprocess_compare.click()
            self.assertIsInstance(window.page_stack.currentWidget(), PostprocessComparePage)
            embedded_window = window.page_stack.currentWidget().window
            self.assertTrue(embedded_window.findChild(QtWidgets.QWidget, "sidebar").isHidden())
            self.assertEqual(
                embedded_window.findChild(QtWidgets.QLabel, "pageTitle").text(),
                "后处理对比",
            )

            window.nav_calibration_score.click()
            self.app.processEvents()
            page = window.page_stack.currentWidget()
            self.assertIsInstance(page, CalibrationScorePage)
            self.assertEqual(page.score_value.text(), "93.50")
            self.assertTrue(window.nav_calibration_score.isChecked())

            window.nav_firmware_upgrade.click()
            page = window.page_stack.currentWidget()
            self.assertIsInstance(page, FirmwareUpgradePage)
            self.assertEqual(page.mode_combo.currentData(), "upgrade")
            self.assertTrue(window.nav_firmware_upgrade.isChecked())
            window.close()

    def test_missing_tool_keeps_recoverable_error_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "pc自动化工具"
            project_root.mkdir()
            window = MainWindow(project_root)

            window.nav_calibration_score.click()

            self.assertIsInstance(window.page_stack.currentWidget(), ToolErrorPage)
            self.assertTrue(window.nav_calibration_score.isChecked())
            window.close()

    def test_main_run_locks_new_tool_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._write_tool_fixtures(Path(temp_dir))
            window = MainWindow(project_root)

            window._set_run_ui_state("running")
            self.assertFalse(window.nav_postprocess_compare.isEnabled())
            self.assertFalse(window.nav_calibration_score.isEnabled())
            self.assertFalse(window.nav_firmware_upgrade.isEnabled())

            window._set_run_ui_state("passed")
            self.assertTrue(window.nav_postprocess_compare.isEnabled())
            self.assertTrue(window.nav_calibration_score.isEnabled())
            self.assertTrue(window.nav_firmware_upgrade.isEnabled())
            window.close()

    def test_firmware_process_locks_navigation_and_f4_requests_safe_stop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._write_tool_fixtures(Path(temp_dir))
            window = MainWindow(project_root)
            window.nav_firmware_upgrade.click()
            page = window.page_stack.currentWidget()
            page._stop_file = Path(temp_dir) / "firmware.stop"

            page._process.start(sys.executable, ["-c", "import time; time.sleep(2)"])
            self.assertTrue(page._process.waitForStarted(1500))
            self.app.processEvents()
            self.assertEqual(window._tool_busy_key, "firmware_upgrade")
            self.assertFalse(window.nav_workspace.isEnabled())
            self.assertEqual(window.sidebar_status_copy.text(), "固件升级任务运行中")

            window._stop_run()
            self.assertTrue(page._stop_file.is_file())
            self.assertEqual(page.status_label.text(), "等待安全停止")

            page._process.kill()
            page._process.waitForFinished(1500)
            self.app.processEvents()
            self.assertIsNone(window._tool_busy_key)
            window.close()

    def test_firmware_runner_emits_machine_readable_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._write_tool_fixtures(Path(temp_dir))
            tool_root = project_root / "工具" / "固件升级工具"
            stop_file = Path(temp_dir) / "runner.stop"
            runner = Path(__file__).parents[1] / "jens_platform" / "firmware_tool_runner.py"

            result = subprocess.run(
                [
                    sys.executable,
                    str(runner),
                    "--tool-root",
                    str(tool_root),
                    "--mode",
                    "stream_only",
                    "--stop-file",
                    str(stop_file),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                timeout=10,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('[JENS_FIRMWARE_RESULT] {"success": true', result.stdout)

    def test_firmware_runner_reports_missing_entry_as_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = Path(__file__).parents[1] / "jens_platform" / "firmware_tool_runner.py"
            result = subprocess.run(
                [
                    sys.executable,
                    str(runner),
                    "--tool-root",
                    temp_dir,
                    "--mode",
                    "stream_only",
                    "--stop-file",
                    str(Path(temp_dir) / "runner.stop"),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                timeout=10,
            )

            self.assertEqual(result.returncode, 2)
            result_line = next(
                line for line in result.stdout.splitlines() if line.startswith("[JENS_FIRMWARE_RESULT] ")
            )
            payload = __import__("json").loads(result_line.split(" ", 1)[1])
            self.assertFalse(payload["stop_requested"])
            self.assertIn("未找到固件测试入口", payload["error"])

    def test_firmware_mode_validation_matrix_and_runner_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._write_tool_fixtures(Path(temp_dir))
            page = FirmwareUpgradePage(project_root)
            upgrade_path = Path(temp_dir) / "upgrade.zip"
            downgrade_path = Path(temp_dir) / "downgrade.zip"
            upgrade_path.write_bytes(b"upgrade")
            downgrade_path.write_bytes(b"downgrade")
            page._stop_file = Path(temp_dir) / "firmware.stop"

            matrix = (
                ("stream_only", "", "", ""),
                ("upgrade", str(upgrade_path), "", ""),
                ("downgrade", "", str(downgrade_path), ""),
                ("cycle", str(upgrade_path), str(downgrade_path), ""),
            )
            for mode, upgrade, downgrade, expected_error in matrix:
                with self.subTest(mode=mode):
                    page.mode_combo.setCurrentIndex(page.mode_combo.findData(mode))
                    page.upgrade_edit.setText(upgrade)
                    page.downgrade_edit.setText(downgrade)
                    self.assertEqual(page._validation_error(), expected_error)
                    args = page._build_runner_args()
                    self.assertEqual(args[args.index("--mode") + 1], mode)

            page.mode_combo.setCurrentIndex(page.mode_combo.findData("cycle"))
            page.upgrade_edit.setText(str(upgrade_path))
            page.downgrade_edit.setText(str(downgrade_path))
            page.cycle_count.setValue(7)
            page.cycle_direction.setCurrentIndex(page.cycle_direction.findData("downgrade_first"))
            page.connection_combo.setCurrentIndex(page.connection_combo.findData("wifi"))
            page.with_stream_check.setChecked(False)
            args = page._build_runner_args()
            self.assertEqual(args[args.index("--cycle-count") + 1], "7")
            self.assertEqual(args[args.index("--cycle-start") + 1], "downgrade_first")
            self.assertEqual(args[args.index("--connection-mode") + 1], "wifi")
            self.assertIn("--without-stream", args)
            page.deleteLater()

    def test_firmware_failed_result_keeps_report_and_notifies_dispatcher(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._write_tool_fixtures(Path(temp_dir))
            report_path = Path(temp_dir) / "report.html"
            report_path.write_text("report", encoding="utf-8")
            window = MainWindow(project_root)
            window.nav_firmware_upgrade.click()
            page = window.page_stack.currentWidget()
            send_email = mock.Mock()
            window._notification_dispatcher.send_tool_result_email = send_email

            page._result = {
                "success": False,
                "report_path": str(report_path),
                "stopped": False,
                "error": "升级失败",
            }
            page._process_finished(1, page._process.NormalExit)

            self.assertEqual(page.status_label.text(), "测试失败")
            self.assertTrue(page.open_report_button.isEnabled())
            send_email.assert_called_once_with("固件升级测试", "failed", str(report_path))
            window.close()

    def test_firmware_email_status_maps_passed_and_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._write_tool_fixtures(Path(temp_dir))
            window = MainWindow(project_root)
            send_email = mock.Mock()
            window._notification_dispatcher.send_tool_result_email = send_email

            window._on_firmware_run_finished(True, "passed.html", False)
            window._on_firmware_run_finished(False, "stopped.html", True)

            self.assertEqual(
                send_email.call_args_list,
                [
                    mock.call("固件升级测试", "passed", "passed.html"),
                    mock.call("固件升级测试", "stopped", "stopped.html"),
                ],
            )
            window.close()

    def test_firmware_prepare_close_blocks_exit_while_process_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._write_tool_fixtures(Path(temp_dir))
            page = FirmwareUpgradePage(project_root)
            page._process.start(sys.executable, ["-c", "import time; time.sleep(2)"])
            self.assertTrue(page._process.waitForStarted(1500))

            with mock.patch.object(QtWidgets.QMessageBox, "warning") as warning:
                self.assertFalse(page.prepare_close())
            warning.assert_called_once()

            page._process.kill()
            page._process.waitForFinished(1500)
            self.assertTrue(page.prepare_close())
            page.deleteLater()

    def test_postprocess_state_locks_navigation_and_f4_stops_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._write_tool_fixtures(Path(temp_dir))
            window = MainWindow(project_root)
            window.nav_postprocess_compare.click()
            page = window.page_stack.currentWidget()

            page.window._process.stateChanged.emit(page.window._process.Starting)
            self.assertEqual(window._tool_busy_key, "postprocess_compare")
            self.assertFalse(window.nav_workspace.isEnabled())
            self.assertTrue(window.act_stop.isEnabled())
            self.assertEqual(window.sidebar_status_copy.text(), "后处理对比任务运行中")

            with mock.patch.object(page, "stop_run") as stop_run:
                window._stop_run()
            stop_run.assert_called_once_with()

            page.window._process.stateChanged.emit(page.window._process.NotRunning)
            self.assertIsNone(window._tool_busy_key)
            self.assertTrue(window.nav_workspace.isEnabled())
            self.assertFalse(window.act_stop.isEnabled())
            window.close()


if __name__ == "__main__":
    unittest.main()
