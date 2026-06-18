@echo off
echo Stopping processes on port 8000...
echo.

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Killing PID %%a
    taskkill /PID %%a /F 2>nul
)

timeout /t 2 /nobreak >nul

powershell -NoProfile -Command ^
  "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2; Write-Host 'WARNING: Port still in use' } catch { Write-Host 'Port 8000 is free. You can run start_python.bat' }"

echo.
pause
