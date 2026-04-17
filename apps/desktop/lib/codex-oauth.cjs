const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { spawn, spawnSync } = require("child_process");
const { waitForLoopbackCallback } = require("./oauth-loopback.cjs");
const { mergeProviderModels, providerDefaults, providerSuggestedModels } = require("./provider-model-catalog.cjs");

const DOCKER_CANDIDATES = process.platform === "win32"
  ? ["docker.exe", "docker"]
  : ["/usr/bin/docker", "/usr/local/bin/docker", "docker"];

const OPENCLAW_IMAGE_CANDIDATES = [
  "openclaw-local:chromium",
  "ghcr.io/openclaw/openclaw:2026.3.2",
];

const OPENAI_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann";
const OPENAI_CODEX_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize";
const OPENAI_CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token";
const OPENAI_CODEX_REDIRECT_URI = "http://localhost:1455/auth/callback";
const OPENAI_CODEX_SCOPE = "openid profile email offline_access";
const OPENAI_CODEX_JWT_CLAIM_PATH = "https://api.openai.com/auth";

let cachedDockerBinary = null;
let cachedOpenClawImage = null;
let currentSession = null;
const LOOPBACK_TIMEOUT_MS = 300000;
const COMPLETION_TIMEOUT_MS = 90000;

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
  throw new Error("Docker bulunamadı. OpenAI hesabı (Codex) gelişmiş moddur ve Docker gerektirir. Normal kullanım için Gemini API veya OpenAI API seçin.");
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
  throw new Error("OpenClaw çalışma ortamı bulunamadı. OpenAI hesabı (Codex) gelişmiş moddur. Normal kullanım için Gemini API veya OpenAI API ile devam edin.");
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

function localOpenClawConfigPath(config) {
  return path.join(ensureStateDir(config), "openclaw.json");
}

function localModelsPath(config) {
  return path.join(ensureStateDir(config), "agents", "main", "agent", "models.json");
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

function readLocalCodexOAuthProfile(config) {
  const payload = safeReadJson(localAuthProfilesPath(config));
  const profiles = payload?.profiles && typeof payload.profiles === "object" ? payload.profiles : {};
  for (const [profileId, profile] of Object.entries(profiles)) {
    if (
      profile
      && String(profile.provider || "") === "openai-codex"
      && String(profile.type || "") === "oauth"
      && String(profile.access || "").trim()
    ) {
      return {
        profileId,
        access: String(profile.access || "").trim(),
        refresh: String(profile.refresh || "").trim(),
        expires: Number(profile.expires || 0) || null,
        accountId: String(profile.accountId || "").trim(),
        email: String(profile.email || "").trim(),
      };
    }
  }
  return null;
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

function createPkcePair() {
  const verifier = crypto.randomBytes(32).toString("base64url");
  const challenge = crypto.createHash("sha256").update(verifier).digest("base64url");
  return { verifier, challenge };
}

function createOAuthState() {
  return crypto.randomBytes(16).toString("hex");
}

function buildCodexAuthUrl({ challenge, state }) {
  const url = new URL(OPENAI_CODEX_AUTHORIZE_URL);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", OPENAI_CODEX_CLIENT_ID);
  url.searchParams.set("redirect_uri", OPENAI_CODEX_REDIRECT_URI);
  url.searchParams.set("scope", OPENAI_CODEX_SCOPE);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("state", state);
  url.searchParams.set("id_token_add_organizations", "true");
  url.searchParams.set("codex_cli_simplified_flow", "true");
  url.searchParams.set("originator", "pi");
  return url.toString();
}

function decodeJwtPayload(token) {
  try {
    const payload = String(token || "").split(".")[1] || "";
    if (!payload) {
      return null;
    }
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(Buffer.from(padded, "base64").toString("utf-8"));
  } catch {
    return null;
  }
}

function extractCodexAccountId(accessToken) {
  const payload = decodeJwtPayload(accessToken);
  const authNode = payload && typeof payload === "object" ? payload[OPENAI_CODEX_JWT_CLAIM_PATH] : null;
  const accountId = authNode && typeof authNode === "object" ? authNode.chatgpt_account_id : "";
  return typeof accountId === "string" && accountId.trim() ? accountId.trim() : "";
}

function mergeAuthProfileStores(base, next) {
  return {
    version: Math.max(Number(base?.version || 1), Number(next?.version || 1), 1),
    profiles: {
      ...(base?.profiles && typeof base.profiles === "object" ? base.profiles : {}),
      ...(next?.profiles && typeof next.profiles === "object" ? next.profiles : {}),
    },
    ...(base?.order && typeof base.order === "object" ? { order: { ...base.order } } : {}),
    ...(base?.lastGood && typeof base.lastGood === "object" ? { lastGood: { ...base.lastGood } } : {}),
    ...(base?.usageStats && typeof base.usageStats === "object" ? { usageStats: { ...base.usageStats } } : {}),
  };
}

function saveLocalAuthProfiles(config, payload) {
  const destination = localAuthProfilesPath(config);
  fs.mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
  fs.writeFileSync(destination, `${JSON.stringify(payload, null, 2)}\n`, { mode: 0o600 });
  return destination;
}

function saveJsonFile(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true, mode: 0o700 });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, { mode: 0o600 });
}

