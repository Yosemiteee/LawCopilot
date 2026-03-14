const path = require("path");
const { spawn, spawnSync } = require("child_process");
const { app, BrowserWindow, dialog, ipcMain, Menu, shell } = require("electron");

const { loadDesktopConfig, resolveRuntimePaths, sanitizeDesktopConfig, saveDesktopConfig } = require("./lib/config.cjs");
const { startBackend, stopBackend, waitForBackend } = require("./lib/backend.cjs");
const { cancelCodexOAuth, getCodexAuthStatus, setCodexModel, startCodexOAuth, submitCodexOAuthCallback } = require("./lib/codex-oauth.cjs");
const { cancelGoogleOAuth, consumeCompletedGoogleOAuth, getGoogleAuthStatus, startGoogleOAuth, submitGoogleOAuthCallback } = require("./lib/google-oauth.cjs");
const { createGoogleCalendarEvent, sendGmailMessage, syncGoogleData } = require("./lib/google-data.cjs");
const { cancelXOAuth, getXAuthStatus, startXOAuth } = require("./lib/x-oauth.cjs");
const { postXUpdate, syncXData } = require("./lib/x-api.cjs");
const { getWhatsAppStatus, sendWhatsAppMessage, syncWhatsAppData, validateWhatsAppConfig } = require("./lib/whatsapp.cjs");
const { sendTelegramTestMessage, validateProviderConfig, validateTelegramConfig } = require("./lib/integrations.cjs");
const { openWorkspacePath, revealWorkspacePath, validateWorkspaceRoot } = require("./lib/workspace.cjs");

let backendHandle = null;
let runtimeInfo = null;
let mainWindow = null;
const hasSingleInstanceLock = app.requestSingleInstanceLock();

function commandExistsLocal(candidate, args = ["--version"]) {
  try {
    const result = spawnSync(candidate, args, {
      stdio: "ignore",
      timeout: 3000,
    });
    return typeof result.status === "number";
  } catch {
    return false;
  }
}

function configOptions() {
  const info = runtimeInfo || {};
  return {
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  };
}

function loadCurrentConfig() {
  return loadDesktopConfig(configOptions());
}

function saveCurrentConfig(patch) {
  const saved = saveDesktopConfig(patch || {}, configOptions());
  runtimeInfo = { ...(runtimeInfo || {}), ...saved };
  return saved;
}

async function refreshBackendAfterConfigChange() {
  if (!runtimeInfo?.runtimePaths) {
    return null;
  }
  return ensureBackendRunning({ runtimePaths: runtimeInfo.runtimePaths, forceRestart: true });
}

async function reportDraftDispatch(pathname, payload) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const response = await fetch(`${runtimeInfo.apiBaseUrl}${pathname}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify(payload || {}),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(String(body?.detail || body?.message || "Gönderim sonucu kaydedilemedi."));
  }
  return body;
}

function travelReservationUrl(sourceContext, draft) {
  const context = sourceContext && typeof sourceContext === "object" ? sourceContext : {};
  const directUrl = String(context.booking_url || context.search_url || "").trim();
  if (directUrl) {
    return directUrl;
  }
  const sourceRefs = Array.isArray(context.source_refs) ? context.source_refs : [];
  for (const item of sourceRefs) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const url = String(item.url || item.href || "").trim();
    if (url) {
      return url;
    }
  }
  const queryParts = [
    String(context.query || "").trim(),
    String(draft?.subject || "").trim(),
    String(draft?.body || "").slice(0, 200).trim(),
  ].filter(Boolean);
  if (!queryParts.length) {
    return "";
  }
  return `https://www.google.com/travel/flights?q=${encodeURIComponent(queryParts.join(" "))}`;
}

