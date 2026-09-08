# Product

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

## Users

三维扫描产品线的自动化测试工程师，在 Windows 桌面环境中高频创建、编排并运行 CrealityScan 自动化任务。

## Product Purpose

Jens 自动化平台将扫描模组、扫描参数预设与标准步骤组合成可运行、可复用的任务。创建任务时，用户需要先选择模组，再多选扫描模式，最后选择开流或后处理并确认生成结果。

## Operating Context

- 主平台为 PyQt 桌面应用，任务保存在 `tasks/*.json`。
- 扫描模式来自 `steps/crealityscan/configure_scan_params_*/v1_0_0/presets.json`。
- 开流任务完成配置与扫描；后处理任务在扫描后继续执行融合、封装和按规则执行贴图。
- Pika 任务需要按既有任务模板自动插入稳定性等待步骤。

## Capabilities and Constraints

- 创建任务流程必须支持全部已配置模组，并支持一次选择多个扫描模式。
- P1、Pika、S1、X1 存在 USB / Wi-Fi 任务变体；连接方式只在适用模组显示。
- 框架点模式需要额外的暂停与切点云流程，由生成规则自动补齐。
- 设计阶段先交付独立 HTML 交互稿，用户确认后才修改 Qt 页面和任务生成逻辑。

## Product Principles

- 用户只选择业务意图，底层步骤由规则可靠生成。
- 自动插入的等待、框架点和后处理步骤必须在生成前透明可见。
- 多选模式时持续显示已选数量与预计任务规模，避免误生成超长任务。
- 延续现有桌面平台的中文术语和浅蓝灰操作界面。

## Accessibility & Inclusion

支持键盘操作、清晰焦点状态和高对比度中文界面。
