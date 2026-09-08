"""读取标定分数 Step。

沉淀自 工具/标定分数查看工具/parser.py（标定分数查看工具），自包含实现：
不依赖外部工具目录，可在平台内独立调用。逻辑与源工具保持一致：
- 定位最新日志目录（macOS / Windows）
- 在最新日期目录下取最新的 scan_log_*.txt
- 逐行解析设备名、SN、标定板、标定分数（normal/raptor/ferret 三种格式）与固件版本
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _default_logs_dir() -> Path:
    """根据系统平台获取 CrealityScan 日志根目录（与源工具 parser.get_logs_dir 一致）。"""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "CrealityScan" / "Logs"
    return home / "AppData" / "Local" / "Creality" / "CrealityScan" / "Logs"


def _latest_log_file(logs_root: Path) -> Optional[Path]:
    """获取最新日志文件：最新修改日期的子目录下，取最新修改的 scan_log_*.txt。"""
    if not logs_root.exists():
        return None
    try:
        folders = [f for f in logs_root.iterdir() if f.is_dir()]
    except OSError:
        return None
    if not folders:
        return None
    latest_folder = max(folders, key=lambda f: f.stat().st_mtime)
    try:
        log_files = list(latest_folder.glob("scan_log_*.txt"))
    except OSError:
        return None
    if not log_files:
        return None
    return max(log_files, key=lambda f: f.stat().st_mtime)


def _parse_log_file(file_path: Optional[Path]) -> Dict[str, Any]:
    """解析日志文件，返回包含设备信息与标定分数的字典（与源工具 parser.parse_log_file 一致）。"""
    result = {
        "device_name": "N/A",
        "sn_code": "N/A",
        "calibration_board": "N/A",
        "calibration_score": "N/A",
        "firmware_version": "N/A",
        "log_file": file_path.name if file_path else "N/A",
        "refresh_time": datetime.now().strftime("%H:%M:%S"),
        "score_source": "",
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
    except OSError:
        return result

    patterns = {
        "device_name": re.compile(r"camera name:\s*(.+)", re.IGNORECASE),
        "sn_code": re.compile(r"camera serial number:\s*(.+)", re.IGNORECASE),
        "calibration_board": re.compile(r"(?:Scan|Input) QRCode SN\s*:\s*(.+)", re.IGNORECASE),
        "score_normal": re.compile(r"Calib calib score\s*:\s*([\d.]+)", re.IGNORECASE),
        "score_raptor": re.compile(r"\[parallel\]\s*score:\s*([\d.]+)", re.IGNORECASE),
        "score_ferret": re.compile(r"Close Calib score:\s*([\d.]+)", re.IGNORECASE),
        "firmware_version": re.compile(r"camera firmware version:\s*(.+)", re.IGNORECASE),
    }

    for line in content.splitlines():
        match = patterns["device_name"].search(line)
        if match:
            result["device_name"] = match.group(1).strip()

        match = patterns["sn_code"].search(line)
        if match:
            result["sn_code"] = match.group(1).strip()

        match = patterns["calibration_board"].search(line)
        if match:
            result["calibration_board"] = match.group(1).strip()

        # 标定分数（三种格式都可能存在，以后出现的为准）
        match = patterns["score_normal"].search(line)
        if match:
            result["calibration_score"] = f"{float(match.group(1)):.2f}"
            result["score_source"] = "normal"

        match = patterns["score_raptor"].search(line)
        if match:
            result["calibration_score"] = f"{float(match.group(1)):.2f}"
            result["score_source"] = "raptor"

        match = patterns["score_ferret"].search(line)
        if match:
            result["calibration_score"] = f"{float(match.group(1)):.2f}"
            result["score_source"] = "ferret"

        match = patterns["firmware_version"].search(line)
        if match:
            result["firmware_version"] = match.group(1).strip()

    return result


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """读取最新 CrealityScan 日志并解析标定分数。

    日志目录优先级：params.log_dir > 用例 case.app.log_dir > 当前用户默认日志目录。
    """
    case = ctx.get("case") if isinstance(ctx.get("case"), dict) else {}
    app = case.get("app") if isinstance(case.get("app"), dict) else {}

    log_dir = str(params.get("log_dir") or "").strip()
    if not log_dir:
        log_dir = str(app.get("log_dir") or "").strip()
    logs_root = Path(log_dir).expanduser() if log_dir else _default_logs_dir()

    log_file = _latest_log_file(logs_root)
    data = _parse_log_file(log_file)
    data["log_dir"] = str(logs_root)

    score = str(data.get("calibration_score") or "N/A")
    has_score = score not in {"", "N/A"}
    print(
        f"[JENS][calibration_score] log_dir={logs_root} "
        f"log_file={data.get('log_file')} score={score} device={data.get('device_name')}"
    )
    data["has_score"] = has_score
    return data
