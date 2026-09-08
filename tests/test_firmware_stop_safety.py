from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from unittest import mock


FIRMWARE_TOOL_ROOT = Path(__file__).parents[1] / "工具" / "固件升级工具"
if str(FIRMWARE_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_TOOL_ROOT))

from testcases.test_firmware_cycle import TestFirmwareCycle  # type: ignore  # noqa: E402


class FirmwareStopSafetyTests(unittest.TestCase):
    @staticmethod
    def _make_case() -> TestFirmwareCycle:
        case = TestFirmwareCycle.__new__(TestFirmwareCycle)
        case._stop_event = threading.Event()
        case._was_stopped = False
        case._on_progress = mock.Mock()
        case.logger = mock.Mock()
        case.stream_handler = mock.Mock()
        case.firmware_handler = mock.Mock()
        case._steps_results = {}
        case._screenshots = {}
        case._frame_data = {}
        return case

    def test_stop_after_pre_stream_skips_firmware_upgrade(self) -> None:
        case = self._make_case()

        def finish_stream(**_kwargs):
            case._stop_event.set()
            return True, None, {}

        case.stream_handler.start_stream.side_effect = finish_stream

        self.assertFalse(case._run_upgrade_only("upgrade.zip"))
        case.firmware_handler.upgrade_firmware.assert_not_called()
        self.assertTrue(case.was_stopped)

    def test_downgrade_first_cycle_stops_between_firmware_operations(self) -> None:
        case = self._make_case()

        def finish_downgrade(path):
            case._stop_event.set()
            return True, None

        case.firmware_handler.upgrade_firmware.side_effect = finish_downgrade

        self.assertFalse(
            case._run_cycle_no_stream(
                "upgrade.zip",
                "downgrade.zip",
                1,
                "downgrade_first",
            )
        )
        case.firmware_handler.upgrade_firmware.assert_called_once_with("downgrade.zip")
        self.assertTrue(case.was_stopped)

    def test_stop_requested_during_final_operation_is_not_false_stopped(self) -> None:
        case = self._make_case()
        calls = 0

        def finish_operation(_path):
            nonlocal calls
            calls += 1
            if calls == 2:
                case._stop_event.set()
            return True, None

        case.firmware_handler.upgrade_firmware.side_effect = finish_operation

        self.assertTrue(
            case._run_cycle_no_stream(
                "upgrade.zip",
                "downgrade.zip",
                1,
                "upgrade_first",
            )
        )
        self.assertEqual(case.firmware_handler.upgrade_firmware.call_count, 2)
        self.assertFalse(case.was_stopped)

    def test_downgrade_first_final_operation_is_not_false_stopped(self) -> None:
        case = self._make_case()
        calls = 0

        def finish_operation(_path):
            nonlocal calls
            calls += 1
            if calls == 2:
                case._stop_event.set()
            return True, None

        case.firmware_handler.upgrade_firmware.side_effect = finish_operation

        self.assertTrue(
            case._run_cycle_no_stream(
                "upgrade.zip",
                "downgrade.zip",
                1,
                "downgrade_first",
            )
        )
        self.assertEqual(case.firmware_handler.upgrade_firmware.call_count, 2)
        self.assertFalse(case.was_stopped)

    def test_stop_before_single_firmware_operation_skips_device_call(self) -> None:
        case = self._make_case()
        case._stop_event.set()

        self.assertFalse(case._run_upgrade_only_no_stream("upgrade.zip"))
        case.firmware_handler.upgrade_firmware.assert_not_called()
        self.assertTrue(case.was_stopped)


if __name__ == "__main__":
    unittest.main()
