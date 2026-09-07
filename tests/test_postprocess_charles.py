from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets  # type: ignore

from jens_platform.tools.postprocess_compare import cli, excel_report
from jens_platform.tools.postprocess_compare.qt_app import CompareWindow
from jens_platform.tools.postprocess_compare import qt_app as qt_app_module


class PostprocessCharlesCliTests(unittest.TestCase):
    def test_parser_accepts_charles_exe(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["--charles-exe", r"C:\Program Files\Charles\Charles.exe"])
        self.assertEqual(args.charles_exe, r"C:\Program Files\Charles\Charles.exe")

    def test_parser_gaussian_quality_default_and_choices(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args([])
        self.assertEqual(args.gaussian_quality, "高质量")
        args = parser.parse_args(["--gaussian-quality", "标准"])
        self.assertEqual(args.gaussian_quality, "标准")
        with self.assertRaises(SystemExit):
            parser.parse_args(["--gaussian-quality", "超高"])

    def test_run_postprocess_step_passes_gaussian_quality_to_params(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir, \
                mock.patch.object(cli.importlib, "import_module") as import_module:
            step_module = mock.Mock()
            step_module.run.return_value = {"operation_elapsed_sec": 1.0, "snapshot": "x.png"}
            import_module.return_value = step_module
            cli._run_postprocess_step(
                "发布版",
                Path(temp_dir),
                900.0,
                "gaussian",
                0,
                gaussian_quality="标准",
            )
            ctx, params = step_module.run.call_args.args
            self.assertEqual(params["gaussian_quality"], "标准")
            self.assertNotIn("gaussian_quality", ctx)

    def test_run_postprocess_step_passes_skip_trip_model_to_params(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir, \
                mock.patch.object(cli.importlib, "import_module") as import_module:
            step_module = mock.Mock()
            step_module.run.return_value = {"operation_elapsed_sec": 1.0, "snapshot": "x.png"}
            import_module.return_value = step_module
            cli._run_postprocess_step(
                "人体补全",
                Path(temp_dir),
                900.0,
                "human_body_completion",
                0,
                enable_hd_geometry=True,
                base_wait_sec=5.0,
                skip_trip_model=True,
            )
            ctx, params = step_module.run.call_args.args
            self.assertTrue(params["skip_trip_model"])
            self.assertTrue(params["enable_hd_geometry"])
            self.assertEqual(params["base_wait_sec"], 5.0)
            self.assertNotIn("skip_trip_model", ctx)

    def test_launch_charles_starts_detached_and_logs_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exe = Path(temp_dir) / "Charles.exe"
            exe.write_bytes(b"exe")
            with mock.patch.object(cli.subprocess, "Popen") as popen:
                proc = mock.Mock()
                proc.pid = 4242
                popen.return_value = proc
                cli._launch_charles(exe)

                popen.assert_called_once()
                self.assertEqual(popen.call_args.args[0], [str(exe)])
                self.assertEqual(popen.call_args.kwargs["cwd"], str(exe.parent))
                self.assertEqual(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
                self.assertEqual(popen.call_args.kwargs["stdout"], subprocess.DEVNULL)
                self.assertEqual(popen.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_launch_charles_failure_raises_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exe = Path(temp_dir) / "Charles.exe"
            exe.write_bytes(b"exe")
            with mock.patch.object(
                cli.subprocess, "Popen", side_effect=OSError("无法启动")
            ):
                with self.assertRaises(RuntimeError):
                    cli._launch_charles(exe)

    def test_launch_charles_missing_exe_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            cli._launch_charles(Path(r"C:\dummy\Charles.exe"))

    def _run_main(
        self,
        charles_path: str | None,
        release_ok: bool = True,
        charles_raise: bool = False,
        delete_package: bool = False,
    ) -> tuple:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            project_set = base / "projects"
            project_set.mkdir()
            project_file = project_set / "proj" / "project.obp"
            project_file.parent.mkdir()
            project_file.write_bytes(b"project")
            output_dir = base / "out"
            output_dir.mkdir()

            argv = ["--operation", "texture"]
            if charles_path is not None:
                argv += ["--charles-exe", charles_path]
            if delete_package:
                argv += ["--delete-download-package"]

            with mock.patch.object(cli, "_prompt_exe") as prompt_exe, \
                    mock.patch.object(cli, "_prompt_version") as prompt_version, \
                    mock.patch.object(cli, "_prompt_project_set") as prompt_project_set, \
                    mock.patch.object(cli, "_prompt_output_dir") as prompt_output_dir, \
                    mock.patch.object(cli, "_resolve_project_files") as resolve_files, \
                    mock.patch.object(cli, "_directory_stats") as directory_stats, \
                    mock.patch.object(cli, "_prepare_working_copy") as prepare_copy, \
                    mock.patch.object(cli, "_install_run_log") as install_log, \
                    mock.patch.object(cli, "_run_one") as run_one, \
                    mock.patch.object(cli, "_delete_download_packages") as delete_packages, \
                    mock.patch.object(cli, "_launch_charles") as launch_charles, \
                    mock.patch.object(
                        excel_report, "generate_excel_report"
                    ) as report:
                release_exe = base / "release.exe"
                test_exe = base / "test.exe"
                prompt_exe.side_effect = [release_exe, test_exe]
                prompt_version.return_value = "1.0"
                prompt_project_set.return_value = project_set
                resolve_files.return_value = [project_file]
                prompt_output_dir.return_value = output_dir
                directory_stats.return_value = (0, 0)
                prepare_copy.return_value = None
                install_log.return_value = None
                run_one.return_value = release_ok
                delete_packages.return_value = None
                if charles_raise:
                    launch_charles.side_effect = RuntimeError("Charles 启动失败")
                else:
                    launch_charles.return_value = None
                report.return_value = output_dir / "对比表.xlsx"

                code = cli.main(argv)
                calls = [call.args[0] for call in run_one.call_args_list]
                return code, calls, launch_charles, delete_packages, run_one

    def test_main_launches_charles_between_release_and_test(self) -> None:
        code, calls, launch_charles, delete_packages, _ = self._run_main(r"C:\dummy\Charles.exe")
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["发布版", "测试版"])
        launch_charles.assert_called_once()
        # 未勾选删除开关：不应删除下载包
        delete_packages.assert_not_called()
        launched = launch_charles.call_args[0][0]
        self.assertEqual(str(launched), str(Path(r"C:\dummy\Charles.exe").expanduser().resolve()))

    def test_main_without_charles_exe_does_not_launch(self) -> None:
        code, calls, launch_charles, delete_packages, _ = self._run_main(None)
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["发布版", "测试版"])
        launch_charles.assert_not_called()
        # 未勾选删除开关：不应删除下载包
        delete_packages.assert_not_called()

    def test_main_charles_launch_failure_aborts_before_test(self) -> None:
        code, calls, launch_charles, delete_packages, _ = self._run_main(
            r"C:\dummy\Charles.exe", release_ok=True, charles_raise=True
        )
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["发布版"])
        self.assertEqual(launch_charles.call_count, 1)
        # 未勾选删除开关：即使 Charles 启动失败，也不删除下载包
        delete_packages.assert_not_called()

    def test_main_delete_download_package_when_flag_set(self) -> None:
        code, calls, launch_charles, delete_packages, _ = self._run_main(
            None, delete_package=True
        )
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["发布版", "测试版"])
        launch_charles.assert_not_called()
        delete_packages.assert_called_once()

    def test_main_delete_download_package_independent_of_charles(self) -> None:
        code, calls, launch_charles, delete_packages, _ = self._run_main(
            r"C:\dummy\Charles.exe", delete_package=True
        )
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["发布版", "测试版"])
        launch_charles.assert_called_once()
        delete_packages.assert_called_once()

    def test_main_does_not_delete_when_release_fails(self) -> None:
        code, calls, launch_charles, delete_packages, _ = self._run_main(
            None, release_ok=False, delete_package=True
        )
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["发布版"])
        launch_charles.assert_not_called()
        delete_packages.assert_not_called()


class PostprocessCharlesGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self) -> None:
        # 每个测试用独立的临时配置目录，避免相互污染真实/本机配置
        self._settings_tmp = tempfile.TemporaryDirectory()
        self._settings_dir_patcher = mock.patch.object(
            qt_app_module, "_SETTINGS_DIR", Path(self._settings_tmp.name)
        )
        self._settings_file_patcher = mock.patch.object(
            qt_app_module, "_SETTINGS_FILE", Path(self._settings_tmp.name) / "settings.json"
        )
        self._settings_dir_patcher.start()
        self._settings_file_patcher.start()
        self.window = CompareWindow(project_root=Path(__file__).resolve().parents[1])

    def tearDown(self) -> None:
        self.window.deleteLater()
        self._settings_file_patcher.stop()
        self._settings_dir_patcher.stop()
        self._settings_tmp.cleanup()

    def test_charles_widgets_present_and_toggle_reveals_path_row(self) -> None:
        w = self.window
        self.assertTrue(w.charles_row.isHidden())
        w.charles_exe.setText(r"C:\dummy\Charles.exe")
        w.charles_check.setChecked(True)
        self.assertFalse(w.charles_row.isHidden())
        self.assertTrue(w.charles_check.isChecked())
        w.charles_check.setChecked(False)
        self.assertTrue(w.charles_row.isHidden())
        self.assertFalse(w.charles_check.isChecked())

    def test_charles_enable_without_path_opens_browse_and_reverts_on_cancel(self) -> None:
        w = self.window
        with mock.patch.object(w, "_browse_charles_exe") as browse:
            w.charles_check.setChecked(True)
            browse.assert_called_once_with()
            w.charles_check.setChecked(False)
        self.assertFalse(w.charles_check.isChecked())

    def test_charles_validation(self) -> None:
        w = self.window
        self.assertEqual(w._charles_error(), "")
        # 先填入路径再开启，避免触发真实的文件选择对话框
        w.charles_exe.setText(r"C:\dummy\Charles.exe")
        w.charles_check.setChecked(True)
        self.assertIn("路径不存在", w._charles_error())
        w.charles_exe.setText("")
        self.assertIn("请选择 Charles.exe", w._charles_error())
        w.charles_check.setChecked(False)
        self.assertEqual(w._charles_error(), "")

    def test_start_run_passes_charles_exe_to_cli(self) -> None:
        w = self.window
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            release_exe = base / "release.exe"
            test_exe = base / "test.exe"
            charles_exe = base / "Charles.exe"
            for p in (release_exe, test_exe, charles_exe):
                p.write_bytes(b"x")
            project_set = base / "proj"
            project_set.mkdir()
            output_dir = base / "out"
            output_dir.mkdir()

            w.release_exe.setText(str(release_exe))
            w.release_version.setText("1.0-r")
            w.test_exe.setText(str(test_exe))
            w.test_version.setText("1.0-t")
            w.project_set.setText(str(project_set))
            w.output_dir.setText(str(output_dir))
            w.operation_buttons["texture"].click()

            w.charles_exe.setText(str(charles_exe))
            w.charles_check.setChecked(True)
            self.assertEqual(w._charles_error(), "")

            with mock.patch.object(w._process, "start") as start, \
                    mock.patch.object(w._process, "waitForStarted", return_value=True):
                w.start_run()
                _, args = start.call_args[0]
                self.assertIn("--charles-exe", args)
                self.assertEqual(
                    args[args.index("--charles-exe") + 1],
                    str(charles_exe),
                )

    def test_start_run_passes_delete_download_package_flag_when_checked(self) -> None:
        w = self.window
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            release_exe = base / "release.exe"
            test_exe = base / "test.exe"
            for p in (release_exe, test_exe):
                p.write_bytes(b"x")
            project_set = base / "proj"
            project_set.mkdir()
            output_dir = base / "out"
            output_dir.mkdir()

            w.release_exe.setText(str(release_exe))
            w.release_version.setText("1.0-r")
            w.test_exe.setText(str(test_exe))
            w.test_version.setText("1.0-t")
            w.project_set.setText(str(project_set))
            w.output_dir.setText(str(output_dir))
            w.operation_buttons["texture"].click()

            # 默认不勾选：不应传 --delete-download-package
            with mock.patch.object(w._process, "start") as start, \
                    mock.patch.object(w._process, "waitForStarted", return_value=True):
                w.start_run()
                _, args = start.call_args[0]
                self.assertNotIn("--delete-download-package", args)

            # 勾选后：应传 --delete-download-package
            w.delete_package_check.setChecked(True)
            with mock.patch.object(w._process, "start") as start, \
                    mock.patch.object(w._process, "waitForStarted", return_value=True):
                w.start_run()
                _, args = start.call_args[0]
                self.assertIn("--delete-download-package", args)

    def test_start_run_passes_skip_trip_model_flag_when_checked(self) -> None:
        w = self.window
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            release_exe = base / "release.exe"
            test_exe = base / "test.exe"
            for p in (release_exe, test_exe):
                p.write_bytes(b"x")
            project_set = base / "proj"
            project_set.mkdir()
            output_dir = base / "out"
            output_dir.mkdir()

            w.release_exe.setText(str(release_exe))
            w.release_version.setText("1.0-r")
            w.test_exe.setText(str(test_exe))
            w.test_version.setText("1.0-t")
            w.project_set.setText(str(project_set))
            w.output_dir.setText(str(output_dir))
            w.operation_buttons["human_body_completion"].click()

            # 默认不勾选：不应传 --skip-trip-model
            with mock.patch.object(w._process, "start") as start, \
                    mock.patch.object(w._process, "waitForStarted", return_value=True):
                w.start_run()
                _, args = start.call_args[0]
                self.assertNotIn("--skip-trip-model", args)

            # 勾选“不生成trip，直接生成人体补全模型”：应传 --skip-trip-model
            w.human_body_skip_trip.setChecked(True)
            with mock.patch.object(w._process, "start") as start, \
                    mock.patch.object(w._process, "waitForStarted", return_value=True):
                w.start_run()
                _, args = start.call_args[0]
                self.assertIn("--skip-trip-model", args)

    def test_advanced_button_replaces_inline_panel(self) -> None:
        w = self.window
        # 高级参数改为“按钮 + 摘要”，不再内联展开面板
        self.assertTrue(hasattr(w, "advanced_button"))
        self.assertTrue(hasattr(w, "advanced_summary"))
        self.assertFalse(hasattr(w, "advanced_panel"))
        self.assertFalse(hasattr(w, "advanced_toggle"))

    def test_advanced_dialog_timeouts_are_horizontal(self) -> None:
        from PyQt5 import QtCore

        w = self.window
        w.operation_buttons["ai_retexture"].click()
        dlg = w._build_advanced_dialog()
        w._sync_advanced_visibility()
        dlg.show()
        dlg.layout().activate()
        QtWidgets.QApplication.processEvents()

        def row_y(spin: QtWidgets.QDoubleSpinBox) -> int:
            return spin.mapTo(dlg, spin.rect().topLeft()).y()

        # 三项通用超时必须在同一水平行（避免纵向堆叠）
        self.assertEqual(
            len({row_y(w.operation_timeout), row_y(w.start_timeout), row_y(w.close_timeout)}),
            1,
        )

    def test_advanced_dialog_accept_updates_summary(self) -> None:
        from PyQt5 import QtCore

        w = self.window
        w.operation_buttons["ai_retexture"].click()

        def _mutate_and_accept() -> None:
            w.operation_timeout.setValue(321.0)
            w.ai_retexture_gaussian.setChecked(True)
            if w._advanced_dialog is not None:
                w._advanced_dialog.accept()

        QtCore.QTimer.singleShot(80, _mutate_and_accept)
        w._open_advanced()
        self.assertIn("321", w.advanced_summary.text())
        self.assertIn("高斯开", w.advanced_summary.text())

    def test_advanced_button_disabled_while_running(self) -> None:
        w = self.window
        self.assertTrue(w.advanced_button.isEnabled())
        w._set_running(True)
        self.assertFalse(w.advanced_button.isEnabled())
        w._set_running(False)
        self.assertTrue(w.advanced_button.isEnabled())

    def test_gaussian_quality_combo_defaults_and_visibility(self) -> None:
        w = self.window
        self.assertEqual(w.gaussian_quality.currentText(), "高质量")
        self.assertEqual(
            [w.gaussian_quality.itemText(i) for i in range(w.gaussian_quality.count())],
            ["快速", "标准", "高质量"],
        )
        # 未选择对比类型时高斯专属组隐藏
        self.assertTrue(w.gaussian_group.isHidden())
        # 高级参数弹窗未打开时，切换对比类型不得把专属选项组弹成独立顶层小窗
        w.operation_buttons["gaussian"].click()
        self.assertTrue(w.gaussian_group.isHidden())
        self.assertTrue(w.specific_none.isHidden())
        self.assertIn("质量高质量", w.advanced_summary.text())
        # 弹窗打开后，按所选对比类型在弹窗内展示对应专属选项组
        dlg = w._build_advanced_dialog()
        w._advanced_dialog = dlg
        w._sync_advanced_visibility()
        dlg.show()
        dlg.layout().activate()
        QtWidgets.QApplication.processEvents()
        self.assertIs(w.gaussian_group.parent(), dlg)
        self.assertFalse(w.gaussian_group.isHidden())
        self.assertTrue(w.specific_none.isHidden())

    def test_exclusive_option_groups_never_pop_as_top_level_windows(self) -> None:
        """回归：首次进入/切换对比类型时，无父级的专属选项组不得弹成顶层小窗。"""
        w = self.window
        for name in ("specific_none", "gaussian_group", "ai_group", "human_group"):
            widget = getattr(w, name)
            self.assertIsNone(widget.parent(), f"{name} 初始应无父级（仅存在于弹窗内）")
            self.assertTrue(widget.isHidden(), f"{name} 初始应隐藏")
        for key in ("texture", "gaussian", "ai_retexture", "human_body_completion"):
            w.operation_buttons[key].click()
            for name in ("specific_none", "gaussian_group", "ai_group", "human_group"):
                widget = getattr(w, name)
                self.assertIsNone(widget.parent())
                self.assertFalse(widget.isVisible(), f"弹窗未打开时 {name} 不得可见（避免顶层小窗）")
                self.assertTrue(widget.isHidden(), f"弹窗未打开时 {name} 应保持隐藏")

    def test_gaussian_quality_summary_updates_with_combo(self) -> None:
        w = self.window
        w.operation_buttons["gaussian"].click()
        w.gaussian_quality.setCurrentText("标准")
        w._update_advanced_summary()
        self.assertIn("质量标准", w.advanced_summary.text())

    def test_start_run_passes_gaussian_quality(self) -> None:
        w = self.window
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            release_exe = base / "release.exe"
            test_exe = base / "test.exe"
            for p in (release_exe, test_exe):
                p.write_bytes(b"x")
            project_set = base / "proj"
            project_set.mkdir()
            output_dir = base / "out"
            output_dir.mkdir()

            w.release_exe.setText(str(release_exe))
            w.release_version.setText("1.0-r")
            w.test_exe.setText(str(test_exe))
            w.test_version.setText("1.0-t")
            w.project_set.setText(str(project_set))
            w.output_dir.setText(str(output_dir))
            w.operation_buttons["gaussian"].click()
            w.gaussian_quality.setCurrentText("快速")

            with mock.patch.object(w._process, "start") as start, \
                    mock.patch.object(w._process, "waitForStarted", return_value=True):
                w.start_run()
                _, args = start.call_args[0]
                self.assertEqual(
                    args[args.index("--gaussian-quality") + 1],
                    "快速",
                )

    def _patch_settings(self, tmp: Path):
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(mock.patch.object(qt_app_module, "_SETTINGS_DIR", Path(tmp)))
        stack.enter_context(
            mock.patch.object(qt_app_module, "_SETTINGS_FILE", Path(tmp) / "settings.json")
        )
        return stack

    def test_save_settings_writes_config_json(self) -> None:
        w = self.window
        w.operation_buttons["gaussian"].click()
        w.release_exe.setText(r"D:\scan\release\CrealityScan.exe")
        w.release_version.setText("1.12.11")
        w.test_exe.setText(r"D:\scan\test\CrealityScan.exe")
        w.test_version.setText("1.13.1")
        w.project_set.setText(r"D:\projects")
        w.output_dir.setText(r"D:\out")
        w.gaussian_quality.setCurrentText("标准")
        w.ai_retexture_gaussian.setChecked(True)
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp = Path(temp_dir)
            with self._patch_settings(tmp):
                w._save_settings()
            data = json.loads((tmp / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(data["operation"], "gaussian")
        self.assertEqual(data["release_exe"], r"D:\scan\release\CrealityScan.exe")
        self.assertEqual(data["release_version"], "1.12.11")
        self.assertEqual(data["gaussian_quality"], "标准")
        self.assertTrue(data["ai_retexture_gaussian"])

    def test_restore_settings_populates_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp = Path(temp_dir)
            payload = {
                "operation": "gaussian",
                "release_exe": r"D:\scan\release\CrealityScan.exe",
                "release_version": "1.12.11",
                "test_exe": r"D:\scan\test\CrealityScan.exe",
                "test_version": "1.13.1",
                "project_set": r"D:\projects",
                "output_dir": r"D:\out",
                "operation_timeout": 123.0,
                "start_timeout": 45.0,
                "close_timeout": 12.0,
                "gaussian_quality": "标准",
                "delete_package": False,
                "charles": False,
                "charles_exe": "",
                "ai_retexture_gaussian": False,
                "ai_retexture_texture_first": True,
                "texture_timeout": 66.0,
                "human_body_hd_geometry": True,
                "human_body_skip_trip": True,
                "base_wait": 33.0,
            }
            (tmp / "settings.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            with self._patch_settings(tmp):
                w2 = CompareWindow(project_root=Path(__file__).resolve().parents[1])
            self.assertEqual(w2._selected_operation, "gaussian")
            self.assertEqual(w2.release_exe.text(), r"D:\scan\release\CrealityScan.exe")
            self.assertEqual(w2.release_version.text(), "1.12.11")
            self.assertEqual(w2.gaussian_quality.currentText(), "标准")
            self.assertEqual(w2.operation_timeout.value(), 123.0)
            self.assertEqual(w2.start_timeout.value(), 45.0)
            self.assertEqual(w2.close_timeout.value(), 12.0)
            self.assertEqual(w2.texture_timeout.value(), 66.0)
            self.assertTrue(w2.human_body_hd_geometry.isChecked())
            self.assertTrue(w2.human_body_skip_trip.isChecked())
            self.assertEqual(w2.base_wait.value(), 33.0)
            w2.deleteLater()

    def test_settings_round_trip_restores_last_config(self) -> None:
        w = self.window
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp = Path(temp_dir)
            w.operation_buttons["human_body_completion"].click()
            w.release_exe.setText(r"D:\scan\release\CrealityScan.exe")
            w.test_version.setText("1.99")
            w.human_body_hd_geometry.setChecked(True)
            w.human_body_skip_trip.setChecked(True)
            w.base_wait.setValue(77.0)
            w.operation_timeout.setValue(321.0)
            with self._patch_settings(tmp):
                w._save_settings()
                w2 = CompareWindow(project_root=Path(__file__).resolve().parents[1])
            self.assertEqual(w2._selected_operation, "human_body_completion")
            self.assertEqual(w2.release_exe.text(), r"D:\scan\release\CrealityScan.exe")
            self.assertEqual(w2.test_version.text(), "1.99")
            self.assertTrue(w2.human_body_hd_geometry.isChecked())
            self.assertTrue(w2.human_body_skip_trip.isChecked())
            self.assertEqual(w2.base_wait.value(), 77.0)
            self.assertEqual(w2.operation_timeout.value(), 321.0)
            w2.deleteLater()


if __name__ == "__main__":
    unittest.main()
