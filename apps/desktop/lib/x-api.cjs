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
  return String(payload?.detail || payload?.title || payload?.error || payload?.message || fallback);
}

function resolveCredentials() {
  return {
    clientId: process.env.LAWCOPILOT_X_CLIENT_ID || "",
    clientSecret: process.env.LAWCOPILOT_X_CLIENT_SECRET || "",
  };
}

async function refreshAccessToken(config) {
  const credentials = resolveCredentials();
  const x = config?.x || {};
  if (!x.refreshToken || !credentials.clientId) {
    return { accessToken: String(x.accessToken || ""), patch: null };
  }
  const expiresAt = x.expiryDate ? Date.parse(String(x.expiryDate)) : 0;
  if (expiresAt && expiresAt > Date.now() + 60_000 && x.accessToken) {
    return { accessToken: String(x.accessToken), patch: null };
  }
  const body = new URLSearchParams({
    refresh_token: String(x.refreshToken),
    grant_type: "refresh_token",
    client_id: credentials.clientId,
  });
  const headers = {
    "Content-Type": "application/x-www-form-urlencoded",
  };
  if (credentials.clientSecret) {
    headers.Authorization = `Basic ${Buffer.from(`${credentials.clientId}:${credentials.clientSecret}`).toString("base64")}`;
  }
  const response = await fetch("https://api.x.com/2/oauth2/token", {
    method: "POST",
    headers,
    body,
  });
  const payload = await parseJson(response);
  if (!response.ok || !payload.access_token) {
    throw new Error(apiError(payload, "X erişim anahtarı yenilenemedi."));
  }
  return {
    accessToken: String(payload.access_token),
    patch: {
      x: {
        accessToken: String(payload.access_token),
        tokenType: String(payload.token_type || "bearer"),
        expiryDate: payload.expires_in ? new Date(Date.now() + Number(payload.expires_in) * 1000).toISOString() : "",
        lastValidatedAt: new Date().toISOString(),
        validationStatus: "valid",
      },
    },
  };
}

async function fetchMentions(accessToken, userId) {
  const params = new URLSearchParams({
    max_results: "10",
    "tweet.fields": "created_at,author_id,conversation_id,public_metrics",
  });
  const response = await fetch(`https://api.x.com/2/users/${encodeURIComponent(String(userId))}/mentions?${params.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(apiError(payload, "X mention kayıtları okunamadı."));
  }
  return Array.isArray(payload.data) ? payload.data : [];
}

async function fetchOwnPosts(accessToken, userId) {
  const params = new URLSearchParams({
    max_results: "10",
    "tweet.fields": "created_at,conversation_id,public_metrics",
  });
  const response = await fetch(`https://api.x.com/2/users/${encodeURIComponent(String(userId))}/tweets?${params.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(apiError(payload, "X gönderileri okunamadı."));
  }
  return Array.isArray(payload.data) ? payload.data : [];
}

async function syncXData(config, runtimeInfo) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const x = config?.x || {};
  if (!x.oauthConnected || !x.accessToken || !x.userId) {
    throw new Error("X hesabı bağlı değil.");
  }
  const refreshed = await refreshAccessToken(config);
  const accessToken = refreshed.accessToken;
  if (!accessToken) {
    throw new Error("X erişim anahtarı bulunamadı.");
  }
  const [mentions, ownPosts] = await Promise.all([
    fetchMentions(accessToken, x.userId),
    fetchOwnPosts(accessToken, x.userId),
  ]);
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/x/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: x.accountLabel || "X hesabı",
      user_id: x.userId,
      scopes: Array.isArray(x.scopes) ? x.scopes : [],
      mentions: mentions.map((item) => ({
        provider: "x",
        external_id: String(item.id || ""),
        post_type: "mention",
        author_handle: x.accountLabel || "x-user",
        content: String(item.text || ""),
        posted_at: String(item.created_at || new Date().toISOString()),
        reply_needed: true,
        metadata: item,
      })),
      posts: ownPosts.map((item) => ({
        provider: "x",
        external_id: String(item.id || ""),
        post_type: "post",
        author_handle: x.accountLabel || "x-user",
        content: String(item.text || ""),
        posted_at: String(item.created_at || new Date().toISOString()),
        reply_needed: false,
        metadata: item,
      })),
      synced_at: new Date().toISOString(),
    }),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(apiError(payload, "X verileri eşitlenemedi."));
  }
  return {
    ok: true,
    message: "X verileri eşitlendi.",
    synced: payload.synced || null,
    patch: {
      ...(refreshed.patch || {}),
      x: {
        ...((refreshed.patch || {}).x || {}),
        lastSyncAt: new Date().toISOString(),
      },
    },
  };
}

async function postXUpdate(config, payload = {}) {
  const x = config?.x || {};
  if (!x.oauthConnected || !x.accessToken) {
    throw new Error("X hesabı bağlı değil.");
  }
  const text = String(payload.text || payload.body || "").trim();
  if (!text) {
    throw new Error("X gönderisi için metin gerekli.");
  }
  const refreshed = await refreshAccessToken(config);
  const accessToken = refreshed.accessToken;
  const response = await fetch("https://api.x.com/2/tweets", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text }),
  });
  const body = await parseJson(response);
  if (!response.ok || !body?.data?.id) {
    throw new Error(apiError(body, "X gönderisi paylaşılamadı."));
  }
  return {
    ok: true,
    message: "X gönderisi paylaşıldı.",
    externalMessageId: String(body.data.id),
    patch: refreshed.patch,
  };
}

module.exports = {
  postXUpdate,
  syncXData,
};
