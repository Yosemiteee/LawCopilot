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
  openclaw_tool_count?: number;
  openclaw_resource_count?: number;
  google_enabled?: boolean;
  google_configured?: boolean;
  google_account_label?: string;
  google_scopes?: string[];
  gmail_connected?: boolean;
  calendar_connected?: boolean;
  drive_connected?: boolean;
  outlook_enabled?: boolean;
  outlook_configured?: boolean;
  outlook_account_label?: string;
  outlook_scopes?: string[];
  outlook_mail_connected?: boolean;
  outlook_calendar_connected?: boolean;
  telegram_enabled?: boolean;
  telegram_configured?: boolean;
  telegram_bot_username?: string;
  telegram_allowed_user_id?: string;
  whatsapp_enabled?: boolean;
  whatsapp_configured?: boolean;
  whatsapp_account_label?: string;
  x_enabled?: boolean;
  x_configured?: boolean;
  x_account_label?: string;
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
  telemetry_access_level?: "full" | "restricted" | string;
  office_id: string;
  structured_log_path?: string | null;
  audit_log_path?: string | null;
  desktop_main_log_path?: string | null;
  desktop_backend_log_path?: string | null;
  db_path?: string | null;
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
  openclaw_tool_count?: number;
  openclaw_resource_count?: number;
  openclaw_context_snapshot_path?: string | null;
  openclaw_capability_manifest_path?: string | null;
  openclaw_resource_manifest_path?: string | null;
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
  outlook_enabled?: boolean;
  outlook_configured?: boolean;
  outlook_account_label?: string;
  outlook_scopes?: string[];
  outlook_mail_connected?: boolean;
  outlook_calendar_connected?: boolean;
  connected_accounts?: ConnectedAccount[];
  telegram_enabled?: boolean;
  telegram_configured?: boolean;
  telegram_bot_username?: string;
  telegram_allowed_user_id?: string;
  whatsapp_enabled?: boolean;
  whatsapp_configured?: boolean;
  whatsapp_account_label?: string;
  x_enabled?: boolean;
  x_configured?: boolean;
  x_account_label?: string;
  recent_runtime_events?: Array<Record<string, unknown>>;
  workspace_configured?: boolean;
  workspace_root_name?: string | null;
  recent_event_count?: number;
  recent_events: Array<Record<string, unknown>>;
  runtime_jobs?: Record<string, unknown>;
};

export type TelemetryPilotSummary = {
  generated_at: string;
  window_hours: number;
  overall_status: "pilot_ready" | "attention" | "launch_blocked" | string;
  telemetry_access_level?: "full" | "restricted" | string;
  privacy_posture: {
    structured_events_metadata_only: boolean;
    sensitive_content_logged: boolean;
    memory_content_visible_in_ui: boolean;
    note: string;
  };
  health_counters: {
    knowledge_records: number;
    learned_topics: number;
    recent_corrections: number;
    connected_accounts: number;
    connector_attention_required: number;
    connector_retry_scheduled: number;
    reflection_due: boolean;
    orchestration_attention_required: number;
    runtime_recent_recoveries: number;
  };
  analytics: {
    recommendation_feedback: {
      accepted: number;
      rejected: number;
      ignored: number;
      total: number;
    };
    assistant_message_feedback: {
      liked: number;
      disliked: number;
      total: number;
    };
    memory_corrections: {
      total: number;
      by_action: Record<string, number>;
    };
    connector_failures: {
      recent_failed_runs: number;
      attention_required: number;
      retry_scheduled: number;
      stale_connectors: number;
      connected_providers: number;
    };
    reflection_runs: {
      completed: number;
      failed: number;
      last_success_at?: string | null;
      next_due_at?: string | null;
      health_status?: string | null;
    };
    retrieval_quality: {
      manual_searches: number;
      low_result_searches: number;
      zero_result_searches: number;
      average_result_count: number;
    };
    runtime_stability: {
      openclaw_runtime_fallbacks: number;
      direct_provider_fallbacks: number;
      thread_stream_fallbacks: number;
      recovery_started_7d: number;
      recovery_failed_7d: number;
    };
    user_interactions: {
      memory_edits: number;
      kb_searches: number;
      recommendation_feedback_events: number;
      assistant_feedback_events: number;
    };
  };
  runtime_diagnostics: {
    desktop_main_log_path?: string | null;
    desktop_backend_log_path?: string | null;
    startup_log_available: boolean;
    backend_log_available: boolean;
    last_backend_ready_elapsed_ms?: number | null;
    recovery_started_7d: number;
    recovery_failed_7d: number;
    backend_exit_detected_7d: number;
    recent_issues: Array<{
      ts: string;
      event: string;
      detail?: string;
    }>;
  };
  runtime_jobs?: Record<string, unknown>;
  onboarding_hints: string[];
  assistant_memory_statement: string;
  degraded_modes: string[];
  launch_blockers: string[];
  known_limitations: string[];
  production_readiness: {
    production_ready: string[];
    partial: string[];
    stub: string[];
  };
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
  matter_title?: string | null;
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
  source?: "manual" | "system" | string;
  name: string;
  relationship: string;
  closeness?: number | null;
  preferences: string;
  notes: string;
  important_dates: ProfileImportantDate[];
};

export type InboxWatchRule = {
  id?: string | null;
  label: string;
  match_type: "person" | "group";
  match_value: string;
  channels: string[];
};

export type InboxKeywordRule = {
  id?: string | null;
  keyword: string;
  label?: string | null;
  channels: string[];
};

export type InboxBlockRule = {
  id?: string | null;
  label: string;
  match_type: "person" | "group";
  match_value: string;
  channels: string[];
  duration_kind: "day" | "month" | "forever";
  starts_at?: string | null;
  expires_at?: string | null;
};

export type SourcePreferenceRule = {
  id?: string | null;
  label?: string | null;
  task_kind: string;
  policy_mode: "prefer" | "restrict";
  preferred_domains: string[];
  preferred_links: string[];
  preferred_providers: string[];
  note?: string | null;
};

export type UserProfile = {
  office_id: string;
  display_name: string;
  favorite_color: string;
  food_preferences: string;
  transport_preference: string;
  weather_preference: string;
  travel_preferences: string;
  home_base: string;
  current_location: string;
  location_preferences: string;
  maps_preference: string;
  prayer_notifications_enabled: boolean;
  prayer_habit_notes: string;
  communication_style: string;
  assistant_notes: string;
  important_dates: ProfileImportantDate[];
  related_profiles: RelatedProfile[];
  contact_profile_overrides: ContactProfileOverride[];
  inbox_watch_rules: InboxWatchRule[];
  inbox_keyword_rules: InboxKeywordRule[];
  inbox_block_rules: InboxBlockRule[];
  source_preference_rules?: SourcePreferenceRule[];
  created_at?: string | null;
  updated_at?: string | null;
};

export type ContactProfileOverride = {
  contact_id: string;
  description: string;
  updated_at?: string | null;
};

export type AssistantContactProfile = {
  id: string;
  kind: "person" | "group";
  display_name: string;
  relationship_hint: string;
  related_profile_id?: string | null;
  closeness?: number | null;
  persona_summary: string;
  persona_detail?: string;
  generated_persona_detail?: string;
  persona_detail_source?: "generated" | "manual" | string;
  persona_detail_updated_at?: string | null;
  channels: string[];
  emails: string[];
  phone_numbers: string[];
  handles: string[];
  watch_enabled: boolean;
  blocked: boolean;
  blocked_until?: string | null;
  last_message_at?: string | null;
  source_count: number;
  inference_signals?: string[];
  preference_signals?: string[];
  gift_ideas?: string[];
  channel_summary?: string;
  last_inbound_preview?: string | null;
  last_inbound_channel?: string | null;
  group_contexts?: string[];
};

