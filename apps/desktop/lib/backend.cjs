const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const DEFAULT_BACKEND_BOOT_TIMEOUT_MS = Number(process.env.LAWCOPILOT_BACKEND_BOOT_TIMEOUT_MS || 180000);
const DEFAULT_BACKEND_REQUEST_TIMEOUT_MS = Number(process.env.LAWCOPILOT_BACKEND_REQUEST_TIMEOUT_MS || 5000);

function runtimeStateDir(runtimePaths, storagePathOverride = "") {
  const artifactsRoot = String(storagePathOverride || runtimePaths?.artifactsRoot || "").trim();
  if (!artifactsRoot) {
    return "";
  }
  const runtimeDir = path.join(artifactsRoot, "runtime");
  try {
    fs.mkdirSync(runtimeDir, { recursive: true, mode: 0o700 });
  } catch {}
  return runtimeDir;
}

function backendPidFile(runtimePaths, storagePathOverride = "") {
  const runtimeDir = runtimeStateDir(runtimePaths, storagePathOverride);
  return runtimeDir ? path.join(runtimeDir, "desktop-backend.pid") : "";
}

function writePidFile(targetPath, pid, metadata = {}) {
  if (!targetPath) {
    return;
  }
  try {
    fs.writeFileSync(
      targetPath,
      `${JSON.stringify(
        {
          pid: Number(pid || 0),
          updated_at: new Date().toISOString(),
          ...metadata,
        },
        null,
        2,
      )}\n`,
      { encoding: "utf-8", mode: 0o600 },
    );
  } catch {}
}

function clearPidFile(targetPath, expectedPid = null) {
  if (!targetPath || !fs.existsSync(targetPath)) {
    return;
  }
  if (expectedPid !== null && expectedPid !== undefined) {
    try {
      const payload = JSON.parse(fs.readFileSync(targetPath, "utf-8"));
      if (Number(payload?.pid || 0) !== Number(expectedPid || 0)) {
        return;
      }
    } catch {
      return;
    }
  }
  try {
    fs.unlinkSync(targetPath);
  } catch {}
}

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
    "https://www.googleapis.com/auth/youtube.readonly",
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

