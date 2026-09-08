# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _safe_name(name: str) -> str:
    text = (name or "").strip()
    return text or "merged_task"


def _load_task_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"任务文件顶层必须是对象: {path}")
    return raw


def _get_file_sort_key(file_path: Path, sort_by: str = "name") -> Any:
    """
    获取文件排序的键值
    
    Args:
        file_path: 文件路径
        sort_by: 排序依据
            - "name": 按文件名（字母顺序）
            - "ctime": 按创建时间（通常最接近上传顺序）
            - "mtime": 按修改时间
            - "birthtime": 按文件创建时间（macOS/Linux 支持）
    """
    if sort_by == "ctime":
        # Windows: 创建时间, Unix: 元数据更改时间（最接近文件创建时间）
        return file_path.stat().st_ctime
    elif sort_by == "mtime":
        return file_path.stat().st_mtime
    elif sort_by == "birthtime":
        # 仅在某些系统上可用（如 macOS）
        try:
            return file_path.stat().st_birthtime
        except AttributeError:
            # 如果不支持，回退到创建时间
            return file_path.stat().st_ctime
    else:
        # 默认按文件名
        return file_path.name


def merge_task_folder(folder: Path, output_name: str | None = None, 
                      sort_by: str = "ctime") -> tuple[Path, list[str]]:
    folder = folder.resolve()
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"任务目录不存在: {folder}")

    # 获取所有 JSON 文件
    task_files = [p for p in folder.glob("*.json") if p.is_file()]
    
    if not task_files:
        raise FileNotFoundError(f"目录下没有可合并的任务 JSON: {folder}")
    
    # 按照指定的排序方式进行排序
    # 使用稳定的排序，如果时间相同则按文件名排序保持一致性
    task_files.sort(key=lambda p: (p.name,))  # 先按文件名作为次级排序
    task_files.sort(key=lambda p: _get_file_sort_key(p, sort_by))
    
    # 可选：打印排序结果用于调试
    # print("文件排序结果:")
    # for i, f in enumerate(task_files, 1):
    #     print(f"  {i}. {f.name}")

    raws = [_load_task_json(path) for path in task_files]
    merged_name = _safe_name(output_name or folder.name)

    first = raws[0]
    merged_steps: list[dict[str, Any]] = []
    warnings: list[str] = []

    first_app = first.get("app") if isinstance(first.get("app"), dict) else {}
    first_keywords = first.get("keywords") if isinstance(first.get("keywords"), list) else []

    for path, raw in zip(task_files, raws):
        app = raw.get("app") if isinstance(raw.get("app"), dict) else {}
        keywords = raw.get("keywords") if isinstance(raw.get("keywords"), list) else []
        if app != first_app:
            warnings.append(f"app 配置与首个任务不一致，已沿用首个任务: {path.name}")
        if keywords != first_keywords:
            warnings.append(f"keywords 与首个任务不一致，已沿用首个任务: {path.name}")

        steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
        if not steps:
            warnings.append(f"steps 为空，已跳过: {path.name}")
            continue
        for step in steps:
            if isinstance(step, dict):
                merged_steps.append(step)

    if not merged_steps:
        raise ValueError(f"目录中没有可写入的步骤: {folder}")

    merged = {
        "case_id": merged_name,
        "name": merged_name,
        "app": first_app,
        "keywords": first_keywords,
        "steps": merged_steps,
    }

    output_path = folder.parent / f"{merged_name}.json"
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path, warnings


def _pick_folder() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(title="选择要合并的任务目录")
    root.destroy()
    return Path(selected) if selected else None


def _show_message(title: str, message: str, is_error: bool = False) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        print(message)
        return

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    if is_error:
        messagebox.showerror(title, message)
    else:
        messagebox.showinfo(title, message)
    root.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="选择任务目录并按上传顺序（创建时间）合并为一个总任务 JSON。",
        epilog="排序方式说明:\n"
               "  ctime    - 按创建时间排序（默认，最接近上传顺序）\n"
               "  mtime    - 按修改时间排序\n"
               "  name     - 按文件名排序\n"
               "  birthtime- 按文件创建时间（仅部分系统支持）"
    )
    parser.add_argument("folder", nargs="?", help="要合并的任务目录路径；不传则弹窗选择。")
    parser.add_argument("--name", dest="output_name", help="输出任务名；默认使用目录名。")
    parser.add_argument("--sort", dest="sort_by", 
                        choices=["ctime", "mtime", "name", "birthtime"],
                        default="ctime", 
                        help="排序方式：ctime(创建时间，默认), mtime(修改时间), name(文件名), birthtime(创建时间)")
    parser.add_argument("--no-gui", action="store_true", help="只输出控制台，不弹窗提示。")
    parser.add_argument("--show-order", action="store_true", help="显示文件合并顺序（仅控制台输出）")
    args = parser.parse_args(argv)

    folder = Path(args.folder).resolve() if args.folder else _pick_folder()
    if folder is None:
        print("未选择任务目录。")
        return 1

    try:
        output_path, warnings = merge_task_folder(folder, args.output_name, args.sort_by)
    except Exception as e:
        msg = f"合并失败：{e}"
        print(msg)
        if not args.no_gui:
            _show_message("合并任务目录", msg, is_error=True)
        return 2

    # 显示排序方式信息
    sort_method_names = {
        "ctime": "创建时间（上传顺序）",
        "mtime": "修改时间",
        "name": "文件名",
        "birthtime": "文件创建时间"
    }
    
    lines = [
        "合并完成",
        f"排序方式: {sort_method_names.get(args.sort_by, args.sort_by)}",
        f"输入目录: {folder}",
        f"输出文件: {output_path}",
    ]
    
    # 如果需要显示文件顺序
    if args.show_order and not args.no_gui:
        # 重新获取文件列表以显示顺序
        task_files = [p for p in folder.glob("*.json") if p.is_file()]
        if args.sort_by == "ctime":
            task_files.sort(key=lambda p: (p.stat().st_ctime, p.name))
        elif args.sort_by == "mtime":
            task_files.sort(key=lambda p: (p.stat().st_mtime, p.name))
        elif args.sort_by == "birthtime":
            try:
                task_files.sort(key=lambda p: (p.stat().st_birthtime, p.name))
            except AttributeError:
                task_files.sort(key=lambda p: (p.stat().st_ctime, p.name))
        else:
            task_files.sort(key=lambda p: p.name)
        
        lines.append("")
        lines.append("文件合并顺序:")
        for i, f in enumerate(task_files, 1):
            lines.append(f"  {i}. {f.name}")
    
    if warnings:
        lines.append("")
        lines.append("警告:")
        lines.extend(f"- {item}" for item in warnings)

    message = "\n".join(lines)
    print(message)
    if not args.no_gui:
        _show_message("合并任务目录", message, is_error=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))