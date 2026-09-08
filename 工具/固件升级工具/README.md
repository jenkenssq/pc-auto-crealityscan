# CrealityScan 固件升级自动化测试框架

基于 Python + Airtest 的 Windows 应用自动化测试框架，用于测试 CrealityScan 三维扫描软件的固件升级功能。支持 USB 和 WiFi 两种连接方式。

## 功能特性

- 支持 USB 和 WiFi 设备连接
- 固件升级前后自动验证设备开流功能
- 支持多种设备系列（Sermoon S1/X1, Creality Pika, Otter, Raptor, Ferret 等）
- 图像识别 + 图像模板匹配双模式
- 日志实时监控与智能判断
- GUI 图形界面（可选命令行模式）
- 测试完成自动发送邮件通知
- 详细的日志记录和截图保存

## 项目结构

```
固件升级自动化/
├── config/                    # 配置文件
│   ├── app_config.yaml       # 应用配置
│   ├── device_config.yaml    # 设备配置
│   └── test_config.yaml      # 测试配置
├── core/                      # 核心功能模块
│   ├── app_manager.py        # 应用管理
│   ├── stream_handler.py     # 开流操作
│   └── firmware_handler.py   # 固件升级
├── gui/                       # GUI 界面
│   └── main_window.py        # 主窗口
├── utils/                     # 工具函数
│   ├── logger.py             # 日志管理
│   ├── log_manager.py        # 日志分析
│   ├── screenshot.py         # 截图工具
│   ├── email_sender.py       # 邮件通知
│   └── test_reporter.py      # 测试报告
├── testcases/                 # 测试用例
│   ├── test_firmware_upgrade.py    # 单次升级测试
│   └── test_firmware_cycle.py      # 循环升级测试
├── resources/                 # 资源文件
│   ├── images/               # UI元素截图模板
│   └── firmware/             # 固件文件
├── logs/                      # 日志输出
├── screenshots/               # 测试截图
├── reports/                   # 测试报告
├── requirements.txt           # 依赖包
├── run_test.py               # 测试入口
└── README.md                 # 说明文档
```

## 测试流程

### 1. 第一次开流操作
- 点击新建项目
- 确认弹窗
- 点击预览
- 点击扫描
- 验证点云渲染和相机出流
- 点击完成扫描
- 点击返回首页
- 确认返回（点击确定）

### 2. 固件升级
- 点击设置
- 点击设备管理
- 选择固件文件
- 确认升级
- 等待升级完成
- 验证设备重连
- 关闭设置页

### 3. 第二次开流操作
- 重复第一次开流流程
- 验证升级后功能正常

## 安装步骤

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 配置应用路径

编辑 `config/app_config.yaml`，修改 CrealityScan 的安装路径：

```yaml
app:
  exe_path: "C:\\Program Files\\CrealityScan\\CrealityScan.exe"
```

### 3. 配置设备连接

编辑 `config/device_config.yaml`：

```yaml
devices:
  default:
    name: "测试设备"
    connection_type: "wifi"  # usb 或 wifi
    ip: "192.168.1.100"      # WiFi 模式必填
    port: "8080"             # WiFi 模式必填
```

### 4. 准备 UI 元素截图（重要！）

这是框架能够正常运行的关键步骤。需要截取以下 UI 元素的图片：

#### 首页元素
- `resources/images/home/new_project.png` - "新建项目"按钮
- `resources/images/home/confirm.png` - 弹窗"确定"按钮
- `resources/images/home/settings.png` - "设置"按钮

#### 扫描页元素
- `resources/images/scan/preview.png` - "预览"按钮
- `resources/images/scan/scan.png` - "扫描"按钮
- `resources/images/scan/finish_scan.png` - "完成扫描"按钮
- `resources/images/scan/back_home.png` - "返回首页"按钮
- `resources/images/scan/ir_camera.png` - IR相机窗口特征
- `resources/images/scan/color_camera.png` - 彩色相机窗口特征
- `resources/images/scan/ir_mode_btn.png` - IR模式按钮
- `resources/images/scan/blue_laser_mode_btn.png` - 蓝光模式按钮
- `resources/images/scan/new_scan_btn.png` - 新扫描按钮
- `resources/images/scan/pika_ir_apply_btn.png` - Pika IR应用按钮

#### 设置页元素
- `resources/images/settings/device_management.png` - "设备管理"按钮
- `resources/images/settings/select_file.png` - "选择文件"按钮
- `resources/images/settings/file_dialog_open_btn.png` - 文件对话框打开按钮
- `resources/images/settings/upgrade_confirm_btn.png` - 升级确认按钮
- `resources/images/settings/upgrade_cancel_btn.png` - 升级取消按钮
- `resources/images/settings/upgrade_success.png` - 升级成功气泡
- `resources/images/settings/close_settings.png` - "关闭设置"按钮

