import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { useAppContext } from "../app/AppContext";
import { dosyaDurumuEtiketi } from "../lib/labels";
import { createMatter, listMatters } from "../services/lawcopilotApi";
import type { Matter } from "../types/domain";

export function MattersPage() {
  const { settings } = useAppContext();
  const navigate = useNavigate();
  const [matters, setMatters] = useState<Matter[]>([]);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    listMatters(settings)
      .then((response) => {
        setMatters(response.items);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token]);

  async function handleCreate(formData: FormData) {
    setIsSubmitting(true);
    try {
      const matter = await createMatter(settings, {
        title: String(formData.get("title") || ""),
        reference_code: String(formData.get("referenceCode") || ""),
        practice_area: String(formData.get("practiceArea") || ""),
        client_name: String(formData.get("clientName") || ""),
        summary: String(formData.get("summary") || "")
      });
      setMatters((prev) => [matter, ...prev]);
      setError("");
      navigate(`/matters/${matter.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dosya oluşturulamadı.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="page-grid page-grid--split">
      <SectionCard title="Dosyalar" subtitle="Belgeler, görevler, aramalar ve taslaklar dosya bağlamında tutulur.">
        {matters.length ? (
          <div className="list">
            {matters.map((matter) => (
              <Link className="list-item" key={matter.id} to={`/matters/${matter.id}`}>
                <div className="toolbar">
                  <h3 className="list-item__title">{matter.title}</h3>
                  <StatusBadge tone="accent">{dosyaDurumuEtiketi(matter.status)}</StatusBadge>
                </div>
                <p className="list-item__meta">
                  {matter.client_name || "Müvekkil atanmadı"} · {matter.practice_area || "Çalışma alanı belirtilmedi"}
                </p>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz dosya oluşturulmadı" description="İlk dosyayı oluşturup belge ve görev akışını başlatın." />
        )}
      </SectionCard>

      <SectionCard title="Yeni dosya oluştur" subtitle="İlk kayıt hafif tutulur; ayrıntılar dosya ekranında zenginleştirilir.">
        <form
          className="field-grid"
          onSubmit={(event) => {
            event.preventDefault();
            handleCreate(new FormData(event.currentTarget));
            event.currentTarget.reset();
          }}
        >
          <label className="stack stack--tight">
            <span>Dosya başlığı</span>
            <input className="input" name="title" placeholder="Örneğin kira tahliye, işçilik alacağı, velayet incelemesi" required />
          </label>
          <div className="field-grid field-grid--two">
            <label className="stack stack--tight">
              <span>Referans kodu</span>
              <input className="input" name="referenceCode" placeholder="DOS-2026-042" />
            </label>
            <label className="stack stack--tight">
              <span>Çalışma alanı</span>
              <input className="input" name="practiceArea" placeholder="İş hukuku, kira, aile hukuku" />
            </label>
          </div>
          <label className="stack stack--tight">
            <span>Müvekkil adı</span>
            <input className="input" name="clientName" placeholder="Müvekkil veya kurum adı" />
          </label>
          <label className="stack stack--tight">
            <span>Açılış özeti</span>
            <textarea className="textarea" name="summary" placeholder="İlk değerlendirme notu veya intake özeti" />
          </label>
          <div className="toolbar">
            <span style={{ color: "var(--text-muted)" }}>Yeni dosya; arama, görev, taslak ve zaman çizelgesi için ortak bağlam olur.</span>
            <button className="button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Oluşturuluyor..." : "Dosyayı oluştur"}
            </button>
          </div>
        </form>
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      </SectionCard>
    </div>
  );
}
