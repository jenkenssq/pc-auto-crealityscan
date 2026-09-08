from __future__ import annotations

import argparse
import importlib
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from .process_manager import ManagedCrealityScan


_AIRTEST_WINDOWS_READY = False
_INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*]+')
_POSTPROCESS_CONFIG = {
    "texture": {
        "name": "贴图",
        "step_name": "贴图操作",
        "module": "steps.tool.postprocess_compare.texture_operation.v1_0_0.impl",
        "default_timeout_sec": 90.0,
    },
    "gaussian": {
        "name": "高斯渲染",
        "step_name": "高斯渲染操作",
        "module": "steps.tool.postprocess_compare.gaussian_rendering.v1_0_0.impl",
        "default_timeout_sec": 900.0,
    },
    "ai_retexture": {
        "name": "AI重贴图",
        "step_name": "AI重贴图操作",
        "module": "steps.tool.postprocess_compare.ai_retexture_operation.v1_0_0.impl",
        "default_timeout_sec": 600.0,
    },
    "human_body_completion": {
        "name": "人体补全",
        "step_name": "人体补全操作",
        "module": "steps.tool.postprocess_compare.human_body_completion.v1_0_0.impl",
        "default_timeout_sec": 600.0,
    },
}


@dataclass(frozen=True)
class ProjectWorkItem:
    sequence: int
    source_project_dir: Path
    project_file_path: Path
    run_dir: Path


def _configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


class _Tee:
    """同时写入原输出流与日志文件的输出流。

    用于把 CLI 全部 print 输出原样复制到运行目录下的日志文件，
    这样即使 GUI 日志窗口只保留有限行，也能在文件里拿到完整过程。
    """

    def __init__(self, stream, file):
        self.stream = stream
        self.file = file

    def write(self, data: str) -> int:
        self.stream.write(data)
        self.file.write(data)
        self.file.flush()
        return len(data)

    def flush(self) -> None:
        self.stream.flush()
        self.file.flush()


