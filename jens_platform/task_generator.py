from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from engine.defaults import DEFAULT_KEYWORDS
from jens_platform.case_store import CaseModel, CaseStep
from jens_runtime import get_resource_root

TASK_KIND_OPEN_STREAM = "开流"
TASK_KIND_POSTPROCESS = "后处理"
TASK_KIND_FPS_STAT = "帧率统计"
CONNECTION_USB = "USB"
CONNECTION_WIFI = "Wi-Fi"

# 帧率统计任务的业务模式顺序（与 帧率统计模板.xlsx 的 G3/H3 行顺序一致）。
FPS_STAT_MODE_ORDER: tuple[str, ...] = (
    "平行线",
    "单线",
    "交叉",
    "无标记点",
    "大物体",
    "中物体",
    "小物体",
    "人脸",
    "人体",
)
# 帧率统计任务默认目标帧数。
DEFAULT_FPS_STAT_FRAMES = 1000


@dataclass(frozen=True)
class ModulePresetSource:
    module_name: str
    display_name: str
    configure_step_id: str
    include_activate_window: bool = True
    supports_connection: bool = False
    pika_waits: bool = False


@dataclass(frozen=True)
class ScanPreset:
    key: str
    name: str
    aliases: tuple[str, ...] = ()
    task_profile: str = "standard"
    connections: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskGenerationOption:
    module_name: str
    task_kind: str
    label: str


MODULE_PRESET_SOURCES: dict[str, ModulePresetSource] = {
    "feeret": ModulePresetSource("feeret", "Ferret", "crealityscan.configure_scan_params_ferret"),
    "otter": ModulePresetSource("otter", "Otter", "crealityscan.configure_scan_params_otter"),
    "otter lite": ModulePresetSource(
        "otter lite", "Otter Lite", "crealityscan.configure_scan_params_otter_lite"
    ),
    "otter lite basic": ModulePresetSource(
        "otter lite basic",
        "Otter Lite Basic",
        "crealityscan.configure_scan_params_otter_lite_basic",
    ),
    "P1": ModulePresetSource(
        "P1", "P1", "crealityscan.configure_scan_params_p1", supports_connection=True
    ),
    "P1S": ModulePresetSource(
        "P1S", "P1S", "crealityscan.configure_scan_params_p1s", supports_connection=True
    ),
    "pika": ModulePresetSource(
        "pika",
        "Pika",
        "crealityscan.configure_scan_params_pika",
        supports_connection=True,
        pika_waits=True,
    ),
    "raptor": ModulePresetSource(
        "raptor", "Raptor", "crealityscan.configure_scan_params_raptor", include_activate_window=False
    ),
    "raptor x": ModulePresetSource(
        "raptor x",
        "Raptor X",
        "crealityscan.configure_scan_params_raptor_x",
        include_activate_window=False,
        supports_connection=True,
    ),
    "raptor pro": ModulePresetSource(
        "raptor pro",
        "Raptor Pro",
        "crealityscan.configure_scan_params_raptor_pro",
        include_activate_window=False,
        supports_connection=True,
    ),
    "S1": ModulePresetSource(
        "S1", "S1", "crealityscan.configure_scan_params_s1", supports_connection=True
    ),
    "X1": ModulePresetSource(
        "X1", "X1", "crealityscan.configure_scan_params_x1", supports_connection=True
    ),
}

# 兼容旧代码和扩展；模式本身不再存放在这里。
TASK_GENERATOR_CONFIG = MODULE_PRESET_SOURCES


def _project_root(project_root: Optional[Path] = None) -> Path:
    explicit_root = Path(project_root) if project_root is not None else None
    if explicit_root is not None and (explicit_root / "steps").is_dir():
        return explicit_root

    resource_root = get_resource_root()
    if (resource_root / "steps").is_dir():
        return resource_root

    return explicit_root if explicit_root is not None else Path(__file__).resolve().parents[1]


