# -*- coding: utf-8 -*-
"""
滑轨单步控制 step —— Mac 端通过网络控制 Windows 上的 motion_service 驱动 ECI1308 滑轨。

协议与 Windows 侧 motion_client / motion_service 完全一致：
  - TCP 连接 + 换行分隔 JSON：{"command": ..., "params": {...}}
  - 本文件为纯标准库实现，可在 Mac 上直接运行，无需额外依赖。

用法示例（在 case JSON 的 steps 中）：

  # 1) 单步脉冲（setp，与 Windows 控制台"单步脉冲"一致）
  {
    "id": "crealityscan.slide_rail_step",
    "version": "pyautogui-poc",
    "name": "滑轨单步右移",
    "params": {
      "host": "192.168.1.20",       # Windows 上 motion_service 的局域网 IP
      "port": 5000,
      "action": "step",             # step | move_relative | move_absolute | get_position |
                                    # set_soft_zero | reset_to_zero | connect_controller |
                                    # emergency_stop | switch_position
      "pulse": 10000,               # step/move_relative 的脉冲数（可正可负）
      "direction": "right",         # 可选 left/right，指定后覆盖 pulse 符号
      "connect_controller": true,   # 是否先确保控制器已连接（服务已连则幂等成功）
      "controller_ip": "192.168.0.11",
      "dll_path": "zauxdll.dll"
    }
  }

  # 2) 按位置 preset 换位（与 Windows 平台 slide_rail.switch_position 一致）
  {
    "id": "crealityscan.slide_rail_step",
    "version": "pyautogui-poc",
    "name": "滑轨换位-中物体",
    "params": {
      "host": "192.168.1.20",
      "port": 5000,
      "action": "switch_position",
      "preset": "中物体",           # 支持：小物体 | 中物体 | 人脸 | 大物体（或 key：small/medium/face/large）
      "connect_controller": true,
      "lift_bottom_safety_margin": 1.0,   # 下降到底的安全余量（秒），默认 1.0
      "reset_to_zero_first": false,       # 移动前是否先回软零点
      "lift_up_seconds_after_move": null  # 覆盖 preset 自带的上移秒数；null=用 preset 默认值，0=不上升
    }
  }
"""
from __future__ import annotations

import json
import os
import socket
from typing import Any, Dict, Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
BUFFER_SIZE = 4096
TIMEOUT_SEC = 180  # 覆盖最长移动时间 + 通信余量

# 滑轨位置预设（与 Windows steps/slide_rail/switch_position/v1_0_0/presets.json 保持一致）
# v1.3 起统一为负脉冲。大物体换位后默认上升 25 秒。
PRESETS: Dict[str, Dict[str, Any]] = {
    "small": {"name": "小物体", "position": -30000, "lift_up_seconds_after_move": 0},
    "medium": {"name": "中物体", "position": -170000, "lift_up_seconds_after_move": 0},
    "face": {"name": "人脸", "position": -370000, "lift_up_seconds_after_move": 0},
    "large": {"name": "大物体", "position": -580000, "lift_up_seconds_after_move": 25},
}

PRESET_ALIASES = {
    "小物体": "small", "小": "small",
    "中物体": "medium", "中": "medium",
    "人脸": "face",
    "大物体": "large", "人体": "large", "大": "large", "body": "large",
}


