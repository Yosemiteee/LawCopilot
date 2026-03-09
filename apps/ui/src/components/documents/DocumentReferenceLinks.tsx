import { useNavigate } from "react-router-dom";

import { buildDocumentViewerPath, type DocumentReference } from "../../lib/documentViewer";

export function DocumentReferenceLinks({ refs, buttonLabel = "Belgeyi incele" }: { refs: DocumentReference[]; buttonLabel?: string }) {
  const navigate = useNavigate();

  if (!refs.length) {
    return null;
  }

  return (
    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
      {refs.map((ref) => (
        <button
          className="button button--ghost"
          key={`${ref.target.scope}-${ref.target.documentId}`}
          onClick={() => navigate(buildDocumentViewerPath(ref.target))}
          type="button"
        >
          {buttonLabel}: {ref.label}
        </button>
      ))}
    </div>
  );
}