function ensureCodexModelState(config, preferredModel = "") {
  const codexDefaults = providerDefaults("openai-codex");
  const selected = String(preferredModel || config?.provider?.model || "").trim();
  const resolvedModel = selected.startsWith("openai-codex/") ? selected : codexDefaults.model;

  const openclawConfigPath = localOpenClawConfigPath(config);
  const openclawConfig = safeReadJson(openclawConfigPath) || {};
  const existingAuthProfiles = openclawConfig?.auth?.profiles && typeof openclawConfig.auth.profiles === "object"
    ? openclawConfig.auth.profiles
    : {};
  const existingAgents = openclawConfig?.agents && typeof openclawConfig.agents === "object"
    ? openclawConfig.agents
    : {};
  const existingDefaults = existingAgents?.defaults && typeof existingAgents.defaults === "object"
    ? existingAgents.defaults
    : {};
  const existingModelConfig = existingDefaults?.model && typeof existingDefaults.model === "object"
    ? existingDefaults.model
    : {};
  const existingModels = existingDefaults?.models && typeof existingDefaults.models === "object"
    ? existingDefaults.models
    : {};
  const nextConfig = {
    ...openclawConfig,
    auth: {
      ...(openclawConfig?.auth && typeof openclawConfig.auth === "object" ? openclawConfig.auth : {}),
      profiles: {
        ...existingAuthProfiles,
        "openai-codex:default": {
          ...(existingAuthProfiles["openai-codex:default"] && typeof existingAuthProfiles["openai-codex:default"] === "object"
            ? existingAuthProfiles["openai-codex:default"]
            : {}),
          provider: "openai-codex",
          mode: "oauth",
        },
      },
    },
    agents: {
      ...existingAgents,
      defaults: {
        ...existingDefaults,
        model: {
          ...existingModelConfig,
          primary: resolvedModel,
          fallbacks: [],
        },
        models: {
          ...existingModels,
          [resolvedModel]: existingModels[resolvedModel] && typeof existingModels[resolvedModel] === "object"
            ? existingModels[resolvedModel]
            : {},
        },
        workspace: String(existingDefaults.workspace || "/home/node/.openclaw/workspace"),
      },
    },
    meta: {
      ...(openclawConfig?.meta && typeof openclawConfig.meta === "object" ? openclawConfig.meta : {}),
      lastTouchedVersion: "2026.4.2",
      lastTouchedAt: nowIso(),
    },
  };
  saveJsonFile(openclawConfigPath, nextConfig);

  const modelsPath = localModelsPath(config);
  const modelsPayload = safeReadJson(modelsPath) || {};
  const existingProviders = modelsPayload?.providers && typeof modelsPayload.providers === "object"
    ? modelsPayload.providers
    : {};
  const existingCodexProvider = existingProviders?.["openai-codex"] && typeof existingProviders["openai-codex"] === "object"
    ? existingProviders["openai-codex"]
    : {};
  const currentProviderModels = Array.isArray(existingCodexProvider.models)
    ? existingCodexProvider.models.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const nextModelsPayload = {
    ...modelsPayload,
    providers: {
      ...existingProviders,
      "openai-codex": {
        ...existingCodexProvider,
        baseUrl: "https://chatgpt.com/backend-api",
        api: "openai-codex-responses",
        models: mergeProviderModels([resolvedModel], currentProviderModels),
      },
    },
  };
  saveJsonFile(modelsPath, nextModelsPayload);
  return resolvedModel;
}

