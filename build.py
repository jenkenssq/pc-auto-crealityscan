#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jens 平台打包脚本：构建 exe（版本由调用方显式指定）。

用法：
    python build.py 1.10       # 显式指定版本（不再自动进位）
    python build.py 1.9 --notes "修复..."   # 附带本版本更新说明

约定：版本号不自动递增。次版本按 1.9 -> 1.10 -> 1.11 递增（可超过 9），
是否进位大版本由用户决定，调用时必须显式给出版本号。

产物：dist/jens_pc_app_vX.Y/，版本同时写入 exe 文件版本资源；
并在产物目录生成 更新说明.txt（内容取自根目录 更新说明.md 的
对应版本段落，或 --notes 内联文本）。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION_RE = re.compile(r"^jens_pc_app_v(\d+)\.(\d+)$")

TOOL_SOURCE = ROOT / "工具"
TOOL_NAMES = ("后处理对比工具", "标定分数查看工具", "固件升级工具")
# 附带工具时排除：构建产物、缓存、样本数据、隐藏配置
TOOL_EXCLUDE_DIRS = {
    "__pycache__", ".git", ".claude", ".serena", ".impeccable",
    ".idea", ".vscode", "build", "dist", "工程集", "结果工程集",
}

SLIDE_RAIL_SOURCE = ROOT / "滑轨"
# 附带滑轨时排除：厂商演示软件、运行日志、缓存
SLIDE_RAIL_EXCLUDE_DIRS = {
    "__pycache__", "2米滑轨控制软件", "position_logs",
}

# 根目录更新说明文件：打包时提取本版本段落生成产物内的 更新说明.txt。
NOTES_DEFAULT_FILE = "更新说明.md"


def _copy_tool_ignore(dirname: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if (Path(dirname) / name).is_dir():
            if name in TOOL_EXCLUDE_DIRS:
                ignored.add(name)
        elif name.endswith((".pyc", ".pyo")):
            ignored.add(name)
    return ignored


def _copy_tools(dst: Path) -> None:
    """把侧边栏工具目录附带进产物，供 _resolve_tool_root 从 exe 目录直接命中。"""
    if not TOOL_SOURCE.is_dir():
        print(f"[BUILD] 未找到 {TOOL_SOURCE}，跳过附带工具")
        return
    tool_dst = dst / "工具"
    tool_dst.mkdir(parents=True, exist_ok=True)
    for name in TOOL_NAMES:
        src = TOOL_SOURCE / name
        if not src.is_dir():
            print(f"[BUILD] 工具缺失: {src}")
            continue
        target = tool_dst / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target, ignore=_copy_tool_ignore)
        size_mb = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) / 1e6
        print(f"[BUILD] 附带工具 {name}: {size_mb:.1f} MB")
    print(f"[BUILD] 工具已附带 -> {tool_dst}")


def _copy_slide_rail_ignore(dirname: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if (Path(dirname) / name).is_dir():
            if name in SLIDE_RAIL_EXCLUDE_DIRS:
                ignored.add(name)
        elif name.endswith((".pyc", ".pyo")):
            ignored.add(name)
    return ignored


def _copy_slide_rail(dst: Path) -> None:
    """附带滑轨运动控制（UI + 服务 + 驱动 DLL）到两处。

    main.py / slide_rail_app.py 从 exe 同级找 滑轨/，步骤 impl 从
    _internal/滑轨 找，两处都要复制才能保证运行时命中。
    """
    if not SLIDE_RAIL_SOURCE.is_dir():
        print(f"[BUILD] 未找到 {SLIDE_RAIL_SOURCE}，跳过附带滑轨")
        return
    for name in ("滑轨",):
        target = dst / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(SLIDE_RAIL_SOURCE, target, ignore=_copy_slide_rail_ignore)
        size_mb = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) / 1e6
        print(f"[BUILD] 附带滑轨 {target.relative_to(dst)}: {size_mb:.1f} MB")
    internal_slide_rail = dst / "_internal" / "滑轨"
    if internal_slide_rail.exists():
        shutil.rmtree(internal_slide_rail)
    shutil.copytree(SLIDE_RAIL_SOURCE, internal_slide_rail, ignore=_copy_slide_rail_ignore)
    size_mb = sum(f.stat().st_size for f in internal_slide_rail.rglob("*") if f.is_file()) / 1e6
    print(f"[BUILD] 附带滑轨 _internal/滑轨: {size_mb:.1f} MB")

    app_src = ROOT / "slide_rail_app.py"
    if app_src.is_file():
        shutil.copy2(app_src, dst / "slide_rail_app.py")
        print("[BUILD] 附带滑轨控制台 -> slide_rail_app.py")


