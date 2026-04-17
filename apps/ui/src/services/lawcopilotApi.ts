import type { AppSettings } from "../app/AppContext";
import type {
  ActivityResponse,
  AgentRun,
  AgentRunEvent,
  AgentToolCatalogItem,
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
  IntegrationActionResponse,
  IntegrationCatalogResponse,
  IntegrationConnectionDetail,
  IntegrationDispatchResponse,
  IntegrationEventsResponse,
  IntegrationMutationResponse,
  IntegrationOAuthStartResponse,
  IntegrationPreviewResponse,
  IntegrationSyncResponse,
  IntegrationValidationResponse,
  IngestionJob,
  Matter,
  MatterNote,
  MatterSummary,
  MatterDocument,
  MatterWorkspaceDocumentLink,
  MemoryExplorerGraphResponse,
  MemoryExplorerHealthResponse,
  MemoryExplorerPageDetail,
  MemoryExplorerPagesResponse,
  MemoryExplorerTimelineResponse,
  ModelProfilesResponse,
  QueryJob,
  GoogleDriveFile,
  OutlookIntegrationStatus,
  PersonalModelFact,
  PersonalModelOverview,
  ProfileReconciliationSummary,
  PersonalModelRetrievalPreview,
  PersonalModelSession,
  PersonalModelSuggestion,
  RiskNotesResponse,
  SearchResponse,
  SimilarDocumentsResponse,
  SocialEvent,
  SuggestedAction,
  Task,
  AssistantAgendaItem,
  AssistantHomeResponse,
  AssistantThreadResponse,
  AssistantThreadStarredMessagesResponse,
  AssistantThreadListResponse,
  AssistantThreadStreamEvent,
  AssistantCalendarResponse,
  AssistantCoreStatus,
  AssistantCoreBlueprint,
  ChannelMemoryState,
  ChannelMemoryStateUpdateResponse,
  AssistantRuntimeProfile,
  AssistantRuntimeWorkspaceStatus,
  AssistantContactProfilesResponse,
  AssistantShareDraftCreateRequest,
  AssistantShareDraftCreateResponse,
  AssistantApproval,
  AssistantOnboardingState,
  AssistantToolStatus,
  TelemetryHealth,
  TelemetryPilotSummary,
  TelegramIntegrationStatus,
  WhatsAppIntegrationStatus,
  LinkedInIntegrationStatus,
  TaskRecommendationsResponse,
  TimelineEvent,
  OutboundDraft,
  UserProfile,
  WorkspaceChunk,
  WorkspaceDocument,
  WorkspaceOverviewResponse,
  WorkspaceRoot,
  WorkspaceScanJob,
  WorkspaceSearchResponse,
  XIntegrationStatus
} from "../types/domain";
import { apiRequest, streamApiRequest } from "./apiClient";

export function getHealth(settings: AppSettings) {
  return apiRequest<Health>(settings, "/health");
}

export function getIntegrationCatalog(settings: AppSettings, params: { query?: string; category?: string } = {}) {
  const qs = new URLSearchParams();
  if (params.query) qs.set("query", params.query);
  if (params.category) qs.set("category", params.category);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<IntegrationCatalogResponse>(settings, `/integrations/catalog${suffix}`);
}

export function getIntegrationConnectionDetail(settings: AppSettings, connectionId: number) {
  return apiRequest<IntegrationConnectionDetail>(settings, `/integrations/connections/${connectionId}`);
}

