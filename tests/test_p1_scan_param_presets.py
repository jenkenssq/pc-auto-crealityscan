from __future__ import annotations

import unittest

from steps.crealityscan.configure_scan_params_p1.v1_0_0.impl import _load_presets, _resolve_preset


class P1ScanParamPresetTests(unittest.TestCase):
    def test_frame_point_usb_and_wifi_presets(self) -> None:
        presets = _load_presets()

        usb_on = _resolve_preset("p1.line_laser.frame_points.texture_on", presets)
        self.assertEqual(usb_on["name"], "线激光-框架点-开启贴图-usb")
        self.assertEqual(_resolve_preset("线激光-框架点-开启贴图", presets), usb_on)

        usb_off = _resolve_preset("p1.line_laser.frame_points.texture_off", presets)
        self.assertEqual(usb_off["name"], "线激光-框架点-关闭贴图-usb")
        self.assertEqual(_resolve_preset("线激光-框架点-关闭贴图", presets), usb_off)

        wifi_on = _resolve_preset("p1.line_laser.frame_points.texture_on_wifi", presets)
        self.assertEqual(wifi_on["name"], "线激光-标记点-框架点-开启贴图-wifi")
        self.assertEqual(
            [action["pos"] for action in wifi_on["actions"]],
            [[90, 210], [70, 360], [318, 415]],
        )

        wifi_off = _resolve_preset("p1.line_laser.frame_points.texture_off_wifi", presets)
        self.assertEqual(wifi_off["name"], "线激光-标记点-框架点-关闭贴图-wifi")
        self.assertEqual(
            [action["pos"] for action in wifi_off["actions"]],
            [[90, 210], [70, 360]],
        )


if __name__ == "__main__":
    unittest.main()