# ---------------------------------------------------------------------------
# 极简纯标准库 Socket 客户端（与 motion_service 协议一致）
# ---------------------------------------------------------------------------
class MotionSocketClient:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 timeout: float = TIMEOUT_SEC) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        response = self.send_command("test_connection")
        if response.get("status") != "success":
            self.close()
            raise RuntimeError(f"运动控制服务连通性检测失败: {response}")

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send_command(self, command: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if self.sock is None:
            raise RuntimeError("未连接到运动控制服务")
        request = {"command": command, "params": params or {}}
        self.sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        data = b""
        while True:
            chunk = self.sock.recv(BUFFER_SIZE)
            if not chunk:
                raise RuntimeError("连接已断开")
            data += chunk
            if b"\n" in data:
                break
        line = data.decode("utf-8").strip().split("\n")[0]
        return json.loads(line)

    def ensure_success(self, response: Any, action: str) -> Dict[str, Any]:
        if not isinstance(response, dict):
            raise RuntimeError(f"{action} 返回非对象结果: {response!r}")
        if response.get("status") != "success":
            raise RuntimeError(str(response.get("message") or response.get("error") or f"{action} 失败"))
        return response


# ---------------------------------------------------------------------------
# 参数解析工具
# ---------------------------------------------------------------------------
def _int(params: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        return int(default)


def _bool(params: Dict[str, Any], key: str, default: bool) -> bool:
    value = params.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _str(params: Dict[str, Any], key: str, default: str) -> str:
    value = params.get(key, default)
    return str(value).strip() if value is not None else str(default)


def _resolve_preset(value: Any) -> Dict[str, Any]:
    """把 preset 的 key/中文名/别名解析成预设配置。"""
    needle = str(value or "").strip()
    if not needle:
        raise ValueError("缺少 params.preset，请选择滑轨位置 preset（小物体/中物体/人脸/大物体）")
    key = PRESET_ALIASES.get(needle) or PRESET_ALIASES.get(needle.lower()) or needle.lower()
    preset = PRESETS.get(key)
    if preset is None:
        raise ValueError(f"未知滑轨位置 preset: {needle!r}（可选：小物体/中物体/人脸/大物体）")
    return {"key": key, **preset}


def _ensure_controller_connected(client: MotionSocketClient, params: Dict[str, Any]) -> None:
    if not _bool(params, "connect_controller", True):
        return
    client.ensure_success(
        client.send_command("connect", {
            "dll_path": _str(params, "dll_path", "zauxdll.dll") or "zauxdll.dll",
            "ip": _str(params, "controller_ip", "192.168.0.11") or "192.168.0.11",
        }),
        "连接滑轨控制器",
    )


# ---------------------------------------------------------------------------
# step 入口
# ---------------------------------------------------------------------------
def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    params = params if isinstance(params, dict) else {}

    host = _str(params, "host", os.environ.get("SLIDE_RAIL_HOST") or DEFAULT_HOST) or DEFAULT_HOST
    port = _int(params, "port", int(os.environ.get("SLIDE_RAIL_PORT") or DEFAULT_PORT))
    action = _str(params, "action", "step")
    pulse = _int(params, "pulse", 10000)
    direction = _str(params, "direction", "").lower()

    # direction 与 Windows 控制台"单步脉冲"语义一致：left=反向，right=正向
    if direction in ("left", "back", "backward", "-"):
        pulse = -abs(pulse)
    elif direction in ("right", "forward", "+"):
        pulse = abs(pulse)

    client = MotionSocketClient(host=host, port=port)
    try:
        client.connect()
        _ensure_controller_connected(client, params)

        result: Dict[str, Any] = {}
        if action in ("step", "move_relative"):
            resp = client.ensure_success(
                client.send_command("horizontal_move", {"pulse": pulse}),
                "滑轨单步移动",
            )
            result = {
                "action": action,
                "pulse": pulse,
                "direction": "left" if pulse < 0 else "right",
                "position": resp.get("position"),
                "relative_position": resp.get("relative_position"),
                "raw": resp,
            }
        elif action == "move_absolute":
            # 允许 preset 指定目标位置；否则用 pulse 作为绝对位置
            target = pulse
            preset = None
            if params.get("preset") not in (None, ""):
                preset = _resolve_preset(params.get("preset"))
                target = int(preset["position"])
            resp = client.ensure_success(
                client.send_command("horizontal_move_abs", {"position": target}),
                "滑轨绝对移动",
            )
            result = {
                "action": action,
                "preset": preset["key"] if preset else None,
                "position": resp.get("position"),
                "relative_position": resp.get("relative_position"),
                "raw": resp,
            }
        elif action == "switch_position":
            # 与 Windows steps/slide_rail/switch_position 语义一致：
            # 下降到底 -> 可选回软零点 -> 绝对移动到 preset 位置 -> 可选上升
            preset = _resolve_preset(params.get("preset"))
            target = int(preset["position"])
            lift_bottom_safety_margin = max(
                0.0, float(params.get("lift_bottom_safety_margin", 1.0) or 1.0))
            reset_to_zero_first = _bool(params, "reset_to_zero_first", False)
            override_lift = params.get("lift_up_seconds_after_move")
            lift_up_seconds = preset.get("lift_up_seconds_after_move", 0)
            if override_lift is not None and str(override_lift).strip() != "":
                lift_up_seconds = max(0.0, float(override_lift))

            client.ensure_success(
                client.send_command("lift_down_to_bottom", {"safety_margin": lift_bottom_safety_margin}),
                "升降台下降到底",
            )
            before = client.ensure_success(client.send_command("get_position"), "读取移动前位置")
            reset_result: Dict[str, Any] = {}
            if reset_to_zero_first:
                reset_result = client.ensure_success(
                    client.send_command("reset_to_zero"), "回软零点")

            move = client.ensure_success(
                client.send_command("horizontal_move_abs", {"position": target}),
                "移动到滑轨目标位置",
            )
            final = client.ensure_success(client.send_command("get_position"), "读取移动后位置")

            lift_up_result: Dict[str, Any] = {}
            if lift_up_seconds > 0:
                lift_up_result = client.ensure_success(
                    client.send_command("lift_up_duration", {"seconds": lift_up_seconds}),
                    "水平换位后升降台上升",
                )

            result = {
                "action": action,
                "preset": preset["key"],
                "preset_name": preset["name"],
                "target_position": target,
                "lift_bottom_safety_margin": lift_bottom_safety_margin,
                "lower_lift_result": {"status": "success"},
                "before_position": before,
                "reset_result": reset_result,
                "move_result": move,
                "final_position": final,
                "lift_up_seconds_after_move": lift_up_seconds,
                "lift_up_result": lift_up_result,
            }
        elif action == "get_position":
            resp = client.ensure_success(client.send_command("get_position"), "读取滑轨位置")
            result = {
                "action": action,
                "position": resp.get("position"),
                "relative_position": resp.get("relative_position"),
                "soft_zero": resp.get("soft_zero"),
                "raw": resp,
            }
        elif action == "set_soft_zero":
            resp = client.ensure_success(client.send_command("set_soft_zero"), "设置软零点")
            result = {"action": action, "soft_zero": resp.get("soft_zero"), "raw": resp}
        elif action == "reset_to_zero":
            resp = client.ensure_success(client.send_command("reset_to_zero"), "回软零点")
            result = {
                "action": action,
                "position": resp.get("position"),
                "relative_position": resp.get("relative_position"),
                "raw": resp,
            }
        elif action == "connect_controller":
            resp = client.ensure_success(
                client.send_command("connect", {
                    "dll_path": _str(params, "dll_path", "zauxdll.dll") or "zauxdll.dll",
                    "ip": _str(params, "controller_ip", "192.168.0.11") or "192.168.0.11",
                }),
                "连接滑轨控制器",
            )
            result = {"action": action, "message": resp.get("message"), "raw": resp}
        elif action == "emergency_stop":
            resp = client.ensure_success(client.send_command("emergency_stop"), "滑轨急停")
            result = {"action": action, "message": resp.get("message"), "raw": resp}
        else:
            raise ValueError(f"未知滑轨 action: {action!r}")

        result.setdefault("host", host)
        result.setdefault("port", port)
        return result
    finally:
        client.close()


if __name__ == "__main__":
    # 本地冒烟测试：
    #   python slide_rail.py --host 192.168.1.20 --action get_position
    #   python slide_rail.py --host 192.168.1.20 --action step --pulse 10000 --direction right
    #   python slide_rail.py --host 192.168.1.20 --action switch_position --preset 中物体
    import argparse

    parser = argparse.ArgumentParser(description="滑轨 step 冒烟测试")
    parser.add_argument("--host", default=os.environ.get("SLIDE_RAIL_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SLIDE_RAIL_PORT", DEFAULT_PORT)))
    parser.add_argument("--pulse", type=int, default=10000)
    parser.add_argument("--direction", default="")
    parser.add_argument("--preset", default="")
    parser.add_argument("--action", default="get_position")
    args = parser.parse_args()

    print(run({}, {
        "host": args.host,
        "port": args.port,
        "pulse": args.pulse,
        "direction": args.direction,
        "preset": args.preset,
        "action": args.action,
        "connect_controller": args.action in ("step", "move_relative", "move_absolute", "switch_position"),
    }))
