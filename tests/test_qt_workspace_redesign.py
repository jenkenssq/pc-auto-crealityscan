from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets  # type: ignore

from jens_platform.dialogs import TaskEditDialog, TaskManagerDialog
from jens_platform.main import MainWindow
from jens_platform.step_registry import StepMeta


class QtWorkspaceRedesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @staticmethod
    def _write_task(project_root: Path) -> Path:
        tasks_dir = project_root / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        path = tasks_dir / "测试任务.json"
        path.write_text(
            json.dumps(
                {
                    "case_id": "test",
                    "name": "测试任务",
                    "steps": [
                        {
                            "id": "common.demo",
                            "version": "1.0.0",
                            "name": "演示步骤",
                            "params": {},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_run_state_locks_and_restores_context_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_task(project_root)
            window = MainWindow(project_root)

            window._running_task = project_root / "tasks" / "测试任务.json"
            window._task_queue_total = 2
            window._task_queue_index = 1
            window._set_run_ui_state("running")
            self.assertFalse(window.list_tasks.isEnabled())
            self.assertFalse(window.btn_create_task.isEnabled())
            self.assertFalse(window.nav_task_library.isEnabled())
            self.assertFalse(window.nav_slide_rail.isEnabled())
            self.assertTrue(window.btn_stop_top.isEnabled())
            self.assertEqual(window.lbl_run_state.text(), "正在运行")

            window._set_run_ui_state("passed")
            self.assertTrue(window.list_tasks.isEnabled())
            self.assertTrue(window.btn_create_task.isEnabled())
            self.assertFalse(window.btn_stop_top.isEnabled())
            window.close()

    def test_batch_queue_forces_full_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            first = self._write_task(project_root)
            second = project_root / "tasks" / "第二个任务.json"
            second.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
            window = MainWindow(project_root)
            window._enqueue_tasks_to_queue([first, second])
            window._refresh_run_start_step_selector()

            self.assertFalse(window.combo_run_start_step.isEnabled())
            self.assertEqual(window.combo_run_start_step.currentData(), 1)
            self.assertIn("批量队列", window.combo_run_start_step.currentText())
            window.close()

    def test_task_manager_actions_follow_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_task(project_root)
            dialog = TaskManagerDialog(project_root)
            dialog.list.clearSelection()
            dialog._refresh_action_state()
            self.assertFalse(dialog.btn_enqueue.isEnabled())
            self.assertFalse(dialog.btn_load.isEnabled())

            task_item = dialog.list.topLevelItem(0).child(0)
            task_item.setSelected(True)
            dialog._refresh_action_state()
            self.assertTrue(dialog.btn_enqueue.isEnabled())
            self.assertTrue(dialog.btn_load.isEnabled())
            dialog.close()

    def test_invalid_step_json_blocks_save(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            task_path = self._write_task(project_root)
            step_meta = StepMeta(
                step_id="common.demo",
                version="1.0.0",
                name="演示步骤",
                source_path=str(project_root / "steps" / "step.json"),
            )
            dialog = TaskEditDialog(project_root, task_path, [step_meta])
            dialog.list_selected.setCurrentRow(0)
            self.app.processEvents()
            dialog.edit_params.setPlainText("{")
            self.app.processEvents()

            self.assertFalse(dialog.btn_ok.isEnabled())
            self.assertTrue(dialog.lab_params_error.isVisible() or not dialog.isVisible())
            self.assertEqual(dialog.edit_params.property("error"), True)
            dialog.close()

    def test_rebuilt_step_list_does_not_keep_deleted_item_during_save(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            task_path = self._write_task(project_root)
            step_meta = StepMeta(
                step_id="common.demo",
                version="1.0.0",
                name="Demo step",
                source_path=str(project_root / "steps" / "step.json"),
            )
            dialog = TaskEditDialog(project_root, task_path, [step_meta])
            dialog.list_selected.setCurrentRow(0)
            self.app.processEvents()

            dialog._refresh_selected_steps()
            self.app.processEvents()
            self.assertIsNone(dialog._current_step_item)

            dialog._save_and_accept()

            self.assertEqual(dialog.result(), QtWidgets.QDialog.Accepted)
            self.assertTrue(task_path.exists())


if __name__ == "__main__":
    unittest.main()
