from __future__ import annotations

import json
import unittest
from pathlib import Path

from jens_platform.task_generator import (
    TASK_GENERATOR_CONFIG,
    TASK_KIND_OPEN_STREAM,
    TASK_KIND_POSTPROCESS,
    build_task_model,
)


RETURN_HOME_STEP_ID = "crealityscan.return_home"


class TaskReturnHomeTests(unittest.TestCase):
    def test_saved_tasks_do_not_embed_return_home_step(self) -> None:
        tasks_dir = Path(__file__).resolve().parents[1] / "tasks"
        task_paths = sorted(path for path in tasks_dir.glob("*.json") if path.name.lower() != "_queue.json")
        self.assertTrue(task_paths)

        for task_path in task_paths:
            # 排除“压测”展开版基准任务（如 50 轮手工展开 JSON）：它是 A1-b
            # 手工展开版（每轮显式内嵌 return_home），仅作压测验收数据，
            # 不属常规任务，不适用“任务不内嵌 return_home”约定。
            if "压测" in task_path.name:
                continue
            with self.subTest(task=task_path.name):
                payload = json.loads(task_path.read_text(encoding="utf-8"))
                steps = payload.get("steps")
                self.assertIsInstance(steps, list)
                self.assertTrue(steps)
                return_home_steps = [step for step in steps if step.get("id") == RETURN_HOME_STEP_ID]
                self.assertEqual(return_home_steps, [])

    def test_generated_tasks_do_not_embed_return_home_step(self) -> None:
        for module_name in TASK_GENERATOR_CONFIG:
            for task_kind in (TASK_KIND_OPEN_STREAM, TASK_KIND_POSTPROCESS):
                with self.subTest(module=module_name, task_kind=task_kind):
                    model = build_task_model(module_name, task_kind, f"{module_name}{task_kind}")
                    self.assertTrue(model.steps)
                    self.assertNotIn(RETURN_HOME_STEP_ID, [step.step_id for step in model.steps])


if __name__ == "__main__":
    unittest.main()
