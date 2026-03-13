import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSpinner } from "../components/common/LoadingSpinner";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { WorkspaceOverviewPanel } from "../components/workspace/WorkspaceOverviewPanel";
import { tr } from "../i18n/tr";
import { buildDocumentViewerPath } from "../lib/documentViewer";
import { disIletisimDurumuEtiketi, kanalEtiketi } from "../lib/labels";
import {
  createAssistantCalendarEvent,
  getAssistantAgenda,
  getAssistantCalendar,
  getAssistantHome,
  getAssistantInbox,
  getAssistantSuggestedActions,
  getAssistantThread,
  getTelemetryHealth,
  listAssistantDrafts,
  listMatters,
  listWorkspaceDocuments,
  postAssistantThreadMessage,
  resetAssistantThread,
  uploadMatterDocument,
} from "../services/lawcopilotApi";
import type {
  AssistantAgendaItem,
  AssistantCalendarItem,
  AssistantHomeResponse,
  AssistantThreadMessage,
  Matter,
  OutboundDraft,
  SuggestedAction,
  TelemetryHealth,
  WorkspaceDocument,
} from "../types/domain";

const TOOL_KEYS = ["today", "calendar", "workspace", "matters", "documents", "drafts", "runtime"] as const;
type ToolKey = (typeof TOOL_KEYS)[number];

const PAGE_SIZE = 30;
const MAX_ATTACHMENTS = 10;

type ComposerAttachment = {
  id: string;
  file: File;
  kind: "image" | "file";
  previewUrl?: string;
};

type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  start: () => void;
  stop: () => void;
};

type BrowserSpeechRecognitionFactory = new () => BrowserSpeechRecognition;

type DesktopGoogleState = {
  connected: boolean;
  enabled: boolean;
  accountLabel: string;
  scopes: string[];
};

type CalendarCreatePayload = {
  title: string;
  startsAt: string;
  endsAt?: string;
  location?: string;
  matterId?: number;
  needsPreparation: boolean;
  target: "google" | "local";
};

const GOOGLE_CALENDAR_WRITE_SCOPES = [
  "https://www.googleapis.com/auth/calendar.events",
  "https://www.googleapis.com/auth/calendar",
];

/* ── Helpers ──────────────────────────────────────────────── */

function dateLabel(value?: string | null) {
  if (!value) return "Zaman bilgisi yok";
  return new Date(value).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" });
}

function timeLabel(value?: string | null) {
  if (!value) return "";
  return new Date(value).toLocaleString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

function toolLabel(tool: ToolKey) {
  const text = tr.assistant;
  const labels: Record<ToolKey, string> = {
    today: text.toolToday,
    calendar: text.toolCalendar,
    workspace: text.toolWorkspace,
    matters: text.toolMatters,
    documents: text.toolDocuments,
    drafts: text.toolDrafts,
    runtime: text.toolRuntime,
  };
  return labels[tool];
}

function padCalendarNumber(value: number) {
  return String(value).padStart(2, "0");
}

function dayKeyFromDate(value: Date) {
  return `${value.getFullYear()}-${padCalendarNumber(value.getMonth() + 1)}-${padCalendarNumber(value.getDate())}`;
}

function dayKeyFromIso(value?: string | null) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return dayKeyFromDate(parsed);
}

function dateFromDayKey(dayKey: string) {
  const [year, month, day] = dayKey.split("-").map((item) => Number(item));
  return new Date(year, Math.max(0, month - 1), day);
}

function monthKeyFromDayKey(dayKey: string) {
  return dayKey.slice(0, 7);
}

function shiftMonthKey(monthKey: string, amount: number) {
  const [year, month] = monthKey.split("-").map((item) => Number(item));
  const next = new Date(year, Math.max(0, month - 1) + amount, 1);
  return `${next.getFullYear()}-${padCalendarNumber(next.getMonth() + 1)}`;
}

function buildMonthCells(monthKey: string) {
  const [year, month] = monthKey.split("-").map((item) => Number(item));
  const firstDay = new Date(year, Math.max(0, month - 1), 1);
  const firstWeekday = (firstDay.getDay() + 6) % 7;
  const gridStart = new Date(year, Math.max(0, month - 1), 1 - firstWeekday);
  return Array.from({ length: 42 }, (_, index) => {
    const current = new Date(gridStart);
    current.setDate(gridStart.getDate() + index);
    const dayKey = dayKeyFromDate(current);
    return {
      dayKey,
      date: current,
      inMonth: monthKeyFromDayKey(dayKey) === monthKey,
    };
  });
}

function monthTitleFromKey(monthKey: string) {
  const [year, month] = monthKey.split("-").map((item) => Number(item));
  return new Date(year, Math.max(0, month - 1), 1).toLocaleDateString("tr-TR", {
    month: "long",
    year: "numeric",
  });
}

