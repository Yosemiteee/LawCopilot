import type { AppSettings } from "../app/AppContext";
import type {
  ActivityResponse,
  Citation,
  ChronologyResponse,
  DocumentChunk,
  Draft,
  GeneratedDraftResponse,
  Health,
  IngestionJob,
  Matter,
  MatterSummary,
  MatterDocument,
  MatterWorkspaceDocumentLink,
  ModelProfilesResponse,
  RiskNotesResponse,
  SearchResponse,
  SimilarDocumentsResponse,
  Task,
  TelemetryHealth,
  TaskRecommendationsResponse,
  TimelineEvent,
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

export function getTelemetryHealth(settings: AppSettings) {
  return apiRequest<TelemetryHealth>(settings, "/telemetry/health");
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
  }>(settings, "/query", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
