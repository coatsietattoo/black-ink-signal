/**
 * Preload script — exposes safe IPC methods to renderer.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('bis', {
  saveCredentials: (creds) => ipcRenderer.invoke('save-credentials', creds),
  getEnvStatus: () => ipcRenderer.invoke('get-env-status'),
  startApp: () => ipcRenderer.invoke('start-app'),
  skipSetup: () => ipcRenderer.invoke('skip-setup'),
});
