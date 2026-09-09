from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt5 import QtCore  # type: ignore


_RUN_DIR_RE = re.compile(r"\\[JENS\\]\\s+run_dir=(.*)")
_REPORT_RE = re.compile(r"\\[JENS\\]\\s+report=(.*)")
_STRESS_RUN_DIR_RE = re.compile(r"\\[JENS\\]\\s+stress_run_dir=(.*)")
_STRESS_SUMMARY_RE = re.compile(r"\\[JENS\\]\\s+stress_summary=(.*)")


def _decode_process_output(raw: bytes) -> str:
    """Decode UTF-8 output first, then fall back to the Windows ANSI code page."""
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("mbcs", errors="replace")


class AirtestRunResult(QtCore.QObject):
    finished = QtCore.pyqtSignal(bool, str, str, str)  # ok, run_dir, report_path, reason(ok|failed|stopped)
    output = QtCore.pyqtSignal(str)  # incremental text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = QtCore.QProcess(self)
        self._proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)

        self._buf = ""
        self._run_dir = ""
        self._report = ""
        self._stress_run_dir = ""
        self._stress_summary = ""
        self._stop_requested = False

    def start(
        self,
        project_root: Path,
        case_json_path: Path,
        extra_env: Optional[Dict[str, str]] = None,
        argv: Optional[list[str]] = None,
    ) -> bool:
        """
        使用当前程序的“runner 子命令”执行任务。

        argv：自定义 CLI 参数（不含程序本体）。不传时默认为 --run-case <case_json_path>。
        """
        if self._proc.state() != QtCore.QProcess.NotRunning:
            return False

        self._buf = ""
        self._run_dir = ""
        self._report = ""
        self._stress_run_dir = ""
        self._stress_summary = ""
        self._stop_requested = False

        # Airtest CLI --log 的目录必须存在
        logdir = project_root / "artifacts" / "_airtest_cli_log"
        logdir.mkdir(parents=True, exist_ok=True)

        env = QtCore.QProcessEnvironment.systemEnvironment()
        env.insert("JENS_CASE_PATH", str(case_json_path))
        if extra_env:
            for key, value in extra_env.items():
                env.insert(str(key), str(value or ""))
        self._proc.setProcessEnvironment(env)
        self._proc.setWorkingDirectory(str(project_root))

        if getattr(sys, "frozen", False):
            program = str(project_root / "jens_runner_helper.exe")
            args = list(argv) if argv is not None else ["--run-case", str(case_json_path)]
        else:
            program = sys.executable
            args = (
                [str(project_root / "platform_app.py"), *list(argv)]
                if argv is not None
                else [str(project_root / "platform_app.py"), "--run-case", str(case_json_path)]
            )
        self._proc.start(program, args)
        return True

    @property
    def stress_run_dir(self) -> str:
        return self._stress_run_dir

    @property
    def stress_summary(self) -> str:
        return self._stress_summary

    def request_stop(self) -> None:
        """
        优雅停止：只标记停止意图，不终止子进程。

        供压测模式使用——GUI 侧写入 stop-file 后调用本方法；编排子进程
        轮询到标志后会在当前轮安全退出、落汇总再自行结束，`finished` 仍会触发。
        """
        self._stop_requested = True

    def stop(self, grace_ms: int = 2000) -> None:
        """
        请求停止当前运行。

        - 先尝试 `terminate()` 进行温和退出
        - 超过 grace_ms 仍未退出则 `kill()`
        """
        if self._proc.state() == QtCore.QProcess.NotRunning:
            return

        self._stop_requested = True
        self._proc.terminate()

        def _kill_if_needed() -> None:
            if self._proc.state() != QtCore.QProcess.NotRunning:
                self._proc.kill()

        QtCore.QTimer.singleShot(max(0, int(grace_ms)), _kill_if_needed)

    def terminate(self) -> None:
        # 兼容旧接口
        self.stop()

    def _on_output(self) -> None:
        # BAT may force UTF-8 while a regular Windows console may still use mbcs.
        data = _decode_process_output(bytes(self._proc.readAllStandardOutput()))
        if not data:
            return
        self._buf += data
        self.output.emit(data)

        # 解析 run_dir/report（每次增量都尝试更新一次）
        for line in data.splitlines():
            m = _RUN_DIR_RE.search(line)
            if m:
                self._run_dir = m.group(1).strip()
            m = _REPORT_RE.search(line)
            if m:
                self._report = m.group(1).strip()
            m = _STRESS_RUN_DIR_RE.search(line)
            if m:
                self._stress_run_dir = m.group(1).strip()
            m = _STRESS_SUMMARY_RE.search(line)
            if m:
                self._stress_summary = m.group(1).strip()

    def _on_finished(self, exit_code: int, exit_status: QtCore.QProcess.ExitStatus) -> None:
        # 兜底：输出可能被拆分成多段，结束时再从缓存里扫一遍
        for line in self._buf.splitlines():
            m = _RUN_DIR_RE.search(line)
            if m:
                self._run_dir = m.group(1).strip()
            m = _REPORT_RE.search(line)
            if m:
                self._report = m.group(1).strip()
            m = _STRESS_RUN_DIR_RE.search(line)
            if m:
                self._stress_run_dir = m.group(1).strip()
            m = _STRESS_SUMMARY_RE.search(line)
            if m:
                self._stress_summary = m.group(1).strip()
        ok = (exit_status == QtCore.QProcess.NormalExit) and (exit_code == 0)
        if self._stop_requested:
            reason = "stopped"
        else:
            reason = "ok" if ok else "failed"
        self.finished.emit(ok, self._run_dir, self._report, reason)
