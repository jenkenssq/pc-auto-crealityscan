# 新建任务实现说明（Codex 迁移交接版）

更新时间：2026-08-16  
适用项目：Jens PC 自动化工具（PyQt5）  
目标：让另一份代码或另一台 Codex 按当前项目的真实行为，复刻“新建任务”向导、动态 preset 发现和任务步骤生成。

> 本文以当前代码为唯一事实来源，不以旧任务 JSON 或历史设计稿为准。

## 1. 结论先行

当前“新建任务”不是手写一个空任务，也不是把所有扫描模式写死在界面里，而是下面这条链路：

```text
主界面“新建任务”按钮
  → 三步创建向导 TaskCreationWizardDialog
  → 根据模组和连接方式动态读取 presets.json
  → 用户多选模式、设置开流/后处理、目标帧数和顺序
  → build_task_model() 按规则生成 CaseModel
  → 打开 TaskEditDialog 供用户最终确认和编辑
  → 用户点击保存后写入 tasks/<任务名>.json
  → 自动加入主界面任务队列并选中
```

核心原则：

1. **模组列表显式注册**：新增模组必须在 `MODULE_PRESET_SOURCES` 注册。
2. **扫描模式动态驱动**：每次选择模组或点击“刷新 preset”时，重新读取对应 `presets.json`。
3. **连接方式只做模式约束**：USB/Wi-Fi 用于过滤 preset 和生成默认任务名，不插入“连接设备”步骤。
4. **任务顺序由用户选择固化**：随机模式在向导内直接打乱 `_selected_order`，最终 JSON 保存的是已经打乱后的确定顺序。
5. **成功返回首页由执行器追加**：`crealityscan.return_home` 不写入任务 JSON，只在全部业务步骤成功后由执行器执行。

## 2. 代码入口与职责

| 文件 | 关键对象 | 职责 |
|---|---|---|
| `jens_platform/main.py` | `MainWindow._create_task()` | 打开向导、接收值、调用生成器、处理同名文件、打开编辑器、刷新队列 |
| `jens_platform/dialogs.py` | `TaskCreationWizardDialog` | 三步向导 UI、模组/连接选择、preset 多选、筛选、随机顺序、摘要与校验 |
| `jens_platform/task_generator.py` | `MODULE_PRESET_SOURCES` | 注册支持的模组及各模组特殊能力 |
| `jens_platform/task_generator.py` | `list_module_presets()` | 定位并解析 `presets.json`，归一化连接方式和任务类型，按连接过滤 |
| `jens_platform/task_generator.py` | `build_task_model()` | 验证输入并生成完整 `CaseModel` |
| `jens_platform/case_store.py` | `CaseModel` / `CaseStep` | 任务内存模型、JSON 序列化和 `tasks/*.json` 保存 |
| `jens_platform/dialogs.py` | `TaskEditDialog._save_and_accept()` | 用户最终确认后真正写入任务文件 |
| `engine/executor.py` | `_execute_success_cleanup()` | 任务全部成功后追加执行“返回首页” |

主调用链对应当前代码：

```text
jens_platform/main.py:_create_task
  ├─ TaskCreationWizardDialog(project_root)
  ├─ dialog.values()
  ├─ _resolve_task_path(task_name)
  ├─ build_task_model(...)
  └─ _edit_task_path(path, initial_model=model)
       └─ TaskEditDialog._save_and_accept()
            └─ save_task_json(project_root, model, path)
```

## 3. 三步向导的交互

### 3.1 窗口框架

- 类型：模态 `QDialog`。
- 标题：`创建测试任务`。
- 初始尺寸：`1220 × 820`。
- 最小尺寸：`1000 × 680`。
- 字体：`Microsoft YaHei UI`，9pt。
- 主体：顶部标题、三段 stepper、中间 `QStackedWidget`、底部操作栏。
- Stepper：
  1. 模组与连接——确定设备上下文。
  2. 选择扫描模式——支持多选。
  3. 生成方式——开流或后处理。

向导的核心状态：

```python
self._module_name: str                 # 当前模组内部名称
self._presets: list[ScanPreset]        # 当前连接方式下可见的 preset
self._selected_order: list[str]        # 已选 preset key，顺序即最终执行顺序
self._active_category: str             # 当前分类筛选
self._last_default_task_name: str      # 判断任务名是否仍可自动更新
```

