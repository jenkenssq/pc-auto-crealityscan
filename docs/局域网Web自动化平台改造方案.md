# Jens 局域网 Web 自动化平台改造方案

## 1. 文档目的

本文档用于规划 Jens PC 自动化测试平台的 Web 化改造。

本次改造不是把 Airtest 自动化放到服务器电脑执行，而是把现有系统拆分为：

- 集中部署在一台服务器电脑上的 Web 管理平台；
- 安装在每位用户 Windows 电脑上的精简执行 Agent；
- 用户通过局域网浏览器使用的任务编排和运行页面。

目标是让用户不再复制和维护完整项目，也不需要使用 Qt 页面。用户只需安装一次精简 Agent，之后通过账号密码登录网页，即可创建任务、选择任务、执行任务，并查看本机自动化任务的进度、日志和结果。

## 2. 已确认需求

根据当前沟通，已经确认以下需求：

- Web 服务集中部署在一台电脑上；
- 用户通过公司局域网访问 Web 页面；
- 每位用户通过自己的账号和密码登录；
- 用户在自己的 Windows 电脑上运行 CrealityScan；
- 用户电脑能够长期保持登录且不锁屏；
- 每位用户电脑安装精简 Agent，不再安装完整项目；
- 多位用户可以在各自电脑上同时执行自动化任务；
- 首版只有管理员和普通用户两个角色；
- 普通用户可以任意组合平台已经发布的 Step；
- 现有项目具备的任务编排功能都需要在网页中开放；
- 不需要从网页远程停止正在运行的任务；
- 不支持暂停后继续；
- Task JSON 继续作为标准任务格式；
- 普通用户可以查看和下载自己的原始 CrealityScan 日志；
- 系统运行在公司局域网内；
- 现有 Qt 平台继续保留，作为开发、维护和应急工具。

仍需确认的问题统一列在本文档第 19 节。

## 3. 可行性结论

该方案可以实现，并且现有 Airtest 执行体系可以继续复用。

准确的系统形态是：

> 中心 Web 控制平台 + 多用户本地执行 Agent

从用户操作层面看，相当于把 Qt 页面中的任务创建、步骤编排、任务选择、任务执行、运行输出和结果查看搬到网页上。

但 Qt 页面后面的 Airtest 执行能力不能全部搬到服务器。Airtest 必须操作用户电脑上的 CrealityScan，因此执行引擎、Airtest 依赖、Step 实现和模板资源必须以精简 Agent 的形式保留在用户本地。

用户不再需要项目源码目录，也不需要手动管理 `steps/`、`tasks/`、`cases/` 和运行命令。Agent 负责从服务器获取任务与受信任的 Step 资源并在本地执行。

## 4. 第一性原理与核心约束

### 4.1 自动化必须在用户本地执行

浏览器和中心服务器无法直接操作用户电脑上的 CrealityScan 窗口。

因此，任务执行链必须是：

```text
网页提交任务
    ↓
服务器把任务下发给当前用户绑定的 Agent
    ↓
Agent 在用户 Windows 会话中启动 Jens Runner
    ↓
Airtest 操作本机 CrealityScan
    ↓
Agent 将进度、日志和结果上传到服务器
```

### 4.2 用户电脑必须保持桌面可交互

任务运行期间，用户电脑必须满足：

- Windows 用户已经登录；
- 桌面未锁屏；
- CrealityScan 已启动且窗口可激活；
- 当前会话允许鼠标、键盘和截图操作；
- 分辨率和缩放比例符合 Step 要求；
- 扫描仪、驱动和相关硬件处于可用状态。

Agent 不应作为传统 Windows Service 直接执行 Airtest。Windows Service 通常位于 Session 0，无法可靠操作登录用户桌面。Agent 应运行在当前登录用户的交互会话中，可配置为登录后自动启动。

### 4.3 并发能力由用户执行机数量决定

每台用户电脑同一时间只能运行一个桌面自动化任务：

