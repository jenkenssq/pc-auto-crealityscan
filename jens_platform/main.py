from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore

from engine.defaults import DEFAULT_KEYWORDS
from engine.logs import extract_device_info
from jens_platform.case_store import (
    CaseModel,
    CaseStep,
    load_case_json,
    load_task_json,
    save_case_json,
    save_task_json,
    save_temp_case_json,
)
from jens_platform.dialogs import (
    ConfirmRunDialog,
    EmailSettingsDialog,
    PointDistanceDialog,
    PresetPickerDialog,
    StressRunDialog,
    TargetFramesDialog,
    SleepSecondsDialog,
    RunFinishedDialog,
    TaskCreationWizardDialog,
    TaskEditDialog,
    TaskManagerDialog,
    show_error,
)
from jens_platform.notifications import NotificationDispatcher, TaskRunSummary, load_task_run_summary
from jens_platform.task_generator import (
    TaskGenerationOption,
    build_task_model,
    list_task_generation_options,
)
from jens_platform.runner import AirtestRunResult
from jens_platform.step_registry import StepMeta, scan_steps
from jens_platform.tool_pages import (
    CalibrationScorePage,
    FirmwareUpgradePage,
    PostprocessComparePage,
    ToolErrorPage,
    ToolPageLoadError,
)
from jens_platform.task_library_page import TaskLibraryPage
from jens_platform.ui_theme import apply_app_theme
from jens_runtime import get_app_root


_CONFIGURE_SCAN_PARAMS_STEP_ID = "crealityscan.configure_scan_params_otter_lite"
_SET_POINT_DISTANCE_STEP_ID = "crealityscan.set_point_distance"
_SLEEP_STEP_ID = "common.sleep"
_SLIDE_RAIL_SWITCH_POSITION_STEP_ID = "slide_rail.switch_position"
_SCAN_UNTIL_FRAMES_STEP_ID = "crealityscan.scan_until_frames_then_stop"
_SCAN_UNTIL_FRAMES_FRAME_POINTS_STEP_ID = "crealityscan.scan_until_frames_reach_target_frame_points"
_TARGET_FRAMES_STEP_IDS = {
    _SCAN_UNTIL_FRAMES_STEP_ID,
}