export function previewIntegrationConnection(
  settings: AppSettings,
  payload: {
    connector_id: string;
    connection_id?: number;
    display_name?: string;
    access_level: "read_only" | "read_write" | "admin_like";
    enabled: boolean;
    mock_mode: boolean;
    scopes?: string[];
    config: Record<string, unknown>;
    secrets: Record<string, unknown>;
  }
) {
  return apiRequest<IntegrationPreviewResponse>(settings, "/integrations/connections/preview", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function saveIntegrationConnection(
  settings: AppSettings,
  payload: {
    connector_id: string;
    connection_id?: number;
    display_name?: string;
    access_level: "read_only" | "read_write" | "admin_like";
    enabled: boolean;
    mock_mode: boolean;
    scopes?: string[];
    config: Record<string, unknown>;
    secrets: Record<string, unknown>;
  }
) {
  return apiRequest<IntegrationMutationResponse>(settings, "/integrations/connections", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function validateIntegrationConnection(settings: AppSettings, connectionId: number) {
  return apiRequest<IntegrationValidationResponse>(settings, `/integrations/connections/${connectionId}/validate`, {
    method: "POST",
  });
}

export function syncIntegrationConnection(settings: AppSettings, connectionId: number) {
  return apiRequest<IntegrationSyncResponse>(settings, `/integrations/connections/${connectionId}/sync`, {
    method: "POST",
  });
}

export function scheduleIntegrationSync(
  settings: AppSettings,
  connectionId: number,
  payload: { mode?: string; trigger_type?: string; run_now?: boolean; force?: boolean }
) {
  return apiRequest<IntegrationSyncResponse>(settings, `/integrations/connections/${connectionId}/sync/schedule`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function dispatchIntegrationSyncJobs(settings: AppSettings, payload: { limit: number }) {
  return apiRequest<IntegrationDispatchResponse>(settings, "/integrations/sync/dispatch", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function disconnectIntegrationConnection(settings: AppSettings, connectionId: number) {
  return apiRequest<IntegrationMutationResponse>(settings, `/integrations/connections/${connectionId}`, {
    method: "DELETE",
  });
}

export function startIntegrationOAuth(
  settings: AppSettings,
  connectionId: number,
  payload: { redirect_uri?: string; requested_scopes?: string[] }
) {
  return apiRequest<IntegrationOAuthStartResponse>(settings, `/integrations/connections/${connectionId}/oauth/start`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function completeIntegrationOAuthCallback(
  settings: AppSettings,
  payload: { state: string; code?: string; error?: string }
) {
  return apiRequest<IntegrationMutationResponse>(settings, "/integrations/oauth/callback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function refreshIntegrationCredentials(settings: AppSettings, connectionId: number) {
  return apiRequest<IntegrationMutationResponse>(settings, `/integrations/connections/${connectionId}/refresh`, {
    method: "POST",
  });
}

export function revokeIntegrationConnection(settings: AppSettings, connectionId: number) {
  return apiRequest<IntegrationMutationResponse>(settings, `/integrations/connections/${connectionId}/revoke`, {
    method: "POST",
  });
}

export function reconnectIntegrationConnection(settings: AppSettings, connectionId: number) {
  return apiRequest<IntegrationMutationResponse>(settings, `/integrations/connections/${connectionId}/reconnect`, {
    method: "POST",
  });
}

export function healthCheckIntegrationConnection(settings: AppSettings, connectionId: number) {
  return apiRequest<IntegrationValidationResponse>(settings, `/integrations/connections/${connectionId}/health`, {
    method: "POST",
  });
}

export function updateIntegrationSafetySettings(
  settings: AppSettings,
  connectionId: number,
  payload: {
    read_enabled?: boolean;
    write_enabled?: boolean;
    delete_enabled?: boolean;
    require_confirmation_for_write?: boolean;
    require_confirmation_for_delete?: boolean;
  }
) {
  return apiRequest<IntegrationMutationResponse>(settings, `/integrations/connections/${connectionId}/safety`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getIntegrationEvents(settings: AppSettings, params: { connection_id?: number; limit?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.connection_id) qs.set("connection_id", String(params.connection_id));
  if (params.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<IntegrationEventsResponse>(settings, `/integrations/events${suffix}`);
}

export function runIntegrationAction(
  settings: AppSettings,
  connectionId: number,
  actionKey: string,
  payload: { input: Record<string, unknown>; confirmed?: boolean }
) {
  return apiRequest<IntegrationActionResponse>(settings, `/integrations/connections/${connectionId}/actions/${actionKey}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
    favorite_color?: string;
    food_preferences?: string;
    transport_preference?: string;
    weather_preference?: string;
    travel_preferences?: string;
    home_base?: string;
    current_location?: string;
    location_preferences?: string;
    maps_preference?: string;
    prayer_notifications_enabled?: boolean;
    prayer_habit_notes?: string;
    communication_style?: string;
    assistant_notes?: string;
    important_dates?: Array<{ label: string; date: string; recurring_annually: boolean; notes?: string }>;
    related_profiles?: Array<{
      id?: string;
      name: string;
      relationship?: string;
      closeness?: number;
      preferences?: string;
      notes?: string;
      important_dates?: Array<{ label: string; date: string; recurring_annually: boolean; notes?: string }>;
    }>;
    contact_profile_overrides?: Array<{
      contact_id: string;
      description: string;
      updated_at?: string;
    }>;
    inbox_watch_rules?: Array<{
      id?: string;
      label: string;
      match_type: "person" | "group";
      match_value: string;
      channels?: string[];
    }>;
    inbox_keyword_rules?: Array<{
      id?: string;
      keyword: string;
      label?: string;
      channels?: string[];
    }>;
    inbox_block_rules?: Array<{
      id?: string;
      label: string;
      match_type: "person" | "group";
      match_value: string;
      channels?: string[];
      duration_kind: "day" | "month" | "forever";
      starts_at?: string;
      expires_at?: string;
    }>;
    source_preference_rules?: Array<{
      id?: string;
      label?: string;
      task_kind: string;
      policy_mode: "prefer" | "restrict";
      preferred_domains?: string[];
      preferred_links?: string[];
      preferred_providers?: string[];
      note?: string;
    }>;
  }
) {
  return apiRequest<{ profile: UserProfile; message: string; profile_reconciliation?: ProfileReconciliationSummary | null }>(settings, "/profile", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function getAssistantContactProfiles(settings: AppSettings) {
  return apiRequest<AssistantContactProfilesResponse>(settings, "/assistant/contact-profiles");
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
    assistant_forms?: Array<Record<string, unknown>>;
    behavior_contract?: Record<string, unknown>;
    evolution_history?: Array<Record<string, unknown>>;
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

export function getAssistantRuntimeCore(settings: AppSettings) {
  return apiRequest<AssistantCoreStatus>(settings, "/assistant/runtime/core");
}

export function buildAssistantRuntimeBlueprint(settings: AppSettings, payload: { description: string }) {
  return apiRequest<AssistantCoreBlueprint>(settings, "/assistant/runtime/core/blueprint", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAssistantRuntimeWorkspace(settings: AppSettings) {
  return apiRequest<AssistantRuntimeWorkspaceStatus>(settings, "/assistant/runtime/workspace");
}

export function getAssistantOnboardingState(settings: AppSettings) {
  return apiRequest<AssistantOnboardingState>(settings, "/assistant/onboarding/state");
}

export function getTelemetryHealth(settings: AppSettings) {
  return apiRequest<TelemetryHealth>(settings, "/telemetry/health");
}

export function getTelemetryPilotSummary(settings: AppSettings) {
  return apiRequest<TelemetryPilotSummary>(settings, "/telemetry/pilot-summary");
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

export function getAssistantConnectorSyncStatus(settings: AppSettings) {
  return apiRequest(settings, "/assistant/connectors/sync-status");
}

export function runAssistantConnectorSync(
  settings: AppSettings,
  payload: { connector_names?: string[]; reason?: string; trigger?: string } = {},
) {
  return apiRequest(settings, "/assistant/connectors/sync", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function applyAssistantMemoryCorrection(
  settings: AppSettings,
  payload: {
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
  },
) {
  return apiRequest(settings, "/assistant/memory/corrections", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAssistantMemoryOverview(settings: AppSettings) {
  return apiRequest(settings, "/assistant/memory/overview");
}

export function getMemoryExplorerPages(settings: AppSettings) {
  return apiRequest<MemoryExplorerPagesResponse>(settings, "/memory/pages");
}

export function getMemoryExplorerPage(settings: AppSettings, pageId: string) {
  return apiRequest<MemoryExplorerPageDetail>(settings, `/memory/page/${encodeURIComponent(pageId)}`);
}

export function getMemoryExplorerGraph(settings: AppSettings, params: { limit?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<MemoryExplorerGraphResponse>(settings, `/memory/graph${suffix}`);
}

export function getMemoryExplorerTimeline(settings: AppSettings, params: { limit?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<MemoryExplorerTimelineResponse>(settings, `/memory/timeline${suffix}`);
}

export function getMemoryExplorerHealth(settings: AppSettings) {
  return apiRequest<MemoryExplorerHealthResponse>(settings, "/memory/health");
}

export function editMemoryExplorerRecord(
  settings: AppSettings,
  payload: {
    action: "correct" | "reduce_confidence" | "suppress_recommendation" | "boost_proactivity";
    page_key?: string;
    target_record_id?: string;
    key?: string;
    corrected_summary?: string;
    scope?: string;
    note?: string;
    recommendation_kind?: string;
    topic?: string;
    source_refs?: Array<Record<string, unknown> | string>;
  },
) {
  return apiRequest(settings, "/memory/edit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function forgetMemoryExplorerRecord(
  settings: AppSettings,
  payload: {
    page_key?: string;
    target_record_id: string;
    note?: string;
    source_refs?: Array<Record<string, unknown> | string>;
  },
) {
  return apiRequest(settings, "/memory/forget", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function changeMemoryExplorerScope(
  settings: AppSettings,
  payload: {
    page_key?: string;
    target_record_id: string;
    scope: string;
    note?: string;
    source_refs?: Array<Record<string, unknown> | string>;
  },
) {
  return apiRequest(settings, "/memory/change-scope", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPersonalModelOverview(settings: AppSettings) {
  return apiRequest<PersonalModelOverview>(settings, "/assistant/personal-model");
}

export function startPersonalModelInterview(
  settings: AppSettings,
  payload: { module_keys?: string[]; scope?: string; source?: string } = {},
) {
  return apiRequest<{ session: PersonalModelSession; overview: PersonalModelOverview }>(
    settings,
    "/assistant/personal-model/interviews/start",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function answerPersonalModelInterview(
  settings: AppSettings,
  sessionId: string,
  payload: { answer_text: string; choice_value?: string; answer_kind?: "text" | "choice" | "voice_transcript" },
) {
  return apiRequest<{
    session: PersonalModelSession;
    raw_entry: Record<string, unknown>;
    stored_facts: PersonalModelFact[];
    next_question?: Record<string, unknown> | null;
    profile_summary: PersonalModelOverview["profile_summary"];
    profile_reconciliation?: ProfileReconciliationSummary | null;
    overview: PersonalModelOverview;
  }>(settings, `/assistant/personal-model/interviews/${encodeURIComponent(sessionId)}/answer`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function pausePersonalModelInterview(settings: AppSettings, sessionId: string) {
  return apiRequest<{ session: PersonalModelSession; overview: PersonalModelOverview }>(
    settings,
    `/assistant/personal-model/interviews/${encodeURIComponent(sessionId)}/pause`,
    { method: "POST" },
  );
}

export function resumePersonalModelInterview(settings: AppSettings, sessionId: string) {
  return apiRequest<{ session: PersonalModelSession; overview: PersonalModelOverview }>(
    settings,
    `/assistant/personal-model/interviews/${encodeURIComponent(sessionId)}/resume`,
    { method: "POST" },
  );
}

export function skipPersonalModelInterviewQuestion(settings: AppSettings, sessionId: string) {
  return apiRequest<{ session: PersonalModelSession; overview: PersonalModelOverview }>(
    settings,
    `/assistant/personal-model/interviews/${encodeURIComponent(sessionId)}/skip`,
    { method: "POST" },
  );
}

export function updatePersonalModelFact(
  settings: AppSettings,
  factId: string,
  payload: {
    value_text?: string;
    scope?: string;
    enabled?: boolean;
    never_use?: boolean;
    sensitive?: boolean;
    visibility?: string;
    confidence?: number;
    note?: string;
  },
) {
  return apiRequest<{ fact: PersonalModelFact; overview: PersonalModelOverview }>(
    settings,
    `/assistant/personal-model/facts/${encodeURIComponent(factId)}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export function deletePersonalModelFact(settings: AppSettings, factId: string) {
  return apiRequest<{ deleted: boolean; fact_id: string; overview: PersonalModelOverview }>(
    settings,
    `/assistant/personal-model/facts/${encodeURIComponent(factId)}`,
    { method: "DELETE" },
  );
}

export function reviewPersonalModelSuggestion(
  settings: AppSettings,
  suggestionId: string,
  payload: { decision: "accept" | "reject" },
) {
  return apiRequest<{ decision: string; fact?: PersonalModelFact; suggestion?: PersonalModelSuggestion; profile_reconciliation?: ProfileReconciliationSummary | null; overview: PersonalModelOverview }>(
    settings,
    `/assistant/personal-model/suggestions/${encodeURIComponent(suggestionId)}/review`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function previewPersonalModelRetrieval(
  settings: AppSettings,
  payload: { query: string; scopes?: string[]; limit?: number },
) {
  return apiRequest<PersonalModelRetrievalPreview>(settings, "/assistant/personal-model/retrieval/preview", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAssistantCoachingDashboard(settings: AppSettings) {
  return apiRequest(settings, "/assistant/coaching");
}

export function upsertAssistantCoachingGoal(
  settings: AppSettings,
  payload: {
    goal_id?: string;
    title: string;
    summary?: string;
    cadence?: "daily" | "weekly" | "flexible" | "one_time";
    target_value?: number;
    unit?: string;
    scope?: string;
    sensitivity?: string;
    reminder_time?: string;
    preferred_days?: string[];
    target_date?: string;
    allow_desktop_notifications?: boolean;
    note?: string;
    source_refs?: Array<Record<string, unknown> | string>;
  },
) {
  return apiRequest(settings, "/assistant/coaching/goals", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function logAssistantCoachingProgress(
  settings: AppSettings,
  goalId: string,
  payload: {
    amount?: number;
    note?: string;
    completed?: boolean;
    happened_at?: string;
  },
) {
  return apiRequest(settings, `/assistant/coaching/goals/${encodeURIComponent(goalId)}/progress`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAssistantLocationContext(settings: AppSettings) {
  return apiRequest(settings, "/assistant/location/context");
}

export function updateAssistantLocationContext(
  settings: AppSettings,
  payload: {
    current_place?: Record<string, unknown>;
    recent_places?: Array<Record<string, unknown>>;
    nearby_categories?: string[];
    observed_at?: string;
    source?: string;
    scope?: string;
    sensitivity?: string;
    source_ref?: string;
    provider?: string;
    provider_mode?: string;
    provider_status?: string;
    capture_mode?: string;
    permission_state?: string;
    privacy_mode?: boolean;
    capture_failure_reason?: string;
    persist_raw?: boolean;
  },
) {
  return apiRequest(settings, "/assistant/location/context", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function evaluateAssistantTriggers(
  settings: AppSettings,
  payload: { forced_types?: string[]; limit?: number; include_suppressed?: boolean; persist?: boolean } = {},
) {
  return apiRequest(settings, "/assistant/triggers/evaluate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAssistantOrchestrationStatus(settings: AppSettings) {
  return apiRequest(settings, "/assistant/orchestration/status");
}

export function runAssistantOrchestration(
  settings: AppSettings,
  payload: { job_names?: string[]; reason?: string; force?: boolean } = {},
) {
  return apiRequest(settings, "/assistant/orchestration/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAgentTools(settings: AppSettings) {
  return apiRequest<{ items: AgentToolCatalogItem[] }>(settings, "/tools");
}

export function createAgentRun(
  settings: AppSettings,
  payload: { goal: string; title?: string; matter_id?: number; thread_id?: number; source_refs?: Array<Record<string, unknown>> },
) {
  return apiRequest<AgentRun>(settings, "/agent/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listAgentRuns(settings: AppSettings, params: { limit?: number; thread_id?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.thread_id) qs.set("thread_id", String(params.thread_id));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<{ items: AgentRun[] }>(settings, `/agent/runs${suffix}`);
}

export function getAgentRun(settings: AppSettings, runId: number | string) {
  return apiRequest<AgentRun>(settings, `/agent/runs/${runId}`);
}

export function getAgentRunEvents(settings: AppSettings, runId: number | string) {
  return apiRequest<{ items: AgentRunEvent[] }>(settings, `/agent/runs/${runId}/events`);
}

export function getAssistantThread(
  settings: AppSettings,
  params: { limit?: number; before_id?: number; thread_id?: number } = {},
) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.before_id) qs.set("before_id", String(params.before_id));
  if (params.thread_id) qs.set("thread_id", String(params.thread_id));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<AssistantThreadResponse>(settings, `/assistant/thread${suffix}`);
}

export function listAssistantThreadStarredMessages(
  settings: AppSettings,
  threadId: number,
  params: { limit?: number } = {},
) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<AssistantThreadStarredMessagesResponse>(settings, `/assistant/threads/${threadId}/starred-messages${suffix}`);
}

export function listAssistantStarredMessages(
  settings: AppSettings,
  params: { limit?: number } = {},
) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<AssistantThreadStarredMessagesResponse>(settings, `/assistant/starred-messages${suffix}`);
}

export function listAssistantThreads(settings: AppSettings, params: { limit?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiRequest<AssistantThreadListResponse>(settings, `/assistant/threads${suffix}`);
}

export function createAssistantThread(settings: AppSettings, payload: { title?: string } = {}) {
  return apiRequest<{ thread: AssistantThreadResponse["thread"]; generated_from?: string }>(settings, "/assistant/threads", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAssistantThread(settings: AppSettings, threadId: number, payload: { title: string }) {
  return apiRequest<{ thread: AssistantThreadResponse["thread"]; generated_from?: string }>(settings, `/assistant/threads/${threadId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAssistantThread(settings: AppSettings, threadId: number) {
  return apiRequest<{ deleted_thread_id: number; selected_thread_id?: number | null; items: AssistantThreadListResponse["items"]; generated_from?: string }>(
    settings,
    `/assistant/threads/${threadId}`,
    {
      method: "DELETE",
    },
  );
}

export function analyzeAssistantAttachment(
  settings: AppSettings,
  payload: { file: File; purpose?: "voice_transcript" | string }
) {
  const formData = new FormData();
  formData.append("file", payload.file);
  if (payload.purpose) {
    formData.append("purpose", payload.purpose);
  }
  return apiRequest<{
    source_ref: Record<string, unknown>;
    analysis_text?: string;
    ai_provider?: string | null;
    ai_model?: string | null;
    generated_from?: string;
  }>(settings, "/assistant/attachments/analyze", {
    method: "POST",
    body: formData
  });
}

export function postAssistantThreadMessage(
  settings: AppSettings,
  payload: { content: string; thread_id?: number; edit_message_id?: number; matter_id?: number; source_refs?: Array<Record<string, unknown>> }
) {
  return apiRequest<AssistantThreadResponse>(settings, "/assistant/thread/messages", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateAssistantThreadMessageStar(
  settings: AppSettings,
  messageId: number,
  payload: { starred: boolean },
) {
  return apiRequest<{ message: AssistantThreadResponse["messages"][number]; generated_from?: string }>(
    settings,
    `/assistant/thread/messages/${messageId}/starred`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function updateAssistantThreadMessageFeedback(
  settings: AppSettings,
  messageId: number,
  payload: { feedback_value: "liked" | "disliked" | "none"; note?: string },
) {
  return apiRequest<{
    message: AssistantThreadResponse["messages"][number];
    learning?: Record<string, unknown> | null;
    assistant_runtime_profile?: AssistantRuntimeProfile;
    memory_overview?: Record<string, unknown>;
    connector_sync_status?: Record<string, unknown>;
    generated_from?: string;
  }>(
    settings,
    `/assistant/thread/messages/${messageId}/feedback`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function streamAssistantThreadMessage(
  settings: AppSettings,
  payload: { content: string; thread_id?: number; edit_message_id?: number; matter_id?: number; source_refs?: Array<Record<string, unknown>> },
  onEvent: (event: AssistantThreadStreamEvent) => void | Promise<void>,
  options: { signal?: AbortSignal } = {},
) {
  await streamApiRequest(
    settings,
    "/assistant/thread/messages/stream",
    {
      method: "POST",
      body: JSON.stringify(payload),
      signal: options.signal,
    },
    async (line) => {
      const event = JSON.parse(line) as AssistantThreadStreamEvent;
      await onEvent(event);
    },
  );
}

export function resetAssistantThread(settings: AppSettings) {
  return apiRequest<AssistantThreadResponse>(settings, "/assistant/thread/reset", {
    method: "POST"
  });
}

export function resetAssistantThreadById(settings: AppSettings, threadId: number) {
  return apiRequest<AssistantThreadResponse>(settings, `/assistant/thread/reset?thread_id=${threadId}`, {
    method: "POST",
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
    attachment_context?: string;
    analysis_available?: boolean;
    analysis_mode?: string;
    ai_provider?: string | null;
    ai_model?: string | null;
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

export function updateChannelMemoryState(
  settings: AppSettings,
  payload: {
    channel_type: "email_thread" | "whatsapp_message" | "telegram_message" | "x_post" | "x_message" | "instagram_message";
    record_id: number;
    memory_state: ChannelMemoryState;
    note?: string;
  }
) {
  return apiRequest<ChannelMemoryStateUpdateResponse>(settings, "/memory/channel-state", {
    method: "POST",
    body: JSON.stringify(payload),
  });
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

export function pauseAssistantAction(settings: AppSettings, actionId: number, note?: string) {
  return apiRequest<{ action: SuggestedAction; draft?: OutboundDraft; message: string }>(settings, `/assistant/actions/${actionId}/pause`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export function resumeAssistantAction(settings: AppSettings, actionId: number, note?: string) {
  return apiRequest<{ action: SuggestedAction; draft?: OutboundDraft; message: string }>(settings, `/assistant/actions/${actionId}/resume`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export function retryAssistantActionDispatch(settings: AppSettings, actionId: number, note?: string) {
  return apiRequest<{ action: SuggestedAction; draft?: OutboundDraft; message: string }>(settings, `/assistant/actions/${actionId}/retry-dispatch`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export function scheduleAssistantActionCompensation(settings: AppSettings, actionId: number, note?: string) {
  return apiRequest<{ action: SuggestedAction; draft?: OutboundDraft; message: string; compensation_action?: SuggestedAction | null; compensation_draft?: OutboundDraft | null }>(
    settings,
    `/assistant/actions/${actionId}/schedule-compensation`,
    {
      method: "POST",
      body: JSON.stringify({ note }),
    },
  );
}

export function listAssistantDrafts(settings: AppSettings) {
  return apiRequest<{ items: OutboundDraft[]; matter_drafts: Draft[]; generated_from: string }>(settings, "/assistant/drafts");
}

export function sendAssistantDraft(settings: AppSettings, draftId: number, note?: string) {
  return apiRequest<{ draft: OutboundDraft; action?: SuggestedAction | null; message: string; dispatch_mode: string }>(settings, `/assistant/drafts/${draftId}/send`, {
    method: "POST",
    body: JSON.stringify({ note })
  });
}

export function removeAssistantDraft(settings: AppSettings, draftId: number, note?: string) {
  return apiRequest<{ draft: OutboundDraft; action?: SuggestedAction | null; message: string }>(settings, `/assistant/drafts/${draftId}/remove`, {
    method: "POST",
    body: JSON.stringify({ note })
  });
}

export function createAssistantShareDraft(settings: AppSettings, payload: AssistantShareDraftCreateRequest) {
  return apiRequest<AssistantShareDraftCreateResponse>(settings, "/assistant/share-drafts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getGoogleIntegrationStatus(settings: AppSettings) {
  return apiRequest<GoogleIntegrationStatus>(settings, "/integrations/google/status");
}

export function listGoogleDriveFiles(settings: AppSettings, limit = 30) {
  return apiRequest<{ configured: boolean; connected: boolean; items: GoogleDriveFile[]; generated_from: string }>(
    settings,
    `/integrations/google/drive-files?limit=${Math.max(1, Math.min(limit, 100))}`
  );
}

export function getOutlookIntegrationStatus(settings: AppSettings) {
  return apiRequest<OutlookIntegrationStatus>(settings, "/integrations/outlook/status");
}

export function getTelegramIntegrationStatus(settings: AppSettings) {
  return apiRequest<TelegramIntegrationStatus>(settings, "/integrations/telegram/status");
}

export function getWhatsAppIntegrationStatus(settings: AppSettings) {
  return apiRequest<WhatsAppIntegrationStatus>(settings, "/integrations/whatsapp/status");
}

export function getXIntegrationStatus(settings: AppSettings) {
  return apiRequest<XIntegrationStatus>(settings, "/integrations/x/status");
}

export function getLinkedInIntegrationStatus(settings: AppSettings) {
  return apiRequest<LinkedInIntegrationStatus>(settings, "/integrations/linkedin/status");
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