```text
单台 Agent 最大运行任务数 = 1
```

但不同用户的电脑彼此独立，因此可以并行执行：

```text
用户 A 电脑：任务 A 运行中
用户 B 电脑：任务 B 运行中
用户 C 电脑：任务 C 运行中
```

平台整体最大并发数约等于当前在线、空闲且环境正常的 Agent 数量。

### 4.4 服务器无需人工管理执行电脑，但必须感知 Agent

管理员不需要手工配置每台执行电脑，也不需要手工分配任务。

但是服务器必须自动记录以下最低状态：

- Agent 属于哪个用户；
- Agent 是否在线；
- Agent 是否空闲或正在执行；
- Agent 版本和 Step 资源版本；
- 当前任务和当前步骤；
- 最后心跳时间；
- CrealityScan 是否可用；
- 屏幕分辨率、缩放比例和磁盘空间是否符合要求。

这些状态用于自动路由任务和向用户解释为什么当前不能执行，不等同于要求管理员人工管理执行电脑。

## 5. 推荐总体架构

```text
                         公司局域网

┌────────────────────────────────────────────────────────────┐
│                     中心 Web 服务器                        │
│  FastAPI / 登录认证 / 用户管理 / Step 与 Task 库 / 数据库  │
│  Agent 连接 / 任务下发 / 事件汇总 / 日志与报告访问         │
└───────────────┬─────────────────┬─────────────────┬────────┘
                │                 │                 │
         HTTP + SSE         Agent 长连接      Agent 长连接
                │                 │                 │
        ┌───────▼──────┐  ┌──────▼───────┐  ┌──────▼───────┐
        │ 用户 A 浏览器 │  │ 用户 A Agent │  │ 用户 B Agent │
        │ 网页操作      │  │ 本地 Runner  │  │ 本地 Runner  │
        └──────────────┘  │ Airtest      │  │ Airtest      │
                          └──────┬───────┘  └──────┬───────┘
                                 ▼                 ▼
                          CrealityScan A    CrealityScan B
                          扫描仪 A          扫描仪 B
```

浏览器和 Agent 是两个不同客户端：

- 浏览器负责用户交互；
- Agent 负责本地执行；
- 两者通过同一个登录用户或一次性绑定关系关联；
- 浏览器关闭不影响已经开始的任务；
- Agent 断线会影响本机任务，但不会影响其他用户任务。

## 6. 部署边界

### 6.1 中心服务器部署内容

服务器保存和运行：

- Web 页面和 API；
- 用户账号、密码哈希和角色；
- Agent 注册、绑定、心跳和版本状态；
- Step 元数据和可信 Step 发布包；
- Task JSON 与任务版本；
- 用户任务提交和运行记录；
- 结构化步骤事件；
- 上传后的日志、截图和报告；
- Agent 安装包和升级包；
- 管理员维护页面和审计日志。

### 6.2 用户电脑部署内容

精简 Agent 至少包含：

- Agent 主程序和系统托盘状态；
- Airtest 及必要运行依赖；
- OCR、截图和设备相关依赖；
- Jens Runner 和执行引擎；
- Step 加载与执行能力；
- 当前任务需要的 Step 实现和模板缓存；
- 与服务器通信、心跳和断线重连能力；
- 本地执行锁；
- 本地日志和临时产物目录；
- Agent 与 Step 资源更新能力。

用户电脑仍需自行安装：

- CrealityScan；
- 扫描仪驱动；
- 相关硬件依赖。

### 6.3 用户电脑不再需要的内容

- 完整项目源码；
- Qt 日常操作页面；
- 完整任务库；
- 用户数据库；
- 管理员功能；
- 项目文档、测试代码和构建文件；
- 与当前任务无关的全部历史运行产物。

## 7. 现有项目能力复用

当前项目可以复用以下能力：

