# 文件选择卡住问题分析与修复

## 问题现象
程序在点击"选择文件"按钮后，文件对话框弹出，但程序停止工作，日志停在：
```
[INFO] 成功点击选择文件按钮
```

之后没有任何输出。

## 问题分析

### 可能的原因

1. **pywinauto 查找对话框时卡住**
   - `desktop.window()` 可能一直在等待
   - `dlg.wait('visible')` 可能超时但没有抛出异常

2. **异常被静默吞掉**
   - try-except 块可能捕获了异常但没有记录日志

3. **对话框标题不匹配**
   - 正则表达式 `.*[Ss]elect.*|.*选择.*|.*[Ff]irmware.*` 可能匹配不到实际的对话框标题

## 修复方案

### 1. 添加详细的日志输出
```python
self.logger.info("正在查找文件选择对话框...")
dlg = desktop.window(title_re="...")
self.logger.info("找到文件对话框，等待其可见...")
dlg.wait('visible', timeout=10)
self.logger.info("文件对话框已可见")
```

### 2. 显式捕获超时异常
```python
from pywinauto.timings import TimeoutError as PywinautoTimeoutError

try:
    dlg.wait('visible', timeout=10)
except PywinautoTimeoutError:
    self.logger.error("等待文件对话框超时")
    raise Exception("文件对话框未出现或不可见")
```

### 3. 增加超时时间
从 5 秒增加到 10 秒，给对话框更多时间加载。

### 4. 分步骤处理
将查找对话框和等待可见分成两个步骤，分别记录日志。

## 调试建议

### 方法1: 查看对话框的实际标题
如果程序仍然卡住，可以手动检查对话框标题：

1. 点击"选择文件"按钮
2. 对话框弹出后，使用 pywinauto 的 inspect 工具查看标题
3. 或者使用以下脚本：

```python
from pywinauto import Desktop

desktop = Desktop(backend="uia")
windows = desktop.windows()

print("当前所有窗口：")
for win in windows:
    try:
        print(f"标题: {win.window_text()}")
        print(f"类名: {win.class_name()}")
        print("---")
    except:
        pass
```

### 方法2: 使用更宽松的匹配条件
如果标题不匹配，可以尝试：

```python
# 方案1: 只匹配包含 "File" 的窗口
dlg = desktop.window(title_re=".*[Ff]ile.*")

# 方案2: 匹配所有对话框类型的窗口
dlg = desktop.window(class_name="#32770")  # Windows 标准对话框类名

# 方案3: 使用更简单的标题匹配
dlg = desktop.window(title="Please Select Your Firmware File")  # 精确匹配
```

### 方法3: 添加超时保护
在整个文件选择方法外层添加总超时：

```python
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("文件选择操作总超时")

# 设置30秒总超时
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(30)

try:
    # 执行文件选择
    self._select_firmware_file(firmware_path)
finally:
    signal.alarm(0)  # 取消超时
```

## 临时解决方案

如果 pywinauto 持续有问题，可以考虑：

### 方案1: 使用 UI Automation
```python
import uiautomation as auto

# 查找文件对话框
dialog = auto.WindowControl(searchDepth=1, ClassName="#32770")
if dialog.Exists(maxSearchSeconds=10):
    # 找到文件名输入框
    edit = dialog.EditControl(AutomationId="1148")
    edit.SetValue(abs_path)
    # 点击打开按钮
    btn = dialog.ButtonControl(Name="打开")
    btn.Click()
```

### 方案2: 使用 AutoIt
通过 Python 调用 AutoIt 脚本来处理文件对话框。

### 方案3: 手动操作
在配置中添加一个选项，允许用户手动选择文件，程序等待用户完成。

## 测试步骤

1. 重新运行测试
2. 观察日志输出，看能否看到：
   ```
   [INFO] 正在查找文件选择对话框...
   [INFO] 找到文件对话框，等待其可见...
   [INFO] 文件对话框已可见
   ```

3. 如果卡在某一步，说明问题在那一步
4. 如果看到超时错误，说明对话框标题不匹配或对话框没有正确弹出

## 修改文件
- ✅ `core/firmware_handler.py` - 添加详细日志和超时处理
