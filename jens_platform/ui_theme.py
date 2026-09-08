from __future__ import annotations

from PyQt5 import QtGui, QtWidgets  # type: ignore


COLORS = {
    "canvas": "#eaf0f8",
    "surface": "#ffffff",
    "surface_soft": "#f6f9fd",
    "surface_blue": "#edf4ff",
    "ink": "#18283d",
    "muted": "#65758b",
    "line": "#d5dfec",
    "line_strong": "#becbdb",
    "primary": "#2e6fd8",
    "primary_hover": "#2358aa",
    "success": "#167553",
    "warning": "#9a5e12",
    "danger": "#b43b3b",
}


def apply_app_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    available = set(QtGui.QFontDatabase().families())
    for family in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"):
        if family in available:
            app.setFont(QtGui.QFont(family, 9))
            break
    app.setStyleSheet(APP_STYLESHEET)


APP_STYLESHEET = r"""
QWidget {
  color: #18283d;
  font-size: 13px;
}
QMainWindow, QDialog { background: #eaf0f8; }
QToolTip {
  color: #ffffff;
  background: #18283d;
  border: 0;
  padding: 6px 8px;
}
QStatusBar {
  min-height: 28px;
  color: #65758b;
  background: #f8fafd;
  border-top: 1px solid #d5dfec;
}
QFrame#appSidebar {
  background: #17283e;
  border: 0;
}
QLabel#brandTitle { color: #ffffff; font-size: 18px; font-weight: 700; }
QLabel#brandSubtitle { color: #9fb1c7; font-size: 11px; }
QLabel#sidebarLabel { color: #8196af; font-size: 11px; font-weight: 700; }
QPushButton#navButton {
  min-height: 42px;
  padding: 0 12px;
  color: #c9d5e3;
  background: transparent;
  border: 0;
  border-radius: 9px;
  text-align: left;
}
QPushButton#navButton:hover { color: #ffffff; background: #223a56; }
QPushButton#navButton:checked { color: #ffffff; background: #2e6fd8; font-weight: 700; }
QFrame#sidebarStatus {
  background: #20364f;
  border: 1px solid #2e4866;
  border-radius: 11px;
}
QLabel#sidebarStatusTitle { color: #ffffff; font-weight: 700; }
QLabel#sidebarStatusText { color: #9fb1c7; font-size: 11px; }

QFrame#topBar, QFrame#dialogHeader, QFrame#dialogFooter {
  background: #ffffff;
  border: 0;
}
QFrame#topBar { border-bottom: 1px solid #d5dfec; }
QFrame#dialogHeader { border-bottom: 1px solid #d5dfec; }
QFrame#dialogFooter { border-top: 1px solid #d5dfec; }
QLabel#pageTitle { color: #18283d; font-size: 21px; font-weight: 700; }
QLabel#dialogTitle { color: #18283d; font-size: 18px; font-weight: 700; }
QLabel#pageSubtitle, QLabel#mutedText, QLabel#fieldHelp {
  color: #65758b;
  font-size: 11px;
}
QLabel#sectionTitle { color: #18283d; font-size: 14px; font-weight: 700; }
QLabel#metricValue { color: #18283d; font-size: 17px; font-weight: 700; }
QLabel#metricLabel { color: #65758b; font-size: 10px; }
QLabel#fieldLabel { color: #42566f; font-size: 11px; font-weight: 700; }
QLabel#deviceValue { color: #18283d; font-size: 13px; font-weight: 600; }
QLabel#calibrationScore {
  color: #167553;
  font-family: "Cascadia Mono", "Consolas";
  font-size: 40px;
  font-weight: 700;
}
QLabel#calibrationScore[state="empty"] { color: #9a5e12; }
QLabel#calibrationScore[state="error"] { color: #b43b3b; }
QLabel#statusGood { color: #167553; background: #e6f5ef; border-radius: 7px; padding: 5px 8px; font-weight: 700; }
QLabel#statusWarn { color: #9a5e12; background: #fff4db; border-radius: 7px; padding: 5px 8px; font-weight: 700; }
QLabel#statusBad { color: #a73333; background: #fdeaea; border-radius: 7px; padding: 5px 8px; font-weight: 700; }

QFrame#panel, QGroupBox {
  background: #ffffff;
  border: 1px solid #d5dfec;
  border-radius: 12px;
}
QGroupBox {
  margin-top: 14px;
  padding-top: 7px;
  font-weight: 700;
}
QGroupBox::title {
  subcontrol-origin: margin;
  left: 14px;
  padding: 0 6px;
  color: #314862;
  background: #ffffff;
}
QFrame#subtlePanel { background: #f6f9fd; border: 1px solid #dce4ee; border-radius: 10px; }
QFrame#metricCell { background: #f6f9fd; border: 0; border-radius: 9px; }
QFrame#separator { background: #d5dfec; border: 0; }

QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QTreeWidget,
QTableWidget, QComboBox, QSpinBox, QDoubleSpinBox {
  color: #18283d;
  background: #ffffff;
  border: 1px solid #d5dfec;
  border-radius: 9px;
  padding: 6px 8px;
  selection-color: #18283d;
  selection-background-color: #dce9ff;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { min-height: 28px; }
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QListWidget:hover,
QTreeWidget:hover, QTableWidget:hover, QComboBox:hover, QSpinBox:hover,
QDoubleSpinBox:hover { border-color: #b7c7da; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QListWidget:focus,
QTreeWidget:focus, QTableWidget:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus { border-color: #2e6fd8; }
QLineEdit[error="true"], QPlainTextEdit[error="true"] { border-color: #b43b3b; background: #fffafa; }
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled { color: #91a0b3; background: #f1f4f8; }
QComboBox::drop-down { width: 28px; border: 0; }
QAbstractItemView { outline: 0; }
QListWidget::item, QTreeWidget::item { min-height: 30px; padding: 5px 7px; border-radius: 7px; }
QListWidget::item:hover, QTreeWidget::item:hover { background: #f2f6fb; }
QListWidget::item:selected, QTreeWidget::item:selected { color: #2358aa; background: #dce9ff; }

QPushButton, QToolButton {
  min-height: 34px;
  padding: 0 13px;
  color: #18283d;
  background: #ffffff;
  border: 1px solid #d5dfec;
  border-radius: 9px;
  font-weight: 600;
}
QPushButton:hover, QToolButton:hover { background: #f2f6fb; border-color: #9db8df; }
QPushButton:pressed, QToolButton:pressed { background: #e5edf7; }
QPushButton:focus, QToolButton:focus { border: 1px solid #2e6fd8; }
QPushButton:disabled, QToolButton:disabled { color: #95a3b5; background: #edf1f6; border-color: #e0e6ee; }
QPushButton#primaryBtn, QToolButton#primaryBtn { color: #ffffff; background: #2e6fd8; border-color: #2e6fd8; }
QPushButton#primaryBtn:hover, QToolButton#primaryBtn:hover { background: #2358aa; border-color: #2358aa; }
QPushButton#dangerBtn { color: #a73333; background: #ffffff; border-color: #e2baba; }
QPushButton#dangerBtn:hover { background: #fdeaea; border-color: #d58e8e; }
QPushButton#quietBtn { color: #42566f; background: transparent; border-color: transparent; }
QPushButton#quietBtn:hover { color: #2358aa; background: #edf4ff; }

QTabWidget::pane { background: #ffffff; border: 1px solid #d5dfec; border-radius: 10px; top: -1px; }
QTabBar::tab {
  min-width: 108px;
  min-height: 34px;
  padding: 0 13px;
  color: #65758b;
  background: #eaf0f8;
  border: 1px solid #d5dfec;
  border-bottom: 0;
  border-top-left-radius: 9px;
  border-top-right-radius: 9px;
  margin-right: 4px;
}
QTabBar::tab:selected { color: #2358aa; background: #ffffff; font-weight: 700; }
QHeaderView::section {
  min-height: 34px;
  padding: 5px 8px;
  color: #42566f;
  background: #f3f6fa;
  border: 0;
  border-bottom: 1px solid #d5dfec;
  font-weight: 700;
}
QTableWidget { alternate-background-color: #f8fafd; gridline-color: #e2e8f0; }
QTableWidget::item { padding: 5px; }
QCheckBox, QRadioButton { spacing: 7px; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
QProgressBar { min-height: 9px; max-height: 9px; background: #dfe6ef; border: 0; border-radius: 4px; }
QProgressBar::chunk { background: #2e6fd8; border-radius: 4px; }
QSplitter::handle { background: #d5dfec; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
QScrollBar:vertical { width: 10px; margin: 2px; background: transparent; }
QScrollBar::handle:vertical { min-height: 28px; background: #c5d1df; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #aabacc; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { height: 0; background: transparent; }
"""
