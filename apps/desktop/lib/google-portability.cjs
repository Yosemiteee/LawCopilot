const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { normalizeGooglePortabilityScopes } = require("./config.cjs");
const { waitForLoopbackCallback } = require("./oauth-loopback.cjs");

let currentSession = null;

function nowIso() {
  return new Date().toISOString();
}

function logFilePath(config) {
  const base = config?.storagePath || path.join(os.homedir(), ".config", "LawCopilot", "artifacts");
  const runtimeDir = path.join(base, "runtime");
  fs.mkdirSync(runtimeDir, { recursive: true, mode: 0o700 });
  return path.join(runtimeDir, "google-portability-oauth.log");
}

function appendLog(config, text) {
  try {
    fs.appendFileSync(logFilePath(config), text, { mode: 0o600 });
  } catch {
    return;
  }
}

function resolveCredentials(config) {
  const portability = config?.googlePortability || {};
  const google = config?.google || {};
  const clientId = String(
    portability.clientId || google.clientId || process.env.LAWCOPILOT_GOOGLE_PORTABILITY_CLIENT_ID || process.env.LAWCOPILOT_GOOGLE_CLIENT_ID || "",
  ).trim();
  const clientSecret = String(
    portability.clientSecret
      || google.clientSecret
      || process.env.LAWCOPILOT_GOOGLE_PORTABILITY_CLIENT_SECRET
      || process.env.LAWCOPILOT_GOOGLE_CLIENT_SECRET
      || "",
  ).trim();
  const redirectUri = String(
    portability.redirectUri
      || process.env.LAWCOPILOT_GOOGLE_PORTABILITY_REDIRECT_URI
      || "http://127.0.0.1:1459/google/portability/auth/callback",
  ).trim();
  return {
    clientId,
    clientSecret,
    redirectUri,
    scopes: normalizeGooglePortabilityScopes(portability.scopes),
  };
}

function getGooglePortabilityAuthStatus(config) {
  const portability = config?.googlePortability || {};
  const credentials = resolveCredentials(config);
  const baseStatus = {
    provider: "google-portability",
    configured: Boolean(portability.oauthConnected && portability.accessToken),
    accountLabel: portability.accountLabel || "",
    scopes: Array.isArray(portability.scopes) ? portability.scopes : credentials.scopes,
    clientReady: Boolean(credentials.clientId && credentials.clientSecret),
    redirectUri: credentials.redirectUri,
    archiveJobId: String(portability.archiveJobId || ""),
    archiveState: String(portability.archiveState || ""),
    archiveStartedAt: String(portability.archiveStartedAt || ""),
    archiveExportTime: String(portability.archiveExportTime || ""),
    lastSyncAt: String(portability.lastSyncAt || ""),
    logFile: logFilePath(config),
  };
  if (currentSession?.status === "waiting") {
    return {
      ...baseStatus,
      authStatus: "bekliyor",
      authUrl: currentSession.authUrl || "",
      browserTarget: currentSession.browserTarget || "",
      message: "Google geçmiş aktarımı için izin ekranı açıldı. Tarayıcıda izinleri tamamlayın; LawCopilot bağlantıyı otomatik algılar.",
      error: "",
    };
  }
  if (currentSession?.status === "error") {
    return {
      ...baseStatus,
      authStatus: "hata",
      authUrl: currentSession.authUrl || "",
      browserTarget: currentSession.browserTarget || "",
      message: currentSession.error || "Google geçmiş aktarımı bağlantısı tamamlanamadı.",
      error: currentSession.error || "",
    };
  }
  if (currentSession?.status === "complete" && currentSession.completedStatus) {
    return {
      ...baseStatus,
      ...currentSession.completedStatus,
      authStatus: "bagli",
      authUrl: currentSession.authUrl || "",
      browserTarget: currentSession.browserTarget || "",
      clientReady: Boolean(credentials.clientId && credentials.clientSecret),
      redirectUri: credentials.redirectUri,
      logFile: logFilePath(config),
    };
  }
  return {
    ...baseStatus,
    authStatus: portability.oauthConnected ? "bagli" : "hazir_degil",
    message: portability.oauthConnected
      ? "Google geçmiş aktarımı bağlantısı hazır."
      : credentials.clientId && credentials.clientSecret
        ? "Google geçmiş aktarımı henüz bağlanmadı."
        : "Google geçmiş aktarımı için OAuth istemcisi hazır değil.",
    error: portability.oauthLastError || "",
    authUrl: currentSession?.authUrl || "",
    browserTarget: currentSession?.browserTarget || "",
  };
}

