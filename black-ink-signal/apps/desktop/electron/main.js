/**
 * Black Ink Signal — Electron main process (production-ready).
 *
 * Single-click launch:
 * 1. Starts FastAPI backend (child process)
 * 2. Starts scheduler (child process)
 * 3. Waits for API health check
 * 4. Opens desktop UI
 * 5. Handles failures with restart + popup
 *
 * First-run: shows setup flow if .env is missing Reddit credentials.
 */

import { app, BrowserWindow, Tray, Menu, Notification, nativeImage, dialog, ipcMain, shell } from 'electron';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'fs';
import { createServer } from 'net';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const isDev = process.env.NODE_ENV === 'development';
const APP_ROOT = isDev
  ? join(__dirname, '..')
  : join(process.resourcesPath, 'app');
const PROJECT_ROOT = isDev
  ? join(__dirname, '..', '..')  // black-ink-signal/
  : join(app.getPath('userData'), 'engine');
const API_DIR = join(PROJECT_ROOT, 'apps', 'api');
const DATA_DIR = join(PROJECT_ROOT, 'data');
const ENV_FILE = join(PROJECT_ROOT, '.env');
const DEV_URL = 'http://localhost:5173';
const PROD_HTML = join(APP_ROOT, 'dist', 'index.html');
const API_PORT = parseInt(process.env.BIS_API_PORT || '8787');
const API_URL = `http://127.0.0.1:${API_PORT}`;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let mainWindow = null;
let setupWindow = null;
let tray = null;
let apiProcess = null;
let schedulerProcess = null;
let isQuitting = false;
let apiReady = false;
let restartAttempts = 0;
const MAX_RESTART_ATTEMPTS = 3;

// ---------------------------------------------------------------------------
// Python detection
// ---------------------------------------------------------------------------

function findPython() {
  // Check venv first (relative to API_DIR)
  const venvPython = join(API_DIR, '.venv', 'bin', 'python3');
  if (existsSync(venvPython)) return venvPython;
  const venvPython2 = join(API_DIR, '.venv', 'bin', 'python');
  if (existsSync(venvPython2)) return venvPython2;
  // macOS Homebrew (Apple Silicon)
  if (existsSync('/opt/homebrew/bin/python3')) return '/opt/homebrew/bin/python3';
  // macOS Homebrew (Intel)
  if (existsSync('/usr/local/bin/python3')) return '/usr/local/bin/python3';
  // System python
  if (existsSync('/usr/bin/python3')) return '/usr/bin/python3';
  // Fallback
  return 'python3';
}

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------