- `jens_platform/case_store.py`：Case、Task、Step 和失败策略数据模型；
- `jens_platform/task_generator.py`：标准开流、后处理任务生成器；
- `jens_platform/step_registry.py`：Step 元数据发现；
- `jens_platform/runner.py`：子进程启动、输出读取和停止逻辑；
- `engine/executor.py`：逐步骤执行、重试、失败截图和结果收集；
- `jens_runner_entry.py`：运行目录、Airtest 初始化、报告和结果归档；
- `steps/`：现有全部自动化能力；
- `tasks/`：现有 Task JSON 兼容格式；
- `artifacts/`：日志、截图、结果和报告结构。

需要新增或抽离的能力：

- Web 服务；
- 用户认证和权限；
- Agent 程序；
- Agent 绑定和心跳；
- 任务下发协议；
- Step 发布包和版本校验；
- 结构化运行事件；
- 日志与产物上传；
- Web 与 Agent 之间的状态恢复；
- Qt 和 Agent 共用的跨进程执行锁。

## 8. 推荐技术选型

### 8.1 中心 Web 服务

- Web 框架：FastAPI；
- ORM：SQLAlchemy；
- 数据迁移：Alembic；
- 数据校验：Pydantic；
- 密码哈希：Argon2；
- 服务进程：Uvicorn；
- 浏览器实时更新：SSE；
- Agent 通信：WebSocket；
- 首版数据库：SQLite WAL；
- 后续数据库：PostgreSQL。

Agent 主动连接服务器，可以避免在每位用户电脑上开放入站端口，也便于穿过公司电脑的本地防火墙策略。

### 8.2 Web 页面

首版建议使用：

- Jinja2 服务端模板；
- HTMX 处理任务列表、编排和运行状态更新；
- 少量原生 JavaScript 处理 SSE 日志流。

首版不建议立即使用 React 或 Vue。当前核心目标是替代 Qt 的操作入口并建立可靠的 Agent 执行链，复杂前端框架不会降低这一部分的风险。

### 8.3 Agent 打包

Agent 建议通过 PyInstaller 生成独立安装包，用户不需要安装 Python 或手工配置依赖。

Agent 分为两层：

1. 稳定的基础运行时：Agent、Airtest、Runner、执行引擎和通用依赖；
2. 可更新资源包：Step 实现、`step.json`、`presets.json` 和模板图片。

这样更新普通 Step 时，不需要让所有用户重新安装完整 Agent。

## 9. Agent 注册与用户绑定

推荐使用一次性绑定码：

1. 用户安装并启动 `Jens Agent`；
2. Agent 首次启动生成一个短时有效的六位绑定码；
3. 用户登录 Web 页面；
4. 用户在“我的执行端”页面输入绑定码；
5. 服务器将 Agent 绑定到当前账号；
6. Agent 保存服务器签发的设备令牌；
7. 后续任务自动下发到该用户绑定的 Agent。

Agent 设备令牌应保存在 Windows 用户配置目录中，并限制普通用户以外的进程读取。

如果首版规定一个账号只能绑定一台电脑，新绑定成功后应使旧 Agent 令牌失效。是否支持一个账号绑定多台 Agent，仍需确认。

## 10. Agent 生命周期和任务流程

### 10.1 Agent 启动

1. 用户登录 Windows 后 Agent 自动启动；
2. Agent 加载本地设备令牌；
3. Agent 连接中心服务器；
4. Agent 上报版本、系统环境和空闲状态；
5. Agent 执行 CrealityScan、分辨率、缩放比例和依赖自检；
6. Web 页面显示“在线且可运行”或明确的异常原因。

### 10.2 任务创建与执行

1. 用户登录网页；
2. 用户从现有 Step 中任意组合任务；
3. 服务器验证每个 `step_id + version` 和参数；
4. 用户点击执行；
5. 服务器确认该用户 Agent 在线、空闲且环境正常；
6. 服务器生成不可变 Task JSON 快照和资源清单；
7. Agent 下载缺失或版本不一致的可信 Step 资源；
8. Agent 校验资源哈希；
9. Agent 在本地启动现有 Jens Runner 子进程；
10. Agent 实时上传日志和结构化步骤事件；
11. 服务器通过 SSE 将状态推送到浏览器；
12. 任务结束后 Agent 上传结果、截图和报告；
13. Agent 恢复为空闲状态。

