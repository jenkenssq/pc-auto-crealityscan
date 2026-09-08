#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CrealityScan 卡住压测脚本（帧数停滞检测）。

流程：打开软件 -> 新建项目(确认) -> 选 蓝色线激光-无标志点模式 -> 循环：
预览(只点不判断) -> 开始扫描 -> 帧数监视(目标帧数)；
达到目标帧数 -> 删除 -> 确定 -> 新建 -> 再预览……
判定卡住：帧数在 stall_timeout 内不再增长 -> stuck_scan（帧号≈0 即"预览已卡"变体）；
仍在增长但超过 max_total_wait -> timeout（不算卡住）。
卡住(bug)时：统计次数 + 截图 + 拉当次软件日志 -> 杀掉 CrealityScan 进程 -> 重新打开(出现日志上报) -> 取消 -> 新建项目+无标志点 -> 继续下一轮。

运行前提：1920x1080 @ 100% 缩放；无标志点/删除/确定 按钮模板放在 pressure_test_freeze_templates/ 目录；
--exe 提供 CrealityScan 可执行文件路径（未提供时从正在运行的进程自动获取，用于卡住后重启）。
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_LOG_DIR = Path.home() / "AppData" / "Local" / "Creality" / "CrealityScan" / "Logs"
DEFAULT_EXE = r"C:\Program Files\CrealityScan\CrealityScan.exe"
TEMPLATE_DIR = ROOT / "pressure_test_freeze_templates"

USER_TEMPLATE_FILES = ("no_marker.png", "delete.png", "confirm.png", "cancel.png")

STEP_TEMPLATES = {
    "preview": (
        ROOT / "steps/crealityscan/preview_scan/v1_0_0/templates/tpl1772635127022.png",
        (-0.41, -0.227),
    ),
    "start": (
        ROOT / "steps/crealityscan/scan_until_frames_then_stop/v1_0_0/templates/tpl1772626136357.png",
        (-0.3, -0.172),
    ),
}

from engine.mouse import move_mouse_smooth  # noqa: E402
from steps.crealityscan.scan_until_frames_then_stop.v1_0_0.impl import (  # noqa: E402
    FRAME_RE,
    _max_frame_in_bytes,
    _parse_log_timestamp,
    _read_live_scan_log,
    _try_pick_scan_log,
)

STUCK_STATUSES = ("stuck_scan", "stuck_unrecovered")


class FrameMonitor:
    """增量读 scan_log，跟踪最大帧号与帧行间隔，用于帧数停滞判定。"""

    def __init__(self, log_root: Path, poll_interval: float = 0.5, read_fn=None):
        self.log_root = Path(log_root)
        self.poll_interval = max(0.05, poll_interval)
        self.read_fn = read_fn or _read_live_scan_log
        self.last_poll_ts = time.time()
        self.reset()

    def reset(self) -> None:
        self.current_fp = _try_pick_scan_log(self.log_root)
        # 从当前日志末尾开始读，只统计本轮新增的帧，避免把上一轮的旧帧重读进来误判已达目标
        if self.current_fp is not None:
            try:
                self.pos = int(self.current_fp.stat().st_size)
            except Exception:
                self.pos = 0
        else:
            self.pos = 0
        self.max_frame = 0
        self.last_progress_ts = time.time()
        self.frame_count_at: List[Tuple[float, int]] = []
        self.interval_samples: List[float] = []

    def poll(self) -> None:
        fp, data, pos, switched = self.read_fn(self.log_root, self.current_fp, self.pos)
        if switched:
            self.current_fp = fp
            self.pos = pos
        now = time.time()
        self.last_poll_ts = now
        if data:
            self._collect_intervals(data)
            cur = _max_frame_in_bytes(data)
            if cur > self.max_frame:
                self.max_frame = cur
                self.last_progress_ts = now
                self.frame_count_at.append((now, cur))

    def _collect_intervals(self, data: bytes) -> None:
        text = data.decode("utf-8", errors="ignore")
        prev: Optional[float] = None
        for raw_line in text.splitlines():
            if not FRAME_RE.search(raw_line.encode("utf-8", errors="ignore")):
                continue
            ts = _parse_log_timestamp(raw_line)
            if ts is None:
                continue
            t = ts.timestamp()
            if prev is not None:
                dt = t - prev
                if 0.0 < dt < 10.0:
                    self.interval_samples.append(dt)
            prev = t

    def frames_per_sec(self) -> float:
        if len(self.frame_count_at) >= 2:
            t0, m0 = self.frame_count_at[0]
            t1, m1 = self.frame_count_at[-1]
            if t1 > t0 and m1 > m0:
                return (m1 - m0) / (t1 - t0)
        return 0.0


