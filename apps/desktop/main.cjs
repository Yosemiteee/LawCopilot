const fs = require("fs");
const net = require("net");
const os = require("os");
const path = require("path");
const { spawn, spawnSync } = require("child_process");
const { app, BrowserWindow, dialog, ipcMain, Menu, Notification, safeStorage, screen, shell } = require("electron");

const {
  defaultAutomationConfig,
  loadDesktopConfig,
  normalizeAutomationConfigForWrite,
  resolveConfigDir,
  resolveRuntimePaths,
  sanitizeDesktopConfig,
  saveDesktopConfig,
} = require("./lib/config.cjs");
const {
  appendBackendLog,
  backendPidFile,
  clearPidFile,
  isManagedBackendPid,
  listeningPids,
  parseEnvFile,
  startBackend,
  stopBackend,
  stopBackendOnPort,
  waitForBackend,
  writePidFile,
} = require("./lib/backend.cjs");
const { cancelCodexOAuth, getCodexAuthStatus, setCodexModel, startCodexOAuth, submitCodexOAuthCallback } = require("./lib/codex-oauth.cjs");
const { cancelGoogleOAuth, consumeCompletedGoogleOAuth, getGoogleAuthStatus, startGoogleOAuth, submitGoogleOAuthCallback } = require("./lib/google-oauth.cjs");
const {
  cancelGooglePortabilityOAuth,
  consumeCompletedGooglePortabilityOAuth,
  getGooglePortabilityAuthStatus,
  startGooglePortabilityOAuth,
  submitGooglePortabilityOAuthCallback,
} = require("./lib/google-portability.cjs");
const { createGoogleCalendarEvent, importGoogleTakeoutData, sendGmailMessage, syncGoogleData, syncGooglePortabilityData } = require("./lib/google-data.cjs");
const { cancelOutlookOAuth, getOutlookAuthStatus, startOutlookOAuth } = require("./lib/outlook-oauth.cjs");
const { syncOutlookData } = require("./lib/outlook-data.cjs");
const { cancelXOAuth, getXAuthStatus, startXOAuth } = require("./lib/x-oauth.cjs");
const { postXUpdate, sendXDirectMessage, syncXData } = require("./lib/x-api.cjs");
const { cancelLinkedInOAuth, getLinkedInAuthStatus, startLinkedInOAuth } = require("./lib/linkedin-oauth.cjs");
const {
  getLinkedInStatus,
  postLinkedInUpdate,
  sendLinkedInWebMessage,
  setLinkedInWebBridgeContext,
  startLinkedInWebLink,
  syncLinkedInData,
} = require("./lib/linkedin-api.cjs");
const { cancelInstagramOAuth, getInstagramAuthStatus, startInstagramOAuth } = require("./lib/instagram-oauth.cjs");
const { sendInstagramMessage, syncInstagramData } = require("./lib/instagram-api.cjs");
const {
  connectWhatsAppWeb,
  disconnectWhatsApp,
  getWhatsAppStatus,
  sendWhatsAppMessage,
  setWhatsAppWebBridgeContext,
  syncWhatsAppData,
  validateWhatsAppConfig,
} = require("./lib/whatsapp.cjs");
const {
  getTelegramStatus,
  sendTelegramTestMessage,
  sendTelegramWebMessage,
  setTelegramWebBridgeContext,
  startTelegramWebLink,
  syncTelegramData,
  validateProviderConfig,
  validateTelegramConfig,
} = require("./lib/integrations.cjs");
const { loadSecretConfig, mergeSecretConfig, saveSecretConfig, splitSecretConfigPatch } = require("./lib/secret-store.cjs");
const { createDesktopUpdater } = require("./lib/updater.cjs");
const { providerDefaults } = require("./lib/provider-model-catalog.cjs");
const { openWorkspacePath, revealWorkspacePath, validateWorkspaceRoot } = require("./lib/workspace.cjs");

const shouldDisableGpu =
  process.env.LAWCOPILOT_DISABLE_GPU === "1"
  || (process.env.LAWCOPILOT_DISABLE_GPU !== "0" && process.platform === "linux");
const isDesktopSmoke = process.env.LAWCOPILOT_DESKTOP_SMOKE === "1";

if (shouldDisableGpu) {
  app.disableHardwareAcceleration();
  app.commandLine.appendSwitch("disable-gpu");
  app.commandLine.appendSwitch("disable-gpu-compositing");
}
if (isDesktopSmoke) {
  app.commandLine.appendSwitch("no-sandbox");
  app.commandLine.appendSwitch("disable-setuid-sandbox");
  app.commandLine.appendSwitch("disable-dev-shm-usage");
}

let backendHandle = null;
let runtimeInfo = null;
let mainWindow = null;
let mainWindowPromise = null;
let checkoutWindow = null;
let automationInterval = null;
let reminderAutomationInterval = null;
let automationKickTimer = null;
let automationInFlight = false;
let backendRefreshPromise = null;
let backendEnsurePromise = null;
let googlePostAuthSyncPromise = null;
let googlePortabilityPostAuthSyncPromise = null;
let desktopUpdater = null;
let connectedServicesSyncInterval = null;
let connectedServicesSyncInFlight = false;
const startupLogRoot = app && typeof app.getPath === "function" ? app.getPath("temp") : os.tmpdir();
const startupLogFile = String(process.env.LAWCOPILOT_DESKTOP_MAIN_LOG || "").trim()
  ? path.resolve(String(process.env.LAWCOPILOT_DESKTOP_MAIN_LOG || "").trim())
  : path.join(startupLogRoot, "lawcopilot-desktop-main.log");
const desktopBootStartedAt = Date.now();
const AUTOMATION_REQUEST_TIMEOUT_MS = Number(process.env.LAWCOPILOT_AUTOMATION_REQUEST_TIMEOUT_MS || 15000);
const DESKTOP_SMOKE_HOLD_MS = Number(process.env.LAWCOPILOT_DESKTOP_SMOKE_HOLD_MS || 250);
const DEFAULT_FOLLOW_UP_REMINDER_HOURS = 24;
const DEFAULT_CALENDAR_REMINDER_LEAD_MINUTES = 30;
const AUTOMATION_RULES_FILE_NAME = "HEARTBEAT-AUTOMATIONS.md";
const WHATSAPP_AUTOSTART_DELAY_MS = Number(process.env.LAWCOPILOT_WHATSAPP_AUTOSTART_DELAY_MS || 10000);
const CONNECTED_SERVICES_SYNC_INTERVAL_MS = Number(process.env.LAWCOPILOT_CONNECTED_SERVICES_SYNC_INTERVAL_MS || 60000);
const REMINDER_AUTOMATION_INTERVAL_MS = Number(process.env.LAWCOPILOT_REMINDER_AUTOMATION_INTERVAL_MS || 10000);
const BACKEND_HEALTH_POLL_MS = Number(process.env.LAWCOPILOT_BACKEND_HEALTH_POLL_MS || 5000);
const BACKEND_HEALTH_FAILURE_THRESHOLD = Number(process.env.LAWCOPILOT_BACKEND_HEALTH_FAILURE_THRESHOLD || 2);
const BACKEND_RECOVERY_BASE_DELAY_MS = Number(process.env.LAWCOPILOT_BACKEND_RECOVERY_BASE_DELAY_MS || 750);
const BACKEND_RECOVERY_MAX_DELAY_MS = Number(process.env.LAWCOPILOT_BACKEND_RECOVERY_MAX_DELAY_MS || 15000);

function logStartup(event, detail = "") {
  const elapsedMs = Math.max(0, Date.now() - desktopBootStartedAt);
  const message = `[${new Date().toISOString()} +${elapsedMs}ms] ${String(event || "").trim()} ${String(detail || "").trim()}`.trim();
  try {
    fs.appendFileSync(startupLogFile, `${message}\n`, { encoding: "utf-8" });
  } catch {
    return;
  }
}

let backendHealthInterval = null;
let backendHealthProbeInFlight = false;
let backendConsecutiveHealthFailures = 0;
let backendRecoveryTimer = null;
let backendRecoveryPromise = null;
let backendRecoveryAttempts = 0;
let backendPlannedRestartDepth = 0;
let appQuitInFlight = false;
let quitCleanupPromise = null;
let desktopSpeechProcess = null;
let desktopSpeechWaiter = null;

function hasRunningLawCopilotInstance() {
  try {
    const result = spawnSync("pgrep", ["-af", "lawcopilot-desktop"], {
      encoding: "utf-8",
      timeout: 2000,
    });
    const currentPid = Number(process.pid || 0);
    const lines = String(result.stdout || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    return lines.some((line) => {
      const pid = Number.parseInt(line.split(/\s+/, 1)[0] || "", 10);
      return Number.isFinite(pid) && pid > 0 && pid !== currentPid;
    });
  } catch {
    return false;
  }
}

function runtimeStatePaths(runtimePaths, storagePathOverride = "") {
  const artifactsRoot = String(storagePathOverride || runtimePaths?.artifactsRoot || "").trim();
  if (!artifactsRoot) {
    return { runtimeDir: "", desktopPidFile: "", backendPidFile: "" };
  }
  const runtimeDir = path.join(artifactsRoot, "runtime");
  try {
    fs.mkdirSync(runtimeDir, { recursive: true, mode: 0o700 });
  } catch {}
  return {
    runtimeDir,
    desktopPidFile: path.join(runtimeDir, "desktop-main.pid"),
    backendPidFile: backendPidFile(runtimePaths, artifactsRoot),
  };
}

function persistDesktopPid(runtimePaths, storagePathOverride = "") {
  const paths = runtimeStatePaths(runtimePaths, storagePathOverride);
  if (!paths.desktopPidFile) {
    return;
  }
  writePidFile(paths.desktopPidFile, process.pid, {
    app_version: app.getVersion ? app.getVersion() : "",
    config_dir: resolveConfigDir(),
    is_packaged: Boolean(app.isPackaged),
    smoke_mode: Boolean(isDesktopSmoke),
  });
}

function clearRuntimePidFiles(runtimePaths, storagePathOverride = "") {
  const paths = runtimeStatePaths(runtimePaths || runtimeInfo?.runtimePaths || {}, storagePathOverride || runtimeInfo?.storagePath || "");
  clearPidFile(paths.desktopPidFile, process.pid);
  clearPidFile(paths.backendPidFile, backendHandle?.child?.pid || null);
}

function clearBackendRecoveryTimer() {
  if (backendRecoveryTimer) {
    clearTimeout(backendRecoveryTimer);
    backendRecoveryTimer = null;
  }
}

function stopBackendHealthMonitor() {
  if (backendHealthInterval) {
    clearInterval(backendHealthInterval);
    backendHealthInterval = null;
  }
  backendHealthProbeInFlight = false;
  backendConsecutiveHealthFailures = 0;
}

logStartup(
  "desktop_boot",
  `pid=${process.pid} smoke=${String(isDesktopSmoke)} configDir=${resolveConfigDir()}`,
);
const hasSingleInstanceLock = app.requestSingleInstanceLock();
const singleInstanceFallbackAllowed =
  !hasSingleInstanceLock
  && (
    isDesktopSmoke
    || String(process.env.LAWCOPILOT_ALLOW_STALE_LOCK_FALLBACK || "").trim() === "1"
  )
  && !hasRunningLawCopilotInstance();
logStartup(
  "single_instance_lock",
  `granted=${String(hasSingleInstanceLock)} fallback=${String(singleInstanceFallbackAllowed)}`,
);
const startupSuppressed = !hasSingleInstanceLock && !singleInstanceFallbackAllowed;

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

function parseDesktopTtsVoices(output) {
  return String(output || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^(.+?)\s{2,}([a-z]{2,}(?:[-_][A-Za-z0-9]+)?)\s{2,}(.+)$/i);
      if (!match) {
        return null;
      }
      const [, name, lang] = match;
      const normalizedName = String(name || "").trim();
      const normalizedLang = String(lang || "").trim().toLowerCase();
      if (!normalizedName) {
        return null;
      }
      return {
        id: `desktop:${normalizedName}`,
        name: normalizedName,
        lang: normalizedLang || "tr",
      };
    })
    .filter(Boolean);
}

function getDesktopTtsVoices() {
  if (!commandExistsLocal("spd-say", ["-L"])) {
    return [];
  }
  try {
    const result = spawnSync("spd-say", ["-L"], {
      encoding: "utf-8",
      timeout: 5000,
    });
    return parseDesktopTtsVoices(result.stdout);
  } catch {
    return [];
  }
}

function stopDesktopSpeech() {
  const child = desktopSpeechProcess;
  desktopSpeechProcess = null;
  if (!child) {
    return { ok: true, stopped: false };
  }
  try {
    child.kill("SIGTERM");
  } catch {}
  return { ok: true, stopped: true };
}

async function speakDesktopText(payload = {}) {
  const text = String(payload.text || "").trim();
  if (!text) {
    return { ok: false, error: "empty_text" };
  }
  if (!commandExistsLocal("spd-say", ["-L"])) {
    return { ok: false, error: "spd_say_missing" };
  }
  stopDesktopSpeech();
  const requestedVoice = String(payload.voiceId || "").trim();
  const voiceName = requestedVoice.startsWith("desktop:") ? requestedVoice.slice("desktop:".length).trim() : "";
  const args = ["-w"];
  if (voiceName) {
    args.push("-y", voiceName);
  } else {
    args.push("-l", "tr");
  }
  args.push(text.slice(0, 4000));
  return new Promise((resolve) => {
    let settled = false;
    try {
      const child = spawn("spd-say", args, {
        stdio: "ignore",
      });
      desktopSpeechProcess = child;
      desktopSpeechWaiter = child;
      const finalize = (result) => {
        if (settled) {
          return;
        }
        settled = true;
        if (desktopSpeechProcess === child) {
          desktopSpeechProcess = null;
        }
        if (desktopSpeechWaiter === child) {
          desktopSpeechWaiter = null;
        }
        resolve(result);
      };
      child.once("error", (error) => {
        finalize({ ok: false, error: String(error?.message || "spawn_failed") });
      });
      child.once("exit", (code, signal) => {
        finalize({
          ok: !signal && Number(code || 0) === 0,
          code: Number.isFinite(code) ? code : null,
          signal: signal || null,
          stopped: Boolean(signal),
        });
      });
    } catch (error) {
      resolve({ ok: false, error: String(error?.message || "spawn_failed") });
    }
  });
}

function configOptions() {
  const info = runtimeInfo || {};
  return {
    repoRoot: info.runtimePaths?.repoRoot || path.resolve(__dirname, "..", ".."),
    storagePath: info.runtimePaths?.artifactsRoot,
  };
}