async function dispatchApprovedAction(payload = {}) {
  const config = loadCurrentConfig();
  const draft = payload?.draft || {};
  const action = payload?.action || {};
  const draftId = Number(payload?.draftId || draft?.id || 0);
  const actionId = Number(payload?.actionId || action?.id || 0);
  const channel = String(payload?.channel || draft?.channel || action?.target_channel || "").trim().toLowerCase();
  const sourceContext = draft?.source_context || {};

  try {
    let result;
    if (channel === "email" || channel === "gmail") {
      result = await sendGmailMessage(config, {
        to: draft?.to_contact,
        subject: draft?.subject,
        body: draft?.body,
        threadId: sourceContext?.thread_id,
      });
    } else if (channel === "telegram") {
      result = await sendTelegramTestMessage({
        botToken: config.telegram?.botToken,
        allowedUserId: sourceContext?.recipient || draft?.to_contact || config.telegram?.allowedUserId,
        text: draft?.body,
      });
    } else if (channel === "whatsapp") {
      result = await sendWhatsAppMessage(config, {
        to: sourceContext?.recipient || draft?.to_contact,
        text: draft?.body,
      });
    } else if (channel === "x") {
      result = await postXUpdate(config, {
        text: draft?.body,
      });
      if (result?.patch) {
        saveCurrentConfig(result.patch);
      }
    } else if (channel === "travel") {
      const url = travelReservationUrl(sourceContext, draft);
      if (!url) {
        throw new Error("Seyahat rezervasyonu için açılacak bağlantı bulunamadı.");
      }
      await shell.openExternal(url);
      result = {
        ok: true,
        message: "Rezervasyon bağlantısı sistem tarayıcısında açıldı.",
        externalMessageId: url,
      };
    } else {
      throw new Error("Bu kanal için otomatik gönderim köprüsü bulunamadı.");
    }

    if (draftId) {
      await reportDraftDispatch(`/assistant/drafts/${draftId}/dispatch-complete`, {
        action_id: actionId || null,
        external_message_id: result?.externalMessageId || result?.messageId || result?.externalThreadId || "",
        note: result?.message || "Dış gönderim tamamlandı.",
      });
    } else if (actionId) {
      await reportDraftDispatch(`/assistant/actions/${actionId}/dispatch-complete`, {
        external_message_id: result?.externalMessageId || result?.messageId || result?.externalThreadId || "",
        note: result?.message || "Dış gönderim tamamlandı.",
      });
    }

    return {
      ok: true,
      channel,
      message: result?.message || "Gönderim tamamlandı.",
      externalMessageId: result?.externalMessageId || result?.messageId || result?.externalThreadId || "",
    };
  } catch (error) {
    const failureMessage = error instanceof Error ? error.message : "Dış gönderim tamamlanamadı.";
    if (draftId) {
      await reportDraftDispatch(`/assistant/drafts/${draftId}/dispatch-failed`, {
        action_id: actionId || null,
        error: failureMessage,
      }).catch(() => null);
    } else if (actionId) {
      await reportDraftDispatch(`/assistant/actions/${actionId}/dispatch-failed`, {
        error: failureMessage,
      }).catch(() => null);
    }
    throw error;
  }
}

async function openUrlPreferChrome(url) {
  const target = String(url || "").trim();
  if (!target) {
    throw new Error("Açılacak tarayıcı adresi bulunamadı.");
  }
  const candidates = process.platform === "darwin"
    ? [
        ["open", ["-a", "Google Chrome", target], "Google Chrome"],
      ]
    : process.platform === "win32"
      ? [
          ["cmd", ["/c", "start", "", "chrome", target], "Google Chrome"],
        ]
      : [
          ["google-chrome-stable", [target], "Google Chrome"],
          ["google-chrome", [target], "Google Chrome"],
          ["chromium-browser", [target], "Chromium"],
          ["chromium", [target], "Chromium"],
        ];

  for (const [command, args, label] of candidates) {
    if (process.platform === "linux" && !commandExistsLocal(command, ["--version"])) {
      continue;
    }
    try {
      const child = spawn(command, args, {
        detached: true,
        stdio: "ignore",
      });
      child.unref();
      return label;
    } catch {
      continue;
    }
  }
  await shell.openExternal(target);
  return "Sistem tarayıcısı";
}

