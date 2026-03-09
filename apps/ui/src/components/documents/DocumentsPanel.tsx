import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../../app/AppContext";
import { buildDocumentViewerPath } from "../../lib/documentViewer";
import { belgeDurumuEtiketi, kisaDosyaBoyutu, kaynakTipiEtiketi } from "../../lib/labels";
import { listMatterDocuments, listMatterIngestionJobs, listMatterWorkspaceDocuments, uploadMatterDocument } from "../../services/lawcopilotApi";
import type { IngestionJob, MatterDocument, MatterWorkspaceDocumentLink } from "../../types/domain";
import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";

export function DocumentsPanel({ matterId }: { matterId: number }) {
  const { settings } = useAppContext();
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<MatterDocument[]>([]);
  const [workspaceLinks, setWorkspaceLinks] = useState<MatterWorkspaceDocumentLink[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    Promise.all([
      listMatterDocuments(settings, matterId),
      listMatterIngestionJobs(settings, matterId),
      listMatterWorkspaceDocuments(settings, matterId)
    ])
      .then(([documentsResponse, jobsResponse, workspaceResponse]) => {
        if (!active) {
          return;
        }
        setDocuments(documentsResponse.items);
        setJobs(jobsResponse.items);
        setWorkspaceLinks(workspaceResponse.items);
        setError("");
      })
      .catch((err: Error) => {
        if (!active) {
          return;
        }
        setError(err.message);
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [settings.baseUrl, settings.token, matterId]);

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
                        navigate(
                          buildDocumentViewerPath({
                            scope: "workspace",
                            documentId: link.workspace_document_id,
                            matterId,
                          }),
                        )
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
                      Belgeyi aç
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
            {jobs.map((job) => (
              <article className="list-item" key={job.id}>
                <div className="toolbar">
                  <h3 className="list-item__title">{job.document_name || `Belge #${job.document_id}`}</h3>
                  <StatusBadge tone={job.status === "indexed" ? "accent" : job.status === "failed" ? "danger" : "warning"}>
                    {belgeDurumuEtiketi(job.status)}
                  </StatusBadge>
                </div>
                <p className="list-item__meta">
                  İş #{job.id} · {new Date(job.updated_at).toLocaleString("tr-TR")}
                  {job.error ? ` · Hata: ${job.error}` : ""}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz içe aktarma işi yok" description="İlk belge yüklendiğinde işler burada görünür." />
        )}
      </SectionCard>
    </div>
  );
}
