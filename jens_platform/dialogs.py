from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore

from engine.window import get_primary_screen_size, get_window_status
from jens_platform.case_store import CaseModel, CaseStep, load_task_json, save_task_json
from jens_platform.step_registry import StepMeta
from jens_platform.task_generator import (
    CONNECTION_USB,
    CONNECTION_WIFI,
    DEFAULT_FPS_STAT_FRAMES,
    MODULE_PRESET_SOURCES,
    TASK_KIND_FPS_STAT,
    TASK_KIND_OPEN_STREAM,
    TASK_KIND_POSTPROCESS,
    ScanPreset,
    fps_stat_mode_plan,
    list_module_presets,
)


def _open_path(path: str) -> None:
    if not path:
        return
    try:
        os.startfile(path)  # type: ignore[attr-defined]  # Windows only
    except Exception:
        # 兜底：不阻断主流程
        pass


class ConfirmRunDialog(QtWidgets.QDialog):
    """
    代替原生 QMessageBox，使“确认运行”更有质感且信息更清晰。
    """

    def __init__(self, title_contains: str = "CrealityScan", parent=None):
        super().__init__(parent)
        self._title_contains = title_contains or "CrealityScan"
        self.setWindowTitle("确认运行")
        self.setModal(True)
        self.setMinimumWidth(520)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        # Header
        header = QtWidgets.QHBoxLayout()
        icon = self.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxWarning)
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(icon.pixmap(32, 32))
        header.addWidget(icon_label, 0, QtCore.Qt.AlignTop)

        title_box = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("运行会控制当前桌面进行点击/截图")
        f = title.font()
        f.setPointSize(max(11, f.pointSize() + 2))
        f.setBold(True)
        title.setFont(f)
        desc = QtWidgets.QLabel("为保证稳定性，请确认以下条件：")
        desc.setStyleSheet("color:#475569;")
        title_box.addWidget(title)
        title_box.addWidget(desc)
        header.addLayout(title_box, 1)
        root.addLayout(header)

        # Checklist（动态检测）
        box = QtWidgets.QFrame()
        box.setObjectName("confirmBox")
        box.setStyleSheet(
            "QFrame#confirmBox{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;}"
        )
        v = QtWidgets.QVBoxLayout(box)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        self._check_labels: list[QtWidgets.QLabel] = []

        def add_check_line() -> QtWidgets.QLabel:
            lab = QtWidgets.QLabel("")
            lab.setWordWrap(True)
            v.addWidget(lab)
            self._check_labels.append(lab)
            return lab

        self._lab_win = add_check_line()
        self._lab_res = add_check_line()
        self._lab_scale = add_check_line()
        self._lab_hint = add_check_line()

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_recheck = QtWidgets.QPushButton("重新检测")
        self.btn_recheck.setObjectName("secondaryBtn")
        btn_row.addWidget(self.btn_recheck)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        root.addWidget(box)

        self.chk_ack = QtWidgets.QCheckBox("我已确认以上条件")
        self.chk_ack.setChecked(True)
        root.addWidget(self.chk_ack)

        # Buttons
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_ok = QtWidgets.QPushButton("继续运行")
        self.btn_ok.setObjectName("primaryBtn")
        self.btn_ok.setDefault(True)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)
        self.chk_ack.toggled.connect(self._refresh_checks)
        self.btn_recheck.clicked.connect(self._refresh_checks)

        self._refresh_checks()

    def _set_check(self, lab: QtWidgets.QLabel, ok: bool, text: str) -> None:
        color = "#166534" if ok else "#b91c1c"
        mark = "✓" if ok else "✗"
        lab.setText(f"<span style='color:{color};font-weight:600'>{mark}</span> {text}")

    def _refresh_checks(self) -> None:
        # 1) 窗口是否存在且未最小化
        st = get_window_status(self._title_contains)
        win_ok = bool(st.get("found")) and not bool(st.get("minimized"))
        if not st.get("found"):
            self._set_check(self._lab_win, False, f"窗口未找到：标题包含 “{self._title_contains}”")
        elif st.get("minimized"):
            self._set_check(self._lab_win, False, f"窗口已最小化：{st.get('title') or self._title_contains}")
        else:
            extra = "（已最大化）" if st.get("maximized") else "（未最大化）"
            self._set_check(self._lab_win, True, f"窗口已打开且可见：{st.get('title') or self._title_contains} {extra}")

        # 2) 分辨率检查（当前只支持 1080P）
        w, h = get_primary_screen_size()
        res_ok = (w, h) == (1920, 1080)
        self._set_check(self._lab_res, res_ok, f"屏幕分辨率：{w}x{h}（要求 1920x1080）")

        # 3) 缩放检查（尽力检测）
        scale = st.get("scale_percent")
        if isinstance(scale, int):
            self._set_check(self._lab_scale, scale == 100, f"系统缩放：{scale}%（建议 100%）")
        else:
            self._set_check(self._lab_scale, True, "系统缩放：无法检测（建议 100%）")

        self._set_check(self._lab_hint, True, "运行期间不要操作鼠标/键盘")

        # OK 按钮：窗口不可用时禁止继续（避免必然跑飞）
        scale_ok = not isinstance(scale, int) or scale == 100
        can_continue = win_ok and res_ok and scale_ok and bool(self.chk_ack.isChecked())
        self.btn_ok.setEnabled(can_continue)


class ImportAirStepDialog(QtWidgets.QDialog):
    """
    导入 .air 用例为平台步骤（Step）。
    """

    def __init__(self, default_name: str, default_step_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入 .air 步骤")
        self.setModal(True)
        self.setMinimumWidth(560)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        title = QtWidgets.QLabel("将 .air 用例导入为“步骤库 Step”")
        f = title.font()
        f.setPointSize(max(11, f.pointSize() + 1))
        f.setBold(True)
        title.setFont(f)
        subtitle = QtWidgets.QLabel("只迁移 touch/wait/swipe/sleep + Template（其他复杂逻辑会提示）")
        subtitle.setStyleSheet("color:#475569;")
        root.addWidget(title)
        root.addWidget(subtitle)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        def mk_label(text: str) -> QtWidgets.QLabel:
            lab = QtWidgets.QLabel(text)
            lab.setStyleSheet("color:#334155;")
            lab.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            lab.setFixedWidth(90)
            return lab

        self.edit_name = QtWidgets.QLineEdit(default_name)
        self.edit_step_id = QtWidgets.QLineEdit(default_step_id)
        self.edit_step_id.setPlaceholderText("例如：crealityscan.create_scan")

        hint = QtWidgets.QLabel("提示：步骤 ID 仅允许字母、数字、下划线和点，并且至少包含一个点")
        hint.setStyleSheet("color:#64748b;")

        grid.addWidget(mk_label("步骤名称"), 0, 0)
        grid.addWidget(self.edit_name, 0, 1)
        grid.addWidget(mk_label("步骤 ID"), 1, 0)
        grid.addWidget(self.edit_step_id, 1, 1)
        root.addLayout(grid)
        root.addWidget(hint)

        # Buttons
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_ok = QtWidgets.QPushButton("导入")
        self.btn_ok.setObjectName("primaryBtn")
        self.btn_ok.setDefault(True)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)

    def values(self) -> Tuple[str, str]:
        return self.edit_name.text().strip(), self.edit_step_id.text().strip()


