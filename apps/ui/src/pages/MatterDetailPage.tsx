import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { MetricCard } from "../components/common/MetricCard";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { Tabs } from "../components/common/Tabs";
import { MatterNotesPanel } from "../components/activity/MatterNotesPanel";
import { RiskNotesPanel } from "../components/activity/RiskNotesPanel";
import { DocumentsPanel } from "../components/documents/DocumentsPanel";
import { DraftsPanel } from "../components/drafts/DraftsPanel";
import { SearchWorkbench } from "../components/documents/SearchWorkbench";
import { TasksPanel } from "../components/tasks/TasksPanel";
import { TimelinePanel } from "../components/activity/TimelinePanel";
import { dosyaDurumuEtiketi, olayTipiEtiketi } from "../lib/labels";
import { getMatter, getMatterSummary, updateMatter } from "../services/lawcopilotApi";
import type { Matter, MatterSummary } from "../types/domain";
import { useParams } from "react-router-dom";

const TABS = [
  { key: "summary", label: "Özet" },
  { key: "documents", label: "Belgeler" },
  { key: "search", label: "Arama" },
  { key: "tasks", label: "Görevler" },
  { key: "drafts", label: "Taslaklar" },
  { key: "notes", label: "Notlar" },
  { key: "timeline", label: "Zaman çizelgesi" }
];

