const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const DOCKER_CANDIDATES = process.platform === "win32"
  ? ["docker.exe", "docker"]
  : ["/usr/bin/docker", "/usr/local/bin/docker", "docker"];

const SCRIPT_CANDIDATES = process.platform === "win32"
  ? []
  : ["/usr/bin/script", "/bin/script", "script"];

const OPENCLAW_IMAGE_CANDIDATES = [
  "openclaw-local:chromium",
  "ghcr.io/openclaw/openclaw:2026.3.2",
];

let cachedDockerBinary = null;
let cachedScriptBinary = null;
let cachedOpenClawImage = null;
let currentSession = null;
const CALLBACK_TIMEOUT_MS = 180000;

function nowIso() {
  return new Date().toISOString();
}

function commandExists(candidate, args = ["--version"]) {
  try {
    const result = spawnSync(candidate, args, {
      stdio: "ignore",
      timeout: 4000,
    });
    return result.status === 0 || result.status === 1;
  } catch {
    return false;
  }
}

function resolveDockerBinary() {
  if (cachedDockerBinary) {
    return cachedDockerBinary;
  }
  for (const candidate of DOCKER_CANDIDATES) {
    if (candidate.includes(path.sep) && !fs.existsSync(candidate)) {
      continue;
    }
    if (commandExists(candidate, ["version"])) {
      cachedDockerBinary = candidate;
      return candidate;
    }
  }
  throw new Error("Docker bulunamadı. Codex hesap oturumu için Docker gerekir.");
}

function resolveScriptBinary() {
  if (process.platform === "win32") {
    throw new Error("Tarayıcı tabanlı Codex oturumu bu aşamada Windows masaüstü kabuğunda gömülü değil.");
  }
  if (cachedScriptBinary) {
    return cachedScriptBinary;
  }
  for (const candidate of SCRIPT_CANDIDATES) {
    if (candidate.includes(path.sep) && !fs.existsSync(candidate)) {
      continue;
    }
    if (commandExists(candidate, ["--version"])) {
      cachedScriptBinary = candidate;
      return candidate;
    }
  }
  throw new Error("TTY köprüsü bulunamadı. Codex oturumu için 'script' komutu gerekir.");
}

function resolveOpenClawImage() {
  if (cachedOpenClawImage) {
    return cachedOpenClawImage;
  }
  const docker = resolveDockerBinary();
  for (const image of OPENCLAW_IMAGE_CANDIDATES) {
    const result = spawnSync(docker, ["image", "inspect", image], {
      stdio: "ignore",
      timeout: 8000,
    });
    if (result.status === 0) {
      cachedOpenClawImage = image;
      return image;
    }
  }
  throw new Error("OpenClaw imajı bulunamadı. Önce openclaw-local:chromium imajı hazırlanmalı.");
}

