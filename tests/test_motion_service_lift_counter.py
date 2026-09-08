import sys
import unittest
from pathlib import Path
from unittest.mock import patch


RAIL_DIR = Path(__file__).resolve().parents[1] / "滑轨"
sys.path.insert(0, str(RAIL_DIR))

from motion_service import MotionService


class _Controller:
    def __init__(self):
        self.calls = []

    def lift_up_with_duration(self, seconds):
        self.calls.append(("up", seconds))

    def lift_down_with_duration(self, seconds):
        self.calls.append(("down", seconds))

    def lift_down(self):
        self.calls.append("down_start")

    def lift_stop(self):
        self.calls.append("stop")


class MotionServiceLiftCounterTests(unittest.TestCase):
    def setUp(self):
        self.service = MotionService()
        self.service.controller = _Controller()

    def test_duration_moves_update_distance_from_bottom(self):
        self.service.cmd_lift_up_duration({"seconds": 20})
        self.assertEqual(self.service.cmd_get_lift_state({})["from_bottom_seconds"], 20.0)

        self.service.cmd_lift_down_duration({"seconds": 4})
        state = self.service.cmd_get_lift_state({})
        self.assertEqual(state["from_bottom_seconds"], 16.0)
        self.assertFalse(state["at_bottom"])

    def test_bottom_command_uses_remaining_counter(self):
        self.service.cmd_lift_up_duration({"seconds": 20})
        with patch("motion_service.time.sleep"):
            result = self.service.cmd_lift_down_to_bottom({"safety_margin": 1})

        self.assertEqual(result["duration"], 20.0)
        self.assertEqual(result["safety_margin"], 0.0)
        self.assertEqual(result["from_bottom_seconds"], 0.0)
        self.assertTrue(result["at_bottom"])
        self.assertIn("down_start", self.service.controller.calls)
        self.assertEqual(self.service.controller.calls[-1], "stop")

    def test_new_service_starts_at_bottom(self):
        state = self.service.cmd_get_lift_state({})
        self.assertEqual(state["from_bottom_seconds"], 0.0)
        self.assertTrue(state["position_known"])
        self.assertTrue(state["at_bottom"])

    def test_unknown_counter_falls_back_to_calibrated_full_descent(self):
        self.service._mark_lift_position_unknown()
        with patch("motion_service.time.sleep"):
            result = self.service.cmd_lift_down_to_bottom({"safety_margin": 1})

        self.assertEqual(result["duration"], 49.0)
        self.assertEqual(result["safety_margin"], 1.0)
        self.assertTrue(result["position_known"])


if __name__ == "__main__":
    unittest.main()
