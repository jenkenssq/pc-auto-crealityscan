# 更新日志

## v1.1.0 (2026-03-12) - 流程优化更新

### 新增功能

#### 1. 开流操作完善 - 返回首页流程
在开流验证成功后，新增了返回首页的完整操作流程：
- 点击"完成扫描"按钮
- 点击"返回首页"按钮
- 点击"确定"按钮确认返回

**影响的文件**：
- `core/stream_handler.py` - 新增 `_return_to_home()` 方法
- 新增UI元素：
  - `resources/images/scan/finish_scan.png`
  - `resources/images/scan/back_home.png`

#### 2. 固件升级完善 - 关闭设置页
在固件升级完成后，新增了关闭设置页的操作：
- 点击"关闭设置"按钮（或使用ESC键）
- 返回首页准备第二次开流

**影响的文件**：
- `core/firmware_handler.py` - 新增 `_close_settings()` 方法
- 新增UI元素：
  - `resources/images/settings/close_settings.png`

### 更新的测试流程

#### 完整流程图

```
启动应用
    ↓
【第一次开流】
├─ 新建项目 → 确认 → 预览 → 扫描
├─ 验证开流成功
└─ 完成扫描 → 返回首页 → 确定 ✨新增
    ↓
【固件升级】
├─ 设置 → 设备管理 → 选择文件 → 确定
├─ 等待升级完成
├─ 验证设备重连
└─ 关闭设置页 ✨新增
    ↓
【第二次开流】
└─ 重复第一次开流流程
    ↓
生成报告
```

### 需要新增的UI截图

如果你已经完成了之前的8张截图，现在需要额外截取3张：

1. **finish_scan.png** - 扫描页的"完成扫描"按钮
2. **back_home.png** - 扫描页的"返回首页"按钮
3. **close_settings.png** - 设置页的"关闭设置"按钮（如果没有可以省略，框架会使用ESC键）

### 文档更新

- ✅ `README.md` - 更新测试流程说明
- ✅ `QUICKSTART.md` - 更新最小截图集（8张→11张）
- ✅ `UI_SCREENSHOT_GUIDE.md` - 新增3个UI元素的截图说明
- ✅ `CHANGELOG.md` - 本文档

### 兼容性说明

- 向后兼容：如果缺少新增的UI截图，测试会报错提示缺少图片
- 建议：按照更新后的文档补充3张新截图

### 升级指南

如果你已经在使用v1.0.0版本：

1. 更新代码文件：
   - `core/stream_handler.py`
   - `core/firmware_handler.py`

2. 补充UI截图：
   - 参考 `UI_SCREENSHOT_GUIDE.md` 截取3张新图片

3. 运行环境检查：
   ```bash
   python check_env.py
   ```

4. 开始测试：
   ```bash
   python run_test.py -f your_firmware.bin
   ```

### 技术细节

#### StreamHandler 新增方法

```python
def _return_to_home(self):
    """
    返回首页操作
    步骤：完成扫描 -> 返回首页 -> 确定
    """
    # 实现细节见 core/stream_handler.py
```

#### FirmwareHandler 新增方法

```python
def _close_settings(self):
    """
    关闭设置页，返回首页
    支持点击关闭按钮或使用ESC键
    """
    # 实现细节见 core/firmware_handler.py
```

---

## v1.0.0 (2026-03-12) - 初始版本

### 功能特性

- ✅ 基础测试框架搭建
- ✅ 应用管理模块
- ✅ 开流操作模块
- ✅ 固件升级模块
- ✅ 日志和截图系统
- ✅ 配置文件系统
- ✅ 完整文档体系

### 支持平台

- Windows 10/11

### 已知限制

- 开流验证逻辑待完善
- 设备重连验证待完善
- 暂不支持Mac平台

---

**维护者**: 测试团队
**最后更新**: 2026-03-12
