const fs = require("fs");
const path = require("path");
const AdmZip = require("adm-zip");

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

const GOOGLE_PORTABILITY_API_BASE = "https://dataportability.googleapis.com/v1";
const GOOGLE_PORTABILITY_RESOURCE_BY_SCOPE = {
  "https://www.googleapis.com/auth/dataportability.myactivity.youtube": "myactivity.youtube",
  "https://www.googleapis.com/auth/dataportability.chrome.history": "chrome.history",
};

function base64UrlEncode(value) {
  return Buffer.from(String(value || ""), "utf-8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function encodeMimeHeaderValue(value) {
  const normalized = normalizeMailHeaderValue(String(value || "")).replace(/\r?\n/g, " ").trim();
  if (!normalized) {
    return "";
  }
  if (/^[\x20-\x7E]*$/.test(normalized)) {
    return normalized;
  }
  const encoded = Buffer.from(normalized, "utf-8").toString("base64");
  return `=?UTF-8?B?${encoded}?=`;
}

function encodeQuotedPrintableBody(value) {
  const normalized = repairUtf8Mojibake(String(value || "")).replace(/\r?\n/g, "\n");
  const bytes = Buffer.from(normalized, "utf8");
  let currentLine = "";
  const lines = [];

  function pushSoftBreakIfNeeded(fragmentLength) {
    if (currentLine.length + fragmentLength <= 73) {
      return;
    }
    lines.push(`${currentLine}=`);
    currentLine = "";
  }

  for (let index = 0; index < bytes.length; index += 1) {
    const byte = bytes[index];
    if (byte === 0x0a) {
      lines.push(currentLine);
      currentLine = "";
      continue;
    }
    const isPrintableAscii =
      (byte >= 33 && byte <= 60) ||
      (byte >= 62 && byte <= 126);
    const nextIsNewline = index + 1 >= bytes.length || bytes[index + 1] === 0x0a;
    const needsEncoding =
      !isPrintableAscii &&
      byte !== 0x09 &&
      byte !== 0x20;
    const trailingWhitespace = (byte === 0x09 || byte === 0x20) && nextIsNewline;
    const fragment = needsEncoding || trailingWhitespace
      ? `=${byte.toString(16).toUpperCase().padStart(2, "0")}`
      : String.fromCharCode(byte);
    pushSoftBreakIfNeeded(fragment.length);
    currentLine += fragment;
  }

  lines.push(currentLine);
  return lines.join("\r\n");
}

function googleError(payload, fallback) {
  return String(payload?.error_description || payload?.error?.message || payload?.error || fallback);
}

const GOOGLE_CALENDAR_WRITE_SCOPES = [
  "https://www.googleapis.com/auth/calendar.events",
  "https://www.googleapis.com/auth/calendar",
];
const GOOGLE_YOUTUBE_READ_SCOPE = "https://www.googleapis.com/auth/youtube.readonly";

function hasGoogleScope(scopes, target) {
  return Array.isArray(scopes) && scopes.some((scope) => String(scope || "").trim() === target);
}

function resolveCredentials(config) {
  const google = config?.google || {};
  return {
    clientId: String(google.clientId || process.env.LAWCOPILOT_GOOGLE_CLIENT_ID || "").trim(),
    clientSecret: String(google.clientSecret || process.env.LAWCOPILOT_GOOGLE_CLIENT_SECRET || "").trim(),
  };
}

function resolvePortabilityCredentials(config) {
  const portability = config?.googlePortability || {};
  const google = config?.google || {};
  return {
    clientId: String(
      portability.clientId || google.clientId || process.env.LAWCOPILOT_GOOGLE_PORTABILITY_CLIENT_ID || process.env.LAWCOPILOT_GOOGLE_CLIENT_ID || "",
    ).trim(),
    clientSecret: String(
      portability.clientSecret
        || google.clientSecret
        || process.env.LAWCOPILOT_GOOGLE_PORTABILITY_CLIENT_SECRET
        || process.env.LAWCOPILOT_GOOGLE_CLIENT_SECRET
        || "",
    ).trim(),
  };
}

async function refreshAccessToken(config) {
  const credentials = resolveCredentials(config);
  const google = config?.google || {};
  if (!google.refreshToken || !credentials.clientId || !credentials.clientSecret) {
    return { accessToken: String(google.accessToken || ""), patch: null };
  }
  const expiresAt = google.expiryDate ? Date.parse(String(google.expiryDate)) : 0;
  if (expiresAt && expiresAt > Date.now() + 60_000 && google.accessToken) {
    return { accessToken: String(google.accessToken), patch: null };
  }
  const body = new URLSearchParams({
    client_id: credentials.clientId,
    client_secret: credentials.clientSecret,
    refresh_token: String(google.refreshToken),
    grant_type: "refresh_token",
  });
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const payload = await parseJson(response);
  if (!response.ok || !payload.access_token) {
    throw new Error(googleError(payload, "Google erişim anahtarı yenilenemedi."));
  }
  return {
    accessToken: String(payload.access_token),
    patch: {
      google: {
        accessToken: String(payload.access_token),
        tokenType: String(payload.token_type || "Bearer"),
        expiryDate: payload.expires_in ? new Date(Date.now() + Number(payload.expires_in) * 1000).toISOString() : "",
        lastValidatedAt: new Date().toISOString(),
        validationStatus: "valid",
      },
    },
  };
}

async function refreshPortabilityAccessToken(config) {
  const credentials = resolvePortabilityCredentials(config);
  const portability = config?.googlePortability || {};
  if (!portability.refreshToken || !credentials.clientId || !credentials.clientSecret) {
    return { accessToken: String(portability.accessToken || ""), patch: null };
  }
  const expiresAt = portability.expiryDate ? Date.parse(String(portability.expiryDate)) : 0;
  if (expiresAt && expiresAt > Date.now() + 60_000 && portability.accessToken) {
    return { accessToken: String(portability.accessToken), patch: null };
  }
  const body = new URLSearchParams({
    client_id: credentials.clientId,
    client_secret: credentials.clientSecret,
    refresh_token: String(portability.refreshToken),
    grant_type: "refresh_token",
  });
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const payload = await parseJson(response);
  if (!response.ok || !payload.access_token) {
    throw new Error(googleError(payload, "Google geçmiş aktarımı erişim anahtarı yenilenemedi."));
  }
  return {
    accessToken: String(payload.access_token),
    patch: {
      googlePortability: {
        accessToken: String(payload.access_token),
        tokenType: String(payload.token_type || "Bearer"),
        expiryDate: payload.expires_in ? new Date(Date.now() + Number(payload.expires_in) * 1000).toISOString() : "",
        lastValidatedAt: new Date().toISOString(),
        validationStatus: "valid",
      },
    },
  };
}

function headerLookup(headers, name) {
  const match = (headers || []).find((item) => String(item?.name || "").toLowerCase() === name.toLowerCase());
  return String(match?.value || "");
}

const GMAIL_SYNC_MESSAGE_LIMIT = 25;
const GMAIL_METADATA_BATCH_SIZE = 5;
const MIME_ENCODED_WORD_PATTERN = /=\?([^?]+)\?([bqBQ])\?([^?]*)\?=/g;

function decodeBufferWithCharset(buffer, charset) {
  const normalizedCharset = String(charset || "").trim().toLowerCase() || "utf-8";
  const aliases = {
    utf8: "utf-8",
    "utf-8": "utf-8",
    usascii: "utf-8",
    "us-ascii": "utf-8",
    latin1: "latin1",
    "iso-8859-1": "latin1",
    iso88591: "latin1",
    windows1252: "latin1",
    "windows-1252": "latin1",
    cp1252: "latin1",
  };
  const resolvedCharset = aliases[normalizedCharset] || aliases[normalizedCharset.replace(/[^a-z0-9]/g, "")] || "utf-8";
  try {
    return new TextDecoder(resolvedCharset, { fatal: false }).decode(buffer);
  } catch {
    return buffer.toString("utf8");
  }
}

function looksLikeUtf8Mojibake(value) {
  return /[ÃÂÄÅÐÑØÞ]/.test(String(value || ""));
}

function mojibakeScore(value) {
  const text = String(value || "");
  return (text.match(/[ÃÂÄÅÐÑØÞ]/g) || []).length + ((text.match(/\uFFFD/g) || []).length * 3);
}

function repairUtf8Mojibake(value) {
  let current = String(value || "");
  for (let attempt = 0; attempt < 2; attempt += 1) {
    if (!looksLikeUtf8Mojibake(current)) {
      break;
    }
    const candidates = [];
    try {
      candidates.push(Buffer.from(current, "latin1").toString("utf8"));
    } catch {}
    const repaired = candidates
      .map((item) => String(item || ""))
      .filter(Boolean)
      .sort((left, right) => mojibakeScore(left) - mojibakeScore(right))[0];
    if (!repaired || repaired === current || mojibakeScore(repaired) > mojibakeScore(current)) {
      break;
    }
    current = repaired;
  }
  return current;
}

function decodeQuotedPrintableWord(value) {
  const normalized = String(value || "").replace(/_/g, " ");
  const bytes = [];
  for (let index = 0; index < normalized.length; index += 1) {
    const current = normalized[index];
    const hex = normalized.slice(index + 1, index + 3);
    if (current === "=" && /^[0-9a-fA-F]{2}$/.test(hex)) {
      bytes.push(Number.parseInt(hex, 16));
      index += 2;
      continue;
    }
    bytes.push(normalized.charCodeAt(index));
  }
  return Buffer.from(bytes);
}

function decodeMimeEncodedWord(_full, charset, encoding, value) {
  let buffer;
  try {
    buffer = String(encoding || "").trim().toLowerCase() === "b"
      ? Buffer.from(String(value || ""), "base64")
      : decodeQuotedPrintableWord(value);
  } catch {
    return String(value || "");
  }
  return decodeBufferWithCharset(buffer, charset);
}

function normalizeMailHeaderValue(value) {
  const raw = String(value || "");
  const decoded = raw.includes("=?")
    ? raw.replace(MIME_ENCODED_WORD_PATTERN, decodeMimeEncodedWord)
    : raw;
  return repairUtf8Mojibake(decoded).replace(/\s+/g, " ").trim();
}

const LOW_SIGNAL_GMAIL_LABELS = new Set([
  "CATEGORY_FORUMS",
  "CATEGORY_PROMOTIONS",
  "CATEGORY_SOCIAL",
  "CATEGORY_UPDATES",
]);

const LOW_SIGNAL_EMAIL_SENDER_TOKENS = [
  "no-reply",
  "noreply",
  "do-not-reply",
  "donotreply",
  "mailer-daemon",
  "postmaster",
  "newsletter",
  "notifications",
  "notification",
  "updates",
];

const LOW_SIGNAL_EMAIL_TEXT_TOKENS = [
  "unsubscribe",
  "list-unsubscribe",
  "newsletter",
  "bülten",
  "bulten",
  "kampanya",
  "indirim",
  "fırsat",
  "firsat",
  "promosyon",
  "promotion",
  "promo",
  "special offer",
  "özel teklif",
  "ozel teklif",
  "limited time",
  "flash sale",
  "daha iyi fiyat",
  "best price",
  "coupon",
  "kupon",
  "webinar",
  "daily digest",
  "weekly digest",
  "haftalık özet",
  "haftalik ozet",
  "duyuru",
  "bilgilendirme",
];

function buildEmailHaystack(...values) {
  return values
    .flat()
    .map((value) => String(value || "").trim().toLowerCase())
    .filter(Boolean)
    .join(" ");
}

function isLowSignalGmailMessage({ labels, subject, sender, snippet, listUnsubscribe, precedence, autoSubmitted }) {
  const normalizedLabels = new Set((Array.isArray(labels) ? labels : []).map((value) => String(value || "").trim().toUpperCase()));
  const haystack = buildEmailHaystack(subject, sender, snippet, listUnsubscribe, precedence, autoSubmitted);
  let score = 0;
  for (const label of normalizedLabels) {
    if (LOW_SIGNAL_GMAIL_LABELS.has(label)) {
      score += 2;
      break;
    }
  }
  if (LOW_SIGNAL_EMAIL_SENDER_TOKENS.some((token) => haystack.includes(token))) {
    score += 1;
  }
  if (LOW_SIGNAL_EMAIL_TEXT_TOKENS.some((token) => haystack.includes(token))) {
    score += 1;
  }
  if (listUnsubscribe || ["bulk", "list", "junk"].includes(String(precedence || "").trim().toLowerCase()) || autoSubmitted) {
    score += 1;
  }
  return score >= 2;
}

async function fetchGmailThreads(accessToken) {
  const listResponse = await fetch(`https://gmail.googleapis.com/gmail/v1/users/me/messages?labelIds=INBOX&maxResults=${GMAIL_SYNC_MESSAGE_LIMIT}&q=newer_than:30d`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const listPayload = await parseJson(listResponse);
  if (!listResponse.ok) {
    throw new Error(googleError(listPayload, "Gmail gelen kutusu okunamadı."));
  }
  const messages = Array.isArray(listPayload.messages) ? listPayload.messages : [];
  const threads = [];
  for (let index = 0; index < messages.length; index += GMAIL_METADATA_BATCH_SIZE) {
    const batch = messages.slice(index, index + GMAIL_METADATA_BATCH_SIZE);
    const results = await Promise.all(
      batch.map(async (message) => {
        const response = await fetch(
          `https://gmail.googleapis.com/gmail/v1/users/me/messages/${encodeURIComponent(String(message.id))}?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date&metadataHeaders=List-Unsubscribe&metadataHeaders=Precedence&metadataHeaders=Auto-Submitted`,
          {
            headers: { Authorization: `Bearer ${accessToken}` },
          },
        );
        const payload = await parseJson(response);
        if (!response.ok) {
          return null;
        }
        const headers = payload.payload?.headers || [];
        const dateValue = headerLookup(headers, "Date");
        const subject = normalizeMailHeaderValue(headerLookup(headers, "Subject")) || "Konu yok";
        const sender = normalizeMailHeaderValue(headerLookup(headers, "From"));
        const snippet = repairUtf8Mojibake(String(payload.snippet || ""));
        const listUnsubscribe = normalizeMailHeaderValue(headerLookup(headers, "List-Unsubscribe"));
        const precedence = normalizeMailHeaderValue(headerLookup(headers, "Precedence"));
        const autoSubmitted = normalizeMailHeaderValue(headerLookup(headers, "Auto-Submitted"));
        const unread = Array.isArray(payload.labelIds) && payload.labelIds.includes("UNREAD");
        const lowSignal = isLowSignalGmailMessage({
          labels: payload.labelIds || [],
          subject,
          sender,
          snippet,
          listUnsubscribe,
          precedence,
          autoSubmitted,
        });
        return {
          provider: "google",
          thread_ref: String(payload.threadId || message.id),
          subject,
          snippet,
          sender,
          received_at: dateValue ? new Date(dateValue).toISOString() : null,
          unread_count: unread ? 1 : 0,
          reply_needed: unread && !lowSignal,
          metadata: {
            message_id: payload.id,
            history_id: payload.historyId,
            labels: payload.labelIds || [],
            sender,
            list_unsubscribe: listUnsubscribe,
            precedence,
            auto_submitted: autoSubmitted,
            auto_generated: Boolean(listUnsubscribe || autoSubmitted || ["bulk", "list", "junk"].includes(String(precedence || "").trim().toLowerCase())),
          },
        };
      }),
    );
    for (const item of results) {
      if (item) {
        threads.push(item);
      }
    }
  }
  return threads;
}

async function fetchCalendarEvents(accessToken) {
  const timeMin = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const timeMax = new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString();
  const params = new URLSearchParams({
    singleEvents: "true",
    orderBy: "startTime",
    maxResults: "120",
    timeMin,
    timeMax,
  });
  const response = await fetch(`https://www.googleapis.com/calendar/v3/calendars/primary/events?${params.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(googleError(payload, "Google Takvim olayları okunamadı."));
  }
  return (Array.isArray(payload.items) ? payload.items : []).map((item) => ({
    provider: "google",
    external_id: String(item.id || ""),
    title: String(item.summary || "Takvim kaydı"),
    starts_at: String(item.start?.dateTime || item.start?.date || new Date().toISOString()),
    ends_at: String(item.end?.dateTime || item.end?.date || ""),
    location: String(item.location || ""),
    metadata: {
      html_link: item.htmlLink || "",
      status: item.status || "",
    },
  }));
}

async function fetchGoogleDriveFiles(accessToken) {
  const params = new URLSearchParams({
    pageSize: "25",
    fields: "files(id, name, mimeType, webViewLink, modifiedTime)",
    orderBy: "modifiedTime desc",
  });
  const response = await fetch(`https://www.googleapis.com/drive/v3/files?${params.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(googleError(payload, "Google Drive dosyaları okunamadı."));
  }
  return (Array.isArray(payload.files) ? payload.files : []).map((file) => ({
    provider: "google",
    external_id: String(file.id || ""),
    name: String(file.name || "İsimsiz dosya"),
    mime_type: String(file.mimeType || ""),
    web_view_link: String(file.webViewLink || ""),
    modified_at: String(file.modifiedTime || new Date().toISOString()),
  }));
}

async function fetchYouTubePlaylistItems(accessToken, playlistId, { limit = 8 } = {}) {
  const params = new URLSearchParams({
    part: "snippet,contentDetails",
    playlistId: String(playlistId || ""),
    maxResults: String(Math.max(1, Math.min(limit, 20))),
  });
  const response = await fetch(`https://www.googleapis.com/youtube/v3/playlistItems?${params.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    return [];
  }
  return (Array.isArray(payload.items) ? payload.items : []).map((item) => ({
    video_id: String(item.contentDetails?.videoId || ""),
    title: String(item.snippet?.title || "İsimsiz video"),
    channel_title: String(item.snippet?.videoOwnerChannelTitle || item.snippet?.channelTitle || ""),
    position: Number(item.snippet?.position || 0),
    published_at: String(item.contentDetails?.videoPublishedAt || item.snippet?.publishedAt || ""),
    thumbnail_url:
      String(
        item.snippet?.thumbnails?.medium?.url
        || item.snippet?.thumbnails?.default?.url
        || item.snippet?.thumbnails?.high?.url
        || "",
      ),
  }));
}

async function fetchYouTubePlaylists(accessToken) {
  const params = new URLSearchParams({
    part: "snippet,contentDetails,status",
    mine: "true",
    maxResults: "25",
  });
  const response = await fetch(`https://www.googleapis.com/youtube/v3/playlists?${params.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(googleError(payload, "YouTube playlistleri okunamadı."));
  }
  const items = Array.isArray(payload.items) ? payload.items : [];
  const playlists = [];
  for (const item of items) {
    const playlistId = String(item.id || "").trim();
    if (!playlistId) {
      continue;
    }
    const playlistItems = await fetchYouTubePlaylistItems(accessToken, playlistId, { limit: 8 });
    playlists.push({
      provider: "youtube",
      external_id: playlistId,
      title: String(item.snippet?.title || "YouTube playlist"),
      description: String(item.snippet?.description || ""),
      privacy_status: String(item.status?.privacyStatus || "private"),
      item_count: Number(item.contentDetails?.itemCount || playlistItems.length || 0),
      channel_title: String(item.snippet?.channelTitle || ""),
      web_view_link: `https://www.youtube.com/playlist?list=${encodeURIComponent(playlistId)}`,
      published_at: String(item.snippet?.publishedAt || ""),
      thumbnails: item.snippet?.thumbnails || {},
      items: playlistItems,
    });
  }
  return playlists;
}

async function syncGoogleData(config, runtimeInfo) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const google = config?.google || {};
  if (!google.oauthConnected) {
    throw new Error("Google hesabı bağlı değil.");
  }
  const refreshed = await refreshAccessToken(config);
  const accessToken = refreshed.accessToken;
  if (!accessToken) {
    throw new Error("Google erişim anahtarı bulunamadı.");
  }
  const scopes = Array.isArray(google.scopes) ? google.scopes : [];
  const shouldFetchYouTube = hasGoogleScope(scopes, GOOGLE_YOUTUBE_READ_SCOPE);
  const [emailThreads, calendarEvents, driveFiles, youtubePlaylists] = await Promise.all([
    fetchGmailThreads(accessToken),
    fetchCalendarEvents(accessToken),
    fetchGoogleDriveFiles(accessToken),
    shouldFetchYouTube ? fetchYouTubePlaylists(accessToken) : Promise.resolve([]),
  ]);
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/google/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: google.accountLabel || "Google hesabı",
      scopes: Array.isArray(google.scopes) ? google.scopes : [],
      email_threads: emailThreads,
      calendar_events: calendarEvents,
      drive_files: driveFiles,
      youtube_playlists: youtubePlaylists,
      synced_at: new Date().toISOString(),
    }),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(googleError(payload, "Google verileri eşitlenemedi."));
  }
  return {
    ok: true,
    message: "Google verileri eşitlendi.",
    synced: payload.synced || {
      email_threads: emailThreads.length,
      calendar_events: calendarEvents.length,
      drive_files: driveFiles.length,
      youtube_playlists: youtubePlaylists.length,
    },
    status: payload.status || null,
    patch: refreshed.patch,
  };
}

