const {
  disconnectLinkedInWeb,
  getLinkedInWebStatus,
  sendLinkedInWebMessage,
  setLinkedInWebBridgeContext,
  startLinkedInWebLink,
  syncLinkedInWebData,
} = require("./linkedin-web-bridge.cjs");

function apiError(payload, fallback) {
  return String(payload?.message || payload?.error_description || payload?.serviceErrorCode || payload?.error || fallback);
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

function linkedinApiVersion() {
  return String(process.env.LAWCOPILOT_LINKEDIN_API_VERSION || "202603").trim();
}

function linkedInHeaders(accessToken) {
  return {
    Authorization: `Bearer ${accessToken}`,
    "Content-Type": "application/json",
    "X-Restli-Protocol-Version": "2.0.0",
    "Linkedin-Version": linkedinApiVersion(),
  };
}

function normalizeLinkedInCollection(payload) {
  if (Array.isArray(payload?.elements)) {
    return payload.elements;
  }
  if (Array.isArray(payload?.results)) {
    return payload.results;
  }
  if (Array.isArray(payload?.data)) {
    return payload.data;
  }
  return [];
}

function firstString(...values) {
  for (const value of values) {
    const text = String(value || "").trim();
    if (text) {
      return text;
    }
  }
  return "";
}

function extractLinkedInText(value) {
  if (typeof value === "string") {
    return value.trim();
  }
  if (!value || typeof value !== "object") {
    return "";
  }
  return firstString(
    value.text,
    value.string,
    value.value,
    value.commentary,
    value.message?.text,
    value.message?.string,
    value.message?.value,
    value.commentary?.text,
    value.commentary?.string,
    value.commentary?.value,
    value.text?.text,
    value.text?.string,
    value.text?.value,
    value.content?.text,
    value.content?.string,
    value.content?.value,
  );
}

function linkedInEntityUrn(item) {
  return firstString(item?.id, item?.entityUrn, item?.urn, item?.activity);
}

function linkedInActorLabel(item, fallback = "LinkedIn") {
  return firstString(
    item?.actor,
    item?.author,
    item?.authorName,
    item?.owner,
    item?.ownerName,
    item?.creator,
    fallback,
  );
}

function resolveLinkedInMode(configOrInput) {
  const linkedin = configOrInput?.linkedin && typeof configOrInput.linkedin === "object"
    ? configOrInput.linkedin
    : configOrInput && typeof configOrInput === "object"
      ? configOrInput
      : {};
  const mode = String(linkedin.mode || "").trim().toLowerCase();
  if (mode === "official" || mode === "web") {
    return mode;
  }
  if (linkedin.oauthConnected || linkedin.accessToken) {
    return "official";
  }
  return "web";
}

async function fetchLinkedInPosts(config) {
  const linkedin = config?.linkedin || {};
  const personUrn = String(linkedin.personUrn || (linkedin.userId ? `urn:li:person:${linkedin.userId}` : "")).trim();
  if (!linkedin.oauthConnected || !linkedin.accessToken || !personUrn) {
    throw new Error("LinkedIn hesabı bağlı değil.");
  }
  const candidates = [
    `https://api.linkedin.com/rest/posts?q=author&author=${encodeURIComponent(personUrn)}&count=20&sortBy=LAST_MODIFIED`,
    `https://api.linkedin.com/rest/posts?q=authors&authors=List(${encodeURIComponent(personUrn)})&count=20&sortBy=LAST_MODIFIED`,
  ];
  let lastError = null;
  for (const url of candidates) {
    const response = await fetch(url, {
      headers: linkedInHeaders(String(linkedin.accessToken)),
    });
    const payload = await parseJson(response);
    if (response.ok) {
      return normalizeLinkedInCollection(payload);
    }
    lastError = new Error(apiError(payload, "LinkedIn gönderileri okunamadı."));
  }
  throw lastError || new Error("LinkedIn gönderileri okunamadı.");
}

async function fetchLinkedInComments(config, objectUrn) {
  const linkedin = config?.linkedin || {};
  const targetUrn = String(objectUrn || "").trim();
  if (!linkedin.oauthConnected || !linkedin.accessToken || !targetUrn) {
    return [];
  }
  const response = await fetch(
    `https://api.linkedin.com/rest/socialActions/${encodeURIComponent(targetUrn)}/comments?count=20&sortOrder=DESCENDING`,
    {
      headers: linkedInHeaders(String(linkedin.accessToken)),
    },
  );
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(apiError(payload, "LinkedIn yorumları okunamadı."));
  }
  return normalizeLinkedInCollection(payload);
}

function normalizeLinkedInPosts(config, posts) {
  const linkedin = config?.linkedin || {};
  const accountLabel = String(linkedin.accountLabel || "LinkedIn hesabı").trim() || "LinkedIn hesabı";
  return (Array.isArray(posts) ? posts : [])
    .map((item) => {
      const externalId = linkedInEntityUrn(item);
      if (!externalId) {
        return null;
      }
      return {
        provider: "linkedin",
        external_id: externalId,
        author_handle: accountLabel,
        content: firstString(
          extractLinkedInText(item?.commentary),
          extractLinkedInText(item?.text),
          extractLinkedInText(item?.content),
          extractLinkedInText(item?.message),
        ),
        posted_at: firstString(item?.lastModifiedAt, item?.createdAt, item?.publishedAt, new Date().toISOString()),
        reply_needed: false,
        metadata: {
          ...item,
          object_urn: externalId,
        },
      };
    })
    .filter(Boolean);
}

