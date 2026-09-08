# 数据模型与 API 契约

## 1. 设计原则

- 数据库是用户、任务、绑定关系和服务器运行记录的权威来源；
- 每次运行保存不可变 Task JSON 和 Step 资源快照；
- 共享任务的可见性与修改权限分离；
- 普通用户只能访问自己的 Run 和 Artifact；
- Agent 事件必须幂等；
- 日志正文和大文件保存在文件系统，数据库保存元数据和索引；
- 每用户最近20条记录的清理必须事务化并可审计。

## 2. 实体关系

```text
User 1 ─── 0..1 Agent
User 1 ─── * Task（创建者）
Task 1 ─── * TaskRun
User 1 ─── * TaskRun（发起者）
Agent 1 ─── * TaskRun（执行端）
TaskRun 1 ─── * StepRun
TaskRun 1 ─── * RunEvent
TaskRun 1 ─── * Artifact
StepPackage * ─── * TaskRun（通过资源快照关联）
```

## 3. 核心数据表

### 3.1 users

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | UUID | 主键 |
| username | String | 唯一、不可为空 |
| password_hash | String | Argon2 哈希 |
| role | Enum | `admin` / `user` |
| is_active | Boolean | 默认 true |
| password_changed_at | DateTime | 密码修改时间 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

删除用户前必须处理其任务所有权。首版建议禁用用户优先于物理删除。

### 3.2 agents

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | UUID | 主键 |
| user_id | UUID | 唯一外键，保证一账号一 Agent |
| display_name | String | 默认使用主机名 |
| device_token_hash | String | 不保存明文令牌 |
| status | Enum | `offline/idle/preparing/running/uploading/error` |
| agent_version | String | Agent 版本 |
| protocol_version | Integer | 通信协议版本 |
| environment_json | JSON | OS、屏幕、缩放和磁盘摘要 |
| current_run_id | UUID? | 当前 Run |
| last_seen_at | DateTime | 最后心跳 |
| bound_at | DateTime | 绑定时间 |
| revoked_at | DateTime? | 令牌吊销时间 |

数据库对有效绑定增加 `user_id` 唯一约束。解绑时吊销令牌，不能只清空页面状态。

### 3.3 agent_binding_codes

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | UUID | 主键 |
| code_hash | String | 不保存绑定码明文 |
| agent_fingerprint | String | Agent 临时标识 |
| expires_at | DateTime | 短时有效 |
| consumed_at | DateTime? | 使用后失效 |
| created_at | DateTime | 创建时间 |

### 3.4 tasks

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | UUID | 主键 |
| owner_user_id | UUID | 创建者/所有者 |
| name | String | 任务名称 |
| description | String | 可选说明 |
| definition_json | JSON | 当前 Task JSON |
| revision | Integer | 乐观锁版本号 |
| is_active | Boolean | 默认 true |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

权限规则：

- 登录用户可读取全部有效任务；
- 登录用户可执行和复制全部有效任务；
- 普通用户只能更新或删除 `owner_user_id == current_user.id` 的任务；
- 管理员可更新或删除全部任务；
- 删除采用软删除时，已有 Run 快照不受影响。

### 3.5 task_runs

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | UUID | 主键 |
| task_id | UUID? | 来源任务，可在任务删除后保留空引用 |
| user_id | UUID | 发起用户 |
| agent_id | UUID | 执行 Agent |
| task_name_snapshot | String | 运行时名称 |
| task_snapshot_json | JSON | 不可变任务快照 |
| resource_manifest_json | JSON | Step 包版本和哈希 |
| status | Enum | Run 状态 |
| current_step_index | Integer? | 当前步骤 |
| total_steps | Integer | 总步骤数 |
| last_event_seq | Integer | 已保存最大事件序号 |
| last_heartbeat_at | DateTime? | 最近一次心跳时间；用于 running 态超时收敛 |
| error_code | String? | 机器可读错误码 |
| error_summary | String? | 用户可读摘要 |
| submitted_at | DateTime | 提交时间 |
| started_at | DateTime? | 开始时间 |
| finished_at | DateTime? | 结束时间 |
| cleanup_at | DateTime? | 服务器清理时间 |

