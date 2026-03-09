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
  telegram_enabled?: boolean;
  telegram_configured?: boolean;
  telegram_bot_username?: string;
  telegram_allowed_user_id?: string;
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
  manual_review_required?: boolean;
  created_by: string;
  approved_by?: string | null;
  created_at: string;
  updated_at: string;
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
  source_context: {
    documents?: string[];
    chronology?: string[];
    risk_notes?: string[];
    open_tasks?: string[];
  };
};
