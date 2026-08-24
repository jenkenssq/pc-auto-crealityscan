---
name: "CrealityScan 后处理对比平台"
description: "让配对配置、串行执行状态与结果证据同时可见的校准工作台。"
colors:
  cobalt-action: "#0a66c2"
  cobalt-hover: "#095aa9"
  cobalt-pressed: "#074d91"
  shell-cool: "#f3f6f8"
  console-frost: "#edf2f5"
  card-white: "#ffffff"
  sidebar-graphite: "#18232e"
  log-ink: "#111a22"
  text-graphite: "#25313c"
  field-text: "#263640"
  text-muted: "#5d6d79"
  field-label: "#4f606e"
  border-cool: "#bdcad4"
  state-idle-soft: "#dfe7ec"
  state-running: "#ad7416"
  state-running-soft: "#f4e4bf"
  state-success: "#26815d"
  state-success-soft: "#d6eadf"
  state-error: "#bd3d3d"
  state-error-soft: "#f1dada"
typography:
  display:
    fontFamily: "IBM Plex Sans SC, Microsoft YaHei UI, sans-serif"
    fontSize: "28px"
    fontWeight: 600
  brand:
    fontFamily: "IBM Plex Sans SC, Microsoft YaHei UI, sans-serif"
    fontSize: "22px"
    fontWeight: 600
  title:
    fontFamily: "Microsoft YaHei UI, sans-serif"
    fontSize: "17px"
    fontWeight: 700
  body:
    fontFamily: "Microsoft YaHei UI, sans-serif"
    fontSize: "12px"
    fontWeight: 400
  control:
    fontFamily: "Microsoft YaHei UI, sans-serif"
    fontSize: "12px"
    fontWeight: 700
  label:
    fontFamily: "Microsoft YaHei UI, sans-serif"
    fontSize: "11px"
    fontWeight: 600
  log:
    fontFamily: "Consolas, monospace"
    fontSize: "9pt"
    fontWeight: 400
rounded:
  control: "8px"
  log: "10px"
  state-pill: "11px"
  panel: "12px"
spacing:
  compact: "7px"
  control: "8px"
  row: "9px"
  cluster: "14px"
  panel-tight: "18px"
  section: "20px"
  panel: "22px"
  frame: "24px"
  header: "28px"
  wide: "32px"
components:
  button-primary:
    backgroundColor: "{colors.cobalt-action}"
    textColor: "{colors.card-white}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "10px 14px"
  button-primary-hover:
    backgroundColor: "{colors.cobalt-hover}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.control}"
    padding: "10px 14px"
  button-primary-pressed:
    backgroundColor: "{colors.cobalt-pressed}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.control}"
    padding: "10px 14px"
  input:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.field-text}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
    height: "20px minimum"
  card:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.text-graphite}"
    rounded: "{rounded.panel}"
    padding: "20px 22px 18px"
  state-idle:
    backgroundColor: "{colors.state-idle-soft}"
    textColor: "{colors.text-muted}"
    typography: "{typography.label}"
    rounded: "{rounded.state-pill}"
    padding: "4px 10px"
    height: "26px"
  step-active:
    backgroundColor: "{colors.cobalt-action}"
    textColor: "{colors.card-white}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "6px 10px"
    height: "32px"
  step-success:
    backgroundColor: "{colors.state-success}"
    textColor: "{colors.card-white}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "6px 10px"
    height: "32px"
  log-panel:
    backgroundColor: "{colors.log-ink}"
    textColor: "{colors.state-idle-soft}"
    typography: "{typography.log}"
    rounded: "{rounded.log}"
    padding: "12px"
---

# Design System: CrealityScan 后处理对比平台

## Overview

**Creative North Star: "校准工作台"**

这是一个服务于自动化测试工程师的仪器式工作台：冷色表面承载配置，石墨文字建立稳定读序，钴蓝只标记可执行动作和当前步骤。界面不追求“数据大屏”的观感，而是让一次配对对比从路径校验、串行执行到结果打开始终处于同一视野。

空间与状态都服从可追溯性。左侧导航稳定定位，中部按顺序完成配置，右侧固定执行控制台持续暴露步骤、日志、总状态和启停操作；视觉层级来自表面色阶、边界与密度，不来自装饰性图表。

**Key Characteristics:**

