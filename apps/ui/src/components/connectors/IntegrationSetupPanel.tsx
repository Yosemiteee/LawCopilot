import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";
import { sozluk } from "../../i18n";
import { asistanAracKapsamEtiketi } from "../../lib/labels";

type PanelMode = "simple" | "onboarding" | "settings" | "connectors";

type IntegrationSetupPanelProps = {
  mode?: PanelMode;
  onUpdated?: () => void;
};

type SanitizedIntegrationConfig = {
  provider?: {
    type?: string;
    authMode?: string;
    baseUrl?: string;
    model?: string;
    validationStatus?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    apiKeyConfigured?: boolean;
    apiKeyMasked?: string;
    accountLabel?: string;
    availableModels?: string[];
    oauthConnected?: boolean;
    oauthLastError?: string;
  };
  google?: {
    enabled?: boolean;
    accountLabel?: string;
    scopes?: string[];
    oauthConnected?: boolean;
    oauthLastError?: string;
    validationStatus?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    clientIdConfigured?: boolean;
    clientSecretConfigured?: boolean;
  };
  telegram?: {
    enabled?: boolean;
    botUsername?: string;
    allowedUserId?: string;
    validationStatus?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    botTokenConfigured?: boolean;
    botTokenMasked?: string;
  };
  whatsapp?: {
    enabled?: boolean;
    businessLabel?: string;
    displayPhoneNumber?: string;
    verifiedName?: string;
    phoneNumberId?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    validationStatus?: string;
    lastSyncAt?: string;
    accessTokenConfigured?: boolean;
    accessTokenMasked?: string;
  };
  x?: {
    enabled?: boolean;
    accountLabel?: string;
    userId?: string;
    scopes?: string[];
    oauthConnected?: boolean;
    oauthLastError?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    validationStatus?: string;
    lastSyncAt?: string;
    accessTokenConfigured?: boolean;
    refreshTokenConfigured?: boolean;
    clientIdConfigured?: boolean;
    clientSecretConfigured?: boolean;
  };
};

type CodexAuthStatus = {
  authStatus?: string;
  message?: string;
  authUrl?: string;
  browserOpened?: boolean;
  browserTarget?: string;
  configured?: boolean;
  availableModels?: string[];
  selectedModel?: string;
  error?: string;
};

type GoogleAuthStatus = {
  authStatus?: string;
  message?: string;
  authUrl?: string;
  browserTarget?: string;
  configured?: boolean;
  accountLabel?: string;
  scopes?: string[];
  clientReady?: boolean;
  error?: string;
};

type WhatsAppAuthStatus = {
  configured?: boolean;
  enabled?: boolean;
  accountLabel?: string;
  displayPhoneNumber?: string;
  verifiedName?: string;
  phoneNumberId?: string;
  validationStatus?: string;
  lastValidatedAt?: string;
  lastSyncAt?: string;
  message?: string;
  error?: string;
};

type XAuthStatus = {
  configured?: boolean;
  accountLabel?: string;
  userId?: string;
  scopes?: string[];
  clientReady?: boolean;
  message?: string;
  error?: string;
};

function parseWhatsAppSetupBundle(value: string) {
  const source = String(value || "").trim();
  if (!source) {
    return {};
  }
  try {
    const parsed = JSON.parse(source) as Record<string, unknown>;
    if (parsed && typeof parsed === "object") {
      return {
        businessLabel: String(parsed.businessLabel || parsed.accountLabel || parsed.verified_name || parsed.verifiedName || "").trim(),
        phoneNumberId: String(parsed.phoneNumberId || parsed.phone_number_id || parsed.sender_id || "").trim(),
        accessToken: String(parsed.accessToken || parsed.access_token || parsed.token || "").trim(),
      };
    }
  } catch {
    // fall through to text parsing
  }

  const matchValue = (patterns: RegExp[]) => {
    for (const pattern of patterns) {
      const match = source.match(pattern);
      if (match?.[1]) {
        return String(match[1]).trim();
      }
    }
    return "";
  };

  return {
    businessLabel: matchValue([
      /(?:businessLabel|accountLabel|verified_name|verifiedName|hesap adı|hesap etiketi)\s*[:=]\s*"?([^"\n,]+)"?/i,
    ]),
    phoneNumberId: matchValue([
      /(?:phoneNumberId|phone_number_id|sender_id|telefon hattı kimliği|telefon numarası kimliği|hat kimliği)\s*[:=]\s*"?([^"\n,]+)"?/i,
    ]),
    accessToken: matchValue([
      /(?:accessToken|access_token|token|erişim anahtarı|erişim belirteci)\s*[:=]\s*"?([^"\n]+)"?/i,
    ]),
  };
}

function providerLabel(value: string) {
  if (value === "openai-codex") {
    return sozluk.integrations.providerTypeCodex;
  }
  if (value === "gemini") {
    return sozluk.integrations.providerTypeGemini;
  }
  if (value === "ollama") {
    return sozluk.integrations.providerTypeOllama;
  }
  if (value === "openai-compatible") {
    return sozluk.integrations.providerTypeCompatible;
  }
  return sozluk.integrations.providerTypeOpenAI;
}

function validationTone(value: string) {
  if (value === "valid") {
    return "accent" as const;
  }
  if (value === "invalid") {
    return "danger" as const;
  }
  return "warning" as const;
}

type ProviderPreset = {
  baseUrl: string;
  defaultModel: string;
  suggestedModels: string[];
};

function providerPreset(type: string): ProviderPreset {
  if (type === "openai-codex") {
    return {
      baseUrl: "oauth://openai-codex",
      defaultModel: "openai-codex/gpt-5.3-codex",
      suggestedModels: [
        "openai-codex/gpt-5.3-codex",
        "openai-codex/gpt-5.1-codex",
      ],
    };
  }
  if (type === "gemini") {
    return {
      baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
      defaultModel: "gemini-2.5-flash",
      suggestedModels: [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
      ],
    };
  }
  if (type === "ollama") {
    return {
      baseUrl: "http://127.0.0.1:11434",
      defaultModel: "llama3.1",
      suggestedModels: ["llama3.1", "llama3.2", "qwen2.5", "mistral"],
    };
  }
  if (type === "openai-compatible") {
    return {
      baseUrl: "https://api.openai.com/v1",
      defaultModel: "",
      suggestedModels: [],
    };
  }
  return {
    baseUrl: "https://api.openai.com/v1",
    defaultModel: "gpt-4.1-mini",
    suggestedModels: ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"],
  };
}

const INTEGRATION_GUIDES = {
  google: "https://console.cloud.google.com/apis/credentials",
  telegram: "https://t.me/BotFather",
  whatsapp: "https://developers.facebook.com/docs/whatsapp/cloud-api/get-started",
  x: "https://developer.x.com/en/portal/dashboard",
};

function SecretField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <label className="setup-form-field setup-form-field--secret">
      <span className="setup-form-field__label">{label}</span>
      <div className="setup-form-secret">
        <input
          className="input setup-form-secret__input"
          type={visible ? "text" : "password"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
        />
        <button
          className="setup-form-secret__toggle"
          type="button"
          aria-label={visible ? "Gizle" : "Göster"}
          title={visible ? "Gizle" : "Göster"}
          onClick={() => setVisible((current) => !current)}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        </button>
      </div>
    </label>
  );
}

