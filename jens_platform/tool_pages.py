from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Callable, Optional

from PyQt5 import QtCore, QtWidgets  # type: ignore


CALIBRATION_TOOL_NAME = "标定分数查看工具"
FIRMWARE_TOOL_NAME = "固件升级工具"


class ToolPageLoadError(RuntimeError):
    pass


def _resolve_tool_root(project_root: Path, tool_name: str, env_name: str) -> Path:
    configured = os.getenv(env_name, "").strip()
    candidates = [Path(configured).expanduser()] if configured else []
    for parent in (project_root, *project_root.parents):
        candidates.append(parent / "工具" / tool_name)
        candidates.append(parent / tool_name)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    expected = project_root / "工具" / tool_name
    raise ToolPageLoadError(f"未找到工具目录：{expected}")


def _load_module(source_path: Path, namespace: str) -> ModuleType:
    if not source_path.is_file():
        raise ToolPageLoadError(f"未找到工具入口：{source_path}")
    digest = hashlib.sha1(str(source_path).encode("utf-8")).hexdigest()[:12]
    module_name = f"_jens_{namespace}_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ToolPageLoadError(f"无法加载工具入口：{source_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except (AttributeError, ImportError, OSError, RuntimeError, SyntaxError, TypeError, ValueError) as exc:
        sys.modules.pop(module_name, None)
        raise ToolPageLoadError(f"加载工具失败：{exc}") from exc
    return module


class PostprocessComparePage(QtWidgets.QWidget):
    busyChanged = QtCore.pyqtSignal(bool)
    statusMessage = QtCore.pyqtSignal(str)

    def __init__(self, project_root: Path, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        try:
            from jens_platform.tools.postprocess_compare.qt_app import CompareWindow
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ToolPageLoadError(f"后处理对比工具加载失败：{exc}") from exc

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        try:
            self.window = CompareWindow(project_root=project_root)
        except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ToolPageLoadError(f"后处理对比窗口初始化失败：{exc}") from exc
        self.window.setParent(self)
        self.window.setWindowFlags(QtCore.Qt.Widget)
        self.window.setMinimumSize(0, 0)
        duplicate_sidebar = self.window.findChild(QtWidgets.QWidget, "sidebar")
        if duplicate_sidebar is not None:
            duplicate_sidebar.hide()
        page_title = self.window.findChild(QtWidgets.QLabel, "pageTitle")
        if page_title is not None:
            page_title.setText("后处理对比")
        layout.addWidget(self.window)

        process = getattr(self.window, "_process", None)
        stop_run = getattr(self.window, "stop_run", None)
        if not isinstance(process, QtCore.QProcess) or not callable(stop_run):
            self.window.deleteLater()
            raise ToolPageLoadError("后处理对比工具缺少运行状态或停止接口")
        self._process = process
        self._stop_run = stop_run
        self._process.stateChanged.connect(self._process_state_changed)

    def _process_state_changed(self, state: QtCore.QProcess.ProcessState) -> None:
        busy = state != QtCore.QProcess.NotRunning
        self.busyChanged.emit(busy)
        self.statusMessage.emit("后处理对比任务正在运行" if busy else "后处理对比工具就绪")

    def is_busy(self) -> bool:
        return self._process.state() != QtCore.QProcess.NotRunning

    def stop_run(self) -> None:
        self._stop_run()

    def activate(self) -> None:
        self.window.setFocus(QtCore.Qt.OtherFocusReason)

    def prepare_close(self) -> bool:
        if not self.is_busy():
            return True
        return bool(self.window.close())


class CalibrationScorePage(QtWidgets.QWidget):
    statusMessage = QtCore.pyqtSignal(str)

    FIELD_LABELS = (
        ("设备", "device_name"),
        ("SN", "sn_code"),
        ("标定板", "calibration_board"),
        ("固件", "firmware_version"),
        ("日志", "log_file"),
    )

    def __init__(self, project_root: Path, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        tool_root = _resolve_tool_root(
            project_root,
            CALIBRATION_TOOL_NAME,
            "JENS_CALIBRATION_SCORE_ROOT",
        )
        parser_module = _load_module(tool_root / "parser.py", "calibration_score_parser")
        self._get_latest_log_file: Optional[Callable[[], Optional[Path]]] = getattr(
            parser_module,
            "get_latest_log_file",
            None,
        )
        self._parse_log_file: Optional[Callable[[Path], dict]] = getattr(
            parser_module,
            "parse_log_file",
            None,
        )
        if not callable(self._get_latest_log_file) or not callable(self._parse_log_file):
            raise ToolPageLoadError("标定分数工具的解析接口不完整")

        self._field_values: dict[str, QtWidgets.QLineEdit] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QtWidgets.QFrame()
        top_bar.setObjectName("topBar")
        top = QtWidgets.QHBoxLayout(top_bar)
        top.setContentsMargins(22, 12, 22, 12)
        heading = QtWidgets.QVBoxLayout()
        heading.setSpacing(2)
        title = QtWidgets.QLabel("标定分数查看")
        title.setObjectName("pageTitle")
        subtitle = QtWidgets.QLabel("读取 CrealityScan 最新日志中的设备与标定结果")
        subtitle.setObjectName("pageSubtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        top.addLayout(heading, 1)
        self.status_label = QtWidgets.QLabel("等待读取")
        self.status_label.setObjectName("statusWarn")
        top.addWidget(self.status_label)
        self.refresh_button = QtWidgets.QPushButton("刷新")
        self.refresh_button.setObjectName("primaryBtn")
        self.refresh_button.clicked.connect(self.refresh_data)
        top.addWidget(self.refresh_button)
        root.addWidget(top_bar)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(22, 20, 22, 22)
        content_layout.setSpacing(12)

        score_panel = QtWidgets.QFrame()
        score_panel.setObjectName("panel")
        score_layout = QtWidgets.QVBoxLayout(score_panel)
        score_layout.setContentsMargins(18, 15, 18, 15)
        score_layout.setSpacing(5)
        score_caption = QtWidgets.QLabel("标定分数")
        score_caption.setObjectName("fieldLabel")
        score_layout.addWidget(score_caption)
        score_row = QtWidgets.QHBoxLayout()
        self.score_value = QtWidgets.QLabel("--")
        self.score_value.setObjectName("calibrationScore")
        self.score_value.setProperty("state", "empty")
        self.score_value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        score_row.addWidget(self.score_value, 1)
        self.copy_button = QtWidgets.QPushButton("复制分数")
        self.copy_button.clicked.connect(self._copy_score)
        self.copy_button.setEnabled(False)
        score_row.addWidget(self.copy_button)
        score_layout.addLayout(score_row)
        content_layout.addWidget(score_panel)

        info_panel = QtWidgets.QFrame()
        info_panel.setObjectName("panel")
        info_layout = QtWidgets.QGridLayout(info_panel)
        info_layout.setContentsMargins(18, 16, 18, 16)
        info_layout.setHorizontalSpacing(14)
        info_layout.setVerticalSpacing(10)
        info_title = QtWidgets.QLabel("设备与日志信息")
        info_title.setObjectName("sectionTitle")
        info_layout.addWidget(info_title, 0, 0, 1, 2)
        for row, (label_text, key) in enumerate(self.FIELD_LABELS, start=1):
            label = QtWidgets.QLabel(label_text)
            label.setObjectName("fieldLabel")
            value = QtWidgets.QLineEdit("N/A")
            value.setReadOnly(True)
            self._field_values[key] = value
            info_layout.addWidget(label, row, 0)
            info_layout.addWidget(value, row, 1)
        info_layout.setColumnStretch(1, 1)
        content_layout.addWidget(info_panel)

        self.refresh_time = QtWidgets.QLabel("尚未刷新")
        self.refresh_time.setObjectName("mutedText")
        content_layout.addWidget(self.refresh_time)
        content_layout.addStretch(1)
        root.addWidget(content, 1)

    def activate(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self.refresh_button.setEnabled(False)
        self._set_status("读取中", "statusWarn")
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        try:
            log_file = self._get_latest_log_file()
            if log_file is None:
                self._show_error("未找到 CrealityScan 日志文件")
                return
            data = self._parse_log_file(log_file)
        except (OSError, RuntimeError, TypeError, UnicodeError, ValueError) as exc:
            self._show_error(f"读取失败：{exc}")
            return
        finally:
            self.refresh_button.setEnabled(True)

        for key, value_widget in self._field_values.items():
            value_widget.setText(str(data.get(key, "N/A")))
        score = str(data.get("calibration_score", "N/A"))
        has_score = score not in {"", "N/A"}
        self.score_value.setText(score if has_score else "--")
        self.score_value.setProperty("state", "ready" if has_score else "empty")
        self.score_value.style().unpolish(self.score_value)
        self.score_value.style().polish(self.score_value)
        self.copy_button.setEnabled(has_score)
        now = datetime.now().strftime("%H:%M:%S")
        self.refresh_time.setText(f"上次刷新 {now}")
        if has_score:
            self._set_status("已读取", "statusGood")
            self.statusMessage.emit("标定分数已刷新")
        else:
            self._set_status("无标定分数", "statusWarn")
            self.refresh_time.setText(f"上次刷新 {now} · 最新日志中未解析到标定分数")
            self.statusMessage.emit("最新日志中未解析到标定分数")

    def _show_error(self, message: str) -> None:
        for value_widget in self._field_values.values():
            value_widget.setText("N/A")
        self.score_value.setText("--")
        self.score_value.setProperty("state", "error")
        self.score_value.style().unpolish(self.score_value)
        self.score_value.style().polish(self.score_value)
        self.copy_button.setEnabled(False)
        self.refresh_time.setText(f"上次尝试 {datetime.now().strftime('%H:%M:%S')} · {message}")
        self._set_status("未读取", "statusBad")
        self.statusMessage.emit(message)

    def _copy_score(self) -> None:
        score = self.score_value.text().strip()
        if score and score != "--":
            QtWidgets.QApplication.clipboard().setText(score)
            self.statusMessage.emit("标定分数已复制")

    def _set_status(self, text: str, object_name: str) -> None:
        self.status_label.setText(text)
        self.status_label.setObjectName(object_name)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)


class FirmwareUpgradePage(QtWidgets.QWidget):
    busyChanged = QtCore.pyqtSignal(bool)
    statusMessage = QtCore.pyqtSignal(str)
    runFinished = QtCore.pyqtSignal(bool, str, bool)

    MODE_DATA = (
        ("仅开流", "stream_only"),
        ("仅升级", "upgrade"),
        ("仅降级", "downgrade"),
        ("升级 ↔ 降级循环", "cycle"),
    )
    PROGRESS_PREFIX = "[JENS_FIRMWARE_PROGRESS] "
    RESULT_PREFIX = "[JENS_FIRMWARE_RESULT] "

    def __init__(self, project_root: Path, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.project_root = project_root
        self.tool_root = _resolve_tool_root(
            project_root,
            FIRMWARE_TOOL_NAME,
            "JENS_FIRMWARE_UPGRADE_ROOT",
        )
        entry = self.tool_root / "testcases" / "test_firmware_cycle.py"
        if not entry.is_file():
            raise ToolPageLoadError(f"未找到固件测试入口：{entry}")

        self._process = QtCore.QProcess(self)
        self._process.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read_process_output)
        self._process.stateChanged.connect(self._process_state_changed)
        self._process.errorOccurred.connect(self._process_error)
        self._process.finished.connect(self._process_finished)
        self._output_buffer = ""
        self._result: dict = {}
        self._report_path = ""
        self._stop_file: Optional[Path] = None
        self._config_controls: list[QtWidgets.QWidget] = []
        self._build_ui()
        self._load_settings()
        self._refresh_mode_controls()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QtWidgets.QFrame()
        top_bar.setObjectName("topBar")
        top = QtWidgets.QHBoxLayout(top_bar)
        top.setContentsMargins(22, 12, 22, 12)
        heading = QtWidgets.QVBoxLayout()
        heading.setSpacing(2)
        title = QtWidgets.QLabel("固件升级测试")
        title.setObjectName("pageTitle")
        subtitle = QtWidgets.QLabel("隔离执行升级、降级与开流验证，运行期间锁定上下文")
        subtitle.setObjectName("pageSubtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        top.addLayout(heading, 1)
        self.status_label = QtWidgets.QLabel("就绪")
        self.status_label.setObjectName("statusGood")
        top.addWidget(self.status_label)
        self.open_report_button = QtWidgets.QPushButton("打开报告")
        self.open_report_button.setEnabled(False)
        self.open_report_button.clicked.connect(self._open_report)
        top.addWidget(self.open_report_button)
        root.addWidget(top_bar)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setContentsMargins(18, 16, 18, 16)
        root.addWidget(splitter, 1)

        config_panel = QtWidgets.QFrame()
        config_panel.setObjectName("panel")
        config_layout = QtWidgets.QVBoxLayout(config_panel)
        config_layout.setContentsMargins(18, 16, 18, 16)
        config_layout.setSpacing(10)
        config_title = QtWidgets.QLabel("测试配置")
        config_title.setObjectName("sectionTitle")
        config_layout.addWidget(config_title)

        self.mode_combo = QtWidgets.QComboBox()
        for text, data in self.MODE_DATA:
            self.mode_combo.addItem(text, data)
        self.mode_combo.setCurrentIndex(1)
        self.mode_combo.currentIndexChanged.connect(self._refresh_mode_controls)
        config_layout.addWidget(self._field_with_label("测试模式", self.mode_combo))

        self.connection_combo = QtWidgets.QComboBox()
        self.connection_combo.addItem("USB", "usb")
        self.connection_combo.addItem("WiFi", "wifi")
        config_layout.addWidget(self._field_with_label("连接方式", self.connection_combo))

        self.with_stream_check = QtWidgets.QCheckBox("包含开流验证")
        self.with_stream_check.setChecked(True)
        self.with_stream_check.setToolTip("取消后只执行固件升级或降级，不执行前后开流验证。")
        config_layout.addWidget(self.with_stream_check)

        self.upgrade_edit, self.upgrade_button, self.upgrade_row = self._path_row(
            "升级固件",
            "选择升级固件包",
            self._browse_upgrade,
        )
        config_layout.addWidget(self.upgrade_row)
        self.downgrade_edit, self.downgrade_button, self.downgrade_row = self._path_row(
            "降级固件",
            "选择降级固件包",
            self._browse_downgrade,
        )
        config_layout.addWidget(self.downgrade_row)
        self.log_dir_edit, self.log_dir_button, self.log_dir_row = self._path_row(
            "日志目录",
            "可选：CrealityScan 日志目录",
            self._browse_log_dir,
        )
        config_layout.addWidget(self.log_dir_row)

        cycle_row = QtWidgets.QWidget()
        cycle_layout = QtWidgets.QHBoxLayout(cycle_row)
        cycle_layout.setContentsMargins(0, 0, 0, 0)
        cycle_layout.setSpacing(8)
        cycle_label = QtWidgets.QLabel("循环次数")
        cycle_label.setObjectName("fieldLabel")
        self.cycle_count = QtWidgets.QSpinBox()
        self.cycle_count.setRange(1, 999)
        self.cycle_count.setValue(1)
        self.cycle_direction = QtWidgets.QComboBox()
        self.cycle_direction.addItem("先升级后降级", "upgrade_first")
        self.cycle_direction.addItem("先降级后升级", "downgrade_first")
        cycle_layout.addWidget(cycle_label)
        cycle_layout.addWidget(self.cycle_count)
        cycle_layout.addWidget(self.cycle_direction, 1)
        config_layout.addWidget(cycle_row)
        self.cycle_row = cycle_row

        safety = QtWidgets.QLabel(
            "停止请求采用安全协作方式：当前固件操作完成后才会停止，不会强制终止升级进程。"
        )
        safety.setObjectName("statusWarn")
        safety.setWordWrap(True)
        config_layout.addWidget(safety)
        config_layout.addStretch(1)

        button_row = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("开始测试")
        self.start_button.setObjectName("primaryBtn")
        self.start_button.clicked.connect(self.start_run)
        self.stop_button = QtWidgets.QPushButton("安全停止")
        self.stop_button.setObjectName("dangerBtn")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_run)
        button_row.addWidget(self.start_button, 1)
        button_row.addWidget(self.stop_button)
        config_layout.addLayout(button_row)

        self._config_controls = [
            self.mode_combo,
            self.connection_combo,
            self.with_stream_check,
            self.upgrade_edit,
            self.upgrade_button,
            self.downgrade_edit,
            self.downgrade_button,
            self.log_dir_edit,
            self.log_dir_button,
            self.cycle_count,
            self.cycle_direction,
        ]
        splitter.addWidget(config_panel)

        log_panel = QtWidgets.QFrame()
        log_panel.setObjectName("panel")
        log_layout = QtWidgets.QVBoxLayout(log_panel)
        log_layout.setContentsMargins(16, 16, 16, 16)
        log_layout.setSpacing(9)
        log_title = QtWidgets.QLabel("运行日志")
        log_title.setObjectName("sectionTitle")
        log_layout.addWidget(log_title)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        log_layout.addWidget(self.progress)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setObjectName("outputBox")
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.log_view.setPlaceholderText("固件测试启动后将在这里显示实时日志。")
        log_layout.addWidget(self.log_view, 1)
        splitter.addWidget(log_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([560, 520])

    @staticmethod
    def _field_with_label(text: str, field: QtWidgets.QWidget) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QtWidgets.QLabel(text)
        label.setObjectName("fieldLabel")
        label.setFixedWidth(72)
        layout.addWidget(label)
        layout.addWidget(field, 1)
        return row

    def _path_row(
        self,
        label_text: str,
        placeholder: str,
        handler,
    ) -> tuple[QtWidgets.QLineEdit, QtWidgets.QPushButton, QtWidgets.QWidget]:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        label = QtWidgets.QLabel(label_text)
        label.setObjectName("fieldLabel")
        label.setFixedWidth(72)
        edit = QtWidgets.QLineEdit()
        edit.setPlaceholderText(placeholder)
        button = QtWidgets.QPushButton("选择…")
        button.clicked.connect(handler)
        layout.addWidget(label)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return edit, button, row

    def _refresh_mode_controls(self) -> None:
        mode = self.mode_combo.currentData()
        self.upgrade_row.setEnabled(mode in {"upgrade", "cycle"})
        self.downgrade_row.setEnabled(mode in {"downgrade", "cycle"})
        self.cycle_row.setEnabled(mode == "cycle")
        if mode == "stream_only":
            self.with_stream_check.setChecked(True)
            self.with_stream_check.setEnabled(False)
        elif self._process.state() == QtCore.QProcess.NotRunning:
            self.with_stream_check.setEnabled(True)

    def _browse_upgrade(self) -> None:
        self._browse_firmware(self.upgrade_edit, "选择升级固件")

    def _browse_downgrade(self) -> None:
        self._browse_firmware(self.downgrade_edit, "选择降级固件")

    def _browse_firmware(self, edit: QtWidgets.QLineEdit, title: str) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            title,
            edit.text().strip() or str(self.tool_root),
            "固件文件 (*.zip *.bin);;所有文件 (*.*)",
        )
        if path:
            edit.setText(path)

    def _browse_log_dir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "选择 CrealityScan 日志目录",
            self.log_dir_edit.text().strip() or str(Path.home()),
        )
        if path:
            self.log_dir_edit.setText(path)

    def _load_settings(self) -> None:
        settings_path = self.tool_root / "settings.json"
        settings: dict = {}
        try:
            if settings_path.is_file():
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError):
            settings = {}
        log_dir = str(settings.get("log_dir") or "").strip()
        if not log_dir:
            default_logs = Path.home() / "AppData" / "Local" / "Creality" / "CrealityScan" / "Logs"
            log_dir = str(default_logs) if default_logs.exists() else ""
        self.log_dir_edit.setText(log_dir)
        self.log_dir_edit.setCursorPosition(0)
        connection = str(settings.get("connection_mode") or "usb")
        index = self.connection_combo.findData(connection)
        self.connection_combo.setCurrentIndex(index if index >= 0 else 0)

    def _save_settings(self) -> None:
        settings_path = self.tool_root / "settings.json"
        settings: dict = {}
        try:
            if settings_path.is_file():
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["log_dir"] = self.log_dir_edit.text().strip()
            settings["connection_mode"] = str(self.connection_combo.currentData())
            settings_path.write_text(
                json.dumps(settings, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            self.statusMessage.emit(f"固件工具设置未保存：{exc}")

    def _validation_error(self) -> str:
        mode = str(self.mode_combo.currentData())
        required: list[tuple[str, str]] = []
        if mode in {"upgrade", "cycle"}:
            required.append(("升级固件", self.upgrade_edit.text().strip()))
        if mode in {"downgrade", "cycle"}:
            required.append(("降级固件", self.downgrade_edit.text().strip()))
        for label, value in required:
            if not value:
                return f"请选择{label}文件。"
            if not Path(value).is_file():
                return f"{label}文件不存在：{value}"
        log_dir = self.log_dir_edit.text().strip()
        if log_dir and not Path(log_dir).is_dir():
            return f"日志目录不存在：{log_dir}"
        return ""

    def _runner_command(self) -> tuple[str, list[str]]:
        common_args = self._build_runner_args()
        if getattr(sys, "frozen", False):
            return sys.executable, ["--firmware-tool-runner", *common_args]
        runner = Path(__file__).with_name("firmware_tool_runner.py")
        return sys.executable, [str(runner), *common_args]

    def _build_runner_args(self) -> list[str]:
        if self._stop_file is None:
            raise ToolPageLoadError("固件停止信号尚未初始化")
        args = [
            "--tool-root",
            str(self.tool_root),
            "--mode",
            str(self.mode_combo.currentData()),
            "--upgrade-path",
            self.upgrade_edit.text().strip(),
            "--downgrade-path",
            self.downgrade_edit.text().strip(),
            "--cycle-count",
            str(self.cycle_count.value()),
            "--cycle-start",
            str(self.cycle_direction.currentData()),
            "--log-dir",
            self.log_dir_edit.text().strip(),
            "--connection-mode",
            str(self.connection_combo.currentData()),
            "--stop-file",
            str(self._stop_file),
        ]
        if not self.with_stream_check.isChecked():
            args.append("--without-stream")
        return args

    def start_run(self) -> None:
        error = self._validation_error()
        if error:
            QtWidgets.QMessageBox.warning(self, "配置不完整", error)
            return
        if self._process.state() != QtCore.QProcess.NotRunning:
            return

        self._save_settings()
        self._stop_file = Path(tempfile.gettempdir()) / f"jens_firmware_{uuid.uuid4().hex}.stop"
        try:
            self._stop_file.unlink(missing_ok=True)
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "无法启动", f"无法初始化停止信号：{exc}")
            return

        self._output_buffer = ""
        self._result = {}
        self._report_path = ""
        self.log_view.clear()
        self.open_report_button.setEnabled(False)
        mode = str(self.mode_combo.currentData())
        if mode == "cycle":
            self.progress.setRange(0, self.cycle_count.value())
            self.progress.setValue(0)
        else:
            self.progress.setRange(0, 0)

        program, args = self._runner_command()
        environment = QtCore.QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUTF8", "1")
        self._process.setProcessEnvironment(environment)
        self._process.setWorkingDirectory(str(self.tool_root))
        self._set_status("启动中", "statusWarn")
        self._process.start(program, args)

    def stop_run(self) -> None:
        if self._process.state() == QtCore.QProcess.NotRunning or self._stop_file is None:
            return
        try:
            self._stop_file.write_text("stop", encoding="utf-8")
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "停止请求失败", str(exc))
            return
        self.stop_button.setEnabled(False)
        self._set_status("等待安全停止", "statusWarn")
        self._append_log("[UI] 已发送安全停止请求，等待当前固件步骤结束。")
        self.statusMessage.emit("固件任务正在等待安全停止")

    def _process_state_changed(self, state: QtCore.QProcess.ProcessState) -> None:
        busy = state != QtCore.QProcess.NotRunning
        for control in self._config_controls:
            control.setEnabled(not busy)
        self.start_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        if not busy:
            self._refresh_mode_controls()
        self.busyChanged.emit(busy)
        if busy:
            self._set_status("运行中", "statusWarn")
            self.statusMessage.emit("固件升级测试正在运行")

    def _process_error(self, error: QtCore.QProcess.ProcessError) -> None:
        if error == QtCore.QProcess.FailedToStart:
            self._set_status("启动失败", "statusBad")
            self._append_log("[ERROR] 无法启动固件测试执行器。")

    def _read_process_output(self) -> None:
        data = bytes(self._process.readAllStandardOutput())
        if not data:
            return
        self._output_buffer += data.decode("utf-8", errors="replace")
        while "\n" in self._output_buffer:
            line, self._output_buffer = self._output_buffer.split("\n", 1)
            self._handle_output_line(line.rstrip("\r"))

    def _handle_output_line(self, line: str) -> None:
        if line.startswith(self.PROGRESS_PREFIX):
            try:
                payload = json.loads(line[len(self.PROGRESS_PREFIX):])
                total = max(1, int(payload.get("total", 1)))
                current = min(total, max(0, int(payload.get("current", 0))))
                self.progress.setRange(0, total)
                self.progress.setValue(current)
                self._set_status(f"运行中 {current}/{total}", "statusWarn")
            except (json.JSONDecodeError, TypeError, ValueError):
                self._append_log(line)
            return
        if line.startswith(self.RESULT_PREFIX):
            try:
                self._result = json.loads(line[len(self.RESULT_PREFIX):])
            except (json.JSONDecodeError, TypeError):
                self._result = {"success": False, "error": "无法解析执行结果"}
            return
        self._append_log(line)

    def _process_finished(self, exit_code: int, _exit_status: QtCore.QProcess.ExitStatus) -> None:
        self._read_process_output()
        if self._output_buffer:
            self._handle_output_line(self._output_buffer.rstrip("\r"))
            self._output_buffer = ""
        self.progress.setRange(0, 1)
        stopped = bool(self._result.get("stopped"))
        success = bool(self._result.get("success")) and exit_code == 0
        self._report_path = str(self._result.get("report_path") or "")
        self.open_report_button.setEnabled(bool(self._report_path and Path(self._report_path).is_file()))
        if stopped:
            self._set_status("已安全停止", "statusWarn")
            self.statusMessage.emit("固件任务已安全停止")
        elif success:
            self.progress.setValue(1)
            self._set_status("测试通过", "statusGood")
            self.statusMessage.emit("固件升级测试通过")
        else:
            self._set_status("测试失败", "statusBad")
            error = str(self._result.get("error") or "请查看运行日志")
            self.statusMessage.emit(f"固件升级测试失败：{error}")
        self.runFinished.emit(success, self._report_path, stopped)
        self._cleanup_stop_file()

    def _append_log(self, text: str) -> None:
        if not text:
            return
        self.log_view.appendPlainText(text)
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _open_report(self) -> None:
        report = Path(self._report_path)
        if not report.is_file():
            QtWidgets.QMessageBox.warning(self, "无法打开报告", f"报告不存在：{report}")
            return
        try:
            os.startfile(str(report))
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "无法打开报告", str(exc))

    def _set_status(self, text: str, object_name: str) -> None:
        self.status_label.setText(text)
        self.status_label.setObjectName(object_name)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _cleanup_stop_file(self) -> None:
        if self._stop_file is None:
            return
        try:
            self._stop_file.unlink(missing_ok=True)
        except OSError:
            pass

    def prepare_close(self) -> bool:
        if self._process.state() == QtCore.QProcess.NotRunning:
            self._cleanup_stop_file()
            return True
        QtWidgets.QMessageBox.warning(
            self,
            "固件任务仍在运行",
            "为避免中断固件操作，当前不能退出平台。请先点击“安全停止”，并等待任务结束。",
        )
        return False


class ToolErrorPage(QtWidgets.QWidget):
    retryRequested = QtCore.pyqtSignal()

    def __init__(self, title: str, detail: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.addStretch(1)
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")
        panel.setMaximumWidth(680)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        heading = QtWidgets.QLabel(title)
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        message = QtWidgets.QLabel(detail)
        message.setObjectName("mutedText")
        message.setWordWrap(True)
        message.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(message)
        retry = QtWidgets.QPushButton("重试加载")
        retry.setObjectName("primaryBtn")
        retry.clicked.connect(self.retryRequested)
        layout.addWidget(retry, 0, QtCore.Qt.AlignLeft)
        root.addWidget(panel, 0, QtCore.Qt.AlignHCenter)
        root.addStretch(1)
