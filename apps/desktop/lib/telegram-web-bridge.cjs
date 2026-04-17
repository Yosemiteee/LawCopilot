const { BrowserWindow, session, shell } = require("electron");

let bridgeContext = {
  loadConfig: () => ({}),
  saveConfig: async () => ({}),
  getRuntimeInfo: async () => null,
};

let webWindow = null;
let statusPollTimer = null;

const state = {
  status: "idle",
  lastError: "",
  accountLabel: "",
  currentUser: "",
  webSessionName: "default",
  lastReadyAt: "",
  lastSyncAt: "",
  messageCountMirrored: 0,
};

const TELEGRAM_WEB_URL = "https://web.telegram.org/k/";
const STATUS_POLL_MS = Number(process.env.LAWCOPILOT_TELEGRAM_WEB_STATUS_POLL_MS || 2500);
const SYNC_MAX_CHATS = Math.max(1, Number(process.env.LAWCOPILOT_TELEGRAM_WEB_MAX_CHATS || 24));
const SYNC_MESSAGES_PER_CHAT = Math.max(1, Number(process.env.LAWCOPILOT_TELEGRAM_WEB_MESSAGES_PER_CHAT || 10));
const SYNC_MAX_TOTAL_MESSAGES = Math.max(1, Number(process.env.LAWCOPILOT_TELEGRAM_WEB_MAX_TOTAL_MESSAGES || 240));
const SYNC_BATCH_SIZE = 100;

function nowIso() {
  return new Date().toISOString();
}

function normalizeTelegramMode(value, fallback = "web") {
  const mode = String(value || fallback || "").trim().toLowerCase();
  if (mode === "bot" || mode === "web") {
    return mode;
  }
  return fallback;
}

function resolveTelegramMode(config) {
  const telegram = config?.telegram || {};
  if (String(telegram.mode || "").trim()) {
    return normalizeTelegramMode(telegram.mode, "web");
  }
  if (telegram.botToken || telegram.allowedUserId) {
    return "bot";
  }
  return "web";
}

function resolveSessionName(config) {
  const raw = String(config?.telegram?.webSessionName || "default").trim();
  return raw.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-+|-+$/g, "") || "default";
}

function resolvePartition(config) {
  return `persist:lawcopilot-telegram-web-${resolveSessionName(config)}`;
}

function stopStatusPolling() {
  if (statusPollTimer) {
    clearInterval(statusPollTimer);
    statusPollTimer = null;
  }
}

async function safeSaveConfig(patch) {
  if (!bridgeContext.saveConfig) {
    return;
  }
  try {
    await bridgeContext.saveConfig(patch);
  } catch (error) {
    console.error("[lawcopilot] telegram_web_save_config_failed", error);
  }
}

function baseStatus(config) {
  const telegram = config?.telegram || {};
  const mode = resolveTelegramMode(config);
  const currentStatus = String(state.status || telegram.webStatus || "idle");
  const configured = mode === "web"
    ? Boolean((currentStatus === "ready" || telegram.webStatus === "ready") && (state.accountLabel || telegram.webAccountLabel))
    : Boolean(telegram.enabled && telegram.botToken && telegram.allowedUserId);
  return {
    provider: "telegram",
    mode,
    configured,
    enabled: Boolean(telegram.enabled),
    accountLabel: mode === "web"
      ? (state.accountLabel || String(telegram.webAccountLabel || telegram.botUsername || "Telegram Web hesabı"))
      : String(telegram.botUsername || "Telegram botu"),
    validationStatus: mode === "web"
      ? (configured ? "valid" : String(telegram.validationStatus || "pending"))
      : String(telegram.validationStatus || "pending"),
    botUsername: String(telegram.botUsername || ""),
    allowedUserId: String(telegram.allowedUserId || ""),
    webStatus: currentStatus,
    webSessionName: state.webSessionName || resolveSessionName(config),
    webAccountLabel: state.accountLabel || String(telegram.webAccountLabel || ""),
    webCurrentUser: state.currentUser || "",
    webLastReadyAt: state.lastReadyAt || String(telegram.webLastReadyAt || ""),
    webLastSyncAt: state.lastSyncAt || String(telegram.webLastSyncAt || ""),
    webMessageCountMirrored: Number(state.messageCountMirrored || 0),
    lastSyncAt: mode === "web"
      ? (state.lastSyncAt || String(telegram.webLastSyncAt || ""))
      : "",
    message: mode === "web"
      ? (
        currentStatus === "ready"
          ? "Telegram Web bağlı; mevcut kişisel sohbetler eşitlenebilir ve mevcut sohbetlere yanıt gönderilebilir."
          : currentStatus === "login_required"
            ? "Telegram Web oturumunu açıp giriş yapın."
            : currentStatus === "loading"
              ? "Telegram Web açılıyor."
              : "Telegram kişisel hesabını web oturumu ile bağlayın."
      )
      : "Telegram botu bağlı.",
    error: state.lastError || "",
  };
}

