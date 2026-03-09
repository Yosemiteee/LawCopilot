import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { MetricCard } from "../components/common/MetricCard";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { dagitimKipiEtiketi, dosyaDurumuEtiketi, modelProfilEtiketi } from "../lib/labels";
import { getHealth, getModelProfiles, listMatters } from "../services/lawcopilotApi";
import type { Health, Matter, ModelProfilesResponse } from "../types/domain";

export function DashboardPage() {
  const { settings } = useAppContext();
  const [health, setHealth] = useState<Health | null>(null);
  const [profiles, setProfiles] = useState<ModelProfilesResponse | null>(null);
  const [matters, setMatters] = useState<Matter[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getHealth(settings), getModelProfiles(settings), listMatters(settings)])
      .then(([healthResponse, profileResponse, mattersResponse]) => {
        setHealth(healthResponse);
        setProfiles(profileResponse);
        setMatters(mattersResponse.items);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token]);

  return (
    <div className="page-grid">
      <SectionCard
        title="LawCopilot çalışma masası"
        subtitle="Avukatlar için dosya odaklı, kaynak dayanaklı ve denetlenebilir çalışma ortamı. Yapay özetler, alıntılar ve operasyon kayıtlarından ayrı tutulur."
      >
        <div className="metric-grid">
          <MetricCard label="Dosya sayısı" value={matters.length} />
          <MetricCard label="Çalışma modu" value={dagitimKipiEtiketi(health?.deployment_mode || settings.deploymentMode)} />
          <MetricCard label="Varsayılan model profili" value={modelProfilEtiketi(profiles?.default || "local")} />
        </div>
        {error ? <p style={{ color: "var(--danger)", marginBottom: 0 }}>{error}</p> : null}
      </SectionCard>

      <div className="page-grid page-grid--split">
        <SectionCard title="Son dosyalar" subtitle="Belgeler, görevler, aramalar ve taslaklar seçili dosya bağlamında tutulur.">
          {matters.length ? (
            <div className="list">
              {matters.slice(0, 5).map((matter) => (
                <Link className="list-item" key={matter.id} to={`/matters/${matter.id}`}>
                  <div className="toolbar">
                    <h3 className="list-item__title">{matter.title}</h3>
                    <StatusBadge tone="accent">{dosyaDurumuEtiketi(matter.status)}</StatusBadge>
                  </div>
                  <p className="list-item__meta">
                    {matter.practice_area || "Sınıflandırılmadı"} · {matter.reference_code || "Referans kodu yok"}
                  </p>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState title="Henüz dosya yok" description="Çalışma masasını kullanmaya başlamak için ilk dosyayı oluşturun." />
          )}
        </SectionCard>

        <SectionCard title="Güven duruşu" subtitle="Sistem, güven ve insan incelemesini hızdan önce koyar.">
          <div className="stack">
            <div className="callout callout--accent">
              <strong>Kaynak dayanaklı arama</strong>
              <p style={{ marginBottom: 0 }}>Arama yalnız seçili kapsam içinde çalışır; belge pasajları cevaplardan ayrı gösterilir.</p>
            </div>
            <div className="callout">
              <strong>Taslak öncelikli iletişim</strong>
              <p style={{ marginBottom: 0 }}>Taslaklar gözden geçirilebilir iş ürünüdür; otomatik gönderim varsayılan değildir.</p>
            </div>
            <div className="callout">
              <strong>Yerel gizlilik</strong>
              <p style={{ marginBottom: 0 }}>
                Etkin mod: <strong>{dagitimKipiEtiketi(health?.deployment_mode || settings.deploymentMode)}</strong>
              </p>
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
