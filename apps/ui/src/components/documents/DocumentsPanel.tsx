import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../../app/AppContext";
import { buildDocumentViewerPath } from "../../lib/documentViewer";
import { openWorkspaceDocument } from "../../lib/workspaceDocuments";
import { belgeDurumuEtiketi, kisaDosyaBoyutu, kaynakTipiEtiketi } from "../../lib/labels";
import { listMatterDocuments, listMatterIngestionJobs, listMatterWorkspaceDocuments, uploadMatterDocument } from "../../services/lawcopilotApi";
import type { IngestionJob, MatterDocument, MatterWorkspaceDocumentLink } from "../../types/domain";
import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";

type IngestionProgress = {
  stageLabel: string;
  percent: number;
  etaLabel: string;
};

function formatEta(seconds: number): string {
  if (seconds <= 0) return "Bitiş bekleniyor";
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 2) return "~1 dk";
  if (minutes < 60) return `~${minutes} dk`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `~${hours} sa ${remainder} dk` : `~${hours} sa`;
}

function ingestionProgress(job: IngestionJob): IngestionProgress {
  const status = String(job.status || "").toLowerCase();
  if (status === "indexed" || status === "completed" || status === "success") {
    return { stageLabel: "İndeks tamamlandı", percent: 100, etaLabel: "Tamamlandı" };
  }
  if (status === "failed" || status === "error") {
    return { stageLabel: "İşlem durdu", percent: 100, etaLabel: "Müdahale gerekli" };
  }

  const created = new Date(job.created_at).getTime();
  const updated = new Date(job.updated_at).getTime();
  const elapsedSeconds = Math.max(0, (Date.now() - created) / 1000);
  const stalenessSeconds = Math.max(0, (Date.now() - updated) / 1000);

  if (status === "pending" || status === "queued") {
    const percent = Math.min(22, 8 + elapsedSeconds / 8);
    return {
      stageLabel: "Sırada",
      percent,
      etaLabel: formatEta(120 - Math.min(110, elapsedSeconds)),
    };
  }

  const percent = Math.min(92, Math.max(30, 30 + elapsedSeconds / 2.5));
  const eta = Math.max(20, 210 - elapsedSeconds - stalenessSeconds * 0.3);
  return {
    stageLabel: "Ayrıştırma ve indeksleme",
    percent,
    etaLabel: formatEta(eta),
  };
}

