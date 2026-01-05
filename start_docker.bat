@echo off
title Pomodoro Timer v2.0 - Docker
cd /d "%~dp0"

echo.
echo ============================================
echo   POMODORO TIMER v2.0 - Docker + MongoDB + ML
echo ============================================
echo.
echo   Starting all services...
echo.

docker-compose up -d

echo.
echo   Services started!
echo.
echo   Access:
echo     - Pomodoro Timer: http://localhost:5000
echo     - ML API:         http://localhost:5001
echo     - MongoDB Admin:  http://localhost:8081
echo       (admin / pomodoro2025)
echo.
echo   To view logs: docker-compose logs -f
echo   To stop:      docker-compose down
echo.
echo ============================================
echo.

pause