function normalizeOutlookScopes(scopes) {
  const defaults = [
    "openid",
    "email",
    "profile",
    "offline_access",
    "User.Read",
    "Mail.Read",
    "Calendars.Read",
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

function normalizeLinkedInScopes(scopes) {
  const defaults = [
    "openid",
    "profile",
    "email",
    "w_member_social",
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

function normalizeInstagramScopes(scopes) {
  const defaults = [
    "instagram_basic",
    "instagram_manage_messages",
    "pages_manage_metadata",
    "pages_show_list",
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

function resolveBrowserWorkerEntry(runtimePaths) {
  const candidates = [
    path.join(runtimePaths.browserWorkerRoot || "", "dist", "index.js"),
    path.join(runtimePaths.browserWorkerRoot || "", "dist", "cli.js"),
    path.join(runtimePaths.repoRoot, "apps", "browser-worker", "dist", "index.js"),
    path.join(runtimePaths.repoRoot, "apps", "browser-worker", "dist", "cli.js"),
  ];
  return candidates.find((candidate) => candidate && fs.existsSync(candidate)) || "";
}

function resolveBrowserWorkerInstallEntry(runtimePaths) {
  const candidates = [
    path.join(runtimePaths.browserWorkerRoot || "", "node_modules", "playwright", "cli.js"),
    path.join(runtimePaths.repoRoot, "apps", "browser-worker", "node_modules", "playwright", "cli.js"),
  ];
  return candidates.find((candidate) => candidate && fs.existsSync(candidate)) || "";
}

function resolveBrowserWorkerCommand(runtimePaths) {
  const explicit = String(process.env.LAWCOPILOT_BROWSER_WORKER_COMMAND || "").trim();
  if (explicit) {
    return explicit;
  }
  if (runtimePaths.isPackaged && process.execPath) {
    return process.execPath;
  }
  return "";
}

function backendEnv(config, runtimePaths) {
  const fileEnv = parseEnvFile(config.envFile);
  const storageRoot = config.storagePath || runtimePaths.artifactsRoot;
  const provider = config.provider || {};
  const google = config.google || {};
  const outlook = config.outlook || {};
  const telegram = config.telegram || {};
  const whatsapp = config.whatsapp || {};
  const x = config.x || {};
  const linkedin = config.linkedin || {};
  const instagram = config.instagram || {};
  const googleScopes = normalizeGoogleScopes(google.scopes);
  const outlookScopes = normalizeOutlookScopes(outlook.scopes);
  const linkedinScopes = normalizeLinkedInScopes(linkedin.scopes);
  const instagramScopes = normalizeInstagramScopes(instagram.scopes);
  const providerConfigured = Boolean(provider.apiKey || provider.oauthConnected || provider.type === "ollama");
  const openclawEnabled = provider.type === "openai-codex";
  const telegramMode = String(telegram.mode || (telegram.botToken || telegram.allowedUserId ? "bot" : "web")).trim().toLowerCase() || "bot";
  const telegramConfigured = telegramMode === "web"
    ? Boolean(telegram.enabled && (telegram.webAccountLabel || telegram.webStatus === "ready"))
    : Boolean(telegram.botToken && telegram.allowedUserId);
  const telegramAccountLabel = telegramMode === "web"
    ? String(telegram.webAccountLabel || "Telegram Web hesabı").trim()
    : String(telegram.botUsername || "Telegram botu").trim();
  const whatsappMode = String(whatsapp.mode || (whatsapp.phoneNumberId || whatsapp.accessToken ? "business_cloud" : "web")).trim().toLowerCase() || "web";
  const whatsappConfigured = whatsappMode === "web"
    ? Boolean(whatsapp.enabled && (whatsapp.webAccountLabel || whatsapp.webStatus === "ready"))
    : Boolean(whatsapp.enabled && whatsapp.accessToken && whatsapp.phoneNumberId);
  const whatsappAccountLabel = whatsappMode === "web"
    ? String(whatsapp.webAccountLabel || whatsapp.businessLabel || whatsapp.verifiedName || whatsapp.displayPhoneNumber || "WhatsApp hesabı").trim()
    : String(whatsapp.businessLabel || whatsapp.verifiedName || whatsapp.displayPhoneNumber || "").trim();
  const linkedinMode = String(linkedin.mode || (linkedin.oauthConnected || linkedin.accessToken ? "official" : "web")).trim().toLowerCase() || "official";
  const linkedinConfigured = linkedinMode === "web"
    ? Boolean(linkedin.enabled && (linkedin.webAccountLabel || linkedin.webStatus === "ready"))
    : Boolean(linkedin.enabled && linkedin.oauthConnected && linkedin.accessToken);
  const linkedinAccountLabel = linkedinMode === "web"
    ? String(linkedin.webAccountLabel || linkedin.accountLabel || "LinkedIn Web hesabı").trim()
    : String(linkedin.accountLabel || "").trim();
  const browserWorkerEntry = resolveBrowserWorkerEntry(runtimePaths);
  const browserWorkerInstallEntry = resolveBrowserWorkerInstallEntry(runtimePaths);
  const browserWorkerEnabled = Boolean(browserWorkerEntry);
  const browserWorkerBrowsersPath = path.join(runtimePaths.browserWorkerRoot, ".bundled-browsers");
  const browserRoot = path.join(storageRoot, "browser");
  return {
    ...process.env,
    ...fileEnv,
    LAWCOPILOT_BOOTSTRAP_ADMIN_KEY: String(
      config.runtimeBootstrapKey || fileEnv.LAWCOPILOT_BOOTSTRAP_ADMIN_KEY || process.env.LAWCOPILOT_BOOTSTRAP_ADMIN_KEY || "",
    ).trim(),
    LAWCOPILOT_APP_NAME: config.appName,
    LAWCOPILOT_APP_VERSION: config.appVersion,
    LAWCOPILOT_OFFICE_ID: config.officeId,
    LAWCOPILOT_DEPLOYMENT_MODE: config.deploymentMode,
    LAWCOPILOT_RELEASE_CHANNEL: config.releaseChannel,
    LAWCOPILOT_DEFAULT_MODEL_PROFILE: config.selectedModelProfile || "cloud",
    LAWCOPILOT_DESKTOP_SHELL: "electron",
    LAWCOPILOT_ENVIRONMENT: process.env.LAWCOPILOT_ENVIRONMENT || "pilot",
    LAWCOPILOT_AUDIT_LOG: path.join(storageRoot, "audit.log.jsonl"),
    LAWCOPILOT_STRUCTURED_LOG: path.join(storageRoot, "events.log.jsonl"),
    LAWCOPILOT_DESKTOP_MAIN_LOG: process.env.LAWCOPILOT_DESKTOP_MAIN_LOG || path.join(os.tmpdir(), "lawcopilot-desktop-main.log"),
    LAWCOPILOT_DESKTOP_BACKEND_LOG: logFile(runtimePaths, storageRoot),
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
          LAWCOPILOT_OPENCLAW_TIMEOUT: process.env.LAWCOPILOT_OPENCLAW_TIMEOUT || "25",
        }
      : {}),
    LAWCOPILOT_PERSONAL_KB_LLM_ARTICLE_AUTHORING_ENABLED:
      process.env.LAWCOPILOT_PERSONAL_KB_LLM_ARTICLE_AUTHORING_ENABLED || "false",
    LAWCOPILOT_GOOGLE_ENABLED: google.enabled ? "true" : "false",
    LAWCOPILOT_GOOGLE_CONFIGURED: google.oauthConnected && google.accessToken ? "true" : "false",
    LAWCOPILOT_GOOGLE_ACCOUNT_LABEL: google.accountLabel || "",
    LAWCOPILOT_GOOGLE_SCOPES: googleScopes.join(","),
    LAWCOPILOT_GOOGLE_CLIENT_ID_CONFIGURED:
      (google.clientId || process.env.LAWCOPILOT_GOOGLE_CLIENT_ID) ? "true" : "false",
    LAWCOPILOT_GOOGLE_CLIENT_SECRET_CONFIGURED:
      (google.clientSecret || process.env.LAWCOPILOT_GOOGLE_CLIENT_SECRET) ? "true" : "false",
    LAWCOPILOT_GMAIL_CONNECTED: google.oauthConnected && googleScopes.some((scope) => String(scope).includes("gmail")) ? "true" : "false",
    LAWCOPILOT_CALENDAR_CONNECTED: google.oauthConnected && googleScopes.some((scope) => String(scope).includes("calendar")) ? "true" : "false",
    LAWCOPILOT_DRIVE_CONNECTED: google.oauthConnected && googleScopes.some((scope) => String(scope).includes("drive")) ? "true" : "false",
    LAWCOPILOT_OUTLOOK_ENABLED: outlook.enabled ? "true" : "false",
    LAWCOPILOT_OUTLOOK_CONFIGURED: outlook.enabled && outlook.oauthConnected && outlook.accessToken ? "true" : "false",
    LAWCOPILOT_OUTLOOK_ACCOUNT_LABEL: outlook.accountLabel || "",
    LAWCOPILOT_OUTLOOK_SCOPES: outlookScopes.join(","),
    LAWCOPILOT_OUTLOOK_MAIL_CONNECTED: outlook.oauthConnected && outlookScopes.some((scope) => String(scope).toLowerCase().includes("mail.")) ? "true" : "false",
    LAWCOPILOT_OUTLOOK_CALENDAR_CONNECTED: outlook.oauthConnected && outlookScopes.some((scope) => String(scope).toLowerCase().includes("calendar")) ? "true" : "false",
    LAWCOPILOT_TELEGRAM_ENABLED: telegram.enabled ? "true" : "false",
    LAWCOPILOT_TELEGRAM_MODE: telegramMode,
    LAWCOPILOT_TELEGRAM_BOT_TOKEN: telegram.botToken || "",
    LAWCOPILOT_TELEGRAM_BOT_USERNAME: telegram.botUsername || "",
    LAWCOPILOT_TELEGRAM_ALLOWED_USER_ID: telegram.allowedUserId || "",
    LAWCOPILOT_TELEGRAM_ACCOUNT_LABEL: telegramAccountLabel,
    LAWCOPILOT_TELEGRAM_CONFIGURED: telegramConfigured ? "true" : "false",
    LAWCOPILOT_WHATSAPP_ENABLED: whatsapp.enabled ? "true" : "false",
    LAWCOPILOT_WHATSAPP_CONFIGURED: whatsappConfigured ? "true" : "false",
    LAWCOPILOT_WHATSAPP_ACCOUNT_LABEL: whatsappAccountLabel,
    LAWCOPILOT_WHATSAPP_PHONE_NUMBER_ID: whatsapp.phoneNumberId || "",
    LAWCOPILOT_WHATSAPP_DISPLAY_PHONE_NUMBER: whatsapp.displayPhoneNumber || "",
    LAWCOPILOT_X_ENABLED: x.enabled ? "true" : "false",
    LAWCOPILOT_X_CONFIGURED: x.enabled && x.oauthConnected && x.accessToken ? "true" : "false",
    LAWCOPILOT_X_ACCOUNT_LABEL: x.accountLabel || "",
    LAWCOPILOT_X_USER_ID: x.userId || "",
    LAWCOPILOT_X_SCOPES: Array.isArray(x.scopes) ? x.scopes.join(",") : "",
    LAWCOPILOT_X_VALIDATION_STATUS: x.validationStatus || "",
    LAWCOPILOT_X_LAST_ERROR: x.oauthLastError || "",
    LAWCOPILOT_LINKEDIN_ENABLED: linkedin.enabled ? "true" : "false",
    LAWCOPILOT_LINKEDIN_MODE: linkedinMode,
    LAWCOPILOT_LINKEDIN_CONFIGURED: linkedinConfigured ? "true" : "false",
    LAWCOPILOT_LINKEDIN_ACCOUNT_LABEL: linkedinAccountLabel,
    LAWCOPILOT_LINKEDIN_USER_ID: linkedin.userId || "",
    LAWCOPILOT_LINKEDIN_PERSON_URN: linkedin.personUrn || "",
    LAWCOPILOT_LINKEDIN_SCOPES: linkedinScopes.join(","),
    LAWCOPILOT_INSTAGRAM_ENABLED: instagram.enabled ? "true" : "false",
    LAWCOPILOT_INSTAGRAM_CONFIGURED: instagram.enabled && instagram.oauthConnected && instagram.pageAccessToken && instagram.pageId ? "true" : "false",
    LAWCOPILOT_INSTAGRAM_ACCOUNT_LABEL: instagram.accountLabel || instagram.username || "",
    LAWCOPILOT_INSTAGRAM_PAGE_ID: instagram.pageId || "",
    LAWCOPILOT_INSTAGRAM_ACCOUNT_ID: instagram.instagramAccountId || "",
    LAWCOPILOT_INSTAGRAM_USERNAME: instagram.username || "",
    LAWCOPILOT_INSTAGRAM_SCOPES: instagramScopes.join(","),
    LAWCOPILOT_BROWSER_WORKER_ENABLED: browserWorkerEnabled ? "true" : "false",
    LAWCOPILOT_BROWSER_WORKER_COMMAND: browserWorkerEnabled ? resolveBrowserWorkerCommand(runtimePaths) : "",
    LAWCOPILOT_BROWSER_WORKER_ENTRY: browserWorkerEntry,
    LAWCOPILOT_BROWSER_WORKER_INSTALL_ENTRY: browserWorkerInstallEntry,
    LAWCOPILOT_BROWSER_WORKER_BROWSERS_PATH: browserWorkerBrowsersPath,
    LAWCOPILOT_BROWSER_WORKER_RUN_AS_NODE: runtimePaths.isPackaged && browserWorkerEnabled ? "true" : "false",
    LAWCOPILOT_BROWSER_PROFILE_DIR: path.join(browserRoot, "profile"),
    LAWCOPILOT_BROWSER_ARTIFACTS_DIR: path.join(browserRoot, "artifacts"),
    LAWCOPILOT_BROWSER_DOWNLOADS_DIR: path.join(browserRoot, "downloads"),
    LAWCOPILOT_BROWSER_WORKER_TIMEOUT: process.env.LAWCOPILOT_BROWSER_WORKER_TIMEOUT || "45",
    LAWCOPILOT_PERSONAL_KB_ROOT: path.join(storageRoot, "runtime", "personal-kb"),
    PLAYWRIGHT_BROWSERS_PATH: browserWorkerBrowsersPath,
    };
}

function logFile(runtimePaths, storagePathOverride = "") {
  const runtimeDir = runtimeStateDir(runtimePaths, storagePathOverride);
  return path.join(runtimeDir, "desktop-backend.log");
}

function appendBackendLog(outFile, message) {
  if (!outFile) {
    return;
  }
  try {
    fs.appendFileSync(outFile, `[desktop-backend] ${new Date().toISOString()} ${String(message || "").trim()}\n`, {
      encoding: "utf-8",
      mode: 0o600,
    });
  } catch {
    return;
  }
}

function readBackendLogTail(outFile, maxBytes = 8192) {
  if (!outFile || !fs.existsSync(outFile)) {
    return "";
  }
  try {
    const stats = fs.statSync(outFile);
    const start = Math.max(0, stats.size - maxBytes);
    const fd = fs.openSync(outFile, "r");
    try {
      const length = Math.max(0, stats.size - start);
      const buffer = Buffer.alloc(length);
      fs.readSync(fd, buffer, 0, length, start);
      return buffer.toString("utf-8").trim();
    } finally {
      fs.closeSync(fd);
    }
  } catch {
    return "";
  }
}

function startBackend(config, runtimePaths) {
  const outFile = logFile(runtimePaths, config?.storagePath);
  const pidFile = backendPidFile(runtimePaths, config?.storagePath);
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
  appendBackendLog(
    outFile,
    `spawn pid=${String(child?.pid || "")} port=${String(config.apiPort)} binary=${String(binary || "python-uvicorn")}`,
  );
  writePidFile(pidFile, child?.pid, {
    api_port: Number(config?.apiPort || 0),
    api_base_url: String(config?.apiBaseUrl || "").trim(),
    binary: String(binary || "python-uvicorn"),
  });
  child.once("exit", (code, signal) => {
    appendBackendLog(
      outFile,
      `exit pid=${String(child?.pid || "")} code=${String(code)} signal=${String(signal || "")}`,
    );
    clearPidFile(pidFile, child?.pid);
  });
  child.once("error", (error) => {
    appendBackendLog(
      outFile,
      `error pid=${String(child?.pid || "")} ${String(error?.stack || error?.message || error || "unknown_error")}`,
    );
  });
  return { child, outFile, pidFile };
}

async function waitForBackend(apiBaseUrl, options = {}) {
  const timeoutMs = Number(options.timeoutMs || DEFAULT_BACKEND_BOOT_TIMEOUT_MS);
  const handle = options.handle || null;
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (handle?.child && handle.child.exitCode !== null) {
      const tail = readBackendLogTail(handle.outFile);
      throw new Error(tail ? `backend_process_exited\n${tail}` : "backend_process_exited");
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), DEFAULT_BACKEND_REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(`${apiBaseUrl}/health`, { signal: controller.signal });
      if (response.ok) {
        clearTimeout(timer);
        if (handle?.outFile) {
          appendBackendLog(
            handle.outFile,
            `health_ready elapsed_ms=${String(Date.now() - started)} api_base_url=${String(apiBaseUrl || "").trim()}`,
          );
        }
        return response.json();
      }
    } catch {}
    clearTimeout(timer);
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  const tail = readBackendLogTail(handle?.outFile);
  throw new Error(tail ? `backend_boot_timeout\n${tail}` : "backend_boot_timeout");
}

function waitForChildExit(child, timeoutMs = 4000) {
  return new Promise((resolve) => {
    if (!child || child.exitCode !== null) {
      resolve();
      return;
    }
    let settled = false;
    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      resolve();
    };
    child.once("exit", finish);
    setTimeout(finish, timeoutMs);
  });
}

function listeningPids(port) {
  const targetPort = Number(port || 0);
  if (!Number.isFinite(targetPort) || targetPort <= 0) {
    return [];
  }
  const pids = new Set();

  if (process.platform === "win32") {
    try {
      const result = spawnSync("netstat", ["-ano", "-p", "tcp"], {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
        timeout: 4000,
      });
      const output = String(result.stdout || "");
      for (const line of output.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed || !/LISTENING/i.test(trimmed)) {
          continue;
        }
        const parts = trimmed.split(/\s+/);
        if (parts.length < 5) {
          continue;
        }
        const localAddress = parts[1] || "";
        const pid = Number(parts[parts.length - 1] || 0);
        if (!localAddress.endsWith(`:${targetPort}`) || !Number.isFinite(pid) || pid <= 0) {
          continue;
        }
        pids.add(pid);
      }
    } catch {}
    return [...pids];
  }

  for (const command of [
    ["lsof", ["-ti", `tcp:${targetPort}`]],
    ["fuser", ["-n", "tcp", String(targetPort)]],
  ]) {
    try {
      const result = spawnSync(command[0], command[1], {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
        timeout: 4000,
      });
      const output = String(result.stdout || "");
      for (const token of output.split(/\s+/)) {
        const pid = Number(token.trim());
        if (Number.isFinite(pid) && pid > 0) {
          pids.add(pid);
        }
      }
      if (pids.size) {
        break;
      }
    } catch {}
  }

  return [...pids];
}

function pidCommandLine(pid) {
  const targetPid = Number(pid || 0);
  if (!Number.isFinite(targetPid) || targetPid <= 0) {
    return "";
  }
  try {
    if (process.platform === "win32") {
      const result = spawnSync("wmic", ["process", "where", `ProcessId=${targetPid}`, "get", "CommandLine", "/value"], {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
        timeout: 4000,
      });
      return String(result.stdout || "").trim();
    }
    const result = spawnSync("ps", ["-p", String(targetPid), "-o", "command="], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 4000,
    });
    return String(result.stdout || "").trim();
  } catch {
    return "";
  }
}

