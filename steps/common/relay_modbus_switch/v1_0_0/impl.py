from __future__ import annotations

import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple


def _as_int(params: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except Exception:
        return int(default)


def _as_float(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except Exception:
        return float(default)


def _as_bool(params: Dict[str, Any], key: str, default: bool) -> bool:
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


def _to_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _crc16_modbus(payload: bytes) -> int:
    crc = 0xFFFF
    for b in payload:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def _append_crc(payload: bytes) -> bytes:
    crc = _crc16_modbus(payload)
    return payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def _crc_ok(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    actual = frame[-2] | (frame[-1] << 8)
    expected = _crc16_modbus(frame[:-2])
    return actual == expected


def _build_write_single_coil(device_addr: int, channel: int, on: bool) -> bytes:
    reg_addr = channel - 1
    data = 0xFF00 if on else 0x0000
    payload = bytes(
        [
            device_addr & 0xFF,
            0x05,
            (reg_addr >> 8) & 0xFF,
            reg_addr & 0xFF,
            (data >> 8) & 0xFF,
            data & 0xFF,
        ]
    )
    return _append_crc(payload)


def _build_read_coils(device_addr: int, channels_count: int) -> bytes:
    payload = bytes(
        [
            device_addr & 0xFF,
            0x01,
            0x00,
            0x00,
            (channels_count >> 8) & 0xFF,
            channels_count & 0xFF,
        ]
    )
    return _append_crc(payload)


def _read_exact(ser: Any, n: int, timeout_sec: float) -> bytes:
    deadline = time.time() + max(0.1, timeout_sec)
    buf = bytearray()
    while len(buf) < n and time.time() < deadline:
        chunk = ser.read(n - len(buf))
        if chunk:
            buf.extend(chunk)
            continue
        time.sleep(0.01)
    if len(buf) < n:
        raise RuntimeError(f"串口读取超时：期望 {n} 字节，实际 {len(buf)} 字节")
    return bytes(buf)


def _transceive(ser: Any, req: bytes, resp_len: int, timeout_sec: float) -> bytes:
    try:
        ser.reset_input_buffer()
    except Exception:
        pass
    ser.write(req)
    ser.flush()
    return _read_exact(ser, resp_len, timeout_sec)


def _validate_write_response(resp: bytes, req: bytes, device_addr: int) -> None:
    if len(resp) != 8:
        raise RuntimeError(f"写线圈回包长度异常：{len(resp)}")
    if not _crc_ok(resp):
        raise RuntimeError(f"写线圈回包 CRC 错误：{_to_hex(resp)}")
    if resp[0] != (device_addr & 0xFF) or resp[1] != 0x05:
        raise RuntimeError(f"写线圈回包地址/功能码异常：{_to_hex(resp)}")
    if resp[:6] != req[:6]:
        raise RuntimeError(f"写线圈回包与请求不一致：req={_to_hex(req)} resp={_to_hex(resp)}")


def _parse_read_coils_response(resp: bytes, device_addr: int, channels_count: int) -> List[bool]:
    if len(resp) < 5:
        raise RuntimeError(f"读线圈回包长度过短：{_to_hex(resp)}")
    if not _crc_ok(resp):
        raise RuntimeError(f"读线圈回包 CRC 错误：{_to_hex(resp)}")
    if resp[0] != (device_addr & 0xFF) or resp[1] != 0x01:
        raise RuntimeError(f"读线圈回包地址/功能码异常：{_to_hex(resp)}")

    byte_count = int(resp[2])
    expected_len = 3 + byte_count + 2
    if len(resp) != expected_len:
        raise RuntimeError(f"读线圈回包长度不匹配：expect={expected_len}, got={len(resp)}")

    data = resp[3 : 3 + byte_count]
    states: List[bool] = []
    for i in range(channels_count):
        data_byte = data[i // 8]
        bit = (data_byte >> (i % 8)) & 0x01
        states.append(bool(bit))
    return states


def _sleep_if_needed(sec: float) -> None:
    if sec > 0:
        time.sleep(sec)


def _run_once(params: Dict[str, Any]) -> Dict[str, Any]:
    action = str(params.get("action") or "cycle").strip().lower()
    if action not in {"on", "off", "cycle"}:
        raise ValueError(f"不支持的 action: {action!r}，仅支持 on/off/cycle")

    device_addr = _as_int(params, "device_addr", 1)
    channel = _as_int(params, "channel", 1)
    channels_count = _as_int(params, "channels_count", 4)
    baudrate = _as_int(params, "baudrate", 9600)
    timeout_sec = _as_float(params, "timeout_sec", 1.0)
    off_duration_sec = _as_float(params, "off_duration_sec", 2.0)
    settle_after_on_sec = _as_float(params, "settle_after_on_sec", 3.0)
    verify = _as_bool(params, "verify", True)
    dry_run = _as_bool(params, "dry_run", False)

    port = str(params.get("port") or "").strip() or str(os.environ.get("JENS_RELAY_PORT") or "").strip()

    if not (1 <= device_addr <= 247):
        raise ValueError(f"device_addr 越界：{device_addr}（合法范围 1..247）")
    if not (1 <= channel <= 32):
        raise ValueError(f"channel 越界：{channel}（合法范围 1..32）")
    if channels_count < channel:
        raise ValueError(f"channels_count({channels_count}) 不能小于 channel({channel})")
    if channels_count < 1 or channels_count > 32:
        raise ValueError(f"channels_count 越界：{channels_count}（合法范围 1..32）")

    planned_ops: List[Tuple[str, bool, float]] = []
    if action == "on":
        planned_ops = [("on", True, settle_after_on_sec)]
    elif action == "off":
        planned_ops = [("off", False, 0.0)]
    else:
        planned_ops = [("off", False, off_duration_sec), ("on", True, settle_after_on_sec)]

    if dry_run:
        return {
            "dry_run": True,
            "port": port,
            "baudrate": baudrate,
            "device_addr": device_addr,
            "channel": channel,
            "action": action,
            "planned_ops": [
                {"name": name, "target_on": target_on, "sleep_after_sec": round(wait_sec, 3)}
                for name, target_on, wait_sec in planned_ops
            ],
        }

    if not port:
        raise RuntimeError("未配置串口：请在 params.port 或环境变量 JENS_RELAY_PORT 中提供串口号")

    try:
        import serial  # type: ignore
    except Exception as e:
        raise RuntimeError("未安装 pyserial。请先执行：python -m pip install pyserial") from e

    trace: List[Dict[str, Any]] = []
    read_req = _build_read_coils(device_addr, channels_count)
    read_resp_len = 3 + int(math.ceil(channels_count / 8.0)) + 2

    with serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout_sec,
        write_timeout=timeout_sec,
    ) as ser:
        final_states: Optional[List[bool]] = None
        for op_name, target_on, wait_sec in planned_ops:
            req = _build_write_single_coil(device_addr, channel, target_on)
            resp = _transceive(ser, req, 8, timeout_sec)
            _validate_write_response(resp, req, device_addr)
            item: Dict[str, Any] = {
                "op": op_name,
                "target_on": target_on,
                "write_req_hex": _to_hex(req),
                "write_resp_hex": _to_hex(resp),
            }

            if verify:
                read_resp = _transceive(ser, read_req, read_resp_len, timeout_sec)
                states = _parse_read_coils_response(read_resp, device_addr, channels_count)
                item["read_req_hex"] = _to_hex(read_req)
                item["read_resp_hex"] = _to_hex(read_resp)
                item["states"] = [1 if x else 0 for x in states]
                if states[channel - 1] != target_on:
                    raise RuntimeError(
                        f"继电器状态校验失败：channel={channel}, expect={int(target_on)}, got={int(states[channel - 1])}"
                    )
                final_states = states

            trace.append(item)
            _sleep_if_needed(wait_sec)

        if final_states is None and verify:
            read_resp = _transceive(ser, read_req, read_resp_len, timeout_sec)
            final_states = _parse_read_coils_response(read_resp, device_addr, channels_count)

    return {
        "dry_run": False,
        "port": port,
        "baudrate": baudrate,
        "device_addr": device_addr,
        "channel": channel,
        "action": action,
        "verify": verify,
        "trace": trace,
        "final_states": [1 if x else 0 for x in final_states] if final_states is not None else [],
    }


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    retry_count = _as_int(params, "retry_count", 2)
    retry_interval_sec = _as_float(params, "retry_interval_sec", 0.5)
    if retry_count < 0:
        retry_count = 0

    last_error: Optional[Exception] = None
    for attempt in range(1, retry_count + 2):
        try:
            result = _run_once(params)
            result["attempt"] = attempt
            return result
        except Exception as e:
            last_error = e
            if attempt >= retry_count + 1:
                break
            time.sleep(max(0.0, retry_interval_sec))

    raise RuntimeError(
        f"继电器步骤执行失败（retries={retry_count}）：{last_error or 'unknown error'}"
    ) from last_error