`_selected_order` 是唯一可信的选择状态。列表重建、搜索、切分类时，勾选状态都从它恢复，不能只依赖 `QListWidgetItem.checkState()`。

### 3.2 第一步：模组与连接

左侧显示模组卡片，右侧显示当前模组、模式数量和连接方式。

- 模组卡片来自 `MODULE_PRESET_SOURCES`，按显示名排序。
- 卡片显示：显示名、当前 preset 数量、能力标签。
- 能力标签：
  - `USB / Wi-Fi`：`supports_connection=True`。
  - `特殊等待`：`pika_waits=True`。
  - `动态 preset`：preset 能成功读取且数量大于 0。
- 双击模组卡片可直接进入第二步。
- 切换模组会清空所有已选模式，并立即重新读取该模组 preset。
- 连接方式默认 `USB`，仅对 `supports_connection=True` 的模组显示。
- 切换 USB/Wi-Fi 会重新读取并过滤 preset，同时删除当前连接下不再可用的已选模式。

重要边界：连接方式只是筛选条件和命名信息，生成器不会添加 `connect_device` 步骤。

### 3.3 第二步：扫描模式多选

页面分三栏：

1. 左栏：分类按钮。
2. 中栏：搜索、全选当前结果、清空、preset 勾选列表。
3. 右栏：已选模式及数量。

分类顺序与判定优先级：

```text
名称含“人脸”或“人体” → 人像
否则名称含“框架点”   → 框架点
否则名称含“线激光”或 key 含 line_laser → 线激光
否则 → 散斑
```

注意：线激光框架点会归入“框架点”，不会归入“线激光”。

搜索范围：`preset.name + preset.key + aliases`，统一转小写后做子串匹配。

列表项显示两行：

```text
<preset 中文名>
<分类> · <USB/Wi-Fi 范围> · <可选的“自动规则”标记>
```

- `task_profile == "frame_points"` 时显示“自动规则”。
- 没有限定连接的 preset 显示 `USB / Wi-Fi 共用`。
- “全选当前结果”只勾选当前搜索和分类过滤后可见的条目。
- 至少选择一个模式才能进入第三步。
- “刷新 preset”会重新读取磁盘文件；新增/删除/改名无需修改 UI 代码。

### 3.4 第三步：生成方式

字段与默认值：

| 字段 | 行为 |
|---|---|
| 任务名称 | 自动生成，可手改；手改后不再被选项变化覆盖 |
| 任务类型 | 默认“开流”；可切换“后处理” |
| 目标帧数 | 默认 200，范围 1–100000，步进 50 |
| 随机顺序 | 默认关闭；开启后立即打乱已选模式 |
| 重新打乱 | 随机模式开启后可用，最多尝试 3 次避免与上一次完全相同 |

默认任务名：

```text
支持连接区分的模组：<模组显示名><开流|后处理><usb|wifi>
不区分连接的模组：<模组显示名><开流|后处理>
```

示例：`P1后处理usb`、`Raptor开流`、`Raptor Pro后处理wifi`。

随机顺序的真实实现：

- 向导直接对 `_selected_order` 调用 `random.shuffle()`。
- 关闭随机后，按照当前 `presets.json` 的原始顺序恢复。
- `values()` 虽返回 `randomized`，但主界面不把它传给生成器。
- 主界面传递的是已经固化顺序的 `preset_keys`。
- `build_task_model(randomize=True, random_seed=...)` 仍保留为程序化调用和测试接口，向导主流程不依赖它。

第三步右侧摘要显示：模组、模式数、目标帧数、预计步骤数、Pika 等待、框架点流程、后处理规则和成功返回首页说明。预计步骤数只用于 UI 提示，不参与真实生成。

## 4. 模组注册

模组不是扫描目录自动发现，而是在 `jens_platform/task_generator.py` 的 `MODULE_PRESET_SOURCES` 中显式注册。

`ModulePresetSource` 字段：

```python
@dataclass(frozen=True)
class ModulePresetSource:
    module_name: str
    display_name: str
    configure_step_id: str
    include_activate_window: bool = True
    supports_connection: bool = False
    pika_waits: bool = False
```

当前注册快照（模式数量仅表示 2026-08-16 当前仓库状态）：