### 10.3 断线处理

- 浏览器断线：本地任务继续运行，重新打开页面后恢复显示；
- Agent 与服务器短暂断线：本地任务继续运行，事件先写入本地缓冲区；
- Agent 恢复连接：按事件序号补传日志和状态；
- Agent 长时间离线：服务器显示 Agent 离线，不把任务误判为成功；
- Web 服务重启：Agent 自动重连并上报当前运行状态。

## 11. 功能模块

### 11.1 用户和权限

首版角色固定为：

| 角色 | 权限 |
| --- | --- |
| 管理员 | 用户管理、Step 发布、Agent 安装包维护、查看全部运行状态和系统配置 |
| 普通用户 | 绑定自己的 Agent、创建和执行自己的任务、查看自己的日志与报告 |

首版认证能力：

- 用户名和密码登录；
- Argon2 密码哈希；
- 登录、退出和 Session 失效；
- 管理员创建、禁用和重置普通用户密码；
- 关键操作审计。

### 11.2 网页任务编排

网页应开放当前 Qt 已有的编排能力：

- 浏览和搜索所有已发布 Step；
- 任意选择和组合 Step；
- 调整执行顺序；
- 设置 Step 名称；
- 编辑 Step 参数；
- 选择 `presets.json` 中的 preset；
- 设置 `abort`、`continue` 和 `retry`；
- 使用现有标准任务生成器；
- 保存、复制、导入和导出 Task JSON；
- 执行前进行服务端校验。

普通用户可以组合管理员发布的 Step，但不建议允许普通用户上传或修改 Python Step 代码。Step 是会在用户电脑执行的受信任代码，发布权限应保留给管理员。

### 11.3 用户任务执行

当前需求不包含网页远程停止，也不支持暂停恢复。

任务状态建议定义为：

```text
dispatching   正在向 Agent 下发
starting      Agent 正在启动 Runner
running       正在执行
passed        执行成功
failed        执行失败
interrupted   Agent 或进程异常中断
```

运行中的任务一直执行到成功、失败或 Agent/Runner 异常退出。是否需要在 Agent 系统托盘中提供本地紧急停止按钮，可以后续单独确认。

### 11.4 实时进度和日志

当前 `execute_case()` 在任务结束后统一返回步骤结果。网页需要运行中的进度，因此执行引擎应增加兼容的结构化事件出口。

建议事件格式：

```json
{"seq":1,"event":"run_started","run_id":"123","total_steps":8}
{"seq":2,"event":"step_started","run_id":"123","step_index":3,"step_name":"预览扫描","attempt":1}
{"seq":3,"event":"step_retrying","run_id":"123","step_index":3,"attempt":2}
{"seq":4,"event":"step_finished","run_id":"123","step_index":3,"status":"passed","duration_sec":8.2}
{"seq":5,"event":"run_finished","run_id":"123","status":"passed"}
```

结构化事件用于计算当前步骤和完成进度。普通 `print()` 输出只用于日志窗口，不作为任务状态判据。

日志链路：

```text
Runner stdout/stderr
    ↓
Agent 本地日志文件和待上传缓冲区
    ↓ WebSocket
中心服务器日志文件
    ↓ SSE
用户浏览器日志窗口
```

日志窗口应支持自动滚动、断线续传、错误高亮、完整日志下载和浏览器最大显示行数限制。

### 11.5 运行明细和产物

普通用户可以查看和下载自己的：

- Task JSON 运行快照；
- 当前及最终步骤明细；
- `result.json`；
- `summary.json`；
- `report.html`；
- 失败截图；
- Runner 日志；
- 原始 CrealityScan 日志。