function portabilityResourcesFromScopes(scopes) {
  const available = Array.isArray(scopes) ? scopes : [];
  const resources = available
    .map((scope) => GOOGLE_PORTABILITY_RESOURCE_BY_SCOPE[String(scope || "").trim()])
    .filter(Boolean);
  return Array.from(new Set(resources));
}

async function portabilityRequest(config, method, pathname, body = undefined) {
  const refreshed = await refreshPortabilityAccessToken(config);
  const accessToken = refreshed.accessToken;
  if (!accessToken) {
    throw new Error("Google geçmiş aktarımı için erişim anahtarı bulunamadı.");
  }
  const response = await fetch(`${GOOGLE_PORTABILITY_API_BASE}${pathname}`, {
    method,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(googleError(payload, "Google geçmiş aktarımı isteği tamamlanamadı."));
  }
  return { payload, patch: refreshed.patch };
}

async function initiateGooglePortabilityArchive(config) {
  const scopes = Array.isArray(config?.googlePortability?.scopes) ? config.googlePortability.scopes : [];
  const resources = portabilityResourcesFromScopes(scopes);
  if (!resources.length) {
    throw new Error("Google geçmiş aktarımı için uygun scope bulunamadı.");
  }
  const { payload, patch } = await portabilityRequest(config, "POST", "/portabilityArchive:initiate", {
    resources,
  });
  const archiveJobId = String(payload?.archiveJobId || payload?.archive_job_id || "").trim();
  const accessType = String(payload?.accessType || payload?.access_type || "").trim();
  if (!archiveJobId) {
    throw new Error("Google geçmiş aktarımı işi başlatıldı ama arşiv kimliği dönmedi.");
  }
  return {
    archiveJobId,
    accessType,
    patch: {
      ...(patch || {}),
      googlePortability: {
        archiveJobId,
        archiveState: "IN_PROGRESS",
        archiveStartedAt: new Date().toISOString(),
      },
    },
  };
}

async function getGooglePortabilityArchiveState(config, archiveJobId) {
  const normalizedJobId = String(archiveJobId || "").trim();
  if (!normalizedJobId) {
    throw new Error("Google geçmiş aktarımı arşiv kimliği eksik.");
  }
  const { payload, patch } = await portabilityRequest(
    config,
    "GET",
    `/archiveJobs/${encodeURIComponent(normalizedJobId)}/portabilityArchiveState`,
  );
  const state = String(payload?.state || "").trim().toUpperCase();
  return {
    name: String(payload?.name || ""),
    state,
    urls: Array.isArray(payload?.urls) ? payload.urls : [],
    exportTime: String(payload?.exportTime || payload?.export_time || ""),
    startTime: String(payload?.startTime || payload?.start_time || ""),
    patch,
  };
}

function normalizeMaybeUrl(value) {
  const text = String(value || "").trim();
  return /^https?:\/\//i.test(text) ? text : "";
}

function coerceIsoTime(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    if (value > 1e15) {
      return new Date(Math.floor(value / 1000)).toISOString();
    }
    if (value > 1e12) {
      return new Date(value).toISOString();
    }
    if (value > 1e9) {
      return new Date(value * 1000).toISOString();
    }
  }
  const text = String(value).trim();
  if (/^\d+$/.test(text)) {
    return coerceIsoTime(Number(text));
  }
  const parsed = Date.parse(text);
  return Number.isFinite(parsed) ? new Date(parsed).toISOString() : "";
}

