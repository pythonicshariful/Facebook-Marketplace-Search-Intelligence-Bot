@echo off
TITLE Marketplace Bot - Unit Test Suite
COLOR 0A
cd /d "%~dp0"

echo ======================================================================
echo    Running Marketplace Bot Automated Test Suite
echo ======================================================================
echo.
".venv\Scripts\pytest.exe" -v
echo.
echo ======================================================================
echo    Test Execution Completed.
echo ======================================================================
pause
