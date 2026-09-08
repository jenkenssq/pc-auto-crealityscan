# Jens 扫描软件自动化测试平台

Jens 是一个面向 Windows 版 CrealityScan 的桌面 UI 自动化测试平台。项目使用 Airtest 执行 UI 与图像识别动作，使用 JSON 编排可复用 Step，通过 PyQt5 平台管理任务队列、运行过程、设备信息和测试报告。

当前已形成桌面端完整闭环：

```text
Step 步骤库 -> Case/Task JSON 编排 -> Runner 串行执行 -> Artifacts 归档与 HTML 报告
                          ^
                          |
                 PyQt5 桌面管理平台
```

> 当前可用形态是本地 Qt 桌面平台。局域网 Web 平台和本地精简 Agent 目前只有设计文档，尚未实现账号登录、网页编排或远程任务下发。

## 1. 核心能力

- 自动发现版本化 Step，支持参数编辑、preset 选择和拖拽编排。
- 创建、编辑、删除 Task，并持久化任务队列及拖拽顺序。
- 支持从指定步骤开始运行，不修改原 Task。
- 使用独立 Runner 子进程串行执行任务，实时显示输出，支持按钮或 `F4` 停止。
- 每步执行前激活目标窗口；失败时自动截图，支持 `abort`、`continue`、`retry`。
- 从 CrealityScan 日志提取模组、SN、连接方式和固件版本。
- 对预览、扫描停止和点云模式切换执行日志驱动的完成判定。
- 采集扫描帧数、SDK/UI FPS、CPU、内存等指标，生成 JSON 结果和 HTML 报告。
- 支持任务失败和队列完成邮件通知。
- 支持压测模式：同一任务循环 N 轮，失败/卡死自动杀进程重开、处理日志上报弹窗（点取消），生成压测汇总报告并邮件通知。
- 支持将部分 Airtest `.air` 脚本转换为 Step。
- 源码态支持滑轨服务、独立控制台、位置 preset 和扫描联动。

## 2. 运行环境

### 2.1 必要条件

- Windows。
- 已安装并能正常运行 CrealityScan。
- Python 3；当前目录版构建产物使用 Python 3.11。
- CrealityScan 窗口保持可见，不要最小化。
- 单显示器，推荐 `1920 x 1080`、系统缩放 `100%`。
- 关闭 CrealityScan 全屏显示，运行期间不要改变窗口布局或操作被测软件。

模板截图和大量坐标基于 `1920 x 1080`。分辨率、缩放、软件 UI 或主题变化都可能使模板匹配或坐标点击失效。

### 2.2 安装依赖

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-ui.txt
```

执行依赖包括 `airtest`、`pyserial`、`mss`、`rapidocr-onnxruntime`；桌面平台依赖 `PyQt5`。

## 3. 快速开始

### 3.1 启动桌面平台

先打开 CrealityScan，再在项目根目录执行：

```powershell
python platform_app.py
```

首次启动且未保存收件邮箱时，平台会打开邮件设置窗口。建议按以下顺序使用：

1. 确认或选择 CrealityScan 日志目录。
2. 点击“刷新设备”，检查模组、SN、连接方式和固件版本。
3. 从任务库选择任务并加入主界面队列。
4. 拖拽调整顺序；调试时可选择“起始步骤”。
5. 点击“运行队列”。
6. 在“运行输出”和“步骤结果”查看过程与结果。
7. 执行结束后打开报告或本次产物目录。

运行期间可点击“停止”或按 `F4`。Runner 先请求子进程退出，2 秒后仍未结束则强制终止。

### 3.2 命令行运行 Case 或 Task

```powershell
python platform_app.py --run-case cases/example_case.json
python platform_app.py --run-case "tasks/Ferret开流.json"
```

也可使用 Airtest CLI：

```powershell
$env:JENS_CASE_PATH = (Resolve-Path "cases/example_case.json")
python -m airtest.cli run "jens_runner.air" --log "artifacts/_airtest_cli_log"
```

成功返回退出码 `0`，失败返回 `1`。Runner 会打印 `run_dir`、`report` 和最终状态。

## 4. 系统架构

| 层级 | 主要模块 | 职责 |
| --- | --- | --- |
| 桌面平台 | `platform_app.py`、`jens_platform/` | 步骤编排、任务管理、队列调度、设备识别、结果展示 |
| Runner | `jens_runner_entry.py`、`jens_runner_helper.py`、`jens_runner.air/` | 初始化 Airtest、创建运行目录、汇总结果 |
| 执行引擎 | `engine/` | 动态加载 Step、失败策略、窗口激活、日志分析、报告生成 |
| 自动化资产 | `steps/`、`cases/`、`tasks/` | Step、模板/preset、用例和任务编排 |
| 外设控制 | `滑轨/`、`steps/slide_rail/` | 滑轨服务、客户端、控制台和位置 Step |
| 运行产物 | `artifacts/` | JSON 结果、HTML 报告、截图、日志和失败现场 |

执行链路：

```text
Qt 任务队列
  -> QProcess 启动 platform_app.py --run-case 或 jens_runner_helper.exe
  -> jens_runner_entry.run_case()
  -> engine.executor.execute_case()
  -> 动态加载 steps.<step_id>.v<version>.impl.run()
  -> result.json + summary.json + report.html
