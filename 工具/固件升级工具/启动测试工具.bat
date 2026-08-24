@echo off
chcp 65001 > nul
echo ============================================================
echo   CrealityScan 自动化测试工具
echo ============================================================
echo.

:: 检查虚拟环境是否存在
if exist "venv\Scripts\activate.bat" (
    echo 检测到虚拟环境，激活中...
    call venv\Scripts\activate.bat
) else (
    echo 使用当前 Python 环境...
)

echo.
echo 启动测试工具...
python run_test.py

echo.
pause
