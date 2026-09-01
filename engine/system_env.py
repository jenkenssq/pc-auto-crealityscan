from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, Optional

# Windows 版本名自动补全（Q4：自动补全“专业版/版本名”）。
_OS_EDITION_MAP = {
    "windows 11": "Windows 11 专业版",
    "windows 10": "Windows 10 专业版",
}
# build 号 → 版本名（Win11 营销版本）。未收录的 build 只给“专业版”，版本名留空。
_BUILD_TO_VERSION_NAME = {
    "22000": "21H2",
    "22621": "22H2",
    "22631": "23H2",
    "22635": "23H2",
    "26100": "24H2",
}


def _first_match(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def parse_system_info_text(text: str) -> Dict[str, object]:
    """
    解析 system_info.txt，返回：
      cpu / cpu_cores / memory_mb / gpu / gpu_memory / os_raw /
      os_name(自动补全专业版) / os_version_name / os_build
    """
    info: Dict[str, object] = {
        "cpu": "",
        "cpu_cores": "",
        "memory_mb": "",
        "gpu": "",
        "gpu_memory": "",
        "os_raw": "",
        "os_name": "",
        "os_version_name": "",
        "os_build": "",
    }
    os_pattern = re.compile(r"^OS:\s*(.+?)\s*$", re.IGNORECASE)
    os_build_pattern = re.compile(r"10\.0\.(\d+)(?:\.(\d+))?", re.IGNORECASE)
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("CPU:") and not info["cpu"]:
            info["cpu"] = line.split(":", 1)[1].strip()
        elif line.startswith("CPU Cores:") and not info["cpu_cores"]:
            info["cpu_cores"] = line.split(":", 1)[1].strip()
        elif line.startswith("Memory:") and not info["memory_mb"]:
            value = line.split(":", 1)[1].strip()
            match = re.search(r"(\d+)", value)
            info["memory_mb"] = int(match.group(1)) if match else 0
        elif line.startswith("GPU:") and not info["gpu"]:
            info["gpu"] = line.split(":", 1)[1].strip()
        elif line.startswith("GPU Memory:") and not info["gpu_memory"]:
            info["gpu_memory"] = line.split(":", 1)[1].strip()
        elif os_pattern.match(line) and not info["os_raw"]:
            info["os_raw"] = line.split(":", 1)[1].strip()
    info["os_build"] = _first_match(os_build_pattern, str(info["os_raw"])) if info["os_raw"] else ""
    info["os_name"] = _compose_os_name(str(info["os_raw"]))
    info["os_version_name"] = _BUILD_TO_VERSION_NAME.get(str(info["os_build"]), "")
    return info


def _compose_os_name(os_raw: str) -> str:
    lower = os_raw.lower()
    for marker, edition in _OS_EDITION_MAP.items():
        if marker in lower:
            return edition
    if "windows" in lower:
        return "Windows 专业版"
    return os_raw


def _latest_subdir(root: Path):
    try:
        subdirs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    return subdirs


def _find_file(logs_root: str, filename: str):
    """在日志根目录（或最新子目录）中定位某个日志文件。"""
    root = Path(logs_root)
    if not root.exists():
        return None
    for candidate in [root, *(_latest_subdir(root) if root.is_dir() else [])]:
        fp = candidate / filename
        if fp.is_file():
            return fp
    return None


def read_system_info_from_logs(logs_root: str) -> Dict[str, object]:
    root = Path(logs_root)
    if not root.exists():
        return {}
    # 优先取最新子目录（与引擎其它解析一致）
    for candidate in [root, *_latest_subdir(root)]:
        fp = candidate / "system_info.txt"
        if fp.is_file():
            try:
                return parse_system_info_text(fp.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return {}


def parse_software_version(app_log_text: str) -> str:
    """从 app.log 第一行提取 Development version。"""
    for line in (app_log_text or "").splitlines():
        match = re.search(r"Development version:\s*(\S+)", line)
        if match:
            return match.group(1).strip()
    return ""


def read_software_version(app_log_path: str) -> str:
    try:
        with open(app_log_path, "r", encoding="utf-8", errors="ignore") as handle:
            return parse_software_version(handle.read(4096))
    except OSError:
        return ""


def parse_wifi_handle_version(app_log_text: str) -> str:
    """从 app.log 中 SCAN_BRIDGE / CR_Scan_Pocket_sys 固件地址提取 wifi 手柄版本。"""
    patterns = (
        re.compile(r"CR_Scan_Pocket_sys_v?([\d.]+)", re.IGNORECASE),
        re.compile(r"version\s*=\s*([\d.]+)", re.IGNORECASE),
    )
    for line in (app_log_text or "").splitlines():
        if "SCAN_BRIDGE" not in line and "CR_Scan_Pocket_sys" not in line:
            continue
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                return match.group(1).strip()
    return ""


def read_wifi_handle_version(app_log_path: str) -> str:
    try:
        with open(app_log_path, "r", encoding="utf-8", errors="ignore") as handle:
            return parse_wifi_handle_version(handle.read())
    except OSError:
        return ""


def detect_wifi_band() -> str:
    """运行 netsh wlan show interfaces 判断 802.11ax(→wifi6) / 802.11ac(→wifi5)。"""
    try:
        completed = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="ignore",
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    text = completed.stdout or ""
    match = re.search(r"Radio type\s*:\s*([\w.-]+)", text, re.IGNORECASE)
    if not match:
        return ""
    radio = match.group(1).lower()
    if radio.startswith("802.11ax"):
        return "wifi6"
    if radio.startswith("802.11ac"):
        return "wifi5"
    return ""


def collect_environment_info(
    logs_root: str,
    *,
    app_log_path: Optional[str] = None,
    detect_band: bool = True,
) -> Dict[str, object]:
    """汇总帧率统计模板所需的电脑侧环境信息。"""
    system_info = read_system_info_from_logs(logs_root) or {}
    info: Dict[str, object] = dict(system_info)
    app_log = Path(app_log_path) if app_log_path else _find_file(logs_root, "app.log")
    if app_log is not None and app_log.is_file():
        info["software_version"] = read_software_version(str(app_log))
        info["wifi_handle_version"] = read_wifi_handle_version(str(app_log))
    if detect_band:
        info["wifi_band"] = detect_wifi_band()
    return info