**截图要求**：
- 使用 Windows 截图工具（Win + Shift + S）
- 只截取按钮或 UI 元素本身，不要包含过多背景
- 保存为 PNG 格式
- 确保截图清晰，分辨率适中

### 5. 准备固件文件

将固件文件放到 `resources/firmware/` 目录下。

## 使用方法

### 方式一：GUI 模式（推荐）

直接运行即可启动图形界面：

```bash
python run_test.py
```

### 方式二：命令行模式

```bash
# 使用相对路径
python run_test.py -f resources/firmware/your_firmware.bin

# 使用绝对路径
python run_test.py -f "D:\固件升级自动化\resources\firmware\v1.2.3.bin"
```

### 参数说明

- `-f, --firmware`: 固件文件路径（命令行模式必需）

## 配置说明

### app_config.yaml

```yaml
app:
  exe_path: "应用可执行文件路径"
  launch_timeout: 30  # 启动超时时间（秒）

image_recognition:
  threshold: 0.85  # 图像识别阈值（0-1）
  timeout: 10      # 识别超时时间（秒）

timeouts:
  stream_start: 30          # 开流超时
  firmware_upgrade: 300     # 升级超时
  device_reconnect: 60      # 设备重连超时
```

### device_config.yaml

```yaml
devices:
  default:
    name: "测试设备"
    connection_type: "wifi"  # usb 或 wifi
    ip: "192.168.1.100"      # WiFi 模式必填
    port: "8080"             # WiFi 模式必填
```

### test_config.yaml

```yaml
test:
  retry:
    enabled: true
    max_attempts: 3

  logging:
    level: "INFO"  # DEBUG, INFO, WARNING, ERROR
```

## 日志和报告

- **日志文件**: `logs/test_YYYYMMDD_HHMMSS.log`
- **截图文件**: `screenshots/`
- **测试报告**: `reports/`

## 支持的设备

### Sermoon 系列

| 设备型号 | 型号代码 | 连接方式 | 固件升级超时 | 重连超时 |
|---------|---------|---------|-------------|---------|
| Sermoon S1 | SCANNER_SERMOON_S1 | USB/WiFi | 360秒 | 120秒 |
| Sermoon X1 | SCANNER_SERMOON_X1 | USB/WiFi | 360秒 | 90秒 |

### Creality Pika 系列

| 设备型号 | 型号代码 | 连接方式 | 固件升级超时 | 重连超时 |
|---------|---------|---------|-------------|---------|
| Creality Pika | SCANNER_PIKA | WiFi | 150秒 | - |

### Otter 系列

| 设备型号 | 型号代码 | 连接方式 | 固件升级超时 | 重连超时 |
|---------|---------|---------|-------------|---------|
| Otter Lite | SCANNER_OTTER_LITE | WiFi | 30秒 | - |
| Otter Basic | SCANNER_OTTER_BASIC | WiFi | 30秒 | - |
| Otter Pro | SCANNER_OTTER_PRO | WiFi | 30秒 | - |

### Raptor 系列

| 设备型号 | 型号代码 | 连接方式 | 固件升级超时 | 重连超时 |
|---------|---------|---------|-------------|---------|
| Raptor | SCANNER_RAPTOR | WiFi | 30秒 | - |
| Raptor X | SCANNER_RAPTOR_X | WiFi | 30秒 | - |
| Raptor Pro | SCANNER_RAPTORPRO | WiFi | 30秒 | - |

### Ferret 系列

| 设备型号 | 型号代码 | 连接方式 | 固件升级超时 | 重连超时 |
|---------|---------|---------|-------------|---------|
| Ferret | SCANNER_FERRET | WiFi | 30秒 | - |
| Ferret Pro | SCANNER_FERRET_PRO | WiFi | 30秒 | - |

> **注意**：不同设备可能需要不同的 UI 截图模板，请根据实际界面截取对应的图片。

## 注意事项

1. **首次运行前必须准备 UI 元素截图**，否则无法识别界面元素
2. 确保 CrealityScan 应用未运行，框架会自动启动
3. 测试过程中不要操作鼠标键盘，避免干扰自动化操作
4. 固件升级时间较长，请耐心等待
5. 如果识别失败，可以调整 `app_config.yaml` 中的 `threshold` 值
6. WiFi 模式需要正确配置设备 IP 和端口

## 常见问题

### Q: 提示找不到 UI 元素？
A: 检查对应的图片文件是否存在，路径是否正确，截图是否清晰。

### Q: 图像识别不准确？
A: 调整 `app_config.yaml` 中的 `threshold` 值，降低可提高识别率但可能误识别。

### Q: 应用启动失败？
A: 检查 `app_config.yaml` 中的 `exe_path` 是否正确。

### Q: 固件升级超时？
A: 增加 `app_config.yaml` 中的 `firmware_upgrade` 超时时间。

### Q: WiFi 设备连接失败？
A: 检查 `config/device_config.yaml` 中的 IP 和端口是否正确，确保设备与电脑在同一网络。

## 技术支持

如有问题，请联系测试团队。