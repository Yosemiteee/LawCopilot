const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const QRCode = require("qrcode");
const { Client, LocalAuth } = require("whatsapp-web.js");

const { resolveConfigDir } = require("./config.cjs");

const DEFAULT_GRAPH_SYNC_MAX_CHATS = Number(process.env.LAWCOPILOT_WHATSAPP_WEB_MAX_CHATS || 80);
const DEFAULT_GRAPH_SYNC_MESSAGES_PER_CHAT = Number(process.env.LAWCOPILOT_WHATSAPP_WEB_MESSAGES_PER_CHAT || 40);
const DEFAULT_SYNC_BATCH_SIZE = Number(process.env.LAWCOPILOT_WHATSAPP_WEB_SYNC_BATCH_SIZE || 100);
const DEFAULT_CONTACT_SYNC_MAX_CHATS = Number(process.env.LAWCOPILOT_WHATSAPP_WEB_CONTACT_MAX_CHATS || 300);

let bridgeContext = {
  loadConfig: () => ({}),
  saveConfig: async () => ({}),
  getRuntimeInfo: async () => null,
};

let client = null;
let clientSessionName = "";
let initPromise = null;
let lastSyncPromise = null;
const seenMessageRefs = new Set();
const CONTACT_ALIAS_CACHE_TTL_MS = 60_000;
const contactAliasCache = {
  builtAt: 0,
  map: new Map(),
};

const state = {
  status: "idle",
  qrText: "",
  qrDataUrl: "",
  lastError: "",
  accountLabel: "",
  currentUser: "",
  webSessionName: "default",
  lastReadyAt: "",
  lastSyncAt: "",
  messageCountMirrored: 0,
};

function nowIso() {
  return new Date().toISOString();
}

function normalizeWhatsAppMode(value, fallback = "web") {
  const mode = String(value || fallback || "").trim().toLowerCase();
  if (mode === "business_cloud" || mode === "web") {
    return mode;
  }
  return fallback;
}

function resolveWhatsAppMode(config) {
  const whatsapp = config?.whatsapp || {};
  if (String(whatsapp.mode || "").trim()) {
    return normalizeWhatsAppMode(whatsapp.mode);
  }
  if (whatsapp.phoneNumberId || whatsapp.accessToken) {
    return "business_cloud";
  }
  return "web";
}

function resolveSessionName(config) {
  const raw = String(config?.whatsapp?.webSessionName || "default").trim();
  return raw.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-+|-+$/g, "") || "default";
}

function resolveAuthDataPath() {
  return path.join(resolveConfigDir(), "whatsapp-web-auth");
}

function resolveSessionUserDataDir(config) {
  return path.join(resolveAuthDataPath(), `session-${resolveSessionName(config)}`);
}

function resolveChromeExecutable() {
  const candidates = [
    process.env.LAWCOPILOT_WHATSAPP_WEB_EXECUTABLE,
    process.env.CHROME_PATH,
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/snap/bin/chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  return candidates.find((candidate) => {
    try {
      return fs.existsSync(candidate);
    } catch {
      return false;
    }
  }) || "";
}

function isReadyStatus(value) {
  return ["ready", "authenticated"].includes(String(value || "").trim().toLowerCase());
}

function buildSelfLabel(clientInfo) {
  const wid = String(clientInfo?.wid?._serialized || clientInfo?.wid?.user || "").trim();
  const pushname = String(clientInfo?.pushname || "").trim();
  return pushname || wid || "WhatsApp";
}

function sessionConflictProcesses(config) {
  const userDataDir = resolveSessionUserDataDir(config);
  if (!userDataDir) {
    return [];
  }
  try {
    const result = spawnSync("pgrep", ["-af", userDataDir], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 2500,
    });
    const currentPid = Number(process.pid || 0);
    return String(result.stdout || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const match = /^(\d+)\s+(.*)$/.exec(line);
        if (!match) {
          return null;
        }
        return {
          pid: Number.parseInt(match[1], 10),
          command: String(match[2] || ""),
        };
      })
      .filter((item) => item && Number.isFinite(item.pid) && item.pid > 0 && item.pid !== currentPid);
  } catch {
    return [];
  }
}

function isSessionConflictError(error) {
  const message = String(error?.message || error || "").toLowerCase();
  return message.includes("browser is already running for");
}

