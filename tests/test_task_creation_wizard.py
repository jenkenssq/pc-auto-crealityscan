from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets  # type: ignore

from jens_platform.dialogs import TaskCreationWizardDialog
from jens_platform.task_generator import TASK_KIND_FPS_STAT, fps_stat_mode_plan


class TaskCreationWizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @staticmethod
    def _write_p1_presets(project_root: Path) -> Path:
        path = (
            project_root
            / "steps"
            / "crealityscan"
            / "configure_scan_params_p1"
            / "v1_0_0"
            / "presets.json"
        )
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "presets": [
                        {"key": "p1.common", "name": "公共模式", "actions": []},
                        {
                            "key": "p1.usb.only",
                            "name": "USB 专属",
                            "connections": ["usb"],
                            "actions": [],
                        },
                        {
                            "key": "p1.wifi.only",
                            "name": "Wi-Fi 专属",
                            "connections": ["wifi"],
                            "actions": [],
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_wizard_reads_presets_selects_multiple_and_returns_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_p1_presets(project_root)
            dialog = TaskCreationWizardDialog(project_root)

            p1_items = [
                dialog.module_list.item(index)
                for index in range(dialog.module_list.count())
                if dialog.module_list.item(index).data(QtCore.Qt.UserRole) == "P1"
            ]
            self.assertEqual(len(p1_items), 1)
            dialog.module_list.setCurrentItem(p1_items[0])
            self.assertFalse(dialog.connection_widget.isHidden())
            dialog.btn_wifi.click()
            self.assertEqual(dialog._connection_type(), "Wi-Fi")
            dialog._go_next()
            self.assertEqual(dialog.preset_list.count(), 2)
            visible_keys = {
                dialog.preset_list.item(index).data(QtCore.Qt.UserRole)
                for index in range(dialog.preset_list.count())
            }
            self.assertEqual(visible_keys, {"p1.common", "p1.wifi.only"})

            dialog.btn_select_visible.click()
            self.assertEqual(len(dialog._selected_order), 2)
            dialog._go_next()
            dialog.spin_target_frames.setValue(350)
            dialog.chk_random_order.setChecked(True)
            values = dialog.values()

            self.assertEqual(values["module_name"], "P1")
            self.assertEqual(values["target_frames"], 350)
            self.assertEqual(values["connection_type"], "Wi-Fi")
            self.assertEqual(set(values["preset_keys"]), {"p1.common", "p1.wifi.only"})
            self.assertTrue(values["randomized"])
            dialog.close()

    def test_switching_connection_prunes_only_incompatible_selected_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_p1_presets(project_root)
            dialog = TaskCreationWizardDialog(project_root)

            for index in range(dialog.module_list.count()):
                item = dialog.module_list.item(index)
                if item.data(QtCore.Qt.UserRole) == "P1":
                    dialog.module_list.setCurrentItem(item)
                    break

            dialog._go_next()
            dialog.btn_select_visible.click()
            self.assertEqual(set(dialog._selected_order), {"p1.common", "p1.usb.only"})

            dialog._go_back()
            dialog.btn_wifi.click()
            self.assertEqual(dialog._selected_order, ["p1.common"])
            dialog._go_next()
            visible_keys = {
                dialog.preset_list.item(index).data(QtCore.Qt.UserRole)
                for index in range(dialog.preset_list.count())
            }
            self.assertEqual(visible_keys, {"p1.common", "p1.wifi.only"})
            dialog.close()

    def test_connection_selector_is_hidden_for_modules_without_connection_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            path = (
                project_root
                / "steps"
                / "crealityscan"
                / "configure_scan_params_otter"
                / "v1_0_0"
                / "presets.json"
            )
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {"presets": [{"key": "otter.common", "name": "公共模式", "actions": []}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            dialog = TaskCreationWizardDialog(project_root)

            for index in range(dialog.module_list.count()):
                item = dialog.module_list.item(index)
                if item.data(QtCore.Qt.UserRole) == "otter":
                    dialog.module_list.setCurrentItem(item)
                    break

            self.assertTrue(dialog.connection_widget.isHidden())
            self.assertEqual(dialog.values()["connection_type"], "")
            dialog.close()

    def test_otter_lite_and_basic_are_separate_module_choices(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        dialog = TaskCreationWizardDialog(project_root)
        module_items = {
            str(dialog.module_list.item(index).data(QtCore.Qt.UserRole) or ""): dialog.module_list.item(index)
            for index in range(dialog.module_list.count())
        }

        self.assertIn("otter lite", module_items)
        self.assertIn("otter lite basic", module_items)
        dialog.module_list.setCurrentItem(module_items["otter lite basic"])
        self.assertEqual(dialog._module_name, "otter lite basic")
        self.assertEqual(len(dialog._presets), 20)
        self.assertIn("Otter Lite Basic", dialog.module_aside_value.text())
        dialog.close()

    def test_raptor_variants_are_separate_module_choices(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        dialog = TaskCreationWizardDialog(project_root)
        module_items = {
            str(dialog.module_list.item(index).data(QtCore.Qt.UserRole) or ""): dialog.module_list.item(index)
            for index in range(dialog.module_list.count())
        }

        self.assertIn("raptor", module_items)
        for module_name, display_name, expected_count, supports_single_line in (
            ("raptor x", "Raptor X", 22, True),
            ("raptor pro", "Raptor Pro", 21, False),
        ):
            with self.subTest(module_name=module_name):
                self.assertIn(module_name, module_items)
                dialog.module_list.setCurrentItem(module_items[module_name])
                self.assertEqual(dialog._module_name, module_name)
                self.assertEqual(len(dialog._presets), expected_count)
                preset_keys = {preset.key for preset in dialog._presets}
                single_line_key = f"{module_name.replace(' ', '_')}.line_laser.point_cloud.single"
                self.assertEqual(single_line_key in preset_keys, supports_single_line)
                self.assertIn(display_name, dialog.module_aside_value.text())
                dialog.btn_wifi.click()
                dialog._go_next()
                visible_keys = {
                    dialog.preset_list.item(index).data(QtCore.Qt.UserRole)
                    for index in range(dialog.preset_list.count())
                }
                self.assertNotIn(f"{module_name.replace(' ', '_')}.line_laser.no_marker", visible_keys)
                dialog._go_back()
                dialog.btn_usb.click()
        dialog.close()

    def test_refresh_preset_button_loads_new_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            path = self._write_p1_presets(project_root)
            dialog = TaskCreationWizardDialog(project_root)
            for index in range(dialog.module_list.count()):
                item = dialog.module_list.item(index)
                if item.data(QtCore.Qt.UserRole) == "P1":
                    dialog.module_list.setCurrentItem(item)
                    break
            dialog._go_next()
            self.assertEqual(dialog.preset_list.count(), 2)

            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["presets"].append({"key": "p1.new", "name": "新模式", "actions": []})
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            dialog.btn_refresh_presets.click()

            self.assertEqual(dialog.preset_list.count(), 3)
            self.assertTrue(any("新模式" in dialog.preset_list.item(i).text() for i in range(3)))
            dialog.close()

    def test_free_edit_button_requests_free_orchestration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_p1_presets(project_root)
            dialog = TaskCreationWizardDialog(project_root)
            for index in range(dialog.module_list.count()):
                item = dialog.module_list.item(index)
                if item.data(QtCore.Qt.UserRole) == "P1":
                    dialog.module_list.setCurrentItem(item)
                    break
            dialog.btn_free_edit.click()
            self.assertTrue(dialog.free_edit_requested)
            self.assertEqual(dialog.free_edit_default_name, "手动编排-P1")
            self.assertEqual(dialog.result(), QtWidgets.QDialog.Accepted)
            dialog.close()

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            dialog = TaskCreationWizardDialog(project_root)
            dialog.btn_free_edit.click()
            self.assertTrue(dialog.free_edit_requested)
            self.assertEqual(dialog.free_edit_default_name, "手动编排任务")
            dialog.close()

    def test_slide_rail_checkbox_flows_into_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_p1_presets(project_root)
            dialog = TaskCreationWizardDialog(project_root)
            for index in range(dialog.module_list.count()):
                item = dialog.module_list.item(index)
                if item.data(QtCore.Qt.UserRole) == "P1":
                    dialog.module_list.setCurrentItem(item)
                    break

            self.assertFalse(dialog.values()["slide_rail"])
            dialog.chk_slide_rail.setChecked(True)
            self.assertTrue(dialog.values()["slide_rail"])
            dialog.close()

    def test_fps_stat_checkbox_auto_selects_modes_kind_and_1000_frames(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        dialog = TaskCreationWizardDialog(project_root)
        module_items = {
            str(dialog.module_list.item(index).data(QtCore.Qt.UserRole) or ""): dialog.module_list.item(index)
            for index in range(dialog.module_list.count())
        }
        dialog.module_list.setCurrentItem(module_items["raptor pro"])
        dialog.btn_wifi.click()
        dialog._go_next()

        self.assertFalse(dialog.chk_fps_stat.isChecked())
        self.assertFalse(dialog._is_fps_stat())

        # 第二步勾选「帧率统计任务」：自动按业务顺序勾选模式，并同步第三步任务类型。
        dialog.chk_fps_stat.setChecked(True)
        self.assertTrue(dialog._is_fps_stat())
        self.assertTrue(dialog.radio_fps.isChecked())
        expected = [
            key for _, key in fps_stat_mode_plan("raptor pro", "Wi-Fi", project_root=project_root)
        ]
        self.assertEqual(dialog._selected_order, expected)
        self.assertNotIn("no_marker", dialog._selected_order)

        # 进入第三步：自动选中「帧率统计」，帧数固定 1000，禁止随机。
        dialog._go_next()
        self.assertTrue(dialog.radio_fps.isChecked())
        self.assertEqual(dialog.spin_target_frames.value(), 1000)
        self.assertTrue(dialog.random_widget.isHidden())
        values = dialog.values()
        self.assertEqual(values["task_kind"], TASK_KIND_FPS_STAT)
        self.assertEqual(values["target_frames"], 1000)
        self.assertEqual(values["preset_keys"], expected)
        self.assertFalse(values["randomized"])

        # 取消勾选后回到开流，恢复随机控件。
        dialog.chk_fps_stat.setChecked(False)
        self.assertFalse(dialog._is_fps_stat())
        self.assertTrue(dialog.radio_open.isChecked())
        self.assertFalse(dialog.random_widget.isHidden())
        self.assertEqual(dialog.values()["task_kind"], "开流")
        dialog.close()


if __name__ == "__main__":
    unittest.main()
