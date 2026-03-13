import type { EmailDraft, SocialEvent, WorkspaceOverviewResponse, GoogleIntegrationStatus } from "../../types/domain";

type SourceSummary = {
  id: string;
  label: string;
  count: number;
  lastActivity?: string;
  emptyText: string;
};

function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("tr-TR", {
      day: "numeric",
      month: "short",
    });
  } catch {
    return "—";
  }
}

export function DataSourcesPanel({
  emailDrafts,
  socialEvents,
  workspaceOverview,
  googleStatus,
  loading,
}: {
  emailDrafts: EmailDraft[];
  socialEvents: SocialEvent[];
  workspaceOverview: WorkspaceOverviewResponse | null;
  googleStatus: GoogleIntegrationStatus | null;
  loading: boolean;
}) {
  const documentCount =
    workspaceOverview?.documents.count ?? workspaceOverview?.documents.items.length ?? 0;

  const sources: SourceSummary[] = [
    {
      id: "documents",
      label: "Belgeler",
      count: documentCount,
      lastActivity: workspaceOverview?.scan_jobs.items?.[0]?.updated_at,
      emptyText: "Henüz belge taranmadı",
    },
    {
      id: "emails",
      label: "E-posta Taslakları",
      count: emailDrafts.length,
      lastActivity: emailDrafts[0]?.updated_at || emailDrafts[0]?.created_at,
      emptyText: "E-posta taslağı yok",
    },
    {
      id: "social",
      label: "Sosyal Medya",
      count: socialEvents.length,
      lastActivity: socialEvents[0]?.created_at,
      emptyText: "Sosyal medya verisi yok",
    },
    {
      id: "drive",
      label: "Google Drive Dosyaları",
      count: googleStatus?.drive_file_count || 0,
      lastActivity: googleStatus?.last_sync_at || undefined,
      emptyText: "Drive dosyası yok",
    },
  ];

  return (
    <section className="hub-sources">
      <h2 className="hub-section-title">Veri Kaynakları</h2>
      {loading ? (
        <p className="hub-empty-text">Yükleniyor…</p>
      ) : (
        <div className="hub-sources__list">
          {sources.map((source) => (
            <div key={source.id} className="hub-source-item">
              <div className="hub-source-item__top">
                <span className="hub-source-item__label">{source.label}</span>
                <span className="hub-source-item__count">{source.count}</span>
              </div>
              <span className="hub-source-item__meta">
                {source.count > 0
                  ? `Son güncelleme: ${formatDate(source.lastActivity)}`
                  : source.emptyText}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Workspace folder info */}
      {workspaceOverview?.workspace ? (
        <div className="hub-sources__folder">
          <div className="hub-sources__folder-row">
            <span className="hub-sources__folder-icon">📂</span>
            <div>
              <span className="hub-source-item__label">
                {workspaceOverview.workspace.display_name}
              </span>
              <span className="hub-source-item__meta" style={{ display: "block" }}>
                {workspaceOverview.workspace.root_path}
              </span>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