class _FakeStallReadFn:
    """模拟"帧数到达 N 后停滞"：N=0 即"预览已卡"变体，用于检测逻辑验证。"""

    def __init__(self, inner, after_frames: int):
        self.inner = inner
        self.after_frames = after_frames
        self.max_seen = 0
        self.triggered = after_frames <= 0

    def __call__(self, log_root, current_fp, pos):
        fp, data, pos, switched = self.inner(log_root, current_fp, pos)
        if self.triggered:
            return fp, b"", pos, switched
        if data:
            self.max_seen = max(self.max_seen, _max_frame_in_bytes(data))
            if self.max_seen >= self.after_frames:
                self.triggered = True
                # 触发的那一批仍返回，让 max_frame 停在该批到达的帧号
        return fp, data, pos, switched


class _FakeSlowReadFn:
    """模拟"仍在增长但极慢"：每次返回一条递增 frame 行，用于 timeout 兜底测试。"""

    def __init__(self):
        self.n = 0

    def __call__(self, log_root, current_fp, pos):
        self.n += 1
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S.000000')}] frame {self.n}\n".encode()
        return (current_fp or Path("fake_scan_log.txt")), line, pos, False


def _monitor_stats(monitor: FrameMonitor) -> Dict[str, float]:
    return {
        "frames_per_sec": round(monitor.frames_per_sec(), 3),
        "stall_detected_sec": round(max(0.0, monitor.last_poll_ts - monitor.last_progress_ts), 3),
    }


def _monitor_frames(
    monitor: FrameMonitor, target_frames: int, stall_timeout: float, max_total_wait: float
) -> Tuple[str, int, Dict[str, float]]:
    deadline = time.time() + max_total_wait
    last_print = 0
    while True:
        monitor.poll()
        if monitor.max_frame >= target_frames:
            return "ok", monitor.max_frame, _monitor_stats(monitor)
        now = time.time()
        if (now - monitor.last_progress_ts) >= stall_timeout:
            return "stuck_scan", monitor.max_frame, _monitor_stats(monitor)
        if now >= deadline:
            return "timeout", monitor.max_frame, _monitor_stats(monitor)
        if monitor.max_frame >= last_print + 100:
            last_print = monitor.max_frame
            print(f"[FREEZE] 帧数 {monitor.max_frame}/{target_frames}")
        time.sleep(monitor.poll_interval)


