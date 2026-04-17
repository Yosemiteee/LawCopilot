import { useEffect, useMemo, useState } from "react";
import { useSearchParams, useParams } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { belgeDurumuEtiketi, kaynakTipiEtiketi, kisaDosyaBoyutu } from "../lib/labels";
import { parseDocumentViewerScope } from "../lib/documentViewer";
import { getDocumentChunks, getMatterDocument, getWorkspaceDocument, getWorkspaceDocumentChunks } from "../services/lawcopilotApi";
import type { DocumentChunk, MatterDocument, WorkspaceChunk, WorkspaceDocument } from "../types/domain";


type ViewerChunk = {
  id: number;
  chunkIndex: number;
  text: string;
  tokenCount: number;
  metadata: {
    line_anchor?: string;
    page?: number;
    line_start?: number;
    line_end?: number;
  };
};

export function DocumentViewerPage() {
  const { scope: scopeSlug, documentId: documentIdParam } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { settings } = useAppContext();
  const scope = parseDocumentViewerScope(scopeSlug);
  const documentId = Number(documentIdParam || 0);
  const matterId = Number(searchParams.get("dosya") || 0) || null;
  const selectedChunkIndexRaw = searchParams.get("parca");
  const selectedChunkIndexParam = selectedChunkIndexRaw !== null ? Number(selectedChunkIndexRaw) : null;
  const selectedChunkIdParam = searchParams.get("parcaKimligi");
  const excerpt = searchParams.get("alinti") || "";

  const [workspaceDocument, setWorkspaceDocument] = useState<WorkspaceDocument | null>(null);
  const [matterDocument, setMatterDocument] = useState<MatterDocument | null>(null);
  const [chunks, setChunks] = useState<ViewerChunk[]>([]);
  const [error, setError] = useState("");
  const [systemError, setSystemError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!scope || !documentId) {
      setIsLoading(false);
      setError("Belge yolu geçersiz.");
      return;
    }

    if (scope === "matter" && !matterId) {
      setIsLoading(false);
      setError("Dosya kapsamı bilgisi eksik olduğu için belge açılamadı.");
      return;
    }

    let active = true;
    setIsLoading(true);
    setError("");
    setSystemError("");

    const load = async () => {
      try {
        if (scope === "workspace") {
          const [document, chunkResponse] = await Promise.all([
            getWorkspaceDocument(settings, documentId),
            getWorkspaceDocumentChunks(settings, documentId),
          ]);
          if (!active) {
            return;
          }
          setWorkspaceDocument(document);
          setMatterDocument(null);
          setChunks(chunkResponse.items.map(mapWorkspaceChunk));
        } else {
          const [document, chunkResponse] = await Promise.all([
            getMatterDocument(settings, matterId!, documentId),
            getDocumentChunks(settings, documentId),
          ]);
          if (!active) {
            return;
          }
          setMatterDocument(document);
          setWorkspaceDocument(null);
          setChunks(chunkResponse.items.map(mapMatterChunk));
        }
      } catch (err) {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : "Belge görüntülenemedi.");
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };

    load().catch(() => undefined);
    return () => {
      active = false;
    };
  }, [documentId, matterId, scope, settings.baseUrl, settings.token]);

  const selectedChunkPosition = useMemo(() => {
    if (!chunks.length) {
      return -1;
    }

    if (selectedChunkIdParam) {
      const byId = chunks.findIndex((item) => String(item.id) === String(selectedChunkIdParam));
      if (byId >= 0) {
        return byId;
      }
    }

    if (selectedChunkIndexParam !== null && !Number.isNaN(selectedChunkIndexParam)) {
      const byIndex = chunks.findIndex((item) => item.chunkIndex === selectedChunkIndexParam);
      if (byIndex >= 0) {
        return byIndex;
      }
    }

    if (excerpt.trim()) {
      const loweredNeedle = normalizeForMatch(excerpt);
      const byExcerpt = chunks.findIndex((item) => normalizeForMatch(item.text).includes(loweredNeedle));
      if (byExcerpt >= 0) {
        return byExcerpt;
      }
      const excerptTerms = loweredNeedle.split(" ").filter((item) => item.length >= 3);
      let bestIndex = 0;
      let bestScore = -1;
      chunks.forEach((item, index) => {
        const normalized = normalizeForMatch(item.text);
        const score = excerptTerms.reduce((sum, term) => sum + (normalized.includes(term) ? 1 : 0), 0);
        if (score > bestScore) {
          bestScore = score;
          bestIndex = index;
        }
      });
      return bestIndex;
    }

    return 0;
  }, [chunks, excerpt, selectedChunkIdParam, selectedChunkIndexParam]);

  const selectedChunk = selectedChunkPosition >= 0 ? chunks[selectedChunkPosition] : null;
  const surroundingChunks = selectedChunkPosition >= 0
    ? chunks.slice(Math.max(0, selectedChunkPosition - 1), Math.min(chunks.length, selectedChunkPosition + 2))
    : [];
  const canOpenInDesktopApp = Boolean(workspaceDocument?.relative_path && window.lawcopilotDesktop?.openPathInOS);
  const canRevealInDesktopApp = Boolean(workspaceDocument?.relative_path && window.lawcopilotDesktop?.revealPathInOS);

  function selectChunk(position: number) {
    if (position < 0 || position >= chunks.length) {
      return;
    }
    const nextChunk = chunks[position];
    const next = new URLSearchParams(searchParams);
    next.set("parca", String(nextChunk.chunkIndex));
    next.set("parcaKimligi", String(nextChunk.id));
    setSearchParams(next, { replace: true });
  }

  async function openInSystem() {
    if (!workspaceDocument?.relative_path) {
      setSystemError("Bu belge masaüstü uygulamasında güvenli dosya yolu ile açılamadı.");
      return;
    }
    try {
      if (!window.lawcopilotDesktop?.openPathInOS) {
        throw new Error("Bu işlem yalnız masaüstü uygulamasında kullanılabilir.");
      }
      await window.lawcopilotDesktop.openPathInOS(workspaceDocument.relative_path);
      setSystemError("");
    } catch (err) {
      setSystemError(err instanceof Error ? err.message : "Belge sistem uygulamasında açılamadı.");
    }
  }

  async function revealInFolder() {
    if (!workspaceDocument?.relative_path) {
      setSystemError("Belge konumu gösterilemedi.");
      return;
    }
    try {
      if (!window.lawcopilotDesktop?.revealPathInOS) {
        throw new Error("Bu işlem yalnız masaüstü uygulamasında kullanılabilir.");
      }
      await window.lawcopilotDesktop.revealPathInOS(workspaceDocument.relative_path);
      setSystemError("");
    } catch (err) {
      setSystemError(err instanceof Error ? err.message : "Belge klasörde gösterilemedi.");
    }
  }

  if (!scope || !documentId) {
    return <EmptyState title="Geçersiz belge yolu" description="Açmak istediğiniz belge yolu çözülemedi." />;
  }

  if (isLoading) {
    return <SectionCard title="Belge görüntüleyici" subtitle="Kaynak pasajı hazırlanıyor."><p>Belge yükleniyor...</p></SectionCard>;
  }

  if (error) {
    return <SectionCard title="Belge görüntüleyici" subtitle="Yalnız seçilen çalışma klasörü kapsamındaki güvenli belgeler açılabilir."><EmptyState title="Belge açılamadı" description={error} /></SectionCard>;
  }

  const title = workspaceDocument?.display_name || matterDocument?.display_name || "Belge";
  const subtitle = workspaceDocument?.relative_path || matterDocument?.filename || "Yol bilgisi kaydedilmedi.";
  const selectedChunkLabel = selectedChunk ? `Parça ${selectedChunk.chunkIndex + 1}` : "Parça seçilmedi";

  return (
    <div className="page-grid page-grid--split">
      <div className="stack">
        <SectionCard
          title="Belge görüntüleyici"
          subtitle="Bu görünüm, alıntı yapılan pasajın dosyada tam olarak nerede geçtiğini gösterir."
          actions={
            scope === "workspace" ? (
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button
                  className="button button--secondary"
                  disabled={!canOpenInDesktopApp}
                  onClick={openInSystem}
                  title={canOpenInDesktopApp ? "Belgeyi sistem uygulamasında aç" : "Bu kısayol yalnız masaüstü uygulamasında çalışır"}
                  type="button"
                >
                  Sistem uygulamasında aç
                </button>
                <button
                  className="button button--ghost"
                  disabled={!canRevealInDesktopApp}
                  onClick={revealInFolder}
                  title={canRevealInDesktopApp ? "Belgenin klasörünü aç" : "Bu kısayol yalnız masaüstü uygulamasında çalışır"}
                  type="button"
                >
                  Klasörde göster
                </button>
              </div>
            ) : undefined
          }
        >
          <div className="callout callout--accent">
            <strong>{title}</strong>
            <p style={{ marginBottom: "0.5rem" }}>{subtitle}</p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {workspaceDocument ? (
                <>
                  <StatusBadge tone={workspaceDocument.indexed_status === "indexed" ? "accent" : workspaceDocument.indexed_status === "failed" ? "danger" : "warning"}>
                    {belgeDurumuEtiketi(workspaceDocument.indexed_status)}
                  </StatusBadge>
                  <StatusBadge>{workspaceDocument.extension}</StatusBadge>
                  <StatusBadge>{kisaDosyaBoyutu(workspaceDocument.size_bytes)}</StatusBadge>
                </>
              ) : matterDocument ? (
                <>
                  <StatusBadge tone={matterDocument.ingest_status === "indexed" ? "accent" : matterDocument.ingest_status === "failed" ? "danger" : "warning"}>
                    {belgeDurumuEtiketi(matterDocument.ingest_status)}
                  </StatusBadge>
                  <StatusBadge>{kaynakTipiEtiketi(matterDocument.source_type)}</StatusBadge>
                  <StatusBadge>{kisaDosyaBoyutu(matterDocument.size_bytes)}</StatusBadge>
                </>
              ) : null}
            </div>
          </div>
          {scope === "workspace" && (!canOpenInDesktopApp || !canRevealInDesktopApp) ? (
            <p className="list-item__meta" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
              Sistem uygulaması kısayolları yalnız masaüstü runtime hazır olduğunda açılır.
            </p>
          ) : null}
          {systemError ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{systemError}</p> : null}
        </SectionCard>

        <SectionCard
          title="Seçili pasaj"
          subtitle="Alıntı yapılan metin vurgulanır; çevresindeki bağlam da aynı ekranda görünür."
          actions={
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button className="button button--ghost" disabled={selectedChunkPosition <= 0} onClick={() => selectChunk(selectedChunkPosition - 1)} type="button">
                Önceki parça
              </button>
              <button className="button button--ghost" disabled={selectedChunkPosition < 0 || selectedChunkPosition >= chunks.length - 1} onClick={() => selectChunk(selectedChunkPosition + 1)} type="button">
                Sonraki parça
              </button>
            </div>
          }
        >
          {selectedChunk ? (
            <div className="stack">
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <StatusBadge tone="accent">{selectedChunkLabel}</StatusBadge>
                {selectedChunk.metadata.line_anchor ? <StatusBadge>{selectedChunk.metadata.line_anchor}</StatusBadge> : null}
                {selectedChunk.metadata.page ? <StatusBadge>{`Sayfa ${selectedChunk.metadata.page}`}</StatusBadge> : null}
                {selectedChunk.metadata.line_start ? <StatusBadge>{`Satır ${selectedChunk.metadata.line_start}${selectedChunk.metadata.line_end ? `-${selectedChunk.metadata.line_end}` : ""}`}</StatusBadge> : null}
              </div>
              <article className="document-viewer__chunk document-viewer__chunk--selected">
                <p className="document-viewer__text">{renderHighlightedText(selectedChunk.text, excerpt)}</p>
              </article>
              {excerpt ? <p className="list-item__meta" style={{ margin: 0 }}>Dayanak pasajı vurgulandı. Metin eşleşmesi yaklaşık ise en yakın parça seçildi.</p> : null}
            </div>
          ) : (
            <EmptyState title="Pasaj bulunamadı" description="Bu belge için gösterilebilecek parça bulunmuyor." />
          )}
        </SectionCard>

        <SectionCard title="Çevresel bağlam" subtitle="Seçili pasajın hemen öncesi ve sonrası birlikte incelenebilir.">
          {surroundingChunks.length ? (
            <div className="stack">
              {surroundingChunks.map((chunk) => {
                const isSelected = selectedChunk?.id === chunk.id;
                return (
                  <article className={`document-viewer__chunk ${isSelected ? "document-viewer__chunk--selected" : ""}`} key={chunk.id}>
                    <div className="toolbar">
                      <h3 className="list-item__title">{isSelected ? "Seçili pasaj" : `Parça ${chunk.chunkIndex + 1}`}</h3>
                      <button className="button button--ghost" onClick={() => selectChunk(chunks.findIndex((item) => item.id === chunk.id))} type="button">
                        Bu parçaya git
                      </button>
                    </div>
                    <p className="document-viewer__text">{renderHighlightedText(chunk.text, isSelected ? excerpt : "")}</p>
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyState title="Bağlam bulunamadı" description="Belge parçası geldiğinde yakın bağlam burada görünür." />
          )}
        </SectionCard>
      </div>

      <SectionCard className="document-viewer__aside-card sticky-panel" title="Parça gezgini" subtitle="Belgedeki normalleştirilmiş metin parçaları arasında doğrudan geçiş yapın.">
        {chunks.length ? (
          <div className="list">
            {chunks.map((chunk, index) => {
              const isSelected = index === selectedChunkPosition;
              return (
                <article className={`list-item ${isSelected ? "document-viewer__navigator-item--selected" : ""}`} key={chunk.id}>
                  <div className="toolbar">
                    <div>
                      <h3 className="list-item__title">{`Parça ${chunk.chunkIndex + 1}`}</h3>
                      <p className="list-item__meta" style={{ marginBottom: 0 }}>
                        {chunk.metadata.line_anchor || (chunk.metadata.page ? `Sayfa ${chunk.metadata.page}` : "Satır bilgisi yok")}
                      </p>
                    </div>
                    <button className="button button--ghost" onClick={() => selectChunk(index)} type="button">
                      {isSelected ? "Açık" : "Aç"}
                    </button>
                  </div>
                  <p style={{ marginBottom: 0, lineHeight: 1.6 }}>{chunk.text.slice(0, 240)}</p>
                </article>
              );
            })}
          </div>
        ) : (
          <EmptyState title="Belge parçası yok" description="Bu belge için indekslenmiş metin parçası bulunamadı." />
        )}
      </SectionCard>
    </div>
  );
}

function mapWorkspaceChunk(chunk: WorkspaceChunk): ViewerChunk {
  return {
    id: chunk.id,
    chunkIndex: chunk.chunk_index,
    text: chunk.text,
    tokenCount: chunk.token_count,
    metadata: chunk.metadata || {},
  };
}

function mapMatterChunk(chunk: DocumentChunk): ViewerChunk {
  return {
    id: chunk.id,
    chunkIndex: chunk.chunk_index,
    text: chunk.text,
    tokenCount: chunk.token_count,
    metadata: chunk.metadata || {},
  };
}

function normalizeForMatch(value: string) {
  return value.toLocaleLowerCase("tr").replace(/\s+/g, " ").trim();
}

function renderHighlightedText(text: string, excerpt: string) {
  const range = findHighlightRange(text, excerpt);
  if (!range) {
    return text;
  }
  const before = text.slice(0, range.start);
  const match = text.slice(range.start, range.end);
  const after = text.slice(range.end);
  return (
    <>
      {before}
      <mark>{match}</mark>
      {after}
    </>
  );
}

function findHighlightRange(text: string, excerpt: string) {
  if (!excerpt.trim()) {
    return null;
  }
  const loweredText = text.toLocaleLowerCase("tr");
  const loweredExcerpt = excerpt.toLocaleLowerCase("tr").replace(/\s+/g, " ").trim();
  const exactIndex = loweredText.indexOf(loweredExcerpt);
  if (exactIndex >= 0) {
    return { start: exactIndex, end: exactIndex + loweredExcerpt.length };
  }

  const terms = loweredExcerpt
    .split(" ")
    .map((item) => item.trim())
    .filter((item) => item.length >= 4)
    .sort((left, right) => right.length - left.length);

  for (const term of terms) {
    const termIndex = loweredText.indexOf(term);
    if (termIndex >= 0) {
      return { start: termIndex, end: termIndex + term.length };
    }
  }

  return null;
}
