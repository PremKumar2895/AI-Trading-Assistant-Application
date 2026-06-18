const { app, BrowserWindow, ipcMain, screen, Tray, Menu, nativeImage } = require('electron');
const path = require('path');
const isDev = require('electron-is-dev');

let mainWindow;
let tray = null;

const TRAY_ICON_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlz' +
  'AAALEwAACxMBAJqcGAAAABZJREFUOI1jYBgFgx8wMjIyMow8AAAE0AABsBCGAAAAAElFTkSuQmCC';

function createTray() {
  try {
    const icon = nativeImage.createFromDataURL(`data:image/png;base64,${TRAY_ICON_B64}`);
    tray = new Tray(icon);
    tray.setToolTip('AI Trading Assistant');
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: 'Show', click: () => mainWindow && (mainWindow.show(), mainWindow.focus()) },
      { type: 'separator' },
      { label: 'Quit', click: () => app.quit() },
    ]));
    tray.on('click', () => mainWindow && (mainWindow.show(), mainWindow.focus()));
  } catch (e) {
    console.warn('Tray creation failed (non-fatal):', e.message);
  }
}

function createWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  mainWindow = new BrowserWindow({
    width: Math.min(1180, width - 40),
    height: Math.min(780, height - 40),
    minWidth: 900,
    minHeight: 600,
    frame: false,
    backgroundColor: '#0d0e12',
    show: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      webSecurity: false, // allow renderer (file://) to call the local engine
    },
  });

  const startUrl = isDev
    ? 'http://localhost:5173'
    : `file://${path.join(__dirname, '../dist/index.html')}`;
  mainWindow.loadURL(startUrl);

  let shown = false;
  const reveal = (why) => {
    if (shown || !mainWindow || mainWindow.isDestroyed()) return;
    shown = true;
    mainWindow.show();
    mainWindow.focus();
    console.log(`AI Trading Assistant window visible (${why})`);
  };
  mainWindow.once('ready-to-show', () => reveal('ready-to-show'));
  mainWindow.webContents.once('did-finish-load', () => reveal('did-finish-load'));
  setTimeout(() => reveal('fallback-timer'), 3000);

  mainWindow.on('closed', () => (mainWindow = null));
}

app.on('ready', () => {
  createWindow();
  createTray();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});

// --- window controls ---
ipcMain.on('quit-app', () => app.quit());
ipcMain.on('minimize-app', () => mainWindow && mainWindow.minimize());
ipcMain.on('maximize-app', () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});
