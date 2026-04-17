import { Fragment, memo, startTransition, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ChangeEvent, type DragEvent, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useAppContext } from "../app/AppContext";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSpinner } from "../components/common/LoadingSpinner";
import { SectionCard } from "../components/common/SectionCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { tr } from "../i18n/tr";
import { buildDocumentViewerPath } from "../lib/documentViewer";
import { belgeDurumuEtiketi, disIletisimDurumuEtiketi, dosyaBasligiEtiketi, dosyaDurumuEtiketi, kanalEtiketi, sistemKaynagiEtiketi, taslakTipiEtiketi } from "../lib/labels";
import { openWorkspaceDocument } from "../lib/workspaceDocuments";
import { invalidateEmbeddedPersonalModelCache } from "./PersonalModelPage";
import {
  analyzeAssistantAttachment,
  applyAssistantMemoryCorrection,
  createAssistantThread,
  createAssistantShareDraft,
  createAgentRun,
  approveAssistantApproval,
  pauseAssistantAction,
  createAssistantCalendarEvent,
  deleteAssistantThread,
  getAgentRun,
  getAgentRunEvents,
  getAgentTools,
  getAssistantAgenda,
  getAssistantApprovals,
  getAssistantCalendar,
  getAssistantConnectorSyncStatus,
  getAssistantHome,
  getAssistantInbox,
  getAssistantOrchestrationStatus,
  getAssistantSuggestedActions,
  getAssistantThread,
  getAssistantContactProfiles,
  listAssistantStarredMessages,
  listAssistantThreads,
  logAssistantCoachingProgress,
  getGoogleIntegrationStatus,
  listAssistantDrafts,
  listGoogleDriveFiles,
  listMatters,
  listWorkspaceDocuments,
  postAssistantThreadMessage,
  retryAssistantActionDispatch,
  scheduleAssistantActionCompensation,
  removeAssistantDraft,
  resumeAssistantAction,
  streamAssistantThreadMessage,
  updateAssistantThreadMessageFeedback,
  updateAssistantThreadMessageStar,
  rejectAssistantApproval,
  resetAssistantThreadById,
  resetAssistantThread,
  runAssistantConnectorSync,
  runAssistantOrchestration,
  sendAssistantDraft,
  upsertAssistantCoachingGoal,
  updateAssistantThread,
  updateAssistantLocationContext,
  uploadMatterDocument,
  evaluateAssistantTriggers,
} from "../services/lawcopilotApi";
import type {
  AgentRun,
  AgentRunApproval,
  AgentRunArtifact,
  AgentRunEvent,
  AgentToolCatalogItem,
  AssistantActionAvailableControls,
  AssistantActionCase,
  AssistantActionCompensationPlan,
  AssistantActionCaseStep,
  AssistantAgendaItem,
  AssistantApproval,
  AssistantCalendarItem,
  AssistantContactProfile,
  AssistantRelationshipProfile,
  AssistantDispatchAttempt,
  AssistantHomeResponse,
  AssistantShareChannel,
  AssistantThreadMessage,
  AssistantThreadResponse,
  AssistantThreadSummary,
  Citation,
  Draft,
  GoogleDriveFile,
  GoogleIntegrationStatus,
  Matter,
  OutboundDraft,
  SuggestedAction,
  WorkspaceDocument,
} from "../types/domain";

const TOOL_KEYS = ["today", "calendar", "matters", "documents", "drafts"] as const;
type ToolKey = (typeof TOOL_KEYS)[number];

const PAGE_SIZE = 30;
const MAX_ATTACHMENTS = 10;
const DEFAULT_DRAWER_WIDTH = 456;
const MIN_DRAWER_WIDTH = 360;
const MAX_DRAWER_WIDTH = 1120;
const DRAWER_WIDTH_STORAGE_KEY = "lawcopilot.assistant.drawer.width";
const DISMISSED_PROACTIVE_STORAGE_KEY = "lawcopilot.assistant.proactive.dismissed";
const SESSION_BRIEF_DISMISSED_STORAGE_KEY = ["lawcopilot", "assistant", "ozetKapatildi"].join(".");
const SELECTED_THREAD_STORAGE_KEY = "lawcopilot.assistant.thread.selected";
const VOICE_PREFERENCE_STORAGE_KEY = "lawcopilot.assistant.voice.preference";
const VOICE_PLAYBACK_PREFERENCE_STORAGE_KEY = "lawcopilot.assistant.voice.playback";
const SETTINGS_PROFILE_CACHE_KEY = "lawcopilot.settings.profile";
const SETTINGS_ASSISTANT_RUNTIME_CACHE_KEY = "lawcopilot.settings.assistant-runtime-profile";
const SETTINGS_MEMORY_UPDATE_EVENT = "lawcopilot:memory-updates";
const ASSISTANT_LIVE_REFRESH_INTERVAL_MS = 60000;
const AUTO_VOICE_PREFERENCE = "__auto__";
const VOICE_AUTO_SUBMIT_SILENCE_MS = 2000;
const VOICE_AUDIO_SILENCE_THRESHOLD = 0.028;
const VOICE_INTERRUPT_AUDIO_THRESHOLD = 0.05;
const VOICE_INTERRUPT_HOLD_MS = 180;
const STARRED_MESSAGE_HIGHLIGHT_TIMEOUT_MS = 2400;
const AUTOMATION_ALLOWED_FIELDS = new Set([
  "enabled",
  "autoSyncConnectedServices",
  "desktopNotifications",
  "importantContacts",
  "doNotAutoReplyContacts",
  "alertViaWhatsApp",
  "alertWhatsAppRecipients",
  "followUpReminderHours",
  "calendarReminderLeadMinutes",
  "morningGreetingEnabled",
  "morningGreetingTime",
  "morningGreetingRecipients",
  "morningGreetingMessage",
  "holidayAutoReplyEnabled",
  "holidayAutoReplyMessage",
  "assistantManagedSummary",
]);

type ComposerAttachment = {
  id: string;
  file: File;
  kind: "image" | "file";
  previewUrl?: string;
};

