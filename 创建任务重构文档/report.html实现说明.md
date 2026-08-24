# `report.html` 实现说明（Codex 迁移交接版）

## 1. 文档目标

本文按当前项目的真实代码说明自动化运行报告 `report.html` 是如何生成、展示和打开的。目标是让另一台 Codex 在不依赖当前会话上下文的情况下，能够复刻相同行为，而不是只仿制页面外观。

当前报告的核心特点：

- 报告由 Python 在任务执行结束后一次性生成，不是 Qt 页面实时渲染。
- 输出是单个自包含 HTML 文件，CSS 和 JavaScript 全部内嵌。
- 不依赖前端框架、图表库、网络字体或外部 CDN。
- Qt 平台只负责查找和打开报告，不负责报告内容的计算。
- 报告数据来源是执行器产出的 `step_results`、日志关键字统计和设备信息。

## 2. 核心文件

| 文件 | 职责 |
| --- | --- |
| `engine/report_html.py` | 报告计算、HTML/CSS/JS 拼装的唯一核心实现 |
| `jens_runner_entry.py` | Windows 主执行入口，准备报告数据、写入报告及清理产物 |
| `output/mac_pyautogui_poc/runner.py` | macOS POC 执行入口，复用同一个报告渲染函数 |
| `engine/logs.py` | 设备信息、日志关键字和 SDK 帧率会话提取 |
| `engine/scan_fps_xlsx.py` | 生成独立的扫描帧率 Excel，不参与 HTML 页面渲染 |
| `jens_platform/main.py` | Qt 主界面定位最新产物、打开 `report.html` |
| `jens_platform/notifications.py` | 通知功能从运行目录读取报告路径和运行结果 |
| `tests/test_report_html.py` | 报告关键行为的回归测试 |

## 3. 总体调用链

```text
Qt 启动任务
  ↓
jens_runner_entry.run_case()
  ↓
execute_case(case, run_dir)
  ├─ 返回 step_results
  └─ 返回 all_passed
  ↓
_attach_sdk_fps_stats(step_results, case)
  └─ 将 SDK 日志中的帧率统计回填到扫描步骤 extra
  ↓
获取设备信息
  ├─ 优先读取 JENS_DEVICE_* 环境变量
  └─ 环境变量没有提供时，从 CrealityScan 日志提取
  ↓
write_scan_fps_workbook(...)
  └─ 可选生成 scan_fps_summary.xlsx
  ↓
scan_keywords(...)
  └─ 统计日志关键字命中
  ↓
写 result.json
  ↓
render_report_html(...)
  ↓
写 report.html（UTF-8）
  ↓
按任务结果清理或保留调试产物
  ↓
写 summary.json
  ↓
Qt 使用 os.startfile(report.html) 调用系统默认浏览器打开
```

重要顺序：`report.html` 在轻量清理之前生成；`summary.json` 在清理之后生成，因此它能够记录最终保留的产物类型。

## 4. 报告渲染入口

唯一入口位于 `engine/report_html.py`：

```python
render_report_html(
    case_name: str,
    started_at: str,
    finished_at: str,
    step_results: list[dict],
    keyword_hits: dict | None,
    device_info: dict | None,
) -> str
```

调用方负责将返回字符串写为 UTF-8：

```python
report_path.write_text(
    render_report_html(
        case_name=case_name,
        started_at=started_at,
        finished_at=finished_at,
        step_results=step_results,
        keyword_hits=keyword_hits,
        device_info=device_info,
    ),
    encoding="utf-8",
)
```

渲染器本身不读文件、不扫描目录，也不修改输入数据；它只消费调用方传入的数据并返回 HTML 字符串。

## 5. 输入数据契约

### 5.1 `step_results`

每个步骤通常包含：

```json
{
  "id": "crealityscan.scan_until_frames_then_stop",
  "version": "1.0.0",
  "name": "扫描至目标帧后完成",
  "status": "passed",
  "duration_sec": 12.345,
  "attempt": 1,
  "screenshot": "D:/.../screenshots/example.png",
  "error": "",
  "extra": {}
}
```

页面识别的状态：

| 状态 | 中文标签 | 视觉语义 |
| --- | --- | --- |
| `passed` | 通过 | 绿色 |
| `failed` | 失败 | 红色 |
| `stopped` | 已停止 | 黄色 |
| `skipped` | 已跳过 | 灰色 |
| 其他或空值 | 未知 | 灰色 |