def _preset_path(source: ModulePresetSource, project_root: Optional[Path] = None) -> Path:
    step_dir_name = source.configure_step_id.rsplit(".", 1)[-1]
    return (
        _project_root(project_root)
        / "steps"
        / "crealityscan"
        / step_dir_name
        / "v1_0_0"
        / "presets.json"
    )


def _normalized_connections(raw: Any, key: str, name: str) -> tuple[str, ...]:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = [str(value) for value in raw]
    else:
        values = []
    normalized: list[str] = []
    for value in values:
        token = value.strip().lower().replace("_", "-")
        if token in {"usb"} and CONNECTION_USB not in normalized:
            normalized.append(CONNECTION_USB)
        if token in {"wifi", "wi-fi", "wlan"} and CONNECTION_WIFI not in normalized:
            normalized.append(CONNECTION_WIFI)
    if normalized:
        return tuple(normalized)

    haystack = f"{key} {name}".lower()
    if "wifi" in haystack or "wi-fi" in haystack:
        return (CONNECTION_WIFI,)
    if "usb" in haystack:
        return (CONNECTION_USB,)
    return ()


def _task_profile(raw: Any, key: str, name: str) -> str:
    profile = str(raw or "").strip().lower().replace("-", "_")
    if profile:
        return profile
    haystack = f"{key} {name}".lower()
    if "frame_points" in haystack or "框架点" in name:
        return "frame_points"
    return "standard"


def list_module_presets(
    module_name: str,
    *,
    project_root: Optional[Path] = None,
    connection_type: str = "",
) -> list[ScanPreset]:
    if module_name not in MODULE_PRESET_SOURCES:
        raise KeyError(f"未知模组：{module_name}")
    source = MODULE_PRESET_SOURCES[module_name]
    path = _preset_path(source, project_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValueError(f"无法读取 {source.display_name} preset：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source.display_name} preset JSON 格式错误：{exc}") from exc

    entries = raw.get("presets") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"{source.display_name} preset 文件缺少 presets 列表：{path}")

    presets: list[ScanPreset] = []
    seen_keys: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        name = str(entry.get("name") or key).strip()
        if not key or not name or key in seen_keys:
            continue
        aliases_raw = entry.get("aliases") if isinstance(entry.get("aliases"), list) else []
        preset = ScanPreset(
            key=key,
            name=name,
            aliases=tuple(str(value).strip() for value in aliases_raw if str(value).strip()),
            task_profile=_task_profile(entry.get("task_profile"), key, name),
            connections=_normalized_connections(entry.get("connections"), key, name),
        )
        if source.module_name == "pika" and not preset.connections and key.startswith("pika.line_laser."):
            preset = ScanPreset(
                key=preset.key,
                name=preset.name,
                aliases=preset.aliases,
                task_profile=preset.task_profile,
                connections=(CONNECTION_USB,),
            )
        if connection_type and preset.connections and connection_type not in preset.connections:
            continue
        presets.append(preset)
        seen_keys.add(key)
    return presets


def _preset_haystack(preset: ScanPreset) -> str:
    return f"{preset.key} {preset.name} {' '.join(preset.aliases)}".lower()


def _fps_stat_key_has(preset: ScanPreset, *tokens: str) -> bool:
    key = preset.key.lower()
    return all(token in key for token in tokens)


def _fps_stat_preference_score(preset: ScanPreset) -> int:
    """同类 preset 的优先级：高精度 > 标准/默认 > 广角。"""
    haystack = _preset_haystack(preset)
    if "high_precision" in haystack or "高精度" in haystack:
        return 0
    if "wide_angle" in haystack or "广角" in haystack:
        return 2
    if "standard" in haystack or "标准" in haystack:
        return 1
    return 1


def _fps_stat_candidates(
    presets: Sequence[ScanPreset],
    predicate,
) -> list[ScanPreset]:
    return [preset for preset in presets if predicate(preset)]


