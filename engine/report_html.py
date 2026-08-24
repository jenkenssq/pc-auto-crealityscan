from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List, Optional


def _h(s: Any) -> str:
    return html.escape("" if s is None else str(s))


def _status_badge(status: Any) -> str:
    text = str(status or "unknown").strip().lower()
    cls = {
        "passed": "passed",
        "failed": "failed",
        "stopped": "stopped",
        "skipped": "skipped",
    }.get(text, "unknown")
    label = {
        "passed": "通过",
        "failed": "失败",
        "stopped": "已停止",
        "skipped": "已跳过",
        "unknown": "未知",
    }.get(text, _h(status or "未知"))
    return f'<span class="badge {cls}">{label}</span>'


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _format_metric_value(value: Any, suffix: str = "", digits: int = 3) -> str:
    if value in (None, ""):
        return "-"
    try:
        number = float(value)
    except Exception:
        return _h(value)
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number))}{suffix}"
    return f"{number:.{digits}f}{suffix}"


def _build_polyline(
    rows: List[Dict[str, Any]],
    key: str,
    max_second: float,
    max_y: float,
    pad_left: float,
    pad_top: float,
    plot_w: float,
    plot_h: float,
) -> str:
    points: List[str] = []
    for row in rows:
        second = _float_value(row.get("second"))
        value = max(0.0, _float_value(row.get(key)))
        x = pad_left if max_second <= 0 else pad_left + (second / max_second) * plot_w
        y = pad_top + plot_h - (value / max_y) * plot_h
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def _render_trend_svg(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return '<div class="muted">无趋势数据</div>'

    width = 1080.0
    height = 320.0
    pad_left = 56.0
    pad_right = 18.0
    pad_top = 18.0
    pad_bottom = 42.0
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    max_second = max(_float_value(item.get("second")) for item in rows)
    max_y = max(
        100.0,
        max(_float_value(item.get("fps")) for item in rows),
        max(_float_value(item.get("cpu_percent")) for item in rows),
        max(_float_value(item.get("memory_percent")) for item in rows),
        1.0,
    )

    grid_lines: List[str] = []
    y_labels: List[str] = []
    for idx in range(5):
        ratio = idx / 4.0
        value = max_y * (1.0 - ratio)
        y = pad_top + plot_h * ratio
        grid_lines.append(
            f"<line x1='{pad_left:.2f}' y1='{y:.2f}' x2='{width - pad_right:.2f}' y2='{y:.2f}' class='chart-grid' />"
        )
        y_labels.append(
            f"<text x='{pad_left - 10:.2f}' y='{y + 4:.2f}' text-anchor='end' class='chart-axis'>{_h(round(value, 1))}</text>"
        )

    x_labels: List[str] = []
    x_ticks = min(6, max(2, int(max_second) + 1))
    for idx in range(x_ticks):
        second = 0.0 if x_ticks == 1 else (max_second * idx / max(1, x_ticks - 1))
        x = pad_left if max_second <= 0 else pad_left + (second / max_second) * plot_w
        x_labels.append(
            f"<text x='{x:.2f}' y='{height - 12:.2f}' text-anchor='middle' class='chart-axis'>{_h(int(round(second)))}s</text>"
        )

    fps_points = _build_polyline(rows, "fps", max_second, max_y, pad_left, pad_top, plot_w, plot_h)
    cpu_points = _build_polyline(rows, "cpu_percent", max_second, max_y, pad_left, pad_top, plot_w, plot_h)
    mem_points = _build_polyline(rows, "memory_percent", max_second, max_y, pad_left, pad_top, plot_w, plot_h)

    return (
        f"<svg viewBox='0 0 {width:.0f} {height:.0f}' class='trend-svg' role='img' aria-label='性能趋势图'>"
        f"<rect x='0' y='0' width='{width:.0f}' height='{height:.0f}' rx='16' class='chart-bg' />"
        f"{''.join(grid_lines)}"
        f"{''.join(y_labels)}"
        f"{''.join(x_labels)}"
        f"<polyline points='{_h(fps_points)}' class='chart-line fps' />"
        f"<polyline points='{_h(cpu_points)}' class='chart-line cpu' />"
        f"<polyline points='{_h(mem_points)}' class='chart-line mem' />"
        f"</svg>"
    )


def _render_trend_sections(step_results: List[Dict[str, Any]]) -> str:
    sections: List[str] = []
    for idx, item in enumerate(step_results, start=1):
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        trend_rows = extra.get("trend_by_second") if isinstance(extra.get("trend_by_second"), list) else []
        if not trend_rows:
            continue

        stats = [
            ("平均帧率", _format_metric_value(extra.get("avg_fps"))),
            ("峰值帧率", _format_metric_value(extra.get("peak_fps"))),
            ("最低帧率", _format_metric_value(extra.get("min_fps"))),
            ("CPU 峰值", _format_metric_value(extra.get("peak_cpu_percent"), "%")),
            ("内存峰值", _format_metric_value(extra.get("peak_memory_percent"), "%")),
            ("Wi-Fi 峰值", _format_metric_value(extra.get("peak_wifi_rate_kbps"), " kbps")),
        ]
        wifi_adapter = str(extra.get("wifi_interface_name") or "").strip()
        if wifi_adapter:
            stats.append(("Wi-Fi 适配器", wifi_adapter))

        stats_html = "".join(
            "<div class='trend-stat'>"
            f"<span class='trend-stat-label'>{_h(label)}</span>"
            f"<strong class='trend-stat-value'>{_h(value)}</strong>"
            "</div>"
            for label, value in stats
        )
        sections.append(
            "<div class='trend-card'>"
            f"<div class='trend-head'><div><h3>步骤 {idx} · {_h(item.get('name'))}</h3>"
            f"<p>{_h(item.get('id'))}</p></div>{_status_badge(item.get('status'))}</div>"
            "<div class='trend-legend'>"
            "<span class='legend-item'><i class='legend-dot fps'></i>帧率</span>"
            "<span class='legend-item'><i class='legend-dot cpu'></i>CPU</span>"
            "<span class='legend-item'><i class='legend-dot mem'></i>内存</span>"
            "</div>"
            f"{_render_trend_svg(trend_rows)}"
            f"<div class='trend-stats'>{stats_html}</div>"
            "</div>"
        )
    if not sections:
        return '<div class="muted">当前报告中没有可用的性能趋势数据</div>'
    return "".join(sections)


def _step_metric_parts(step_id: str, extra: Dict[str, Any]) -> List[str]:
    metric_parts: List[str] = []
    if step_id == "crealityscan.scan_until_frames_then_stop":
        if extra.get("avg_fps") not in (None, ""):
            metric_parts.append(f"扫描帧率 {_format_metric_value(extra.get('avg_fps'))}")
        return metric_parts

    if extra.get("avg_fps") not in (None, ""):
        metric_parts.append(f"骞冲潎甯х巼 {extra.get('avg_fps')}")
    if extra.get("peak_fps") not in (None, ""):
        metric_parts.append(f"宄板€煎抚鐜?{extra.get('peak_fps')}")
    if extra.get("min_fps") not in (None, ""):
        metric_parts.append(f"鏈€浣庡抚鐜?{extra.get('min_fps')}")
    if extra.get("peak_cpu_percent") not in (None, ""):
        metric_parts.append(f"cpu_peak {extra.get('peak_cpu_percent')}%")
    if extra.get("peak_memory_percent") not in (None, ""):
        metric_parts.append(f"mem_peak {extra.get('peak_memory_percent')}%")
    if extra.get("peak_wifi_rate_kbps") not in (None, ""):
        metric_parts.append(f"wifi_peak {extra.get('peak_wifi_rate_kbps')}kbps")
    if extra.get("stop_click_frame") not in (None, ""):
        metric_parts.append(f"stop_frame {extra.get('stop_click_frame')}")
    if extra.get("scan_elapsed_sec") not in (None, ""):
        metric_parts.append(f"elapsed {extra.get('scan_elapsed_sec')}s")
    if extra.get("operation_elapsed_sec") not in (None, ""):
        operation_elapsed_label = str(extra.get("operation_elapsed_label") or "鎿嶄綔鑰楁椂").strip()
        metric_parts.append(
            f"{operation_elapsed_label} {_format_metric_value(extra.get('operation_elapsed_sec'), 's')}"
        )
    if extra.get("fps_seconds_count") not in (None, ""):
        metric_parts.append(f"甯х巼閲囨牱鏁?{extra.get('fps_seconds_count')}")
    elif extra.get("max_frame") not in (None, ""):
        metric_parts.append(f"max_frame {extra.get('max_frame')}")
    return metric_parts


def render_report_html(
    case_name: str,
    started_at: str,
    finished_at: str,
    step_results: List[Dict[str, Any]],
    keyword_hits: Optional[Dict[str, List[str]]] = None,
    device_info: Optional[Dict[str, str]] = None,
    total_mode_count: Optional[int] = None,
) -> str:
    keyword_hits = keyword_hits if isinstance(keyword_hits, dict) else {}
    ok_count = sum(1 for r in step_results if r.get("status") == "passed")
    fail_count = sum(1 for r in step_results if r.get("status") == "failed")
    stopped_count = sum(1 for r in step_results if r.get("status") == "stopped")
    skipped_count = sum(1 for r in step_results if r.get("status") == "skipped")
    total_count = len(step_results)
    overall_status = "failed" if fail_count else ("passed" if ok_count else "unknown")
    total_runtime_sec = round(sum(_float_value(r.get("duration_sec")) or 0.0 for r in step_results), 1)
    screenshot_count = sum(1 for r in step_results if r.get("screenshot"))
    keyword_total = sum(
        len(value) if isinstance(value, list) else max(0, int(value))
        for value in keyword_hits.values()
        if isinstance(value, (list, int, float))
    )
    failed_names = [str(r.get("name") or r.get("id") or "") for r in step_results if r.get("status") == "failed"]
    _SCAN_MODE_ID_PREFIX = "crealityscan.configure_scan_params_"
    _POINT_CLOUD_SWITCH_ID = "crealityscan.pause_switch_point_cloud_scan"
    _POINT_CLOUD_SCAN_ID = "crealityscan.scan_until_frames_then_stop"
    _FRAME_POINT_TOKEN = "框架点"

    module_names = {
        "p1": "P1",
        "pika": "Pika",
        "raptor": "Raptor",
        "raptor_x": "Raptor X",
        "raptor_pro": "Raptor Pro",
        "s1": "S1",
    }
    mode_results = [
        result
        for result in step_results
        if str(result.get("id") or "").startswith(_SCAN_MODE_ID_PREFIX)
    ]
    passed_mode_results = [result for result in mode_results if result.get("status") == "passed"]

    def _mode_item_html(name: str, module_name: str, duration_text: str, metric_label: str) -> str:
        return (
            '<li class="mode-dialog-item" data-testid="passed-mode-item">'
            f'<div class="mode-dialog-name">{_h(name)}</div>'
            '<dl class="mode-dialog-meta">'
            f'<div><dt>模组</dt><dd>{_h(module_name)}</dd></div>'
            f'<div><dt>{_h(metric_label)}</dt><dd class="mono">{_h(duration_text)}</dd></div>'
            '</dl>'
            '</li>'
        )

    passed_mode_items: List[str] = []
    frame_point_module: Optional[str] = None
    await_point_cloud_scan = False
    for result in step_results:
        step_id = str(result.get("id") or "")
        status = result.get("status")
        if step_id.startswith(_SCAN_MODE_ID_PREFIX):
            extra = result.get("extra") if isinstance(result.get("extra"), dict) else {}
            step_name = str(result.get("name") or "")
            mode_name = str(
                extra.get("preset_name")
                or (step_name.removeprefix("扫描参数：") if step_name else "")
                or extra.get("preset_input")
                or step_id
            )
            module_key = step_id.removeprefix(_SCAN_MODE_ID_PREFIX).lower()
            module_name = module_names.get(module_key, module_key.upper() or "未知模组")
            if status != "passed":
                frame_point_module = None
                await_point_cloud_scan = False
                continue
            duration = result.get("duration_sec")
            duration_text = f"{float(duration):.3f}s" if isinstance(duration, (int, float)) else "-"
            passed_mode_items.append(_mode_item_html(mode_name, module_name, duration_text, "配置耗时"))
            frame_point_module = module_name if _FRAME_POINT_TOKEN in mode_name else None
            await_point_cloud_scan = False
        elif step_id == _POINT_CLOUD_SWITCH_ID:
            await_point_cloud_scan = frame_point_module is not None and status == "passed"
        elif step_id == _POINT_CLOUD_SCAN_ID:
            if await_point_cloud_scan and status == "passed":
                duration = result.get("duration_sec")
                duration_text = f"{float(duration):.3f}s" if isinstance(duration, (int, float)) else "-"
                passed_mode_items.append(
                    _mode_item_html("切点云", frame_point_module, duration_text, "切点云耗时")
                )
            await_point_cloud_scan = False

    selected_mode_count = total_mode_count if total_mode_count is not None else len(mode_results)
    passed_mode_count = len(passed_mode_results)
    mode_pass_percent = (
        round(passed_mode_count * 100 / selected_mode_count) if selected_mode_count else 0
    )
    passed_mode_items_html = (
        f'<ul class="mode-dialog-list">{"".join(passed_mode_items)}</ul>'
        if passed_mode_items
        else '<div class="mode-dialog-empty" data-testid="passed-modes-empty">本次没有通过的扫描模式</div>'
    )

    rows: List[str] = []
    for idx, r in enumerate(step_results, start=1):
        status = r.get("status")
        dur = r.get("duration_sec")
        dur_text = f"{float(dur):.3f}" if isinstance(dur, (int, float)) else _h(dur or "-")
        screenshot = r.get("screenshot")
        extra = r.get("extra") if isinstance(r.get("extra"), dict) else {}
        metric_parts = _step_metric_parts(str(r.get("id") or ""), extra)

        metrics_cell = (
            "".join(f"<span class='metric-pill mono'>{_h(part)}</span>" for part in metric_parts)
            if metric_parts
            else '<span class="muted">无补充指标</span>'
        )
        screenshot_cell = (
            f'<a class="link-pill" href="{_h(screenshot)}">{_h(Path(screenshot).name)}</a>'
            if screenshot
            else '<span class="muted">无截图</span>'
        )
        err = str(r.get("error") or "").strip()
        attempt = r.get("attempt") if r.get("attempt") not in (None, "") else "-"
        status_class = str(status or "unknown").strip().lower()
        if status_class not in {"passed", "failed", "stopped", "skipped"}:
            status_class = "unknown"
        rows.append(
            f"<tr class='step-row {status_class}'>"
            f"<td class='step-index'>{idx:02d}</td>"
            f"<td><div class='step-name'>{_h(r.get('name'))}</div><div class='step-id mono'>{_h(r.get('id'))}</div></td>"
            f"<td class='mono'>{_h(r.get('version'))}</td>"
            f"<td>{_status_badge(status)}</td>"
            f"<td class='mono'>{dur_text}</td>"
            f"<td class='mono'>{_h(attempt)}</td>"
            f"<td><div class='metric-cluster'>{metrics_cell}</div></td>"
            f"<td>{screenshot_cell}</td>"
            f"<td><pre class='error-block {'has-error' if err else 'no-error'}'>{_h(err) if err else '无异常'}</pre></td>"
            "</tr>"
        )

    device_rows = [
        ("模组名称", (device_info or {}).get("camera_name", "")),
        ("模组 SN", (device_info or {}).get("camera_serial_number", "")),
        ("连接方式", (device_info or {}).get("camera_connection_type", "")),
        ("固件版本", (device_info or {}).get("camera_firmware_version", "")),
    ]
    device_section_html = "".join(
        "<div class='info-item'>"
        f"<span class='info-label'>{_h(label)}</span>"
        f"<strong class='info-value'>{_h(value or '-')}</strong>"
        "</div>"
        for label, value in device_rows
    )

    timeline_rows = [
        ("开始时间", started_at or "-"),
        ("结束时间", finished_at or "-"),
        ("累计步骤耗时", f"{total_runtime_sec:.1f}s" if total_runtime_sec else "-"),
        ("失败步骤", " / ".join(failed_names[:3]) if failed_names else "无"),
    ]
    timeline_html = "".join(
        "<div class='timeline-item'>"
        f"<span class='timeline-label'>{_h(label)}</span>"
        f"<strong class='timeline-value'>{_h(value)}</strong>"
        "</div>"
        for label, value in timeline_rows
    )

    trend_section_html = _render_trend_sections(step_results)
    runtime_sub = "基于步骤 duration_sec 聚合"
    keyword_sub = "日志关键字命中条数"

    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Jens 自动化报告 - {_h(case_name)}</title>
  <style>
    :root {{
      color-scheme: light;
      --canvas: #f3f6fa;
      --surface: #ffffff;
      --surface-subtle: #f8fafc;
      --ink: #111827;
      --muted: #64748b;
      --line: #dbe3ed;
      --line-strong: #c7d2df;
      --accent: #2563eb;
      --accent-soft: #eff6ff;
      --accent-deep: #1d4ed8;
      --accent-deep-soft: #eff6ff;
      --success: #137a4b;
      --success-soft: #e7f7ef;
      --danger: #b42335;
      --danger-soft: #fff0f1;
      --warn: #9a5b00;
      --warn-soft: #fff6df;
      --shadow: 0 12px 32px rgba(55, 75, 105, 0.07);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: var(--canvas);
      font: 14px/1.55 "Aptos", "Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI", sans-serif;
    }}
    body::before {{ display: none; }}
    .report-shell {{
      width: 100%;
      max-width: 1680px;
      margin: 0 auto;
      padding: 24px 28px 48px;
      animation: none;
    }}
    .report-header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
      align-items: center;
      gap: 28px;
      padding: 22px 24px;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: var(--shadow);
      color: var(--ink);
    }}
    .report-header h1 {{
      margin: 0;
      font: 750 clamp(26px, 3vw, 38px)/1.12 "Aptos Display", "Segoe UI Variable Display", "Microsoft YaHei UI", sans-serif;
      letter-spacing: -0.04em;
    }}
    .hero-meta {{ display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 12px; }}
    .hero-chip {{
      display: inline-flex;
      align-items: center;
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
      color: var(--muted);
      font-size: 12px;
    }}
    .hero-chip + .hero-chip::before {{
      content: "";
      width: 1px;
      height: 12px;
      margin-right: 20px;
      background: var(--line-strong);
    }}
    .hero-status {{
      display: grid;
      grid-template-columns: auto 1fr;
      align-items: start;
      gap: 14px;
      min-height: auto;
      padding-left: 24px;
      border-left: 1px solid var(--line);
    }}
    .status-panel {{ padding: 1px 0 0; border: 0; border-radius: 0; background: transparent; }}
    .status-panel .badge {{ min-width: 76px; padding: 7px 12px; font-size: 12px; }}
    .status-note {{ color: var(--muted); font-size: 12px; line-height: 1.55; }}
    .summary-board {{
      display: grid;
      grid-template-columns: minmax(210px, 1.35fr) repeat(5, minmax(130px, 1fr));
      gap: 0;
      margin: 16px 0;
      overflow: hidden;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: var(--shadow);
    }}
    .mode-card {{
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 148px;
      padding: 18px 20px;
      border: 0;
      border-right: 1px solid var(--line);
      border-radius: 0;
      background: var(--accent-soft);
      box-shadow: none;
      color: var(--ink);
      font: inherit;
      text-align: left;
      cursor: pointer;
      transition: background-color 160ms ease-out, box-shadow 160ms ease-out;
    }}
    .mode-card:hover {{ background: #e4efff; }}
    .mode-card:focus-visible {{ outline: 3px solid rgba(37, 99, 235, 0.32); outline-offset: -3px; }}
    .mode-card::after {{ display: none; }}
    .mode-label {{ display: block; color: var(--accent-deep); font-size: 12px; font-weight: 700; }}
    .mode-count {{ display: flex; align-items: baseline; margin: 14px 0 12px; gap: 8px; }}
    .mode-value {{
      color: var(--accent-deep);
      font: 760 48px/0.9 "Aptos Display", "Segoe UI Variable Display", sans-serif;
      letter-spacing: -0.05em;
    }}
    .mode-total {{ color: var(--muted); font-size: 13px; }}
    .mode-foot {{ display: flex; justify-content: space-between; gap: 10px; margin: 0; color: var(--muted); font-size: 11px; }}
    .mode-foot span:last-child {{ color: var(--accent-deep); font-weight: 700; }}
    .mode-action {{ display: block; margin-top: 7px; color: var(--accent-deep); font-size: 11px; font-weight: 650; }}
    .mode-dialog {{
      width: min(560px, calc(100vw - 32px));
      max-height: min(720px, calc(100vh - 48px));
      padding: 0;
      overflow: hidden;
      color: var(--ink);
      background: var(--surface);
      border: 1px solid var(--line-strong);
      border-radius: 16px;
      box-shadow: 0 24px 64px rgba(30, 50, 80, 0.22);
    }}
    .mode-dialog::backdrop {{ background: rgba(15, 23, 42, 0.48); }}
    .mode-dialog-head {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 20px;
      padding: 22px 24px 18px;
      border-bottom: 1px solid var(--line);
    }}
    .mode-dialog-head h2 {{ margin: 0 0 5px; font-size: 20px; line-height: 1.25; letter-spacing: -0.02em; }}
    .mode-dialog-head p {{ margin: 0; color: var(--muted); font-size: 12px; }}
    .mode-dialog-close {{
      flex: 0 0 auto;
      min-height: 36px;
      padding: 7px 13px;
      color: var(--ink);
      background: var(--surface-subtle);
      border: 1px solid var(--line);
      border-radius: 8px;
      font: 650 12px/1.2 inherit;
      cursor: pointer;
    }}
    .mode-dialog-close:hover {{ background: #eef2f7; }}
    .mode-dialog-close:focus-visible {{ outline: 3px solid rgba(37, 99, 235, 0.28); outline-offset: 2px; }}
    .mode-dialog-body {{ max-height: calc(100vh - 180px); padding: 0 24px 24px; overflow-y: auto; }}
    .mode-dialog-list {{ margin: 0; padding: 0; list-style: none; }}
    .mode-dialog-item {{ padding: 18px 0; border-bottom: 1px solid var(--line); }}
    .mode-dialog-item:last-child {{ border-bottom: 0; }}
    .mode-dialog-name {{ overflow-wrap: anywhere; font-size: 15px; font-weight: 700; line-height: 1.45; }}
    .mode-dialog-meta {{ display: flex; flex-wrap: wrap; gap: 10px 28px; margin: 10px 0 0; }}
    .mode-dialog-meta > div {{ display: flex; gap: 7px; }}
    .mode-dialog-meta dt {{ color: var(--muted); font-size: 12px; }}
    .mode-dialog-meta dd {{ margin: 0; color: var(--ink); font-size: 12px; font-weight: 650; }}
    .mode-dialog-empty {{ margin-top: 22px; padding: 28px 18px; color: var(--muted); text-align: center; background: var(--surface-subtle); border-radius: 12px; }}
    .metric-grid {{ display: contents; }}
    .overview-card, .overview-card.wide {{
      grid-column: auto;
      min-width: 0;
      padding: 18px 16px;
      border: 0;
      border-right: 1px solid var(--line);
      border-radius: 0;
      background: var(--surface);
      box-shadow: none;
    }}
    .overview-card:last-child {{ border-right: 0; }}
    .overview-label {{
      display: block;
      margin-bottom: 16px;
      color: var(--muted);
      font-size: 11px;
      letter-spacing: 0;
      text-transform: none;
    }}
    .overview-value {{
      display: block;
      margin-bottom: 8px;
      color: var(--ink);
      font: 740 30px/1 "Aptos Display", "Segoe UI Variable Display", sans-serif;
      letter-spacing: -0.04em;
    }}
    .overview-card.success .overview-value {{ color: var(--success); }}
    .overview-card.danger .overview-value {{ color: var(--danger); }}
    .overview-sub {{ display: block; color: var(--muted); font-size: 11px; line-height: 1.4; }}
    .main-layout {{
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) minmax(340px, 0.5fr);
      gap: 16px;
      align-items: start;
    }}
    .main-layout > main {{ display: contents; }}
    .main-layout > aside {{ grid-column: 2; grid-row: 2; }}
    .main-layout > main > .section-card:first-child {{ grid-column: 1 / -1; grid-row: 1; }}
    .main-layout > main > .section-card:nth-child(2) {{ grid-column: 1; grid-row: 2; }}
    .stack {{ display: grid; gap: 16px; min-width: 0; }}
    .section-card {{
      padding: 0;
      overflow: hidden;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: var(--shadow);
    }}
    .section-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      margin: 0;
      padding: 18px 20px 14px;
      border-bottom: 1px solid var(--line);
    }}
    .section-head h2 {{
      margin: 0 0 3px;
      font: 720 19px/1.2 "Aptos Display", "Segoe UI Variable Display", "Microsoft YaHei UI", sans-serif;
      letter-spacing: -0.02em;
    }}
    .section-head p {{ margin: 0; max-width: 72ch; color: var(--muted); font-size: 12px; }}
    .section-stamp {{ display: none; }}
    .table-shell {{
      overflow-x: auto;
      border: 0;
      border-radius: 0;
      background: var(--surface);
    }}
    table {{ width: 100%; min-width: 1080px; border-collapse: collapse; }}
    thead th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f1f5f9;
      color: #475569;
      font-size: 11px;
      letter-spacing: 0;
      text-transform: none;
    }}
    th, td {{
      padding: 11px 12px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid var(--line);
    }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    tbody tr:nth-child(even) {{ background: var(--surface-subtle); }}
    tbody tr:hover {{ background: var(--accent-soft); }}
    tbody tr.failed {{ background: var(--danger-soft); }}
    tbody tr.failed:hover {{ background: #ffe4e7; }}
    .step-index {{ color: var(--muted); font-weight: 700; }}
    .step-name {{ margin-bottom: 3px; font-weight: 700; }}
    .step-id {{ color: var(--muted); }}
    .step-id, .mono {{ font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11px; }}
    .metric-cluster {{ display: flex; flex-wrap: wrap; gap: 5px; max-width: 340px; }}
    .metric-pill, .link-pill {{
      display: inline-flex;
      align-items: center;
      padding: 4px 7px;
      border-color: #cbdcf7;
      border-radius: 6px;
      background: var(--accent-soft);
      color: var(--accent-deep);
      font-size: 11px;
      line-height: 1.2;
      text-decoration: none;
    }}
    .link-pill:hover {{ transform: none; box-shadow: none; text-decoration: underline; }}
    .device-grid, .timeline-grid {{ display: grid; gap: 0; }}
    .device-grid {{ grid-template-columns: 1fr; }}
    .info-item, .timeline-item, .trend-stat {{
      min-height: 0;
      padding: 13px 18px;
      border: 0;
      border-bottom: 1px solid var(--line);
      border-radius: 0;
      background: transparent;
    }}
    .info-item:last-child, .timeline-item:last-child {{ border-bottom: 0; }}
    .info-label, .timeline-label, .trend-stat-label {{ display: block; margin-bottom: 5px; color: var(--muted); font-size: 11px; }}
    .info-value, .timeline-value {{ font-size: 13px; line-height: 1.45; word-break: break-word; }}
    .trend-wrap {{ display: grid; gap: 0; }}
    .trend-card {{
      padding: 18px 20px 20px;
      border: 0;
      border-bottom: 1px solid var(--line);
      border-radius: 0;
      background: var(--surface);
    }}
    .trend-card:last-child {{ border-bottom: 0; }}
    .trend-head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 14px; }}
    .trend-head h3 {{ font-size: 16px; }}
    .trend-head h3, .trend-head p {{ margin-top: 0; }}
    .trend-head p {{ margin-bottom: 0; color: var(--muted); font-size: 12px; }}
    .trend-legend {{ display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 10px; color: var(--muted); font-size: 12px; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
    .legend-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; }}
    .legend-dot.fps {{ background: var(--accent); }}
    .legend-dot.cpu {{ background: var(--danger); }}
    .legend-dot.mem {{ background: var(--success); }}
    .trend-svg {{ display: block; width: 100%; height: auto; }}
    .chart-bg {{ fill: var(--surface-subtle); stroke: var(--line); }}
    .chart-grid {{ stroke: var(--line); }}
    .chart-axis {{ fill: var(--muted); }}
    .chart-line {{ fill: none; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }}
    .chart-line.fps {{ stroke: var(--accent); }}
    .chart-line.cpu {{ stroke: var(--danger); }}
    .chart-line.mem {{ stroke: var(--success); }}
    .trend-stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0; margin-top: 14px; border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }}
    .trend-stat {{ border-right: 1px solid var(--line); border-bottom: 0; }}
    .trend-stat:last-child {{ border-right: 0; }}
    .trend-stat-value {{ color: var(--ink); font-size: 13px; }}
    .badge {{ display: inline-flex; align-items: center; justify-content: center; min-width: 62px; padding: 5px 9px; border-radius: 6px; font-size: 11px; font-weight: 700; }}
    .badge.passed {{ background: var(--success-soft); color: var(--success); }}
    .badge.failed {{ background: var(--danger-soft); color: var(--danger); }}
    .badge.stopped {{ background: var(--warn-soft); color: var(--warn); }}
    .badge.skipped {{ background: #eef2f6; color: #526174; }}
    .badge.unknown {{ background: #eef2f6; color: #526174; }}
    .error-block {{ font-size: 11px; }}
    .error-block.has-error {{ color: var(--danger); }}
    .error-block.no-error {{ color: var(--muted); }}
    @media (max-width: 1180px) {{
      .summary-board {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .mode-card {{ border-bottom: 1px solid var(--line); }}
      .overview-card:nth-child(-n+2) {{ border-bottom: 1px solid var(--line); }}
      .main-layout {{ grid-template-columns: 1fr; }}
      .main-layout > aside {{ grid-column: 1; grid-row: auto; grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .main-layout > main > .section-card:nth-child(2) {{ grid-column: 1; }}
    }}
    @media (max-width: 760px) {{
      .report-shell {{ padding: 12px 12px 32px; }}
      .report-header {{ grid-template-columns: 1fr; gap: 16px; padding: 18px; }}
      .hero-status {{ padding: 14px 0 0; border-top: 1px solid var(--line); border-left: 0; }}
      .hero-chip + .hero-chip::before {{ display: none; }}
      .hero-meta {{ display: grid; gap: 5px; }}
      .summary-board {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .mode-card {{ min-height: 136px; border-right: 1px solid var(--line); }}
      .overview-card {{ min-height: 136px; border-bottom: 1px solid var(--line); }}
      .overview-card:nth-child(odd) {{ border-right: 0; }}
      .main-layout > aside {{ grid-template-columns: 1fr; }}
      .section-head {{ padding: 16px; }}
      .trend-card {{ padding: 16px; }}
      .trend-stats {{ grid-template-columns: 1fr; }}
      .trend-stat {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .trend-stat:last-child {{ border-bottom: 0; }}
      .mode-dialog-head {{ padding: 18px 18px 15px; }}
      .mode-dialog-body {{ padding: 0 18px 18px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{ scroll-behavior: auto !important; animation: none !important; transition: none !important; }}
    }}
  </style>
</head>
<body>
  <div class=\"report-shell\">
    <header class=\"report-header\">
      <div>
        <h1>{_h(case_name)}</h1>
        <div class=\"hero-meta\">
          <span class=\"hero-chip\">开始 · {_h(started_at or "-")}</span>
          <span class=\"hero-chip\">结束 · {_h(finished_at or "-")}</span>
          <span class=\"hero-chip\">步骤耗时 · {_h(runtime_sub)}</span>
        </div>
      </div>
      <div class=\"hero-status\">
        <div class=\"status-panel\">{_status_badge(overall_status)}</div>
        <div class=\"status-note\">当前报告共 {total_count} 个步骤，其中失败 {fail_count} 个、停止 {stopped_count} 个、跳过 {skipped_count} 个。若失败不为 0，请先从步骤矩阵和运行时间线开始排查。</div>
      </div>
    </header>

    <section class=\"summary-board\">
      <button type=\"button\" class=\"mode-card\" data-testid=\"passed-modes\" data-pass-percent=\"{mode_pass_percent}\" aria-haspopup=\"dialog\" aria-controls=\"passed-modes-dialog\">
        <span class=\"mode-label\">通过的模式</span>
        <div class=\"mode-count\">
          <strong class=\"mode-value\">{passed_mode_count}</strong>
          <span class=\"mode-total\">/ 已选择 {selected_mode_count}</span>
        </div>
        <div>
          <div class=\"mode-foot\">
            <span>扫描参数配置步骤</span>
            <span>{mode_pass_percent}% 通过</span>
          </div>
          <span class=\"mode-action\">点击查看详情</span>
        </div>
      </button>
      <div class=\"metric-grid\">
        <div class=\"overview-card\">
          <span class=\"overview-label\">步骤总数</span>
          <strong class=\"overview-value\">{total_count}</strong>
          <span class=\"overview-sub\">本次写入报告的步骤数量</span>
        </div>
        <div class=\"overview-card success\">
          <span class=\"overview-label\">通过步骤</span>
          <strong class=\"overview-value\">{ok_count}</strong>
          <span class=\"overview-sub\">运行链中正常收敛的步骤</span>
        </div>
        <div class=\"overview-card danger\">
          <span class=\"overview-label\">失败步骤</span>
          <strong class=\"overview-value\">{fail_count}</strong>
          <span class=\"overview-sub\">需要优先复盘的异常节点</span>
        </div>
        <div class=\"overview-card\">
          <span class=\"overview-label\">累计耗时</span>
          <strong class=\"overview-value\">{_h(f'{total_runtime_sec:.1f}s' if total_runtime_sec else '-')}</strong>
          <span class=\"overview-sub\">{_h(runtime_sub)}</span>
        </div>
        <div class=\"overview-card wide\">
          <span class=\"overview-label\">关键字命中</span>
          <strong class=\"overview-value\">{keyword_total}</strong>
          <span class=\"overview-sub\">{_h(keyword_sub)} · 截图 {screenshot_count}</span>
        </div>
      </div>
    </section>

    <div class=\"main-layout\">
      <main class=\"stack\">
        <section class=\"section-card\">
          <div class=\"section-head\">
            <div>
              <h2>步骤矩阵</h2>
            </div>
          </div>
          <div class=\"table-shell\">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                   <th>步骤</th>
                   <th>版本</th>
                   <th>状态</th>
                   <th>耗时（秒）</th>
                   <th>尝试次数</th>
                   <th>指标</th>
                   <th>产物</th>
                   <th>异常</th>
                </tr>
              </thead>
              <tbody>{''.join(rows)}</tbody>
            </table>
          </div>
        </section>

        <section class=\"section-card\">
          <div class=\"section-head\">
            <div>
              <h2>性能趋势</h2>
              <p>仅展示有趋势数据的步骤。优先关注帧率断崖、CPU 峰值和内存占用的同步变化。</p>
            </div>
          </div>
          <div class=\"trend-wrap\">{trend_section_html}</div>
        </section>
      </main>

      <aside class=\"stack\">
        <section class=\"section-card\">
          <div class=\"section-head\">
            <div>
              <h2>设备档案</h2>

            </div>
          </div>
          <div class=\"device-grid\">{device_section_html}</div>
        </section>

        <section class=\"section-card\">
          <div class=\"section-head\">
            <div>
              <h2>运行时间线</h2>
              <p>保留本次执行的时间节点与失败摘要。</p>
            </div>
          </div>
          <div class=\"timeline-grid\">{timeline_html}</div>
        </section>
      </aside>
    </div>
  </div>
  <dialog id=\"passed-modes-dialog\" class=\"mode-dialog\" aria-labelledby=\"passed-modes-dialog-title\">
    <div class=\"mode-dialog-head\">
      <div>
        <h2 id=\"passed-modes-dialog-title\">已通过的扫描模式</h2>
        <p>本次选择 {selected_mode_count} 个模式，通过 {passed_mode_count} 个。</p>
      </div>
      <button type=\"button\" class=\"mode-dialog-close\" data-dialog-close>关闭</button>
    </div>
    <div class=\"mode-dialog-body\">{passed_mode_items_html}</div>
  </dialog>
  <script>
    (() => {{
      const trigger = document.querySelector('[data-testid="passed-modes"]');
      const dialog = document.getElementById('passed-modes-dialog');
      const closeButton = dialog?.querySelector('[data-dialog-close]');
      if (!trigger || !dialog) return;

      trigger.addEventListener('click', () => {{
        if (typeof dialog.showModal === 'function') dialog.showModal();
        else dialog.setAttribute('open', '');
      }});
      closeButton?.addEventListener('click', () => dialog.close());
      dialog.addEventListener('click', (event) => {{
        if (event.target === dialog) dialog.close();
      }});
    }})();
  </script>
</body>
</html>
"""
