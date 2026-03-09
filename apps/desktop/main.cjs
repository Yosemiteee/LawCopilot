const path = require("path");
const { app, BrowserWindow, dialog, ipcMain } = require("electron");

const { loadDesktopConfig, resolveRuntimePaths, sanitizeDesktopConfig, saveDesktopConfig } = require("./lib/config.cjs");
const { startBackend, stopBackend, waitForBackend } = require("./lib/backend.cjs");
const { sendTelegramTestMessage, validateProviderConfig, validateTelegramConfig } = require("./lib/integrations.cjs");
const { openWorkspacePath, revealWorkspacePath, validateWorkspaceRoot } = require("./lib/workspace.cjs");

let backendHandle = null;
let runtimeInfo = null;
let mainWindow = null;

async function bootRuntime() {
  const runtimePaths = resolveRuntimePaths({
    repoRoot: path.resolve(__dirname, "..", ".."),
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    userDataPath: app.getPath("userData"),
  });
  const config = loadDesktopConfig({ repoRoot: runtimePaths.repoRoot, storagePath: runtimePaths.artifactsRoot });
  backendHandle = startBackend(config, runtimePaths);
  const health = await waitForBackend(config.apiBaseUrl, 15000);
  const sessionToken = (await createLawyerToken(config.apiBaseUrl)).access_token;
  runtimeInfo = {
    ...config,
    ...health,
    sessionToken,
    backendLogFile: backendHandle.outFile,
    runtimePaths
  };
  await syncWorkspaceConfig({ ...config, sessionToken });
  return { config, runtimePaths };
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
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.whenReady().then(async () => {
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
ipcMain.handle("lawcopilot:get-desktop-config", async () => {
  const info = runtimeInfo || {};
  const config = loadDesktopConfig({
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  });
  return sanitizeDesktopConfig(config);
});
ipcMain.handle("lawcopilot:save-desktop-config", async (_event, patch) => {
  const info = runtimeInfo || {};
  const saved = saveDesktopConfig(patch || {}, {
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  });
  runtimeInfo = { ...(runtimeInfo || {}), ...saved };
  return sanitizeDesktopConfig(saved);
});
ipcMain.handle("lawcopilot:get-integration-config", async () => {
  const info = runtimeInfo || {};
  const config = loadDesktopConfig({
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  });
  return sanitizeDesktopConfig(config);
});
ipcMain.handle("lawcopilot:save-integration-config", async (_event, patch) => {
  const info = runtimeInfo || {};
  const saved = saveDesktopConfig(patch || {}, {
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  });
  runtimeInfo = { ...(runtimeInfo || {}), ...saved };
  return sanitizeDesktopConfig(saved);
});
ipcMain.handle("lawcopilot:validate-provider-config", async (_event, payload) => validateProviderConfig(payload || {}));
ipcMain.handle("lawcopilot:validate-telegram-config", async (_event, payload) => validateTelegramConfig(payload || {}));
ipcMain.handle("lawcopilot:send-telegram-test-message", async (_event, payload) => {
  const info = runtimeInfo || {};
  const current = loadDesktopConfig({
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  });
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
  const info = runtimeInfo || {};
  const config = loadDesktopConfig({
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  });
  return {
    workspaceRootPath: config.workspaceRootPath,
    workspaceRootName: config.workspaceRootName,
    workspaceRootHash: config.workspaceRootHash,
    scanOnStartup: config.scanOnStartup,
    locale: config.locale,
  };
});
ipcMain.handle("lawcopilot:save-workspace-config", async (_event, patch) => {
  const info = runtimeInfo || {};
  const saved = saveDesktopConfig(patch || {}, {
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  });
  runtimeInfo = { ...(runtimeInfo || {}), ...saved };
  if (saved.workspaceRootPath) {
    await syncWorkspaceConfig(runtimeInfo);
  }
  return sanitizeDesktopConfig(saved);
});
ipcMain.handle("lawcopilot:open-path", async (_event, relativePath) => {
  const info = runtimeInfo || {};
  const config = loadDesktopConfig({
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  });
  return openWorkspacePath(config, String(relativePath || ""));
});
ipcMain.handle("lawcopilot:reveal-path", async (_event, relativePath) => {
  const info = runtimeInfo || {};
  const config = loadDesktopConfig({
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  });
  return revealWorkspacePath(config, String(relativePath || ""));
});
