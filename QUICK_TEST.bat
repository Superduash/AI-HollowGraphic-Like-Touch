@echo off
REM Quick test runner for AI HollowGraphic Like Touch
REM Run this to verify all functionality is working

echo [TESTING] AI HollowGraphic Like Touch - Comprehensive Test Suite
echo ================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found. Please run setup first.
    exit /b 1
)

echo Starting tests...
".venv\Scripts\python.exe" tests/run_tests.py

if %errorlevel% equ 0 (
    echo.
    echo ================================================================
    echo [SUCCESS] All tests passed! Application is ready.
    echo ================================================================
) else (
    echo.
    echo ================================================================
    echo [FAILURE] Some tests failed. See details above.
    echo ================================================================
)

exit /b %errorlevel%
