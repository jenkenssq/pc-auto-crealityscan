---
name: Jens 自动化测试平台
description: 面向高频扫描自动化操作的冷蓝灰桌面工作台
colors:
  primary: "#2e6fd8"
  primary-deep: "#2358aa"
  canvas: "#eaf0f8"
  surface: "#ffffff"
  surface-soft: "#f6f9fd"
  ink: "#18283d"
  muted: "#65758b"
  line: "#d5dfec"
  success: "#167553"
  warning: "#9a5e12"
  danger: "#b43b3b"
typography:
  title:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, sans-serif"
    fontSize: "21px"
    fontWeight: 700
  body:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 400
  label:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, sans-serif"
    fontSize: "11px"
    fontWeight: 700
rounded:
  control: "9px"
  panel: "12px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "22px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    height: "34px"
    padding: "0 13px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "28px"
    padding: "6px 8px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "14px 16px"
---

# Design System: Jens 自动化测试平台

## Overview

**Creative North Star: "扫描运行台"**

Jens 是一套服务操作而非展示品牌的桌面视觉系统。它采用冷蓝灰背景、稳定的深色导航和高信息密度白色工作区，让任务队列、设备上下文与运行结果保持清晰分区。界面表达集中在精确状态、可靠层级和一致控件上，不用装饰性 Hero 或营销式大卡片抢占操作空间。

**Key Characteristics:**

- 运行优先的信息架构
- 单一蓝色主操作语义
- 清晰的成功、警告、失败状态
- 紧凑但不拥挤的桌面密度
- 中文任务术语和可发现的恢复路径

## Colors

色彩以冷蓝灰中性色为主，蓝色只表示主操作、当前选择或焦点，状态色只表达真实运行状态。

**The One Accent Rule.** 同一操作区域只保留一个蓝色主按钮；普通入口使用白底次级按钮。

任务队列标题栏中的“新建任务”允许使用主蓝色高亮，作为创建入口；顶部“运行队列”属于全局执行区域，两者不在同一操作组。

**The Honest State Rule.** 成功、警告和失败色必须与实际状态一致，失败页不能使用成功文案或假定产物存在。

## Typography

界面统一使用 Microsoft YaHei UI，并以 Segoe UI 作为后备。标题、正文和标签使用紧凑字阶，技术日志与 JSON 参数可以使用系统等宽字体。

**The Native Label Rule.** 按钮、导航、字段和数据表使用中文业务术语；步骤 ID 等技术标识只在排障信息中保留英文。

## Layout

主窗口采用固定左侧导航与可伸缩工作区。工作区顶部是全局运行操作，中部由任务队列和运行上下文组成，下部是日志与步骤结果。常用间距遵循 4、8、12、16、22 像素节奏。复杂创建流程使用分步弹窗与持续可见摘要；长时操作优先留在工作区。

运行时必须锁定所有会改变执行上下文的入口。批量任务只允许从第一步完整执行；单任务才允许选择中间起始步骤。

## Elevation & Depth

系统以背景分层和单像素边界建立深度，不依赖大面积阴影。侧栏、画布、白色面板和浅色子面板形成四级空间关系；弹窗由操作系统窗口层级承担浮起感。

**The Flat Workspace Rule.** 工作面板在静止状态保持平坦；边框和背景足以表达归属，不叠加装饰性阴影。

## Shapes

输入和按钮使用轻微圆角，面板使用更宽但受控的圆角。小状态标签可以使用紧凑圆角；大面积胶囊和高圆角卡片不属于此系统。

## Components

### Buttons

- 主按钮使用蓝底白字，表示当前区域唯一的主要动作。
- 次级按钮使用白底细边框，悬停时转为浅蓝灰。
- 停止和删除使用危险语义，保持白底红字以避免过度抢占注意力。
- 所有按钮具备 hover、pressed、focus 和 disabled 状态。

### Cards / Containers

- 面板使用白色背景、单像素冷灰边界和 12px 圆角。
- 内部子面板使用浅灰蓝背景，避免嵌套白卡片。
- 空态必须说明用户下一步可以做什么。

### Inputs / Fields

- 输入框使用白底、冷灰边界和 9px 圆角。
- 聚焦时边界切换为主蓝色；错误时使用红色边界、浅红背景和可读错误文案。
- 无效 JSON 等配置错误必须阻止保存，不能静默保留旧值。

### Navigation

- 左侧导航使用深海军蓝背景，只承载稳定工作区和工具入口；“新建任务”等一次性动作放在内容区按钮中。
- 当前工作区使用实心主蓝色；临时动作完成后返回“运行工作台”选中态。
- 运行时禁用所有可能改变上下文的导航入口。

## Do's and Don'ts

### Do:

- **Do** 让用户始终看见“现在能否运行、正在运行什么、失败后从哪里复盘”。
- **Do** 在长列表、任务库和队列中提供搜索、空态、数量和明确选择反馈。
- **Do** 使用集中运行状态驱动按钮、导航、队列和环境控件。
- **Do** 保持 preset 动态驱动，新增模式无需修改 UI 枚举。

### Don't:

- **Don't** 在同一页面重复提供多组新建、编辑和运行入口。
- **Don't** 在运行中允许修改队列、日志目录、任务或设备控制上下文。
- **Don't** 对非法输入静默失败或只禁用按钮而不解释原因。
- **Don't** 用宣传性 Hero、装饰渐变或同尺寸卡片网格代替操作信息。