export type AssistantRelationshipProfile = {
  id: string;
  display_name: string;
  relationship_hint: string;
  related_profile_id?: string | null;
  closeness?: number | null;
  profile_strength: "orta" | "yüksek";
  selection_score: number;
  selection_reason: string;
  summary: string;
  channels: string[];
  emails: string[];
  phone_numbers: string[];
  handles: string[];
  watch_enabled: boolean;
  blocked: boolean;
  blocked_until?: string | null;
  last_message_at?: string | null;
  source_count: number;
  preference_signals: string[];
  gift_ideas: string[];
  inference_signals?: string[];
  channel_summary?: string;
  last_inbound_preview?: string | null;
  last_inbound_channel?: string | null;
  group_contexts?: string[];
  important_dates: Array<Record<string, unknown>>;
  notes?: string;
  auto_selected: boolean;
};

export type AssistantContactProfilesResponse = {
  items: AssistantContactProfile[];
  relationship_profiles?: AssistantRelationshipProfile[];
  directory_summary?: {
    total_accounts?: number;
    priority_profiles?: number;
    blocked_accounts?: number;
    watch_enabled_accounts?: number;
    channels?: Record<string, number>;
  };
  generated_from: string;
};

export type AssistantShareChannel = "whatsapp" | "telegram" | "email" | "x" | "linkedin";

export type AssistantShareDraftCreateRequest = {
  channel: AssistantShareChannel;
  content: string;
  to_contact?: string;
  subject?: string;
  thread_id?: number;
  message_id?: number;
  contact_profile_id?: string;
};

export type AssistantShareDraftCreateResponse = {
  draft: OutboundDraft;
  message: string;
  generated_from: string;
};

export type AssistantRuntimeForm = {
  slug: string;
  title: string;
  summary?: string;
  category?: string;
  active: boolean;
  source?: string;
  scopes?: string[];
  capabilities?: string[];
  ui_surfaces?: string[];
  supports_coaching?: boolean;
  custom?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  last_requested_at?: string | null;
};

export type AssistantBehaviorContract = {
  initiative_level?: string;
  planning_depth?: string;
  accountability_style?: string;
  follow_up_style?: string;
  explanation_style?: string;
};

export type AssistantCoreFormCatalogItem = {
  slug: string;
  title: string;
  summary?: string;
  category?: string;
  scopes?: string[];
  capabilities?: string[];
  ui_surfaces?: string[];
  supports_coaching?: boolean;
};

export type AssistantCoreCapabilityCatalogItem = {
  slug: string;
  title: string;
  summary?: string;
  category?: string;
  suggested_scopes?: string[];
  implies_surfaces?: string[];
};

export type AssistantCoreSurfaceCatalogItem = {
  slug: string;
  title: string;
  summary?: string;
  category?: string;
};

export type AssistantCoreCapabilityContract = AssistantCoreCapabilityCatalogItem & {
  operating_hint?: string;
};

export type AssistantCoreOperatingContract = {
  mode?: string;
  primary_scope?: string;
  supports_coaching?: boolean;
  behavior_style?: string;
  active_form_titles?: string[];
  capability_contracts?: AssistantCoreCapabilityContract[];
  surface_contracts?: AssistantCoreSurfaceCatalogItem[];
  guidance?: string[];
  setup_actions?: Array<{
    id: string;
    title: string;
    why?: string;
    surface?: string;
    priority?: string;
  }>;
};

export type AssistantCoreStatus = {
  summary?: {
    active_forms?: number;
    available_forms?: number;
    supports_coaching?: boolean;
    capability_count?: number;
  };
  active_forms?: AssistantRuntimeForm[];
  available_forms?: AssistantCoreFormCatalogItem[];
  form_catalog?: AssistantCoreFormCatalogItem[];
  capability_catalog?: AssistantCoreCapabilityCatalogItem[];
  surface_catalog?: AssistantCoreSurfaceCatalogItem[];
  capability_contracts?: AssistantCoreCapabilityContract[];
  surface_contracts?: AssistantCoreSurfaceCatalogItem[];
  operating_contract?: AssistantCoreOperatingContract;
  suggested_setup_actions?: Array<{
    id: string;
    title: string;
    why?: string;
    surface?: string;
    priority?: string;
  }>;
  behavior_contract?: AssistantBehaviorContract;
  capabilities?: string[];
  scopes?: string[];
  ui_surfaces?: string[];
  supports_coaching?: boolean;
  evolution_history?: Array<Record<string, unknown>>;
  core_summary?: string;
  defaults?: {
    role_summary?: string;
    tone?: string;
  };
  transformation_examples?: Array<{
    prompt: string;
    title: string;
    focus?: string;
  }>;
  updated_at?: string | null;
};

export type AssistantCoreBlueprint = {
  summary?: string;
  confidence?: number;
  matched_forms?: Array<{
    slug: string;
    title: string;
    category?: string;
  }>;
  why?: string[];
  behavior_contract_patch?: Partial<AssistantBehaviorContract>;
  activation_prompt?: string;
  transformation_scope?: string[];
  capability_titles?: string[];
  form?: Partial<AssistantRuntimeForm> & {
    capabilities?: string[];
    scopes?: string[];
    ui_surfaces?: string[];
  };
};

export type AssistantRuntimeProfile = {
  office_id: string;
  assistant_name: string;
  role_summary: string;
  tone: string;
  avatar_path: string;
  soul_notes: string;
  tools_notes: string;
  assistant_forms: AssistantRuntimeForm[];
  behavior_contract: AssistantBehaviorContract;
  evolution_history: Array<Record<string, unknown>>;
  heartbeat_extra_checks: string[];
  created_at?: string | null;
  updated_at?: string | null;
};

