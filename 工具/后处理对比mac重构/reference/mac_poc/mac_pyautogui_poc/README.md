# mac PyAutoGUI 验证原型

这个目录是一套独立的 `PyAutoGUI` 验证原型，用来在**不改动主工程**的前提下，验证 macOS 桌面自动化是否可行。

## 当前已迁移的核心 step

- `crealityscan.create_project`
- `crealityscan.create_scan`
- `crealityscan.configure_scan_params_otter_lite`
- `crealityscan.import_project`
- `crealityscan.view_logs`

## 默认验证链路

默认样例文件：

- [example_case.json](/D:/自动化工具/自动化脚本/pc自动化工具/output/mac_pyautogui_poc/example_case.json)

执行顺序：

- `create_project -> create_scan -> configure_scan_params -> view_logs`

这个链路适合先验证以下能力：

- 模板图定位点击
- 固定坐标点击
- 鼠标移动复位
- 截图留证
- 报告生成

## 导入工程验证链路

备用样例文件：

- [example_case_import_project.json](/D:/自动化工具/自动化脚本/pc自动化工具/output/mac_pyautogui_poc/example_case_import_project.json)

执行顺序：

- `import_project -> view_logs`

这个链路适合单独验证“导入工程”相关模板图是否在 mac 上仍然稳定可用。

## 这套原型复用了什么

- 主工程 `steps/.../templates` 下的原始模板图
- 主工程 `presets.json`
- 主工程 `engine/report_html.py` 的 HTML 报告渲染

## 这套原型主动去掉了什么

- Windows 专用窗口激活
- Airtest 桌面设备连接
- 每步前自动抢前台焦点

也就是说，这套原型默认前提是：

- `CrealityScan` 已经手动放到前台
- 软件窗口保持可见
- 运行期间不要切走焦点

## 运行前提

运行前请确认：

- `CrealityScan` 已经打开，并且位于主屏前台
- 主屏分辨率与样例 case 中配置一致
- macOS 已给 Terminal / Python 授予：
- 屏幕录制权限
- 辅助功能权限

## 安装依赖

```powershell
python -m pip install -r output/mac_pyautogui_poc/requirements-mac.txt
```

## 运行方式

运行默认验证链路：

```powershell
python output/mac_pyautogui_poc/runner.py --case output/mac_pyautogui_poc/example_case.json
```

运行导入工程验证链路：

```powershell
python output/mac_pyautogui_poc/runner.py --case output/mac_pyautogui_poc/example_case_import_project.json
```

## 产物输出

运行产物会写到：

- [artifacts](/D:/自动化工具/自动化脚本/pc自动化工具/output/mac_pyautogui_poc/artifacts)

每次运行会生成一个时间戳目录，目录内通常包含：

- `result.json`
- `report.html`
- `screenshots/`

## 目录说明

- [desktop_api.py](/D:/自动化工具/自动化脚本/pc自动化工具/output/mac_pyautogui_poc/desktop_api.py)
- `PyAutoGUI` 桌面交互封装
- [runner.py](/D:/自动化工具/自动化脚本/pc自动化工具/output/mac_pyautogui_poc/runner.py)
- 原型执行入口
- [registry.py](/D:/自动化工具/自动化脚本/pc自动化工具/output/mac_pyautogui_poc/registry.py)
- step 注册表
- [steps](/D:/自动化工具/自动化脚本/pc自动化工具/output/mac_pyautogui_poc/steps)
- 已迁移的 step 实现

## 当前目标

这套原型不是为了立即替换主工程，而是先验证这几个关键问题：

- `PyAutoGUI` 找图点击在 mac 上是否稳定
- 固定坐标在 mac 上是否无偏移
- 去掉窗口控制后，整条链路是否还能稳定执行

如果这些问题验证通过，再继续迁移：

- `fusion_operation`
- `texture_operation`
- `package_operation`

这几类长流程 step。