function findValue(record, predicate, seen = new Set()) {
  if (!record || typeof record !== "object" || seen.has(record)) {
    return "";
  }
  seen.add(record);
  if (Array.isArray(record)) {
    for (const item of record) {
      const value = findValue(item, predicate, seen);
      if (value) {
        return value;
      }
    }
    return "";
  }
  for (const [key, value] of Object.entries(record)) {
    if (predicate(key, value)) {
      if (typeof value === "string" || typeof value === "number") {
        return String(value);
      }
    }
    if (value && typeof value === "object") {
      const nested = findValue(value, predicate, seen);
      if (nested) {
        return nested;
      }
    }
  }
  return "";
}

function flattenRecords(value) {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => flattenRecords(item));
  }
  if (typeof value === "object") {
    const nestedArrays = Object.values(value)
      .filter((item) => Array.isArray(item))
      .flatMap((item) => flattenRecords(item));
    return nestedArrays.length ? nestedArrays : [value];
  }
  return [];
}

function decodeHtmlEntities(value) {
  return String(value || "")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, "\"")
    .replace(/&#39;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&#(\d+);/g, (_match, code) => String.fromCharCode(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_match, code) => String.fromCharCode(parseInt(code, 16)));
}

function stripHtml(value) {
  return decodeHtmlEntities(
    String(value || "")
      .replace(/<\s*br\s*\/?>/gi, "\n")
      .replace(/<\s*\/(?:p|div|li|tr|h\d)\s*>/gi, "\n")
      .replace(/<[^>]+>/g, " "),
  )
    .replace(/\s+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function extractDateFromText(value) {
  const text = stripHtml(value);
  if (!text) {
    return "";
  }
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim().replace(/^[•·*-]\s*/, "");
    if (!line) {
      continue;
    }
    const parsed = Date.parse(line);
    if (Number.isFinite(parsed)) {
      return new Date(parsed).toISOString();
    }
  }
  const isoMatch = text.match(/\b\d{4}-\d{2}-\d{2}[T ][0-9:.+-Z]*/);
  if (isoMatch) {
    const parsed = Date.parse(isoMatch[0]);
    if (Number.isFinite(parsed)) {
      return new Date(parsed).toISOString();
    }
  }
  return "";
}

function parseHtmlEntriesFromText(text, fileName = "") {
  const html = String(text || "").trim();
  if (!html) {
    return [];
  }
  const lowerName = String(fileName || "").toLowerCase();
  const entries = [];
  const anchorPattern = /<a\b[^>]*href=(["'])(.*?)\1[^>]*>([\s\S]*?)<\/a>/gi;
  for (const match of html.matchAll(anchorPattern)) {
    const href = normalizeMaybeUrl(decodeHtmlEntities(match[2] || ""));
    if (!href || !/^https?:\/\//i.test(href)) {
      continue;
    }
    const title = stripHtml(match[3] || "").trim() || href;
    const start = Math.max(0, (match.index || 0) - 240);
    const end = Math.min(html.length, (match.index || 0) + match[0].length + 360);
    const context = html.slice(start, end);
    const timestamp = extractDateFromText(context);
    const textContext = stripHtml(context);
    let subtitle = "";
    for (const line of textContext.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)) {
      if (line !== title && !/^https?:\/\//i.test(line) && !Date.parse(line)) {
        subtitle = line;
        break;
      }
    }
    entries.push({
      title,
      url: href,
      time: timestamp,
      subtitle,
      source_file: lowerName,
      raw_context: textContext.slice(0, 800),
    });
  }
  return entries;
}

function deriveYoutubeHistoryEntries(records) {
  const entries = [];
  for (const record of records) {
    const url = normalizeMaybeUrl(
      findValue(record, (_key, value) => typeof value === "string" && /youtu(\.be|be\.com)/i.test(value)),
    );
    if (!url) {
      continue;
    }
    const title = String(
      findValue(record, (key, value) => typeof value === "string" && ["title", "name", "header"].includes(String(key).toLowerCase()))
      || url,
    ).trim();
    const viewedAt = coerceIsoTime(
      findValue(record, (key) => ["time", "time_usec", "timeusec", "viewedat", "visitedat", "eventtime", "timestamp"].includes(String(key).toLowerCase())),
    );
    const channelTitle = String(
      findValue(record, (key, value) => typeof value === "string" && ["channeltitle", "ownerchanneltitle", "subtitle"].includes(String(key).toLowerCase())),
    ).trim();
    entries.push({
      provider: "youtube",
      external_id: `${title}:${viewedAt || url}`.slice(0, 255),
      title: title.slice(0, 500),
      url: url.slice(0, 2000),
      channel_title: channelTitle.slice(0, 255) || undefined,
      viewed_at: viewedAt || undefined,
      metadata: record,
    });
  }
  return entries;
}

function deriveChromeHistoryEntries(records) {
  const entries = [];
  for (const record of records) {
    const url = normalizeMaybeUrl(
      findValue(record, (key, value) => typeof value === "string" && ["url", "pageurl", "link", "titleurl"].includes(String(key).toLowerCase()))
      || findValue(record, (_key, value) => typeof value === "string" && /^https?:\/\//i.test(value)),
    );
    if (!url || /youtu(\.be|be\.com)/i.test(url)) {
      continue;
    }
    const title = String(
      findValue(record, (key, value) => typeof value === "string" && ["title", "name", "header"].includes(String(key).toLowerCase())),
    ).trim();
    const visitedAt = coerceIsoTime(
      findValue(record, (key) => ["time", "time_usec", "timeusec", "visitedat", "lastvisitedtime", "timestamp"].includes(String(key).toLowerCase())),
    );
    entries.push({
      provider: "chrome",
      external_id: `${url}:${visitedAt || title}`.slice(0, 255),
      title: title.slice(0, 500) || undefined,
      url: url.slice(0, 2000),
      visited_at: visitedAt || undefined,
      metadata: record,
    });
  }
  return entries;
}

function uniqueBy(items, keyFn) {
  const seen = new Set();
  const results = [];
  for (const item of items) {
    const key = keyFn(item);
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    results.push(item);
  }
  return results;
}

async function downloadArchivePayload(url) {
  const response = await fetch(String(url || "").trim());
  if (!response.ok) {
    throw new Error("Google geçmiş arşivi indirilemedi.");
  }
  return Buffer.from(await response.arrayBuffer());
}

function parseArchiveEntries(buffer) {
  const zip = new AdmZip(buffer);
  const entries = [];
  for (const entry of zip.getEntries()) {
    if (entry.isDirectory) {
      continue;
    }
    const name = String(entry.entryName || "").toLowerCase();
    const text = entry.getData().toString("utf-8").trim();
    if (!text) {
      continue;
    }
    if (name.endsWith(".html") || name.endsWith(".htm")) {
      entries.push(...parseHtmlEntriesFromText(text, name));
      continue;
    }
    if (!name.endsWith(".json") && !name.endsWith(".ndjson")) {
      continue;
    }
    if (name.endsWith(".ndjson")) {
      for (const line of text.split(/\r?\n/)) {
        const normalized = line.trim();
        if (!normalized) {
          continue;
        }
        try {
          entries.push(...flattenRecords(JSON.parse(normalized)));
        } catch {
          continue;
        }
      }
      continue;
    }
    try {
      entries.push(...flattenRecords(JSON.parse(text)));
    } catch {
      continue;
    }
  }
  return entries;
}

function parseJsonEntriesFromText(text, fileName = "") {
  const normalizedText = String(text || "").trim();
  if (!normalizedText) {
    return [];
  }
  const lowerName = String(fileName || "").toLowerCase();
  if (lowerName.endsWith(".ndjson")) {
    const entries = [];
    for (const line of normalizedText.split(/\r?\n/)) {
      const normalizedLine = line.trim();
      if (!normalizedLine) {
        continue;
      }
      try {
        entries.push(...flattenRecords(JSON.parse(normalizedLine)));
      } catch {
        continue;
      }
    }
    return entries;
  }
  try {
    return flattenRecords(JSON.parse(normalizedText));
  } catch {
    return [];
  }
}

async function collectTakeoutInputFiles(inputPaths, results = [], seen = new Set()) {
  const paths = Array.isArray(inputPaths)
    ? inputPaths.map((value) => String(value || "").trim()).filter(Boolean)
    : [];
  for (const filePath of paths) {
    if (!filePath || seen.has(filePath) || results.length >= 50) {
      continue;
    }
    seen.add(filePath);
    let stat = null;
    try {
      stat = await fs.promises.stat(filePath);
    } catch {
      continue;
    }
    if (stat.isDirectory()) {
      let entries = [];
      try {
        entries = await fs.promises.readdir(filePath);
      } catch {
        continue;
      }
      await collectTakeoutInputFiles(entries.map((name) => path.join(filePath, name)), results, seen);
      continue;
    }
    results.push(filePath);
  }
  return results;
}

async function parseLocalGoogleTakeoutFiles(filePaths) {
  const paths = await collectTakeoutInputFiles(filePaths);
  const records = [];
  for (const filePath of paths.slice(0, 50)) {
    const lowerName = path.basename(filePath).toLowerCase();
    const payload = await fs.promises.readFile(filePath);
    if (lowerName.endsWith(".zip")) {
      records.push(...parseArchiveEntries(payload));
      continue;
    }
    if (lowerName.endsWith(".html") || lowerName.endsWith(".htm")) {
      records.push(...parseHtmlEntriesFromText(payload.toString("utf-8"), lowerName));
      continue;
    }
    if (lowerName.endsWith(".json") || lowerName.endsWith(".ndjson")) {
      records.push(...parseJsonEntriesFromText(payload.toString("utf-8"), lowerName));
    }
  }
  return {
    youtubeHistoryEntries: uniqueBy(deriveYoutubeHistoryEntries(records), (item) => item.external_id).slice(0, 500),
    chromeHistoryEntries: uniqueBy(deriveChromeHistoryEntries(records), (item) => item.external_id).slice(0, 500),
  };
}

function extractArchiveUrls(urls) {
  const list = Array.isArray(urls) ? urls : [];
  return list
    .map((item) => {
      if (typeof item === "string") {
        return item;
      }
      if (item && typeof item === "object") {
        return String(item.url || item.downloadUrl || item.href || "").trim();
      }
      return "";
    })
    .filter(Boolean);
}

async function parseGooglePortabilityArchives(urls) {
  const archiveUrls = extractArchiveUrls(urls);
  const records = [];
  for (const url of archiveUrls.slice(0, 5)) {
    const payload = await downloadArchivePayload(url);
    records.push(...parseArchiveEntries(payload));
  }
  const youtubeHistoryEntries = uniqueBy(deriveYoutubeHistoryEntries(records), (item) => item.external_id).slice(0, 200);
  const chromeHistoryEntries = uniqueBy(deriveChromeHistoryEntries(records), (item) => item.external_id).slice(0, 200);
  return {
    youtubeHistoryEntries,
    chromeHistoryEntries,
  };
}

async function syncGooglePortabilityData(config, runtimeInfo) {
  const portability = config?.googlePortability || {};
  if (!portability.oauthConnected) {
    throw new Error("Google geçmiş aktarımı hesabı bağlı değil.");
  }
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  let combinedPatch = {};
  const currentState = String(portability.archiveState || "").trim().toUpperCase();
  const currentJobId = String(portability.archiveJobId || "").trim();
  const alreadyImported =
    portability.lastImportedAt
    && portability.archiveExportTime
    && Date.parse(String(portability.lastImportedAt)) >= Date.parse(String(portability.archiveExportTime));

  if (!currentJobId || !currentState || currentState === "FAILED" || currentState === "CANCELLED" || (currentState === "COMPLETE" && alreadyImported)) {
    const initiated = await initiateGooglePortabilityArchive(config);
    combinedPatch = { ...combinedPatch, ...(initiated.patch || {}) };
    return {
      ok: true,
      message: "Google geçmiş aktarımı başlatıldı. Arşiv hazır olduğunda tekrar eşitleyin.",
      patch: combinedPatch,
      archiveJobId: initiated.archiveJobId,
      archiveState: "IN_PROGRESS",
    };
  }

  const state = await getGooglePortabilityArchiveState(config, currentJobId);
  combinedPatch = {
    ...combinedPatch,
    ...(state.patch || {}),
    googlePortability: {
      ...((combinedPatch && combinedPatch.googlePortability) || {}),
      archiveJobId: currentJobId,
      archiveState: state.state || currentState,
      archiveStartedAt: state.startTime || portability.archiveStartedAt || "",
      archiveExportTime: state.exportTime || portability.archiveExportTime || "",
      lastSyncAt: new Date().toISOString(),
    },
  };

  if (state.state !== "COMPLETE") {
    return {
      ok: true,
      message: "Google geçmiş aktarımı henüz hazırlanıyor. Birkaç dakika sonra tekrar eşitleyin.",
      patch: combinedPatch,
      archiveJobId: currentJobId,
      archiveState: state.state || currentState,
    };
  }

  const { youtubeHistoryEntries, chromeHistoryEntries } = await parseGooglePortabilityArchives(state.urls);
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/google/portability/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: portability.accountLabel || config?.google?.accountLabel || "Google geçmiş aktarımı",
      scopes: Array.isArray(portability.scopes) ? portability.scopes : [],
      youtube_history_entries: youtubeHistoryEntries,
      chrome_history_entries: chromeHistoryEntries,
      synced_at: new Date().toISOString(),
      checkpoint: {
        archive_job_id: currentJobId,
        archive_state: state.state,
      },
    }),
  });
  const result = await parseJson(response);
  if (!response.ok) {
    throw new Error(googleError(result, "Google geçmiş aktarımı LawCopilot'a işlenemedi."));
  }
  combinedPatch = {
    ...combinedPatch,
    googlePortability: {
      ...((combinedPatch && combinedPatch.googlePortability) || {}),
      lastImportedAt: new Date().toISOString(),
      lastSyncAt: new Date().toISOString(),
      youtubeHistoryAvailable: youtubeHistoryEntries.length > 0,
      youtubeHistoryCount: youtubeHistoryEntries.length,
      chromeHistoryAvailable: chromeHistoryEntries.length > 0,
      chromeHistoryCount: chromeHistoryEntries.length,
    },
  };
  return {
    ok: true,
    message: "Google geçmiş verileri içe aktarıldı.",
    patch: combinedPatch,
    status: result?.status || null,
    synced: result?.synced || {
      youtube_history_entries: youtubeHistoryEntries.length,
      chrome_history_entries: chromeHistoryEntries.length,
    },
  };
}

