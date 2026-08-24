@echo off
chcp 65001 > nul
echo ============================================================
echo   CrealityScan 自动化测试工具 - 部署脚本
echo ============================================================
echo.
echo 正在检查 Python 环境...

:: 检查 Python 是否安装
python --version > nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python 3.10+，请先安装 Python
    echo 下载地址: https://www.python.org/downloads/
    echo.
    echo 提示: 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

:: 检查 Python 版本
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYTHON_VERSION=%%v
echo 检测到 Python 版本: %PYTHON_VERSION%

:: 创建虚拟环境（可选）
echo.
echo 是否创建虚拟环境？（推荐，选是）
echo   是 - 创建虚拟环境（推荐，更干净）
echo   否 - 使用当前环境
set /p USE_VENV="请选择 [是/否]: "

if /i "%USE_VENV%"=="是" (
    echo.
    echo 创建虚拟环境...
    python -m venv venv
    echo.
    echo 激活虚拟环境...
    call venv\Scripts\activate.bat

    echo.
    echo 安装依赖包...
    pip install -r requirements.txt

    echo.
    echo ============================================================
    echo   部署完成！
    echo ============================================================
    echo.
    echo 运行程序：
    echo   call venv\Scripts\activate.bat
    echo   python run_test.py
    echo.
    echo 或双击运行: 启动测试工具.bat
    pause
) else (
    echo.
    echo 安装依赖包到当前环境...
    pip install -r requirements.txt

    echo.
    echo ============================================================
    echo   部署完成！
    echo ============================================================
    echo.
    echo 运行程序：
    echo   python run_test.py
    echo.
    echo 或双击运行: 启动测试工具.bat
    pause
)