export type AssistantOnboardingState = {
  complete: boolean;
  setup_complete?: boolean;
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
  current_question?: {
    id: string;
    field: string;
    target: string;
    question: string;
    reason: string;
    help_text?: string;
    examples?: string[];
    quick_replies?: string[];
  };
  interview_intro?: string;
  interview_topics?: string[];
  steps?: Array<{
    id: string;
    title: string;
    description: string;
    complete: boolean;
    action: string;
    route?: string;
  }>;
  questions?: Array<{
    id: string;
    field: string;
    target: string;
    question: string;
    reason: string;
    help_text?: string;
    examples?: string[];
    quick_replies?: string[];
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
  tool_count?: number;
  tool_namespace_count?: number;
  resource_count?: number;
  progress_path?: string | null;
  context_snapshot_path?: string | null;
  capability_manifest_path?: string | null;
  resource_manifest_path?: string | null;
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
  provider?: string | null;
  memory_state?: ChannelMemoryState | string | null;
  matter_id?: number | null;
  recommended_action_ids?: Array<number | string>;
  manual_review_required: boolean;
};

export type ChannelMemoryState = "operational_only" | "candidate_memory" | "approved_memory";

export type ChannelMemoryStateUpdateResponse = {
  item: Record<string, unknown> & {
    id?: number | string;
    memory_state?: ChannelMemoryState | string | null;
  };
  memory_overview?: AssistantHomeResponse["memory_overview"];
  health?: Record<string, unknown>;
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
  outlook_connected?: boolean;
};

export type AssistantActionCase = {
  id: number;
  case_type: string;
  title: string;
  status: string;
  current_step: string;
  action_id?: number | null;
  draft_id?: number | null;
  approval_required?: boolean;
  metadata?: Record<string, unknown> | null;
  last_actor?: string | null;
  last_error?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type AssistantDispatchAttempt = {
  id: number;
  action_id?: number | null;
  draft_id?: number | null;
  dispatch_target?: string | null;
  status: string;
  external_message_id?: string | null;
  note?: string | null;
  error?: string | null;
  metadata?: Record<string, unknown> | null;
  actor?: string | null;
  created_at: string;
  updated_at: string;
};

export type AssistantExternalReceipt = {
  id: number;
  dispatch_attempt_id?: number | null;
  action_id?: number | null;
  draft_id?: number | null;
  provider?: string | null;
  receipt_type: string;
  receipt_status?: string | null;
  external_receipt_id?: string | null;
  external_message_id?: string | null;
  external_reference?: string | null;
  note?: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AssistantActionCaseStep = {
  step_key: string;
  title: string;
  status: string;
  detail?: string | null;
};

export type AssistantActionCompensationPlan = {
  status: string;
  strategy: string;
  reason: string;
  recommended_action_type?: string | null;
  recommended_target_channel?: string | null;
  suggested_instruction?: string | null;
  compensation_action_id?: number | null;
  compensation_case_id?: number | null;
  can_schedule: boolean;
};

export type AssistantActionAvailableControls = {
  can_pause: boolean;
  can_resume: boolean;
  can_retry_dispatch: boolean;
  can_schedule_compensation: boolean;
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
  action_case?: AssistantActionCase | null;
  dispatch_attempts?: AssistantDispatchAttempt[];
  external_receipts?: AssistantExternalReceipt[];
  case_steps?: AssistantActionCaseStep[];
  compensation_plan?: AssistantActionCompensationPlan | null;
  available_controls?: AssistantActionAvailableControls | null;
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
  action_case?: AssistantActionCase | null;
  available_controls?: AssistantActionAvailableControls | null;
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
  action_id?: number | null;
  linked_action?: SuggestedAction | null;
  action_case?: AssistantActionCase | null;
  dispatch_attempts?: AssistantDispatchAttempt[];
  external_receipts?: AssistantExternalReceipt[];
  case_steps?: AssistantActionCaseStep[];
  compensation_plan?: AssistantActionCompensationPlan | null;
  available_controls?: AssistantActionAvailableControls | null;
};

export type AssistantActionLadder = {
  current_stage?: string;
  available_next_stages?: string[];
  manual_review_required?: boolean;
  auto_execution_eligible?: boolean;
  future_stage?: string;
  policy_label?: string;
  risk_level?: string;
  trusted_low_risk_available?: boolean;
  reversible?: boolean;
  preview_required_before_execute?: boolean;
  preview_summary?: string;
  audit_label?: string;
  undo_strategy?: string;
  trusted_execution_note?: string;
  execution_policy?: string;
  approval_reason?: string;
  irreversible?: boolean;
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
    route?: string;
  }>;
  proactive_suggestions?: Array<{
    id: string;
    kind: string;
    title: string;
    details: string;
    action_label?: string;
    secondary_action_label?: string;
    secondary_action_url?: string;
    prompt?: string;
    matter_id?: number | null;
    tool?: string | null;
    priority?: string;
    why_now?: string;
    why_this_user?: string;
    confidence?: number;
    requires_confirmation?: boolean;
    memory_scope?: string[];
    source_basis?: Array<Record<string, unknown> | string>;
    supporting_pages_or_records?: Array<Record<string, unknown>>;
    recent_related_feedback?: Array<Record<string, unknown>>;
    explainability?: Record<string, unknown>;
    action_ladder?: AssistantActionLadder;
  }>;
  connected_accounts: ConnectedAccount[];
  relationship_profiles?: AssistantRelationshipProfile[];
  contact_directory?: AssistantContactProfile[];
  contact_directory_summary?: {
    total_accounts?: number;
    priority_profiles?: number;
    blocked_accounts?: number;
    watch_enabled_accounts?: number;
    channels?: Record<string, number>;
  };
  generated_from: string;
  onboarding?: AssistantOnboardingState;
  explainable_recommendations?: Array<{
    id: string;
    kind: string;
    suggestion: string;
    why_this: string;
    confidence: number;
    requires_confirmation: boolean;
    risk_level: string;
    memory_scope?: string[];
    source_basis?: Array<Record<string, unknown> | string>;
    supporting_pages_or_records?: Array<Record<string, unknown>>;
    recent_related_feedback?: Array<Record<string, unknown>>;
  }>;
  proactive_triggers?: Array<{
    id: string;
    trigger_type: string;
    title: string;
    why_now: string;
    why_this_user: string;
    confidence: number;
    urgency: string;
    scope: string;
    source_basis?: Array<Record<string, unknown> | string>;
    requires_confirmation: boolean;
    supporting_pages_or_records?: Array<Record<string, unknown>>;
    recent_related_feedback?: Array<Record<string, unknown>>;
    recommended_action?: Record<string, unknown>;
    explainability?: Record<string, unknown>;
    action_ladder?: AssistantActionLadder;
  }>;
  knowledge_base?: {
    enabled: boolean;
    search_backend?: string;
    raw_source_count?: number;
    connector_sync_count?: number;
  };
  knowledge_health_summary?: Record<string, number | string>;
  decision_timeline?: Array<Record<string, unknown>>;
  assistant_known_profile?: Record<string, Array<{
    id: string;
    title: string;
    summary: string;
    updated_at?: string;
    scope?: string;
    record_type?: string;
    sensitivity?: string;
    shareability?: string;
    confidence?: number;
    source_basis?: string[];
  }>>;
  memory_overview?: {
    counts?: Record<string, number>;
    by_scope?: Record<string, number>;
    by_type?: Record<string, number>;
    by_shareability?: Record<string, number>;
    recent_corrections?: Array<Record<string, unknown>>;
    do_not_reinfer?: Array<Record<string, unknown>>;
    repeated_contradictions?: Array<Record<string, unknown>>;
    highlighted_records?: Array<Record<string, unknown>>;
    suppressed_topics?: string[];
    boosted_topics?: string[];
    learned_topics?: Array<Record<string, unknown>>;
  };
  proactive_control_state?: {
    suppressed_topics?: string[];
    boosted_topics?: string[];
  };
  recommendation_history_summary?: Array<Record<string, unknown>>;
  connector_sync_status?: {
    updated_at?: string | null;
    last_reason?: string | null;
    summary?: {
      total_connectors?: number;
      healthy_connectors?: number;
      attention_required?: number;
      retry_scheduled?: number;
      stubs?: number;
      connected_providers?: number;
      stale_connectors?: number;
      fresh_connectors?: number;
    };
    items: Array<{
      connector: string;
      description: string;
      sync_mode: string;
      last_synced_at?: string | null;
      cursor?: string | null;
      checkpoint?: Record<string, unknown> | null;
      record_count?: number;
      synced_record_count?: number;
      dedupe_key_count?: number;
      last_reason?: string | null;
      last_trigger?: string | null;
      health_status?: string | null;
      sync_status?: string | null;
      sync_status_message?: string | null;
      last_error?: string | null;
      consecutive_failures?: number;
      next_retry_at?: string | null;
      last_attempted_at?: string | null;
      last_success_at?: string | null;
      last_duration_ms?: number | null;
      retry_delay_minutes?: number | null;
      provider_mode?: string | null;
      stub?: boolean;
      freshness_status?: string | null;
      freshness_minutes?: number | null;
      stale_sync?: boolean;
      providers: Array<{
        provider: string;
        connected: boolean;
        account_label?: string | null;
        last_sync_at?: string | null;
        status?: string | null;
        health_status?: string | null;
        sync_status?: string | null;
        sync_status_message?: string | null;
        last_error?: string | null;
        next_retry_at?: string | null;
        provider_mode?: string | null;
      }>;
    }>;
    jobs?: Array<Record<string, unknown>>;
  };
  location_context?: {
    provider?: string;
    provider_mode?: string;
    provider_status?: string;
    capture_mode?: string;
    permission_state?: string | null;
    privacy_mode?: boolean;
    capture_failure_reason?: string | null;
    freshness_label?: string | null;
    freshness_minutes?: number | null;
    source?: string;
    observed_at?: string | null;
    updated_at?: string | null;
    scope?: string | null;
    sensitivity?: string | null;
    time_bucket?: string;
    current_place?: Record<string, unknown> | null;
    recent_places?: Array<Record<string, unknown>>;
    frequent_patterns?: Array<Record<string, unknown>>;
    nearby_candidates?: Array<Record<string, unknown>>;
    navigation_handoff?: Record<string, unknown>;
    snapshot_path?: string | null;
    location_explainability?: Record<string, unknown> | null;
    device_context?: Record<string, unknown> | null;
    context_composition?: Record<string, unknown> | null;
  } | null;
  reflection_status?: {
    status?: string | null;
    health_status?: string | null;
    last_reflection_at?: string | null;
    last_error?: string | null;
    next_due_at?: string | null;
    is_due?: boolean;
    consecutive_failures?: number;
    summary?: Record<string, number | string>;
    recommended_kb_actions?: Array<Record<string, unknown>>;
  };
  autonomy_status?: {
    generated_at?: string | null;
    status?: string | null;
    policy?: Record<string, unknown>;
    matters_now?: Array<Record<string, unknown>>;
    open_loop_count?: number;
    reflection_health?: Record<string, unknown>;
    connector_health?: Record<string, unknown>;
    silence_reasons?: string[];
  };
  orchestration_status?: {
    updated_at?: string | null;
    last_reason?: string | null;
    last_run_at?: string | null;
    summary?: {
      total_jobs?: number;
      failed_jobs?: number;
      due_jobs?: number;
      healthy_jobs?: number;
      retry_scheduled?: number;
      running_jobs?: number;
      attention_required?: number;
      next_due_at?: string | null;
      last_error?: string | null;
    };
    jobs?: Array<Record<string, unknown>>;
    runs?: Array<Record<string, unknown>>;
  };
  coaching_dashboard?: {
    updated_at?: string | null;
    last_review_at?: string | null;
    summary?: {
      active_goals?: number;
      completed_goals?: number;
      due_checkins?: number;
      progress_logs?: number;
      tasks_due_today?: number;
      attention_required?: number;
    };
    active_goals?: Array<{
      id: string;
      title: string;
      summary?: string;
      cadence?: string;
      scope?: string;
      sensitivity?: string;
      unit?: string;
      target_value?: number | null;
      current_value?: number | null;
      progress_ratio?: number;
      progress_percent?: number;
      remaining_value?: number | null;
      remaining_value_text?: string | null;
      next_check_in_at?: string | null;
      last_progress_at?: string | null;
      streak_days?: number;
      needs_checkin?: boolean;
      needs_attention?: boolean;
      why_now?: string;
      priority_label?: string;
      allow_desktop_notifications?: boolean;
    }>;
    completed_goals?: Array<Record<string, unknown>>;
    due_checkins?: Array<Record<string, unknown>>;
    recent_progress_logs?: Array<Record<string, unknown>>;
    notification_candidates?: Array<Record<string, unknown>>;
    derived_focus_areas?: Array<Record<string, unknown>>;
    insights?: string[];
    plan?: {
      generated_at?: string;
      reason?: string;
      summary?: Record<string, unknown>;
      focus?: Array<Record<string, unknown>>;
      strengths?: string[];
      risks?: string[];
      strategies?: string[];
      hypotheses?: string[];
    };
  };
  assistant_core?: AssistantCoreStatus;
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
  starred: boolean;
  starred_at?: string | null;
  feedback_value?: "liked" | "disliked" | null;
  feedback_note?: string | null;
  feedback_at?: string | null;
  thread_title?: string | null;
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
    archived?: boolean;
  };
  messages: AssistantThreadMessage[];
  has_more?: boolean;
  total_count?: number;
  assistant_summary?: string | null;
  generated_from?: string;
  dispatch_mode?: string | null;
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
  automation_updates?: Array<Record<string, unknown>>;
  message?: AssistantThreadMessage | string;
};

export type AssistantThreadStarredMessagesResponse = {
  thread?: AssistantThreadResponse["thread"] | null;
  items: AssistantThreadMessage[];
  generated_from?: string;
};

export type AssistantThreadSummary = {
  id: number;
  office_id: string;
  title: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  archived?: boolean;
  message_count?: number;
  last_message_preview?: string | null;
  last_message_at?: string | null;
};

export type AssistantThreadListResponse = {
  items: AssistantThreadSummary[];
  selected_thread_id?: number | null;
  generated_from?: string;
};

export type AssistantThreadStreamEvent =
  | { type: "thread_ready"; thread: AssistantThreadResponse["thread"]; user_message: AssistantThreadMessage }
  | { type: "assistant_start" }
  | { type: "assistant_chunk"; delta: string; content: string }
  | { type: "assistant_complete"; response: AssistantThreadResponse }
  | { type: "error"; detail: string; status?: number };

export type GoogleIntegrationStatus = {
  provider: string;
  configured: boolean;
  enabled: boolean;
  account_label?: string;
  scopes: string[];
  gmail_connected: boolean;
  calendar_connected: boolean;
  drive_connected?: boolean;
  youtube_connected?: boolean;
  youtube_playlist_count?: number;
  youtube_history_available?: boolean;
  youtube_history_count?: number;
  chrome_history_available?: boolean;
  chrome_history_count?: number;
  portability_configured?: boolean;
  portability_account_label?: string;
  portability_scopes?: string[];
  portability_status?: string;
  portability_last_sync_at?: string | null;
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
  message_count?: number;
  last_sync_at?: string | null;
  connected_account?: ConnectedAccount | null;
  desktop_managed: boolean;
};

export type OutlookIntegrationStatus = {
  provider: string;
  configured: boolean;
  enabled: boolean;
  account_label?: string;
  scopes: string[];
  mail_connected: boolean;
  calendar_connected: boolean;
  status: string;
  email_thread_count?: number;
  calendar_event_count?: number;
  last_sync_at?: string | null;
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
  dm_count?: number;
  last_sync_at?: string | null;
  connected_account?: ConnectedAccount | null;
  desktop_managed: boolean;
};

export type LinkedInIntegrationStatus = {
  provider: string;
  configured: boolean;
  enabled: boolean;
  account_label?: string;
  user_id?: string;
  person_urn?: string;
  scopes: string[];
  status: string;
  post_count?: number;
  comment_count?: number;
  last_sync_at?: string | null;
  connected_account?: ConnectedAccount | null;
  desktop_managed: boolean;
};

export type IntegrationUiOption = {
  value: string;
  label: string;
  description?: string;
};

export type IntegrationUiField = {
  key: string;
  label: string;
  kind: "text" | "password" | "url" | "textarea" | "select" | "boolean" | "number";
  target: "config" | "secret";
  required: boolean;
  secret: boolean;
  placeholder?: string;
  help_text?: string;
  default?: unknown;
  options?: IntegrationUiOption[];
};

export type IntegrationPermissionPreset = {
  level: "read_only" | "read_write" | "admin_like";
  label: string;
  description: string;
  allowed_operations: string[];
};

export type IntegrationActionSpec = {
  key: string;
  title: string;
  description: string;
  operation: string;
  access: string;
  approval_required: boolean;
  input_schema?: Record<string, unknown>;
  method?: string | null;
  path?: string | null;
  response_items_path?: string | null;
  response_item_path?: string | null;
  cursor_path?: string | null;
  query_map?: Record<string, string>;
};

export type IntegrationResourceSpec = {
  key: string;
  title: string;
  description: string;
  item_types: string[];
  supports_search: boolean;
};

export type IntegrationTriggerSpec = {
  key: string;
  title: string;
  description: string;
  event_types: string[];
};

export type IntegrationSyncPolicy = {
  mode: string;
  default_strategy: string;
  cursor_field?: string | null;
  schedule_hint_minutes?: number | null;
};

export type IntegrationPaginationStrategy = {
  type: string;
  cursor_param?: string | null;
  page_param?: string | null;
  page_size_param?: string | null;
  items_path?: string | null;
};

export type IntegrationWebhookSupport = {
  supported: boolean;
  signature_header?: string | null;
  events: string[];
  secret_required: boolean;
};

export type IntegrationRateLimit = {
  strategy: string;
  requests_per_minute?: number | null;
  burst_limit?: number | null;
  retry_after_header?: string | null;
};

export type IntegrationConnectorSpec = {
  id: string;
  name: string;
  description: string;
  category: string;
  auth_type: string;
  auth_config: {
    client_configurable: boolean;
    supports_refresh: boolean;
    authorization_url?: string | null;
    token_url?: string | null;
    revocation_url?: string | null;
    documentation_url?: string | null;
    default_scopes?: string[];
    scope_separator?: string;
    pkce_required?: boolean;
    token_field_map?: Record<string, string>;
    notes: string[];
  };
  scopes: string[];
  base_url?: string | null;
  resources: IntegrationResourceSpec[];
  actions: IntegrationActionSpec[];
  triggers: IntegrationTriggerSpec[];
  sync_policies: IntegrationSyncPolicy[];
  pagination_strategy: IntegrationPaginationStrategy;
  webhook_support: IntegrationWebhookSupport;
  rate_limit: IntegrationRateLimit;
  ui_schema: IntegrationUiField[];
  permissions: IntegrationPermissionPreset[];
  capability_flags: Record<string, boolean>;
  management_mode: "platform" | "legacy-desktop";
  default_access_level: "read_only" | "read_write" | "admin_like";
  tags: string[];
  docs_url?: string | null;
  setup_hint?: string;
};

export type IntegrationConnection = {
  id: number;
  connector_id: string;
  display_name: string;
  status: string;
  auth_type: string;
  access_level: "read_only" | "read_write" | "admin_like";
  management_mode: "platform" | "legacy-desktop";
  enabled: boolean;
  mock_mode: boolean;
  scopes: string[];
  config: Record<string, unknown>;
  health_status: string;
  health_message?: string | null;
  auth_status?: string | null;
  auth_summary?: {
    status?: string;
    auth_type?: string;
    supports_refresh?: boolean;
    requested_scopes?: string[];
    granted_scopes?: string[];
    expires_at?: string | null;
    refresh_token_present?: boolean;
    last_refreshed_at?: string | null;
    last_revoked_at?: string | null;
    permission_summary?: string[];
  };
  credential_expires_at?: string | null;
  credential_refreshed_at?: string | null;
  credential_revoked_at?: string | null;
  last_health_check_at?: string | null;
  last_validated_at?: string | null;
  last_sync_at?: string | null;
  last_error?: string | null;
  sync_status?: string | null;
  sync_status_message?: string | null;
  cursor?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
};

export type IntegrationCapabilitySummary = {
  connector_id: string;
  access_level: string;
  permission_summary: {
    label: string;
    description: string;
    allowed_operations: string[];
  };
  auth_summary?: Record<string, unknown>;
  safety_settings: IntegrationSafetySettings;
  allowed_actions: Array<{
    key: string;
    title: string;
    operation: string;
    access: string;
    requires_confirmation: boolean;
    reason: string;
  }>;
  blocked_actions: Array<{
    key: string;
    title: string;
    operation: string;
    access: string;
    requires_confirmation: boolean;
    reason: string;
  }>;
};

export type IntegrationSafetySettings = {
  read_enabled: boolean;
  write_enabled: boolean;
  delete_enabled: boolean;
  require_confirmation_for_write: boolean;
  require_confirmation_for_delete: boolean;
};

export type IntegrationOauthSession = {
  id: number;
  state: string;
  redirect_uri?: string | null;
  authorization_url?: string | null;
  status: string;
  requested_scopes?: string[];
  created_by?: string | null;
  created_at: string;
  completed_at?: string | null;
  error?: string | null;
  metadata?: Record<string, unknown>;
};

export type IntegrationResourceRecord = {
  id: number;
  resource_kind: string;
  external_id: string;
  source_record_type: string;
  title?: string | null;
  body_text?: string | null;
  search_text?: string | null;
  source_url?: string | null;
  parent_external_id?: string | null;
  owner_label?: string | null;
  occurred_at?: string | null;
  modified_at?: string | null;
  checksum?: string | null;
  permissions?: Record<string, unknown>;
  tags?: string[];
  attributes?: Record<string, unknown>;
  sync_metadata?: Record<string, unknown>;
  synced_at: string;
  updated_at: string;
};

export type IntegrationEventRecord = {
  id: number;
  event_type: string;
  severity: string;
  message: string;
  actor?: string | null;
  data?: Record<string, unknown>;
  created_at: string;
};

export type IntegrationWebhookRecord = {
  id: number;
  connector_id: string;
  connection_id?: number | null;
  event_id: string;
  event_type: string;
  status: string;
  request_signature?: string | null;
  request_timestamp?: string | null;
  payload?: Record<string, unknown>;
  response?: Record<string, unknown>;
  error?: string | null;
  received_at: string;
  processed_at?: string | null;
};

export type IntegrationWorkerStatus = {
  state: string;
  poll_seconds?: number;
  batch_size?: number;
  actor?: string;
  last_tick_at?: string | null;
  last_result_count?: number;
  last_error?: string | null;
};

export type IntegrationLegacyStatus = {
  provider: string;
  account_label?: string | null;
  connected: boolean;
  status: string;
  scopes: string[];
  capabilities: string[];
  write_enabled: boolean;
  approval_required: boolean;
  connected_account?: ConnectedAccount | null;
  desktop_managed: boolean;
};

export type IntegrationSecurityPosture = {
  storage_posture: string;
  connector_dry_run: boolean;
  human_review_gate: boolean;
  allowed_domains: string[];
  sync_worker_enabled?: boolean;
  secret_key_id?: string;
  secret_key_count?: number;
};

export type IntegrationGeneratedRequest = {
  id: number;
  connector_id: string;
  service_name: string;
  request_text: string;
  status: string;
  version?: number;
  enabled?: boolean;
  docs_url?: string | null;
  openapi_url?: string | null;
  documentation_excerpt?: string | null;
  last_error?: string | null;
  metadata?: Record<string, unknown>;
  skill?: {
    name?: string;
    connector_id?: string;
    capabilities?: string[];
    permissions?: string[];
    ui_label?: string;
  } | null;
  review?: {
    decision?: string;
    status?: string;
    notes?: string | null;
    reviewed_by?: string | null;
    reviewed_at?: string | null;
    live_use_enabled?: boolean;
  };
  versions?: Array<{
    version: number;
    status: string;
    enabled: boolean;
    created_at: string;
  }>;
  live_use_enabled?: boolean;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
  connector?: IntegrationConnectorSpec | null;
};

export type IntegrationConnectorPattern = {
  id: number;
  pattern_key: string;
  connector_id?: string | null;
  service_name: string;
  category?: string | null;
  auth_type?: string | null;
  docs_host?: string | null;
  base_url?: string | null;
  source_kind: string;
  success_count: number;
  pattern?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  last_used_at?: string | null;
};

export type IntegrationCatalogItem = {
  connector: IntegrationConnectorSpec;
  connections: IntegrationConnection[];
  legacy_status?: IntegrationLegacyStatus | null;
  generated_request?: IntegrationGeneratedRequest | null;
  installed: boolean;
  primary_status: string;
  source: string;
};

export type IntegrationCatalogResponse = {
  items: IntegrationCatalogItem[];
  categories: string[];
  security: IntegrationSecurityPosture;
  generated_from: string;
};

export type IntegrationConnectionDetail = {
  connection: IntegrationConnection;
  connector: IntegrationConnectorSpec;
  capabilities?: IntegrationCapabilitySummary;
  safety_settings?: IntegrationSafetySettings;
  sync_runs: Array<{
    id: number;
    mode: string;
    status: string;
    trigger_type?: string;
    item_count: number;
    attempt_count?: number;
    max_attempts?: number;
    scheduled_for?: string | null;
    started_at: string;
    finished_at?: string | null;
    next_retry_at?: string | null;
    error?: string | null;
    cursor?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
  }>;
  record_preview: Array<{
    id: number;
    record_type: string;
    external_id: string;
    title?: string | null;
    text_content?: string | null;
    content_hash?: string | null;
    source_url?: string | null;
    permissions?: Record<string, unknown>;
    tags?: string[];
    raw?: Record<string, unknown>;
    normalized?: Record<string, unknown>;
    synced_at: string;
    updated_at: string;
  }>;
  resource_preview?: IntegrationResourceRecord[];
  action_runs: Array<{
    id: number;
    action_key: string;
    operation: string;
    status: string;
    requested_by: string;
    approval_required: boolean;
    approval_state: string;
    input?: Record<string, unknown>;
    output?: Record<string, unknown>;
    policy?: Record<string, unknown>;
    error?: string | null;
    created_at: string;
    updated_at: string;
  }>;
  event_preview?: IntegrationEventRecord[];
  webhook_preview?: IntegrationWebhookRecord[];
  oauth_sessions?: IntegrationOauthSession[];
  security: IntegrationSecurityPosture;
  generated_from: string;
};

export type IntegrationPreviewResponse = {
  connector: IntegrationConnectorSpec;
  display_name: string;
  normalized: {
    config: Record<string, unknown>;
    scopes: string[];
    access_level: "read_only" | "read_write" | "admin_like";
    mock_mode: boolean;
  };
  validation: {
    status: string;
    health_status: string;
    message: string;
    warnings?: string[];
    config: Record<string, unknown>;
    access_level: "read_only" | "read_write" | "admin_like";
    scopes: string[];
    secret_keys: string[];
  };
  security: IntegrationSecurityPosture;
  generated_from: string;
};

export type IntegrationMutationResponse = {
  connection: IntegrationConnection;
  connector?: IntegrationConnectorSpec;
  safety_settings?: IntegrationSafetySettings;
  message: string;
  generated_from: string;
};

export type IntegrationValidationResponse = {
  connection: IntegrationConnection;
  connector: IntegrationConnectorSpec;
  validation: {
    status: string;
    health_status: string;
    message: string;
    warnings?: string[];
    config?: Record<string, unknown>;
    access_level?: string;
    scopes?: string[];
    secret_keys?: string[];
  };
  generated_from: string;
};

export type IntegrationSyncResponse = {
  connection: IntegrationConnection;
  connector: IntegrationConnectorSpec;
  sync_run?: {
    id: number;
    mode: string;
    status: string;
    item_count: number;
    started_at: string;
    finished_at?: string | null;
    error?: string | null;
    cursor?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
  };
  record_count: number;
  message: string;
  generated_from: string;
};

export type IntegrationActionResponse = {
  action_run: {
    id: number;
    action_key: string;
    operation: string;
    status: string;
    approval_state: string;
    approval_required: boolean;
    input?: Record<string, unknown>;
    output?: Record<string, unknown>;
    error?: string | null;
    created_at: string;
    updated_at: string;
  };
  connector: IntegrationConnectorSpec;
  connection: IntegrationConnection;
  message: string;
  generated_from: string;
};

export type IntegrationOAuthStartResponse = {
  connection: IntegrationConnection;
  connector: IntegrationConnectorSpec;
  oauth_session: IntegrationOauthSession;
  authorization_url: string;
  message: string;
  generated_from: string;
};

export type IntegrationEventsResponse = {
  items: IntegrationEventRecord[];
  webhook_items?: IntegrationWebhookRecord[];
  worker?: IntegrationWorkerStatus | null;
  generated_from: string;
};

export type IntegrationDispatchResponse = {
  items: IntegrationSyncResponse[];
  count: number;
  generated_from: string;
};

export type IntegrationScaffoldResponse = {
  service_name: string;
  inference: {
    connector_id: string;
    category: string;
    auth_type: string;
    docs_url?: string | null;
    openapi_url?: string | null;
  };
  connector: IntegrationConnectorSpec;
  review_gate: {
    required: boolean;
    checklist: string[];
  };
  warnings: string[];
  suggested_validation_tests?: Array<{ name: string; description: string }>;
  mock_fixtures?: Array<Record<string, unknown>>;
  generated_from: string;
};

export type IntegrationAutomationResponse = {
  created: boolean;
  connector: IntegrationConnectorSpec;
  generated_request?: IntegrationGeneratedRequest | null;
  scaffold?: IntegrationScaffoldResponse | null;
  message: string;
  generated_from: string;
};

export type IntegrationGeneratedRequestsResponse = {
  items: IntegrationGeneratedRequest[];
  generated_from: string;
};

export type IntegrationGeneratedRequestMutationResponse = {
  generated_request: IntegrationGeneratedRequest;
  connector?: IntegrationConnectorSpec | null;
  message: string;
  generated_from: string;
};

export type IntegrationGeneratedRequestDeleteResponse = {
  deleted: boolean;
  connector_id: string;
  message: string;
  generated_from: string;
};

export type IntegrationConnectorPatternsResponse = {
  items: IntegrationConnectorPattern[];
  generated_from: string;
};

export type IntegrationLaunchOpsSummary = {
  rollout: {
    connector_dry_run: boolean;
    integration_worker_enabled: boolean;
    assistant_setup_timeout_minutes: number;
    allowed_domains: string[];
  };
  health: {
    connection_count: number;
    generated_connector_count: number;
    degraded_connections: Array<{
      connection_id: number;
      connector_id: string;
      display_name: string;
      health_status: string;
      auth_status: string;
      sync_status: string;
      last_error?: string | null;
    }>;
    stale_pending_setups: Array<{
      setup_id: number;
      thread_id: number;
      service_name: string;
      status: string;
      updated_at?: string | null;
    }>;
    worker?: IntegrationWorkerStatus | Record<string, unknown> | null;
    ready_for_launch: boolean;
    readiness_checks: Array<{
      level: string;
      label: string;
      count: number;
      message: string;
    }>;
  };
  analytics: {
    connector_requests: {
      total: number;
      top_requested: Array<{ service_name: string; count: number }>;
    };
    assistant_setups: {
      counts: Record<string, number>;
      completion_rate: number;
      top_dropoffs: Array<{ field: string; count: number }>;
    };
    oauth: {
      counts: Record<string, number>;
      completion_rate: number;
    };
    sync: {
      counts: Record<string, number>;
      success_rate: number;
    };
    webhooks: {
      counts: Record<string, number>;
    };
  };
  support: {
    recent_alerts: IntegrationEventRecord[];
    generated_review_pending: number;
    generated_rejected: number;
  };
  security: IntegrationSecurityPosture;
  generated_from: string;
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
  category?: string | null;
  severity?: string | null;
  notify_user?: boolean;
  evidence_value?: boolean;
  summary?: string | null;
  recommended_action?: string | null;
  metadata?: Record<string, unknown> | null;
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

export type AgentToolCatalogItem = {
  name: string;
  label?: string | null;
  description?: string | null;
  kind?: string | null;
  risk_level?: string | null;
  approval_policy?: string | null;
  available?: boolean;
  idempotent?: boolean;
  timeout_seconds?: number | null;
  allowed_scopes?: string[];
  input_schema?: Record<string, unknown> | null;
  output_schema?: Record<string, unknown> | null;
};

export type AgentRunArtifact = {
  id?: number | string;
  kind?: string | null;
  label?: string | null;
  url?: string | null;
  path?: string | null;
  content_type?: string | null;
  text_excerpt?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type AgentStep = {
  id?: number | string;
  run_id?: number | string;
  step_index?: number;
  role?: string | null;
  kind?: string | null;
  title?: string | null;
  detail?: string | null;
  status?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type ToolInvocation = {
  id?: number | string;
  run_id?: number | string;
  step_id?: number | string;
  tool_name?: string | null;
  tool?: string | null;
  mode?: string | null;
  status?: string | null;
  summary?: string | null;
  approval_required?: boolean;
  risk_level?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type AgentRunApproval = {
  id?: string | number;
  title?: string | null;
  tool?: string | null;
  status?: string | null;
  reason?: string | null;
  approval_required?: boolean;
};

export type AgentRunEvent = {
  id?: number | string;
  type?: string | null;
  kind?: string | null;
  title?: string | null;
  role?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  message?: string | null;
  summary?: string | null;
  status?: string | null;
  step?: AgentStep | null;
  invocation?: ToolInvocation | null;
  artifact?: AgentRunArtifact | null;
  payload?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
};

export type AgentRun = {
  id: number | string;
  office_id?: string;
  title?: string | null;
  goal?: string | null;
  matter_id?: number | null;
  status?: string | null;
  result_status?: string | null;
  summary?: string | null;
  final_output?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  support_level?: string | null;
  confidence?: string | null;
  execution_posture?: string | null;
  review_summary?: string | null;
  review_notes?: string[];
  source_backed?: boolean;
  citations?: Citation[];
  artifacts?: AgentRunArtifact[];
  steps?: AgentStep[];
  tool_invocations?: ToolInvocation[];
  approval_requests?: AgentRunApproval[];
  summary_payload?: Record<string, unknown> | null;
  result_payload?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
};

export type MemoryExplorerListItem = {
  id: string;
  kind: "wiki_page" | "concept" | "system_file" | "report";
  page_key?: string | null;
  title: string;
  summary?: string | null;
  description?: string | null;
  path?: string | null;
  record_count?: number;
  active_record_count?: number;
  scope?: string | null;
  scope_summary?: Record<string, number>;
  record_type_counts?: Record<string, number>;
  sensitivity_summary?: Record<string, number>;
  shareability_summary?: Record<string, number>;
  claim_summary?: {
    bound_records?: number | null;
    status_counts?: Record<string, number>;
  };
  confidence?: number | null;
  last_updated?: string | null;
  backlink_count?: number;
  linked_pages?: Array<Record<string, unknown>>;
  quality_flags?: string[];
  editable?: boolean;
};

export type MemoryExplorerPagesResponse = {
  generated_at?: string | null;
  summary?: Record<string, number | string>;
  items: MemoryExplorerListItem[];
  transparency?: Record<string, unknown>;
};

export type MemoryExplorerRecord = {
  id?: string | null;
  key?: string | null;
  title?: string | null;
  summary?: string | null;
  status?: string | null;
  confidence?: number | null;
  updated_at?: string | null;
  record_type?: string | null;
  scope?: string | null;
  sensitivity?: string | null;
  exportability?: string | null;
  model_routing_hint?: string | null;
  shareability?: string | null;
  source_refs?: Array<Record<string, unknown> | string>;
  source_basis?: Array<Record<string, unknown> | string>;
  correction_history?: Array<Record<string, unknown>>;
  backlinks?: Array<Record<string, unknown>>;
  relations?: Array<Record<string, unknown>>;
  epistemic?: {
    status?: string | null;
    subject_key?: string | null;
    predicate?: string | null;
    current_claim_id?: string | null;
    current_basis?: string | null;
    validation_state?: string | null;
    retrieval_eligibility?: string | null;
    contested_count?: number | null;
    support_strength?: string | null;
    support_contaminated?: boolean | null;
    support_cycle_detected?: boolean | null;
    support_reason_codes?: string[];
    external_support_count?: number | null;
    self_generated_support_count?: number | null;
    memory_tier?: string | null;
    salience_score?: number | null;
    age_days?: number | null;
  } | null;
  metadata?: Record<string, unknown>;
};

export type MemoryExplorerClaimBinding = {
  record_id?: string | null;
  record_key?: string | null;
  record_title?: string | null;
  current_claim_id?: string | null;
  subject_key?: string | null;
  predicate?: string | null;
  status?: string | null;
  basis?: string | null;
  validation_state?: string | null;
  retrieval_eligibility?: string | null;
  support_strength?: string | null;
  support_reason_codes?: string[];
  support_contaminated?: boolean | null;
  support_cycle_detected?: boolean | null;
  external_support_count?: number | null;
  self_generated_support_count?: number | null;
  memory_tier?: string | null;
  salience_score?: number | null;
  age_days?: number | null;
  supporting_claim_ids?: string[];
  source_claim_ids?: string[];
  derived_from_claim_ids?: string[];
};

export type MemoryExplorerArticleClaimBinding = {
  section?: string | null;
  anchor?: string | null;
  offset_start?: number | null;
  offset_end?: number | null;
  text?: string | null;
  claim_ids?: string[];
  subjects?: string[];
  predicates?: string[];
  support_strengths?: string[];
};

export type MemoryExplorerPageDetail = {
  id: string;
  kind: "wiki_page" | "concept" | "system_file" | "report";
  page_key?: string | null;
  title: string;
  summary?: string | null;
  description?: string | null;
  path?: string | null;
  content_markdown?: string | null;
  last_updated?: string | null;
  confidence?: number | null;
  scope_summary?: Record<string, number>;
  sensitivity_summary?: Record<string, number | string>;
  source_refs?: Array<Record<string, unknown> | string>;
  source_basis?: Array<Record<string, unknown> | string>;
  backlinks?: Array<Record<string, unknown>>;
  linked_pages?: Array<Record<string, unknown>>;
  records?: Array<MemoryExplorerRecord | Record<string, unknown>>;
  claim_bindings?: Array<MemoryExplorerClaimBinding | Record<string, unknown>>;
  article_claim_bindings?: Array<MemoryExplorerArticleClaimBinding | Record<string, unknown>>;
  claim_summary?: {
    bound_records?: number | null;
    status_counts?: Record<string, number>;
  };
  related_concepts?: Array<Record<string, unknown>>;
  quality_flags?: string[];
  article_sections?: Record<string, unknown>;
  transparency?: Record<string, unknown>;
};

export type MemoryExplorerGraphResponse = {
  generated_at?: string | null;
  backend?: string | null;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  summary?: Record<string, unknown>;
  legend?: Record<string, string>;
};

export type MemoryExplorerTimelineResponse = {
  generated_at?: string | null;
  summary?: Record<string, unknown>;
  items: Array<{
    id: string;
    timestamp: string;
    event_type: string;
    title: string;
    summary: string;
    metadata?: Record<string, unknown>;
  }>;
};

export type MemoryExplorerHealthResponse = {
  generated_at?: string | null;
  summary?: Record<string, number | string>;
  reflection_status?: Record<string, unknown>;
  health_status?: string | null;
  low_confidence_records?: Array<Record<string, unknown>>;
  contradictions?: Array<Record<string, unknown>>;
  stale_records?: Array<Record<string, unknown>>;
  recommendation_spam_risk?: Array<Record<string, unknown>>;
  knowledge_gaps?: Array<Record<string, unknown>>;
  research_topics?: Array<Record<string, unknown>>;
  potential_wiki_pages?: Array<Record<string, unknown>>;
  prunable_records?: Array<Record<string, unknown>>;
  inconsistency_hotspots?: Array<Record<string, unknown>>;
  contested_claims?: Array<Record<string, unknown>>;
  suspicious_claims?: Array<Record<string, unknown>>;
  claim_summary?: Record<string, unknown>;
  recommended_kb_actions?: Array<Record<string, unknown>>;
  reflection_output?: Record<string, unknown>;
  memory_overview?: Record<string, unknown>;
  transparency?: Record<string, unknown>;
};

export type PersonalModelQuestion = {
  id: string;
  module_key: string;
  prompt: string;
  title?: string | null;
  help_text?: string | null;
  examples?: string[];
  choices?: Array<{ value: string; label: string }>;
  category?: string | null;
  fact_key?: string | null;
  input_mode?: "text" | "choice" | string;
  skippable?: boolean;
  supports_voice_future?: boolean;
};

export type PersonalModelSession = {
  id: string;
  scope?: string | null;
  source?: string | null;
  module_keys?: string[];
  status?: string | null;
  started_at?: string | null;
  paused_at?: string | null;
  completed_at?: string | null;
  updated_at?: string | null;
  progress?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  session_context?: Record<string, unknown>;
  current_question?: PersonalModelQuestion | null;
};

export type PersonalModelFact = {
  id: string;
  category?: string | null;
  fact_key?: string | null;
  title?: string | null;
  value_text?: string | null;
  value_json?: Record<string, unknown>;
  confidence?: number | null;
  confidence_percent?: number | null;
  confidence_label?: string | null;
  confidence_type?: "explicit" | "inferred" | string;
  source_entry_id?: number | null;
  visibility?: string | null;
  scope?: string | null;
  scope_label?: string | null;
  sensitive?: boolean;
  enabled?: boolean;
  never_use?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  learned_at_label?: string | null;
  why_known?: string | null;
  usage_label?: string | null;
  source_summary?: string | null;
  epistemic_status?: string | null;
  epistemic_status_label?: string | null;
  epistemic_claim_id?: string | null;
  epistemic_basis?: string | null;
  epistemic_basis_label?: string | null;
  epistemic_support_strength?: string | null;
  epistemic_support_contaminated?: boolean;
  epistemic_retrieval_eligibility?: string | null;
  metadata?: Record<string, unknown>;
  selection_reasons?: string[];
  selection_reason_labels?: string[];
  score?: number | null;
  profile_reconciliation?: ProfileReconciliationSummary | null;
};

export type PersonalModelRawEntry = {
  id: number | string;
  session_id?: string | null;
  module_key?: string | null;
  question_id?: string | null;
  question_text?: string | null;
  answer_text?: string | null;
  answer_kind?: string | null;
  answer_value?: Record<string, unknown>;
  source?: string | null;
  confidence_type?: string | null;
  confidence?: number | null;
  explicit?: boolean;
  created_at?: string | null;
  metadata?: Record<string, unknown>;
};

export type PersonalModelSuggestion = {
  id: string;
  source?: string | null;
  category?: string | null;
  fact_key?: string | null;
  title?: string | null;
  prompt?: string | null;
  proposed_value_text?: string | null;
  proposed_value_json?: Record<string, unknown>;
  confidence?: number | null;
  confidence_percent?: number | null;
  confidence_label?: string | null;
  scope?: string | null;
  sensitive?: boolean;
  status?: "pending" | "accepted" | "rejected" | string;
  evidence?: Record<string, unknown>;
  learning_reason?: string | null;
  why_asked?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ProfileReconciliationChange = {
  field: string;
  title?: string | null;
  fact_key?: string | null;
  fact_id?: string | number | null;
  direction?: string | null;
  authority_mode?: string | null;
  authority_family?: string | null;
};

export type ProfileReconciliationSummary = {
  authority?: string | null;
  authority_model?: string | null;
  requested_authority?: string | null;
  changed?: boolean;
  synced_facts?: ProfileReconciliationChange[];
  hydrated_fields?: ProfileReconciliationChange[];
  claim_projection_fields?: ProfileReconciliationChange[];
  settings_fields?: ProfileReconciliationChange[];
};

export type PersonalModelOverview = {
  generated_at?: string | null;
  active_session?: PersonalModelSession | null;
  sessions: PersonalModelSession[];
  modules: Array<{
    key: string;
    title: string;
    description?: string | null;
    question_count: number;
    answered_count: number;
    complete: boolean;
  }>;
  facts: PersonalModelFact[];
  raw_entries: PersonalModelRawEntry[];
  pending_suggestions: PersonalModelSuggestion[];
  profile_summary: {
    generated_at?: string | null;
    fact_count?: number;
    sections?: Array<{ category: string; title: string; facts: PersonalModelFact[] }>;
    markdown?: string | null;
    assistant_guidance?: PersonalModelFact[];
  };
  usage_policy?: Record<string, unknown>;
};

export type PersonalModelRetrievalPreview = {
  query: string;
  intent?: { name?: string; categories?: string[] };
  selected_categories?: string[];
  facts: PersonalModelFact[];
  assistant_context_pack?: AssistantContextPackEntry[];
  summary_lines?: string[];
  usage_note?: string | null;
};

export type AssistantContextPackEntry = {
  id?: string | null;
  family?: string | null;
  item_kind?: string | null;
  source_type?: string | null;
  source_ref?: string | null;
  subject_key?: string | null;
  predicate?: string | null;
  title?: string | null;
  summary?: string | null;
  scope?: string | null;
  claim_status?: string | null;
  basis?: string | null;
  freshness?: string | null;
  assistant_visibility?: "visible" | "blocked" | string | null;
  why_visible?: string | null;
  why_blocked?: string | null;
  retrieval_eligibility?: string | null;
  sensitive?: boolean | null;
  memory_tier?: string | null;
  profile_kind?: string | null;
  support_strength?: string | null;
  priority?: number | null;
  prompt_line?: string | null;
  metadata?: Record<string, unknown>;
};