export function MatterDetailPage() {
  const params = useParams();
  const matterId = Number(params.matterId);
  const { settings, setCurrentMatter } = useAppContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const [matter, setMatter] = useState<Matter | null>(null);
  const [summary, setSummary] = useState<MatterSummary | null>(null);
  const [error, setError] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const activeTab = searchParams.get("tab") || "summary";

  useEffect(() => {
    Promise.all([getMatter(settings, matterId), getMatterSummary(settings, matterId)])
      .then(([matterResponse, summaryResponse]) => {
        setMatter(matterResponse);
        setSummary(summaryResponse);
        setCurrentMatter(matterResponse.id, matterResponse.title);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [matterId, settings.baseUrl, settings.token, setCurrentMatter]);

  async function handleMatterUpdate(formData: FormData) {
    if (!matter) return;
    setIsUpdating(true);
    try {
      const updated = await updateMatter(settings, matter.id, {
        status: String(formData.get("status") || matter.status),
        practice_area: String(formData.get("practiceArea") || "") || undefined,
        client_name: String(formData.get("clientName") || "") || undefined,
        summary: String(formData.get("summary") || "") || undefined,
        lead_lawyer: String(formData.get("leadLawyer") || "") || undefined,
      });
      setMatter(updated);
      setIsEditing(false);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dosya güncellenemedi.");
    } finally {
      setIsUpdating(false);
    }
  }

  function renderTab() {
    if (!matter) {
      return <EmptyState title="Dosya yüklenemedi" description={error || "Devam etmek için listeden bir dosya açın."} />;
    }
    switch (activeTab) {
      case "documents":
        return <DocumentsPanel matterId={matter.id} />;
      case "search":
        return <SearchWorkbench matterId={matter.id} heading="Kaynak dayanaklı dosya araması" />;
      case "tasks":
        return <TasksPanel matterId={matter.id} />;
      case "drafts":
        return <DraftsPanel matterId={matter.id} matterLabel={matter.title} />;
      case "notes":
        return <MatterNotesPanel matterId={matter.id} />;
      case "timeline":
        return <TimelinePanel matterId={matter.id} />;
      default:
        return (
          <SectionCard title="Dosya özeti" subtitle="Özet, inceleme uyarıları ve son hareketlerle birlikte gösterilir.">
            {summary ? (
              <div className="stack">
                <div className="metric-grid">
                  <MetricCard label="Not" value={summary.counts.notes} />
                  <MetricCard label="Görev" value={summary.counts.tasks} />
                  <MetricCard label="Taslak" value={summary.counts.drafts} />
                </div>
                <div className="callout callout--accent">
                  <strong>Özet</strong>
                  <p style={{ marginBottom: 0, lineHeight: 1.6 }}>{summary.summary}</p>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <StatusBadge tone={summary.manual_review_required ? "warning" : "accent"}>
                    {summary.manual_review_required ? "İnceleme önerilir" : "Hazır"}
                  </StatusBadge>
                </div>
                <RiskNotesPanel matterId={matter.id} />
                <SectionCard title="Son hareketler" subtitle="Dosyanın son olayları özet görünümünde de görünür kalır.">
                  {summary.latest_timeline.length ? (
                    <div className="list">
                      {summary.latest_timeline.map((event) => (
                        <article className="list-item" key={event.id}>
                          <div className="toolbar">
                            <h3 className="list-item__title">{event.title}</h3>
                            <StatusBadge tone="accent">{olayTipiEtiketi(event.event_type)}</StatusBadge>
                          </div>
                          <p className="list-item__meta">{new Date(event.event_at).toLocaleString("tr-TR")}</p>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="Henüz hareket yok" description="Belge, not, taslak veya görev eklendikçe zaman akışı burada görünür." />
                  )}
                </SectionCard>
              </div>
            ) : (
              <p>Özet yükleniyor...</p>
            )}
          </SectionCard>
        );
    }
  }

  return (
    <div className="page-grid">
      <SectionCard
        title={matter?.title || "Dosya ayrıntısı"}
        subtitle="Geçerli dosya her sekmede görünür; arama, taslak ve görevler aynı hukuki bağlama bağlı kalır."
        actions={
          matter ? (
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
              <StatusBadge tone="accent">{dosyaDurumuEtiketi(matter.status)}</StatusBadge>
              {matter.practice_area ? <StatusBadge>{matter.practice_area}</StatusBadge> : null}
              <button
                className="button button--ghost"
                type="button"
                onClick={() => setIsEditing(!isEditing)}
                style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }}
              >
                {isEditing ? "İptal" : "Düzenle"}
              </button>
            </div>
          ) : null
        }
      >
        {matter ? (
          <div className="stack">
            {isEditing ? (
              <form
                className="field-grid"
                onSubmit={(event) => {
                  event.preventDefault();
                  handleMatterUpdate(new FormData(event.currentTarget));
                }}
              >
                <div className="field-grid field-grid--two">
                  <label className="stack stack--tight">
                    <span>Durum</span>
                    <select className="select" name="status" defaultValue={matter.status}>
                      <option value="active">Açık</option>
                      <option value="on_hold">Beklemede</option>
                      <option value="closed">Kapalı</option>
                    </select>
                  </label>
                  <label className="stack stack--tight">
                    <span>Çalışma alanı</span>
                    <input className="input" name="practiceArea" defaultValue={matter.practice_area || ""} placeholder="İş hukuku, kira, aile hukuku" />
                  </label>
                </div>
                <div className="field-grid field-grid--two">
                  <label className="stack stack--tight">
                    <span>Müvekkil</span>
                    <input className="input" name="clientName" defaultValue={matter.client_name || ""} placeholder="Müvekkil veya kurum adı" />
                  </label>
                  <label className="stack stack--tight">
                    <span>Sorumlu avukat</span>
                    <input className="input" name="leadLawyer" defaultValue={matter.lead_lawyer || ""} placeholder="Av. Ad Soyad" />
                  </label>
                </div>
                <label className="stack stack--tight">
                  <span>Özet</span>
                  <textarea className="textarea" name="summary" defaultValue={matter.summary || ""} placeholder="Dosya durum özeti" />
                </label>
                <div className="toolbar">
                  <span style={{ color: "var(--text-muted)" }}>Değişiklikler kaydedildiğinde dosya kaydı güncellenir.</span>
                  <button className="button" type="submit" disabled={isUpdating}>
                    {isUpdating ? "Kaydediliyor..." : "Değişiklikleri kaydet"}
                  </button>
                </div>
              </form>
            ) : (
              <p style={{ margin: 0, color: "var(--text-muted)" }}>
                {matter.client_name || "Müvekkil henüz girilmedi"} · {matter.reference_code || "Referans kodu yok"}
                {matter.lead_lawyer ? ` · ${matter.lead_lawyer}` : ""}
              </p>
            )}
            <Tabs
              activeTab={activeTab}
              items={TABS.map((item) => ({
                key: item.key,
                label: item.label,
                onSelect: () => setSearchParams({ tab: item.key })
              }))}
            />
          </div>
        ) : (
          <p>Dosya yükleniyor...</p>
        )}
      </SectionCard>
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      {renderTab()}
    </div>
  );
}