function quoteShellArg(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

function writeIfMissing(filePath, content) {
  if (fs.existsSync(filePath)) {
    return;
  }
  fs.mkdirSync(path.dirname(filePath), { recursive: true, mode: 0o700 });
  fs.writeFileSync(filePath, content, { mode: 0o600 });
}

function seedWorkspaceScaffold(stateDir) {
  const workspaceDir = path.join(stateDir, "workspace");
  const hiddenStatePath = path.join(workspaceDir, ".openclaw", "workspace-state.json");
  fs.mkdirSync(path.join(workspaceDir, ".openclaw"), { recursive: true, mode: 0o700 });
  fs.mkdirSync(path.join(workspaceDir, "memory", "daily-logs"), { recursive: true, mode: 0o700 });
  fs.mkdirSync(path.join(workspaceDir, "skills"), { recursive: true, mode: 0o700 });

  writeIfMissing(path.join(workspaceDir, "AGENTS.md"), [
    "# LawCopilot Runtime",
    "",
    "Bu çalışma alanı LawCopilot tarafından hazırlanır.",
    "",
    "Backend ilk senkron çalıştığında bu dosya daha ayrıntılı içerikle güncellenir.",
    "",
  ].join("\n"));
  writeIfMissing(path.join(workspaceDir, "SOUL.md"), "# SOUL.md\n\nİlk senkron bekleniyor.\n");
  writeIfMissing(path.join(workspaceDir, "USER.md"), "# USER.md\n\nİlk senkron bekleniyor.\n");
  writeIfMissing(path.join(workspaceDir, "IDENTITY.md"), "# IDENTITY.md\n\nİlk senkron bekleniyor.\n");
  writeIfMissing(path.join(workspaceDir, "TOOLS.md"), "# TOOLS.md\n\nİlk senkron bekleniyor.\n");
  writeIfMissing(path.join(workspaceDir, "HEARTBEAT.md"), "# HEARTBEAT.md\n\n- İlk senkron tamamlanınca görevler burada görünür.\n");
  writeIfMissing(path.join(workspaceDir, "MEMORY.md"), "# MEMORY.md\n\nİlk senkron bekleniyor.\n");
  writeIfMissing(path.join(workspaceDir, "BOOTSTRAP.md"), [
    "# BOOTSTRAP.md",
    "",
    "LawCopilot ilk kurulum scaffold'unu hazırladı.",
    "Ayarlar ekranında kullanıcı profili ve asistan kimliği tamamlandığında bu dosya kaldırılır.",
    "",
  ].join("\n"));
  writeIfMissing(path.join(workspaceDir, "skills", "manifest.json"), "[]\n");
  writeIfMissing(
    hiddenStatePath,
    `${JSON.stringify({ version: 2, scaffoldSeededAt: nowIso() }, null, 2)}\n`,
  );
}

function ensureStateDir(config) {
  const base = config?.storagePath || path.join(os.homedir(), ".config", "LawCopilot", "artifacts");
  const stateDir = path.join(base, "openclaw-state");
  fs.mkdirSync(path.join(stateDir, "workspace"), { recursive: true, mode: 0o700 });
  seedWorkspaceScaffold(stateDir);
  return stateDir;
}

function localAuthProfilesPath(config) {
  return path.join(ensureStateDir(config), "agents", "main", "agent", "auth-profiles.json");
}

function safeReadJson(filePath) {
  try {
    if (!fs.existsSync(filePath)) {
      return null;
    }
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return null;
  }
}

function hasCodexOAuthProfile(payload) {
  const profiles = payload?.profiles || {};
  return Object.values(profiles).some((profile) => (
    profile
    && String(profile.provider || "") === "openai-codex"
    && String(profile.type || "") === "oauth"
    && String(profile.access || "")
  ));
}

function legacyAuthCandidates(config) {
  const candidates = new Set();
  candidates.add(path.join(os.homedir(), ".openclaw", "agents", "main", "agent", "auth-profiles.json"));
  if (config?.storagePath) {
    candidates.add(path.resolve(config.storagePath, "..", "..", "..", "state", "agents", "main", "agent", "auth-profiles.json"));
  }
  return Array.from(candidates);
}

function importLegacyCodexAuth(config) {
  const destination = localAuthProfilesPath(config);
  const existingPayload = safeReadJson(destination);
  if (hasCodexOAuthProfile(existingPayload)) {
    return "";
  }

  for (const candidate of legacyAuthCandidates(config)) {
    if (!candidate || candidate === destination) {
      continue;
    }
    const payload = safeReadJson(candidate);
    if (!hasCodexOAuthProfile(payload)) {
      continue;
    }
    fs.mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
    fs.copyFileSync(candidate, destination);
    fs.chmodSync(destination, 0o600);
    appendLog(config, `\n[lawcopilot] mevcut Codex auth profili içe aktarıldı: ${candidate}\n`);
    return candidate;
  }

  return "";
}

function logFilePath(config) {
  const base = config?.storagePath || path.join(os.homedir(), ".config", "LawCopilot", "artifacts");
  const runtimeDir = path.join(base, "runtime");
  fs.mkdirSync(runtimeDir, { recursive: true, mode: 0o700 });
  return path.join(runtimeDir, "codex-oauth.log");
}

function appendLog(config, text) {
  try {
    fs.appendFileSync(logFilePath(config), text, { mode: 0o600 });
  } catch {
    return;
  }
}

function runDockerJson(config, openclawArgs) {
  const docker = resolveDockerBinary();
  const image = resolveOpenClawImage();
  const stateDir = ensureStateDir(config);
  const result = spawnSync(
    docker,
    ["run", "--rm", "-v", `${stateDir}:/home/node/.openclaw`, image, "openclaw", ...openclawArgs],
    {
      encoding: "utf-8",
      timeout: 30000,
    },
  );
  if (result.status !== 0) {
    const errorText = String(result.stderr || result.stdout || "").trim();
    throw new Error(errorText || "OpenClaw komutu çalıştırılamadı.");
  }
  const raw = String(result.stdout || "").trim();
  return raw ? JSON.parse(raw) : {};
}

function runDocker(config, openclawArgs) {
  const docker = resolveDockerBinary();
  const image = resolveOpenClawImage();
  const stateDir = ensureStateDir(config);
  const result = spawnSync(
    docker,
    ["run", "--rm", "-v", `${stateDir}:/home/node/.openclaw`, image, "openclaw", ...openclawArgs],
    {
      encoding: "utf-8",
      timeout: 30000,
    },
  );
  if (result.status !== 0) {
    const errorText = String(result.stderr || result.stdout || "").trim();
    throw new Error(errorText || "OpenClaw komutu çalıştırılamadı.");
  }
  return String(result.stdout || "").trim();
}

function defaultCodexStatus(config) {
  return {
    ok: true,
    provider: "openai-codex",
    authStatus: "hazır_değil",
    message: "Henüz OpenAI hesabı bağlanmadı.",
    browserOpened: false,
    configured: false,
    availableModels: [],
    catalogModels: [],
    selectedModel: config?.provider?.model || "",
    stateDir: ensureStateDir(config),
    logFile: logFilePath(config),
  };
}

function normalizeModelList(payload) {
  const models = Array.isArray(payload?.models) ? payload.models : [];
  return models.map((item) => ({
    key: String(item.key || ""),
    name: String(item.name || item.key || ""),
    available: Boolean(item.available),
    configured: Array.isArray(item.tags) && item.tags.includes("configured"),
  })).filter((item) => item.key);
}

function getPersistedCodexStatus(config) {
  const status = defaultCodexStatus(config);
  try {
    importLegacyCodexAuth(config);
    const state = runDockerJson(config, ["models", "status", "--json"]);
    const list = runDockerJson(config, ["models", "list", "--provider", "openai-codex", "--all", "--json"]);
    const models = normalizeModelList(list);
    const providerStatus = Array.isArray(state?.auth?.oauth?.providers)
      ? state.auth.oauth.providers.find((item) => String(item.provider || "") === "openai-codex")
      : null;
    const configured = providerStatus?.status === "ok";
    const persistedModel = String(state?.resolvedDefault || state?.defaultModel || "");
    const selectedModel = persistedModel.startsWith("openai-codex/")
      ? persistedModel
      : String(config?.provider?.model || "openai-codex/gpt-5.3-codex");
    return {
      ok: true,
      provider: "openai-codex",
      authStatus: configured ? "bagli" : "hazır_değil",
      message: configured ? "OpenAI hesabı bağlı." : "Henüz OpenAI hesabı bağlanmadı.",
      browserOpened: false,
      configured,
      availableModels: models.filter((item) => item.available).map((item) => item.key),
      catalogModels: models.map((item) => item.key),
      selectedModel,
      stateDir: ensureStateDir(config),
      logFile: logFilePath(config),
      expiresAt: providerStatus?.expiresAt || null,
    };
  } catch (error) {
    return {
      ...status,
      authStatus: "hata",
      message: error instanceof Error ? error.message : "Codex durumu okunamadı.",
      ok: false,
    };
  }
}

function cleanupSession(session) {
  if (!session) {
    return;
  }
  try {
    session.child.kill("SIGTERM");
  } catch {
    return;
  }
}

async function waitForPersistedCodexConnection(config, session, timeoutMs = CALLBACK_TIMEOUT_MS) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (!currentSession || currentSession.id !== session.id) {
      const persisted = getPersistedCodexStatus(config);
      if (persisted.configured) {
        return persisted;
      }
      throw new Error("OAuth oturumu artık aktif değil.");
    }
    if (session.error) {
      throw new Error(session.error);
    }
    const persisted = getPersistedCodexStatus(config);
    if (persisted.configured) {
      session.status = "bagli";
      session.message = persisted.message || "OpenAI hesabı başarıyla bağlandı.";
      session.availableModels = persisted.availableModels || [];
      session.selectedModel = persisted.selectedModel || session.selectedModel || "";
      session.expiresAt = persisted.expiresAt || null;
      cleanupSession(session);
      currentSession = null;
      return persisted;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error("OAuth akışı tamamlanamadı. Tarayıcı yönlendirme adresini yeniden alıp tekrar deneyin.");
}

function parseAuthUrl(output) {
  const match = String(output || "").match(/https:\/\/auth\.openai\.com\/oauth\/authorize[^\s"'<>]+/);
  return match ? match[0] : "";
}

function buildDockerTtyCommand(config) {
  const docker = resolveDockerBinary();
  const image = resolveOpenClawImage();
  const stateDir = ensureStateDir(config);
  const args = [
    docker,
    "run",
    "--rm",
    "-i",
    "-v",
    `${stateDir}:/home/node/.openclaw`,
    image,
    "openclaw",
    "onboard",
    "--flow",
    "manual",
    "--mode",
    "local",
    "--workspace",
    "/home/node/.openclaw/workspace",
    "--skip-channels",
    "--skip-skills",
    "--skip-ui",
    "--no-install-daemon",
    "--auth-choice",
    "openai-codex",
    "--accept-risk",
  ];
  return args.map(quoteShellArg).join(" ");
}

function waitForAuthUrl(session, timeoutMs = 20000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    function check() {
      if (!currentSession || currentSession.id !== session.id) {
        reject(new Error("OAuth oturumu artık aktif değil."));
        return;
      }
      if (session.authUrl) {
        resolve(snapshotSession(session));
        return;
      }
      if (session.error) {
        reject(new Error(session.error));
        return;
      }
      if (Date.now() - started >= timeoutMs) {
        reject(new Error("Tarayıcı giriş bağlantısı zamanında üretilemedi."));
        return;
      }
      setTimeout(check, 150);
    }
    check();
  });
}

function finalizeSession(config, session) {
  const persisted = getPersistedCodexStatus(config);
  if (persisted.configured) {
    session.status = "bagli";
    session.message = "OpenAI hesabı başarıyla bağlandı.";
    session.availableModels = persisted.availableModels;
    session.selectedModel = persisted.selectedModel;
    session.expiresAt = persisted.expiresAt || null;
  } else if (!session.error) {
    session.status = "hata";
    session.message = persisted.message || "OpenAI hesabı bağlanamadı.";
  }
  return snapshotSession(session);
}

function createCompletionPromise(config, session) {
  return new Promise((resolve) => {
    session.child.once("exit", () => {
      resolve(finalizeSession(config, session));
      if (currentSession && currentSession.id === session.id) {
        currentSession = null;
      }
    });
  });
}

function snapshotSession(session) {
  return {
    ok: true,
    provider: "openai-codex",
    authStatus: session.status,
    message: session.message,
    authUrl: session.authUrl || "",
    browserOpened: Boolean(session.browserOpened),
    browserTarget: session.browserTarget || "",
    configured: session.status === "bagli",
    availableModels: session.availableModels || [],
    selectedModel: session.selectedModel || "",
    logFile: session.logFile,
    expiresAt: session.expiresAt || null,
    error: session.error || "",
  };
}

function handleSessionOutput(config, session, chunk) {
  const text = String(chunk || "");
  session.output += text;
  appendLog(config, text);
  const authUrl = parseAuthUrl(session.output);
  if (authUrl && !session.authUrl) {
    session.authUrl = authUrl;
    session.status = "callback_bekleniyor";
    session.message = "Tarayıcıda OpenAI oturumunu açın, ardından yönlendirme adresini bu pencereye yapıştırın.";
    if (typeof session.onAuthUrl === "function") {
      Promise.resolve(session.onAuthUrl(authUrl))
        .then((target) => {
          session.browserOpened = true;
          session.browserTarget = String(target || "");
        })
        .catch((error) => {
          session.browserOpened = false;
          session.browserTarget = "";
          session.error = error instanceof Error ? error.message : "Tarayıcı açılamadı.";
        });
    }
  }
}

async function startCodexOAuth(config, onAuthUrl) {
  if (currentSession) {
    return snapshotSession(currentSession);
  }
  const scriptBinary = resolveScriptBinary();
  const command = buildDockerTtyCommand(config);
  const child = spawn(scriptBinary, ["-qefc", command, "/dev/null"], {
    env: {
      ...process.env,
      TERM: process.env.TERM || "xterm-256color",
    },
    stdio: ["pipe", "pipe", "pipe"],
  });

  const session = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    child,
    status: "baslatiliyor",
    message: "OpenAI oturum akışı hazırlanıyor.",
    authUrl: "",
    browserOpened: false,
    browserTarget: "",
    output: "",
    error: "",
    availableModels: [],
    selectedModel: "",
    logFile: logFilePath(config),
    expiresAt: null,
    onAuthUrl,
  };

  currentSession = session;
  session.completion = createCompletionPromise(config, session);

  child.stdout.on("data", (chunk) => handleSessionOutput(config, session, chunk));
  child.stderr.on("data", (chunk) => handleSessionOutput(config, session, chunk));
  child.on("error", (error) => {
    session.status = "hata";
    session.message = "OAuth akışı başlatılamadı.";
    session.error = error instanceof Error ? error.message : "OAuth akışı başlatılamadı.";
  });

  return waitForAuthUrl(session);
}

