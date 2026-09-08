from __future__ import annotations

import importlib
import os
import re
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.window import activate_window


SUCCESS_CLEANUP_STEP_ID = "crealityscan.return_home"
SUCCESS_CLEANUP_STEP_VERSION = "1.0.0"
SUCCESS_CLEANUP_STEP_NAME = "返回首页"


def version_to_module(version: str) -> str:
    # "1.0.0" -> "v1_0_0"
    if not re.fullmatch(r"\d+(\.\d+)*", version or ""):
        # 允许未来使用非语义化版本，但模块名只能由安全字符组成
        safe = re.sub(r"[^0-9A-Za-z_]+", "_", version or "v0")
        return f"v{safe}"
    return "v" + version.replace(".", "_")


def _safe_filename_part(text: str, default: str = "step") -> str:
    value = (text or "").strip()
    value = re.sub(r'[<>:"/\\\\|?*]+', "_", value)
    value = re.sub(r"\s+", "_", value)
    value = value.strip("._ ")
    return value or default


def _set_current_step_env(idx: int, name: str, step_id: str, attempt: int) -> None:
    step_name_safe = _safe_filename_part(name or step_id, default=f"step{idx:03d}")
    os.environ["JENS_CURRENT_STEP_INDEX"] = f"{idx:03d}"
    os.environ["JENS_CURRENT_STEP_NAME"] = name or step_id
    os.environ["JENS_CURRENT_STEP_NAME_SAFE"] = step_name_safe
    os.environ["JENS_CURRENT_STEP_ATTEMPT"] = str(attempt)


def _clear_current_step_env() -> None:
    for key in (
        "JENS_CURRENT_STEP_INDEX",
        "JENS_CURRENT_STEP_NAME",
        "JENS_CURRENT_STEP_NAME_SAFE",
        "JENS_CURRENT_STEP_ATTEMPT",
    ):
        os.environ.pop(key, None)


def resolve_step_callable(step_id: str, version: str) -> Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]:
    """
    约定：step_id 以 "." 分隔，对应 steps 包的层级目录。
    例如：crealityscan.import_project + 1.0.0 =>
      steps.crealityscan.import_project.v1_0_0.impl:run
    """
    if not step_id or "." not in step_id:
        raise ValueError(f"非法 step_id: {step_id!r}（至少包含一个 '.'）")
    parts = step_id.split(".")
    mod_ver = version_to_module(version)
    module_name = ".".join(["steps", *parts, mod_ver, "impl"])
    mod = importlib.import_module(module_name)
    fn = getattr(mod, "run", None)
    if not callable(fn):
        raise AttributeError(f"步骤实现缺少可调用 run(ctx, params): {module_name}")
    return fn


def _try_snapshot(path: str) -> Optional[str]:
    try:
        from airtest.core.api import snapshot  # type: ignore

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        snapshot(filename=path)
        return path
    except Exception:
        return None


@dataclass
class StepFailurePolicy:
    action: str = "abort"  # abort | continue | retry
    max_retries: int = 0
    retry_wait_sec: float = 0.5


def _parse_on_fail(raw: Any) -> StepFailurePolicy:
    if not isinstance(raw, dict):
        return StepFailurePolicy()
    action = raw.get("action", "abort")
    if action not in {"abort", "continue", "retry"}:
        action = "abort"
    max_retries = int(raw.get("max_retries", 0) or 0)
    retry_wait_sec = float(raw.get("retry_wait_sec", 0.5) or 0.5)
    return StepFailurePolicy(action=action, max_retries=max_retries, retry_wait_sec=retry_wait_sec)


def _execute_success_cleanup(
    case: Dict[str, Any],
    run_dir: str,
    results: List[Dict[str, Any]],
    title_contains: str,
    step_index: int,
) -> bool:
    started = time.time()
    screenshot_path: Optional[str] = None
    _set_current_step_env(step_index, SUCCESS_CLEANUP_STEP_NAME, SUCCESS_CLEANUP_STEP_ID, 1)
    try:
        if title_contains:
            activate_window(title_contains)
        fn = resolve_step_callable(SUCCESS_CLEANUP_STEP_ID, SUCCESS_CLEANUP_STEP_VERSION)
        extra = fn(
            {
                "case": case,
                "run_dir": run_dir,
                "step_index": step_index,
                "env": dict(os.environ),
            },
            {},
        )
        cleanup_extra = dict(extra) if isinstance(extra, dict) else {}
        cleanup_extra["executor_cleanup"] = True
        results.append(
            {
                "id": SUCCESS_CLEANUP_STEP_ID,
                "version": SUCCESS_CLEANUP_STEP_VERSION,
                "name": SUCCESS_CLEANUP_STEP_NAME,
                "status": "passed",
                "duration_sec": round(time.time() - started, 3),
                "attempt": 1,
                "screenshot": None,
                "extra": cleanup_extra,
            }
        )
        return True
    except Exception:
        error = traceback.format_exc()
        screenshot_path = _try_snapshot(
            str(Path(run_dir) / "screenshots" / "success_cleanup_return_home_failed.png")
        )
        results.append(
            {
                "id": SUCCESS_CLEANUP_STEP_ID,
                "version": SUCCESS_CLEANUP_STEP_VERSION,
                "name": SUCCESS_CLEANUP_STEP_NAME,
                "status": "failed",
                "duration_sec": round(time.time() - started, 3),
                "attempt": 1,
                "screenshot": screenshot_path,
                "error": error,
                "extra": {"executor_cleanup": True},
            }
        )
        return False
    finally:
        _clear_current_step_env()