管理员是否可以查看所有用户的原始日志，需要在权限规则中明确。当前建议管理员可查看，以便维护和排障。

## 12. Step 发布与更新

为了减少用户电脑上的项目内容，Step 应由中心服务器统一发布，Agent 按需下载和缓存。

一个 Step 发布包至少包含：

```text
step.json
impl.py
presets.json（可选）
templates/（可选）
manifest.json
```

`manifest.json` 应记录：

- `step_id`；
- `version`；
- 文件清单；
- 每个文件的 SHA-256；
- 最低 Agent 版本；
- 发布时间；
- 发布者。

执行任务前，Agent 根据 Task JSON 中的 `step_id + version` 检查本地缓存。只有哈希匹配的受信任资源才能执行。

更新策略：

- 已运行任务始终使用任务快照指定的 Step 版本；
- 管理员发布新版本时不覆盖旧版本；
- Agent 只下载本次任务需要的版本；
- 无用缓存根据保留策略清理；
- Agent 基础运行时与 Step 资源分开升级。

## 13. 建议数据模型

### 13.1 users

| 字段 | 含义 |
| --- | --- |
| id | 用户 ID |
| username | 唯一用户名 |
| password_hash | Argon2 密码哈希 |
| role | `admin` 或 `user` |
| is_active | 是否启用 |
| created_at | 创建时间 |
| updated_at | 更新时间 |

### 13.2 agents

| 字段 | 含义 |
| --- | --- |
| id | Agent ID |
| user_id | 绑定用户 |
| name | 执行端名称 |
| device_token_hash | Agent 令牌哈希 |
| status | `offline/idle/running/error` |
| agent_version | Agent 版本 |
| environment_json | 分辨率、缩放、系统等环境信息 |
| current_run_id | 当前任务运行 ID |
| last_seen_at | 最后心跳时间 |
| bound_at | 绑定时间 |

### 13.3 tasks

| 字段 | 含义 |
| --- | --- |
| id | 任务 ID |
| owner_user_id | 任务所有者 |
| name | 任务名称 |
| definition_json | 当前 Task JSON |
| version | 乐观锁版本号 |
| is_active | 是否启用 |
| created_at | 创建时间 |
| updated_at | 更新时间 |

### 13.4 task_runs

| 字段 | 含义 |
| --- | --- |
| id | 运行 ID |
| task_id | 来源任务 ID |
| user_id | 发起用户 |
| agent_id | 实际执行 Agent |
| task_snapshot_json | 不可变 Task JSON 快照 |
| resource_manifest_json | 本次 Step 资源清单 |
| status | 运行状态 |
| current_step_index | 当前步骤 |
| total_steps | 总步骤数 |
| error_summary | 错误摘要 |
| submitted_at | 提交时间 |
| started_at | 开始时间 |
| finished_at | 结束时间 |

### 13.5 step_runs

| 字段 | 含义 |
| --- | --- |
| id | 步骤运行 ID |
| task_run_id | 所属运行 ID |
| step_index | 步骤序号 |
| step_id | Step ID |
| step_version | Step 版本 |
| step_name | 本次步骤名称 |
| status | 步骤状态 |
| attempt | 尝试次数 |
| duration_sec | 耗时 |
| screenshot_path | 失败截图 |
| extra_json | Step 返回明细 |
| error_text | 异常堆栈 |

### 13.6 run_events

保存带序号的结构化运行事件，用于浏览器刷新、Agent 重连和状态恢复。

### 13.7 artifacts

记录日志、截图、报告和原始 CrealityScan 日志的归属、路径、大小、哈希和上传状态。

### 13.8 step_packages

记录管理员发布的 Step 版本、文件清单、哈希、兼容 Agent 版本和启用状态。

### 13.9 audit_logs

记录登录、用户管理、Agent 绑定、任务修改、任务执行和 Step 发布等关键操作。

## 14. 建议通信接口

### 14.1 浏览器接口

