@echo off
title AI Trading - Python Engine
cd /d "%~dp0python-engine"

echo Installing Python dependencies...
python -m pip install -r requirements.txt -q

echo.
echo Checking port 8000...

powershell -NoProfile -Command ^
  "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"

if %ERRORLEVEL%==0 (
    echo.
    echo [OK] Python engine is ALREADY running on http://127.0.0.1:8000
    echo      You can start the desktop app now. Do not start a second engine.
    echo.
    pause
    exit /b 0
)

echo.
echo Starting server at http://127.0.0.1:8000
echo Health check: http://127.0.0.1:8000/health
echo WebSocket:    ws://127.0.0.1:8000/ws
echo.
echo Keep this window OPEN while using the app.
echo.

python -m uvicorn app:app --host 127.0.0.1 --port 8000
if errorlevel 1 (
    echo.
    echo Port 8000 may be stuck. Run stop_python.bat then try again.
    echo Or close any other "Python Engine" / uvicorn window.
    echo.
    pause
)