function loadEnv() {
  if (!existsSync(ENV_FILE)) return {};
  const content = readFileSync(ENV_FILE, 'utf-8');
  const env = {};
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const match = trimmed.match(/^([^=]+)=(.*)$/);
    if (match) {
      env[match[1].trim()] = match[2].trim().replace(/^["']|["']$/g, '');
    }
  }
  return env;
}

function hasRedditCredentials() {
  const env = loadEnv();
  return !!(env.BIS_REDDIT_CLIENT_ID && env.BIS_REDDIT_CLIENT_SECRET);
}

function saveEnvCredentials(creds) {
  let content = '';
  if (existsSync(ENV_FILE)) {
    content = readFileSync(ENV_FILE, 'utf-8');
  }

  const updates = {
    BIS_REDDIT_CLIENT_ID: creds.clientId,
    BIS_REDDIT_CLIENT_SECRET: creds.clientSecret,
    BIS_REDDIT_USERNAME: creds.username,
    BIS_REDDIT_PASSWORD: creds.password,
    BIS_REDDIT_USER_AGENT: creds.userAgent || 'BlackInkSignal/0.1',
  };

  for (const [key, value] of Object.entries(updates)) {
    const regex = new RegExp(`^#?\\s*${key}=.*$`, 'm');
    if (regex.test(content)) {
      content = content.replace(regex, `${key}=${value}`);
    } else {
      content += `\n${key}=${value}`;
    }
  }

  writeFileSync(ENV_FILE, content.trim() + '\n');
}

// ---------------------------------------------------------------------------
// Backend management
// ---------------------------------------------------------------------------

function getProcessEnv() {
  const env = { ...process.env, ...loadEnv() };
  env.PYTHONPATH = [
    join(PROJECT_ROOT, 'packages', 'core'),
    join(PROJECT_ROOT, 'packages', 'connectors', 'reddit'),
  ].join(':');
  env.BIS_DB_PATH = join(DATA_DIR, 'black_ink_signal.db');
  return env;
}

function startBackend() {
  return new Promise((resolve, reject) => {
    const python = findPython();
    const env = getProcessEnv();

    // Ensure data directory exists
    if (!existsSync(DATA_DIR)) {
      mkdirSync(DATA_DIR, { recursive: true });
    }

    console.log(`[BIS] Starting API: ${python} -m uvicorn app.main:app --port ${API_PORT} --host 127.0.0.1`);

    apiProcess = spawn(python, [
      '-m', 'uvicorn', 'app.main:app',
      '--host', '127.0.0.1',
      '--port', String(API_PORT),
    ], {
      cwd: API_DIR,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    apiProcess.stdout.on('data', (data) => {
      const msg = data.toString();
      console.log(`[API] ${msg.trim()}`);
      if (msg.includes('Application startup complete') || msg.includes('Uvicorn running')) {
        apiReady = true;
        resolve();
      }
    });

    apiProcess.stderr.on('data', (data) => {
      const msg = data.toString();
      console.error(`[API:err] ${msg.trim()}`);
      if (msg.includes('Application startup complete') || msg.includes('Uvicorn running')) {
        apiReady = true;
        resolve();
      }
    });

    apiProcess.on('error', (err) => {
      console.error('[BIS] Failed to start API:', err.message);
      reject(err);
    });

    apiProcess.on('exit', (code) => {
      console.log(`[BIS] API exited with code ${code}`);
      apiReady = false;
      if (!isQuitting && code !== 0) {
        handleBackendCrash();
      }
    });

    // Timeout: if no startup message in 15s, try health check
    setTimeout(async () => {
      if (!apiReady) {
        try {
          const res = await fetch(`${API_URL}/health`);
          if (res.ok) {
            apiReady = true;
            resolve();
          } else {
            reject(new Error('API health check failed'));
          }
        } catch {
          reject(new Error('API did not start within 15 seconds'));
        }
      }
    }, 15000);
  });
}

function startScheduler() {
  const python = findPython();
  const env = getProcessEnv();

  console.log('[BIS] Starting scheduler...');

  schedulerProcess = spawn(python, ['app/scheduler.py'], {
    cwd: API_DIR,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  schedulerProcess.stdout.on('data', (d) => console.log(`[SCHED] ${d.toString().trim()}`));
  schedulerProcess.stderr.on('data', (d) => console.error(`[SCHED:err] ${d.toString().trim()}`));
  schedulerProcess.on('exit', (code) => {
    console.log(`[BIS] Scheduler exited with code ${code}`);
    if (!isQuitting && code !== 0) {
      // Restart scheduler silently
      setTimeout(() => startScheduler(), 5000);
    }
  });
}

function stopBackend() {
  if (apiProcess) {
    apiProcess.kill('SIGTERM');
    apiProcess = null;
  }
  if (schedulerProcess) {
    schedulerProcess.kill('SIGTERM');
    schedulerProcess = null;
  }
}

async function handleBackendCrash() {
  restartAttempts++;
  if (restartAttempts > MAX_RESTART_ATTEMPTS) {
    dialog.showErrorBox(
      'Black Ink Signal — Backend Failed',
      `The backend crashed ${MAX_RESTART_ATTEMPTS} times and won't restart.\n\n` +
      'Possible issues:\n' +
      '• Python not found or wrong version\n' +
      '• Missing dependencies (run: pip install -r requirements.txt)\n' +
      '• Port 8787 already in use\n\n' +
      'Check the console logs for details.'
    );
    return;
  }

  console.log(`[BIS] Backend crashed. Restart attempt ${restartAttempts}/${MAX_RESTART_ATTEMPTS}...`);

  try {
    await startBackend();
    startScheduler();
    restartAttempts = 0; // Reset on success
  } catch (err) {
    handleBackendCrash();
  }
}

// ---------------------------------------------------------------------------
// Health check polling
// ---------------------------------------------------------------------------

async function waitForApi(timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${API_URL}/health`);
      if (res.ok) return true;
    } catch {}
    await new Promise(r => setTimeout(r, 500));
  }
  return false;
}

// ---------------------------------------------------------------------------
// Windows
// ---------------------------------------------------------------------------

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    title: 'Black Ink Signal',
    titleBarStyle: 'hiddenInset',  // macOS native feel
    backgroundColor: '#09090b',
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: join(__dirname, 'preload.js'),
    },
  });

  if (isDev) {
    mainWindow.loadURL(DEV_URL);
  } else {
    mainWindow.loadFile(PROD_HTML);
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Open external links in system browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

function createSetupWindow() {
  setupWindow = new BrowserWindow({
    width: 600,
    height: 700,
    resizable: false,
    title: 'Black Ink Signal — Setup',
    backgroundColor: '#09090b',
    show: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: join(__dirname, 'preload.js'),
    },
  });

  setupWindow.loadFile(join(__dirname, 'setup.html'));

  // Open external links in system browser
  setupWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  setupWindow.webContents.on('will-navigate', (event, url) => {
    if (url.startsWith('http') && !url.includes('localhost')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
}

// ---------------------------------------------------------------------------
// Tray
// ---------------------------------------------------------------------------

function createTray() {
  // 22x22 macOS tray icon (template image for dark/light mode)
  const icon = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAAhUlEQVQ4T' +
    '2NkYPj/n4EBHTAyMDAyoIthVcfIiKGOEUMdI1Z1jMg2MOJQR7YNjBjqGLFsYMSwgRGHOkZsGxgx1DFi' +
    '2cCIywZGDHWMWDYw4tLAiKGOEcsGRlwaGDHUMWLZwIhLAyOGOkYsGxhxaWDEUMeIZQMjLg2M6OoYAQC2' +
    'kx4WkZcKIQAAAABJRU5ErkJggg=='
  );
  icon.setTemplateImage(true);

  tray = new Tray(icon);
  tray.setToolTip('Black Ink Signal');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Black Ink Signal',
      click: () => {
        if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
      },
    },
    { type: 'separator' },
    {
      label: apiReady ? '● API Running' : '○ API Offline',
      enabled: false,
    },
    { type: 'separator' },
    {
      label: 'Quit',
      accelerator: 'CmdOrCtrl+Q',
      click: () => {
        isQuitting = true;
        stopBackend();
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => {
    if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
  });
}

// ---------------------------------------------------------------------------
// IPC handlers (for setup window)
// ---------------------------------------------------------------------------

ipcMain.handle('save-credentials', async (event, creds) => {
  saveEnvCredentials(creds);
  return { success: true };
});

ipcMain.handle('get-env-status', async () => {
  return {
    hasCredentials: hasRedditCredentials(),
    envPath: ENV_FILE,
    apiPort: API_PORT,
    projectRoot: PROJECT_ROOT,
  };
});

ipcMain.handle('start-app', async () => {
  if (setupWindow) {
    setupWindow.close();
    setupWindow = null;
  }
  await launchApp();
});

ipcMain.handle('skip-setup', async () => {
  if (setupWindow) {
    setupWindow.close();
    setupWindow = null;
  }
  await launchApp();
});

// ---------------------------------------------------------------------------
// Launch flow
// ---------------------------------------------------------------------------

async function launchApp() {
  // Show splash / loading state
  createMainWindow();

  try {
    await startBackend();
  } catch (err) {
    const ready = await waitForApi(5000);
    if (!ready) {
      dialog.showErrorBox(
        'Black Ink Signal — Startup Error',
        `Could not start the backend server.\n\n` +
        `Error: ${err.message}\n\n` +
        'Make sure Python 3.11+ is installed and dependencies are set up.\n' +
        'See docs/LOCAL_SETUP.md for details.'
      );
    }
  }

  // Start scheduler (non-blocking)
  startScheduler();

  // Create tray
  createTray();
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  // macOS: set dock icon
  if (process.platform === 'darwin') {
    // The dock icon is set via the .icns in the build config
    app.dock.setMenu(Menu.buildFromTemplate([
      { label: 'Show Window', click: () => mainWindow?.show() },
    ]));
  }

  // First-run check
  const hasEnv = existsSync(ENV_FILE) && hasRedditCredentials();

  if (!hasEnv && !isDev) {
    // Show setup flow
    createSetupWindow();
  } else {
    await launchApp();
  }
});

app.on('window-all-closed', () => {
  // Don't quit — stay in tray
});

app.on('activate', () => {
  if (mainWindow) {
    mainWindow.show();
  } else if (!setupWindow) {
    launchApp();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  stopBackend();
});

// Graceful shutdown on signals
process.on('SIGTERM', () => { isQuitting = true; stopBackend(); app.quit(); });
process.on('SIGINT', () => { isQuitting = true; stopBackend(); app.quit(); });
