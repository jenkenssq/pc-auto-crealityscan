#!/bin/bash
# ============================================
#  标定分数查看工具 - macOS 打包脚本
#  双击本文件即可在 Mac 上打出 .app 应用包
#  打出的 .app 自带 Python + tkinter 环境，
#  目标 Mac 无需安装任何东西，双击即用
# ============================================

# 双击启动时工作目录是用户主目录，需切换到脚本所在目录
cd "$(dirname "$0")" || exit 1

# ---- 1. 查找可用的 Python3 ----
PYTHON=""
for candidate in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "========================================"
    echo "  错误：未找到 Python3"
    echo "========================================"
    echo "打包机需先安装 Python 3（推荐 Homebrew）："
    echo "  brew install python@3.12"
    echo ""
    read -r -p "按回车键关闭窗口..."
    exit 1
fi

# ---- 2. 检查 tkinter（打包 .app 必需，会连同 Tcl/Tk 一起打入）----
if ! "$PYTHON" -c "import tkinter" >/dev/null 2>&1; then
    echo "========================================"
    echo "  错误：Python 缺少 tkinter"
    echo "========================================"
    echo "请执行：brew install python-tk"
    echo ""
    read -r -p "按回车键关闭窗口..."
    exit 1
fi

# ---- 3. 安装/检查 PyInstaller ----
# 用真实加载模块检测（pip show 只看安装元数据，残留记录会误判已安装）
if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
    echo "[安装] 正在安装 PyInstaller ..."
    "$PYTHON" -m pip install --force-reinstall pyinstaller || {
        echo "[错误] PyInstaller 安装失败，请检查网络后重试"
        read -r -p "按回车键关闭窗口..."
        exit 1
    }
fi

# ---- 4. 打包 ----
# 架构说明：默认打当前机器的芯片架构。
#   如果目标 Mac 可能同时有 Apple Silicon 和 Intel，
#   取消下面一行注释，打出 universal2 通用包（需已安装 Xcode）：
# ARCH_FLAG="--target-architecture universal2"
ARCH_FLAG=""

echo "[打包] 正在生成 .app ..."
"$PYTHON" -m pyinstaller --onefile --windowed $ARCH_FLAG --name "标定分数查看工具" main.py

APP="dist/标定分数查看工具.app"
if [ -d "$APP" ]; then
    echo ""
    echo "========================================"
    echo "  打包成功！"
    echo "  应用位置: dist/标定分数查看工具.app"
    echo "========================================"
    echo ""
    echo "分发到其他 Mac 后，若提示'无法验证开发者'，"
    echo "在目标 Mac 上执行一次清除隔离属性即可："
    echo "  xattr -cr \"标定分数查看工具.app\""
    echo ""
    open dist
else
    echo ""
    echo "[错误] 打包失败，请截图上方报错信息"
fi

read -r -p "按回车键关闭窗口..."