function normalizeConfigPatchSecrets(patch, currentConfig) {
  const next = JSON.parse(JSON.stringify(patch || {}));
  if (next.provider && typeof next.provider === "object") {
    const nextType = String(next.provider.type || currentConfig?.provider?.type || "").trim();
    const currentType = String(currentConfig?.provider?.type || "").trim();
    const hasApiKeyField = Object.prototype.hasOwnProperty.call(next.provider, "apiKey");
    if ((!hasApiKeyField && nextType && currentType && nextType !== currentType) || String(next.provider.authMode || "").trim() === "oauth") {
      next.provider.apiKey = "";
    }
  }
  return next;
}

function migrateLegacySecrets(rawConfig, options) {
  const { secretPatch, publicPatch } = splitSecretConfigPatch(rawConfig || {});
  const hasLegacySecrets = Boolean(Object.keys(secretPatch || {}).length);
  if (!hasLegacySecrets || !safeStorage?.isEncryptionAvailable?.()) {
    return rawConfig;
  }
  const existingSecrets = loadSecretConfig(options, { safeStorage });
  const mergedSecrets = mergeSecretConfig(existingSecrets, secretPatch);
  saveSecretConfig(mergedSecrets, options, { safeStorage });
  saveDesktopConfig(publicPatch, options);
  return mergeSecretConfig(publicPatch, mergedSecrets);
}

function loadCurrentConfig(optionsOverride = {}) {
  const options = { ...configOptions(), ...optionsOverride };
  const rawConfig = loadDesktopConfig(options);
  const migratedConfig = migrateLegacySecrets(rawConfig, options);
  const secretConfig = loadSecretConfig(options, { safeStorage });
  return mergeSecretConfig(migratedConfig, secretConfig);
}

function saveCurrentConfig(patch, optionsOverride = {}) {
  const options = { ...configOptions(), ...optionsOverride };
  const current = loadCurrentConfig(options);
  const normalizedPatch = normalizeConfigPatchSecrets(patch, current);
  const { secretPatch, publicPatch } = splitSecretConfigPatch(normalizedPatch || {});
  const savedPublic = saveDesktopConfig(publicPatch || {}, options);
  if (Object.keys(secretPatch || {}).length) {
    saveSecretConfig(secretPatch, options, { safeStorage });
  }
  const saved = mergeSecretConfig(savedPublic, loadSecretConfig(options, { safeStorage }));
  runtimeInfo = { ...(runtimeInfo || {}), ...saved };
  syncAutomationArtifact(saved);
  return saved;
}

async function refreshBackendAfterConfigChange() {
  if (!runtimeInfo?.runtimePaths) {
    return null;
  }
  const config = loadCurrentConfig({
    repoRoot: runtimeInfo.runtimePaths.repoRoot,
    storagePath: runtimeInfo.storagePath || runtimeInfo.runtimePaths.artifactsRoot,
  });
  const nextFingerprint = backendConfigFingerprint(config);
  const currentFingerprint = String(runtimeInfo.backendConfigFingerprint || "").trim();
  const childAlive = Boolean(backendHandle?.child && backendHandle.child.exitCode === null);
  if (childAlive && nextFingerprint && currentFingerprint === nextFingerprint) {
    const health = await readHealth(runtimeInfo.apiBaseUrl).catch(() => null);
    if (health) {
      runtimeInfo = {
        ...(runtimeInfo || {}),
        ...config,
        ...health,
        backendConfigFingerprint: nextFingerprint,
      };
      logStartup("backend_refresh_skipped", "reason=fingerprint_match");
      return runtimeInfo;
    }
  }
  return ensureBackendRunning({ runtimePaths: runtimeInfo.runtimePaths, forceRestart: true });
}

function backendRefreshNotice() {
  return "Değişiklik kaydedildi. Arka plan servisleri yenilendi.";
}

function backendRefreshFailureMessage(error) {
  const raw = String(error?.message || error || "").trim().toLowerCase();
  if (raw.includes("backend_port_in_use")) {
    return "Arka plan servisi başlatılamadı. Kullandığı port başka bir uygulama tarafından tutuluyor.";
  }
  if (raw.includes("secure_storage_unavailable")) {
    return "Bu cihazda güvenli anahtar saklama hazır değil. Model veya hesap anahtarı kaydedilemedi.";
  }
  if (raw.includes("backend_unreachable")) {
    return "Arka plan servisi yeniden başlatılamadı. Ayar geri alındı; uygulamayı tekrar deneyin.";
  }
  return "Ayar kaydedilemedi. Arka plan servisi güvenli şekilde yenilenemedi.";
}

function ensureDesktopUpdater() {
  if (desktopUpdater) {
    return desktopUpdater;
  }
  desktopUpdater = createDesktopUpdater({
    app,
    loadConfig: () => loadCurrentConfig(),
    saveConfig: (patch) => saveCurrentConfig(patch || {}),
    getMainWindow: () => mainWindow,
    notify: (title, body) => notifyDesktop(title, body),
    log: (event, detail = "") => logStartup(`updater_${event}`, String(detail || "")),
  });
  return desktopUpdater;
}

async function saveConfigWithRefresh(patch, optionsOverride = {}) {
  const options = { ...configOptions(), ...optionsOverride };
  const previous = loadCurrentConfig(options);
  const saved = saveCurrentConfig(patch || {}, options);
  if (!patchRequiresBackendRefresh(patch)) {
    return { saved, runtimeWarning: "" };
  }
  if (backendRefreshPromise) {
    await backendRefreshPromise;
  }
  backendRefreshPromise = refreshBackendAfterConfigChange()
    .catch(async (error) => {
      console.error("[lawcopilot] backend_refresh_failed", error);
      try {
        saveCurrentConfig(previous, options);
        await refreshBackendAfterConfigChange();
      } catch (rollbackError) {
        console.error("[lawcopilot] backend_refresh_rollback_failed", rollbackError);
      }
      throw new Error(backendRefreshFailureMessage(error));
    })
    .finally(() => {
      backendRefreshPromise = null;
    });
  await backendRefreshPromise;
  return {
    saved: loadCurrentConfig(options),
    runtimeWarning: backendRefreshNotice(),
  };
}

function saveConfigWithoutRefresh(patch, optionsOverride = {}) {
  const options = { ...configOptions(), ...optionsOverride };
  const saved = saveCurrentConfig(patch || {}, options);
  return {
    saved,
    runtimeWarning: "",
  };
}

async function activateCodexProviderFromOAuthStatus(options = {}) {
  const config = loadCurrentConfig();
  const status = await getCodexAuthStatus(config);
  if (!status?.configured) {
    return { changed: false, status, config };
  }
  const currentProvider = config?.provider && typeof config.provider === "object" ? config.provider : {};
  const codexDefaults = providerDefaults("openai-codex");
  const needsActivation = (
    String(currentProvider.type || "") !== "openai-codex"
    || String(currentProvider.authMode || "") !== "oauth"
    || String(currentProvider.baseUrl || "") !== "oauth://openai-codex"
    || !currentProvider.oauthConnected
    || String(currentProvider.validationStatus || "") !== "valid"
  );
  if (!needsActivation) {
    return { changed: false, status, config };
  }
  const saved = saveCurrentConfig({
    provider: {
      type: "openai-codex",
      authMode: "oauth",
      baseUrl: "oauth://openai-codex",
      model: status.selectedModel || currentProvider.model || codexDefaults.model,
      apiKey: "",
      accountLabel: "OpenAI hesabı (Codex OAuth)",
      availableModels: status.catalogModels || status.availableModels || [],
      oauthConnected: true,
      oauthLastError: "",
      configuredAt: currentProvider.configuredAt || new Date().toISOString(),
      lastValidatedAt: new Date().toISOString(),
      validationStatus: "valid",
    },
  });
  if (options.refreshBackend !== false && runtimeInfo?.runtimePaths) {
    await refreshBackendAfterConfigChange().catch((error) => {
      console.error("[lawcopilot] codex_provider_activation_refresh_failed", error);
    });
  }
  return { changed: true, status, config: saved };
}

function scheduleGooglePostAuthSync(savedConfig) {
  if (googlePostAuthSyncPromise) {
    return googlePostAuthSyncPromise;
  }
  googlePostAuthSyncPromise = (async () => {
    const refreshedRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
    if (savedConfig?.google?.oauthConnected) {
      const syncResult = await syncGoogleData(savedConfig, refreshedRuntime).catch(() => null);
      if (syncResult?.patch) {
        saveCurrentConfig(syncResult.patch);
      }
    }
  })()
    .catch((error) => {
      console.error("[lawcopilot] google_post_auth_sync_failed", error);
    })
    .finally(() => {
      googlePostAuthSyncPromise = null;
    });
  return googlePostAuthSyncPromise;
}

function scheduleGooglePortabilityPostAuthSync(savedConfig) {
  if (googlePortabilityPostAuthSyncPromise) {
    return googlePortabilityPostAuthSyncPromise;
  }
  googlePortabilityPostAuthSyncPromise = (async () => {
    const refreshedRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
    if (savedConfig?.googlePortability?.oauthConnected) {
      const syncResult = await syncGooglePortabilityData(savedConfig, refreshedRuntime).catch(() => null);
      if (syncResult?.patch) {
        saveCurrentConfig(syncResult.patch);
      }
    }
  })()
    .catch((error) => {
      console.error("[lawcopilot] google_portability_post_auth_sync_failed", error);
    })
    .finally(() => {
      googlePortabilityPostAuthSyncPromise = null;
    });
  return googlePortabilityPostAuthSyncPromise;
}

async function runProviderSync(providerKey, task, timeoutCode, options = {}) {
  const errorField = String(options.errorField || "").trim();
  const timestamp = new Date().toISOString();
  try {
    const result = await withTimeout(task, AUTOMATION_REQUEST_TIMEOUT_MS, timeoutCode);
    const providerPatch = {
      ...((result?.patch && result.patch[providerKey]) || {}),
      lastValidatedAt: timestamp,
      validationStatus: "valid",
    };
    if (errorField) {
      providerPatch[errorField] = "";
    }
    const patch = result?.patch
      ? { ...result.patch, [providerKey]: providerPatch }
      : { [providerKey]: providerPatch };
    saveCurrentConfig(patch);
    return { ...(result || {}), ok: result?.ok !== false, patch };
  } catch (error) {
    const message = String(error?.message || error || "Senkron başarısız.");
    console.error(`[lawcopilot] ${providerKey}_sync_failed`, error);
    const providerPatch = {
      lastValidatedAt: timestamp,
      validationStatus: "invalid",
    };
    if (errorField) {
      providerPatch[errorField] = message;
    }
    const patch = { [providerKey]: providerPatch };
    saveCurrentConfig(patch);
    return { ok: false, error: message, patch };
  }
}

async function saveLocationSnapshot(payload) {
  const info = runtimeInfo || (await ensureBackendRunning({ forceRestart: false }).catch(() => null));
  const artifactsRoot = info?.runtimePaths?.artifactsRoot || path.resolve(__dirname, "..", "..", "artifacts");
  const snapshotDir = path.join(artifactsRoot, "runtime", "location");
  const snapshotPath = path.join(snapshotDir, "context.json");
  const observedAt = String(payload?.observed_at || "").trim() || new Date().toISOString();
  const normalized = {
    current_place: payload?.current_place && typeof payload.current_place === "object" ? payload.current_place : {},
    recent_places: Array.isArray(payload?.recent_places) ? payload.recent_places : [],
    nearby_categories: Array.isArray(payload?.nearby_categories) ? payload.nearby_categories : [],
    observed_at: observedAt,
    source: String(payload?.source || "desktop_geolocation_capture").trim() || "desktop_geolocation_capture",
    scope: String(payload?.scope || "personal").trim() || "personal",
    sensitivity: String(payload?.sensitivity || "high").trim() || "high",
    provider: String(payload?.provider || "desktop_browser_capture_v1").trim() || "desktop_browser_capture_v1",
    provider_mode: String(payload?.provider_mode || "desktop_renderer_geolocation").trim() || "desktop_renderer_geolocation",
    provider_status: String(payload?.provider_status || "fresh").trim() || "fresh",
    capture_mode: String(payload?.capture_mode || "device_capture").trim() || "device_capture",
    permission_state: String(payload?.permission_state || "granted").trim() || "granted",
    privacy_mode: Boolean(payload?.privacy_mode),
    capture_failure_reason: String(payload?.capture_failure_reason || "").trim() || null,
    saved_at: new Date().toISOString(),
  };
  fs.mkdirSync(snapshotDir, { recursive: true });
  fs.writeFileSync(snapshotPath, `${JSON.stringify(normalized, null, 2)}\n`, "utf-8");
  return {
    ok: true,
    snapshotPath,
    payload: normalized,
  };
}

