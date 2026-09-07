# 后处理对比工具 —— macOS 重构交接包

本目录用于把 Windows 版「CrealityScan 后处理对比工具」（`工具/后处理对比工具`）重构为 **macOS 版**。
里面的内容是为 Mac 端 agent 准备的全部参考材料 + 一份重构提示词。

## 目录结构

```
后后处理对比mac重构/
├─ 提示词.md                    ← ★ 给 Mac agent 的重构任务书（先读这个）
├─ requirements-mac.txt         ← Mac 版依赖清单
├─ README.md                    ← 本说明
└─ reference/
   ├─ pc_tool/                  ← Windows 版完整源码（功能与逻辑的事实来源）
   │  ├─ README.md
   │  ├─ requirements.txt
   │  ├─ cli.py
   │  ├─ postprocess_compare/   ← 主编排 / 进程管理 / Excel 对比表 / Qt GUI
   │  ├─ setps/                 ← 6 个自动化步骤（含模板图 templates/*.png）
   │  └─ docs/                  ← 需求 / 设计 / 产品文档
   └─ mac_poc/                  ← 已在 Mac 上验证过的 PyAutoGUI 原型（自动化底座）
      └─ mac_pyautogui_poc/
         ├─ desktop_api.py      ← PyAutoGUI 桌面封装（直接复用）
         ├─ runner.py / registry.py / runtime.py
         ├─ steps/              ← 移植范式
         └─ requirements-mac.txt
```

## 怎么用

1. 把这个目录整体拷到 Mac 上（或让 Mac agent 直接读取）。
2. 让 Mac agent 阅读 `提示词.md`，按其中的需求合同、移植规格、验收标准逐步重构。
3. 参考材料只读，不要改动；Mac 版产物建议输出到新的 `mac后处理对比工具/` 目录。

## 要点速览

- Windows 版依赖 Airtest(Windows 桌面)/pywinauto/ctypes，Mac 上不可用，需用 PyAutoGUI + AppleScript 重写桌面交互。
- 模板图（`reference/pc_tool/setps/*/v1_0_0/templates/*.png`）原样拷进 Mac 工程复用。
- 固定坐标点击（如 `(160,285)` 等）按 1920×1080 定义，Mac 上需按实际分辨率处理或重新采集。
- 日志目录 / Extensions 下载包目录在 macOS 上的默认路径需真机确认，做成可配置。
- 必须保留：双版本串行、双副本隔离、导入/下载/进度等待与心跳日志、运行日志、截图留证、对比表。

详细要求见 `提示词.md`。