class PresetPickerDialog(QtWidgets.QDialog):
    """让用户从预设方案列表中选择一项。"""

    def __init__(self, title: str, presets: Iterable[Tuple[str, str]], parent=None):
        """
        presets: (name_cn, key)
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(520)
        self._selected: Tuple[str, str] = ("", "")

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        header = QtWidgets.QLabel("请选择一个预设方案")
        f = header.font()
        f.setBold(True)
        header.setFont(f)
        header.setStyleSheet("color:#1f2a44;")
        root.addWidget(header)

        self.edit_filter = QtWidgets.QLineEdit()
        self.edit_filter.setPlaceholderText("搜索（支持中文名称或内部标识）")
        root.addWidget(self.edit_filter)

        self.list = QtWidgets.QListWidget()
        self.list.setAlternatingRowColors(True)
        root.addWidget(self.list, 1)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_ok = QtWidgets.QPushButton("确定")
        self.btn_ok.setObjectName("primaryBtn")
        self.btn_ok.setDefault(True)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._accept_selected)
        self.list.itemDoubleClicked.connect(lambda _: self._accept_selected())
        self.edit_filter.textChanged.connect(self._apply_filter)

        self._all_items: list[QtWidgets.QListWidgetItem] = []
        for name_cn, key in presets:
            it = QtWidgets.QListWidgetItem(name_cn)
            it.setData(QtCore.Qt.UserRole, (name_cn, key))
            self._all_items.append(it)

        self._apply_filter()
        if self.list.count() > 0:
            self.list.setCurrentRow(0)

    def _apply_filter(self) -> None:
        text = self.edit_filter.text().strip().lower()
        self.list.clear()
        for it in self._all_items:
            name_cn, key = it.data(QtCore.Qt.UserRole) or ("", "")
            hay = f"{name_cn} {key}".lower()
            if text and text not in hay:
                continue
            new_it = QtWidgets.QListWidgetItem(str(name_cn or ""))
            new_it.setData(QtCore.Qt.UserRole, (name_cn, key))
            self.list.addItem(new_it)

    def _accept_selected(self) -> None:
        cur = self.list.currentItem()
        if not cur:
            return
        data = cur.data(QtCore.Qt.UserRole)
        if isinstance(data, tuple) and len(data) == 2:
            self._selected = (str(data[0] or ""), str(data[1] or ""))
        self.accept()

    def selected(self) -> Tuple[str, str]:
        return self._selected


class TaskCreationWizardDialog(QtWidgets.QDialog):
    """从动态 preset 创建标准扫描任务。"""

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.project_root = Path(project_root)
        self._module_name = ""
        self._presets: list[ScanPreset] = []
        self._selected_order: list[str] = []
        self._module_cards: dict[str, QtWidgets.QFrame] = {}
        self._active_category = "全部"
        self._last_default_task_name = ""
        self._syncing_fps = False
        self.free_edit_requested = False
        self.free_edit_default_name = ""

        self.setWindowTitle("创建测试任务")
        self.setModal(True)
        self.resize(1220, 820)
        self.setMinimumSize(1000, 680)
        self.setObjectName("taskCreationWizard")
        self.setFont(QtGui.QFont("Microsoft YaHei UI", 9))
        self.setStyleSheet(self._wizard_stylesheet())

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QtWidgets.QFrame()
        header.setObjectName("wizardHeader")
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 14)
        header_layout.setSpacing(4)
        title = QtWidgets.QLabel("创建测试任务")
        title.setObjectName("wizardTitle")
        subtitle = QtWidgets.QLabel("从真实 preset 生成标准扫描任务，所有自动规则会在创建前显示。")
        subtitle.setObjectName("wizardMuted")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        self.step_labels: list[QtWidgets.QLabel] = []
        self.step_cards: list[QtWidgets.QFrame] = []
        self.step_numbers: list[QtWidgets.QLabel] = []
        self.step_details: list[QtWidgets.QLabel] = []
        stepper = QtWidgets.QFrame()
        stepper.setObjectName("wizardStepper")
        step_row = QtWidgets.QHBoxLayout(stepper)
        step_row.setContentsMargins(24, 9, 24, 9)
        step_row.setSpacing(8)
        for index, (text, detail) in enumerate(
            (("模组与连接", "确定设备上下文"), ("选择扫描模式", "支持多选"), ("生成方式", "开流/后处理/帧率统计")),
            start=1,
        ):
            card = QtWidgets.QFrame()
            card.setObjectName("stepCard")
            card_layout = QtWidgets.QHBoxLayout(card)
            card_layout.setContentsMargins(10, 5, 10, 5)
            card_layout.setSpacing(10)
            number = QtWidgets.QLabel(str(index))
            number.setObjectName("stepNumber")
            number.setAlignment(QtCore.Qt.AlignCenter)
            number.setFixedSize(30, 30)
            copy = QtWidgets.QVBoxLayout()
            copy.setSpacing(1)
            label = QtWidgets.QLabel(text)
            label.setObjectName("stepTitle")
            detail_label = QtWidgets.QLabel(detail)
            detail_label.setObjectName("stepDetail")
            copy.addWidget(label)
            copy.addWidget(detail_label)
            card_layout.addWidget(number)
            card_layout.addLayout(copy)
            card_layout.addStretch(1)
            self.step_cards.append(card)
            self.step_numbers.append(number)
            self.step_labels.append(label)
            self.step_details.append(detail_label)
            step_row.addWidget(card, 1)
        root.addWidget(stepper)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self._build_module_page())
        self.stack.addWidget(self._build_preset_page())
        self.stack.addWidget(self._build_options_page())
        root.addWidget(self.stack, 1)

        footer_frame = QtWidgets.QFrame()
        footer_frame.setObjectName("wizardFooter")
        footer = QtWidgets.QHBoxLayout(footer_frame)
        footer.setContentsMargins(22, 13, 22, 13)
        footer.setSpacing(10)
        self.footer_summary = QtWidgets.QLabel("请选择一个扫描模组")
        self.footer_summary.setObjectName("wizardMuted")
        footer.addWidget(self.footer_summary, 1)
        self.btn_free_edit = QtWidgets.QPushButton("自由编排任务")
        self.btn_free_edit.setObjectName("secondaryBtn")
        self.btn_free_edit.setToolTip("跳过向导，新建空任务后从步骤库手动编排")
        self.btn_free_edit.clicked.connect(self._request_free_edit)
        footer.addWidget(self.btn_free_edit)
        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_back = QtWidgets.QPushButton("上一步")
        self.btn_back.setObjectName("secondaryBtn")
        self.btn_next = QtWidgets.QPushButton("下一步：选择模式")
        self.btn_next.setObjectName("primaryBtn")
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_back)
        footer.addWidget(self.btn_next)
        root.addWidget(footer_frame)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_back.clicked.connect(self._go_back)
        self.btn_next.clicked.connect(self._go_next)
        self._load_modules()
        self._refresh_page_state()

    @staticmethod
    def _wizard_stylesheet() -> str:
        return """
        QDialog#taskCreationWizard { background:#ffffff; color:#18283d; font-family:"Microsoft YaHei UI"; font-size:13px; }
        QFrame#wizardHeader { background:#ffffff; border-bottom:1px solid #d5dfec; }
        QLabel#wizardTitle { color:#18283d; font-size:20px; font-weight:700; }
        QLabel#wizardMuted { color:#65758b; font-size:12px; }
        QFrame#wizardStepper { background:#fbfcfe; border-bottom:1px solid #d5dfec; }
        QFrame#stepCard { background:transparent; border:0; border-radius:10px; }
        QFrame#stepCard[state="active"] { background:#edf4ff; }
        QLabel#stepNumber { color:#65758b; border:1px solid #becbdb; border-radius:15px; font-weight:700; }
        QLabel#stepNumber[state="active"] { color:#ffffff; background:#2e6fd8; border-color:#2e6fd8; }
        QLabel#stepNumber[state="done"] { color:#167553; background:#e6f5ef; border-color:#b8dfd1; }
        QLabel#stepTitle { color:#42566f; font-size:13px; font-weight:700; }
        QLabel#stepTitle[state="active"] { color:#2358aa; }
        QLabel#stepDetail { color:#7a899c; font-size:11px; }
        QStackedWidget { background:#ffffff; }
        QFrame#pageAside, QFrame#categoryPane { background:#f6f9fd; }
        QFrame#pageAside { border-left:1px solid #d5dfec; }
        QFrame#categoryPane { border-right:1px solid #d5dfec; }
        QFrame#selectedPane, QFrame#summaryPane { background:#f7faff; border-left:1px solid #d5dfec; }
        QLabel#pageTitle { color:#18283d; font-size:21px; font-weight:700; }
        QLabel#sectionTitle { color:#18283d; font-size:14px; font-weight:700; }
        QLabel#asideValue { color:#2358aa; font-size:25px; font-weight:700; }
        QLabel#eyebrow { color:#65758b; font-size:11px; font-weight:700; }
        QLabel#ruleHint { color:#785018; background:#fff4db; border-radius:10px; padding:12px; }
        QFrame#slideRailOption { background:#eef5ff; border:1px solid #c7d9f4; border-radius:10px; }
        QListWidget#moduleList { background:transparent; border:0; outline:0; padding:0; }
        QListWidget#moduleList::item { background:transparent; border:0; padding:0; margin:0; }
        QFrame#moduleCard { background:#ffffff; border:1px solid #d5dfec; border-radius:13px; }
        QFrame#moduleCard[selected="true"] { background:#edf4ff; border:2px solid #2e6fd8; }
        QLabel#moduleName { color:#18283d; font-size:16px; font-weight:700; }
        QLabel#moduleCount { color:#65758b; font-size:11px; }
        QLabel#moduleTags { color:#48617e; background:#f0f4f9; border-radius:5px; padding:4px 7px; font-size:10px; }
        QLineEdit, QSpinBox { min-height:38px; background:#ffffff; color:#18283d; border:1px solid #d5dfec; border-radius:10px; padding:0 10px; selection-background-color:#dce9ff; }
        QLineEdit:focus, QSpinBox:focus { border-color:#2e6fd8; }
        QListWidget#presetList { background:#ffffff; border:0; border-radius:0; outline:0; }
        QListWidget#presetList::item { min-height:44px; padding:5px 8px; border-bottom:1px solid #e4eaf2; }
        QListWidget#presetList::item:hover { background:#f7faff; color:#2358aa; }
        QListWidget#selectedList { background:transparent; border:0; outline:0; font-size:11px; }
        QListWidget#selectedList::item { padding:8px 2px; border-bottom:1px solid #e2e8f0; }
        QPushButton#categoryButton { min-height:36px; color:#42566f; background:transparent; border:0; border-radius:9px; text-align:left; padding:0 10px; }
        QPushButton#categoryButton:checked { color:#2358aa; background:#dce9ff; font-weight:700; }
        QRadioButton#taskKindCard { min-height:86px; color:#18283d; background:#ffffff; border:1px solid #d5dfec; border-radius:13px; padding:14px; font-size:13px; font-weight:700; }
        QRadioButton#taskKindCard:checked { background:#edf4ff; border:2px solid #2e6fd8; color:#2358aa; }
        QRadioButton#taskKindCard::indicator { width:16px; height:16px; }
        QFrame#segmentContainer { background:#edf2f8; border-radius:10px; }
        QPushButton#segmentButton { min-width:86px; min-height:34px; color:#42566f; background:transparent; border:0; border-radius:8px; }
        QPushButton#segmentButton:checked { color:#2358aa; background:#ffffff; border:1px solid #c8d6e8; font-weight:700; }
        QFrame#metricGrid { background:#d5dfec; border-radius:10px; }
        QFrame#metricCell { background:#ffffff; }
        QLabel#metricLabel { color:#65758b; font-size:10px; }
        QLabel#metricValue { color:#18283d; font-size:14px; font-weight:700; }
        QLabel#flowText { color:#42566f; font-size:11px; padding:5px 0; }
        QLabel#errorText { color:#a73333; font-size:11px; }
        QFrame#wizardFooter { background:#fbfcfe; border-top:1px solid #d5dfec; }
        QPushButton { min-height:38px; border-radius:10px; padding:0 15px; font-weight:600; }
        QPushButton#primaryBtn { color:#ffffff; background:#2e6fd8; border:1px solid #2e6fd8; }
        QPushButton#primaryBtn:hover { background:#2358aa; }
        QPushButton#primaryBtn:disabled { color:#8795a8; background:#dfe6ef; border-color:#dfe6ef; }
        QPushButton#secondaryBtn { color:#18283d; background:#ffffff; border:1px solid #d5dfec; }
        QPushButton#secondaryBtn:hover { background:#edf4ff; border-color:#9db8df; }
        QCheckBox { color:#42566f; spacing:7px; }
        """

    def _build_connection_selector(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(widget)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        label = QtWidgets.QLabel("连接方式")
        label.setObjectName("sectionTitle")
        column.addWidget(label)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(0)
        self.connection_group = QtWidgets.QButtonGroup(self)
        self.connection_group.setExclusive(True)
        segments = QtWidgets.QFrame()
        segments.setObjectName("segmentContainer")
        segment_layout = QtWidgets.QHBoxLayout(segments)
        segment_layout.setContentsMargins(3, 3, 3, 3)
        segment_layout.setSpacing(2)
        self.btn_usb = QtWidgets.QPushButton(CONNECTION_USB)
        self.btn_wifi = QtWidgets.QPushButton(CONNECTION_WIFI)
        for button in (self.btn_usb, self.btn_wifi):
            button.setObjectName("segmentButton")
            button.setCheckable(True)
            self.connection_group.addButton(button)
            segment_layout.addWidget(button)
            button.toggled.connect(self._connection_changed)
        self.btn_usb.setChecked(True)
        row.addWidget(segments)
        row.addStretch(1)
        column.addLayout(row)

        help_label = QtWidgets.QLabel("第二步只显示当前连接可用的模式；切换连接会移除不兼容的已选模式。")
        help_label.setObjectName("wizardMuted")
        help_label.setWordWrap(True)
        column.addWidget(help_label)
        widget.setVisible(False)
        return widget

    def _build_module_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 26, 24)
        content_layout.setSpacing(7)
        heading = QtWidgets.QLabel("这次要测试哪个模组？")
        heading.setObjectName("pageTitle")
        content_layout.addWidget(heading)
        hint = QtWidgets.QLabel("选择后将动态读取该模组的 presets.json；以后新增或修改模式会自动同步。")
        hint.setObjectName("wizardMuted")
        content_layout.addWidget(hint)
        self.module_list = QtWidgets.QListWidget()
        self.module_list.setObjectName("moduleList")
        self.module_list.setViewMode(QtWidgets.QListView.IconMode)
        self.module_list.setResizeMode(QtWidgets.QListView.Adjust)
        self.module_list.setMovement(QtWidgets.QListView.Static)
        self.module_list.setWrapping(True)
        self.module_list.setSpacing(6)
        self.module_list.setGridSize(QtCore.QSize(270, 112))
        self.module_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.module_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.module_list.currentItemChanged.connect(self._module_changed)
        self.module_list.itemDoubleClicked.connect(lambda _: self._go_next())
        content_layout.addSpacing(10)
        content_layout.addWidget(self.module_list, 1)
        layout.addWidget(content, 1)

        aside = QtWidgets.QFrame()
        aside.setObjectName("pageAside")
        aside.setFixedWidth(300)
        aside_layout = QtWidgets.QVBoxLayout(aside)
        aside_layout.setContentsMargins(24, 25, 24, 24)
        aside_layout.setSpacing(8)
        aside_title = QtWidgets.QLabel("当前选择")
        aside_title.setObjectName("sectionTitle")
        self.module_aside_value = QtWidgets.QLabel("尚未选择")
        self.module_aside_value.setObjectName("asideValue")
        self.module_aside_help = QtWidgets.QLabel("选择一个模组后继续。切换模组会清空当前已选模式。")
        self.module_aside_help.setObjectName("wizardMuted")
        self.module_aside_help.setWordWrap(True)
        self.connection_widget = self._build_connection_selector()
        slide_rail_widget = QtWidgets.QFrame()
        slide_rail_widget.setObjectName("slideRailOption")
        slide_rail_layout = QtWidgets.QVBoxLayout(slide_rail_widget)
        slide_rail_layout.setContentsMargins(12, 11, 12, 11)
        slide_rail_layout.setSpacing(4)
        self.chk_slide_rail = QtWidgets.QCheckBox("启用滑轨")
        self.chk_slide_rail.setToolTip(
            "每个扫描模式前自动插入滑轨切换位置步骤：线激光→中物体、散斑按大小对应、人脸→人脸、人体→大物体"
        )
        slide_rail_layout.addWidget(self.chk_slide_rail)
        slide_rail_hint = QtWidgets.QLabel("创建任务时自动加入对应的滑轨切换位置步骤")
        slide_rail_hint.setObjectName("wizardMuted")
        slide_rail_hint.setWordWrap(True)
        slide_rail_layout.addWidget(slide_rail_hint)
        info = QtWidgets.QLabel("• 扫描模式来自各模组 preset 配置\n\n• 多选模式会生成连续任务块\n\n• 框架点与 Pika 特殊流程自动补齐")
        info.setObjectName("wizardMuted")
        info.setWordWrap(True)
        aside_layout.addWidget(aside_title)
        aside_layout.addWidget(self.module_aside_value)
        aside_layout.addWidget(self.module_aside_help)
        aside_layout.addSpacing(14)
        aside_layout.addWidget(self.connection_widget)
        aside_layout.addSpacing(10)
        aside_layout.addWidget(slide_rail_widget)
        aside_layout.addSpacing(14)
        aside_layout.addWidget(info)
        aside_layout.addStretch(1)
        layout.addWidget(aside)
        return page

    def _build_preset_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        category_pane = QtWidgets.QFrame()
        category_pane.setObjectName("categoryPane")
        category_pane.setFixedWidth(210)
        category_layout = QtWidgets.QVBoxLayout(category_pane)
        category_layout.setContentsMargins(16, 22, 16, 18)
        category_layout.setSpacing(4)
        category_label = QtWidgets.QLabel("模式分类")
        category_label.setObjectName("eyebrow")
        category_layout.addWidget(category_label)
        self.category_buttons: dict[str, QtWidgets.QPushButton] = {}
        category_group = QtWidgets.QButtonGroup(self)
        category_group.setExclusive(True)
        for category in ("全部", "线激光", "散斑", "框架点", "人像"):
            button = QtWidgets.QPushButton("全部模式" if category == "全部" else category)
            button.setObjectName("categoryButton")
            button.setCheckable(True)
            button.setChecked(category == "全部")
            button.clicked.connect(lambda _checked=False, value=category: self._set_category(value))
            category_group.addButton(button)
            self.category_buttons[category] = button
            category_layout.addWidget(button)
        category_layout.addStretch(1)
        layout.addWidget(category_pane)

        mode_pane = QtWidgets.QWidget()
        mode_layout = QtWidgets.QVBoxLayout(mode_pane)
        mode_layout.setContentsMargins(22, 21, 22, 18)
        mode_layout.setSpacing(8)
        top = QtWidgets.QHBoxLayout()
        self.preset_heading = QtWidgets.QLabel("选择扫描模式")
        self.preset_heading.setObjectName("pageTitle")
        top.addWidget(self.preset_heading)
        top.addStretch(1)
        self.btn_refresh_presets = QtWidgets.QPushButton("刷新 preset")
        self.btn_refresh_presets.setObjectName("secondaryBtn")
        self.btn_refresh_presets.clicked.connect(self._reload_presets)
        top.addWidget(self.btn_refresh_presets)
        mode_layout.addLayout(top)
        mode_hint = QtWidgets.QLabel("支持多选；任务默认按 preset 顺序生成，也可在下一步随机打乱。")
        mode_hint.setObjectName("wizardMuted")
        mode_layout.addWidget(mode_hint)

        fps_row = QtWidgets.QHBoxLayout()
        fps_row.setSpacing(8)
        self.chk_fps_stat = QtWidgets.QCheckBox("帧率统计任务")
        self.chk_fps_stat.setToolTip(
            "勾选后自动按业务顺序勾选扫描模式；第三步自动选择「帧率统计」并固定 1000 帧。"
        )
        fps_row.addWidget(self.chk_fps_stat)
        fps_hint = QtWidgets.QLabel("自动按业务顺序勾选模式 · 第三步固定 1000 帧")
        fps_hint.setObjectName("wizardMuted")
        fps_row.addWidget(fps_hint)
        fps_row.addStretch(1)
        mode_layout.addSpacing(2)
        mode_layout.addLayout(fps_row)

        toolbar = QtWidgets.QHBoxLayout()
        self.preset_filter = QtWidgets.QLineEdit()
        self.preset_filter.setPlaceholderText("搜索模式名称或内部 key")
        self.preset_filter.textChanged.connect(self._apply_preset_filter)
        toolbar.addWidget(self.preset_filter, 1)
        self.btn_select_visible = QtWidgets.QPushButton("全选当前结果")
        self.btn_select_visible.setObjectName("secondaryBtn")
        self.btn_clear_presets = QtWidgets.QPushButton("清空")
        self.btn_clear_presets.setObjectName("secondaryBtn")
        self.btn_select_visible.clicked.connect(self._select_visible_presets)
        self.btn_clear_presets.clicked.connect(self._clear_presets)
        toolbar.addWidget(self.btn_select_visible)
        toolbar.addWidget(self.btn_clear_presets)
        mode_layout.addSpacing(7)
        mode_layout.addLayout(toolbar)

        self.preset_list = QtWidgets.QListWidget()
        self.preset_list.setObjectName("presetList")
        self.preset_list.itemChanged.connect(self._preset_check_changed)
        mode_layout.addWidget(self.preset_list, 1)
        layout.addWidget(mode_pane, 1)

        selected_pane = QtWidgets.QFrame()
        selected_pane.setObjectName("selectedPane")
        selected_pane.setFixedWidth(280)
        selected_layout = QtWidgets.QVBoxLayout(selected_pane)
        selected_layout.setContentsMargins(18, 22, 18, 18)
        selected_layout.setSpacing(6)
        selected_title = QtWidgets.QLabel("已选模式")
        selected_title.setObjectName("eyebrow")
        selected_layout.addWidget(selected_title)
        self.selected_count_label = QtWidgets.QLabel("0 个")
        self.selected_count_label.setObjectName("asideValue")
        selected_layout.addWidget(self.selected_count_label)
        self.selected_list = QtWidgets.QListWidget()
        self.selected_list.setObjectName("selectedList")
        selected_layout.addWidget(self.selected_list, 1)
        layout.addWidget(selected_pane)

        self.chk_fps_stat.toggled.connect(self._fps_stat_check_toggled)
        return page

    def _build_options_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        form_box = QtWidgets.QWidget()
        form = QtWidgets.QVBoxLayout(form_box)
        form.setContentsMargins(28, 23, 28, 22)
        form.setSpacing(8)
        options_title = QtWidgets.QLabel("最后确认任务生成方式")
        options_title.setObjectName("pageTitle")
        options_hint = QtWidgets.QLabel("系统会基于已选模式生成标准步骤，自动规则会在右侧摘要中明确标记。")
        options_hint.setObjectName("wizardMuted")
        form.addWidget(options_title)
        form.addWidget(options_hint)

        name_label = QtWidgets.QLabel("任务名称")
        name_label.setObjectName("eyebrow")
        form.addSpacing(10)
        form.addWidget(name_label)

        self.edit_task_name = QtWidgets.QLineEdit()
        form.addWidget(self.edit_task_name)

        kind_label = QtWidgets.QLabel("任务类型")
        kind_label.setObjectName("eyebrow")
        form.addSpacing(8)
        form.addWidget(kind_label)
        kind_widget = QtWidgets.QWidget()
        kind_row = QtWidgets.QHBoxLayout(kind_widget)
        kind_row.setContentsMargins(0, 0, 0, 0)
        kind_row.setSpacing(12)
        self.radio_open = QtWidgets.QRadioButton("开流测试\n配置参数 → 扫描至目标帧 → 完成")
        self.radio_post = QtWidgets.QRadioButton("后处理测试\n开流步骤 + 融合 → 封装 → 贴图")
        self.radio_fps = QtWidgets.QRadioButton("帧率统计\n开流步骤 + 预览/扫描/稳定帧率")
        for radio in (self.radio_open, self.radio_post, self.radio_fps):
            radio.setObjectName("taskKindCard")
        self.radio_open.setChecked(True)
        kind_row.addWidget(self.radio_open)
        kind_row.addWidget(self.radio_post)
        kind_row.addWidget(self.radio_fps)
        form.addWidget(kind_widget)

        frames_label = QtWidgets.QLabel("目标帧数")
        frames_label.setObjectName("eyebrow")
        form.addSpacing(8)
        form.addWidget(frames_label)
        self.spin_target_frames = QtWidgets.QSpinBox()
        self.spin_target_frames.setRange(1, 100000)
        self.spin_target_frames.setValue(200)
        self.spin_target_frames.setSingleStep(50)
        self.spin_target_frames.setSuffix(" 帧")
        self.spin_target_frames.setFixedWidth(180)
        form.addWidget(self.spin_target_frames, 0, QtCore.Qt.AlignLeft)

        random_widget = QtWidgets.QWidget()
        random_row = QtWidgets.QHBoxLayout(random_widget)
        random_row.setContentsMargins(0, 0, 0, 0)
        self.chk_random_order = QtWidgets.QCheckBox("随机打乱已选模式顺序")
        self.btn_reshuffle = QtWidgets.QPushButton("重新打乱")
        self.btn_reshuffle.setObjectName("secondaryBtn")
        self.btn_reshuffle.setEnabled(False)
        random_row.addWidget(self.chk_random_order)
        random_row.addWidget(self.btn_reshuffle)
        random_row.addStretch(1)
        form.addSpacing(7)
        form.addWidget(random_widget)
        self.random_widget = random_widget

        pika_hint = QtWidgets.QLabel("Pika 将按任务库现有规律自动加入稳定性等待步骤。")
        pika_hint.setWordWrap(True)
        pika_hint.setObjectName("ruleHint")
        self.pika_hint = pika_hint
        form.addSpacing(6)
        form.addWidget(pika_hint)
        form.addStretch(1)
        layout.addWidget(form_box, 1)

        summary_box = QtWidgets.QFrame()
        summary_box.setObjectName("summaryPane")
        summary_box.setFixedWidth(390)
        summary_layout = QtWidgets.QVBoxLayout(summary_box)
        summary_layout.setContentsMargins(24, 24, 24, 20)
        summary_layout.setSpacing(10)
        summary_title = QtWidgets.QLabel("任务生成摘要")
        summary_title.setObjectName("sectionTitle")
        summary_layout.addWidget(summary_title)
        self.summary_status = QtWidgets.QLabel("可生成")
        self.summary_status.setObjectName("asideValue")
        summary_layout.addWidget(self.summary_status)
        metric_grid = QtWidgets.QFrame()
        metric_grid.setObjectName("metricGrid")
        metric_layout = QtWidgets.QGridLayout(metric_grid)
        metric_layout.setContentsMargins(1, 1, 1, 1)
        metric_layout.setHorizontalSpacing(1)
        metric_layout.setVerticalSpacing(1)
        self.summary_metrics: dict[str, QtWidgets.QLabel] = {}
        for index, (key, label) in enumerate((("module", "模组"), ("modes", "模式"), ("frames", "目标帧数"), ("steps", "预计步骤"))):
            cell = QtWidgets.QFrame()
            cell.setObjectName("metricCell")
            cell_layout = QtWidgets.QVBoxLayout(cell)
            cell_layout.setContentsMargins(11, 9, 11, 9)
            metric_label = QtWidgets.QLabel(label)
            metric_label.setObjectName("metricLabel")
            metric_value = QtWidgets.QLabel("-")
            metric_value.setObjectName("metricValue")
            cell_layout.addWidget(metric_label)
            cell_layout.addWidget(metric_value)
            self.summary_metrics[key] = metric_value
            metric_layout.addWidget(cell, index // 2, index % 2)
        summary_layout.addWidget(metric_grid)
        self.summary_text = QtWidgets.QLabel()
        self.summary_text.setObjectName("flowText")
        self.summary_text.setWordWrap(True)
        self.summary_text.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        summary_layout.addWidget(self.summary_text, 1)
        self.compatibility_error = QtWidgets.QLabel("")
        self.compatibility_error.setWordWrap(True)
        self.compatibility_error.setObjectName("errorText")
        summary_layout.addWidget(self.compatibility_error)
        layout.addWidget(summary_box)

        self.radio_open.toggled.connect(self._options_changed)
        self.radio_post.toggled.connect(self._options_changed)
        self.radio_fps.toggled.connect(self._fps_stat_kind_toggled)
        self.spin_target_frames.valueChanged.connect(self._options_changed)
        self.edit_task_name.textChanged.connect(self._refresh_page_state)
        self.chk_random_order.toggled.connect(self._random_toggled)
        self.chk_slide_rail.toggled.connect(self._options_changed)
        self.btn_reshuffle.clicked.connect(self._reshuffle)
        return page

    def _load_modules(self) -> None:
        self.module_list.clear()
        self._module_cards.clear()
        for source in sorted(MODULE_PRESET_SOURCES.values(), key=lambda item: item.display_name.lower()):
            try:
                preset_count = len(list_module_presets(source.module_name, project_root=self.project_root))
                count_text = f"{preset_count} 个模式"
            except ValueError as exc:
                count_text = "preset 读取失败"
                preset_count = 0
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.UserRole, source.module_name)
            item.setSizeHint(QtCore.QSize(260, 102))
            self.module_list.addItem(item)

            card = QtWidgets.QFrame()
            card.setObjectName("moduleCard")
            card.setProperty("selected", False)
            card.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(15, 13, 15, 13)
            card_layout.setSpacing(8)
            name_row = QtWidgets.QHBoxLayout()
            name = QtWidgets.QLabel(source.display_name)
            name.setObjectName("moduleName")
            count = QtWidgets.QLabel(count_text)
            count.setObjectName("moduleCount")
            name_row.addWidget(name)
            name_row.addStretch(1)
            name_row.addWidget(count)
            card_layout.addLayout(name_row)
            tags = []
            if source.supports_connection:
                tags.append("USB / Wi-Fi")
            if source.pika_waits:
                tags.append("特殊等待")
            if preset_count:
                tags.append("动态 preset")
            tags_row = QtWidgets.QHBoxLayout()
            tags_row.setSpacing(5)
            for tag_text in tags:
                tag = QtWidgets.QLabel(tag_text)
                tag.setObjectName("moduleTags")
                tag.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
                tags_row.addWidget(tag)
            tags_row.addStretch(1)
            card_layout.addLayout(tags_row)
            for label in card.findChildren(QtWidgets.QLabel):
                label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            self.module_list.setItemWidget(item, card)
            self._module_cards[source.module_name] = card

    def _module_changed(self, current, _previous) -> None:
        module_name = str(current.data(QtCore.Qt.UserRole) or "") if current else ""
        if module_name == self._module_name:
            return
        self._module_name = module_name
        self._selected_order.clear()
        for name, card in self._module_cards.items():
            card.setProperty("selected", name == module_name)
            card.style().unpolish(card)
            card.style().polish(card)
        if module_name:
            self._reload_presets()
            self._set_default_task_name()
        self._refresh_page_state()

    def _reload_presets(self) -> None:
        if not self._module_name:
            return
        source = MODULE_PRESET_SOURCES[self._module_name]
        connection_type = self._connection_type() if source.supports_connection else ""
        try:
            presets = list_module_presets(
                self._module_name,
                project_root=self.project_root,
                connection_type=connection_type,
            )
        except ValueError as exc:
            show_error(self, "无法读取 preset", str(exc))
            return
        available_keys = {preset.key for preset in presets}
        self._selected_order = [key for key in self._selected_order if key in available_keys]
        self._presets = presets
        connection = f" · {connection_type}" if connection_type else ""
        self.preset_heading.setText(f"{source.display_name} 的扫描模式（{len(presets)}{connection}）")
        self._populate_preset_list()
        self._refresh_page_state()

    def _connection_label(self, preset: ScanPreset) -> str:
        return " / ".join(preset.connections) if preset.connections else "USB / Wi-Fi 共用"

    @staticmethod
    def _preset_category(preset: ScanPreset) -> str:
        name = preset.name
        if "人脸" in name or "人体" in name:
            return "人像"
        if "框架点" in name:
            return "框架点"
        if "线激光" in name or "line_laser" in preset.key:
            return "线激光"
        return "散斑"

    def _set_category(self, category: str) -> None:
        self._active_category = category
        self._populate_preset_list()

    def _populate_preset_list(self) -> None:
        query = self.preset_filter.text().strip().lower() if hasattr(self, "preset_filter") else ""
        self.preset_list.blockSignals(True)
        try:
            self.preset_list.clear()
            for preset in self._presets:
                haystack = f"{preset.name} {preset.key} {' '.join(preset.aliases)}".lower()
                if query and query not in haystack:
                    continue
                category = self._preset_category(preset)
                if self._active_category != "全部" and category != self._active_category:
                    continue
                rule = " · 自动规则" if preset.task_profile == "frame_points" else ""
                item = QtWidgets.QListWidgetItem(
                    f"{preset.name}\n{category} · {self._connection_label(preset)}{rule}"
                )
                item.setData(QtCore.Qt.UserRole, preset.key)
                item.setToolTip(preset.key)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Checked if preset.key in self._selected_order else QtCore.Qt.Unchecked)
                self.preset_list.addItem(item)
        finally:
            self.preset_list.blockSignals(False)
        self._refresh_selected_list()

    def _refresh_selected_list(self) -> None:
        if not hasattr(self, "selected_list"):
            return
        by_key = {preset.key: preset for preset in self._presets}
        self.selected_list.clear()
        for index, key in enumerate(self._selected_order, start=1):
            preset = by_key.get(key)
            if preset:
                prefix = f"{index}. " if self.chk_random_order.isChecked() else ""
                self.selected_list.addItem(f"{prefix}{preset.name}")

    def _apply_preset_filter(self) -> None:
        self._populate_preset_list()

    def _checked_visible_keys(self) -> list[str]:
        keys: list[str] = []
        for index in range(self.preset_list.count()):
            item = self.preset_list.item(index)
            if item.checkState() == QtCore.Qt.Checked:
                keys.append(str(item.data(QtCore.Qt.UserRole) or ""))
        return keys

    def _preset_check_changed(self, item: QtWidgets.QListWidgetItem) -> None:
        key = str(item.data(QtCore.Qt.UserRole) or "")
        if item.checkState() == QtCore.Qt.Checked:
            if key and key not in self._selected_order:
                self._selected_order.append(key)
        elif key in self._selected_order:
            self._selected_order.remove(key)
        self._refresh_page_state()

    def _select_visible_presets(self) -> None:
        self.preset_list.blockSignals(True)
        try:
            for index in range(self.preset_list.count()):
                item = self.preset_list.item(index)
                key = str(item.data(QtCore.Qt.UserRole) or "")
                item.setCheckState(QtCore.Qt.Checked)
                if key and key not in self._selected_order:
                    self._selected_order.append(key)
        finally:
            self.preset_list.blockSignals(False)
        self._refresh_page_state()

    def _clear_presets(self) -> None:
        self._selected_order.clear()
        self._populate_preset_list()
        self._refresh_page_state()

    def _task_kind(self) -> str:
        if self._is_fps_stat():
            return TASK_KIND_FPS_STAT
        return TASK_KIND_POSTPROCESS if self.radio_post.isChecked() else TASK_KIND_OPEN_STREAM

    def _is_fps_stat(self) -> bool:
        return self.chk_fps_stat.isChecked()

    def _fps_stat_check_toggled(self, checked: bool) -> None:
        """第二步「帧率统计任务」勾选：自动按业务顺序选择模式并同步第三步任务类型。"""
        self._set_fps_stat_enabled(checked)
        self._options_changed()

    def _fps_stat_kind_toggled(self, checked: bool) -> None:
        """第三步「帧率统计」任务类型切换：与第二步勾选保持一致。"""
        self._set_fps_stat_enabled(checked)
        self._options_changed()

    def _set_fps_stat_enabled(self, enabled: bool) -> None:
        """保持第二步勾选与第三步「帧率统计」任务类型双向一致，并应用帧率统计规则。"""
        if self._syncing_fps:
            return
        self._syncing_fps = True
        try:
            if self.chk_fps_stat.isChecked() != enabled:
                self.chk_fps_stat.setChecked(enabled)
            if self.radio_fps.isChecked() != enabled:
                self.radio_fps.setChecked(enabled)
            if enabled:
                # 帧率统计固定扫描 1000 帧，且模式必须按业务顺序，禁止随机打乱。
                self.spin_target_frames.setValue(DEFAULT_FPS_STAT_FRAMES)
                if self.chk_random_order.isChecked():
                    self.chk_random_order.setChecked(False)
                self.random_widget.setVisible(False)
                self._apply_fps_stat_preset_selection()
            else:
                self.random_widget.setVisible(True)
                if not self.radio_open.isChecked() and not self.radio_post.isChecked():
                    self.radio_open.setChecked(True)
        finally:
            self._syncing_fps = False

    def _apply_fps_stat_preset_selection(self) -> None:
        """按业务规则自动预勾选模式并固定顺序；用户仍可在第二步取消个别模式。"""
        if not self._module_name or not self._is_fps_stat():
            return
        source = MODULE_PRESET_SOURCES[self._module_name]
        connection_type = self._connection_type() if source.supports_connection else ""
        try:
            plan = fps_stat_mode_plan(self._module_name, connection_type, project_root=self.project_root)
        except (KeyError, ValueError, OSError):
            return
        self._selected_order = [key for _, key in plan]
        if hasattr(self, "preset_list"):
            self._populate_preset_list()
        self._refresh_page_state()

    def _connection_type(self) -> str:
        return CONNECTION_WIFI if self.btn_wifi.isChecked() else CONNECTION_USB

    def _connection_changed(self, checked: bool) -> None:
        if not checked or not self._module_name:
            return
        source = MODULE_PRESET_SOURCES[self._module_name]
        if not source.supports_connection:
            return
        self._reload_presets()
        if self._is_fps_stat():
            self._apply_fps_stat_preset_selection()
        self._set_default_task_name()

    def _random_toggled(self, enabled: bool) -> None:
        self.btn_reshuffle.setEnabled(enabled)
        if enabled:
            self._reshuffle()
        else:
            preset_order = {preset.key: index for index, preset in enumerate(self._presets)}
            self._selected_order.sort(key=lambda key: preset_order.get(key, len(preset_order)))
            self._refresh_page_state()

    def _reshuffle(self) -> None:
        if len(self._selected_order) > 1:
            previous = list(self._selected_order)
            for _ in range(3):
                random.shuffle(self._selected_order)
                if self._selected_order != previous:
                    break
        self._refresh_page_state()

    def _options_changed(self, *_args) -> None:
        if self._module_name:
            self._set_default_task_name()
        self._refresh_page_state()

    def _set_default_task_name(self) -> None:
        if not self._module_name:
            return
        source = MODULE_PRESET_SOURCES[self._module_name]
        suffix = self._connection_type().lower().replace("-", "") if source.supports_connection else ""
        name = f"{source.display_name}{self._task_kind()}{suffix}"
        current_name = self.edit_task_name.text().strip()
        if current_name and current_name != self._last_default_task_name:
            return
        self.edit_task_name.blockSignals(True)
        self.edit_task_name.setText(name)
        self.edit_task_name.blockSignals(False)
        self._last_default_task_name = name

    def _incompatible_selected(self) -> list[ScanPreset]:
        if not self._module_name:
            return []
        source = MODULE_PRESET_SOURCES[self._module_name]
        if not source.supports_connection:
            return []
        selected_connection = self._connection_type()
        by_key = {preset.key: preset for preset in self._presets}
        return [
            by_key[key]
            for key in self._selected_order
            if key in by_key and by_key[key].connections and selected_connection not in by_key[key].connections
        ]

    def _refresh_summary(self) -> None:
        if not self._module_name:
            self.summary_text.clear()
            return
        source = MODULE_PRESET_SOURCES[self._module_name]
        by_key = {preset.key: preset for preset in self._presets}
        names = [by_key[key].name for key in self._selected_order if key in by_key]
        connection = f"\n连接方式：{self._connection_type()}" if source.supports_connection else ""
        if self._is_fps_stat():
            order_label = "业务顺序（固定）"
        else:
            order_label = "随机顺序（已固化）" if self.chk_random_order.isChecked() else "preset 顺序"
        estimated_steps = 1 + len(names) * (7 if self._task_kind() == TASK_KIND_POSTPROCESS else 4)
        estimated_steps += sum(3 for key in self._selected_order if key in by_key and by_key[key].task_profile == "frame_points")
        if self.chk_slide_rail.isChecked():
            estimated_steps += len(names)
        if source.pika_waits:
            estimated_steps += len(names) * 3 + 2
        self.summary_metrics["module"].setText(source.display_name)
        self.summary_metrics["modes"].setText(f"{len(names)} 个")
        self.summary_metrics["frames"].setText(f"{self.spin_target_frames.value()} 帧")
        self.summary_metrics["steps"].setText(f"约 {estimated_steps} 步")
        self.summary_status.setText("请检查连接" if self._incompatible_selected() else "可生成")
        lines = [
            f"● 准备运行环境\n   激活窗口并新建项目",
            f"● 逐个执行已选模式\n   {len(names)} 个模式 · {order_label} · 扫描至 {self.spin_target_frames.value()} 帧",
        ]
        if source.pika_waits:
            lines.append("● Pika 稳定性等待［自动］\n   关键节点自动等待 1–3 秒")
        if any(by_key[key].task_profile == "frame_points" for key in self._selected_order if key in by_key):
            lines.append("● 框架点流程［自动］\n   暂停并切换点云后继续扫描")
        if self.chk_slide_rail.isChecked():
            lines.append("● 滑轨切换位置［启用］\n   每个模式扫描前自动移动到对应位置")
        if self._task_kind() == TASK_KIND_POSTPROCESS:
            lines.append("● 执行后处理［自动］\n   融合 → 封装 → 按模式规则贴图")
        if self._is_fps_stat():
            lines.append("● 采集帧率数据［自动］\n   运行后从日志提取预览/扫描/稳定帧率，写入帧率统计模板 Excel")
        lines.append(f"● 任务成功收尾［自动］\n   返回首页 · {self._task_kind()}{connection}")
        self.summary_text.setText("\n\n".join(lines))

        incompatible = self._incompatible_selected()
        self.compatibility_error.setText(
            "当前连接方式不支持：" + "、".join(preset.name for preset in incompatible)
            if incompatible
            else ""
        )

    def _refresh_page_state(self) -> None:
        page_index = self.stack.currentIndex()
        for index, label in enumerate(self.step_labels):
            state = "active" if index == page_index else "done" if index < page_index else "pending"
            for widget in (self.step_cards[index], self.step_numbers[index], label, self.step_details[index]):
                widget.setProperty("state", state)
                widget.style().unpolish(widget)
                widget.style().polish(widget)

        self.btn_back.setVisible(page_index > 0)
        source = MODULE_PRESET_SOURCES.get(self._module_name)
        self.connection_widget.setVisible(bool(source and source.supports_connection))
        if source:
            connection = f" · {self._connection_type()}" if source.supports_connection else ""
            self.step_details[0].setText(f"{source.display_name}{connection}")
            self.module_aside_value.setText(source.display_name)
            if source.supports_connection:
                self.module_aside_help.setText(f"当前连接有 {len(self._presets)} 个扫描模式可供选择。")
            else:
                self.module_aside_help.setText(f"{len(self._presets)} 个扫描模式可供选择。")
        else:
            self.step_details[0].setText("确定扫描设备")
            self.module_aside_value.setText("尚未选择")
            self.module_aside_help.setText("选择一个模组后继续。切换模组会清空当前已选模式。")
        if self._is_fps_stat():
            self.step_details[1].setText(
                f"帧率统计 · 已选 {len(self._selected_order)} 个" if self._selected_order else "帧率统计"
            )
        else:
            self.step_details[1].setText(f"已选 {len(self._selected_order)} 个" if self._selected_order else "支持多选")
        self.step_details[2].setText(self._task_kind() if self._selected_order else "开流/后处理/帧率统计")
        if page_index == 0:
            self.btn_next.setText("下一步：选择模式")
            self.btn_next.setEnabled(bool(self._module_name))
            connection = f" · {self._connection_type()}" if source and source.supports_connection else ""
            self.footer_summary.setText(
                "请选择一个扫描模组" if not source else f"已选 {source.display_name}{connection}"
            )
        elif page_index == 1:
            self.btn_next.setText("下一步：生成方式")
            self.btn_next.setEnabled(bool(self._selected_order))
            self.selected_count_label.setText(f"{len(self._selected_order)} 个")
            self._refresh_selected_list()
            connection = f" · {self._connection_type()}" if source and source.supports_connection else ""
            self.footer_summary.setText(
                f"{source.display_name if source else '-'}{connection} · 已选 {len(self._selected_order)} 个模式"
            )
        else:
            incompatible = self._incompatible_selected()
            self.btn_next.setText("生成任务并打开编辑器")
            self.btn_next.setEnabled(
                bool(self._selected_order) and bool(self.edit_task_name.text().strip()) and not incompatible
            )
            connection = f" · {self._connection_type()}" if source and source.supports_connection else ""
            self.footer_summary.setText(
                f"{source.display_name if source else '-'} · {len(self._selected_order)} 个模式 · "
                f"{self.spin_target_frames.value()} 帧 · {self._task_kind()}{connection}"
            )
            self._refresh_summary()

    def _go_back(self) -> None:
        if self.stack.currentIndex() > 0:
            self.stack.setCurrentIndex(self.stack.currentIndex() - 1)
            self._refresh_page_state()

    def _go_next(self) -> None:
        page_index = self.stack.currentIndex()
        if page_index == 0:
            if not self._module_name:
                return
            self.stack.setCurrentIndex(1)
        elif page_index == 1:
            if not self._selected_order:
                show_error(self, "无法继续", "请至少选择一个扫描模式。")
                return
            # 第二步勾选了帧率统计时，第三步自动选择「帧率统计」任务类型并固定 1000 帧。
            self._set_fps_stat_enabled(self._is_fps_stat())
            source = MODULE_PRESET_SOURCES[self._module_name]
            self.pika_hint.setVisible(source.pika_waits)
            self._set_default_task_name()
            self.stack.setCurrentIndex(2)
        else:
            if not self.edit_task_name.text().strip():
                show_error(self, "无法生成任务", "任务名称不能为空。")
                return
            incompatible = self._incompatible_selected()
            if incompatible:
                show_error(self, "扫描模式与连接方式不匹配", self.compatibility_error.text())
                return
            self.accept()
            return
        self._refresh_page_state()

    def _request_free_edit(self) -> None:
        source = MODULE_PRESET_SOURCES.get(self._module_name)
        self.free_edit_default_name = f"手动编排-{source.display_name}" if source else "手动编排任务"
        self.free_edit_requested = True
        self.accept()

    def values(self) -> dict[str, object]:
        source = MODULE_PRESET_SOURCES[self._module_name]
        return {
            "module_name": self._module_name,
            "task_kind": self._task_kind(),
            "task_name": self.edit_task_name.text().strip(),
            "preset_keys": list(self._selected_order),
            "target_frames": self.spin_target_frames.value(),
            "connection_type": self._connection_type() if source.supports_connection else "",
            "randomized": self.chk_random_order.isChecked(),
            "slide_rail": self.chk_slide_rail.isChecked(),
        }


class TaskManagerDialog(QtWidgets.QDialog):
    """
    任务库：集中管理 tasks/*.json（Task=保存一份当前编排）。

    按扫描模组分类展示，支持导入/删除、加入主界面队列、加载到编辑器。
    """

    _CATEGORY_ORDER = (
        "P1",
        "P1S",
        "Raptor",
        "Raptor X",
        "Raptor Pro",
        "S1",
        "X1",
        "Pika",
        "Otter",
        "Otter Lite",
        "Otter Lite Basic",
        "Feeret",
        "测试任务",
    )
    _MODULE_LABELS = {
        "p1": "P1",
        "p1s": "P1S",
        "raptor": "Raptor",
        "raptor_x": "Raptor X",
        "raptor_pro": "Raptor Pro",
        "s1": "S1",
        "x1": "X1",
        "pika": "Pika",
        "otter": "Otter",
        "otter_lite": "Otter Lite",
        "otter_lite_basic": "Otter Lite Basic",
        "feeret": "Feeret",
    }
    _FILENAME_PREFIXES = (
        ("otter lite basic", "Otter Lite Basic"),
        ("otter_lite_basic", "Otter Lite Basic"),
        ("otter lite", "Otter Lite"),
        ("otter_lite", "Otter Lite"),
        ("p1s", "P1S"),
        ("raptor pro", "Raptor Pro"),
        ("raptor_pro", "Raptor Pro"),
        ("raptor x", "Raptor X"),
        ("raptor_x", "Raptor X"),
        ("raptor", "Raptor"),
        ("feeret", "Feeret"),
        ("otter", "Otter"),
        ("pika", "Pika"),
        ("p1", "P1"),
        ("s1", "S1"),
        ("x1", "X1"),
    )

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self._project_root = project_root
        self._action = ""

        self.setWindowTitle("任务库")
        self.setModal(True)
        self.resize(920, 640)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("任务库")
        title.setObjectName("dialogTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.btn_add = QtWidgets.QPushButton("添加任务")
        self.btn_add.setObjectName("secondaryBtn")
        header.addWidget(self.btn_add)

        self.btn_refresh = QtWidgets.QPushButton("刷新")
        self.btn_refresh.setObjectName("secondaryBtn")
        header.addWidget(self.btn_refresh)

        self.btn_open_dir = QtWidgets.QPushButton("打开 tasks 目录")
        self.btn_open_dir.setObjectName("secondaryBtn")
        header.addWidget(self.btn_open_dir)

        root.addLayout(header)

        self.lab_summary = QtWidgets.QLabel("正在读取任务…")
        self.lab_summary.setObjectName("mutedText")
        root.addWidget(self.lab_summary)

        self.edit_filter = QtWidgets.QLineEdit()
        self.edit_filter.setPlaceholderText("搜索任务（按文件名或分类）")
        root.addWidget(self.edit_filter)

        self.list = QtWidgets.QTreeWidget()
        self.list.setHeaderHidden(True)
        self.list.setRootIsDecorated(True)
        self.list.setIndentation(22)
        self.list.setUniformRowHeights(True)
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        root.addWidget(self.list, 1)

        self.lab_empty = QtWidgets.QLabel("任务库中没有匹配的任务。可清除搜索条件，或点击“添加任务”导入 JSON。")
        self.lab_empty.setObjectName("mutedText")
        self.lab_empty.setAlignment(QtCore.Qt.AlignCenter)
        self.lab_empty.setWordWrap(True)
        self.lab_empty.setMinimumHeight(64)
        self.lab_empty.hide()
        root.addWidget(self.lab_empty)

        btns = QtWidgets.QHBoxLayout()
        self.btn_delete = QtWidgets.QPushButton("删除")
        self.btn_delete.setObjectName("dangerBtn")
        btns.addWidget(self.btn_delete)
        btns.addStretch(1)

        self.btn_enqueue = QtWidgets.QPushButton("加入主界面")
        self.btn_enqueue.setObjectName("primaryBtn")
        btns.addWidget(self.btn_enqueue)

        self.btn_load = QtWidgets.QPushButton("加载到编辑器")
        self.btn_load.setObjectName("secondaryBtn")
        btns.addWidget(self.btn_load)


        self.btn_close = QtWidgets.QPushButton("关闭")
        self.btn_close.setObjectName("secondaryBtn")
        btns.addWidget(self.btn_close)

        root.addLayout(btns)

        self.btn_close.clicked.connect(self.reject)
        self.btn_add.clicked.connect(self._add_tasks)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_open_dir.clicked.connect(self._open_tasks_dir)
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_enqueue.clicked.connect(lambda: self._accept_action("enqueue"))
        self.btn_load.clicked.connect(lambda: self._accept_action("load"))
        self.edit_filter.textChanged.connect(self._apply_filter)
        self.list.itemDoubleClicked.connect(lambda *_: self._accept_action("load"))
        self.list.itemSelectionChanged.connect(self._refresh_action_state)

        self._all: list[Path] = []
        self._category_by_path: dict[Path, str] = {}
        self.refresh()

    @classmethod
    def _task_category(cls, task_path: Path) -> str:
        stem = task_path.stem.strip().lower()
        if stem.isdigit() or "测试" in stem or "演示" in stem:
            return "测试任务"

        try:
            model = load_task_json(task_path)
        except (OSError, UnicodeError, ValueError):
            model = None

        if model is not None:
            marker = "crealityscan.configure_scan_params_"
            for step in model.steps:
                if not step.step_id.startswith(marker):
                    continue
                module_key = step.step_id[len(marker) :].strip().lower()
                label = cls._MODULE_LABELS.get(module_key)
                if label:
                    return label

        for prefix, label in cls._FILENAME_PREFIXES:
            if stem.startswith(prefix):
                return label
        return "测试任务"

    def _tasks_dir(self) -> Path:
        d = self._project_root / "tasks"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _safe_task_stem(self, name: str) -> str:
        import re

        s = (name or "task").strip() or "task"
        s = re.sub(r'[<>:"/\\|?*]+', "_", s)
        s = re.sub(r"\s+", " ", s)
        s = s.strip().strip(".")
        if not s:
            s = "task"
        return s[:80]

    def _unique_task_path(self, stem: str) -> Path:
        base = self._tasks_dir()
        stem = self._safe_task_stem(stem)
        cand = base / f"{stem}.json"
        if not cand.exists():
            return cand
        i = 2
        while True:
            p = base / f"{stem}_{i}.json"
            if not p.exists():
                return p
            i += 1

    def _add_tasks(self) -> None:
        base = self._tasks_dir()
        fps, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "选择任务 JSON（可多选）",
            str(base),
            "JSON (*.json)",
        )
        if not fps:
            return

        added: list[Path] = []
        failed: list[str] = []
        for fp in fps:
            src = Path(fp)
            try:
                # Task 与 Case 结构一致，复用解析
                model = load_task_json(src)
                stem = (model.name or model.case_id or src.stem).strip() or src.stem
                dst = self._unique_task_path(stem)
                # 如果用户选的就是 tasks 目录下同名文件，则不重复导入
                try:
                    if src.resolve() == dst.resolve():
                        continue
                except Exception:
                    pass
                save_task_json(self._project_root, model, path=dst)
                added.append(dst)
            except Exception as e:
                failed.append(f"{src.name}: {e}")

        if failed and not added:
            show_error(self, "添加任务失败", "\n".join(failed[:12]))
            return

        self.refresh()
        if added:
            self.setWindowTitle(f"任务库（已添加 {len(added)} 个）")

    def refresh(self) -> None:
        self._all = []
        self._category_by_path = {}
        d = self._tasks_dir()
        try:
            fps = [p for p in d.glob("*.json") if p.is_file() and p.name.lower() != "_queue.json"]
            fps.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            self._all = fps
            self._category_by_path = {p: self._task_category(p) for p in fps}
        except OSError:
            self._all = []
            self._category_by_path = {}
        self._apply_filter()
        self.lab_summary.setText(f"共 {len(self._all)} 个任务 · 按扫描模组分类")

    def _apply_filter(self) -> None:
        text = self.edit_filter.text().strip().lower()
        self.list.clear()
        grouped: dict[str, list[Path]] = {}
        for p in self._all:
            name = p.name
            category = self._category_by_path.get(p, "测试任务")
            if text and text not in name.lower() and text not in category.lower():
                continue
            grouped.setdefault(category, []).append(p)

        order = {name: index for index, name in enumerate(self._CATEGORY_ORDER)}
        first_task_item = None
        for category in sorted(grouped, key=lambda name: (order.get(name, len(order)), name.lower())):
            paths = grouped[category]
            group_item = QtWidgets.QTreeWidgetItem([f"{category}（{len(paths)}）"])
            group_item.setFlags(group_item.flags() & ~QtCore.Qt.ItemIsSelectable)
            group_font = group_item.font(0)
            group_font.setBold(True)
            group_item.setFont(0, group_font)
            group_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#355278")))
            group_item.setBackground(0, QtGui.QBrush(QtGui.QColor("#edf4ff")))
            group_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
            group_item.setToolTip(0, f"{category}：{len(paths)} 个任务")
            self.list.addTopLevelItem(group_item)

            for path in paths:
                task_item = QtWidgets.QTreeWidgetItem([path.name])
                task_item.setToolTip(0, str(path))
                task_item.setData(0, QtCore.Qt.UserRole, str(path))
                task_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                group_item.addChild(task_item)
                if first_task_item is None:
                    first_task_item = task_item
            group_item.setExpanded(True)

        if first_task_item is not None:
            self.list.setCurrentItem(first_task_item)
        has_results = first_task_item is not None
        self.list.setVisible(has_results)
        self.lab_empty.setVisible(not has_results)
        self._refresh_action_state()

    def _refresh_action_state(self) -> None:
        selected = self._selected_paths()
        self.btn_delete.setEnabled(bool(selected))
        self.btn_enqueue.setEnabled(bool(selected))
        self.btn_load.setEnabled(len(selected) == 1)

    def _selected_paths(self) -> list[Path]:
        out: list[Path] = []
        for it in self.list.selectedItems():
            raw = it.data(0, QtCore.Qt.UserRole)
            if isinstance(raw, str) and raw:
                out.append(Path(raw))
        return out

    def _open_tasks_dir(self) -> None:
        _open_path(str(self._tasks_dir()))

    def _delete_selected(self) -> None:
        fps = self._selected_paths()
        if not fps:
            return
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("确认删除")
        box.setText(f"确定删除 {len(fps)} 个任务文件吗？此操作不可恢复。")
        box.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Ok)
        if box.exec_() != QtWidgets.QMessageBox.Ok:
            return

        ok = 0
        for p in fps:
            try:
                p.unlink(missing_ok=True)  # py3.8 doesn't support missing_ok; fallback below
                ok += 1
            except TypeError:
                try:
                    if p.exists():
                        p.unlink()
                        ok += 1
                except Exception:
                    pass
            except Exception:
                pass

        self.refresh()
        self.setWindowTitle(f"任务库（已删除 {ok}/{len(fps)}）")

    def _accept_action(self, action: str) -> None:
        fps = self._selected_paths()
        if not fps:
            self.lab_summary.setText("请先选择至少一个任务。")
            return
        if action == "load" and len(fps) != 1:
            self.lab_summary.setText("加载到编辑器时只能选择一个任务。")
            return
        self._action = action
        self.accept()

    def result_action(self) -> str:
        return self._action

    def selected_paths(self) -> list[Path]:
        return self._selected_paths()


class PointDistanceDialog(QtWidgets.QDialog):
    """
    让用户输入点距（mm），用于点距文本框输入类步骤。
    """

    def __init__(self, default_value: str = "0.45", parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置点距（mm）")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._value = ""

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        title = QtWidgets.QLabel("请输入点距（mm）")
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#1f2a44;")
        root.addWidget(title)

        self.edit = QtWidgets.QLineEdit(str(default_value or "0.45"))
        self.edit.setPlaceholderText("例如：0.45")
        self.edit.setMinimumHeight(30)
        root.addWidget(self.edit)

        hint = QtWidgets.QLabel("提示：推荐使用小数点格式；确定后会自动点击文本框并输入该数值。")
        hint.setStyleSheet("color:#64748b;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_ok = QtWidgets.QPushButton("确定")
        self.btn_ok.setObjectName("primaryBtn")
        self.btn_ok.setDefault(True)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._accept_if_valid)
        self.edit.returnPressed.connect(self._accept_if_valid)
        self.edit.textChanged.connect(self._refresh_ok_enabled)

        self._refresh_ok_enabled()

    def _refresh_ok_enabled(self) -> None:
        s = self.edit.text().strip()
        try:
            v = float(s)
            ok = v > 0
        except Exception:
            ok = False
        self.btn_ok.setEnabled(ok)

    def _accept_if_valid(self) -> None:
        s = self.edit.text().strip()
        try:
            v = float(s)
        except Exception:
            return
        if v <= 0:
            return
        # 保留用户原始格式（避免 0.450000）
        self._value = s
        self.accept()

    def value(self) -> str:
        return self._value


class TargetFramesDialog(QtWidgets.QDialog):
    """
    让用户输入目标帧数，用于“开始扫描并在帧数达标后完成”类步骤。
    """

    def __init__(self, default_value: str = "200", parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置目标帧数")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._value: int = 0

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        title = QtWidgets.QLabel("请输入目标帧数")
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#1f2a44;")
        root.addWidget(title)

        self.edit = QtWidgets.QLineEdit(str(default_value or "200"))
        self.edit.setPlaceholderText("例如：200")
        self.edit.setMinimumHeight(30)
        root.addWidget(self.edit)

        hint = QtWidgets.QLabel("提示：当扫描日志中的 frame >= 目标帧数时，该步骤视为成功。")
        hint.setStyleSheet("color:#64748b;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_ok = QtWidgets.QPushButton("确定")
        self.btn_ok.setObjectName("primaryBtn")
        self.btn_ok.setDefault(True)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._accept_if_valid)
        self.edit.returnPressed.connect(self._accept_if_valid)
        self.edit.textChanged.connect(self._refresh_ok_enabled)

        self._refresh_ok_enabled()

    def _refresh_ok_enabled(self) -> None:
        s = self.edit.text().strip()
        try:
            v = int(s)
            ok = v > 0
        except Exception:
            ok = False
        self.btn_ok.setEnabled(ok)

    def _accept_if_valid(self) -> None:
        s = self.edit.text().strip()
        try:
            v = int(s)
        except Exception:
            return
        if v <= 0:
            return
        self._value = v
        self.accept()

    def value(self) -> int:
        return int(self._value)


class SleepSecondsDialog(QtWidgets.QDialog):
    """
    让用户输入等待秒数，用于通用等待步骤。
    """

    def __init__(self, default_value: float = 1.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置等待秒数")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._value: float = float(default_value or 1.0)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        title = QtWidgets.QLabel("请输入等待秒数")
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#1f2a44;")
        root.addWidget(title)

        self.edit = QtWidgets.QLineEdit(f"{self._value:g}")
        self.edit.setPlaceholderText("例如：3")
        self.edit.setMinimumHeight(30)
        root.addWidget(self.edit)

        hint = QtWidgets.QLabel("提示：该步骤会按输入秒数暂停后再继续执行后续步骤。")
        hint.setStyleSheet("color:#64748b;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_ok = QtWidgets.QPushButton("确定")
        self.btn_ok.setObjectName("primaryBtn")
        self.btn_ok.setDefault(True)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._accept_if_valid)
        self.edit.returnPressed.connect(self._accept_if_valid)
        self.edit.textChanged.connect(self._refresh_ok_enabled)

        self._refresh_ok_enabled()

    def _refresh_ok_enabled(self) -> None:
        s = self.edit.text().strip()
        try:
            v = float(s)
            ok = v >= 0
        except Exception:
            ok = False
        self.btn_ok.setEnabled(ok)

    def _accept_if_valid(self) -> None:
        s = self.edit.text().strip()
        try:
            v = float(s)
        except Exception:
            return
        if v < 0:
            return
        self._value = v
        self.accept()

    def value(self) -> float:
        return float(self._value)


class RunFinishedDialog(QtWidgets.QDialog):
    """
    运行结束弹窗：展示产物目录/报告，并提供“一键打开”。
    """

    def __init__(self, ok: bool, run_dir: str, report: str, parent=None, reason: str = ""):
        super().__init__(parent)
        if reason == "stopped":
            self.setWindowTitle("已停止")
        else:
            self.setWindowTitle("运行完成" if ok else "运行失败")
        self.setModal(True)
        self.setMinimumWidth(620)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        if reason == "stopped":
            sp = QtWidgets.QStyle.SP_MediaStop
        else:
            sp = QtWidgets.QStyle.SP_DialogApplyButton if ok else QtWidgets.QStyle.SP_MessageBoxCritical
        icon = self.style().standardIcon(sp)
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(icon.pixmap(32, 32))
        header.addWidget(icon_label, 0, QtCore.Qt.AlignTop)

        title_box = QtWidgets.QVBoxLayout()
        if reason == "stopped":
            title = QtWidgets.QLabel("已停止运行")
        else:
            title = QtWidgets.QLabel("执行成功" if ok else "执行失败")
        f = title.font()
        f.setPointSize(max(11, f.pointSize() + 2))
        f.setBold(True)
        title.setFont(f)
        run_dir_exists = bool(run_dir and Path(run_dir).exists())
        report_exists = bool(report and Path(report).exists())
        if reason == "stopped":
            subtitle = QtWidgets.QLabel("如已生成部分产物，可在下方打开。")
        elif not ok:
            subtitle = QtWidgets.QLabel("任务未完成。请查看步骤结果、截图和运行输出定位失败原因。")
        elif report_exists:
            subtitle = QtWidgets.QLabel("运行产物与 HTML 报告已生成。")
        else:
            subtitle = QtWidgets.QLabel("运行已完成，但未找到 HTML 报告。可检查产物目录。")
        subtitle.setObjectName("mutedText")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        root.addLayout(header)

        # Paths
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        def mk_label(text: str) -> QtWidgets.QLabel:
            lab = QtWidgets.QLabel(text)
            lab.setStyleSheet("color:#334155;")
            lab.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            lab.setFixedWidth(90)
            return lab

        self.edit_run_dir = QtWidgets.QLineEdit(run_dir or "")
        self.edit_run_dir.setReadOnly(True)
        self.edit_report = QtWidgets.QLineEdit(report or "")
        self.edit_report.setReadOnly(True)

        btn_open_dir = QtWidgets.QPushButton("打开目录")
        btn_open_dir.setObjectName("secondaryBtn")
        btn_open_report = QtWidgets.QPushButton("打开报告")
        btn_open_report.setObjectName("secondaryBtn")
        btn_open_dir.setEnabled(run_dir_exists)
        btn_open_report.setEnabled(report_exists)

        grid.addWidget(mk_label("产物目录"), 0, 0)
        grid.addWidget(self.edit_run_dir, 0, 1)
        grid.addWidget(btn_open_dir, 0, 2)
        grid.addWidget(mk_label("报告"), 1, 0)
        grid.addWidget(self.edit_report, 1, 1)
        grid.addWidget(btn_open_report, 1, 2)

        root.addLayout(grid)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.setObjectName("primaryBtn")
        close_btn.setDefault(True)
        btns.addWidget(close_btn)
        root.addLayout(btns)

        close_btn.clicked.connect(self.accept)
        btn_open_dir.clicked.connect(lambda: _open_path(self.edit_run_dir.text().strip()))
        btn_open_report.clicked.connect(lambda: _open_path(self.edit_report.text().strip()))


class EmailSettingsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        current_email: str,
        availability_checker: Callable[[], Tuple[bool, str]],
        parent=None,
        startup_mode: bool = False,
        current_label: str = "",
    ):
        super().__init__(parent)
        self._availability_checker = availability_checker
        self._startup_mode = bool(startup_mode)
        self._email = ""

        self.setWindowTitle("收集通知邮箱" if self._startup_mode else "邮件设置")
        self.setModal(True)
        self.setMinimumWidth(580)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        title = QtWidgets.QLabel("请输入接收自动化测试通知的邮箱（可选）")
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(max(11, title_font.pointSize() + 1))
        title.setFont(title_font)
        root.addWidget(title)

        desc = QtWidgets.QLabel(
            "邮箱为可选项。留空也可继续进入平台，但将不会发送邮件通知；SMTP 凭证缺失或网络异常时，通知功能同样会被禁用。"
        )
        desc.setStyleSheet("color:#475569;")
        desc.setWordWrap(True)
        root.addWidget(desc)

        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        lab_email = QtWidgets.QLabel("收件邮箱")
        lab_email.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        lab_email.setFixedWidth(90)
        self.edit_email = QtWidgets.QLineEdit(current_email or "")
        self.edit_email.setPlaceholderText("例如：user@example.com")
        form.addWidget(lab_email, 0, 0)
        form.addWidget(self.edit_email, 0, 1)

        lab_label = QtWidgets.QLabel("标识")
        lab_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        lab_label.setFixedWidth(90)
        self.edit_label = QtWidgets.QLineEdit(current_label or "")
        self.edit_label.setPlaceholderText("例如：深圳压测电脑1（用于邮件标题前缀）")
        form.addWidget(lab_label, 1, 0)
        form.addWidget(self.edit_label, 1, 1)
        root.addLayout(form)

        status_box = QtWidgets.QFrame()
        status_box.setStyleSheet(
            "QFrame{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;}"
        )
        status_layout = QtWidgets.QVBoxLayout(status_box)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)

        self.lab_status = QtWidgets.QLabel("")
        self.lab_status.setWordWrap(True)
        status_layout.addWidget(self.lab_status)

        self.lab_env = QtWidgets.QLabel(
            "必需环境变量：JENS_SMTP_HOST、JENS_SMTP_PORT、JENS_SMTP_USER、JENS_SMTP_PASSWORD"
        )
        self.lab_env.setWordWrap(True)
        self.lab_env.setStyleSheet("color:#64748b;")
        status_layout.addWidget(self.lab_env)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        self.btn_recheck = QtWidgets.QPushButton("重新检测通知环境")
        self.btn_recheck.setObjectName("secondaryBtn")
        row.addWidget(self.btn_recheck)
        status_layout.addLayout(row)
        root.addWidget(status_box)

        btns = QtWidgets.QHBoxLayout()
        if self._startup_mode:
            self.btn_exit = QtWidgets.QPushButton("退出平台")
            self.btn_exit.setObjectName("secondaryBtn")
            btns.addWidget(self.btn_exit)
        else:
            self.btn_cancel = QtWidgets.QPushButton("取消")
            self.btn_cancel.setObjectName("secondaryBtn")
            btns.addWidget(self.btn_cancel)
        btns.addStretch(1)
        self.btn_save = QtWidgets.QPushButton("保存并继续" if self._startup_mode else "保存")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.setDefault(True)
        btns.addWidget(self.btn_save)
        root.addLayout(btns)

        self.edit_email.textChanged.connect(self._refresh_save_enabled)
        self.btn_recheck.clicked.connect(self._refresh_status)
        self.btn_save.clicked.connect(self._accept_if_valid)
        if self._startup_mode:
            self.btn_exit.clicked.connect(self.reject)
        else:
            self.btn_cancel.clicked.connect(self.reject)

        self._refresh_status()
        self._refresh_save_enabled()

    def _refresh_status(self) -> None:
        enabled, reason = self._availability_checker()
        if enabled:
            self.lab_status.setText("<span style='color:#166534;font-weight:600'>通知功能可用</span>")
        else:
            safe_reason = reason or "SMTP 凭证缺失或网络异常"
            self.lab_status.setText(
                f"<span style='color:#b91c1c;font-weight:600'>通知功能已禁用</span><br>{safe_reason}"
            )

    def _refresh_save_enabled(self) -> None:
        text = self.edit_email.text().strip()
        ok = (not text) or (("@" in text) and ("." in text.split("@")[-1]))
        self.btn_save.setEnabled(ok)

    def _accept_if_valid(self) -> None:
        text = self.edit_email.text().strip()
        if text and ("@" not in text or "." not in text.split("@")[-1]):
            return
        self._email = text
        self.accept()

    def email(self) -> str:
        return self._email or self.edit_email.text().strip()

    def label(self) -> str:
        return self.edit_label.text().strip()


def show_error(parent, title: str, message: str) -> None:
    # 简化：统一用 Qt 的 QMessageBox，但依赖全局样式表使其观感更接近主界面
    box = QtWidgets.QMessageBox(parent)
    box.setIcon(QtWidgets.QMessageBox.Critical)
    box.setWindowTitle(title)
    box.setText(message)
    box.setStandardButtons(QtWidgets.QMessageBox.Ok)
    box.exec_()


_SET_POINT_DISTANCE_STEP_ID = "crealityscan.set_point_distance"
_SLEEP_STEP_ID = "common.sleep"
_SLIDE_RAIL_SWITCH_POSITION_STEP_ID = "slide_rail.switch_position"
_SCAN_UNTIL_FRAMES_STEP_ID = "crealityscan.scan_until_frames_then_stop"
_SCAN_UNTIL_FRAMES_FRAME_POINTS_STEP_ID = "crealityscan.scan_until_frames_reach_target_frame_points"
_TARGET_FRAMES_STEP_IDS = {
    _SCAN_UNTIL_FRAMES_STEP_ID,
}


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


class _AvailableStepItem(QtWidgets.QListWidgetItem):
    def __init__(self, meta: StepMeta):
        super().__init__(meta.name)
        self.meta = meta
        self.setToolTip(f"{meta.step_id}@{meta.version}")


class _SelectedStepItem(QtWidgets.QListWidgetItem):
    def __init__(self, step: CaseStep):
        super().__init__(step.name or step.step_id)
        self.step = step
        self.setToolTip(f"{step.step_id}@{step.version}")

    def refresh_text(self) -> None:
        self.setText(self.step.name or self.step.step_id)
        self.setToolTip(f"{self.step.step_id}@{self.step.version}")


class TaskEditDialog(QtWidgets.QDialog):
    """
    任务编辑弹窗：仅编辑“任务（保存一份当前编排）”里的步骤列表与步骤参数。

    约束：不把任务加载到主界面“已选步骤”，避免误解（KISS）。
    """

    def __init__(
        self,
        project_root: Path,
        task_path: Path,
        step_metas: list[StepMeta],
        parent=None,
        initial_model: Optional[CaseModel] = None,
    ):
        super().__init__(parent)
        self.project_root = project_root
        self.task_path = Path(task_path)
        self._all_step_metas = list(step_metas)
        self._current_step_item: Optional[_SelectedStepItem] = None

        if self.task_path.exists():
            try:
                self.model = load_task_json(self.task_path)
            except Exception as e:
                raise RuntimeError(f"加载任务失败：{self.task_path}\n{e}") from e
        elif initial_model is not None:
            self.model = initial_model
        else:
            raise RuntimeError(f"任务不存在：{self.task_path}")

        self.setWindowTitle(f"{'编辑' if self.task_path.exists() else '新建'}任务：{self.task_path.stem}")
        self.setModal(True)
        self.resize(980, 640)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        hint = QtWidgets.QLabel(f"任务文件：{self.task_path.name}")
        hint.setStyleSheet("color:#475569;")
        root.addWidget(hint)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        # 可选步骤
        box_avail = QtWidgets.QGroupBox("可选步骤（双击添加）")
        v1 = QtWidgets.QVBoxLayout(box_avail)
        v1.setContentsMargins(10, 16, 10, 10)
        v1.setSpacing(8)
        self.edit_step_filter = QtWidgets.QLineEdit()
        self.edit_step_filter.setPlaceholderText("搜索（按名称或步骤 ID）")
        self.edit_step_filter.textChanged.connect(self._apply_step_filter)
        v1.addWidget(self.edit_step_filter)
        self.list_available = QtWidgets.QListWidget()
        self.list_available.setAlternatingRowColors(True)
        self.list_available.itemDoubleClicked.connect(self._add_selected_step)
        v1.addWidget(self.list_available, 1)
        splitter.addWidget(box_avail)

        # 已选步骤
        box_sel = QtWidgets.QGroupBox("任务步骤（可拖拽排序）")
        v2 = QtWidgets.QVBoxLayout(box_sel)
        v2.setContentsMargins(10, 16, 10, 10)
        v2.setSpacing(8)
        self.list_selected = QtWidgets.QListWidget()
        self.list_selected.setAlternatingRowColors(True)
        self.list_selected.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list_selected.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.list_selected.setDragEnabled(True)
        self.list_selected.setAcceptDrops(True)
        self.list_selected.setDropIndicatorShown(True)
        self.list_selected.setDragDropOverwriteMode(False)
        self.list_selected.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list_selected.currentItemChanged.connect(self._on_selected_step_changed)
        v2.addWidget(self.list_selected, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_remove = QtWidgets.QPushButton("移除")
        self.btn_remove.setObjectName("secondaryBtn")
        self.btn_remove.clicked.connect(self._remove_selected_step)
        btn_row.addWidget(self.btn_remove)
        btn_row.addStretch(1)
        v2.addLayout(btn_row)
        splitter.addWidget(box_sel)

        # 步骤配置
        box_detail = QtWidgets.QGroupBox("步骤配置")
        v3 = QtWidgets.QVBoxLayout(box_detail)
        v3.setContentsMargins(10, 16, 10, 10)
        v3.setSpacing(8)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        def mk_label(text: str, width: int = 110) -> QtWidgets.QLabel:
            lab = QtWidgets.QLabel(text)
            lab.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            lab.setFixedWidth(width)
            return lab

        self.edit_step_name = QtWidgets.QLineEdit()
        self.combo_on_fail = QtWidgets.QComboBox()
        self.combo_on_fail.addItem("终止任务", "abort")
        self.combo_on_fail.addItem("继续执行", "continue")
        self.combo_on_fail.addItem("重试步骤", "retry")
        self.spin_retries = QtWidgets.QSpinBox()
        self.spin_retries.setRange(0, 20)
        self.spin_retry_wait = QtWidgets.QDoubleSpinBox()
        self.spin_retry_wait.setRange(0.0, 30.0)
        self.spin_retry_wait.setDecimals(2)
        self.spin_retry_wait.setSingleStep(0.1)
        self.edit_params = QtWidgets.QPlainTextEdit()
        self.edit_params.setPlaceholderText("{ }（JSON）")
        self.edit_params.setFixedHeight(120)
        self.edit_params.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        self.lab_params_error = QtWidgets.QLabel("")
        self.lab_params_error.setObjectName("statusBad")
        self.lab_params_error.setWordWrap(True)
        self.lab_params_error.hide()

        self.edit_step_name.textChanged.connect(self._apply_step_detail_changes)
        self.combo_on_fail.currentTextChanged.connect(self._apply_step_detail_changes)
        self.spin_retries.valueChanged.connect(self._apply_step_detail_changes)
        self.spin_retry_wait.valueChanged.connect(self._apply_step_detail_changes)
        self.edit_params.textChanged.connect(self._apply_step_detail_changes)

        r = 0
        grid.addWidget(mk_label("显示名"), r, 0)
        grid.addWidget(self.edit_step_name, r, 1)
        r += 1
        grid.addWidget(mk_label("失败策略"), r, 0)
        grid.addWidget(self.combo_on_fail, r, 1)
        r += 1
        grid.addWidget(mk_label("重试次数"), r, 0)
        grid.addWidget(self.spin_retries, r, 1)
        r += 1
        grid.addWidget(mk_label("重试间隔(秒)"), r, 0)
        grid.addWidget(self.spin_retry_wait, r, 1)
        r += 1
        grid.addWidget(mk_label("参数（JSON）"), r, 0, QtCore.Qt.AlignTop)
        grid.addWidget(self.edit_params, r, 1)
        r += 1
        grid.addWidget(self.lab_params_error, r, 1)
        grid.setColumnStretch(1, 1)
        v3.addLayout(grid)

        self.btn_pick_preset = QtWidgets.QPushButton("选择预设…")
        self.btn_pick_preset.setObjectName("secondaryBtn")
        self.btn_pick_preset.clicked.connect(self._pick_preset_for_current_step)
        v3.addWidget(self.btn_pick_preset)
        self.btn_pick_preset.setVisible(False)

        self.btn_set_point_distance = QtWidgets.QPushButton("设置点距…")
        self.btn_set_point_distance.setObjectName("secondaryBtn")
        self.btn_set_point_distance.clicked.connect(self._set_point_distance_for_current_step)
        v3.addWidget(self.btn_set_point_distance)
        self.btn_set_point_distance.setVisible(False)

        self.btn_set_target_frames = QtWidgets.QPushButton("设置目标帧数…")
        self.btn_set_target_frames.setObjectName("secondaryBtn")
        self.btn_set_target_frames.clicked.connect(self._set_target_frames_for_current_step)
        v3.addWidget(self.btn_set_target_frames)
        self.btn_set_target_frames.setVisible(False)

        self.btn_set_sleep_seconds = QtWidgets.QPushButton("设置等待秒数…")
        self.btn_set_sleep_seconds.setObjectName("secondaryBtn")
        self.btn_set_sleep_seconds.clicked.connect(self._set_sleep_seconds_for_current_step)
        v3.addWidget(self.btn_set_sleep_seconds)
        self.btn_set_sleep_seconds.setVisible(False)

        v3.addStretch(1)
        splitter.addWidget(box_detail)

        splitter.setSizes([320, 320, 340])

        # Buttons
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_ok = QtWidgets.QPushButton("保存")
        self.btn_ok.setObjectName("primaryBtn")
        self.btn_ok.setDefault(True)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._save_and_accept)

        self._apply_step_filter()
        self._refresh_selected_steps()
        self._set_step_detail_enabled(False)

    def _find_step_meta(self, step_id: str, version: str) -> Optional[StepMeta]:
        for m in self._all_step_metas:
            if m.step_id == step_id and m.version == version:
                return m
        return None

    def _presets_path_for_step(self, step_id: str, version: str) -> Optional[Path]:
        meta = self._find_step_meta(step_id, version)
        if not meta:
            return None
        return Path(meta.source_path).with_name("presets.json")

    def _is_preset_step(self, step_id: str, version: str) -> bool:
        fp = self._presets_path_for_step(step_id, version)
        return bool(fp and fp.exists())

    def _load_presets_for_step(self, step_id: str, version: str) -> list[tuple[str, str]]:
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

    def _apply_step_filter(self) -> None:
        text = self.edit_step_filter.text().strip().lower()
        self.list_available.clear()
        for m in self._all_step_metas:
            if text:
                hay = f"{m.name} {m.step_id} {m.version}".lower()
                if text not in hay:
                    continue
            self.list_available.addItem(_AvailableStepItem(m))

    def _refresh_selected_steps(self) -> None:
        self._current_step_item = None
        self.list_selected.blockSignals(True)
        try:
            self.list_selected.clear()
            for s in self.model.steps:
                self.list_selected.addItem(_SelectedStepItem(s))
        finally:
            self.list_selected.blockSignals(False)

    def _sync_model_from_selected_list_order(self) -> None:
        steps: list[CaseStep] = []
        for i in range(self.list_selected.count()):
            it = self.list_selected.item(i)
            if isinstance(it, _SelectedStepItem):
                steps.append(it.step)
        self.model.steps = steps

    def _pick_preset_for_step(self, step: CaseStep) -> bool:
        try:
            presets = self._load_presets_for_step(step.step_id, step.version)
        except Exception as e:
            show_error(self, "无法加载预设", str(e))
            return False
        if not presets:
            show_error(self, "无法加载预设", "未找到可用预设（预设文件为空或解析失败）。")
            return False

        dlg = PresetPickerDialog("选择扫描参数预设", presets, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return False
        name_cn, key = dlg.selected()
        step.params = {"preset": name_cn or key}
        if name_cn:
            step.name = _preset_step_name(step.step_id, name_cn)
        return True

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

    def _set_target_frames_for_step(self, step: CaseStep) -> bool:
        default_value = "200"
        if isinstance(step.params, dict):
            v = step.params.get("target_frames")
            if v is None:
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

    def _configure_step_on_add(self, step: CaseStep) -> bool:
        if self._is_preset_step(step.step_id, step.version):
            if not self._pick_preset_for_step(step):
                return False
        if step.step_id == _SET_POINT_DISTANCE_STEP_ID:
            if not self._set_point_distance_for_step(step):
                return False
        if _is_target_frames_step(step.step_id):
            if not self._set_target_frames_for_step(step):
                return False
        if step.step_id == _SLEEP_STEP_ID:
            if not self._set_sleep_seconds_for_step(step):
                return False
        return True

    def _add_selected_step(self, item: QtWidgets.QListWidgetItem) -> None:
        if not isinstance(item, _AvailableStepItem):
            return
        meta = item.meta
        step = CaseStep(step_id=meta.step_id, version=meta.version, name=meta.name)
        if not self._configure_step_on_add(step):
            return
        self.model.steps.append(step)
        self._refresh_selected_steps()

    def _remove_selected_step(self) -> None:
        cur = self.list_selected.currentItem()
        if not isinstance(cur, _SelectedStepItem):
            return
        idx = self.list_selected.row(cur)
        if 0 <= idx < len(self.model.steps):
            self.model.steps.pop(idx)
        self._refresh_selected_steps()
        self._set_step_detail_enabled(False)

    def _on_selected_step_changed(self, cur, prev) -> None:
        self._sync_model_from_selected_list_order()
        if not isinstance(cur, _SelectedStepItem):
            self._current_step_item = None
            self._set_step_detail_enabled(False)
            self.btn_pick_preset.setVisible(False)
            self.btn_set_point_distance.setVisible(False)
            self.btn_set_target_frames.setVisible(False)
            self.btn_set_sleep_seconds.setVisible(False)
            return
        self._current_step_item = cur
        self._set_step_detail_enabled(True)
        self._load_step_detail(cur.step)
        self.btn_pick_preset.setVisible(self._is_preset_step(cur.step.step_id, cur.step.version))
        self.btn_set_point_distance.setVisible(cur.step.step_id == _SET_POINT_DISTANCE_STEP_ID)
        self.btn_set_target_frames.setVisible(_is_target_frames_step(cur.step.step_id))
        self.btn_set_sleep_seconds.setVisible(cur.step.step_id == _SLEEP_STEP_ID)

    def _set_step_detail_enabled(self, enabled: bool) -> None:
        self.edit_step_name.setEnabled(enabled)
        self.combo_on_fail.setEnabled(enabled)
        self.spin_retries.setEnabled(enabled)
        self.spin_retry_wait.setEnabled(enabled)
        self.edit_params.setEnabled(enabled)
        self.btn_pick_preset.setEnabled(enabled)
        self.btn_set_point_distance.setEnabled(enabled)
        self.btn_set_target_frames.setEnabled(enabled)
        self.btn_set_sleep_seconds.setEnabled(enabled)

    def _live_current_step_item(self) -> Optional[_SelectedStepItem]:
        current = self.list_selected.currentItem()
        if not isinstance(current, _SelectedStepItem):
            self._current_step_item = None
            return None
        self._current_step_item = current
        return current

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
            idx = self.combo_on_fail.findData(action)
            self.combo_on_fail.setCurrentIndex(idx if idx >= 0 else 0)
            self.spin_retries.setValue(int(on_fail.get("max_retries") or 0))
            self.spin_retry_wait.setValue(float(on_fail.get("retry_wait_sec") or 0.5))
            self.edit_params.setPlainText(json.dumps(step.params or {}, ensure_ascii=False, indent=2))
            self.edit_params.setProperty("error", False)
            self.edit_params.style().unpolish(self.edit_params)
            self.edit_params.style().polish(self.edit_params)
            self.lab_params_error.hide()
            self.btn_ok.setEnabled(True)
        finally:
            self.edit_step_name.blockSignals(False)
            self.combo_on_fail.blockSignals(False)
            self.spin_retries.blockSignals(False)
            self.spin_retry_wait.blockSignals(False)
            self.edit_params.blockSignals(False)

    def _apply_step_detail_changes(self) -> None:
        current_item = self._live_current_step_item()
        if current_item is None:
            return
        step = current_item.step
        step.name = self.edit_step_name.text().strip()
        step.on_fail = {
            "action": self.combo_on_fail.currentData() or "abort",
            "max_retries": int(self.spin_retries.value()),
            "retry_wait_sec": float(self.spin_retry_wait.value()),
        }
        params_valid = True
        try:
            parsed_params = json.loads(self.edit_params.toPlainText() or "{}")
            if not isinstance(parsed_params, dict):
                raise ValueError("参数根节点必须是 JSON 对象")
            step.params = parsed_params
        except (json.JSONDecodeError, ValueError) as exc:
            params_valid = False
            self.lab_params_error.setText(f"参数格式错误：{exc}")
        self.edit_params.setProperty("error", not params_valid)
        self.edit_params.style().unpolish(self.edit_params)
        self.edit_params.style().polish(self.edit_params)
        self.lab_params_error.setVisible(not params_valid)
        self.btn_ok.setEnabled(params_valid)
        current_item.refresh_text()

    def _pick_preset_for_current_step(self) -> None:
        current_item = self._live_current_step_item()
        if current_item is None:
            return
        step = current_item.step
        if not self._is_preset_step(step.step_id, step.version):
            return
        if not self._pick_preset_for_step(step):
            return
        self._load_step_detail(step)
        current_item.refresh_text()

    def _set_point_distance_for_current_step(self) -> None:
        current_item = self._live_current_step_item()
        if current_item is None:
            return
        step = current_item.step
        if step.step_id != _SET_POINT_DISTANCE_STEP_ID:
            return
        if not self._set_point_distance_for_step(step):
            return
        self._load_step_detail(step)
        current_item.refresh_text()

    def _set_target_frames_for_current_step(self) -> None:
        current_item = self._live_current_step_item()
        if current_item is None:
            return
        step = current_item.step
        if not _is_target_frames_step(step.step_id):
            return
        if not self._set_target_frames_for_step(step):
            return
        self._load_step_detail(step)
        current_item.refresh_text()

    def _set_sleep_seconds_for_current_step(self) -> None:
        current_item = self._live_current_step_item()
        if current_item is None:
            return
        step = current_item.step
        if step.step_id != _SLEEP_STEP_ID:
            return
        if not self._set_sleep_seconds_for_step(step):
            return
        self._load_step_detail(step)
        current_item.refresh_text()

    def _save_and_accept(self) -> None:
        self._sync_model_from_selected_list_order()
        self._apply_step_detail_changes()
        if not self.btn_ok.isEnabled():
            self.lab_params_error.setText("请先修正参数 JSON，再保存任务。")
            self.lab_params_error.show()
            return
        try:
            save_task_json(self.project_root, self.model, path=self.task_path)
        except Exception as e:
            show_error(self, "保存失败", str(e))
            return
        self.accept()


class StressRunDialog(QtWidgets.QDialog):
    """压测模式设置弹窗：选择任务、CrealityScan.exe、执行次数。"""

    _SETTINGS_REL = Path("Jens") / "压测模式" / "settings.json"

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self._project_root = Path(project_root)
        self.selected_task: Optional[Path] = None
        self.exe_path: str = ""
        self.rounds: int = 50

        self.setWindowTitle("压测模式")
        self.setModal(True)
        self.setMinimumWidth(680)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        header = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("压测模式")
        title.setObjectName("dialogTitle")
        desc = QtWidgets.QLabel(
            "选择要压测的任务，指定 CrealityScan.exe 与执行次数。"
            "失败/卡死轮次会自动截图、保存日志、杀进程重开并处理上报弹窗。"
        )
        desc.setObjectName("mutedText")
        desc.setWordWrap(True)
        header.addWidget(title)
        header.addWidget(desc)
        root.addLayout(header)

        # 任务选择
        task_box = QtWidgets.QFrame()
        task_box.setStyleSheet(
            "QFrame{background:#f6f9fd;border:1px solid #d5dfec;border-radius:9px;}"
        )
        task_layout = QtWidgets.QVBoxLayout(task_box)
        task_head = QtWidgets.QHBoxLayout()
        task_label = QtWidgets.QLabel("压测任务（单选）")
        task_label.setStyleSheet("font-weight:700;")
        task_head.addWidget(task_label)
        task_head.addStretch(1)
        self.lab_task_count = QtWidgets.QLabel("")
        self.lab_task_count.setObjectName("mutedText")
        task_head.addWidget(self.lab_task_count)
        task_layout.addLayout(task_head)

        self.list_tasks = QtWidgets.QListWidget()
        self.list_tasks.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        task_layout.addWidget(self.list_tasks)
        root.addWidget(task_box)

        # exe 路径
        exe_box = QtWidgets.QHBoxLayout()
        exe_label = QtWidgets.QLabel("CrealityScan.exe")
        exe_label.setStyleSheet("font-weight:700;")
        exe_box.addWidget(exe_label)
        self.edit_exe = QtWidgets.QLineEdit()
        self.edit_exe.setPlaceholderText("选择 CrealityScan.exe（重开软件时使用）")
        exe_box.addWidget(self.edit_exe, 1)
        self.btn_browse = QtWidgets.QPushButton("浏览…")
        self.btn_browse.setObjectName("secondaryBtn")
        self.btn_browse.clicked.connect(self._browse_exe)
        exe_box.addWidget(self.btn_browse)
        root.addLayout(exe_box)

        # 执行次数
        rounds_box = QtWidgets.QHBoxLayout()
        rounds_label = QtWidgets.QLabel("执行次数")
        rounds_label.setStyleSheet("font-weight:700;")
        rounds_box.addWidget(rounds_label)
        self.spin_rounds = QtWidgets.QSpinBox()
        self.spin_rounds.setRange(1, 100000)
        self.spin_rounds.setValue(self.rounds)
        self.spin_rounds.setFixedWidth(120)
        rounds_box.addWidget(self.spin_rounds)
        rounds_box.addStretch(1)
        root.addLayout(rounds_box)

        # 固定默认参数说明
        hint = QtWidgets.QLabel(
            "固定默认参数：卡死判定静默 180s ｜ 软件启动等待 120s ｜ 上报弹窗处理 40s"
        )
        hint.setObjectName("mutedText")
        root.addWidget(hint)

        # 按钮
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)
        self.btn_start = QtWidgets.QPushButton("开始压测")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.clicked.connect(self._start)
        btn_row.addWidget(self.btn_start)
        root.addLayout(btn_row)

        self._load_tasks()
        self._load_settings()
        self._refresh_state()
        self.list_tasks.itemSelectionChanged.connect(self._refresh_state)
        self.edit_exe.textChanged.connect(self._refresh_state)
        self.spin_rounds.valueChanged.connect(lambda _v: self._refresh_state())

    # ---- 数据 ----
    def _task_dir(self) -> Path:
        return self._project_root / "tasks"

    def _load_tasks(self) -> None:
        files = [
            p for p in self._task_dir().glob("*.json")
            if p.is_file() and p.name.lower() != "_queue.json"
        ]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files:
            item = QtWidgets.QListWidgetItem(p.stem)
            item.setData(QtCore.Qt.UserRole, str(p))
            item.setToolTip(str(p))
            self.list_tasks.addItem(item)
        self.lab_task_count.setText(f"共 {len(files)} 个任务")

    def _settings_path(self) -> Path:
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return base / self._SETTINGS_REL

    def _load_settings(self) -> None:
        try:
            raw = json.loads(self._settings_path().read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        exe = str(raw.get("exe_path") or "").strip()
        if exe:
            self.edit_exe.setText(exe)
        try:
            rounds = int(raw.get("rounds") or 0)
            if 1 <= rounds <= 100000:
                self.spin_rounds.setValue(rounds)
        except Exception:
            pass

    def _save_settings(self) -> None:
        try:
            path = self._settings_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"exe_path": self.edit_exe.text().strip(), "rounds": self.spin_rounds.value()}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---- 交互 ----
    def _browse_exe(self) -> None:
        current = self.edit_exe.text().strip()
        start = str(Path(current).parent) if current else str(Path("C:/Program Files"))
        fp, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择 CrealityScan.exe", start, "可执行文件 (*.exe)"
        )
        if fp:
            self.edit_exe.setText(fp)

    def _refresh_state(self) -> None:
        has_task = bool(self.list_tasks.currentItem())
        exe = self.edit_exe.text().strip()
        exe_ok = bool(exe) and Path(exe).is_file() and Path(exe).name.lower() in {"crealityscan.exe", "crealityscan", "creality scan.exe"}
        self.btn_start.setEnabled(has_task and exe_ok)
        tip = []
        if not has_task:
            tip.append("请选择一个任务")
        if not exe_ok:
            tip.append("请选择有效的 CrealityScan.exe 路径")
        self.btn_start.setToolTip("；".join(tip))

    def _start(self) -> None:
        item = self.list_tasks.currentItem()
        if item is None:
            return
        task_path = Path(str(item.data(QtCore.Qt.UserRole)))
        exe = self.edit_exe.text().strip()
        rounds = self.spin_rounds.value()
        if not task_path.is_file():
            show_error(self, "无法开始压测", f"任务文件不存在：{task_path}")
            return
        if not exe or not Path(exe).is_file():
            show_error(self, "无法开始压测", "请选择有效的 CrealityScan.exe 路径。")
            return
        if rounds < 1:
            show_error(self, "无法开始压测", "执行次数必须大于等于 1。")
            return
        self.selected_task = task_path
        self.exe_path = exe
        self.rounds = rounds
        self._save_settings()
        self.accept()
