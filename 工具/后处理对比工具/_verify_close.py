from __future__ import annotations

import os
import time
from pathlib import Path

import psutil

from postprocess_compare.process_manager import ManagedCrealityScan

EXE = Path(r"D:\扫描工具\1.12.3\CrealityScan\CrealityScan.exe")


def main() -> None:
    if not EXE.exists():
        print(f"[VERIFY] exe 不存在：{EXE}")
        return

    mcs = ManagedCrealityScan(EXE)
    print(f"[VERIFY] 启动 CrealityScan：{EXE}")
    pid = mcs.start(timeout_sec=120.0)
    print(f"[VERIFY] 已启动 PID={pid}")

    # 指定窗口：按 title_re 精确定位主窗口（不依赖 top_window）
    win = mcs.app.window(title_re=mcs.window_title_re)
    win.wait("exists visible enabled ready", timeout=30)
    print(f"[VERIFY] 指定窗口: handle={win.handle} title={win.window_text()!r}")

    # 置顶窗口
    try:
        win.maximize()
    except Exception as exc:  # noqa: BLE001
        print(f"[VERIFY] maximize 失败：{exc}")
    win.set_focus()
    time.sleep(1.0)
    print("[VERIFY] 已置顶指定窗口")

    try:
        from airtest.core.api import connect_device, snapshot  # type: ignore
        connect_device("Windows:///")
        snapshot(filename="verify_close_before3.png")
        print("[VERIFY] 关闭前截图 verify_close_before3.png 已保存")
    except Exception as exc:  # noqa: BLE001
        print(f"[VERIFY] 关闭前截图失败：{exc}")

    # 关闭指定窗口（WM_CLOSE）
    started = time.time()
    win.close()
    print("[VERIFY] 已向指定窗口发送 close(WM_CLOSE)")

    exited = False
    try:
        psutil.Process(pid).wait(timeout=20.0)
        exited = True
    except psutil.TimeoutExpired:
        exited = False
    except psutil.NoSuchProcess:
        exited = True

    elapsed = time.time() - started
    running = psutil.pid_exists(pid) if pid else False
    print(f"[VERIFY] elapsed={elapsed:.3f}s exited={exited} running_after={running}")
    print(f"[VERIFY] 判定 => {'正常关闭(指定窗口 WM_CLOSE)' if exited else '20s 未退出，需强制结束'}")


if __name__ == "__main__":
    main()