function providerPatchForValidation(payload, config) {
  const currentProvider = config?.provider || {};
  const payloadType = String(payload?.type || currentProvider.type || "openai").trim();
  const currentType = String(currentProvider.type || "").trim();
  const incomingApiKey = String(payload?.apiKey || "").trim();
  return {
    ...payload,
    type: payloadType,
    baseUrl: String(payload?.baseUrl || currentProvider.baseUrl || "").trim(),
    model: String(payload?.model || currentProvider.model || "").trim(),
    apiKey: incomingApiKey || (payloadType === currentType ? String(currentProvider.apiKey || "").trim() : ""),
  };
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasOnlyKeys(value, allowedKeys) {
  if (!isPlainObject(value)) {
    return false;
  }
  const keys = Object.keys(value);
  return keys.length > 0 && keys.every((key) => allowedKeys.has(key));
}

function isPassiveIntegrationSetupPatch(patch) {
  if (!isPlainObject(patch)) {
    return false;
  }
  const keys = Object.keys(patch);
  if (keys.length !== 1) {
    return false;
  }
  if (keys[0] === "google") {
    return hasOnlyKeys(patch.google, new Set(["clientId", "clientSecret"]));
  }
  if (keys[0] === "outlook") {
    return hasOnlyKeys(patch.outlook, new Set(["clientId", "tenantId", "redirectUri"]));
  }
  if (keys[0] === "x") {
    return hasOnlyKeys(patch.x, new Set(["clientId", "clientSecret", "redirectUri"]));
  }
  if (keys[0] === "linkedin") {
    return hasOnlyKeys(patch.linkedin, new Set(["clientId", "clientSecret", "redirectUri"]));
  }
  if (keys[0] === "instagram") {
    return hasOnlyKeys(patch.instagram, new Set(["clientId", "clientSecret", "redirectUri", "pageNameHint"]));
  }
  if (keys[0] === "whatsapp") {
    return hasOnlyKeys(
      patch.whatsapp,
      new Set([
        "mode",
        "enabled",
        "accessToken",
        "phoneNumberId",
        "businessLabel",
        "displayPhoneNumber",
        "verifiedName",
        "configuredAt",
        "lastValidatedAt",
        "validationStatus",
        "lastSyncAt",
        "webSessionName",
        "webStatus",
        "webAccountLabel",
        "webLastReadyAt",
        "webLastSyncAt",
      ]),
    );
  }
  return false;
}

function patchRequiresBackendRefresh(patch) {
  const keys = Object.keys(patch || {});
  if (!keys.length) {
    return false;
  }
  if (isPassiveIntegrationSetupPatch(patch)) {
    return false;
  }
  const passiveKeys = new Set([
    "themeMode",
    "themeAccent",
    "chatFontSize",
    "chatWallpaper",
    "customWallpaper",
    "automation",
    "updater",
  ]);
  return keys.some((key) => !passiveKeys.has(key));
}

function normalizeTextList(values) {
  const items = [];
  for (const raw of Array.isArray(values) ? values : []) {
    const value = String(raw || "").trim();
    if (!value || items.includes(value)) {
      continue;
    }
    items.push(value);
  }
  return items;
}

function sortForStableSerialization(value) {
  if (Array.isArray(value)) {
    return value.map((item) => sortForStableSerialization(item));
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  return Object.keys(value)
    .sort((left, right) => left.localeCompare(right))
    .reduce((accumulator, key) => {
      accumulator[key] = sortForStableSerialization(value[key]);
      return accumulator;
    }, {});
}

function backendConfigFingerprint(config) {
  const normalized = {
    officeId: String(config?.officeId || "").trim(),
    deploymentMode: String(config?.deploymentMode || "").trim(),
    releaseChannel: String(config?.releaseChannel || "").trim(),
    selectedModelProfile: String(config?.selectedModelProfile || "").trim(),
    apiHost: String(config?.apiHost || "").trim(),
    apiPort: Number(config?.apiPort || 0),
    apiBaseUrl: String(config?.apiBaseUrl || "").trim(),
    storagePath: String(config?.storagePath || "").trim(),
    envFile: String(config?.envFile || "").trim(),
    runtimeBootstrapKey: String(config?.runtimeBootstrapKey || "").trim(),
    provider: sortForStableSerialization(config?.provider || {}),
    google: sortForStableSerialization(config?.google || {}),
    outlook: sortForStableSerialization(config?.outlook || {}),
    telegram: sortForStableSerialization(config?.telegram || {}),
    whatsapp: sortForStableSerialization(config?.whatsapp || {}),
    x: sortForStableSerialization(config?.x || {}),
    linkedin: sortForStableSerialization(config?.linkedin || {}),
    instagram: sortForStableSerialization(config?.instagram || {}),
  };
  return JSON.stringify(normalized);
}

function buildApiBaseUrlWithPort(apiBaseUrl, apiHost, apiPort) {
  const normalizedPort = Number(apiPort || 0);
  try {
    const next = new URL(String(apiBaseUrl || "").trim());
    if (Number.isFinite(normalizedPort) && normalizedPort > 0) {
      next.port = String(normalizedPort);
    }
    return next.toString().replace(/\/$/, "");
  } catch {
    const host = String(apiHost || "127.0.0.1").trim() || "127.0.0.1";
    return `http://${host}:${String(normalizedPort || 0)}`;
  }
}

function findAvailablePort(preferredHost = "127.0.0.1") {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, String(preferredHost || "127.0.0.1").trim() || "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? Number(address.port || 0) : 0;
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        if (!Number.isFinite(port) || port <= 0) {
          reject(new Error("backend_dynamic_port_unavailable"));
          return;
        }
        resolve(port);
      });
    });
  });
}

setWhatsAppWebBridgeContext({
  loadConfig: () => loadCurrentConfig(),
  saveConfig: async (patch) => saveCurrentConfig(patch || {}),
  getRuntimeInfo: async () => runtimeInfo || ensureBackendRunning({ forceRestart: false }).catch(() => null),
});

setTelegramWebBridgeContext({
  loadConfig: () => loadCurrentConfig(),
  saveConfig: async (patch) => saveCurrentConfig(patch || {}),
  getRuntimeInfo: async () => runtimeInfo || ensureBackendRunning({ forceRestart: false }).catch(() => null),
});

setLinkedInWebBridgeContext({
  loadConfig: () => loadCurrentConfig(),
  saveConfig: async (patch) => saveCurrentConfig(patch || {}),
  getRuntimeInfo: async () => runtimeInfo || ensureBackendRunning({ forceRestart: false }).catch(() => null),
});

async function maybeStartConfiguredWhatsAppWeb() {
  const config = loadCurrentConfig();
  const mode = String(config?.whatsapp?.mode || "").trim().toLowerCase();
  const shouldStart = Boolean(
    config?.whatsapp?.enabled
    && (mode === "web" || (!mode && !config?.whatsapp?.phoneNumberId && !config?.whatsapp?.accessToken)),
  );
  if (!shouldStart) {
    return;
  }
  try {
    await connectWhatsAppWeb(config);
  } catch (error) {
    if (String(error?.code || "").trim() === "WHATSAPP_WEB_SESSION_BUSY") {
      logStartup("whatsapp_web_autostart_skipped", String(error?.message || "session_busy"));
      return;
    }
    console.error("[lawcopilot] whatsapp_web_autostart_failed", error);
  }
}

function scheduleWhatsAppWebAutostart() {
  setTimeout(() => {
    void maybeStartConfiguredWhatsAppWeb();
  }, Math.max(0, WHATSAPP_AUTOSTART_DELAY_MS));
}

function currentAutomationConfig(config) {
  const rawAutomation = config?.automation && typeof config.automation === "object" ? config.automation : {};
  return normalizeAutomationConfigForWrite(rawAutomation);
}

function buildAutomationKey(prefix, item, extra = "") {
  return [
    prefix,
    String(item?.source_type || item?.kind || "item").trim(),
    String(item?.source_ref || item?.id || item?.title || "ref").trim(),
    String(extra || "").trim(),
  ].filter(Boolean).join(":");
}

function notifyDesktop(title, body) {
  if (!Notification.isSupported()) {
    return;
  }
  const resolvedTitle = String(title || "").trim();
  if (!resolvedTitle) {
    return;
  }
  try {
    const notification = new Notification({
      title: resolvedTitle,
      body: String(body || "").trim(),
      silent: false,
    });
    notification.show();
  } catch {
    return;
  }
}

function emitAutomationEvent(payload) {
  try {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }
    mainWindow.webContents.send("lawcopilot:automation-event", payload || {});
  } catch {
    return;
  }
}

function pruneAutomationLedger(ledger, nowIso) {
  const entries = ledger?.entries && typeof ledger.entries === "object" ? { ...ledger.entries } : {};
  const nowValue = Date.parse(String(nowIso || ""));
  const items = Object.entries(entries).filter(([, value]) => {
    if (!nowValue) {
      return true;
    }
    const parsed = Date.parse(String(value || ""));
    if (!parsed) {
      return true;
    }
    return nowValue - parsed <= 1000 * 60 * 60 * 24 * 45;
  });
  if (items.length <= 1200) {
    return {
      entries: Object.fromEntries(items),
      lastRunAt: String(nowIso || ""),
    };
  }
  const trimmed = items
    .sort((left, right) => Date.parse(String(right[1] || "")) - Date.parse(String(left[1] || "")))
    .slice(0, 1200);
  return {
    entries: Object.fromEntries(trimmed),
    lastRunAt: String(nowIso || ""),
  };
}

function markAutomationLedger(ledger, key, timestamp) {
  const entries = ledger.entries && typeof ledger.entries === "object" ? ledger.entries : {};
  entries[key] = String(timestamp || new Date().toISOString());
  ledger.entries = entries;
}

function markRecipientLedger(ledger, keyPrefix, recipient, timestamp) {
  const recipientKey = `${String(keyPrefix || "").trim()}:${String(recipient || "").trim()}`;
  markAutomationLedger(ledger, recipientKey, timestamp);
  return recipientKey;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = AUTOMATION_REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function withTimeout(task, timeoutMs, errorCode) {
  let timer = null;
  try {
    return await Promise.race([
      Promise.resolve().then(() => task()),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(errorCode || "operation_timeout")), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }
}

async function automationApiGet(pathname) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("automation_runtime_unavailable");
  }
  let response = await fetchWithTimeout(`${runtimeInfo.apiBaseUrl}${pathname}`, {
    headers: {
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
  });
  if (response.status === 401) {
    const token = await createRuntimeToken(runtimeInfo.apiBaseUrl, resolveBootstrapKey(runtimeInfo));
    runtimeInfo = { ...(runtimeInfo || {}), sessionToken: token.access_token };
    response = await fetchWithTimeout(`${runtimeInfo.apiBaseUrl}${pathname}`, {
      headers: {
        Authorization: `Bearer ${runtimeInfo.sessionToken}`,
      },
    });
  }
  if (!response.ok) {
    throw new Error(`automation_api_failed:${pathname}:${response.status}`);
  }
  return response.json().catch(() => ({}));
}

async function automationApiPost(pathname, payload = {}) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("automation_runtime_unavailable");
  }
  let response = await fetchWithTimeout(`${runtimeInfo.apiBaseUrl}${pathname}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify(payload || {}),
  });
  if (response.status === 401) {
    const token = await createRuntimeToken(runtimeInfo.apiBaseUrl, resolveBootstrapKey(runtimeInfo));
    runtimeInfo = { ...(runtimeInfo || {}), sessionToken: token.access_token };
    response = await fetchWithTimeout(`${runtimeInfo.apiBaseUrl}${pathname}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${runtimeInfo.sessionToken}`,
      },
      body: JSON.stringify(payload || {}),
    });
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(String(body?.detail || body?.message || `automation_api_failed:${pathname}:${response.status}`));
  }
  return body;
}

async function runAssistantLegacySetup(payload = {}) {
  const setupId = Number(payload?.setupId || payload?.setup_id || 0);
  if (!setupId) {
    throw new Error("assistant_setup_id_required");
  }
  const prepared = await automationApiPost(`/integrations/assistant-setups/${setupId}/desktop/prepare`, {});
  const desktopAction = String(prepared?.desktop_action || "").trim();
  const configPatch = prepared?.config_patch && typeof prepared.config_patch === "object" ? prepared.config_patch : {};
  let config = loadCurrentConfig();
  if (Object.keys(configPatch).length) {
    config = saveCurrentConfig(configPatch);
    await refreshBackendAfterConfigChange().catch(() => null);
    config = loadCurrentConfig();
  }
  let message = String(prepared?.desktop_action_help || prepared?.setup?.next_step || "Kurulum masaüstü akışına aktarıldı.");
  let status = null;
  let validation = null;

  if (desktopAction === "start_google_auth") {
    status = await startGoogleOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
    message = String(status?.message || message);
  } else if (desktopAction === "start_outlook_auth") {
    status = await startOutlookOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
    message = String(status?.message || message);
  } else if (desktopAction === "save_telegram") {
    validation = await validateTelegramConfig({
      enabled: Boolean(config.telegram?.enabled),
      botToken: config.telegram?.botToken,
      allowedUserId: config.telegram?.allowedUserId,
    });
    config = saveCurrentConfig({
      telegram: {
        botUsername: validation?.telegram?.botUsername || config.telegram?.botUsername || "",
        validationStatus: validation?.telegram?.validationStatus || "valid",
        lastValidatedAt: validation?.telegram?.lastValidatedAt || new Date().toISOString(),
      },
    });
    await refreshBackendAfterConfigChange().catch(() => null);
    const syncResult = await syncTelegramData(config, runtimeInfo).catch(() => null);
    message = String(syncResult?.message || validation?.message || message);
  } else if (desktopAction === "start_telegram_web_link") {
    status = await startTelegramWebLink(config);
    message = String(status?.message || message);
  } else if (desktopAction === "start_whatsapp_web_link") {
    status = await connectWhatsAppWeb(config);
    message = String(status?.message || message);
  } else if (desktopAction === "save_whatsapp_business") {
    validation = await validateWhatsAppConfig({
      enabled: Boolean(config.whatsapp?.enabled),
      mode: "business_cloud",
      accessToken: config.whatsapp?.accessToken,
      phoneNumberId: config.whatsapp?.phoneNumberId,
      businessLabel: config.whatsapp?.businessLabel,
    });
    config = saveCurrentConfig({
      whatsapp: {
        businessLabel: validation?.whatsapp?.businessLabel || config.whatsapp?.businessLabel || "",
        displayPhoneNumber: validation?.whatsapp?.displayPhoneNumber || config.whatsapp?.displayPhoneNumber || "",
        verifiedName: validation?.whatsapp?.verifiedName || config.whatsapp?.verifiedName || "",
        validationStatus: validation?.whatsapp?.validationStatus || "valid",
        lastValidatedAt: validation?.whatsapp?.lastValidatedAt || new Date().toISOString(),
      },
    });
    await refreshBackendAfterConfigChange().catch(() => null);
    const syncResult = await syncWhatsAppData(config, runtimeInfo).catch(() => null);
    message = String(syncResult?.message || validation?.message || message);
  } else if (desktopAction === "start_x_auth") {
    status = await startXOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
    message = String(status?.message || message);
  } else if (desktopAction === "start_linkedin_auth") {
    status = await startLinkedInOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
    message = String(status?.message || message);
  } else if (desktopAction === "start_linkedin_web_link") {
    status = await startLinkedInWebLink(config);
    message = String(status?.message || message);
  } else if (desktopAction === "start_instagram_auth") {
    status = await startInstagramOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
    message = String(status?.message || message);
  }

  return {
    ok: true,
    desktopAction,
    message,
    status,
    validation,
    setup: prepared?.setup || null,
    connector: prepared?.connector || null,
    generated_from: "assistant_integration_desktop_apply",
  };
}

function normalizeAutomationText(value) {
  let text = String(value || "").trim().toLowerCase();
  const replacements = {
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
    "’": "'",
    "“": '"',
    "”": '"',
  };
  for (const [source, target] of Object.entries(replacements)) {
    text = text.replaceAll(source, target);
  }
  return text.replace(/\s+/g, " ").trim();
}

function normalizeAutomationMode(value) {
  const mode = String(value || "").trim().toLowerCase();
  if (["auto_reply", "notify", "custom", "reminder"].includes(mode)) {
    return mode;
  }
  return "custom";
}

function normalizeAutomationRule(raw, index = 0) {
  const value = raw && typeof raw === "object" ? raw : {};
  const summary = String(value.summary || value.label || value.instruction || "").replace(/\s+/g, " ").trim().slice(0, 240);
  if (!summary) {
    return null;
  }
  return {
    id: String(value.id || `rule-${index + 1}`).trim().slice(0, 80) || `rule-${index + 1}`,
    summary,
    instruction: String(value.instruction || summary).replace(/\s+/g, " ").trim().slice(0, 400),
    mode: normalizeAutomationMode(value.mode),
    channels: normalizeTextList(Array.isArray(value.channels) ? value.channels : []).map((item) => item.toLowerCase()).slice(0, 6),
    targets: normalizeTextList(Array.isArray(value.targets) ? value.targets : []).slice(0, 12),
    matchTerms: normalizeTextList(
      Array.isArray(value.matchTerms)
        ? value.matchTerms
        : Array.isArray(value.match_terms)
          ? value.match_terms
          : [],
    ).slice(0, 12),
    replyText: String(value.replyText || value.reply_text || "").replace(/\s+/g, " ").trim().slice(0, 280),
    reminderAt: String(value.reminderAt || value.reminder_at || "").trim(),
    threadId: Number.parseInt(String(value.threadId || value.thread_id || 0), 10) || 0,
    active: value.active !== false,
  };
}

function normalizeAutomationRules(rules) {
  const items = [];
  const seen = new Set();
  for (const [index, raw] of (Array.isArray(rules) ? rules : []).entries()) {
    const item = normalizeAutomationRule(raw, index);
    if (!item) {
      continue;
    }
    const key = `${item.mode}:${normalizeAutomationText(item.summary)}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    items.push(item);
  }
  return items.slice(0, 40);
}

