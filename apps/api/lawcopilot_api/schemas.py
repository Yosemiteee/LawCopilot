from datetime import datetime
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class QueryIn(BaseModel):
    model_config = {"protected_namespaces": ()}

    query: str = Field(min_length=3, max_length=8000)
    model_profile: str | None = None
    allow_writeback: bool = False


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
    to_email: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=3, max_length=250)
    body: str = Field(min_length=10, max_length=12000)

    @field_validator("to_email")
    @classmethod
    def validate_to_email(cls, value: str) -> str:
        candidate = str(value or "").strip()
        if not EMAIL_RE.match(candidate):
            raise ValueError("Geçerli bir e-posta adresi girin.")
        return candidate


class EmailDraftApproveRequest(BaseModel):
    draft_id: int = Field(gt=0)


class EmailDraftRetractRequest(BaseModel):
    draft_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=500)


class SocialIngestRequest(BaseModel):
    source: str = Field(pattern="^(x|linkedin|instagram|news|website|blog|forum)$")
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
        pattern="^(client_update|internal_summary|intake_summary|first_case_assessment|missing_document_request|question_list|meeting_recap|meeting_summary|petition|general)$",
    )
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=12000)
    target_channel: str = Field(default="internal", pattern="^(internal|email|client_portal)$")
    to_contact: str | None = Field(default=None, max_length=255)


class MatterDraftGenerateRequest(BaseModel):
    draft_type: str = Field(
        default="client_update",
        pattern="^(client_update|internal_summary|intake_summary|first_case_assessment|missing_document_request|question_list|meeting_recap|meeting_summary|petition|general)$",
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
        pattern="^(send_email|reply_email|send_telegram_message|send_whatsapp_message|send_instagram_message|send_linkedin_message|post_x_update|post_linkedin_update|reserve_travel_ticket|create_task|prepare_client_update|prepare_internal_summary)$"
    )
    matter_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, max_length=240)
    instructions: str | None = Field(default=None, max_length=1600)
    target_channel: str | None = Field(default=None, pattern="^(email|telegram|whatsapp|instagram|x|linkedin|travel|internal|task)$")
    to_contact: str | None = Field(default=None, max_length=255)
    source_refs: list[dict] | None = Field(default=None, max_length=20)


class AssistantActionDecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1200)


class AssistantDraftSendRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1200)


class AssistantShareDraftCreateRequest(BaseModel):
    channel: str = Field(pattern="^(whatsapp|telegram|instagram|email|x|linkedin)$")
    content: str = Field(min_length=1, max_length=12000)
    to_contact: str | None = Field(default=None, max_length=255)
    subject: str | None = Field(default=None, max_length=240)
    thread_id: int | None = Field(default=None, gt=0)
    message_id: int | None = Field(default=None, gt=0)
    contact_profile_id: str | None = Field(default=None, max_length=255)


class AssistantThreadMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    thread_id: int | None = Field(default=None, gt=0)
    edit_message_id: int | None = Field(default=None, gt=0)
    matter_id: int | None = Field(default=None, gt=0)
    source_refs: list[dict] | None = Field(default=None, max_length=20)


class AssistantThreadSystemMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    thread_id: int | None = Field(default=None, gt=0)
    source_context: dict[str, Any] | None = None


class AssistantThreadCreateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


class AssistantThreadUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class AssistantThreadMessageStarRequest(BaseModel):
    starred: bool


class AssistantThreadMessageFeedbackRequest(BaseModel):
    feedback_value: str = Field(pattern="^(liked|disliked|none)$")
    note: str | None = Field(default=None, max_length=500)


class AgentRunCreateRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=8000)
    title: str | None = Field(default=None, max_length=240)
    matter_id: int | None = Field(default=None, gt=0)
    thread_id: int | None = Field(default=None, gt=0)
    source_kind: str = Field(default="assistant", pattern="^(assistant|workbench|automation|api)$")
    run_type: str = Field(default="investigation", pattern="^(investigation|research|review|automation)$")
    preferred_tools: list[str] | None = Field(default=None, max_length=20)
    source_refs: list[dict] | None = Field(default=None, max_length=20)
    mode: str | None = Field(default=None, pattern="^(research|review|investigation|automation)$")
    render_mode: str = Field(default="auto", pattern="^(auto|cheap|browser)$")
    strategy: str | None = Field(default=None, pattern="^(auto|cheap|browser)$")
    allow_browser: bool = True


class AgentRunDecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1200)


class WebIntelExtractRequest(BaseModel):
    url: str = Field(min_length=5, max_length=2000)
    render_mode: str = Field(default="auto", pattern="^(auto|cheap|browser)$")
    include_screenshot: bool = True
    strategy: str | None = Field(default=None, pattern="^(auto|cheap|browser)$")
    allow_browser: bool = True


class VideoAnalyzeRequest(BaseModel):
    url: str = Field(min_length=5, max_length=2000)
    transcript_text: str | None = Field(default=None, max_length=50000)
    max_segments: int = Field(default=40, ge=5, le=400)
    strategy: str = Field(default="transcript-first", pattern="^(transcript-first|audio-transcribe|frame-sample)$")


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


class GoogleYouTubePlaylistMirrorRequest(BaseModel):
    provider: str = Field(default="youtube")
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=4000)
    privacy_status: str | None = Field(default=None, max_length=80)
    item_count: int = Field(default=0, ge=0, le=100000)
    channel_title: str | None = Field(default=None, max_length=255)
    web_view_link: str | None = Field(default=None, max_length=1000)
    published_at: datetime | None = None
    thumbnails: dict | None = None
    items: list[dict[str, Any]] = Field(default_factory=list, max_length=20)


class GoogleYouTubeHistoryMirrorRequest(BaseModel):
    provider: str = Field(default="youtube")
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    channel_title: str | None = Field(default=None, max_length=255)
    viewed_at: datetime | None = None
    metadata: dict | None = None


class GoogleChromeHistoryMirrorRequest(BaseModel):
    provider: str = Field(default="chrome")
    external_id: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=500)
    url: str = Field(min_length=1, max_length=2000)
    visited_at: datetime | None = None
    metadata: dict | None = None


class GoogleSyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    scopes: list[str] | None = Field(default=None, max_length=20)
    email_threads: list[GoogleEmailThreadMirrorRequest] = Field(default_factory=list, max_length=50)
    calendar_events: list[GoogleCalendarEventMirrorRequest] = Field(default_factory=list, max_length=50)
    drive_files: list[GoogleDriveFileMirrorRequest] = Field(default_factory=list, max_length=50)
    youtube_playlists: list[GoogleYouTubePlaylistMirrorRequest] = Field(default_factory=list, max_length=50)
    synced_at: datetime | None = None
    cursor: str | None = Field(default=None, max_length=255)
    checkpoint: dict | None = None


class GooglePortabilitySyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    scopes: list[str] | None = Field(default=None, max_length=20)
    youtube_history_entries: list[GoogleYouTubeHistoryMirrorRequest] = Field(default_factory=list, max_length=200)
    chrome_history_entries: list[GoogleChromeHistoryMirrorRequest] = Field(default_factory=list, max_length=200)
    synced_at: datetime | None = None
    cursor: str | None = Field(default=None, max_length=255)
    checkpoint: dict | None = None


class OutlookEmailThreadMirrorRequest(BaseModel):
    provider: str = Field(default="outlook")
    thread_ref: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=500)
    snippet: str | None = Field(default=None, max_length=4000)
    sender: str | None = Field(default=None, max_length=255)
    received_at: datetime | None = None
    unread_count: int = Field(default=0, ge=0, le=9999)
    reply_needed: bool = True
    matter_id: int | None = Field(default=None, gt=0)
    metadata: dict | None = None


class OutlookCalendarEventMirrorRequest(BaseModel):
    provider: str = Field(default="outlook")
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    starts_at: datetime
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    matter_id: int | None = Field(default=None, gt=0)
    metadata: dict | None = None


class OutlookSyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    scopes: list[str] | None = Field(default=None, max_length=20)
    email_threads: list[OutlookEmailThreadMirrorRequest] = Field(default_factory=list, max_length=50)
    calendar_events: list[OutlookCalendarEventMirrorRequest] = Field(default_factory=list, max_length=150)
    synced_at: datetime | None = None
    cursor: str | None = Field(default=None, max_length=255)
    checkpoint: dict | None = None


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


class WhatsAppContactMirrorRequest(BaseModel):
    provider: str = Field(default="whatsapp")
    conversation_ref: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    profile_name: str | None = Field(default=None, max_length=255)
    phone_number: str | None = Field(default=None, max_length=64)
    is_group: bool = False
    group_name: str | None = Field(default=None, max_length=255)
    last_seen_at: datetime | None = None
    metadata: dict | None = None


class WhatsAppSyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    phone_number_id: str | None = Field(default=None, max_length=255)
    display_phone_number: str | None = Field(default=None, max_length=255)
    verified_name: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=1000)
    messages: list[WhatsAppMessageMirrorRequest] = Field(default_factory=list, max_length=100)
    contacts: list[WhatsAppContactMirrorRequest] = Field(default_factory=list, max_length=600)
    synced_at: datetime | None = None
    cursor: str | None = Field(default=None, max_length=255)
    checkpoint: dict | None = None


class TelegramMessageMirrorRequest(BaseModel):
    provider: str = Field(default="telegram")
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


class TelegramSyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    bot_username: str | None = Field(default=None, max_length=255)
    allowed_user_id: str | None = Field(default=None, max_length=255)
    scopes: list[str] | None = Field(default=None, max_length=20)
    messages: list[TelegramMessageMirrorRequest] = Field(default_factory=list, max_length=100)
    synced_at: datetime | None = None
    cursor: str | None = Field(default=None, max_length=255)
    checkpoint: dict | None = None


class XPostMirrorRequest(BaseModel):
    provider: str = Field(default="x")
    external_id: str = Field(min_length=1, max_length=255)
    post_type: str = Field(default="post", pattern="^(post|mention|reply)$")
    author_handle: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1, max_length=4000)
    posted_at: datetime | None = None
    reply_needed: bool = False
    metadata: dict | None = None


class XMessageMirrorRequest(BaseModel):
    provider: str = Field(default="x")
    conversation_ref: str = Field(min_length=1, max_length=255)
    message_ref: str = Field(min_length=1, max_length=255)
    sender: str | None = Field(default=None, max_length=255)
    recipient: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
    direction: str = Field(default="inbound", pattern="^(inbound|outbound)$")
    sent_at: datetime | None = None
    reply_needed: bool = False
    metadata: dict | None = None


class XSyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    user_id: str | None = Field(default=None, max_length=255)
    scopes: list[str] | None = Field(default=None, max_length=20)
    mentions: list[XPostMirrorRequest] = Field(default_factory=list, max_length=50)
    posts: list[XPostMirrorRequest] = Field(default_factory=list, max_length=50)
    messages: list[XMessageMirrorRequest] = Field(default_factory=list, max_length=100)
    synced_at: datetime | None = None


class InstagramMessageMirrorRequest(BaseModel):
    provider: str = Field(default="instagram")
    conversation_ref: str = Field(min_length=1, max_length=255)
    message_ref: str = Field(min_length=1, max_length=255)
    sender: str | None = Field(default=None, max_length=255)
    recipient: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
    direction: str = Field(default="inbound", pattern="^(inbound|outbound)$")
    sent_at: datetime | None = None
    reply_needed: bool = False
    metadata: dict | None = None


class InstagramSyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    instagram_account_id: str | None = Field(default=None, max_length=255)
    page_id: str | None = Field(default=None, max_length=255)
    page_name: str | None = Field(default=None, max_length=255)
    scopes: list[str] | None = Field(default=None, max_length=20)
    messages: list[InstagramMessageMirrorRequest] = Field(default_factory=list, max_length=100)
    synced_at: datetime | None = None
    cursor: str | None = Field(default=None, max_length=255)
    checkpoint: dict | None = None


class LinkedInPostMirrorRequest(BaseModel):
    provider: str = Field(default="linkedin")
    external_id: str = Field(min_length=1, max_length=255)
    author_handle: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=0, max_length=4000)
    posted_at: datetime | None = None
    reply_needed: bool = False
    metadata: dict | None = None


class LinkedInCommentMirrorRequest(BaseModel):
    provider: str = Field(default="linkedin")
    external_id: str = Field(min_length=1, max_length=255)
    object_urn: str | None = Field(default=None, max_length=255)
    parent_external_id: str | None = Field(default=None, max_length=255)
    author_handle: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1, max_length=4000)
    posted_at: datetime | None = None
    reply_needed: bool = False
    metadata: dict | None = None


class LinkedInMessageMirrorRequest(BaseModel):
    provider: str = Field(default="linkedin")
    conversation_ref: str = Field(min_length=1, max_length=255)
    message_ref: str = Field(min_length=1, max_length=255)
    sender: str | None = Field(default=None, max_length=255)
    recipient: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
    direction: str = Field(default="inbound", pattern="^(inbound|outbound)$")
    sent_at: datetime | None = None
    reply_needed: bool = False
    metadata: dict | None = None


