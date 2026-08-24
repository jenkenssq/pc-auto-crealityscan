# 文件选择问题修复 - Enter字符串问题

## 问题现象
文件名输入框中显示：`Creality_Otter_Lite_Basic_app1_1.0.2.zipEnter`

文件路径后面多了 "Enter" 字符串。

## 问题原因

### 原因1: type_keys() 处理路径时的问题
当使用 `dlg.type_keys(abs_path)` 输入包含特殊字符的路径时，pywinauto可能会：
- 把某些字符当作快捷键处理
- 把 `{ENTER}` 当作普通文本输入

### 原因2: keyevent() 参数错误
Airtest的 `keyevent()` 函数应该使用 `"ENTER"` 而不是 `"Enter"`。

## 修复方案

### 1. 改进方法1：直接输入完整路径
```python
file_name_edit = dlg.child_window(auto_id="1148", control_type="Edit")
file_name_edit.set_focus()
sleep(0.2)
file_name_edit.set_text("")  # 先清空
sleep(0.2)
file_name_edit.set_text(abs_path)  # 使用set_text而不是type_keys
sleep(0.5)
open_btn.click()
```

**关键改进**：
- 使用 `set_text()` 而不是 `type_keys()`，避免特殊字符问题
- 先清空输入框，确保没有残留内容
- 增加 `set_focus()` 确保输入框获得焦点

### 2. 改进方法2：先切换目录再选择文件
```python
# 切换到文件目录
address_bar = dlg.child_window(auto_id="1001", control_type="Edit")
address_bar.set_focus()
address_bar.set_text(file_dir)
address_bar.type_keys("{ENTER}")
sleep(1.5)

# 输入文件名
file_name_edit = dlg.child_window(auto_id="1148", control_type="Edit")
file_name_edit.set_focus()
file_name_edit.set_text("")
file_name_edit.set_text(file_name)
open_btn.click()
```

**关键改进**：
- 分离目录和文件名
- 增加等待时间，确保目录切换完成
- 使用 `set_text()` 输入文件名

### 3. 新增方法3：输入文件名后直接回车
```python
# 确保在正确的目录
address_bar.set_text(file_dir)
address_bar.type_keys("{ENTER}")
sleep(1)

# 输入文件名并回车
file_name_edit.set_focus()
file_name_edit.set_text("")
file_name_edit.set_text(file_name)
file_name_edit.type_keys("{ENTER}")  # 直接在输入框上按回车
```

**关键改进**：
- 不点击"打开"按钮，直接在输入框按回车
- 更符合用户手动操作习惯

### 4. 修复Airtest备用方案
```python
# 修改前
keyevent("Enter")  # 错误：会被当作文本输入

# 修改后
keyevent("ENTER")  # 正确：大写的ENTER
```

## 调试信息增强

每个方法都增加了详细的日志输出：
```python
self.logger.info("尝试方法1: 直接输入完整路径")
# ... 执行方法1 ...
self.logger.info(f"方法1成功: 已选择固件文件")

# 如果失败
self.logger.warning(f"方法1失败: {e1}")
```

这样可以清楚地看到：
- 哪个方法被执行了
- 哪个方法成功了
- 失败的原因是什么

## 测试建议

重新运行测试，观察日志输出：

```bash
cd D:\固件升级自动化
python main.py
```

预期日志输出：
```
[INFO] 选择固件文件
[INFO] 文件目录: D:\固件升级自动化\resources\firmware
[INFO] 文件名: Creality_Otter_Lite_Basic_app1_1.0.2.zip
[INFO] 尝试方法1: 直接输入完整路径
[INFO] 方法1成功: 已选择固件文件
```

如果方法1失败，会自动尝试方法2和方法3。

## 为什么会出现 "Enter" 字符串

最可能的原因是之前的方法3使用了：
```python
dlg.type_keys(abs_path)  # 路径中可能包含特殊字符
dlg.type_keys("{ENTER}")  # 如果上一行失败，这行可能被当作文本
```

当 `type_keys(abs_path)` 遇到特殊字符时可能抛出异常，但异常被捕获后继续执行，导致 `{ENTER}` 被当作普通文本输入。

## 核心原则

1. **优先使用 set_text()**：对于路径和文件名，使用 `set_text()` 而不是 `type_keys()`
2. **type_keys() 只用于按键**：只用于 `{ENTER}`, `^l` 等按键操作
3. **先清空再输入**：使用 `set_text("")` 清空输入框，避免残留内容
4. **增加焦点控制**：使用 `set_focus()` 确保控件获得焦点
5. **增加等待时间**：在关键操作后增加适当的等待时间

## 修改文件
- ✅ `core/firmware_handler.py` - 完全重写 `_select_firmware_file()` 方法
