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

const WHATSAPP_REQUEST_TIMEOUT_MS = Number(process.env.LAWCOPILOT_WHATSAPP_REQUEST_TIMEOUT_MS || 15000);
const {
  disconnectWhatsAppWeb,
  getWhatsAppWebStatus,
  sendWhatsAppWebMessage,
  setWhatsAppWebBridgeContext,
  startWhatsAppWebLink,
  syncWhatsAppWebData,
} = require("./whatsapp-web-bridge.cjs");

function normalizeWhatsAppMode(value, fallback = "web") {
  const mode = String(value || fallback || "").trim().toLowerCase();
  if (mode === "business_cloud" || mode === "web") {
    return mode;
  }
  return fallback;
}

function resolveWhatsAppMode(configOrInput) {
  const whatsapp = configOrInput?.whatsapp && typeof configOrInput.whatsapp === "object"
    ? configOrInput.whatsapp
    : configOrInput && typeof configOrInput === "object"
      ? configOrInput
      : {};
  if (String(whatsapp.mode || "").trim()) {
    return normalizeWhatsAppMode(whatsapp.mode);
  }
  if (whatsapp.phoneNumberId || whatsapp.accessToken) {
    return "business_cloud";
  }
  return "web";
}

async function fetchWithTimeout(url, options = {}, timeoutMs = WHATSAPP_REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

function graphBaseUrl() {
  return String(process.env.LAWCOPILOT_WHATSAPP_GRAPH_BASE_URL || "https://graph.facebook.com/v22.0").replace(/\/+$/, "");
}

function responseMessage(payload, fallback) {
  return String(payload?.error?.message || payload?.error?.error_user_msg || payload?.message || fallback);
}

function getWhatsAppStatus(config) {
  const mode = resolveWhatsAppMode(config);
  if (mode === "web") {
    return getWhatsAppWebStatus(config);
  }
  const whatsapp = config?.whatsapp || {};
  const configured = Boolean(whatsapp.enabled && whatsapp.accessToken && whatsapp.phoneNumberId);
  return {
    provider: "whatsapp",
    mode: "business_cloud",
    authStatus: configured ? "bagli" : "hazir_degil",
    configured,
    enabled: Boolean(whatsapp.enabled),
    accountLabel: String(whatsapp.businessLabel || whatsapp.verifiedName || whatsapp.displayPhoneNumber || "WhatsApp hesabı"),
    displayPhoneNumber: String(whatsapp.displayPhoneNumber || ""),
    verifiedName: String(whatsapp.verifiedName || ""),
    phoneNumberId: String(whatsapp.phoneNumberId || ""),
    validationStatus: String(whatsapp.validationStatus || "pending"),
    lastValidatedAt: String(whatsapp.lastValidatedAt || ""),
    lastSyncAt: String(whatsapp.lastSyncAt || ""),
    message: configured ? "WhatsApp bağlantısı hazır." : "WhatsApp için erişim belirteci ve telefon numarası kimliği gerekli.",
  };
}

async function validateWhatsAppConfig(input) {
  if (resolveWhatsAppMode(input) === "web") {
    return {
      ok: true,
      message: "WhatsApp Web modu için doğrulama QR ile bağlantı başlatıldığında yapılır.",
      whatsapp: {
        enabled: Boolean(input?.enabled ?? true),
        mode: "web",
        validationStatus: "pending",
        lastValidatedAt: "",
      },
    };
  }
  const accessToken = String(input?.accessToken || "").trim();
  const phoneNumberId = String(input?.phoneNumberId || "").trim();
  const businessLabel = String(input?.businessLabel || "").trim();

  if (!accessToken || !phoneNumberId) {
    throw new Error("WhatsApp doğrulaması için erişim belirteci ve telefon numarası kimliği gerekli.");
  }

  const response = await fetchWithTimeout(
    `${graphBaseUrl()}/${encodeURIComponent(phoneNumberId)}?fields=display_phone_number,verified_name`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  );
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(responseMessage(payload, "WhatsApp doğrulaması başarısız oldu."));
  }

  return {
    ok: true,
    message: "WhatsApp bağlantısı doğrulandı.",
    whatsapp: {
      enabled: Boolean(input?.enabled ?? true),
      mode: "business_cloud",
      businessLabel: businessLabel || String(payload.verified_name || payload.display_phone_number || "WhatsApp"),
      verifiedName: String(payload.verified_name || ""),
      displayPhoneNumber: String(payload.display_phone_number || ""),
      phoneNumberId,
      lastValidatedAt: new Date().toISOString(),
      validationStatus: "valid",
    },
  };
}

