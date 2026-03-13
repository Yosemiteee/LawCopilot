import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";
import { sozluk } from "../../i18n";

type PanelMode = "onboarding" | "settings" | "connectors";

type IntegrationSetupPanelProps = {
  mode?: PanelMode;
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

function providerLabel(value: string) {
  if (value === "openai-codex") {
    return sozluk.integrations.providerTypeCodex;
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

export function IntegrationSetupPanel({ mode = "connectors" }: IntegrationSetupPanelProps) {
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
      const google = config.google || {};
      const telegram = config.telegram || {};
      setProviderType(String(provider.type || "openai"));
      setProviderBaseUrl(String(provider.baseUrl || "https://api.openai.com/v1"));
      setProviderModel(String(provider.model || "gpt-4.1-mini"));
      setProviderMaskedKey(String(provider.apiKeyMasked || ""));
      setProviderStatusValue(String(provider.validationStatus || "pending"));
      setProviderStatusMessage("");
      setProviderAvailableModels(Array.isArray(provider.availableModels) ? provider.availableModels || [] : []);
      setCodexConfigured(Boolean(provider.oauthConnected));
      setGoogleEnabled(Boolean(google.enabled));
      setGoogleConfigured(Boolean(google.oauthConnected));
      setGoogleClientReady(Boolean(google.clientIdConfigured));
      setGoogleAccountLabel(String(google.accountLabel || ""));
      setGoogleScopes(Array.isArray(google.scopes) ? google.scopes : []);
      setGoogleStatusValue(String(google.validationStatus || "pending"));
      setTelegramEnabled(Boolean(telegram.enabled));
      setTelegramAllowedUserId(String(telegram.allowedUserId || ""));
      setTelegramBotUsername(String(telegram.botUsername || ""));
      setTelegramMaskedToken(String(telegram.botTokenMasked || ""));
      setTelegramStatusValue(String(telegram.validationStatus || "pending"));
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
    }
    void loadConfig();
    return () => {
      active = false;
    };
  }, []);

  const providerNeedsKey = providerType !== "ollama" && providerType !== "openai-codex";
  const providerUsesBrowserAuth = providerType === "openai-codex";
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

  async function startGoogleAuthFlow() {
    if (!window.lawcopilotDesktop?.startGoogleAuth) {
      setGoogleError(sozluk.integrations.desktopOnly);
      return;
    }
    setGoogleBusy(true);
    try {
      const status = (await window.lawcopilotDesktop.startGoogleAuth()) as GoogleAuthStatus;
      applyGoogleStatus(status, sozluk.integrations.googleAuthPending);
      setGoogleEnabled(true);
    } catch (error) {
      setGoogleStatusValue("invalid");
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
    } catch (error) {
      setTelegramError(error instanceof Error ? error.message : sozluk.integrations.telegramSaveError);
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

  return (
    <div className="stack">
      <SectionCard title={sozluk.integrations.providerTitle} subtitle={providerSubtitle}>
        <div className="field-grid">
          <label className="stack stack--tight">
            <span>{sozluk.integrations.providerTypeLabel}</span>
            <select
              className="select"
              value={providerType}
              onChange={(event) => {
                const value = event.target.value;
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
                if (value === "ollama") {
                  setProviderBaseUrl("http://127.0.0.1:11434");
                  setProviderModel("llama3.1");
                } else {
                  setProviderBaseUrl("https://api.openai.com/v1");
                  setProviderModel("gpt-4.1-mini");
                }
              }}
            >
              <option value="openai">{sozluk.integrations.providerTypeOpenAI}</option>
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
                <input className="input" value={providerModel} onChange={(event) => setProviderModel(event.target.value)} />
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
              {providerAvailableModels.length ? (
                <div className="stack stack--tight">
                  <strong>{sozluk.integrations.availableModelsTitle}</strong>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    {providerAvailableModels.map((item) => (
                      <StatusBadge key={item}>{item}</StatusBadge>
                    ))}
                  </div>
                </div>
              ) : null}
            </>
          )}
          {providerStatusMessage ? <p style={{ color: "var(--accent)", marginBottom: 0 }}>{providerStatusMessage}</p> : null}
          {providerError ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{providerError}</p> : null}
        </div>
      </SectionCard>

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
                  <StatusBadge key={scope}>{scope}</StatusBadge>
                ))}
              </div>
            </div>
          ) : null}
          <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.integrations.googleNote}</p>
          {googleStatusMessage ? <p style={{ color: "var(--accent)", marginBottom: 0 }}>{googleStatusMessage}</p> : null}
          {googleError ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{googleError}</p> : null}
        </div>
      </SectionCard>

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
  );
}
