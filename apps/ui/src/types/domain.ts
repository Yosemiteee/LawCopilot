export type Health = {
  ok: boolean;
  service: string;
  version: string;
  app_name?: string;
  office_id: string;
  deployment_mode: string;
  default_model_profile?: string;
  release_channel?: string;
  environment?: string;
  desktop_shell?: string;
  connector_dry_run: boolean;
  provider_type?: string;
  provider_base_url?: string;
  provider_model?: string;
  provider_configured?: boolean;
  assistant_runtime_mode?: string;
  openclaw_runtime_enabled?: boolean;
  openclaw_workspace_ready?: boolean;
  openclaw_bootstrap_required?: boolean;
  openclaw_last_sync_at?: string | null;
  openclaw_curated_skill_count?: number;
  google_enabled?: boolean;
  google_configured?: boolean;
  google_account_label?: string;
  google_scopes?: string[];
  gmail_connected?: boolean;
  calendar_connected?: boolean;
  drive_connected?: boolean;
  telegram_enabled?: boolean;
  telegram_configured?: boolean;
  telegram_bot_username?: string;
  telegram_allowed_user_id?: string;
  rag_backend: string;
  workspace_configured?: boolean;
  workspace_root_name?: string | null;
  rag_runtime: {
    backend: string;
    mode: string;
    warning?: string | null;
  };
};

export type ModelProfilesResponse = {
  default: string;
  deployment_mode: string;
  default_model_profile?: string;
  office_id: string;
  profiles: Record<string, { provider?: string; model?: string; notes?: string; dataResidency?: string; policy?: string }>;
};

export type TelemetryHealth = {
  ok: boolean;
  app_name: string;
  version: string;
  release_channel: string;
  environment: string;
  deployment_mode: string;
  desktop_shell: string;
  office_id: string;
  structured_log_path: string;
  audit_log_path: string;
  db_path: string;
  connector_dry_run: boolean;
  provider_type?: string;
  provider_base_url?: string;
  provider_model?: string;
  provider_configured?: boolean;
  assistant_runtime_mode?: string;
  openclaw_runtime_enabled?: boolean;
  openclaw_workspace_ready?: boolean;
  openclaw_bootstrap_required?: boolean;
  openclaw_last_sync_at?: string | null;
  openclaw_curated_skill_count?: number;
  runtime_last_status?: string;
  runtime_last_task?: string;
  runtime_last_model?: string;
  runtime_last_provider?: string;
  google_enabled?: boolean;
  google_configured?: boolean;
  google_account_label?: string;
  google_scopes?: string[];
  gmail_connected?: boolean;
  calendar_connected?: boolean;
  connected_accounts?: ConnectedAccount[];
  telegram_enabled?: boolean;
  telegram_configured?: boolean;
  telegram_bot_username?: string;
  telegram_allowed_user_id?: string;
  recent_runtime_events?: Array<Record<string, unknown>>;
  workspace_configured?: boolean;
  workspace_root_name?: string | null;
  recent_events: Array<Record<string, unknown>>;
};

