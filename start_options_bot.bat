@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: start_options_bot.bat — Launch the Option Riders Options Bot dashboard
::
:: What this does:
::   1. Changes to the project directory
::   2. Activates a Python virtual environment if one exists (venv or .venv)
::   3. Starts server.py (Flask, port 8126) in a new minimised window
::   4. Opens the dashboard in the default browser
::
:: Dashboard URL: http://127.0.0.1:8126
:: ─────────────────────────────────────────────────────────────────────────────

title Option Riders — Options Bot
cd /d "%~dp0"

:: ── Activate venv if present ─────────────────────────────────────────────────
if exist "venv\Scripts\activate.bat" (
    echo [+] Activating venv...
    call "venv\Scripts\activate.bat"
) else if exist ".venv\Scripts\activate.bat" (
    echo [+] Activating .venv...
    call ".venv\Scripts\activate.bat"
) else (
    echo [!] No virtual environment found — using system Python.
)

:: ── Check Python is available ────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and try again.
    pause
    exit /b 1
)

:: ── Install / update dependencies ────────────────────────────────────────────
echo [+] Checking dependencies...
pip install -q -r requirements.txt

:: ── Create required directories ───────────────────────────────────────────────
if not exist "logs" mkdir logs
if not exist "static" mkdir static

:: ── Start the options bot Flask server in a new window ───────────────────────
echo [+] Starting Options Bot server on port 8126...
start "Options Bot Server" /min cmd /k "python server.py"

:: Wait a moment for the server to start, then open the browser
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8126"

echo.
echo [OK] Options Bot is running!
echo      Dashboard: http://127.0.0.1:8126
echo      API:       http://127.0.0.1:8126/api/options
echo      The bot window is minimised in the taskbar.
echo      Logs:      logs\options_bot_YYYY-MM-DD.log
echo.
echo      Press any key to exit this window (bot keeps running).
pause >nul