```text
POST /auth/login
POST /auth/logout
GET  /auth/me

GET    /api/tasks
POST   /api/tasks
GET    /api/tasks/{task_id}
PUT    /api/tasks/{task_id}
POST   /api/tasks/{task_id}/clone
GET    /api/steps
GET    /api/steps/{step_id}/{version}/presets
POST   /api/task-generator/preview

GET  /api/my-agent
POST /api/my-agent/bind
POST /api/runs
GET  /api/runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
GET  /api/runs/{run_id}/artifacts
```

当前需求不提供运行中任务的远程停止接口。

### 14.2 Agent 接口

```text
POST /api/agent/register
POST /api/agent/bind-code
GET  /api/agent/packages/{package_id}
POST /api/agent/runs/{run_id}/artifacts
WS   /api/agent/connect
```

Agent WebSocket 消息至少包括：

- `hello`：身份、版本和环境；
- `heartbeat`：在线、空闲和当前运行状态；
- `run_offer`：服务器下发任务；
- `run_accepted`：Agent 接受任务；
- `run_rejected`：环境异常或正在运行；
- `run_event`：结构化进度；
- `log_chunk`：增量日志；
- `run_finished`：最终结果；
- `artifact_manifest`：运行产物清单。

所有任务和事件必须带 `run_id`、Agent 身份和递增序号，支持幂等重试，避免断线重发产生重复记录。

## 15. 安全要求

即使系统只在公司局域网内使用，也必须满足：

- 用户密码只保存 Argon2 哈希；
- Agent 令牌不可明文存入数据库；
- 登录接口限制连续失败次数；
- Cookie 设置 `HttpOnly`、`SameSite` 和合理有效期；
- 修改类网页请求启用 CSRF 防护；
- 普通用户只能访问自己的 Agent、任务、运行记录和产物；
- 任务 JSON 在服务器和 Agent 两侧分别校验；
- 普通用户只能组合已发布 Step，不能上传 Python 代码；
- Step 发布包必须校验版本和文件哈希；
- 日志显示进行 HTML 转义；
- 产物下载通过数据库 ID 定位，禁止接受任意文件路径；
- Agent 主动连接服务器，不在用户电脑开放控制端口；
- 记录管理员发布 Step 和用户执行任务等审计操作；
- Web 服务不得直接暴露到互联网。

公司局域网不等于绝对可信。条件允许时，仍建议使用内部域名和 HTTPS，避免账号、Agent 令牌和日志在网络中明文传输。

## 16. 与现有 Qt 平台的关系

Qt 平台继续保留，但不再是普通用户的主要入口。

推荐职责：

- Web 页面：普通用户日常创建和执行任务；
- Agent：普通用户电脑本地执行；
- Qt 平台：开发调试、Step 维护、本机应急和断网排障。

Qt、Agent 和现有 Runner 应复用同一套 CaseModel、Task Generator、Step Registry 和执行引擎。

每台电脑必须使用跨进程全局执行锁，确保以下入口不能同时操作 CrealityScan：

- Qt 启动的任务；
- Agent 接收的任务；
- 用户手动启动的 Runner。

复杂的新逻辑应放到独立服务模块，不应继续堆入 `jens_platform/main.py`。

## 17. 分阶段实施建议

### 第一阶段：单用户 Agent 闭环验证

- FastAPI 基础服务；
- 管理员和普通用户登录；
- 一个普通用户绑定一个 Agent；
- Agent 登录后自启动和心跳；
- Web 查看现有任务；
- Web 下发任务到当前用户 Agent；
- Agent 调用现有 Runner；
- 实时标准输出；
- 结构化当前步骤；
- 结果、截图和报告上传；
- 浏览器刷新后恢复运行状态。

### 第二阶段：网页完整替代 Qt 日常操作

- 全部 Step 浏览；
- 任意 Step 组合；
- preset 和参数编辑；
- 失败策略；
- 标准任务生成器；
- Task JSON 导入和导出；
- 任务复制和版本；
- 原始 CrealityScan 日志上传与下载；
- Agent 环境自检；
- Agent 与 Step 按需更新。

