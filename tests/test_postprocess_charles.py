from __future__ import annotations

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


class PostprocessCharlesCliTests(unittest.TestCase):
    def test_parser_accepts_charles_exe(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["--charles-exe", r"C:\Program Files\Charles\Charles.exe"])
        self.assertEqual(args.charles_exe, r"C:\Program Files\Charles\Charles.exe")

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
        self.window = CompareWindow(project_root=Path(__file__).resolve().parents[1])

    def tearDown(self) -> None:
        self.window.deleteLater()

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


if __name__ == "__main__":
    unittest.main()
