from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_DEVICE_INFO_PATTERNS = {
    "camera_name": re.compile(r"camera name:\s*(.+?)\s*$", re.IGNORECASE),
    "camera_serial_number": re.compile(r"camera serial number:\s*(.+?)\s*$", re.IGNORECASE),
    "camera_connection_type": re.compile(r"camera connection type:\s*(.+?)\s*$", re.IGNORECASE),
    "camera_firmware_version": re.compile(r"camera firmware version:\s*(.+?)\s*$", re.IGNORECASE),
}
_SDK_PIPELINE_START_RE = re.compile(r"Pipeline start done!")
_SDK_PIPELINE_STOP_RE = re.compile(r"Stop pipeline done!")
_SDK_FPS_RE = re.compile(r"frameset output rate=(\d+(?:\.\d+)?)fps", re.IGNORECASE)
_SDK_TIMESTAMP_RE = re.compile(r"^\[(\d{2})/(\d{2}) (\d{2}:\d{2}:\d{2}\.\d+)\]")
# scan_log_*.txt 的完整时间戳（含年份）。
_SCAN_LOG_TIMESTAMP_RE = re.compile(r"\[(\d{4})-(\d{2})-(\d{2}) (\d{2}:\d{2}:\d{2}\.\d+)\]")
_SCAN_LOG_PREVIEW_RE = re.compile(r"obscan_scan_preview")
_SCAN_LOG_SCAN_START_RE = re.compile(r"obscan_scan_start")
# 停止标志：优先 OB_SCAN_MESSAGE_ID_SCANNING_STOP_SUCCESS；部分机型（如 Raptor Pro USB）
# 只输出 `stop progress 1.000000`（进度到达 1.0 即完成），与扫描步骤的成功判定保持一致。
_SCAN_LOG_SCAN_STOP_RE = re.compile(
    r"OB_SCAN_MESSAGE_ID_SCANNING_STOP_SUCCESS|stop progress 1\.0+", re.IGNORECASE
)
_DEVICE_INFO_JSON_ALIASES = {
    "camera_name": ("camera_name", "cameraName", "name", "camera"),
    "camera_serial_number": (
        "camera_serial_number",
        "cameraSerialNumber",
        "serial_number",
        "serialNumber",
        "sn",
    ),
    "camera_connection_type": (
        "camera_connection_type",
        "cameraConnectionType",
        "connection_type",
        "connectionType",
        "connection",
    ),
    "camera_firmware_version": (
        "camera_firmware_version",
        "cameraFirmwareVersion",
        "firmware_version",
        "firmwareVersion",
        "firmware",
    ),
}


def _safe_mtime(fp: Path) -> float:
    try:
        return float(fp.stat().st_mtime)
    except Exception:
        return 0.0


def _latest_subdir(root: Path) -> Optional[Path]:
    try:
        subs = [p for p in root.iterdir() if p.is_dir()]
    except Exception:
        return None
    if not subs:
        return None
    return max(subs, key=_safe_mtime)


def copy_logs(src_dir: str, dst_dir: str) -> None:
    """
    复制 CrealityScan 日志到归档目录。

    为避免产物过大/过杂：
    - 如果 src_dir 下存在子目录，则只复制“最新的日志文件夹”（按 mtime）到 dst_dir/<folder_name>
    - 否则复制 src_dir 全量到 dst_dir
    """
    src = Path(src_dir)
    dst_root = Path(dst_dir)
    if not src.exists():
        return

    dst_root.mkdir(parents=True, exist_ok=True)

    if src.is_file():
        shutil.copy2(str(src), str(dst_root / src.name))
        return

    if src.is_dir():
        latest = _latest_subdir(src)
        if latest is not None:
            dst = dst_root / latest.name
            shutil.copytree(str(latest), str(dst), dirs_exist_ok=True)
            return

    # 兜底：复制源目录（或用户直接传入的会话目录）
    shutil.copytree(str(src), str(dst_root), dirs_exist_ok=True)


def _iter_text_files(root: Path) -> Sequence[Path]:
    exts = {".log", ".txt"}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            yield p


def _resolve_scan_root(root: Path) -> Optional[Path]:
    if not root.exists():
        return None
    if root.is_dir():
        latest = _latest_subdir(root)
        if latest is not None:
            return latest
    return root


def _normalize_device_info_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()
    return ""


