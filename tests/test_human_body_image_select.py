# -*- coding: utf-8 -*-
"""后处理对比：人体补全 / AI重贴图 的图片选择弹窗逻辑测试。

覆盖“只有一张图片时直接填完整路径导入，不依赖点击文件列表”的修复：
- 单图：文件名框填入图片完整路径，点“打开”即导入，不再点击文件列表；
- 多图：先导航进入目录，再点击文件列表 + Ctrl+A 全选后确认；
- 单图直接导入未关闭弹窗时，回退到多图流程。
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from steps.tool.postprocess_compare.human_body_completion.v1_0_0 import impl as hb_impl
from steps.tool.postprocess_compare.ai_retexture_operation.v1_0_0 import impl as ai_impl


class _Dialog:
    """模拟 Windows 文件选择弹窗（#32770）的 pywinauto 控件树。"""

    def __init__(self, close_on_first_ok=False):
        self.file_name_edit = mock.Mock()
        self.open_button = mock.Mock()
        self.shell_view = mock.Mock()
        self._ok_calls = 0
        self._close_on_first_ok = close_on_first_ok

    def wait(self, *args, **kwargs):
        return None

    def wait_not(self, *args, **kwargs):
        self._ok_calls += 1
        if self._close_on_first_ok and self._ok_calls == 1:
            from pywinauto.timings import TimeoutError

            raise TimeoutError("dialog still visible (simulated)")
        return True

    def child_window(self, **kwargs):
        if kwargs.get("control_id") == 1148 and kwargs.get("class_name") == "Edit":
            return self.file_name_edit
        if kwargs.get("control_id") == 1 and kwargs.get("class_name") == "Button":
            return self.open_button
        if kwargs.get("class_name") == "SHELLDLL_DefView":
            return self.shell_view
        raise AssertionError(f"unexpected child_window call: {kwargs}")


def _run_select(func, img_dir, params=None):
    """在 patch 了 pywinauto.Desktop 的环境中执行选择函数，返回模拟的 dialog。"""
    dialog = _Dialog()
    desktop = mock.Mock()
    desktop.window.return_value = dialog
    sleep_log = []
    with mock.patch("pywinauto.Desktop", return_value=desktop):
        func(0, img_dir, params or {}, sleep_log.append)
    return dialog, sleep_log


class SelectHeadFrontImageSingleTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.img_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make(self, *names):
        for n in names:
            (self.img_dir / n).write_bytes(b"\xff\xd8\xff\xe0")
        return self.img_dir

    def test_single_image_uses_full_file_path_not_dir(self):
        for impl in (hb_impl, ai_impl):
            with self.subTest(impl=impl.__name__):
                func = getattr(impl, "_select_head_front_images" if impl is hb_impl else "_import_texture_images")
                self._make("liangtai.jpg")
                dialog, _ = _run_select(func, self.img_dir)
                dialog.file_name_edit.set_edit_text.assert_called_once_with(
                    str(self.img_dir / "liangtai.jpg")
                )
                dialog.open_button.click_input.assert_called_once()
                # 单图不得走“点击文件列表 + Ctrl+A”路径
                dialog.shell_view.click_input.assert_not_called()
                dialog.shell_view.type_keys.assert_not_called()

    def test_single_image_falls_back_to_dir_flow_when_not_closed(self):
        func = getattr(hb_impl, "_select_head_front_images")
        self._make("a.jpg")
        dialog = _Dialog(close_on_first_ok=True)
        desktop = mock.Mock()
        desktop.window.return_value = dialog
        sleep_log = []
        with mock.patch("pywinauto.Desktop", return_value=desktop):
            func(0, self.img_dir, {}, sleep_log.append)
        # 第一次失败后应回退到多图流程：
        # 第一次先填图片完整路径，弹窗未关闭后回退填目录路径导航
        set_edit_calls = dialog.file_name_edit.set_edit_text.call_args_list
        self.assertEqual(set_edit_calls[0], mock.call(str(self.img_dir / "a.jpg")))
        self.assertEqual(set_edit_calls[1], mock.call(str(self.img_dir)))
        dialog.shell_view.click_input.assert_called()
        dialog.shell_view.type_keys.assert_called_once_with("^a")

    def test_multiple_images_navigates_then_select_all(self):
        for impl in (hb_impl, ai_impl):
            with self.subTest(impl=impl.__name__):
                func = getattr(impl, "_select_head_front_images" if impl is hb_impl else "_import_texture_images")
                self._make("a.jpg", "b.png", "note.txt")
                dialog, _ = _run_select(func, self.img_dir)
                # 首步用目录路径导航进入目录
                self.assertEqual(
                    dialog.file_name_edit.set_edit_text.call_args_list[0],
                    mock.call(str(self.img_dir)),
                )
                dialog.shell_view.click_input.assert_called()
                dialog.shell_view.type_keys.assert_called_once_with("^a")
                dialog.open_button.click_input.assert_called()

    def test_single_image_case_insensitive_extension(self):
        for impl in (hb_impl, ai_impl):
            with self.subTest(impl=impl.__name__):
                func = getattr(impl, "_select_head_front_images" if impl is hb_impl else "_import_texture_images")
                self._make("photo.JPG")
                dialog, _ = _run_select(func, self.img_dir)
                dialog.file_name_edit.set_edit_text.assert_called_once_with(
                    str(self.img_dir / "photo.JPG")
                )


