# -*- coding: utf-8 -*-
"""后处理对比：导入工程成功判定日志关键字测试。

覆盖 _wait_project_import_success 对两类成功日志的判定：
- 原关键字 OB_SCAN_MESSAGE_ID_PROJECT_IMPORT_SUCCESS；
- 新增关键字 i proj progress 1.000000（任一命中即成功）；
- 两者都未出现时超时抛错。
"""
import tempfile
import unittest
from pathlib import Path

from steps.tool.postprocess_compare.import_project.v1_0_0 import impl as import_impl


class ImportProjectSuccessKeyTest(unittest.TestCase):
    def _wait(self, log_content: bytes, timeout_sec: float = 5.0) -> tuple:
        with tempfile.TemporaryDirectory() as td:
            log_dir = Path(td)
            log = log_dir / "scan_log_20260904_112517.txt"
            log.write_bytes(log_content)
            return import_impl._wait_project_import_success(
                log_root=log_dir,
                baseline_log=None,
                baseline_position=0,
                timeout_sec=timeout_sec,
                poll_interval_sec=0.05,
            )

    def test_original_key_still_success(self) -> None:
        marker = import_impl.PROJECT_IMPORT_SUCCESS_KEYS[0]
        log, elapsed, matched = self._wait(b"abc " + marker + b" def")
        self.assertTrue(log.name.startswith("scan_log_"))
        self.assertGreaterEqual(elapsed, 0)
        self.assertEqual(matched, marker)

    def test_new_progress_key_is_success(self) -> None:
        marker = b"i proj progress 1.000000"
        log, elapsed, matched = self._wait(b"[2026-09-04 11:25:17.435525][INFO] " + marker)
        self.assertTrue(log.name.startswith("scan_log_"))
        self.assertGreaterEqual(elapsed, 0)
        self.assertEqual(matched, marker)

    def test_timeout_raises_when_no_success_key(self) -> None:
        with self.assertRaises(RuntimeError) as cm:
            self._wait(b"some other log line", timeout_sec=0.2)
        self.assertIn("i proj progress 1.000000", str(cm.exception))

    def test_success_keys_include_both(self) -> None:
        keys = set(import_impl.PROJECT_IMPORT_SUCCESS_KEYS)
        self.assertEqual(
            keys,
            {b"OB_SCAN_MESSAGE_ID_PROJECT_IMPORT_SUCCESS", b"i proj progress 1.000000"},
        )


if __name__ == "__main__":
    unittest.main()
