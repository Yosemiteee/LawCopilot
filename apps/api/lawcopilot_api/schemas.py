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


class AssistantActionGenerateRequest(BaseModel):
    action_type: str = Field(
        pattern="^(send_email|reply_email|send_telegram_message|send_whatsapp_message|post_x_update|reserve_travel_ticket|create_task|prepare_client_update|prepare_internal_summary)$"
    )
    matter_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, max_length=240)
    instructions: str | None = Field(default=None, max_length=1600)
    target_channel: str | None = Field(default=None, pattern="^(email|telegram|whatsapp|x|travel|internal|task)$")
    to_contact: str | None = Field(default=None, max_length=255)
    source_refs: list[dict] | None = Field(default=None, max_length=20)


class AssistantActionDecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1200)


class AssistantDraftSendRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1200)


class AssistantThreadMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    matter_id: int | None = Field(default=None, gt=0)
    source_refs: list[dict] | None = Field(default=None, max_length=20)


class AssistantCalendarEventCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    starts_at: datetime
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    matter_id: int | None = Field(default=None, gt=0)
    needs_preparation: bool = True
    provider: str = Field(default="lawcopilot-planner", pattern=r"^[a-z0-9_-]{2,64}$")
    external_id: str | None = Field(default=None, max_length=255)
    status: str = Field(default="confirmed", pattern="^(confirmed|tentative|cancelled|open)$")
    attendees: list[str] = Field(default_factory=list, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)
    metadata: dict | None = None


class GoogleEmailThreadMirrorRequest(BaseModel):
    provider: str = Field(default="google")
    thread_ref: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=500)
    snippet: str | None = Field(default=None, max_length=4000)
    sender: str | None = Field(default=None, max_length=255)
    received_at: datetime | None = None
    unread_count: int = Field(default=0, ge=0, le=9999)
    reply_needed: bool = True
    matter_id: int | None = Field(default=None, gt=0)
    metadata: dict | None = None


class GoogleCalendarEventMirrorRequest(BaseModel):
    provider: str = Field(default="google")
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    starts_at: datetime
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    matter_id: int | None = Field(default=None, gt=0)
    metadata: dict | None = None


class GoogleDriveFileMirrorRequest(BaseModel):
    provider: str = Field(default="google")
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=500)
    mime_type: str | None = Field(default=None, max_length=120)
    web_view_link: str | None = Field(default=None, max_length=1000)
    modified_at: datetime | None = None


class GoogleSyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    scopes: list[str] | None = Field(default=None, max_length=20)
    email_threads: list[GoogleEmailThreadMirrorRequest] = Field(default_factory=list, max_length=50)
    calendar_events: list[GoogleCalendarEventMirrorRequest] = Field(default_factory=list, max_length=50)
    drive_files: list[GoogleDriveFileMirrorRequest] = Field(default_factory=list, max_length=50)
    synced_at: datetime | None = None


class WhatsAppMessageMirrorRequest(BaseModel):
    provider: str = Field(default="whatsapp")
    conversation_ref: str = Field(min_length=1, max_length=255)
    message_ref: str = Field(min_length=1, max_length=255)
    sender: str | None = Field(default=None, max_length=255)
    recipient: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
    direction: str = Field(default="inbound", pattern="^(inbound|outbound)$")
    sent_at: datetime | None = None
    reply_needed: bool = False
    matter_id: int | None = Field(default=None, gt=0)
    metadata: dict | None = None


class WhatsAppSyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    phone_number_id: str | None = Field(default=None, max_length=255)
    display_phone_number: str | None = Field(default=None, max_length=255)
    verified_name: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=1000)
    messages: list[WhatsAppMessageMirrorRequest] = Field(default_factory=list, max_length=100)
    synced_at: datetime | None = None


class XPostMirrorRequest(BaseModel):
    provider: str = Field(default="x")
    external_id: str = Field(min_length=1, max_length=255)
    post_type: str = Field(default="post", pattern="^(post|mention|reply)$")
    author_handle: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1, max_length=4000)
    posted_at: datetime | None = None
    reply_needed: bool = False
    metadata: dict | None = None


class XSyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    user_id: str | None = Field(default=None, max_length=255)
    scopes: list[str] | None = Field(default=None, max_length=20)
    mentions: list[XPostMirrorRequest] = Field(default_factory=list, max_length=50)
    posts: list[XPostMirrorRequest] = Field(default_factory=list, max_length=50)
    synced_at: datetime | None = None


class AssistantDispatchReportRequest(BaseModel):
    action_id: int | None = Field(default=None, gt=0)
    external_message_id: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=1200)
    error: str | None = Field(default=None, max_length=2000)


class ProfileImportantDateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    date: str = Field(min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")
    recurring_annually: bool = True
    notes: str | None = Field(default=None, max_length=600)


class RelatedProfileRequest(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    relationship: str | None = Field(default=None, max_length=120)
    preferences: str | None = Field(default=None, max_length=1600)
    notes: str | None = Field(default=None, max_length=1600)
    important_dates: list[ProfileImportantDateRequest] = Field(default_factory=list, max_length=12)


class UserProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)
    favorite_color: str | None = Field(default=None, max_length=120)
    food_preferences: str | None = Field(default=None, max_length=1200)
    transport_preference: str | None = Field(default=None, max_length=240)
    weather_preference: str | None = Field(default=None, max_length=240)
    travel_preferences: str | None = Field(default=None, max_length=1200)
    communication_style: str | None = Field(default=None, max_length=600)
    assistant_notes: str | None = Field(default=None, max_length=2400)
    important_dates: list[ProfileImportantDateRequest] = Field(default_factory=list, max_length=24)
    related_profiles: list[RelatedProfileRequest] = Field(default_factory=list, max_length=24)


class AssistantRuntimeProfileRequest(BaseModel):
    assistant_name: str | None = Field(default=None, max_length=120)
    role_summary: str | None = Field(default=None, max_length=240)
    tone: str | None = Field(default=None, max_length=120)
    avatar_path: str | None = Field(default=None, max_length=800)
    soul_notes: str | None = Field(default=None, max_length=2400)
    tools_notes: str | None = Field(default=None, max_length=2400)
    heartbeat_extra_checks: list[str] = Field(default_factory=list, max_length=12)
