const crypto = require("crypto");
const { waitForLoopbackCallback } = require("./oauth-loopback.cjs");

let currentSession = null;
let pendingLoopback = null;

const DEFAULT_OUTLOOK_SCOPES = [
  "openid",
  "email",
  "profile",
  "offline_access",
  "User.Read",
  "Mail.Read",
  "Calendars.Read",
];

function base64Url(value) {
  return Buffer.from(value)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function normalizeScopes(scopes) {
  const merged = [];
  for (const scope of [...DEFAULT_OUTLOOK_SCOPES, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function resolveCredentials(config) {
  const outlook = config?.outlook || {};
  return {
    clientId: String(outlook.clientId || process.env.LAWCOPILOT_OUTLOOK_CLIENT_ID || "").trim(),
    tenantId: String(outlook.tenantId || process.env.LAWCOPILOT_OUTLOOK_TENANT_ID || "common").trim() || "common",
    redirectUri: String(outlook.redirectUri || process.env.LAWCOPILOT_OUTLOOK_REDIRECT_URI || "http://127.0.0.1:1458/outlook/auth/callback").trim(),
    scopes: normalizeScopes(outlook.scopes),
  };
}

function getOutlookAuthStatus(config) {
  const outlook = config?.outlook || {};
  const credentials = resolveCredentials(config);
  return {
    provider: "outlook",
    authStatus: outlook.oauthConnected ? "bagli" : "hazir_degil",
    configured: Boolean(outlook.oauthConnected && outlook.accessToken),
    accountLabel: outlook.accountLabel || "",
    clientId: credentials.clientId,
    tenantId: credentials.tenantId,
    scopes: Array.isArray(outlook.scopes) ? outlook.scopes : credentials.scopes,
    clientReady: Boolean(credentials.clientId),
    redirectUri: credentials.redirectUri,
    authUrl: currentSession?.authUrl || "",
    message: outlook.oauthConnected
      ? "Outlook hesabı bağlandı."
      : credentials.clientId
        ? "Outlook hesabı henüz bağlanmadı."
        : "Outlook OAuth istemcisi tanımlı değil. Önce uygulama kimliğini girin.",
    error: outlook.oauthLastError || "",
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
  return String(payload?.error_description || payload?.error?.message || payload?.error || fallback);
}

function normalizeErrorText(value) {
  return String(value || "").toLowerCase();
}

function describeOutlookCallbackError(callbackUrl, credentials = {}) {
  const url = new URL(String(callbackUrl || "").trim());
  const error = String(url.searchParams.get("error") || "").trim();
  const errorDescription = String(url.searchParams.get("error_description") || "").replace(/\+/g, " ").trim();
  if (!error && !errorDescription) {
    return "";
  }

  const detail = errorDescription || error;
  const normalized = normalizeErrorText(`${error} ${errorDescription}`);
  const codeMatch = detail.match(/AADSTS\d+/i) || error.match(/AADSTS\d+/i);
  const code = codeMatch ? codeMatch[0].toUpperCase() : "";
  const redirectUri = String(credentials.redirectUri || "http://127.0.0.1:1458/outlook/auth/callback").trim();
  const tenantId = String(credentials.tenantId || "common").trim() || "common";
  const tenantHint = tenantId === "common"
    ? " LawCopilot tarafında tenant alanını `common` bırakmanız doğru."
    : ` LawCopilot tarafında şu an tenant alanında \`${tenantId}\` kayıtlı; kişisel veya farklı tenant hesaplarında \`common\` kullanın.`;

  if (
    normalized.includes("does not exist in tenant")
    || normalized.includes("needs to be added as an external user")
    || normalized.includes("microsoft services")
    || normalized.includes("personal microsoft accounts")
    || normalized.includes("multi-tenant")
    || normalized.includes("multitenant")
  ) {
    return (
      "Bu Microsoft hesabı mevcut Azure uygulama kaydıyla uyumlu değil. "
      + "Kişisel Outlook/Hotmail/Live hesabı bağlayacaksanız Azure uygulamasında `Supported account types` ayarını "
      + "`Accounts in any organizational directory and personal Microsoft accounts` yapın. "
      + "Sadece şirket Microsoft 365 hesabı kullanılacaksa doğru tenant hesabıyla giriş yapın."
      + tenantHint
    );
  }

  if (normalized.includes("redirect uri") || normalized.includes("reply url")) {
    return (
      "Azure uygulama kaydındaki yönlendirme adresi LawCopilot ile uyuşmuyor. "
      + "Authentication bölümünde platform olarak `Mobile and desktop applications` ekleyin ve yönlendirme adresini "
      + `\`${redirectUri}\` yapın.`
    );
  }

  if (
    normalized.includes("public client")
    || normalized.includes("native client")
    || normalized.includes("cross-origin token redemption")
  ) {
    return (
      "Azure uygulama kaydı masaüstü OAuth akışına uygun görünmüyor. "
      + "Authentication bölümünde platform olarak `Mobile and desktop applications` kullanın; web istemcisi gibi kurmayın."
    );
  }

  return code ? `Outlook OAuth hatası (${code}): ${detail}` : `Outlook OAuth hatası: ${detail}`;
}

async function exchangeOutlookCallback(config, callbackUrl) {
  if (!currentSession) {
    throw new Error("Outlook OAuth oturumu başlatılmadı.");
  }
  const credentials = resolveCredentials(config);
  const url = new URL(String(callbackUrl || "").trim());
  const callbackError = describeOutlookCallbackError(callbackUrl, credentials);
  if (callbackError) {
    throw new Error(callbackError);
  }
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code) {
    throw new Error("Outlook yönlendirme adresinde kod bulunamadı.");
  }
  if (state !== currentSession.state) {
    throw new Error("Outlook OAuth state doğrulaması başarısız oldu.");
  }

  const body = new URLSearchParams({
    client_id: credentials.clientId,
    grant_type: "authorization_code",
    code,
    redirect_uri: credentials.redirectUri,
    code_verifier: currentSession.codeVerifier,
  });
  const tokenResponse = await fetch(`https://login.microsoftonline.com/${encodeURIComponent(credentials.tenantId)}/oauth2/v2.0/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const tokenPayload = await parseJson(tokenResponse);
  if (!tokenResponse.ok || !tokenPayload.access_token) {
    throw new Error(tokenError(tokenPayload, "Outlook erişim anahtarı alınamadı."));
  }

  const meResponse = await fetch("https://graph.microsoft.com/v1.0/me?$select=displayName,mail,userPrincipalName", {
    headers: {
      Authorization: `Bearer ${tokenPayload.access_token}`,
    },
  });
  const mePayload = await parseJson(meResponse);
  if (!meResponse.ok) {
    throw new Error(tokenError(mePayload, "Outlook kullanıcı bilgisi alınamadı."));
  }

  currentSession = null;
  return {
    configured: true,
    provider: "outlook",
    accountLabel: String(mePayload.mail || mePayload.userPrincipalName || mePayload.displayName || "Outlook hesabı"),
    tenantId: credentials.tenantId,
    accessToken: String(tokenPayload.access_token || ""),
    refreshToken: String(tokenPayload.refresh_token || ""),
    tokenType: String(tokenPayload.token_type || "Bearer"),
    expiryDate: tokenPayload.expires_in ? new Date(Date.now() + Number(tokenPayload.expires_in) * 1000).toISOString() : "",
    scopes: String(tokenPayload.scope || credentials.scopes.join(" ")).split(" ").filter(Boolean),
    authStatus: "bagli",
    message: "Outlook hesabı bağlandı.",
  };
}

async function startOutlookOAuth(config, openUrl) {
  const credentials = resolveCredentials(config);
  if (!credentials.clientId) {
    throw new Error("Outlook OAuth istemcisi tanımlı değil. Uygulama kimliği gerekir.");
  }
  const state = crypto.randomBytes(16).toString("hex");
  const codeVerifier = base64Url(crypto.randomBytes(32));
  const codeChallenge = base64Url(crypto.createHash("sha256").update(codeVerifier).digest());
  const authUrl = new URL(`https://login.microsoftonline.com/${encodeURIComponent(credentials.tenantId)}/oauth2/v2.0/authorize`);
  authUrl.searchParams.set("client_id", credentials.clientId);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("redirect_uri", credentials.redirectUri);
  authUrl.searchParams.set("response_mode", "query");
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
  pendingLoopback = waitForLoopbackCallback(credentials.redirectUri, {
    timeoutMs: 180_000,
    successMessage: "Outlook bağlantısı tamamlandı. LawCopilot uygulamasına dönebilirsiniz.",
    errorMessage: "Outlook bağlantısı tamamlanamadı. LawCopilot uygulamasına dönüp tekrar deneyin.",
  });
  let callbackUrl = "";
  try {
    callbackUrl = await pendingLoopback;
  } finally {
    pendingLoopback = null;
  }
  const status = await exchangeOutlookCallback(config, callbackUrl);
  return {
    ...getOutlookAuthStatus(config),
    ...status,
    authStatus: "bagli",
    authUrl: authUrl.toString(),
    browserTarget,
    callbackCaptured: true,
    message: "Outlook hesabı bağlandı ve yönlendirme otomatik tamamlandı.",
  };
}

function cancelOutlookOAuth(config) {
  currentSession = null;
  if (pendingLoopback?.cancel) {
    try {
      pendingLoopback.cancel("Outlook OAuth akışı iptal edildi.");
    } catch {}
  }
  pendingLoopback = null;
  return {
    ...getOutlookAuthStatus(config),
    authStatus: "iptal",
    message: "Outlook oturum akışı iptal edildi.",
  };
}

module.exports = {
  cancelOutlookOAuth,
  describeOutlookCallbackError,
  getOutlookAuthStatus,
  startOutlookOAuth,
};
