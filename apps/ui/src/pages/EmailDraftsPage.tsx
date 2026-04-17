import { useEffect, useState } from "react";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { epostaTaslakDurumuEtiketi } from "../lib/labels";
import {
  approveEmailDraft,
  createEmailDraft,
  emailDraftHistory,
  listEmailDrafts,
  previewEmailDraft,
  retractEmailDraft,
} from "../services/lawcopilotApi";
import type { EmailDraft, EmailDraftEvent, EmailDraftPreview } from "../types/domain";

export function EmailDraftsPage() {
  const { settings } = useAppContext();
  const [drafts, setDrafts] = useState<EmailDraft[]>([]);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [preview, setPreview] = useState<EmailDraftPreview | null>(null);
  const [history, setHistory] = useState<{ draft: EmailDraft; events: EmailDraftEvent[] } | null>(null);

  useEffect(() => {
    listEmailDrafts(settings)
      .then((response) => {
        setDrafts(response.items);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token]);

  async function handleCreate(formData: FormData) {
    setIsSubmitting(true);
    try {
      const draft = await createEmailDraft(settings, {
        to_email: String(formData.get("toEmail") || ""),
        subject: String(formData.get("subject") || ""),
        body: String(formData.get("body") || ""),
      });
      setDrafts((prev) => [draft, ...prev]);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Taslak oluşturulamadı.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleApprove(draftId: number) {
    try {
      const result = await approveEmailDraft(settings, draftId);
      setDrafts((prev) =>
        prev.map((draft) => (draft.id === draftId ? result.draft : draft))
      );
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Onay başarısız.");
    }
  }

  async function handleRetract(draftId: number) {
    const reason = window.prompt("Geri çekme nedeni (isteğe bağlı):");
    try {
      const result = await retractEmailDraft(settings, draftId, reason || undefined);
      setDrafts((prev) =>
        prev.map((draft) => (draft.id === draftId ? result.draft : draft))
      );
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Geri çekme başarısız.");
    }
  }

  async function handlePreview(draftId: number) {
    try {
      const data = await previewEmailDraft(settings, draftId);
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Önizleme yüklenemedi.");
    }
  }

  async function handleHistory(draftId: number) {
    try {
      const data = await emailDraftHistory(settings, draftId);
      setHistory(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tarihçe yüklenemedi.");
    }
  }

  function statusTone(status: string): "accent" | "warning" | "danger" {
    switch (status) {
      case "approved":
        return "accent";
      case "retracted":
        return "danger";
      default:
        return "warning";
    }
  }

  return (
    <div className="page-grid page-grid--split">
      <div className="stack">
        <SectionCard
          title="E-posta taslakları"
          subtitle="Avukatlar oluşturur, yöneticiler onaylar veya geri çeker. Otomatik gönderim devre dışıdır."
        >
          <div className="callout callout--accent">
            <strong>Onay akışı</strong>
            <p style={{ marginBottom: 0 }}>
              Taslak → İnceleme → Onay / Geri çekme. E-postalar
              onaylanmadan gönderilmez.
            </p>
          </div>
          {drafts.length ? (
            <div className="list" style={{ marginTop: "1rem" }}>
              {drafts.map((draft) => (
                <article className="list-item" key={draft.id}>
                  <div className="toolbar">
                    <h3 className="list-item__title">{draft.subject}</h3>
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      <StatusBadge tone={statusTone(draft.status)}>
                        {epostaTaslakDurumuEtiketi(draft.status)}
                      </StatusBadge>
                    </div>
                  </div>
                  <p className="list-item__meta">
                    Alıcı: {draft.to_email} · Talep eden: {draft.requested_by} ·{" "}
                    {new Date(draft.created_at).toLocaleString("tr-TR")}
                  </p>
                  <p style={{ marginBottom: "0.75rem", lineHeight: 1.6 }}>
                    {draft.body.slice(0, 200)}
                    {draft.body.length > 200 ? "…" : ""}
                  </p>
                  <div className="toolbar">
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        className="button button--ghost"
                        type="button"
                        onClick={() => handlePreview(draft.id)}
                        style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }}
                      >
                        Önizle
                      </button>
                      <button
                        className="button button--ghost"
                        type="button"
                        onClick={() => handleHistory(draft.id)}
                        style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }}
                      >
                        Tarihçe
                      </button>
                    </div>
                    {draft.status === "draft" ? (
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <button
                          className="button"
                          type="button"
                          onClick={() => handleApprove(draft.id)}
                          style={{ padding: "0.5rem 1rem", fontSize: "0.85rem" }}
                        >
                          Onayla
                        </button>
                        <button
                          className="button button--secondary"
                          type="button"
                          onClick={() => handleRetract(draft.id)}
                          style={{ padding: "0.5rem 1rem", fontSize: "0.85rem" }}
                        >
                          Geri çek
                        </button>
                      </div>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Henüz e-posta taslağı yok"
              description="Yeni bir e-posta taslağı oluşturarak müvekkil iletişim akışını başlatın."
            />
          )}
          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
        </SectionCard>

        {preview ? (
          <SectionCard title="Taslak önizleme" subtitle="İçerik gönderilmeden önceki son haline bakılır.">
            <div className="stack">
              <div className="callout">
                <strong>{preview.subject}</strong>
                <p style={{ marginBottom: "0.5rem" }}>Alıcı: {preview.to_email}</p>
                <p style={{ marginBottom: 0 }}>{preview.body_preview}</p>
              </div>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <StatusBadge tone={statusTone(preview.status)}>
                  {epostaTaslakDurumuEtiketi(preview.status)}
                </StatusBadge>
                <StatusBadge>{`${preview.body_words} kelime`}</StatusBadge>
                <StatusBadge>{`${preview.body_chars} karakter`}</StatusBadge>
              </div>
              <button
                className="button button--ghost"
                type="button"
                onClick={() => setPreview(null)}
                style={{ justifySelf: "end" }}
              >
                Kapat
              </button>
            </div>
          </SectionCard>
        ) : null}

        {history ? (
          <SectionCard title="Taslak tarihçesi" subtitle="Taslağın oluşturulma, onay ve geri çekme akışı.">
            <div className="list">
              {history.events.map((event) => (
                <article className="list-item" key={event.id}>
                  <div className="toolbar">
                    <h3 className="list-item__title">{event.event_type}</h3>
                    <StatusBadge>{event.actor}</StatusBadge>
                  </div>
                  <p className="list-item__meta">
                    {new Date(event.created_at).toLocaleString("tr-TR")}
                    {event.details ? ` · ${event.details}` : ""}
                  </p>
                </article>
              ))}
            </div>
            <button
              className="button button--ghost"
              type="button"
              onClick={() => setHistory(null)}
              style={{ marginTop: "0.75rem" }}
            >
              Kapat
            </button>
          </SectionCard>
        ) : null}
      </div>

      <SectionCard title="Yeni e-posta taslağı" subtitle="Taslak oluştur ve onay gönder." className="sticky-panel">
        <form
          className="field-grid"
          onSubmit={(event) => {
            event.preventDefault();
            handleCreate(new FormData(event.currentTarget));
            event.currentTarget.reset();
          }}
        >
          <label className="stack stack--tight">
            <span>Alıcı e-posta</span>
            <input
              className="input"
              name="toEmail"
              type="email"
              placeholder="muvekkil@example.com"
              required
            />
          </label>
          <label className="stack stack--tight">
            <span>Konu</span>
            <input
              className="input"
              name="subject"
              placeholder="Dosya güncellemesi, belge talep listesi"
              required
            />
          </label>
          <label className="stack stack--tight">
            <span>İçerik</span>
            <textarea
              className="textarea"
              name="body"
              placeholder="E-posta gövdesi"
              required
            />
          </label>
          <div className="toolbar">
            <span style={{ color: "var(--text-muted)" }}>
              E-postalar otomatik gönderilmez; onay akışına girer.
            </span>
            <button className="button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Oluşturuluyor..." : "Taslak oluştur"}
            </button>
          </div>
        </form>
      </SectionCard>
    </div>
  );
}
