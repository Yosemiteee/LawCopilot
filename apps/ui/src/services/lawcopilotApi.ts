import type { AppSettings } from "../app/AppContext";
import type {
  ActivityResponse,
  Citation,
  CitationReviewResponse,
  ChronologyResponse,
  DocumentChunk,
  Draft,
  EmailDraft,
  EmailDraftEvent,
  EmailDraftPreview,
  GeneratedDraftResponse,
  GoogleIntegrationStatus,
  Health,
  IngestionJob,
  Matter,
  MatterNote,
  MatterSummary,
  MatterDocument,
  MatterWorkspaceDocumentLink,
  ModelProfilesResponse,
  QueryJob,
  RiskNotesResponse,
  SearchResponse,
  SimilarDocumentsResponse,
  SocialEvent,
  SuggestedAction,
  Task,
  AssistantAgendaItem,
  AssistantHomeResponse,
  AssistantThreadResponse,
  AssistantCalendarResponse,
  AssistantRuntimeProfile,
  AssistantRuntimeWorkspaceStatus,
  AssistantApproval,
  AssistantToolStatus,
  TelemetryHealth,
  TelegramIntegrationStatus,
  TaskRecommendationsResponse,
  TimelineEvent,
  OutboundDraft,
  UserProfile,
  WorkspaceChunk,
  WorkspaceDocument,
  WorkspaceOverviewResponse,
  WorkspaceRoot,
  WorkspaceScanJob,
  WorkspaceSearchResponse
} from "../types/domain";
import { apiRequest } from "./apiClient";

export function getHealth(settings: AppSettings) {
  return apiRequest<Health>(settings, "/health");
}

export function getModelProfiles(settings: AppSettings) {
  return apiRequest<ModelProfilesResponse>(settings, "/settings/model-profiles");
}

export function getUserProfile(settings: AppSettings) {
  return apiRequest<UserProfile>(settings, "/profile");
}

