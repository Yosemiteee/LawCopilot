function normalizeBaseUrl(value, fallback) {
  const base = String(value || fallback || "").trim();
  return base.replace(/\/+$/, "");
}

function providerDefaults(type) {
  if (type === "openai-codex") {
    return {
      type: "openai-codex",
      baseUrl: "oauth://openai-codex",
      model: "openai-codex/gpt-5.3-codex",
    };
  }
  if (type === "gemini") {
    return {
      type: "gemini",
      baseUrl: "https://generativelanguage.googleapis.com/v1beta",
      model: "gemini-2.5-flash",
    };
  }
  if (type === "ollama") {
    return {
      type: "ollama",
      baseUrl: "http://127.0.0.1:11434",
      model: "llama3.1",
    };
  }
  if (type === "openai-compatible") {
    return {
      type: "openai-compatible",
      baseUrl: "https://api.openai.com/v1",
      model: "gpt-4.1-mini",
    };
  }
  return {
    type: "openai",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4.1-mini",
  };
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
  const baseUrl = normalizeBaseUrl(input?.baseUrl, defaults.baseUrl);
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

module.exports = {
  normalizeBaseUrl,
  providerDefaults,
  sendTelegramTestMessage,
  validateProviderConfig,
  validateTelegramConfig,
};