### 3.6 step_runs

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID | 主键 |
| task_run_id | UUID | 所属 Run |
| step_index | Integer | 步骤序号 |
| step_id | String | Step ID |
| step_version | String | Step 版本 |
| step_name | String | 快照名称 |
| status | Enum | 等待、执行中、重试、通过、失败等 |
| attempt | Integer | 尝试次数 |
| duration_sec | Decimal? | 耗时 |
| extra_json | JSON? | Step 返回数据 |
| error_text | Text? | 异常堆栈 |
| started_at | DateTime? | 开始时间 |
| finished_at | DateTime? | 结束时间 |

对 `(task_run_id, step_index)` 建立唯一约束，重试更新同一步明细并保留 attempt。

### 3.7 run_events

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID | 主键 |
| task_run_id | UUID | 所属 Run |
| seq | Integer | Run 内递增序号 |
| event_type | String | 事件类型 |
| payload_json | JSON | 事件数据 |
| agent_sent_at | DateTime | Agent 发送时间 |
| received_at | DateTime | 服务器接收时间 |

对 `(task_run_id, seq)` 建立唯一约束，实现补传去重。

### 3.8 artifacts

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID | 主键 |
| task_run_id | UUID | 所属 Run |
| artifact_type | Enum | report/result/screenshot/log/crealityscan_log 等 |
| display_name | String | 页面显示名 |
| storage_path | String | 服务器内部相对路径 |
| size_bytes | Integer | 文件大小 |
| sha256 | String | 完整性校验 |
| uploaded_at | DateTime | 上传完成时间 |

禁止将客户端提供的绝对路径直接写入 `storage_path`。

### 3.9 step_packages

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID | 主键 |
| step_id | String | Step ID |
| version | String | Step 版本 |
| package_sha256 | String | 包哈希 |
| manifest_json | JSON | 文件清单和哈希 |
| min_agent_version | String | 最低 Agent 版本 |
| is_active | Boolean | 是否可用于新任务 |
| published_by | UUID | 管理员 |
| published_at | DateTime | 发布时间 |

对 `(step_id, version)` 建立唯一约束，同版本禁止覆盖。

### 3.10 audit_logs

记录：

- 登录成功与失败；
- 用户创建、禁用和密码重置；
- Agent 绑定、解绑和令牌吊销；
- 任务创建、复制、修改和删除；
- Run 提交和本地停止结果；
- Step 发布、启用和停用；
- 运行记录清理。

## 4. Run 状态机

```text
dispatching
  ├─ agent_rejected
  └─ starting
       ├─ failed
       └─ running
            ├─ passed
            ├─ failed
            ├─ stopped_local
            └─ interrupted
```

终态：

```text
agent_rejected
passed
failed
stopped_local
interrupted
```

禁止把 `stopped_local` 或 `interrupted` 转为 `passed`。重复终态事件只能幂等确认，不能改变已确认的不同终态。

### 4.1 心跳超时收敛（suspected → interrupted）

- `starting` / `running` 态的 Run 关联 Agent 心跳超时（`task_runs.last_heartbeat_at` 超过心跳窗口，默认 30 秒）时，页面将 Run 显示为 `suspected`（疑似中断），不落库为终态；
- `suspected` 期间 Agent 重连并证明同一 `run_id` 仍在执行（上报 `state=running` + `current_run_id`，或续传 `seq` 事件）→ 恢复 `running`，清除 suspected；
- `suspected` 持续超过 `suspected_timeout`（默认 5 分钟，建议可配置）仍无有效心跳 → 收敛为终态 `interrupted`；
- 收敛为 `interrupted` 后按终态处理，不可再恢复；Agent 后续上报同一 Run 的事件按幂等规则丢弃或记警告；
- 收敛判定使用 Run 自身 `last_heartbeat_at` 而非 `agents.last_seen_at`，避免 Agent 在线但 Run 停滞造成误判；
- 该机制只收敛服务器侧状态，不影响 Agent 本地继续执行与补传；Agent 重连后若发现服务器已将该 Run 收敛为 `interrupted`，应停止本地执行并释放执行锁。

## 5. 浏览器 API

### 5.1 认证

