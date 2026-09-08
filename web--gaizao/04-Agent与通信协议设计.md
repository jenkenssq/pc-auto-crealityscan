# Agent 与通信协议设计

## 1. Agent 定位

Jens Agent 是用户电脑上的精简执行端。它不是远程桌面工具，也不是完整 Qt 平台。

Agent 的唯一核心职责是：接收当前绑定用户的任务，在本地交互桌面中安全地调用现有 Runner，并把状态和产物传回中心服务器。

## 2. Agent 进程结构

```text
Agent 小窗口
├─ 绑定与连接状态
├─ 环境检查
├─ 当前任务
├─ 紧急停止按钮
└─ 快捷键设置

Agent Core
├─ Auth Client
├─ WebSocket Client
├─ Heartbeat
├─ Package Manager
├─ Environment Checker
├─ Execution Lock
├─ Runner Supervisor
├─ Event/Log Buffer
└─ Artifact Uploader
```

首版 Agent 由用户双击启动。关闭 Agent 小窗口是否退出进程必须清晰：推荐关闭按钮提示“退出 Agent 将中断连接”，不默认隐藏到托盘。

## 3. 本地目录建议

```text
%LOCALAPPDATA%/JensAgent/
├─ config/
│  ├─ agent.json
│  └─ shortcuts.json
├─ runtime/
├─ step-cache/
│  └─ <step_id>/<version>/
├─ runs/
│  └─ <run_id>/
├─ pending-events/
├─ logs/
└─ updates/
```

设备令牌应使用 Windows 用户级安全存储能力保护，不在日志或页面中输出完整值。

## 4. Agent 状态机

```text
unbound
  → binding
  → connecting
  → idle
  → preparing
  → running
  → uploading
  → idle

任意连接态 → offline
任意执行准备态 → error
running → stopping_local → stopped_local → uploading → idle
```

状态含义：

| 状态 | 含义 |
| --- | --- |
| unbound | 未绑定用户 |
| connecting | 正在连接服务器 |
| offline | 无法连接服务器 |
| idle | 在线且可接收任务 |
| preparing | 校验任务、下载资源和环境检查 |
| running | Runner 正在执行 |
| uploading | 正在上传最终产物 |
| error | 无法执行，需要用户处理 |
| stopping_local | 用户在本机触发紧急停止 |

## 5. 环境检查

任务开始前至少检查：

- Windows 当前会话可交互；
- 本地执行锁可获取；
- CrealityScan 进程和目标窗口存在；
- 屏幕分辨率；
- Windows 缩放比例；
- Airtest 和 OCR 运行依赖；
- Task 引用的 Step 包完整且哈希正确；
- 日志目录可读；
- 运行目录可写；
- 磁盘剩余空间达到最低阈值。

环境检查失败时 Agent 拒绝任务，返回具体错误码和用户可执行的处理建议，不启动 Runner。

## 6. 本地执行锁

Agent、Qt 和手动 Runner 必须使用同一个跨进程锁。

锁记录建议包含：

- owner 类型；
- 进程 ID；
- 开始时间；
- run_id 或本地任务标识。

发现锁存在时先检查持有进程是否仍存活。不得仅根据陈旧锁文件永久阻塞执行。

## 7. Runner 监督

Agent 启动 Runner 时：

- 使用独立子进程；
- 设置明确工作目录和环境变量；
- 捕获标准输出和标准错误；
- 记录进程 ID；
- 实时写本地日志；
- 解析结构化事件通道；
- 进程异常退出时保留退出码和最后输出；
- 无论结果如何都释放执行锁。

Agent 不应根据普通日志文本推断 Step 成功。步骤状态必须来自执行引擎结构化事件。

## 8. 本地紧急停止

### 8.1 按钮

- 仅在 `running` 时可用；
- 按钮使用明确的停止图标和“紧急停止”文字；
- 点击后显示二次确认，包含当前任务名称；
- 确认后立即进入 `stopping_local`，阻止重复触发；
- 先调用温和终止；
- 超过配置宽限期仍未退出则强制结束；
- 保存已有日志和产物；
- 最终状态固定为 `stopped_local`。

### 8.2 全局快捷键

- 默认关闭；
- 用户可在 Agent 小窗口启用；
- 用户可以修改组合键；
- 禁止单键和常用系统组合；
- 注册失败或冲突时不能显示为已启用；
- 触发后弹出本地确认或明显反馈；
- 快捷键设置只保存在本机，不由网页远程更改。

首版建议默认候选组合为 `Ctrl+Alt+Shift+F12`，但在未完成冲突验证前保持关闭。

## 9. 通信方式

### 9.1 浏览器

- HTTP/HTTPS：页面和普通 API；
- SSE：当前 Run 的结构化事件和日志展示。

### 9.2 Agent

- HTTPS：绑定、Step 包下载和 Artifact 上传；
- WebSocket：认证后长连接、心跳、任务下发和实时事件。