def fps_stat_mode_plan(
    module_name: str,
    connection_type: str = "",
    *,
    project_root: Optional[Path] = None,
) -> list[tuple[str, str]]:
    """
    按业务规则挑选“帧率统计”任务要测试的模式，返回 [(业务短名, preset key), ...]。

    顺序固定为 平行线/单线/交叉/无标记点/大物体/中物体/小物体/人脸/人体，
    与 帧率统计模板.xlsx 的 G3/H3 行顺序一致；模组不存在的模式直接跳过（不占位）。
    - 无标记点仅存在于 USB 连接（connection_type=Wi-Fi 时被 list_module_presets 过滤掉）。
    - 大/中/小物体默认取“几何”，人脸/人体取“纹理”（优先高精度）。
    """
    if module_name not in MODULE_PRESET_SOURCES:
        raise KeyError(f"未知模组：{module_name}")
    source = MODULE_PRESET_SOURCES[module_name]
    presets = list_module_presets(
        module_name,
        project_root=project_root,
        connection_type=connection_type if source.supports_connection else "",
    )

    def line(tail: str) -> Any:
        return lambda p: _fps_stat_key_has(p, "line_laser", "point_cloud", tail)

    def speckle(size: str) -> Any:
        return lambda p: _fps_stat_key_has(p, size, "geometry") and "line_laser" not in p.key and "frame_points" not in p.key

    def textured(part: str) -> Any:
        return lambda p: _fps_stat_key_has(p, part, "texture") and "line_laser" not in p.key and "frame_points" not in p.key

    rules: list[tuple[str, Any]] = [
        ("平行线", line("parallel")),
        ("单线", line("single")),
        ("交叉", line("cross")),
        ("无标记点", lambda p: "no_marker" in p.key),
        ("大物体", speckle("large")),
        ("中物体", speckle("medium")),
        ("小物体", speckle("small")),
        ("人脸", textured("face")),
        ("人体", textured("body")),
    ]

    plan: list[tuple[str, str]] = []
    for short_name, predicate in rules:
        candidates = _fps_stat_candidates(presets, predicate)
        if not candidates:
            continue
        if short_name == "无标记点":
            exact = [p for p in candidates if p.key.rstrip(".").endswith("no_marker")]
            if exact:
                candidates = exact
        candidates.sort(key=lambda p: (_fps_stat_preference_score(p), p.key))
        plan.append((short_name, candidates[0].key))
    return plan


def fps_stat_preset_keys(
    module_name: str,
    connection_type: str = "",
    *,
    project_root: Optional[Path] = None,
) -> list[str]:
    return [key for _, key in fps_stat_mode_plan(module_name, connection_type, project_root=project_root)]


def list_task_generation_options() -> list[TaskGenerationOption]:
    options: list[TaskGenerationOption] = []
    for source in sorted(MODULE_PRESET_SOURCES.values(), key=lambda item: item.display_name.lower()):
        for task_kind in (TASK_KIND_OPEN_STREAM, TASK_KIND_POSTPROCESS, TASK_KIND_FPS_STAT):
            options.append(
                TaskGenerationOption(
                    module_name=source.module_name,
                    task_kind=task_kind,
                    label=f"{source.display_name} / {task_kind} / 动态 preset",
                )
            )
    return options


def ordered_presets(
    presets: Sequence[ScanPreset], *, randomize: bool = False, random_seed: Optional[int] = None
) -> list[ScanPreset]:
    result = list(presets)
    if randomize:
        random.Random(random_seed).shuffle(result)
    return result


def _step(step_id: str, name: str, params: Optional[dict[str, Any]] = None) -> CaseStep:
    return CaseStep(
        step_id=step_id,
        version="1.0.0",
        name=name,
        params=dict(params or {}),
        on_fail={"action": "abort"},
    )


def _sleep(seconds: float) -> CaseStep:
    return _step("common.sleep", f"等待{seconds:g}s", {"seconds": float(seconds)})