function createSessionBusyError(config) {
  const userDataDir = resolveSessionUserDataDir(config);
  const error = new Error(
    "Bu WhatsApp Web oturumu zaten baska bir Chromium surecinde acik. O sureci kapatin veya farkli bir oturum adi kullanin.",
  );
  error.code = "WHATSAPP_WEB_SESSION_BUSY";
  error.userDataDir = userDataDir;
  error.processes = sessionConflictProcesses(config);
  return error;
}

function baseStatus(config) {
  const whatsapp = config?.whatsapp || {};
  const mode = resolveWhatsAppMode(config);
  const currentWebStatus = String(state.status || whatsapp.webStatus || "idle");
  const configured = mode === "web"
    ? Boolean(isReadyStatus(currentWebStatus) || whatsapp.webAccountLabel)
    : Boolean(whatsapp.enabled && whatsapp.accessToken && whatsapp.phoneNumberId);
  return {
    provider: "whatsapp",
    mode,
    configured,
    enabled: Boolean(whatsapp.enabled),
    accountLabel:
      state.accountLabel
      || String(whatsapp.webAccountLabel || whatsapp.businessLabel || whatsapp.verifiedName || whatsapp.displayPhoneNumber || "WhatsApp hesabı"),
    displayPhoneNumber: String(whatsapp.displayPhoneNumber || ""),
    verifiedName: String(whatsapp.verifiedName || ""),
    phoneNumberId: String(whatsapp.phoneNumberId || ""),
    validationStatus: mode === "web" ? (configured ? "valid" : String(whatsapp.validationStatus || "pending")) : String(whatsapp.validationStatus || "pending"),
    webStatus: currentWebStatus,
    webSessionName: state.webSessionName || resolveSessionName(config),
    webQrDataUrl: state.qrDataUrl || "",
    webQrReady: Boolean(state.qrDataUrl),
    webCurrentUser: state.currentUser || "",
    webAccountLabel: state.accountLabel || String(whatsapp.webAccountLabel || ""),
    webLastReadyAt: state.lastReadyAt || String(whatsapp.webLastReadyAt || ""),
    webLastSyncAt: state.lastSyncAt || String(whatsapp.webLastSyncAt || ""),
    webBrowserLabel: resolveChromeExecutable() ? path.basename(resolveChromeExecutable()) : "",
    webMessageCountMirrored: Number(state.messageCountMirrored || 0),
    lastValidatedAt: String(whatsapp.lastValidatedAt || ""),
    lastSyncAt: mode === "web"
      ? (state.lastSyncAt || String(whatsapp.webLastSyncAt || whatsapp.lastSyncAt || ""))
      : String(whatsapp.lastSyncAt || ""),
    message: mode === "web"
      ? (
        currentWebStatus === "initializing"
          ? "WhatsApp Web başlatılıyor."
          :
        currentWebStatus === "session_busy"
          ? "WhatsApp Web oturumu başka bir Chromium sürecinde açık. O süreci kapatabilir veya farklı bir oturum adı kullanabilirsiniz."
          :
        currentWebStatus === "qr_required"
          ? "QR kodunu telefondaki WhatsApp ile tarayın."
          : configured
            ? "WhatsApp Web bağlı; gelen mesajlar eşitlenebilir ve aynı hesaptan mesaj gönderilebilir."
            : "Kişisel WhatsApp hesabını QR ile bağlayın."
      )
      : (configured ? "WhatsApp bağlantısı hazır." : "WhatsApp için erişim belirteci ve telefon numarası kimliği gerekli."),
    error: state.lastError || (currentWebStatus === "session_busy" ? "Bu oturum için stale bir Chromium süreci bulundu." : ""),
  };
}

