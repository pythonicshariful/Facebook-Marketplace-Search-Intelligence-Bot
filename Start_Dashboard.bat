@echo off
TITLE Marketplace Vehicle Intelligence Bot
COLOR 0B
cd /d "%~dp0"

echo ======================================================================
echo    Facebook Marketplace Vehicle Search Intelligence Bot
echo ======================================================================
echo.

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in .venv!
    echo Running setup script...
    powershell -ExecutionPolicy Bypass -File "scripts\setup_venv.ps1"
)

echo Starting Bot Server at http://127.0.0.1:8080 ...
echo.
echo Launching your browser to http://127.0.0.1:8080 in 3 seconds...
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8080"

echo.
echo Press Ctrl+C in this window at any time to safely stop the bot.
echo ----------------------------------------------------------------------
".venv\Scripts\python.exe" run.py
pause