def _standard_scan_steps(
    target_frames: int,
    *,
    include_preview: bool = True,
    slide_rail: bool = False,
) -> list[CaseStep]:
    steps: list[CaseStep] = []
    if include_preview:
        steps.append(_step("crealityscan.preview_scan", "预览扫描"))
    steps.append(
        _step(
            "crealityscan.scan_until_frames_then_stop",
            f"扫描至{target_frames}帧后完成",
            {
                "target_frames": target_frames,
                "slide_rail_scan_motion_enabled": slide_rail,
            },
        )
    )
    return steps


def _frame_points_scan_steps(
    target_frames: int,
    *,
    include_initial_preview: bool = True,
    slide_rail: bool = False,
) -> list[CaseStep]:
    steps: list[CaseStep] = []
    if include_initial_preview:
        steps.append(_step("crealityscan.preview_scan", "预览扫描"))
    steps.extend(
        [
        _step(
            "crealityscan.scan_until_frames_reach_target_frame_points",
            "开始扫描等待5秒并暂停（框架点）",
            {"slide_rail_scan_motion_enabled": slide_rail},
        ),
        _step("crealityscan.pause_switch_point_cloud_scan", "切点云"),
        *_standard_scan_steps(target_frames, slide_rail=slide_rail),
        ]
    )
    return steps


def _should_texture(preset: ScanPreset) -> bool:
    haystack = f"{preset.key} {preset.name}".lower()
    if any(token in haystack for token in ("texture_off", "关闭贴图", "不贴图")):
        return False
    if any(token in haystack for token in ("texture_on", "开启贴图")):
        return True
    if any(token in haystack for token in ("no_marker", "无标记点", "无标志点")):
        return True
    if "line_laser" in haystack or "线激光" in preset.name:
        return False
    return True


def _postprocess_steps(preset: ScanPreset) -> list[CaseStep]:
    steps = [
        _step("crealityscan.fusion_operation", "进行融合操作"),
        _step("crealityscan.package_operation", "进行封装操作"),
    ]
    if _should_texture(preset):
        steps.append(_step("crealityscan.texture_operation", "进行贴图操作"))
    return steps


def _pika_config_params(preset: ScanPreset) -> dict[str, Any]:
    params: dict[str, Any] = {"preset": preset.key}
    if not preset.key.startswith("pika.wifi."):
        params.update({"delay_sec": 0.5, "mouse_safe_sleep_sec": 0.5})
    return params


_SLIDE_RAIL_SWITCH_STEP_ID = "slide_rail.switch_position"
_SLIDE_RAIL_POSITION_NAMES = {
    "small": "小物体",
    "medium": "中物体",
    "face": "人脸",
    "large": "大物体",
}


def _slide_rail_position_for_preset(preset: ScanPreset) -> str:
    haystack = f"{preset.key} {preset.name} { ' '.join(preset.aliases) }".lower()
    if "face" in haystack or "人脸" in haystack:
        return "face"
    if "body" in haystack or "人体" in haystack:
        return "large"
    if "line_laser" in haystack or "线激光" in haystack:
        return "medium"
    for size in ("small", "medium", "large"):
        if size in haystack or {"small": "小物体", "medium": "中物体", "large": "大物体"}[size] in haystack:
            return size
    return "medium"


def _slide_rail_switch_step(preset: ScanPreset) -> CaseStep:
    position = _slide_rail_position_for_preset(preset)
    position_name = _SLIDE_RAIL_POSITION_NAMES[position]
    return _step(
        _SLIDE_RAIL_SWITCH_STEP_ID,
        f"移动滑轨位置至{position_name}",
        {"preset": position_name},
    )


