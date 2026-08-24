"""
循环升降级测试用例
支持三种模式：仅升级、仅降级、升级↔降级循环 N 次
复用现有 StreamHandler / FirmwareHandler
"""

import re
import sys
import queue
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
import sys
from pathlib import Path
from utils import Logger, ScreenshotHelper
from utils.test_reporter import TestReporter
from core.app_manager import AppManager
from core.stream_handler import StreamHandler
from core.firmware_handler import FirmwareHandler

MODE_UPGRADE   = "upgrade"
MODE_DOWNGRADE = "downgrade"
MODE_CYCLE     = "cycle"
MODE_STREAM_ONLY = "stream_only"

MODE_LABEL = {
    MODE_UPGRADE:     "仅升级",
    MODE_DOWNGRADE:   "仅降级",
    MODE_CYCLE:       "升降级循环",
    MODE_STREAM_ONLY: "仅开流",
}


class TestFirmwareCycle:
    """
    循环升降级测试

    Args:
        gui_log_queue: GUI 日志队列，None 时只输出到控制台/文件
        stop_event:    外部停止信号
        on_progress:   进度回调 on_progress(current_round, total_rounds)
        log_dir:       CrealityScan 日志目录（可选，优先于配置文件）
    """

    def __init__(
        self,
        gui_log_queue: Optional[queue.Queue] = None,
        stop_event: Optional[threading.Event] = None,
        on_progress=None,
        log_dir: Optional[str] = None,
        connection_mode: Optional[str] = None,  # "usb" 或 "wifi"
        with_stream: bool = True,  # 是否包含开流验证
    ):
        self._gui_queue   = gui_log_queue
        self._stop_event  = stop_event or threading.Event()
        self._on_progress = on_progress
        self._log_dir = log_dir
        self._connection_mode = connection_mode  # 强制指定连接模式，None则自动检测
        self._with_stream = with_stream  # 是否包含开流验证
        self._was_stopped = False

        # 加载配置
        self.app_config    = self._load_config("app_config.yaml")
        self.device_config = self._load_config("device_config.yaml")
        self.test_config   = self._load_config("test_config.yaml")

        # 初始化 Logger，并把日志同步到 GUI 队列
        log_level = self.test_config["test"]["logging"]["level"]
        self.logger = Logger(level=getattr(logging, log_level))
        if self._gui_queue is not None:
            self._attach_gui_handler()

        self.screenshot       = ScreenshotHelper()
        self.app_manager      = AppManager(self.app_config, self.logger)
        self.stream_handler   = StreamHandler(
            self.app_config, self.logger, self.screenshot, log_dir=self._log_dir
        )
        self.firmware_handler = FirmwareHandler(
            self.app_config, self.device_config, self.logger, self.screenshot,
            log_dir=self._log_dir, connection_mode=self._connection_mode,
        )
        # 使用绝对路径保存报告（兼容打包后运行）
        if getattr(sys, 'frozen', False):
            report_dir = Path(sys.executable).parent / "test_reports"
        else:
            report_dir = Path(__file__).parent.parent / "test_reports"
        self.reporter = TestReporter(report_dir=str(report_dir))

        # 运行时收集的数据
        self._steps_results: dict[str, bool] = {}
        self._screenshots:   dict[str, str]  = {}
        self._frame_data:    dict[str, dict] = {}
        self._before_version: str = "Unknown"
        self._after_version:  str = "Unknown"

    # ── 配置 ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _load_config(path: str) -> dict:
        """加载配置文件，优先从外部目录读取，打包后可直接修改无需重打包"""
        from utils import get_base_dir

        base_dir = get_base_dir()
        config_path = Path(path)

        # 外部配置文件路径（exe同级目录）
        external_config = base_dir / path
        # 打包内部配置文件路径
        if getattr(sys, 'frozen', False):
            internal_config = Path(sys._MEIPASS) / path
        else:
            internal_config = base_dir / path

        # 优先使用外部配置
        if external_config.exists():
            with open(external_config, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)

        # 其次使用内部打包配置
        if internal_config.exists():
            with open(internal_config, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)

        raise FileNotFoundError(f"配置文件未找到: {external_config} 或 {internal_config}")

    def _attach_gui_handler(self):
        """把日志消息投入 GUI 队列"""
        class _QH(logging.Handler):
            def __init__(self, q):
                super().__init__()
                self._q = q
            def emit(self, record):
                self._q.put(self.format(record))

        handler = _QH(self._gui_queue)
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        ))
        self.logger.logger.addHandler(handler)

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def run(
        self,
        mode: str,
        upgrade_path: Optional[str],
        downgrade_path: Optional[str],
        cycle_count: int = 1,
        cycle_start: Optional[str] = None,
        log_dir: Optional[str] = None,
        with_stream: Optional[bool] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        执行测试

        Args:
            cycle_start: 循环模式下的起始方向，可选 "upgrade_first" 或 "downgrade_first"
            with_stream: 是否包含开流验证，默认使用实例级的 _with_stream

        Returns:
            (success, html_report_path)
        """
        self._was_stopped = False
        # 优先使用传入的参数，否则使用实例变量
        use_stream = with_stream if with_stream is not None else self._with_stream
        stream_desc = "含开流" if use_stream else "纯固件"

        start_time = datetime.now()
        self.logger.info("=" * 60)
        self.logger.info(f"测试模式: {MODE_LABEL.get(mode, mode)}  循环次数: {cycle_count}  [{stream_desc}]")
        if mode == MODE_CYCLE and cycle_start:
            direction = "先升级后降级" if cycle_start == "upgrade_first" else "先降级后升级"
            self.logger.info(f"循环方向: {direction}")
        self.logger.info("=" * 60)

        if not self._setup():
            return False, None

        # 收集升级前版本（app 启动后再读日志）
        self._collect_version("before")

        success = False
        try:
            if not use_stream:
                # 纯固件模式（不含开流）
                if mode == MODE_UPGRADE:
                    success = self._run_upgrade_only_no_stream(upgrade_path)
                elif mode == MODE_DOWNGRADE:
                    success = self._run_downgrade_only_no_stream(downgrade_path)
                elif mode == MODE_CYCLE:
                    success = self._run_cycle_no_stream(upgrade_path, downgrade_path, cycle_count, cycle_start)
                else:
                    self.logger.error("仅开流模式不支持纯固件模式")
                    success = False
            else:
                # 含开流模式
                if mode == MODE_UPGRADE:
                    success = self._run_upgrade_only(upgrade_path)
                elif mode == MODE_DOWNGRADE:
                    success = self._run_downgrade_only(downgrade_path)
                elif mode == MODE_STREAM_ONLY:
                    success = self._run_stream_only()
                else:
                    success = self._run_cycle(upgrade_path, downgrade_path, cycle_count, cycle_start)
        except Exception as e:
            self.logger.error(f"测试异常: {e}")
        finally:
            # 收集升级后版本
            self._collect_version("after")
            primary_fw = upgrade_path or downgrade_path or ""
            report_path = self._teardown(
                start_time, mode, cycle_count, success, primary_fw
            )

        return success, report_path

    @property
    def was_stopped(self) -> bool:
        return self._was_stopped

    def _stop_before(self, next_step: str) -> bool:
        if not self._stop_event.is_set():
            return False
        self._was_stopped = True
        self.logger.warning(f"已在安全边界停止，跳过后续步骤：{next_step}")
        return True

    # ── 版本收集 ──────────────────────────────────────────────────────────────

    def _collect_version(self, timing: str):
        try:
            lm = self.firmware_handler.log_manager
            if lm:
                lm.refresh_latest_log_dir()
                ver = lm.get_device_firmware_version() or "Unknown"
            else:
                ver = "Unknown"
        except Exception:
            ver = "Unknown"

        if timing == "before":
            self._before_version = ver
            self.logger.info(f"升级前固件版本: {ver}")
        else:
            self._after_version = ver
            self.logger.info(f"升级后固件版本: {ver}")

    # ── 前置 / 后置 ───────────────────────────────────────────────────────────

    def _setup(self) -> bool:
        if not self.app_manager.connect_windows():
            self.logger.error("Windows 设备连接失败")
            return False
        if not self.app_manager.launch_app():
            self.logger.error("应用启动失败")
            return False
        return True

    def _teardown(
        self,
        start_time: datetime,
        mode: str,
        cycle_count: int,
        success: bool,
        primary_fw: str,
    ) -> Optional[str]:
        end_time = datetime.now()
        try:
            self.reporter.set_test_info(
                firmware_path=primary_fw,
                test_start_time=start_time,
                test_end_time=end_time,
            )
            self._steps_results["overall"] = success
            self.reporter.set_execution_summary(
                overall_result=success,
                steps_results=self._steps_results,
            )
            # 版本对比
            self.reporter.add_comparison_data(
                comparison_type="固件版本",
                before_data={"firmware_version": self._before_version},
                after_data={"firmware_version": self._after_version},
                analysis=self._analyze_version(),
            )
            # 帧率数据
            if self._frame_data:
                self.reporter.add_metrics("帧数性能", self._frame_data)
            # 截图
            for key, path in self._screenshots.items():
                self.reporter.add_screenshot(path, f"{key}截图", key)

            self.reporter.generate_performance_charts()

            report_name = self._build_report_name(
                mode, cycle_count, primary_fw, start_time
            )
            return self.reporter.generate_html_report(report_name=report_name)
        except Exception as e:
            import traceback
            self.logger.error(f"生成报告失败: {e}\n{traceback.format_exc()}")
            return None

    def _analyze_version(self) -> str:
        b, a = self._before_version, self._after_version
        if b == "Unknown" or a == "Unknown":
            return "无法获取完整版本信息，建议检查日志配置"
        if b == a:
            return f"警告：升级前后版本号相同 ({b})，可能升级未成功"
        return f"固件版本成功从 {b} 变更为 {a}"

    def _build_report_name(
        self,
        mode: str,
        cycle_count: int,
        fw_path: str,
        start_time: datetime,
    ) -> str:
        """
        格式：设备名_升级前版本-升级后版本_模式描述_YYYYMMDDHHmm
        例：OtterLiteBasic_1.0.2-1.0.3_升降级循环5次_202603131937
        """
        # 从固件文件名提取设备名
        stem = Path(fw_path).stem if fw_path else ""
        stem = re.sub(r"^Creality_", "", stem)
        stem = re.sub(r"_(?:app\d+_)?\d+\.\d+\.\d+.*$", "", stem)
        device_name = "".join(w.capitalize() for w in stem.split("_")) or "Device"

        mode_desc = MODE_LABEL.get(mode, mode)
        if mode == MODE_CYCLE:
            mode_desc = f"{mode_desc}{cycle_count}次"

        ts = start_time.strftime("%Y%m%d%H%M")
        return (
            f"{device_name}_{self._before_version}-{self._after_version}"
            f"_{mode_desc}_测试报告_{ts}"
        )

    # ── 辅助：记录步骤结果 + 截图 + 帧率 ─────────────────────────────────────

    def _record_stream(self, phase: str, ok: bool, ss: Optional[str], fd: dict):
        self._steps_results[phase] = ok
        if ss:
            self._screenshots[phase] = ss
        if fd:
            self._frame_data[phase] = fd

    def _record_fw(self, phase: str, ok: bool, ss: Optional[str]):
        self._steps_results[phase] = ok
        if ss:
            self._screenshots[phase] = ss

    # ── 三种模式实现 ──────────────────────────────────────────────────────────

    def _run_upgrade_only(self, upgrade_path: str) -> bool:
        self.logger.step("仅升级模式")
        if self._stop_before("升级前开流"):
            return False

        ok, ss, fd = self.stream_handler.start_stream(phase="升级前开流")
        self._record_stream("升级前开流", ok, ss, fd)
        if not ok:
            return False
        if self._stop_before("固件升级"):
            return False

        fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(upgrade_path)
        self._record_fw("固件升级", fw_ok, fw_ss)
        if not fw_ok:
            return False
        if self._stop_before("升级后开流"):
            return False

        ok2, ss2, fd2 = self.stream_handler.start_stream(phase="升级后开流")
        self._record_stream("升级后开流", ok2, ss2, fd2)
        return ok2

    def _run_downgrade_only(self, downgrade_path: str) -> bool:
        self.logger.step("仅降级模式")
        if self._stop_before("降级前开流"):
            return False

        ok, ss, fd = self.stream_handler.start_stream(phase="降级前开流")
        self._record_stream("降级前开流", ok, ss, fd)
        if not ok:
            return False
        if self._stop_before("固件降级"):
            return False

        fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(downgrade_path)
        self._record_fw("固件降级", fw_ok, fw_ss)
        if not fw_ok:
            return False
        if self._stop_before("降级后开流"):
            return False

        ok2, ss2, fd2 = self.stream_handler.start_stream(phase="降级后开流")
        self._record_stream("降级后开流", ok2, ss2, fd2)
        return ok2

    def _run_stream_only(self) -> bool:
        """仅开流模式：一次开流验证，不含固件升级/降级"""
        self.logger.step("仅开流模式")
        if self._stop_before("开流验证"):
            return False

        ok, ss, fd = self.stream_handler.start_stream(phase="开流验证")
        self._record_stream("开流验证", ok, ss, fd)
        return ok

    def _run_upgrade_only_no_stream(self, upgrade_path: str) -> bool:
        """纯固件升级模式（不含开流验证）"""
        self.logger.step("纯固件升级模式")
        if self._stop_before("固件升级"):
            return False
        fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(upgrade_path)
        self._record_fw("固件升级", fw_ok, fw_ss)
        return fw_ok

    def _run_downgrade_only_no_stream(self, downgrade_path: str) -> bool:
        """纯固件降级模式（不含开流验证）"""
        self.logger.step("纯固件降级模式")
        if self._stop_before("固件降级"):
            return False
        fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(downgrade_path)
        self._record_fw("固件降级", fw_ok, fw_ss)
        return fw_ok

    def _run_cycle_no_stream(
        self, upgrade_path: str, downgrade_path: str, total: int, cycle_start: Optional[str] = None
    ) -> bool:
        """纯固件循环模式（不含开流验证）"""
        self.logger.step(f"纯固件循环模式 ({total}次)")

        start_with_upgrade = cycle_start != "downgrade_first"
        direction_str = "先升级后降级" if start_with_upgrade else "先降级后升级"
        self.logger.info(f"循环方向: {direction_str}")

        for i in range(1, total + 1):
            if self._stop_before(f"第 {i} 轮固件操作"):
                return False

            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"第 {i}/{total} 轮开始")
            self.logger.info(f"{'='*60}")

            if start_with_upgrade:
                # 1. 固件升级
                fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(upgrade_path)
                self._record_fw(f"第{i}轮-固件升级", fw_ok, fw_ss)
                if not fw_ok:
                    self.logger.error(f"第 {i} 轮固件升级失败")
                    return False
                if self._stop_before(f"第 {i} 轮固件降级"):
                    return False

                # 2. 固件降级
                fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(downgrade_path)
                self._record_fw(f"第{i}轮-固件降级", fw_ok, fw_ss)
                if not fw_ok:
                    self.logger.error(f"第 {i} 轮固件降级失败")
                    return False
            else:
                # 1. 固件降级
                fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(downgrade_path)
                self._record_fw(f"第{i}轮-固件降级", fw_ok, fw_ss)
                if not fw_ok:
                    self.logger.error(f"第 {i} 轮固件降级失败")
                    return False
                if self._stop_before(f"第 {i} 轮固件升级"):
                    return False

                # 2. 固件升级
                fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(upgrade_path)
                self._record_fw(f"第{i}轮-固件升级", fw_ok, fw_ss)
                if not fw_ok:
                    self.logger.error(f"第 {i} 轮固件升级失败")
                    return False

            self.logger.result(f"第 {i}/{total} 轮完成", success=True)

            if self._on_progress:
                self._on_progress(i, total)

        return True

    def _run_cycle(
        self, upgrade_path: str, downgrade_path: str, total: int, cycle_start: Optional[str] = None
    ) -> bool:
        """
        升级↔降级循环 total 次
        每轮4步（开流→升级→开流→降级），末尾统一执行最终验证开流

        Args:
            cycle_start: 起始方向，"upgrade_first" 先升级后降级，"downgrade_first" 先降级后升级
        """
        # 确定起始方向（默认先升级）
        start_with_upgrade = cycle_start != "downgrade_first"

        for i in range(1, total + 1):
            if self._stop_before(f"第 {i} 轮测试"):
                return False

            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"第 {i}/{total} 轮开始")
            direction_str = "先升级后降级" if start_with_upgrade else "先降级后升级"
            self.logger.info(f"方向: {direction_str}")
            self.logger.info(f"{'='*60}")

            if start_with_upgrade:
                # 1. 升级前开流
                ok, ss, fd = self.stream_handler.start_stream(phase=f"第{i}轮-升级前")
                self._record_stream(f"第{i}轮-升级前开流", ok, ss, fd)
                if not ok:
                    self.logger.error(f"第 {i} 轮升级前开流失败")
                    return False
                if self._stop_before(f"第 {i} 轮固件升级"):
                    return False

                # 2. 固件升级
                fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(upgrade_path)
                self._record_fw(f"第{i}轮-固件升级", fw_ok, fw_ss)
                if not fw_ok:
                    self.logger.error(f"第 {i} 轮固件升级失败")
                    return False
                if self._stop_before(f"第 {i} 轮升级后开流"):
                    return False

                # 3. 升级后开流
                ok, ss, fd = self.stream_handler.start_stream(phase=f"第{i}轮-升级后")
                self._record_stream(f"第{i}轮-升级后开流", ok, ss, fd)
                if not ok:
                    self.logger.error(f"第 {i} 轮升级后开流失败")
                    return False
                if self._stop_before(f"第 {i} 轮固件降级"):
                    return False

                # 4. 固件降级
                fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(downgrade_path)
                self._record_fw(f"第{i}轮-固件降级", fw_ok, fw_ss)
                if not fw_ok:
                    self.logger.error(f"第 {i} 轮固件降级失败")
                    return False
            else:
                # 先降级后升级的流程

                # 1. 降级前开流
                ok, ss, fd = self.stream_handler.start_stream(phase=f"第{i}轮-降级前")
                self._record_stream(f"第{i}轮-降级前开流", ok, ss, fd)
                if not ok:
                    self.logger.error(f"第 {i} 轮降级前开流失败")
                    return False
                if self._stop_before(f"第 {i} 轮固件降级"):
                    return False

                # 2. 固件降级
                fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(downgrade_path)
                self._record_fw(f"第{i}轮-固件降级", fw_ok, fw_ss)
                if not fw_ok:
                    self.logger.error(f"第 {i} 轮固件降级失败")
                    return False
                if self._stop_before(f"第 {i} 轮降级后开流"):
                    return False

                # 3. 降级后开流
                ok, ss, fd = self.stream_handler.start_stream(phase=f"第{i}轮-降级后")
                self._record_stream(f"第{i}轮-降级后开流", ok, ss, fd)
                if not ok:
                    self.logger.error(f"第 {i} 轮降级后开流失败")
                    return False
                if self._stop_before(f"第 {i} 轮固件升级"):
                    return False

                # 4. 固件升级
                fw_ok, fw_ss = self.firmware_handler.upgrade_firmware(upgrade_path)
                self._record_fw(f"第{i}轮-固件升级", fw_ok, fw_ss)
                if not fw_ok:
                    self.logger.error(f"第 {i} 轮固件升级失败")
                    return False

            self.logger.result(f"第 {i}/{total} 轮完成", success=True)

            if self._on_progress:
                self._on_progress(i, total)

        if self._stop_before("最终验证开流"):
            return False

        # 所有轮次结束后，统一执行最终验证开流
        self.logger.info(f"\n{'='*60}")
        self.logger.info("执行最终验证开流")
        self.logger.info(f"{'='*60}")

        ok, ss, fd = self.stream_handler.start_stream(phase="最终验证开流")
        self._record_stream("最终验证开流", ok, ss, fd)

        return ok