| 内部名称 | 显示名 | 参数配置 step id | 激活窗口 | 区分连接 | Pika 等待 | 全部 | USB | Wi-Fi |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `feeret` | Ferret | `crealityscan.configure_scan_params_ferret` | 是 | 否 | 否 | 23 | 23 | 23 |
| `otter` | Otter | `crealityscan.configure_scan_params_otter` | 是 | 否 | 否 | 26 | 26 | 26 |
| `otter lite` | Otter Lite | `crealityscan.configure_scan_params_otter_lite` | 是 | 否 | 否 | 20 | 20 | 20 |
| `otter lite basic` | Otter Lite Basic | `crealityscan.configure_scan_params_otter_lite_basic` | 是 | 否 | 否 | 20 | 20 | 20 |
| `P1` | P1 | `crealityscan.configure_scan_params_p1` | 是 | 是 | 否 | 23 | 21 | 19 |
| `P1S` | P1S | `crealityscan.configure_scan_params_p1s` | 是 | 是 | 否 | 23 | 23 | 21 |
| `pika` | Pika | `crealityscan.configure_scan_params_pika` | 是 | 是 | 是 | 21 | 18 | 13 |
| `raptor` | Raptor | `crealityscan.configure_scan_params_raptor` | 否 | 否 | 否 | 19 | 19 | 19 |
| `raptor x` | Raptor X | `crealityscan.configure_scan_params_raptor_x` | 否 | 是 | 否 | 22 | 22 | 21 |
| `raptor pro` | Raptor Pro | `crealityscan.configure_scan_params_raptor_pro` | 否 | 是 | 否 | 21 | 21 | 20 |
| `S1` | S1 | `crealityscan.configure_scan_params_s1` | 是 | 是 | 否 | 26 | 24 | 23 |
| `X1` | X1 | `crealityscan.configure_scan_params_x1` | 是 | 是 | 否 | 24 | 22 | 21 |

注意：`feeret` 是当前代码中的内部键拼写，迁移时若改成 `ferret` 会造成兼容差异。

新增模组的最低要求：

1. 创建并注册参数配置 step。
2. 确保存在：

   ```text
   steps/crealityscan/<configure_step_id 最后一段>/v1_0_0/presets.json
   ```

3. 在 `MODULE_PRESET_SOURCES` 增加一项。
4. 根据设备行为设置 `include_activate_window`、`supports_connection`、`pika_waits`。
5. 增加生成器测试和向导模组发现测试。

仅新增目录不会自动出现在新建任务页面；动态发现只覆盖 preset，不覆盖模组注册。

## 5. preset 动态发现

### 5.1 路径约定

生成器从参数配置 step id 的最后一段推导目录：

```text
crealityscan.configure_scan_params_p1
  → steps/crealityscan/configure_scan_params_p1/v1_0_0/presets.json
```

开发环境优先使用传入 `project_root` 下的 `steps`。如果打包版应用目录没有 `steps`，则通过 `jens_runtime.get_resource_root()` 回退到 PyInstaller `_MEIPASS` 或 `_internal` 资源目录。

打包时必须把整个 `steps` 目录包含进资源，否则模组卡片会显示“preset 读取失败”。

### 5.2 preset 支持的数据结构

```json
{
  "presets": [
    {
      "key": "p1.line_laser.frame_points.texture_on",
      "name": "线激光-框架点-开启贴图-usb",
      "aliases": ["框架点贴图"],
      "connections": ["usb"],
      "task_profile": "frame_points",
      "actions": []
    }
  ]
}
```

新建任务功能实际读取的字段：

| 字段 | 必填 | 用途 |
|---|---:|---|
| `key` | 是 | 唯一标识、写入任务步骤 `params.preset` |
| `name` | 否 | 中文展示名；缺失时回退到 key |
| `aliases` | 否 | 搜索匹配 |
| `connections` | 否 | USB/Wi-Fi 过滤 |
| `task_profile` | 否 | `frame_points` 触发框架点流程 |
| `actions` | 参数 step 使用 | 向导不解析动作，但实际执行 preset 时由参数配置 step 使用 |

读取规则：

- 使用 `utf-8-sig`，兼容 BOM。
- 顶层必须是对象，且包含 `presets` 列表。
- 非对象条目跳过。
- 缺 key、缺有效名称或 key 重复的条目跳过。
- 重复 key 保留第一条。
- JSON 读取或格式错误会在 UI 弹出具体错误。

### 5.3 连接方式归一化

显式 `connections` 支持字符串或列表，按下面规则归一化：

