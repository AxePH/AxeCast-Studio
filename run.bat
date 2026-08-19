@echo off
title AxeCast Studio Launcher 🪓
cd /d "%~dp0"

echo ====================================================
echo        Starting AxeCast Studio Mobile Mirror 🪓
echo ====================================================
echo.

python app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ====================================================
    echo An error occurred. Checking required packages...
    echo ====================================================
    python -m pip install -r requirements.txt
    python app.py
)
pause
