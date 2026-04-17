import { useEffect, useMemo, useState } from "react";

import { useAppContext } from "../../app/AppContext";
import { StatusBadge } from "../common/StatusBadge";
import { normalizeUiErrorMessage } from "../../lib/errors";
import {
  disconnectIntegrationConnection,
  getIntegrationCatalog,
  saveIntegrationConnection,
  syncIntegrationConnection,
  validateIntegrationConnection,
} from "../../services/lawcopilotApi";
import type { IntegrationCatalogItem, IntegrationConnection } from "../../types/domain";

const ELASTIC_GUIDE_CLOUD_ID = "https://www.elastic.co/docs/deploy-manage/deploy/elastic-cloud/find-cloud-id";
const ELASTIC_GUIDE_API_KEYS = "https://www.elastic.co/docs/deploy-manage/api-keys";

type ElasticSetupPanelProps = {
  onUpdated?: () => void;
};

function trimOrEmpty(value: string) {
  return String(value || "").trim();
}

function cleanRecord(value: Record<string, unknown>) {
  const entries = Object.entries(value).filter(([, item]) => {
    if (item === null || item === undefined) {
      return false;
    }
    if (typeof item === "string") {
      return item.trim().length > 0;
    }
    return true;
  });
  return Object.fromEntries(entries);
}

function validationTone(status: string) {
  switch (String(status || "").toLowerCase()) {
    case "valid":
    case "connected":
    case "ok":
      return "accent" as const;
    case "invalid":
    case "error":
      return "danger" as const;
    default:
      return "warning" as const;
  }
}

function validationLabel(status: string) {
  switch (String(status || "").toLowerCase()) {
    case "valid":
    case "connected":
    case "ok":
      return "Bağlı";
    case "invalid":
    case "error":
      return "Hatalı";
    case "pending":
      return "Hazır değil";
    default:
      return "Bekliyor";
  }
}

function firstElasticConnection(item?: IntegrationCatalogItem | null) {
  return item?.connections?.[0] || null;
}

function applyConnectionConfig(connection: IntegrationConnection | null) {
  const config = (connection?.config || {}) as Record<string, unknown>;
  return {
    clusterLabel: trimOrEmpty(String(config.cluster_label || connection?.display_name || "")),
    baseUrl: trimOrEmpty(String(config.base_url || "")),
    cloudId: trimOrEmpty(String(config.cloud_id || "")),
    indexPattern: trimOrEmpty(String(config.index_pattern || "cases-*")) || "cases-*",
    searchFields: trimOrEmpty(String(config.search_fields || "")),
    resultSize: String(config.result_size || 10),
    apiKeyId: trimOrEmpty(String(config.api_key_id || "")),
    username: trimOrEmpty(String(config.username || "")),
  };
}

