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

// UI controls
ipcMain.on('start-scanning', (event, region) => {
    console.log("Starting scan with region:", region);
    if(region){
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
