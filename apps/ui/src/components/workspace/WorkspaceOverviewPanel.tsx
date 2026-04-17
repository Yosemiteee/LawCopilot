import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../../app/AppContext";
import { belgeDurumuEtiketi } from "../../lib/labels";
import { getWorkspaceOverview, runWorkspaceScan, saveWorkspaceRoot } from "../../services/lawcopilotApi";
import type { WorkspaceOverviewResponse } from "../../types/domain";
import { MetricCard } from "../common/MetricCard";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";
import { sozluk } from "../../i18n";
import { normalizeUiErrorMessage } from "../../lib/errors";

export function WorkspaceOverviewPanel() {
  const { settings, setWorkspace, setCurrentMatter } = useAppContext();
  const navigate = useNavigate();
  const [overview, setOverview] = useState<WorkspaceOverviewResponse | null>(null);
  const [error, setError] = useState("");
  const [isScanning, setIsScanning] = useState(false);
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

  const latestJob = overview?.scan_jobs.items?.[0];
  const documentCount = overview?.documents.count ?? overview?.documents.items.length ?? 0;
  const hasWorkspace = settings.workspaceConfigured && Boolean(overview?.workspace);
  const isEmptyWorkspace = hasWorkspace && documentCount === 0;
  const isScanRunning = isScanning || (latestJob ? !["completed", "failed"].includes(latestJob.status) : false);
  const workspaceDisplayPath = overview?.workspace?.root_path || settings.workspaceRootPath || "";
  const latestScanValue = latestJob ? new Date(latestJob.updated_at).toLocaleString("tr-TR") : sozluk.workspace.lastScanNever;

  return (
    <div className="page-grid page-grid--workspace workspace-overview">
      <div className="stack workspace-overview__main">
        <SectionCard
          title={sozluk.settings.workspaceTitle}
          subtitle={sozluk.settings.workspaceSubtitle}
          actions={
            <div className="workspace-overview__actions">
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
          <div className="workspace-overview__body">
          {hasWorkspace ? (
            <div className="workspace-overview__hero">
              <div className="workspace-overview__hero-main">
                <span className="workspace-overview__eyebrow">Aktif çalışma klasörü</span>
                <h3 className="workspace-overview__workspace-name">{overview?.workspace?.display_name}</h3>
                <p className="workspace-overview__workspace-path">{workspaceDisplayPath}</p>
              </div>
              <div className="workspace-overview__status-cluster">
                <div className="workspace-overview__metric-grid">
                  <MetricCard label={sozluk.workspace.documentCountLabel} value={documentCount} />
                  <MetricCard label={sozluk.workspace.lastScanLabel} value={latestScanValue} />
                  <MetricCard label={sozluk.workspace.scanJobCountLabel} value={overview?.scan_jobs.items.length ?? 0} />
                </div>
                {latestJob ? (
                  <div className="workspace-overview__badge-row">
                    <StatusBadge tone={latestJob.status === "completed" ? "accent" : latestJob.status === "failed" ? "danger" : "warning"}>
                      {belgeDurumuEtiketi(latestJob.status)}
                    </StatusBadge>
                    <StatusBadge>{`${latestJob.files_indexed} indekslendi`}</StatusBadge>
                    {latestJob.files_failed ? <StatusBadge>{`${latestJob.files_failed} hata`}</StatusBadge> : null}
                    {latestJob.files_skipped ? <StatusBadge>{`${latestJob.files_skipped} atlandı`}</StatusBadge> : null}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {!isDesktopApp ? (
            <div className="field-grid workspace-overview__manual-path">
              <label className="stack stack--tight">
                <span>Çalışma klasörü yolu</span>
                <div className="workspace-overview__manual-path-row">
                  <input
                    className="input"
                    value={manualPath}
                    onChange={(e) => setManualPath(e.target.value)}
                    placeholder="/home/kullanici/belgelerim veya C:\\Belgeler\\Dosyalar"
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
              <p className="workspace-overview__support-copy">
                Sunucunun erişebildiği bir klasör yolunu girin. Masaüstü uygulamasında dosya seçici kullanılır.
              </p>
            </div>
          ) : null}
          {hasWorkspace ? (
            <div className="stack workspace-overview__status-stack">
              <div className="callout workspace-overview__focus-callout">
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
              <div className="workspace-overview__info-grid">
                {isScanRunning ? (
                  <div className="callout">
                    <strong>{sozluk.workspace.scanInProgressTitle}</strong>
                    <p style={{ marginBottom: 0 }}>{sozluk.workspace.scanInProgressDescription}</p>
                  </div>
                ) : null}
                {isEmptyWorkspace ? (
                  <div className="callout">
                    <strong>{sozluk.workspace.emptyFolderTitle}</strong>
                    <p style={{ marginBottom: 0 }}>{sozluk.workspace.emptyFolderDescription}</p>
                  </div>
                ) : null}
              </div>
              {isEmptyWorkspace ? (
                <p className="workspace-overview__support-copy">{sozluk.workspace.emptyFolderHint}</p>
              ) : null}
            </div>
          ) : (
            <div className="stack workspace-overview__status-stack">
              <div className="callout callout--accent">
                <strong>{sozluk.workspace.notSelectedTitle}</strong>
                <p style={{ marginBottom: 0 }}>{sozluk.workspace.notSelectedDescription}</p>
              </div>
              <div className="workspace-overview__empty-actions">
                {isDesktopApp ? (
                  <button className="button" type="button" onClick={chooseRoot}>
                    {sozluk.workspace.choose}
                  </button>
                ) : null}
                <button className="button button--secondary" type="button" onClick={() => navigate("/settings?tab=kurulum&section=kurulum-karti")}>
                  {sozluk.shell.setupBannerAction}
                </button>
              </div>
            </div>
          )}
          {error ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{error}</p> : null}
          <p className="workspace-overview__support-copy">{sozluk.workspace.rootPolicy}</p>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
