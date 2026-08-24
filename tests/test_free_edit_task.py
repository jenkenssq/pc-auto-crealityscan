
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets  # type: ignore

from jens_platform.main import MainWindow


class FreeEditTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _wizard_mock(self, free_edit_requested: bool):
        dialog = mock.Mock()
        dialog.exec_.return_value = QtWidgets.QDialog.Accepted
        dialog.free_edit_requested = free_edit_requested
        dialog.free_edit_default_name = "手动编排-P1"
        return dialog

    def test_free_edit_skips_preset_generation_and_opens_empty_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            window = MainWindow(project_root)
            try:
                with mock.patch(
                    "jens_platform.main.TaskCreationWizardDialog",
                    return_value=self._wizard_mock(True),
                ), mock.patch.object(window, "_edit_task_path") as edit_path, mock.patch(
                    "jens_platform.main.QtWidgets.QInputDialog.getText",
                    return_value=("我的手动任务", True),
                ):
                    window._create_task()

                edit_path.assert_called_once()
                kwargs = edit_path.call_args.kwargs
                model = kwargs.get("initial_model")
                self.assertIsNotNone(model)
                self.assertEqual(model.name, "我的手动任务")
                self.assertEqual(model.case_id, "我的手动任务")
                self.assertEqual(model.steps, [])
            finally:
                window.close()

    def test_free_edit_cancel_does_not_open_editor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            window = MainWindow(project_root)
            try:
                with mock.patch(
                    "jens_platform.main.TaskCreationWizardDialog",
                    return_value=self._wizard_mock(True),
                ), mock.patch.object(window, "_edit_task_path") as edit_path, mock.patch(
                    "jens_platform.main.QtWidgets.QInputDialog.getText",
                    return_value=("", False),
                ):
                    window._create_task()

                edit_path.assert_not_called()
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
