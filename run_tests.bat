@echo off
setlocal enabledelayedexpansion
title Pomodoro Timer v2.0 - Test Runner
cd /d "%~dp0"

echo.
echo ============================================
echo   POMODORO TIMER v2.0 - TEST SUITE
echo ============================================
echo.

REM Check if pytest is installed
python -m pytest --version >nul 2>&1
if errorlevel 1 (
    echo   Installing test dependencies...
    pip install -r requirements-test.txt
    echo.
)

echo   Running tests...
echo.

REM Parse arguments
if "%1"=="" (
    REM Run tests separately to avoid module conflicts
    echo   [1/2] Running Web App tests...
    python -m pytest tests/web/ -v --tb=short
    set WEB_EXIT=!errorlevel!

    echo.
    echo   [2/2] Running ML Service tests...
    python -m pytest tests/ml_service/ -v --tb=short
    set ML_EXIT=!errorlevel!

    echo.
    if !WEB_EXIT!==0 if !ML_EXIT!==0 (
        echo   All tests passed!
    ) else (
        echo   Some tests failed.
    )
) else if "%1"=="web" (
    REM Run only web tests
    python -m pytest tests/web/ -v --tb=short
) else if "%1"=="ml" (
    REM Run only ML service tests
    python -m pytest tests/ml_service/ -v --tb=short
) else if "%1"=="cov" (
    REM Run with coverage report (separately)
    echo   Running Web tests with coverage...
    python -m pytest tests/web/ -v --cov=web --cov-report=term-missing
    echo.
    echo   Running ML tests with coverage...
    python -m pytest tests/ml_service/ -v --cov=ml-service --cov-report=term-missing --cov-report=html
    echo.
    echo   Coverage report: htmlcov/index.html
) else if "%1"=="fast" (
    REM Run fast tests only (skip slow/integration)
    python -m pytest tests/web/ -v -m "not slow and not integration"
    python -m pytest tests/ml_service/ -v -m "not slow and not integration"
) else (
    REM Run specific test file or test
    python -m pytest %* -v --tb=short
)

echo.
echo ============================================
echo.

pause
