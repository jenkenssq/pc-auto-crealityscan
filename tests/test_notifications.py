from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets  # type: ignore

from jens_platform.dialogs import EmailSettingsDialog
from jens_platform.notifications import (
    NotificationDispatcher,
    NotificationSettings,
    TaskRunSummary,
    load_notification_settings,
    save_notification_settings,
)


class NotificationSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_label_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            save_notification_settings(
                project_root,
                NotificationSettings(recipient_email="a@b.com", label="深圳压测电脑1"),
            )
            loaded = load_notification_settings(project_root)
            self.assertEqual(loaded.recipient_email, "a@b.com")
            self.assertEqual(loaded.label, "深圳压测电脑1")

    def test_load_legacy_settings_without_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            fp = project_root / "config" / "notification_settings.json"
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(json.dumps({"recipient_email": "a@b.com"}), encoding="utf-8")
            loaded = load_notification_settings(project_root)
            self.assertEqual(loaded.label, "")

    def test_failure_subject_with_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            dispatcher = NotificationDispatcher(project_root)
            dispatcher.set_label("深圳压测电脑1")
            summary = TaskRunSummary(task_json_name="P1开流.json", status="failed")
            with mock.patch.object(dispatcher, "_send_async") as m:
                dispatcher.send_failure_email(summary)
            self.assertEqual(m.call_count, 1)
            self.assertEqual(m.call_args[0][0], "深圳压测电脑1-pc端软件ui自动化测试失败")

    def test_failure_subject_without_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            dispatcher = NotificationDispatcher(project_root)
            summary = TaskRunSummary(task_json_name="P1开流.json", status="failed")
            with mock.patch.object(dispatcher, "_send_async") as m:
                dispatcher.send_failure_email(summary)
            self.assertEqual(m.call_args[0][0], "自动化测试失败通知 - P1开流.json")

    def test_success_subject_with_label_and_report_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            report_path = project_root / "report.html"
            report_path.write_text("<html></html>", encoding="utf-8")
            dispatcher = NotificationDispatcher(project_root)
            dispatcher.set_label("深圳压测电脑1")
            summary = TaskRunSummary(
                task_json_name="P1开流.json",
                status="passed",
                report_path=str(report_path),
            )
            with mock.patch.object(dispatcher, "_send_async") as send_async:
                dispatcher.send_success_email(summary)

            self.assertEqual(send_async.call_args[0][0], "深圳压测电脑1-pc端软件ui自动化测试成功")
            self.assertEqual(send_async.call_args[0][2], [(report_path, "P1开流.html")])
            self.assertIn("任务状态: 通过", send_async.call_args[0][1])

    def test_success_subject_without_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dispatcher = NotificationDispatcher(Path(temp_dir))
            summary = TaskRunSummary(task_json_name="P1开流.json", status="passed")
            with mock.patch.object(dispatcher, "_send_async") as send_async:
                dispatcher.send_success_email(summary)
            self.assertEqual(send_async.call_args[0][0], "自动化测试成功通知 - P1开流.json")

    def test_email_settings_dialog_has_label_field(self) -> None:
        dlg = EmailSettingsDialog(
            "a@b.com",
            lambda: (True, ""),
            current_label="深圳压测电脑1",
        )
        self.assertEqual(dlg.edit_label.text(), "深圳压测电脑1")
        dlg.edit_label.setText("新标识")
        self.assertEqual(dlg.label(), "新标识")
        dlg.close()


if __name__ == "__main__":
    unittest.main()