function automationRulesFilePath(config) {
  const storageRoot = String(config?.storagePath || configOptions().storagePath || "").trim();
  const runtimeRoot = path.join(storageRoot || path.join(configOptions().repoRoot, "artifacts"), "runtime");
  return path.join(runtimeRoot, AUTOMATION_RULES_FILE_NAME);
}

function serializeAutomationArtifactMarkdown(automation) {
  const rules = normalizeAutomationRules(automation?.automationRules);
  const lines = [
    "# HEARTBEAT-AUTOMATIONS.md",
    "",
    "Bu dosya LawCopilot tarafından otomatik yazılır.",
    "Asistan sohbetinde verilen otomasyon taleplerinin kısa ve okunabilir özeti burada tutulur.",
    "",
    `Son güncelleme: ${new Date().toISOString()}`,
    "",
    "## Aktif Kurallar",
  ];
  if (rules.length) {
    for (const rule of rules) {
      const scope = rule.channels.length ? rule.channels.join(", ") : "genel";
      lines.push(`- ${rule.summary} [${scope}]`);
      if (rule.instruction && rule.instruction !== rule.summary) {
        lines.push(`  - Kaynak talep: ${rule.instruction}`);
      }
    }
  } else {
    lines.push("- Kayitli otomasyon kurali yok.");
  }
  lines.push(
    "",
    "## Machine Data",
    "```json",
    JSON.stringify(
      {
        enabled: Boolean(automation?.enabled),
        autoSyncConnectedServices: Boolean(automation?.autoSyncConnectedServices),
        desktopNotifications: Boolean(automation?.desktopNotifications),
        automationRules: rules,
      },
      null,
      2,
    ),
    "```",
    "",
  );
  return lines.join("\n");
}

function syncAutomationArtifact(config) {
  try {
    const automation = currentAutomationConfig(config);
    const artifactPath = automationRulesFilePath(config);
    fs.mkdirSync(path.dirname(artifactPath), { recursive: true, mode: 0o700 });
    fs.writeFileSync(artifactPath, serializeAutomationArtifactMarkdown(automation), { encoding: "utf-8", mode: 0o600 });
  } catch (error) {
    console.error("[lawcopilot] automation_artifact_write_failed", error);
  }
}

function resolveBootstrapKey(config) {
  const direct = String(config?.runtimeBootstrapKey || process.env.LAWCOPILOT_BOOTSTRAP_ADMIN_KEY || "").trim();
  if (direct) {
    return direct;
  }
  const envFile = String(config?.envFile || "").trim();
  if (!envFile) {
    return "";
  }
  const parsed = parseEnvFile(envFile);
  return String(parsed.LAWCOPILOT_BOOTSTRAP_ADMIN_KEY || "").trim();
}

function loadAutomationArtifact(config, automation) {
  const fallback = {
    enabled: Boolean(automation?.enabled),
    autoSyncConnectedServices: Boolean(automation?.autoSyncConnectedServices),
    desktopNotifications: Boolean(automation?.desktopNotifications),
    automationRules: normalizeAutomationRules(automation?.automationRules),
  };
  try {
    const raw = fs.readFileSync(automationRulesFilePath(config), "utf-8");
    const match = raw.match(/```json\s*([\s\S]*?)\s*```/i);
    if (!match) {
      return fallback;
    }
    const parsed = JSON.parse(match[1]);
    return {
      ...fallback,
      enabled: typeof parsed?.enabled === "boolean" ? parsed.enabled : fallback.enabled,
      autoSyncConnectedServices: typeof parsed?.autoSyncConnectedServices === "boolean"
        ? parsed.autoSyncConnectedServices
        : fallback.autoSyncConnectedServices,
      desktopNotifications: typeof parsed?.desktopNotifications === "boolean"
        ? parsed.desktopNotifications
        : fallback.desktopNotifications,
      automationRules: normalizeAutomationRules(parsed?.automationRules),
    };
  } catch {
    return fallback;
  }
}

function automationChannelForItem(item) {
  const sourceType = String(item?.source_type || "").trim().toLowerCase();
  const provider = String(item?.provider || "").trim().toLowerCase();
  if (sourceType.includes("whatsapp") || provider === "whatsapp") {
    return "whatsapp";
  }
  if (sourceType.includes("telegram") || provider === "telegram") {
    return "telegram";
  }
  if (sourceType.includes("email") || sourceType.includes("outlook") || provider === "gmail" || provider === "outlook") {
    return sourceType.includes("outlook") || provider === "outlook" ? "outlook" : "email";
  }
  if (sourceType === "x_post" || provider === "x") {
    return "x";
  }
  return "generic";
}

function automationItemHaystack(item) {
  return normalizeAutomationText([
    item?.contact_label,
    item?.sender,
    item?.recipient,
    item?.thread_subject,
    item?.title,
    item?.details,
    item?.importance_reason,
  ].join(" "));
}

function automationItemSender(item) {
  return normalizeAutomationText([
    item?.sender,
    item?.contact_label,
    item?.recipient,
  ].join(" "));
}

function automationItemTitle(item) {
  return normalizeAutomationText([
    item?.thread_subject,
    item?.title,
  ].join(" "));
}

function isSuppressedDesktopNotificationItem(item) {
  const channel = automationChannelForItem(item);
  if (!["email", "outlook"].includes(channel)) {
    return false;
  }
  const sender = automationItemSender(item);
  const title = automationItemTitle(item);
  const details = normalizeAutomationText(item?.details || "");
  const haystack = `${sender} ${title} ${details}`.trim();

  const senderTokens = [
    "no reply",
    "noreply",
    "do not reply",
    "donotreply",
    "mailer-daemon",
    "postmaster",
    "newsletter",
    "news@",
    "@newsletter",
    "kampanya",
    "promosyon",
  ];
  if (senderTokens.some((token) => haystack.includes(token))) {
    return true;
  }

  const promoTokens = [
    "indirim",
    "firsat",
    "fırsat",
    "kampanya",
    "promosyon",
    "promotion",
    "discount",
    "sale",
    "flash sale",
    "limited time",
    "son gun",
    "son gün",
    "daha iyi fiyat",
    "coupon",
    "kupon",
    "% off",
    "% daha",
  ];
  return promoTokens.some((token) => haystack.includes(token));
}

function followUpReminderBody(item, ageHours) {
  const contact = String(item?.contact_label || item?.sender || "ilgili kişi").trim();
  const channel = String(item?.provider || item?.source_type || "iletişim").trim();
  return `${contact} için ${channel} kanalında ${ageHours} saati aşan yanıt bekleyen bir ileti var. İstersen taslak hazırlayabilirim.`;
}

function calendarReminderBody(item) {
  const location = String(item?.location || item?.details || "").trim();
  return location
    ? `${location} için kısa hazırlık notu ve katılım teyidi oluşturabilirim.`
    : "İstersen kısa hazırlık notu ve katılım teyidi oluşturabilirim.";
}

async function maybeSyncConnectedServices(config, automation, options = {}) {
  const force = Boolean(options.force);
  if ((!force && !automation.autoSyncConnectedServices) || !runtimeInfo) {
    return;
  }
  const currentRuntime = runtimeInfo;
  const syncTasks = [];
  if (config.google?.enabled && config.google?.oauthConnected) {
    syncTasks.push(runProviderSync("google", () => syncGoogleData(config, currentRuntime), "google_sync_timeout", { errorField: "oauthLastError" }));
  }
  if (config.outlook?.enabled && config.outlook?.oauthConnected) {
    syncTasks.push(runProviderSync("outlook", () => syncOutlookData(config, currentRuntime), "outlook_sync_timeout", { errorField: "oauthLastError" }));
  }
  if (config.telegram?.enabled) {
    syncTasks.push(runProviderSync("telegram", () => syncTelegramData(config, currentRuntime), "telegram_sync_timeout"));
  }
  if (config.whatsapp?.enabled) {
    syncTasks.push(runProviderSync("whatsapp", () => syncWhatsAppData(config, currentRuntime), "whatsapp_sync_timeout"));
  }
  if (config.x?.enabled && config.x?.oauthConnected) {
    syncTasks.push(runProviderSync("x", () => syncXData(config, currentRuntime), "x_sync_timeout", { errorField: "oauthLastError" }));
  }
  if (config.instagram?.enabled && config.instagram?.oauthConnected) {
    syncTasks.push(runProviderSync("instagram", () => syncInstagramData(config, currentRuntime), "instagram_sync_timeout", { errorField: "oauthLastError" }));
  }
  if (config.linkedin?.enabled) {
    syncTasks.push(runProviderSync("linkedin", () => syncLinkedInData(config, currentRuntime), "linkedin_sync_timeout", { errorField: "oauthLastError" }));
  }
  await Promise.all(syncTasks);
}

async function runConnectedServicesSync(options = {}) {
  if (connectedServicesSyncInFlight || !runtimeInfo?.sessionToken) {
    return;
  }
  connectedServicesSyncInFlight = true;
  try {
    const config = loadCurrentConfig();
    const automation = currentAutomationConfig(config);
    await maybeSyncConnectedServices(config, automation, { force: true, ...options });
  } catch {
    return;
  } finally {
    connectedServicesSyncInFlight = false;
  }
}

function startConnectedServicesSync() {
  if (connectedServicesSyncInterval) {
    clearInterval(connectedServicesSyncInterval);
  }
  connectedServicesSyncInterval = setInterval(() => {
    void runConnectedServicesSync();
  }, Math.max(15000, CONNECTED_SERVICES_SYNC_INTERVAL_MS));
  setTimeout(() => {
    void runConnectedServicesSync();
  }, 15000);
}

function stopConnectedServicesSync() {
  if (connectedServicesSyncInterval) {
    clearInterval(connectedServicesSyncInterval);
    connectedServicesSyncInterval = null;
  }
  connectedServicesSyncInFlight = false;
}

function maybeNotifyInboxItems(automation, ledger, inbox, nowIso) {
  if (!automation.desktopNotifications) {
    return;
  }
  for (const item of Array.isArray(inbox) ? inbox : []) {
    if (isSuppressedDesktopNotificationItem(item)) {
      continue;
    }
    const importanceReason = String(item?.importance_reason || "").trim();
    const priority = String(item?.priority || "").trim().toLowerCase();
    if (!importanceReason && priority !== "high") {
      continue;
    }
    const ledgerKey = buildAutomationKey("inbox-attention", item);
    if (ledger.entries?.[ledgerKey]) {
      continue;
    }
    notifyDesktop(
      String(item?.title || "Önemli ileti"),
      importanceReason || String(item?.details || "Yeni veya yanıt bekleyen önemli bir ileti var.").trim(),
    );
    markAutomationLedger(ledger, ledgerKey, nowIso);
  }
}

function maybeNotifyFollowUps(automation, ledger, inbox, nowIso) {
  if (!automation.desktopNotifications) {
    return;
  }
  const thresholdHours = Number.parseInt(String(automation.followUpReminderHours || DEFAULT_FOLLOW_UP_REMINDER_HOURS), 10) || DEFAULT_FOLLOW_UP_REMINDER_HOURS;
  const thresholdMs = thresholdHours * 60 * 60 * 1000;
  const maxAgeMs = Math.max(thresholdMs * 7, 1000 * 60 * 60 * 24 * 7);
  for (const item of Array.isArray(inbox) ? inbox : []) {
    if (isSuppressedDesktopNotificationItem(item)) {
      continue;
    }
    const dueAt = Date.parse(String(item?.due_at || ""));
    if (!dueAt) {
      continue;
    }
    const ageMs = Date.now() - dueAt;
    if (ageMs < thresholdMs || ageMs > maxAgeMs) {
      continue;
    }
    const ledgerKey = buildAutomationKey("follow-up", item, String(thresholdHours));
    if (ledger.entries?.[ledgerKey]) {
      continue;
    }
    notifyDesktop(String(item?.title || "Takip gerekiyor"), followUpReminderBody(item, thresholdHours));
    markAutomationLedger(ledger, ledgerKey, nowIso);
  }
}