class LinkedInSyncRequest(BaseModel):
    account_label: str | None = Field(default=None, max_length=255)
    user_id: str | None = Field(default=None, max_length=255)
    person_urn: str | None = Field(default=None, max_length=255)
    scopes: list[str] | None = Field(default=None, max_length=20)
    posts: list[LinkedInPostMirrorRequest] = Field(default_factory=list, max_length=100)
    comments: list[LinkedInCommentMirrorRequest] = Field(default_factory=list, max_length=200)
    messages: list[LinkedInMessageMirrorRequest] = Field(default_factory=list, max_length=100)
    synced_at: datetime | None = None
    cursor: str | None = Field(default=None, max_length=255)
    checkpoint: dict | None = None


class AssistantDispatchReportRequest(BaseModel):
    action_id: int | None = Field(default=None, gt=0)
    dispatch_attempt_id: int | None = Field(default=None, gt=0)
    external_message_id: str | None = Field(default=None, max_length=255)
    provider: str | None = Field(default=None, max_length=80)
    external_receipt_id: str | None = Field(default=None, max_length=255)
    external_reference: str | None = Field(default=None, max_length=255)
    receipt_status: str | None = Field(default=None, max_length=80)
    receipt_payload: dict[str, Any] | None = None
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
    closeness: int | None = Field(default=None, ge=1, le=5)
    preferences: str | None = Field(default=None, max_length=1600)
    notes: str | None = Field(default=None, max_length=1600)
    important_dates: list[ProfileImportantDateRequest] = Field(default_factory=list, max_length=12)


class ContactProfileOverrideRequest(BaseModel):
    contact_id: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=4000)
    updated_at: str | None = Field(default=None, max_length=40)


class InboxWatchRuleRequest(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    match_type: str = Field(pattern="^(person|group)$")
    match_value: str = Field(min_length=1, max_length=240)
    channels: list[str] = Field(default_factory=list, max_length=8)


class InboxKeywordRuleRequest(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    keyword: str = Field(min_length=1, max_length=120)
    label: str | None = Field(default=None, max_length=160)
    channels: list[str] = Field(default_factory=list, max_length=8)


class InboxBlockRuleRequest(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    match_type: str = Field(pattern="^(person|group)$")
    match_value: str = Field(min_length=1, max_length=240)
    channels: list[str] = Field(default_factory=list, max_length=8)
    duration_kind: str = Field(pattern="^(day|month|forever)$")
    starts_at: str | None = Field(default=None, max_length=40)
    expires_at: str | None = Field(default=None, max_length=40)


class SourcePreferenceRuleRequest(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    label: str | None = Field(default=None, max_length=120)
    task_kind: str = Field(default="general_research", min_length=2, max_length=80)
    policy_mode: str = Field(default="prefer", pattern="^(prefer|restrict)$")
    preferred_domains: list[str] = Field(default_factory=list, max_length=12)
    preferred_links: list[str] = Field(default_factory=list, max_length=8)
    preferred_providers: list[str] = Field(default_factory=list, max_length=8)
    note: str | None = Field(default=None, max_length=280)


class UserProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)
    favorite_color: str | None = Field(default=None, max_length=120)
    food_preferences: str | None = Field(default=None, max_length=1200)
    transport_preference: str | None = Field(default=None, max_length=240)
    weather_preference: str | None = Field(default=None, max_length=240)
    travel_preferences: str | None = Field(default=None, max_length=1200)
    home_base: str | None = Field(default=None, max_length=160)
    current_location: str | None = Field(default=None, max_length=200)
    location_preferences: str | None = Field(default=None, max_length=1200)
    maps_preference: str | None = Field(default=None, max_length=120)
    prayer_notifications_enabled: bool = False
    prayer_habit_notes: str | None = Field(default=None, max_length=600)
    communication_style: str | None = Field(default=None, max_length=600)
    assistant_notes: str | None = Field(default=None, max_length=2400)
    important_dates: list[ProfileImportantDateRequest] = Field(default_factory=list, max_length=24)
    related_profiles: list[RelatedProfileRequest] = Field(default_factory=list, max_length=24)
    contact_profile_overrides: list[ContactProfileOverrideRequest] = Field(default_factory=list, max_length=200)
    inbox_watch_rules: list[InboxWatchRuleRequest] = Field(default_factory=list, max_length=40)
    inbox_keyword_rules: list[InboxKeywordRuleRequest] = Field(default_factory=list, max_length=40)
    inbox_block_rules: list[InboxBlockRuleRequest] = Field(default_factory=list, max_length=40)
    source_preference_rules: list[SourcePreferenceRuleRequest] = Field(default_factory=list, max_length=24)


class AssistantRuntimeProfileRequest(BaseModel):
    assistant_name: str | None = Field(default=None, max_length=120)
    role_summary: str | None = Field(default=None, max_length=240)
    tone: str | None = Field(default=None, max_length=120)
    avatar_path: str | None = Field(default=None, max_length=800)
    soul_notes: str | None = Field(default=None, max_length=2400)
    tools_notes: str | None = Field(default=None, max_length=2400)
    assistant_forms: list[dict] = Field(default_factory=list, max_length=24)
    behavior_contract: dict = Field(default_factory=dict)
    evolution_history: list[dict] = Field(default_factory=list, max_length=80)
    heartbeat_extra_checks: list[str] = Field(default_factory=list, max_length=12)


class AssistantRuntimeBlueprintRequest(BaseModel):
    description: str = Field(min_length=3, max_length=2000)


class KnowledgeBaseIngestRequest(BaseModel):
    source_type: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    occurred_at: datetime | None = None
    source_ref: str | None = Field(default=None, max_length=4096)
    tags: list[str] = Field(default_factory=list, max_length=20)
    metadata: dict | None = None


class KnowledgeBaseSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    scopes: list[str] = Field(default_factory=list, max_length=12)
    page_keys: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=8, ge=1, le=20)
    include_decisions: bool = True
    include_reflections: bool = True
    metadata_filters: dict | None = None
    record_types: list[str] = Field(default_factory=list, max_length=20)


class KnowledgeWikiCompileRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=120)
    previews: bool = False
    background: bool = False


class KnowledgeSynthesisRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=120)
    background: bool = False


class KnowledgeReflectionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=120)
    background: bool = False


class KnowledgeMemoryCorrectionRequest(BaseModel):
    action: str = Field(pattern="^(correct|forget|change_scope|reduce_confidence|suppress_recommendation|boost_proactivity)$")
    page_key: str | None = Field(default=None, max_length=40)
    target_record_id: str | None = Field(default=None, max_length=240)
    key: str | None = Field(default=None, max_length=240)
    corrected_summary: str | None = Field(default=None, max_length=2000)
    scope: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=500)
    recommendation_kind: str | None = Field(default=None, max_length=120)
    topic: str | None = Field(default=None, max_length=120)
    source_refs: list[dict | str] = Field(default_factory=list, max_length=20)


class MemoryForgetRequest(BaseModel):
    page_key: str | None = Field(default=None, max_length=40)
    target_record_id: str = Field(min_length=1, max_length=240)
    note: str | None = Field(default=None, max_length=500)
    source_refs: list[dict | str] = Field(default_factory=list, max_length=20)


class MemoryScopeChangeRequest(BaseModel):
    page_key: str | None = Field(default=None, max_length=40)
    target_record_id: str = Field(min_length=1, max_length=240)
    scope: str = Field(min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=500)
    source_refs: list[dict | str] = Field(default_factory=list, max_length=20)


class ChannelMemoryStateUpdateRequest(BaseModel):
    channel_type: str = Field(
        pattern="^(email_thread|whatsapp_message|telegram_message|x_post|x_message|instagram_message|linkedin_post|linkedin_comment|linkedin_message)$"
    )
    record_id: int = Field(ge=1)
    memory_state: str = Field(pattern="^(operational_only|candidate_memory|approved_memory)$")
    note: str | None = Field(default=None, max_length=500)


class PersonalModelSessionStartRequest(BaseModel):
    module_keys: list[str] = Field(default_factory=list, max_length=12)
    scope: str = Field(default="global", min_length=1, max_length=160)
    source: str = Field(default="guided_interview", min_length=1, max_length=80)


class PersonalModelInterviewAnswerRequest(BaseModel):
    answer_text: str = Field(min_length=1, max_length=2000)
    choice_value: str | None = Field(default=None, max_length=120)
    answer_kind: str = Field(default="text", pattern="^(text|choice|voice_transcript)$")


