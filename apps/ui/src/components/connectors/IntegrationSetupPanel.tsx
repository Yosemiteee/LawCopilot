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
    baseUrl?: string;
    model?: string;
    validationStatus?: string;
    configuredAt?: string;
    lastValidatedAt?: string;
    apiKeyConfigured?: boolean;
    apiKeyMasked?: string;
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

function providerLabel(value: string) {
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

  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramBotToken, setTelegramBotToken] = useState("");
  const [telegramAllowedUserId, setTelegramAllowedUserId] = useState("");
  const [telegramBotUsername, setTelegramBotUsername] = useState("");
  const [telegramMaskedToken, setTelegramMaskedToken] = useState("");
  const [telegramStatusValue, setTelegramStatusValue] = useState("pending");
  const [telegramStatusMessage, setTelegramStatusMessage] = useState("");
  const [telegramBusy, setTelegramBusy] = useState(false);
  const [telegramError, setTelegramError] = useState("");

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
      const telegram = config.telegram || {};
      setProviderType(String(provider.type || "openai"));
      setProviderBaseUrl(String(provider.baseUrl || "https://api.openai.com/v1"));
      setProviderModel(String(provider.model || "gpt-4.1-mini"));
      setProviderMaskedKey(String(provider.apiKeyMasked || ""));
      setProviderStatusValue(String(provider.validationStatus || "pending"));
      setTelegramEnabled(Boolean(telegram.enabled));
      setTelegramAllowedUserId(String(telegram.allowedUserId || ""));
      setTelegramBotUsername(String(telegram.botUsername || ""));
      setTelegramMaskedToken(String(telegram.botTokenMasked || ""));
      setTelegramStatusValue(String(telegram.validationStatus || "pending"));
      setDesktopReady(true);
    }
    void loadConfig();
    return () => {
      active = false;
    };
  }, []);

  const providerNeedsKey = providerType !== "ollama";
  const providerSubtitle = useMemo(() => {
    if (mode === "onboarding") {
      return sozluk.integrations.providerOnboardingSubtitle;
    }
    return sozluk.integrations.providerSubtitle;
  }, [mode]);

  async function validateProvider() {
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
    if (!window.lawcopilotDesktop?.saveIntegrationConfig) {
      setProviderError(sozluk.integrations.desktopOnly);
      return;
    }
    try {
      const saved = (await window.lawcopilotDesktop.saveIntegrationConfig({
        provider: {
          type: providerType,
          baseUrl: providerBaseUrl,
          model: providerModel,
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
                if (value === "ollama") {
                  setProviderBaseUrl("http://127.0.0.1:11434");
                } else if (!providerBaseUrl) {
                  setProviderBaseUrl("https://api.openai.com/v1");
                }
              }}
            >
              <option value="openai">{sozluk.integrations.providerTypeOpenAI}</option>
              <option value="openai-compatible">{sozluk.integrations.providerTypeCompatible}</option>
              <option value="ollama">{sozluk.integrations.providerTypeOllama}</option>
            </select>
          </label>
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
          {providerStatusMessage ? <p style={{ color: "var(--accent)", marginBottom: 0 }}>{providerStatusMessage}</p> : null}
          {providerError ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{providerError}</p> : null}
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