export function IntegrationSetupPanel({ mode = "connectors", onUpdated }: IntegrationSetupPanelProps) {
  const [desktopReady, setDesktopReady] = useState(Boolean(window.lawcopilotDesktop));
  const [providerType, setProviderType] = useState("openai");
  const [providerBaseUrl, setProviderBaseUrl] = useState("https://api.openai.com/v1");
  const [providerModel, setProviderModel] = useState("gpt-4.1-mini");
  const [providerApiKey, setProviderApiKey] = useState("");
  const [providerMaskedKey, setProviderMaskedKey] = useState("");
  const [providerStatusValue, setProviderStatusValue] = useState("pending");
  const [providerStatusMessage, setProviderStatusMessage] = useState("");
  const [providerAvailableModels, setProviderAvailableModels] = useState<string[]>([]);
  const [providerBusy, setProviderBusy] = useState(false);
  const [providerError, setProviderError] = useState("");

  const [codexAuthUrl, setCodexAuthUrl] = useState("");
  const [codexCallbackUrl, setCodexCallbackUrl] = useState("");
  const [codexBrowserTarget, setCodexBrowserTarget] = useState("");
  const [codexConfigured, setCodexConfigured] = useState(false);
  const [codexBusy, setCodexBusy] = useState(false);

  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [googleConfigured, setGoogleConfigured] = useState(false);
  const [googleClientReady, setGoogleClientReady] = useState(false);
  const [googleAccountLabel, setGoogleAccountLabel] = useState("");
  const [googleScopes, setGoogleScopes] = useState<string[]>([]);
  const [googleClientId, setGoogleClientId] = useState("");
  const [googleClientSecret, setGoogleClientSecret] = useState("");
  const [googleStatusValue, setGoogleStatusValue] = useState("pending");
  const [googleStatusMessage, setGoogleStatusMessage] = useState("");
  const [googleError, setGoogleError] = useState("");
  const [googleBusy, setGoogleBusy] = useState(false);
  const [googleAuthUrl, setGoogleAuthUrl] = useState("");
  const [googleCallbackUrl, setGoogleCallbackUrl] = useState("");
  const [googleBrowserTarget, setGoogleBrowserTarget] = useState("");

  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramBotToken, setTelegramBotToken] = useState("");
  const [telegramAllowedUserId, setTelegramAllowedUserId] = useState("");
  const [telegramBotUsername, setTelegramBotUsername] = useState("");
  const [telegramMaskedToken, setTelegramMaskedToken] = useState("");
  const [telegramStatusValue, setTelegramStatusValue] = useState("pending");
  const [telegramStatusMessage, setTelegramStatusMessage] = useState("");
  const [telegramBusy, setTelegramBusy] = useState(false);
  const [telegramError, setTelegramError] = useState("");
  const [whatsAppEnabled, setWhatsAppEnabled] = useState(false);
  const [whatsAppBusinessLabel, setWhatsAppBusinessLabel] = useState("");
  const [whatsAppPhoneNumberId, setWhatsAppPhoneNumberId] = useState("");
  const [whatsAppAccessToken, setWhatsAppAccessToken] = useState("");
  const [whatsAppSetupBundle, setWhatsAppSetupBundle] = useState("");
  const [whatsAppMaskedToken, setWhatsAppMaskedToken] = useState("");
  const [whatsAppDisplayNumber, setWhatsAppDisplayNumber] = useState("");
  const [whatsAppVerifiedName, setWhatsAppVerifiedName] = useState("");
  const [whatsAppStatusValue, setWhatsAppStatusValue] = useState("pending");
  const [whatsAppStatusMessage, setWhatsAppStatusMessage] = useState("");
  const [whatsAppBusy, setWhatsAppBusy] = useState(false);
  const [whatsAppError, setWhatsAppError] = useState("");
  const [whatsAppLastSyncAt, setWhatsAppLastSyncAt] = useState("");
  const [xEnabled, setXEnabled] = useState(false);
  const [xConfigured, setXConfigured] = useState(false);
  const [xClientReady, setXClientReady] = useState(false);
  const [xAccountLabel, setXAccountLabel] = useState("");
  const [xScopes, setXScopes] = useState<string[]>([]);
  const [xClientId, setXClientId] = useState("");
  const [xClientSecret, setXClientSecret] = useState("");
  const [xStatusValue, setXStatusValue] = useState("pending");
  const [xStatusMessage, setXStatusMessage] = useState("");
  const [xBusy, setXBusy] = useState(false);
  const [xError, setXError] = useState("");
  const [xLastSyncAt, setXLastSyncAt] = useState("");
  const currentProviderPreset = useMemo(() => providerPreset(providerType), [providerType]);
  const suggestedProviderModels = useMemo(() => {
    const source = providerAvailableModels.length ? providerAvailableModels : currentProviderPreset.suggestedModels;
    const next = source.filter(Boolean);
    if (providerModel && !next.includes(providerModel)) {
      next.unshift(providerModel);
    }
    return next;
  }, [currentProviderPreset.suggestedModels, providerAvailableModels, providerModel]);

  function applyCodexStatus(status: CodexAuthStatus, fallbackMessage = "") {
    const configured = Boolean(status.configured);
    setCodexConfigured(configured);
    setProviderStatusValue(configured ? "valid" : status.authStatus === "hata" ? "invalid" : "pending");
    setProviderStatusMessage(String(status.message || fallbackMessage || ""));
    setProviderAvailableModels(Array.isArray(status.availableModels) ? status.availableModels : []);
    setCodexAuthUrl(String(status.authUrl || ""));
    setCodexBrowserTarget(String(status.browserTarget || ""));
    setProviderError(String(status.error || ""));
    if (status.selectedModel) {
      setProviderModel(String(status.selectedModel));
    }
  }

  function applyGoogleStatus(status: GoogleAuthStatus, fallbackMessage = "") {
    setGoogleConfigured(Boolean(status.configured));
    setGoogleClientReady(Boolean(status.clientReady));
    setGoogleAccountLabel(String(status.accountLabel || ""));
    setGoogleScopes(Array.isArray(status.scopes) ? status.scopes : []);
    setGoogleStatusValue(Boolean(status.configured) ? "valid" : status.authStatus === "hata" ? "invalid" : "pending");
    setGoogleStatusMessage(String(status.message || fallbackMessage || ""));
    setGoogleAuthUrl(String(status.authUrl || ""));
    setGoogleBrowserTarget(String(status.browserTarget || ""));
    setGoogleError(String(status.error || ""));
  }

  function applyWhatsAppStatus(status: WhatsAppAuthStatus, fallbackMessage = "") {
    setWhatsAppEnabled(Boolean(status.enabled));
    setWhatsAppBusinessLabel(String(status.accountLabel || ""));
    setWhatsAppDisplayNumber(String(status.displayPhoneNumber || ""));
    setWhatsAppVerifiedName(String(status.verifiedName || ""));
    setWhatsAppPhoneNumberId(String(status.phoneNumberId || ""));
    setWhatsAppStatusValue(Boolean(status.configured) ? "valid" : String(status.validationStatus || "pending"));
    setWhatsAppStatusMessage(String(status.message || fallbackMessage || ""));
    setWhatsAppLastSyncAt(String(status.lastSyncAt || ""));
    setWhatsAppError(String(status.error || ""));
  }

  function applyXStatus(status: XAuthStatus, fallbackMessage = "") {
    setXConfigured(Boolean(status.configured));
    setXClientReady(Boolean(status.clientReady));
    setXAccountLabel(String(status.accountLabel || ""));
    setXScopes(Array.isArray(status.scopes) ? status.scopes : []);
    setXStatusValue(Boolean(status.configured) ? "valid" : "pending");
    setXStatusMessage(String(status.message || fallbackMessage || ""));
    setXError(String(status.error || ""));
  }

  useEffect(() => {
    let active = true;
    async function loadConfig() {
      if (!window.lawcopilotDesktop?.getIntegrationConfig) {
        setDesktopReady(false);
        return;
      }
      const config = (await window.lawcopilotDesktop.getIntegrationConfig()) as SanitizedIntegrationConfig;
      if (!active) {
        return;
      }
      const provider = config.provider || {};
      const providerDefaults = providerPreset(String(provider.type || "openai"));
      const google = config.google || {};
      const telegram = config.telegram || {};
      const whatsapp = config.whatsapp || {};
      const x = config.x || {};
      setProviderType(String(provider.type || "openai"));
      setProviderBaseUrl(String(provider.baseUrl || providerDefaults.baseUrl));
      setProviderModel(String(provider.model || providerDefaults.defaultModel));
      setProviderMaskedKey(String(provider.apiKeyMasked || ""));
      setProviderStatusValue(String(provider.validationStatus || "pending"));
      setProviderStatusMessage("");
      setProviderAvailableModels(Array.isArray(provider.availableModels) ? provider.availableModels || [] : []);
      setCodexConfigured(Boolean(provider.oauthConnected));
      setGoogleEnabled(Boolean(google.enabled));
      setGoogleConfigured(Boolean(google.oauthConnected));
      setGoogleClientReady(Boolean(google.clientIdConfigured && google.clientSecretConfigured));
      setGoogleAccountLabel(String(google.accountLabel || ""));
      setGoogleScopes(Array.isArray(google.scopes) ? google.scopes : []);
      setGoogleStatusValue(String(google.validationStatus || "pending"));
      setTelegramEnabled(Boolean(telegram.enabled));
      setTelegramAllowedUserId(String(telegram.allowedUserId || ""));
      setTelegramBotUsername(String(telegram.botUsername || ""));
      setTelegramMaskedToken(String(telegram.botTokenMasked || ""));
      setTelegramStatusValue(String(telegram.validationStatus || "pending"));
      setWhatsAppEnabled(Boolean(whatsapp.enabled));
      setWhatsAppBusinessLabel(String(whatsapp.businessLabel || ""));
      setWhatsAppDisplayNumber(String(whatsapp.displayPhoneNumber || ""));
      setWhatsAppVerifiedName(String(whatsapp.verifiedName || ""));
      setWhatsAppPhoneNumberId(String(whatsapp.phoneNumberId || ""));
      setWhatsAppMaskedToken(String(whatsapp.accessTokenMasked || ""));
      setWhatsAppStatusValue(String(whatsapp.validationStatus || "pending"));
      setWhatsAppLastSyncAt(String(whatsapp.lastSyncAt || ""));
      setXEnabled(Boolean(x.enabled));
      setXConfigured(Boolean(x.oauthConnected));
      setXClientReady(Boolean(x.clientIdConfigured && x.clientSecretConfigured));
      setXAccountLabel(String(x.accountLabel || ""));
      setXScopes(Array.isArray(x.scopes) ? x.scopes : []);
      setXStatusValue(String(x.validationStatus || "pending"));
      setXLastSyncAt(String(x.lastSyncAt || ""));
      setDesktopReady(true);
      if ((provider.type || "") === "openai-codex" && window.lawcopilotDesktop?.getCodexAuthStatus) {
        const status = (await window.lawcopilotDesktop.getCodexAuthStatus()) as CodexAuthStatus;
        if (active) {
          applyCodexStatus(status);
        }
      }
      if (window.lawcopilotDesktop?.getGoogleAuthStatus) {
        const status = (await window.lawcopilotDesktop.getGoogleAuthStatus()) as GoogleAuthStatus;
        if (active) {
          applyGoogleStatus(status);
        }
      }
      if (window.lawcopilotDesktop?.getWhatsAppStatus) {
        const status = (await window.lawcopilotDesktop.getWhatsAppStatus()) as WhatsAppAuthStatus;
        if (active) {
          applyWhatsAppStatus(status);
        }
      }
      if (window.lawcopilotDesktop?.getXAuthStatus) {
        const status = (await window.lawcopilotDesktop.getXAuthStatus()) as XAuthStatus;
        if (active) {
          applyXStatus(status);
        }
      }
    }
    void loadConfig();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!googleAuthUrl || googleConfigured) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void refreshGoogleStatus();
    }, 2000);
    return () => window.clearInterval(intervalId);
  }, [googleAuthUrl, googleConfigured]);

  const providerNeedsKey = providerType !== "ollama" && providerType !== "openai-codex";
  const providerUsesBrowserAuth = providerType === "openai-codex";
  const simpleMode = mode === "simple" || mode === "onboarding" || mode === "settings";
  const googleHasGmail = googleScopes.some((scope) => String(scope).includes("gmail"));
  const googleHasCalendar = googleScopes.some((scope) => String(scope).includes("calendar"));
  const googleHasDrive = googleScopes.some((scope) => String(scope).includes("drive"));
  const showCodexCallback = Boolean(codexAuthUrl || codexBrowserTarget || codexCallbackUrl.trim());
  const showGoogleCallback = Boolean(googleAuthUrl || googleBrowserTarget || googleCallbackUrl.trim());
  const providerSubtitle = useMemo(() => {
    if (mode === "onboarding") {
      return sozluk.integrations.providerOnboardingSubtitle;
    }
    return sozluk.integrations.providerSubtitle;
  }, [mode]);

  async function refreshCodexStatus() {
    if (!window.lawcopilotDesktop?.getCodexAuthStatus) {
      setProviderError(sozluk.integrations.desktopOnly);
      return;
    }
    setCodexBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.getCodexAuthStatus()) as CodexAuthStatus;
      applyCodexStatus(status, sozluk.integrations.codexAuthIdle);
    } catch (error) {
      setProviderStatusValue("invalid");
      setProviderError(error instanceof Error ? error.message : sozluk.integrations.codexAuthError);
    } finally {
      setCodexBusy(false);
    }
  }

  async function startCodexAuthFlow() {
    if (!window.lawcopilotDesktop?.startCodexAuth) {
      setProviderError(sozluk.integrations.desktopOnly);
      return;
    }
    setCodexBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.startCodexAuth()) as CodexAuthStatus;
      applyCodexStatus(status, sozluk.integrations.codexAuthPending);
      setProviderError("");
    } catch (error) {
      setProviderStatusValue("invalid");
      setProviderStatusMessage("");
      setProviderError(error instanceof Error ? error.message : sozluk.integrations.codexAuthError);
    } finally {
      setCodexBusy(false);
    }
  }

  async function submitCodexCallback() {
    if (!window.lawcopilotDesktop?.submitCodexAuthCallback) {
      setProviderError(sozluk.integrations.desktopOnly);
      return;
    }
    setCodexBusy(true);
    try {
      const response = (await window.lawcopilotDesktop.submitCodexAuthCallback(codexCallbackUrl)) as {
        status?: CodexAuthStatus;
        config?: SanitizedIntegrationConfig;
      };
      applyCodexStatus(response.status || {}, sozluk.integrations.codexAuthConnected);
      const provider = response.config?.provider || {};
      setProviderType(String(provider.type || "openai"));
      setProviderModel(String(provider.model || providerModel));
      setProviderAvailableModels(Array.isArray(provider.availableModels) ? provider.availableModels || [] : []);
      setCodexCallbackUrl("");
      setProviderError("");
      onUpdated?.();
    } catch (error) {
      setProviderStatusValue("invalid");
      setProviderStatusMessage("");
      setProviderError(error instanceof Error ? error.message : sozluk.integrations.codexAuthError);
    } finally {
      setCodexBusy(false);
    }
  }

  async function cancelCodexAuthFlow() {
    if (!window.lawcopilotDesktop?.cancelCodexAuth) {
      return;
    }
    const status = await window.lawcopilotDesktop.cancelCodexAuth();
    applyCodexStatus(status as CodexAuthStatus, sozluk.integrations.codexAuthCancelled);
  }

  async function refreshGoogleStatus() {
    if (!window.lawcopilotDesktop?.getGoogleAuthStatus) {
      setGoogleError(sozluk.integrations.desktopOnly);
      return;
    }
    setGoogleBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.getGoogleAuthStatus()) as GoogleAuthStatus;
      applyGoogleStatus(status, sozluk.integrations.googleAuthIdle);
    } catch (error) {
      setGoogleStatusValue("invalid");
      setGoogleError(error instanceof Error ? error.message : sozluk.integrations.googleAuthError);
    } finally {
      setGoogleBusy(false);
    }
  }

  async function saveGoogleClientSetup() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setGoogleError(sozluk.integrations.desktopOnly);
      return;
    }
    if (!googleClientId.trim() || !googleClientSecret.trim()) {
      setGoogleError(sozluk.integrations.googleClientSetupRequired);
      return;
    }
    setGoogleBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        google: {
          clientId: googleClientId.trim(),
          clientSecret: googleClientSecret.trim(),
        },
      });
      setGoogleClientId("");
      setGoogleClientSecret("");
      await refreshGoogleStatus();
      setGoogleError("");
      setGoogleStatusMessage(sozluk.integrations.googleClientSaved);
    } catch (error) {
      setGoogleError(error instanceof Error ? error.message : sozluk.integrations.googleClientSaveError);
    } finally {
      setGoogleBusy(false);
    }
  }

  async function startGoogleAuthFlow() {
    if (!window.lawcopilotDesktop?.startGoogleAuth) {
      setGoogleError(sozluk.integrations.desktopOnly);
      return;
    }
    setGoogleBusy(true);
    setGoogleError("");
    setGoogleStatusMessage(sozluk.integrations.googleAuthWaiting);
    try {
      const status = (await window.lawcopilotDesktop.startGoogleAuth()) as GoogleAuthStatus;
      applyGoogleStatus(status, sozluk.integrations.googleAuthConnected);
      setGoogleEnabled(true);
      setGoogleCallbackUrl("");
      onUpdated?.();
    } catch (error) {
      setGoogleStatusValue("invalid");
      setGoogleStatusMessage("");
      setGoogleError(error instanceof Error ? error.message : sozluk.integrations.googleAuthError);
    } finally {
      setGoogleBusy(false);
    }
  }

  async function submitGoogleCallback() {
    if (!window.lawcopilotDesktop?.submitGoogleAuthCallback) {
      setGoogleError(sozluk.integrations.desktopOnly);
      return;
    }
    setGoogleBusy(true);
    try {
      const response = (await window.lawcopilotDesktop.submitGoogleAuthCallback(googleCallbackUrl)) as {
        status?: GoogleAuthStatus;
        config?: SanitizedIntegrationConfig;
      };
      applyGoogleStatus(response.status || {}, sozluk.integrations.googleAuthConnected);
      setGoogleEnabled(Boolean(response.config?.google?.enabled ?? true));
      setGoogleCallbackUrl("");
      onUpdated?.();
    } catch (error) {
      setGoogleStatusValue("invalid");
      setGoogleError(error instanceof Error ? error.message : sozluk.integrations.googleAuthError);
    } finally {
      setGoogleBusy(false);
    }
  }

  async function cancelGoogleAuthFlow() {
    if (!window.lawcopilotDesktop?.cancelGoogleAuth) {
      return;
    }
    const status = (await window.lawcopilotDesktop.cancelGoogleAuth()) as GoogleAuthStatus;
    applyGoogleStatus(status, sozluk.integrations.googleAuthCancelled);
  }

  async function disconnectGoogle() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setGoogleError(sozluk.integrations.desktopOnly);
      return;
    }
    setGoogleBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        google: {
          enabled: false,
          accountLabel: "",
          scopes: [],
          oauthConnected: false,
          oauthLastError: "",
          validationStatus: "pending",
          accessToken: "",
          refreshToken: "",
          tokenType: "",
          expiryDate: "",
        },
      });
      applyGoogleStatus({ configured: false, clientReady: googleClientReady, scopes: [], message: sozluk.integrations.googleDisconnected });
      setGoogleEnabled(false);
      onUpdated?.();
    } catch (error) {
      setGoogleError(error instanceof Error ? error.message : sozluk.integrations.googleDisconnectError);
    } finally {
      setGoogleBusy(false);
    }
  }

  async function syncGoogleNow() {
    if (!window.lawcopilotDesktop?.syncGoogleData) {
      setGoogleError(sozluk.integrations.desktopOnly);
      return;
    }
    setGoogleBusy(true);
    try {
      const result = (await window.lawcopilotDesktop.syncGoogleData()) as { message?: string };
      setGoogleStatusMessage(String(result.message || sozluk.integrations.syncNow));
      setGoogleError("");
      onUpdated?.();
    } catch (error) {
      setGoogleError(error instanceof Error ? error.message : sozluk.integrations.googleSyncError);
    } finally {
      setGoogleBusy(false);
    }
  }

  async function saveCodexModel() {
    if (!window.lawcopilotDesktop?.setCodexModel) {
      setProviderError(sozluk.integrations.desktopOnly);
      return;
    }
    setCodexBusy(true);
    try {
      const response = (await window.lawcopilotDesktop.setCodexModel(providerModel)) as {
        status?: CodexAuthStatus;
        config?: SanitizedIntegrationConfig;
      };
      applyCodexStatus(response.status || {}, sozluk.integrations.codexModelSaved);
      setProviderError("");
    } catch (error) {
      setProviderError(error instanceof Error ? error.message : sozluk.integrations.codexModelSaveError);
    } finally {
      setCodexBusy(false);
    }
  }

  async function validateProvider() {
    if (providerUsesBrowserAuth) {
      await refreshCodexStatus();
      return;
    }
    if (!window.lawcopilotDesktop?.validateProviderConfig) {
      setProviderError(sozluk.integrations.desktopOnly);
      return;
    }
    setProviderBusy(true);
    try {
      const response = (await window.lawcopilotDesktop.validateProviderConfig({
        type: providerType,
        baseUrl: providerBaseUrl,
        model: providerModel,
        apiKey: providerApiKey,
      })) as { message?: string; provider?: { availableModels?: string[]; baseUrl?: string; model?: string; validationStatus?: string } };
      setProviderStatusMessage(String(response.message || sozluk.integrations.providerValidated));
      setProviderStatusValue(String(response.provider?.validationStatus || "valid"));
      setProviderAvailableModels(Array.isArray(response.provider?.availableModels) ? response.provider?.availableModels || [] : []);
      if (response.provider?.baseUrl) {
        setProviderBaseUrl(String(response.provider.baseUrl));
      }
      if (!providerModel && response.provider?.model) {
        setProviderModel(String(response.provider.model));
      }
      setProviderError("");
    } catch (error) {
      setProviderStatusMessage("");
      setProviderStatusValue("invalid");
      setProviderError(error instanceof Error ? error.message : sozluk.integrations.providerValidateError);
    } finally {
      setProviderBusy(false);
    }
  }

  async function saveProvider() {
    if (providerUsesBrowserAuth) {
      await saveCodexModel();
      return;
    }
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setProviderError(sozluk.integrations.desktopOnly);
      return;
    }
    try {
      const saved = (await window.lawcopilotDesktop.saveIntegrationConfig({
        provider: {
          type: providerType,
          authMode: "api-key",
          baseUrl: providerBaseUrl,
          model: providerModel,
          availableModels: providerAvailableModels,
          oauthConnected: false,
          oauthLastError: "",
          ...(providerApiKey ? { apiKey: providerApiKey } : {}),
          configuredAt: new Date().toISOString(),
          validationStatus: providerStatusValue === "valid" ? "valid" : "pending",
        },
      })) as SanitizedIntegrationConfig;
      setProviderMaskedKey(String(saved.provider?.apiKeyMasked || ""));
      setProviderStatusMessage(sozluk.integrations.providerSaved);
      setProviderError("");
      setProviderApiKey("");
      onUpdated?.();
    } catch (error) {
      setProviderError(error instanceof Error ? error.message : sozluk.integrations.providerSaveError);
    }
  }

  async function validateTelegram() {
    if (!window.lawcopilotDesktop?.validateTelegramConfig) {
      setTelegramError(sozluk.integrations.desktopOnly);
      return;
    }
    setTelegramBusy(true);
    try {
      const response = (await window.lawcopilotDesktop.validateTelegramConfig({
        enabled: telegramEnabled,
        botToken: telegramBotToken,
        allowedUserId: telegramAllowedUserId,
      })) as { message?: string; telegram?: { botUsername?: string; validationStatus?: string } };
      setTelegramStatusMessage(String(response.message || sozluk.integrations.telegramValidated));
      setTelegramStatusValue(String(response.telegram?.validationStatus || "valid"));
      setTelegramBotUsername(String(response.telegram?.botUsername || telegramBotUsername));
      setTelegramError("");
    } catch (error) {
      setTelegramStatusMessage("");
      setTelegramStatusValue("invalid");
      setTelegramError(error instanceof Error ? error.message : sozluk.integrations.telegramValidateError);
    } finally {
      setTelegramBusy(false);
    }
  }

  async function saveTelegram() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setTelegramError(sozluk.integrations.desktopOnly);
      return;
    }
    try {
      const saved = (await window.lawcopilotDesktop.saveIntegrationConfig({
        telegram: {
          enabled: telegramEnabled,
          ...(telegramBotToken ? { botToken: telegramBotToken } : {}),
          allowedUserId: telegramAllowedUserId,
          botUsername: telegramBotUsername,
          configuredAt: new Date().toISOString(),
          validationStatus: telegramStatusValue === "valid" ? "valid" : "pending",
        },
      })) as SanitizedIntegrationConfig;
      setTelegramMaskedToken(String(saved.telegram?.botTokenMasked || ""));
      setTelegramStatusMessage(sozluk.integrations.telegramSaved);
      setTelegramError("");
      setTelegramBotToken("");
      onUpdated?.();
    } catch (error) {
      setTelegramError(error instanceof Error ? error.message : sozluk.integrations.telegramSaveError);
    }
  }

  async function refreshWhatsAppStatus() {
    if (!window.lawcopilotDesktop?.getWhatsAppStatus) {
      setWhatsAppError(sozluk.integrations.desktopOnly);
      return;
    }
    setWhatsAppBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.getWhatsAppStatus()) as WhatsAppAuthStatus;
      applyWhatsAppStatus(status, sozluk.integrations.whatsappIdle);
    } catch (error) {
      setWhatsAppStatusValue("invalid");
      setWhatsAppError(error instanceof Error ? error.message : sozluk.integrations.whatsappValidateError);
    } finally {
      setWhatsAppBusy(false);
    }
  }

  async function validateWhatsApp() {
    if (!window.lawcopilotDesktop?.validateWhatsAppConfig) {
      setWhatsAppError(sozluk.integrations.desktopOnly);
      return;
    }
    setWhatsAppBusy(true);
    try {
      const response = (await window.lawcopilotDesktop.validateWhatsAppConfig({
        enabled: true,
        accessToken: whatsAppAccessToken,
        phoneNumberId: whatsAppPhoneNumberId,
        businessLabel: whatsAppBusinessLabel,
      })) as { message?: string; whatsapp?: WhatsAppAuthStatus };
      applyWhatsAppStatus({ ...(response.whatsapp || {}), configured: true }, response.message || sozluk.integrations.whatsappValidated);
      setWhatsAppError("");
    } catch (error) {
      setWhatsAppStatusValue("invalid");
      setWhatsAppStatusMessage("");
      setWhatsAppError(error instanceof Error ? error.message : sozluk.integrations.whatsappValidateError);
    } finally {
      setWhatsAppBusy(false);
    }
  }

  function handleWhatsAppBundleChange(nextValue: string) {
    setWhatsAppSetupBundle(nextValue);
    const parsed = parseWhatsAppSetupBundle(nextValue);
    if (parsed.businessLabel) {
      setWhatsAppBusinessLabel(parsed.businessLabel);
    }
    if (parsed.phoneNumberId) {
      setWhatsAppPhoneNumberId(parsed.phoneNumberId);
    }
    if (parsed.accessToken) {
      setWhatsAppAccessToken(parsed.accessToken);
    }
  }

  async function saveWhatsApp() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setWhatsAppError(sozluk.integrations.desktopOnly);
      return;
    }
    setWhatsAppBusy(true);
    try {
      const saved = (await window.lawcopilotDesktop.saveIntegrationConfig({
        whatsapp: {
          enabled: true,
          ...(whatsAppAccessToken ? { accessToken: whatsAppAccessToken } : {}),
          phoneNumberId: whatsAppPhoneNumberId,
          businessLabel: whatsAppBusinessLabel,
          displayPhoneNumber: whatsAppDisplayNumber,
          verifiedName: whatsAppVerifiedName,
          configuredAt: new Date().toISOString(),
          validationStatus: whatsAppStatusValue === "valid" ? "valid" : "pending",
        },
      })) as SanitizedIntegrationConfig;
      setWhatsAppMaskedToken(String(saved.whatsapp?.accessTokenMasked || ""));
      setWhatsAppStatusMessage(sozluk.integrations.whatsappSaved);
      setWhatsAppError("");
      setWhatsAppAccessToken("");
      setWhatsAppSetupBundle("");
      onUpdated?.();
    } catch (error) {
      setWhatsAppError(error instanceof Error ? error.message : sozluk.integrations.whatsappSaveError);
    } finally {
      setWhatsAppBusy(false);
    }
  }

  async function syncWhatsApp() {
    if (!window.lawcopilotDesktop?.syncWhatsAppData) {
      setWhatsAppError(sozluk.integrations.desktopOnly);
      return;
    }
    setWhatsAppBusy(true);
    try {
      const result = (await window.lawcopilotDesktop.syncWhatsAppData()) as { message?: string; patch?: { whatsapp?: { lastSyncAt?: string } } };
      setWhatsAppStatusMessage(String(result.message || sozluk.integrations.whatsappSynced));
      setWhatsAppLastSyncAt(String(result.patch?.whatsapp?.lastSyncAt || new Date().toISOString()));
      setWhatsAppError("");
      onUpdated?.();
    } catch (error) {
      setWhatsAppError(error instanceof Error ? error.message : sozluk.integrations.whatsappSyncError);
    } finally {
      setWhatsAppBusy(false);
    }
  }

  async function disconnectWhatsApp() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setWhatsAppError(sozluk.integrations.desktopOnly);
      return;
    }
    setWhatsAppBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        whatsapp: {
          enabled: false,
          accessToken: "",
          phoneNumberId: "",
          businessLabel: "",
          displayPhoneNumber: "",
          verifiedName: "",
          validationStatus: "pending",
        },
      });
      applyWhatsAppStatus({ configured: false, enabled: false, message: sozluk.integrations.whatsappDisconnected });
      setWhatsAppMaskedToken("");
      setWhatsAppSetupBundle("");
      onUpdated?.();
    } catch (error) {
      setWhatsAppError(error instanceof Error ? error.message : sozluk.integrations.whatsappDisconnectError);
    } finally {
      setWhatsAppBusy(false);
    }
  }

  async function refreshXStatus() {
    if (!window.lawcopilotDesktop?.getXAuthStatus) {
      setXError(sozluk.integrations.desktopOnly);
      return;
    }
    setXBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.getXAuthStatus()) as XAuthStatus;
      applyXStatus(status, sozluk.integrations.xIdle);
    } catch (error) {
      setXStatusValue("invalid");
      setXError(error instanceof Error ? error.message : sozluk.integrations.xAuthError);
    } finally {
      setXBusy(false);
    }
  }

  async function saveXClientSetup() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setXError(sozluk.integrations.desktopOnly);
      return;
    }
    if (!xClientId.trim() || !xClientSecret.trim()) {
      setXError(sozluk.integrations.xClientSetupRequired);
      return;
    }
    setXBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        x: {
          clientId: xClientId.trim(),
          clientSecret: xClientSecret.trim(),
        },
      });
      setXClientId("");
      setXClientSecret("");
      await refreshXStatus();
      setXError("");
      setXStatusMessage(sozluk.integrations.xClientSaved);
    } catch (error) {
      setXError(error instanceof Error ? error.message : sozluk.integrations.xClientSaveError);
    } finally {
      setXBusy(false);
    }
  }

  async function startXAuthFlow() {
    if (!window.lawcopilotDesktop?.startXAuth) {
      setXError(sozluk.integrations.desktopOnly);
      return;
    }
    setXBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.startXAuth()) as XAuthStatus;
      applyXStatus(status, sozluk.integrations.xConnected);
      setXEnabled(true);
      onUpdated?.();
    } catch (error) {
      setXStatusValue("invalid");
      setXError(error instanceof Error ? error.message : sozluk.integrations.xAuthError);
    } finally {
      setXBusy(false);
    }
  }

  async function syncX() {
    if (!window.lawcopilotDesktop?.syncXData) {
      setXError(sozluk.integrations.desktopOnly);
      return;
    }
    setXBusy(true);
    try {
      const result = (await window.lawcopilotDesktop.syncXData()) as { message?: string; patch?: { x?: { lastSyncAt?: string } } };
      setXStatusMessage(String(result.message || sozluk.integrations.xSynced));
      setXLastSyncAt(String(result.patch?.x?.lastSyncAt || new Date().toISOString()));
      setXError("");
      onUpdated?.();
    } catch (error) {
      setXError(error instanceof Error ? error.message : sozluk.integrations.xSyncError);
    } finally {
      setXBusy(false);
    }
  }

  async function disconnectX() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setXError(sozluk.integrations.desktopOnly);
      return;
    }
    setXBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        x: {
          enabled: false,
          accountLabel: "",
          userId: "",
          scopes: [],
          oauthConnected: false,
          oauthLastError: "",
          validationStatus: "pending",
          accessToken: "",
          refreshToken: "",
          tokenType: "",
          expiryDate: "",
        },
      });
      applyXStatus({ configured: false, clientReady: xClientReady, scopes: [], message: sozluk.integrations.xDisconnected });
      setXEnabled(false);
      onUpdated?.();
    } catch (error) {
      setXError(error instanceof Error ? error.message : sozluk.integrations.xDisconnectError);
    } finally {
      setXBusy(false);
    }
  }

  async function sendTelegramTest() {
    if (!window.lawcopilotDesktop?.sendTelegramTestMessage) {
      setTelegramError(sozluk.integrations.desktopOnly);
      return;
    }
    setTelegramBusy(true);
    try {
      const response = (await window.lawcopilotDesktop.sendTelegramTestMessage({
        botToken: telegramBotToken,
        allowedUserId: telegramAllowedUserId,
        text: sozluk.integrations.telegramTestText,
      })) as { message?: string };
      setTelegramStatusMessage(String(response.message || sozluk.integrations.telegramTestSent));
      setTelegramError("");
    } catch (error) {
      setTelegramError(error instanceof Error ? error.message : sozluk.integrations.telegramTestError);
    } finally {
      setTelegramBusy(false);
    }
  }

  if (!desktopReady) {
    return <EmptyState title={sozluk.integrations.desktopOnlyTitle} description={sozluk.integrations.desktopOnlyDescription} />;
  }

  if (simpleMode) {
    return (
      <div className="setup-form-stack">
        <section className="setup-form-section" id="integration-provider" style={{ scrollMarginTop: "1rem" }}>
          <div className="setup-form-section__header">
            <div>
              <h3 className="setup-form-section__title">{sozluk.integrations.providerSimpleTitle}</h3>
              <p className="setup-form-section__meta">{sozluk.integrations.providerSimpleSubtitle}</p>
            </div>
            <div className="setup-form-section__badges">
              <StatusBadge tone="accent">{providerLabel(providerType)}</StatusBadge>
              <StatusBadge tone={validationTone(providerStatusValue)}>
                {providerStatusValue === "valid" ? sozluk.integrations.validated : sozluk.integrations.notValidated}
              </StatusBadge>
            </div>
          </div>

          <div className="setup-form-grid">
            <label className="setup-form-field">
              <span className="setup-form-field__label">{sozluk.integrations.providerTypeLabel}</span>
              <select
                className="select"
                value={providerType}
                onChange={(event) => {
                  const value = event.target.value;
                  const nextPreset = providerPreset(value);
                  setProviderType(value);
                  setProviderStatusMessage("");
                  setProviderError("");
                  setProviderAvailableModels([]);
                  setProviderMaskedKey("");
                  if (value === "openai-codex") {
                    setProviderBaseUrl("oauth://openai-codex");
                    setProviderModel("openai-codex/gpt-5.3-codex");
                    setProviderApiKey("");
                    void refreshCodexStatus();
                    return;
                  }
                  setCodexAuthUrl("");
                  setCodexBrowserTarget("");
                  setCodexConfigured(false);
                  setProviderBaseUrl(nextPreset.baseUrl);
                  setProviderModel(nextPreset.defaultModel);
                }}
              >
                <option value="openai">{sozluk.integrations.providerTypeOpenAI}</option>
                <option value="gemini">{sozluk.integrations.providerTypeGemini}</option>
                <option value="openai-compatible">{sozluk.integrations.providerTypeCompatible}</option>
                <option value="ollama">{sozluk.integrations.providerTypeOllama}</option>
                <option value="openai-codex">{sozluk.integrations.providerTypeCodex}</option>
              </select>
            </label>

            <label className="setup-form-field">
              <span className="setup-form-field__label">{sozluk.integrations.providerModelLabel}</span>
              {suggestedProviderModels.length ? (
                <select className="select" value={providerModel} onChange={(event) => setProviderModel(event.target.value)}>
                  {suggestedProviderModels.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              ) : (
                <input className="input" value={providerModel} onChange={(event) => setProviderModel(event.target.value)} />
              )}
            </label>

            {!providerUsesBrowserAuth && (providerType === "openai-compatible" || providerType === "ollama") ? (
              <label className="setup-form-field">
                <span className="setup-form-field__label">{sozluk.integrations.providerBaseUrlLabel}</span>
                <input className="input" value={providerBaseUrl} onChange={(event) => setProviderBaseUrl(event.target.value)} />
              </label>
            ) : null}

            {!providerUsesBrowserAuth && providerNeedsKey ? (
              <SecretField
                label={sozluk.integrations.providerApiKeyLabel}
                value={providerApiKey}
                onChange={setProviderApiKey}
                placeholder={providerMaskedKey || sozluk.integrations.providerApiKeyPlaceholder}
              />
            ) : null}

            {providerUsesBrowserAuth && showCodexCallback ? (
              <label className="setup-form-field setup-form-field--wide">
                <span className="setup-form-field__label">{sozluk.integrations.codexCallbackLabel}</span>
                <textarea
                  className="textarea"
                  value={codexCallbackUrl}
                  onChange={(event) => setCodexCallbackUrl(event.target.value)}
                  placeholder={sozluk.integrations.codexCallbackPlaceholder}
                  rows={3}
                />
              </label>
            ) : null}
          </div>

          <p className="setup-form-section__hint">
            {providerUsesBrowserAuth ? sozluk.integrations.providerSimpleBrowserHint : sozluk.integrations.providerSimpleKeyHint}
          </p>

          {providerUsesBrowserAuth && showCodexCallback && codexAuthUrl ? (
            <label className="setup-form-field">
              <span className="setup-form-field__label">{sozluk.integrations.codexAuthUrlLabel}</span>
              <input className="input" readOnly value={codexAuthUrl} />
            </label>
          ) : null}

          <div className="setup-form-actions">
            {providerUsesBrowserAuth ? (
              <>
                <button className="button" type="button" onClick={startCodexAuthFlow} disabled={codexBusy}>
                  {codexConfigured ? sozluk.integrations.providerReconnectAction : sozluk.integrations.providerConnectAction}
                </button>
                <button className="button button--secondary" type="button" onClick={refreshCodexStatus} disabled={codexBusy}>
                  {sozluk.integrations.refreshStatus}
                </button>
                {showCodexCallback ? (
                  <>
                    <button className="button button--secondary" type="button" onClick={submitCodexCallback} disabled={codexBusy || !codexCallbackUrl.trim()}>
                      {sozluk.integrations.codexSubmitCallback}
                    </button>
                    <button className="button button--secondary" type="button" onClick={cancelCodexAuthFlow} disabled={codexBusy}>
                      {sozluk.integrations.cancelCodexAuth}
                    </button>
                  </>
                ) : null}
                <button className="button button--secondary" type="button" onClick={saveProvider} disabled={codexBusy || !providerModel || !codexConfigured}>
                  {sozluk.integrations.codexSaveModel}
                </button>
              </>
            ) : (
              <>
                <button className="button button--secondary" type="button" onClick={validateProvider} disabled={providerBusy}>
                  {providerBusy ? sozluk.integrations.validating : sozluk.integrations.validateProvider}
                </button>
                <button className="button" type="button" onClick={saveProvider}>
                  {sozluk.integrations.saveProvider}
                </button>
              </>
            )}
          </div>

          {providerStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{providerStatusMessage}</p> : null}
          {providerError ? <p className="setup-form-feedback setup-form-feedback--error">{providerError}</p> : null}
        </section>

        <section className="setup-form-section" id="integration-google" style={{ scrollMarginTop: "1rem" }}>
          <div className="setup-form-section__header">
            <div>
              <h3 className="setup-form-section__title">{sozluk.integrations.googleSimpleTitle}</h3>
              <p className="setup-form-section__meta">{sozluk.integrations.googleSimpleSubtitle}</p>
            </div>
            <div className="setup-form-section__badges">
              <StatusBadge tone={googleConfigured ? "accent" : "warning"}>
                {googleConfigured ? sozluk.integrations.googleConnected : sozluk.integrations.googleNotConnected}
              </StatusBadge>
              {googleAccountLabel ? <StatusBadge>{googleAccountLabel}</StatusBadge> : null}
            </div>
          </div>

          <div className="setup-form-section__guide-row">
            <p className="setup-form-section__hint">{sozluk.integrations.googleSimpleAutoSync}</p>
            <a className="setup-form-guide-link" href={INTEGRATION_GUIDES.google} target="_blank" rel="noreferrer">
              {sozluk.integrations.googleGuideConsoleAction}
            </a>
          </div>

          <div className="setup-form-guide-box">
            <strong>{sozluk.integrations.googleGuideTitle}</strong>
            <p className="setup-form-guide-note">{sozluk.integrations.googleGuideIntro}</p>
            <ol className="setup-form-guide-list">
              <li>{sozluk.integrations.googleGuideStep1}</li>
              <li>{sozluk.integrations.googleGuideStep2}</li>
              <li>{sozluk.integrations.googleGuideStep3}</li>
              <li>{sozluk.integrations.googleGuideStep4}</li>
              <li>{sozluk.integrations.googleGuideStep5}</li>
              <li>{sozluk.integrations.googleGuideStep6}</li>
            </ol>
            <div className="setup-form-section__badges">
              <StatusBadge>{sozluk.integrations.googleGuideScopesTitle}</StatusBadge>
              <span className="setup-form-guide-code">{sozluk.integrations.googleGuideScopesValue}</span>
            </div>
            <p className="setup-form-guide-note">{sozluk.integrations.googleGuideAdminNote}</p>
          </div>

          {!googleClientReady ? (
            <div className="setup-form-subsection">
              <strong>{sozluk.integrations.googleClientSetupTitle}</strong>
              <p>{sozluk.integrations.googleClientSetupSubtitle}</p>
              <div className="setup-form-grid">
                <label className="setup-form-field">
                  <span className="setup-form-field__label">{sozluk.integrations.googleClientIdLabel}</span>
                  <input className="input" value={googleClientId} onChange={(event) => setGoogleClientId(event.target.value)} />
                </label>
                <SecretField
                  label={sozluk.integrations.googleClientSecretLabel}
                  value={googleClientSecret}
                  onChange={setGoogleClientSecret}
                />
              </div>
              <div className="setup-form-actions">
                <button className="button" type="button" onClick={saveGoogleClientSetup} disabled={googleBusy}>
                  {sozluk.integrations.googleClientSaveAction}
                </button>
              </div>
            </div>
          ) : null}

          <div className="setup-form-actions">
            <button className="button" type="button" onClick={startGoogleAuthFlow} disabled={googleBusy || !googleClientReady}>
              {googleConfigured ? sozluk.integrations.googleReconnectAction : sozluk.integrations.googleConnectAction}
            </button>
            {googleConfigured ? (
              <button className="button button--secondary" type="button" onClick={syncGoogleNow} disabled={googleBusy}>
                {sozluk.integrations.syncNow}
              </button>
            ) : null}
            <button className="button button--secondary" type="button" onClick={refreshGoogleStatus} disabled={googleBusy}>
              {sozluk.integrations.refreshStatus}
            </button>
            {googleConfigured ? (
              <button className="button button--secondary" type="button" onClick={disconnectGoogle} disabled={googleBusy}>
                {sozluk.integrations.disconnectAction}
              </button>
            ) : null}
          </div>

          {googleAuthUrl && !googleConfigured ? (
            <div className="setup-form-subsection">
              <strong>{sozluk.integrations.googleAuthUrlLabel}</strong>
              <p>{sozluk.integrations.googleManualOpenNote}</p>
              <label className="setup-form-field">
                <span className="setup-form-field__label">{sozluk.integrations.googleAuthUrlLabel}</span>
                <input className="input" readOnly value={googleAuthUrl} />
              </label>
              {googleBrowserTarget ? <p className="setup-form-section__hint">{`Tarayıcı hedefi: ${googleBrowserTarget}`}</p> : null}
            </div>
          ) : null}

          {googleStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{googleStatusMessage}</p> : null}
          {googleError ? <p className="setup-form-feedback setup-form-feedback--error">{googleError}</p> : null}
        </section>

        <section className="setup-form-section" id="integration-telegram" style={{ scrollMarginTop: "1rem" }}>
          <div className="setup-form-section__header">
            <div>
              <h3 className="setup-form-section__title">{sozluk.integrations.telegramSimpleTitle}</h3>
              <p className="setup-form-section__meta">{sozluk.integrations.telegramSimpleSubtitle}</p>
            </div>
            <div className="setup-form-section__badges">
              <StatusBadge tone={telegramStatusValue === "valid" ? "accent" : "warning"}>
                {telegramStatusValue === "valid" ? sozluk.integrations.validated : sozluk.integrations.notValidated}
              </StatusBadge>
              {telegramBotUsername ? <StatusBadge>{telegramBotUsername}</StatusBadge> : null}
            </div>
          </div>

          <div className="setup-form-section__guide-row">
            <p className="setup-form-section__hint">{sozluk.integrations.telegramSimpleHint}</p>
            <a className="setup-form-guide-link" href={INTEGRATION_GUIDES.telegram} target="_blank" rel="noreferrer">
              BotFather aç
            </a>
          </div>

          <div className="setup-form-grid">
            <SecretField
              label={sozluk.integrations.telegramBotTokenLabel}
              value={telegramBotToken}
              onChange={setTelegramBotToken}
              placeholder={telegramMaskedToken || sozluk.integrations.telegramBotTokenPlaceholder}
            />
            <label className="setup-form-field">
              <span className="setup-form-field__label">{sozluk.integrations.telegramUserIdLabel}</span>
              <input className="input" value={telegramAllowedUserId} onChange={(event) => setTelegramAllowedUserId(event.target.value)} />
            </label>
          </div>

          <div className="setup-form-actions">
            <button className="button button--secondary" type="button" onClick={validateTelegram} disabled={telegramBusy}>
              {telegramBusy ? sozluk.integrations.validating : sozluk.integrations.validateTelegram}
            </button>
            <button className="button button--secondary" type="button" onClick={sendTelegramTest} disabled={telegramBusy || !telegramAllowedUserId}>
              {sozluk.integrations.sendTelegramTest}
            </button>
            <button className="button" type="button" onClick={saveTelegram}>
              {sozluk.integrations.saveTelegram}
            </button>
          </div>

          {telegramStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{telegramStatusMessage}</p> : null}
          {telegramError ? <p className="setup-form-feedback setup-form-feedback--error">{telegramError}</p> : null}
        </section>

        <section className="setup-form-section" id="integration-whatsapp" style={{ scrollMarginTop: "1rem" }}>
          <div className="setup-form-section__header">
            <div>
              <h3 className="setup-form-section__title">{sozluk.integrations.whatsappTitle}</h3>
              <p className="setup-form-section__meta">{sozluk.integrations.whatsappSubtitle}</p>
            </div>
            <div className="setup-form-section__badges">
              <StatusBadge tone={whatsAppStatusValue === "valid" ? "accent" : "warning"}>
                {whatsAppStatusValue === "valid" ? sozluk.integrations.validated : sozluk.integrations.notValidated}
              </StatusBadge>
              {whatsAppDisplayNumber ? <StatusBadge>{whatsAppDisplayNumber}</StatusBadge> : null}
            </div>
          </div>

          <div className="setup-form-section__guide-row">
            <p className="setup-form-section__hint">{sozluk.integrations.whatsappGuidedHint}</p>
            <a className="setup-form-guide-link" href={INTEGRATION_GUIDES.whatsapp} target="_blank" rel="noreferrer">
              Meta rehberi
            </a>
          </div>

          <label className="setup-form-field setup-form-field--wide">
            <span className="setup-form-field__label">{sozluk.integrations.whatsappPasteLabel}</span>
            <textarea
              className="textarea"
              rows={4}
              value={whatsAppSetupBundle}
              onChange={(event) => handleWhatsAppBundleChange(event.target.value)}
              placeholder={sozluk.integrations.whatsappPastePlaceholder}
            />
          </label>

          <div className="setup-form-grid">
            <label className="setup-form-field">
              <span className="setup-form-field__label">{sozluk.integrations.whatsappBusinessLabel}</span>
              <input className="input" value={whatsAppBusinessLabel} onChange={(event) => setWhatsAppBusinessLabel(event.target.value)} />
            </label>
            <label className="setup-form-field">
              <span className="setup-form-field__label">{sozluk.integrations.whatsappPhoneNumberId}</span>
              <input className="input" value={whatsAppPhoneNumberId} onChange={(event) => setWhatsAppPhoneNumberId(event.target.value)} />
            </label>
            <SecretField
              label={sozluk.integrations.whatsappAccessToken}
              value={whatsAppAccessToken}
              onChange={setWhatsAppAccessToken}
              placeholder={whatsAppMaskedToken || sozluk.integrations.whatsappAccessTokenPlaceholder}
            />
          </div>

          <p className="setup-form-section__hint">{sozluk.integrations.whatsappHint}</p>
          {whatsAppVerifiedName ? <p className="setup-form-section__hint">{`${sozluk.integrations.whatsappVerifiedName}: ${whatsAppVerifiedName}`}</p> : null}
          {whatsAppLastSyncAt ? <p className="setup-form-section__hint">{`${sozluk.integrations.lastSyncLabel}: ${new Date(whatsAppLastSyncAt).toLocaleString("tr-TR")}`}</p> : null}

          <div className="setup-form-actions">
            <button className="button button--secondary" type="button" onClick={validateWhatsApp} disabled={whatsAppBusy}>
              {whatsAppBusy ? sozluk.integrations.validating : sozluk.integrations.validateWhatsApp}
            </button>
            <button className="button" type="button" onClick={saveWhatsApp} disabled={whatsAppBusy}>
              {sozluk.integrations.saveWhatsApp}
            </button>
            <button className="button button--secondary" type="button" onClick={syncWhatsApp} disabled={whatsAppBusy || !whatsAppPhoneNumberId}>
              {sozluk.integrations.syncNow}
            </button>
            {(whatsAppMaskedToken || whatsAppAccessToken || whatsAppPhoneNumberId) ? (
              <button className="button button--secondary" type="button" onClick={disconnectWhatsApp} disabled={whatsAppBusy}>
                {sozluk.integrations.disconnectAction}
              </button>
            ) : null}
          </div>

          {whatsAppStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{whatsAppStatusMessage}</p> : null}
          {whatsAppError ? <p className="setup-form-feedback setup-form-feedback--error">{whatsAppError}</p> : null}
        </section>

        <section className="setup-form-section" id="integration-x" style={{ scrollMarginTop: "1rem" }}>
          <div className="setup-form-section__header">
            <div>
              <h3 className="setup-form-section__title">{sozluk.integrations.xTitle}</h3>
              <p className="setup-form-section__meta">{sozluk.integrations.xSubtitle}</p>
            </div>
            <div className="setup-form-section__badges">
              <StatusBadge tone={xConfigured ? "accent" : "warning"}>
                {xConfigured ? sozluk.integrations.xConnected : sozluk.integrations.xNotConnected}
              </StatusBadge>
              {xAccountLabel ? <StatusBadge>{xAccountLabel}</StatusBadge> : null}
            </div>
          </div>

          <div className="setup-form-section__guide-row">
            <p className="setup-form-section__hint">{sozluk.integrations.xHint}</p>
            <a className="setup-form-guide-link" href={INTEGRATION_GUIDES.x} target="_blank" rel="noreferrer">
              X geliştirici paneli
            </a>
          </div>

          {!xClientReady ? (
            <div className="setup-form-subsection">
              <strong>{sozluk.integrations.xClientSetupTitle}</strong>
              <p>{sozluk.integrations.xClientSetupSubtitle}</p>
              <div className="setup-form-grid">
                <label className="setup-form-field">
                  <span className="setup-form-field__label">{sozluk.integrations.xClientIdLabel}</span>
                  <input className="input" value={xClientId} onChange={(event) => setXClientId(event.target.value)} />
                </label>
                <SecretField
                  label={sozluk.integrations.xClientSecretLabel}
                  value={xClientSecret}
                  onChange={setXClientSecret}
                />
              </div>
              <div className="setup-form-actions">
                <button className="button" type="button" onClick={saveXClientSetup} disabled={xBusy}>
                  {sozluk.integrations.xClientSaveAction}
                </button>
              </div>
            </div>
          ) : null}

          {xLastSyncAt ? <p className="setup-form-section__hint">{`${sozluk.integrations.lastSyncLabel}: ${new Date(xLastSyncAt).toLocaleString("tr-TR")}`}</p> : null}

          <div className="setup-form-actions">
            <button className="button" type="button" onClick={startXAuthFlow} disabled={xBusy || !xClientReady}>
              {xConfigured ? sozluk.integrations.xReconnectAction : sozluk.integrations.xConnectAction}
            </button>
            <button className="button button--secondary" type="button" onClick={syncX} disabled={xBusy || !xConfigured}>
              {sozluk.integrations.syncNow}
            </button>
            <button className="button button--secondary" type="button" onClick={refreshXStatus} disabled={xBusy}>
              {sozluk.integrations.refreshStatus}
            </button>
            {xConfigured ? (
              <button className="button button--secondary" type="button" onClick={disconnectX} disabled={xBusy}>
                {sozluk.integrations.disconnectAction}
              </button>
            ) : null}
          </div>

          {xStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{xStatusMessage}</p> : null}
          {xError ? <p className="setup-form-feedback setup-form-feedback--error">{xError}</p> : null}
        </section>
      </div>
    );
  }

  return (
    <div className="stack">
      <div id="integration-provider" style={{ scrollMarginTop: "1rem" }}>
      <SectionCard title={sozluk.integrations.providerTitle} subtitle={providerSubtitle}>
        <div className="field-grid">
          <label className="stack stack--tight">
            <span>{sozluk.integrations.providerTypeLabel}</span>
            <select
              className="select"
              value={providerType}
              onChange={(event) => {
                const value = event.target.value;
                const nextPreset = providerPreset(value);
                setProviderType(value);
                setProviderStatusMessage("");
                setProviderError("");
                setProviderAvailableModels([]);
                setProviderMaskedKey("");
                if (value === "openai-codex") {
                  setProviderBaseUrl("oauth://openai-codex");
                  setProviderModel("openai-codex/gpt-5.3-codex");
                  setProviderApiKey("");
                  void refreshCodexStatus();
                  return;
                }
                setCodexAuthUrl("");
                setCodexBrowserTarget("");
                setCodexConfigured(false);
                setProviderBaseUrl(nextPreset.baseUrl);
                setProviderModel(nextPreset.defaultModel);
              }}
            >
              <option value="openai">{sozluk.integrations.providerTypeOpenAI}</option>
              <option value="gemini">{sozluk.integrations.providerTypeGemini}</option>
              <option value="openai-compatible">{sozluk.integrations.providerTypeCompatible}</option>
              <option value="ollama">{sozluk.integrations.providerTypeOllama}</option>
              <option value="openai-codex">{sozluk.integrations.providerTypeCodex}</option>
            </select>
          </label>

          {providerUsesBrowserAuth ? (
            <>
              <div className="callout callout--accent">
                <strong>{sozluk.integrations.providerAuthModeLabel}</strong>
                <p style={{ marginBottom: "0.4rem" }}>{sozluk.integrations.providerAuthModeBrowser}</p>
                <p style={{ marginBottom: 0 }}>{sozluk.integrations.codexBrowserAuthNote}</p>
              </div>

              <label className="stack stack--tight">
                <span>{sozluk.integrations.providerModelLabel}</span>
                <select
                  className="select"
                  value={providerModel}
                  onChange={(event) => setProviderModel(event.target.value)}
                  disabled={!providerAvailableModels.length}
                >
                  {providerAvailableModels.length ? (
                    providerAvailableModels.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))
                  ) : (
                    <option value={providerModel || "openai-codex/gpt-5.3-codex"}>{providerModel || "openai-codex/gpt-5.3-codex"}</option>
                  )}
                </select>
              </label>

              <label className="stack stack--tight">
                <span>{sozluk.integrations.codexCallbackLabel}</span>
                <textarea
                  className="textarea"
                  value={codexCallbackUrl}
                  onChange={(event) => setCodexCallbackUrl(event.target.value)}
                  placeholder={sozluk.integrations.codexCallbackPlaceholder}
                  rows={3}
                />
              </label>

              <div className="toolbar">
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <StatusBadge tone="accent">{providerLabel(providerType)}</StatusBadge>
                  <StatusBadge tone={validationTone(providerStatusValue)}>
                    {providerStatusValue === "valid" ? sozluk.integrations.validated : sozluk.integrations.notValidated}
                  </StatusBadge>
                  {codexConfigured ? <StatusBadge tone="accent">{sozluk.integrations.codexAuthConnected}</StatusBadge> : null}
                  {codexBrowserTarget ? <StatusBadge>{`${sozluk.integrations.codexBrowserOpened}: ${codexBrowserTarget}`}</StatusBadge> : null}
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button className="button button--secondary" type="button" onClick={startCodexAuthFlow} disabled={codexBusy}>
                    {codexBusy ? sozluk.integrations.validating : sozluk.integrations.startCodexAuth}
                  </button>
                  <button className="button button--secondary" type="button" onClick={refreshCodexStatus} disabled={codexBusy}>
                    {sozluk.integrations.refreshCodexAuth}
                  </button>
                  <button className="button button--secondary" type="button" onClick={submitCodexCallback} disabled={codexBusy || !codexCallbackUrl.trim()}>
                    {sozluk.integrations.codexSubmitCallback}
                  </button>
                  <button className="button button--secondary" type="button" onClick={cancelCodexAuthFlow} disabled={codexBusy}>
                    {sozluk.integrations.cancelCodexAuth}
                  </button>
                  <button className="button" type="button" onClick={saveProvider} disabled={codexBusy || !providerModel || !codexConfigured}>
                    {sozluk.integrations.codexSaveModel}
                  </button>
                </div>
              </div>

              {codexAuthUrl ? (
                <label className="stack stack--tight">
                  <span>{sozluk.integrations.codexAuthUrlLabel}</span>
                  <input className="input" readOnly value={codexAuthUrl} />
                </label>
              ) : null}

              {providerAvailableModels.length ? (
                <div className="stack stack--tight">
                  <strong>{sozluk.integrations.codexAvailableModelsTitle}</strong>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    {providerAvailableModels.map((item) => (
                      <StatusBadge key={item}>{item}</StatusBadge>
                    ))}
                  </div>
                </div>
              ) : null}

              <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.codexManualOpenNote}</p>
            </>
          ) : (
            <>
              <label className="stack stack--tight">
                <span>{sozluk.integrations.providerBaseUrlLabel}</span>
                <input className="input" value={providerBaseUrl} onChange={(event) => setProviderBaseUrl(event.target.value)} />
              </label>
              <label className="stack stack--tight">
                <span>{sozluk.integrations.providerModelLabel}</span>
                {suggestedProviderModels.length ? (
                  <select className="select" value={providerModel} onChange={(event) => setProviderModel(event.target.value)}>
                    {suggestedProviderModels.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input className="input" value={providerModel} onChange={(event) => setProviderModel(event.target.value)} />
                )}
              </label>
              {providerNeedsKey ? (
                <label className="stack stack--tight">
                  <span>{sozluk.integrations.providerApiKeyLabel}</span>
                  <input
                    className="input"
                    type="password"
                    value={providerApiKey}
                    onChange={(event) => setProviderApiKey(event.target.value)}
                    placeholder={providerMaskedKey || sozluk.integrations.providerApiKeyPlaceholder}
                  />
                </label>
              ) : null}
              <div className="toolbar">
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <StatusBadge tone="accent">{providerLabel(providerType)}</StatusBadge>
                  <StatusBadge tone={validationTone(providerStatusValue)}>
                    {providerStatusValue === "valid" ? sozluk.integrations.validated : sozluk.integrations.notValidated}
                  </StatusBadge>
                  {providerMaskedKey ? <StatusBadge>{providerMaskedKey}</StatusBadge> : null}
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button className="button button--secondary" type="button" onClick={validateProvider} disabled={providerBusy}>
                    {providerBusy ? sozluk.integrations.validating : sozluk.integrations.validateProvider}
                  </button>
                  <button className="button" type="button" onClick={saveProvider}>
                    {sozluk.integrations.saveProvider}
                  </button>
                </div>
              </div>
              <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.providerBrowserAuthNote}</p>
              {suggestedProviderModels.length ? (
                <div className="stack stack--tight">
                  <strong>{providerAvailableModels.length ? sozluk.integrations.availableModelsTitle : "Başlangıç model seçenekleri"}</strong>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    {suggestedProviderModels.map((item) => (
                      <StatusBadge key={item}>{item}</StatusBadge>
                    ))}
                  </div>
                </div>
              ) : null}
              {providerType === "gemini" ? (
                <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>
                  Gemini için masaüstü köprüsü model listesini döndürmezse başlangıç önerileri gösterilir; doğrulama hazır değilse ayarı yine de kaydedebilirsiniz.
                </p>
              ) : null}
            </>
          )}
          {providerStatusMessage ? <p style={{ color: "var(--accent)", marginBottom: 0 }}>{providerStatusMessage}</p> : null}
          {providerError ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{providerError}</p> : null}
        </div>
      </SectionCard>
      </div>

      <div id="integration-google" style={{ scrollMarginTop: "1rem" }}>
      <SectionCard title={sozluk.integrations.googleTitle} subtitle={sozluk.integrations.googleSubtitle}>
        <div className="field-grid">
          <div className="callout callout--accent">
            <strong>{sozluk.integrations.googleScopesTitle}</strong>
            <p style={{ marginBottom: 0 }}>{sozluk.integrations.googleScopesDescription}</p>
          </div>
          <label className="stack stack--tight">
            <span>{sozluk.integrations.googleCallbackLabel}</span>
            <textarea
              className="textarea"
              value={googleCallbackUrl}
              onChange={(event) => setGoogleCallbackUrl(event.target.value)}
              placeholder={sozluk.integrations.googleCallbackPlaceholder}
              rows={3}
            />
          </label>
          <div className="toolbar">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <StatusBadge tone={googleConfigured ? "accent" : "warning"}>
                {googleConfigured ? sozluk.integrations.googleConnected : sozluk.integrations.googleNotConnected}
              </StatusBadge>
              <StatusBadge tone={googleClientReady ? "accent" : "warning"}>
                {googleClientReady ? sozluk.integrations.googleClientReady : sozluk.integrations.googleClientMissing}
              </StatusBadge>
              {googleAccountLabel ? <StatusBadge>{googleAccountLabel}</StatusBadge> : null}
              {googleEnabled ? <StatusBadge tone="accent">{sozluk.integrations.googleEnabled}</StatusBadge> : null}
              <StatusBadge tone={googleHasGmail ? "accent" : "warning"}>Gmail</StatusBadge>
              <StatusBadge tone={googleHasCalendar ? "accent" : "warning"}>Takvim</StatusBadge>
              <StatusBadge tone={googleHasDrive ? "accent" : "warning"}>Drive</StatusBadge>
              {googleBrowserTarget ? <StatusBadge>{`${sozluk.integrations.codexBrowserOpened}: ${googleBrowserTarget}`}</StatusBadge> : null}
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button className="button button--secondary" type="button" onClick={startGoogleAuthFlow} disabled={googleBusy || !googleClientReady}>
                {googleBusy ? sozluk.integrations.validating : sozluk.integrations.googleStartAuth}
              </button>
              <button className="button button--secondary" type="button" onClick={refreshGoogleStatus} disabled={googleBusy}>
                {sozluk.integrations.googleRefreshAuth}
              </button>
              <button className="button button--secondary" type="button" onClick={submitGoogleCallback} disabled={googleBusy || !googleCallbackUrl.trim()}>
                {sozluk.integrations.googleCompleteAuth}
              </button>
              <button className="button" type="button" onClick={cancelGoogleAuthFlow} disabled={googleBusy}>
                {sozluk.integrations.googleCancelAuth}
              </button>
            </div>
          </div>
          {googleAuthUrl ? (
            <label className="stack stack--tight">
              <span>{sozluk.integrations.googleAuthUrlLabel}</span>
              <input className="input" readOnly value={googleAuthUrl} />
            </label>
          ) : null}
          {googleScopes.length ? (
            <div className="stack stack--tight">
              <strong>{sozluk.integrations.googleGrantedScopesTitle}</strong>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                {googleScopes.map((scope) => (
                  <StatusBadge key={scope}>{asistanAracKapsamEtiketi(scope)}</StatusBadge>
                ))}
              </div>
            </div>
          ) : null}
          <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.googleNote}</p>
          {googleStatusMessage ? <p style={{ color: "var(--accent)", marginBottom: 0 }}>{googleStatusMessage}</p> : null}
          {googleError ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{googleError}</p> : null}
        </div>
      </SectionCard>
      </div>

      <div id="integration-telegram" style={{ scrollMarginTop: "1rem" }}>
      <SectionCard title={sozluk.integrations.telegramTitle} subtitle={sozluk.integrations.telegramSubtitle}>
        <div className="field-grid">
          <label className="stack stack--tight">
            <span>{sozluk.integrations.telegramEnableLabel}</span>
            <select className="select" value={telegramEnabled ? "true" : "false"} onChange={(event) => setTelegramEnabled(event.target.value === "true")}>
              <option value="false">{sozluk.integrations.telegramDisabled}</option>
              <option value="true">{sozluk.integrations.telegramEnabled}</option>
            </select>
          </label>
          <label className="stack stack--tight">
            <span>{sozluk.integrations.telegramBotTokenLabel}</span>
            <input
              className="input"
              type="password"
              value={telegramBotToken}
              onChange={(event) => setTelegramBotToken(event.target.value)}
              placeholder={telegramMaskedToken || sozluk.integrations.telegramBotTokenPlaceholder}
            />
          </label>
          <label className="stack stack--tight">
            <span>{sozluk.integrations.telegramUserIdLabel}</span>
            <input className="input" value={telegramAllowedUserId} onChange={(event) => setTelegramAllowedUserId(event.target.value)} />
          </label>
          <label className="stack stack--tight">
            <span>{sozluk.integrations.telegramBotNameLabel}</span>
            <input className="input" value={telegramBotUsername} onChange={(event) => setTelegramBotUsername(event.target.value)} />
          </label>
          <div className="toolbar">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <StatusBadge tone={telegramEnabled ? "accent" : "warning"}>
                {telegramEnabled ? sozluk.integrations.telegramEnabled : sozluk.integrations.telegramDisabled}
              </StatusBadge>
              <StatusBadge tone={validationTone(telegramStatusValue)}>
                {telegramStatusValue === "valid" ? sozluk.integrations.validated : sozluk.integrations.notValidated}
              </StatusBadge>
              {telegramMaskedToken ? <StatusBadge>{telegramMaskedToken}</StatusBadge> : null}
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button className="button button--secondary" type="button" onClick={validateTelegram} disabled={telegramBusy}>
                {telegramBusy ? sozluk.integrations.validating : sozluk.integrations.validateTelegram}
              </button>
              <button className="button button--secondary" type="button" onClick={sendTelegramTest} disabled={telegramBusy || !telegramAllowedUserId}>
                {sozluk.integrations.sendTelegramTest}
              </button>
              <button className="button" type="button" onClick={saveTelegram}>
                {sozluk.integrations.saveTelegram}
              </button>
            </div>
          </div>
          <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.telegramNote}</p>
          {telegramStatusMessage ? <p style={{ color: "var(--accent)", marginBottom: 0 }}>{telegramStatusMessage}</p> : null}
          {telegramError ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{telegramError}</p> : null}
        </div>
      </SectionCard>
      </div>
    </div>
  );
}
