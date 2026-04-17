const { providerDefaults } = require("./provider-model-catalog.cjs");
const {
  disconnectTelegramWeb,
  getTelegramWebStatus,
  sendTelegramWebMessage,
  setTelegramWebBridgeContext,
  startTelegramWebLink,
  syncTelegramWebData,
} = require("./telegram-web-bridge.cjs");

function normalizeBaseUrl(value, fallback) {
  const base = String(value || fallback || "").trim();
  return base.replace(/\/+$/, "");
}

function nowIso() {
  return new Date().toISOString();
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
  if (payload?.error?.message) {
    return String(payload.error.message);
  }
  if (payload?.description) {
    return String(payload.description);
  }
  if (payload?.message) {
    return String(payload.message);
  }
  return fallback;
}

async function validateProviderConfig(input) {
  const type = String(input?.type || "openai");
  const defaults = providerDefaults(type);
  let baseUrl = normalizeBaseUrl(input?.baseUrl, defaults.baseUrl);
  if (type === "gemini") {
    baseUrl = baseUrl.replace(/\/openai$/i, "");
  }
  const model = String(input?.model || defaults.model || "").trim();
  const apiKey = String(input?.apiKey || "").trim();

  if (type === "openai-codex") {
    throw new Error("Codex hesap oturumu için tarayıcı tabanlı OAuth akışını kullanın.");
  }

  if (type !== "ollama" && !apiKey) {
    throw new Error("Sağlayıcı doğrulaması için API anahtarı gerekli.");
  }

  if (!baseUrl) {
    throw new Error("Sağlayıcı doğrulaması için temel adres gerekli.");
  }

  let availableModels = [];
  let providerName = type;

  if (type === "ollama") {
    const response = await fetch(`${baseUrl}/api/tags`);
    const payload = await parseJson(response);
    if (!response.ok) {
      throw new Error(responseErrorMessage(payload, "Ollama doğrulaması başarısız oldu."));
    }
    availableModels = Array.isArray(payload.models) ? payload.models.map((item) => item.name).filter(Boolean) : [];
    providerName = "ollama";
  } else if (type === "gemini") {
    const response = await fetch(`${baseUrl}/models?key=${encodeURIComponent(apiKey)}`);
    const payload = await parseJson(response);
    if (!response.ok) {
      throw new Error(responseErrorMessage(payload, "Gemini doğrulaması başarısız oldu."));
    }
    availableModels = Array.isArray(payload.models)
      ? payload.models
        .map((item) => String(item?.name || "").replace(/^models\//, ""))
        .filter(Boolean)
      : [];
    providerName = "gemini";
  } else {
    const response = await fetch(`${baseUrl}/models`, {
      headers: {
        Authorization: `Bearer ${apiKey}`,
      },
    });
    const payload = await parseJson(response);
    if (!response.ok) {
      throw new Error(responseErrorMessage(payload, "Sağlayıcı doğrulaması başarısız oldu."));
    }
    availableModels = Array.isArray(payload.data) ? payload.data.map((item) => item.id).filter(Boolean) : [];
    providerName = type === "openai" ? "openai" : "openai-compatible";
  }

  return {
    ok: true,
    message: "Sağlayıcı bağlantısı doğrulandı.",
    provider: {
      type,
      providerName,
      baseUrl,
      model,
      lastValidatedAt: nowIso(),
      validationStatus: "valid",
      availableModels: availableModels.slice(0, 25),
    },
  };
}

async function validateTelegramConfig(input) {
  if (resolveTelegramMode(input) === "web") {
    return {
      ok: true,
      message: "Telegram Web modu için doğrulama web oturumu açıldığında yapılır.",
      telegram: {
        enabled: Boolean(input?.enabled ?? true),
        mode: "web",
        validationStatus: "pending",
        lastValidatedAt: "",
      },
    };
  }
  const botToken = String(input?.botToken || "").trim();
  const allowedUserId = String(input?.allowedUserId || "").trim();
  const apiBaseUrl = normalizeBaseUrl(input?.apiBaseUrl, "https://api.telegram.org");

  if (!botToken) {
    throw new Error("Telegram doğrulaması için bot token gerekli.");
  }

  const response = await fetch(`${apiBaseUrl}/bot${botToken}/getMe`);
  const payload = await parseJson(response);
  if (!response.ok || payload?.ok === false) {
    throw new Error(responseErrorMessage(payload, "Telegram bot doğrulaması başarısız oldu."));
  }

  const username = payload?.result?.username ? `@${payload.result.username}` : "";
  return {
    ok: true,
    message: "Telegram botu doğrulandı.",
    telegram: {
      enabled: Boolean(input?.enabled),
      botUsername: username,
      allowedUserId,
      lastValidatedAt: nowIso(),
      validationStatus: "valid",
    },
  };
}

async function sendTelegramTestMessage(input) {
  if (resolveTelegramMode(input) === "web") {
    return sendTelegramWebMessage({ telegram: input }, input);
  }
  const botToken = String(input?.botToken || "").trim();
  const allowedUserId = String(input?.allowedUserId || "").trim();
  const text = String(input?.text || "LawCopilot test mesajı").trim();
  const apiBaseUrl = normalizeBaseUrl(input?.apiBaseUrl, "https://api.telegram.org");

  if (!botToken || !allowedUserId) {
    throw new Error("Test mesajı için bot token ve Telegram kullanıcı kimliği gerekli.");
  }

  const response = await fetch(`${apiBaseUrl}/bot${botToken}/sendMessage`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      chat_id: allowedUserId,
      text,
    }),
  });
  const payload = await parseJson(response);
  if (!response.ok || payload?.ok === false) {
    throw new Error(responseErrorMessage(payload, "Telegram test mesajı gönderilemedi."));
  }

  return {
    ok: true,
    message: "Telegram test mesajı gönderildi.",
    messageId: payload?.result?.message_id,
  };
}