export function ElasticSetupPanel({ onUpdated }: ElasticSetupPanelProps) {
  const { settings } = useAppContext();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [connectorItem, setConnectorItem] = useState<IntegrationCatalogItem | null>(null);
  const [connection, setConnection] = useState<IntegrationConnection | null>(null);
  const [clusterLabel, setClusterLabel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [cloudId, setCloudId] = useState("");
  const [indexPattern, setIndexPattern] = useState("cases-*");
  const [searchFields, setSearchFields] = useState("");
  const [resultSize, setResultSize] = useState("10");
  const [apiKey, setApiKey] = useState("");
  const [apiKeyId, setApiKeyId] = useState("");
  const [apiKeySecret, setApiKeySecret] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadElasticState() {
    setLoading(true);
    try {
      const catalog = await getIntegrationCatalog(settings);
      const item = catalog.items.find((entry) => entry.connector.id === "elastic") || null;
      const nextConnection = firstElasticConnection(item);
      setConnectorItem(item);
      setConnection(nextConnection);
      const config = applyConnectionConfig(nextConnection);
      setClusterLabel(config.clusterLabel);
      setBaseUrl(config.baseUrl);
      setCloudId(config.cloudId);
      setIndexPattern(config.indexPattern);
      setSearchFields(config.searchFields);
      setResultSize(config.resultSize);
      setApiKeyId(config.apiKeyId);
      setUsername(config.username);
      setMessage(nextConnection?.health_message || "");
      setError("");
    } catch (err) {
      setError(normalizeUiErrorMessage(err, "Elastic bilgileri yüklenemedi."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadElasticState();
  }, [settings.baseUrl, settings.token]);

  const connectorScopes = useMemo(() => connectorItem?.connector.scopes || [], [connectorItem]);
  const isConfigured = Boolean(connection);
  const canSave = Boolean(trimOrEmpty(clusterLabel) && (trimOrEmpty(baseUrl) || trimOrEmpty(cloudId)));

  function buildPayload() {
    const numericResultSize = Number(resultSize);
    const config = cleanRecord({
      cluster_label: clusterLabel || "Elastic",
      base_url: baseUrl,
      cloud_id: cloudId,
      index_pattern: indexPattern || "cases-*",
      search_fields: searchFields,
      result_size: Number.isFinite(numericResultSize) && numericResultSize > 0 ? Math.max(1, Math.min(100, Math.round(numericResultSize))) : 10,
      api_key_id: apiKeyId,
      username,
    });
    const secrets = cleanRecord({
      api_key: apiKey,
      api_key_secret: apiKeySecret,
      password,
    });
    return {
      connector_id: "elastic",
      connection_id: connection?.id,
      display_name: trimOrEmpty(clusterLabel) || "Elastic",
      access_level: "read_only" as const,
      enabled: true,
      mock_mode: false,
      scopes: connectorScopes,
      config,
      secrets,
    };
  }

  async function handleSaveAndValidate() {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const saved = await saveIntegrationConnection(settings, buildPayload());
      const validated = await validateIntegrationConnection(settings, saved.connection.id);
      setConnection(validated.connection);
      setMessage(validated.validation.message || saved.message || "Elastic bağlantısı kaydedildi.");
      onUpdated?.();
      await loadElasticState();
    } catch (err) {
      setError(normalizeUiErrorMessage(err, "Elastic bağlantısı kaydedilemedi."));
    } finally {
      setSaving(false);
    }
  }

  async function handleSync() {
    if (!connection) {
      return;
    }
    setSyncing(true);
    setMessage("");
    setError("");
    try {
      const response = await syncIntegrationConnection(settings, connection.id);
      setConnection(response.connection);
      setMessage(response.message || "Elastic senkronu başlatıldı.");
      onUpdated?.();
      await loadElasticState();
    } catch (err) {
      setError(normalizeUiErrorMessage(err, "Elastic senkronu başlatılamadı."));
    } finally {
      setSyncing(false);
    }
  }

  async function handleDisconnect() {
    if (!connection) {
      return;
    }
    setDisconnecting(true);
    setMessage("");
    setError("");
    try {
      await disconnectIntegrationConnection(settings, connection.id);
      setConnection(null);
      setMessage("Elastic bağlantısı kaldırıldı.");
      setApiKey("");
      setApiKeySecret("");
      setPassword("");
      onUpdated?.();
      await loadElasticState();
    } catch (err) {
      setError(normalizeUiErrorMessage(err, "Elastic bağlantısı kaldırılamadı."));
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <section className="setup-form-section" id="integration-elastic" style={{ scrollMarginTop: "1rem" }}>
      <div className="setup-form-section__header">
        <div>
          <h3 className="setup-form-section__title">Elastic</h3>
          <p className="setup-form-section__meta">Elastic Cloud veya self-hosted Elasticsearch cluster bağlayın.</p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <StatusBadge tone={validationTone(connection?.health_status || connection?.status || "pending")}>
            {validationLabel(connection?.health_status || connection?.status || "pending")}
          </StatusBadge>
          {connection?.display_name ? <StatusBadge>{connection.display_name}</StatusBadge> : null}
          {connection?.last_sync_at ? <StatusBadge>{`Son senkron: ${new Date(connection.last_sync_at).toLocaleString("tr-TR")}`}</StatusBadge> : null}
        </div>
      </div>

      <p className="setup-form-section__hint">
        En kolay kurulum: Elastic Cloud kullanıyorsanız <strong>Cloud ID</strong> ve yalnız gerekli indekslere read izni olan bir <strong>API key</strong> girin.
        Self-hosted kurulumda <strong>Temel URL</strong> ile API key veya kullanıcı/parola kullanabilirsiniz.
      </p>

      <div className="callout">
        <strong>Kurulum bilgisi</strong>
        <ol className="setup-form-guide-list">
          <li>Elastic Cloud kullanıyorsanız deployment sayfasından Cloud ID’yi kopyalayın. Self-hosted kullanıyorsanız Elasticsearch HTTPS adresini alın.</li>
          <li>Tercihen yalnız gerekli indekslere read izni veren bir API key oluşturun.</li>
          <li>Cluster etiketi, Cloud ID veya Temel URL ve indeks desenini girin.</li>
          <li>API key ya da kullanıcı/parola ile kaydedin. Sonra doğrulama ve ilk senkronu başlatın.</li>
        </ol>
        <div className="toolbar">
          <a className="button button--secondary" href={ELASTIC_GUIDE_CLOUD_ID} target="_blank" rel="noreferrer">
            Cloud ID nasıl bulunur
          </a>
          <a className="button button--secondary" href={ELASTIC_GUIDE_API_KEYS} target="_blank" rel="noreferrer">
            API key rehberi
          </a>
        </div>
      </div>

      {loading ? (
        <p className="setup-form-section__hint">Elastic bağlantı durumu yükleniyor...</p>
      ) : (
        <>
          <div className="setup-form-grid">
            <label className="setup-form-field">
              <span className="setup-form-field__label">Cluster etiketi</span>
              <input className="input" value={clusterLabel} onChange={(event) => setClusterLabel(event.target.value)} placeholder="Üretim Elastic" />
            </label>
            <label className="setup-form-field">
              <span className="setup-form-field__label">İndeks deseni</span>
              <input className="input" value={indexPattern} onChange={(event) => setIndexPattern(event.target.value)} placeholder="cases-*" />
            </label>
            <label className="setup-form-field">
              <span className="setup-form-field__label">Elastic Cloud ID</span>
              <input className="input" value={cloudId} onChange={(event) => setCloudId(event.target.value)} placeholder="my-deployment:dXMtZWFzdC0x..." />
            </label>
            <label className="setup-form-field">
              <span className="setup-form-field__label">Temel URL</span>
              <input className="input" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://cluster.example.com:9200" />
            </label>
            <label className="setup-form-field">
              <span className="setup-form-field__label">Aranacak alanlar</span>
              <input className="input" value={searchFields} onChange={(event) => setSearchFields(event.target.value)} placeholder="title^3, summary^2, body" />
            </label>
            <label className="setup-form-field">
              <span className="setup-form-field__label">Varsayılan sonuç sayısı</span>
              <input className="input" type="number" min={1} max={100} value={resultSize} onChange={(event) => setResultSize(event.target.value)} />
            </label>
            <label className="setup-form-field">
              <span className="setup-form-field__label">API key</span>
              <input className="input" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="Encoded API key" />
            </label>
          </div>

          <details className="setup-form-section__details">
            <summary>Gelişmiş bağlantı seçenekleri</summary>
            <div className="setup-form-grid" style={{ marginTop: "0.9rem" }}>
              <label className="setup-form-field">
                <span className="setup-form-field__label">API key ID</span>
                <input className="input" value={apiKeyId} onChange={(event) => setApiKeyId(event.target.value)} />
              </label>
              <label className="setup-form-field">
                <span className="setup-form-field__label">API key secret</span>
                <input className="input" type="password" value={apiKeySecret} onChange={(event) => setApiKeySecret(event.target.value)} />
              </label>
              <label className="setup-form-field">
                <span className="setup-form-field__label">Kullanıcı adı</span>
                <input className="input" value={username} onChange={(event) => setUsername(event.target.value)} />
              </label>
              <label className="setup-form-field">
                <span className="setup-form-field__label">Parola</span>
                <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
              </label>
            </div>
          </details>

          <div className="toolbar">
            <button className="button" type="button" onClick={handleSaveAndValidate} disabled={saving || !canSave}>
              {saving ? "Elastic kaydediliyor..." : isConfigured ? "Elastic bağlantısını güncelle" : "Elastic bağlantısını kaydet"}
            </button>
            {connection ? (
              <button className="button button--secondary" type="button" onClick={handleSync} disabled={syncing}>
                {syncing ? "Elastic senkronu çalışıyor..." : "İlk senkronu çalıştır"}
              </button>
            ) : null}
            {connection ? (
              <button className="button button--secondary" type="button" onClick={handleDisconnect} disabled={disconnecting}>
                {disconnecting ? "Kaldırılıyor..." : "Bağlantıyı kaldır"}
              </button>
            ) : null}
          </div>

          {message ? <p className="setup-form-feedback setup-form-feedback--success">{message}</p> : null}
          {error ? <p className="setup-form-feedback setup-form-feedback--error">{error}</p> : null}
        </>
      )}
    </section>
  );
}
