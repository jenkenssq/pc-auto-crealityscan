# Product

<!-- impeccable:product-schema 1 -->

## Platform

Windows desktop (PyQt5)

## Users

主要用户是负责 CrealityScan 发布验证与回归测试的自动化测试工程师。他们需要在 Windows 测试机上，对同一批工程执行两个软件版本的相同后处理流程，并人工比较结果。

## Product Purpose

该工具通过一次配置，串行驱动发布版和测试版 CrealityScan 完成相同后处理任务，保留隔离工程副本、截图、耗时与日志。成功意味着测试人员可以稳定复现两个版本的处理过程，并快速定位可供人工比较的结果材料。

## Positioning

产品的核心机制是对同一来源工程创建两份隔离工作副本，并用同一套 Airtest Step 严格串行控制两个 CrealityScan 版本，避免源工程污染、并行进程冲突和步骤差异。

## Operating Context

工具运行在安装了 Python、PyQt5、Airtest、pywinauto 和两个 CrealityScan 可执行文件的 Windows 测试机上。用户选择对比类型、两个版本及标签、原始工程集与输出目录，启动后观察步骤状态和实时日志，完成后打开时间戳结果目录进行人工比较。

## Capabilities and Constraints

- 每次运行只能选择贴图、高斯渲染、AI重贴图或人体补全其中一种操作。
- 发布版处理全部工程并退出后，测试版才开始处理。
- 原始工程不能被直接导入或修改。
- 发布版和测试版 EXE 路径必须不同。
- 输出目录不能位于原始工程集内部。
- 运行过程中只能存在一个受控 CrealityScan 进程。
- 工程导入完成以日志标记 `OB_SCAN_MESSAGE_ID_PROJECT_IMPORT_SUCCESS` 或 `i proj progress 1.000000`（任一命中）为准。
- 当前不生成 HTML 报告，不做图像质量评分，也不自动判断优胜版本。
- 本次 GUI 重构保持业务流程、字段顺序、中文文案和 CLI 参数映射不变。

## Brand Commitments

保留产品名称“CrealityScan后处理对比平台”、中文界面和面向工程测试的专业语气。界面应优先表达可追溯、可诊断和安全执行，不引入营销化表达。

## Evidence on Hand

- 当前行为与使用方式：`README.md`
- GUI 实现：`postprocess_compare/qt_app.py`
- CLI 编排：`postprocess_compare/cli.py`
- Airtest 步骤与模板：`setps/`
- 示例工程与输出材料：`工程集/`、`结果工程集/`、`artifacts/`
- 没有真实品牌图像、用户研究或自动化质量评分数据，不得在界面中虚构。

## Product Principles

- 先保护源工程，再追求执行效率。
- 任何异步步骤都必须以可验证信号完成。
- 运行状态、失败原因和结果位置必须清晰可追溯。
- 高风险操作保持明确、克制并可中止。
- 视觉表达服务于扫描效率，不遮蔽任务和状态。

## Accessibility & Inclusion

桌面界面保持键盘可操作、清晰焦点态、足够文字与控件对比度，并在常见 Windows 缩放比例下保持信息可读。
