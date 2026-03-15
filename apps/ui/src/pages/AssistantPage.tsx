import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ChangeEvent, type DragEvent, type FormEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSpinner } from "../components/common/LoadingSpinner";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { WorkspaceOverviewPanel } from "../components/workspace/WorkspaceOverviewPanel";
import { tr } from "../i18n/tr";
import { buildDocumentViewerPath } from "../lib/documentViewer";
import { belgeDurumuEtiketi, disIletisimDurumuEtiketi, dosyaBasligiEtiketi, dosyaDurumuEtiketi, kanalEtiketi, oncelikEtiketi } from "../lib/labels";
import { openWorkspaceDocument } from "../lib/workspaceDocuments";
import {
  approveAssistantApproval,
  createAssistantCalendarEvent,
  getAssistantAgenda,
  getAssistantApprovals,
  getAssistantCalendar,
  getAssistantHome,
  getAssistantInbox,
  getAssistantSuggestedActions,
  getAssistantThread,
  getGoogleIntegrationStatus,
  getTelemetryHealth,
  listAssistantDrafts,
  listGoogleDriveFiles,
  listMatters,
  listWorkspaceDocuments,
  postAssistantThreadMessage,
  rejectAssistantApproval,
  resetAssistantThread,
  sendAssistantDraft,
  uploadMatterDocument,
} from "../services/lawcopilotApi";
import type {
  AssistantAgendaItem,
  AssistantCalendarItem,
  AssistantHomeResponse,
  AssistantThreadMessage,
  GoogleDriveFile,
  GoogleIntegrationStatus,
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
const DEFAULT_DRAWER_WIDTH = 456;
const MIN_DRAWER_WIDTH = 360;
const MAX_DRAWER_WIDTH = 1120;
const DRAWER_WIDTH_STORAGE_KEY = "lawcopilot.assistant.drawer.width";
const DISMISSED_PROACTIVE_STORAGE_KEY = "lawcopilot.assistant.proactive.dismissed";

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

type GoogleAutoSyncState = {
  started: boolean;
  completed: boolean;
};

type AssistantHomeSuggestion = NonNullable<AssistantHomeResponse["proactive_suggestions"]>[number];

type CalendarCreatePayload = {
  title: string;
  startsAt: string;
  endsAt?: string;
  location?: string;
  matterId?: number;
  needsPreparation: boolean;
  target: "google" | "local";
};

type BubbleResultItem = {
  title: string;
  url: string;
  snippet: string;
};

type BubbleApprovalItem = {
  id: string;
  action_id?: number | null;
  draft_id?: number | null;
  tool?: string | null;
  title?: string | null;
  reason?: string | null;
  status?: string | null;
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

function setupLinkForItem(item: { id?: string | null; action?: string | null }) {
  const action = String(item.action || "").trim();
  const id = String(item.id || "").trim();
  if (id === "setup-google") {
    return "/settings?tab=workspace&section=integration-google";
  }
  if (id === "setup-telegram") {
    return "/settings?tab=workspace&section=integration-telegram";
  }
  if (id === "setup-whatsapp") {
    return "/settings?tab=workspace&section=integration-whatsapp";
  }
  if (id === "setup-x") {
    return "/settings?tab=workspace&section=integration-x";
  }
  if (action === "open_onboarding" || action === "open_settings") {
    return "/settings?tab=workspace&section=workspace-setup-card";
  }
  return "/settings?tab=workspace&section=workspace-setup-card";
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

function googleDriveTypeLabel(value?: string | null) {
  const normalized = String(value || "").toLowerCase();
  if (!normalized) {
    return "Drive";
  }
  if (normalized.includes("folder")) {
    return "Klasör";
  }
  if (normalized.includes("document")) {
    return "Doküman";
  }
  if (normalized.includes("spreadsheet")) {
    return "Tablo";
  }
  if (normalized.includes("presentation")) {
    return "Sunum";
  }
  if (normalized.includes("pdf")) {
    return "PDF";
  }
  if (normalized.includes("image")) {
    return "Görsel";
  }
  return normalized.split("/").pop() || "Drive";
}

function priorityTone(value?: string | null): "accent" | "warning" | "danger" {
  switch ((value || "").toLowerCase()) {
    case "high":
      return "danger";
    case "medium":
      return "warning";
    default:
      return "accent";
  }
}

function shouldAutoSyncGoogle(status: GoogleIntegrationStatus | null) {
  if (!status?.configured) {
    return false;
  }
  const lastSyncAt = status.last_sync_at ? Date.parse(status.last_sync_at) : 0;
  if (!lastSyncAt) {
    return true;
  }
  return Date.now() - lastSyncAt > 5 * 60 * 1000;
}

function isToolKey(value?: string | null): value is ToolKey {
  return TOOL_KEYS.includes(String(value || "") as ToolKey);
}

function stripLeadingGreeting(value?: string | null) {
  return String(value || "").replace(/^Selam[^.]*\.\s*/u, "").trim();
}

function currentLocalDayKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function loadDismissedProactiveIds() {
  if (typeof window === "undefined") {
    return [] as string[];
  }
  try {
    const raw = window.localStorage.getItem(DISMISSED_PROACTIVE_STORAGE_KEY);
    if (!raw) {
      return [] as string[];
    }
    const parsed = JSON.parse(raw) as { day?: string; ids?: unknown };
    if (parsed.day !== currentLocalDayKey() || !Array.isArray(parsed.ids)) {
      return [] as string[];
    }
    return parsed.ids.map((item) => String(item || "").trim()).filter(Boolean);
  } catch {
    return [] as string[];
  }
}

function persistDismissedProactiveIds(ids: string[]) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(
      DISMISSED_PROACTIVE_STORAGE_KEY,
      JSON.stringify({
        day: currentLocalDayKey(),
        ids: ids.filter(Boolean),
      }),
    );
  } catch {
    // Local persistence is best-effort only.
  }
}

function buildHomeSummaryText(home: AssistantHomeResponse | null, fallback: string) {
  if (!home) {
    return fallback;
  }
  const parts = [String(home.greeting_message || "").trim(), stripLeadingGreeting(home.today_summary || "")]
    .filter(Boolean)
    .map((item) => item.replace(/\s+/g, " ").trim());
  return parts.join(" ").trim() || fallback;
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

function speechTextFromMessage(value: string) {
  return String(value || "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .replace(/\[(.*?)\]\((.*?)\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function resolveSpeechVoice() {
  const voices = window.speechSynthesis?.getVoices?.() || [];
  return (
    voices.find((voice) => String(voice.lang || "").toLowerCase().startsWith("tr")) ||
    voices.find((voice) => String(voice.lang || "").toLowerCase().startsWith("en")) ||
    null
  );
}

function clampDrawerWidth(value: number, viewportWidth?: number) {
  const viewportMax = typeof viewportWidth === "number" && Number.isFinite(viewportWidth) ? viewportWidth : (typeof window !== "undefined" ? window.innerWidth : 1440);
  const maxAllowed = Math.max(MIN_DRAWER_WIDTH, Math.min(MAX_DRAWER_WIDTH, viewportMax - 180));
  return Math.max(MIN_DRAWER_WIDTH, Math.min(Math.round(value), maxAllowed));
}

function initialDrawerWidth() {
  if (typeof window === "undefined") {
    return DEFAULT_DRAWER_WIDTH;
  }
  const stored = Number(window.localStorage.getItem(DRAWER_WIDTH_STORAGE_KEY) || "");
  return clampDrawerWidth(Number.isFinite(stored) ? stored : DEFAULT_DRAWER_WIDTH, window.innerWidth);
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

function sameActionLabel(left: unknown, right: unknown) {
  return String(left || "")
    .trim()
    .toLocaleLowerCase("tr-TR") === String(right || "").trim().toLocaleLowerCase("tr-TR");
}

function renderBubbleText(value: string): ReactNode {
  const lines = String(value || "").split("\n");
  return lines.map((line, lineIndex) => {
    const nodes: ReactNode[] = [];
    const pattern = /\*\*(.+?)\*\*/g;
    let cursor = 0;
    let match = pattern.exec(line);

    while (match) {
      const start = match.index ?? 0;
      if (start > cursor) {
        nodes.push(line.slice(cursor, start));
      }
      nodes.push(
        <strong key={`line-${lineIndex}-strong-${start}`}>
          {match[1]}
        </strong>,
      );
      cursor = start + match[0].length;
      match = pattern.exec(line);
    }

    if (cursor < line.length) {
      nodes.push(line.slice(cursor));
    }

    return (
      <Fragment key={`line-${lineIndex}`}>
        {nodes}
        {lineIndex < lines.length - 1 ? <br /> : null}
      </Fragment>
    );
  });
}

function bubbleResultItems(sourceContext: Record<string, unknown> | null | undefined, key: string): BubbleResultItem[] {
  const items = Array.isArray(sourceContext?.[key]) ? (sourceContext?.[key] as Array<Record<string, unknown>>) : [];
  return items
    .map((item) => {
      const title = String(item?.title || item?.label || "Sonuç").trim();
      const url = String(item?.url || item?.href || "").trim();
      const snippet = String(item?.snippet || item?.summary || "").trim();
      if (!title && !url) {
        return null;
      }
      return {
        title: title || url,
        url,
        snippet,
      };
    })
    .filter((item): item is BubbleResultItem => Boolean(item));
}

function bubbleApprovalItems(sourceContext: Record<string, unknown> | null | undefined): BubbleApprovalItem[] {
  return messageMetaItems(sourceContext, "approval_requests").map((item) => ({
    id: String(item.id || ""),
    action_id: item.action_id ? Number(item.action_id) : undefined,
    draft_id: item.draft_id ? Number(item.draft_id) : undefined,
    tool: String(item.tool || ""),
    title: String(item.title || ""),
    reason: String(item.reason || ""),
    status: String(item.status || ""),
  }));
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
    <div className="tool-panel-grid">
      <SectionCard title={tr.assistant.todayTitle} subtitle={tr.assistant.todaySubtitle}>
        {items.length ? (
          <div className="tool-card-grid">
            {items.map((item) => (
              <article className="list-item" key={item.id}>
                <div className="toolbar">
                  <strong>{item.title}</strong>
                  <StatusBadge tone={priorityTone(item.priority)}>{oncelikEtiketi(item.priority)}</StatusBadge>
                </div>
                <p className="list-item__meta">{item.details || "Ayrıntı belirtilmedi"}</p>
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
          <div className="tool-card-grid">
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

function MattersTool({ matters, googleStatus }: { matters: Matter[]; googleStatus: GoogleIntegrationStatus | null }) {
  return (
    <SectionCard title="Dosyalar" subtitle="Asistanın kullanabildiği dosya bağlamları.">
      <div className="stack">
        {googleStatus?.configured ? (
          <div className="callout callout--accent">
            <strong>{googleStatus.account_label || "Google çalışma alanı bağlı"}</strong>
            <p className="list-item__meta" style={{ marginBottom: "0.75rem" }}>
              Gmail, Takvim ve Drive verileri uygulama yüzeylerine aynalanır.
            </p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <StatusBadge tone={googleStatus.gmail_connected ? "accent" : "warning"}>{`${googleStatus.email_thread_count || 0} Gmail iş parçacığı`}</StatusBadge>
              <StatusBadge tone={googleStatus.calendar_connected ? "accent" : "warning"}>{`${googleStatus.calendar_event_count || 0} Takvim kaydı`}</StatusBadge>
              <StatusBadge tone={googleStatus.drive_connected ? "accent" : "warning"}>{`${googleStatus.drive_file_count || 0} Drive dosyası`}</StatusBadge>
            </div>
          </div>
        ) : null}

        {matters.length ? (
          <div className="tool-card-grid">
            {matters.map((matter) => (
              <Link className="list-item" key={matter.id} to={`/matters/${matter.id}`}>
                <div className="toolbar">
                  <strong>{dosyaBasligiEtiketi(matter.title)}</strong>
                  <StatusBadge>{dosyaDurumuEtiketi(matter.status)}</StatusBadge>
                </div>
                <p className="list-item__meta">{matter.client_name || "Müvekkil belirtilmedi"}</p>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="Henüz dosya yok" description="Yeni dosyalar oluşturuldukça asistan bunları bağlam olarak kullanır." />
        )}
      </div>
    </SectionCard>
  );
}

function DocumentsTool({
  documents,
  driveFiles,
  googleStatus,
  canSyncGoogle,
  isSyncing,
  onSyncGoogle,
}: {
  documents: WorkspaceDocument[];
  driveFiles: GoogleDriveFile[];
  googleStatus: GoogleIntegrationStatus | null;
  canSyncGoogle: boolean;
  isSyncing: boolean;
  onSyncGoogle: () => Promise<string>;
}) {
  const text = tr.assistant;
  const navigate = useNavigate();
  const googleConnected = Boolean(googleStatus?.configured);
  const driveConnected = Boolean(googleStatus?.drive_connected);
  const hasDriveFiles = driveFiles.length > 0;

  return (
    <SectionCard title="Belgeler" subtitle="Çalışma alanı belgeleri ile Google Drive dosyaları birlikte görünür.">
      <div className="stack">
        <div className="toolbar" style={{ alignItems: "flex-start" }}>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <StatusBadge tone={documents.length ? "accent" : "warning"}>{`${documents.length} yerel belge`}</StatusBadge>
            <StatusBadge tone={driveConnected ? "accent" : "warning"}>{`${driveFiles.length} Drive dosyası`}</StatusBadge>
            {googleStatus?.account_label ? <StatusBadge>{googleStatus.account_label}</StatusBadge> : null}
            {googleStatus?.last_sync_at ? <StatusBadge>{`Son eşitleme ${dateLabel(googleStatus.last_sync_at)}`}</StatusBadge> : null}
          </div>
          {googleConnected && canSyncGoogle ? (
            <button className="button button--ghost" type="button" onClick={() => void onSyncGoogle()} disabled={isSyncing}>
              {isSyncing ? text.calendarPlannerSyncing : "Google verilerini yenile"}
            </button>
          ) : null}
        </div>

        <div className="tool-panel-grid">
          <div className="stack stack--tight">
            <strong>Çalışma alanı belgeleri</strong>
            {documents.length ? (
              <div className="tool-card-grid">
                {documents.slice(0, 10).map((document) => (
                  <article className="list-item" key={document.id}>
                    <div className="toolbar">
                      <strong>{document.display_name}</strong>
                      <StatusBadge>{document.extension}</StatusBadge>
                    </div>
                    <p className="list-item__meta">{document.relative_path}</p>
                    <div className="toolbar">
                      <StatusBadge tone={document.indexed_status === "indexed" ? "accent" : "warning"}>{belgeDurumuEtiketi(document.indexed_status)}</StatusBadge>
                      <button
                        className="button button--ghost"
                        type="button"
                        onClick={() =>
                          void openWorkspaceDocument({
                            relativePath: document.relative_path,
                            fallbackTarget: { scope: "workspace", documentId: document.id },
                            navigate,
                          })
                        }
                      >
                        Belgeyi aç
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState title="Yerel belge bulunamadı" description="Çalışma alanı tarandığında belgeler burada görünür." />
            )}
          </div>

          <div className="stack stack--tight">
            <strong>Google Drive</strong>
            {hasDriveFiles ? (
              <div className="tool-card-grid">
                {driveFiles.slice(0, 10).map((file) => (
                  <article className="list-item" key={`${file.provider}-${file.external_id}`}>
                    <div className="toolbar">
                      <strong>{file.name}</strong>
                      <StatusBadge>{googleDriveTypeLabel(file.mime_type)}</StatusBadge>
                    </div>
                    <p className="list-item__meta">{file.modified_at ? `Güncellendi: ${dateLabel(file.modified_at)}` : "Değişiklik tarihi yok"}</p>
                    <div className="toolbar">
                      <StatusBadge tone="accent">Google Drive</StatusBadge>
                      {file.web_view_link ? (
                        <a className="button button--ghost" href={file.web_view_link} target="_blank" rel="noreferrer">
                          Drive'da aç
                        </a>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            ) : googleConnected && !driveConnected ? (
              <div className="callout">
                <strong>Drive izni henüz yok</strong>
                <p className="list-item__meta">Google hesabını Drive erişimi ile bağladığınızda bu alan otomatik dolacak.</p>
                <Link className="button button--ghost" to="/settings">
                  {text.openSettingsAction}
                </Link>
              </div>
            ) : (
              <EmptyState
                title={googleConnected ? "Drive dosyası bulunamadı" : "Google Drive bağlı değil"}
                description={googleConnected ? "Google eşitleme yapıldığında son Drive dosyaları burada görünür." : "Ayarlar üzerinden Google hesabınızı bağlayın."}
              />
            )}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

function isDispatchableDraftChannel(channel: string) {
  return ["email", "gmail", "telegram", "whatsapp", "x", "travel"].includes(String(channel || "").trim().toLowerCase());
}

function mergeDraftIntoList(currentDrafts: OutboundDraft[], incomingDraft: OutboundDraft) {
  const incomingId = String(incomingDraft.id || "").trim();
  const nextDrafts = incomingId
    ? [incomingDraft, ...currentDrafts.filter((item) => String(item.id || "").trim() !== incomingId)]
    : [incomingDraft, ...currentDrafts];

  return nextDrafts.sort((left, right) => {
    const leftUpdatedAt = Date.parse(String(left.updated_at || left.created_at || ""));
    const rightUpdatedAt = Date.parse(String(right.updated_at || right.created_at || ""));
    if (!Number.isNaN(leftUpdatedAt) || !Number.isNaN(rightUpdatedAt)) {
      return (Number.isNaN(rightUpdatedAt) ? 0 : rightUpdatedAt) - (Number.isNaN(leftUpdatedAt) ? 0 : leftUpdatedAt);
    }
    return Number(right.id || 0) - Number(left.id || 0);
  });
}

function DraftsTool({
  drafts,
  onSendDraft,
  draftBusyId,
}: {
  drafts: OutboundDraft[];
  onSendDraft: (draft: OutboundDraft) => void | Promise<void>;
  draftBusyId: string;
}) {
  return (
    <SectionCard title="Taslaklar" subtitle="Dış aksiyonlar taslak ve onay akışıyla yönetilir.">
      {drafts.length ? (
        <div className="tool-card-grid">
          {drafts.slice(0, 10).map((draft) => {
            const draftId = String(draft.id);
            const isBusy = draftBusyId === draftId;
            const isSent = String(draft.delivery_status || "").trim() === "sent" || String(draft.dispatch_state || "").trim() === "completed";
            const isReady = String(draft.dispatch_state || "").trim() === "ready" || String(draft.delivery_status || "").trim() === "ready_to_send";
            const canSend = isDispatchableDraftChannel(draft.channel) && !isSent && !isReady;
            const actionLabel = String(draft.approval_status || "").trim() === "approved" ? "Gönder" : "Onayla ve gönder";

            return (
              <article className="list-item" key={draftId}>
                <div className="toolbar">
                  <strong>{draft.subject || draft.draft_type}</strong>
                  <StatusBadge>{disIletisimDurumuEtiketi(draft.approval_status, draft.delivery_status)}</StatusBadge>
                </div>
                <p className="list-item__meta">{draft.to_contact || "Hedef belirtilmedi"} · {kanalEtiketi(draft.channel)}</p>
                <p style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>{draft.body.slice(0, 180)}</p>
                {draft.dispatch_error ? <p className="list-item__meta">Son hata: {draft.dispatch_error}</p> : null}
                <div className="toolbar" style={{ marginTop: "0.85rem" }}>
                  <div className="list-item__meta" style={{ marginTop: 0 }}>
                    {isSent
                      ? "Bu taslak gönderildi."
                      : isReady
                        ? "Gönderim hazırlanıyor."
                        : String(draft.approval_status || "").trim() === "approved"
                          ? "Onay verildi. Gönderime hazırsın."
                          : "Önce onaylanır, sonra otomatik gönderilir."}
                  </div>
                  {canSend ? (
                    <button className="button button--secondary" type="button" disabled={isBusy} onClick={() => void onSendDraft(draft)}>
                      {isBusy ? "Gönderiliyor..." : actionLabel}
                    </button>
                  ) : null}
                </div>
              </article>
            );
          })}
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

function ChatBubble({
  message,
  onOpenTool,
  onApproveApproval,
  onRejectApproval,
  approvalBusyId,
  handledApprovalIds,
}: {
  message: AssistantThreadMessage;
  onOpenTool: (tool: ToolKey) => void;
  onApproveApproval: (approval: BubbleApprovalItem, message: AssistantThreadMessage) => void;
  onRejectApproval: (approval: BubbleApprovalItem) => void;
  approvalBusyId: string;
  handledApprovalIds: Record<string, string>;
}) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const attachmentBadges = sourceRefBadges(message.source_context);
  const proposedActions = messageMetaItems(message.source_context, "proposed_actions");
  const approvalRequests = bubbleApprovalItems(message.source_context);
  const memoryUpdates = messageMetaItems(message.source_context, "memory_updates");
  const webSearchResults = bubbleResultItems(message.source_context, "web_search_results");
  const travelOptions = bubbleResultItems(message.source_context, "travel_options");
  const visibleApprovalRequests = approvalRequests.filter((item) => !handledApprovalIds[item.id]);
  const visibleProposedActions = proposedActions.filter((item) => {
    const type = String(item.type || "").trim();
    if (type !== "navigation") {
      return true;
    }
    return !message.tool_suggestions.some(
      (suggestion) => sameActionLabel(suggestion.tool, item.tool) || sameActionLabel(suggestion.label, item.label),
    );
  });

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
        <div className="wa-bubble__text">{renderBubbleText(message.content)}</div>

        {isAssistant && (webSearchResults.length > 0 || travelOptions.length > 0 || message.tool_suggestions.length > 0 || visibleProposedActions.length > 0 || approvalRequests.length > 0 || memoryUpdates.length > 0) ? (
          <div className="wa-bubble__extras">
            {webSearchResults.length > 0 ? (
              <div className="wa-bubble__suggestions">
                <span className="wa-bubble__suggestion-label">{tr.assistant.webResultsTitle}</span>
                <div className="wa-bubble__result-grid">
                  {webSearchResults.slice(0, 3).map((item) => (
                    <article key={`${message.id}-${item.url || item.title}`} className="wa-bubble__result-card">
                      <strong>{item.title}</strong>
                      {item.snippet ? <p>{item.snippet}</p> : null}
                      {item.url ? (
                        <a className="wa-bubble__result-link" href={item.url} target="_blank" rel="noreferrer">
                          {tr.assistant.openExternalLink}
                        </a>
                      ) : null}
                    </article>
                  ))}
                </div>
              </div>
            ) : null}
            {travelOptions.length > 0 ? (
              <div className="wa-bubble__suggestions">
                <span className="wa-bubble__suggestion-label">{tr.assistant.travelResultsTitle}</span>
                <div className="wa-bubble__result-grid">
                  {travelOptions.slice(0, 3).map((item) => (
                    <article key={`${message.id}-travel-${item.url || item.title}`} className="wa-bubble__result-card">
                      <strong>{item.title}</strong>
                      {item.snippet ? <p>{item.snippet}</p> : null}
                      {item.url ? (
                        <a className="wa-bubble__result-link" href={item.url} target="_blank" rel="noreferrer">
                          {tr.assistant.openExternalLink}
                        </a>
                      ) : null}
                    </article>
                  ))}
                </div>
                <p className="wa-bubble__helper-text">{tr.assistant.travelFollowupHint}</p>
              </div>
            ) : null}
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
            {visibleProposedActions.length > 0 ? (
              <div className="wa-bubble__suggestions">
                <span className="wa-bubble__suggestion-label">Önerilen aksiyonlar</span>
                <div className="wa-bubble__suggestion-chips">
                  {visibleProposedActions.map((item, index) => (
                    <span key={`proposed-${message.id}-${index}`} className="wa-chip">
                      {String(item.label || item.tool || "Aksiyon")}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
            {visibleApprovalRequests.length > 0 ? (
              <div className="wa-bubble__approval-list">
                {visibleApprovalRequests.map((item) => {
                  const isBusy = approvalBusyId === item.id;
                  return (
                    <article key={item.id || `${message.id}-${item.title}`} className="wa-bubble__approval-card">
                      <div className="wa-bubble__approval-header">
                        <strong>{item.title || tr.assistant.approvalCardTitle}</strong>
                        <span className="wa-chip wa-chip--attachment">{kanalEtiketi(item.tool || "assistant")}</span>
                      </div>
                      {item.reason ? <p>{item.reason}</p> : null}
                      <div className="wa-bubble__approval-actions">
                        <button className="wa-bubble__action-btn wa-bubble__action-btn--primary" type="button" disabled={isBusy} onClick={() => onApproveApproval(item, message)}>
                          {isBusy ? tr.assistant.approvalProcessing : tr.assistant.approvalApprove}
                        </button>
                        <button className="wa-bubble__action-btn" type="button" disabled={isBusy} onClick={() => onRejectApproval(item)}>
                          {tr.assistant.approvalReject}
                        </button>
                      </div>
                    </article>
                  );
                })}
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
  const promptFromRoute = searchParams.get("prompt");

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
  const [googleStatus, setGoogleStatus] = useState<GoogleIntegrationStatus | null>(null);
  const [googleDriveFiles, setGoogleDriveFiles] = useState<GoogleDriveFile[]>([]);
  const [actions, setActions] = useState<SuggestedAction[]>([]);
  const [drafts, setDrafts] = useState<OutboundDraft[]>([]);
  const [matters, setMatters] = useState<Matter[]>([]);
  const [documents, setDocuments] = useState<WorkspaceDocument[]>([]);
  const [runtimeHealth, setRuntimeHealth] = useState<TelemetryHealth | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGoogleSyncing, setIsGoogleSyncing] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [isMessagesScrolling, setIsMessagesScrolling] = useState(false);
  const [isToolsScrolling, setIsToolsScrolling] = useState(false);
  const [drawerWidth, setDrawerWidth] = useState(initialDrawerWidth);
  const [isDrawerFullscreen, setIsDrawerFullscreen] = useState(false);
  const [isDrawerResizing, setIsDrawerResizing] = useState(false);
  const [isCalendarSyncing, setIsCalendarSyncing] = useState(false);
  const [isCalendarCreating, setIsCalendarCreating] = useState(false);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [isDragActive, setIsDragActive] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isVoiceModeActive, setIsVoiceModeActive] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceLastReply, setVoiceLastReply] = useState("");
  const [approvalBusyId, setApprovalBusyId] = useState("");
  const [draftBusyId, setDraftBusyId] = useState("");
  const [handledApprovalIds, setHandledApprovalIds] = useState<Record<string, string>>({});
  const [isSessionBriefDismissed, setIsSessionBriefDismissed] = useState(false);
  const [dismissedProactiveIds, setDismissedProactiveIds] = useState<string[]>(() => loadDismissedProactiveIds());
  const [error, setError] = useState("");

  // refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputWrapperRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const isFirstLoad = useRef(true);
  const messageScrollTimerRef = useRef<number | null>(null);
  const toolsScrollRef = useRef<HTMLDivElement>(null);
  const toolsScrollTimerRef = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const speechSeedPromptRef = useRef("");
  const voiceModeActiveRef = useRef(false);
  const attachmentStoreRef = useRef<ComposerAttachment[]>([]);
  const drawerResizeStartRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const googleAutoSyncRef = useRef<GoogleAutoSyncState>({ started: false, completed: false });
  const onboardingAutoStartRef = useRef(false);

  /* ── Scroll helpers ─────────────────────────────────────── */

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const container = messagesContainerRef.current;
    const normalizedBehavior = behavior === "instant" ? "auto" : behavior;

    if (container) {
      if (typeof container.scrollTo === "function") {
        container.scrollTo({
          top: container.scrollHeight,
          behavior: normalizedBehavior,
        });
      } else {
        container.scrollTop = container.scrollHeight;
      }
      return;
    }

    messagesEndRef.current?.scrollIntoView({ behavior: normalizedBehavior });
  }, []);

  const settleAtBottom = useCallback((frames = 3) => {
    let remainingFrames = Math.max(1, frames);
    const step = () => {
      scrollToBottom("auto");
      remainingFrames -= 1;
      if (remainingFrames > 0) {
        requestAnimationFrame(step);
      }
    };
    requestAnimationFrame(step);
  }, [scrollToBottom]);

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

  async function loadGoogleStatusData() {
    const response = await getGoogleIntegrationStatus(settings);
    setGoogleStatus(response);
    return response;
  }

  async function loadDocumentsToolData() {
    const [workspaceResponse, driveResponse] = await Promise.all([
      listWorkspaceDocuments(settings),
      listGoogleDriveFiles(settings),
    ]);
    setDocuments(workspaceResponse.items);
    setGoogleDriveFiles(driveResponse.items);
  }

  async function syncGoogleMirror(options: {
    refreshHome?: boolean;
    refreshToday?: boolean;
    refreshCalendar?: boolean;
    refreshDocuments?: boolean;
    silent?: boolean;
  } = {}) {
    if (!window.lawcopilotDesktop?.syncGoogleData) {
      throw new Error(text.syncDesktopOnly);
    }
    setIsGoogleSyncing(true);
    try {
      const result = await window.lawcopilotDesktop.syncGoogleData();
      await loadGoogleStatusData().catch(() => null);
      if (options.refreshHome !== false) {
        await loadHomeAndThread();
      }
      if (options.refreshToday) {
        const [agendaResponse, inboxResponse, actionsResponse] = await Promise.all([
          getAssistantAgenda(settings),
          getAssistantInbox(settings),
          getAssistantSuggestedActions(settings),
        ]);
        setAgenda(agendaResponse.items);
        setInbox(inboxResponse.items);
        setActions(actionsResponse.items);
      }
      if (options.refreshCalendar) {
        await loadCalendarToolData();
      }
      if (options.refreshDocuments) {
        await loadDocumentsToolData();
      }
      return String(result?.message || text.syncSuccess);
    } catch (err) {
      if (!options.silent) {
        throw err;
      }
      return "";
    } finally {
      setIsGoogleSyncing(false);
    }
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
      await loadDocumentsToolData();
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

  async function refreshAssistantSurface() {
    await loadHomeAndThread();
    if (selectedTool) {
      await loadToolData(selectedTool);
    }
  }

  /* ── Effects ────────────────────────────────────────────── */

  useEffect(() => {
    setIsLoading(true);
    isFirstLoad.current = true;
    googleAutoSyncRef.current = { started: false, completed: false };
    setHandledApprovalIds({});
    loadHomeAndThread()
      .then(async () => {
        const status = await loadGoogleStatusData().catch(() => null);
        if (!googleAutoSyncRef.current.started && window.lawcopilotDesktop?.syncGoogleData && shouldAutoSyncGoogle(status)) {
          googleAutoSyncRef.current.started = true;
          await syncGoogleMirror({
            refreshHome: true,
            refreshToday: selectedTool === "today",
            refreshCalendar: selectedTool === "calendar",
            refreshDocuments: selectedTool === "documents",
            silent: true,
          });
          googleAutoSyncRef.current.completed = true;
        }
        setError("");
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, [settings.baseUrl, settings.token]);

  // scroll to bottom on first load or when messages arrive
  useEffect(() => {
    if (threadMessages.length > 0 && isFirstLoad.current) {
      settleAtBottom();
      isFirstLoad.current = false;
    }
  }, [settleAtBottom, threadMessages]);

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
    window.speechSynthesis?.cancel();
  }, []);

  useEffect(() => {
    window.localStorage.setItem(DRAWER_WIDTH_STORAGE_KEY, String(drawerWidth));
  }, [drawerWidth]);

  useEffect(() => {
    function handleViewportResize() {
      setDrawerWidth((current) => clampDrawerWidth(current, window.innerWidth));
    }

    window.addEventListener("resize", handleViewportResize);
    return () => window.removeEventListener("resize", handleViewportResize);
  }, []);

  useEffect(() => {
    if (!isDrawerResizing) {
      return;
    }

    function handlePointerMove(event: PointerEvent) {
      const resizeStart = drawerResizeStartRef.current;
      if (!resizeStart) {
        return;
      }
      const deltaX = event.clientX - resizeStart.startX;
      setDrawerWidth(clampDrawerWidth(resizeStart.startWidth - deltaX, window.innerWidth));
    }

    function finishResize() {
      drawerResizeStartRef.current = null;
      setIsDrawerResizing(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", finishResize);
    window.addEventListener("pointercancel", finishResize);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", finishResize);
      window.removeEventListener("pointercancel", finishResize);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDrawerResizing]);

  const quickPrompts = useMemo(
    () => {
      return [
        text.quickPromptToday,
        text.quickPromptMissing,
        text.quickPromptClientUpdate,
        text.quickPromptCalendar,
        text.quickPromptSimilarity,
        text.quickPromptWebSearch,
        text.quickPromptTravel,
      ].filter((item, index, source) => source.indexOf(item) === index);
    },
    [home?.onboarding, text],
  );
  const onboardingGuidance = home?.onboarding && !home.onboarding.complete ? home.onboarding : null;
  const attachmentHint = settings.currentMatterId ? text.chatAttachmentHintBound : text.chatAttachmentHintLoose;
  const canSubmit = Boolean(prompt.trim() || attachments.length);
  const proactiveSuggestions = home?.proactive_suggestions || [];
  const visibleProactiveSuggestions = useMemo(
    () => proactiveSuggestions.filter((item) => !dismissedProactiveIds.includes(String(item.id || "").trim())),
    [dismissedProactiveIds, proactiveSuggestions],
  );
  const sessionBriefSuggestions = visibleProactiveSuggestions.slice(0, 2);
  const homeSummaryText = useMemo(
    () => buildHomeSummaryText(home, text.threadEmptyDescription),
    [home, text.threadEmptyDescription],
  );
  const googleAssistantAccessReady = Boolean(
    googleStatus?.configured
      && (googleStatus.gmail_connected || googleStatus.calendar_connected || googleStatus.drive_connected),
  );
  const googleAssistantAccessSummary = useMemo(() => {
    if (!googleStatus?.configured) {
      return "";
    }
    if (googleAssistantAccessReady) {
      return "Gmail, Takvim ve Drive verileri asistanın kullanımına açık. Sorularınızda bu kaynaklara da bakabilirim.";
    }
    return "Google hesabı bağlandı. İlk eşitleme tamamlandığında Gmail, Takvim ve Drive bilgileri burada görünür.";
  }, [googleAssistantAccessReady, googleStatus?.configured]);
  const voiceStatusLabel = isSubmitting
    ? text.chatVoiceModeThinking
    : isSpeaking
      ? text.chatVoiceModeSpeaking
      : isListening
        ? text.chatVoiceModeListening
        : text.chatVoiceModeReady;

  useEffect(() => {
    const container = messagesContainerRef.current;
    const inputWrapper = inputWrapperRef.current;
    if (!container || !inputWrapper) {
      return;
    }

    const syncBottomClearance = () => {
      const footerHeight = Math.ceil(inputWrapper.getBoundingClientRect().height);
      container.style.setProperty("--wa-bottom-clearance", `${footerHeight + 32}px`);
    };

    syncBottomClearance();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", syncBottomClearance);
      return () => window.removeEventListener("resize", syncBottomClearance);
    }

    const observer = new ResizeObserver(() => syncBottomClearance());
    observer.observe(inputWrapper);
    window.addEventListener("resize", syncBottomClearance);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", syncBottomClearance);
    };
  }, [attachments.length, isSessionBriefDismissed, isVoiceModeActive, sessionBriefSuggestions.length, threadMessages.length]);

  /* ── Handlers ───────────────────────────────────────────── */

  useEffect(() => {
    if (!promptFromRoute) {
      return;
    }
    setPrompt((current) => (current.trim() ? current : promptFromRoute));
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete("prompt");
    setSearchParams(nextParams, { replace: true });
  }, [promptFromRoute, searchParams, setSearchParams]);

  useEffect(() => {
    if (threadMessages.length === 0) {
      setIsSessionBriefDismissed(false);
    }
  }, [threadMessages.length]);

  useEffect(() => {
    persistDismissedProactiveIds(dismissedProactiveIds);
  }, [dismissedProactiveIds]);

  useEffect(() => {
    if (onboardingAutoStartRef.current) {
      return;
    }
    if (!home?.onboarding || home.onboarding.complete || home.onboarding.blocked_by_setup) {
      return;
    }
    if (threadMessages.length > 0 || isLoading || isSubmitting || promptFromRoute) {
      return;
    }
    onboardingAutoStartRef.current = true;
    void handleSubmit(home.onboarding.starter_prompts?.[0] || "Tanışma görüşmesini başlatalım.");
  }, [home, isLoading, isSubmitting, promptFromRoute, threadMessages.length]);

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

  function startListening(mode: "normal" | "voice") {
    const Recognition = getSpeechRecognitionFactory();
    if (!Recognition) {
      setError(text.chatMicUnsupported);
      if (mode === "voice") {
        setIsVoiceModeActive(false);
        voiceModeActiveRef.current = false;
      }
      return;
    }
    try {
      const recognition = speechRecognitionRef.current || new Recognition();
      recognition.lang = "tr-TR";
      recognition.interimResults = true;
      recognition.continuous = mode === "normal";
      
      let lastTranscript = "";

      recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map((result) => result[0]?.transcript || "")
          .join(" ")
          .trim();
        lastTranscript = transcript;
        setPrompt(`${speechSeedPromptRef.current}${transcript}`.trimStart());
        if (mode === "voice") {
          setVoiceTranscript(transcript);
        }
      };

      recognition.onend = () => {
        setIsListening(false);
        if (mode === "voice" && voiceModeActiveRef.current) {
          const finalPrompt = `${speechSeedPromptRef.current}${lastTranscript}`.trimStart();
          if (finalPrompt) {
            handleSubmit(finalPrompt);
          } else {
            startListening("voice");
          }
        }
      };

      recognition.onerror = () => {
        setIsListening(false);
        if (mode === "voice" && voiceModeActiveRef.current) {
          startListening("voice");
        } else {
          setError(text.chatMicError);
        }
      };

      speechRecognitionRef.current = recognition;
      speechSeedPromptRef.current = prompt.trim() ? `${prompt.trim()} ` : "";
      recognition.start();
      setIsListening(true);
      setError("");
    } catch {
      setError(text.chatMicError);
      setIsListening(false);
      if (mode === "voice") {
        setIsVoiceModeActive(false);
        voiceModeActiveRef.current = false;
      }
    }
  }

  function handleMicToggle() {
    if (isVoiceModeActive) {
      handleVoiceModeToggle();
      return;
    }
    if (isListening) {
      stopListening();
      return;
    }
    startListening("normal");
  }

  function speakAssistantMessage(textContent: string) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(speechTextFromMessage(textContent));
    utterance.lang = "tr-TR";
    const preferredVoice = resolveSpeechVoice();
    if (preferredVoice) {
      utterance.voice = preferredVoice;
    }
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => {
      setIsSpeaking(false);
      if (voiceModeActiveRef.current) {
        startListening("voice");
      }
    };
    utterance.onerror = () => {
      setIsSpeaking(false);
      if (voiceModeActiveRef.current) {
        startListening("voice");
      }
    };
    window.speechSynthesis.speak(utterance);
  }

  function handleVoiceModeToggle() {
    if (isVoiceModeActive) {
      setIsVoiceModeActive(false);
      voiceModeActiveRef.current = false;
      stopListening();
      window.speechSynthesis?.cancel();
      setIsSpeaking(false);
      setVoiceTranscript("");
      return;
    }
    setVoiceTranscript("");
    setVoiceLastReply("");
    setIsVoiceModeActive(true);
    voiceModeActiveRef.current = true;
    startListening("voice");
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

  async function prepareAttachmentSourceRefs(selectedAttachments: ComposerAttachment[], matterId?: number) {
    const sourceRefs: Array<Record<string, unknown>> = [];
    let partialFallback = false;

    if (!selectedAttachments.length) {
      return { sourceRefs, partialFallback };
    }

    const uploadResults = await Promise.allSettled(
      selectedAttachments.map(async (attachment) => {
        if (!matterId) {
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
        const response = await uploadMatterDocument(settings, matterId, {
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

  async function handleSubmit(nextPrompt?: string, options: { matterId?: number } = {}) {
    const content = (nextPrompt ?? prompt).trim();
    const selectedAttachments = [...attachments];
    const targetMatterId = options.matterId ?? settings.currentMatterId ?? undefined;
    const finalContent = content || (selectedAttachments.length ? text.chatDefaultAttachmentPrompt : "");
    if (!finalContent) {
      return;
    }
    setIsSubmitting(true);
    setPrompt("");
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
        const prepared = await prepareAttachmentSourceRefs(selectedAttachments, targetMatterId);
        sourceRefs = prepared.sourceRefs;
        if (prepared.partialFallback) {
          setError(text.chatAttachmentPartialFallback);
        }
      }
      const response = await postAssistantThreadMessage(settings, {
        content: finalContent,
        matter_id: targetMatterId,
        source_refs: sourceRefs,
      });
      setThreadMessages(response.messages);
      if (response.draft_preview) {
        setDrafts((current) => mergeDraftIntoList(current, response.draft_preview as OutboundDraft));
      }
      const homeResponse = await getAssistantHome(settings);
      setHome(homeResponse);
      if (selectedTool) {
        await loadToolData(selectedTool).catch(() => null);
      }
      if (response.draft_preview) {
        setDrafts((current) => mergeDraftIntoList(current, response.draft_preview as OutboundDraft));
      }
      if (!selectedAttachments.length) {
        setError("");
      }
      clearAttachments();
      requestAnimationFrame(() => scrollToBottom());
      if (voiceModeActiveRef.current) {
        const lastMsg = response.messages[response.messages.length - 1];
        if (lastMsg && lastMsg.role === "assistant") {
          setVoiceLastReply(lastMsg.content);
          setVoiceTranscript("");
          speakAssistantMessage(lastMsg.content);
        } else {
          startListening("voice");
        }
      }
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

  async function handleApproveFromBubble(approval: BubbleApprovalItem, message: AssistantThreadMessage) {
    if (!approval.id) {
      return;
    }
    setApprovalBusyId(approval.id);
    try {
      const response = (await approveAssistantApproval(settings, approval.id, { note: "Sohbet içinden onaylandı." })) as Record<string, unknown>;
      const draft = ((response.draft && typeof response.draft === "object" ? response.draft : null)
        || (message.draft_preview && typeof message.draft_preview === "object" ? message.draft_preview : null)) as Record<string, unknown> | null;
      const action = (response.action && typeof response.action === "object"
        ? response.action
        : (message.source_context?.assistant_action && typeof message.source_context.assistant_action === "object" ? message.source_context.assistant_action : null)) as Record<string, unknown> | null;

      setHandledApprovalIds((current) => ({ ...current, [approval.id]: "approved" }));

      if (response.dispatch_mode === "ready_to_send" && draft && window.lawcopilotDesktop?.dispatchApprovedAction) {
        await window.lawcopilotDesktop.dispatchApprovedAction({
          action,
          draft,
          actionId: Number(action?.id || approval.action_id || 0) || undefined,
          draftId: Number(draft?.id || approval.draft_id || 0) || undefined,
          channel: String(draft?.channel || action?.target_channel || approval.tool || "").trim(),
        });
      }

      await refreshAssistantSurface();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Onay işlemi tamamlanamadı.");
    } finally {
      setApprovalBusyId("");
    }
  }

  async function handleRejectFromBubble(approval: BubbleApprovalItem) {
    if (!approval.id) {
      return;
    }
    setApprovalBusyId(approval.id);
    try {
      await rejectAssistantApproval(settings, approval.id, { note: "Sohbet içinden vazgeçildi." });
      setHandledApprovalIds((current) => ({ ...current, [approval.id]: "rejected" }));
      await refreshAssistantSurface();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aksiyon kapatılamadı.");
    } finally {
      setApprovalBusyId("");
    }
  }

  async function handleSendDraftFromTool(draft: OutboundDraft) {
    const draftId = Number(draft.id || 0);
    if (!draftId) {
      return;
    }
    setDraftBusyId(String(draft.id));
    try {
      let response: Record<string, unknown>;
      try {
        response = await sendAssistantDraft(settings, draftId, "Taslaklar panelinden onaylanıp gönderildi.") as Record<string, unknown>;
      } catch (err) {
        const message = err instanceof Error ? err.message : "";
        if (!message.includes("onaylanmalıdır")) {
          throw err;
        }
        const approvals = await getAssistantApprovals(settings);
        const approval = approvals.items.find((item) => Number(item.draft_id || item.draft?.id || 0) === draftId);
        if (!approval?.id) {
          throw err;
        }
        response = await approveAssistantApproval(settings, approval.id, { note: "Taslaklar panelinden onaylanıp gönderildi." }) as Record<string, unknown>;
      }
      const nextDraft = (response.draft && typeof response.draft === "object" ? response.draft : draft) as Record<string, unknown>;
      const nextAction = (response.action && typeof response.action === "object" ? response.action : null) as Record<string, unknown> | null;

      if (response.dispatch_mode === "ready_to_send") {
        if (!window.lawcopilotDesktop?.dispatchApprovedAction) {
          throw new Error("Masaüstü gönderim köprüsü hazır değil.");
        }
        await window.lawcopilotDesktop.dispatchApprovedAction({
          action: nextAction,
          draft: nextDraft,
          actionId: Number(nextAction?.id || 0) || undefined,
          draftId,
          channel: String(nextDraft?.channel || draft.channel || "").trim(),
        });
      }

      await refreshAssistantSurface();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Taslak gönderilemedi.");
      await refreshAssistantSurface().catch(() => null);
    } finally {
      setDraftBusyId("");
    }
  }

  async function handleResetThread() {
    setIsResetting(true);
    try {
      await resetAssistantThread(settings);
      setHandledApprovalIds({});
      await loadHomeAndThread();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : text.queryError);
    } finally {
      setIsResetting(false);
    }
  }

  async function handleSyncGoogleCalendar() {
    try {
      setIsCalendarSyncing(true);
      return await syncGoogleMirror({ refreshToday: true, refreshCalendar: true });
    } finally {
      setIsCalendarSyncing(false);
    }
  }

  async function handleSyncGoogleDocuments() {
    return syncGoogleMirror({ refreshDocuments: true, refreshToday: true });
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
    setIsDrawerFullscreen(false);
    const params = new URLSearchParams(searchParams);
    params.delete("tool");
    setSearchParams(params, { replace: true });
  }

  function handleProactiveSuggestion(item: AssistantHomeSuggestion) {
    setIsSessionBriefDismissed(true);
    if (item.id) {
      setDismissedProactiveIds((current) => {
        const nextId = String(item.id).trim();
        if (!nextId || current.includes(nextId)) {
          return current;
        }
        return [...current, nextId];
      });
    }
    if (item.prompt) {
      void handleSubmit(item.prompt, { matterId: item.matter_id || undefined });
      return;
    }
    if (isToolKey(item.tool)) {
      openTool(item.tool);
    }
  }

  function handleDrawerResizeStart(event: ReactPointerEvent<HTMLButtonElement>) {
    if (isDrawerFullscreen) {
      return;
    }
    event.preventDefault();
    drawerResizeStartRef.current = {
      startX: event.clientX,
      startWidth: drawerWidth,
    };
    setIsDrawerResizing(true);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  function handleDrawerResizeReset() {
    setDrawerWidth(clampDrawerWidth(DEFAULT_DRAWER_WIDTH, window.innerWidth));
  }

  const assistantBodyStyle = useMemo(
    () => ({ "--assistant-drawer-width": `${drawerWidth}px` } as CSSProperties),
    [drawerWidth],
  );

  /* ── Render ─────────────────────────────────────────────── */

  if (isLoading) {
    return <LoadingSpinner label="Asistan yükleniyor..." />;
  }

  return (
    <div className="assistant-vnext">
      <div
        className={`assistant-vnext__body${selectedTool ? " assistant-vnext__body--with-drawer" : ""}${selectedTool && isDrawerFullscreen ? " assistant-vnext__body--drawer-fullscreen" : ""}${isDrawerResizing ? " assistant-vnext__body--drawer-resizing" : ""}`}
        style={selectedTool ? assistantBodyStyle : undefined}
      >
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
                    <ChatBubble
                      key={message.id}
                      message={message}
                      onOpenTool={openTool}
                      onApproveApproval={handleApproveFromBubble}
                      onRejectApproval={handleRejectFromBubble}
                      approvalBusyId={approvalBusyId}
                      handledApprovalIds={handledApprovalIds}
                    />
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
                  <h2 className="wa-welcome__title">{home?.greeting_title || text.welcomeTitle}</h2>
                  <p className="wa-welcome__subtitle">
                    {homeSummaryText}
                  </p>
                  {home?.counts ? (
                    <div className="wa-welcome__badges">
                      <span className="wa-badge">{`${home.counts.agenda} ajanda`}</span>
                      <span className="wa-badge">{`${home.counts.inbox} iletişim`}</span>
                      <span className="wa-badge">{`${home.counts.calendar_today} takvim`}</span>
                      <span className="wa-badge">{`${home.counts.drafts_pending} onay`}</span>
                    </div>
                  ) : null}

                  {googleStatus?.configured ? (
                    <div className="callout callout--accent wa-welcome__card">
                      <strong>{googleStatus.account_label || "Google hesabı bağlı"}</strong>
                      <p className="list-item__meta" style={{ marginTop: "0.45rem", marginBottom: "0.75rem" }}>
                        {googleAssistantAccessSummary}
                      </p>
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "center" }}>
                        <StatusBadge tone={googleStatus.gmail_connected ? "accent" : "warning"}>
                          {googleStatus.gmail_connected
                            ? `${googleStatus.email_thread_count || 0} Gmail konuşması`
                            : "Gmail henüz eşitlenmedi"}
                        </StatusBadge>
                        <StatusBadge tone={googleStatus.calendar_connected ? "accent" : "warning"}>
                          {googleStatus.calendar_connected
                            ? `${googleStatus.calendar_event_count || 0} Takvim kaydı`
                            : "Takvim henüz eşitlenmedi"}
                        </StatusBadge>
                        <StatusBadge tone={googleStatus.drive_connected ? "accent" : "warning"}>
                          {googleStatus.drive_connected
                            ? `${googleStatus.drive_file_count || 0} Drive dosyası`
                            : "Drive henüz eşitlenmedi"}
                        </StatusBadge>
                        {googleStatus.last_sync_at ? (
                          <StatusBadge>{`Son eşitleme ${dateLabel(googleStatus.last_sync_at)}`}</StatusBadge>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {visibleProactiveSuggestions.length ? (
                    <div className="callout callout--accent wa-welcome__card">
                      <strong>{text.proactiveTitle}</strong>
                      <div className="list" style={{ marginTop: "0.75rem" }}>
                        {visibleProactiveSuggestions.map((item) => (
                          <article className="list-item" key={item.id}>
                            <div className="toolbar">
                              <strong>{item.title}</strong>
                              {item.priority ? (
                                <StatusBadge tone={item.priority === "high" ? "warning" : "accent"}>{item.priority}</StatusBadge>
                              ) : null}
                            </div>
                            <p className="list-item__meta">{item.details}</p>
                            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                              <button className="button button--secondary" type="button" onClick={() => handleProactiveSuggestion(item)}>
                                {item.action_label || text.proactiveDefaultAction}
                              </button>
                              {isToolKey(item.tool) ? (
                                <button className="button button--ghost" type="button" onClick={() => openTool(item.tool as ToolKey)}>
                                  {toolLabel(item.tool as ToolKey)}
                                </button>
                              ) : null}
                            </div>
                          </article>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {home?.requires_setup?.length ? (
                    <div className="callout wa-welcome__card wa-welcome__card--narrow">
                      <strong>Kurulum eksikleri</strong>
                      <div className="list" style={{ marginTop: "0.75rem" }}>
                        {home.requires_setup.map((item) => (
                          <article className="list-item" key={item.id}>
                            <strong>{item.title}</strong>
                            <p className="list-item__meta">{item.details}</p>
                            <Link className="button button--secondary" to={setupLinkForItem(item)}>
                              {text.openSettingsAction}
                            </Link>
                          </article>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {home?.onboarding && !home.onboarding.complete ? (
                    <div className="callout callout--accent wa-welcome__card">
                      <strong>Kişisel asistan tanışma görüşmesi</strong>
                      <p className="list-item__meta" style={{ marginTop: "0.45rem" }}>
                        {home.onboarding.interview_intro || "Asistan önce kendi rolünü, sonra seni ve alışkanlıklarını tanımak için soruları tek tek sorar."}
                      </p>
                      {home.onboarding.interview_topics?.length ? (
                        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
                          {home.onboarding.interview_topics.slice(0, 6).map((item) => (
                            <span key={item} className="wa-badge">{item}</span>
                          ))}
                        </div>
                      ) : null}
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

            {onboardingGuidance ? (
              <div className="callout callout--accent" style={{ margin: "0 1rem 1rem" }}>
                <div className="toolbar" style={{ alignItems: "flex-start" }}>
                  <div>
                    <strong>Tanışma röportajı</strong>
                    <p style={{ margin: "0.35rem 0 0" }}>
                      {onboardingGuidance.interview_intro || "Asistan önce kendi rolünü, sonra sizi ve tercihlerinizi tanımaya çalışır."}
                    </p>
                  </div>
                  <Link className="button button--secondary" to="/onboarding">
                    Kurulum özeti
                  </Link>
                </div>
                {onboardingGuidance.next_question ? (
                  <div className="callout" style={{ marginTop: "0.75rem" }}>
                    <strong>Şu anki soru</strong>
                    <p style={{ marginBottom: 0 }}>{onboardingGuidance.next_question}</p>
                  </div>
                ) : null}
              </div>
            ) : null}

            {/* Input area */}
            <div className="wa-input-wrapper" ref={inputWrapperRef}>
              {threadMessages.length > 0 && home && !isSessionBriefDismissed ? (
                <div className="callout callout--accent wa-session-brief" style={{ marginBottom: "0.85rem" }}>
                  <div className="wa-session-brief__header">
                    <strong className="wa-session-brief__title">{home.greeting_title || text.welcomeTitle}</strong>
                    <button
                      className="wa-callout-close"
                      type="button"
                      aria-label="Özet panelini kapat"
                      title="Kapat"
                      onClick={() => setIsSessionBriefDismissed(true)}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M18 6 6 18" />
                        <path d="m6 6 12 12" />
                      </svg>
                    </button>
                  </div>
                  <p className="list-item__meta wa-session-brief__body" style={{ marginBottom: sessionBriefSuggestions.length ? "0.75rem" : 0 }}>
                    {homeSummaryText}
                  </p>
                  {sessionBriefSuggestions.length ? (
                    <div className="wa-session-brief__actions">
                      {sessionBriefSuggestions.map((item) => (
                        <button key={`session-${item.id}`} className="button button--ghost" type="button" onClick={() => handleProactiveSuggestion(item)}>
                          {item.action_label || item.title}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {isVoiceModeActive ? (
                <div className="wa-voice-panel" aria-live="polite">
                  <div className="wa-voice-panel__header">
                    <div className="wa-voice-panel__copy">
                      <strong>{text.chatVoiceModeTitle}</strong>
                      <span>{text.chatVoiceModeSubtitle}</span>
                    </div>
                    <button
                      className="wa-voice-panel__close"
                      type="button"
                      onClick={handleVoiceModeToggle}
                      aria-label={text.chatVoiceModeStop}
                      title={text.chatVoiceModeStop}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M18 6 6 18" />
                        <path d="m6 6 12 12" />
                      </svg>
                    </button>
                  </div>

                  <button
                    className={`wa-voice-panel__orb${isListening ? " wa-voice-panel__orb--listening" : ""}${isSpeaking ? " wa-voice-panel__orb--speaking" : ""}${isSubmitting ? " wa-voice-panel__orb--thinking" : ""}`}
                    type="button"
                    onClick={() => {
                      if (isSpeaking) {
                        window.speechSynthesis?.cancel();
                        setIsSpeaking(false);
                        if (voiceModeActiveRef.current) {
                          startListening("voice");
                        }
                        return;
                      }
                      if (isListening) {
                        stopListening();
                        return;
                      }
                      startListening("voice");
                    }}
                    aria-label={isListening ? text.chatMicStop : text.chatVoiceModeStart}
                    title={isListening ? text.chatMicStop : text.chatVoiceModeStart}
                  >
                    <span className="wa-voice-panel__orb-ring" />
                    <span className="wa-voice-panel__orb-core">
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3z" />
                        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                        <path d="M12 19v3" />
                      </svg>
                    </span>
                  </button>

                  <div className="wa-voice-panel__status">
                    <strong>{voiceStatusLabel}</strong>
                    <span>{text.chatVoiceModeHint}</span>
                  </div>

                  <div className="wa-voice-panel__cards">
                    <article className="wa-voice-panel__card">
                      <span className="wa-voice-panel__card-label">{text.chatVoiceModeTranscriptLabel}</span>
                      <p>{voiceTranscript || prompt || text.chatVoiceModeTranscriptEmpty}</p>
                    </article>
                    <article className="wa-voice-panel__card">
                      <span className="wa-voice-panel__card-label">{text.chatVoiceModeReplyLabel}</span>
                      <p>{voiceLastReply || text.chatVoiceModeReplyEmpty}</p>
                    </article>
                  </div>
                </div>
              ) : null}
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
              {!isVoiceModeActive ? (
                <form
                  className="wa-input-area"
                  onSubmit={(event) => {
                    event.preventDefault();
                    handleSubmit();
                  }}
                >
                  <div className="wa-input-actions wa-input-actions--left">
                    <button className="wa-icon-btn" type="button" title={text.chatAttachFile} aria-label={text.chatAttachFile} onClick={openAttachmentPicker}>
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
                      className="wa-voice-launch"
                      type="button"
                      title={text.chatVoiceModeStart}
                      aria-label={text.chatVoiceModeStart}
                      onClick={handleVoiceModeToggle}
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M2 10v3" />
                        <path d="M6 6v11" />
                        <path d="M10 3v18" />
                        <path d="M14 8v7" />
                        <path d="M18 5v13" />
                        <path d="M22 10v3" />
                      </svg>
                      <span>{text.chatVoiceModeButton}</span>
                    </button>
                    <button
                      className={`wa-icon-btn${isListening ? " wa-icon-btn--active" : ""}`}
                      type="button"
                      title={isListening ? text.chatMicStop : text.chatMicStart}
                      aria-label={isListening ? text.chatMicStop : text.chatMicStart}
                      onClick={handleMicToggle}
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3z" />
                        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                        <path d="M12 19v3" />
                      </svg>
                    </button>
                    <button className="wa-send-btn" type="submit" disabled={isSubmitting || !canSubmit} title={text.chatSend} aria-label={text.chatSend}>
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
              ) : null}
              <div className="wa-input-footer">
                {error ? (
                  <span style={{ color: "var(--danger)" }}>{error}</span>
                ) : isSpeaking ? (
                  <span>{text.chatVoiceModeSpeaking}</span>
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
          <button
            className={`assistant-tools-resizer${isDrawerResizing ? " assistant-tools-resizer--active" : ""}`}
            type="button"
            onPointerDown={handleDrawerResizeStart}
            onDoubleClick={handleDrawerResizeReset}
            aria-label={text.toolsResizeHandle}
            title={text.toolsResizeHandle}
          >
            <span />
            <span />
            <span />
          </button>
        ) : null}

        {selectedTool ? (
          <aside className="assistant-tools-drawer">
            <SectionCard
              className="assistant-tools-panel"
              title={text.toolsTitle}
              subtitle={text.toolsSubtitle}
              actions={
                <div className="assistant-tools-actions">
                  <button
                    className="assistant-tools-icon-btn"
                    type="button"
                    onClick={() => setIsDrawerFullscreen((current) => !current)}
                    aria-label={isDrawerFullscreen ? text.toolsExitFullscreen : text.toolsEnterFullscreen}
                    title={isDrawerFullscreen ? text.toolsExitFullscreen : text.toolsEnterFullscreen}
                  >
                    {isDrawerFullscreen ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M9 15H5v4" />
                        <path d="M15 9h4V5" />
                        <path d="M19 9l-5-5" />
                        <path d="M5 15l5 5" />
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M15 3h6v6" />
                        <path d="M9 21H3v-6" />
                        <path d="M21 3l-7 7" />
                        <path d="M3 21l7-7" />
                      </svg>
                    )}
                  </button>
                  <button
                    className="assistant-tools-icon-btn"
                    type="button"
                    onClick={closeTool}
                    aria-label={text.toolsClose}
                    title={text.toolsClose}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M18 6 6 18" />
                      <path d="m6 6 12 12" />
                    </svg>
                  </button>
                </div>
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
                {selectedTool === "matters" ? <MattersTool matters={matters} googleStatus={googleStatus} /> : null}
                {selectedTool === "documents" ? (
                  <DocumentsTool
                    documents={documents}
                    driveFiles={googleDriveFiles}
                    googleStatus={googleStatus}
                    canSyncGoogle={Boolean(window.lawcopilotDesktop?.syncGoogleData)}
                    isSyncing={isGoogleSyncing}
                    onSyncGoogle={handleSyncGoogleDocuments}
                  />
                ) : null}
                {selectedTool === "drafts" ? <DraftsTool drafts={drafts} onSendDraft={handleSendDraftFromTool} draftBusyId={draftBusyId} /> : null}
                {selectedTool === "runtime" ? <RuntimeTool health={runtimeHealth} /> : null}
              </div>
            </SectionCard>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
