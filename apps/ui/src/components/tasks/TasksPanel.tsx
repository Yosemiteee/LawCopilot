import { useEffect, useState } from "react";

import { useAppContext } from "../../app/AppContext";
import { gorevDurumuEtiketi, oncelikEtiketi, sistemKaynagiEtiketi } from "../../lib/labels";
import { createMatterTask, getMatterTaskRecommendations, listMatterTasks } from "../../services/lawcopilotApi";
import type { Task, TaskRecommendation } from "../../types/domain";
import { EmptyState } from "../common/EmptyState";
import { SectionCard } from "../common/SectionCard";
import { StatusBadge } from "../common/StatusBadge";

export function TasksPanel({ matterId }: { matterId: number }) {
  const { settings } = useAppContext();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [recommendations, setRecommendations] = useState<TaskRecommendation[]>([]);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    Promise.all([listMatterTasks(settings, matterId), getMatterTaskRecommendations(settings, matterId)])
      .then(([tasksResponse, recommendationResponse]) => {
        setTasks(tasksResponse.items);
        setRecommendations(recommendationResponse.items);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token, matterId]);

  async function createTask(formData: FormData) {
    setIsSubmitting(true);
    try {
      const task = await createMatterTask(settings, matterId, {
        title: String(formData.get("title") || ""),
        priority: String(formData.get("priority") || "medium"),
        due_at: String(formData.get("dueAt") || "") || undefined,
        explanation: String(formData.get("explanation") || "") || undefined
      });
      setTasks((prev) => [task, ...prev]);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Görev oluşturulamadı.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function createFromRecommendation(recommendation: TaskRecommendation) {
    setIsSubmitting(true);
    try {
      const task = await createMatterTask(settings, matterId, {
        title: recommendation.title,
        priority: recommendation.priority,
        due_at: recommendation.due_at || undefined,
        explanation: recommendation.explanation,
        origin_type: recommendation.origin_type,
        recommended_by: recommendation.recommended_by
      });
      setTasks((prev) => [task, ...prev]);
      setRecommendations((prev) => prev.filter((item) => item.title !== recommendation.title));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Öneri görevleştirilemedi.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="stack">
      <SectionCard title="Önerilen görevler" subtitle="Bunlar açıklanabilir önerilerdir; biri inceleyip oluşturana kadar nihai aksiyon değildir.">
        {recommendations.length ? (
          <div className="list">
            {recommendations.map((recommendation) => (
              <article className="list-item" key={recommendation.title}>
                <div className="toolbar">
                  <h3 className="list-item__title">{recommendation.title}</h3>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <StatusBadge tone={recommendation.priority === "high" ? "danger" : recommendation.priority === "medium" ? "warning" : "accent"}>
                      {oncelikEtiketi(recommendation.priority)}
                    </StatusBadge>
                    <StatusBadge>{sistemKaynagiEtiketi(recommendation.recommended_by)}</StatusBadge>
                  </div>
                </div>
                <p style={{ marginBottom: "0.5rem", lineHeight: 1.6 }}>{recommendation.explanation}</p>
                <p className="list-item__meta">
                  Sinyaller: {recommendation.signals.join(", ")}
                  {recommendation.due_at ? ` · Önerilen tarih ${recommendation.due_at}` : ""}
                </p>
                <div className="toolbar" style={{ marginTop: "0.75rem" }}>
                  <span style={{ color: "var(--text-muted)" }}>Canlı göreve dönüşmeden önce insan incelemesi gerekir.</span>
                  <button className="button button--secondary" type="button" onClick={() => createFromRecommendation(recommendation)} disabled={isSubmitting}>
                    Öneriden görev oluştur
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Önerilen görev yok" description="Kronoloji, tarihler veya risk sinyalleri oluştuğunda takip görevleri önerilir." />
        )}
      </SectionCard>

      <SectionCard title="Dosya görevleri" subtitle="Görevler seçili dosyaya bağlı kalır; iş ve delil bağı aynı yerde tutulur.">
        <form
          className="field-grid field-grid--two"
          onSubmit={(event) => {
            event.preventDefault();
            createTask(new FormData(event.currentTarget));
            event.currentTarget.reset();
          }}
        >
          <label className="stack stack--tight">
            <span>Görev başlığı</span>
            <input className="input" name="title" placeholder="Eksik imzaları iste, tebliğ tarihini doğrula" required />
          </label>
          <label className="stack stack--tight">
            <span>Öncelik</span>
            <select className="select" name="priority" defaultValue="medium">
              <option value="high">Yüksek</option>
              <option value="medium">Orta</option>
              <option value="low">Düşük</option>
            </select>
          </label>
          <label className="stack stack--tight">
            <span>Son tarih</span>
            <input className="input" name="dueAt" placeholder="2026-03-20T09:00:00Z" />
          </label>
          <label className="stack stack--tight" style={{ gridColumn: "1 / -1" }}>
            <span>Neden önemli</span>
            <textarea className="textarea" name="explanation" placeholder="Bir sonraki inceleyici için kısa açıklama" />
          </label>
          <div style={{ gridColumn: "1 / -1" }} className="toolbar">
            <span style={{ color: "var(--text-muted)" }}>Görevler, yapay öneriler ve nihai dosya kayıtlarından açıkça ayrılır.</span>
            <button className="button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Kaydediliyor..." : "Görev ekle"}
            </button>
          </div>
        </form>
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      </SectionCard>

      <SectionCard title="Görev kuyruğu" subtitle="Bu dosyaya bağlı aktif iş listesi.">
        {tasks.length ? (
          <div className="list">
            {tasks.map((task) => (
              <article className="list-item" key={task.id}>
                <div className="toolbar">
                  <h3 className="list-item__title">{task.title}</h3>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <StatusBadge tone={task.priority === "high" ? "danger" : task.priority === "medium" ? "warning" : "accent"}>
                      {oncelikEtiketi(task.priority)}
                    </StatusBadge>
                    <StatusBadge>{gorevDurumuEtiketi(task.status)}</StatusBadge>
                    {task.recommended_by ? <StatusBadge tone="warning">{sistemKaynagiEtiketi(task.recommended_by)}</StatusBadge> : null}
                  </div>
                </div>
                <p className="list-item__meta">
                  {task.due_at ? `${new Date(task.due_at).toLocaleString("tr-TR")} · ` : ""}
                  {task.explanation || "Açıklama kaydı yok."}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz görev yok" description="Çalışma masasını sabitlemek için ilk görevi ekleyin." />
        )}
      </SectionCard>
    </div>
  );
}
