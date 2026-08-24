import unittest
from pathlib import Path

from jens_platform.task_generator import CONNECTION_USB, CONNECTION_WIFI, list_module_presets
from steps.crealityscan.configure_scan_params_x1.v1_0_0.impl import _load_presets, _resolve_preset


class X1ScanParamPresetTests(unittest.TestCase):
    def test_frame_point_usb_and_wifi_presets(self) -> None:
        presets = _load_presets()

        usb_on = _resolve_preset("x1.line_laser.frame_points.texture_on", presets)
        self.assertEqual(usb_on["name"], "线激光-框架点-开启贴图-usb")
        self.assertEqual(_resolve_preset("线激光-框架点-开启贴图", presets), usb_on)

        usb_off = _resolve_preset("x1.line_laser.frame_points.texture_off", presets)
        self.assertEqual(usb_off["name"], "线激光-框架点-关闭贴图-usb")
        self.assertEqual(_resolve_preset("线激光-框架点-关闭贴图", presets), usb_off)

        wifi_on = _resolve_preset("x1.line_laser.frame_points.texture_on_wifi", presets)
        self.assertEqual(wifi_on["name"], "线激光-框架点-开启贴图-wifi")
        self.assertEqual(
            [action["pos"] for action in wifi_on["actions"]],
            [[90, 210], [70, 360], [317, 476]],
        )

        wifi_off = _resolve_preset("x1.line_laser.frame_points.texture_off_wifi", presets)
        self.assertEqual(wifi_off["name"], "线激光-框架点-关闭贴图-wifi")
        self.assertEqual(
            [action["pos"] for action in wifi_off["actions"]],
            [[90, 210], [70, 360]],
        )

    def test_task_creation_filters_x1_frame_points_by_connection(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        usb_keys = {
            preset.key
            for preset in list_module_presets(
                "X1", project_root=project_root, connection_type=CONNECTION_USB
            )
        }
        wifi_keys = {
            preset.key
            for preset in list_module_presets(
                "X1", project_root=project_root, connection_type=CONNECTION_WIFI
            )
        }

        self.assertIn("x1.line_laser.frame_points.texture_on", usb_keys)
        self.assertIn("x1.line_laser.frame_points.texture_off", usb_keys)
        self.assertNotIn("x1.line_laser.frame_points.texture_on_wifi", usb_keys)
        self.assertNotIn("x1.line_laser.frame_points.texture_off_wifi", usb_keys)
        self.assertIn("x1.line_laser.frame_points.texture_on_wifi", wifi_keys)
        self.assertIn("x1.line_laser.frame_points.texture_off_wifi", wifi_keys)
        self.assertNotIn("x1.line_laser.frame_points.texture_on", wifi_keys)
        self.assertNotIn("x1.line_laser.frame_points.texture_off", wifi_keys)


if __name__ == "__main__":
    unittest.main()