async function importGoogleTakeoutData(config, runtimeInfo, filePaths) {
  const paths = await collectTakeoutInputFiles(filePaths);
  if (!paths.length) {
    throw new Error("İçe aktarmak için en az bir Google Takeout dosyası seçin.");
  }
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const portability = config?.googlePortability || {};
  const { youtubeHistoryEntries, chromeHistoryEntries } = await parseLocalGoogleTakeoutFiles(paths);
  if (!youtubeHistoryEntries.length && !chromeHistoryEntries.length) {
    throw new Error("Seçilen dosyalarda içe aktarılabilir YouTube veya tarayıcı geçmişi bulunamadı. Google Takeout ZIP'ini, dışa aktarılmış klasörü veya JSON/HTML geçmiş dosyalarını seçin.");
  }
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/google/portability/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: portability.accountLabel || config?.google?.accountLabel || "Google Takeout içe aktarımı",
      scopes: Array.isArray(portability.scopes) ? portability.scopes : [],
      youtube_history_entries: youtubeHistoryEntries,
      chrome_history_entries: chromeHistoryEntries,
      synced_at: new Date().toISOString(),
      checkpoint: {
        source: "takeout_import",
        imported_files: paths.map((filePath) => path.basename(filePath)).slice(0, 20),
      },
    }),
  });
  const result = await parseJson(response);
  if (!response.ok) {
    throw new Error(googleError(result, "Google Takeout geçmiş verileri LawCopilot'a işlenemedi."));
  }
  return {
    ok: true,
    message: `Google Takeout geçmiş verileri içe aktarıldı. YouTube: ${youtubeHistoryEntries.length}, tarayıcı: ${chromeHistoryEntries.length}.`,
    patch: {
      googlePortability: {
        enabled: true,
        accountLabel: portability.accountLabel || config?.google?.accountLabel || "Google Takeout içe aktarımı",
        validationStatus: "valid",
        archiveState: "IMPORTED",
        lastImportedAt: new Date().toISOString(),
        lastSyncAt: new Date().toISOString(),
        youtubeHistoryAvailable: youtubeHistoryEntries.length > 0,
        youtubeHistoryCount: youtubeHistoryEntries.length,
        chromeHistoryAvailable: chromeHistoryEntries.length > 0,
        chromeHistoryCount: chromeHistoryEntries.length,
      },
    },
    status: result?.status || null,
    synced: result?.synced || {
      youtube_history_entries: youtubeHistoryEntries.length,
      chrome_history_entries: chromeHistoryEntries.length,
    },
  };
}

