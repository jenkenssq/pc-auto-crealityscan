# 自动化脚本全面优化建议

基于对完整测试流程日志的深入分析，我发现了以下可以优化的地方。

## 1. 通过日志实时验证状态 ⭐⭐⭐

### 当前问题
- 依赖固定等待时间（sleep）
- 依赖UI图像识别
- 无法确认操作是否真正成功

### 优化方案：状态驱动的测试流程

#### 1.1 扫描状态监控

**日志中的状态变化**：
```
[2026-03-12 16:28:15.967840] [Debug] [ScanStatus] ScanStatus Changed: Created -> Previewing
[2026-03-12 16:28:19.336841] [Debug] [ScanStatus] ScanStatus Changed: Previewing -> Scanning
[2026-03-12 16:28:23.999497] [Debug] [ScanStatus] ScanStatus Changed: Scanning -> Stopped
```

**状态流转**：
```
Uncreate → Created → Previewing → Scanning → Stopped
```

**优化代码**：
```python
def wait_for_scan_status(self, target_status, timeout=30):
    """
    等待扫描状态变化到目标状态

    Args:
        target_status: 目标状态 (Previewing, Scanning, Stopped等)
        timeout: 超时时间

    Returns:
        bool: 是否达到目标状态
    """
    pattern = rf'\[ScanStatus\] ScanStatus Changed:.*-> {target_status}'
    return self._wait_for_log_pattern(pattern, timeout)
```

**使用示例**：
```python
# 点击预览后，等待状态变为Previewing
self._click_preview()
if self.wait_for_scan_status("Previewing"):
    self.logger.info("预览状态已就绪")

# 点击扫描后，等待状态变为Scanning
self._click_scan()
if self.wait_for_scan_status("Scanning"):
    self.logger.info("扫描已开始")
```

#### 1.2 会话创建验证

**日志标识**：
```
[2026-03-12 16:28:14.353921] [Debug] Create session
[2026-03-12 16:28:14.511400] [Debug] [DTM GA4] Tracking event: scan_created, params: 2
```

**优化**：
```python
def verify_session_created(self):
    """验证扫描会话是否创建成功"""
    keywords = ["Create session", "scan_created"]
    return self._check_log_keywords(keywords)
```

## 2. 智能等待机制 ⭐⭐⭐

### 当前问题
- 使用固定的sleep时间
- 可能等待过长或过短

### 优化方案：基于日志的动态等待

#### 2.1 设备连接等待

**不要固定等待，而是监控日志**：
```python
def wait_for_device_connected(self, timeout=30):
    """等待设备连接成功"""
    keywords = ["OnDeviceConnect", "Device connected"]
    start_time = time.time()

    while time.time() - start_time < timeout:
        if self._check_recent_log_keywords(keywords):
            self.logger.info("设备已连接")
            return True
        sleep(1)

    return False
```

#### 2.2 预览就绪等待

**监控预览状态**：
```python
def wait_for_preview_ready(self, timeout=30):
    """等待预览就绪"""
    # 方法1：监控状态变化
    if self.wait_for_scan_status("Previewing", timeout):
        return True

    # 方法2：监控预览消息
    pattern = r'OnScanningPreviewMessage'
    return self._wait_for_log_pattern(pattern, timeout)
```

## 3. 测试前环境检查 ⭐⭐

### 优化方案：Pre-flight检查

```python
def preflight_check(self):
    """测试前环境检查"""
    checks = []

    # 1. 检查日志目录是否存在
    if not Path(self.log_dir).exists():
        checks.append(("日志目录", False, f"目录不存在: {self.log_dir}"))
    else:
        checks.append(("日志目录", True, ""))

    # 2. 检查设备是否已连接（通过最新日志）
    if self._check_device_connected_from_log():
        checks.append(("设备连接", True, ""))
    else:
        checks.append(("设备连接", False, "未检测到设备连接"))

    # 3. 检查软件是否运行
    if self.app_manager.is_app_running():
        checks.append(("软件运行", True, ""))
    else:
        checks.append(("软件运行", False, "CrealityScan未运行"))

    # 4. 检查固件文件是否存在
    if Path(self.firmware_path).exists():
        checks.append(("固件文件", True, ""))
    else:
        checks.append(("固件文件", False, f"文件不存在: {self.firmware_path}"))

    # 输出检查结果
    self.logger.info("=" * 60)
    self.logger.info("环境检查结果")
    self.logger.info("=" * 60)

    all_passed = True
    for name, passed, message in checks:
        status = "✓" if passed else "✗"
        self.logger.info(f"{status} {name}: {message if message else '正常'}")
        if not passed:
            all_passed = False

    return all_passed
```

