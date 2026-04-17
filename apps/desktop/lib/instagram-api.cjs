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
  return String(payload?.error?.message || payload?.message || payload?.detail || payload?.raw || fallback);
}

function graphVersion() {
  return String(process.env.LAWCOPILOT_INSTAGRAM_GRAPH_VERSION || "v22.0").trim();
}

function resolveInstagramConfig(config) {
  const instagram = config?.instagram || {};
  if (!instagram.oauthConnected || !instagram.pageAccessToken || !instagram.pageId || !instagram.instagramAccountId) {
    throw new Error("Instagram Professional hesabı bağlı değil.");
  }
  return {
    pageAccessToken: String(instagram.pageAccessToken || "").trim(),
    pageId: String(instagram.pageId || "").trim(),
    instagramAccountId: String(instagram.instagramAccountId || "").trim(),
    accountLabel: String(instagram.accountLabel || instagram.username || "Instagram hesabı").trim(),
  };
}

function graphUrl(pathname, accessToken, query = {}) {
  const url = new URL(`https://graph.facebook.com/${graphVersion()}${pathname}`);
  url.searchParams.set("access_token", accessToken);
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function fetchConversations(instagram) {
  const response = await fetch(
    graphUrl(`/${instagram.pageId}/conversations`, instagram.pageAccessToken, {
      platform: "instagram",
      fields: "id,updated_time",
      limit: "25",
    }),
  );
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(apiError(payload, "Instagram konuşmaları alınamadı."));
  }
  return Array.isArray(payload.data) ? payload.data : [];
}

async function fetchConversationMessages(instagram, conversationId) {
  const response = await fetch(
    graphUrl(`/${conversationId}/messages`, instagram.pageAccessToken, {
      fields: "id,created_time,from,to,message",
      limit: "25",
    }),
  );
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(apiError(payload, "Instagram mesajları alınamadı."));
  }
  return Array.isArray(payload.data) ? payload.data : [];
}

function participantLabel(raw) {
  const value = raw && typeof raw === "object" ? raw : {};
  return String(value.username || value.name || value.id || "").trim();
}

function normalizeConversationMessages(instagram, conversation, messages) {
  const normalized = [];
  const ownIds = new Set([instagram.pageId, instagram.instagramAccountId].filter(Boolean));
  for (const item of Array.isArray(messages) ? messages : []) {
    const from = item?.from && typeof item.from === "object" ? item.from : {};
    const toData = Array.isArray(item?.to?.data) ? item.to.data : [];
    const fromId = String(from.id || "").trim();
    const isOutbound = ownIds.has(fromId);
    const participant = isOutbound
      ? (toData.find((entry) => !ownIds.has(String(entry?.id || "").trim())) || toData[0] || {})
      : from;
    const participantId = String(participant?.id || "").trim();
    normalized.push({
      provider: "instagram",
      conversation_ref: String(conversation?.id || "").trim(),
      message_ref: String(item?.id || "").trim(),
      sender: participantLabel(from) || (isOutbound ? instagram.accountLabel : "Instagram kullanıcısı"),
      recipient: isOutbound ? participantLabel(participant) || "Instagram alıcısı" : instagram.accountLabel,
      body: String(item?.message || "").trim() || "Metin dışı Instagram mesajı",
      direction: isOutbound ? "outbound" : "inbound",
      sent_at: String(item?.created_time || new Date().toISOString()),
      reply_needed: !isOutbound,
      metadata: {
        conversation_id: String(conversation?.id || "").trim(),
        participant_id: participantId,
        participant_label: participantLabel(participant),
        from_id: fromId,
        to_ids: toData.map((entry) => String(entry?.id || "").trim()).filter(Boolean),
      },
    });
  }
  return normalized.filter((item) => item.message_ref);
}

async function syncInstagramData(config, runtimeInfo) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const instagram = resolveInstagramConfig(config);
  const conversations = await fetchConversations(instagram);
  const messagesByConversation = await Promise.all(
    conversations.map(async (conversation) => ({
      conversation,
      messages: await fetchConversationMessages(instagram, String(conversation?.id || "").trim()),
    })),
  );
  const messages = messagesByConversation.flatMap((item) =>
    normalizeConversationMessages(instagram, item.conversation, item.messages),
  );
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/instagram/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: instagram.accountLabel,
      page_id: instagram.pageId,
      instagram_account_id: instagram.instagramAccountId,
      messages,
      synced_at: new Date().toISOString(),
    }),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(apiError(payload, "Instagram verileri eşitlenemedi."));
  }
  return {
    ok: true,
    message: "Instagram mesajları eşitlendi.",
    synced: payload.synced || null,
    patch: {
      instagram: {
        lastSyncAt: new Date().toISOString(),
        lastValidatedAt: new Date().toISOString(),
        validationStatus: "valid",
      },
    },
  };
}

async function sendInstagramMessage(config, payload = {}) {
  const instagram = resolveInstagramConfig(config);
  const text = String(payload.text || payload.body || "").trim();
  if (!text) {
    throw new Error("Instagram mesajı için metin gerekli.");
  }
  const targetId = String(
    payload.participantId
    || payload.recipientId
    || payload.to
    || payload.recipient
    || "",
  ).trim();
  if (!targetId) {
    throw new Error("Instagram alıcısı çözümlenemedi.");
  }
  const response = await fetch(graphUrl(`/${instagram.pageId}/messages`, instagram.pageAccessToken), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      recipient: { id: targetId },
      messaging_type: "RESPONSE",
      message: { text },
    }),
  });
  const body = await parseJson(response);
  if (!response.ok) {
    throw new Error(apiError(body, "Instagram mesajı gönderilemedi."));
  }
  const externalMessageId = String(body?.message_id || body?.recipient_id || targetId).trim();
  return {
    ok: true,
    message: "Instagram mesajı gönderildi.",
    externalMessageId,
    patch: {
      instagram: {
        lastSyncAt: new Date().toISOString(),
        lastValidatedAt: new Date().toISOString(),
        validationStatus: "valid",
      },
    },
  };
}

module.exports = {
  sendInstagramMessage,
  syncInstagramData,
};