### 5.2 `extra`

报告当前会消费以下字段：

| 字段 | 用途 |
| --- | --- |
| `preset_name` | 通过模式弹窗的首选模式名 |
| `preset_input` | 模式名回退值 |
| `avg_fps` | 平均帧率；开流步骤的矩阵指标只显示此值 |
| `peak_fps` | 趋势卡片峰值帧率 |
| `min_fps` | 趋势卡片最低帧率 |
| `fps_seconds_count` | 帧率样本数量；普通步骤指标可使用 |
| `trend_by_second` | 性能趋势数据 |
| `peak_cpu_percent` | CPU 峰值 |
| `peak_memory_percent` | 内存峰值 |
| `peak_wifi_rate_kbps` | Wi-Fi 峰值速率 |
| `wifi_interface_name` | Wi-Fi 网卡名称 |
| `operation_elapsed_sec` | 融合、封装、贴图等操作本身耗时 |
| `operation_elapsed_label` | 操作耗时中文标签，如“融合耗时” |
| `stop_click_frame` | 点击完成时的帧数 |
| `scan_elapsed_sec` | 扫描耗时 |
| `max_frame` | 最大帧数回退指标 |

`trend_by_second` 的每一项格式：

```json
{
  "second": 1,
  "fps": 47.8,
  "cpu_percent": 52.1,
  "memory_percent": 38.6
}
```

### 5.3 `keyword_hits`

标准形态是“关键字 → 命中行列表”：

```json
{
  "ERROR": ["line 1", "line 2"],
  "Exception": ["line 3"]
}
```

为兼容已有调用，渲染器也接受数字计数：

```json
{
  "ERROR": 195,
  "Exception": 112
}
```

HTML 只展示总命中数，不展示命中的具体日志行。

### 5.4 `device_info`

```json
{
  "camera_name": "Raptor Pro",
  "camera_serial_number": "...",
  "camera_connection_type": "USB3.0",
  "camera_firmware_version": "1.0.5"
}
```

字段为空时，设备档案中显示 `-`。

## 6. Runner 数据准备

### 6.1 SDK 帧率挂载

`jens_runner_entry._attach_sdk_fps_stats()` 只处理：

```text
crealityscan.scan_until_frames_then_stop
```

处理规则：

1. 先从该步骤 `extra` 中移除旧的 SDK 帧率字段，避免复用脏数据。
2. 只给 `status == passed` 的扫描步骤挂载帧率。
3. 使用 `scan_started_log_at` 作为扫描开始时间。
4. 优先使用 `stop_click_log_at` 作为扫描结束时间；缺失时退回开始时间。
5. 从 `case.app.log_dir` 读取日志根目录；若未配置，则回退到步骤 `extra.log_file` 的父目录。
6. 调用 `extract_sdk_fps_sessions()` 提取 SDK 帧率会话。
7. 以 5 秒容差匹配覆盖当前扫描时间区间的会话。
8. 一个 SDK 会话只能匹配一个扫描步骤。
9. 多个候选会话中，选择开始时间离扫描开始时间最近的会话。
10. 回填平均、峰值、最低帧率、样本数和会话起止时间。

回填字段：

```text
avg_fps
peak_fps
min_fps
fps_seconds_count
sdk_fps_sessions_count
sdk_fps_session_start_at
sdk_fps_session_stop_at
```

其中 HTML 步骤矩阵对开流步骤只显示 `avg_fps`；其他字段仍保留在 `result.json`，趋势卡片也可使用其中部分字段。

### 6.2 设备信息优先级

第一优先级是环境变量：

```text
JENS_DEVICE_CAMERA_NAME
JENS_DEVICE_CAMERA_SN
JENS_DEVICE_CONNECTION_TYPE
JENS_DEVICE_FIRMWARE_VERSION
```

只有当环境变量没有得到任何设备信息时，才调用 `extract_device_info()` 从 CrealityScan 日志尾部提取。当前不是逐字段合并：只要环境变量结果非空，就不会再从日志补齐其余空字段。

### 6.3 日志关键字

