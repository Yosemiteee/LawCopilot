import { useEffect, useState } from "react";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { gorevDurumuEtiketi, oncelikEtiketi } from "../lib/labels";
import {
  completeTasksBulk,
  listAllTasks,
  updateTaskDue,
  updateTaskStatus,
} from "../services/lawcopilotApi";
import type { Task } from "../types/domain";

export function TasksPage() {
  const { settings } = useAppContext();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [error, setError] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [isBulkCompleting, setIsBulkCompleting] = useState(false);

  useEffect(() => {
    listAllTasks(settings)
      .then((response) => {
        setTasks(response.items);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [settings.baseUrl, settings.token]);

  function toggleSelect(taskId: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  }

  async function handleStatusUpdate(taskId: number, status: string) {
    try {
      const result = await updateTaskStatus(settings, taskId, status);
      setTasks((prev) =>
        prev.map((task) => (task.id === taskId ? result.task : task))
      );
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Durum güncellenemedi.");
    }
  }

  async function handleDueUpdate(taskId: number) {
    const input = window.prompt("Yeni son tarih (YYYY-MM-DDThh:mm:ssZ):");
    if (!input) return;
    try {
      const result = await updateTaskDue(settings, taskId, input);
      setTasks((prev) =>
        prev.map((task) => (task.id === taskId ? result.task : task))
      );
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tarih güncellenemedi.");
    }
  }

  async function handleBulkComplete() {
    if (selectedIds.size === 0) return;
    setIsBulkCompleting(true);
    try {
      await completeTasksBulk(settings, Array.from(selectedIds));
      setTasks((prev) =>
        prev.map((task) =>
          selectedIds.has(task.id)
            ? { ...task, status: "completed" }
            : task
        )
      );
      setSelectedIds(new Set());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Toplu tamamlama başarısız.");
    } finally {
      setIsBulkCompleting(false);
    }
  }

  const openTasks = tasks.filter((task) => task.status !== "completed");
  const completedTasks = tasks.filter((task) => task.status === "completed");

  function statusTone(status: string): "accent" | "warning" | "danger" {
    switch (status) {
      case "completed":
        return "accent";
      case "in_progress":
        return "warning";
      default:
        return "danger";
    }
  }

  function nextStatus(current: string): string | null {
    switch (current) {
      case "open":
        return "in_progress";
      case "in_progress":
        return "completed";
      default:
        return null;
    }
  }

  function renderTask(task: Task) {
    const next = nextStatus(task.status);
    return (
      <article className="list-item" key={task.id}>
        <div className="toolbar">
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            {task.status !== "completed" ? (
              <input
                type="checkbox"
                checked={selectedIds.has(task.id)}
                onChange={() => toggleSelect(task.id)}
                style={{ width: "1.1rem", height: "1.1rem" }}
              />
            ) : null}
            <h3 className="list-item__title">{task.title}</h3>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <StatusBadge tone={task.priority === "high" ? "danger" : task.priority === "medium" ? "warning" : "accent"}>
              {oncelikEtiketi(task.priority)}
            </StatusBadge>
            <StatusBadge tone={statusTone(task.status)}>
              {gorevDurumuEtiketi(task.status)}
            </StatusBadge>
          </div>
        </div>
        <p className="list-item__meta">
          {task.due_at ? `${new Date(task.due_at).toLocaleString("tr-TR")} · ` : ""}
          {task.explanation || "Açıklama yok"}
          {task.matter_id ? ` · Dosya #${task.matter_id}` : " · Genel görev"}
        </p>
        {task.status !== "completed" ? (
          <div className="toolbar" style={{ marginTop: "0.5rem" }}>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {next ? (
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={() => handleStatusUpdate(task.id, next)}
                  style={{ padding: "0.35rem 0.7rem", fontSize: "0.8rem" }}
                >
                  {next === "in_progress" ? "Başlat" : "Tamamla"}
                </button>
              ) : null}
              <button
                className="button button--ghost"
                type="button"
                onClick={() => handleDueUpdate(task.id)}
                style={{ padding: "0.35rem 0.7rem", fontSize: "0.8rem" }}
              >
                Tarih güncelle
              </button>
            </div>
          </div>
        ) : null}
      </article>
    );
  }

  return (
    <div className="page-grid">
      <SectionCard
        title="Tüm görevler"
        subtitle="Dosya bağımsız tüm görevleri listeler. Durumu güncelle, tarihi değiştir veya toplu tamamla."
        actions={
          selectedIds.size > 0 ? (
            <button
              className="button"
              type="button"
              onClick={handleBulkComplete}
              disabled={isBulkCompleting}
            >
              {isBulkCompleting
                ? "Tamamlanıyor..."
                : `${selectedIds.size} görevi tamamla`}
            </button>
          ) : null
        }
      >
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
        {openTasks.length ? (
          <div className="list">{openTasks.map(renderTask)}</div>
        ) : (
          <EmptyState
            title="Açık görev yok"
            description="Tüm görevler tamamlandı veya henüz görev oluşturulmadı."
          />
        )}
      </SectionCard>

      {completedTasks.length ? (
        <SectionCard
          title="Tamamlanan görevler"
          subtitle={`${completedTasks.length} görev tamamlandı.`}
        >
          <div className="list">{completedTasks.map(renderTask)}</div>
        </SectionCard>
      ) : null}
    </div>
  );
}