async function submitCodexOAuthCallback(config, callbackUrl) {
  if (!currentSession) {
    throw new Error("Aktif bir OAuth oturumu yok.");
  }
  const normalized = String(callbackUrl || "").trim();
  if (!normalized.startsWith("http://") && !normalized.startsWith("https://")) {
    throw new Error("Yönlendirme adresi tam URL olarak yapıştırılmalı.");
  }
  if (!normalized.includes("code=")) {
    throw new Error("Yönlendirme adresinde yetki kodu bulunamadı.");
  }
  currentSession.status = "tamamlaniyor";
  currentSession.message = "OpenAI hesabı bağlantısı tamamlanıyor.";
  currentSession.child.stdin.write(`${normalized}\r\n`);
  const result = await Promise.race([
    currentSession.completion,
    waitForPersistedCodexConnection(config, currentSession, CALLBACK_TIMEOUT_MS),
  ]);
  if (!result.configured) {
    throw new Error(result.message || "OpenAI hesabı bağlanamadı.");
  }
  return result;
}

function cancelCodexOAuth() {
  if (!currentSession) {
    return {
      ok: true,
      authStatus: "iptal_edildi",
      message: "Aktif OAuth oturumu yoktu.",
    };
  }
  currentSession.status = "iptal_edildi";
  currentSession.message = "OpenAI oturum akışı iptal edildi.";
  currentSession.child.kill("SIGTERM");
  currentSession = null;
  return {
    ok: true,
    authStatus: "iptal_edildi",
    message: "OpenAI oturum akışı iptal edildi.",
  };
}

function getCodexAuthStatus(config) {
  if (currentSession) {
    return snapshotSession(currentSession);
  }
  return getPersistedCodexStatus(config);
}

function setCodexModel(config, model) {
  const selected = String(model || "").trim();
  if (!selected) {
    throw new Error("Seçilecek model belirtilmedi.");
  }
  runDocker(config, ["models", "set", selected]);
  const status = getPersistedCodexStatus(config);
  return {
    ...status,
    message: "Codex modeli güncellendi.",
  };
}

module.exports = {
  cancelCodexOAuth,
  getCodexAuthStatus,
  parseAuthUrl,
  resolveOpenClawImage,
  setCodexModel,
  startCodexOAuth,
  submitCodexOAuthCallback,
};