关键字来自 `case.keywords`。当它不是字符串列表时，使用 `DEFAULT_KEYWORDS`。Runner 使用轻量日志尾部扫描，并限制最大匹配数量，随后把统计结果传给 HTML。

## 7. 报告统计公式

| 指标 | 当前算法 |
| --- | --- |
| 步骤总数 | `len(step_results)` |
| 通过步骤 | `status == passed` 的数量 |
| 失败步骤 | `status == failed` 的数量 |
| 停止步骤 | `status == stopped` 的数量 |
| 跳过步骤 | `status == skipped` 的数量 |
| 累计耗时 | 所有步骤 `duration_sec` 求和后四舍五入到 1 位小数 |
| 截图数 | `screenshot` 非空的步骤数量 |
| 关键字命中 | 列表取长度，数字直接累加 |
| 失败摘要 | 最多列出前三个失败步骤名 |

总体状态算法：

```python
if fail_count:
    overall_status = "failed"
elif ok_count:
    overall_status = "passed"
else:
    overall_status = "unknown"
```

注意：总体状态不是直接使用 Runner 的 `all_passed`。如果没有失败、至少有一个通过，即使同时存在 `stopped` 或 `skipped`，HTML 顶部仍会显示“通过”。复刻时若要求行为完全一致，必须保留这一规则；若要修正，应另立需求并补测试。

## 8. “通过的模式”卡片

### 8.1 模式步骤识别

只要步骤 ID 满足以下前缀，就计为“已选择模式”：

```python
step_id.startswith("crealityscan.configure_scan_params_")
```

算法：

```text
已选择模式数 = 所有参数配置步骤数量，不区分状态
通过模式数 = 参数配置步骤中 status == passed 的数量
通过率 = round(通过模式数 × 100 / 已选择模式数)
无已选择模式时通过率 = 0
```

卡片使用按钮元素，关键测试属性：

```html
<button
  data-testid="passed-modes"
  data-pass-percent="67"
  aria-haspopup="dialog"
  aria-controls="passed-modes-dialog">
</button>
```

### 8.2 模式名称优先级

```text
extra.preset_name
  ↓ 缺失
步骤 name 去掉前缀“扫描参数：”
  ↓ 缺失
extra.preset_input
  ↓ 缺失
step id
```

### 8.3 模组名称映射

参数配置步骤 ID 去掉前缀后得到模组键。当前显式映射：

| 内部键 | 展示名 |
| --- | --- |
| `p1` | P1 |
| `pika` | Pika |
| `raptor` | Raptor |
| `raptor_x` | Raptor X |
| `raptor_pro` | Raptor Pro |
| `s1` | S1 |

未显式映射的模组会直接显示内部键的大写形式，例如 `otter_lite_basic` 会显示为 `OTTER_LITE_BASIC`。新增模组后，如果希望弹窗名称自然，应同步扩展 `module_names`。

### 8.4 弹窗内容

弹窗为原生：

```html
<dialog id="passed-modes-dialog">
```

每个通过模式展示：

- 模式名称；
- 模组名称；
- 参数配置步骤耗时，数字格式固定为 3 位小数并带 `s`。

没有通过模式时显示：

```html
<div data-testid="passed-modes-empty">本次没有通过的扫描模式</div>
```

## 9. 页面信息架构

页面从上到下分为：

1. 报告头部
   - 任务名；
   - 开始时间；
   - 结束时间；
   - 总体状态；
   - 失败、停止、跳过数量摘要。
2. Summary board
   - 可点击的“通过的模式”卡片；
   - 步骤总数；
   - 通过步骤；
   - 失败步骤；
   - 累计耗时；
   - 关键字命中总数与截图数。
3. 主内容区
   - 步骤矩阵；
   - 性能趋势。
4. 侧栏
   - 设备档案；
   - 运行时间线。
5. 页面末尾
   - 通过模式详情 `<dialog>`；
   - 弹窗交互 JavaScript。

## 10. 步骤矩阵

表格列：

```text
#
步骤
版本
状态
耗时（秒）
尝试次数
指标
产物
异常
```

渲染规则：

- 序号固定两位，如 `01`、`02`。
- 步骤列同时显示 `name` 和 `id`。
- 数字耗时固定 3 位小数。
- `attempt` 缺失时显示 `-`。
- `screenshot` 非空时生成链接，链接文字为路径中的文件名。
- `error` 使用 `<pre>`，保留换行；无异常显示“无异常”。
- 没有补充指标时显示“无补充指标”。
- 失败行使用危险色背景。
- 表头为 sticky，窄屏允许横向滚动。

