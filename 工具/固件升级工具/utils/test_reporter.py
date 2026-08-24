"""
测试报告生成模块
提供详细的测试报告生成功能，包含对比分析和可视化展示
"""

import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# 可选依赖：matplotlib用于图表生成
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("警告: matplotlib未安装，图表生成功能将不可用")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


class TestReporter:
    """测试报告生成器"""

    def __init__(self, report_dir: str = "test_reports"):
        """
        初始化测试报告生成器

        Args:
            report_dir: 报告保存目录
        """
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

        # 报告数据
        self.test_data = {
            "test_info": {},
            "execution_summary": {},
            "detailed_results": {},
            "comparisons": {},
            "screenshots": [],
            "metrics": {},
            "recommendations": []
        }

    def set_test_info(self, firmware_path: str, test_start_time: datetime, test_end_time: Optional[datetime] = None):
        """设置测试基本信息"""
        self.test_data["test_info"] = {
            "firmware_file": Path(firmware_path).name,
            "firmware_path": str(firmware_path),
            "test_start_time": test_start_time.isoformat(),
            "test_end_time": test_end_time.isoformat() if test_end_time else None,
            "test_duration": None
        }

    def set_execution_summary(self, overall_result: bool, steps_results: Dict[str, bool]):
        """设置执行摘要"""
        passed_steps = sum(1 for result in steps_results.values() if result)
        total_steps = len(steps_results)

        self.test_data["execution_summary"] = {
            "overall_result": "PASS" if overall_result else "FAIL",
            "total_steps": total_steps,
            "passed_steps": passed_steps,
            "failed_steps": total_steps - passed_steps,
            "success_rate": f"{(passed_steps / total_steps * 100):.1f}%" if total_steps > 0 else "0%",
            "steps_detail": steps_results
        }

    def add_detailed_results(self, phase: str, results: Dict[str, Any]):
        """添加详细测试结果"""
        self.test_data["detailed_results"][phase] = results

    def add_comparison_data(self, comparison_type: str, before_data: Dict, after_data: Dict, analysis: str):
        """添加对比分析数据（功能已移除，保留方法避免报错）"""
        # 详细对比分析功能已移除，此方法保留以避免现有代码报错
        pass

    def add_screenshot(self, screenshot_path: str, description: str, step: str):
        """添加截图到报告"""
        if os.path.exists(screenshot_path):
            # 复制截图到报告目录
            report_screenshot_dir = self.report_dir / "screenshots"
            report_screenshot_dir.mkdir(exist_ok=True)

            filename = f"{step}_{Path(screenshot_path).name}"
            target_path = report_screenshot_dir / filename
            shutil.copy2(screenshot_path, target_path)

            self.test_data["screenshots"].append({
                "step": step,
                "description": description,
                "filename": filename,
                "path": str(target_path)
            })

    def add_metrics(self, metrics_type: str, metrics_data: Dict[str, Any]):
        """添加性能指标"""
        self.test_data["metrics"][metrics_type] = metrics_data

    def add_recommendation(self, category: str, message: str, priority: str = "MEDIUM"):
        """添加改进建议"""
        self.test_data["recommendations"].append({
            "category": category,
            "message": message,
            "priority": priority,
            "timestamp": datetime.now().isoformat()
        })

    def generate_performance_charts(self):
        """生成性能图表"""
        if not MATPLOTLIB_AVAILABLE:
            print("跳过图表生成：matplotlib未安装")
            return

        charts_dir = self.report_dir / "charts"
        charts_dir.mkdir(exist_ok=True)

        # 清理旧的 fps_*.png 文件
        for old_file in charts_dir.glob("fps_*.png"):
            old_file.unlink()

        # 帧率曲线图（扫描对比）
        frame_data = self.test_data["metrics"].get("帧数性能", {})
        if not frame_data:
            print("跳过图表生成：未找到帧数性能数据")
            return

        print(f"生成图表，帧数数据键名: {list(frame_data.keys())}")

        # 检查是否有循环测试数据
        if any(key.startswith("第") and "轮" in key for key in frame_data.keys()):
            # 循环测试：为每一轮生成独立图表
            self._generate_cycle_fps_charts(charts_dir, frame_data)
        elif self._has_single_mode_data(frame_data):
            # 分模式数据（蓝色线激光/红外）：生成分模式图表
            self._generate_single_mode_fps_charts(charts_dir, frame_data)
        else:
            # 单次测试：将任意键名的数据映射为"第一次"/"第二次"
            mapped_data = self._map_frame_data_for_single_test(frame_data)
            if mapped_data:
                self._generate_fps_chart(charts_dir, mapped_data, mode="scan")

    def _has_single_mode_data(self, frame_data: dict) -> bool:
        """检查帧率数据是否包含分模式数据（蓝色线激光/红外）"""
        return any("-蓝色线激光" in key or "-红外" in key for key in frame_data.keys())

    def _map_frame_data_for_single_test(self, frame_data: dict) -> dict:
        """
        将单次测试的帧率数据映射为标准格式
        支持各种键名：第一次/第二次、升级前开流/升级后开流 等
        """
        if not frame_data:
            return {}

        # 已经是标准格式
        if "第一次" in frame_data or "第二次" in frame_data:
            return frame_data

        # 尝试映射中文键名到标准格式
        mapping = {
            "升级前开流": "第一次",
            "降级前开流": "第一次",
            "升级后开流": "第二次",
            "降级后开流": "第二次",
        }

        mapped = {}
        sorted_keys = sorted(frame_data.keys())  # 按字母/时间顺序排序

        for idx, key in enumerate(sorted_keys):
            # 使用映射或按顺序分配
            standard_key = mapping.get(key, f"第{idx + 1}次")
            mapped[standard_key] = frame_data[key]

        print(f"映射后的帧数数据: {list(mapped.keys())}")
        return mapped

    def _generate_fps_chart(self, charts_dir: Path, frame_data: dict, mode: str):
        """
        生成帧率对比曲线图

        Args:
            mode: 'preview' 生成预览帧率图，'scan' 生成扫描帧率图
        """
        if not MATPLOTLIB_AVAILABLE:
            return

        key = f"{mode}_fps"
        title = "预览帧率对比（第一次 vs 第二次开流）" if mode == "preview" else "扫描帧率对比（第一次 vs 第二次开流）"
        filename = f"fps_{mode}.png"

        first_entry = frame_data.get("第一次", {})
        second_entry = frame_data.get("第二次", {})

        print(f"第一次开流数据: {first_entry}")
        print(f"第二次开流数据: {second_entry}")

        first_data = first_entry.get(key, [])
        second_data = second_entry.get(key, [])

        print(f"第一次 scan_fps 数据: {first_data}")
        print(f"第二次 scan_fps 数据: {second_data}")

        if not first_data and not second_data:
            print("没有有效的帧率数据，跳过图表生成")
            return

        plt.figure(figsize=(10, 5))
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial']
        plt.rcParams['axes.unicode_minus'] = False

        if first_data:
            x1 = [p[0] for p in first_data]
            y1 = [p[1] for p in first_data]
            plt.plot(x1, y1, color='steelblue', linewidth=1.5, marker='o',
                     markersize=4, label='第一次开流')
            for x, y in zip(x1, y1):
                plt.annotate(f'{int(y)}', (x, y), textcoords='offset points',
                             xytext=(0, 6), ha='center', fontsize=7, color='steelblue')

        if second_data:
            x2 = [p[0] for p in second_data]
            y2 = [p[1] for p in second_data]
            plt.plot(x2, y2, color='darkorange', linewidth=1.5, marker='s',
                     markersize=4, label='第二次开流')
            for x, y in zip(x2, y2):
                plt.annotate(f'{int(y)}', (x, y), textcoords='offset points',
                             xytext=(0, -12), ha='center', fontsize=7, color='darkorange')

        plt.title(title)
        plt.xlabel('时间（秒）')
        plt.ylabel('FPS')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(charts_dir / filename, dpi=150, bbox_inches='tight')
        plt.close()

    def _generate_cycle_fps_charts(self, charts_dir: Path, frame_data: dict):
        """
        为循环测试生成多轮帧率对比图

        Args:
            charts_dir: 图表保存目录
            frame_data: 帧率数据，包含多轮测试数据
        """
        if not MATPLOTLIB_AVAILABLE:
            return

        # 提取所有轮次
        rounds = set()
        for key in frame_data.keys():
            if key.startswith("第") and "轮" in key:
                # 提取轮次号，如"第1轮-升级前" -> "第1轮"
                round_prefix = key.split("-")[0]
                rounds.add(round_prefix)

        # 为每一轮生成图表
        for round_prefix in sorted(rounds):
            self._generate_round_fps_chart(charts_dir, frame_data, round_prefix)

        # 生成汇总对比图
        self._generate_summary_fps_chart(charts_dir, frame_data, rounds)

    def _generate_round_fps_chart(self, charts_dir: Path, frame_data: dict, round_prefix: str):
        """生成单轮测试的帧率对比图"""
        # 收集该轮的所有阶段
        round_data = {}
        for key, data in frame_data.items():
            if key.startswith(round_prefix):
                stage = key.split("-")[1] if "-" in key else key
                round_data[stage] = data

        if not round_data:
            return

        plt.figure(figsize=(12, 6))
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial']
        plt.rcParams['axes.unicode_minus'] = False

        colors = ['steelblue', 'darkorange', 'green', 'red', 'purple']
        markers = ['o', 's', '^', 'v', 'D']

        for idx, (stage, data) in enumerate(round_data.items()):
            if not data:
                continue

            scan_fps_key = "scan_fps"
            fps_data = data.get(scan_fps_key, [])

            if fps_data:
                x = [p[0] for p in fps_data]
                y = [p[1] for p in fps_data]
                color = colors[idx % len(colors)]
                marker = markers[idx % len(markers)]

                plt.plot(x, y, color=color, linewidth=1.5, marker=marker,
                        markersize=4, label=stage)

                # 添加数据点标注
                for x_val, y_val in zip(x, y):
                    plt.annotate(f'{int(y_val)}', (x_val, y_val), textcoords='offset points',
                                xytext=(0, 6), ha='center', fontsize=7, color=color)

        plt.title(f'{round_prefix}扫描帧率对比')
        plt.xlabel('时间（秒）')
        plt.ylabel('FPS')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        filename = f"fps_{round_prefix.replace(' ', '_')}.png"
        plt.savefig(charts_dir / filename, dpi=150, bbox_inches='tight')
        plt.close()

    def _generate_summary_fps_chart(self, charts_dir: Path, frame_data: dict, rounds: set):
        """生成所有轮次的汇总帧率对比图"""
        plt.figure(figsize=(14, 8))
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial']
        plt.rcParams['axes.unicode_minus'] = False

        colors = ['steelblue', 'darkorange', 'green', 'red', 'purple', 'brown', 'pink', 'gray']

        for idx, round_prefix in enumerate(sorted(rounds)):
            # 收集该轮的平均帧率
            round_avg_fps = []
            stages = []

            for key, data in frame_data.items():
                if key.startswith(round_prefix):
                    stage = key.split("-")[1] if "-" in key else key
                    scan_fps_key = "scan_fps"
                    fps_data = data.get(scan_fps_key, [])

                    if fps_data:
                        avg_fps = sum(p[1] for p in fps_data) / len(fps_data)
                        round_avg_fps.append(avg_fps)
                        stages.append(stage)

            if round_avg_fps and stages:
                color = colors[idx % len(colors)]
                x_pos = range(len(stages))
                plt.plot(x_pos, round_avg_fps, color=color, linewidth=2, marker='o',
                        markersize=6, label=f'{round_prefix}平均帧率')

                # 添加数据标注
                for x, y in zip(x_pos, round_avg_fps):
                    plt.annotate(f'{y:.1f}', (x, y), textcoords='offset points',
                                xytext=(0, 8), ha='center', fontsize=8, color=color)

        plt.title('各轮次平均帧率汇总对比')
        plt.xlabel('测试阶段')
        plt.ylabel('平均FPS')
        plt.xticks(range(len(stages)), stages, rotation=45)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        filename = "fps_summary.png"
        plt.savefig(charts_dir / filename, dpi=150, bbox_inches='tight')
        plt.close()

    def generate_html_report(self, report_name: str = "") -> str:
        """生成HTML格式的详细测试报告"""
        report_time = datetime.now()
        if report_name:
            report_filename = f"{report_name}.html"
        else:
            report_filename = f"test_report_{report_time.strftime('%Y%m%d_%H%M%S')}.html"
        report_path = self.report_dir / report_filename

        # 计算测试时长
        if self.test_data["test_info"]["test_start_time"] and self.test_data["test_info"]["test_end_time"]:
            start_time = datetime.fromisoformat(self.test_data["test_info"]["test_start_time"])
            end_time = datetime.fromisoformat(self.test_data["test_info"]["test_end_time"])
            duration = end_time - start_time
            self.test_data["test_info"]["test_duration"] = str(duration)

        html_content = self._generate_html_content(report_time)

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return str(report_path)

    def _generate_html_content(self, report_time: datetime) -> str:
        """生成HTML报告内容"""
        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CrealityScan固件升级测试报告</title>
    <style>
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #007acc;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #007acc;
            margin: 0;
        }}
        .section {{
            margin-bottom: 30px;
            padding: 20px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
        }}
        .section h2 {{
            color: #333;
            border-left: 4px solid #007acc;
            padding-left: 15px;
            margin-top: 0;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .summary-item {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }}
        .summary-item .label {{
            font-size: 14px;
            color: #666;
            margin-bottom: 5px;
        }}
        .summary-item .value {{
            font-size: 24px;
            font-weight: bold;
            word-wrap: break-word;
            overflow-wrap: break-word;
            max-width: 100%;
        }}
        .pass {{
            color: #28a745;
        }}
        .fail {{
            color: #dc3545;
        }}
        .comparison-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        .comparison-table th,
        .comparison-table td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        .comparison-table th {{
            background-color: #f2f2f2;
            font-weight: bold;
        }}
        .screenshot-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .screenshot-item {{
            text-align: center;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            padding: 10px;
        }}
        .screenshot-item img {{
            max-width: 100%;
            height: auto;
            border-radius: 4px;
        }}
        .recommendation {{
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 10px 0;
            border-radius: 4px;
        }}
        .chart-container {{
            text-align: center;
            margin: 20px 0;
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            color: #666;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>CrealityScan固件升级测试报告</h1>
            <p>生成时间: {report_time.strftime('%Y年%m月%d日 %H:%M:%S')}</p>
        </div>

        <!-- 测试基本信息 -->
        <div class="section">
            <h2>测试基本信息</h2>
            <div class="summary-grid">
                <div class="summary-item">
                    <div class="label">固件文件</div>
                    <div class="value">{self.test_data['test_info'].get('firmware_file', 'N/A')}</div>
                </div>
                <div class="summary-item">
                    <div class="label">测试结果</div>
                    <div class="value {'pass' if self.test_data['execution_summary'].get('overall_result') == 'PASS' else 'fail'}">
                        {self.test_data['execution_summary'].get('overall_result', 'N/A')}
                    </div>
                </div>
                <div class="summary-item">
                    <div class="label">成功率</div>
                    <div class="value">{self.test_data['execution_summary'].get('success_rate', 'N/A')}</div>
                </div>
                <div class="summary-item">
                    <div class="label">测试时长</div>
                    <div class="value">{self.test_data['test_info'].get('test_duration', 'N/A')}</div>
                </div>
            </div>
        </div>

        <!-- 执行摘要 -->
        <div class="section">
            <h2>执行摘要</h2>
            <table class="comparison-table">
                <tr>
                    <th>步骤</th>
                    <th>结果</th>
                </tr>
                {self._generate_steps_table_rows()}
            </table>
        </div>

        <!-- 性能图表 -->
        <div class="section">
            <h2>帧率统计图表</h2>
            {self._generate_charts_html()}
        </div>

        <!-- 测试截图 -->
        <div class="section">
            <h2>测试截图</h2>
            <div class="screenshot-grid">
                {self._generate_screenshot_grid()}
            </div>
        </div>

        <!-- 改进建议 -->
        <div class="section">
            <h2>改进建议</h2>
            {self._generate_recommendations()}
        </div>

        <div class="footer">
            <p>CrealityScan固件升级自动化测试框架 - 测试报告</p>
            <p>报告生成工具版本: 1.0</p>
        </div>
    </div>
</body>
</html>
        """

    def _generate_steps_table_rows(self) -> str:
        """生成步骤表格行"""
        rows = ""
        steps_detail = self.test_data["execution_summary"].get("steps_detail", {})
        for step, result in steps_detail.items():
            status = "通过" if result else "失败"
            color_class = "pass" if result else "fail"
            rows += f'<tr><td>{step}</td><td class="{color_class}">{status}</td></tr>\n'
        return rows


    def _generate_screenshot_grid(self) -> str:
        """生成截图网格"""
        grid = ""
        for screenshot in self.test_data["screenshots"]:
            grid += f"""
            <div class="screenshot-item">
                <h4>{screenshot['step']}</h4>
                <p>{screenshot['description']}</p>
                <img src="screenshots/{screenshot['filename']}" alt="{screenshot['description']}">
            </div>
            """
        return grid

    def _generate_recommendations(self) -> str:
        """生成改进建议"""
        if not self.test_data["recommendations"]:
            return "<p>暂无改进建议。</p>"

        recommendations_html = ""
        for rec in self.test_data["recommendations"]:
            priority_color = {
                "HIGH": "#dc3545",
                "MEDIUM": "#ffc107",
                "LOW": "#28a745"
            }.get(rec["priority"], "#6c757d")

            recommendations_html += f"""
            <div class="recommendation">
                <strong style="color: {priority_color};">[{rec['priority']}] {rec['category']}</strong>
                <p>{rec['message']}</p>
            </div>
            """

        return recommendations_html

    def _generate_single_mode_fps_charts(self, charts_dir: Path, frame_data: dict):
        """
        生成分模式帧率图表（蓝色线激光/红外）

        Args:
            charts_dir: 图表保存目录
            frame_data: 帧率数据，键名格式为 "{phase}-蓝色线激光" 或 "{phase}-红外"
        """
        if not MATPLOTLIB_AVAILABLE:
            return

        # 提取所有阶段
        phases = set()
        for key in frame_data.keys():
            if "-蓝色线激光" in key:
                phases.add(key.replace("-蓝色线激光", ""))
            elif "-红外" in key:
                phases.add(key.replace("-红外", ""))

        for phase in sorted(phases):
            blue_key = f"{phase}-蓝色线激光"
            ir_key = f"{phase}-红外"

            blue_data = frame_data.get(blue_key, {}).get("scan_fps", [])
            ir_data = frame_data.get(ir_key, {}).get("scan_fps", [])

            if not blue_data and not ir_data:
                continue

            plt.figure(figsize=(12, 6))
            plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial']
            plt.rcParams['axes.unicode_minus'] = False

            if blue_data:
                x = [p[0] for p in blue_data]
                y = [p[1] for p in blue_data]
                plt.plot(x, y, color='blue', linewidth=1.5, marker='o',
                        markersize=4, label='蓝色线激光')
                for xi, yi in zip(x, y):
                    plt.annotate(f'{int(yi)}', (xi, yi), textcoords='offset points',
                                xytext=(0, 6), ha='center', fontsize=7, color='blue')

            if ir_data:
                x = [p[0] for p in ir_data]
                y = [p[1] for p in ir_data]
                plt.plot(x, y, color='darkorange', linewidth=1.5, marker='s',
                        markersize=4, label='红外')
                for xi, yi in zip(x, y):
                    plt.annotate(f'{int(yi)}', (xi, yi), textcoords='offset points',
                                xytext=(0, 6), ha='center', fontsize=7, color='darkorange')

            plt.title(f'{phase}扫描帧率对比')
            plt.xlabel('时间（秒）')
            plt.ylabel('FPS')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()

            filename = f"fps_{phase}.png"
            plt.savefig(charts_dir / filename, dpi=150, bbox_inches='tight')
            plt.close()

    def _generate_charts_html(self) -> str:
        """生成图表HTML内容"""
        charts_html = ""
        charts_dir = self.report_dir / "charts"

        if not charts_dir.exists():
            return "<p>未生成性能图表</p>"

        # 获取所有图表文件
        chart_files = list(charts_dir.glob("fps_*.png"))

        if not chart_files:
            return "<p>暂无性能图表数据</p>"

        # 检查是否有循环测试图表
        cycle_charts = [f for f in chart_files if "第" in f.stem and "轮" in f.stem]
        summary_charts = [f for f in chart_files if "summary" in f.stem]
        # 分模式图表（非循环、非汇总的 fps_*.png）
        mode_charts = [f for f in chart_files if f not in cycle_charts and f not in summary_charts
                      and f.name != "fps_scan.png"]
        standard_charts = [f for f in chart_files if f.name == "fps_scan.png"]

        if cycle_charts:
            # 循环测试图表
            charts_html += "<h3>各轮次帧率对比</h3>"
            for chart_file in sorted(cycle_charts):
                charts_html += f"""
                <div class="chart-container">
                    <img src="charts/{chart_file.name}" alt="{chart_file.stem}" onerror="this.style.display='none'">
                </div>
                """

            # 汇总图表
            if summary_charts:
                charts_html += "<h3>帧率汇总对比</h3>"
                for chart_file in summary_charts:
                    charts_html += f"""
                    <div class="chart-container">
                        <img src="charts/{chart_file.name}" alt="{chart_file.stem}" onerror="this.style.display='none'">
                    </div>
                    """
        elif mode_charts:
            # 分模式图表
            for chart_file in sorted(mode_charts):
                phase_name = chart_file.stem.replace("fps_", "")
                charts_html += f"<h3>{phase_name}扫描帧率</h3>"
                charts_html += f"""
                <div class="chart-container">
                    <img src="charts/{chart_file.name}" alt="{chart_file.stem}" onerror="this.style.display='none'">
                </div>
                """
        elif standard_charts:
            # 标准测试图表
            for chart_file in standard_charts:
                charts_html += f"""
                <div class="chart-container">
                    <img src="charts/{chart_file.name}" alt="{chart_file.stem}" onerror="this.style.display='none'">
                </div>
                """

        return charts_html

    def generate_json_report(self, report_name: str = "") -> str:
        """生成JSON格式的测试数据报告"""
        report_time = datetime.now()
        if report_name:
            report_filename = f"{report_name}.json"
        else:
            report_filename = f"test_data_{report_time.strftime('%Y%m%d_%H%M%S')}.json"
        report_path = self.report_dir / report_filename

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.test_data, f, ensure_ascii=False, indent=2)

        return str(report_path)

    def save_report_data(self, data: Dict[str, Any]):
        """保存报告数据"""
        self.test_data.update(data)

    def get_report_summary(self) -> Dict[str, Any]:
        """获取报告摘要"""
        return {
            "overall_result": self.test_data["execution_summary"].get("overall_result"),
            "success_rate": self.test_data["execution_summary"].get("success_rate"),
            "test_duration": self.test_data["test_info"].get("test_duration"),
            "firmware_file": self.test_data["test_info"].get("firmware_file"),
            "report_generated": datetime.now().isoformat()
        }