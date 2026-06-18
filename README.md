# AI Trading Assistant (Phase 1 MVP)

## Prerequisites
- **Node.js**: Installed on your system.
- **Python 3.11**: Installed with `pip`.
- **Windows/macOS**: Desktop environment.

## Installation

### 1. Python Engine
Navigate to `python-engine` and install dependencies:
```sh
cd python-engine
pip install -r requirements.txt
```

### 2. Desktop App
Navigate to `desktop-app` and install dependencies:
```sh
cd desktop-app
npm install
```

## Running the System

### One-Click Start (Recommended)
Simply double-click **`start_app.bat`** in the main project folder. 
It will automatically launch Python, React, and Electron in separate windows.

### Manual Start
If you prefer running manual commands, follow these steps:

**Terminal 1 (Python Engine) — required first:**
```sh
# Double-click start_python.bat  OR:
cd python-engine
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```
Verify in browser: **http://127.0.0.1:8000/health** (must show `{"status":"healthy"}`)

> Use `127.0.0.1` in the browser, not `0.0.0.0` (invalid in browsers).

**Terminal 2 (desktop-app):**
Run `desktop-app\run_ui.bat`

**Terminal 3 (desktop-app):**
Run `desktop-app\run_electron.bat`


### Step 3: Usage
1. Open your trading chart (e.g., TradingView or Broker App).
2. The Overlay will appear Always-On-Top.
3. Click **START** on the overlay.
4. The system will start capturing the screen and analyzing candles.
5. Signals (BUY/SELL/WAIT) will appear in real-time.

## Binomo setup (recommended)

1. Open **binomo.com/trading** in Chrome/Edge (maximize window).
2. Install **Tesseract OCR** on Windows: https://github.com/UB-Mannheim/tesseract/wiki  
   Default path: `C:\Program Files\Tesseract-OCR\tesseract.exe`
3. Start Python + desktop app. Enable **Force Scan** if asset shows UNKNOWN.
4. Place the overlay **away from the chart** (right side is OK) so candles are visible.
5. Signals: **UP** = green button, **DOWN** = red button. **EXPIRY** matches your 1m/5m setting.

> No screen-based tool can guarantee 100% wins. Use demo account first.

## Troubleshooting
- **`ECONNREFUSED 127.0.0.1:8000`**: Python engine is not running. Run `start_python.bat` and keep that window open until you see `Uvicorn running on http://127.0.0.1:8000`.
- **"Connection Refused"**: Open http://127.0.0.1:8000/health — if it fails, fix Python errors in the engine terminal.
- **SyntaxError on start**: Update project files; `app.py` must import without errors (`python -c "import app"` from `python-engine`).
- **Black Screen / No Capture**: 
  - Ensure the app has Screen Recording permissions (mainly macOS).
  - On Windows, ensure no full-screen exclusive games/apps are blocking it.
- **Dependencies Fail**: Run `npm install` inside `desktop-app` again.