async function safeSaveConfig(patch) {
  if (!bridgeContext.saveConfig) {
    return;
  }
  try {
    await bridgeContext.saveConfig(patch);
  } catch (error) {
    console.error("[lawcopilot] whatsapp_web_save_config_failed", error);
  }
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

function responseErrorMessage(payload, fallback) {
  return String(payload?.error?.message || payload?.message || payload?.description || fallback);
}

function buildChatRecipient(raw) {
  const text = String(raw || "").trim();
  if (!text) {
    return "";
  }
  if (text.includes("@")) {
    return text;
  }
  const digits = text.replace(/\D+/g, "");
  return digits ? `${digits}@c.us` : "";
}

function normalizeChatLookupText(value) {
  return String(value || "")
    .replace(/[İIı]/g, "i")
    .replace(/[Şş]/g, "s")
    .replace(/[Ğğ]/g, "g")
    .replace(/[Üü]/g, "u")
    .replace(/[Öö]/g, "o")
    .replace(/[Çç]/g, "c")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

async function resolveChatRecipient(raw, conversationRef = "") {
  const directConversationRef = buildChatRecipient(conversationRef);
  if (directConversationRef) {
    return directConversationRef;
  }
  const directRecipient = buildChatRecipient(raw);
  if (directRecipient) {
    return directRecipient;
  }
  const needle = normalizeChatLookupText(raw);
  if (!needle || !client) {
    return "";
  }

  const chats = await client.getChats().catch(() => []);
  let bestMatch = "";
  let bestScore = -1;

  for (const chat of chats) {
    const chatId = String(chat?.id?._serialized || "").trim();
    if (!chatId || chatId === "status@broadcast") {
      continue;
    }
    const contact = await chat.getContact?.().catch(() => null);
    const candidates = [
      chat?.name,
      chat?.formattedTitle,
      chat?.id?.user,
      contact?.name,
      contact?.shortName,
      contact?.pushname,
      contact?.number,
    ];

    for (const candidate of candidates) {
      const normalizedCandidate = normalizeChatLookupText(candidate);
      if (!normalizedCandidate) {
        continue;
      }
      let score = -1;
      if (normalizedCandidate === needle) {
        score = 100;
      } else if (normalizedCandidate.startsWith(needle) || needle.startsWith(normalizedCandidate)) {
        score = 70;
      } else if (normalizedCandidate.includes(needle) || needle.includes(normalizedCandidate)) {
        score = 45;
      }
      if (score > bestScore) {
        bestScore = score;
        bestMatch = chatId;
      }
    }
  }

  return bestMatch;
}

function compactMetadata(raw) {
  try {
    return JSON.parse(JSON.stringify(raw || {}));
  } catch {
    return {};
  }
}

function resolveSavedContactLabel(contact) {
  return String(
    contact?.name
    || contact?.shortName
    || contact?.pushname
    || contact?.number
    || "",
  ).trim();
}

function resolveProfileContactLabel(contact) {
  return String(
    contact?.pushname
    || contact?.shortName
    || contact?.name
    || contact?.number
    || "",
  ).trim();
}

async function resolveContactBySerializedId(raw) {
  const contactId = buildChatRecipient(raw);
  if (!contactId || !client?.getContactById) {
    return null;
  }
  try {
    return await client.getContactById(contactId);
  } catch {
    return null;
  }
}

function appendSavedContactAlias(map, alias, label) {
  const normalizedAlias = normalizeChatLookupText(alias);
  const normalizedLabel = String(label || "").trim();
  if (!normalizedAlias || !normalizedLabel || map.has(normalizedAlias)) {
    return;
  }
  map.set(normalizedAlias, normalizedLabel);
}

async function getSavedContactAliasMap() {
  const now = Date.now();
  if (contactAliasCache.builtAt && now - contactAliasCache.builtAt < CONTACT_ALIAS_CACHE_TTL_MS) {
    return contactAliasCache.map;
  }
  const map = new Map();
  const chats = await client?.getChats?.().catch(() => []) || [];
  for (const chat of chats) {
    const chatId = String(chat?.id?._serialized || "").trim();
    if (!chatId || chatId === "status@broadcast" || chatId.endsWith("@g.us")) {
      continue;
    }
    const chatContact = await chat.getContact?.().catch(() => null);
    const savedLabel = String(
      chat?.name
      || chat?.formattedTitle
      || resolveSavedContactLabel(chatContact)
      || resolveProfileContactLabel(chatContact)
      || "",
    ).trim();
    if (!savedLabel) {
      continue;
    }
    for (const alias of [
      chat?.name,
      chat?.formattedTitle,
      chat?.id?.user,
      chatId,
      chatContact?.name,
      chatContact?.pushname,
      chatContact?.shortName,
      chatContact?.number,
      chatContact?.id?._serialized,
      chatContact?.id?.user,
    ]) {
      appendSavedContactAlias(map, alias, savedLabel);
    }
  }
  contactAliasCache.builtAt = now;
  contactAliasCache.map = map;
  return map;
}

async function resolveAliasedSavedLabel(...values) {
  const aliasMap = await getSavedContactAliasMap();
  for (const value of values) {
    const normalizedValue = normalizeChatLookupText(value);
    if (!normalizedValue) {
      continue;
    }
    const savedLabel = aliasMap.get(normalizedValue);
    if (savedLabel) {
      return savedLabel;
    }
  }
  return "";
}

async function upsertMessages(messages) {
  const runtimeInfo = await bridgeContext.getRuntimeInfo?.();
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const config = bridgeContext.loadConfig?.() || {};
  const status = baseStatus(config);
  const syncPayloadBase = {
    account_label: status.accountLabel,
    phone_number_id: status.phoneNumberId || "",
    display_phone_number: status.displayPhoneNumber || "",
    verified_name: status.accountLabel || "",
    synced_at: nowIso(),
    note: "WhatsApp Web yerel oturumu üzerinden senkronlandı.",
  };
  const postChunk = async (chunk) => {
    const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/whatsapp/sync`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${runtimeInfo.sessionToken}`,
      },
      body: JSON.stringify({
        ...syncPayloadBase,
        messages: chunk,
        contacts: [],
      }),
    });
    const payload = await parseJson(response);
    if (!response.ok) {
      throw new Error(responseErrorMessage(payload, "WhatsApp mesajları eşitlenemedi."));
    }
    return payload;
  };
  const chunks = [];
  for (let index = 0; index < messages.length; index += DEFAULT_SYNC_BATCH_SIZE) {
    chunks.push(messages.slice(index, index + DEFAULT_SYNC_BATCH_SIZE));
  }
  if (chunks.length === 0) {
    await postChunk([]);
  } else {
    for (const chunk of chunks) {
      await postChunk(chunk);
    }
  }
  state.messageCountMirrored += messages.length;
  state.lastSyncAt = nowIso();
  await safeSaveConfig({
    whatsapp: {
      enabled: true,
      mode: "web",
      webStatus: state.status,
      webAccountLabel: state.accountLabel,
      webLastSyncAt: state.lastSyncAt,
      lastSyncAt: state.lastSyncAt,
      validationStatus: state.status === "ready" ? "valid" : "pending",
    },
  });
  return {
    ok: true,
    message: `WhatsApp Web üzerinden ${messages.length} mesaj eşitlendi.`,
    patch: {
      whatsapp: {
        webLastSyncAt: state.lastSyncAt,
        lastSyncAt: state.lastSyncAt,
      },
    },
  };
}

