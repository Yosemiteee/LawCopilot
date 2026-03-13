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

function googleError(payload, fallback) {
  return String(payload?.error_description || payload?.error?.message || payload?.error || fallback);
}

const GOOGLE_CALENDAR_WRITE_SCOPES = [
  "https://www.googleapis.com/auth/calendar.events",
  "https://www.googleapis.com/auth/calendar",
];

function resolveCredentials() {
  return {
    clientId: process.env.LAWCOPILOT_GOOGLE_CLIENT_ID || "",
    clientSecret: process.env.LAWCOPILOT_GOOGLE_CLIENT_SECRET || "",
  };
}

async function refreshAccessToken(config) {
  const credentials = resolveCredentials();
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

function headerLookup(headers, name) {
  const match = (headers || []).find((item) => String(item?.name || "").toLowerCase() === name.toLowerCase());
  return String(match?.value || "");
}

async function fetchGmailThreads(accessToken) {
  const listResponse = await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages?labelIds=INBOX&maxResults=10&q=newer_than:30d", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const listPayload = await parseJson(listResponse);
  if (!listResponse.ok) {
    throw new Error(googleError(listPayload, "Gmail gelen kutusu okunamadı."));
  }
  const messages = Array.isArray(listPayload.messages) ? listPayload.messages : [];
  const threads = [];
  for (const message of messages) {
    const response = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/messages/${encodeURIComponent(String(message.id))}?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date`,
      {
        headers: { Authorization: `Bearer ${accessToken}` },
      },
    );
    const payload = await parseJson(response);
    if (!response.ok) {
      continue;
    }
    const headers = payload.payload?.headers || [];
    const dateValue = headerLookup(headers, "Date");
    threads.push({
      provider: "google",
      thread_ref: String(payload.threadId || message.id),
      subject: headerLookup(headers, "Subject") || "Konu yok",
      snippet: String(payload.snippet || ""),
      sender: headerLookup(headers, "From") || "",
      received_at: dateValue ? new Date(dateValue).toISOString() : null,
      unread_count: Array.isArray(payload.labelIds) && payload.labelIds.includes("UNREAD") ? 1 : 0,
      reply_needed: Array.isArray(payload.labelIds) ? payload.labelIds.includes("UNREAD") : true,
      metadata: {
        message_id: payload.id,
        history_id: payload.historyId,
        labels: payload.labelIds || [],
      },
    });
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
  const [emailThreads, calendarEvents, driveFiles] = await Promise.all([
    fetchGmailThreads(accessToken),
    fetchCalendarEvents(accessToken),
    fetchGoogleDriveFiles(accessToken),
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
    synced: payload.synced || { email_threads: emailThreads.length, calendar_events: calendarEvents.length, drive_files: driveFiles.length },
    status: payload.status || null,
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
  createGoogleCalendarEvent,
  syncGoogleData,
};
