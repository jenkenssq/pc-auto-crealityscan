@echo off
chcp 65001 > nul
echo ============================================================
echo   CrealityScan 自动化测试工具 - 打包程序
echo ============================================================
echo.

:: 检查 Python 是否安装
python --version > nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查 pip 是否安装
pip --version > nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 pip，请重新安装 Python
    pause
    exit /b 1
)

echo [1/3] 检查依赖...
echo.
pip show pyinstaller > nul 2>&1
if errorlevel 1 (
    echo     安装 PyInstaller...
    pip install pyinstaller
)

echo.
echo [2/3] 安装项目依赖...
pip install -r requirements.txt

echo.
echo [3/3] 开始打包...
echo.
python build_exe.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败！
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   打包完成！
echo ============================================================
echo.
echo 输出目录: dist\CrealityScan自动化测试工具
echo.
echo 按任意键打开输出目录...
pause > nul
explorer dist\CrealityScan自动化测试工具