function fullDayTitle(dayKey: string) {
  return dateFromDayKey(dayKey).toLocaleDateString("tr-TR", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function hasGoogleCalendarWriteScope(scopes: string[]) {
  return scopes.some((scope) => GOOGLE_CALENDAR_WRITE_SCOPES.includes(String(scope || "").trim()));
}

function resolveDesktopGoogleState(payload: Record<string, unknown> | null, fallbackConnected: boolean): DesktopGoogleState {
  const google = payload && typeof payload.google === "object" && payload.google ? (payload.google as Record<string, unknown>) : null;
  const scopes = Array.isArray(google?.scopes) ? google.scopes.map((scope) => String(scope || "").trim()).filter(Boolean) : [];
  return {
    connected: Boolean(google?.oauthConnected) || fallbackConnected,
    enabled: Boolean(google?.enabled) || fallbackConnected,
    accountLabel: String(google?.accountLabel || ""),
    scopes,
  };
}

function calendarProviderLabel(item: AssistantCalendarItem) {
  const text = tr.assistant;
  if (item.provider === "google") {
    return text.calendarProviderGoogle;
  }
  if (item.provider === "user-profile" || item.source_type === "user_profile") {
    return text.calendarProviderProfile;
  }
  if (item.source_type === "task") {
    return text.calendarProviderTask;
  }
  return text.calendarProviderLocal;
}

function attachmentKind(file: File, preferredKind?: "image" | "file") {
  if (preferredKind) {
    return preferredKind;
  }
  return file.type.startsWith("image/") ? "image" : "file";
}

function createComposerAttachment(file: File, preferredKind?: "image" | "file"): ComposerAttachment {
  const kind = attachmentKind(file, preferredKind);
  return {
    id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 9)}`,
    file,
    kind,
    previewUrl: kind === "image" ? URL.createObjectURL(file) : undefined,
  };
}

function revokeAttachmentPreviews(items: ComposerAttachment[]) {
  for (const item of items) {
    if (item.previewUrl) {
      URL.revokeObjectURL(item.previewUrl);
    }
  }
}

function getSpeechRecognitionFactory(): BrowserSpeechRecognitionFactory | null {
  const browserWindow = window as Window & {
    SpeechRecognition?: BrowserSpeechRecognitionFactory;
    webkitSpeechRecognition?: BrowserSpeechRecognitionFactory;
  };
  return browserWindow.SpeechRecognition || browserWindow.webkitSpeechRecognition || null;
}

function sourceRefBadges(sourceContext?: Record<string, unknown> | null) {
  const refs = Array.isArray(sourceContext?.source_refs) ? sourceContext.source_refs : [];
  return refs
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const value = item as Record<string, unknown>;
      return {
        label: String(value.label || value.display_name || value.name || value.relative_path || "Ek"),
        uploaded: Boolean(value.uploaded || value.document_id || value.id),
      };
    })
    .filter((item): item is { label: string; uploaded: boolean } => Boolean(item));
}

function messageMetaItems(sourceContext: Record<string, unknown> | null | undefined, key: string) {
  return Array.isArray(sourceContext?.[key]) ? (sourceContext?.[key] as Array<Record<string, unknown>>) : [];
}

/* ── Tool Panels (unchanged) ─────────────────────────────── */

function ToolTabs({ activeTool, onSelect }: { activeTool: ToolKey; onSelect: (tool: ToolKey) => void }) {
  return (
    <div className="tabs" style={{ marginBottom: "1rem" }}>
      {TOOL_KEYS.map((tool) => (
        <button
          key={tool}
          className={`tab${activeTool === tool ? " tab--active" : ""}`}
          type="button"
          onClick={() => onSelect(tool)}
        >
          {toolLabel(tool)}
        </button>
      ))}
    </div>
  );
}

function TodayTool({ agenda, inbox, actions }: { agenda: AssistantAgendaItem[]; inbox: AssistantAgendaItem[]; actions: SuggestedAction[] }) {
  const items = [...agenda, ...inbox].slice(0, 10);
  return (
    <div className="stack">
      <SectionCard title={tr.assistant.todayTitle} subtitle={tr.assistant.todaySubtitle}>
        {items.length ? (
          <div className="list">
            {items.map((item) => (
              <article className="list-item" key={item.id}>
                <div className="toolbar">
                  <strong>{item.title}</strong>
                  <StatusBadge tone={item.priority === "high" ? "warning" : "accent"}>{item.priority}</StatusBadge>
                </div>
                <p className="list-item__meta">{item.details || "Ayrıntı yok"}</p>
                <p className="list-item__meta">{dateLabel(item.due_at)}</p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title={tr.assistant.agendaEmptyTitle} description={tr.assistant.agendaEmptyDescription} />
        )}
      </SectionCard>
      <SectionCard title={tr.assistant.suggestedActionsTitleCompact} subtitle="Asistanın önerdiği en yakın aksiyonlar.">
        {actions.length ? (
          <div className="list">
            {actions.slice(0, 5).map((action) => (
              <article className="list-item" key={action.id}>
                <div className="toolbar">
                  <strong>{action.title}</strong>
                  <StatusBadge tone={action.manual_review_required ? "warning" : "accent"}>
                    {action.manual_review_required ? tr.assistant.approvalRequired : tr.assistant.draftReady}
                  </StatusBadge>
                </div>
                <p className="list-item__meta">{action.rationale || action.description || "Gerekçe yok"}</p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title={tr.assistant.suggestedActionsEmptyTitle} description={tr.assistant.suggestedActionsEmptyDescription} />
        )}
      </SectionCard>
    </div>
  );
}

function CalendarTool({
  items,
  today,
  googleState,
  selectedMatterId,
  canSyncGoogle,
  isSyncing,
  isCreating,
  onSyncGoogle,
  onCreateEvent,
}: {
  items: AssistantCalendarItem[];
  today: string;
  googleState: DesktopGoogleState | null;
  selectedMatterId?: number;
  canSyncGoogle: boolean;
  isSyncing: boolean;
  isCreating: boolean;
  onSyncGoogle: () => Promise<string>;
  onCreateEvent: (payload: CalendarCreatePayload) => Promise<{ delivery: "google" | "local"; message: string }>;
}) {
  const text = tr.assistant;
  const todayKey = today || dayKeyFromDate(new Date());
  const [visibleMonth, setVisibleMonth] = useState(monthKeyFromDayKey(todayKey));
  const [selectedDay, setSelectedDay] = useState(todayKey);
  const [plannerTitle, setPlannerTitle] = useState("");
  const [plannerLocation, setPlannerLocation] = useState("");
  const [plannerDate, setPlannerDate] = useState(todayKey);
  const [plannerStart, setPlannerStart] = useState("09:00");
  const [plannerEnd, setPlannerEnd] = useState("10:00");
  const [plannerNeedsPreparation, setPlannerNeedsPreparation] = useState(true);
  const [plannerTarget, setPlannerTarget] = useState<"google" | "local">("local");
  const [plannerNotice, setPlannerNotice] = useState("");
  const [plannerError, setPlannerError] = useState("");

  const googleConnected = Boolean(googleState?.connected);
  const googleWriteReady = hasGoogleCalendarWriteScope(googleState?.scopes || []);
  const monthCells = useMemo(() => buildMonthCells(visibleMonth), [visibleMonth]);
  const itemsByDay = useMemo(() => {
    const grouped = new Map<string, AssistantCalendarItem[]>();
    for (const item of items) {
      const key = dayKeyFromIso(item.starts_at);
      if (!key) {
        continue;
      }
      const current = grouped.get(key) || [];
      current.push(item);
      grouped.set(key, current);
    }
    return grouped;
  }, [items]);
  const selectedDayItems = itemsByDay.get(selectedDay) || [];

  useEffect(() => {
    setVisibleMonth(monthKeyFromDayKey(todayKey));
    setSelectedDay(todayKey);
    setPlannerDate(todayKey);
  }, [todayKey]);

  useEffect(() => {
    if (googleConnected && googleWriteReady) {
      setPlannerTarget((current) => (current === "local" ? "google" : current));
      return;
    }
    setPlannerTarget("local");
  }, [googleConnected, googleWriteReady]);

  function handleSelectDay(dayKey: string) {
    setSelectedDay(dayKey);
    setPlannerDate(dayKey);
    setPlannerNotice("");
    setPlannerError("");
  }

  async function handlePlannerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedTitle = plannerTitle.trim();
    if (!normalizedTitle) {
      setPlannerError(text.calendarPlannerTitleRequired);
      return;
    }
    const startDate = new Date(`${plannerDate}T${plannerStart}:00`);
    const endDate = plannerEnd ? new Date(`${plannerDate}T${plannerEnd}:00`) : null;
    if (endDate && endDate <= startDate) {
      setPlannerError(text.calendarPlannerRangeError);
      return;
    }
    setPlannerError("");
    setPlannerNotice("");
    try {
      const result = await onCreateEvent({
        title: normalizedTitle,
        startsAt: startDate.toISOString(),
        endsAt: endDate?.toISOString(),
        location: plannerLocation.trim(),
        matterId: selectedMatterId,
        needsPreparation: plannerNeedsPreparation,
        target: plannerTarget === "google" && googleConnected && googleWriteReady ? "google" : "local",
      });
      setPlannerNotice(result.message);
      setPlannerTitle("");
      setPlannerLocation("");
      setSelectedDay(plannerDate);
      setVisibleMonth(monthKeyFromDayKey(plannerDate));
      if (result.delivery === "local" && plannerTarget === "google") {
        setPlannerTarget("local");
      }
    } catch (err) {
      setPlannerError(err instanceof Error ? err.message : text.queryError);
    }
  }

  async function handleSync() {
    setPlannerError("");
    setPlannerNotice("");
    try {
      const message = await onSyncGoogle();
      setPlannerNotice(message);
    } catch (err) {
      setPlannerError(err instanceof Error ? err.message : text.syncError);
    }
  }

  return (
    <SectionCard title={text.calendarTitle} subtitle={text.calendarSubtitle}>
      <div className="calendar-tool">
        <div className="calendar-tool__topbar">
          <div className="calendar-tool__status-copy">
            <strong>{monthTitleFromKey(visibleMonth)}</strong>
            <span>{text.calendarMonthSubtitle}</span>
          </div>
          <div className="calendar-tool__status-actions">
            <StatusBadge tone={googleConnected ? (googleWriteReady ? "accent" : "warning") : "warning"}>
              {googleConnected ? (googleWriteReady ? text.calendarPlannerGoogleReady : text.calendarPlannerGoogleReadOnly) : text.calendarPlannerGoogleMissing}
            </StatusBadge>
            {googleState?.accountLabel ? <span className="pill">{googleState.accountLabel}</span> : null}
            {canSyncGoogle ? (
              <button className="button button--ghost calendar-tool__sync-btn" type="button" onClick={handleSync} disabled={isSyncing}>
                {isSyncing ? text.calendarPlannerSyncing : text.calendarPlannerSync}
              </button>
            ) : null}
          </div>
        </div>

        <div className="calendar-tool__nav">
          <button className="calendar-tool__nav-btn" type="button" title={text.monthPrevious} onClick={() => setVisibleMonth((current) => shiftMonthKey(current, -1))}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <button className="calendar-tool__today-btn" type="button" onClick={() => {
            setVisibleMonth(monthKeyFromDayKey(todayKey));
            handleSelectDay(todayKey);
          }}>
            {text.currentTimeLabel}
          </button>
          <button className="calendar-tool__nav-btn" type="button" title={text.monthNext} onClick={() => setVisibleMonth((current) => shiftMonthKey(current, 1))}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>

        <div className="calendar-tool__weekday-row">
          {text.calendarWeekdays.map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>

        <div className="calendar-tool__month-grid">
          {monthCells.map((cell) => {
            const dayItems = itemsByDay.get(cell.dayKey) || [];
            return (
              <button
                key={cell.dayKey}
                className={`calendar-tool__day${cell.inMonth ? "" : " calendar-tool__day--outside"}${cell.dayKey === todayKey ? " calendar-tool__day--today" : ""}${cell.dayKey === selectedDay ? " calendar-tool__day--selected" : ""}`}
                type="button"
                onClick={() => handleSelectDay(cell.dayKey)}
              >
                <span className="calendar-tool__day-number">{cell.date.getDate()}</span>
                <div className="calendar-tool__day-items">
                  {dayItems.slice(0, 2).map((item) => (
                    <span key={`${cell.dayKey}-${item.id}`} className={`calendar-tool__mini-item${item.needs_preparation ? " calendar-tool__mini-item--warning" : ""}`}>
                      {item.all_day ? item.title : `${timeLabel(item.starts_at)} ${item.title}`}
                    </span>
                  ))}
                  {dayItems.length > 2 ? <span className="calendar-tool__mini-more">+{dayItems.length - 2}</span> : null}
                </div>
              </button>
            );
          })}
        </div>

        <div className="calendar-tool__detail-card">
          <div className="calendar-tool__detail-header">
            <div>
              <strong>{fullDayTitle(selectedDay)}</strong>
              <span>{text.calendarEventsSubtitle}</span>
            </div>
            <StatusBadge>{`${selectedDayItems.length} kayıt`}</StatusBadge>
          </div>
          {selectedDayItems.length ? (
            <div className="calendar-tool__event-list">
              {selectedDayItems.map((item) => (
                <article className="calendar-tool__event-card" key={item.id}>
                  <div className="toolbar">
                    <div className="calendar-tool__event-copy">
                      <strong>{item.title}</strong>
                      <span>
                        {item.all_day ? "Tüm gün" : `${timeLabel(item.starts_at)}${item.ends_at ? ` - ${timeLabel(item.ends_at)}` : ""}`}
                      </span>
                    </div>
                    <div className="calendar-tool__event-badges">
                      <StatusBadge tone={item.needs_preparation ? "warning" : "accent"}>
                        {item.needs_preparation ? text.preparationNeeded : text.calendarEntry}
                      </StatusBadge>
                      <StatusBadge>{calendarProviderLabel(item)}</StatusBadge>
                    </div>
                  </div>
                  <p className="list-item__meta">{item.details || text.noLocation}</p>
                  {item.location ? <p className="list-item__meta">{item.location}</p> : null}
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title={text.calendarPlannerEmptyDay} description={text.calendarPlannerEmptyDayNote} />
          )}
        </div>

        <form className="calendar-tool__planner-card" onSubmit={handlePlannerSubmit}>
          <div className="calendar-tool__detail-header">
            <div>
              <strong>{text.calendarPlannerTitle}</strong>
              <span>{text.calendarPlannerSubtitle}</span>
            </div>
            <StatusBadge tone={selectedMatterId ? "accent" : "warning"}>
              {selectedMatterId ? text.calendarPlannerBound : text.calendarPlannerLoose}
            </StatusBadge>
          </div>

          <div className="calendar-tool__target-row">
            <span>{text.calendarPlannerTargetLabel}</span>
            <div className="calendar-tool__target-tabs">
              <button
                className={`calendar-tool__target-tab${plannerTarget === "google" ? " calendar-tool__target-tab--active" : ""}`}
                type="button"
                disabled={!googleConnected || !googleWriteReady}
                onClick={() => setPlannerTarget("google")}
              >
                {text.calendarPlannerTargetGoogle}
              </button>
              <button
                className={`calendar-tool__target-tab${plannerTarget === "local" ? " calendar-tool__target-tab--active" : ""}`}
                type="button"
                onClick={() => setPlannerTarget("local")}
              >
                {text.calendarPlannerTargetLocal}
              </button>
            </div>
          </div>

          {googleConnected && !googleWriteReady ? (
            <div className="callout">
              <strong>{text.calendarPlannerGoogleReadOnly}</strong>
              <p className="list-item__meta">{text.calendarPlannerGoogleScopeHint}</p>
              <Link className="button button--ghost calendar-tool__settings-link" to="/settings">
                {text.openSettingsAction}
              </Link>
            </div>
          ) : null}

          <div className="field-grid">
            <label className="calendar-tool__field">
              <span>{text.calendarPlannerTitleLabel}</span>
              <input className="input" value={plannerTitle} onChange={(event) => setPlannerTitle(event.target.value)} />
            </label>
            <label className="calendar-tool__field">
              <span>{text.calendarPlannerLocationLabel}</span>
              <input className="input" value={plannerLocation} onChange={(event) => setPlannerLocation(event.target.value)} />
            </label>
          </div>

          <div className="field-grid field-grid--two">
            <label className="calendar-tool__field">
              <span>{text.calendarPlannerDateLabel}</span>
              <input className="input" type="date" value={plannerDate} onChange={(event) => {
                setPlannerDate(event.target.value);
                setSelectedDay(event.target.value);
                setVisibleMonth(monthKeyFromDayKey(event.target.value));
              }} />
            </label>
            <label className="calendar-tool__field">
              <span>{text.calendarPlannerPreparation}</span>
              <button
                className={`calendar-tool__toggle${plannerNeedsPreparation ? " calendar-tool__toggle--active" : ""}`}
                type="button"
                onClick={() => setPlannerNeedsPreparation((current) => !current)}
              >
                {plannerNeedsPreparation ? text.preparationNeeded : text.calendarEntry}
              </button>
            </label>
          </div>

          <div className="field-grid field-grid--two">
            <label className="calendar-tool__field">
              <span>{text.calendarPlannerStartLabel}</span>
              <input className="input" type="time" value={plannerStart} onChange={(event) => setPlannerStart(event.target.value)} />
            </label>
            <label className="calendar-tool__field">
              <span>{text.calendarPlannerEndLabel}</span>
              <input className="input" type="time" value={plannerEnd} onChange={(event) => setPlannerEnd(event.target.value)} />
            </label>
          </div>

          {plannerError ? <p className="calendar-tool__feedback calendar-tool__feedback--error">{plannerError}</p> : null}
          {plannerNotice ? <p className="calendar-tool__feedback">{plannerNotice}</p> : null}

          <div className="calendar-tool__planner-actions">
            <button className="button" type="submit" disabled={isCreating}>
              {isCreating ? text.calendarPlannerSubmitting : text.calendarPlannerSubmit}
            </button>
          </div>
        </form>
      </div>
    </SectionCard>
  );
}

function MattersTool({ matters }: { matters: Matter[] }) {
  return (
    <SectionCard title="Dosyalar" subtitle="Asistanın kullanabildiği dosya bağlamları.">
      {matters.length ? (
        <div className="list">
          {matters.map((matter) => (
            <Link className="list-item" key={matter.id} to={`/matters/${matter.id}`}>
              <div className="toolbar">
                <strong>{matter.title}</strong>
                <StatusBadge>{matter.status}</StatusBadge>
              </div>
              <p className="list-item__meta">{matter.client_name || "Müvekkil belirtilmedi"}</p>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState title="Henüz dosya yok" description="Yeni dosyalar oluşturuldukça asistan bunları bağlam olarak kullanır." />
      )}
    </SectionCard>
  );
}

function DocumentsTool({ documents }: { documents: WorkspaceDocument[] }) {
  return (
    <SectionCard title="Belgeler" subtitle="Çalışma klasöründeki son indeksli belgeler.">
      {documents.length ? (
        <div className="list">
          {documents.slice(0, 12).map((document) => (
            <article className="list-item" key={document.id}>
              <div className="toolbar">
                <strong>{document.display_name}</strong>
                <StatusBadge>{document.extension}</StatusBadge>
              </div>
              <p className="list-item__meta">{document.relative_path}</p>
              <div className="toolbar">
                <StatusBadge tone={document.indexed_status === "indexed" ? "accent" : "warning"}>{document.indexed_status}</StatusBadge>
                <Link className="button button--ghost" to={buildDocumentViewerPath({ scope: "workspace", documentId: document.id })}>
                  Aç
                </Link>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState title="Belge bulunamadı" description="Çalışma alanı tarandığında belgeler burada görünür." />
      )}
    </SectionCard>
  );
}

function DraftsTool({ drafts }: { drafts: OutboundDraft[] }) {
  return (
    <SectionCard title="Taslaklar" subtitle="Dış aksiyonlar taslak ve onay akışıyla yönetilir.">
      {drafts.length ? (
        <div className="list">
          {drafts.slice(0, 10).map((draft) => (
            <article className="list-item" key={String(draft.id)}>
              <div className="toolbar">
                <strong>{draft.subject || draft.draft_type}</strong>
                <StatusBadge>{disIletisimDurumuEtiketi(draft.approval_status, draft.delivery_status)}</StatusBadge>
              </div>
              <p className="list-item__meta">{draft.to_contact || "Hedef belirtilmedi"} · {kanalEtiketi(draft.channel)}</p>
              <p style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>{draft.body.slice(0, 180)}</p>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState title="Taslak yok" description="Asistan bir dış aksiyon hazırladığında burada görünür." />
      )}
    </SectionCard>
  );
}

function RuntimeTool({ health }: { health: TelemetryHealth | null }) {
  const runtimeMode = String(health?.assistant_runtime_mode || "");
  const runtimeLabel =
    runtimeMode === "direct-provider"
      ? "Doğrudan sağlayıcı"
      : runtimeMode === "advanced-openclaw"
        ? "Gelişmiş ajan köprüsü"
        : "Fallback modu";
  return (
    <SectionCard title="Durum" subtitle="Bağlantılar ve sistem durumu burada görünür.">
      {health ? (
        <div className="list">
          <article className="list-item">
            <div className="toolbar">
              <strong>Sistem durumu</strong>
              <StatusBadge tone={health.provider_configured ? "accent" : "warning"}>
                {health.provider_configured ? runtimeLabel : "Sınırlı"}
              </StatusBadge>
            </div>
          </article>
          <article className="list-item">
            <div className="toolbar">
              <strong>Bağlı hizmetler</strong>
              <StatusBadge>{health.google_configured ? "Google bağlı" : "Google yok"}</StatusBadge>
            </div>
            <p className="list-item__meta">Telegram: {health.telegram_configured ? "Bağlı" : "Yok"}</p>
          </article>
        </div>
      ) : (
        <EmptyState title="Durum yüklenemedi" description="Servis hazır olduğunda bağlantı durumu burada görünür." />
      )}
    </SectionCard>
  );
}

/* ── WhatsApp-style Message Bubble ───────────────────────── */

function ChatBubble({ message, onOpenTool }: { message: AssistantThreadMessage; onOpenTool: (tool: ToolKey) => void }) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const attachmentBadges = sourceRefBadges(message.source_context);
  const proposedActions = messageMetaItems(message.source_context, "proposed_actions");
  const approvalRequests = messageMetaItems(message.source_context, "approval_requests");
  const memoryUpdates = messageMetaItems(message.source_context, "memory_updates");
  const executedTools = messageMetaItems(message.source_context, "executed_tools");

  return (
    <div className={`wa-bubble-row ${isUser ? "wa-bubble-row--user" : "wa-bubble-row--assistant"}`}>
      {isAssistant && (
        <div className="wa-avatar">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z" />
            <path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
          </svg>
        </div>
      )}
      <div className={`wa-bubble ${isUser ? "wa-bubble--user" : "wa-bubble--assistant"}`}>
        <p className="wa-bubble__text">{message.content}</p>

        {isAssistant && (message.tool_suggestions.length > 0 || message.linked_entities.length > 0 || message.draft_preview) ? (
          <div className="wa-bubble__extras">
            {message.tool_suggestions.length > 0 && (
              <div className="wa-bubble__suggestions">
                <span className="wa-bubble__suggestion-label">{tr.assistant.suggestedActionsTitleCompact}</span>
                <div className="wa-bubble__suggestion-chips">
                  {message.tool_suggestions.map((item) => (
                    <button key={`${item.tool}-${item.label}`} className="wa-chip" type="button" onClick={() => onOpenTool(item.tool as ToolKey)}>
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {message.draft_preview && typeof message.draft_preview === "object" ? (
              <div className="wa-bubble__draft-preview">
                <strong>{tr.assistant.draftPreviewTitleCompact}</strong>
                {"subject" in message.draft_preview && message.draft_preview.subject ? <p>{String(message.draft_preview.subject)}</p> : null}
                {"body" in message.draft_preview ? <p>{String(message.draft_preview.body).slice(0, 260)}</p> : null}
              </div>
            ) : null}
            {proposedActions.length > 0 ? (
              <div className="wa-bubble__suggestions">
                <span className="wa-bubble__suggestion-label">Önerilen aksiyonlar</span>
                <div className="wa-bubble__suggestion-chips">
                  {proposedActions.map((item, index) => (
                    <span key={`proposed-${message.id}-${index}`} className="wa-chip">
                      {String(item.label || item.tool || "Aksiyon")}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
            {approvalRequests.length > 0 ? (
              <div className="wa-bubble__draft-preview">
                <strong>Onay bekleyen işlem</strong>
                {approvalRequests.map((item, index) => (
                  <p key={`approval-${message.id}-${index}`}>{String(item.title || item.tool || "Dış aksiyon")} onay bekliyor.</p>
                ))}
              </div>
            ) : null}
            {memoryUpdates.length > 0 ? (
              <div className="wa-bubble__draft-preview">
                <strong>Bellek güncellemesi</strong>
                {memoryUpdates.map((item, index) => (
                  <p key={`memory-${message.id}-${index}`}>{String(item.summary || item.value || "Profil notu güncellendi.")}</p>
                ))}
              </div>
            ) : null}
            {executedTools.length > 0 ? (
              <div className="wa-bubble__suggestions">
                <span className="wa-bubble__suggestion-label">Kullanılan araçlar</span>
                <div className="wa-bubble__suggestion-chips">
                  {executedTools.map((item, index) => (
                    <span key={`tool-${message.id}-${index}`} className="wa-chip">
                      {String(item.tool || "Araç")}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        {attachmentBadges.length ? (
          <div className="wa-bubble__extras">
            <div className="wa-bubble__suggestions">
              <span className="wa-bubble__suggestion-label">{tr.assistant.chatAttachmentsTitle}</span>
              <div className="wa-bubble__suggestion-chips">
                {attachmentBadges.map((item) => (
                  <span key={`${message.id}-${item.label}`} className={`wa-chip wa-chip--attachment${item.uploaded ? " wa-chip--attachment-ready" : ""}`}>
                    {item.label}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ) : null}

      </div>
    </div>
  );
}

/* ── Typing Indicator ────────────────────────────────────── */

function TypingIndicator() {
  return (
    <div className="wa-bubble-row wa-bubble-row--assistant">
      <div className="wa-avatar">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z" />
          <path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
        </svg>
      </div>
      <div className="wa-bubble wa-bubble--assistant wa-typing">
        <span className="wa-typing__dot" />
        <span className="wa-typing__dot" />
        <span className="wa-typing__dot" />
      </div>
    </div>
  );
}

/* ── Scroll-to-bottom button ─────────────────────────────── */

function ScrollToBottomButton({ onClick, visible }: { onClick: () => void; visible: boolean }) {
  if (!visible) return null;
  return (
    <button className="wa-scroll-bottom" type="button" onClick={onClick} title="En alta git">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>
  );
}

/* ── Main Page Component ─────────────────────────────────── */

export function AssistantPage() {
  const { settings } = useAppContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const text = tr.assistant;
  const selectedTool = (searchParams.get("tool") as ToolKey | null) || null;

  // state
  const [home, setHome] = useState<AssistantHomeResponse | null>(null);
  const [threadMessages, setThreadMessages] = useState<AssistantThreadMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [agenda, setAgenda] = useState<AssistantAgendaItem[]>([]);
  const [inbox, setInbox] = useState<AssistantAgendaItem[]>([]);
  const [calendar, setCalendar] = useState<AssistantCalendarItem[]>([]);
  const [calendarToday, setCalendarToday] = useState(dayKeyFromDate(new Date()));
  const [calendarGoogleState, setCalendarGoogleState] = useState<DesktopGoogleState | null>(null);
  const [actions, setActions] = useState<SuggestedAction[]>([]);
  const [drafts, setDrafts] = useState<OutboundDraft[]>([]);
  const [matters, setMatters] = useState<Matter[]>([]);
  const [documents, setDocuments] = useState<WorkspaceDocument[]>([]);
  const [runtimeHealth, setRuntimeHealth] = useState<TelemetryHealth | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [isMessagesScrolling, setIsMessagesScrolling] = useState(false);
  const [isToolsScrolling, setIsToolsScrolling] = useState(false);
  const [isCalendarSyncing, setIsCalendarSyncing] = useState(false);
  const [isCalendarCreating, setIsCalendarCreating] = useState(false);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [isDragActive, setIsDragActive] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState("");

  // refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const isFirstLoad = useRef(true);
  const messageScrollTimerRef = useRef<number | null>(null);
  const toolsScrollRef = useRef<HTMLDivElement>(null);
  const toolsScrollTimerRef = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const speechSeedPromptRef = useRef("");
  const attachmentStoreRef = useRef<ComposerAttachment[]>([]);

  /* ── Scroll helpers ─────────────────────────────────────── */

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);

  /* ── Load data ──────────────────────────────────────────── */

  async function loadHomeAndThread() {
    const [homeResponse, threadResponse] = await Promise.all([
      getAssistantHome(settings),
      getAssistantThread(settings, { limit: PAGE_SIZE }),
    ]);
    setHome(homeResponse);
    setThreadMessages(threadResponse.messages);
    setHasMore(!!threadResponse.has_more);
  }

  async function loadCalendarToolData() {
    const desktopConfigPromise = window.lawcopilotDesktop?.getIntegrationConfig
      ? window.lawcopilotDesktop.getIntegrationConfig().catch(() => null)
      : Promise.resolve(null);
    const [calendarResponse, desktopConfig] = await Promise.all([
      getAssistantCalendar(settings),
      desktopConfigPromise,
    ]);
    setCalendar(calendarResponse.items);
    setCalendarToday(calendarResponse.today);
    setCalendarGoogleState(resolveDesktopGoogleState((desktopConfig as Record<string, unknown> | null) || null, calendarResponse.google_connected));
  }

  async function loadOlderMessages() {
    if (isLoadingMore || !hasMore || threadMessages.length === 0) return;
    setIsLoadingMore(true);

    const container = messagesContainerRef.current;
    const previousScrollHeight = container?.scrollHeight || 0;

    try {
      const firstId = threadMessages[0].id;
      const response = await getAssistantThread(settings, { limit: PAGE_SIZE, before_id: firstId });
      if (response.messages.length > 0) {
        setThreadMessages((prev) => [...response.messages, ...prev]);
      }
      setHasMore(!!response.has_more);

      // preserve scroll position
      requestAnimationFrame(() => {
        if (container) {
          const newScrollHeight = container.scrollHeight;
          container.scrollTop = newScrollHeight - previousScrollHeight;
        }
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : text.queryError);
    } finally {
      setIsLoadingMore(false);
    }
  }

  async function loadToolData(tool: ToolKey) {
    if (tool === "today") {
      const [agendaResponse, inboxResponse, actionsResponse] = await Promise.all([
        getAssistantAgenda(settings),
        getAssistantInbox(settings),
        getAssistantSuggestedActions(settings),
      ]);
      setAgenda(agendaResponse.items);
      setInbox(inboxResponse.items);
      setActions(actionsResponse.items);
      return;
    }
    if (tool === "calendar") {
      await loadCalendarToolData();
      return;
    }
    if (tool === "matters") {
      const response = await listMatters(settings);
      setMatters(response.items);
      return;
    }
    if (tool === "documents") {
      const response = await listWorkspaceDocuments(settings);
      setDocuments(response.items);
      return;
    }
    if (tool === "drafts") {
      const response = await listAssistantDrafts(settings);
      setDrafts(response.items);
      return;
    }
    if (tool === "runtime") {
      const response = await getTelemetryHealth(settings);
      setRuntimeHealth(response);
    }
  }

  /* ── Effects ────────────────────────────────────────────── */

  useEffect(() => {
    setIsLoading(true);
    isFirstLoad.current = true;
    loadHomeAndThread()
      .then(() => setError(""))
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, [settings.baseUrl, settings.token]);

  // scroll to bottom on first load or when messages arrive
  useEffect(() => {
    if (threadMessages.length > 0 && isFirstLoad.current) {
      requestAnimationFrame(() => scrollToBottom("instant" as ScrollBehavior));
      isFirstLoad.current = false;
    }
  }, [threadMessages, scrollToBottom]);

  // infinite scroll: observe sentinel at top
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isLoadingMore) {
          loadOlderMessages();
        }
      },
      { root: messagesContainerRef.current, threshold: 0.1 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, threadMessages]);

  // show/hide scroll-to-bottom button
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    function handleScroll() {
      if (!container) return;
      setIsMessagesScrolling(true);
      if (messageScrollTimerRef.current !== null) {
        window.clearTimeout(messageScrollTimerRef.current);
      }
      messageScrollTimerRef.current = window.setTimeout(() => {
        setIsMessagesScrolling(false);
        messageScrollTimerRef.current = null;
      }, 520);
      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      setShowScrollBtn(distanceFromBottom > 200);
    }

    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      container.removeEventListener("scroll", handleScroll);
      if (messageScrollTimerRef.current !== null) {
        window.clearTimeout(messageScrollTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!selectedTool) return;
    loadToolData(selectedTool).catch((err: Error) => setError(err.message));
  }, [selectedTool, settings.baseUrl, settings.token]);

  useEffect(() => {
    const container = toolsScrollRef.current;
    if (!container || !selectedTool) {
      return;
    }

    function handleScroll() {
      setIsToolsScrolling(true);
      if (toolsScrollTimerRef.current !== null) {
        window.clearTimeout(toolsScrollTimerRef.current);
      }
      toolsScrollTimerRef.current = window.setTimeout(() => {
        setIsToolsScrolling(false);
        toolsScrollTimerRef.current = null;
      }, 520);
    }

    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      container.removeEventListener("scroll", handleScroll);
      if (toolsScrollTimerRef.current !== null) {
        window.clearTimeout(toolsScrollTimerRef.current);
      }
    };
  }, [selectedTool]);

  useEffect(() => {
    attachmentStoreRef.current = attachments;
  }, [attachments]);

  useEffect(() => () => {
    revokeAttachmentPreviews(attachmentStoreRef.current);
    if (speechRecognitionRef.current) {
      speechRecognitionRef.current.stop();
    }
  }, []);

  const quickPrompts = useMemo(
    () => [
      text.quickPromptToday,
      text.quickPromptMissing,
      text.quickPromptClientUpdate,
      text.quickPromptCalendar,
      text.quickPromptSimilarity,
    ],
    [text],
  );
  const attachmentHint = settings.currentMatterId ? text.chatAttachmentHintBound : text.chatAttachmentHintLoose;
  const canSubmit = Boolean(prompt.trim() || attachments.length);

  /* ── Handlers ───────────────────────────────────────────── */

  function addAttachments(nextFiles: File[], preferredKind?: "image" | "file") {
    if (!nextFiles.length) {
      return;
    }
    setAttachments((prev) => {
      const remaining = Math.max(0, MAX_ATTACHMENTS - prev.length);
      if (!remaining) {
        return prev;
      }
      const freshItems = nextFiles.slice(0, remaining).map((file) => createComposerAttachment(file, preferredKind));
      return [...prev, ...freshItems];
    });
    setError("");
  }

  function handleSelectedFiles(files: FileList | File[] | null, preferredKind?: "image" | "file") {
    if (!files) {
      return;
    }
    addAttachments(Array.from(files), preferredKind);
  }

  function handleAttachmentInputChange(event: ChangeEvent<HTMLInputElement>) {
    handleSelectedFiles(event.target.files);
    event.currentTarget.value = "";
  }

  function removeAttachment(attachmentId: string) {
    setAttachments((prev) => {
      const target = prev.find((item) => item.id === attachmentId);
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return prev.filter((item) => item.id !== attachmentId);
    });
  }

  function clearAttachments() {
    revokeAttachmentPreviews(attachmentStoreRef.current);
    attachmentStoreRef.current = [];
    setAttachments([]);
  }

  function openAttachmentPicker() {
    fileInputRef.current?.click();
  }

  function stopListening() {
    if (speechRecognitionRef.current) {
      speechRecognitionRef.current.stop();
    }
    setIsListening(false);
  }

  function handleMicToggle() {
    if (isListening) {
      stopListening();
      return;
    }
    const Recognition = getSpeechRecognitionFactory();
    if (!Recognition) {
      setError(text.chatMicUnsupported);
      return;
    }
    try {
      const recognition = speechRecognitionRef.current || new Recognition();
      recognition.lang = "tr-TR";
      recognition.interimResults = true;
      recognition.continuous = true;
      recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map((result) => result[0]?.transcript || "")
          .join(" ")
          .trim();
        setPrompt(`${speechSeedPromptRef.current}${transcript}`.trimStart());
      };
      recognition.onend = () => {
        setIsListening(false);
      };
      recognition.onerror = () => {
        setError(text.chatMicError);
        setIsListening(false);
      };
      speechRecognitionRef.current = recognition;
      speechSeedPromptRef.current = prompt.trim() ? `${prompt.trim()} ` : "";
      recognition.start();
      setIsListening(true);
      setError("");
    } catch {
      setError(text.chatMicError);
      setIsListening(false);
    }
  }

  function handleComposerDragEnter(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types || []).includes("Files")) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current += 1;
    setIsDragActive(true);
  }

  function handleComposerDragOver(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types || []).includes("Files")) {
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setIsDragActive(true);
  }

  function handleComposerDragLeave(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types || []).includes("Files")) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDragActive(false);
    }
  }

  function handleComposerDrop(event: DragEvent<HTMLDivElement>) {
    if (!Array.from(event.dataTransfer.types || []).includes("Files")) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current = 0;
    setIsDragActive(false);
    handleSelectedFiles(event.dataTransfer.files);
  }

  async function prepareAttachmentSourceRefs(selectedAttachments: ComposerAttachment[]) {
    const sourceRefs: Array<Record<string, unknown>> = [];
    let partialFallback = false;

    if (!selectedAttachments.length) {
      return { sourceRefs, partialFallback };
    }

    const uploadResults = await Promise.allSettled(
      selectedAttachments.map(async (attachment) => {
        if (!settings.currentMatterId) {
          return {
            label: attachment.file.name,
            kind: attachment.kind,
            uploaded: false,
            contentType: attachment.file.type,
            sizeBytes: attachment.file.size,
            documentId: undefined,
            matterId: undefined,
            relativePath: undefined,
          };
        }
        const response = await uploadMatterDocument(settings, settings.currentMatterId, {
          file: attachment.file,
          displayName: attachment.file.name,
          sourceType: "upload",
        });
        return {
          label: response.document.display_name || attachment.file.name,
          kind: attachment.kind,
          uploaded: true,
          contentType: response.document.content_type || attachment.file.type,
          sizeBytes: response.document.size_bytes || attachment.file.size,
          documentId: response.document.id,
          matterId: response.document.matter_id,
          relativePath: response.document.filename,
        };
      }),
    );

    uploadResults.forEach((result, index) => {
      const attachment = selectedAttachments[index];
      if (result.status === "fulfilled") {
        sourceRefs.push({
          type: result.value.uploaded ? "matter_document" : (result.value.kind === "image" ? "image_attachment" : "file_attachment"),
          label: result.value.label,
          content_type: result.value.contentType,
          size_bytes: result.value.sizeBytes,
          uploaded: result.value.uploaded,
          document_id: result.value.documentId,
          matter_id: result.value.matterId,
          relative_path: result.value.relativePath,
        });
        return;
      }
      partialFallback = true;
      sourceRefs.push({
        type: attachment.kind === "image" ? "image_attachment" : "file_attachment",
        label: attachment.file.name,
        content_type: attachment.file.type,
        size_bytes: attachment.file.size,
        uploaded: false,
        upload_error: true,
      });
    });

    return { sourceRefs, partialFallback };
  }

  async function handleSubmit(nextPrompt?: string) {
    const content = (nextPrompt ?? prompt).trim();
    const selectedAttachments = [...attachments];
    const finalContent = content || (selectedAttachments.length ? text.chatDefaultAttachmentPrompt : "");
    if (!finalContent) {
      return;
    }
    setIsSubmitting(true);
    if (!nextPrompt) {
      setPrompt("");
    }
    if (isListening) {
      stopListening();
    }

    let sourceRefs: Array<Record<string, unknown>> = selectedAttachments.map((attachment) => ({
      type: attachment.kind === "image" ? "image_attachment" : "file_attachment",
      label: attachment.file.name,
      content_type: attachment.file.type,
      size_bytes: attachment.file.size,
      uploaded: false,
    }));

    // optimistic user message
    const tempUserMsg: AssistantThreadMessage = {
      id: Date.now(),
      thread_id: 0,
      office_id: "",
      role: "user",
      content: finalContent,
      linked_entities: [],
      tool_suggestions: [],
      draft_preview: null,
      source_context: {
        source_refs: sourceRefs,
      },
      requires_approval: false,
      generated_from: "assistant_thread_user",
      ai_provider: null,
      ai_model: null,
      created_at: new Date().toISOString(),
    };
    setThreadMessages((prev) => [...prev, tempUserMsg]);
    requestAnimationFrame(() => scrollToBottom());

    try {
      if (selectedAttachments.length) {
        const prepared = await prepareAttachmentSourceRefs(selectedAttachments);
        sourceRefs = prepared.sourceRefs;
        if (prepared.partialFallback) {
          setError(text.chatAttachmentPartialFallback);
        }
      }
      const response = await postAssistantThreadMessage(settings, {
        content: finalContent,
        matter_id: settings.currentMatterId || undefined,
        source_refs: sourceRefs,
      });
      setThreadMessages(response.messages);
      const homeResponse = await getAssistantHome(settings);
      setHome(homeResponse);
      if (!selectedAttachments.length) {
        setError("");
      }
      clearAttachments();
      requestAnimationFrame(() => scrollToBottom());
      if (response.tool_suggestions?.[0]?.tool) {
        const params = new URLSearchParams(searchParams);
        params.set("tool", String(response.tool_suggestions[0].tool));
        setSearchParams(params, { replace: true });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : text.queryError);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleResetThread() {
    setIsResetting(true);
    try {
      await resetAssistantThread(settings);
      await loadHomeAndThread();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : text.queryError);
    } finally {
      setIsResetting(false);
    }
  }

  async function handleSyncGoogleCalendar() {
    if (!window.lawcopilotDesktop?.syncGoogleData) {
      throw new Error(text.syncDesktopOnly);
    }
    setIsCalendarSyncing(true);
    try {
      const result = await window.lawcopilotDesktop.syncGoogleData();
      await loadCalendarToolData();
      return String(result?.message || text.syncSuccess);
    } finally {
      setIsCalendarSyncing(false);
    }
  }

  async function handleCreateCalendarEvent(payload: CalendarCreatePayload) {
    setIsCalendarCreating(true);
    try {
      let delivery: "google" | "local" = "local";
      let message: string = text.calendarPlannerSuccessLocal;
      if (payload.target === "google" && window.lawcopilotDesktop?.createGoogleCalendarEvent) {
        try {
          const result = await window.lawcopilotDesktop.createGoogleCalendarEvent({
            title: payload.title,
            startsAt: payload.startsAt,
            endsAt: payload.endsAt,
            location: payload.location,
            matterId: payload.matterId,
            needsPreparation: payload.needsPreparation,
          });
          delivery = "google";
          message = String(result?.message || text.calendarPlannerSuccessGoogle);
        } catch (err) {
          await createAssistantCalendarEvent(settings, {
            title: payload.title,
            starts_at: payload.startsAt,
            ends_at: payload.endsAt,
            location: payload.location,
            matter_id: payload.matterId,
            needs_preparation: payload.needsPreparation,
          });
          const reason = err instanceof Error ? err.message : "";
          message = reason ? `${reason} ${text.calendarPlannerFallbackLocal}` : text.calendarPlannerFallbackLocal;
        }
      } else {
        await createAssistantCalendarEvent(settings, {
          title: payload.title,
          starts_at: payload.startsAt,
          ends_at: payload.endsAt,
          location: payload.location,
          matter_id: payload.matterId,
          needs_preparation: payload.needsPreparation,
        });
      }
      await loadCalendarToolData();
      return { delivery, message };
    } finally {
      setIsCalendarCreating(false);
    }
  }

  function openTool(tool: ToolKey) {
    const params = new URLSearchParams(searchParams);
    params.set("tool", tool);
    setSearchParams(params, { replace: true });
  }

  function closeTool() {
    const params = new URLSearchParams(searchParams);
    params.delete("tool");
    setSearchParams(params, { replace: true });
  }

  /* ── Render ─────────────────────────────────────────────── */

  if (isLoading) {
    return <LoadingSpinner label="Asistan yükleniyor..." />;
  }

  return (
    <div className="assistant-vnext">
      <div className={`assistant-vnext__body${selectedTool ? " assistant-vnext__body--with-drawer" : ""}`}>
        <div className="wa-chat-surface">
          <div
            className={`wa-chat-container${isDragActive ? " wa-chat-container--drag-active" : ""}`}
            onDragEnter={handleComposerDragEnter}
            onDragOver={handleComposerDragOver}
            onDragLeave={handleComposerDragLeave}
            onDrop={handleComposerDrop}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={handleAttachmentInputChange}
            />
            {isDragActive ? (
              <div className="wa-drop-overlay" aria-hidden="true">
                <div className="wa-drop-overlay__panel">
                  <strong>{text.chatDropTitle}</strong>
                  <span>{text.chatDropSubtitle}</span>
                </div>
              </div>
            ) : null}

            {/* Messages area */}
            <div className={`wa-messages${isMessagesScrolling ? " wa-messages--scrolling" : ""}`} ref={messagesContainerRef}>
              {threadMessages.length ? (
                <>
                  {/* Sentinel for infinite scroll */}
                  <div ref={sentinelRef} className="wa-sentinel">
                    {isLoadingMore && (
                      <div className="wa-load-more-spinner">
                        <div className="wa-spinner" />
                      </div>
                    )}
                    {!hasMore && threadMessages.length > PAGE_SIZE && (
                      <div className="wa-thread-beginning">Konuşma başlangıcı</div>
                    )}
                  </div>

                  {/* Reset thread button */}
                  {!hasMore && (
                    <div className="wa-reset-row">
                      <button className="wa-reset-btn" type="button" onClick={handleResetThread} disabled={isResetting}>
                        {isResetting ? text.threadResetBusy : text.threadReset}
                      </button>
                    </div>
                  )}

                  {/* Message bubbles */}
                  {threadMessages.map((message) => (
                    <ChatBubble key={message.id} message={message} onOpenTool={openTool} />
                  ))}

                  {/* Typing indicator */}
                  {isSubmitting && <TypingIndicator />}
                </>
              ) : (
                <div className="wa-welcome">
                  <div className="wa-welcome__icon">
                    <svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" opacity="0.3">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                  </div>
                  <h2 className="wa-welcome__title">LawCopilot Asistan</h2>
                  <p className="wa-welcome__subtitle">
                    {home?.today_summary || text.threadEmptyDescription}
                  </p>
                  {home?.counts ? (
                    <div className="wa-welcome__badges">
                      <span className="wa-badge">{`${home.counts.agenda} ajanda`}</span>
                      <span className="wa-badge">{`${home.counts.inbox} iletişim`}</span>
                      <span className="wa-badge">{`${home.counts.calendar_today} takvim`}</span>
                      <span className="wa-badge">{`${home.counts.drafts_pending} onay`}</span>
                    </div>
                  ) : null}

                  {home?.requires_setup?.length ? (
                    <div className="callout" style={{ width: "100%", maxWidth: "500px" }}>
                      <strong>Kurulum eksikleri</strong>
                      <div className="list" style={{ marginTop: "0.75rem" }}>
                        {home.requires_setup.map((item) => (
                          <article className="list-item" key={item.id}>
                            <strong>{item.title}</strong>
                            <p className="list-item__meta">{item.details}</p>
                            <Link className="button button--secondary" to="/settings">
                              {text.openSettingsAction}
                            </Link>
                          </article>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <div className="wa-quick-prompts">
                    <strong>{text.quickPromptsTitle}</strong>
                    <p className="wa-quick-prompts__sub">{text.quickPromptsSubtitle}</p>
                    <div className="wa-quick-prompts__grid">
                      {quickPrompts.map((item) => (
                        <button key={item} className="wa-chip wa-chip--prompt" type="button" onClick={() => handleSubmit(item)} disabled={isSubmitting}>
                          {item}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Scroll-to-bottom fab */}
            <ScrollToBottomButton visible={showScrollBtn} onClick={() => scrollToBottom()} />

            {/* Input area */}
            <div className="wa-input-wrapper">
              {attachments.length ? (
                <div className="wa-attachments">
                  <div className="wa-attachments__header">
                    <strong>{text.chatAttachmentsTitle}</strong>
                    <span>{attachmentHint}</span>
                  </div>
                  <div className="wa-attachments__list">
                    {attachments.map((attachment) => (
                      <article key={attachment.id} className={`wa-attachment-chip wa-attachment-chip--${attachment.kind}`}>
                        {attachment.previewUrl ? <img className="wa-attachment-chip__preview" src={attachment.previewUrl} alt={attachment.file.name} /> : null}
                        <div className="wa-attachment-chip__meta">
                          <strong>{attachment.file.name}</strong>
                          <span>{settings.currentMatterId ? text.chatAttachmentUploading : text.chatAttachmentLocalOnly}</span>
                        </div>
                        <button
                          className="wa-attachment-chip__remove"
                          type="button"
                          title={text.chatAttachmentRemove}
                          onClick={() => removeAttachment(attachment.id)}
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M18 6 6 18" />
                            <path d="m6 6 12 12" />
                          </svg>
                        </button>
                      </article>
                    ))}
                  </div>
                </div>
              ) : null}
              <form
                className="wa-input-area"
                onSubmit={(event) => {
                  event.preventDefault();
                  handleSubmit();
                }}
              >
                <div className="wa-input-actions wa-input-actions--left">
                  <button className="wa-icon-btn" type="button" title={text.chatAttachFile} onClick={openAttachmentPicker}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 5v14" />
                      <path d="M5 12h14" />
                    </svg>
                  </button>
                </div>
                <textarea
                  className="wa-input-field"
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder={text.chatPlaceholder}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSubmit();
                    }
                  }}
                />
                <div className="wa-input-actions wa-input-actions--right">
                  <button
                    className={`wa-icon-btn${isListening ? " wa-icon-btn--active" : ""}`}
                    type="button"
                    title={isListening ? text.chatMicStop : text.chatMicStart}
                    onClick={handleMicToggle}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3z" />
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                      <path d="M12 19v3" />
                    </svg>
                  </button>
                  <button className="wa-send-btn" type="submit" disabled={isSubmitting || !canSubmit} title={text.chatSend}>
                    {isSubmitting ? (
                      <div className="wa-spinner wa-spinner--small" />
                    ) : (
                      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="22" y1="2" x2="11" y2="13" />
                        <polygon points="22 2 15 22 11 13 2 9 22 2" />
                      </svg>
                    )}
                  </button>
                </div>
              </form>
              <div className="wa-input-footer">
                {error ? (
                  <span style={{ color: "var(--danger)" }}>{error}</span>
                ) : isListening ? (
                  <span>{text.chatListening}</span>
                ) : attachments.length ? (
                  <span>{attachmentHint}</span>
                ) : (
                  <span>Asistan hata yapabilir. Önemli bilgileri doğrulayın.</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {selectedTool ? (
          <aside className="assistant-tools-drawer">
            <SectionCard
              className="assistant-tools-panel"
              title={text.toolsTitle}
              subtitle={text.toolsSubtitle}
              actions={
                <button className="button button--ghost" type="button" onClick={closeTool}>
                  {text.toolsClose}
                </button>
              }
            >
              <div className={`assistant-tools-scroll${isToolsScrolling ? " assistant-tools-scroll--scrolling" : ""}`} ref={toolsScrollRef}>
                <ToolTabs activeTool={selectedTool} onSelect={openTool} />
                {selectedTool === "today" ? <TodayTool agenda={agenda} inbox={inbox} actions={actions} /> : null}
                {selectedTool === "calendar" ? (
                  <CalendarTool
                    items={calendar}
                    today={calendarToday}
                    googleState={calendarGoogleState}
                    selectedMatterId={settings.currentMatterId || undefined}
                    canSyncGoogle={Boolean(window.lawcopilotDesktop?.syncGoogleData)}
                    isSyncing={isCalendarSyncing}
                    isCreating={isCalendarCreating}
                    onSyncGoogle={handleSyncGoogleCalendar}
                    onCreateEvent={handleCreateCalendarEvent}
                  />
                ) : null}
                {selectedTool === "workspace" ? <WorkspaceOverviewPanel /> : null}
                {selectedTool === "matters" ? <MattersTool matters={matters} /> : null}
                {selectedTool === "documents" ? <DocumentsTool documents={documents} /> : null}
                {selectedTool === "drafts" ? <DraftsTool drafts={drafts} /> : null}
                {selectedTool === "runtime" ? <RuntimeTool health={runtimeHealth} /> : null}
              </div>
            </SectionCard>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
