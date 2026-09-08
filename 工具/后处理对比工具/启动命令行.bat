@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
echo.
echo 请选择后处理对比类型：
echo [1] 贴图
echo [2] 高斯渲染
echo [3] AI重贴图
choice /c 123 /n /m "请输入选项："
if errorlevel 3 set "OPERATION=ai_retexture"
if errorlevel 2 set "OPERATION=gaussian"
if errorlevel 1 set "OPERATION=texture"
python cli.py --operation "%OPERATION%"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo 退出码: %EXIT_CODE%
pause
exit /b %EXIT_CODE%