def _extract_device_info_from_json(root: Path) -> Dict[str, str]:
    device_info_path = root / "device_info.json"
    if not device_info_path.is_file():
        return {}

    try:
        raw = json.loads(device_info_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    candidates = [raw]
    for nested_key in ("device_info", "deviceInfo", "device", "camera"):
        nested = raw.get(nested_key)
        if isinstance(nested, dict):
            candidates.append(nested)

    info: Dict[str, str] = {}
    for target_key, aliases in _DEVICE_INFO_JSON_ALIASES.items():
        for candidate in candidates:
            for alias in aliases:
                value = _normalize_device_info_value(candidate.get(alias))
                if value:
                    info[target_key] = value
                    break
            if target_key in info:
                break
    return info


def _read_tail_text(fp: Path, max_bytes_per_file: int) -> str:
    size = fp.stat().st_size
    with fp.open("rb") as f:
        if size > max_bytes_per_file:
            f.seek(-max_bytes_per_file, os.SEEK_END)
        data = f.read()
    return data.decode("utf-8", errors="ignore")


def extract_device_info(logs_root: str, max_bytes_per_file: int = 1024 * 1024) -> Dict[str, str]:
    """
    从 Creality Scan 最新日志目录中提取设备信息。

    优先读取最新目录下的 `device_info.json`，缺失字段再回退扫描文本日志。

    当前返回字段：
    - camera_name
    - camera_serial_number
    - camera_connection_type
    - camera_firmware_version
    """
    root = _resolve_scan_root(Path(logs_root))
    if root is None or not root.exists():
        return {}

    info: Dict[str, str] = _extract_device_info_from_json(root)
    if len(info) == len(_DEVICE_INFO_PATTERNS):
        return info

    files = sorted(_iter_text_files(root), key=_safe_mtime, reverse=True)
    for fp in files:
        try:
            text = _read_tail_text(fp, max_bytes_per_file)
        except Exception:
            continue

        file_info: Dict[str, str] = {}
        for raw_line in text.splitlines():
            line = _ANSI_ESCAPE_RE.sub("", raw_line).strip()
            if not line:
                continue
            for key, pattern in _DEVICE_INFO_PATTERNS.items():
                match = pattern.search(line)
                if match:
                    file_info[key] = match.group(1).strip()
        for key, value in file_info.items():
            info.setdefault(key, value)
        if len(info) == len(_DEVICE_INFO_PATTERNS):
            break

    return info


def scan_keywords(
    logs_root: str, keywords: List[str], max_matches: int = 200, max_bytes_per_file: int = 1024 * 1024
) -> Dict[str, List[str]]:
    """
    在日志目录中按关键词扫描，返回 {keyword: [line, ...]}。
    为了性能与稳定性：
    - 每个文件只读取末尾 max_bytes_per_file 字节
    - 读文件用 errors='ignore'
    """
    root = _resolve_scan_root(Path(logs_root))
    if root is None or not root.exists():
        return {}

    result: Dict[str, List[str]] = {k: [] for k in keywords}
    keywords_lower = [k.lower() for k in keywords]

    for fp in _iter_text_files(root):
        try:
            text = _read_tail_text(fp, max_bytes_per_file)
        except Exception:
            continue

        for line in text.splitlines():
            line_lower = line.lower()
            for k, kl in zip(keywords, keywords_lower):
                if kl and kl in line_lower:
                    result[k].append(f"{fp.name}: {line}")
                    if len(result[k]) >= max_matches:
                        # 达到上限就不再追加，避免报告过大
                        break

    # 移除空项
    return {k: v for k, v in result.items() if v}


def extract_sdk_fps_sessions(logs_root: str, year_hint: Optional[int] = None) -> List[Dict[str, object]]:
    """Return complete SDK pipeline FPS sessions with timestamps."""
    root = _resolve_scan_root(Path(logs_root))
    if root is None or not root.exists():
        return []

    sdk_log = root / "ScannerStreamSDK.log"
    if not sdk_log.is_file():
        return []

    year = int(year_hint or datetime.now().year)
    sessions: List[Dict[str, object]] = []
    current: Optional[Dict[str, object]] = None

    try:
        lines = sdk_log.open("r", encoding="utf-8", errors="ignore")
    except Exception:
        return []

    with lines:
        for line in lines:
            timestamp_match = _SDK_TIMESTAMP_RE.search(line)
            line_at: Optional[datetime] = None
            if timestamp_match:
                try:
                    line_at = datetime.strptime(
                        f"{year}-{timestamp_match.group(1)}-{timestamp_match.group(2)} "
                        f"{timestamp_match.group(3)}",
                        "%Y-%m-%d %H:%M:%S.%f",
                    )
                except ValueError:
                    line_at = None

            if _SDK_PIPELINE_START_RE.search(line):
                current = {"start_line": line.rstrip(), "start_at": line_at, "fps": []}
                continue
            if current is None:
                continue

            fps_match = _SDK_FPS_RE.search(line)
            if fps_match:
                try:
                    current["fps"].append(float(fps_match.group(1)))
                except (TypeError, ValueError):
                    pass
                continue

            if _SDK_PIPELINE_STOP_RE.search(line):
                fps_values = current.get("fps") if isinstance(current.get("fps"), list) else []
                start_at = current.get("start_at")
                if fps_values and isinstance(start_at, datetime) and line_at is not None:
                    sessions.append(
                        {
                            "start_line": current.get("start_line", ""),
                            "stop_line": line.rstrip(),
                            "start_at": start_at.isoformat(timespec="microseconds"),
                            "stop_at": line_at.isoformat(timespec="microseconds"),
                            "avg_fps": round(sum(fps_values) / len(fps_values), 3),
                            "peak_fps": round(max(fps_values), 3),
                            "min_fps": round(min(fps_values), 3),
                            "samples": len(fps_values),
                        }
                    )
                current = None

    return sessions


def extract_sdk_fps_stats(logs_root: str, max_bytes_per_file: int = 1024 * 1024) -> Dict[str, object]:
    root = _resolve_scan_root(Path(logs_root))
    if root is None or not root.exists():
        return {}

    sdk_log = root / "ScannerStreamSDK.log"
    if not sdk_log.is_file():
        return {}

    try:
        text = _read_tail_text(sdk_log, max_bytes_per_file)
    except Exception:
        return {}

    sessions: List[Dict[str, object]] = []
    current: Optional[Dict[str, object]] = None
    for line in text.splitlines():
        if _SDK_PIPELINE_START_RE.search(line):
            current = {"start_line": line, "fps": []}
            continue
        if current is None:
            continue
        m = _SDK_FPS_RE.search(line)
        if m:
            try:
                current["fps"].append(float(m.group(1)))
            except Exception:
                pass
            continue
        if _SDK_PIPELINE_STOP_RE.search(line):
            current["stop_line"] = line
            fps_values = current.get("fps") if isinstance(current.get("fps"), list) else []
            if fps_values:
                sessions.append(
                    {
                        "start_line": current.get("start_line", ""),
                        "stop_line": current.get("stop_line", ""),
                        "avg_fps": round(sum(fps_values) / len(fps_values), 3),
                        "peak_fps": round(max(fps_values), 3),
                        "min_fps": round(min(fps_values), 3),
                        "samples": len(fps_values),
                    }
                )
            current = None

    if not sessions:
        return {}

    latest = sessions[-1]
    return {
        "sdk_avg_fps": latest["avg_fps"],
        "sdk_peak_fps": latest["peak_fps"],
        "sdk_min_fps": latest["min_fps"],
        "sdk_fps_samples": latest["samples"],
        "sdk_fps_sessions_count": len(sessions),
    }


def _parse_scan_log_timestamp(line: str) -> Optional[datetime]:
    match = _SCAN_LOG_TIMESTAMP_RE.search(line)
    if not match:
        return None
    try:
        return datetime.strptime(
            f"{match.group(1)}-{match.group(2)}-{match.group(3)} {match.group(4)}",
            "%Y-%m-%d %H:%M:%S.%f",
        )
    except ValueError:
        return None


def _extract_scan_phase_blocks(
    logs_root: str,
    start_at: Optional[datetime] = None,
    end_at: Optional[datetime] = None,
) -> tuple[list[dict[str, object]], Optional[int]]:
    """
    从 scan_log_*.txt 中解析“预览开始 → 扫描开始 → 扫描停止”的分组。

    注意：扫描日志可能按大小滚动成多个 scan_log_*.txt，长任务（多次扫描）期间
    会跨文件滚动，因此必须按文件名时间顺序读取全部日志，而不是只读“最新”一份，
    否则只会拿到最后一个日志里的扫描，导致帧率统计缺行。

    可选 start_at/end_at 用于只保留任务时间窗口内的扫描，避免把同一会话目录里
    早于本次任务的扫描混进来。

    返回 (blocks, year_hint)，每个 block:
      {"preview_at": datetime|None, "scan_at": datetime|None, "stop_at": datetime|None}
    """
    root = _resolve_scan_root(Path(logs_root))
    if root is None or not root.exists():
        return [], None

    scan_logs = sorted(
        (p for p in root.glob("scan_log_*.txt") if p.is_file()),
        key=lambda p: p.name,
    )
    if not scan_logs:
        return [], None

    events: list[tuple[str, datetime]] = []
    year_hint: Optional[int] = None
    for fp in scan_logs:
        try:
            handle = fp.open("r", encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with handle:
            for line in handle:
                stamp = _parse_scan_log_timestamp(line)
                if stamp is None:
                    continue
                if year_hint is None:
                    year_hint = stamp.year
                if _SCAN_LOG_PREVIEW_RE.search(line):
                    events.append(("preview", stamp))
                elif _SCAN_LOG_SCAN_START_RE.search(line):
                    events.append(("scan_start", stamp))
                elif _SCAN_LOG_SCAN_STOP_RE.search(line):
                    events.append(("stop", stamp))

    blocks: list[dict[str, object]] = []
    pending_preview: Optional[datetime] = None
    for kind, stamp in events:
        if kind == "preview":
            pending_preview = stamp
        elif kind == "scan_start":
            if start_at is not None and stamp < start_at:
                pending_preview = None
                continue
            if end_at is not None and stamp > end_at:
                pending_preview = None
                continue
            blocks.append({"preview_at": pending_preview, "scan_at": stamp, "stop_at": None})
            pending_preview = None
        elif kind == "stop":
            if blocks and blocks[-1].get("stop_at") is None:
                blocks[-1]["stop_at"] = stamp
    return blocks, year_hint


def extract_fps_metrics_by_phase(
    logs_root: str,
    start_at: Optional[datetime] = None,
    end_at: Optional[datetime] = None,
) -> list[Dict[str, object]]:
    """
    按“预览/扫描”阶段切分 SDK 帧率采样，返回每个模式一个阶段指标块。

    数据源：
    - scan_log_*.txt：obscan_scan_preview / obscan_scan_start / 停止标志
      （OB_SCAN_MESSAGE_ID_SCANNING_STOP_SUCCESS 或 stop progress 1.000000）切分阶段；
    - ScannerStreamSDK.log：`frameset output rate=<值>fps` 帧率采样点。

    可选 start_at/end_at 只统计任务时间窗口内的扫描阶段。

    每个 block:
      preview_at / scan_at / stop_at（ISO 或空串）
      preview_fps / scan_min_fps / scan_max_fps / scan_avg_fps（原始浮点，可能为 None）
      preview_samples / scan_samples（采样点数量）

    返回原始浮点值，四舍五入在写入 Excel 时统一处理。
    """
    root = _resolve_scan_root(Path(logs_root))
    if root is None or not root.exists():
        return []

    blocks, year_hint = _extract_scan_phase_blocks(logs_root, start_at=start_at, end_at=end_at)
    if not blocks:
        return []

    sdk_log = root / "ScannerStreamSDK.log"
    samples: list[tuple[datetime, float]] = []
    if sdk_log.is_file():
        year = year_hint
        try:
            with sdk_log.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    fps_match = _SDK_FPS_RE.search(line)
                    if not fps_match:
                        continue
                    ts_match = _SDK_TIMESTAMP_RE.search(line)
                    if not ts_match or year is None:
                        continue
                    try:
                        stamp = datetime.strptime(
                            f"{year}-{ts_match.group(1)}-{ts_match.group(2)} {ts_match.group(3)}",
                            "%Y-%m-%d %H:%M:%S.%f",
                        )
                        samples.append((stamp, float(fps_match.group(1))))
                    except (ValueError, TypeError):
                        continue
        except OSError:
            samples = []

    result: List[Dict[str, object]] = []
    for block in blocks:
        preview_at = block.get("preview_at")
        scan_at = block.get("scan_at")
        stop_at = block.get("stop_at")
        preview_values: list[float] = []
        scan_values: list[float] = []
        for stamp, value in samples:
            if scan_at is None:
                continue
            if preview_at is not None and preview_at <= stamp < scan_at:
                preview_values.append(value)
            elif stop_at is not None and scan_at <= stamp <= stop_at:
                scan_values.append(value)
            elif stop_at is None and stamp >= scan_at:
                scan_values.append(value)

        def _avg(values: Sequence[float]) -> Optional[float]:
            return sum(values) / len(values) if values else None

        result.append(
            {
                "preview_at": preview_at.isoformat(timespec="microseconds") if preview_at else "",
                "scan_at": scan_at.isoformat(timespec="microseconds") if scan_at else "",
                "stop_at": stop_at.isoformat(timespec="microseconds") if stop_at else "",
                "preview_fps": _avg(preview_values),
                "scan_min_fps": min(scan_values) if scan_values else None,
                "scan_max_fps": max(scan_values) if scan_values else None,
                "scan_avg_fps": _avg(scan_values),
                "preview_samples": len(preview_values),
                "scan_samples": len(scan_values),
            }
        )
    return result

