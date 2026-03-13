import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSpinner } from "../components/common/LoadingSpinner";
import { MetricCard } from "../components/common/MetricCard";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import {
  ajandaTipiEtiketi,
  asistanAksiyonDurumuEtiketi,
  asistanAksiyonTipiEtiketi,
  dagitimKipiEtiketi,
  disIletisimDurumuEtiketi,
  kanalEtiketi,
  modelProfilEtiketi,
} from "../lib/labels";
import {
  approveAssistantAction,
  dismissAssistantAction,
  generateAssistantAction,
  getAssistantAgenda,
  getAssistantInbox,
  getAssistantSuggestedActions,
  getGoogleIntegrationStatus,
  getHealth,
  getModelProfiles,
  getTelegramIntegrationStatus,
  getTelemetryHealth,
  listAssistantDrafts,
  sendAssistantDraft,
} from "../services/lawcopilotApi";
import type {
  AssistantAgendaItem,
  GoogleIntegrationStatus,
  ModelProfilesResponse,
  OutboundDraft,
  SuggestedAction,
  TelegramIntegrationStatus,
  TelemetryHealth,
} from "../types/domain";

function dateLabel(value?: string | null) {
  if (!value) return "Zaman bilgisi yok";
  return new Date(value).toLocaleString("tr-TR");
}