function isManagedBackendPid(pid, runtimePaths, allowedPids = []) {
  const targetPid = Number(pid || 0);
  if (!Number.isFinite(targetPid) || targetPid <= 0) {
    return false;
  }
  if ((Array.isArray(allowedPids) ? allowedPids : [allowedPids]).some((value) => Number(value || 0) === targetPid)) {
    return true;
  }
  const commandLine = pidCommandLine(targetPid);
  if (!commandLine) {
    return false;
  }
  const normalized = commandLine.replace(/\\/g, "/").toLowerCase();
  const apiRoot = String(runtimePaths?.apiRoot || "").replace(/\\/g, "/").toLowerCase();
  const backendBinRoot = String(runtimePaths?.backendBinRoot || "").replace(/\\/g, "/").toLowerCase();
  if (apiRoot && normalized.includes(apiRoot)) {
    return true;
  }
  if (backendBinRoot && normalized.includes(backendBinRoot)) {
    return true;
  }
  if (normalized.includes("lawcopilot-api")) {
    return true;
  }
  return false;
}

function waitForPortRelease(port, timeoutMs = 4000) {
  const startedAt = Date.now();
  return new Promise((resolve) => {
    const tick = () => {
      if (!listeningPids(port).length || Date.now() - startedAt >= timeoutMs) {
        resolve();
        return;
      }
      setTimeout(tick, 150);
    };
    tick();
  });
}

