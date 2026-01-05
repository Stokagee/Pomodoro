@echo off
title Pomodoro Timer - IT Optimized
cd /d "%~dp0"

echo.
echo ============================================
echo   POMODORO TIMER - IT Optimized (52/17)
echo ============================================
echo.
echo   Checking Python dependencies...
echo.

pip show flask >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing dependencies...
    pip install -r requirements.txt
)

echo.
echo   Starting server...
echo   Open browser: http://localhost:5000
echo.
echo   Press Ctrl+C to stop
echo ============================================
echo.

python app.py

pause
