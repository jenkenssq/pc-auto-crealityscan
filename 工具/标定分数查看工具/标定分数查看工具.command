#!/bin/bash
# ============================================
#  标定分数查看工具 - macOS 启动脚本
#  在 Finder 中双击本文件即可运行
#  首次使用请先执行: chmod +x 标定分数查看工具.command
# ============================================

# 双击启动时工作目录是用户主目录，需切换到脚本所在目录
cd "$(dirname "$0")" || exit 1

# ---- 1. 查找可用的 Python3 ----
PYTHON=""
for candidate in python3 /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "========================================"
    echo "  错误：未找到 Python3"
    echo "========================================"
    echo "请先安装 Python 3（推荐 Homebrew）："
    echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo "  brew install python@3.12"
    echo ""
    read -r -p "按回车键关闭窗口..."
    exit 1
fi

# ---- 2. 检查 tkinter 是否可用 ----
# 系统自带 Python 自带 tkinter；Homebrew 安装的 Python 需额外安装 python-tk
if ! "$PYTHON" -c "import tkinter" >/dev/null 2>&1; then
    echo "========================================"
    echo "  错误：Python 缺少 tkinter"
    echo "========================================"
    echo "若使用 Homebrew 的 Python，请执行："
    echo "  brew install python-tk"
    echo ""
    read -r -p "按回车键关闭窗口..."
    exit 1
fi

# ---- 3. 运行主程序 ----
# 前台运行：关闭程序窗口后，本终端窗口自动关闭
"$PYTHON" main.py
STATUS=$?

if [ "$STATUS" -ne 0 ]; then
    echo ""
    echo "程序异常退出（错误码 $STATUS），请截图上方报错信息。"
    read -r -p "按回车键关闭窗口..."
fi