```text
usb                    → USB
wifi / wi-fi / wlan    → Wi-Fi
```

没有显式连接元数据时：

1. key 或 name 含 `wifi` / `wi-fi` → Wi-Fi 专属。
2. key 或 name 含 `usb` → USB 专属。
3. Pika 的 key 以 `pika.line_laser.` 开头 → USB 专属。
4. 其他 → USB/Wi-Fi 共用。

过滤规则：只有模组 `supports_connection=True` 时才传入连接条件；preset 没有限定连接时在两种连接下都显示。

当前“无标记点仅 USB 可见”依赖 preset 的 `connections: ["usb"]` 或 Pika 线激光兜底规则，不是生成器里针对“无标记点”的全局硬编码。

### 5.4 框架点 profile

`task_profile` 的判定：

1. 若显式提供，转小写并把 `-` 替换成 `_`。
2. 否则 key/name 含 `frame_points` 或中文名含“框架点” → `frame_points`。
3. 其他 → `standard`。

建议新增 preset 时显式写 `task_profile` 和 `connections`，不要只依赖命名推断。现有文件仍大量依赖推断，因此迁移时必须保留兼容逻辑。

## 6. 任务步骤生成规则

所有自动生成步骤：

- `version` 固定为 `1.0.0`。
- 默认失败策略为 `{"action": "abort"}`。
- 参数配置步骤写入稳定的 preset key，不写中文名。

### 6.1 任务开头

```text
如果 include_activate_window=True：
  common.activate_window（激活/置顶窗口）

如果 pika_waits=True：
  common.sleep 1s

crealityscan.create_project（新建项目）

如果 pika_waits=True：
  common.sleep 1s
```

Raptor、Raptor X、Raptor Pro 不生成 `common.activate_window`；其他当前模组会生成。

### 6.2 多模式边界

第一个模式直接开始配置。从第二个模式开始，每个模式前插入：

```text
crealityscan.create_scan（新建扫描）
Pika 再等待 3s
```

模式块按 `_selected_order` / `preset_keys` 顺序串联。

### 6.3 普通模式（standard）

非 Pika：

```text
<模组参数配置 step> params={"preset": preset.key}
crealityscan.preview_scan
crealityscan.scan_until_frames_then_stop params={"target_frames": N}
```

Pika：

```text
crealityscan.configure_scan_params_pika
  params={"preset": preset.key, "delay_sec": 0.5, "mouse_safe_sleep_sec": 0.5}
common.sleep 3s
crealityscan.scan_until_frames_then_stop params={"target_frames": N}
common.sleep 1s
```

Pika 的普通模式在扫描前不插入 `preview_scan`。

Pika Wi-Fi key 以 `pika.wifi.` 开头时，参数配置步骤只写 `preset`，不增加 `delay_sec` 和 `mouse_safe_sleep_sec`。

### 6.4 框架点模式（frame_points）

非 Pika：

```text
<模组参数配置 step>
crealityscan.preview_scan
crealityscan.scan_until_frames_reach_target_frame_points
crealityscan.pause_switch_point_cloud_scan
crealityscan.preview_scan
crealityscan.scan_until_frames_then_stop params={"target_frames": N}
```

Pika：

```text
crealityscan.configure_scan_params_pika
common.sleep 3s
crealityscan.scan_until_frames_reach_target_frame_points
crealityscan.pause_switch_point_cloud_scan
crealityscan.preview_scan
crealityscan.scan_until_frames_then_stop params={"target_frames": N}
common.sleep 1s
```

关键特例：Pika 框架点在参数配置后、切点云前**不做预览扫描**；切点云后的 `preview_scan` 必须保留。

### 6.5 开流与后处理

开流任务在扫描完成后结束当前模式块。

后处理任务在扫描完成后追加：

```text
crealityscan.fusion_operation
crealityscan.package_operation
按贴图规则决定是否追加 crealityscan.texture_operation
```

贴图判定按以下优先级，顺序不能改变：

1. key/name 含 `texture_off`、`关闭贴图`、`不贴图` → **不贴图**。
2. key/name 含 `texture_on`、`开启贴图` → **贴图**。
3. key/name 含 `no_marker`、`无标记点`、`无标志点` → **贴图**。
4. key/name 含 `line_laser` 或中文名含 `线激光` → **默认不贴图**。
5. 其他模式 → **默认贴图**，包含散斑。

