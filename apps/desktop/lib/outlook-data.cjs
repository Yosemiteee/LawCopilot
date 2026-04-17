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

const DEFAULT_OUTLOOK_SCOPES = [
  "openid",
  "email",
  "profile",
  "offline_access",
  "User.Read",
  "Mail.Read",
  "Calendars.Read",
];

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

function graphError(payload, fallback) {
  return String(payload?.error?.message || payload?.error_description || payload?.error || fallback);
}

function resolveCredentials(config) {
  const outlook = config?.outlook || {};
  return {
    clientId: String(outlook.clientId || process.env.LAWCOPILOT_OUTLOOK_CLIENT_ID || "").trim(),
    tenantId: String(outlook.tenantId || process.env.LAWCOPILOT_OUTLOOK_TENANT_ID || "common").trim() || "common",
    scopes: normalizeScopes(outlook.scopes),
  };
}

function parseOutlookDateTime(value) {
  const raw = String(value?.dateTime || "").trim();
  const timezone = String(value?.timeZone || "UTC").trim().toUpperCase();
  if (!raw) {
    return "";
  }
  if (/[zZ]|[+-]\d{2}:\d{2}$/.test(raw)) {
    return new Date(raw).toISOString();
  }
  if (timezone === "UTC") {
    return new Date(`${raw}Z`).toISOString();
  }
  return new Date(raw).toISOString();
}

function addressLabel(value) {
  const address = String(value?.address || "").trim();
  const name = String(value?.name || "").trim();
  if (name && address) {
    return `${name} <${address}>`;
  }
  return address || name;
}

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

function isLowSignalOutlookMessage({ inferenceClassification, sender, subject, snippet, categories }) {
  const haystack = buildEmailHaystack(sender, subject, snippet, categories);
  let score = 0;
  if (String(inferenceClassification || "").trim().toLowerCase() === "other") {
    score += 1;
  }
  if (LOW_SIGNAL_EMAIL_SENDER_TOKENS.some((token) => haystack.includes(token))) {
    score += 1;
  }
  if (LOW_SIGNAL_EMAIL_TEXT_TOKENS.some((token) => haystack.includes(token))) {
    score += 1;
  }
  return score >= 2;
}