async function runInWindow(window, fn, ...args) {
  if (!window || window.isDestroyed()) {
    throw new Error("telegram_web_window_missing");
  }
  const payload = JSON.stringify(args ?? []);
  const script = `(${fn.toString()})(...${payload})`;
  return window.webContents.executeJavaScript(script, true);
}

async function detectTelegramState(window) {
  return runInWindow(window, () => {
    const text = String(document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const title = String(document.title || "").trim();
    const visibleComposer = Array.from(document.querySelectorAll('[contenteditable="true"], textarea'))
      .filter((item) => item instanceof HTMLElement && item.offsetParent !== null);
    const hasChatList = Boolean(
      document.querySelector("[data-peer-id]")
      || document.querySelector('[role="listitem"]')
      || document.querySelector(".chatlist")
    );
    const hasQr = Boolean(document.querySelector("canvas")) && /qr|scan|tara|telegram web/i.test(`${text} ${title}`.toLowerCase());
    const hasLoginForm = Boolean(document.querySelector('input[type="tel"], input[name="phone_number"]'));
    const ready = Boolean(hasChatList || visibleComposer.length);
    const accountLabel = title
      .replace(/\(\d+\)\s*/g, "")
      .replace(/\s*\|\s*Telegram.*$/i, "")
      .trim();
    return {
      ready,
      hasQr,
      hasLoginForm,
      accountLabel,
      title,
    };
  });
}

function buildWindow(config, { show = false } = {}) {
  if (webWindow && !webWindow.isDestroyed()) {
    if (show) {
      webWindow.show();
      webWindow.focus();
    }
    return webWindow;
  }
  webWindow = new BrowserWindow({
    width: 1240,
    height: 920,
    minWidth: 980,
    minHeight: 720,
    title: "Telegram Web bağlantısı",
    autoHideMenuBar: true,
    backgroundColor: "#102123",
    show,
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      partition: resolvePartition(config),
    },
  });
  webWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/i.test(String(url || ""))) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });
  webWindow.on("closed", () => {
    webWindow = null;
    stopStatusPolling();
  });
  return webWindow;
}

async function ensureWindow(config, { show = false } = {}) {
  const window = buildWindow(config, { show });
  if (!window.webContents.getURL()) {
    state.status = "loading";
    await window.loadURL(TELEGRAM_WEB_URL);
  } else if (!window.webContents.getURL().startsWith("https://web.telegram.org")) {
    state.status = "loading";
    await window.loadURL(TELEGRAM_WEB_URL);
  }
  return window;
}

async function refreshStatus(config) {
  if (!webWindow || webWindow.isDestroyed()) {
    return baseStatus(config);
  }
  try {
    const snapshot = await detectTelegramState(webWindow);
    if (snapshot.ready) {
      state.status = "ready";
      state.lastError = "";
      state.lastReadyAt = state.lastReadyAt || nowIso();
      state.accountLabel = snapshot.accountLabel || state.accountLabel || "Telegram Web hesabı";
      state.currentUser = snapshot.accountLabel || state.currentUser || "";
      await safeSaveConfig({
        telegram: {
          enabled: true,
          mode: "web",
          webStatus: "ready",
          webAccountLabel: state.accountLabel,
          webLastReadyAt: state.lastReadyAt,
          validationStatus: "valid",
          lastValidatedAt: nowIso(),
        },
      });
    } else if (snapshot.hasQr || snapshot.hasLoginForm) {
      state.status = "login_required";
      state.lastError = "";
      await safeSaveConfig({
        telegram: {
          enabled: true,
          mode: "web",
          webStatus: "login_required",
          validationStatus: "pending",
        },
      });
    } else {
      state.status = "loading";
    }
  } catch (error) {
    state.status = "error";
    state.lastError = String(error?.message || error || "telegram_web_status_failed");
  }
  return baseStatus(config);
}