def _build_steps(
    source: ModulePresetSource,
    presets: Sequence[ScanPreset],
    task_kind: str,
    target_frames: int,
    *,
    slide_rail: bool = False,
) -> list[CaseStep]:
    steps: list[CaseStep] = []
    if source.include_activate_window:
        steps.append(_step("common.activate_window", "激活/置顶窗口"))
    if source.pika_waits:
        steps.append(_sleep(1))
    steps.append(_step("crealityscan.create_project", "新建项目"))
    if source.pika_waits:
        steps.append(_sleep(3))

    for index, preset in enumerate(presets):
        if index > 0:
            steps.append(_step("crealityscan.create_scan", "新建扫描"))
            if source.pika_waits:
                steps.append(_sleep(3))
        if slide_rail:
            steps.append(_slide_rail_switch_step(preset))
        params = _pika_config_params(preset) if source.pika_waits else {"preset": preset.key}
        steps.append(_step(source.configure_step_id, f"扫描参数：{preset.name}", params))
        if source.pika_waits:
            steps.append(_sleep(3))
        if preset.task_profile == "frame_points":
            steps.extend(
                _frame_points_scan_steps(
                    target_frames,
                    include_initial_preview=not source.pika_waits,
                    slide_rail=slide_rail,
                )
            )
        else:
            steps.extend(
                _standard_scan_steps(
                    target_frames,
                    include_preview=not source.pika_waits,
                    slide_rail=slide_rail,
                )
            )
        if task_kind == TASK_KIND_POSTPROCESS:
            steps.extend(_postprocess_steps(preset))
        if source.pika_waits:
            steps.append(_sleep(1))
    return steps


def build_task_model(
    module_name: str,
    task_kind: str,
    task_name: str,
    *,
    preset_keys: Optional[Iterable[str]] = None,
    target_frames: int = 200,
    connection_type: str = "",
    randomize: bool = False,
    random_seed: Optional[int] = None,
    project_root: Optional[Path] = None,
    app_log_dir: str = "",
    keywords: Optional[Iterable[str]] = None,
    app_window_title_contains: str = "CrealityScan",
    app_device_uri: str = "Windows:///",
    slide_rail: bool = False,
) -> CaseModel:
    if module_name not in MODULE_PRESET_SOURCES:
        raise KeyError(f"未知模组：{module_name}")
    if task_kind not in {TASK_KIND_OPEN_STREAM, TASK_KIND_POSTPROCESS, TASK_KIND_FPS_STAT}:
        raise KeyError(f"未知任务类型：{task_kind}")
    if isinstance(target_frames, bool) or not isinstance(target_frames, int) or not 1 <= target_frames <= 100000:
        raise ValueError("目标帧数必须是 1–100000 之间的整数")

    source = MODULE_PRESET_SOURCES[module_name]
    available = list_module_presets(
        module_name,
        project_root=project_root,
        connection_type=connection_type if source.supports_connection else "",
    )
    by_key = {preset.key: preset for preset in available}
    if preset_keys is None and task_kind == TASK_KIND_FPS_STAT:
        # 帧率统计任务按业务规则自动挑选模式并固定顺序。
        requested_keys = fps_stat_preset_keys(
            module_name,
            connection_type=connection_type if source.supports_connection else "",
            project_root=project_root,
        )
    else:
        requested_keys = list(preset_keys) if preset_keys is not None else [preset.key for preset in available]
    if not requested_keys:
        raise ValueError("至少选择一个扫描模式")
    missing = [key for key in requested_keys if key not in by_key]
    if missing:
        raise ValueError(f"preset 已不存在或不可用：{', '.join(missing)}")
    selected = [by_key[key] for key in requested_keys]
    if task_kind == TASK_KIND_FPS_STAT:
        # 帧率统计需要按固定业务顺序输出，禁止随机打乱。
        randomize = False
    selected = ordered_presets(selected, randomize=randomize, random_seed=random_seed)

    normalized_name = (task_name or f"{source.display_name}{task_kind}").strip()
    normalized_name = normalized_name or f"{source.display_name}{task_kind}"
    return CaseModel(
        case_id=normalized_name,
        name=normalized_name,
        app_window_title_contains=app_window_title_contains or "CrealityScan",
        app_log_dir=app_log_dir or "",
        app_device_uri=app_device_uri or "Windows:///",
        keywords=list(keywords or DEFAULT_KEYWORDS),
        task_kind=task_kind,
        connection_type=connection_type,
        steps=_build_steps(source, selected, task_kind, target_frames, slide_rail=slide_rail),
    )
