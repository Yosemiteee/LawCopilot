const { waitForLoopbackCallback } = require("./oauth-loopback.cjs");

let currentSession = null;

const DEFAULT_LINKEDIN_SCOPES = ["openid", "profile", "email", "w_member_social", "r_member_social"];

function normalizeScopes(scopes) {
  const merged = [];
  for (const scope of [...DEFAULT_LINKEDIN_SCOPES, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function resolveCredentials(config) {
  const linkedin = config?.linkedin || {};
  return {
    clientId: String(linkedin.clientId || process.env.LAWCOPILOT_LINKEDIN_CLIENT_ID || "").trim(),
    clientSecret: String(linkedin.clientSecret || process.env.LAWCOPILOT_LINKEDIN_CLIENT_SECRET || "").trim(),
    redirectUri: String(linkedin.redirectUri || process.env.LAWCOPILOT_LINKEDIN_REDIRECT_URI || "http://127.0.0.1:1457/linkedin/auth/callback").trim(),
    scopes: normalizeScopes(linkedin.scopes),
  };
}

function getLinkedInAuthStatus(config) {
  const linkedin = config?.linkedin || {};
  const credentials = resolveCredentials(config);
  const clientReady = Boolean(credentials.clientId && credentials.clientSecret);
  return {
    provider: "linkedin",
    authStatus: linkedin.oauthConnected ? "bagli" : "hazir_degil",
    configured: Boolean(linkedin.oauthConnected && linkedin.accessToken),
    accountLabel: String(linkedin.accountLabel || "").trim(),
    userId: String(linkedin.userId || "").trim(),
    personUrn: String(linkedin.personUrn || "").trim(),
    email: String(linkedin.email || "").trim(),
    scopes: normalizeScopes(linkedin.scopes),
    clientReady,
    redirectUri: credentials.redirectUri,
    authUrl: currentSession?.authUrl || "",
    message: linkedin.oauthConnected
      ? "LinkedIn hesabı bağlandı."
      : clientReady
        ? "LinkedIn hesabı henüz bağlanmadı."
        : "LinkedIn OAuth istemcisi eksik. Önce istemci kimliği ve gizli anahtarı girin.",
    error: String(linkedin.oauthLastError || "").trim(),
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

function apiError(payload, fallback) {
  return String(payload?.error_description || payload?.error || payload?.message || fallback);
}

async function fetchUserInfo(accessToken) {
  const response = await fetch("https://api.linkedin.com/v2/userinfo", {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  const payload = await parseJson(response);
  if (!response.ok || !payload?.sub) {
    throw new Error(apiError(payload, "LinkedIn kullanıcı bilgisi alınamadı."));
  }
  return payload;
}

async function exchangeLinkedInCallback(config, callbackUrl) {
  if (!currentSession) {
    throw new Error("LinkedIn OAuth oturumu başlatılmadı.");
  }
  const credentials = resolveCredentials(config);
  if (!credentials.clientId || !credentials.clientSecret) {
    throw new Error("LinkedIn OAuth için istemci kimliği ve gizli anahtar gerekli.");
  }
  const url = new URL(String(callbackUrl || "").trim());
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code) {
    throw new Error("LinkedIn yönlendirme adresinde kod bulunamadı.");
  }
  if (state !== currentSession.state) {
    throw new Error("LinkedIn OAuth state doğrulaması başarısız oldu.");
  }
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: credentials.redirectUri,
    client_id: credentials.clientId,
    client_secret: credentials.clientSecret,
  });
  const tokenResponse = await fetch("https://www.linkedin.com/oauth/v2/accessToken", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });
  const tokenPayload = await parseJson(tokenResponse);
  if (!tokenResponse.ok || !tokenPayload.access_token) {
    throw new Error(apiError(tokenPayload, "LinkedIn erişim anahtarı alınamadı."));
  }
  const userInfo = await fetchUserInfo(String(tokenPayload.access_token));
  currentSession = null;
  const name = String(userInfo.name || [userInfo.given_name, userInfo.family_name].filter(Boolean).join(" ") || "").trim();
  const email = String(userInfo.email || "").trim();
  const userId = String(userInfo.sub || "").trim();
  return {
    configured: true,
    provider: "linkedin",
    accountLabel: name || email || "LinkedIn hesabı",
    userId,
    personUrn: userId ? `urn:li:person:${userId}` : "",
    email,
    accessToken: String(tokenPayload.access_token || ""),
    tokenType: String(tokenPayload.token_type || "Bearer"),
    expiryDate: tokenPayload.expires_in ? new Date(Date.now() + Number(tokenPayload.expires_in) * 1000).toISOString() : "",
    scopes: String(tokenPayload.scope || credentials.scopes.join(" ")).split(" ").filter(Boolean),
    authStatus: "bagli",
    message: "LinkedIn hesabı bağlandı.",
  };
}

async function startLinkedInOAuth(config, openUrl) {
  const credentials = resolveCredentials(config);
  if (!credentials.clientId || !credentials.clientSecret) {
    throw new Error("LinkedIn OAuth için istemci kimliği ve gizli anahtar gerekli.");
  }
  const state = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const authUrl = new URL("https://www.linkedin.com/oauth/v2/authorization");
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("client_id", credentials.clientId);
  authUrl.searchParams.set("redirect_uri", credentials.redirectUri);
  authUrl.searchParams.set("scope", credentials.scopes.join(" "));
  authUrl.searchParams.set("state", state);
  currentSession = {
    state,
    authUrl: authUrl.toString(),
    createdAt: Date.now(),
  };
  const browserTarget = await openUrl(authUrl.toString());
  const callbackUrl = await waitForLoopbackCallback(credentials.redirectUri, {
    timeoutMs: 180_000,
    successMessage: "LinkedIn bağlantısı tamamlandı. LawCopilot uygulamasına dönebilirsiniz.",
    errorMessage: "LinkedIn bağlantısı tamamlanamadı. LawCopilot uygulamasına dönüp tekrar deneyin.",
  });
  const status = await exchangeLinkedInCallback(config, callbackUrl);
  return {
    ...getLinkedInAuthStatus(config),
    ...status,
    authStatus: "bagli",
    authUrl: authUrl.toString(),
    browserTarget,
    callbackCaptured: true,
    message: "LinkedIn hesabı bağlandı ve yönlendirme otomatik tamamlandı.",
  };
}

function cancelLinkedInOAuth(config) {
  currentSession = null;
  return {
    ...getLinkedInAuthStatus(config),
    authStatus: "iptal",
    message: "LinkedIn oturum akışı iptal edildi.",
  };
}

module.exports = {
  cancelLinkedInOAuth,
  getLinkedInAuthStatus,
  startLinkedInOAuth,
};