class DirectHumanBodyCompletionModeTest(unittest.TestCase):
    """人体补全“不生成trip，直接生成人体补全模型”高级参数模式。

    覆盖：点击AI人体补全后直接进入“选择人体模型”，选择模型底座，
    预览并等待AI人体补全进度条消失后应用，跳过导入图片/立即生成/创建人体模型。
    """

    def setUp(self):
        self.base = Path("templates")

    def _run(self, params=None, wait_side_effect=None):
        from airtest.core.api import Template  # noqa: F401

        touch = mock.Mock()
        sleep = mock.Mock()
        # _wait_progress_disappear 先等到进度条出现（True），再等到消失（False）
        exists = mock.Mock(
            side_effect=wait_side_effect if wait_side_effect is not None else [True, False]
        )
        hb_impl._run_direct_human_body_completion(
            self.base, params or {}, Template, exists, touch, sleep
        )
        return touch, sleep, exists

    def test_sequence_clicks_model_dialog_then_preview_then_apply(self):
        touch, sleep, exists = self._run()
        # 顺序：选择人体模型模板 -> (90,325) -> (140,720)选择模型底座 -> 预览 -> 应用
        args = [call.args[0] for call in touch.call_args_list]
        self.assertEqual(len(args), 5)
        # 模板点击（选择人体模型/预览/应用）传入的是 Template 对象而非坐标元组
        self.assertNotIsInstance(args[0], tuple)
        self.assertEqual(args[1], (90, 325))
        self.assertEqual(args[2], (140, 720))
        self.assertNotIsInstance(args[3], tuple)
        self.assertNotIsInstance(args[4], tuple)

    def test_waits_ai_body_complete_progress_then_sleeps(self):
        touch, sleep, exists = self._run()
        # 等待“AI人体补全”进度条（exists 模板）
        self.assertGreaterEqual(exists.call_count, 1)
        # 结束时按 click_delay_sec 稳定等待
        sleep.assert_called_once_with(0.5)

    def test_run_skip_trip_branch_skips_image_import(self):
        # run() 中 skip_trip_model=True 时应走直连分支，不调用图片选择逻辑
        import sys
        import types

        fake_touch = mock.Mock()
        fake_sleep = mock.Mock()
        fake_exists = mock.Mock(side_effect=[False, False])
        fake_Template = mock.Mock(return_value=mock.Mock())
        fake_snapshot = mock.Mock()

        airtest_api = types.ModuleType("airtest.core.api")
        airtest_api.Template = fake_Template
        airtest_api.exists = fake_exists
        airtest_api.snapshot = fake_snapshot
        airtest_api.touch = fake_touch
        airtest_api.sleep = fake_sleep
        with mock.patch.dict(sys.modules, {"airtest.core.api": airtest_api}):
            with mock.patch.object(
                hb_impl, "_run_direct_human_body_completion"
            ) as direct_mock, mock.patch.object(
                hb_impl, "_select_head_front_images"
            ) as select_mock:
                hb_impl.run(
                    {
                        "run_dir": "x",
                        "step_index": 2,
                    },
                    {"skip_trip_model": True},
                )
        direct_mock.assert_called_once()
        select_mock.assert_not_called()

    def test_run_full_branch_still_uses_image_import(self):
        import sys
        import types
        from tempfile import TemporaryDirectory

        fake_touch = mock.Mock()
        fake_sleep = mock.Mock()
        fake_exists = mock.Mock(side_effect=[False, False])
        fake_Template = mock.Mock(return_value=mock.Mock())
        fake_snapshot = mock.Mock()

        airtest_api = types.ModuleType("airtest.core.api")
        airtest_api.Template = fake_Template
        airtest_api.exists = fake_exists
        airtest_api.snapshot = fake_snapshot
        airtest_api.touch = fake_touch
        airtest_api.sleep = fake_sleep
        with TemporaryDirectory() as tmp, mock.patch.dict(
            sys.modules, {"airtest.core.api": airtest_api}
        ):
            run_dir = Path(tmp) / "round"
            run_dir.mkdir()
            (Path(tmp) / "img").mkdir()
            with mock.patch.object(
                hb_impl, "_run_direct_human_body_completion"
            ) as direct_mock, mock.patch.object(
                hb_impl, "_select_head_front_images"
            ) as select_mock, mock.patch.object(
                hb_impl, "_wait_progress_disappear"
            ):
                # 默认（skip_trip_model 缺省）走原有两步流程，需要图片选择
                hb_impl.run(
                    {
                        "run_dir": str(run_dir),
                        "step_index": 2,
                        "process_id": 1,
                    },
                    {},
                )
        direct_mock.assert_not_called()
        select_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
