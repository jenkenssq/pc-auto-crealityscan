from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

from engine.mouse import move_mouse_smooth
from engine.slide_rail_scan_motion import SlideRailScanMotion


START_KEY = b"obscan_scan_start"
START_FALLBACK_KEY = b"blae run begin"
# 停止成功判定关键字：命中任一即视为停止成功。
# - OB_SCAN_MESSAGE_ID_SCANNING_STOP_SUCCESS：多数版本会输出的进程消息。
# - stop progress 1.000000：部分版本/机型只输出 stop progress，进度到达 1.0 即完成。
STOP_SUCCESS_KEY = b"OB_SCAN_MESSAGE_ID_SCANNING_STOP_SUCCESS"
STOP_PROGRESS_COMPLETE_KEY = b"stop progress 1.000000"
STOP_SUCCESS_KEYS = (STOP_SUCCESS_KEY, STOP_PROGRESS_COMPLETE_KEY)
FRAME_RE = re.compile(br"frame\s+(\d+)", re.IGNORECASE)
TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6})\]")
FRAME_TEXT_RE = re.compile(r"\bframe\s+(\d+)\b", re.IGNORECASE)
CONVERT_INDEX_RE = re.compile(
    br"\bconvert index\s+(\d+)\s+to\s+file index\s+(\d+)\b", re.IGNORECASE
)
CONVERT_INDEX_TEXT_RE = re.compile(
    r"\bconvert index\s+(\d+)\s+to\s+file index\s+(\d+)\b", re.IGNORECASE
)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
ANSI_FALLBACK_RE = re.compile(r"\[(?:\d{1,3};)*\d{1,3}m|\[0m", re.IGNORECASE)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
SCAN_LOG_NAME_RE = re.compile(r"^scan_log_(\d{8})-(\d{6})\.txt$", re.IGNORECASE)


def _resolve_target_frames(params: Dict[str, Any]) -> int:
    # 新参数：target_frames（更符合直觉：达到/大于等于 N 帧即达标）
    raw = params.get("target_frames")
    if raw is not None:
        try:
            v = int(raw)
            if v > 0:
                return v
        except Exception:
            pass

    # 兼容旧参数：target_frames_gt（严格大于），等价于 target_frames = gt + 1
    gt = _int(params, "target_frames_gt", 200)
    return max(1, gt + 1)