### 10.1 开流步骤指标的特殊规则

对步骤：

```text
crealityscan.scan_until_frames_then_stop
```

矩阵只显示：

```text
扫描帧率 {avg_fps}
```

即使 `peak_fps`、`min_fps`、`fps_seconds_count` 存在，也不会在该行显示。这是现有测试明确锁定的行为。

### 10.2 普通步骤可显示的指标

普通步骤按字段存在性追加指标，包括：

- 平均、峰值、最低帧率；
- CPU 峰值；
- 内存峰值；
- Wi-Fi 峰值；
- 停止帧；
- 扫描耗时；
- 后处理操作耗时；
- 帧率样本数或最大帧数。

操作耗时使用：

```text
{operation_elapsed_label} {operation_elapsed_sec}s
```

例如：`融合耗时 11.234s`。

## 11. 性能趋势 SVG

只有 `extra.trend_by_second` 为非空列表的步骤才生成趋势卡片。所有图表均由 Python 拼装原生 SVG，不使用 JavaScript 图表库。

### 11.1 坐标规则

```text
viewBox: 1080 × 320
左边距: 56
右边距: 18
上边距: 18
下边距: 42
Y 轴最大值: max(100, 所有 FPS, 所有 CPU, 所有内存, 1)
Y 轴网格线: 5 条
X 轴刻度: 最少 2 个，最多 6 个
```

三条折线：

| 数据 | 颜色语义 |
| --- | --- |
| FPS | 蓝色 accent |
| CPU | 红色 danger |
| 内存 | 绿色 success |

FPS、CPU 和内存共用同一条 Y 轴。这能保持实现简单，但数值量级差异较大时，小幅变化可能不明显。

### 11.2 趋势卡片统计

趋势卡片下方显示：

```text
平均帧率
峰值帧率
最低帧率
CPU 峰值
内存峰值
Wi-Fi 峰值
Wi-Fi 适配器（仅字段非空时）
```

整个报告没有任何趋势数据时显示“当前报告中没有可用的性能趋势数据”。

## 12. HTML 安全与格式化

动态文本统一经 `_h()` 调用 `html.escape()`，覆盖：

- 任务名；
- 步骤名和 ID；
- 状态兜底文案；
- 指标文本；
- 设备信息；
- 错误内容；
- 截图路径；
- SVG 点坐标字符串。

数值格式通过 `_format_metric_value()` 统一：

- 空值显示 `-`；
- 整数不保留小数；
- 非整数默认保留 3 位小数；
- 非数值回退为转义后的原文本。

## 13. CSS 设计系统

CSS 全部位于 `<head><style>` 内，设计方向为浅色企业测试报告。

主要变量：

```css
--canvas: #f3f6fa;
--surface: #ffffff;
--ink: #111827;
--muted: #64748b;
--line: #dbe3ed;
--accent: #2563eb;
--success: #137a4b;
--danger: #b42335;
--warn: #9a5b00;
```

关键布局：

- 页面最大宽度 `1680px`；
- Summary board 使用网格；
- 主区域为“主内容 + 侧栏”；
- 步骤矩阵允许横向滚动；
- 趋势统计根据空间自适应列数。

字体回退：

```text
Aptos
Segoe UI Variable
Segoe UI
Microsoft YaHei UI
sans-serif
```

响应式断点：

- `1180px`：摘要卡片改为 3 列，主内容和侧栏改为单列，侧栏内部为 2 列；
- `760px`：头部单列、摘要改为 2 列、侧栏内部单列、趋势统计单列。

无障碍与动效：

- 状态不只依赖颜色，同时展示中文文本；
- SVG 使用 `role="img"` 和 `aria-label`；
- 模式卡片声明 `aria-haspopup` 和 `aria-controls`；
- 支持 `prefers-reduced-motion: reduce`。

## 14. 弹窗 JavaScript

脚本采用立即执行函数，且只负责模式弹窗：

