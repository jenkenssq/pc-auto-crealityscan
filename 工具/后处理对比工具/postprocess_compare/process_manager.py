from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil
from pywinauto import Application
from pywinauto import keyboard, mouse
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PywinautoTimeoutError


_CLOSE_CONFIRM_COORDS = (1098, 578)


@dataclass
class CloseResult:
    forced: bool
    elapsed_sec: float
    confirmation_clicked: bool = False


class ManagedCrealityScan:
    def __init__(self, exe_path: Path, window_title_re: str = ".*CrealityScan.*") -> None:
        self.exe_path = exe_path
        self.window_title_re = window_title_re
        self.app: Optional[Application] = None
        self.process_id: Optional[int] = None

    def ensure_no_conflicting_process(self) -> None:
        target_name = self.exe_path.name.casefold()
        for process in psutil.process_iter(["pid", "name", "exe"]):
            try:
                process_name = str(process.info.get("name") or "").casefold()
                if process_name == target_name:
                    raise RuntimeError(
                        f"检测到正在运行的 {self.exe_path.name}（PID={process.info['pid']}），请先关闭后重试。"
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def start(self, timeout_sec: float = 120.0) -> int:
        self.ensure_no_conflicting_process()
        started = time.time()
        self.app = Application(backend="uia").start(
            f'"{self.exe_path}"',
            work_dir=str(self.exe_path.parent),
        )
        self.process_id = int(self.app.process)

        window = self.app.window(title_re=self.window_title_re)
        # 等待窗口就绪（exists+visible+enabled+ready），期间每 10s 打印一次已等时长，
        # 便于在日志里区分“仍在等待”与“真的卡死”。
        deadline = time.time() + timeout_sec
        last_beat = 0.0
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                self.force_kill()
                raise RuntimeError(
                    f"CrealityScan 启动后 {timeout_sec:.0f} 秒内未出现可操作窗口：{self.exe_path}"
                )
            try:
                window.wait("exists visible enabled ready", timeout=min(5.0, remaining))
                break
            except PywinautoTimeoutError:
                now = time.time()
                if now - last_beat >= 10.0:
                    print(
                        f"[COMPARE] 等待 {self.exe_path.name} 主窗口就绪中... "
                        f"已等待 {now - started:.1f}s / 上限 {timeout_sec:.0f}s"
                    )
                    last_beat = now
                continue

        try:
            window.maximize()
        except (RuntimeError, ElementNotFoundError, PywinautoTimeoutError):
            pass
        window.set_focus()
        print(
            f"[COMPARE] app_started pid={self.process_id} "
            f"elapsed_sec={time.time() - started:.3f} exe={self.exe_path}"
        )
        return self.process_id

    def focus(self) -> None:
        if self.app is None:
            raise RuntimeError("CrealityScan 尚未启动")
        window = self.app.window(title_re=self.window_title_re)
        window.wait("exists visible", timeout=20)
        window.set_focus()

    def is_running(self) -> bool:
        if self.process_id is None:
            return False
        return psutil.pid_exists(self.process_id)

    def close(self, timeout_sec: float = 15.0) -> CloseResult:
        started = time.time()
        if self.app is None or self.process_id is None or not self.is_running():
            return CloseResult(forced=False, elapsed_sec=0.0)

        forced = False
        confirmation_clicked = False
        try:
            self.app.top_window().close()
        except (RuntimeError, PywinautoTimeoutError):
            pass

        if self._wait_exit(min(timeout_sec, 0.5)):
            return CloseResult(
                forced=False,
                elapsed_sec=round(time.time() - started, 3),
                confirmation_clicked=False,
            )

        # 等待关闭确认框弹出并渲染，避免点击过快落空
        time.sleep(0.5)
        confirmation_clicked = self._click_close_confirmation()
        if confirmation_clicked:
            remaining = max(0.0, timeout_sec - (time.time() - started))
            if self._wait_exit(remaining):
                return CloseResult(
                    forced=False,
                    elapsed_sec=round(time.time() - started, 3),
                    confirmation_clicked=True,
                )

        try:
            top_window = self.app.top_window()
            top_window.set_focus()
            keyboard.SendKeys("{ENTER}")
        except (RuntimeError, PywinautoTimeoutError):
            pass

        remaining = max(0.0, timeout_sec - (time.time() - started))
        if not self._wait_exit(remaining):
            forced = True
            self.force_kill()

        return CloseResult(
            forced=forced,
            elapsed_sec=round(time.time() - started, 3),
            confirmation_clicked=confirmation_clicked,
        )

    def _click_close_confirmation(self) -> bool:
        try:
            mouse.click(button="left", coords=_CLOSE_CONFIRM_COORDS)
        except (OSError, RuntimeError) as exc:
            print(f"[COMPARE][WARN] 关闭确认坐标点击失败，将使用 Enter 兜底：{exc}")
            return False

        print(f"[COMPARE] close_confirmation_clicked coords={_CLOSE_CONFIRM_COORDS}")
        return True

    def _wait_exit(self, timeout_sec: float) -> bool:
        if self.process_id is None or not psutil.pid_exists(self.process_id):
            return True
        try:
            psutil.Process(self.process_id).wait(timeout=max(0.0, timeout_sec))
            return True
        except psutil.NoSuchProcess:
            return True
        except psutil.TimeoutExpired:
            return False

    def force_kill(self) -> None:
        if self.app is not None:
            try:
                self.app.kill()
            except (RuntimeError, psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if self.process_id is not None and psutil.pid_exists(self.process_id):
            try:
                process = psutil.Process(self.process_id)
                process.kill()
                process.wait(timeout=5)
            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                pass
