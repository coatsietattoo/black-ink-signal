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

import { app, BrowserWindow, Tray, Menu, nativeImage, dialog, ipcMain, shell } from 'electron';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const isDev = process.env.NODE_ENV === 'development';
const DEV_PROJECT_ROOT = '/Users/alancoates/Downloads/black-ink-signal';
const DEV_API_DIR = '/Users/alancoates/Downloads/black-ink-signal/apps/api';
const APP_ROOT = join(__dirname, '..');
const RESOURCES_ROOT = process.resourcesPath;
const PROJECT_ROOT = isDev
  ? DEV_PROJECT_ROOT
  : join(process.resourcesPath, 'app');
const API_DIR = isDev
  ? DEV_API_DIR
  : join(PROJECT_ROOT, 'apps', 'api');
const DATA_DIR = isDev
  ? join(PROJECT_ROOT, 'data')
  : join(app.getPath('userData'), 'data');
const ENV_FILE = isDev
  ? join(PROJECT_ROOT, '.env')
  : join(app.getPath('userData'), '.env');
const ENV_TEMPLATE_FILE = join(PROJECT_ROOT, '.env.example');
const DEV_URL = 'http://localhost:5173';
const PROD_HTML = join(APP_ROOT, 'dist', 'index.html');
const API_PORT = parseInt(process.env.BIS_API_PORT || '8787', 10);
const API_URL = `http://127.0.0.1:${API_PORT}`;
const DEV_PYTHON_CANDIDATES = [
  '/Users/alancoates/Downloads/black-ink-signal/apps/api/.venv/bin/python3.11',
  '/Users/alancoates/Downloads/black-ink-signal/apps/api/.venv/bin/python3',
];
const PROD_PYTHON_PATH = join(RESOURCES_ROOT, 'python', 'bin', 'python3.11');

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
const BUILD_STAMP = 'May-29-mac-dev-diagnostic-v1';

// ---------------------------------------------------------------------------
// Backend/Python resolution
// ---------------------------------------------------------------------------

function findExistingPath(candidates) {
  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) return candidate;
  }
  return null;
}

function resolveBackendLaunch() {
  const pythonPath = isDev ? findExistingPath(DEV_PYTHON_CANDIDATES) : PROD_PYTHON_PATH;

  console.log('[BIS DEV] PROJECT_ROOT=', PROJECT_ROOT);
  console.log('[BIS DEV] API_DIR=', API_DIR);
  console.log('[BIS DEV] DEV_PYTHON_CANDIDATES=', DEV_PYTHON_CANDIDATES);
  console.log('[BIS DEV] selectedPython=', pythonPath);

  if (!pythonPath || !existsSync(pythonPath)) {
    throw new Error(
      isDev
        ? 'Python 3.11+ venv not found. Expected apps/api/.venv/bin/python3.11'
        : 'Bundled Python 3.11+ runtime not found in app resources. Expected Resources/python/bin/python3.11'
    );
  }

  return {
    command: pythonPath,
    args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(API_PORT)],
    cwd: API_DIR,
    pythonPath,
  };
}

function logSpawnPlan(label, plan, cwdOverride = null) {
  const resolvedPython = plan.pythonPath || plan.command;
  console.log(`[BIS] Python executable: ${resolvedPython}`);
  console.log(`[BIS] API cwd: ${cwdOverride || plan.cwd}`);
  console.log(`[BIS] resourcesPath: ${process.resourcesPath}`);
  console.log(`[BIS] Spawn label: ${label}`);
  console.log(`[BIS] Spawn command: ${plan.command} ${plan.args.join(' ')}`);
}

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------

function ensurePackagedEnvTemplate() {
  if (isDev) return;
  if (existsSync(ENV_FILE)) return;
  if (!existsSync(ENV_TEMPLATE_FILE)) return;

  try {
    writeFileSync(ENV_FILE, readFileSync(ENV_TEMPLATE_FILE, 'utf-8'));
  } catch (err) {
    console.warn(`[BIS] Could not seed packaged env file: ${err.message}`);
  }
}

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

  writeFileSync(ENV_FILE, `${content.trim()}\n`);
}

// ---------------------------------------------------------------------------
// Backend management
// ---------------------------------------------------------------------------

function getProcessEnv() {
  const env = { ...process.env, ...loadEnv() };
  const pythonPaths = [
    join(PROJECT_ROOT, 'packages', 'core'),
    join(PROJECT_ROOT, 'packages', 'connectors', 'reddit'),
    API_DIR,
  ];

  env.PYTHONPATH = [env.PYTHONPATH, ...pythonPaths].filter(Boolean).join(':');
  env.BIS_DB_PATH = join(DATA_DIR, 'black_ink_signal.db');

  if (!env.BIS_SUBREDDITS) {
    env.BIS_SUBREDDITS = 'Edmonton,tattoos,tattooadvice,tattoodesigns,irezumi,AskReddit';
  }
  if (!env.BIS_KEYWORDS) {
    env.BIS_KEYWORDS = 'tattoo artist|looking for tattoo|cover up tattoo|Edmonton tattoo|black and grey tattoo|realism tattoo|tattoo recommendations|first tattoo|sleeve tattoo|walk in tattoo|tattoo quote';
  }
  if (!env.PYTHONUNBUFFERED) {
    env.PYTHONUNBUFFERED = '1';
  }

  return env;
}

