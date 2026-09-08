from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from engine.io import dump_json
from engine.stress_process import StressProcessManager, _kill_process_tree
from jens_runtime import get_app_root


SUMMARY_JSON_NAME = "压测汇总.json"
SUMMARY_HTML_NAME = "压测汇总.html"
ROUND_DIR_PREFIX = "round"


@dataclass
class StressRoundResult:
    round_index: int
    status: str  # passed | failed | frozen | skipped | stopped
    reason: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_sec: float = 0.0
    round_dir: str = ""
    report_path: str = ""
    error: str = ""


@dataclass
class StressRunSummary:
    case_name: str
    exe_path: str
    total_rounds: int
    started_at: str = ""
    finished_at: str = ""
    duration_sec: float = 0.0
    passed_count: int = 0
    failed_count: int = 0
    frozen_count: int = 0
    skipped_count: int = 0
    stopped: bool = False
    rounds: list = field(default_factory=list)
    run_dir: str = ""

    @property
    def pass_rate(self) -> float:
        executed = self.passed_count + self.failed_count + self.frozen_count
        if executed <= 0:
            return 0.0
        return round(self.passed_count / executed * 100.0, 2)


def _safe_dir_name(name: str) -> str:
    import re

    name = name.strip() or "case"
    name = re.sub(r'[<>:"/\\\\|?*]+', "_", name)
    return name


def _round_argv(project_root: Path, case_path: Path, round_dir: Path) -> list[str]:
    """构造单轮执行的子进程 argv。"""
    if getattr(sys, "frozen", False):
        return [
            str(project_root / "jens_runner_helper.exe"),
            "--stress-round",
            "--case",
            str(case_path),
            "--round-dir",
            str(round_dir),
        ]
    return [
        sys.executable,
        str(project_root / "platform_app.py"),
        "--stress-round",
        "--case",
        str(case_path),
        "--round-dir",
        str(round_dir),
    ]


class _FileStopFlag:
    """跨进程停止标志：GUI 侧写入 stop-file，编排进程轮询到即优雅收尾。

    兼容内存版 stop_event（进程内直接置位）；两者任一触发即视为停止请求。
    """

    def __init__(self, stop_file: Optional[str] = None, stop_event=None) -> None:
        self._stop_file = Path(stop_file) if stop_file else None
        self._stop_event = stop_event

    def is_set(self) -> bool:
        if self._stop_event is not None and self._stop_event.is_set():
            return True
        if self._stop_file is not None and self._stop_file.exists():
            return True
        return False


class _RoundMonitor:
    """单轮运行监视器：读取子进程输出 + 监听 CrealityScan 日志推进，用于卡死判定。

    活动来源（任一发生即视为未卡死）：
      - 轮次子进程 stdout 有任何输出（步骤心跳、日志打印等）；
      - CrealityScan 日志目录出现新写入（scan_log_*.txt 的 mtime/大小变化）。
    若两类活动持续静默超过 freeze_timeout_sec，则判定该轮“软件卡死”。
    """

    def __init__(
        self,
        proc: subprocess.Popen,
        log_root: Optional[str],
        freeze_timeout_sec: float,
        check_interval_sec: float = 1.0,
    ) -> None:
        self.proc = proc
        self.log_root = Path(log_root) if log_root else None
        self.freeze_timeout_sec = float(freeze_timeout_sec)
        self.check_interval_sec = check_interval_sec
        self._last_activity = time.time()
        self._lock = threading.Lock()
        self._log_sig = self._snapshot_log_signature()
        self._lines: list[str] = []
        self._reader = threading.Thread(target=self._read_output, daemon=True, name="stress-round-reader")
        self._reader.start()

    def _read_output(self) -> None:
        try:
            for line in self.proc.stdout:
                self._push((line or "").rstrip("\r\n"))
        except Exception:
            pass
        finally:
            try:
                self.proc.stdout.close()
            except Exception:
                pass

    def _push(self, line: str) -> None:
        if not line:
            return
        with self._lock:
            self._lines.append(line)
            if len(self._lines) > 5000:
                del self._lines[:1000]
            self._last_activity = time.time()

    def output_lines(self) -> list[str]:
        with self._lock:
            return list(self._lines)

    def _snapshot_log_signature(self):
        if not self.log_root or not self.log_root.exists():
            return None
        try:
            if self.log_root.is_file():
                st = self.log_root.stat()
                return (st.st_mtime, st.st_size, 1)
            max_mtime = 0.0
            total_size = 0
            count = 0
            for fp in self.log_root.rglob("*.txt"):
                try:
                    st = fp.stat()
                    max_mtime = max(max_mtime, st.st_mtime)
                    total_size += st.st_size
                    count += 1
                except OSError:
                    continue
            return (max_mtime, total_size, count)
        except OSError:
            return None

    def poll(self) -> None:
        """由编排循环周期调用；若日志有推进则刷新活动时间。"""
        sig = self._snapshot_log_signature()
        if sig != self._log_sig:
            self._log_sig = sig
            with self._lock:
                self._last_activity = time.time()

    def is_frozen(self) -> bool:
        with self._lock:
            return (time.time() - self._last_activity) > self.freeze_timeout_sec

    def close(self) -> None:
        if self.proc.poll() is not None:
            self._reader.join(timeout=2)


