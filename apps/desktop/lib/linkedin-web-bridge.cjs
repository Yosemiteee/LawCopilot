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
  webSessionName: "default",
  lastReadyAt: "",
  lastSyncAt: "",
  messageCountMirrored: 0,
};

const LINKEDIN_URL = "https://www.linkedin.com/messaging/";
const STATUS_POLL_MS = Number(process.env.LAWCOPILOT_LINKEDIN_WEB_STATUS_POLL_MS || 2500);
const SYNC_MAX_CONVERSATIONS = Number(process.env.LAWCOPILOT_LINKEDIN_WEB_MAX_CONVERSATIONS || 24);

function nowIso() {
  return new Date().toISOString();
}

function normalizeLinkedInMode(value, fallback = "web") {
  const mode = String(value || fallback || "").trim().toLowerCase();
  if (mode === "official" || mode === "web") {
    return mode;
  }
  return fallback;
}

function resolveLinkedInMode(config) {
  const linkedin = config?.linkedin || {};
  if (String(linkedin.mode || "").trim()) {
    return normalizeLinkedInMode(linkedin.mode, "web");
  }
  if (linkedin.oauthConnected || linkedin.accessToken) {
    return "official";
  }
  return "web";
}

function resolveSessionName(config) {
  const raw = String(config?.linkedin?.webSessionName || "default").trim();
  return raw.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-+|-+$/g, "") || "default";
}

function resolvePartition(config) {
  return `persist:lawcopilot-linkedin-web-${resolveSessionName(config)}`;
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
    console.error("[lawcopilot] linkedin_web_save_config_failed", error);
  }
}

function baseStatus(config) {
  const linkedin = config?.linkedin || {};
  const mode = resolveLinkedInMode(config);
  const currentStatus = String(state.status || linkedin.webStatus || "idle");
  const configured = mode === "web"
    ? Boolean((currentStatus === "ready" || linkedin.webStatus === "ready") && (state.accountLabel || linkedin.webAccountLabel))
    : Boolean(linkedin.enabled && linkedin.oauthConnected && linkedin.accessToken);
  return {
    provider: "linkedin",
    mode,
    configured,
    enabled: Boolean(linkedin.enabled),
    accountLabel: mode === "web"
      ? (state.accountLabel || String(linkedin.webAccountLabel || linkedin.accountLabel || "LinkedIn Web hesabı"))
      : String(linkedin.accountLabel || "LinkedIn hesabı"),
    scopes: Array.isArray(linkedin.scopes) ? linkedin.scopes : [],
    validationStatus: mode === "web"
      ? (configured ? "valid" : String(linkedin.validationStatus || "pending"))
      : String(linkedin.validationStatus || "pending"),
    webStatus: currentStatus,
    webSessionName: state.webSessionName || resolveSessionName(config),
    webAccountLabel: state.accountLabel || String(linkedin.webAccountLabel || ""),
    webLastReadyAt: state.lastReadyAt || String(linkedin.webLastReadyAt || ""),
    webLastSyncAt: state.lastSyncAt || String(linkedin.webLastSyncAt || ""),
    webMessageCountMirrored: Number(state.messageCountMirrored || 0),
    lastSyncAt: mode === "web"
      ? (state.lastSyncAt || String(linkedin.webLastSyncAt || linkedin.lastSyncAt || ""))
      : String(linkedin.lastSyncAt || ""),
    message: mode === "web"
      ? (
        currentStatus === "ready"
          ? "LinkedIn Web bağlı; DM önizlemeleri eşitlenebilir ve mevcut konuşmalara yanıt gönderilebilir."
          : currentStatus === "login_required"
            ? "LinkedIn Web oturumunu açıp giriş yapın."
            : currentStatus === "loading"
              ? "LinkedIn Web açılıyor."
              : "LinkedIn kişisel mesajları için web oturumu başlatın."
      )
      : "LinkedIn resmi erişimi bağlı.",
    error: state.lastError || "",
  };
}

async function runInWindow(window, fn, ...args) {
  if (!window || window.isDestroyed()) {
    throw new Error("linkedin_web_window_missing");
  }
  const payload = JSON.stringify(args ?? []);
  const script = `(${fn.toString()})(...${payload})`;
  return window.webContents.executeJavaScript(script, true);
}

