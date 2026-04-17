const crypto = require("crypto");
const { waitForLoopbackCallback } = require("./oauth-loopback.cjs");

let currentSession = null;

const DEFAULT_X_SCOPES = ["tweet.read", "tweet.write", "users.read", "dm.read", "dm.write", "offline.access"];

function base64Url(value) {
  return Buffer.from(value)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function normalizeScopes(scopes) {
  const merged = [];
  for (const scope of [...DEFAULT_X_SCOPES, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function resolveCredentials(config) {
  const x = config?.x || {};
  return {
    clientId: String(x.clientId || process.env.LAWCOPILOT_X_CLIENT_ID || "").trim(),
    clientSecret: String(x.clientSecret || process.env.LAWCOPILOT_X_CLIENT_SECRET || "").trim(),
    redirectUri: String(x.redirectUri || process.env.LAWCOPILOT_X_REDIRECT_URI || "http://127.0.0.1:1457/x/auth/callback").trim(),
    scopes: normalizeScopes(x.scopes),
  };
}

function getXAuthStatus(config) {
  const x = config?.x || {};
  const credentials = resolveCredentials(config);
  return {
    provider: "x",
    authStatus: x.oauthConnected ? "bagli" : "hazir_degil",
    configured: Boolean(x.oauthConnected && x.accessToken),
    accountLabel: x.accountLabel || "",
    userId: x.userId || "",
    scopes: x.oauthConnected && Array.isArray(x.scopes) && x.scopes.length ? x.scopes : credentials.scopes,
    clientReady: Boolean(credentials.clientId),
    redirectUri: credentials.redirectUri,
    authUrl: currentSession?.authUrl || "",
    message: x.oauthConnected
      ? "X hesabı bağlandı."
      : credentials.clientId
        ? "X hesabı henüz bağlanmadı."
        : "X OAuth istemcisi tanımlı değil. Önce istemci kimliğini tanımlayın.",
    error: x.oauthLastError || "",
  };
}

async function parseJson(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

function tokenError(payload, fallback) {
  return String(payload?.error_description || payload?.error || payload?.title || fallback);
}

async function exchangeXCallback(config, callbackUrl) {
  if (!currentSession) {
    throw new Error("X OAuth oturumu başlatılmadı.");
  }
  const credentials = resolveCredentials(config);
  const url = new URL(String(callbackUrl || "").trim());
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code) {
    throw new Error("X yönlendirme adresinde kod bulunamadı.");
  }
  if (state !== currentSession.state) {
    throw new Error("X OAuth state doğrulaması başarısız oldu.");
  }
  const body = new URLSearchParams({
    code,
    grant_type: "authorization_code",
    client_id: credentials.clientId,
    redirect_uri: credentials.redirectUri,
    code_verifier: currentSession.codeVerifier,
  });
  const headers = {
    "Content-Type": "application/x-www-form-urlencoded",
  };
  if (credentials.clientSecret) {
    headers.Authorization = `Basic ${Buffer.from(`${credentials.clientId}:${credentials.clientSecret}`).toString("base64")}`;
  }
  const tokenResponse = await fetch("https://api.x.com/2/oauth2/token", {
    method: "POST",
    headers,
    body,
  });
  const tokenPayload = await parseJson(tokenResponse);
  if (!tokenResponse.ok || !tokenPayload.access_token) {
    throw new Error(tokenError(tokenPayload, "X erişim anahtarı alınamadı."));
  }

  const meResponse = await fetch("https://api.x.com/2/users/me", {
    headers: {
      Authorization: `Bearer ${tokenPayload.access_token}`,
    },
  });
  const mePayload = await parseJson(meResponse);
  if (!meResponse.ok || !mePayload?.data?.id) {
    throw new Error(tokenError(mePayload, "X kullanıcı bilgisi alınamadı."));
  }
  currentSession = null;
  return {
    configured: true,
    provider: "x",
    accountLabel: String(mePayload.data.username || mePayload.data.name || "X hesabı"),
    userId: String(mePayload.data.id || ""),
    accessToken: String(tokenPayload.access_token || ""),
    refreshToken: String(tokenPayload.refresh_token || ""),
    tokenType: String(tokenPayload.token_type || "bearer"),
    expiryDate: tokenPayload.expires_in ? new Date(Date.now() + Number(tokenPayload.expires_in) * 1000).toISOString() : "",
    scopes: String(tokenPayload.scope || credentials.scopes.join(" ")).split(" ").filter(Boolean),
    authStatus: "bagli",
    message: "X hesabı bağlandı.",
  };
}

async function startXOAuth(config, openUrl) {
  const credentials = resolveCredentials(config);
  if (!credentials.clientId) {
    throw new Error("X OAuth istemcisi tanımlı değil. LAWCOPILOT_X_CLIENT_ID gerekir.");
  }
  const state = crypto.randomBytes(16).toString("hex");
  const codeVerifier = base64Url(crypto.randomBytes(32));
  const codeChallenge = base64Url(crypto.createHash("sha256").update(codeVerifier).digest());
  const authUrl = new URL("https://twitter.com/i/oauth2/authorize");
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("client_id", credentials.clientId);
  authUrl.searchParams.set("redirect_uri", credentials.redirectUri);
  authUrl.searchParams.set("scope", credentials.scopes.join(" "));
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("code_challenge", codeChallenge);
  authUrl.searchParams.set("code_challenge_method", "S256");
  currentSession = {
    state,
    codeVerifier,
    authUrl: authUrl.toString(),
    createdAt: Date.now(),
  };
  const browserTarget = await openUrl(authUrl.toString());
  const callbackUrl = await waitForLoopbackCallback(credentials.redirectUri, {
    timeoutMs: 180_000,
    successMessage: "X bağlantısı tamamlandı. LawCopilot uygulamasına dönebilirsiniz.",
    errorMessage: "X bağlantısı tamamlanamadı. LawCopilot uygulamasına dönüp tekrar deneyin.",
  });
  const status = await exchangeXCallback(config, callbackUrl);
  return {
    ...getXAuthStatus(config),
    ...status,
    authStatus: "bagli",
    authUrl: authUrl.toString(),
    browserTarget,
    callbackCaptured: true,
    message: "X hesabı bağlandı ve yönlendirme otomatik tamamlandı.",
  };
}

function cancelXOAuth(config) {
  currentSession = null;
  const x = config?.x || {};
  return {
    ...getXAuthStatus({
      ...config,
      x: {
        ...x,
        enabled: false,
        accountLabel: "",
        userId: "",
        scopes: [],
        oauthConnected: false,
        oauthLastError: "",
        configuredAt: "",
        lastValidatedAt: "",
        validationStatus: "pending",
        lastSyncAt: "",
        accessToken: "",
        refreshToken: "",
        tokenType: "",
        expiryDate: "",
        clientId: "",
        clientSecret: "",
      },
    }),
    authStatus: "iptal",
    message: "X oturum akışı iptal edildi.",
    patch: {
      x: {
        enabled: false,
        accountLabel: "",
        userId: "",
        scopes: [],
        oauthConnected: false,
        oauthLastError: "",
        configuredAt: "",
        lastValidatedAt: "",
        validationStatus: "pending",
        lastSyncAt: "",
        accessToken: "",
        refreshToken: "",
        tokenType: "",
        expiryDate: "",
        clientId: "",
        clientSecret: "",
        redirectUri: String(x.redirectUri || ""),
      },
    },
  };
}

module.exports = {
  cancelXOAuth,
  getXAuthStatus,
  startXOAuth,
};
