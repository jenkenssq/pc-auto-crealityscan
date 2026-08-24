# 基于日志分析的代码优化方案

## 日志分析总结

通过分析 `C:\Users\zengx\AppData\Local\Creality\CrealityScan\Logs\20260312162806` 目录下的日志文件，我发现了以下关键信息：

### 1. 日志文件结构

```
20260312162806/  (目录名为时间戳)
├── app.log                          # 主应用日志（511KB）
├── scan_log_20260312-162807.txt     # 扫描日志（683KB）
├── ScannerStreamSDK.log             # SDK日志（258KB）
├── device_info.json                 # 设备信息
├── system_info.txt                  # 系统信息
└── alog.txt                         # 其他日志
```

**重要发现**：日志目录名就是时间戳，需要找到最新的目录！

### 2. 关键日志标识

#### 设备连接（app.log）
```
[2026-03-12 16:28:08.088158] [Debug] OnDeviceConnect: CurrentDeviceInfo = DeviceInfo
[2026-03-12 16:28:08.089158] [Debug] [FirmWareUpgradeManager]  Device connected:1 scannerpid=SCANNER_OTTER_LITE_BASIC
[2026-03-12 16:28:08.089158] [Debug] [FirmWareUpgradeManager]  Device connected:2 SCANNER_OTTER_LITE_BASIC+WBH575E000P
```

**关键字**：
- `OnDeviceConnect`
- `Device connected`
- `FirmWareUpgradeManager]  Device connected`

#### 设备断开（app.log）
```
[2026-03-12 16:28:43.771734] [Debug] [MultiScannerConnectedTask]  Device disconnected, completing task
[2026-03-12 16:28:43.771734] [Debug] OnDeviceDisconnect:#########DeviceInfoList Total[0]##########
[2026-03-12 16:28:43.771734] [Debug] OnDeviceDisconnect: isActiveDeviceDisconnect = True
[2026-03-12 16:28:43.771734] [Debug] [FirmWareUpgradeManager]  Device disconnected
```

**关键字**：
- `Device disconnected`
- `OnDeviceDisconnect`
- `isActiveDeviceDisconnect = True`

#### 固件升级成功（app.log）
```
[2026-03-12 16:28:41.815015] [Debug] OnDeviceUpgradeSuccess called curCheckingFwDeviceinfo+ SCANNER_OTTER_LITE_BASIC
[2026-03-12 16:28:41.815015] [Debug] [FirmWareUpgradeManager]  Firmware upgrade task completed
[2026-03-12 16:28:41.815015] [Debug] [FirmWareUpgradeManager]  显示成功toastSermoon S1 upgrade completed, event invoke
[2026-03-12 16:28:41.815015] [Debug] Device Upgrade Success
[2026-03-12 16:28:46.814019] [Debug] [DTM GA4] Tracking event: firmware_upgrade_completed, params: 5
```

**关键字**：
- `OnDeviceUpgradeSuccess`
- `Device Upgrade Success`
- `firmware_upgrade_completed`
- `Firmware upgrade task completed`

#### 帧数信息（scan_log_*.txt）
```
[2026-03-12 16:28:16.653187][INFO ][11880][::0] frame 0
[2026-03-12 16:29:02.534656][INFO ][20664][::0] frame 100
[2026-03-12 16:29:02.565724][INFO ][20664][::0] frame 101
```

**关键字**：
- `frame \d+` (正则表达式)
- 格式：`[时间戳][INFO ][线程ID][::0] frame 数字`

### 3. 彩色相机判断

在扫描日志中发现：
```
[2026-03-12 16:28:16.625053][INFO ][5956][::0] got valid frame set(color,double ir).
```

**关键字**：
- `got valid frame set(color,double ir)` - 有彩色相机
- `got valid frame set(double ir)` - 无彩色相机（推测）

## 代码优化方案

### 1. 日志文件路径获取优化

**问题**：用户提供的是日志目录，需要找到最新的日志文件

**解决方案**：
```python
def get_latest_log_file(log_dir, log_name="app.log"):
    """
    获取最新的日志文件路径

    Args:
        log_dir: 日志根目录 (如 C:\\Users\\zengx\\AppData\\Local\\Creality\\CrealityScan\\Logs)
        log_name: 日志文件名 (如 app.log 或 scan_log_*.txt)

    Returns:
        str: 最新日志文件的完整路径
    """
    log_root = Path(log_dir)
    if not log_root.exists():
        return None

    # 获取所有时间戳目录，按时间排序
    timestamp_dirs = [d for d in log_root.iterdir() if d.is_dir()]
    if not timestamp_dirs:
        return None

    # 找到最新的目录（按名称排序，因为是时间戳格式）
    latest_dir = sorted(timestamp_dirs, key=lambda x: x.name, reverse=True)[0]

    # 如果是通配符，找到匹配的文件
    if "*" in log_name:
        import glob
        pattern = str(latest_dir / log_name)
        files = glob.glob(pattern)
        if files:
            return files[0]
    else:
        log_file = latest_dir / log_name
        if log_file.exists():
            return str(log_file)

    return None
```

