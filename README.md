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

**Terminal 1 (Python Engine):**
```sh
cd python-engine
uvicorn app:app --host 0.0.0.0 --port 8000
```
*You should see "Uvicorn running on http://0.0.0.0:8000"*

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

## Troubleshooting
- **"Connection Refused"**: Ensure Python server is running on port 8000.
- **Black Screen / No Capture**: 
  - Ensure the app has Screen Recording permissions (mainly macOS).
  - On Windows, ensure no full-screen exclusive games/apps are blocking it.
- **Dependencies Fail**: Run `npm install` inside `desktop-app` again.