function startStatusPolling(config) {
  stopStatusPolling();
  statusPollTimer = setInterval(() => {
    void refreshStatus(config);
  }, STATUS_POLL_MS);
}

async function startTelegramWebLink(config) {
  state.webSessionName = resolveSessionName(config);
  const window = await ensureWindow(config, { show: true });
  startStatusPolling(config);
  const status = await refreshStatus(config);
  if (!window.isVisible()) {
    window.show();
  }
  window.focus();
  return status;
}

async function scrapeTelegramConversationMessages(
  window,
  maxChats = SYNC_MAX_CHATS,
  messagesPerChat = SYNC_MESSAGES_PER_CHAT,
  maxTotalMessages = SYNC_MAX_TOTAL_MESSAGES,
) {
  return runInWindow(window, async (chatLimit, perChatLimit, totalLimit) => {
    const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const normalizeLower = (value) => normalize(value).toLowerCase();
    const isRenderable = (node) => {
      if (!(node instanceof HTMLElement)) {
        return false;
      }
      const style = window.getComputedStyle(node);
      return style.display !== "none" && style.visibility !== "hidden";
    };
    const isTimestampOnly = (value) => /^(\d{1,2}:\d{2})(\s?[ap]m)?$/i.test(String(value || "").trim());
    const TIMESTAMP_TAIL_PATTERN = /\s+(?:mon|tue|wed|thu|fri|sat|sun|pzt|sal|car|çar|per|cum|cmt|paz|today|yesterday|bugun|bugün|dun|dün|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)(?:\s+\d{1,2})?(?:\s+[a-z0-9._-]{1,4})?$/i;
    const PREVIEW_SPLIT_PATTERN = /\s+(?:today|yesterday|bugun|bugün|dun|dün|mon|tue|wed|thu|fri|sat|sun|pzt|sal|car|çar|per|cum|cmt|paz|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+\d{1,2}(?:\s+[a-z0-9._-]{1,4})?\s*$/i;
    const cleanDecoratedText = (value, hints = {}) => {
      let text = normalize(String(value || "").replace(/[\uE000-\uF8FF]/g, " "));
      if (!text) {
        return "";
      }
      text = text.replace(/\s*[•·]\s*/g, " ");
      text = text.replace(/\s*…\s*/g, " ").trim();
      text = text.replace(TIMESTAMP_TAIL_PATTERN, "").trim();
      const authorHint = normalize(String(hints.author || ""));
      const chatHint = normalize(String(hints.chatName || ""));
      if (authorHint && normalizeLower(text).startsWith(`${normalizeLower(authorHint)} `)) {
        text = normalize(text.slice(authorHint.length));
      }
      if (chatHint && normalizeLower(text).endsWith(` ${normalizeLower(chatHint)}`)) {
        text = normalize(text.slice(0, Math.max(0, text.length - chatHint.length)));
      }
      text = text.replace(TIMESTAMP_TAIL_PATTERN, "").trim();
      return normalize(text);
    };
    const splitPreviewRow = (value) => {
      const raw = normalize(String(value || "").replace(/[\uE000-\uF8FF]/g, " "));
      if (!raw) {
        return { label: "", preview: "" };
      }
      const lines = raw.split("\n").map((line) => normalize(line)).filter(Boolean);
      if (lines.length >= 2) {
        return {
          label: cleanDecoratedText(lines[0]),
          preview: cleanDecoratedText(lines.slice(1).join(" ")),
        };
      }
      const compact = raw.replace(/\s*…\s*/g, " ").trim();
      const match = compact.match(/^(.*?)(?:\s+([^\s].*?)\s+(?:today|yesterday|bugun|bugün|dun|dün|mon|tue|wed|thu|fri|sat|sun|pzt|sal|car|çar|per|cum|cmt|paz|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+\d{1,2}(?:\s+[a-z0-9._-]{1,4})?)$/i);
      if (match) {
        const beforeDate = cleanDecoratedText(match[1]);
        const trailingName = cleanDecoratedText(match[2]);
        if (trailingName && beforeDate) {
          return { label: trailingName, preview: beforeDate };
        }
      }
      const dateCut = compact.replace(PREVIEW_SPLIT_PATTERN, "").trim();
      return { label: cleanDecoratedText(dateCut), preview: "" };
    };
    const hashText = (value) => {
      let hash = 0;
      const text = String(value || "");
      for (let index = 0; index < text.length; index += 1) {
        hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
      }
      return Math.abs(hash);
    };
    const chatItemSelectors = [
      ".chatlist-chat[data-peer-id]",
      ".chatlist .chatlist-chat",
      ".chatlist-container .chatlist-chat",
      "#chatlist-container .chatlist-chat",
      "[role='listitem'][data-peer-id]",
      ".chatlist [data-peer-id]",
      ".chatlist-container [data-peer-id]",
      "#chatlist-container [data-peer-id]",
    ].join(", ");
    const bubbleSelectors = [
      ".bubbles .bubble[data-mid]",
      ".bubbles-inner .bubble[data-mid]",
      ".bubble[data-mid]",
    ].join(", ");
    const composerSelectors = [
      ".input-message-input[contenteditable='true']",
      "[contenteditable='true'].input-message-input",
      "[contenteditable='true'][role='textbox']",
      "[contenteditable='true']",
      "textarea",
    ].join(", ");
    const collectChatCandidates = () => {
      const rows = [];
      const seen = new Set();
      const rawCandidates = Array.from(document.querySelectorAll(chatItemSelectors));
      for (const candidate of rawCandidates) {
        if (!isRenderable(candidate)) {
          continue;
        }
        const row = candidate.closest(".chatlist-chat[data-peer-id], .chatlist-chat, [role='listitem'][data-peer-id]") || candidate;
        if (!isRenderable(row)) {
          continue;
        }
        if (row.closest(".bubbles, .topbar, .chat-topbar, .chat-info")) {
          continue;
        }
        const peerId = normalize(
          row.getAttribute("data-peer-id")
          || candidate.getAttribute("data-peer-id")
          || row.getAttribute("href")
          || candidate.getAttribute("href")
          || "",
        );
        const fullText = normalize(row.textContent || row.innerText || "");
        const lines = fullText.split("\n").map((line) => normalize(line)).filter(Boolean);
        const titleNode = row.querySelector(".dialog-title .peer-title, .user-title .peer-title, .dialog-title .user-title, .user-title, .peer-title");
        const subtitleNode = row.querySelector(".dialog-subtitle .dialog-subtitle-span-last, .dialog-subtitle .dialog-subtitle-span, .dialog-subtitle, .last-message, .user-subtitle, .preview");
        const parsedFallback = splitPreviewRow(lines.join("\n"));
        const label = cleanDecoratedText(
          titleNode?.textContent
          || parsedFallback.label
          || lines[0]
          || peerId,
        );
        const preview = cleanDecoratedText(
          subtitleNode?.textContent
          || parsedFallback.preview
          || lines.slice(1).join(" ")
          || "",
          { chatName: label },
        );
        const uniqueKey = `${peerId}:${label}`;
        if (!label || !peerId || seen.has(uniqueKey)) {
          continue;
        }
        seen.add(uniqueKey);
        rows.push({
          row,
          peerId,
          label,
          preview,
        });
        if (rows.length >= chatLimit) {
          break;
        }
      }
      return rows;
    };
    const readActiveConversation = (fallbackPeerId, fallbackLabel) => {
      const activeTitle = Array.from(
        document.querySelectorAll(".topbar .chat-info .peer-title[data-peer-id], .topbar .chat-info .peer-title, .chat-topbar .chat-info .peer-title, .chat-info .peer-title[data-peer-id], .chat-info .peer-title, .topbar .peer-title"),
      ).find((node) => isRenderable(node));
      const conversationRef = normalize(activeTitle?.getAttribute("data-peer-id") || fallbackPeerId);
      const chatName = cleanDecoratedText(activeTitle?.textContent || fallbackLabel || fallbackPeerId);
      const bubbles = Array.from(document.querySelectorAll(bubbleSelectors)).filter(isRenderable);
      if (!conversationRef || !chatName || !bubbles.length) {
        return [];
      }
      const recent = bubbles.slice(Math.max(0, bubbles.length - perChatLimit));
      const items = [];
      for (const bubble of recent) {
        const direction = bubble.classList.contains("is-out") ? "outbound" : "inbound";
        const author = normalize(
          bubble.querySelector(".bubble-name-first, .peer-title, .bubble-name-forwarded, .title-flex")?.textContent || "",
        );
        const explicitBodies = Array.from(
          bubble.querySelectorAll(".translatable-message, .quote-like .translatable-message, .translated-wrapper .translatable-message"),
        )
          .map((node) => normalize(node.textContent || node.innerText || ""))
          .filter(Boolean);
        let lines = [];
        if (explicitBodies.length) {
          lines = explicitBodies;
        } else {
          lines = normalize(bubble.querySelector(".bubble-content")?.textContent || bubble.textContent || bubble.innerText || "")
            .split("\n")
            .map((line) => normalize(line))
            .filter(Boolean);
        }
        if (author && lines.length && normalizeLower(lines[0]) === normalizeLower(author)) {
          lines.shift();
        }
        lines = lines.filter((line) => {
          const lowered = normalizeLower(line);
          if (!lowered) {
            return false;
          }
          if (lowered === "edited" || lowered === "düzenlendi" || lowered === "görüldü") {
            return false;
          }
          if (isTimestampOnly(line)) {
            return false;
          }
          return true;
        });
        const cleanedAuthor = cleanDecoratedText(author, { chatName });
        const body = cleanDecoratedText(lines.join(" "), { author: cleanedAuthor, chatName });
        if (!body) {
          continue;
        }
        const messageRef = normalize(
          bubble.getAttribute("data-mid")
          || `${conversationRef}:${bubble.getAttribute("data-timestamp") || Date.now()}:${hashText(body)}`,
        );
        const timestampRaw = Number(bubble.getAttribute("data-timestamp") || 0);
        const sentAt = timestampRaw > 0 ? new Date(timestampRaw * 1000).toISOString() : new Date().toISOString();
        items.push({
          provider: "telegram",
          conversation_ref: conversationRef,
          message_ref: messageRef,
          sender: direction === "outbound" ? "Siz" : (cleanedAuthor || chatName),
          recipient: direction === "outbound" ? chatName : "Siz",
          body,
          direction,
          sent_at: sentAt,
          reply_needed: direction === "inbound",
          metadata: {
            chat_name: chatName,
            chat_title: chatName,
            peer_id: conversationRef,
            contact_name: chatName,
            display_name: chatName,
            profile_name: cleanedAuthor || chatName,
            author_name: cleanedAuthor || "",
            is_group: Boolean(cleanedAuthor && normalizeLower(cleanedAuthor) !== normalizeLower(chatName)),
            extracted_from: "telegram_web_message",
          },
        });
      }
      return items;
    };
    const items = [];
    const seen = new Set();
    const chats = collectChatCandidates();
    for (const chat of chats) {
      chat.row.click();
      let attempts = 0;
      while (attempts < 20) {
        const composerReady = Array.from(document.querySelectorAll(composerSelectors)).some((node) => node instanceof HTMLElement);
        const bubblesReady = Array.from(document.querySelectorAll(bubbleSelectors)).some((node) => node instanceof HTMLElement);
        if (composerReady || bubblesReady) {
          break;
        }
        attempts += 1;
        await sleep(120);
      }
      await sleep(180);
      const messages = readActiveConversation(chat.peerId, chat.label);
      if (!messages.length && chat.label && (chat.preview || chat.label)) {
        messages.push({
          provider: "telegram",
          conversation_ref: chat.peerId,
          message_ref: `preview:${chat.peerId}:${hashText(`${chat.label}:${chat.preview}`)}`,
          sender: chat.label,
          recipient: "Telegram Web",
          body: cleanDecoratedText(chat.preview, { chatName: chat.label }) || chat.label,
          direction: "inbound",
          sent_at: new Date().toISOString(),
          reply_needed: Boolean(chat.preview),
          metadata: {
            chat_name: chat.label,
            chat_title: chat.label,
            peer_id: chat.peerId,
            contact_name: chat.label,
            display_name: chat.label,
            profile_name: chat.label,
            author_name: "",
            is_group: false,
            preview: cleanDecoratedText(chat.preview, { chatName: chat.label }),
            extracted_from: "telegram_web_preview_fallback",
          },
        });
      }
      for (const message of messages) {
        const dedupeKey = `${message.conversation_ref}:${message.message_ref}`;
        if (seen.has(dedupeKey)) {
          continue;
        }
        seen.add(dedupeKey);
        items.push(message);
        if (items.length >= totalLimit) {
          return items;
        }
      }
      await sleep(60);
    }
    return items;
  }, maxChats, messagesPerChat, maxTotalMessages);
}

async function syncTelegramWebData(config, runtimeInfo) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const window = await ensureWindow(config, { show: false });
  const status = await refreshStatus(config);
  if (status.webStatus !== "ready") {
    throw new Error("Telegram Web oturumu hazır değil. Giriş yapıp tekrar deneyin.");
  }
  const messages = await scrapeTelegramConversationMessages(
    window,
    SYNC_MAX_CHATS,
    SYNC_MESSAGES_PER_CHAT,
    SYNC_MAX_TOTAL_MESSAGES,
  );
  const syncedAt = nowIso();
  let syncedCount = 0;
  let lastPayload = {};
  const chunks = [];
  for (let index = 0; index < messages.length; index += SYNC_BATCH_SIZE) {
    chunks.push(messages.slice(index, index + SYNC_BATCH_SIZE));
  }
  if (!chunks.length) {
    chunks.push([]);
  }
  for (const chunk of chunks) {
    const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/telegram/sync`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${runtimeInfo.sessionToken}`,
      },
      body: JSON.stringify({
        account_label: status.webAccountLabel || status.accountLabel || "Telegram Web hesabı",
        bot_username: "",
        allowed_user_id: "",
        scopes: ["messages:read", "messages:send", "personal_account:web_session"],
        messages: chunk,
        synced_at: syncedAt,
        checkpoint: { mode: "web_conversation_messages" },
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(String(payload?.detail || payload?.message || "Telegram Web verileri eşitlenemedi."));
    }
    syncedCount += Array.isArray(chunk) ? chunk.length : 0;
    lastPayload = payload;
  }
  state.lastSyncAt = syncedAt;
  state.messageCountMirrored = Array.isArray(messages) ? messages.length : 0;
  await safeSaveConfig({
    telegram: {
      enabled: true,
      mode: "web",
      webStatus: "ready",
      webAccountLabel: status.webAccountLabel || status.accountLabel || "Telegram Web hesabı",
      webLastReadyAt: state.lastReadyAt || nowIso(),
      webLastSyncAt: syncedAt,
      validationStatus: "valid",
      lastValidatedAt: nowIso(),
    },
  });
  return {
    ok: true,
    message: "Telegram Web konuşmaları eşitlendi.",
    synced: {
      ...(typeof lastPayload?.synced === "object" && lastPayload?.synced ? lastPayload.synced : {}),
      messages: syncedCount,
      synced_at: syncedAt,
    },
    patch: {
      telegram: {
        enabled: true,
        mode: "web",
        webStatus: "ready",
        webAccountLabel: status.webAccountLabel || status.accountLabel || "Telegram Web hesabı",
        webLastReadyAt: state.lastReadyAt || nowIso(),
        webLastSyncAt: syncedAt,
        validationStatus: "valid",
        lastValidatedAt: nowIso(),
      },
    },
  };
}

async function sendTelegramWebMessage(config, payload = {}) {
  const window = await ensureWindow(config, { show: false });
  const status = await refreshStatus(config);
  if (status.webStatus !== "ready") {
    throw new Error("Telegram Web oturumu hazır değil.");
  }
  const text = String(payload.text || payload.body || "").trim();
  const target = String(payload.conversationRef || payload.conversation_ref || payload.to || payload.recipient || "").trim();
  if (!text || !target) {
    throw new Error("Telegram Web gönderimi için sohbet ve mesaj gerekli.");
  }
  const result = await runInWindow(window, async (conversationRef, messageText) => {
    const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
    const targetNeedle = normalize(conversationRef);
    const candidates = Array.from(
      document.querySelectorAll(".chatlist-chat[data-peer-id], .chatlist .chatlist-chat, .chatlist-container .chatlist-chat, #chatlist-container .chatlist-chat, [role='listitem'][data-peer-id], .chatlist [data-peer-id]"),
    ).filter((node) => node instanceof HTMLElement && node.offsetParent !== null);
    const match = candidates.find((node) => {
      const text = normalize(node.innerText || node.textContent || "");
      const ref = normalize(node.getAttribute("data-peer-id") || node.getAttribute("href") || "");
      return text.includes(targetNeedle) || ref.includes(targetNeedle);
    });
    if (!match) {
      return { ok: false, error: "conversation_not_found" };
    }
    match.click();
    await sleep(350);
    const composer = Array.from(document.querySelectorAll(".input-message-input[contenteditable='true'], [contenteditable='true'][role='textbox'], [contenteditable='true'], textarea"))
      .filter((node) => node instanceof HTMLElement && node.offsetParent !== null)
      .pop();
    if (!composer) {
      return { ok: false, error: "composer_not_found" };
    }
    composer.focus();
    if ("value" in composer) {
      composer.value = messageText;
      composer.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      composer.textContent = messageText;
      composer.dispatchEvent(new InputEvent("input", { bubbles: true, data: messageText, inputType: "insertText" }));
    }
    await sleep(80);
    const sendButton = Array.from(document.querySelectorAll("button"))
      .find((button) => /send|gonder|gönder/i.test(String(button.getAttribute("aria-label") || button.getAttribute("title") || button.textContent || "")));
    if (sendButton) {
      sendButton.click();
    } else {
      composer.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Enter", code: "Enter" }));
      composer.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: "Enter", code: "Enter" }));
    }
    return { ok: true };
  }, target, text);
  if (!result?.ok) {
    throw new Error(result?.error === "conversation_not_found" ? "Telegram Web sohbeti bulunamadı." : "Telegram Web mesajı gönderilemedi.");
  }
  return {
    ok: true,
    message: "Telegram Web mesajı gönderildi.",
    recipient: target,
    externalMessageId: `telegram-web-${Date.now()}`,
  };
}

