# 步骤与用例 JSON 规范（v0）

本规范用于“步骤库（Step Library）”与“用例编排（Case）”的数据交换，目标是让平台 UI 能：

- 展示可选步骤列表
- 让用户拖拽排序组合
- 针对“特殊步骤”展示参数面板
- 让执行引擎按编排运行，并产出可追溯的步骤级结果与报告

> 设计原则：KISS/YAGNI。先满足当前落地需要，后续再逐步扩展字段。

## 1. 用例编排 JSON（Case）

路径建议：`cases/*.json`（平台最终输出的就是这种 JSON）。

### 1.1 顶层字段

- `case_id` (string, required): 用例唯一标识（建议英文/下划线）
- `name` (string, required): 用例名称（可中文）
- `app` (object, optional):
  - `window_title_contains` (string, optional): 用于激活/置顶窗口的标题关键字（默认 `CrealityScan`）
  - `device_uri` (string, optional): Airtest 连接设备 URI（Windows 默认 `Windows:///`）
  - `log_dir` (string, optional): CrealityScan 日志目录（由用户填写；可给默认值）
- `keywords` (string[], optional): 全局日志关键词（未填则使用默认关键词）
- `steps` (array, required): 步骤列表（按数组顺序执行）

### 1.2 Step 对象字段（Case.steps[*]）

- `id` (string, required): Step ID，例如 `crealityscan.import_project`
- `version` (string, required): 版本，例如 `1.0.0`
- `name` (string, optional): 展示名；不填则用 `id`
- `params` (object, optional): 参数对象；无参数可 `{}` 或省略
- `on_fail` (object, optional): 失败策略（不填默认 `abort`）
  - `action` (string): `abort` | `continue` | `retry`
  - `max_retries` (int): 仅当 `retry` 时有效
  - `retry_wait_sec` (float): 重试间隔（秒）

## 2. 步骤元数据 JSON（Step Metadata）

路径建议：`steps/**/step.json`（未来平台会扫描并展示）。

### 2.1 字段

- `id` (string, required): 对应 Case.steps[*].id
- `name` (string, required): 展示名
- `version` (string, required): 版本号
- `description` (string, optional): 描述
- `params_schema` (object, optional): 参数 Schema（只对需要参数的步骤填写；无参数可 `{}`）

> 备注：`params_schema` 暂按“平台内部约定”先做最小可用，后续可升级成标准 JSON Schema。

## 3. 代码与目录约定

### 3.1 Step ID → Python 模块路径

执行引擎按以下规则加载步骤实现（实现函数名固定 `run(ctx, params)`）：

- `step_id` 按 `.` 分段映射到 `steps/` 下的目录层级
- `version` 映射到目录名：`v{version}`，并将 `.` 替换为 `_`

例：

- `id=crealityscan.view_logs` + `version=1.0.0`
- 实现模块：`steps.crealityscan.view_logs.v1_0_0.impl`
- 入口函数：`run(ctx, params)`

### 3.2 ctx / params

- `params`：来自 Case.steps[*].params
- `ctx`：运行期上下文（当前包含 `case/run_dir/step_index/env`），后续可扩展但尽量保持向后兼容
