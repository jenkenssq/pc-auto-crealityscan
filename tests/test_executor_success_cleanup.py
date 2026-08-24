from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine import executor


class ExecutorSuccessCleanupTests(unittest.TestCase):
    def test_failed_task_does_not_return_home(self) -> None:
        calls: list[str] = []

        def fake_resolve(step_id: str, version: str):
            def run(ctx, params):
                calls.append(step_id)
                raise RuntimeError("main step failed")

            return run

        case = {
            "steps": [
                {
                    "id": "demo.failure",
                    "version": "1.0.0",
                    "name": "failure",
                    "on_fail": {"action": "abort"},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(executor, "resolve_step_callable", side_effect=fake_resolve),
                patch.object(executor, "activate_window"),
                patch.object(executor, "_try_snapshot", return_value=None),
            ):
                results, all_passed = executor.execute_case(case, str(Path(temp_dir)))

        self.assertFalse(all_passed)
        self.assertEqual(calls, ["demo.failure"])
        self.assertEqual([result["id"] for result in results], ["demo.failure"])

    def test_continued_failure_does_not_return_home(self) -> None:
        calls: list[str] = []

        def fake_resolve(step_id: str, version: str):
            def run(ctx, params):
                calls.append(step_id)
                if step_id == "demo.failure":
                    raise RuntimeError("main step failed")
                return {"ok": True}

            return run

        case = {
            "steps": [
                {
                    "id": "demo.failure",
                    "version": "1.0.0",
                    "name": "failure",
                    "on_fail": {"action": "continue"},
                },
                {"id": "demo.after", "version": "1.0.0", "name": "after"},
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(executor, "resolve_step_callable", side_effect=fake_resolve),
                patch.object(executor, "activate_window"),
                patch.object(executor, "_try_snapshot", return_value=None),
            ):
                results, all_passed = executor.execute_case(case, str(Path(temp_dir)))

        self.assertFalse(all_passed)
        self.assertEqual(calls, ["demo.failure", "demo.after"])
        self.assertNotIn(executor.SUCCESS_CLEANUP_STEP_ID, [result["id"] for result in results])

    def test_cleanup_failure_marks_successful_task_failed(self) -> None:
        calls: list[str] = []

        def fake_resolve(step_id: str, version: str):
            def run(ctx, params):
                calls.append(step_id)
                if step_id == executor.SUCCESS_CLEANUP_STEP_ID:
                    raise RuntimeError("cleanup failed")
                return {"ok": True}

            return run

        case = {"steps": [{"id": "demo.success", "version": "1.0.0", "name": "success"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(executor, "resolve_step_callable", side_effect=fake_resolve),
                patch.object(executor, "activate_window"),
                patch.object(executor, "_try_snapshot", return_value=None),
            ):
                results, all_passed = executor.execute_case(case, str(Path(temp_dir)))

        self.assertFalse(all_passed)
        self.assertEqual(calls, ["demo.success", executor.SUCCESS_CLEANUP_STEP_ID])
        self.assertEqual(results[-1]["status"], "failed")
        self.assertTrue(results[-1]["extra"]["executor_cleanup"])


if __name__ == "__main__":
    unittest.main()
