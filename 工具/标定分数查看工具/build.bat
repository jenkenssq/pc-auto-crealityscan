@echo off
chcp 65001 >nul
echo ========================================
echo   标定分数查看工具 - 打包脚本
echo ========================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.x
    pause
    exit /b 1
)

REM 安装/检查PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [安装] 正在安装 PyInstaller...
    pip install pyinstaller
)

REM 打包
echo.
echo [打包] 正在生成可执行文件...
pyinstaller --onefile --windowed --name "标定分数查看工具" --add-data "parser.py;." main.py

if exist "dist\标定分数查看工具.exe" (
    echo.
    echo ========================================
    echo   打包成功!
    echo   文件位置: dist\标定分数查看工具.exe
    echo ========================================
    start explorer dist
) else (
    echo.
    echo [错误] 打包失败，请检查上方错误信息
)

pause