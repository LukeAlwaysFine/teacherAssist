@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo   === TeacherAssist ===
echo.

:: find Python
set "PYTHON="
python --version >nul 2>&1 && set "PYTHON=python"
if not defined PYTHON py --version >nul 2>&1 && set "PYTHON=py"
if not defined PYTHON (
    echo Python not found. Install Python 3.11+
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)
echo   Python: %PYTHON%

:: run
%PYTHON% launcher.py
pause
