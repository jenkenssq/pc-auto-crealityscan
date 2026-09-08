from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from steps.crealityscan.pause_switch_point_cloud_scan.v1_0_0 import impl


def _write_log(path: Path, lines: list[bytes]) -> None:
    with path.open("wb") as fp:
        for line in lines:
            fp.write(line + b"\n")


def _wait_switch(log_file: Path, start_pos: int = 0) -> None:
    """以缩短的超时/轮询间隔调用被测函数，便于测试快速结束。"""
    with (
        mock.patch.object(impl, "POINT_CLOUD_SWITCH_TIMEOUT_SEC", 2.0),
        mock.patch.object(impl, "LOG_POLL_INTERVAL_SEC", 0.01),
    ):
        impl._wait_point_cloud_switch_success(log_file, start_pos)


class PauseSwitchPointCloudTests(unittest.TestCase):
    def test_sermoon_s1_marker_opt_progress_is_accepted(self) -> None:
        """Sermoon S1 固件：无 OB_SCAN_MESSAGE_ID_MARKER_FRAMEWORK_OPTIMIZATION_SUCCESS，
        但出现 marker_opt progress 1.000000，应判定切点云成功。"""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "scan_log_test.txt"
            _write_log(
                log,
                [
                    b"some earlier line",
                    b"[INFO] marker_opt progress 1.000000",
                    b"[INFO] obscan_scan_reconfig_scan_mode_config",
                    b"[INFO] scan_type: OB_SCAN_CLOUD_FUSED",
                    b"[INFO] start stream done.",
                    b"[INFO] config property ex done.",
                ],
            )
            # 不应抛出异常
            _wait_switch(log)

    def test_legacy_marker_framework_key_still_accepted(self) -> None:
        """旧固件：OB_SCAN_MESSAGE_ID_MARKER_FRAMEWORK_OPTIMIZATION_SUCCESS 仍可判定成功。"""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "scan_log_test.txt"
            _write_log(
                log,
                [
                    b"[INFO] OB_SCAN_MESSAGE_ID_MARKER_FRAMEWORK_OPTIMIZATION_SUCCESS",
                    b"[INFO] obscan_scan_reconfig_scan_mode_config",
                    b"[INFO] scan_type: OB_SCAN_CLOUD_FUSED",
                    b"[INFO] start stream done.",
                    b"[INFO] config property ex done.",
                ],
            )
            _wait_switch(log)

    def test_partial_progress_does_not_count_as_success(self) -> None:
        """未达到 1.000000 的中间进度不应作为成功标志。"""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "scan_log_test.txt"
            _write_log(
                log,
                [
                    b"[INFO] marker_opt progress 0.500000",
                    b"[INFO] marker_opt progress 0.900000",
                    b"[INFO] obscan_scan_reconfig_scan_mode_config",
                    b"[INFO] scan_type: OB_SCAN_CLOUD_FUSED",
                    b"[INFO] start stream done.",
                    b"[INFO] config property ex done.",
                ],
            )
            with self.assertRaises(RuntimeError) as ctx:
                _wait_switch(log)
            self.assertIn(b"marker_opt progress 1.000000", str(ctx.exception).encode("utf-8"))

    def test_timeout_error_lists_marker_alternatives(self) -> None:
        """首个标志缺失时，超时错误应同时提示两个候选（旧固件 + Sermoon S1）。"""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "scan_log_test.txt"
            _write_log(
                log,
                [
                    b"[INFO] obscan_scan_reconfig_scan_mode_config",
                    b"[INFO] scan_type: OB_SCAN_CLOUD_FUSED",
                    b"[INFO] start stream done.",
                    b"[INFO] config property ex done.",
                ],
            )
            with self.assertRaises(RuntimeError) as ctx:
                _wait_switch(log)
            msg = str(ctx.exception)
            self.assertIn("OB_SCAN_MESSAGE_ID_MARKER_FRAMEWORK_OPTIMIZATION_SUCCESS", msg)
            self.assertIn("marker_opt progress 1.000000", msg)


if __name__ == "__main__":
    unittest.main()
