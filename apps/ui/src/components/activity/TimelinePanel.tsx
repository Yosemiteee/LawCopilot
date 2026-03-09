import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../../app/AppContext";
import { buildCitationTarget, buildDocumentViewerPath } from "../../lib/documentViewer";
import { belirsizlikEtiketi, gerceklikEtiketi, guvenEtiketi, hareketTuruEtiketi, olayTipiEtiketi } from "../../lib/labels";
import { getMatterActivity, getMatterChronology, listMatterTimeline } from "../../services/lawcopilotApi";
import type { ActivityItem, ChronologyIssue, ChronologyItem, TimelineEvent } from "../../types/domain";
import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";

export function TimelinePanel({ matterId }: { matterId: number }) {
  const { settings } = useAppContext();
  const navigate = useNavigate();
  const [chronology, setChronology] = useState<ChronologyItem[]>([]);
  const [issues, setIssues] = useState<ChronologyIssue[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getMatterChronology(settings, matterId), getMatterActivity(settings, matterId), listMatterTimeline(settings, matterId)])
      .then(([chronologyResponse, activityResponse, timelineResponse]) => {
        setChronology(chronologyResponse.items);
        setIssues(chronologyResponse.issues);
        setActivity(activityResponse.items);
        setTimeline(timelineResponse.items);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token, matterId]);

  return (
    <div className="stack">
      <SectionCard title="Kronoloji" subtitle="Olgusal ve çıkarımsal olaylar ayrı gösterilir; güçlü ve zayıf taraflar görünür kalır.">
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
        {issues.length ? (
          <div className="stack stack--tight" style={{ marginBottom: "1rem" }}>
            {issues.map((issue, index) => (
              <div className="callout" key={`${issue.type}-${index}`}>
                <strong>{issue.title}</strong>
                <p style={{ marginBottom: 0 }}>{issue.details}</p>
              </div>
            ))}
          </div>
        ) : null}
        {chronology.length ? (
          <div className="list">
            {chronology.map((item) => (
              <article className="list-item" key={item.id}>
                <div className="toolbar">
                  <h3 className="list-item__title">{item.event}</h3>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <StatusBadge tone={item.factuality === "factual" ? "accent" : "warning"}>{gerceklikEtiketi(item.factuality)}</StatusBadge>
                    <StatusBadge>{guvenEtiketi(item.confidence)}</StatusBadge>
                    {item.uncertainty !== "none" ? <StatusBadge tone="warning">{belirsizlikEtiketi(item.uncertainty)}</StatusBadge> : null}
                  </div>
                </div>
                <p className="list-item__meta">{item.date} · {item.source_label}</p>
                {item.citation ? <p style={{ marginBottom: 0 }}>Kaynak pasajı: {item.citation.excerpt}</p> : null}
                {item.citation ? (
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
                    <button
                      className="button button--ghost"
                      onClick={() => navigate(buildDocumentViewerPath(buildCitationTarget(item.citation!, "matter", matterId)))}
                      type="button"
                    >
                      Belgedeki yeri aç
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz kronoloji yok" description="Notlar, belgeler ve son tarih bilgileri tarih tabanlı olay ürettikçe kronoloji oluşur." />
        )}
      </SectionCard>

      <SectionCard title="Hareket akışı" subtitle="Notlar, taslak olayları, içe aktarma güncellemeleri ve görev değişiklikleri tek akışta görünür.">
        {activity.length ? (
          <div className="list">
            {activity.map((item) => (
              <article className="list-item" key={item.source_ref}>
                <div className="toolbar">
                  <h3 className="list-item__title">{item.title}</h3>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <StatusBadge>{hareketTuruEtiketi(item.kind)}</StatusBadge>
                    {item.badge ? <StatusBadge tone={item.requires_review ? "warning" : "accent"}>{olayTipiEtiketi(item.badge)}</StatusBadge> : null}
                  </div>
                </div>
                <p className="list-item__meta">{new Date(item.created_at).toLocaleString("tr-TR")}</p>
                <p style={{ marginBottom: 0 }}>{item.details || "Ek ayrıntı kaydedilmedi."}</p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz hareket yok" description="Belgeler, notlar, taslaklar ve görevler değiştikçe bu akış dolacaktır." />
        )}
      </SectionCard>

      <SectionCard title="Ham zaman çizelgesi" subtitle="Kronoloji ve hareket akışının yanında temel olay kayıtları da görünür kalır.">
        {timeline.length ? (
          <div className="list">
            {timeline.map((event) => (
              <article className="list-item" key={event.id}>
                <div className="toolbar">
                  <h3 className="list-item__title">{event.title}</h3>
                  <StatusBadge tone="accent">{olayTipiEtiketi(event.event_type)}</StatusBadge>
                </div>
                <p className="list-item__meta">{new Date(event.event_at).toLocaleString("tr-TR")}</p>
                <p style={{ marginBottom: 0 }}>{event.details || "Ek ayrıntı kaydedilmedi."}</p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz olay yok" description="Belge, not, taslak veya görev eklendiğinde olaylar burada görünür." />
        )}
      </SectionCard>
    </div>
  );
}