function persistCodexOAuthCredentials(config, credentials) {
  const email = typeof credentials.email === "string" && credentials.email.trim()
    ? credentials.email.trim()
    : "default";
  const profileId = `openai-codex:${email}`;
  const existingPayload = safeReadJson(localAuthProfilesPath(config));
  const merged = mergeAuthProfileStores(existingPayload, {
    version: 1,
    profiles: {
      [profileId]: {
        type: "oauth",
        provider: "openai-codex",
        access: credentials.access,
        refresh: credentials.refresh,
        expires: credentials.expires,
        accountId: credentials.accountId,
        ...(credentials.email ? { email: credentials.email } : {}),
      },
    },
  });
  const providerOrder = Array.isArray(merged?.order?.["openai-codex"])
    ? merged.order["openai-codex"].filter((item) => item !== profileId)
    : [];
  merged.order = {
    ...(merged.order || {}),
    "openai-codex": [profileId, ...providerOrder],
  };
  merged.lastGood = {
    ...(merged.lastGood || {}),
    "openai-codex": profileId,
  };
  saveLocalAuthProfiles(config, merged);
  ensureCodexModelState(config);
  return { profileId, storePath: localAuthProfilesPath(config) };
}

async function exchangeCodexAuthorizationCode(code, verifier) {
  const response = await fetch(OPENAI_CODEX_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: OPENAI_CODEX_CLIENT_ID,
      code,
      code_verifier: verifier,
      redirect_uri: OPENAI_CODEX_REDIRECT_URI,
    }),
  });
  const responseText = await response.text().catch(() => "");
  let payload = {};
  try {
    payload = responseText ? JSON.parse(responseText) : {};
  } catch {
    payload = {};
  }
  if (!response.ok) {
    throw new Error(`OpenAI token değişimi başarısız oldu (${response.status}).`);
  }
  const access = String(payload.access_token || "").trim();
  const refresh = String(payload.refresh_token || "").trim();
  const expiresIn = Number(payload.expires_in || 0);
  const email = String(payload.email || payload.user?.email || "").trim();
  if (!access || !refresh || !Number.isFinite(expiresIn) || expiresIn <= 0) {
    throw new Error("OpenAI token yanıtı eksik geldi.");
  }
  const accountId = extractCodexAccountId(access);
  if (!accountId) {
    throw new Error("OpenAI hesabı kimliği alınamadı.");
  }
  return {
    access,
    refresh,
    expires: Date.now() + (expiresIn * 1000),
    accountId,
    email: email || undefined,
  };
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

function runDockerJsonAsync(config, openclawArgs) {
  const docker = resolveDockerBinary();
  const image = resolveOpenClawImage();
  const stateDir = ensureStateDir(config);
  return new Promise((resolve, reject) => {
    const child = spawn(
      docker,
      ["run", "--rm", "-v", `${stateDir}:/home/node/.openclaw`, image, "openclaw", ...openclawArgs],
      {
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk || "");
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk || "");
    });
    child.on("error", (error) => reject(error));
    child.on("close", (code) => {
      if (code !== 0) {
        const errorText = String(stderr || stdout || "").trim();
        reject(new Error(errorText || "OpenClaw komutu çalıştırılamadı."));
        return;
      }
      const raw = String(stdout || "").trim();
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch {
        reject(new Error("OpenClaw JSON çıktısı okunamadı."));
      }
    });
  });
}

function runDockerAsync(config, openclawArgs) {
  const docker = resolveDockerBinary();
  const image = resolveOpenClawImage();
  const stateDir = ensureStateDir(config);
  return new Promise((resolve, reject) => {
    const child = spawn(
      docker,
      ["run", "--rm", "-v", `${stateDir}:/home/node/.openclaw`, image, "openclaw", ...openclawArgs],
      {
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk || "");
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk || "");
    });
    child.on("error", (error) => reject(error));
    child.on("close", (code) => {
      if (code !== 0) {
        const errorText = String(stderr || stdout || "").trim();
        reject(new Error(errorText || "OpenClaw komutu çalıştırılamadı."));
        return;
      }
      resolve(String(stdout || "").trim());
    });
  });
}

