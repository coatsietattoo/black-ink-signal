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
import { existsSync, readFileSync, writeFileSync, mkdirSync, appendFileSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const isDev = process.env.NODE_ENV === 'development';
const APP_ROOT = join(__dirname, '..');
const RESOURCES_ROOT = process.resourcesPath;
const PROJECT_ROOT = isDev
  ? join(__dirname, '..', '..', '..')
  : join(process.resourcesPath, 'app');
const API_DIR = join(PROJECT_ROOT, 'apps', 'api');
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
  join(PROJECT_ROOT, 'apps', 'api', '.venv', 'bin', 'python3.11'),
  join(PROJECT_ROOT, 'apps', 'api', '.venv', 'bin', 'python3'),
  join(PROJECT_ROOT, 'apps', 'api', '.venv', 'bin', 'python'),
];
const PROD_PYTHON_PATH = join(RESOURCES_ROOT, 'python', 'bin', 'python3.11');

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let mainWindow = null;
let setupWindow = null;
let tray = null;
let isQuitting = false;
let apiReady = false;
const BUILD_STAMP = 'Jun-09-supervisor-v1';
const SERVICE_BACKOFF_MS = 5000;
const HEALTH_CHECK_INTERVAL_MS = 15000;
const serviceState = {
  api: {
    label: 'api',
    process: null,
    stopping: false,
    ready: false,
    restartTimer: null,
    healthTimer: null,
    lastExitCode: null,
    lastStartAt: null,
  },
  scheduler: {
    label: 'scheduler',
    process: null,
    stopping: false,
    ready: false,
    restartTimer: null,
    healthTimer: null,
    lastExitCode: null,
    lastStartAt: null,
  },
};

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

function ensureLogDir() {
  const logDir = isDev ? join(PROJECT_ROOT, 'runtime', 'logs') : join(app.getPath('userData'), 'logs');
  if (!existsSync(logDir)) {
    mkdirSync(logDir, { recursive: true });
  }
  return logDir;
}

function getSupervisorLogFile() {
  return join(ensureLogDir(), 'supervisor.log');
}

function writeSupervisorLog(level, message) {
  const line = `${new Date().toISOString()} [${level}] ${message}`;
  console.log(line);
  try {
    appendFileSync(getSupervisorLogFile(), `${line}\n`);
  } catch (err) {
    console.error(`[BIS] Failed to write supervisor log: ${err.message}`);
  }
}

