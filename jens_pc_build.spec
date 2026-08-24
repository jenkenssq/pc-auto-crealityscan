# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)


project_root = Path.cwd()
icon_path = project_root / "build_assets" / "jens_app.ico"


def _vs_version(exe_name: str):
    ver = os.environ.get("JENS_BUILD_VERSION", "0.1")
    parts = [int(x) for x in ver.split(".")]
    while len(parts) < 4:
        parts.append(0)
    major, minor, build, revision = parts[:4]
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=(major, minor, build, revision),
            prodvers=(major, minor, build, revision),
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "080404b0",
                        [
                            StringStruct("CompanyName", "Jens"),
                            StringStruct("FileDescription", "Jens 扫描软件自动化测试平台"),
                            StringStruct("FileVersion", ver),
                            StringStruct("InternalName", exe_name.rsplit(".", 1)[0]),
                            StringStruct("OriginalFilename", exe_name),
                            StringStruct("ProductName", "Jens"),
                            StringStruct("ProductVersion", ver),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [0x0804, 1200])]),
        ],
    )


def unique_pairs(pairs):
    seen = set()
    out = []
    for a, b in pairs:
        key = (str(a), str(b))
        if key in seen:
            continue
        seen.add(key)
        out.append((a, b))
    return out


airtest_datas, airtest_binaries, airtest_hiddenimports = collect_all("airtest")
poco_datas, poco_binaries, poco_hiddenimports = collect_all("poco")
rapidocr_datas, rapidocr_binaries, rapidocr_hiddenimports = collect_all("rapidocr_onnxruntime")
# onnxruntime 的 PyInstaller hook 会收集推理所需 DLL。不要 collect_all，
# 否则会把量化、Transformer、onnx.reference 等开发工具一起递归导入，
# 既显著放大安装包，也可能在分析阶段触发原生扩展崩溃。
onnxruntime_datas, onnxruntime_binaries, onnxruntime_hiddenimports = [], [], []
mss_datas, mss_binaries, mss_hiddenimports = collect_all("mss")
engine_hiddenimports = collect_submodules("engine")

extra_datas = [
    (str(project_root / ".env"), "."),
    (str(project_root / "README.md"), "."),
    (str(project_root / "build_assets" / "jens_app.ico"), "build_assets"),
    (str(project_root / "steps"), "steps"),
    (str(project_root / "cases"), "cases"),
    (str(project_root / "tasks"), "tasks"),
    (str(project_root / "docs"), "docs"),
    (str(project_root / "jens_runner.air"), "jens_runner.air"),
]

if (project_root / "config").exists():
    extra_datas.append((str(project_root / "config"), "config"))

all_datas = unique_pairs(
    list(airtest_datas)
    + list(poco_datas)
    + list(rapidocr_datas)
    + list(onnxruntime_datas)
    + list(mss_datas)
    + extra_datas
)

# 后处理对比 CLI 的第三方依赖（airtest/psutil/PIL 已由平台打包）。
try:
    tool_hiddenimports = (
        collect_submodules("pywinauto")
        + collect_submodules("openpyxl")
        + ["et_xmlfile"]
    )
except Exception:
    tool_hiddenimports = []
all_binaries = unique_pairs(
    list(airtest_binaries)
    + list(poco_binaries)
    + list(rapidocr_binaries)
    + list(onnxruntime_binaries)
    + list(mss_binaries)
)
all_hiddenimports = sorted(
    set(
        list(airtest_hiddenimports)
        + list(poco_hiddenimports)
        + list(rapidocr_hiddenimports)
        + list(onnxruntime_hiddenimports)
        + list(mss_hiddenimports)
        + list(engine_hiddenimports)
        + list(tool_hiddenimports)
    )
)


a_gui = Analysis(
    ["platform_app.py"],
    pathex=[str(project_root)],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz_gui = PYZ(a_gui.pure)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="jens_pc_app",
    version=_vs_version("jens_pc_app.exe"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon_path),
)


a_runner = Analysis(
    ["jens_runner_helper.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz_runner = PYZ(a_runner.pure)

exe_runner = EXE(
    pyz_runner,
    a_runner.scripts,
    [],
    exclude_binaries=True,
    name="jens_runner_helper",
    version=_vs_version("jens_runner_helper.exe"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)


coll = COLLECT(
    exe_gui,
    exe_runner,
    a_gui.binaries,
    a_gui.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="jens_pc_app",
)