async function bootRuntime() {
  const runtimePaths = resolveRuntimePaths({
    repoRoot: path.resolve(__dirname, "..", ".."),
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    userDataPath: app.getPath("userData"),
  });
  // Always refresh the local API process on app launch so the packaged app
  // never keeps talking to an older backend binary left alive on the same port.
  const info = await ensureBackendRunning({ runtimePaths, forceRestart: true });
  return { config: info, runtimePaths };
}

async function readHealth(apiBaseUrl) {
  try {
    const response = await fetch(`${apiBaseUrl}/health`);
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

function attachBackendExitWatcher(handle) {
  if (!handle?.child || handle.child.__lawcopilotExitWatcher) {
    return;
  }
  handle.child.__lawcopilotExitWatcher = true;
  handle.child.once("exit", () => {
    if (backendHandle?.child === handle.child) {
      backendHandle = null;
    }
  });
}

async function ensureBackendRunning(options = {}) {
  const runtimePaths = options.runtimePaths || resolveRuntimePaths({
    repoRoot: path.resolve(__dirname, "..", ".."),
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    userDataPath: app.getPath("userData"),
  });
  const config = loadDesktopConfig({ repoRoot: runtimePaths.repoRoot, storagePath: runtimePaths.artifactsRoot });
  if (options.forceRestart && backendHandle) {
    stopBackend(backendHandle);
    backendHandle = null;
  }
  let health = await readHealth(config.apiBaseUrl);
  const childExited = Boolean(backendHandle?.child && backendHandle.child.exitCode !== null);
  if (!health && (!backendHandle || childExited || options.forceRestart)) {
    backendHandle = startBackend(config, runtimePaths);
    attachBackendExitWatcher(backendHandle);
    health = await waitForBackend(config.apiBaseUrl);
  }
  if (!health) {
    throw new Error("backend_unreachable");
  }
  const sessionToken = (await createLawyerToken(config.apiBaseUrl)).access_token;
  runtimeInfo = {
    ...config,
    ...health,
    sessionToken,
    backendLogFile: backendHandle?.outFile || runtimeInfo?.backendLogFile || "",
    runtimePaths
  };
  await syncWorkspaceConfig({ ...config, sessionToken });
  return runtimeInfo;
}

async function syncWorkspaceConfig(config) {
  if (!config.workspaceRootPath) {
    return;
  }
  try {
    const token = config.sessionToken || (await createLawyerToken(config.apiBaseUrl)).access_token;
    await fetch(`${config.apiBaseUrl}/workspace`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        root_path: config.workspaceRootPath,
        display_name: config.workspaceRootName || path.basename(config.workspaceRootPath),
      }),
    });
    if (config.scanOnStartup) {
      await fetch(`${config.apiBaseUrl}/workspace/scan`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ full_rescan: false }),
      });
    }
  } catch {
    return;
  }
}

