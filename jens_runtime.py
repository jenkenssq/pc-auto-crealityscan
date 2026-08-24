from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_resource_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass).resolve()
        return (Path(sys.executable).resolve().parent / "_internal").resolve()
    return Path(__file__).resolve().parent


def iter_existing_resource_roots() -> Iterable[Path]:
    seen: set[str] = set()
    for root in (get_app_root(), get_resource_root()):
        key = str(root.resolve())
        if key in seen:
            continue
        seen.add(key)
        if root.exists():
            yield root
