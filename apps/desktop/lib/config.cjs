const fs = require("fs");
const os = require("os");
const path = require("path");

function repoRootFrom(baseDir) {
  return path.resolve(baseDir, "..", "..", "..");
}

function defaultDesktopConfig(repoRoot, options = {}) {
  const artifactsRoot = options.storagePath || path.join(repoRoot, "artifacts");
  return {
    appName: "LawCopilot",
    appVersion: "0.7.0-pilot.1",
    officeId: process.env.LAWCOPILOT_OFFICE_ID || "default-office",
    deploymentMode: process.env.LAWCOPILOT_DEPLOYMENT_MODE || "local-only",
    releaseChannel: process.env.LAWCOPILOT_RELEASE_CHANNEL || "pilot",
    locale: "tr",
    selectedModelProfile: process.env.LAWCOPILOT_DEFAULT_MODEL_PROFILE || "hybrid",
    apiHost: "127.0.0.1",
    apiPort: 18731,
    apiBaseUrl: "http://127.0.0.1:18731",
    logLevel: "info",
    storagePath: artifactsRoot,
    envFile: path.join(artifactsRoot, "runtime", "pilot.env"),
    scanOnStartup: true,
    workspaceRootPath: "",
    workspaceRootName: "",
    workspaceRootHash: "",
    provider: {
      type: "openai",
      baseUrl: "https://api.openai.com/v1",
      model: "gpt-4.1-mini",
      apiKey: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
    },
    telegram: {
      enabled: false,
      botToken: "",
      botUsername: "",
      allowedUserId: "",
      configuredAt: "",
      lastValidatedAt: "",
      validationStatus: "pending",
    },
  };
}

function mergeDesktopConfig(current, patch) {
  const next = { ...current, ...patch };
  next.provider = { ...(current.provider || {}), ...(patch.provider || {}) };
  next.telegram = { ...(current.telegram || {}), ...(patch.telegram || {}) };
  return next;
}

function maskSecret(value) {
  const text = String(value || "");
  if (!text) {
    return "";
  }
  if (text.length <= 8) {
    return `${"*".repeat(Math.max(0, text.length - 2))}${text.slice(-2)}`;
  }
  return `${text.slice(0, 3)}${"*".repeat(Math.max(0, text.length - 7))}${text.slice(-4)}`;
}

function sanitizeDesktopConfig(config) {
  const provider = config.provider || {};
  const telegram = config.telegram || {};
  return {
    ...config,
    provider: {
      type: provider.type || "openai",
      baseUrl: provider.baseUrl || "",
      model: provider.model || "",
      configuredAt: provider.configuredAt || "",
      lastValidatedAt: provider.lastValidatedAt || "",
      validationStatus: provider.validationStatus || "pending",
      apiKeyConfigured: Boolean(provider.apiKey),
      apiKeyMasked: maskSecret(provider.apiKey),
    },
    telegram: {
      enabled: Boolean(telegram.enabled),
      botUsername: telegram.botUsername || "",
      allowedUserId: telegram.allowedUserId || "",
      configuredAt: telegram.configuredAt || "",
      lastValidatedAt: telegram.lastValidatedAt || "",
      validationStatus: telegram.validationStatus || "pending",
      botTokenConfigured: Boolean(telegram.botToken),
      botTokenMasked: maskSecret(telegram.botToken),
    },
  };
}

function resolveConfigDir(options = {}) {
  if (options.overrideDir) {
    return options.overrideDir;
  }
  if (process.env.LAWCOPILOT_DESKTOP_CONFIG_DIR) {
    return process.env.LAWCOPILOT_DESKTOP_CONFIG_DIR;
  }
  return path.join(os.homedir(), ".config", "LawCopilot");
}

function configFilePath(options = {}) {
  return path.join(resolveConfigDir(options), "desktop-config.json");
}

function loadDesktopConfig(options = {}) {
  const repoRoot = options.repoRoot || repoRootFrom(__dirname);
  const defaults = defaultDesktopConfig(repoRoot, options);
  const filePath = configFilePath(options);
  if (!fs.existsSync(filePath)) {
    return defaults;
  }
  try {
    return mergeDesktopConfig(defaults, JSON.parse(fs.readFileSync(filePath, "utf-8")));
  } catch {
    return defaults;
  }
}

function saveDesktopConfig(patch, options = {}) {
  const dir = resolveConfigDir(options);
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const current = loadDesktopConfig(options);
  const next = mergeDesktopConfig(current, patch || {});
  if (next.storagePath && (!next.envFile || next.envFile.startsWith(path.join(current.storagePath || "", "runtime")))) {
    next.envFile = path.join(next.storagePath, "runtime", "pilot.env");
  }
  fs.writeFileSync(configFilePath(options), JSON.stringify(next, null, 2), { mode: 0o600 });
  return next;
}

function resolveRuntimePaths(options = {}) {
  const repoRoot = options.repoRoot || repoRootFrom(__dirname);
  const isPackaged = Boolean(options.isPackaged);
  const resourcesPath = options.resourcesPath || path.join(repoRoot, "apps", "desktop");
  const artifactsRoot =
    options.artifactsRoot
    || (isPackaged ? path.join(options.userDataPath || path.join(os.homedir(), ".config", "LawCopilot"), "artifacts") : path.join(repoRoot, "artifacts"));
  return {
    repoRoot,
    uiDist: isPackaged ? path.join(resourcesPath, "ui-dist") : path.join(repoRoot, "apps", "ui", "dist"),
    apiRoot: isPackaged ? path.join(resourcesPath, "api-bin") : path.join(repoRoot, "apps", "api"),
    backendBinRoot: isPackaged ? path.join(resourcesPath, "api-bin") : path.join(repoRoot, "apps", "api", "dist"),
    artifactsRoot,
    isPackaged,
  };
}

module.exports = {
  configFilePath,
  defaultDesktopConfig,
  loadDesktopConfig,
  resolveConfigDir,
  resolveRuntimePaths,
  sanitizeDesktopConfig,
  saveDesktopConfig
};
