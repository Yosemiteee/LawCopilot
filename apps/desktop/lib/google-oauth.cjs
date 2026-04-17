const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { waitForLoopbackCallback } = require("./oauth-loopback.cjs");

let currentSession = null;
const DEFAULT_GOOGLE_SCOPES = [
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

function normalizeGoogleScopes(scopes) {
  const merged = [];
  for (const scope of [...DEFAULT_GOOGLE_SCOPES, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function nowIso() {
  return new Date().toISOString();
}

function logFilePath(config) {
  const base = config?.storagePath || path.join(os.homedir(), ".config", "LawCopilot", "artifacts");
  const runtimeDir = path.join(base, "runtime");
  fs.mkdirSync(runtimeDir, { recursive: true, mode: 0o700 });
  return path.join(runtimeDir, "google-oauth.log");
}

function appendLog(config, text) {
  try {
    fs.appendFileSync(logFilePath(config), text, { mode: 0o600 });
  } catch {
    return;
  }
}

function resolveCredentials(config) {
  const google = config?.google || {};
  const clientId = String(google.clientId || process.env.LAWCOPILOT_GOOGLE_CLIENT_ID || "").trim();
  const clientSecret = String(google.clientSecret || process.env.LAWCOPILOT_GOOGLE_CLIENT_SECRET || "").trim();
  const redirectUri = String(google.redirectUri || process.env.LAWCOPILOT_GOOGLE_REDIRECT_URI || "http://127.0.0.1:1456/google/auth/callback").trim();
  return {
    clientId,
    clientSecret,
    redirectUri,
    scopes: normalizeGoogleScopes(config?.google?.scopes),
  };
}

function getGoogleAuthStatus(config) {
  const google = config?.google || {};
  const credentials = resolveCredentials(config);
  if (currentSession?.status === "waiting") {
    return {
      provider: "google",
      authStatus: "bekliyor",
      configured: false,
      accountLabel: google.accountLabel || "",
      scopes: Array.isArray(google.scopes) ? google.scopes : credentials.scopes,
      clientReady: Boolean(credentials.clientId && credentials.clientSecret),
      redirectUri: credentials.redirectUri,
      authUrl: currentSession.authUrl || "",
      browserTarget: currentSession.browserTarget || "",
      message: "Google giriş ekranı açıldı. Tarayıcıda izinleri tamamlayın; LawCopilot bağlantıyı otomatik algılar.",
      error: "",
      logFile: logFilePath(config),
    };
  }
  if (currentSession?.status === "error") {
    return {
      provider: "google",
      authStatus: "hata",
      configured: false,
      accountLabel: google.accountLabel || "",
      scopes: Array.isArray(google.scopes) ? google.scopes : credentials.scopes,
      clientReady: Boolean(credentials.clientId && credentials.clientSecret),
      redirectUri: credentials.redirectUri,
      authUrl: currentSession.authUrl || "",
      browserTarget: currentSession.browserTarget || "",
      message: currentSession.error || "Google bağlantısı tamamlanamadı.",
      error: currentSession.error || "",
      logFile: logFilePath(config),
    };
  }
  if (currentSession?.status === "complete" && currentSession.completedStatus) {
    return {
      provider: "google",
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
    provider: "google",
    authStatus: google.oauthConnected ? "bagli" : "hazir_degil",
    configured: Boolean(google.oauthConnected && google.accessToken),
    accountLabel: google.accountLabel || "",
    scopes: Array.isArray(google.scopes) ? google.scopes : credentials.scopes,
    clientReady: Boolean(credentials.clientId && credentials.clientSecret),
    redirectUri: credentials.redirectUri,
    authUrl: currentSession?.authUrl || "",
    message: google.oauthConnected
      ? "Google hesabı bağlandı."
      : credentials.clientId && credentials.clientSecret
        ? "Google hesabı henüz bağlanmadı."
        : "Google OAuth istemcisi tanımlı değil. Önce istemci kimliği ve gizli anahtar tanımlayın.",
    error: google.oauthLastError || "",
    logFile: logFilePath(config),
  };
}

async function exchangeGoogleCallback(config, callbackUrl) {
  if (!currentSession) {
    throw new Error("Google OAuth oturumu başlatılmadı.");
  }
  const url = new URL(String(callbackUrl || "").trim());
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code) {
    throw new Error("Google yönlendirme adresinde kod bulunamadı.");
  }
  if (state !== currentSession.state) {
    throw new Error("Google OAuth state doğrulaması başarısız oldu.");
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
    throw new Error(String(tokenPayload.error_description || tokenPayload.error || "Google token alınamadı."));
  }
  const userInfoResponse = await fetch("https://www.googleapis.com/oauth2/v2/userinfo", {
    headers: { Authorization: `Bearer ${tokenPayload.access_token}` },
  });
  const userInfo = await userInfoResponse.json().catch(() => ({}));
  appendLog(config, `[${nowIso()}] google_oauth_complete ${String(userInfo.email || "")}\n`);
  return {
    configured: true,
    provider: "google",
    accountLabel: String(userInfo.email || userInfo.name || "Google hesabı"),
    accessToken: String(tokenPayload.access_token || ""),
    refreshToken: String(tokenPayload.refresh_token || ""),
    tokenType: String(tokenPayload.token_type || "Bearer"),
    expiryDate: tokenPayload.expires_in ? new Date(Date.now() + Number(tokenPayload.expires_in) * 1000).toISOString() : "",
    scopes: String(tokenPayload.scope || "").split(" ").filter(Boolean),
    authStatus: "bagli",
    message: "Google hesabı bağlandı.",
  };
}

async function startGoogleOAuth(config, openUrl) {
  const credentials = resolveCredentials(config);
  if (!credentials.clientId || !credentials.clientSecret) {
    throw new Error("Google OAuth istemcisi tanımlı değil. LAWCOPILOT_GOOGLE_CLIENT_ID ve LAWCOPILOT_GOOGLE_CLIENT_SECRET gerekir.");
  }
  if (currentSession?.status === "waiting") {
    return getGoogleAuthStatus(config);
  }
  const state = crypto.randomBytes(16).toString("hex");
  const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  authUrl.searchParams.set("client_id", credentials.clientId);
  authUrl.searchParams.set("redirect_uri", credentials.redirectUri);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("scope", credentials.scopes.join(" "));
  authUrl.searchParams.set("access_type", "offline");
  authUrl.searchParams.set("include_granted_scopes", "true");
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
  appendLog(config, `[${nowIso()}] google_oauth_start ${browserTarget}\n`);
  currentSession.completionPromise = waitForLoopbackCallback(credentials.redirectUri, {
    timeoutMs: 180_000,
    successMessage: "Google bağlantısı tamamlandı. LawCopilot uygulamasına dönebilirsiniz.",
    errorMessage: "Google bağlantısı tamamlanamadı. LawCopilot uygulamasına dönüp tekrar deneyin.",
  })
    .then((callbackUrl) => exchangeGoogleCallback(config, callbackUrl))
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
        currentSession.error = error instanceof Error ? error.message : "Google bağlantısı tamamlanamadı.";
      }
      return null;
    });
  return getGoogleAuthStatus(config);
}

async function submitGoogleOAuthCallback(config, callbackUrl) {
  const status = await exchangeGoogleCallback(config, callbackUrl);
  if (currentSession) {
    currentSession.status = "complete";
    currentSession.completedStatus = status;
    currentSession.error = "";
  }
  return status;
}

function consumeCompletedGoogleOAuth() {
  if (!currentSession) {
    return null;
  }
  if (currentSession.status === "complete" && currentSession.completedStatus) {
    const completed = currentSession.completedStatus;
    currentSession = null;
    return { status: completed };
  }
  if (currentSession.status === "error") {
    const error = currentSession.error || "Google bağlantısı tamamlanamadı.";
    currentSession = null;
    return { error };
  }
  return null;
}

function cancelGoogleOAuth(config) {
  currentSession = null;
  appendLog(config, `[${nowIso()}] google_oauth_cancelled\n`);
  return {
    ...getGoogleAuthStatus(config),
    authStatus: "iptal",
    message: "Google oturum akışı iptal edildi.",
  };
}

module.exports = {
  cancelGoogleOAuth,
  consumeCompletedGoogleOAuth,
  getGoogleAuthStatus,
  startGoogleOAuth,
  submitGoogleOAuthCallback,
};