export type WorkspaceRoot = {
  id: number;
  office_id: string;
  display_name: string;
  root_path: string;
  root_path_hash: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type WorkspaceScanJob = {
  id: number;
  office_id: string;
  workspace_root_id: number;
  status: string;
  files_seen: number;
  files_indexed: number;
  files_skipped: number;
  files_failed: number;
  error?: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceDocument = {
  id: number;
  office_id: string;
  workspace_root_id: number;
  relative_path: string;
  display_name: string;
  extension: string;
  content_type?: string | null;
  size_bytes: number;
  mtime: number;
  checksum: string;
  parser_status: string;
  indexed_status: string;
  document_language: string;
  last_error?: string | null;
  root_path?: string;
  workspace_root_name?: string;
  created_at: string;
  updated_at: string;
};

export type GoogleDriveFile = {
  id: number;
  office_id: string;
  provider: string;
  external_id: string;
  name: string;
  mime_type?: string | null;
  web_view_link?: string | null;
  modified_at?: string | null;
  matter_id?: number | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceChunk = {
  id: number;
  workspace_document_id: number;
  office_id: string;
  workspace_root_id: number;
  chunk_index: number;
  text: string;
  token_count: number;
  display_name: string;
  relative_path: string;
  extension: string;
  metadata: {
    line_anchor?: string;
    page?: number;
    line_start?: number;
    line_end?: number;
    relative_path?: string;
  };
};

export type WorkspaceCitation = {
  workspace_document_id: number;
  scope: string;
  document_id?: number | null;
  document_name: string;
  matter_id?: number | null;
  chunk_id?: number | string | null;
  chunk_index?: number | null;
  excerpt: string;
  relevance_score: number;
  source_type: string;
  support_type: string;
  confidence: string;
  relative_path?: string | null;
  line_anchor?: string | null;
  page?: number | null;
  line_start?: number | null;
  line_end?: number | null;
};

export type WorkspaceSearchResponse = {
  answer: string;
  generated_from?: string;
  ai_provider?: string | null;
  ai_model?: string | null;
  support_level: string;
  manual_review_required: boolean;
  citation_count: number;
  source_coverage: number;
  attention_points: string[];
  missing_document_signals: string[];
  draft_suggestions: string[];
  citations: WorkspaceCitation[];
  related_documents: Array<{
    workspace_document_id: number;
    document_name: string;
    relative_path?: string | null;
    max_score: number;
    reason: string;
  }>;
  scope: string;
};

export type SimilarWorkspaceDocument = {
  workspace_document_id: number;
  belge_adi: string;
  goreli_yol?: string | null;
  benzerlik_puani: number;
  neden_benzer: string;
  klasor_baglami: string;
  skor_bilesenleri: {
    dosya_adi: number;
    icerik: number;
    belge_turu: number;
    checksum: number;
    klasor_baglami: number;
    hukuk_terimleri: number;
    genel_skor: number;
  };
  ortak_terimler: string[];
  destekleyici_pasajlar: WorkspaceCitation[];
  dikkat_notlari: string[];
  taslak_onerileri: string[];
  manuel_inceleme_gerekir: boolean;
  sinyaller: string[];
};

export type SimilarDocumentsResponse = {
  items: SimilarWorkspaceDocument[];
  explanation: string;
  generated_from?: string;
  ai_provider?: string | null;
  ai_model?: string | null;
  signals?: string[];
  top_terms: string[];
  manual_review_required: boolean;
};

export type WorkspaceOverviewResponse = {
  configured: boolean;
  workspace: WorkspaceRoot | null;
  documents: { items: WorkspaceDocument[]; count?: number };
  scan_jobs: { items: WorkspaceScanJob[] };
};

export type MatterWorkspaceDocumentLink = {
  id: number;
  matter_id: number;
  workspace_document_id: number;
  linked_by: string;
  linked_at: string;
  display_name: string;
  relative_path: string;
  extension: string;
  indexed_status: string;
  workspace_root_id?: number;
};

export type Matter = {
  id: number;
  office_id: string;
  title: string;
  reference_code?: string | null;
  practice_area?: string | null;
  status: string;
  summary?: string | null;
  client_name?: string | null;
  lead_lawyer?: string | null;
  opened_at?: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type MatterSummary = {
  matter: Matter;
  summary: string;
  counts: {
    notes: number;
    tasks: number;
    drafts: number;
  };
  latest_timeline: TimelineEvent[];
  generated_from: string;
  manual_review_required: boolean;
  ai_provider?: string | null;
  ai_model?: string | null;
};

export type MatterDocument = {
  id: number;
  matter_id: number;
  office_id: string;
  filename: string;
  display_name: string;
  content_type?: string | null;
  source_type: string;
  source_ref?: string | null;
  checksum: string;
  size_bytes: number;
  ingest_status: string;
  created_at: string;
  updated_at: string;
  chunk_count?: number;
};

export type IngestionJob = {
  id: number;
  office_id: string;
  matter_id: number;
  document_id: number;
  status: string;
  error?: string | null;
  created_at: string;
  updated_at: string;
  document_name?: string;
  filename?: string;
};

export type Citation = {
  index?: number;
  label?: string;
  document_id: number;
  document_name: string;
  matter_id: number;
  chunk_id?: number | string | null;
  chunk_index?: number | null;
  excerpt: string;
  relevance_score: number;
  source_type: string;
  support_type: string;
  confidence: string;
  line_anchor?: string | null;
  page?: number | null;
  line_start?: number | null;
  line_end?: number | null;
};

export type SearchResponse = {
  answer: string;
  model_profile: string;
  support_level: string;
  manual_review_required: boolean;
  citation_count: number;
  source_coverage: number;
  generated_from: string;
  ai_provider?: string | null;
  ai_model?: string | null;
  citations: Citation[];
  related_documents: Array<{
    document_id: number;
    document_name: string;
    matter_id: number;
    max_score: number;
    reason: string;
  }>;
  retrieval_summary: {
    scope: string;
    matter_id: number;
    document_count: number;
    citation_count: number;
    top_document?: string | null;
    warning?: string | null;
  };
};

export type Task = {
  id: number;
  office_id?: string;
  matter_id?: number | null;
  title: string;
  due_at?: string | null;
  priority: string;
  status: string;
  owner: string;
  origin_type?: string | null;
  origin_ref?: string | null;
  recommended_by?: string | null;
  explanation?: string | null;
  created_at: string;
};

export type Draft = {
  id: number;
  matter_id: number;
  office_id: string;
  draft_type: string;
  title: string;
  body: string;
  status: string;
  target_channel: string;
  to_contact?: string | null;
  source_context?: {
    documents?: string[];
    chronology?: string[];
    risk_notes?: string[];
    open_tasks?: string[];
  } | null;
  generated_from?: string | null;
  ai_provider?: string | null;
  ai_model?: string | null;
  manual_review_required?: boolean;
  created_by: string;
  approved_by?: string | null;
  created_at: string;
  updated_at: string;
};

export type ConnectedAccount = {
  id?: number;
  provider: string;
  account_label: string;
  status: string;
  scopes: string[];
  connected_at?: string | null;
  last_sync_at?: string | null;
  manual_review_required: boolean;
  metadata?: Record<string, unknown>;
};

export type ProfileImportantDate = {
  label: string;
  date: string;
  recurring_annually: boolean;
  notes?: string | null;
  next_occurrence?: string | null;
  days_until?: number | null;
};

export type RelatedProfile = {
  id?: string | null;
  name: string;
  relationship: string;
  preferences: string;
  notes: string;
  important_dates: ProfileImportantDate[];
};

export type UserProfile = {
  office_id: string;
  display_name: string;
  favorite_color: string;
  food_preferences: string;
  transport_preference: string;
  weather_preference: string;
  travel_preferences: string;
  communication_style: string;
  assistant_notes: string;
  important_dates: ProfileImportantDate[];
  related_profiles: RelatedProfile[];
  created_at?: string | null;
  updated_at?: string | null;
};

export type AssistantRuntimeProfile = {
  office_id: string;
  assistant_name: string;
  role_summary: string;
  tone: string;
  avatar_path: string;
  soul_notes: string;
  tools_notes: string;
  heartbeat_extra_checks: string[];
  created_at?: string | null;
  updated_at?: string | null;
};

export type AssistantOnboardingState = {
  complete: boolean;
  stage?: string;
  summary?: string;
  workspace_ready: boolean;
  provider_ready: boolean;
  model_ready?: boolean;
  assistant_ready: boolean;
  user_ready: boolean;
  blocked_by_setup?: boolean;
  provider_type?: string;
  provider_model?: string;
  workspace_root_name?: string | null;
  next_question?: string;
  interview_intro?: string;
  interview_topics?: string[];
  steps?: Array<{
    id: string;
    title: string;
    description: string;
    complete: boolean;
    action: string;
  }>;
  questions?: Array<{
    id: string;
    field: string;
    target: string;
    question: string;
    reason: string;
  }>;
  suggested_prompts?: string[];
  starter_prompts?: string[];
  profile?: {
    display_name?: string;
    favorite_color?: string;
    transport_preference?: string;
    communication_style?: string;
  };
  assistant_profile?: {
    assistant_name?: string;
    tone?: string;
    role_summary?: string;
  };
};

export type AssistantRuntimeWorkspaceFile = {
  name: string;
  path: string;
  exists: boolean;
  preview: string;
};

export type AssistantRuntimeWorkspaceSkill = {
  slug: string;
  title: string;
  summary: string;
  enabled: boolean;
  reason?: string | null;
};

export type AssistantRuntimeWorkspaceStatus = {
  enabled: boolean;
  workspace_ready: boolean;
  bootstrap_required: boolean;
  last_sync_at?: string | null;
  workspace_path?: string | null;
  curated_skill_count: number;
  curated_skills: AssistantRuntimeWorkspaceSkill[];
  files: AssistantRuntimeWorkspaceFile[];
  daily_log_path?: string | null;
};

export type AssistantAgendaItem = {
  id: string;
  kind: string;
  title: string;
  details?: string | null;
  priority: string;
  due_at?: string | null;
  source_type: string;
  source_ref?: string | null;
  matter_id?: number | null;
  recommended_action_ids?: Array<number | string>;
  manual_review_required: boolean;
};

export type AssistantCalendarItem = {
  id: string;
  kind: string;
  title: string;
  details?: string | null;
  starts_at: string;
  ends_at?: string | null;
  location?: string | null;
  source_type: string;
  source_ref?: string | null;
  matter_id?: number | null;
  priority?: string | null;
  all_day: boolean;
  needs_preparation: boolean;
  provider?: string | null;
  status?: string | null;
  attendees?: string[];
  metadata?: Record<string, unknown> | null;
};

export type AssistantCalendarResponse = {
  today: string;
  items: AssistantCalendarItem[];
  generated_from: string;
  google_connected: boolean;
};

export type SuggestedAction = {
  id: number;
  matter_id?: number | null;
  action_type: string;
  title: string;
  description?: string | null;
  rationale?: string | null;
  source_refs: Array<Record<string, unknown>>;
  target_channel?: string | null;
  draft_id?: number | null;
  status: string;
  dispatch_state?: string | null;
  dispatch_error?: string | null;
  external_message_id?: string | null;
  manual_review_required: boolean;
  created_at: string;
  updated_at: string;
};

export type AssistantToolStatus = {
  provider: string;
  account_label?: string | null;
  connected: boolean;
  status: string;
  scopes: string[];
  capabilities: string[];
  write_enabled: boolean;
  approval_required: boolean;
  connected_account?: ConnectedAccount | null;
};

export type AssistantApproval = {
  id: string;
  action_id?: number | null;
  draft_id?: number | null;
  status: string;
  title: string;
  action_type?: string | null;
  target_channel?: string | null;
  manual_review_required: boolean;
  approval_required: boolean;
  draft?: OutboundDraft | null;
  action?: SuggestedAction | null;
};

export type OutboundDraft = {
  id: number | string;
  matter_id?: number | null;
  matter_title?: string | null;
  draft_type: string;
  channel: string;
  to_contact?: string | null;
  subject?: string | null;
  body: string;
  source_context?: Record<string, unknown> | null;
  generated_from?: string | null;
  ai_model?: string | null;
  ai_provider?: string | null;
  approval_status: string;
  delivery_status: string;
  dispatch_state?: string | null;
  dispatch_error?: string | null;
  external_message_id?: string | null;
  last_dispatch_at?: string | null;
  created_by?: string;
  approved_by?: string | null;
  created_at: string;
  updated_at: string;
};

export type AssistantHomeResponse = {
  today_summary: string;
  display_name?: string;
  greeting_title?: string;
  greeting_message?: string;
  counts: {
    agenda: number;
    inbox: number;
    drafts_pending: number;
    calendar_today: number;
  };
  priority_items: Array<{
    id: string;
    title: string;
    details?: string | null;
    kind: string;
    priority: string;
    due_at?: string | null;
    source_type: string;
    source_ref?: string | null;
  }>;
  requires_setup: Array<{
    id: string;
    title: string;
    details: string;
    action: string;
  }>;
  proactive_suggestions?: Array<{
    id: string;
    kind: string;
    title: string;
    details: string;
    action_label?: string;
    prompt?: string;
    matter_id?: number | null;
    tool?: string | null;
    priority?: string;
  }>;
  connected_accounts: ConnectedAccount[];
  generated_from: string;
  onboarding?: AssistantOnboardingState;
};

export type AssistantThreadMessage = {
  id: number;
  thread_id: number;
  office_id: string;
  role: "user" | "assistant";
  content: string;
  linked_entities: Array<Record<string, unknown>>;
  tool_suggestions: Array<{ tool: string; label: string; reason: string }>;
  draft_preview?: OutboundDraft | Record<string, unknown> | null;
  source_context?: Record<string, unknown> | null;
  requires_approval: boolean;
  generated_from?: string | null;
  ai_provider?: string | null;
  ai_model?: string | null;
  created_at: string;
};

export type AssistantThreadResponse = {
  thread: {
    id: number;
    office_id: string;
    title: string;
    created_by: string;
    created_at: string;
    updated_at: string;
  };
  messages: AssistantThreadMessage[];
  has_more?: boolean;
  total_count?: number;
  assistant_summary?: string | null;
  generated_from?: string;
  tool_suggestions?: Array<{ tool: string; label: string; reason: string }>;
  linked_entities?: Array<Record<string, unknown>>;
  draft_preview?: OutboundDraft | Record<string, unknown> | null;
  requires_approval?: boolean;
  ai_provider?: string | null;
  ai_model?: string | null;
  onboarding?: AssistantOnboardingState;
  proposed_actions?: Array<Record<string, unknown>>;
  approval_requests?: Array<Record<string, unknown>>;
  memory_updates?: Array<Record<string, unknown>>;
  executed_tools?: Array<Record<string, unknown>>;
  message?: AssistantThreadMessage | string;
};

export type GoogleIntegrationStatus = {
  provider: string;
  configured: boolean;
  enabled: boolean;
  account_label?: string;
  scopes: string[];
  gmail_connected: boolean;
  calendar_connected: boolean;
  drive_connected?: boolean;
  calendar_write_ready?: boolean;
  status: string;
  email_thread_count?: number;
  calendar_event_count?: number;
  drive_file_count?: number;
  last_sync_at?: string | null;
  connected_account?: ConnectedAccount | null;
  desktop_managed: boolean;
};

export type TelegramIntegrationStatus = {
  provider: string;
  configured: boolean;
  enabled: boolean;
  account_label?: string;
  status: string;
  allowed_user_id?: string;
  connected_account?: ConnectedAccount | null;
  desktop_managed: boolean;
};

export type WhatsAppIntegrationStatus = {
  provider: string;
  configured: boolean;
  enabled: boolean;
  account_label?: string;
  phone_number_id?: string;
  display_phone_number?: string;
  status: string;
  message_count?: number;
  last_sync_at?: string | null;
  connected_account?: ConnectedAccount | null;
  desktop_managed: boolean;
};

export type XIntegrationStatus = {
  provider: string;
  configured: boolean;
  enabled: boolean;
  account_label?: string;
  user_id?: string;
  scopes: string[];
  status: string;
  mention_count?: number;
  post_count?: number;
  last_sync_at?: string | null;
  connected_account?: ConnectedAccount | null;
  desktop_managed: boolean;
};

export type TimelineEvent = {
  id: number;
  matter_id: number;
  event_type: string;
  title: string;
  details?: string | null;
  event_at: string;
  created_by?: string | null;
  created_at: string;
};

export type DocumentChunk = {
  id: number;
  document_id: number;
  office_id: string;
  matter_id: number;
  chunk_index: number;
  text: string;
  token_count: number;
  metadata: {
    line_anchor?: string;
    page?: number;
    line_start?: number;
    line_end?: number;
  };
};

export type ChronologyItem = {
  id: string;
  date: string;
  event: string;
  source_kind: string;
  source_id: number | string;
  source_label: string;
  factuality: string;
  uncertainty: string;
  confidence: string;
  signals: string[];
  citation?: Citation | null;
};

export type ChronologyIssue = {
  type: string;
  severity: string;
  title: string;
  details: string;
  source_labels: string[];
};

export type ChronologyResponse = {
  matter_id: number;
  items: ChronologyItem[];
  issues: ChronologyIssue[];
  generated_from: string;
  manual_review_required: boolean;
};

export type RiskNote = {
  category: string;
  title: string;
  details: string;
  severity: string;
  manual_review_required: boolean;
  signals: string[];
  source_labels: string[];
};

export type RiskNotesResponse = {
  matter_id: number;
  label: string;
  manual_review_required: boolean;
  generated_from: string;
  ai_overview?: string | null;
  ai_provider?: string | null;
  ai_model?: string | null;
  items: RiskNote[];
};

export type TaskRecommendation = {
  title: string;
  priority: string;
  due_at?: string | null;
  recommended_by: string;
  origin_type: string;
  manual_review_required: boolean;
  signals: string[];
  explanation: string;
};

export type TaskRecommendationsResponse = {
  matter_id: number;
  manual_review_required: boolean;
  generated_from: string;
  items: TaskRecommendation[];
};

export type ActivityItem = {
  kind: string;
  title: string;
  details?: string | null;
  created_at: string;
  actor?: string | null;
  badge?: string | null;
  source_ref: string;
  requires_review: boolean;
};

export type ActivityResponse = {
  matter_id: number;
  generated_from: string;
  items: ActivityItem[];
};

export type GeneratedDraftResponse = {
  draft: Draft;
  review_message: string;
  generated_from?: string;
  ai_provider?: string | null;
  ai_model?: string | null;
  source_context: {
    documents?: string[];
    chronology?: string[];
    risk_notes?: string[];
    open_tasks?: string[];
  };
};

export type EmailDraft = {
  id: number;
  office_id: string;
  matter_id?: number | null;
  to_email: string;
  subject: string;
  body: string;
  status: string;
  requested_by: string;
  approved_by?: string | null;
  retracted_by?: string | null;
  retract_reason?: string | null;
  created_at: string;
  updated_at: string;
};

export type EmailDraftPreview = {
  id: number;
  to_email: string;
  subject: string;
  status: string;
  requested_by: string;
  approved_by?: string | null;
  created_at: string;
  body_preview: string;
  body_chars: number;
  body_words: number;
};

export type EmailDraftEvent = {
  id: number;
  draft_id: number;
  event_type: string;
  actor: string;
  details?: string | null;
  created_at: string;
};

export type SocialEvent = {
  id: number;
  office_id: string;
  source: string;
  handle: string;
  content: string;
  risk_score: number;
  created_at: string;
};

export type QueryJob = {
  id: number | string;
  query: string;
  status: string;
  model_profile?: string | null;
  answer?: string | null;
  sources?: Array<Record<string, unknown>>;
  citation_quality?: { grade: string; score: number } | null;
  error?: string | null;
  created_at: string;
  updated_at?: string;
  toast_acked?: boolean;
};

export type MatterNote = {
  id: number;
  matter_id: number;
  office_id: string;
  body: string;
  note_type: string;
  event_at?: string | null;
  created_by: string;
  created_at: string;
};

export type CitationReviewResponse = {
  grade: string;
  score: number;
  recommendations: string[];
  citation_count: number;
  reference_density: number;
};