Agent 主动连接中心服务器，不在用户电脑监听远程控制端口。

### 9.3 服务器地址与首次引导

- Agent 配置中心服务器地址优先使用稳定主机名或内部域名（如 `https://jens-server.corp.local`），不写死 IP；地址保存在 `%LOCALAPPDATA%/JensAgent/config/agent.json`；
- 首次启动：Agent 处于未配置状态，打开地址与绑定界面，要求输入中心服务器地址和绑定码，校验可达性与协议版本兼容后持久化；
- 安装包可内置管理员填写的默认地址（便于快速部署），但以首次引导输入为准，用户可随时重新配置；
- 不使用 mDNS/广播自动发现：Windows 局域网环境可靠性不足且扩大攻击面，首版采用“人工配置一次 + 主机名 + 退避重连”。

### 9.4 断线重连与地址变更

- 连接断开后按指数退避重连（建议 2s 起、每轮 ×2、上限 60s）并加入随机抖动，避免多 Agent 同时风暴；网络恢复后自动重连，无需人工干预；
- 重连成功流程：重新认证 → 再次 `hello` → 按第 12 节从 `last_acked_seq + 1` 补传 pending-events → 上报本地状态（`idle`/`running` + `current_run_id`）；
- 配置为主机名时：DNS 更新后按退避自动重连即可，不要求人工重配；
- 配置为 IP 且持续连接失败：退避重试；超过连续失败阈值（建议 10 分钟）后进入 `offline`，小窗口提示“服务器地址不可达”，并提供“重新配置地址”入口；
- 服务器地址变更不要求首版自动发现或重定向，由管理员通过 Agent 重新配置入口解决。

## 10. 消息信封

所有 WebSocket 消息使用统一信封：

```json
{
  "protocol_version": 1,
  "message_id": "uuid",
  "type": "run_event",
  "agent_id": "agent-uuid",
  "run_id": "run-uuid",
  "seq": 42,
  "sent_at": "2026-07-30T10:00:00.000+08:00",
  "payload": {}
}
```

规则：

- `message_id` 用于消息幂等；
- Run 内事件使用递增 `seq`；
- 时间使用带时区 ISO 8601；
- 未知消息类型不得导致 Agent 崩溃；
- 协议版本不兼容时明确拒绝并提示升级。

## 11. 主要消息

### hello

Agent 连接后上报：

```json
{
  "agent_version": "1.0.0",
  "hostname": "SCAN-PC-01",
  "os_version": "Windows 11",
  "screen": {"width": 1920, "height": 1080, "scale": 100},
  "state": "idle",
  "current_run_id": null
}
```

### heartbeat

- 建议每10秒发送；
- 服务器超过30秒未收到则显示离线；
- 包含状态、当前 run_id、磁盘空间和环境摘要。

### run_offer

服务器下发：

- Run ID；
- Task JSON 快照；
- Step 资源清单；
- 事件协议版本；
- Artifact 上传地址和限制。

### run_accepted / run_rejected

Agent 必须明确接受或拒绝。拒绝使用具体错误码，例如：

```text
AGENT_BUSY
CREALITYSCAN_NOT_RUNNING
WINDOW_NOT_FOUND
EXECUTION_LOCKED
SCREEN_UNSUPPORTED
STEP_PACKAGE_INVALID
DISK_SPACE_LOW
```

### run_event

事件包括：

```text
run_started
step_started
step_retrying
step_finished
run_finished
run_failed
run_stopped_local
```

### log_chunk

包含来源、编码、起始偏移、结束偏移和文本。日志块可重发，服务器按偏移去重。

### artifact_manifest

任务结束后先上报文件名、类型、大小和 SHA-256，再通过 HTTPS 上传。服务器只接受当前 Run 允许的文件类型和大小。

## 12. 断线与补传

- Agent 将未确认事件追加写入本地持久化队列；
- 服务器确认已保存的最大 `seq`；
- Agent 重连后从 `last_acked_seq + 1` 开始补传；
- 日志使用文件偏移补传；
- 浏览器是否在线不影响 Agent 上传；
- 服务器重启后 Agent 自动重新认证；
- 同一 Run 的重复事件必须幂等处理。

## 13. Step 包管理

Agent 根据 `step_id + version + package_hash` 判断缓存是否可用。

下载流程：

1. 下载到临时目录；
2. 校验包级和文件级 SHA-256；
3. 校验 manifest 与 Agent 版本；
4. 原子移动到版本缓存目录；
5. 只读使用该版本执行本次 Run；
6. 下载或校验失败时拒绝执行。

管理员发布的新版本不能改变已经存在的相同版本内容。

## 14. 本地产物策略

Agent 本地产物不受服务器“最近20条”清理规则控制。

首版：

- Agent 保留本地所有运行目录；
- 页面不承诺远程删除本地文件；
- 服务器删除旧记录时不发送删除指令；
- 本地磁盘不足由 Agent 环境检查提示用户自行处理。