- 冷色仪器表面与石墨文字形成低干扰、长时间可读的工作环境。
- 钴蓝是唯一主操作色，只用于当前选择、焦点、启动动作和执行中的步骤。
- 紧凑而可测量的间距、固定栏宽和对齐标签支持快速扫描。
- 待机、运行、成功、失败拥有明确且一致的颜色语义。
- 配置、执行状态和证据同时可见，不引入仪表盘装饰。

## Colors

色彩以冷灰表面为基底，以单一钴蓝建立操作主线，并用克制的琥珀、绿色和红色表达运行语义。

### Primary

- **校准钴蓝**：用于主按钮、已选分段、输入焦点与活动步骤，是屏幕上唯一的高强调操作色。
- **深钴蓝状态**：悬停与按下逐级加深，使操作反馈明确但不产生浮夸动效。

### Neutral

- **冷雾工作面**：应用于应用壳层和右侧执行台，以轻微色阶区分区域而不制造卡片堆叠。
- **白色校准卡**：只承载主配置容器、输入和常规按钮，保持内容面清晰。
- **石墨侧栏**：固定导航的深色锚点，也作为提示与品牌区域的背景。
- **日志墨黑**：限定在实时日志证据区，建立与配置控件不同的证据材质。
- **石墨正文与冷灰辅助字**：主次文字不只依赖字号差异，颜色同时参与层级。
- **冷灰边界**：用于输入、按钮、分隔与面板轮廓，避免纯装饰描边。

### Tertiary

- **运行琥珀**：只表示任务正在运行或需要注意，浅色底用于状态胶囊。
- **验证绿色**：用于有效路径、已完成步骤和成功状态。
- **故障红色**：用于失败步骤与紧急停止的悬停警示；不承担普通强调。

### Named Rules

**The One Cobalt Rule.** 钴蓝只表达当前选择、键盘焦点、主操作或活动步骤；普通信息不得争抢这条操作主线。

**The Semantic State Rule.** 同一状态在胶囊、步骤和状态点中保持同义；不得用颜色表达与运行语义无关的装饰分类。

## Typography

**Display Font:** IBM Plex Sans SC SemiBold（回退到 Microsoft YaHei UI）  
**Body Font:** Microsoft YaHei UI（回退到系统无衬线字体）  
**Label/Mono Font:** Microsoft YaHei UI；证据日志使用 Consolas

**Character:** IBM Plex Sans SC SemiBold 仅负责品牌与页标题，带来克制的工程识别度；Microsoft YaHei UI 承担中文正文和控件，保证 Windows 原生清晰度。Consolas 将日志与操作界面区分为可核验的机器证据。

### Hierarchy

- **Display**（SemiBold，28px）：只用于当前页面标题，形成首要入口。
- **Brand**（SemiBold，22px）：只用于产品品牌名称，不与页面标题竞争。
- **Title**（Bold，15–17px）：用于执行台标题和配置面板标题。
- **Body**（Regular，12px）：用于说明、字段内容、状态文字和常规按钮。
- **Label**（SemiBold/Bold，10–11px）：用于导航分组、步骤编号、状态胶囊和小型辅助标签。
- **Log**（Regular，9pt）：用于不换行的实时日志预览。

### Named Rules

**The Two-Family Rule.** 品牌与页标题使用 IBM Plex Sans SC SemiBold；正文与控件使用 Microsoft YaHei UI；只有机器日志使用 Consolas。

## Layout

首屏采用稳定的三栏工作台：左侧导航固定为 240px，中部配置区弹性占满剩余空间，右侧执行台固定为 340px。窗口默认 1480×900，最小 1180×720；低于最小尺寸不压缩关键执行证据。

外壳无间隙拼接三栏。左栏内边距为 22px/30px/24px，中栏为 32px/28px/30px/24px，右栏为 18px/26px/24px。中部以 20px 垂直节奏组织页头、对比类型、配置卡和说明；配置卡内部以 22px 水平内边距、9px 行内间距和 94px 固定标签宽度构成可扫描表单。右栏的六步执行器采用两列三行、7px 间距，每个步骤固定高 32px。

**The Fixed Console Rule.** 配置可以随窗口伸展，执行台保持固定宽度；任务状态、日志和启停按钮不得被折叠到二级页面或滚动末端。

## Elevation & Depth

