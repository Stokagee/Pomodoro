@echo off
title Pomodoro Timer - Stop
cd /d "%~dp0"

echo.
echo ============================================
echo   Stopping Pomodoro Timer services...
echo ============================================
echo.

docker-compose down

echo.
echo   All services stopped.
echo ============================================
echo.

pause