function extractWhatsAppDigits(raw) {
  const text = String(raw || "").trim().toLowerCase();
  if (!text) {
    return "";
  }
  if (text.includes("@")) {
    const [local, domain] = text.split("@", 2);
    if (domain === "c.us" || domain === "s.whatsapp.net") {
      const digits = String(local || "").replace(/\D+/g, "");
      return digits.length >= 7 && digits.length <= 15 ? digits : "";
    }
    return "";
  }
  if (!/^\+?[\d\s().-]{7,24}$/.test(text)) {
    return "";
  }
  const digits = text.replace(/\D+/g, "");
  if (digits.length < 7 || digits.length > 15) {
    return "";
  }
  if (text.startsWith("+") || text.startsWith("00") || /[ ()-]/.test(text)) {
    return digits;
  }
  return digits.length <= 13 ? digits : "";
}

async function buildChatContactSnapshot(chat) {
  const conversationRef = String(chat?.id?._serialized || "").trim();
  if (!conversationRef || conversationRef === "status@broadcast") {
    return null;
  }
  const isGroup = Boolean(chat?.isGroup || conversationRef.endsWith("@g.us"));
  const contact = !isGroup ? await chat.getContact?.().catch(() => null) : null;
  const chatName = String(chat?.name || chat?.formattedTitle || "").trim();
  const savedLabel = String(
    chatName
    || await resolveAliasedSavedLabel(
      chatName,
      resolveSavedContactLabel(contact),
      resolveProfileContactLabel(contact),
      chat?.id?._serialized,
      chat?.id?.user,
      contact?.number,
      contact?.id?._serialized,
      contact?.id?.user,
    )
    || resolveSavedContactLabel(contact)
    || resolveProfileContactLabel(contact)
  ).trim();
  const profileName = String(resolveProfileContactLabel(contact)).trim();
  const displayName = isGroup ? (chatName || conversationRef) : (savedLabel || profileName || conversationRef);
  const phoneNumber = isGroup
    ? ""
    : (
      extractWhatsAppDigits(contact?.number)
      || extractWhatsAppDigits(contact?.id?.user)
      || extractWhatsAppDigits(contact?.id?._serialized)
      || extractWhatsAppDigits(conversationRef)
    );
  const lastSeenAt = Number(chat?.timestamp || 0) > 0 ? new Date(Number(chat.timestamp) * 1000).toISOString() : "";
  return {
    provider: "whatsapp_web",
    conversation_ref: conversationRef,
    display_name: displayName,
    profile_name: profileName || "",
    phone_number: phoneNumber || "",
    is_group: isGroup,
    group_name: isGroup ? chatName || displayName : "",
    last_seen_at: lastSeenAt || null,
    metadata: compactMetadata({
      chat_name: chatName,
      contact_name: !isGroup ? displayName : "",
      profile_name: profileName,
      is_group: isGroup,
    }),
  };
}

