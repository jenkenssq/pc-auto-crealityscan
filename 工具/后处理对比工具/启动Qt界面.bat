@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if not errorlevel 1 goto :start_gui
echo 未找到 Python，请先安装 Python 3.11 或更高版本。
pause
exit /b 1

:start_gui
python -m postprocess_compare.qt_app
if not errorlevel 1 goto :done
echo Qt 应用退出码：%errorlevel%
pause

:done
endlocal