```text
查找 [data-testid="passed-modes"]
  ↓
查找 #passed-modes-dialog
  ↓
卡片点击
  ├─ 支持 showModal()：调用 dialog.showModal()
  └─ 不支持 showModal()：设置 open 属性
  ↓
关闭按钮点击：dialog.close()
  ↓
点击 dialog 自身的遮罩区域：dialog.close()
```

Escape 关闭没有手写监听，依赖浏览器对模态原生 `<dialog>` 的默认行为。

页面没有筛选、排序、折线悬浮提示、数据请求或本地存储逻辑。

## 15. 产物文件与保留策略

运行目录至少包含：

```text
report.html
result.json
summary.json
```

可能额外包含：

```text
scan_fps_summary.xlsx
airtest/ocr_fps_*
logs/
screenshots/
```

### 15.1 成功任务

成功时调用 `_cleanup_lightweight_artifacts()`：

- 保留 `report.html`、`result.json`、`summary.json`；
- 若 Excel 生成成功，保留 `scan_fps_summary.xlsx`；
- Airtest 目录仅保留 `ocr_fps_*` 调试文件；
- 删除其他 Airtest 文件；
- 删除 `logs/`；
- 删除 `screenshots/`。

### 15.2 失败任务

失败时不做轻量清理，并将 CrealityScan 日志复制到：

```text
logs/crealityscan/
```

因此失败产物会保留报告、JSON、日志、截图和 Airtest 调试数据，方便排障。

### 15.3 `result.json` 与 `summary.json`

`result.json` 偏完整数据，包含：

```text
case
step_results
all_passed
started_at
finished_at
device_info
scan_fps_xlsx_path
scan_fps_xlsx_error
```

`summary.json` 偏索引和通知用途，包含：

```text
case_name
status
artifact_mode
started_at
finished_at
step_counts
failed_step_name
keyword_hit_counts
device_info
report_path
result_path
scan_fps_xlsx_path
scan_fps_xlsx_error
retained_items
```

## 16. Qt 平台如何展示报告

Qt 不把报告嵌入 `QWebEngineView`，也不解析 HTML。

当前行为：

1. 运行完成后保存最新运行目录和报告路径。
2. 若需要从磁盘恢复，则从 `artifacts` 中按目录修改时间寻找最新运行目录。
3. 检查该目录下是否存在 `report.html`。
4. 用户点击“打开报告”或双击没有截图的结果行时，调用 Windows `os.startfile()`。
5. 系统使用默认浏览器打开本地 HTML。

因此复刻报告时，不需要改 Qt 组件；只需保证产物目录和文件名仍为 `report.html`。

## 17. 打包注意事项

`report_html.py` 是运行时代码，必须随 PyInstaller 一起打包。报告没有静态 CSS、JS、字体或图片目录，因此不存在额外前端资源漏打包问题。

需要保证：

- 打包环境包含 `engine.report_html`；
- 运行目录可写；
- 使用 UTF-8 写文件；
- Windows 能通过默认浏览器打开 `.html`；
- `engine.logs` 的日志提取逻辑也被包含，否则设备信息、关键字和 SDK 帧率会缺失，但 HTML 仍可生成。

## 18. 扩展报告的正确方法

### 18.1 新增步骤指标

1. 在具体 step 的结果 `extra` 中写入结构化字段。
2. 在 `_step_metric_parts()` 中决定矩阵展示文案。
3. 如果属于趋势统计，在 `_render_trend_sections()` 中增加统计项。
4. 给 `tests/test_report_html.py` 增加渲染断言。
5. 保持 Runner、`result.json`、HTML 使用同一个字段名。

不要从步骤名称字符串反向解析业务数据；名称是展示层，`extra` 才是数据契约。

### 18.2 新增模组

模式识别本身依赖统一的步骤 ID 前缀，因此新模组只要使用：

```text
crealityscan.configure_scan_params_{module_key}
```

就会自动计入模式数量。但为了弹窗显示正确名称，还应扩展 `module_names` 映射并补测试。

### 18.3 新增页面卡片

新统计应在 `render_report_html()` 的 Python 计算区先得到确定值，再插入 HTML。不要在 JavaScript 中重新计算同一数据，否则容易让测试、打印报告和浏览器展示产生分歧。

## 19. 回归测试

执行：

```powershell
python -m unittest tests.test_report_html
```

现有测试锁定：

