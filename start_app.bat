@echo off
echo ===================================================
echo AI Trading Assistant - Launcher
echo ===================================================

cd /d "%~dp0"

echo 1. Python Engine (port 8000)...
start "Python Engine" cmd /k "%~dp0start_python.bat"

echo Waiting for engine (up to 20s)...
powershell -Command "$ok=$false; 1..10 | ForEach-Object { try { $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){$ok=$true; break} } catch {}; Start-Sleep -Seconds 2 }; if(-not $ok){ Write-Host 'WARNING: Engine not ready - check Python window' } else { Write-Host 'Engine OK' }"

echo 2. React UI...
start "React UI" cmd /k "cd /d %~dp0desktop-app && npm run dev"

timeout /t 5 /nobreak >nul

echo 3. Electron overlay...
start "Electron App" cmd /k "cd /d %~dp0desktop-app && npm start"

echo ===================================================
echo Done. If Electron shows connection errors:
echo   - Open the "Python Engine" window first
echo   - Visit http://127.0.0.1:8000/health in browser
echo ===================================================
pause