export function DocumentsPanel({ matterId }: { matterId: number }) {
  const { settings } = useAppContext();
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<MatterDocument[]>([]);
  const [workspaceLinks, setWorkspaceLinks] = useState<MatterWorkspaceDocumentLink[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function loadPanelData(options?: { silent?: boolean }) {
    if (!options?.silent) {
      setIsLoading(true);
    }
    try {
      const [documentsResponse, jobsResponse, workspaceResponse] = await Promise.all([
        listMatterDocuments(settings, matterId),
        listMatterIngestionJobs(settings, matterId),
        listMatterWorkspaceDocuments(settings, matterId)
      ]);
      setDocuments(documentsResponse.items);
      setJobs(jobsResponse.items);
      setWorkspaceLinks(workspaceResponse.items);
      setError("");
      return jobsResponse.items;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Belge paneli yüklenemedi.");
      return [] as IngestionJob[];
    } finally {
      if (!options?.silent) {
        setIsLoading(false);
      }
    }
  }

  useEffect(() => {
    let active = true;
    loadPanelData().catch(() => undefined);

    const timer = window.setInterval(async () => {
      if (!active) return;
      const activeJobs = jobs.some((item) => {
        const status = String(item.status || "").toLowerCase();
        return status !== "indexed" && status !== "completed" && status !== "success" && status !== "failed" && status !== "error";
      });
      if (!activeJobs && !isSubmitting) {
        return;
      }
      await loadPanelData({ silent: true });
    }, 5000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [settings.baseUrl, settings.token, matterId, isSubmitting, jobs]);

  async function handleUpload(formData: FormData) {
    const file = formData.get("file");
    if (!(file instanceof File) || !file.name) {
      setError("Yükleme yapmadan önce bir belge seçin.");
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await uploadMatterDocument(settings, matterId, {
        file,
        displayName: String(formData.get("displayName") || file.name),
        sourceType: String(formData.get("sourceType") || "upload")
      });
      setDocuments((prev) => [response.document, ...prev]);
      setJobs((prev) => [response.job, ...prev]);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Belge yüklenemedi.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const latestJob = jobs[0];
  const latestProgress = latestJob ? ingestionProgress(latestJob) : null;

  return (
    <div className="stack">
      <SectionCard title="Dosyaya belge yükle" subtitle="Bu dosya kapsamına yeni dayanak belge ekleyin ve içe aktarma durumunu izleyin.">
        <form
          className="field-grid field-grid--two"
          onSubmit={(event) => {
            event.preventDefault();
            handleUpload(new FormData(event.currentTarget));
            event.currentTarget.reset();
          }}
        >
          <label className="stack stack--tight">
            <span>Görünen ad</span>
            <input className="input" name="displayName" placeholder="Kira sözleşmesi, dava dilekçesi, intake notu" />
          </label>
          <label className="stack stack--tight">
            <span>Kaynak türü</span>
            <select className="select" name="sourceType" defaultValue="upload">
              <option value="upload">Yükleme</option>
              <option value="email">E-posta</option>
              <option value="portal">Portal</option>
              <option value="internal_note">İç not</option>
            </select>
          </label>
          <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
            <span>Belge dosyası</span>
            <input className="input" type="file" name="file" />
          </label>
          <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
            <span style={{ color: "var(--text-muted)" }}>Varsayılan davranış: dosya kapsamlı, kaynak dayanaklı ve izlenebilir içe aktarma.</span>
            <button className="button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Yükleniyor..." : "Belge ekle"}
            </button>
          </div>
        </form>
        {latestProgress ? (
          <div className="callout" style={{ marginTop: "1rem" }}>
            <div className="toolbar" style={{ marginBottom: "0.45rem" }}>
              <strong>İçe aktarma durumu: {latestProgress.stageLabel}</strong>
              <StatusBadge tone={latestJob?.status === "failed" ? "danger" : latestJob?.status === "indexed" ? "accent" : "warning"}>
                %{Math.round(latestProgress.percent)}
              </StatusBadge>
            </div>
            <div
              aria-label="Yükleme ilerleme çubuğu"
              style={{
                width: "100%",
                height: "0.55rem",
                borderRadius: "999px",
                background: "rgba(15, 23, 42, 0.08)",
                overflow: "hidden",
                marginBottom: "0.5rem",
              }}
            >
              <div
                style={{
                  width: `${latestProgress.percent}%`,
                  height: "100%",
                  borderRadius: "999px",
                  background: latestJob?.status === "failed" ? "var(--danger)" : "var(--accent)",
                  transition: "width 220ms ease",
                }}
              />
            </div>
            <p className="list-item__meta" style={{ marginBottom: 0 }}>
              Tahmini kalan süre: {latestProgress.etaLabel} · İş #{latestJob?.id}
            </p>
          </div>
        ) : null}
        {error ? <p style={{ color: "var(--danger)", marginTop: "1rem" }}>{error}</p> : null}
      </SectionCard>

      <SectionCard title="Dosyaya bağlı çalışma alanı belgeleri" subtitle="Seçili çalışma klasöründen bağlanan belgeler kopyalanmadan burada görünür.">
        {workspaceLinks.length ? (
          <div className="list">
            {workspaceLinks.map((link) => (
              <article className="list-item" key={`${link.matter_id}-${link.workspace_document_id}`}>
                <div className="toolbar">
                  <h3 className="list-item__title">{link.display_name}</h3>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                    <StatusBadge tone={link.indexed_status === "indexed" ? "accent" : link.indexed_status === "failed" ? "danger" : "warning"}>
                      {belgeDurumuEtiketi(link.indexed_status)}
                    </StatusBadge>
                    <StatusBadge>{link.extension}</StatusBadge>
                    <button
                      className="button button--ghost"
                      onClick={() =>
                        void openWorkspaceDocument({
                          relativePath: link.relative_path,
                          fallbackTarget: {
                            scope: "workspace",
                            documentId: link.workspace_document_id,
                            matterId,
                          },
                          navigate,
                        })
                      }
                      type="button"
                    >
                      Belgeyi aç
                    </button>
                  </div>
                </div>
                <p className="list-item__meta">{link.relative_path} · Bağlayan: {link.linked_by}</p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Bağlı çalışma alanı belgesi yok" description="Üst menüdeki Belgeler ekranından çalışma alanı belgesi seçip bu dosyaya bağlayın." />
        )}
      </SectionCard>

      <SectionCard title="Dosya belgeleri" subtitle="Bu dosyaya doğrudan yüklenen belgeler burada listelenir.">
        {isLoading ? (
          <p>Belgeler yükleniyor...</p>
        ) : documents.length ? (
          <div className="list">
            {documents.map((document) => (
              <article className="list-item" key={document.id}>
                <div className="toolbar">
                  <h3 className="list-item__title">{document.display_name}</h3>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                    <StatusBadge tone={document.ingest_status === "indexed" ? "accent" : document.ingest_status === "failed" ? "danger" : "warning"}>
                      {belgeDurumuEtiketi(document.ingest_status)}
                    </StatusBadge>
                    <StatusBadge>{kaynakTipiEtiketi(document.source_type)}</StatusBadge>
                    <button
                      className="button button--ghost"
                      onClick={() =>
                        navigate(
                          buildDocumentViewerPath({
                            scope: "matter",
                            documentId: document.id,
                            matterId,
                          }),
                        )
                      }
                      type="button"
                    >
                      Belgeyi incele
                    </button>
                  </div>
                </div>
                <p className="list-item__meta">
                  {document.filename} · {document.chunk_count ?? 0} parça · {kisaDosyaBoyutu(document.size_bytes)}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz dosya belgesi yok" description="Kaynak dayanaklı aramayı başlatmak için ilk belgeyi yükleyin veya çalışma alanından belge bağlayın." />
        )}
      </SectionCard>

      <SectionCard title="İçe aktarma işleri" subtitle="Belge ayrıştırma ve parçalama akışının operasyonel görünürlüğü.">
        {jobs.length ? (
          <div className="list">
            {jobs.map((job) => {
              const progress = ingestionProgress(job);
              return (
                <article className="list-item" key={job.id}>
                  <div className="toolbar">
                    <h3 className="list-item__title">{job.document_name || `Belge #${job.document_id}`}</h3>
                    <StatusBadge tone={job.status === "indexed" ? "accent" : job.status === "failed" ? "danger" : "warning"}>
                      {belgeDurumuEtiketi(job.status)}
                    </StatusBadge>
                  </div>
                  <div
                    style={{
                      width: "100%",
                      height: "0.4rem",
                      borderRadius: "999px",
                      background: "rgba(15, 23, 42, 0.08)",
                      overflow: "hidden",
                      marginBottom: "0.45rem",
                    }}
                  >
                    <div
                      style={{
                        width: `${progress.percent}%`,
                        height: "100%",
                        borderRadius: "999px",
                        background: job.status === "failed" ? "var(--danger)" : "var(--accent)",
                      }}
                    />
                  </div>
                  <p className="list-item__meta">
                    İş #{job.id} · {progress.stageLabel} · Kalan: {progress.etaLabel} · {new Date(job.updated_at).toLocaleString("tr-TR")}
                    {job.error ? ` · Hata: ${job.error}` : ""}
                  </p>
                </article>
              );
            })}
          </div>
        ) : (
          <EmptyState title="Henüz içe aktarma işi yok" description="İlk belge yüklendiğinde işler burada görünür." />
        )}
      </SectionCard>
    </div>
  );
}
