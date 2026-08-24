# 修复说明 - Airtest Template 参数错误

## 问题描述
运行时报错：`wait() got an unexpected keyword argument 'threshold'`

## 原因分析
Airtest 的 `wait()` 和 `touch()` 函数不直接接受 `threshold` 参数。需要使用 `Template` 对象来包装图片路径并设置识别阈值。

## 错误代码
```python
# 错误的用法
wait(image_path, timeout=self.timeout, threshold=self.threshold)
touch(image_path)
```

## 正确代码
```python
# 正确的用法
from airtest.core.cv import Template

template = Template(image_path, threshold=self.threshold)
wait(template, timeout=self.timeout)
touch(template)
```

## 修复内容

### 1. stream_handler.py
- ✅ 导入 `Template` 类：`from airtest.core.cv import Template`
- ✅ 更新 `_click_element()` 方法，使用 `Template` 对象

### 2. firmware_handler.py
- ✅ 导入 `Template` 类：`from airtest.core.cv import Template`
- ✅ 更新 `_click_element()` 方法，使用 `Template` 对象

## 修复后的代码

```python
def _click_element(self, element_key, element_name):
    """点击UI元素（通用方法）"""
    image_path = self.images.get(element_key)

    if not Path(image_path).exists():
        self.logger.error(f"{element_name}图片不存在: {image_path}")
        return False

    try:
        # 创建Template对象，设置识别阈值
        template = Template(image_path, threshold=self.threshold)

        # 等待元素出现
        if wait(template, timeout=self.timeout):
            touch(template)
            sleep(self.click_delay)
            self.logger.info(f"成功点击{element_name}")
            return True
        else:
            self.logger.error(f"未找到{element_name}")
            return False
    except Exception as e:
        self.logger.error(f"点击{element_name}失败: {e}")
        return False
```

## 测试建议
修复后请重新运行测试，确认：
1. 新建项目按钮可以正常点击
2. 其他UI元素点击功能正常
3. 图像识别阈值设置生效

## Airtest API 参考

### Template 类
```python
Template(filename, threshold=0.8, target_pos=5, record_pos=None, resolution=())
```

参数说明：
- `filename`: 图片文件路径
- `threshold`: 识别阈值（0-1），默认0.8，越高越严格
- `target_pos`: 点击位置偏移
- `record_pos`: 录制时的位置
- `resolution`: 分辨率

### 常用方法
```python
# 等待图片出现
wait(Template("image.png", threshold=0.8), timeout=10)

# 点击图片
touch(Template("image.png", threshold=0.8))

# 检查图片是否存在
exists(Template("image.png", threshold=0.8))

# 断言图片存在
assert_exists(Template("image.png", threshold=0.8), "图片应该存在")
```

## 注意事项
1. `threshold` 值范围是 0-1，建议设置在 0.7-0.9 之间
2. 如果识别不准确，可以适当降低 `threshold` 值
3. 如果误识别太多，可以适当提高 `threshold` 值
4. 建议在配置文件中统一管理 `threshold` 值
