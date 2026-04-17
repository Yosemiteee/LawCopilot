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

function hasScope(scopes, scope) {
  return Array.isArray(scopes) && scopes.map((item) => String(item || "").trim()).includes(scope);
}

function hasDirectMessageReadScope(scopes) {
  return hasScope(scopes, "dm.read");
}

function hasDirectMessageWriteScope(scopes) {
  return hasScope(scopes, "dm.write");
}

function resolveCredentials(config) {
  const x = config?.x || {};
  return {
    clientId: String(x.clientId || process.env.LAWCOPILOT_X_CLIENT_ID || "").trim(),
    clientSecret: String(x.clientSecret || process.env.LAWCOPILOT_X_CLIENT_SECRET || "").trim(),
  };
}

async function refreshAccessToken(config) {
  const credentials = resolveCredentials(config);
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

function xUserLabel(value) {
  const username = String(value?.username || "").trim();
  if (username) {
    return `@${username}`;
  }
  const name = String(value?.name || "").trim();
  if (name) {
    return name;
  }
  return String(value?.id || "").trim();
}

async function fetchDirectMessages(accessToken) {
  const params = new URLSearchParams({
    max_results: "50",
    "dm_event.fields": "created_at,dm_conversation_id,sender_id,participant_ids,text",
    expansions: "sender_id,participant_ids",
    "user.fields": "id,name,username",
  });
  const response = await fetch(`https://api.x.com/2/dm_events?${params.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(apiError(payload, "X direkt mesaj kayıtları okunamadı."));
  }
  return {
    events: Array.isArray(payload.data) ? payload.data : [],
    users: Array.isArray(payload?.includes?.users) ? payload.includes.users : [],
  };
}

async function lookupUserByUsername(accessToken, username) {
  const normalized = String(username || "").trim().replace(/^@+/, "");
  if (!normalized) {
    throw new Error("X kullanıcı adı boş olamaz.");
  }
  const response = await fetch(`https://api.x.com/2/users/by/username/${encodeURIComponent(normalized)}?user.fields=id,name,username`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const payload = await parseJson(response);
  if (!response.ok || !payload?.data?.id) {
    throw new Error(apiError(payload, "X kullanıcı bilgisi alınamadı."));
  }
  return payload.data;
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
  const supportsDirectMessages = hasDirectMessageReadScope(x.scopes);
  const [mentions, ownPosts, directMessages] = await Promise.all([
    fetchMentions(accessToken, x.userId),
    fetchOwnPosts(accessToken, x.userId),
    supportsDirectMessages ? fetchDirectMessages(accessToken) : Promise.resolve({ events: [], users: [] }),
  ]);
  const dmUsers = new Map(
    (directMessages.users || [])
      .filter((item) => item && typeof item === "object" && item.id)
      .map((item) => [String(item.id), item]),
  );
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
      messages: (directMessages.events || [])
        .filter((item) => String(item?.event_type || "").trim() === "MessageCreate")
        .map((item) => {
          const senderId = String(item?.sender_id || "").trim();
          const participantIds = Array.isArray(item?.participant_ids)
            ? item.participant_ids.map((value) => String(value || "").trim()).filter(Boolean)
            : [];
          const otherParticipantIds = participantIds.filter((value) => value && value !== String(x.userId || ""));
          const sender = xUserLabel(dmUsers.get(senderId) || { id: senderId });
          const recipient = otherParticipantIds.map((value) => xUserLabel(dmUsers.get(value) || { id: value })).filter(Boolean).join(", ");
          const text = String(item?.text || "").trim();
          return {
            provider: "x",
            conversation_ref: String(item?.dm_conversation_id || otherParticipantIds.join("-") || senderId || "x-dm"),
            message_ref: String(item?.id || ""),
            sender,
            recipient: recipient || (senderId === String(x.userId || "") ? "X DM alıcısı" : x.accountLabel || "X hesabı"),
            body: text || "Ekli medya veya boş DM olayı",
            direction: senderId === String(x.userId || "") ? "outbound" : "inbound",
            sent_at: String(item?.created_at || new Date().toISOString()),
            reply_needed: senderId !== String(x.userId || ""),
            metadata: {
              ...item,
              sender_id: senderId,
              participant_ids: participantIds,
            },
          };
        })
        .filter((item) => item.message_ref && item.body),
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

async function sendXDirectMessage(config, payload = {}) {
  const x = config?.x || {};
  if (!x.oauthConnected || !x.accessToken) {
    throw new Error("X hesabı bağlı değil.");
  }
  if (!hasDirectMessageWriteScope(x.scopes)) {
    throw new Error("X DM gönderimi için dm.write izni gerekli. Hesabı yeniden bağlayın.");
  }
  const text = String(payload.text || payload.body || "").trim();
  if (!text) {
    throw new Error("X DM gönderimi için mesaj metni gerekli.");
  }
  const refreshed = await refreshAccessToken(config);
  const accessToken = refreshed.accessToken;
  let participantId = String(payload.participantId || payload.toUserId || payload.recipientId || "").trim();
  if (!participantId) {
    const toHandle = String(payload.to || payload.username || payload.handle || "").trim();
    if (!toHandle) {
      throw new Error("X DM gönderimi için kullanıcı kimliği veya kullanıcı adı gerekli.");
    }
    const user = await lookupUserByUsername(accessToken, toHandle);
    participantId = String(user.id || "").trim();
  }
  if (!participantId) {
    throw new Error("X DM alıcısı çözümlenemedi.");
  }
  const response = await fetch(`https://api.x.com/2/dm_conversations/with/${encodeURIComponent(participantId)}/messages`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text }),
  });
  const body = await parseJson(response);
  if (!response.ok || !body?.data?.dm_event_id) {
    throw new Error(apiError(body, "X direkt mesajı gönderilemedi."));
  }
  return {
    ok: true,
    message: "X direkt mesajı gönderildi.",
    externalMessageId: String(body.data.dm_event_id),
    conversationId: String(body?.data?.dm_conversation_id || ""),
    recipientId: participantId,
    patch: refreshed.patch,
  };
}

module.exports = {
  hasDirectMessageReadScope,
  hasDirectMessageWriteScope,
  postXUpdate,
  sendXDirectMessage,
  syncXData,
};