type SourceRefAttachment = {
  label: string;
  uploaded: boolean;
  kind: "image" | "file";
  previewUrl?: string;
  contentType?: string;
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
type DesktopVoiceOption = {
  id: string;
  name: string;
  lang?: string;
};

type ThreadDisplayMessage = Omit<AssistantThreadMessage, "id"> & {
  id: number | string;
};

type ThreadMenuPosition = {
  top: number;
  left: number;
};

type AssistantMessageFeedbackValue = "liked" | "disliked";
type AssistantSidebarSection = "threads" | "starred";

const SHARE_CHANNEL_OPTIONS: Array<{
  value: AssistantShareChannel;
  label: string;
  needsRecipient: boolean;
}> = [
  { value: "whatsapp", label: "WhatsApp", needsRecipient: true },
  { value: "email", label: "E-posta", needsRecipient: true },
  { value: "telegram", label: "Telegram", needsRecipient: true },
  { value: "x", label: "X", needsRecipient: false },
  { value: "linkedin", label: "LinkedIn", needsRecipient: false },
];

type AssistantShareTargetOption = {
  id: string;
  profileId: string;
  label: string;
  sublabel: string;
  value: string;
  kind: "person" | "group";
};

type DesktopGoogleState = {
  connected: boolean;
  enabled: boolean;
  accountLabel: string;
  scopes: string[];
};

type DesktopOutlookState = {
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

function _normalizeAssistantSearchText(value: string) {
  return String(value || "")
    .toLocaleLowerCase("tr-TR")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ı/g, "i")
    .trim();
}

function assistantShareNeedsRecipient(channel: AssistantShareChannel) {
  return SHARE_CHANNEL_OPTIONS.find((item) => item.value === channel)?.needsRecipient ?? false;
}

function assistantShareDefaultSubject(content: string) {
  const compact = String(content || "").split(/\s+/).join(" ").trim();
  if (!compact) {
    return "Asistan paylaşımı";
  }
  if (compact.length > 72) {
    return `${compact.slice(0, 69).trimEnd()}...`;
  }
  return compact;
}

function assistantContactPointsSummary(item: AssistantContactProfile | AssistantRelationshipProfile) {
  const parts = [
    ...(item.emails || []).slice(0, 2),
    ...(item.phone_numbers || []).slice(0, 2),
    ...(item.handles || []).slice(0, 2),
  ].filter(Boolean);
  return parts.join(" · ");
}

function normalizeAssistantShareSearchText(value: string) {
  return String(value || "")
    .toLocaleLowerCase("tr-TR")
    .replace(/ç/g, "c")
    .replace(/ğ/g, "g")
    .replace(/ı/g, "i")
    .replace(/ö/g, "o")
    .replace(/ş/g, "s")
    .replace(/ü/g, "u")
    .replace(/\s+/g, " ")
    .trim();
}

function assistantContactSupportsChannel(profile: AssistantContactProfile, channel: AssistantShareChannel) {
  if (profile.blocked) {
    return false;
  }
  if (channel === "email") {
    return profile.emails.length > 0;
  }
  if (channel === "whatsapp") {
    return profile.channels.includes("whatsapp");
  }
  if (channel === "telegram") {
    return profile.channels.includes("telegram");
  }
  return true;
}

function assistantShareTargetValue(profile: AssistantContactProfile, channel: AssistantShareChannel) {
  if (channel === "email") {
    return String(profile.emails[0] || profile.display_name || "").trim();
  }
  if (channel === "telegram") {
    return String(profile.handles[0] || profile.display_name || "").trim();
  }
  return String(profile.display_name || "").trim();
}

function assistantShareTargetOptions(
  profiles: AssistantContactProfile[],
  channel: AssistantShareChannel,
  query: string,
) {
  const needle = normalizeAssistantShareSearchText(query);
  return profiles
    .filter((profile) => assistantContactSupportsChannel(profile, channel))
    .map((profile): AssistantShareTargetOption => {
      const value = assistantShareTargetValue(profile, channel);
      const contactMeta =
        channel === "email"
          ? profile.emails[0] || ""
          : channel === "telegram"
            ? profile.handles[0] || profile.phone_numbers[0] || ""
            : profile.kind === "group"
              ? "Grup"
              : profile.phone_numbers[0] || profile.relationship_hint || "";
      const summary = [contactMeta, profile.persona_summary].filter(Boolean).join(" · ");
      return {
        id: `${profile.id}:${channel}`,
        profileId: profile.id,
        label: profile.display_name,
        sublabel: summary,
        value,
        kind: profile.kind,
      };
    })
    .filter((item) => {
      if (!needle) {
        return true;
      }
      return normalizeAssistantShareSearchText([item.label, item.sublabel, item.value].join(" ")).includes(needle);
    });
}

function AssistantHomeSummaryPanel({ summary }: { summary: string }) {
  const normalized = String(summary || "").trim();
  if (!normalized) {
    return null;
  }
  return (
    <div className="callout wa-welcome__card wa-welcome__card--narrow">
      <strong>Bugün özeti</strong>
      <p className="list-item__meta" style={{ marginBottom: 0, marginTop: "0.65rem" }}>{normalized}</p>
    </div>
  );
}

function AssistantHomeProactivePanel({
  items,
  onRun,
}: {
  items: NonNullable<AssistantHomeResponse["proactive_suggestions"]>;
  onRun: (item: NonNullable<AssistantHomeResponse["proactive_suggestions"]>[number]) => void;
}) {
  if (!items.length) {
    return null;
  }
  return (
    <div className="callout wa-welcome__card wa-welcome__card--narrow">
      <strong>Önerilen adımlar</strong>
      <div className="list" style={{ marginTop: "0.85rem" }}>
        {items.slice(0, 3).map((item) => (
          <article className="list-item" key={String(item.id || item.title)}>
            <div className="toolbar">
              <strong>{item.title}</strong>
              <StatusBadge tone={item.requires_confirmation ? "warning" : "accent"}>
                {item.priority || "öneri"}
              </StatusBadge>
            </div>
            <p className="list-item__meta">{item.details || item.why_now || "Ayrıntı yok"}</p>
            {item.action_label ? (
              <div style={{ marginTop: "0.65rem" }}>
                <button className="button button--ghost" type="button" onClick={() => onRun(item)}>
                  {item.action_label}
                </button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}

function AssistantHomeGoogleAccessPanel({
  accountLabel,
  summary,
  badges,
}: {
  accountLabel?: string | null;
  summary: string;
  badges: string[];
}) {
  if (!String(accountLabel || "").trim() && !summary && !badges.length) {
    return null;
  }
  return (
    <div className="callout wa-welcome__card wa-welcome__card--narrow">
      <strong>{accountLabel || "Google erişimi hazır"}</strong>
      {!accountLabel && summary ? (
        <p className="list-item__meta" style={{ marginTop: "0.65rem", marginBottom: badges.length ? "0.75rem" : 0 }}>
          {summary}
        </p>
      ) : null}
      {badges.length ? (
        <div className="wa-welcome__badges" style={{ justifyContent: "flex-start" }}>
          {badges.map((item) => (
            <span className="wa-badge" key={item}>{item}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AssistantHomeContactsPanel({
  importantProfiles,
  directory,
  summary,
  busyId,
  onToggleMute,
}: {
  importantProfiles: AssistantRelationshipProfile[];
  directory: AssistantContactProfile[];
  summary: AssistantHomeResponse["contact_directory_summary"] | null;
  busyId: string;
  onToggleMute: (item: AssistantContactProfile) => void | Promise<void>;
}) {
  if (!importantProfiles.length && !directory.length) {
    return null;
  }
  const [showAllDirectory, setShowAllDirectory] = useState(false);
  const directoryItems = showAllDirectory ? directory : directory.slice(0, 4);
  const channelCoverage = Object.entries(summary?.channels || {})
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 3)
    .map(([channel, count]) => `${kanalEtiketi(channel)} ${count}`);
  return (
    <div className="callout wa-welcome__card wa-welcome__card--narrow">
      <div className="toolbar" style={{ alignItems: "flex-start" }}>
        <div>
          <strong>Önemli kişiler</strong>
          <p className="list-item__meta" style={{ marginBottom: 0 }}>
            İlişki ve iletişim sinyallerine göre öne çıkan kişiler.
          </p>
        </div>
        {summary?.priority_profiles ? <StatusBadge tone="accent">{`${summary.priority_profiles} öncelikli kişi`}</StatusBadge> : null}
      </div>
      {importantProfiles.length ? (
        <div className="list" style={{ marginTop: "0.85rem" }}>
          {importantProfiles.slice(0, 3).map((item) => (
            <article className="list-item" key={item.id}>
              <div className="toolbar">
                <strong>{item.display_name}</strong>
                <StatusBadge tone={item.profile_strength === "yüksek" ? "accent" : "warning"}>{item.relationship_hint || "kişi"}</StatusBadge>
              </div>
              <p className="list-item__meta">{item.summary}</p>
              {item.inference_signals?.length ? (
                <p className="list-item__meta" style={{ marginTop: "0.45rem" }}>
                  {item.inference_signals.join(" · ")}
                </p>
              ) : null}
              {item.last_inbound_preview ? (
                <p className="list-item__meta" style={{ marginTop: "0.45rem" }}>
                  {`Son gelen${item.last_inbound_channel ? ` (${item.last_inbound_channel})` : ""}: ${item.last_inbound_preview}`}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
      {directory.length ? (
        <>
          <div className="toolbar" style={{ marginTop: "1rem", alignItems: "center" }}>
            <strong>Hesaplar ve adresler</strong>
            <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
              {summary?.total_accounts ? <StatusBadge>{`${summary.total_accounts} kayıt`}</StatusBadge> : null}
              {channelCoverage.length ? <StatusBadge tone="neutral">{channelCoverage.join(" · ")}</StatusBadge> : null}
            </div>
          </div>
          <div className="list" style={{ marginTop: "0.75rem" }}>
            {directoryItems.map((item) => (
              <article className="list-item" key={item.id}>
                <div className="toolbar">
                  <strong>{item.display_name}</strong>
                  <StatusBadge tone={item.blocked ? "warning" : (item.watch_enabled ? "accent" : "neutral")}>
                    {item.kind === "group" ? "grup" : "kişi"}
                  </StatusBadge>
                </div>
                <p className="list-item__meta">
                  {[item.relationship_hint, item.persona_summary || item.channel_summary].filter(Boolean).join(" · ")}
                </p>
                {item.channel_summary && item.persona_summary ? (
                  <p className="list-item__meta" style={{ marginTop: "0.45rem" }}>
                    {item.channel_summary}
                  </p>
                ) : null}
                {item.inference_signals?.length ? (
                  <p className="list-item__meta" style={{ marginTop: "0.45rem" }}>
                    {item.inference_signals.join(" · ")}
                  </p>
                ) : null}
                {item.last_inbound_preview ? (
                  <p className="list-item__meta" style={{ marginTop: "0.45rem" }}>
                    {`Son gelen${item.last_inbound_channel ? ` (${item.last_inbound_channel})` : ""}: ${item.last_inbound_preview}`}
                  </p>
                ) : null}
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.65rem" }}>
                  <button
                    className="button button--ghost"
                    type="button"
                    disabled={busyId === item.id}
                    onClick={() => void onToggleMute(item)}
                  >
                    {busyId === item.id ? "Kaydediliyor..." : item.blocked ? "Sessizi kaldır" : "Sessize al"}
                  </button>
                </div>
              </article>
            ))}
          </div>
          {directory.length > 4 ? (
            <div style={{ marginTop: "0.75rem" }}>
              <button
                className="button button--ghost"
                type="button"
                onClick={() => setShowAllDirectory((current) => !current)}
              >
                {showAllDirectory ? "Daha az göster" : `Tüm kayıtları göster (${directory.length})`}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function AssistantHomeKnowledgePanel({
  entries,
  health,
  connectorItems,
  onForget,
}: {
  entries: Array<{
    id: string;
    title: string;
    summary: string;
    pageKey: string;
  }>;
  health: Record<string, unknown> | null;
  connectorItems: Array<Record<string, unknown>>;
  onForget: (item: { id: string; pageKey: string }) => void | Promise<void>;
}) {
  if (!entries.length && !health && !connectorItems.length) {
    return null;
  }
  return (
    <div className="callout wa-welcome__card wa-welcome__card--narrow">
      <strong>Asistanın bildikleri</strong>
      {entries.length ? (
        <div className="list" style={{ marginTop: "0.85rem" }}>
          {entries.slice(0, 3).map((item) => (
            <article className="list-item" key={`${item.pageKey}:${item.id}`}>
              <strong>{item.title}</strong>
              <p className="list-item__meta">{item.summary}</p>
              <div style={{ marginTop: "0.65rem" }}>
                <button className="button button--ghost" type="button" onClick={() => void onForget(item)}>
                  Unut
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : null}
      {health ? (
        <>
          <div className="toolbar" style={{ marginTop: entries.length ? "1rem" : "0.85rem" }}>
            <strong>Bilgi sağlığı</strong>
          </div>
          <div className="wa-welcome__badges" style={{ marginTop: "0.65rem", justifyContent: "flex-start" }}>
            {Object.entries(health).slice(0, 4).map(([key, value]) => (
              <span className="wa-badge" key={key}>{`${key}: ${String(value)}`}</span>
            ))}
          </div>
        </>
      ) : null}
      {connectorItems.length ? (
        <>
          <div className="toolbar" style={{ marginTop: "1rem" }}>
            <strong>Bağlayıcı eşitleme</strong>
          </div>
          <div className="list" style={{ marginTop: "0.65rem" }}>
            {connectorItems.slice(0, 3).map((item, index) => (
              <article className="list-item" key={`${String(item.connector || index)}`}>
                <strong>{String(item.description || item.connector || "Bağlayıcı")}</strong>
                <p className="list-item__meta">
                  {[String(item.sync_mode || ""), String(item.record_count || ""), String(item.last_synced_at || "")].filter(Boolean).join(" · ")}
                </p>
              </article>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

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

type BubbleMapPreview = {
  title: string;
  subtitle: string;
  destinationLabel: string;
  destinationQuery: string;
  originLabel: string;
  routeMode: string;
  mapsUrl: string;
  directionsUrl: string;
  embedUrl: string;
  sourceKind: string;
  startsAt: string;
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

type AssistantAutomationUpdate = {
  mode?: string;
  summary?: string;
  warnings?: string[];
  needs_clarification?: boolean;
  operations?: Array<Record<string, unknown>>;
};

type AssistantMemoryUpdate = {
  kind?: string;
  summary?: string;
  value?: string;
  route?: string;
  action?: string;
  action_label?: string;
  warnings?: string[];
};

type AssistantAutomationRule = {
  id: string;
  summary: string;
  instruction: string;
  mode: string;
  channels: string[];
  targets: string[];
  match_terms: string[];
  reply_text: string;
  reminder_at?: string;
  thread_id?: number;
  active: boolean;
};

type RunInspectorSummary = {
  tools: string[];
  citations: Citation[];
  artifacts: AgentRunArtifact[];
  approvals: AgentRunApproval[];
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

function memoryScopeLabel(value?: string | null) {
  const scope = String(value || "").trim();
  if (!scope) return "genel";
  if (scope === "global") return "genel";
  if (scope === "personal") return "kişisel";
  if (scope === "professional" || scope === "workspace") return "çalışma alanı";
  if (scope.startsWith("project:")) return "proje";
  return scope;
}

function explainabilityConfidenceLabel(value: unknown) {
  const confidence = Number(value);
  if (!Number.isFinite(confidence) || confidence <= 0) return null;
  if (confidence >= 0.85) return "Dayanak güçlü";
  if (confidence >= 0.72) return "Dayanak iyi";
  if (confidence >= 0.6) return "Dayanak sınırlı";
  return "Dayanak zayıf";
}

function explainabilityReasonSummary(reasons: string[]) {
  const normalized = new Set(
    reasons
      .map((item) => String(item || "").trim().toLowerCase())
      .filter(Boolean),
  );
  if (!normalized.size) {
    return "";
  }

  const parts: string[] = [];
  if ([
    "token_overlap",
    "concept_token_overlap",
    "exact_phrase",
  ].some((item) => normalized.has(item))) {
    parts.push("mesajındaki ifadelerle doğrudan örtüşen kayıtlar");
  }
  if ([
    "scope_match",
    "metadata_match",
    "page_intent_match",
    "query_intent_match",
  ].some((item) => normalized.has(item))) {
    parts.push("konuya ve doğru bağlama uyan kayıtlar");
  }
  if ([
    "semantic_article_match",
    "semantic_expansion",
    "semantic_reranker",
    "semantic_vector_match",
    "relation_match",
    "concept_kind_match",
    "concept_title_match",
  ].some((item) => normalized.has(item))) {
    parts.push("anlam olarak yakın kayıtlar");
  }
  if ([
    "high_confidence",
    "freshness",
    "priority_weight",
    "recent_activity_match",
    "knowledge_density",
    "fts_primary_hit",
    "result_diversity",
  ].some((item) => normalized.has(item))) {
    parts.push("daha güvenilir ve güncel görünen kayıtlar");
  }
  if ([
    "correction_history_penalty",
    "decay_penalty",
    "low_confidence_penalty",
  ].some((item) => normalized.has(item))) {
    parts.push("zayıf veya eski kalan kayıtlar ise geri planda bırakıldı");
  }

  if (!parts.length) {
    return "Bu yanıt hazırlanırken konuya en uygun kayıtlar öne alındı.";
  }
  if (parts.length === 1) {
    return `Bu yanıt hazırlanırken ${parts[0]} öne alındı.`;
  }
  const lastPart = parts[parts.length - 1];
  return `Bu yanıt hazırlanırken ${parts.slice(0, -1).join(", ")} ve ${lastPart} öne alındı.`;
}

function memoryShareabilityLabel(value?: string | null) {
  const shareability = String(value || "").trim();
  if (!shareability) return "paylaşılabilir";
  if (shareability === "private") return "özel";
  if (shareability === "project_private") return "proje-özel";
  if (shareability === "workspace_shareable") return "çalışma ile paylaşılabilir";
  return shareability;
}

function coachingCadenceLabel(value?: string | null) {
  const cadence = String(value || "").trim();
  if (cadence === "daily") return "günlük";
  if (cadence === "weekly") return "haftalık";
  if (cadence === "one_time") return "tek seferlik";
  if (cadence === "flexible") return "esnek";
  return cadence || "aktif";
}

function coachingPriorityTone(value?: string | null): "accent" | "warning" | "neutral" {
  const normalized = String(value || "").trim();
  if (normalized === "high") return "warning";
  if (normalized === "medium") return "accent";
  return "neutral";
}

function timeLabel(value?: string | null) {
  if (!value) return "";
  return new Date(value).toLocaleString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

function statusTone(value?: string | null): "neutral" | "accent" | "warning" | "danger" {
  const normalized = String(value || "").trim().toLowerCase();
  if (["connected", "valid", "available", "completed", "approved", "active", "healthy"].includes(normalized)) return "accent";
  if (["pending", "configured", "dry_run", "requires_confirmation", "authorization_required", "authorization_pending", "queued", "review_pending", "desktop_handoff", "ready_for_desktop_action", "stale", "aging", "retry_scheduled", "permission_denied", "attention_required", "guarded"].includes(normalized)) return "warning";
  if (["invalid", "failed", "degraded", "revoked", "error", "blocked", "disconnected", "expired", "rejected", "cancelled", "capture_failed", "privacy_mode", "critical"].includes(normalized)) return "danger";
  return "neutral";
}

function statusLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "connected") return "Bağlı";
  if (normalized === "valid") return "Sağlıklı";
  if (normalized === "available") return "Hazır";
  if (normalized === "pending") return "Beklemede";
  if (normalized === "configured") return "Yapılandırıldı";
  if (normalized === "queued") return "Sırada";
  if (normalized === "dry_run") return "Deneme modu";
  if (normalized === "requires_confirmation") return "Onay gerekiyor";
  if (normalized === "authorization_required") return "Yetkilendirme gerekli";
  if (normalized === "authorization_pending") return "Yetkilendirme bekliyor";
  if (normalized === "review_pending") return "İnceleme onayı bekliyor";
  if (normalized === "collecting_input") return "Kurulum bilgileri bekleniyor";
  if (normalized === "awaiting_provider_choice") return "Servis seçimi bekleniyor";
  if (normalized === "desktop_handoff") return "Kurulum ekranda tamamlanacak";
  if (normalized === "ready_for_desktop_action") return "Son adım hazır";
  if (normalized === "completed") return "Tamamlandı";
  if (normalized === "failed") return "Başarısız";
  if (normalized === "retry_scheduled") return "Yeniden deneme planlandı";
  if (normalized === "busy") return "Çalışıyor";
  if (normalized === "fresh") return "Taze";
  if (normalized === "aging") return "Yakında eskir";
  if (normalized === "stale") return "Eskimeye başladı";
  if (normalized === "expired") return "Süresi doldu";
  if (normalized === "active") return "Aktif";
  if (normalized === "guarded") return "Temkinli";
  if (normalized === "healthy") return "Sağlıklı";
  if (normalized === "attention_required") return "Dikkat gerekiyor";
  if (normalized === "critical") return "Kritik";
  if (normalized === "invalid") return "Geçersiz";
  if (normalized === "degraded") return "Sorunlu";
  if (normalized === "revoked") return "Devre dışı";
  if (normalized === "error") return "Hata";
  if (normalized === "blocked") return "Engellendi";
  if (normalized === "disconnected") return "Bağlantı kesildi";
  if (normalized === "rejected") return "Reddedildi";
  if (normalized === "permission_denied") return "Konum izni yok";
  if (normalized === "capture_failed") return "Konum alınamadı";
  if (normalized === "privacy_mode") return "Gizlilik modu";
  if (normalized === "unsupported") return "Desteklenmiyor";
  if (normalized === "cancelled") return "İptal edildi";
  return normalized || "Bilinmiyor";
}

function whatsAppWebStatusTone(value?: string | null): "neutral" | "accent" | "warning" | "danger" {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "ready") return "accent";
  if (["initializing", "authenticated", "qr_required"].includes(normalized)) return "warning";
  if (["session_busy", "auth_failure", "disconnected"].includes(normalized)) return "danger";
  return "neutral";
}

function whatsAppWebStatusLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "initializing") return "WhatsApp hazırlanıyor";
  if (normalized === "qr_required") return "QR hazır";
  if (normalized === "authenticated") return "Telefon doğrulandı";
  if (normalized === "ready") return "WhatsApp bağlı";
  if (normalized === "session_busy") return "Başka WhatsApp oturumu açık";
  if (normalized === "auth_failure") return "Doğrulama başarısız";
  if (normalized === "disconnected") return "Bağlantı kesildi";
  return "";
}

function assistantContextFamilyLabel(value: unknown) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "personal_model") return "bana dair";
  if (normalized === "knowledge_base") return "bellek atlası";
  if (normalized === "operational") return "anlık operasyon";
  return normalized || "bağlam";
}

function assistantContextVisibilityLabel(value: unknown) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "blocked") return "şu an gizleniyor";
  return "asistana açık";
}

function assistantContextFreshnessLabel(value: unknown) {
  const normalized = String(value || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    hot: "çok güncel",
    warm: "yakın geçmiş",
    stable: "kalıcı bilgi",
    stale: "eskimeye yakın",
    unknown: "bilinmiyor",
  };
  return mapping[normalized] || normalized || "bilinmiyor";
}

function locationCaptureModeLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "device_capture") return "Cihaz konumu";
  if (normalized === "snapshot_fallback") return "Son kayıtlı konum";
  if (normalized === "inferred_memory") return "Bellekten çıkarım";
  if (normalized === "manual_memory") return "Elle girilen bağlam";
  return String(value || "").trim();
}

function locationProviderModeLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "desktop_renderer_geolocation") return "Masaüstü konum algılama";
  if (normalized === "desktop_file_snapshot") return "Kayıtlı konum özeti";
  return String(value || "").trim();
}

function locationPermissionLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "granted") return "İzin: verildi";
  if (normalized === "denied") return "İzin: reddedildi";
  if (normalized === "prompt") return "İzin: sorulacak";
  if (normalized === "blocked") return "İzin: engellendi";
  if (normalized === "restricted") return "İzin: kısıtlı";
  if (normalized === "unsupported") return "İzin: desteklenmiyor";
  return normalized ? `İzin: ${normalized}` : "";
}

function locationRouteModeLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "walking") return "Yürüyüş";
  if (normalized === "driving") return "Araç";
  if (normalized === "transit") return "Toplu taşıma";
  if (normalized === "bicycling") return "Bisiklet";
  return String(value || "").trim();
}

function connectorSyncModeLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "mirror") return "Ayna eşitleme";
  if (normalized === "mirror_pull") return "Ayna eşitleme";
  if (normalized === "local_scan") return "Yerel tarama";
  if (normalized === "adapter_stub") return "Hazır değil";
  return String(value || "").trim();
}

function sensitivityLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "high") return "Yüksek hassasiyet";
  if (normalized === "medium") return "Orta hassasiyet";
  if (normalized === "low") return "Düşük hassasiyet";
  return String(value || "").trim();
}

function integrationAccessLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "read_only") return "Salt okuma";
  if (normalized === "read_write") return "Okuma ve yazma";
  if (normalized === "admin_like") return "Geniş yetki";
  return String(value || "").trim() || "Standart erişim";
}

function integrationSkillSummary(setup: Record<string, unknown> | null) {
  const skill = setup?.skill;
  if (!skill || typeof skill !== "object") {
    return "";
  }
  return String((skill as Record<string, unknown>).summary || "").trim();
}

function integrationCapabilityPreview(setup: Record<string, unknown> | null) {
  if (!setup) {
    return [] as string[];
  }
  const direct = Array.isArray(setup.capabilities)
    ? (setup.capabilities as unknown[]).map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  if (direct.length > 0) {
    return direct.slice(0, 4);
  }
  const skill = setup.skill;
  if (!skill || typeof skill !== "object") {
    return [] as string[];
  }
  const preview = Array.isArray((skill as Record<string, unknown>).capability_preview)
    ? ((skill as Record<string, unknown>).capability_preview as unknown[]).map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  if (preview.length > 0) {
    return preview.slice(0, 4);
  }
  const groups = Array.isArray((skill as Record<string, unknown>).capability_groups)
    ? ((skill as Record<string, unknown>).capability_groups as Array<Record<string, unknown>>)
      .map((item) => String(item.label || "").trim())
      .filter(Boolean)
    : [];
  return groups.slice(0, 4);
}

function actionStageLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "suggest") return "Öneri";
  if (normalized === "draft") return "Taslak";
  if (normalized === "preview") return "Önizleme";
  if (normalized === "one_click_approve") return "Onay";
  if (normalized === "execute") return "İşlendi";
  return normalized || "Bilinmiyor";
}

function toolLabel(tool: ToolKey) {
  const text = tr.assistant;
  const labels: Record<ToolKey, string> = {
    today: text.toolToday,
    calendar: text.toolCalendar,
    matters: text.toolMatters,
    documents: text.toolDocuments,
    drafts: text.toolDrafts,
  };
  return labels[tool];
}

function setupLinkForItem(item: { id?: string | null; action?: string | null; route?: string | null }) {
  const action = String(item.action || "").trim();
  const id = String(item.id || "").trim();
  const explicitRoute = String(item.route || "").trim();
  if (explicitRoute) {
    return explicitRoute;
  }
  if (id === "setup-provider" || id === "setup-provider-model") {
    return "/settings?tab=kurulum&section=integration-provider&return_to=assistant";
  }
  if (id === "setup-google") {
    return "/settings?tab=kurulum&section=integration-google&return_to=assistant";
  }
  if (id === "setup-telegram") {
    return "/settings?tab=kurulum&section=integration-telegram&return_to=assistant";
  }
  if (id === "setup-whatsapp") {
    return "/settings?tab=kurulum&section=integration-whatsapp&return_to=assistant";
  }
  if (id === "setup-x") {
    return "/settings?tab=kurulum&section=integration-x&return_to=assistant";
  }
  if (action === "open_onboarding" || action === "open_settings") {
    return "/settings?tab=kurulum&section=integration-provider&return_to=assistant";
  }
  return "/settings?tab=kurulum&section=integration-provider&return_to=assistant";
}

function padCalendarNumber(value: number) {
  return String(value).padStart(2, "0");
}

function isAgentRunTerminal(status?: string | null) {
  return ["completed", "failed", "cancelled", "canceled", "rejected"].includes(String(status || "").trim().toLowerCase());
}

function agentRunStatusTone(status?: string | null): "neutral" | "accent" | "warning" | "danger" {
  const normalized = String(status || "").trim().toLowerCase();
  if (["completed", "succeeded", "done"].includes(normalized)) return "accent";
  if (["failed", "error", "cancelled", "canceled", "rejected"].includes(normalized)) return "danger";
  if (["requires_approval", "waiting_approval", "pending_review", "prepared"].includes(normalized)) return "warning";
  return "neutral";
}

function agentRunStatusLabel(status?: string | null) {
  const normalized = String(status || "").trim().toLowerCase();
  if (!normalized) return "Hazırlanıyor";
  if (["queued", "created"].includes(normalized)) return "Sıraya alındı";
  if (["planning", "researching", "running", "in_progress"].includes(normalized)) return "İşleniyor";
  if (normalized === "requires_approval") return "Onay bekliyor";
  if (normalized === "prepared") return "Hazır";
  if (normalized === "completed") return "Tamamlandı";
  if (["failed", "error"].includes(normalized)) return "Hata";
  if (["cancelled", "canceled"].includes(normalized)) return "İptal edildi";
  return normalized.replace(/_/g, " ");
}

function summarizeAgentRun(run: AgentRun | null, events: AgentRunEvent[] = []): RunInspectorSummary {
  const seenTools = new Set<string>();
  const tools: string[] = [];
  const toolCandidates = [
    ...(Array.isArray(run?.tool_invocations) ? run.tool_invocations : []),
    ...events.map((event) => event.invocation).filter(Boolean),
  ];
  for (const item of toolCandidates) {
    const name = String(item?.tool_name || item?.tool || "").trim();
    if (!name || seenTools.has(name)) {
      continue;
    }
    seenTools.add(name);
    tools.push(name);
  }

  const citations = Array.isArray(run?.citations) ? run.citations.filter(Boolean) : [];
  const artifactCandidates = [
    ...(Array.isArray(run?.artifacts) ? run.artifacts : []),
    ...events.map((event) => event.artifact).filter(Boolean),
  ];
  const artifacts: AgentRunArtifact[] = [];
  const seenArtifacts = new Set<string>();
  for (const artifact of artifactCandidates) {
    const key = [
      String(artifact?.id || "").trim(),
      String(artifact?.kind || "").trim(),
      String(artifact?.url || artifact?.path || artifact?.label || "").trim(),
    ].join(":");
    if (!key || seenArtifacts.has(key)) {
      continue;
    }
    seenArtifacts.add(key);
    artifacts.push(artifact as AgentRunArtifact);
  }

  const approvalCandidates = Array.isArray(run?.approval_requests) ? run.approval_requests : [];
  const approvals = approvalCandidates.filter(Boolean);

  return { tools, citations, artifacts, approvals };
}

function formatToolLabel(name: string, catalog: AgentToolCatalogItem[]) {
  const normalized = String(name || "").trim();
  if (!normalized) {
    return "Araç";
  }
  const fromCatalog = catalog.find((item) => String(item.name || "").trim() === normalized);
  return String(fromCatalog?.label || normalized).trim();
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

function resolveDesktopOutlookState(payload: Record<string, unknown> | null, fallbackConnected: boolean): DesktopOutlookState {
  const outlook = payload && typeof payload.outlook === "object" && payload.outlook ? (payload.outlook as Record<string, unknown>) : null;
  const scopes = Array.isArray(outlook?.scopes) ? outlook.scopes.map((scope) => String(scope || "").trim()).filter(Boolean) : [];
  return {
    connected: Boolean(outlook?.oauthConnected) || fallbackConnected,
    enabled: Boolean(outlook?.enabled) || fallbackConnected,
    accountLabel: String(outlook?.accountLabel || ""),
    scopes,
  };
}

type CalendarProviderKind = "google" | "outlook" | "profile" | "task" | "local";

function calendarProviderKey(item: AssistantCalendarItem): CalendarProviderKind {
  const provider = String(item.provider || "").toLowerCase();
  const sourceType = String(item.source_type || "").toLowerCase();
  const kind = String(item.kind || "").toLowerCase();
  if (provider.includes("google")) {
    return "google";
  }
  if (provider.includes("outlook")) {
    return "outlook";
  }
  if (provider === "user-profile" || sourceType === "user_profile" || kind === "personal_date") {
    return "profile";
  }
  if (sourceType === "task" || kind === "task_due") {
    return "task";
  }
  return "local";
}

function calendarProviderLabel(item: AssistantCalendarItem) {
  const text = tr.assistant;
  const provider = calendarProviderKey(item);
  if (provider === "google") {
    return text.calendarProviderGoogle;
  }
  if (provider === "outlook") {
    return text.calendarProviderOutlook;
  }
  if (provider === "profile") {
    return text.calendarProviderProfile;
  }
  if (provider === "task") {
    return text.calendarProviderTask;
  }
  return text.calendarProviderLocal;
}

function calendarProviderGlyph(item: AssistantCalendarItem) {
  const provider = calendarProviderKey(item);
  if (provider === "google") {
    return "G";
  }
  if (provider === "outlook") {
    return "O";
  }
  if (provider === "profile") {
    return "P";
  }
  if (provider === "task") {
    return "T";
  }
  return "L";
}

function attachmentKind(file: File, preferredKind?: "image" | "file") {
  if (preferredKind) {
    return preferredKind;
  }
  const normalizedType = String(file.type || "").trim().toLowerCase();
  const normalizedName = String(file.name || "").trim().toLowerCase();
  if (
    normalizedType.startsWith("image/")
    || [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"].some((ext) => normalizedName.endsWith(ext))
  ) {
    return "image";
  }
  return "file";
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

function todayItemBadgeLabel(item: AssistantAgendaItem) {
  const provider = String(item.provider || "").toLowerCase();
  const sourceType = String(item.source_type || "").toLowerCase();
  const kind = String(item.kind || "").toLowerCase();
  if (provider === "google") {
    return "Gmail";
  }
  if (provider === "outlook") {
    return "Outlook";
  }
  if (provider === "whatsapp" || sourceType === "whatsapp_message") {
    return "WhatsApp";
  }
  if (provider === "x" || sourceType === "x_post") {
    return "X";
  }
  if (kind === "draft_review" || sourceType === "outbound_draft") {
    return "Taslak";
  }
  if (kind === "calendar_prep" || sourceType === "calendar_event") {
    return "Takvim";
  }
  if (kind === "social_alert" || kind === "social_watch" || sourceType === "social_event") {
    return "Sosyal";
  }
  if (kind === "personal_date" || sourceType === "user_profile") {
    return "Hatırlatma";
  }
  if (kind === "due_today" || kind === "overdue_task" || sourceType === "task") {
    return "Görev";
  }
  if (sourceType === "email_thread") {
    return "E-posta";
  }
  return "Ajanda";
}

type TodayCategoryKey = "overview" | "messages" | "email" | "calendar" | "drafts" | "tasks" | "social" | "other";

function todayItemCategoryKey(item: AssistantAgendaItem): TodayCategoryKey {
  const sourceType = String(item.source_type || "").toLowerCase();
  const kind = String(item.kind || "").toLowerCase();
  if (kind === "social_alert" || kind === "social_watch" || sourceType === "social_event" || sourceType === "x_post") {
    return "social";
  }
  if (kind === "draft_review" || sourceType === "outbound_draft") {
    return "drafts";
  }
  if (kind === "calendar_prep" || sourceType === "calendar_event") {
    return "calendar";
  }
  if (sourceType === "email_thread") {
    return "email";
  }
  if (["whatsapp_message", "telegram_message", "x_message", "instagram_message"].includes(sourceType)) {
    return "messages";
  }
  if (kind === "due_today" || kind === "overdue_task" || kind === "personal_date" || sourceType === "task" || sourceType === "user_profile") {
    return "tasks";
  }
  return "other";
}

function todayCategoryLabel(category: TodayCategoryKey) {
  switch (category) {
    case "overview":
      return "Öne çıkanlar";
    case "messages":
      return "Mesajlar";
    case "email":
      return "E-posta";
    case "calendar":
      return "Takvim";
    case "drafts":
      return "Taslaklar";
    case "tasks":
      return "Görevler";
    case "social":
      return "Sosyal";
    default:
      return "Diğer";
  }
}

function todayCategoryDescription(category: TodayCategoryKey) {
  switch (category) {
    case "overview":
      return "Bugün için gerçekten öne çıkan başlıklar.";
    case "messages":
      return "Yanıt bekleyen mesajlaşma başlıkları.";
    case "email":
      return "Takip edilmesi gereken e-postalar.";
    case "calendar":
      return "Hazırlık gerektiren yakın takvim kayıtları.";
    case "drafts":
      return "Gönderim veya onay bekleyen taslaklar.";
    case "tasks":
      return "Bugünlük görevler ve kişisel hatırlatmalar.";
    case "social":
      return "Sosyal akıştan gelen risk veya izleme sinyalleri.";
    default:
      return "Diğer yardımcı kayıtlar.";
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

function loadSessionBriefDismissed() {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    return window.sessionStorage.getItem(SESSION_BRIEF_DISMISSED_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function persistSessionBriefDismissed(value: boolean) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    if (value) {
      window.sessionStorage.setItem(SESSION_BRIEF_DISMISSED_STORAGE_KEY, "1");
    } else {
      window.sessionStorage.removeItem(SESSION_BRIEF_DISMISSED_STORAGE_KEY);
    }
  } catch {
    // Session persistence is best-effort only.
  }
}

function loadSelectedAssistantThreadId() {
  if (typeof window === "undefined") {
    return 0;
  }
  try {
    return Number(window.localStorage.getItem(SELECTED_THREAD_STORAGE_KEY) || 0) || 0;
  } catch {
    return 0;
  }
}

function persistSelectedAssistantThreadId(threadId: number) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    if (threadId > 0) {
      window.localStorage.setItem(SELECTED_THREAD_STORAGE_KEY, String(threadId));
    } else {
      window.localStorage.removeItem(SELECTED_THREAD_STORAGE_KEY);
    }
  } catch {
    // Local persistence is best-effort only.
  }
}

function feedbackValueFromMessage(message: { feedback_value?: string | null } | null | undefined): AssistantMessageFeedbackValue | null {
  const value = String(message?.feedback_value || "").trim().toLowerCase();
  return value === "liked" || value === "disliked" ? value : null;
}

async function copyTextToClipboard(value: string) {
  const text = String(value || "");
  if (!text) {
    return false;
  }
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the execCommand fallback.
  }
  if (typeof document === "undefined") {
    return false;
  }
  const input = document.createElement("textarea");
  input.value = text;
  input.setAttribute("readonly", "true");
  input.style.position = "fixed";
  input.style.opacity = "0";
  input.style.pointerEvents = "none";
  document.body.appendChild(input);
  input.focus();
  input.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(input);
  }
}

function summarizeAssistantThread(response: AssistantThreadResponse): AssistantThreadSummary {
  const lastMessage = [...(response.messages || [])].reverse().find((item) => String(item.content || "").trim());
  return {
    ...response.thread,
    message_count: response.total_count ?? response.messages.length,
    last_message_preview: lastMessage?.content || null,
    last_message_at: lastMessage?.created_at || response.thread.updated_at,
  };
}

function mergeAssistantMessages(...sources: AssistantThreadMessage[][]): AssistantThreadMessage[] {
  const byId = new Map<number, AssistantThreadMessage>();
  for (const source of sources) {
    for (const item of source) {
      byId.set(item.id, item);
    }
  }
  return [...byId.values()].sort((left, right) => left.id - right.id);
}

function trimThreadPreview(value?: string | null) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "Henüz mesaj yok";
  }
  if (normalized.length <= 88) {
    return normalized;
  }
  return `${normalized.slice(0, 85).trimEnd()}...`;
}

function threadTimestampLabel(value?: string | null) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  const now = new Date();
  const sameDay = parsed.toDateString() === now.toDateString();
  return sameDay
    ? parsed.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })
    : parsed.toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
}

function starredMessagePreview(value?: string | null) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "İçerik görünmüyor";
  }
  if (normalized.length <= 140) {
    return normalized;
  }
  return `${normalized.slice(0, 137).trimEnd()}...`;
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
    previewUrl: isInlinePreviewableAttachment(kind, file.type, file.name) ? URL.createObjectURL(file) : undefined,
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

const AUDIO_RECORDING_MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/ogg",
] as const;

function canUseModelAudioCapture() {
  return typeof navigator !== "undefined"
    && Boolean(navigator.mediaDevices?.getUserMedia)
    && typeof MediaRecorder !== "undefined";
}

function preferredAudioRecordingMimeType() {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return "";
  }
  return AUDIO_RECORDING_MIME_CANDIDATES.find((item) => MediaRecorder.isTypeSupported(item)) || "";
}

function audioRecordingExtension(mimeType: string) {
  const normalized = String(mimeType || "").toLowerCase();
  if (normalized.includes("mp4") || normalized.includes("m4a")) {
    return "m4a";
  }
  if (normalized.includes("ogg")) {
    return "ogg";
  }
  if (normalized.includes("wav")) {
    return "wav";
  }
  if (normalized.includes("mpeg") || normalized.includes("mp3")) {
    return "mp3";
  }
  return "webm";
}

function normalizeVoiceTranscriptText(value: unknown) {
  return String(value || "")
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function speechTextFromMessage(value: string) {
  return String(value || "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .replace(/\[(.*?)\]\((.*?)\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function speechVoiceId(voice: SpeechSynthesisVoice) {
  return String(voice.voiceURI || voice.name || "").trim();
}

function resolveSpeechVoice(voices: SpeechSynthesisVoice[], preferredVoiceId = "") {
  if (preferredVoiceId) {
    const preferred = voices.find((voice) => speechVoiceId(voice) === preferredVoiceId);
    if (preferred) {
      return preferred;
    }
  }
  return (
    voices.find((voice) => String(voice.lang || "").toLowerCase().startsWith("tr")) ||
    voices.find((voice) => String(voice.lang || "").toLowerCase().startsWith("en")) ||
    voices[0] ||
    null
  );
}

function speechVoiceLabel(voice: SpeechSynthesisVoice) {
  const name = String(voice.name || "Sistem sesi").trim();
  const lang = String(voice.lang || "").trim();
  return lang ? `${name} (${lang})` : name;
}

function createTransientThreadMessage(role: "user" | "assistant", content: string, id: string): ThreadDisplayMessage {
  return {
    id,
    thread_id: 0,
    office_id: "",
    role,
    content,
    linked_entities: [],
    tool_suggestions: [],
    draft_preview: null,
    source_context: {},
    requires_approval: false,
    generated_from: "assistant_thread_transient",
    ai_provider: null,
    ai_model: null,
    starred: false,
    starred_at: null,
    feedback_value: null,
    feedback_note: null,
    feedback_at: null,
    created_at: new Date().toISOString(),
  };
}

function attachmentPreviewKey(label?: string | null, contentType?: string | null, sizeBytes?: number | string | null) {
  return [
    String(label || "").trim().toLocaleLowerCase("tr-TR"),
    String(contentType || "").trim().toLocaleLowerCase("tr-TR"),
    Number(sizeBytes || 0) || 0,
  ].join("::");
}

function attachmentPreviewCandidates(label?: string | null, contentType?: string | null, sizeBytes?: number | string | null) {
  const normalizedLabel = String(label || "").trim();
  const normalizedType = String(contentType || "").trim();
  const normalizedSize = Number(sizeBytes || 0) || 0;
  const candidates = [
    attachmentPreviewKey(normalizedLabel, normalizedType, normalizedSize),
    attachmentPreviewKey(normalizedLabel, "", normalizedSize),
    attachmentPreviewKey(normalizedLabel, normalizedType, 0),
    attachmentPreviewKey(normalizedLabel, "", 0),
  ];
  if (normalizedLabel.toLowerCase().endsWith(".pdf")) {
    candidates.push(attachmentPreviewKey(normalizedLabel, "application/pdf", normalizedSize));
    candidates.push(attachmentPreviewKey(normalizedLabel, "application/pdf", 0));
  }
  return Array.from(new Set(candidates.filter(Boolean)));
}

function attachmentPreviewKeyFromComposerAttachment(item: ComposerAttachment) {
  return attachmentPreviewKey(item.file.name, item.file.type, item.file.size);
}

function isInlinePreviewableAttachment(kind: "image" | "file", contentType?: string | null, label?: string | null) {
  const normalizedType = String(contentType || "").trim().toLowerCase();
  const normalizedLabel = String(label || "").trim().toLowerCase();
  return kind === "image"
    || normalizedType.startsWith("image/")
    || normalizedType.includes("pdf")
    || normalizedType.startsWith("audio/")
    || normalizedLabel.endsWith(".pdf")
    || [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".flac", ".webm"].some((ext) => normalizedLabel.endsWith(ext));
}

function enrichSourceContextAttachmentPreviews(
  sourceContext: Record<string, unknown> | null | undefined,
  previewIndex: Record<string, string>,
) {
  const refs = Array.isArray(sourceContext?.source_refs) ? sourceContext.source_refs : [];
  let changed = false;
  const nextRefs = refs.map((item) => {
    if (!item || typeof item !== "object") {
      return item;
    }
    const value = item as Record<string, unknown>;
    const type = String(value.type || "").trim().toLowerCase();
    const contentType = String(value.content_type || "").trim();
    const kind: "image" | "file" = type === "image_attachment" || contentType.startsWith("image/") ? "image" : "file";
    if (!isInlinePreviewableAttachment(kind, contentType, String(value.label || value.display_name || value.name || ""))) {
      return item;
    }
    if (String(value.preview_url || "").trim()) {
      return item;
    }
    const nextPreviewUrl = attachmentPreviewCandidates(
      String(value.label || value.display_name || value.name || ""),
      contentType,
      Number(value.size_bytes || 0),
    ).map((key) => previewIndex[key]).find(Boolean);
    if (!nextPreviewUrl) {
      return item;
    }
    changed = true;
    return {
      ...value,
      preview_url: nextPreviewUrl,
    };
  });
  if (!changed) {
    return sourceContext;
  }
  return {
    ...(sourceContext || {}),
    source_refs: nextRefs,
  };
}

function enrichThreadMessageAttachmentPreviews(message: ThreadDisplayMessage, previewIndex: Record<string, string>): ThreadDisplayMessage {
  const nextSourceContext = enrichSourceContextAttachmentPreviews(message.source_context, previewIndex);
  if (nextSourceContext === message.source_context) {
    return message;
  }
  return {
    ...message,
    source_context: nextSourceContext,
  };
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

function sourceRefAttachments(sourceContext?: Record<string, unknown> | null): SourceRefAttachment[] {
  const refs = Array.isArray(sourceContext?.source_refs) ? sourceContext.source_refs : [];
  const items = refs.map((item): SourceRefAttachment | null => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const value = item as Record<string, unknown>;
      const type = String(value.type || "").trim().toLowerCase();
      const contentType = String(value.content_type || "").trim();
      const kind: "image" | "file" = type === "image_attachment" || contentType.startsWith("image/") ? "image" : "file";
      return {
        label: String(value.label || value.display_name || value.name || value.relative_path || "Ek"),
        uploaded: Boolean(value.uploaded || value.document_id || value.id),
        kind,
        previewUrl: String(value.preview_url || "").trim() || undefined,
        contentType: contentType || undefined,
      };
  });
  return items.filter((item): item is SourceRefAttachment => item !== null);
}

function attachmentTypeLabel(label?: string | null, contentType?: string | null) {
  const normalizedType = String(contentType || "").trim().toLowerCase();
  const normalizedLabel = String(label || "").trim().toLowerCase();
  if (normalizedType.includes("pdf") || normalizedLabel.endsWith(".pdf")) {
    return "PDF";
  }
  if (normalizedType.startsWith("audio/")) {
    return "SES";
  }
  const extensionMatch = normalizedLabel.match(/\.([a-z0-9]{2,6})$/i);
  if (extensionMatch?.[1]) {
    return extensionMatch[1].toUpperCase();
  }
  if (normalizedType.includes("word")) {
    return "DOCX";
  }
  if (normalizedType.includes("spreadsheet") || normalizedType.includes("excel")) {
    return "XLSX";
  }
  if (normalizedType.includes("presentation") || normalizedType.includes("powerpoint")) {
    return "PPTX";
  }
  if (normalizedType.startsWith("image/")) {
    return "GÖRSEL";
  }
  return "BELGE";
}

function messageMetaItems(sourceContext: Record<string, unknown> | null | undefined, key: string) {
  return Array.isArray(sourceContext?.[key]) ? (sourceContext?.[key] as Array<Record<string, unknown>>) : [];
}

function normalizeMemoryUpdate(item: unknown, fallbackId: string): AssistantMemoryUpdate | null {
  if (!item || typeof item !== "object") {
    return null;
  }
  const record = item as Record<string, unknown>;
  const summary = normalizeAutomationText(record.summary || record.value || "", 240);
  const value = normalizeAutomationText(record.value || record.summary || "", 240);
  const route = normalizeAutomationText(record.route || "", 240);
  const action = normalizeAutomationText(record.action || "", 80);
  const actionLabel = normalizeAutomationText(record.action_label || "", 80);
  const warnings = normalizeAutomationList(record.warnings);
  if (!summary && !value && !warnings.length) {
    return null;
  }
  return {
    kind: normalizeAutomationText(record.kind || fallbackId, 80) || fallbackId,
    summary,
    value,
    route,
    action,
    action_label: actionLabel,
    warnings,
  };
}

function bubbleMemoryUpdates(sourceContext: Record<string, unknown> | null | undefined): AssistantMemoryUpdate[] {
  const items: AssistantMemoryUpdate[] = [];
  const seen = new Set<string>();

  const append = (item: AssistantMemoryUpdate | null) => {
    if (!item) {
      return;
    }
    const key = [
      item.summary || "",
      item.value || "",
      item.route || "",
      (item.warnings || []).join("|"),
    ].join("::");
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    items.push(item);
  };

  messageMetaItems(sourceContext, "memory_updates").forEach((item, index) => append(normalizeMemoryUpdate(item, `memory-${index + 1}`)));
  if (items.length === 0) {
    messageMetaItems(sourceContext, "automation_updates").forEach((item, index) => append(
      normalizeMemoryUpdate(
        {
          kind: "automation_signal",
          summary: (item as Record<string, unknown>).summary || "Otomasyon ayarı güncellendi.",
          route: "/settings?tab=automation&section=automation-panel",
          action: "open_settings",
          action_label: tr.assistant.openSettingsAction,
          warnings: (item as Record<string, unknown>).warnings,
        },
        `automation-${index + 1}`,
      ),
    ));
  }
  return items;
}

function normalizeAutomationList(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  const items: string[] = [];
  for (const raw of value) {
    const candidate = String(raw || "").trim();
    if (!candidate || items.includes(candidate)) {
      continue;
    }
    items.push(candidate);
  }
  return items;
}

function normalizeAutomationText(value: unknown, maxLength = 240) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

function normalizeAutomationRule(rule: unknown, fallbackId: string): AssistantAutomationRule | null {
  if (!rule || typeof rule !== "object") {
    return null;
  }
  const record = rule as Record<string, unknown>;
  const summary = normalizeAutomationText(record.summary || record.label || record.instruction || "");
  if (!summary) {
    return null;
  }
  return {
    id: normalizeAutomationText(record.id || fallbackId, 80) || fallbackId,
    summary,
    instruction: normalizeAutomationText(record.instruction || summary, 400),
    mode: normalizeAutomationText(record.mode || "custom", 32).toLowerCase() || "custom",
    channels: normalizeAutomationList(record.channels).map((item) => item.toLowerCase()).slice(0, 6),
    targets: normalizeAutomationList(record.targets).slice(0, 12),
    match_terms: normalizeAutomationList(record.match_terms ?? record.matchTerms).slice(0, 12),
    reply_text: normalizeAutomationText(record.reply_text ?? record.replyText, 280),
    reminder_at: normalizeAutomationText(record.reminder_at ?? record.reminderAt, 80),
    thread_id: Number.parseInt(String(record.thread_id ?? record.threadId ?? 0), 10) || undefined,
    active: record.active !== false,
  };
}

function normalizeAutomationRules(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as AssistantAutomationRule[];
  }
  const items: AssistantAutomationRule[] = [];
  const seen = new Set<string>();
  value.forEach((rule, index) => {
    const normalized = normalizeAutomationRule(rule, `rule-${index + 1}`);
    if (!normalized) {
      return;
    }
    const key = `${normalized.mode}:${normalized.summary.toLocaleLowerCase("tr-TR")}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    items.push(normalized);
  });
  return items.slice(0, 40);
}

function responseAutomationUpdates(response: AssistantThreadResponse): AssistantAutomationUpdate[] {
  if (Array.isArray(response.automation_updates)) {
    return response.automation_updates as AssistantAutomationUpdate[];
  }
  const lastAssistantMessage = [...response.messages].reverse().find((item) => item.role === "assistant");
  if (!lastAssistantMessage?.source_context) {
    return [];
  }
  return messageMetaItems(lastAssistantMessage.source_context, "automation_updates") as AssistantAutomationUpdate[];
}

function applyAutomationOperations(
  currentAutomation: Record<string, unknown> | null | undefined,
  updates: AssistantAutomationUpdate[],
  preferredThreadId?: number,
) {
  const canonicalReminderText = (rule: AssistantAutomationRule | null | undefined) => String(
    rule?.reply_text || rule?.instruction || rule?.summary || "",
  )
    .toLocaleLowerCase("tr-TR")
    .replace(/\b(?:kullanıcıya|kullaniciya|bana|beni|bizi|hatırlat|hatirlat|hatırlatma|hatirlatma|gerektiğini|gerektigini)\b/g, " ")
    .replace(/\b(?:\d{1,2}(?:[:.\s])\d{2}\s*(?:de|da|te|ta)?|\d{1,3}\s*(?:dk|dakika|saat|gun|gün|hafta)\s*sonra)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const nextAutomation: Record<string, unknown> = {
    ...((currentAutomation && typeof currentAutomation === "object") ? currentAutomation : {}),
  };
  for (const update of updates) {
    const operations = Array.isArray(update.operations) ? update.operations : [];
    for (const operation of operations) {
      const kind = String(operation.op || "").trim();
      const path = String(operation.path || "").trim();
      if (kind === "set") {
        if (!AUTOMATION_ALLOWED_FIELDS.has(path)) {
          continue;
        }
        nextAutomation[path] = operation.value;
        continue;
      }
      if (kind === "add_list") {
        if (!AUTOMATION_ALLOWED_FIELDS.has(path)) {
          continue;
        }
        const currentList = normalizeAutomationList(nextAutomation[path]);
        const incoming = normalizeAutomationList(operation.values);
        nextAutomation[path] = Array.from(new Set([...currentList, ...incoming]));
        continue;
      }
      if (kind === "add_rule") {
        const currentRules = normalizeAutomationRules(nextAutomation.automationRules);
        const nextRuleSource = operation.rule && typeof operation.rule === "object"
          ? {
              ...(operation.rule as Record<string, unknown>),
              thread_id: Number(
                (operation.rule as Record<string, unknown>).thread_id
                || (operation.rule as Record<string, unknown>).threadId
                || preferredThreadId
                || 0,
              ) || undefined,
            }
          : operation.rule;
        const nextRule = normalizeAutomationRule(
          nextRuleSource,
          `rule-${Date.now()}-${currentRules.length + 1}`,
        );
        if (!nextRule) {
          continue;
        }
        const dedupedRules = nextRule.mode === "reminder"
          ? currentRules.filter((rule) => !(rule.mode === "reminder" && canonicalReminderText(rule) && canonicalReminderText(rule) === canonicalReminderText(nextRule)))
          : currentRules;
        nextAutomation.automationRules = normalizeAutomationRules([...dedupedRules, nextRule]);
        continue;
      }
      if (kind === "remove_rule") {
        const matchTexts = normalizeAutomationList(operation.match_texts).map((item) => item.toLocaleLowerCase("tr-TR"));
        if (!matchTexts.length) {
          continue;
        }
        nextAutomation.automationRules = normalizeAutomationRules(nextAutomation.automationRules).filter((rule) => {
          const haystack = [
            rule.id,
            rule.summary,
            rule.instruction,
            ...rule.targets,
            ...rule.match_terms,
            ...rule.channels,
          ].join(" ").toLocaleLowerCase("tr-TR");
          return !matchTexts.some((item) => haystack.includes(item));
        });
      }
    }
  }
  return nextAutomation;
}

async function maybeApplyAssistantAutomationUpdates(response: AssistantThreadResponse) {
  const updates = responseAutomationUpdates(response).filter(
    (item) => Array.isArray(item.operations) && item.operations.length > 0,
  );
  if (!updates.length) {
    return "";
  }
  if (!window.lawcopilotDesktop?.getStoredConfig || !window.lawcopilotDesktop?.saveStoredConfig) {
    return "Bu otomasyon kuralı yalnız masaüstü uygulamasında arka plana yazılabilir.";
  }
  try {
    const currentConfig = await window.lawcopilotDesktop.getStoredConfig();
    const currentAutomation = currentConfig?.automation && typeof currentConfig.automation === "object"
      ? (currentConfig.automation as Record<string, unknown>)
      : {};
    const nextAutomation = applyAutomationOperations(
      currentAutomation,
      updates,
      Number(response.thread?.id || 0) || undefined,
    );
    await window.lawcopilotDesktop.saveStoredConfig({ automation: nextAutomation });
    return "";
  } catch {
    return "Asistan otomasyon kuralını masaüstü ayarlarına yazamadım.";
  }
}

function sameActionLabel(left: unknown, right: unknown) {
  return String(left || "")
    .trim()
    .toLocaleLowerCase("tr-TR") === String(right || "").trim().toLocaleLowerCase("tr-TR");
}

function renderBubbleInlineText(value: string, lineIndex: number): ReactNode {
  const nodes: ReactNode[] = [];
  const pattern = /\*\*(.+?)\*\*/g;
  let cursor = 0;
  let match = pattern.exec(value);

  while (match) {
    const start = match.index ?? 0;
    if (start > cursor) {
      nodes.push(value.slice(cursor, start));
    }
    nodes.push(
      <strong key={`line-${lineIndex}-strong-${start}`}>
        {match[1]}
      </strong>,
    );
    cursor = start + match[0].length;
    match = pattern.exec(value);
  }

  if (cursor < value.length) {
    nodes.push(value.slice(cursor));
  }

  return nodes;
}

function renderBubbleText(value: string): ReactNode {
  const lines = String(value || "").split("\n");
  const blocks: ReactNode[] = [];
  let lineIndex = 0;

  while (lineIndex < lines.length) {
    const line = lines[lineIndex];
    const bulletMatch = line.match(/^\s*[*-]\s+(.+)$/);
    if (bulletMatch) {
      const items: string[] = [];
      while (lineIndex < lines.length) {
        const currentMatch = lines[lineIndex].match(/^\s*[*-]\s+(.+)$/);
        if (!currentMatch) {
          break;
        }
        items.push(currentMatch[1]);
        lineIndex += 1;
      }
      blocks.push(
        <ul key={`list-${lineIndex}`} className="wa-bubble__list">
          {items.map((item, itemIndex) => (
            <li key={`list-${lineIndex}-${itemIndex}`} className="wa-bubble__list-item">
              {renderBubbleInlineText(item, lineIndex + itemIndex)}
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    blocks.push(
      <Fragment key={`line-${lineIndex}`}>
        {renderBubbleInlineText(line, lineIndex)}
        {lineIndex < lines.length - 1 ? <br /> : null}
      </Fragment>,
    );
    lineIndex += 1;
  }

  return blocks;
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

function bubbleMapPreview(sourceContext: Record<string, unknown> | null | undefined): BubbleMapPreview | null {
  const value = sourceContext?.map_preview;
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const destinationQuery = String(record.destination_query || "").trim();
  const embedUrl = String(record.embed_url || "").trim();
  const mapsUrl = String(record.maps_url || "").trim();
  const directionsUrl = String(record.directions_url || "").trim();
  if (!destinationQuery || (!embedUrl && !mapsUrl && !directionsUrl)) {
    return null;
  }
  return {
    title: String(record.title || record.destination_label || "Harita").trim(),
    subtitle: String(record.subtitle || "").trim(),
    destinationLabel: String(record.destination_label || destinationQuery).trim(),
    destinationQuery,
    originLabel: String(record.origin_label || "").trim(),
    routeMode: String(record.route_mode || "").trim(),
    mapsUrl,
    directionsUrl,
    embedUrl,
    sourceKind: String(record.source_kind || "").trim(),
    startsAt: String(record.starts_at || "").trim(),
  };
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

function buildActiveApprovalStatusMap(items: AssistantApproval[]) {
  return Object.fromEntries(
    (items || [])
      .filter((item) => String(item.id || "").trim())
      .map((item) => [String(item.id), String(item.status || "")]),
  );
}

function onboardingQuickReplies(sourceContext: Record<string, unknown> | null | undefined): string[] {
  if (!sourceContext || typeof sourceContext !== "object") {
    return [];
  }
  const onboarding = sourceContext.onboarding;
  if (!onboarding || typeof onboarding !== "object") {
    return [];
  }
  const onboardingRecord = onboarding as Record<string, unknown>;
  const currentQuestion = onboardingRecord.current_question && typeof onboardingRecord.current_question === "object"
    ? (onboardingRecord.current_question as Record<string, unknown>)
    : null;
  const nextQuestion = Array.isArray(onboardingRecord.next_questions) && onboardingRecord.next_questions[0] && typeof onboardingRecord.next_questions[0] === "object"
    ? (onboardingRecord.next_questions[0] as Record<string, unknown>)
    : null;
  const rawReplies = currentQuestion?.quick_replies || nextQuestion?.quick_replies;
  if (!Array.isArray(rawReplies)) {
    return [];
  }
  const seen = new Set<string>();
  const replies: string[] = [];
  for (const item of rawReplies) {
    const value = String(item || "").trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    replies.push(value);
  }
  return replies;
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

function TodayTool({
  agenda,
  actions,
  actionBusyId,
  actionBusyMode,
  onPauseAction,
  onResumeAction,
  onRetryAction,
  onCompensateAction,
}: {
  agenda: AssistantAgendaItem[];
  actions: SuggestedAction[];
  actionBusyId: string;
  actionBusyMode: "" | "pause" | "resume" | "retry" | "compensate";
  onPauseAction: (action: SuggestedAction) => void | Promise<void>;
  onResumeAction: (action: SuggestedAction) => void | Promise<void>;
  onRetryAction: (action: SuggestedAction) => void | Promise<void>;
  onCompensateAction: (action: SuggestedAction) => void | Promise<void>;
}) {
  const groupedItems = useMemo<Record<TodayCategoryKey, AssistantAgendaItem[]>>(
    () => ({
      overview: agenda.slice(0, 10),
      messages: agenda.filter((item) => todayItemCategoryKey(item) === "messages"),
      email: agenda.filter((item) => todayItemCategoryKey(item) === "email"),
      calendar: agenda.filter((item) => todayItemCategoryKey(item) === "calendar"),
      drafts: agenda.filter((item) => todayItemCategoryKey(item) === "drafts"),
      tasks: agenda.filter((item) => todayItemCategoryKey(item) === "tasks"),
      social: agenda.filter((item) => todayItemCategoryKey(item) === "social"),
      other: agenda.filter((item) => todayItemCategoryKey(item) === "other"),
    }),
    [agenda],
  );
  const visibleCategories = useMemo(
    () => ([
      "overview",
      "messages",
      "email",
      "calendar",
      "drafts",
      "tasks",
      "social",
      "other",
    ] as TodayCategoryKey[]).filter((category) => category === "overview" || groupedItems[category].length > 0),
    [groupedItems],
  );
  const [activeCategory, setActiveCategory] = useState<TodayCategoryKey>("overview");

  useEffect(() => {
    if (!visibleCategories.includes(activeCategory)) {
      setActiveCategory("overview");
    }
  }, [activeCategory, visibleCategories]);

  const items = groupedItems[activeCategory] || [];
  const categorySubtitle = activeCategory === "overview"
    ? tr.assistant.agendaSubtitle
    : todayCategoryDescription(activeCategory);
  return (
    <div className="tool-panel-grid">
      <SectionCard title={tr.assistant.agendaTitle} subtitle={categorySubtitle}>
        <div className="drafts-tool__filters" role="tablist" aria-label="Bugün bölümleri" style={{ marginBottom: "1rem" }}>
          {visibleCategories.map((category) => {
            const isActive = activeCategory === category;
            const count = category === "overview" ? agenda.length : groupedItems[category].length;
            return (
              <button
                key={category}
                className={`drafts-tool__filter-button${isActive ? " drafts-tool__filter-button--active" : ""}`}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveCategory(category)}
              >
                {`${todayCategoryLabel(category)} (${count})`}
              </button>
            );
          })}
        </div>
        {items.length ? (
          <div className="tool-card-grid">
            {items.map((item) => (
              <article className="list-item" key={item.id}>
                <div className="toolbar">
                  <strong>{item.title}</strong>
                  <StatusBadge tone="neutral">{todayItemBadgeLabel(item)}</StatusBadge>
                </div>
                <p className="list-item__meta">{item.details || "Ayrıntı belirtilmedi"}</p>
                <p className="list-item__meta">{dateLabel(item.due_at)}</p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title={activeCategory === "overview" ? tr.assistant.agendaEmptyTitle : `${todayCategoryLabel(activeCategory)} için kayıt yok`}
            description={activeCategory === "overview" ? tr.assistant.agendaEmptyDescription : todayCategoryDescription(activeCategory)}
          />
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
                <p className="list-item__meta">
                  {assistantActionControlSummary(action.action_case, action.dispatch_attempts) || "Aksiyon vakası henüz başlatılmadı."}
                </p>
                <ActionCaseStepRail steps={action.case_steps} />
                <ActionCaseCompensationNotice plan={action.compensation_plan} />
                <div className="toolbar" style={{ marginTop: "0.85rem" }}>
                  <div className="list-item__meta" style={{ marginTop: 0 }}>
                    {action.action_case?.current_step ? `Adım: ${assistantActionCaseStatusLabel(action.action_case.current_step)}` : "İzleme adımı yok"}
                  </div>
                  <ActionCaseControls
                    controls={action.available_controls}
                    busy={actionBusyId === String(action.id) ? actionBusyMode : ""}
                    onPause={() => onPauseAction(action)}
                    onResume={() => onResumeAction(action)}
                    onRetry={() => onRetryAction(action)}
                    onCompensate={() => onCompensateAction(action)}
                  />
                </div>
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
  outlookState,
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
  outlookState: DesktopOutlookState | null;
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
  const outlookConnected = Boolean(outlookState?.connected);
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
            <StatusBadge tone={outlookConnected ? "accent" : "warning"}>
              {outlookConnected ? text.calendarPlannerOutlookReady : text.calendarPlannerOutlookMissing}
            </StatusBadge>
            {googleState?.accountLabel ? <span className="pill">{googleState.accountLabel}</span> : null}
            {outlookState?.accountLabel ? <span className="pill">{outlookState.accountLabel}</span> : null}
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
                  {dayItems.slice(0, 2).map((item) => {
                    const providerKey = calendarProviderKey(item);
                    const entryLabel = item.all_day ? item.title : `${timeLabel(item.starts_at)} ${item.title}`;
                    return (
                      <span
                        key={`${cell.dayKey}-${item.id}`}
                        data-provider={providerKey}
                        title={`${calendarProviderLabel(item)} · ${entryLabel}`}
                        className={`calendar-tool__mini-item calendar-tool__mini-item--${providerKey}${item.needs_preparation ? " calendar-tool__mini-item--warning" : ""}`}
                      >
                        <span className="calendar-tool__mini-provider" aria-hidden="true">
                          {calendarProviderGlyph(item)}
                        </span>
                        <span className="calendar-tool__mini-item-text">{entryLabel}</span>
                      </span>
                    );
                  })}
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
              {selectedDayItems.map((item) => {
                const providerKey = calendarProviderKey(item);
                return (
                  <article className={`calendar-tool__event-card calendar-tool__event-card--${providerKey}`} key={item.id}>
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
                        <span className={`calendar-tool__source-badge calendar-tool__source-badge--${providerKey}`} data-provider={providerKey}>
                          <span className="calendar-tool__source-badge-mark" aria-hidden="true">
                            {calendarProviderGlyph(item)}
                          </span>
                          <span>{calendarProviderLabel(item)}</span>
                        </span>
                      </div>
                    </div>
                    <p className="list-item__meta">{item.details || text.noLocation}</p>
                    {item.location ? <p className="list-item__meta">{item.location}</p> : null}
                  </article>
                );
              })}
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
              Gmail, Takvim, Drive ve YouTube oynatma listeleri uygulama yüzeylerine aynalanır.
            </p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <StatusBadge tone={googleStatus.gmail_connected ? "accent" : "warning"}>{`${googleStatus.email_thread_count || 0} Gmail iş parçacığı`}</StatusBadge>
              <StatusBadge tone={googleStatus.calendar_connected ? "accent" : "warning"}>{`${googleStatus.calendar_event_count || 0} Takvim kaydı`}</StatusBadge>
              <StatusBadge tone={googleStatus.drive_connected ? "accent" : "warning"}>{`${googleStatus.drive_file_count || 0} Drive dosyası`}</StatusBadge>
              <StatusBadge tone={googleStatus.youtube_connected ? "accent" : "warning"}>{`${googleStatus.youtube_playlist_count || 0} YouTube oynatma listesi`}</StatusBadge>
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
              <div className="tool-card-grid documents-tool__card-grid">
                {documents.slice(0, 10).map((document) => (
                  <article className="list-item documents-tool__card" key={document.id}>
                    <div className="toolbar documents-tool__card-header">
                      <strong className="documents-tool__card-title">{document.display_name}</strong>
                      <StatusBadge>{document.extension}</StatusBadge>
                    </div>
                    <p className="list-item__meta documents-tool__card-meta">{document.relative_path}</p>
                    <div className="toolbar documents-tool__card-actions">
                      <StatusBadge tone={document.indexed_status === "indexed" ? "accent" : "warning"}>{belgeDurumuEtiketi(document.indexed_status)}</StatusBadge>
                      <button
                        className="button button--ghost documents-tool__card-button"
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
              <div className="tool-card-grid documents-tool__card-grid">
                {driveFiles.slice(0, 10).map((file) => (
                  <article className="list-item documents-tool__card" key={`${file.provider}-${file.external_id}`}>
                    <div className="toolbar documents-tool__card-header">
                      <strong className="documents-tool__card-title">{file.name}</strong>
                      <StatusBadge>{googleDriveTypeLabel(file.mime_type)}</StatusBadge>
                    </div>
                    <p className="list-item__meta documents-tool__card-meta">
                      {file.modified_at ? `Güncellendi: ${dateLabel(file.modified_at)}` : "Değişiklik tarihi yok"}
                    </p>
                    <div className="toolbar documents-tool__card-actions">
                      <StatusBadge tone="accent">Google Drive</StatusBadge>
                      {file.web_view_link ? (
                        <a className="button button--ghost documents-tool__card-button" href={file.web_view_link} target="_blank" rel="noreferrer">
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

function mergeActionIntoList(currentActions: SuggestedAction[], incomingAction: SuggestedAction) {
  const incomingId = Number(incomingAction.id || 0);
  const nextActions = incomingId > 0
    ? [incomingAction, ...currentActions.filter((item) => Number(item.id || 0) !== incomingId)]
    : [incomingAction, ...currentActions];

  return nextActions.sort((left, right) => {
    const leftUpdatedAt = Date.parse(String(left.updated_at || left.created_at || ""));
    const rightUpdatedAt = Date.parse(String(right.updated_at || right.created_at || ""));
    if (!Number.isNaN(leftUpdatedAt) || !Number.isNaN(rightUpdatedAt)) {
      return (Number.isNaN(rightUpdatedAt) ? 0 : rightUpdatedAt) - (Number.isNaN(leftUpdatedAt) ? 0 : leftUpdatedAt);
    }
    return Number(right.id || 0) - Number(left.id || 0);
  });
}

function assistantActionCaseStatusLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "awaiting_approval") return "Onay bekliyor";
  if (normalized === "approved") return "Hazır";
  if (normalized === "draft_ready") return "Taslak hazır";
  if (normalized === "paused") return "Duraklatıldı";
  if (normalized === "awaiting_external_confirmation") return "Dış onay bekliyor";
  if (normalized === "failed_terminal") return "Gönderim başarısız";
  if (normalized === "completed") return "Tamamlandı";
  if (normalized === "cancelled") return "Kapatıldı";
  return statusLabel(normalized);
}

function latestAssistantDispatchAttempt(attempts?: AssistantDispatchAttempt[] | null) {
  if (!attempts?.length) {
    return null;
  }
  return [...attempts].sort((left, right) => {
    const leftTime = Date.parse(String(left.updated_at || left.created_at || ""));
    const rightTime = Date.parse(String(right.updated_at || right.created_at || ""));
    return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
  })[0] || null;
}

function assistantActionControlSummary(actionCase?: AssistantActionCase | null, attempts?: AssistantDispatchAttempt[] | null) {
  const parts: string[] = [];
  const statusLabelText = assistantActionCaseStatusLabel(actionCase?.status);
  if (statusLabelText) {
    parts.push(statusLabelText);
  }
  const latestAttempt = latestAssistantDispatchAttempt(attempts);
  if (latestAttempt?.status) {
    parts.push(`Son deneme: ${statusLabel(latestAttempt.status)}`);
  }
  const retryReadyAt = latestAttempt?.metadata && typeof latestAttempt.metadata === "object"
    ? String((latestAttempt.metadata as Record<string, unknown>).retry_ready_at || "").trim()
    : "";
  if (String(latestAttempt?.status || "").trim().toLowerCase() === "retry_scheduled" && retryReadyAt) {
    parts.push(`Tekrar zamanı: ${dateLabel(retryReadyAt)}`);
  }
  if (latestAttempt?.error) {
    parts.push(String(latestAttempt.error));
  }
  return parts.filter(Boolean).join(" · ");
}

function assistantActionCaseStepStatusLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "done") return "Tamam";
  if (normalized === "active") return "Sırada";
  if (normalized === "pending") return "Bekliyor";
  if (normalized === "failed") return "Hata";
  if (normalized === "paused") return "Duraklatıldı";
  if (normalized === "retry") return "Yeniden denenecek";
  if (normalized === "skipped") return "Atlandı";
  if (normalized === "cancelled") return "Kapatıldı";
  return statusLabel(normalized);
}

function assistantActionCompensationStatusLabel(value?: string | null) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "recommended") return "Telafi öneriliyor";
  if (normalized === "scheduled") return "Telafi planlandı";
  if (normalized === "completed") return "Telafi işlendi";
  if (normalized === "failed") return "Telafi başarısız";
  if (normalized === "monitor") return "İzleniyor";
  if (normalized === "not_required") return "Telafi gerekmiyor";
  return statusLabel(normalized);
}

function assistantActionCaseStepTone(value?: string | null): "neutral" | "warning" | "accent" {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "done" || normalized === "skipped") return "accent";
  if (normalized === "active" || normalized === "retry") return "warning";
  if (normalized === "failed" || normalized === "paused" || normalized === "cancelled") return "warning";
  return "neutral";
}

function ActionCaseStepRail({ steps }: { steps?: AssistantActionCaseStep[] | null }) {
  if (!steps?.length) {
    return null;
  }
  return (
    <div style={{ display: "grid", gap: "0.55rem", marginTop: "0.75rem" }}>
      {steps.map((step) => (
        <div
          key={step.step_key}
          style={{
            border: "1px solid var(--border-subtle)",
            borderRadius: "0.85rem",
            padding: "0.7rem 0.8rem",
            background: "var(--surface-subtle)",
          }}
        >
          <div className="toolbar" style={{ alignItems: "center", gap: "0.75rem" }}>
            <strong style={{ fontSize: "0.96rem" }}>{step.title}</strong>
            <StatusBadge tone={assistantActionCaseStepTone(step.status)}>
              {assistantActionCaseStepStatusLabel(step.status)}
            </StatusBadge>
          </div>
          {step.detail ? <p className="list-item__meta" style={{ marginTop: "0.45rem" }}>{step.detail}</p> : null}
        </div>
      ))}
    </div>
  );
}

function ActionCaseCompensationNotice({ plan }: { plan?: AssistantActionCompensationPlan | null }) {
  if (!plan || !plan.reason) {
    return null;
  }
  return (
    <div
      style={{
        border: "1px dashed var(--border-subtle)",
        borderRadius: "0.85rem",
        padding: "0.7rem 0.8rem",
        marginTop: "0.75rem",
        background: "var(--surface-subtle)",
      }}
    >
      <div className="toolbar" style={{ alignItems: "center", gap: "0.75rem" }}>
        <strong style={{ fontSize: "0.96rem" }}>Telafi</strong>
        <StatusBadge tone={plan.status === "recommended" || plan.status === "failed" ? "warning" : (plan.status === "scheduled" || plan.status === "completed" ? "accent" : "neutral")}>
          {assistantActionCompensationStatusLabel(plan.status)}
        </StatusBadge>
      </div>
      <p className="list-item__meta" style={{ marginTop: "0.45rem", marginBottom: 0 }}>{plan.reason}</p>
    </div>
  );
}

function ActionCaseControls({
  controls,
  busy,
  onPause,
  onResume,
  onRetry,
  onCompensate,
}: {
  controls?: AssistantActionAvailableControls | null;
  busy: "" | "pause" | "resume" | "retry" | "compensate";
  onPause?: () => void | Promise<void>;
  onResume?: () => void | Promise<void>;
  onRetry?: () => void | Promise<void>;
  onCompensate?: () => void | Promise<void>;
}) {
  const canPause = Boolean(controls?.can_pause && onPause);
  const canResume = Boolean(controls?.can_resume && onResume);
  const canRetry = Boolean(controls?.can_retry_dispatch && onRetry);
  const canCompensate = Boolean(controls?.can_schedule_compensation && onCompensate);
  if (!canPause && !canResume && !canRetry && !canCompensate) {
    return null;
  }
  return (
    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
      {canPause ? (
        <button className="button button--ghost" type="button" disabled={Boolean(busy)} onClick={() => void onPause?.()}>
          {busy === "pause" ? "Duraklatılıyor..." : "Duraklat"}
        </button>
      ) : null}
      {canResume ? (
        <button className="button button--ghost" type="button" disabled={Boolean(busy)} onClick={() => void onResume?.()}>
          {busy === "resume" ? "Başlatılıyor..." : "Devam ettir"}
        </button>
      ) : null}
      {canRetry ? (
        <button className="button button--secondary" type="button" disabled={Boolean(busy)} onClick={() => void onRetry?.()}>
          {busy === "retry" ? "Planlanıyor..." : "Yeniden dene"}
        </button>
      ) : null}
      {canCompensate ? (
        <button className="button button--ghost" type="button" disabled={Boolean(busy)} onClick={() => void onCompensate?.()}>
          {busy === "compensate" ? "Hazırlanıyor..." : "Telafi hazırla"}
        </button>
      ) : null}
    </div>
  );
}

type DraftFilterKey = "all" | "whatsapp" | "email" | "gmail" | "outlook" | "telegram" | "x" | "travel";
type DraftSortKey = "newest" | "oldest";

function draftTimestampValue(draft: OutboundDraft) {
  const updatedAt = Date.parse(String(draft.updated_at || ""));
  if (!Number.isNaN(updatedAt)) {
    return updatedAt;
  }
  const createdAt = Date.parse(String(draft.created_at || ""));
  if (!Number.isNaN(createdAt)) {
    return createdAt;
  }
  return Number(draft.id || 0) || 0;
}

function draftProviderKey(draft: OutboundDraft): DraftFilterKey {
  const sourceContext = (draft.source_context || {}) as Record<string, unknown>;
  const provider = String(
    sourceContext.provider ||
      sourceContext.email_provider ||
      sourceContext.mail_provider ||
      "",
  )
    .trim()
    .toLowerCase();
  const channel = String(draft.channel || "").trim().toLowerCase();

  if (provider === "gmail" || channel === "gmail") {
    return "gmail";
  }
  if (provider === "outlook") {
    return "outlook";
  }
  if (channel === "whatsapp") {
    return "whatsapp";
  }
  if (channel === "telegram") {
    return "telegram";
  }
  if (channel === "x") {
    return "x";
  }
  if (channel === "travel") {
    return "travel";
  }
  return "email";
}

function DraftsTool({
  drafts,
  matterDrafts,
  onSendDraft,
  onRemoveDraft,
  draftBusyId,
  draftBusyMode,
  actionBusyId,
  actionBusyMode,
  onPauseAction,
  onResumeAction,
  onRetryAction,
  onCompensateAction,
}: {
  drafts: OutboundDraft[];
  matterDrafts: Draft[];
  onSendDraft: (draft: OutboundDraft) => void | Promise<void>;
  onRemoveDraft: (draft: OutboundDraft) => void | Promise<void>;
  draftBusyId: string;
  draftBusyMode: "" | "send" | "remove";
  actionBusyId: string;
  actionBusyMode: "" | "pause" | "resume" | "retry" | "compensate";
  onPauseAction: (action: SuggestedAction) => void | Promise<void>;
  onResumeAction: (action: SuggestedAction) => void | Promise<void>;
  onRetryAction: (action: SuggestedAction) => void | Promise<void>;
  onCompensateAction: (action: SuggestedAction) => void | Promise<void>;
}) {
  const [activeDraftFilter, setActiveDraftFilter] = useState<DraftFilterKey>("all");
  const [draftSortOrder, setDraftSortOrder] = useState<DraftSortKey>("newest");

  const sortedDrafts = useMemo(() => {
    return [...drafts].sort((left, right) => {
      const delta = draftTimestampValue(right) - draftTimestampValue(left);
      return draftSortOrder === "newest" ? delta : -delta;
    });
  }, [drafts, draftSortOrder]);

  const draftCounts = useMemo(() => {
    const counts: Record<DraftFilterKey, number> = {
      all: drafts.length,
      whatsapp: 0,
      email: 0,
      gmail: 0,
      outlook: 0,
      telegram: 0,
      x: 0,
      travel: 0,
    };
    drafts.forEach((draft) => {
      const key = draftProviderKey(draft);
      counts[key] += 1;
    });
    return counts;
  }, [drafts]);

  const availableDraftFilters = useMemo(() => {
    const base: Array<{ key: DraftFilterKey; label: string }> = [{ key: "all", label: "Tümü" }];
    const candidates: Array<{ key: DraftFilterKey; label: string }> = [
      { key: "whatsapp", label: "WhatsApp" },
      { key: "gmail", label: "Gmail" },
      { key: "outlook", label: "Outlook" },
      { key: "email", label: "E-posta" },
      { key: "telegram", label: "Telegram" },
      { key: "x", label: "X" },
      { key: "travel", label: "Seyahat" },
    ];
    return base.concat(candidates.filter((item) => draftCounts[item.key] > 0));
  }, [draftCounts]);

  const filteredDrafts = useMemo(() => {
    if (activeDraftFilter === "all") {
      return sortedDrafts;
    }
    return sortedDrafts.filter((draft) => draftProviderKey(draft) === activeDraftFilter);
  }, [activeDraftFilter, sortedDrafts]);

  return (
    <SectionCard title="Taslaklar" subtitle="Hukuki çalışma taslakları ile dış iletişim taslakları burada görünür.">
      {matterDrafts.length ? (
        <div className="stack" style={{ marginBottom: drafts.length ? "1rem" : 0 }}>
          <div className="toolbar">
            <strong>Hukuki taslaklar</strong>
            <StatusBadge tone="accent">{`${matterDrafts.length} kayıt`}</StatusBadge>
          </div>
          <div className="tool-card-grid">
            {matterDrafts.slice(0, 10).map((draft) => (
              <article className="list-item" key={`matter-draft-${draft.id}`}>
                <div className="toolbar">
                  <strong>{draft.title}</strong>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <StatusBadge tone="warning">{taslakTipiEtiketi(draft.draft_type)}</StatusBadge>
                    <StatusBadge>{kanalEtiketi(draft.target_channel)}</StatusBadge>
                  </div>
                </div>
                <p className="list-item__meta">
                  {draft.matter_title || "Dosya"} · {new Date(draft.updated_at || draft.created_at).toLocaleString("tr-TR")}
                </p>
                <p style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>{draft.body.slice(0, 220)}</p>
                <div className="toolbar" style={{ marginTop: "0.85rem" }}>
                  <div className="list-item__meta" style={{ marginTop: 0 }}>
                    {draft.manual_review_required ? "İnceleme bekliyor." : "Taslak hazır."}
                  </div>
                  {draft.generated_from ? <StatusBadge>{sistemKaynagiEtiketi(draft.generated_from)}</StatusBadge> : null}
                </div>
              </article>
            ))}
          </div>
        </div>
      ) : null}

      {drafts.length ? (
        <div className="stack">
          <div className="toolbar">
            <strong>Dış iletişim taslakları</strong>
            <StatusBadge tone="accent">{`${filteredDrafts.length} kayıt`}</StatusBadge>
          </div>
          <div className="drafts-tool__controls">
            <div className="drafts-tool__filters" role="tablist" aria-label="Taslak kanalları">
              {availableDraftFilters.map((filter) => {
                const isActive = activeDraftFilter === filter.key;
                return (
                  <button
                    key={filter.key}
                    className={`drafts-tool__filter-button${isActive ? " drafts-tool__filter-button--active" : ""}`}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    onClick={() => setActiveDraftFilter(filter.key)}
                  >
                    {`${filter.label} (${draftCounts[filter.key]})`}
                  </button>
                );
              })}
            </div>
            <div className="drafts-tool__sort" role="group" aria-label="Taslak sıralaması">
              <span>Sıralama</span>
              <div className="drafts-tool__sort-group">
                <button
                  className={`drafts-tool__sort-button${draftSortOrder === "newest" ? " drafts-tool__sort-button--active" : ""}`}
                  type="button"
                  aria-pressed={draftSortOrder === "newest"}
                  onClick={() => setDraftSortOrder("newest")}
                >
                  En yeni önce
                </button>
                <button
                  className={`drafts-tool__sort-button${draftSortOrder === "oldest" ? " drafts-tool__sort-button--active" : ""}`}
                  type="button"
                  aria-pressed={draftSortOrder === "oldest"}
                  onClick={() => setDraftSortOrder("oldest")}
                >
                  En eski önce
                </button>
              </div>
            </div>
          </div>
          {filteredDrafts.length ? (
            <div className="tool-card-grid">
              {filteredDrafts.slice(0, 10).map((draft) => {
              const draftId = String(draft.id);
              const isBusy = draftBusyId === draftId;
              const isSendBusy = isBusy && draftBusyMode === "send";
              const isRemoveBusy = isBusy && draftBusyMode === "remove";
              const linkedAction = draft.linked_action || null;
              const actionControls = linkedAction?.available_controls || draft.available_controls || null;
              const actionCase = linkedAction?.action_case || draft.action_case || null;
              const dispatchAttempts = linkedAction?.dispatch_attempts || draft.dispatch_attempts || [];
              const isActionBusy = actionBusyId === String(linkedAction?.id || draft.action_id || "");
              const isSent = String(draft.delivery_status || "").trim() === "sent" || String(draft.dispatch_state || "").trim() === "completed";
              const isPaymentPending = String(draft.delivery_status || "").trim() === "payment_pending" || String(draft.dispatch_state || "").trim() === "awaiting_external_confirmation";
              const isReady = String(draft.dispatch_state || "").trim() === "ready" || String(draft.delivery_status || "").trim() === "ready_to_send";
              const canSend = isDispatchableDraftChannel(draft.channel) && !isSent && !isReady && !isPaymentPending;
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
                  {linkedAction ? (
                    <p className="list-item__meta">
                      {assistantActionControlSummary(actionCase, dispatchAttempts) || "Aksiyon takibi hazır."}
                    </p>
                  ) : null}
                  <ActionCaseStepRail steps={linkedAction?.case_steps || draft.case_steps} />
                  <ActionCaseCompensationNotice plan={linkedAction?.compensation_plan || draft.compensation_plan} />
                  <div className="toolbar" style={{ marginTop: "0.85rem" }}>
                    <div className="list-item__meta" style={{ marginTop: 0 }}>
                      {isSent
                        ? "Bu taslak gönderildi."
                        : isPaymentPending
                          ? "Ödeme penceresi açıldı. Satın alma sağlayıcı tarafında tamamlanacak."
                        : isReady
                          ? "Gönderim hazırlanıyor."
                          : String(draft.approval_status || "").trim() === "approved"
                            ? "Onay verildi. Gönderime hazırsın."
                            : "Önce onaylanır, sonra otomatik gönderilir."}
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
                      {linkedAction ? (
                        <ActionCaseControls
                          controls={actionControls}
                          busy={isActionBusy ? actionBusyMode : ""}
                          onPause={() => onPauseAction(linkedAction)}
                          onResume={() => onResumeAction(linkedAction)}
                          onRetry={() => onRetryAction(linkedAction)}
                          onCompensate={() => onCompensateAction(linkedAction)}
                        />
                      ) : null}
                      {canSend ? (
                        <button className="button button--secondary" type="button" disabled={isBusy} onClick={() => void onSendDraft(draft)}>
                          {isSendBusy ? "Gönderiliyor..." : actionLabel}
                        </button>
                      ) : null}
                      <button className="button button--ghost" type="button" disabled={isBusy} onClick={() => void onRemoveDraft(draft)}>
                        {isRemoveBusy ? "Kaldırılıyor..." : "Kaldır"}
                      </button>
                    </div>
                  </div>
                </article>
                );
              })}
            </div>
          ) : (
            <EmptyState title="Bu kanalda taslak yok" description="Farklı bir kanal seçebilir veya yeni bir taslak oluşturabilirsiniz." />
          )}
        </div>
      ) : null}

      {!drafts.length && !matterDrafts.length ? (
        <EmptyState title="Taslak yok" description="Asistan bir hukuki taslak veya dış aksiyon hazırladığında burada görünür." />
      ) : null}
    </SectionCard>
  );
}

/* ── WhatsApp-style Message Bubble ───────────────────────── */

type ChatBubbleProps = {
  message: ThreadDisplayMessage;
  onToggleStar: (message: ThreadDisplayMessage) => void;
  onCopyMessage: (message: ThreadDisplayMessage) => void;
  onShareMessage: (message: ThreadDisplayMessage) => void;
  onEditMessage: (message: ThreadDisplayMessage) => void;
  isEditing: boolean;
  editValue: string;
  editBusy: boolean;
  onEditValueChange: (value: string) => void;
  onCancelEdit: () => void;
  onSubmitEdit: (message: ThreadDisplayMessage) => void;
  onSetFeedback: (message: ThreadDisplayMessage, value: AssistantMessageFeedbackValue) => void;
  onSubmitFeedbackNote: (message: ThreadDisplayMessage, value: AssistantMessageFeedbackValue, note: string) => Promise<void> | void;
  onOpenTool: (tool: ToolKey) => void;
  onPreviewClick?: (url: string, name: string, type: string) => void;
  onQuickReply: (text: string) => void;
  onRunIntegrationSetup: (setup: Record<string, unknown>) => Promise<void> | void;
  integrationSetupDesktopState?: Record<string, unknown> | null;
  onApproveApproval: (approval: BubbleApprovalItem, message: ThreadDisplayMessage) => void;
  onRejectApproval: (approval: BubbleApprovalItem) => void;
  feedbackValue: AssistantMessageFeedbackValue | null;
  starBusyMessageId: number | null;
  approvalBusyId: string;
  handledApprovalIds: Record<string, string>;
  activeApprovalStatuses: Record<string, string>;
  onMessageMemoryAction: (payload: {
    action: "correct" | "forget" | "change_scope" | "reduce_confidence" | "suppress_recommendation" | "boost_proactivity";
    page_key?: string;
    target_record_id?: string;
    corrected_summary?: string;
    scope?: string;
    note?: string;
    recommendation_kind?: string;
    topic?: string;
    source_refs?: Array<Record<string, unknown> | string>;
  }) => void | Promise<void>;
};

function isPendingApprovalStatus(status: unknown) {
  return ["pending", "pending_review", "requires_approval", "waiting_approval", "prepared"].includes(
    String(status || "").trim().toLowerCase(),
  );
}

function shouldRenderBubbleApproval(
  item: BubbleApprovalItem,
  handledApprovalIds: Record<string, string>,
  activeApprovalStatuses: Record<string, string>,
) {
  if (!item.id || handledApprovalIds[item.id]) {
    return false;
  }
  if (item.status && !isPendingApprovalStatus(item.status)) {
    return false;
  }
  const activeStatus = activeApprovalStatuses[item.id];
  if (!activeStatus) {
    return false;
  }
  return isPendingApprovalStatus(activeStatus);
}

function chatBubbleApprovalSignature(message: ThreadDisplayMessage, approvalBusyId: string, handledApprovalIds: Record<string, string>) {
  const approvals = bubbleApprovalItems(message.source_context);
  if (!approvals.length) {
    return "";
  }
  return approvals
    .map((item) => `${item.id}:${handledApprovalIds[item.id] || ""}:${approvalBusyId === item.id ? "busy" : ""}`)
    .join("|");
}

function bubbleExplainability(sourceContext: Record<string, unknown> | null | undefined) {
  if (!sourceContext || typeof sourceContext !== "object") {
    return null;
  }
  const drawer = sourceContext.explainability_drawer;
  if (drawer && typeof drawer === "object") {
    return drawer as Record<string, unknown>;
  }
  const explainability = sourceContext.explainability;
  if (explainability && typeof explainability === "object") {
    return explainability as Record<string, unknown>;
  }
  return null;
}

const ChatBubble = memo(function ChatBubble({
  message,
  onToggleStar,
  onCopyMessage,
  onShareMessage,
  onEditMessage,
  isEditing,
  editValue,
  editBusy,
  onEditValueChange,
  onCancelEdit,
  onSubmitEdit,
  onSetFeedback,
  onSubmitFeedbackNote,
  onOpenTool,
  onQuickReply,
  onRunIntegrationSetup,
  integrationSetupDesktopState,
  onApproveApproval,
  onRejectApproval,
  feedbackValue,
  starBusyMessageId,
  approvalBusyId,
  handledApprovalIds,
  activeApprovalStatuses,
  onMessageMemoryAction,
  onPreviewClick,
}: ChatBubbleProps) {
  const [isCopied, setIsCopied] = useState(false);
  const handleCopy = useCallback(() => {
    onCopyMessage(message);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  }, [message, onCopyMessage]);
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const shouldRenderAttachments = isUser;
  const canStar = typeof message.id === "number" && Number(message.thread_id || 0) > 0;
  const isStarBusy = canStar && starBusyMessageId === message.id;
  const isOnboardingBubble = String(message.generated_from || "").trim() === "assistant_onboarding_guide";
  const bubbleText = useMemo(() => renderBubbleText(message.content), [message.content]);
  const attachmentItems = useMemo(() => sourceRefAttachments(message.source_context), [message.source_context]);
  const visualAttachments = useMemo(
    () => attachmentItems.filter((item) => item.kind === "image" && item.previewUrl),
    [attachmentItems],
  );
  const attachmentBadges = useMemo(
    () => sourceRefBadges({
      ...(message.source_context || {}),
      source_refs: attachmentItems.filter((item) => item.kind !== "image" || !item.previewUrl).map((item) => ({
        label: item.label,
        uploaded: item.uploaded,
      })),
    }),
    [attachmentItems, message.source_context],
  );
  const proposedActions = useMemo(() => messageMetaItems(message.source_context, "proposed_actions"), [message.source_context]);
  const approvalRequests = useMemo(() => bubbleApprovalItems(message.source_context), [message.source_context]);
  const memoryUpdates = useMemo(() => bubbleMemoryUpdates(message.source_context), [message.source_context]);
  const mapPreview = useMemo(() => bubbleMapPreview(message.source_context), [message.source_context]);
  const webSearchResults = useMemo(() => bubbleResultItems(message.source_context, "web_search_results"), [message.source_context]);
  const travelOptions = useMemo(() => bubbleResultItems(message.source_context, "travel_options"), [message.source_context]);
  const integrationSetup = useMemo(
    () => (message.source_context?.integration_setup && typeof message.source_context.integration_setup === "object"
      ? message.source_context.integration_setup as Record<string, unknown>
      : null),
    [message.source_context],
  );
  const integrationSetupDesktopStatus = useMemo(
    () => (integrationSetupDesktopState && typeof integrationSetupDesktopState === "object"
      ? integrationSetupDesktopState
      : null),
    [integrationSetupDesktopState],
  );
  const integrationSetupSummary = useMemo(() => integrationSkillSummary(integrationSetup), [integrationSetup]);
  const integrationSetupCapabilities = useMemo(() => integrationCapabilityPreview(integrationSetup), [integrationSetup]);
  const integrationSetupIsWhatsApp = useMemo(() => {
    if (!integrationSetup) {
      return false;
    }
    const connectorId = String(integrationSetup.connector_id || "").trim().toLowerCase();
    const serviceName = String(integrationSetup.service_name || "").trim().toLowerCase();
    return connectorId === "whatsapp" || serviceName.includes("whatsapp");
  }, [integrationSetup]);
  const integrationSetupDesktopMessage = useMemo(
    () => String(
      integrationSetupDesktopStatus?.message
      || integrationSetup?.desktop_status_message
      || integrationSetup?.live_status_message
      || "",
    ).trim(),
    [integrationSetup, integrationSetupDesktopStatus],
  );
  const integrationSetupDesktopError = useMemo(
    () => String(integrationSetupDesktopStatus?.error || integrationSetup?.desktop_status_error || "").trim(),
    [integrationSetup, integrationSetupDesktopStatus],
  );
  const integrationSetupDesktopWebStatus = useMemo(
    () => String(integrationSetupDesktopStatus?.webStatus || integrationSetup?.web_status || "").trim(),
    [integrationSetup, integrationSetupDesktopStatus],
  );
  const integrationSetupDesktopQrDataUrl = useMemo(
    () => String(integrationSetupDesktopStatus?.webQrDataUrl || integrationSetup?.web_qr_data_url || "").trim(),
    [integrationSetup, integrationSetupDesktopStatus],
  );
  const integrationSetupDesktopAccountLabel = useMemo(
    () => String(
      integrationSetupDesktopStatus?.webAccountLabel
      || integrationSetupDesktopStatus?.accountLabel
      || integrationSetup?.web_account_label
      || "",
    ).trim(),
    [integrationSetup, integrationSetupDesktopStatus],
  );
  const integrationSetupDesktopCurrentUser = useMemo(
    () => String(integrationSetupDesktopStatus?.webCurrentUser || integrationSetup?.web_current_user || "").trim(),
    [integrationSetup, integrationSetupDesktopStatus],
  );
  const explainability = useMemo(() => bubbleExplainability(message.source_context), [message.source_context]);
  const assistantContextPack = useMemo(
    () => Array.isArray(message.source_context?.assistant_context_pack) ? message.source_context.assistant_context_pack as Array<Record<string, unknown>> : [],
    [message.source_context],
  );
  const supportingRecords = useMemo(
    () => Array.isArray(explainability?.supporting_pages_or_records) ? explainability.supporting_pages_or_records as Array<Record<string, unknown>> : [],
    [explainability],
  );
  const contextSelectionReasons = useMemo(
    () => Array.isArray(explainability?.context_selection_reasons) ? explainability.context_selection_reasons as string[] : [],
    [explainability],
  );
  const recentRelatedFeedback = useMemo(
    () => Array.isArray(explainability?.recent_related_feedback) ? explainability.recent_related_feedback as Array<Record<string, unknown>> : [],
    [explainability],
  );
  const supportingRelations = useMemo(
    () => Array.isArray(explainability?.supporting_relations) ? explainability.supporting_relations as Array<Record<string, unknown>> : [],
    [explainability],
  );
  const claimSummaryLines = useMemo(
    () => Array.isArray(explainability?.claim_summary_lines) ? explainability.claim_summary_lines as string[] : [],
    [explainability],
  );
  const resolvedClaims = useMemo(
    () => Array.isArray(explainability?.resolved_claims) ? explainability.resolved_claims as Array<Record<string, unknown>> : [],
    [explainability],
  );
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);
  const memoryScopes = useMemo(
    () => Array.isArray(explainability?.memory_scope) ? explainability.memory_scope as string[] : [],
    [explainability],
  );
  const explainabilityConfidenceLabelText = useMemo(() => {
    const hasGrounding = supportingRecords.length > 0
      || supportingRelations.length > 0
      || contextSelectionReasons.length > 0
      || recentRelatedFeedback.length > 0
      || claimSummaryLines.length > 0
      || resolvedClaims.length > 0;
    if (!hasGrounding) {
      return null;
    }
    return explainabilityConfidenceLabel(explainability?.confidence);
  }, [claimSummaryLines.length, contextSelectionReasons.length, explainability?.confidence, recentRelatedFeedback.length, resolvedClaims.length, supportingRecords.length, supportingRelations.length]);
  const explainabilityReasonSummaryText = useMemo(
    () => explainabilityReasonSummary(contextSelectionReasons),
    [contextSelectionReasons],
  );
  const primarySupportingRecord = supportingRecords[0] || null;
  const [isExplainabilityOpen, setIsExplainabilityOpen] = useState(false);
  const [isMapExpanded, setIsMapExpanded] = useState(false);
  const [isFeedbackReasonOpen, setIsFeedbackReasonOpen] = useState(false);
  const [isDesktopSetupBusy, setIsDesktopSetupBusy] = useState(false);
  const [feedbackReasonDraft, setFeedbackReasonDraft] = useState(String(message.feedback_note || ""));
  const [isFeedbackReasonSaving, setIsFeedbackReasonSaving] = useState(false);
  const integrationSetupAutoRunRef = useRef(false);
  useEffect(() => {
    if (!isEditing) {
      return;
    }
    window.requestAnimationFrame(() => {
      const node = editTextareaRef.current;
      if (!node) {
        return;
      }
      node.focus();
      const cursor = node.value.length;
      node.setSelectionRange(cursor, cursor);
    });
  }, [isEditing]);

  const canRunLegacySetup = Boolean(
    integrationSetup
    && String(integrationSetup.setup_mode || "").trim() === "legacy_desktop"
    && String(integrationSetup.desktop_action || "").trim()
    && integrationSetup.id
    && window.lawcopilotDesktop?.runAssistantLegacySetup,
  );

  async function handleRunLegacySetup() {
    if (!integrationSetup || !canRunLegacySetup || isDesktopSetupBusy) {
      return;
    }
    try {
      setIsDesktopSetupBusy(true);
      await onRunIntegrationSetup(integrationSetup);
    } finally {
      setIsDesktopSetupBusy(false);
    }
  }
  useEffect(() => {
    if (!canRunLegacySetup || !integrationSetup || integrationSetupAutoRunRef.current) {
      return;
    }
    if (!Boolean(integrationSetup.auto_run_desktop_action)) {
      return;
    }
    const createdAt = Date.parse(String(message.created_at || ""));
    if (Number.isFinite(createdAt) && Date.now() - createdAt > 15_000) {
      return;
    }
    integrationSetupAutoRunRef.current = true;
    void handleRunLegacySetup().catch(() => undefined);
  }, [canRunLegacySetup, handleRunLegacySetup, integrationSetup, message.created_at]);
  useEffect(() => {
    if (!isMapExpanded) {
      return;
    }
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsMapExpanded(false);
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isMapExpanded]);
  useEffect(() => {
    if (!mapPreview) {
      setIsMapExpanded(false);
    }
  }, [mapPreview]);
  useEffect(() => {
    setFeedbackReasonDraft(String(message.feedback_note || ""));
  }, [message.feedback_note, message.id]);
  useEffect(() => {
    if (!feedbackValue) {
      setIsFeedbackReasonOpen(false);
      return;
    }
    if (!String(message.feedback_note || "").trim()) {
      setIsFeedbackReasonOpen(true);
    }
  }, [feedbackValue, message.feedback_note]);
  const visibleApprovalRequests = useMemo(
    () => approvalRequests.filter((item) => shouldRenderBubbleApproval(item, handledApprovalIds, activeApprovalStatuses)),
    [activeApprovalStatuses, approvalRequests, handledApprovalIds],
  );
  const visibleProposedActions = useMemo(
    () => proposedActions.filter((item) => {
      const type = String(item.type || "").trim();
      if (type !== "navigation") {
        return true;
      }
      return !message.tool_suggestions.some(
        (suggestion) => sameActionLabel(suggestion.tool, item.tool) || sameActionLabel(suggestion.label, item.label),
      );
    }),
    [message.tool_suggestions, proposedActions],
  );

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
      <div className={`wa-bubble ${isUser ? "wa-bubble--user-shell" : "wa-bubble--assistant-shell"}${isUser && isEditing ? " wa-bubble--editing" : ""}`}>
        {shouldRenderAttachments && attachmentBadges.length ? (
          <div className="wa-attachments__list" style={{ alignSelf: isUser ? "flex-end" : "flex-start", marginBottom: "0.25rem" }}>
            {attachmentBadges.map((item) => {
              const attachmentItem = attachmentItems.find((a) => a.label === item.label);
              const hasPreview = Boolean(attachmentItem?.previewUrl);
              return (
                <button
                  key={`${message.id}-${item.label}`}
                  type="button"
                  className="wa-attachment-chip wa-attachment-chip--file"
                  onClick={() => hasPreview && onPreviewClick?.(attachmentItem!.previewUrl!, attachmentItem!.label, attachmentItem!.contentType || "application/pdf")}
                  aria-label={item.label}
                  style={{ 
                    cursor: hasPreview ? "pointer" : "default", 
                    padding: "0.5rem", 
                    borderRadius: "0.5rem",
                    border: "1px solid var(--border-color)",
                    background: "var(--bg-surface)"
                  }}
                >
                  <div className="wa-attachment-chip__placeholder" style={{ width: "32px", height: "32px", borderRadius: "6px" }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    </svg>
                  </div>
                  <div className="wa-attachment-chip__meta">
                    <strong>{item.label}</strong>
                    <span>{attachmentTypeLabel(attachmentItem?.label || item.label, attachmentItem?.contentType)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        ) : null}
        {shouldRenderAttachments && visualAttachments.length ? (
          <div className="wa-bubble__media-row" style={{ alignSelf: isUser ? "flex-end" : "flex-start", marginBottom: "0.25rem", display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
            {visualAttachments.map((item) => (
              <button
                key={`${message.id}-img-${item.label}`}
                type="button"
                className="wa-bubble__media-thumb"
                onClick={() => onPreviewClick?.(item.previewUrl || "", item.label, item.contentType || "image/png")}
                aria-label={item.label}
                style={{
                  cursor: "pointer",
                  padding: 0,
                  border: "1px solid var(--border-color)",
                  borderRadius: "0.5rem",
                  overflow: "hidden",
                  background: "var(--bg-surface)",
                  display: "block",
                  width: "120px",
                  height: "80px",
                  position: "relative",
                }}
              >
                <img
                  src={item.previewUrl}
                  alt={item.label}
                  loading="lazy"
                  style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                />
              </button>
            ))}
          </div>
        ) : null}
        {Boolean(bubbleText || isEditing || isAssistant) ? (
          <div className={`wa-bubble__surface ${isUser ? "wa-bubble__surface--user" : "wa-bubble__surface--assistant"}`}>
            {isUser && isEditing ? (
            <div className="wa-bubble__edit-shell">
              <textarea
                ref={editTextareaRef}
                className="wa-bubble__edit-input"
                rows={Math.min(10, Math.max(4, (editValue || String(message.content || "")).split("\n").length + 1))}
                value={editValue || String(message.content || "")}
                onChange={(event) => onEditValueChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    event.preventDefault();
                    onCancelEdit();
                    return;
                  }
                  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                    event.preventDefault();
                    onSubmitEdit(message);
                  }
                }}
              />
              <div className="wa-bubble__edit-actions">
                <button className="wa-bubble__edit-btn wa-bubble__edit-btn--ghost" type="button" onClick={onCancelEdit} disabled={editBusy}>
                  İptal
                </button>
                <button className="wa-bubble__edit-btn wa-bubble__edit-btn--primary" type="button" onClick={() => onSubmitEdit(message)} disabled={editBusy || !editValue.trim()}>
                  {editBusy ? "Gönderiliyor..." : "Gönder"}
                </button>
              </div>
            </div>
          ) : (
            <div className="wa-bubble__text">{bubbleText}</div>
          )}

          {isAssistant && (Boolean(integrationSetup) || Boolean(mapPreview) || webSearchResults.length > 0 || travelOptions.length > 0 || visibleProposedActions.length > 0 || approvalRequests.length > 0 || memoryUpdates.length > 0) ? (
            <div className="wa-bubble__extras">
              {mapPreview ? (
                <div className="wa-bubble__suggestions">
                  <span className="wa-bubble__suggestion-label">
                    {mapPreview.sourceKind === "calendar_event" ? "Konum ve rota" : "Harita görünümü"}
                  </span>
                  <article className="wa-map-card">
                    <button
                      className="wa-map-card__preview"
                      type="button"
                      onClick={() => setIsMapExpanded(true)}
                      aria-label={`${mapPreview.title} haritasını büyüt`}
                    >
                      {mapPreview.embedUrl ? (
                        <iframe
                          className="wa-map-card__iframe"
                          src={mapPreview.embedUrl}
                          title={`${mapPreview.title} harita önizlemesi`}
                          loading="lazy"
                          referrerPolicy="no-referrer-when-downgrade"
                        />
                      ) : (
                        <div className="wa-map-card__placeholder">
                          <strong>{mapPreview.destinationLabel}</strong>
                          <span>Haritayı büyütmek için tıkla</span>
                        </div>
                      )}
                      <span className="wa-map-card__expand-badge">Büyüt</span>
                    </button>
                    <div className="wa-map-card__body">
                      <div className="wa-map-card__header">
                        <div>
                          <strong>{mapPreview.title}</strong>
                          {mapPreview.subtitle ? <p>{mapPreview.subtitle}</p> : null}
                        </div>
                        {mapPreview.routeMode ? (
                          <StatusBadge tone="accent">{locationRouteModeLabel(mapPreview.routeMode)}</StatusBadge>
                        ) : null}
                      </div>
                      <div className="wa-map-card__meta">
                        <span>{mapPreview.destinationLabel}</span>
                        {mapPreview.originLabel ? <span>{`Çıkış: ${mapPreview.originLabel}`}</span> : null}
                      </div>
                      <div className="wa-map-card__actions">
                        {mapPreview.directionsUrl ? (
                          <a className="wa-bubble__action-btn wa-bubble__action-btn--primary" href={mapPreview.directionsUrl} target="_blank" rel="noreferrer">
                            Yol tarifi
                          </a>
                        ) : null}
                        {mapPreview.mapsUrl ? (
                          <a className="wa-bubble__action-btn" href={mapPreview.mapsUrl} target="_blank" rel="noreferrer">
                            Haritada aç
                          </a>
                        ) : null}
                      </div>
                    </div>
                  </article>
                </div>
              ) : null}
              {integrationSetup ? (
                <div className="wa-bubble__suggestions">
                  <span className="wa-bubble__suggestion-label">Bağlantı yardımcısı</span>
                  <div className="wa-bubble__draft-preview">
                    <strong>{String(integrationSetup.service_name || integrationSetup.connector_id || "Bağlayıcı")}</strong>
                    <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
                      {String(integrationSetup.status || "").trim() ? <StatusBadge tone={statusTone(String(integrationSetup.status || ""))}>{statusLabel(String(integrationSetup.status || ""))}</StatusBadge> : null}
                      {String(integrationSetup.access_level || "").trim() ? <StatusBadge>{integrationAccessLabel(String(integrationSetup.access_level || ""))}</StatusBadge> : null}
                    </div>
                    {integrationSetupSummary ? (
                      <p className="wa-bubble__helper-text" style={{ marginTop: "0.65rem", marginBottom: 0 }}>
                        {integrationSetupSummary}
                      </p>
                    ) : null}
                    {String(integrationSetup.next_step || "").trim() ? (
                      <div style={{ marginTop: "0.65rem", display: "grid", gap: "0.25rem" }}>
                        <strong style={{ fontSize: "0.92rem" }}>Sıradaki adım</strong>
                        <p style={{ margin: 0 }}>{String(integrationSetup.next_step || "")}</p>
                      </div>
                    ) : null}
                    {integrationSetupCapabilities.length > 0 ? (
                      <div style={{ marginTop: "0.75rem", display: "grid", gap: "0.35rem" }}>
                        <strong style={{ fontSize: "0.92rem" }}>Bu bağlantı tamamlandığında yapabileceklerim</strong>
                        <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                          {integrationSetupCapabilities.map((item) => (
                            <StatusBadge key={`${message.id}-integration-capability-${item}`} tone="accent">{item}</StatusBadge>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {Array.isArray(integrationSetup.review_summary) && integrationSetup.review_summary.length > 0 ? (
                      <div style={{ marginTop: "0.65rem", display: "grid", gap: "0.3rem" }}>
                        <strong style={{ fontSize: "0.92rem" }}>
                          {String(integrationSetup.setup_mode || "") === "legacy_desktop" ? "Kurulum adımları" : "Kurulum notları"}
                        </strong>
                        {(integrationSetup.review_summary as string[]).map((item) => (
                          <p key={`${message.id}-integration-review-${item}`} className="list-item__meta" style={{ marginBottom: "0.35rem" }}>{item}</p>
                        ))}
                      </div>
                    ) : null}
                    {integrationSetupIsWhatsApp && (
                      integrationSetupDesktopMessage
                      || integrationSetupDesktopError
                      || integrationSetupDesktopWebStatus
                      || integrationSetupDesktopQrDataUrl
                    ) ? (
                      <div style={{ marginTop: "0.75rem", display: "grid", gap: "0.45rem" }}>
                        <strong style={{ fontSize: "0.92rem" }}>Canlı kurulum durumu</strong>
                        <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                          {integrationSetupDesktopWebStatus ? (
                            <StatusBadge tone={whatsAppWebStatusTone(integrationSetupDesktopWebStatus)}>
                              {whatsAppWebStatusLabel(integrationSetupDesktopWebStatus) || integrationSetupDesktopWebStatus}
                            </StatusBadge>
                          ) : null}
                        </div>
                        {integrationSetupDesktopMessage ? (
                          <p className="wa-bubble__helper-text" style={{ marginBottom: 0 }}>
                            {integrationSetupDesktopMessage}
                          </p>
                        ) : null}
                        {integrationSetupDesktopError ? (
                          <p className="wa-bubble__helper-text" style={{ marginBottom: 0, color: "var(--danger-600)" }}>
                            {integrationSetupDesktopError}
                          </p>
                        ) : null}
                        {integrationSetupDesktopAccountLabel ? (
                          <p className="wa-bubble__helper-text" style={{ marginBottom: 0 }}>
                            {`Bağlanan hesap: ${integrationSetupDesktopAccountLabel}`}
                          </p>
                        ) : null}
                        {integrationSetupDesktopCurrentUser ? (
                          <p className="wa-bubble__helper-text" style={{ marginBottom: 0 }}>
                            {`WhatsApp kimliği: ${integrationSetupDesktopCurrentUser}`}
                          </p>
                        ) : null}
                        {integrationSetupDesktopQrDataUrl ? (
                          <div
                            style={{
                              display: "grid",
                              gap: "0.5rem",
                              justifyItems: "start",
                              padding: "0.75rem",
                              borderRadius: "1rem",
                              background: "rgba(255,255,255,0.06)",
                            }}
                          >
                            <img
                              src={integrationSetupDesktopQrDataUrl}
                              alt="WhatsApp QR kodu"
                              style={{
                                width: "min(18rem, 100%)",
                                maxWidth: "100%",
                                borderRadius: "0.85rem",
                                background: "#ffffff",
                                padding: "0.6rem",
                              }}
                            />
                            <p className="wa-bubble__helper-text" style={{ marginBottom: 0 }}>
                              Telefondaki WhatsApp uygulamasında Bağlı cihazlar bölümünü açıp bu QR kodunu tarayın.
                            </p>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="wa-bubble__approval-actions" style={{ marginTop: "0.75rem" }}>
                      {canRunLegacySetup ? (
                        <button
                          className="wa-bubble__action-btn wa-bubble__action-btn--primary"
                          type="button"
                          disabled={isDesktopSetupBusy}
                          onClick={() => void handleRunLegacySetup()}
                        >
                          {isDesktopSetupBusy
                            ? "Kurulum hazırlanıyor..."
                            : String(integrationSetup.desktop_cta_label || "Kuruluma sohbetten devam et")}
                        </button>
                      ) : null}
                      {String(integrationSetup.deep_link_path || "").trim() ? (
                        <Link className="wa-bubble__action-btn" to={String(integrationSetup.deep_link_path || "")}>
                          Kurulum ekranını aç
                        </Link>
                      ) : null}
                      {String(integrationSetup.authorization_url || "").trim() ? (
                        <a className="wa-bubble__action-btn" href={String(integrationSetup.authorization_url || "")} target="_blank" rel="noreferrer">
                          İzin ekranını aç
                        </a>
                      ) : null}
                    </div>
                    {Array.isArray(integrationSetup.suggested_replies) && integrationSetup.suggested_replies.length > 0 ? (
                      <div className="wa-bubble__suggestion-chips" style={{ marginTop: "0.75rem" }}>
                        {(integrationSetup.suggested_replies as string[]).map((item) => (
                          <button key={`${message.id}-integration-reply-${item}`} className="wa-chip" type="button" onClick={() => onQuickReply(item)}>
                            {item}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}
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
                          <button className="wa-bubble__action-btn wa-bubble__action-btn--primary" type="button" disabled={isBusy} onClick={() => onApproveApproval(item, message as any)}>
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
              {memoryUpdates.length > 0 && !isOnboardingBubble ? (
                <div className="wa-bubble__draft-preview">
                  <strong>Bellek güncellemesi</strong>
                  {memoryUpdates.map((item, index) => (
                    <div key={`memory-${message.id}-${index}`} style={{ marginTop: index === 0 ? "0.5rem" : "0.75rem" }}>
                      <p style={{ marginBottom: 0.35 }}>{String(item.summary || item.value || "Profil notu güncellendi.")}</p>
                      {Array.isArray(item.warnings) ? item.warnings.map((warning, warningIndex) => (
                        <p key={`memory-warning-${message.id}-${index}-${warningIndex}`} style={{ marginBottom: 0.35 }}>
                          {String(warning)}
                        </p>
                      )) : null}
                      {item.route ? (
                        <Link className="wa-bubble__action-btn" to={item.route}>
                          {String(item.action_label || tr.assistant.openSettingsAction || "Ayarları aç")}
                        </Link>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
        ) : null}

        <div className={`wa-bubble__actions ${isUser ? "wa-bubble__actions--user" : "wa-bubble__actions--assistant"}${isUser && isEditing ? " wa-bubble__actions--hidden" : ""}`}>
          <button
            className="wa-bubble__icon-btn"
            type="button"
            aria-label={isUser ? "Mesajı kopyala" : "Yanıtı kopyala"}
            title={isUser ? "Mesajı kopyala" : "Yanıtı kopyala"}
            onClick={handleCopy}
          >
            {isCopied ? (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            ) : (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M8 8V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2" />
                <rect width="10" height="10" x="4" y="10" rx="2" ry="2" />
              </svg>
            )}
          </button>
          {isUser ? (
            <button
              className="wa-bubble__icon-btn"
              type="button"
              aria-label="Mesajı düzenle"
              title="Mesajı düzenle"
              onClick={() => onEditMessage(message)}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
              </svg>
            </button>
          ) : null}
          {isAssistant ? (
            <>
              <button
                className="wa-bubble__icon-btn"
                type="button"
                aria-label="Mesajı paylaş"
                title="Mesajı paylaş"
                onClick={() => onShareMessage(message)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
              </button>
              <button
                className={`wa-bubble__icon-btn${isExplainabilityOpen ? " wa-bubble__icon-btn--active" : ""}`}
                type="button"
                aria-label={isExplainabilityOpen ? "Yanıt açıklamasını kapat" : "Yanıt açıklamasını aç"}
                aria-pressed={isExplainabilityOpen}
                title={isExplainabilityOpen ? "Yanıt açıklamasını kapat" : "Yanıt açıklamasını aç"}
                onClick={() => setIsExplainabilityOpen((current) => !current)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 16v-4" />
                  <path d="M12 8h.01" />
                </svg>
              </button>
              <button
                className={`wa-bubble__icon-btn${feedbackValue === "liked" ? " wa-bubble__icon-btn--active wa-bubble__icon-btn--positive" : ""}`}
                type="button"
                aria-label="Yanıtı beğen"
                aria-pressed={feedbackValue === "liked"}
                title={feedbackValue === "liked" ? "İyi yanıt" : "Yanıtı beğen"}
                onClick={() => onSetFeedback(message, "liked")}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
                </svg>
              </button>
              <button
                className={`wa-bubble__icon-btn${feedbackValue === "disliked" ? " wa-bubble__icon-btn--active wa-bubble__icon-btn--negative" : ""}`}
                type="button"
                aria-label="Yanıtı beğenme"
                aria-pressed={feedbackValue === "disliked"}
                title={feedbackValue === "disliked" ? "Yanıt beğenilmedi" : "Yanıtı beğenme"}
                onClick={() => onSetFeedback(message, "disliked")}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3" />
                </svg>
              </button>
              {canStar ? (
                <button
                  className={`wa-bubble__icon-btn${message.starred ? " wa-bubble__icon-btn--active wa-bubble__icon-btn--starred" : ""}`}
                  type="button"
                  disabled={isStarBusy}
                  aria-label={message.starred ? "Yıldızı kaldır" : "Mesajı yıldızla"}
                  aria-pressed={message.starred}
                  title={message.starred ? "Yıldızı kaldır" : "Mesajı yıldızla"}
                  onClick={() => onToggleStar(message)}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill={message.starred ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <polygon points="12 2 15.1 8.3 22 9.3 17 14.2 18.2 21 12 17.7 5.8 21 7 14.2 2 9.3 8.9 8.3 12 2" />
                  </svg>
                </button>
              ) : null}
            </>
          ) : null}
        </div>
        {isAssistant && explainability && isExplainabilityOpen ? (
          <div className="wa-bubble__extras">
            <div className="wa-bubble__suggestions">
              <div className="callout callout--muted" style={{ marginTop: "0.2rem" }}>
                <p style={{ marginBottom: "0.6rem" }}>{String(explainability.why_this || "Bu yanıt konuşma ve bilgi tabanı bağlamıyla üretildi.")}</p>
                <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.65rem" }}>
                  {memoryScopes.map((scope) => (
                    <StatusBadge key={`${message.id}-scope-${scope}`} tone="neutral">{memoryScopeLabel(scope)}</StatusBadge>
                  ))}
                  {explainabilityConfidenceLabelText ? (
                    <StatusBadge tone="accent">{explainabilityConfidenceLabelText}</StatusBadge>
                  ) : null}
                  {Boolean(explainability.requires_confirmation) ? (
                    <StatusBadge tone="warning">İşlem öncesi onay gerekir</StatusBadge>
                  ) : null}
                </div>
                {claimSummaryLines.length > 0 ? (
                  <div style={{ marginBottom: "0.65rem" }}>
                    <strong style={{ display: "block", marginBottom: "0.35rem" }}>Doğrulanmış bilgiler</strong>
                    {claimSummaryLines.slice(0, 3).map((line, index) => (
                      <div key={`${message.id}-claim-line-${index}`} className="list-item__meta" style={{ marginBottom: "0.25rem" }}>
                        {String(line || "").replace(/^-+\s*/, "")}
                      </div>
                    ))}
                  </div>
                ) : null}
                {assistantContextPack.length > 0 ? (
                  <div style={{ marginBottom: "0.65rem" }}>
                    <strong style={{ display: "block", marginBottom: "0.35rem" }}>Asistanın o anda gördüğü bağlam</strong>
                    {assistantContextPack.slice(0, 4).map((item, index) => (
                      <div key={`${message.id}-context-pack-${index}`} style={{ marginBottom: "0.45rem" }}>
                        <div>
                          <span>{String(item.title || item.predicate || "Bağlam girdisi")}</span>
                          <span className="list-item__meta">{` · ${assistantContextFamilyLabel(item.family)} · ${memoryScopeLabel(String(item.scope || ""))} · ${assistantContextFreshnessLabel(item.freshness)}`}</span>
                        </div>
                        <div className="list-item__meta" style={{ marginBottom: 0 }}>
                          {assistantContextVisibilityLabel(item.assistant_visibility)}
                          {String(item.summary || "").trim() ? ` · ${String(item.summary || "").trim()}` : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
                {supportingRecords.length > 0 ? (
                  <div style={{ marginBottom: "0.65rem" }}>
                    <strong style={{ display: "block", marginBottom: "0.35rem" }}>Dayandığı kayıtlar</strong>
                    {supportingRecords.slice(0, 2).map((item, index) => (
                      <div key={`${message.id}-kb-${index}`} style={{ marginBottom: "0.35rem" }}>
                        <span>{String(item.title || item.page_key || "Kayıt")}</span>
                        {String(item.scope || "").trim() ? <span className="list-item__meta">{` · ${memoryScopeLabel(String(item.scope || ""))}`}</span> : null}
                      </div>
                    ))}
                  </div>
                ) : null}
                {explainabilityReasonSummaryText ? (
                  <p className="list-item__meta" style={{ marginBottom: "0.65rem" }}>
                    {explainabilityReasonSummaryText}
                  </p>
                ) : null}
                <div className="wa-bubble__suggestion-chips">
                  {primarySupportingRecord ? (
                    <>
                      <button
                        className="wa-chip"
                        type="button"
                        onClick={() => {
                          const correctedSummary = window.prompt(
                            "Doğru hafıza özeti",
                            String(primarySupportingRecord.summary || primarySupportingRecord.title || ""),
                          );
                          if (!correctedSummary) {
                            return;
                          }
                          void onMessageMemoryAction({
                            action: "correct",
                            page_key: String(primarySupportingRecord.page_key || ""),
                            target_record_id: String(primarySupportingRecord.record_id || ""),
                            corrected_summary: correctedSummary,
                            scope: String(primarySupportingRecord.scope || ""),
                            note: "Chat explainability drawer üzerinden düzeltildi.",
                            source_refs: Array.isArray(explainability.source_basis) ? explainability.source_basis as Array<Record<string, unknown> | string> : [],
                          });
                        }}
                      >
                        Bu bilgiyi düzelt
                      </button>
                      <button
                        className="wa-chip"
                        type="button"
                        onClick={() => {
                          if (!window.confirm("Bu memory kaydı unutulsun mu?")) {
                            return;
                          }
                          void onMessageMemoryAction({
                            action: "forget",
                            page_key: String(primarySupportingRecord.page_key || ""),
                            target_record_id: String(primarySupportingRecord.record_id || ""),
                            note: "Chat explainability drawer üzerinden unutuldu.",
                            source_refs: Array.isArray(explainability.source_basis) ? explainability.source_basis as Array<Record<string, unknown> | string> : [],
                          });
                        }}
                      >
                        Bunu unut
                      </button>
                      <button
                        className="wa-chip"
                        type="button"
                        onClick={() => {
                          void onMessageMemoryAction({
                            action: "reduce_confidence",
                            page_key: String(primarySupportingRecord.page_key || ""),
                            target_record_id: String(primarySupportingRecord.record_id || ""),
                            scope: String(primarySupportingRecord.scope || ""),
                            note: "Chat explainability drawer üzerinden güven azaltıldı.",
                            source_refs: Array.isArray(explainability.source_basis) ? explainability.source_basis as Array<Record<string, unknown> | string> : [],
                          });
                        }}
                      >
                        Güveni düşür
                      </button>
                      <button
                        className="wa-chip"
                        type="button"
                        onClick={() => {
                          const nextScope = window.prompt("Yeni scope", String(primarySupportingRecord.scope || "personal"));
                          if (!nextScope) {
                            return;
                          }
                          void onMessageMemoryAction({
                            action: "change_scope",
                            page_key: String(primarySupportingRecord.page_key || ""),
                            target_record_id: String(primarySupportingRecord.record_id || ""),
                            scope: nextScope,
                            note: "Chat explainability drawer üzerinden scope taşındı.",
                            source_refs: Array.isArray(explainability.source_basis) ? explainability.source_basis as Array<Record<string, unknown> | string> : [],
                          });
                        }}
                      >
                        Başka scope'a taşı
                      </button>
                    </>
                  ) : null}
                  <button
                    className="wa-chip"
                    type="button"
                    onClick={() => {
                      const topic = String(primarySupportingRecord?.title || message.generated_from || "assistant");
                      void onMessageMemoryAction({
                        action: "suppress_recommendation",
                        recommendation_kind: topic,
                        scope: String(primarySupportingRecord?.scope || "personal"),
                        note: "Chat yanıtı düzeyinde daha az öner tercih edildi.",
                        source_refs: Array.isArray(explainability.source_basis) ? explainability.source_basis as Array<Record<string, unknown> | string> : [],
                      });
                    }}
                  >
                    Bu konuda daha az öner
                  </button>
                  <button
                    className="wa-chip"
                    type="button"
                    onClick={() => {
                      const topic = String(primarySupportingRecord?.title || message.generated_from || "assistant");
                      void onMessageMemoryAction({
                        action: "boost_proactivity",
                        topic,
                        scope: String(primarySupportingRecord?.scope || "personal"),
                        note: "Chat yanıtı düzeyinde daha proaktif ol tercihi verildi.",
                        source_refs: Array.isArray(explainability.source_basis) ? explainability.source_basis as Array<Record<string, unknown> | string> : [],
                      });
                    }}
                  >
                    Bu konuda daha proaktif ol
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : null}
        {isAssistant && feedbackValue ? (
          <div className="wa-bubble__extras">
            <div className="wa-bubble__suggestions">
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
                <span className="wa-bubble__suggestion-label">{feedbackValue === "liked" ? "Neyi beğendin?" : "Neden beğenmedin?"}</span>
                {!isFeedbackReasonOpen ? (
                  <button className="wa-chip" type="button" onClick={() => setIsFeedbackReasonOpen(true)}>
                    {String(message.feedback_note || "").trim() ? "Açıklamayı düzenle" : "Açıklama ekle"}
                  </button>
                ) : null}
              </div>
              {String(message.feedback_note || "").trim() && !isFeedbackReasonOpen ? (
                <p className="wa-bubble__helper-text" style={{ marginTop: "0.6rem", marginBottom: 0 }}>
                  {String(message.feedback_note || "")}
                </p>
              ) : null}
              {isFeedbackReasonOpen ? (
                <div className="wa-bubble__edit-shell wa-bubble__edit-shell--feedback" style={{ marginTop: "0.65rem" }}>
                  <textarea
                    className="wa-bubble__edit-input wa-bubble__edit-input--feedback"
                    rows={3}
                    value={feedbackReasonDraft}
                    placeholder={
                      feedbackValue === "liked"
                        ? "Örneğin: Anneme sıcak yazman iyiydi, çiçek önerin de uygundu."
                        : "Örneğin: Annem çikolatayı sevmiyor, daha kısa ve sade olmalı."
                    }
                    onChange={(event) => setFeedbackReasonDraft(event.target.value)}
                  />
                  <div className="wa-bubble__edit-actions">
                    <button
                      className="wa-bubble__edit-btn wa-bubble__edit-btn--ghost"
                      type="button"
                      disabled={isFeedbackReasonSaving}
                      onClick={() => {
                        setFeedbackReasonDraft(String(message.feedback_note || ""));
                        setIsFeedbackReasonOpen(false);
                      }}
                    >
                      {String(message.feedback_note || "").trim() ? "Kapat" : "Şimdi değil"}
                    </button>
                    <button
                      className="wa-bubble__edit-btn wa-bubble__edit-btn--primary"
                      type="button"
                      disabled={isFeedbackReasonSaving || !feedbackReasonDraft.trim()}
                      onClick={async () => {
                        setIsFeedbackReasonSaving(true);
                        try {
                          await onSubmitFeedbackNote(message, feedbackValue, feedbackReasonDraft.trim());
                          setIsFeedbackReasonOpen(false);
                        } finally {
                          setIsFeedbackReasonSaving(false);
                        }
                      }}
                    >
                      {isFeedbackReasonSaving ? "Kaydediliyor..." : "Kaydet"}
                    </button>
                  </div>
                  <p className="wa-bubble__helper-text" style={{ marginTop: "0.6rem", marginBottom: 0 }}>
                    Bu açıklama kişi profili, iletişim tarzı ve öneri tercihleri için öğrenim sinyali olarak kullanılacak.
                  </p>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
      {isAssistant && mapPreview && isMapExpanded ? (
        <div className="assistant-map-modal-backdrop" role="presentation" onClick={() => setIsMapExpanded(false)}>
          <div
            className="assistant-map-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby={`assistant-map-modal-title-${message.id}`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="assistant-map-modal__header">
              <div className="assistant-map-modal__copy">
                <h3 id={`assistant-map-modal-title-${message.id}`}>{mapPreview.title}</h3>
                {mapPreview.subtitle ? <p>{mapPreview.subtitle}</p> : null}
              </div>
              <button className="assistant-map-modal__close" type="button" onClick={() => setIsMapExpanded(false)} aria-label="Haritayı kapat">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
            </div>
            <div className="assistant-map-modal__canvas">
              {mapPreview.embedUrl ? (
                <iframe
                  className="assistant-map-modal__iframe"
                  src={mapPreview.embedUrl}
                  title={`${mapPreview.title} haritası`}
                  loading="eager"
                  referrerPolicy="no-referrer-when-downgrade"
                />
              ) : (
                <div className="assistant-map-modal__placeholder">
                  <strong>{mapPreview.destinationLabel}</strong>
                  <span>Bu konum için gömülü önizleme hazır değil.</span>
                </div>
              )}
            </div>
            <div className="assistant-map-modal__footer">
              <div className="assistant-map-modal__meta">
                <span>{mapPreview.destinationLabel}</span>
                {mapPreview.originLabel ? <span>{`Çıkış: ${mapPreview.originLabel}`}</span> : null}
              </div>
              <div className="assistant-map-modal__actions">
                {mapPreview.directionsUrl ? (
                  <a className="assistant-confirm-dialog__button" href={mapPreview.directionsUrl} target="_blank" rel="noreferrer">
                    Yol tarifi
                  </a>
                ) : null}
                {mapPreview.mapsUrl ? (
                  <a className="assistant-confirm-dialog__button assistant-confirm-dialog__button--secondary" href={mapPreview.mapsUrl} target="_blank" rel="noreferrer">
                    Haritada aç
                  </a>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}, (prevProps, nextProps) => {
  if (prevProps.message !== nextProps.message) {
    return false;
  }
  if (prevProps.feedbackValue !== nextProps.feedbackValue) {
    return false;
  }
  if (prevProps.isEditing !== nextProps.isEditing) {
    return false;
  }
  if (prevProps.editValue !== nextProps.editValue) {
    return false;
  }
  if (prevProps.editBusy !== nextProps.editBusy) {
    return false;
  }
  if ((prevProps.starBusyMessageId === prevProps.message.id) !== (nextProps.starBusyMessageId === nextProps.message.id)) {
    return false;
  }
  return chatBubbleApprovalSignature(prevProps.message, prevProps.approvalBusyId, prevProps.handledApprovalIds)
    === chatBubbleApprovalSignature(nextProps.message, nextProps.approvalBusyId, nextProps.handledApprovalIds);
});

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

type SidebarNavIconName = "compose" | "search" | "star" | "profile" | "memory" | "settings";

function SidebarToggleIcon({ expanded }: { expanded: boolean }) {
  void expanded;
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3.5" y="4.75" width="17" height="14.5" rx="3.4" />
      <path d="M9 4.75v14.5" />
    </svg>
  );
}

function SidebarNavIcon({ name, active = false }: { name: SidebarNavIconName; active?: boolean }) {
  if (name === "compose") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
      </svg>
    );
  }
  if (name === "search") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="11" cy="11" r="6.75" />
        <path d="m20 20-3.5-3.5" />
      </svg>
    );
  }
  if (name === "star") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="m12 3.75 2.55 5.2 5.7.82-4.13 4.02.98 5.68L12 16.78 6.9 19.47l.98-5.68-4.13-4.02 5.7-.82Z" />
      </svg>
    );
  }
  if (name === "profile") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 12.25a3.85 3.85 0 1 0 0-7.7 3.85 3.85 0 0 0 0 7.7Z" />
        <path d="M5.2 19.25a6.8 6.8 0 0 1 13.6 0" />
      </svg>
    );
  }
  if (name === "memory") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M6.25 4.75h8.5l3 3v11.5a2 2 0 0 1-2 2h-9.5a2 2 0 0 1-2-2v-12.5a2 2 0 0 1 2-2Z" />
        <path d="M14.75 4.75v3.5h3.5" />
        <path d="M8.25 11.25h7.5" />
        <path d="M8.25 15.25h7.5" />
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function ThreadOverflowIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="5" cy="12" r="1.7" />
      <circle cx="12" cy="12" r="1.7" />
      <circle cx="19" cy="12" r="1.7" />
    </svg>
  );
}

function ThreadRenameIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12.5 4.75H7a2.25 2.25 0 0 0-2.25 2.25v10A2.25 2.25 0 0 0 7 19.25h10A2.25 2.25 0 0 0 19.25 17v-5.5" />
      <path d="m14.15 6.35 3.5 3.5" />
      <path d="m9.45 15.85 1.9-.42 6.05-6.05a1.45 1.45 0 0 0 0-2.05l-.72-.72a1.45 1.45 0 0 0-2.05 0l-6.05 6.05z" />
    </svg>
  );
}

function ThreadDeleteIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3.75 6.75h16.5" />
      <path d="M9.25 3.75h5.5" />
      <path d="M8 6.75v11a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-11" />
      <path d="M10 10.25v5.5" />
      <path d="M14 10.25v5.5" />
    </svg>
  );
}

/* ── Main Page Component ─────────────────────────────────── */

export function AssistantPage() {
  const { settings } = useAppContext();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const text = tr.assistant;
  const rawSelectedTool = searchParams.get("tool");
  const selectedTool = isToolKey(rawSelectedTool) ? rawSelectedTool : null;
  const promptFromRoute = searchParams.get("prompt");
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(() => searchParams.get("sidebar") !== "0");
  const [sidebarSection, setSidebarSection] = useState<AssistantSidebarSection>(() => (
    searchParams.get("stars") === "1" ? "starred" : "threads"
  ));
  const isThreadHistoryOpen = isSidebarExpanded && sidebarSection === "threads";
  const isStarredMessagesOpen = isSidebarExpanded && sidebarSection === "starred";

  // state
  const [home, setHome] = useState<AssistantHomeResponse | null>(null);
  const [threadSummaries, setThreadSummaries] = useState<AssistantThreadSummary[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState(() => loadSelectedAssistantThreadId());
  const [threadSearch, setThreadSearch] = useState("");
  const [starredSearch, setStarredSearch] = useState("");
  const [threadMessages, setThreadMessages] = useState<AssistantThreadMessage[]>([]);
  const [starredMessages, setStarredMessages] = useState<AssistantThreadMessage[]>([]);
  const [streamingAssistantMessage, setStreamingAssistantMessage] = useState<ThreadDisplayMessage | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [agenda, setAgenda] = useState<AssistantAgendaItem[]>([]);
  const [inbox, setInbox] = useState<AssistantAgendaItem[]>([]);
  const [calendar, setCalendar] = useState<AssistantCalendarItem[]>([]);
  const [calendarToday, setCalendarToday] = useState(dayKeyFromDate(new Date()));
  const [calendarGoogleState, setCalendarGoogleState] = useState<DesktopGoogleState | null>(null);
  const [calendarOutlookState, setCalendarOutlookState] = useState<DesktopOutlookState | null>(null);
  const [googleStatus, setGoogleStatus] = useState<GoogleIntegrationStatus | null>(null);
  const [googleDriveFiles, setGoogleDriveFiles] = useState<GoogleDriveFile[]>([]);
  const [actions, setActions] = useState<SuggestedAction[]>([]);
  const [drafts, setDrafts] = useState<OutboundDraft[]>([]);
  const [matterDrafts, setMatterDrafts] = useState<Draft[]>([]);
  const [matters, setMatters] = useState<Matter[]>([]);
  const [documents, setDocuments] = useState<WorkspaceDocument[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isThreadListLoading, setIsThreadListLoading] = useState(false);
  const [isCreatingThread, setIsCreatingThread] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResponding, setIsResponding] = useState(false);
  const [isGoogleSyncing, setIsGoogleSyncing] = useState(false);
  const [isLocationRefreshing, setIsLocationRefreshing] = useState(false);
  const [isOrchestrationRunning, setIsOrchestrationRunning] = useState(false);
  const [isCoachSaving, setIsCoachSaving] = useState(false);
  const [coachGoalForm, setCoachGoalForm] = useState({
    title: "",
    summary: "",
    targetValue: "",
    unit: "sayfa",
    cadence: "daily",
    reminderTime: "08:00",
    targetDate: "",
    allowDesktopNotifications: true,
  });
  const [coachProgressDrafts, setCoachProgressDrafts] = useState<Record<string, { amount: string; note: string }>>({});
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
  const [attachmentPreviewIndex, setAttachmentPreviewIndex] = useState<Record<string, string>>({});
  const [fullscreenPreview, setFullscreenPreview] = useState<{ url: string; name: string; type: string } | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isVoiceModeActive, setIsVoiceModeActive] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isVoiceAnalyzing, setIsVoiceAnalyzing] = useState(false);
  const [isVoiceSettingsOpen, setIsVoiceSettingsOpen] = useState(false);
  const [isVoicePlaybackEnabled, setIsVoicePlaybackEnabled] = useState(() => {
    if (typeof window === "undefined") {
      return true;
    }
    return String(window.localStorage.getItem(VOICE_PLAYBACK_PREFERENCE_STORAGE_KEY) || "").trim().toLowerCase() !== "false";
  });
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceLastReply, setVoiceLastReply] = useState("");
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [desktopVoices, setDesktopVoices] = useState<DesktopVoiceOption[]>([]);
  const [selectedVoiceId, setSelectedVoiceId] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }
    const stored = String(window.localStorage.getItem(VOICE_PREFERENCE_STORAGE_KEY) || "").trim();
    return stored === AUTO_VOICE_PREFERENCE ? "" : stored;
  });
  const [approvalBusyId, setApprovalBusyId] = useState("");
  const [starBusyMessageId, setStarBusyMessageId] = useState<number | null>(null);
  const [activeApprovalStatuses, setActiveApprovalStatuses] = useState<Record<string, string>>({});
  const [draftBusyId, setDraftBusyId] = useState("");
  const [draftBusyMode, setDraftBusyMode] = useState<"" | "send" | "remove">("");
  const [actionBusyId, setActionBusyId] = useState("");
  const [actionBusyMode, setActionBusyMode] = useState<"" | "pause" | "resume" | "retry" | "compensate">("");
  const [handledApprovalIds, setHandledApprovalIds] = useState<Record<string, string>>({});
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editingMessageDraft, setEditingMessageDraft] = useState("");
  const [threadMenuOpenId, setThreadMenuOpenId] = useState<number | null>(null);
  const [threadMenuPosition, setThreadMenuPosition] = useState<ThreadMenuPosition | null>(null);
  const [renamingThreadId, setRenamingThreadId] = useState<number | null>(null);
  const [threadRenameValue, setThreadRenameValue] = useState("");
  const [threadActionBusyId, setThreadActionBusyId] = useState<number | null>(null);
  const [deleteConfirmThread, setDeleteConfirmThread] = useState<AssistantThreadSummary | null>(null);
  const [shareDialogMessage, setShareDialogMessage] = useState<ThreadDisplayMessage | null>(null);
  const [shareChannel, setShareChannel] = useState<AssistantShareChannel>("whatsapp");
  const [shareProfiles, setShareProfiles] = useState<AssistantContactProfile[]>([]);
  const [shareProfilesLoading, setShareProfilesLoading] = useState(false);
  const [shareRecipientQuery, setShareRecipientQuery] = useState("");

  useEffect(() => {
    if (!fullscreenPreview || typeof document === "undefined") {
      return;
    }
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setFullscreenPreview(null);
      }
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [fullscreenPreview]);
  const [shareRecipient, setShareRecipient] = useState("");
  const [shareSelectedProfileId, setShareSelectedProfileId] = useState("");
  const [shareDraftSubject, setShareDraftSubject] = useState("");
  const [shareDraftBody, setShareDraftBody] = useState("");
  const [shareDialogBusy, setShareDialogBusy] = useState(false);
  const [shareDialogError, setShareDialogError] = useState("");
  const [isSessionBriefDismissed, setIsSessionBriefDismissed] = useState(() => loadSessionBriefDismissed());
  const [dismissedProactiveIds, setDismissedProactiveIds] = useState<string[]>(() => loadDismissedProactiveIds());
  const [latestAgentRun, setLatestAgentRun] = useState<AgentRun | null>(null);
  const [latestAgentRunEvents, setLatestAgentRunEvents] = useState<AgentRunEvent[]>([]);
  const [agentToolCatalog, setAgentToolCatalog] = useState<AgentToolCatalogItem[]>([]);
  const [highlightedMessageId, setHighlightedMessageId] = useState<number | null>(null);
  const [integrationSetupDesktopStates, setIntegrationSetupDesktopStates] = useState<Record<number, Record<string, unknown>>>({});
  const [error, setError] = useState("");

  // refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messageNodeMapRef = useRef<Record<number, HTMLDivElement | null>>({});
  const composerInputRef = useRef<HTMLTextAreaElement>(null);
  const inputWrapperRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const isFirstLoad = useRef(true);
  const highlightedMessageTimerRef = useRef<number | null>(null);
  const messageScrollTimerRef = useRef<number | null>(null);
  const threadMessagesRef = useRef<AssistantThreadMessage[]>([]);
  const hasMoreRef = useRef(false);
  const selectedThreadIdRef = useRef(0);
  const toolsScrollRef = useRef<HTMLDivElement>(null);
  const toolsScrollTimerRef = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const threadSearchInputRef = useRef<HTMLInputElement>(null);
  const starredSearchInputRef = useRef<HTMLInputElement>(null);
  const threadMenuRef = useRef<HTMLDivElement>(null);
  const threadMenuTriggerRefs = useRef<Record<number, HTMLButtonElement | null>>({});
  const threadRenameInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const speechPreviewRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const speechSeedPromptRef = useRef("");
  const voiceModeActiveRef = useRef(false);
  const audioCaptureModeRef = useRef<"normal" | "voice" | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaRecorderChunksRef = useRef<Blob[]>([]);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const discardRecordedAudioRef = useRef(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioAnalyserRef = useRef<AnalyserNode | null>(null);
  const audioMeterFrameRef = useRef<number | null>(null);
  const interruptStreamRef = useRef<MediaStream | null>(null);
  const interruptAudioContextRef = useRef<AudioContext | null>(null);
  const interruptAnalyserRef = useRef<AnalyserNode | null>(null);
  const interruptMeterFrameRef = useRef<number | null>(null);
  const interruptSpeechSinceRef = useRef<number | null>(null);
  const voiceTranscriptRef = useRef("");
  const voiceSilenceSinceRef = useRef<number | null>(null);
  const voiceDetectedSpeechRef = useRef(false);
  const voiceRecognitionSilenceTimerRef = useRef<number | null>(null);
  const resumeListeningAfterSpeechRef = useRef(false);
  const selectedSpeechVoiceRef = useRef<SpeechSynthesisVoice | null>(null);
  const selectedVoiceIdRef = useRef("");
  const isVoicePlaybackEnabledRef = useRef(true);
  const isRespondingRef = useRef(false);
  const speechInFlightRef = useRef(false);
  const streamingSpeechQueueRef = useRef<string[]>([]);
  const streamingSpeechCursorRef = useRef(0);
  const streamingSpeechFinalRef = useRef(false);
  const suppressAssistantSpeechRef = useRef(false);
  const attachmentStoreRef = useRef<ComposerAttachment[]>([]);
  const submittedAttachmentsRef = useRef<ComposerAttachment[]>([]);
  const attachmentPreviewIndexRef = useRef<Record<string, string>>({});
  const drawerResizeStartRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const googleAutoSyncRef = useRef<GoogleAutoSyncState>({ started: false, completed: false });
  const onboardingAutoStartRef = useRef(false);
  const agentRunSequenceRef = useRef(0);
  const submitAbortControllerRef = useRef<AbortController | null>(null);
  const lastSubmittedPromptRef = useRef("");
  const whatsAppSetupPollerRef = useRef<Record<number, number>>({});
  const whatsAppSetupSyncAttemptedRef = useRef<Record<number, boolean>>({});

  const clearWhatsAppSetupPoller = useCallback((setupId: number) => {
    const timerId = whatsAppSetupPollerRef.current[setupId];
    if (typeof timerId === "number") {
      window.clearInterval(timerId);
      delete whatsAppSetupPollerRef.current[setupId];
    }
    delete whatsAppSetupSyncAttemptedRef.current[setupId];
  }, []);

  const updateIntegrationSetupDesktopState = useCallback((setupId: number, nextState: Record<string, unknown>) => {
    setIntegrationSetupDesktopStates((current) => ({
      ...current,
      [setupId]: {
        ...(current[setupId] || {}),
        ...nextState,
        updatedAt: new Date().toISOString(),
      },
    }));
  }, []);

  const syncDesktopSetupFollowUpMessage = useCallback((setup: Record<string, unknown>, nextState: Record<string, unknown>) => {
    const setupId = Number(setup.id || 0);
    if (!setupId) {
      return;
    }
    const threadId = selectedThreadIdRef.current || Number(setup.thread_id || 0);
    if (!threadId) {
      return;
    }
    const officeId = threadMessagesRef.current.find((item) => item.thread_id === threadId)?.office_id || "default-office";
    const messageId = -(900000 + setupId);
    const content = String(nextState.message || setup.next_step || "Kurulum adımı ilerliyor.").trim() || "Kurulum adımı ilerliyor.";
    const mergedSetup = {
      ...setup,
      desktop_status_message: String(nextState.message || ""),
      desktop_status_error: String(nextState.error || ""),
      web_status: String(nextState.webStatus || ""),
      web_qr_data_url: String(nextState.webQrDataUrl || ""),
      web_account_label: String(nextState.webAccountLabel || nextState.accountLabel || ""),
      web_current_user: String(nextState.webCurrentUser || ""),
    };
    const followUpMessage: AssistantThreadMessage = {
      id: messageId,
      thread_id: threadId,
      office_id: officeId,
      role: "assistant",
      content,
      linked_entities: [],
      tool_suggestions: [],
      draft_preview: null,
      source_context: {
        integration_setup: mergedSetup,
      },
      requires_approval: false,
      generated_from: "assistant_integration_desktop_live",
      ai_provider: null,
      ai_model: null,
      starred: false,
      starred_at: null,
      feedback_value: null,
      feedback_note: null,
      feedback_at: null,
      thread_title: null,
      created_at: new Date().toISOString(),
    };
    setThreadMessages((current) => {
      const existingIndex = current.findIndex((item) => item.id === messageId);
      if (existingIndex >= 0) {
        const next = current.slice();
        next[existingIndex] = {
          ...next[existingIndex],
          ...followUpMessage,
          created_at: next[existingIndex].created_at,
        };
        return next;
      }
      return [...current, followUpMessage];
    });
  }, []);

  const startWhatsAppSetupPolling = useCallback((setupId: number) => {
    if (!window.lawcopilotDesktop?.getWhatsAppStatus) {
      return;
    }
    clearWhatsAppSetupPoller(setupId);

    const poll = async () => {
      try {
        const status = await window.lawcopilotDesktop!.getWhatsAppStatus!();
        if (!status || typeof status !== "object") {
          return;
        }
        updateIntegrationSetupDesktopState(setupId, status);
        syncDesktopSetupFollowUpMessage({ id: setupId, connector_id: "whatsapp", service_name: "WhatsApp" }, status);
        const webStatus = String(status.webStatus || "").trim().toLowerCase();
        if (
          webStatus === "ready"
          && !whatsAppSetupSyncAttemptedRef.current[setupId]
          && window.lawcopilotDesktop?.syncWhatsAppData
        ) {
          whatsAppSetupSyncAttemptedRef.current[setupId] = true;
          try {
            const syncResult = await window.lawcopilotDesktop.syncWhatsAppData();
            if (syncResult && typeof syncResult === "object") {
              updateIntegrationSetupDesktopState(setupId, {
                ...syncResult,
                synced: true,
              });
            }
          } catch (err) {
            updateIntegrationSetupDesktopState(setupId, {
              syncError: err instanceof Error ? err.message : "WhatsApp eşitlemesi tamamlanamadı.",
            });
          }
        }
        if (["ready", "session_busy", "auth_failure", "disconnected"].includes(webStatus)) {
          clearWhatsAppSetupPoller(setupId);
        }
      } catch (err) {
        updateIntegrationSetupDesktopState(setupId, {
          error: err instanceof Error ? err.message : "WhatsApp durumu alınamadı.",
        });
      }
    };

    void poll();
    whatsAppSetupPollerRef.current[setupId] = window.setInterval(() => {
      void poll();
    }, 1500);
  }, [clearWhatsAppSetupPoller, syncDesktopSetupFollowUpMessage, updateIntegrationSetupDesktopState]);

  useEffect(() => {
    return () => {
      Object.values(whatsAppSetupPollerRef.current).forEach((timerId) => window.clearInterval(timerId));
      whatsAppSetupPollerRef.current = {};
    };
  }, []);
  const pendingStreamScrollFrameRef = useRef<number | null>(null);
  const handleSubmitRef = useRef<(nextPrompt?: string, options?: { matterId?: number }) => Promise<void> | void>(() => undefined);
  const openToolRef = useRef<(tool: ToolKey) => void>(() => undefined);
  const approveApprovalRef = useRef<(approval: BubbleApprovalItem, message: ThreadDisplayMessage) => Promise<void> | void>(() => undefined);
  const rejectApprovalRef = useRef<(approval: BubbleApprovalItem) => Promise<void> | void>(() => undefined);

  useEffect(() => {
    attachmentPreviewIndexRef.current = attachmentPreviewIndex;
  }, [attachmentPreviewIndex]);

  useEffect(() => {
    threadMessagesRef.current = threadMessages;
  }, [threadMessages]);

  useEffect(() => {
    hasMoreRef.current = hasMore;
  }, [hasMore]);

  useEffect(() => {
    if (composerInputRef.current) {
      composerInputRef.current.style.height = "auto";
      composerInputRef.current.style.height = `${composerInputRef.current.scrollHeight}px`;
    }
  }, [prompt]);

  useEffect(() => {
    selectedThreadIdRef.current = selectedThreadId;
  }, [selectedThreadId]);

  useEffect(() => {
    setEditingMessageId(null);
    setEditingMessageDraft("");
  }, [selectedThreadId]);

  useEffect(() => {
    setThreadMenuOpenId(null);
    setThreadMenuPosition(null);
  }, [selectedThreadId]);

  useEffect(() => {
    if (renamingThreadId === null) {
      return;
    }
    window.setTimeout(() => {
      threadRenameInputRef.current?.focus();
      threadRenameInputRef.current?.select();
    }, 0);
  }, [renamingThreadId]);

  useEffect(() => {
    if (threadMenuOpenId === null) {
      return;
    }
    const updateMenuPosition = () => {
      const trigger = threadMenuTriggerRefs.current[threadMenuOpenId];
      if (!trigger) {
        setThreadMenuOpenId(null);
        setThreadMenuPosition(null);
        return;
      }
      const rect = trigger.getBoundingClientRect();
      const menuWidth = 212;
      const menuHeight = 112;
      const viewportPadding = 12;
      const spaceBelow = window.innerHeight - rect.bottom;
      const top = spaceBelow >= menuHeight + viewportPadding
        ? rect.bottom + 6
        : Math.max(viewportPadding, rect.top - menuHeight - 6);
      const left = Math.min(
        Math.max(viewportPadding, rect.right - menuWidth),
        window.innerWidth - menuWidth - viewportPadding,
      );
      setThreadMenuPosition({ top, left });
    };
    updateMenuPosition();
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (threadMenuRef.current?.contains(target)) {
        return;
      }
      const trigger = threadMenuTriggerRefs.current[threadMenuOpenId];
      if (trigger?.contains(target)) {
        return;
      }
      setThreadMenuOpenId(null);
      setThreadMenuPosition(null);
    };
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setThreadMenuOpenId(null);
        setThreadMenuPosition(null);
      }
    };
    window.addEventListener("scroll", updateMenuPosition, true);
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("scroll", updateMenuPosition, true);
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [threadMenuOpenId]);

  useEffect(() => {
    if (!deleteConfirmThread) {
      return;
    }
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && threadActionBusyId !== deleteConfirmThread.id) {
        setDeleteConfirmThread(null);
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [deleteConfirmThread, threadActionBusyId]);

  useEffect(() => {
    return () => {
      Object.values(attachmentPreviewIndexRef.current).forEach((item) => {
        if (item) {
          URL.revokeObjectURL(item);
        }
      });
      if (highlightedMessageTimerRef.current !== null) {
        window.clearTimeout(highlightedMessageTimerRef.current);
      }
    };
  }, []);

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

  const scheduleStreamScrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    if (pendingStreamScrollFrameRef.current !== null) {
      return;
    }
    pendingStreamScrollFrameRef.current = window.requestAnimationFrame(() => {
      pendingStreamScrollFrameRef.current = null;
      scrollToBottom(behavior);
    });
  }, [scrollToBottom]);

  /* ── Load data ──────────────────────────────────────────── */

  async function loadThreadState(
    preferredThreadId?: number | null,
    options: { allowEmpty?: boolean } = {},
  ) {
    const allowEmpty = options.allowEmpty === true;
    let summaries: AssistantThreadSummary[] = [];
    let selectedId = preferredThreadId || 0;
    let threadResponse: AssistantThreadResponse | null = null;

    try {
      const listResponse = await listAssistantThreads(settings, { limit: 100 });
      summaries = Array.isArray(listResponse.items) ? listResponse.items : [];
      if (!summaries.length) {
        if (allowEmpty) {
          return {
            summaries: [],
            selectedId: 0,
            threadResponse: null,
          };
        }
        const fallbackResponse = await getAssistantThread(settings, { limit: PAGE_SIZE });
        return {
          summaries: [summarizeAssistantThread(fallbackResponse)],
          selectedId: fallbackResponse.thread.id,
          threadResponse: fallbackResponse,
        };
      }
      if (!summaries.some((item) => item.id === selectedId)) {
        selectedId = Number(listResponse.selected_thread_id || summaries[0]?.id || 0);
      }
      if (selectedId > 0) {
        try {
          threadResponse = await getAssistantThread(settings, { limit: PAGE_SIZE, thread_id: selectedId });
        } catch {
          selectedId = Number(summaries[0]?.id || 0);
          threadResponse = selectedId > 0 ? await getAssistantThread(settings, { limit: PAGE_SIZE, thread_id: selectedId }) : null;
        }
      }
    } catch {
      if (allowEmpty) {
        return {
          summaries: [],
          selectedId: 0,
          threadResponse: null,
        };
      }
      let fallbackResponse: AssistantThreadResponse;
      try {
        fallbackResponse = await getAssistantThread(
          settings,
          preferredThreadId ? { limit: PAGE_SIZE, thread_id: preferredThreadId } : { limit: PAGE_SIZE },
        );
      } catch {
        fallbackResponse = await getAssistantThread(settings, { limit: PAGE_SIZE });
      }
      return {
        summaries: [summarizeAssistantThread(fallbackResponse)],
        selectedId: fallbackResponse.thread.id,
        threadResponse: fallbackResponse,
      };
    }

    if (!threadResponse) {
      if (allowEmpty && !summaries.length) {
        return {
          summaries: [],
          selectedId: 0,
          threadResponse: null,
        };
      }
      threadResponse = await getAssistantThread(settings, { limit: PAGE_SIZE });
      if (!selectedId) {
        selectedId = threadResponse.thread.id;
      }
      if (!summaries.some((item) => item.id === threadResponse?.thread.id)) {
        summaries = [summarizeAssistantThread(threadResponse), ...summaries];
      }
    }

    return { summaries, selectedId, threadResponse };
  }

  async function refreshThreadSummaries(preferredThreadId?: number | null) {
    setIsThreadListLoading(true);
    try {
      const threadState = await loadThreadState(preferredThreadId);
      startTransition(() => {
        setThreadSummaries(threadState.summaries);
        setSelectedThreadId(threadState.selectedId);
      });
      persistSelectedAssistantThreadId(threadState.selectedId);
      return threadState;
    } finally {
      setIsThreadListLoading(false);
    }
  }

  async function loadHomeAndThread(preferredThreadId?: number | null, options: { refreshHome?: boolean } = {}) {
    const shouldRefreshHome = options.refreshHome !== false;
    let homeResponse = home;
    if (shouldRefreshHome) {
      try {
        homeResponse = await getAssistantHome(settings);
      } catch (err) {
        if (!homeResponse) {
          setError(err instanceof Error ? err.message : text.queryError);
        }
      }
    }
    const allowEmptyThread = Boolean(homeResponse?.onboarding?.blocked_by_setup);
    const [threadStateResult, approvalsResult, inboxResult] = await Promise.allSettled([
      loadThreadState(preferredThreadId, { allowEmpty: allowEmptyThread }),
      getAssistantApprovals(settings),
      getAssistantInbox(settings),
    ]);
    if (threadStateResult.status !== "fulfilled") {
      throw threadStateResult.reason;
    }
    const threadState = threadStateResult.value;
    const approvalsResponse = approvalsResult.status === "fulfilled" ? approvalsResult.value : { items: [] as AssistantApproval[] };
    const inboxResponse = inboxResult.status === "fulfilled" ? inboxResult.value : { items: inbox };
    startTransition(() => {
      if (homeResponse) {
        setHome(homeResponse);
      }
      setStreamingAssistantMessage(null);
      setThreadSummaries(threadState.summaries);
      setSelectedThreadId(threadState.selectedId);
      setThreadMessages(threadState.threadResponse?.messages || []);
      setHasMore(!!threadState.threadResponse?.has_more);
      setInbox(inboxResponse.items || []);
      setActiveApprovalStatuses(buildActiveApprovalStatusMap(approvalsResponse.items || []));
    });
    persistSelectedAssistantThreadId(threadState.selectedId);
    return threadState;
  }

  async function loadCalendarToolData() {
    const desktopConfigPromise = window.lawcopilotDesktop?.getIntegrationConfig
      ? window.lawcopilotDesktop.getIntegrationConfig().catch(() => null)
      : Promise.resolve(null);
    const [calendarResponse, desktopConfig] = await Promise.all([
      getAssistantCalendar(settings),
      desktopConfigPromise,
    ]);
    const integrationPayload = (desktopConfig as Record<string, unknown> | null) || null;
    setCalendar(calendarResponse.items);
    setCalendarToday(calendarResponse.today);
    setCalendarGoogleState(resolveDesktopGoogleState(integrationPayload, calendarResponse.google_connected));
    setCalendarOutlookState(resolveDesktopOutlookState(integrationPayload, Boolean(calendarResponse.outlook_connected)));
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
        await loadHomeAndThread(selectedThreadId || undefined);
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

  async function handleManualConnectorSync(connectorName: string) {
    setError("");
    try {
      await runAssistantConnectorSync(settings, {
        connector_names: [connectorName],
        reason: `ui_manual_sync:${connectorName}`,
        trigger: "assistant_home",
      });
      const connectorStatus = await getAssistantConnectorSyncStatus(settings).catch(() => null);
      const refreshedHome = await getAssistantHome(settings);
      startTransition(() => {
        if (connectorStatus && refreshedHome?.connector_sync_status) {
          refreshedHome.connector_sync_status = connectorStatus as AssistantHomeResponse["connector_sync_status"];
        }
        setHome(refreshedHome);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bağlayıcı eşitlemesi başlatılamadı.");
    }
  }

  function defaultNearbyCategoriesForNow() {
    const hour = new Date().getHours();
    if (hour < 11) {
      return ["cafe", "coworking", "transit"];
    }
    if (hour < 16) {
      return ["light_meal", "mosque", "cafe"];
    }
    if (hour < 21) {
      return ["market", "light_meal", "historic_site"];
    }
    return ["transit", "market"];
  }

  async function handleRefreshLocationContext() {
    setError("");
    setIsLocationRefreshing(true);
    const persistLocationStatus = async (statusPatch: {
      provider_status: string;
      permission_state?: string;
      capture_failure_reason?: string;
      privacy_mode?: boolean;
    }) => {
      const observedAt = new Date().toISOString();
      const nearbyCategories = nearbyLocationCandidates
        .map((item) => String(item.category || "").trim())
        .filter(Boolean);
      const nextScope = String(locationContext?.scope || "personal").trim() || "personal";
      const nextSensitivity = String(locationContext?.sensitivity || "high").trim() || "high";
      const payload: {
        current_place?: Record<string, unknown>;
        recent_places: Array<Record<string, unknown>>;
        nearby_categories: string[];
        observed_at: string;
        source: string;
        scope: string;
        sensitivity: string;
        persist_raw: boolean;
        provider: string;
        provider_mode: string;
        provider_status: string;
        capture_mode: string;
        permission_state?: string;
        privacy_mode?: boolean;
        capture_failure_reason?: string;
        source_ref?: string;
      } = {
        recent_places: Array.isArray(locationContext?.recent_places)
          ? locationContext.recent_places.slice(0, 8) as Array<Record<string, unknown>>
          : [],
        nearby_categories: nearbyCategories.length ? nearbyCategories : defaultNearbyCategoriesForNow(),
        observed_at: observedAt,
        source: "browser_geolocation",
        scope: nextScope,
        sensitivity: nextSensitivity,
        persist_raw: false,
        provider: "desktop_browser_capture_v1",
        provider_mode: "desktop_renderer_geolocation",
        provider_status: statusPatch.provider_status,
        capture_mode: "device_capture",
        permission_state: statusPatch.permission_state,
        privacy_mode: statusPatch.privacy_mode,
        capture_failure_reason: statusPatch.capture_failure_reason,
      };
      const snapshotResult = await window.lawcopilotDesktop?.saveLocationSnapshot?.(payload).catch(() => null);
      if (snapshotResult && typeof snapshotResult.snapshotPath === "string" && snapshotResult.snapshotPath.trim()) {
        payload.source_ref = snapshotResult.snapshotPath;
      }
      await updateAssistantLocationContext(settings, payload).catch(() => null);
      const [refreshedHome, orchestration] = await Promise.all([
        getAssistantHome(settings).catch(() => null),
        getAssistantOrchestrationStatus(settings).catch(() => null),
      ]);
      if (refreshedHome) {
        startTransition(() => {
          if (orchestration && refreshedHome?.orchestration_status) {
            refreshedHome.orchestration_status = orchestration as AssistantHomeResponse["orchestration_status"];
          }
          setHome(refreshedHome);
        });
      }
    };
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      const message = "Bu cihazda tarayıcı konum erişimi kullanılamıyor.";
      await persistLocationStatus({
        provider_status: "capture_failed",
        permission_state: "unsupported",
        capture_failure_reason: message,
      });
      setError(message);
      setIsLocationRefreshing(false);
      return;
    }
    try {
      const position = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 12000,
          maximumAge: 300000,
        });
      });
      const observedAt = new Date(position.timestamp || Date.now()).toISOString();
      const currentPlace = locationContext?.current_place && typeof locationContext.current_place === "object"
        ? locationContext.current_place as Record<string, unknown>
        : {};
      const recentPlaces = Array.isArray(locationContext?.recent_places)
        ? locationContext.recent_places.slice(0, 8) as Array<Record<string, unknown>>
        : [];
      const nearbyCategories = nearbyLocationCandidates
        .map((item) => String(item.category || "").trim())
        .filter(Boolean);
      const nextScope = String(locationContext?.scope || "personal").trim() || "personal";
      const nextSensitivity = String(locationContext?.sensitivity || "high").trim() || "high";
      const nextCurrentPlace = {
        ...currentPlace,
        place_id: String(currentPlace.place_id || `device-${position.coords.latitude.toFixed(4)}-${position.coords.longitude.toFixed(4)}`),
        label: String(currentPlace.label || currentPlace.area || "Cihaz konumu"),
        category: String(currentPlace.category || "device_location"),
        area: String(currentPlace.area || ""),
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy_meters: position.coords.accuracy,
        observed_at: observedAt,
        started_at: observedAt,
        scope: nextScope,
        sensitivity: nextSensitivity,
        captured_via: "browser_geolocation",
        tags: Array.from(new Set([...(Array.isArray(currentPlace.tags) ? currentPlace.tags.map((item) => String(item)) : []), "device_capture"])),
      };
      const payload: {
        current_place: Record<string, unknown>;
        recent_places: Array<Record<string, unknown>>;
        nearby_categories: string[];
        observed_at: string;
        source: string;
        scope: string;
        sensitivity: string;
        persist_raw: boolean;
        source_ref?: string;
        provider?: string;
        provider_mode?: string;
        provider_status?: string;
        capture_mode?: string;
        permission_state?: string;
        privacy_mode?: boolean;
      } = {
        current_place: nextCurrentPlace,
        recent_places: recentPlaces,
        nearby_categories: nearbyCategories.length ? nearbyCategories : defaultNearbyCategoriesForNow(),
        observed_at: observedAt,
        source: "browser_geolocation",
        scope: nextScope,
        sensitivity: nextSensitivity,
        persist_raw: true,
        provider: "desktop_browser_capture_v1",
        provider_mode: "desktop_renderer_geolocation",
        provider_status: "fresh",
        capture_mode: "device_capture",
        permission_state: "granted",
        privacy_mode: false,
      };
      const snapshotResult = await window.lawcopilotDesktop?.saveLocationSnapshot?.(payload).catch(() => null);
      if (snapshotResult && typeof snapshotResult.snapshotPath === "string" && snapshotResult.snapshotPath.trim()) {
        payload.source_ref = snapshotResult.snapshotPath;
      }
      await updateAssistantLocationContext(settings, payload);
      await evaluateAssistantTriggers(settings, {
        forced_types: ["location_context"],
        limit: 2,
        persist: true,
        include_suppressed: false,
      }).catch(() => null);
      const [refreshedHome, orchestration] = await Promise.all([
        getAssistantHome(settings),
        getAssistantOrchestrationStatus(settings).catch(() => null),
      ]);
      startTransition(() => {
        if (orchestration && refreshedHome?.orchestration_status) {
          refreshedHome.orchestration_status = orchestration as AssistantHomeResponse["orchestration_status"];
        }
        setHome(refreshedHome);
      });
    } catch (err) {
      const code = Number((err as { code?: number } | null)?.code || 0);
      let providerStatus = "capture_failed";
      let permissionState = "unknown";
      let message = err instanceof Error ? err.message : "Konum bağlamı güncellenemedi.";
      if (code === 1) {
        providerStatus = "permission_denied";
        permissionState = "denied";
        message = "Konum izni reddedildi.";
      } else if (code === 2) {
        permissionState = "unknown";
        message = "Konum şu anda alınamadı.";
      } else if (code === 3) {
        permissionState = "granted";
        message = "Konum alma isteği zaman aşımına uğradı.";
      }
      await persistLocationStatus({
        provider_status: providerStatus,
        permission_state: permissionState,
        capture_failure_reason: message,
      });
      setError(message);
    } finally {
      setIsLocationRefreshing(false);
    }
  }

  async function handleRunManualOrchestration(jobNames?: string[]) {
    setError("");
    setIsOrchestrationRunning(true);
    try {
      await runAssistantOrchestration(settings, {
        job_names: jobNames || [],
        reason: "assistant_home_manual_run",
        force: false,
      });
      await loadHomeAndThread(selectedThreadId || undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Arka plan işleri çalıştırılamadı.");
    } finally {
      setIsOrchestrationRunning(false);
    }
  }

  async function handleCreateCoachingGoal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!coachGoalForm.title.trim()) {
      setError("Koçluk hedefi için başlık girin.");
      return;
    }
    setError("");
    setIsCoachSaving(true);
    try {
      const result = await upsertAssistantCoachingGoal(settings, {
        title: coachGoalForm.title.trim(),
        summary: coachGoalForm.summary.trim() || undefined,
        cadence: coachGoalForm.cadence as "daily" | "weekly" | "flexible" | "one_time",
        target_value: coachGoalForm.targetValue.trim() ? Number(coachGoalForm.targetValue) : undefined,
        unit: coachGoalForm.unit.trim() || undefined,
        reminder_time: coachGoalForm.reminderTime.trim() || undefined,
        target_date: coachGoalForm.targetDate.trim() || undefined,
        allow_desktop_notifications: coachGoalForm.allowDesktopNotifications,
        scope: "personal",
        sensitivity: "high",
        source_refs: ["assistant_home_coach_form"],
      });
      const refreshedHome = (result && typeof result === "object" && "home" in result)
        ? (result as { home?: AssistantHomeResponse }).home
        : await getAssistantHome(settings);
      startTransition(() => {
        if (refreshedHome) {
          setHome(refreshedHome);
        }
        setCoachGoalForm({
          title: "",
          summary: "",
          targetValue: "",
          unit: coachGoalForm.unit || "sayfa",
          cadence: coachGoalForm.cadence || "daily",
          reminderTime: coachGoalForm.reminderTime || "08:00",
          targetDate: "",
          allowDesktopNotifications: coachGoalForm.allowDesktopNotifications,
        });
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Koçluk hedefi kaydedilemedi.");
    } finally {
      setIsCoachSaving(false);
    }
  }

  async function handleLogCoachingProgress(goalId: string, completed = false) {
    const draft = coachProgressDrafts[goalId] || { amount: "", note: "" };
    setError("");
    setIsCoachSaving(true);
    try {
      const result = await logAssistantCoachingProgress(settings, goalId, {
        amount: draft.amount.trim() ? Number(draft.amount) : undefined,
        note: draft.note.trim() || undefined,
        completed,
      });
      const refreshedHome = (result && typeof result === "object" && "home" in result)
        ? (result as { home?: AssistantHomeResponse }).home
        : await getAssistantHome(settings);
      startTransition(() => {
        if (refreshedHome) {
          setHome(refreshedHome);
        }
        setCoachProgressDrafts((current) => ({ ...current, [goalId]: { amount: "", note: "" } }));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "İlerleme kaydı işlenemedi.");
    } finally {
      setIsCoachSaving(false);
    }
  }

  async function handleMemoryCorrectionAction(payload: {
    action: "correct" | "forget" | "change_scope" | "reduce_confidence" | "suppress_recommendation" | "boost_proactivity";
    page_key?: string;
    target_record_id?: string;
    key?: string;
    corrected_summary?: string;
    scope?: string;
    note?: string;
    recommendation_kind?: string;
    topic?: string;
    source_refs?: Array<Record<string, unknown> | string>;
  }) {
    setError("");
    try {
      await applyAssistantMemoryCorrection(settings, payload);
      await loadHomeAndThread(selectedThreadId || undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Memory düzeltmesi uygulanamadı.");
    }
  }

  async function handleKnownMemoryAction(item: {
    id: string;
    title: string;
    summary: string;
    pageKey: string;
    scope?: string;
  }, action: "forget" | "correct" | "change_scope" | "reduce_confidence") {
    if (action === "forget") {
      if (!window.confirm(`"${item.title}" kaydı unutulsun mu?`)) {
        return;
      }
      await handleMemoryCorrectionAction({
        action: "forget",
        page_key: item.pageKey,
        target_record_id: item.id,
        note: `${item.title} kaydı kullanıcı tarafından unutuldu.`,
      });
      return;
    }
    if (action === "change_scope") {
      const nextScope = window.prompt("Yeni scope girin", item.scope || "personal");
      if (!nextScope) {
        return;
      }
      await handleMemoryCorrectionAction({
        action: "change_scope",
        page_key: item.pageKey,
        target_record_id: item.id,
        scope: nextScope,
        note: `${item.title} kaydı için scope düzeltildi.`,
      });
      return;
    }
    if (action === "reduce_confidence") {
      await handleMemoryCorrectionAction({
        action: "reduce_confidence",
        page_key: item.pageKey,
        target_record_id: item.id,
        note: `${item.title} kaydı için güven azaltıldı.`,
        scope: item.scope,
      });
      return;
    }
    const correctedSummary = window.prompt("Doğru hafıza özeti", item.summary || "");
    if (!correctedSummary) {
      return;
    }
    await handleMemoryCorrectionAction({
      action: "correct",
      page_key: item.pageKey,
      target_record_id: item.id,
      corrected_summary: correctedSummary,
      scope: item.scope,
      note: `${item.title} kaydı kullanıcı tarafından düzeltildi.`,
    });
  }

  async function handleRecommendationPreferenceAction(
    item: AssistantHomeSuggestion,
    action: "suppress_recommendation" | "boost_proactivity",
  ) {
    const topic = String(item.kind || item.title || "").trim();
    if (!topic) {
      return;
    }
    await handleMemoryCorrectionAction({
      action,
      recommendation_kind: topic,
      topic,
      scope: "personal",
      note: action === "suppress_recommendation"
        ? `${topic} önerileri kullanıcı tarafından baskılandı.`
        : `${topic} konusunda daha proaktif olunması istendi.`,
      source_refs: [{ type: "home_suggestion", id: item.id, kind: item.kind }],
    });
  }

  async function loadOlderMessages() {
    if (isLoadingMore || !hasMore || threadMessages.length === 0 || !selectedThreadId) return;
    setIsLoadingMore(true);

    const container = messagesContainerRef.current;
    const previousScrollHeight = container?.scrollHeight || 0;

    try {
      const firstId = threadMessages[0].id;
      const response = await getAssistantThread(settings, { limit: PAGE_SIZE, before_id: firstId, thread_id: selectedThreadId });
      if (response.messages.length > 0) {
        setThreadMessages((prev) => mergeAssistantMessages(response.messages, prev));
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
      setMatterDrafts(response.matter_drafts);
    }
  }

  async function refreshAssistantSurface() {
    await loadHomeAndThread(selectedThreadId || undefined);
    if (selectedTool) {
      await loadToolData(selectedTool);
    }
  }

  const loadStarredMessages = useCallback(async () => {
    const response = await listAssistantStarredMessages(settings, { limit: 200 });
    setStarredMessages(response.items || []);
  }, [settings]);

  const scrollToThreadMessage = useCallback((messageId: number) => {
    const node = messageNodeMapRef.current[messageId];
    if (!node) {
      return false;
    }
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightedMessageId(messageId);
    if (highlightedMessageTimerRef.current !== null) {
      window.clearTimeout(highlightedMessageTimerRef.current);
    }
    highlightedMessageTimerRef.current = window.setTimeout(() => {
      setHighlightedMessageId((current) => (current === messageId ? null : current));
    }, STARRED_MESSAGE_HIGHLIGHT_TIMEOUT_MS);
    return true;
  }, []);

  const ensureThreadMessageLoaded = useCallback(async (messageId: number) => {
    const threadId = selectedThreadIdRef.current;
    if (!threadId) {
      return false;
    }
    if (threadMessagesRef.current.some((item) => item.id === messageId)) {
      return true;
    }
    let beforeId = threadMessagesRef.current[0]?.id;
    let nextHasMore = hasMoreRef.current;
    if (!beforeId || !nextHasMore) {
      return false;
    }
    setIsLoadingMore(true);
    try {
      while (beforeId && nextHasMore && !threadMessagesRef.current.some((item) => item.id === messageId)) {
        const response = await getAssistantThread(settings, { limit: PAGE_SIZE, before_id: beforeId, thread_id: threadId });
        if (!response.messages.length) {
          nextHasMore = false;
          hasMoreRef.current = false;
          setHasMore(false);
          break;
        }
        const merged = mergeAssistantMessages(response.messages, threadMessagesRef.current);
        threadMessagesRef.current = merged;
        setThreadMessages(merged);
        nextHasMore = !!response.has_more;
        hasMoreRef.current = nextHasMore;
        setHasMore(nextHasMore);
        beforeId = response.messages[0]?.id;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : text.queryError);
      return false;
    } finally {
      setIsLoadingMore(false);
    }
    return threadMessagesRef.current.some((item) => item.id === messageId);
  }, [settings, text.queryError]);

  const handleToggleMessageStar = useCallback(async (message: ThreadDisplayMessage) => {
    if (typeof message.id !== "number" || Number(message.thread_id || 0) <= 0) {
      return;
    }
    const nextStarred = !message.starred;
    const previousStarredAt = message.starred_at || null;
    const optimisticStarredAt = nextStarred ? new Date().toISOString() : null;
    setStarBusyMessageId(message.id);
    setThreadMessages((prev) => prev.map((item) => (
      item.id === message.id
        ? { ...item, starred: nextStarred, starred_at: optimisticStarredAt }
        : item
    )));
    try {
      const response = await updateAssistantThreadMessageStar(settings, message.id, { starred: nextStarred });
      const updated = response.message;
      setThreadMessages((prev) => prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)));
      if (isStarredMessagesOpen) {
        await loadStarredMessages();
      }
      setError("");
    } catch (err) {
      setThreadMessages((prev) => prev.map((item) => (
        item.id === message.id
          ? { ...item, starred: !nextStarred, starred_at: previousStarredAt }
          : item
      )));
      setError(err instanceof Error ? err.message : "Mesaj yıldızlanamadı.");
    } finally {
      setStarBusyMessageId(null);
    }
  }, [isStarredMessagesOpen, loadStarredMessages, settings]);

  const handleOpenStarredMessage = useCallback(async (message: AssistantThreadMessage) => {
    const targetThreadId = Number(message.thread_id || 0);
    if (!targetThreadId) {
      setError("Yıldızlı mesajın sohbeti bulunamadı.");
      return;
    }
    if (targetThreadId !== selectedThreadIdRef.current) {
      const threadState = await loadHomeAndThread(targetThreadId, { refreshHome: false });
      selectedThreadIdRef.current = threadState.selectedId;
      threadMessagesRef.current = threadState.threadResponse?.messages || [];
      hasMoreRef.current = !!threadState.threadResponse?.has_more;
      startTransition(() => {
        setThreadSummaries(threadState.summaries);
        setSelectedThreadId(threadState.selectedId);
        setThreadMessages(threadState.threadResponse?.messages || []);
        setHasMore(!!threadState.threadResponse?.has_more);
      });
    }
    const found = await ensureThreadMessageLoaded(message.id);
    if (!found) {
      setError("Yıldızlı mesaj bulunamadı.");
      return;
    }
    setSidebarSection("threads");
    setIsSidebarExpanded(true);
    window.requestAnimationFrame(() => {
      let attempts = 0;
      const tryScroll = () => {
        if (scrollToThreadMessage(message.id)) {
          return;
        }
        if (attempts >= 8) {
          return;
        }
        attempts += 1;
        window.setTimeout(tryScroll, 80);
      };
      tryScroll();
    });
  }, [ensureThreadMessageLoaded, loadHomeAndThread, scrollToThreadMessage]);

  const shareTargetOptions = useMemo(
    () => assistantShareTargetOptions(shareProfiles, shareChannel, shareRecipientQuery),
    [shareChannel, shareProfiles, shareRecipientQuery],
  );

  const loadShareProfiles = useCallback(async () => {
    if (shareProfilesLoading || shareProfiles.length > 0) {
      return;
    }
    setShareProfilesLoading(true);
    try {
      const response = await getAssistantContactProfiles(settings);
      setShareProfiles(response.items || []);
    } catch (err) {
      setShareDialogError(err instanceof Error ? err.message : "Paylaşım kişileri yüklenemedi.");
    } finally {
      setShareProfilesLoading(false);
    }
  }, [settings, shareProfiles.length, shareProfilesLoading]);

  const handleOpenShareDialog = useCallback((message: ThreadDisplayMessage) => {
    setShareDialogMessage(message);
    setShareChannel("whatsapp");
    setShareRecipientQuery("");
    setShareRecipient("");
    setShareSelectedProfileId("");
    setShareDraftSubject(assistantShareDefaultSubject(message.content));
    setShareDraftBody(String(message.content || ""));
    setShareDialogError("");
    void loadShareProfiles();
  }, [loadShareProfiles]);

  const handleCloseShareDialog = useCallback(() => {
    if (shareDialogBusy) {
      return;
    }
    setShareDialogMessage(null);
    setShareRecipientQuery("");
    setShareRecipient("");
    setShareSelectedProfileId("");
    setShareDraftSubject("");
    setShareDraftBody("");
    setShareDialogError("");
  }, [shareDialogBusy]);

  useEffect(() => {
    if (!shareDialogMessage) {
      return;
    }
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && !shareDialogBusy) {
        handleCloseShareDialog();
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [handleCloseShareDialog, shareDialogBusy, shareDialogMessage]);

  const handleShareChannelChange = useCallback((channel: AssistantShareChannel) => {
    setShareChannel(channel);
    setShareRecipientQuery("");
    setShareRecipient("");
    setShareSelectedProfileId("");
    setShareDialogError("");
  }, []);

  const handleSelectShareTarget = useCallback((item: AssistantShareTargetOption) => {
    setShareSelectedProfileId(item.profileId);
    setShareRecipient(item.value);
    setShareRecipientQuery(item.label);
    setShareDialogError("");
  }, []);

  const handleCreateShareDraft = useCallback(async () => {
    if (!shareDialogMessage) {
      return;
    }
    const nextBody = shareDraftBody.trim();
    const nextRecipient = shareRecipient.trim();
    const nextSubject = shareDraftSubject.trim();
    if (!nextBody) {
      setShareDialogError("Paylaşılacak içerik boş bırakılamaz.");
      return;
    }
    if (assistantShareNeedsRecipient(shareChannel) && !nextRecipient) {
      setShareDialogError("Bu kanal için kişi, grup veya alıcı seçin.");
      return;
    }
    if (shareChannel === "email" && !nextSubject) {
      setShareDialogError("E-posta için konu girin.");
      return;
    }
    setShareDialogBusy(true);
    try {
      const response = await createAssistantShareDraft(settings, {
        channel: shareChannel,
        content: nextBody,
        to_contact: assistantShareNeedsRecipient(shareChannel) ? nextRecipient : undefined,
        subject: shareChannel === "email" ? nextSubject : undefined,
        thread_id: Number(shareDialogMessage.thread_id || 0) > 0 ? Number(shareDialogMessage.thread_id) : undefined,
        message_id: typeof shareDialogMessage.id === "number" ? shareDialogMessage.id : undefined,
        contact_profile_id: shareSelectedProfileId || undefined,
      });
      const createdDraft = response.draft;
      setDrafts((current) => mergeDraftIntoList(current, createdDraft));
      try {
        const dispatchResult = await prepareAssistantDraftForDispatch(
          createdDraft,
          "Mesaj paylaşım panelinden hazırlandı.",
          { allowPendingBridge: true },
        );
        await refreshAssistantSurface().catch(() => null);
        handleCloseShareDialog();
        if (dispatchResult.pendingDesktopBridge) {
          openTool("drafts");
        }
        setError("");
      } catch (dispatchError) {
        handleCloseShareDialog();
        openTool("drafts");
        setError(
          dispatchError instanceof Error
            ? `${dispatchError.message} Paylaşım taslağını Taslaklar alanına bıraktım.`
            : "Paylaşım taslağı oluşturuldu. Son adımı Taslaklar alanından tamamlayın.",
        );
      }
    } catch (err) {
      setShareDialogError(err instanceof Error ? err.message : "Paylaşım taslağı oluşturulamadı.");
    } finally {
      setShareDialogBusy(false);
    }
  }, [
    handleCloseShareDialog,
    settings,
    shareChannel,
    shareDialogMessage,
    shareDraftBody,
    shareDraftSubject,
    shareRecipient,
    shareSelectedProfileId,
  ]);

  const handleCopyThreadMessage = useCallback(async (message: ThreadDisplayMessage) => {
    const ok = await copyTextToClipboard(message.content);
    if (!ok) {
      setError(message.role === "assistant" ? "Yanıt kopyalanamadı." : "Mesaj kopyalanamadı.");
      return;
    }
    setError("");
  }, []);

  const handleEditThreadMessage = useCallback((message: ThreadDisplayMessage) => {
    const nextValue = String(message.content || "");
    setEditingMessageId(typeof message.id === "number" ? message.id : null);
    setEditingMessageDraft(nextValue);
  }, []);

  const handleCancelThreadEdit = useCallback(() => {
    setEditingMessageId(null);
    setEditingMessageDraft("");
    setError("");
  }, []);

  const handleSubmitEditedThreadMessage = useCallback((message: ThreadDisplayMessage) => {
    const nextValue = editingMessageDraft.trim();
    if (!nextValue) {
      setError("Mesaj boş bırakılamaz.");
      return;
    }
    if (nextValue === String(message.content || "").trim()) {
      handleCancelThreadEdit();
      return;
    }
    void handleSubmit(nextValue, { editMessage: message });
  }, [editingMessageDraft, handleCancelThreadEdit, handleSubmit]);

  const persistAssistantMessageFeedback = useCallback(async (
    message: ThreadDisplayMessage,
    value: AssistantMessageFeedbackValue,
    options: { note?: string; preserveSelection?: boolean } = {},
  ) => {
    if (typeof message.id !== "number") {
      return;
    }
    const previousValue = feedbackValueFromMessage(message);
    const nextValue = options.preserveSelection ? value : (previousValue === value ? null : value);
    const optimisticFeedbackAt = nextValue ? new Date().toISOString() : null;
    const nextNote = nextValue ? (options.note !== undefined ? (options.note.trim() || null) : message.feedback_note || null) : null;
    setThreadMessages((prev) => prev.map((item) => (
      item.id === message.id
        ? { ...item, feedback_value: nextValue, feedback_at: optimisticFeedbackAt, feedback_note: nextNote }
        : item
    )));

    try {
      const response = await updateAssistantThreadMessageFeedback(settings, message.id, {
        feedback_value: nextValue ?? "none",
        note: nextNote || undefined,
      });
      const updated = response.message;
      setThreadMessages((prev) => prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)));
      setError("");
    } catch (err) {
      setThreadMessages((prev) => prev.map((item) => (
        item.id === message.id
          ? { ...item, feedback_value: previousValue, feedback_at: message.feedback_at || null, feedback_note: message.feedback_note || null }
          : item
      )));
      setError(err instanceof Error ? err.message : "Yanıt geri bildirimi kaydedilemedi.");
    }
  }, [settings]);

  const handleAssistantMessageFeedback = useCallback((message: ThreadDisplayMessage, value: AssistantMessageFeedbackValue) => (
    persistAssistantMessageFeedback(message, value)
  ), [persistAssistantMessageFeedback]);

  const handleAssistantMessageFeedbackNote = useCallback((message: ThreadDisplayMessage, value: AssistantMessageFeedbackValue, note: string) => (
    persistAssistantMessageFeedback(message, value, { note, preserveSelection: true })
  ), [persistAssistantMessageFeedback]);

  async function loadAgentToolCatalog() {
    if (agentToolCatalog.length > 0) {
      return agentToolCatalog;
    }
    try {
      const response = await getAgentTools(settings);
      setAgentToolCatalog(response.items || []);
      return response.items || [];
    } catch {
      return [];
    }
  }

  async function syncAgentRunState(runId: number | string, sequence: number, includeEvents = false) {
    try {
      const [runResponse, eventsResponse] = await Promise.all([
        getAgentRun(settings, runId),
        includeEvents ? getAgentRunEvents(settings, runId) : Promise.resolve<{ items: AgentRunEvent[] }>({ items: [] }),
      ]);
      if (sequence !== agentRunSequenceRef.current) {
        return null;
      }
      setLatestAgentRun(runResponse);
      if (includeEvents) {
        setLatestAgentRunEvents(eventsResponse.items || []);
      }
      return runResponse;
    } catch {
      return null;
    }
  }

  async function startAgentRunTracking(runId: number | string) {
    const sequence = ++agentRunSequenceRef.current;
    await loadAgentToolCatalog();
    const firstRun = await syncAgentRunState(runId, sequence, true);
    if (!firstRun) {
      return;
    }
    let currentStatus = String(firstRun.status || firstRun.result_status || "").trim();
    for (let attempt = 0; attempt < 8 && !isAgentRunTerminal(currentStatus); attempt += 1) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, 1200));
      const nextRun = await syncAgentRunState(runId, sequence, attempt === 7 || attempt % 2 === 1);
      if (!nextRun) {
        return;
      }
      currentStatus = String(nextRun.status || nextRun.result_status || "").trim();
    }
  }

  /* ── Effects ────────────────────────────────────────────── */

  useEffect(() => {
    if (!rawSelectedTool || selectedTool) {
      return;
    }
    const params = new URLSearchParams(searchParams);
    params.delete("tool");
    setSearchParams(params, { replace: true });
  }, [rawSelectedTool, searchParams, selectedTool, setSearchParams]);

  useEffect(() => {
    setIsLoading(true);
    isFirstLoad.current = true;
    googleAutoSyncRef.current = { started: false, completed: false };
    setHandledApprovalIds({});
    agentRunSequenceRef.current += 1;
    setLatestAgentRun(null);
    setLatestAgentRunEvents([]);
    setAgentToolCatalog([]);

    loadHomeAndThread(selectedThreadId || undefined)
      .then(() => {
        // UI blokesini hemen kaldır (yerel veri yüklendi)
        setIsLoading(false);
        setError("");

        // Arka plan görevleri (Google Sync vb.) asenkron devam eder
        void loadGoogleStatusData()
          .then((status) => {
            if (!googleAutoSyncRef.current.started && window.lawcopilotDesktop?.syncGoogleData && shouldAutoSyncGoogle(status)) {
              googleAutoSyncRef.current.started = true;
              void syncGoogleMirror({
                refreshHome: true,
                refreshToday: selectedTool === "today",
                refreshCalendar: selectedTool === "calendar",
                refreshDocuments: selectedTool === "documents",
                silent: true,
              }).then(() => {
                googleAutoSyncRef.current.completed = true;
              }).catch(() => { /* sessizce yut */ });
            }
          })
          .catch(() => null);
      })
      .catch((err: Error) => {
        setError(err.message);
        setIsLoading(false);
      });
  }, [settings.baseUrl, settings.token]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }
    const handleMemoryUpdate = (event: Event) => {
      const detail = event instanceof CustomEvent ? event.detail as { kinds?: string[] } | undefined : undefined;
      const kinds = new Set((detail?.kinds || []).map((item) => String(item || "").trim()));
      if (!kinds.has("profile_signal")) {
        return;
      }
      void loadHomeAndThread(selectedThreadId || undefined).catch(() => null);
    };
    window.addEventListener(SETTINGS_MEMORY_UPDATE_EVENT, handleMemoryUpdate as EventListener);
    return () => {
      window.removeEventListener(SETTINGS_MEMORY_UPDATE_EVENT, handleMemoryUpdate as EventListener);
    };
  }, [loadHomeAndThread, selectedThreadId]);

  useEffect(() => {
    if (!window.lawcopilotDesktop?.onAutomationEvent) {
      return undefined;
    }
    const dispose = window.lawcopilotDesktop.onAutomationEvent((payload) => {
      const kind = String(payload?.kind || "").trim();
      if (kind !== "reminder_fired") {
        return;
      }
      void refreshAssistantSurface().catch(() => null);
    });
    return typeof dispose === "function" ? dispose : undefined;
  }, [refreshAssistantSurface]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      if (document.hidden || isSubmitting || isResponding || isLoadingMore || Boolean(streamingAssistantMessage)) {
        return;
      }
      void refreshAssistantSurface().catch(() => null);
    }, ASSISTANT_LIVE_REFRESH_INTERVAL_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [
    isLoadingMore,
    isResponding,
    isSubmitting,
    selectedThreadId,
    selectedTool,
    settings.baseUrl,
    settings.token,
    streamingAssistantMessage,
  ]);

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
  }, [hasMore, isLoadingMore]);

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

  useEffect(() => {
    if (!window.speechSynthesis?.getVoices) {
      setAvailableVoices([]);
    } else {
      const loadVoices = () => {
        const nextVoices = window.speechSynthesis?.getVoices?.() || [];
        setAvailableVoices(nextVoices);
      };

      loadVoices();

      const synth = window.speechSynthesis;
      synth.addEventListener?.("voiceschanged", loadVoices);
      return () => synth.removeEventListener?.("voiceschanged", loadVoices);
    }
  }, []);

  useEffect(() => {
    if (!window.lawcopilotDesktop?.getDesktopTtsVoices) {
      return;
    }
    let cancelled = false;
    window.lawcopilotDesktop.getDesktopTtsVoices()
      .then((voices) => {
        if (cancelled || !Array.isArray(voices)) {
          return;
        }
        const normalized = voices
          .map((voice) => ({
            id: String(voice?.id || "").trim(),
            name: String(voice?.name || "").trim(),
            lang: String(voice?.lang || "").trim(),
          }))
          .filter((voice) => voice.id && voice.name);
        setDesktopVoices(normalized);
      })
      .catch(() => null);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => () => {
    revokeAttachmentPreviews(attachmentStoreRef.current);
    revokeAttachmentPreviews(submittedAttachmentsRef.current);
    if (speechRecognitionRef.current) {
      speechRecognitionRef.current.stop();
    }
    if (speechPreviewRecognitionRef.current) {
      speechPreviewRecognitionRef.current.stop();
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      discardRecordedAudioRef.current = true;
      mediaRecorderRef.current.stop();
    }
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    if (audioMeterFrameRef.current !== null) {
      window.cancelAnimationFrame(audioMeterFrameRef.current);
      audioMeterFrameRef.current = null;
    }
    audioAnalyserRef.current = null;
    audioContextRef.current?.close().catch(() => null);
    audioContextRef.current = null;
    if (interruptMeterFrameRef.current !== null) {
      window.cancelAnimationFrame(interruptMeterFrameRef.current);
      interruptMeterFrameRef.current = null;
    }
    interruptAnalyserRef.current = null;
    interruptAudioContextRef.current?.close().catch(() => null);
    interruptAudioContextRef.current = null;
    interruptStreamRef.current?.getTracks().forEach((track) => track.stop());
    interruptStreamRef.current = null;
    interruptSpeechSinceRef.current = null;
    voiceDetectedSpeechRef.current = false;
    if (pendingStreamScrollFrameRef.current !== null) {
      window.cancelAnimationFrame(pendingStreamScrollFrameRef.current);
      pendingStreamScrollFrameRef.current = null;
    }
    resumeListeningAfterSpeechRef.current = false;
    window.speechSynthesis?.cancel();
    void window.lawcopilotDesktop?.stopSpeaking?.().catch(() => null);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(DRAWER_WIDTH_STORAGE_KEY, String(drawerWidth));
  }, [drawerWidth]);

  useEffect(() => {
    window.localStorage.setItem(VOICE_PREFERENCE_STORAGE_KEY, selectedVoiceId || AUTO_VOICE_PREFERENCE);
  }, [selectedVoiceId]);

  useEffect(() => {
    window.localStorage.setItem(VOICE_PLAYBACK_PREFERENCE_STORAGE_KEY, isVoicePlaybackEnabled ? "true" : "false");
  }, [isVoicePlaybackEnabled]);

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
      const basePrompts = [
        text.quickPromptToday,
        text.quickPromptMissing,
        text.quickPromptClientUpdate,
        text.quickPromptCalendar,
        text.quickPromptSimilarity,
        text.quickPromptWebSearch,
        text.quickPromptTravel,
      ];
      const shouldPrioritizeConnections = threadMessages.length === 0
        && (!home?.connected_accounts?.length || Boolean(home?.onboarding && !home.onboarding.complete));
      const prompts = shouldPrioritizeConnections
        ? [
            text.quickPromptConnectGoogle,
            text.quickPromptConnectSlack,
            text.quickPromptConnectApi,
            text.quickPromptToday,
            text.quickPromptCalendar,
          ]
        : basePrompts;
      return prompts.filter((item, index, source) => source.indexOf(item) === index);
    },
    [home?.connected_accounts?.length, home?.onboarding, text, threadMessages.length],
  );
  const attachmentHint = settings.currentMatterId ? text.chatAttachmentHintBound : text.chatAttachmentHintLoose;
  const canSubmit = Boolean(prompt.trim() || attachments.length);
  const selectedSpeechVoice = useMemo(
    () => resolveSpeechVoice(availableVoices, selectedVoiceId),
    [availableVoices, selectedVoiceId],
  );
  const hasStreamingAssistantContent = Boolean(streamingAssistantMessage?.content?.trim());
  const displayedMessages = useMemo(() => {
    const items: ThreadDisplayMessage[] = threadMessages.map((message) => enrichThreadMessageAttachmentPreviews(message, attachmentPreviewIndex));
    if (streamingAssistantMessage && streamingAssistantMessage.content.trim()) {
      items.push(streamingAssistantMessage);
    }
    return items;
  }, [attachmentPreviewIndex, streamingAssistantMessage, threadMessages]);
  const proactiveSuggestions = home?.proactive_suggestions || [];
  const connectorSyncItems = useMemo(
    () => (home?.connector_sync_status?.items || []).slice().sort((left, right) => {
      const leftConnected = (left.providers || []).some((item) => item.connected);
      const rightConnected = (right.providers || []).some((item) => item.connected);
      return Number(rightConnected) - Number(leftConnected);
    }),
    [home?.connector_sync_status?.items],
  );
  const locationContext = home?.location_context || null;
  const locationExplainability = locationContext?.location_explainability && typeof locationContext.location_explainability === "object"
    ? locationContext.location_explainability as Record<string, unknown>
    : null;
  const canCaptureBrowserLocation = typeof navigator !== "undefined" && Boolean(navigator.geolocation);
  const nearbyLocationCandidates = useMemo(
    () => Array.isArray(locationContext?.nearby_candidates) ? locationContext.nearby_candidates as Array<Record<string, unknown>> : [],
    [locationContext],
  );
  const locationPrimaryMapUrl = useMemo(() => {
    const directHandoff = locationContext?.navigation_handoff && typeof locationContext.navigation_handoff === "object"
      ? String((locationContext.navigation_handoff as Record<string, unknown>).maps_url || "").trim()
      : "";
    if (directHandoff) {
      return directHandoff;
    }
    const nearbyUrl = nearbyLocationCandidates
      .map((item) => (
        item?.navigation_prep && typeof item.navigation_prep === "object"
          ? String((item.navigation_prep as Record<string, unknown>).maps_url || "").trim()
          : ""
      ))
      .find(Boolean);
    return nearbyUrl || "";
  }, [locationContext?.navigation_handoff, nearbyLocationCandidates]);
  const decisionTimeline = home?.decision_timeline || [];
  const memoryOverview = home?.memory_overview || null;
  const knowledgeHealthSummary = home?.knowledge_health_summary || null;
  const assistantCore = home?.assistant_core || null;
  const coachingDashboard = home?.coaching_dashboard || null;
  const activeAssistantForms = useMemo(
    () => Array.isArray(assistantCore?.active_forms) ? assistantCore.active_forms as Array<Record<string, unknown>> : [],
    [assistantCore],
  );
  const availableAssistantForms = useMemo(
    () => Array.isArray(assistantCore?.available_forms) ? assistantCore.available_forms as Array<Record<string, unknown>> : [],
    [assistantCore],
  );
  const assistantCoreEvolution = useMemo(
    () => Array.isArray(assistantCore?.evolution_history) ? assistantCore.evolution_history as Array<Record<string, unknown>> : [],
    [assistantCore],
  );
  const assistantCoreCapabilityContracts = useMemo(
    () => Array.isArray(assistantCore?.capability_contracts) ? assistantCore.capability_contracts as Array<Record<string, unknown>> : [],
    [assistantCore],
  );
  const assistantCoreSurfaceContracts = useMemo(
    () => Array.isArray(assistantCore?.surface_contracts) ? assistantCore.surface_contracts as Array<Record<string, unknown>> : [],
    [assistantCore],
  );
  const assistantCoreSetupActions = useMemo(
    () => Array.isArray(assistantCore?.suggested_setup_actions) ? assistantCore.suggested_setup_actions as Array<Record<string, unknown>> : [],
    [assistantCore],
  );
  const coachingGoals = useMemo<Array<Record<string, unknown>>>(
    () => Array.isArray(coachingDashboard?.active_goals) ? coachingDashboard.active_goals as Array<Record<string, unknown>> : [],
    [coachingDashboard],
  );
  const coachingDueCheckins = useMemo(
    () => Array.isArray(coachingDashboard?.due_checkins) ? coachingDashboard.due_checkins as Array<Record<string, unknown>> : [],
    [coachingDashboard],
  );
  const coachingInsights = useMemo(
    () => Array.isArray(coachingDashboard?.insights) ? coachingDashboard.insights : [],
    [coachingDashboard],
  );
  const coachingNotifications = useMemo(
    () => Array.isArray(coachingDashboard?.notification_candidates) ? coachingDashboard.notification_candidates as Array<Record<string, unknown>> : [],
    [coachingDashboard],
  );
  const recentCorrections = useMemo(
    () => Array.isArray(memoryOverview?.recent_corrections) ? memoryOverview.recent_corrections as Array<Record<string, unknown>> : [],
    [memoryOverview],
  );
  const learnedTopics = useMemo(
    () => Array.isArray(memoryOverview?.learned_topics) ? memoryOverview.learned_topics as Array<Record<string, unknown>> : [],
    [memoryOverview],
  );
  const recommendationHistorySummary = home?.recommendation_history_summary || [];
  const proactiveControlState = home?.proactive_control_state || null;
  const orchestrationStatus = home?.orchestration_status || null;
  const reflectionStatus = home?.reflection_status || null;
  const autonomyStatus = home?.autonomy_status || null;
  const orchestrationJobs = useMemo(
    () => Array.isArray(orchestrationStatus?.jobs) ? orchestrationStatus.jobs as Array<Record<string, unknown>> : [],
    [orchestrationStatus],
  );
  const autonomyMattersNow = useMemo(
    () => Array.isArray(autonomyStatus?.matters_now) ? autonomyStatus.matters_now as Array<Record<string, unknown>> : [],
    [autonomyStatus],
  );
  const assistantActivityFeed = useMemo(() => {
    const items: Array<{ id: string; title: string; summary?: string; tone?: "accent" | "warning" | "neutral" | "danger" }> = [];
    decisionTimeline.forEach((item, index) => {
      items.push({
        id: `decision-${String(item.id || index)}`,
        title: String(item.title || item.kind || "Karar kaydı"),
        summary: String(item.summary || item.why || item.risk_level || ""),
        tone: "neutral",
      });
    });
    assistantCoreEvolution.forEach((item, index) => {
      items.push({
        id: `evolution-${String(item.id || index)}`,
        title: String(item.title || item.summary || "Asistan evrimi"),
        summary: String(item.summary || ""),
        tone: "accent",
      });
    });
    (Array.isArray(reflectionStatus?.recommended_kb_actions) ? reflectionStatus.recommended_kb_actions : []).forEach((item, index) => {
      items.push({
        id: `reflection-action-${index}`,
        title: String(item.action || item.title || "KB aksiyonu"),
        summary: String(item.reason || item.summary || ""),
        tone: statusTone(String(item.priority || reflectionStatus?.health_status || "")),
      });
    });
    orchestrationJobs.forEach((item, index) => {
      items.push({
        id: `job-${String(item.job || index)}`,
        title: String(item.job || item.title || "Arka plan işi"),
        summary: String(item.status_message || item.last_error || ""),
        tone: statusTone(String(item.status || "")),
      });
    });
    const deduped = new Map<string, { id: string; title: string; summary?: string; tone?: "accent" | "warning" | "neutral" | "danger" }>();
    items.forEach((item) => {
      const key = `${item.title.toLocaleLowerCase("tr-TR")}:${String(item.summary || "").toLocaleLowerCase("tr-TR")}`;
      if (!deduped.has(key)) {
        deduped.set(key, item);
      }
    });
    return Array.from(deduped.values()).slice(0, 5);
  }, [assistantCoreEvolution, decisionTimeline, orchestrationJobs, reflectionStatus?.health_status, reflectionStatus?.recommended_kb_actions]);
  const visibleThreadSummaries = useMemo(() => {
    const query = threadSearch.trim().toLocaleLowerCase("tr-TR");
    if (!query) {
      return threadSummaries;
    }
    return threadSummaries.filter((item) => {
      const haystacks = [
        String(item.title || ""),
        String(item.last_message_preview || ""),
      ].map((value) => value.toLocaleLowerCase("tr-TR"));
      return haystacks.some((value) => value.includes(query));
    });
  }, [threadSearch, threadSummaries]);
  const openThreadMenuItem = useMemo(
    () => threadSummaries.find((item) => item.id === threadMenuOpenId) || null,
    [threadMenuOpenId, threadSummaries],
  );
  const visibleStarredMessages = useMemo(() => {
    const query = starredSearch.trim().toLocaleLowerCase("tr-TR");
    if (!query) {
      return starredMessages;
    }
    return starredMessages.filter((item) => {
      const haystacks = [
        String(item.content || ""),
        String(item.thread_title || ""),
      ].map((value) => value.toLocaleLowerCase("tr-TR"));
      return haystacks.some((value) => value.includes(query));
    });
  }, [starredMessages, starredSearch]);
  const latestAssistantThreadMessage = useMemo(
    () => [...threadMessages].reverse().find((item) => item.role === "assistant") || null,
    [threadMessages],
  );
  const isOnboardingMode = Boolean(home?.onboarding && !home.onboarding.complete);
  const quickPromptsTitle = threadMessages.length === 0
    && (!home?.connected_accounts?.length || isOnboardingMode)
    ? text.connectionQuickPromptsTitle
    : text.quickPromptsTitle;
  const quickPromptsSubtitle = threadMessages.length === 0
    && (!home?.connected_accounts?.length || isOnboardingMode)
    ? text.connectionQuickPromptsSubtitle
    : text.quickPromptsSubtitle;
  const welcomeQuickPrompts = useMemo(() => {
    if (threadMessages.length === 0 && home?.onboarding?.blocked_by_setup) {
      const starterPrompts = Array.isArray(home.onboarding.starter_prompts)
        ? home.onboarding.starter_prompts
          .map((item) => String(item || "").trim())
          .filter(Boolean)
        : [];
      return starterPrompts.slice(0, 4);
    }
    return threadMessages.length === 0 ? quickPrompts.slice(0, 4) : quickPrompts;
  }, [home?.onboarding?.blocked_by_setup, home?.onboarding?.starter_prompts, quickPrompts, threadMessages.length]);
  const visibleProactiveSuggestions = useMemo(
    () => proactiveSuggestions.filter((item) => !dismissedProactiveIds.includes(String(item.id || "").trim())),
    [dismissedProactiveIds, proactiveSuggestions],
  );
  const showSessionBrief = Boolean(threadMessages.length > 0 && home && !isSessionBriefDismissed && !isOnboardingMode);
  const sessionBriefSuggestions = visibleProactiveSuggestions.slice(0, 2);
  const homeSummaryText = useMemo(
    () => buildHomeSummaryText(home, text.threadEmptyDescription),
    [home, text.threadEmptyDescription],
  );
  const googleAssistantAccessReady = Boolean(
    googleStatus?.configured
      && (
        googleStatus.gmail_connected
        || googleStatus.calendar_connected
        || googleStatus.drive_connected
        || googleStatus.youtube_connected
      ),
  );
  const googleAssistantAccessSummary = useMemo(() => {
    if (!googleStatus?.configured) {
      return "";
    }
    if (googleAssistantAccessReady) {
      return "Gmail, Takvim, Drive ve YouTube oynatma listesi verileri asistanın kullanımına açık. Sorularınızda bu kaynaklara da bakabilirim.";
    }
    return "Google hesabı bağlandı. İlk eşitleme tamamlandığında Gmail, Takvim, Drive ve YouTube playlist bilgileri burada görünür.";
  }, [googleAssistantAccessReady, googleStatus?.configured]);
  const welcomeSetupItems = useMemo(() => {
    const pendingOnboardingSteps: Array<{ id: string; title: string; details: string; action: string; route: string }> = Array.isArray(home?.onboarding?.steps)
      ? home.onboarding.steps
        .filter((item) => !item.complete)
        .slice(0, 3)
        .map((item) => ({
          id: String(item.id || item.title || "step"),
          title: String(item.title || "Kurulum adımı"),
          details: String(item.description || ""),
          action: String(item.action || "open_settings"),
          route: setupLinkForItem({
            id: String(item.id || item.title || "step"),
            action: String(item.action || "open_settings"),
            route: typeof (item as Record<string, unknown>).route === "string" ? String((item as Record<string, unknown>).route || "") : "",
          }),
        }))
      : [];
    const filteredPendingOnboardingSteps = home?.onboarding?.blocked_by_setup
      ? pendingOnboardingSteps.filter((item) => ["setup-provider", "setup-provider-model"].includes(item.id))
      : pendingOnboardingSteps;
    if (filteredPendingOnboardingSteps.length > 0) {
      return filteredPendingOnboardingSteps;
    }
    const mappedRequiresSetup: Array<{ id: string; title: string; details: string; action: string; route: string }> = (home?.requires_setup || []).slice(0, 3).map((item) => ({
      id: String(item.id || item.title || "setup"),
      title: String(item.title || "Kurulum"),
      details: String(item.details || ""),
      action: String(item.action || "open_settings"),
      route: setupLinkForItem({
        id: String(item.id || item.title || "setup"),
        action: String(item.action || "open_settings"),
        route: typeof (item as Record<string, unknown>).route === "string" ? String((item as Record<string, unknown>).route || "") : "",
      }),
    }));
    if (home?.onboarding?.blocked_by_setup) {
      return mappedRequiresSetup.filter((item) => ["setup-provider", "setup-provider-model"].includes(item.id));
    }
    return mappedRequiresSetup;
  }, [home?.onboarding?.blocked_by_setup, home?.onboarding?.steps, home?.requires_setup]);
  const welcomeConnectedAccounts = useMemo(
    () => (home?.connected_accounts || []).slice(0, 4),
    [home?.connected_accounts],
  );
  const welcomeLeadSuggestion = useMemo(
    () => (isOnboardingMode ? null : visibleProactiveSuggestions[0] || null),
    [isOnboardingMode, visibleProactiveSuggestions],
  );
  const welcomeHeroSubtitle = useMemo(() => {
    if (threadMessages.length !== 0) {
      return homeSummaryText;
    }
    if (isOnboardingMode && home?.onboarding?.blocked_by_setup && String(home?.onboarding?.summary || "").trim()) {
      return String(home?.onboarding?.summary || "").trim();
    }
    if (isOnboardingMode && String(home?.onboarding?.interview_intro || "").trim()) {
      return String(home?.onboarding?.interview_intro || "").trim();
    }
    if (welcomeSetupItems.length) {
      return text.welcomeStarterSubtitleSetup;
    }
    if (welcomeConnectedAccounts.length || googleStatus?.configured) {
      return text.welcomeStarterSubtitleReady;
    }
    return text.threadEmptyDescription;
  }, [
    googleStatus?.configured,
    homeSummaryText,
    home?.onboarding?.interview_intro,
    isOnboardingMode,
    text.threadEmptyDescription,
    text.welcomeStarterSubtitleReady,
    text.welcomeStarterSubtitleSetup,
    threadMessages.length,
    welcomeConnectedAccounts.length,
    welcomeSetupItems.length,
  ]);
  const welcomeStarterItems = useMemo(
    () => {
      if (isOnboardingMode) {
        const onboardingItems: Array<{ id: string; title: string; details: string; route?: string }> = [];
        if (home?.onboarding?.blocked_by_setup) {
          const onboardingSummary = String(home?.onboarding?.summary || "").trim();
          if (onboardingSummary) {
            onboardingItems.push({
              id: "onboarding-setup-first",
              title: "Önce modeli bağla",
              details: onboardingSummary,
              route: "/settings?tab=kurulum&section=integration-provider&return_to=assistant",
            });
          }
          if (welcomeSetupItems.length) {
            onboardingItems.push({
              id: "onboarding-setup-item",
              title: welcomeSetupItems[0].title,
              details: welcomeSetupItems[0].details,
              route: welcomeSetupItems[0].route,
            });
          }
          if (onboardingItems.length) {
            return onboardingItems.slice(0, 1);
          }
        }
        const interviewIntro = String(home?.onboarding?.interview_intro || "").trim();
        if (interviewIntro) {
          onboardingItems.push({
            id: "onboarding-intro",
            title: "Önce kısa bir tanışma",
            details: interviewIntro,
          });
        }
        const onboardingSummary = String(home?.onboarding?.summary || "").trim();
        if (onboardingSummary) {
          onboardingItems.push({
            id: "onboarding-next-step",
            title: "Sonra ilk bağlantılar",
            details: onboardingSummary,
          });
        }
        if (onboardingItems.length) {
          return onboardingItems.slice(0, 2);
        }
      }
      if (welcomeSetupItems.length) {
        return welcomeSetupItems.slice(0, 2).map((item) => ({
          id: item.id,
          title: item.title,
          details: item.details,
          route: item.route,
        }));
      }
      const items: Array<{ id: string; title: string; details: string; route?: string }> = [];
      if (welcomeConnectedAccounts.length || googleStatus?.configured) {
        items.push({
          id: "connected",
          title: text.welcomeStarterConnectedTitle,
          details: googleStatus?.configured ? googleAssistantAccessSummary : text.welcomeStarterConnectedBody,
        });
      }
      if (welcomeLeadSuggestion) {
        items.push({
          id: String(welcomeLeadSuggestion.id || "starter-suggestion"),
          title: text.welcomeStarterSuggestionTitle,
          details: [welcomeLeadSuggestion.title, welcomeLeadSuggestion.details].filter(Boolean).join(" · "),
        });
      }
      if (!items.length) {
        items.push({
          id: "write-directly",
          title: text.welcomeStarterFallbackTitle,
          details: text.welcomeStarterFallbackBody,
        });
      }
      return items.slice(0, 2);
    },
    [
      googleAssistantAccessSummary,
      googleStatus?.configured,
      home?.onboarding?.interview_intro,
      home?.onboarding?.summary,
      isOnboardingMode,
      text.welcomeStarterConnectedBody,
      text.welcomeStarterConnectedTitle,
      text.welcomeStarterFallbackBody,
      text.welcomeStarterFallbackTitle,
      text.welcomeStarterSuggestionTitle,
      welcomeConnectedAccounts.length,
      welcomeLeadSuggestion,
      welcomeSetupItems,
    ],
  );
  const showWelcomeSetupShortcut = Boolean(
    !isOnboardingMode && (welcomeSetupItems.length || (!welcomeConnectedAccounts.length && !googleStatus?.configured)),
  );
  const handleWelcomePrompt = useCallback((item: string) => {
    if (home?.onboarding?.blocked_by_setup) {
      navigate("/settings?tab=kurulum&section=integration-provider&return_to=assistant");
      return;
    }
    handleSubmit(item);
  }, [handleSubmit, home?.onboarding?.blocked_by_setup, navigate]);
  const voiceStatusLabel = isVoiceAnalyzing
    ? text.chatVoiceModeAnalyzing
    : isResponding
    ? text.chatVoiceModeThinking
    : isSpeaking
      ? text.chatVoiceModeSpeaking
      : isListening
        ? text.chatVoiceModeListening
        : text.chatVoiceModeReady;
  const composerPlaceholder = isVoiceModeActive
    ? (
      isVoiceAnalyzing
        ? text.chatVoiceModeAnalyzing
        : isResponding
          ? text.chatVoiceModeThinking
          : isSpeaking
            ? text.chatVoiceModeSpeaking
            : isListening
              ? text.chatVoiceModeListening
              : text.chatVoiceModeReady
    )
    : text.chatPlaceholder;

  const handleCancelPendingReply = useCallback(() => {
    submitAbortControllerRef.current?.abort();
    submitAbortControllerRef.current = null;
    setStreamingAssistantMessage(null);
    setIsResponding(false);
    setIsSubmitting(false);
    if (!prompt.trim() && lastSubmittedPromptRef.current.trim()) {
      setPrompt(lastSubmittedPromptRef.current);
    }
    setError("");
  }, [prompt]);

  useEffect(() => {
    selectedSpeechVoiceRef.current = selectedSpeechVoice;
  }, [selectedSpeechVoice]);

  useEffect(() => {
    selectedVoiceIdRef.current = selectedVoiceId;
  }, [selectedVoiceId]);

  useEffect(() => {
    isVoicePlaybackEnabledRef.current = isVoicePlaybackEnabled;
  }, [isVoicePlaybackEnabled]);

  useEffect(() => {
    isRespondingRef.current = isResponding;
  }, [isResponding]);

  useEffect(() => {
    voiceTranscriptRef.current = voiceTranscript;
  }, [voiceTranscript]);

  useEffect(() => {
    if (!isVoiceModeActive || !prompt.trim()) {
      return;
    }
    requestAnimationFrame(() => scrollToBottom("auto"));
  }, [isVoiceModeActive, prompt, scrollToBottom]);

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
  }, [attachments.length, isSessionBriefDismissed, isVoiceModeActive, sessionBriefSuggestions.length]);

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
    persistSessionBriefDismissed(isSessionBriefDismissed);
  }, [isSessionBriefDismissed]);

  useEffect(() => {
    persistSelectedAssistantThreadId(selectedThreadId);
  }, [selectedThreadId]);

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
    void handleSubmit(home.onboarding.starter_prompts?.[0] || "Kısa bir tanışma yapalım.");
  }, [home, isLoading, isSubmitting, promptFromRoute, threadMessages.length]);

  useEffect(() => {
    if (!isOnboardingMode) {
      return;
    }
    setLatestAgentRun(null);
    setLatestAgentRunEvents([]);
  }, [isOnboardingMode]);

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

  function cacheAttachmentPreviews(items: ComposerAttachment[]) {
    const nextEntries = items
      .filter((item) => item.previewUrl)
      .map((item) => ({
        key: attachmentPreviewKeyFromComposerAttachment(item),
        url: item.previewUrl as string,
      }))
      .filter((item) => item.key && item.url);
    if (!nextEntries.length) {
      return {} as Record<string, string>;
    }
    const createdEntries = Object.fromEntries(nextEntries.map((item) => [item.key, item.url]));
    setAttachmentPreviewIndex((current) => {
      const next = { ...current };
      for (const item of nextEntries) {
        const existing = next[item.key];
        if (existing && existing !== item.url) {
          URL.revokeObjectURL(existing);
        }
        next[item.key] = item.url;
      }
      return next;
    });
    return createdEntries;
  }

  function clearAttachments() {
    revokeAttachmentPreviews(attachmentStoreRef.current);
    revokeAttachmentPreviews(submittedAttachmentsRef.current);
    attachmentStoreRef.current = [];
    submittedAttachmentsRef.current = [];
    setAttachments([]);
  }

  function stashComposerAttachments(items: ComposerAttachment[]) {
    submittedAttachmentsRef.current = items;
    attachmentStoreRef.current = [];
    setAttachments([]);
  }

  function finalizeSubmittedAttachments() {
    if (!submittedAttachmentsRef.current.length) {
      return;
    }
    revokeAttachmentPreviews(submittedAttachmentsRef.current);
    submittedAttachmentsRef.current = [];
  }

  function restoreSubmittedAttachments() {
    if (!submittedAttachmentsRef.current.length) {
      return;
    }
    const stashed = [...submittedAttachmentsRef.current];
    submittedAttachmentsRef.current = [];
    setAttachments((prev) => [...stashed, ...prev]);
  }

  function openAttachmentPicker() {
    fileInputRef.current?.click();
  }

  function stopLiveSpeechPreview() {
    if (speechPreviewRecognitionRef.current) {
      try {
        speechPreviewRecognitionRef.current.stop();
      } catch {
        // no-op
      }
      speechPreviewRecognitionRef.current = null;
    }
  }

  function clearVoiceRecognitionSilenceTimer() {
    if (voiceRecognitionSilenceTimerRef.current !== null) {
      window.clearTimeout(voiceRecognitionSilenceTimerRef.current);
      voiceRecognitionSilenceTimerRef.current = null;
    }
  }

  function resetStreamingSpeechState() {
    streamingSpeechQueueRef.current = [];
    streamingSpeechCursorRef.current = 0;
    streamingSpeechFinalRef.current = false;
  }

  function findSpeakableSegmentCutoff(text: string, force = false) {
    let cutoff = -1;
    for (let index = 0; index < text.length; index += 1) {
      const char = text[index];
      if (char === "." || char === "!" || char === "?" || char === "…" || char === "\n" || char === ":" || char === ";") {
        cutoff = index + 1;
      }
    }
    if (cutoff < 0 && force && text.trim()) {
      return text.length;
    }
    return cutoff;
  }

  function startLiveSpeechPreview(mode: "normal" | "voice") {
    const Recognition = getSpeechRecognitionFactory();
    if (!Recognition) {
      return;
    }
    try {
      const recognition = new Recognition();
      recognition.lang = "tr-TR";
      recognition.interimResults = true;
      recognition.continuous = true;
      recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map((result) => result[0]?.transcript || "")
          .join(" ")
          .trim();
        if (!transcript) {
          return;
        }
        if (mode === "voice") {
          setVoiceTranscript(transcript);
          setPrompt(`${speechSeedPromptRef.current}${transcript}`.trimStart());
        } else {
          setPrompt(`${speechSeedPromptRef.current}${transcript}`.trimStart());
        }
      };
      recognition.onerror = () => {
        speechPreviewRecognitionRef.current = null;
      };
      recognition.onend = () => {
        if (speechPreviewRecognitionRef.current === recognition) {
          speechPreviewRecognitionRef.current = null;
        }
      };
      recognition.start();
      speechPreviewRecognitionRef.current = recognition;
    } catch {
      speechPreviewRecognitionRef.current = null;
    }
  }

  function stopAudioLevelMeter() {
    if (audioMeterFrameRef.current !== null) {
      window.cancelAnimationFrame(audioMeterFrameRef.current);
      audioMeterFrameRef.current = null;
    }
    audioAnalyserRef.current = null;
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => null);
      audioContextRef.current = null;
    }
    voiceSilenceSinceRef.current = null;
    voiceDetectedSpeechRef.current = false;
    setVoiceLevel(0);
  }

  function stopInterruptMonitor() {
    if (interruptMeterFrameRef.current !== null) {
      window.cancelAnimationFrame(interruptMeterFrameRef.current);
      interruptMeterFrameRef.current = null;
    }
    interruptAnalyserRef.current = null;
    if (interruptAudioContextRef.current) {
      interruptAudioContextRef.current.close().catch(() => null);
      interruptAudioContextRef.current = null;
    }
    interruptStreamRef.current?.getTracks().forEach((track) => track.stop());
    interruptStreamRef.current = null;
    interruptSpeechSinceRef.current = null;
  }

  async function startInterruptMonitor() {
    if (!voiceModeActiveRef.current || !speechInFlightRef.current || interruptStreamRef.current || isListening || isVoiceAnalyzing) {
      return;
    }
    const AudioContextCtor = window.AudioContext || (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextCtor || !navigator.mediaDevices?.getUserMedia) {
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      if (!voiceModeActiveRef.current || !speechInFlightRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const audioContext = new AudioContextCtor();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 2048;
      analyser.smoothingTimeConstant = 0.82;
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      interruptStreamRef.current = stream;
      interruptAudioContextRef.current = audioContext;
      interruptAnalyserRef.current = analyser;
      interruptSpeechSinceRef.current = null;
      const samples = new Uint8Array(analyser.fftSize);
      const updateMeter = () => {
        if (!interruptAnalyserRef.current || !voiceModeActiveRef.current || !speechInFlightRef.current) {
          stopInterruptMonitor();
          return;
        }
        interruptAnalyserRef.current.getByteTimeDomainData(samples);
        let sumSquares = 0;
        for (let index = 0; index < samples.length; index += 1) {
          const centered = (samples[index] - 128) / 128;
          sumSquares += centered * centered;
        }
        const rms = Math.sqrt(sumSquares / samples.length);
        setVoiceLevel(Math.max(0, Math.min(1, rms * 3.6)));
        if (rms >= VOICE_INTERRUPT_AUDIO_THRESHOLD) {
          if (interruptSpeechSinceRef.current === null) {
            interruptSpeechSinceRef.current = performance.now();
          } else if (performance.now() - interruptSpeechSinceRef.current >= VOICE_INTERRUPT_HOLD_MS) {
            stopInterruptMonitor();
            interruptAssistantForVoiceInput();
            return;
          }
        } else {
          interruptSpeechSinceRef.current = null;
        }
        interruptMeterFrameRef.current = window.requestAnimationFrame(updateMeter);
      };
      interruptMeterFrameRef.current = window.requestAnimationFrame(updateMeter);
    } catch {
      stopInterruptMonitor();
    }
  }

  function startAudioLevelMeter(stream: MediaStream) {
    stopAudioLevelMeter();
    const AudioContextCtor = window.AudioContext || (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextCtor) {
      return;
    }
    try {
      const audioContext = new AudioContextCtor();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 2048;
      analyser.smoothingTimeConstant = 0.82;
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      audioContextRef.current = audioContext;
      audioAnalyserRef.current = analyser;
      const samples = new Uint8Array(analyser.fftSize);
      const updateMeter = () => {
        if (!audioAnalyserRef.current) {
          return;
        }
        audioAnalyserRef.current.getByteTimeDomainData(samples);
        let sumSquares = 0;
        for (let index = 0; index < samples.length; index += 1) {
          const centered = (samples[index] - 128) / 128;
          sumSquares += centered * centered;
        }
        const rms = Math.sqrt(sumSquares / samples.length);
        setVoiceLevel(Math.max(0, Math.min(1, rms * 3.6)));
        if (audioCaptureModeRef.current === "voice" && mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
          const hasTranscript = Boolean(voiceTranscriptRef.current.trim());
          const speechDetectedThreshold = Math.max(VOICE_AUDIO_SILENCE_THRESHOLD * 0.5, 0.012);
          if (rms >= speechDetectedThreshold) {
            voiceDetectedSpeechRef.current = true;
          }
          if (hasTranscript || voiceDetectedSpeechRef.current) {
            if (rms < VOICE_AUDIO_SILENCE_THRESHOLD) {
              if (voiceSilenceSinceRef.current === null) {
                voiceSilenceSinceRef.current = performance.now();
              } else if (performance.now() - voiceSilenceSinceRef.current > VOICE_AUTO_SUBMIT_SILENCE_MS) {
                try {
                  mediaRecorderRef.current.stop();
                } catch {
                  cleanupAudioCapture();
                  setIsListening(false);
                }
                return;
              }
            } else {
              voiceSilenceSinceRef.current = null;
            }
          } else {
            voiceSilenceSinceRef.current = null;
          }
        }
        audioMeterFrameRef.current = window.requestAnimationFrame(updateMeter);
      };
      audioMeterFrameRef.current = window.requestAnimationFrame(updateMeter);
    } catch {
      stopAudioLevelMeter();
    }
  }

  function cleanupAudioCapture() {
    mediaRecorderRef.current = null;
    mediaRecorderChunksRef.current = [];
    clearVoiceRecognitionSilenceTimer();
    stopLiveSpeechPreview();
    stopInterruptMonitor();
    stopAudioLevelMeter();
    voiceDetectedSpeechRef.current = false;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    audioCaptureModeRef.current = null;
  }

  async function finalizeRecordedAudioCapture(mode: "normal" | "voice", blob: Blob) {
    setIsVoiceAnalyzing(true);
    setError("");
    try {
      const mimeType = String(blob.type || preferredAudioRecordingMimeType() || "audio/webm");
      const file = new File(
        [blob],
        `ses-kaydi-${Date.now()}.${audioRecordingExtension(mimeType)}`,
        { type: mimeType, lastModified: Date.now() },
      );
      const analysis = await analyzeAssistantAttachment(settings, { file, purpose: "voice_transcript" });
      const sourceRef = analysis?.source_ref && typeof analysis.source_ref === "object"
        ? analysis.source_ref as Record<string, unknown>
        : {};
      const analysisAvailable = Boolean(sourceRef.analysis_available);
      const transcript = analysisAvailable
        ? normalizeVoiceTranscriptText(
            analysis.analysis_text
            || sourceRef.attachment_context
            || "",
          )
        : "";
      if (!transcript) {
        setError(analysisAvailable ? text.chatMicNoSpeech : text.chatMicUnsupported);
        return;
      }
      const nextPrompt = `${speechSeedPromptRef.current}${transcript}`.trim();
      setVoiceTranscript(transcript);
      setPrompt(nextPrompt);
      if (mode === "voice") {
        if (!voiceModeActiveRef.current) {
          return;
        }
        await handleSubmit(nextPrompt);
      } else {
        setPrompt(nextPrompt);
      }
    } catch {
      setError(text.chatMicError);
    } finally {
      setIsVoiceAnalyzing(false);
    }
  }

  async function startModelAudioCapture(mode: "normal" | "voice") {
    if (!canUseModelAudioCapture()) {
      return false;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const preferredMimeType = preferredAudioRecordingMimeType();
      const recorder = preferredMimeType
        ? new MediaRecorder(stream, { mimeType: preferredMimeType })
        : new MediaRecorder(stream);
      discardRecordedAudioRef.current = false;
      mediaRecorderChunksRef.current = [];
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      audioCaptureModeRef.current = mode;
      voiceDetectedSpeechRef.current = false;
      startAudioLevelMeter(stream);
      startLiveSpeechPreview(mode);
      if (mode === "voice") {
        setVoiceTranscript("");
        setPrompt(speechSeedPromptRef.current.trim());
      }
      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          mediaRecorderChunksRef.current.push(event.data);
        }
      };
      recorder.onerror = () => {
        cleanupAudioCapture();
        setIsListening(false);
        setError(text.chatMicError);
      };
      recorder.onstop = () => {
        const captureMode = audioCaptureModeRef.current || mode;
        const shouldDiscard = discardRecordedAudioRef.current;
        const chunks = [...mediaRecorderChunksRef.current];
        cleanupAudioCapture();
        setIsListening(false);
        if (shouldDiscard || !chunks.length) {
          return;
        }
        const blob = new Blob(chunks, { type: recorder.mimeType || preferredMimeType || "audio/webm" });
        void finalizeRecordedAudioCapture(captureMode, blob);
      };
      recorder.start();
      setIsListening(true);
      setError("");
      return true;
    } catch (error) {
      const denied = error instanceof DOMException && error.name === "NotAllowedError";
      setError(denied ? text.chatMicPermissionDenied : text.chatMicError);
      setIsListening(false);
      cleanupAudioCapture();
      return false;
    }
  }

  function stopListening(options: { discard?: boolean } = {}) {
    discardRecordedAudioRef.current = Boolean(options.discard);
    clearVoiceRecognitionSilenceTimer();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        cleanupAudioCapture();
        setIsListening(false);
      }
      return;
    }
    if (speechRecognitionRef.current) {
      speechRecognitionRef.current.stop();
    }
    if (options.discard) {
      cleanupAudioCapture();
    }
    setIsListening(false);
  }

  function startSpeechRecognitionCapture(mode: "normal" | "voice") {
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
      const scheduleVoiceAutoSubmit = () => {
        clearVoiceRecognitionSilenceTimer();
        if (mode !== "voice" || !lastTranscript.trim()) {
          return;
        }
        voiceRecognitionSilenceTimerRef.current = window.setTimeout(() => {
          if (speechRecognitionRef.current === recognition) {
            recognition.stop();
          }
        }, VOICE_AUTO_SUBMIT_SILENCE_MS);
      };

      recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map((result) => result[0]?.transcript || "")
          .join(" ")
          .trim();
        lastTranscript = transcript;
        setPrompt(`${speechSeedPromptRef.current}${transcript}`.trimStart());
        if (mode === "voice") {
          setVoiceTranscript(transcript);
          scheduleVoiceAutoSubmit();
        }
      };

      recognition.onend = () => {
        clearVoiceRecognitionSilenceTimer();
        setIsListening(false);
        if (mode === "voice") {
          const finalPrompt = `${speechSeedPromptRef.current}${lastTranscript}`.trimStart();
          if (finalPrompt) {
            setVoiceTranscript(lastTranscript);
            void handleSubmit(finalPrompt);
          } else if (voiceModeActiveRef.current) {
            startListening("voice");
          }
        }
      };

      recognition.onerror = () => {
        clearVoiceRecognitionSilenceTimer();
        setIsListening(false);
        setError(text.chatMicError);
      };

      speechRecognitionRef.current = recognition;
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

  function startListening(mode: "normal" | "voice") {
    clearVoiceRecognitionSilenceTimer();
    stopInterruptMonitor();
    speechSeedPromptRef.current = prompt.trim() ? `${prompt.trim()} ` : "";
    if (mode === "voice") {
      setVoiceLastReply("");
    }
    if (!canUseModelAudioCapture()) {
      startSpeechRecognitionCapture(mode);
      return;
    }
    void startModelAudioCapture(mode);
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

  function cancelAssistantSpeech(options: { resumeListening?: boolean } = {}) {
    resumeListeningAfterSpeechRef.current = false;
    resetStreamingSpeechState();
    speechInFlightRef.current = false;
    stopInterruptMonitor();
    window.speechSynthesis?.cancel();
    void window.lawcopilotDesktop?.stopSpeaking?.().catch(() => null);
    setIsSpeaking(false);
    if (options.resumeListening && voiceModeActiveRef.current) {
      startListening("voice");
    }
  }

  function interruptAssistantForVoiceInput() {
    suppressAssistantSpeechRef.current = true;
    submitAbortControllerRef.current?.abort();
    submitAbortControllerRef.current = null;
    setStreamingAssistantMessage(null);
    setIsResponding(false);
    isRespondingRef.current = false;
    setIsSubmitting(false);
    cancelAssistantSpeech({ resumeListening: true });
  }

  function defaultDesktopVoiceId() {
    const preferredTurkish = desktopVoices.find((voice) => String(voice.lang || "").toLowerCase().startsWith("tr"));
    return preferredTurkish?.id || desktopVoices[0]?.id || "";
  }

  function speakTextSegment(
    textContent: string,
    options: { resumeListening?: boolean; cancelExisting?: boolean; onComplete?: () => void } = {},
  ) {
    const { resumeListening = false, cancelExisting = false, onComplete } = options;
    if (!isVoicePlaybackEnabledRef.current) {
      speechInFlightRef.current = false;
      setIsSpeaking(false);
      if (resumeListening && voiceModeActiveRef.current) {
        startListening("voice");
      }
      onComplete?.();
      return;
    }
    const canUseDesktopSpeech = Boolean(window.lawcopilotDesktop?.speakText);
    const liveVoices = window.speechSynthesis?.getVoices?.() || availableVoices;
    const preferredVoice = resolveSpeechVoice(liveVoices, selectedVoiceIdRef.current) || selectedSpeechVoiceRef.current;
    const wantsDesktopVoice = selectedVoiceIdRef.current.startsWith("desktop:");
    const canUseBrowserSpeech = Boolean(window.speechSynthesis && typeof SpeechSynthesisUtterance !== "undefined" && !wantsDesktopVoice);
    const desktopVoiceId = selectedVoiceIdRef.current.startsWith("desktop:")
      ? selectedVoiceIdRef.current
      : defaultDesktopVoiceId();
    if (canUseBrowserSpeech && window.speechSynthesis && typeof SpeechSynthesisUtterance !== "undefined") {
      resumeListeningAfterSpeechRef.current = resumeListening;
      if (cancelExisting) {
        window.speechSynthesis.cancel();
        void window.lawcopilotDesktop?.stopSpeaking?.().catch(() => null);
      }
      const utterance = new SpeechSynthesisUtterance(speechTextFromMessage(textContent));
      utterance.lang = preferredVoice?.lang || "tr-TR";
      if (preferredVoice) {
        utterance.voice = preferredVoice;
      }
      utterance.onstart = () => {
        speechInFlightRef.current = true;
        setIsSpeaking(true);
        if (voiceModeActiveRef.current) {
          void startInterruptMonitor();
        }
      };
      utterance.onend = () => {
        stopInterruptMonitor();
        speechInFlightRef.current = false;
        setIsSpeaking(false);
        const shouldResume = resumeListeningAfterSpeechRef.current && voiceModeActiveRef.current;
        resumeListeningAfterSpeechRef.current = false;
        onComplete?.();
        if (shouldResume) {
          startListening("voice");
        }
      };
      utterance.onerror = () => {
        stopInterruptMonitor();
        speechInFlightRef.current = false;
        setIsSpeaking(false);
        const shouldResume = resumeListeningAfterSpeechRef.current && voiceModeActiveRef.current;
        resumeListeningAfterSpeechRef.current = false;
        onComplete?.();
        if (shouldResume) {
          startListening("voice");
        }
      };
      window.speechSynthesis.speak(utterance);
      return;
    }
    if (canUseDesktopSpeech) {
      resumeListeningAfterSpeechRef.current = resumeListening;
      if (cancelExisting) {
        void window.lawcopilotDesktop?.stopSpeaking?.().catch(() => null);
        window.speechSynthesis?.cancel();
      }
      speechInFlightRef.current = true;
      setIsSpeaking(true);
      if (voiceModeActiveRef.current) {
        void startInterruptMonitor();
      }
      void window.lawcopilotDesktop?.speakText?.({
        text: speechTextFromMessage(textContent),
        voiceId: desktopVoiceId,
      })
        .catch(() => null)
        .finally(() => {
          stopInterruptMonitor();
          speechInFlightRef.current = false;
          setIsSpeaking(false);
          const shouldResume = resumeListeningAfterSpeechRef.current && voiceModeActiveRef.current;
          resumeListeningAfterSpeechRef.current = false;
          onComplete?.();
          if (shouldResume) {
            startListening("voice");
          }
        });
      return;
    }
    if (!window.speechSynthesis || typeof SpeechSynthesisUtterance === "undefined") {
      speechInFlightRef.current = false;
      setIsSpeaking(false);
      if (resumeListening && voiceModeActiveRef.current) {
        startListening("voice");
      }
      onComplete?.();
      return;
    }
  }

  function flushStreamingSpeechQueue() {
    if (suppressAssistantSpeechRef.current || !streamingSpeechQueueRef.current.length || speechInFlightRef.current) {
      return;
    }
    const nextSegment = streamingSpeechQueueRef.current.shift();
    if (!nextSegment) {
      if (streamingSpeechFinalRef.current && voiceModeActiveRef.current && !isRespondingRef.current) {
        streamingSpeechFinalRef.current = false;
        startListening("voice");
      }
      return;
    }
    speakTextSegment(nextSegment, {
      onComplete: () => {
        if (streamingSpeechQueueRef.current.length) {
          flushStreamingSpeechQueue();
          return;
        }
        if (streamingSpeechFinalRef.current && voiceModeActiveRef.current && !isRespondingRef.current) {
          streamingSpeechFinalRef.current = false;
          startListening("voice");
        }
      },
    });
  }

  function queueStreamingAssistantSpeech(textContent: string, forceFinal = false) {
    if (suppressAssistantSpeechRef.current || !isVoicePlaybackEnabledRef.current) {
      return;
    }
    const speakable = speechTextFromMessage(textContent);
    const alreadyQueued = streamingSpeechCursorRef.current;
    if (speakable.length <= alreadyQueued) {
      if (forceFinal) {
        streamingSpeechFinalRef.current = true;
      }
      return;
    }
    const remaining = speakable.slice(alreadyQueued);
    const cutoff = findSpeakableSegmentCutoff(remaining, forceFinal);
    if (cutoff <= 0) {
      if (forceFinal) {
        streamingSpeechFinalRef.current = true;
      }
      return;
    }
    const segment = remaining.slice(0, cutoff).trim();
    streamingSpeechCursorRef.current += cutoff;
    if (segment) {
      streamingSpeechQueueRef.current.push(segment);
    }
    if (forceFinal) {
      streamingSpeechFinalRef.current = true;
    }
    flushStreamingSpeechQueue();
  }

  function speakAssistantMessage(textContent: string) {
    suppressAssistantSpeechRef.current = false;
    resetStreamingSpeechState();
    speakTextSegment(textContent, { resumeListening: voiceModeActiveRef.current, cancelExisting: true });
  }

  function handleVoiceModeToggle() {
    if (isVoiceModeActive) {
      setIsVoiceModeActive(false);
      setIsVoiceSettingsOpen(false);
      voiceModeActiveRef.current = false;
      stopListening({ discard: true });
      cancelAssistantSpeech();
      setIsVoiceAnalyzing(false);
      setVoiceTranscript("");
      setVoiceLastReply("");
      return;
    }
    setVoiceTranscript("");
    setVoiceLastReply("");
    resetStreamingSpeechState();
    setIsVoiceSettingsOpen(false);
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
        let analysisRef: Record<string, unknown> | null = null;
        try {
          const analysis = await analyzeAssistantAttachment(settings, { file: attachment.file });
          analysisRef = analysis.source_ref || null;
        } catch {
          analysisRef = null;
        }

        if (!matterId) {
          return {
            label: String(analysisRef?.label || attachment.file.name),
            kind: attachment.kind,
            uploaded: false,
            contentType: String(analysisRef?.content_type || attachment.file.type || ""),
            sizeBytes: Number(analysisRef?.size_bytes || attachment.file.size || 0),
            documentId: undefined,
            matterId: undefined,
            relativePath: undefined,
            attachmentContext: String(analysisRef?.attachment_context || ""),
            analysisAvailable: Boolean(analysisRef?.analysis_available),
            analysisMode: String(analysisRef?.analysis_mode || ""),
            fallback: !analysisRef,
          };
        }

        let response: Awaited<ReturnType<typeof uploadMatterDocument>> | null = null;
        try {
          response = await uploadMatterDocument(settings, matterId, {
            file: attachment.file,
            displayName: attachment.file.name,
            sourceType: "upload",
          });
        } catch {
          response = null;
        }
        return {
          label: response?.document.display_name || String(analysisRef?.label || attachment.file.name),
          kind: attachment.kind,
          uploaded: Boolean(response?.document),
          contentType: response?.document.content_type || String(analysisRef?.content_type || attachment.file.type || ""),
          sizeBytes: response?.document.size_bytes || Number(analysisRef?.size_bytes || attachment.file.size || 0),
          documentId: response?.document.id,
          matterId: response?.document.matter_id,
          relativePath: response?.document.filename,
          attachmentContext: response?.attachment_context || String(analysisRef?.attachment_context || ""),
          analysisAvailable: response?.analysis_available ?? Boolean(analysisRef?.analysis_available),
          analysisMode: response?.analysis_mode || String(analysisRef?.analysis_mode || ""),
          fallback: !response && !analysisRef,
        };
      }),
    );

    uploadResults.forEach((result, index) => {
      const attachment = selectedAttachments[index];
      if (result.status === "fulfilled") {
        if (result.value.fallback) {
          partialFallback = true;
        }
        sourceRefs.push({
          type: result.value.uploaded
            ? "matter_document"
            : result.value.kind === "image"
              ? "image_attachment"
              : String(result.value.contentType || "").startsWith("audio/")
                ? "audio_attachment"
                : "file_attachment",
          label: result.value.label,
          content_type: result.value.contentType,
          size_bytes: result.value.sizeBytes,
          uploaded: result.value.uploaded,
          document_id: result.value.documentId,
          matter_id: result.value.matterId,
          relative_path: result.value.relativePath,
          attachment_context: result.value.attachmentContext,
          analysis_available: result.value.analysisAvailable,
          analysis_mode: result.value.analysisMode,
        });
        return;
      }
      partialFallback = true;
      sourceRefs.push({
        type: attachment.kind === "image"
          ? "image_attachment"
          : String(attachment.file.type || "").startsWith("audio/")
            ? "audio_attachment"
            : "file_attachment",
        label: attachment.file.name,
        content_type: attachment.file.type,
        size_bytes: attachment.file.size,
        uploaded: false,
        upload_error: true,
      });
    });

    return { sourceRefs, partialFallback };
  }

  async function handleSubmit(nextPrompt?: string, options: { matterId?: number; editMessage?: ThreadDisplayMessage | null } = {}) {
    if (isSubmitting) {
      return;
    }
    suppressAssistantSpeechRef.current = false;
    submitAbortControllerRef.current?.abort();
    submitAbortControllerRef.current = null;
    const content = (nextPrompt ?? prompt).trim();
    const selectedAttachments = [...attachments];
    const editMessage = options.editMessage ?? null;
    const editMessageId = editMessage ? Number(editMessage.id || 0) : 0;
    const existingSourceRefs = editMessage?.source_context && Array.isArray(editMessage.source_context.source_refs)
      ? (editMessage.source_context.source_refs as Array<Record<string, unknown>>)
      : [];
    const previousThreadMessages = editMessageId > 0 ? [...threadMessagesRef.current] : null;
    const targetMatterId = options.matterId ?? settings.currentMatterId ?? undefined;
    const finalContent = content || (selectedAttachments.length ? text.chatDefaultAttachmentPrompt : "");
    if (!finalContent) {
      return;
    }
    lastSubmittedPromptRef.current = editMessageId > 0 ? "" : finalContent;
    if (selectedTool) {
      closeTool();
    }
    setIsSubmitting(true);
    setIsResponding(true);
    setEditingMessageId(null);
    setEditingMessageDraft("");
    setPrompt("");
    setVoiceTranscript("");
    setIsVoiceSettingsOpen(false);
    if (selectedAttachments.length) {
      stashComposerAttachments(selectedAttachments);
    }
    if (isListening) {
      stopListening();
    }

    let sourceRefs: Array<Record<string, unknown>> = selectedAttachments.length
      ? selectedAttachments.map((attachment) => ({
          type: attachment.kind === "image"
            ? "image_attachment"
            : String(attachment.file.type || "").startsWith("audio/")
              ? "audio_attachment"
              : "file_attachment",
          label: attachment.file.name,
          content_type: attachment.file.type,
          size_bytes: attachment.file.size,
          uploaded: false,
        }))
      : existingSourceRefs.map((item) => ({ ...item }));
    const previewEntries = cacheAttachmentPreviews(selectedAttachments);
    const optimisticSourceRefs = sourceRefs.map((item) => {
      const type = String(item.type || "").trim().toLowerCase();
      const contentType = String(item.content_type || "");
      const label = String(item.label || "");
      const kind: "image" | "file" = type === "image_attachment" || contentType.startsWith("image/") ? "image" : "file";
      if (!isInlinePreviewableAttachment(kind, contentType, label)) {
        return item;
      }
      const previewUrl = attachmentPreviewCandidates(
        label,
        contentType,
        Number(item.size_bytes || 0),
      ).map((key) => previewEntries[key]).find(Boolean);
      return previewUrl ? { ...item, preview_url: previewUrl } : item;
    });

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
        source_refs: optimisticSourceRefs,
      },
      requires_approval: false,
      generated_from: "assistant_thread_user",
      ai_provider: null,
      ai_model: null,
      starred: false,
      starred_at: null,
      created_at: new Date().toISOString(),
    };
    if (editMessageId > 0) {
      startTransition(() => {
        setThreadMessages((prev) => prev
          .filter((item) => Number(item.id || 0) <= editMessageId)
          .map((item) => (
            Number(item.id || 0) === editMessageId
              ? {
                  ...item,
                  content: finalContent,
                  source_context: {
                    ...(item.source_context || {}),
                    source_refs: optimisticSourceRefs,
                  },
                }
              : item
          )));
      });
    } else {
      setThreadMessages((prev) => [...prev, tempUserMsg]);
    }
    requestAnimationFrame(() => scrollToBottom());
    const submitController = new AbortController();
    submitAbortControllerRef.current = submitController;

    try {
      if (selectedAttachments.length) {
        const prepared = await prepareAttachmentSourceRefs(selectedAttachments, targetMatterId);
        sourceRefs = prepared.sourceRefs;
        if (prepared.partialFallback) {
          setError(text.chatAttachmentPartialFallback);
        }
      }
      const starterPrompts = Array.isArray(home?.onboarding?.starter_prompts) ? home.onboarding.starter_prompts : [];
      const onboardingReplyLoop = Boolean(
        home?.onboarding
          && !home.onboarding.complete
          && latestAssistantThreadMessage?.generated_from === "assistant_onboarding_guide"
          && !selectedAttachments.length
          && finalContent.length <= 220,
      );
      if (editMessageId <= 0 && !isOnboardingMode && !starterPrompts.includes(finalContent) && !onboardingReplyLoop) {
        void createAgentRun(settings, {
          goal: finalContent,
          title: finalContent.slice(0, 120),
          matter_id: targetMatterId,
          thread_id: selectedThreadId || undefined,
          source_refs: sourceRefs,
        })
          .then((run) => {
            setLatestAgentRun(run);
            setLatestAgentRunEvents([]);
            void startAgentRunTracking(run.id);
          })
          .catch(() => null);
      }
      let finalResponse: AssistantThreadResponse | null = null;
      await streamAssistantThreadMessage(
        settings,
        {
          content: finalContent,
          thread_id: selectedThreadId || undefined,
          edit_message_id: editMessageId > 0 ? editMessageId : undefined,
          matter_id: targetMatterId,
          source_refs: sourceRefs,
        },
        async (event) => {
          if (event.type === "thread_ready") {
            return;
          }
          if (event.type === "assistant_start") {
            suppressAssistantSpeechRef.current = false;
            resetStreamingSpeechState();
            setStreamingAssistantMessage(createTransientThreadMessage("assistant", "", "assistant-stream"));
            return;
          }
          if (event.type === "assistant_chunk") {
            setStreamingAssistantMessage((current) => ({
              ...(current || createTransientThreadMessage("assistant", "", "assistant-stream")),
              content: event.content,
            }));
            if (voiceModeActiveRef.current) {
              setVoiceLastReply(event.content);
              if (isVoicePlaybackEnabledRef.current && !suppressAssistantSpeechRef.current) {
                queueStreamingAssistantSpeech(event.content);
              }
            }
            scheduleStreamScrollToBottom("auto");
            return;
          }
          if (event.type === "assistant_complete") {
            finalResponse = event.response;
            setIsResponding(false);
            return;
          }
          if (event.type === "error") {
            throw new Error(event.detail || text.queryError);
          }
        },
        { signal: submitController.signal },
      );
      setStreamingAssistantMessage(null);
      submitAbortControllerRef.current = null;
      if (!finalResponse) {
        throw new Error(text.noResponse);
      }
      const response = finalResponse as AssistantThreadResponse;
      const responseMessage = response.message && typeof response.message === "object" ? response.message : null;
      const responseMemoryUpdates = responseMessage?.source_context
        && typeof responseMessage.source_context === "object"
        && Array.isArray(responseMessage.source_context.memory_updates)
        ? responseMessage.source_context.memory_updates as Array<Record<string, unknown>>
        : [];
      const responseMemoryKinds = Array.from(
        new Set(responseMemoryUpdates.map((item) => String(item.kind || "").trim()).filter(Boolean)),
      );
      if (responseMemoryKinds.length && typeof window !== "undefined") {
        window.localStorage.removeItem(SETTINGS_PROFILE_CACHE_KEY);
        window.localStorage.removeItem(SETTINGS_ASSISTANT_RUNTIME_CACHE_KEY);
        invalidateEmbeddedPersonalModelCache(settings.officeId);
        window.dispatchEvent(new CustomEvent(SETTINGS_MEMORY_UPDATE_EVENT, {
          detail: {
            kinds: responseMemoryKinds,
          },
        }));
      }
      startTransition(() => {
        setSelectedThreadId(response.thread.id);
        setThreadMessages(response.messages);
      });
      persistSelectedAssistantThreadId(response.thread.id);
      const automationApplyError = await maybeApplyAssistantAutomationUpdates(response);
      if (response.draft_preview) {
        setDrafts((current) => mergeDraftIntoList(current, response.draft_preview as OutboundDraft));
      }
      if (
        response.dispatch_mode === "ready_to_send"
        && response.draft_preview
        && window.lawcopilotDesktop?.dispatchApprovedAction
      ) {
        const responseAction = responseMessage?.source_context
          && typeof responseMessage.source_context === "object"
          && responseMessage.source_context.assistant_action
          && typeof responseMessage.source_context.assistant_action === "object"
          ? responseMessage.source_context.assistant_action as Record<string, unknown>
          : null;
        const responseDraft = response.draft_preview as Record<string, unknown>;
        await window.lawcopilotDesktop.dispatchApprovedAction({
          action: responseAction,
          draft: responseDraft,
          actionId: Number(responseAction?.id || 0) || undefined,
          draftId: Number(responseDraft?.id || 0) || undefined,
          channel: String(responseDraft?.channel || responseAction?.target_channel || "").trim(),
        });
        await refreshAssistantSurface().catch(() => null);
      }
      const homeResponse = await getAssistantHome(settings);
      startTransition(() => {
        setHome(homeResponse);
      });
      if (selectedTool) {
        await loadToolData(selectedTool).catch(() => null);
      }
      await refreshThreadSummaries(response.thread.id).catch(() => null);
      if (automationApplyError) {
        setError(automationApplyError);
      } else if (!selectedAttachments.length) {
        setError("");
      }
      finalizeSubmittedAttachments();
      lastSubmittedPromptRef.current = "";
      scheduleStreamScrollToBottom("auto");
      if (voiceModeActiveRef.current) {
        const lastMsg = response.messages[response.messages.length - 1];
        if (lastMsg && lastMsg.role === "assistant") {
          setVoiceLastReply(lastMsg.content);
          if (isVoicePlaybackEnabledRef.current && !suppressAssistantSpeechRef.current) {
            queueStreamingAssistantSpeech(lastMsg.content, true);
          } else {
            startListening("voice");
          }
        } else {
          startListening("voice");
        }
      }
    } catch (err) {
      setStreamingAssistantMessage(null);
      setIsResponding(false);
      restoreSubmittedAttachments();
      if (editMessageId > 0 && previousThreadMessages) {
        startTransition(() => {
          setThreadMessages(previousThreadMessages);
        });
        setEditingMessageId(editMessageId);
        setEditingMessageDraft(finalContent);
      }
      if (err instanceof DOMException && err.name === "AbortError") {
        setError("");
      } else {
        setError(err instanceof Error ? err.message : text.queryError);
      }
    } finally {
      submitAbortControllerRef.current = null;
      setIsResponding(false);
      setIsSubmitting(false);
    }
  }

  async function handleApproveFromBubble(approval: BubbleApprovalItem, message: any) {
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

  async function prepareAssistantDraftForDispatch(
    draft: OutboundDraft,
    note: string,
    options: { allowPendingBridge?: boolean } = {},
  ) {
    const draftId = Number(draft.id || 0);
    if (!draftId) {
      throw new Error("Taslak bulunamadı.");
    }
    let response: Record<string, unknown>;
    try {
      response = await sendAssistantDraft(settings, draftId, note) as Record<string, unknown>;
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
      response = await approveAssistantApproval(settings, approval.id, { note }) as Record<string, unknown>;
    }
    const nextDraft = (response.draft && typeof response.draft === "object" ? response.draft : draft) as Record<string, unknown>;
    const nextAction = (response.action && typeof response.action === "object" ? response.action : null) as Record<string, unknown> | null;
    let pendingDesktopBridge = false;

    if (response.dispatch_mode === "ready_to_send") {
      if (!window.lawcopilotDesktop?.dispatchApprovedAction) {
        if (!options.allowPendingBridge) {
          throw new Error("Masaüstü gönderim köprüsü hazır değil.");
        }
        pendingDesktopBridge = true;
      } else {
        await window.lawcopilotDesktop.dispatchApprovedAction({
          action: nextAction,
          draft: nextDraft,
          actionId: Number(nextAction?.id || 0) || undefined,
          draftId,
          channel: String(nextDraft?.channel || draft.channel || "").trim(),
        });
      }
    }

    return {
      draft: nextDraft as OutboundDraft,
      action: nextAction,
      dispatchMode: String(response.dispatch_mode || ""),
      pendingDesktopBridge,
    };
  }

  async function handleSendDraftFromTool(draft: OutboundDraft) {
    const draftId = Number(draft.id || 0);
    if (!draftId) {
      return;
    }
    setDraftBusyId(String(draft.id));
    setDraftBusyMode("send");
    try {
      await prepareAssistantDraftForDispatch(draft, "Taslaklar panelinden onaylanıp gönderildi.");
      await refreshAssistantSurface();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Taslak gönderilemedi.");
      await refreshAssistantSurface().catch(() => null);
    } finally {
      setDraftBusyId("");
      setDraftBusyMode("");
    }
  }

  async function handleRemoveDraftFromTool(draft: OutboundDraft) {
    const draftId = Number(draft.id || 0);
    if (!draftId) {
      return;
    }
    setDraftBusyId(String(draft.id));
    setDraftBusyMode("remove");
    try {
      await removeAssistantDraft(settings, draftId, "Taslak çalışma panelinden kaldırıldı.");
      setDrafts((current) => current.filter((item) => Number(item.id || 0) !== draftId));
      setError("");
      await refreshAssistantSurface().catch(() => null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Taslak kaldırılamadı.");
      await refreshAssistantSurface().catch(() => null);
    } finally {
      setDraftBusyId("");
      setDraftBusyMode("");
    }
  }

  async function handlePauseActionFromTool(action: SuggestedAction) {
    const actionId = Number(action.id || 0);
    if (!actionId) {
      return;
    }
    setActionBusyId(String(actionId));
    setActionBusyMode("pause");
    try {
      const response = await pauseAssistantAction(settings, actionId, "Çalışma panelinden duraklatıldı.");
      const nextDraft = response.draft;
      if (response.action) {
        setActions((current) => mergeActionIntoList(current, response.action));
      }
      if (nextDraft) {
        setDrafts((current) => mergeDraftIntoList(current, nextDraft));
      }
      await refreshAssistantSurface().catch(() => null);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aksiyon duraklatılamadı.");
    } finally {
      setActionBusyId("");
      setActionBusyMode("");
    }
  }

  async function handleResumeActionFromTool(action: SuggestedAction) {
    const actionId = Number(action.id || 0);
    if (!actionId) {
      return;
    }
    setActionBusyId(String(actionId));
    setActionBusyMode("resume");
    try {
      const response = await resumeAssistantAction(settings, actionId, "Çalışma panelinden yeniden başlatıldı.");
      const nextDraft = response.draft;
      if (response.action) {
        setActions((current) => mergeActionIntoList(current, response.action));
      }
      if (nextDraft) {
        setDrafts((current) => mergeDraftIntoList(current, nextDraft));
      }
      await refreshAssistantSurface().catch(() => null);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aksiyon yeniden başlatılamadı.");
    } finally {
      setActionBusyId("");
      setActionBusyMode("");
    }
  }

  async function handleRetryActionFromTool(action: SuggestedAction) {
    const actionId = Number(action.id || 0);
    if (!actionId) {
      return;
    }
    setActionBusyId(String(actionId));
    setActionBusyMode("retry");
    try {
      const response = await retryAssistantActionDispatch(settings, actionId, "Çalışma panelinden yeniden deneme planlandı.");
      const nextDraft = response.draft;
      if (response.action) {
        setActions((current) => mergeActionIntoList(current, response.action));
      }
      if (nextDraft) {
        setDrafts((current) => mergeDraftIntoList(current, nextDraft));
      }
      await refreshAssistantSurface().catch(() => null);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yeniden gönderim planlanamadı.");
    } finally {
      setActionBusyId("");
      setActionBusyMode("");
    }
  }

  async function handleCompensateActionFromTool(action: SuggestedAction) {
    const actionId = Number(action.id || 0);
    if (!actionId) {
      return;
    }
    setActionBusyId(String(actionId));
    setActionBusyMode("compensate");
    try {
      const response = await scheduleAssistantActionCompensation(settings, actionId, "Çalışma panelinden telafi akışı başlatıldı.");
      const nextDraft = response.draft;
      if (response.action) {
        setActions((current) => mergeActionIntoList(current, response.action));
      }
      if (nextDraft) {
        setDrafts((current) => mergeDraftIntoList(current, nextDraft));
      }
      if (response.compensation_action) {
        setActions((current) => mergeActionIntoList(current, response.compensation_action as SuggestedAction));
      }
      if (response.compensation_draft) {
        setDrafts((current) => mergeDraftIntoList(current, response.compensation_draft as OutboundDraft));
      }
      await refreshAssistantSurface().catch(() => null);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Telafi akışı başlatılamadı.");
    } finally {
      setActionBusyId("");
      setActionBusyMode("");
    }
  }

  async function handleResetThread() {
    setIsResetting(true);
    try {
      if (selectedThreadId) {
        await resetAssistantThreadById(settings, selectedThreadId);
      } else {
        await resetAssistantThread(settings);
      }
      setHandledApprovalIds({});
      await loadHomeAndThread(selectedThreadId || undefined);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : text.queryError);
    } finally {
      setIsResetting(false);
    }
  }

  async function handleSelectThread(threadId: number) {
    if (!threadId || threadId === selectedThreadId || isSubmitting) {
      return;
    }
    setIsThreadListLoading(true);
    setStreamingAssistantMessage(null);
    try {
      const response = await getAssistantThread(settings, { limit: PAGE_SIZE, thread_id: threadId });
      startTransition(() => {
        setSelectedThreadId(threadId);
        setThreadMessages(response.messages);
        setStarredMessages([]);
        setHasMore(!!response.has_more);
        setStreamingAssistantMessage(null);
      });
      persistSelectedAssistantThreadId(threadId);
      setSidebarSection("threads");
      setError("");
      isFirstLoad.current = true;
      scheduleStreamScrollToBottom("auto");
      void refreshThreadSummaries(threadId).catch(() => null);
    } catch (err) {
      setError(err instanceof Error ? err.message : text.queryError);
    } finally {
      setIsThreadListLoading(false);
    }
  }

  async function handleCreateThread() {
    if (isCreatingThread || isSubmitting) {
      return;
    }
    setIsCreatingThread(true);
    try {
      const response = await createAssistantThread(settings);
      const nextThreadId = Number(response.thread?.id || 0);
      setHandledApprovalIds({});
      if (nextThreadId > 0) {
        const thread = response.thread;
        startTransition(() => {
          setStreamingAssistantMessage(null);
          setThreadMessages([]);
          setStarredMessages([]);
          setHasMore(false);
          setSelectedThreadId(nextThreadId);
          setThreadSummaries((current) => {
            const nextSummary: AssistantThreadSummary = {
              ...thread,
              message_count: 0,
              last_message_preview: null,
              last_message_at: thread.updated_at || thread.created_at,
            };
            return [nextSummary, ...current.filter((item) => item.id !== nextThreadId)];
          });
        });
        persistSelectedAssistantThreadId(nextThreadId);
        setSidebarSection("threads");
        scheduleStreamScrollToBottom("auto");
        void refreshThreadSummaries(nextThreadId).catch(() => null);
      } else {
        startTransition(() => {
          setStreamingAssistantMessage(null);
          setThreadMessages([]);
          setStarredMessages([]);
          setHasMore(false);
        });
        void loadHomeAndThread(undefined, { refreshHome: false }).catch(() => null);
      }
      setPrompt("");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : text.queryError);
    } finally {
      setIsCreatingThread(false);
    }
  }

  function handleOpenThreadMenu(threadId: number) {
    setThreadMenuOpenId((current) => {
      const nextId = current === threadId ? null : threadId;
      if (nextId === null) {
        setThreadMenuPosition(null);
      }
      return nextId;
    });
  }

  function handleStartThreadRename(item: AssistantThreadSummary) {
    setThreadMenuOpenId(null);
    setThreadMenuPosition(null);
    setRenamingThreadId(item.id);
    setThreadRenameValue(String(item.title || "Yeni sohbet"));
  }

  function handleCancelThreadRename() {
    setRenamingThreadId(null);
    setThreadRenameValue("");
  }

  async function handleSubmitThreadRename(threadId: number) {
    const nextTitle = threadRenameValue.trim();
    if (!nextTitle) {
      setError("Sohbet adı boş bırakılamaz.");
      return;
    }
    if (threadActionBusyId === threadId) {
      return;
    }
    const currentTitle = String(threadSummaries.find((item) => item.id === threadId)?.title || "").trim();
    if (currentTitle === nextTitle) {
      handleCancelThreadRename();
      return;
    }
    setThreadActionBusyId(threadId);
    try {
      await updateAssistantThread(settings, threadId, { title: nextTitle });
      startTransition(() => {
        setThreadSummaries((current) => current.map((item) => (
          item.id === threadId ? { ...item, title: nextTitle } : item
        )));
      });
      handleCancelThreadRename();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : text.queryError);
    } finally {
      setThreadActionBusyId(null);
    }
  }

  function handleRequestDeleteThread(item: AssistantThreadSummary) {
    if (threadActionBusyId === item.id) {
      return;
    }
    setThreadMenuOpenId(null);
    setThreadMenuPosition(null);
    setDeleteConfirmThread(item);
  }

  async function handleDeleteThread() {
    const item = deleteConfirmThread;
    if (!item || threadActionBusyId === item.id) {
      return;
    }
    setThreadMenuOpenId(null);
    setThreadMenuPosition(null);
    setDeleteConfirmThread(null);
    const deletedThreadId = item.id;
    setThreadActionBusyId(item.id);
    try {
      const response = await deleteAssistantThread(settings, item.id);
      const nextThreadId = Number(response.selected_thread_id || 0);
      const deletedSelectedThread = deletedThreadId === selectedThreadIdRef.current;
      setHandledApprovalIds({});
      handleCancelThreadRename();
      if (deletedSelectedThread && nextThreadId > 0) {
        await loadHomeAndThread(nextThreadId, { refreshHome: false });
      } else {
        startTransition(() => {
          setThreadSummaries(response.items || []);
        });
      }
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : text.queryError);
    } finally {
      setThreadActionBusyId(null);
    }
  }

  function handleThreadRenameKeyDown(event: ReactKeyboardEvent<HTMLInputElement>, threadId: number) {
    if (event.key === "Enter") {
      event.preventDefault();
      void handleSubmitThreadRename(threadId);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      handleCancelThreadRename();
    }
  }

  function setThreadHistoryOpen(nextOpen: boolean) {
    setIsSidebarExpanded(nextOpen);
    if (nextOpen) {
      setSidebarSection("threads");
    }
  }

  function setStarredMessagesOpen(nextOpen: boolean) {
    setIsSidebarExpanded(nextOpen);
    if (nextOpen) {
      setSidebarSection("starred");
    }
  }

  useEffect(() => {
    if (!isThreadHistoryOpen && !isStarredMessagesOpen) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsSidebarExpanded(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isStarredMessagesOpen, isThreadHistoryOpen]);

  useEffect(() => {
    if (!isStarredMessagesOpen) {
      setStarredSearch("");
      return;
    }
    void loadStarredMessages().catch((err) => {
      setError(err instanceof Error ? err.message : "Yıldızlı mesajlar yüklenemedi.");
    });
  }, [isStarredMessagesOpen, loadStarredMessages]);

  useEffect(() => {
    if (searchParams.get("new") !== "1" || isCreatingThread || isSubmitting) {
      return;
    }
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete("new");
    setSearchParams(nextParams, { replace: true });
    void handleCreateThread();
  }, [isCreatingThread, isSubmitting, searchParams, setSearchParams]);

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

  handleSubmitRef.current = handleSubmit;
  openToolRef.current = openTool;
  approveApprovalRef.current = handleApproveFromBubble;
  rejectApprovalRef.current = handleRejectFromBubble;

  const handleBubbleQuickReply = useCallback((nextText: string) => {
    void handleSubmitRef.current(nextText);
  }, []);

  const handleRunIntegrationSetup = useCallback(async (setup: Record<string, unknown>) => {
    const setupId = Number(setup.id || 0);
    if (!setupId) {
      throw new Error("Kurulum bilgisi eksik görünüyor.");
    }
    if (!window.lawcopilotDesktop?.runAssistantLegacySetup) {
      const fallbackPath = String(setup.deep_link_path || "").trim();
      if (fallbackPath) {
        navigate(fallbackPath);
        return;
      }
      throw new Error("Bu cihazda sohbetten kurulum devamı desteklenmiyor.");
    }
    try {
      setError("");
      const result = await window.lawcopilotDesktop.runAssistantLegacySetup({ setupId });
      if (result && typeof result === "object") {
        const desktopAction = String(result.desktopAction || result.desktop_action || setup.desktop_action || "").trim();
        const status = result.status && typeof result.status === "object"
          ? result.status as Record<string, unknown>
          : {};
        const validation = result.validation && typeof result.validation === "object"
          ? result.validation as Record<string, unknown>
          : {};
        updateIntegrationSetupDesktopState(setupId, {
          desktopAction,
          message: String(result.message || status.message || validation.message || ""),
          ...status,
          ...validation,
        });
        syncDesktopSetupFollowUpMessage(setup, {
          desktopAction,
          message: String(result.message || status.message || validation.message || ""),
          ...status,
          ...validation,
        });
        if (desktopAction === "start_whatsapp_web_link") {
          startWhatsAppSetupPolling(setupId);
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Kurulum adımı başlatılamadı.";
      setError(message);
      throw err;
    }
  }, [navigate, startWhatsAppSetupPolling, syncDesktopSetupFollowUpMessage, updateIntegrationSetupDesktopState]);

  const handleBubbleOpenTool = useCallback((tool: ToolKey) => {
    openToolRef.current(tool);
  }, []);

  const handleBubbleApproveApproval = useCallback((approval: BubbleApprovalItem, message: ThreadDisplayMessage) => {
    void approveApprovalRef.current(approval, message);
  }, []);

  const handleBubbleRejectApproval = useCallback((approval: BubbleApprovalItem) => {
    void rejectApprovalRef.current(approval);
  }, []);

  const assistantBodyStyle = useMemo(
    () => ({ "--assistant-drawer-width": `${drawerWidth}px` } as CSSProperties),
    [drawerWidth],
  );

  function openSidebarSection(section: AssistantSidebarSection) {
    setSidebarSection(section);
    setIsSidebarExpanded(true);
  }

  function focusThreadSearch() {
    window.setTimeout(() => threadSearchInputRef.current?.focus(), 0);
  }

  function focusStarredSearch() {
    window.setTimeout(() => starredSearchInputRef.current?.focus(), 0);
  }

  /* ── Render ─────────────────────────────────────────────── */

  if (isLoading) {
    return <LoadingSpinner label="Asistan yükleniyor..." />;
  }

  return (
    <div className="assistant-vnext">
      <div className={`assistant-workspace${isSidebarExpanded ? " assistant-workspace--sidebar-open" : ""}`}>
        <aside className={`assistant-sidebar${isSidebarExpanded ? " assistant-sidebar--expanded" : ""}`} aria-label="Asistan kenar çubuğu">
          <div className="assistant-sidebar__rail">
              <div className="assistant-sidebar__header">
                <button
                  className="assistant-sidebar__rail-btn assistant-sidebar__rail-btn--toggle"
                  type="button"
                  onClick={() => setIsSidebarExpanded((current) => !current)}
                  aria-label={isSidebarExpanded ? "Kenar çubuğunu kapat" : "Kenar çubuğunu aç"}
                  title={isSidebarExpanded ? "Kenar çubuğunu kapat" : "Kenar çubuğunu aç"}
                >
                  <SidebarToggleIcon expanded={isSidebarExpanded} />
                </button>
                <div className="assistant-sidebar__brand">
                  <strong>LawCopilot</strong>
                  <span>Asistan oturumları</span>
                </div>
              </div>

              <div className="assistant-sidebar__nav">
                <button
                  className="assistant-sidebar__rail-btn"
                  type="button"
                  onClick={() => void handleCreateThread()}
                  aria-label="Yeni sohbet"
                  title="Yeni sohbet"
                  disabled={isCreatingThread || isSubmitting}
                >
                  <SidebarNavIcon name="compose" />
                  <span className="assistant-sidebar__rail-label">Yeni sohbet</span>
                </button>
                <button
                  className={`assistant-sidebar__rail-btn${sidebarSection === "threads" ? " assistant-sidebar__rail-btn--active" : ""}`}
                  type="button"
                  onClick={() => {
                    openSidebarSection("threads");
                    focusThreadSearch();
                  }}
                  aria-label="Sohbetlerde ara"
                  title="Sohbetlerde ara"
                >
                  <SidebarNavIcon name="search" active={sidebarSection === "threads"} />
                  <span className="assistant-sidebar__rail-label">Sohbetlerde ara</span>
                </button>
                <button
                  className={`assistant-sidebar__rail-btn${sidebarSection === "starred" ? " assistant-sidebar__rail-btn--active" : ""}`}
                  type="button"
                  onClick={() => {
                    openSidebarSection("starred");
                    focusStarredSearch();
                  }}
                  aria-label="Yıldızlı mesajlar"
                  title="Yıldızlı mesajlar"
                >
                  <SidebarNavIcon name="star" active={sidebarSection === "starred"} />
                  <span className="assistant-sidebar__rail-label">Yıldızlanan mesajlar</span>
                </button>
                <button
                  className="assistant-sidebar__rail-btn"
                  type="button"
                  onClick={() => navigate("/settings")}
                  aria-label="Ayarlar"
                  title="Ayarlar"
                >
                  <SidebarNavIcon name="settings" />
                  <span className="assistant-sidebar__rail-label">Ayarlar</span>
                </button>
              </div>

              <div className={`assistant-sidebar__details${isSidebarExpanded ? " assistant-sidebar__details--expanded" : ""}`}>
              <div className="assistant-sidebar__divider" aria-hidden="true" />
              <div className="assistant-sidebar__panel-scroll">
                {sidebarSection === "threads" ? (
                  <>
                    <label className="assistant-history-modal__search assistant-sidebar__search">
                      <SidebarNavIcon name="search" />
                      <input
                        ref={threadSearchInputRef}
                        type="search"
                        value={threadSearch}
                        onChange={(event) => setThreadSearch(event.target.value)}
                        placeholder="Sohbet ara"
                      />
                    </label>
                    <div className="assistant-sidebar__section-label">Yakın sohbetler</div>
                    <div className="assistant-history-modal__list assistant-sidebar__list">
                      {isThreadListLoading && !threadSummaries.length ? (
                        <div className="assistant-history-modal__empty">Sohbetler yükleniyor...</div>
                      ) : visibleThreadSummaries.length ? (
                        visibleThreadSummaries.map((item) => (
                          <div
                            key={item.id}
                            className={`assistant-history-row${item.id === selectedThreadId ? " assistant-history-row--active" : ""}`}
                          >
                            <button
                              className="assistant-history-row__main"
                              type="button"
                              onClick={() => handleSelectThread(item.id)}
                              disabled={isSubmitting || threadActionBusyId === item.id}
                            >
                              <span className="assistant-history-row__content">
                                {renamingThreadId === item.id ? (
                                  <input
                                    ref={threadRenameInputRef}
                                    className="assistant-history-row__rename-input"
                                    value={threadRenameValue}
                                    onChange={(event) => setThreadRenameValue(event.target.value)}
                                    onClick={(event) => event.stopPropagation()}
                                    onBlur={() => void handleSubmitThreadRename(item.id)}
                                    onKeyDown={(event) => handleThreadRenameKeyDown(event, item.id)}
                                    placeholder="Sohbet adı"
                                    disabled={threadActionBusyId === item.id}
                                  />
                                ) : (
                                  <span className="assistant-history-row__title">{item.title || "Yeni sohbet"}</span>
                                )}
                                {item.last_message_preview ? (
                                  <span className="assistant-history-row__snippet">{item.last_message_preview}</span>
                                ) : null}
                              </span>
                              <span className="assistant-history-row__meta">{threadTimestampLabel(item.last_message_at || item.updated_at)}</span>
                            </button>
                            <div className="assistant-history-row__actions">
                              <button
                                ref={(node) => {
                                  threadMenuTriggerRefs.current[item.id] = node;
                                }}
                                className={`assistant-history-row__menu-trigger${threadMenuOpenId === item.id ? " assistant-history-row__menu-trigger--open" : ""}`}
                                type="button"
                                aria-haspopup="menu"
                                aria-expanded={threadMenuOpenId === item.id}
                                aria-label={`${item.title || "Sohbet"} için seçenekler`}
                                title="Sohbet seçenekleri"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleOpenThreadMenu(item.id);
                                }}
                              >
                                <ThreadOverflowIcon />
                              </button>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="assistant-history-modal__empty">
                          {threadSearch.trim() ? "Aramaya uygun sohbet bulunamadı." : "Henüz kayıtlı sohbet yok."}
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <label className="assistant-history-modal__search assistant-sidebar__search">
                      <SidebarNavIcon name="search" />
                      <input
                        ref={starredSearchInputRef}
                        type="search"
                        value={starredSearch}
                        onChange={(event) => setStarredSearch(event.target.value)}
                        placeholder="Yıldızlı mesaj ara"
                      />
                    </label>
                    <div className="assistant-sidebar__section-label">
                      Tüm sohbetlerde yıldızlananlar
                    </div>
                    <div className="assistant-history-modal__list assistant-sidebar__list">
                      {visibleStarredMessages.length ? (
                        visibleStarredMessages.map((item) => (
                          <button
                            key={`starred-${item.id}`}
                            className="assistant-history-row assistant-history-row--starred"
                            type="button"
                            onClick={() => void handleOpenStarredMessage(item)}
                            disabled={isSubmitting}
                          >
                            <span className="assistant-history-row__content">
                              <span className="assistant-history-row__title">{item.thread_title || "Yıldızlı mesaj"}</span>
                              <span className="assistant-history-row__snippet">{starredMessagePreview(item.content)}</span>
                            </span>
                            <span className="assistant-history-row__meta">{threadTimestampLabel(item.starred_at || item.created_at)}</span>
                          </button>
                        ))
                      ) : (
                        <div className="assistant-history-modal__empty">
                          {starredSearch.trim() ? "Aramaya uygun yıldızlı mesaj bulunamadı." : "Henüz yıldızlanan mesaj yok."}
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
              </div>
          </div>
        </aside>

        {threadMenuOpenId !== null && openThreadMenuItem && threadMenuPosition && typeof document !== "undefined"
          ? createPortal(
            <div
              ref={threadMenuRef}
              className="assistant-history-row__menu"
              role="menu"
              aria-label="Sohbet seçenekleri"
              style={{
                top: `${threadMenuPosition.top}px`,
                left: `${threadMenuPosition.left}px`,
              }}
            >
              <button
                className="assistant-history-row__menu-item"
                type="button"
                role="menuitem"
                onClick={() => handleStartThreadRename(openThreadMenuItem)}
              >
                <ThreadRenameIcon />
                <span>Yeniden adlandır</span>
              </button>
              <button
                className="assistant-history-row__menu-item assistant-history-row__menu-item--danger"
                type="button"
                role="menuitem"
                onClick={() => handleRequestDeleteThread(openThreadMenuItem)}
              >
                <ThreadDeleteIcon />
                <span>Sil</span>
              </button>
            </div>,
            document.body,
          )
          : null}

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
              accept="image/*,.pdf,.txt,.md,.doc,.docx,audio/*"
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
              {displayedMessages.length ? (
                <>
                  {/* Sentinel for infinite scroll */}
                  {threadMessages.length ? (
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
                  ) : null}

                  {/* Reset thread button */}
                  {!hasMore && threadMessages.length > 0 ? (
                    <div className="wa-reset-row">
                      <button className="wa-reset-btn" type="button" onClick={handleResetThread} disabled={isResetting}>
                        {isResetting ? text.threadResetBusy : text.threadReset}
                      </button>
                    </div>
                  ) : null}

                  {/* Message bubbles */}
                  {displayedMessages.map((message) => (
                    <div
                      key={message.id}
                      ref={(node) => {
                        if (typeof message.id === "number") {
                          messageNodeMapRef.current[message.id] = node;
                        }
                      }}
                      className={`wa-message-anchor${typeof message.id === "number" && highlightedMessageId === message.id ? " wa-message-anchor--highlight" : ""}`}
                    >
                      <ChatBubble
                        message={message}
                        onToggleStar={handleToggleMessageStar}
                        onCopyMessage={handleCopyThreadMessage}
                        onShareMessage={handleOpenShareDialog}
                        onEditMessage={handleEditThreadMessage}
                        isEditing={editingMessageId === message.id}
                        editValue={editingMessageId === message.id ? editingMessageDraft : ""}
                        editBusy={isSubmitting && editingMessageId === message.id}
                        onEditValueChange={setEditingMessageDraft}
                        onCancelEdit={handleCancelThreadEdit}
                        onSubmitEdit={handleSubmitEditedThreadMessage}
                        onSetFeedback={handleAssistantMessageFeedback}
                        onSubmitFeedbackNote={handleAssistantMessageFeedbackNote}
                        onOpenTool={handleBubbleOpenTool}
                        onQuickReply={handleBubbleQuickReply}
                        onRunIntegrationSetup={handleRunIntegrationSetup}
                        integrationSetupDesktopState={(() => {
                          const setup = message.source_context?.integration_setup;
                          if (!setup || typeof setup !== "object") {
                            return null;
                          }
                          const setupId = Number((setup as Record<string, unknown>).id || 0);
                          return setupId ? (integrationSetupDesktopStates[setupId] || null) : null;
                        })()}
                        onApproveApproval={handleBubbleApproveApproval}
                        onRejectApproval={handleBubbleRejectApproval}
                        feedbackValue={message.role === "assistant" ? feedbackValueFromMessage(message) : null}
                        starBusyMessageId={starBusyMessageId}
                        approvalBusyId={approvalBusyId}
                        handledApprovalIds={handledApprovalIds}
                        activeApprovalStatuses={activeApprovalStatuses}
                        onMessageMemoryAction={handleMemoryCorrectionAction}
                        onPreviewClick={(url, name, type) => setFullscreenPreview({ url, name, type })}
                      />
                    </div>
                  ))}

                  {/* Typing indicator */}
                  {isResponding && !hasStreamingAssistantContent ? <TypingIndicator /> : null}
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
                    {welcomeHeroSubtitle}
                  </p>

                  <div className="wa-welcome__stack">
                    <div className="callout wa-welcome__card wa-welcome__card--narrow">
                      <strong>{text.welcomeStarterTitle}</strong>
                      <div className="list" style={{ marginTop: "0.85rem" }}>
                        {welcomeStarterItems.slice(0, 1).map((item) => (
                          item.route ? (
                            <button
                              key={item.id}
                              className="list-item assistant-welcome-link-card"
                              type="button"
                              onClick={() => navigate(item.route!)}
                            >
                              <strong>{item.title}</strong>
                              {item.details ? <p className="list-item__meta">{item.details}</p> : null}
                            </button>
                          ) : (
                            <article className="list-item" key={item.id}>
                              <strong>{item.title}</strong>
                              {item.details ? <p className="list-item__meta">{item.details}</p> : null}
                            </article>
                          )
                        ))}
                      </div>
                      <div style={{ display: "flex", gap: "0.5rem", justifyContent: "center", marginTop: "0.85rem", flexWrap: "wrap" }}>
                        {showWelcomeSetupShortcut && !welcomeLeadSuggestion ? (
                          <Link className="button button--secondary" to="/settings?tab=kurulum&section=kurulum-karti">
                            {text.welcomeSetupAction}
                          </Link>
                        ) : null}
                        {welcomeLeadSuggestion ? (
                          <button className="button button--secondary" type="button" onClick={() => handleProactiveSuggestion(welcomeLeadSuggestion)}>
                            {welcomeLeadSuggestion.action_label || text.proactiveDefaultAction}
                          </button>
                        ) : null}
                      </div>
                    </div>
                    {home?.relationship_profiles?.length || home?.contact_directory?.length ? (
                      <AssistantHomeContactsPanel
                        importantProfiles={home?.relationship_profiles || []}
                        directory={home?.contact_directory || []}
                        summary={home?.contact_directory_summary || null}
                        busyId=""
                        onToggleMute={() => undefined}
                      />
                    ) : null}
                  </div>

                  {!home?.onboarding?.blocked_by_setup && welcomeQuickPrompts.length ? (
                    <div className="wa-quick-prompts">
                      <strong>{quickPromptsTitle}</strong>
                      <p className="wa-quick-prompts__sub">{quickPromptsSubtitle}</p>
                      <div className="wa-quick-prompts__grid">
                        {welcomeQuickPrompts.slice(0, 2).map((item) => (
                          <button key={item} className="wa-chip wa-chip--prompt" type="button" onClick={() => handleWelcomePrompt(item)} disabled={isSubmitting}>
                            {item}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Scroll-to-bottom fab */}
            <ScrollToBottomButton visible={showScrollBtn} onClick={() => scrollToBottom()} />

            {/* Input area */}
            <div className="wa-input-wrapper" ref={inputWrapperRef}>
              {showSessionBrief ? (
                <>
                  <div className="callout callout--accent wa-session-brief" style={{ marginBottom: "0.85rem" }}>
                    <div className="wa-session-brief__header">
                      <strong className="wa-session-brief__title">{home?.greeting_title || text.welcomeTitle}</strong>
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
                          <div key={`session-${item.id}`} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                            <button className="button button--ghost" type="button" onClick={() => handleProactiveSuggestion(item)}>
                              {item.action_label || item.title}
                            </button>
                            {item.secondary_action_url ? (
                              <a
                                className="button button--ghost"
                                href={item.secondary_action_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {item.secondary_action_label || "Haritada aç"}
                              </a>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </>
              ) : null}
              <form
                className={`wa-input-area${isVoiceModeActive ? " wa-input-area--voice" : ""}`}
                onSubmit={(event) => {
                  event.preventDefault();
                  handleSubmit();
                }}
              >
                {attachments.length ? (
                  <div className="wa-attachments">
                    <div className="wa-attachments__list wa-attachments__list--composer">
                      {attachments.map((attachment) => (
                        <article
                          key={attachment.id}
                          className={`wa-attachment-chip wa-attachment-chip--${attachment.kind}`}
                          onClick={() => {
                            const url = attachment.previewUrl || URL.createObjectURL(attachment.file);
                            setFullscreenPreview({ url, name: attachment.file.name, type: attachment.file.type || "application/pdf" });
                          }}
                          style={{ cursor: "pointer" }}
                        >
                          {attachment.kind === "image" && attachment.previewUrl ? (
                            <img className="wa-attachment-chip__preview" src={attachment.previewUrl} alt={attachment.file.name} />
                          ) : (
                            <div className="wa-attachment-chip__placeholder">
                              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                              </svg>
                            </div>
                          )}
                          <div className="wa-attachment-chip__meta">
                            <strong>{attachment.file.name}</strong>
                            <span>{attachmentTypeLabel(attachment.file.name, attachment.file.type)}</span>
                          </div>
                          <button
                            className="wa-attachment-chip__remove"
                            type="button"
                            title={text.chatAttachmentRemove}
                            onClick={(e) => {
                              e.stopPropagation();
                              removeAttachment(attachment.id);
                            }}
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M18 6 6 18" />
                              <path d="m6 6 12 12" />
                            </svg>
                          </button>
                        </article>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className={`wa-input-row${isVoiceModeActive ? " wa-input-row--voice" : ""}`} aria-live={isVoiceModeActive ? "polite" : undefined}>
                  <div className="wa-input-actions wa-input-actions--left">
                    <button className="wa-icon-btn" type="button" title={text.chatAttachFile} aria-label={text.chatAttachFile} onClick={openAttachmentPicker}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 5v14" />
                        <path d="M5 12h14" />
                      </svg>
                    </button>
                  </div>
                  <textarea
                    ref={composerInputRef}
                    className={`wa-input-field${isVoiceModeActive ? " wa-input-field--voice" : ""}`}
                    value={prompt}
                    onChange={(event) => {
                      const nextValue = event.target.value;
                      setPrompt(nextValue);
                      if (isVoiceModeActive) {
                        const seed = speechSeedPromptRef.current;
                        const transcriptOnly = seed && nextValue.startsWith(seed)
                          ? nextValue.slice(seed.length).trimStart()
                          : nextValue;
                        setVoiceTranscript(transcriptOnly);
                      }
                    }}
                    placeholder={composerPlaceholder}
                    rows={1}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSubmit();
                      }
                    }}
                  />
                  <div className="wa-input-actions wa-input-actions--right">
                    {isVoiceModeActive ? (
                      <>
                        <div className="wa-voice-meter" aria-hidden="true">
                          {Array.from({ length: 12 }, (_, index) => {
                            const normalized = (index + 1) / 12;
                            const active = voiceLevel >= normalized * 0.78;
                            const animated = isSpeaking || isResponding || isListening;
                            return (
                              <span
                                key={`voice-inline-${index}`}
                                className={`wa-voice-meter__bar${active ? " wa-voice-meter__bar--active" : ""}${animated ? " wa-voice-meter__bar--animated" : ""}`}
                                style={{ ["--voice-bar-delay" as string]: `${index * 80}ms` }}
                              />
                            );
                          })}
                        </div>
                        <button
                          className={`wa-icon-btn${isListening ? " wa-icon-btn--active" : ""}`}
                          type="button"
                          title={isListening ? text.chatMicStop : text.chatMicStart}
                          aria-label={isListening ? text.chatMicStop : text.chatMicStart}
                          onClick={() => {
                            if (isSpeaking) {
                              cancelAssistantSpeech({ resumeListening: true });
                              return;
                            }
                            if (isListening) {
                              stopListening();
                              return;
                            }
                            startListening("voice");
                          }}
                          disabled={isVoiceAnalyzing}
                        >
                          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
                            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                            <line x1="12" y1="19" x2="12" y2="22"/>
                            <line x1="8" y1="22" x2="16" y2="22"/>
                          </svg>
                        </button>
                        <button
                          className={`wa-icon-btn${isVoiceSettingsOpen ? " wa-icon-btn--active" : ""}`}
                          type="button"
                          title={text.chatVoiceSelectionLabel}
                          aria-label={text.chatVoiceSelectionToggle}
                          onClick={() => setIsVoiceSettingsOpen((current) => !current)}
                        >
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <line x1="4" y1="21" x2="4" y2="14" />
                            <line x1="4" y1="10" x2="4" y2="3" />
                            <line x1="12" y1="21" x2="12" y2="12" />
                            <line x1="12" y1="8" x2="12" y2="3" />
                            <line x1="20" y1="21" x2="20" y2="16" />
                            <line x1="20" y1="12" x2="20" y2="3" />
                            <line x1="2" y1="14" x2="6" y2="14" />
                            <line x1="10" y1="8" x2="14" y2="8" />
                            <line x1="18" y1="16" x2="22" y2="16" />
                          </svg>
                        </button>
                        <button
                          className="wa-send-btn wa-send-btn--voice"
                          type="button"
                          title={text.chatVoiceModeFinish}
                          aria-label={text.chatVoiceModeFinish}
                          onClick={handleVoiceModeToggle}
                        >
                          {text.chatVoiceModeFinish}
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          className={`wa-icon-btn${isListening ? " wa-icon-btn--active" : ""}`}
                          type="button"
                          title={isListening ? text.chatMicStop : text.chatMicStart}
                          aria-label={isListening ? text.chatMicStop : text.chatMicStart}
                          onClick={handleMicToggle}
                          disabled={isSubmitting || isVoiceAnalyzing}
                        >
                          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
                            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                            <line x1="12" y1="19" x2="12" y2="22"/>
                            <line x1="8" y1="22" x2="16" y2="22"/>
                          </svg>
                        </button>
                        {isResponding ? (
                          <button className="wa-send-btn" type="button" title={text.chatCancelReply} aria-label={text.chatCancelReply} onClick={handleCancelPendingReply}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <rect x="6" y="6" width="12" height="12" rx="2" ry="2" />
                            </svg>
                          </button>
                        ) : prompt.trim().length > 0 ? (
                          <button className="wa-send-btn" type="submit" disabled={!canSubmit || isSubmitting} title={text.chatSend} aria-label={text.chatSend}>
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M12 20V4M5 11l7-7 7 7"/>
                            </svg>
                          </button>
                        ) : (
                          <button
                            className="wa-send-btn"
                            type="button"
                            title={text.chatVoiceModeButton}
                            aria-label={text.chatVoiceModeStart}
                            onClick={handleVoiceModeToggle}
                            disabled={isVoiceAnalyzing}
                          >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M5 10v4M9 8v8M13 6v12M17 8v8M21 10v4" />
                            </svg>
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
                {isVoiceModeActive && isVoiceSettingsOpen ? (
                  <div className="wa-voice-settings" role="dialog" aria-label={text.chatVoiceSelectionLabel}>
                    <label className="wa-voice-settings__toggle">
                      <input
                        type="checkbox"
                        checked={isVoicePlaybackEnabled}
                        onChange={(event) => setIsVoicePlaybackEnabled(event.target.checked)}
                      />
                      <span>{text.chatVoicePlaybackToggle}</span>
                    </label>
                    <label htmlFor="assistant-voice-select" className="wa-voice-settings__label">
                      {text.chatVoiceSelectionLabel}
                    </label>
                    <select
                      id="assistant-voice-select"
                      className="wa-voice-settings__input"
                      aria-label={text.chatVoiceSelectionLabel}
                      value={selectedVoiceId || AUTO_VOICE_PREFERENCE}
                      onChange={(event) => {
                        const nextValue = String(event.target.value || "");
                        const resolvedValue = nextValue === AUTO_VOICE_PREFERENCE ? "" : nextValue;
                        const liveVoices = window.speechSynthesis?.getVoices?.() || availableVoices;
                        selectedVoiceIdRef.current = resolvedValue;
                        selectedSpeechVoiceRef.current = resolveSpeechVoice(liveVoices, resolvedValue);
                        setSelectedVoiceId(resolvedValue);
                      }}
                    >
                      <option value={AUTO_VOICE_PREFERENCE}>{text.chatVoiceSelectionAuto}</option>
                      {desktopVoices.length ? (
                        <optgroup label="Masaüstü sesleri">
                          {desktopVoices.map((voice) => (
                            <option key={voice.id} value={voice.id}>
                              {voice.name}{voice.lang ? ` (${voice.lang})` : ""}
                            </option>
                          ))}
                        </optgroup>
                      ) : null}
                      {availableVoices.length ? (
                        <optgroup label="Tarayıcı sesleri">
                          {availableVoices.map((voice) => {
                            const optionId = speechVoiceId(voice);
                            return (
                              <option key={optionId} value={optionId}>
                                {speechVoiceLabel(voice)}
                              </option>
                            );
                          })}
                        </optgroup>
                      ) : null}
                    </select>
                  </div>
                ) : null}
              </form>
              <div className="wa-input-footer">
                {error ? (
                  <span style={{ color: "var(--danger)" }}>{error}</span>
                ) : isVoiceModeActive ? (
                  <span>{voiceStatusLabel}</span>
                ) : isVoiceAnalyzing ? (
                  <span>{text.chatMicAnalyzing}</span>
                ) : isSpeaking ? (
                  <span>{text.chatVoiceModeSpeaking}</span>
                ) : isListening ? (
                  <span>{text.chatListening}</span>
                ) : isVoiceModeActive ? null : attachments.length ? (
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
                {selectedTool === "today" ? (
                  <TodayTool
                    agenda={agenda}
                    actions={actions}
                    actionBusyId={actionBusyId}
                    actionBusyMode={actionBusyMode}
                    onPauseAction={handlePauseActionFromTool}
                    onResumeAction={handleResumeActionFromTool}
                    onRetryAction={handleRetryActionFromTool}
                    onCompensateAction={handleCompensateActionFromTool}
                  />
                ) : null}
                {selectedTool === "calendar" ? (
                  <CalendarTool
                    items={calendar}
                    today={calendarToday}
                    googleState={calendarGoogleState}
                    outlookState={calendarOutlookState}
                    selectedMatterId={settings.currentMatterId || undefined}
                    canSyncGoogle={Boolean(window.lawcopilotDesktop?.syncGoogleData)}
                    isSyncing={isCalendarSyncing}
                    isCreating={isCalendarCreating}
                    onSyncGoogle={handleSyncGoogleCalendar}
                    onCreateEvent={handleCreateCalendarEvent}
                  />
                ) : null}
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
                {selectedTool === "drafts" ? (
                  <DraftsTool
                    drafts={drafts}
                    matterDrafts={matterDrafts}
                    onSendDraft={handleSendDraftFromTool}
                    onRemoveDraft={handleRemoveDraftFromTool}
                    draftBusyId={draftBusyId}
                    draftBusyMode={draftBusyMode}
                    actionBusyId={actionBusyId}
                    actionBusyMode={actionBusyMode}
                    onPauseAction={handlePauseActionFromTool}
                    onResumeAction={handleResumeActionFromTool}
                    onRetryAction={handleRetryActionFromTool}
                    onCompensateAction={handleCompensateActionFromTool}
                  />
                ) : null}
              </div>
            </SectionCard>
          </aside>
        ) : null}
      </div>
      {shareDialogMessage ? (
        <div
          className="assistant-share-dialog-backdrop"
          role="presentation"
          onClick={() => {
            if (!shareDialogBusy) {
              handleCloseShareDialog();
            }
          }}
        >
          <div
            className="assistant-share-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="assistant-share-dialog-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="assistant-share-dialog__header">
              <div className="assistant-share-dialog__copy">
                <h3 id="assistant-share-dialog-title" className="assistant-share-dialog__title">Mesajı paylaş</h3>
                <p className="assistant-share-dialog__description">
                  Yanıtı WhatsApp, e-posta, Telegram, X veya LinkedIn için hızlıca paylaşıma hazırlayabilirsin.
                </p>
              </div>
              <button
                className="assistant-share-dialog__close"
                type="button"
                onClick={handleCloseShareDialog}
                disabled={shareDialogBusy}
                aria-label="Paylaşım penceresini kapat"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
            </div>

            <div className="assistant-share-dialog__channel-list" role="tablist" aria-label="Paylaşım kanalları">
              {SHARE_CHANNEL_OPTIONS.map((item) => (
                <button
                  key={item.value}
                  className={`assistant-share-dialog__channel-btn${shareChannel === item.value ? " assistant-share-dialog__channel-btn--active" : ""}`}
                  type="button"
                  role="tab"
                  aria-selected={shareChannel === item.value}
                  onClick={() => handleShareChannelChange(item.value)}
                  disabled={shareDialogBusy}
                >
                  {item.label}
                </button>
              ))}
            </div>

            {assistantShareNeedsRecipient(shareChannel) ? (
              <div className="assistant-share-dialog__section">
                <div className="assistant-share-dialog__section-head">
                  <strong>
                    {shareChannel === "email"
                      ? "Alıcı"
                      : shareChannel === "telegram"
                        ? "Kişi veya grup"
                        : "Kişi veya grup"}
                  </strong>
                  <span>
                    {shareChannel === "whatsapp"
                      ? "WhatsApp kişi ve grupları"
                      : shareChannel === "telegram"
                        ? "Telegram hedefleri"
                        : "E-posta adresleri"}
                  </span>
                </div>
                <input
                  className="input assistant-share-dialog__search"
                  type="search"
                  placeholder={shareChannel === "email" ? "Alıcı ara" : "Kişi veya grup ara"}
                  value={shareRecipientQuery}
                  onChange={(event) => setShareRecipientQuery(event.target.value)}
                  disabled={shareDialogBusy}
                />
                <div className="assistant-share-dialog__target-list" role="list">
                  {shareProfilesLoading ? (
                    <div className="assistant-share-dialog__empty">Kişiler yükleniyor...</div>
                  ) : shareTargetOptions.length ? (
                    shareTargetOptions.slice(0, 12).map((item) => (
                      <button
                        key={item.id}
                        className={`assistant-share-dialog__target-row${shareSelectedProfileId === item.profileId ? " assistant-share-dialog__target-row--active" : ""}`}
                        type="button"
                        onClick={() => handleSelectShareTarget(item)}
                        disabled={shareDialogBusy}
                      >
                        <div className="assistant-share-dialog__target-copy">
                          <strong>{item.label}</strong>
                          {item.sublabel ? <span>{item.sublabel}</span> : null}
                        </div>
                        <StatusBadge tone={item.kind === "group" ? "warning" : "neutral"}>
                          {item.kind === "group" ? "Grup" : "Kişi"}
                        </StatusBadge>
                      </button>
                    ))
                  ) : (
                    <div className="assistant-share-dialog__empty">
                      Uygun hedef bulunamadı. İstersen alıcıyı aşağıya elle yaz.
                    </div>
                  )}
                </div>
                <input
                  className="input assistant-share-dialog__recipient-input"
                  type={shareChannel === "email" ? "email" : "text"}
                  placeholder={
                    shareChannel === "email"
                      ? "ornek@alan.com"
                      : shareChannel === "telegram"
                        ? "@kullanici veya grup adı"
                        : "Kişi adı, grup adı veya numara"
                  }
                  value={shareRecipient}
                  onChange={(event) => {
                    setShareRecipient(event.target.value);
                    if (!event.target.value.trim()) {
                      setShareSelectedProfileId("");
                    }
                  }}
                  disabled={shareDialogBusy}
                />
              </div>
            ) : null}

            {shareChannel === "email" ? (
              <div className="assistant-share-dialog__section">
                <div className="assistant-share-dialog__section-head">
                  <strong>Konu</strong>
                  <span>E-posta konu satırı</span>
                </div>
                <input
                  className="input assistant-share-dialog__recipient-input"
                  type="text"
                  placeholder="Kısa bir konu yaz"
                  value={shareDraftSubject}
                  onChange={(event) => setShareDraftSubject(event.target.value)}
                  disabled={shareDialogBusy}
                />
              </div>
            ) : null}

            <div className="assistant-share-dialog__section">
              <div className="assistant-share-dialog__section-head">
                <strong>Paylaşım metni</strong>
                <span>İstersen göndermeden önce düzenleyebilirsin.</span>
              </div>
              <textarea
                className="assistant-share-dialog__textarea"
                rows={8}
                value={shareDraftBody}
                onChange={(event) => setShareDraftBody(event.target.value)}
                disabled={shareDialogBusy}
              />
            </div>

            {shareDialogError ? <p className="assistant-share-dialog__error">{shareDialogError}</p> : null}

            <div className="assistant-share-dialog__actions">
              <button
                className="assistant-share-dialog__button assistant-share-dialog__button--secondary"
                type="button"
                onClick={handleCloseShareDialog}
                disabled={shareDialogBusy}
              >
                Vazgeç
              </button>
              <button
                className="assistant-share-dialog__button assistant-share-dialog__button--primary"
                type="button"
                onClick={() => void handleCreateShareDraft()}
                disabled={shareDialogBusy}
              >
                {shareDialogBusy ? "Hazırlanıyor..." : "Paylaşımı hazırla"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {deleteConfirmThread ? (
        <div
          className="assistant-confirm-dialog-backdrop"
          role="presentation"
          onClick={() => {
            if (threadActionBusyId !== deleteConfirmThread.id) {
              setDeleteConfirmThread(null);
            }
          }}
        >
          <div
            className="assistant-confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="assistant-thread-delete-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="assistant-confirm-dialog__icon" aria-hidden="true">
              <ThreadDeleteIcon />
            </div>
            <div className="assistant-confirm-dialog__copy">
              <h3 id="assistant-thread-delete-title" className="assistant-confirm-dialog__title">Sohbet silinsin mi?</h3>
              <p className="assistant-confirm-dialog__description">
                <strong>{deleteConfirmThread.title || "Bu sohbet"}</strong> kalıcı olarak sohbet listesinden kaldırılacak.
              </p>
              <p className="assistant-confirm-dialog__hint">Bu işlem geri alınamaz.</p>
            </div>
            <div className="assistant-confirm-dialog__actions">
              <button
                className="assistant-confirm-dialog__button assistant-confirm-dialog__button--secondary"
                type="button"
                onClick={() => setDeleteConfirmThread(null)}
                disabled={threadActionBusyId === deleteConfirmThread.id}
              >
                Vazgeç
              </button>
              <button
                className="assistant-confirm-dialog__button assistant-confirm-dialog__button--danger"
                type="button"
                onClick={() => void handleDeleteThread()}
                disabled={threadActionBusyId === deleteConfirmThread.id}
              >
                {threadActionBusyId === deleteConfirmThread.id ? "Siliniyor..." : "Sohbeti sil"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {fullscreenPreview ? (
        <div className="wa-fullscreen-preview" onClick={() => setFullscreenPreview(null)}>
          <div
            className="wa-fullscreen-preview__panel"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={fullscreenPreview.name}
          >
            <div className="wa-fullscreen-preview__header">
              <span className="wa-fullscreen-preview__title">{fullscreenPreview.name}</span>
              <button className="wa-fullscreen-preview__close" type="button" onClick={() => setFullscreenPreview(null)} aria-label="Kapat">
                &times;
              </button>
            </div>
            <div className="wa-fullscreen-preview__body">
              {fullscreenPreview.type.startsWith("image/") ? (
                <div className="wa-fullscreen-preview__frame-shell">
                  <img src={fullscreenPreview.url} alt={fullscreenPreview.name} />
                </div>
              ) : fullscreenPreview.type.startsWith("audio/") ? (
                <div className="wa-fullscreen-preview__frame-shell wa-fullscreen-preview__frame-shell--audio">
                  <audio controls src={fullscreenPreview.url} preload="metadata">
                    Tarayıcı bu ses kaydını oynatamıyor.
                  </audio>
                </div>
              ) : (
                <div className="wa-fullscreen-preview__frame-shell">
                  <iframe
                    src={fullscreenPreview.type.toLowerCase().includes("pdf")
                      ? `${fullscreenPreview.url}#toolbar=1&navpanes=0&scrollbar=1&statusbar=0&messages=0&view=FitH`
                      : fullscreenPreview.url}
                    title={fullscreenPreview.name}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
      </div>
    </div>
  );
}
