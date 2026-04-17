import { useState } from "react";

import type { AssistantAgendaItem, OutboundDraft, SocialEvent } from "../../types/domain";

type ActivityRailFilter = "all" | "priority" | "drafts" | "social";

type ActivityRailItem = {
  id: string;
  title: string;
  kind: string;
  dueAt?: string | null;
  timestamp?: string | null;
  tone: "danger" | "warning" | "accent" | "neutral";
  sourceLabel: string;
  detail?: string;
  filter: ActivityRailFilter;
};

function priorityDot(priority: string) {
  const colors: Record<string, string> = {
    high: "var(--danger)",
    medium: "var(--warning)",
    low: "var(--accent)",
  };
  return (
    <span
      style={{
        display: "inline-block",
        width: 6,
        height: 6,
        borderRadius: "50%",
        background: colors[priority] || colors.medium,
        flexShrink: 0,
        marginTop: 6,
      }}
    />
  );
}

function kindLabel(kind: string): string {
  const labels: Record<string, string> = {
    reply_needed: "Yanıt bekliyor",
    social_alert: "Sosyal risk uyarısı",
    social_watch: "Sosyal izleme",
    calendar_prep: "Takvim hazırlığı",
    due_today: "Bugün vadeli",
    overdue_task: "Gecikmiş",
  };
  return labels[kind] || kind;
}

function formatTime(isoDate?: string | null): string {
  if (!isoDate) return "";
  try {
    return new Date(isoDate).toLocaleString("tr-TR", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function RecentActivityFeed({
  agenda,
  inbox,
  assistantDrafts,
  socialEvents,
  loading,
}: {
  agenda: AssistantAgendaItem[];
  inbox: AssistantAgendaItem[];
  assistantDrafts: OutboundDraft[];
  socialEvents: SocialEvent[];
  loading: boolean;
}) {
  const signalItems: ActivityRailItem[] = [...inbox, ...agenda].map((item) => ({
    id: `signal-${item.id}`,
    title: item.title,
    kind: kindLabel(item.kind),
    dueAt: item.due_at,
    timestamp: item.due_at,
    tone: item.priority === "high" ? "danger" : item.priority === "medium" ? "warning" : "accent",
    sourceLabel: item.kind === "reply_needed" ? "Inbox" : "Assistant",
    detail: item.details || "Yeni sinyal üretildi.",
    filter: item.priority === "high" ? "priority" : "all",
  }));

  const draftItems: ActivityRailItem[] = assistantDrafts.map((draft) => ({
    id: `draft-${draft.id}`,
    title: draft.subject || draft.draft_type || "Taslak üretildi",
    kind: "Taslak",
    dueAt: draft.updated_at || draft.created_at,
    timestamp: draft.updated_at || draft.created_at,
    tone: String(draft.delivery_status || "").trim() === "sent" ? "accent" : "warning",
    sourceLabel: String(draft.channel || "assistant").trim() || "assistant",
    detail: draft.to_contact || "Gönderim hedefi bekleniyor.",
    filter: "drafts",
  }));

  const socialItems: ActivityRailItem[] = socialEvents.map((event) => ({
    id: `social-${event.id}`,
    title: event.summary || event.category || event.handle || "Sosyal sinyal",
    kind: "Sosyal",
    dueAt: event.created_at,
    timestamp: event.created_at,
    tone: String(event.severity || "").trim() === "high" ? "danger" : "neutral",
    sourceLabel: String(event.source || "social").trim() || "social",
    detail: event.content || event.recommended_action || "Yeni sosyal aktivite algılandı.",
    filter: "social",
  }));

  const railItems: ActivityRailItem[] = [...signalItems, ...draftItems, ...socialItems]
    .sort((left, right) => {
      const leftTime = Date.parse(String(left.timestamp || left.dueAt || ""));
      const rightTime = Date.parse(String(right.timestamp || right.dueAt || ""));
      return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
    })
    .slice(0, 18);

  const [activeFilter, setActiveFilter] = useState<ActivityRailFilter>("all");
  const filteredItems = railItems.filter((item) => activeFilter === "all" || item.filter === activeFilter);

  return (
    <section className="hub-activity hub-activity--rail">
      <div className="hub-activity__header">
        <div>
          <h2 className="hub-section-title">Activity Rail</h2>
          <p className="hub-activity__subtitle">Asistanın ürettiği sinyaller, taslaklar ve dış olaylar tek akışta görünür.</p>
        </div>
        <div className="hub-activity__filters" role="tablist" aria-label="Activity filtreleri">
          {[
            ["all", "Tümü"],
            ["priority", "Öncelikli"],
            ["drafts", "Taslak"],
            ["social", "Sosyal"],
          ].map(([key, label]) => {
            const filterKey = key as ActivityRailFilter;
            const active = activeFilter === filterKey;
            return (
              <button
                key={key}
                className={`hub-activity__filter${active ? " hub-activity__filter--active" : ""}`}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setActiveFilter(filterKey)}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>
      {loading ? (
        <p className="hub-empty-text">Yükleniyor…</p>
      ) : filteredItems.length === 0 ? (
        <div className="hub-empty-state">
          <p className="hub-empty-text">Bu filtre için activity yok.</p>
          <p className="hub-empty-hint">Yeni olaylar geldikçe burada şeffaf şekilde akacak.</p>
        </div>
      ) : (
        <div className="hub-activity__list hub-activity__list--rail">
          {filteredItems.map((item) => (
            <article key={item.id} className={`hub-activity-item hub-activity-item--${item.tone}`}>
              <div className="hub-activity-item__rail">
                <span className={`hub-activity-item__pulse hub-activity-item__pulse--${item.tone}`} />
                <span className="hub-activity-item__line" />
              </div>
              <div className="hub-activity-item__content hub-activity-item__content--rail">
                <div className="hub-activity-item__topline">
                  <span className="hub-activity-item__title">{item.title}</span>
                  <span className={`hub-activity-item__badge hub-activity-item__badge--${item.tone}`}>{item.kind}</span>
                </div>
                <p className="hub-activity-item__detail">{item.detail}</p>
                <div className="hub-activity-item__meta hub-activity-item__meta--rail">
                  <span className="hub-activity-item__kind">{item.sourceLabel}</span>
                  {(item.timestamp || item.dueAt) ? (
                    <span className="hub-activity-item__time">{formatTime(item.timestamp || item.dueAt)}</span>
                  ) : null}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
