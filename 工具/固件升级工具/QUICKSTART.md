# 快速开始指南

本指南帮助你快速上手CrealityScan固件升级自动化测试框架。

## 第一步：安装依赖

打开命令行，进入项目目录，运行：

```bash
pip install -r requirements.txt
```

## 第二步：配置应用路径

编辑 `config/app_config.yaml`，修改CrealityScan的安装路径：

```yaml
app:
  exe_path: "C:\\Program Files\\CrealityScan\\CrealityScan.exe"
```

**注意**：路径中的反斜杠需要使用双反斜杠 `\\`

## 第三步：准备UI截图（最重要！）

这是框架能够运行的关键步骤。你需要截取CrealityScan应用的UI元素图片。

### 最小截图集（11张）

为了快速开始，至少需要截取以下11张图片：

1. **resources/images/home/new_project.png** - 首页的"新建项目"按钮
2. **resources/images/home/confirm.png** - 弹窗的"确定"按钮
3. **resources/images/home/settings.png** - 首页的"设置"按钮
4. **resources/images/scan/preview.png** - 扫描页的"预览"按钮
5. **resources/images/scan/scan.png** - 扫描页的"扫描"按钮
6. **resources/images/scan/finish_scan.png** - "完成扫描"按钮 **【新增】**
7. **resources/images/scan/back_home.png** - "返回首页"按钮 **【新增】**
8. **resources/images/settings/device_management.png** - 设置页的"设备管理"按钮
9. **resources/images/settings/select_file.png** - "选择文件"按钮
10. **resources/images/settings/upgrade_success.png** - 升级成功提示气泡
11. **resources/images/settings/close_settings.png** - "关闭设置"按钮 **【新增】**

### 如何截图

1. 启动CrealityScan应用
2. 按 `Win + Shift + S` 启动Windows截图工具
3. 框选目标UI元素（只截按钮本身，不要包含太多背景）
4. 打开画图工具（mspaint），粘贴（Ctrl + V）
5. 另存为PNG格式到对应路径

**详细截图指南请参考**: `UI_SCREENSHOT_GUIDE.md`

## 第四步：准备固件文件

将固件文件放到 `resources/firmware/` 目录下，例如：

```
resources/firmware/v1.2.3.bin
```

## 第五步：检查环境

运行环境检查脚本，确保一切就绪：

```bash
python check_env.py
```

如果所有检查都通过，你会看到：

```
✓ 所有检查通过！可以开始测试。
```

## 第六步：运行测试

```bash
python run_test.py -f resources/firmware/v1.2.3.bin
```

## 测试过程

测试会自动执行以下步骤：

1. 启动CrealityScan应用
2. 执行第一次开流操作
3. 执行固件升级
4. 执行第二次开流操作
5. 生成测试报告

**注意**：测试过程中请不要操作鼠标键盘！

## 查看结果

- **控制台输出**：实时显示测试进度和结果
- **日志文件**：`logs/test_YYYYMMDD_HHMMSS.log`
- **截图文件**：`screenshots/` 目录下保存了各步骤的截图

## 常见问题

### 1. 提示"未找到XXX按钮"

**原因**：UI截图不存在或识别失败

**解决**：
- 检查对应的PNG文件是否存在
- 重新截取更清晰的图片
- 降低识别阈值（修改 `config/app_config.yaml` 中的 `threshold`）

### 2. 应用启动失败

**原因**：应用路径配置错误

**解决**：
- 检查 `config/app_config.yaml` 中的 `exe_path` 是否正确
- 确保路径使用双反斜杠 `\\`

### 3. 固件升级超时

**原因**：升级时间超过默认超时时间（300秒）

**解决**：
- 增加 `config/app_config.yaml` 中的 `firmware_upgrade` 超时时间

### 4. 依赖包安装失败

**原因**：网络问题或Python版本不兼容

**解决**：
- 使用国内镜像：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`
- 确保Python版本 >= 3.8

## 下一步

- 阅读 `README.md` 了解完整功能
- 阅读 `UI_SCREENSHOT_GUIDE.md` 学习截图技巧
- 根据实际需求调整配置文件

## 需要帮助？

如果遇到问题：
1. 运行 `python check_env.py` 检查环境
2. 查看日志文件了解详细错误信息
3. 参考 `README.md` 中的"常见问题"章节
4. 联系测试团队获取支持

祝测试顺利！🚀