function startBackend() {
  return new Promise((resolve, reject) => {
    const env = getProcessEnv();
    const plan = resolveBackendLaunch();

    if (!existsSync(DATA_DIR)) {
      mkdirSync(DATA_DIR, { recursive: true });
    }

    logSpawnPlan('api', plan);

    apiProcess = spawn(plan.command, plan.args, {
      cwd: plan.cwd,
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
  const env = getProcessEnv();
  const plan = resolveBackendLaunch();
  const schedulerArgs = ['-m', 'app.scheduler'];
  const schedulerCwd = API_DIR;

  console.log('[BIS] Starting scheduler...');
  logSpawnPlan('scheduler', { ...plan, args: schedulerArgs }, schedulerCwd);

  schedulerProcess = spawn(plan.command, schedulerArgs, {
    cwd: schedulerCwd,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  schedulerProcess.stdout.on('data', (d) => console.log(`[SCHED] ${d.toString().trim()}`));
  schedulerProcess.stderr.on('data', (d) => console.error(`[SCHED:err] ${d.toString().trim()}`));
  schedulerProcess.on('exit', (code) => {
    console.log(`[BIS] Scheduler exited with code ${code}`);
    if (!isQuitting && code !== 0) {
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
  restartAttempts += 1;
  if (restartAttempts > MAX_RESTART_ATTEMPTS) {
    dialog.showErrorBox(
      'Black Ink Signal — Backend Failed',
      `The backend crashed ${MAX_RESTART_ATTEMPTS} times and won't restart.\n\n` +
        'Possible issues:\n' +
        '• Python not found or wrong version\n' +
        '• Missing bundled backend executable or packaged Python runtime\n' +
        '• Missing dependencies\n' +
        '• Port 8787 already in use\n\n' +
        'Check the console logs for the resolved Python path and backend command.'
    );
    return;
  }

  console.log(`[BIS] Backend crashed. Restart attempt ${restartAttempts}/${MAX_RESTART_ATTEMPTS}...`);

  try {
    await startBackend();
    startScheduler();
    restartAttempts = 0;
  } catch {
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
    } catch {
      // ignore
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

// ---------------------------------------------------------------------------
// Windows
// ---------------------------------------------------------------------------

function createMainWindow() {
  console.log(`[BIS RUNTIME] isDev=${isDev} app.isPackaged=${app.isPackaged}`);
  console.log(`[BIS RUNTIME] __dirname=${__dirname}`);
  console.log(`[BIS RUNTIME] APP_ROOT=${APP_ROOT}`);
  console.log(`[BIS RUNTIME] PROD_HTML=${PROD_HTML}`);

  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    title: 'Black Ink Signal',
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#09090b',
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: join(__dirname, 'preload.js'),
    },
  });

  if (isDev) {
    console.log(`[BIS RUNTIME] loadURL=${DEV_URL}`);
    mainWindow.loadURL(DEV_URL);
  } else {
    console.log(`[BIS RUNTIME] loadFile=${PROD_HTML}`);
    mainWindow.loadFile(PROD_HTML);
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

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
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
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
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ---------------------------------------------------------------------------
// IPC handlers
// ---------------------------------------------------------------------------

ipcMain.handle('save-credentials', async (_event, creds) => {
  saveEnvCredentials(creds);
  return { success: true };
});

ipcMain.handle('get-env-status', async () => ({
  hasCredentials: hasRedditCredentials(),
  envPath: ENV_FILE,
  apiPort: API_PORT,
  projectRoot: PROJECT_ROOT,
}));

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

ipcMain.handle('open-external', async (_event, url) => {
  if (!url || typeof url !== 'string') {
    throw new Error('Invalid URL');
  }
  await shell.openExternal(url);
  return { success: true };
});

// ---------------------------------------------------------------------------
// Launch flow
// ---------------------------------------------------------------------------

async function launchApp() {
  createMainWindow();

  try {
    await startBackend();
  } catch (err) {
    const ready = await waitForApi(5000);
    if (!ready) {
      dialog.showErrorBox(
        'Black Ink Signal — Startup Error',
        `Could not start the backend server.\n\nError: ${err.message}\n\n` +
          'Make sure a bundled backend exists, or Python 3.11+ is available in the packaged runtime.\n' +
          'The app logs the resolved Python path and backend command to help diagnose packaged launches.'
      );
    }
  }

  startScheduler();
  createTray();
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  console.log(`[BIS BUILD] ${BUILD_STAMP}`);
  console.log(`[BIS RUNTIME] app.isPackaged=${app.isPackaged}`);
  console.log(`[BIS RUNTIME] __dirname=${__dirname}`);
  console.log(`[BIS RUNTIME] APP_ROOT=${APP_ROOT}`);
  console.log(`[BIS RUNTIME] PROD_HTML=${PROD_HTML}`);

  await dialog.showMessageBox({
    type: 'info',
    message: `BUILD: ${BUILD_STAMP}\n__dirname=${__dirname}\nAPP_ROOT=${APP_ROOT}\nPROD_HTML=${PROD_HTML}`,
    buttons: ['OK'],
  });

  ensurePackagedEnvTemplate();

  if (process.platform === 'darwin') {
    app.dock.setMenu(
      Menu.buildFromTemplate([{ label: 'Show Window', click: () => mainWindow?.show() }])
    );
  }

  const hasEnv = existsSync(ENV_FILE) && hasRedditCredentials();

  if (!hasEnv && !isDev) {
    createSetupWindow();
  } else {
    await launchApp();
  }
});

app.on('window-all-closed', () => {
  // stay resident in tray
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

process.on('SIGTERM', () => {
  isQuitting = true;
  stopBackend();
  app.quit();
});

process.on('SIGINT', () => {
  isQuitting = true;
  stopBackend();
  app.quit();
});
