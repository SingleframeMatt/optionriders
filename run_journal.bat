@echo off
REM Option Riders - Trade Journal launcher (Windows)
REM First-time setup:
REM   1. Double-click this file. It'll create a .env from .env.example.
REM   2. Open .env in Notepad, paste your IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID.
REM   3. Double-click this file again to start the journal.
REM   4. Open http://127.0.0.1:8125/journal.html in your browser.

setlocal
cd /d "%~dp0"

if not exist .env (
    if exist .env.example (
        copy /Y .env.example .env >nul
        echo.
        echo ============================================================
        echo  Created .env from .env.example
        echo.
        echo  Next step: open .env in Notepad, fill in your IBKR token
        echo  and query ID, save it, then re-run this script.
        echo ============================================================
        echo.
        notepad .env
        pause
        exit /b 0
    ) else (
        echo ERROR: no .env or .env.example found.
        pause
        exit /b 1
    )
)

REM Sanity-check that the token is filled in
findstr /R "^IBKR_FLEX_TOKEN=..........." .env >nul
if errorlevel 1 (
    echo.
    echo .env exists but IBKR_FLEX_TOKEN looks empty.
    echo Open .env, paste your token and query ID, save it, then re-run.
    echo.
    notepad .env
    pause
    exit /b 0
)

REM Locate python. Prefer py launcher (shipped with python.org installer), fall back to python.
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo ERROR: Python is not installed.
        echo Install Python 3.10 or newer from https://www.python.org/downloads/windows/
        echo During install, tick "Add Python to PATH".
        pause
        exit /b 1
    )
)

echo.
echo Starting trade journal on http://127.0.0.1:8125/journal.html
echo Press Ctrl+C in this window to stop.
echo.

%PY% server.py

pause