def _extract_version_section(text: str, ver: str) -> str | None:
    """从更新说明文本中提取目标版本段落（形如 "## v1.2" 的标题，到下一标题为止）。"""
    version_heading = re.compile(
        rf"^#{{1,6}}\s*\[?(?:版本\s*)?v?{re.escape(ver)}(?![0-9])[^\n]*$",
        re.MULTILINE,
    )
    match = version_heading.search(text)
    if match is None:
        return None
    start = match.start()
    rest = text[match.end():]
    next_heading = re.compile(r"^#{1,6}\s", re.MULTILINE).search(rest)
    end = match.end() + (next_heading.start() if next_heading else len(rest))
    return text[start:end].strip()


def _write_update_notes(dst: Path, ver: str, notes_file: Path | None, inline_notes: str | None) -> None:
    """把本版本更新说明写入产物目录下的 更新说明.txt。"""
    if inline_notes:
        body = inline_notes.strip()
    elif notes_file is not None:
        text = notes_file.read_text(encoding="utf-8")
        section = _extract_version_section(text, ver)
        body = section if section is not None else text.strip()
    else:
        body = ""
    if not body:
        body = "（本次构建未提供更新说明，请补充后随产物分发。）"
    header = (
        f"Jens 扫描软件自动化测试平台 v{ver} 更新说明\n"
        + "=" * 40
        + f"\n构建日期：{datetime.now():%Y-%m-%d %H:%M}\n"
        + f"版本：{ver}\n\n"
    )
    target = dst / "更新说明.txt"
    target.write_text(header + body + "\n", encoding="utf-8")
    print(f"[BUILD] 已生成更新说明 -> {target}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Jens 平台打包脚本（版本必须显式指定，不自动递增）")
    ap.add_argument(
        "version",
        nargs="?",
        help="显式指定版本，如 1.10（必填；次版本可超过 9，进位大版本由用户决定）",
    )
    ap.add_argument(
        "--no-tools",
        action="store_true",
        help="构建后不附带侧边栏工具（默认附带 工具/ 三个工具）",
    )
    ap.add_argument(
        "--notes",
        help="本版本更新说明文本（优先于 --notes-file 和默认 更新说明.md）",
    )
    ap.add_argument(
        "--notes-file",
        help="更新说明源文件（默认读取根目录 更新说明.md 中本版本段落）",
    )
    args = ap.parse_args(argv)

    if args.version:
        parts = args.version.split(".")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            print(f"[BUILD] 版本格式错误: {args.version!r}，应为 X.Y（如 1.10）")
            return 2
        major, minor = int(parts[0]), int(parts[1])
    else:
        existing = sorted(
            (m.group(1), m.group(2))
            for d in (ROOT / "dist").glob("jens_pc_app_v*")
            if (m := VERSION_RE.match(d.name))
        )
        shown = "、".join(f"v{maj}.{min}" for maj, min in existing) or "（无）"
        print(
            "[BUILD] 版本必须显式指定（不再自动进位）：python build.py X.Y，例如 1.10"
        )
        print(f"[BUILD] dist 下现有版本：{shown}")
        return 2
    ver = f"{major}.{minor}"

    env = os.environ.copy()
    env["JENS_BUILD_VERSION"] = ver

    print(f"[BUILD] 目标版本 v{ver}")
    print(f"[BUILD] 执行 PyInstaller ...")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "jens_pc_build.spec"],
        cwd=str(ROOT),
        env=env,
        check=True,
    )

    src = ROOT / "dist" / "jens_pc_app"
    dst = ROOT / "dist" / f"jens_pc_app_v{ver}"
    if not src.exists():
        print(f"[BUILD] 未找到构建产物 {src}，构建可能失败")
        return 1
    if dst.exists():
        print(f"[BUILD] 目标目录已存在，拒绝覆盖: {dst}")
        return 1
    src.rename(dst)
    print(f"[BUILD] 完成 -> {dst}")
    if not args.no_tools:
        _copy_tools(dst)
    _copy_slide_rail(dst)
    default_notes = ROOT / NOTES_DEFAULT_FILE
    notes_file = (
        Path(args.notes_file).expanduser()
        if args.notes_file
        else (default_notes if default_notes.is_file() else None)
    )
    _write_update_notes(dst, ver, notes_file, args.notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