async function stopBackendOnPort(port, options = {}) {
  const skip = new Set(
    [...(Array.isArray(options.exceptPids) ? options.exceptPids : [options.exceptPids])]
      .map((value) => Number(value || 0))
      .filter((value) => Number.isFinite(value) && value > 0)
  );
  const allowedPids = [...(Array.isArray(options.allowPids) ? options.allowPids : [options.allowPids])]
    .map((value) => Number(value || 0))
    .filter((value) => Number.isFinite(value) && value > 0);
  const runtimePaths = options.runtimePaths || {};
  const blockedPids = [];
  const stoppedPids = [];

  for (const pid of listeningPids(port)) {
    if (skip.has(pid) || pid === process.pid) {
      continue;
    }
    if (!isManagedBackendPid(pid, runtimePaths, allowedPids)) {
      blockedPids.push(pid);
      continue;
    }

    if (process.platform === "win32") {
      try {
        spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], {
          stdio: "ignore",
          timeout: 4000,
        });
        stoppedPids.push(pid);
      } catch {}
      continue;
    }

    try {
      process.kill(pid, "SIGTERM");
      stoppedPids.push(pid);
    } catch {}
  }

  await waitForPortRelease(port, 3000);

  for (const pid of listeningPids(port)) {
    if (skip.has(pid) || pid === process.pid) {
      continue;
    }
    if (!isManagedBackendPid(pid, runtimePaths, allowedPids)) {
      if (!blockedPids.includes(pid)) {
        blockedPids.push(pid);
      }
      continue;
    }
    if (process.platform === "win32") {
      try {
        spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], {
          stdio: "ignore",
          timeout: 4000,
        });
      } catch {}
    } else {
      try {
        process.kill(pid, "SIGKILL");
      } catch {}
    }
  }

  await waitForPortRelease(port, 2000);
  return {
    stoppedPids,
    blockedPids,
  };
}

async function stopBackend(handle) {
  if (!handle || !handle.child) {
    return;
  }
  const child = handle.child;
  const pidFile = handle.pidFile || "";
  if (child.exitCode !== null) {
    clearPidFile(pidFile, child.pid);
    return;
  }

  try {
    child.kill("SIGTERM");
  } catch {}
  await waitForChildExit(child, 3000);

  if (child.exitCode !== null) {
    clearPidFile(pidFile, child.pid);
    return;
  }

  if (process.platform === "win32" && child.pid) {
    try {
      spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
        timeout: 4000,
      });
    } catch {}
  } else {
    try {
      child.kill("SIGKILL");
    } catch {}
  }

  await waitForChildExit(child, 2000);
  clearPidFile(pidFile, child.pid);
}

module.exports = {
  appendBackendLog,
  backendPidFile,
  backendEnv,
  clearPidFile,
  isManagedBackendPid,
  listeningPids,
  parseEnvFile,
  readBackendLogTail,
  resolveBrowserWorkerCommand,
  resolveBrowserWorkerEntry,
  resolveBrowserWorkerInstallEntry,
  startBackend,
  stopBackend,
  stopBackendOnPort,
  waitForBackend,
  writePidFile,
};
