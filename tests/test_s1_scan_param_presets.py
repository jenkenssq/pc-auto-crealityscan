from __future__ import annotations

import unittest

from steps.crealityscan.configure_scan_params_s1.v1_0_0.impl import _load_presets, _resolve_preset


class S1ScanParamPresetTests(unittest.TestCase):
    def test_frame_point_wifi_presets(self) -> None:
        presets = _load_presets()

        wifi_on = _resolve_preset("s1.line_laser.frame_points.texture_on_wifi", presets)
        self.assertEqual(wifi_on["name"], "线激光-标记点-框架点-开启贴图-wifi")
        self.assertEqual(
            [action["pos"] for action in wifi_on["actions"]],
            [[90, 210], [70, 360], [318, 415]],
        )

        wifi_off = _resolve_preset("s1.line_laser.frame_points.texture_off_wifi", presets)
        self.assertEqual(wifi_off["name"], "线激光-标记点-框架点-关闭贴图-wifi")
        self.assertEqual(
            [action["pos"] for action in wifi_off["actions"]],
            [[90, 210], [70, 360]],
        )


if __name__ == "__main__":
    unittest.main()
