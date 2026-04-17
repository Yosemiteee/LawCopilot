import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";
import { sozluk } from "../../i18n";
import { asistanAracKapsamEtiketi } from "../../lib/labels";
import { providerPresetCatalog, uniqueProviderModels } from "../../lib/providerCatalog";

const SETTINGS_MEMORY_UPDATE_EVENT = "lawcopilot:memory-updates";

type PanelMode = "simple" | "onboarding" | "settings" | "connectors";
type SetupSectionKey = "provider" | "google" | "outlook" | "telegram" | "whatsapp" | "x" | "instagram" | "linkedin";

type IntegrationSetupPanelProps = {
  mode?: PanelMode;
  onUpdated?: () => void;
  sections?: SetupSectionKey[];
};

type SanitizedIntegrationConfig = {
  runtimeWarning?: string;
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
  googlePortability?: {
    enabled?: boolean;
    accountLabel?: string;
    scopes?: string[];
    oauthConnected?: boolean;
    oauthLastError?: string;
    validationStatus?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    lastSyncAt?: string;
    lastImportedAt?: string;
    archiveJobId?: string;
    archiveState?: string;
    archiveStartedAt?: string;
    archiveExportTime?: string;
    accessTokenConfigured?: boolean;
    refreshTokenConfigured?: boolean;
    clientIdConfigured?: boolean;
    clientSecretConfigured?: boolean;
    youtubeHistoryAvailable?: boolean;
    youtubeHistoryCount?: number;
    chromeHistoryAvailable?: boolean;
    chromeHistoryCount?: number;
  };
  outlook?: {
    enabled?: boolean;
    accountLabel?: string;
    clientId?: string;
    tenantId?: string;
    scopes?: string[];
    oauthConnected?: boolean;
    oauthLastError?: string;
    validationStatus?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    lastSyncAt?: string;
    accessTokenConfigured?: boolean;
    refreshTokenConfigured?: boolean;
    clientIdConfigured?: boolean;
  };
  telegram?: {
    enabled?: boolean;
    mode?: string;
    accountLabel?: string;
    botUsername?: string;
    allowedUserId?: string;
    webSessionName?: string;
    webStatus?: string;
    webAccountLabel?: string;
    webLastReadyAt?: string;
    webLastSyncAt?: string;
    validationStatus?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    botTokenConfigured?: boolean;
    botTokenMasked?: string;
  };
  whatsapp?: {
    enabled?: boolean;
    mode?: string;
    businessLabel?: string;
    displayPhoneNumber?: string;
    verifiedName?: string;
    phoneNumberId?: string;
    webSessionName?: string;
    webStatus?: string;
    webAccountLabel?: string;
    webLastReadyAt?: string;
    webLastSyncAt?: string;
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
  linkedin?: {
    enabled?: boolean;
    mode?: string;
    accountLabel?: string;
    userId?: string;
    personUrn?: string;
    email?: string;
    scopes?: string[];
    oauthConnected?: boolean;
    oauthLastError?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    validationStatus?: string;
    lastSyncAt?: string;
    webSessionName?: string;
    webStatus?: string;
    webAccountLabel?: string;
    webLastReadyAt?: string;
    webLastSyncAt?: string;
    accessTokenConfigured?: boolean;
    clientIdConfigured?: boolean;
    clientSecretConfigured?: boolean;
  };
  instagram?: {
    enabled?: boolean;
    accountLabel?: string;
    username?: string;
    pageId?: string;
    pageName?: string;
    pageNameHint?: string;
    instagramAccountId?: string;
    scopes?: string[];
    oauthConnected?: boolean;
    oauthLastError?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    validationStatus?: string;
    lastSyncAt?: string;
    accessTokenConfigured?: boolean;
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
  catalogModels?: string[];
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

type GooglePortabilityAuthStatus = {
  authStatus?: string;
  message?: string;
  authUrl?: string;
  browserTarget?: string;
  configured?: boolean;
  accountLabel?: string;
  scopes?: string[];
  clientReady?: boolean;
  archiveJobId?: string;
  archiveState?: string;
  archiveStartedAt?: string;
  archiveExportTime?: string;
  lastSyncAt?: string;
  error?: string;
};

type OutlookAuthStatus = {
  authStatus?: string;
  message?: string;
  authUrl?: string;
  browserTarget?: string;
  configured?: boolean;
  accountLabel?: string;
  clientId?: string;
  tenantId?: string;
  scopes?: string[];
  clientReady?: boolean;
  error?: string;
};

type WhatsAppAuthStatus = {
  configured?: boolean;
  enabled?: boolean;
  mode?: string;
  accountLabel?: string;
  displayPhoneNumber?: string;
  verifiedName?: string;
  phoneNumberId?: string;
  validationStatus?: string;
  lastValidatedAt?: string;
  lastSyncAt?: string;
  webStatus?: string;
  webSessionName?: string;
  webQrDataUrl?: string;
  webQrReady?: boolean;
  webCurrentUser?: string;
  webAccountLabel?: string;
  webLastReadyAt?: string;
  webLastSyncAt?: string;
  webBrowserLabel?: string;
  webMessageCountMirrored?: number;
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

type LinkedInAuthStatus = {
  configured?: boolean;
  mode?: string;
  accountLabel?: string;
  userId?: string;
  personUrn?: string;
  email?: string;
  scopes?: string[];
  clientReady?: boolean;
  validationStatus?: string;
  lastSyncAt?: string;
  webSessionName?: string;
  webStatus?: string;
  webAccountLabel?: string;
  webLastReadyAt?: string;
  webLastSyncAt?: string;
  webMessageCountMirrored?: number;
  message?: string;
  error?: string;
};

type InstagramAuthStatus = {
  configured?: boolean;
  accountLabel?: string;
  username?: string;
  pageId?: string;
  pageName?: string;
  instagramAccountId?: string;
  pageNameHint?: string;
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

const PROVIDER_TYPE_OPTIONS = [
  { value: "openai", label: () => sozluk.integrations.providerTypeOpenAI },
  { value: "openai-codex", label: () => sozluk.integrations.providerTypeCodex },
  { value: "gemini", label: () => sozluk.integrations.providerTypeGemini },
  { value: "openai-compatible", label: () => sozluk.integrations.providerTypeCompatible },
  { value: "ollama", label: () => sozluk.integrations.providerTypeOllama },
] as const;

function validationTone(value: string) {
  if (value === "valid") {
    return "accent" as const;
  }
  if (value === "invalid") {
    return "danger" as const;
  }
  return "warning" as const;
}

function includesScope(scopes: string[], scope: string) {
  return scopes.map((item) => String(item || "").trim()).includes(scope);
}

type ProviderPreset = {
  baseUrl: string;
  defaultModel: string;
  suggestedModels: string[];
};

function providerPreset(type: string): ProviderPreset {
  const entry = providerPresetCatalog(type);
  return {
    baseUrl: String(entry.baseUrl || ""),
    defaultModel: String(entry.defaultModel || ""),
    suggestedModels: Array.isArray(entry.suggestedModels) ? uniqueProviderModels(entry.suggestedModels) : [],
  };
}

function normalizeProviderModel(type: string, model: string, fallback = "") {
  const normalizedType = String(type || "openai").trim() || "openai";
  const normalizedModel = String(model || "").trim();
  const preset = providerPreset(normalizedType);
  if (normalizedType === "openai-codex") {
    if (normalizedModel.startsWith("openai-codex/")) {
      return normalizedModel;
    }
    return String(fallback || preset.defaultModel || "openai-codex/gpt-5.4");
  }
  return normalizedModel || String(fallback || preset.defaultModel || "");
}

function normalizeProviderBaseUrl(type: string, value: string, fallback = "") {
  const base = String(value || fallback || "").trim().replace(/\/+$/, "");
  if (type === "gemini") {
    return base.replace(/\/openai$/i, "");
  }
  return base;
}

function friendlyCodexErrorMessage(error: unknown) {
  const raw = error instanceof Error ? error.message : String(error || "");
  if (!raw) {
    return sozluk.integrations.codexAuthError;
  }
  if (/docker bulunamad/i.test(raw)) {
    return "OpenAI hesabı (Codex) gelişmiş bir seçenektir. Bu mod için Docker gerekir. Normal kullanım için Gemini bağlantısı veya OpenAI anahtarıyla devam edin.";
  }
  if (/openclaw imajı bulunamad/i.test(raw)) {
    return "OpenAI hesabı (Codex) gelişmiş bir seçenektir. Bu mod için ek çalışma ortamı eksik. Normal kullanım için Gemini bağlantısı veya OpenAI anahtarıyla devam edin.";
  }
  if (/windows masaüstü kabuğunda gömülü değil/i.test(raw) || /tty köprüsü bulunamad/i.test(raw)) {
    return "OpenAI hesabı (Codex) bu kurulumda hazır değil. Normal kullanım için Gemini bağlantısı veya OpenAI anahtarı seçin.";
  }
  if (/oauth akışı zamanında tamamlanamad/i.test(raw)) {
    return "Giriş tarayıcıda tamamlandıysa bu adım birkaç saniyede bitmeliydi. Akışı yeniden başlatıp yönlendirme adresinin tamamını kullanın.";
  }
  if (/tarayıcı giriş bağlantısı hazırlanırken zaman aşımı oluştu/i.test(raw)) {
    return "Codex giriş bağlantısı zamanında hazırlanamadı. Docker veya arka plan hizmeti yavaş açılıyorsa birkaç saniye bekleyip yeniden deneyin.";
  }
  if (/yerel oauth yönlendirme portu açılamadı/i.test(raw)) {
    return "Tarayıcı yönlendirme portu bu makinede açılamadı. Girişi tamamladıktan sonra açılan yönlendirme adresini manuel yapıştırın.";
  }
  if (/oauth oturumu artık aktif değil/i.test(raw)) {
    return "Giriş oturumu kapandı. Hesabı yeniden bağlayıp akışı baştan başlatın.";
  }
  return raw;
}

function shouldSuggestCodexManualFallback(error: unknown) {
  const raw = rawDesktopErrorMessage(error).toLocaleLowerCase("tr-TR");
  return raw.includes("yerel oauth yönlendirme portu açılamadı");
}

function rawDesktopErrorMessage(error: unknown) {
  const raw = error instanceof Error ? error.message : String(error || "");
  if (!raw) {
    return "";
  }
  return raw
    .replace(/^Error invoking remote method '[^']+':\s*/i, "")
    .replace(/^TypeError:\s*/i, "")
    .trim();
}

function friendlyProviderErrorMessage(error: unknown, mode: "save" | "validate") {
  const raw = rawDesktopErrorMessage(error);
  if (!raw) {
    return mode === "save" ? sozluk.integrations.providerSaveError : sozluk.integrations.providerValidateError;
  }
  if (/fetch failed|backend_unreachable|backend_boot_timeout|token_bootstrap_failed/i.test(raw)) {
    return mode === "save"
      ? "Sağlayıcı ayarı kaydedildi ancak arka plan bağlantısı henüz yenilenemedi. Birkaç saniye sonra tekrar deneyin."
      : "Bağlantı kontrolü şu anda tamamlanamadı. Ağ bağlantınızı ve API anahtarınızı kontrol edip yeniden deneyin.";
  }
  if (/secure_storage_unavailable/i.test(raw)) {
    return "Bu cihazda güvenli anahtar saklama hazır değil. Anahtar kaydedilemediği için işlem tamamlanamadı.";
  }
  if (/backend_port_in_use/i.test(raw)) {
    return "Arka plan servisi başlatılamadı. Kullandığı portu başka bir uygulama meşgul ediyor.";
  }
  if (/api anahtari gerekli/i.test(raw)) {
    return "Bu sağlayıcıyı doğrulamak için API anahtarı girin veya kayıtlı anahtarla tekrar deneyin.";
  }
  if (/invalid_api_key|api key not valid|unauthorized|permission denied|forbidden/i.test(raw)) {
    return "API anahtarı kabul edilmedi. Anahtarı kontrol edip yeniden deneyin.";
  }
  if (/ENOTFOUND|network|timeout|timed out|aborted/i.test(raw)) {
    return "Sağlayıcıya şu anda ulaşılamadı. İnternet bağlantınızı ve temel adresi kontrol edip yeniden deneyin.";
  }
  return raw;
}

function providerSecretPlaceholder(maskedKey: string) {
  return String(maskedKey || "").trim()
    ? "Kayıtlı API anahtarı kullanılıyor."
    : sozluk.integrations.providerApiKeyPlaceholder;
}

const INTEGRATION_GUIDES = {
  google: "https://console.cloud.google.com/apis/credentials",
  googleTakeout: "https://takeout.google.com/settings/takeout",
  outlook: "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
  telegramBot: "https://t.me/BotFather",
  telegramWeb: "https://web.telegram.org/k/",
  telegramWebHelp: "https://telegram.org/faq#q-i-cannot-login",
  whatsapp: "https://developers.facebook.com/apps/creation/",
  x: "https://developer.x.com/en/portal/dashboard",
  instagram: "https://developers.facebook.com/apps/",
  linkedin: "https://www.linkedin.com/developers/apps",
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

function optionalGuideSteps(...steps: Array<string | undefined>) {
  return steps.filter((step): step is string => Boolean(String(step || "").trim()));
}

export function IntegrationSetupPanel({ mode = "connectors", onUpdated: onUpdatedProp, sections }: IntegrationSetupPanelProps) {
  const defaultOpenAiPreset = providerPreset("openai");
  const [desktopReady, setDesktopReady] = useState(Boolean(window.lawcopilotDesktop));
  const [providerType, setProviderType] = useState("openai");
  const [savedProviderType, setSavedProviderType] = useState("openai");
  const [providerBaseUrl, setProviderBaseUrl] = useState(defaultOpenAiPreset.baseUrl);
  const [providerModel, setProviderModel] = useState(defaultOpenAiPreset.defaultModel);
  const [providerApiKey, setProviderApiKey] = useState("");
  const [providerMaskedKey, setProviderMaskedKey] = useState("");
  const [providerStatusValue, setProviderStatusValue] = useState("pending");
  const [providerStatusMessage, setProviderStatusMessage] = useState("");
  const [providerAvailableModels, setProviderAvailableModels] = useState<string[]>([]);
  const [providerBusy, setProviderBusy] = useState(false);
  const [providerRefreshPending, setProviderRefreshPending] = useState(false);
  const [providerError, setProviderError] = useState("");

  const [codexAuthUrl, setCodexAuthUrl] = useState("");
  const [codexAuthState, setCodexAuthState] = useState("");
  const [codexCallbackUrl, setCodexCallbackUrl] = useState("");
  const [codexBrowserTarget, setCodexBrowserTarget] = useState("");
  const [codexConfigured, setCodexConfigured] = useState(false);
  const [codexBusy, setCodexBusy] = useState(false);
  const [showCodexManualFallback, setShowCodexManualFallback] = useState(false);

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
  const [googlePortabilityConfigured, setGooglePortabilityConfigured] = useState(false);
  const [googlePortabilityClientReady, setGooglePortabilityClientReady] = useState(false);
  const [googlePortabilityAccountLabel, setGooglePortabilityAccountLabel] = useState("");
  const [googlePortabilityScopes, setGooglePortabilityScopes] = useState<string[]>([]);
  const [googlePortabilityStatusValue, setGooglePortabilityStatusValue] = useState("pending");
  const [googlePortabilityStatusMessage, setGooglePortabilityStatusMessage] = useState("");
  const [googlePortabilityError, setGooglePortabilityError] = useState("");
  const [googlePortabilityBusy, setGooglePortabilityBusy] = useState(false);
  const [googlePortabilityAuthUrl, setGooglePortabilityAuthUrl] = useState("");
  const [googlePortabilityBrowserTarget, setGooglePortabilityBrowserTarget] = useState("");
  const [googlePortabilityArchiveState, setGooglePortabilityArchiveState] = useState("");
  const [googlePortabilityArchiveJobId, setGooglePortabilityArchiveJobId] = useState("");
  const [googlePortabilityLastSyncAt, setGooglePortabilityLastSyncAt] = useState("");
  const [googlePortabilityLastImportedAt, setGooglePortabilityLastImportedAt] = useState("");
  const [googleYouTubeHistoryCount, setGoogleYouTubeHistoryCount] = useState(0);
  const [googleChromeHistoryCount, setGoogleChromeHistoryCount] = useState(0);
  const [outlookEnabled, setOutlookEnabled] = useState(false);
  const [outlookConfigured, setOutlookConfigured] = useState(false);
  const [outlookClientReady, setOutlookClientReady] = useState(false);
  const [outlookAccountLabel, setOutlookAccountLabel] = useState("");
  const [outlookScopes, setOutlookScopes] = useState<string[]>([]);
  const [outlookClientId, setOutlookClientId] = useState("");
  const [outlookTenantId, setOutlookTenantId] = useState("common");
  const [outlookStatusValue, setOutlookStatusValue] = useState("pending");
  const [outlookStatusMessage, setOutlookStatusMessage] = useState("");
  const [outlookBusy, setOutlookBusy] = useState(false);
  const [outlookError, setOutlookError] = useState("");
  const [outlookLastSyncAt, setOutlookLastSyncAt] = useState("");

  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramMode, setTelegramMode] = useState("bot");
  const [telegramBotToken, setTelegramBotToken] = useState("");
  const [telegramAllowedUserId, setTelegramAllowedUserId] = useState("");
  const [telegramBotUsername, setTelegramBotUsername] = useState("");
  const [telegramMaskedToken, setTelegramMaskedToken] = useState("");
  const [telegramWebSessionName, setTelegramWebSessionName] = useState("default");
  const [telegramWebStatus, setTelegramWebStatus] = useState("idle");
  const [telegramWebAccountLabel, setTelegramWebAccountLabel] = useState("");
  const [telegramWebLastReadyAt, setTelegramWebLastReadyAt] = useState("");
  const [telegramWebLastSyncAt, setTelegramWebLastSyncAt] = useState("");
  const [telegramStatusValue, setTelegramStatusValue] = useState("pending");
  const [telegramStatusMessage, setTelegramStatusMessage] = useState("");
  const [telegramBusy, setTelegramBusy] = useState(false);
  const [telegramError, setTelegramError] = useState("");
  const [whatsAppEnabled, setWhatsAppEnabled] = useState(false);
  const [whatsAppMode, setWhatsAppMode] = useState("web");
  const [whatsAppBusinessLabel, setWhatsAppBusinessLabel] = useState("");
  const [whatsAppPhoneNumberId, setWhatsAppPhoneNumberId] = useState("");
  const [whatsAppAccessToken, setWhatsAppAccessToken] = useState("");
  const [whatsAppSetupBundle, setWhatsAppSetupBundle] = useState("");
  const [whatsAppMaskedToken, setWhatsAppMaskedToken] = useState("");
  const [whatsAppDisplayNumber, setWhatsAppDisplayNumber] = useState("");
  const [whatsAppVerifiedName, setWhatsAppVerifiedName] = useState("");
  const [whatsAppWebSessionName, setWhatsAppWebSessionName] = useState("default");
  const [whatsAppWebStatus, setWhatsAppWebStatus] = useState("idle");
  const [whatsAppWebQrDataUrl, setWhatsAppWebQrDataUrl] = useState("");
  const [whatsAppWebCurrentUser, setWhatsAppWebCurrentUser] = useState("");
  const [whatsAppWebAccountLabel, setWhatsAppWebAccountLabel] = useState("");
  const [whatsAppWebLastReadyAt, setWhatsAppWebLastReadyAt] = useState("");
  const [whatsAppWebLastSyncAt, setWhatsAppWebLastSyncAt] = useState("");
  const [whatsAppWebBrowserLabel, setWhatsAppWebBrowserLabel] = useState("");
  const [whatsAppWebMessageCountMirrored, setWhatsAppWebMessageCountMirrored] = useState(0);
  const [whatsAppStatusValue, setWhatsAppStatusValue] = useState("pending");
  const [whatsAppStatusMessage, setWhatsAppStatusMessage] = useState("");
  const [whatsAppBusy, setWhatsAppBusy] = useState(false);
  const [whatsAppError, setWhatsAppError] = useState("");
  const [whatsAppLastSyncAt, setWhatsAppLastSyncAt] = useState("");
  const whatsAppGuideSteps = optionalGuideSteps(
    sozluk.integrations.whatsappGuideStep1,
    sozluk.integrations.whatsappGuideStep2,
    sozluk.integrations.whatsappGuideStep3,
    sozluk.integrations.whatsappGuideStep4,
    sozluk.integrations.whatsappGuideStep5,
    sozluk.integrations.whatsappGuideStep6,
    sozluk.integrations.whatsappGuideStep7,
  );
  const whatsAppWebGuideSteps = optionalGuideSteps(
    sozluk.integrations.whatsappWebGuideStep1,
    sozluk.integrations.whatsappWebGuideStep2,
    sozluk.integrations.whatsappWebGuideStep3,
    sozluk.integrations.whatsappWebGuideStep4,
  );
  const telegramUsesWebMode = telegramMode === "web";
  const whatsappUsesWebMode = whatsAppMode === "web";
  const whatsAppWebReady = whatsappUsesWebMode && whatsAppWebStatus === "ready";
  const whatsAppWebLinking = whatsappUsesWebMode && ["initializing", "authenticated"].includes(whatsAppWebStatus);
  const whatsAppWebNeedsQr = whatsappUsesWebMode && whatsAppWebStatus === "qr_required";
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
  const [instagramEnabled, setInstagramEnabled] = useState(false);
  const [instagramConfigured, setInstagramConfigured] = useState(false);
  const [instagramClientReady, setInstagramClientReady] = useState(false);
  const [instagramAccountLabel, setInstagramAccountLabel] = useState("");
  const [instagramUsername, setInstagramUsername] = useState("");
  const [instagramPageName, setInstagramPageName] = useState("");
  const [instagramPageNameHint, setInstagramPageNameHint] = useState("");
  const [instagramScopes, setInstagramScopes] = useState<string[]>([]);
  const [instagramClientId, setInstagramClientId] = useState("");
  const [instagramClientSecret, setInstagramClientSecret] = useState("");
  const [instagramStatusValue, setInstagramStatusValue] = useState("pending");
  const [instagramStatusMessage, setInstagramStatusMessage] = useState("");
  const [instagramBusy, setInstagramBusy] = useState(false);
  const [instagramError, setInstagramError] = useState("");
  const [instagramLastSyncAt, setInstagramLastSyncAt] = useState("");
  const [linkedInEnabled, setLinkedInEnabled] = useState(false);
  const [linkedInMode, setLinkedInMode] = useState("official");
  const [linkedInConfigured, setLinkedInConfigured] = useState(false);
  const [linkedInClientReady, setLinkedInClientReady] = useState(false);
  const [linkedInAccountLabel, setLinkedInAccountLabel] = useState("");
  const [linkedInScopes, setLinkedInScopes] = useState<string[]>([]);
  const [linkedInClientId, setLinkedInClientId] = useState("");
  const [linkedInClientSecret, setLinkedInClientSecret] = useState("");
  const [linkedInWebSessionName, setLinkedInWebSessionName] = useState("default");
  const [linkedInWebStatus, setLinkedInWebStatus] = useState("idle");
  const [linkedInWebAccountLabel, setLinkedInWebAccountLabel] = useState("");
  const [linkedInWebLastReadyAt, setLinkedInWebLastReadyAt] = useState("");
  const [linkedInWebLastSyncAt, setLinkedInWebLastSyncAt] = useState("");
  const [linkedInStatusValue, setLinkedInStatusValue] = useState("pending");
  const [linkedInStatusMessage, setLinkedInStatusMessage] = useState("");
  const [linkedInBusy, setLinkedInBusy] = useState(false);
  const [linkedInError, setLinkedInError] = useState("");
  const [linkedInLastSyncAt, setLinkedInLastSyncAt] = useState("");
  const linkedInUsesWebMode = linkedInMode === "web";

  function notifyProfileSignalUpdate() {
    if (typeof window === "undefined") {
      return;
    }
    window.dispatchEvent(new CustomEvent(SETTINGS_MEMORY_UPDATE_EVENT, {
      detail: {
        kinds: ["profile_signal"],
      },
    }));
  }

  const onUpdated = () => {
    onUpdatedProp?.();
    notifyProfileSignalUpdate();
  };

  const currentProviderPreset = useMemo(() => providerPreset(providerType), [providerType]);
  const suggestedProviderModels = useMemo(() => {
    const unique = uniqueProviderModels([...currentProviderPreset.suggestedModels, ...providerAvailableModels]);
    const normalizedCurrentModel = normalizeProviderModel(providerType, providerModel, currentProviderPreset.defaultModel);
    if (normalizedCurrentModel && !unique.includes(normalizedCurrentModel)) {
      unique.unshift(normalizedCurrentModel);
    }
    return unique;
  }, [currentProviderPreset.defaultModel, currentProviderPreset.suggestedModels, providerAvailableModels, providerModel, providerType]);

  function applyCodexStatus(status: CodexAuthStatus, fallbackMessage = "") {
    const configured = Boolean(status.configured);
    const mergedModels = uniqueProviderModels([
      ...currentProviderPreset.suggestedModels,
      ...(Array.isArray(status.catalogModels) ? status.catalogModels : []),
      ...(Array.isArray(status.availableModels) ? status.availableModels : []),
    ]);
    setCodexConfigured(configured);
    if (configured) {
      setShowCodexManualFallback(false);
    }
    setProviderStatusValue(configured ? "valid" : status.authStatus === "hata" ? "invalid" : "pending");
    setProviderStatusMessage(String(status.message || fallbackMessage || ""));
    setCodexAuthState(String(status.authStatus || ""));
    setProviderAvailableModels(mergedModels);
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

  function applyGooglePortabilityStatus(status: GooglePortabilityAuthStatus, fallbackMessage = "") {
    setGooglePortabilityConfigured(Boolean(status.configured));
    setGooglePortabilityClientReady(Boolean(status.clientReady));
    setGooglePortabilityAccountLabel(String(status.accountLabel || ""));
    setGooglePortabilityScopes(Array.isArray(status.scopes) ? status.scopes : []);
    setGooglePortabilityStatusValue(Boolean(status.configured) ? "valid" : status.authStatus === "hata" ? "invalid" : "pending");
    setGooglePortabilityStatusMessage(String(status.message || fallbackMessage || ""));
    setGooglePortabilityAuthUrl(String(status.authUrl || ""));
    setGooglePortabilityBrowserTarget(String(status.browserTarget || ""));
    setGooglePortabilityArchiveState(String(status.archiveState || ""));
    setGooglePortabilityArchiveJobId(String(status.archiveJobId || ""));
    setGooglePortabilityLastSyncAt(String(status.lastSyncAt || ""));
    setGooglePortabilityError(String(status.error || ""));
  }

  function applyOutlookStatus(status: OutlookAuthStatus, fallbackMessage = "") {
    setOutlookConfigured(Boolean(status.configured));
    setOutlookClientReady(Boolean(status.clientReady));
    setOutlookAccountLabel(String(status.accountLabel || ""));
    setOutlookClientId(String(status.clientId || ""));
    setOutlookScopes(Array.isArray(status.scopes) ? status.scopes : []);
    setOutlookTenantId(String(status.tenantId || "common"));
    setOutlookStatusValue(Boolean(status.configured) ? "valid" : status.authStatus === "hata" ? "invalid" : "pending");
    setOutlookStatusMessage(String(status.message || fallbackMessage || ""));
    setOutlookError(String(status.error || ""));
  }

  function applyTelegramStatus(status: Record<string, unknown>, fallbackMessage = "") {
    const nextMode = String(status.mode || telegramMode || "bot");
    setTelegramEnabled(Boolean(status.enabled));
    setTelegramMode(nextMode);
    setTelegramBotUsername(String(status.accountLabel || status.botUsername || ""));
    setTelegramAllowedUserId(String(status.allowedUserId || ""));
    setTelegramStatusValue(Boolean(status.configured) ? "valid" : String(status.validationStatus || "pending"));
    setTelegramStatusMessage(String(status.message || fallbackMessage || ""));
    setTelegramWebSessionName(String(status.webSessionName || "default"));
    setTelegramWebStatus(String(status.webStatus || "idle"));
    setTelegramWebAccountLabel(String(status.webAccountLabel || ""));
    setTelegramWebLastReadyAt(String(status.webLastReadyAt || ""));
    setTelegramWebLastSyncAt(String(status.webLastSyncAt || status.lastSyncAt || ""));
    setTelegramError(String(status.error || ""));
  }

  function applyWhatsAppStatus(status: WhatsAppAuthStatus, fallbackMessage = "") {
    const nextWebStatus = String(status.webStatus || "idle");
    setWhatsAppEnabled(Boolean(status.enabled));
    setWhatsAppMode(String(status.mode || "web"));
    setWhatsAppBusinessLabel(String(status.accountLabel || ""));
    setWhatsAppDisplayNumber(String(status.displayPhoneNumber || ""));
    setWhatsAppVerifiedName(String(status.verifiedName || ""));
    setWhatsAppPhoneNumberId(String(status.phoneNumberId || ""));
    setWhatsAppStatusValue(Boolean(status.configured) ? "valid" : String(status.validationStatus || "pending"));
    setWhatsAppStatusMessage(
      String(status.message || fallbackMessage || (nextWebStatus === "ready" ? sozluk.integrations.whatsappWebReadyMessage : "")),
    );
    setWhatsAppLastSyncAt(String(status.lastSyncAt || ""));
    setWhatsAppWebSessionName(String(status.webSessionName || "default"));
    setWhatsAppWebStatus(nextWebStatus);
    setWhatsAppWebQrDataUrl(String(status.webQrDataUrl || ""));
    setWhatsAppWebCurrentUser(String(status.webCurrentUser || ""));
    setWhatsAppWebAccountLabel(String(status.webAccountLabel || ""));
    setWhatsAppWebLastReadyAt(String(status.webLastReadyAt || ""));
    setWhatsAppWebLastSyncAt(String(status.webLastSyncAt || status.lastSyncAt || ""));
    setWhatsAppWebBrowserLabel(String(status.webBrowserLabel || ""));
    setWhatsAppWebMessageCountMirrored(Number(status.webMessageCountMirrored || 0));
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

  function applyLinkedInStatus(status: LinkedInAuthStatus, fallbackMessage = "") {
    const nextMode = String(status.mode || linkedInMode || "official");
    setLinkedInConfigured(Boolean(status.configured));
    setLinkedInMode(nextMode);
    setLinkedInClientReady(Boolean(status.clientReady));
    setLinkedInAccountLabel(String(status.accountLabel || ""));
    setLinkedInScopes(Array.isArray(status.scopes) ? status.scopes : []);
    setLinkedInStatusValue(Boolean(status.configured) ? "valid" : String(status.validationStatus || "pending"));
    setLinkedInLastSyncAt(String(status.lastSyncAt || ""));
    setLinkedInWebSessionName(String(status.webSessionName || "default"));
    setLinkedInWebStatus(String(status.webStatus || "idle"));
    setLinkedInWebAccountLabel(String(status.webAccountLabel || ""));
    setLinkedInWebLastReadyAt(String(status.webLastReadyAt || ""));
    setLinkedInWebLastSyncAt(String(status.webLastSyncAt || status.lastSyncAt || ""));
    setLinkedInStatusMessage(String(status.message || fallbackMessage || ""));
    setLinkedInError(String(status.error || ""));
  }

  function applyInstagramStatus(status: InstagramAuthStatus, fallbackMessage = "") {
    setInstagramConfigured(Boolean(status.configured));
    setInstagramClientReady(Boolean(status.clientReady));
    setInstagramAccountLabel(String(status.accountLabel || ""));
    setInstagramUsername(String(status.username || ""));
    setInstagramPageName(String(status.pageName || ""));
    setInstagramScopes(Array.isArray(status.scopes) ? status.scopes : []);
    setInstagramStatusValue(Boolean(status.configured) ? "valid" : "pending");
    setInstagramStatusMessage(String(status.message || fallbackMessage || ""));
    setInstagramError(String(status.error || ""));
  }

  function handleProviderTypeChange(value: string) {
    const nextPreset = providerPreset(value);
    setProviderType(value);
    setProviderStatusValue("pending");
    setProviderStatusMessage("");
    setProviderError("");
    setProviderAvailableModels([]);
    setProviderMaskedKey("");
    setProviderApiKey("");
    setProviderRefreshPending(false);
    setCodexAuthUrl("");
    setCodexBrowserTarget("");
    setCodexCallbackUrl("");
    setCodexConfigured(false);
    setShowCodexManualFallback(false);
    if (value === "openai-codex") {
      setProviderBaseUrl("oauth://openai-codex");
      setProviderModel(nextPreset.defaultModel);
      setProviderStatusMessage(sozluk.integrations.codexAuthIdle);
      return;
    }
    setProviderBaseUrl(nextPreset.baseUrl);
    setProviderModel(nextPreset.defaultModel);
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
      const googlePortability = config.googlePortability || {};
      const outlook = config.outlook || {};
      const telegram = config.telegram || {};
      const whatsapp = config.whatsapp || {};
      const x = config.x || {};
      const linkedin = config.linkedin || {};
      const instagram = config.instagram || {};
    setProviderType(String(provider.type || "openai"));
    setSavedProviderType(String(provider.type || "openai"));
    setProviderBaseUrl(normalizeProviderBaseUrl(String(provider.type || "openai"), String(provider.baseUrl || providerDefaults.baseUrl), providerDefaults.baseUrl));
    setProviderModel(normalizeProviderModel(String(provider.type || "openai"), String(provider.model || ""), providerDefaults.defaultModel));
      setProviderApiKey("");
      setProviderMaskedKey(String(provider.apiKeyMasked || ""));
      setProviderStatusValue(String(provider.validationStatus || "pending"));
      setProviderStatusMessage("");
      setProviderAvailableModels(uniqueProviderModels(Array.isArray(provider.availableModels) ? provider.availableModels || [] : []));
      setCodexConfigured(Boolean(provider.oauthConnected));
      setGoogleEnabled(Boolean(google.enabled));
      setGoogleConfigured(Boolean(google.oauthConnected));
      setGoogleClientReady(Boolean(google.clientIdConfigured && google.clientSecretConfigured));
      setGoogleAccountLabel(String(google.accountLabel || ""));
      setGoogleScopes(Array.isArray(google.scopes) ? google.scopes : []);
      setGoogleStatusValue(String(google.validationStatus || "pending"));
      setGooglePortabilityConfigured(Boolean(googlePortability.oauthConnected));
      setGooglePortabilityClientReady(
        Boolean(
          (googlePortability.clientIdConfigured && googlePortability.clientSecretConfigured)
          || (google.clientIdConfigured && google.clientSecretConfigured),
        ),
      );
      setGooglePortabilityAccountLabel(String(googlePortability.accountLabel || ""));
      setGooglePortabilityScopes(Array.isArray(googlePortability.scopes) ? googlePortability.scopes : []);
      setGooglePortabilityStatusValue(String(googlePortability.validationStatus || "pending"));
      setGooglePortabilityArchiveState(String(googlePortability.archiveState || ""));
      setGooglePortabilityArchiveJobId(String(googlePortability.archiveJobId || ""));
      setGooglePortabilityLastSyncAt(String(googlePortability.lastSyncAt || ""));
      setGooglePortabilityLastImportedAt(String(googlePortability.lastImportedAt || ""));
      setGoogleYouTubeHistoryCount(Number(googlePortability.youtubeHistoryCount || 0));
      setGoogleChromeHistoryCount(Number(googlePortability.chromeHistoryCount || 0));
      setOutlookEnabled(Boolean(outlook.enabled));
      setOutlookConfigured(Boolean(outlook.oauthConnected));
      setOutlookClientReady(Boolean(outlook.clientIdConfigured));
      setOutlookAccountLabel(String(outlook.accountLabel || ""));
      setOutlookClientId(String(outlook.clientId || ""));
      setOutlookScopes(Array.isArray(outlook.scopes) ? outlook.scopes : []);
      setOutlookTenantId(String(outlook.tenantId || "common"));
      setOutlookStatusValue(String(outlook.validationStatus || "pending"));
      setOutlookLastSyncAt(String(outlook.lastSyncAt || ""));
      setTelegramEnabled(Boolean(telegram.enabled));
      setTelegramMode(String(telegram.mode || "bot"));
      setTelegramAllowedUserId(String(telegram.allowedUserId || ""));
      setTelegramBotUsername(String(telegram.botUsername || ""));
      setTelegramMaskedToken(String(telegram.botTokenMasked || ""));
      setTelegramWebSessionName(String(telegram.webSessionName || "default"));
      setTelegramWebStatus(String(telegram.webStatus || "idle"));
      setTelegramWebAccountLabel(String(telegram.webAccountLabel || ""));
      setTelegramWebLastReadyAt(String(telegram.webLastReadyAt || ""));
      setTelegramWebLastSyncAt(String(telegram.webLastSyncAt || ""));
      setTelegramStatusValue(String(telegram.validationStatus || "pending"));
      setWhatsAppEnabled(Boolean(whatsapp.enabled));
      setWhatsAppMode(String(whatsapp.mode || (whatsapp.phoneNumberId || whatsapp.accessTokenConfigured ? "business_cloud" : "web")));
      setWhatsAppBusinessLabel(String(whatsapp.businessLabel || ""));
      setWhatsAppDisplayNumber(String(whatsapp.displayPhoneNumber || ""));
      setWhatsAppVerifiedName(String(whatsapp.verifiedName || ""));
      setWhatsAppPhoneNumberId(String(whatsapp.phoneNumberId || ""));
      setWhatsAppMaskedToken(String(whatsapp.accessTokenMasked || ""));
      setWhatsAppWebSessionName(String(whatsapp.webSessionName || "default"));
      setWhatsAppWebStatus(String(whatsapp.webStatus || "idle"));
      setWhatsAppWebAccountLabel(String(whatsapp.webAccountLabel || ""));
      setWhatsAppWebLastReadyAt(String(whatsapp.webLastReadyAt || ""));
      setWhatsAppWebLastSyncAt(String(whatsapp.webLastSyncAt || ""));
      setWhatsAppStatusValue(String(whatsapp.validationStatus || "pending"));
      setWhatsAppLastSyncAt(String(whatsapp.lastSyncAt || ""));
      setXEnabled(Boolean(x.enabled));
      setXConfigured(Boolean(x.oauthConnected));
      setXClientReady(Boolean(x.clientIdConfigured && x.clientSecretConfigured));
      setXAccountLabel(String(x.accountLabel || ""));
      setXScopes(Array.isArray(x.scopes) ? x.scopes : []);
      setXStatusValue(String(x.validationStatus || "pending"));
      setXLastSyncAt(String(x.lastSyncAt || ""));
      setInstagramEnabled(Boolean(instagram.enabled));
      setInstagramConfigured(Boolean(instagram.oauthConnected));
      setInstagramClientReady(Boolean(instagram.clientIdConfigured && instagram.clientSecretConfigured));
      setInstagramAccountLabel(String(instagram.accountLabel || ""));
      setInstagramUsername(String(instagram.username || ""));
      setInstagramPageName(String(instagram.pageName || ""));
      setInstagramPageNameHint(String(instagram.pageNameHint || ""));
      setInstagramScopes(Array.isArray(instagram.scopes) ? instagram.scopes : []);
      setInstagramStatusValue(String(instagram.validationStatus || "pending"));
      setInstagramLastSyncAt(String(instagram.lastSyncAt || ""));
      setLinkedInEnabled(Boolean(linkedin.enabled));
      setLinkedInMode(String(linkedin.mode || "official"));
      setLinkedInConfigured(Boolean(linkedin.oauthConnected));
      setLinkedInClientReady(Boolean(linkedin.clientIdConfigured && linkedin.clientSecretConfigured));
      setLinkedInAccountLabel(String(linkedin.accountLabel || ""));
      setLinkedInScopes(Array.isArray(linkedin.scopes) ? linkedin.scopes : []);
      setLinkedInStatusValue(String(linkedin.validationStatus || "pending"));
      setLinkedInLastSyncAt(String(linkedin.lastSyncAt || ""));
      setLinkedInWebSessionName(String(linkedin.webSessionName || "default"));
      setLinkedInWebStatus(String(linkedin.webStatus || "idle"));
      setLinkedInWebAccountLabel(String(linkedin.webAccountLabel || ""));
      setLinkedInWebLastReadyAt(String(linkedin.webLastReadyAt || ""));
      setLinkedInWebLastSyncAt(String(linkedin.webLastSyncAt || ""));
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
      if (window.lawcopilotDesktop?.getGooglePortabilityAuthStatus) {
        const status = (await window.lawcopilotDesktop.getGooglePortabilityAuthStatus()) as GooglePortabilityAuthStatus;
        if (active) {
          applyGooglePortabilityStatus(status);
        }
      }
      if (window.lawcopilotDesktop?.getOutlookAuthStatus) {
        const status = (await window.lawcopilotDesktop.getOutlookAuthStatus()) as OutlookAuthStatus;
        if (active) {
          applyOutlookStatus(status);
        }
      }
      if (window.lawcopilotDesktop?.getTelegramStatus) {
        const status = (await window.lawcopilotDesktop.getTelegramStatus()) as Record<string, unknown>;
        if (active) {
          applyTelegramStatus(status);
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
      if (window.lawcopilotDesktop?.getInstagramAuthStatus) {
        const status = (await window.lawcopilotDesktop.getInstagramAuthStatus()) as InstagramAuthStatus;
        if (active) {
          applyInstagramStatus(status);
        }
      }
      if (window.lawcopilotDesktop?.getLinkedInStatus) {
        const status = (await window.lawcopilotDesktop.getLinkedInStatus()) as LinkedInAuthStatus;
        if (active) {
          applyLinkedInStatus(status);
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
    }, 700);
    return () => window.clearInterval(intervalId);
  }, [googleAuthUrl, googleConfigured]);

  useEffect(() => {
    if (!googlePortabilityAuthUrl || googlePortabilityConfigured) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void refreshGooglePortabilityStatus();
    }, 700);
    return () => window.clearInterval(intervalId);
  }, [googlePortabilityAuthUrl, googlePortabilityConfigured]);

  useEffect(() => {
    if (codexConfigured) {
      return;
    }
    if (!["baslatiliyor", "callback_bekleniyor", "tamamlaniyor"].includes(String(codexAuthState || "")) && !codexAuthUrl) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void refreshCodexStatus();
    }, 700);
    return () => window.clearInterval(intervalId);
  }, [codexAuthState, codexAuthUrl, codexConfigured]);

  useEffect(() => {
    if (!window.lawcopilotDesktop?.getWhatsAppStatus) {
      return;
    }
    if (whatsAppMode !== "web") {
      return;
    }
    if (!["qr_required", "authenticated", "initializing"].includes(whatsAppWebStatus)) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void refreshWhatsAppStatus();
    }, 2000);
    return () => window.clearInterval(intervalId);
  }, [whatsAppMode, whatsAppWebStatus]);

  const providerNeedsKey = providerType !== "ollama" && providerType !== "openai-codex";
  const providerUsesBrowserAuth = providerType === "openai-codex";
  const providerActionBusy = providerUsesBrowserAuth ? codexBusy : (providerBusy || providerRefreshPending);
  const providerHasConfiguredConnection = savedProviderType === providerType && (providerUsesBrowserAuth ? codexConfigured : Boolean(providerMaskedKey));
  const simpleMode = mode === "simple" || mode === "onboarding" || mode === "settings";
  const compactSettingsMode = mode === "settings";
  const telegramSetupEnabled = simpleMode ? true : telegramEnabled;
  const visibleSections = useMemo(() => (
    new Set<SetupSectionKey>(sections && sections.length ? sections : ["provider", "google", "outlook", "telegram", "whatsapp", "x", "instagram", "linkedin"])
  ), [sections]);
  const showSection = (key: SetupSectionKey) => visibleSections.has(key);
  const googleHasGmail = googleScopes.some((scope) => String(scope).includes("gmail"));
  const googleHasCalendar = googleScopes.some((scope) => String(scope).includes("calendar"));
  const googleHasDrive = googleScopes.some((scope) => String(scope).includes("drive"));
  const googleHasYouTube = googleScopes.some((scope) => String(scope).includes("youtube"));
  const googleHistoryConnected = googlePortabilityConfigured || googleYouTubeHistoryCount > 0 || googleChromeHistoryCount > 0;
  const likelyTurkeyRegion = useMemo(() => {
    try {
      const locale = `${window.navigator?.language || ""} ${Intl.DateTimeFormat().resolvedOptions().locale || ""}`.toLowerCase();
      const timeZone = String(Intl.DateTimeFormat().resolvedOptions().timeZone || "").toLowerCase();
      return locale.includes("tr") || timeZone === "europe/istanbul";
    } catch {
      return false;
    }
  }, []);
  const googlePortabilityPending = ["IN_PROGRESS", "CREATING", "PENDING"].includes(String(googlePortabilityArchiveState || "").toUpperCase());
  const googlePortabilityComplete = String(googlePortabilityArchiveState || "").toUpperCase() === "COMPLETE";
  const preferGoogleTakeoutImport = likelyTurkeyRegion && !googlePortabilityConfigured && !googlePortabilityAuthUrl;
  const googleHistoryStatusLabel = googlePortabilityPending
    ? sozluk.integrations.googleHistoryStatusInProgress
    : googlePortabilityComplete
      ? sozluk.integrations.googleHistoryStatusComplete
      : googleHistoryConnected
        ? sozluk.integrations.googleHistoryConnected
        : sozluk.integrations.googleHistoryStatusIdle;
  const outlookHasMail = outlookScopes.some((scope) => String(scope).toLowerCase().includes("mail."));
  const outlookHasCalendar = outlookScopes.some((scope) => String(scope).toLowerCase().includes("calendar"));
  const xDirectMessagesReady = includesScope(xScopes, "dm.read") && includesScope(xScopes, "dm.write");
  const showCodexCallback = Boolean(codexAuthUrl || codexBrowserTarget || codexCallbackUrl.trim());
  const showGoogleCallback = Boolean(googleAuthUrl || googleBrowserTarget || googleCallbackUrl.trim());
  const codexAwaitingCompletion = providerUsesBrowserAuth && Boolean(codexAuthUrl) && !codexConfigured;
  const providerSubtitle = useMemo(() => {
    if (mode === "onboarding") {
      return sozluk.integrations.providerOnboardingSubtitle;
    }
    return sozluk.integrations.providerSubtitle;
  }, [mode]);

  async function persistCodexProviderSelection(nextModel: string, syncRemote = false) {
    const normalizedModel = normalizeProviderModel("openai-codex", nextModel, providerPreset("openai-codex").defaultModel);
    setProviderModel(normalizedModel);
    if (syncRemote && window.lawcopilotDesktop?.setCodexModel) {
      const response = (await window.lawcopilotDesktop.setCodexModel(normalizedModel)) as {
        status?: CodexAuthStatus;
        config?: SanitizedIntegrationConfig;
      };
      applyCodexStatus(response.status || {}, sozluk.integrations.codexModelSaved);
      setSavedProviderType(String(response.config?.provider?.type || "openai-codex"));
      setProviderError("");
      return true;
    }
    if (!window.lawcopilotDesktop?.saveIntegrationConfigFast) {
      setProviderError(sozluk.integrations.desktopOnly);
      return false;
    }
    const saved = (await window.lawcopilotDesktop.saveIntegrationConfigFast({
      provider: {
        type: "openai-codex",
        authMode: "oauth",
        baseUrl: "oauth://openai-codex",
        model: normalizedModel,
        accountLabel: providerLabel("openai-codex"),
        validationStatus: codexConfigured ? "valid" : "pending",
      },
    })) as SanitizedIntegrationConfig;
    setSavedProviderType(String(saved.provider?.type || "openai-codex"));
    setProviderStatusValue(String(saved.provider?.validationStatus || (codexConfigured ? "valid" : "pending")));
    setProviderError("");
    return true;
  }

  function handleProviderModelChange(nextModel: string) {
    const normalizedModel = normalizeProviderModel(providerType, nextModel, currentProviderPreset.defaultModel);
    setProviderModel(normalizedModel);
    if (!providerUsesBrowserAuth || !codexConfigured) {
      return;
    }
    void persistCodexProviderSelection(normalizedModel, true).catch((error) => {
      setProviderError(friendlyCodexErrorMessage(error));
    });
  }

  async function refreshCodexStatus() {
    if (!window.lawcopilotDesktop?.getCodexAuthStatus) {
      setProviderError(sozluk.integrations.desktopOnly);
      return;
    }
    setCodexBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.getCodexAuthStatus()) as CodexAuthStatus;
      applyCodexStatus(status, sozluk.integrations.codexAuthIdle);
      if (status.error || status.authStatus === "hata") {
        if (shouldSuggestCodexManualFallback(status.error || status.message || "")) {
          setShowCodexManualFallback(true);
        }
        setProviderError(friendlyCodexErrorMessage(status.error || status.message || ""));
      } else {
        setProviderError("");
      }
    } catch (error) {
      setProviderStatusValue("invalid");
      if (shouldSuggestCodexManualFallback(error)) {
        setShowCodexManualFallback(true);
      }
      setProviderError(friendlyCodexErrorMessage(error));
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
    setCodexAuthState("baslatiliyor");
    setProviderStatusValue("pending");
    setProviderStatusMessage(sozluk.integrations.codexAuthPending);
    try {
      const modelSaved = await persistCodexProviderSelection(providerModel, false);
      if (!modelSaved) {
        return;
      }
      const status = (await window.lawcopilotDesktop.startCodexAuth()) as CodexAuthStatus;
      applyCodexStatus(status, sozluk.integrations.codexAuthPending);
      setProviderError("");
    } catch (error) {
      setProviderStatusValue("invalid");
      setProviderStatusMessage("");
      if (shouldSuggestCodexManualFallback(error)) {
        setShowCodexManualFallback(true);
      }
      setProviderError(friendlyCodexErrorMessage(error));
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
      setProviderAvailableModels(uniqueProviderModels(Array.isArray(provider.availableModels) ? provider.availableModels || [] : []));
      setCodexCallbackUrl("");
      setProviderError("");
      onUpdated?.();
    } catch (error) {
      setProviderStatusValue("invalid");
      setProviderStatusMessage("");
      if (shouldSuggestCodexManualFallback(error)) {
        setShowCodexManualFallback(true);
      }
      setProviderError(friendlyCodexErrorMessage(error));
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
      if (status.configured && !googleConfigured) {
        setGoogleStatusMessage(sozluk.integrations.googleAuthConnected);
        onUpdated?.();
      }
    } catch (error) {
      setGoogleStatusValue("invalid");
      setGoogleError(error instanceof Error ? error.message : sozluk.integrations.googleAuthError);
    } finally {
      setGoogleBusy(false);
    }
  }

  async function saveGoogleClientSetup() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfigFast) {
      setGoogleError(sozluk.integrations.desktopOnly);
      return false;
    }
    if (!googleClientId.trim() || !googleClientSecret.trim()) {
      setGoogleError(sozluk.integrations.googleClientSetupRequired);
      return false;
    }
    setGoogleBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfigFast({
        google: {
          clientId: googleClientId.trim(),
          clientSecret: googleClientSecret.trim(),
        },
      });
      setGoogleClientId("");
      setGoogleClientSecret("");
      setGoogleClientReady(true);
      setGoogleError("");
      setGoogleStatusMessage(sozluk.integrations.googleClientSaved);
      return true;
    } catch (error) {
      setGoogleError(error instanceof Error ? error.message : sozluk.integrations.googleClientSaveError);
      return false;
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
      if (status.configured) {
        setGoogleStatusMessage(sozluk.integrations.googleAuthConnected);
        onUpdated?.();
      }
    } catch (error) {
      setGoogleStatusValue("invalid");
      setGoogleStatusMessage("");
      setGoogleError(error instanceof Error ? error.message : sozluk.integrations.googleAuthError);
    } finally {
      setGoogleBusy(false);
    }
  }

  async function connectGoogleAccount() {
    if (!googleClientReady) {
      const setupSaved = await saveGoogleClientSetup();
      if (!setupSaved) {
        return;
      }
    }
    await startGoogleAuthFlow();
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
      if (response.status?.configured && window.lawcopilotDesktop?.syncGoogleData) {
        const result = (await window.lawcopilotDesktop.syncGoogleData()) as { message?: string };
        setGoogleStatusMessage(
          String(result.message || "Google verileri eşitlendi. Gmail, Takvim, Drive ve YouTube oynatma listeleri artık asistana açık."),
        );
      }
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

  async function refreshGooglePortabilityStatus() {
    if (!window.lawcopilotDesktop?.getGooglePortabilityAuthStatus) {
      setGooglePortabilityError(sozluk.integrations.desktopOnly);
      return;
    }
    setGooglePortabilityBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.getGooglePortabilityAuthStatus()) as GooglePortabilityAuthStatus;
      applyGooglePortabilityStatus(status, sozluk.integrations.googleHistoryStatusIdle);
      if (status.configured && !googlePortabilityConfigured) {
        setGooglePortabilityStatusMessage(sozluk.integrations.googleHistoryConnected);
        onUpdated?.();
      }
    } catch (error) {
      setGooglePortabilityStatusValue("invalid");
      setGooglePortabilityError(error instanceof Error ? error.message : sozluk.integrations.googleHistoryAuthError);
    } finally {
      setGooglePortabilityBusy(false);
    }
  }

  async function connectGooglePortability() {
    if (!window.lawcopilotDesktop?.startGooglePortabilityAuth) {
      setGooglePortabilityError(sozluk.integrations.desktopOnly);
      return;
    }
    if (!googlePortabilityClientReady) {
      const setupSaved = await saveGoogleClientSetup();
      if (!setupSaved) {
        return;
      }
    }
    setGooglePortabilityBusy(true);
    setGooglePortabilityError("");
    setGooglePortabilityStatusMessage(sozluk.integrations.googleHistoryAuthWaiting);
    try {
      const status = (await window.lawcopilotDesktop.startGooglePortabilityAuth()) as GooglePortabilityAuthStatus;
      applyGooglePortabilityStatus(status, sozluk.integrations.googleHistoryAuthWaiting);
      if (status.configured) {
        setGooglePortabilityStatusMessage(sozluk.integrations.googleHistoryConnected);
        onUpdated?.();
      }
    } catch (error) {
      setGooglePortabilityStatusValue("invalid");
      setGooglePortabilityStatusMessage("");
      setGooglePortabilityError(error instanceof Error ? error.message : sozluk.integrations.googleHistoryAuthError);
    } finally {
      setGooglePortabilityBusy(false);
    }
  }

  async function syncGooglePortabilityHistory() {
    if (!window.lawcopilotDesktop?.syncGooglePortabilityData) {
      setGooglePortabilityError(sozluk.integrations.desktopOnly);
      return;
    }
    setGooglePortabilityBusy(true);
    setGooglePortabilityError("");
    try {
      const result = (await window.lawcopilotDesktop.syncGooglePortabilityData()) as {
        message?: string;
        status?: {
          youtube_history_count?: number;
          chrome_history_count?: number;
          portability_status?: string;
          portability_last_sync_at?: string;
          portability_scopes?: string[];
          portability_account_label?: string;
        };
        patch?: {
          googlePortability?: {
            archiveJobId?: string;
            archiveState?: string;
            archiveStartedAt?: string;
            archiveExportTime?: string;
            lastSyncAt?: string;
            lastImportedAt?: string;
            youtubeHistoryCount?: number;
            chromeHistoryCount?: number;
          };
        };
        archiveJobId?: string;
        archiveState?: string;
      };
      const status = result.status || {};
      const patch = result.patch?.googlePortability || {};
      setGooglePortabilityArchiveJobId(String(result.archiveJobId || patch.archiveJobId || googlePortabilityArchiveJobId || ""));
      setGooglePortabilityArchiveState(String(result.archiveState || patch.archiveState || googlePortabilityArchiveState || ""));
      setGooglePortabilityLastSyncAt(
        String(status.portability_last_sync_at || patch.lastSyncAt || googlePortabilityLastSyncAt || ""),
      );
      setGooglePortabilityLastImportedAt(String(patch.lastImportedAt || googlePortabilityLastImportedAt || ""));
      setGoogleYouTubeHistoryCount(Number(status.youtube_history_count || patch.youtubeHistoryCount || 0));
      setGoogleChromeHistoryCount(Number(status.chrome_history_count || patch.chromeHistoryCount || 0));
      setGooglePortabilityScopes(Array.isArray(status.portability_scopes) ? status.portability_scopes : googlePortabilityScopes);
      if (status.portability_account_label) {
        setGooglePortabilityAccountLabel(String(status.portability_account_label));
      }
      const nextConfigured = Boolean(
        status.portability_status ? String(status.portability_status).toLowerCase() === "connected" : googlePortabilityConfigured,
      );
      const nextPending = ["IN_PROGRESS", "CREATING", "PENDING"].includes(
        String(result.archiveState || patch.archiveState || googlePortabilityArchiveState || "").toUpperCase(),
      );
      const nextHistoryConnected = nextConfigured || Number(status.youtube_history_count || patch.youtubeHistoryCount || 0) > 0 || Number(status.chrome_history_count || patch.chromeHistoryCount || 0) > 0;
      setGooglePortabilityConfigured(nextConfigured);
      setGooglePortabilityStatusValue(nextPending ? "pending" : nextHistoryConnected ? "valid" : googlePortabilityStatusValue);
      setGooglePortabilityStatusMessage(
        String(
          result.message
            || (nextPending ? sozluk.integrations.googleHistorySyncStarted : nextHistoryConnected ? sozluk.integrations.googleHistoryConnected : sozluk.integrations.googleHistoryStatusIdle),
        ),
      );
      onUpdated?.();
    } catch (error) {
      setGooglePortabilityStatusValue("invalid");
      setGooglePortabilityError(error instanceof Error ? error.message : sozluk.integrations.googleHistoryAuthError);
    } finally {
      setGooglePortabilityBusy(false);
    }
  }

  async function importGoogleHistoryArchive() {
    if (!window.lawcopilotDesktop?.chooseGoogleHistoryArchive || !window.lawcopilotDesktop?.importGoogleHistoryArchive) {
      setGooglePortabilityError(sozluk.integrations.desktopOnly);
      return;
    }
    setGooglePortabilityBusy(true);
    setGooglePortabilityError("");
    try {
      const selection = (await window.lawcopilotDesktop.chooseGoogleHistoryArchive()) as {
        canceled?: boolean;
        filePaths?: string[];
      };
      if (selection.canceled || !Array.isArray(selection.filePaths) || selection.filePaths.length === 0) {
        setGooglePortabilityBusy(false);
        return;
      }
      const result = (await window.lawcopilotDesktop.importGoogleHistoryArchive(selection.filePaths)) as {
        message?: string;
        status?: {
          youtube_history_count?: number;
          chrome_history_count?: number;
          portability_status?: string;
          portability_last_sync_at?: string;
          portability_account_label?: string;
        };
        patch?: {
          googlePortability?: {
            lastSyncAt?: string;
            lastImportedAt?: string;
            youtubeHistoryCount?: number;
            chromeHistoryCount?: number;
            accountLabel?: string;
            archiveState?: string;
          };
        };
      };
      const status = result.status || {};
      const patch = result.patch?.googlePortability || {};
      setGooglePortabilityArchiveState(String(patch.archiveState || "IMPORTED"));
      setGooglePortabilityLastSyncAt(String(status.portability_last_sync_at || patch.lastSyncAt || new Date().toISOString()));
      setGooglePortabilityLastImportedAt(String(patch.lastImportedAt || new Date().toISOString()));
      setGoogleYouTubeHistoryCount(Number(status.youtube_history_count || patch.youtubeHistoryCount || 0));
      setGoogleChromeHistoryCount(Number(status.chrome_history_count || patch.chromeHistoryCount || 0));
      if (status.portability_account_label || patch.accountLabel) {
        setGooglePortabilityAccountLabel(String(status.portability_account_label || patch.accountLabel || ""));
      }
      setGooglePortabilityConfigured(false);
      setGooglePortabilityStatusValue("valid");
      setGooglePortabilityStatusMessage(String(result.message || sozluk.integrations.googleHistoryTakeoutImported));
      setGooglePortabilityError("");
      onUpdated?.();
    } catch (error) {
      setGooglePortabilityStatusValue("invalid");
      setGooglePortabilityError(error instanceof Error ? error.message : sozluk.integrations.googleHistoryTakeoutSelectError);
    } finally {
      setGooglePortabilityBusy(false);
    }
  }

  async function cancelGooglePortabilityAuthFlow() {
    if (!window.lawcopilotDesktop?.cancelGooglePortabilityAuth) {
      return;
    }
    const status = (await window.lawcopilotDesktop.cancelGooglePortabilityAuth()) as GooglePortabilityAuthStatus;
    applyGooglePortabilityStatus(status, sozluk.integrations.googleAuthCancelled);
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

  async function refreshOutlookStatus() {
    if (!window.lawcopilotDesktop?.getOutlookAuthStatus) {
      setOutlookError(sozluk.integrations.desktopOnly);
      return;
    }
    setOutlookBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.getOutlookAuthStatus()) as OutlookAuthStatus;
      applyOutlookStatus(status, sozluk.integrations.outlookAuthIdle);
    } catch (error) {
      setOutlookStatusValue("invalid");
      setOutlookError(error instanceof Error ? error.message : sozluk.integrations.outlookAuthError);
    } finally {
      setOutlookBusy(false);
    }
  }

  async function saveOutlookClientSetup() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setOutlookError(sozluk.integrations.desktopOnly);
      return false;
    }
    if (!outlookClientId.trim()) {
      setOutlookError(sozluk.integrations.outlookClientSetupRequired);
      return false;
    }
    setOutlookBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        outlook: {
          clientId: outlookClientId.trim(),
          tenantId: outlookTenantId.trim() || "common",
        },
      });
      await refreshOutlookStatus();
      setOutlookError("");
      setOutlookStatusMessage(sozluk.integrations.outlookClientSaved);
      return true;
    } catch (error) {
      setOutlookError(error instanceof Error ? error.message : sozluk.integrations.outlookClientSaveError);
      return false;
    } finally {
      setOutlookBusy(false);
    }
  }

  async function startOutlookAuthFlow() {
    if (!window.lawcopilotDesktop?.startOutlookAuth) {
      setOutlookError(sozluk.integrations.desktopOnly);
      return;
    }
    setOutlookBusy(true);
    setOutlookError("");
    setOutlookStatusMessage(sozluk.integrations.outlookAuthWaiting);
    try {
      const status = (await window.lawcopilotDesktop.startOutlookAuth()) as OutlookAuthStatus;
      applyOutlookStatus(status, sozluk.integrations.outlookAuthConnected);
      setOutlookEnabled(true);
      if (status.configured && window.lawcopilotDesktop?.syncOutlookData) {
        const result = (await window.lawcopilotDesktop.syncOutlookData()) as { message?: string; patch?: { outlook?: { lastSyncAt?: string } } };
        setOutlookStatusMessage(String(result.message || sozluk.integrations.outlookSynced));
        setOutlookLastSyncAt(String(result.patch?.outlook?.lastSyncAt || new Date().toISOString()));
      }
      onUpdated?.();
    } catch (error) {
      setOutlookStatusValue("invalid");
      setOutlookStatusMessage("");
      setOutlookError(error instanceof Error ? error.message : sozluk.integrations.outlookAuthError);
    } finally {
      setOutlookBusy(false);
    }
  }

  async function connectOutlookAccount() {
    const setupSaved = await saveOutlookClientSetup();
    if (!setupSaved) {
      return;
    }
    await startOutlookAuthFlow();
  }

  async function disconnectOutlook() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setOutlookError(sozluk.integrations.desktopOnly);
      return;
    }
    setOutlookBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        outlook: {
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
          lastSyncAt: "",
        },
      });
      applyOutlookStatus({ configured: false, clientReady: outlookClientReady, scopes: [], tenantId: outlookTenantId, message: sozluk.integrations.outlookDisconnected });
      setOutlookEnabled(false);
      setOutlookLastSyncAt("");
      onUpdated?.();
    } catch (error) {
      setOutlookError(error instanceof Error ? error.message : sozluk.integrations.outlookDisconnectError);
    } finally {
      setOutlookBusy(false);
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
      setProviderError(friendlyCodexErrorMessage(error));
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
    setProviderError("");
    try {
      const response = (await window.lawcopilotDesktop.validateProviderConfig({
        type: providerType,
        baseUrl: normalizeProviderBaseUrl(providerType, providerBaseUrl, currentProviderPreset.baseUrl),
        model: providerModel,
        apiKey: providerApiKey.trim(),
      })) as { message?: string; provider?: { availableModels?: string[]; baseUrl?: string; model?: string; validationStatus?: string } };
      setProviderStatusMessage(String(response.message || sozluk.integrations.providerValidated));
      setProviderStatusValue(String(response.provider?.validationStatus || "valid"));
      setProviderAvailableModels(uniqueProviderModels(Array.isArray(response.provider?.availableModels) ? response.provider?.availableModels || [] : []));
      if (response.provider?.baseUrl) {
        setProviderBaseUrl(normalizeProviderBaseUrl(providerType, String(response.provider.baseUrl), currentProviderPreset.baseUrl));
      }
      if (!providerModel && response.provider?.model) {
        setProviderModel(String(response.provider.model));
      }
      setProviderError("");
    } catch (error) {
      setProviderStatusMessage("");
      setProviderStatusValue("invalid");
      setProviderError(friendlyProviderErrorMessage(error, "validate"));
    } finally {
      setProviderBusy(false);
    }
  }

  async function saveProvider() {
    if (providerUsesBrowserAuth) {
      await startCodexAuthFlow();
      return;
    }
    const canSaveProvider = Boolean(
      window.lawcopilotDesktop?.saveIntegrationConfig
      || (window.lawcopilotDesktop?.saveIntegrationConfigFast && window.lawcopilotDesktop?.ensureBackend),
    );
    if (!canSaveProvider || !window.lawcopilotDesktop?.validateProviderConfig) {
      setProviderError(sozluk.integrations.desktopOnly);
      return;
    }
    setProviderBusy(true);
    setProviderRefreshPending(false);
    setProviderError("");
    try {
      const normalizedBaseUrl = normalizeProviderBaseUrl(providerType, providerBaseUrl, currentProviderPreset.baseUrl);
      const nextProviderTypeChanged = providerType !== savedProviderType;
      const trimmedProviderApiKey = providerApiKey.trim();
      const validation = (await window.lawcopilotDesktop.validateProviderConfig({
        type: providerType,
        baseUrl: normalizedBaseUrl,
        model: providerModel,
        apiKey: trimmedProviderApiKey,
      })) as { message?: string; provider?: { availableModels?: string[]; baseUrl?: string; model?: string; validationStatus?: string } };
      const validatedBaseUrl = normalizeProviderBaseUrl(
        providerType,
        String(validation.provider?.baseUrl || normalizedBaseUrl),
        currentProviderPreset.baseUrl,
      );
      const validatedModel = String(validation.provider?.model || providerModel);
      const validatedModels = uniqueProviderModels(Array.isArray(validation.provider?.availableModels) ? validation.provider?.availableModels || [] : []);
      const providerPatch: {
        type: string;
        authMode: string;
        baseUrl: string;
        model: string;
        accountLabel: string;
        availableModels: string[];
        oauthConnected: boolean;
        oauthLastError: string;
        apiKey?: string;
        configuredAt: string;
        validationStatus: string;
      } = {
        type: providerType,
        authMode: "api-key",
        baseUrl: validatedBaseUrl,
        model: validatedModel,
        accountLabel: providerLabel(providerType),
        availableModels: validatedModels,
        oauthConnected: false,
        oauthLastError: "",
        configuredAt: new Date().toISOString(),
        validationStatus: String(validation.provider?.validationStatus || "valid"),
      };
      if (providerNeedsKey && (nextProviderTypeChanged || trimmedProviderApiKey)) {
        providerPatch.apiKey = trimmedProviderApiKey;
      }
      const saveIntegrationConfig = window.lawcopilotDesktop?.saveIntegrationConfig;
      const canRefreshInBackground = Boolean(window.lawcopilotDesktop?.saveIntegrationConfigFast && window.lawcopilotDesktop?.ensureBackend);
      if (canRefreshInBackground) {
        const saved = (await window.lawcopilotDesktop.saveIntegrationConfigFast?.({
          provider: providerPatch,
        })) as SanitizedIntegrationConfig;
        setSavedProviderType(String(saved.provider?.type || providerType));
        setProviderBaseUrl(validatedBaseUrl);
        setProviderModel(validatedModel);
        setProviderAvailableModels(validatedModels);
        setProviderStatusValue("pending");
        setProviderMaskedKey(String(saved.provider?.apiKeyMasked || ""));
        setProviderStatusMessage(sozluk.integrations.providerSavedPendingRefresh);
        setProviderError("");
        setProviderApiKey("");
        setProviderRefreshPending(true);
        void window.lawcopilotDesktop.ensureBackend?.({ forceRestart: true })
          .then((runtime) => {
            const runtimeProvider = runtime?.provider && typeof runtime.provider === "object"
              ? runtime.provider as Record<string, unknown>
              : {};
            const refreshedBaseUrl = normalizeProviderBaseUrl(
              providerType,
              String(runtimeProvider.baseUrl || validatedBaseUrl),
              currentProviderPreset.baseUrl,
            );
            const refreshedModel = normalizeProviderModel(
              providerType,
              String(runtimeProvider.model || validatedModel),
              currentProviderPreset.defaultModel,
            );
            const refreshedModels = uniqueProviderModels(
              Array.isArray(runtimeProvider.availableModels)
                ? (runtimeProvider.availableModels as string[])
                : validatedModels,
            );
            setSavedProviderType(String(runtimeProvider.type || providerType));
            setProviderBaseUrl(refreshedBaseUrl);
            setProviderModel(refreshedModel);
            setProviderAvailableModels(refreshedModels);
            setProviderMaskedKey(String(runtimeProvider.apiKeyMasked || saved.provider?.apiKeyMasked || ""));
            setProviderStatusValue(String(runtimeProvider.validationStatus || "valid"));
            setProviderStatusMessage(sozluk.integrations.providerSavedReady);
            setProviderError("");
            setProviderRefreshPending(false);
            onUpdated?.();
          })
          .catch((error) => {
            setProviderStatusValue(String(saved.provider?.validationStatus || validation.provider?.validationStatus || "pending"));
            setProviderStatusMessage(sozluk.integrations.providerSavedRefreshFailed);
            setProviderError(friendlyProviderErrorMessage(error, "save"));
            setProviderRefreshPending(false);
          });
        return;
      }
      const saved = (await saveIntegrationConfig?.({
        provider: providerPatch,
      })) as SanitizedIntegrationConfig;
      setSavedProviderType(String(saved.provider?.type || providerType));
      setProviderBaseUrl(validatedBaseUrl);
      setProviderModel(validatedModel);
      setProviderAvailableModels(validatedModels);
      setProviderStatusValue(String(saved.provider?.validationStatus || validation.provider?.validationStatus || "valid"));
      setProviderMaskedKey(String(saved.provider?.apiKeyMasked || ""));
      setProviderStatusMessage(String(saved.runtimeWarning || validation.message || sozluk.integrations.providerSaved));
      setProviderError("");
      setProviderApiKey("");
      onUpdated?.();
    } catch (error) {
      setProviderError(friendlyProviderErrorMessage(error, "save"));
    } finally {
      setProviderBusy(false);
    }
  }

  async function disconnectProvider() {
    const desktop = window.lawcopilotDesktop;
    const canSaveProvider = Boolean(
      desktop?.saveIntegrationConfig
      || (desktop?.saveIntegrationConfigFast && desktop?.ensureBackend),
    );
    if (!canSaveProvider) {
      setProviderError(sozluk.integrations.desktopOnly);
      return;
    }
    setProviderBusy(true);
    setProviderRefreshPending(false);
    setProviderError("");
    const preset = providerPreset(providerType);
    const providerPatch = {
      type: providerType,
      authMode: providerUsesBrowserAuth ? "oauth" : (providerNeedsKey ? "api-key" : "none"),
      baseUrl: normalizeProviderBaseUrl(providerType, preset.baseUrl, preset.baseUrl),
      model: normalizeProviderModel(providerType, providerModel, preset.defaultModel),
      accountLabel: "",
      availableModels: [],
      oauthConnected: false,
      oauthLastError: "",
      configuredAt: "",
      validationStatus: "pending",
      apiKey: "",
    };
    try {
      const canRefreshInBackground = Boolean(desktop?.saveIntegrationConfigFast && desktop?.ensureBackend);
      if (canRefreshInBackground) {
        const saved = (await desktop?.saveIntegrationConfigFast?.({
          provider: providerPatch,
        })) as SanitizedIntegrationConfig;
        setSavedProviderType(String(saved.provider?.type || providerType));
        setProviderBaseUrl(String(saved.provider?.baseUrl || providerPatch.baseUrl));
        setProviderModel(String(saved.provider?.model || providerPatch.model));
        setProviderAvailableModels([]);
        setProviderMaskedKey("");
        setProviderApiKey("");
        setProviderStatusValue("pending");
        setProviderStatusMessage(sozluk.integrations.providerDisconnected);
        setCodexConfigured(false);
        setCodexAuthUrl("");
        setCodexAuthState("");
        setCodexCallbackUrl("");
        setCodexBrowserTarget("");
        setProviderRefreshPending(true);
        void desktop?.ensureBackend?.({ forceRestart: true })
          .then(() => {
            setProviderRefreshPending(false);
            onUpdated?.();
          })
          .catch((error) => {
            setProviderRefreshPending(false);
            setProviderError(friendlyProviderErrorMessage(error, "save"));
          });
        return;
      }
      const saved = (await desktop?.saveIntegrationConfig?.({
        provider: providerPatch,
      })) as SanitizedIntegrationConfig;
      setSavedProviderType(String(saved.provider?.type || providerType));
      setProviderBaseUrl(String(saved.provider?.baseUrl || providerPatch.baseUrl));
      setProviderModel(String(saved.provider?.model || providerPatch.model));
      setProviderAvailableModels([]);
      setProviderMaskedKey("");
      setProviderApiKey("");
      setProviderStatusValue("pending");
      setProviderStatusMessage(sozluk.integrations.providerDisconnected);
      setCodexConfigured(false);
      setCodexAuthUrl("");
      setCodexAuthState("");
      setCodexCallbackUrl("");
      setCodexBrowserTarget("");
      onUpdated?.();
    } catch (error) {
      setProviderError(friendlyProviderErrorMessage(error, "save"));
    } finally {
      setProviderBusy(false);
    }
  }

  async function refreshTelegramStatus() {
    if (!window.lawcopilotDesktop?.getTelegramStatus) {
      setTelegramError(sozluk.integrations.desktopOnly);
      return;
    }
    setTelegramBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.getTelegramStatus()) as Record<string, unknown>;
      applyTelegramStatus(status, sozluk.integrations.telegramIdle);
    } catch (error) {
      setTelegramStatusValue("invalid");
      setTelegramError(error instanceof Error ? error.message : sozluk.integrations.telegramValidateError);
    } finally {
      setTelegramBusy(false);
    }
  }

  async function validateTelegram() {
    if (!window.lawcopilotDesktop?.validateTelegramConfig) {
      setTelegramError(sozluk.integrations.desktopOnly);
      return;
    }
    if (telegramMode === "web") {
      await refreshTelegramStatus();
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
    setTelegramBusy(true);
    try {
      const saved = (await window.lawcopilotDesktop.saveIntegrationConfig({
        telegram: {
          enabled: telegramSetupEnabled,
          mode: telegramMode,
          ...(telegramMode === "bot" && telegramBotToken ? { botToken: telegramBotToken } : {}),
          allowedUserId: telegramMode === "bot" ? telegramAllowedUserId : "",
          botUsername: telegramMode === "bot" ? telegramBotUsername : "",
          webSessionName: telegramMode === "web" ? telegramWebSessionName : "",
          configuredAt: new Date().toISOString(),
          validationStatus: telegramStatusValue === "valid" ? "valid" : "pending",
        },
      })) as SanitizedIntegrationConfig;
      setTelegramMaskedToken(String(saved.telegram?.botTokenMasked || ""));
      if (telegramMode === "bot" && window.lawcopilotDesktop?.syncTelegramData && telegramEnabled) {
        const syncResponse = (await window.lawcopilotDesktop.syncTelegramData()) as { message?: string };
        setTelegramStatusMessage(String(syncResponse.message || sozluk.integrations.telegramSaved));
      } else {
        setTelegramStatusMessage(sozluk.integrations.telegramSaved);
      }
      setTelegramError("");
      setTelegramBotToken("");
      onUpdated?.();
    } catch (error) {
      setTelegramError(error instanceof Error ? error.message : sozluk.integrations.telegramSaveError);
    } finally {
      setTelegramBusy(false);
    }
  }

  async function startTelegramWebFlow() {
    if (!window.lawcopilotDesktop?.startTelegramWebLink) {
      setTelegramError(sozluk.integrations.desktopOnly);
      return;
    }
    setTelegramBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig?.({
        telegram: {
          enabled: telegramSetupEnabled,
          mode: "web",
          webSessionName: telegramWebSessionName,
          configuredAt: new Date().toISOString(),
          validationStatus: "pending",
        },
      });
      const status = (await window.lawcopilotDesktop.startTelegramWebLink()) as Record<string, unknown>;
      applyTelegramStatus(status, sozluk.integrations.telegramWebLinkStarted);
      onUpdated?.();
    } catch (error) {
      setTelegramError(error instanceof Error ? error.message : sozluk.integrations.telegramSaveError);
    } finally {
      setTelegramBusy(false);
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
    if (whatsappUsesWebMode) {
      setWhatsAppStatusMessage(sozluk.integrations.whatsappWebValidateHint);
      setWhatsAppError("");
      return;
    }
    if (!window.lawcopilotDesktop?.validateWhatsAppConfig) {
      setWhatsAppError(sozluk.integrations.desktopOnly);
      return;
    }
    setWhatsAppBusy(true);
    try {
      const response = (await window.lawcopilotDesktop.validateWhatsAppConfig({
        enabled: true,
        mode: "business_cloud",
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
      const whatsappPatch = whatsappUsesWebMode
        ? {
          enabled: true,
          mode: "web",
          webSessionName: whatsAppWebSessionName.trim() || "default",
          webStatus: whatsAppWebStatus || "idle",
          webAccountLabel: whatsAppWebAccountLabel,
          webLastReadyAt: whatsAppWebLastReadyAt,
          webLastSyncAt: whatsAppWebLastSyncAt,
          configuredAt: new Date().toISOString(),
          validationStatus: whatsAppStatusValue === "valid" ? "valid" : "pending",
        }
        : {
          enabled: true,
          mode: "business_cloud",
          ...(whatsAppAccessToken ? { accessToken: whatsAppAccessToken } : {}),
          phoneNumberId: whatsAppPhoneNumberId,
          businessLabel: whatsAppBusinessLabel,
          displayPhoneNumber: whatsAppDisplayNumber,
          verifiedName: whatsAppVerifiedName,
          configuredAt: new Date().toISOString(),
          validationStatus: whatsAppStatusValue === "valid" ? "valid" : "pending",
        };
      const saved = (await window.lawcopilotDesktop.saveIntegrationConfig({
        whatsapp: whatsappPatch,
      })) as SanitizedIntegrationConfig;
      setWhatsAppMaskedToken(String(saved.whatsapp?.accessTokenMasked || ""));
      setWhatsAppStatusMessage(whatsappUsesWebMode ? sozluk.integrations.whatsappWebSaved : sozluk.integrations.whatsappSaved);
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

  async function disconnectWhatsApp() {
    const desktop = window.lawcopilotDesktop;
    if (!desktop?.disconnectWhatsApp && !desktop?.saveIntegrationConfig) {
      setWhatsAppError(sozluk.integrations.desktopOnly);
      return;
    }
    setWhatsAppBusy(true);
    try {
      if (desktop?.disconnectWhatsApp) {
        await desktop.disconnectWhatsApp();
      } else {
        await desktop.saveIntegrationConfig?.({
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
      }
      applyWhatsAppStatus({ configured: false, enabled: false, mode: whatsAppMode, message: sozluk.integrations.whatsappDisconnected });
      setWhatsAppMaskedToken("");
      setWhatsAppSetupBundle("");
      setWhatsAppWebQrDataUrl("");
      onUpdated?.();
    } catch (error) {
      setWhatsAppError(error instanceof Error ? error.message : sozluk.integrations.whatsappDisconnectError);
    } finally {
      setWhatsAppBusy(false);
    }
  }

  async function startWhatsAppWebLink() {
    if (!window.lawcopilotDesktop?.startWhatsAppWebLink) {
      setWhatsAppError(sozluk.integrations.desktopOnly);
      return;
    }
    setWhatsAppBusy(true);
    setWhatsAppError("");
    try {
      await saveWhatsApp();
      const status = (await window.lawcopilotDesktop.startWhatsAppWebLink()) as WhatsAppAuthStatus;
      applyWhatsAppStatus(status, sozluk.integrations.whatsappWebConnecting);
      setWhatsAppStatusMessage(status.message || sozluk.integrations.whatsappWebConnecting);
      onUpdated?.();
    } catch (error) {
      setWhatsAppError(error instanceof Error ? error.message : sozluk.integrations.whatsappWebConnectError);
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
      if (status.configured && window.lawcopilotDesktop?.syncXData) {
        const result = (await window.lawcopilotDesktop.syncXData()) as { message?: string; patch?: { x?: { lastSyncAt?: string } } };
        setXStatusMessage(String(result.message || sozluk.integrations.xSynced));
        setXLastSyncAt(String(result.patch?.x?.lastSyncAt || new Date().toISOString()));
      }
      onUpdated?.();
    } catch (error) {
      setXStatusValue("invalid");
      setXError(error instanceof Error ? error.message : sozluk.integrations.xAuthError);
    } finally {
      setXBusy(false);
    }
  }

  async function disconnectX() {
    if (!window.lawcopilotDesktop?.cancelXAuth && !window.lawcopilotDesktop?.saveIntegrationConfig) {
      setXError(sozluk.integrations.desktopOnly);
      return;
    }
    setXBusy(true);
    try {
      if (window.lawcopilotDesktop.cancelXAuth) {
        await window.lawcopilotDesktop.cancelXAuth();
      } else {
        await window.lawcopilotDesktop.saveIntegrationConfig?.({
          x: {
            enabled: false,
            accountLabel: "",
            userId: "",
            scopes: [],
            oauthConnected: false,
            oauthLastError: "",
            configuredAt: "",
            lastValidatedAt: "",
            validationStatus: "pending",
            lastSyncAt: "",
            accessToken: "",
            refreshToken: "",
            tokenType: "",
            expiryDate: "",
            clientId: "",
            clientSecret: "",
          },
        });
      }
      setXClientId("");
      setXClientSecret("");
      setXLastSyncAt("");
      applyXStatus({ configured: false, clientReady: false, scopes: [], message: sozluk.integrations.xDisconnected });
      setXEnabled(false);
      onUpdated?.();
    } catch (error) {
      setXError(error instanceof Error ? error.message : sozluk.integrations.xDisconnectError);
    } finally {
      setXBusy(false);
    }
  }

  async function refreshInstagramStatus() {
    if (!window.lawcopilotDesktop?.getInstagramAuthStatus) {
      setInstagramError(sozluk.integrations.desktopOnly);
      return;
    }
    setInstagramBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.getInstagramAuthStatus()) as InstagramAuthStatus;
      applyInstagramStatus(status, sozluk.integrations.instagramIdle);
    } catch (error) {
      setInstagramStatusValue("invalid");
      setInstagramError(error instanceof Error ? error.message : sozluk.integrations.instagramAuthError);
    } finally {
      setInstagramBusy(false);
    }
  }

  async function saveInstagramClientSetup() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setInstagramError(sozluk.integrations.desktopOnly);
      return;
    }
    if (!instagramClientId.trim() || !instagramClientSecret.trim()) {
      setInstagramError(sozluk.integrations.instagramClientSetupRequired);
      return;
    }
    setInstagramBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        instagram: {
          clientId: instagramClientId.trim(),
          clientSecret: instagramClientSecret.trim(),
          pageNameHint: instagramPageNameHint.trim(),
        },
      });
      setInstagramClientId("");
      setInstagramClientSecret("");
      await refreshInstagramStatus();
      setInstagramError("");
      setInstagramStatusMessage(sozluk.integrations.instagramClientSaved);
    } catch (error) {
      setInstagramError(error instanceof Error ? error.message : sozluk.integrations.instagramClientSaveError);
    } finally {
      setInstagramBusy(false);
    }
  }

  async function startInstagramAuthFlow() {
    if (!window.lawcopilotDesktop?.startInstagramAuth) {
      setInstagramError(sozluk.integrations.desktopOnly);
      return;
    }
    setInstagramBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.startInstagramAuth()) as InstagramAuthStatus;
      applyInstagramStatus(status, sozluk.integrations.instagramConnected);
      setInstagramEnabled(true);
      if (status.configured && window.lawcopilotDesktop?.syncInstagramData) {
        const result = (await window.lawcopilotDesktop.syncInstagramData()) as { message?: string; patch?: { instagram?: { lastSyncAt?: string } } };
        setInstagramStatusMessage(String(result.message || sozluk.integrations.instagramSynced));
        setInstagramLastSyncAt(String(result.patch?.instagram?.lastSyncAt || new Date().toISOString()));
      }
      onUpdated?.();
    } catch (error) {
      setInstagramStatusValue("invalid");
      setInstagramError(error instanceof Error ? error.message : sozluk.integrations.instagramAuthError);
    } finally {
      setInstagramBusy(false);
    }
  }

  async function disconnectInstagram() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setInstagramError(sozluk.integrations.desktopOnly);
      return;
    }
    setInstagramBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        instagram: {
          enabled: false,
          accountLabel: "",
          username: "",
          pageId: "",
          pageName: "",
          pageNameHint: "",
          instagramAccountId: "",
          scopes: [],
          oauthConnected: false,
          oauthLastError: "",
          validationStatus: "pending",
          accessToken: "",
          pageAccessToken: "",
          tokenType: "",
          expiryDate: "",
          lastSyncAt: "",
        },
      });
      applyInstagramStatus({ configured: false, clientReady: instagramClientReady, scopes: [], message: sozluk.integrations.instagramDisconnected });
      setInstagramEnabled(false);
      setInstagramPageName("");
      setInstagramUsername("");
      setInstagramLastSyncAt("");
      onUpdated?.();
    } catch (error) {
      setInstagramError(error instanceof Error ? error.message : sozluk.integrations.instagramDisconnectError);
    } finally {
      setInstagramBusy(false);
    }
  }

  async function refreshLinkedInStatus() {
    if (!window.lawcopilotDesktop?.getLinkedInStatus) {
      setLinkedInError(sozluk.integrations.desktopOnly);
      return;
    }
    setLinkedInBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.getLinkedInStatus()) as LinkedInAuthStatus;
      applyLinkedInStatus(status, sozluk.integrations.linkedinIdle);
    } catch (error) {
      setLinkedInStatusValue("invalid");
      setLinkedInError(error instanceof Error ? error.message : sozluk.integrations.linkedinAuthError);
    } finally {
      setLinkedInBusy(false);
    }
  }

  async function saveLinkedInClientSetup() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setLinkedInError(sozluk.integrations.desktopOnly);
      return;
    }
    if (linkedInMode === "web") {
      setLinkedInStatusMessage(sozluk.integrations.linkedinWebModeSaved);
      return;
    }
    if (!linkedInClientId.trim() || !linkedInClientSecret.trim()) {
      setLinkedInError(sozluk.integrations.linkedinClientSetupRequired);
      return;
    }
    setLinkedInBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        linkedin: {
          enabled: true,
          mode: "official",
          clientId: linkedInClientId.trim(),
          clientSecret: linkedInClientSecret.trim(),
        },
      });
      setLinkedInClientId("");
      setLinkedInClientSecret("");
      await refreshLinkedInStatus();
      setLinkedInError("");
      setLinkedInStatusMessage(sozluk.integrations.linkedinClientSaved);
    } catch (error) {
      setLinkedInError(error instanceof Error ? error.message : sozluk.integrations.linkedinClientSaveError);
    } finally {
      setLinkedInBusy(false);
    }
  }

  async function startLinkedInAuthFlow() {
    if (!window.lawcopilotDesktop?.startLinkedInAuth) {
      setLinkedInError(sozluk.integrations.desktopOnly);
      return;
    }
    setLinkedInBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.startLinkedInAuth()) as LinkedInAuthStatus;
      applyLinkedInStatus(status, sozluk.integrations.linkedinConnected);
      setLinkedInEnabled(true);
      setLinkedInLastSyncAt(new Date().toISOString());
      onUpdated?.();
    } catch (error) {
      setLinkedInStatusValue("invalid");
      setLinkedInError(error instanceof Error ? error.message : sozluk.integrations.linkedinAuthError);
    } finally {
      setLinkedInBusy(false);
    }
  }

  async function startLinkedInWebFlow() {
    if (!window.lawcopilotDesktop?.startLinkedInWebLink) {
      setLinkedInError(sozluk.integrations.desktopOnly);
      return;
    }
    setLinkedInBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig?.({
        linkedin: {
          enabled: true,
          mode: "web",
          webSessionName: linkedInWebSessionName,
          configuredAt: new Date().toISOString(),
          validationStatus: "pending",
        },
      });
      const status = (await window.lawcopilotDesktop.startLinkedInWebLink()) as LinkedInAuthStatus;
      applyLinkedInStatus(status, sozluk.integrations.linkedinWebLinkStarted);
      setLinkedInEnabled(true);
      onUpdated?.();
    } catch (error) {
      setLinkedInStatusValue("invalid");
      setLinkedInError(error instanceof Error ? error.message : sozluk.integrations.linkedinAuthError);
    } finally {
      setLinkedInBusy(false);
    }
  }

  async function disconnectLinkedIn() {
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setLinkedInError(sozluk.integrations.desktopOnly);
      return;
    }
    setLinkedInBusy(true);
    try {
      await window.lawcopilotDesktop.saveIntegrationConfig({
        linkedin: {
          enabled: false,
          accountLabel: "",
          userId: "",
          personUrn: "",
          email: "",
          scopes: [],
          oauthConnected: false,
          oauthLastError: "",
          validationStatus: "pending",
          accessToken: "",
          tokenType: "",
          expiryDate: "",
        },
      });
      applyLinkedInStatus({ configured: false, clientReady: linkedInClientReady, scopes: [], message: sozluk.integrations.linkedinDisconnected });
      setLinkedInEnabled(false);
      onUpdated?.();
    } catch (error) {
      setLinkedInError(error instanceof Error ? error.message : sozluk.integrations.linkedinDisconnectError);
    } finally {
      setLinkedInBusy(false);
    }
  }

  if (!desktopReady) {
    return <EmptyState title={sozluk.integrations.desktopOnlyTitle} description={sozluk.integrations.desktopOnlyDescription} />;
  }

  if (simpleMode) {
    return (
      <div className="setup-form-stack">
        {showSection("provider") ? (
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
                onChange={(event) => handleProviderTypeChange(event.target.value)}
              >
                {PROVIDER_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label()}
                  </option>
                ))}
              </select>
            </label>

            <label className="setup-form-field">
              <span className="setup-form-field__label">{sozluk.integrations.providerModelLabel}</span>
              {suggestedProviderModels.length ? (
                <select className="select" value={providerModel} onChange={(event) => handleProviderModelChange(event.target.value)}>
                  {suggestedProviderModels.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              ) : (
                <input className="input" value={providerModel} onChange={(event) => handleProviderModelChange(event.target.value)} />
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
                placeholder={providerSecretPlaceholder(providerMaskedKey)}
              />
            ) : null}

            {providerUsesBrowserAuth && showCodexCallback ? (
              <div className="setup-form-field setup-form-field--wide">
                <div className="callout callout--accent">
                  <strong>{sozluk.integrations.codexAutoFlowTitle}</strong>
                  <p style={{ marginBottom: 0 }}>
                    {codexConfigured ? sozluk.integrations.codexAuthConnected : sozluk.integrations.codexAutoFlowDescription}
                  </p>
                </div>
              </div>
            ) : null}
          </div>

          <p className="setup-form-section__hint">
            {providerUsesBrowserAuth ? sozluk.integrations.providerSimpleBrowserHint : sozluk.integrations.providerSimpleKeyHint}
          </p>

          {providerHasConfiguredConnection ? (
            <p className="setup-form-section__hint">{sozluk.integrations.providerConnectedNote}</p>
          ) : savedProviderType && savedProviderType !== providerType ? (
            <p className="setup-form-section__hint">{sozluk.integrations.providerSwitchedNote}</p>
          ) : null}

          <div className="setup-form-actions">
            <button className="button" type="button" onClick={saveProvider} disabled={providerActionBusy}>
              {providerUsesBrowserAuth
                ? codexConfigured
                  ? sozluk.integrations.providerReconnectAction
                  : sozluk.integrations.providerConnectAction
                : providerHasConfiguredConnection
                  ? sozluk.integrations.providerUpdateAction
                  : sozluk.integrations.providerConnectAction}
            </button>
            {providerHasConfiguredConnection ? (
              <button className="button button--secondary" type="button" onClick={disconnectProvider} disabled={providerActionBusy}>
                {sozluk.integrations.providerDisconnectAction}
              </button>
            ) : null}
          </div>

          {providerUsesBrowserAuth && showCodexCallback && showCodexManualFallback ? (
            <div className="setup-form-subsection">
              <strong>{sozluk.integrations.codexManualFallbackTitle}</strong>
              <p>{sozluk.integrations.codexManualOpenNote}</p>
              {codexAuthUrl ? (
                <label className="setup-form-field">
                  <span className="setup-form-field__label">{sozluk.integrations.codexAuthUrlLabel}</span>
                  <input className="input" readOnly value={codexAuthUrl} />
                </label>
              ) : null}
              <label className="setup-form-field">
                <span className="setup-form-field__label">{sozluk.integrations.codexCallbackLabel}</span>
                <textarea
                  className="textarea"
                  value={codexCallbackUrl}
                  onChange={(event) => setCodexCallbackUrl(event.target.value)}
                  placeholder={sozluk.integrations.codexCallbackPlaceholder}
                  rows={3}
                />
              </label>
              <div className="setup-form-actions">
                <button className="button button--secondary" type="button" onClick={submitCodexCallback} disabled={codexBusy || !codexCallbackUrl.trim()}>
                  {sozluk.integrations.codexSubmitCallback}
                </button>
              </div>
            </div>
          ) : null}

          {providerStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{providerStatusMessage}</p> : null}
          {providerError ? <p className="setup-form-feedback setup-form-feedback--error">{providerError}</p> : null}
        </section>
        ) : null}

        {showSection("google") ? (
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

          {compactSettingsMode ? (
            <details className="setup-form-details">
              <summary className="setup-form-details__summary">{sozluk.integrations.showGuideDetails}</summary>
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
            </details>
          ) : (
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
          )}

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
            </div>
          ) : null}

          <div className="setup-form-actions">
            <button
              className="button"
              type="button"
              onClick={connectGoogleAccount}
              disabled={googleBusy || (!googleClientReady && (!googleClientId.trim() || !googleClientSecret.trim()))}
            >
              {googleConfigured ? sozluk.integrations.googleReconnectAction : sozluk.integrations.googleConnectAction}
            </button>
            {googleConfigured ? (
              <button className="button button--secondary" type="button" onClick={disconnectGoogle} disabled={googleBusy}>
                {sozluk.integrations.disconnectAction}
              </button>
            ) : null}
          </div>

          {googleAuthUrl && !googleConfigured ? (
            <details className="setup-form-details">
              <summary className="setup-form-details__summary">{sozluk.integrations.showManualLink}</summary>
              <div className="setup-form-subsection">
                <strong>{sozluk.integrations.googleAuthUrlLabel}</strong>
                <p>{sozluk.integrations.googleManualOpenNote}</p>
                <label className="setup-form-field">
                  <span className="setup-form-field__label">{sozluk.integrations.googleAuthUrlLabel}</span>
                  <input className="input" readOnly value={googleAuthUrl} />
                </label>
                {googleBrowserTarget ? <p className="setup-form-section__hint">{`Tarayıcı hedefi: ${googleBrowserTarget}`}</p> : null}
              </div>
            </details>
          ) : null}

          <div className="setup-form-subsection">
            <strong>{sozluk.integrations.googleHistoryTitle}</strong>
            <p>{sozluk.integrations.googleHistorySubtitle}</p>
            <div className="setup-form-section__badges">
              <StatusBadge tone={googleHistoryConnected ? "accent" : "warning"}>{googleHistoryStatusLabel}</StatusBadge>
              {googlePortabilityAccountLabel ? <StatusBadge>{googlePortabilityAccountLabel}</StatusBadge> : null}
              <StatusBadge tone={googleYouTubeHistoryCount > 0 ? "accent" : "warning"}>
                {`${sozluk.integrations.googleHistoryYoutubeLabel}: ${googleYouTubeHistoryCount}`}
              </StatusBadge>
              <StatusBadge tone={googleChromeHistoryCount > 0 ? "accent" : "warning"}>
                {`${sozluk.integrations.googleHistoryChromeLabel}: ${googleChromeHistoryCount}`}
              </StatusBadge>
            </div>
            <p className="setup-form-section__hint">{sozluk.integrations.googleHistoryGuideNote}</p>
            <p className="setup-form-section__hint">{sozluk.integrations.googleHistoryTakeoutNote}</p>
            <div className="setup-form-guide-box">
              <strong>{sozluk.integrations.googleHistoryTakeoutGuideTitle}</strong>
              <ol className="setup-form-guide-list">
                <li>{sozluk.integrations.googleHistoryTakeoutStep1}</li>
                <li>{sozluk.integrations.googleHistoryTakeoutStep2}</li>
                <li>{sozluk.integrations.googleHistoryTakeoutStep3}</li>
              </ol>
            </div>
            <div className="setup-form-actions">
              <a className="button button--secondary" href={INTEGRATION_GUIDES.googleTakeout} target="_blank" rel="noreferrer">
                {sozluk.integrations.googleHistoryTakeoutOpenAction}
              </a>
              <button className="button button--secondary" type="button" onClick={importGoogleHistoryArchive} disabled={googlePortabilityBusy}>
                {sozluk.integrations.googleHistoryTakeoutAction}
              </button>
            </div>
            {preferGoogleTakeoutImport ? (
              <details className="setup-form-details">
                <summary className="setup-form-details__summary">{sozluk.integrations.googleHistoryAdvancedAction}</summary>
                <div className="setup-form-subsection">
                  <p>{sozluk.integrations.googleHistoryPortabilityCountryNotice}</p>
                  <div className="setup-form-actions">
                    <button className="button button--secondary" type="button" onClick={connectGooglePortability} disabled={googlePortabilityBusy || (!googlePortabilityClientReady && (!googleClientId.trim() || !googleClientSecret.trim()))}>
                      {googleHistoryConnected ? sozluk.integrations.googleHistoryReconnectAction : sozluk.integrations.googleHistoryConnectAction}
                    </button>
                    <button className="button button--secondary" type="button" onClick={syncGooglePortabilityHistory} disabled={googlePortabilityBusy || !googlePortabilityConfigured}>
                      {sozluk.integrations.googleHistorySyncAction}
                    </button>
                    {googlePortabilityAuthUrl && !googlePortabilityConfigured ? (
                      <button className="button button--ghost" type="button" onClick={cancelGooglePortabilityAuthFlow} disabled={googlePortabilityBusy}>
                        {sozluk.integrations.googleHistoryCancelAction}
                      </button>
                    ) : null}
                  </div>
                </div>
              </details>
            ) : (
              <div className="setup-form-actions">
                <button className="button button--secondary" type="button" onClick={connectGooglePortability} disabled={googlePortabilityBusy || (!googlePortabilityClientReady && (!googleClientId.trim() || !googleClientSecret.trim()))}>
                  {googleHistoryConnected ? sozluk.integrations.googleHistoryReconnectAction : sozluk.integrations.googleHistoryConnectAction}
                </button>
                <button className="button button--secondary" type="button" onClick={syncGooglePortabilityHistory} disabled={googlePortabilityBusy || !googlePortabilityConfigured}>
                  {sozluk.integrations.googleHistorySyncAction}
                </button>
                {googlePortabilityAuthUrl && !googlePortabilityConfigured ? (
                  <button className="button button--ghost" type="button" onClick={cancelGooglePortabilityAuthFlow} disabled={googlePortabilityBusy}>
                    {sozluk.integrations.googleHistoryCancelAction}
                  </button>
                ) : null}
              </div>
            )}
            {googlePortabilityAuthUrl && !googlePortabilityConfigured ? (
              <details className="setup-form-details">
                <summary className="setup-form-details__summary">{sozluk.integrations.showManualLink}</summary>
                <div className="setup-form-subsection">
                  <strong>{sozluk.integrations.googleHistoryTitle}</strong>
                  <p>{sozluk.integrations.googleHistoryAuthWaiting}</p>
                  <label className="setup-form-field">
                    <span className="setup-form-field__label">{sozluk.integrations.googleAuthUrlLabel}</span>
                    <input className="input" readOnly value={googlePortabilityAuthUrl} />
                  </label>
                  {googlePortabilityBrowserTarget ? <p className="setup-form-section__hint">{`Tarayıcı hedefi: ${googlePortabilityBrowserTarget}`}</p> : null}
                </div>
              </details>
            ) : null}
            {googlePortabilityLastSyncAt ? (
              <p className="setup-form-section__hint">{`Son eşitleme: ${new Date(googlePortabilityLastSyncAt).toLocaleString("tr-TR")}`}</p>
            ) : null}
          </div>

          {googleStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{googleStatusMessage}</p> : null}
          {googleError ? <p className="setup-form-feedback setup-form-feedback--error">{googleError}</p> : null}
          {googlePortabilityStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{googlePortabilityStatusMessage}</p> : null}
          {googlePortabilityError ? <p className="setup-form-feedback setup-form-feedback--error">{googlePortabilityError}</p> : null}
        </section>
        ) : null}

        {showSection("outlook") ? (
        <section className="setup-form-section" id="integration-outlook" style={{ scrollMarginTop: "1rem" }}>
          <div className="setup-form-section__header">
            <div>
              <h3 className="setup-form-section__title">{sozluk.integrations.outlookSimpleTitle}</h3>
              <p className="setup-form-section__meta">{sozluk.integrations.outlookSimpleSubtitle}</p>
            </div>
            <div className="setup-form-section__badges">
              <StatusBadge tone={outlookConfigured ? "accent" : "warning"}>
                {outlookConfigured ? sozluk.integrations.outlookConnected : sozluk.integrations.outlookNotConnected}
              </StatusBadge>
              {outlookAccountLabel ? <StatusBadge>{outlookAccountLabel}</StatusBadge> : null}
            </div>
          </div>

          <div className="setup-form-section__guide-row">
            <p className="setup-form-section__hint">{sozluk.integrations.outlookSimpleAutoSync}</p>
            <a className="setup-form-guide-link" href={INTEGRATION_GUIDES.outlook} target="_blank" rel="noreferrer">
              {sozluk.integrations.outlookGuideConsoleAction}
            </a>
          </div>

          {compactSettingsMode ? (
            <details className="setup-form-details">
              <summary className="setup-form-details__summary">{sozluk.integrations.showGuideDetails}</summary>
              <div className="setup-form-guide-box">
                <strong>{sozluk.integrations.outlookGuideTitle}</strong>
                <p className="setup-form-guide-note">{sozluk.integrations.outlookGuideIntro}</p>
                <ol className="setup-form-guide-list">
                  <li>{sozluk.integrations.outlookGuideStep1}</li>
                  <li>{sozluk.integrations.outlookGuideStep2}</li>
                  <li>{sozluk.integrations.outlookGuideStep3}</li>
                  <li>{sozluk.integrations.outlookGuideStep4}</li>
                  <li>{sozluk.integrations.outlookGuideStep5}</li>
                </ol>
                <div className="setup-form-section__badges">
                  <StatusBadge>{sozluk.integrations.outlookGuideScopesTitle}</StatusBadge>
                  <span className="setup-form-guide-code">{sozluk.integrations.outlookGuideScopesValue}</span>
                </div>
              </div>
            </details>
          ) : (
            <div className="setup-form-guide-box">
              <strong>{sozluk.integrations.outlookGuideTitle}</strong>
              <p className="setup-form-guide-note">{sozluk.integrations.outlookGuideIntro}</p>
              <ol className="setup-form-guide-list">
                <li>{sozluk.integrations.outlookGuideStep1}</li>
                <li>{sozluk.integrations.outlookGuideStep2}</li>
                <li>{sozluk.integrations.outlookGuideStep3}</li>
                <li>{sozluk.integrations.outlookGuideStep4}</li>
                <li>{sozluk.integrations.outlookGuideStep5}</li>
              </ol>
              <div className="setup-form-section__badges">
                <StatusBadge>{sozluk.integrations.outlookGuideScopesTitle}</StatusBadge>
                <span className="setup-form-guide-code">{sozluk.integrations.outlookGuideScopesValue}</span>
              </div>
            </div>
          )}

          <div className="setup-form-subsection">
            <strong>{sozluk.integrations.outlookClientSetupTitle}</strong>
            <p>{sozluk.integrations.outlookClientSetupSubtitle}</p>
            <div className="setup-form-grid">
              <label className="setup-form-field">
                <span className="setup-form-field__label">{sozluk.integrations.outlookClientIdLabel}</span>
                <input className="input" value={outlookClientId} onChange={(event) => setOutlookClientId(event.target.value)} />
              </label>
              <label className="setup-form-field">
                <span className="setup-form-field__label">{sozluk.integrations.outlookTenantIdLabel}</span>
                <input className="input" value={outlookTenantId} onChange={(event) => setOutlookTenantId(event.target.value)} placeholder="common" />
              </label>
            </div>
            <div className="setup-form-actions">
              <button className="button" type="button" onClick={saveOutlookClientSetup} disabled={outlookBusy}>
                {outlookClientReady ? sozluk.integrations.providerUpdateAction : sozluk.integrations.outlookClientSaveAction}
              </button>
            </div>
          </div>

          {outlookLastSyncAt ? <p className="setup-form-section__hint">{`${sozluk.integrations.lastSyncLabel}: ${new Date(outlookLastSyncAt).toLocaleString("tr-TR")}`}</p> : null}

          <div className="setup-form-actions">
            <button className="button" type="button" onClick={connectOutlookAccount} disabled={outlookBusy || !outlookClientId.trim()}>
              {outlookConfigured ? sozluk.integrations.outlookReconnectAction : sozluk.integrations.outlookConnectAction}
            </button>
            {outlookConfigured ? (
              <button className="button button--secondary" type="button" onClick={disconnectOutlook} disabled={outlookBusy}>
                {sozluk.integrations.disconnectAction}
              </button>
            ) : null}
          </div>

          <div className="setup-form-section__badges">
            <StatusBadge tone={outlookClientReady ? "accent" : "warning"}>
              {outlookClientReady ? sozluk.integrations.outlookClientReady : sozluk.integrations.outlookClientMissing}
            </StatusBadge>
            <StatusBadge tone={outlookHasMail ? "accent" : "warning"}>Outlook Mail</StatusBadge>
            <StatusBadge tone={outlookHasCalendar ? "accent" : "warning"}>Outlook Takvim</StatusBadge>
          </div>

          {outlookStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{outlookStatusMessage}</p> : null}
          {outlookError ? <p className="setup-form-feedback setup-form-feedback--error">{outlookError}</p> : null}
        </section>
        ) : null}

        {showSection("telegram") ? (
        <section className="setup-form-section" id="integration-telegram" style={{ scrollMarginTop: "1rem" }}>
          <div className="setup-form-section__header">
            <div>
              <h3 className="setup-form-section__title">{sozluk.integrations.telegramSimpleTitle}</h3>
              <p className="setup-form-section__meta">{sozluk.integrations.telegramSimpleSubtitle}</p>
            </div>
            <div className="setup-form-section__badges">
              <StatusBadge>{telegramUsesWebMode ? sozluk.integrations.telegramModeWeb : sozluk.integrations.telegramModeBot}</StatusBadge>
              <StatusBadge tone={telegramStatusValue === "valid" ? "accent" : "warning"}>
                {telegramStatusValue === "valid" ? sozluk.integrations.validated : sozluk.integrations.notValidated}
              </StatusBadge>
              {telegramUsesWebMode && telegramWebAccountLabel ? <StatusBadge>{telegramWebAccountLabel}</StatusBadge> : null}
              {!telegramUsesWebMode && telegramBotUsername ? <StatusBadge>{telegramBotUsername}</StatusBadge> : null}
            </div>
          </div>

          <div className="setup-form-mode-switch">
            <button
              className={`setup-form-mode-switch__button ${telegramUsesWebMode ? "setup-form-mode-switch__button--active" : ""}`}
              type="button"
              onClick={() => setTelegramMode("web")}
            >
              {sozluk.integrations.telegramModeWeb}
            </button>
            <button
              className={`setup-form-mode-switch__button ${!telegramUsesWebMode ? "setup-form-mode-switch__button--active" : ""}`}
              type="button"
              onClick={() => setTelegramMode("bot")}
            >
              {sozluk.integrations.telegramModeBot}
            </button>
          </div>

          <div className="setup-form-section__guide-row">
            <p className="setup-form-section__hint">
              {telegramUsesWebMode ? sozluk.integrations.telegramWebSimpleHint : sozluk.integrations.telegramBotSimpleHint}
            </p>
            <a
              className="setup-form-guide-link"
              href={telegramUsesWebMode ? INTEGRATION_GUIDES.telegramWeb : INTEGRATION_GUIDES.telegramBot}
              target="_blank"
              rel="noreferrer"
            >
              {telegramUsesWebMode ? sozluk.integrations.telegramWebOfficialAction : sozluk.integrations.telegramBotGuideAction}
            </a>
            {telegramUsesWebMode ? (
              <a className="setup-form-guide-link" href={INTEGRATION_GUIDES.telegramWebHelp} target="_blank" rel="noreferrer">
                {sozluk.integrations.telegramWebGuideHelpAction}
              </a>
            ) : null}
          </div>

          {telegramUsesWebMode ? (
            <>
              <div className="setup-form-grid">
                <label className="setup-form-field">
                  <span className="setup-form-field__label">{sozluk.integrations.webSessionNameLabel}</span>
                  <input className="input" value={telegramWebSessionName} onChange={(event) => setTelegramWebSessionName(event.target.value)} />
                </label>
              </div>

              <p className="setup-form-section__hint">{sozluk.integrations.telegramWebNote}</p>
              {telegramWebLastReadyAt ? (
                <p className="setup-form-section__hint">{`${sozluk.integrations.lastReadyLabel}: ${new Date(telegramWebLastReadyAt).toLocaleString("tr-TR")}`}</p>
              ) : null}
              {telegramWebLastSyncAt ? (
                <p className="setup-form-section__hint">{`${sozluk.integrations.lastSyncLabel}: ${new Date(telegramWebLastSyncAt).toLocaleString("tr-TR")}`}</p>
              ) : null}

              <div className="setup-form-actions">
                <button className="button" type="button" onClick={startTelegramWebFlow} disabled={telegramBusy || !telegramSetupEnabled}>
                  {telegramBusy ? sozluk.integrations.validating : sozluk.integrations.telegramWebConnectAction}
                </button>
                <button className="button button--secondary" type="button" onClick={saveTelegram} disabled={telegramBusy}>
                  {sozluk.integrations.saveTelegram}
                </button>
              </div>
            </>
          ) : (
            <>
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
                <button className="button" type="button" onClick={saveTelegram} disabled={telegramBusy}>
                  {sozluk.integrations.saveTelegram}
                </button>
              </div>
            </>
          )}

          {telegramStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{telegramStatusMessage}</p> : null}
          {telegramError ? <p className="setup-form-feedback setup-form-feedback--error">{telegramError}</p> : null}
        </section>
        ) : null}

        {showSection("whatsapp") || showSection("x") || showSection("instagram") || showSection("linkedin") ? (
        <>
          {showSection("whatsapp") ? (
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

            <div className="setup-form-mode-switch">
              <button
                className={`setup-form-mode-switch__button ${whatsappUsesWebMode ? "setup-form-mode-switch__button--active" : ""}`}
                type="button"
                onClick={() => setWhatsAppMode("web")}
              >
                {sozluk.integrations.whatsappModeWeb}
              </button>
              <button
                className={`setup-form-mode-switch__button ${!whatsappUsesWebMode ? "setup-form-mode-switch__button--active" : ""}`}
                type="button"
                onClick={() => setWhatsAppMode("business_cloud")}
              >
                {sozluk.integrations.whatsappModeBusiness}
              </button>
            </div>

            <p className="setup-form-section__hint">{whatsappUsesWebMode ? sozluk.integrations.whatsappWebGuidedHint : sozluk.integrations.whatsappGuidedHint}</p>

            {compactSettingsMode ? (
              <details className="setup-form-details">
                <summary className="setup-form-details__summary">{sozluk.integrations.showGuideDetails}</summary>
                <div className="setup-form-guide-box">
                  <strong>{whatsappUsesWebMode ? sozluk.integrations.whatsappWebGuideTitle : sozluk.integrations.whatsappGuideTitle}</strong>
                  <p className="setup-form-guide-note">{whatsappUsesWebMode ? sozluk.integrations.whatsappWebGuideIntro : sozluk.integrations.whatsappGuideIntro}</p>
                  <ol className="setup-form-guide-list">
                    {(whatsappUsesWebMode ? whatsAppWebGuideSteps : whatsAppGuideSteps).map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                </div>
              </details>
            ) : (
              <div className="setup-form-guide-box">
                <strong>{whatsappUsesWebMode ? sozluk.integrations.whatsappWebGuideTitle : sozluk.integrations.whatsappGuideTitle}</strong>
                <p className="setup-form-guide-note">{whatsappUsesWebMode ? sozluk.integrations.whatsappWebGuideIntro : sozluk.integrations.whatsappGuideIntro}</p>
                <ol className="setup-form-guide-list">
                  {(whatsappUsesWebMode ? whatsAppWebGuideSteps : whatsAppGuideSteps).map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              </div>
            )}

            {whatsappUsesWebMode ? (
              <>
                <p className="setup-form-section__hint">{sozluk.integrations.whatsappWebHint}</p>
                {whatsAppWebAccountLabel ? <p className="setup-form-section__hint">{`${sozluk.integrations.whatsappWebLinkedAccount}: ${whatsAppWebAccountLabel}`}</p> : null}
                {whatsAppWebCurrentUser ? <p className="setup-form-section__hint">{`${sozluk.integrations.whatsappWebCurrentUser}: ${whatsAppWebCurrentUser}`}</p> : null}
                {whatsAppWebBrowserLabel ? <p className="setup-form-section__hint">{`${sozluk.integrations.whatsappWebBrowser}: ${whatsAppWebBrowserLabel}`}</p> : null}
                {whatsAppWebLastReadyAt ? <p className="setup-form-section__hint">{`${sozluk.integrations.whatsappWebReadyAt}: ${new Date(whatsAppWebLastReadyAt).toLocaleString("tr-TR")}`}</p> : null}
                {whatsAppWebLastSyncAt ? <p className="setup-form-section__hint">{`${sozluk.integrations.lastSyncLabel}: ${new Date(whatsAppWebLastSyncAt).toLocaleString("tr-TR")}`}</p> : null}
                {whatsAppWebMessageCountMirrored ? <p className="setup-form-section__hint">{`${sozluk.integrations.whatsappWebMirroredMessages}: ${whatsAppWebMessageCountMirrored}`}</p> : null}

                {whatsAppWebQrDataUrl ? (
                  <div className="setup-form-qr-card">
                    <img className="setup-form-qr-card__image" src={whatsAppWebQrDataUrl} alt={sozluk.integrations.whatsappWebQrAlt} />
                    <p className="setup-form-guide-note">{sozluk.integrations.whatsappWebQrHint}</p>
                  </div>
                ) : null}

                <div className="setup-form-actions">
                  {whatsAppWebReady ? (
                    <StatusBadge tone="accent">{sozluk.integrations.whatsappWebReadyAction}</StatusBadge>
                  ) : (
                    <button className="button" type="button" onClick={startWhatsAppWebLink} disabled={whatsAppBusy || whatsAppWebLinking}>
                      {whatsAppWebLinking ? sozluk.integrations.whatsappWebConnectingShort : (whatsAppWebNeedsQr ? sozluk.integrations.whatsappWebReconnectAction : sozluk.integrations.whatsappWebConnectAction)}
                    </button>
                  )}
                  {(whatsAppWebStatus !== "idle" || whatsAppWebAccountLabel) ? (
                    <button className="button button--secondary" type="button" onClick={disconnectWhatsApp} disabled={whatsAppBusy}>
                      {sozluk.integrations.disconnectAction}
                    </button>
                  ) : null}
                </div>
              </>
            ) : (
              <>
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
                  {(whatsAppMaskedToken || whatsAppAccessToken || whatsAppPhoneNumberId) ? (
                    <button className="button button--secondary" type="button" onClick={disconnectWhatsApp} disabled={whatsAppBusy}>
                      {sozluk.integrations.disconnectAction}
                    </button>
                  ) : null}
                </div>
              </>
            )}

            {whatsAppStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{whatsAppStatusMessage}</p> : null}
            {whatsAppError ? <p className="setup-form-feedback setup-form-feedback--error">{whatsAppError}</p> : null}
          </section>
          ) : null}

          {showSection("x") ? (
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

            {compactSettingsMode ? (
              <details className="setup-form-details">
                <summary className="setup-form-details__summary">{sozluk.integrations.showGuideDetails}</summary>
                <div className="setup-form-guide-box">
                  <strong>{sozluk.integrations.xGuideTitle}</strong>
                  <p className="setup-form-guide-note">{sozluk.integrations.xGuideIntro}</p>
                  <ol className="setup-form-guide-list">
                    <li>{sozluk.integrations.xGuideStep1}</li>
                    <li>{sozluk.integrations.xGuideStep2}</li>
                    <li>{sozluk.integrations.xGuideStep3}</li>
                    <li>{sozluk.integrations.xGuideStep4}</li>
                    <li>{sozluk.integrations.xGuideStep5}</li>
                  </ol>
                </div>
              </details>
            ) : (
              <div className="setup-form-guide-box">
                <strong>{sozluk.integrations.xGuideTitle}</strong>
                <p className="setup-form-guide-note">{sozluk.integrations.xGuideIntro}</p>
                <ol className="setup-form-guide-list">
                  <li>{sozluk.integrations.xGuideStep1}</li>
                  <li>{sozluk.integrations.xGuideStep2}</li>
                  <li>{sozluk.integrations.xGuideStep3}</li>
                  <li>{sozluk.integrations.xGuideStep4}</li>
                  <li>{sozluk.integrations.xGuideStep5}</li>
                </ol>
              </div>
            )}

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
              {xConfigured ? (
                <button className="button button--secondary" type="button" onClick={disconnectX} disabled={xBusy}>
                  {sozluk.integrations.disconnectAction}
                </button>
              ) : null}
            </div>

          {xStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{xStatusMessage}</p> : null}
          {xError ? <p className="setup-form-feedback setup-form-feedback--error">{xError}</p> : null}
          </section>
          ) : null}

          {showSection("instagram") ? (
          <section className="setup-form-section" id="integration-instagram" style={{ scrollMarginTop: "1rem" }}>
            <div className="setup-form-section__header">
              <div>
                <h3 className="setup-form-section__title">{sozluk.integrations.instagramTitle}</h3>
                <p className="setup-form-section__meta">{sozluk.integrations.instagramSubtitle}</p>
              </div>
              <div className="setup-form-section__badges">
                <StatusBadge tone={instagramConfigured ? "accent" : "warning"}>
                  {instagramConfigured ? sozluk.integrations.instagramConnected : sozluk.integrations.instagramNotConnected}
                </StatusBadge>
                {(instagramAccountLabel || instagramUsername) ? <StatusBadge>{instagramAccountLabel || instagramUsername}</StatusBadge> : null}
              </div>
            </div>

            <div className="setup-form-section__guide-row">
              <p className="setup-form-section__hint">{sozluk.integrations.instagramHint}</p>
              <a className="setup-form-guide-link" href={INTEGRATION_GUIDES.instagram} target="_blank" rel="noreferrer">
                {sozluk.integrations.instagramGuideConsoleAction}
              </a>
            </div>

            {compactSettingsMode ? (
              <details className="setup-form-details">
                <summary className="setup-form-details__summary">{sozluk.integrations.showGuideDetails}</summary>
                <div className="setup-form-guide-box">
                  <strong>{sozluk.integrations.instagramGuideTitle}</strong>
                  <p className="setup-form-guide-note">{sozluk.integrations.instagramGuideIntro}</p>
                  <ol className="setup-form-guide-list">
                    <li>{sozluk.integrations.instagramGuideStep1}</li>
                    <li>{sozluk.integrations.instagramGuideStep2}</li>
                    <li>{sozluk.integrations.instagramGuideStep3}</li>
                    <li>{sozluk.integrations.instagramGuideStep4}</li>
                    <li>{sozluk.integrations.instagramGuideStep5}</li>
                  </ol>
                  <p className="setup-form-guide-note">{sozluk.integrations.instagramLimitNote}</p>
                </div>
              </details>
            ) : (
              <div className="setup-form-guide-box">
                <strong>{sozluk.integrations.instagramGuideTitle}</strong>
                <p className="setup-form-guide-note">{sozluk.integrations.instagramGuideIntro}</p>
                <ol className="setup-form-guide-list">
                  <li>{sozluk.integrations.instagramGuideStep1}</li>
                  <li>{sozluk.integrations.instagramGuideStep2}</li>
                  <li>{sozluk.integrations.instagramGuideStep3}</li>
                  <li>{sozluk.integrations.instagramGuideStep4}</li>
                  <li>{sozluk.integrations.instagramGuideStep5}</li>
                </ol>
                <p className="setup-form-guide-note">{sozluk.integrations.instagramLimitNote}</p>
              </div>
            )}

            {!instagramClientReady ? (
              <div className="setup-form-subsection">
                <strong>{sozluk.integrations.instagramClientSetupTitle}</strong>
                <p>{sozluk.integrations.instagramClientSetupSubtitle}</p>
                <div className="setup-form-grid">
                  <label className="setup-form-field">
                    <span className="setup-form-field__label">{sozluk.integrations.instagramClientIdLabel}</span>
                    <input className="input" value={instagramClientId} onChange={(event) => setInstagramClientId(event.target.value)} />
                  </label>
                  <SecretField
                    label={sozluk.integrations.instagramClientSecretLabel}
                    value={instagramClientSecret}
                    onChange={setInstagramClientSecret}
                  />
                  <label className="setup-form-field">
                    <span className="setup-form-field__label">{sozluk.integrations.instagramPageNameHintLabel}</span>
                    <input className="input" value={instagramPageNameHint} onChange={(event) => setInstagramPageNameHint(event.target.value)} placeholder={sozluk.integrations.instagramPageNameHintPlaceholder} />
                  </label>
                </div>
                <div className="setup-form-actions">
                  <button className="button" type="button" onClick={saveInstagramClientSetup} disabled={instagramBusy}>
                    {sozluk.integrations.instagramClientSaveAction}
                  </button>
                </div>
              </div>
            ) : null}

            {instagramLastSyncAt ? <p className="setup-form-section__hint">{`${sozluk.integrations.lastSyncLabel}: ${new Date(instagramLastSyncAt).toLocaleString("tr-TR")}`}</p> : null}

            <div className="setup-form-actions">
              <button className="button" type="button" onClick={startInstagramAuthFlow} disabled={instagramBusy || !instagramClientReady}>
                {instagramConfigured ? sozluk.integrations.instagramReconnectAction : sozluk.integrations.instagramConnectAction}
              </button>
              {instagramConfigured ? (
                <button className="button button--secondary" type="button" onClick={disconnectInstagram} disabled={instagramBusy}>
                  {sozluk.integrations.disconnectAction}
                </button>
              ) : null}
            </div>

            <div className="setup-form-section__badges">
              <StatusBadge tone={instagramClientReady ? "accent" : "warning"}>
                {instagramClientReady ? sozluk.integrations.instagramClientReady : sozluk.integrations.instagramClientMissing}
              </StatusBadge>
              <StatusBadge tone={includesScope(instagramScopes, "instagram_manage_messages") ? "accent" : "warning"}>
                {sozluk.integrations.instagramMessagingReady}
              </StatusBadge>
              <StatusBadge tone="warning">{sozluk.integrations.instagramProfessionalOnly}</StatusBadge>
            </div>

            {instagramPageName || instagramUsername ? (
              <p className="setup-form-section__hint">
                {[instagramUsername ? `@${instagramUsername}` : "", instagramPageName || ""].filter(Boolean).join(" • ")}
              </p>
            ) : null}

            {instagramStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{instagramStatusMessage}</p> : null}
            {instagramError ? <p className="setup-form-feedback setup-form-feedback--error">{instagramError}</p> : null}
          </section>
          ) : null}

          {showSection("linkedin") ? (
          <section className="setup-form-section" id="integration-linkedin" style={{ scrollMarginTop: "1rem" }}>
            <div className="setup-form-section__header">
              <div>
                <h3 className="setup-form-section__title">{sozluk.integrations.linkedinTitle}</h3>
                <p className="setup-form-section__meta">{sozluk.integrations.linkedinSubtitle}</p>
              </div>
              <div className="setup-form-section__badges">
                <StatusBadge tone={linkedInConfigured ? "accent" : "warning"}>
                  {linkedInConfigured ? sozluk.integrations.linkedinConnected : sozluk.integrations.linkedinNotConnected}
                </StatusBadge>
                {linkedInAccountLabel ? <StatusBadge>{linkedInAccountLabel}</StatusBadge> : null}
              </div>
            </div>

            <div className="setup-form-section__guide-row">
              <p className="setup-form-section__hint">{sozluk.integrations.linkedinHint}</p>
              <a className="setup-form-guide-link" href={INTEGRATION_GUIDES.linkedin} target="_blank" rel="noreferrer">
                {sozluk.integrations.linkedinGuideConsoleAction}
              </a>
            </div>

            <div className="setup-form-grid">
              <label className="setup-form-field">
                <span className="setup-form-field__label">{sozluk.integrations.linkedinModeLabel}</span>
                <select className="select" value={linkedInMode} onChange={(event) => setLinkedInMode(event.target.value)}>
                  <option value="official">{sozluk.integrations.linkedinModeOfficial}</option>
                  <option value="web">{sozluk.integrations.linkedinModeWeb}</option>
                </select>
              </label>
              {linkedInUsesWebMode ? (
                <label className="setup-form-field">
                  <span className="setup-form-field__label">{sozluk.integrations.webSessionNameLabel}</span>
                  <input className="input" value={linkedInWebSessionName} onChange={(event) => setLinkedInWebSessionName(event.target.value)} />
                </label>
              ) : null}
            </div>

            {!linkedInUsesWebMode && compactSettingsMode ? (
              <details className="setup-form-details">
                <summary className="setup-form-details__summary">{sozluk.integrations.showGuideDetails}</summary>
                <div className="setup-form-guide-box">
                  <strong>{sozluk.integrations.linkedinGuideTitle}</strong>
                  <p className="setup-form-guide-note">{sozluk.integrations.linkedinGuideIntro}</p>
                  <ol className="setup-form-guide-list">
                    <li>{sozluk.integrations.linkedinGuideStep1}</li>
                    <li>{sozluk.integrations.linkedinGuideStep2}</li>
                    <li>{sozluk.integrations.linkedinGuideStep3}</li>
                    <li>{sozluk.integrations.linkedinGuideStep4}</li>
                  </ol>
                  <p className="setup-form-guide-note">{sozluk.integrations.linkedinLimitNote}</p>
                </div>
              </details>
            ) : !linkedInUsesWebMode ? (
              <div className="setup-form-guide-box">
                <strong>{sozluk.integrations.linkedinGuideTitle}</strong>
                <p className="setup-form-guide-note">{sozluk.integrations.linkedinGuideIntro}</p>
                <ol className="setup-form-guide-list">
                  <li>{sozluk.integrations.linkedinGuideStep1}</li>
                  <li>{sozluk.integrations.linkedinGuideStep2}</li>
                  <li>{sozluk.integrations.linkedinGuideStep3}</li>
                  <li>{sozluk.integrations.linkedinGuideStep4}</li>
                </ol>
                <p className="setup-form-guide-note">{sozluk.integrations.linkedinLimitNote}</p>
              </div>
            ) : (
              <div className="setup-form-guide-box">
                <strong>{sozluk.integrations.linkedinWebGuideTitle}</strong>
                <p className="setup-form-guide-note">{sozluk.integrations.linkedinWebGuideIntro}</p>
                <ol className="setup-form-guide-list">
                  <li>{sozluk.integrations.linkedinWebGuideStep1}</li>
                  <li>{sozluk.integrations.linkedinWebGuideStep2}</li>
                  <li>{sozluk.integrations.linkedinWebGuideStep3}</li>
                </ol>
                <p className="setup-form-guide-note">{sozluk.integrations.linkedinWebGuideLimitNote}</p>
              </div>
            )}

            {!linkedInUsesWebMode && !linkedInClientReady ? (
              <div className="setup-form-subsection">
                <strong>{sozluk.integrations.linkedinClientSetupTitle}</strong>
                <p>{sozluk.integrations.linkedinClientSetupSubtitle}</p>
                <div className="setup-form-grid">
                  <label className="setup-form-field">
                    <span className="setup-form-field__label">{sozluk.integrations.linkedinClientIdLabel}</span>
                    <input className="input" value={linkedInClientId} onChange={(event) => setLinkedInClientId(event.target.value)} />
                  </label>
                  <SecretField
                    label={sozluk.integrations.linkedinClientSecretLabel}
                    value={linkedInClientSecret}
                    onChange={setLinkedInClientSecret}
                  />
                </div>
                <div className="setup-form-actions">
                  <button className="button" type="button" onClick={saveLinkedInClientSetup} disabled={linkedInBusy}>
                    {sozluk.integrations.linkedinClientSaveAction}
                  </button>
                </div>
              </div>
            ) : null}

            {(linkedInUsesWebMode ? linkedInWebLastSyncAt : linkedInLastSyncAt) ? (
              <p className="setup-form-section__hint">
                {`${sozluk.integrations.lastSyncLabel}: ${new Date((linkedInUsesWebMode ? linkedInWebLastSyncAt : linkedInLastSyncAt) || "").toLocaleString("tr-TR")}`}
              </p>
            ) : null}
            {linkedInUsesWebMode && linkedInWebLastReadyAt ? (
              <p className="setup-form-section__hint">
                {`${sozluk.integrations.lastReadyLabel}: ${new Date(linkedInWebLastReadyAt).toLocaleString("tr-TR")}`}
              </p>
            ) : null}

            <div className="setup-form-actions">
              {linkedInUsesWebMode ? (
                <button className="button" type="button" onClick={startLinkedInWebFlow} disabled={linkedInBusy}>
                  {linkedInConfigured ? sozluk.integrations.linkedinWebReconnectAction : sozluk.integrations.linkedinWebConnectAction}
                </button>
              ) : (
                <button className="button" type="button" onClick={startLinkedInAuthFlow} disabled={linkedInBusy || !linkedInClientReady}>
                  {linkedInConfigured ? sozluk.integrations.linkedinReconnectAction : sozluk.integrations.linkedinConnectAction}
                </button>
              )}
              {linkedInConfigured ? (
                <button className="button button--secondary" type="button" onClick={disconnectLinkedIn} disabled={linkedInBusy}>
                  {sozluk.integrations.disconnectAction}
                </button>
              ) : null}
            </div>

            <div className="setup-form-section__badges">
              <StatusBadge>{linkedInUsesWebMode ? sozluk.integrations.linkedinModeWeb : sozluk.integrations.linkedinModeOfficial}</StatusBadge>
              {!linkedInUsesWebMode ? (
                <>
                  <StatusBadge tone={linkedInClientReady ? "accent" : "warning"}>
                    {linkedInClientReady ? sozluk.integrations.linkedinClientReady : sozluk.integrations.linkedinClientMissing}
                  </StatusBadge>
                  <StatusBadge tone={includesScope(linkedInScopes, "w_member_social") ? "accent" : "warning"}>
                    {sozluk.integrations.linkedinShareReady}
                  </StatusBadge>
                  <StatusBadge tone={includesScope(linkedInScopes, "r_member_social") ? "accent" : "warning"}>
                    {sozluk.integrations.linkedinCommentReady}
                  </StatusBadge>
                  <StatusBadge tone="warning">{sozluk.integrations.linkedinDmUnavailable}</StatusBadge>
                </>
              ) : (
                <>
                  {linkedInWebAccountLabel ? <StatusBadge tone="accent">{linkedInWebAccountLabel}</StatusBadge> : null}
                  <StatusBadge tone={linkedInConfigured ? "accent" : "warning"}>{sozluk.integrations.linkedinWebDmReady}</StatusBadge>
                </>
              )}
            </div>

            {linkedInStatusMessage ? <p className="setup-form-feedback setup-form-feedback--success">{linkedInStatusMessage}</p> : null}
            {linkedInError ? <p className="setup-form-feedback setup-form-feedback--error">{linkedInError}</p> : null}
          </section>
          ) : null}
        </>
        ) : null}
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
              onChange={(event) => handleProviderTypeChange(event.target.value)}
            >
              {PROVIDER_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label()}
                </option>
              ))}
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
                  onChange={(event) => handleProviderModelChange(event.target.value)}
                  disabled={!suggestedProviderModels.length}
                >
                  {suggestedProviderModels.length ? (
                    suggestedProviderModels.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))
                  ) : (
                    <option value={providerModel || currentProviderPreset.defaultModel}>{providerModel || currentProviderPreset.defaultModel}</option>
                  )}
                </select>
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
                  <button className="button" type="button" onClick={saveProvider} disabled={codexBusy}>
                    {codexConfigured ? sozluk.integrations.providerReconnectAction : sozluk.integrations.providerConnectAction}
                  </button>
                  {providerHasConfiguredConnection ? (
                    <button className="button button--secondary" type="button" onClick={disconnectProvider} disabled={providerActionBusy}>
                      {sozluk.integrations.providerDisconnectAction}
                    </button>
                  ) : null}
                </div>
              </div>

              {codexAuthUrl ? (
                <label className="stack stack--tight">
                  <span>{sozluk.integrations.codexAuthUrlLabel}</span>
                  <input className="input" readOnly value={codexAuthUrl} />
                </label>
              ) : null}

              {suggestedProviderModels.length ? (
                <div className="stack stack--tight">
                  <strong>{sozluk.integrations.codexAvailableModelsTitle}</strong>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    {suggestedProviderModels.map((item) => (
                      <StatusBadge key={item}>{item}</StatusBadge>
                    ))}
                  </div>
                </div>
              ) : null}

              <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.codexManualOpenNote}</p>
              {providerHasConfiguredConnection ? (
                <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.providerConnectedNote}</p>
              ) : savedProviderType && savedProviderType !== providerType ? (
                <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.providerSwitchedNote}</p>
              ) : null}
              {showCodexCallback && showCodexManualFallback ? (
                <div className="stack stack--tight">
                  <strong>{sozluk.integrations.codexManualFallbackTitle}</strong>
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
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <button className="button button--secondary" type="button" onClick={submitCodexCallback} disabled={codexBusy || !codexCallbackUrl.trim()}>
                      {sozluk.integrations.codexSubmitCallback}
                    </button>
                  </div>
                </div>
              ) : null}
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
                  <select className="select" value={providerModel} onChange={(event) => handleProviderModelChange(event.target.value)}>
                    {suggestedProviderModels.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input className="input" value={providerModel} onChange={(event) => handleProviderModelChange(event.target.value)} />
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
                    placeholder={providerSecretPlaceholder(providerMaskedKey)}
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
                  <button className="button" type="button" onClick={saveProvider} disabled={providerActionBusy}>
                    {providerHasConfiguredConnection ? sozluk.integrations.providerUpdateAction : sozluk.integrations.providerConnectAction}
                  </button>
                  {providerHasConfiguredConnection ? (
                    <button className="button button--secondary" type="button" onClick={disconnectProvider} disabled={providerActionBusy}>
                      {sozluk.integrations.providerDisconnectAction}
                    </button>
                  ) : null}
                </div>
              </div>
              <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.providerBrowserAuthNote}</p>
              {providerHasConfiguredConnection ? (
                <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.providerConnectedNote}</p>
              ) : savedProviderType && savedProviderType !== providerType ? (
                <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.providerSwitchedNote}</p>
              ) : null}
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
          {!googleClientReady ? (
            <>
              <label className="stack stack--tight">
                <span>{sozluk.integrations.googleClientIdLabel}</span>
                <input className="input" value={googleClientId} onChange={(event) => setGoogleClientId(event.target.value)} />
              </label>
              <label className="stack stack--tight">
                <span>{sozluk.integrations.googleClientSecretLabel}</span>
                <input className="input" type="password" value={googleClientSecret} onChange={(event) => setGoogleClientSecret(event.target.value)} />
              </label>
            </>
          ) : null}
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
              <StatusBadge tone={googleHasYouTube ? "accent" : "warning"}>YouTube</StatusBadge>
              {googleBrowserTarget ? <StatusBadge>{`${sozluk.integrations.codexBrowserOpened}: ${googleBrowserTarget}`}</StatusBadge> : null}
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button
                className="button"
                type="button"
                onClick={connectGoogleAccount}
                disabled={googleBusy || (!googleClientReady && (!googleClientId.trim() || !googleClientSecret.trim()))}
              >
                {googleConfigured ? sozluk.integrations.googleReconnectAction : sozluk.integrations.googleConnectAction}
              </button>
              {googleConfigured ? (
                <button className="button button--secondary" type="button" onClick={disconnectGoogle} disabled={googleBusy}>
                  {sozluk.integrations.disconnectAction}
                </button>
              ) : null}
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
          <div className="stack stack--tight">
            <strong>{sozluk.integrations.googleHistoryTitle}</strong>
            <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.googleHistorySubtitle}</p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <StatusBadge tone={googleHistoryConnected ? "accent" : "warning"}>{googleHistoryStatusLabel}</StatusBadge>
              {googlePortabilityAccountLabel ? <StatusBadge>{googlePortabilityAccountLabel}</StatusBadge> : null}
              <StatusBadge tone={googleYouTubeHistoryCount > 0 ? "accent" : "warning"}>
                {`${sozluk.integrations.googleHistoryYoutubeLabel}: ${googleYouTubeHistoryCount}`}
              </StatusBadge>
              <StatusBadge tone={googleChromeHistoryCount > 0 ? "accent" : "warning"}>
                {`${sozluk.integrations.googleHistoryChromeLabel}: ${googleChromeHistoryCount}`}
              </StatusBadge>
            </div>
            <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.googleHistoryGuideNote}</p>
            <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.googleHistoryTakeoutNote}</p>
            <div className="setup-form-guide-box">
              <strong>{sozluk.integrations.googleHistoryTakeoutGuideTitle}</strong>
              <ol className="setup-form-guide-list">
                <li>{sozluk.integrations.googleHistoryTakeoutStep1}</li>
                <li>{sozluk.integrations.googleHistoryTakeoutStep2}</li>
                <li>{sozluk.integrations.googleHistoryTakeoutStep3}</li>
              </ol>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <a className="button button--secondary" href={INTEGRATION_GUIDES.googleTakeout} target="_blank" rel="noreferrer">
                {sozluk.integrations.googleHistoryTakeoutOpenAction}
              </a>
              <button className="button button--secondary" type="button" onClick={importGoogleHistoryArchive} disabled={googlePortabilityBusy}>
                {sozluk.integrations.googleHistoryTakeoutAction}
              </button>
            </div>
            {preferGoogleTakeoutImport ? (
              <details className="setup-form-details">
                <summary className="setup-form-details__summary">{sozluk.integrations.googleHistoryAdvancedAction}</summary>
                <div className="setup-form-subsection">
                  <p>{sozluk.integrations.googleHistoryPortabilityCountryNotice}</p>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <button className="button button--secondary" type="button" onClick={connectGooglePortability} disabled={googlePortabilityBusy || (!googlePortabilityClientReady && (!googleClientId.trim() || !googleClientSecret.trim()))}>
                      {googleHistoryConnected ? sozluk.integrations.googleHistoryReconnectAction : sozluk.integrations.googleHistoryConnectAction}
                    </button>
                    <button className="button button--secondary" type="button" onClick={syncGooglePortabilityHistory} disabled={googlePortabilityBusy || !googlePortabilityConfigured}>
                      {sozluk.integrations.googleHistorySyncAction}
                    </button>
                    {googlePortabilityAuthUrl && !googlePortabilityConfigured ? (
                      <button className="button button--ghost" type="button" onClick={cancelGooglePortabilityAuthFlow} disabled={googlePortabilityBusy}>
                        {sozluk.integrations.googleHistoryCancelAction}
                      </button>
                    ) : null}
                  </div>
                </div>
              </details>
            ) : (
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button className="button button--secondary" type="button" onClick={connectGooglePortability} disabled={googlePortabilityBusy || (!googlePortabilityClientReady && (!googleClientId.trim() || !googleClientSecret.trim()))}>
                  {googleHistoryConnected ? sozluk.integrations.googleHistoryReconnectAction : sozluk.integrations.googleHistoryConnectAction}
                </button>
                <button className="button button--secondary" type="button" onClick={syncGooglePortabilityHistory} disabled={googlePortabilityBusy || !googlePortabilityConfigured}>
                  {sozluk.integrations.googleHistorySyncAction}
                </button>
                {googlePortabilityAuthUrl && !googlePortabilityConfigured ? (
                  <button className="button button--ghost" type="button" onClick={cancelGooglePortabilityAuthFlow} disabled={googlePortabilityBusy}>
                    {sozluk.integrations.googleHistoryCancelAction}
                  </button>
                ) : null}
              </div>
            )}
            {googlePortabilityAuthUrl && !googlePortabilityConfigured ? (
              <label className="stack stack--tight">
                <span>{sozluk.integrations.googleAuthUrlLabel}</span>
                <input className="input" readOnly value={googlePortabilityAuthUrl} />
              </label>
            ) : null}
            {googlePortabilityLastSyncAt ? (
              <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{`Son eşitleme: ${new Date(googlePortabilityLastSyncAt).toLocaleString("tr-TR")}`}</p>
            ) : null}
            {googlePortabilityStatusMessage ? <p style={{ color: "var(--accent)", marginBottom: 0 }}>{googlePortabilityStatusMessage}</p> : null}
            {googlePortabilityError ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{googlePortabilityError}</p> : null}
          </div>
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
            <span>{sozluk.integrations.telegramModeLabel}</span>
            <select className="select" value={telegramMode} onChange={(event) => setTelegramMode(event.target.value)}>
              <option value="bot">{sozluk.integrations.telegramModeBot}</option>
              <option value="web">{sozluk.integrations.telegramModeWeb}</option>
            </select>
          </label>
          {telegramUsesWebMode ? (
            <label className="stack stack--tight">
              <span>{sozluk.integrations.webSessionNameLabel}</span>
              <input className="input" value={telegramWebSessionName} onChange={(event) => setTelegramWebSessionName(event.target.value)} />
            </label>
          ) : (
            <>
              <label className="stack stack--tight">
                <span>{sozluk.integrations.telegramBotNameLabel}</span>
                <input className="input" value={telegramBotUsername} onChange={(event) => setTelegramBotUsername(event.target.value)} />
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
            </>
          )}
          <div className="toolbar">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <StatusBadge tone={telegramEnabled ? "accent" : "warning"}>
                {telegramEnabled ? sozluk.integrations.telegramEnabled : sozluk.integrations.telegramDisabled}
              </StatusBadge>
              <StatusBadge>{telegramUsesWebMode ? sozluk.integrations.telegramModeWeb : sozluk.integrations.telegramModeBot}</StatusBadge>
              <StatusBadge tone={validationTone(telegramStatusValue)}>
                {telegramStatusValue === "valid" ? sozluk.integrations.validated : sozluk.integrations.notValidated}
              </StatusBadge>
              {!telegramUsesWebMode && telegramMaskedToken ? <StatusBadge>{telegramMaskedToken}</StatusBadge> : null}
              {telegramUsesWebMode && telegramWebAccountLabel ? <StatusBadge>{telegramWebAccountLabel}</StatusBadge> : null}
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button className="button" type="button" onClick={saveTelegram}>
                {sozluk.integrations.saveTelegram}
              </button>
              {telegramUsesWebMode ? (
                <button className="button button--secondary" type="button" onClick={startTelegramWebFlow} disabled={telegramBusy || !telegramEnabled}>
                  {telegramBusy ? sozluk.integrations.validating : sozluk.integrations.telegramWebConnectAction}
                </button>
              ) : (
                <button className="button button--secondary" type="button" onClick={validateTelegram} disabled={telegramBusy}>
                  {telegramBusy ? sozluk.integrations.validating : sozluk.integrations.validateTelegram}
                </button>
              )}
            </div>
          </div>
          <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>
            {telegramUsesWebMode ? sozluk.integrations.telegramWebNote : sozluk.integrations.telegramNote}
          </p>
          {telegramUsesWebMode && telegramWebLastReadyAt ? (
            <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>
              {`${sozluk.integrations.lastReadyLabel}: ${new Date(telegramWebLastReadyAt).toLocaleString("tr-TR")}`}
            </p>
          ) : null}
          {telegramUsesWebMode && telegramWebLastSyncAt ? (
            <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>
              {`${sozluk.integrations.lastSyncLabel}: ${new Date(telegramWebLastSyncAt).toLocaleString("tr-TR")}`}
            </p>
          ) : null}
          {telegramStatusMessage ? <p style={{ color: "var(--accent)", marginBottom: 0 }}>{telegramStatusMessage}</p> : null}
          {telegramError ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{telegramError}</p> : null}
        </div>
      </SectionCard>
      </div>
    </div>
  );
}
