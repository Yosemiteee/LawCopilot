const { waitForLoopbackCallback } = require("./oauth-loopback.cjs");

let currentSession = null;

const DEFAULT_INSTAGRAM_SCOPES = [
  "instagram_basic",
  "instagram_manage_messages",
  "pages_manage_metadata",
  "pages_show_list",
];

function graphVersion() {
  return String(process.env.LAWCOPILOT_INSTAGRAM_GRAPH_VERSION || "v22.0").trim();
}

function normalizeScopes(scopes) {
  const merged = [];
  for (const scope of [...DEFAULT_INSTAGRAM_SCOPES, ...(Array.isArray(scopes) ? scopes : [])]) {
    const value = String(scope || "").trim();
    if (!value || merged.includes(value)) {
      continue;
    }
    merged.push(value);
  }
  return merged;
}

function resolveCredentials(config) {
  const instagram = config?.instagram || {};
  return {
    clientId: String(instagram.clientId || process.env.LAWCOPILOT_INSTAGRAM_CLIENT_ID || "").trim(),
    clientSecret: String(instagram.clientSecret || process.env.LAWCOPILOT_INSTAGRAM_CLIENT_SECRET || "").trim(),
    redirectUri: String(
      instagram.redirectUri
      || process.env.LAWCOPILOT_INSTAGRAM_REDIRECT_URI
      || "http://127.0.0.1:1457/instagram/auth/callback",
    ).trim(),
    scopes: normalizeScopes(instagram.scopes),
  };
}

function getInstagramAuthStatus(config) {
  const instagram = config?.instagram || {};
  const credentials = resolveCredentials(config);
  const configured = Boolean(instagram.oauthConnected && instagram.pageAccessToken && instagram.pageId && instagram.instagramAccountId);
  return {
    provider: "instagram",
    authStatus: configured ? "bagli" : "hazir_degil",
    configured,
    accountLabel: String(instagram.accountLabel || "").trim(),
    username: String(instagram.username || "").trim(),
    pageId: String(instagram.pageId || "").trim(),
    pageName: String(instagram.pageName || "").trim(),
    instagramAccountId: String(instagram.instagramAccountId || "").trim(),
    pageNameHint: String(instagram.pageNameHint || "").trim(),
    scopes: normalizeScopes(instagram.scopes),
    clientReady: Boolean(credentials.clientId && credentials.clientSecret),
    redirectUri: credentials.redirectUri,
    authUrl: currentSession?.authUrl || "",
    message: configured
      ? "Instagram Professional hesabı bağlandı."
      : credentials.clientId && credentials.clientSecret
        ? "Instagram Professional hesabı henüz bağlanmadı."
        : "Instagram bağlantısı için Meta App istemci kimliği ve gizli anahtarı gerekli.",
    error: String(instagram.oauthLastError || "").trim(),
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
  return String(
    payload?.error?.message
    || payload?.error_description
    || payload?.message
    || payload?.raw
    || fallback,
  );
}

async function exchangeUserAccessToken(credentials, code) {
  const url = new URL(`https://graph.facebook.com/${graphVersion()}/oauth/access_token`);
  url.searchParams.set("client_id", credentials.clientId);
  url.searchParams.set("client_secret", credentials.clientSecret);
  url.searchParams.set("redirect_uri", credentials.redirectUri);
  url.searchParams.set("code", code);
  const response = await fetch(url.toString());
  const payload = await parseJson(response);
  if (!response.ok || !payload.access_token) {
    throw new Error(apiError(payload, "Instagram kullanıcı erişim anahtarı alınamadı."));
  }
  return payload;
}

async function exchangeLongLivedUserToken(credentials, accessToken) {
  const url = new URL(`https://graph.facebook.com/${graphVersion()}/oauth/access_token`);
  url.searchParams.set("grant_type", "fb_exchange_token");
  url.searchParams.set("client_id", credentials.clientId);
  url.searchParams.set("client_secret", credentials.clientSecret);
  url.searchParams.set("fb_exchange_token", accessToken);
  const response = await fetch(url.toString());
  const payload = await parseJson(response);
  if (!response.ok || !payload.access_token) {
    return null;
  }
  return payload;
}

async function fetchConnectedPages(accessToken) {
  const url = new URL(`https://graph.facebook.com/${graphVersion()}/me/accounts`);
  url.searchParams.set("fields", "id,name,access_token,connected_instagram_account{id,username,name}");
  url.searchParams.set("limit", "50");
  url.searchParams.set("access_token", accessToken);
  const response = await fetch(url.toString());
  const payload = await parseJson(response);
  if (!response.ok || !Array.isArray(payload?.data)) {
    throw new Error(apiError(payload, "Instagram için bağlı Meta sayfaları alınamadı."));
  }
  return payload.data;
}

function selectPage(config, pages) {
  const instagram = config?.instagram || {};
  const explicitPageId = String(instagram.pageId || "").trim();
  const pageNameHint = String(instagram.pageNameHint || "").trim().toLocaleLowerCase("tr-TR");
  const eligible = (Array.isArray(pages) ? pages : []).filter((item) => item?.connected_instagram_account?.id && item?.access_token);
  if (explicitPageId) {
    return eligible.find((item) => String(item.id || "").trim() === explicitPageId) || null;
  }
  if (pageNameHint) {
    return (
      eligible.find((item) => {
        const pageName = String(item?.name || "").trim().toLocaleLowerCase("tr-TR");
        const username = String(item?.connected_instagram_account?.username || "").trim().toLocaleLowerCase("tr-TR");
        const accountName = String(item?.connected_instagram_account?.name || "").trim().toLocaleLowerCase("tr-TR");
        return [pageName, username, accountName].some((value) => value && value.includes(pageNameHint));
      })
      || null
    );
  }
  return eligible[0] || null;
}

async function exchangeInstagramCallback(config, callbackUrl) {
  if (!currentSession) {
    throw new Error("Instagram OAuth oturumu başlatılmadı.");
  }
  const credentials = resolveCredentials(config);
  if (!credentials.clientId || !credentials.clientSecret) {
    throw new Error("Instagram OAuth için istemci kimliği ve gizli anahtar gerekli.");
  }
  const url = new URL(String(callbackUrl || "").trim());
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code) {
    throw new Error("Instagram yönlendirme adresinde kod bulunamadı.");
  }
  if (state !== currentSession.state) {
    throw new Error("Instagram OAuth state doğrulaması başarısız oldu.");
  }
  const shortLived = await exchangeUserAccessToken(credentials, code);
  const longLived = await exchangeLongLivedUserToken(credentials, String(shortLived.access_token || ""));
  const userAccessToken = String(longLived?.access_token || shortLived.access_token || "");
  const expiresIn = Number(longLived?.expires_in || shortLived.expires_in || 0);
  const pages = await fetchConnectedPages(userAccessToken);
  const selectedPage = selectPage(config, pages);
  if (!selectedPage) {
    throw new Error("Bu Meta hesabında bağlı Instagram Professional hesabı bulunamadı. Hesabın bir Facebook sayfasına bağlı olduğundan emin olun.");
  }
  currentSession = null;
  const instagramAccount = selectedPage.connected_instagram_account || {};
  return {
    configured: true,
    provider: "instagram",
    accountLabel: String(instagramAccount.username || instagramAccount.name || selectedPage.name || "Instagram hesabı").trim(),
    username: String(instagramAccount.username || "").trim(),
    pageId: String(selectedPage.id || "").trim(),
    pageName: String(selectedPage.name || "").trim(),
    instagramAccountId: String(instagramAccount.id || "").trim(),
    accessToken: userAccessToken,
    pageAccessToken: String(selectedPage.access_token || "").trim(),
    tokenType: String(shortLived.token_type || longLived?.token_type || "Bearer").trim(),
    expiryDate: expiresIn ? new Date(Date.now() + expiresIn * 1000).toISOString() : "",
    scopes: credentials.scopes,
    authStatus: "bagli",
    message: "Instagram Professional hesabı bağlandı.",
  };
}