## 4. 错误检测和恢复 ⭐⭐

### 4.1 监控日志中的错误

```python
def check_for_errors_in_log(self):
    """检查日志中是否有错误"""
    error_patterns = [
        r'\[Error\]',
        r'Exception',
        r'failed',
        r'timeout',
    ]

    recent_logs = self._get_recent_logs(lines=100)

    for pattern in error_patterns:
        matches = re.findall(pattern, recent_logs, re.IGNORECASE)
        if matches:
            self.logger.warning(f"检测到错误: {pattern}")
            return True

    return False
```

### 4.2 自动重试机制

```python
def execute_with_retry(self, func, max_retries=3, retry_delay=5):
    """
    带重试的执行函数

    Args:
        func: 要执行的函数
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）
    """
    for attempt in range(max_retries):
        try:
            result = func()
            if result:
                return True

            if attempt < max_retries - 1:
                self.logger.warning(f"操作失败，{retry_delay}秒后重试 ({attempt + 1}/{max_retries})")
                sleep(retry_delay)
        except Exception as e:
            self.logger.error(f"执行异常: {e}")
            if attempt < max_retries - 1:
                sleep(retry_delay)

    return False
```

## 5. 性能数据收集 ⭐⭐

### 5.1 记录每个步骤的耗时

```python
class PerformanceTracker:
    """性能追踪器"""

    def __init__(self):
        self.timings = {}

    def start(self, step_name):
        """开始计时"""
        self.timings[step_name] = {"start": time.time()}

    def end(self, step_name):
        """结束计时"""
        if step_name in self.timings:
            self.timings[step_name]["end"] = time.time()
            self.timings[step_name]["duration"] = (
                self.timings[step_name]["end"] - self.timings[step_name]["start"]
            )

    def get_report(self):
        """生成性能报告"""
        report = []
        report.append("=" * 60)
        report.append("性能统计")
        report.append("=" * 60)

        for step, timing in self.timings.items():
            if "duration" in timing:
                report.append(f"{step}: {timing['duration']:.2f}秒")

        return "\n".join(report)
```

**使用示例**：
```python
# 在测试类中
self.perf_tracker = PerformanceTracker()

# 第一次开流
self.perf_tracker.start("第一次开流")
self.stream_handler.start_stream(phase="第一次")
self.perf_tracker.end("第一次开流")

# 固件升级
self.perf_tracker.start("固件升级")
self.firmware_handler.upgrade_firmware(firmware_path)
self.perf_tracker.end("固件升级")

# 生成报告
print(self.perf_tracker.get_report())
```

### 5.2 从日志中提取性能指标

```python
def extract_performance_metrics(self):
    """从日志中提取性能指标"""
    metrics = {}

    # 提取帧率
    scan_log = self._get_scan_log_content()
    frame_times = re.findall(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*frame (\d+)', scan_log)

    if len(frame_times) >= 2:
        # 计算平均帧率
        first_time = datetime.strptime(frame_times[0][0], '%Y-%m-%d %H:%M:%S.%f')
        last_time = datetime.strptime(frame_times[-1][0], '%Y-%m-%d %H:%M:%S.%f')
        duration = (last_time - first_time).total_seconds()
        frame_count = int(frame_times[-1][1])

        if duration > 0:
            fps = frame_count / duration
            metrics['average_fps'] = fps
            metrics['total_frames'] = frame_count
            metrics['scan_duration'] = duration

    return metrics
```

## 6. 更详细的测试报告 ⭐⭐

### 6.1 HTML报告生成

```python
def generate_html_report(self, test_result, performance_data):
    """生成HTML测试报告"""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>CrealityScan固件升级测试报告</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .header { background: #4CAF50; color: white; padding: 20px; }
            .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; }
            .pass { color: green; }
            .fail { color: red; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>CrealityScan固件升级测试报告</h1>
            <p>测试时间: {timestamp}</p>
        </div>

        <div class="section">
            <h2>测试结果</h2>
            <table>
                <tr>
                    <th>测试项</th>
                    <th>结果</th>
                    <th>耗时</th>
                </tr>
                <tr>
                    <td>第一次开流</td>
                    <td class="{first_stream_class}">{first_stream_result}</td>
                    <td>{first_stream_time}</td>
                </tr>
                <tr>
                    <td>固件升级</td>
                    <td class="{upgrade_class}">{upgrade_result}</td>
                    <td>{upgrade_time}</td>
                </tr>
                <tr>
                    <td>第二次开流</td>
                    <td class="{second_stream_class}">{second_stream_result}</td>
                    <td>{second_stream_time}</td>
                </tr>
            </table>
        </div>

        <div class="section">
            <h2>性能指标</h2>
            <ul>
                <li>平均帧率: {fps} FPS</li>
                <li>总帧数: {total_frames}</li>
                <li>扫描时长: {scan_duration}秒</li>
            </ul>
        </div>

        <div class="section">
            <h2>截图</h2>
            {screenshots}
        </div>
    </body>
    </html>
    """

    # 填充模板数据
    # ...

    # 保存HTML文件
    report_path = f"reports/test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return report_path
```

