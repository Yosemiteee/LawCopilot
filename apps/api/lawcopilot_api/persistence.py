from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .assistant_core import DEFAULT_ASSISTANT_ROLE_SUMMARY, DEFAULT_ASSISTANT_TONE


class Persistence:
    CHANNEL_MEMORY_STATES = frozenset({"operational_only", "candidate_memory", "approved_memory"})
    ASSISTANT_CONTEXT_SNAPSHOT_RETENTION_DAYS = 90
    ASSISTANT_CONTEXT_SNAPSHOT_MAX_PER_THREAD = 120
    _UNSET = object()
    _SNAPSHOT_TEXT_KEYS = frozenset(
        {
            "attachment_context",
            "body",
            "content",
            "details",
            "effective_query",
            "message",
            "message_text",
            "original_query",
            "prompt_line",
            "query",
            "raw_content",
            "raw_payload",
            "raw_text",
            "response_text",
            "snippet",
            "summary",
            "text",
            "title",
            "value_text",
            "why_blocked",
            "why_visible",
        }
    )
    _SNAPSHOT_ALLOWED_CONTEXT_ITEM_KEYS = frozenset(
        {
            "id",
            "family",
            "item_kind",
            "source_type",
            "source_ref",
            "subject_key",
            "predicate",
            "scope",
            "claim_status",
            "basis",
            "freshness",
            "assistant_visibility",
            "retrieval_eligibility",
            "sensitive",
            "memory_tier",
            "profile_kind",
            "support_strength",
            "priority",
        }
    )
    _SUSPICIOUS_GENERIC_RELATED_PROFILES = {
        "sibling": {
            "ids": frozenset({"sibling"}),
            "names": frozenset({"kardes", "kardeş"}),
            "relationships": frozenset({"kardes", "kardeş"}),
            "evidence_aliases": (),
        },
        "partner": {
            "ids": frozenset({"partner"}),
            "names": frozenset({"es", "sevgili", "partner"}),
            "relationships": frozenset({"es", "sevgili", "partner"}),
            "evidence_aliases": ("esim", "eşim", "sevgilim", "karim", "kocam", "partnerim"),
        },
    }

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS offices (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    deployment_mode TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS matters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    reference_code TEXT,
                    practice_area TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    summary TEXT,
                    client_name TEXT,
                    lead_lawyer TEXT,
                    opened_at TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS matter_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matter_id INTEGER NOT NULL,
                    note_type TEXT NOT NULL,
                    body TEXT NOT NULL,
                    event_at TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS matter_timeline_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matter_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    details TEXT,
                    event_at TEXT NOT NULL,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matter_id INTEGER NOT NULL,
                    office_id TEXT NOT NULL,
                    draft_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    target_channel TEXT NOT NULL,
                    to_contact TEXT,
                    source_context_json TEXT,
                    generated_from TEXT,
                    manual_review_required INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL,
                    approved_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    matter_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    content_type TEXT,
                    source_type TEXT NOT NULL,
                    source_ref TEXT,
                    checksum TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    ingest_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    office_id TEXT NOT NULL,
                    matter_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    matter_id INTEGER NOT NULL,
                    document_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workspace_roots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    root_path_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workspace_scan_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    workspace_root_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    files_seen INTEGER NOT NULL DEFAULT 0,
                    files_indexed INTEGER NOT NULL DEFAULT 0,
                    files_skipped INTEGER NOT NULL DEFAULT 0,
                    files_failed INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (workspace_root_id) REFERENCES workspace_roots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workspace_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    workspace_root_id INTEGER NOT NULL,
                    relative_path TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    content_type TEXT,
                    size_bytes INTEGER NOT NULL,
                    mtime INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    parser_status TEXT NOT NULL,
                    indexed_status TEXT NOT NULL,
                    document_language TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (workspace_root_id) REFERENCES workspace_roots(id) ON DELETE CASCADE,
                    UNIQUE (workspace_root_id, relative_path)
                );

                CREATE TABLE IF NOT EXISTS workspace_document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_document_id INTEGER NOT NULL,
                    office_id TEXT NOT NULL,
                    workspace_root_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY (workspace_document_id) REFERENCES workspace_documents(id) ON DELETE CASCADE,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (workspace_root_id) REFERENCES workspace_roots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workspace_matter_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matter_id INTEGER NOT NULL,
                    workspace_document_id INTEGER NOT NULL,
                    linked_by TEXT NOT NULL,
                    linked_at TEXT NOT NULL,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE,
                    FOREIGN KEY (workspace_document_id) REFERENCES workspace_documents(id) ON DELETE CASCADE,
                    UNIQUE (matter_id, workspace_document_id)
                );

                CREATE TABLE IF NOT EXISTS draft_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL DEFAULT 'default-office',
                    matter_id INTEGER,
                    title TEXT NOT NULL,
                    due_at TEXT,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    origin_type TEXT,
                    origin_ref TEXT,
                    recommended_by TEXT,
                    explanation TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS email_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL DEFAULT 'default-office',
                    matter_id INTEGER,
                    to_email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'draft_ready',
                    requested_by TEXT NOT NULL,
                    approved_by TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS email_draft_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (draft_id) REFERENCES email_drafts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS social_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL DEFAULT 'default-office',
                    source TEXT NOT NULL,
                    handle TEXT NOT NULL,
                    content TEXT NOT NULL,
                    risk_score REAL NOT NULL,
                    category TEXT,
                    severity TEXT NOT NULL DEFAULT 'info',
                    notify_user INTEGER NOT NULL DEFAULT 0,
                    evidence_value INTEGER NOT NULL DEFAULT 0,
                    summary TEXT,
                    recommended_action TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS connected_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    account_label TEXT,
                    status TEXT NOT NULL,
                    scopes_json TEXT,
                    connected_at TEXT,
                    last_sync_at TEXT,
                    manual_review_required INTEGER NOT NULL DEFAULT 1,
                    metadata_json TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, provider)
                );

                CREATE TABLE IF NOT EXISTS user_profiles (
                    office_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    favorite_color TEXT,
                    food_preferences TEXT,
                    transport_preference TEXT,
                    weather_preference TEXT,
                    travel_preferences TEXT,
                    home_base TEXT,
                    current_location TEXT,
                    location_preferences TEXT,
                    maps_preference TEXT,
                    prayer_notifications_enabled INTEGER NOT NULL DEFAULT 0,
                    prayer_habit_notes TEXT,
                    communication_style TEXT,
                    assistant_notes TEXT,
                    important_dates_json TEXT NOT NULL DEFAULT '[]',
                    related_profiles_json TEXT NOT NULL DEFAULT '[]',
                    contact_profile_overrides_json TEXT NOT NULL DEFAULT '[]',
                    inbox_watch_rules_json TEXT NOT NULL DEFAULT '[]',
                    inbox_keyword_rules_json TEXT NOT NULL DEFAULT '[]',
                    inbox_block_rules_json TEXT NOT NULL DEFAULT '[]',
                    source_preference_rules_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS assistant_runtime_profiles (
                    office_id TEXT PRIMARY KEY,
                    assistant_name TEXT,
                    role_summary TEXT,
                    tone TEXT,
                    avatar_path TEXT,
                    soul_notes TEXT,
                    tools_notes TEXT,
                    assistant_forms_json TEXT NOT NULL DEFAULT '[]',
                    behavior_contract_json TEXT NOT NULL DEFAULT '{}',
                    evolution_history_json TEXT NOT NULL DEFAULT '[]',
                    heartbeat_extra_checks_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS personal_model_sessions (
                    id TEXT PRIMARY KEY,
                    office_id TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'global',
                    source TEXT NOT NULL DEFAULT 'guided_interview',
                    module_keys_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'active',
                    current_question_id TEXT,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    progress_json TEXT NOT NULL DEFAULT '{}',
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT NOT NULL,
                    paused_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS personal_model_raw_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    session_id TEXT,
                    module_key TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    answer_text TEXT NOT NULL,
                    answer_kind TEXT NOT NULL DEFAULT 'text',
                    answer_value_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'interview',
                    confidence_type TEXT NOT NULL DEFAULT 'explicit',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    explicit INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES personal_model_sessions(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS personal_model_facts (
                    id TEXT PRIMARY KEY,
                    office_id TEXT NOT NULL,
                    session_id TEXT,
                    category TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    value_text TEXT NOT NULL,
                    value_json TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 0.7,
                    confidence_type TEXT NOT NULL DEFAULT 'explicit',
                    source_entry_id INTEGER,
                    visibility TEXT NOT NULL DEFAULT 'assistant_visible',
                    scope TEXT NOT NULL DEFAULT 'global',
                    sensitive INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    never_use INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES personal_model_sessions(id) ON DELETE SET NULL,
                    FOREIGN KEY (source_entry_id) REFERENCES personal_model_raw_entries(id) ON DELETE SET NULL,
                    UNIQUE (office_id, fact_key, scope)
                );

                CREATE TABLE IF NOT EXISTS personal_model_suggestions (
                    id TEXT PRIMARY KEY,
                    office_id TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'chat',
                    category TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    proposed_value_text TEXT NOT NULL,
                    proposed_value_json TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 0.65,
                    scope TEXT NOT NULL DEFAULT 'global',
                    sensitive INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS epistemic_artifacts (
                    id TEXT PRIMARY KEY,
                    office_id TEXT NOT NULL,
                    artifact_kind TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_ref TEXT,
                    summary TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    sensitive INTEGER NOT NULL DEFAULT 0,
                    immutable INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS epistemic_claims (
                    id TEXT PRIMARY KEY,
                    office_id TEXT NOT NULL,
                    artifact_id TEXT,
                    subject_key TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_value_text TEXT NOT NULL,
                    object_value_json TEXT NOT NULL DEFAULT '{}',
                    scope TEXT NOT NULL DEFAULT 'global',
                    epistemic_basis TEXT NOT NULL,
                    validation_state TEXT NOT NULL,
                    consent_class TEXT NOT NULL DEFAULT 'allowed',
                    retrieval_eligibility TEXT NOT NULL DEFAULT 'eligible',
                    sensitive INTEGER NOT NULL DEFAULT 0,
                    self_generated INTEGER NOT NULL DEFAULT 0,
                    valid_from TEXT,
                    valid_to TEXT,
                    supersedes_claim_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (artifact_id) REFERENCES epistemic_artifacts(id) ON DELETE SET NULL,
                    FOREIGN KEY (supersedes_claim_id) REFERENCES epistemic_claims(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_epistemic_artifacts_office_kind
                    ON epistemic_artifacts(office_id, artifact_kind, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_epistemic_claims_lookup
                    ON epistemic_claims(office_id, subject_key, predicate, scope, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_epistemic_claims_retrieval
                    ON epistemic_claims(office_id, retrieval_eligibility, self_generated, updated_at DESC);

                CREATE TABLE IF NOT EXISTS email_threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'gmail',
                    thread_ref TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    participants_json TEXT NOT NULL,
                    snippet TEXT,
                    received_at TEXT,
                    unread_count INTEGER NOT NULL DEFAULT 0,
                    reply_needed INTEGER NOT NULL DEFAULT 0,
                    matter_id INTEGER,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL,
                    UNIQUE (office_id, provider, thread_ref)
                );

                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'google-calendar',
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    ends_at TEXT,
                    attendees_json TEXT,
                    location TEXT,
                    matter_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'confirmed',
                    needs_preparation INTEGER NOT NULL DEFAULT 1,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL,
                    UNIQUE (office_id, provider, external_id)
                );

                CREATE TABLE IF NOT EXISTS google_drive_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'google',
                    external_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    mime_type TEXT,
                    web_view_link TEXT,
                    modified_at TEXT,
                    matter_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL,
                    UNIQUE (office_id, provider, external_id)
                );

                CREATE TABLE IF NOT EXISTS whatsapp_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'whatsapp',
                    conversation_ref TEXT NOT NULL,
                    message_ref TEXT NOT NULL,
                    sender TEXT,
                    recipient TEXT,
                    body TEXT NOT NULL,
                    direction TEXT NOT NULL DEFAULT 'inbound',
                    sent_at TEXT,
                    reply_needed INTEGER NOT NULL DEFAULT 0,
                    matter_id INTEGER,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL,
                    UNIQUE (office_id, provider, message_ref)
                );

                CREATE TABLE IF NOT EXISTS whatsapp_contact_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'whatsapp',
                    conversation_ref TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    profile_name TEXT,
                    phone_number TEXT,
                    is_group INTEGER NOT NULL DEFAULT 0,
                    group_name TEXT,
                    last_seen_at TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, provider, conversation_ref)
                );

                CREATE TABLE IF NOT EXISTS telegram_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'telegram',
                    conversation_ref TEXT NOT NULL,
                    message_ref TEXT NOT NULL,
                    sender TEXT,
                    recipient TEXT,
                    body TEXT NOT NULL,
                    direction TEXT NOT NULL DEFAULT 'inbound',
                    sent_at TEXT,
                    reply_needed INTEGER NOT NULL DEFAULT 0,
                    matter_id INTEGER,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL,
                    UNIQUE (office_id, provider, message_ref)
                );

                CREATE TABLE IF NOT EXISTS x_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'x',
                    external_id TEXT NOT NULL,
                    post_type TEXT NOT NULL DEFAULT 'post',
                    author_handle TEXT,
                    content TEXT NOT NULL,
                    posted_at TEXT,
                    reply_needed INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, provider, external_id)
                );

                CREATE TABLE IF NOT EXISTS x_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'x',
                    conversation_ref TEXT NOT NULL,
                    message_ref TEXT NOT NULL,
                    sender TEXT,
                    recipient TEXT,
                    body TEXT NOT NULL,
                    direction TEXT NOT NULL DEFAULT 'inbound',
                    sent_at TEXT,
                    reply_needed INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, provider, message_ref)
                );

                CREATE TABLE IF NOT EXISTS instagram_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'instagram',
                    conversation_ref TEXT NOT NULL,
                    message_ref TEXT NOT NULL,
                    sender TEXT,
                    recipient TEXT,
                    body TEXT NOT NULL,
                    direction TEXT NOT NULL DEFAULT 'inbound',
                    sent_at TEXT,
                    reply_needed INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, provider, message_ref)
                );

                CREATE TABLE IF NOT EXISTS linkedin_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'linkedin',
                    external_id TEXT NOT NULL,
                    author_handle TEXT,
                    content TEXT NOT NULL,
                    posted_at TEXT,
                    reply_needed INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, provider, external_id)
                );

                CREATE TABLE IF NOT EXISTS linkedin_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'linkedin',
                    external_id TEXT NOT NULL,
                    object_urn TEXT,
                    parent_external_id TEXT,
                    author_handle TEXT,
                    content TEXT NOT NULL,
                    posted_at TEXT,
                    reply_needed INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, provider, external_id)
                );

                CREATE TABLE IF NOT EXISTS linkedin_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'linkedin',
                    conversation_ref TEXT NOT NULL,
                    message_ref TEXT NOT NULL,
                    sender TEXT,
                    recipient TEXT,
                    body TEXT NOT NULL,
                    direction TEXT NOT NULL DEFAULT 'inbound',
                    sent_at TEXT,
                    reply_needed INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, provider, message_ref)
                );

                CREATE TABLE IF NOT EXISTS outbound_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    matter_id INTEGER,
                    draft_type TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    to_contact TEXT,
                    subject TEXT,
                    body TEXT NOT NULL,
                    source_context_json TEXT,
                    generated_from TEXT,
                    ai_model TEXT,
                    ai_provider TEXT,
                    approval_status TEXT NOT NULL DEFAULT 'pending_review',
                    delivery_status TEXT NOT NULL DEFAULT 'not_sent',
                    dispatch_state TEXT NOT NULL DEFAULT 'idle',
                    dispatch_error TEXT,
                    external_message_id TEXT,
                    last_dispatch_at TEXT,
                    created_by TEXT NOT NULL,
                    approved_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS assistant_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    matter_id INTEGER,
                    action_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    rationale TEXT,
                    source_refs_json TEXT,
                    target_channel TEXT,
                    draft_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'suggested',
                    dispatch_state TEXT NOT NULL DEFAULT 'idle',
                    dispatch_error TEXT,
                    external_message_id TEXT,
                    last_dispatch_at TEXT,
                    manual_review_required INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL,
                    FOREIGN KEY (draft_id) REFERENCES outbound_drafts(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS approval_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    action_id INTEGER,
                    outbound_draft_id INTEGER,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (action_id) REFERENCES assistant_actions(id) ON DELETE SET NULL,
                    FOREIGN KEY (outbound_draft_id) REFERENCES outbound_drafts(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS action_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    case_type TEXT NOT NULL DEFAULT 'assistant_action',
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'planned',
                    current_step TEXT NOT NULL DEFAULT 'planned',
                    action_id INTEGER,
                    draft_id INTEGER,
                    approval_required INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL,
                    last_actor TEXT,
                    metadata_json TEXT,
                    last_error TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (action_id) REFERENCES assistant_actions(id) ON DELETE SET NULL,
                    FOREIGN KEY (draft_id) REFERENCES outbound_drafts(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS action_case_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    case_id INTEGER NOT NULL,
                    step_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    note TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (case_id) REFERENCES action_cases(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS dispatch_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    action_id INTEGER,
                    draft_id INTEGER,
                    dispatch_target TEXT,
                    status TEXT NOT NULL DEFAULT 'started',
                    external_message_id TEXT,
                    actor TEXT NOT NULL,
                    note TEXT,
                    error TEXT,
                    metadata_json TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (action_id) REFERENCES assistant_actions(id) ON DELETE SET NULL,
                    FOREIGN KEY (draft_id) REFERENCES outbound_drafts(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS external_receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    dispatch_attempt_id INTEGER,
                    action_id INTEGER,
                    draft_id INTEGER,
                    provider TEXT,
                    receipt_type TEXT NOT NULL DEFAULT 'dispatch_update',
                    receipt_status TEXT,
                    external_receipt_id TEXT,
                    external_message_id TEXT,
                    external_reference TEXT,
                    actor TEXT NOT NULL,
                    note TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (dispatch_attempt_id) REFERENCES dispatch_attempts(id) ON DELETE SET NULL,
                    FOREIGN KEY (action_id) REFERENCES assistant_actions(id) ON DELETE SET NULL,
                    FOREIGN KEY (draft_id) REFERENCES outbound_drafts(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS assistant_threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS assistant_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    office_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    linked_entities_json TEXT,
                    tool_suggestions_json TEXT,
                    draft_preview_json TEXT,
                    source_context_json TEXT,
                    requires_approval INTEGER NOT NULL DEFAULT 0,
                    generated_from TEXT,
                    ai_provider TEXT,
                    ai_model TEXT,
                    feedback_value TEXT,
                    feedback_note TEXT,
                    feedback_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES assistant_threads(id) ON DELETE CASCADE,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS assistant_context_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    thread_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    source_context_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES assistant_threads(id) ON DELETE CASCADE,
                    FOREIGN KEY (message_id) REFERENCES assistant_messages(id) ON DELETE CASCADE,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    matter_id INTEGER,
                    thread_id INTEGER,
                    parent_run_id INTEGER,
                    source_kind TEXT NOT NULL DEFAULT 'assistant',
                    run_type TEXT NOT NULL DEFAULT 'investigation',
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    approval_required INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    cancelled_at TEXT,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL,
                    FOREIGN KEY (thread_id) REFERENCES assistant_threads(id) ON DELETE SET NULL,
                    FOREIGN KEY (parent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS agent_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    office_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    rationale TEXT,
                    input_json TEXT NOT NULL DEFAULT '{}',
                    output_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tool_invocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    office_id TEXT NOT NULL,
                    step_id INTEGER,
                    tool_name TEXT NOT NULL,
                    tool_class TEXT NOT NULL,
                    risk_level TEXT NOT NULL DEFAULT 'low',
                    approval_policy TEXT NOT NULL DEFAULT 'none',
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL DEFAULT '{}',
                    output_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    approval_required INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY (step_id) REFERENCES agent_steps(id) ON DELETE SET NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS run_approval_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    run_id INTEGER NOT NULL,
                    step_id INTEGER,
                    tool_invocation_id INTEGER,
                    approval_kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT NOT NULL,
                    decided_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    decided_at TEXT,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY (step_id) REFERENCES agent_steps(id) ON DELETE SET NULL,
                    FOREIGN KEY (tool_invocation_id) REFERENCES tool_invocations(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS browser_session_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    run_id INTEGER NOT NULL,
                    step_id INTEGER,
                    artifact_type TEXT NOT NULL,
                    path TEXT,
                    url TEXT,
                    sha256 TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY (step_id) REFERENCES agent_steps(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS memory_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    run_id INTEGER,
                    memory_scope TEXT NOT NULL,
                    entity_key TEXT,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS external_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    external_ref TEXT,
                    title TEXT,
                    actor_label TEXT,
                    summary TEXT,
                    importance TEXT NOT NULL DEFAULT 'normal',
                    reply_needed INTEGER NOT NULL DEFAULT 0,
                    legal_risk INTEGER NOT NULL DEFAULT 0,
                    evidence_value INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    source_created_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS automation_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    rule_type TEXT NOT NULL,
                    scope_json TEXT NOT NULL DEFAULT '{}',
                    config_json TEXT NOT NULL DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    managed_by_assistant INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_applied_at TEXT,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS query_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner TEXT NOT NULL,
                    status TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    model_profile TEXT,
                    continue_in_background INTEGER NOT NULL DEFAULT 1,
                    detached INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    error TEXT,
                    toast_pending INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS runtime_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    worker_kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    write_intent TEXT NOT NULL DEFAULT 'read_only',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT,
                    error TEXT,
                    requested_by TEXT NOT NULL,
                    lease_owner TEXT,
                    leased_at TEXT,
                    completed_at TEXT,
                    priority INTEGER NOT NULL DEFAULT 100,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_matters_office ON matters (office_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_drafts_matter ON drafts (matter_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_timeline_matter ON matter_timeline_events (matter_id, event_at DESC);
                CREATE INDEX IF NOT EXISTS idx_documents_matter ON documents (matter_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks (document_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_document_chunks_scope ON document_chunks (office_id, matter_id, document_id);
                CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_matter ON ingestion_jobs (matter_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_workspace_roots_office ON workspace_roots (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_workspace_scan_jobs_root ON workspace_scan_jobs (workspace_root_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_workspace_documents_root ON workspace_documents (workspace_root_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_workspace_document_chunks_doc ON workspace_document_chunks (workspace_document_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_workspace_document_chunks_scope ON workspace_document_chunks (workspace_root_id, workspace_document_id);
                CREATE INDEX IF NOT EXISTS idx_workspace_matter_links_matter ON workspace_matter_links (matter_id, workspace_document_id);
                CREATE INDEX IF NOT EXISTS idx_connected_accounts_provider ON connected_accounts (office_id, provider);
                CREATE INDEX IF NOT EXISTS idx_user_profiles_office ON user_profiles (office_id);
                CREATE INDEX IF NOT EXISTS idx_assistant_runtime_profiles_office ON assistant_runtime_profiles (office_id);
                CREATE INDEX IF NOT EXISTS idx_personal_model_sessions_office ON personal_model_sessions (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_personal_model_raw_entries_office ON personal_model_raw_entries (office_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_personal_model_facts_office ON personal_model_facts (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_personal_model_facts_category ON personal_model_facts (office_id, category, scope, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_personal_model_suggestions_office ON personal_model_suggestions (office_id, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_email_threads_office ON email_threads (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_calendar_events_office ON calendar_events (office_id, starts_at ASC);
                CREATE INDEX IF NOT EXISTS idx_google_drive_files_office ON google_drive_files (office_id, modified_at DESC);
                CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_office ON whatsapp_messages (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_telegram_messages_office ON telegram_messages (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_x_posts_office ON x_posts (office_id, posted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_x_messages_office ON x_messages (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_instagram_messages_office ON instagram_messages (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_linkedin_posts_office ON linkedin_posts (office_id, posted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_linkedin_comments_office ON linkedin_comments (office_id, posted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_linkedin_messages_office ON linkedin_messages (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_outbound_drafts_office ON outbound_drafts (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_outbound_drafts_matter ON outbound_drafts (matter_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_assistant_actions_office ON assistant_actions (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_approval_events_office ON approval_events (office_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_action_cases_office ON action_cases (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_action_cases_action ON action_cases (office_id, action_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_action_cases_draft ON action_cases (office_id, draft_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_action_case_events_case ON action_case_events (case_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_dispatch_attempts_action ON dispatch_attempts (office_id, action_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_dispatch_attempts_draft ON dispatch_attempts (office_id, draft_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_external_receipts_attempt ON external_receipts (dispatch_attempt_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_external_receipts_action ON external_receipts (office_id, action_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_external_receipts_draft ON external_receipts (office_id, draft_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_assistant_messages_thread ON assistant_messages (thread_id, id ASC);
                CREATE INDEX IF NOT EXISTS idx_assistant_context_snapshots_message
                    ON assistant_context_snapshots (office_id, message_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_runs_office ON agent_runs (office_id, updated_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_runs_thread ON agent_runs (thread_id, updated_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_steps_run ON agent_steps (run_id, step_index ASC);
                CREATE INDEX IF NOT EXISTS idx_tool_invocations_run ON tool_invocations (run_id, id ASC);
                CREATE INDEX IF NOT EXISTS idx_run_approval_requests_run ON run_approval_requests (run_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_browser_session_artifacts_run ON browser_session_artifacts (run_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memory_events_office ON memory_events (office_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_external_events_office ON external_events (office_id, updated_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_automation_rules_office ON automation_rules (office_id, updated_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_runtime_jobs_queue ON runtime_jobs (office_id, status, worker_kind, priority ASC, id ASC);
                """
            )
            self._ensure_column(conn, "tasks", "office_id", "TEXT NOT NULL DEFAULT 'default-office'")
            self._ensure_column(conn, "tasks", "matter_id", "INTEGER")
            self._ensure_column(conn, "tasks", "origin_type", "TEXT")
            self._ensure_column(conn, "tasks", "origin_ref", "TEXT")
            self._ensure_column(conn, "tasks", "recommended_by", "TEXT")
            self._ensure_column(conn, "tasks", "explanation", "TEXT")
            self._ensure_column(conn, "tasks", "updated_at", "TEXT")
            self._ensure_column(conn, "matter_notes", "event_at", "TEXT")
            self._ensure_column(conn, "drafts", "source_context_json", "TEXT")
            self._ensure_column(conn, "drafts", "generated_from", "TEXT")
            self._ensure_column(conn, "drafts", "manual_review_required", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "email_drafts", "office_id", "TEXT NOT NULL DEFAULT 'default-office'")
            self._ensure_column(conn, "email_drafts", "matter_id", "INTEGER")
            self._ensure_column(conn, "email_drafts", "review_status", "TEXT NOT NULL DEFAULT 'draft_ready'")
            self._ensure_column(conn, "social_events", "office_id", "TEXT NOT NULL DEFAULT 'default-office'")
            self._ensure_column(conn, "social_events", "category", "TEXT")
            self._ensure_column(conn, "social_events", "severity", "TEXT NOT NULL DEFAULT 'info'")
            self._ensure_column(conn, "social_events", "notify_user", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "social_events", "evidence_value", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "social_events", "summary", "TEXT")
            self._ensure_column(conn, "social_events", "recommended_action", "TEXT")
            self._ensure_column(conn, "social_events", "metadata_json", "TEXT")
            self._ensure_column(conn, "user_profiles", "favorite_color", "TEXT")
            self._ensure_column(conn, "user_profiles", "home_base", "TEXT")
            self._ensure_column(conn, "user_profiles", "current_location", "TEXT")
            self._ensure_column(conn, "user_profiles", "location_preferences", "TEXT")
            self._ensure_column(conn, "user_profiles", "maps_preference", "TEXT")
            self._ensure_column(conn, "user_profiles", "prayer_notifications_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "user_profiles", "prayer_habit_notes", "TEXT")
            self._ensure_column(conn, "user_profiles", "related_profiles_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "user_profiles", "contact_profile_overrides_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "user_profiles", "inbox_watch_rules_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "user_profiles", "inbox_keyword_rules_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "user_profiles", "inbox_block_rules_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "user_profiles", "source_preference_rules_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "outbound_drafts", "dispatch_state", "TEXT NOT NULL DEFAULT 'idle'")
            self._ensure_column(conn, "outbound_drafts", "dispatch_error", "TEXT")
            self._ensure_column(conn, "outbound_drafts", "external_message_id", "TEXT")
            self._ensure_column(conn, "outbound_drafts", "last_dispatch_at", "TEXT")
            self._ensure_column(conn, "assistant_actions", "dispatch_state", "TEXT NOT NULL DEFAULT 'idle'")
            self._ensure_column(conn, "assistant_actions", "dispatch_error", "TEXT")
            self._ensure_column(conn, "assistant_actions", "external_message_id", "TEXT")
            self._ensure_column(conn, "assistant_actions", "last_dispatch_at", "TEXT")
            self._ensure_column(conn, "assistant_threads", "archived", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "assistant_messages", "starred", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "assistant_messages", "starred_at", "TEXT")
            self._ensure_column(conn, "assistant_messages", "feedback_value", "TEXT")
            self._ensure_column(conn, "assistant_messages", "feedback_note", "TEXT")
            self._ensure_column(conn, "assistant_messages", "feedback_at", "TEXT")
            self._ensure_column(conn, "query_jobs", "runtime_job_id", "INTEGER")
            self._ensure_column(conn, "assistant_runtime_profiles", "assistant_forms_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "assistant_runtime_profiles", "behavior_contract_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "assistant_runtime_profiles", "evolution_history_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_default_office(conn, "default-office", "Varsayilan Ofis", "local-only")
            self._ensure_assistant_threads_multi_session(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_matter ON tasks (matter_id, id DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_social_events_office ON social_events (office_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_assistant_threads_office_updated ON assistant_threads (office_id, archived, updated_at DESC, id DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_assistant_messages_thread_created ON assistant_messages (office_id, thread_id, id DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_assistant_messages_starred ON assistant_messages (office_id, thread_id, starred, starred_at DESC, id DESC)")
            conn.execute("UPDATE matter_notes SET event_at=COALESCE(event_at, created_at)")
            conn.execute("UPDATE tasks SET updated_at=COALESCE(updated_at, created_at)")

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
        if column_name in self._table_columns(conn, table_name):
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    def _ensure_assistant_threads_multi_session(self, conn: sqlite3.Connection) -> None:
        indexes = conn.execute("PRAGMA index_list(assistant_threads)").fetchall()
        has_office_unique = False
        for index_row in indexes:
            if not int(index_row["unique"] or 0):
                continue
            index_name = str(index_row["name"] or "")
            columns = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
            column_names = [str(col["name"] or "") for col in columns]
            if column_names == ["office_id"]:
                has_office_unique = True
                break
        if not has_office_unique:
            return

        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assistant_threads_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                INSERT INTO assistant_threads_v2 (id, office_id, title, created_by, created_at, updated_at, archived)
                SELECT id, office_id, title, created_by, created_at, updated_at, COALESCE(archived, 0)
                FROM assistant_threads
                """
            )
            conn.execute("DROP TABLE assistant_threads")
            conn.execute("ALTER TABLE assistant_threads_v2 RENAME TO assistant_threads")
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

    def _ensure_default_office(self, conn: sqlite3.Connection, office_id: str, name: str, deployment_mode: str) -> None:
        row = conn.execute("SELECT id FROM offices WHERE id=?", (office_id,)).fetchone()
        if row:
            return
        conn.execute(
            "INSERT INTO offices (id, name, deployment_mode, created_at) VALUES (?, ?, ?, ?)",
            (office_id, name, deployment_mode, self._now()),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def _get_matter_row(self, conn: sqlite3.Connection, matter_id: int, office_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM matters WHERE id=? AND office_id=?",
            (matter_id, office_id),
        ).fetchone()

    def _add_matter_timeline_event(
        self,
        conn: sqlite3.Connection,
        matter_id: int,
        event_type: str,
        title: str,
        details: str | None,
        event_at: str | None,
        created_by: str | None,
    ) -> dict[str, Any]:
        ts = event_at or self._now()
        cur = conn.execute(
            """
            INSERT INTO matter_timeline_events (matter_id, event_type, title, details, event_at, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (matter_id, event_type, title, details, ts, created_by, self._now()),
        )
        row = conn.execute("SELECT * FROM matter_timeline_events WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def store_session(self, session_id: str, subject: str, role: str, expires_at: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (session_id, subject, role, created_at, expires_at, revoked) VALUES (?, ?, ?, ?, ?, 0)",
                (session_id, subject, role, self._now(), expires_at),
            )

    def is_session_active(self, session_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT expires_at FROM sessions WHERE session_id=? AND revoked=0",
                (session_id,),
            ).fetchone()
            if row is None:
                return False
            try:
                expires_at = datetime.fromisoformat(str(row["expires_at"]))
            except ValueError:
                return False
            return expires_at > datetime.now(timezone.utc)

    def revoke_session(self, session_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("UPDATE sessions SET revoked=1 WHERE session_id=?", (session_id,))
            return cur.rowcount > 0

    def create_matter(
        self,
        office_id: str,
        title: str,
        reference_code: str | None,
        practice_area: str | None,
        status: str,
        summary: str | None,
        client_name: str | None,
        lead_lawyer: str | None,
        opened_at: str | None,
        created_by: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            cur = conn.execute(
                """
                INSERT INTO matters (
                    office_id, title, reference_code, practice_area, status, summary,
                    client_name, lead_lawyer, opened_at, created_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    title,
                    reference_code,
                    practice_area,
                    status,
                    summary,
                    client_name,
                    lead_lawyer,
                    opened_at,
                    created_by,
                    now,
                    now,
                ),
            )
            matter_id = int(cur.lastrowid)
            self._add_matter_timeline_event(
                conn,
                matter_id,
                "matter_created",
                "Dosya oluşturuldu",
                f"{title} oluşturuldu",
                opened_at or now,
                created_by,
            )
            row = self._get_matter_row(conn, matter_id, office_id)
            return dict(row) if row else {}

    def list_matters(self, office_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM matters WHERE office_id=? ORDER BY updated_at DESC, id DESC",
                (office_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_matter(self, matter_id: int, office_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            return self._row_to_dict(self._get_matter_row(conn, matter_id, office_id))

    def update_matter(self, office_id: str, matter_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "title",
            "reference_code",
            "practice_area",
            "status",
            "summary",
            "client_name",
            "lead_lawyer",
            "opened_at",
        }
        updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if not updates:
            return self.get_matter(matter_id, office_id)
        updates["updated_at"] = self._now()
        assignments = ", ".join(f"{key}=?" for key in updates)
        params = [updates[key] for key in updates] + [matter_id, office_id]
        with self._conn() as conn:
            row = self._get_matter_row(conn, matter_id, office_id)
            if not row:
                return None
            conn.execute(f"UPDATE matters SET {assignments} WHERE id=? AND office_id=?", params)
            updated = self._get_matter_row(conn, matter_id, office_id)
            return dict(updated) if updated else None

    def add_matter_note(
        self,
        office_id: str,
        matter_id: int,
        note_type: str,
        body: str,
        created_by: str,
        event_at: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            cur = conn.execute(
                """
                INSERT INTO matter_notes (matter_id, note_type, body, event_at, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (matter_id, note_type, body, event_at or self._now(), created_by, self._now()),
            )
            note = conn.execute("SELECT * FROM matter_notes WHERE id=?", (cur.lastrowid,)).fetchone()
            conn.execute(
                "UPDATE matters SET updated_at=? WHERE id=? AND office_id=?",
                (self._now(), matter_id, office_id),
            )
            self._add_matter_timeline_event(
                conn,
                matter_id,
                "note_added",
                "Dosya notu eklendi",
                body[:240],
                event_at,
                created_by,
            )
            return dict(note) if note else None

    def list_matter_notes(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                "SELECT * FROM matter_notes WHERE matter_id=? ORDER BY event_at DESC, id DESC",
                (matter_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_matter_timeline(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT * FROM matter_timeline_events
                WHERE matter_id=?
                ORDER BY event_at DESC, id DESC
                """,
                (matter_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_matter_summary(self, office_id: str, matter_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            counts = {
                "notes": conn.execute("SELECT COUNT(*) AS c FROM matter_notes WHERE matter_id=?", (matter_id,)).fetchone()["c"],
                "tasks": conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE matter_id=?", (matter_id,)).fetchone()["c"],
                "drafts": conn.execute("SELECT COUNT(*) AS c FROM drafts WHERE matter_id=?", (matter_id,)).fetchone()["c"],
            }
            latest_timeline = conn.execute(
                "SELECT * FROM matter_timeline_events WHERE matter_id=? ORDER BY event_at DESC, id DESC LIMIT 3",
                (matter_id,),
            ).fetchall()
            summary_text = matter["summary"] or (
                f"{matter['title']} dosyası için çalışma özeti. "
                f"Not sayısı: {counts['notes']}, görev sayısı: {counts['tasks']}, taslak sayısı: {counts['drafts']}."
            )
            return {
                "matter": dict(matter),
                "summary": summary_text,
                "counts": counts,
                "latest_timeline": [dict(row) for row in latest_timeline],
                "generated_from": "matter_record" if matter["summary"] else "matter_record_and_counts",
                "manual_review_required": matter["summary"] is None,
            }

    def create_matter_draft(
        self,
        office_id: str,
        matter_id: int,
        draft_type: str,
        title: str,
        body: str,
        target_channel: str,
        to_contact: str | None,
        created_by: str,
        *,
        source_context: dict[str, Any] | None = None,
        generated_from: str | None = None,
        manual_review_required: bool = True,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            cur = conn.execute(
                """
                INSERT INTO drafts (
                    matter_id, office_id, draft_type, title, body, status,
                    target_channel, to_contact, source_context_json, generated_from,
                    manual_review_required, created_by, approved_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    matter_id,
                    office_id,
                    draft_type,
                    title,
                    body,
                    target_channel,
                    to_contact,
                    json.dumps(source_context, ensure_ascii=False) if source_context else None,
                    generated_from,
                    1 if manual_review_required else 0,
                    created_by,
                    now,
                    now,
                ),
            )
            draft_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO draft_events (draft_id, event_type, actor, note, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    draft_id,
                    "draft_generated" if generated_from else "draft_created",
                    created_by,
                    f"{draft_type} taslağı oluşturuldu",
                    now,
                ),
            )
            conn.execute(
                "UPDATE matters SET updated_at=? WHERE id=? AND office_id=?",
                (now, matter_id, office_id),
            )
            self._add_matter_timeline_event(
                conn,
                matter_id,
                "draft_created",
                "Dosya taslağı oluşturuldu",
                title,
                now,
                created_by,
            )
            row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
            return self._decode_draft(dict(row)) if row else None

    def list_matter_drafts(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                "SELECT * FROM drafts WHERE matter_id=? AND office_id=? ORDER BY updated_at DESC, id DESC",
                (matter_id, office_id),
            ).fetchall()
            return [self._decode_draft(dict(row)) for row in rows]

    def list_matter_draft_events(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT e.*, d.title AS draft_title, d.draft_type
                FROM draft_events e
                JOIN drafts d ON d.id = e.draft_id
                WHERE d.matter_id=? AND d.office_id=?
                ORDER BY e.created_at DESC, e.id DESC
                """,
                (matter_id, office_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_active_workspace_root(self, office_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM workspace_roots
                WHERE office_id=? AND status='active'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (office_id,),
            ).fetchone()
            return dict(row) if row else None

    def save_workspace_root(self, office_id: str, display_name: str, root_path: str, root_path_hash: str) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            existing = conn.execute(
                "SELECT id FROM workspace_roots WHERE office_id=? AND root_path_hash=?",
                (office_id, root_path_hash),
            ).fetchone()
            conn.execute("UPDATE workspace_roots SET status='inactive', updated_at=? WHERE office_id=?", (now, office_id))
            if existing:
                conn.execute(
                    """
                    UPDATE workspace_roots
                    SET display_name=?, root_path=?, status='active', updated_at=?
                    WHERE id=?
                    """,
                    (display_name, root_path, now, existing["id"]),
                )
                row = conn.execute("SELECT * FROM workspace_roots WHERE id=?", (existing["id"],)).fetchone()
                return dict(row)
            cur = conn.execute(
                """
                INSERT INTO workspace_roots (office_id, display_name, root_path, root_path_hash, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (office_id, display_name, root_path, root_path_hash, now, now),
            )
            row = conn.execute("SELECT * FROM workspace_roots WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row)

    def create_workspace_scan_job(self, office_id: str, workspace_root_id: int) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            root = conn.execute(
                "SELECT * FROM workspace_roots WHERE id=? AND office_id=?",
                (workspace_root_id, office_id),
            ).fetchone()
            if not root:
                return None
            cur = conn.execute(
                """
                INSERT INTO workspace_scan_jobs (
                    office_id, workspace_root_id, status, files_seen, files_indexed, files_skipped, files_failed, error, created_at, updated_at
                )
                VALUES (?, ?, 'queued', 0, 0, 0, 0, NULL, ?, ?)
                """,
                (office_id, workspace_root_id, now, now),
            )
            row = conn.execute("SELECT * FROM workspace_scan_jobs WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row) if row else None

    def update_workspace_scan_job(
        self,
        office_id: str,
        job_id: int,
        *,
        status: str,
        files_seen: int | None = None,
        files_indexed: int | None = None,
        files_skipped: int | None = None,
        files_failed: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            current = conn.execute(
                "SELECT * FROM workspace_scan_jobs WHERE id=? AND office_id=?",
                (job_id, office_id),
            ).fetchone()
            if not current:
                return None
            conn.execute(
                """
                UPDATE workspace_scan_jobs
                SET status=?, files_seen=?, files_indexed=?, files_skipped=?, files_failed=?, error=?, updated_at=?
                WHERE id=? AND office_id=?
                """,
                (
                    status,
                    files_seen if files_seen is not None else current["files_seen"],
                    files_indexed if files_indexed is not None else current["files_indexed"],
                    files_skipped if files_skipped is not None else current["files_skipped"],
                    files_failed if files_failed is not None else current["files_failed"],
                    error,
                    self._now(),
                    job_id,
                    office_id,
                ),
            )
            row = conn.execute("SELECT * FROM workspace_scan_jobs WHERE id=? AND office_id=?", (job_id, office_id)).fetchone()
            return dict(row) if row else None

    def list_workspace_scan_jobs(self, office_id: str, workspace_root_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM workspace_scan_jobs
                WHERE office_id=? AND workspace_root_id=?
                ORDER BY updated_at DESC, id DESC
                """,
                (office_id, workspace_root_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_workspace_document(
        self,
        office_id: str,
        workspace_root_id: int,
        *,
        relative_path: str,
        display_name: str,
        extension: str,
        content_type: str | None,
        size_bytes: int,
        mtime: int,
        checksum: str,
        parser_status: str,
        indexed_status: str,
        document_language: str,
        last_error: str | None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO workspace_documents (
                    office_id, workspace_root_id, relative_path, display_name, extension, content_type, size_bytes, mtime,
                    checksum, parser_status, indexed_status, document_language, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_root_id, relative_path) DO UPDATE SET
                    display_name=excluded.display_name,
                    extension=excluded.extension,
                    content_type=excluded.content_type,
                    size_bytes=excluded.size_bytes,
                    mtime=excluded.mtime,
                    checksum=excluded.checksum,
                    parser_status=excluded.parser_status,
                    indexed_status=excluded.indexed_status,
                    document_language=excluded.document_language,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    workspace_root_id,
                    relative_path,
                    display_name,
                    extension,
                    content_type,
                    size_bytes,
                    mtime,
                    checksum,
                    parser_status,
                    indexed_status,
                    document_language,
                    last_error,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM workspace_documents WHERE workspace_root_id=? AND relative_path=?",
                (workspace_root_id, relative_path),
            ).fetchone()
            return dict(row) if row else {}

    def mark_missing_workspace_documents(self, office_id: str, workspace_root_id: int, seen_relative_paths: list[str]) -> int:
        with self._conn() as conn:
            query = """
                UPDATE workspace_documents
                SET indexed_status='missing', updated_at=?
                WHERE office_id=? AND workspace_root_id=?
            """
            params: list[Any] = [self._now(), office_id, workspace_root_id]
            if seen_relative_paths:
                placeholders = ",".join(["?"] * len(seen_relative_paths))
                query += f" AND relative_path NOT IN ({placeholders})"
                params.extend(seen_relative_paths)
            cur = conn.execute(query, params)
            return cur.rowcount

    def replace_workspace_document_chunks(
        self,
        office_id: str,
        workspace_root_id: int,
        workspace_document_id: int,
        chunks: list[dict[str, Any]],
    ) -> int:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM workspace_document_chunks WHERE office_id=? AND workspace_root_id=? AND workspace_document_id=?",
                (office_id, workspace_root_id, workspace_document_id),
            )
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO workspace_document_chunks (
                        workspace_document_id, office_id, workspace_root_id, chunk_index, text, token_count, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workspace_document_id,
                        office_id,
                        workspace_root_id,
                        chunk["chunk_index"],
                        chunk["text"],
                        chunk["token_count"],
                        chunk["metadata_json"],
                    ),
                )
            return len(chunks)

    def get_workspace_document(self, office_id: str, workspace_document_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT d.*, r.display_name AS workspace_root_name, r.root_path
                FROM workspace_documents d
                JOIN workspace_roots r ON r.id = d.workspace_root_id
                WHERE d.office_id=? AND d.id=?
                """,
                (office_id, workspace_document_id),
            ).fetchone()
            return dict(row) if row else None

    def list_workspace_documents(
        self,
        office_id: str,
        workspace_root_id: int,
        *,
        query_text: str | None = None,
        extension: str | None = None,
        status: str | None = None,
        path_prefix: str | None = None,
        limit: int | None = None,
        include_chunk_count: bool = True,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT d.*"
            if include_chunk_count:
                query += ", COUNT(c.id) AS chunk_count"
            query += "\nFROM workspace_documents d\n"
            if include_chunk_count:
                query += "LEFT JOIN workspace_document_chunks c ON c.workspace_document_id = d.id\n"
            query += "WHERE d.office_id=? AND d.workspace_root_id=?"
            params: list[Any] = [office_id, workspace_root_id]
            if query_text:
                pattern = f"%{query_text}%"
                query += " AND (d.display_name LIKE ? OR d.relative_path LIKE ?)"
                params.extend([pattern, pattern])
            if extension:
                query += " AND d.extension=?"
                params.append(extension)
            if status:
                query += " AND d.indexed_status=?"
                params.append(status)
            if path_prefix:
                query += " AND d.relative_path LIKE ?"
                params.append(f"{path_prefix.rstrip('/')}%")
            if include_chunk_count:
                query += " GROUP BY d.id"
            query += " ORDER BY d.updated_at DESC, d.id DESC"
            if limit is not None and limit > 0:
                query += " LIMIT ?"
                params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def count_workspace_documents(
        self,
        office_id: str,
        workspace_root_id: int,
        *,
        query_text: str | None = None,
        extension: str | None = None,
        status: str | None = None,
        path_prefix: str | None = None,
    ) -> int:
        with self._conn() as conn:
            query = "SELECT COUNT(*) AS cnt FROM workspace_documents d WHERE d.office_id=? AND d.workspace_root_id=?"
            params: list[Any] = [office_id, workspace_root_id]
            if query_text:
                pattern = f"%{query_text}%"
                query += " AND (d.display_name LIKE ? OR d.relative_path LIKE ?)"
                params.extend([pattern, pattern])
            if extension:
                query += " AND d.extension=?"
                params.append(extension)
            if status:
                query += " AND d.indexed_status=?"
                params.append(status)
            if path_prefix:
                query += " AND d.relative_path LIKE ?"
                params.append(f"{path_prefix.rstrip('/')}%")
            row = conn.execute(query, params).fetchone()
            return int(row["cnt"]) if row else 0

    def list_workspace_document_chunks(self, office_id: str, workspace_document_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            document = self.get_workspace_document(office_id, workspace_document_id)
            if not document:
                return None
            rows = conn.execute(
                """
                SELECT c.*, d.display_name, d.relative_path, d.extension
                FROM workspace_document_chunks c
                JOIN workspace_documents d ON d.id = c.workspace_document_id
                WHERE c.office_id=? AND c.workspace_document_id=?
                ORDER BY c.chunk_index ASC
                """,
                (office_id, workspace_document_id),
            ).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                try:
                    item["metadata"] = json.loads(str(item.get("metadata_json") or "{}"))
                except json.JSONDecodeError:
                    item["metadata"] = {}
                items.append(item)
            return items

    def search_workspace_document_chunks(
        self,
        office_id: str,
        workspace_root_id: int,
        *,
        path_prefix: str | None = None,
        extensions: list[str] | None = None,
        workspace_document_id: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = """
                SELECT
                    c.id,
                    c.workspace_document_id AS document_id,
                    c.workspace_root_id,
                    c.office_id,
                    c.chunk_index,
                    c.text,
                    c.token_count,
                    c.metadata_json,
                    d.display_name,
                    d.relative_path,
                    d.extension,
                    d.content_type,
                    d.checksum,
                    'workspace' AS source_type,
                    NULL AS matter_id
                FROM workspace_document_chunks c
                JOIN workspace_documents d ON d.id = c.workspace_document_id
                WHERE c.office_id=? AND c.workspace_root_id=? AND d.indexed_status='indexed'
            """
            params: list[Any] = [office_id, workspace_root_id]
            if workspace_document_id is not None:
                query += " AND c.workspace_document_id=?"
                params.append(workspace_document_id)
            if path_prefix:
                query += " AND d.relative_path LIKE ?"
                params.append(f"{path_prefix.rstrip('/')}%")
            if extensions:
                placeholders = ",".join(["?"] * len(extensions))
                query += f" AND d.extension IN ({placeholders})"
                params.extend(extensions)
            query += " ORDER BY c.workspace_document_id ASC, c.chunk_index ASC"
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def attach_workspace_document_to_matter(self, office_id: str, matter_id: int, workspace_document_id: int, linked_by: str) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            document = conn.execute(
                "SELECT * FROM workspace_documents WHERE office_id=? AND id=?",
                (office_id, workspace_document_id),
            ).fetchone()
            if not document:
                return None
            conn.execute(
                """
                INSERT OR IGNORE INTO workspace_matter_links (matter_id, workspace_document_id, linked_by, linked_at)
                VALUES (?, ?, ?, ?)
                """,
                (matter_id, workspace_document_id, linked_by, now),
            )
            self._add_matter_timeline_event(
                conn,
                matter_id,
                "workspace_document_attached",
                "Çalışma alanı belgesi bağlandı",
                str(document["display_name"]),
                now,
                linked_by,
            )
            row = conn.execute(
                """
                SELECT l.*, d.display_name, d.relative_path, d.extension, d.indexed_status
                FROM workspace_matter_links l
                JOIN workspace_documents d ON d.id = l.workspace_document_id
                WHERE l.matter_id=? AND l.workspace_document_id=?
                """,
                (matter_id, workspace_document_id),
            ).fetchone()
            return dict(row) if row else None

    def get_matter_by_workspace_document(self, office_id: str, workspace_document_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT m.*
                FROM matters m
                JOIN workspace_matter_links l ON l.matter_id = m.id
                WHERE m.office_id=? AND l.workspace_document_id=?
                ORDER BY m.updated_at DESC, m.id DESC
                LIMIT 1
                """,
                (office_id, workspace_document_id),
            ).fetchone()
            return dict(row) if row else None

    def list_matter_workspace_documents(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT l.*, d.display_name, d.relative_path, d.extension, d.indexed_status, d.workspace_root_id
                FROM workspace_matter_links l
                JOIN workspace_documents d ON d.id = l.workspace_document_id
                WHERE l.matter_id=?
                ORDER BY l.linked_at DESC, l.id DESC
                """,
                (matter_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def search_linked_workspace_chunks(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT
                    c.id,
                    c.workspace_document_id AS document_id,
                    c.workspace_root_id,
                    c.office_id,
                    c.chunk_index,
                    c.text,
                    c.token_count,
                    c.metadata_json,
                    d.display_name,
                    d.relative_path,
                    d.extension,
                    d.content_type,
                    d.checksum,
                    'workspace' AS source_type,
                    ? AS matter_id
                FROM workspace_document_chunks c
                JOIN workspace_documents d ON d.id = c.workspace_document_id
                JOIN workspace_matter_links l ON l.workspace_document_id = d.id
                WHERE d.office_id=? AND l.matter_id=? AND d.indexed_status='indexed'
                ORDER BY c.workspace_document_id ASC, c.chunk_index ASC
                """,
                (matter_id, office_id, matter_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_document(
        self,
        office_id: str,
        matter_id: int,
        filename: str,
        display_name: str,
        content_type: str | None,
        source_type: str,
        source_ref: str | None,
        checksum: str,
        size_bytes: int,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            cur = conn.execute(
                """
                INSERT INTO documents (
                    office_id, matter_id, filename, display_name, content_type, source_type, source_ref,
                    checksum, size_bytes, ingest_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (
                    office_id,
                    matter_id,
                    filename,
                    display_name,
                    content_type,
                    source_type,
                    source_ref,
                    checksum,
                    size_bytes,
                    now,
                    now,
                ),
            )
            document_id = int(cur.lastrowid)
            self._add_matter_timeline_event(
                conn,
                matter_id,
                "document_registered",
                "Dosya belgesi kaydedildi",
                display_name,
                now,
                None,
            )
            row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            return dict(row) if row else None

    def get_document(self, office_id: str, matter_id: int, document_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id=? AND office_id=? AND matter_id=?",
                (document_id, office_id, matter_id),
            ).fetchone()
            return dict(row) if row else None

    def get_document_global(self, office_id: str, document_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id=? AND office_id=?",
                (document_id, office_id),
            ).fetchone()
            return dict(row) if row else None

    def list_matter_documents(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT d.*, COUNT(c.id) AS chunk_count
                FROM documents d
                LEFT JOIN document_chunks c ON c.document_id = d.id
                WHERE d.office_id=? AND d.matter_id=?
                GROUP BY d.id
                ORDER BY d.updated_at DESC, d.id DESC
                """,
                (office_id, matter_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_document_status(self, office_id: str, document_id: int, status: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE documents SET ingest_status=?, updated_at=? WHERE id=? AND office_id=?",
                (status, self._now(), document_id, office_id),
            )
            row = conn.execute("SELECT * FROM documents WHERE id=? AND office_id=?", (document_id, office_id)).fetchone()
            return dict(row) if row else None

    def record_matter_event(
        self,
        office_id: str,
        matter_id: int,
        event_type: str,
        title: str,
        details: str | None,
        event_at: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            return self._add_matter_timeline_event(conn, matter_id, event_type, title, details, event_at, created_by)

    def create_ingestion_job(self, office_id: str, matter_id: int, document_id: int) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO ingestion_jobs (office_id, matter_id, document_id, status, error, created_at, updated_at)
                VALUES (?, ?, ?, 'queued', NULL, ?, ?)
                """,
                (office_id, matter_id, document_id, now, now),
            )
            row = conn.execute("SELECT * FROM ingestion_jobs WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row)

    def update_ingestion_job(
        self,
        office_id: str,
        job_id: int,
        status: str,
        *,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE ingestion_jobs SET status=?, error=?, updated_at=? WHERE id=? AND office_id=?",
                (status, error, self._now(), job_id, office_id),
            )
            row = conn.execute("SELECT * FROM ingestion_jobs WHERE id=? AND office_id=?", (job_id, office_id)).fetchone()
            return dict(row) if row else None

    def list_matter_ingestion_jobs(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT j.*, d.display_name AS document_name, d.filename
                FROM ingestion_jobs j
                JOIN documents d ON d.id = j.document_id
                WHERE j.office_id=? AND j.matter_id=?
                ORDER BY j.updated_at DESC, j.id DESC
                """,
                (office_id, matter_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def replace_document_chunks(
        self,
        office_id: str,
        matter_id: int,
        document_id: int,
        chunks: list[dict[str, Any]],
    ) -> int:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM document_chunks WHERE office_id=? AND matter_id=? AND document_id=?",
                (office_id, matter_id, document_id),
            )
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO document_chunks (
                        document_id, office_id, matter_id, chunk_index, text, token_count, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        office_id,
                        matter_id,
                        chunk["chunk_index"],
                        chunk["text"],
                        chunk["token_count"],
                        chunk["metadata_json"],
                    ),
                )
            return len(chunks)

    def list_document_chunks(self, office_id: str, document_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            document = conn.execute(
                "SELECT * FROM documents WHERE id=? AND office_id=?",
                (document_id, office_id),
            ).fetchone()
            if not document:
                return None
            rows = conn.execute(
                """
                SELECT c.*, d.display_name, d.filename, d.source_type
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.document_id=? AND c.office_id=?
                ORDER BY c.chunk_index ASC
                """,
                (document_id, office_id),
            ).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                try:
                    item["metadata"] = json.loads(str(item.get("metadata_json") or "{}"))
                except json.JSONDecodeError:
                    item["metadata"] = {}
                items.append(item)
            return items

    def search_document_chunks(
        self,
        office_id: str,
        matter_id: int,
        *,
        document_ids: list[int] | None = None,
        source_types: list[str] | None = None,
        filename_contains: str | None = None,
    ) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            query = """
                SELECT c.*, d.display_name, d.filename, d.source_type, d.content_type, d.source_ref
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.office_id=? AND c.matter_id=? AND d.ingest_status='indexed'
            """
            params: list[Any] = [office_id, matter_id]
            if document_ids:
                placeholders = ",".join(["?"] * len(document_ids))
                query += f" AND c.document_id IN ({placeholders})"
                params.extend(document_ids)
            if source_types:
                placeholders = ",".join(["?"] * len(source_types))
                query += f" AND d.source_type IN ({placeholders})"
                params.extend(source_types)
            if filename_contains:
                query += " AND (d.filename LIKE ? OR d.display_name LIKE ?)"
                pattern = f"%{filename_contains}%"
                params.extend([pattern, pattern])
            query += " ORDER BY c.document_id ASC, c.chunk_index ASC"
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def create_task(
        self,
        title: str,
        due_at: str | None,
        priority: str,
        owner: str,
        *,
        office_id: str = "default-office",
        matter_id: int | None = None,
        origin_type: str | None = None,
        origin_ref: str | None = None,
        recommended_by: str | None = None,
        explanation: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            if matter_id is not None and not self._get_matter_row(conn, matter_id, office_id):
                raise ValueError("Dosya bulunamadı.")
            now = self._now()
            cur = conn.execute(
                """
                INSERT INTO tasks (
                    office_id, matter_id, title, due_at, priority, status, owner,
                    origin_type, origin_ref, recommended_by, explanation, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
                """,
                (office_id, matter_id, title, due_at, priority, owner, origin_type, origin_ref, recommended_by, explanation, now, now),
            )
            task_id = cur.lastrowid
            if matter_id is not None:
                self._add_matter_timeline_event(
                    conn,
                    matter_id,
                    "task_created",
                    "Dosya görevi oluşturuldu",
                    title,
                    due_at,
                    owner,
                )
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(row)

    def list_matter_tasks(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                "SELECT * FROM tasks WHERE office_id=? AND matter_id=? ORDER BY updated_at DESC, id DESC",
                (office_id, matter_id),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_tasks(self, owner: str, matter_id: int | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if matter_id is None:
                rows = conn.execute("SELECT * FROM tasks WHERE owner=? ORDER BY id DESC", (owner,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE owner=? AND matter_id=? ORDER BY id DESC",
                    (owner, matter_id),
                ).fetchall()
            return [dict(r) for r in rows]

    def complete_tasks_bulk(self, task_ids: list[int], owner: str) -> int:
        if not task_ids:
            return 0
        placeholders = ",".join(["?"] * len(task_ids))
        params = [*task_ids, owner]
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM tasks WHERE id IN ({placeholders}) AND owner=? AND status!='completed'",
                params,
            ).fetchall()
            cur = conn.execute(
                f"UPDATE tasks SET status='completed', updated_at=? WHERE id IN ({placeholders}) AND owner=? AND status!='completed'",
                [self._now(), *params],
            )
            for row in rows:
                if row["matter_id"] is not None:
                    self._add_matter_timeline_event(
                        conn,
                        int(row["matter_id"]),
                        "task_completed",
                        "Dosya görevi tamamlandı",
                        str(row["title"]),
                        self._now(),
                        owner,
                    )
            return int(cur.rowcount or 0)

    def update_task_status(self, task_id: int, status: str, owner: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
            if not row:
                return None
            conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=? AND owner=?", (status, self._now(), task_id, owner))
            if row["matter_id"] is not None:
                self._add_matter_timeline_event(
                    conn,
                    int(row["matter_id"]),
                    "task_status_updated",
                    "Dosya görevi durumu değişti",
                    f"{row['title']} -> {status}",
                    self._now(),
                    owner,
                )
            updated = conn.execute("SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
            return dict(updated) if updated else None

    def update_task_due_at(self, task_id: int, due_at: str | None, owner: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
            if not row:
                return None
            conn.execute("UPDATE tasks SET due_at=?, updated_at=? WHERE id=? AND owner=?", (due_at, self._now(), task_id, owner))
            if row["matter_id"] is not None:
                self._add_matter_timeline_event(
                    conn,
                    int(row["matter_id"]),
                    "task_due_updated",
                    "Dosya görevi tarihi güncellendi",
                    f"{row['title']} -> {due_at or 'temizlendi'}",
                    due_at or self._now(),
                    owner,
                )
            updated = conn.execute("SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
            return dict(updated) if updated else None

    @staticmethod
    def _decode_draft(row: dict[str, Any]) -> dict[str, Any]:
        if row.get("source_context_json"):
            try:
                row["source_context"] = json.loads(row["source_context_json"])
            except json.JSONDecodeError:
                row["source_context"] = None
        else:
            row["source_context"] = None
        row["manual_review_required"] = bool(row.get("manual_review_required"))
        row.pop("source_context_json", None)
        return row

    def create_query_job(self, owner: str, query_text: str, model_profile: str | None, continue_in_background: bool) -> dict:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO query_jobs (owner, status, query_text, model_profile, continue_in_background, created_at, updated_at)
                VALUES (?, 'running', ?, ?, ?, ?, ?)
                """,
                (owner, query_text, model_profile, 1 if continue_in_background else 0, now, now),
            )
            row = conn.execute("SELECT * FROM query_jobs WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_query_job(dict(row))

    def get_query_job(self, job_id: int, owner: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            return self._decode_query_job(dict(row)) if row else None

    def list_query_jobs(self, owner: str, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM query_jobs WHERE owner=? ORDER BY id DESC LIMIT ?",
                (owner, max(1, min(limit, 100))),
            ).fetchall()
            return [self._decode_query_job(dict(row)) for row in rows]

    def update_query_job_status(
        self,
        job_id: int,
        owner: str,
        status: str,
        *,
        result: dict | None = None,
        error: str | None = None,
        detached: bool | None = None,
        toast_pending: bool | None = None,
    ) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            if not row:
                return None
            current = dict(row)
            result_json = json.dumps(result, ensure_ascii=False) if result is not None else current.get("result_json")
            detached_val = current["detached"] if detached is None else (1 if detached else 0)
            toast_val = current["toast_pending"] if toast_pending is None else (1 if toast_pending else 0)
            completed_at = self._now() if status in {"completed", "cancelled", "failed"} else None
            conn.execute(
                """
                UPDATE query_jobs
                SET status=?, result_json=?, error=?, detached=?, toast_pending=?, updated_at=?, completed_at=COALESCE(?, completed_at)
                WHERE id=? AND owner=?
                """,
                (status, result_json, error, detached_val, toast_val, self._now(), completed_at, job_id, owner),
            )
            updated = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            return self._decode_query_job(dict(updated)) if updated else None

    def request_query_job_cancel(self, job_id: int, owner: str, keep_background: bool) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            if not row:
                return None
            if keep_background:
                conn.execute(
                    "UPDATE query_jobs SET detached=1, updated_at=? WHERE id=? AND owner=?",
                    (self._now(), job_id, owner),
                )
            else:
                conn.execute(
                    "UPDATE query_jobs SET cancel_requested=1, updated_at=? WHERE id=? AND owner=?",
                    (self._now(), job_id, owner),
                )
            updated = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            return self._decode_query_job(dict(updated)) if updated else None

    def acknowledge_query_job_toast(self, job_id: int, owner: str) -> dict | None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE query_jobs SET toast_pending=0, updated_at=? WHERE id=? AND owner=?",
                (self._now(), job_id, owner),
            )
            row = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            return self._decode_query_job(dict(row)) if row else None

    def set_query_job_runtime_job(self, job_id: int, owner: str, runtime_job_id: int) -> dict | None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE query_jobs SET runtime_job_id=?, updated_at=? WHERE id=? AND owner=?",
                (int(runtime_job_id), self._now(), job_id, owner),
            )
            row = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            return self._decode_query_job(dict(row)) if row else None

    @staticmethod
    def _decode_query_job(row: dict) -> dict:
        if row.get("result_json"):
            try:
                row["result"] = json.loads(row["result_json"])
            except json.JSONDecodeError:
                row["result"] = None
        else:
            row["result"] = None
        row["continue_in_background"] = bool(row.get("continue_in_background"))
        row["detached"] = bool(row.get("detached"))
        row["cancel_requested"] = bool(row.get("cancel_requested"))
        row["toast_pending"] = bool(row.get("toast_pending"))
        row["runtime_job_id"] = int(row["runtime_job_id"]) if row.get("runtime_job_id") not in {None, ""} else None
        row.pop("result_json", None)
        return row

    def create_runtime_job(
        self,
        office_id: str,
        *,
        job_type: str,
        worker_kind: str,
        requested_by: str,
        payload: dict[str, Any] | None = None,
        write_intent: str = "read_only",
        priority: int = 100,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO runtime_jobs (
                    office_id, job_type, worker_kind, status, write_intent, payload_json,
                    requested_by, priority, created_at, updated_at
                )
                VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    job_type,
                    worker_kind,
                    str(write_intent or "read_only"),
                    json.dumps(payload or {}, ensure_ascii=False),
                    requested_by,
                    int(priority),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM runtime_jobs WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_runtime_job(dict(row)) if row else {}

    def list_runtime_jobs(
        self,
        office_id: str,
        *,
        worker_kind: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM runtime_jobs WHERE office_id=?"
            params: list[Any] = [office_id]
            if worker_kind:
                query += " AND worker_kind=?"
                params.append(worker_kind)
            if status:
                query += " AND status=?"
                params.append(status)
            query += " ORDER BY priority ASC, id ASC LIMIT ?"
            params.append(max(1, min(limit, 500)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_runtime_job(dict(row)) for row in rows]

    def claim_runtime_job(
        self,
        office_id: str,
        *,
        worker_kind: str,
        lease_owner: str,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM runtime_jobs
                WHERE office_id=? AND worker_kind=? AND status='queued'
                ORDER BY priority ASC, id ASC
                LIMIT 1
                """,
                (office_id, worker_kind),
            ).fetchone()
            if not row:
                return None
            now = self._now()
            conn.execute(
                """
                UPDATE runtime_jobs
                SET status='running', lease_owner=?, leased_at=?, updated_at=?
                WHERE id=? AND office_id=? AND status='queued'
                """,
                (lease_owner, now, now, int(row["id"]), office_id),
            )
            claimed = conn.execute("SELECT * FROM runtime_jobs WHERE id=?", (int(row["id"]),)).fetchone()
            return self._decode_runtime_job(dict(claimed)) if claimed else None

    def finish_runtime_job(
        self,
        office_id: str,
        job_id: int,
        *,
        lease_owner: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM runtime_jobs WHERE office_id=? AND id=?",
                (office_id, job_id),
            ).fetchone()
            if not row:
                return None
            if str(row["lease_owner"] or "") != str(lease_owner or ""):
                return None
            now = self._now()
            conn.execute(
                """
                UPDATE runtime_jobs
                SET status=?, result_json=?, error=?, completed_at=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    str(status or "completed"),
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    error,
                    now if str(status or "").strip().lower() in {"completed", "failed", "cancelled"} else None,
                    now,
                    office_id,
                    job_id,
                ),
            )
            updated = conn.execute("SELECT * FROM runtime_jobs WHERE office_id=? AND id=?", (office_id, job_id)).fetchone()
            return self._decode_runtime_job(dict(updated)) if updated else None

    def summarize_runtime_jobs(
        self,
        office_id: str,
        *,
        worker_kind: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            params: list[Any] = [office_id]
            query = "SELECT status, COUNT(*) AS count FROM runtime_jobs WHERE office_id=?"
            if worker_kind:
                query += " AND worker_kind=?"
                params.append(worker_kind)
            query += " GROUP BY status"
            rows = conn.execute(query, params).fetchall()
            counts = {
                str(row["status"] or ""): int(row["count"] or 0)
                for row in rows
                if str(row["status"] or "").strip()
            }
            queued_params: list[Any] = [office_id]
            queued_query = "SELECT MIN(created_at) AS oldest_created_at FROM runtime_jobs WHERE office_id=? AND status='queued'"
            if worker_kind:
                queued_query += " AND worker_kind=?"
                queued_params.append(worker_kind)
            queued_row = conn.execute(queued_query, queued_params).fetchone()
            failed_params: list[Any] = [office_id]
            failed_query = "SELECT MAX(updated_at) AS last_failed_at FROM runtime_jobs WHERE office_id=? AND status='failed'"
            if worker_kind:
                failed_query += " AND worker_kind=?"
                failed_params.append(worker_kind)
            failed_row = conn.execute(failed_query, failed_params).fetchone()
            return {
                "counts": counts,
                "queued": int(counts.get("queued", 0)),
                "running": int(counts.get("running", 0)),
                "completed": int(counts.get("completed", 0)),
                "failed": int(counts.get("failed", 0)),
                "oldest_queued_created_at": str(queued_row["oldest_created_at"] or "") or None if queued_row else None,
                "last_failed_at": str(failed_row["last_failed_at"] or "") or None if failed_row else None,
            }

    @staticmethod
    def _decode_runtime_job(row: dict[str, Any]) -> dict[str, Any]:
        if row.get("payload_json"):
            try:
                row["payload"] = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                row["payload"] = {}
        else:
            row["payload"] = {}
        if row.get("result_json"):
            try:
                row["result"] = json.loads(row["result_json"])
            except json.JSONDecodeError:
                row["result"] = None
        else:
            row["result"] = None
        row.pop("payload_json", None)
        row.pop("result_json", None)
        return row

    def _add_email_event(self, conn: sqlite3.Connection, draft_id: int, event_type: str, actor: str, note: str | None = None) -> None:
        conn.execute(
            "INSERT INTO email_draft_events (draft_id, event_type, actor, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (draft_id, event_type, actor, note, self._now()),
        )

    def create_email_draft(
        self,
        to_email: str,
        subject: str,
        body: str,
        requested_by: str,
        *,
        office_id: str = "default-office",
        matter_id: int | None = None,
    ) -> dict:
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            if matter_id is not None and not self._get_matter_row(conn, matter_id, office_id):
                raise ValueError("Dosya bulunamadı.")
            cur = conn.execute(
                """
                INSERT INTO email_drafts (office_id, matter_id, to_email, subject, body, status, review_status, requested_by, created_at)
                VALUES (?, ?, ?, ?, ?, 'draft', 'draft_ready', ?, ?)
                """,
                (office_id, matter_id, to_email, subject, body, requested_by, self._now()),
            )
            draft_id = int(cur.lastrowid)
            self._add_email_event(conn, draft_id, "draft_created", requested_by, "Taslak oluşturuldu")
            if matter_id is not None:
                self._add_matter_timeline_event(
                    conn,
                    matter_id,
                    "external_draft_created",
                    "Email draft created",
                    subject,
                    self._now(),
                    requested_by,
                )
            row = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            return dict(row)

    def approve_email_draft(self, draft_id: int, approved_by: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            if not row:
                return None
            if row["status"] != "draft":
                return dict(row)
            conn.execute(
                "UPDATE email_drafts SET status='approved', review_status='approved', approved_by=? WHERE id=?",
                (approved_by, draft_id),
            )
            self._add_email_event(conn, draft_id, "approved", approved_by, "Taslak onaylandı")
            updated = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            return dict(updated) if updated else None

    def retract_email_draft(self, draft_id: int, actor: str, note: str | None = None) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            if not row:
                return None
            if row["status"] != "approved":
                return dict(row)
            conn.execute(
                "UPDATE email_drafts SET status='draft', review_status='draft_ready', approved_by=NULL WHERE id=?",
                (draft_id,),
            )
            self._add_email_event(conn, draft_id, "retracted", actor, note or "Tek tık geri çekme")
            updated = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            return dict(updated) if updated else None

    def get_email_draft(self, draft_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            return dict(row) if row else None

    def list_email_drafts(self, owner: str | None = None) -> list[dict]:
        with self._conn() as conn:
            if owner:
                rows = conn.execute(
                    "SELECT * FROM email_drafts WHERE requested_by=? ORDER BY id DESC",
                    (owner,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM email_drafts ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]

    def list_email_draft_events(self, draft_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM email_draft_events WHERE draft_id=? ORDER BY id DESC",
                (draft_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def _decode_social_event(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "metadata_json", "metadata")
        row["notify_user"] = bool(row.get("notify_user"))
        row["evidence_value"] = bool(row.get("evidence_value"))
        return row

    def add_social_event(
        self,
        source: str,
        handle: str,
        content: str,
        risk_score: float,
        *,
        office_id: str = "default-office",
        category: str | None = None,
        severity: str = "info",
        notify_user: bool = False,
        evidence_value: bool = False,
        summary: str | None = None,
        recommended_action: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            cur = conn.execute(
                """
                INSERT INTO social_events (
                    office_id, source, handle, content, risk_score, category, severity,
                    notify_user, evidence_value, summary, recommended_action, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    source,
                    handle,
                    content,
                    risk_score,
                    category,
                    severity,
                    1 if notify_user else 0,
                    1 if evidence_value else 0,
                    summary,
                    recommended_action,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    self._now(),
                ),
            )
            row = conn.execute("SELECT * FROM social_events WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_social_event(dict(row)) if row else {}

    def list_social_events(self, limit: int = 20, *, office_id: str | None = None) -> list[dict]:
        with self._conn() as conn:
            query = "SELECT * FROM social_events"
            params: list[Any] = []
            if office_id:
                query += " WHERE office_id=?"
                params.append(office_id)
            query += " ORDER BY id DESC LIMIT ?"
            params.append(max(1, min(limit, 100)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_social_event(dict(r)) for r in rows]

    @staticmethod
    def _decode_json_field(row: dict[str, Any], source_key: str, target_key: str) -> dict[str, Any]:
        raw = row.get(source_key)
        if raw:
            try:
                row[target_key] = json.loads(str(raw))
            except json.JSONDecodeError:
                row[target_key] = []
        else:
            row[target_key] = []
        row.pop(source_key, None)
        return row

    @staticmethod
    def _decode_json_object_field(row: dict[str, Any], source_key: str, target_key: str) -> dict[str, Any]:
        raw = row.get(source_key)
        if raw:
            try:
                value = json.loads(str(raw))
            except json.JSONDecodeError:
                value = {}
            row[target_key] = value if isinstance(value, dict) else {}
        else:
            row[target_key] = {}
        row.pop(source_key, None)
        return row

    @classmethod
    def _normalize_channel_memory_state(cls, value: Any) -> str:
        state = str(value or "").strip().lower()
        if state in cls.CHANNEL_MEMORY_STATES:
            return state
        return "operational_only"

    @classmethod
    def _merge_channel_metadata(
        cls,
        existing_metadata: dict[str, Any] | None,
        incoming_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(existing_metadata or {})
        merged.update(dict(incoming_metadata or {}))
        merged["memory_state"] = cls._normalize_channel_memory_state(merged.get("memory_state"))
        return merged

    def _load_existing_channel_metadata(
        self,
        conn: sqlite3.Connection,
        *,
        table: str,
        office_id: str,
        lookup: dict[str, Any],
    ) -> dict[str, Any]:
        where_parts = ["office_id=?"]
        params: list[Any] = [office_id]
        for key, value in lookup.items():
            where_parts.append(f"{key}=?")
            params.append(value)
        row = conn.execute(
            f"SELECT metadata_json FROM {table} WHERE {' AND '.join(where_parts)}",
            params,
        ).fetchone()
        if not row:
            return {}
        raw = row["metadata_json"]
        if not raw:
            return {}
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    @classmethod
    def _apply_channel_memory_state(cls, row: dict[str, Any]) -> dict[str, Any]:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        state = cls._normalize_channel_memory_state(metadata.get("memory_state"))
        metadata["memory_state"] = state
        row["metadata"] = metadata
        row["memory_state"] = state
        return row

    def upsert_connected_account(
        self,
        office_id: str,
        provider: str,
        *,
        account_label: str,
        status: str,
        scopes: list[str] | None = None,
        connected_at: str | None = None,
        last_sync_at: str | None = None,
        manual_review_required: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            conn.execute(
                """
                INSERT INTO connected_accounts (
                    office_id, provider, account_label, status, scopes_json, connected_at,
                    last_sync_at, manual_review_required, metadata_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider) DO UPDATE SET
                    account_label=excluded.account_label,
                    status=excluded.status,
                    scopes_json=excluded.scopes_json,
                    connected_at=excluded.connected_at,
                    last_sync_at=excluded.last_sync_at,
                    manual_review_required=excluded.manual_review_required,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    account_label,
                    status,
                    json.dumps(scopes or [], ensure_ascii=False),
                    connected_at,
                    last_sync_at,
                    1 if manual_review_required else 0,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM connected_accounts WHERE office_id=? AND provider=?",
                (office_id, provider),
            ).fetchone()
            return self._decode_connected_account(dict(row)) if row else {}

    def get_connected_account(self, office_id: str, provider: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM connected_accounts WHERE office_id=? AND provider=?",
                (office_id, provider),
            ).fetchone()
            return self._decode_connected_account(dict(row)) if row else None

    def list_connected_accounts(self, office_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM connected_accounts WHERE office_id=? ORDER BY provider ASC",
                (office_id,),
            ).fetchall()
            return [self._decode_connected_account(dict(row)) for row in rows]

    @staticmethod
    def _decode_connected_account(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "scopes_json", "scopes")
        row = Persistence._decode_json_field(row, "metadata_json", "metadata")
        row["manual_review_required"] = bool(row.get("manual_review_required"))
        return row

    def upsert_user_profile(
        self,
        office_id: str,
        *,
        display_name: str | None = None,
        favorite_color: str | None = None,
        food_preferences: str | None = None,
        transport_preference: str | None = None,
        weather_preference: str | None = None,
        travel_preferences: str | None = None,
        home_base: str | None = None,
        current_location: str | None = None,
        location_preferences: str | None = None,
        maps_preference: str | None = None,
        prayer_notifications_enabled: bool | None = None,
        prayer_habit_notes: str | None = None,
        communication_style: str | None = None,
        assistant_notes: str | None = None,
        important_dates: list[dict[str, Any]] | None = None,
        related_profiles: list[dict[str, Any]] | None = None,
        contact_profile_overrides: list[dict[str, Any]] | None = None,
        inbox_watch_rules: list[dict[str, Any]] | None = None,
        inbox_keyword_rules: list[dict[str, Any]] | None = None,
        inbox_block_rules: list[dict[str, Any]] | None = None,
        source_preference_rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            existing = conn.execute("SELECT * FROM user_profiles WHERE office_id=?", (office_id,)).fetchone()
            existing_profile = self._decode_user_profile(dict(existing)) if existing else self._empty_user_profile(office_id)
            next_related_profiles = self._sanitize_related_profiles(
                related_profiles if related_profiles is not None else (existing_profile.get("related_profiles") or [])
            )
            next_contact_profile_overrides = self._sanitize_contact_profile_overrides(
                contact_profile_overrides if contact_profile_overrides is not None else (existing_profile.get("contact_profile_overrides") or [])
            )
            conn.execute(
                """
                INSERT INTO user_profiles (
                    office_id, display_name, favorite_color, food_preferences, transport_preference, weather_preference,
                    travel_preferences, home_base, current_location, location_preferences, maps_preference,
                    prayer_notifications_enabled, prayer_habit_notes, communication_style, assistant_notes,
                    important_dates_json, related_profiles_json, contact_profile_overrides_json, inbox_watch_rules_json, inbox_keyword_rules_json,
                    inbox_block_rules_json, source_preference_rules_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    favorite_color=excluded.favorite_color,
                    food_preferences=excluded.food_preferences,
                    transport_preference=excluded.transport_preference,
                    weather_preference=excluded.weather_preference,
                    travel_preferences=excluded.travel_preferences,
                    home_base=excluded.home_base,
                    current_location=excluded.current_location,
                    location_preferences=excluded.location_preferences,
                    maps_preference=excluded.maps_preference,
                    prayer_notifications_enabled=excluded.prayer_notifications_enabled,
                    prayer_habit_notes=excluded.prayer_habit_notes,
                    communication_style=excluded.communication_style,
                    assistant_notes=excluded.assistant_notes,
                    important_dates_json=excluded.important_dates_json,
                    related_profiles_json=excluded.related_profiles_json,
                    contact_profile_overrides_json=excluded.contact_profile_overrides_json,
                    inbox_watch_rules_json=excluded.inbox_watch_rules_json,
                    inbox_keyword_rules_json=excluded.inbox_keyword_rules_json,
                    inbox_block_rules_json=excluded.inbox_block_rules_json,
                    source_preference_rules_json=excluded.source_preference_rules_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    display_name,
                    favorite_color,
                    food_preferences,
                    transport_preference,
                    weather_preference,
                    travel_preferences,
                    home_base,
                    current_location,
                    location_preferences,
                    maps_preference,
                    1 if prayer_notifications_enabled is True else 0 if prayer_notifications_enabled is False else 1 if existing_profile.get("prayer_notifications_enabled") else 0,
                    prayer_habit_notes,
                    communication_style,
                    assistant_notes,
                    json.dumps(important_dates if important_dates is not None else (existing_profile.get("important_dates") or []), ensure_ascii=False),
                    json.dumps(next_related_profiles, ensure_ascii=False),
                    json.dumps(next_contact_profile_overrides, ensure_ascii=False),
                    json.dumps(inbox_watch_rules if inbox_watch_rules is not None else (existing_profile.get("inbox_watch_rules") or []), ensure_ascii=False),
                    json.dumps(inbox_keyword_rules if inbox_keyword_rules is not None else (existing_profile.get("inbox_keyword_rules") or []), ensure_ascii=False),
                    json.dumps(inbox_block_rules if inbox_block_rules is not None else (existing_profile.get("inbox_block_rules") or []), ensure_ascii=False),
                    json.dumps(source_preference_rules if source_preference_rules is not None else (existing_profile.get("source_preference_rules") or []), ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM user_profiles WHERE office_id=?", (office_id,)).fetchone()
            return self._decode_user_profile(dict(row)) if row else self._empty_user_profile(office_id)

    def get_user_profile(self, office_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM user_profiles WHERE office_id=?", (office_id,)).fetchone()
            return self._decode_user_profile(dict(row)) if row else self._empty_user_profile(office_id)

    def upsert_assistant_runtime_profile(
        self,
        office_id: str,
        *,
        assistant_name: str | None = None,
        role_summary: str | None = None,
        tone: str | None = None,
        avatar_path: str | None = None,
        soul_notes: str | None = None,
        tools_notes: str | None = None,
        assistant_forms: list[dict[str, Any]] | None = None,
        behavior_contract: dict[str, Any] | None = None,
        evolution_history: list[dict[str, Any]] | None = None,
        heartbeat_extra_checks: list[str] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            conn.execute(
                """
                INSERT INTO assistant_runtime_profiles (
                    office_id, assistant_name, role_summary, tone, avatar_path, soul_notes,
                    tools_notes, assistant_forms_json, behavior_contract_json, evolution_history_json,
                    heartbeat_extra_checks_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id) DO UPDATE SET
                    assistant_name=excluded.assistant_name,
                    role_summary=excluded.role_summary,
                    tone=excluded.tone,
                    avatar_path=excluded.avatar_path,
                    soul_notes=excluded.soul_notes,
                    tools_notes=excluded.tools_notes,
                    assistant_forms_json=excluded.assistant_forms_json,
                    behavior_contract_json=excluded.behavior_contract_json,
                    evolution_history_json=excluded.evolution_history_json,
                    heartbeat_extra_checks_json=excluded.heartbeat_extra_checks_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    assistant_name,
                    role_summary,
                    tone,
                    avatar_path,
                    soul_notes,
                    tools_notes,
                    json.dumps(assistant_forms or [], ensure_ascii=False),
                    json.dumps(behavior_contract or {}, ensure_ascii=False),
                    json.dumps(evolution_history or [], ensure_ascii=False),
                    json.dumps(heartbeat_extra_checks or [], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM assistant_runtime_profiles WHERE office_id=?", (office_id,)).fetchone()
            return self._decode_assistant_runtime_profile(dict(row)) if row else self._empty_assistant_runtime_profile(office_id)

    def get_assistant_runtime_profile(self, office_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM assistant_runtime_profiles WHERE office_id=?", (office_id,)).fetchone()
            return self._decode_assistant_runtime_profile(dict(row)) if row else self._empty_assistant_runtime_profile(office_id)

    def create_personal_model_session(
        self,
        office_id: str,
        *,
        session_id: str,
        scope: str,
        source: str,
        module_keys: list[str],
        status: str,
        current_question_id: str | None,
        state: dict[str, Any] | None,
        progress: dict[str, Any] | None,
        summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            conn.execute(
                """
                INSERT INTO personal_model_sessions (
                    id, office_id, scope, source, module_keys_json, status, current_question_id,
                    state_json, progress_json, summary_json, started_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    office_id,
                    scope,
                    source,
                    json.dumps(module_keys or [], ensure_ascii=False),
                    status,
                    current_question_id,
                    json.dumps(state or {}, ensure_ascii=False),
                    json.dumps(progress or {}, ensure_ascii=False),
                    json.dumps(summary or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM personal_model_sessions WHERE office_id=? AND id=?", (office_id, session_id)).fetchone()
            return self._decode_personal_model_session(dict(row)) if row else {}

    def get_personal_model_session(self, office_id: str, session_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM personal_model_sessions WHERE office_id=? AND id=?",
                (office_id, session_id),
            ).fetchone()
            return self._decode_personal_model_session(dict(row)) if row else None

    def list_personal_model_sessions(self, office_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM personal_model_sessions WHERE office_id=? ORDER BY updated_at DESC LIMIT ?",
                (office_id, max(1, min(limit, 200))),
            ).fetchall()
            return [self._decode_personal_model_session(dict(row)) for row in rows]

    def update_personal_model_session(
        self,
        office_id: str,
        session_id: str,
        *,
        status: str | None = None,
        current_question_id: str | None = None,
        state: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        paused_at: str | None = None,
        completed_at: str | None = None,
    ) -> dict[str, Any] | None:
        existing = self.get_personal_model_session(office_id, session_id)
        if not existing:
            return None
        now = self._now()
        next_status = status if status is not None else existing.get("status")
        next_state = state if state is not None else dict(existing.get("state") or {})
        next_progress = progress if progress is not None else dict(existing.get("progress") or {})
        next_summary = summary if summary is not None else dict(existing.get("summary") or {})
        next_current_question_id = current_question_id if current_question_id is not None else existing.get("current_question_id")
        next_paused_at = paused_at if paused_at is not None else existing.get("paused_at")
        next_completed_at = completed_at if completed_at is not None else existing.get("completed_at")
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE personal_model_sessions
                SET status=?, current_question_id=?, state_json=?, progress_json=?, summary_json=?,
                    paused_at=?, completed_at=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    next_status,
                    next_current_question_id,
                    json.dumps(next_state or {}, ensure_ascii=False),
                    json.dumps(next_progress or {}, ensure_ascii=False),
                    json.dumps(next_summary or {}, ensure_ascii=False),
                    next_paused_at,
                    next_completed_at,
                    now,
                    office_id,
                    session_id,
                ),
            )
            row = conn.execute("SELECT * FROM personal_model_sessions WHERE office_id=? AND id=?", (office_id, session_id)).fetchone()
            return self._decode_personal_model_session(dict(row)) if row else None

    def add_personal_model_raw_entry(
        self,
        office_id: str,
        *,
        session_id: str | None,
        module_key: str,
        question_id: str,
        question_text: str,
        answer_text: str,
        answer_kind: str,
        answer_value: dict[str, Any] | None,
        source: str,
        confidence_type: str,
        confidence: float,
        explicit: bool,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            cur = conn.execute(
                """
                INSERT INTO personal_model_raw_entries (
                    office_id, session_id, module_key, question_id, question_text, answer_text, answer_kind,
                    answer_value_json, source, confidence_type, confidence, explicit, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    session_id,
                    module_key,
                    question_id,
                    question_text,
                    answer_text,
                    answer_kind,
                    json.dumps(answer_value or {}, ensure_ascii=False),
                    source,
                    confidence_type,
                    round(float(confidence), 4),
                    1 if explicit else 0,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            row = conn.execute("SELECT * FROM personal_model_raw_entries WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_personal_model_raw_entry(dict(row)) if row else {}

    def list_personal_model_raw_entries(
        self,
        office_id: str,
        *,
        session_id: str | None = None,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            params: list[Any] = [office_id]
            query = "SELECT * FROM personal_model_raw_entries WHERE office_id=?"
            if session_id:
                query += " AND session_id=?"
                params.append(session_id)
            query += " ORDER BY id DESC LIMIT ?"
            params.append(max(1, min(limit, 400)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_personal_model_raw_entry(dict(row)) for row in rows]

    def upsert_personal_model_fact(
        self,
        office_id: str,
        *,
        fact_id: str,
        session_id: str | None,
        category: str,
        fact_key: str,
        title: str,
        value_text: str,
        value_json: dict[str, Any] | None,
        confidence: float,
        confidence_type: str,
        source_entry_id: int | None,
        visibility: str,
        scope: str,
        sensitive: bool,
        enabled: bool,
        never_use: bool,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            conn.execute(
                """
                INSERT INTO personal_model_facts (
                    id, office_id, session_id, category, fact_key, title, value_text, value_json, confidence,
                    confidence_type, source_entry_id, visibility, scope, sensitive, enabled, never_use,
                    created_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, fact_key, scope) DO UPDATE SET
                    session_id=excluded.session_id,
                    category=excluded.category,
                    title=excluded.title,
                    value_text=excluded.value_text,
                    value_json=excluded.value_json,
                    confidence=excluded.confidence,
                    confidence_type=excluded.confidence_type,
                    source_entry_id=excluded.source_entry_id,
                    visibility=excluded.visibility,
                    sensitive=excluded.sensitive,
                    enabled=excluded.enabled,
                    never_use=excluded.never_use,
                    updated_at=excluded.updated_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    fact_id,
                    office_id,
                    session_id,
                    category,
                    fact_key,
                    title,
                    value_text,
                    json.dumps(value_json or {}, ensure_ascii=False),
                    round(float(confidence), 4),
                    confidence_type,
                    source_entry_id,
                    visibility,
                    scope,
                    1 if sensitive else 0,
                    1 if enabled else 0,
                    1 if never_use else 0,
                    now,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            row = conn.execute(
                "SELECT * FROM personal_model_facts WHERE office_id=? AND fact_key=? AND scope=?",
                (office_id, fact_key, scope),
            ).fetchone()
            return self._decode_personal_model_fact(dict(row)) if row else {}

    def get_personal_model_fact(self, office_id: str, fact_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM personal_model_facts WHERE office_id=? AND id=?",
                (office_id, fact_id),
            ).fetchone()
            return self._decode_personal_model_fact(dict(row)) if row else None

    def list_personal_model_facts(
        self,
        office_id: str,
        *,
        category: str | None = None,
        scope: str | None = None,
        include_disabled: bool = True,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            params: list[Any] = [office_id]
            query = "SELECT * FROM personal_model_facts WHERE office_id=?"
            if category:
                query += " AND category=?"
                params.append(category)
            if scope:
                query += " AND scope=?"
                params.append(scope)
            if not include_disabled:
                query += " AND enabled=1"
            query += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
            params.append(max(1, min(limit, 1000)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_personal_model_fact(dict(row)) for row in rows]

    def update_personal_model_fact(
        self,
        office_id: str,
        fact_id: str,
        *,
        title: str | None = None,
        value_text: str | None = None,
        value_json: dict[str, Any] | None = None,
        confidence: float | None = None,
        visibility: str | None = None,
        scope: str | None = None,
        sensitive: bool | None = None,
        enabled: bool | None = None,
        never_use: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        existing = self.get_personal_model_fact(office_id, fact_id)
        if not existing:
            return None
        next_metadata = dict(existing.get("metadata") or {})
        if metadata:
            next_metadata.update(metadata)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE personal_model_facts
                SET title=?, value_text=?, value_json=?, confidence=?, visibility=?, scope=?, sensitive=?,
                    enabled=?, never_use=?, metadata_json=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    title if title is not None else existing.get("title"),
                    value_text if value_text is not None else existing.get("value_text"),
                    json.dumps(value_json if value_json is not None else dict(existing.get("value_json") or {}), ensure_ascii=False),
                    round(float(confidence if confidence is not None else existing.get("confidence") or 0.0), 4),
                    visibility if visibility is not None else existing.get("visibility"),
                    scope if scope is not None else existing.get("scope"),
                    1 if (sensitive if sensitive is not None else bool(existing.get("sensitive"))) else 0,
                    1 if (enabled if enabled is not None else bool(existing.get("enabled"))) else 0,
                    1 if (never_use if never_use is not None else bool(existing.get("never_use"))) else 0,
                    json.dumps(next_metadata, ensure_ascii=False),
                    self._now(),
                    office_id,
                    fact_id,
                ),
            )
            row = conn.execute("SELECT * FROM personal_model_facts WHERE office_id=? AND id=?", (office_id, fact_id)).fetchone()
            return self._decode_personal_model_fact(dict(row)) if row else None

    def delete_personal_model_fact(self, office_id: str, fact_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM personal_model_facts WHERE office_id=? AND id=?",
                (office_id, fact_id),
            )
            return int(cur.rowcount or 0) > 0

    def create_personal_model_suggestion(
        self,
        office_id: str,
        *,
        suggestion_id: str,
        source: str,
        category: str,
        fact_key: str,
        title: str,
        prompt: str,
        proposed_value_text: str,
        proposed_value_json: dict[str, Any] | None,
        confidence: float,
        scope: str,
        sensitive: bool,
        evidence: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            conn.execute(
                """
                INSERT INTO personal_model_suggestions (
                    id, office_id, source, category, fact_key, title, prompt, proposed_value_text,
                    proposed_value_json, confidence, scope, sensitive, status, evidence_json, metadata_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    prompt=excluded.prompt,
                    proposed_value_text=excluded.proposed_value_text,
                    proposed_value_json=excluded.proposed_value_json,
                    confidence=excluded.confidence,
                    sensitive=excluded.sensitive,
                    evidence_json=excluded.evidence_json,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    suggestion_id,
                    office_id,
                    source,
                    category,
                    fact_key,
                    title,
                    prompt,
                    proposed_value_text,
                    json.dumps(proposed_value_json or {}, ensure_ascii=False),
                    round(float(confidence), 4),
                    scope,
                    1 if sensitive else 0,
                    json.dumps(evidence or {}, ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM personal_model_suggestions WHERE office_id=? AND id=?", (office_id, suggestion_id)).fetchone()
            return self._decode_personal_model_suggestion(dict(row)) if row else {}

    def get_personal_model_suggestion(self, office_id: str, suggestion_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM personal_model_suggestions WHERE office_id=? AND id=?",
                (office_id, suggestion_id),
            ).fetchone()
            return self._decode_personal_model_suggestion(dict(row)) if row else None

    def list_personal_model_suggestions(
        self,
        office_id: str,
        *,
        status: str | None = None,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            params: list[Any] = [office_id]
            query = "SELECT * FROM personal_model_suggestions WHERE office_id=?"
            if status:
                query += " AND status=?"
                params.append(status)
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_personal_model_suggestion(dict(row)) for row in rows]

    def update_personal_model_suggestion_status(self, office_id: str, suggestion_id: str, *, status: str, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
        existing = self.get_personal_model_suggestion(office_id, suggestion_id)
        if not existing:
            return None
        next_metadata = dict(existing.get("metadata") or {})
        if metadata:
            next_metadata.update(metadata)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE personal_model_suggestions
                SET status=?, metadata_json=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    status,
                    json.dumps(next_metadata, ensure_ascii=False),
                    self._now(),
                    office_id,
                    suggestion_id,
                ),
            )
            row = conn.execute("SELECT * FROM personal_model_suggestions WHERE office_id=? AND id=?", (office_id, suggestion_id)).fetchone()
            return self._decode_personal_model_suggestion(dict(row)) if row else None

    def create_epistemic_artifact(
        self,
        office_id: str,
        *,
        artifact_id: str,
        artifact_kind: str,
        source_kind: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        source_ref: str | None = None,
        sensitive: bool = False,
        immutable: bool = True,
    ) -> dict[str, Any]:
        now = self._now()
        payload_json = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
        content_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            conn.execute(
                """
                INSERT INTO epistemic_artifacts (
                    id, office_id, artifact_kind, source_kind, source_ref, summary, content_hash,
                    payload_json, provenance_json, sensitive, immutable, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    summary=excluded.summary,
                    payload_json=excluded.payload_json,
                    provenance_json=excluded.provenance_json,
                    source_ref=excluded.source_ref,
                    sensitive=excluded.sensitive
                """,
                (
                    artifact_id,
                    office_id,
                    artifact_kind,
                    source_kind,
                    source_ref,
                    summary,
                    content_hash,
                    payload_json,
                    json.dumps(provenance or {}, ensure_ascii=False),
                    1 if sensitive else 0,
                    1 if immutable else 0,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM epistemic_artifacts WHERE office_id=? AND id=?", (office_id, artifact_id)).fetchone()
            return self._decode_epistemic_artifact(dict(row)) if row else {}

    def get_epistemic_artifact(self, office_id: str, artifact_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM epistemic_artifacts WHERE office_id=? AND id=?",
                (office_id, artifact_id),
            ).fetchone()
            return self._decode_epistemic_artifact(dict(row)) if row else None

    def list_epistemic_artifacts(
        self,
        office_id: str,
        *,
        artifact_kind: str | None = None,
        source_kind: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            params: list[Any] = [office_id]
            query = "SELECT * FROM epistemic_artifacts WHERE office_id=?"
            if artifact_kind:
                query += " AND artifact_kind=?"
                params.append(artifact_kind)
            if source_kind:
                query += " AND source_kind=?"
                params.append(source_kind)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(1, min(limit, 1000)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_epistemic_artifact(dict(row)) for row in rows]

    def create_epistemic_claim(
        self,
        office_id: str,
        *,
        claim_id: str,
        subject_key: str,
        predicate: str,
        object_value_text: str,
        scope: str,
        epistemic_basis: str,
        validation_state: str,
        consent_class: str,
        retrieval_eligibility: str,
        object_value_json: dict[str, Any] | None = None,
        artifact_id: str | None = None,
        sensitive: bool = False,
        self_generated: bool = False,
        valid_from: str | None = None,
        valid_to: str | None = None,
        supersedes_claim_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            conn.execute(
                """
                INSERT INTO epistemic_claims (
                    id, office_id, artifact_id, subject_key, predicate, object_value_text, object_value_json,
                    scope, epistemic_basis, validation_state, consent_class, retrieval_eligibility,
                    sensitive, self_generated, valid_from, valid_to, supersedes_claim_id,
                    metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    artifact_id=excluded.artifact_id,
                    object_value_text=excluded.object_value_text,
                    object_value_json=excluded.object_value_json,
                    epistemic_basis=excluded.epistemic_basis,
                    validation_state=excluded.validation_state,
                    consent_class=excluded.consent_class,
                    retrieval_eligibility=excluded.retrieval_eligibility,
                    sensitive=excluded.sensitive,
                    self_generated=excluded.self_generated,
                    valid_from=excluded.valid_from,
                    valid_to=excluded.valid_to,
                    supersedes_claim_id=excluded.supersedes_claim_id,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    claim_id,
                    office_id,
                    artifact_id,
                    subject_key,
                    predicate,
                    object_value_text,
                    json.dumps(object_value_json or {}, ensure_ascii=False),
                    scope,
                    epistemic_basis,
                    validation_state,
                    consent_class,
                    retrieval_eligibility,
                    1 if sensitive else 0,
                    1 if self_generated else 0,
                    valid_from,
                    valid_to,
                    supersedes_claim_id,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM epistemic_claims WHERE office_id=? AND id=?", (office_id, claim_id)).fetchone()
            return self._decode_epistemic_claim(dict(row)) if row else {}

    def get_epistemic_claim(self, office_id: str, claim_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM epistemic_claims WHERE office_id=? AND id=?",
                (office_id, claim_id),
            ).fetchone()
            return self._decode_epistemic_claim(dict(row)) if row else None

    def list_epistemic_claims(
        self,
        office_id: str,
        *,
        subject_key: str | None = None,
        predicate: str | None = None,
        scope: str | None = None,
        artifact_id: str | None = None,
        include_blocked: bool = True,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            params: list[Any] = [office_id]
            query = "SELECT * FROM epistemic_claims WHERE office_id=?"
            if subject_key:
                query += " AND subject_key=?"
                params.append(subject_key)
            if predicate:
                query += " AND predicate=?"
                params.append(predicate)
            if scope:
                query += " AND scope=?"
                params.append(scope)
            if artifact_id:
                query += " AND artifact_id=?"
                params.append(artifact_id)
            if not include_blocked:
                query += " AND retrieval_eligibility NOT IN ('blocked', 'quarantined')"
            query += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
            params.append(max(1, min(limit, 2000)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_epistemic_claim(dict(row)) for row in rows]

    def update_epistemic_claim(
        self,
        office_id: str,
        claim_id: str,
        *,
        validation_state: str | None = None,
        retrieval_eligibility: str | None = None,
        valid_to: str | None = None,
        supersedes_claim_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        existing = self.get_epistemic_claim(office_id, claim_id)
        if not existing:
            return None
        next_metadata = dict(existing.get("metadata") or {})
        if metadata:
            next_metadata.update(metadata)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE epistemic_claims
                SET validation_state=?, retrieval_eligibility=?, valid_to=?, supersedes_claim_id=?, metadata_json=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    validation_state if validation_state is not None else existing.get("validation_state"),
                    retrieval_eligibility if retrieval_eligibility is not None else existing.get("retrieval_eligibility"),
                    valid_to if valid_to is not None else existing.get("valid_to"),
                    supersedes_claim_id if supersedes_claim_id is not None else existing.get("supersedes_claim_id"),
                    json.dumps(next_metadata, ensure_ascii=False),
                    self._now(),
                    office_id,
                    claim_id,
                ),
            )
            row = conn.execute("SELECT * FROM epistemic_claims WHERE office_id=? AND id=?", (office_id, claim_id)).fetchone()
            return self._decode_epistemic_claim(dict(row)) if row else None

    @staticmethod
    def _empty_user_profile(office_id: str) -> dict[str, Any]:
        return {
            "office_id": office_id,
            "display_name": "",
            "favorite_color": "",
            "food_preferences": "",
            "transport_preference": "",
            "weather_preference": "",
            "travel_preferences": "",
            "home_base": "",
            "current_location": "",
            "location_preferences": "",
            "maps_preference": "",
            "prayer_notifications_enabled": False,
            "prayer_habit_notes": "",
            "communication_style": "",
            "assistant_notes": "",
            "important_dates": [],
            "related_profiles": [],
            "contact_profile_overrides": [],
            "inbox_watch_rules": [],
            "inbox_keyword_rules": [],
            "inbox_block_rules": [],
            "source_preference_rules": [],
            "created_at": None,
            "updated_at": None,
        }

    @staticmethod
    def _decode_personal_model_session(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "module_keys_json", "module_keys")
        row = Persistence._decode_json_object_field(row, "state_json", "state")
        row = Persistence._decode_json_object_field(row, "progress_json", "progress")
        row = Persistence._decode_json_object_field(row, "summary_json", "summary")
        return row

    @staticmethod
    def _decode_personal_model_raw_entry(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "answer_value_json", "answer_value")
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["explicit"] = bool(row.get("explicit"))
        return row

    @staticmethod
    def _decode_personal_model_fact(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "value_json", "value_json")
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["sensitive"] = bool(row.get("sensitive"))
        row["enabled"] = bool(row.get("enabled"))
        row["never_use"] = bool(row.get("never_use"))
        return row

    @staticmethod
    def _decode_personal_model_suggestion(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "proposed_value_json", "proposed_value_json")
        row = Persistence._decode_json_object_field(row, "evidence_json", "evidence")
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["sensitive"] = bool(row.get("sensitive"))
        return row

    @staticmethod
    def _decode_epistemic_artifact(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "payload_json", "payload")
        row = Persistence._decode_json_object_field(row, "provenance_json", "provenance")
        row["sensitive"] = bool(row.get("sensitive"))
        row["immutable"] = bool(row.get("immutable"))
        return row

    @staticmethod
    def _decode_epistemic_claim(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "object_value_json", "object_value_json")
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["sensitive"] = bool(row.get("sensitive"))
        row["self_generated"] = bool(row.get("self_generated"))
        return row

    @staticmethod
    def _normalize_profile_text(value: Any) -> str:
        return (
            str(value or "")
            .lower()
            .replace("i̇", "i")
            .replace("\u0307", "")
            .replace("ı", "i")
            .replace("ğ", "g")
            .replace("ü", "u")
            .replace("ş", "s")
            .replace("ö", "o")
            .replace("ç", "c")
            .strip()
        )

    @staticmethod
    def _contains_profile_phrase(text: str, phrase: str) -> bool:
        normalized_text = Persistence._normalize_profile_text(text)
        normalized_phrase = Persistence._normalize_profile_text(phrase)
        if not normalized_text or not normalized_phrase:
            return False
        pattern = re.escape(normalized_phrase).replace(r"\ ", r"\s+")
        return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", normalized_text) is not None

    @staticmethod
    def _sanitize_related_profiles(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        sanitized: list[dict[str, Any]] = []
        for raw in list(items or []):
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            identifier = Persistence._normalize_profile_text(item.get("id"))
            name = Persistence._normalize_profile_text(item.get("name"))
            relationship = Persistence._normalize_profile_text(item.get("relationship"))
            source = Persistence._normalize_profile_text(item.get("source"))
            preferences = str(item.get("preferences") or "").strip()
            notes = str(item.get("notes") or "").strip()
            important_dates = [entry for entry in list(item.get("important_dates") or []) if isinstance(entry, dict)]

            suspicious = False
            for meta in Persistence._SUSPICIOUS_GENERIC_RELATED_PROFILES.values():
                if identifier not in meta["ids"] and name not in meta["names"] and relationship not in meta["relationships"]:
                    continue
                if source == "manual":
                    break
                if preferences or important_dates or not notes:
                    break
                if any(Persistence._contains_profile_phrase(notes, alias) for alias in meta["evidence_aliases"]):
                    break
                suspicious = True
                break

            if suspicious:
                continue

            item["important_dates"] = important_dates
            sanitized.append(item)
        return sanitized

    @staticmethod
    def _sanitize_contact_profile_overrides(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        sanitized: list[dict[str, Any]] = []
        seen_contact_ids: set[str] = set()
        for raw in list(items or []):
            if not isinstance(raw, dict):
                continue
            contact_id = str(raw.get("contact_id") or "").strip()[:255]
            description = str(raw.get("description") or "").strip()[:4000]
            if not contact_id or not description or contact_id in seen_contact_ids:
                continue
            updated_at = str(raw.get("updated_at") or "").strip()[:40] or None
            sanitized.append(
                {
                    "contact_id": contact_id,
                    "description": description,
                    "updated_at": updated_at,
                }
            )
            seen_contact_ids.add(contact_id)
        return sanitized

    @staticmethod
    def _decode_user_profile(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "important_dates_json", "important_dates")
        row = Persistence._decode_json_field(row, "related_profiles_json", "related_profiles")
        row = Persistence._decode_json_field(row, "contact_profile_overrides_json", "contact_profile_overrides")
        row = Persistence._decode_json_field(row, "inbox_watch_rules_json", "inbox_watch_rules")
        row = Persistence._decode_json_field(row, "inbox_keyword_rules_json", "inbox_keyword_rules")
        row = Persistence._decode_json_field(row, "inbox_block_rules_json", "inbox_block_rules")
        row = Persistence._decode_json_field(row, "source_preference_rules_json", "source_preference_rules")
        row["display_name"] = row.get("display_name") or ""
        row["favorite_color"] = row.get("favorite_color") or ""
        row["food_preferences"] = row.get("food_preferences") or ""
        row["transport_preference"] = row.get("transport_preference") or ""
        row["weather_preference"] = row.get("weather_preference") or ""
        row["travel_preferences"] = row.get("travel_preferences") or ""
        row["home_base"] = row.get("home_base") or ""
        row["current_location"] = row.get("current_location") or ""
        row["location_preferences"] = row.get("location_preferences") or ""
        row["maps_preference"] = row.get("maps_preference") or ""
        row["prayer_notifications_enabled"] = bool(row.get("prayer_notifications_enabled"))
        row["prayer_habit_notes"] = row.get("prayer_habit_notes") or ""
        row["communication_style"] = row.get("communication_style") or ""
        row["assistant_notes"] = row.get("assistant_notes") or ""
        row["related_profiles"] = Persistence._sanitize_related_profiles(row.get("related_profiles") or [])
        row["contact_profile_overrides"] = Persistence._sanitize_contact_profile_overrides(row.get("contact_profile_overrides") or [])
        row["inbox_watch_rules"] = row.get("inbox_watch_rules") or []
        row["inbox_keyword_rules"] = row.get("inbox_keyword_rules") or []
        row["inbox_block_rules"] = row.get("inbox_block_rules") or []
        row["source_preference_rules"] = row.get("source_preference_rules") or []
        return row

    @staticmethod
    def _empty_assistant_runtime_profile(office_id: str) -> dict[str, Any]:
        return {
            "office_id": office_id,
            "assistant_name": "",
            "role_summary": DEFAULT_ASSISTANT_ROLE_SUMMARY,
            "tone": DEFAULT_ASSISTANT_TONE,
            "avatar_path": "",
            "soul_notes": "",
            "tools_notes": "",
            "assistant_forms": [],
            "behavior_contract": {},
            "evolution_history": [],
            "heartbeat_extra_checks": [],
            "created_at": None,
            "updated_at": None,
        }

    @staticmethod
    def _decode_assistant_runtime_profile(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "assistant_forms_json", "assistant_forms")
        row = Persistence._decode_json_object_field(row, "behavior_contract_json", "behavior_contract")
        row = Persistence._decode_json_field(row, "evolution_history_json", "evolution_history")
        row = Persistence._decode_json_field(row, "heartbeat_extra_checks_json", "heartbeat_extra_checks")
        row["assistant_name"] = row.get("assistant_name") or ""
        row["role_summary"] = row.get("role_summary") or DEFAULT_ASSISTANT_ROLE_SUMMARY
        if row["role_summary"] == "Kaynak dayanaklı hukuk çalışma asistanı":
            row["role_summary"] = DEFAULT_ASSISTANT_ROLE_SUMMARY
        row["tone"] = row.get("tone") or DEFAULT_ASSISTANT_TONE
        row["avatar_path"] = row.get("avatar_path") or ""
        row["soul_notes"] = row.get("soul_notes") or ""
        row["tools_notes"] = row.get("tools_notes") or ""
        row["assistant_forms"] = row.get("assistant_forms") or []
        row["behavior_contract"] = row.get("behavior_contract") or {}
        row["evolution_history"] = row.get("evolution_history") or []
        return row

    def upsert_email_thread(
        self,
        office_id: str,
        *,
        provider: str,
        thread_ref: str,
        subject: str,
        participants: list[str] | None = None,
        snippet: str | None = None,
        received_at: str | None = None,
        unread_count: int = 0,
        reply_needed: bool = False,
        matter_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            metadata_payload = self._merge_channel_metadata(
                self._load_existing_channel_metadata(
                    conn,
                    table="email_threads",
                    office_id=office_id,
                    lookup={"provider": provider, "thread_ref": thread_ref},
                ),
                metadata,
            )
            conn.execute(
                """
                INSERT INTO email_threads (
                    office_id, provider, thread_ref, subject, participants_json, snippet,
                    received_at, unread_count, reply_needed, matter_id, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, thread_ref) DO UPDATE SET
                    subject=excluded.subject,
                    participants_json=excluded.participants_json,
                    snippet=excluded.snippet,
                    received_at=excluded.received_at,
                    unread_count=excluded.unread_count,
                    reply_needed=excluded.reply_needed,
                    matter_id=excluded.matter_id,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    thread_ref,
                    subject,
                    json.dumps(participants or [], ensure_ascii=False),
                    snippet,
                    received_at,
                    unread_count,
                    1 if reply_needed else 0,
                    matter_id,
                    json.dumps(metadata_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM email_threads WHERE office_id=? AND provider=? AND thread_ref=?",
                (office_id, provider, thread_ref),
            ).fetchone()
            return self._decode_email_thread(dict(row)) if row else {}

    def list_email_threads(
        self,
        office_id: str,
        *,
        reply_needed_only: bool = False,
        provider: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM email_threads WHERE office_id=?"
            params: list[Any] = [office_id]
            if reply_needed_only:
                query += " AND reply_needed=1"
            if provider:
                query += " AND provider=?"
                params.append(provider)
            query += " ORDER BY COALESCE(received_at, updated_at) DESC, id DESC"
            if limit is not None and limit > 0:
                query += " LIMIT ?"
                params.append(max(1, min(limit, 500)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_email_thread(dict(row)) for row in rows]

    @staticmethod
    def _decode_email_thread(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "participants_json", "participants")
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["reply_needed"] = bool(row.get("reply_needed"))
        return Persistence._apply_channel_memory_state(row)

    def upsert_calendar_event(
        self,
        office_id: str,
        *,
        provider: str,
        external_id: str,
        title: str,
        starts_at: str,
        ends_at: str | None = None,
        attendees: list[str] | None = None,
        location: str | None = None,
        matter_id: int | None = None,
        status: str = "confirmed",
        needs_preparation: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            conn.execute(
                """
                INSERT INTO calendar_events (
                    office_id, provider, external_id, title, starts_at, ends_at, attendees_json, location,
                    matter_id, status, needs_preparation, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, external_id) DO UPDATE SET
                    title=excluded.title,
                    starts_at=excluded.starts_at,
                    ends_at=excluded.ends_at,
                    attendees_json=excluded.attendees_json,
                    location=excluded.location,
                    matter_id=excluded.matter_id,
                    status=excluded.status,
                    needs_preparation=excluded.needs_preparation,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    external_id,
                    title,
                    starts_at,
                    ends_at,
                    json.dumps(attendees or [], ensure_ascii=False),
                    location,
                    matter_id,
                    status,
                    1 if needs_preparation else 0,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM calendar_events WHERE office_id=? AND provider=? AND external_id=?",
                (office_id, provider, external_id),
            ).fetchone()
            return self._decode_calendar_event(dict(row)) if row else {}

    def list_calendar_events(self, office_id: str, *, limit: int = 20, provider: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM calendar_events WHERE office_id=?"
            params: list[Any] = [office_id]
            if provider:
                query += " AND provider=?"
                params.append(provider)
            query += " ORDER BY starts_at ASC, id DESC LIMIT ?"
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_calendar_event(dict(row)) for row in rows]

    @staticmethod
    def _decode_calendar_event(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "attendees_json", "attendees")
        row = Persistence._decode_json_field(row, "metadata_json", "metadata")
        row["needs_preparation"] = bool(row.get("needs_preparation"))
        return row

    def upsert_drive_file(
        self,
        office_id: str,
        *,
        provider: str,
        external_id: str,
        name: str,
        mime_type: str | None = None,
        web_view_link: str | None = None,
        modified_at: str | None = None,
        matter_id: int | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            conn.execute(
                """
                INSERT INTO google_drive_files (
                    office_id, provider, external_id, name, mime_type, web_view_link,
                    modified_at, matter_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, external_id) DO UPDATE SET
                    name=excluded.name,
                    mime_type=excluded.mime_type,
                    web_view_link=excluded.web_view_link,
                    modified_at=excluded.modified_at,
                    matter_id=excluded.matter_id,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    external_id,
                    name,
                    mime_type,
                    web_view_link,
                    modified_at,
                    matter_id,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM google_drive_files WHERE office_id=? AND provider=? AND external_id=?",
                (office_id, provider, external_id),
            ).fetchone()
            return dict(row) if row else {}

    def list_drive_files(self, office_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM google_drive_files WHERE office_id=? ORDER BY modified_at DESC, id DESC LIMIT ?",
                (office_id, max(1, min(limit, 200))),
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_whatsapp_message(
        self,
        office_id: str,
        *,
        provider: str,
        conversation_ref: str,
        message_ref: str,
        body: str,
        sender: str | None = None,
        recipient: str | None = None,
        direction: str = "inbound",
        sent_at: str | None = None,
        reply_needed: bool = False,
        matter_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            metadata_payload = self._merge_channel_metadata(
                self._load_existing_channel_metadata(
                    conn,
                    table="whatsapp_messages",
                    office_id=office_id,
                    lookup={"provider": provider, "message_ref": message_ref},
                ),
                metadata,
            )
            conn.execute(
                """
                INSERT INTO whatsapp_messages (
                    office_id, provider, conversation_ref, message_ref, sender, recipient, body, direction,
                    sent_at, reply_needed, matter_id, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, message_ref) DO UPDATE SET
                    conversation_ref=excluded.conversation_ref,
                    sender=excluded.sender,
                    recipient=excluded.recipient,
                    body=excluded.body,
                    direction=excluded.direction,
                    sent_at=excluded.sent_at,
                    reply_needed=excluded.reply_needed,
                    matter_id=excluded.matter_id,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    conversation_ref,
                    message_ref,
                    sender,
                    recipient,
                    body,
                    direction,
                    sent_at,
                    1 if reply_needed else 0,
                    matter_id,
                    json.dumps(metadata_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM whatsapp_messages WHERE office_id=? AND provider=? AND message_ref=?",
                (office_id, provider, message_ref),
            ).fetchone()
            return self._decode_whatsapp_message(dict(row)) if row else {}

    def upsert_whatsapp_contact_snapshot(
        self,
        office_id: str,
        *,
        provider: str,
        conversation_ref: str,
        display_name: str,
        profile_name: str | None = None,
        phone_number: str | None = None,
        is_group: bool = False,
        group_name: str | None = None,
        last_seen_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            metadata_payload = self._merge_channel_metadata(
                self._load_existing_channel_metadata(
                    conn,
                    table="whatsapp_contact_snapshots",
                    office_id=office_id,
                    lookup={"provider": provider, "conversation_ref": conversation_ref},
                ),
                metadata,
            )
            conn.execute(
                """
                INSERT INTO whatsapp_contact_snapshots (
                    office_id, provider, conversation_ref, display_name, profile_name, phone_number, is_group,
                    group_name, last_seen_at, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, conversation_ref) DO UPDATE SET
                    display_name=excluded.display_name,
                    profile_name=excluded.profile_name,
                    phone_number=excluded.phone_number,
                    is_group=excluded.is_group,
                    group_name=excluded.group_name,
                    last_seen_at=excluded.last_seen_at,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    conversation_ref,
                    display_name,
                    profile_name,
                    phone_number,
                    1 if is_group else 0,
                    group_name,
                    last_seen_at,
                    json.dumps(metadata_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM whatsapp_contact_snapshots WHERE office_id=? AND provider=? AND conversation_ref=?",
                (office_id, provider, conversation_ref),
            ).fetchone()
            return self._decode_whatsapp_contact_snapshot(dict(row)) if row else {}

    def list_whatsapp_messages(self, office_id: str, *, reply_needed_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM whatsapp_messages WHERE office_id=?"
            params: list[Any] = [office_id]
            if reply_needed_only:
                query += " AND reply_needed=1"
            query += " ORDER BY COALESCE(sent_at, updated_at) DESC, id DESC LIMIT ?"
            params.append(max(1, min(limit, 5000)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_whatsapp_message(dict(row)) for row in rows]

    def list_whatsapp_contact_snapshots(self, office_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM whatsapp_contact_snapshots WHERE office_id=? ORDER BY COALESCE(last_seen_at, updated_at) DESC, id DESC LIMIT ?",
                (office_id, max(1, min(limit, 1000))),
            ).fetchall()
            return [self._decode_whatsapp_contact_snapshot(dict(row)) for row in rows]

    @staticmethod
    def _decode_whatsapp_message(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["reply_needed"] = bool(row.get("reply_needed"))
        return Persistence._apply_channel_memory_state(row)

    @staticmethod
    def _decode_whatsapp_contact_snapshot(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["is_group"] = bool(row.get("is_group"))
        return row

    def upsert_telegram_message(
        self,
        office_id: str,
        *,
        provider: str,
        conversation_ref: str,
        message_ref: str,
        body: str,
        sender: str | None = None,
        recipient: str | None = None,
        direction: str = "inbound",
        sent_at: str | None = None,
        reply_needed: bool = False,
        matter_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            metadata_payload = self._merge_channel_metadata(
                self._load_existing_channel_metadata(
                    conn,
                    table="telegram_messages",
                    office_id=office_id,
                    lookup={"provider": provider, "message_ref": message_ref},
                ),
                metadata,
            )
            conn.execute(
                """
                INSERT INTO telegram_messages (
                    office_id, provider, conversation_ref, message_ref, sender, recipient, body, direction,
                    sent_at, reply_needed, matter_id, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, message_ref) DO UPDATE SET
                    conversation_ref=excluded.conversation_ref,
                    sender=excluded.sender,
                    recipient=excluded.recipient,
                    body=excluded.body,
                    direction=excluded.direction,
                    sent_at=excluded.sent_at,
                    reply_needed=excluded.reply_needed,
                    matter_id=excluded.matter_id,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    conversation_ref,
                    message_ref,
                    sender,
                    recipient,
                    body,
                    direction,
                    sent_at,
                    1 if reply_needed else 0,
                    matter_id,
                    json.dumps(metadata_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM telegram_messages WHERE office_id=? AND provider=? AND message_ref=?",
                (office_id, provider, message_ref),
            ).fetchone()
            return self._decode_telegram_message(dict(row)) if row else {}

    def list_telegram_messages(self, office_id: str, *, reply_needed_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM telegram_messages WHERE office_id=?"
            params: list[Any] = [office_id]
            if reply_needed_only:
                query += " AND reply_needed=1"
            query += " ORDER BY COALESCE(sent_at, updated_at) DESC, id DESC LIMIT ?"
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_telegram_message(dict(row)) for row in rows]

    def clear_telegram_messages(self, office_id: str, *, provider: str | None = None) -> int:
        with self._conn() as conn:
            if provider:
                cursor = conn.execute(
                    "DELETE FROM telegram_messages WHERE office_id=? AND provider=?",
                    (office_id, provider),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM telegram_messages WHERE office_id=?",
                    (office_id,),
                )
            return int(cursor.rowcount or 0)

    @staticmethod
    def _decode_telegram_message(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["reply_needed"] = bool(row.get("reply_needed"))
        return Persistence._apply_channel_memory_state(row)

    def upsert_x_post(
        self,
        office_id: str,
        *,
        provider: str,
        external_id: str,
        post_type: str,
        content: str,
        author_handle: str | None = None,
        posted_at: str | None = None,
        reply_needed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            metadata_payload = self._merge_channel_metadata(
                self._load_existing_channel_metadata(
                    conn,
                    table="x_posts",
                    office_id=office_id,
                    lookup={"provider": provider, "external_id": external_id},
                ),
                metadata,
            )
            conn.execute(
                """
                INSERT INTO x_posts (
                    office_id, provider, external_id, post_type, author_handle, content, posted_at,
                    reply_needed, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, external_id) DO UPDATE SET
                    post_type=excluded.post_type,
                    author_handle=excluded.author_handle,
                    content=excluded.content,
                    posted_at=excluded.posted_at,
                    reply_needed=excluded.reply_needed,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    external_id,
                    post_type,
                    author_handle,
                    content,
                    posted_at,
                    1 if reply_needed else 0,
                    json.dumps(metadata_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM x_posts WHERE office_id=? AND provider=? AND external_id=?",
                (office_id, provider, external_id),
            ).fetchone()
            return self._decode_x_post(dict(row)) if row else {}

    def list_x_posts(self, office_id: str, *, post_type: str | None = None, reply_needed_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM x_posts WHERE office_id=?"
            params: list[Any] = [office_id]
            if post_type:
                query += " AND post_type=?"
                params.append(post_type)
            if reply_needed_only:
                query += " AND reply_needed=1"
            query += " ORDER BY COALESCE(posted_at, updated_at) DESC, id DESC LIMIT ?"
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_x_post(dict(row)) for row in rows]

    @staticmethod
    def _decode_x_post(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["reply_needed"] = bool(row.get("reply_needed"))
        return Persistence._apply_channel_memory_state(row)

    def upsert_x_message(
        self,
        office_id: str,
        *,
        provider: str,
        conversation_ref: str,
        message_ref: str,
        body: str,
        sender: str | None = None,
        recipient: str | None = None,
        direction: str = "inbound",
        sent_at: str | None = None,
        reply_needed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            metadata_payload = self._merge_channel_metadata(
                self._load_existing_channel_metadata(
                    conn,
                    table="x_messages",
                    office_id=office_id,
                    lookup={"provider": provider, "message_ref": message_ref},
                ),
                metadata,
            )
            conn.execute(
                """
                INSERT INTO x_messages (
                    office_id, provider, conversation_ref, message_ref, sender, recipient, body, direction,
                    sent_at, reply_needed, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, message_ref) DO UPDATE SET
                    conversation_ref=excluded.conversation_ref,
                    sender=excluded.sender,
                    recipient=excluded.recipient,
                    body=excluded.body,
                    direction=excluded.direction,
                    sent_at=excluded.sent_at,
                    reply_needed=excluded.reply_needed,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    conversation_ref,
                    message_ref,
                    sender,
                    recipient,
                    body,
                    direction,
                    sent_at,
                    1 if reply_needed else 0,
                    json.dumps(metadata_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM x_messages WHERE office_id=? AND provider=? AND message_ref=?",
                (office_id, provider, message_ref),
            ).fetchone()
            return self._decode_x_message(dict(row)) if row else {}

    def list_x_messages(self, office_id: str, *, reply_needed_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM x_messages WHERE office_id=?"
            params: list[Any] = [office_id]
            if reply_needed_only:
                query += " AND reply_needed=1"
            query += " ORDER BY COALESCE(sent_at, updated_at) DESC, id DESC LIMIT ?"
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_x_message(dict(row)) for row in rows]

    @staticmethod
    def _decode_x_message(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["reply_needed"] = bool(row.get("reply_needed"))
        return Persistence._apply_channel_memory_state(row)

    def upsert_instagram_message(
        self,
        office_id: str,
        *,
        provider: str,
        conversation_ref: str,
        message_ref: str,
        body: str,
        sender: str | None = None,
        recipient: str | None = None,
        direction: str = "inbound",
        sent_at: str | None = None,
        reply_needed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            metadata_payload = self._merge_channel_metadata(
                self._load_existing_channel_metadata(
                    conn,
                    table="instagram_messages",
                    office_id=office_id,
                    lookup={"provider": provider, "message_ref": message_ref},
                ),
                metadata,
            )
            conn.execute(
                """
                INSERT INTO instagram_messages (
                    office_id, provider, conversation_ref, message_ref, sender, recipient, body, direction,
                    sent_at, reply_needed, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, message_ref) DO UPDATE SET
                    conversation_ref=excluded.conversation_ref,
                    sender=excluded.sender,
                    recipient=excluded.recipient,
                    body=excluded.body,
                    direction=excluded.direction,
                    sent_at=excluded.sent_at,
                    reply_needed=excluded.reply_needed,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    conversation_ref,
                    message_ref,
                    sender,
                    recipient,
                    body,
                    direction,
                    sent_at,
                    1 if reply_needed else 0,
                    json.dumps(metadata_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM instagram_messages WHERE office_id=? AND provider=? AND message_ref=?",
                (office_id, provider, message_ref),
            ).fetchone()
            return self._decode_instagram_message(dict(row)) if row else {}

    def list_instagram_messages(self, office_id: str, *, reply_needed_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM instagram_messages WHERE office_id=?"
            params: list[Any] = [office_id]
            if reply_needed_only:
                query += " AND reply_needed=1"
            query += " ORDER BY COALESCE(sent_at, updated_at) DESC, id DESC LIMIT ?"
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_instagram_message(dict(row)) for row in rows]

    @staticmethod
    def _decode_instagram_message(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["reply_needed"] = bool(row.get("reply_needed"))
        return Persistence._apply_channel_memory_state(row)

    def upsert_linkedin_post(
        self,
        office_id: str,
        *,
        provider: str,
        external_id: str,
        content: str,
        author_handle: str | None = None,
        posted_at: str | None = None,
        reply_needed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            metadata_payload = self._merge_channel_metadata(
                self._load_existing_channel_metadata(
                    conn,
                    table="linkedin_posts",
                    office_id=office_id,
                    lookup={"provider": provider, "external_id": external_id},
                ),
                metadata,
            )
            conn.execute(
                """
                INSERT INTO linkedin_posts (
                    office_id, provider, external_id, author_handle, content, posted_at,
                    reply_needed, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, external_id) DO UPDATE SET
                    author_handle=excluded.author_handle,
                    content=excluded.content,
                    posted_at=excluded.posted_at,
                    reply_needed=excluded.reply_needed,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    external_id,
                    author_handle,
                    content,
                    posted_at,
                    1 if reply_needed else 0,
                    json.dumps(metadata_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM linkedin_posts WHERE office_id=? AND provider=? AND external_id=?",
                (office_id, provider, external_id),
            ).fetchone()
            return self._decode_linkedin_post(dict(row)) if row else {}

    def list_linkedin_posts(
        self,
        office_id: str,
        *,
        reply_needed_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM linkedin_posts WHERE office_id=?"
            params: list[Any] = [office_id]
            if reply_needed_only:
                query += " AND reply_needed=1"
            query += " ORDER BY COALESCE(posted_at, updated_at) DESC, id DESC LIMIT ?"
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_linkedin_post(dict(row)) for row in rows]

    @staticmethod
    def _decode_linkedin_post(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["reply_needed"] = bool(row.get("reply_needed"))
        return Persistence._apply_channel_memory_state(row)

    def upsert_linkedin_comment(
        self,
        office_id: str,
        *,
        provider: str,
        external_id: str,
        content: str,
        object_urn: str | None = None,
        parent_external_id: str | None = None,
        author_handle: str | None = None,
        posted_at: str | None = None,
        reply_needed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            metadata_payload = self._merge_channel_metadata(
                self._load_existing_channel_metadata(
                    conn,
                    table="linkedin_comments",
                    office_id=office_id,
                    lookup={"provider": provider, "external_id": external_id},
                ),
                metadata,
            )
            conn.execute(
                """
                INSERT INTO linkedin_comments (
                    office_id, provider, external_id, object_urn, parent_external_id, author_handle,
                    content, posted_at, reply_needed, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, external_id) DO UPDATE SET
                    object_urn=excluded.object_urn,
                    parent_external_id=excluded.parent_external_id,
                    author_handle=excluded.author_handle,
                    content=excluded.content,
                    posted_at=excluded.posted_at,
                    reply_needed=excluded.reply_needed,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    external_id,
                    object_urn,
                    parent_external_id,
                    author_handle,
                    content,
                    posted_at,
                    1 if reply_needed else 0,
                    json.dumps(metadata_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM linkedin_comments WHERE office_id=? AND provider=? AND external_id=?",
                (office_id, provider, external_id),
            ).fetchone()
            return self._decode_linkedin_comment(dict(row)) if row else {}

    def list_linkedin_comments(
        self,
        office_id: str,
        *,
        reply_needed_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM linkedin_comments WHERE office_id=?"
            params: list[Any] = [office_id]
            if reply_needed_only:
                query += " AND reply_needed=1"
            query += " ORDER BY COALESCE(posted_at, updated_at) DESC, id DESC LIMIT ?"
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_linkedin_comment(dict(row)) for row in rows]

    @staticmethod
    def _decode_linkedin_comment(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["reply_needed"] = bool(row.get("reply_needed"))
        return Persistence._apply_channel_memory_state(row)

    def upsert_linkedin_message(
        self,
        office_id: str,
        *,
        provider: str,
        conversation_ref: str,
        message_ref: str,
        body: str,
        sender: str | None = None,
        recipient: str | None = None,
        direction: str = "inbound",
        sent_at: str | None = None,
        reply_needed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            metadata_payload = self._merge_channel_metadata(
                self._load_existing_channel_metadata(
                    conn,
                    table="linkedin_messages",
                    office_id=office_id,
                    lookup={"provider": provider, "message_ref": message_ref},
                ),
                metadata,
            )
            conn.execute(
                """
                INSERT INTO linkedin_messages (
                    office_id, provider, conversation_ref, message_ref, sender, recipient, body, direction,
                    sent_at, reply_needed, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(office_id, provider, message_ref) DO UPDATE SET
                    conversation_ref=excluded.conversation_ref,
                    sender=excluded.sender,
                    recipient=excluded.recipient,
                    body=excluded.body,
                    direction=excluded.direction,
                    sent_at=excluded.sent_at,
                    reply_needed=excluded.reply_needed,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    provider,
                    conversation_ref,
                    message_ref,
                    sender,
                    recipient,
                    body,
                    direction,
                    sent_at,
                    1 if reply_needed else 0,
                    json.dumps(metadata_payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM linkedin_messages WHERE office_id=? AND provider=? AND message_ref=?",
                (office_id, provider, message_ref),
            ).fetchone()
            return self._decode_linkedin_message(dict(row)) if row else {}

    def list_linkedin_messages(
        self,
        office_id: str,
        *,
        reply_needed_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM linkedin_messages WHERE office_id=?"
            params: list[Any] = [office_id]
            if reply_needed_only:
                query += " AND reply_needed=1"
            query += " ORDER BY COALESCE(sent_at, updated_at) DESC, id DESC LIMIT ?"
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_linkedin_message(dict(row)) for row in rows]

    @staticmethod
    def _decode_linkedin_message(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["reply_needed"] = bool(row.get("reply_needed"))
        return Persistence._apply_channel_memory_state(row)

    def set_channel_memory_state(
        self,
        office_id: str,
        *,
        channel_type: str,
        record_id: int,
        memory_state: str,
    ) -> dict[str, Any] | None:
        state = self._normalize_channel_memory_state(memory_state)
        table_map: dict[str, tuple[str, Any]] = {
            "email_thread": ("email_threads", self._decode_email_thread),
            "whatsapp_message": ("whatsapp_messages", self._decode_whatsapp_message),
            "telegram_message": ("telegram_messages", self._decode_telegram_message),
            "x_post": ("x_posts", self._decode_x_post),
            "x_message": ("x_messages", self._decode_x_message),
            "instagram_message": ("instagram_messages", self._decode_instagram_message),
            "linkedin_post": ("linkedin_posts", self._decode_linkedin_post),
            "linkedin_comment": ("linkedin_comments", self._decode_linkedin_comment),
            "linkedin_message": ("linkedin_messages", self._decode_linkedin_message),
        }
        target = table_map.get(str(channel_type or "").strip())
        if target is None:
            return None
        table_name, decoder = target
        now = self._now()
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {table_name} WHERE office_id=? AND id=?",
                (office_id, int(record_id)),
            ).fetchone()
            if row is None:
                return None
            payload = decoder(dict(row))
            metadata = self._merge_channel_metadata(payload.get("metadata"), {"memory_state": state})
            conn.execute(
                f"UPDATE {table_name} SET metadata_json=?, updated_at=? WHERE office_id=? AND id=?",
                (
                    json.dumps(metadata, ensure_ascii=False),
                    now,
                    office_id,
                    int(record_id),
                ),
            )
            updated = conn.execute(
                f"SELECT * FROM {table_name} WHERE office_id=? AND id=?",
                (office_id, int(record_id)),
            ).fetchone()
            return decoder(dict(updated)) if updated else None

    def create_outbound_draft(
        self,
        office_id: str,
        *,
        draft_type: str,
        channel: str,
        body: str,
        created_by: str,
        matter_id: int | None = None,
        to_contact: str | None = None,
        subject: str | None = None,
        source_context: dict[str, Any] | None = None,
        generated_from: str | None = None,
        ai_model: str | None = None,
        ai_provider: str | None = None,
        approval_status: str = "pending_review",
        delivery_status: str = "not_sent",
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            if matter_id is not None and not self._get_matter_row(conn, matter_id, office_id):
                raise ValueError("Dosya bulunamadı.")
            cur = conn.execute(
                """
                INSERT INTO outbound_drafts (
                    office_id, matter_id, draft_type, channel, to_contact, subject, body, source_context_json,
                    generated_from, ai_model, ai_provider, approval_status, delivery_status, created_by,
                    approved_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    office_id,
                    matter_id,
                    draft_type,
                    channel,
                    to_contact,
                    subject,
                    body,
                    json.dumps(source_context or {}, ensure_ascii=False),
                    generated_from,
                    ai_model,
                    ai_provider,
                    approval_status,
                    delivery_status,
                    created_by,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM outbound_drafts WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_outbound_draft(dict(row)) if row else {}

    def list_outbound_drafts(self, office_id: str, *, matter_id: int | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = "SELECT * FROM outbound_drafts WHERE office_id=?"
            params: list[Any] = [office_id]
            if matter_id is not None:
                query += " AND matter_id=?"
                params.append(matter_id)
            query += " ORDER BY updated_at DESC, id DESC"
            rows = conn.execute(query, params).fetchall()
            return [self._decode_outbound_draft(dict(row)) for row in rows]

    def get_outbound_draft(self, office_id: str, draft_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM outbound_drafts WHERE office_id=? AND id=?",
                (office_id, draft_id),
            ).fetchone()
            return self._decode_outbound_draft(dict(row)) if row else None

    def update_outbound_draft(
        self,
        office_id: str,
        draft_id: int,
        *,
        approval_status: str | None = None,
        delivery_status: str | None = None,
        approved_by: str | None = None,
        dispatch_state: str | None = None,
        dispatch_error: str | None = None,
        external_message_id: str | None = None,
        last_dispatch_at: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM outbound_drafts WHERE office_id=? AND id=?",
                (office_id, draft_id),
            ).fetchone()
            if not row:
                return None
            current = dict(row)
            conn.execute(
                """
                UPDATE outbound_drafts
                SET approval_status=?, delivery_status=?, approved_by=?, dispatch_state=?, dispatch_error=?, external_message_id=?, last_dispatch_at=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    approval_status or current["approval_status"],
                    delivery_status or current["delivery_status"],
                    approved_by if approved_by is not None else current.get("approved_by"),
                    dispatch_state if dispatch_state is not None else current.get("dispatch_state"),
                    dispatch_error if dispatch_error is not None else current.get("dispatch_error"),
                    external_message_id if external_message_id is not None else current.get("external_message_id"),
                    last_dispatch_at if last_dispatch_at is not None else current.get("last_dispatch_at"),
                    self._now(),
                    office_id,
                    draft_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM outbound_drafts WHERE office_id=? AND id=?",
                (office_id, draft_id),
            ).fetchone()
            return self._decode_outbound_draft(dict(updated)) if updated else None

    @staticmethod
    def _decode_outbound_draft(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "source_context_json", "source_context")
        row["dispatch_state"] = row.get("dispatch_state") or "idle"
        row["dispatch_error"] = row.get("dispatch_error") or None
        row["external_message_id"] = row.get("external_message_id") or None
        return row

    def create_assistant_action(
        self,
        office_id: str,
        *,
        action_type: str,
        title: str,
        created_by: str,
        matter_id: int | None = None,
        description: str | None = None,
        rationale: str | None = None,
        source_refs: list[dict[str, Any]] | None = None,
        target_channel: str | None = None,
        draft_id: int | None = None,
        status: str = "suggested",
        manual_review_required: bool = True,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO assistant_actions (
                    office_id, matter_id, action_type, title, description, rationale, source_refs_json,
                    target_channel, draft_id, status, manual_review_required, created_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    matter_id,
                    action_type,
                    title,
                    description,
                    rationale,
                    json.dumps(source_refs or [], ensure_ascii=False),
                    target_channel,
                    draft_id,
                    status,
                    1 if manual_review_required else 0,
                    created_by,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM assistant_actions WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_assistant_action(dict(row)) if row else {}

    def list_assistant_actions(
        self,
        office_id: str,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = """
                SELECT a.*, d.subject AS draft_subject, d.to_contact AS draft_to_contact
                FROM assistant_actions a
                LEFT JOIN outbound_drafts d ON d.id = a.draft_id
                WHERE a.office_id=?
            """
            params: list[Any] = [office_id]
            if status:
                query += " AND a.status=?"
                params.append(status)
            query += " ORDER BY a.updated_at DESC, a.id DESC LIMIT ?"
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(query, params).fetchall()
            return [self._decode_assistant_action(dict(row)) for row in rows]

    def get_assistant_action(self, office_id: str, action_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM assistant_actions WHERE office_id=? AND id=?",
                (office_id, action_id),
            ).fetchone()
            return self._decode_assistant_action(dict(row)) if row else None

    def get_assistant_action_by_draft_id(self, office_id: str, draft_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM assistant_actions
                WHERE office_id=? AND draft_id=?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (office_id, draft_id),
            ).fetchone()
            return self._decode_assistant_action(dict(row)) if row else None

    def update_assistant_action_status(
        self,
        office_id: str,
        action_id: int,
        status: str,
        *,
        draft_id: int | None = None,
        dispatch_state: str | None = None,
        dispatch_error: str | None = None,
        external_message_id: str | None = None,
        last_dispatch_at: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            current = conn.execute(
                "SELECT * FROM assistant_actions WHERE office_id=? AND id=?",
                (office_id, action_id),
            ).fetchone()
            if not current:
                return None
            conn.execute(
                """
                UPDATE assistant_actions
                SET status=?, draft_id=?, dispatch_state=?, dispatch_error=?, external_message_id=?, last_dispatch_at=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    status,
                    draft_id if draft_id is not None else current["draft_id"],
                    dispatch_state if dispatch_state is not None else current["dispatch_state"],
                    dispatch_error if dispatch_error is not None else current["dispatch_error"],
                    external_message_id if external_message_id is not None else current["external_message_id"],
                    last_dispatch_at if last_dispatch_at is not None else current["last_dispatch_at"],
                    self._now(),
                    office_id,
                    action_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM assistant_actions WHERE office_id=? AND id=?",
                (office_id, action_id),
            ).fetchone()
            return self._decode_assistant_action(dict(row)) if row else None

    @staticmethod
    def _decode_assistant_action(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "source_refs_json", "source_refs")
        row["manual_review_required"] = bool(row.get("manual_review_required"))
        row["dispatch_state"] = row.get("dispatch_state") or "idle"
        row["dispatch_error"] = row.get("dispatch_error") or None
        row["external_message_id"] = row.get("external_message_id") or None
        return row

    def create_action_case(
        self,
        office_id: str,
        *,
        case_type: str,
        title: str,
        created_by: str,
        status: str,
        current_step: str,
        approval_required: bool = True,
        action_id: int | None = None,
        draft_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        last_actor: str | None = None,
        last_error: str | None = None,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            cur = conn.execute(
                """
                INSERT INTO action_cases (
                    office_id, case_type, title, status, current_step, action_id, draft_id, approval_required,
                    created_by, last_actor, metadata_json, last_error, completed_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    case_type,
                    title,
                    status,
                    current_step,
                    action_id,
                    draft_id,
                    1 if approval_required else 0,
                    created_by,
                    last_actor,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    last_error,
                    completed_at,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM action_cases WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_action_case(dict(row)) if row else {}

    def get_action_case(self, office_id: str, case_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM action_cases WHERE office_id=? AND id=?",
                (office_id, case_id),
            ).fetchone()
            return self._decode_action_case(dict(row)) if row else None

    def get_action_case_by_action_id(self, office_id: str, action_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM action_cases
                WHERE office_id=? AND action_id=?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (office_id, action_id),
            ).fetchone()
            return self._decode_action_case(dict(row)) if row else None

    def get_action_case_by_draft_id(self, office_id: str, draft_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM action_cases
                WHERE office_id=? AND draft_id=?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (office_id, draft_id),
            ).fetchone()
            return self._decode_action_case(dict(row)) if row else None

    def update_action_case(
        self,
        office_id: str,
        case_id: int,
        *,
        status: str | None = None,
        current_step: str | None = None,
        action_id: int | None | object = _UNSET,
        draft_id: int | None | object = _UNSET,
        approval_required: bool | None = None,
        last_actor: str | None | object = _UNSET,
        metadata: dict[str, Any] | None = None,
        last_error: str | None | object = _UNSET,
        completed_at: str | None | object = _UNSET,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            current = conn.execute(
                "SELECT * FROM action_cases WHERE office_id=? AND id=?",
                (office_id, case_id),
            ).fetchone()
            if not current:
                return None
            current_dict = dict(current)
            next_metadata = dict(json.loads(current_dict.get("metadata_json") or "{}"))
            if metadata:
                next_metadata.update(metadata)
            conn.execute(
                """
                UPDATE action_cases
                SET status=?, current_step=?, action_id=?, draft_id=?, approval_required=?, last_actor=?,
                    metadata_json=?, last_error=?, completed_at=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    status or current_dict["status"],
                    current_step or current_dict["current_step"],
                    current_dict["action_id"] if action_id is self._UNSET else action_id,
                    current_dict["draft_id"] if draft_id is self._UNSET else draft_id,
                    1 if (approval_required if approval_required is not None else bool(current_dict.get("approval_required"))) else 0,
                    current_dict.get("last_actor") if last_actor is self._UNSET else last_actor,
                    json.dumps(next_metadata, ensure_ascii=False),
                    current_dict.get("last_error") if last_error is self._UNSET else last_error,
                    current_dict.get("completed_at") if completed_at is self._UNSET else completed_at,
                    self._now(),
                    office_id,
                    case_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM action_cases WHERE office_id=? AND id=?",
                (office_id, case_id),
            ).fetchone()
            return self._decode_action_case(dict(updated)) if updated else None

    def add_action_case_event(
        self,
        office_id: str,
        *,
        case_id: int,
        step_key: str,
        event_type: str,
        actor: str,
        note: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO action_case_events (office_id, case_id, step_key, event_type, actor, note, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    case_id,
                    step_key,
                    event_type,
                    actor,
                    note,
                    json.dumps(payload or {}, ensure_ascii=False),
                    self._now(),
                ),
            )
            row = conn.execute("SELECT * FROM action_case_events WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_action_case_event(dict(row)) if row else {}

    def list_action_case_events(self, office_id: str, case_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM action_case_events
                WHERE office_id=? AND case_id=?
                ORDER BY created_at DESC, id DESC
                """,
                (office_id, case_id),
            ).fetchall()
            return [self._decode_action_case_event(dict(row)) for row in rows]

    def ensure_action_case_for_assistant_action(
        self,
        office_id: str,
        *,
        action: dict[str, Any],
        draft: dict[str, Any] | None,
        created_by: str,
        status: str,
        current_step: str,
        note: str | None = None,
        actor: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action_id = int(action["id"])
        draft_id = int(draft["id"]) if draft and draft.get("id") else None
        case_row = self.get_action_case_by_action_id(office_id, action_id)
        if case_row is None and draft_id is not None:
            case_row = self.get_action_case_by_draft_id(office_id, draft_id)
        payload = {
            "action_type": action.get("action_type"),
            "target_channel": action.get("target_channel"),
            "action_status": action.get("status"),
            "dispatch_state": action.get("dispatch_state"),
            "draft_id": draft_id,
        }
        if draft:
            payload["draft_status"] = draft.get("approval_status")
            payload["delivery_status"] = draft.get("delivery_status")
        if case_row is None:
            case_row = self.create_action_case(
                office_id,
                case_type="assistant_action",
                title=str(action.get("title") or "Assistant action"),
                created_by=created_by,
                status=status,
                current_step=current_step,
                approval_required=bool(action.get("manual_review_required")),
                action_id=action_id,
                draft_id=draft_id,
                metadata={**payload, **dict(metadata or {})},
                last_actor=actor,
            )
        else:
            case_row = self.update_action_case(
                office_id,
                int(case_row["id"]),
                status=status,
                current_step=current_step,
                action_id=action_id,
                draft_id=draft_id,
                approval_required=bool(action.get("manual_review_required")),
                last_actor=actor,
                metadata={**payload, **dict(metadata or {})},
            ) or case_row
        self.add_action_case_event(
            office_id,
            case_id=int(case_row["id"]),
            step_key=current_step,
            event_type=status,
            actor=actor or created_by,
            note=note,
            payload=payload,
        )
        return case_row

    @staticmethod
    def _decode_action_case(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "metadata_json", "metadata")
        row["approval_required"] = bool(row.get("approval_required"))
        row["last_error"] = row.get("last_error") or None
        row["completed_at"] = row.get("completed_at") or None
        return row

    @staticmethod
    def _decode_action_case_event(row: dict[str, Any]) -> dict[str, Any]:
        return Persistence._decode_json_field(row, "payload_json", "payload")

    def create_dispatch_attempt(
        self,
        office_id: str,
        *,
        actor: str,
        action_id: int | None = None,
        draft_id: int | None = None,
        dispatch_target: str | None = None,
        status: str = "started",
        external_message_id: str | None = None,
        note: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            cur = conn.execute(
                """
                INSERT INTO dispatch_attempts (
                    office_id, action_id, draft_id, dispatch_target, status, external_message_id,
                    actor, note, error, metadata_json, started_at, completed_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    office_id,
                    action_id,
                    draft_id,
                    dispatch_target,
                    status,
                    external_message_id,
                    actor,
                    note,
                    error,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM dispatch_attempts WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_dispatch_attempt(dict(row)) if row else {}

    def get_dispatch_attempt(self, office_id: str, attempt_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dispatch_attempts WHERE office_id=? AND id=?",
                (office_id, attempt_id),
            ).fetchone()
            return self._decode_dispatch_attempt(dict(row)) if row else None

    def get_latest_dispatch_attempt(
        self,
        office_id: str,
        *,
        action_id: int | None = None,
        draft_id: int | None = None,
        only_open: bool = False,
    ) -> dict[str, Any] | None:
        if action_id is None and draft_id is None:
            return None
        query = "SELECT * FROM dispatch_attempts WHERE office_id=?"
        params: list[Any] = [office_id]
        if action_id is not None:
            query += " AND action_id=?"
            params.append(action_id)
        if draft_id is not None:
            query += " AND draft_id=?"
            params.append(draft_id)
        if only_open:
            query += " AND status IN ('started', 'dispatching', 'awaiting_external_confirmation', 'retry_scheduled')"
        query += " ORDER BY created_at DESC, id DESC LIMIT 1"
        with self._conn() as conn:
            row = conn.execute(query, params).fetchone()
            return self._decode_dispatch_attempt(dict(row)) if row else None

    def update_dispatch_attempt(
        self,
        office_id: str,
        attempt_id: int,
        *,
        status: str | None = None,
        external_message_id: str | None | object = _UNSET,
        note: str | None | object = _UNSET,
        error: str | None | object = _UNSET,
        metadata: dict[str, Any] | None = None,
        completed_at: str | None | object = _UNSET,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            current = conn.execute(
                "SELECT * FROM dispatch_attempts WHERE office_id=? AND id=?",
                (office_id, attempt_id),
            ).fetchone()
            if not current:
                return None
            current_dict = dict(current)
            next_metadata = dict(json.loads(current_dict.get("metadata_json") or "{}"))
            if metadata:
                next_metadata.update(metadata)
            conn.execute(
                """
                UPDATE dispatch_attempts
                SET status=?, external_message_id=?, note=?, error=?, metadata_json=?, completed_at=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    status or current_dict["status"],
                    current_dict.get("external_message_id") if external_message_id is self._UNSET else external_message_id,
                    current_dict.get("note") if note is self._UNSET else note,
                    current_dict.get("error") if error is self._UNSET else error,
                    json.dumps(next_metadata, ensure_ascii=False),
                    current_dict.get("completed_at") if completed_at is self._UNSET else completed_at,
                    self._now(),
                    office_id,
                    attempt_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM dispatch_attempts WHERE office_id=? AND id=?",
                (office_id, attempt_id),
            ).fetchone()
            return self._decode_dispatch_attempt(dict(updated)) if updated else None

    def list_dispatch_attempts(
        self,
        office_id: str,
        *,
        action_id: int | None = None,
        draft_id: int | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM dispatch_attempts WHERE office_id=?"
        params: list[Any] = [office_id]
        if action_id is not None:
            query += " AND action_id=?"
            params.append(action_id)
        if draft_id is not None:
            query += " AND draft_id=?"
            params.append(draft_id)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._decode_dispatch_attempt(dict(row)) for row in rows]

    @staticmethod
    def _decode_dispatch_attempt(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "metadata_json", "metadata")
        row["external_message_id"] = row.get("external_message_id") or None
        row["note"] = row.get("note") or None
        row["error"] = row.get("error") or None
        row["completed_at"] = row.get("completed_at") or None
        return row

    def create_external_receipt(
        self,
        office_id: str,
        *,
        actor: str,
        dispatch_attempt_id: int | None = None,
        action_id: int | None = None,
        draft_id: int | None = None,
        provider: str | None = None,
        receipt_type: str = "dispatch_update",
        receipt_status: str | None = None,
        external_receipt_id: str | None = None,
        external_message_id: str | None = None,
        external_reference: str | None = None,
        note: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            cur = conn.execute(
                """
                INSERT INTO external_receipts (
                    office_id, dispatch_attempt_id, action_id, draft_id, provider, receipt_type, receipt_status,
                    external_receipt_id, external_message_id, external_reference, actor, note, payload_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    dispatch_attempt_id,
                    action_id,
                    draft_id,
                    provider,
                    receipt_type,
                    receipt_status,
                    external_receipt_id,
                    external_message_id,
                    external_reference,
                    actor,
                    note,
                    json.dumps(payload or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM external_receipts WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_external_receipt(dict(row)) if row else {}

    def list_external_receipts(
        self,
        office_id: str,
        *,
        action_id: int | None = None,
        draft_id: int | None = None,
        dispatch_attempt_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM external_receipts WHERE office_id=?"
        params: list[Any] = [office_id]
        if dispatch_attempt_id is not None:
            query += " AND dispatch_attempt_id=?"
            params.append(dispatch_attempt_id)
        if action_id is not None:
            query += " AND action_id=?"
            params.append(action_id)
        if draft_id is not None:
            query += " AND draft_id=?"
            params.append(draft_id)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._decode_external_receipt(dict(row)) for row in rows]

    @staticmethod
    def _decode_external_receipt(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "payload_json", "payload")
        row["provider"] = row.get("provider") or None
        row["receipt_status"] = row.get("receipt_status") or None
        row["external_receipt_id"] = row.get("external_receipt_id") or None
        row["external_message_id"] = row.get("external_message_id") or None
        row["external_reference"] = row.get("external_reference") or None
        row["note"] = row.get("note") or None
        return row

    def add_approval_event(
        self,
        office_id: str,
        *,
        actor: str,
        event_type: str,
        action_id: int | None = None,
        outbound_draft_id: int | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO approval_events (office_id, action_id, outbound_draft_id, event_type, actor, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (office_id, action_id, outbound_draft_id, event_type, actor, note, self._now()),
            )
            row = conn.execute("SELECT * FROM approval_events WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row) if row else {}

    def list_approval_events(self, office_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM approval_events WHERE office_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
                (office_id, max(1, min(limit, 200))),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_agent_run(
        self,
        office_id: str,
        *,
        title: str,
        goal: str,
        created_by: str,
        status: str = "queued",
        matter_id: int | None = None,
        thread_id: int | None = None,
        parent_run_id: int | None = None,
        source_kind: str = "assistant",
        run_type: str = "investigation",
        summary: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        approval_required: bool = False,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            cur = conn.execute(
                """
                INSERT INTO agent_runs (
                    office_id, matter_id, thread_id, parent_run_id, source_kind, run_type, title, goal,
                    status, created_by, summary_json, result_json, error, approval_required,
                    created_at, updated_at, started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    matter_id,
                    thread_id,
                    parent_run_id,
                    source_kind,
                    run_type,
                    title,
                    goal,
                    status,
                    created_by,
                    json.dumps(summary or {}, ensure_ascii=False),
                    json.dumps(result or {}, ensure_ascii=False),
                    error,
                    1 if approval_required else 0,
                    now,
                    now,
                    now if status in {"planning", "running", "completed"} else None,
                ),
            )
            row = conn.execute("SELECT * FROM agent_runs WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_agent_run(dict(row)) if row else {}

    def update_agent_run(
        self,
        office_id: str,
        run_id: int,
        *,
        status: str | None = None,
        summary: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        approval_required: bool | None = None,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            current = conn.execute("SELECT * FROM agent_runs WHERE office_id=? AND id=?", (office_id, run_id)).fetchone()
            if not current:
                return None
            current_decoded = self._decode_agent_run(dict(current))
            next_status = status or str(current_decoded.get("status") or "queued")
            next_summary = summary if summary is not None else current_decoded.get("summary")
            next_result = result if result is not None else current_decoded.get("result")
            conn.execute(
                """
                UPDATE agent_runs
                SET status=?, summary_json=?, result_json=?, error=?, approval_required=?, updated_at=?,
                    started_at=COALESCE(started_at, ?),
                    completed_at=?,
                    cancelled_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    next_status,
                    json.dumps(next_summary or {}, ensure_ascii=False),
                    json.dumps(next_result or {}, ensure_ascii=False),
                    error if error is not None else current_decoded.get("error"),
                    1 if (approval_required if approval_required is not None else bool(current_decoded.get("approval_required"))) else 0,
                    now,
                    now if next_status in {"planning", "running", "completed"} else None,
                    now if next_status in {"completed", "failed", "cancelled", "awaiting_approval"} else None,
                    now if next_status == "cancelled" else None,
                    office_id,
                    run_id,
                ),
            )
            row = conn.execute("SELECT * FROM agent_runs WHERE office_id=? AND id=?", (office_id, run_id)).fetchone()
            return self._decode_agent_run(dict(row)) if row else None

    def get_agent_run(self, office_id: str, run_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE office_id=? AND id=?", (office_id, run_id)).fetchone()
            return self._decode_agent_run(dict(row)) if row else None

    def list_agent_runs(self, office_id: str, *, limit: int = 20, thread_id: int | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            safe_limit = max(1, min(limit, 200))
            if thread_id is None:
                rows = conn.execute(
                    "SELECT * FROM agent_runs WHERE office_id=? ORDER BY updated_at DESC, id DESC LIMIT ?",
                    (office_id, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_runs WHERE office_id=? AND thread_id=? ORDER BY updated_at DESC, id DESC LIMIT ?",
                    (office_id, thread_id, safe_limit),
                ).fetchall()
            return [self._decode_agent_run(dict(row)) for row in rows]

    def create_agent_step(
        self,
        office_id: str,
        *,
        run_id: int,
        step_index: int,
        role: str,
        title: str,
        status: str = "pending",
        rationale: str | None = None,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO agent_steps (
                    run_id, office_id, step_index, role, title, status, rationale, input_json, output_json, error,
                    created_at, updated_at, started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    office_id,
                    step_index,
                    role,
                    title,
                    status,
                    rationale,
                    json.dumps(input_payload or {}, ensure_ascii=False),
                    json.dumps(output_payload or {}, ensure_ascii=False),
                    error,
                    now,
                    now,
                    now if status in {"running", "completed"} else None,
                ),
            )
            row = conn.execute("SELECT * FROM agent_steps WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_agent_step(dict(row)) if row else {}

    def update_agent_step(
        self,
        office_id: str,
        step_id: int,
        *,
        status: str | None = None,
        output_payload: dict[str, Any] | None = None,
        rationale: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            current = conn.execute("SELECT * FROM agent_steps WHERE office_id=? AND id=?", (office_id, step_id)).fetchone()
            if not current:
                return None
            current_decoded = self._decode_agent_step(dict(current))
            next_status = status or str(current_decoded.get("status") or "pending")
            conn.execute(
                """
                UPDATE agent_steps
                SET status=?, rationale=?, output_json=?, error=?, updated_at=?,
                    started_at=COALESCE(started_at, ?),
                    completed_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    next_status,
                    rationale if rationale is not None else current_decoded.get("rationale"),
                    json.dumps(output_payload if output_payload is not None else (current_decoded.get("output") or {}), ensure_ascii=False),
                    error if error is not None else current_decoded.get("error"),
                    now,
                    now if next_status in {"running", "completed"} else None,
                    now if next_status in {"completed", "failed", "cancelled", "blocked"} else None,
                    office_id,
                    step_id,
                ),
            )
            row = conn.execute("SELECT * FROM agent_steps WHERE office_id=? AND id=?", (office_id, step_id)).fetchone()
            return self._decode_agent_step(dict(row)) if row else None

    def list_agent_steps(self, office_id: str, *, run_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_steps WHERE office_id=? AND run_id=? ORDER BY step_index ASC, id ASC",
                (office_id, run_id),
            ).fetchall()
            return [self._decode_agent_step(dict(row)) for row in rows]

    def create_tool_invocation(
        self,
        office_id: str,
        *,
        run_id: int,
        step_id: int | None,
        tool_name: str,
        tool_class: str,
        risk_level: str,
        approval_policy: str,
        status: str = "pending",
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        error: str | None = None,
        approval_required: bool = False,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO tool_invocations (
                    run_id, office_id, step_id, tool_name, tool_class, risk_level, approval_policy, status,
                    input_json, output_json, error, approval_required, created_at, updated_at, started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    office_id,
                    step_id,
                    tool_name,
                    tool_class,
                    risk_level,
                    approval_policy,
                    status,
                    json.dumps(input_payload or {}, ensure_ascii=False),
                    json.dumps(output_payload or {}, ensure_ascii=False),
                    error,
                    1 if approval_required else 0,
                    now,
                    now,
                    now if status in {"running", "completed"} else None,
                ),
            )
            row = conn.execute("SELECT * FROM tool_invocations WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_tool_invocation(dict(row)) if row else {}

    def update_tool_invocation(
        self,
        office_id: str,
        invocation_id: int,
        *,
        status: str | None = None,
        output_payload: dict[str, Any] | None = None,
        error: str | None = None,
        approval_required: bool | None = None,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            current = conn.execute("SELECT * FROM tool_invocations WHERE office_id=? AND id=?", (office_id, invocation_id)).fetchone()
            if not current:
                return None
            current_decoded = self._decode_tool_invocation(dict(current))
            next_status = status or str(current_decoded.get("status") or "pending")
            conn.execute(
                """
                UPDATE tool_invocations
                SET status=?, output_json=?, error=?, approval_required=?, updated_at=?,
                    started_at=COALESCE(started_at, ?),
                    completed_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    next_status,
                    json.dumps(output_payload if output_payload is not None else (current_decoded.get("output") or {}), ensure_ascii=False),
                    error if error is not None else current_decoded.get("error"),
                    1 if (approval_required if approval_required is not None else bool(current_decoded.get("approval_required"))) else 0,
                    now,
                    now if next_status in {"running", "completed"} else None,
                    now if next_status in {"completed", "failed", "cancelled", "blocked"} else None,
                    office_id,
                    invocation_id,
                ),
            )
            row = conn.execute("SELECT * FROM tool_invocations WHERE office_id=? AND id=?", (office_id, invocation_id)).fetchone()
            return self._decode_tool_invocation(dict(row)) if row else None

    def list_tool_invocations(self, office_id: str, *, run_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tool_invocations WHERE office_id=? AND run_id=? ORDER BY id ASC",
                (office_id, run_id),
            ).fetchall()
            return [self._decode_tool_invocation(dict(row)) for row in rows]

    def create_run_approval_request(
        self,
        office_id: str,
        *,
        run_id: int,
        approval_kind: str,
        title: str,
        reason: str,
        created_by: str,
        step_id: int | None = None,
        tool_invocation_id: int | None = None,
        payload: dict[str, Any] | None = None,
        status: str = "pending",
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO run_approval_requests (
                    office_id, run_id, step_id, tool_invocation_id, approval_kind, title, reason, status,
                    payload_json, created_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    run_id,
                    step_id,
                    tool_invocation_id,
                    approval_kind,
                    title,
                    reason,
                    status,
                    json.dumps(payload or {}, ensure_ascii=False),
                    created_by,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM run_approval_requests WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_run_approval_request(dict(row)) if row else {}

    def decide_run_approval_request(
        self,
        office_id: str,
        approval_id: int,
        *,
        status: str,
        decided_by: str,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE run_approval_requests
                SET status=?, decided_by=?, decided_at=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (status, decided_by, now, now, office_id, approval_id),
            )
            row = conn.execute("SELECT * FROM run_approval_requests WHERE office_id=? AND id=?", (office_id, approval_id)).fetchone()
            return self._decode_run_approval_request(dict(row)) if row else None

    def list_run_approval_requests(self, office_id: str, *, run_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM run_approval_requests WHERE office_id=? AND run_id=? ORDER BY id ASC",
                (office_id, run_id),
            ).fetchall()
            return [self._decode_run_approval_request(dict(row)) for row in rows]

    def create_browser_session_artifact(
        self,
        office_id: str,
        *,
        run_id: int,
        artifact_type: str,
        path: str | None = None,
        url: str | None = None,
        sha256: str | None = None,
        metadata: dict[str, Any] | None = None,
        step_id: int | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO browser_session_artifacts (
                    office_id, run_id, step_id, artifact_type, path, url, sha256, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    run_id,
                    step_id,
                    artifact_type,
                    path,
                    url,
                    sha256,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM browser_session_artifacts WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_browser_session_artifact(dict(row)) if row else {}

    def list_browser_session_artifacts(self, office_id: str, *, run_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM browser_session_artifacts WHERE office_id=? AND run_id=? ORDER BY id ASC",
                (office_id, run_id),
            ).fetchall()
            return [self._decode_browser_session_artifact(dict(row)) for row in rows]

    def add_memory_event(
        self,
        office_id: str,
        *,
        memory_scope: str,
        event_type: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        run_id: int | None = None,
        entity_key: str | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO memory_events (office_id, run_id, memory_scope, entity_key, event_type, summary, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    run_id,
                    memory_scope,
                    entity_key,
                    event_type,
                    summary,
                    json.dumps(payload or {}, ensure_ascii=False),
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM memory_events WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_memory_event(dict(row)) if row else {}

    def list_memory_events(self, office_id: str, *, run_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            safe_limit = max(1, min(limit, 200))
            if run_id is None:
                rows = conn.execute(
                    "SELECT * FROM memory_events WHERE office_id=? ORDER BY id DESC LIMIT ?",
                    (office_id, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory_events WHERE office_id=? AND run_id=? ORDER BY id DESC LIMIT ?",
                    (office_id, run_id, safe_limit),
                ).fetchall()
            return [self._decode_memory_event(dict(row)) for row in rows]

    def add_external_event(
        self,
        office_id: str,
        *,
        provider: str,
        event_type: str,
        summary: str,
        external_ref: str | None = None,
        title: str | None = None,
        actor_label: str | None = None,
        importance: str = "normal",
        reply_needed: bool = False,
        legal_risk: bool = False,
        evidence_value: bool = False,
        metadata: dict[str, Any] | None = None,
        source_created_at: str | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO external_events (
                    office_id, provider, event_type, external_ref, title, actor_label, summary, importance,
                    reply_needed, legal_risk, evidence_value, metadata_json, source_created_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    provider,
                    event_type,
                    external_ref,
                    title,
                    actor_label,
                    summary,
                    importance,
                    1 if reply_needed else 0,
                    1 if legal_risk else 0,
                    1 if evidence_value else 0,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    source_created_at,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM external_events WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_external_event(dict(row)) if row else {}

    def list_external_events(
        self,
        office_id: str,
        *,
        provider: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            clauses = ["office_id=?"]
            params: list[Any] = [office_id]
            if provider:
                clauses.append("provider=?")
                params.append(str(provider))
            if event_type:
                clauses.append("event_type=?")
                params.append(str(event_type))
            params.append(max(1, min(limit, 200)))
            rows = conn.execute(
                f"SELECT * FROM external_events WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC, id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
            return [self._decode_external_event(dict(row)) for row in rows]

    def delete_external_events(
        self,
        office_id: str,
        *,
        provider: str,
        event_type: str | None = None,
    ) -> int:
        with self._conn() as conn:
            clauses = ["office_id=?", "provider=?"]
            params: list[Any] = [office_id, str(provider)]
            if event_type:
                clauses.append("event_type=?")
                params.append(str(event_type))
            cur = conn.execute(
                f"DELETE FROM external_events WHERE {' AND '.join(clauses)}",
                tuple(params),
            )
            return int(cur.rowcount or 0)

    def upsert_automation_rule(
        self,
        office_id: str,
        *,
        rule_type: str,
        scope: dict[str, Any] | None,
        config: dict[str, Any] | None,
        created_by: str,
        enabled: bool = True,
        managed_by_assistant: bool = True,
    ) -> dict[str, Any]:
        now = self._now()
        scope_json = json.dumps(scope or {}, ensure_ascii=False)
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM automation_rules
                WHERE office_id=? AND rule_type=? AND scope_json=?
                """,
                (office_id, rule_type, scope_json),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE automation_rules
                    SET config_json=?, enabled=?, managed_by_assistant=?, updated_at=?
                    WHERE office_id=? AND id=?
                    """,
                    (
                        json.dumps(config or {}, ensure_ascii=False),
                        1 if enabled else 0,
                        1 if managed_by_assistant else 0,
                        now,
                        office_id,
                        int(row["id"]),
                    ),
                )
                updated = conn.execute("SELECT * FROM automation_rules WHERE office_id=? AND id=?", (office_id, int(row["id"]))).fetchone()
                return self._decode_automation_rule(dict(updated)) if updated else {}
            cur = conn.execute(
                """
                INSERT INTO automation_rules (
                    office_id, rule_type, scope_json, config_json, enabled, managed_by_assistant,
                    created_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    rule_type,
                    scope_json,
                    json.dumps(config or {}, ensure_ascii=False),
                    1 if enabled else 0,
                    1 if managed_by_assistant else 0,
                    created_by,
                    now,
                    now,
                ),
            )
            created = conn.execute("SELECT * FROM automation_rules WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_automation_rule(dict(created)) if created else {}

    def list_automation_rules(self, office_id: str, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if enabled_only:
                rows = conn.execute(
                    "SELECT * FROM automation_rules WHERE office_id=? AND enabled=1 ORDER BY updated_at DESC, id DESC",
                    (office_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM automation_rules WHERE office_id=? ORDER BY updated_at DESC, id DESC",
                    (office_id,),
                ).fetchall()
            return [self._decode_automation_rule(dict(row)) for row in rows]

    def list_agent_run_events(self, office_id: str, *, run_id: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for step in self.list_agent_steps(office_id, run_id=run_id):
            items.append(
                {
                    "kind": "step",
                    "id": step.get("id"),
                    "status": step.get("status"),
                    "title": step.get("title"),
                    "role": step.get("role"),
                    "created_at": step.get("created_at"),
                    "updated_at": step.get("updated_at"),
                    "payload": step,
                }
            )
        for invocation in self.list_tool_invocations(office_id, run_id=run_id):
            items.append(
                {
                    "kind": "tool",
                    "id": invocation.get("id"),
                    "status": invocation.get("status"),
                    "title": invocation.get("tool_name"),
                    "role": "executor",
                    "created_at": invocation.get("created_at"),
                    "updated_at": invocation.get("updated_at"),
                    "payload": invocation,
                }
            )
        for approval in self.list_run_approval_requests(office_id, run_id=run_id):
            items.append(
                {
                    "kind": "approval",
                    "id": approval.get("id"),
                    "status": approval.get("status"),
                    "title": approval.get("title"),
                    "role": "reviewer",
                    "created_at": approval.get("created_at"),
                    "updated_at": approval.get("updated_at"),
                    "payload": approval,
                }
            )
        for artifact in self.list_browser_session_artifacts(office_id, run_id=run_id):
            items.append(
                {
                    "kind": "artifact",
                    "id": artifact.get("id"),
                    "status": "stored",
                    "title": artifact.get("artifact_type"),
                    "role": "executor",
                    "created_at": artifact.get("created_at"),
                    "updated_at": artifact.get("created_at"),
                    "payload": artifact,
                }
            )
        items.sort(key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)))
        return items

    def list_all_matter_drafts(self, office_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT d.*, m.title AS matter_title
                FROM drafts d
                JOIN matters m ON m.id = d.matter_id
                WHERE d.office_id=?
                ORDER BY d.updated_at DESC, d.id DESC
                """,
                (office_id,),
            ).fetchall()
            return [self._decode_draft(dict(row)) for row in rows]

    def list_office_tasks(self, office_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE office_id=? ORDER BY COALESCE(due_at, updated_at, created_at) ASC, id DESC",
                (office_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_assistant_thread(self, office_id: str, *, created_by: str, title: str = "Yeni görev") -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            cur = conn.execute(
                """
                INSERT INTO assistant_threads (office_id, title, created_by, created_at, updated_at, archived)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (office_id, title, created_by, now, now),
            )
            row = conn.execute("SELECT * FROM assistant_threads WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row) if row else {}

    def get_or_create_assistant_thread(self, office_id: str, *, created_by: str, title: str = "LawCopilot Asistan") -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM assistant_threads
                WHERE office_id=? AND archived=0
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (office_id,),
            ).fetchone()
            if row:
                return dict(row)
        return self.create_assistant_thread(office_id, created_by=created_by, title=title)

    def list_assistant_threads(self, office_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            safe_limit = max(1, min(limit, 200))
            rows = conn.execute(
                """
                SELECT
                    t.*,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM assistant_messages m
                        WHERE m.office_id=t.office_id AND m.thread_id=t.id
                    ), 0) AS message_count,
                    (
                        SELECT m.content
                        FROM assistant_messages m
                        WHERE m.office_id=t.office_id AND m.thread_id=t.id
                        ORDER BY m.id DESC
                        LIMIT 1
                    ) AS last_message_preview,
                    (
                        SELECT m.created_at
                        FROM assistant_messages m
                        WHERE m.office_id=t.office_id AND m.thread_id=t.id
                        ORDER BY m.id DESC
                        LIMIT 1
                    ) AS last_message_at
                FROM assistant_threads t
                WHERE t.office_id=? AND t.archived=0
                ORDER BY t.updated_at DESC, t.id DESC
                LIMIT ?
                """,
                (office_id, safe_limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_assistant_thread(self, office_id: str, thread_id: int | None = None) -> dict[str, Any] | None:
        with self._conn() as conn:
            if thread_id is not None:
                row = conn.execute(
                    "SELECT * FROM assistant_threads WHERE office_id=? AND id=? AND archived=0",
                    (office_id, thread_id),
                ).fetchone()
                return dict(row) if row else None
            row = conn.execute(
                """
                SELECT * FROM assistant_threads
                WHERE office_id=? AND archived=0
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (office_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_assistant_thread(
        self,
        office_id: str,
        *,
        thread_id: int,
        title: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any] | None:
        assignments: list[str] = ["updated_at=?"]
        values: list[Any] = [self._now()]
        if title is not None:
            assignments.append("title=?")
            values.append(title)
        if archived is not None:
            assignments.append("archived=?")
            values.append(1 if archived else 0)
        values.extend([office_id, thread_id])
        with self._conn() as conn:
            conn.execute(
                f"UPDATE assistant_threads SET {', '.join(assignments)} WHERE office_id=? AND id=?",
                tuple(values),
            )
            row = conn.execute(
                "SELECT * FROM assistant_threads WHERE office_id=? AND id=?",
                (office_id, thread_id),
            ).fetchone()
            return dict(row) if row else None

    def delete_assistant_thread(self, office_id: str, *, thread_id: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM assistant_threads WHERE office_id=? AND id=? AND archived=0",
                (office_id, thread_id),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE assistant_threads SET archived=1, updated_at=? WHERE office_id=? AND id=?",
                (self._now(), office_id, thread_id),
            )
            return True

    def maybe_promote_assistant_thread_title(
        self,
        office_id: str,
        *,
        thread_id: int,
        content: str,
    ) -> dict[str, Any] | None:
        candidate = " ".join(str(content or "").split()).strip()
        if not candidate:
            return self.get_assistant_thread(office_id, thread_id)
        if len(candidate) > 72:
            candidate = f"{candidate[:69].rstrip()}..."
        with self._conn() as conn:
            row = conn.execute(
                "SELECT title FROM assistant_threads WHERE office_id=? AND id=?",
                (office_id, thread_id),
            ).fetchone()
            if not row:
                return None
            current_title = str(row["title"] or "").strip().lower()
            if current_title not in {"lawcopilot asistan", "yeni görev", "yeni oturum"}:
                return self.get_assistant_thread(office_id, thread_id)
        return self.update_assistant_thread(office_id, thread_id=thread_id, title=candidate)

    def append_assistant_message(
        self,
        office_id: str,
        *,
        thread_id: int,
        role: str,
        content: str,
        linked_entities: list[dict[str, Any]] | None = None,
        tool_suggestions: list[dict[str, Any]] | None = None,
        draft_preview: dict[str, Any] | None = None,
        source_context: dict[str, Any] | None = None,
        requires_approval: bool = False,
        generated_from: str | None = None,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO assistant_messages (
                    thread_id, office_id, role, content, linked_entities_json, tool_suggestions_json,
                    draft_preview_json, source_context_json, requires_approval, generated_from,
                    ai_provider, ai_model, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    office_id,
                    role,
                    content,
                    json.dumps(linked_entities or [], ensure_ascii=False),
                    json.dumps(tool_suggestions or [], ensure_ascii=False),
                    json.dumps(draft_preview or {}, ensure_ascii=False),
                    json.dumps(source_context or {}, ensure_ascii=False),
                    1 if requires_approval else 0,
                    generated_from,
                    ai_provider,
                    ai_model,
                    now,
                ),
            )
            conn.execute(
                "UPDATE assistant_threads SET updated_at=? WHERE office_id=? AND id=?",
                (now, office_id, thread_id),
            )
            row = conn.execute("SELECT * FROM assistant_messages WHERE id=?", (cur.lastrowid,)).fetchone()
            decoded = self._decode_assistant_message(dict(row)) if row else {}
            if row and source_context:
                self.append_assistant_context_snapshot(
                    office_id,
                    thread_id=thread_id,
                    message_id=int(cur.lastrowid),
                    source_context=source_context,
                    created_at=now,
                    conn=conn,
                )
            return decoded

    def append_assistant_context_snapshot(
        self,
        office_id: str,
        *,
        thread_id: int,
        message_id: int,
        source_context: dict[str, Any] | None,
        created_at: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        sanitized_source_context = self._sanitize_assistant_context_snapshot(source_context or {})
        payload = json.dumps(sanitized_source_context, ensure_ascii=False)
        now = created_at or self._now()
        active_conn: sqlite3.Connection
        close_when_done = False
        if conn is None:
            active_conn = self._conn()
            close_when_done = True
        else:
            active_conn = conn
        try:
            cur = active_conn.execute(
                """
                INSERT INTO assistant_context_snapshots (
                    office_id, thread_id, message_id, source_context_json, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (office_id, thread_id, message_id, payload, now),
            )
            row = active_conn.execute(
                "SELECT * FROM assistant_context_snapshots WHERE id=?",
                (cur.lastrowid,),
            ).fetchone()
            self._prune_assistant_context_snapshots(
                office_id,
                thread_id=thread_id,
                conn=active_conn,
            )
            return self._decode_assistant_context_snapshot(dict(row)) if row else {}
        finally:
            if close_when_done:
                active_conn.close()

    def list_assistant_context_snapshots(
        self,
        office_id: str,
        *,
        thread_id: int | None = None,
        message_id: int | None = None,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        with self._conn() as conn:
            if message_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM assistant_context_snapshots
                    WHERE office_id=? AND message_id=?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (office_id, message_id, safe_limit),
                ).fetchall()
            elif thread_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM assistant_context_snapshots
                    WHERE office_id=? AND thread_id=?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (office_id, thread_id, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM assistant_context_snapshots
                    WHERE office_id=?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (office_id, safe_limit),
                ).fetchall()
        return [self._decode_assistant_context_snapshot(dict(row)) for row in rows]

    def _prune_assistant_context_snapshots(
        self,
        office_id: str,
        *,
        thread_id: int,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        active_conn = conn or self._conn()
        close_when_done = conn is None
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=self.ASSISTANT_CONTEXT_SNAPSHOT_RETENTION_DAYS)).isoformat()
            active_conn.execute(
                """
                DELETE FROM assistant_context_snapshots
                WHERE office_id=? AND thread_id=? AND created_at < ?
                """,
                (office_id, thread_id, cutoff),
            )
            rows = active_conn.execute(
                """
                SELECT id FROM assistant_context_snapshots
                WHERE office_id=? AND thread_id=?
                ORDER BY created_at DESC, id DESC
                LIMIT -1 OFFSET ?
                """,
                (office_id, thread_id, self.ASSISTANT_CONTEXT_SNAPSHOT_MAX_PER_THREAD),
            ).fetchall()
            stale_ids = [int(row["id"]) for row in rows]
            if stale_ids:
                placeholders = ",".join("?" for _ in stale_ids)
                active_conn.execute(
                    f"DELETE FROM assistant_context_snapshots WHERE id IN ({placeholders})",
                    stale_ids,
                )
        finally:
            if close_when_done:
                active_conn.close()

    @staticmethod
    def _snapshot_ref(value: Any) -> dict[str, Any]:
        if value is None:
            payload = ""
            size = 0
        elif isinstance(value, str):
            payload = value
            size = len(value)
        else:
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
            size = len(payload)
        return {
            "ref_only": True,
            "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "size": size,
        }

    @classmethod
    def _sanitize_assistant_context_pack_item(cls, item: dict[str, Any]) -> dict[str, Any]:
        sanitized = {key: item.get(key) for key in cls._SNAPSHOT_ALLOWED_CONTEXT_ITEM_KEYS if key in item}
        title = str(item.get("title") or "").strip()
        if title:
            sanitized["title_ref"] = cls._snapshot_ref(title)
        summary = item.get("summary")
        if summary not in {None, ""}:
            sanitized["summary_ref"] = cls._snapshot_ref(summary)
        prompt_line = item.get("prompt_line")
        if prompt_line not in {None, ""}:
            sanitized["prompt_line_ref"] = cls._snapshot_ref(prompt_line)
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and metadata:
            sanitized["metadata"] = cls._sanitize_assistant_context_snapshot(metadata)
        return sanitized

    @classmethod
    def _sanitize_compact_context_block(cls, payload: dict[str, Any], *, name: str) -> dict[str, Any]:
        sanitized: dict[str, Any] = {
            "context_type": name,
            "field_count": len(payload),
        }
        for key, value in payload.items():
            normalized_key = str(key or "").strip().lower()
            if normalized_key in {"scopes", "selected_categories", "context_selection_reasons"} and isinstance(value, list):
                sanitized[key] = [str(item) for item in list(value)[:12]]
            elif normalized_key in {"backend", "usage_note"} and isinstance(value, str):
                sanitized[key] = value
            elif normalized_key == "intent" and isinstance(value, dict):
                sanitized[key] = {
                    "name": str(value.get("name") or "").strip() or "general",
                    "categories": [str(item) for item in list(value.get("categories") or [])[:8]],
                }
            elif isinstance(value, list):
                sanitized[f"{key}_count"] = len(value)
            elif isinstance(value, dict):
                sanitized[f"{key}_count"] = len(value)
            elif normalized_key in cls._SNAPSHOT_TEXT_KEYS:
                sanitized[f"{key}_ref"] = cls._snapshot_ref(value)
            else:
                sanitized[key] = value
        return sanitized

    @classmethod
    def _sanitize_source_ref(cls, item: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in item.items():
            normalized_key = str(key or "").strip().lower()
            if normalized_key in cls._SNAPSHOT_TEXT_KEYS:
                sanitized[f"{key}_ref"] = cls._snapshot_ref(value)
            elif isinstance(value, dict):
                sanitized[key] = cls._sanitize_assistant_context_snapshot(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    cls._sanitize_assistant_context_snapshot(entry) if isinstance(entry, dict) else cls._snapshot_ref(entry)
                    for entry in list(value)[:8]
                ]
                if len(value) > 8:
                    sanitized[f"{key}_truncated"] = True
            else:
                sanitized[key] = value
        return sanitized

    @classmethod
    def _sanitize_assistant_context_snapshot(cls, payload: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {
            "snapshot_version": 2,
            "retention_class": "redacted_structured",
        }
        for key, value in payload.items():
            normalized_key = str(key or "").strip().lower()
            if value is None:
                continue
            if normalized_key == "assistant_context_pack" and isinstance(value, list):
                sanitized[key] = [cls._sanitize_assistant_context_pack_item(item) for item in value if isinstance(item, dict)][:16]
                continue
            if normalized_key in {"knowledge_context", "personal_model_context"} and isinstance(value, dict):
                sanitized[key] = cls._sanitize_compact_context_block(value, name=normalized_key)
                continue
            if normalized_key == "source_refs" and isinstance(value, list):
                sanitized[key] = [cls._sanitize_source_ref(item) for item in value if isinstance(item, dict)][:16]
                continue
            if normalized_key in cls._SNAPSHOT_TEXT_KEYS:
                sanitized[f"{key}_ref"] = cls._snapshot_ref(value)
                continue
            if isinstance(value, dict):
                sanitized[key] = cls._sanitize_assistant_context_snapshot(value)
                continue
            if isinstance(value, list):
                if all(isinstance(item, dict) for item in value):
                    sanitized[key] = [cls._sanitize_assistant_context_snapshot(item) for item in list(value)[:8]]
                else:
                    sanitized[f"{key}_count"] = len(value)
                if len(value) > 8:
                    sanitized[f"{key}_truncated"] = True
                continue
            sanitized[key] = value
        return sanitized

    def list_assistant_messages(
        self,
        office_id: str,
        *,
        thread_id: int,
        limit: int = 120,
        before_id: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            safe_limit = max(1, min(limit, 500))
            if before_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM assistant_messages
                    WHERE office_id=? AND thread_id=? AND id < ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (office_id, thread_id, before_id, safe_limit),
                ).fetchall()
                rows = list(reversed(rows))
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM assistant_messages
                        WHERE office_id=? AND thread_id=?
                        ORDER BY id DESC
                        LIMIT ?
                    ) sub ORDER BY id ASC
                    """,
                    (office_id, thread_id, safe_limit),
                ).fetchall()
            return [self._decode_assistant_message(dict(row)) for row in rows]

    def get_assistant_message(self, office_id: str, *, message_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM assistant_messages WHERE office_id=? AND id=?",
                (office_id, message_id),
            ).fetchone()
            return self._decode_assistant_message(dict(row)) if row else None

    def rewrite_assistant_user_message(
        self,
        office_id: str,
        *,
        thread_id: int,
        message_id: int,
        content: str,
        linked_entities: list[dict[str, Any]] | None = None,
        source_context: dict[str, Any] | None = None,
        generated_from: str | None = None,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM assistant_messages
                WHERE office_id=? AND thread_id=? AND id=? AND role='user'
                """,
                (office_id, thread_id, message_id),
            ).fetchone()
            if not row:
                return None
            current = dict(row)
            current_linked_entities = linked_entities if linked_entities is not None else json.loads(str(current.get("linked_entities_json") or "[]"))
            current_source_context = source_context if source_context is not None else json.loads(str(current.get("source_context_json") or "{}"))
            conn.execute(
                """
                UPDATE assistant_messages
                SET content=?, linked_entities_json=?, source_context_json=?, generated_from=?
                WHERE office_id=? AND thread_id=? AND id=?
                """,
                (
                    content,
                    json.dumps(current_linked_entities or [], ensure_ascii=False),
                    json.dumps(current_source_context or {}, ensure_ascii=False),
                    generated_from or current.get("generated_from"),
                    office_id,
                    thread_id,
                    message_id,
                ),
            )
            conn.execute(
                "DELETE FROM assistant_messages WHERE office_id=? AND thread_id=? AND id>?",
                (office_id, thread_id, message_id),
            )
            conn.execute(
                "UPDATE assistant_threads SET updated_at=? WHERE office_id=? AND id=?",
                (now, office_id, thread_id),
            )
            updated = conn.execute(
                "SELECT * FROM assistant_messages WHERE office_id=? AND thread_id=? AND id=?",
                (office_id, thread_id, message_id),
            ).fetchone()
            return self._decode_assistant_message(dict(updated)) if updated else None

    def list_assistant_feedback_messages(
        self,
        office_id: str,
        *,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            safe_limit = max(1, min(limit, 5000))
            rows = conn.execute(
                """
                SELECT * FROM assistant_messages
                WHERE office_id=?
                  AND role='assistant'
                  AND feedback_value IN ('liked', 'disliked')
                ORDER BY id ASC
                LIMIT ?
                """,
                (office_id, safe_limit),
            ).fetchall()
            return [self._decode_assistant_message(dict(row)) for row in rows]

    def set_assistant_message_star(self, office_id: str, *, message_id: int, starred: bool) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT thread_id FROM assistant_messages WHERE office_id=? AND id=?",
                (office_id, message_id),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """
                UPDATE assistant_messages
                SET starred=?, starred_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    1 if starred else 0,
                    now if starred else None,
                    office_id,
                    message_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM assistant_messages WHERE office_id=? AND id=?",
                (office_id, message_id),
            ).fetchone()
            return self._decode_assistant_message(dict(updated)) if updated else None

    def set_assistant_message_feedback(
        self,
        office_id: str,
        *,
        message_id: int,
        feedback_value: str | None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_value = str(feedback_value or "").strip().lower()
        if normalized_value not in {"liked", "disliked"}:
            normalized_value = ""
        normalized_note = str(note or "").strip() or None
        now = self._now() if normalized_value else None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM assistant_messages WHERE office_id=? AND id=?",
                (office_id, message_id),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """
                UPDATE assistant_messages
                SET feedback_value=?, feedback_note=?, feedback_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    normalized_value or None,
                    normalized_note if normalized_value else None,
                    now,
                    office_id,
                    message_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM assistant_messages WHERE office_id=? AND id=?",
                (office_id, message_id),
            ).fetchone()
            return self._decode_assistant_message(dict(updated)) if updated else None

    def list_starred_assistant_messages(
        self,
        office_id: str,
        *,
        thread_id: int | None = None,
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            safe_limit = max(1, min(limit, 500))
            if thread_id is None:
                rows = conn.execute(
                    """
                    SELECT m.*, t.title AS thread_title
                    FROM assistant_messages m
                    LEFT JOIN assistant_threads t
                      ON t.id = m.thread_id AND t.office_id = m.office_id
                    WHERE m.office_id=? AND COALESCE(m.starred, 0)=1
                    ORDER BY COALESCE(m.starred_at, m.created_at) DESC, m.id DESC
                    LIMIT ?
                    """,
                    (office_id, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT m.*, t.title AS thread_title
                    FROM assistant_messages m
                    LEFT JOIN assistant_threads t
                      ON t.id = m.thread_id AND t.office_id = m.office_id
                    WHERE m.office_id=? AND m.thread_id=? AND COALESCE(m.starred, 0)=1
                    ORDER BY COALESCE(m.starred_at, m.created_at) DESC, m.id DESC
                    LIMIT ?
                    """,
                    (office_id, thread_id, safe_limit),
                ).fetchall()
            return [self._decode_assistant_message(dict(row)) for row in rows]

    def count_assistant_messages(self, office_id: str, *, thread_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM assistant_messages WHERE office_id=? AND thread_id=?",
                (office_id, thread_id),
            ).fetchone()
            return int(row["cnt"]) if row else 0

    def reset_assistant_thread(self, office_id: str, *, created_by: str, title: str = "LawCopilot Asistan") -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM assistant_threads
                WHERE office_id=? AND archived=0
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (office_id,),
            ).fetchone()
            if not row:
                return self.get_or_create_assistant_thread(office_id, created_by=created_by, title=title)
            thread_id = int(row["id"])
            return self.reset_assistant_thread_by_id(office_id, thread_id=thread_id, created_by=created_by, title=title)

    def reset_assistant_thread_by_id(self, office_id: str, *, thread_id: int, created_by: str, title: str = "LawCopilot Asistan") -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM assistant_threads WHERE office_id=? AND id=? AND archived=0",
                (office_id, thread_id),
            ).fetchone()
            if not row:
                return self.create_assistant_thread(office_id, created_by=created_by, title=title)
            conn.execute("DELETE FROM assistant_messages WHERE office_id=? AND thread_id=?", (office_id, thread_id))
            conn.execute(
                "UPDATE assistant_threads SET title=?, created_by=?, updated_at=? WHERE office_id=? AND id=?",
                (title, created_by, now, office_id, thread_id),
            )
            updated = conn.execute(
                "SELECT * FROM assistant_threads WHERE office_id=? AND id=?",
                (office_id, thread_id),
            ).fetchone()
            return dict(updated) if updated else {}

    @staticmethod
    def _decode_assistant_message(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_field(row, "linked_entities_json", "linked_entities")
        row = Persistence._decode_json_field(row, "tool_suggestions_json", "tool_suggestions")
        row = Persistence._decode_json_field(row, "draft_preview_json", "draft_preview")
        row = Persistence._decode_json_field(row, "source_context_json", "source_context")
        row["requires_approval"] = bool(row.get("requires_approval"))
        row["starred"] = bool(row.get("starred"))
        feedback_value = str(row.get("feedback_value") or "").strip().lower()
        row["feedback_value"] = feedback_value if feedback_value in {"liked", "disliked"} else None
        row["feedback_note"] = row.get("feedback_note") or None
        row["feedback_at"] = row.get("feedback_at") or None
        return row

    @staticmethod
    def _decode_assistant_context_snapshot(row: dict[str, Any]) -> dict[str, Any]:
        return Persistence._decode_json_object_field(row, "source_context_json", "source_context")

    @staticmethod
    def _decode_agent_run(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "summary_json", "summary")
        row = Persistence._decode_json_object_field(row, "result_json", "result")
        row["approval_required"] = bool(row.get("approval_required"))
        return row

    @staticmethod
    def _decode_agent_step(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "input_json", "input")
        row = Persistence._decode_json_object_field(row, "output_json", "output")
        return row

    @staticmethod
    def _decode_tool_invocation(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "input_json", "input")
        row = Persistence._decode_json_object_field(row, "output_json", "output")
        row["approval_required"] = bool(row.get("approval_required"))
        return row

    @staticmethod
    def _decode_run_approval_request(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "payload_json", "payload")
        return row

    @staticmethod
    def _decode_browser_session_artifact(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        return row

    @staticmethod
    def _decode_memory_event(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "payload_json", "payload")
        return row

    @staticmethod
    def _decode_external_event(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "metadata_json", "metadata")
        row["reply_needed"] = bool(row.get("reply_needed"))
        row["legal_risk"] = bool(row.get("legal_risk"))
        row["evidence_value"] = bool(row.get("evidence_value"))
        return row

    @staticmethod
    def _decode_automation_rule(row: dict[str, Any]) -> dict[str, Any]:
        row = Persistence._decode_json_object_field(row, "scope_json", "scope")
        row = Persistence._decode_json_object_field(row, "config_json", "config")
        row["enabled"] = bool(row.get("enabled"))
        row["managed_by_assistant"] = bool(row.get("managed_by_assistant"))
        return row
