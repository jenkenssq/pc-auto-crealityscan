import importlib.util
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets


SLIDE_RAIL_DIR = Path(__file__).resolve().parents[1] / "滑轨"
sys.path.insert(0, str(SLIDE_RAIL_DIR))
SPEC = importlib.util.spec_from_file_location("slide_rail_ui", SLIDE_RAIL_DIR / "slide_rail_ui.py")
slide_rail_ui = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(slide_rail_ui)


class _InputClient:
    def __init__(self, values):
        self.values = values

    def read_input(self, input_number):
        return {"status": "success", "value": self.values[input_number]}


class SlideRailLimitDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_compare_finds_low_level_trigger(self):
        middle = {port: 1 for port in range(16)}
        bottom = dict(middle)
        bottom[11] = 0

        self.assertEqual(slide_rail_ui.compare_limit_snapshots(middle, bottom), [(11, 1, 0)])

    def test_compare_keeps_multiple_candidates(self):
        middle = {port: 0 for port in range(16)}
        bottom = dict(middle)
        bottom[2] = 1
        bottom[7] = 1

        self.assertEqual(
            slide_rail_ui.compare_limit_snapshots(middle, bottom),
            [(2, 0, 1), (7, 0, 1)],
        )

    def test_read_limit_inputs_rejects_failed_port(self):
        class FailedClient:
            def read_input(self, input_number):
                if input_number == 4:
                    return {"status": "error", "message": "控制器未连接"}
                return {"status": "success", "value": 0}

        with self.assertRaisesRegex(RuntimeError, "IN4 读取失败"):
            slide_rail_ui.SlideRailWindow._read_limit_inputs(FailedClient())

    def test_window_reports_unique_candidate_and_can_clear(self):
        window = slide_rail_ui.SlideRailWindow()
        middle = {port: 1 for port in range(16)}
        bottom = dict(middle)
        bottom[11] = 0

        window._on_limit_snapshot_captured("middle", middle)
        window._on_limit_snapshot_captured("bottom", bottom)

        self.assertIn("候选下限位：IN11", window.limit_result_value.text())
        self.assertIn("低电平触发", window.limit_result_value.text())
        window._clear_limit_diagnostic()
        self.assertEqual(window.limit_result_value.text(), "等待两次采集")
        window.close()

    def test_read_limit_inputs_collects_all_sixteen_ports(self):
        values = {port: port % 2 for port in range(16)}

        self.assertEqual(
            slide_rail_ui.SlideRailWindow._read_limit_inputs(_InputClient(values)),
            values,
        )


if __name__ == "__main__":
    unittest.main()
