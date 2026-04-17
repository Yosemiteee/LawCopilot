import { useEffect, useState } from "react";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { riskSkoruEtiketi, sosyalMedyaKaynakEtiketi } from "../lib/labels";
import { ingestSocialEvent, listSocialEvents } from "../services/lawcopilotApi";
import type { SocialEvent } from "../types/domain";

export function SocialMediaPage() {
  const { settings } = useAppContext();
  const [events, setEvents] = useState<SocialEvent[]>([]);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    listSocialEvents(settings, 50)
      .then((response) => {
        setEvents(response.items);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token]);

  async function handleSubmit(formData: FormData) {
    setIsSubmitting(true);
    try {
      const result = await ingestSocialEvent(settings, {
        source: String(formData.get("source") || "x"),
        handle: String(formData.get("handle") || ""),
        content: String(formData.get("content") || ""),
      });
      setEvents((prev) => [result.event, ...prev]);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Olay eklenemedi.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="page-grid page-grid--split">
      <SectionCard
        title="Sosyal medya izleme"
        subtitle="Dava ile ilgili sosyal medya paylaşımları risk skoruyla takip edilir. Salt okunur pipeline."
      >
        <div className="callout callout--accent">
          <strong>Salt okunur izleme</strong>
          <p style={{ marginBottom: 0 }}>
            Bu modül paylaşımları analiz eder ve risk skoru hesaplar. Hiçbir sosyal medya hesabına
            erişim veya otomatik eylem yapılmaz.
          </p>
        </div>
        {events.length ? (
          <div className="list" style={{ marginTop: "1rem" }}>
            {events.map((event) => {
              const risk = riskSkoruEtiketi(event.risk_score);
              return (
                <article className="list-item" key={event.id}>
                  <div className="toolbar">
                    <h3 className="list-item__title">{event.handle}</h3>
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      <StatusBadge>{sosyalMedyaKaynakEtiketi(event.source)}</StatusBadge>
                      <StatusBadge tone={risk.tone}>{risk.label}</StatusBadge>
                      <StatusBadge>{`Skor: ${(event.risk_score * 100).toFixed(0)}%`}</StatusBadge>
                    </div>
                  </div>
                  <p style={{ marginBottom: "0.5rem", lineHeight: 1.6 }}>
                    {event.content}
                  </p>
                  <p className="list-item__meta">
                    {new Date(event.created_at).toLocaleString("tr-TR")}
                  </p>
                </article>
              );
            })}
          </div>
        ) : (
          <EmptyState
            title="Henüz sosyal medya olayı yok"
            description="Takip edilecek bir paylaşım kaydı ekleyerek izlemeyi başlatın."
          />
        )}
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      </SectionCard>

      <SectionCard title="Sosyal medya paylaşımı ekle" subtitle="Dava ile ilgili paylaşımları kayıt altına alın." className="sticky-panel">
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
              <span>Kaynak</span>
              <select className="select" name="source" defaultValue="x">
                <option value="x">X (Twitter)</option>
                <option value="linkedin">LinkedIn</option>
                <option value="instagram">Instagram</option>
                <option value="news">Haber</option>
              </select>
            </label>
            <label className="stack stack--tight">
              <span>Hesap / Handle</span>
              <input className="input" name="handle" placeholder="@kullaniciadi" required />
            </label>
          </div>
          <label className="stack stack--tight">
            <span>Paylaşım içeriği</span>
            <textarea
              className="textarea"
              name="content"
              placeholder="Sosyal medya paylaşımının metni"
              required
            />
          </label>
          <div className="toolbar">
            <span style={{ color: "var(--text-muted)" }}>
              İçerik risk analizi otomatik yapılır; dava, mahkeme gibi terimler skoru artırır.
            </span>
            <button className="button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Kaydediliyor..." : "Paylaşımı kaydet"}
            </button>
          </div>
        </form>
      </SectionCard>
    </div>
  );
}
