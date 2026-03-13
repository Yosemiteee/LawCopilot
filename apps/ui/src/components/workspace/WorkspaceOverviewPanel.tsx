import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../../app/AppContext";
import { belgeDurumuEtiketi, dagitimKipiEtiketi, destekSeviyesiEtiketi, modelProfilEtiketi } from "../../lib/labels";
import { buildCitationTarget, buildDocumentViewerPath } from "../../lib/documentViewer";
import { getWorkspaceOverview, runWorkspaceScan, saveWorkspaceRoot, searchWorkspace } from "../../services/lawcopilotApi";
import type { WorkspaceOverviewResponse, WorkspaceSearchResponse } from "../../types/domain";
import { EmptyState } from "../common/EmptyState";
import { MetricCard } from "../common/MetricCard";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";
import { CitationList } from "../citations/CitationList";
import { sozluk } from "../../i18n";
import { normalizeUiErrorMessage } from "../../lib/errors";

export function WorkspaceOverviewPanel() {
  const { settings, setWorkspace, setCurrentMatter } = useAppContext();
  const navigate = useNavigate();
  const [overview, setOverview] = useState<WorkspaceOverviewResponse | null>(null);
  const [result, setResult] = useState<WorkspaceSearchResponse | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [manualPath, setManualPath] = useState(settings.workspaceRootPath || "");
  const [isSavingPath, setIsSavingPath] = useState(false);
  const isDesktopApp = Boolean(window.lawcopilotDesktop?.chooseWorkspaceRoot);

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
      setError(normalizeUiErrorMessage(err, sozluk.workspace.loadError));
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
      setCurrentMatter(null, "");
      await refreshOverview();
      navigate("/workspace", { replace: true });
    } catch (err) {
      setError(normalizeUiErrorMessage(err, sozluk.workspace.chooseError));
    }
  }

  async function setRootManually() {
    if (!manualPath.trim()) return;
    setIsSavingPath(true);
    try {
      const pathName = manualPath.trim().split("/").filter(Boolean).pop() || manualPath.trim();
      const result = await saveWorkspaceRoot(settings, {
        root_path: manualPath.trim(),
        display_name: pathName,
      });
      setWorkspace({
        workspaceConfigured: true,
        workspaceRootName: result.workspace.display_name || pathName,
        workspaceRootPath: result.workspace.root_path || manualPath.trim(),
        workspaceRootHash: result.workspace.root_path_hash || "",
      });
      setCurrentMatter(null, "");
      await refreshOverview();
      setError("");
    } catch (err) {
      setError(normalizeUiErrorMessage(err, "Klasör kaydedilemedi."));
    } finally {
      setIsSavingPath(false);
    }
  }

  async function triggerScan(fullRescan = false) {
    setIsScanning(true);
    try {
      await runWorkspaceScan(settings, { full_rescan: fullRescan });
      await refreshOverview();
      setError("");
    } catch (err) {
      setError(normalizeUiErrorMessage(err, sozluk.workspace.scanError));
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
      setError(normalizeUiErrorMessage(err, sozluk.workspace.searchError));
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
    <div className="page-grid page-grid--workspace">
      <div className="stack">
        <SectionCard
          title={sozluk.workspace.title}
          subtitle={sozluk.workspace.subtitle}
          actions={
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {isDesktopApp ? (
                <button className="button button--secondary" type="button" onClick={chooseRoot}>
                  {settings.workspaceConfigured ? sozluk.workspace.change : sozluk.workspace.choose}
                </button>
              ) : null}
              <button className="button" type="button" onClick={() => triggerScan(false)} disabled={!settings.workspaceConfigured || isScanning}>
                {isScanning ? sozluk.workspace.scanning : sozluk.workspace.rescan}
              </button>
            </div>
          }
        >
          {/* Aktif klasör göstergesi */}
          {settings.workspaceConfigured && settings.workspaceRootPath ? (
            <div className="callout callout--accent" style={{ marginBottom: "1rem" }}>
              <strong>📂 Aktif çalışma klasörü</strong>
              <p style={{ marginBottom: 0, fontFamily: "monospace", fontSize: "0.9rem" }}>
                {settings.workspaceRootPath}
              </p>
            </div>
          ) : null}

          {/* Tarayıcıda manuel yol girişi */}
          {!isDesktopApp ? (
            <div className="field-grid" style={{ marginBottom: "1rem" }}>
              <label className="stack stack--tight">
                <span>Çalışma klasörü yolu</span>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    className="input"
                    value={manualPath}
                    onChange={(e) => setManualPath(e.target.value)}
                    placeholder="/home/kullanici/belgelerim veya C:\\Belgeler\\Dosyalar"
                    style={{ flex: 1 }}
                  />
                  <button
                    className="button"
                    type="button"
                    onClick={setRootManually}
                    disabled={!manualPath.trim() || isSavingPath}
                  >
                    {isSavingPath ? "Kaydediliyor..." : settings.workspaceConfigured ? "Klasörü değiştir" : "Klasörü kaydet"}
                  </button>
                </div>
              </label>
              <p style={{ color: "var(--text-muted)", marginBottom: 0, fontSize: "0.85rem" }}>
                Sunucunun erişebildiği bir klasör yolunu girin. Masaüstü uygulamasında dosya seçici kullanılır.
              </p>
            </div>
          ) : null}
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
                <>
                  <EmptyState title={sozluk.workspace.emptyFolderTitle} description={sozluk.workspace.emptyFolderDescription} />
                  <p style={{ color: "var(--text-muted)", marginBottom: 0 }}>{sozluk.workspace.emptyFolderHint}</p>
                </>
              ) : null}
            </div>
          ) : (
            <div className="stack">
              <div className="callout callout--accent">
                <strong>{sozluk.workspace.notSelectedTitle}</strong>
                <p style={{ marginBottom: 0 }}>{sozluk.workspace.notSelectedDescription}</p>
              </div>
              <div className="metric-grid">
                <MetricCard label={sozluk.workspace.modeLabel} value={dagitimKipiEtiketi(settings.deploymentMode)} />
                <MetricCard label={sozluk.settings.modelProfile} value={modelProfilEtiketi(settings.selectedModelProfile)} />
                <MetricCard label={sozluk.settings.providerStatusLabel} value={sozluk.settings.providerMissing} />
              </div>
            </div>
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
            <div className="stack">
              <EmptyState title={sozluk.workspace.chooseFirstTitle} description={sozluk.workspace.chooseFirstDescription} />
              <div className="toolbar">
                <button className="button" type="button" onClick={() => navigate("/settings")}>
                  {sozluk.shell.setupBannerAction}
                </button>
              </div>
            </div>
          )}
        </SectionCard>
      </div>

      <div className="stack">
        <SectionCard title="Çalışma masası kısayolları" subtitle="İlk kurulum ve çekirdek erişimi artık yan ekranda değil, ana ürün yüzeyinin parçası.">
          <div className="stack">
            <div className="callout">
              <strong>Ayarlar</strong>
              <p style={{ marginBottom: "0.75rem" }}>Çalışma klasörü, model profili, sağlayıcı ve Telegram kurulumu artık Ayarlar ekranından yönetilir.</p>
              <button className="button button--secondary" type="button" onClick={() => navigate("/settings")}>
                Ayarlara git
              </button>
            </div>
            <div className="callout">
              <strong>Çekirdek</strong>
              <p style={{ marginBottom: "0.75rem" }}>Arka plan işleri, bağlantılar ve son olaylar tek ekrandan izlenir.</p>
              <button className="button button--secondary" type="button" onClick={() => navigate("/connectors")}>
                Çekirdeği aç
              </button>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="Şu anda ne yapılabilir?" subtitle="Kurulum durumuna göre GUI üzerinden erişebileceğiniz ana işler.">
          <div className="list">
            <article className="list-item">
              <h3 className="list-item__title">Çalışma klasörünü sınırla</h3>
              <p className="list-item__meta">Uygulama yalnız seçili klasör ve alt klasörlerine erişir.</p>
            </article>
            <article className="list-item">
              <h3 className="list-item__title">Kaynak dayanaklı arama</h3>
              <p className="list-item__meta">Arama, dayanak pasajları ve ilgili belgeleri ayrı bloklarda gösterir.</p>
            </article>
            <article className="list-item">
              <h3 className="list-item__title">Benzer dosya tespiti</h3>
              <p className="list-item__meta">Dosya adı, içerik, klasör bağlamı ve checksum sinyalleriyle açıklanabilir eşleşme üretir.</p>
            </article>
            <article className="list-item">
              <h3 className="list-item__title">Türkçe hukuk iş akışları</h3>
              <p className="list-item__meta">Taslak, risk notu, görev ve zaman çizelgesi iş akışları GUI üzerinden kullanılır.</p>
            </article>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
