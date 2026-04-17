import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { buildDocumentViewerPath } from "../lib/documentViewer";
import { attachWorkspaceDocumentToMatter, findSimilarWorkspaceDocuments, getWorkspaceDocumentChunks, listWorkspaceDocuments } from "../services/lawcopilotApi";
import type { SimilarDocumentsResponse, WorkspaceChunk, WorkspaceDocument } from "../types/domain";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { belgeDurumuEtiketi, kisaDosyaBoyutu } from "../lib/labels";
import { openWorkspaceDocument } from "../lib/workspaceDocuments";

export function DocumentsPage() {
  const { settings } = useAppContext();
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<WorkspaceDocument[]>([]);
  const [selected, setSelected] = useState<WorkspaceDocument | null>(null);
  const [chunks, setChunks] = useState<WorkspaceChunk[]>([]);
  const [similar, setSimilar] = useState<SimilarDocumentsResponse | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isAttaching, setIsAttaching] = useState(false);

  async function refreshDocuments(searchText = "") {
    setIsLoading(true);
    try {
      const response = await listWorkspaceDocuments(settings, { q: searchText || undefined });
      setDocuments(response.items);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Belgeler yüklenemedi.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!settings.workspaceConfigured) {
      setDocuments([]);
      setSelected(null);
      setChunks([]);
      return;
    }
    refreshDocuments().catch(() => undefined);
  }, [settings.baseUrl, settings.token, settings.workspaceConfigured]);

  useEffect(() => {
    if (!selected) {
      setChunks([]);
      return;
    }
    getWorkspaceDocumentChunks(settings, selected.id)
      .then((response) => setChunks(response.items))
      .catch(() => setChunks([]));
  }, [selected?.id, settings.baseUrl, settings.token]);

  const previewChunks = useMemo(() => chunks.slice(0, 3), [chunks]);

  async function searchSimilar(document: WorkspaceDocument) {
    setSelected(document);
    try {
      const response = await findSimilarWorkspaceDocuments(settings, { document_id: document.id, limit: 5 });
      setSimilar(response);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Benzer belge taraması yapılamadı.");
    }
  }

  async function attachToMatter(document: WorkspaceDocument) {
    if (!settings.currentMatterId) {
      setError("Önce bir dosya seçin.");
      return;
    }
    setIsAttaching(true);
    try {
      await attachWorkspaceDocumentToMatter(settings, settings.currentMatterId, document.id);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Belge seçili dosyaya bağlanamadı.");
    } finally {
      setIsAttaching(false);
    }
  }

  async function revealPath(relativePath: string) {
    try {
      await window.lawcopilotDesktop?.revealPathInOS?.(relativePath);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Belge yolu açılamadı.");
    }
  }

  if (!settings.workspaceConfigured) {
    return <EmptyState title="Önce çalışma klasörü seçin" description="Belge listesi yalnız seçtiğiniz çalışma klasörü içinden oluşturulur." />;
  }

  return (
    <div className="page-grid page-grid--split">
      <SectionCard title="Çalışma alanı belgeleri" subtitle="Yalnız seçilen klasör ağacındaki belgeler listelenir ve analiz edilir." className="sticky-panel">
        <div className="stack">
          <div className="callout callout--accent">
            <strong>{settings.currentMatterId ? "Seçili dosya bağı açık" : "Henüz seçili dosya yok"}</strong>
            <p style={{ marginBottom: 0 }}>
              {settings.currentMatterId
                ? `${settings.currentMatterLabel || "Seçili dosya"} bu çalışma klasöründen belge bağlayabilir. Çalışma klasörü belge havuzudur, dosya ise inceleme ve taslak üretim yüzeyidir.`
                : "Çalışma klasörü yerel belge havuzudur. Bir dosya seçtiğinizde uygun belgeleri doğrudan o dosyaya bağlayabilirsiniz."}
            </p>
          </div>
          <div className="toolbar">
            <input
              className="input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Belge adı veya yol içinde ara"
            />
            <button className="button button--secondary" type="button" onClick={() => refreshDocuments(query)}>
              Filtrele
            </button>
          </div>
          {error ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{error}</p> : null}
          {isLoading ? (
            <p>Belgeler yükleniyor...</p>
          ) : documents.length ? (
            <div className="list">
              {documents.map((document) => (
                <article className="list-item" key={document.id}>
                  <div className="toolbar">
                    <div>
                      <h3 className="list-item__title">{document.display_name}</h3>
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>
                        {document.relative_path}
                      </p>
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      <StatusBadge tone={document.indexed_status === "indexed" ? "accent" : document.indexed_status === "failed" ? "danger" : "warning"}>
                        {belgeDurumuEtiketi(document.indexed_status)}
                      </StatusBadge>
                      <StatusBadge>{document.extension}</StatusBadge>
                      <StatusBadge>{kisaDosyaBoyutu(document.size_bytes)}</StatusBadge>
                    </div>
                  </div>
                  <div className="toolbar">
                    <button className="button button--secondary" type="button" onClick={() => searchSimilar(document)}>
                      Benzer dosyaları bul
                    </button>
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      <button
                        className="button button--ghost"
                        type="button"
                        onClick={() =>
                          void openWorkspaceDocument({
                            relativePath: document.relative_path,
                            fallbackTarget: {
                              scope: "workspace",
                              documentId: document.id,
                            },
                            navigate,
                          })
                        }
                      >
                        Belgeyi aç
                      </button>
                      <button className="button button--secondary" type="button" onClick={() => revealPath(document.relative_path)}>
                        Klasörde göster
                      </button>
                      <button className="button" type="button" onClick={() => attachToMatter(document)} disabled={!settings.currentMatterId || isAttaching}>
                        {settings.currentMatterId ? "Seçili dosyaya bağla" : "Önce dosya seçin"}
                      </button>
                    </div>
                  </div>
                  {document.last_error ? <p className="list-item__meta">Hata: {document.last_error}</p> : null}
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="Henüz belge bulunamadı" description="Çalışma klasörünü taradıktan sonra desteklenen belgeler burada görünür." />
          )}
        </div>
      </SectionCard>

      <div className="stack">
        <SectionCard title="Seçili belge önizlemesi" subtitle="Pasaj önizlemesi ve benzer dosya tespiti aynı yerden incelenir.">
          {selected ? (
            <div className="stack">
              <div className="callout callout--accent">
                <strong>{selected.display_name}</strong>
                <p style={{ marginBottom: 0 }}>{selected.relative_path}</p>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
                  <button
                    className="button button--ghost"
                    onClick={() =>
                      navigate(
                        buildDocumentViewerPath({
                          scope: "workspace",
                          documentId: selected.id,
                          chunkIndex: previewChunks[0]?.chunk_index ?? 0,
                          chunkId: previewChunks[0]?.id,
                          excerpt: previewChunks[0]?.text.slice(0, 180),
                        }),
                      )
                    }
                    type="button"
                  >
                    Ayrıntılı incelemeye geç
                  </button>
                </div>
              </div>
              {previewChunks.length ? (
                <div className="list">
                  {previewChunks.map((chunk) => (
                    <article className="list-item" key={chunk.id}>
                      <h3 className="list-item__title">Parça #{chunk.chunk_index + 1}</h3>
                      <p style={{ marginBottom: 0, lineHeight: 1.6 }}>{chunk.text.slice(0, 260)}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState title="Parça önizlemesi yok" description="Bu belge için henüz indekslenmiş pasaj bulunmadı." />
              )}
            </div>
          ) : (
            <EmptyState title="Bir belge seçin" description="Benzer dosya analizi ve pasaj önizlemesi için listeden bir belge seçin." />
          )}
        </SectionCard>

        <SectionCard title="Benzer dava dosyaları" subtitle="Sonuçlar kör skor değil, açıklama ve destekleyici pasajlarla gelir.">
          {similar?.items.length ? (
            <div className="stack">
              <div className="callout callout--accent">
                <strong>Benzerlik özeti</strong>
                <p style={{ marginBottom: 0 }}>{similar.explanation}</p>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
                </div>
              </div>
              <div className="list">
                {similar.items.map((item) => (
                  <article className="list-item" key={item.workspace_document_id}>
                    <div className="toolbar">
                      <div>
                        <h3 className="list-item__title">{item.belge_adi}</h3>
                        <p className="list-item__meta" style={{ marginBottom: 0 }}>{item.goreli_yol || "Yol bilgisi yok"}</p>
                      </div>
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                        <StatusBadge tone="accent">{`Benzerlik ${(item.benzerlik_puani * 100).toFixed(0)}%`}</StatusBadge>
                        <StatusBadge tone={item.manuel_inceleme_gerekir ? "warning" : "accent"}>
                          {item.manuel_inceleme_gerekir ? "İnceleme gerekli" : "Hazır"}
                        </StatusBadge>
                        <button
                          className="button button--ghost"
                          onClick={() =>
                            void openWorkspaceDocument({
                              relativePath: item.goreli_yol,
                              fallbackTarget: {
                                scope: "workspace",
                                documentId: item.workspace_document_id,
                                chunkId: item.destekleyici_pasajlar[0]?.chunk_id,
                                chunkIndex: item.destekleyici_pasajlar[0]?.chunk_index ?? 0,
                                excerpt: item.destekleyici_pasajlar[0]?.excerpt,
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
                    <p style={{ marginBottom: "0.5rem", lineHeight: 1.6 }}>{item.neden_benzer}</p>
                    <p className="list-item__meta">
                      Klasör bağlamı: {item.klasor_baglami} · Dosya adı %{(item.skor_bilesenleri.dosya_adi * 100).toFixed(0)} · İçerik %{(item.skor_bilesenleri.icerik * 100).toFixed(0)} · Klasör %{(item.skor_bilesenleri.klasor_baglami * 100).toFixed(0)}
                    </p>
                    {item.ortak_terimler.length ? <p className="list-item__meta">Ortak terimler: {item.ortak_terimler.join(", ")}</p> : null}
                    {item.destekleyici_pasajlar.length ? (
                      <div className="callout" style={{ marginTop: "0.5rem" }}>
                        <strong>Destekleyici pasajlar</strong>
                        {item.destekleyici_pasajlar.slice(0, 2).map((passage, index) => (
                          <p key={`${item.workspace_document_id}-${index}`} style={{ marginBottom: index === 1 ? 0 : "0.35rem" }}>
                            {passage.excerpt}
                          </p>
                        ))}
                      </div>
                    ) : null}
                    {item.dikkat_notlari.length ? (
                      <div className="callout" style={{ marginTop: "0.5rem" }}>
                        <strong>Dikkat edilmesi gereken noktalar</strong>
                        {item.dikkat_notlari.map((note, index) => (
                          <p key={`${item.workspace_document_id}-note-${index}`} style={{ marginBottom: index === item.dikkat_notlari.length - 1 ? 0 : "0.35rem" }}>
                            {note}
                          </p>
                        ))}
                      </div>
                    ) : null}
                    {item.taslak_onerileri.length ? (
                      <div className="callout" style={{ marginTop: "0.5rem" }}>
                        <strong>Taslak önerileri</strong>
                        <p style={{ marginBottom: 0 }}>{item.taslak_onerileri.join(" · ")}</p>
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState title="Henüz benzer dosya sonucu yok" description="Listeden bir belge seçip benzer dosyaları bulun." />
          )}
        </SectionCard>
      </div>
    </div>
  );
}