def _resolve_app_icon(project_root: Path) -> Optional[Path]:
    candidates = [
        project_root / "build_assets" / "jens_app.ico",
        project_root / "_internal" / "build_assets" / "jens_app.ico",
        project_root / "jens_app.ico",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _is_target_frames_step(step_id: str) -> bool:
    return step_id in _TARGET_FRAMES_STEP_IDS


def _target_frames_step_name(step_id: str, frames: int) -> str:
    if step_id == _SCAN_UNTIL_FRAMES_FRAME_POINTS_STEP_ID:
        return f"扫描至{frames}帧达标并停止（框架点）"
    return f"扫描至{frames}帧后完成"


def _preset_step_name(step_id: str, preset_name: str) -> str:
    if step_id == _SLIDE_RAIL_SWITCH_POSITION_STEP_ID:
        return f"移动滑轨位置至{preset_name}"
    return f"扫描参数：{preset_name}"


def _candidate_crealityscan_log_dirs() -> list[Path]:
    candidates: list[Path] = []
    override = str(os.environ.get("JENS_CREALITYSCAN_LOG_DIR") or "").strip()
    if override:
        candidates.append(Path(override))

    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        local_root = Path(local_app_data)
        candidates.extend(
            [
                local_root / "Creality" / "CrealityScan" / "Logs",
                local_root / "CrealityScan" / "Logs",
            ]
        )

    home_local_root = Path.home() / "AppData" / "Local"
    candidates.extend(
        [
            home_local_root / "Creality" / "CrealityScan" / "Logs",
            home_local_root / "CrealityScan" / "Logs",
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _has_scan_log_files(log_root: Path) -> bool:
    if not log_root.exists() or not log_root.is_dir():
        return False
    try:
        if any(log_root.glob("scan_log_*.txt")):
            return True
    except Exception:
        return False
    try:
        for child in log_root.iterdir():
            if not child.is_dir():
                continue
            try:
                if any(child.glob("scan_log_*.txt")):
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _auto_detect_crealityscan_log_dir() -> str:
    candidates = _candidate_crealityscan_log_dirs()
    for candidate in candidates:
        if _has_scan_log_files(candidate):
            return str(candidate)
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return str(candidate)
    if candidates:
        return str(candidates[0])
    return ""

class StepListItem(QtWidgets.QListWidgetItem):
    def __init__(self, meta: StepMeta):
        super().__init__(meta.name)
        self.meta = meta
        # 列表里只展示中文名；技术信息放到 tooltip（便于排查/搜索）
        self.setToolTip(f"{meta.step_id}@{meta.version}")


class SelectedStepItem(QtWidgets.QListWidgetItem):
    def __init__(self, step: CaseStep):
        super().__init__(step.name or step.step_id)
        self.step = step
        self.setToolTip(f"{step.step_id}@{step.version}")

    def refresh_text(self) -> None:
        self.setText(self.step.name or self.step.step_id)
        self.setToolTip(f"{self.step.step_id}@{self.step.version}")


class TaskListWidget(QtWidgets.QListWidget):
    def __init__(self, on_reordered: Callable[[], None], parent=None):
        super().__init__(parent)
        self._on_reordered = on_reordered

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[name-defined]
        super().dropEvent(event)
        try:
            self._on_reordered()
        except Exception:
            pass

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[name-defined]
        bar = self.verticalScrollBar()
        if bar is not None and bar.isVisible():
            delta = event.angleDelta().y()
            if delta:
                step = max(24, bar.singleStep())
                bar.setValue(bar.value() - (step if delta > 0 else -step))
                event.accept()
                return
        super().wheelEvent(event)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, project_root: Path):
        super().__init__()
        self.project_root = project_root
        icon_path = _resolve_app_icon(project_root)
        if icon_path:
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))
        self.setWindowTitle("Jens 自动化测试平台")
        self._configure_initial_window_geometry()

        self.setStatusBar(QtWidgets.QStatusBar(self))
        self.statusBar().showMessage("就绪")

        self._last_run_dir: str = ""
        self._last_report: str = ""

        self._current_task_path: Optional[Path] = None
        self._task_queue: list[Path] = []
        self._task_queue_total: int = 0
        self._task_queue_index: int = 0
        self._task_run_start_step_index: int = 1
        self._running_task: Optional[Path] = None
        self._batch_mode: bool = False
        self._queue_started_at: str = ""
        self._queue_summaries: list[TaskRunSummary] = []
        self._device_info: dict[str, str] = {}
        self._slide_rail_service_proc: Optional[subprocess.Popen] = None
        self._pages: dict[str, QtWidgets.QWidget] = {}
        self._page_nav_buttons: dict[str, QtWidgets.QPushButton] = {}
        self._tool_busy_key: Optional[str] = None

        self.model = CaseModel(
            case_id="case_001",
            name="新用例",
            app_window_title_contains="CrealityScan",
            app_log_dir=_auto_detect_crealityscan_log_dir(),
            keywords=list(DEFAULT_KEYWORDS),
            steps=[],
        )
        self._current_step_item: Optional[SelectedStepItem] = None
        self._all_step_metas: list[StepMeta] = []

        self._runner = AirtestRunResult(self)
        self._runner.output.connect(self._append_output)
        self._runner.finished.connect(self._on_run_finished)
        self._stop_pending = False
        self._stress_mode = False
        self._stress_task: Optional[Path] = None
        self._stress_exe = ""
        self._stress_rounds = 0
        self._stress_stop_file: Optional[Path] = None
        self._notification_dispatcher = NotificationDispatcher(project_root, self)
        self._notification_dispatcher.status.connect(self._on_notification_status)

        self._apply_style()
        self._build_ui()
        self._load_step_registry()
        self._refresh_selected_steps()
        self._refresh_device_connection()
        QtCore.QTimer.singleShot(0, self._ensure_slide_rail_service_started)

    def _configure_initial_window_geometry(self) -> None:
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            self.resize(1600, 920)
            self.setMinimumSize(1280, 820)
            return

        available = screen.availableGeometry()
        target_width = min(max(1520, int(available.width() * 0.84)), available.width())
        target_height = min(max(920, int(available.height() * 0.88)), available.height())
        min_width = min(1280, available.width())
        min_height = min(820, available.height())

        self.resize(target_width, target_height)
        self.setMinimumSize(min_width, min_height)

        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def ensure_notification_email(self) -> bool:
        current_email = self._notification_dispatcher.settings.recipient_email.strip()
        if current_email:
            return True
        dlg = EmailSettingsDialog(
            current_email=current_email,
            availability_checker=self._notification_availability_tuple,
            parent=self,
            startup_mode=True,
            current_label=self._notification_dispatcher.settings.label,
        )
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return False
        email = dlg.email().strip()
        self._notification_dispatcher.set_recipient_email(email)
        self._notification_dispatcher.set_label(dlg.label())
        if email:
            self.statusBar().showMessage("通知邮箱已保存", 3000)
        else:
            self.statusBar().showMessage("未填写通知邮箱，已跳过邮件通知", 4000)
        return True

    def _notification_availability_tuple(self) -> tuple[bool, str]:
        status = self._notification_dispatcher.refresh_availability()
        return status.enabled, status.reason

    def _open_email_settings(self) -> None:
        dlg = EmailSettingsDialog(
            current_email=self._notification_dispatcher.settings.recipient_email,
            availability_checker=self._notification_availability_tuple,
            parent=self,
            startup_mode=False,
            current_label=self._notification_dispatcher.settings.label,
        )
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        email = dlg.email().strip()
        self._notification_dispatcher.set_recipient_email(email)
        self._notification_dispatcher.set_label(dlg.label())
        if email:
            self.statusBar().showMessage("邮件设置已更新", 3000)
        else:
            self.statusBar().showMessage("邮件通知已禁用", 4000)

    def _open_slide_rail_console(self) -> None:
        app_path = self.project_root / "slide_rail_app.py"
        if not app_path.exists():
            show_error(self, "无法打开滑轨控制台", f"未找到启动文件：{app_path}")
            return
        try:
            if getattr(sys, "frozen", False):
                # 打包态无独立 python：经 --slide-rail-ui-runner 在 exe 进程内跑滑轨控制台
                cmd = [sys.executable, "--slide-rail-ui-runner"]
            else:
                cmd = [sys.executable, str(app_path)]
            subprocess.Popen(cmd, cwd=str(self.project_root), close_fds=True)
            self.statusBar().showMessage("滑轨控制台已打开", 3000)
        except Exception as e:
            show_error(self, "无法打开滑轨控制台", str(e))

    def _is_slide_rail_service_available(self, host: str = "127.0.0.1", port: int = 5000) -> bool:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return True
        except OSError:
            return False

    def _ensure_slide_rail_service_started(self) -> None:
        if self._is_slide_rail_service_available():
            self.statusBar().showMessage("滑轨服务已可用", 3000)
            self._append_output("[JENS][slide_rail] motion_service already available at 127.0.0.1:5000\n")
            return

        service_path = self.project_root / "滑轨" / "motion_service.py"
        if not service_path.exists():
            self.statusBar().showMessage("未找到滑轨服务文件，已跳过自动启动", 5000)
            self._append_output(f"[JENS][slide_rail] motion_service not found: {service_path}\n")
            return

        try:
            self._append_output(f"[JENS][slide_rail] starting motion_service: {service_path}\n")
            if getattr(sys, "frozen", False):
                # 打包态无独立 python：经 --slide-rail-service-runner 在 exe 进程内
                # 跑 socket 服务（阻断级联的关键：不再回落成新的平台 GUI）
                cmd = [sys.executable, "--slide-rail-service-runner"]
            else:
                cmd = [sys.executable, str(service_path)]
            self._slide_rail_service_proc = subprocess.Popen(
                cmd,
                cwd=str(service_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            QtCore.QTimer.singleShot(1000, self._report_slide_rail_service_status)
        except Exception as e:
            self._append_output(f"[JENS][slide_rail] failed to start motion_service: {e}\n")
            show_error(self, "无法启动滑轨服务", str(e))

    def _report_slide_rail_service_status(self) -> None:
        if self._is_slide_rail_service_available():
            self.statusBar().showMessage("滑轨服务已自动启动", 4000)
            self._append_output("[JENS][slide_rail] motion_service started at 127.0.0.1:5000\n")
            return
        self.statusBar().showMessage("滑轨服务启动中或启动失败，请打开滑轨控制台检查", 6000)
        self._append_output("[JENS][slide_rail] motion_service is not reachable at 127.0.0.1:5000\n")

    def _connect_slide_rail_controller(self) -> None:
        if not self._is_slide_rail_service_available():
            self._append_output("[JENS][slide_rail] motion_service not reachable, try starting it first\n")
            self._ensure_slide_rail_service_started()
            QtCore.QTimer.singleShot(1200, self._connect_slide_rail_controller)
            return

        slide_rail_dir = self.project_root / "滑轨"
        module_dir = str(slide_rail_dir)
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)

        try:
            from motion_client import create_motion_client  # type: ignore

            self._append_output("[JENS][slide_rail] connecting motion_service client\n")
            client = create_motion_client(use_mock=False, host="127.0.0.1", port=5000)
            if not client.connect():
                last_error = getattr(client, "last_error", "") or "connect service failed"
                self._append_output(f"[JENS][slide_rail] service client connect failed: {last_error}\n")
                self.statusBar().showMessage("滑轨服务连接失败", 5000)
                return
            try:
                self._append_output("[JENS][slide_rail] connecting controller ip=192.168.0.11 dll=zauxdll.dll\n")
                result = client.connect_controller(dll_path="zauxdll.dll", ip="192.168.0.11")
                self._append_output(
                    "[JENS][slide_rail] controller connect result="
                    + json.dumps(result, ensure_ascii=False)
                    + "\n"
                )
                if isinstance(result, dict) and result.get("status") == "success":
                    self.statusBar().showMessage("滑轨控制器已连接", 4000)
                else:
                    self.statusBar().showMessage("滑轨控制器连接失败", 6000)
            finally:
                client.disconnect()
        except Exception as e:
            self._append_output(f"[JENS][slide_rail] controller connect exception: {e}\n")
            show_error(self, "无法连接滑轨控制器", str(e))

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        for page in self._pages.values():
            prepare_close = getattr(page, "prepare_close", None)
            if callable(prepare_close) and not prepare_close():
                event.ignore()
                return
        proc = self._slide_rail_service_proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        super().closeEvent(event)

    def _on_notification_status(self, level: str, message: str) -> None:
        text = (message or "").strip()
        if not text:
            return
        self._append_output(f"\n[NOTIFY] {text}\n")
        timeout = 6000 if level == "success" else 10000
        self.statusBar().showMessage(text, timeout)

    def _set_device_info_display(self, info: dict[str, str], status_text: str) -> None:
        self._device_info = dict(info or {})
        self.lbl_device_status.setText(status_text)
        self.lbl_device_status.setObjectName("statusGood" if self._device_info else "statusWarn")
        self.lbl_device_status.style().unpolish(self.lbl_device_status)
        self.lbl_device_status.style().polish(self.lbl_device_status)
        self.lbl_device_name.setText(self._device_info.get("camera_name") or "-")
        self.lbl_device_sn.setText(self._device_info.get("camera_serial_number") or "-")
        self.lbl_device_connection.setText(self._device_info.get("camera_connection_type") or "-")
        self.lbl_device_firmware.setText(self._device_info.get("camera_firmware_version") or "-")

    def _refresh_device_connection(self) -> None:
        log_dir = self.edit_log_dir.text().strip()
        if not log_dir:
            detected = _auto_detect_crealityscan_log_dir()
            if detected:
                log_dir = detected
                self.edit_log_dir.setText(log_dir)

        self.model.app_log_dir = log_dir
        if not log_dir:
            self._set_device_info_display({}, "未配置日志目录")
            self.statusBar().showMessage("未配置日志目录，无法刷新设备连接", 4000)
            return

        log_path = Path(log_dir)
        if not log_path.exists():
            detected = _auto_detect_crealityscan_log_dir()
            if detected and detected != log_dir and Path(detected).exists():
                log_dir = detected
                log_path = Path(log_dir)
                self.edit_log_dir.setText(log_dir)
                self.model.app_log_dir = log_dir

        if not log_path.exists():
            self._set_device_info_display({}, "日志目录不存在")
            self.statusBar().showMessage("日志目录不存在，无法刷新设备连接", 4000)
            return

        info = extract_device_info(log_dir)
        if info:
            self._set_device_info_display(info, "已识别到最近一次设备连接")
            self._append_output(
                "[UI] device_info "
                f"name={info.get('camera_name','-')} "
                f"sn={info.get('camera_serial_number','-')} "
                f"connection={info.get('camera_connection_type','-')} "
                f"firmware={info.get('camera_firmware_version','-')}\n"
            )
            self.statusBar().showMessage("设备连接信息已刷新", 3000)
            return

        self._set_device_info_display({}, "未识别到设备信息")
        self.statusBar().showMessage("未识别到设备信息", 4000)

    def _find_step_meta(self, step_id: str, version: str) -> Optional[StepMeta]:
        for m in self._all_step_metas:
            if m.step_id == step_id and m.version == version:
                return m
        return None

    def _presets_path_for_step(self, step_id: str, version: str) -> Optional[Path]:
        meta = self._find_step_meta(step_id, version)
        if not meta:
            return None
        # 约定：presets.json 与 step.json 同目录（即 version 目录下）
        return Path(meta.source_path).with_name("presets.json")

    def _is_preset_step(self, step_id: str, version: str) -> bool:
        fp = self._presets_path_for_step(step_id, version)
        return bool(fp and fp.exists())

    def _load_presets_for_step(self, step_id: str, version: str) -> list[tuple[str, str]]:
        """返回 [(中文名称, key)]，用于 UI 选择 preset。"""
        fp = self._presets_path_for_step(step_id, version)
        if not fp or not fp.exists():
            return []
        raw = json.loads(fp.read_text(encoding="utf-8"))
        presets = raw.get("presets") if isinstance(raw, dict) else None
        if not isinstance(presets, list):
            return []
        out: list[tuple[str, str]] = []
        for p in presets:
            if not isinstance(p, dict):
                continue
            name_cn = str(p.get("name") or "").strip()
            key = str(p.get("key") or "").strip()
            if name_cn and key:
                out.append((name_cn, key))
        return out

    def _apply_style(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app:
            apply_app_theme(app)

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        shell = QtWidgets.QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("appSidebar")
        sidebar.setFixedWidth(208)
        side = QtWidgets.QVBoxLayout(sidebar)
        side.setContentsMargins(16, 20, 16, 16)
        side.setSpacing(7)
        brand = QtWidgets.QLabel("Jens")
        brand.setObjectName("brandTitle")
        side.addWidget(brand)
        brand_copy = QtWidgets.QLabel("扫描自动化测试平台")
        brand_copy.setObjectName("brandSubtitle")
        side.addWidget(brand_copy)
        side.addSpacing(20)
        nav_label = QtWidgets.QLabel("工作区")
        nav_label.setObjectName("sidebarLabel")
        side.addWidget(nav_label)

        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_group.setExclusive(True)

        def add_nav(
            text: str,
            handler,
            checked: bool = False,
            page_key: Optional[str] = None,
        ) -> QtWidgets.QPushButton:
            button = QtWidgets.QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setChecked(checked)

            def invoke() -> None:
                handler()
                if page_key is None:
                    button.setChecked(False)
                    current_button = self._page_nav_buttons.get(self._current_page_key())
                    if current_button is not None:
                        current_button.setChecked(True)

            button.clicked.connect(invoke)
            self.nav_group.addButton(button)
            side.addWidget(button)
            if page_key is not None:
                self._page_nav_buttons[page_key] = button
            return button

        self.nav_workspace = add_nav(
            "运行工作台",
            lambda: self._show_page("workspace"),
            True,
            "workspace",
        )
        self.nav_task_library = add_nav("任务库", lambda: self._show_page("task_library"), page_key="task_library")
        side.addSpacing(14)
        tools_label = QtWidgets.QLabel("工具")
        tools_label.setObjectName("sidebarLabel")
        side.addWidget(tools_label)
        self.nav_firmware_upgrade = add_nav(
            "固件升级",
            lambda: self._show_page("firmware_upgrade"),
            page_key="firmware_upgrade",
        )
        self.nav_postprocess_compare = add_nav(
            "后处理对比",
            lambda: self._show_page("postprocess_compare"),
            page_key="postprocess_compare",
        )
        self.nav_calibration_score = add_nav(
            "标定分数查看",
            lambda: self._show_page("calibration_score"),
            page_key="calibration_score",
        )
        self.nav_slide_rail = add_nav("滑轨控制", self._open_slide_rail_console)
        self.nav_email = add_nav("邮件通知", self._open_email_settings)
        side.addStretch(1)
        sidebar_status = QtWidgets.QFrame()
        sidebar_status.setObjectName("sidebarStatus")
        sidebar_status_layout = QtWidgets.QVBoxLayout(sidebar_status)
        sidebar_status_layout.setContentsMargins(11, 10, 11, 10)
        sidebar_status_layout.setSpacing(3)
        self.sidebar_status_title = QtWidgets.QLabel("快捷停止 · F4")
        self.sidebar_status_title.setObjectName("sidebarStatusTitle")
        sidebar_status_layout.addWidget(self.sidebar_status_title)
        self.sidebar_status_copy = QtWidgets.QLabel("运行时可随时请求停止")
        self.sidebar_status_copy.setObjectName("sidebarStatusText")
        sidebar_status_layout.addWidget(self.sidebar_status_copy)
        side.addWidget(sidebar_status)
        shell.addWidget(sidebar)

        self.page_stack = QtWidgets.QStackedWidget()
        shell.addWidget(self.page_stack, 1)

        workspace = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(workspace)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.page_stack.addWidget(workspace)
        self._pages["workspace"] = workspace

        top_bar = QtWidgets.QFrame()
        top_bar.setObjectName("topBar")
        top = QtWidgets.QHBoxLayout(top_bar)
        top.setContentsMargins(22, 12, 22, 12)
        top.setSpacing(10)
        heading = QtWidgets.QVBoxLayout()
        heading.setSpacing(2)
        title = QtWidgets.QLabel("运行工作台")
        title.setObjectName("pageTitle")
        heading.addWidget(title)
        subtitle = QtWidgets.QLabel("组织任务队列，确认设备上下文并观察执行结果")
        subtitle.setObjectName("pageSubtitle")
        heading.addWidget(subtitle)
        top.addLayout(heading, 1)

        self.btn_open_report_top = QtWidgets.QPushButton("打开报告")
        self.btn_open_report_top.clicked.connect(self._open_last_report)
        self.btn_open_report_top.setEnabled(False)
        top.addWidget(self.btn_open_report_top)
        self.btn_open_run_dir_top = QtWidgets.QPushButton("打开产物")
        self.btn_open_run_dir_top.clicked.connect(self._open_last_run_dir)
        self.btn_open_run_dir_top.setEnabled(False)
        top.addWidget(self.btn_open_run_dir_top)
        self.btn_stop_top = QtWidgets.QPushButton("停止")
        self.btn_stop_top.setObjectName("dangerBtn")
        self.btn_stop_top.clicked.connect(self._stop_run)
        self.btn_stop_top.setEnabled(False)
        top.addWidget(self.btn_stop_top)
        self.btn_run_top = QtWidgets.QPushButton("运行队列")
        self.btn_run_top.setObjectName("primaryBtn")
        self.btn_run_top.clicked.connect(self._run_case)
        top.addWidget(self.btn_run_top)
        self.btn_stress_top = QtWidgets.QPushButton("压测模式")
        self.btn_stress_top.setObjectName("secondaryBtn")
        self.btn_stress_top.setToolTip("压测模式：选择任务 + CrealityScan.exe + 执行次数，失败/卡死自动杀进程重开")
        self.btn_stress_top.clicked.connect(self._run_stress_case)
        top.addWidget(self.btn_stress_top)
        root.addWidget(top_bar)

        self.act_run = QtWidgets.QAction("运行", self)
        self.act_run.triggered.connect(self._run_case)
        self.act_stop = QtWidgets.QAction("停止", self)
        self.act_stop.triggered.connect(self._stop_run)
        self.act_stop.setShortcut(QtGui.QKeySequence("F4"))
        self.act_stop.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        self.act_stop.setToolTip("停止当前自动化运行（F4）")
        self.act_stop.setStatusTip("停止当前自动化运行（F4）")
        self.act_stop.setEnabled(False)
        self.addAction(self.act_run)
        self.addAction(self.act_stop)
        self.act_open_report = QtWidgets.QAction("打开报告", self)
        self.act_open_report.triggered.connect(self._open_last_report)
        self.act_open_run_dir = QtWidgets.QAction("打开产物", self)
        self.act_open_run_dir.triggered.connect(self._open_last_run_dir)
        self.act_open_report.setEnabled(False)
        self.act_open_run_dir.setEnabled(False)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(18, 16, 18, 16)
        content_layout.setSpacing(12)
        root.addWidget(content, 1)

        run_banner = QtWidgets.QFrame()
        run_banner.setObjectName("panel")
        run_banner_layout = QtWidgets.QHBoxLayout(run_banner)
        run_banner_layout.setContentsMargins(16, 11, 16, 11)
        run_banner_layout.setSpacing(14)
        self.lbl_run_state = QtWidgets.QLabel("准备就绪")
        self.lbl_run_state.setObjectName("statusGood")
        run_banner_layout.addWidget(self.lbl_run_state)
        run_copy = QtWidgets.QVBoxLayout()
        run_copy.setSpacing(2)
        self.lbl_run_task = QtWidgets.QLabel("等待选择任务")
        self.lbl_run_task.setObjectName("sectionTitle")
        run_copy.addWidget(self.lbl_run_task)
        self.lbl_run_detail = QtWidgets.QLabel("任务按队列顺序执行；运行期间将锁定会改变上下文的操作。")
        self.lbl_run_detail.setObjectName("mutedText")
        run_copy.addWidget(self.lbl_run_detail)
        run_banner_layout.addLayout(run_copy, 1)
        self.run_progress = QtWidgets.QProgressBar()
        self.run_progress.setTextVisible(False)
        self.run_progress.setRange(0, 1)
        self.run_progress.setValue(0)
        self.run_progress.setFixedWidth(180)
        run_banner_layout.addWidget(self.run_progress)
        content_layout.addWidget(run_banner)

        body_split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        body_split.setChildrenCollapsible(False)
        body_split.setOpaqueResize(False)
        content_layout.addWidget(body_split, 3)

        queue_panel = QtWidgets.QFrame()
        queue_panel.setObjectName("panel")
        queue_layout = QtWidgets.QVBoxLayout(queue_panel)
        queue_layout.setContentsMargins(16, 14, 16, 14)
        queue_layout.setSpacing(9)
        queue_head = QtWidgets.QHBoxLayout()
        queue_title_box = QtWidgets.QVBoxLayout()
        queue_title_box.setSpacing(2)
        queue_title = QtWidgets.QLabel("待执行任务")
        queue_title.setObjectName("sectionTitle")
        queue_title_box.addWidget(queue_title)
        queue_hint = QtWidgets.QLabel("拖拽调整顺序，双击编辑任务")
        queue_hint.setObjectName("mutedText")
        queue_title_box.addWidget(queue_hint)
        queue_head.addLayout(queue_title_box, 1)
        self.btn_create_task = QtWidgets.QPushButton("新建任务")
        self.btn_create_task.setObjectName("primaryBtn")
        self.btn_create_task.clicked.connect(self._create_task)
        queue_head.addWidget(self.btn_create_task)
        self.btn_open_task_lib = QtWidgets.QPushButton("任务库")
        self.btn_open_task_lib.clicked.connect(lambda: self._show_page("task_library"))
        queue_head.addWidget(self.btn_open_task_lib)
        queue_layout.addLayout(queue_head)

        self.list_tasks = TaskListWidget(on_reordered=self._persist_task_bar_order)
        self.list_tasks.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list_tasks.setAlternatingRowColors(True)
        self.list_tasks.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list_tasks.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.list_tasks.setDragEnabled(True)
        self.list_tasks.setAcceptDrops(True)
        self.list_tasks.setDropIndicatorShown(True)
        self.list_tasks.setDragDropOverwriteMode(False)
        self.list_tasks.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.list_tasks.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.list_tasks.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.list_tasks.setAutoScroll(True)
        self.list_tasks.setAutoScrollMargin(24)
        self.list_tasks.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.list_tasks.verticalScrollBar().setSingleStep(28)
        self.list_tasks.itemDoubleClicked.connect(lambda *_: self._edit_selected_task())
        try:
            m = self.list_tasks.model()
            m.rowsMoved.connect(lambda *args: self._persist_task_bar_order())
            m.rowsInserted.connect(lambda *args: self._persist_task_bar_order())
            m.rowsRemoved.connect(lambda *args: self._persist_task_bar_order())
        except Exception:
            pass

        self.list_tasks.setMinimumHeight(250)
        self.lab_queue_empty = QtWidgets.QLabel("队列中还没有任务\n点击“新建任务”，或从任务库选择已有任务加入队列。")
        self.lab_queue_empty.setObjectName("mutedText")
        self.lab_queue_empty.setAlignment(QtCore.Qt.AlignCenter)
        self.lab_queue_empty.setWordWrap(True)
        self.lab_queue_empty.setMinimumHeight(250)
        self.lab_queue_empty.hide()
        queue_layout.addWidget(self.list_tasks, 1)
        queue_layout.addWidget(self.lab_queue_empty, 1)

        run_start_row = QtWidgets.QHBoxLayout()
        run_start_row.setContentsMargins(0, 0, 0, 0)
        run_start_row.setSpacing(8)
        run_start_label = QtWidgets.QLabel("起始步骤")
        run_start_label.setObjectName("fieldLabel")
        run_start_row.addWidget(run_start_label)
        self.combo_run_start_step = QtWidgets.QComboBox()
        self.combo_run_start_step.setMinimumHeight(30)
        self.combo_run_start_step.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.combo_run_start_step.setToolTip("选择本次运行从任务的哪一步开始；不会修改任务文件。")
        run_start_row.addWidget(self.combo_run_start_step, 1)
        queue_layout.addLayout(run_start_row)
        self.list_tasks.currentItemChanged.connect(lambda *_: self._refresh_run_start_step_selector())
        self.list_tasks.itemSelectionChanged.connect(self._refresh_run_start_step_selector)

        task_btns = QtWidgets.QHBoxLayout()
        self.btn_task_pick = QtWidgets.QPushButton("从任务库选择…")
        self.btn_task_pick.clicked.connect(lambda: self._show_page("task_library"))
        task_btns.addWidget(self.btn_task_pick)

        self.btn_task_remove = QtWidgets.QPushButton("从队列移除")
        self.btn_task_remove.clicked.connect(self._remove_selected_from_task_queue)
        task_btns.addWidget(self.btn_task_remove)

        self.btn_edit_task = QtWidgets.QPushButton("编辑选中任务")
        self.btn_edit_task.clicked.connect(self._edit_selected_task)
        task_btns.addWidget(self.btn_edit_task)

        task_btns.addStretch(1)
        queue_layout.addLayout(task_btns)
        self.btn_task_run = self.btn_run_top
        self._refresh_tasks()

        body_split.addWidget(queue_panel)

        context_panel = QtWidgets.QFrame()
        context_panel.setObjectName("panel")
        context_panel.setMinimumWidth(350)
        context_layout = QtWidgets.QVBoxLayout(context_panel)
        context_layout.setContentsMargins(16, 14, 16, 14)
        context_layout.setSpacing(12)
        context_head = QtWidgets.QHBoxLayout()
        context_title = QtWidgets.QLabel("运行上下文")
        context_title.setObjectName("sectionTitle")
        context_head.addWidget(context_title)
        context_head.addStretch(1)
        self.btn_refresh_device = QtWidgets.QPushButton("刷新设备")
        self.btn_refresh_device.clicked.connect(self._refresh_device_connection)
        context_head.addWidget(self.btn_refresh_device)
        context_layout.addLayout(context_head)

        self.edit_log_dir = QtWidgets.QLineEdit(self.model.app_log_dir)
        self.btn_browse_log_dir = QtWidgets.QPushButton("选择…")
        self.btn_browse_log_dir.clicked.connect(self._browse_log_dir)
        self.edit_log_dir.setPlaceholderText(r"例如：C:\\Users\\...\\CrealityScan\\Logs")
        log_label = QtWidgets.QLabel("CrealityScan 日志目录")
        log_label.setObjectName("fieldLabel")
        context_layout.addWidget(log_label)
        log_row = QtWidgets.QHBoxLayout()
        log_row.setSpacing(7)
        log_row.addWidget(self.edit_log_dir, 1)
        log_row.addWidget(self.btn_browse_log_dir)
        context_layout.addLayout(log_row)

        separator = QtWidgets.QFrame()
        separator.setObjectName("separator")
        separator.setFixedHeight(1)
        context_layout.addWidget(separator)

        device_status_row = QtWidgets.QHBoxLayout()
        status_label = QtWidgets.QLabel("设备状态")
        status_label.setObjectName("fieldLabel")
        device_status_row.addWidget(status_label)
        device_status_row.addStretch(1)
        self.lbl_device_status = QtWidgets.QLabel("未检测")
        self.lbl_device_status.setObjectName("statusWarn")
        device_status_row.addWidget(self.lbl_device_status)
        context_layout.addLayout(device_status_row)

        grid_device = QtWidgets.QGridLayout()
        grid_device.setHorizontalSpacing(12)
        grid_device.setVerticalSpacing(9)
        self.btn_slide_rail_console = QtWidgets.QPushButton("滑轨控制")
        self.btn_slide_rail_console.clicked.connect(self._open_slide_rail_console)
        self.lbl_device_name = QtWidgets.QLabel("-")
        self.lbl_device_sn = QtWidgets.QLabel("-")
        self.lbl_device_connection = QtWidgets.QLabel("-")
        self.lbl_device_firmware = QtWidgets.QLabel("-")

        for lab in [
            self.lbl_device_status,
            self.lbl_device_name,
            self.lbl_device_sn,
            self.lbl_device_connection,
            self.lbl_device_firmware,
        ]:
            lab.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            if lab is not self.lbl_device_status:
                lab.setObjectName("deviceValue")

        def context_label(text: str) -> QtWidgets.QLabel:
            label = QtWidgets.QLabel(text)
            label.setObjectName("mutedText")
            return label

        grid_device.addWidget(context_label("模组"), 0, 0)
        grid_device.addWidget(self.lbl_device_name, 0, 1)
        grid_device.addWidget(context_label("SN"), 1, 0)
        grid_device.addWidget(self.lbl_device_sn, 1, 1)
        grid_device.addWidget(context_label("连接"), 2, 0)
        grid_device.addWidget(self.lbl_device_connection, 2, 1)
        grid_device.addWidget(context_label("固件"), 3, 0)
        grid_device.addWidget(self.lbl_device_firmware, 3, 1)
        grid_device.setColumnStretch(1, 1)
        context_layout.addLayout(grid_device)
        context_layout.addStretch(1)
        tool_row = QtWidgets.QHBoxLayout()
        self.btn_slide_rail_service_toolbar = QtWidgets.QPushButton("连接滑轨服务")
        self.btn_slide_rail_service_toolbar.clicked.connect(self._ensure_slide_rail_service_started)
        tool_row.addWidget(self.btn_slide_rail_service_toolbar)
        self.btn_slide_rail_controller_toolbar = QtWidgets.QPushButton("连接控制器")
        self.btn_slide_rail_controller_toolbar.clicked.connect(self._connect_slide_rail_controller)
        tool_row.addWidget(self.btn_slide_rail_controller_toolbar)
        context_layout.addLayout(tool_row)
        context_layout.addWidget(self.btn_slide_rail_console)
        body_split.addWidget(context_panel)
        body_split.setStretchFactor(0, 7)
        body_split.setStretchFactor(1, 3)
        body_split.setSizes([850, 390])

        observatory = QtWidgets.QFrame()
        observatory.setObjectName("panel")
        observatory_layout = QtWidgets.QVBoxLayout(observatory)
        observatory_layout.setContentsMargins(14, 12, 14, 12)
        observatory_layout.setSpacing(7)
        obs_head = QtWidgets.QHBoxLayout()
        obs_title = QtWidgets.QLabel("运行观测")
        obs_title.setObjectName("sectionTitle")
        obs_head.addWidget(obs_title)
        obs_head.addStretch(1)
        obs_help = QtWidgets.QLabel("双击结果行可打开截图或报告")
        obs_help.setObjectName("mutedText")
        obs_head.addWidget(obs_help)
        observatory_layout.addLayout(obs_head)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMinimumHeight(220)
        observatory_layout.addWidget(self.tabs, 1)

        self.text_output = QtWidgets.QPlainTextEdit()
        self.text_output.setObjectName("outputBox")
        self.text_output.setReadOnly(True)
        self.text_output.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        self.tabs.addTab(self.text_output, "运行输出")

        self.table_results = QtWidgets.QTableWidget()
        self.table_results.setColumnCount(9)
        self.table_results.setHorizontalHeaderLabels(
            ["序号", "步骤 ID", "版本", "名称", "状态", "耗时（秒）", "尝试", "指标", "截图"]
        )
        self.table_results.horizontalHeader().setStretchLastSection(True)
        self.table_results.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.table_results.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.table_results.horizontalHeader().setSectionResizeMode(7, QtWidgets.QHeaderView.Stretch)
        self.table_results.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_results.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table_results.setAlternatingRowColors(True)
        self.table_results.verticalHeader().setVisible(False)
        self.table_results.cellDoubleClicked.connect(self._open_result_artifact)
        for column, width in enumerate((54, 210, 76, 240, 76, 86, 66, 260, 90)):
            self.table_results.setColumnWidth(column, width)
        self.tabs.addTab(self.table_results, "步骤结果")
        content_layout.addWidget(observatory, 2)

        self.statusBar().showMessage("就绪 · F4 可请求停止当前自动化运行")
        self._refresh_task_queue_empty_state()
        self._set_run_ui_state("idle")

    def _refresh_task_queue_empty_state(self) -> None:
        is_empty = self.list_tasks.count() == 0
        self.list_tasks.setVisible(not is_empty)
        self.lab_queue_empty.setVisible(is_empty)

    def _set_run_ui_state(self, state: str, detail: str = "") -> None:
        running = state in {"running", "stopping"}
        stopping = state == "stopping"
        state_copy = {
            "idle": ("准备就绪", "statusGood"),
            "running": ("正在运行", "statusGood"),
            "stopping": ("正在停止", "statusWarn"),
            "passed": ("运行通过", "statusGood"),
            "failed": ("运行失败", "statusBad"),
            "stopped": ("已停止", "statusWarn"),
        }
        text, object_name = state_copy.get(state, state_copy["idle"])
        self.lbl_run_state.setText(text)
        self.lbl_run_state.setObjectName(object_name)
        self.lbl_run_state.style().unpolish(self.lbl_run_state)
        self.lbl_run_state.style().polish(self.lbl_run_state)
        task_name = self._running_task.stem if self._running_task else "等待选择任务"
        self.lbl_run_task.setText(task_name)
        if detail:
            self.lbl_run_detail.setText(detail)
        elif state == "idle":
            self.lbl_run_detail.setText("任务按队列顺序执行；运行期间将锁定会改变上下文的操作。")

        if running:
            maximum = max(1, int(self._task_queue_total or 1))
            current = max(0, int(self._task_queue_index or (1 if self._running_task else 0)))
            self.run_progress.setRange(0, maximum)
            self.run_progress.setValue(min(current, maximum))
        else:
            self.run_progress.setRange(0, 1)
            self.run_progress.setValue(1 if state == "passed" else 0)

        self.act_run.setEnabled(not running)
        self.act_stop.setEnabled(running and not stopping)
        self.btn_run_top.setEnabled(not running)
        self.btn_stop_top.setEnabled(running and not stopping)
        self.btn_stress_top.setEnabled(not running)
        for control in (
            self.btn_create_task,
            self.btn_open_task_lib,
            self.btn_task_pick,
            self.btn_task_remove,
            self.btn_edit_task,
            self.edit_log_dir,
            self.btn_browse_log_dir,
            self.btn_refresh_device,
            self.btn_slide_rail_service_toolbar,
            self.btn_slide_rail_controller_toolbar,
            self.btn_slide_rail_console,
            self.combo_run_start_step,
            self.list_tasks,
            self.nav_task_library,
            self.nav_slide_rail,
            self.nav_email,
            self.nav_postprocess_compare,
            self.nav_calibration_score,
            self.nav_firmware_upgrade,
        ):
            control.setEnabled(not running)

    def _current_page_key(self) -> str:
        current = self.page_stack.currentWidget() if hasattr(self, "page_stack") else None
        for key, page in self._pages.items():
            if page is current:
                return key
        return "workspace"

    def _show_page(self, key: str) -> bool:
        if self._tool_busy_key is not None and key != self._tool_busy_key:
            self.statusBar().showMessage("工具任务运行中，请先停止后再切换页面", 5000)
            busy_button = self._page_nav_buttons.get(self._tool_busy_key)
            if busy_button is not None:
                busy_button.setChecked(True)
            return False
        page = self._pages.get(key)
        if page is None:
            page = self._create_tool_page(key)
            self._pages[key] = page
            self.page_stack.addWidget(page)
        self.page_stack.setCurrentWidget(page)
        button = self._page_nav_buttons.get(key)
        if button is not None:
            button.setChecked(True)
        activate = getattr(page, "activate", None)
        if callable(activate):
            activate()
        return True

    def _create_tool_page(self, key: str) -> QtWidgets.QWidget:
        try:
            if key == "postprocess_compare":
                page = PostprocessComparePage(self.project_root, self)
                page.busyChanged.connect(
                    lambda busy, page_key=key: self._set_tool_busy(page_key, busy)
                )
            elif key == "firmware_upgrade":
                page = FirmwareUpgradePage(self.project_root, self)
                page.busyChanged.connect(
                    lambda busy, page_key=key: self._set_tool_busy(page_key, busy)
                )
                page.runFinished.connect(self._on_firmware_run_finished)
            elif key == "calibration_score":
                page = CalibrationScorePage(self.project_root, self)
            elif key == "task_library":
                page = TaskLibraryPage(self.project_root, self)
                page.enqueueRequested.connect(self._enqueue_tasks_to_queue)
                page.loadRequested.connect(lambda path: self._edit_task_path(Path(path)))
                page.tasksChanged.connect(self._refresh_tasks)
            else:
                raise ToolPageLoadError(f"未知工具页面：{key}")
            page.statusMessage.connect(lambda message: self.statusBar().showMessage(message, 5000))
            return page
        except ToolPageLoadError as exc:
            title = {
                "postprocess_compare": "后处理对比工具不可用",
                "calibration_score": "标定分数工具不可用",
                "firmware_upgrade": "固件升级工具不可用",
            }.get(key, "工具不可用")
            error_page = ToolErrorPage(title, str(exc), self)
            error_page.retryRequested.connect(lambda page_key=key: self._retry_tool_page(page_key))
            return error_page

    def _retry_tool_page(self, key: str) -> None:
        old_page = self._pages.pop(key, None)
        if old_page is not None:
            self.page_stack.removeWidget(old_page)
            old_page.deleteLater()
        self._show_page(key)

    def _set_tool_busy(self, key: str, busy: bool) -> None:
        self._tool_busy_key = key if busy else None
        self.act_run.setEnabled(not busy)
        self.act_stop.setEnabled(busy)
        tool_name = {
            "postprocess_compare": "后处理对比",
            "firmware_upgrade": "固件升级",
        }.get(key, "工具")
        self.sidebar_status_copy.setText(f"{tool_name}任务运行中" if busy else "运行时可随时请求停止")
        for page_key, button in self._page_nav_buttons.items():
            button.setEnabled(not busy or page_key == key)
        for button in (
            self.nav_task_library,
            self.nav_slide_rail,
            self.nav_email,
        ):
            button.setEnabled(not busy)

    def _on_firmware_run_finished(self, success: bool, report_path: str, stopped: bool) -> None:
        status = "stopped" if stopped else ("passed" if success else "failed")
        self._notification_dispatcher.send_tool_result_email(
            "固件升级测试",
            status,
            report_path,
        )

    def _load_step_registry(self) -> None:
        self._all_step_metas = scan_steps(self.project_root)
        self._apply_step_filter()

    def _apply_step_filter(self) -> None:
        if not hasattr(self, "list_available"):
            return
        text = ""
        if hasattr(self, "edit_step_filter"):
            text = self.edit_step_filter.text().strip().lower()
        self.list_available.clear()
        for m in self._all_step_metas:
            if text:
                hay = f"{m.name} {m.step_id} {m.version}".lower()
                if text not in hay:
                    continue
            self.list_available.addItem(StepListItem(m))

    def _refresh_selected_steps(self) -> None:
        if not hasattr(self, "list_selected"):
            return
        self.list_selected.blockSignals(True)
        try:
            self.list_selected.clear()
            for s in self.model.steps:
                self.list_selected.addItem(SelectedStepItem(s))
        finally:
            self.list_selected.blockSignals(False)

    def _sync_model_from_selected_list_order(self) -> None:
        if not hasattr(self, "list_selected"):
            return
        steps = []
        for i in range(self.list_selected.count()):
            it = self.list_selected.item(i)
            if isinstance(it, SelectedStepItem):
                steps.append(it.step)
        self.model.steps = steps

    def _add_selected_step(self, item: QtWidgets.QListWidgetItem) -> None:
        if not isinstance(item, StepListItem):
            return
        meta = item.meta
        # 双击添加：允许重复（编排场景常见需要多次执行同一步骤）
        step = CaseStep(step_id=meta.step_id, version=meta.version, name=meta.name)
        if self._is_preset_step(meta.step_id, meta.version):
            if not self._pick_preset_for_step(step):
                return
        if meta.step_id == _SET_POINT_DISTANCE_STEP_ID:
            if not self._set_point_distance_for_step(step):
                return
        if _is_target_frames_step(meta.step_id):
            if not self._set_target_frames_for_step(step):
                return
        if meta.step_id == _SLEEP_STEP_ID:
            if not self._set_sleep_seconds_for_step(step):
                return
        self.model.steps.append(step)
        self._refresh_selected_steps()

    def _remove_selected_step(self) -> None:
        cur = self.list_selected.currentItem()
        if not isinstance(cur, SelectedStepItem):
            return
        idx = self.list_selected.row(cur)
        if 0 <= idx < len(self.model.steps):
            self.model.steps.pop(idx)
        self._refresh_selected_steps()

    def _on_selected_step_changed(self, cur, prev) -> None:
        self._sync_model_from_selected_list_order()
        if not isinstance(cur, SelectedStepItem):
            self._current_step_item = None
            self._set_step_detail_enabled(False)
            if hasattr(self, "btn_pick_preset"):
                self.btn_pick_preset.setVisible(False)
            if hasattr(self, "btn_set_point_distance"):
                self.btn_set_point_distance.setVisible(False)
            if hasattr(self, "btn_set_target_frames"):
                self.btn_set_target_frames.setVisible(False)
            if hasattr(self, "btn_set_sleep_seconds"):
                self.btn_set_sleep_seconds.setVisible(False)
            return
        self._current_step_item = cur
        self._set_step_detail_enabled(True)
        self._load_step_detail(cur.step)
        if hasattr(self, "btn_pick_preset"):
            self.btn_pick_preset.setVisible(self._is_preset_step(cur.step.step_id, cur.step.version))
        if hasattr(self, "btn_set_point_distance"):
            self.btn_set_point_distance.setVisible(cur.step.step_id == _SET_POINT_DISTANCE_STEP_ID)
        if hasattr(self, "btn_set_target_frames"):
            self.btn_set_target_frames.setVisible(_is_target_frames_step(cur.step.step_id))
        if hasattr(self, "btn_set_sleep_seconds"):
            self.btn_set_sleep_seconds.setVisible(cur.step.step_id == _SLEEP_STEP_ID)

    def _set_step_detail_enabled(self, enabled: bool) -> None:
        self.edit_step_name.setEnabled(enabled)
        self.combo_on_fail.setEnabled(enabled)
        self.spin_retries.setEnabled(enabled)
        self.spin_retry_wait.setEnabled(enabled)
        self.edit_params.setEnabled(enabled)
        if hasattr(self, "btn_pick_preset"):
            self.btn_pick_preset.setEnabled(enabled)
        if hasattr(self, "btn_set_point_distance"):
            self.btn_set_point_distance.setEnabled(enabled)
        if hasattr(self, "btn_set_target_frames"):
            self.btn_set_target_frames.setEnabled(enabled)
        if hasattr(self, "btn_set_sleep_seconds"):
            self.btn_set_sleep_seconds.setEnabled(enabled)

    def _load_step_detail(self, step: CaseStep) -> None:
        self.edit_step_name.blockSignals(True)
        self.combo_on_fail.blockSignals(True)
        self.spin_retries.blockSignals(True)
        self.spin_retry_wait.blockSignals(True)
        self.edit_params.blockSignals(True)
        try:
            self.edit_step_name.setText(step.name or "")
            on_fail = step.on_fail or {"action": "abort"}
            action = str(on_fail.get("action") or "abort")
            idx = self.combo_on_fail.findText(action)
            self.combo_on_fail.setCurrentIndex(idx if idx >= 0 else 0)
            self.spin_retries.setValue(int(on_fail.get("max_retries") or 0))
            self.spin_retry_wait.setValue(float(on_fail.get("retry_wait_sec") or 0.5))
            self.edit_params.setPlainText(json.dumps(step.params or {}, ensure_ascii=False, indent=2))
        finally:
            self.edit_step_name.blockSignals(False)
            self.combo_on_fail.blockSignals(False)
            self.spin_retries.blockSignals(False)
            self.spin_retry_wait.blockSignals(False)
            self.edit_params.blockSignals(False)

    def _apply_step_detail_changes(self) -> None:
        if not self._current_step_item:
            return
        step = self._current_step_item.step
        step.name = self.edit_step_name.text().strip()
        step.on_fail = {
            "action": self.combo_on_fail.currentText(),
            "max_retries": int(self.spin_retries.value()),
            "retry_wait_sec": float(self.spin_retry_wait.value()),
        }
        try:
            step.params = json.loads(self.edit_params.toPlainText() or "{}")
            if not isinstance(step.params, dict):
                step.params = {}
        except Exception:
            # 输入不合法时不覆盖旧值；由用户修正
            pass
        self._current_step_item.refresh_text()

    def _pick_preset_for_step(self, step: CaseStep) -> bool:
        """
        为支持 presets.json 的步骤选择 preset，并写回 step.params。
        """
        try:
            presets = self._load_presets_for_step(step.step_id, step.version)
        except Exception as e:
            show_error(self, "无法加载 preset", str(e))
            return False
        if not presets:
            show_error(self, "无法加载 preset", "未找到可用 preset（presets.json 为空或解析失败）。")
            return False

        dlg = PresetPickerDialog("选择扫描参数 preset", presets, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return False
        name_cn, key = dlg.selected()
        # 记录中文名，便于阅读；Step 实现支持中文/英文 key
        step.params = {"preset": name_cn or key}
        # 默认把显示名改为更直观（用户仍可在右侧“显示名”里手动改）
        if name_cn:
            step.name = _preset_step_name(step.step_id, name_cn)
        return True

    def _pick_preset_for_current_step(self) -> None:
        if not self._current_step_item:
            return
        step = self._current_step_item.step
        if not self._is_preset_step(step.step_id, step.version):
            return
        self._pick_preset_for_step(step)
        # 回填 params 文本框并刷新显示
        self._load_step_detail(step)
        self._current_step_item.refresh_text()

    def _set_point_distance_for_step(self, step: CaseStep) -> bool:
        default_value = "0.45"
        if isinstance(step.params, dict):
            v = step.params.get("distance_mm")
            if v is not None:
                default_value = str(v).strip() or default_value

        dlg = PointDistanceDialog(default_value=default_value, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return False
        distance_mm = dlg.value()
        if not distance_mm:
            return False
        step.params = {"distance_mm": distance_mm}
        step.name = f"点距：{distance_mm}mm"
        return True

    def _set_point_distance_for_current_step(self) -> None:
        if not self._current_step_item:
            return
        step = self._current_step_item.step
        if step.step_id != _SET_POINT_DISTANCE_STEP_ID:
            return
        if not self._set_point_distance_for_step(step):
            return
        self._load_step_detail(step)
        self._current_step_item.refresh_text()

    def _set_target_frames_for_step(self, step: CaseStep) -> bool:
        default_value = "200"
        if isinstance(step.params, dict):
            # 新参数优先
            v = step.params.get("target_frames")
            if v is None:
                # 兼容旧参数：gt + 1
                gt = step.params.get("target_frames_gt")
                if gt is not None:
                    try:
                        default_value = str(int(gt) + 1)
                    except Exception:
                        pass
            else:
                default_value = str(v).strip() or default_value

        dlg = TargetFramesDialog(default_value=default_value, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return False
        frames = dlg.value()
        if not frames:
            return False

        frames_value = int(frames)
        step.params = {"target_frames": frames_value}
        step.name = _target_frames_step_name(step.step_id, frames_value)
        return True

    def _set_target_frames_for_current_step(self) -> None:
        if not self._current_step_item:
            return
        step = self._current_step_item.step
        if not _is_target_frames_step(step.step_id):
            return
        if not self._set_target_frames_for_step(step):
            return
        self._load_step_detail(step)
        self._current_step_item.refresh_text()

    def _set_sleep_seconds_for_step(self, step: CaseStep) -> bool:
        default_value = 1.0
        if isinstance(step.params, dict):
            try:
                default_value = float(step.params.get("seconds", default_value))
            except (TypeError, ValueError):
                default_value = 1.0
        dlg = SleepSecondsDialog(default_value=default_value, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return False
        seconds = dlg.value()
        step.params = {"seconds": float(seconds)}
        step.name = f"等待{seconds:g}s"
        return True

    def _set_sleep_seconds_for_current_step(self) -> None:
        if not self._current_step_item:
            return
        step = self._current_step_item.step
        if step.step_id != _SLEEP_STEP_ID:
            return
        if not self._set_sleep_seconds_for_step(step):
            return
        self._load_step_detail(step)
        self._current_step_item.refresh_text()

    def _browse_log_dir(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "选择 CrealityScan 日志目录", self.edit_log_dir.text())
        if d:
            self.edit_log_dir.setText(d)
            self._refresh_device_connection()

    def _update_model_from_ui(self) -> None:
        self._sync_model_from_selected_list_order()
        # 用例基础信息不在 UI 暴露：保持当前 model 值（KISS / YAGNI）
        case_id_widget = getattr(self, "edit_case_id", None)
        case_name_widget = getattr(self, "edit_case_name", None)
        if case_id_widget is not None:
            self.model.case_id = case_id_widget.text().strip() or "case"
        if case_name_widget is not None:
            self.model.name = case_name_widget.text().strip() or (self.model.case_id or "case")
        if not (self.model.case_id or "").strip():
            self.model.case_id = "case"
        if not (self.model.name or "").strip():
            self.model.name = self.model.case_id

        self.model.app_log_dir = self.edit_log_dir.text().strip()

        # 低频项不在 UI 暴露：保持当前值/默认值（KISS）
        if not (self.model.app_window_title_contains or "").strip():
            self.model.app_window_title_contains = "CrealityScan"
        if not self.model.keywords:
            self.model.keywords = list(DEFAULT_KEYWORDS)

    def _save_case(self) -> None:
        self._update_model_from_ui()
        try:
            path = save_case_json(self.project_root, self.model)
            self.statusBar().showMessage(f"已保存：{path}")
        except Exception as e:
            show_error(self, "保存失败", str(e))

    def _open_task_manager(self) -> None:
        dlg = TaskManagerDialog(self.project_root, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return

        action = dlg.result_action()
        paths = dlg.selected_paths()
        if not paths:
            return

        if action == "load":
            self._edit_task_path(Path(paths[0]))
            return

        if action == "enqueue":
            self._enqueue_tasks_to_queue([Path(p) for p in paths])
            self.statusBar().showMessage(f"已加入队列：{len(paths)} 个任务")
            return

        if action == "run":
            self._run_task_paths([Path(paths[0])])
            return

        if action == "batch":
            self._run_task_paths([Path(p) for p in paths])
            return

    def _enqueue_tasks_to_queue(self, paths: list[Path]) -> None:
        if not paths:
            return
        base = self._tasks_dir()
        existing = {str(p) for p in self._task_paths_in_list_order()} if hasattr(self, "list_tasks") else set()
        added_items: list[QtWidgets.QListWidgetItem] = []

        for p in paths:
            p = Path(p)
            try:
                rel = p.relative_to(base)
                if rel.name.lower() == "_queue.json":
                    continue
            except Exception:
                # 只允许 tasks/ 下的任务进入队列（避免队列持久化失败）
                continue
            if str(p) in existing:
                continue
            it = QtWidgets.QListWidgetItem(p.stem)
            it.setToolTip(str(p))
            it.setData(QtCore.Qt.UserRole, str(p))
            it.setFlags(
                it.flags()
                | QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsSelectable
                | QtCore.Qt.ItemIsDragEnabled
                | QtCore.Qt.ItemIsDropEnabled
            )
            self.list_tasks.addItem(it)
            existing.add(str(p))
            added_items.append(it)

        self._persist_task_bar_order()
        self._refresh_task_queue_empty_state()
        if added_items:
            try:
                self.list_tasks.clearSelection()
                for it in added_items:
                    it.setSelected(True)
                self.list_tasks.setCurrentItem(added_items[-1])
                self.list_tasks.scrollToItem(added_items[-1], QtWidgets.QAbstractItemView.PositionAtBottom)
            except Exception:
                pass

    def _remove_selected_from_task_queue(self) -> None:
        if not hasattr(self, "list_tasks"):
            return
        rows = sorted({it.listWidget().row(it) for it in self.list_tasks.selectedItems() if it}, reverse=True)
        if not rows:
            return
        for r in rows:
            try:
                self.list_tasks.takeItem(r)
            except Exception:
                pass
        self._persist_task_bar_order()
        self._refresh_task_queue_empty_state()

    def _open_tasks_dir(self) -> None:
        try:
            os.startfile(str(self._tasks_dir()))  # type: ignore[attr-defined]
        except Exception:
            pass

    def _tasks_dir(self) -> Path:
        base = self.project_root / "tasks"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _task_queue_file(self) -> Path:
        return self._tasks_dir() / "_queue.json"

    def _load_task_queue_names(self) -> list[str]:
        fp = self._task_queue_file()
        if not fp.exists():
            return []
        try:
            raw = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        for x in raw:
            if isinstance(x, str) and x.strip().lower().endswith(".json"):
                out.append(x.strip())
        return out

    def _save_task_queue_names(self, names: list[str]) -> None:
        fp = self._task_queue_file()
        fp.write_text(json.dumps(names, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _task_paths_in_list_order(self) -> list[Path]:
        out: list[Path] = []
        for i in range(self.list_tasks.count()):
            it = self.list_tasks.item(i)
            if not it:
                continue
            raw = it.data(QtCore.Qt.UserRole)
            if isinstance(raw, str) and raw:
                out.append(Path(raw))
        return out

    def _persist_task_bar_order(self) -> None:
        if not hasattr(self, "list_tasks"):
            return
        if getattr(self, "_task_bar_refreshing", False):
            return
        base = self._tasks_dir()
        names: list[str] = []
        for p in self._task_paths_in_list_order():
            try:
                rel = p.relative_to(base)
                if rel.name.lower() == "_queue.json":
                    continue
                names.append(rel.name)
            except Exception:
                # 非 tasks 目录下的路径不写入队列
                continue
        try:
            self._save_task_queue_names(names)
        except Exception:
            pass

    def _refresh_tasks(self) -> None:
        if not hasattr(self, "list_tasks"):
            return

        base = self._tasks_dir()

        # 只展示“队列”中的任务（用户明确选择的子集），避免默认把全部 tasks/*.json 都塞进主界面。
        queue_names = self._load_task_queue_names()
        ordered: list[Path] = []
        for name in queue_names:
            p = base / name
            if p.exists() and p.is_file() and p.name.lower().endswith(".json") and p.name.lower() != "_queue.json":
                ordered.append(p)

        self._task_bar_refreshing = True
        self.list_tasks.blockSignals(True)
        try:
            self.list_tasks.clear()
            for p in ordered:
                it = QtWidgets.QListWidgetItem(p.stem)
                it.setToolTip(str(p))
                it.setData(QtCore.Qt.UserRole, str(p))
                it.setFlags(
                    it.flags()
                    | QtCore.Qt.ItemIsEnabled
                    | QtCore.Qt.ItemIsSelectable
                    | QtCore.Qt.ItemIsDragEnabled
                    | QtCore.Qt.ItemIsDropEnabled
                )
                self.list_tasks.addItem(it)
        finally:
            self.list_tasks.blockSignals(False)
            self._task_bar_refreshing = False

        # 若队列文件不存在/损坏，写回一次，确保后续拖拽可持久化
        self._persist_task_bar_order()
        self._refresh_task_queue_empty_state()
        self._refresh_run_start_step_selector()

    def _find_task_in_list(self) -> None:
        text = (self.edit_task_filter.text() if hasattr(self, "edit_task_filter") else "").strip().lower()
        if not text:
            return
        for i in range(self.list_tasks.count()):
            it = self.list_tasks.item(i)
            if not it:
                continue
            hay = (it.text() or "").strip().lower()
            if text in hay:
                self.list_tasks.setCurrentRow(i)
                it.setSelected(True)
                return

    def _selected_task_paths(self) -> list[Path]:
        out: list[Path] = []
        for it in self.list_tasks.selectedItems():
            raw = it.data(QtCore.Qt.UserRole)
            if isinstance(raw, str) and raw:
                out.append(Path(raw))
        return out

    def _build_default_task_model(self, name: str) -> CaseModel:
        task_name = (name or "新任务").strip() or "新任务"
        return CaseModel(
            case_id=self._safe_task_stem(task_name),
            name=task_name,
            app_window_title_contains="CrealityScan",
            app_log_dir=self.edit_log_dir.text().strip() or self.model.app_log_dir,
            keywords=list(self.model.keywords or DEFAULT_KEYWORDS),
            steps=[],
        )

    def _build_generated_task_model_from_option(self, option: TaskGenerationOption, name: str) -> Optional[CaseModel]:
        task_name = (name or f"{option.module_name}{option.task_kind}").strip() or f"{option.module_name}{option.task_kind}"
        current_log_dir = self.edit_log_dir.text().strip() or self.model.app_log_dir
        current_keywords = list(self.model.keywords or DEFAULT_KEYWORDS)
        try:
            model = build_task_model(
                module_name=option.module_name,
                task_kind=option.task_kind,
                task_name=task_name,
                app_log_dir=current_log_dir,
                keywords=current_keywords,
            )
        except Exception as e:
            show_error(self, "无法生成任务", str(e))
            return None
        model.case_id = self._safe_task_stem(model.case_id)
        return model

    def _task_generator_options(self) -> list[TaskGenerationOption]:
        return list_task_generation_options()

    def _build_generated_task_model(self, name: str) -> Optional[CaseModel]:
        options = self._task_generator_options()
        if not options:
            show_error(self, "无法生成任务", "当前没有可用的生成规则。")
            return None

        labels = [option.label for option in options]
        label, ok = QtWidgets.QInputDialog.getItem(
            self,
            "从生成器生成任务",
            "选择模板：",
            labels,
            0,
            False,
        )
        if not ok or not label:
            return None

        option = next((item for item in options if item.label == label), None)
        if option is None:
            show_error(self, "无法生成任务", f"未找到模板：{label}")
            return None
        return self._build_generated_task_model_from_option(option, name)

    def _resolve_task_path(self, name: str) -> Optional[Path]:
        base = self.project_root / "tasks"
        base.mkdir(parents=True, exist_ok=True)
        stem = self._safe_task_stem(name)
        path = base / f"{stem}.json"
        if not path.exists():
            return path

        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle("任务已存在")
        box.setText(f"同名任务已存在：{path.name}\n是否覆盖？")
        box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel)
        result = box.exec_()
        if result == QtWidgets.QMessageBox.Yes:
            return path
        if result == QtWidgets.QMessageBox.Cancel:
            return None

        i = 2
        while True:
            cand = base / f"{stem}_{i}.json"
            if not cand.exists():
                return cand
            i += 1

    def _select_task_in_queue(self, fp: Path) -> None:
        target = str(Path(fp))
        self.list_tasks.clearSelection()
        for i in range(self.list_tasks.count()):
            it = self.list_tasks.item(i)
            if it and str(it.data(QtCore.Qt.UserRole) or "") == target:
                self.list_tasks.setCurrentRow(i)
                it.setSelected(True)
                break

    def _edit_task_path(self, fp: Path, initial_model: Optional[CaseModel] = None) -> bool:
        try:
            dlg = TaskEditDialog(self.project_root, fp, self._all_step_metas, parent=self, initial_model=initial_model)
        except Exception as e:
            show_error(self, "无法编辑任务", str(e))
            return False
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return False

        self._current_task_path = fp
        self.edit_log_dir.setText(dlg.model.app_log_dir)
        self._refresh_tasks()
        self._enqueue_tasks_to_queue([fp])
        self._select_task_in_queue(fp)
        self.statusBar().showMessage(f"已保存任务：{fp}")
        return True

    def _create_task(self) -> None:
        dlg = TaskCreationWizardDialog(self.project_root, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        if dlg.free_edit_requested:
            self._create_task_from_scratch(getattr(dlg, "free_edit_default_name", "") or "")
            return
        values = dlg.values()
        name = str(values.get("task_name") or "").strip()
        path = self._resolve_task_path(name)
        if path is None:
            return
        try:
            model = build_task_model(
                module_name=str(values.get("module_name") or ""),
                task_kind=str(values.get("task_kind") or ""),
                task_name=name,
                preset_keys=[str(value) for value in values.get("preset_keys", [])],
                target_frames=int(values.get("target_frames") or 200),
                connection_type=str(values.get("connection_type") or ""),
                project_root=self.project_root,
                app_log_dir=self.edit_log_dir.text().strip() or self.model.app_log_dir,
                keywords=list(self.model.keywords or DEFAULT_KEYWORDS),
                slide_rail=bool(values.get("slide_rail") or False),
            )
        except (KeyError, OSError, TypeError, ValueError) as exc:
            show_error(self, "无法生成任务", str(exc))
            return
        model.case_id = self._safe_task_stem(model.case_id)
        self._edit_task_path(path, initial_model=model)

    def _create_task_from_scratch(self, default_name: str = "") -> None:
        default_name = (default_name or "手动编排任务").strip() or "手动编排任务"
        name, ok = QtWidgets.QInputDialog.getText(self, "自由编排任务", "任务名称：", text=default_name)
        name = (name or "").strip()
        if not ok or not name:
            return
        path = self._resolve_task_path(name)
        if path is None:
            return
        self._edit_task_path(path, initial_model=self._build_default_task_model(name))

    def _edit_selected_task(self) -> None:
        fps = self._selected_task_paths()
        if not fps:
            return
        self._edit_task_path(Path(fps[0]))

    def _safe_task_stem(self, name: str) -> str:
        import re

        s = (name or "task").strip() or "task"
        s = re.sub(r'[<>:"/\\\\|?*]+', "_", s)
        s = s.strip() or "task"
        return s

    def _save_current_as_task(self) -> None:
        self._create_task()

    def _delete_selected_tasks(self) -> None:
        fps = self._selected_task_paths()
        if not fps:
            return
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("确认删除")
        box.setText(f"确定删除 {len(fps)} 个任务文件吗？此操作不可恢复。")
        box.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Ok)
        if box.exec_() != QtWidgets.QMessageBox.Ok:
            return

        for p in fps:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        self._refresh_tasks()

    def _run_start_reference_task_path(self) -> Optional[Path]:
        if not hasattr(self, "list_tasks"):
            return None
        cur = self.list_tasks.currentItem()
        if cur is None:
            selected = self.list_tasks.selectedItems()
            cur = selected[0] if selected else None
        if cur is not None:
            raw = cur.data(QtCore.Qt.UserRole)
            if isinstance(raw, str) and raw:
                return Path(raw)
        paths = self._task_paths_in_list_order()
        return paths[0] if paths else None

    def _refresh_run_start_step_selector(self) -> None:
        if not hasattr(self, "combo_run_start_step"):
            return
        current_index = int(self.combo_run_start_step.currentData() or 1)
        self.combo_run_start_step.blockSignals(True)
        try:
            self.combo_run_start_step.clear()
            if self.list_tasks.count() > 1:
                self.combo_run_start_step.addItem("批量队列仅支持从第1步完整执行", 1)
                self.combo_run_start_step.setEnabled(False)
                self.combo_run_start_step.setToolTip("不同任务的步骤结构可能不同，批量运行不会共用起始步骤序号。")
                return
            task_path = self._run_start_reference_task_path()
            if not task_path or not task_path.exists():
                self.combo_run_start_step.addItem("第1步（完整执行）", 1)
                self.combo_run_start_step.setEnabled(False)
                return

            model = load_task_json(task_path)
            steps = list(model.steps or [])
            if not steps:
                self.combo_run_start_step.addItem("第1步（完整执行）", 1)
                self.combo_run_start_step.setEnabled(False)
                return

            for i, step in enumerate(steps, start=1):
                name = (step.name or step.step_id or "").strip() or f"步骤{i}"
                prefix = "完整执行：" if i == 1 else "从这里开始："
                self.combo_run_start_step.addItem(f"第{i}步 · {prefix}{name}", i)
            self.combo_run_start_step.setEnabled(True)
            restored = self.combo_run_start_step.findData(current_index)
            self.combo_run_start_step.setCurrentIndex(restored if restored >= 0 else 0)
        except Exception as e:
            self.combo_run_start_step.clear()
            self.combo_run_start_step.addItem("第1步（完整执行）", 1)
            self.combo_run_start_step.setEnabled(False)
            self.combo_run_start_step.setToolTip(f"无法读取任务步骤：{e}")
        finally:
            self.combo_run_start_step.blockSignals(False)

    def _selected_run_start_step_index(self) -> int:
        if not hasattr(self, "combo_run_start_step"):
            return 1
        try:
            return max(1, int(self.combo_run_start_step.currentData() or 1))
        except Exception:
            return 1

    def _runtime_json_for_task(self, task_path: Path, start_step_index: int) -> Path:
        start_step_index = max(1, int(start_step_index or 1))
        if start_step_index <= 1:
            return task_path

        raw = json.loads(Path(task_path).read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError(f"任务 JSON 必须是对象：{task_path}")
        steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
        if start_step_index > len(steps):
            return task_path

        run_options = raw.get("run_options") if isinstance(raw.get("run_options"), dict) else {}
        run_options = dict(run_options)
        run_options["start_step_index"] = start_step_index
        raw["run_options"] = run_options

        base = self.project_root / "cases" / "_generated"
        base.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = base / f"{self._safe_task_stem(task_path.stem)}_from_step{start_step_index}_{ts}.json"
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _run_task_paths(self, paths: list[Path]) -> None:

        if hasattr(self, "act_run") and not self.act_run.isEnabled():
            show_error(self, "无法运行任务", "当前正在运行中，请先停止或等待结束。")
            return
        if not paths:
            return
        queue_paths = [Path(p) for p in paths]
        self._queue_started_at = datetime.now().isoformat(timespec="seconds")
        self._queue_summaries = []

        title_contains = self.model.app_window_title_contains
        try:
            first = load_task_json(Path(queue_paths[0]))
            title_contains = first.app_window_title_contains or title_contains
        except Exception:
            pass

        if ConfirmRunDialog(title_contains=title_contains, parent=self).exec_() != QtWidgets.QDialog.Accepted:
            return

        self._task_run_start_step_index = self._selected_run_start_step_index() if len(queue_paths) == 1 else 1
        if len(queue_paths) == 1:
            self._batch_mode = False
            self._task_queue = []
            self._task_queue_total = 1
            self._task_queue_index = 1
            self._running_task = Path(queue_paths[0])
            try:
                runtime_json = self._runtime_json_for_task(self._running_task, self._task_run_start_step_index)
            except Exception as e:
                show_error(self, "无法运行任务", f"生成运行 JSON 失败：{e}")
                return
            self._start_run_with_json(runtime_json, label="task_json", clear_output=True)
            return

        self._batch_mode = True
        self._task_queue = queue_paths
        self._task_queue_total = len(self._task_queue)
        self._task_queue_index = 0
        self._running_task = None

        self.text_output.clear()
        if hasattr(self, "tabs"):
            self.tabs.setCurrentWidget(self.text_output)
        if hasattr(self, "table_results"):
            self._clear_results_table()
        self._append_output(f"[UI] task_queue_total={self._task_queue_total}\n")
        self._start_next_task_from_queue()

    def _start_next_task_from_queue(self) -> None:
        # 批量运行：按队列顺序串行启动下一个任务（KISS：最小状态机）
        if not self._task_queue:
            self._append_output("\n[UI] task queue empty\n")
            self._batch_mode = False
            self._running_task = None
            self._set_run_ui_state("passed", "队列中的任务已全部执行完成。")
            self.statusBar().showMessage("队列已完成")
            return

        while self._task_queue and not Path(self._task_queue[0]).exists():
            missing_task = Path(self._task_queue.pop(0))
            self._append_output(f"[UI] skip missing task_json={missing_task}\n")
            self._queue_summaries.append(TaskRunSummary(task_json_name=missing_task.name, status="skipped"))
        if not self._task_queue:
            self._batch_mode = False
            self._running_task = None
            self._set_run_ui_state("failed", "队列为空，或任务文件已不存在。")
            self.statusBar().showMessage("队列为空/任务文件缺失")
            return

        next_task = Path(self._task_queue[0])
        next_index = int(getattr(self, "_task_queue_index", 0)) + 1
        if self._task_queue_total <= 0:
            self._task_queue_total = next_index + len(self._task_queue) - 1
        self._running_task = next_task

        self.statusBar().showMessage(f"批量运行 {next_index}/{self._task_queue_total} …")
        self._set_run_ui_state("running", f"正在执行队列第 {next_index}/{self._task_queue_total} 个任务。")
        try:
            runtime_json = self._runtime_json_for_task(next_task, self._task_run_start_step_index)
        except Exception as e:
            self._append_output(f"[UI] skip task_json={next_task} generate runtime json failed: {e}\n")
            self._queue_summaries.append(TaskRunSummary(task_json_name=next_task.name, status="skipped"))
            self._task_queue.pop(0)
            QtCore.QTimer.singleShot(0, self._start_next_task_from_queue)
            return

        started = self._start_run_with_json(runtime_json, label="task_json", clear_output=False)
        if not started:
            self._append_output("[UI] runner busy, retry queued task shortly\n")
            QtCore.QTimer.singleShot(100, self._start_next_task_from_queue)
            return

        self._task_queue.pop(0)
        self._task_queue_index = next_index
        self._append_output(f"\n[UI] start task {self._task_queue_index}/{self._task_queue_total}\n")

    def _load_case(self) -> None:
        fp, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择用例 JSON", str(self.project_root / "cases"), "JSON (*.json)"
        )
        if not fp:
            return
        try:
            m = load_case_json(Path(fp))
            self.model = m
            loaded_log_dir = (self.model.app_log_dir or "").strip()
            if not loaded_log_dir or not Path(loaded_log_dir).exists():
                detected = _auto_detect_crealityscan_log_dir()
                if detected:
                    self.model.app_log_dir = detected

            self._current_task_path = None
            # 回填 UI
            if hasattr(self, "edit_case_id"):
                self.edit_case_id.setText(self.model.case_id)
            if hasattr(self, "edit_case_name"):
                self.edit_case_name.setText(self.model.name)
            self.edit_log_dir.setText(self.model.app_log_dir)
            self._refresh_selected_steps()
            self._apply_step_filter()
        except Exception as e:
            show_error(self, "加载失败", str(e))

    def _new_case(self) -> None:
        # 极简新建：不做“是否保存”提示（YAGNI），后续需要再加。
        self.model = CaseModel(
            case_id="case_001",
            name="新用例",
            app_window_title_contains="CrealityScan",
            app_log_dir=_auto_detect_crealityscan_log_dir(),
            keywords=list(DEFAULT_KEYWORDS),
            steps=[],
        )
        if hasattr(self, "edit_case_id"):
            self.edit_case_id.setText(self.model.case_id)
        if hasattr(self, "edit_case_name"):
            self.edit_case_name.setText(self.model.name)
        self.edit_log_dir.setText(self.model.app_log_dir)
        self._refresh_selected_steps()
        self._apply_step_filter()
        self._current_task_path = None
        self.statusBar().showMessage("已新建用例")

    def _start_run_with_json(self, json_path: Path, *, label: str, clear_output: bool) -> bool:
        self._stop_pending = False
        if clear_output:
            self.text_output.clear()
            if hasattr(self, "table_results"):
                self._clear_results_table()
        if hasattr(self, "tabs"):
            self.tabs.setCurrentWidget(self.text_output)

        self._refresh_device_connection()
        extra_env = {
            "JENS_DEVICE_CAMERA_NAME": self._device_info.get("camera_name", ""),
            "JENS_DEVICE_CAMERA_SN": self._device_info.get("camera_serial_number", ""),
            "JENS_DEVICE_CONNECTION_TYPE": self._device_info.get("camera_connection_type", ""),
            "JENS_DEVICE_FIRMWARE_VERSION": self._device_info.get("camera_firmware_version", ""),
        }
        started = self._runner.start(self.project_root, json_path, extra_env=extra_env)
        if not started:
            self._set_run_ui_state("idle", "运行器忙，请稍后重新运行。")
            self.statusBar().showMessage("运行器忙，稍后重试")
            return False

        self._append_output(f"\n[UI] start {label}={json_path}\n")
        if int(getattr(self, "_task_run_start_step_index", 1) or 1) > 1:
            self._append_output(f"[UI] start_step_index={self._task_run_start_step_index}\n")

        current = max(1, int(self._task_queue_index or 1))
        total = max(1, int(self._task_queue_total or 1))
        self._set_run_ui_state("running", f"正在执行队列第 {current}/{total} 个任务。")
        self.statusBar().showMessage("运行中…")
        return True

    def _run_stress_case(self) -> None:
        """压测模式：选择任务 + exe + 次数，启动压测编排子进程。"""
        if hasattr(self, "act_run") and not self.act_run.isEnabled():
            show_error(self, "无法运行压测", "当前正在运行中，请先停止或等待结束。")
            return
        dlg = StressRunDialog(self.project_root, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        task_path = dlg.selected_task
        exe_path = dlg.exe_path
        rounds = dlg.rounds
        if task_path is None or not task_path.is_file():
            show_error(self, "无法运行压测", "任务文件不存在。")
            return

        self._stop_pending = False
        self._stress_mode = True
        self._stress_task = task_path
        self._stress_exe = exe_path
        self._stress_rounds = rounds

        self.text_output.clear()
        if hasattr(self, "table_results"):
            self._clear_results_table()
        if hasattr(self, "tabs"):
            self.tabs.setCurrentWidget(self.text_output)

        self._refresh_device_connection()
        extra_env = {
            "JENS_DEVICE_CAMERA_NAME": self._device_info.get("camera_name", ""),
            "JENS_DEVICE_CAMERA_SN": self._device_info.get("camera_serial_number", ""),
            "JENS_DEVICE_CONNECTION_TYPE": self._device_info.get("camera_connection_type", ""),
            "JENS_DEVICE_FIRMWARE_VERSION": self._device_info.get("camera_firmware_version", ""),
        }
        stop_file = self._stress_stop_file_path()
        # argv 不含程序本体（runner.start 会按源码/打包态自动补齐入口）。
        argv = [
            "--stress-run",
            "--case",
            str(task_path),
            "--exe",
            exe_path,
            "--rounds",
            str(rounds),
            "--stop-file",
            str(stop_file),
        ]
        started = self._runner.start(self.project_root, task_path, extra_env=extra_env, argv=argv)
        if not started:
            self._stress_mode = False
            self._set_run_ui_state("idle", "运行器忙，请稍后重新运行。")
            self.statusBar().showMessage("运行器忙，稍后重试")
            return
        self._append_output(
            f"\n[UI] start stress task={task_path} exe={exe_path} rounds={rounds}\n"
        )
        self._set_run_ui_state("running", f"压测模式：共 {rounds} 轮，失败/卡死自动杀进程重开。")
        self.statusBar().showMessage(f"压测运行中（{rounds} 轮）…")

    def _run_case(self) -> None:
        # 运行逻辑：按“任务栏”的顺序串行执行（任务栏顺序即队列顺序）
        paths = self._task_paths_in_list_order() if hasattr(self, "list_tasks") else []
        if not paths:
            show_error(self, "无法运行", "任务栏为空：请先新建任务，或从任务库把任务加入队列。")
            return
        self._run_task_paths(paths)

    def _stop_run(self) -> None:
        if self._tool_busy_key is not None:
            page = self._pages.get(self._tool_busy_key)
            stop_run = getattr(page, "stop_run", None)
            if callable(stop_run):
                stop_run()
                self.statusBar().showMessage("已发送工具停止请求", 5000)
            return
        if self._stop_pending:
            return
        self._stop_pending = True

        if self._stress_mode:
            # 压测：优雅停止。写入 stop-file，编排子进程轮询到后
            # 当前轮安全退出 -> 落汇总 -> 自行结束（不在此强杀）。
            if self._stress_stop_file is not None:
                try:
                    self._stress_stop_file.parent.mkdir(parents=True, exist_ok=True)
                    self._stress_stop_file.write_text("stop", encoding="utf-8")
                except OSError as exc:
                    print(f"[UI][WARN] 写入压测停止标志失败：{exc}")
            self._runner.request_stop()
            self._set_run_ui_state("stopping", "已请求压测停止，等待当前轮安全退出。")
            self.statusBar().showMessage("压测停止中（等待当前轮结束）…")
            self._append_output("\n[UI] stress stop requested（等待当前轮安全退出）\n")
            return

        # 停止时清空队列，避免停止后继续跑下一个任务
        self._task_queue = []
        self._task_queue_total = 0
        self._task_queue_index = 0
        self._batch_mode = False
        self._queue_started_at = ""
        self._queue_summaries = []

        self._set_run_ui_state("stopping", "已发送停止请求，正在等待当前步骤安全退出。")
        self.statusBar().showMessage("停止中…")
        self._append_output("\n[UI] stop requested\n")
        self._runner.stop()

    def _append_output(self, text: str) -> None:
        self.text_output.moveCursor(QtGui.QTextCursor.End)
        self.text_output.insertPlainText(text)
        self.text_output.moveCursor(QtGui.QTextCursor.End)

    def _on_run_finished(self, ok: bool, run_dir: str, report: str, reason: str) -> None:
        if self._stress_mode:
            self._on_stress_run_finished(ok, reason)
            return
        # runner 输出解析失败时（常见：编码导致中文路径丢失），兜底取 artifacts 下最新目录
        # 但“停止”场景下可能拿到上一次运行的产物，避免误导则不做兜底推断。
        if reason != "stopped" and (not run_dir or not report):
            infer_dir, infer_report = self._infer_latest_artifact()
            run_dir = run_dir or infer_dir
            report = report or infer_report

        self._last_run_dir = run_dir or ""
        self._last_report = report or ""

        self._append_output(f"\n[UI] finished ok={ok} reason={reason}\n")
        if self._running_task:
            self._append_output(f"[UI] task_json={self._running_task}\n")
        if run_dir:
            self._append_output(f"[UI] run_dir={run_dir}\n")
        if report:
            self._append_output(f"[UI] report={report}\n")
        self._refresh_device_connection()

        if hasattr(self, "act_open_report"):
            self.act_open_report.setEnabled(bool(self._last_report))
            self.btn_open_report_top.setEnabled(bool(self._last_report))
        if hasattr(self, "act_open_run_dir"):
            self.act_open_run_dir.setEnabled(bool(self._last_run_dir))
            self.btn_open_run_dir_top.setEnabled(bool(self._last_run_dir))
        if hasattr(self, "table_results"):
            self._load_results_from_run_dir(self._last_run_dir)
        if hasattr(self, "tabs") and hasattr(self, "table_results"):
            self.tabs.setCurrentWidget(self.table_results)

        current_task_name = self._running_task.name if self._running_task else ""
        current_summary = load_task_run_summary(self._last_run_dir, current_task_name, reason=reason)
        current_summary.report_path = self._last_report or current_summary.report_path
        if current_task_name:
            self._queue_summaries.append(current_summary)
        if reason == "failed" and current_task_name:
            self._notification_dispatcher.send_failure_email(current_summary)
        elif ok and reason != "stopped" and current_task_name:
            self._notification_dispatcher.send_success_email(current_summary)

        # 批量运行：自动启动下一个任务；仅在队列结束/或停止时弹窗
        if self._batch_mode and reason != "stopped":
            if self._task_queue:
                self._append_output("\n[UI] next task...\n")
                QtCore.QTimer.singleShot(0, self._start_next_task_from_queue)
                return
            # 队列已空，结束批量模式
            self._batch_mode = False

        if reason != "stopped" and self._queue_started_at and self._queue_summaries:
            # 队列完成邮件已停用：每个任务按成功/失败单独通知，避免再发重复汇总。
            self._queue_started_at = ""
            self._queue_summaries = []

        if reason == "stopped":
            self._set_run_ui_state("stopped", "运行已停止，已有产物仍可在下方查看。")
            self.statusBar().showMessage("已停止")
        else:
            self._set_run_ui_state(
                "passed" if ok else "failed",
                "运行完成，可查看步骤结果与报告。" if ok else "任务执行失败，请从步骤结果和截图定位原因。",
            )
            self.statusBar().showMessage("运行完成" if ok else "运行失败")

        self._running_task = None

        # 按你的要求：完成后弹窗告诉用户产物目录/报告路径
        RunFinishedDialog(ok=ok, run_dir=self._last_run_dir, report=self._last_report, parent=self, reason=reason).exec_()

    def _on_stress_run_finished(self, ok: bool, reason: str) -> None:
        """压测编排子进程结束后：汇总展示 + 结果通知。"""
        stress_run_dir = getattr(self._runner, "stress_run_dir", "") or ""
        stress_summary = getattr(self._runner, "stress_summary", "") or ""
        if reason != "stopped" and not stress_run_dir:
            # 输出解析失败兜底：取 artifacts 下最新“_压测_”目录
            stress_run_dir = self._infer_latest_stress_artifact()

        self._last_run_dir = stress_run_dir or ""
        self._last_report = stress_summary or ""
        self._append_output(f"\n[UI] stress finished ok={ok} reason={reason}\n")
        if stress_run_dir:
            self._append_output(f"[UI] stress_run_dir={stress_run_dir}\n")
        if stress_summary:
            self._append_output(f"[UI] stress_summary={stress_summary}\n")

        if hasattr(self, "act_open_report"):
            self.act_open_report.setEnabled(bool(stress_summary))
            self.btn_open_report_top.setEnabled(bool(stress_summary))
        if hasattr(self, "act_open_run_dir"):
            self.act_open_run_dir.setEnabled(bool(stress_run_dir))
            self.btn_open_run_dir_top.setEnabled(bool(stress_run_dir))

        task_name = self._stress_task.stem if self._stress_task else ""
        task_label = task_name or "压测任务"
        summary = TaskRunSummary(
            task_json_name=task_label,
            status="passed" if ok and reason != "stopped" else ("failed" if reason != "stopped" else "stopped"),
            report_path=stress_summary,
            run_dir=stress_run_dir,
        )
        if reason != "stopped":
            self._notification_dispatcher.send_stress_summary_email(summary)

        if reason == "stopped":
            self._set_run_ui_state("stopped", "压测已停止，已完成轮次的产物仍可查看。")
            self.statusBar().showMessage("压测已停止")
        else:
            self._set_run_ui_state(
                "passed" if ok else "failed",
                "压测完成，可查看压测汇总报告。" if ok else "压测存在失败轮次，请查看压测汇总报告。",
            )
            self.statusBar().showMessage("压测完成" if ok else "压测完成（存在失败）")

        self._stress_mode = False
        self._stress_task = None
        self._stress_exe = ""
        self._stress_rounds = 0
        if self._stress_stop_file is not None:
            try:
                self._stress_stop_file.unlink(missing_ok=True)
            except OSError:
                pass
            self._stress_stop_file = None

        RunFinishedDialog(
            ok=ok,
            run_dir=stress_run_dir,
            report=stress_summary,
            parent=self,
            reason=reason,
        ).exec_()

    def _stress_stop_file_path(self) -> Path:
        """生成本次压测唯一的跨进程停止标志文件路径（%LOCALAPPDATA%\\Jens\\压测模式\\）。"""
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Jens" / "压测模式"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"stop_{uuid.uuid4().hex}.flag"

    def _infer_latest_stress_artifact(self) -> str:
        base = self.project_root / "artifacts"
        if not base.exists():
            return ""
        dirs = [p for p in base.iterdir() if p.is_dir() and "压测" in p.name and p.name != "_airtest_cli_log"]
        if not dirs:
            return ""
        latest = max(dirs, key=lambda p: p.stat().st_mtime)
        return str(latest)

    def _infer_latest_artifact(self) -> tuple[str, str]:
        """
        从 artifacts 目录推断最新一次运行产物目录与报告路径。
        """
        base = self.project_root / "artifacts"
        if not base.exists():
            return "", ""
        dirs = [p for p in base.iterdir() if p.is_dir() and p.name != "_airtest_cli_log"]
        if not dirs:
            return "", ""
        latest = max(dirs, key=lambda p: p.stat().st_mtime)
        report = latest / "report.html"
        return str(latest), (str(report) if report.exists() else "")

    def _clear_results_table(self) -> None:
        self.table_results.setRowCount(0)
        self.table_results.clearSpans()

    def _format_step_metrics(self, step_result: dict) -> str:
        extra = step_result.get("extra") if isinstance(step_result.get("extra"), dict) else {}
        if not extra:
            return ""

        parts: list[str] = []
        avg_fps = extra.get("avg_fps")
        if avg_fps not in (None, ""):
            parts.append(f"avg_fps={avg_fps}")

        peak_fps = extra.get("peak_fps")
        if peak_fps not in (None, ""):
            parts.append(f"peak_fps={peak_fps}")

        min_fps = extra.get("min_fps")
        if min_fps not in (None, ""):
            parts.append(f"min_fps={min_fps}")

        peak_cpu = extra.get("peak_cpu_percent")
        if peak_cpu not in (None, ""):
            parts.append(f"cpu_peak={peak_cpu}%")

        peak_memory = extra.get("peak_memory_percent")
        if peak_memory not in (None, ""):
            parts.append(f"mem_peak={peak_memory}%")

        peak_wifi = extra.get("peak_wifi_rate_kbps")
        if peak_wifi not in (None, ""):
            parts.append(f"wifi_peak={peak_wifi}kbps")

        stop_click_frame = extra.get("stop_click_frame")
        if stop_click_frame not in (None, ""):
            parts.append(f"stop_frame={stop_click_frame}")

        elapsed_sec = extra.get("scan_elapsed_sec")
        if elapsed_sec not in (None, ""):
            parts.append(f"elapsed={elapsed_sec}s")

        max_frame = extra.get("max_frame")
        if max_frame not in (None, "") and stop_click_frame in (None, ""):
            parts.append(f"max_frame={max_frame}")

        fps_seconds_count = extra.get("fps_seconds_count")
        if fps_seconds_count not in (None, ""):
            parts.append(f"fps_secs={fps_seconds_count}")

        return " | ".join(parts)

    def _load_results_from_run_dir(self, run_dir: str) -> None:
        if not run_dir:
            return
        try:
            result_path = Path(run_dir) / "result.json"
            if not result_path.exists():
                return
            raw = json.loads(result_path.read_text(encoding="utf-8"))
            step_results = raw.get("step_results") if isinstance(raw, dict) else None
            if not isinstance(step_results, list):
                return
            case = raw.get("case") if isinstance(raw, dict) else None
        except Exception:
            return

        case_name = ""
        if isinstance(case, dict):
            case_name = str(case.get("name") or case.get("case_id") or "").strip()
        if not case_name and self._running_task:
            case_name = self._running_task.stem
        task_label = case_name or Path(run_dir).name
        section_prefix = (
            f"任务 {self._task_queue_index}/{self._task_queue_total}"
            if self._batch_mode or self._task_queue_total > 1
            else "任务"
        )

        base_row = self.table_results.rowCount()
        total_rows = base_row + 1 + len(step_results)
        self.table_results.setRowCount(total_rows)
        self.table_results.setSpan(base_row, 0, 1, self.table_results.columnCount())
        section_item = QtWidgets.QTableWidgetItem(f"{section_prefix}: {task_label}")
        section_item.setData(QtCore.Qt.UserRole, "section")
        section_item.setForeground(QtGui.QBrush(QtGui.QColor("#1e3a8a")))
        section_item.setBackground(QtGui.QBrush(QtGui.QColor("#dbeafe")))
        section_font = section_item.font()
        section_font.setBold(True)
        section_item.setFont(section_font)
        self.table_results.setItem(base_row, 0, section_item)
        self.table_results.setRowHeight(base_row, 30)

        for i, r in enumerate(step_results, start=1):
            if not isinstance(r, dict):
                continue
            screenshot = ""
            if r.get("screenshot"):
                screenshot = str(r.get("screenshot") or "")
            else:
                extra = r.get("extra") if isinstance(r.get("extra"), dict) else {}
                screenshot = str(extra.get("snapshot") or "")
            metrics = self._format_step_metrics(r)

            vals = [
                str(i),
                str(r.get("id") or ""),
                str(r.get("version") or ""),
                str(r.get("name") or ""),
                {"passed": "通过", "failed": "失败", "skipped": "跳过"}.get(
                    str(r.get("status") or "").lower(), str(r.get("status") or "")
                ),
                str(r.get("duration_sec") or ""),
                str(r.get("attempt") or ""),
                metrics,
                "查看截图" if screenshot else "",
            ]
            row = base_row + i
            for col, v in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(v)
                if col == 8 and screenshot:
                    item.setData(QtCore.Qt.UserRole, screenshot)
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#2358aa")))
                if col == 4:  # Status
                    status = str(r.get("status") or "").lower()
                    if status == "passed":
                        item.setForeground(QtGui.QBrush(QtGui.QColor("#166534")))
                    elif status == "failed":
                        item.setForeground(QtGui.QBrush(QtGui.QColor("#b91c1c")))
                    elif status == "skipped":
                        item.setForeground(QtGui.QBrush(QtGui.QColor("#64748b")))
                self.table_results.setItem(row, col, item)

    def _open_result_artifact(self, row: int, col: int) -> None:
        try:
            section_item = self.table_results.item(row, 0)
            if section_item and section_item.data(QtCore.Qt.UserRole) == "section":
                return
            shot_item = self.table_results.item(row, 8)
            shot = str(shot_item.data(QtCore.Qt.UserRole) or "").strip() if shot_item else ""
            if shot and Path(shot).exists():
                os.startfile(shot)  # type: ignore[attr-defined]
                return
        except Exception:
            pass
        if self._last_report and Path(self._last_report).exists():
            try:
                os.startfile(self._last_report)  # type: ignore[attr-defined]
            except Exception:
                pass

    def _open_last_report(self) -> None:
        if self._last_report and Path(self._last_report).exists():
            os.startfile(self._last_report)  # type: ignore[attr-defined]
        else:
            self.statusBar().showMessage("暂无可打开的报告（请先运行一次）")

    def _open_last_run_dir(self) -> None:
        if self._last_run_dir and Path(self._last_run_dir).exists():
            os.startfile(self._last_run_dir)  # type: ignore[attr-defined]
        else:
            self.statusBar().showMessage("暂无可打开的产物目录（请先运行一次）")


def main() -> None:
    project_root = get_app_root()
    app = QtWidgets.QApplication([])
    icon_path = _resolve_app_icon(project_root)
    if icon_path:
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))
    w = MainWindow(project_root)
    if not w.ensure_notification_email():
        return
    w.show()
    app.exec_()


if __name__ == "__main__":
    main()
