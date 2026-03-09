const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lawcopilotDesktop", {
  getRuntimeInfo: () => ipcRenderer.invoke("lawcopilot:get-runtime-info"),
  getStoredConfig: () => ipcRenderer.invoke("lawcopilot:get-desktop-config"),
  saveStoredConfig: (patch) => ipcRenderer.invoke("lawcopilot:save-desktop-config", patch),
  getIntegrationConfig: () => ipcRenderer.invoke("lawcopilot:get-integration-config"),
  saveIntegrationConfig: (patch) => ipcRenderer.invoke("lawcopilot:save-integration-config", patch),
  validateProviderConfig: (payload) => ipcRenderer.invoke("lawcopilot:validate-provider-config", payload),
  validateTelegramConfig: (payload) => ipcRenderer.invoke("lawcopilot:validate-telegram-config", payload),
  sendTelegramTestMessage: (payload) => ipcRenderer.invoke("lawcopilot:send-telegram-test-message", payload),
  chooseWorkspaceRoot: () => ipcRenderer.invoke("lawcopilot:choose-workspace-root"),
  getWorkspaceConfig: () => ipcRenderer.invoke("lawcopilot:get-workspace-config"),
  saveWorkspaceConfig: (patch) => ipcRenderer.invoke("lawcopilot:save-workspace-config", patch),
  openPathInOS: (relativePath) => ipcRenderer.invoke("lawcopilot:open-path", relativePath),
  revealPathInOS: (relativePath) => ipcRenderer.invoke("lawcopilot:reveal-path", relativePath),
});
