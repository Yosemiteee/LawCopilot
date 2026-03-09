import { useNavigate } from "react-router-dom";

import { buildDocumentViewerPath, type DocumentViewerTarget } from "../../lib/documentViewer";
import type { Citation } from "../../types/domain";
import { guvenEtiketi, kaynakTipiEtiketi } from "../../lib/labels";
import { EmptyState } from "../common/EmptyState";
import { StatusBadge } from "../common/StatusBadge";

export function CitationList({
  citations,
  resolveTarget,
}: {
  citations: Citation[];
  resolveTarget?: (citation: Citation) => DocumentViewerTarget | null;
}) {
  const navigate = useNavigate();

  if (!citations.length) {
    return <EmptyState title="Alıntı yok" description="Bu sonuç için destekleyici pasaj dönmedi." />;
  }

  return (
    <div className="list">
      {citations.map((citation) => (
        <article className="list-item" key={`${citation.document_id}-${citation.chunk_id ?? citation.chunk_index ?? citation.index}`}>
          <div className="toolbar">
            <h3 className="list-item__title">{citation.document_name}</h3>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {citation.label ? <StatusBadge tone="accent">{citation.label}</StatusBadge> : null}
              <StatusBadge tone={citation.confidence === "high" ? "accent" : citation.confidence === "medium" ? "warning" : "danger"}>
                {guvenEtiketi(citation.confidence)}
              </StatusBadge>
              <StatusBadge>{kaynakTipiEtiketi(citation.source_type)}</StatusBadge>
            </div>
          </div>
          <p className="list-item__meta">
            Parça #{(citation.chunk_index ?? 0) + 1}
            {citation.line_anchor ? ` · ${citation.line_anchor}` : ""}
            {citation.page ? ` · Sayfa ${citation.page}` : ""}
          </p>
          <p style={{ marginBottom: 0, lineHeight: 1.6 }}>{citation.excerpt}</p>
          {resolveTarget ? (
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
              <button
                className="button button--ghost"
                onClick={() => {
                  const target = resolveTarget(citation);
                  if (target) {
                    navigate(buildDocumentViewerPath(target));
                  }
                }}
                type="button"
              >
                Belgedeki yeri aç
              </button>
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}