def _execute_round(proc: subprocess.Popen, monitor: _RoundMonitor) -> tuple[str, Optional[int]]:
    """运行单轮并监控，返回 (status, exit_code)。

    status: passed | failed | frozen

    按 D4-a 约定，停止不中断当前轮：本函数只负责把当前轮完整跑完
    （正常结束或卡死判定后结束），停止请求在下一轮开始前由编排循环生效。
    """
    while True:
        monitor.poll()
        ret = proc.poll()
        if ret is not None:
            monitor.close()
            return ("passed" if ret == 0 else "failed"), ret
        if monitor.is_frozen():
            _kill_process_tree(proc.pid)
            monitor.close()
            return "frozen", None
        time.sleep(monitor.check_interval_sec)


def _spawn_round_process(project_root: Path, case_path: Path, round_dir: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        _round_argv(project_root, case_path, round_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(project_root),
        bufsize=1,
    )


def run_stress_round(case_path: str, round_dir: str) -> int:
    """单轮执行入口（--stress-round）：在指定 round 目录内完整跑一次任务。"""
    from jens_runner_entry import run_case

    return int(run_case(case_path, run_dir=round_dir))


def run_stress_case(
    case_path: str,
    exe_path: str,
    rounds: int,
    *,
    freeze_timeout_sec: float = 180.0,
    launch_timeout_sec: float = 120.0,
    popup_timeout_sec: float = 40.0,
    stop_event=None,
    stop_file: Optional[str] = None,
) -> int:
    """压测模式总编排入口（--stress-run）。

    流程：
      - 首轮保证 CrealityScan 运行（可复用已在运行的实例）；
      - 每轮启动独立轮次子进程执行整个任务；
      - 轮次通过 -> 复用软件直接下一轮；
      - 轮次失败/卡死 -> 截图+日志已由轮次保留，强杀进程 -> 重开 ->
        处理“软件意外退出”上报弹窗（点取消）-> 下一轮。
      - 输出压测汇总 JSON/HTML。
      - 停止：进程内 stop_event 或 GUI 侧 stop_file（跨进程）任一触发，
        当前轮安全退出后不再启动下一轮，并照常落汇总。
    """
    app_root = get_app_root()
    project_root = app_root
    case = _load_case(case_path)
    case_name = str(case.get("name") or case.get("case_id") or "case")
    app = case.get("app") if isinstance(case.get("app"), dict) else {}
    log_root = str(app.get("log_dir") or "").strip()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = app_root / "artifacts" / f"{_safe_dir_name(case_name)}_压测_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    stop_flag = _FileStopFlag(stop_file=stop_file, stop_event=stop_event)

    manager = StressProcessManager(Path(exe_path))
    started_at = datetime.now().isoformat(timespec="seconds")
    round_results: list[StressRoundResult] = []

    try:
        manager.ensure_running(launch_timeout_sec=launch_timeout_sec)
        print(f"[STRESS] initial CrealityScan running pid={manager.find_running_pid()}")
    except Exception as exc:
        print(f"[STRESS][ERROR] 无法启动/找到 CrealityScan：{exc}")
        for i in range(1, rounds + 1):
            round_results.append(
                StressRoundResult(
                    round_index=i,
                    status="failed",
                    reason="CrealityScan 启动失败",
                    error=str(exc),
                )
            )
        finished_at = datetime.now().isoformat(timespec="seconds")
        summary = _build_summary(case_name, exe_path, rounds, run_dir, started_at, finished_at, round_results, stopped=False)
        _write_stress_summary(summary)
        print(f"[JENS] stress_run_dir={run_dir}")
        print(f"[JENS] stress_summary={run_dir / SUMMARY_JSON_NAME}")
        print(f"[JENS] stress_status=FAILED")
        return 1

    stopped = False
    for i in range(1, rounds + 1):
        if stop_flag.is_set():
            stopped = True
            print("[STRESS] user requested stop, aborting remaining rounds")
            break

        round_dir = run_dir / f"{ROUND_DIR_PREFIX}{i:02d}"
        round_dir.mkdir(parents=True, exist_ok=True)
        round_started = datetime.now().isoformat(timespec="seconds")
        t0 = time.time()

        try:
            manager.ensure_running(launch_timeout_sec=launch_timeout_sec)
        except Exception as exc:
            round_results.append(
                StressRoundResult(
                    round_index=i,
                    status="failed",
                    reason="CrealityScan 启动失败",
                    error=str(exc),
                    started_at=round_started,
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    round_dir=str(round_dir),
                )
            )
            print(f"[STRESS] round {i}/{rounds} FAILED (启动失败): {exc}")
            continue

        try:
            proc = _spawn_round_process(project_root, Path(case_path), round_dir)
            monitor = _RoundMonitor(proc, log_root, freeze_timeout_sec)
            status, exit_code = _execute_round(proc, monitor)
            monitor.close()
            duration = round(time.time() - t0, 3)
            round_finished = datetime.now().isoformat(timespec="seconds")
            report_path = round_dir / "report.html"

            if status == "passed":
                result = StressRoundResult(
                    round_index=i,
                    status="passed",
                    reason="",
                    started_at=round_started,
                    finished_at=round_finished,
                    duration_sec=duration,
                    round_dir=str(round_dir),
                    report_path=str(report_path) if report_path.is_file() else "",
                )
                print(f"[STRESS] round {i}/{rounds} PASSED in {duration:.1f}s")
            else:
                if status == "frozen":
                    reason = "软件卡死（日志/心跳静默超时）"
                    error_text = f"freeze_timeout_sec={freeze_timeout_sec:g}"
                else:
                    reason = f"步骤失败 exit_code={exit_code}"
                    error_text = f"round_exit_code={exit_code}"
                result = StressRoundResult(
                    round_index=i,
                    status=status,
                    reason=reason,
                    error=error_text,
                    started_at=round_started,
                    finished_at=round_finished,
                    duration_sec=duration,
                    round_dir=str(round_dir),
                    report_path=str(report_path) if report_path.is_file() else "",
                )
                print(f"[STRESS] round {i}/{rounds} {status.upper()} in {duration:.1f}s, recovering...")
                try:
                    manager.recover(
                        launch_timeout_sec=launch_timeout_sec,
                        popup_timeout_sec=popup_timeout_sec,
                        evidence_dir=round_dir / "recovery",
                    )
                except Exception as exc:
                    print(f"[STRESS][WARN] 轮次恢复失败（将尝试下一轮）: {exc}")
            round_results.append(result)
        except Exception as exc:
            # 轮次内部异常（启动子进程失败、监视器异常等）不中断整体压测：
            # 本轮记失败 -> 尝试恢复 -> 继续下一轮。
            if "monitor" in locals():
                try:
                    monitor.close()
                except Exception:
                    pass
            result = StressRoundResult(
                round_index=i,
                status="failed",
                reason="轮次执行异常",
                error=str(exc),
                started_at=round_started,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                duration_sec=round(time.time() - t0, 3),
                round_dir=str(round_dir),
            )
            print(f"[STRESS] round {i}/{rounds} FAILED (异常): {exc}")
            try:
                manager.recover(
                    launch_timeout_sec=launch_timeout_sec,
                    popup_timeout_sec=popup_timeout_sec,
                    evidence_dir=round_dir / "recovery",
                )
            except Exception as rec_exc:
                print(f"[STRESS][WARN] 轮次恢复失败（将尝试下一轮）: {rec_exc}")
            round_results.append(result)

    finished_at = datetime.now().isoformat(timespec="seconds")
    summary = _build_summary(case_name, exe_path, rounds, run_dir, started_at, finished_at, round_results, stopped=stopped)
    _write_stress_summary(summary)

    all_passed = summary.passed_count == summary.total_rounds and not summary.stopped
    print(f"[JENS] stress_run_dir={run_dir}")
    print(f"[JENS] stress_summary={run_dir / SUMMARY_JSON_NAME}")
    print(f"[JENS] stress_status={'PASSED' if all_passed else 'FAILED'}")
    print(f"[JENS] stress_stats=passed={summary.passed_count} failed={summary.failed_count} "
          f"frozen={summary.frozen_count} total={summary.total_rounds} pass_rate={summary.pass_rate}%")
    return 0 if all_passed else 1


def _load_case(case_path: str) -> dict:
    from engine.io import load_json

    return load_json(case_path)


def _build_summary(
    case_name: str,
    exe_path: str,
    total_rounds: int,
    run_dir: Path,
    started_at: str,
    finished_at: str,
    round_results: list,
    *,
    stopped: bool,
) -> StressRunSummary:
    passed = sum(1 for r in round_results if r.status == "passed")
    failed = sum(1 for r in round_results if r.status == "failed")
    frozen = sum(1 for r in round_results if r.status == "frozen")
    skipped = sum(1 for r in round_results if r.status in {"skipped", "stopped"})
    duration = 0.0
    if round_results:
        duration = round(max(r.duration_sec for r in round_results), 3)
    return StressRunSummary(
        case_name=case_name,
        exe_path=exe_path,
        total_rounds=total_rounds,
        started_at=started_at,
        finished_at=finished_at,
        duration_sec=duration,
        passed_count=passed,
        failed_count=failed,
        frozen_count=frozen,
        skipped_count=skipped,
        stopped=stopped,
        rounds=round_results,
        run_dir=str(run_dir),
    )


def _write_stress_summary(summary: StressRunSummary) -> None:
    run_dir = Path(summary.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_name": summary.case_name,
        "exe_path": summary.exe_path,
        "total_rounds": summary.total_rounds,
        "started_at": summary.started_at,
        "finished_at": summary.finished_at,
        "duration_sec": summary.duration_sec,
        "pass_rate": summary.pass_rate,
        "counts": {
            "passed": summary.passed_count,
            "failed": summary.failed_count,
            "frozen": summary.frozen_count,
            "skipped": summary.skipped_count,
        },
        "stopped": summary.stopped,
        "status": _summary_status(summary),
        "rounds": [
            {
                "round_index": r.round_index,
                "status": r.status,
                "reason": r.reason,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "duration_sec": r.duration_sec,
                "round_dir": r.round_dir,
                "report_path": r.report_path,
                "error": r.error,
            }
            for r in summary.rounds
        ],
    }
    dump_json(str(run_dir / SUMMARY_JSON_NAME), payload)
    (run_dir / SUMMARY_HTML_NAME).write_text(
        _render_stress_summary_html(summary, payload),
        encoding="utf-8",
    )


def _summary_status(summary: StressRunSummary) -> str:
    if summary.stopped:
        return "stopped"
    if summary.passed_count == summary.total_rounds:
        return "passed"
    return "failed"


def _render_stress_summary_html(summary: StressRunSummary, payload: dict) -> str:
    status = payload["status"]
    status_text = {"passed": "全部通过", "failed": "存在失败", "stopped": "已停止"}.get(status, status)
    status_color = {"passed": "#167553", "failed": "#b43b3b", "stopped": "#9a5e12"}.get(status, "#65758b")

    rows = []
    for r in summary.rounds:
        status_label = {
            "passed": "通过",
            "failed": "失败",
            "frozen": "卡死",
            "skipped": "跳过",
            "stopped": "停止",
        }.get(r.status, r.status)
        color = {
            "passed": "#167553",
            "failed": "#b43b3b",
            "frozen": "#b43b3b",
            "skipped": "#65758b",
            "stopped": "#9a5e12",
        }.get(r.status, "#65758b")
        report_link = (
            f'<a href="{r.report_path}" target="_blank">报告</a>' if r.report_path else "-"
        )
        reason = (r.reason or "").replace("<", "&lt;").replace(">", "&gt;")
        rows.append(
            "<tr>"
            f"<td>{r.round_index}</td>"
            f"<td><span style='color:{color};font-weight:600'>{status_label}</span></td>"
            f"<td>{reason}</td>"
            f"<td>{r.duration_sec:.1f}s</td>"
            f"<td>{r.started_at}</td>"
            f"<td>{r.finished_at}</td>"
            f"<td>{report_link}</td>"
            "</tr>"
        )

    stats_cells = "".join(
        f"<div style='flex:1;background:#f6f9fd;border:1px solid #d5dfec;border-radius:9px;"
        f"padding:10px 14px;margin:0 6px;text-align:center'>"
        f"<div style='font-size:22px;font-weight:700;color:{color}'>{value}</div>"
        f"<div style='color:#65758b;font-size:12px'>{label}</div></div>"
        for label, value, color in (
            ("总轮次", summary.total_rounds, "#18283d"),
            ("通过", summary.passed_count, "#167553"),
            ("失败", summary.failed_count, "#b43b3b"),
            ("卡死", summary.frozen_count, "#b43b3b"),
            ("通过率", f"{summary.pass_rate}%", "#2e6fd8"),
        )
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>压测汇总 - {summary.case_name}</title>
<style>
  body {{ font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif; margin: 24px; background: #eaf0f8; color: #18283d; }}
  .card {{ background: #ffffff; border: 1px solid #d5dfec; border-radius: 12px; padding: 18px 20px; margin-bottom: 16px; }}
  h1 {{ font-size: 21px; margin: 0 0 4px 0; }}
  .muted {{ color: #65758b; font-size: 13px; }}
  .stats {{ display: flex; margin: 6px -6px 0 -6px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border: 1px solid #d5dfec; padding: 7px 9px; text-align: left; }}
  th {{ background: #f6f9fd; }}
  .status-badge {{ color: {status_color}; font-weight: 700; }}
</style>
</head>
<body>
  <div class="card">
    <h1>压测汇总报告</h1>
    <div class="muted">任务：{summary.case_name} ｜ 软件：{summary.exe_path}</div>
    <div class="muted">开始：{summary.started_at} ｜ 结束：{summary.finished_at} ｜ 状态：<span class="status-badge">{status_text}</span></div>
    <div class="stats">{stats_cells}</div>
  </div>
  <div class="card">
    <h2>轮次明细</h2>
    <table>
      <thead><tr><th>轮次</th><th>状态</th><th>说明</th><th>耗时</th><th>开始</th><th>结束</th><th>报告</th></tr></thead>
      <tbody>{''.join(rows) if rows else '<tr><td colspan="7">无轮次结果</td></tr>'}</tbody>
    </table>
  </div>
</body>
</html>"""


def parse_stress_run_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="stress-run", description="压测模式")
    parser.add_argument("--case", required=True, help="任务 JSON 路径")
    parser.add_argument("--exe", required=True, help="CrealityScan.exe 路径")
    parser.add_argument("--rounds", type=int, required=True, help="执行次数")
    parser.add_argument("--freeze-timeout", type=float, default=180.0, help="卡死判定静默秒数")
    parser.add_argument("--launch-timeout", type=float, default=120.0, help="启动等待秒数")
    parser.add_argument("--popup-timeout", type=float, default=40.0, help="上报弹窗处理秒数")
    parser.add_argument("--stop-file", default=None, help="停止标志文件：存在即视为停止请求（GUI 跨进程优雅停止用）")
    return parser.parse_args(argv)


def parse_stress_round_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="stress-round", description="压测单轮")
    parser.add_argument("--case", required=True, help="任务 JSON 路径")
    parser.add_argument("--round-dir", required=True, help="本轮产物目录")
    return parser.parse_args(argv)


def main_stress_run(argv: list[str]) -> int:
    args = parse_stress_run_args(argv)
    return int(
        run_stress_case(
            args.case,
            args.exe,
            args.rounds,
            freeze_timeout_sec=args.freeze_timeout,
            launch_timeout_sec=args.launch_timeout,
            popup_timeout_sec=args.popup_timeout,
            stop_file=args.stop_file,
        )
    )


def main_stress_round(argv: list[str]) -> int:
    args = parse_stress_round_args(argv)
    return int(run_stress_round(args.case, args.round_dir))