由此得到：

- 散斑默认贴图。
- 线激光交叉线/平行线/单线默认不贴图。
- 明确“开启贴图”的线激光仍贴图。
- 明确“关闭贴图/不贴图”的模式不贴图。
- 无标记点虽然是线激光，但优先命中无标记点规则，默认贴图。

### 6.6 成功返回首页

生成器不把 `crealityscan.return_home` 写入 `tasks/*.json`。

`engine/executor.py` 在所有业务步骤通过后调用 `_execute_success_cleanup()`，把下面这条结果追加到运行结果：

```text
crealityscan.return_home / 1.0.0 / 返回首页
extra.executor_cleanup = true
```

只在业务步骤全部成功时执行；任务失败时不返回首页。复刻新建任务功能时不要再把返回首页写进任务末尾，否则会重复执行。

## 7. 生成示例

### 7.1 P1 普通开流模式

输入：

```text
模组=P1
连接=USB
类型=开流
preset=p1.speckle.medium.geometry
目标帧数=200
```

生成：

```text
01 common.activate_window
02 crealityscan.create_project
03 crealityscan.configure_scan_params_p1
04 crealityscan.preview_scan
05 crealityscan.scan_until_frames_then_stop target_frames=200
```

### 7.2 P1 框架点关闭贴图后处理

输入 preset：`p1.line_laser.frame_points.texture_off`

生成：

```text
01 common.activate_window
02 crealityscan.create_project
03 crealityscan.configure_scan_params_p1
04 crealityscan.preview_scan
05 crealityscan.scan_until_frames_reach_target_frame_points
06 crealityscan.pause_switch_point_cloud_scan
07 crealityscan.preview_scan
08 crealityscan.scan_until_frames_then_stop target_frames=200
09 crealityscan.fusion_operation
10 crealityscan.package_operation
```

不生成 `texture_operation`。

### 7.3 Pika 框架点开流

输入 preset：`pika.line_laser.frame_points.texture_on`

生成：

```text
01 common.activate_window
02 common.sleep 1s
03 crealityscan.create_project
04 common.sleep 1s
05 crealityscan.configure_scan_params_pika
06 common.sleep 3s
07 crealityscan.scan_until_frames_reach_target_frame_points
08 crealityscan.pause_switch_point_cloud_scan
09 crealityscan.preview_scan
10 crealityscan.scan_until_frames_then_stop target_frames=200
11 common.sleep 1s
```

第 7 步前没有 `preview_scan`，第 8 步切点云后有一次 `preview_scan`。

## 8. 任务名、文件路径与保存

任务名会先清理 Windows 非法文件名字符：

```text
< > : " / \ | ? *  → _
```

保存路径：

```text
tasks/<安全任务名>.json
```

同名任务处理：

- 选择“是” → 覆盖原文件。
- 选择“否” → 自动寻找 `<任务名>_2.json`、`_3.json`……
- 选择“取消” → 放弃创建。

向导点“生成任务并打开编辑器”后不会立即写盘，而是创建 `CaseModel` 并打开 `TaskEditDialog`。只有用户在编辑器点击保存，才调用 `save_task_json()`。

保存成功后：

1. 刷新任务库/队列。
2. 将新任务加入主界面队列。
3. 自动选中新任务。
4. 状态栏显示保存路径。

任务 JSON 结构：

```json
{
  "case_id": "P1后处理usb",
  "name": "P1后处理usb",
  "app": {
    "window_title_contains": "CrealityScan",
    "device_uri": "Windows:///",
    "log_dir": "..."
  },
  "keywords": ["Traceback", "Exception", "ERROR", "失败", "崩溃"],
  "steps": [
    {
      "id": "crealityscan.configure_scan_params_p1",
      "version": "1.0.0",
      "name": "扫描参数：散斑-中物体-几何",
      "params": {"preset": "p1.speckle.medium.geometry"},
      "on_fail": {"action": "abort"}
    }
  ]
}
```

连接方式当前没有单独写入 `CaseModel.app`；它通过任务名和选中的连接专属 preset 间接体现。不要误把 `app.device_uri=Windows:///` 当成 USB/Wi-Fi 类型。

## 9. 错误处理和校验

向导/生成器已覆盖的错误：