function logSpawnPlan(label, plan, cwdOverride = null) {
  const resolvedPython = plan.pythonPath || plan.command;
  writeSupervisorLog('INFO', `Python executable (${label}): ${resolvedPython}`);
  writeSupervisorLog('INFO', `Working directory (${label}): ${cwdOverride || plan.cwd}`);
  writeSupervisorLog('INFO', `resourcesPath: ${process.resourcesPath}`);
  writeSupervisorLog('INFO', `Spawn command (${label}): ${plan.command} ${plan.args.join(' ')}`);
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

function clearServiceTimer(state, key) {
  if (state[key]) {
    clearTimeout(state[key]);
    clearInterval(state[key]);
    state[key] = null;
  }
}

function markApiReady(ready) {
  apiReady = ready;
  serviceState.api.ready = ready;
  updateTrayMenu();
}

function scheduleServiceRestart(serviceName, reason) {
  const state = serviceState[serviceName];
  if (!state || isQuitting || state.stopping || state.restartTimer) return;

  writeSupervisorLog('WARN', `Scheduling ${serviceName} restart in ${SERVICE_BACKOFF_MS}ms (${reason})`);
  state.restartTimer = setTimeout(async () => {
    state.restartTimer = null;
    try {
      await startService(serviceName);
    } catch (err) {
      writeSupervisorLog('ERROR', `Restart failed for ${serviceName}: ${err.message}`);
      scheduleServiceRestart(serviceName, 'restart_failed');
    }
  }, SERVICE_BACKOFF_MS);
}

function attachProcessLogging(serviceName, child) {
  child.stdout.on('data', (data) => {
    const msg = data.toString().trim();
    if (!msg) return;
    writeSupervisorLog('INFO', `[${serviceName}] ${msg}`);
    if (serviceName === 'api' && (msg.includes('Application startup complete') || msg.includes('Uvicorn running'))) {
      markApiReady(true);
    }
  });

  child.stderr.on('data', (data) => {
    const msg = data.toString().trim();
    if (!msg) return;
    writeSupervisorLog('ERROR', `[${serviceName}] ${msg}`);
    if (serviceName === 'api' && (msg.includes('Application startup complete') || msg.includes('Uvicorn running'))) {
      markApiReady(true);
    }
  });
}

function startApiHealthMonitor() {
  const state = serviceState.api;
  clearServiceTimer(state, 'healthTimer');
  state.healthTimer = setInterval(async () => {
    if (isQuitting || state.stopping || !state.process) return;
    try {
      const res = await fetch(`${API_URL}/health`);
      const ok = res.ok;
      markApiReady(ok);
      if (!ok) {
        writeSupervisorLog('WARN', 'API health check returned non-OK status');
      }
    } catch (err) {
      markApiReady(false);
      writeSupervisorLog('WARN', `API health check failed: ${err.message}`);
    }
  }, HEALTH_CHECK_INTERVAL_MS);
}

function startSchedulerHealthMonitor() {
  const state = serviceState.scheduler;
  clearServiceTimer(state, 'healthTimer');
  state.healthTimer = setInterval(() => {
    if (isQuitting || state.stopping) return;
    if (!state.process || state.process.killed) {
      writeSupervisorLog('WARN', 'Scheduler health check detected missing process');
      scheduleServiceRestart('scheduler', 'health_check_missing_process');
    }
  }, HEALTH_CHECK_INTERVAL_MS);
}

async function waitForApi(timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${API_URL}/health`);
      if (res.ok) {
        markApiReady(true);
        return true;
      }
    } catch {
      // ignore
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function getServiceLaunchConfig(serviceName) {
  const plan = resolveBackendLaunch();
  if (serviceName === 'scheduler') {
    return {
      command: plan.command,
      args: ['-m', 'app.scheduler'],
      cwd: API_DIR,
      pythonPath: plan.pythonPath,
    };
  }
  return plan;
}

async function startService(serviceName) {
  const state = serviceState[serviceName];
  if (!state) {
    throw new Error(`Unknown service: ${serviceName}`);
  }
  if (state.process && !state.process.killed) {
    return;
  }

  const env = getProcessEnv();
  const plan = getServiceLaunchConfig(serviceName);

  if (!existsSync(DATA_DIR)) {
    mkdirSync(DATA_DIR, { recursive: true });
  }

  state.stopping = false;
  state.lastStartAt = new Date().toISOString();
  logSpawnPlan(serviceName, plan);
  writeSupervisorLog('INFO', `Starting ${serviceName}`);

  await new Promise((resolve, reject) => {
    let settled = false;
    const child = spawn(plan.command, plan.args, {
      cwd: plan.cwd,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    state.process = child;
    attachProcessLogging(serviceName, child);

    child.on('error', (err) => {
      state.process = null;
      if (!settled) {
        settled = true;
        reject(err);
      }
      writeSupervisorLog('ERROR', `${serviceName} failed to start: ${err.message}`);
      scheduleServiceRestart(serviceName, 'spawn_error');
    });

    child.on('exit', (code, signal) => {
      state.lastExitCode = code;
      state.process = null;
      state.ready = false;
      if (serviceName === 'api') {
        markApiReady(false);
      }
      writeSupervisorLog('WARN', `${serviceName} exited (code=${code ?? 'null'}, signal=${signal ?? 'null'})`);
      if (!isQuitting && !state.stopping) {
        scheduleServiceRestart(serviceName, 'unexpected_exit');
      }
      updateTrayMenu();
    });

    if (serviceName === 'scheduler') {
      state.ready = true;
      updateTrayMenu();
      if (!settled) {
        settled = true;
        resolve();
      }
      return;
    }

    waitForApi(15000)
      .then((ready) => {
        if (!settled) {
          settled = true;
          if (ready) {
            resolve();
          } else {
            reject(new Error('API did not become healthy within 15 seconds'));
          }
        }
      })
      .catch((err) => {
        if (!settled) {
          settled = true;
          reject(err);
        }
      });
  });

  state.ready = true;
  if (serviceName === 'api') {
    startApiHealthMonitor();
  } else if (serviceName === 'scheduler') {
    startSchedulerHealthMonitor();
  }
  updateTrayMenu();
}

function stopService(serviceName) {
  const state = serviceState[serviceName];
  if (!state) return;

  state.stopping = true;
  clearServiceTimer(state, 'restartTimer');
  clearServiceTimer(state, 'healthTimer');

  if (state.process) {
    writeSupervisorLog('INFO', `Stopping ${serviceName}`);
    state.process.kill('SIGTERM');
    state.process = null;
  }

  state.ready = false;
  if (serviceName === 'api') {
    markApiReady(false);
  }
  updateTrayMenu();
}

function stopManagedServices() {
  stopService('scheduler');
  stopService('api');
}

// ---------------------------------------------------------------------------
// Windows
// ---------------------------------------------------------------------------

function createMainWindow() {
  writeSupervisorLog('INFO', `Window runtime isDev=${isDev} app.isPackaged=${app.isPackaged}`);
  writeSupervisorLog('INFO', `Window __dirname=${__dirname}`);
  writeSupervisorLog('INFO', `Window APP_ROOT=${APP_ROOT}`);
  writeSupervisorLog('INFO', `Window PROD_HTML=${PROD_HTML}`);

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
    writeSupervisorLog('INFO', `Loading dev URL ${DEV_URL}`);
    mainWindow.loadURL(DEV_URL);
  } else {
    writeSupervisorLog('INFO', `Loading packaged HTML ${PROD_HTML}`);
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

function buildTrayMenu() {
  return Menu.buildFromTemplate([
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
    {
      label: serviceState.scheduler.process ? '● Scheduler Running' : '○ Scheduler Offline',
      enabled: false,
    },
    { type: 'separator' },
    {
      label: 'Quit',
      accelerator: 'CmdOrCtrl+Q',
      click: () => {
        isQuitting = true;
        stopManagedServices();
        app.quit();
      },
    },
  ]);
}

function updateTrayMenu() {
  if (!tray) return;
  tray.setContextMenu(buildTrayMenu());
}

function createTray() {
  if (tray) {
    updateTrayMenu();
    return;
  }

  const icon = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAAhUlEQVQ4T' +
      '2NkYPj/n4EBHTAyMDAyoIthVcfIiKGOEUMdI1Z1jMg2MOJQR7YNjBjqGLFsYMSwgRGHOkZsGxgx1DFi' +
      '2cCIywZGDHWMWDYw4tLAiKGOEcsGRlwaGDHUMWLZwIhLAyOGOkYsGxhxaWDEUMeIZQMjLg2M6OoYAQC2' +
      'kx4WkZcKIQAAAABJRU5ErkJggg=='
  );
  icon.setTemplateImage(true);

  tray = new Tray(icon);
  tray.setToolTip('Black Ink Signal');
  updateTrayMenu();
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
  if (!mainWindow) {
    createMainWindow();
  }

  try {
    await startService('api');
    await startService('scheduler');
  } catch (err) {
    const ready = await waitForApi(5000);
    if (!ready) {
      writeSupervisorLog('ERROR', `Startup failed: ${err.message}`);
      dialog.showErrorBox(
        'Black Ink Signal — Startup Error',
        `Could not start the backend services.\n\nError: ${err.message}\n\n` +
          `Review the supervisor log at:\n${getSupervisorLogFile()}`
      );
    }
  }

  createTray();
  updateTrayMenu();
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  ensureLogDir();
  writeSupervisorLog('INFO', `Build: ${BUILD_STAMP}`);
  writeSupervisorLog('INFO', `Runtime app.isPackaged=${app.isPackaged}`);
  writeSupervisorLog('INFO', `Runtime __dirname=${__dirname}`);
  writeSupervisorLog('INFO', `Runtime APP_ROOT=${APP_ROOT}`);
  writeSupervisorLog('INFO', `Runtime PROD_HTML=${PROD_HTML}`);

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
  stopManagedServices();
});

process.on('SIGTERM', () => {
  isQuitting = true;
  stopManagedServices();
  app.quit();
});

process.on('SIGINT', () => {
  isQuitting = true;
  stopManagedServices();
  app.quit();
});