function buildMimeMessage(payload = {}) {
  const normalizedSubject = normalizeMailHeaderValue(payload.subject);
  const normalizedBody = repairUtf8Mojibake(String(payload.body || "")).trim();
  const lines = [
    `To: ${String(payload.to || "").trim()}`,
    `Subject: ${encodeMimeHeaderValue(normalizedSubject)}`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: quoted-printable",
    "",
    encodeQuotedPrintableBody(normalizedBody),
  ];
  return base64UrlEncode(lines.join("\r\n"));
}

async function sendGmailMessage(config, payload = {}) {
  const google = config?.google || {};
  if (!google.oauthConnected) {
    throw new Error("Google hesabı bağlı değil.");
  }
  const refreshed = await refreshAccessToken(config);
  const accessToken = refreshed.accessToken;
  if (!accessToken) {
    throw new Error("Google erişim anahtarı bulunamadı.");
  }
  const to = String(payload.to || "").trim();
  const subject = normalizeMailHeaderValue(payload.subject);
  const body = repairUtf8Mojibake(String(payload.body || "")).trim();
  if (!to || !subject || !body) {
    throw new Error("Gmail gönderimi için alıcı, konu ve gövde gerekli.");
  }
  const response = await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      raw: buildMimeMessage({ to, subject, body }),
      threadId: payload.threadId ? String(payload.threadId) : undefined,
    }),
  });
  const result = await parseJson(response);
  if (!response.ok || !result?.id) {
    throw new Error(googleError(result, "Gmail iletisi gönderilemedi."));
  }
  return {
    ok: true,
    message: "Gmail iletisi gönderildi.",
    externalMessageId: String(result.id),
    externalThreadId: String(result.threadId || ""),
    patch: refreshed.patch,
  };
}