async function exchangeGooglePortabilityCallback(config, callbackUrl) {
  if (!currentSession) {
    throw new Error("Google geçmiş aktarımı oturumu başlatılmadı.");
  }
  const url = new URL(String(callbackUrl || "").trim());
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code) {
    throw new Error("Google yönlendirme adresinde kod bulunamadı.");
  }
  if (state !== currentSession.state) {
    throw new Error("Google geçmiş aktarımı state doğrulaması başarısız oldu.");
  }
  const credentials = resolveCredentials(config);
  const body = new URLSearchParams({
    code,
    client_id: credentials.clientId,
    client_secret: credentials.clientSecret,
    redirect_uri: credentials.redirectUri,
    grant_type: "authorization_code",
  });
  const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const tokenPayload = await tokenResponse.json().catch(() => ({}));
  if (!tokenResponse.ok || !tokenPayload.access_token) {
    throw new Error(String(tokenPayload.error_description || tokenPayload.error || "Google geçmiş aktarımı token'ı alınamadı."));
  }
  const portability = config?.googlePortability || {};
  const google = config?.google || {};
  const accountLabel = String(
    portability.accountLabel
      || google.accountLabel
      || "Google geçmiş aktarımı",
  ).trim();
  appendLog(config, `[${nowIso()}] google_portability_oauth_complete ${accountLabel}\n`);
  return {
    configured: true,
    provider: "google-portability",
    accountLabel,
    accessToken: String(tokenPayload.access_token || ""),
    refreshToken: String(tokenPayload.refresh_token || ""),
    tokenType: String(tokenPayload.token_type || "Bearer"),
    expiryDate: tokenPayload.expires_in ? new Date(Date.now() + Number(tokenPayload.expires_in) * 1000).toISOString() : "",
    scopes: String(tokenPayload.scope || "").split(" ").filter(Boolean),
    authStatus: "bagli",
    message: "Google geçmiş aktarımı bağlantısı kuruldu.",
  };
}

async function startGooglePortabilityOAuth(config, openUrl) {
  const credentials = resolveCredentials(config);
  if (!credentials.clientId || !credentials.clientSecret) {
    throw new Error("Google geçmiş aktarımı için OAuth istemcisi hazır değil.");
  }
  if (currentSession?.status === "waiting") {
    return getGooglePortabilityAuthStatus(config);
  }
  const state = crypto.randomBytes(16).toString("hex");
  const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  authUrl.searchParams.set("client_id", credentials.clientId);
  authUrl.searchParams.set("redirect_uri", credentials.redirectUri);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("scope", credentials.scopes.join(" "));
  authUrl.searchParams.set("access_type", "offline");
  authUrl.searchParams.set("prompt", "consent");
  authUrl.searchParams.set("state", state);
  currentSession = {
    state,
    authUrl: authUrl.toString(),
    createdAt: Date.now(),
    status: "waiting",
    completedStatus: null,
    error: "",
    browserTarget: "",
  };
  let browserTarget = "";
  try {
    browserTarget = await openUrl(authUrl.toString());
  } catch (error) {
    currentSession = null;
    throw error;
  }
  currentSession.browserTarget = browserTarget;
  appendLog(config, `[${nowIso()}] google_portability_oauth_start ${browserTarget}\n`);
  currentSession.completionPromise = waitForLoopbackCallback(credentials.redirectUri, {
    timeoutMs: 180_000,
    successMessage: "Google geçmiş aktarımı bağlantısı tamamlandı. LawCopilot uygulamasına dönebilirsiniz.",
    errorMessage: "Google geçmiş aktarımı bağlantısı tamamlanamadı. LawCopilot uygulamasına dönüp tekrar deneyin.",
  })
    .then((callbackUrl) => exchangeGooglePortabilityCallback(config, callbackUrl))
    .then((status) => {
      if (currentSession?.state === state) {
        currentSession.status = "complete";
        currentSession.completedStatus = status;
        currentSession.error = "";
      }
      return status;
    })
    .catch((error) => {
      if (currentSession?.state === state) {
        currentSession.status = "error";
        currentSession.error = error instanceof Error ? error.message : "Google geçmiş aktarımı bağlantısı tamamlanamadı.";
      }
      return null;
    });
  return getGooglePortabilityAuthStatus(config);
}

async function submitGooglePortabilityOAuthCallback(config, callbackUrl) {
  const status = await exchangeGooglePortabilityCallback(config, callbackUrl);
  if (currentSession) {
    currentSession.status = "complete";
    currentSession.completedStatus = status;
    currentSession.error = "";
  }
  return status;
}

function consumeCompletedGooglePortabilityOAuth() {
  if (!currentSession) {
    return null;
  }
  if (currentSession.status === "complete" && currentSession.completedStatus) {
    const completed = currentSession.completedStatus;
    currentSession = null;
    return { status: completed };
  }
  if (currentSession.status === "error") {
    const error = currentSession.error || "Google geçmiş aktarımı bağlantısı tamamlanamadı.";
    currentSession = null;
    return { error };
  }
  return null;
}

function cancelGooglePortabilityOAuth(config) {
  currentSession = null;
  appendLog(config, `[${nowIso()}] google_portability_oauth_cancelled\n`);
  return {
    ...getGooglePortabilityAuthStatus(config),
    authStatus: "iptal",
    message: "Google geçmiş aktarımı oturum akışı iptal edildi.",
  };
}

module.exports = {
  cancelGooglePortabilityOAuth,
  consumeCompletedGooglePortabilityOAuth,
  getGooglePortabilityAuthStatus,
  startGooglePortabilityOAuth,
  submitGooglePortabilityOAuthCallback,
};
