# CrealityScan 后处理对比平台

CrealityScan 后处理对比平台用于对比两个 CrealityScan 版本处理同一批工程后的结果。
工具会为发布版和测试版分别创建独立工程副本，按相同流程串行执行，并保存处理后的工程、截图和运行日志。

## 当前能力

- Qt 工作台界面和命令行两种入口。
- 发布版、测试版串行运行，不同时控制两个 CrealityScan 进程。
- 支持工程集批量处理。
- 强制选择一种后处理类型：
  - 贴图
  - 高斯渲染
  - AI重贴图
- 导入工程使用 `OB_SCAN_MESSAGE_ID_PROJECT_IMPORT_SUCCESS` 日志标识判定完成。
- 返回首页点击确认后固定等待 3 秒。
- 后处理步骤记录耗时并保存全屏截图。
- 贴图截图前自动将鼠标移到左上角，等待界面退出 hover 状态后再留证。
- 两个版本全部完成后自动生成发布版/测试版截图并排的 Excel 对比表。
- 支持紧急停止，停止时会终止当前 CLI 进程树。
- 支持中文、空格路径和独立输出目录。

## 目录结构

```text
后处理对比工具/
├─ README.md
├─ cli.py                         # 命令行入口
├─ requirements.txt               # Python 依赖
├─ 启动Qt界面.bat                  # Qt 工作台入口
├─ 启动命令行.bat                  # 命令行入口
├─ postprocess_compare/
│  ├─ qt_app.py                   # Qt 界面
│  ├─ cli.py                      # 执行编排
│  └─ process_manager.py          # CrealityScan 启动和关闭
├─ setps/
│  ├─ import_project/             # 导入工程
│  ├─ texture_operation/          # 贴图操作
│  ├─ gaussian_rendering/         # 高斯渲染操作
│  └─ return_home/                # 返回首页
└─ artifacts/                     # 运行产物目录
```

## 安装依赖

在 `后处理对比工具` 目录执行：

```powershell
python -m pip install -r requirements.txt
```

依赖包括：

- Python 3.11 或更高版本
- PyQt5
- Airtest
- psutil
- pywinauto
- openpyxl
- Pillow

## Qt 启动

双击：

```text
启动Qt界面.bat
```

界面操作流程：

1. 选择“贴图”、“高斯渲染”或“AI重贴图”。必须明确选择，不能留空。
2. 选择发布版 `CrealityScan.exe` 和版本标签。
3. 选择测试版 `CrealityScan.exe` 和版本标签。
4. 选择原始工程集目录。
5. 选择输出目录。
6. 按需展开高级参数。
7. 点击“开始对比”。

运行期间配置会锁定。右侧控制台显示当前步骤和最近 5 行日志；“紧急停止”会终止当前任务。

## 命令行启动

### 交互式启动

双击：

```text
启动命令行.bat
```

脚本会先让用户选择贴图、高斯渲染或AI重贴图，然后依次询问 EXE、版本标签、工程集和输出目录。

### 参数启动

贴图对比：

```powershell
python -m postprocess_compare `
  --operation texture `
  --release-exe "D:\CrealityScan\release\CrealityScan.exe" `
  --release-version "1.12.3-release" `
  --test-exe "D:\CrealityScan\test\CrealityScan.exe" `
  --test-version "1.12.4-test" `
  --project-set "D:\扫描工程集" `
  --output-dir "D:\对比结果"
```

高斯渲染对比：

```powershell
python -m postprocess_compare `
  --operation gaussian `
  --operation-timeout 900 `
  --release-exe "D:\CrealityScan\release\CrealityScan.exe" `
  --release-version "1.12.3-release" `
  --test-exe "D:\CrealityScan\test\CrealityScan.exe" `
  --test-version "1.12.4-test" `
  --project-set "D:\扫描工程集" `
  --output-dir "D:\对比结果"
```

AI重贴图对比：

```powershell
python -m postprocess_compare `
  --operation ai_retexture `
  --operation-timeout 600 `
  --release-exe "D:\CrealityScan\release\CrealityScan.exe" `
  --release-version "1.12.3-release" `
  --test-exe "D:\CrealityScan\test\CrealityScan.exe" `
  --test-version "1.12.4-test" `
  --project-set "D:\扫描工程集" `
  --output-dir "D:\对比结果"
```

`--operation` 是必填参数：

| 值 | 类型 | 默认超时 |
| --- | --- | ---: |
| `texture` | 贴图 | 90 秒 |
| `gaussian` | 高斯渲染 | 900 秒 |
| `ai_retexture` | AI重贴图 | 600 秒 |

其他超时参数：

- `--start-timeout`：等待 CrealityScan 主窗口，默认 120 秒。
- `--close-timeout`：等待软件关闭，默认 20 秒。
- `--operation-timeout`：覆盖当前后处理类型的默认超时。
- `--texture-timeout`：贴图进度等待超时，默认 90 秒（AI重贴图的前置贴图也使用该值）。
- `--gaussian-timeout`：高斯渲染进度等待超时，默认 900 秒。
- `--ai-retexture-timeout`：AI重贴图操作等待超时，默认 600 秒。
- `--ai-retexture-gaussian`：AI重贴图开启高斯渲染。
- `--no-texture-first`：AI重贴图前不先执行贴图操作（默认先执行贴图）。

## 执行流程

每个版本按以下流程执行：

```text
创建工作副本
  -> 启动 CrealityScan
  -> 导入工程
  -> 等待导入成功日志
  -> 执行选中的后处理操作
  -> 等待后处理完成
  -> 保存全屏截图和耗时
  -> 返回首页
  -> 点击确认并等待 3 秒