| 场景 | 当前行为 |
|---|---|
| 未选择模组 | 第一步“下一步”禁用 |
| 未选择模式 | 第二步“下一步”禁用；直接调用时弹出“至少选择一个” |
| 任务名为空 | 第三步禁止生成并弹出错误 |
| preset 文件不存在 | 显示“preset 读取失败”或弹出具体路径错误 |
| preset JSON 非法 | 弹出 JSON 解析错误 |
| preset 顶层缺少列表 | 弹出“缺少 presets 列表” |
| preset 已删除或不适用当前连接 | `build_task_model()` 抛出“preset 已不存在或不可用” |
| 目标帧数非法 | 生成器拒绝非整数、布尔值、<1 或 >100000 |
| 同名任务 | 覆盖、自动加序号或取消 |
| 任务编辑器保存失败 | 弹出具体异常，不接受对话框 |

生成器只捕获并转换明确的文件/JSON问题；主界面 `_create_task()` 捕获 `KeyError`、`OSError`、`TypeError`、`ValueError`。复刻时不要用一个宽泛 `except Exception` 吞掉生成错误。

## 10. 迁移到另一份代码的最短路径

如果目标代码与本项目同源，优先迁移现有实现，不要根据截图重写：

1. 整体迁移 `jens_platform/task_generator.py`。
2. 迁移 `jens_platform/dialogs.py` 中：
   - task generator 相关 import；
   - 完整 `TaskCreationWizardDialog` 类。
3. 迁移 `jens_platform/main.py` 中：
   - `TaskCreationWizardDialog`、`build_task_model` import；
   - 主界面的“新建任务”按钮及 `_create_task()`；
   - `_resolve_task_path()`、`_edit_task_path()`、`_safe_task_stem()`；
   - 保存后刷新和入队逻辑。
4. 确保 `CaseModel`、`CaseStep`、`save_task_json()` 接口兼容。
5. 确保参数配置 step 与 `presets.json` 被同步迁移。
6. 打包配置必须包含 `steps/` 资源。
7. 迁移下面的自动化测试并全部通过。

不要把每个 preset 复制到 Qt 代码中；否则模式新增、改名、连接属性变化后，创建页不会更新。

## 11. 测试与验收

核心测试：

```powershell
python -m unittest tests.test_task_generator tests.test_task_creation_wizard
```

建议同时运行相关回归：

```powershell
python -m unittest tests.test_task_generator tests.test_task_creation_wizard tests.test_task_return_home tests.test_task_manager_dialog
```

### 11.1 当前仓库测试基线说明

2026-08-16 实测 `tests.test_task_generator` 与 `tests.test_task_creation_wizard` 共 18 项，其中 16 项通过、2 项失败。失败原因相同：

```text
Raptor Pro 的 presets.json 当前有 21 个模式，
但下面两个测试仍硬编码 assertEqual(..., 22)：

tests/test_task_generator.py:test_raptor_variants_use_their_own_configure_steps
tests/test_task_creation_wizard.py:test_raptor_variants_are_separate_module_choices
```

这是 preset 变更后测试数量断言未同步，不是动态发现或步骤生成失败。另一台 Codex 落实时应先把这两个断言改为验证关键模式/配置 step/连接过滤行为，避免继续硬编码会随 preset 增删而变化的总数；如果目标分支要求锁定产品模式清单，也可以把期望值同步为该分支当时的真实数量。

必须通过的行为清单：

- [ ] 向导能显示全部已注册模组。
- [ ] Otter Lite 与 Otter Lite Basic 是两个独立选项。
- [ ] Raptor、Raptor X、Raptor Pro 是三个独立选项，使用各自参数配置 step。
- [ ] 修改 `presets.json` 后点击“刷新 preset”即可看到新模式。
- [ ] USB/Wi-Fi 切换会过滤专属模式并清理不兼容选择。
- [ ] 所有无标记点模式在 Wi-Fi 下不可见。
- [ ] 第二步支持多选、搜索、分类、全选当前结果和清空。
- [ ] 目标帧数默认 200，并写进每个最终扫描步骤。
- [ ] 随机模式固化为任务 JSON 中的实际顺序。
- [ ] 普通模式、框架点模式生成不同步骤链。
- [ ] Pika 自动加入 1–3 秒等待，不添加连接设备步骤。
- [ ] Pika 框架点切点云前无预览、切点云后有预览。
- [ ] 后处理始终有融合和封装，贴图遵循优先级规则。
- [ ] 生成后先打开任务编辑器，保存后才写入 `tasks/*.json`。
- [ ] 业务步骤全部成功后仅由执行器追加一次“返回首页”。
- [ ] 打包版能从 `_internal/steps` 读取 preset。

