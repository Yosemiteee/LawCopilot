const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lawcopilotDesktop", {
  getRuntimeInfo: () => ipcRenderer.invoke("lawcopilot:get-runtime-info"),
  ensureBackend: (options) => ipcRenderer.invoke("lawcopilot:ensure-backend", options),
  getStoredConfig: () => ipcRenderer.invoke("lawcopilot:get-desktop-config"),
  saveStoredConfig: (patch) => ipcRenderer.invoke("lawcopilot:save-desktop-config", patch),
  getDesktopTtsVoices: () => ipcRenderer.invoke("lawcopilot:get-desktop-tts-voices"),
  speakText: (payload) => ipcRenderer.invoke("lawcopilot:speak-text", payload),
  stopSpeaking: () => ipcRenderer.invoke("lawcopilot:stop-speaking"),
  getUpdateStatus: () => ipcRenderer.invoke("lawcopilot:get-update-status"),
  checkForUpdates: () => ipcRenderer.invoke("lawcopilot:check-for-updates"),
  downloadUpdate: () => ipcRenderer.invoke("lawcopilot:download-update"),
  quitAndInstallUpdate: () => ipcRenderer.invoke("lawcopilot:quit-and-install-update"),
  onUpdateStatus: (listener) => {
    if (typeof listener !== "function") {
      return () => {};
    }
    const handler = (_event, payload) => listener(payload);
    ipcRenderer.on("lawcopilot:update-status", handler);
    return () => {
      ipcRenderer.removeListener("lawcopilot:update-status", handler);
    };
  },
  onAutomationEvent: (listener) => {
    if (typeof listener !== "function") {
      return () => {};
    }
    const handler = (_event, payload) => listener(payload);
    ipcRenderer.on("lawcopilot:automation-event", handler);
    return () => {
      ipcRenderer.removeListener("lawcopilot:automation-event", handler);
    };
  },
  saveLocationSnapshot: (payload) => ipcRenderer.invoke("lawcopilot:save-location-snapshot", payload),
  getIntegrationConfig: () => ipcRenderer.invoke("lawcopilot:get-integration-config"),
  saveIntegrationConfig: (patch) => ipcRenderer.invoke("lawcopilot:save-integration-config", patch),
  saveIntegrationConfigFast: (patch) => ipcRenderer.invoke("lawcopilot:save-integration-config-fast", patch),
  runAssistantLegacySetup: (payload) => ipcRenderer.invoke("lawcopilot:run-assistant-legacy-setup", payload),
  validateProviderConfig: (payload) => ipcRenderer.invoke("lawcopilot:validate-provider-config", payload),
  getCodexAuthStatus: () => ipcRenderer.invoke("lawcopilot:get-codex-auth-status"),
  startCodexAuth: () => ipcRenderer.invoke("lawcopilot:start-codex-auth"),
  submitCodexAuthCallback: (callbackUrl) => ipcRenderer.invoke("lawcopilot:submit-codex-auth-callback", callbackUrl),
  cancelCodexAuth: () => ipcRenderer.invoke("lawcopilot:cancel-codex-auth"),
  setCodexModel: (model) => ipcRenderer.invoke("lawcopilot:set-codex-model", model),
  getGoogleAuthStatus: () => ipcRenderer.invoke("lawcopilot:get-google-auth-status"),
  startGoogleAuth: () => ipcRenderer.invoke("lawcopilot:start-google-auth"),
  submitGoogleAuthCallback: (callbackUrl) => ipcRenderer.invoke("lawcopilot:submit-google-auth-callback", callbackUrl),
  cancelGoogleAuth: () => ipcRenderer.invoke("lawcopilot:cancel-google-auth"),
  syncGoogleData: () => ipcRenderer.invoke("lawcopilot:sync-google-data"),
  getGooglePortabilityAuthStatus: () => ipcRenderer.invoke("lawcopilot:get-google-portability-auth-status"),
  startGooglePortabilityAuth: () => ipcRenderer.invoke("lawcopilot:start-google-portability-auth"),
  submitGooglePortabilityAuthCallback: (callbackUrl) => ipcRenderer.invoke("lawcopilot:submit-google-portability-auth-callback", callbackUrl),
  cancelGooglePortabilityAuth: () => ipcRenderer.invoke("lawcopilot:cancel-google-portability-auth"),
  syncGooglePortabilityData: () => ipcRenderer.invoke("lawcopilot:sync-google-portability-data"),
  chooseGoogleHistoryArchive: () => ipcRenderer.invoke("lawcopilot:choose-google-history-archive"),
  importGoogleHistoryArchive: (filePaths) => ipcRenderer.invoke("lawcopilot:import-google-history-archive", filePaths),
  getOutlookAuthStatus: () => ipcRenderer.invoke("lawcopilot:get-outlook-auth-status"),
  startOutlookAuth: () => ipcRenderer.invoke("lawcopilot:start-outlook-auth"),
  cancelOutlookAuth: () => ipcRenderer.invoke("lawcopilot:cancel-outlook-auth"),
  syncOutlookData: () => ipcRenderer.invoke("lawcopilot:sync-outlook-data"),
  sendGmailMessage: (payload) => ipcRenderer.invoke("lawcopilot:send-gmail-message", payload),
  createGoogleCalendarEvent: (payload) => ipcRenderer.invoke("lawcopilot:create-google-calendar-event", payload),
  validateTelegramConfig: (payload) => ipcRenderer.invoke("lawcopilot:validate-telegram-config", payload),
  getTelegramStatus: () => ipcRenderer.invoke("lawcopilot:get-telegram-status"),
  startTelegramWebLink: () => ipcRenderer.invoke("lawcopilot:start-telegram-web-link"),
  sendTelegramTestMessage: (payload) => ipcRenderer.invoke("lawcopilot:send-telegram-test-message", payload),
  syncTelegramData: () => ipcRenderer.invoke("lawcopilot:sync-telegram-data"),
  getWhatsAppStatus: () => ipcRenderer.invoke("lawcopilot:get-whatsapp-status"),
  validateWhatsAppConfig: (payload) => ipcRenderer.invoke("lawcopilot:validate-whatsapp-config", payload),
  startWhatsAppWebLink: () => ipcRenderer.invoke("lawcopilot:start-whatsapp-web-link"),
  syncWhatsAppData: () => ipcRenderer.invoke("lawcopilot:sync-whatsapp-data"),
  sendWhatsAppMessage: (payload) => ipcRenderer.invoke("lawcopilot:send-whatsapp-message", payload),
  disconnectWhatsApp: () => ipcRenderer.invoke("lawcopilot:disconnect-whatsapp"),
  getXAuthStatus: () => ipcRenderer.invoke("lawcopilot:get-x-auth-status"),
  startXAuth: () => ipcRenderer.invoke("lawcopilot:start-x-auth"),
  cancelXAuth: () => ipcRenderer.invoke("lawcopilot:cancel-x-auth"),
  syncXData: () => ipcRenderer.invoke("lawcopilot:sync-x-data"),
  postXUpdate: (payload) => ipcRenderer.invoke("lawcopilot:post-x-update", payload),
  sendXDirectMessage: (payload) => ipcRenderer.invoke("lawcopilot:send-x-direct-message", payload),
  getLinkedInAuthStatus: () => ipcRenderer.invoke("lawcopilot:get-linkedin-auth-status"),
  getLinkedInStatus: () => ipcRenderer.invoke("lawcopilot:get-linkedin-status"),
  startLinkedInAuth: () => ipcRenderer.invoke("lawcopilot:start-linkedin-auth"),
  startLinkedInWebLink: () => ipcRenderer.invoke("lawcopilot:start-linkedin-web-link"),
  cancelLinkedInAuth: () => ipcRenderer.invoke("lawcopilot:cancel-linkedin-auth"),
  syncLinkedInData: () => ipcRenderer.invoke("lawcopilot:sync-linkedin-data"),
  postLinkedInUpdate: (payload) => ipcRenderer.invoke("lawcopilot:post-linkedin-update", payload),
  getInstagramAuthStatus: () => ipcRenderer.invoke("lawcopilot:get-instagram-auth-status"),
  startInstagramAuth: () => ipcRenderer.invoke("lawcopilot:start-instagram-auth"),
  cancelInstagramAuth: () => ipcRenderer.invoke("lawcopilot:cancel-instagram-auth"),
  syncInstagramData: () => ipcRenderer.invoke("lawcopilot:sync-instagram-data"),
  sendInstagramMessage: (payload) => ipcRenderer.invoke("lawcopilot:send-instagram-message", payload),
  dispatchApprovedAction: (payload) => ipcRenderer.invoke("lawcopilot:dispatch-approved-action", payload),
  chooseWorkspaceRoot: () => ipcRenderer.invoke("lawcopilot:choose-workspace-root"),
  getWorkspaceConfig: () => ipcRenderer.invoke("lawcopilot:get-workspace-config"),
  saveWorkspaceConfig: (patch) => ipcRenderer.invoke("lawcopilot:save-workspace-config", patch),
  openPathInOS: (relativePath) => ipcRenderer.invoke("lawcopilot:open-path", relativePath),
  revealPathInOS: (relativePath) => ipcRenderer.invoke("lawcopilot:reveal-path", relativePath),
});