async function disconnectTelegramWeb(config) {
  stopStatusPolling();
  if (webWindow && !webWindow.isDestroyed()) {
    webWindow.close();
    webWindow = null;
  }
  try {
    await session.fromPartition(resolvePartition(config)).clearStorageData();
  } catch {}
  state.status = "idle";
  state.lastError = "";
  state.accountLabel = "";
  state.currentUser = "";
  state.lastReadyAt = "";
  state.lastSyncAt = "";
  state.messageCountMirrored = 0;
  return {
    ok: true,
    message: "Telegram Web oturumu kaldırıldı.",
    patch: {
      telegram: {
        enabled: false,
        mode: "bot",
        webStatus: "idle",
        webAccountLabel: "",
        webLastReadyAt: "",
        webLastSyncAt: "",
        validationStatus: "pending",
      },
    },
  };
}

function getTelegramWebStatus(config) {
  state.webSessionName = resolveSessionName(config);
  return baseStatus(config);
}

function setTelegramWebBridgeContext(next) {
  bridgeContext = {
    ...bridgeContext,
    ...(next || {}),
  };
}

module.exports = {
  disconnectTelegramWeb,
  getTelegramWebStatus,
  sendTelegramWebMessage,
  setTelegramWebBridgeContext,
  startTelegramWebLink,
  syncTelegramWebData,
};