function maybeNotifyCalendarItems(automation, ledger, calendar, nowIso) {
  if (!automation.desktopNotifications) {
    return;
  }
  const leadMinutes = Number.parseInt(
    String(automation.calendarReminderLeadMinutes || DEFAULT_CALENDAR_REMINDER_LEAD_MINUTES),
    10,
  ) || DEFAULT_CALENDAR_REMINDER_LEAD_MINUTES;
  const leadMs = leadMinutes * 60 * 1000;
  for (const item of Array.isArray(calendar) ? calendar : []) {
    const startsAt = Date.parse(String(item?.starts_at || ""));
    if (!startsAt) {
      continue;
    }
    const delta = startsAt - Date.now();
    if (delta < 0 || delta > leadMs) {
      continue;
    }
    const ledgerKey = buildAutomationKey("calendar-reminder", item, String(leadMinutes));
    if (ledger.entries?.[ledgerKey]) {
      continue;
    }
    notifyDesktop(`${String(item?.title || "Takvim kaydı").trim()} ${leadMinutes} dk sonra`, calendarReminderBody(item));
    markAutomationLedger(ledger, ledgerKey, nowIso);
  }
  for (const item of Array.isArray(calendar) ? calendar : []) {
    const responseStatus = String(item?.metadata?.response_status || "").trim().toLowerCase();
    if (!["notresponded", "none", "tentativelyaccepted", "tentative"].includes(responseStatus)) {
      continue;
    }
    const startsAt = Date.parse(String(item?.starts_at || ""));
    if (!startsAt || startsAt - Date.now() > 1000 * 60 * 60 * 48) {
      continue;
    }
    const ledgerKey = buildAutomationKey("calendar-rsvp", item, responseStatus);
    if (ledger.entries?.[ledgerKey]) {
      continue;
    }
    notifyDesktop(
      `${String(item?.title || "Takvim kaydı").trim()} için katılım teyidi`,
      "Bu kayıt için katılacağım / katılmayacağım yanıtını netleştirmek isteyebilirsin.",
    );
    markAutomationLedger(ledger, ledgerKey, nowIso);
  }
}

function ruleMatchesInboxItem(rule, item) {
  if (!rule?.active) {
    return false;
  }
  const channel = automationChannelForItem(item);
  if (rule.channels.length && !rule.channels.includes(channel)) {
    return false;
  }
  if (normalizeAutomationMode(rule.mode) === "auto_reply" && String(item?.direction || "").trim().toLowerCase() !== "inbound") {
    return false;
  }
  if (!rule.targets.length && !rule.matchTerms.length) {
    return false;
  }
  const haystack = automationItemHaystack(item);
  const targetMatched = rule.targets.length
    ? rule.targets.some((itemValue) => haystack.includes(normalizeAutomationText(itemValue)))
    : true;
  const termMatched = rule.matchTerms.length
    ? rule.matchTerms.some((itemValue) => haystack.includes(normalizeAutomationText(itemValue)))
    : true;
  return targetMatched && termMatched;
}

function autoReplyTextForRule(rule, item) {
  if (rule.replyText) {
    return rule.replyText;
  }
  const haystack = automationItemHaystack(item);
  if (haystack.includes("gunaydin")) {
    return "Günaydın, mesajını aldım. Sana da iyi günler dilerim.";
  }
  if (haystack.includes("bayram")) {
    return "Teşekkür ederim, iyi bayramlar dilerim.";
  }
  if (haystack.includes("tesekkur")) {
    return "Rica ederim, mesajını aldım.";
  }
  if (haystack.includes("?")) {
    return "Mesajını aldım. Müsait olur olmaz net bir dönüş yapacağım.";
  }
  return "Mesajını aldım. Uygun olur olmaz kısa bir dönüş yapacağım.";
}

async function maybeRunRuleBasedAutomations(config, automation, ledger, inbox, nowIso) {
  const artifact = loadAutomationArtifact(config, automation);
  const rules = normalizeAutomationRules(artifact.automationRules);
  if (!rules.length) {
    return;
  }
  for (const rule of rules) {
    if (!rule?.active || normalizeAutomationMode(rule.mode) !== "reminder") {
      continue;
    }
    const reminderAt = Date.parse(String(rule.reminderAt || ""));
    if (!reminderAt || reminderAt > Date.now()) {
      continue;
    }
    const ledgerKey = buildAutomationKey("rule:reminder", { id: rule.id, title: rule.summary }, String(rule.reminderAt || ""));
    if (ledger.entries?.[ledgerKey]) {
      continue;
    }
    const title = String(rule.summary || "Hatırlatma").trim() || "Hatırlatma";
    const body = String(rule.replyText || rule.instruction || rule.summary || "").trim();
    const reminderResponse = await automationApiPost("/assistant/thread/system-message", {
      content: body || title,
      thread_id: Number(rule.threadId || 0) || undefined,
      source_context: {
        automation_event: "reminder_fired",
        reminder_rule_id: String(rule.id || "").trim(),
        reminder_title: title,
        reminder_body: body,
        reminder_at: String(rule.reminderAt || "").trim(),
        delivered_at: nowIso,
      },
    });
    notifyDesktop(title, body);
    emitAutomationEvent({
      kind: "reminder_fired",
      title,
      body,
      rule_id: String(rule.id || "").trim(),
      reminder_at: String(rule.reminderAt || "").trim(),
      delivered_at: nowIso,
      thread_id: Number(reminderResponse?.thread?.id || rule.threadId || 0) || null,
      message_id: Number(reminderResponse?.message?.id || 0) || null,
    });
    markAutomationLedger(ledger, ledgerKey, nowIso);
  }
  const canSendWhatsApp = Boolean(config.whatsapp?.enabled && config.whatsapp?.accessToken && config.whatsapp?.phoneNumberId);
  for (const rule of rules) {
    const mode = normalizeAutomationMode(rule.mode);
    if (!["auto_reply", "notify"].includes(mode)) {
      continue;
    }
    for (const item of Array.isArray(inbox) ? inbox : []) {
      if (!ruleMatchesInboxItem(rule, item)) {
        continue;
      }
      if (mode === "notify" && isSuppressedDesktopNotificationItem(item)) {
        continue;
      }
      const ledgerKey = buildAutomationKey(`rule:${mode}`, item, rule.id);
      if (ledger.entries?.[ledgerKey]) {
        continue;
      }
      if (mode === "notify") {
        if (!automation.desktopNotifications) {
          continue;
        }
        notifyDesktop(String(item?.title || "Otomasyon uyarisi"), rule.summary);
        markAutomationLedger(ledger, ledgerKey, nowIso);
        continue;
      }
      if (!canSendWhatsApp || automationChannelForItem(item) !== "whatsapp") {
        continue;
      }
      const target = String(item?.sender || item?.contact_label || "").trim();
      if (!target) {
        continue;
      }
      try {
        await sendWhatsAppMessage(config, {
          to: target,
          text: autoReplyTextForRule(rule, item),
        });
        notifyDesktop("Otomatik yanıt gönderildi", `${target} için "${rule.summary}" kuralı çalıştı.`);
        markAutomationLedger(ledger, ledgerKey, nowIso);
      } catch {
        continue;
      }
    }
  }
}

function maybeNotifyPriorityHomeItems(automation, ledger, home, nowIso) {
  if (!automation.desktopNotifications) {
    return;
  }
  for (const item of Array.isArray(home?.priority_items) ? home.priority_items : []) {
    const kind = String(item?.kind || "").trim();
    const priority = String(item?.priority || "").trim();
    if (!["social_alert", "social_watch"].includes(kind) || priority !== "high") {
      continue;
    }
    const ledgerKey = buildAutomationKey("priority-home", item);
    if (ledger.entries?.[ledgerKey]) {
      continue;
    }
    notifyDesktop(String(item?.title || "Önemli uyarı"), String(item?.details || "").trim());
    markAutomationLedger(ledger, ledgerKey, nowIso);
  }
}

function maybeNotifyCoachingHomeItems(automation, ledger, home, nowIso) {
  if (!automation.desktopNotifications) {
    return;
  }
  const candidates = Array.isArray(home?.coaching_dashboard?.notification_candidates)
    ? home.coaching_dashboard.notification_candidates
    : [];
  for (const item of candidates) {
    if (!item?.notify_desktop) {
      continue;
    }
    const ledgerKey = buildAutomationKey("coach-home", item, String(item?.goal_id || ""));
    if (ledger.entries?.[ledgerKey]) {
      continue;
    }
    notifyDesktop(
      String(item?.title || "Koçluk hatırlatması"),
      String(item?.body || item?.why_now || "Hedef check-in zamanı geldi.").trim(),
    );
    markAutomationLedger(ledger, ledgerKey, nowIso);
  }
}

async function runDesktopAutomation() {
  if (automationInFlight || !runtimeInfo?.sessionToken) {
    return;
  }
  automationInFlight = true;
  try {
    const config = loadCurrentConfig();
    const automation = currentAutomationConfig(config);
    if (!automation.enabled) {
      return;
    }
    await maybeSyncConnectedServices(config, automation);
    const [home, inboxPayload, calendarPayload] = await Promise.all([
      automationApiGet("/assistant/home").catch(() => ({})),
      automationApiGet("/assistant/inbox").catch(() => ({ items: [] })),
      automationApiGet("/assistant/calendar").catch(() => ({ items: [] })),
    ]);
    const nowIso = new Date().toISOString();
    const ledger = pruneAutomationLedger(automation.automationLedger || {}, nowIso);
    const inbox = Array.isArray(inboxPayload?.items) ? inboxPayload.items : [];
    const calendar = Array.isArray(calendarPayload?.items) ? calendarPayload.items : [];
    maybeNotifyPriorityHomeItems(automation, ledger, home, nowIso);
    maybeNotifyCoachingHomeItems(automation, ledger, home, nowIso);
    maybeNotifyInboxItems(automation, ledger, inbox, nowIso);
    maybeNotifyFollowUps(automation, ledger, inbox, nowIso);
    maybeNotifyCalendarItems(automation, ledger, calendar, nowIso);
    await maybeRunRuleBasedAutomations(config, automation, ledger, inbox, nowIso);
    saveCurrentConfig({
      automation: {
        automationLedger: ledger,
      },
    });
  } catch {
    return;
  } finally {
    automationInFlight = false;
  }
}

async function runReminderAutomationTick() {
  if (automationInFlight || !runtimeInfo?.sessionToken) {
    return;
  }
  automationInFlight = true;
  try {
    const config = loadCurrentConfig();
    const automation = currentAutomationConfig(config);
    if (!automation.enabled) {
      return;
    }
    const nowIso = new Date().toISOString();
    const ledger = pruneAutomationLedger(automation.automationLedger || {}, nowIso);
    await maybeRunRuleBasedAutomations(config, automation, ledger, [], nowIso);
    saveCurrentConfig({
      automation: {
        automationLedger: ledger,
      },
    });
  } catch {
    return;
  } finally {
    automationInFlight = false;
  }
}

function startDesktopAutomation() {
  if (automationInterval) {
    clearInterval(automationInterval);
  }
  if (reminderAutomationInterval) {
    clearInterval(reminderAutomationInterval);
  }
  if (automationKickTimer) {
    clearTimeout(automationKickTimer);
    automationKickTimer = null;
  }
  automationInterval = setInterval(() => {
    void runDesktopAutomation();
  }, 5 * 60 * 1000);
  reminderAutomationInterval = setInterval(() => {
    void runReminderAutomationTick();
  }, Math.max(5000, REMINDER_AUTOMATION_INTERVAL_MS));
  automationKickTimer = setTimeout(() => {
    void runReminderAutomationTick();
  }, 5000);
}

function stopDesktopAutomation() {
  if (automationInterval) {
    clearInterval(automationInterval);
    automationInterval = null;
  }
  if (reminderAutomationInterval) {
    clearInterval(reminderAutomationInterval);
    reminderAutomationInterval = null;
  }
  if (automationKickTimer) {
    clearTimeout(automationKickTimer);
    automationKickTimer = null;
  }
}

