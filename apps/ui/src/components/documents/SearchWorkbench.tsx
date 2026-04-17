import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { buildCitationTarget, buildDocumentViewerPath } from "../../lib/documentViewer";
import { useAppContext } from "../../app/AppContext";
import { atifKaliteEtiketi, destekSeviyesiEtiketi, modelProfilEtiketi } from "../../lib/labels";
import { getModelProfiles, reviewCitations, searchMatter } from "../../services/lawcopilotApi";
import type { Citation, CitationReviewResponse, SearchResponse } from "../../types/domain";
import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";
import { CitationList } from "../citations/CitationList";

function citationKey(citation: Citation) {
  return `${citation.document_id}-${citation.chunk_id ?? citation.chunk_index ?? citation.index}`;
}

export function SearchWorkbench({ matterId, heading = "Dosya araması" }: { matterId: number; heading?: string }) {
  const { settings } = useAppContext();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [citationReview, setCitationReview] = useState<CitationReviewResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [defaultProfile, setDefaultProfile] = useState("local");
  const [selectedCitationKey, setSelectedCitationKey] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getModelProfiles(settings)
      .then((response) => {
        if (active) {
          setDefaultProfile(response.default);
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [settings.baseUrl, settings.token]);

  useEffect(() => {
    if (result?.citations?.length) {
      setSelectedCitationKey(citationKey(result.citations[0]));
      return;
    }
    setSelectedCitationKey(null);
  }, [result]);

  const selectedCitation = useMemo(
    () => result?.citations.find((citation) => citationKey(citation) === selectedCitationKey) ?? null,
    [result, selectedCitationKey],
  );

  async function handleSearch() {
    setIsSubmitting(true);
    try {
      const response = await searchMatter(settings, matterId, {
        query,
        limit: 5
      });
      setResult(response);
      setError("");
      setCitationReview(null);
      if (response.answer) {
        reviewCitations(settings, { answer: response.answer })
          .then((review) => setCitationReview(review))
          .catch(() => undefined);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Arama yapılamadı.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="stack">
      <SectionCard title={heading} subtitle="Arama yalnız geçerli dosya içinde çalışır. Her öneriden önce belge dayanaklarını inceleyin.">
        <div className="field-grid">
          <label className="stack stack--tight">
            <span>Arama sorgusu</span>
            <textarea
              className="textarea"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Örneğin: risk noktaları, zaman çizelgesi ipuçları, belge dayanaklı cevaplar"
            />
          </label>
          <div className="toolbar">
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <StatusBadge tone="accent">Dosya kapsamı</StatusBadge>
              <StatusBadge>{modelProfilEtiketi(defaultProfile)}</StatusBadge>
            </div>
            <button className="button" disabled={!query.trim() || isSubmitting} onClick={handleSearch} type="button">
              {isSubmitting ? "Aranıyor..." : "Aramayı çalıştır"}
            </button>
          </div>
          {error ? <p style={{ color: "var(--danger)", margin: 0 }}>{error}</p> : null}
        </div>
      </SectionCard>

      {result ? (
        <>
          <SectionCard
            title="Arama özeti"
            subtitle="Yapay çıktı, dayanak pasajlar ve inceleme uyarıları bilinçli olarak ayrı gösterilir."
            actions={
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <StatusBadge tone={result.support_level === "high" ? "accent" : result.support_level === "medium" ? "warning" : "danger"}>
                  {destekSeviyesiEtiketi(result.support_level)}
                </StatusBadge>
                <StatusBadge tone={result.manual_review_required ? "warning" : "accent"}>
                  {result.manual_review_required ? "İnceleme gerekli" : "Kaynak dayanaklı"}
                </StatusBadge>
              </div>
            }
          >
            <div className="callout callout--accent">
              <strong>Kısa cevap</strong>
              <p style={{ marginBottom: 0, lineHeight: 1.6 }}>{result.answer}</p>
            </div>
            <div className="metric-grid" style={{ marginTop: "1rem" }}>
              <div className="metric-card">
                <div className="metric-card__label">Alıntı</div>
                <div className="metric-card__value">{result.citation_count}</div>
              </div>
              <div className="metric-card">
                <div className="metric-card__label">Kapsama</div>
                <div className="metric-card__value">{result.source_coverage}</div>
              </div>
              {citationReview ? (
                <div className="metric-card">
                  <div className="metric-card__label">Kaynak kalitesi</div>
                  <div className="metric-card__value">
                    <StatusBadge tone={citationReview.grade === "A" ? "accent" : citationReview.grade === "B" ? "warning" : "danger"}>
                      {atifKaliteEtiketi(citationReview.grade)}
                    </StatusBadge>
                  </div>
                </div>
              ) : null}
            </div>
            {citationReview?.recommendations?.length ? (
              <div className="callout" style={{ marginTop: "1rem" }}>
                <strong>Kaynak önerileri</strong>
                <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
                  {citationReview.recommendations.map((rec, i) => (
                    <li key={i} style={{ lineHeight: 1.6 }}>{rec}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Destekleyici alıntılar" subtitle="Belge pasajları, asistan özetinden ayrı tutulur.">
            <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "minmax(0, 1.4fr) minmax(280px, 1fr)" }}>
              <CitationList
                citations={result.citations}
                resolveTarget={(citation) => buildCitationTarget(citation, "matter", matterId)}
                onSelectCitation={(citation) => setSelectedCitationKey(citationKey(citation))}
                selectedCitationKey={selectedCitationKey}
              />
              <aside className="stack stack--tight" style={{ alignSelf: "start", position: "sticky", top: "1rem" }}>
                <div className="section-card" style={{ margin: 0 }}>
                  <div className="section-card__header" style={{ marginBottom: "0.5rem" }}>
                    <div>
                      <h3 style={{ margin: 0 }}>Kaynak önizleme</h3>
                      <p style={{ margin: "0.25rem 0 0", color: "var(--text-muted)" }}>
                        Alıntı detayını kontrol edip tek tıkla ilgili dosyaya geçin.
                      </p>
                    </div>
                  </div>
                  {selectedCitation ? (
                    <div className="stack stack--tight">
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                        <StatusBadge tone="accent">{selectedCitation.document_name}</StatusBadge>
                        <StatusBadge tone={selectedCitation.confidence === "high" ? "accent" : selectedCitation.confidence === "medium" ? "warning" : "danger"}>
                          Güven: {selectedCitation.confidence}
                        </StatusBadge>
                      </div>
                      <p className="list-item__meta" style={{ margin: 0 }}>
                        Parça #{(selectedCitation.chunk_index ?? 0) + 1}
                        {selectedCitation.line_anchor ? ` · ${selectedCitation.line_anchor}` : ""}
                        {selectedCitation.page ? ` · Sayfa ${selectedCitation.page}` : ""}
                      </p>
                      <blockquote style={{ margin: 0, padding: "0.75rem", borderLeft: "3px solid var(--accent-600)", background: "var(--surface-muted)", borderRadius: "0.5rem", lineHeight: 1.6 }}>
                        {selectedCitation.excerpt}
                      </blockquote>
                      <button
                        className="button"
                        onClick={() => {
                          const target = buildCitationTarget(selectedCitation, "matter", matterId);
                          navigate(buildDocumentViewerPath(target));
                        }}
                        type="button"
                      >
                        Dosyaya git
                      </button>
                    </div>
                  ) : (
                    <p style={{ margin: 0, color: "var(--text-muted)" }}>Soldaki listeden bir alıntı seçin.</p>
                  )}
                </div>
              </aside>
            </div>
          </SectionCard>

          <SectionCard title="İlgili belgeler" subtitle="Bu aramayla en yakın ilişkili dosya içi kaynaklar.">
            {result.related_documents.length ? (
              <div className="list">
                {result.related_documents.map((document) => (
                  <article className="list-item" key={document.document_id}>
                    <div className="toolbar">
                      <h3 className="list-item__title">{document.document_name}</h3>
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                        <StatusBadge tone="accent">Skor {document.max_score}</StatusBadge>
                        <button
                          className="button button--ghost"
                          onClick={() =>
                            navigate(
                              buildDocumentViewerPath({
                                scope: "matter",
                                documentId: document.document_id,
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
                    <p className="list-item__meta">{document.reason}</p>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState title="İlgili belge yok" description="Arama yeterli dayanak bulduğunda ilgili belge sinyalleri burada görünür." />
            )}
          </SectionCard>
        </>
      ) : (
        <EmptyState title="Geçerli dosyada arama yapın" description="Kaynak dayanaklı cevap ve alıntıları görmek için dosya kapsamlı sorgu çalıştırın." />
      )}
    </div>
  );
}