class PersonalModelFactUpdateRequest(BaseModel):
    value_text: str | None = Field(default=None, max_length=1000)
    scope: str | None = Field(default=None, max_length=160)
    enabled: bool | None = None
    never_use: bool | None = None
    sensitive: bool | None = None
    visibility: str | None = Field(default=None, max_length=80)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    note: str | None = Field(default=None, max_length=500)


class PersonalModelSuggestionReviewRequest(BaseModel):
    decision: str = Field(pattern="^(accept|reject)$")


class PersonalModelRetrievalPreviewRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    scopes: list[str] = Field(default_factory=list, max_length=12)
    limit: int = Field(default=6, ge=1, le=12)


class ConnectorSyncTriggerRequest(BaseModel):
    connector_names: list[str] = Field(default_factory=list, max_length=20)
    reason: str | None = Field(default=None, max_length=120)
    trigger: str | None = Field(default=None, max_length=80)


class AssistantLocationContextRequest(BaseModel):
    current_place: dict | None = None
    recent_places: list[dict] = Field(default_factory=list, max_length=40)
    nearby_categories: list[str] = Field(default_factory=list, max_length=20)
    observed_at: datetime | None = None
    source: str | None = Field(default=None, max_length=80)
    scope: str | None = Field(default=None, max_length=160)
    sensitivity: str | None = Field(default=None, max_length=40)
    source_ref: str | None = Field(default=None, max_length=2048)
    provider: str | None = Field(default=None, max_length=120)
    provider_mode: str | None = Field(default=None, max_length=120)
    provider_status: str | None = Field(default=None, max_length=80)
    capture_mode: str | None = Field(default=None, max_length=80)
    permission_state: str | None = Field(default=None, max_length=80)
    privacy_mode: bool | None = None
    capture_failure_reason: str | None = Field(default=None, max_length=600)
    persist_raw: bool = True


class TriggerEvaluationRequest(BaseModel):
    forced_types: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=4, ge=1, le=12)
    include_suppressed: bool = False
    persist: bool = True


class OrchestrationRunRequest(BaseModel):
    job_names: list[str] = Field(default_factory=list, max_length=20)
    reason: str | None = Field(default=None, max_length=120)
    force: bool = False
    background: bool = False


class RuntimeJobProcessRequest(BaseModel):
    worker_kind: str = Field(default="knowledge_base", pattern="^(knowledge_base)$")
    limit: int = Field(default=4, ge=1, le=20)


class CoachingGoalUpsertRequest(BaseModel):
    goal_id: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=3, max_length=160)
    summary: str | None = Field(default=None, max_length=800)
    cadence: str = Field(default="daily", pattern="^(daily|weekly|flexible|one_time)$")
    target_value: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=48)
    scope: str | None = Field(default="personal", max_length=160)
    sensitivity: str | None = Field(default="high", max_length=40)
    reminder_time: str | None = Field(default=None, max_length=16)
    preferred_days: list[str] = Field(default_factory=list, max_length=7)
    target_date: str | None = Field(default=None, max_length=40)
    allow_desktop_notifications: bool = True
    note: str | None = Field(default=None, max_length=400)
    source_refs: list[dict | str] = Field(default_factory=list, max_length=20)


class CoachingProgressLogRequest(BaseModel):
    amount: float | None = Field(default=None)
    note: str | None = Field(default=None, max_length=500)
    completed: bool = False
    happened_at: datetime | None = None


class DecisionRecordCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    summary: str = Field(min_length=3, max_length=4000)
    intent: str | None = Field(default=None, max_length=120)
    source_refs: list[dict | str] = Field(default_factory=list, max_length=20)
    reasoning_summary: str = Field(min_length=3, max_length=4000)
    confidence: float = Field(ge=0.0, le=1.0)
    user_confirmation_required: bool = False
    possible_risks: list[str] = Field(default_factory=list, max_length=20)
    action_kind: str | None = Field(default=None, max_length=120)
    alternatives: list[str] = Field(default_factory=list, max_length=20)


class RecommendationRequest(BaseModel):
    current_context: str | None = Field(default=None, max_length=2000)
    location_context: str | None = Field(default=None, max_length=255)
    limit: int = Field(default=3, ge=1, le=10)
    persist: bool = True


class RecommendationFeedbackRequest(BaseModel):
    outcome: str = Field(pattern="^(accepted|rejected|ignored)$")
    note: str | None = Field(default=None, max_length=500)


class ProactiveHookRequest(BaseModel):
    context: dict | None = None
    user_prompt: str | None = Field(default=None, max_length=2000)
    persist: bool = True
