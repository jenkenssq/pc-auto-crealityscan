# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from motion_client import create_motion_client


def compare_limit_snapshots(
    middle_snapshot: dict[int, int],
    bottom_snapshot: dict[int, int],
) -> list[tuple[int, int, int]]:
    """比较中间位与最低位输入快照，返回发生变化的输入点。"""
    expected_ports = set(range(16))
    for name, snapshot in (("中间位置", middle_snapshot), ("最低位置", bottom_snapshot)):
        missing_ports = sorted(expected_ports.difference(snapshot))
        if missing_ports:
            missing_text = ", ".join(f"IN{port}" for port in missing_ports)
            raise ValueError(f"{name}快照缺少输入点：{missing_text}")

    return [
        (port, middle_snapshot[port], bottom_snapshot[port])
        for port in range(16)
        if middle_snapshot[port] != bottom_snapshot[port]
    ]


class CommandWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(object, object, object)

    def __init__(self, job_id: object, fn: Callable[[], Any], parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._job_id = job_id
        self._fn = fn

    @QtCore.pyqtSlot()
    def run(self) -> None:
        try:
            self.finished.emit(self._job_id, self._fn(), None)
        except Exception as exc:
            self.finished.emit(self._job_id, None, exc)


class SlideRailWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("滑轨控制台")
        self.resize(1180, 760)

        self.client = None
        self._threads: list[QtCore.QThread] = []
        self._jobs: dict[object, tuple[str, QtCore.QThread, CommandWorker, Optional[Callable[[Any], None]]]] = {}
        self._busy_count = 0
        self._limit_middle_snapshot: dict[int, int] = {}
        self._limit_bottom_snapshot: dict[int, int] = {}
        self.position_log_dir = Path(__file__).resolve().parent / "position_logs"

        self._build_ui()
        self._apply_style()
        self._refresh_enabled()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        try:
            if self.client is not None:
                self.client.disconnect()
        finally:
            super().closeEvent(event)

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)

        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(10)
        root.addLayout(top)

        self.host_edit = QtWidgets.QLineEdit("127.0.0.1")
        self.port_spin = QtWidgets.QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(5000)
        self.mock_check = QtWidgets.QCheckBox("模拟模式")
        self.mock_check.setChecked(True)

        self.service_status = QtWidgets.QLabel("服务：未连接")
        self.controller_status = QtWidgets.QLabel("控制器：未知")

        self.connect_btn = QtWidgets.QPushButton("连接服务")
        self.disconnect_btn = QtWidgets.QPushButton("断开服务")
        self.check_btn = QtWidgets.QPushButton("检查服务")

        top.addWidget(QtWidgets.QLabel("Host"))
        top.addWidget(self.host_edit)
        top.addWidget(QtWidgets.QLabel("Port"))
        top.addWidget(self.port_spin)
        top.addWidget(self.mock_check)
        top.addWidget(self.connect_btn)
        top.addWidget(self.disconnect_btn)
        top.addWidget(self.check_btn)
        top.addStretch(1)
        top.addWidget(self.service_status)
        top.addWidget(self.controller_status)

        body = QtWidgets.QSplitter(QtCore.Qt.Horizontal, central)
        root.addWidget(body, 1)

        left = QtWidgets.QWidget(body)
        body.addWidget(left)
        body.setStretchFactor(0, 3)

        right = QtWidgets.QWidget(body)
        body.addWidget(right)
        body.setStretchFactor(1, 2)

        grid = QtWidgets.QGridLayout(left)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        grid.addWidget(self._controller_group(), 0, 0)
        grid.addWidget(self._lift_group(), 0, 1)
        grid.addWidget(self._horizontal_group(), 1, 0)
        grid.addWidget(self._combo_group(), 1, 1)
        grid.addWidget(self._continuous_group(), 2, 0)
        grid.addWidget(self._debug_group(), 2, 1)

        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self._limit_diagnostic_group())

        log_header = QtWidgets.QHBoxLayout()
        self.busy_label = QtWidgets.QLabel("空闲")
        self.clear_log_btn = QtWidgets.QPushButton("清空日志")
        log_header.addWidget(QtWidgets.QLabel("命令日志"))
        log_header.addStretch(1)
        log_header.addWidget(self.busy_label)
        log_header.addWidget(self.clear_log_btn)
        right_layout.addLayout(log_header)

        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        right_layout.addWidget(self.log_edit, 1)

        self.connect_btn.clicked.connect(self._connect_service)
        self.disconnect_btn.clicked.connect(self._disconnect_service)
        self.check_btn.clicked.connect(lambda: self._run_client_command("检查服务", lambda c: {"status": "success" if c.check_connection() else "error"}))
        self.clear_log_btn.clicked.connect(self.log_edit.clear)

    def _limit_diagnostic_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("限位诊断")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(6)

        hint = QtWidgets.QLabel("先将升降台停在中间位置采集，再移动到最低位置采集。诊断过程只读取输入点，不会驱动设备。")
        hint.setWordWrap(True)
        hint.setObjectName("secondaryText")
        layout.addWidget(hint)

        button_row = QtWidgets.QHBoxLayout()
        self.capture_middle_limit_btn = QtWidgets.QPushButton("采集中间位置")
        self.capture_bottom_limit_btn = QtWidgets.QPushButton("采集最低位置")
        self.clear_limit_diagnostic_btn = QtWidgets.QPushButton("清除诊断")
        button_row.addWidget(self.capture_middle_limit_btn)
        button_row.addWidget(self.capture_bottom_limit_btn)
        button_row.addWidget(self.clear_limit_diagnostic_btn)
        layout.addLayout(button_row)

        self.limit_middle_value = QtWidgets.QLabel("中间位置：未采集")
        self.limit_bottom_value = QtWidgets.QLabel("最低位置：未采集")
        self.limit_result_value = QtWidgets.QLabel("等待两次采集")
        self.limit_result_value.setObjectName("diagnosticPending")
        self.limit_result_value.setWordWrap(True)
        for label in (self.limit_middle_value, self.limit_bottom_value, self.limit_result_value):
            label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(self.limit_middle_value)
        layout.addWidget(self.limit_bottom_value)
        layout.addWidget(self.limit_result_value)

        self.capture_middle_limit_btn.clicked.connect(lambda: self._capture_limit_snapshot("middle"))
        self.capture_bottom_limit_btn.clicked.connect(lambda: self._capture_limit_snapshot("bottom"))
        self.clear_limit_diagnostic_btn.clicked.connect(self._clear_limit_diagnostic)
        return group

    def _controller_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("控制器")
        form = QtWidgets.QFormLayout(group)

        self.dll_edit = QtWidgets.QLineEdit("zauxdll.dll")
        self.ip_edit = QtWidgets.QLineEdit("192.168.0.11")
        self.connect_controller_btn = QtWidgets.QPushButton("连接控制器")
        self.disconnect_controller_btn = QtWidgets.QPushButton("断开控制器")
        self.is_connected_btn = QtWidgets.QPushButton("控制器状态")
        self.emergency_btn = QtWidgets.QPushButton("急停")
        self.emergency_btn.setObjectName("dangerButton")

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.connect_controller_btn)
        row.addWidget(self.disconnect_controller_btn)
        row.addWidget(self.is_connected_btn)
        row.addWidget(self.emergency_btn)

        form.addRow("DLL", self.dll_edit)
        form.addRow("IP", self.ip_edit)
        form.addRow(row)

        self.connect_controller_btn.clicked.connect(
            lambda: self._run_client_command(
                "连接控制器",
                lambda c: c.connect_controller(self.dll_edit.text().strip() or "zauxdll.dll", self.ip_edit.text().strip() or "192.168.0.11"),
                update_controller=True,
            )
        )
        self.disconnect_controller_btn.clicked.connect(lambda: self._run_client_command("断开控制器", lambda c: c.disconnect_controller(), update_controller=True))
        self.is_connected_btn.clicked.connect(self._check_controller)
        self.emergency_btn.clicked.connect(lambda: self._run_client_command("急停", lambda c: c.emergency_stop(), allow_when_busy=True, record_position_after=True))
        return group

    def _lift_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("升降")
        layout = QtWidgets.QGridLayout(group)

        self.lift_seconds = QtWidgets.QDoubleSpinBox()
        self.lift_seconds.setRange(0.1, 120.0)
        self.lift_seconds.setDecimals(2)
        self.lift_seconds.setValue(2.0)
        self.safety_margin = QtWidgets.QDoubleSpinBox()
        self.safety_margin.setRange(0.0, 20.0)
        self.safety_margin.setDecimals(2)
        self.safety_margin.setValue(1.0)
        self.safe_down = QtWidgets.QDoubleSpinBox()
        self.safe_down.setRange(0.0, 20.0)
        self.safe_down.setDecimals(2)
        self.safe_down.setValue(0.2)
        self.lift_counter_value = QtWidgets.QLabel("距最低位：0.0 秒（已知）")
        self.lift_counter_value.setObjectName("secondaryText")

        self.lift_up_btn = QtWidgets.QPushButton("持续上升")
        self.lift_down_btn = QtWidgets.QPushButton("持续下降")
        self.lift_stop_btn = QtWidgets.QPushButton("停止升降")
        self.lift_stop_btn.setObjectName("warningButton")
        self.lift_up_seconds_btn = QtWidgets.QPushButton("上升指定秒")
        self.lift_down_seconds_btn = QtWidgets.QPushButton("下降指定秒")
        self.lift_bottom_btn = QtWidgets.QPushButton("下降到底")
        self.home_lift_btn = QtWidgets.QPushButton("回上限位")

        layout.addWidget(QtWidgets.QLabel("秒数"), 0, 0)
        layout.addWidget(self.lift_seconds, 0, 1)
        layout.addWidget(QtWidgets.QLabel("到底余量"), 1, 0)
        layout.addWidget(self.safety_margin, 1, 1)
        layout.addWidget(QtWidgets.QLabel("回零安全下降"), 2, 0)
        layout.addWidget(self.safe_down, 2, 1)
        layout.addWidget(self.lift_up_btn, 3, 0)
        layout.addWidget(self.lift_down_btn, 3, 1)
        layout.addWidget(self.lift_stop_btn, 4, 0)
        layout.addWidget(self.lift_up_seconds_btn, 4, 1)
        layout.addWidget(self.lift_down_seconds_btn, 5, 0)
        layout.addWidget(self.lift_bottom_btn, 5, 1)
        layout.addWidget(self.home_lift_btn, 6, 0, 1, 2)
        layout.addWidget(self.lift_counter_value, 7, 0, 1, 2)

        self.lift_up_btn.clicked.connect(lambda: self._run_client_command("持续上升", lambda c: c.lift_up(), record_position_after=True))
        self.lift_down_btn.clicked.connect(lambda: self._run_client_command("持续下降", lambda c: c.lift_down(), record_position_after=True))
        self.lift_stop_btn.clicked.connect(lambda: self._run_client_command("停止升降", lambda c: c.lift_stop(), allow_when_busy=True, record_position_after=True))
        self.lift_up_seconds_btn.clicked.connect(lambda: self._run_client_command("上升指定秒", lambda c: c.lift_up_duration(self.lift_seconds.value()), record_position_after=True))
        self.lift_down_seconds_btn.clicked.connect(lambda: self._run_client_command("下降指定秒", lambda c: c.lift_down_duration(self.lift_seconds.value()), record_position_after=True))
        self.lift_bottom_btn.clicked.connect(lambda: self._run_client_command("下降到底", lambda c: c.lift_down_to_bottom(self.safety_margin.value()), record_position_after=True))
        self.home_lift_btn.clicked.connect(lambda: self._run_client_command("回上限位", lambda c: c.home_lift_platform(self.safe_down.value()), record_position_after=True))
        return group

    def _horizontal_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("水平移动")
        layout = QtWidgets.QGridLayout(group)

        self.pulse_spin = QtWidgets.QSpinBox()
        self.pulse_spin.setRange(1, 2_000_000)
        self.pulse_spin.setSingleStep(1000)
        self.pulse_spin.setValue(10000)
        self.relative_pulse_spin = QtWidgets.QSpinBox()
        self.relative_pulse_spin.setRange(-2_000_000, 2_000_000)
        self.relative_pulse_spin.setSingleStep(1000)
        self.relative_pulse_spin.setValue(10000)
        self.abs_pos_spin = QtWidgets.QSpinBox()
        self.abs_pos_spin.setRange(-2_000_000, 2_000_000)
        self.abs_pos_spin.setSingleStep(1000)

        self.move_left_btn = QtWidgets.QPushButton("向左移动")
        self.move_right_btn = QtWidgets.QPushButton("向右移动")
        self.move_relative_btn = QtWidgets.QPushButton("相对移动")
        self.move_abs_btn = QtWidgets.QPushButton("绝对移动")
        self.get_pos_btn = QtWidgets.QPushButton("读取位置")
        self.set_zero_btn = QtWidgets.QPushButton("设软零点")
        self.reset_zero_btn = QtWidgets.QPushButton("回软零点")
        self.position_value = QtWidgets.QLabel("-")
        self.relative_position_value = QtWidgets.QLabel("-")
        self.soft_zero_value = QtWidgets.QLabel("-")

        layout.addWidget(QtWidgets.QLabel("单步脉冲"), 0, 0)
        layout.addWidget(self.pulse_spin, 0, 1)
        layout.addWidget(self.move_left_btn, 1, 0)
        layout.addWidget(self.move_right_btn, 1, 1)
        layout.addWidget(QtWidgets.QLabel("相对脉冲"), 2, 0)
        layout.addWidget(self.relative_pulse_spin, 2, 1)
        layout.addWidget(QtWidgets.QLabel("绝对位置"), 3, 0)
        layout.addWidget(self.abs_pos_spin, 3, 1)
        layout.addWidget(self.move_relative_btn, 4, 0)
        layout.addWidget(self.move_abs_btn, 4, 1)
        layout.addWidget(self.get_pos_btn, 5, 0)
        layout.addWidget(self.set_zero_btn, 5, 1)
        layout.addWidget(self.reset_zero_btn, 6, 0, 1, 2)
        layout.addWidget(QtWidgets.QLabel("绝对位置"), 7, 0)
        layout.addWidget(self.position_value, 7, 1)
        layout.addWidget(QtWidgets.QLabel("相对位置"), 8, 0)
        layout.addWidget(self.relative_position_value, 8, 1)
        layout.addWidget(QtWidgets.QLabel("软零点"), 9, 0)
        layout.addWidget(self.soft_zero_value, 9, 1)

        self.move_left_btn.clicked.connect(lambda: self._run_client_command("向左移动", lambda c: c.move_relative(-abs(self.pulse_spin.value())), record_position_after=True))
        self.move_right_btn.clicked.connect(lambda: self._run_client_command("向右移动", lambda c: c.move_relative(abs(self.pulse_spin.value())), record_position_after=True))
        self.move_relative_btn.clicked.connect(lambda: self._run_client_command("相对移动", lambda c: c.move_relative(self.relative_pulse_spin.value()), record_position_after=True))
        self.move_abs_btn.clicked.connect(lambda: self._run_client_command("绝对移动", lambda c: c.move_absolute(self.abs_pos_spin.value()), record_position_after=True))
        self.get_pos_btn.clicked.connect(lambda: self._run_client_command("读取位置", lambda c: c.get_position(), record_position_after=True))
        self.set_zero_btn.clicked.connect(lambda: self._run_client_command("设软零点", lambda c: c.set_soft_zero(), record_position_after=True))
        self.reset_zero_btn.clicked.connect(lambda: self._run_client_command("回软零点", lambda c: c.reset_to_zero(), record_position_after=True))
        return group

    def _combo_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("组合动作")
        layout = QtWidgets.QGridLayout(group)

        self.combo_lift_seconds = QtWidgets.QDoubleSpinBox()
        self.combo_lift_seconds.setRange(-120.0, 120.0)
        self.combo_lift_seconds.setDecimals(2)
        self.combo_horizontal_pulse = QtWidgets.QSpinBox()
        self.combo_horizontal_pulse.setRange(-2_000_000, 2_000_000)
        self.combo_horizontal_pulse.setSingleStep(1000)
        self.combo_reset_first = QtWidgets.QCheckBox("先回上限位")
        self.combo_safe_down = QtWidgets.QDoubleSpinBox()
        self.combo_safe_down.setRange(0.0, 20.0)
        self.combo_safe_down.setDecimals(2)
        self.combo_safe_down.setValue(0.2)

        self.pre_scan_btn = QtWidgets.QPushButton("执行扫描前运动")
        self.object_scan_btn = QtWidgets.QPushButton("物体扫描前运动")

        layout.addWidget(QtWidgets.QLabel("升降秒数"), 0, 0)
        layout.addWidget(self.combo_lift_seconds, 0, 1)
        layout.addWidget(QtWidgets.QLabel("水平脉冲"), 1, 0)
        layout.addWidget(self.combo_horizontal_pulse, 1, 1)
        layout.addWidget(self.combo_reset_first, 2, 0)
        layout.addWidget(self.combo_safe_down, 2, 1)
        layout.addWidget(self.pre_scan_btn, 3, 0, 1, 2)
        layout.addWidget(self.object_scan_btn, 4, 0, 1, 2)

        self.pre_scan_btn.clicked.connect(
            lambda: self._run_client_command(
                "执行扫描前运动",
                lambda c: c.execute_pre_scan_motion(
                    lift_seconds=self.combo_lift_seconds.value(),
                    horizontal_pulse=self.combo_horizontal_pulse.value(),
                    reset_first=self.combo_reset_first.isChecked(),
                    safe_down=self.combo_safe_down.value(),
                ),
                record_position_after=True,
            )
        )
        self.object_scan_btn.clicked.connect(
            lambda: self._run_client_command(
                "物体扫描前运动",
                lambda c: c.execute_object_scan_motion(
                    horizontal_pulse=self.combo_horizontal_pulse.value(),
                    scan_cycle_seconds=max(0.1, abs(self.combo_lift_seconds.value()) or 2),
                    object_type="manual",
                ),
                record_position_after=True,
            )
        )
        return group

    def _continuous_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("连续运动")
        layout = QtWidgets.QGridLayout(group)

        self.cycle_seconds = QtWidgets.QDoubleSpinBox()
        self.cycle_seconds.setRange(0.1, 120.0)
        self.cycle_seconds.setDecimals(2)
        self.cycle_seconds.setValue(4.0)
        self.sweep_pulse = QtWidgets.QSpinBox()
        self.sweep_pulse.setRange(1, 2_000_000)
        self.sweep_pulse.setSingleStep(1000)
        self.sweep_pulse.setValue(10000)
        self.sweep_speed = QtWidgets.QSpinBox()
        self.sweep_speed.setRange(1, 500000)
        self.sweep_speed.setSingleStep(1000)
        self.sweep_speed.setValue(2000)

        self.continuous_cycle_btn = QtWidgets.QPushButton("启动连续扫描")
        self.stop_continuous_btn = QtWidgets.QPushButton("停止连续扫描")
        self.stop_continuous_btn.setObjectName("warningButton")
        self.start_sweep_btn = QtWidgets.QPushButton("启动水平往返")
        self.stop_sweep_btn = QtWidgets.QPushButton("停止水平往返")
        self.stop_sweep_btn.setObjectName("warningButton")

        layout.addWidget(QtWidgets.QLabel("上下秒数"), 0, 0)
        layout.addWidget(self.cycle_seconds, 0, 1)
        layout.addWidget(QtWidgets.QLabel("往返脉冲"), 1, 0)
        layout.addWidget(self.sweep_pulse, 1, 1)
        layout.addWidget(QtWidgets.QLabel("水平速度"), 2, 0)
        layout.addWidget(self.sweep_speed, 2, 1)
        layout.addWidget(self.continuous_cycle_btn, 3, 0)
        layout.addWidget(self.stop_continuous_btn, 3, 1)
        layout.addWidget(self.start_sweep_btn, 4, 0)
        layout.addWidget(self.stop_sweep_btn, 4, 1)

        self.continuous_cycle_btn.clicked.connect(
            lambda: self._run_client_command(
                "启动连续扫描",
                lambda c: c.continuous_scan_cycle(self.cycle_seconds.value(), self.sweep_pulse.value(), self.sweep_speed.value()),
                record_position_after=True,
            )
        )
        self.stop_continuous_btn.clicked.connect(lambda: self._run_client_command("停止连续扫描", lambda c: c.stop_continuous(), allow_when_busy=True, record_position_after=True))
        self.start_sweep_btn.clicked.connect(lambda: self._run_client_command("启动水平往返", lambda c: c.start_horizontal_sweep(self.sweep_pulse.value(), self.sweep_speed.value()), record_position_after=True))
        self.stop_sweep_btn.clicked.connect(lambda: self._run_client_command("停止水平往返", lambda c: c.stop_horizontal_sweep(), allow_when_busy=True, record_position_after=True))
        return group

    def _debug_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("调试")
        layout = QtWidgets.QGridLayout(group)

        self.input_spin = QtWidgets.QSpinBox()
        self.input_spin.setRange(0, 255)
        self.input_spin.setValue(2)
        self.axis_spin = QtWidgets.QSpinBox()
        self.axis_spin.setRange(0, 16)
        self.axis_spin.setValue(0)
        self.speed_spin = QtWidgets.QSpinBox()
        self.speed_spin.setRange(1, 500000)
        self.speed_spin.setSingleStep(1000)
        self.speed_spin.setValue(80000)
        self.accel_spin = QtWidgets.QSpinBox()
        self.accel_spin.setRange(1, 1000000)
        self.accel_spin.setSingleStep(1000)
        self.accel_spin.setValue(150000)
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItem("正向", 1)
        self.direction_combo.addItem("反向", -1)

        self.read_input_btn = QtWidgets.QPushButton("读取输入")
        self.set_speed_btn = QtWidgets.QPushButton("设置速度")
        self.set_accel_btn = QtWidgets.QPushButton("设置加速度")
        self.stop_axis_btn = QtWidgets.QPushButton("停止轴")
        self.continuous_move_btn = QtWidgets.QPushButton("轴连续移动")

        layout.addWidget(QtWidgets.QLabel("输入点"), 0, 0)
        layout.addWidget(self.input_spin, 0, 1)
        layout.addWidget(self.read_input_btn, 0, 2)
        layout.addWidget(QtWidgets.QLabel("轴号"), 1, 0)
        layout.addWidget(self.axis_spin, 1, 1)
        layout.addWidget(self.stop_axis_btn, 1, 2)
        layout.addWidget(QtWidgets.QLabel("速度"), 2, 0)
        layout.addWidget(self.speed_spin, 2, 1)
        layout.addWidget(self.set_speed_btn, 2, 2)
        layout.addWidget(QtWidgets.QLabel("加速度"), 3, 0)
        layout.addWidget(self.accel_spin, 3, 1)
        layout.addWidget(self.set_accel_btn, 3, 2)
        layout.addWidget(QtWidgets.QLabel("方向"), 4, 0)
        layout.addWidget(self.direction_combo, 4, 1)
        layout.addWidget(self.continuous_move_btn, 4, 2)

        self.read_input_btn.clicked.connect(lambda: self._run_client_command("读取输入", lambda c: c.read_input(self.input_spin.value())))
        self.set_speed_btn.clicked.connect(lambda: self._run_client_command("设置速度", lambda c: c.set_speed(self.axis_spin.value(), self.speed_spin.value())))
        self.set_accel_btn.clicked.connect(lambda: self._run_client_command("设置加速度", lambda c: c.set_accel(self.axis_spin.value(), self.accel_spin.value())))
        self.stop_axis_btn.clicked.connect(lambda: self._run_client_command("停止轴", lambda c: c.stop_axis(self.axis_spin.value()), allow_when_busy=True, record_position_after=True))
        self.continuous_move_btn.clicked.connect(
            lambda: self._run_client_command(
                "轴连续移动",
                lambda c: c.continuous_move(self.axis_spin.value(), int(self.direction_combo.currentData()), self.speed_spin.value()),
                record_position_after=True,
            )
        )
        return group

    def _connect_service(self) -> None:
        if self.client is not None:
            self._append_log("服务已连接")
            return

        host = self.host_edit.text().strip() or "127.0.0.1"
        port = int(self.port_spin.value())
        use_mock = self.mock_check.isChecked()
        self._append_log(f"连接服务 host={host} port={port} mock={use_mock}")

        def do_connect() -> Any:
            client = create_motion_client(use_mock=use_mock, host=host, port=port)
            ok = client.connect()
            if not ok:
                raise RuntimeError(getattr(client, "last_error", None) or "无法连接到运动控制服务")
            return client

        self._run_worker("连接服务", do_connect, on_success=self._on_service_connected)

    def _on_service_connected(self, client: Any) -> None:
        self.client = client
        self.service_status.setText("服务：已连接")
        self._append_response("连接服务", {"status": "success", "mock": self.mock_check.isChecked()})
        self._refresh_enabled()

    def _disconnect_service(self) -> None:
        if self.client is None:
            return
        try:
            self.client.disconnect()
        finally:
            self.client = None
            self.service_status.setText("服务：未连接")
            self.controller_status.setText("控制器：未知")
            self._append_log("已断开服务")
            self._refresh_enabled()

    def _check_controller(self) -> None:
        def command(client: Any) -> Any:
            connected = client.is_controller_connected()
            return {"status": "success", "connected": connected}

        self._run_client_command("控制器状态", command, update_controller=True)

    @staticmethod
    def _read_limit_inputs(client: Any) -> dict[int, int]:
        snapshot: dict[int, int] = {}
        for input_number in range(16):
            response = client.read_input(input_number)
            if not isinstance(response, dict):
                raise RuntimeError(f"IN{input_number} 读取失败：服务返回格式无效")
            if response.get("status") != "success":
                message = response.get("message") or response.get("error") or "服务未返回成功状态"
                raise RuntimeError(f"IN{input_number} 读取失败：{message}")
            value = response.get("value")
            if isinstance(value, bool):
                snapshot[input_number] = int(value)
            elif isinstance(value, (int, float)) and value in (0, 1):
                snapshot[input_number] = int(value)
            else:
                raise RuntimeError(f"IN{input_number} 读取失败：无效电平 {value!r}")
        return snapshot

    def _capture_limit_snapshot(self, position: str) -> None:
        if position == "middle":
            title = "采集中间位置限位输入"
        elif position == "bottom":
            title = "采集最低位置限位输入"
        else:
            raise ValueError(f"未知限位诊断位置：{position}")

        self._run_client_command(
            title,
            self._read_limit_inputs,
            on_success=lambda result: self._on_limit_snapshot_captured(position, result),
        )

    def _on_limit_snapshot_captured(self, position: str, snapshot: Any) -> None:
        if not isinstance(snapshot, dict):
            raise RuntimeError("限位诊断快照格式无效")
        normalized_snapshot = {int(port): int(value) for port, value in snapshot.items()}
        summary = self._format_limit_snapshot(normalized_snapshot)
        if position == "middle":
            self._limit_middle_snapshot = normalized_snapshot
            self.limit_middle_value.setText(f"中间位置：{summary}")
        else:
            self._limit_bottom_snapshot = normalized_snapshot
            self.limit_bottom_value.setText(f"最低位置：{summary}")
        self._update_limit_diagnostic_result()

    @staticmethod
    def _format_limit_snapshot(snapshot: dict[int, int]) -> str:
        return "  ".join(f"IN{port}={snapshot[port]}" for port in range(16))

    def _update_limit_diagnostic_result(self) -> None:
        if not self._limit_middle_snapshot or not self._limit_bottom_snapshot:
            missing_position = "最低位置" if self._limit_middle_snapshot else "中间位置"
            self._set_limit_result(f"等待采集{missing_position}", "pending")
            return

        changes = compare_limit_snapshots(self._limit_middle_snapshot, self._limit_bottom_snapshot)
        if not changes:
            self._set_limit_result("IN0–IN15 均未变化，请检查接线、端口范围，或确认最低位限位已触发。", "warning")
            return

        descriptions = [
            f"IN{port}：{middle} → {bottom}（{'低电平' if bottom == 0 else '高电平'}触发）"
            for port, middle, bottom in changes
        ]
        if len(changes) == 1:
            self._set_limit_result(f"候选下限位：{descriptions[0]}", "success")
        else:
            self._set_limit_result(
                "检测到多个变化端口，请重复采集确认：" + "；".join(descriptions),
                "warning",
            )

    def _set_limit_result(self, text: str, state: str) -> None:
        self.limit_result_value.setText(text)
        object_names = {
            "pending": "diagnosticPending",
            "success": "diagnosticSuccess",
            "warning": "diagnosticWarning",
        }
        self.limit_result_value.setObjectName(object_names[state])
        self.limit_result_value.style().unpolish(self.limit_result_value)
        self.limit_result_value.style().polish(self.limit_result_value)

    def _clear_limit_diagnostic(self) -> None:
        self._limit_middle_snapshot = {}
        self._limit_bottom_snapshot = {}
        self.limit_middle_value.setText("中间位置：未采集")
        self.limit_bottom_value.setText("最低位置：未采集")
        self._set_limit_result("等待两次采集", "pending")
        self._append_log("已清除限位诊断结果")

    def _run_client_command(
        self,
        title: str,
        command: Callable[[Any], Any],
        *,
        update_controller: bool = False,
        allow_when_busy: bool = False,
        record_position_after: bool = False,
        on_success: Optional[Callable[[Any], None]] = None,
    ) -> None:
        if self.client is None:
            QtWidgets.QMessageBox.warning(self, "未连接", "请先连接运动控制服务。")
            return
        if self._busy_count and not allow_when_busy:
            QtWidgets.QMessageBox.information(self, "命令执行中", "请等待当前命令完成。")
            return

        def do_command() -> Any:
            return command(self.client)

        self._run_worker(
            title,
            do_command,
            on_success=lambda result: self._on_client_command_success(
                title,
                result,
                update_controller=update_controller,
                record_position_after=record_position_after,
                on_success=on_success,
            ),
        )

    def _on_client_command_success(
        self,
        title: str,
        result: Any,
        *,
        update_controller: bool,
        record_position_after: bool,
        on_success: Optional[Callable[[Any], None]],
    ) -> None:
        self._on_command_success(
            title,
            result,
            update_controller=update_controller,
            record_position_after=record_position_after,
        )
        if on_success is not None and not (isinstance(result, dict) and result.get("status") == "error"):
            on_success(result)

    def _run_worker(
        self,
        title: str,
        fn: Callable[[], Any],
        *,
        on_success: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self._busy_count += 1
        self._refresh_enabled()
        self._append_log(f">>> {title}")

        thread = QtCore.QThread(self)
        job_id = object()
        worker = CommandWorker(job_id, fn)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._finish_worker)
        self._threads.append(thread)
        self._jobs[job_id] = (title, thread, worker, on_success)
        thread.start()

    @QtCore.pyqtSlot(object, object, object)
    def _finish_worker(self, job_id: object, result: Any, error: Optional[BaseException]) -> None:
        job = self._jobs.pop(job_id, None)
        if job is None:
            return
        title, thread, worker, on_success = job
        try:
            if error is not None:
                self._append_log(f"[ERROR] {title}: {error}")
                self._append_log("".join(traceback.format_exception_only(type(error), error)).strip())
                QtWidgets.QMessageBox.critical(self, title, str(error))
            elif on_success is not None:
                on_success(result)
        finally:
            self._busy_count = max(0, self._busy_count - 1)
            self._refresh_enabled()
            thread.quit()
            if thread in self._threads:
                self._threads.remove(thread)
            worker.deleteLater()
            thread.finished.connect(thread.deleteLater)

    def _on_command_success(
        self,
        title: str,
        result: Any,
        *,
        update_controller: bool = False,
        record_position_after: bool = False,
    ) -> None:
        self._append_response(title, result)
        self._update_position_display(result)
        self._update_lift_state_display(result)
        if update_controller and isinstance(result, dict):
            if "connected" in result:
                self.controller_status.setText("控制器：已连接" if result.get("connected") else "控制器：未连接")
            elif result.get("status") == "success":
                self.controller_status.setText("控制器：已连接")
        if isinstance(result, dict) and result.get("status") == "error":
            QtWidgets.QMessageBox.warning(self, title, str(result.get("message") or result.get("error") or "命令失败"))
            return
        if record_position_after:
            if isinstance(result, dict) and "position" in result:
                self._write_position_log(title, result)
            else:
                self._record_current_position(title)

    def _record_current_position(self, source_command: str) -> None:
        if self.client is None:
            return

        def read_position() -> Any:
            return self.client.get_position()

        self._run_worker(
            f"记录位置：{source_command}",
            read_position,
            on_success=lambda result: self._on_position_recorded(source_command, result),
        )

    def _on_position_recorded(self, source_command: str, result: Any) -> None:
        self._update_position_display(result)
        self._write_position_log(source_command, result)

    def _write_position_log(self, source_command: str, position_result: Any) -> None:
        if not isinstance(position_result, dict):
            self._append_log(f"位置记录跳过：{source_command} 未返回位置对象")
            return
        if position_result.get("status") == "error":
            self._append_log(f"位置记录失败：{position_result.get('message') or position_result.get('error')}")
            return

        now = datetime.now()
        record = {
            "timestamp": now.isoformat(timespec="milliseconds"),
            "source_command": source_command,
            "position": position_result.get("position"),
            "relative_position": position_result.get("relative_position"),
            "soft_zero": position_result.get("soft_zero"),
            "raw": position_result,
        }
        try:
            self.position_log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.position_log_dir / f"slide_rail_position_{now:%Y%m%d}.jsonl"
            with log_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._append_log(f"位置已记录：{log_path}")
        except OSError as exc:
            self._append_log(f"位置日志写入失败：{exc}")

    def _update_position_display(self, result: Any) -> None:
        if not isinstance(result, dict):
            return
        if "position" in result:
            self.position_value.setText(self._format_position(result.get("position")))
        if "relative_position" in result:
            self.relative_position_value.setText(self._format_position(result.get("relative_position")))
        if "soft_zero" in result:
            self.soft_zero_value.setText(self._format_position(result.get("soft_zero")))

    def _update_lift_state_display(self, result: Any) -> None:
        if not isinstance(result, dict) or "position_known" not in result:
            return
        if not result.get("position_known"):
            self.lift_counter_value.setText("距最低位：未知（请重新下降到底）")
            return
        seconds = result.get("from_bottom_seconds", 0)
        try:
            seconds_text = f"{float(seconds):.1f} 秒"
        except (TypeError, ValueError):
            seconds_text = "-"
        suffix = "（已在最低位）" if result.get("at_bottom") else "（已知）"
        self.lift_counter_value.setText(f"距最低位：{seconds_text}{suffix}")

    @staticmethod
    def _format_position(value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "-"
        if number.is_integer():
            return f"{int(number)} pulse"
        return f"{number:.3f} pulse"

    def _append_response(self, title: str, result: Any) -> None:
        if isinstance(result, (dict, list)):
            text = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            text = repr(result)
        self._append_log(f"{title} 返回：\n{text}")

    def _append_log(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_edit.appendPlainText(f"[{ts}] {text}")
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())

    def _refresh_enabled(self) -> None:
        connected = self.client is not None
        busy = self._busy_count > 0
        self.busy_label.setText("执行中" if busy else "空闲")
        self.connect_btn.setEnabled(not connected and not busy)
        self.disconnect_btn.setEnabled(connected and not busy)
        self.host_edit.setEnabled(not connected and not busy)
        self.port_spin.setEnabled(not connected and not busy)
        self.mock_check.setEnabled(not connected and not busy)

        for button in self.findChildren(QtWidgets.QPushButton):
            if button in {self.connect_btn, self.disconnect_btn, self.clear_log_btn}:
                continue
            if button.objectName() in {"dangerButton", "warningButton"}:
                button.setEnabled(connected)
            else:
                button.setEnabled(connected and not busy)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QGroupBox {
                font-weight: 600;
                border: 1px solid #c9ced6;
                border-radius: 6px;
                margin-top: 10px;
                padding: 10px 8px 8px 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QPushButton {
                min-height: 28px;
                padding: 4px 10px;
            }
            QPushButton#dangerButton {
                background: #b42318;
                color: white;
                border: 1px solid #8f1d14;
                border-radius: 4px;
            }
            QPushButton#warningButton {
                background: #f59e0b;
                color: #211400;
                border: 1px solid #d97706;
                border-radius: 4px;
            }
            QLabel#secondaryText,
            QLabel#diagnosticPending {
                color: #5f6b7a;
            }
            QLabel#diagnosticPending,
            QLabel#diagnosticSuccess,
            QLabel#diagnosticWarning {
                font-weight: 600;
            }
            QLabel#diagnosticSuccess {
                color: #067647;
            }
            QLabel#diagnosticWarning {
                color: #b54708;
            }
            QPlainTextEdit {
                font-family: Consolas, "Microsoft YaHei UI", monospace;
                font-size: 12px;
            }
            """
        )


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = SlideRailWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
