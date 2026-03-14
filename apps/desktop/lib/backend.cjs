const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const DEFAULT_BACKEND_BOOT_TIMEOUT_MS = Number(process.env.LAWCOPILOT_BACKEND_BOOT_TIMEOUT_MS || 60000);

function normalizeGoogleScopes(scopes) {
  const defaults = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
  ];
  const merged = [];
  for (const scope of [...defaults, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function parseEnvFile(filePath) {
  if (!filePath || !fs.existsSync(filePath)) {
    return {};
  }
  const out = {};
  const lines = fs.readFileSync(filePath, "utf-8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) {
      continue;
    }
    const [key, ...rest] = trimmed.split("=");
    out[key] = rest.join("=").trim();
  }
  return out;
}

function findPythonBinary(apiRoot) {
  const candidates = [
    path.join(apiRoot, ".venv", "bin", "python"),
    path.join(apiRoot, ".venv", "Scripts", "python.exe"),
    "python3",
    "python"
  ];
  return candidates.find((candidate) => candidate === "python3" || candidate === "python" || fs.existsSync(candidate));
}

function findBackendBinary(runtimePaths) {
  const platform = process.platform;
  const arch = process.arch;
  const candidates = [];
  if (platform === "win32") {
    candidates.push(path.join(runtimePaths.backendBinRoot, "lawcopilot-api.exe"));
  } else if (platform === "darwin") {
    candidates.push(path.join(runtimePaths.backendBinRoot, `lawcopilot-api-${arch}`));
    candidates.push(path.join(runtimePaths.backendBinRoot, "lawcopilot-api"));
  } else {
    candidates.push(path.join(runtimePaths.backendBinRoot, "lawcopilot-api"));
    candidates.push(path.join(runtimePaths.backendBinRoot, `lawcopilot-api-${arch}`));
  }
  return candidates.find((candidate) => fs.existsSync(candidate));
}

function backendEnv(config, runtimePaths) {
  const fileEnv = parseEnvFile(config.envFile);
  const storageRoot = config.storagePath || runtimePaths.artifactsRoot;
  const provider = config.provider || {};
  const google = config.google || {};
  const telegram = config.telegram || {};
  const whatsapp = config.whatsapp || {};
  const x = config.x || {};
  const googleScopes = normalizeGoogleScopes(google.scopes);
  const providerConfigured = Boolean(provider.apiKey || provider.oauthConnected || provider.type === "ollama");
  const openclawEnabled = provider.type === "openai-codex";
  return {
    ...process.env,
    ...fileEnv,
    LAWCOPILOT_APP_NAME: config.appName,
    LAWCOPILOT_APP_VERSION: config.appVersion,
    LAWCOPILOT_OFFICE_ID: config.officeId,
    LAWCOPILOT_DEPLOYMENT_MODE: config.deploymentMode,
    LAWCOPILOT_RELEASE_CHANNEL: config.releaseChannel,
    LAWCOPILOT_DEFAULT_MODEL_PROFILE: config.selectedModelProfile || "hybrid",
    LAWCOPILOT_DESKTOP_SHELL: "electron",
    LAWCOPILOT_ENVIRONMENT: process.env.LAWCOPILOT_ENVIRONMENT || "pilot",
    LAWCOPILOT_AUDIT_LOG: path.join(storageRoot, "audit.log.jsonl"),
    LAWCOPILOT_STRUCTURED_LOG: path.join(storageRoot, "events.log.jsonl"),
    LAWCOPILOT_DB_PATH: path.join(storageRoot, "lawcopilot.db"),
    LAWCOPILOT_CONNECTOR_DRY_RUN: "false",
    LAWCOPILOT_PROVIDER_TYPE: provider.type || "",
    LAWCOPILOT_PROVIDER_BASE_URL: provider.baseUrl || "",
    LAWCOPILOT_PROVIDER_MODEL: provider.model || "",
    LAWCOPILOT_PROVIDER_API_KEY: provider.apiKey || "",
    LAWCOPILOT_PROVIDER_CONFIGURED: providerConfigured ? "true" : "false",
    ...(openclawEnabled
      ? {
          LAWCOPILOT_OPENCLAW_STATE_DIR: path.join(storageRoot, "openclaw-state"),
          LAWCOPILOT_OPENCLAW_IMAGE: process.env.LAWCOPILOT_OPENCLAW_IMAGE || "openclaw-local:chromium",
          LAWCOPILOT_OPENCLAW_TIMEOUT: process.env.LAWCOPILOT_OPENCLAW_TIMEOUT || "75",
        }
      : {}),
    LAWCOPILOT_GOOGLE_ENABLED: google.enabled ? "true" : "false",
    LAWCOPILOT_GOOGLE_CONFIGURED: google.oauthConnected && google.accessToken ? "true" : "false",
    LAWCOPILOT_GOOGLE_ACCOUNT_LABEL: google.accountLabel || "",
    LAWCOPILOT_GOOGLE_SCOPES: googleScopes.join(","),
    LAWCOPILOT_GMAIL_CONNECTED: google.oauthConnected && googleScopes.some((scope) => String(scope).includes("gmail")) ? "true" : "false",
    LAWCOPILOT_CALENDAR_CONNECTED: google.oauthConnected && googleScopes.some((scope) => String(scope).includes("calendar")) ? "true" : "false",
    LAWCOPILOT_DRIVE_CONNECTED: google.oauthConnected && googleScopes.some((scope) => String(scope).includes("drive")) ? "true" : "false",
    LAWCOPILOT_TELEGRAM_ENABLED: telegram.enabled ? "true" : "false",
    LAWCOPILOT_TELEGRAM_BOT_TOKEN: telegram.botToken || "",
    LAWCOPILOT_TELEGRAM_BOT_USERNAME: telegram.botUsername || "",
    LAWCOPILOT_TELEGRAM_ALLOWED_USER_ID: telegram.allowedUserId || "",
    LAWCOPILOT_TELEGRAM_CONFIGURED: telegram.botToken && telegram.allowedUserId ? "true" : "false",
    LAWCOPILOT_WHATSAPP_ENABLED: whatsapp.enabled ? "true" : "false",
    LAWCOPILOT_WHATSAPP_CONFIGURED: whatsapp.enabled && whatsapp.accessToken && whatsapp.phoneNumberId ? "true" : "false",
    LAWCOPILOT_WHATSAPP_ACCOUNT_LABEL: whatsapp.businessLabel || whatsapp.verifiedName || whatsapp.displayPhoneNumber || "",
    LAWCOPILOT_WHATSAPP_PHONE_NUMBER_ID: whatsapp.phoneNumberId || "",
    LAWCOPILOT_WHATSAPP_DISPLAY_PHONE_NUMBER: whatsapp.displayPhoneNumber || "",
    LAWCOPILOT_X_ENABLED: x.enabled ? "true" : "false",
    LAWCOPILOT_X_CONFIGURED: x.enabled && x.oauthConnected && x.accessToken ? "true" : "false",
    LAWCOPILOT_X_ACCOUNT_LABEL: x.accountLabel || "",
    LAWCOPILOT_X_USER_ID: x.userId || "",
    LAWCOPILOT_X_SCOPES: Array.isArray(x.scopes) ? x.scopes.join(",") : "",
  };
}

function logFile(runtimePaths) {
  const runtimeDir = path.join(runtimePaths.artifactsRoot, "runtime");
  fs.mkdirSync(runtimeDir, { recursive: true, mode: 0o700 });
  return path.join(runtimeDir, "desktop-backend.log");
}

function startBackend(config, runtimePaths) {
  const outFile = logFile(runtimePaths);
  const output = fs.openSync(outFile, "a", 0o600);
  const binary = findBackendBinary(runtimePaths);
  const env = backendEnv(config, runtimePaths);
  let child;
  if (binary) {
    child = spawn(binary, ["--host", config.apiHost, "--port", String(config.apiPort)], {
      cwd: runtimePaths.apiRoot,
      env,
      stdio: ["ignore", output, output]
    });
  } else {
    if (runtimePaths.isPackaged) {
      throw new Error("backend_binary_not_found");
    }
    const python = findPythonBinary(runtimePaths.apiRoot);
    if (!python) {
      throw new Error("backend_runtime_not_found");
    }
    child = spawn(
      python,
      ["-m", "uvicorn", "main:app", "--host", config.apiHost, "--port", String(config.apiPort)],
      {
        cwd: runtimePaths.apiRoot,
        env,
        stdio: ["ignore", output, output]
      }
    );
  }
  return { child, outFile };
}

async function waitForBackend(apiBaseUrl, timeoutMs = DEFAULT_BACKEND_BOOT_TIMEOUT_MS) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(`${apiBaseUrl}/health`);
      if (response.ok) {
        return response.json();
      }
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  throw new Error("backend_boot_timeout");
}

function stopBackend(handle) {
  if (!handle || !handle.child || handle.child.killed) {
    return;
  }
  handle.child.kill("SIGTERM");
}

module.exports = {
  parseEnvFile,
  startBackend,
  stopBackend,
  waitForBackend
};