系统默认无阴影。深度由冷雾壳层、白色配置卡、石墨侧栏、日志墨黑面以及 1px 冷灰边界构成；Windows 支持时应用 Mica 作为系统级背景质感，但不依赖它承载信息层级。组件在悬停、聚焦和状态变化时通过色阶与边框变化响应，而不是抬升。

**The Flat Instrument Rule.** 表面静止时保持平整；禁止为卡片、按钮或状态块添加装饰性投影。

## Shapes

控件、导航项、分段按钮和步骤块使用 8px 圆角，形成一致的仪器控制面；日志区使用 10px，状态胶囊使用 11px，主配置卡使用 12px。圆角随容器层级轻微增加，但不使用胶囊化主按钮或夸张大圆角。分隔线固定为 1px，侧栏提示仅保留顶部边界。

## Components

### Buttons

- **Shape:** 稳定的矩形控制件（8px 圆角），常规内边距为 8px 13px，主操作为 10px 14px。
- **Primary:** 校准钴蓝底与白字，700 字重；悬停和按下分别进入深一级钴蓝。
- **Hover / Focus:** 普通按钮悬停转为浅蓝表面和蓝灰边界；键盘焦点使用 1px 校准钴蓝边界。
- **Secondary / Ghost:** “查看结果”使用蓝色描边；高级参数开关无背景、左对齐；“紧急停止”默认保持中性，仅在悬停时进入浅红警示。
- **Disabled:** 灰色文字与冷灰底同时降低，仍保留边界和控件轮廓。

### Inputs / Fields

- **Style:** 白色输入面、冷灰 1px 边界、8px 圆角与 8px 10px 内边距；标签固定宽度，浏览按钮固定 56px。
- **Focus:** 焦点边界切换为校准钴蓝。
- **Valid / Invalid:** 有效路径使用柔和绿色边界并显示系统确认图标；无效路径使用琥珀边界并显示系统警告图标。
- **Disabled:** 运行期间切换为冷灰底、灰色文字和弱化边界，清楚表达配置锁定。

### Cards / Containers

- **Corner Style:** 主配置卡使用 12px 圆角；高级参数容器使用 8px 圆角。
- **Background:** 配置卡为白色，高级参数区为更浅的冷灰表面。
- **Shadow Strategy:** 无阴影，仅使用 1px 冷灰边界与表面色阶。
- **Internal Padding:** 配置卡为 22px 20px 22px 18px；高级参数区为 10px。

### Navigation

左侧导航使用石墨底和 8px 圆角项目。默认项为冷灰文字，悬停进入更亮的石墨表面，选中项使用深蓝石墨底与白字；未开放入口保持可见但禁用，并通过工具提示解释原因。

### Segmented Operation Selector

贴图与高斯渲染是互斥的并列选择，每项最小宽 112px。未选时为白底冷灰边界；选中后完整切换为校准钴蓝底、白字和 700 字重。

### Execution Console

执行台由状态胶囊、两列六步指示器、最多五行的实时日志预览、状态点和启停按钮组成。活动步骤在 360ms 周期内于两档钴蓝之间脉冲，已完成步骤为验证绿色，失败的当前步骤为故障红色；未开始步骤保持冷灰。运行时锁定所有配置，只开放紧急停止。

## Do's and Don'ts

### Do:

- **Do** 保持左导航、中配置、右执行台的首屏并存关系。
- **Do** 让路径校验、当前步骤、日志证据和结果入口使用明确的可验证状态。
- **Do** 将钴蓝保留给选择、焦点、主操作和正在执行的步骤。
- **Do** 使用真实中文工程术语与紧凑测量，不写营销式标题或虚构质量结论。
- **Do** 在新增状态时同时定义默认、运行、成功、失败和禁用表现。

### Don't:

- **Don't** 添加 KPI 卡、趋势图、装饰性统计或其他仪表盘式元素。
- **Don't** 用阴影、渐变、发光或大面积高饱和色制造层级。
- **Don't** 将日志、失败原因或结果位置隐藏在弹窗、二级页面或执行结束之后。
- **Don't** 让配置控件在任务运行中仍可编辑，也不要仅靠颜色传达路径或任务状态。
- **Don't** 混用展示字体与正文职责，或用 IBM Plex Sans SC 填满表单和日志。

**Finish Review:** ship. **Remaining:** clear.
