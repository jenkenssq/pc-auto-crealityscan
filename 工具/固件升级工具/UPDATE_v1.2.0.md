# v1.2.0 更新说明 - 固件升级流程优化

## 更新日期
2026-03-12

## 更新概述
根据用户反馈，优化了固件升级流程和开流验证逻辑，增加了通过日志文件监控设备状态的功能。

## 主要更新

### 1. 固件升级流程优化 ✨

#### 文件选择对话框处理改进
- **问题**：之前简单地输入路径+Enter，可能无法正确处理Windows文件对话框
- **改进**：
  - 使用pywinauto库正确操作Windows文件选择对话框
  - 在文件名输入框中输入路径
  - 点击"打开"按钮确认选择
  - 如果pywinauto失败，自动降级到键盘输入方式

#### 升级确认弹窗处理
- **新增**：选择固件文件后，会弹出"是否立即升级"的确认对话框
- **处理**：
  - 新增 `upgrade_confirm.png` UI元素
  - 点击确认按钮后才开始升级
  - 如果没有专门的升级确认按钮截图，自动使用通用确定按钮

#### 设备重连验证 - 通过日志监控
- **问题**：之前只是简单等待10秒，无法准确判断设备是否重连
- **改进**：
  - 通过读取CrealityScan软件日志文件来监控设备状态
  - 检测设备掉线关键字：`["设备断开", "设备掉线", "device offline", "device disconnected"]`
  - 检测设备上线关键字：`["设备连接", "设备上线", "device online", "device connected"]`
  - 实时监控日志文件的新增内容
  - 如果未配置日志路径，降级到简单等待方式

### 2. 开流验证逻辑优化 ✨

#### 彩色视窗动态检测
- **问题**：不是所有模式都有彩色视窗，之前会尝试验证所有相机
- **改进**：
  - 通过读取日志文件判断当前模式是否有彩色视窗
  - 检测彩色相机关键字：`["彩色相机", "彩色视窗", "color camera", "RGB camera"]`
  - 检测无彩色关键字：`["无彩色", "no color", "IR only"]`
  - 如果没有彩色视窗，跳过彩色相机的验证
  - 如果未配置日志路径，默认假设有彩色视窗

### 3. 配置文件更新

#### app_config.yaml 新增配置项
```yaml
app:
  # 日志文件路径（用于监控设备状态和判断彩色视窗）
  log_file_path: ""  # 例如: "C:\\Users\\YourName\\AppData\\Local\\CrealityScan\\logs\\app.log"
```

**配置说明**：
- 如果配置了日志文件路径，框架会使用日志监控功能
- 如果未配置，框架会使用简化逻辑（等待固定时间）
- 建议配置日志路径以获得更准确的测试结果

## 新增UI截图需求

### 必需截图
无新增必需截图

### 可选截图（推荐）
1. **upgrade_confirm.png** - "是否立即升级"确认对话框的"确定"按钮
   - 如果与通用确定按钮样式相同，可以省略
   - 框架会自动降级使用通用确定按钮

## 文件更新清单

### 核心代码
1. **core/firmware_handler.py**
   - 改进 `_select_firmware_file()` 方法 - 使用pywinauto处理文件对话框
   - 改进 `_confirm_upgrade()` 方法 - 处理升级确认弹窗
   - 重写 `_verify_device_reconnect()` 方法 - 通过日志监控设备状态
   - 新增 `_monitor_device_reconnect_by_log()` 方法 - 日志监控实现

2. **core/stream_handler.py**
   - 改进 `_verify_stream_success()` 方法 - 动态判断是否需要验证彩色相机
   - 新增 `_check_color_camera_from_log()` 方法 - 通过日志判断彩色视窗

3. **testcases/test_firmware_upgrade.py**
   - 添加日志文件路径配置传递逻辑

### 配置文件
1. **config/app_config.yaml**
   - 新增 `log_file_path` 配置项

### 文档
1. **UPDATE_v1.2.0.md** - 本文档

## 使用指南

### 配置日志文件路径

1. 找到CrealityScan的日志文件位置
   - 通常在：`C:\Users\<用户名>\AppData\Local\CrealityScan\logs\`
   - 或者在CrealityScan安装目录下的logs文件夹

2. 编辑 `config/app_config.yaml`
```yaml
app:
  log_file_path: "C:\\Users\\YourName\\AppData\\Local\\CrealityScan\\logs\\app.log"
```

3. 确保日志文件路径正确且可读

### 日志关键字自定义

如果默认的关键字不匹配你的日志格式，可以修改代码中的关键字列表：

**设备状态关键字**（`core/firmware_handler.py`）：
```python
offline_keywords = ["设备断开", "设备掉线", "device offline", "device disconnected"]
online_keywords = ["设备连接", "设备上线", "device online", "device connected"]
```

**彩色视窗关键字**（`core/stream_handler.py`）：
```python
color_keywords = ["彩色相机", "彩色视窗", "color camera", "RGB camera"]
no_color_keywords = ["无彩色", "no color", "IR only"]
```

## 测试流程变化

### 固件升级流程（更新后）
```
点击"选择文件"
    ↓
弹出Windows文件选择对话框
    ↓
在文件名输入框输入路径
    ↓
点击"打开"按钮
    ↓
返回软件，弹出"是否立即升级"确认对话框 ✨新增
    ↓
点击"确定"确认升级 ✨新增
    ↓
开始升级
    ↓
监控日志，检测"升级成功"提示
    ↓
监控日志，检测设备掉线 ✨改进
    ↓
监控日志，检测设备上线 ✨改进
    ↓
关闭设置页
```

### 开流验证流程（更新后）
```
点击扫描
    ↓
等待渲染
    ↓
读取日志，判断是否有彩色视窗 ✨新增
    ↓
验证IR相机（必需）
    ↓
验证彩色相机（如果有） ✨动态判断
    ↓
验证成功
```

## 兼容性说明

- **向后兼容**：如果未配置日志文件路径，框架会自动降级到简化逻辑
- **UI截图兼容**：新增的 `upgrade_confirm.png` 是可选的，如果没有会自动使用通用确定按钮
- **日志格式兼容**：如果日志关键字不匹配，可以自定义修改

## 已知限制

1. **日志文件编码**：假设日志文件为UTF-8编码，如果是其他编码可能需要调整
2. **日志关键字**：默认关键字可能不适用所有版本的CrealityScan，需要根据实际情况调整
3. **文件对话框**：pywinauto可能在某些Windows版本或配置下失败，会自动降级到键盘输入

## 升级步骤

1. 更新代码文件：
   - `core/firmware_handler.py`
   - `core/stream_handler.py`
   - `testcases/test_firmware_upgrade.py`
   - `config/app_config.yaml`

2. 配置日志文件路径（推荐）

3. 运行测试验证

## 反馈与支持

如果遇到问题：
1. 检查日志文件路径是否正确
2. 检查日志关键字是否匹配
3. 查看测试日志了解详细错误信息

---

**版本**: v1.2.0
**作者**: 测试团队
**日期**: 2026-03-12
