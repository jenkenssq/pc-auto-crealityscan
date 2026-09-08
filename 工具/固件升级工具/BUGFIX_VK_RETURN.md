# 修复方案 - VK_RETURN 被当作文本输入

## 问题现象
文件名输入框显示：`Creality_Otter_Lite_Basic_app1_1.0.2.zipVK_RETURN`

"VK_RETURN" 被当作文本追加到文件名后面，而不是按下回车键。

## 问题原因
Airtest 的 `keyevent()` 函数主要是为移动设备（Android/iOS）设计的，在 Windows 上不能正确工作。

## 解决方案

### 方案1: 使用 text("\n") 输入换行符（推荐）
```python
# 输入文件路径
text(abs_path)
sleep(1)

# 输入换行符代替按回车
text("\n")
sleep(1)
```

**优势**：
- 简单直接
- 不依赖 keyevent()
- 换行符在大多数输入框中等同于回车

### 方案2: 使用 pywinauto 点击"打开"按钮
```python
# 输入文件路径
text(abs_path)
sleep(1)

# 使用 pywinauto 点击打开按钮
from pywinauto import Desktop
desktop = Desktop(backend="uia")
dlg = desktop.window(class_name="#32770")  # 标准对话框
open_btn = dlg.child_window(title_re=".*打开.*|.*Open.*", control_type="Button")
open_btn.click()
sleep(1)
```

**优势**：
- 更可靠
- 模拟真实用户操作
- 不依赖按键事件

### 方案3: 使用 win32api 发送按键（最可靠）
```python
import win32api
import win32con

# 输入文件路径
text(abs_path)
sleep(1)

# 使用 Windows API 按回车
win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
sleep(1)
```

**优势**：
- 使用底层 Windows API
- 最可靠的按键模拟
- 不会被当作文本输入

## 推荐实现

结合三种方案，按优先级尝试：

```python
def _select_firmware_file(self, firmware_path):
    try:
        # 点击选择文件按钮
        if not self._click_element('select_file_btn', "选择文件按钮"):
            return False

        sleep(3)

        abs_path = str(Path(firmware_path).absolute())
        self.logger.info(f"文件路径: {abs_path}")

        # 方法1: text() + 换行符
        try:
            self.logger.info("方法1: 使用换行符")
            text(abs_path)
            sleep(1)
            text("\n")  # 换行符代替回车
            sleep(2)
            return True
        except Exception as e1:
            self.logger.warning(f"方法1失败: {e1}")

        # 方法2: text() + pywinauto 点击按钮
        try:
            self.logger.info("方法2: 点击打开按钮")
            from pywinauto import Desktop

            # 先输入路径（如果方法1没输入成功）
            text(abs_path)
            sleep(1)

            # 查找并点击打开按钮
            desktop = Desktop(backend="uia")
            dlg = desktop.window(class_name="#32770")
            open_btn = dlg.child_window(title_re=".*打开.*|.*Open.*", control_type="Button")
            open_btn.click()
            sleep(2)
            return True
        except Exception as e2:
            self.logger.warning(f"方法2失败: {e2}")

        # 方法3: text() + win32api 按键
        try:
            self.logger.info("方法3: 使用 Windows API")
            import win32api
            import win32con

            text(abs_path)
            sleep(1)

            # 按回车
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            sleep(2)
            return True
        except Exception as e3:
            self.logger.error(f"方法3失败: {e3}")
            return False

    except Exception as e:
        self.logger.error(f"选择固件文件失败: {e}")
        return False
```

## 关键改进

1. **移除 keyevent("VK_RETURN")**：不再使用这个不可靠的方法
2. **使用 text("\n")**：最简单的方法，换行符通常等同于回车
3. **备用方案**：如果换行符不行，点击"打开"按钮
4. **最后备用**：使用 Windows API 发送真正的按键事件

## 为什么 text("\n") 有效

在大多数 Windows 输入框中：
- `\n` (换行符) 会被解释为回车键
- 这是标准的文本输入行为
- 不需要特殊的按键模拟

## 测试步骤

1. 应用修复
2. 重新运行测试
3. 观察文件名输入框，应该只有文件路径，没有额外字符
4. 文件应该能成功选择

## 预期结果

文件名输入框应该显示：
```
Creality_Otter_Lite_Basic_app1_1.0.2.zip
```

而不是：
```
Creality_Otter_Lite_Basic_app1_1.0.2.zipVK_RETURN  ❌
```
