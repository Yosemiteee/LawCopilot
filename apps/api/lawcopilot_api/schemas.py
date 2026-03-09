from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class QueryIn(BaseModel):
    model_config = {"protected_namespaces": ()}

    query: str = Field(min_length=3, max_length=8000)
    model_profile: str | None = None


class QueryJobCreateRequest(QueryIn):
    continue_in_background: bool = True


class TokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    role: str = Field(pattern="^(intern|lawyer|admin)$")
    bootstrap_key: str | None = None


class ConnectorPreviewRequest(BaseModel):
    destination: str = Field(min_length=3, max_length=255)
    message: str = Field(min_length=1, max_length=5000)


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    due_at: datetime | None = None
    priority: str = Field(pattern="^(low|medium|high)$")
    matter_id: int | None = Field(default=None, gt=0)
    origin_type: str | None = Field(default=None, pattern="^(manual|assistant|draft|document|timeline)$")
    origin_ref: str | None = Field(default=None, max_length=120)
    recommended_by: str | None = Field(default=None, max_length=120)
    explanation: str | None = Field(default=None, max_length=1200)


class TaskBulkCompleteRequest(BaseModel):
    task_ids: list[int] = Field(min_length=1, max_length=200)


class TaskStatusUpdateRequest(BaseModel):
    task_id: int = Field(gt=0)
    status: str = Field(pattern="^(open|in_progress|completed)$")


class TaskDueUpdateRequest(BaseModel):
    task_id: int = Field(gt=0)
    due_at: datetime | None = None


class CitationReviewRequest(BaseModel):
    answer: str = Field(min_length=5, max_length=12000)


class EmailDraftCreateRequest(BaseModel):
    matter_id: int | None = Field(default=None, gt=0)
    to_email: EmailStr
    subject: str = Field(min_length=3, max_length=250)
    body: str = Field(min_length=10, max_length=12000)


class EmailDraftApproveRequest(BaseModel):
    draft_id: int = Field(gt=0)


class EmailDraftRetractRequest(BaseModel):
    draft_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=500)


class SocialIngestRequest(BaseModel):
    source: str = Field(pattern="^(x|linkedin|instagram|news)$")
    handle: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=10, max_length=4000)


class MatterCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    reference_code: str | None = Field(default=None, max_length=64)
    practice_area: str | None = Field(default=None, max_length=120)
    status: str = Field(default="active", pattern="^(active|on_hold|closed)$")
    summary: str | None = Field(default=None, max_length=6000)
    client_name: str | None = Field(default=None, max_length=160)
    lead_lawyer: str | None = Field(default=None, max_length=160)
    opened_at: datetime | None = None


class MatterUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    reference_code: str | None = Field(default=None, max_length=64)
    practice_area: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, pattern="^(active|on_hold|closed)$")
    summary: str | None = Field(default=None, max_length=6000)
    client_name: str | None = Field(default=None, max_length=160)
    lead_lawyer: str | None = Field(default=None, max_length=160)
    opened_at: datetime | None = None


class MatterNoteCreateRequest(BaseModel):
    body: str = Field(min_length=3, max_length=12000)
    note_type: str = Field(default="working_note", pattern="^(working_note|client_note|internal_note|risk_note)$")
    event_at: datetime | None = None


class MatterDraftCreateRequest(BaseModel):
    draft_type: str = Field(
        default="client_update",
        pattern="^(client_update|internal_summary|intake_summary|first_case_assessment|missing_document_request|question_list|meeting_recap|meeting_summary|general)$",
    )
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=12000)
    target_channel: str = Field(default="internal", pattern="^(internal|email|client_portal)$")
    to_contact: str | None = Field(default=None, max_length=255)


class MatterDraftGenerateRequest(BaseModel):
    draft_type: str = Field(
        default="client_update",
        pattern="^(client_update|internal_summary|intake_summary|first_case_assessment|missing_document_request|question_list|meeting_recap|meeting_summary|general)$",
    )
    target_channel: str = Field(default="internal", pattern="^(internal|email|client_portal)$")
    to_contact: str | None = Field(default=None, max_length=255)
    instructions: str | None = Field(default=None, max_length=1200)


class MatterSearchRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    query: str = Field(min_length=3, max_length=8000)
    model_profile: str | None = None
    limit: int = Field(default=5, ge=1, le=20)
    document_ids: list[int] | None = Field(default=None, max_length=50)
    source_types: list[str] | None = Field(default=None, max_length=20)
    filename_contains: str | None = Field(default=None, max_length=120)


class WorkspaceRootRequest(BaseModel):
    root_path: str = Field(min_length=1, max_length=4096)
    display_name: str | None = Field(default=None, max_length=255)


class WorkspaceScanRequest(BaseModel):
    full_rescan: bool = False
    extensions: list[str] | None = Field(default=None, max_length=20)


class WorkspaceSearchRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    query: str = Field(min_length=3, max_length=8000)
    limit: int = Field(default=5, ge=1, le=20)
    path_prefix: str | None = Field(default=None, max_length=1024)
    extensions: list[str] | None = Field(default=None, max_length=20)


class SimilarDocumentsRequest(BaseModel):
    query: str | None = Field(default=None, max_length=8000)
    document_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=5, ge=1, le=20)
    path_prefix: str | None = Field(default=None, max_length=1024)


class WorkspaceAttachRequest(BaseModel):
    workspace_document_id: int = Field(gt=0)