async function reportDraftDispatch(pathname, payload) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const response = await fetchWithTimeout(`${runtimeInfo.apiBaseUrl}${pathname}`, {
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
  let reportMode = "complete";

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
      if (String(config.telegram?.mode || "").trim().toLowerCase() === "web") {
        result = await sendTelegramWebMessage(config, {
          conversationRef: sourceContext?.conversation_ref,
          to: sourceContext?.recipient_label || sourceContext?.recipient || draft?.to_contact,
          text: draft?.body,
        });
      } else {
        result = await sendTelegramTestMessage({
          botToken: config.telegram?.botToken,
          allowedUserId: sourceContext?.recipient || draft?.to_contact || config.telegram?.allowedUserId,
          text: draft?.body,
        });
      }
    } else if (channel === "whatsapp") {
      result = await sendWhatsAppMessage(config, {
        to: sourceContext?.recipient || draft?.to_contact,
        recipient: sourceContext?.recipient || draft?.to_contact,
        conversationRef: sourceContext?.conversation_ref,
        text: draft?.body,
      });
    } else if (channel === "x") {
      const targetUserId = String(sourceContext?.participant_id || sourceContext?.recipient_id || "").trim();
      const targetHandle = String(sourceContext?.recipient || draft?.to_contact || "").trim();
      if (targetUserId || targetHandle.startsWith("@")) {
        result = await sendXDirectMessage(config, {
          participantId: targetUserId,
          to: targetHandle,
          text: draft?.body,
        });
      } else {
        result = await postXUpdate(config, {
          text: draft?.body,
        });
      }
      if (result?.patch) {
        saveCurrentConfig(result.patch);
      }
    } else if (channel === "linkedin") {
      if (
        String(config.linkedin?.mode || "").trim().toLowerCase() === "web"
        || sourceContext?.conversation_ref
        || sourceContext?.recipient
        || sourceContext?.recipient_label
      ) {
        result = await sendLinkedInWebMessage(config, {
          conversationRef: sourceContext?.conversation_ref,
          to: sourceContext?.recipient_label || sourceContext?.recipient || draft?.to_contact,
          text: draft?.body,
        });
      } else {
        result = await postLinkedInUpdate(config, {
          text: draft?.body,
        });
      }
      if (result?.patch) {
        saveCurrentConfig(result.patch);
      }
    } else if (channel === "instagram") {
      result = await sendInstagramMessage(config, {
        participantId: sourceContext?.participant_id || sourceContext?.recipient_id,
        recipientId: sourceContext?.participant_id || sourceContext?.recipient_id,
        to: sourceContext?.recipient || draft?.to_contact,
        recipient: sourceContext?.recipient || draft?.to_contact,
        text: draft?.body,
      });
      if (result?.patch) {
        saveCurrentConfig(result.patch);
      }
    } else if (channel === "x_dm") {
      result = await sendXDirectMessage(config, {
        participantId: sourceContext?.participant_id || sourceContext?.recipient_id,
        to: sourceContext?.recipient || draft?.to_contact,
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
      await openSecureCheckoutWindow(url, { draft, sourceContext });
      reportMode = "started";
      result = {
        ok: true,
        message: "Güvenli ödeme penceresi LawCopilot içinde açıldı. Satın alma sağlayıcı tarafında tamamlanacak.",
        externalMessageId: url,
      };
    } else {
      throw new Error("Bu kanal için otomatik gönderim köprüsü bulunamadı.");
    }

    if (result?.patch) {
      saveCurrentConfig(result.patch);
    }

    if (draftId) {
      await reportDraftDispatch(`/assistant/drafts/${draftId}/dispatch-${reportMode}`, {
        action_id: actionId || null,
        external_message_id: result?.externalMessageId || result?.messageId || result?.externalThreadId || "",
        note: result?.message || (reportMode === "started" ? "Dış işlem başlatıldı." : "Dış gönderim tamamlandı."),
      });
    } else if (actionId) {
      await reportDraftDispatch(`/assistant/actions/${actionId}/dispatch-${reportMode}`, {
        external_message_id: result?.externalMessageId || result?.messageId || result?.externalThreadId || "",
        note: result?.message || (reportMode === "started" ? "Dış işlem başlatıldı." : "Dış gönderim tamamlandı."),
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
  try {
    await shell.openExternal(target, { activate: true });
    return "Sistem tarayıcısı";
  } catch {
    // Fallback to direct browser commands below.
  }
  const candidates = process.platform === "darwin"
    ? [
        ["open", ["-a", "Google Chrome", target], "Google Chrome"],
      ]
    : process.platform === "win32"
      ? [
          ["cmd", ["/c", "start", "", "chrome", "--new-tab", target], "Google Chrome"],
        ]
      : [
          ["google-chrome-stable", ["--new-tab", target], "Google Chrome"],
          ["google-chrome", ["--new-tab", target], "Google Chrome"],
          ["chromium-browser", ["--new-tab", target], "Chromium"],
          ["chromium", ["--new-tab", target], "Chromium"],
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

async function bootRuntime(runtimePathsOverride = null) {
  const runtimePaths = runtimePathsOverride || resolveRuntimePaths({
    repoRoot: path.resolve(__dirname, "..", ".."),
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    userDataPath: app.getPath("userData"),
  });
  const info = await ensureBackendRunning({ runtimePaths, forceRestart: false });
  return { config: info, runtimePaths };
}

async function readHealth(apiBaseUrl) {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/health`);
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

function backendRecoveryDelayMs(attempt) {
  const normalizedAttempt = Math.max(1, Number(attempt || 1));
  return Math.min(
    BACKEND_RECOVERY_MAX_DELAY_MS,
    BACKEND_RECOVERY_BASE_DELAY_MS * (2 ** Math.max(0, normalizedAttempt - 1)),
  );
}

function startBackendHealthMonitor() {
  stopBackendHealthMonitor();
  if (!runtimeInfo?.apiBaseUrl) {
    return;
  }
  backendHealthInterval = setInterval(() => {
    if (backendHealthProbeInFlight || appQuitInFlight || backendEnsurePromise || backendRecoveryPromise) {
      return;
    }
    backendHealthProbeInFlight = true;
    void readHealth(runtimeInfo.apiBaseUrl)
      .then((health) => {
        if (health) {
          backendConsecutiveHealthFailures = 0;
          runtimeInfo = { ...(runtimeInfo || {}), ...health };
          return;
        }
        backendConsecutiveHealthFailures += 1;
        logStartup("backend_health_miss", `count=${backendConsecutiveHealthFailures}`);
        if (backendConsecutiveHealthFailures >= BACKEND_HEALTH_FAILURE_THRESHOLD) {
          scheduleBackendRecovery(`health_probe_miss:${backendConsecutiveHealthFailures}`);
        }
      })
      .catch((error) => {
        backendConsecutiveHealthFailures += 1;
        logStartup(
          "backend_health_error",
          `count=${backendConsecutiveHealthFailures} error=${String(error?.message || error || "unknown")}`,
        );
        if (backendConsecutiveHealthFailures >= BACKEND_HEALTH_FAILURE_THRESHOLD) {
          scheduleBackendRecovery(`health_probe_error:${backendConsecutiveHealthFailures}`);
        }
      })
      .finally(() => {
        backendHealthProbeInFlight = false;
      });
  }, Math.max(1000, BACKEND_HEALTH_POLL_MS));
}

async function runBackendRecovery(reason) {
  if (appQuitInFlight) {
    return runtimeInfo;
  }
  if (backendRecoveryPromise) {
    return backendRecoveryPromise;
  }
  clearBackendRecoveryTimer();
  const attempt = backendRecoveryAttempts + 1;
  backendRecoveryAttempts = attempt;
  logStartup("backend_recovery_start", `attempt=${attempt} reason=${String(reason || "unknown")}`);
  backendRecoveryPromise = ensureBackendRunning({
    runtimePaths: runtimeInfo?.runtimePaths,
    forceRestart: true,
  })
    .then((info) => {
      backendRecoveryAttempts = 0;
      backendConsecutiveHealthFailures = 0;
      startBackendHealthMonitor();
      logStartup("backend_recovery_ready", `attempt=${attempt} pid=${String(backendHandle?.child?.pid || "")}`);
      return info;
    })
    .catch((error) => {
      const detail = String(error?.message || error || "unknown");
      logStartup("backend_recovery_failed", `attempt=${attempt} reason=${String(reason || "unknown")} error=${detail}`);
      scheduleBackendRecovery(`retry_after_failure:${detail}`);
      throw error;
    })
    .finally(() => {
      backendRecoveryPromise = null;
    });
  return backendRecoveryPromise;
}

function scheduleBackendRecovery(reason, delayMs = null) {
  if (appQuitInFlight || backendPlannedRestartDepth > 0 || backendRecoveryTimer || backendRecoveryPromise) {
    return;
  }
  const nextAttempt = backendRecoveryAttempts + 1;
  const delay = delayMs === null ? backendRecoveryDelayMs(nextAttempt) : Math.max(0, Number(delayMs || 0));
  logStartup(
    "backend_recovery_scheduled",
    `attempt=${nextAttempt} delay_ms=${delay} reason=${String(reason || "unknown")}`,
  );
  backendRecoveryTimer = setTimeout(() => {
    backendRecoveryTimer = null;
    void runBackendRecovery(reason).catch((error) => {
      console.error("[lawcopilot] backend_recovery_failed", error);
    });
  }, delay);
}

function attachBackendExitWatcher(handle) {
  if (!handle?.child || handle.child.__lawcopilotExitWatcher) {
    return;
  }
  handle.child.__lawcopilotExitWatcher = true;
  handle.child.once("exit", (code, signal) => {
    const isCurrentHandle = backendHandle?.child === handle.child;
    if (isCurrentHandle) {
      backendHandle = null;
    }
    if (appQuitInFlight) {
      return;
    }
    if (backendPlannedRestartDepth > 0 || handle.__lawcopilotExpectedStop) {
      logStartup(
        "backend_exit_expected",
        `code=${String(code ?? "null")} signal=${String(signal || "")}`,
      );
      return;
    }
    if (!isCurrentHandle) {
      logStartup(
        "backend_exit_ignored",
        `stale_handle=true code=${String(code ?? "null")} signal=${String(signal || "")}`,
      );
      return;
    }
    const reason = `child_exit:${String(code ?? "null")}:${String(signal || "")}`;
    logStartup("backend_exit_detected", reason);
    scheduleBackendRecovery(reason, 250);
  });
}

async function ensureBackendRunning(options = {}) {
  if (backendEnsurePromise) {
    if (!options.forceRestart) {
      return backendEnsurePromise;
    }
    await backendEnsurePromise.catch(() => null);
  }
  backendEnsurePromise = (async () => {
    const runtimePaths = options.runtimePaths || resolveRuntimePaths({
      repoRoot: path.resolve(__dirname, "..", ".."),
      isPackaged: app.isPackaged,
      resourcesPath: process.resourcesPath,
      userDataPath: app.getPath("userData"),
    });
    const configOptionsForRuntime = { repoRoot: runtimePaths.repoRoot, storagePath: runtimePaths.artifactsRoot };
    let config = loadCurrentConfig(configOptionsForRuntime);
    let nextFingerprint = backendConfigFingerprint(config);
    persistDesktopPid(runtimePaths, config.storagePath);
    const priorBackendPid = Number(backendHandle?.child?.pid || 0);
    let backendRestarted = false;
    const plannedRestart = Boolean(options.forceRestart);
    const bootStartedAt = Date.now();
    logStartup(
      "backend_boot_begin",
      `force_restart=${String(Boolean(options.forceRestart))} port=${String(config.apiPort)} prior_pid=${String(priorBackendPid || "")}`,
    );
    if (plannedRestart) {
      backendPlannedRestartDepth += 1;
    }
    try {
      if (options.forceRestart && backendHandle) {
        backendHandle.__lawcopilotExpectedStop = true;
        await stopBackend(backendHandle);
        backendHandle = null;
        backendRestarted = true;
      }
      if (options.forceRestart) {
        const stopResult = await stopBackendOnPort(config.apiPort, {
          allowPids: priorBackendPid ? [priorBackendPid] : [],
          runtimePaths,
        });
        if (Array.isArray(stopResult?.blockedPids) && stopResult.blockedPids.length) {
          const fallbackPort = await findAvailablePort(config.apiHost).catch(() => 0);
          if (!Number.isFinite(fallbackPort) || fallbackPort <= 0) {
            throw new Error("backend_port_in_use");
          }
          const nextBaseUrl = buildApiBaseUrlWithPort(config.apiBaseUrl, config.apiHost, fallbackPort);
          config = saveCurrentConfig({
            apiPort: fallbackPort,
            apiBaseUrl: nextBaseUrl,
          }, configOptionsForRuntime);
          nextFingerprint = backendConfigFingerprint(config);
          logStartup(
            "backend_port_reassigned",
            `from=${String(runtimeInfo?.apiPort || "")} to=${String(fallbackPort)} blocked_pids=${stopResult.blockedPids.join(",")}`,
          );
        }
      }
      let health = options.forceRestart ? null : await readHealth(config.apiBaseUrl);
      const childExited = Boolean(backendHandle?.child && backendHandle.child.exitCode !== null);
      if (!options.forceRestart && !health && !backendHandle) {
        const existingManagedPids = listeningPids(config.apiPort).filter((pid) =>
          isManagedBackendPid(pid, runtimePaths, priorBackendPid ? [priorBackendPid] : []),
        );
        if (existingManagedPids.length) {
          logStartup("backend_existing_port_wait", `pids=${existingManagedPids.join(",")}`);
          health = await waitForBackend(config.apiBaseUrl, { timeoutMs: 8000 }).catch(() => null);
          if (health) {
            logStartup("backend_existing_port_ready", `pids=${existingManagedPids.join(",")}`);
          } else {
            const stopResult = await stopBackendOnPort(config.apiPort, {
              allowPids: priorBackendPid ? [priorBackendPid] : [],
              runtimePaths,
            });
            if (Array.isArray(stopResult?.blockedPids) && stopResult.blockedPids.length) {
              throw new Error("backend_port_in_use");
            }
            if (Array.isArray(stopResult?.stoppedPids) && stopResult.stoppedPids.length) {
              logStartup("backend_existing_port_cleared", `pids=${stopResult.stoppedPids.join(",")}`);
            }
          }
        }
      }
      if (!health && (!backendHandle || childExited || options.forceRestart)) {
        let startupError = null;
        for (let attempt = 1; attempt <= 2 && !health; attempt += 1) {
          logStartup("backend_spawn_attempt", `attempt=${attempt} port=${String(config.apiPort)}`);
          backendHandle = startBackend(config, runtimePaths);
          attachBackendExitWatcher(backendHandle);
          try {
            health = await waitForBackend(config.apiBaseUrl, { handle: backendHandle });
            backendRestarted = true;
            logStartup(
              "backend_spawn_ready",
              `attempt=${attempt} pid=${String(backendHandle?.child?.pid || "")} elapsed_ms=${String(Date.now() - bootStartedAt)}`,
            );
          } catch (error) {
            startupError = error;
            console.error("[lawcopilot] backend_start_attempt_failed", { attempt, error });
            logStartup(
              "backend_spawn_failed",
              `attempt=${attempt} error=${String(error?.message || error || "unknown")}`,
            );
            await stopBackend(backendHandle).catch(() => null);
            backendHandle = null;
            await stopBackendOnPort(config.apiPort, {
              allowPids: priorBackendPid ? [priorBackendPid] : [],
              runtimePaths,
            }).catch(() => null);
            if (attempt < 2) {
              await new Promise((resolve) => setTimeout(resolve, 750));
            }
          }
        }
        if (!health && startupError) {
          throw startupError;
        }
      }
      if (!health) {
        throw new Error("backend_unreachable");
      }
      const runtimeBootstrapKey = resolveBootstrapKey(config);
      let sessionToken = "";
      try {
        sessionToken = (await createRuntimeToken(config.apiBaseUrl, runtimeBootstrapKey)).access_token;
      } catch (error) {
        const detail = String(error?.message || error || "");
        const shouldRecoverBootstrap = detail.startsWith("token_bootstrap_failed:") && !options.forceRestart;
        if (!shouldRecoverBootstrap) {
          throw error;
        }
        appendBackendLog(
          backendHandle?.outFile || "",
          `bootstrap_token_retry reason=${detail}`,
        );
        await stopBackend(backendHandle).catch(() => null);
        backendHandle = null;
        await stopBackendOnPort(config.apiPort, { runtimePaths }).catch(() => null);
        backendHandle = startBackend(config, runtimePaths);
        attachBackendExitWatcher(backendHandle);
        health = await waitForBackend(config.apiBaseUrl, { handle: backendHandle });
        backendRestarted = true;
        sessionToken = (await createRuntimeToken(config.apiBaseUrl, runtimeBootstrapKey)).access_token;
      }
      runtimeInfo = {
        ...config,
        appVersion: app.getVersion ? app.getVersion() : config.appVersion,
        ...health,
        sessionToken,
        runtimeBootstrapKey,
        backendConfigFingerprint: nextFingerprint,
        backendLogFile: backendHandle?.outFile || runtimeInfo?.backendLogFile || "",
        runtimePaths
      };
      backendConsecutiveHealthFailures = 0;
      startBackendHealthMonitor();
      if (backendRestarted) {
        await syncWorkspaceConfig({ ...config, sessionToken, runtimeBootstrapKey }, { waitForScan: false });
      }
      logStartup(
        "backend_boot_ready",
        `force_restart=${String(Boolean(options.forceRestart))} pid=${String(backendHandle?.child?.pid || "")} elapsed_ms=${String(Date.now() - bootStartedAt)}`,
      );
      return runtimeInfo;
    } finally {
      if (plannedRestart) {
        backendPlannedRestartDepth = Math.max(0, backendPlannedRestartDepth - 1);
      }
    }
  })().finally(() => {
    backendEnsurePromise = null;
  });
  return backendEnsurePromise;
}

async function syncWorkspaceConfig(config, options = {}) {
  if (!config.workspaceRootPath) {
    return;
  }
  const waitForScan = options.waitForScan !== false;
  try {
    const token = config.sessionToken || (await createRuntimeToken(config.apiBaseUrl, resolveBootstrapKey(config))).access_token;
    await fetchWithTimeout(`${config.apiBaseUrl}/workspace`, {
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
      const scanPromise = fetchWithTimeout(`${config.apiBaseUrl}/workspace/scan`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ full_rescan: false }),
      });
      if (waitForScan) {
        await scanPromise;
      } else {
        void scanPromise.catch(() => null);
      }
    }
  } catch {
    return;
  }
}

async function createRuntimeToken(apiBaseUrl, bootstrapKey = "") {
  const payload = { subject: "desktop-runtime", role: "lawyer" };
  if (bootstrapKey) {
    payload.bootstrap_key = bootstrapKey;
  }
  const response = await fetchWithTimeout(`${apiBaseUrl}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`token_bootstrap_failed:${response.status}`);
  }
  return response.json();
}

function normalizeWindowBounds(window) {
  if (!window || window.isDestroyed()) {
    return;
  }
  const fallbackBounds = {
    x: 120,
    y: 80,
    width: 1480,
    height: 980,
  };
  const bounds = window.getBounds();
  const display = screen.getDisplayMatching(bounds);
  const workArea = display?.workArea || fallbackBounds;
  const width = Math.max(1180, Math.min(bounds.width || 0, workArea.width || fallbackBounds.width));
  const height = Math.max(760, Math.min(bounds.height || 0, workArea.height || fallbackBounds.height));
  const x = workArea.x + Math.max(0, Math.round(((workArea.width || fallbackBounds.width) - width) / 2));
  const y = workArea.y + Math.max(0, Math.round(((workArea.height || fallbackBounds.height) - height) / 2));
  const isClearlyOffscreen = (
    bounds.x + 80 < workArea.x
    || bounds.y + 80 < workArea.y
    || bounds.x > workArea.x + workArea.width - 120
    || bounds.y > workArea.y + workArea.height - 120
  );
  const isTooSmall = bounds.width < 1180 || bounds.height < 760;
  if (isTooSmall || isClearlyOffscreen) {
    window.setBounds({
      x,
      y,
      width,
      height,
    });
  }
}

function showMainWindow(window) {
  if (!window || window.isDestroyed()) {
    return;
  }
  normalizeWindowBounds(window);
  if (window.isMinimized()) {
    window.restore();
  }
  if (!window.isVisible()) {
    window.show();
  }
  window.focus();
}

function isSafeExternalUrl(value) {
  try {
    const target = new URL(String(value || "").trim());
    return target.protocol === "https:" || target.protocol === "http:";
  } catch {
    return false;
  }
}

function checkoutWindowTitle(url, draft = {}) {
  const subject = String(draft?.subject || "").trim();
  if (subject) {
    return `${subject} · LawCopilot ödeme`;
  }
  try {
    const target = new URL(String(url || "").trim());
    const host = String(target.hostname || "").replace(/^www\./i, "").trim();
    if (host) {
      return `${host} · LawCopilot ödeme`;
    }
  } catch {
    // Ignore parse issues and fall through to the generic title.
  }
  return "LawCopilot ödeme";
}

function focusAuxWindow(window) {
  if (!window || window.isDestroyed()) {
    return;
  }
  if (window.isMinimized()) {
    window.restore();
  }
  if (!window.isVisible()) {
    window.show();
  }
  window.focus();
}

async function openSecureCheckoutWindow(url, { draft = {} } = {}) {
  const target = String(url || "").trim();
  if (!isSafeExternalUrl(target)) {
    throw new Error("Ödeme bağlantısı güvenli bir http/https adresi değil.");
  }

  if (checkoutWindow && !checkoutWindow.isDestroyed()) {
    checkoutWindow.setTitle(checkoutWindowTitle(target, draft));
    await checkoutWindow.loadURL(target);
    focusAuxWindow(checkoutWindow);
    return checkoutWindow;
  }

  const parentWindow = mainWindow && !mainWindow.isDestroyed() ? mainWindow : null;
  const window = new BrowserWindow({
    width: 1240,
    height: 920,
    minWidth: 980,
    minHeight: 720,
    title: checkoutWindowTitle(target, draft),
    backgroundColor: "#102123",
    show: false,
    autoHideMenuBar: true,
    parent: parentWindow || undefined,
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
      spellcheck: false,
      partition: "persist:lawcopilot-checkout",
    },
  });
  window.removeMenu();
  checkoutWindow = window;

  const openNext = (nextUrl) => {
    const normalized = String(nextUrl || "").trim();
    if (!normalized) {
      return;
    }
    if (isSafeExternalUrl(normalized)) {
      void window.loadURL(normalized).catch(() => {
        void shell.openExternal(normalized).catch(() => null);
      });
      return;
    }
    void shell.openExternal(normalized).catch(() => null);
  };

  window.webContents.setWindowOpenHandler(({ url: nextUrl }) => {
    openNext(nextUrl);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event, nextUrl) => {
    const normalized = String(nextUrl || "").trim();
    if (isSafeExternalUrl(normalized)) {
      return;
    }
    event.preventDefault();
    void shell.openExternal(normalized).catch(() => null);
  });
  window.webContents.on("did-navigate", (_event, navigatedUrl) => {
    if (!window.isDestroyed()) {
      window.setTitle(checkoutWindowTitle(navigatedUrl, draft));
    }
  });
  window.on("closed", () => {
    if (checkoutWindow === window) {
      checkoutWindow = null;
    }
  });
  window.once("ready-to-show", () => {
    focusAuxWindow(window);
  });
  await window.loadURL(target);
  focusAuxWindow(window);
  return window;
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
  let revealTimer = null;
  let revealed = false;
  const revealWindow = () => {
    if (revealed || window.isDestroyed()) {
      return;
    }
    revealed = true;
    if (revealTimer) {
      clearTimeout(revealTimer);
      revealTimer = null;
    }
    logStartup("window_revealed");
    showMainWindow(window);
  };
  const entryFile = path.join(runtimePaths.uiDist, "index.html");
  if (String(process.env.LAWCOPILOT_CLEAR_CACHE_ON_BOOT || "").trim() === "1") {
    await window.webContents.session.clearCache();
  }
  window.webContents.setWindowOpenHandler(({ url }) => {
    const target = String(url || "").trim();
    if (/^https?:\/\//i.test(target)) {
      void openUrlPreferChrome(target);
      return { action: "deny" };
    }
    return { action: "allow" };
  });
  window.webContents.on("will-navigate", (event, url) => {
    const target = String(url || "").trim();
    const current = String(window.webContents.getURL() || "").trim();
    if (!/^https?:\/\//i.test(target)) {
      return;
    }
    if (target === current) {
      return;
    }
    event.preventDefault();
    void openUrlPreferChrome(target);
  });
  window.once("ready-to-show", () => {
    logStartup("window_ready_to_show");
    revealWindow();
  });
  window.webContents.once("did-finish-load", () => {
    logStartup("window_did_finish_load");
    revealWindow();
  });
  window.webContents.once("did-fail-load", (_event, errorCode, errorDescription, validatedUrl, isMainFrame) => {
    logStartup(
      "window_load_failed",
      `code=${String(errorCode)} main_frame=${String(Boolean(isMainFrame))} url=${String(validatedUrl || "").trim()} detail=${String(errorDescription || "").trim()}`,
    );
    revealWindow();
  });
  window.webContents.on("render-process-gone", (_event, details) => {
    logStartup(
      "window_render_gone",
      `reason=${String(details?.reason || "unknown")} exit_code=${String(details?.exitCode ?? "")}`,
    );
  });
  window.on("unresponsive", () => {
    logStartup("window_unresponsive");
  });
  window.on("responsive", () => {
    logStartup("window_responsive");
  });
  revealTimer = setTimeout(revealWindow, 2500);
  try {
    await window.loadFile(entryFile);
  } catch (error) {
    console.error("[lawcopilot] ui_load_failed", error);
    revealWindow();
  }
  window.on("closed", () => {
    logStartup("window_closed");
    if (mainWindow === window) {
      mainWindow = null;
    }
    if (revealTimer) {
      clearTimeout(revealTimer);
      revealTimer = null;
    }
  });
  mainWindow = window;
  return window;
}

async function ensureMainWindow(runtimePathsOverride = null) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    showMainWindow(mainWindow);
    return mainWindow;
  }
  if (mainWindowPromise) {
    return mainWindowPromise;
  }
  const runtimePaths =
    runtimePathsOverride
    ||
    runtimeInfo?.runtimePaths
    || resolveRuntimePaths({
      repoRoot: path.resolve(__dirname, "..", ".."),
      isPackaged: app.isPackaged,
      resourcesPath: process.resourcesPath,
      userDataPath: app.getPath("userData"),
    });
  mainWindowPromise = createWindow(runtimePaths)
    .finally(() => {
      mainWindowPromise = null;
    });
  return mainWindowPromise;
}

if (String(process.env.LAWCOPILOT_DISABLE_GPU || "").trim() === "1") {
  app.disableHardwareAcceleration();
}
if (!hasSingleInstanceLock && !singleInstanceFallbackAllowed) {
  logStartup("desktop_quit", "single_instance_lock_denied");
  app.quit();
} else if (!hasSingleInstanceLock) {
  logStartup("single_instance_lock_recovered", "stale_lock_suspected");
}
app.on("second-instance", () => {
  void ensureMainWindow().catch((error) => {
    console.error("[lawcopilot] second_instance_window_failed", error);
  });
});
app.on("activate", () => {
  void ensureMainWindow().catch((error) => {
    console.error("[lawcopilot] activate_window_failed", error);
  });
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.whenReady()
  .then(async () => {
    if (startupSuppressed) {
      logStartup("startup_skipped", "single_instance_lock_denied");
      return;
    }
    logStartup("app_ready");
    Menu.setApplicationMenu(null);
    const runtimePaths = resolveRuntimePaths({
      repoRoot: path.resolve(__dirname, "..", ".."),
      isPackaged: app.isPackaged,
      resourcesPath: process.resourcesPath,
      userDataPath: app.getPath("userData"),
    });
    const runtimeBootPromise = bootRuntime(runtimePaths).catch((error) => {
      throw error;
    });
    if (isDesktopSmoke) {
      const { runtimePaths: bootedRuntimePaths } = await runtimeBootPromise;
      logStartup("backend_ready", bootedRuntimePaths.apiBinary);
      setTimeout(() => app.quit(), Math.max(250, DESKTOP_SMOKE_HOLD_MS));
      return;
    }
    await ensureMainWindow(runtimePaths);
    logStartup("window_created");
    const updaterController = ensureDesktopUpdater();
    const { runtimePaths: bootedRuntimePaths } = await runtimeBootPromise;
    logStartup("backend_ready", bootedRuntimePaths.apiBinary);
    await activateCodexProviderFromOAuthStatus().catch((error) => {
      console.error("[lawcopilot] codex_provider_activation_failed", error);
    });
    scheduleWhatsAppWebAutostart();
    startDesktopAutomation();
    startConnectedServicesSync();
    void updaterController.maybeAutoCheckOnLaunch().catch((error) => {
      console.error("[lawcopilot] updater_auto_check_failed", error);
    });
  })
  .catch((error) => {
    const detail = error?.stack || error?.message || String(error || "unknown_startup_error");
    logStartup("startup_failed", detail);
    stopBackendHealthMonitor();
    clearBackendRecoveryTimer();
    clearRuntimePidFiles(runtimeInfo?.runtimePaths, runtimeInfo?.storagePath);
    console.error("[lawcopilot] startup_failed", error);
    try {
      dialog.showErrorBox("LawCopilot baslatilamadi", String(error?.message || error || "Bilinmeyen hata"));
    } catch {
      // Ignore dialog failures in headless or degraded desktop sessions.
    }
    app.quit();
  });

app.on("before-quit", (event) => {
  logStartup("before_quit");
  stopDesktopSpeech();
  if (quitCleanupPromise) {
    event.preventDefault();
    return;
  }
  appQuitInFlight = true;
  stopDesktopAutomation();
  stopConnectedServicesSync();
  stopBackendHealthMonitor();
  clearBackendRecoveryTimer();
  if (!backendHandle?.child || backendHandle.child.exitCode !== null) {
    const runtimePaths = runtimeInfo?.runtimePaths;
    if (!runtimePaths || !runtimeInfo?.apiPort) {
      clearRuntimePidFiles(runtimeInfo?.runtimePaths, runtimeInfo?.storagePath);
      return;
    }
    event.preventDefault();
    quitCleanupPromise = (async () => {
      try {
        await stopBackendOnPort(runtimeInfo.apiPort, {
          allowPids: [],
          runtimePaths,
        }).catch(() => null);
        clearRuntimePidFiles(runtimePaths, runtimeInfo?.storagePath);
        logStartup("backend_stopped_for_quit");
      } finally {
        setTimeout(() => app.exit(0), 0);
      }
    })();
    return;
  }
  event.preventDefault();
  quitCleanupPromise = (async () => {
    try {
      const runtimePaths = runtimeInfo?.runtimePaths;
      await stopBackend(backendHandle).catch(() => null);
      if (runtimePaths) {
        await stopBackendOnPort(runtimeInfo?.apiPort, {
          allowPids: [],
          runtimePaths,
        }).catch(() => null);
      }
      backendHandle = null;
      clearRuntimePidFiles(runtimePaths, runtimeInfo?.storagePath);
      logStartup("backend_stopped_for_quit");
    } finally {
      setTimeout(() => app.exit(0), 0);
    }
  })();
});

app.on("quit", () => {
  appQuitInFlight = true;
  stopConnectedServicesSync();
  stopBackendHealthMonitor();
  clearBackendRecoveryTimer();
  clearRuntimePidFiles(runtimeInfo?.runtimePaths, runtimeInfo?.storagePath);
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
ipcMain.handle("lawcopilot:get-desktop-tts-voices", async () => getDesktopTtsVoices());
ipcMain.handle("lawcopilot:speak-text", async (_event, payload) => speakDesktopText(payload || {}));
ipcMain.handle("lawcopilot:stop-speaking", async () => stopDesktopSpeech());
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
  const { saved, runtimeWarning } = await saveConfigWithRefresh(patch || {});
  ensureDesktopUpdater().refreshFromConfig();
  startDesktopAutomation();
  void runReminderAutomationTick();
  return {
    ...sanitizeDesktopConfig(saved),
    runtimeWarning,
  };
});
ipcMain.handle("lawcopilot:get-update-status", async () => ensureDesktopUpdater().getStatus());
ipcMain.handle("lawcopilot:check-for-updates", async () => ensureDesktopUpdater().checkForUpdates("manual"));
ipcMain.handle("lawcopilot:download-update", async () => ensureDesktopUpdater().downloadUpdate());
ipcMain.handle("lawcopilot:quit-and-install-update", async () => ensureDesktopUpdater().quitAndInstall());
ipcMain.handle("lawcopilot:save-location-snapshot", async (_event, payload) => saveLocationSnapshot(payload || {}));
ipcMain.handle("lawcopilot:get-integration-config", async () => {
  const config = loadCurrentConfig();
  return sanitizeDesktopConfig(config);
});
ipcMain.handle("lawcopilot:save-integration-config", async (_event, patch) => {
  const { saved, runtimeWarning } = await saveConfigWithRefresh(patch || {});
  ensureDesktopUpdater().refreshFromConfig();
  startDesktopAutomation();
  void runReminderAutomationTick();
  return {
    ...sanitizeDesktopConfig(saved),
    runtimeWarning,
  };
});
ipcMain.handle("lawcopilot:save-integration-config-fast", async (_event, patch) => {
  const { saved, runtimeWarning } = saveConfigWithoutRefresh(patch || {});
  ensureDesktopUpdater().refreshFromConfig();
  startDesktopAutomation();
  void runReminderAutomationTick();
  return {
    ...sanitizeDesktopConfig(saved),
    runtimeWarning,
  };
});
ipcMain.handle("lawcopilot:run-assistant-legacy-setup", async (_event, payload) => runAssistantLegacySetup(payload || {}));
ipcMain.handle("lawcopilot:validate-provider-config", async (_event, payload) => {
  const config = loadCurrentConfig();
  return validateProviderConfig(providerPatchForValidation(payload || {}, config));
});
ipcMain.handle("lawcopilot:validate-telegram-config", async (_event, payload) => validateTelegramConfig(payload || {}));
ipcMain.handle("lawcopilot:get-telegram-status", async () => {
  const config = loadCurrentConfig();
  return getTelegramStatus(config);
});
ipcMain.handle("lawcopilot:start-telegram-web-link", async () => {
  const config = loadCurrentConfig();
  return startTelegramWebLink(config);
});
ipcMain.handle("lawcopilot:get-codex-auth-status", async () => {
  const result = await activateCodexProviderFromOAuthStatus();
  return result.status;
});
ipcMain.handle("lawcopilot:start-codex-auth", async () => {
  const config = loadCurrentConfig();
  const status = await startCodexOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl), { waitForAuthUrl: false });
  return status;
});
ipcMain.handle("lawcopilot:submit-codex-auth-callback", async (_event, callbackUrl) => {
  const config = loadCurrentConfig();
  const status = await submitCodexOAuthCallback(config, String(callbackUrl || ""));
  const codexDefaults = providerDefaults("openai-codex");
  const saved = saveCurrentConfig({
    provider: {
      type: "openai-codex",
      authMode: "oauth",
      baseUrl: "oauth://openai-codex",
      model: status.selectedModel || config.provider?.model || codexDefaults.model,
      apiKey: "",
      accountLabel: "OpenAI hesabı (Codex OAuth)",
      availableModels: status.catalogModels || status.availableModels || [],
      oauthConnected: Boolean(status.configured),
      oauthLastError: "",
      configuredAt: status.configured ? new Date().toISOString() : config.provider?.configuredAt || "",
      lastValidatedAt: new Date().toISOString(),
      validationStatus: status.configured ? "valid" : "invalid",
    },
  });
  await refreshBackendAfterConfigChange();
  return {
    status,
    config: sanitizeDesktopConfig(saved),
  };
});
ipcMain.handle("lawcopilot:cancel-codex-auth", async () => cancelCodexOAuth());
ipcMain.handle("lawcopilot:set-codex-model", async (_event, model) => {
  const config = loadCurrentConfig();
  const status = await setCodexModel(config, String(model || ""));
  const saved = saveCurrentConfig({
    provider: {
      type: "openai-codex",
      authMode: "oauth",
      baseUrl: "oauth://openai-codex",
      model: status.selectedModel || String(model || ""),
      apiKey: "",
      accountLabel: "OpenAI hesabı (Codex OAuth)",
      availableModels: status.catalogModels || status.availableModels || [],
      oauthConnected: Boolean(status.configured),
      oauthLastError: status.error || "",
      configuredAt: config.provider?.configuredAt || new Date().toISOString(),
      lastValidatedAt: new Date().toISOString(),
      validationStatus: status.configured ? "valid" : "pending",
    },
  });
  await refreshBackendAfterConfigChange();
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
    void scheduleGooglePostAuthSync(saved);
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
ipcMain.handle("lawcopilot:get-google-portability-auth-status", async () => {
  const config = loadCurrentConfig();
  const completed = consumeCompletedGooglePortabilityOAuth();
  if (completed?.status) {
    const saved = saveCurrentConfig({
      googlePortability: {
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
    void scheduleGooglePortabilityPostAuthSync(saved);
    return getGooglePortabilityAuthStatus(loadCurrentConfig());
  }
  if (completed?.error) {
    return {
      ...getGooglePortabilityAuthStatus(config),
      authStatus: "hata",
      message: completed.error,
      error: completed.error,
    };
  }
  return getGooglePortabilityAuthStatus(config);
});
ipcMain.handle("lawcopilot:start-google-auth", async () => {
  const config = loadCurrentConfig();
  const status = await startGoogleOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
  return status;
});
ipcMain.handle("lawcopilot:start-google-portability-auth", async () => {
  const config = loadCurrentConfig();
  const status = await startGooglePortabilityOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
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
  void scheduleGooglePostAuthSync(saved);
  return {
    status,
    config: sanitizeDesktopConfig(saved),
  };
});
ipcMain.handle("lawcopilot:submit-google-portability-auth-callback", async (_event, callbackUrl) => {
  const config = loadCurrentConfig();
  const status = await submitGooglePortabilityOAuthCallback(config, String(callbackUrl || ""));
  const saved = saveCurrentConfig({
    googlePortability: {
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
  void scheduleGooglePortabilityPostAuthSync(saved);
  return {
    status,
    config: sanitizeDesktopConfig(saved),
  };
});
ipcMain.handle("lawcopilot:cancel-google-auth", async () => {
  const config = loadCurrentConfig();
  return cancelGoogleOAuth(config);
});
ipcMain.handle("lawcopilot:cancel-google-portability-auth", async () => {
  const config = loadCurrentConfig();
  return cancelGooglePortabilityOAuth(config);
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
ipcMain.handle("lawcopilot:sync-google-portability-data", async () => {
  const config = loadCurrentConfig();
  const currentRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
  const result = await syncGooglePortabilityData(config, currentRuntime);
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:import-google-history-archive", async (_event, filePaths) => {
  const config = loadCurrentConfig();
  const currentRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
  const result = await importGoogleTakeoutData(config, currentRuntime, Array.isArray(filePaths) ? filePaths : []);
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:get-outlook-auth-status", async () => {
  const config = loadCurrentConfig();
  return getOutlookAuthStatus(config);
});
ipcMain.handle("lawcopilot:start-outlook-auth", async () => {
  const config = loadCurrentConfig();
  const status = await startOutlookOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
  const saved = saveCurrentConfig({
    outlook: {
      enabled: true,
      accountLabel: status.accountLabel,
      tenantId: status.tenantId || config.outlook?.tenantId || "common",
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
    const syncResult = await syncOutlookData(saved, refreshedRuntime).catch(() => null);
    if (syncResult?.patch) {
      saveCurrentConfig(syncResult.patch);
    }
  }
  return status;
});
ipcMain.handle("lawcopilot:cancel-outlook-auth", async () => {
  const config = loadCurrentConfig();
  return cancelOutlookOAuth(config);
});
ipcMain.handle("lawcopilot:sync-outlook-data", async () => {
  const config = loadCurrentConfig();
  const currentRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
  const result = await syncOutlookData(config, currentRuntime);
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
ipcMain.handle("lawcopilot:start-whatsapp-web-link", async () => {
  const config = loadCurrentConfig();
  return connectWhatsAppWeb(config);
});
ipcMain.handle("lawcopilot:sync-whatsapp-data", async () => {
  const config = loadCurrentConfig();
  const currentRuntime = runtimeInfo || (await ensureBackendRunning({ forceRestart: false }).catch(() => null));
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
ipcMain.handle("lawcopilot:disconnect-whatsapp", async () => {
  const config = loadCurrentConfig();
  const result = await disconnectWhatsApp(config);
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
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
    await runProviderSync("x", () => syncXData(saved, refreshedRuntime), "x_sync_timeout", { errorField: "oauthLastError" });
  }
  return {
    ...status,
    ...getXAuthStatus(loadCurrentConfig()),
  };
});
ipcMain.handle("lawcopilot:cancel-x-auth", async () => {
  const config = loadCurrentConfig();
  const result = cancelXOAuth(config);
  if (result.patch) {
    saveCurrentConfig(result.patch);
    await refreshBackendAfterConfigChange().catch(() => null);
  }
  return result;
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
ipcMain.handle("lawcopilot:send-x-direct-message", async (_event, payload) => {
  const config = loadCurrentConfig();
  const result = await sendXDirectMessage(config, payload || {});
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:get-linkedin-auth-status", async () => {
  const config = loadCurrentConfig();
  return getLinkedInAuthStatus(config);
});
ipcMain.handle("lawcopilot:get-linkedin-status", async () => {
  const config = loadCurrentConfig();
  return getLinkedInStatus(config);
});
ipcMain.handle("lawcopilot:start-linkedin-auth", async () => {
  const config = loadCurrentConfig();
  const status = await startLinkedInOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
  const saved = saveCurrentConfig({
    linkedin: {
      enabled: true,
      accountLabel: status.accountLabel,
      userId: status.userId || "",
      personUrn: status.personUrn || "",
      email: status.email || "",
      scopes: status.scopes || [],
      oauthConnected: Boolean(status.configured),
      oauthLastError: "",
      configuredAt: new Date().toISOString(),
      lastValidatedAt: new Date().toISOString(),
      validationStatus: status.configured ? "valid" : "invalid",
      accessToken: status.accessToken || "",
      tokenType: status.tokenType || "",
      expiryDate: status.expiryDate || "",
      lastSyncAt: new Date().toISOString(),
    },
  });
  const refreshedRuntime = await refreshBackendAfterConfigChange().catch(() => null);
  if (refreshedRuntime) {
    await runProviderSync("linkedin", () => syncLinkedInData(saved, refreshedRuntime), "linkedin_sync_timeout", { errorField: "oauthLastError" });
  }
  return {
    ...status,
    config: sanitizeDesktopConfig(loadCurrentConfig()),
  };
});
ipcMain.handle("lawcopilot:start-linkedin-web-link", async () => {
  const config = loadCurrentConfig();
  return startLinkedInWebLink(config);
});
ipcMain.handle("lawcopilot:cancel-linkedin-auth", async () => {
  const config = loadCurrentConfig();
  return cancelLinkedInOAuth(config);
});
ipcMain.handle("lawcopilot:post-linkedin-update", async (_event, payload) => {
  const config = loadCurrentConfig();
  const result = await postLinkedInUpdate(config, payload || {});
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:sync-linkedin-data", async () => {
  const config = loadCurrentConfig();
  const currentRuntime = await ensureBackendRuntime();
  const result = await syncLinkedInData(config, currentRuntime);
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:get-instagram-auth-status", async () => {
  const config = loadCurrentConfig();
  return getInstagramAuthStatus(config);
});
ipcMain.handle("lawcopilot:start-instagram-auth", async () => {
  const config = loadCurrentConfig();
  const status = await startInstagramOAuth(config, async (authUrl) => openUrlPreferChrome(authUrl));
  const saved = saveCurrentConfig({
    instagram: {
      enabled: true,
      accountLabel: status.accountLabel || "",
      username: status.username || "",
      pageId: status.pageId || "",
      pageName: status.pageName || "",
      instagramAccountId: status.instagramAccountId || "",
      scopes: status.scopes || [],
      oauthConnected: Boolean(status.configured),
      oauthLastError: "",
      configuredAt: new Date().toISOString(),
      lastValidatedAt: new Date().toISOString(),
      validationStatus: status.configured ? "valid" : "invalid",
      accessToken: status.accessToken || "",
      pageAccessToken: status.pageAccessToken || "",
      tokenType: status.tokenType || "",
      expiryDate: status.expiryDate || "",
      lastSyncAt: new Date().toISOString(),
    },
  });
  const refreshedRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
  if (status.configured) {
    await runProviderSync("instagram", () => syncInstagramData(saved, refreshedRuntime), "instagram_sync_timeout", { errorField: "oauthLastError" });
  }
  return {
    ...status,
    config: sanitizeDesktopConfig(loadCurrentConfig()),
  };
});
ipcMain.handle("lawcopilot:cancel-instagram-auth", async () => {
  const config = loadCurrentConfig();
  return cancelInstagramOAuth(config);
});
ipcMain.handle("lawcopilot:sync-instagram-data", async () => {
  const config = loadCurrentConfig();
  const currentRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
  const result = await syncInstagramData(config, currentRuntime);
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
});
ipcMain.handle("lawcopilot:send-instagram-message", async (_event, payload) => {
  const config = loadCurrentConfig();
  const result = await sendInstagramMessage(config, payload || {});
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
ipcMain.handle("lawcopilot:sync-telegram-data", async () => {
  const config = loadCurrentConfig();
  const currentRuntime = (await refreshBackendAfterConfigChange().catch(() => null)) || runtimeInfo;
  const result = await syncTelegramData(config, currentRuntime);
  if (result.patch) {
    saveCurrentConfig(result.patch);
  }
  return result;
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
  const saved = saveCurrentConfig(
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
ipcMain.handle("lawcopilot:choose-google-history-archive", async () => {
  const result = await dialog.showOpenDialog(mainWindow || undefined, {
    title: "Google Takeout geçmiş dosyasını seç",
    properties: ["openFile", "openDirectory", "multiSelections"],
    filters: [
      { name: "Google Takeout", extensions: ["zip", "json", "ndjson", "html", "htm"] },
      { name: "ZIP arşivleri", extensions: ["zip"] },
      { name: "JSON dosyaları", extensions: ["json", "ndjson"] },
      { name: "HTML dosyaları", extensions: ["html", "htm"] },
      { name: "Tüm dosyalar", extensions: ["*"] },
    ],
  });
  return {
    canceled: Boolean(result.canceled),
    filePaths: Array.isArray(result.filePaths) ? result.filePaths : [],
  };
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