function normalizeLinkedInComments(post, comments) {
  const objectUrn = linkedInEntityUrn(post);
  return (Array.isArray(comments) ? comments : [])
    .map((item) => {
      const externalId = linkedInEntityUrn(item);
      if (!externalId) {
        return null;
      }
      return {
        provider: "linkedin",
        external_id: externalId,
        object_urn: objectUrn,
        parent_external_id: firstString(item?.parentComment, item?.parent),
        author_handle: linkedInActorLabel(item),
        content: firstString(
          extractLinkedInText(item?.message),
          extractLinkedInText(item?.commentary),
          extractLinkedInText(item?.text),
          "LinkedIn yorumu",
        ),
        posted_at: firstString(item?.lastModifiedAt, item?.createdAt, item?.publishedAt, new Date().toISOString()),
        reply_needed: true,
        metadata: {
          ...item,
          object_urn: objectUrn,
          comment_urn: externalId,
        },
      };
    })
    .filter(Boolean);
}

async function syncLinkedInData(config, runtimeInfo) {
  if (resolveLinkedInMode(config) === "web") {
    return syncLinkedInWebData(config, runtimeInfo);
  }
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const linkedin = config?.linkedin || {};
  if (!linkedin.oauthConnected || !linkedin.accessToken) {
    throw new Error("LinkedIn hesabı bağlı değil.");
  }
  const posts = await fetchLinkedInPosts(config);
  const commentsByPost = await Promise.all(
    posts.map(async (post) => ({
      post,
      comments: await fetchLinkedInComments(config, linkedInEntityUrn(post)).catch(() => []),
    })),
  );
  const normalizedPosts = normalizeLinkedInPosts(config, posts);
  const normalizedComments = commentsByPost.flatMap((item) => normalizeLinkedInComments(item.post, item.comments));
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/linkedin/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: linkedin.accountLabel || "LinkedIn hesabı",
      user_id: linkedin.userId || "",
      person_urn: linkedin.personUrn || "",
      scopes: Array.isArray(linkedin.scopes) ? linkedin.scopes : [],
      posts: normalizedPosts,
      comments: normalizedComments,
      synced_at: new Date().toISOString(),
    }),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(apiError(payload, "LinkedIn verileri eşitlenemedi."));
  }
  return {
    ok: true,
    message: "LinkedIn verileri eşitlendi.",
    synced: payload.synced || null,
    patch: {
      linkedin: {
        lastSyncAt: new Date().toISOString(),
        lastValidatedAt: new Date().toISOString(),
        validationStatus: "valid",
      },
    },
  };
}

async function postLinkedInUpdate(config, payload = {}) {
  if (resolveLinkedInMode(config) === "web") {
    throw new Error("LinkedIn Web modunda gönderi paylaşımı yerine mevcut konuşmalara mesaj yanıtı desteklenir.");
  }
  const linkedin = config?.linkedin || {};
  if (!linkedin.oauthConnected || !linkedin.accessToken) {
    throw new Error("LinkedIn hesabı bağlı değil.");
  }
  const text = String(payload.text || payload.body || "").trim();
  if (!text) {
    throw new Error("LinkedIn gönderisi için metin gerekli.");
  }
  const author = String(linkedin.personUrn || (linkedin.userId ? `urn:li:person:${linkedin.userId}` : "")).trim();
  if (!author) {
    throw new Error("LinkedIn kullanıcı kimliği çözümlenemedi. Hesabı yeniden bağlayın.");
  }
  const response = await fetch("https://api.linkedin.com/rest/posts", {
    method: "POST",
    headers: linkedInHeaders(String(linkedin.accessToken)),
    body: JSON.stringify({
      author,
      commentary: text,
      visibility: "PUBLIC",
      distribution: {
        feedDistribution: "MAIN_FEED",
        targetEntities: [],
        thirdPartyDistributionChannels: [],
      },
      lifecycleState: "PUBLISHED",
      isReshareDisabledByAuthor: false,
    }),
  });
  const body = await parseJson(response);
  const externalMessageId = String(
    response.headers.get("x-restli-id")
    || body?.id
    || body?.entityUrn
    || "",
  ).trim();
  if (!response.ok || !externalMessageId) {
    throw new Error(apiError(body, "LinkedIn gönderisi paylaşılamadı."));
  }
  return {
    ok: true,
    message: "LinkedIn gönderisi paylaşıldı.",
    externalMessageId,
    patch: {
      linkedin: {
        lastSyncAt: new Date().toISOString(),
        lastValidatedAt: new Date().toISOString(),
        validationStatus: "valid",
      },
    },
  };
}

function getLinkedInStatus(config) {
  if (resolveLinkedInMode(config) === "web") {
    return getLinkedInWebStatus(config);
  }
  const linkedin = config?.linkedin || {};
  const configured = Boolean(linkedin.enabled && linkedin.oauthConnected && linkedin.accessToken);
  return {
    provider: "linkedin",
    mode: "official",
    configured,
    accountLabel: String(linkedin.accountLabel || "LinkedIn hesabı"),
    userId: String(linkedin.userId || ""),
    personUrn: String(linkedin.personUrn || ""),
    scopes: Array.isArray(linkedin.scopes) ? linkedin.scopes : [],
    validationStatus: String(linkedin.validationStatus || "pending"),
    lastSyncAt: String(linkedin.lastSyncAt || ""),
    message: configured
      ? "LinkedIn gönderi ve yorum erişimi bağlı."
      : "LinkedIn resmi erişimi için istemci kimliği, gizli anahtar ve OAuth bağlantısı gerekli.",
  };
}

module.exports = {
  disconnectLinkedInWeb,
  getLinkedInStatus,
  sendLinkedInWebMessage,
  setLinkedInWebBridgeContext,
  startLinkedInWebLink,
  postLinkedInUpdate,
  syncLinkedInData,
};