- `keyword_hits` 接受数字计数并正确求和；
- 参数配置步骤的已选择数和通过数正确；
- 通过率写入 `data-pass-percent`；
- 模式卡片可打开原生 `dialog`；
- 通过模式弹窗列出模式名、模组和配置耗时；
- 无通过模式时显示空状态；
- Raptor X 和 Raptor Pro 名称正确；
- 后处理步骤显示本身操作耗时；
- 开流步骤矩阵只显示一个“扫描帧率”，不显示峰值和最低值。

建议迁移后额外验收：

1. 用成功产物打开报告，确认布局和中文无乱码。
2. 用失败产物确认失败行、异常和截图链接。
3. 用多个扫描模式确认通过数量、通过率和弹窗列表。
4. 用含 `trend_by_second` 的产物确认三条折线和统计卡片。
5. 用 760px 以下浏览器宽度确认表格横向滚动和卡片重排。
6. 用新增模组确认弹窗名称映射。

## 20. 当前已知问题

### 20.1 普通步骤部分指标文案存在历史乱码

`_step_metric_parts()` 中除开流专用分支之外，部分中文文本已出现乱码，例如平均帧率、峰值帧率、最低帧率、操作耗时和样本数字样。迁移时不要把这些乱码当作正确产品文案；如果目标是完全复制现状，可原样迁移，但更推荐单独修复并补测试。

### 20.2 新模组名称不会自动本地化

模式步骤能自动发现，但弹窗展示名使用硬编码映射。Otter、Otter Lite Basic、P1S、X1 等若未加入映射，会显示内部键的大写形式。

### 20.3 成功任务的截图链接可能失效

报告先根据步骤中的 `screenshot` 生成链接，随后成功任务会删除 `screenshots/`。因此成功报告中可能保留一个指向已删除文件的链接。失败任务不会清理截图，链接通常有效。

### 20.4 总体状态与 `all_passed` 口径不完全一致

HTML 自己依据失败数和通过数计算总体状态，而不是使用 Runner 的 `all_passed`。混合 `passed + stopped` 等边界情况可能与执行器状态不一致。

### 20.5 趋势图共用单轴

FPS、CPU 和内存共用一个 Y 轴，适合快速概览，但不适合精细比较不同量纲。

### 20.6 报告是静态快照

报告生成后不会自动感知 `result.json` 或 preset 的后续变化。要更新报告必须重新调用 `render_report_html()` 并覆盖文件。

## 21. 给另一台 Codex 的直接实施提示

可将下面内容直接交给另一台 Codex：

```text
请按“创建任务重构文档/report.html实现说明.md”复刻当前自动化报告。

实施要求：
1. 以 engine/report_html.py 的 render_report_html() 为唯一报告渲染入口。
2. 保留 jens_runner_entry.py 中“执行步骤 → 挂载 SDK 帧率 → 设备信息 → Excel → 关键字 → result.json → report.html → 产物清理 → summary.json”的顺序。
3. 报告必须是 UTF-8 自包含 HTML，不引入 CDN、前端框架或图表库。
4. 保留参数配置步骤前缀驱动的模式统计及原生 dialog 详情。
5. 开流步骤矩阵只展示 avg_fps；后处理使用 operation_elapsed_sec 和 operation_elapsed_label。
6. Qt 只通过 os.startfile() 打开报告，不把展示逻辑重复实现到 Qt。
7. 迁移后运行 python -m unittest tests.test_report_html。
8. 已知乱码、模组名称映射、成功截图链接和总体状态口径属于现存问题；不要无意中改变行为，如需修复必须单独提交并增加测试。
```

## 22. 最小复刻验收标准

满足以下条件可认为复刻完成：

- 执行一次任务会在对应产物目录生成 UTF-8 的 `report.html`；
- 报告可离线打开，且不访问网络资源；
- 顶部统计和步骤矩阵与 `result.json.step_results` 一致；
- 参数配置步骤能计入“通过的模式”，点击卡片能展示详情；
- 扫描步骤能显示步骤结果中的平均帧率；
- 后处理步骤能显示融合、封装、贴图等步骤自身耗时；
- 有趋势数据时能显示 FPS、CPU、内存折线；
- 设备信息和关键字统计能进入报告；
- 成功与失败任务遵循现有产物保留策略；
- `tests.test_report_html` 全部通过。