async function upsertWhatsAppSync(messages, contacts = []) {
  const runtimeInfo = await bridgeContext.getRuntimeInfo?.();
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const config = bridgeContext.loadConfig?.() || {};
  const status = baseStatus(config);
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/whatsapp/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: status.accountLabel,
      phone_number_id: status.phoneNumberId || "",
      display_phone_number: status.displayPhoneNumber || "",
      verified_name: status.accountLabel || "",
      synced_at: nowIso(),
      note: "WhatsApp Web yerel oturumu üzerinden senkronlandı.",
      messages,
      contacts,
    }),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(responseErrorMessage(payload, "WhatsApp verileri eşitlenemedi."));
  }
  state.messageCountMirrored += messages.length;
  state.lastSyncAt = nowIso();
  await safeSaveConfig({
    whatsapp: {
      enabled: true,
      mode: "web",
      webStatus: state.status,
      webAccountLabel: state.accountLabel,
      webLastSyncAt: state.lastSyncAt,
      lastSyncAt: state.lastSyncAt,
      validationStatus: state.status === "ready" ? "valid" : "pending",
    },
  });
  return {
    ok: true,
    message: `WhatsApp Web üzerinden ${messages.length} mesaj ve ${contacts.length} sohbet eşitlendi.`,
    patch: {
      whatsapp: {
        webLastSyncAt: state.lastSyncAt,
        lastSyncAt: state.lastSyncAt,
      },
    },
  };
}

async function normalizeMessage(message) {
  const messageRef = String(message?.id?._serialized || "").trim();
  if (!messageRef || seenMessageRefs.has(messageRef)) {
    return null;
  }
  const chat = await message.getChat().catch(() => null);
  const conversationRef = String(chat?.id?._serialized || message?.from || message?.to || messageRef).trim();
  if (!conversationRef || conversationRef === "status@broadcast") {
    return null;
  }
  const body = String(message?.body || message?.caption || "").trim();
  if (!body) {
    return null;
  }
  const sentAt = message?.timestamp ? new Date(Number(message.timestamp) * 1000).toISOString() : nowIso();
  const direction = message?.fromMe ? "outbound" : "inbound";
  const chatName = String(chat?.name || "").trim();
  const isGroup = Boolean(chat?.isGroup || conversationRef.endsWith("@g.us"));
  const participantRef = String(message?.author || message?.participant || "").trim();
  const primaryContact = await message.getContact().catch(() => null);
  const chatContact = !isGroup ? await chat?.getContact?.().catch(() => null) : null;
  const participantContact = isGroup ? await resolveContactBySerializedId(participantRef) : null;
  const savedDirectLabel = String(
    chatName
    || await resolveAliasedSavedLabel(
      chatName,
      resolveSavedContactLabel(chatContact || primaryContact),
      resolveProfileContactLabel(chatContact || primaryContact),
      chat?.id?._serialized,
      chat?.id?.user,
    )
    || resolveSavedContactLabel(chatContact || primaryContact)
  ).trim();
  const profileDirectLabel = resolveProfileContactLabel(chatContact || primaryContact);
  const savedParticipantLabel = String(
    await resolveAliasedSavedLabel(
      resolveSavedContactLabel(participantContact || primaryContact),
      resolveProfileContactLabel(participantContact || primaryContact),
      message?.notifyName,
      participantRef,
      participantContact?.number,
      participantContact?.id?._serialized,
      participantContact?.id?.user,
      primaryContact?.name,
      primaryContact?.pushname,
      primaryContact?.shortName,
    )
    || resolveSavedContactLabel(participantContact || primaryContact)
  ).trim();
  const profileParticipantLabel = resolveProfileContactLabel(participantContact || primaryContact);
  const contactName = String(
    isGroup
      ? (savedParticipantLabel || profileParticipantLabel || message?.notifyName || "")
      : (chatName || savedDirectLabel || profileDirectLabel || message?.notifyName || "")
  ).trim();
  const profileName = String(
    isGroup
      ? (profileParticipantLabel || savedParticipantLabel || "")
      : (profileDirectLabel || savedDirectLabel || "")
  ).trim();
  const preferredDirectLabel = !isGroup ? String(chatName || savedDirectLabel || profileDirectLabel || "").trim() : "";
  const sender = direction === "outbound"
    ? (state.accountLabel || state.currentUser || "Siz")
    : (contactName || chatName || String(message?.from || conversationRef));
  const recipient = direction === "outbound"
    ? (chatName || contactName || String(message?.to || conversationRef))
    : (state.accountLabel || state.currentUser || "Siz");
  const normalized = {
    provider: "whatsapp_web",
    conversation_ref: conversationRef,
    message_ref: messageRef,
    sender,
    recipient,
    body,
    direction,
    sent_at: sentAt,
    reply_needed: direction === "inbound",
    metadata: compactMetadata({
      from: message?.from || "",
      to: message?.to || "",
      fromMe: Boolean(message?.fromMe),
      type: String(message?.type || ""),
      timestamp: Number(message?.timestamp || 0),
      chat_name: chatName,
      group_name: isGroup ? chatName : "",
      is_group: isGroup,
      contact_name: preferredDirectLabel || contactName,
      profile_name: profileName,
      author: participantRef,
      participant: participantRef,
      has_media: Boolean(message?.hasMedia),
    }),
  };
  seenMessageRefs.add(messageRef);
  return normalized;
}

