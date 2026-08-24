"""
日志文件管理器
负责自动检测最新的日志目录，并提供统一的日志读取接口
"""
import os
import re
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from datetime import datetime


class LogManager:
    """日志文件管理器，用于处理CrealityScan的日志文件"""

    def __init__(self, log_base_dir: str):
        """
        初始化日志管理器

        Args:
            log_base_dir: 日志根目录，例如 C:\\Users\\zengx\\AppData\\Local\\Creality\\CrealityScan\\Logs
        """
        self.log_base_dir = Path(log_base_dir)
        self.current_log_dir: Optional[Path] = None
        self.app_log_path: Optional[Path] = None
        self.scan_log_path: Optional[Path] = None
        self._app_log_size: int = 0  # 记录app.log文件大小，用于增量读取

    def refresh_latest_log_dir(self) -> bool:
        """
        刷新并定位到最新的日志目录

        Returns:
            bool: 是否成功找到日志目录
        """
        if not self.log_base_dir.exists():
            print(f"[LogManager] 日志根目录不存在: {self.log_base_dir}")
            return False

        # 获取所有时间戳格式的子目录 (格式: YYYYMMDDHHMMSS)
        timestamp_dirs = []
        for item in self.log_base_dir.iterdir():
            if item.is_dir() and re.match(r'^\d{14}$', item.name):
                timestamp_dirs.append(item)

        if not timestamp_dirs:
            print(f"[LogManager] 未找到任何日志目录")
            return False

        # 按时间戳排序，获取最新的目录
        latest_dir = max(timestamp_dirs, key=lambda d: d.name)
        self.current_log_dir = latest_dir

        # 定位app.log文件
        app_log = latest_dir / "app.log"
        if app_log.exists():
            self.app_log_path = app_log
        else:
            print(f"[LogManager] 警告: 未找到app.log文件在 {latest_dir}")

        # 定位scan_log文件 (格式: scan_log_*.txt)
        scan_logs = list(latest_dir.glob("scan_log_*.txt"))
        if scan_logs:
            # 如果有多个，取最新的
            self.scan_log_path = max(scan_logs, key=lambda f: f.stat().st_mtime)
        else:
            print(f"[LogManager] 警告: 未找到scan_log文件在 {latest_dir}")

        print(f"[LogManager] 已定位到最新日志目录: {latest_dir.name}")

        # 记录当前日志文件大小
        self._app_log_size = self._get_app_log_size()
        return True

    def _get_app_log_size(self) -> int:
        """获取当前app.log文件大小"""
        if self.app_log_path and self.app_log_path.exists():
            return self.app_log_path.stat().st_size
        return 0

    def get_current_log_size(self) -> int:
        """获取当前app.log文件大小（外部调用）"""
        return self._get_app_log_size()

    def read_new_app_log(self, encoding: str = 'utf-8') -> str:
        """
        读取app.log新增的内容（从上次记录的位置开始）

        Returns:
            str: 新增的日志内容
        """
        if not self.app_log_path or not self.app_log_path.exists():
            return ""

        try:
            current_size = self.app_log_path.stat().st_size
            if current_size <= self._app_log_size:
                # 文件没有新增内容
                return ""

            # 只读取新增部分
            with open(self.app_log_path, 'r', encoding=encoding, errors='ignore') as f:
                f.seek(self._app_log_size)
                new_content = f.read()

            # 更新记录的位置
            self._app_log_size = current_size
            return new_content
        except Exception as e:
            print(f"[LogManager] 读取新增日志失败: {e}")
            return ""

    def reset_log_position(self):
        """重置日志位置记录（用于开始新的检测时）"""
        self._app_log_size = self._get_app_log_size()

    def read_log_since_time(self, start_time: str, encoding: str = 'utf-8') -> str:
        """
        读取指定时间之后的日志内容

        Args:
            start_time: 起始时间，格式如 "2026-04-11 16:29:08"

        Returns:
            str: 指定时间之后的日志内容
        """
        if not self.app_log_path or not self.app_log_path.exists():
            return ""

        try:
            # 解析起始时间
            from datetime import datetime
            start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')

            # 读取完整日志
            with open(self.app_log_path, 'r', encoding=encoding, errors='ignore') as f:
                full_content = f.read()

            # 按行分割，找到起始时间之后的日志
            lines = full_content.split('\n')
            result_lines = []

            for line in lines:
                # 提取日志行的时间戳（格式: [2026-04-11 15:42:33.770186]）
                if '[' in line:
                    try:
                        time_str = line.split('[')[1].split(']')[0]
                        # 只保留到秒（去除毫秒）
                        time_str_sec = time_str.split('.')[0]
                        line_dt = datetime.strptime(time_str_sec, '%Y-%m-%d %H:%M:%S')

                        if line_dt >= start_dt:
                            result_lines.append(line)
                    except (ValueError, IndexError):
                        # 如果解析失败，保守起见保留这行
                        result_lines.append(line)

            return '\n'.join(result_lines)
        except Exception as e:
            print(f"[LogManager] 按时间读取日志失败: {e}")
            return ""

    def read_app_log(self, encoding: str = 'utf-8') -> str:
        """
        读取app.log文件内容

        Args:
            encoding: 文件编码

        Returns:
            str: 日志内容
        """
        if not self.app_log_path or not self.app_log_path.exists():
            return ""

        try:
            with open(self.app_log_path, 'r', encoding=encoding, errors='ignore') as f:
                return f.read()
        except Exception as e:
            print(f"[LogManager] 读取app.log失败: {e}")
            return ""

    def read_scan_log(self, encoding: str = 'utf-8') -> str:
        """
        读取scan_log文件内容

        Args:
            encoding: 文件编码

        Returns:
            str: 日志内容
        """
        if not self.scan_log_path or not self.scan_log_path.exists():
            return ""

        try:
            with open(self.scan_log_path, 'r', encoding=encoding, errors='ignore') as f:
                return f.read()
        except Exception as e:
            print(f"[LogManager] 读取scan_log失败: {e}")
            return ""

    def tail_app_log(self, lines: int = 100, encoding: str = 'utf-8') -> List[str]:
        """
        读取app.log的最后N行

        Args:
            lines: 读取的行数
            encoding: 文件编码

        Returns:
            List[str]: 日志行列表
        """
        content = self.read_app_log(encoding)
        if not content:
            return []

        all_lines = content.splitlines()
        return all_lines[-lines:]

    def tail_scan_log(self, lines: int = 100, encoding: str = 'utf-8') -> List[str]:
        """
        读取scan_log的最后N行

        Args:
            lines: 读取的行数
            encoding: 文件编码

        Returns:
            List[str]: 日志行列表
        """
        content = self.read_scan_log(encoding)
        if not content:
            return []

        all_lines = content.splitlines()
        return all_lines[-lines:]

    def search_in_app_log(self, pattern: str, use_regex: bool = False) -> List[Tuple[int, str]]:
        """
        在app.log中搜索指定模式

        Args:
            pattern: 搜索模式（字符串或正则表达式）
            use_regex: 是否使用正则表达式

        Returns:
            List[Tuple[int, str]]: 匹配的行号和内容列表
        """
        content = self.read_app_log()
        if not content:
            return []

        results = []
        for line_num, line in enumerate(content.splitlines(), 1):
            if use_regex:
                if re.search(pattern, line):
                    results.append((line_num, line))
            else:
                if pattern in line:
                    results.append((line_num, line))

        return results

    def search_in_scan_log(self, pattern: str, use_regex: bool = False) -> List[Tuple[int, str]]:
        """
        在scan_log中搜索指定模式

        Args:
            pattern: 搜索模式（字符串或正则表达式）
            use_regex: 是否使用正则表达式

        Returns:
            List[Tuple[int, str]]: 匹配的行号和内容列表
        """
        content = self.read_scan_log()
        if not content:
            return []

        results = []
        for line_num, line in enumerate(content.splitlines(), 1):
            if use_regex:
                if re.search(pattern, line):
                    results.append((line_num, line))
            else:
                if pattern in line:
                    results.append((line_num, line))

        return results

    def get_fps_series(self) -> Dict[str, List[Tuple[float, float]]]:
        """
        从scan_log中解析预览和扫描阶段的帧率序列

        日志格式:
          - obscan_scan_preview  → 预览开始
          - obscan_scan_start    → 扫描开始
          - frame N + 时间戳     → 每帧记录

        Returns:
            dict: {
                'preview': [(相对秒, fps), ...],
                'scan':    [(相对秒, fps), ...]
            }
        """
        content = self.read_scan_log()
        if not content:
            return {'preview': [], 'scan': []}

        # 解析每行：时间戳 + frame N（支持ANSI颜色代码）
        # 例如: [1;33mframe 0[0m 或 frame 1
        line_pattern = re.compile(
            r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*?(?:\x1b\[[0-9;]*m)?frame\s+(\d+)(?:\x1b\[0m)?'
        )
        # 定位阶段分界线时间戳
        preview_start_ts = None
        scan_start_ts = None

        ts_fmt = '%Y-%m-%d %H:%M:%S.%f'

        for line in content.splitlines():
            if 'obscan_scan_preview' in line:
                m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]', line)
                if m:
                    preview_start_ts = datetime.strptime(m.group(1), ts_fmt)
            elif 'obscan_scan_start' in line:
                m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]', line)
                if m:
                    scan_start_ts = datetime.strptime(m.group(1), ts_fmt)

        if not preview_start_ts:
            return {'preview': [], 'scan': []}

        # 收集各阶段帧时间戳列表
        preview_timestamps = []  # frame 0 阶段
        scan_timestamps = []     # frame N>0 阶段

        for line in content.splitlines():
            m = line_pattern.search(line)
            if not m:
                continue
            ts = datetime.strptime(m.group(1), ts_fmt)
            frame_num = int(m.group(2))

            if scan_start_ts and ts >= scan_start_ts:
                scan_timestamps.append((ts, frame_num))
            elif ts >= preview_start_ts:
                preview_timestamps.append((ts, frame_num))

        def _to_fps_series(timestamps):
            """将时间戳列表按秒分桶，计算每秒帧数增量"""
            if not timestamps:
                return []
            base_ts = timestamps[0][0]
            # 按秒分桶：记录每秒内最大帧号与最小帧号之差
            buckets: Dict[int, Tuple[int, int]] = {}  # second -> (min_frame, max_frame)
            for ts, frame_num in timestamps:
                sec = int((ts - base_ts).total_seconds())
                if sec not in buckets:
                    buckets[sec] = (frame_num, frame_num)
                else:
                    buckets[sec] = (min(buckets[sec][0], frame_num),
                                    max(buckets[sec][1], frame_num))
            result = []
            for sec in sorted(buckets):
                fps = buckets[sec][1] - buckets[sec][0]
                result.append((float(sec), float(fps)))
            return result

        return {
            'preview': _to_fps_series(preview_timestamps),
            'scan': _to_fps_series(scan_timestamps)
        }

    def get_latest_frame_count(self) -> Optional[int]:
        """
        从scan_log中获取最新的帧数

        Returns:
            Optional[int]: 最新帧数，如果未找到则返回None
        """
        content = self.read_scan_log()
        if not content:
            return None

        # 查找所有帧数记录 (格式: frame 100)
        pattern = r'frame\s+(\d+)'
        matches = re.findall(pattern, content)

        if matches:
            # 返回最后一个匹配的帧数
            return int(matches[-1])

        return None

    def has_color_camera(self) -> bool:
        """
        检测是否存在彩色相机

        Returns:
            bool: 是否存在彩色相机
        """
        content = self.read_scan_log()
        if not content:
            return False

        # 搜索彩色相机相关的关键字
        color_keywords = ["color camera", "ColorCamera", "RGB camera"]
        for keyword in color_keywords:
            if keyword.lower() in content.lower():
                return True

        return False

    def get_current_scan_status(self) -> Optional[str]:
        """
        从app.log中获取当前扫描状态

        Returns:
            Optional[str]: 当前扫描状态，如果未找到则返回None
        """
        # 搜索扫描状态变化记录 (格式: [ScanStatus] ScanStatus Changed: Previewing -> Scanning)
        matches = self.search_in_app_log(r'\[ScanStatus\] ScanStatus Changed:.*->.*', use_regex=True)

        if matches:
            # 获取最后一条状态变化记录
            last_match = matches[-1][1]
            # 提取状态 (格式: "... -> Scanning")
            status_match = re.search(r'->\s*(\w+)', last_match)
            if status_match:
                return status_match.group(1)

        return None

    def is_device_connected(self) -> bool:
        """
        检查设备是否已连接

        Returns:
            bool: 设备是否已连接
        """
        # 搜索最近的设备连接/断开记录
        connect_keywords = ["OnDeviceConnect", "Device connected"]
        disconnect_keywords = ["Device disconnected", "OnDeviceDisconnect"]

        content = self.read_app_log()
        if not content:
            return False

        lines = content.splitlines()

        # 从后往前查找最近的连接/断开事件
        for line in reversed(lines):
            for keyword in connect_keywords:
                if keyword in line:
                    return True
            for keyword in disconnect_keywords:
                if keyword in line:
                    return False

        return False

    def get_device_firmware_version(self) -> Optional[str]:
        """
        从app.log中获取当前设备固件版本号

        Returns:
            Optional[str]: 固件版本号（如 "1.4.3"），未找到则返回None
        """
        content = self.read_app_log()
        if not content:
            return None

        # 主要格式: Cur Device Version Info: [SCANNER_RAPTOR]:1.4.3
        matches = re.findall(r'Cur Device Version Info:.*?:(\d+\.\d+\.\d+)', content)
        if matches:
            return matches[-1]

        # 备选格式: scannerFwVersion:1.4.3
        matches = re.findall(r'scannerFwVersion:(\d+\.\d+\.\d+)', content)
        if matches:
            return matches[-1]

        return None

    def get_firmware_version_after_upgrade(self, upgrade_time: str = None) -> Optional[str]:
        """
        从app.log中获取升级后的设备固件版本号

        如果指定了升级成功时间点，则只读取该时间点之后的版本信息

        Args:
            upgrade_time: 升级成功的时间点 (格式: "YYYY-MM-DD HH:MM:SS")

        Returns:
            Optional[str]: 固件版本号（如 "1.4.3"），未找到则返回None
        """
        content = self.read_app_log()
        if not content:
            return None

        lines = content.splitlines()

        # 如果指定了升级时间，只读取该时间点之后的行
        if upgrade_time:
            try:
                from datetime import datetime
                upgrade_dt = datetime.strptime(upgrade_time, '%Y-%m-%d %H:%M:%S')

                # 从后往前查找升级时间点之后的版本记录
                for line in reversed(lines):
                    # 检查该行是否在升级时间之后
                    time_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if time_match:
                        line_dt = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
                        if line_dt >= upgrade_dt:
                            # 优先查找 scannerFwVersion 格式（记录更完整的版本变化）
                            version_match = re.search(r'scannerFwVersion:(\d+\.\d+\.\d+)', line)
                            if version_match and version_match.group(1) != 'NA':
                                return version_match.group(1)
                            # 备选：查找 Cur Device Version Info 格式
                            version_match = re.search(r'Cur Device Version Info:.*?:(\d+\.\d+\.\d+)', line)
                            if version_match:
                                return version_match.group(1)
            except Exception:
                pass

        # 如果没有指定升级时间或解析失败，从后往前查找最后一个有效的版本号
        for line in reversed(lines):
            version_match = re.search(r'scannerFwVersion:(\d+\.\d+\.\d+)', line)
            if version_match and version_match.group(1) != 'NA':
                return version_match.group(1)
            version_match = re.search(r'Cur Device Version Info:.*?:(\d+\.\d+\.\d+)', line)
            if version_match:
                return version_match.group(1)

        return None

    def get_device_model(self) -> Optional[str]:
        """
        从 app.log 获取当前连接的设备型号

        日志格式示例:
        - scannerPid:SCANNER_SERMOON_S1
        - scannerPid:SCANNER_SERMOON_X1
        - scannerPid:SCANNER_OTTER_LITE_BASIC

        Returns:
            str: 设备型号 (如 "SCANNER_SERMOON_S1")，未找到返回 None
        """
        content = self.read_app_log()
        if not content:
            return None

        # 匹配 scannerPid:XXX 格式
        matches = re.findall(r'scannerPid:([A-Za-z_0-9]+)', content)
        if matches:
            # 返回最后一个匹配的设备型号（最新的设备连接信息）
            return matches[-1]

        return None

    def get_log_dir_info(self) -> dict:
        """
        获取当前日志目录信息

        Returns:
            dict: 日志目录信息
        """
        return {
            "log_base_dir": str(self.log_base_dir),
            "current_log_dir": str(self.current_log_dir) if self.current_log_dir else None,
            "app_log_path": str(self.app_log_path) if self.app_log_path else None,
            "scan_log_path": str(self.scan_log_path) if self.scan_log_path else None,
        }

    def is_x1wifi_connected(self) -> bool:
        """
        检测X1 WiFi设备是否已连接（X1模组+wifiBridge同时在线）

        日志特征:
        - scannerPid:SCANNER_SERMOON_X1
        - wifiBridgePid:SCAN_BRIDGE

        Returns:
            bool: X1 WiFi设备是否已连接
        """
        return self.is_wifi_device_connected('SERMOON_X1')

    def is_s1wifi_connected(self) -> bool:
        """
        检测S1 WiFi设备是否已连接（S1模组+wifiBridge同时在线）

        日志特征:
        - scannerPid:SCANNER_SERMOON_S1
        - wifiBridgePid:SCAN_BRIDGE

        Returns:
            bool: S1 WiFi设备是否已连接
        """
        return self.is_wifi_device_connected('SERMOON_S1')

    def is_raptorwifi_connected(self) -> bool:
        """
        检测Raptor系列WiFi设备是否已连接（Raptor模组+wifiBridge同时在线）

        日志特征:
        - scannerPid:SCANNER_RAPTOR* (RAPTOR, RAPTORPRO, RAPTORX)
        - wifiBridgePid:SCAN_BRIDGE

        Returns:
            bool: Raptor WiFi设备是否已连接
        """
        content = self.read_app_log()
        if not content:
            return False

        # Raptor WiFi特征：scannerPid包含RAPTOR（不区分大小写）且存在wifiBridgePid
        content_upper = content.upper()
        has_raptor = 'SCANNERPID:SCANNER_RAPTOR' in content_upper
        has_wifi_bridge = 'WIFIBRIDGEPID:' in content_upper

        return has_raptor and has_wifi_bridge

    def is_otterwifi_connected(self) -> bool:
        """
        检测Otter系列WiFi设备是否已连接（Otter模组+wifiBridge同时在线）

        日志特征:
        - scannerPid:SCANNER_OTTER
        - wifiBridgePid:SCAN_BRIDGE

        Returns:
            bool: Otter WiFi设备是否已连接
        """
        content = self.read_app_log()
        if not content:
            return False

        # Otter WiFi特征：scannerPid包含OTTER（不区分大小写）且存在wifiBridgePid
        content_upper = content.upper()
        has_otter = 'SCANNERPID:SCANNER_OTTER' in content_upper
        has_wifi_bridge = 'WIFIBRIDGEPID:' in content_upper

        return has_otter and has_wifi_bridge

    def is_ferretwifi_connected(self) -> bool:
        """
        检测Ferret系列WiFi设备是否已连接（Ferret模组+wifiBridge同时在线）

        日志特征:
        - scannerPid:SCANNER_FERRET
        - wifiBridgePid:WIFI_BRIDGE

        Returns:
            bool: Ferret WiFi设备是否已连接
        """
        content = self.read_app_log()
        if not content:
            return False

        # Ferret WiFi特征：scannerPid包含FERRET（不区分大小写）且存在WIFI_BRIDGE
        content_upper = content.upper()
        has_ferret = 'SCANNERPID:SCANNER_FERRET' in content_upper
        has_wifi_bridge = 'WIFI_BRIDGE' in content_upper  # Ferret使用WIFI_BRIDGE

        return has_ferret and has_wifi_bridge

    def is_pikawifi_connected(self) -> bool:
        """
        检测Creality Pika系列WiFi设备是否已连接（Pika模组+wifiBridge同时在线）

        日志特征:
        - scannerPid:SCANNER_RAPTOR_PIKA
        - wifiBridgePid:SCAN_BRIDGE

        Returns:
            bool: Pika WiFi设备是否已连接
        """
        content = self.read_app_log()
        if not content:
            return False

        # Pika WiFi特征：scannerPid包含RAPTOR_PIKA（不区分大小写）且存在wifiBridgePid
        content_upper = content.upper()
        has_pika = 'SCANNERPID:SCANNER_RAPTOR_PIKA' in content_upper
        has_wifi_bridge = 'WIFIBRIDGEPID:' in content_upper

        return has_pika and has_wifi_bridge

    def is_wifi_device_connected(self, device_pattern: str) -> bool:
        """
        检测指定WiFi设备是否已连接（指定模组+wifiBridge同时在线）

        日志特征:
        - scannerPid:SCANNER_XXX（如SCANNER_SERMOON_X1）
        - wifiBridgePid:存在（WiFi手柄保持连接）

        Args:
            device_pattern: 设备型号匹配模式（如 'SERMOON_X1', 'SERMOON_S1', 'OTTER'）

        Returns:
            bool: 指定WiFi设备是否已连接
        """
        content = self.read_app_log()
        if not content:
            return False

        # WiFi设备特征：scannerPid匹配指定型号 且 存在wifiBridgePid
        # 注意：需要同时将内容和搜索模式都转成大写进行匹配
        content_upper = content.upper()
        search_pattern = f'SCANNERPID:SCANNER_{device_pattern.upper()}'
        has_device = search_pattern in content_upper
        has_wifi_bridge = 'WIFIBRIDGEPID:' in content_upper

        return has_device and has_wifi_bridge

    def is_blue_line_laser_module(self) -> bool:
        """
        判断是否为蓝色线激光模组（Sermoon/Raptor/Pika）

        通过设备型号判断，蓝色线激光模组需要开双流（蓝色线激光+红外）
        散斑模组（Otter/Ferret）只需开单流（红外）

        Returns:
            bool: 是否为蓝色线激光模组
        """
        model = self.get_device_model()
        if not model:
            return False
        m = model.upper()
        return any(kw in m for kw in ['SERMOON', 'RAPTOR', 'PIKA'])

    def get_device_connection_info(self) -> dict:
        """
        获取设备连接详细信息

        Returns:
            dict: 设备连接信息，包含:
                - scanner_pid: scannerPid值
                - wifi_bridge_pid: wifiBridgePid值
                - is_wifi_mode: 是否为WiFi模式
                - device_type: 设备类型（如果可识别）
        """
        content = self.read_app_log()
        if not content:
            return {
                'scanner_pid': None,
                'wifi_bridge_pid': None,
                'is_wifi_mode': False,
                'device_type': None
            }

        # 提取scannerPid - 找到最后一个（最新的）scannerPid记录
        # 因为升级过程中会先断开(X1->UNKNOWN)，然后重连(X1->SCANNER_SERMOON_X1)
        # 需要获取最后出现的值来判断是否已重连
        scanner_matches = re.findall(r'scannerPid:([A-Za-z_0-9]+)', content)
        scanner_pid = scanner_matches[-1] if scanner_matches else None

        # 提取wifiBridgePid - 同样取最后一个
        wifi_bridge_matches = re.findall(r'wifiBridgePid:([A-Za-z_0-9]+)', content)
        wifi_bridge_pid = wifi_bridge_matches[-1] if wifi_bridge_matches else None

        # 判断是否为WiFi模式
        is_wifi_mode = wifi_bridge_pid is not None

        # 识别设备类型
        device_type = None
        if scanner_pid:
            if 'SERMOON_X1' in scanner_pid.upper():
                device_type = 'Sermoon X1'
            elif 'SERMOON_S1' in scanner_pid.upper():
                device_type = 'Sermoon S1'
            elif 'RAPTORPRO' in scanner_pid.upper():
                device_type = 'Raptor Pro'
            elif 'RAPTORX' in scanner_pid.upper():
                device_type = 'Raptor X'
            elif 'RAPTOR' in scanner_pid.upper():
                device_type = 'Raptor'
            elif 'OTTER' in scanner_pid.upper():
                device_type = scanner_pid.replace('SCANNER_', '')

        return {
            'scanner_pid': scanner_pid,
            'wifi_bridge_pid': wifi_bridge_pid,
            'is_wifi_mode': is_wifi_mode,
            'device_type': device_type
        }
