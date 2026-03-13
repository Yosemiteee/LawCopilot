import { useEffect, useMemo, useState } from "react";

import { useAppContext } from "../../app/AppContext";
import { resolveSourceDocumentReferences } from "../../lib/documentViewer";
import { oncelikEtiketi, riskKategoriEtiketi } from "../../lib/labels";
import { getMatterRiskNotes, listMatterDocuments, listMatterWorkspaceDocuments } from "../../services/lawcopilotApi";
import type { MatterDocument, MatterWorkspaceDocumentLink, RiskNote } from "../../types/domain";
import { DocumentReferenceLinks } from "../documents/DocumentReferenceLinks";
import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";

export function RiskNotesPanel({ matterId }: { matterId: number }) {
  const { settings } = useAppContext();
  const [items, setItems] = useState<RiskNote[]>([]);
  const [overview, setOverview] = useState("");
  const [matterDocuments, setMatterDocuments] = useState<MatterDocument[]>([]);
  const [workspaceDocuments, setWorkspaceDocuments] = useState<MatterWorkspaceDocumentLink[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      getMatterRiskNotes(settings, matterId),
      listMatterDocuments(settings, matterId),
      listMatterWorkspaceDocuments(settings, matterId),
    ])
      .then(([riskResponse, documentResponse, workspaceResponse]) => {
        setItems(riskResponse.items);
        setOverview(riskResponse.ai_overview || "");
        setMatterDocuments(documentResponse.items);
        setWorkspaceDocuments(workspaceResponse.items);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token, matterId]);

  const sourceLookup = useMemo(
    () => ({
      matterDocuments,
      workspaceDocuments,
    }),
    [matterDocuments, workspaceDocuments],
  );

  return (
    <SectionCard title="Risk notları" subtitle="Bunlar hukuki görüş değil; çalışma notu ve inceleme hatırlatmalarıdır.">
      {error ? (
        <p style={{ color: "var(--danger)" }}>{error}</p>
      ) : items.length ? (
        <div className="stack">
          {overview ? (
            <div className="callout callout--accent">
              <strong>Hızlı inceleme özeti</strong>
              <p style={{ marginBottom: 0, lineHeight: 1.6 }}>{overview}</p>
            </div>
          ) : null}
          <div className="list">
          {items.map((item, index) => (
            <article className="list-item" key={`${item.category}-${index}`}>
              <div className="toolbar">
                <h3 className="list-item__title">{item.title}</h3>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <StatusBadge tone={item.severity === "high" ? "danger" : item.severity === "medium" ? "warning" : "accent"}>
                    {oncelikEtiketi(item.severity)}
                  </StatusBadge>
                  <StatusBadge>{riskKategoriEtiketi(item.category)}</StatusBadge>
                </div>
              </div>
              <p style={{ marginBottom: "0.5rem", lineHeight: 1.6 }}>{item.details}</p>
              <p className="list-item__meta">
                Kaynaklar: {item.source_labels.join(", ") || "iş akışı motoru"} · İnsan incelemesi gerekir
              </p>
              <DocumentReferenceLinks
                refs={resolveSourceDocumentReferences(item.source_labels, sourceLookup.matterDocuments, sourceLookup.workspaceDocuments, matterId)}
                buttonLabel="Kaynağı aç"
              />
            </article>
          ))}
          </div>
        </div>
      ) : (
        <EmptyState title="Henüz risk notu yok" description="Eksik tarih, eksik belge, iddia dili veya süre baskısı görüldüğünde risk notu oluşur." />
      )}
    </SectionCard>
  );
}
