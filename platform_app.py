# -*- coding: utf-8 -*-
import sys
from pathlib import Path


def _run_postprocess_compare(argv: list[str]) -> int:
    """打包态下在平台 exe 进程内运行后处理对比 CLI。

    收编后 postprocess_compare 是 jens_platform.tools 包的一部分，随平台
    一起收集（源码态直接可导入）；CLI 不依赖 __file__，模板由步骤实现按
    steps/ 相对路径解析，因此可直接 import 而非 spec_from_file_location。
    """
    from jens_platform.tools.postprocess_compare.cli import main

    return int(main(argv))


def _run_slide_rail_script(script_name: str, *, as_main: bool = False) -> int:
    """打包态下在平台 exe 进程内运行 滑轨/ 目录下的脚本。

    从 exe 同级的 滑轨 目录用 runpy.run_path 执行，保持 __file__ 指向
    滑轨 目录（zmotion_controller 用 __file__ 回退定位 DLL）。
    as_main=True 时以 __main__ 语义执行（motion_service 与 slide_rail_ui
    的入口都写在 __main__ 块里）。
    """
    import runpy

    if getattr(sys, "frozen", False):
        slide_rail_dir = Path(sys.executable).resolve().parent / "滑轨"
    else:
        slide_rail_dir = Path(__file__).resolve().parent / "滑轨"
    if str(slide_rail_dir) not in sys.path:
        sys.path.insert(0, str(slide_rail_dir))
    script_path = slide_rail_dir / f"{script_name}.py"
    if not script_path.is_file():
        print(f"[SLIDE_RAIL][ERROR] 未找到脚本：{script_path}")
        return 2
    # runpy.run_path 直接编译脚本并以指定 run_name 执行，绕开 SourceFileLoader
    # 的 _check_name 名称校验：打包态下把模块改名 __main__ 再 exec_module，
    # 会触发 "loader for motion_service cannot handle _main"。
    runpy.run_path(str(script_path), run_name="__main__" if as_main else script_name)
    return 0


def _run_slide_rail_service() -> int:
    """滑轨运动服务：纯标准库 socket 服务，阻塞持有 5000/5001 端口。"""
    return _run_slide_rail_script("motion_service", as_main=True)


def _run_slide_rail_ui() -> int:
    """滑轨控制台：独立 QApplication，须在独立子进程中运行。"""
    return _run_slide_rail_script("slide_rail_ui", as_main=True)


def _main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--firmware-tool-runner":
        from jens_platform.firmware_tool_runner import main as run_firmware_tool

        return int(run_firmware_tool(sys.argv[2:]))

    if len(sys.argv) >= 2 and sys.argv[1] == "--postprocess-compare-runner":
        return _run_postprocess_compare(sys.argv[2:])

    if len(sys.argv) >= 2 and sys.argv[1] == "--slide-rail-service-runner":
        return _run_slide_rail_service()

    if len(sys.argv) >= 2 and sys.argv[1] == "--slide-rail-ui-runner":
        return _run_slide_rail_ui()

    if len(sys.argv) >= 3 and sys.argv[1] == "--run-case":
        from jens_runner_entry import run_case

        return int(run_case(sys.argv[2]))

    try:
        # 优先使用 PyQt5（你机器上已安装），避免 PyQt5/PySide2 混装导致 Qt 插件/DLL 冲突。
        from PyQt5.QtCore import QLibraryInfo  # type: ignore
    except Exception:
        print("未检测到 PyQt5。请先安装 UI 依赖：")
        print("  python -m pip install -r requirements-ui.txt")
        return 2

    # 显式指定 Qt 插件与 DLL 搜索路径，解决常见的
    # “Could not load the Qt platform plugin 'windows'” 问题。
    try:
        import os

        plugins_dir = QLibraryInfo.location(QLibraryInfo.PluginsPath)
        bin_dir = QLibraryInfo.location(QLibraryInfo.BinariesPath)
        if bin_dir:
            os.add_dll_directory(bin_dir)
        if plugins_dir:
            os.environ.setdefault("QT_PLUGIN_PATH", plugins_dir)
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", os.path.join(plugins_dir, "platforms"))
    except Exception:
        # 兜底：不因设置失败而阻断启动
        pass

    from jens_platform.main import main

    main()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
