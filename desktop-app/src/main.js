const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('path');
const { startCaptureLoop, stopCaptureLoop, setCaptureRegion } = require('./capture/capture');
const { connectWebSocket, sendFrame, onSignalReceived } = require('./websocket');
const isDev = require('electron-is-dev');

let mainWindow;

function createWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  mainWindow = new BrowserWindow({
    width: 400, // Small overlay
    height: 600,
    x: width - 450,
    y: 100,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false, // For MVP speed, usually not recommended but allows require('electron') in renderer
      webSecurity: false
    }
  });

  // Load Vite Dev Server url in Dev, or local file in Prod
  const startUrl = isDev
    ? 'http://localhost:5173'
    : `file://${path.join(__dirname, '../dist/index.html')}`;

  mainWindow.loadURL(startUrl);

  // Open DevTools in detached state for debugging if needed
  // mainWindow.webContents.openDevTools({ mode: 'detach' });

  mainWindow.on('closed', () => (mainWindow = null));

  // Track window movement to mask it in Python Engine
  mainWindow.on('move', sendOverlayBounds);
  mainWindow.on('resize', sendOverlayBounds);

  // Send initial bounds after a short delay to ensure WS is ready
  setTimeout(sendOverlayBounds, 2000);
}

app.on('ready', () => {
  createWindow();
  connectWebSocket(); // Connect to Python Engine on start
});

app.on('window-all-closed', () => {
  stopCaptureLoop();
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});

// --- IPC Handlers ---

// Receive signal from WebSocket logic and forward to UI
onSignalReceived((signalData) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('signal-update', signalData);
  }
});

// Helper to send bounds
function sendOverlayBounds() {
  if (!mainWindow) return;
  const bounds = mainWindow.getBounds();
  const { sendCommand } = require('./websocket');
  sendCommand({ action: 'update_overlay_bounds', bounds });
}

// UI controls
ipcMain.on('start-scanning', (event, region) => {
  console.log("Starting scan with region:", region);
  if (region) {
    setCaptureRegion(region); // {x, y, w, h}
  }
  // Callback to send frame via WS
  const onFrameCaptured = (buffer) => {
    sendFrame(buffer);
  };

  startCaptureLoop(onFrameCaptured);
});

ipcMain.on('stop-scanning', () => {
  console.log("Stopping scan");
  stopCaptureLoop();
});

ipcMain.on('send-command', (event, data) => {
  const { sendCommand } = require('./websocket');
  sendCommand(data);
});
