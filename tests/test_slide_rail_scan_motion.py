import sys
import types
import unittest
from unittest.mock import patch

from engine.slide_rail_scan_motion import SlideRailScanMotion
from steps.crealityscan.scan_until_frames_reach_target_frame_points.v1_0_0 import impl as frame_points_impl
from 滑轨.zmotion_controller import ZMotionController


class _FakeMotionClient:
    def __init__(self, *, stop_client: bool = False):
        self.stop_client = stop_client
        self.connected = False
        self.disconnected = False
        self.cycle_kwargs = {}
        self.stop_called = False

    def connect(self):
        self.connected = True
        return True

    def disconnect(self):
        self.disconnected = True

    def is_controller_connected(self):
        return True

    def continuous_scan_cycle(self, **kwargs):
        self.cycle_kwargs = kwargs
        return {"status": "success"}

    def stop_continuous(self):
        self.stop_called = True
        return {"status": "success", "message": "已发送停止信号"}


class SlideRailScanMotionTests(unittest.TestCase):
    def test_motion_uses_required_defaults_and_sends_stop(self) -> None:
        cycle_client = _FakeMotionClient()
        stop_client = _FakeMotionClient(stop_client=True)
        clients = iter((cycle_client, stop_client))

        with patch(
            "engine.slide_rail_scan_motion._create_motion_client",
            side_effect=lambda _host, _port: next(clients),
        ):
            motion = SlideRailScanMotion({"slide_rail_scan_motion_enabled": True})
            motion.start()
            motion.stop()

        self.assertEqual(
            cycle_client.cycle_kwargs,
            {
                "scan_cycle_seconds": 4.0,
                "horizontal_pulse": 10000,
                "horizontal_speed": 2000,
            },
        )
        self.assertTrue(stop_client.stop_called)
        self.assertTrue(motion.to_extra()["stop_sent"])

    def test_disabled_motion_never_connects(self) -> None:
        with patch("engine.slide_rail_scan_motion._create_motion_client") as create_client:
            motion = SlideRailScanMotion({"slide_rail_scan_motion_enabled": False})
            motion.start()
            motion.stop()

        create_client.assert_not_called()
        self.assertEqual(motion.to_extra()["skipped_reason"], "disabled")

    def test_frame_points_stops_motion_before_pause_click(self) -> None:
        events = []

        class FakeTemplate:
            def __init__(self, filename, **_kwargs):
                self.filename = filename

        class FakeMotion:
            def __init__(self, _params):
                pass

            def start(self):
                events.append("motion_start")

            def stop(self):
                events.append("motion_stop")

            def to_extra(self):
                return {"started": True, "stop_sent": True}

        api = types.ModuleType("airtest.core.api")
        api.Template = FakeTemplate
        api.device = lambda: None
        api.move_to = lambda _pos: None
        api.sleep = lambda seconds: events.append(f"sleep:{seconds}")
        api.touch = lambda pos: events.append(f"touch:{pos}")
        api.wait = lambda template, timeout: template.filename
        core = types.ModuleType("airtest.core")
        core.api = api
        airtest = types.ModuleType("airtest")
        airtest.core = core

        with patch.dict(
            sys.modules,
            {"airtest": airtest, "airtest.core": core, "airtest.core.api": api},
        ), patch.object(frame_points_impl, "SlideRailScanMotion", FakeMotion), patch.object(
            frame_points_impl, "move_mouse_smooth", return_value=True
        ):
            result = frame_points_impl.run(
                {},
                {"wait_before_pause_sec": 5, "mouse_safe_sleep_sec": 0},
            )

        start_touch = next(index for index, event in enumerate(events) if event.startswith("touch:"))
        pause_touch = max(index for index, event in enumerate(events) if event.startswith("touch:"))
        self.assertLess(start_touch, events.index("motion_start"))
        self.assertLess(events.index("motion_start"), events.index("sleep:5.0"))
        self.assertLess(events.index("sleep:5.0"), events.index("motion_stop"))
        self.assertLess(events.index("motion_stop"), pause_touch)
        self.assertTrue(result["slide_rail_scan_motion"]["stop_sent"])

    def test_lift_down_repeats_command_away_from_top_limit(self) -> None:
        controller = ZMotionController.__new__(ZMotionController)
        commands = []
        controller.execute_command = lambda command: commands.append(command) or ""
        controller.read_input = lambda _input_number: 1

        with patch("滑轨.zmotion_controller.time.sleep", return_value=None):
            controller.lift_down()

        self.assertEqual(commands.count("OP(6,1)"), 15)
        self.assertIn("OP(6,0)", commands)
        self.assertIn("OP(7,0)", commands)


if __name__ == "__main__":
    unittest.main()
