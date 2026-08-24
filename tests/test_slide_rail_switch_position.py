import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from steps.slide_rail.switch_position.v1_0_0 import impl


class _FakeClient:
    def __init__(self):
        self.calls = []
        self.disconnected = False

    def connect(self):
        self.calls.append("connect")
        return True

    def disconnect(self):
        self.calls.append("disconnect")
        self.disconnected = True

    def lift_down_to_bottom(self, safety_margin):
        self.calls.append(("lift_down_to_bottom", safety_margin))
        return {"status": "success", "message": "已下降到底（49.0秒）", "duration": 49.0}

    def get_position(self):
        self.calls.append("get_position")
        return {"status": "success", "position": 0}

    def move_absolute(self, position):
        self.calls.append(("move_absolute", position))
        return {"status": "success", "position": position}

    def lift_up_duration(self, seconds):
        self.calls.append(("lift_up_duration", seconds))
        return {"status": "success", "message": f"上升{seconds}秒完成"}

    def reset_to_zero(self):
        self.calls.append("reset_to_zero")
        return {"status": "success"}


class SlideRailSwitchPositionTests(unittest.TestCase):
    def test_lift_reaches_bottom_before_horizontal_move(self) -> None:
        client = _FakeClient()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            impl, "_create_client", return_value=client
        ):
            result = impl.run(
                {"run_dir": str(Path(temp_dir))},
                {"preset": "中物体"},
            )

        lower_index = client.calls.index(("lift_down_to_bottom", 1.0))
        move_index = client.calls.index(("move_absolute", 560000))
        self.assertLess(lower_index, move_index)
        self.assertTrue(client.disconnected)
        self.assertEqual(result["lower_lift_result"]["status"], "success")
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "lift_up_duration" for call in client.calls))

    def test_large_object_lifts_twenty_seconds_after_horizontal_move(self) -> None:
        client = _FakeClient()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            impl, "_create_client", return_value=client
        ):
            result = impl.run(
                {"run_dir": str(Path(temp_dir))},
                {"preset": "大物体"},
            )

        move_index = client.calls.index(("move_absolute", 170000))
        lift_index = client.calls.index(("lift_up_duration", 20.0))
        self.assertLess(move_index, lift_index)
        self.assertEqual(result["lift_up_seconds_after_move"], 20.0)
        self.assertEqual(result["lift_up_result"]["status"], "success")

    def test_large_object_lift_failure_fails_step(self) -> None:
        client = _FakeClient()
        client.lift_up_duration = lambda _seconds: {
            "status": "error",
            "message": "上升失败",
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            impl, "_create_client", return_value=client
        ):
            with self.assertRaisesRegex(RuntimeError, "上升失败"):
                impl.run(
                    {"run_dir": str(Path(temp_dir))},
                    {"preset": "大物体"},
                )

        self.assertTrue(client.disconnected)

    def test_lift_failure_prevents_horizontal_move(self) -> None:
        client = _FakeClient()
        client.lift_down_to_bottom = lambda _safety_margin: {
            "status": "error",
            "message": "下降失败",
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            impl, "_create_client", return_value=client
        ):
            with self.assertRaisesRegex(RuntimeError, "下降失败"):
                impl.run(
                    {"run_dir": str(Path(temp_dir))},
                    {"preset": "小物体"},
                )

        self.assertFalse(any(isinstance(call, tuple) and call[0] == "move_absolute" for call in client.calls))
        self.assertTrue(client.disconnected)


if __name__ == "__main__":
    unittest.main()