```text
POST /auth/login
POST /auth/logout
GET  /auth/me
PUT  /auth/password
```

### 5.2 任务

```text
GET    /api/tasks
POST   /api/tasks
GET    /api/tasks/{task_id}
PUT    /api/tasks/{task_id}
DELETE /api/tasks/{task_id}
POST   /api/tasks/{task_id}/clone
POST   /api/tasks/import
GET    /api/tasks/{task_id}/export
```

更新任务请求必须携带 `revision`。版本冲突返回 `409 Conflict`。

### 5.3 Step 与生成器

```text
GET  /api/steps
GET  /api/steps/{step_id}/{version}
GET  /api/steps/{step_id}/{version}/presets
POST /api/task-generator/preview
```

### 5.4 我的 Agent

```text
GET    /api/my-agent
POST   /api/my-agent/bind
DELETE /api/my-agent/binding
GET    /api/agent-installer
```

### 5.5 Run

```text
POST /api/runs
GET  /api/runs
GET  /api/runs/current
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
GET  /api/runs/{run_id}/artifacts
GET  /api/artifacts/{artifact_id}/download
```

首版不存在网页 `stop` 或 `pause` API。

## 6. 管理员 API

```text
GET    /api/admin/users
POST   /api/admin/users
PUT    /api/admin/users/{user_id}
POST   /api/admin/users/{user_id}/reset-password
POST   /api/admin/users/{user_id}/disable

GET    /api/admin/tasks
PUT    /api/admin/tasks/{task_id}
DELETE /api/admin/tasks/{task_id}

GET    /api/admin/agents/summary
GET    /api/admin/runs/summary

GET    /api/admin/step-packages
POST   /api/admin/step-packages
POST   /api/admin/step-packages/{package_id}/activate
POST   /api/admin/step-packages/{package_id}/deactivate
```

管理员 Run 摘要接口不返回普通用户原始 CrealityScan 日志内容或下载地址。

## 7. Agent API

```text
POST /api/agent/binding-code
POST /api/agent/token/refresh
GET  /api/agent/packages/{package_id}
POST /api/agent/runs/{run_id}/artifacts/init
PUT  /api/agent/runs/{run_id}/artifacts/{artifact_id}
POST /api/agent/runs/{run_id}/artifacts/complete
WS   /api/agent/connect
```

Agent 身份与浏览器 Session 完全分离，Agent API 不接受浏览器 Cookie 代替设备令牌。

### 7.1 产物路径清洗

Agent 上传 `summary.json` / `result.json` 前必须剥离其中的绝对路径字段（`report_path`、`result_path`、截图绝对路径等），只保留相对文件名与 `run_id` 引用；服务器入库时二次校验，发现绝对路径字段一律清除。

页面展示与下载统一通过 `GET /api/artifacts/{artifact_id}/download` 按 Run/用户归属鉴权，不暴露服务器文件系统路径；`artifacts.storage_path` 只保存服务器内部相对路径。

## 8. 标准错误格式

```json
{
  "error": {
    "code": "AGENT_OFFLINE",
    "message": "执行端当前离线，请在用户电脑启动 Jens Agent。",
    "details": {}
  }
}
```

建议错误码：

```text
AUTH_INVALID
AUTH_DISABLED
FORBIDDEN
TASK_NOT_FOUND
TASK_REVISION_CONFLICT
AGENT_NOT_BOUND
AGENT_OFFLINE
AGENT_BUSY
AGENT_ENVIRONMENT_ERROR
STEP_VERSION_UNAVAILABLE
ARTIFACT_NOT_FOUND
RUN_RETENTION_EXPIRED
```

## 9. 每用户20条清理规则

清理时机：Run 到达终态且服务器端 Artifact 处理完成后。

算法：

1. 按当前 `user_id` 查询所有终态 Run；
2. 按 `finished_at DESC, id DESC` 排序；
3. 保留前20条；
4. 对超额记录先标记 `cleanup_at`；
5. 删除服务器 Artifact 文件；
6. 删除或归档关联事件和步骤明细；
7. 删除 Run 元数据或保留最小审计墓碑；
8. 记录清理审计；
9. 不向 Agent 发送本地删除命令。

运行中和未完成上传的 Run 不参与清理。

