import type { OutboundDraft, SocialEvent, WorkspaceOverviewResponse, GoogleIntegrationStatus } from "../../types/domain";

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
  assistantDrafts,
  socialEvents,
  workspaceOverview,
  googleStatus,
  loading,
}: {
  assistantDrafts: OutboundDraft[];
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
      id: "drafts",
      label: "İletişim Taslakları",
      count: assistantDrafts.length,
      lastActivity: assistantDrafts[0]?.updated_at || assistantDrafts[0]?.created_at,
      emptyText: "İletişim taslağı yok",
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
    {
      id: "youtube",
      label: "YouTube Oynatma Listeleri",
      count: googleStatus?.youtube_playlist_count || 0,
      lastActivity: googleStatus?.last_sync_at || undefined,
      emptyText: "YouTube oynatma listesi yok",
    },
    {
      id: "youtube-history",
      label: "YouTube Geçmişi",
      count: googleStatus?.youtube_history_count || 0,
      lastActivity: googleStatus?.portability_last_sync_at || undefined,
      emptyText: "YouTube geçmiş kaydı yok",
    },
    {
      id: "browser-history",
      label: "Tarayıcı Geçmişi",
      count: googleStatus?.chrome_history_count || 0,
      lastActivity: googleStatus?.portability_last_sync_at || undefined,
      emptyText: "Tarayıcı geçmiş kaydı yok",
    },
  ];

  return (
    <section className="hub-sources">
      <h2 className="hub-section-title">Kaynak özeti</h2>
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

      {workspaceOverview?.workspace ? (
        <div className="hub-sources__folder">
          <div className="hub-sources__folder-row">
            <div>
              <span className="hub-source-item__label">Bağlı çalışma klasörü</span>
              <strong style={{ display: "block", marginTop: "0.2rem" }}>{workspaceOverview.workspace.display_name}</strong>
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