function defaultCodexStatus(config) {
  const codexDefaults = providerDefaults("openai-codex");
  const catalogModels = providerSuggestedModels("openai-codex");
  const configuredModel = String(config?.provider?.model || "").trim();
  return {
    ok: true,
    provider: "openai-codex",
    authStatus: "hazır_değil",
    message: "Henüz OpenAI hesabı bağlanmadı.",
    browserOpened: false,
    configured: false,
    availableModels: [],
    catalogModels,
    selectedModel: configuredModel.startsWith("openai-codex/") ? configuredModel : codexDefaults.model,
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

async function getPersistedCodexStatus(config) {
  const status = defaultCodexStatus(config);
  try {
    importLegacyCodexAuth(config);
    const localProfile = readLocalCodexOAuthProfile(config);
    if (localProfile) {
      const codexDefaults = providerDefaults("openai-codex");
      const configuredModel = String(config?.provider?.model || "").trim();
      const selectedModel = ensureCodexModelState(
        config,
        configuredModel.startsWith("openai-codex/") ? configuredModel : codexDefaults.model,
      );
      return {
        ok: true,
        provider: "openai-codex",
        authStatus: "bagli",
        message: "OpenAI hesabı bağlı.",
        browserOpened: false,
        configured: true,
        availableModels: [],
        catalogModels: providerSuggestedModels("openai-codex"),
        selectedModel,
        stateDir: ensureStateDir(config),
        logFile: logFilePath(config),
        expiresAt: localProfile.expires || null,
      };
    }
    const [state, list] = await Promise.all([
      runDockerJsonAsync(config, ["models", "status", "--json"]),
      runDockerJsonAsync(config, ["models", "list", "--provider", "openai-codex", "--all", "--json"]),
    ]);
    const models = normalizeModelList(list);
    const catalogModels = mergeProviderModels(
      providerSuggestedModels("openai-codex"),
      models.map((item) => item.key),
    );
    const providerStatus = Array.isArray(state?.auth?.oauth?.providers)
      ? state.auth.oauth.providers.find((item) => String(item.provider || "") === "openai-codex")
      : null;
    const configured = providerStatus?.status === "ok";
    const persistedModel = String(state?.resolvedDefault || state?.defaultModel || "");
    const codexDefaults = providerDefaults("openai-codex");
    const configuredModel = String(config?.provider?.model || "").trim();
    const selectedModel = persistedModel.startsWith("openai-codex/")
      ? persistedModel
      : configuredModel.startsWith("openai-codex/")
        ? configuredModel
        : codexDefaults.model;
    return {
      ok: true,
      provider: "openai-codex",
      authStatus: configured ? "bagli" : "hazır_değil",
      message: configured ? "OpenAI hesabı bağlı." : "Henüz OpenAI hesabı bağlanmadı.",
      browserOpened: false,
      configured,
      availableModels: models.filter((item) => item.available).map((item) => item.key),
      catalogModels,
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
  cancelLoopbackWait(session);
}

function cancelLoopbackWait(session) {
  const loopbackPromise = session?.loopbackPromise;
  if (!loopbackPromise || typeof loopbackPromise.cancel !== "function") {
    return;
  }
  try {
    loopbackPromise.cancel();
  } catch {
    return;
  }
}

function parseAuthUrl(output) {
  const match = String(output || "").match(/https:\/\/auth\.openai\.com\/oauth\/authorize[^\s"'<>]+/);
  return match ? match[0] : "";
}

function normalizeCodexCallbackInput(callbackUrl) {
  const normalized = String(callbackUrl || "").trim();
  if (!normalized) {
    throw new Error("Yönlendirme adresi veya yetki kodu gerekli.");
  }
  if (normalized.startsWith("http://") || normalized.startsWith("https://")) {
    let parsed;
    try {
      parsed = new URL(normalized);
    } catch {
      throw new Error("Yönlendirme adresi tam URL olarak yapıştırılmalı.");
    }
    const code = String(parsed.searchParams.get("code") || "").trim();
    if (!code) {
      throw new Error("Yönlendirme adresinde yetki kodu bulunamadı.");
    }
    return {
      raw: normalized,
      submitValue: code,
      code,
    };
  }
  const compact = normalized.replace(/\s+/g, "");
  if (!compact || !compact.startsWith("ac_")) {
    throw new Error("Yetki kodu geçerli görünmüyor. Tam yönlendirme adresini veya sadece yetki kodunu yapıştırın.");
  }
  return {
    raw: normalized,
    submitValue: compact,
    code: compact,
  };
}

function shouldResetSession(session) {
  if (!session) {
    return false;
  }
  if (session.error || session.status === "hata" || session.status === "iptal_edildi") {
    return true;
  }
  const startedAt = Number(session.startedAt || 0);
  return startedAt > 0 && Date.now() - startedAt > LOOPBACK_TIMEOUT_MS + COMPLETION_TIMEOUT_MS;
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
    catalogModels: session.catalogModels || [],
    selectedModel: session.selectedModel || "",
    logFile: session.logFile,
    expiresAt: session.expiresAt || null,
    error: session.error || "",
  };
}

async function finalizeCodexConnection(config, session, normalized) {
  if (normalized.raw.startsWith("http://") || normalized.raw.startsWith("https://")) {
    try {
      const parsed = new URL(normalized.raw);
      const returnedState = String(parsed.searchParams.get("state") || "").trim();
      if (returnedState && returnedState !== String(session.state || "")) {
        throw new Error("OAuth durumu doğrulanamadı. Akışı yeniden başlatın.");
      }
    } catch (error) {
      if (error instanceof Error) {
        throw error;
      }
      throw new Error("OAuth yönlendirme adresi doğrulanamadı.");
    }
  }

  const credentials = await exchangeCodexAuthorizationCode(normalized.code, session.verifier);
  const persistedProfile = persistCodexOAuthCredentials(config, credentials);
  appendLog(config, `\n[lawcopilot] codex_oauth_persisted ${persistedProfile.profileId}\n`);

  const codexDefaults = providerDefaults("openai-codex");
  const configuredModel = String(config?.provider?.model || "").trim();
  const persisted = {
    ok: true,
    provider: "openai-codex",
    authStatus: "bagli",
    message: "OpenAI hesabı başarıyla bağlandı.",
    browserOpened: false,
    configured: true,
    availableModels: [],
    catalogModels: providerSuggestedModels("openai-codex"),
    selectedModel: configuredModel.startsWith("openai-codex/") ? configuredModel : codexDefaults.model,
    stateDir: ensureStateDir(config),
    logFile: logFilePath(config),
    expiresAt: credentials.expires,
  };
  session.status = "bagli";
  session.message = persisted.message;
  session.availableModels = persisted.availableModels;
  session.catalogModels = persisted.catalogModels;
  session.selectedModel = persisted.selectedModel;
  session.expiresAt = persisted.expiresAt;
  cleanupSession(session);
  if (currentSession && currentSession.id === session.id) {
    currentSession = null;
  }
  return persisted;
}

async function startCodexOAuth(config, onAuthUrl, options = {}) {
  const awaitAuthUrl = options.waitForAuthUrl !== false;
  ensureStateDir(config);
  if (shouldResetSession(currentSession)) {
    cleanupSession(currentSession);
    currentSession = null;
  }
  if (currentSession) {
    return snapshotSession(currentSession);
  }

  const codexDefaults = providerDefaults("openai-codex");
  const catalogModels = providerSuggestedModels("openai-codex");
  const { verifier, challenge } = createPkcePair();
  const state = createOAuthState();
  const authUrl = buildCodexAuthUrl({ challenge, state });
  const session = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    status: "callback_bekleniyor",
    message: "Tarayıcıda OpenAI oturumunu tamamlayın. LawCopilot bağlantıyı otomatik algılamaya çalışır.",
    authUrl,
    browserOpened: false,
    browserTarget: "",
    error: "",
    availableModels: [],
    catalogModels,
    selectedModel: String(config?.provider?.model || codexDefaults.model),
    logFile: logFilePath(config),
    expiresAt: null,
    verifier,
    state,
    redirectUri: OPENAI_CODEX_REDIRECT_URI,
    startedAt: Date.now(),
  };

  currentSession = session;
  appendLog(config, `\n[lawcopilot] codex_oauth_url ${authUrl}\n`);
  session.loopbackPromise = waitForLoopbackCallback(OPENAI_CODEX_REDIRECT_URI, {
    timeoutMs: LOOPBACK_TIMEOUT_MS,
    successMessage: "OpenAI bağlantısı tamamlandı. LawCopilot uygulamasına dönebilirsiniz.",
    errorMessage: "OpenAI bağlantısı tamamlanamadı. LawCopilot uygulamasına dönüp tekrar deneyin.",
  });
  session.loopbackTask = session.loopbackPromise
    .then(async (callbackUrl) => {
      appendLog(config, `\n[lawcopilot] codex_oauth_loopback ${callbackUrl}\n`);
      if (!currentSession || currentSession.id !== session.id) {
        return null;
      }
      if (session.submittingPromise) {
        return session.submittingPromise;
      }
      return submitCodexOAuthCallback(config, callbackUrl);
    })
    .catch((error) => {
      const message = error instanceof Error ? error.message : String(error || "");
      session.status = "hata";
      session.message = message || "OpenAI hesabı bağlantısı tamamlanamadı.";
      session.error = message || "OpenAI hesabı bağlantısı tamamlanamadı.";
      appendLog(config, `\n[lawcopilot] codex_oauth_loopback_error ${message}\n`);
      return null;
    });

  Promise.resolve(typeof onAuthUrl === "function" ? onAuthUrl(authUrl) : "")
    .then((target) => {
      session.browserOpened = true;
      session.browserTarget = String(target || "");
    })
    .catch((error) => {
      session.browserOpened = false;
      session.browserTarget = "";
      session.error = error instanceof Error ? error.message : "Tarayıcı açılamadı.";
    });

  try {
    return awaitAuthUrl ? snapshotSession(session) : snapshotSession(session);
  } catch (error) {
    const message = error instanceof Error ? error.message : "OAuth oturumu başlatılamadı.";
    session.status = "hata";
    session.message = message;
    session.error = message;
    cleanupSession(session);
    if (currentSession && currentSession.id === session.id) {
      currentSession = null;
    }
    throw error;
  }
}

async function submitCodexOAuthCallback(config, callbackUrl) {
  if (!currentSession) {
    throw new Error("Aktif bir OAuth oturumu yok.");
  }
  if (currentSession.submittingPromise) {
    return currentSession.submittingPromise;
  }
  const normalized = normalizeCodexCallbackInput(callbackUrl);
  currentSession.status = "tamamlaniyor";
  currentSession.message = "OpenAI hesabı bağlantısı tamamlanıyor. Bu adım normalde birkaç saniye sürer.";
  currentSession.lastSubmittedCode = normalized.code;
  cancelLoopbackWait(currentSession);
  appendLog(config, `\n[lawcopilot] codex_oauth_submit ${normalized.code.slice(0, 12)}...\n`);
  currentSession.submittingPromise = (async () => {
    return finalizeCodexConnection(config, currentSession, normalized);
  })();
  try {
    return await currentSession.submittingPromise;
  } catch (error) {
    const message = error instanceof Error ? error.message : "OpenAI hesabı bağlantısı tamamlanamadı.";
    if (currentSession) {
      currentSession.status = "hata";
      currentSession.message = message;
      currentSession.error = message;
    }
    throw error;
  } finally {
    if (currentSession) {
      currentSession.submittingPromise = null;
    }
  }
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
  cleanupSession(currentSession);
  currentSession = null;
  return {
    ok: true,
    authStatus: "iptal_edildi",
    message: "OpenAI oturum akışı iptal edildi.",
  };
}

async function getCodexAuthStatus(config) {
  if (currentSession) {
    return snapshotSession(currentSession);
  }
  return getPersistedCodexStatus(config);
}

async function setCodexModel(config, model) {
  const selected = String(model || "").trim();
  if (!selected) {
    throw new Error("Seçilecek model belirtilmedi.");
  }
  if (!selected.startsWith("openai-codex/")) {
    throw new Error("Geçersiz Codex modeli.");
  }
  ensureCodexModelState(config, selected);
  const status = await getPersistedCodexStatus(config);
  return {
    ...status,
    message: "Codex modeli güncellendi.",
  };
}

module.exports = {
  cancelCodexOAuth,
  getCodexAuthStatus,
  normalizeCodexCallbackInput,
  parseAuthUrl,
  resolveOpenClawImage,
  setCodexModel,
  startCodexOAuth,
  submitCodexOAuthCallback,
};
