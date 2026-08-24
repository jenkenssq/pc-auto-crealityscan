from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets  # type: ignore

from jens_platform.main import MainWindow


class TaskLibraryPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @staticmethod
    def _write_task(tasks_dir: Path, name: str, step_ids: list[str]) -> Path:
        path = tasks_dir / name
        payload = {
            "case_id": path.stem,
            "name": path.stem,
            "steps": [
                {
                    "id": step_id,
                    "version": "1.0.0",
                    "name": step_id,
                    "params": {},
                }
                for step_id in step_ids
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    @staticmethod
    def _page(window: MainWindow):
        return window._pages["task_library"]

    def test_show_page_creates_task_library_page_and_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            tasks_dir = project_root / "tasks"
            tasks_dir.mkdir()
            p1 = self._write_task(tasks_dir, "任意名字.json", ["crealityscan.configure_scan_params_p1"])
            pika = self._write_task(tasks_dir, "pika后处理usb.json", [])
            self._write_task(tasks_dir, "_queue.json", [])

            window = MainWindow(project_root)
            try:
                self.assertTrue(window._show_page("task_library"))
                self.assertIn("task_library", window._pages)
                self.assertTrue(window.nav_task_library.isChecked())
                page = self._page(window)

                groups = [page.tree.topLevelItem(i).text(0) for i in range(page.tree.topLevelItemCount())]
                self.assertEqual(groups, ["P1（1）", "Pika（1）"])
                visible = {
                    Path(g.child(i).data(0, QtCore.Qt.UserRole))
                    for gi in range(page.tree.topLevelItemCount())
                    for g in [page.tree.topLevelItem(gi)]
                    for i in range(g.childCount())
                }
                self.assertEqual(visible, {p1, pika})
            finally:
                window.close()

    def test_filter_limits_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            tasks_dir = project_root / "tasks"
            tasks_dir.mkdir()
            self._write_task(tasks_dir, "p1开流wifi.json", ["crealityscan.configure_scan_params_p1"])
            self._write_task(tasks_dir, "otter后处理.json", [])

            window = MainWindow(project_root)
            try:
                window._show_page("task_library")
                page = self._page(window)
                page.edit_filter.setText("后处理")
                self.assertEqual(page.tree.topLevelItemCount(), 1)
                self.assertEqual(page.tree.topLevelItem(0).text(0), "Otter（1）")
            finally:
                window.close()

    def test_enqueue_emits_and_joins_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            tasks_dir = project_root / "tasks"
            tasks_dir.mkdir()
            task = self._write_task(tasks_dir, "p1开流usb.json", ["crealityscan.configure_scan_params_p1"])

            window = MainWindow(project_root)
            try:
                window._show_page("task_library")
                page = self._page(window)
                page.tree.topLevelItem(0).child(0).setSelected(True)
                page.btn_enqueue.click()
                self.assertEqual(window.list_tasks.count(), 1)
                item_path = Path(window.list_tasks.item(0).data(QtCore.Qt.UserRole))
                self.assertEqual(item_path, task)
            finally:
                window.close()

    def test_delete_removes_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            tasks_dir = project_root / "tasks"
            tasks_dir.mkdir()
            task = self._write_task(tasks_dir, "p1开流usb.json", ["crealityscan.configure_scan_params_p1"])

            window = MainWindow(project_root)
            try:
                window._show_page("task_library")
                page = self._page(window)
                page.tree.topLevelItem(0).child(0).setSelected(True)
                with mock.patch.object(
                    QtWidgets.QMessageBox,
                    "exec_",
                    return_value=QtWidgets.QMessageBox.Ok,
                ):
                    page.btn_delete.click()
                self.assertFalse(task.exists())
                self.assertEqual(page.tree.topLevelItemCount(), 0)
            finally:
                window.close()

    def test_load_requires_single_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            tasks_dir = project_root / "tasks"
            tasks_dir.mkdir()
            self._write_task(tasks_dir, "p1开流usb.json", ["crealityscan.configure_scan_params_p1"])
            self._write_task(tasks_dir, "p1开流wifi.json", ["crealityscan.configure_scan_params_p1"])

            window = MainWindow(project_root)
            try:
                window._show_page("task_library")
                page = self._page(window)
                page.tree.clearSelection()
                self.assertFalse(page.btn_load.isEnabled())
                group = page.tree.topLevelItem(0)
                group.child(0).setSelected(True)
                group.child(1).setSelected(True)
                self.assertEqual(len(page._selected_paths()), 2)
                self.assertFalse(page.btn_load.isEnabled())
                page.tree.clearSelection()
                group.child(0).setSelected(True)
                self.assertEqual(len(page._selected_paths()), 1)
                self.assertTrue(page.btn_load.isEnabled())
            finally:
                window.close()

    def test_tool_busy_locks_task_library_nav(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            tasks_dir = project_root / "tasks"
            tasks_dir.mkdir()
            self._write_task(tasks_dir, "p1开流usb.json", ["crealityscan.configure_scan_params_p1"])

            window = MainWindow(project_root)
            try:
                window._show_page("task_library")
                window._set_tool_busy("firmware_upgrade", True)
                self.assertFalse(window.nav_task_library.isEnabled())
                window._set_tool_busy("firmware_upgrade", False)
                self.assertTrue(window.nav_task_library.isEnabled())
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