def _num(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        v = params.get(key, default)
        return float(v)
    except Exception:
        return float(default)


def _int(params: Dict[str, Any], key: str, default: int) -> int:
    try:
        v = params.get(key, default)
        return int(v)
    except Exception:
        return int(default)


def _bool(params: Dict[str, Any], key: str, default: bool) -> bool:
    raw = params.get(key, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in {"1", "true", "yes", "y", "on"}:
            return True
        if s in {"0", "false", "no", "n", "off"}:
            return False
    return bool(default)


def _read_new_bytes(fp: Path, pos: int) -> Tuple[bytes, int]:
    with fp.open("rb") as f:
        try:
            size = int(fp.stat().st_size)
        except Exception:
            size = 0
        if pos < 0 or pos > size:
            pos = 0
        f.seek(pos)
        data = f.read()
        return data, f.tell()


def _path_mtime(fp: Path) -> float:
    try:
        return float(fp.stat().st_mtime)
    except Exception:
        return 0.0


def _path_size(fp: Path) -> int:
    try:
        return int(fp.stat().st_size)
    except Exception:
        return 0


def _scan_log_name_timestamp(fp: Path) -> Optional[datetime]:
    match = SCAN_LOG_NAME_RE.match(fp.name)
    if not match:
        return None
    try:
        return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _scan_log_sort_key(fp: Path) -> Tuple[int, float, float, str]:
    name_timestamp = _scan_log_name_timestamp(fp)
    if name_timestamp is not None:
        return (1, name_timestamp.timestamp(), _path_mtime(fp), fp.name)
    return (0, _path_mtime(fp), 0.0, fp.name)


def _is_newer_scan_log(candidate: Path, current_fp: Path) -> bool:
    candidate_timestamp = _scan_log_name_timestamp(candidate)
    current_timestamp = _scan_log_name_timestamp(current_fp)
    if candidate_timestamp is not None and current_timestamp is not None:
        return candidate_timestamp > current_timestamp
    return _scan_log_sort_key(candidate) > _scan_log_sort_key(current_fp)


def _latest_session_dir(log_root: Path) -> Optional[Path]:
    try:
        dirs = [p for p in log_root.iterdir() if p.is_dir()]
    except Exception:
        return None
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def _latest_scan_log_in_dir(session_dir: Path) -> Optional[Path]:
    try:
        files = [p for p in session_dir.glob("scan_log_*.txt") if p.is_file()]
    except Exception:
        return None
    if not files:
        return None
    return max(files, key=_scan_log_sort_key)


def _try_pick_scan_log(log_root: Path) -> Optional[Path]:
    if log_root.is_file():
        return log_root

    session = _latest_session_dir(log_root)
    if session:
        fp = _latest_scan_log_in_dir(session)
        if fp:
            return fp

    # 兜底：递归找（兼容目录结构变化）
    try:
        files = [p for p in log_root.rglob("scan_log_*.txt") if p.is_file()]
    except Exception:
        files = []
    if not files:
        return None
    return max(files, key=_scan_log_sort_key)



def _has_effective_scan_signal(fp: Path) -> bool:
    try:
        data = fp.read_bytes()
    except Exception:
        return False
    return _max_frame_in_bytes(data) > 0 or _scan_started_in_bytes(data, (START_KEY, START_FALLBACK_KEY))


def _should_switch_scan_log(current_fp: Optional[Path], candidate: Optional[Path], pos: int) -> bool:
    if candidate is None:
        return False
    if current_fp is None:
        return True
    if candidate == current_fp:
        return False
    if not _is_newer_scan_log(candidate, current_fp):
        return False
    if _has_effective_scan_signal(candidate):
        return True
    current_size = _path_size(current_fp)
    if current_size > 0 and pos >= current_size:
        return True
    return False


def _try_pick_stalled_scan_log(log_root: Path, current_fp: Optional[Path]) -> Optional[Path]:
    if current_fp is None or log_root.is_file():
        return None

    try:
        files = [path for path in current_fp.parent.glob("scan_log_*.txt") if path.is_file()]
    except Exception:
        files = []
    candidates = [
        path
        for path in files
        if path != current_fp and _is_newer_scan_log(path, current_fp) and _has_effective_scan_signal(path)
    ]
    if not candidates:
        return None
    return max(candidates, key=_scan_log_sort_key)


def _read_live_scan_log(log_root: Path, current_fp: Optional[Path], pos: int) -> Tuple[Optional[Path], bytes, int, bool]:
    candidate = _try_pick_scan_log(log_root)
    switched = False
    if _should_switch_scan_log(current_fp, candidate, pos):
        current_fp = candidate
        pos = 0
        switched = True
    if current_fp is None:
        return None, b"", pos, switched
    data, pos = _read_new_bytes(current_fp, pos)
    return current_fp, data, pos, switched


def _extract_frame_from_text(text: str) -> Optional[int]:
    if not text:
        return None
    norm = text.replace(" ", "")
    norm = norm.replace("O", "0").replace("o", "0")
    values: List[int] = []
    joined_digits = "".join(ch for ch in norm if ch.isdigit())
    if joined_digits:
        try:
            joined_value = int(joined_digits)
        except Exception:
            joined_value = -1
        if 0 <= joined_value <= 100000:
            values.append(joined_value)
    norm = norm.replace(",", "")
    for match in NUMBER_RE.finditer(norm):
        try:
            value = int(float(match.group(0)))
        except Exception:
            continue
        if 0 <= value <= 100000:
            values.append(value)
    if not values:
        return None
    return max(values)


def _wait_scan_log(log_root: Path, after_ts: float, timeout_sec: float, poll_interval_sec: float) -> Path:
    deadline = time.time() + timeout_sec
    last: Optional[Path] = None
    while time.time() < deadline:
        cand = _try_pick_scan_log(log_root)
        if cand:
            last = cand
            try:
                if cand.stat().st_mtime >= after_ts:
                    return cand
            except Exception:
                return cand
        time.sleep(max(0.2, poll_interval_sec))
    if last:
        return last
    raise RuntimeError(f"未找到 scan_log_*.txt：{log_root}")


def _max_frame_in_bytes(data: bytes) -> int:
    max_frame = 0
    for m in CONVERT_INDEX_RE.finditer(data):
        try:
            convert_index = int(m.group(1))
            file_index = int(m.group(2))
            n = max(convert_index, file_index)
            if n > max_frame:
                max_frame = n
        except Exception:
            continue
    if max_frame > 0:
        return max_frame
    for m in FRAME_RE.finditer(data):
        try:
            n = int(m.group(1))
            if n > max_frame:
                max_frame = n
        except Exception:
            continue
    if max_frame > 0:
        return max_frame
    return max_frame


def _first_frame_ge_in_bytes(data: bytes, target_frames: int) -> Optional[int]:
    for m in CONVERT_INDEX_RE.finditer(data):
        try:
            convert_index = int(m.group(1))
            file_index = int(m.group(2))
            n = max(convert_index, file_index)
        except Exception:
            continue
        if n >= target_frames:
            return n
    for m in FRAME_RE.finditer(data):
        try:
            n = int(m.group(1))
        except Exception:
            continue
        if n >= target_frames:
            return n
    return None


def _parse_log_timestamp(line: str) -> Optional[datetime]:
    m = TIMESTAMP_RE.match(line.strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")
    except Exception:
        return None


def _normalize_log_line(line: str) -> str:
    text = ANSI_RE.sub("", line or "")
    text = ANSI_FALLBACK_RE.sub("", text)
    return text.strip()


def _extract_start_event(data: bytes, start_keys: Tuple[bytes, ...]) -> Tuple[Optional[datetime], Optional[str]]:
    marker_texts = [k.decode("utf-8", errors="ignore").strip().lower() for k in start_keys if k]
    text = data.decode("utf-8", errors="ignore")
    for raw_line in text.splitlines():
        line = _normalize_log_line(raw_line)
        if not line:
            continue
        ts = _parse_log_timestamp(line)
        if ts is None:
            continue
        lower_line = line.lower()
        if any(marker and marker in lower_line for marker in marker_texts):
            return ts, line
        if CONVERT_INDEX_TEXT_RE.search(line):
            return ts, line
        if FRAME_TEXT_RE.search(line):
            return ts, line
    return None, None


def _extract_frame_records(data: bytes) -> Tuple[Optional[int], Optional[datetime], Optional[int], Optional[datetime]]:
    first_frame: Optional[int] = None
    first_ts: Optional[datetime] = None
    last_frame: Optional[int] = None
    last_ts: Optional[datetime] = None
    text = data.decode("utf-8", errors="ignore")
    for raw_line in text.splitlines():
        line = _normalize_log_line(raw_line)
        if not line:
            continue
        convert_match = CONVERT_INDEX_TEXT_RE.search(line)
        if convert_match:
            ts = _parse_log_timestamp(line)
            if ts is None:
                continue
            try:
                frame_no = max(int(convert_match.group(1)), int(convert_match.group(2)))
            except Exception:
                continue
            if first_frame is None:
                first_frame = frame_no
                first_ts = ts
            last_frame = frame_no
            last_ts = ts
            continue
        m = FRAME_TEXT_RE.search(line)
        if not m:
            continue
        ts = _parse_log_timestamp(line)
        if ts is None:
            continue
        try:
            frame_no = int(m.group(1))
        except Exception:
            continue
        if first_frame is None:
            first_frame = frame_no
            first_ts = ts
        last_frame = frame_no
        last_ts = ts
    return first_frame, first_ts, last_frame, last_ts


def _pick_wifi_interface_name() -> str:
    keywords = ("wi-fi", "wifi", "wlan", "wireless", "无线", "无线网络", "无线局域网")
    try:
        counters = psutil.net_io_counters(pernic=True)
    except Exception:
        return ""
    for name in counters:
        lower_name = str(name or "").strip().lower()
        if any(key in lower_name for key in keywords):
            return str(name)
    return ""


def _prime_system_sampler(wifi_interface_name: str) -> Dict[str, Any]:
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass

    last_total_bytes: Optional[int] = None
    if wifi_interface_name:
        try:
            counters = psutil.net_io_counters(pernic=True)
            nic = counters.get(wifi_interface_name)
            if nic is not None:
                last_total_bytes = int(nic.bytes_recv + nic.bytes_sent)
        except Exception:
            last_total_bytes = None

    return {
        "wifi_interface_name": wifi_interface_name,
        "last_ts": time.time(),
        "last_total_bytes": last_total_bytes,
    }


def _sample_system_metrics(state: Dict[str, Any], observed_at: float) -> Dict[str, float]:
    try:
        cpu_percent = float(psutil.cpu_percent(interval=None))
    except Exception:
        cpu_percent = 0.0

    try:
        memory_percent = float(psutil.virtual_memory().percent)
    except Exception:
        memory_percent = 0.0

    wifi_rate_kbps = 0.0
    wifi_interface_name = str(state.get("wifi_interface_name") or "")
    if wifi_interface_name:
        try:
            counters = psutil.net_io_counters(pernic=True)
            nic = counters.get(wifi_interface_name)
            if nic is not None:
                total_bytes = int(nic.bytes_recv + nic.bytes_sent)
                last_total_bytes = state.get("last_total_bytes")
                last_ts = float(state.get("last_ts") or observed_at)
                dt = max(0.001, observed_at - last_ts)
                if last_total_bytes is not None:
                    delta_bytes = max(0, total_bytes - int(last_total_bytes))
                    wifi_rate_kbps = (delta_bytes * 8.0 / 1024.0) / dt
                state["last_total_bytes"] = total_bytes
        except Exception:
            wifi_rate_kbps = 0.0

    state["last_ts"] = observed_at
    return {
        "cpu_percent": round(cpu_percent, 3),
        "memory_percent": round(memory_percent, 3),
        "wifi_rate_kbps": round(wifi_rate_kbps, 3),
    }


def _build_resource_by_second(samples: List[Tuple[float, float, float, float]], origin_ts: float) -> Dict[int, Dict[str, float]]:
    buckets: Dict[int, Dict[str, float]] = {}
    for observed_at, cpu_percent, memory_percent, wifi_rate_kbps in samples:
        sec = int(max(0.0, observed_at - origin_ts))
        bucket = buckets.setdefault(
            sec,
            {
                "cpu_sum": 0.0,
                "memory_sum": 0.0,
                "wifi_sum": 0.0,
                "count": 0.0,
            },
        )
        bucket["cpu_sum"] += float(cpu_percent)
        bucket["memory_sum"] += float(memory_percent)
        bucket["wifi_sum"] += float(wifi_rate_kbps)
        bucket["count"] += 1.0
    return buckets


def _merge_trend_rows(
    system_samples: List[Tuple[float, float, float, float]],
    origin_ts: float,
) -> List[Dict[str, float]]:
    resource_map = _build_resource_by_second(system_samples, origin_ts)
    all_seconds = sorted(resource_map)
    rows: List[Dict[str, float]] = []
    last_cpu = 0.0
    last_memory = 0.0
    last_wifi = 0.0
    for sec in all_seconds:
        resource_item = resource_map.get(sec)
        if resource_item and resource_item.get("count", 0.0) > 0:
            count = float(resource_item["count"])
            last_cpu = resource_item["cpu_sum"] / count
            last_memory = resource_item["memory_sum"] / count
            last_wifi = resource_item["wifi_sum"] / count
        rows.append(
            {
                "second": float(sec),
                "cpu_percent": round(last_cpu, 3),
                "memory_percent": round(last_memory, 3),
                "wifi_rate_kbps": round(last_wifi, 3),
            }
        )
    return rows


def _summarize_trend_rows(rows: List[Dict[str, float]]) -> Dict[str, float]:
    if not rows:
        return {
            "avg_cpu_percent": 0.0,
            "peak_cpu_percent": 0.0,
            "avg_memory_percent": 0.0,
            "peak_memory_percent": 0.0,
            "avg_wifi_rate_kbps": 0.0,
            "peak_wifi_rate_kbps": 0.0,
        }

    count = float(len(rows))
    return {
        "avg_cpu_percent": round(sum(float(item.get("cpu_percent", 0.0)) for item in rows) / count, 3),
        "peak_cpu_percent": round(max(float(item.get("cpu_percent", 0.0)) for item in rows), 3),
        "avg_memory_percent": round(sum(float(item.get("memory_percent", 0.0)) for item in rows) / count, 3),
        "peak_memory_percent": round(max(float(item.get("memory_percent", 0.0)) for item in rows), 3),
        "avg_wifi_rate_kbps": round(sum(float(item.get("wifi_rate_kbps", 0.0)) for item in rows) / count, 3),
        "peak_wifi_rate_kbps": round(max(float(item.get("wifi_rate_kbps", 0.0)) for item in rows), 3),
    }


def _first_key_in(buf: bytes, keys: Tuple[bytes, ...]) -> Optional[bytes]:
    for key in keys:
        if key and key in buf:
            return key
    return None


def _wait_log_contains(
    log_root: Path,
    fp: Path,
    start_pos: int,
    key: Any,
    timeout_sec: float,
    poll_interval_sec: float,
) -> Tuple[Path, int]:
    # 兼容传入单个 bytes 或一组 bytes（任一命中即返回）。
    if isinstance(key, bytes):
        keys: Tuple[bytes, ...] = (key,)
    else:
        keys = tuple(bytes(k) for k in key)
    deadline = time.time() + timeout_sec
    current_fp = fp
    pos = start_pos
    buf = b""
    while time.time() < deadline:
        current_fp, data, pos, switched = _read_live_scan_log(log_root, current_fp, pos)
        if switched:
            buf = b""
            if current_fp is not None:
                print(f"[JENS] log_file={current_fp}")
                print(f"[JENS][scan_debug] cleared_wait_log_buffer keys={keys!r} log={current_fp}")
        if data:
            buf += data
            if len(buf) > 512 * 1024:
                buf = buf[-512 * 1024 :]
            matched = _first_key_in(buf, keys)
            if matched is not None:
                print(
                    f"[JENS][scan_debug] stop success log matched: "
                    f"{matched.decode('utf-8', errors='ignore')}"
                )
                return current_fp, pos
        time.sleep(max(0.2, poll_interval_sec))
    raise RuntimeError(f"等待日志关键字超时：{keys!r} in {current_fp}")


def _scan_started_in_bytes(data: bytes, start_keys: Tuple[bytes, ...], allow_frame_fallback: bool = True) -> bool:
    if not data:
        return False
    for k in start_keys:
        if k and k in data:
            return True
    if allow_frame_fallback:
        return FRAME_RE.search(data) is not None
    return False


def _poll_scan_start_from_logs(
    log_root: Path,
    current_fp: Optional[Path],
    pos: int,
    scan_buf: bytes,
    pre_log: Optional[Path],
    pre_log_size: int,
    step_started_at: float,
    start_keys: Tuple[bytes, ...],
    scan_origin_py_ts: Optional[float],
    fallback_start_py_ts: Optional[float],
    allow_frame_fallback: bool = True,
) -> Tuple[Optional[Path], int, bytes, Optional[float], Optional[float], bool, bool]:
    cand = _try_pick_scan_log(log_root)
    if cand and pre_log and cand != pre_log:
        try:
            if cand.stat().st_mtime < step_started_at - 1.0:
                cand = None
        except Exception:
            pass


    log_changed = bool(cand and (current_fp is None or cand != current_fp))
    if cand and log_changed:
        current_fp = cand
        scan_buf = b""
        if pre_log and cand == pre_log:
            pos = pre_log_size
        else:
            try:
                size = int(cand.stat().st_size)
            except Exception:
                size = 0
            pos = max(0, size - 256 * 1024)

    if current_fp is None:
        return current_fp, pos, scan_buf, scan_origin_py_ts, fallback_start_py_ts, False, log_changed

    try:
        data, pos = _read_new_bytes(current_fp, pos)
    except Exception:
        return (
            current_fp,
            pos,
            scan_buf,
            scan_origin_py_ts,
            fallback_start_py_ts,
            _scan_started_in_bytes(scan_buf, start_keys, allow_frame_fallback=allow_frame_fallback),
            log_changed,
        )

    if data:
        observed_at = time.time()
        scan_buf += data
        if START_KEY in data and scan_origin_py_ts is None:
            scan_origin_py_ts = observed_at
        if fallback_start_py_ts is None and _scan_started_in_bytes(
            data, start_keys, allow_frame_fallback=allow_frame_fallback
        ):
            fallback_start_py_ts = observed_at
        if len(scan_buf) > 512 * 1024:
            scan_buf = scan_buf[-512 * 1024 :]

    started = _scan_started_in_bytes(scan_buf, start_keys, allow_frame_fallback=allow_frame_fallback)
    if started and fallback_start_py_ts is None:
        fallback_start_py_ts = time.time()
    return current_fp, pos, scan_buf, scan_origin_py_ts, fallback_start_py_ts, started, log_changed


def _wait_log_contains_any(
    log_root: Path, fp: Path, start_pos: int, keys: Tuple[bytes, ...], timeout_sec: float, poll_interval_sec: float
) -> Tuple[Path, int]:
    deadline = time.time() + timeout_sec
    current_fp = fp
    pos = start_pos
    buf = b""
    while time.time() < deadline:
        current_fp, data, pos, switched = _read_live_scan_log(log_root, current_fp, pos)
        if switched:
            buf = b""
            if current_fp is not None:
                print(f"[JENS] log_file={current_fp}")
                print(f"[JENS][scan_debug] cleared_wait_log_any_buffer keys={keys!r} log={current_fp}")
        if data:
            buf += data
            if len(buf) > 512 * 1024:
                buf = buf[-512 * 1024 :]
            if _scan_started_in_bytes(data, keys) or _scan_started_in_bytes(buf, keys):
                return current_fp, pos
        time.sleep(max(0.2, poll_interval_sec))
    raise RuntimeError(f"等待日志开始标记超时：{keys!r} in {current_fp}")


def _wait_frames_ge(
    log_root: Path,
    fp: Path,
    start_pos: int,
    target_frames: int,
    timeout_sec: float,
    frame_stall_timeout_sec: float = 300,
    poll_interval_sec: float = 0.2,
    stalled_log_switch_interval_sec: float = 5,
    system_sampler_state: Optional[Dict[str, Any]] = None,
    system_samples: Optional[List[Tuple[float, float, float, float]]] = None,
) -> Tuple[Path, int, int]:
    deadline = time.time() + timeout_sec
    current_fp = fp
    pos = start_pos
    max_frame = 0
    sleep_sec = max(0.05, float(poll_interval_sec))
    stall_timeout_sec = max(0.1, float(frame_stall_timeout_sec))
    stalled_switch_interval_sec = max(0.1, float(stalled_log_switch_interval_sec))
    last_frame_progress_at = time.monotonic()
    last_stalled_switch_attempt_at = last_frame_progress_at
    frame_buf = b""

    print(
        f"[JENS][scan_debug] wait_frames begin log={current_fp} start_pos={start_pos} "
        f"target_frames={target_frames} timeout_sec={timeout_sec} "
        f"frame_stall_timeout_sec={stall_timeout_sec} "
        f"stalled_log_switch_interval_sec={stalled_switch_interval_sec}"
    )

    while time.time() < deadline:
        pos_before = pos
        current_fp, data, pos, switched = _read_live_scan_log(log_root, current_fp, pos)
        if switched:
            frame_buf = b""
            last_stalled_switch_attempt_at = time.monotonic()
        if switched or data:
            print(
                f"[JENS][scan_debug] wait_frames poll log={current_fp} switched={switched} "
                f"pos_before={pos_before} pos_after={pos} bytes={len(data)}"
            )
        if switched and current_fp is not None:
            print(f"[JENS] log_file={current_fp}")
        if data:
            frame_buf += data
            if len(frame_buf) > 64 * 1024:
                frame_buf = frame_buf[-64 * 1024 :]
            observed_at = time.time()
            if system_sampler_state is not None and system_samples is not None:
                metrics = _sample_system_metrics(system_sampler_state, observed_at)
                system_samples.append(
                    (
                        observed_at,
                        float(metrics["cpu_percent"]),
                        float(metrics["memory_percent"]),
                        float(metrics["wifi_rate_kbps"]),
                    )
                )
            cur = _max_frame_in_bytes(frame_buf)
            if cur > 0:
                print(f"[JENS][scan_debug] wait_frames batch_frame_max={cur} log={current_fp}")
            if cur > max_frame:
                max_frame = cur
                last_frame_progress_at = time.monotonic()
                last_stalled_switch_attempt_at = last_frame_progress_at
                print(f"[JENS] frame={max_frame}")
                print(
                    f"[JENS][scan_debug] wait_frames progress max_frame={max_frame} "
                    f"target_frames={target_frames} log={current_fp} pos={pos}"
                )
            reached_frame = _first_frame_ge_in_bytes(frame_buf, target_frames)
            if reached_frame is not None:
                print(
                    f"[JENS][scan_debug] wait_frames target_reached first_frame={reached_frame} "
                    f"target_frames={target_frames} log={current_fp} pos={pos}"
                )
                return current_fp, int(reached_frame), pos
        if max_frame >= target_frames:
            print(
                f"[JENS][scan_debug] wait_frames target_reached_without_new_data max_frame={max_frame} "
                f"target_frames={target_frames} log={current_fp} pos={pos}"
            )
            return current_fp, max_frame, pos
        stalled_sec = time.monotonic() - last_frame_progress_at
        since_switch_attempt_sec = time.monotonic() - last_stalled_switch_attempt_at
        if (
            stalled_sec >= stalled_switch_interval_sec
            and since_switch_attempt_sec >= stalled_switch_interval_sec
        ):
            last_stalled_switch_attempt_at = time.monotonic()
            stalled_candidate = _try_pick_stalled_scan_log(log_root, current_fp)
            print(
                f"[JENS][scan_debug] wait_frames stalled_log_switch_attempt "
                f"stalled_sec={stalled_sec:.3f} current={current_fp} candidate={stalled_candidate}"
            )
            if stalled_candidate is not None:
                current_fp = stalled_candidate
                pos = 0
                frame_buf = b""
                print(f"[JENS] log_file={current_fp}")
                print(
                    f"[JENS][scan_debug] wait_frames stalled_log_switched "
                    f"stalled_sec={stalled_sec:.3f} log={current_fp}"
                )
                continue
        if stalled_sec >= stall_timeout_sec:
            print(
                f"[JENS][scan_debug] wait_frames stalled stalled_sec={stalled_sec:.3f} "
                f"last_frame={max_frame} target_frames={target_frames} log={current_fp} pos={pos}"
            )
            raise RuntimeError(
                f"扫描帧数连续 {stall_timeout_sec:g} 秒未增长："
                f"target>={target_frames}, last={max_frame}, log={current_fp}"
            )
        if not data:
            time.sleep(sleep_sec)

    raise RuntimeError(f"等待帧数达到阈值超时：target>={target_frames}, last={max_frame}, log={current_fp}")


def _reset_mouse_hover(params: Dict[str, Any], move_to, sleep) -> None:
    """
    预览等操作结束后，鼠标可能停留在“开始”按钮上触发 hover 态，导致模板图不匹配。
    在点击前把鼠标移到一个安全位置，让 UI 恢复到非 hover 状态（KISS：默认移到左上角）。
    """
    safe_x = _int(params, "mouse_safe_x", 10)
    safe_y = _int(params, "mouse_safe_y", 10)
    move_duration_sec = _num(params, "mouse_safe_move_duration_sec", 0.35)
    move_steps = _int(params, "mouse_safe_move_steps", 12)
    sleep_sec = _num(params, "mouse_safe_sleep_sec", 0.35)
    try:
        ok = move_mouse_smooth((safe_x, safe_y), duration_sec=move_duration_sec, steps=move_steps)
        if not ok:
            move_to((safe_x, safe_y))
    except Exception:
        return
    try:
        sleep(max(0.0, sleep_sec))
    except Exception:
        pass


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from airtest.core.api import Template, device, exists, sleep, touch, wait  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "无法导入 Airtest（airtest.core.api）。请先安装依赖：python -m pip install -r requirements.txt"
        ) from e

    # 兼容：部分 Airtest 版本不再提供 api.move_to（例如 1.4.3）。
    try:
        from airtest.core.api import move_to as _move_to  # type: ignore
    except Exception:
        _move_to = None

    def move_to(pos) -> None:
        if _move_to is not None:
            _move_to(pos)
            return
        dev = device()
        if hasattr(dev, "move"):
            dev.move(pos)
            return
        if hasattr(dev, "mouse_move"):
            dev.mouse_move(pos)
            return
        raise RuntimeError("当前设备不支持鼠标移动（缺少 move/mouse_move）。")

    case = ctx.get("case") if isinstance(ctx.get("case"), dict) else {}
    app = case.get("app") if isinstance(case.get("app"), dict) else {}
    window_title_contains = str(app.get("window_title_contains") or "CrealityScan").strip()

    log_dir_param = str(params.get("log_dir") or "").strip()
    log_dir_case = str(app.get("log_dir") or "").strip()
    if log_dir_param or log_dir_case:
        log_root = Path(log_dir_param or log_dir_case)
    else:
        # 兜底：按默认安装/运行习惯推断（用户无需重复填写路径）
        log_root = Path.home() / "AppData" / "Local" / "Creality" / "CrealityScan" / "Logs"

    print(
        f"[JENS][scan_debug] effective_log_root={log_root} "
        f"source={'params' if log_dir_param else ('case' if log_dir_case else 'default')}"
    )

    target_frames = _resolve_target_frames(params)
    wait_log_file_timeout_sec = _num(params, "wait_log_file_timeout_sec", 30)
    wait_scan_start_timeout_sec = _num(params, "wait_scan_start_timeout_sec", 60)
    wait_frames_timeout_sec = _num(params, "wait_frames_timeout_sec", 1800)
    frame_stall_timeout_sec = _num(params, "frame_stall_timeout_sec", 300)
    poll_interval_sec = _num(params, "poll_interval_sec", 0.2)
    stalled_log_switch_interval_sec = _num(params, "stalled_log_switch_interval_sec", 5)
    wait_stop_success_timeout_sec = _num(params, "wait_stop_success_timeout_sec", 120)
    wifi_interface_name = str(params.get("wifi_interface_name") or "").strip() or _pick_wifi_interface_name()
    system_sampler_state = _prime_system_sampler(wifi_interface_name)

    base = Path(__file__).resolve().parent / "templates"

    # 扫描开始标记（可扩展：用户可在 params.scan_start_markers 里传入自定义字符串列表）
    start_keys = (START_KEY, START_FALLBACK_KEY)
    raw_markers = params.get("scan_start_markers")
    if isinstance(raw_markers, list) and all(isinstance(x, str) for x in raw_markers):
        extra = tuple((x or "").encode("utf-8", errors="ignore") for x in raw_markers if str(x or "").strip())
        if extra:
            start_keys = tuple(dict.fromkeys([*start_keys, *extra]))  # 去重且保序

    # 基线：在点击“开始”之前记录最新 scan_log 的大小，避免误用历史日志中的“开始标记”。
    pre_log = _try_pick_scan_log(log_root)
    pre_log_size = 0
    if pre_log:
        try:
            pre_log_size = int(pre_log.stat().st_size)
        except Exception:
            pre_log_size = 0

    # 1) 点击开始扫描
    start_btn_timeout_sec = _num(params, "start_btn_timeout_sec", 10)
    start_btn_retry = max(1, _int(params, "start_btn_retry", 3))
    start_btn_threshold = _num(params, "start_btn_threshold", 0.7)
    start_frame_wait_timeout_sec = max(0.5, _num(params, "start_frame_wait_timeout_sec", 300.0))
    start_btn_reclick_interval_sec = _num(params, "start_btn_reclick_interval_sec", 1.0)
    start_btn_reclick_wait_sec = _num(params, "start_btn_reclick_wait_sec", 2.0)
    start_tpl = Template(
        str(base / "tpl1772626136357.png"),
        record_pos=(-0.3, -0.172),
        resolution=(1920, 1080),
        threshold=start_btn_threshold,
    )
    stop_tpl = Template(str(base / "tpl1772626510524.png"), record_pos=(-0.248, -0.173), resolution=(1920, 1080))

    log_fp: Optional[Path] = None
    pos = 0
    scan_buf = b""
    t0 = time.time()
    last_click_ts = t0
    start_click_sent = False
    scan_origin_py_ts: Optional[float] = None
    fallback_start_py_ts: Optional[float] = None
    suppress_start_reclick = False

    def _poll_scan_start(allow_frame_fallback: bool) -> bool:
        nonlocal log_fp, pos, scan_buf, scan_origin_py_ts, fallback_start_py_ts

        prev_log_fp = log_fp
        (
            log_fp,
            pos,
            scan_buf,
            scan_origin_py_ts,
            fallback_start_py_ts,
            started,
            log_changed,
        ) = _poll_scan_start_from_logs(
            log_root=log_root,
            current_fp=log_fp,
            pos=pos,
            scan_buf=scan_buf,
            pre_log=pre_log,
            pre_log_size=pre_log_size,
            step_started_at=t0,
            start_keys=start_keys,
            scan_origin_py_ts=scan_origin_py_ts,
            fallback_start_py_ts=fallback_start_py_ts,
            allow_frame_fallback=allow_frame_fallback,
        )
        if log_changed and log_fp is not None and log_fp != prev_log_fp:
            print(f"[JENS] log_file={log_fp}")
        return started

    def _has_scan_start_marker() -> bool:
        return _scan_started_in_bytes(scan_buf, start_keys, allow_frame_fallback=False)

    def _has_valid_frame() -> bool:
        return _max_frame_in_bytes(scan_buf) > 0

    def _scan_start_confirmed() -> bool:
        return _has_scan_start_marker() and _has_valid_frame()

    def _is_scan_running_ui() -> bool:
        try:
            return bool(exists(stop_tpl))
        except Exception:
            return False

    def _suppress_start_clicks(message: str) -> None:
        nonlocal suppress_start_reclick, fallback_start_py_ts
        if not suppress_start_reclick:
            print(message)
        suppress_start_reclick = True
        if fallback_start_py_ts is None:
            fallback_start_py_ts = time.time()

    last_err: Optional[Exception] = None
    start_confirmed = False
    for attempt in range(1, start_btn_retry + 1):
        if attempt == 1:
            _poll_scan_start(allow_frame_fallback=True)
            if _scan_start_confirmed() and _is_scan_running_ui():
                _suppress_start_clicks("[JENS] scan_start marker and valid frame detected before initial start click")
                start_confirmed = True
                break
            if _has_scan_start_marker() and not _has_valid_frame():
                print("[JENS] scan_start marker detected before initial start click, but no valid frame; click start")

        _reset_mouse_hover(params, move_to, sleep)
        try:
            start_pos = wait(start_tpl, timeout=start_btn_timeout_sec)
            touch(start_pos)
            start_click_sent = True
            t0 = time.time()
            last_click_ts = t0
            print(f"[JENS] start button clicked attempt={attempt}/{start_btn_retry}")
        except Exception as e:
            last_err = e
            _poll_scan_start(allow_frame_fallback=True)
            if _scan_start_confirmed():
                print(
                    f"[JENS] scan_start marker and valid frame detected after start button miss "
                    f"attempt={attempt}/{start_btn_retry}"
                )
                start_confirmed = True
                break
            if start_click_sent and _is_scan_running_ui():
                print("[JENS] scan UI is running after start button miss, but marker/frame confirmation is incomplete")
            print(f"[JENS] start button click failed attempt={attempt}/{start_btn_retry}")
            continue

        confirm_deadline = time.time() + start_frame_wait_timeout_sec
        log_deadline = time.time() + wait_log_file_timeout_sec
        while time.time() < confirm_deadline:
            _poll_scan_start(allow_frame_fallback=True)
            if _scan_start_confirmed():
                print(
                    f"[JENS] scan_start marker and valid frame detected after start click "
                    f"attempt={attempt}/{start_btn_retry}"
                )
                start_confirmed = True
                break
            if log_fp is None and time.time() >= log_deadline:
                print(f"[JENS] scan_log not found after start click attempt={attempt}/{start_btn_retry}: {log_root}")
                break
            time.sleep(max(0.2, poll_interval_sec))

        if start_confirmed:
            break
        print(
            f"[JENS] scan_start marker and valid frame not both detected after start click "
            f"attempt={attempt}/{start_btn_retry}; retry start"
        )

    if not start_confirmed:
        raise RuntimeError(
            f"点击开始扫描 {start_btn_retry} 次后，仍未同时从日志检测到开始标记和有效 frame。"
        ) from last_err

    scan_started_log_dt, scan_start_line = _extract_start_event(scan_buf, start_keys)
    first_frame, first_frame_dt, last_frame_in_buf, last_frame_dt = _extract_frame_records(scan_buf)
    scan_started_dt = scan_started_log_dt or first_frame_dt
    start_frame = first_frame if first_frame is not None else 0
    if scan_started_dt is not None:
        print(f"[JENS] scan_start_log_time={scan_started_dt.isoformat(timespec='microseconds')}")
    scan_started_py_ts = scan_origin_py_ts or fallback_start_py_ts or time.time()
    system_samples: List[Tuple[float, float, float, float]] = []
    first_metrics = _sample_system_metrics(system_sampler_state, scan_started_py_ts)
    system_samples.append(
        (
            scan_started_py_ts,
            float(first_metrics["cpu_percent"]),
            float(first_metrics["memory_percent"]),
            float(first_metrics["wifi_rate_kbps"]),
        )
    )
    # 4) 等待 frame 达到阈值
    assert log_fp is not None
    slide_motion = SlideRailScanMotion(params)
    slide_motion.start()
    try:
        log_fp, max_frame, pos = _wait_frames_ge(
            log_root,
            log_fp,
            pos,
            target_frames,
            wait_frames_timeout_sec,
            frame_stall_timeout_sec,
            poll_interval_sec,
            stalled_log_switch_interval_sec,
            system_sampler_state=system_sampler_state,
            system_samples=system_samples,
        )
    finally:
        slide_motion.stop()
    frame_reach_source = "log"
    frame_reach_value = max_frame
    print(
        f"[JENS] reach target frames: {frame_reach_value} >= {target_frames} "
        f"source={frame_reach_source}"
    )

    # 5) 点击完成/停止扫描
    stop_pos = None
    try:
        stop_pos = exists(stop_tpl)
    except Exception:
        stop_pos = None
    if not stop_pos:
        stop_pos = wait(stop_tpl, timeout=_num(params, "stop_btn_timeout_sec", 10))
    log_fp, data, pos, switched = _read_live_scan_log(log_root, log_fp, pos)
    if switched and log_fp is not None:
        print(f"[JENS] log_file={log_fp}")
    stop_click_frame = max(max_frame, frame_reach_value)
    stop_click_log_dt: Optional[datetime] = last_frame_dt
    if data:
        stop_poll_ts = time.time()
        stop_metrics = _sample_system_metrics(system_sampler_state, stop_poll_ts)
        system_samples.append(
            (
                stop_poll_ts,
                float(stop_metrics["cpu_percent"]),
                float(stop_metrics["memory_percent"]),
                float(stop_metrics["wifi_rate_kbps"]),
            )
        )
        latest_frame = _max_frame_in_bytes(data)
        if latest_frame > max_frame:
            max_frame = latest_frame
            print(f"[JENS] frame={max_frame}")
        _, _, last_frame_after_target, last_frame_after_target_dt = _extract_frame_records(data)
        if last_frame_after_target is not None:
            stop_click_frame = last_frame_after_target
            stop_click_log_dt = last_frame_after_target_dt
        elif latest_frame > stop_click_frame:
            stop_click_frame = latest_frame

    if stop_click_log_dt is None and last_frame_in_buf is not None:
        stop_click_frame = last_frame_in_buf
        stop_click_log_dt = last_frame_dt

    stop_click_ts = time.time()
    elapsed_sec = max(0.0, stop_click_ts - scan_started_py_ts)
    frame_delta = max(0, stop_click_frame - start_frame)
    trend_by_second = _merge_trend_rows(system_samples, scan_started_py_ts)
    trend_summary = _summarize_trend_rows(trend_by_second)
    print(
        f"[JENS] elapsed_sec={elapsed_sec:.3f} stop_click_frame={stop_click_frame}"
    )
    for item in trend_by_second:
        print(
            f"[JENS] sys[{int(item['second'])}s] cpu={item['cpu_percent']:.3f}% "
            f"mem={item['memory_percent']:.3f}% wifi={item['wifi_rate_kbps']:.3f}kbps"
        )
    touch(stop_pos)

    # 6) 等待停止成功日志（任一标志命中即视为完成）
    log_fp, pos = _wait_log_contains(
        log_root, log_fp, pos, STOP_SUCCESS_KEYS, wait_stop_success_timeout_sec, poll_interval_sec
    )
    print("[JENS] stop success detected")
    return {
        "log_file": str(log_fp),
        "max_frame": max_frame,
        "target_frames": target_frames,
        "start_frame": start_frame,
        "stop_click_frame": stop_click_frame,
        "scan_elapsed_sec": round(elapsed_sec, 3),
        "frame_reach_source": frame_reach_source,
        "frame_reach_value": frame_reach_value,
        "trend_by_second": trend_by_second,
        "avg_cpu_percent": trend_summary["avg_cpu_percent"],
        "peak_cpu_percent": trend_summary["peak_cpu_percent"],
        "avg_memory_percent": trend_summary["avg_memory_percent"],
        "peak_memory_percent": trend_summary["peak_memory_percent"],
        "avg_wifi_rate_kbps": trend_summary["avg_wifi_rate_kbps"],
        "peak_wifi_rate_kbps": trend_summary["peak_wifi_rate_kbps"],
        "wifi_interface_name": wifi_interface_name,
        "slide_rail_scan_motion": slide_motion.to_extra(),
        "scan_started_log_at": (scan_started_dt.isoformat(timespec="microseconds") if scan_started_dt else ""),
        "stop_click_log_at": (stop_click_log_dt.isoformat(timespec="microseconds") if stop_click_log_dt else ""),
        "scan_start_log_line": scan_start_line or "",
    }