async function detectLinkedInState(window) {
  return runInWindow(window, () => {
    const text = String(document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const title = String(document.title || "").trim();
    const hasLoginForm = Boolean(document.querySelector('input[name="session_key"], input[name="session_password"]'));
    const hasMessagingList = Boolean(
      document.querySelector(".msg-conversations-container__conversations-list")
      || document.querySelector(".msg-thread-listitem")
      || document.querySelector('[data-view-name*="messaging"]')
    );
    const hasComposer = Boolean(document.querySelector('.msg-form__contenteditable, [contenteditable="true"][role="textbox"]'));
    const ready = Boolean(hasMessagingList || hasComposer);
    const accountLabel = String(
      document.querySelector(".global-nav__me img")?.getAttribute("alt")
      || document.querySelector(".profile-card-member-details")?.textContent
      || title
    ).replace(/\s+/g, " ").trim();
    return {
      ready,
      hasLoginForm,
      accountLabel,
      title,
      text,
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
    title: "LinkedIn Web bağlantısı",
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
    await window.loadURL(LINKEDIN_URL);
  } else if (!window.webContents.getURL().startsWith("https://www.linkedin.com")) {
    state.status = "loading";
    await window.loadURL(LINKEDIN_URL);
  }
  return window;
}

async function refreshStatus(config) {
  if (!webWindow || webWindow.isDestroyed()) {
    return baseStatus(config);
  }
  try {
    const snapshot = await detectLinkedInState(webWindow);
    if (snapshot.ready) {
      state.status = "ready";
      state.lastError = "";
      state.lastReadyAt = state.lastReadyAt || nowIso();
      state.accountLabel = snapshot.accountLabel || state.accountLabel || "LinkedIn Web hesabı";
      await safeSaveConfig({
        linkedin: {
          enabled: true,
          mode: "web",
          webStatus: "ready",
          webAccountLabel: state.accountLabel,
          webLastReadyAt: state.lastReadyAt,
          validationStatus: "valid",
          lastValidatedAt: nowIso(),
        },
      });
    } else if (snapshot.hasLoginForm) {
      state.status = "login_required";
      state.lastError = "";
      await safeSaveConfig({
        linkedin: {
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
    state.lastError = String(error?.message || error || "linkedin_web_status_failed");
  }
  return baseStatus(config);
}

function startStatusPolling(config) {
  stopStatusPolling();
  statusPollTimer = setInterval(() => {
    void refreshStatus(config);
  }, STATUS_POLL_MS);
}

async function startLinkedInWebLink(config) {
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

async function scrapeLinkedInPreviewMessages(window, maxConversations = SYNC_MAX_CONVERSATIONS) {
  return runInWindow(window, async (limit) => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const candidates = Array.from(
      document.querySelectorAll("li.msg-conversations-container__convo-item, li.msg-thread-listitem, li.msg-conversation-listitem"),
    );
    const items = [];
    const seen = new Set();
    for (const node of candidates) {
      if (!(node instanceof HTMLElement) || node.offsetParent === null) {
        continue;
      }
      const text = normalize(node.innerText || node.textContent || "");
      if (!text) {
        continue;
      }
      const lines = text.split("\n").map((line) => normalize(line)).filter(Boolean);
      const label = normalize(
        node.querySelector(".msg-conversation-listitem__participant-names")?.textContent
        || node.querySelector(".msg-thread-listitem__name")?.textContent
        || lines[0]
        || ""
      );
      const preview = normalize(
        node.querySelector(".msg-conversation-listitem__message-snippet-body")?.textContent
        || node.querySelector(".msg-thread-listitem__preview")?.textContent
        || lines[lines.length - 1]
        || ""
      );
      if (!label || !preview) {
        continue;
      }
      const href = String(node.querySelector("a")?.getAttribute("href") || "").trim();
      const conversationRef = href || label;
      if (seen.has(conversationRef)) {
        continue;
      }
      seen.add(conversationRef);
      items.push({
        provider: "linkedin",
        conversation_ref: conversationRef,
        message_ref: `${conversationRef}:${Date.now()}:${items.length + 1}`,
        sender: label,
        recipient: "LinkedIn",
        body: preview.replace(/^(you:|sen:|siz:)\s*/i, "").trim(),
        direction: /^(you:|sen:|siz:)/i.test(preview) ? "outbound" : "inbound",
        sent_at: new Date().toISOString(),
        reply_needed: !/^(you:|sen:|siz:)/i.test(preview),
        metadata: {
          chat_name: label,
          href,
          preview,
          extracted_from: "linkedin_web_preview",
        },
      });
      if (items.length >= limit) {
        break;
      }
    }
    return items;
  }, maxConversations);
}

async function syncLinkedInWebData(config, runtimeInfo) {
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const window = await ensureWindow(config, { show: false });
  const status = await refreshStatus(config);
  if (status.webStatus !== "ready") {
    throw new Error("LinkedIn Web oturumu hazır değil. Giriş yapıp tekrar deneyin.");
  }
  const messages = await scrapeLinkedInPreviewMessages(window, SYNC_MAX_CONVERSATIONS);
  const syncedAt = nowIso();
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/linkedin/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: status.webAccountLabel || status.accountLabel || "LinkedIn Web hesabı",
      user_id: "",
      person_urn: "",
      scopes: ["messages:read", "messages:send", "personal_account:web_session"],
      posts: [],
      comments: [],
      messages,
      synced_at: syncedAt,
      checkpoint: { mode: "web_preview" },
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(String(payload?.detail || payload?.message || "LinkedIn Web verileri eşitlenemedi."));
  }
  state.lastSyncAt = syncedAt;
  state.messageCountMirrored = Array.isArray(messages) ? messages.length : 0;
  await safeSaveConfig({
    linkedin: {
      enabled: true,
      mode: "web",
      webStatus: "ready",
      webAccountLabel: status.webAccountLabel || status.accountLabel || "LinkedIn Web hesabı",
      webLastReadyAt: state.lastReadyAt || nowIso(),
      webLastSyncAt: syncedAt,
      validationStatus: "valid",
      lastValidatedAt: nowIso(),
    },
  });
  return {
    ok: true,
    message: "LinkedIn Web konuşma önizlemeleri eşitlendi.",
    synced: payload.synced || null,
    patch: {
      linkedin: {
        enabled: true,
        mode: "web",
        webStatus: "ready",
        webAccountLabel: status.webAccountLabel || status.accountLabel || "LinkedIn Web hesabı",
        webLastReadyAt: state.lastReadyAt || nowIso(),
        webLastSyncAt: syncedAt,
        validationStatus: "valid",
        lastValidatedAt: nowIso(),
      },
    },
  };
}

async function sendLinkedInWebMessage(config, payload = {}) {
  const window = await ensureWindow(config, { show: false });
  const status = await refreshStatus(config);
  if (status.webStatus !== "ready") {
    throw new Error("LinkedIn Web oturumu hazır değil.");
  }
  const text = String(payload.text || payload.body || "").trim();
  const target = String(payload.conversationRef || payload.conversation_ref || payload.to || payload.recipient || "").trim();
  if (!text || !target) {
    throw new Error("LinkedIn Web gönderimi için konuşma ve mesaj gerekli.");
  }
  const result = await runInWindow(window, async (conversationRef, messageText) => {
    const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
    const targetNeedle = normalize(conversationRef);
    const candidates = Array.from(
      document.querySelectorAll("li.msg-conversations-container__convo-item, li.msg-thread-listitem, li.msg-conversation-listitem"),
    ).filter((node) => node instanceof HTMLElement && node.offsetParent !== null);
    const match = candidates.find((node) => {
      const text = normalize(node.innerText || node.textContent || "");
      const href = normalize(node.querySelector("a")?.getAttribute("href") || "");
      return text.includes(targetNeedle) || href.includes(targetNeedle);
    });
    if (!match) {
      return { ok: false, error: "conversation_not_found" };
    }
    match.click();
    await sleep(450);
    const composer = Array.from(document.querySelectorAll(".msg-form__contenteditable, [contenteditable='true'][role='textbox']"))
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
    await sleep(100);
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
    throw new Error(result?.error === "conversation_not_found" ? "LinkedIn Web konuşması bulunamadı." : "LinkedIn Web mesajı gönderilemedi.");
  }
  return {
    ok: true,
    message: "LinkedIn Web mesajı gönderildi.",
    recipient: target,
    externalMessageId: `linkedin-web-${Date.now()}`,
  };
}

async function disconnectLinkedInWeb(config) {
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
  state.lastReadyAt = "";
  state.lastSyncAt = "";
  state.messageCountMirrored = 0;
  return {
    ok: true,
    message: "LinkedIn Web oturumu kaldırıldı.",
    patch: {
      linkedin: {
        enabled: false,
        mode: "official",
        webStatus: "idle",
        webAccountLabel: "",
        webLastReadyAt: "",
        webLastSyncAt: "",
        validationStatus: "pending",
      },
    },
  };
}

function getLinkedInWebStatus(config) {
  state.webSessionName = resolveSessionName(config);
  return baseStatus(config);
}

function setLinkedInWebBridgeContext(next) {
  bridgeContext = {
    ...bridgeContext,
    ...(next || {}),
  };
}

module.exports = {
  disconnectLinkedInWeb,
  getLinkedInWebStatus,
  sendLinkedInWebMessage,
  setLinkedInWebBridgeContext,
  startLinkedInWebLink,
  syncLinkedInWebData,
};