```

版本顺序固定为：

```text
发布版全部工程 -> 关闭发布版 -> 测试版全部工程 -> 关闭测试版
```

同一批次内的每个原始工程都会生成发布版和测试版两份副本。原始工程不会直接导入 CrealityScan。

## 工程集规则

工程集可以直接包含 `project.obp`，也可以在一级子目录中包含多个 `project.obp`：

```text
工程集/
├─ 工程A/project.obp
├─ 工程B/project.obp
└─ 工程C/project.obp
```

多个工程按路径排序后处理，输出名称带有工程序号，例如：

```text
工程1_1.12.3_贴图
工程2_1.12.3_贴图
工程1_1.12.3_高斯渲染
```

## 输出目录

每次任务创建独立时间戳目录：

```text
对比结果/
└─ compare_20260808_153000_123456/
   ├─ release/
   │  ├─ 工程1_1.12.3_贴图/
   │  │  └─ artifacts/screenshots/
   │  └─ ...
   ├─ test/
   │  ├─ 工程1_1.12.4_贴图/
   │  │  └─ artifacts/screenshots/
   │  └─ ...
   └─ 20260808_153000贴图对比表.xlsx
```

Excel 文件命名为“时间戳 + 执行的后处理名称 + 对比表”，每个工程的发布版和测试版截图按序号并排嵌入；截图缺失或数量异常时会在对应行明确标记，不会用其他工程截图替代。

任务完成后，“查看结果”按钮会优先直接打开 Excel 对比表；表格不可用时回退到本次输出目录。

## 完成判定

### 导入工程

导入工程点击打开后，轮询 CrealityScan 最新日志，只匹配点击之后新增的内容：

```text
OB_SCAN_MESSAGE_ID_PROJECT_IMPORT_SUCCESS
```

未检测到该标识时不会进入后处理步骤。

### 贴图、高斯渲染和 AI重贴图

三个后处理 Step 都按照对应 Airtest 模板等待进度状态完成，并记录操作耗时。高斯渲染默认超时为 15 分钟，AI重贴图默认超时为 10 分钟，且 AI重贴图默认会先执行一次贴图操作（可用 `--no-texture-first` 关闭）。

贴图 Step 完成后、截图前通过 Airtest `move_to` 将鼠标移动到左上角安全位置，避免鼠标停留在操作控件上导致截图保留 hover 高亮。默认坐标为 `(10, 10)`，移动后等待 `0.3` 秒再截图；移动失败最多重试 2 次，仍失败则报告明确错误且不生成误导性截图。

内部 Step 参数支持覆盖默认值：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `mouse_safe_x` | `10` | 截图前鼠标安全位置的横坐标 |
| `mouse_safe_y` | `10` | 截图前鼠标安全位置的纵坐标 |
| `mouse_safe_sleep_sec` | `0.3` | 移动后等待界面恢复非 hover 状态的时间 |

### 返回首页

点击首页确认按钮后等待 3 秒，再继续下一个工程或关闭当前版本；不再要求人工按 Enter 确认。

## Windows 兼容性

- Windows 11：Qt 界面尝试启用 Mica 材质效果。
- Windows 10：Mica 不可用时自动回退到普通 Qt 浅色界面，不影响功能。
- 需要安装 Python、PyQt5、Airtest、psutil、pywinauto、openpyxl 和 Pillow。
- CrealityScan 两个 EXE 不能使用同一路径。
- 启动任务前应关闭同名的 CrealityScan 进程，避免窗口绑定冲突。

## 退出码

| 退出码 | 含义 |
| ---: | --- |
| `0` | 发布版和测试版均完成 |
| `1` | 至少一侧启动、操作或关闭失败 |
| `2` | 配置无效、未选择后处理类型或工作副本准备失败 |
| `3` | 用户中断任务 |

## 当前限制

- 一次任务只能选择一种后处理类型，不能在单个任务中组合执行贴图、高斯渲染和AI重贴图（AI重贴图内部自带的前置贴图除外）。
- CLI 当前固定执行导入工程、选中后处理、返回首页流程。
- 左侧“对比任务、运行记录、设置”目前是界面导航占位入口。
- Excel 对比表只汇总截图，不做图片质量评分或像素差异判定。
- 未实现图片质量评分、像素差异分析和自动判断哪个版本更好。

## 常见问题

### 双击 BAT 后出现 `/m`、`/b` 或 `errorlevel` 不是命令

请确认使用仓库内最新的 BAT 文件。启动脚本必须使用 Windows `CRLF` 换行，不能被编辑器转换为 Unix `LF`。

### GUI 无法启动

确认依赖已安装：

```powershell
python -m pip install -r requirements.txt
```

### 导入工程一直等待

检查 CrealityScan 日志是否持续写入，并确认日志中出现：

```text
OB_SCAN_MESSAGE_ID_PROJECT_IMPORT_SUCCESS
```

### 任务启动后找不到窗口

确认 EXE 路径有效、软件没有被其他实例占用，并检查启动超时是否需要增加。
