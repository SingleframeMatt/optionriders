@echo off
cd /d "%~dp0"
echo Starting Crypto Bot (port 8125)...
start /min cmd /c "python crypto_server.py > crypto_server.log 2>&1"
timeout /t 2 /nobreak >/dev/null
echo Starting Options Bot (port 8126)...
call "%~dp0start_options_bot.bat"
timeout /t 2 /nobreak >/dev/null
echo Starting Proxy (port 8127)...
start /min cmd /c "python proxy.py > proxy.log 2>&1"
timeout /t 2 /nobreak >/dev/null
echo Starting Futures Bot (port 8128)...
start /min cmd /c "python futures_bot.py > futures_bot.log 2>&1"
echo All bots started.