async function createLawyerToken(apiBaseUrl) {
  const response = await fetch(`${apiBaseUrl}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject: "desktop-runtime", role: "lawyer" }),
  });
  if (!response.ok) {
    throw new Error(`token_bootstrap_failed:${response.status}`);
  }
  return response.json();
}

async function createWindow(runtimePaths) {
  const window = new BrowserWindow({
    width: 1480,
    height: 980,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#102123",
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      preload: path.join(__dirname, "preload.cjs")
    }
  });
  const entryFile = path.join(runtimePaths.uiDist, "index.html");
  await window.loadFile(entryFile);
  window.once("ready-to-show", () => window.show());
  mainWindow = window;
  return window;
}

app.disableHardwareAcceleration();
if (!hasSingleInstanceLock) {
  app.quit();
}
app.on("second-instance", () => {
  if (!mainWindow) {
    return;
  }
  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  mainWindow.focus();
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  const { runtimePaths } = await bootRuntime();
  if (process.env.LAWCOPILOT_DESKTOP_SMOKE === "1") {
    setTimeout(() => app.quit(), 250);
    return;
  }
  await createWindow(runtimePaths);
});

app.on("before-quit", () => {
  stopBackend(backendHandle);
});

ipcMain.handle("lawcopilot:get-runtime-info", async () => {
  if (!runtimeInfo) {
    return null;
  }
  const sanitized = sanitizeDesktopConfig(runtimeInfo);
  return {
    ...sanitized,
    sessionToken: runtimeInfo.sessionToken,
    backendLogFile: runtimeInfo.backendLogFile,
    runtimePaths: runtimeInfo.runtimePaths,
    default_model_profile: runtimeInfo.default_model_profile,
  };
});
ipcMain.handle("lawcopilot:ensure-backend", async (_event, options) => {
  const info = await ensureBackendRunning({ forceRestart: Boolean(options?.forceRestart) });
  const sanitized = sanitizeDesktopConfig(info);
  return {
    ...sanitized,
    sessionToken: info.sessionToken,
    backendLogFile: info.backendLogFile,
    runtimePaths: info.runtimePaths,
    default_model_profile: info.default_model_profile,
  };
});
ipcMain.handle("lawcopilot:get-desktop-config", async () => {
  const config = loadCurrentConfig();
  return sanitizeDesktopConfig(config);
});
ipcMain.handle("lawcopilot:save-desktop-config", async (_event, patch) => {
  const saved = saveCurrentConfig(patch || {});
  await refreshBackendAfterConfigChange().catch(() => null);
  return sanitizeDesktopConfig(saved);
});
ipcMain.handle("lawcopilot:get-integration-config", async () => {
  const config = loadCurrentConfig();
  return sanitizeDesktopConfig(config);
});
ipcMain.handle("lawcopilot:save-integration-config", async (_event, patch) => {
  const saved = saveCurrentConfig(patch || {});
  await refreshBackendAfterConfigChange().catch(() => null);
  return sanitizeDesktopConfig(saved);
});
ipcMain.handle("lawcopilot:validate-provider-config", async (_event, payload) => validateProviderConfig(payload || {}));
ipcMain.handle("lawcopilot:validate-telegram-config", async (_event, payload) => validateTelegramConfig(payload || {}));
ipcMain.handle("lawcopilot:get-codex-auth-status", async () => {
  const config = loadCurrentConfig();
  return getCodexAuthStatus(config);
});
ipcMain.handle("lawcopilot:start-codex-auth", async () => {
  const config = loadCurrentConfig();
  const status = await startCodexOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
  return status;
});
ipcMain.handle("lawcopilot:submit-codex-auth-callback", async (_event, callbackUrl) => {
  const config = loadCurrentConfig();
  const status = await submitCodexOAuthCallback(config, String(callbackUrl || ""));
  const saved = saveCurrentConfig({
    provider: {
      type: "openai-codex",
      authMode: "oauth",
      baseUrl: "oauth://openai-codex",
      model: status.selectedModel || config.provider?.model || "openai-codex/gpt-5.3-codex",
      apiKey: "",
      accountLabel: "OpenAI hesabı (Codex OAuth)",
      availableModels: status.availableModels || [],
      oauthConnected: Boolean(status.configured),
      oauthLastError: "",
      configuredAt: status.configured ? new Date().toISOString() : config.provider?.configuredAt || "",
      lastValidatedAt: new Date().toISOString(),
      validationStatus: status.configured ? "valid" : "invalid",
    },
  });
  return {
    status,
    config: sanitizeDesktopConfig(saved),
  };
});
ipcMain.handle("lawcopilot:cancel-codex-auth", async () => cancelCodexOAuth());
ipcMain.handle("lawcopilot:set-codex-model", async (_event, model) => {
  const config = loadCurrentConfig();
  const status = setCodexModel(config, String(model || ""));
  const saved = saveCurrentConfig({
    provider: {
      type: "openai-codex",
      authMode: "oauth",
      baseUrl: "oauth://openai-codex",
      model: status.selectedModel || String(model || ""),
      apiKey: "",
      accountLabel: "OpenAI hesabı (Codex OAuth)",
      availableModels: status.availableModels || [],
      oauthConnected: Boolean(status.configured),
      oauthLastError: status.error || "",
      configuredAt: config.provider?.configuredAt || new Date().toISOString(),
      lastValidatedAt: new Date().toISOString(),
      validationStatus: status.configured ? "valid" : "pending",
    },
  });
  return {
    status,
    config: sanitizeDesktopConfig(saved),
  };
});
ipcMain.handle("lawcopilot:get-google-auth-status", async () => {
  const config = loadCurrentConfig();
  const completed = consumeCompletedGoogleOAuth();
  if (completed?.status) {
    const saved = saveCurrentConfig({
      google: {
        enabled: true,
        accountLabel: completed.status.accountLabel,
        scopes: completed.status.scopes || [],
        oauthConnected: Boolean(completed.status.configured),
        oauthLastError: "",
        configuredAt: new Date().toISOString(),
        lastValidatedAt: new Date().toISOString(),
        validationStatus: completed.status.configured ? "valid" : "invalid",
        accessToken: completed.status.accessToken || "",
        refreshToken: completed.status.refreshToken || "",
        tokenType: completed.status.tokenType || "",
        expiryDate: completed.status.expiryDate || "",
      },
    });
    const refreshedRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
    if (completed.status.configured) {
      const syncResult = await syncGoogleData(saved, refreshedRuntime).catch(() => null);
      if (syncResult?.patch) {
        saveCurrentConfig(syncResult.patch);
      }
    }
    return getGoogleAuthStatus(loadCurrentConfig());
  }
  if (completed?.error) {
    return {
      ...getGoogleAuthStatus(config),
      authStatus: "hata",
      message: completed.error,
      error: completed.error,
    };
  }
  return getGoogleAuthStatus(config);
});
ipcMain.handle("lawcopilot:start-google-auth", async () => {
  const config = loadCurrentConfig();
  const status = await startGoogleOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
  return status;
});
ipcMain.handle("lawcopilot:submit-google-auth-callback", async (_event, callbackUrl) => {
  const config = loadCurrentConfig();
  const status = await submitGoogleOAuthCallback(config, String(callbackUrl || ""));
  const saved = saveCurrentConfig({
    google: {
      enabled: true,
      accountLabel: status.accountLabel,
      scopes: status.scopes || [],
      oauthConnected: Boolean(status.configured),
      oauthLastError: "",
      configuredAt: new Date().toISOString(),
      lastValidatedAt: new Date().toISOString(),
      validationStatus: status.configured ? "valid" : "invalid",
      accessToken: status.accessToken || "",
      refreshToken: status.refreshToken || "",
      tokenType: status.tokenType || "",
      expiryDate: status.expiryDate || "",
    },
  });
  await refreshBackendAfterConfigChange().catch(() => null);
  return {
    status,
    config: sanitizeDesktopConfig(saved),
  };
});
ipcMain.handle("lawcopilot:cancel-google-auth", async () => {
  const config = loadCurrentConfig();
  return cancelGoogleOAuth(config);
});
ipcMain.handle("lawcopilot:sync-google-data", async () => {
  const config = loadCurrentConfig();
  const currentRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
  const result = await syncGoogleData(config, currentRuntime);
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:send-gmail-message", async (_event, payload) => {
  const config = loadCurrentConfig();
  const result = await sendGmailMessage(config, payload || {});
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:create-google-calendar-event", async (_event, payload) => {
  const config = loadCurrentConfig();
  const result = await createGoogleCalendarEvent(config, runtimeInfo, payload || {});
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:get-whatsapp-status", async () => {
  const config = loadCurrentConfig();
  return getWhatsAppStatus(config);
});
ipcMain.handle("lawcopilot:validate-whatsapp-config", async (_event, payload) => validateWhatsAppConfig(payload || {}));
ipcMain.handle("lawcopilot:sync-whatsapp-data", async () => {
  const config = loadCurrentConfig();
  const currentRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
  const result = await syncWhatsAppData(config, currentRuntime);
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:send-whatsapp-message", async (_event, payload) => {
  const config = loadCurrentConfig();
  return sendWhatsAppMessage(config, payload || {});
});
ipcMain.handle("lawcopilot:get-x-auth-status", async () => {
  const config = loadCurrentConfig();
  return getXAuthStatus(config);
});
ipcMain.handle("lawcopilot:start-x-auth", async () => {
  const config = loadCurrentConfig();
  const status = await startXOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
  const saved = saveCurrentConfig({
    x: {
      enabled: true,
      accountLabel: status.accountLabel,
      userId: status.userId || "",
      scopes: status.scopes || [],
      oauthConnected: Boolean(status.configured),
      oauthLastError: "",
      configuredAt: new Date().toISOString(),
      lastValidatedAt: new Date().toISOString(),
      validationStatus: status.configured ? "valid" : "invalid",
      accessToken: status.accessToken || "",
      refreshToken: status.refreshToken || "",
      tokenType: status.tokenType || "",
      expiryDate: status.expiryDate || "",
    },
  });
  const refreshedRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
  if (status.configured) {
    const syncResult = await syncXData(saved, refreshedRuntime).catch(() => null);
    if (syncResult?.patch) {
      saveCurrentConfig(syncResult.patch);
    }
  }
  return status;
});
ipcMain.handle("lawcopilot:cancel-x-auth", async () => {
  const config = loadCurrentConfig();
  return cancelXOAuth(config);
});
ipcMain.handle("lawcopilot:sync-x-data", async () => {
  const config = loadCurrentConfig();
  const currentRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
  const result = await syncXData(config, currentRuntime);
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:post-x-update", async (_event, payload) => {
  const config = loadCurrentConfig();
  const result = await postXUpdate(config, payload || {});
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:dispatch-approved-action", async (_event, payload) => dispatchApprovedAction(payload || {}));
ipcMain.handle("lawcopilot:send-telegram-test-message", async (_event, payload) => {
  const current = loadCurrentConfig();
  const merged = {
    ...(current.telegram || {}),
    ...(payload || {}),
  };
  return sendTelegramTestMessage(merged);
});
ipcMain.handle("lawcopilot:choose-workspace-root", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Çalışma klasörünü seçin",
    properties: ["openDirectory", "createDirectory"],
  });
  if (result.canceled || !result.filePaths[0]) {
    return { canceled: true };
  }
  const validated = validateWorkspaceRoot(result.filePaths[0]);
  const info = runtimeInfo || {};
  const saved = saveDesktopConfig(
    {
      workspaceRootPath: validated.rootPath,
      workspaceRootName: validated.displayName,
      workspaceRootHash: validated.rootHash,
    },
    {
      repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
      storagePath: info.runtimePaths?.artifactsRoot,
    },
  );
  runtimeInfo = { ...(runtimeInfo || {}), ...saved };
  await syncWorkspaceConfig(runtimeInfo);
  return { canceled: false, workspace: sanitizeDesktopConfig(saved) };
});
ipcMain.handle("lawcopilot:get-workspace-config", async () => {
  const config = loadCurrentConfig();
  return {
    workspaceRootPath: config.workspaceRootPath,
    workspaceRootName: config.workspaceRootName,
    workspaceRootHash: config.workspaceRootHash,
    scanOnStartup: config.scanOnStartup,
    locale: config.locale,
  };
});
ipcMain.handle("lawcopilot:save-workspace-config", async (_event, patch) => {
  const saved = saveCurrentConfig(patch || {});
  if (saved.workspaceRootPath) {
    await syncWorkspaceConfig(runtimeInfo);
  }
  return sanitizeDesktopConfig(saved);
});
ipcMain.handle("lawcopilot:open-path", async (_event, relativePath) => {
  const config = loadCurrentConfig();
  return openWorkspacePath(config, String(relativePath || ""));
});
ipcMain.handle("lawcopilot:reveal-path", async (_event, relativePath) => {
  const config = loadCurrentConfig();
  return revealWorkspacePath(config, String(relativePath || ""));
});
