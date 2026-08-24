import unittest

from engine.report_html import render_report_html


class ReportHtmlTests(unittest.TestCase):
    def test_render_report_accepts_keyword_hit_counts(self) -> None:
        html = render_report_html(
            case_name="keyword-demo",
            started_at="",
            finished_at="",
            step_results=[],
            keyword_hits={"Exception": 112, "ERROR": 195},
            device_info={},
        )

        self.assertIn('<strong class="overview-value">307</strong>', html)

    def test_render_report_counts_selected_and_passed_scan_modes(self) -> None:
        html = render_report_html(
            case_name="mode-demo",
            started_at="2026-08-13T10:00:00",
            finished_at="2026-08-13T10:01:00",
            step_results=[
                {
                    "id": "crealityscan.configure_scan_params_p1",
                    "name": "扫描参数：线激光-框架点-开启贴图-usb",
                    "status": "passed",
                    "duration_sec": 3.456,
                    "extra": {"preset_name": "线激光-框架点-开启贴图-usb"},
                },
                {
                    "id": "crealityscan.configure_scan_params_s1",
                    "name": "扫描参数：线激光-标记点-框架点-关闭贴图-wifi",
                    "status": "passed",
                    "duration_sec": 4.567,
                },
                {"id": "crealityscan.configure_scan_params_raptor", "status": "failed"},
                {"id": "crealityscan.preview", "status": "passed"},
            ],
            keyword_hits={},
            device_info={},
        )

        self.assertIn('data-testid="passed-modes"', html)
        self.assertIn('<strong class="mode-value">2</strong>', html)
        self.assertIn('/ 已选择 3', html)
        self.assertIn('data-pass-percent="67"', html)
        self.assertIn('aria-haspopup="dialog"', html)
        self.assertIn('<dialog id="passed-modes-dialog"', html)
        self.assertEqual(html.count('data-testid="passed-mode-item"'), 2)
        self.assertIn("线激光-框架点-开启贴图-usb", html)
        self.assertIn("线激光-标记点-框架点-关闭贴图-wifi", html)
        self.assertIn("<dd>P1</dd>", html)
        self.assertIn("<dd>S1</dd>", html)
        self.assertIn("3.456s", html)
        self.assertIn("dialog.showModal()", html)
        self.assertIn('<th>步骤</th>', html)
        self.assertIn('<th>状态</th>', html)
        self.assertIn('class="report-header"', html)
        self.assertNotIn('Step Matrix', html)

    def test_render_report_shows_empty_passed_modes_state(self) -> None:
        html = render_report_html(
            case_name="empty-mode-demo",
            started_at="",
            finished_at="",
            step_results=[
                {"id": "crealityscan.configure_scan_params_raptor", "status": "failed"}
            ],
            keyword_hits={},
            device_info={},
        )

        self.assertIn('data-testid="passed-modes-empty"', html)
        self.assertIn("本次没有通过的扫描模式", html)
        self.assertNotIn('data-testid="passed-mode-item"', html)

    def test_render_report_localizes_raptor_variant_module_names(self) -> None:
        html = render_report_html(
            case_name="raptor-variants",
            started_at="",
            finished_at="",
            step_results=[
                {
                    "id": "crealityscan.configure_scan_params_raptor_x",
                    "name": "Raptor X mode",
                    "status": "passed",
                },
                {
                    "id": "crealityscan.configure_scan_params_raptor_pro",
                    "name": "Raptor Pro mode",
                    "status": "passed",
                },
            ],
            keyword_hits={},
            device_info={},
        )

        self.assertIn("<dd>Raptor X</dd>", html)
        self.assertIn("<dd>Raptor Pro</dd>", html)

    def test_render_report_counts_frame_point_scan_after_point_cloud_as_passed_mode(self) -> None:
        html = render_report_html(
            case_name="frame-point-demo",
            started_at="",
            finished_at="",
            step_results=[
                {
                    "id": "crealityscan.configure_scan_params_p1",
                    "name": "扫描参数：线激光-框架点-开启贴图-usb",
                    "status": "passed",
                    "duration_sec": 3.456,
                    "extra": {"preset_name": "线激光-框架点-开启贴图-usb"},
                },
                {
                    "id": "crealityscan.scan_until_frames_reach_target_frame_points",
                    "name": "开始扫描等待5秒并暂停（框架点）",
                    "status": "passed",
                    "duration_sec": 5.5,
                },
                {
                    "id": "crealityscan.pause_switch_point_cloud_scan",
                    "name": "切点云",
                    "status": "passed",
                    "duration_sec": 2.5,
                },
                {
                    "id": "crealityscan.preview_scan",
                    "name": "预览扫描",
                    "status": "passed",
                    "duration_sec": 1.0,
                },
                {
                    "id": "crealityscan.scan_until_frames_then_stop",
                    "name": "扫描至100帧后完成",
                    "status": "passed",
                    "duration_sec": 30.0,
                },
            ],
            keyword_hits={},
            device_info={},
        )

        self.assertEqual(html.count('data-testid="passed-mode-item"'), 2)
        self.assertIn('<strong class="mode-value">1</strong>', html)
        self.assertIn('/ 已选择 1', html)
        self.assertIn('data-pass-percent="100"', html)
        self.assertIn('<div class="mode-dialog-name">切点云</div>', html)
        self.assertIn("<dt>切点云耗时</dt>", html)
        self.assertIn("30.000s", html)
        self.assertIn("<dd>P1</dd>", html)
        dialog = html[html.find('<ul class="mode-dialog-list">'):]
        frame_pos = dialog.find("线激光-框架点-开启贴图-usb")
        point_pos = dialog.find('<div class="mode-dialog-name">切点云</div>')
        self.assertLess(frame_pos, point_pos)

    def test_render_report_does_not_count_failed_scan_after_point_cloud(self) -> None:
        html = render_report_html(
            case_name="frame-point-scan-fail-demo",
            started_at="",
            finished_at="",
            step_results=[
                {
                    "id": "crealityscan.configure_scan_params_p1",
                    "name": "扫描参数：线激光-框架点-开启贴图-usb",
                    "status": "passed",
                    "duration_sec": 3.456,
                    "extra": {"preset_name": "线激光-框架点-开启贴图-usb"},
                },
                {
                    "id": "crealityscan.pause_switch_point_cloud_scan",
                    "name": "切点云",
                    "status": "passed",
                    "duration_sec": 2.5,
                },
                {
                    "id": "crealityscan.scan_until_frames_then_stop",
                    "name": "扫描至100帧后完成",
                    "status": "failed",
                    "duration_sec": 30.0,
                },
            ],
            keyword_hits={},
            device_info={},
        )

        self.assertEqual(html.count('data-testid="passed-mode-item"'), 1)
        self.assertIn('<strong class="mode-value">1</strong>', html)
        self.assertIn('/ 已选择 1', html)
        self.assertNotIn('<div class="mode-dialog-name">切点云</div>', html)

    def test_render_report_does_not_count_scan_without_frame_point_mode(self) -> None:
        html = render_report_html(
            case_name="orphan-point-cloud-demo",
            started_at="",
            finished_at="",
            step_results=[
                {
                    "id": "crealityscan.scan_until_frames_then_stop",
                    "name": "扫描至100帧后完成",
                    "status": "passed",
                    "duration_sec": 30.0,
                },
            ],
            keyword_hits={},
            device_info={},
        )

        self.assertIn('data-testid="passed-modes-empty"', html)
        self.assertNotIn('<div class="mode-dialog-name">切点云</div>', html)

    def test_render_report_counts_point_cloud_scan_only_once_per_frame_point_block(self) -> None:
        html = render_report_html(
            case_name="mixed-blocks-demo",
            started_at="",
            finished_at="",
            step_results=[
                {
                    "id": "crealityscan.configure_scan_params_p1",
                    "name": "扫描参数：线激光-开启贴图-usb",
                    "status": "passed",
                    "duration_sec": 2.0,
                    "extra": {"preset_name": "线激光-开启贴图-usb"},
                },
                {
                    "id": "crealityscan.scan_until_frames_then_stop",
                    "name": "扫描至100帧后完成",
                    "status": "passed",
                    "duration_sec": 20.0,
                },
                {
                    "id": "crealityscan.configure_scan_params_p1",
                    "name": "扫描参数：线激光-框架点-开启贴图-usb",
                    "status": "passed",
                    "duration_sec": 3.456,
                    "extra": {"preset_name": "线激光-框架点-开启贴图-usb"},
                },
                {
                    "id": "crealityscan.pause_switch_point_cloud_scan",
                    "name": "切点云",
                    "status": "passed",
                    "duration_sec": 2.5,
                },
                {
                    "id": "crealityscan.scan_until_frames_then_stop",
                    "name": "扫描至100帧后完成",
                    "status": "passed",
                    "duration_sec": 30.0,
                },
            ],
            keyword_hits={},
            device_info={},
        )

        self.assertEqual(html.count('data-testid="passed-mode-item"'), 3)
        self.assertIn('<strong class="mode-value">2</strong>', html)
        self.assertIn('/ 已选择 2', html)
        self.assertEqual(html.count('<div class="mode-dialog-name">切点云</div>'), 1)

    def test_render_report_uses_total_mode_count_as_denominator(self) -> None:
        step_results = [
            {
                "id": "crealityscan.configure_scan_params_p1",
                "name": f"扫描参数：模式{i}",
                "status": "passed",
                "duration_sec": 1.0,
            }
            for i in range(1, 5)
        ] + [
            {
                "id": "crealityscan.configure_scan_params_p1",
                "name": "扫描参数：模式5",
                "status": "failed",
                "duration_sec": 1.0,
            }
        ]
        html = render_report_html(
            case_name="partial-run-demo",
            started_at="",
            finished_at="",
            step_results=step_results,
            keyword_hits={},
            device_info={},
            total_mode_count=20,
        )

        self.assertIn('<strong class="mode-value">4</strong>', html)
        self.assertIn('/ 已选择 20', html)
        self.assertIn('data-pass-percent="20"', html)
        self.assertEqual(html.count('data-testid="passed-mode-item"'), 4)

    def test_render_report_includes_localized_operation_elapsed_metric(self) -> None:
        html = render_report_html(
            case_name="metric-demo",
            started_at="2026-04-13T10:00:00",
            finished_at="2026-04-13T10:00:12",
            step_results=[
                {
                    "id": "crealityscan.fusion_operation",
                    "version": "1.0.0",
                    "name": "进行融合操作",
                    "status": "passed",
                    "duration_sec": 12.345,
                    "attempt": 1,
                    "screenshot": "artifacts/screenshots/fusion.png",
                    "extra": {
                        "operation_elapsed_sec": 11.234,
                        "operation_elapsed_label": "融合耗时",
                    },
                }
            ],
            keyword_hits={},
            device_info={},
        )

        self.assertIn("融合耗时 11.234s", html)
        self.assertIn("耗时（秒）", html)


if __name__ == "__main__":
    unittest.main()


class ReportHtmlSdkFpsTests(unittest.TestCase):
    def test_render_report_includes_sdk_fps_metrics(self) -> None:
        html = render_report_html(
            case_name="fps-demo",
            started_at="2026-04-13T10:00:00",
            finished_at="2026-04-13T10:00:12",
            step_results=[
                {
                    "id": "crealityscan.scan_until_frames_then_stop",
                    "version": "1.0.0",
                    "name": "扫描至目标帧后完成",
                    "status": "passed",
                    "duration_sec": 12.345,
                    "attempt": 1,
                    "screenshot": "",
                    "extra": {
                        "avg_fps": 47.825,
                        "peak_fps": 48.06,
                        "min_fps": 47.59,
                        "fps_seconds_count": 2,
                    },
                }
            ],
            keyword_hits={},
            device_info={},
        )

        self.assertIn("扫描帧率 47.825", html)
        self.assertNotIn("平均帧率 47.825", html)
        self.assertNotIn("峰值帧率 48.06", html)
        self.assertNotIn("最低帧率 47.59", html)
