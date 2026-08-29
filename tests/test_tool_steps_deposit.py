"""沉淀进平台的工具 Step 回归测试。

覆盖：
- 固件升级工具 / 标定分数查看工具 沉淀出的三个 Step 能被平台扫描发现
- 标定分数读取 Step 能独立解析最新日志（自包含，无需硬件）
- 各 Step 模块可导入且暴露 run(ctx, params)（不要求在导入时安装 Airtest）
- 固件 Step 的源工具目录解析可用
"""

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

NEW_STEP_MODULES = {
    "tool.calibration_score.read": (
        "steps.tool.calibration_score.read.v1_0_0.impl",
        "steps/tool/calibration_score/read/v1_0_0/step.json",
    ),
    "tool.firmware_upgrade.stream": (
        "steps.tool.firmware_upgrade.stream.v1_0_0.impl",
        "steps/tool/firmware_upgrade/stream/v1_0_0/step.json",
    ),
    "tool.firmware_upgrade.upgrade": (
        "steps.tool.firmware_upgrade.upgrade.v1_0_0.impl",
        "steps/tool/firmware_upgrade/upgrade/v1_0_0/step.json",
    ),
}


class ToolStepsDepositTests(unittest.TestCase):
    def test_new_tool_steps_are_discovered_by_registry(self) -> None:
        from jens_platform.step_registry import scan_steps

        metas = scan_steps(PROJECT_ROOT)
        ids = {meta.step_id for meta in metas}
        for step_id, (_, rel_step_json) in NEW_STEP_MODULES.items():
            with self.subTest(step_id=step_id):
                self.assertIn(step_id, ids)
                self.assertTrue((PROJECT_ROOT / rel_step_json).is_file(), rel_step_json)

    def test_new_steps_import_and_expose_run(self) -> None:
        for step_id, (module_name, _) in NEW_STEP_MODULES.items():
            with self.subTest(step_id=step_id):
                module = importlib.import_module(module_name)
                self.assertTrue(callable(getattr(module, "run", None)), module_name)

    def test_calibration_score_read_parses_latest_log(self) -> None:
        from steps.tool.calibration_score.read.v1_0_0.impl import run

        with tempfile.TemporaryDirectory() as tmp:
            logs_root = Path(tmp)

            old_day = logs_root / "20260828"
            old_day.mkdir()
            old_log = old_day / "scan_log_000.txt"
            old_log.write_text("old\n", encoding="utf-8")

            latest_day = logs_root / "20260829"
            latest_day.mkdir()
            log = latest_day / "scan_log_002.txt"
            log.write_text(
                "camera name: Otter\n"
                "camera serial number: SN123\n"
                "Scan QRCode SN : BOARD-1\n"
                "Calib calib score : 91.250000\n"
                "camera firmware version: 1.0.1\n",
                encoding="utf-8",
            )

            # 源工具按“最新修改时间”挑选日期目录/日志文件，这里显式制造新旧差异
            import os
            import time

            now = time.time()
            os.utime(str(old_day), (now - 100, now - 100))
            os.utime(str(old_log), (now - 100, now - 100))
            os.utime(str(latest_day), (now, now))
            os.utime(str(log), (now, now))

            ctx = {"case": {"app": {}}, "run_dir": tmp}
            data = run(ctx, {"log_dir": str(logs_root)})

            self.assertEqual(data["calibration_score"], "91.25")
            self.assertEqual(data["device_name"], "Otter")
            self.assertEqual(data["sn_code"], "SN123")
            self.assertEqual(data["calibration_board"], "BOARD-1")
            self.assertEqual(data["log_file"], "scan_log_002.txt")
            self.assertEqual(data["firmware_version"], "1.0.1")
            self.assertTrue(data["has_score"])

    def test_firmware_tool_root_resolves(self) -> None:
        from steps.tool.firmware_upgrade._tool_loader import resolve_tool_root

        root = resolve_tool_root()
        self.assertEqual(root.name, "固件升级工具")
        for rel in ("app_config.yaml", "device_config.yaml"):
            self.assertTrue((root / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
