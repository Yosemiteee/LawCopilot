import { useEffect, useState } from "react";

import { useAppContext } from "../../app/AppContext";
import { notTipiEtiketi } from "../../lib/labels";
import { createMatterNote, listMatterTimeline } from "../../services/lawcopilotApi";
import type { MatterNote, TimelineEvent } from "../../types/domain";
import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";

export function MatterNotesPanel({ matterId }: { matterId: number }) {
  const { settings } = useAppContext();
  const [notes, setNotes] = useState<MatterNote[]>([]);
  const [timelineNotes, setTimelineNotes] = useState<TimelineEvent[]>([]);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    listMatterTimeline(settings, matterId)
      .then((response) => {
        const noteEvents = response.items.filter(
          (event) => event.event_type === "note_added"
        );
        setTimelineNotes(noteEvents);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token, matterId]);

  async function handleSubmit(formData: FormData) {
    setIsSubmitting(true);
    try {
      const note = await createMatterNote(settings, matterId, {
        body: String(formData.get("body") || ""),
        note_type: String(formData.get("noteType") || "working_note"),
        event_at: String(formData.get("eventAt") || "") || undefined,
      });
      setNotes((prev) => [note, ...prev]);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Not oluşturulamadı.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const allNotes = [
    ...notes.map((note) => ({
      id: `note-${note.id}`,
      body: note.body,
      note_type: note.note_type,
      created_at: note.created_at,
      created_by: note.created_by,
    })),
    ...timelineNotes.map((event) => ({
      id: `timeline-${event.id}`,
      body: event.details || event.title,
      note_type: "working_note",
      created_at: event.event_at,
      created_by: event.created_by || "",
    })),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  return (
    <div className="stack">
      <SectionCard
        title="Not ekle"
        subtitle="Notlar dosya bağlamında saklanır ve zaman çizelgesine yansır."
      >
        <form
          className="field-grid"
          onSubmit={(event) => {
            event.preventDefault();
            handleSubmit(new FormData(event.currentTarget));
            event.currentTarget.reset();
          }}
        >
          <div className="field-grid field-grid--two">
            <label className="stack stack--tight">
              <span>Not türü</span>
              <select className="select" name="noteType" defaultValue="working_note">
                <option value="working_note">Çalışma notu</option>
                <option value="client_note">Müvekkil notu</option>
                <option value="internal_note">İç not</option>
                <option value="risk_note">Risk notu</option>
              </select>
            </label>
            <label className="stack stack--tight">
              <span>Olay tarihi (isteğe bağlı)</span>
              <input
                className="input"
                name="eventAt"
                type="datetime-local"
              />
            </label>
          </div>
          <label className="stack stack--tight">
            <span>Not içeriği</span>
            <textarea
              className="textarea"
              name="body"
              placeholder="Eksik belge notu, toplantı özeti, müvekkil talimatları..."
              required
            />
          </label>
          <div className="toolbar">
            <span style={{ color: "var(--text-muted)" }}>
              Notlar, zaman çizelgesi ve risk değerlendirmelerinin girdisidir.
            </span>
            <button className="button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Kaydediliyor..." : "Notu kaydet"}
            </button>
          </div>
        </form>
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      </SectionCard>

      <SectionCard
        title="Dosya notları"
        subtitle="Bu dosyaya eklenen tüm notlar oluşturulma tarihine göre sıralanır."
      >
        {allNotes.length ? (
          <div className="list">
            {allNotes.map((note) => (
              <article className="list-item" key={note.id}>
                <div className="toolbar">
                  <h3 className="list-item__title">
                    {note.body.slice(0, 120)}
                    {note.body.length > 120 ? "…" : ""}
                  </h3>
                  <StatusBadge tone="accent">
                    {notTipiEtiketi(note.note_type)}
                  </StatusBadge>
                </div>
                <p style={{ marginBottom: "0.5rem", lineHeight: 1.6 }}>
                  {note.body}
                </p>
                <p className="list-item__meta">
                  {new Date(note.created_at).toLocaleString("tr-TR")}
                  {note.created_by ? ` · ${note.created_by}` : ""}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Henüz not eklenmedi"
            description="Dosyaya ilk notu ekleyerek çalışma notlarını kayıt altına alın."
          />
        )}
      </SectionCard>
    </div>
  );
}