export function DashboardPage() {
  const { settings } = useAppContext();
  const [healthMode, setHealthMode] = useState<string>(settings.deploymentMode);
  const [profiles, setProfiles] = useState<ModelProfilesResponse | null>(null);
  const [agenda, setAgenda] = useState<AssistantAgendaItem[]>([]);
  const [inbox, setInbox] = useState<AssistantAgendaItem[]>([]);
  const [actions, setActions] = useState<SuggestedAction[]>([]);
  const [drafts, setDrafts] = useState<OutboundDraft[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryHealth | null>(null);
  const [googleStatus, setGoogleStatus] = useState<GoogleIntegrationStatus | null>(null);
  const [telegramStatus, setTelegramStatus] = useState<TelegramIntegrationStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isMutating, setIsMutating] = useState(false);
  const [error, setError] = useState("");
  const [selectedActionId, setSelectedActionId] = useState<number | null>(null);
  const [activeFilter, setActiveFilter] = useState<"all" | "today" | "overdue" | "reply" | "approval">("all");

  async function refreshSurface() {
    const [
      healthResponse,
      profileResponse,
      agendaResponse,
      inboxResponse,
      actionResponse,
      draftResponse,
      telemetryResponse,
      googleResponse,
      telegramResponse,
    ] = await Promise.all([
      getHealth(settings),
      getModelProfiles(settings),
      getAssistantAgenda(settings),
      getAssistantInbox(settings),
      getAssistantSuggestedActions(settings),
      listAssistantDrafts(settings),
      getTelemetryHealth(settings),
      getGoogleIntegrationStatus(settings).catch(() => null),
      getTelegramIntegrationStatus(settings).catch(() => null),
    ]);
    setHealthMode(healthResponse.deployment_mode || settings.deploymentMode);
    setProfiles(profileResponse);
    setAgenda(agendaResponse.items);
    setInbox(inboxResponse.items);
    setActions(actionResponse.items);
    setDrafts(draftResponse.items);
    setTelemetry(telemetryResponse);
    setGoogleStatus(googleResponse);
    setTelegramStatus(telegramResponse);
    setSelectedActionId((current) => {
      if (current && actionResponse.items.some((item) => item.id === current)) return current;
      return actionResponse.items[0]?.id ?? null;
    });
  }

  useEffect(() => {
    setIsLoading(true);
    refreshSurface()
      .then(() => setError(""))
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, [settings.baseUrl, settings.token]);

  const selectedAction = actions.find((a) => a.id === selectedActionId) || null;
  const selectedDraft = drafts.find((d) => Number(d.id) === Number(selectedAction?.draft_id)) || null;

  const filteredAgenda = useMemo(() => {
    const combined = [...agenda, ...inbox];
    switch (activeFilter) {
      case "today":
        return combined.filter((item) => item.kind === "due_today" || item.kind === "calendar_prep");
      case "overdue":
        return combined.filter((item) => item.kind === "overdue_task");
      case "reply":
        return combined.filter((item) => item.kind === "reply_needed");
      case "approval":
        return combined.filter((item) => item.manual_review_required);
      default:
        return combined;
    }
  }, [activeFilter, agenda, inbox]);

  async function handleApproveAction(actionId: number) {
    setIsMutating(true);
    try {
      await approveAssistantAction(settings, actionId, "Arayüz üzerinden onaylandı.");
      await refreshSurface();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aksiyon onaylanamadı.");
    } finally {
      setIsMutating(false);
    }
  }

  async function handleDismissAction(actionId: number) {
    setIsMutating(true);
    try {
      await dismissAssistantAction(settings, actionId, "Arayüz üzerinden kapatıldı.");
      await refreshSurface();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aksiyon kapatılamadı.");
    } finally {
      setIsMutating(false);
    }
  }

  async function handleSendDraft(draftId: number) {
    setIsMutating(true);
    try {
      await sendAssistantDraft(settings, draftId, "Arayüz üzerinden gönderim denendi.");
      await refreshSurface();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Taslak gönderilemedi.");
    } finally {
      setIsMutating(false);
    }
  }

  async function handleGenerate(actionType: string) {
    if (!settings.currentMatterId) {
      setError("Hedef odaklı aksiyon üretmek için önce bir dosya seçin.");
      return;
    }
    setIsMutating(true);
    try {
      await generateAssistantAction(settings, {
        action_type: actionType,
        matter_id: settings.currentMatterId,
        target_channel: actionType === "send_telegram_message" ? "telegram" : "email",
        title: settings.currentMatterLabel ? `${settings.currentMatterLabel} için asistan aksiyonu` : undefined,
      });
      await refreshSurface();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aksiyon üretilemedi.");
    } finally {
      setIsMutating(false);
    }
  }

  async function handleSyncGoogle() {
    if (!window.lawcopilotDesktop?.syncGoogleData) {
      setError("Google eşitleme yalnız masaüstü uygulamasında kullanılabilir.");
      return;
    }
    setIsMutating(true);
    try {
      await window.lawcopilotDesktop.syncGoogleData();
      await refreshSurface();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google verileri eşitlenemedi.");
    } finally {
      setIsMutating(false);
    }
  }

  if (isLoading) {
    return <LoadingSpinner label="Genel bakış yükleniyor..." />;
  }

  const waitingDrafts = drafts.filter((d) => d.approval_status !== "approved" || d.delivery_status !== "sent");

  return (
    <div className="page-grid">
      <SectionCard
        title="Genel bakış"
        subtitle="Bugünün işleri, önerilen aksiyonlar ve onay bekleyen taslaklar tek bakışta görünür."
      >
        <div className="toolbar" style={{ alignItems: "flex-start" }}>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <StatusBadge tone="accent">{new Date().toLocaleDateString("tr-TR", { dateStyle: "full" })}</StatusBadge>
            <StatusBadge tone="accent">{dagitimKipiEtiketi(healthMode)}</StatusBadge>
            <StatusBadge>{modelProfilEtiketi(profiles?.default || settings.selectedModelProfile)}</StatusBadge>
            <StatusBadge tone={googleStatus?.configured ? "accent" : "warning"}>
              {googleStatus?.configured ? "Google bağlı" : "Google bağlı değil"}
            </StatusBadge>
            <StatusBadge tone={telegramStatus?.configured ? "accent" : "warning"}>
              {telegramStatus?.configured ? "Telegram bağlı" : "Telegram bağlı değil"}
            </StatusBadge>

            <StatusBadge tone={telemetry?.provider_configured ? "accent" : "warning"}>
              {telemetry?.assistant_runtime_mode === "advanced-openclaw"
                ? "Gelişmiş ajan köprüsü"
                : telemetry?.assistant_runtime_mode === "direct-provider"
                  ? "Doğrudan sağlayıcı"
                  : "Fallback modu"}
            </StatusBadge>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button className="button button--secondary" type="button" onClick={handleSyncGoogle} disabled={isMutating || !googleStatus?.configured}>
              Google verisini yenile
            </button>
            <Link className="button button--secondary" to="/settings">
              Bağlantıları yönet
            </Link>
          </div>
        </div>
        <div className="metric-grid" style={{ marginTop: "1rem" }}>
          <MetricCard label="Ajanda" value={agenda.length + inbox.length} />
          <MetricCard label="Önerilen adım" value={actions.length} />
          <MetricCard label="Onay bekleyen taslak" value={waitingDrafts.length} />
        </div>
        {settings.currentMatterId ? (
          <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>
            Etkin dosya bağlamı: <strong>{settings.currentMatterLabel || `Dosya #${settings.currentMatterId}`}</strong>
          </p>
        ) : (
          <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>
            Genel ajanda görünümü açık. Dosya seçerseniz taslak aksiyonlar doğrudan o dosya bağlamıyla üretilir.
          </p>
        )}
        {googleStatus?.last_sync_at ? (
          <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>
            Google son eşitleme: {dateLabel(googleStatus.last_sync_at)} · {googleStatus.email_thread_count || 0} e-posta zinciri · {googleStatus.calendar_event_count || 0} takvim kaydı
          </p>
        ) : null}
        {error ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{error}</p> : null}
      </SectionCard>

      <div className="page-grid page-grid--split">
        <div className="stack">
          <SectionCard title="Bugün yapılması gerekenler" subtitle="Avukatın önce görmesi gereken işler, bekleyen yanıtlar ve yaklaşan hazırlıklar.">
            <div className="toolbar" style={{ marginBottom: "0.75rem" }}>
              {[
                { key: "all", label: "Tümü" },
                { key: "today", label: "Bugün" },
                { key: "overdue", label: "Geciken" },
                { key: "reply", label: "Yanıt bekleyen" },
                { key: "approval", label: "İnceleme isteyen" },
              ].map((filter) => (
                <button
                  key={filter.key}
                  className={activeFilter === filter.key ? "button" : "button button--secondary"}
                  type="button"
                  onClick={() => setActiveFilter(filter.key as typeof activeFilter)}
                >
                  {filter.label}
                </button>
              ))}
            </div>
            {filteredAgenda.length ? (
              <div className="list">
                {filteredAgenda.map((item) => (
                  <article className="list-item" key={item.id}>
                    <div className="toolbar">
                      <h3 className="list-item__title">{item.title}</h3>
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                        <StatusBadge tone={item.priority === "high" ? "danger" : item.priority === "medium" ? "warning" : "accent"}>
                          {ajandaTipiEtiketi(item.kind)}
                        </StatusBadge>
                        {item.manual_review_required ? <StatusBadge>İnceleme gerekli</StatusBadge> : null}
                      </div>
                    </div>
                    <p className="list-item__meta">
                      {dateLabel(item.due_at)}
                      {item.matter_id ? ` · Dosya #${item.matter_id}` : ""}
                    </p>
                    {item.details ? <p style={{ marginBottom: 0 }}>{item.details}</p> : null}
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState title="Ajanda boş" description="Bağlı kaynaklardan yeni sinyal geldikçe burada görünür." />
            )}
          </SectionCard>
        </div>

        <div className="stack">
          <SectionCard
            title="Önerilen adımlar"
            subtitle="Asistan önerir, taslak üretir ve açık onay ister."
            actions={
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button className="button button--secondary" type="button" onClick={() => handleGenerate("prepare_client_update")} disabled={isMutating}>
                  Güncelleme taslağı
                </button>
                <button className="button button--secondary" type="button" onClick={() => handleGenerate("reply_email")} disabled={isMutating}>
                  E-posta yanıtı
                </button>
                <button className="button button--secondary" type="button" onClick={() => handleGenerate("send_telegram_message")} disabled={isMutating}>
                  Telegram yanıtı
                </button>
              </div>
            }
          >
            {actions.length ? (
              <div className="list">
                {actions.map((action) => (
                  <article
                    className="list-item"
                    key={action.id}
                    onClick={() => setSelectedActionId(action.id)}
                    style={{
                      cursor: "pointer",
                      borderColor: selectedActionId === action.id ? "var(--accent)" : undefined,
                    }}
                  >
                    <div className="toolbar">
                      <h3 className="list-item__title">{action.title}</h3>
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                        <StatusBadge tone="warning">{asistanAksiyonTipiEtiketi(action.action_type)}</StatusBadge>
                        <StatusBadge>{asistanAksiyonDurumuEtiketi(action.status)}</StatusBadge>
                      </div>
                    </div>
                    {action.description ? <p style={{ marginBottom: "0.5rem" }}>{action.description}</p> : null}
                    {action.rationale ? <p className="list-item__meta">{action.rationale}</p> : null}
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState title="Önerilen aksiyon yok" description="Ajanda ve risk sinyalleri geldikçe burada taslak aksiyonlar oluşur." />
            )}
          </SectionCard>

          <SectionCard
            title="Seçili adım"
            subtitle="Taslak önizleme, dayanak ve onay akışı burada yönetilir."
            actions={
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <Link className="button button--secondary" to="/drafts">
                  Taslak merkezi
                </Link>
                <Link className="button button--secondary" to="/matters">
                  Dosyaları aç
                </Link>
              </div>
            }
          >
            {selectedAction ? (
              <div className="stack">
                <div className="callout callout--accent">
                  <strong>{selectedAction.title}</strong>
                  <p style={{ marginBottom: 0 }}>{selectedAction.rationale || "Ek gerekçe yok."}</p>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <StatusBadge tone="warning">{asistanAksiyonTipiEtiketi(selectedAction.action_type)}</StatusBadge>
                  <StatusBadge>{asistanAksiyonDurumuEtiketi(selectedAction.status)}</StatusBadge>
                  {selectedAction.target_channel ? <StatusBadge>{kanalEtiketi(selectedAction.target_channel)}</StatusBadge> : null}
                </div>
                {selectedDraft ? (
                  <article className="list-item">
                    <div className="toolbar">
                      <h3 className="list-item__title">{selectedDraft.subject || "Taslak önizleme"}</h3>
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                        <StatusBadge>{kanalEtiketi(selectedDraft.channel)}</StatusBadge>

                      </div>
                    </div>
                    {selectedDraft.to_contact ? <p className="list-item__meta">Hedef kişi: {selectedDraft.to_contact}</p> : null}
                    <p style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>{selectedDraft.body}</p>
                  </article>
                ) : (
                  <EmptyState title="Taslak önizleme yok" description="Bu aksiyon için henüz taslak kaydı bulunmuyor." />
                )}
                <div className="toolbar">
                  <button
                    className="button"
                    type="button"
                    onClick={() => handleApproveAction(selectedAction.id)}
                    disabled={isMutating || selectedAction.status === "approved"}
                  >
                    {isMutating ? "İşleniyor..." : "Onayla"}
                  </button>
                  <button
                    className="button button--secondary"
                    type="button"
                    onClick={() => handleDismissAction(selectedAction.id)}
                    disabled={isMutating || selectedAction.status === "dismissed"}
                  >
                    Kapat
                  </button>
                  {selectedDraft ? (
                    <button
                      className="button button--secondary"
                      type="button"
                      onClick={() => handleSendDraft(Number(selectedDraft.id))}
                      disabled={isMutating || selectedDraft.approval_status !== "approved"}
                    >
                      Gönder
                    </button>
                  ) : null}
                </div>
              </div>
            ) : (
              <EmptyState title="Aksiyon seçilmedi" description="Önerilen aksiyonlardan birini seçin." />
            )}
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
