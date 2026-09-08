# 更新日志 v1.3.1

## 更新时间
2026-03-12

## 更新内容

### 1. 新增LogManager日志管理器 (⭐⭐⭐ 高优先级)

**文件**: `utils/log_manager.py`

**功能**:
- 自动检测最新的日志目录（基于时间戳）
- 统一管理app.log和scan_log_*.txt文件
- 提供便捷的日志读取和搜索API
- 支持帧数提取、彩色相机检测、设备连接状态检测等

**核心方法**:
```python
# 刷新并定位最新日志目录
log_manager.refresh_latest_log_dir()

# 获取最新帧数
frame_count = log_manager.get_latest_frame_count()

# 检测彩色相机
has_color = log_manager.has_color_camera()

# 检查设备连接状态
is_connected = log_manager.is_device_connected()

# 获取当前扫描状态
status = log_manager.get_current_scan_status()
```

### 2. 更新stream_handler.py集成LogManager

**变更**:
- 移除直接读取日志文件的代码
- 使用LogManager统一管理日志
- 简化`_wait_for_frame_count()`方法
- 简化`_check_color_camera_from_log()`方法

**优势**:
- 代码更简洁，职责更清晰
- 自动处理日志目录切换
- 更好的错误处理
- 更容易测试和维护

### 3. 待完成任务

**下一步**:
1. 更新`firmware_handler.py`集成LogManager
2. 实现基于日志的智能等待机制（替代固定sleep）
3. 添加扫描状态实时监控
4. 实现设备连接状态实时监控

## 技术亮点

1. **自动日志目录检测**: 无需手动配置具体日志文件路径，自动找到最新的日志目录
2. **分离关注点**: 日志读取逻辑与业务逻辑分离，提高代码可维护性
3. **统一接口**: 所有日志相关操作通过LogManager统一管理
4. **健壮性**: 完善的错误处理和默认值机制

## 配置要求

在`config/app_config.yaml`中配置日志根目录:
```yaml
app:
  log_dir: "C:\\Users\\zengx\\AppData\\Local\\Creality\\CrealityScan\\Logs"
```

LogManager会自动检测该目录下最新的时间戳子目录。