```

`jens_runtime.py` 统一处理源码态与 PyInstaller 安装态路径。可写数据使用程序所在目录，内置资源可从 PyInstaller 的 `_internal` 目录加载。

## 5. Step、Case 与 Task

### 5.1 Step 插件

标准目录：

```text
steps/<domain>/<step_name>/v1_0_0/
├─ __init__.py
├─ step.json
├─ impl.py
├─ presets.json       # 可选
└─ templates/         # 可选
```

映射示例：

```text
id: crealityscan.import_project
version: 1.0.0
module: steps.crealityscan.import_project.v1_0_0.impl
entry: run(ctx, params)
```

`step.json` 至少需要非空的 `id`、`name` 和 `version`。平台扫描 `steps/**/step.json`，无效元数据会被跳过。

`run(ctx, params)` 中，`ctx` 包含 `case`、`run_dir`、`step_index` 和 `env`；`params` 来自当前编排。Step 应抛出明确异常，由引擎统一截图、重试和记录。

### 5.2 Case JSON

Case 默认保存在 `cases/`：

```json
{
  "case_id": "example_case",
  "name": "示例用例",
  "app": {
    "window_title_contains": "CrealityScan",
    "device_uri": "Windows:///",
    "log_dir": "C:\\Users\\...\\CrealityScan\\Logs"
  },
  "keywords": ["Traceback", "Exception", "ERROR", "失败", "崩溃"],
  "steps": [
    {
      "id": "common.activate_window",
      "version": "1.0.0",
      "name": "激活/置顶窗口",
      "params": {},
      "on_fail": {"action": "abort"}
    }
  ]
}
```

`on_fail.action` 支持：

- `abort`：失败后终止任务。
- `continue`：记录失败并继续。
- `retry`：按 `max_retries` 和 `retry_wait_sec` 重试。

“从指定步骤开始”会在 `cases/_generated/` 生成带 `run_options.start_step_index` 的临时 JSON。此前步骤记为 `skipped`，原 Task 不变。完整规范见 [docs/步骤与用例JSON规范.md](docs/步骤与用例JSON规范.md)。

### 5.3 Task JSON

Task 与 Case 使用相同结构，但默认位于 `tasks/`，用于任务库和批量队列。主界面只展示已加入队列的任务，队列状态保存在 `tasks/_queue.json`。

当前任务库与生成器覆盖模组：

- Ferret（文件名沿用 `feeret`）、Otter、Otter Lite、Otter Lite Basic、P1、Pika、Raptor、Raptor X、Raptor Pro、S1、X1：`tasks/` 下已提交开流/后处理任务（含 USB/Wi-Fi 与 `-滑轨` 变体）。
- P1S：已接入任务生成器，`tasks/` 下当前无提交任务文件。
- Pika：Wi-Fi/USB 开流和后处理，生成时自动插入稳定性等待步骤。

`tasks/1.json`、`tasks/2.json`、`tasks/演示任务.json` 是示例或调试任务，不属于标准全量任务。

任务生成器配置在 `jens_platform/task_generator.py`，当前支持（12 个模组）：

```text
feeret, otter, otter lite, otter lite basic, P1, P1S, pika,
raptor, raptor x, raptor pro, S1, X1
```

P1S 和 Pika 已接入生成器。其中 Pika 任务会自动插入稳定性等待步骤；`raptor`/`raptor x`/`raptor pro` 生成的“开流”任务不含“激活/置顶窗口”；P1、P1S、Pika、raptor x、raptor pro、S1、X1 支持 USB/Wi-Fi 连接方式过滤。新任务以生成器为准，手工 `tasks/*.json` 仅作样本或现场调试使用。

任务类型支持三种：`开流`、`后处理`、`帧率统计`。其中 `帧率统计`（`TASK_KIND_FPS_STAT`）在第二步勾选「帧率统计任务」即自动按业务顺序挑选模式（平行线/单线/交叉/无标记点[仅USB]/大/中/小物体[几何]/人脸/人体[纹理]），第三步自动选中「帧率统计」并固定 1000 帧；每模式执行“预览 → 等待5s → 扫描至 1000 帧”（预览后自动插入 `common.sleep` 5s，用于稳定采集预览帧率）；其中“无标记点”在 P1/P1S 等机型会按“交叉线/平行线”拆成两行（`无标记点-交叉线`、`无标记点-平行线`），单一种类的机型仍为单个 `无标记点`；Pika 的“有标志点”线激光按 标准/均衡/快速 各占一行。运行结束后由 `engine/fps_stat_xlsx.py` 按 `帧率统计模板.xlsx` 写入 A1:H3（WIFI→G 列、USB→H 列，回填不破坏另一列），帧率数值保留整数（去掉小数、不做四舍五入）。

## 6. 标准扫描流程

普通开流参数块：

```text
扫描参数 -> 预览扫描 -> 扫描至目标帧并完成
```

普通后处理参数块：

```text
扫描参数 -> 预览扫描 -> 扫描至目标帧并完成 -> 融合 -> 封装 -> 贴图
```

框架点后处理参数块：

```text
扫描参数 -> 预览 -> 开始扫描并暂停 -> 切点云并等待新流就绪
         -> 预览 -> 扫描至目标帧并完成 -> 融合 -> 封装 -> 贴图
```

每个参数块结束后，在下一块开始前插入“新建扫描”；最后一个参数块后不插入。

## 7. 扫描参数 preset

当前有 12 个模组参数 Step：

| 模组 | Step ID | preset 数 |
| --- | --- | ---: |
| Ferret | `crealityscan.configure_scan_params_ferret` | 23 |
| Otter | `crealityscan.configure_scan_params_otter` | 26 |
| Otter Lite | `crealityscan.configure_scan_params_otter_lite` | 20 |
| Otter Lite Basic | `crealityscan.configure_scan_params_otter_lite_basic` | 20 |
| P1 | `crealityscan.configure_scan_params_p1` | 23 |
| P1S | `crealityscan.configure_scan_params_p1s` | 23 |
| Pika | `crealityscan.configure_scan_params_pika` | 21 |
| Raptor | `crealityscan.configure_scan_params_raptor` | 19 |
| Raptor X | `crealityscan.configure_scan_params_raptor_x` | 22 |
| Raptor Pro | `crealityscan.configure_scan_params_raptor_pro` | 21 |
| S1 | `crealityscan.configure_scan_params_s1` | 26 |
| X1 | `crealityscan.configure_scan_params_x1` | 24 |

preset 可用 `key`、中文 `name` 或 `aliases` 引用。平台读取步骤版本目录中的 `presets.json` 并显示选择窗口。

### 7.1 P1S 当前配置

P1S 使用独立 Step `crealityscan.configure_scan_params_p1s` 和 `p1s.*` key。当前 23 个 preset 包括：

- 线激光点云：交叉线、平行线、单线（3）。
- 线激光框架点：开启贴图、关闭贴图（2）。
- 线激光无标记点：交叉线、平行线（2）。
- 散斑小物体、中物体：几何/纹理，各含快速和高精度（8）。
- 散斑大物体：几何、纹理（2）。
- 散斑人脸：几何/纹理，各含快速和高精度（4）。
- 散斑人体：几何、纹理（2）。

合计 23 个。P1S 已接入任务生成器（`jens_platform/task_generator.py`），默认按全部 23 个 preset 生成开流/后处理任务；`tasks/` 下当前没有提交 P1S 任务文件。修改 P1S `presets.json` 后，需用生成器重新生成对应任务并校验引用。

## 8. 日志驱动判定

多个步骤通过读取 CrealityScan `scan_log` 增量判断真实状态。运行前应设置 `app.log_dir`；未配置时部分步骤会回退到当前 Windows 用户的默认日志目录。

- `crealityscan.preview_scan`：匹配预览成功日志后返回。
- `crealityscan.scan_until_frames_then_stop`：确认扫描开始和有效帧，等待帧数达标，点击完成后继续等待停止成功标志（`OB_SCAN_MESSAGE_ID_SCANNING_STOP_SUCCESS` 或 `stop progress 1.000000`，任一命中即完成）。
- `crealityscan.pause_switch_point_cloud_scan`：严格按顺序等待，每个位置命中其任一候选即推进：

```text
（标定框架优化成功，二选一）
  OB_SCAN_MESSAGE_ID_MARKER_FRAMEWORK_OPTIMIZATION_SUCCESS   # 旧固件
  marker_opt progress 1.000000                               # Sermoon S1 等新固件（优化进度 100%）
obscan_scan_reconfig_scan_mode_config
scan_type: OB_SCAN_CLOUD_FUSED
start stream done.
config property ex done.
```

全部匹配后再执行默认 1 秒的 `ready_stable_sec` 稳定等待。`scan_type: OB_SCAN_CLOUD_FUSED` 只代表配置已写入，不能单独判定 UI 就绪；未点击预览时底层流也可能产生点云，所以不使用 `total_points_num:`。

`crealityscan.create_scan` 当前只执行原有点击动作，不做日志关键字匹配。

## 9. 结果与报告

每次运行创建：

```text
artifacts/<任务名>_<YYYYMMDD_HHMMSS>/
├─ airtest/
├─ screenshots/
├─ logs/crealityscan/
├─ result.json
├─ summary.json
└─ report.html
```

- 成功任务会清理部分重型临时产物。
- 失败任务尽量保留截图、Airtest 明细和 CrealityScan 日志。
- `result.json` 记录步骤状态、耗时、尝试次数、错误和扩展指标。
- 报告包含设备信息、关键词命中、步骤明细及可用的 FPS/CPU/内存趋势。
- 双击“步骤结果”中的截图路径可打开产物。

默认日志关键词定义在 `engine/defaults.py`：`Traceback`、`Exception`、`ERROR`、`失败`、`崩溃`。

## 10. 滑轨支持

源码态启动独立控制台：

```powershell
python slide_rail_app.py
```

主平台启动时尝试在 `127.0.0.1:5000` 自动启动 `滑轨/motion_service.py`，控制器仍需单独连接。当前默认控制器 IP 为 `192.168.0.11`，DLL 为 `zauxdll.dll`。

`slide_rail.switch_position` preset：

| preset | 位置（脉冲） |
| --- | ---: |
| 小物体 | -30000 |
| 中物体 | -170000 |
| 人脸 | -370000 |
| 大物体/人体 | -580000 |

“大物体/人体”换位后默认上升 25 秒；其余 preset 无上升动作。位置均为负脉冲，与 v1.3 统一后的 `presets.json` 一致。

位置日志默认写入 `run_dir/slide_rail_position_logs/`。`scan_until_frames_then_stop` 默认允许滑轨扫描联动；只有服务和控制器在线才执行，否则自动跳过。

> 当前 `jens_pc_build.spec` 未打包 `滑轨/` 及 DLL。滑轨目前应以源码态使用；安装版支持前需补打包配置并完成硬件验收。

## 11. 邮件通知

收件邮箱保存在 `config/notification_settings.json`。SMTP 从项目或安装目录下的 `.env` 读取。

必填：

```dotenv
JENS_SMTP_HOST=
JENS_SMTP_PORT=
JENS_SMTP_USER=
JENS_SMTP_PASSWORD=
```

可选：

```dotenv
JENS_SMTP_USE_SSL=
JENS_SMTP_USE_STARTTLS=
JENS_SMTP_TIMEOUT_SEC=8
```

平台支持任务失败和队列完成通知。`.env` 已加入 `.gitignore`，通常包含凭证，不应提交；打包前必须确认构建机上的 `.env` 适合分发。

## 12. 压测模式

用于对 CrealityScan 执行“同一任务反复 N 轮”的稳定性压测。每轮独立归档，
失败/卡死自动**强杀进程 → 重开软件 → 处理“软件意外退出”上报弹窗（点取消）→ 进入下一轮**。

### 12.1 入口

- 界面：顶栏 **压测模式** 按钮 → 选择任务（`tasks/` 单选）+ `CrealityScan.exe` + 执行次数。
- 命令行：

  ```powershell
  python platform_app.py --stress-run ^
    --case "tasks/Raptor Pro无标志点50次后处理压测.json" ^
    --exe "C:/Program Files/Creality/CrealityScan.exe" ^
    --rounds 50
  ```

### 12.2 行为约定

- 选中任务完整跑一遍 = 1 轮；轮末由执行器自动 `return_home`，任务 JSON 不内嵌。
- 普通失败或卡死：本轮记失败（截图+日志+报告）→ 强杀进程树 → 重开 → 下一轮。
- 卡死判定：CrealityScan 日志无新行 + 轮次进程无心跳，静默超过 `--freeze-timeout`
  （默认 180s）才判卡死。
- “软件意外退出”上报弹窗点 **取消**：pywinauto 按钮“取消/Cancel”优先，
  Airtest 模板 `jens_platform/stress/templates/cancel_btn.png` 兜底，找不到则截图留证。
- 中途可停止：当前轮完整跑完后不再启动下一轮（停止不打断当前轮），并照常生成
  汇总报告（标记“已停止”）。

### 12.3 产物

```text
artifacts/<任务名>_压测_<时间戳>/
├─ 压测汇总.json
├─ 压测汇总.html
├─ round01/ ... roundNN/      # 每轮独立 result.json + report.html + 截图/日志
```

汇总字段与统计口径、通知、默认参数见 `docs/平台压测模式方案/压测模式使用说明.md`。

## 13. 导入 Airtest .air

“导入.air”会解析旧脚本，生成 Step 目录、`step.json`、`impl.py` 和模板资源。当前主要支持 `touch`、`wait`、`swipe`、`sleep`、`Template`。

导入后仍需检查坐标、模板阈值、超时、异常信息和日志就绪条件。转换成功不等于 Step 已通过稳定性验收。

## 14. 目录结构

```text
.
├─ platform_app.py            # Qt 入口，也支持 --run-case
├─ slide_rail_app.py          # 滑轨控制台入口
├─ jens_runner_entry.py       # Runner 主逻辑
├─ jens_runner_helper.py      # 安装态 Runner
├─ jens_runtime.py            # 源码态/安装态路径
├─ engine/                    # 执行、日志、窗口、报告、IO、压测编排
├─ jens_platform/             # Qt UI、任务、通知、Step 导入、压测弹窗
├─ jens_platform/stress/      # 压测模板（取消按钮 cancel_btn.png）
├─ jens_runner.air/           # Airtest CLI 入口
├─ steps/                     # 版本化 Step 库
├─ cases/                     # Case；含 user/ 和 _generated/
├─ tasks/                     # Task 库和 _queue.json
├─ 滑轨/                      # 服务、客户端、UI、DLL
├─ tests/                     # 单元测试
├─ docs/                      # 项目文档
├─ web--gaizao/               # Web + Agent 设计，仅文档
├─ 用例仓库/                  # 历史 .air 素材
├─ build_assets/              # 打包资源
├─ build/                     # PyInstaller 中间产物
├─ 安装程序/                  # 当前目录版输出
├─ config/                    # 通知配置
└─ artifacts/                 # 运行时生成，Git 忽略
```

当前平台可发现 40 个有效 Step：`common` 3 个、`crealityscan` 27 个、`slide_rail` 1 个、`tool.calibration_score` 1 个（读取标定分数）、`tool.firmware_upgrade` 2 个（固件开流、固件升级）、`tool.postprocess_compare` 6 个（贴图、高斯渲染、AI重贴图、人体补全、导入工程、返回首页）。

其中 `tool.calibration_score.read`、`tool.firmware_upgrade.stream`、`tool.firmware_upgrade.upgrade` 分别沉淀自 `工具/标定分数查看工具`、`工具/固件升级工具`：标定分数读取为自包含实现；固件开流/升级 Step 复用源工具实现，运行时从 `工具/固件升级工具`（或环境变量 `JENS_FIRMWARE_UPGRADE_ROOT`）加载配置与核心模块。

`steps/crealityscan/set_scan_params_speckle_medium_geometry` 已清空 `id/version`，属于废弃 Step，不会被发现。

## 15. 打包

安装 PyInstaller 后构建 one-folder 目录版：

```powershell
python -m pip install pyinstaller
python build.py          # 自动探测 dist 最高版本并 +1（如 v0.3 -> v0.4）
python build.py 0.4      # 或手动指定版本
python build.py --no-tools   # 不附带侧边栏工具
```

`build.py` 调用 PyInstaller 构建，并将产物自动命名为 `dist/jens_pc_app_vX.Y/`，版本号同时写入两个 exe 的 Windows 文件版本资源（右键 exe → 属性 → 详细信息可见）。版本递增规则：次版本 +1，`v0.9` 进位到 `v1.0`。

默认会把 `工具/` 下三个侧边栏工具（后处理对比、标定分数、固件升级）附带进产物 `工具/` 目录，并排除 `__pycache__`、PyInstaller 产物（`build`/`dist`）和样本工程集等杂物；可用 `--no-tools` 跳过。侧边栏工具是运行时从 exe 目录向上查找 `工具/<工具名>` 动态加载的，工具在目标机正常运行仍需其自身依赖（如 Python 环境、excel 库等）。

后处理对比工具的任务配置支持“开启Charles”：勾选后选择 `Charles.exe`，在发布版全部后处理完成并关闭、启动测试版之前自动拉起 Charles 抓包代理（CLI 参数 `--charles-exe`）；Charles 启动失败时本次对比判定失败、不再启动测试版。

人体补全对比类型可在“高级参数”中勾选“不生成trip，直接生成人体补全模型”（CLI 参数 `--skip-trip-model`）：跳过导入图片/生成 trip，点击AI人体补全后直接选择模型底座并预览/应用；任务步骤参数也可通过 `{"skip_trip_model": true}` 开启。

Spec 生成 `jens_pc_app.exe` 和 `jens_runner_helper.exe`，并收集 `steps/`、`cases/`、`tasks/`、`docs/`、`config/`、`jens_runner.air/`、`README.md`、`.env` 及运行依赖。

分发时必须保留整个 `jens_pc_app/` 目录，不能只复制 EXE。`用例仓库/`、`web--gaizao/` 和 `滑轨/` 当前不在 Spec 中。

## 16. 测试与校验

```powershell
python -m unittest discover -s tests -v
```

当前测试覆盖从指定 Step 开始执行、日志轮转与帧数轮询、SDK FPS、HTML 报告、OCR 文本解析和任务生成器。

扫描注册表：

```powershell
python -c "from pathlib import Path; from jens_platform.step_registry import scan_steps; print([m.step_id for m in scan_steps(Path('.').resolve())])"
```

维护 preset 或 Task 后至少检查：

1. 每个 `id + version` 都能解析到有效 Step。
2. `params.preset` 能在对应 `key/name/aliases` 中命中。
3. 普通、框架点和后处理块顺序正确。
4. 最后一个参数块后没有多余“新建扫描”。
5. 在目标分辨率和真实 CrealityScan 版本上完成冒烟测试。

## 17. Web 改造状态

`web--gaizao/` 是“中心 Web 平台 + 用户浏览器 + 用户本地精简 Agent”的设计文档集，当前没有实现代码，也未替代 Qt 平台。入口见 [web--gaizao/README.md](web--gaizao/README.md)。

账号权限、共享任务库、本地 Agent、任务下发、进度日志、执行记录和紧急停止均属于规划能力，不能按当前 README 的命令直接使用。

## 18. 维护入口

- 新增动作：新建 `steps/<domain>/<name>/v1_0_0/` 插件。
- 新增扫描参数：维护对应 `presets.json` 和模板。
- 新增生成器模组：维护 `jens_platform/task_generator.py` 及 `tests/test_task_generator.py`。
- 修改日志条件：复用增量读取和日志轮转逻辑，并补超时、轮转和关键字顺序测试。
- 修改报告：维护 `engine/report_html.py`、`engine/logs.py`。
- 修改桌面平台：入口为 `jens_platform/main.py:MainWindow`。
- 修改滑轨协议：维护 `滑轨/motion_service.py` 和 `滑轨/motion_client.py`。

相关背景资料见 [docs/项目技术框架说明.md](docs/项目技术框架说明.md)、[docs/项目执行流程图.svg](docs/项目执行流程图.svg)。其中历史文档的步骤数量与依赖清单可能未同步，当前盘点以本 README 和代码为准。

## 19. 当前限制

- UI 自动化强依赖分辨率、缩放、窗口布局、模板和 CrealityScan 版本。
- 日志格式或目录变化会导致日志驱动 Step 超时。
- Step 注册表会跳过无效 `step.json`，UI 当前不展示解析详情。
- Qt 主窗口职责较多，复杂扩展应拆分模块。
- 任务生成器已覆盖全部 12 个模组，`tests/test_task_generator.py` 当前全绿；新增模组或 preset 时需同时更新生成器配置、标准 Task 与测试基准。
- 安装版暂未包含滑轨资源。
- Web 平台、账号数据库和本地 Agent 仍处于设计阶段。

软件图标来源：[Icons8](https://icons8.com/icon/RIVoFQandML6/baseball-cap)。
