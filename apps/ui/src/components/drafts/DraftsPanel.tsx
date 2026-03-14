import { useEffect, useMemo, useState } from "react";

import { useAppContext } from "../../app/AppContext";
import { resolveSourceDocumentReferences } from "../../lib/documentViewer";
import { kanalEtiketi, sistemKaynagiEtiketi, taslakTipiEtiketi, uretimDurumuEtiketi } from "../../lib/labels";
import { createMatterDraft, generateMatterDraft, listMatterDocuments, listMatterDrafts, listMatterWorkspaceDocuments } from "../../services/lawcopilotApi";
import type { Draft, MatterDocument, MatterWorkspaceDocumentLink } from "../../types/domain";
import { DocumentReferenceLinks } from "../documents/DocumentReferenceLinks";
import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";

export function DraftsPanel({ matterId, matterLabel }: { matterId: number; matterLabel: string }) {
  const { settings } = useAppContext();
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [matterDocuments, setMatterDocuments] = useState<MatterDocument[]>([]);
  const [workspaceDocuments, setWorkspaceDocuments] = useState<MatterWorkspaceDocumentLink[]>([]);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reviewMessage, setReviewMessage] = useState("");

  useEffect(() => {
    Promise.all([
      listMatterDrafts(settings, matterId),
      listMatterDocuments(settings, matterId),
      listMatterWorkspaceDocuments(settings, matterId),
    ])
      .then(([draftResponse, documentResponse, workspaceResponse]) => {
        setDrafts(draftResponse.items);
        setMatterDocuments(documentResponse.items);
        setWorkspaceDocuments(workspaceResponse.items);
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

  async function handleSubmit(formData: FormData) {
    setIsSubmitting(true);
    try {
      const draft = await createMatterDraft(settings, matterId, {
        draft_type: String(formData.get("draftType") || "client_update"),
        title: String(formData.get("title") || ""),
        body: String(formData.get("body") || ""),
        target_channel: String(formData.get("targetChannel") || "internal"),
        to_contact: String(formData.get("toContact") || "")
      });
      setDrafts((prev) => [draft, ...prev]);
      setError("");
      setReviewMessage("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Taslak oluşturulamadı.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleGenerate(formData: FormData) {
    setIsSubmitting(true);
    try {
      const response = await generateMatterDraft(settings, matterId, {
        draft_type: String(formData.get("generateDraftType") || "client_update"),
        target_channel: String(formData.get("generateTargetChannel") || "internal"),
        to_contact: String(formData.get("generateToContact") || ""),
        instructions: String(formData.get("generateInstructions") || "")
      });
      setDrafts((prev) => [response.draft, ...prev]);
      setReviewMessage(response.review_message);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Taslak üretilemedi.");
      setReviewMessage("");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="stack">
      <SectionCard title="Taslak inceleme" subtitle="Taslaklar dosyaya bağlı tutulur ve dış kullanımdan önce açıkça inceleme ister.">
        <div className="callout callout--accent">
          <strong>Göndermeden önce inceleyin</strong>
          <p style={{ marginBottom: 0 }}>
            Aşağıdaki taslaklar nihai kayıt değildir. <strong>{matterLabel}</strong> dosyasına bağlı çalışma çıktılarıdır ve dış kullanımdan önce gözden geçirilmelidir.
          </p>
        </div>
        <form
          className="field-grid"
          style={{ marginTop: "1rem" }}
          onSubmit={(event) => {
            event.preventDefault();
            handleGenerate(new FormData(event.currentTarget));
            event.currentTarget.reset();
          }}
        >
          <div className="field-grid field-grid--two">
            <label className="stack stack--tight">
              <span>Üretilecek taslak türü</span>
              <select className="select" name="generateDraftType" defaultValue="client_update">
                <option value="client_update">Müvekkil durum güncellemesi</option>
                <option value="internal_summary">İç ekip özeti</option>
                <option value="first_case_assessment">İlk dosya değerlendirmesi</option>
                <option value="missing_document_request">Belge talep listesi</option>
                <option value="meeting_summary">Toplantı özeti</option>
                <option value="question_list">Soru listesi</option>
              </select>
            </label>
            <label className="stack stack--tight">
              <span>Hedef kanal</span>
              <select className="select" name="generateTargetChannel" defaultValue="internal">
                <option value="internal">İç kullanım</option>
                <option value="email">E-posta</option>
                <option value="client_portal">Müvekkil portalı</option>
              </select>
            </label>
          </div>
          <label className="stack stack--tight">
            <span>İnceleyici notu</span>
            <textarea className="textarea" name="generateInstructions" placeholder="Üretilecek çalışma taslağı için ek yönlendirme" />
          </label>
          <label className="stack stack--tight">
            <span>Alıcı veya kişi bilgisi</span>
            <input className="input" name="generateToContact" placeholder="İsteğe bağlı kişi veya referans" />
          </label>
          <div className="toolbar">
            <span style={{ color: "var(--text-muted)" }}>Üretim sırasında kronoloji, risk notları, indekslenmiş belgeler ve açık görevler bağlam olarak kullanılır.</span>
            <button className="button button--secondary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Üretiliyor..." : "Dosyadan üret"}
            </button>
          </div>
        </form>
        {reviewMessage ? <p style={{ color: "var(--accent)", marginTop: "1rem" }}>{reviewMessage}</p> : null}
        <form
          className="field-grid"
          style={{ marginTop: "1rem" }}
          onSubmit={(event) => {
            event.preventDefault();
            handleSubmit(new FormData(event.currentTarget));
            event.currentTarget.reset();
          }}
        >
          <div className="field-grid field-grid--two">
            <label className="stack stack--tight">
              <span>Taslak türü</span>
              <select className="select" name="draftType" defaultValue="client_update">
                <option value="client_update">Müvekkil durum güncellemesi</option>
                <option value="internal_summary">İç ekip özeti</option>
                <option value="first_case_assessment">İlk dosya değerlendirmesi</option>
                <option value="missing_document_request">Belge talep listesi</option>
                <option value="meeting_summary">Toplantı özeti</option>
                <option value="question_list">Soru listesi</option>
              </select>
            </label>
            <label className="stack stack--tight">
              <span>Hedef kanal</span>
              <select className="select" name="targetChannel" defaultValue="internal">
                <option value="internal">İç kullanım</option>
                <option value="email">E-posta</option>
                <option value="client_portal">Müvekkil portalı</option>
              </select>
            </label>
          </div>
          <label className="stack stack--tight">
            <span>Taslak başlığı</span>
            <input className="input" name="title" placeholder="Müvekkil güncellemesi, belge talebi, toplantı özeti" required />
          </label>
          <label className="stack stack--tight">
            <span>Alıcı veya kişi bilgisi</span>
            <input className="input" name="toContact" placeholder="İsteğe bağlı kişi veya referans" />
          </label>
          <label className="stack stack--tight">
            <span>Taslak metni</span>
            <textarea className="textarea" name="body" placeholder="Çalışma taslağını buraya yazın veya yapıştırın" required />
          </label>
          <div className="toolbar">
            <span style={{ color: "var(--text-muted)" }}>Taslaklar öneridir; nihai müvekkil iletişimi değildir.</span>
            <button className="button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Kaydediliyor..." : "Taslak oluştur"}
            </button>
          </div>
        </form>
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      </SectionCard>

      <SectionCard title="Taslak kuyruğu" subtitle="Hukuki inceleme bekleyen dosya bağlı taslaklar.">
        {drafts.length ? (
          <div className="list">
            {drafts.map((draft) => (
              <article className="list-item" key={draft.id}>
                <div className="toolbar">
                  <h3 className="list-item__title">{draft.title}</h3>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <StatusBadge tone="warning">{taslakTipiEtiketi(draft.draft_type)}</StatusBadge>
                    <StatusBadge>{kanalEtiketi(draft.target_channel)}</StatusBadge>
                    <StatusBadge tone="accent">{draft.status}</StatusBadge>
                    {draft.generated_from ? <StatusBadge>{sistemKaynagiEtiketi(draft.generated_from)}</StatusBadge> : null}
                    {draft.generated_from ? <StatusBadge>{uretimDurumuEtiketi(draft.generated_from)}</StatusBadge> : null}
                    {draft.manual_review_required ? <StatusBadge tone="warning">İnceleme gerekli</StatusBadge> : null}
                  </div>
                </div>
                <p className="list-item__meta">
                  Dosya: {matterLabel} · Oluşturulma: {new Date(draft.created_at).toLocaleString("tr-TR")}
                </p>
                <p style={{ marginBottom: 0, lineHeight: 1.6 }}>{draft.body.slice(0, 240)}</p>
                {draft.source_context ? (
                  <div className="callout" style={{ marginTop: "0.75rem" }}>
                    <strong>Kaynak bağlamı</strong>
                    {draft.source_context.documents?.length ? <p style={{ marginBottom: "0.25rem" }}>Belgeler: {draft.source_context.documents.join(" | ")}</p> : null}
                    {draft.source_context.chronology?.length ? <p style={{ marginBottom: "0.25rem" }}>Kronoloji: {draft.source_context.chronology.join(" | ")}</p> : null}
                    {draft.source_context.risk_notes?.length ? <p style={{ marginBottom: "0.25rem" }}>Risk notları: {draft.source_context.risk_notes.join(" | ")}</p> : null}
                    <DocumentReferenceLinks
                      refs={resolveSourceDocumentReferences(
                        draft.source_context.documents || [],
                        sourceLookup.matterDocuments,
                        sourceLookup.workspaceDocuments,
                        matterId,
                      )}
                      buttonLabel="Belgeyi incele"
                    />
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz taslak yok" description="Bu dosyaya bağlı ilk gözden geçirilebilir taslağı oluşturun." />
        )}
      </SectionCard>
    </div>
  );
}
