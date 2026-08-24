from __future__ import annotations

from typing import Any, Dict


def run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    raise RuntimeError(
        "该步骤已废弃：请使用 crealityscan.configure_scan_params（preset 方案）替代。"
        "（此 step 为兼容历史文件保留，但已从平台列表隐藏）"
    )