async function syncHistory() {
  if (!client) {
    throw new Error("WhatsApp Web istemcisi hazır değil.");
  }
  if (lastSyncPromise) {
    return lastSyncPromise;
  }
  lastSyncPromise = (async () => {
    const chats = await client.getChats();
    const sortedChats = chats
      .filter((chat) => String(chat?.id?._serialized || "") !== "status@broadcast")
      .sort((left, right) => Number(right?.timestamp || 0) - Number(left?.timestamp || 0))
    const selectedChats = sortedChats
      .slice(0, Math.max(1, DEFAULT_GRAPH_SYNC_MAX_CHATS));
    const selectedContacts = sortedChats.slice(0, Math.max(50, DEFAULT_CONTACT_SYNC_MAX_CHATS));
    const messages = [];
    for (const chat of selectedChats) {
      const history = await chat.fetchMessages({ limit: Math.max(1, DEFAULT_GRAPH_SYNC_MESSAGES_PER_CHAT) }).catch(() => []);
      for (const item of history) {
        const normalized = await normalizeMessage(item);
        if (normalized) {
          messages.push(normalized);
        }
      }
    }
    const contacts = [];
    for (const chat of selectedContacts) {
      const snapshot = await buildChatContactSnapshot(chat);
      if (snapshot) {
        contacts.push(snapshot);
      }
    }
    if (!messages.length && !contacts.length) {
      return upsertWhatsAppSync([], []);
    }
    return upsertWhatsAppSync(messages, contacts);
  })()
    .finally(() => {
      lastSyncPromise = null;
    });
  return lastSyncPromise;
}

