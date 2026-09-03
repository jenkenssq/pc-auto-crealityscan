from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Optional, Sequence

from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore


_OUTPUT_DIR_RE = re.compile(r"\[COMPARE\] 本次输出目录：(.+)")
_REPORT_PATH_RE = re.compile(r"\[COMPARE\] Excel对比表：(.+)")
_SPINNER_FRAMES = ("◐", "◓", "◑", "◒")


_DISPLAY_FONT_PATH = Path(__file__).resolve().parent / "assets" / "fonts" / "IBMPlexSansSC-SemiBold.otf"

_SETTINGS_DIR = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "Jens" / "后处理对比工具"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"


def _load_settings() -> dict:
    """读取上次任务配置；文件缺失或损坏时返回空字典。"""
    try:
        if _SETTINGS_FILE.is_file():
            raw = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError, TypeError):
        pass
    return {}


def _save_settings(data: dict) -> None:
    """把任务配置写入用户本地配置目录，保证下次打开可恢复。"""
    try:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _decode_output(data: bytes) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("mbcs", errors="replace")


# THESIS: A calibration workbench that keeps configuration, execution state, and evidence visible without dashboard ornament.
# OWN-WORLD: Cool instrument surfaces, graphite text, cobalt actions, compact measurements, and explicit semantic states.
# STORY: Configure one paired comparison, verify every path, follow the serial run, then open the preserved result.
# FIRST VIEWPORT: Stable navigation at left, ordered configuration in the center, and a fixed execution console at right.
# FORM: Instrument calibration console, assigned direction 6, seed b20ef582.
# FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
class CompareWindow(QtWidgets.QMainWindow):
    def __init__(self, project_root: Optional[Path] = None) -> None:
        super().__init__()
        self._project_root = project_root
        self._process = QtCore.QProcess(self)
        self._stop_requested = False
        self._output_dir: Optional[Path] = None
        self._report_path: Optional[Path] = None
        self._selected_operation: Optional[str] = None
        self._log_lines: Deque[str] = deque(maxlen=2000)
        self._current_step = 0
        self._spinner_index = 0
        self._spinner_phase = False
        self._step_names = ("准备", "发布", "操作", "首页", "测试", "完成")
        self._spinner_timer = QtCore.QTimer(self)
        self._spinner_timer.setInterval(360)
        self._spinner_timer.timeout.connect(self._animate_step)
        self._path_rows: list[QtWidgets.QWidget] = []
        self._build_ui()
        self._connect_process()
        self._restore_settings()
        self._apply_mica()

    def _build_ui(self) -> None:
        self.setWindowTitle("CrealityScan后处理对比平台")
        self.resize(1480, 900)
        self.setMinimumSize(1180, 720)

        QtGui.QFontDatabase.addApplicationFont(str(_DISPLAY_FONT_PATH))
        app_font = QtGui.QFont("Microsoft YaHei UI")
        app_font.setPointSize(9)
        QtWidgets.QApplication.instance().setFont(app_font)

        shell = QtWidgets.QWidget()
        shell.setObjectName("appShell")
        shell_layout = QtWidgets.QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.setCentralWidget(shell)

        shell_layout.addWidget(self._build_sidebar())
        shell_layout.addWidget(self._build_center_panel(), 1)
        shell_layout.addWidget(self._build_console_panel())
        self.setStyleSheet(self._stylesheet())

    @staticmethod
    def _stylesheet() -> str:
        return """
            QWidget#appShell { background: #f3f6f8; color: #25313c; }
            QToolTip { color: #f5f8fa; background: #18232e; border: 1px solid #304253; padding: 5px 7px; }
            QFrame#sidebar { background: #18232e; border: 0; }
            QLabel#brand { color: #f5f8fa; font-family: "IBM Plex Sans SC"; font-size: 22px; font-weight: 600; }
            QLabel#brandSubtitle { color: #93a4b4; font-size: 12px; }
            QLabel#navLabel { color: #9baab8; font-size: 11px; font-weight: 600; padding: 3px 10px; }
            QPushButton#navButton { color: #c9d3dc; text-align: left; border: 0; border-radius: 8px; padding: 11px 14px; font-size: 13px; }
            QPushButton#navButton:hover { color: #ffffff; background: #223344; }
            QPushButton#navButton:checked { color: #ffffff; background: #274763; font-weight: 700; }
            QPushButton#navButton:disabled { color: #617385; background: transparent; }
            QFrame#sidebarTip { background: transparent; border: 0; border-top: 1px solid #304253; border-radius: 0; }
            QLabel#tipTitle { color: #dce5ec; font-size: 12px; font-weight: 700; }
            QLabel#tipText { color: #8193a4; font-size: 11px; }
            QWidget#centerPanel { background: #f3f6f8; }
            QFrame#consolePanel { background: #edf2f5; border-left: 1px solid #d1dae1; }
            QLabel#pageTitle { color: #18232e; font-family: "IBM Plex Sans SC"; font-size: 28px; font-weight: 600; }
            QLabel#pageSubtitle { color: #4f5f6c; font-size: 12px; }
            QLabel#consoleTitle { color: #18232e; font-size: 17px; font-weight: 700; }
            QLabel#consoleState { color: #546472; background: #dfe7ec; border-radius: 11px; padding: 4px 10px; font-size: 11px; }
            QLabel#consoleState[state="running"] { color: #6d470b; background: #f4e4bf; }
            QLabel#consoleState[state="success"] { color: #17543d; background: #d6eadf; }
            QLabel#consoleState[state="error"] { color: #872d2d; background: #f1dada; }
            QLabel#fieldLabel { color: #4f606e; font-size: 12px; }
            QLabel#panelTitle { color: #1e2b36; font-size: 15px; font-weight: 700; }
            QLabel#panelHint, QLabel#helperText { color: #5d6d79; font-size: 11px; }
            QLabel#stepCaption { color: #334654; font-size: 12px; font-weight: 700; }
            QFrame#floatingPanel { background: #ffffff; border: 1px solid #d5dfe6; border-radius: 12px; }
            QFrame#settingSeparator { color: #e8edf1; background: #e8edf1; max-height: 1px; }
            QLineEdit, QDoubleSpinBox { color: #263640; background: #ffffff; border: 1px solid #bdcad4; border-radius: 8px; padding: 8px 10px; min-height: 20px; font-size: 12px; selection-background-color: #0a66c2; }
            QLineEdit { placeholder-text-color: #5f7280; }
            QLineEdit:focus, QDoubleSpinBox:focus { border: 1px solid #0a66c2; }
            QLineEdit[pathState="valid"] { border-color: #75a990; }
            QLineEdit[pathState="invalid"] { border-color: #c98a54; }
            QLineEdit:disabled, QDoubleSpinBox:disabled { background: #eef2f4; color: #83919c; border-color: #dce3e8; }
            QPushButton { color: #334654; background: #ffffff; border: 1px solid #bdcad4; border-radius: 8px; padding: 8px 13px; font-size: 12px; }
            QPushButton:hover { color: #123f67; background: #f2f7fb; border-color: #82add2; }
            QPushButton:pressed { background: #e3edf5; border-color: #5f94c1; }
            QPushButton:focus { border: 1px solid #0a66c2; }
            QPushButton:disabled { color: #9aa7b1; background: #e9eef1; border-color: #d7e0e5; }
            QPushButton#browseButton { color: #445866; padding: 7px 11px; }
            QPushButton#outlineButton { color: #0a5fb3; border-color: #8db5d8; padding: 8px 15px; }
            QPushButton#segmentButton { min-width: 112px; color: #435664; border: 1px solid #bdcad4; background: #ffffff; padding: 8px 18px; }
            QPushButton#segmentButton:checked { color: #ffffff; background: #0a66c2; border-color: #0a66c2; font-weight: 700; }
            QPushButton#advancedButton { color: #3e607b; border: 1px solid #b8c5ce; background: #ffffff; padding: 7px 13px; border-radius: 8px; font-weight: 600; }
            QPushButton#advancedButton:hover { color: #0a66c2; border-color: #82add2; background: #f2f7fb; }
            QLabel#advToggleBadge { color: #7b8c99; font-size: 11px; }
            QLabel#advZoneTitle { color: #4f606e; font-size: 11px; font-weight: 700; padding: 4px 0; }
            QLabel#advFieldLabel { color: #4f606e; font-size: 12px; }
            QLabel#advUnit { color: #5d6d79; font-size: 12px; }
            QLabel#advZoneHint { color: #5d6d79; font-size: 11px; background: #edf1f5; border: 1px dashed #cdd8e1; border-radius: 7px; padding: 7px 11px; }
            QCheckBox { color: #263640; font-size: 12px; spacing: 7px; }
            QCheckBox::indicator { width: 14px; height: 14px; }
            QPushButton#primaryButton { color: #ffffff; background: #0a66c2; border-color: #0a66c2; padding: 10px 14px; font-weight: 700; }
            QPushButton#primaryButton:hover { background: #095aa9; border-color: #095aa9; }
            QPushButton#primaryButton:pressed { background: #074d91; border-color: #074d91; }
            QPushButton#secondaryButton { color: #5a6873; background: #f8fafb; border-color: #b8c5ce; padding: 10px 14px; }
            QPushButton#secondaryButton:hover { color: #a03333; background: #fff7f7; border-color: #d7a0a0; }
            QLabel#pathCheck { min-width: 18px; }
            QPlainTextEdit { color: #dce7ef; background: #111a22; border: 1px solid #253847; border-radius: 10px; padding: 12px; selection-background-color: #174f7d; font-size: 11px; }
            QLabel#stepIndicator { color: #445864; background: #dbe3e8; border-radius: 8px; padding: 6px 10px; font-size: 10px; font-weight: 700; }
            QLabel#stepIndicator[state="active"] { color: #ffffff; background: #0a66c2; }
            QLabel#stepIndicator[state="active"][pulse="true"] { background: #085596; }
            QLabel#stepIndicator[state="done"] { color: #ffffff; background: #26815d; }
            QLabel#stepIndicator[state="error"] { color: #ffffff; background: #bd3d3d; }
            QLabel#statusLabel { color: #4d5f6c; font-size: 12px; }
            QLabel#statusDotIdle { color: #8e9ca7; font-size: 13px; }
            QLabel#statusDotRunning { color: #ad7416; font-size: 13px; }
            QLabel#statusDotSuccess { color: #26815d; font-size: 13px; }
            QLabel#statusDotError { color: #bd3d3d; font-size: 13px; }
        """

    def _build_sidebar(self) -> QtWidgets.QWidget:
        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        layout = QtWidgets.QVBoxLayout(sidebar)
        layout.setContentsMargins(22, 30, 22, 24)
        layout.setSpacing(8)

        brand = QtWidgets.QLabel("CrealityScan")
        brand.setObjectName("brand")
        subtitle = QtWidgets.QLabel("后处理对比平台")
        subtitle.setObjectName("brandSubtitle")
        layout.addWidget(brand)
        layout.addWidget(subtitle)
        layout.addSpacing(34)

        nav_label = QtWidgets.QLabel("主导航")
        nav_label.setObjectName("navLabel")
        layout.addWidget(nav_label)
        self._nav_buttons: dict[str, QtWidgets.QPushButton] = {}
        for key, text in (
            ("home", "工作台首页"),
            ("tasks", "对比任务"),
            ("history", "运行记录"),
            ("settings", "设置"),
        ):
            button = QtWidgets.QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setChecked(key == "home")
            button.setEnabled(key == "home")
            if key != "home":
                button.setToolTip("该导航页将在任务记录模块完成后启用")
            button.clicked.connect(lambda _checked=False, selected=key: self._navigate(selected))
            layout.addWidget(button)
            self._nav_buttons[key] = button

        layout.addStretch(1)
        tip = QtWidgets.QFrame()
        tip.setObjectName("sidebarTip")
        tip_layout = QtWidgets.QVBoxLayout(tip)
        tip_layout.setContentsMargins(14, 13, 14, 13)
        tip_title = QtWidgets.QLabel("自动化工作台")
        tip_title.setObjectName("tipTitle")
        tip_text = QtWidgets.QLabel("两个版本 · 同一工程集\n结果过程可追溯")
        tip_text.setObjectName("tipText")
        tip_text.setWordWrap(True)
        tip_layout.addWidget(tip_title)
        tip_layout.addWidget(tip_text)
        layout.addWidget(tip)
        return sidebar

    def _build_center_panel(self) -> QtWidgets.QWidget:
        center = QtWidgets.QWidget()
        center.setObjectName("centerPanel")
        layout = QtWidgets.QVBoxLayout(center)
        layout.setContentsMargins(32, 28, 30, 24)
        layout.setSpacing(20)

        header = QtWidgets.QHBoxLayout()
        title_box = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("工作台首页")
        title.setObjectName("pageTitle")
        subtitle = QtWidgets.QLabel("配置一次，自动完成两个版本的后处理结果对比")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.open_output_button = QtWidgets.QPushButton("查看结果")
        self.open_output_button.setObjectName("outlineButton")
        self.open_output_button.setEnabled(False)
        header.addWidget(self.open_output_button, 0, QtCore.Qt.AlignTop)
        layout.addLayout(header)

        mode_row = QtWidgets.QHBoxLayout()
        mode_title = QtWidgets.QLabel("对比类型")
        mode_title.setObjectName("fieldLabel")
        mode_row.addWidget(mode_title)
        mode_row.addSpacing(16)
        self.operation_group = QtWidgets.QButtonGroup(self)
        self.operation_group.setExclusive(True)
        self.operation_buttons: dict[str, QtWidgets.QPushButton] = {}
        for key, text in (
            ("texture", "贴图"),
            ("gaussian", "高斯渲染"),
            ("ai_retexture", "AI重贴图"),
            ("human_body_completion", "人体补全"),
        ):
            button = QtWidgets.QPushButton(text)
            button.setObjectName("segmentButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, selected=key: self._select_operation(selected))
            self.operation_group.addButton(button)
            self.operation_buttons[key] = button
            mode_row.addWidget(button)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        config_panel = QtWidgets.QFrame()
        config_panel.setObjectName("floatingPanel")
        config_layout = QtWidgets.QVBoxLayout(config_panel)
        config_layout.setContentsMargins(22, 20, 22, 18)
        config_layout.setSpacing(0)

        config_header = QtWidgets.QHBoxLayout()
        config_title = QtWidgets.QLabel("任务配置")
        config_title.setObjectName("panelTitle")
        config_hint = QtWidgets.QLabel("所有路径均以本机文件为准")
        config_hint.setObjectName("panelHint")
        config_header.addWidget(config_title)
        config_header.addStretch(1)
        config_header.addWidget(config_hint)
        config_layout.addLayout(config_header)
        config_layout.addSpacing(8)

        self.release_exe = self._path_edit("选择发布版 CrealityScan.exe")
        self.test_exe = self._path_edit("选择测试版 CrealityScan.exe")
        self.project_set = self._path_edit("选择包含一个或多个工程目录的工程集")
        self.output_dir = self._path_edit("选择对比结果输出目录")
        self.release_version = QtWidgets.QLineEdit()
        self.release_version.setPlaceholderText("版本标签，例如 1.12.3-release")
        self.test_version = QtWidgets.QLineEdit()
        self.test_version.setPlaceholderText("版本标签，例如 1.12.4-test")

        config_layout.addWidget(self._setting_row("发布版 EXE", self.release_exe, self._browse_release_exe))
        config_layout.addWidget(self._separator())
        config_layout.addWidget(self._setting_row("发布版标签", self.release_version, None))
        config_layout.addWidget(self._separator())
        config_layout.addWidget(self._setting_row("测试版 EXE", self.test_exe, self._browse_test_exe))
        config_layout.addWidget(self._separator())
        config_layout.addWidget(self._setting_row("测试版标签", self.test_version, None))
        config_layout.addWidget(self._separator())
        config_layout.addWidget(self._setting_row("原始工程集", self.project_set, self._browse_project_set))
        config_layout.addWidget(self._separator())
        config_layout.addWidget(self._setting_row("输出目录", self.output_dir, self._browse_output_dir))
        config_layout.addWidget(self._separator())

        # ── 发布后删除下载包（可选）：让用户选择是否在发布版完成后删除旧下载包 ──
        delete_toggle_row = QtWidgets.QHBoxLayout()
        delete_toggle_row.setSpacing(8)
        self.delete_package_check = QtWidgets.QCheckBox("发布后删除下载包")
        self.delete_package_check.setToolTip(
            "勾选后，发布版全部后处理完成并关闭时删除本次操作对应的下载包，"
            "使测试版运行时重新下载新版本下载包。"
        )
        self.delete_package_hint = QtWidgets.QLabel("测试版重新下载新包")
        self.delete_package_hint.setObjectName("panelHint")
        delete_toggle_row.addWidget(self.delete_package_check)
        delete_toggle_row.addWidget(self.delete_package_hint)
        delete_toggle_row.addStretch(1)
        config_layout.addLayout(delete_toggle_row)

        # ── 开启Charles（可选）：发布版后处理完成后、测试版启动前自动启动抓包代理 ──
        charles_toggle_row = QtWidgets.QHBoxLayout()
        charles_toggle_row.setSpacing(8)
        self.charles_check = QtWidgets.QCheckBox("开启Charles")
        self.charles_check.setToolTip(
            "开启后，在发布版后处理完成并关闭、启动测试版之前，自动启动 Charles 抓包代理。"
        )
        self.charles_check.toggled.connect(self._toggle_charles)
        self.charles_hint = QtWidgets.QLabel("发布版后处理完成后自动启动抓包代理")
        self.charles_hint.setObjectName("panelHint")
        charles_toggle_row.addWidget(self.charles_check)
        charles_toggle_row.addWidget(self.charles_hint)
        charles_toggle_row.addStretch(1)
        config_layout.addLayout(charles_toggle_row)

        self.charles_exe = self._path_edit("选择 Charles.exe 可执行文件路径")
        self.charles_row = self._setting_row("Charles.exe", self.charles_exe, self._browse_charles_exe)
        self.charles_row.setVisible(False)
        config_layout.addWidget(self.charles_row)
        config_layout.addWidget(self._separator())

        # ── 高级参数：点击打开弹窗，避免在表单内纵向堆叠占空间 ──
        # 通用超时
        self.postprocess_timeout_label = QtWidgets.QLabel("后处理超时")
        self.operation_timeout = self._seconds_spin(90.0, 1.0, 86400.0)
        self.start_timeout = self._seconds_spin(120.0, 1.0, 3600.0)
        self.close_timeout = self._seconds_spin(20.0, 1.0, 600.0)

        # 专属选项提示（贴图无专属参数时显示）
        self.specific_none = QtWidgets.QLabel("贴图无专属参数，直接使用上方通用超时。")
        self.specific_none.setObjectName("advZoneHint")
        self.specific_none.setWordWrap(True)

        # 高斯渲染专属组
        self.gaussian_quality = QtWidgets.QComboBox()
        self.gaussian_quality.addItems(["快速", "标准", "高质量"])
        self.gaussian_quality.setCurrentText("高质量")
        self.gaussian_quality.setToolTip("选择高斯渲染质量等级，默认高质量")
        self.gaussian_quality_label = QtWidgets.QLabel("质量等级")
        self.gaussian_quality_label.setObjectName("advFieldLabel")
        self.gaussian_group = QtWidgets.QWidget()
        gaussian_layout = QtWidgets.QHBoxLayout(self.gaussian_group)
        gaussian_layout.setContentsMargins(0, 0, 0, 0)
        gaussian_layout.setSpacing(9)
        gaussian_title = QtWidgets.QLabel("高斯渲染专属选项")
        gaussian_title.setObjectName("advZoneTitle")
        gaussian_layout.addWidget(gaussian_title)
        gaussian_layout.addSpacing(8)
        gaussian_layout.addWidget(self.gaussian_quality_label)
        gaussian_layout.addWidget(self.gaussian_quality, 0, QtCore.Qt.AlignLeft)
        gaussian_layout.addStretch(1)

        # AI重贴图专属组
        self.ai_retexture_gaussian = QtWidgets.QCheckBox("开启高斯渲染")
        self.ai_retexture_gaussian.setChecked(False)
        self.ai_retexture_texture_first = QtWidgets.QCheckBox("先执行贴图")
        self.ai_retexture_texture_first.setChecked(True)
        self.texture_timeout_label = QtWidgets.QLabel("前置贴图超时")
        self.texture_timeout_label.setObjectName("advFieldLabel")
        self.texture_timeout = self._seconds_spin(90.0, 1.0, 3600.0)
        self.ai_group = QtWidgets.QWidget()
        ai_layout = QtWidgets.QVBoxLayout(self.ai_group)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        ai_layout.setSpacing(6)
        ai_title = QtWidgets.QLabel("AI重贴图专属选项")
        ai_title.setObjectName("advZoneTitle")
        ai_layout.addWidget(ai_title)
        ai_layout.addWidget(self.ai_retexture_gaussian)
        ai_texture_row = QtWidgets.QHBoxLayout()
        ai_texture_row.setSpacing(9)
        ai_texture_row.addWidget(self.ai_retexture_texture_first)
        ai_texture_row.addWidget(self.texture_timeout_label)
        ai_texture_row.addWidget(self.texture_timeout, 0, QtCore.Qt.AlignLeft)
        ai_texture_row.addWidget(QtWidgets.QLabel("秒"))
        ai_texture_row.addStretch(1)
        ai_layout.addLayout(ai_texture_row)

        # 人体补全专属组
        self.human_body_hd_geometry = QtWidgets.QCheckBox("开启超清几何精度")
        self.human_body_hd_geometry.setChecked(False)
        self.base_wait_label = QtWidgets.QLabel("底座等待")
        self.base_wait_label.setObjectName("advFieldLabel")
        self.base_wait = self._seconds_spin(20.0, 0.0, 3600.0)
        self.human_group = QtWidgets.QWidget()
        human_layout = QtWidgets.QVBoxLayout(self.human_group)
        human_layout.setContentsMargins(0, 0, 0, 0)
        human_layout.setSpacing(6)
        human_title = QtWidgets.QLabel("人体补全专属选项")
        human_title.setObjectName("advZoneTitle")
        human_layout.addWidget(human_title)
        human_layout.addWidget(self.human_body_hd_geometry)
        human_base_row = QtWidgets.QHBoxLayout()
        human_base_row.setSpacing(9)
        human_base_row.addWidget(self.base_wait_label)
        human_base_row.addWidget(self.base_wait, 0, QtCore.Qt.AlignLeft)
        human_base_row.addWidget(QtWidgets.QLabel("秒"))
        human_base_row.addStretch(1)
        human_layout.addLayout(human_base_row)

        # 初始无对比类型被选中：仅显示“无专属参数”提示
        self.specific_none.setVisible(True)
        self.ai_group.setVisible(False)
        self.human_group.setVisible(False)
        self.gaussian_group.setVisible(False)

        # 表单内只保留一个“高级参数”入口按钮 + 当前值摘要
        self._advanced_dialog: Optional[QtWidgets.QDialog] = None
        adv_row = QtWidgets.QHBoxLayout()
        adv_row.setSpacing(8)
        self.advanced_button = QtWidgets.QPushButton("高级参数...")
        self.advanced_button.setObjectName("advancedButton")
        self.advanced_button.setToolTip("打开高级参数设置弹窗（超时、专属选项）")
        self.advanced_button.clicked.connect(self._open_advanced)
        self.advanced_summary = QtWidgets.QLabel()
        self.advanced_summary.setObjectName("advToggleBadge")
        adv_row.addWidget(self.advanced_button)
        adv_row.addWidget(self.advanced_summary, 1)
        config_layout.addSpacing(12)
        config_layout.addLayout(adv_row)
        self._update_advanced_summary()

        layout.addWidget(config_panel)

        note = QtWidgets.QLabel("导入工程、后处理和返回首页均由自动化流程完成；运行过程中会锁定配置。")
        note.setObjectName("helperText")
        layout.addWidget(note)
        layout.addStretch(1)
        return center

    def _build_console_panel(self) -> QtWidgets.QWidget:
        right = QtWidgets.QFrame()
        right.setObjectName("consolePanel")
        right.setFixedWidth(340)
        layout = QtWidgets.QVBoxLayout(right)
        layout.setContentsMargins(18, 26, 18, 24)
        layout.setSpacing(14)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("执行控制台")
        title.setObjectName("consoleTitle")
        self.console_state = QtWidgets.QLabel("待机")
        self.console_state.setObjectName("consoleState")
        self.console_state.setFixedHeight(26)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.console_state)
        layout.addLayout(header)

        steps_title = QtWidgets.QLabel("执行步骤")
        steps_title.setObjectName("fieldLabel")
        layout.addWidget(steps_title)
        self.step_indicators: list[QtWidgets.QLabel] = []
        indicator_grid = QtWidgets.QGridLayout()
        indicator_grid.setHorizontalSpacing(7)
        indicator_grid.setVerticalSpacing(7)
        for number, text in enumerate(("准备", "发布", "操作", "首页", "测试", "完成"), start=1):
            indicator = QtWidgets.QLabel(f"{number:02d}  {text}")
            indicator.setObjectName("stepIndicator")
            indicator.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            indicator.setFixedHeight(32)
            indicator.setToolTip(text)
            indicator_grid.addWidget(indicator, (number - 1) // 2, (number - 1) % 2)
            self.step_indicators.append(indicator)
        layout.addLayout(indicator_grid)

        log_title = QtWidgets.QLabel("实时日志预览")
        log_title.setObjectName("fieldLabel")
        layout.addWidget(log_title)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.log_view.setFont(QtGui.QFont("Consolas", 9))
        self.log_view.setPlaceholderText("运行日志（保留本次运行全部输出，完整日志同时写入输出目录的 运行日志.txt）")
        self.log_view.setMinimumHeight(300)
        layout.addWidget(self.log_view, 1)

        status_row = QtWidgets.QHBoxLayout()
        self.status_dot = QtWidgets.QLabel("●")
        self.status_dot.setObjectName("statusDotIdle")
        self.status_label = QtWidgets.QLabel("就绪：请选择对比类型")
        self.status_label.setObjectName("statusLabel")
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_label, 1)
        layout.addLayout(status_row)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(8)
        self.start_button = QtWidgets.QPushButton("开始对比")
        self.start_button.setObjectName("primaryButton")
        self.stop_button = QtWidgets.QPushButton("紧急停止")
        self.stop_button.setObjectName("secondaryButton")
        self.stop_button.setEnabled(False)
        buttons.addWidget(self.start_button, 1)
        buttons.addWidget(self.stop_button, 1)
        layout.addLayout(buttons)
        return right

    def _setting_row(
        self,
        label_text: str,
        edit: QtWidgets.QLineEdit,
        browse_callback: Optional[Callable[[], None]],
    ) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(9)
        label = QtWidgets.QLabel(label_text)
        label.setObjectName("fieldLabel")
        label.setFixedWidth(94)
        row_layout.addWidget(label)
        row_layout.addWidget(edit, 1)
        if browse_callback is not None:
            browse = QtWidgets.QPushButton("浏览")
            browse.setObjectName("browseButton")
            browse.setFixedWidth(56)
            browse.clicked.connect(browse_callback)
            row_layout.addWidget(browse)
            self._path_rows.append(row)
            edit.textChanged.connect(lambda text, target=edit: self._update_path_state(target, text))
        else:
            row_layout.addStretch(1)
        check = QtWidgets.QLabel()
        check.setObjectName("pathCheck")
        check.setFixedWidth(18)
        check.setAlignment(QtCore.Qt.AlignCenter)
        check.setVisible(False)
        row_layout.addWidget(check)
        setattr(edit, "_path_check", check)
        return row

    @staticmethod
    def _separator() -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setObjectName("settingSeparator")
        return line

    @staticmethod
    def _path_edit(placeholder: str) -> QtWidgets.QLineEdit:
        edit = QtWidgets.QLineEdit()
        edit.setPlaceholderText(placeholder)
        return edit

    @staticmethod
    def _seconds_spin(value: float, minimum: float, maximum: float) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        return spin

    def _connect_process(self) -> None:
        self._process.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read_process_output)
        self._process.started.connect(lambda: self._set_running(True))
        self._process.errorOccurred.connect(self._process_error)
        self._process.finished.connect(self._process_finished)
        self.start_button.clicked.connect(self.start_run)
        self.stop_button.clicked.connect(self.stop_run)
        self.open_output_button.clicked.connect(self.open_output_dir)

    def _apply_mica(self) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            backdrop_type = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(38),
                ctypes.byref(backdrop_type),
                ctypes.sizeof(backdrop_type),
            )
        except (AttributeError, OSError, TypeError):
            pass

    def _navigate(self, key: str) -> None:
        for name, button in self._nav_buttons.items():
            button.setChecked(name == key)
        if key != "home":
            self._set_status("该导航页将在任务记录模块完成后启用", "idle")

    def _update_path_state(self, edit: QtWidgets.QLineEdit, text: str) -> None:
        check = getattr(edit, "_path_check", None)
        if check is None:
            return
        value = text.strip()
        if not value:
            check.setVisible(False)
            edit.setProperty("pathState", "")
        else:
            is_valid = Path(value).exists()
            icon_kind = QtWidgets.QStyle.SP_DialogApplyButton if is_valid else QtWidgets.QStyle.SP_MessageBoxWarning
            check.setPixmap(self.style().standardIcon(icon_kind).pixmap(14, 14))
            check.setToolTip("路径有效" if is_valid else "路径不存在")
            check.setVisible(True)
            edit.setProperty("pathState", "valid" if is_valid else "invalid")
        edit.style().unpolish(edit)
        edit.style().polish(edit)

    def _restore_settings(self) -> None:
        """把上次保存的任务配置恢复到界面控件上。"""
        data = _load_settings()
        if not data:
            return
        operation = str(data.get("operation") or "")
        if operation in self.operation_buttons:
            self._select_operation(operation)
        self.release_exe.setText(str(data.get("release_exe") or ""))
        self.release_version.setText(str(data.get("release_version") or ""))
        self.test_exe.setText(str(data.get("test_exe") or ""))
        self.test_version.setText(str(data.get("test_version") or ""))
        self.project_set.setText(str(data.get("project_set") or ""))
        self.output_dir.setText(str(data.get("output_dir") or ""))
        self.operation_timeout.setValue(float(data.get("operation_timeout") or self.operation_timeout.value()))
        self.start_timeout.setValue(float(data.get("start_timeout") or self.start_timeout.value()))
        self.close_timeout.setValue(float(data.get("close_timeout") or self.close_timeout.value()))
        self.delete_package_check.setChecked(bool(data.get("delete_package")))
        # 先填 Charles 路径再勾选，避免 _toggle_charles 在路径为空时弹出文件选择框
        self.charles_exe.setText(str(data.get("charles_exe") or ""))
        self.charles_check.setChecked(bool(data.get("charles")))
        quality = str(data.get("gaussian_quality") or "高质量")
        if self.gaussian_quality.findText(quality) >= 0:
            self.gaussian_quality.setCurrentText(quality)
        self.ai_retexture_gaussian.setChecked(bool(data.get("ai_retexture_gaussian")))
        self.ai_retexture_texture_first.setChecked(bool(data.get("ai_retexture_texture_first", True)))
        self.texture_timeout.setValue(float(data.get("texture_timeout") or self.texture_timeout.value()))
        self.human_body_hd_geometry.setChecked(bool(data.get("human_body_hd_geometry")))
        self.base_wait.setValue(float(data.get("base_wait") or self.base_wait.value()))
        self._update_advanced_summary()
        for edit in (self.release_exe, self.test_exe, self.project_set, self.output_dir, self.charles_exe):
            self._update_path_state(edit, edit.text())

    def _save_settings(self) -> None:
        """把当前界面任务配置保存到本地，供下次启动恢复。"""
        data = {
            "operation": self._selected_operation or "",
            "release_exe": self.release_exe.text().strip(),
            "release_version": self.release_version.text().strip(),
            "test_exe": self.test_exe.text().strip(),
            "test_version": self.test_version.text().strip(),
            "project_set": self.project_set.text().strip(),
            "output_dir": self.output_dir.text().strip(),
            "operation_timeout": self.operation_timeout.value(),
            "start_timeout": self.start_timeout.value(),
            "close_timeout": self.close_timeout.value(),
            "delete_package": self.delete_package_check.isChecked(),
            "charles": self.charles_check.isChecked(),
            "charles_exe": self.charles_exe.text().strip(),
            "gaussian_quality": self.gaussian_quality.currentText(),
            "ai_retexture_gaussian": self.ai_retexture_gaussian.isChecked(),
            "ai_retexture_texture_first": self.ai_retexture_texture_first.isChecked(),
            "texture_timeout": self.texture_timeout.value(),
            "human_body_hd_geometry": self.human_body_hd_geometry.isChecked(),
            "base_wait": self.base_wait.value(),
        }
        _save_settings(data)

    def _open_advanced(self) -> None:
        """打开高级参数弹窗；保存后刷新表单摘要。"""
        if self._advanced_dialog is None:
            self._advanced_dialog = self._build_advanced_dialog()
        self._sync_advanced_visibility()
        if self._advanced_dialog.exec_() == QtWidgets.QDialog.Accepted:
            self._update_advanced_summary()

    def _build_advanced_dialog(self) -> QtWidgets.QDialog:
        """构建高级参数弹窗：通用超时横向排一行，专属选项按类型显示。"""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("高级参数")
        dlg.setModal(True)
        dlg.setMinimumWidth(640)
        outer = QtWidgets.QVBoxLayout(dlg)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)

        def zone_title(text: str) -> QtWidgets.QLabel:
            title = QtWidgets.QLabel(text)
            title.setObjectName("advZoneTitle")
            return title

        def timeout_field(label: QtWidgets.QLabel, spin: QtWidgets.QDoubleSpinBox) -> QtWidgets.QWidget:
            field = QtWidgets.QWidget()
            lay = QtWidgets.QHBoxLayout(field)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
            label.setObjectName("advFieldLabel")
            label.setFixedWidth(112)
            spin.setFixedWidth(112)
            unit = QtWidgets.QLabel("秒")
            unit.setObjectName("advUnit")
            lay.addWidget(label)
            lay.addWidget(spin)
            lay.addWidget(unit)
            return field

        outer.addWidget(zone_title("通用超时 · 适用于所选对比类型"))
        timeout_row = QtWidgets.QHBoxLayout()
        timeout_row.setSpacing(18)
        timeout_row.addWidget(timeout_field(self.postprocess_timeout_label, self.operation_timeout))
        timeout_row.addWidget(timeout_field(QtWidgets.QLabel("启动超时"), self.start_timeout))
        timeout_row.addWidget(timeout_field(QtWidgets.QLabel("关闭超时"), self.close_timeout))
        timeout_row.addStretch(1)
        outer.addLayout(timeout_row)

        outer.addSpacing(6)
        outer.addWidget(zone_title("专属选项"))
        outer.addWidget(self.specific_none)
        outer.addWidget(self.gaussian_group)
        outer.addWidget(self.ai_group)
        outer.addWidget(self.human_group)

        outer.addSpacing(6)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        cancel = QtWidgets.QPushButton("取消")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(dlg.reject)
        ok = QtWidgets.QPushButton("保存")
        ok.setObjectName("primaryButton")
        ok.clicked.connect(dlg.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        outer.addLayout(buttons)
        return dlg

    def _sync_advanced_visibility(self) -> None:
        """按当前所选对比类型切换专属选项区可见性。"""
        is_gaussian = self._selected_operation == "gaussian"
        is_ai = self._selected_operation == "ai_retexture"
        is_human = self._selected_operation == "human_body_completion"
        self.specific_none.setVisible(not is_gaussian and not is_ai and not is_human)
        self.gaussian_group.setVisible(is_gaussian)
        self.ai_group.setVisible(is_ai)
        self.human_group.setVisible(is_human)

    def _update_advanced_summary(self) -> None:
        """刷新表单内“高级参数”入口旁的当前值摘要（紧凑单行）。"""
        if not hasattr(self, "advanced_summary"):
            return

        def fmt(value: float) -> str:
            return f"{value:g}"

        summary = "超时 {} / {} / {} 秒".format(
            fmt(self.operation_timeout.value()),
            fmt(self.start_timeout.value()),
            fmt(self.close_timeout.value()),
        )
        extra: list[str] = []
        if self._selected_operation == "gaussian":
            extra.append(f"质量{self.gaussian_quality.currentText()}")
        elif self._selected_operation == "ai_retexture":
            extra.append("高斯" + ("开" if self.ai_retexture_gaussian.isChecked() else "关"))
            extra.append("先贴图" if self.ai_retexture_texture_first.isChecked() else "不先贴图")
            extra.append(f"前置{fmt(self.texture_timeout.value())}秒")
        elif self._selected_operation == "human_body_completion":
            extra.append("超清" + ("开" if self.human_body_hd_geometry.isChecked() else "关"))
            extra.append(f"底座{fmt(self.base_wait.value())}秒")
        else:
            extra.append("无专属参数")
        summary += " · " + " · ".join(extra)
        self.advanced_summary.setText(summary)

    def _toggle_charles(self, enabled: bool) -> None:
        """开启Charles开关：打开时展示路径行，未设置路径则弹出文件选择对话框。"""
        self.charles_row.setVisible(enabled)
        if enabled and not self.charles_exe.text().strip():
            self._browse_charles_exe()
            if not self.charles_exe.text().strip():
                self.charles_check.setChecked(False)

    def _charles_error(self) -> str:
        if not self.charles_check.isChecked():
            return ""
        path = self.charles_exe.text().strip()
        if not path:
            return "已开启Charles，请选择 Charles.exe 可执行文件路径。"
        if not Path(path).is_file():
            return f"Charles.exe 路径不存在：{path}"
        return ""

    def _select_operation(self, operation: str) -> None:
        self._selected_operation = operation
        self.operation_buttons[operation].setChecked(True)
        for key, button in self.operation_buttons.items():
            button.setProperty("selected", key == operation)
            button.style().unpolish(button)
            button.style().polish(button)
        if operation == "gaussian":
            self.postprocess_timeout_label.setText("高斯渲染超时")
            self.operation_timeout.setValue(900.0)
        elif operation == "ai_retexture":
            self.postprocess_timeout_label.setText("AI重贴图超时")
            self.operation_timeout.setValue(600.0)
        elif operation == "human_body_completion":
            self.postprocess_timeout_label.setText("人体补全超时")
            self.operation_timeout.setValue(600.0)
        else:
            self.postprocess_timeout_label.setText("贴图超时")
            self.operation_timeout.setValue(90.0)
        self._sync_advanced_visibility()
        self._update_advanced_summary()
        self._set_status(f"已选择{self.operation_buttons[operation].text()}对比", "idle")

    def _set_step_state(self, step: int, state: str) -> None:
        if step < 1 or step > len(self.step_indicators):
            return
        label = self.step_indicators[step - 1]
        label.setProperty("state", state)
        label.setProperty("pulse", False)
        label.setText(f"{step:02d}  {self._step_names[step - 1]}")
        label.style().unpolish(label)
        label.style().polish(label)

    def _set_active_step(self, step: int) -> None:
        if step < 1:
            return
        for index in range(1, len(self.step_indicators) + 1):
            self._set_step_state(index, "done" if index < step else ("active" if index == step else "idle"))
        self._current_step = step
        self._spinner_index = 0
        self._spinner_phase = False
        self._spinner_timer.start()

    def _animate_step(self) -> None:
        if not self._current_step or self._current_step > len(self.step_indicators):
            return
        label = self.step_indicators[self._current_step - 1]
        if label.property("state") == "active":
            self._spinner_phase = not self._spinner_phase
            label.setProperty("pulse", self._spinner_phase)
            label.style().unpolish(label)
            label.style().polish(label)
            self._spinner_index += 1

    def _finish_steps(self, success: bool) -> None:
        self._spinner_timer.stop()
        for index in range(1, len(self.step_indicators) + 1):
            if success:
                state = "done"
            elif index < self._current_step:
                state = "done"
            elif index == self._current_step:
                state = "error"
            else:
                state = "idle"
            self._set_step_state(index, state)

    def _set_status(self, text: str, state: str) -> None:
        self.status_label.setText(text)
        self.console_state.setText({"running": "运行中", "success": "完成", "error": "失败"}.get(state, "待机"))
        self.console_state.setProperty("state", state)
        self.console_state.style().unpolish(self.console_state)
        self.console_state.style().polish(self.console_state)
        self.status_dot.setObjectName({"idle": "statusDotIdle", "running": "statusDotRunning", "success": "statusDotSuccess", "error": "statusDotError"}.get(state, "statusDotIdle"))
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)

    def _append_log(self, text: str) -> None:
        for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
            if not line:
                continue
            self._log_lines.append(line)
            if "开始执行" in line or "导入成功" in line:
                self._set_active_step(3 if self._current_step < 3 else self._current_step)
            elif "返回首页" in line:
                self._set_active_step(4 if "发布版" in line else 6)
            elif "正在启动发布版" in line:
                self._set_active_step(2)
            elif "正在启动测试版" in line:
                self._set_active_step(5)
            elif "工作副本" in line:
                self._set_active_step(1)
        self.log_view.setPlainText("\n".join(self._log_lines))
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _read_process_output(self) -> None:
        data = bytes(self._process.readAllStandardOutput())
        text = _decode_output(data)
        if not text:
            return
        match = _OUTPUT_DIR_RE.search(text)
        if match:
            self._output_dir = Path(match.group(1).strip())
            self.open_output_button.setEnabled(self._output_dir.is_dir())
        report_match = _REPORT_PATH_RE.search(text)
        if report_match:
            self._report_path = Path(report_match.group(1).strip())
            if self._report_path.is_file():
                self.open_output_button.setText("打开对比表")
                self.open_output_button.setEnabled(True)
        self._append_log(text)

    def _process_error(self, error: QtCore.QProcess.ProcessError) -> None:
        if error != QtCore.QProcess.Crashed:
            self._append_log(f"[GUI][ERROR] CLI 进程错误：{error}")

    def _process_finished(self, exit_code: int, exit_status: QtCore.QProcess.ExitStatus) -> None:
        self._read_process_output()
        stopped = self._stop_requested
        self._set_running(False)
        if stopped:
            self._set_status("任务已停止", "idle")
            self._finish_steps(False)
        elif exit_status == QtCore.QProcess.NormalExit and exit_code == 0:
            self._set_status("对比完成", "success")
            self._finish_steps(True)
        else:
            self._set_status("对比失败，请查看日志", "error")
            self._finish_steps(False)
        self._append_log(f"[GUI] CLI 退出码：{exit_code}")
        self._stop_requested = False

    def _set_running(self, running: bool) -> None:
        controls = (
            self.release_exe,
            self.release_version,
            self.test_exe,
            self.test_version,
            self.project_set,
            self.output_dir,
            self.delete_package_check,
            self.charles_check,
            self.operation_timeout,
            self.start_timeout,
            self.close_timeout,
            self.advanced_button,
            self.gaussian_quality,
            self.ai_retexture_gaussian,
            self.ai_retexture_texture_first,
            self.texture_timeout,
            self.human_body_hd_geometry,
            self.base_wait,
        )
        for widget in controls:
            widget.setEnabled(not running)
        for row in self._path_rows:
            row.setEnabled(not running)
        for button in self.operation_buttons.values():
            button.setEnabled(not running)
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if running:
            self._set_status("正在执行对比任务...", "running")
            self._set_active_step(1)

    def _validate_inputs(self) -> list[str]:
        values = {
            "发布版 EXE": self.release_exe.text().strip(),
            "发布版标签": self.release_version.text().strip(),
            "测试版 EXE": self.test_exe.text().strip(),
            "测试版标签": self.test_version.text().strip(),
            "原始工程集": self.project_set.text().strip(),
            "输出目录": self.output_dir.text().strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if self._selected_operation is None:
            missing.insert(0, "对比类型")
        return missing

    def start_run(self) -> None:
        missing = self._validate_inputs()
        if missing:
            QtWidgets.QMessageBox.warning(self, "配置不完整", "请填写：" + "、".join(missing))
            return
        charles_error = self._charles_error()
        if charles_error:
            QtWidgets.QMessageBox.warning(self, "配置不完整", charles_error)
            return
        if self._process.state() != QtCore.QProcess.NotRunning:
            return

        self._log_lines.clear()
        self.log_view.clear()
        self._output_dir = None
        self._report_path = None
        self.open_output_button.setText("查看结果")
        self.open_output_button.setEnabled(False)
        self._stop_requested = False
        self._save_settings()
        args = [
            "--release-exe",
            self.release_exe.text().strip(),
            "--release-version",
            self.release_version.text().strip(),
            "--test-exe",
            self.test_exe.text().strip(),
            "--test-version",
            self.test_version.text().strip(),
            "--project-set",
            self.project_set.text().strip(),
            "--output-dir",
            self.output_dir.text().strip(),
            "--operation",
            self._selected_operation or "",
            "--operation-timeout",
            str(self.operation_timeout.value()),
            "--start-timeout",
            str(self.start_timeout.value()),
            "--close-timeout",
            str(self.close_timeout.value()),
        ]
        args.append("--gaussian-quality")
        args.append(self.gaussian_quality.currentText())
        args.append("--texture-timeout")
        args.append(str(self.texture_timeout.value()))
        if not self.ai_retexture_texture_first.isChecked():
            args.append("--no-texture-first")
        if self.ai_retexture_gaussian.isChecked():
            args.append("--ai-retexture-gaussian")
        if self.human_body_hd_geometry.isChecked():
            args.append("--human-body-hd-geometry")
        args.append("--base-wait")
        args.append(str(self.base_wait.value()))
        if self.delete_package_check.isChecked():
            args.append("--delete-download-package")
        if self.charles_check.isChecked():
            args.append("--charles-exe")
            args.append(self.charles_exe.text().strip())
        env = QtCore.QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        self._process.setProcessEnvironment(env)
        # 打包态下 CLI 已随 jens_platform 包冻结进 exe，通过 --postprocess-compare-runner 复用自身进程；
        # 源码态以平台根目录为工作目录，通过 python -m 启动收编后的 CLI 包。
        if getattr(sys, "frozen", False):
            program = sys.executable
            args = ["--postprocess-compare-runner", *args]
        else:
            program = sys.executable
            args = ["-m", "jens_platform.tools.postprocess_compare", *args]
            root = self._project_root or Path(__file__).resolve().parents[3]
            self._process.setWorkingDirectory(str(root))
        self._process.start(program, args)
        if not self._process.waitForStarted(1500):
            self._set_running(False)
            self._set_status("CLI 启动失败", "error")
            QtWidgets.QMessageBox.critical(self, "启动失败", "无法启动对比 CLI 进程。")

    def stop_run(self) -> None:
        if self._process.state() == QtCore.QProcess.NotRunning:
            return
        self._stop_requested = True
        self._set_status("正在停止任务...", "running")
        self._append_log("[GUI] 收到紧急停止请求，正在终止当前任务。")
        self._process.terminate()
        QtCore.QTimer.singleShot(2000, self._force_stop_process)

    def _force_stop_process(self) -> None:
        if self._process.state() == QtCore.QProcess.NotRunning:
            return
        pid = int(self._process.processId() or 0)
        if pid and os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            self._process.kill()

    def open_output_dir(self) -> None:
        target = self._report_path
        if target is None or not target.is_file():
            target = self._output_dir
        if target is None or not target.exists():
            return
        opened = QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(target)))
        if not opened and target == self._report_path and self._output_dir is not None:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self._output_dir)))

    def _browse_file(self, target: QtWidgets.QLineEdit, title: str, file_filter: str) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, title, target.text(), file_filter)
        if path:
            target.setText(path)

    def _browse_release_exe(self) -> None:
        self._browse_file(self.release_exe, "选择发布版 CrealityScan.exe", "可执行文件 (*.exe)")

    def _browse_test_exe(self) -> None:
        self._browse_file(self.test_exe, "选择测试版 CrealityScan.exe", "可执行文件 (*.exe)")

    def _browse_project_set(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择原始工程集目录", self.project_set.text())
        if path:
            self.project_set.setText(path)

    def _browse_output_dir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择对比结果输出目录", self.output_dir.text())
        if path:
            self.output_dir.setText(path)

    def _browse_charles_exe(self) -> None:
        self._browse_file(self.charles_exe, "选择 Charles.exe", "可执行文件 (*.exe)")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._process.state() != QtCore.QProcess.NotRunning:
            answer = QtWidgets.QMessageBox.question(
                self,
                "任务仍在运行",
                "当前对比任务仍在运行，是否紧急停止并退出？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                event.ignore()
                return
            self.stop_run()
            self._process.waitForFinished(2500)
        self._save_settings()
        event.accept()


def main(argv: Optional[Sequence[str]] = None) -> int:
    app = QtWidgets.QApplication(list(argv or sys.argv))
    app.setApplicationName("CrealityScan后处理对比平台")
    app.setStyle("Fusion")
    window = CompareWindow()
    window.show()
    return int(app.exec_())


if __name__ == "__main__":
    raise SystemExit(main())