async function syncTelegramData(config, runtimeInfo) {
  if (resolveTelegramMode(config) === "web") {
    return syncTelegramWebData(config, runtimeInfo);
  }
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const telegram = config?.telegram || {};
  const botToken = String(telegram.botToken || "").trim();
  const allowedUserId = String(telegram.allowedUserId || "").trim();
  const apiBaseUrl = normalizeBaseUrl(telegram.apiBaseUrl, "https://api.telegram.org");
  if (!telegram.enabled || !botToken || !allowedUserId) {
    throw new Error("Telegram botu bağlı değil.");
  }

  const [botInfoResponse, updatesResponse] = await Promise.all([
    fetch(`${apiBaseUrl}/bot${botToken}/getMe`),
    fetch(`${apiBaseUrl}/bot${botToken}/getUpdates?limit=50&allowed_updates=${encodeURIComponent(JSON.stringify(["message"]))}`),
  ]);
  const botInfoPayload = await parseJson(botInfoResponse);
  const updatesPayload = await parseJson(updatesResponse);
  if (!botInfoResponse.ok || botInfoPayload?.ok === false) {
    throw new Error(responseErrorMessage(botInfoPayload, "Telegram bot bilgisi alınamadı."));
  }
  if (!updatesResponse.ok || updatesPayload?.ok === false) {
    throw new Error(responseErrorMessage(updatesPayload, "Telegram mesajları alınamadı."));
  }

  const updates = Array.isArray(updatesPayload?.result) ? updatesPayload.result : [];
  const messages = updates
    .map((item) => item?.message)
    .filter(Boolean)
    .filter((message) => String(message?.chat?.id || message?.from?.id || "") === allowedUserId)
    .map((message) => {
      const senderUsername = String(message?.from?.username || "").trim();
      const senderName = [message?.from?.first_name, message?.from?.last_name].filter(Boolean).join(" ").trim();
      const sender = senderUsername ? `@${senderUsername}` : senderName || String(message?.from?.id || "");
      const recipient = botInfoPayload?.result?.username ? `@${botInfoPayload.result.username}` : "Telegram botu";
      return {
        provider: "telegram",
        conversation_ref: `chat:${message?.chat?.id || allowedUserId}`,
        message_ref: String(message?.message_id || ""),
        sender,
        recipient,
        body: String(message?.text || message?.caption || "").trim(),
        direction: "inbound",
        sent_at: message?.date ? new Date(Number(message.date) * 1000).toISOString() : new Date().toISOString(),
        reply_needed: true,
        metadata: message,
      };
    })
    .filter((message) => message.message_ref && message.body);

  const syncedAt = new Date().toISOString();
  const response = await fetch(`${runtimeInfo.apiBaseUrl}/integrations/telegram/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: botInfoPayload?.result?.username ? `@${botInfoPayload.result.username}` : "Telegram botu",
      bot_username: botInfoPayload?.result?.username ? `@${botInfoPayload.result.username}` : "",
      allowed_user_id: allowedUserId,
      scopes: ["messages:read", "messages:send"],
      messages,
      synced_at: syncedAt,
    }),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(responseErrorMessage(payload, "Telegram verileri eşitlenemedi."));
  }
  return {
    ok: true,
    message: "Telegram verileri eşitlendi.",
    synced: payload.synced || null,
    patch: {
      telegram: {
        botUsername: botInfoPayload?.result?.username ? `@${botInfoPayload.result.username}` : String(telegram.botUsername || ""),
        lastValidatedAt: new Date().toISOString(),
        validationStatus: "valid",
      },
    },
  };
}

function resolveTelegramMode(configOrInput) {
  const telegram = configOrInput?.telegram && typeof configOrInput.telegram === "object"
    ? configOrInput.telegram
    : configOrInput && typeof configOrInput === "object"
      ? configOrInput
      : {};
  const mode = String(telegram.mode || "").trim().toLowerCase();
  if (mode === "bot" || mode === "web") {
    return mode;
  }
  if (telegram.botToken || telegram.allowedUserId) {
    return "bot";
  }
  return "web";
}

function getTelegramStatus(config) {
  if (resolveTelegramMode(config) === "web") {
    return getTelegramWebStatus(config);
  }
  const telegram = config?.telegram || {};
  const configured = Boolean(telegram.enabled && telegram.botToken && telegram.allowedUserId);
  return {
    provider: "telegram",
    mode: "bot",
    authStatus: configured ? "bagli" : "hazir_degil",
    configured,
    enabled: Boolean(telegram.enabled),
    accountLabel: String(telegram.botUsername || "Telegram botu"),
    validationStatus: String(telegram.validationStatus || "pending"),
    lastValidatedAt: String(telegram.lastValidatedAt || ""),
    message: configured
      ? "Telegram botu hazır; yalnız botla yapılan konuşmalar okunur ve bot adına mesaj gönderilir."
      : "Telegram botu için bot token ve izinli kullanıcı kimliği gerekli.",
  };
}

module.exports = {
  disconnectTelegramWeb,
  getTelegramStatus,
  normalizeBaseUrl,
  sendTelegramWebMessage,
  syncTelegramData,
  providerDefaults,
  setTelegramWebBridgeContext,
  startTelegramWebLink,
  sendTelegramTestMessage,
  validateProviderConfig,
  validateTelegramConfig,
};
