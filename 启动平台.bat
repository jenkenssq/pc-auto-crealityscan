@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

rem Always resolve files relative to this batch file, not the current directory.
set "JENS_ROOT=%~dp0"
pushd "%JENS_ROOT%" >nul 2>&1
if errorlevel 1 goto :path_error

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem Also support placing this script beside a packaged application.
if exist "%JENS_ROOT%jens_pc_app.exe" (
    start "" /D "%JENS_ROOT%" "%JENS_ROOT%jens_pc_app.exe"
    set "EXIT_CODE=!ERRORLEVEL!"
    goto :finish
)

if not exist "%JENS_ROOT%platform_app.py" goto :entry_missing

if exist "%JENS_ROOT%.venv\Scripts\python.exe" (
    "%JENS_ROOT%.venv\Scripts\python.exe" "%JENS_ROOT%platform_app.py"
    set "EXIT_CODE=!ERRORLEVEL!"
    goto :finish
)

if exist "%JENS_ROOT%venv\Scripts\python.exe" (
    "%JENS_ROOT%venv\Scripts\python.exe" "%JENS_ROOT%platform_app.py"
    set "EXIT_CODE=!ERRORLEVEL!"
    goto :finish
)

where python.exe >nul 2>&1
if not errorlevel 1 (
    python.exe "%JENS_ROOT%platform_app.py"
    set "EXIT_CODE=!ERRORLEVEL!"
    goto :finish
)

where py.exe >nul 2>&1
if not errorlevel 1 (
    py.exe -3 "%JENS_ROOT%platform_app.py"
    set "EXIT_CODE=!ERRORLEVEL!"
    goto :finish
)

echo.
echo [JENS] Python 3 was not found.
echo Install Python or create .venv in:
echo %JENS_ROOT%
set "EXIT_CODE=2"
goto :finish

:path_error
echo.
echo [JENS] Cannot access the directory containing this batch file:
echo %~dp0
set "EXIT_CODE=3"
goto :pause_and_exit

:entry_missing
echo.
echo [JENS] platform_app.py was not found in:
echo %JENS_ROOT%
set "EXIT_CODE=4"
goto :finish

:finish
popd >nul 2>&1
if "%EXIT_CODE%"=="0" exit /b 0

:pause_and_exit
echo.
echo [JENS] Platform startup failed. Exit code: %EXIT_CODE%
echo Check Python and install dependencies with:
echo   python -m pip install -r requirements.txt
echo   python -m pip install -r requirements-ui.txt
echo.
pause
exit /b %EXIT_CODE%
