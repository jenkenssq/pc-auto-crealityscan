# 给 Mac 端 Agent 的改动提示词

> 把下面方框内的整段内容作为提示词发给负责 Mac 端的 Agent。
> 目标：让 Mac 自动化测试平台（mac_pyautogui_poc）能通过网络控制 Windows 上的滑轨服务，提供与 Windows 控制台一致的"单步脉冲（setp）"移动。

---

```
【任务】为 Mac 自动化测试平台添加"滑轨单步控制"能力

【背景】
- Windows 上已运行 motion_service.py（32 位 Python + zauxdll.dll），它通过 Socket
  驱动 ECI1308 滑轨控制器，监听 TCP 5000 端口（已改为监听 0.0.0.0，可从局域网访问）。
- 协议：TCP 连接 + 换行分隔 JSON。客户端发 {"command": "xxx", "params": {...}}，
  服务端回一行 JSON，字段含 status（"success"/"error"）。
- 平台项目位于 output/mac_pyautogui_poc/，是 PyAutoGUI 步骤化 runner：
  * steps/ 目录下每个 .py 暴露 run(ctx, params) -> dict
  * registry.py 里把 step id 映射到 run
- 关键命令（与 Windows 控制台"单步脉冲"完全一致）：
  * connect            -> 连接控制器，params: {"dll_path": "zauxdll.dll", "ip": "192.168.0.11"}，已连则幂等成功
  * horizontal_move    -> 相对移动，params: {"pulse": 12345}（正=右/负=左，含软限位保护+到位等待）
  * horizontal_move_abs-> 绝对移动，params: {"position": 12345}
  * get_position       -> 读取位置，返回 position/relative_position/soft_zero
  * set_soft_zero / reset_to_zero -> 设软零点 / 回软零点
  * emergency_stop     -> 急停

【要求】
1. 新建 output/mac_pyautogui_poc/steps/slide_rail.py，纯标准库（socket/json），
   实现一个 run(ctx, params) 函数和一个内部极简 Socket 客户端（TCP + 换行 JSON）。
   不得引入额外依赖，不得 import Windows 侧 motion_client（避免路径依赖）。
2. run 的 params 支持：
   - host（默认取环境变量 SLIDE_RAIL_HOST，否则 127.0.0.1）
   - port（默认取环境变量 SLIDE_RAIL_PORT，否则 5000）
   - action：step | move_relative | move_absolute | get_position |
              set_soft_zero | reset_to_zero | connect_controller | emergency_stop |
              switch_position（默认 step）
   - pulse：脉冲数（可正可负，默认 10000）
   - direction：left/right（可选，指定后覆盖 pulse 符号：left 取负、right 取正，与 Windows 控制台一致）
   - preset：位置预设（可选），与 Windows slide_rail.switch_position 的 presets.json 完全一致：
       小物体 small -30000 / 中物体 medium -170000 / 人脸 face -370000 /
       大物体 large -580000（换位后默认上升 25 秒）
     preset 用于 action=move_absolute（按 preset 绝对移动）或 action=switch_position（完整换位流程）
   - switch_position 流程（对齐 Windows）：
       下降到底 -> 可选回软零点 -> 绝对移动到 preset 位置 -> 按 preset 可选上升（大物体默认 25 秒）
     switch_position 专属参数：
       lift_bottom_safety_margin（默认 1.0，下降到底的安全余量）
       reset_to_zero_first（默认 false）
       lift_up_seconds_after_move（可选覆盖 preset 自带上移秒数；null=用 preset 默认，0=不上升）
   - connect_controller：bool（默认 true，先确保控制器已连接）
   - controller_ip（默认 192.168.0.11）、dll_path（默认 zauxdll.dll）
3. 每个命令要校验响应 status=="success"，否则抛 RuntimeError 并带出 message。
4. 返回值是 dict：至少包含 action、host、port 及该命令的位置/结果字段；失败必须抛异常，
   不要吞错误。连接用完必须 close（用 try/finally）。
5. preset 列表应内嵌在 slide_rail.py（可参考 presets.reference.json），无需额外文件。
6. 在 output/mac_pyautogui_poc/registry.py 注册：
   from .steps import slide_rail  （加入现有 from .steps import ... 那行）
   STEP_REGISTRY 增加 "crealityscan.slide_rail_step": slide_rail.run
7. 自测（可离线验证）：在本机起一个临时 TCP mock 服务，模拟上面协议，
   用 resolve_step("crealityscan.slide_rail_step") 跑通：
   step/right -> pulse 为正；step/left -> pulse 为负；get_position / move_absolute /
   emergency_stop 各跑一次；switch_position + preset（如"中物体"、大物体）验证绝对位置与
   大物体默认上升 25 秒、以及 lift_up_seconds_after_move=0 覆盖；
   未知 action / 未知 preset 必须抛 ValueError。
8. 验证后清理临时 mock 服务，删除测试脚本，只保留正式代码改动。

【验收】
- python -m py_compile 三个文件通过；
- 用 mock 服务离线跑通上述自测清单；
- 提示里说明真实联调时：Windows 上确保 motion_service 已启动、防火墙已放行 5000、
  Mac 能 ping 通 Windows 局域网 IP。
```

---

### 参考实现（可直接作为答案或对照）

`output/mac_pyautogui_poc/steps/slide_rail.py` 和 `registry.py` 的改动已在本仓库完成，
可直接拷贝参考（含 `if __name__ == "__main__"` 的冒烟测试入口）。Mac 端 Agent 若无法访问
本仓库，可按提示词自行实现；核心协议与字段以提示词第【背景】为准。