async function startInstagramOAuth(config, openUrl) {
  const credentials = resolveCredentials(config);
  if (!credentials.clientId || !credentials.clientSecret) {
    throw new Error("Instagram bağlantısı için Meta App istemci kimliği ve gizli anahtarı gerekli.");
  }
  const state = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const authUrl = new URL(`https://www.facebook.com/${graphVersion()}/dialog/oauth`);
  authUrl.searchParams.set("client_id", credentials.clientId);
  authUrl.searchParams.set("redirect_uri", credentials.redirectUri);
  authUrl.searchParams.set("scope", credentials.scopes.join(","));
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("state", state);
  currentSession = {
    state,
    authUrl: authUrl.toString(),
    createdAt: Date.now(),
  };
  const browserTarget = await openUrl(authUrl.toString());
  const callbackUrl = await waitForLoopbackCallback(credentials.redirectUri, {
    timeoutMs: 180_000,
    successMessage: "Instagram bağlantısı tamamlandı. LawCopilot uygulamasına dönebilirsiniz.",
    errorMessage: "Instagram bağlantısı tamamlanamadı. LawCopilot uygulamasına dönüp tekrar deneyin.",
  });
  const status = await exchangeInstagramCallback(config, callbackUrl);
  return {
    ...getInstagramAuthStatus(config),
    ...status,
    authStatus: "bagli",
    authUrl: authUrl.toString(),
    browserTarget,
    callbackCaptured: true,
    message: "Instagram Professional hesabı bağlandı ve yönlendirme otomatik tamamlandı.",
  };
}

function cancelInstagramOAuth(config) {
  currentSession = null;
  return {
    ...getInstagramAuthStatus(config),
    authStatus: "iptal",
    message: "Instagram oturum akışı iptal edildi.",
  };
}

module.exports = {
  cancelInstagramOAuth,
  getInstagramAuthStatus,
  startInstagramOAuth,
};