def execute_case(case: Dict[str, Any], run_dir: str) -> Tuple[List[Dict[str, Any]], bool]:
    """
    执行用例 steps，返回 (step_results, all_passed)。
    """
    steps = case.get("steps", [])
    if not isinstance(steps, list) or not steps:
        raise ValueError("case.steps 不能为空")

    app = case.get("app", {}) if isinstance(case.get("app"), dict) else {}
    title_contains = str(app.get("window_title_contains") or "CrealityScan")
    run_options = case.get("run_options") if isinstance(case.get("run_options"), dict) else {}
    try:
        start_step_index = int(run_options.get("start_step_index") or 1)
    except Exception:
        start_step_index = 1
    if start_step_index < 1:
        start_step_index = 1
    if start_step_index > len(steps):
        start_step_index = 1

    results: List[Dict[str, Any]] = []
    all_passed = True

    for idx, s in enumerate(steps, start=1):
        if not isinstance(s, dict):
            raise ValueError(f"step[{idx}] 必须是对象")
        step_id = str(s.get("id") or "")
        version = str(s.get("version") or "1.0.0")
        name = str(s.get("name") or step_id)
        step_name_safe = _safe_filename_part(name or step_id, default=f"step{idx:03d}")
        params = s.get("params") if isinstance(s.get("params"), dict) else {}
        on_fail = _parse_on_fail(s.get("on_fail"))

        if idx < start_step_index:
            results.append(
                {
                    "id": step_id,
                    "version": version,
                    "name": name,
                    "status": "skipped",
                    "duration_sec": 0,
                    "attempt": 0,
                    "screenshot": None,
                    "extra": {"reason": f"start_step_index={start_step_index}"},
                }
            )
            continue

        # 每步前激活/置顶窗口，提升 Template 点击稳定性
        if title_contains:
            activate_window(title_contains)

        fn = resolve_step_callable(step_id, version)
        attempt = 0
        last_err: Optional[str] = None
        screenshot_path: Optional[str] = None
        started = time.time()

        try:
            while True:
                attempt += 1
                _set_current_step_env(idx, name, step_id, attempt)
                try:
                    extra = fn(
                        {
                            "case": case,
                            "run_dir": run_dir,
                            "step_index": idx,
                            "env": dict(os.environ),
                        },
                        params,
                    )
                    dur = round(time.time() - started, 3)
                    results.append(
                        {
                            "id": step_id,
                            "version": version,
                            "name": name,
                            "status": "passed",
                            "duration_sec": dur,
                            "attempt": attempt,
                            "screenshot": screenshot_path,
                            "extra": extra if isinstance(extra, dict) else {},
                        }
                    )
                    break
                except Exception:
                    last_err = traceback.format_exc()
                    # 失败时抓一张图，方便报告定位
                    screenshot_path = _try_snapshot(
                        str(Path(run_dir) / "screenshots" / f"step{idx:03d}_{step_name_safe}_{attempt}_failed.png")
                    )

                    if on_fail.action == "retry" and attempt <= on_fail.max_retries:
                        time.sleep(on_fail.retry_wait_sec)
                        continue

                    dur = round(time.time() - started, 3)
                    results.append(
                        {
                            "id": step_id,
                            "version": version,
                            "name": name,
                            "status": "failed",
                            "duration_sec": dur,
                            "attempt": attempt,
                            "screenshot": screenshot_path,
                            "error": last_err,
                        }
                    )
                    all_passed = False
                    if on_fail.action == "continue":
                        break
                    # abort
                    return results, False
        finally:
            _clear_current_step_env()

    if all_passed:
        all_passed = _execute_success_cleanup(
            case,
            run_dir,
            results,
            title_contains,
            len(steps) + 1,
        )
    return results, all_passed
