@echo off
REM Enable JARVIS to start on Windows boot
REM Run as Administrator

echo.
echo ================================
echo JARVIS Startup Setup
echo ================================
echo.
echo This will enable JARVIS to start automatically on Windows boot.
echo.

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0echo ================================
echo JARVIS Startup Setup
echo ================================
echo.
echo This will enable JARVIS to start automatically on Windows boot.
echo.
REM Get the directory where this script is located
set PYTHON_CMD=python

REM Run the setup script
python "%SCRIPT_DIR%setup_windows_startup.py"

if %errorlevel% equ 0 (
    echo.
    echo Setup complete! JARVIS will start on next Windows boot.
    echo.
    pause
) else (
    echo.
    echo Setup failed. Try running as Administrator.
    echo.
    pause
)
