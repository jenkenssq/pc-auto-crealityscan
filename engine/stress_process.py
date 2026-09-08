from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import psutil

from jens_platform.tools.postprocess_compare.process_manager import ManagedCrealityScan


# 日志上报弹窗“取消”按钮模板（裁剪自用户提供的 软件意外退出 弹窗截图）。
# 注意：压测模式遇到崩溃上报弹窗一律点【取消】（不发送崩溃报告）。
CANCEL_BTN_TEMPLATE_REL = Path("jens_platform") / "stress" / "templates" / "cancel_btn.png"
CRASH_DIALOG_TEXT = "软件意外退出"


def _kill_process_tree(pid: int) -> None:
    """强制结束进程树（先子进程后父进程），并等待退出。"""
    if not pid or not psutil.pid_exists(pid):
        return
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for child in children:
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    try:
        parent.kill()
        parent.wait(timeout=5)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
        pass
    for child in children:
        try:
            child.wait(timeout=2)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            pass


def _find_pids_by_exe_name(exe_name: str) -> list[int]:
    target = Path(exe_name).name.casefold()
    pids: list[int] = []
    for process in psutil.process_iter(["pid", "name"]):
        try:
            name = str(process.info.get("name") or "").casefold()
            if name == target:
                pids.append(int(process.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


class StressProcessManager:
    """压测模式下 CrealityScan 进程生命周期管理 + 崩溃上报弹窗处理。

    与后处理对比工具共用 ManagedCrealityScan，但压测模式允许：
      - 首轮复用已在运行的实例（不强制无冲突启动）；
      - 失败/卡死轮次后强制杀进程并重开。
    """

    def __init__(self, exe_path: Path, window_title_re: str = ".*CrealityScan.*") -> None:
        self.exe_path = Path(exe_path)
        self.window_title_re = window_title_re
        self._managed: Optional[ManagedCrealityScan] = None
        self._adopted_pid: Optional[int] = None

    # ---- 查询 ----
    def _exe_name(self) -> str:
        return self.exe_path.name

    def find_running_pid(self) -> Optional[int]:
        pids = _find_pids_by_exe_name(self._exe_name())
        return pids[0] if pids else None

    def is_tracked_running(self) -> bool:
        if self._managed is not None and self._managed.is_running():
            return True
        if self._adopted_pid is not None and psutil.pid_exists(self._adopted_pid):
            return True
        return False

    # ---- 启动 ----
    def ensure_running(self, launch_timeout_sec: float = 120.0) -> int:
        """确保存在一个可用的 CrealityScan 实例。

        优先复用已跟踪/已存在的实例；否则从 exe 启动新实例。
        """
        if self.is_tracked_running():
            return self._tracked_pid()
        existing = self.find_running_pid()
        if existing is not None:
            self._adopted_pid = existing
            return existing
        # 启动新实例（已确认无同名进程，可安全通过 ensure_no_conflicting_process）
        self._managed = ManagedCrealityScan(self.exe_path, self.window_title_re)
        pid = self._managed.start(timeout_sec=launch_timeout_sec)
        self._adopted_pid = None
        return pid

    def _tracked_pid(self) -> int:
        if self._managed is not None and self._managed.is_running():
            return int(self._managed.process_id)
        if self._adopted_pid is not None and psutil.pid_exists(self._adopted_pid):
            return int(self._adopted_pid)
        raise RuntimeError("压测模式：未跟踪到可用的 CrealityScan 进程")

    # ---- 杀进程 ----
    def kill(self, wait_sec: float = 5.0) -> list[int]:
        """强制结束所有同名 CrealityScan 进程。"""
        if self._managed is not None:
            try:
                self._managed.force_kill()
            except Exception:
                pass
            self._managed = None
        killed: list[int] = []
        for pid in _find_pids_by_exe_name(self._exe_name()):
            try:
                _kill_process_tree(pid)
                killed.append(pid)
            except Exception:
                continue
        self._adopted_pid = None
        # 等待全部退出
        deadline = time.time() + wait_sec
        while time.time() < deadline:
            if not _find_pids_by_exe_name(self._exe_name()):
                break
            time.sleep(0.3)
        return killed

    # ---- 恢复：杀 + 重开 + 处理弹窗 ----
    def recover(
        self,
        *,
        launch_timeout_sec: float = 120.0,
        popup_timeout_sec: float = 40.0,
        evidence_dir: Optional[Path] = None,
    ) -> int:
        """卡死/失败后的标准恢复流程：强杀 -> 重开 -> 处理日志上报弹窗。"""
        killed = self.kill()
        print(f"[STRESS] killed CrealityScan processes={killed}")
        time.sleep(1.0)
        pid = self.ensure_running(launch_timeout_sec=launch_timeout_sec)
        print(f"[STRESS] relaunched CrealityScan pid={pid}")
        self.handle_crash_report_popup(timeout_sec=popup_timeout_sec, evidence_dir=evidence_dir)
        return pid

    # ---- 日志上报弹窗处理 ----
    def handle_crash_report_popup(self, timeout_sec: float = 40.0, evidence_dir: Optional[Path] = None) -> bool:
        """处理“软件意外退出，此报告自动发送给 CrealityScan”弹窗，点击“取消”。

        注意：压测模式不发送崩溃报告，因此弹窗一律点【取消】。
        策略（按可靠性顺序）：
          1. pywinauto：按窗口文本定位弹窗，点击“取消”按钮；
          2. Airtest 模板匹配 cancel_btn.png 点击；
          3. 都失败则截图留证并返回 False（不阻塞后续轮次）。
        """
        pid = self._tracked_pid()
        if self._click_cancel_pywinauto(pid, timeout_sec=timeout_sec):
            return True
        if self._click_cancel_airtest(timeout_sec=timeout_sec):
            return True
        self._snapshot_evidence(evidence_dir)
        print("[STRESS][WARN] 未检测到日志上报弹窗，或无法自动点击“取消”（已截图留证）")
        return False

    def _click_cancel_pywinauto(self, pid: int, timeout_sec: float) -> bool:
        try:
            from pywinauto import Application
        except Exception:
            return False
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                app = Application(backend="uia").connect(process=pid, timeout=3)
            except Exception:
                time.sleep(0.5)
                continue
            dialog = self._find_crash_dialog(app)
            if dialog is not None:
                for button_text in ("取消", "Cancel"):
                    try:
                        button = dialog.child_window(title=button_text, control_type="Button")
                        if button.exists(timeout=1):
                            button.click_input()
                            print(f"[STRESS] popup_cancel_clicked button={button_text!r}")
                            return True
                    except Exception:
                        continue
            time.sleep(0.5)
        return False

    def _find_crash_dialog(self, app):
        try:
            windows = app.windows()
        except Exception:
            return None
        for handle in windows:
            try:
                ctrl = app.window(handle=handle)
                if not ctrl.exists(timeout=0.2):
                    continue
                if CRASH_DIALOG_TEXT in (ctrl.window_text() or ""):
                    return ctrl
            except Exception:
                continue
        # 兜底：在进程内任一窗口的控件树里查找该文案
        for handle in windows:
            try:
                ctrl = app.window(handle=handle)
                texts = ctrl.descendants(control_type="Text")
                for text_ctrl in texts:
                    if CRASH_DIALOG_TEXT in (text_ctrl.window_text() or ""):
                        return ctrl
            except Exception:
                continue
        return None

    def _click_cancel_airtest(self, timeout_sec: float) -> bool:
        try:
            from airtest.core.api import Template, connect_device, exists, touch, auto_setup
        except Exception:
            return False
        template_path = self._cancel_template_path()
        if not template_path:
            return False
        try:
            auto_setup(__file__, logdir=None)
            connect_device("Windows:///")
        except Exception:
            return False
        tpl = Template(str(template_path), threshold=0.8)
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                pos = exists(tpl)
                if pos is not None:
                    touch(tpl)
                    print("[STRESS] popup_cancel_clicked via airtest template")
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def _cancel_template_path(self) -> Optional[Path]:
        # 源码态/安装态统一从资源根查找
        try:
            from jens_runtime import iter_existing_resource_roots

            for root in iter_existing_resource_roots():
                candidate = root / CANCEL_BTN_TEMPLATE_REL
                if candidate.is_file():
                    return candidate
        except Exception:
            pass
        local = Path(__file__).resolve().parents[1] / CANCEL_BTN_TEMPLATE_REL
        return local if local.is_file() else None

    def _snapshot_evidence(self, evidence_dir: Optional[Path]) -> None:
        if evidence_dir is None:
            return
        try:
            from airtest.core.api import auto_setup, connect_device, snapshot

            evidence_dir.mkdir(parents=True, exist_ok=True)
            auto_setup(__file__, logdir=None)
            connect_device("Windows:///")
            out = str(evidence_dir / f"popup_evidence_{int(time.time())}.png")
            snapshot(filename=out)
            print(f"[STRESS] popup_evidence_saved={out}")
        except Exception as exc:
            print(f"[STRESS][WARN] 截图留证失败：{exc}")
