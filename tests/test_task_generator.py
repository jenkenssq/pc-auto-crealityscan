import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jens_platform.task_generator import (
    CONNECTION_USB,
    CONNECTION_WIFI,
    MODULE_PRESET_SOURCES,
    TASK_KIND_OPEN_STREAM,
    TASK_KIND_POSTPROCESS,
    build_task_model,
    list_module_presets,
)


class TaskGeneratorTests(unittest.TestCase):
    @staticmethod
    def _write_presets(project_root: Path, step_dir: str, presets: list[dict]) -> Path:
        path = project_root / "steps" / "crealityscan" / step_dir / "v1_0_0" / "presets.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"group": "test", "presets": presets}, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def test_preset_file_is_the_dynamic_mode_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            path = self._write_presets(
                project_root,
                "configure_scan_params_p1",
                [{"key": "p1.mode.first", "name": "第一个模式", "actions": []}],
            )

            first_read = list_module_presets("P1", project_root=project_root)
            self.assertEqual([preset.name for preset in first_read], ["第一个模式"])

            path.write_text(
                json.dumps(
                    {
                        "presets": [
                            {"key": "p1.mode.first", "name": "第一个模式", "actions": []},
                            {"key": "p1.mode.new", "name": "新增模式", "actions": []},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            second_read = list_module_presets("P1", project_root=project_root)

            self.assertEqual([preset.name for preset in second_read], ["第一个模式", "新增模式"])

    def test_missing_app_steps_falls_back_to_packaged_resource_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            app_root = temp_root / "dist" / "jens_pc_app"
            resource_root = app_root / "_internal"
            app_root.mkdir(parents=True)
            self._write_presets(
                resource_root,
                "configure_scan_params_p1",
                [{"key": "p1.packaged", "name": "Packaged preset", "actions": []}],
            )

            with patch(
                "jens_platform.task_generator.get_resource_root",
                return_value=resource_root,
            ):
                presets = list_module_presets("P1", project_root=app_root)

            self.assertEqual([preset.key for preset in presets], ["p1.packaged"])

    def test_connection_only_filters_connection_specific_presets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_presets(
                project_root,
                "configure_scan_params_p1",
                [
                    {"key": "p1.common", "name": "公共模式", "actions": []},
                    {"key": "p1.usb", "name": "USB 模式", "connections": ["usb"], "actions": []},
                    {"key": "p1.wifi", "name": "Wi-Fi 模式", "connections": ["wifi"], "actions": []},
                ],
            )

            usb = list_module_presets("P1", project_root=project_root, connection_type=CONNECTION_USB)
            wifi = list_module_presets("P1", project_root=project_root, connection_type=CONNECTION_WIFI)

            self.assertEqual([preset.key for preset in usb], ["p1.common", "p1.usb"])
        self.assertEqual([preset.key for preset in wifi], ["p1.common", "p1.wifi"])

    def test_all_no_marker_presets_are_usb_only(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        modules = ("P1", "P1S", "pika", "S1", "X1", "raptor x", "raptor pro")

        for module_name in modules:
            with self.subTest(module_name=module_name):
                usb_presets = list_module_presets(
                    module_name, project_root=project_root, connection_type=CONNECTION_USB
                )
                wifi_presets = list_module_presets(
                    module_name, project_root=project_root, connection_type=CONNECTION_WIFI
                )
                usb_no_marker = [p for p in usb_presets if "no_marker" in p.key]
                wifi_no_marker = [p for p in wifi_presets if "no_marker" in p.key]
                self.assertGreaterEqual(len(usb_no_marker), 1)
                self.assertEqual(wifi_no_marker, [])

    def test_selected_order_target_frames_and_random_seed_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_presets(
                project_root,
                "configure_scan_params_p1",
                [
                    {"key": "p1.a", "name": "模式 A", "actions": []},
                    {"key": "p1.b", "name": "模式 B", "actions": []},
                    {"key": "p1.c", "name": "模式 C", "actions": []},
                ],
            )

            model = build_task_model(
                "P1",
                TASK_KIND_OPEN_STREAM,
                "随机任务",
                preset_keys=["p1.a", "p1.b", "p1.c"],
                target_frames=350,
                randomize=True,
                random_seed=7,
                project_root=project_root,
            )

            configured = [
                step.params["preset"]
                for step in model.steps
                if step.step_id == "crealityscan.configure_scan_params_p1"
            ]
            self.assertEqual(configured, ["p1.c", "p1.a", "p1.b"])
            scan_steps = [
                step for step in model.steps if step.step_id == "crealityscan.scan_until_frames_then_stop"
            ]
            self.assertEqual([step.params["target_frames"] for step in scan_steps], [350, 350, 350])
            self.assertEqual([step.name for step in scan_steps], ["扫描至350帧后完成"] * 3)

    def test_frame_points_and_postprocess_rules_come_from_preset_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_presets(
                project_root,
                "configure_scan_params_p1",
                [
                    {
                        "key": "p1.custom.frame",
                        "name": "自定义特殊扫描",
                        "task_profile": "frame_points",
                        "actions": [],
                    }
                ],
            )

            model = build_task_model(
                "P1",
                TASK_KIND_POSTPROCESS,
                "框架点任务",
                preset_keys=["p1.custom.frame"],
                project_root=project_root,
            )
            step_ids = [step.step_id for step in model.steps]

            self.assertIn("crealityscan.scan_until_frames_reach_target_frame_points", step_ids)
            self.assertIn("crealityscan.pause_switch_point_cloud_scan", step_ids)
            self.assertIn("crealityscan.preview_scan", step_ids)
            self.assertIn("crealityscan.fusion_operation", step_ids)
            self.assertIn("crealityscan.package_operation", step_ids)
            self.assertIn("crealityscan.texture_operation", step_ids)

    def test_postprocess_texture_rules_cover_all_real_presets(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        module_names = (
            "feeret",
            "otter",
            "otter lite",
            "otter lite basic",
            "P1",
            "P1S",
            "pika",
            "raptor",
            "raptor x",
            "raptor pro",
            "S1",
            "X1",
        )
        texture_off_count = 0
        line_laser_count = 0
        texture_on_count = 0
        no_marker_count = 0
        speckle_count = 0

        for module_name in module_names:
            for preset in list_module_presets(module_name, project_root=project_root):
                haystack = f"{preset.key} {preset.name}".lower()
                is_texture_off = any(
                    token in haystack for token in ("texture_off", "关闭贴图", "不贴图")
                )
                is_texture_on = any(
                    token in haystack for token in ("texture_on", "开启贴图")
                )
                is_no_marker = any(
                    token in haystack for token in ("no_marker", "无标记点", "无标志点")
                )
                is_line_laser = "line_laser" in haystack or "线激光" in preset.name
                is_speckle = "speckle" in preset.key.lower() or "散斑" in preset.name
                if (
                    not is_texture_off
                    and not is_texture_on
                    and not is_no_marker
                    and not is_line_laser
                    and not is_speckle
                ):
                    continue

                model = build_task_model(
                    module_name,
                    TASK_KIND_POSTPROCESS,
                    f"{module_name}-{preset.key}",
                    preset_keys=[preset.key],
                    project_root=project_root,
                )
                step_ids = [step.step_id for step in model.steps]

                if is_texture_off:
                    texture_off_count += 1
                    self.assertNotIn(
                        "crealityscan.texture_operation",
                        step_ids,
                        f"不贴图 preset 不应生成贴图步骤：{preset.key}",
                    )
                elif is_texture_on:
                    texture_on_count += 1
                    self.assertIn(
                        "crealityscan.texture_operation",
                        step_ids,
                        f"开启贴图 preset 应生成贴图步骤：{preset.key}",
                    )
                elif is_no_marker:
                    no_marker_count += 1
                    self.assertIn(
                        "crealityscan.texture_operation",
                        step_ids,
                        f"无标记点 preset 应保留默认贴图步骤：{preset.key}",
                    )
                elif is_line_laser:
                    line_laser_count += 1
                    self.assertNotIn(
                        "crealityscan.texture_operation",
                        step_ids,
                        f"线激光 preset 默认不应生成贴图步骤：{preset.key}",
                    )
                elif is_speckle:
                    speckle_count += 1
                    self.assertIn(
                        "crealityscan.texture_operation",
                        step_ids,
                        f"散斑 preset 应保留默认贴图步骤：{preset.key}",
                    )

        self.assertGreater(texture_off_count, 0)
        self.assertGreater(line_laser_count, 0)
        self.assertGreater(texture_on_count, 0)
        self.assertGreater(no_marker_count, 0)
        self.assertGreater(speckle_count, 0)

    def test_otter_lite_basic_uses_its_own_configure_step(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        presets = list_module_presets("otter lite basic", project_root=project_root)
        self.assertEqual(len(presets), 20)

        model = build_task_model(
            "otter lite basic",
            TASK_KIND_OPEN_STREAM,
            "Otter Lite Basic开流",
            preset_keys=[presets[0].key],
            project_root=project_root,
        )
        configure_steps = [
            step for step in model.steps if step.step_id.startswith("crealityscan.configure_scan_params_")
        ]
        self.assertEqual(len(configure_steps), 1)
        self.assertEqual(
            configure_steps[0].step_id,
            "crealityscan.configure_scan_params_otter_lite_basic",
        )

    def test_raptor_variants_use_their_own_configure_steps(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        variants = {
            "raptor x": ("crealityscan.configure_scan_params_raptor_x", 22, True),
            "raptor pro": ("crealityscan.configure_scan_params_raptor_pro", 21, False),
        }

        for module_name, (expected_step_id, expected_count, supports_single_line) in variants.items():
            with self.subTest(module_name=module_name):
                presets = list_module_presets(module_name, project_root=project_root)
                self.assertEqual(len(presets), expected_count)
                single_line_key = f"{module_name.replace(' ', '_')}.line_laser.point_cloud.single"
                self.assertEqual(single_line_key in {preset.key for preset in presets}, supports_single_line)

                model = build_task_model(
                    module_name,
                    TASK_KIND_OPEN_STREAM,
                    f"{module_name} open stream",
                    preset_keys=[presets[0].key],
                    project_root=project_root,
                )
                step_ids = [step.step_id for step in model.steps]
                configure_steps = [
                    step_id
                    for step_id in step_ids
                    if step_id.startswith("crealityscan.configure_scan_params_")
                ]
                self.assertEqual(configure_steps, [expected_step_id])
                self.assertNotIn("common.activate_window", step_ids)

    def test_pika_adds_waits_but_no_connection_step(self) -> None:
        root = Path(__file__).resolve().parents[1]
        model = build_task_model(
            "pika",
            TASK_KIND_OPEN_STREAM,
            "Pika USB",
            preset_keys=["pika.line_laser.point_cloud.no_marker"],
            connection_type=CONNECTION_USB,
            project_root=root,
        )
        step_ids = [step.step_id for step in model.steps]

        self.assertGreaterEqual(step_ids.count("common.sleep"), 3)
        self.assertNotIn("crealityscan.connect_device", step_ids)
        self.assertNotIn("common.connect_device", step_ids)

    def test_pika_frame_points_only_previews_after_switching_point_cloud(self) -> None:
        root = Path(__file__).resolve().parents[1]
        model = build_task_model(
            "pika",
            TASK_KIND_OPEN_STREAM,
            "Pika frame points",
            preset_keys=["pika.line_laser.frame_points.texture_on"],
            connection_type=CONNECTION_USB,
            project_root=root,
        )
        step_ids = [step.step_id for step in model.steps]

        self.assertEqual(step_ids.count("crealityscan.preview_scan"), 1)
        self.assertIn("crealityscan.scan_until_frames_reach_target_frame_points", step_ids)
        self.assertIn("crealityscan.pause_switch_point_cloud_scan", step_ids)
        self.assertIn("crealityscan.scan_until_frames_then_stop", step_ids)
        self.assertLess(
            step_ids.index("crealityscan.pause_switch_point_cloud_scan"),
            step_ids.index("crealityscan.preview_scan"),
        )

    def test_invalid_or_deleted_preset_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "preset 已不存在"):
            build_task_model(
                "P1",
                TASK_KIND_OPEN_STREAM,
                "失效任务",
                preset_keys=["p1.deleted.mode"],
            )

    def test_slide_rail_steps_are_absent_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_presets(
                project_root,
                "configure_scan_params_p1",
                [{"key": "p1.line_laser.point_cloud.cross", "name": "线激光-交叉线", "actions": []}],
            )
            model = build_task_model(
                "P1",
                TASK_KIND_OPEN_STREAM,
                "默认任务",
                preset_keys=["p1.line_laser.point_cloud.cross"],
                project_root=project_root,
            )
            self.assertNotIn("slide_rail.switch_position", [step.step_id for step in model.steps])

    def test_slide_rail_step_precedes_each_configure_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_presets(
                project_root,
                "configure_scan_params_p1",
                [
                    {"key": "p1.line_laser.point_cloud.cross", "name": "线激光-交叉线", "actions": []},
                    {"key": "p1.speckle.small.geometry", "name": "散斑-小物体-几何", "actions": []},
                ],
            )
            model = build_task_model(
                "P1",
                TASK_KIND_OPEN_STREAM,
                "滑轨任务",
                preset_keys=["p1.line_laser.point_cloud.cross", "p1.speckle.small.geometry"],
                project_root=project_root,
                slide_rail=True,
            )
            steps = model.steps
            step_ids = [step.step_id for step in steps]

            self.assertEqual(step_ids.count("slide_rail.switch_position"), 2)
            configure_indices = [
                index
                for index, step in enumerate(steps)
                if step.step_id == "crealityscan.configure_scan_params_p1"
            ]
            for configure_index in configure_indices:
                self.assertEqual(steps[configure_index - 1].step_id, "slide_rail.switch_position")
            rail_presets = [
                step.params["preset"]
                for step in steps
                if step.step_id == "slide_rail.switch_position"
            ]
            self.assertEqual(rail_presets, ["中物体", "小物体"])
            self.assertEqual(
                [step.name for step in steps if step.step_id == "slide_rail.switch_position"],
                ["移动滑轨位置至中物体", "移动滑轨位置至小物体"],
            )

    def test_slide_rail_option_controls_both_frame_point_scan_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_presets(
                project_root,
                "configure_scan_params_p1",
                [
                    {
                        "key": "p1.line_laser.frame_points.texture_on.usb",
                        "name": "线激光-框架点-开启贴图-usb",
                        "actions": [],
                    }
                ],
            )

            disabled_model = build_task_model(
                "P1",
                TASK_KIND_OPEN_STREAM,
                "不启用滑轨",
                preset_keys=["p1.line_laser.frame_points.texture_on.usb"],
                project_root=project_root,
                slide_rail=False,
            )
            enabled_model = build_task_model(
                "P1",
                TASK_KIND_OPEN_STREAM,
                "启用滑轨",
                preset_keys=["p1.line_laser.frame_points.texture_on.usb"],
                project_root=project_root,
                slide_rail=True,
            )

            scan_ids = {
                "crealityscan.scan_until_frames_reach_target_frame_points",
                "crealityscan.scan_until_frames_then_stop",
            }
            disabled_scan_steps = [step for step in disabled_model.steps if step.step_id in scan_ids]
            enabled_scan_steps = [step for step in enabled_model.steps if step.step_id in scan_ids]

            self.assertEqual(len(disabled_scan_steps), 2)
            self.assertEqual(len(enabled_scan_steps), 2)
            self.assertTrue(
                all(step.params["slide_rail_scan_motion_enabled"] is False for step in disabled_scan_steps)
            )
            self.assertTrue(
                all(step.params["slide_rail_scan_motion_enabled"] is True for step in enabled_scan_steps)
            )

    def test_slide_rail_position_mapping_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            self._write_presets(
                project_root,
                "configure_scan_params_p1",
                [
                    {"key": "p1.line_laser.point_cloud.cross", "name": "线激光", "actions": []},
                    {"key": "p1.line_laser.no_marker.cross", "name": "无标记点", "actions": []},
                    {"key": "p1.line_laser.frame_points.texture_on", "name": "框架点", "actions": []},
                    {"key": "p1.speckle.small.geometry", "name": "小物体", "actions": []},
                    {"key": "p1.speckle.medium.geometry", "name": "中物体", "actions": []},
                    {"key": "p1.speckle.large.geometry", "name": "大物体", "actions": []},
                    {"key": "p1.face.geometry", "name": "人脸", "actions": []},
                    {"key": "p1.body.geometry", "name": "人体", "actions": []},
                ],
            )
            model = build_task_model(
                "P1",
                TASK_KIND_OPEN_STREAM,
                "映射任务",
                preset_keys=[
                    "p1.line_laser.point_cloud.cross",
                    "p1.line_laser.no_marker.cross",
                    "p1.line_laser.frame_points.texture_on",
                    "p1.speckle.small.geometry",
                    "p1.speckle.medium.geometry",
                    "p1.speckle.large.geometry",
                    "p1.face.geometry",
                    "p1.body.geometry",
                ],
                project_root=project_root,
                slide_rail=True,
            )
            rail_presets = [
                step.params["preset"]
                for step in model.steps
                if step.step_id == "slide_rail.switch_position"
            ]
            self.assertEqual(
                rail_presets,
                ["中物体", "中物体", "中物体", "小物体", "中物体", "大物体", "人脸", "大物体"],
            )

    def test_slide_rail_mapping_covers_all_real_presets(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        module_names = (
            "feeret",
            "otter",
            "otter lite",
            "otter lite basic",
            "P1",
            "P1S",
            "pika",
            "raptor",
            "raptor x",
            "raptor pro",
            "S1",
            "X1",
        )
        valid_positions = {"小物体", "中物体", "人脸", "大物体"}

        for module_name in module_names:
            for preset in list_module_presets(module_name, project_root=project_root):
                with self.subTest(module_name=module_name, preset_key=preset.key):
                    model = build_task_model(
                        module_name,
                        TASK_KIND_OPEN_STREAM,
                        f"{module_name}-{preset.key}",
                        preset_keys=[preset.key],
                        project_root=project_root,
                        slide_rail=True,
                    )
                    steps = model.steps
                    step_ids = [step.step_id for step in steps]
                    configure_ids = [
                        step_id
                        for step_id in step_ids
                        if step_id.startswith("crealityscan.configure_scan_params_")
                    ]
                    self.assertEqual(len(configure_ids), 1)
                    configure_index = step_ids.index(configure_ids[0])
                    self.assertEqual(
                        steps[configure_index - 1].step_id,
                        "slide_rail.switch_position",
                    )
                    rail_steps = [
                        step for step in steps if step.step_id == "slide_rail.switch_position"
                    ]
                    self.assertEqual(len(rail_steps), 1)
                    self.assertIn(rail_steps[0].params["preset"], valid_positions)

    def test_slide_rail_mapping_respects_declared_size_for_all_modules(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        module_names = tuple(MODULE_PRESET_SOURCES)

        for module_name in module_names:
            for preset in list_module_presets(module_name, project_root=project_root):
                haystack = f"{preset.key} {preset.name} {' '.join(preset.aliases)}".lower()
                expected = "中物体"
                if "face" in haystack or "人脸" in haystack:
                    expected = "人脸"
                elif any(token in haystack for token in ("body", "人体", "large", "大物体")):
                    expected = "大物体"
                elif "small" in haystack or "小物体" in haystack:
                    expected = "小物体"

                with self.subTest(module_name=module_name, preset_key=preset.key):
                    model = build_task_model(
                        module_name,
                        TASK_KIND_OPEN_STREAM,
                        f"{module_name}-{preset.key}",
                        preset_keys=[preset.key],
                        project_root=project_root,
                        slide_rail=True,
                    )
                    rail_step = next(step for step in model.steps if step.step_id == "slide_rail.switch_position")
                    self.assertEqual(rail_step.params["preset"], expected)

    def test_otter_lite_basic_slide_rail_mapping_uses_compound_size_keys(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        expected = {
            "otter_lite_basic.small_geometry": "小物体",
            "otter_lite_basic.small_texture": "小物体",
            "otter_lite_basic.medium_geometry": "中物体",
            "otter_lite_basic.medium_marker": "中物体",
            "otter_lite_basic.large_geometry_fast": "大物体",
            "otter_lite_basic.large_texture_high_precision": "大物体",
            "otter_lite_basic.face_geometry": "人脸",
            "otter_lite_basic.body_geometry_fast": "大物体",
            "otter_lite_basic.frame_points_small": "小物体",
            "otter_lite_basic.frame_points_medium": "中物体",
            "otter_lite_basic.frame_points_large": "大物体",
        }

        for preset_key, expected_position in expected.items():
            with self.subTest(preset_key=preset_key):
                model = build_task_model(
                    "otter lite basic",
                    TASK_KIND_OPEN_STREAM,
                    f"Otter Lite Basic-{preset_key}",
                    preset_keys=[preset_key],
                    project_root=project_root,
                    slide_rail=True,
                )
                rail_step = next(step for step in model.steps if step.step_id == "slide_rail.switch_position")
                self.assertEqual(rail_step.params["preset"], expected_position)


if __name__ == "__main__":
    unittest.main()
