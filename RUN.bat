@echo off
setlocal enabledelayedexpansion
title AI Trading Assistant - Launcher
cd /d "%~dp0"

echo.
echo  ============================================================
echo    AI TRADING ASSISTANT  ^|  one-click launcher
echo  ============================================================
echo.

REM --- Kill any leftover engine / app from previous runs ----------
echo [CLEAN] Stopping any previous engine / app instances...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING" 2^>nul') do taskkill /PID %%a /F >nul 2>&1
taskkill /IM electron.exe /F >nul 2>&1
ping -n 2 127.0.0.1 >nul

REM --- 1. Check Python --------------------------------------------
where python >nul 2>&1
if errorlevel 1 goto NO_PYTHON
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [1/7] Python: %%v

REM --- 2. Python dependencies -------------------------------------
echo [2/7] Checking Python dependencies...
python -m pip install -r "%~dp0python-engine\requirements.txt" --quiet --disable-pip-version-check
echo       Dependencies ready.

REM --- 3. Node / npm check ----------------------------------------
where npm >nul 2>&1
if errorlevel 1 goto NO_NODE
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo [3/7] Node: %%v

REM --- 4. Node dependencies (only first run) ----------------------
if exist "%~dp0desktop-app\node_modules" goto NODE_DEPS_OK
echo [4/7] Installing Node dependencies. First run, please wait.
pushd "%~dp0desktop-app"
call npm install
popd
goto NODE_DEPS_DONE
:NODE_DEPS_OK
echo [4/7] Node dependencies already installed.
:NODE_DEPS_DONE

REM --- 5. Build the UI --------------------------------------------
echo [5/7] Building user interface...
pushd "%~dp0desktop-app"
call npm run build >nul 2>&1
popd
if not exist "%~dp0desktop-app\dist\index.html" goto BUILD_FAILED
echo       UI built.

REM --- 6. Train the AI model (only first run) ---------------------
if exist "%~dp0python-engine\model_store\trade_model.pkl" goto MODEL_OK
echo [6/7] Training AI model on market history. First run only, about 1-2 min.
pushd "%~dp0python-engine"
python train.py
popd
goto MODEL_DONE
:MODEL_OK
echo [6/7] AI model already trained.
:MODEL_DONE

REM --- 7. Start the Python analysis engine ------------------------
echo [7/7] Starting analysis engine on port 8000...
start "AI Trading Engine - keep this window open" /D "%~dp0python-engine" cmd /k python -m uvicorn app:app --host 127.0.0.1 --port 8000

REM --- Wait up to 40 s for the engine health endpoint ------------
echo       Waiting for engine to come online...
set /a TRIES=0
:WAIT_LOOP
set /a TRIES+=1
powershell -NoProfile -Command "try { Invoke-WebRequest 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto ENGINE_READY
if !TRIES! GEQ 40 goto ENGINE_TIMEOUT
ping -n 2 127.0.0.1 >nul
goto WAIT_LOOP

:ENGINE_TIMEOUT
echo.
echo  [WARN] Engine did not respond after 40 s.
echo         Check the "AI Trading Engine" window for errors.
echo         The app will still open and reconnect once the engine is up.
goto LAUNCH_APP

:ENGINE_READY
echo       Engine is ready.

:LAUNCH_APP
echo.
echo  ============================================================
echo    APP IS LAUNCHING
echo.
echo    A desktop window will open shortly.
echo    Search any asset (EUR/USD, Apple, BTC, Gold, Nifty),
echo    pick it, and the AI analyses every timeframe for you.
echo.
echo    If you do not see the window, check the taskbar or the
echo    system tray icon near the clock.
echo  ============================================================
echo.

set ELECTRON_IS_DEV=0
pushd "%~dp0desktop-app"
call npm start
popd

REM --- Cleanup when the app window is closed ----------------------
echo.
echo  Shutting down the analysis engine...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING" 2^>nul') do taskkill /PID %%a /F >nul 2>&1
echo  Done. You can close this window.
goto END

:NO_PYTHON
echo.
echo  [ERROR] Python is not installed or not on PATH.
echo          Install Python 3.10+ from https://python.org then re-run.
goto FAIL

:NO_NODE
echo.
echo  [ERROR] Node.js / npm is not installed or not on PATH.
echo          Install Node.js LTS from https://nodejs.org then re-run.
goto FAIL

:BUILD_FAILED
echo.
echo  [ERROR] UI build failed - dist\index.html was not created.
echo          Open a terminal in desktop-app and run:  npm run build
echo          to see the full error message.
goto FAIL

:FAIL
echo.
pause
exit /b 1

:END
pause
endlocal