## 7. 日志解析和分析 ⭐

### 7.1 提取关键事件时间线

```python
def extract_event_timeline(self):
    """从日志中提取事件时间线"""
    events = []

    app_log = self._get_app_log_content()

    # 定义关键事件
    event_patterns = {
        "设备连接": r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*OnDeviceConnect',
        "创建会话": r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*Create session',
        "开始预览": r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*ScanStatus Changed:.*-> Previewing',
        "开始扫描": r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*ScanStatus Changed:.*-> Scanning',
        "停止扫描": r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*ScanStatus Changed:.*-> Stopped',
        "升级成功": r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*Device Upgrade Success',
        "设备断开": r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*Device disconnected',
    }

    for event_name, pattern in event_patterns.items():
        matches = re.findall(pattern, app_log)
        for match in matches:
            events.append({
                "time": match,
                "event": event_name
            })

    # 按时间排序
    events.sort(key=lambda x: x["time"])

    return events
```

## 8. 并发测试支持 ⭐

### 8.1 多设备并行测试

```python
def run_parallel_tests(firmware_path, device_list):
    """并行测试多个设备"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}

    with ThreadPoolExecutor(max_workers=len(device_list)) as executor:
        futures = {}

        for device in device_list:
            test = TestFirmwareUpgrade(device_config=device)
            future = executor.submit(test.run, firmware_path)
            futures[future] = device['name']

        for future in as_completed(futures):
            device_name = futures[future]
            try:
                result = future.result()
                results[device_name] = result
            except Exception as e:
                results[device_name] = {"error": str(e)}

    return results
```

## 9. 配置文件增强 ⭐

### 9.1 添加更多可配置项

```yaml
# app_config.yaml

# 日志配置
logging:
  log_dir: "C:\\Users\\zengx\\AppData\\Local\\Creality\\CrealityScan\\Logs"
  monitor_interval: 1  # 日志监控间隔（秒）

# 重试配置
retry:
  enabled: true
  max_attempts: 3
  delay: 5

# 性能监控
performance:
  enabled: true
  collect_fps: true
  collect_timing: true

# 报告配置
report:
  format: "html"  # html, json, pdf
  include_screenshots: true
  include_logs: true
  include_performance: true

# 验证配置
verification:
  use_log_verification: true  # 优先使用日志验证
  use_ui_verification: false  # 备用UI图像识别
  strict_mode: false  # 严格模式：任何错误都终止测试
```

## 10. 测试数据管理 ⭐

### 10.1 测试历史记录

```python
class TestHistoryManager:
    """测试历史管理器"""

    def __init__(self, history_file="test_history.json"):
        self.history_file = history_file
        self.history = self._load_history()

    def _load_history(self):
        """加载历史记录"""
        if Path(self.history_file).exists():
            with open(self.history_file, 'r') as f:
                return json.load(f)
        return []

    def add_record(self, test_result):
        """添加测试记录"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "result": test_result,
            "firmware_version": test_result.get("firmware_version"),
            "duration": test_result.get("duration"),
            "success": test_result.get("overall")
        }
        self.history.append(record)
        self._save_history()

    def _save_history(self):
        """保存历史记录"""
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)

    def get_statistics(self):
        """获取统计信息"""
        total = len(self.history)
        success = sum(1 for r in self.history if r.get("success"))

        return {
            "total_tests": total,
            "success_count": success,
            "failure_count": total - success,
            "success_rate": success / total if total > 0 else 0
        }
```

## 优先级总结

### 高优先级（立即实现）⭐⭐⭐
1. **通过日志实时验证状态** - 最重要的优化
2. **智能等待机制** - 提高测试效率和可靠性
3. **日志文件自动查找** - 解决时间戳目录问题

### 中优先级（近期实现）⭐⭐
4. **测试前环境检查** - 提前发现问题
5. **错误检测和恢复** - 提高测试健壮性
6. **性能数据收集** - 提供更多测试信息
7. **更详细的测试报告** - 改善用户体验

### 低优先级（长期优化）⭐
8. **日志解析和分析** - 深度分析
9. **并发测试支持** - 提高测试效率
10. **测试数据管理** - 长期数据积累

---

**文档版本**: v1.5.0
**日期**: 2026-03-12