### 2. 设备状态监控优化

**优化后的关键字**：
```python
# 设备连接关键字
online_keywords = [
    "OnDeviceConnect",
    "Device connected",
    "FirmWareUpgradeManager]  Device connected"
]

# 设备断开关键字
offline_keywords = [
    "Device disconnected",
    "OnDeviceDisconnect",
    "isActiveDeviceDisconnect = True"
]
```

### 3. 固件升级成功判断优化

**优化后的关键字**：
```python
upgrade_success_keywords = [
    "OnDeviceUpgradeSuccess",
    "Device Upgrade Success",
    "firmware_upgrade_completed",
    "Firmware upgrade task completed"
]
```

### 4. 帧数监控优化

**优化后的正则表达式**：
```python
# 扫描日志中的帧数格式
frame_pattern = r'\[INFO\s*\]\s*\[\d+\]\s*\[::0\]\s*frame\s+(\d+)'

# 或者更简单的
frame_pattern = r'frame\s+(\d+)'
```

**注意**：帧数信息在 `scan_log_*.txt` 文件中，不在 `app.log` 中！

### 5. 彩色相机判断优化

**优化后的关键字**：
```python
# 在 scan_log_*.txt 中查找
color_camera_keywords = [
    "got valid frame set(color,double ir)",
    "got valid frame set(color",
]

no_color_camera_keywords = [
    "got valid frame set(double ir)",
    "got valid frame set(ir)",
]
```

## 配置文件更新

### app_config.yaml

```yaml
app:
  # 日志根目录（不是具体的日志文件）
  log_dir: "C:\\Users\\zengx\\AppData\\Local\\Creality\\CrealityScan\\Logs"

  # 日志文件名配置
  log_files:
    app_log: "app.log"
    scan_log: "scan_log_*.txt"
```

## 实现建议

### 1. 创建日志管理类

```python
class LogFileManager:
    """日志文件管理器"""

    def __init__(self, log_dir):
        self.log_dir = Path(log_dir)
        self.latest_dir = None
        self.app_log_path = None
        self.scan_log_path = None

    def update_latest_logs(self):
        """更新到最新的日志文件"""
        # 找到最新的时间戳目录
        timestamp_dirs = [d for d in self.log_dir.iterdir() if d.is_dir()]
        if timestamp_dirs:
            self.latest_dir = sorted(timestamp_dirs, key=lambda x: x.name, reverse=True)[0]
            self.app_log_path = self.latest_dir / "app.log"

            # 找到扫描日志
            scan_logs = list(self.latest_dir.glob("scan_log_*.txt"))
            if scan_logs:
                self.scan_log_path = scan_logs[0]

    def get_app_log(self):
        """获取应用日志路径"""
        self.update_latest_logs()
        return str(self.app_log_path) if self.app_log_path and self.app_log_path.exists() else None

    def get_scan_log(self):
        """获取扫描日志路径"""
        self.update_latest_logs()
        return str(self.scan_log_path) if self.scan_log_path and self.scan_log_path.exists() else None
```

### 2. 帧数监控需要读取扫描日志

**重要**：帧数信息在 `scan_log_*.txt` 中，不在 `app.log` 中！

```python
def _wait_for_frame_count(self, target_frames=100):
    """等待帧数达到目标值"""
    # 获取扫描日志路径（不是app.log！）
    scan_log_path = self.log_manager.get_scan_log()

    if not scan_log_path:
        self.logger.warning("未找到扫描日志文件")
        return False

    # 监控扫描日志中的帧数
    pattern = r'frame\s+(\d+)'
    # ... 监控逻辑
```

### 3. 彩色相机判断需要读取扫描日志

```python
def _check_color_camera_from_log(self):
    """通过扫描日志判断是否有彩色相机"""
    # 获取扫描日志路径
    scan_log_path = self.log_manager.get_scan_log()

    if not scan_log_path:
        return True  # 默认假设有

    # 读取扫描日志
    with open(scan_log_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

        if "got valid frame set(color" in content:
            return True
        elif "got valid frame set(double ir)" in content:
            return False

    return True
```

## 总结

### 关键发现

1. **日志目录结构**：日志在时间戳命名的子目录中，需要找到最新的
2. **多个日志文件**：
   - `app.log` - 设备连接、固件升级状态
   - `scan_log_*.txt` - 帧数、彩色相机信息
3. **准确的关键字**：通过实际日志找到了准确的判断关键字

### 优化优先级

1. **高优先级**：
   - 实现日志文件自动查找（找到最新的时间戳目录）
   - 更新设备连接/断开的关键字
   - 更新固件升级成功的关键字

2. **中优先级**：
   - 帧数监控改为读取 `scan_log_*.txt`
   - 彩色相机判断改为读取 `scan_log_*.txt`

3. **低优先级**：
   - 添加日志文件管理类
   - 优化日志读取性能

---

**文档版本**: v1.4.0
**日期**: 2026-03-12
**基于日志**: 20260312162806
