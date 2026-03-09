import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../../app/AppContext";
import { belgeDurumuEtiketi, dagitimKipiEtiketi, destekSeviyesiEtiketi } from "../../lib/labels";
import { buildCitationTarget, buildDocumentViewerPath } from "../../lib/documentViewer";
import { getWorkspaceOverview, runWorkspaceScan, searchWorkspace } from "../../services/lawcopilotApi";
import type { WorkspaceOverviewResponse, WorkspaceSearchResponse } from "../../types/domain";
import { EmptyState } from "../common/EmptyState";
import { MetricCard } from "../common/MetricCard";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";
import { CitationList } from "../citations/CitationList";
import { sozluk } from "../../i18n";

export function WorkspaceOverviewPanel() {
  const { settings, setWorkspace } = useAppContext();
  const navigate = useNavigate();
  const [overview, setOverview] = useState<WorkspaceOverviewResponse | null>(null);
  const [result, setResult] = useState<WorkspaceSearchResponse | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [isSearching, setIsSearching] = useState(false);

  async function refreshOverview() {
    try {
      const response = await getWorkspaceOverview(settings);
      setOverview(response);
      setWorkspace({
        workspaceConfigured: response.configured,
        workspaceRootName: response.workspace?.display_name || settings.workspaceRootName,
        workspaceRootPath: response.workspace?.root_path || settings.workspaceRootPath,
        workspaceRootHash: response.workspace?.root_path_hash || settings.workspaceRootHash
      });
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.workspace.loadError);
    }
  }

  useEffect(() => {
    refreshOverview().catch(() => undefined);
  }, [settings.baseUrl, settings.token]);

  async function chooseRoot() {
    if (!window.lawcopilotDesktop?.chooseWorkspaceRoot) {
      setError(sozluk.settings.desktopOnlyChoose);
      return;
    }
    try {
      const response = await window.lawcopilotDesktop.chooseWorkspaceRoot();
      if ((response as { canceled?: boolean }).canceled) {
        return;
      }
      const workspace = (response as { workspace?: Record<string, unknown> }).workspace || {};
      setWorkspace({
        workspaceConfigured: Boolean(workspace.workspaceRootPath),
        workspaceRootName: String(workspace.workspaceRootName || ""),
        workspaceRootPath: String(workspace.workspaceRootPath || ""),
        workspaceRootHash: String(workspace.workspaceRootHash || "")
      });
      await refreshOverview();
      navigate("/workspace", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.workspace.chooseError);
    }
  }

  async function triggerScan(fullRescan = false) {
    setIsScanning(true);
    try {
      await runWorkspaceScan(settings, { full_rescan: fullRescan });
      await refreshOverview();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.workspace.scanError);
    } finally {
      setIsScanning(false);
    }
  }

  async function runSearch() {
    setIsSearching(true);
    try {
      const response = await searchWorkspace(settings, { query, limit: 5 });
      setResult(response);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : sozluk.workspace.searchError);
    } finally {
      setIsSearching(false);
    }
  }

  const latestJob = overview?.scan_jobs.items?.[0];
  const documentCount = overview?.documents.count ?? overview?.documents.items.length ?? 0;
  const hasWorkspace = settings.workspaceConfigured && Boolean(overview?.workspace);
  const isEmptyWorkspace = hasWorkspace && documentCount === 0;
  const isScanRunning = isScanning || (latestJob ? !["completed", "failed"].includes(latestJob.status) : false);

  return (
    <div className="stack">
      <SectionCard
        title={sozluk.workspace.title}
        subtitle={sozluk.workspace.subtitle}
        actions={
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button className="button button--secondary" type="button" onClick={chooseRoot}>
              {settings.workspaceConfigured ? sozluk.workspace.change : sozluk.workspace.choose}
            </button>
            <button className="button" type="button" onClick={() => triggerScan(false)} disabled={!settings.workspaceConfigured || isScanning}>
              {isScanning ? sozluk.workspace.scanning : sozluk.workspace.rescan}
            </button>
          </div>
        }
      >
        {hasWorkspace ? (
          <div className="stack">
            <div className="callout">
              <strong>
                {settings.currentMatterId
                  ? sozluk.workspace.matterBridgeSelectedTitle
                  : sozluk.workspace.matterBridgeIdleTitle}
              </strong>
              <p style={{ marginBottom: 0 }}>
                {settings.currentMatterId
                  ? `${settings.currentMatterLabel || "Seçili dosya"} açık. ${sozluk.workspace.matterBridgeSelectedDescription}`
                  : sozluk.workspace.matterBridgeIdleDescription}
              </p>
            </div>
            <div className="metric-grid">
              <MetricCard label={sozluk.workspace.modeLabel} value={dagitimKipiEtiketi(settings.deploymentMode)} />
              <MetricCard label={sozluk.workspace.documentCountLabel} value={documentCount} />
              <MetricCard label={sozluk.workspace.lastScanLabel} value={latestJob ? new Date(latestJob.updated_at).toLocaleString("tr-TR") : sozluk.workspace.lastScanNever} />
            </div>
            <div className="callout callout--accent">
              <strong>{overview?.workspace?.display_name}</strong>
              <p style={{ marginBottom: 0 }}>{overview?.workspace?.root_path}</p>
            </div>
            {latestJob ? (
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <StatusBadge tone={latestJob.status === "completed" ? "accent" : latestJob.status === "failed" ? "danger" : "warning"}>
                  {belgeDurumuEtiketi(latestJob.status)}
                </StatusBadge>
                <StatusBadge>{`${latestJob.files_indexed} indekslendi`}</StatusBadge>
                <StatusBadge>{`${latestJob.files_failed} hata`}</StatusBadge>
                <StatusBadge>{`${latestJob.files_skipped} atlandı`}</StatusBadge>
              </div>
            ) : null}
            {isScanRunning ? (
              <div className="callout">
                <strong>{sozluk.workspace.scanInProgressTitle}</strong>
                <p style={{ marginBottom: 0 }}>{sozluk.workspace.scanInProgressDescription}</p>
              </div>
            ) : null}
            {isEmptyWorkspace ? (
              <EmptyState title={sozluk.workspace.emptyFolderTitle} description={sozluk.workspace.emptyFolderDescription} />
            ) : null}
            {isEmptyWorkspace ? <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.workspace.emptyFolderHint}</p> : null}
          </div>
        ) : (
          <EmptyState
            title={sozluk.workspace.notSelectedTitle}
            description={sozluk.workspace.notSelectedDescription}
          />
        )}
        {error ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{error}</p> : null}
        <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.workspace.rootPolicy}</p>
      </SectionCard>

      <SectionCard title={sozluk.workspace.searchTitle} subtitle={sozluk.workspace.searchSubtitle}>
        {settings.workspaceConfigured ? (
          <div className="stack">
            <label className="stack stack--tight">
              <span>{sozluk.workspace.searchLabel}</span>
              <textarea
                className="textarea"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={sozluk.workspace.searchPlaceholder}
              />
            </label>
            <div className="toolbar">
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <StatusBadge tone="accent">{sozluk.workspace.selectedScope}</StatusBadge>
                {overview?.workspace ? <StatusBadge>{overview.workspace.display_name}</StatusBadge> : null}
              </div>
              <button className="button" type="button" onClick={runSearch} disabled={!query.trim() || isSearching}>
                {isSearching ? sozluk.workspace.searching : sozluk.workspace.runSearch}
              </button>
            </div>
            {result ? (
              <div className="stack">
                <div className="callout callout--accent">
                  <strong>{sozluk.workspace.summaryTitle}</strong>
                  <p style={{ marginBottom: 0, lineHeight: 1.6 }}>{result.answer}</p>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <StatusBadge tone={result.support_level === "yuksek" ? "accent" : result.support_level === "orta" ? "warning" : "danger"}>
                    {destekSeviyesiEtiketi(result.support_level)}
                  </StatusBadge>
                  <StatusBadge tone={result.manual_review_required ? "warning" : "accent"}>
                    {result.manual_review_required ? sozluk.workspace.sourceBackedReview : sozluk.workspace.sourceBackedReady}
                  </StatusBadge>
                  <StatusBadge>{`${result.citation_count} alıntı`}</StatusBadge>
                </div>
                <SectionCard title={sozluk.workspace.citationsTitle} subtitle={sozluk.workspace.citationsSubtitle}>
                  <CitationList citations={result.citations.map((item, index) => ({
                    index: index + 1,
                    label: `[${index + 1}]`,
                    document_id: Number(item.workspace_document_id),
                    document_name: item.document_name,
                    matter_id: 0,
                    chunk_id: item.chunk_id,
                    chunk_index: item.chunk_index,
                    excerpt: item.excerpt,
                    relevance_score: item.relevance_score,
                    source_type: item.source_type,
                    support_type: item.support_type,
                    confidence: item.confidence,
                    line_anchor: item.line_anchor,
                    page: item.page,
                    line_start: item.line_start,
                    line_end: item.line_end
                  }))} resolveTarget={(citation) => buildCitationTarget(citation, "workspace")} />
                </SectionCard>
                <SectionCard title={sozluk.workspace.relatedDocumentsTitle} subtitle={sozluk.workspace.relatedDocumentsSubtitle}>
                  {result.related_documents.length ? (
                    <div className="list">
                      {result.related_documents.map((item) => (
                        <article className="list-item" key={item.workspace_document_id}>
                          <div className="toolbar">
                            <div>
                              <h3 className="list-item__title">{item.document_name}</h3>
                              <p className="list-item__meta" style={{ marginBottom: 0 }}>
                                {item.relative_path || "Yol bilgisi kaydedilmedi."}
                              </p>
                            </div>
                            <button
                              className="button button--ghost"
                              onClick={() =>
                                navigate(
                                  buildDocumentViewerPath({
                                    scope: "workspace",
                                    documentId: item.workspace_document_id,
                                  }),
                                )
                              }
                              type="button"
                            >
                              Belgeyi aç
                            </button>
                          </div>
                          <p style={{ marginBottom: 0 }}>{item.reason}</p>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title={sozluk.workspace.relatedDocumentsEmptyTitle} description={sozluk.workspace.relatedDocumentsEmptyDescription} />
                  )}
                </SectionCard>
                <SectionCard title={sozluk.workspace.attentionPointsTitle} subtitle={sozluk.workspace.attentionPointsSubtitle}>
                  {result.attention_points.length ? (
                    <div className="list">
                      {result.attention_points.map((item, index) => (
                        <article className="list-item" key={`attention-${index}`}>
                          <p style={{ marginBottom: 0 }}>{item}</p>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title={sozluk.workspace.attentionPointsEmptyTitle} description={sozluk.workspace.attentionPointsEmptyDescription} />
                  )}
                </SectionCard>
                <SectionCard title={sozluk.workspace.missingSignalsTitle} subtitle={sozluk.workspace.missingSignalsSubtitle}>
                  {result.missing_document_signals.length ? (
                    <div className="list">
                      {result.missing_document_signals.map((item, index) => (
                        <article className="list-item" key={`missing-${index}`}>
                          <p style={{ marginBottom: 0 }}>{item}</p>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title={sozluk.workspace.missingSignalsEmptyTitle} description={sozluk.workspace.missingSignalsEmptyDescription} />
                  )}
                </SectionCard>
                <SectionCard title={sozluk.workspace.draftSuggestionsTitle} subtitle={sozluk.workspace.draftSuggestionsSubtitle}>
                  {result.draft_suggestions.length ? (
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      {result.draft_suggestions.map((item) => (
                        <StatusBadge key={item} tone="accent">
                          {item}
                        </StatusBadge>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title={sozluk.workspace.draftSuggestionsEmptyTitle} description={sozluk.workspace.draftSuggestionsEmptyDescription} />
                  )}
                </SectionCard>
              </div>
            ) : null}
          </div>
        ) : (
          <EmptyState title={sozluk.workspace.chooseFirstTitle} description={sozluk.workspace.chooseFirstDescription} />
        )}
      </SectionCard>
    </div>
  );
}
