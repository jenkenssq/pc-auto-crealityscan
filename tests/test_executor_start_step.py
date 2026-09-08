import tempfile
import unittest
from pathlib import Path

from engine import executor


class ExecutorStartStepTests(unittest.TestCase):
    def test_execute_case_skips_steps_before_start_step_index(self) -> None:
        calls: list[str] = []

        def fake_resolve(step_id: str, version: str):
            def run(ctx, params):
                calls.append(step_id)
                return {"called": step_id}

            return run

        original_resolve = executor.resolve_step_callable
        original_activate_window = executor.activate_window
        try:
            executor.resolve_step_callable = fake_resolve
            executor.activate_window = lambda title: None
            case = {
                "run_options": {"start_step_index": 2},
                "steps": [
                    {"id": "demo.one", "version": "1.0.0", "name": "one"},
                    {"id": "demo.two", "version": "1.0.0", "name": "two"},
                    {"id": "demo.three", "version": "1.0.0", "name": "three"},
                ],
            }
            with tempfile.TemporaryDirectory() as tmp_dir:
                results, all_passed = executor.execute_case(case, str(Path(tmp_dir)))
        finally:
            executor.resolve_step_callable = original_resolve
            executor.activate_window = original_activate_window

        self.assertTrue(all_passed)
        self.assertEqual(calls, ["demo.two", "demo.three", "crealityscan.return_home"])
        self.assertEqual([r["status"] for r in results], ["skipped", "passed", "passed", "passed"])
        self.assertEqual(results[0]["attempt"], 0)
        self.assertEqual(results[-1]["name"], "返回首页")
        self.assertTrue(results[-1]["extra"]["executor_cleanup"])


if __name__ == "__main__":
    unittest.main()
