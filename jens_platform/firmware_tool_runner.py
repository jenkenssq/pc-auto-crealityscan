from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from pathlib import Path
from typing import Optional, Sequence


PROGRESS_PREFIX = "[JENS_FIRMWARE_PROGRESS] "
RESULT_PREFIX = "[JENS_FIRMWARE_RESULT] "


class _StdoutQueue:
    def put(self, message: object) -> None:
        print(str(message), flush=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jens 固件升级工具执行器")
    parser.add_argument("--tool-root", required=True)
    parser.add_argument("--mode", required=True, choices=("stream_only", "upgrade", "downgrade", "cycle"))
    parser.add_argument("--upgrade-path", default="")
    parser.add_argument("--downgrade-path", default="")
    parser.add_argument("--cycle-count", type=int, default=1)
    parser.add_argument("--cycle-start", choices=("upgrade_first", "downgrade_first"), default="upgrade_first")
    parser.add_argument("--log-dir", default="")
    parser.add_argument("--connection-mode", choices=("usb", "wifi"), default="usb")
    parser.add_argument("--without-stream", action="store_true")
    parser.add_argument("--stop-file", required=True)
    return parser


def _watch_stop_file(stop_path: Path, stop_event: threading.Event, finished: threading.Event) -> None:
    while not finished.wait(0.2):
        if stop_path.exists():
            stop_event.set()
            print("[WARNING] 已收到停止请求，将在当前安全步骤结束后停止", flush=True)
            return


def _emit_result(
    success: bool,
    report_path: Optional[str],
    stopped: bool,
    stop_requested: bool = False,
    error: str = "",
) -> None:
    payload = {
        "success": bool(success),
        "report_path": str(report_path or ""),
        "stopped": bool(stopped),
        "stop_requested": bool(stop_requested),
        "error": error,
    }
    print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=False), flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    tool_root = Path(args.tool_root).resolve()
    stop_path = Path(args.stop_file).resolve()
    entry = tool_root / "testcases" / "test_firmware_cycle.py"
    if not entry.is_file():
        _emit_result(False, None, False, error=f"未找到固件测试入口：{entry}")
        return 2

    os.chdir(tool_root)
    sys.path.insert(0, str(tool_root))
    stop_event = threading.Event()
    finished = threading.Event()
    watcher = threading.Thread(
        target=_watch_stop_file,
        args=(stop_path, stop_event, finished),
        daemon=True,
    )
    watcher.start()

    try:
        from testcases.test_firmware_cycle import TestFirmwareCycle

        def on_progress(current: int, total: int) -> None:
            print(
                PROGRESS_PREFIX
                + json.dumps({"current": int(current), "total": int(total)}, ensure_ascii=False),
                flush=True,
            )

        test = TestFirmwareCycle(
            gui_log_queue=_StdoutQueue(),
            stop_event=stop_event,
            on_progress=on_progress,
            log_dir=args.log_dir or None,
            connection_mode=args.connection_mode,
            with_stream=not args.without_stream,
        )
        success, report_path = test.run(
            mode=args.mode,
            upgrade_path=args.upgrade_path or None,
            downgrade_path=args.downgrade_path or None,
            cycle_count=max(1, int(args.cycle_count)),
            cycle_start=args.cycle_start if args.mode == "cycle" else None,
            with_stream=not args.without_stream,
        )
        stopped = bool(getattr(test, "was_stopped", False))
        _emit_result(bool(success), report_path, stopped, stop_event.is_set())
        return 0 if success else 1
    except (FileNotFoundError, ImportError, IndexError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"[ERROR] 固件测试执行异常：{exc}", flush=True)
        _emit_result(False, None, False, stop_event.is_set(), str(exc))
        return 2
    finally:
        finished.set()
        try:
            stop_path.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