async function syncWhatsAppData(config, runtimeInfo) {
  if (resolveWhatsAppMode(config) === "web") {
    return syncWhatsAppWebData(config, runtimeInfo);
  }
  if (!runtimeInfo?.apiBaseUrl || !runtimeInfo?.sessionToken) {
    throw new Error("Yerel servis oturumu hazır değil.");
  }
  const whatsapp = config?.whatsapp || {};
  if (!whatsapp.enabled || !whatsapp.accessToken || !whatsapp.phoneNumberId) {
    throw new Error("WhatsApp hesabı bağlı değil.");
  }
  const syncedAt = new Date().toISOString();
  const response = await fetchWithTimeout(`${runtimeInfo.apiBaseUrl}/integrations/whatsapp/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${runtimeInfo.sessionToken}`,
    },
    body: JSON.stringify({
      account_label: whatsapp.businessLabel || whatsapp.verifiedName || whatsapp.displayPhoneNumber || "WhatsApp hesabı",
      phone_number_id: whatsapp.phoneNumberId,
      display_phone_number: whatsapp.displayPhoneNumber || "",
      verified_name: whatsapp.verifiedName || "",
      messages: [],
      synced_at: syncedAt,
      note: "Meta Cloud API gelen mesaj geçmişini doğrudan listelemediği için bu senkron bağlantı durumunu ve son gönderimleri aynalar.",
    }),
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(responseMessage(payload, "WhatsApp durumu eşitlenemedi."));
  }
  return {
    ok: true,
    message: "WhatsApp bağlantı durumu eşitlendi.",
    synced: payload.synced || null,
    patch: {
      whatsapp: {
        lastSyncAt: syncedAt,
      },
    },
  };
}

async function sendWhatsAppMessage(config, payload = {}) {
  if (resolveWhatsAppMode(config) === "web") {
    return sendWhatsAppWebMessage(config, payload);
  }
  const whatsapp = config?.whatsapp || {};
  if (!whatsapp.enabled || !whatsapp.accessToken || !whatsapp.phoneNumberId) {
    throw new Error("WhatsApp hesabı bağlı değil.");
  }
  const to = String(payload.to || payload.recipient || "").trim();
  const text = String(payload.text || payload.body || "").trim();
  if (!to || !text) {
    throw new Error("WhatsApp gönderimi için hedef numara ve mesaj gerekli.");
  }
  const response = await fetchWithTimeout(`${graphBaseUrl()}/${encodeURIComponent(String(whatsapp.phoneNumberId))}/messages`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${whatsapp.accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      messaging_product: "whatsapp",
      recipient_type: "individual",
      to,
      type: "text",
      text: {
        preview_url: false,
        body: text,
      },
    }),
  });
  const body = await parseJson(response);
  if (!response.ok || !Array.isArray(body?.messages) || !body.messages[0]?.id) {
    throw new Error(responseMessage(body, "WhatsApp mesajı gönderilemedi."));
  }
  return {
    ok: true,
    message: "WhatsApp mesajı gönderildi.",
    externalMessageId: String(body.messages[0].id),
    recipient: to,
  };
}

async function connectWhatsAppWeb(config) {
  return startWhatsAppWebLink(config);
}

async function disconnectWhatsApp(config) {
  if (resolveWhatsAppMode(config) === "web") {
    return disconnectWhatsAppWeb(config);
  }
  return {
    ok: true,
    message: "WhatsApp bağlantısı kaldırıldı.",
    patch: {
      whatsapp: {
        enabled: false,
        accessToken: "",
        phoneNumberId: "",
        businessLabel: "",
        displayPhoneNumber: "",
        verifiedName: "",
        validationStatus: "pending",
        lastSyncAt: "",
      },
    },
  };
}

module.exports = {
  connectWhatsAppWeb,
  disconnectWhatsApp,
  getWhatsAppStatus,
  sendWhatsAppMessage,
  setWhatsAppWebBridgeContext,
  syncWhatsAppData,
  validateWhatsAppConfig,
};