async function refreshAccessToken(config) {
  const credentials = resolveCredentials(config);
  const outlook = config?.outlook || {};
  if (!outlook.refreshToken || !credentials.clientId) {
    return { accessToken: String(outlook.accessToken || ""), patch: null };
  }
  const expiresAt = outlook.expiryDate ? Date.parse(String(outlook.expiryDate)) : 0;
  if (expiresAt && expiresAt > Date.now() + 60_000 && outlook.accessToken) {
    return { accessToken: String(outlook.accessToken), patch: null };
  }
  const body = new URLSearchParams({
    client_id: credentials.clientId,
    grant_type: "refresh_token",
    refresh_token: String(outlook.refreshToken),
    scope: credentials.scopes.join(" "),
  });
  const response = await fetch(`https://login.microsoftonline.com/${encodeURIComponent(credentials.tenantId)}/oauth2/v2.0/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const payload = await parseJson(response);
  if (!response.ok || !payload.access_token) {
    throw new Error(graphError(payload, "Outlook erişim anahtarı yenilenemedi."));
  }
  return {
    accessToken: String(payload.access_token),
    patch: {
      outlook: {
        accessToken: String(payload.access_token),
        refreshToken: String(payload.refresh_token || outlook.refreshToken || ""),
        tokenType: String(payload.token_type || "Bearer"),
        expiryDate: payload.expires_in ? new Date(Date.now() + Number(payload.expires_in) * 1000).toISOString() : "",
        lastValidatedAt: new Date().toISOString(),
        validationStatus: "valid",
      },
    },
  };
}

async function fetchOutlookThreads(accessToken) {
  const since = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
  const params = new URLSearchParams({
    $top: "25",
    $select: "id,conversationId,subject,from,receivedDateTime,isRead,bodyPreview,webLink,inferenceClassification,categories",
    $orderby: "receivedDateTime DESC",
    $filter: `receivedDateTime ge ${since}`,
  });
  const response = await fetch(`https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages?${params.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(graphError(payload, "Outlook gelen kutusu okunamadı."));
  }
  const messages = Array.isArray(payload.value) ? payload.value : [];
  const grouped = new Map();
  for (const item of messages) {
    const threadRef = String(item.conversationId || item.id || "").trim();
    if (!threadRef) {
      continue;
    }
    const sender = addressLabel(item.from?.emailAddress);
    const receivedAt = item.receivedDateTime ? new Date(String(item.receivedDateTime)).toISOString() : null;
    const lowSignal = isLowSignalOutlookMessage({
      inferenceClassification: item.inferenceClassification,
      sender,
      subject: item.subject,
      snippet: item.bodyPreview,
      categories: item.categories,
    });
    if (!grouped.has(threadRef)) {
      grouped.set(threadRef, {
        provider: "outlook",
        thread_ref: threadRef,
        subject: String(item.subject || "Konu yok"),
        snippet: String(item.bodyPreview || ""),
        sender,
        received_at: receivedAt,
        unread_count: 0,
        reply_needed: false,
        metadata: {
          web_link: String(item.webLink || ""),
          last_message_id: String(item.id || ""),
          message_count: 0,
          inference_classification: String(item.inferenceClassification || ""),
          categories: Array.isArray(item.categories) ? item.categories : [],
          sender,
        },
        participants: [],
      });
    }
    const current = grouped.get(threadRef);
    current.metadata.message_count += 1;
    if (sender && !current.participants.includes(sender)) {
      current.participants.push(sender);
    }
    if (receivedAt && (!current.received_at || receivedAt > current.received_at)) {
      current.received_at = receivedAt;
      current.subject = String(item.subject || current.subject || "Konu yok");
      current.snippet = String(item.bodyPreview || current.snippet || "");
      current.sender = sender || current.sender;
      current.metadata.web_link = String(item.webLink || current.metadata.web_link || "");
      current.metadata.last_message_id = String(item.id || current.metadata.last_message_id || "");
    }
    if (!item.isRead) {
      current.unread_count += 1;
      if (!lowSignal) {
        current.reply_needed = true;
      }
    }
  }
  return [...grouped.values()].map((item) => ({
    provider: item.provider,
    thread_ref: item.thread_ref,
    subject: item.subject,
    snippet: item.snippet,
    sender: item.sender,
    received_at: item.received_at,
    unread_count: item.unread_count,
    reply_needed: item.reply_needed,
    metadata: {
      ...item.metadata,
      participants: item.participants,
    },
  }));
}

async function fetchOutlookCalendarEvents(accessToken) {
  const params = new URLSearchParams({
    startDateTime: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    endDateTime: new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString(),
    $top: "120",
    $select: "id,subject,start,end,location,webLink,attendees,responseStatus,isAllDay",
  });
  const response = await fetch(`https://graph.microsoft.com/v1.0/me/calendar/calendarView?${params.toString()}`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Prefer: 'outlook.timezone="UTC"',
    },
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(graphError(payload, "Outlook takvim kayıtları okunamadı."));
  }
  return (Array.isArray(payload.value) ? payload.value : []).map((item) => ({
    provider: "outlook",
    external_id: String(item.id || ""),
    title: String(item.subject || "Takvim kaydı"),
    starts_at: parseOutlookDateTime(item.start),
    ends_at: parseOutlookDateTime(item.end) || "",
    location: String(item.location?.displayName || ""),
    metadata: {
      web_link: String(item.webLink || ""),
      is_all_day: Boolean(item.isAllDay),
      attendee_count: Array.isArray(item.attendees) ? item.attendees.length : 0,
      response_status: String(item.responseStatus?.response || ""),
    },
  }));
}

async function syncOutlookData(config, runtimeInfo) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const outlook = config?.outlook || {};
  if (!outlook.oauthConnected) {
    throw new Error("Outlook hesabı bağlı değil.");
  }
  const refreshed = await refreshAccessToken(config);
  const accessToken = refreshed.accessToken;
  if (!accessToken) {
    throw new Error("Outlook erişim anahtarı bulunamadı.");
  }
  const [emailThreads, calendarEvents] = await Promise.all([
    fetchOutlookThreads(accessToken),
    fetchOutlookCalendarEvents(accessToken),
  ]);
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/outlook/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: outlook.accountLabel || "Outlook hesabı",
      scopes: Array.isArray(outlook.scopes) ? outlook.scopes : [],
      email_threads: emailThreads,
      calendar_events: calendarEvents,
      synced_at: new Date().toISOString(),
    }),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(graphError(payload, "Outlook verileri eşitlenemedi."));
  }
  return {
    ok: true,
    message: "Outlook verileri eşitlendi.",
    synced: payload.synced || { email_threads: emailThreads.length, calendar_events: calendarEvents.length },
    status: payload.status || null,
    patch: {
      ...((refreshed.patch || {})),
      outlook: {
        ...(((refreshed.patch || {}).outlook) || {}),
        lastSyncAt: new Date().toISOString(),
      },
    },
  };
}

module.exports = {
  syncOutlookData,
};
