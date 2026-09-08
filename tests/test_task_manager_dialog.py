from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets  # type: ignore

from jens_platform.dialogs import TaskManagerDialog


class TaskManagerDialogTests(unittest.TestCase):
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

    def test_groups_tasks_by_module_and_hides_queue_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            tasks_dir = project_root / "tasks"
            tasks_dir.mkdir()
            p1_path = self._write_task(
                tasks_dir,
                "任意名字.json",
                ["crealityscan.configure_scan_params_p1"],
            )
            pika_path = self._write_task(tasks_dir, "pika后处理usb.json", [])
            otter_lite_basic_path = self._write_task(
                tasks_dir,
                "任意Basic名字.json",
                ["crealityscan.configure_scan_params_otter_lite_basic"],
            )
            raptor_x_path = self._write_task(
                tasks_dir,
                "任意RaptorX名字.json",
                ["crealityscan.configure_scan_params_raptor_x"],
            )
            raptor_pro_path = self._write_task(
                tasks_dir,
                "任意RaptorPro名字.json",
                ["crealityscan.configure_scan_params_raptor_pro"],
            )
            demo_path = self._write_task(tasks_dir, "演示任务.json", [])
            numbered_path = self._write_task(
                tasks_dir,
                "1.json",
                ["crealityscan.configure_scan_params_p1"],
            )
            self._write_task(tasks_dir, "_queue.json", [])

            dialog = TaskManagerDialog(project_root)
            categories = [
                dialog.list.topLevelItem(index).text(0)
                for index in range(dialog.list.topLevelItemCount())
            ]

            self.assertEqual(
                categories,
                [
                    "P1（1）",
                    "Raptor X（1）",
                    "Raptor Pro（1）",
                    "Pika（1）",
                    "Otter Lite Basic（1）",
                    "测试任务（2）",
                ],
            )
            visible_paths = {
                Path(group.child(index).data(0, QtCore.Qt.UserRole))
                for group_index in range(dialog.list.topLevelItemCount())
                for group in [dialog.list.topLevelItem(group_index)]
                for index in range(group.childCount())
            }
            self.assertEqual(
                visible_paths,
                {
                    p1_path,
                    pika_path,
                    otter_lite_basic_path,
                    raptor_x_path,
                    raptor_pro_path,
                    demo_path,
                    numbered_path,
                },
            )

            dialog.edit_filter.setText("后处理")
            self.app.processEvents()
            self.assertEqual(dialog.list.topLevelItemCount(), 1)
            pika_group = dialog.list.topLevelItem(0)
            self.assertEqual(pika_group.text(0), "Pika（1）")
            dialog.list.clearSelection()
            pika_group.child(0).setSelected(True)
            self.assertEqual(dialog._selected_paths(), [pika_path])

            dialog.edit_filter.setText("测试任务")
            self.app.processEvents()
            self.assertEqual(dialog.list.topLevelItemCount(), 1)
            self.assertEqual(dialog.list.topLevelItem(0).text(0), "测试任务（2）")
            dialog.close()


if __name__ == "__main__":
    unittest.main()