export function saveUserProfile(
  settings: AppSettings,
  payload: {
    display_name?: string;
    food_preferences?: string;
    transport_preference?: string;
    weather_preference?: string;
    travel_preferences?: string;
    communication_style?: string;
    assistant_notes?: string;
    important_dates?: Array<{ label: string; date: string; recurring_annually: boolean; notes?: string }>;
  }
) {
  return apiRequest<{ profile: UserProfile; message: string }>(settings, "/profile", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function getAssistantRuntimeProfile(settings: AppSettings) {
  return apiRequest<AssistantRuntimeProfile>(settings, "/assistant/runtime/profile");
}

export function saveAssistantRuntimeProfile(
  settings: AppSettings,
  payload: {
    assistant_name?: string;
    role_summary?: string;
    tone?: string;
    avatar_path?: string;
    soul_notes?: string;
    tools_notes?: string;
    heartbeat_extra_checks?: string[];
  }
) {
  return apiRequest<{ profile: AssistantRuntimeProfile; message: string; workspace: AssistantRuntimeWorkspaceStatus }>(
    settings,
    "/assistant/runtime/profile",
    {
      method: "PUT",
      body: JSON.stringify(payload),
    }
  );
}

export function getAssistantRuntimeWorkspace(settings: AppSettings) {
  return apiRequest<AssistantRuntimeWorkspaceStatus>(settings, "/assistant/runtime/workspace");
}

export function getTelemetryHealth(settings: AppSettings) {
  return apiRequest<TelemetryHealth>(settings, "/telemetry/health");
}

export function getAssistantToolsStatus(settings: AppSettings) {
  return apiRequest<{ items: AssistantToolStatus[]; generated_from: string }>(settings, "/assistant/tools/status");
}

export function getAssistantApprovals(settings: AppSettings) {
  return apiRequest<{ items: AssistantApproval[]; generated_from: string }>(settings, "/assistant/approvals");
}

export function approveAssistantApproval(settings: AppSettings, approvalId: string, payload: { note?: string } = {}) {
  return apiRequest(settings, `/assistant/approvals/${approvalId}/approve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function rejectAssistantApproval(settings: AppSettings, approvalId: string, payload: { note?: string } = {}) {
  return apiRequest(settings, `/assistant/approvals/${approvalId}/reject`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAssistantHome(settings: AppSettings) {
  return apiRequest<AssistantHomeResponse>(settings, "/assistant/home");
}

export function getAssistantThread(
  settings: AppSettings,
  params: { limit?: number; before_id?: number } = {},
) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.before_id) qs.set("before_id", String(params.before_id));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<AssistantThreadResponse>(settings, `/assistant/thread${suffix}`);
}

export function postAssistantThreadMessage(
  settings: AppSettings,
  payload: { content: string; matter_id?: number; source_refs?: Array<Record<string, unknown>> }
) {
  return apiRequest<AssistantThreadResponse>(settings, "/assistant/thread/messages", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function resetAssistantThread(settings: AppSettings) {
  return apiRequest<AssistantThreadResponse>(settings, "/assistant/thread/reset", {
    method: "POST"
  });
}

export function getWorkspaceOverview(settings: AppSettings) {
  return apiRequest<WorkspaceOverviewResponse>(settings, "/workspace");
}

export function saveWorkspaceRoot(settings: AppSettings, payload: { root_path: string; display_name?: string }) {
  return apiRequest<{ workspace: WorkspaceRoot; message: string }>(settings, "/workspace", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function runWorkspaceScan(settings: AppSettings, payload: { full_rescan?: boolean; extensions?: string[] } = {}) {
  return apiRequest<{
    workspace: WorkspaceRoot;
    job: WorkspaceScanJob;
    stats: { files_seen: number; files_indexed: number; files_skipped: number; files_failed: number };
    message: string;
  }>(settings, "/workspace/scan", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listWorkspaceScanJobs(settings: AppSettings) {
  return apiRequest<{ configured: boolean; workspace_root_id?: number; items: WorkspaceScanJob[] }>(settings, "/workspace/scan-jobs");
}

export function listWorkspaceDocuments(
  settings: AppSettings,
  filters: { q?: string; extension?: string; status?: string; path_prefix?: string } = {}
) {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.extension) params.set("extension", filters.extension);
  if (filters.status) params.set("status", filters.status);
  if (filters.path_prefix) params.set("path_prefix", filters.path_prefix);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<{ configured: boolean; workspace_root_id?: number; items: WorkspaceDocument[] }>(settings, `/workspace/documents${suffix}`);
}

export function getWorkspaceDocument(settings: AppSettings, documentId: number) {
  return apiRequest<WorkspaceDocument>(settings, `/workspace/documents/${documentId}`);
}

export function getWorkspaceDocumentChunks(settings: AppSettings, documentId: number) {
  return apiRequest<{ document_id: number; items: WorkspaceChunk[] }>(settings, `/workspace/documents/${documentId}/chunks`);
}

export function searchWorkspace(
  settings: AppSettings,
  payload: { query: string; limit?: number; path_prefix?: string; extensions?: string[] }
) {
  return apiRequest<WorkspaceSearchResponse>(settings, "/workspace/search", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function findSimilarWorkspaceDocuments(
  settings: AppSettings,
  payload: { document_id?: number; query?: string; limit?: number; path_prefix?: string }
) {
  return apiRequest<SimilarDocumentsResponse>(settings, "/workspace/similar-documents", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function attachWorkspaceDocumentToMatter(settings: AppSettings, matterId: number, workspaceDocumentId: number) {
  return apiRequest<MatterWorkspaceDocumentLink>(settings, `/matters/${matterId}/documents/attach-from-workspace`, {
    method: "POST",
    body: JSON.stringify({ workspace_document_id: workspaceDocumentId })
  });
}

export function listMatterWorkspaceDocuments(settings: AppSettings, matterId: number) {
  return apiRequest<{ matter_id: number; items: MatterWorkspaceDocumentLink[] }>(settings, `/matters/${matterId}/workspace-documents`);
}

export function listMatters(settings: AppSettings) {
  return apiRequest<{ items: Matter[] }>(settings, "/matters");
}

export function createMatter(
  settings: AppSettings,
  payload: { title: string; reference_code?: string; practice_area?: string; client_name?: string; summary?: string }
) {
  return apiRequest<Matter>(settings, "/matters", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getMatter(settings: AppSettings, matterId: number) {
  return apiRequest<Matter>(settings, `/matters/${matterId}`);
}

export function getMatterSummary(settings: AppSettings, matterId: number) {
  return apiRequest<MatterSummary>(settings, `/matters/${matterId}/summary`);
}

export function listMatterDocuments(settings: AppSettings, matterId: number) {
  return apiRequest<{ items: MatterDocument[] }>(settings, `/matters/${matterId}/documents`);
}

export function getMatterDocument(settings: AppSettings, matterId: number, documentId: number) {
  return apiRequest<MatterDocument>(settings, `/matters/${matterId}/documents/${documentId}`);
}

export function uploadMatterDocument(
  settings: AppSettings,
  matterId: number,
  payload: { file: File; displayName: string; sourceType: string; sourceRef?: string }
) {
  const formData = new FormData();
  formData.append("file", payload.file);
  formData.append("display_name", payload.displayName);
  formData.append("source_type", payload.sourceType);
  if (payload.sourceRef) {
    formData.append("source_ref", payload.sourceRef);
  }
  return apiRequest<{
    document: MatterDocument;
    job: IngestionJob;
    chunk_count: number;
  }>(settings, `/matters/${matterId}/documents`, {
    method: "POST",
    body: formData
  });
}

export function listMatterIngestionJobs(settings: AppSettings, matterId: number) {
  return apiRequest<{ items: IngestionJob[] }>(settings, `/matters/${matterId}/ingestion-jobs`);
}

export function searchMatter(
  settings: AppSettings,
  matterId: number,
  payload: {
    query: string;
    limit?: number;
    document_ids?: number[];
    source_types?: string[];
    filename_contains?: string;
  }
) {
  return apiRequest<SearchResponse>(settings, `/matters/${matterId}/search`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listMatterTasks(settings: AppSettings, matterId: number) {
  return apiRequest<{ items: Task[] }>(settings, `/matters/${matterId}/tasks`);
}

export function createMatterTask(
  settings: AppSettings,
  matterId: number,
  payload: {
    title: string;
    priority: string;
    due_at?: string;
    explanation?: string;
    origin_type?: string;
    recommended_by?: string;
  }
) {
  return apiRequest<Task>(settings, "/tasks", {
    method: "POST",
    body: JSON.stringify({ ...payload, matter_id: matterId, origin_type: payload.origin_type || "manual" })
  });
}

export function getMatterTaskRecommendations(settings: AppSettings, matterId: number) {
  return apiRequest<TaskRecommendationsResponse>(settings, `/matters/${matterId}/task-recommendations`);
}

export function listMatterDrafts(settings: AppSettings, matterId: number) {
  return apiRequest<{ items: Draft[] }>(settings, `/matters/${matterId}/drafts`);
}

export function createMatterDraft(
  settings: AppSettings,
  matterId: number,
  payload: { draft_type: string; title: string; body: string; target_channel: string; to_contact?: string }
) {
  return apiRequest<Draft>(settings, `/matters/${matterId}/drafts`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function generateMatterDraft(
  settings: AppSettings,
  matterId: number,
  payload: { draft_type: string; target_channel: string; to_contact?: string; instructions?: string }
) {
  return apiRequest<GeneratedDraftResponse>(settings, `/matters/${matterId}/drafts/generate`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listMatterTimeline(settings: AppSettings, matterId: number) {
  return apiRequest<{ items: TimelineEvent[] }>(settings, `/matters/${matterId}/timeline`);
}

export function getMatterChronology(settings: AppSettings, matterId: number) {
  return apiRequest<ChronologyResponse>(settings, `/matters/${matterId}/chronology`);
}

export function getMatterRiskNotes(settings: AppSettings, matterId: number) {
  return apiRequest<RiskNotesResponse>(settings, `/matters/${matterId}/risk-notes`);
}

export function getMatterActivity(settings: AppSettings, matterId: number) {
  return apiRequest<ActivityResponse>(settings, `/matters/${matterId}/activity`);
}

export function getDocumentChunks(settings: AppSettings, documentId: number) {
  return apiRequest<{ items: DocumentChunk[] }>(settings, `/documents/${documentId}/chunks`);
}

export function getDocumentCitations(settings: AppSettings, documentId: number) {
  return apiRequest<{ items: Citation[] }>(settings, `/documents/${documentId}/citations`);
}

export function runLegacyAssistantQuery(settings: AppSettings, payload: { query: string; model_profile?: string }) {
  return apiRequest<{
    answer: string;
    ui_citations: Citation[];
    citation_quality?: { grade: string; score: number };
    generated_from?: string;
    ai_provider?: string | null;
    ai_model?: string | null;
  }>(settings, "/query", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getAssistantAgenda(settings: AppSettings) {
  return apiRequest<{ items: AssistantAgendaItem[]; generated_from: string }>(settings, "/assistant/agenda");
}

export function getAssistantCalendar(settings: AppSettings) {
  return apiRequest<AssistantCalendarResponse>(settings, "/assistant/calendar");
}

export function createAssistantCalendarEvent(
  settings: AppSettings,
  payload: {
    title: string;
    starts_at: string;
    ends_at?: string;
    location?: string;
    matter_id?: number;
    needs_preparation?: boolean;
    provider?: string;
    external_id?: string;
    status?: string;
    attendees?: string[];
    notes?: string;
    metadata?: Record<string, unknown>;
  }
) {
  return apiRequest<{ event: Record<string, unknown>; message: string }>(settings, "/assistant/calendar/events", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getAssistantInbox(settings: AppSettings) {
  return apiRequest<{ items: AssistantAgendaItem[]; generated_from: string }>(settings, "/assistant/inbox");
}

export function getAssistantSuggestedActions(settings: AppSettings) {
  return apiRequest<{ items: SuggestedAction[]; generated_from: string; manual_review_required: boolean }>(settings, "/assistant/suggested-actions");
}

export function generateAssistantAction(
  settings: AppSettings,
  payload: {
    action_type: string;
    matter_id?: number;
    title?: string;
    instructions?: string;
    target_channel?: string;
    to_contact?: string;
    source_refs?: Array<Record<string, unknown>>;
  }
) {
  return apiRequest<{
    action: SuggestedAction;
    draft: OutboundDraft;
    generated_from: string;
    manual_review_required: boolean;
    message: string;
  }>(settings, "/assistant/actions/generate", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function approveAssistantAction(settings: AppSettings, actionId: number, note?: string) {
  return apiRequest<{ action: SuggestedAction; draft?: OutboundDraft; dispatch_mode: string; message: string }>(settings, `/assistant/actions/${actionId}/approve`, {
    method: "POST",
    body: JSON.stringify({ note })
  });
}

export function dismissAssistantAction(settings: AppSettings, actionId: number, note?: string) {
  return apiRequest<{ action: SuggestedAction; message: string }>(settings, `/assistant/actions/${actionId}/dismiss`, {
    method: "POST",
    body: JSON.stringify({ note })
  });
}

export function listAssistantDrafts(settings: AppSettings) {
  return apiRequest<{ items: OutboundDraft[]; matter_drafts: Draft[]; generated_from: string }>(settings, "/assistant/drafts");
}

export function sendAssistantDraft(settings: AppSettings, draftId: number, note?: string) {
  return apiRequest<{ draft: OutboundDraft; message: string; dispatch_mode: string }>(settings, `/assistant/drafts/${draftId}/send`, {
    method: "POST",
    body: JSON.stringify({ note })
  });
}

export function getGoogleIntegrationStatus(settings: AppSettings) {
  return apiRequest<GoogleIntegrationStatus>(settings, "/integrations/google/status");
}

export function getTelegramIntegrationStatus(settings: AppSettings) {
  return apiRequest<TelegramIntegrationStatus>(settings, "/integrations/telegram/status");
}

// ── Matter Update & Notes ──────────────────────────────────────

export function updateMatter(
  settings: AppSettings,
  matterId: number,
  payload: {
    title?: string;
    reference_code?: string;
    practice_area?: string;
    status?: string;
    summary?: string;
    client_name?: string;
    lead_lawyer?: string;
  }
) {
  return apiRequest<Matter>(settings, `/matters/${matterId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function createMatterNote(
  settings: AppSettings,
  matterId: number,
  payload: { body: string; note_type: string; event_at?: string }
) {
  return apiRequest<MatterNote>(settings, `/matters/${matterId}/notes`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

// ── Global Task Management ─────────────────────────────────────

export function listAllTasks(settings: AppSettings, matterId?: number) {
  const suffix = matterId ? `?matter_id=${matterId}` : "";
  return apiRequest<{ items: Task[] }>(settings, `/tasks${suffix}`);
}

export function updateTaskStatus(settings: AppSettings, taskId: number, status: string) {
  return apiRequest<{ ok: boolean; task: Task }>(settings, "/tasks/update-status", {
    method: "POST",
    body: JSON.stringify({ task_id: taskId, status })
  });
}

export function updateTaskDue(settings: AppSettings, taskId: number, dueAt: string | null) {
  return apiRequest<{ ok: boolean; task: Task }>(settings, "/tasks/update-due", {
    method: "POST",
    body: JSON.stringify({ task_id: taskId, due_at: dueAt })
  });
}

export function completeTasksBulk(settings: AppSettings, taskIds: number[]) {
  return apiRequest<{ ok: boolean; updated_count: number; requested_ids: number[] }>(settings, "/tasks/complete-bulk", {
    method: "POST",
    body: JSON.stringify({ task_ids: taskIds })
  });
}

// ── Email Drafts ───────────────────────────────────────────────

export function createEmailDraft(
  settings: AppSettings,
  payload: { to_email: string; subject: string; body: string; matter_id?: number }
) {
  return apiRequest<EmailDraft>(settings, "/email/drafts", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listEmailDrafts(settings: AppSettings) {
  return apiRequest<{ items: EmailDraft[] }>(settings, "/email/drafts");
}

export function previewEmailDraft(settings: AppSettings, draftId: number) {
  return apiRequest<EmailDraftPreview>(settings, `/email/drafts/${draftId}/preview`);
}

export function emailDraftHistory(settings: AppSettings, draftId: number) {
  return apiRequest<{ draft: EmailDraft; events: EmailDraftEvent[] }>(settings, `/email/drafts/${draftId}/history`);
}

export function approveEmailDraft(settings: AppSettings, draftId: number) {
  return apiRequest<{ status: string; draft: EmailDraft; dispatch: Record<string, string> }>(settings, "/email/approve", {
    method: "POST",
    body: JSON.stringify({ draft_id: draftId })
  });
}

export function retractEmailDraft(settings: AppSettings, draftId: number, reason?: string) {
  return apiRequest<{ status: string; draft: EmailDraft }>(settings, "/email/retract", {
    method: "POST",
    body: JSON.stringify({ draft_id: draftId, reason })
  });
}

// ── Background Query Jobs ──────────────────────────────────────

export function createQueryJob(
  settings: AppSettings,
  payload: { query: string; model_profile?: string; continue_in_background?: boolean }
) {
  return apiRequest<QueryJob>(settings, "/query/jobs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listQueryJobs(settings: AppSettings, limit = 20) {
  return apiRequest<{ items: QueryJob[]; stats: Record<string, number> }>(settings, `/query/jobs?limit=${limit}`);
}

export function getQueryJobStatus(settings: AppSettings, jobId: number | string) {
  return apiRequest<QueryJob>(settings, `/query/jobs/${jobId}`);
}

export function cancelQueryJob(settings: AppSettings, jobId: number | string) {
  return apiRequest<{ ok: boolean; job: QueryJob }>(settings, `/query/jobs/${jobId}/cancel`, {
    method: "POST"
  });
}

export function ackQueryJobToast(settings: AppSettings, jobId: number | string) {
  return apiRequest<{ ok: boolean }>(settings, `/query/jobs/${jobId}/ack-toast`, {
    method: "POST"
  });
}

// ── Social Media Monitoring ────────────────────────────────────

export function ingestSocialEvent(
  settings: AppSettings,
  payload: { source: string; handle: string; content: string }
) {
  return apiRequest<{ event: SocialEvent; mode: string }>(settings, "/social/ingest", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listSocialEvents(settings: AppSettings, limit = 20) {
  return apiRequest<{ items: SocialEvent[]; read_only: boolean }>(settings, `/social/events?limit=${limit}`);
}

// ── Citation Quality Review ────────────────────────────────────

export function reviewCitations(settings: AppSettings, payload: { answer: string }) {
  return apiRequest<CitationReviewResponse>(settings, "/citations/review", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
