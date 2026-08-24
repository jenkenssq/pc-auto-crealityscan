# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepare_pyqt5() -> int:
    try:
        from PyQt5.QtCore import QLibraryInfo  # type: ignore
    except Exception:
        print("未检测到 PyQt5。请先安装 UI 依赖：")
        print("  python -m pip install -r requirements-ui.txt")
        return 2

    try:
        plugins_dir = QLibraryInfo.location(QLibraryInfo.PluginsPath)
        bin_dir = QLibraryInfo.location(QLibraryInfo.BinariesPath)
        if bin_dir:
            os.add_dll_directory(bin_dir)
        if plugins_dir:
            os.environ.setdefault("QT_PLUGIN_PATH", plugins_dir)
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", os.path.join(plugins_dir, "platforms"))
    except Exception:
        pass
    return 0


def _main() -> int:
    status = _prepare_pyqt5()
    if status:
        return status

    project_root = Path(__file__).resolve().parent
    slide_rail_dir = project_root / "滑轨"
    sys.path.insert(0, str(slide_rail_dir))

    from slide_rail_ui import main

    return int(main())


if __name__ == "__main__":
    raise SystemExit(_main())
