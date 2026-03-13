import type { AssistantAgendaItem } from "../../types/domain";

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
  loading,
}: {
  agenda: AssistantAgendaItem[];
  inbox: AssistantAgendaItem[];
  loading: boolean;
}) {
  const allItems = [...inbox, ...agenda].slice(0, 12);

  return (
    <section className="hub-activity">
      <h2 className="hub-section-title">Güncel Çalışmalar</h2>
      {loading ? (
        <p className="hub-empty-text">Yükleniyor…</p>
      ) : allItems.length === 0 ? (
        <div className="hub-empty-state">
          <p className="hub-empty-text">Henüz güncel bir çalışma sinyali yok.</p>
          <p className="hub-empty-hint">
            Hesaplarınızı bağladığınızda ajanda, gelen işler ve öneriler burada görünür.
          </p>
        </div>
      ) : (
        <div className="hub-activity__list">
          {allItems.map((item) => (
            <div key={item.id} className="hub-activity-item">
              <div className="hub-activity-item__row">
                {priorityDot(item.priority)}
                <div className="hub-activity-item__content">
                  <span className="hub-activity-item__title">{item.title}</span>
                  <div className="hub-activity-item__meta">
                    <span className="hub-activity-item__kind">{kindLabel(item.kind)}</span>
                    {item.due_at ? (
                      <span className="hub-activity-item__time">{formatTime(item.due_at)}</span>
                    ) : null}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