## 12. 已知边界与改进建议

这些是当前真实实现的边界，复刻时先保持一致，不要偷偷改变行为：

1. **模组不是全自动发现**：新增参数配置目录后仍需注册 `MODULE_PRESET_SOURCES`。
2. **连接方式不写入任务结构**：报告若拿不到运行时设备信息，不能仅凭 `app.device_uri` 判断 USB/Wi-Fi。
3. **大量 preset 依赖命名推断**：当前 268 条 preset 中没有显式 `task_profile`，只有少量显式 `connections`。
4. **UI 的预计步骤数是近似值**：真实步骤数以 `build_task_model()` 输出为准。
5. **分类是中文名称启发式**：新增命名体系可能被误分到“散斑”。
6. **向导的 `randomized` 返回值未持久化**：持久化的是打乱后的顺序，不记录“这是随机任务”的元数据。

后续若要重构，优先把下面元数据显式写入 preset，而不是继续堆叠名称判断：

```json
{
  "connections": ["usb"],
  "task_profile": "frame_points",
  "category": "框架点",
  "postprocess": {
    "texture": true
  }
}
```

但这属于下一阶段数据模型升级，不是复刻当前功能的必要条件。

## 13. 代码定位索引

- `jens_platform/dialogs.py:316`：`TaskCreationWizardDialog` 起点。
- `jens_platform/dialogs.py:489`：连接方式选择器。
- `jens_platform/dialogs.py:527`：第一页模组页面。
- `jens_platform/dialogs.py:586`：第二页 preset 多选页面。
- `jens_platform/dialogs.py:674`：第三页生成方式页面。
- `jens_platform/dialogs.py:869`：动态重新读取 preset。
- `jens_platform/dialogs.py:998`：随机模式顺序。
- `jens_platform/dialogs.py:1147`：向导前进与最终校验。
- `jens_platform/dialogs.py:1173`：向导输出值。
- `jens_platform/task_generator.py:35`：模组注册表。
- `jens_platform/task_generator.py:157`：preset 动态解析与连接过滤。
- `jens_platform/task_generator.py:247`：普通扫描步骤。
- `jens_platform/task_generator.py:261`：框架点扫描步骤。
- `jens_platform/task_generator.py:280`：后处理贴图判定。
- `jens_platform/task_generator.py:309`：完整任务步骤拼装。
- `jens_platform/task_generator.py:350`：`build_task_model()`。
- `jens_platform/main.py:707`：主界面“新建任务”按钮。
- `jens_platform/main.py:1631`：同名任务路径处理。
- `jens_platform/main.py:1684`：新建任务主流程。
- `jens_platform/dialogs.py:2565`：任务编辑器最终保存。
- `jens_platform/case_store.py:27`：任务数据模型。
- `engine/executor.py:102`：成功后返回首页。
- `tests/test_task_generator.py`：步骤与业务规则测试。
- `tests/test_task_creation_wizard.py`：向导交互测试。

## 14. 可直接交给另一台 Codex 的任务说明

```text
请阅读“创建任务重构文档/README.md”，按当前实现复刻 Qt 新建任务功能。

要求：
1. 保持三步向导：模组与连接 → 扫描模式多选 → 生成方式。
2. 模式必须动态读取各模组 configure_scan_params_*/v1_0_0/presets.json，禁止在 UI 写死。
3. USB/Wi-Fi 在第一页选择，只过滤支持连接区分的模组模式，不生成连接设备步骤。
4. 目标帧数默认 200，范围 1–100000。
5. 支持随机打乱已选模式，最终任务固化打乱后的顺序。
6. 严格实现普通、框架点、后处理贴图和 Pika 等待规则。
7. Pika 框架点切点云前不预览，切点云后必须预览。
8. 不要把 return_home 写入任务 JSON；它由执行器在成功后追加。
9. 生成后打开现有任务编辑器，用户保存后再写入 tasks/*.json 并加入队列。
10. 迁移并通过 test_task_generator.py 和 test_task_creation_wizard.py。

实施前先对照文档列出的源文件与函数；若目标分支接口不同，保持行为一致并说明适配点。
```
