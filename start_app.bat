@echo off
echo ===================================================
echo AI Trading Assistant - One-Click Launcher
echo ===================================================

echo 1. Starting Python Signal Engine...
start "Python Engine" cmd /k "cd python-engine && uvicorn app:app --host 0.0.0.0 --port 8000"

echo 2. Starting React UI Renderer...
start "React UI" cmd /k "cd desktop-app && npm run dev"

echo Waiting 5 seconds for UI to be ready...
timeout /t 5 /nobreak

echo 3. Starting Electron Overlay...
start "Electron App" cmd /k "cd desktop-app && npm start"

echo ===================================================
echo All systems launched!
echo Minimized windows can be found in your taskbar.
echo ===================================================
pause