function hasCalendarWriteScope(scopes) {
  return Array.isArray(scopes) && scopes.some((scope) => GOOGLE_CALENDAR_WRITE_SCOPES.includes(String(scope || "").trim()));
}

async function mirrorCreatedCalendarEvent(runtimeInfo, payload) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/assistant/calendar/events`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify(payload),
  });
  const body = await parseJson(response);
  if (!response.ok) {
    throw new Error(googleError(body, "Takvim kaydı yerel ajandaya işlenemedi."));
  }
  return body;
}

async function createGoogleCalendarEvent(config, runtimeInfo, payload) {
  const google = config?.google || {};
  if (!google.oauthConnected) {
    throw new Error("Google hesabı bağlı değil.");
  }
  if (!hasCalendarWriteScope(google.scopes)) {
    throw new Error("Google Takvim yazma izni yok. Ayarlar ekranından Google hesabını yeniden bağlayın.");
  }
  const refreshed = await refreshAccessToken(config);
  const accessToken = refreshed.accessToken;
  if (!accessToken) {
    throw new Error("Google erişim anahtarı bulunamadı.");
  }
  const startsAt = String(payload?.startsAt || "").trim();
  if (!startsAt) {
    throw new Error("Takvim başlangıç zamanı eksik.");
  }
  const endValue = String(payload?.endsAt || "").trim();
  const endDate = endValue ? new Date(endValue) : new Date(new Date(startsAt).getTime() + 60 * 60 * 1000);
  const googlePayload = {
    summary: String(payload?.title || "Plan"),
    location: String(payload?.location || ""),
    description: String(payload?.notes || ""),
    start: { dateTime: startsAt },
    end: { dateTime: endDate.toISOString() },
  };
  const response = await fetch("https://www.googleapis.com/calendar/v3/calendars/primary/events", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(googlePayload),
  });
  const body = await parseJson(response);
  if (!response.ok || !body?.id) {
    throw new Error(googleError(body, "Google Takvim kaydı oluşturulamadı."));
  }
  const mirrored = await mirrorCreatedCalendarEvent(runtimeInfo, {
    provider: "google",
    external_id: String(body.id),
    title: String(body.summary || payload?.title || "Plan"),
    starts_at: String(body.start?.dateTime || body.start?.date || startsAt),
    ends_at: String(body.end?.dateTime || body.end?.date || endDate.toISOString()),
    location: String(body.location || payload?.location || ""),
    matter_id: payload?.matterId || null,
    needs_preparation: payload?.needsPreparation !== false,
    status: String(body.status || "confirmed"),
    attendees: Array.isArray(body.attendees) ? body.attendees.map((item) => String(item?.email || "")).filter(Boolean) : [],
    notes: String(payload?.notes || ""),
    metadata: {
      html_link: body.htmlLink || "",
      calendar_id: body.organizer?.email || "primary",
      provider_status: body.status || "",
    },
  });
  return {
    ok: true,
    message: "Plan Google Takvim'e eklendi.",
    patch: refreshed.patch,
    event: mirrored?.event || null,
  };
}

module.exports = {
  buildMimeMessage,
  createGoogleCalendarEvent,
  encodeMimeHeaderValue,
  importGoogleTakeoutData,
  parseLocalGoogleTakeoutFiles,
  sendGmailMessage,
  syncGoogleData,
  syncGooglePortabilityData,
};