async function destroyClient({ logout = false, removeAuth = false } = {}) {
  const currentClient = client;
  client = null;
  initPromise = null;
  contactAliasCache.builtAt = 0;
  contactAliasCache.map = new Map();
  if (currentClient) {
    try {
      if (logout) {
        await currentClient.logout().catch(() => null);
      }
      await currentClient.destroy().catch(() => null);
    } catch {
      // ignore teardown failures
    }
  }
  if (removeAuth) {
    const authDir = path.join(resolveAuthDataPath(), `session-${clientSessionName || "default"}`);
    try {
      fs.rmSync(authDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  }
}

function attachEventHandlers(nextClient) {
  nextClient.on("qr", async (qr) => {
    state.status = "qr_required";
    state.qrText = qr;
    state.qrDataUrl = await QRCode.toDataURL(qr, { margin: 1, width: 320 }).catch(() => "");
    state.lastError = "";
    await safeSaveConfig({
      whatsapp: {
        enabled: true,
        mode: "web",
        webStatus: "qr_required",
        webSessionName: state.webSessionName,
        validationStatus: "pending",
      },
    });
  });

  nextClient.on("authenticated", async () => {
    state.status = "authenticated";
    state.qrText = "";
    state.qrDataUrl = "";
    state.lastError = "";
    await safeSaveConfig({
      whatsapp: {
        enabled: true,
        mode: "web",
        webStatus: "authenticated",
        webSessionName: state.webSessionName,
        configuredAt: nowIso(),
        validationStatus: "pending",
      },
    });
  });

  nextClient.on("ready", async () => {
    state.status = "ready";
    state.qrText = "";
    state.qrDataUrl = "";
    state.lastError = "";
    state.lastReadyAt = nowIso();
    state.accountLabel = buildSelfLabel(nextClient.info);
    state.currentUser = String(nextClient.info?.wid?._serialized || "").trim();
    await safeSaveConfig({
      whatsapp: {
        enabled: true,
        mode: "web",
        webStatus: "ready",
        webSessionName: state.webSessionName,
        webAccountLabel: state.accountLabel,
        webLastReadyAt: state.lastReadyAt,
        configuredAt: nowIso(),
        validationStatus: "valid",
      },
    });
    try {
      await syncHistory();
    } catch (error) {
      console.error("[lawcopilot] whatsapp_web_initial_sync_failed", error);
      state.lastError = String(error?.message || error || "");
    }
  });

  nextClient.on("auth_failure", async (message) => {
    state.status = "auth_failure";
    state.lastError = String(message || "WhatsApp oturumu doğrulanamadı.");
    await safeSaveConfig({
      whatsapp: {
        enabled: true,
        mode: "web",
        webStatus: "auth_failure",
        validationStatus: "invalid",
      },
    });
  });

  nextClient.on("disconnected", async (reason) => {
    state.status = "disconnected";
    state.lastError = String(reason || "WhatsApp bağlantısı kesildi.");
    state.qrText = "";
    state.qrDataUrl = "";
    await safeSaveConfig({
      whatsapp: {
        enabled: false,
        mode: "web",
        webStatus: "disconnected",
        validationStatus: "pending",
      },
    });
  });

  nextClient.on("message", async (message) => {
    const normalized = await normalizeMessage(message);
    if (!normalized) {
      return;
    }
    try {
      await upsertMessages([normalized]);
    } catch (error) {
      console.error("[lawcopilot] whatsapp_web_live_sync_failed", error);
    }
  });

  nextClient.on("message_create", async (message) => {
    if (!message?.fromMe) {
      return;
    }
    const normalized = await normalizeMessage(message);
    if (!normalized) {
      return;
    }
    try {
      await upsertMessages([normalized]);
    } catch (error) {
      console.error("[lawcopilot] whatsapp_web_outbound_sync_failed", error);
    }
  });
}

async function ensureClient(config) {
  if (client && state.status !== "disconnected" && state.status !== "auth_failure" && clientSessionName === resolveSessionName(config)) {
    return client;
  }
  if (initPromise) {
    return initPromise;
  }
  const busyProcesses = sessionConflictProcesses(config);
  if (busyProcesses.length) {
    const busyError = createSessionBusyError(config);
    state.status = "session_busy";
    state.lastError = busyError.message;
    state.webSessionName = resolveSessionName(config);
    clientSessionName = state.webSessionName;
    void safeSaveConfig({
      whatsapp: {
        enabled: Boolean(config?.whatsapp?.enabled),
        mode: "web",
        webStatus: "session_busy",
        webSessionName: state.webSessionName,
      },
    });
    throw busyError;
  }
  state.webSessionName = resolveSessionName(config);
  clientSessionName = state.webSessionName;
  initPromise = (async () => {
    await destroyClient();
    state.status = "initializing";
    state.lastError = "";
    const executablePath = resolveChromeExecutable();
    const nextClient = new Client({
      authStrategy: new LocalAuth({
        clientId: state.webSessionName,
        dataPath: resolveAuthDataPath(),
      }),
      puppeteer: {
        headless: true,
        executablePath: executablePath || undefined,
        args: [
          "--no-sandbox",
          "--disable-setuid-sandbox",
          "--disable-dev-shm-usage",
          "--disable-gpu",
          "--no-first-run",
          "--no-default-browser-check",
        ],
      },
    });
    attachEventHandlers(nextClient);
    client = nextClient;
    try {
      await nextClient.initialize();
    } catch (error) {
      if (isSessionConflictError(error)) {
        state.status = "session_busy";
        state.lastError = createSessionBusyError(config).message;
        void safeSaveConfig({
          whatsapp: {
            enabled: Boolean(config?.whatsapp?.enabled),
            mode: "web",
            webStatus: "session_busy",
            webSessionName: state.webSessionName,
          },
        });
      }
      throw error;
    }
    return nextClient;
  })()
    .finally(() => {
      initPromise = null;
    });
  return initPromise;
}

async function startWhatsAppWebLink(config) {
  const mode = resolveWhatsAppMode(config);
  if (mode !== "web") {
    throw new Error("Bu işlem yalnız WhatsApp Web modunda kullanılabilir.");
  }
  await ensureClient(config);
  return baseStatus(config);
}

async function syncWhatsAppWebData(config) {
  const mode = resolveWhatsAppMode(config);
  if (mode !== "web") {
    throw new Error("Bu işlem yalnız WhatsApp Web modunda kullanılabilir.");
  }
  await ensureClient(config);
  if (state.status !== "ready") {
    return {
      ok: false,
      message: state.status === "qr_required"
        ? "Önce QR kodunu tarayıp WhatsApp Web oturumunu hazır hale getirin."
        : "WhatsApp Web henüz hazır değil.",
      patch: null,
    };
  }
  return syncHistory();
}

async function sendWhatsAppWebMessage(config, payload = {}) {
  const mode = resolveWhatsAppMode(config);
  if (mode !== "web") {
    throw new Error("Bu işlem yalnız WhatsApp Web modunda kullanılabilir.");
  }
  await ensureClient(config);
  if (!client || state.status !== "ready") {
    throw new Error("WhatsApp Web henüz hazır değil. Önce QR ile bağlantıyı tamamlayın.");
  }
  const to = await resolveChatRecipient(
    payload.to || payload.recipient || "",
    payload.conversationRef || payload.conversation_ref || "",
  );
  const text = String(payload.text || payload.body || "").trim();
  if (!to || !text) {
    throw new Error("WhatsApp gönderimi için hedef sohbet ve mesaj gerekli.");
  }
  const sentMessage = await client.sendMessage(to, text);
  const normalized = await normalizeMessage(sentMessage);
  if (normalized) {
    await upsertMessages([normalized]);
  }
  return {
    ok: true,
    message: "WhatsApp Web mesajı gönderildi.",
    externalMessageId: String(sentMessage?.id?._serialized || ""),
    recipient: to,
  };
}

async function disconnectWhatsAppWeb(config) {
  const mode = resolveWhatsAppMode(config);
  if (mode !== "web") {
    return {
      ok: true,
      message: "WhatsApp Web zaten aktif değil.",
    };
  }
  await destroyClient({ logout: true, removeAuth: true });
  state.status = "idle";
  state.qrText = "";
  state.qrDataUrl = "";
  state.lastError = "";
  state.accountLabel = "";
  state.currentUser = "";
  state.lastReadyAt = "";
  state.lastSyncAt = "";
  state.messageCountMirrored = 0;
  contactAliasCache.builtAt = 0;
  contactAliasCache.map = new Map();
  const sessionName = resolveSessionName(config);
  await safeSaveConfig({
    whatsapp: {
      enabled: false,
      mode: "web",
      webStatus: "idle",
      webSessionName: sessionName,
      webAccountLabel: "",
      webLastReadyAt: "",
      webLastSyncAt: "",
      validationStatus: "pending",
      lastSyncAt: "",
    },
  });
  return {
    ok: true,
    message: "WhatsApp Web oturumu kaldırıldı.",
  };
}

function shouldAutoStart(config) {
  const whatsapp = config?.whatsapp || {};
  return resolveWhatsAppMode(config) === "web" && Boolean(whatsapp.enabled) && isReadyStatus(whatsapp.webStatus || whatsapp.validationStatus || "");
}

function setWhatsAppWebBridgeContext(nextContext = {}) {
  bridgeContext = {
    ...bridgeContext,
    ...nextContext,
  };
}

function getWhatsAppWebStatus(config) {
  if (shouldAutoStart(config) && !client && !initPromise && !sessionConflictProcesses(config).length) {
    startWhatsAppWebLink(config).catch((error) => {
      state.lastError = String(error?.message || error || "");
    });
  }
  return baseStatus(config);
}

module.exports = {
  disconnectWhatsAppWeb,
  getWhatsAppWebStatus,
  sendWhatsAppWebMessage,
  setWhatsAppWebBridgeContext,
  startWhatsAppWebLink,
  syncWhatsAppWebData,
  __internal: {
    createSessionBusyError,
    isSessionConflictError,
    resolveSessionUserDataDir,
    sessionConflictProcesses,
  },
};
