import re
import sys
from pathlib import Path
from datetime import datetime


def get_logs_dir() -> Path:
    """根据系统平台获取日志目录"""
    home = Path.home()
    if sys.platform == "darwin":
        # macOS
        return home / "Library" / "CrealityScan" / "Logs"
    else:
        # Windows
        return home / "AppData" / "Local" / "Creality" / "CrealityScan" / "Logs"


def get_latest_log_file() -> Path | None:
    """
    获取最新的日志文件路径
    """
    logs_dir = get_logs_dir()

    if not logs_dir.exists():
        return None

    # 获取所有日期文件夹，按修改时间排序
    folders = [f for f in logs_dir.iterdir() if f.is_dir()]
    if not folders:
        return None

    # 按修改时间获取最新的文件夹
    latest_folder = max(folders, key=lambda f: f.stat().st_mtime)

    # 在最新文件夹中获取所有 scan_log_*.txt 文件
    log_files = list(latest_folder.glob("scan_log_*.txt"))
    if not log_files:
        return None

    # 按修改时间排序，取最新的文件
    latest_file = max(log_files, key=lambda f: f.stat().st_mtime)
    return latest_file


def parse_log_file(file_path: Path) -> dict:
    """
    解析日志文件，返回包含设备信息的字典
    """
    result = {
        "device_name": "N/A",
        "sn_code": "N/A",
        "calibration_board": "N/A",
        "calibration_score": "N/A",
        "firmware_version": "N/A",
        "log_file": file_path.name if file_path else "N/A",
        "refresh_time": datetime.now().strftime("%H:%M:%S")
    }

    if not file_path or not file_path.exists():
        return result

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding="gbk")
        except Exception:
            return result

    # 正则匹配规则
    patterns = {
        "device_name": re.compile(r"camera name:\s*(.+)", re.IGNORECASE),
        "sn_code": re.compile(r"camera serial number:\s*(.+)", re.IGNORECASE),
        "calibration_board": re.compile(r"(?:Scan|Input) QRCode SN\s*:\s*(.+)", re.IGNORECASE),
        "score_normal": re.compile(r"Calib calib score\s*:\s*([\d.]+)", re.IGNORECASE),
        "score_raptor": re.compile(r"\[parallel\]\s*score:\s*([\d.]+)", re.IGNORECASE),
        "score_ferret": re.compile(r"Close Calib score:\s*([\d.]+)", re.IGNORECASE),
        "firmware_version": re.compile(r"camera firmware version:\s*(.+)", re.IGNORECASE),
    }

    # 逐行解析，只保留最后一次匹配的结果
    for line in content.splitlines():
        # 设备名称
        match = patterns["device_name"].search(line)
        if match:
            result["device_name"] = match.group(1).strip()

        # SN码
        match = patterns["sn_code"].search(line)
        if match:
            result["sn_code"] = match.group(1).strip()

        # 标定板编号
        match = patterns["calibration_board"].search(line)
        if match:
            result["calibration_board"] = match.group(1).strip()

        # 标定分数（两种格式都可能存在，以后出现的为准）
        match = patterns["score_normal"].search(line)
        if match:
            score = float(match.group(1))
            result["calibration_score"] = f"{score:.2f}"
            result["score_source"] = "normal"

        match = patterns["score_raptor"].search(line)
        if match:
            score = float(match.group(1))
            result["calibration_score"] = f"{score:.2f}"
            result["score_source"] = "raptor"

        match = patterns["score_ferret"].search(line)
        if match:
            score = float(match.group(1))
            result["calibration_score"] = f"{score:.2f}"
            result["score_source"] = "ferret"

        # 固件版本
        match = patterns["firmware_version"].search(line)
        if match:
            result["firmware_version"] = match.group(1).strip()

    return result