### 第三阶段：多用户正式运行

- 多 Agent 同时在线和并行执行；
- 用户数据隔离；
- 管理员用户数量和系统状态管理；
- Agent 断线续传；
- 服务重启状态恢复；
- 运行记录保留策略；
- 审计和磁盘空间管理；
- 内部 HTTPS 部署。

不建议第一阶段就一次性开发完整网页编排器和自动更新。应先验证最关键链路：服务器能否稳定把任务发到用户 Agent，并实时收到执行状态。

## 18. 首版验收标准

- 管理员可以创建、禁用和重置普通用户；
- 普通用户可以从局域网浏览器登录；
- 未登录用户无法访问任务和运行记录；
- 用户能够安装 Agent 并使用绑定码完成绑定；
- 网页能够准确显示 Agent 在线、空闲、运行中和异常状态；
- Agent 离线时网页拒绝启动任务并说明原因；
- 用户能在网页中组合当前平台已有 Step；
- 用户能导入和导出兼容的 Task JSON；
- 用户点击执行后，任务只发送到自己的 Agent；
- 同一 Agent 不会同时运行两个任务；
- 不同用户的 Agent 可以同时运行各自任务；
- 浏览器关闭或刷新不会中止任务；
- 页面能实时显示当前步骤、完成进度和日志；
- Agent 短暂断线后可以补传事件和日志；
- 任务结束后可以查看步骤明细、截图和报告；
- 普通用户只能查看和下载自己的产物；
- Step 资源版本和哈希不匹配时 Agent 拒绝执行；
- Qt 和 Agent 不能同时操作同一台电脑上的 CrealityScan。

## 19. 待确认问题

正式开发前仍需确认：

1. 是否可以确认每个普通用户都有独立的 Windows 电脑、CrealityScan 和扫描仪？
2. 一个账号只允许绑定一台 Agent，还是允许绑定多台电脑并在运行时选择？
3. 用户创建的 Task 仅自己可见，还是所有普通用户共享任务库？
4. “每个用户 20 条任务”是指最多保存 20 个任务定义，还是只保留最近 20 条运行记录？
5. 删除旧运行记录时，是否同时删除服务器和 Agent 本地的日志、截图与报告文件？
6. Agent 是否需要开机自动启动并常驻系统托盘？
7. Agent 是否需要提供只能在本机点击的紧急停止按钮？
8. 管理员是否可以查看所有用户的原始 CrealityScan 日志？
9. 中心服务器能否长期运行，并配置固定局域网 IP 或内部域名？

## 20. 当前推荐决策

在剩余问题确认前，建议按以下默认边界设计：

- 一台中心 Web 服务器；
- 每位用户一台独立 Windows 执行电脑和扫描设备；
- 一个普通用户绑定一台 Agent；
- 用户任务默认仅本人可见；
- 管理员可查看全部用户和运行状态；
- 普通用户可以任意组合已发布 Step，但不能上传 Step 代码；
- Agent 登录后自动启动并主动连接服务器；
- 每台 Agent 并发数固定为 1，多 Agent 可并行；
- Agent 基础运行时使用安装包，Step 资源按需下载；
- Task JSON 继续作为导入、导出和运行快照格式；
- 不提供网页远程停止和暂停恢复；
- 日志通过 Agent 缓冲、WebSocket 上传和 SSE 展示；
- 普通用户可以下载自己的完整日志和报告；
- 保留 Qt 作为开发、维护和应急入口；
- 中心数据库首版使用 SQLite WAL，日志正文保存为文件；
- 优先实现一个用户、一个 Agent、一个任务的最小闭环，再扩展多用户。

该架构能实现“项目集中维护、用户只安装精简执行端、所有操作通过网页完成”的目标，同时保留 Airtest 必须在用户本地桌面执行的技术事实。