def _median(xs: List[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _compute_stall_timeout(
    intervals: List[float], min_stall_sec: float, k: float, fixed: Optional[float]
) -> float:
    if fixed is not None and fixed > 0:
        return float(fixed)
    if not intervals:
        return max(min_stall_sec, 15.0)
    return max(min_stall_sec, k * _median(intervals))


def _step_template(name: str, threshold: Optional[float] = None):
    from airtest.core.api import Template

    path, record_pos = STEP_TEMPLATES[name]
    kw: Dict[str, Any] = {"record_pos": record_pos, "resolution": (1920, 1080)}
    if threshold:
        kw["threshold"] = threshold
    return Template(str(path), **kw)


def _user_template(name: str):
    from airtest.core.api import Template

    return Template(str(TEMPLATE_DIR / f"{name}.png"))


def _click_template(name: str, timeout: float, threshold: Optional[float] = None) -> None:
    from airtest.core.api import touch, wait

    pos = wait(_step_template(name, threshold=threshold), timeout=timeout)
    touch(pos)


def _click_user_template(name: str, timeout: float) -> None:
    from airtest.core.api import touch, wait

    pos = wait(_user_template(name), timeout=timeout)
    touch(pos)


def _reset_mouse_hover(safe_x: int = 10, safe_y: int = 10) -> None:
    from airtest.core.api import device, sleep

    try:
        ok = move_mouse_smooth((safe_x, safe_y), duration_sec=0.35, steps=12)
        if not ok:
            dev = device()
            if hasattr(dev, "move"):
                dev.move((safe_x, safe_y))
    except Exception:
        return
    try:
        sleep(0.35)
    except Exception:
        pass


def _activate_scan_window() -> None:
    from engine.window import activate_window

    if not activate_window("CrealityScan"):
        print("[FREEZE] 警告：未找到 CrealityScan 窗口，请确认已打开且未最小化")


def _select_markerless(btn_timeout: float) -> None:
    _activate_scan_window()
    _reset_mouse_hover()
    try:
        _click_user_template("no_marker", btn_timeout)
        print("[FREEZE] 已选择蓝色线激光-无标志点模式")
    except Exception as e:  # noqa: BLE001
        print(f"[FREEZE] 未找到无标志点按钮（可能已处于无标志点模式），继续: {e}")


def _new_project_and_markerless(btn_timeout: float, skip_markerless: bool) -> None:
    from steps.crealityscan.create_project.v1_0_0.impl import run as create_project_run

    _activate_scan_window()
    create_project_run({}, {})
    print("[FREEZE] 已新建项目并确认")
    time.sleep(0.5)
    if not skip_markerless:
        _select_markerless(btn_timeout)


def _find_scan_pid() -> Optional[int]:
    from engine.window import find_window_by_title_contains

    hwnd = find_window_by_title_contains("CrealityScan")
    if not hwnd:
        return None
    try:
        import ctypes

        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:  # noqa: BLE001
        return None


def _scan_exe_path() -> Optional[str]:
    pid = _find_scan_pid()
    if not pid:
        return None
    try:
        import psutil

        return psutil.Process(pid).exe()
    except Exception:  # noqa: BLE001
        return None


def _wait_scan_window(timeout: float) -> bool:
    from engine.window import find_window_by_title_contains

    deadline = time.time() + timeout
    while time.time() < deadline:
        if find_window_by_title_contains("CrealityScan"):
            return True
        time.sleep(1.0)
    return False


def _kill_scan() -> bool:
    pid = _find_scan_pid()
    if not pid:
        return False
    try:
        import psutil

        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[FREEZE] 杀进程失败: {e}")
        return False


def _launch_scan(exe: Optional[str]) -> bool:
    if not exe:
        return False
    try:
        subprocess.Popen([exe])
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[FREEZE] 启动软件失败: {e}")
        return False


def _ensure_scan_open(exe: Optional[str], wait_open_timeout: float) -> bool:
    if _find_scan_pid():
        _activate_scan_window()
        return True
    if _launch_scan(exe):
        return _wait_scan_window(wait_open_timeout)
    return False


def _do_preview(preview_settle_sec: float) -> None:
    _activate_scan_window()
    _reset_mouse_hover()
    _click_template("preview", 10)
    print("[FREEZE] 已点击预览")
    if preview_settle_sec > 0:
        time.sleep(preview_settle_sec)


def _start_scan_and_monitor(
    monitor: FrameMonitor,
    target_frames: int,
    stall_timeout: float,
    max_total_wait: float,
    btn_timeout: float,
) -> Tuple[str, int, Dict[str, float]]:
    _activate_scan_window()
    _reset_mouse_hover()
    monitor.reset()
    _click_template("start", btn_timeout)
    print("[FREEZE] 已点击开始扫描")
    return _monitor_frames(monitor, target_frames, stall_timeout, max_total_wait)


def _delete_and_new(btn_timeout: float) -> None:
    from airtest.core.api import sleep
    from steps.crealityscan.create_scan.v1_0_0.impl import run as create_scan_run

    _activate_scan_window()
    _reset_mouse_hover()
    _click_user_template("delete", btn_timeout)
    print("[FREEZE] 已点击删除")
    sleep(0.5)
    _activate_scan_window()
    _reset_mouse_hover()
    _click_user_template("confirm", btn_timeout)
    print("[FREEZE] 已点击确定")
    sleep(0.5)
    _activate_scan_window()
    _reset_mouse_hover()
    create_scan_run({}, {})
    print("[FREEZE] 已新建")


def _capture_evidence(run_dir: Path, round_no: int, phase: str, frame: int) -> str:
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    name = f"round{round_no}_{phase}_stuck_{frame}.png"
    try:
        from airtest.core.api import snapshot

        snapshot(filename=str(evidence_dir / name))
    except Exception as e:  # noqa: BLE001
        print(f"[FREEZE] 截图失败: {e}")
    return f"evidence/{name}"


def _copy_scan_log(run_dir: Path, round_no: int, phase: str, frame: int, monitor: Optional[FrameMonitor]) -> str:
    """卡住时把当次会话的软件日志（scan_log + 会话目录 *.log/*.txt）复制到 evidence 里用于排查。"""
    fp = monitor.current_fp if monitor is not None else None
    if not fp or not Path(fp).exists():
        return ""
    session = Path(fp).parent
    log_dir = run_dir / "evidence" / f"round{round_no}_{phase}_stuck_{frame}_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    paths = [Path(fp)]
    try:
        paths += sorted(session.glob("*.log")) + sorted(session.glob("*.txt"))
    except Exception:  # noqa: BLE001
        pass
    for p in paths:
        try:
            shutil.copy2(p, log_dir / p.name)
            copied += 1
        except Exception:  # noqa: BLE001
            pass
    return f"evidence/{log_dir.name}" if copied else ""


def _recover(
    run_dir: Path, round_no: int, phase: str, frame: int, monitor: Optional[FrameMonitor], cfg: SimpleNamespace
) -> Tuple[bool, int, str, str]:
    """卡住(bug)：截图+拉当次日志 -> 杀软件 -> 打开软件(出现日志上报) -> 取消 -> 新建项目+无标志点。返回 (是否恢复, 尝试次数, 截图路径, 日志路径)。"""
    evidence = _capture_evidence(run_dir, round_no, phase, frame)
    log_copied = _copy_scan_log(run_dir, round_no, phase, frame, monitor)
    print(f"[FREEZE] 第{round_no}轮 {phase} 卡住(frame={frame}) -> 杀软件 -> 打开软件 -> 日志上报 -> 取消 -> 新建项目 (evidence={evidence} logs={log_copied})")
    from airtest.core.api import sleep

    attempts = 0
    for attempt in range(1, cfg.relaunch_retries + 1):
        attempts = attempt
        try:
            exe = cfg.exe or _scan_exe_path()  # 杀之前先取 exe 路径
            _kill_scan()
            time.sleep(1.0)
            _launch_scan(exe)
            if not _wait_scan_window(cfg.wait_open_timeout):
                print(f"[FREEZE] 重开后未找到窗口 attempt={attempt}/{cfg.relaunch_retries}")
                time.sleep(1.0)
                continue
            _activate_scan_window()
            _reset_mouse_hover()
            _click_user_template("cancel", cfg.btn_timeout)  # 日志上报 -> 取消
            print(f"[FREEZE] 日志上报 -> 取消 attempt={attempt}/{cfg.relaunch_retries}")
            _new_project_and_markerless(cfg.btn_timeout, cfg.skip_markerless)
            return True, attempts, evidence, log_copied
        except Exception as e:  # noqa: BLE001
            print(f"[FREEZE] 恢复(杀软件/打开/取消/新建项目)失败 attempt={attempt}: {e}")
        time.sleep(1.0)
    return False, attempts, evidence, log_copied


def _run_one_round(
    r: int, monitor: FrameMonitor, cfg: SimpleNamespace, stall_timeout: float, run_dir: Path
) -> Dict[str, Any]:
    round_res: Dict[str, Any] = {
        "round": r,
        "status": "",
        "max_frame": 0,
        "stall_frame": 0,
        "stall_detected_sec": 0.0,
        "frames_per_sec": 0.0,
        "duration_sec": 0.0,
        "relaunch_attempts": 0,
        "recovered": None,
        "evidence": "",
        "log_file": "",
        "error": "",
    }
    t0 = time.time()
    try:
        _do_preview(cfg.preview_settle_sec)
        status, max_frame, stats = _start_scan_and_monitor(
            monitor, cfg.target_frames, stall_timeout, cfg.max_total_wait, cfg.btn_timeout
        )
        round_res["max_frame"] = int(max_frame)
        round_res["frames_per_sec"] = stats["frames_per_sec"]
        round_res["stall_detected_sec"] = stats["stall_detected_sec"]

        if status in ("ok", "timeout"):
            try:
                _delete_and_new(cfg.btn_timeout)
                round_res["status"] = status
            except Exception as e:  # noqa: BLE001
                round_res["status"] = "cleanup_failed"
                round_res["error"] = str(e)
                round_res["stall_frame"] = int(max_frame)
                recovered, attempts, evidence, log_file = _recover(run_dir, r, "scan", int(max_frame), monitor, cfg)
                round_res["recovered"] = recovered
                round_res["relaunch_attempts"] = attempts
                round_res["evidence"] = evidence
                round_res["log_file"] = log_file
                if not recovered:
                    round_res["status"] = "stuck_unrecovered"
        else:  # stuck_scan
            round_res["status"] = "stuck_scan"
            round_res["stall_frame"] = int(max_frame)
            recovered, attempts, evidence = _recover(run_dir, r, "scan", int(max_frame), cfg)
            round_res["recovered"] = recovered
            round_res["relaunch_attempts"] = attempts
            round_res["evidence"] = evidence
            if not recovered:
                round_res["status"] = "stuck_unrecovered"
    except Exception as e:  # noqa: BLE001
        round_res["status"] = "error"
        round_res["error"] = str(e)
        round_res["stall_frame"] = int(monitor.max_frame)
        recovered, attempts, evidence, log_file = _recover(run_dir, r, "scan", int(monitor.max_frame), monitor, cfg)
        round_res["recovered"] = recovered
        round_res["relaunch_attempts"] = attempts
        round_res["evidence"] = evidence
        round_res["log_file"] = log_file
        if not recovered:
            round_res["status"] = "stuck_unrecovered"

    round_res["duration_sec"] = round(time.time() - t0, 3)
    return round_res


def _build_cfg(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        target_frames=args.frames,
        preview_settle_sec=args.preview_settle_sec,
        btn_timeout=args.btn_timeout,
        relaunch_retries=args.relaunch_retries,
        wait_open_timeout=args.wait_open_timeout,
        max_total_wait=args.max_total_wait,
        exe=args.exe,
        skip_markerless=args.skip_markerless,
    )


def _write_results(run_dir: Path, cfg: Dict[str, Any], calib: Dict[str, Any], summary: Dict[str, Any], results: List[Dict[str, Any]]) -> Path:
    payload = {
        "tool": "pressure_test_freeze",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config": cfg,
        "calibration": calib,
        "summary": summary,
        "rounds": results,
    }
    out = run_dir / f"pressure_test_freeze_{run_dir.name}.json"
    import json

    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = run_dir / "rounds.csv"
    if results:
        fieldnames = [
            "round", "status", "max_frame", "stall_frame", "stall_detected_sec",
            "frames_per_sec", "duration_sec", "relaunch_attempts", "recovered", "evidence", "log_file", "error",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in results:
                w.writerow({k: row.get(k, "") for k in fieldnames})
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="CrealityScan 卡住压测（帧数停滞检测）")
    ap.add_argument("--rounds", type=int, default=10, help="压测轮数（默认10）")
    ap.add_argument("--frames", type=int, default=500, help="每轮目标帧数（默认500）")
    ap.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="CrealityScan Logs 目录")
    ap.add_argument("--stall-timeout", type=float, default=None, help="帧数停滞判定阈值(秒)；默认自适应")
    ap.add_argument("--min-stall-sec", type=float, default=10.0, help="最小停滞阈值(秒)")
    ap.add_argument("--stall-k", type=float, default=10.0, help="停滞阈值 = k × 中位帧间隔")
    ap.add_argument("--max-total-wait", type=float, default=600.0, help="总等待兜底(秒)，仍增长超时不算卡住")
    ap.add_argument("--poll-interval", type=float, default=0.5, help="轮询间隔(秒)")
    ap.add_argument("--preview-settle-sec", type=float, default=2.0, help="点预览后的稳定等待(秒)")
    ap.add_argument("--btn-timeout", type=float, default=10.0, help="按钮模板匹配超时(秒)")
    ap.add_argument("--relaunch-retries", type=int, default=2, help="卡住后杀进程重启的重试次数")
    ap.add_argument("--wait-open-timeout", type=float, default=60.0, help="重启后等待软件窗口出现超时(秒)")
    ap.add_argument("--exe", default=DEFAULT_EXE, help=f"CrealityScan.exe 路径（用于自动拉起；默认 {DEFAULT_EXE}）")
    ap.add_argument("--calibrate", action="store_true", help="先跑一轮校准（不计入统计）")
    ap.add_argument("--skip-markerless", action="store_true", help="跳过选择无标志点模式")
    ap.add_argument("--stop-on-unrecovered", action="store_true", help="出现未恢复的卡住即停止")
    ap.add_argument("--fake-stall", type=int, default=None, metavar="N", help="测试用：帧数到达 N 后模拟停滞(N=0 即预览即卡)")
    ap.add_argument("--fake-slow", action="store_true", help="测试用：模拟帧数极慢增长，验证 timeout 兜底")
    ap.add_argument("--out-dir", default=None, help="输出目录（默认 artifacts/pressure_test_freeze_<ts>）")
    args = ap.parse_args(argv)

    missing = [f for f in USER_TEMPLATE_FILES if not (TEMPLATE_DIR / f).exists()]
    if missing:
        print(f"[FREEZE] 缺少用户按钮模板：{missing}，请放入 {TEMPLATE_DIR}（1920x1080 截图）")
        return 2

    try:
        from airtest.core.api import auto_setup, connect_device
    except Exception as e:  # noqa: BLE001
        print(f"[FREEZE] 无法导入 Airtest：{e}。请先安装依赖：python -m pip install -r requirements.txt")
        return 2

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.out_dir) if args.out_dir else ROOT / "artifacts" / f"pressure_test_freeze_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    auto_setup(str(ROOT / "jens_runner.air" / "main.py"))
    connect_device("Windows:///")

    read_fn = _read_live_scan_log
    if args.fake_stall is not None:
        read_fn = _FakeStallReadFn(read_fn, args.fake_stall)
    elif args.fake_slow:
        read_fn = _FakeSlowReadFn()

    monitor = FrameMonitor(args.log_dir, args.poll_interval, read_fn)
    cfg = _build_cfg(args)
    stall_timeout = args.stall_timeout or max(args.min_stall_sec, 15.0)

    if not _ensure_scan_open(args.exe, args.wait_open_timeout):
        print("[FREEZE] 找不到 CrealityScan 窗口，且未提供 --exe 无法拉起。请先打开软件，或用 --exe 指定路径")
        return 2
    _new_project_and_markerless(args.btn_timeout, args.skip_markerless)

    calib: Dict[str, Any] = {"calibrated": False, "median_interval_sec": 0.0, "stall_timeout_used": round(stall_timeout, 3)}
    if args.calibrate:
        res = _run_one_round(0, monitor, cfg, stall_timeout, run_dir)
        stall_timeout = _compute_stall_timeout(monitor.interval_samples, args.min_stall_sec, args.stall_k, args.stall_timeout)
        calib = {
            "calibrated": True,
            "median_interval_sec": round(_median(monitor.interval_samples), 6),
            "stall_timeout_used": round(stall_timeout, 3),
            "calib_round_status": res["status"],
        }
        print(f"[FREEZE] 校准完成: {calib}")

    print(
        f"[FREEZE] ============================================================"
    )
    print(f"[FREEZE] 开始压测: 轮数={args.rounds} 目标帧数={args.frames} stall_timeout={stall_timeout:.1f}s")
    print(f"[FREEZE] log_dir={args.log_dir} out_dir={run_dir}")
    print(f"[FREEZE] ============================================================")

    results: List[Dict[str, Any]] = []
    for r in range(1, args.rounds + 1):
        print(f"\n[FREEZE] ---------- 第 {r}/{args.rounds} 轮 开始 ----------")
        round_res = _run_one_round(r, monitor, cfg, stall_timeout, run_dir)
        stall_timeout = _compute_stall_timeout(
            monitor.interval_samples, args.min_stall_sec, args.stall_k, args.stall_timeout
        )
        results.append(round_res)
        print(
            f"[FREEZE] 第 {r} 轮 结束: status={round_res['status']} "
            f"max_frame={round_res['max_frame']} stall_frame={round_res['stall_frame']} "
            f"wall={round_res['duration_sec']}s"
        )
        if round_res["status"] == "stuck_unrecovered" and args.stop_on_unrecovered:
            print("[FREEZE] 出现未恢复的卡住，--stop-on-unrecovered 触发停止")
            break

    total = len(results)
    ok_count = sum(1 for x in results if x["status"] == "ok")
    stuck_count = sum(1 for x in results if x["status"] in STUCK_STATUSES)
    timeout_count = sum(1 for x in results if x["status"] == "timeout")
    error_count = sum(1 for x in results if x["status"] == "error")
    cleanup_failed_count = sum(1 for x in results if x["status"] == "cleanup_failed")
    unrecovered = sum(1 for x in results if x["status"] == "stuck_unrecovered")
    frames_before_stall = [int(x["stall_frame"] or 0) for x in results if x["status"] in STUCK_STATUSES]
    ok_fps = [float(x["frames_per_sec"]) for x in results if x["status"] == "ok" and x["frames_per_sec"] > 0]
    summary = {
        "total_rounds": total,
        "ok_count": ok_count,
        "stuck_scan_count": stuck_count,
        "timeout_count": timeout_count,
        "error_count": error_count,
        "cleanup_failed_count": cleanup_failed_count,
        "unrecovered_count": unrecovered,
        "freeze_probability": round(stuck_count / total, 4) if total else 0.0,
        "avg_frames_per_sec": round(sum(ok_fps) / len(ok_fps), 3) if ok_fps else 0.0,
        "frames_before_stall": frames_before_stall,
    }

    out = _write_results(
        run_dir,
        {
            "rounds": args.rounds,
            "target_frames": args.frames,
            "stall_timeout_sec": round(stall_timeout, 3),
            "min_stall_sec": args.min_stall_sec,
            "stall_k": args.stall_k,
            "max_total_wait_sec": args.max_total_wait,
            "log_dir": args.log_dir,
        },
        calib,
        summary,
        results,
    )
    print(f"\n[FREEZE] ============================================================")
    print(f"[FREEZE] 压测结束: 完成 {summary['total_rounds']} 轮, ok={ok_count}, "
          f"stuck={stuck_count}, timeout={timeout_count}, "
          f"error={error_count}, cleanup_failed={cleanup_failed_count}, unrecovered={unrecovered}")
    print(f"[FREEZE] 卡住概率 = {summary['freeze_probability']}  frames_before_stall={frames_before_stall}")
    if error_count:
        for x in results:
            if x["status"] == "error":
                print(f"[FREEZE] error 轮: 第{x['round']}轮  {x.get('error')}")
    if cleanup_failed_count:
        for x in results:
            if x["status"] == "cleanup_failed":
                print(f"[FREEZE] cleanup_failed 轮: 第{x['round']}轮  {x.get('error')}")
    print(f"[FREEZE] 结果已保存: {run_dir}")
    print(f"[FREEZE] ============================================================")
    return 0 if unrecovered == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