def _install_run_log(path: Path) -> None:
    """把当前进程 stdout/stderr 复制到 path（追加），并打印本次运行起点。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a", encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"[COMPARE][WARN] 无法写入运行日志文件（{path}）：{exc}")
        return
    handle.write(f"\n===== 本次运行开始：{datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    handle.flush()
    sys.stdout = _Tee(sys.__stdout__, handle)
    sys.stderr = _Tee(sys.__stderr__, handle)
    print(f"[COMPARE][INFO] 运行日志已写入：{path}")


def _ts() -> str:
    """返回 [HH:MM:SS] 时间戳前缀，便于在日志里定位每个阶段耗时。"""
    return f"[{datetime.now():%H:%M:%S}]"


def _normalize_exe(value: str, label: str) -> Path:
    path = Path(value.strip().strip('"')).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{label} EXE 不存在：{path}")
    if path.suffix.casefold() != ".exe":
        raise ValueError(f"{label}路径不是 EXE 文件：{path}")
    return path


def _prompt_exe(label: str, supplied: Optional[str]) -> Path:
    value = supplied
    while not value:
        value = input(f"请输入{label} CrealityScan EXE 路径：").strip()
    return _normalize_exe(value, label)


def _prompt_version(label: str, supplied: Optional[str]) -> str:
    value = supplied
    while not value:
        value = input(f"请输入{label}软件版本标识：").strip()
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label}软件版本标识不能为空")
    return normalized


def _safe_path_component(value: str) -> str:
    safe = _INVALID_PATH_CHARS_RE.sub("_", value).strip(" .")
    if not safe:
        raise ValueError(f"无法生成有效目录名称：{value!r}")
    return safe


def _prompt_output_dir(supplied: Optional[str]) -> Path:
    value = supplied
    while not value:
        value = input("请输入对比结果根目录：").strip()
    path = Path(value.strip().strip('"')).expanduser().resolve()
    if path.exists() and not path.is_dir():
        raise ValueError(f"对比结果路径不是目录：{path}")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"无法创建对比结果根目录 {path}：{exc}") from exc
    return path


def _normalize_project_set(value: str) -> Path:
    path = Path(value.strip().strip('"')).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"工程集目录不存在：{path}")
    return path


def _prompt_project_set(supplied: Optional[str]) -> Path:
    value = supplied
    while not value:
        value = input("请输入原始工程集目录：").strip()
    return _normalize_project_set(value)


def _resolve_project_files(project_set_path: Path) -> list[Path]:
    candidates = []
    direct_project = project_set_path / "project.obp"
    if direct_project.is_file():
        candidates.append(direct_project.resolve())
    candidates.extend(
        sorted(
            (path.resolve() for path in project_set_path.glob("*/project.obp") if path.is_file()),
            key=lambda path: str(path).casefold(),
        )
    )

    if not candidates:
        raise ValueError(f"工程集内未找到 project.obp：{project_set_path}")
    return candidates


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _directory_stats(source_dir: Path) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    for path in source_dir.rglob("*"):
        if path.is_file():
            file_count += 1
            total_bytes += path.stat().st_size
    return file_count, total_bytes


def _prepare_working_copy(
    source_dir: Path,
    destination_dir: Path,
    max_retries: int = 2,
) -> None:
    if destination_dir.exists():
        raise RuntimeError(f"工作副本目录已存在，禁止覆盖：{destination_dir}")

    destination_dir.parent.mkdir(parents=True, exist_ok=True)
    file_count, total_bytes = _directory_stats(source_dir)
    free_bytes = shutil.disk_usage(destination_dir.parent).free
    if free_bytes < total_bytes:
        raise RuntimeError(
            f"磁盘空间不足：复制需要 {total_bytes} 字节，可用 {free_bytes} 字节，"
            f"目标={destination_dir.parent}"
        )

    print(f"[COMPARE] 正在创建工作副本：{source_dir} -> {destination_dir}")
    started = time.time()
    for attempt in range(1, max_retries + 2):
        try:
            shutil.copytree(source_dir, destination_dir)
            print(
                f"[COMPARE] 工作副本创建完成，文件数={file_count}，"
                f"大小={total_bytes}，耗时={time.time() - started:.3f}s，"
                f"目标={destination_dir}"
            )
            return
        except (OSError, shutil.Error) as exc:
            if destination_dir.exists():
                try:
                    shutil.rmtree(destination_dir)
                except OSError as cleanup_exc:
                    raise RuntimeError(
                        f"工作副本复制失败且无法清理不完整目录 {destination_dir}：{cleanup_exc}"
                    ) from cleanup_exc
            if attempt > max_retries:
                raise RuntimeError(
                    f"工作副本复制失败，已重试 {max_retries} 次，"
                    f"源={source_dir}，目标={destination_dir}：{exc}"
                ) from exc
            print(
                f"[COMPARE][WARN] 工作副本复制失败，准备重试 "
                f"attempt={attempt}/{max_retries + 1}：{exc}"
            )
            time.sleep(1.0)


def _ensure_airtest_windows() -> None:
    global _AIRTEST_WINDOWS_READY
    if _AIRTEST_WINDOWS_READY:
        return

    try:
        from airtest.core.api import connect_device  # type: ignore
        from airtest.core.error import (  # type: ignore
            AirtestError,
            DeviceConnectionError,
            NoDeviceError,
        )
    except ImportError as exc:
        raise RuntimeError("未安装 Airtest，无法执行导入工程 Step。") from exc

    try:
        connect_device("Windows:///")
    except (AirtestError, DeviceConnectionError, NoDeviceError, OSError, RuntimeError) as exc:
        raise RuntimeError(f"Airtest Windows 桌面连接失败：{exc}") from exc
    _AIRTEST_WINDOWS_READY = True


def _run_import_project_step(
    label: str,
    project_set_path: Path,
    project_file_path: Path,
    process_id: int,
) -> None:
    _ensure_airtest_windows()
    try:
        from airtest.core.error import AirtestError  # type: ignore
        from steps.tool.postprocess_compare.import_project.v1_0_0.impl import run as run_import_project
    except ImportError as exc:
        raise RuntimeError("无法加载导入工程 Step。") from exc

    print(f"[COMPARE] {label}开始执行导入工程 Step，工程文件={project_file_path}")
    try:
        result = run_import_project(
            {
                "step_index": 1,
                "version_label": label,
                "process_id": process_id,
                "project_set_path": str(project_set_path),
            },
            {
                "project_set_path": str(project_set_path),
                "project_file_path": str(project_file_path),
            },
        )
    except (AirtestError, OSError, RuntimeError) as exc:
        raise RuntimeError(f"{label}导入工程 Step 执行失败：{exc}") from exc
    print(
        f"[COMPARE] {label}导入工程 Step 已执行，"
        f"成功标识={result.get('success_marker') or ''}，"
        f"日志文件={result.get('success_log_file') or ''}，"
        f"耗时={float(result.get('import_elapsed_sec') or 0):.3f}s"
    )


def _run_postprocess_step(
    label: str,
    run_dir: Path,
    timeout_sec: float,
    operation: str,
    process_id: int,
    enable_gaussian: bool = False,
    run_texture_first: bool = True,
    texture_timeout_sec: float = 90.0,
    enable_hd_geometry: bool = False,
    base_wait_sec: float = 20.0,
    gaussian_quality: str = "高质量",
    skip_trip_model: bool = False,
    version_label: Optional[str] = None,
) -> None:
    config = _POSTPROCESS_CONFIG.get(operation)
    if config is None:
        raise RuntimeError(f"不支持的后处理类型：{operation}")
    try:
        from airtest.core.error import AirtestError  # type: ignore
        step_module = importlib.import_module(str(config["module"]))
    except ImportError as exc:
        raise RuntimeError(f"无法加载{config['step_name']} Step。") from exc

    print(f"[COMPARE] {label}开始执行{config['step_name']} Step")
    params: dict[str, object] = {"timeout_sec": timeout_sec, "enable_gaussian": enable_gaussian}
    if operation == "gaussian":
        params["gaussian_quality"] = gaussian_quality
    if operation == "ai_retexture":
        params["run_texture_first"] = run_texture_first
        params["texture_timeout_sec"] = texture_timeout_sec
    if operation == "human_body_completion":
        params["enable_hd_geometry"] = enable_hd_geometry
        params["base_wait_sec"] = base_wait_sec
        params["skip_trip_model"] = skip_trip_model
    try:
        result = step_module.run(
            {
                "step_index": 2,
                "version_label": version_label or label,
                "run_dir": str(run_dir),
                "process_id": process_id,
            },
            params,
        )
    except (AirtestError, OSError, RuntimeError) as exc:
        raise RuntimeError(f"{label}{config['step_name']} Step 执行失败：{exc}") from exc

    print(
        f"[COMPARE] {label}{config['step_name']} Step 已完成，"
        f"耗时={float(result.get('operation_elapsed_sec') or 0):.3f}s，"
        f"截图={result.get('snapshot') or ''}"
    )


def _run_return_home_step(label: str) -> None:
    try:
        from airtest.core.error import AirtestError  # type: ignore
        from steps.tool.postprocess_compare.return_home.v1_0_0.impl import run as run_return_home
    except ImportError as exc:
        raise RuntimeError("无法加载返回首页 Step。") from exc

    print(f"[COMPARE] {label}开始执行返回首页 Step")
    try:
        run_return_home(
            {
                "step_index": 3,
                "version_label": label,
            },
            {},
        )
    except (AirtestError, OSError, RuntimeError) as exc:
        raise RuntimeError(f"{label}返回首页 Step 执行失败：{exc}") from exc
    print(f"[COMPARE] {label}返回首页 Step 已执行")


def _run_one(
    label: str,
    exe_path: Path,
    project_set_path: Path,
    work_items: Sequence[ProjectWorkItem],
    postprocess_timeout_sec: float,
    operation: str,
    start_timeout_sec: float,
    close_timeout_sec: float,
    enable_gaussian: bool = False,
    run_texture_first: bool = True,
    texture_timeout_sec: float = 90.0,
    enable_hd_geometry: bool = False,
    base_wait_sec: float = 20.0,
    gaussian_quality: str = "高质量",
    skip_trip_model: bool = False,
) -> bool:
    app = ManagedCrealityScan(exe_path)
    try:
        print(f"\n{'=' * 60}")
        print(f"[COMPARE]{_ts()} 开始{label}阶段：启动 {exe_path}")
        print("=" * 60)
        phase_t0 = time.time()
        pid = app.start(timeout_sec=start_timeout_sec)
        print(
            f"[COMPARE]{_ts()} {label}已启动，PID={pid}，"
            f"启动耗时={time.time() - phase_t0:.1f}s"
        )
        for position, item in enumerate(work_items, start=1):
            step_label = f"{label}工程{item.sequence}"
            postprocess_name = str(_POSTPROCESS_CONFIG[operation]["step_name"])
            print(f"\n[COMPARE]{_ts()} —— {step_label}（阶段 {position}/{len(work_items)}）——")
            print(
                f"[COMPARE] 源工程={item.source_project_dir}，"
                f"工作副本={item.project_file_path.parent}"
            )
            t0 = time.time()
            _run_import_project_step(
                step_label,
                project_set_path,
                item.project_file_path,
                pid,
            )
            print(
                f"[COMPARE]{_ts()} {step_label}导入工程完成，耗时={time.time() - t0:.1f}s，"
                f"自动执行{postprocess_name}。"
            )
            t0 = time.time()
            _run_postprocess_step(
                step_label,
                item.run_dir,
                postprocess_timeout_sec,
                operation,
                pid,
                enable_gaussian,
                run_texture_first,
                texture_timeout_sec,
                enable_hd_geometry,
                base_wait_sec,
                gaussian_quality=gaussian_quality,
                skip_trip_model=skip_trip_model,
                version_label=label,
            )
            print(f"[COMPARE]{_ts()} {step_label}{postprocess_name}完成，耗时={time.time() - t0:.1f}s。")
            t0 = time.time()
            _run_return_home_step(step_label)
            print(f"[COMPARE]{_ts()} {step_label}返回首页完成，耗时={time.time() - t0:.1f}s。")
            if position < len(work_items):
                print(f"[COMPARE] 本阶段后续工程继续，自动导入下一个工程。")
            else:
                print(f"[COMPARE] 本阶段全部工程处理完毕，自动进入关闭流程。")
        close_result = app.close(timeout_sec=close_timeout_sec)
        close_mode = "强制结束" if close_result.forced else "正常关闭"
        confirm_mode = "已点击" if close_result.confirmation_clicked else "未点击"
        print(
            f"[COMPARE]{_ts()} {label}已关闭，方式={close_mode}，"
            f"关闭确认坐标={confirm_mode}，耗时={close_result.elapsed_sec:.3f}s"
        )
        return True
    except KeyboardInterrupt:
        print(f"\n[COMPARE]{_ts()} 用户中断，正在关闭{label}。")
        app.close(timeout_sec=close_timeout_sec)
        raise
    except (OSError, RuntimeError) as exc:
        print(f"[COMPARE][ERROR]{_ts()} {label}执行失败：{exc}")
        app.force_kill()
        return False


def _delete_download_packages(operation: str) -> None:
    """删除当前后处理操作对应的 CrealityScan 下载包。

    在发布版完成后、测试版开始前调用：删掉旧下载包后，测试版运行时才会触发
    重新下载新版本下载包，从而让发布版与测试版使用不同版本的下载包。
    """
    from .excel_report import iter_download_package_dirs

    dirs = iter_download_package_dirs(operation)
    if not dirs:
        print("[COMPARE][INFO] 当前后处理类型无独立下载包，跳过删除。")
        return
    for directory in dirs:
        if not directory.exists():
            print(f"[COMPARE][INFO] 下载包不存在，跳过：{directory}")
            continue
        try:
            shutil.rmtree(directory)
            print(f"[COMPARE][INFO] 已删除下载包：{directory}")
        except OSError as exc:
            print(f"[COMPARE][WARN] 删除下载包失败（{directory}）：{exc}")


def _launch_charles(exe_path: Path) -> None:
    """在发布版完成后、测试版启动前，独立拉起 Charles 抓包代理。

    以脱离 CLI 生命周期的方式启动（分离会话），不阻塞后续测试版流程；
    仅负责“启动”这个动作，Charles 自身是否完成监听由用户/抓包结果验证。
    """
    if not exe_path.is_file():
        raise RuntimeError(f"Charles.exe 不存在：{exe_path}")
    print(f"[COMPARE]{_ts()} 开始启动 Charles：{exe_path}")
    try:
        kwargs: dict = {
            "cwd": str(exe_path.parent),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            flags |= getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
            kwargs["creationflags"] = flags
        proc = subprocess.Popen([str(exe_path)], **kwargs)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"启动 Charles 失败（{exe_path}）：{exc}") from exc
    print(f"[COMPARE]{_ts()} Charles 已启动，PID={proc.pid}。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="顺序执行导入工程、后处理操作、返回首页 Step")
    parser.add_argument("--release-exe", help="发布版 CrealityScan.exe 路径")
    parser.add_argument("--release-version", help="发布版软件版本标识")
    parser.add_argument("--test-exe", help="测试版 CrealityScan.exe 路径")
    parser.add_argument("--test-version", help="测试版软件版本标识")
    parser.add_argument("--project-set", help="原始工程集目录")
    parser.add_argument("--output-dir", help="对比结果根目录")
    parser.add_argument(
        "--operation",
        "--postprocess",
        dest="operation",
        choices=tuple(_POSTPROCESS_CONFIG),
        default=None,
        help="后处理对比类型：texture=贴图，gaussian=高斯渲染，ai_retexture=AI重贴图，human_body_completion=人体补全",
    )
    parser.add_argument(
        "--operation-timeout",
        type=float,
        default=None,
        help="当前后处理操作的超时秒数；未指定时按类型使用默认值",
    )
    parser.add_argument(
        "--texture-timeout",
        type=float,
        default=90.0,
        help="贴图进度等待超时秒数（AI重贴图的前置贴图也使用该值）",
    )
    parser.add_argument("--gaussian-timeout", type=float, default=900.0, help="高斯渲染进度等待超时秒数")
    parser.add_argument(
        "--gaussian-quality",
        choices=("快速", "标准", "高质量"),
        default="高质量",
        help="高斯渲染质量等级：快速/标准/高质量，默认高质量",
    )
    parser.add_argument("--ai-retexture-timeout", type=float, default=600.0, help="AI重贴图操作等待超时秒数")
    parser.add_argument("--ai-retexture-gaussian", action="store_true", help="AI重贴图开启高斯渲染")
    parser.add_argument(
        "--human-body-completion-timeout",
        type=float,
        default=600.0,
        help="人体补全操作等待超时秒数（创建人体模型与AI人体补全两个进度条共用）",
    )
    parser.add_argument(
        "--human-body-hd-geometry",
        action="store_true",
        help="人体补全开启超清几何精度（点击坐标 320,465 开启开关）",
    )
    parser.add_argument(
        "--base-wait",
        type=float,
        default=20.0,
        help="人体补全选择模型底座后的固定等待秒数",
    )
    parser.add_argument(
        "--skip-trip-model",
        action="store_true",
        help="人体补全不生成trip，直接生成人体补全模型：点击AI人体补全后直接选择模型底座并预览/应用，跳过导入图片/立即生成/创建人体模型",
    )
    parser.add_argument(
        "--no-texture-first",
        action="store_true",
        help="AI重贴图前不先执行贴图操作（默认先执行贴图）",
    )
    parser.add_argument("--start-timeout", type=float, default=120.0, help="等待主窗口超时秒数")
    parser.add_argument("--close-timeout", type=float, default=20.0, help="正常关闭超时秒数")
    parser.add_argument(
        "--charles-exe",
        help="开启Charles时指定的 Charles.exe 路径；发布版完成后、测试版启动前自动启动抓包代理",
    )
    parser.add_argument(
        "--delete-download-package",
        action="store_true",
        help="发布版全部后处理完成后删除本次操作对应的下载包（触发测试版重新下载新包）",
    )
    parser.add_argument(
        "--test-only",
        action="store_true",
        help="只跑测试版：跳过发布版阶段与最终对比表，用于单独验证测试版（如自动下载）。",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    _configure_console_encoding()
    args = build_parser().parse_args(argv)
    if not args.operation:
        print("[COMPARE][ERROR] 必须选择后处理对比类型：贴图或高斯渲染。")
        return 2
    try:
        if args.test_only:
            release_exe: Optional[Path] = None
            release_version = ""
            test_exe = _prompt_exe("测试版", args.test_exe)
            test_version = _prompt_version("测试版", args.test_version)
        else:
            release_exe = _prompt_exe("发布版", args.release_exe)
            release_version = _prompt_version("发布版", args.release_version)
            test_exe = _prompt_exe("测试版", args.test_exe)
            test_version = _prompt_version("测试版", args.test_version)
        project_set_path = _prompt_project_set(args.project_set)
        project_files = _resolve_project_files(project_set_path)
        output_dir = _prompt_output_dir(args.output_dir)
    except (EOFError, ValueError) as exc:
        print(f"[COMPARE][ERROR] 输入无效：{exc}")
        return 2

    if not args.test_only and release_exe == test_exe:
        print("[COMPARE][ERROR] 发布版和测试版不能使用同一个 EXE 路径。")
        return 2

    if _is_relative_to(output_dir, project_set_path):
        print("[COMPARE][ERROR] 对比结果根目录不能位于原始工程集内部。")
        return 2

    run_root = output_dir / f"compare_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    # 尽早落盘完整运行日志：即使 GUI 窗口只保留有限行，也能从文件拿到全程输出。
    try:
        run_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[COMPARE][WARN] 无法创建输出目录（{run_root}）：{exc}")
    _install_run_log(run_root / "运行日志.txt")
    operation_config = _POSTPROCESS_CONFIG[args.operation]
    if args.operation_timeout is not None:
        operation_timeout_sec = max(1.0, args.operation_timeout)
    elif args.operation == "gaussian":
        operation_timeout_sec = max(1.0, args.gaussian_timeout)
    elif args.operation == "ai_retexture":
        operation_timeout_sec = max(1.0, args.ai_retexture_timeout)
    elif args.operation == "human_body_completion":
        operation_timeout_sec = max(1.0, args.human_body_completion_timeout)
    else:
        operation_timeout_sec = max(1.0, args.texture_timeout)
    release_work_items: list[ProjectWorkItem] = []
    test_work_items: list[ProjectWorkItem] = []
    try:
        source_total_bytes = sum(
            _directory_stats(project_file.parent)[1] for project_file in project_files
        )
        required_bytes = source_total_bytes * 2
        free_bytes = shutil.disk_usage(output_dir).free
        if free_bytes < required_bytes:
            raise RuntimeError(
                f"磁盘空间不足：创建两份工作副本需要 {required_bytes} 字节，"
                f"可用 {free_bytes} 字节，目标={output_dir}"
            )
        release_result_name = _safe_path_component(f"{release_version}_{operation_config['name']}")
        test_result_name = _safe_path_component(f"{test_version}_{operation_config['name']}")
        for sequence, source_project_file in enumerate(project_files, start=1):
            source_project_dir = source_project_file.parent
            project_result_prefix = _safe_path_component(f"工程{sequence}")
            release_side_dir = run_root / "release"
            test_side_dir = run_root / "test"
            release_copy_dir = release_side_dir / _safe_path_component(
                f"{project_result_prefix}_{release_result_name}"
            )
            test_copy_dir = test_side_dir / _safe_path_component(
                f"{project_result_prefix}_{test_result_name}"
            )

            _prepare_working_copy(source_project_dir, release_copy_dir)
            _prepare_working_copy(source_project_dir, test_copy_dir)
            release_work_items.append(
                ProjectWorkItem(
                    sequence=sequence,
                    source_project_dir=source_project_dir,
                    project_file_path=release_copy_dir / "project.obp",
                    run_dir=release_copy_dir / "artifacts",
                )
            )
            test_work_items.append(
                ProjectWorkItem(
                    sequence=sequence,
                    source_project_dir=source_project_dir,
                    project_file_path=test_copy_dir / "project.obp",
                    run_dir=test_copy_dir / "artifacts",
                )
            )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[COMPARE][ERROR] 工作副本准备失败：{exc}")
        return 2

    print(f"\n[COMPARE] 原始工程集：{project_set_path}")
    print(f"[COMPARE] 工程数量：{len(project_files)}")
    for item in release_work_items:
        test_item = test_work_items[item.sequence - 1]
        print(
            f"[COMPARE] 工程映射 {item.sequence}：源={item.source_project_dir}，"
            f"发布版副本={item.project_file_path.parent}，"
            f"测试版副本={test_item.project_file_path.parent}"
        )
    print(f"[COMPARE] 本次输出目录：{run_root}")
    print(f"[COMPARE] 后处理类型：{operation_config['name']}，超时={operation_timeout_sec:.1f}s")
    if args.test_only:
        print("[COMPARE] 测试版单跑模式（--test-only）：跳过发布版阶段与对比表。")
    else:
        print("[COMPARE] 将按“发布版 -> 测试版”顺序运行，两个版本不会同时打开。")
    try:
        release_ok = False
        test_ok = False
        if args.test_only:
            test_ok = _run_one(
                "测试版",
                test_exe,
                project_set_path,
                test_work_items,
                postprocess_timeout_sec=operation_timeout_sec,
                operation=args.operation,
                start_timeout_sec=max(1.0, args.start_timeout),
                close_timeout_sec=max(1.0, args.close_timeout),
                enable_gaussian=args.ai_retexture_gaussian,
                run_texture_first=not args.no_texture_first,
                texture_timeout_sec=max(1.0, args.texture_timeout),
                enable_hd_geometry=args.human_body_hd_geometry,
                base_wait_sec=max(0.0, args.base_wait),
                skip_trip_model=args.skip_trip_model,
                gaussian_quality=args.gaussian_quality,
            )
        else:
            release_ok = _run_one(
                "发布版",
                release_exe,
                project_set_path,
                release_work_items,
                postprocess_timeout_sec=operation_timeout_sec,
                operation=args.operation,
                start_timeout_sec=max(1.0, args.start_timeout),
                close_timeout_sec=max(1.0, args.close_timeout),
                enable_gaussian=args.ai_retexture_gaussian,
                run_texture_first=not args.no_texture_first,
                texture_timeout_sec=max(1.0, args.texture_timeout),
                enable_hd_geometry=args.human_body_hd_geometry,
                base_wait_sec=max(0.0, args.base_wait),
                skip_trip_model=args.skip_trip_model,
                gaussian_quality=args.gaussian_quality,
            )
            if release_ok and args.delete_download_package:
                print("\n[COMPARE] 发布版已完成后处理，删除下载包以触发测试版重新下载新包。")
                _delete_download_packages(args.operation)
            if release_ok and args.charles_exe:
                print("\n[COMPARE] 发布版已关闭，将在启动测试版之前启动 Charles 抓包代理。")
                try:
                    _launch_charles(Path(args.charles_exe).expanduser().resolve())
                except (OSError, RuntimeError) as exc:
                    print(f"[COMPARE][ERROR]{_ts()} {exc}")
                    print("[COMPARE][ERROR] 未启动 Charles，本次不再启动测试版，任务判定失败。")
                    release_ok = False
            if release_ok:
                test_ok = _run_one(
                    "测试版",
                    test_exe,
                    project_set_path,
                    test_work_items,
                    postprocess_timeout_sec=operation_timeout_sec,
                    operation=args.operation,
                    start_timeout_sec=max(1.0, args.start_timeout),
                    close_timeout_sec=max(1.0, args.close_timeout),
                    enable_gaussian=args.ai_retexture_gaussian,
                    run_texture_first=not args.no_texture_first,
                    texture_timeout_sec=max(1.0, args.texture_timeout),
                    enable_hd_geometry=args.human_body_hd_geometry,
                    base_wait_sec=max(0.0, args.base_wait),
                    skip_trip_model=args.skip_trip_model,
                    gaussian_quality=args.gaussian_quality,
                )
    except KeyboardInterrupt:
        return 3

    if args.test_only:
        if test_ok:
            print(
                f"\n[COMPARE] 测试版单跑完成：{operation_config['name']}、返回首页和关闭流程。"
            )
            return 0
        print("\n[COMPARE] 测试版单跑失败。")
        return 1

    if release_ok and test_ok:
        print(
            f"\n[COMPARE] 两个版本均已完成导入、{operation_config['name']}、返回首页和关闭流程。"
        )
        try:
            from .excel_report import ReportProject, generate_excel_report

            if len(release_work_items) != len(test_work_items):
                raise ValueError("发布版和测试版工程数量不一致，无法生成对比表。")
            report_projects = []
            for release_item, test_item in zip(release_work_items, test_work_items):
                if (
                    release_item.sequence != test_item.sequence
                    or release_item.source_project_dir != test_item.source_project_dir
                ):
                    raise ValueError(
                        f"工程 {release_item.sequence} 的发布版与测试版来源不一致。"
                    )
                report_projects.append(
                    ReportProject(
                        sequence=release_item.sequence,
                        source_project_dir=release_item.source_project_dir,
                        release_run_dir=release_item.run_dir,
                        test_run_dir=test_item.run_dir,
                    )
                )
            report_path = generate_excel_report(
                run_root=run_root,
                operation=args.operation,
                operation_name=str(operation_config["name"]),
                release_version=release_version,
                test_version=test_version,
                projects=report_projects,
            )
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            print(f"[COMPARE][ERROR] Excel 对比表生成失败：{exc}")
            return 1
        print(f"[COMPARE] Excel对比表：{report_path}")
        return 0
    print("\n[COMPARE] 至少一个版本启动或关闭失败。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
