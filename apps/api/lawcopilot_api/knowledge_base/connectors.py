from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from ..integrations.repository import IntegrationRepository


def _json_fingerprint(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


@dataclass
class ConnectorRecord:
    connector_name: str
    source_type: str
    title: str
    content: str
    source_ref: str
    metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: str | None = None
    tags: list[str] = field(default_factory=list)
    scope: str = "global"
    sensitivity: str = "medium"
    exportability: str = "redaction_required"
    model_routing_hint: str = "redaction_required"

    @property
    def fingerprint(self) -> str:
        payload = {
            "connector_name": self.connector_name,
            "source_type": self.source_type,
            "title": self.title,
            "content": self.content,
            "source_ref": self.source_ref,
            "metadata": self.metadata,
            "occurred_at": self.occurred_at,
            "tags": self.tags,
            "scope": self.scope,
            "sensitivity": self.sensitivity,
            "exportability": self.exportability,
            "model_routing_hint": self.model_routing_hint,
        }
        return _json_fingerprint(payload)


class KnowledgeConnector(Protocol):
    name: str
    description: str
    sync_mode: str
    provider_hints: tuple[str, ...]

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        ...


def _professional_scope(matter_id: Any | None) -> str:
    if matter_id is None:
        return "professional"
    return f"project:matter-{matter_id}"


def _channel_memory_state(item: dict[str, Any] | None) -> str:
    payload = dict(item or {})
    metadata = payload.get("metadata")
    metadata_obj = metadata if isinstance(metadata, dict) else {}
    state = str(payload.get("memory_state") or metadata_obj.get("memory_state") or "").strip().lower()
    if state in {"candidate_memory", "approved_memory"}:
        return state
    return "operational_only"


def _channel_memory_claim_eligible(item: dict[str, Any] | None) -> bool:
    return _channel_memory_state(item) == "approved_memory"


def _infer_place_category(value: Any | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    if any(token in text for token in ("ev", "home", "ikamet")):
        return "home"
    if any(token in text for token in ("ofis", "office", "büro", "buro", "workspace", "cowork")):
        return "office"
    if any(token in text for token in ("mahkeme", "court", "adliye")):
        return "court"
    if any(token in text for token in ("istasyon", "station", "metro", "havaalan", "terminal", "durak")):
        return "transit"
    if any(token in text for token in ("cami", "mescit", "mosque")):
        return "mosque"
    if any(token in text for token in ("kafe", "cafe", "kahve")):
        return "cafe"
    if any(token in text for token in ("market", "migros", "carrefour", "bim", "a101", "şok", "sok")):
        return "market"
    if any(token in text for token in ("restoran", "lokanta", "yemek", "salata", "çorba", "corba")):
        return "light_meal"
    if any(token in text for token in ("müze", "muze", "tarihi", "tarih", "historic")):
        return "historic_site"
    return "place"


def _recent_browser_artifacts(store: Any, office_id: str, *, run_limit: int = 8, artifact_limit: int = 40) -> list[dict[str, Any]]:
    if not hasattr(store, "list_agent_runs") or not hasattr(store, "list_browser_session_artifacts"):
        return []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run in store.list_agent_runs(office_id, limit=run_limit) or []:
        run_id = int(run.get("id") or 0)
        if run_id <= 0:
            continue
        for artifact in store.list_browser_session_artifacts(office_id, run_id=run_id) or []:
            marker = f"{run_id}:{artifact.get('id') or artifact.get('url') or artifact.get('path')}"
            if marker in seen:
                continue
            seen.add(marker)
            items.append(
                {
                    **artifact,
                    "run_id": run_id,
                    "run_goal": run.get("goal"),
                    "run_title": run.get("title"),
                    "run_status": run.get("status"),
                }
            )
            if len(items) >= artifact_limit:
                return items
    return items


def _consumer_signal_kind(*, provider: str, event_type: str, url: str) -> str:
    normalized_provider = str(provider or "").strip().lower()
    normalized_event_type = str(event_type or "").strip().lower()
    normalized_url = str(url or "").strip().lower()
    combined = " ".join([normalized_provider, normalized_event_type, normalized_url]).strip()
    if any(token in combined for token in ("youtube", "youtu", "video", "watch")):
        return "youtube_history"
    if any(token in combined for token in ("reading", "bookmark", "saved_link", "article", "makale")):
        return "reading_list"
    if any(token in combined for token in ("shop", "shopping", "market", "food", "meal", "grocery")):
        return "shopping_signal"
    if any(token in combined for token in ("travel", "trip", "route", "flight", "hotel", "booking")):
        return "travel_signal"
    if any(
        token in combined
        for token in (
            "weather",
            "forecast",
            "temperature",
            "rain",
            "umbrella",
            "hava",
            "yagmur",
            "yağmur",
            "ruzgar",
            "rüzgar",
            "sicak",
            "sıcak",
            "soguk",
            "soğuk",
        )
    ):
        return "weather_context"
    if any(
        token in combined
        for token in (
            "places",
            "place",
            "nearby",
            "maps",
            "map",
            "route_to_place",
            "cafe",
            "coffee",
            "kahve",
            "restaurant",
            "lokanta",
            "mosque",
            "cami",
            "market",
            "park",
            "museum",
            "yakın",
            "yakin",
        )
    ):
        return "place_interest"
    if any(
        token in combined
        for token in (
            "web",
            "website",
            "crawl",
            "inspection",
            "search",
            "research",
            "site",
            "article",
            "makale",
            "arastirma",
            "araştırma",
            "incele",
        )
    ):
        return "web_research_signal"
    return "consumer_signal"


def _consumer_signal_tags(kind: str) -> list[str]:
    base = ["consumer", "connector"]
    if kind == "youtube_history":
        return [*base, "youtube", "content"]
    if kind == "reading_list":
        return [*base, "reading", "links"]
    if kind == "shopping_signal":
        return [*base, "shopping", "food"]
    if kind == "travel_signal":
        return [*base, "travel"]
    if kind == "weather_context":
        return [*base, "weather", "planning"]
    if kind == "place_interest":
        return [*base, "places", "local_context"]
    if kind == "web_research_signal":
        return [*base, "research", "web"]
    return [*base, "lifestyle"]


def _claim_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _claim_hint(
    *,
    subject_key: str,
    predicate: str,
    value: Any,
    display_label: str,
    scope: str | None = None,
    retrieval_eligibility: str | None = None,
    consent_class: str | None = None,
    sensitive: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hint: dict[str, Any] = {
        "subject_key": str(subject_key).strip(),
        "predicate": str(predicate).strip(),
        "object_value_text": _claim_text(value),
        "display_label": str(display_label).strip(),
    }
    if scope:
        hint["scope"] = str(scope).strip()
    if retrieval_eligibility:
        hint["retrieval_eligibility"] = str(retrieval_eligibility).strip()
    if consent_class:
        hint["consent_class"] = str(consent_class).strip()
    if sensitive is not None:
        hint["sensitive"] = bool(sensitive)
    if metadata:
        hint["metadata"] = dict(metadata)
    return hint


def _safe_url_host(value: Any | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(urlparse(text).netloc or "").strip().lower()
    except Exception:
        return ""


def _consumer_activity_claim_hints(
    *,
    kind: str,
    source_ref: str,
    title: str,
    url: str,
    query: str,
    category: str,
    scope: str,
    sensitivity: str,
) -> list[dict[str, Any]]:
    retrieval_eligibility = "blocked" if str(sensitivity or "").strip().lower() in {"high", "restricted"} else "demoted"
    subject_key = f"activity:{kind}:{_json_fingerprint([source_ref, title, url, query, category])[:12]}"
    hints: list[dict[str, Any]] = []
    if query:
        hints.append(
            _claim_hint(
                subject_key=subject_key,
                predicate="query",
                value=query,
                display_label="Araştırma sorgusu",
                scope=scope,
                retrieval_eligibility=retrieval_eligibility,
                metadata={"signal_kind": kind, "claim_view": "recent_activity"},
            )
        )
    if title:
        hints.append(
            _claim_hint(
                subject_key=subject_key,
                predicate="topic_title",
                value=title,
                display_label="İçerik başlığı",
                scope=scope,
                retrieval_eligibility=retrieval_eligibility,
                metadata={"signal_kind": kind, "claim_view": "recent_activity"},
            )
        )
    if category:
        hints.append(
            _claim_hint(
                subject_key=subject_key,
                predicate="category",
                value=category,
                display_label="İçerik kategorisi",
                scope=scope,
                retrieval_eligibility=retrieval_eligibility,
                metadata={"signal_kind": kind, "claim_view": "recent_activity"},
            )
        )
    host = _safe_url_host(url)
    if host:
        hints.append(
            _claim_hint(
                subject_key=subject_key,
                predicate="url_host",
                value=host,
                display_label="Kaynak alan adı",
                scope=scope,
                retrieval_eligibility=retrieval_eligibility,
                metadata={"signal_kind": kind, "claim_view": "recent_activity"},
            )
        )
    return hints


class EmailThreadConnector:
    name = "email_threads"
    description = "Google/Outlook mirror edilen e-posta thread kayıtları."
    sync_mode = "mirror_pull"
    provider_hints = ("google", "outlook")

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        records: list[ConnectorRecord] = []
        for item in store.list_email_threads(office_id) or []:
            if not _channel_memory_claim_eligible(item):
                continue
            matter_id = item.get("matter_id")
            records.append(
                ConnectorRecord(
                    connector_name=self.name,
                    source_type="email",
                    title=str(item.get("subject") or "Email thread").strip() or "Email thread",
                    content=str(item.get("snippet") or item.get("subject") or "").strip(),
                    source_ref=f"email-thread:{item.get('provider')}:{item.get('thread_ref')}",
                    occurred_at=str(item.get("received_at") or item.get("updated_at") or "") or None,
                    tags=["email", "connector", "reply_needed" if item.get("reply_needed") else "informational"],
                    scope=_professional_scope(matter_id),
                    sensitivity="high",
                    exportability="local_only",
                    model_routing_hint="prefer_local",
                    metadata={
                        "participants": list(item.get("participants") or []),
                        "provider": item.get("provider"),
                        "thread_ref": item.get("thread_ref"),
                        "matter_id": matter_id,
                        "memory_state": _channel_memory_state(item),
                        "reply_needed": bool(item.get("reply_needed")),
                        "epistemic_claim_hints": [
                            _claim_hint(
                                subject_key=f"communication_thread:{item.get('provider')}:{item.get('thread_ref')}",
                                predicate="reply_needed",
                                value=bool(item.get("reply_needed")),
                                display_label="Yanıt bekliyor",
                            )
                        ],
                        "source_fingerprint": _json_fingerprint(
                            [
                                item.get("provider"),
                                item.get("thread_ref"),
                                item.get("subject"),
                                item.get("snippet"),
                                item.get("received_at"),
                                item.get("updated_at"),
                            ]
                        ),
                        "sync_timestamp": str(item.get("updated_at") or item.get("received_at") or ""),
                        "privacy_sensitivity": "high",
                    },
                )
            )
        return records


class CalendarConnector:
    name = "calendar_events"
    description = "Google/Outlook ve local planner takvim olayları."
    sync_mode = "mirror_pull"
    provider_hints = ("google", "outlook", "local")

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        records: list[ConnectorRecord] = []
        for item in store.list_calendar_events(office_id, limit=100) or []:
            matter_id = item.get("matter_id")
            attendees = list(item.get("attendees") or [])
            records.append(
                ConnectorRecord(
                    connector_name=self.name,
                    source_type="calendar",
                    title=str(item.get("title") or "Calendar event").strip() or "Calendar event",
                    content="; ".join(
                        part
                        for part in [
                            str(item.get("title") or "").strip(),
                            f"location={item.get('location')}" if item.get("location") else "",
                            f"attendees={', '.join(attendees)}" if attendees else "",
                        ]
                        if part
                    ),
                    source_ref=f"calendar:{item.get('provider')}:{item.get('external_id')}",
                    occurred_at=str(item.get("starts_at") or item.get("updated_at") or "") or None,
                    tags=["calendar", "connector", "needs_prep" if item.get("needs_preparation") else "scheduled"],
                    scope=_professional_scope(matter_id) if matter_id else "personal",
                    sensitivity="medium" if not matter_id else "high",
                    exportability="redaction_required" if not matter_id else "local_only",
                    model_routing_hint="redaction_required" if not matter_id else "prefer_local",
                    metadata={
                        "provider": item.get("provider"),
                        "external_id": item.get("external_id"),
                        "matter_id": matter_id,
                        "status": item.get("status"),
                        "location": item.get("location"),
                        "attendees": attendees,
                        "epistemic_claim_hints": [
                            _claim_hint(
                                subject_key=f"calendar_event:{item.get('provider')}:{item.get('external_id')}",
                                predicate="status",
                                value=str(item.get("status") or "confirmed"),
                                display_label="Takvim durumu",
                            ),
                            *(
                                [
                                    _claim_hint(
                                        subject_key=f"calendar_event:{item.get('provider')}:{item.get('external_id')}",
                                        predicate="location",
                                        value=str(item.get("location") or "").strip(),
                                        display_label="Takvim konumu",
                                    )
                                ]
                                if str(item.get("location") or "").strip()
                                else []
                            ),
                            _claim_hint(
                                subject_key=f"calendar_event:{item.get('provider')}:{item.get('external_id')}",
                                predicate="preparation_needed",
                                value=bool(item.get("needs_preparation")),
                                display_label="Hazırlık gerektiriyor",
                            ),
                        ],
                        "source_fingerprint": _json_fingerprint(
                            [
                                item.get("provider"),
                                item.get("external_id"),
                                item.get("title"),
                                item.get("starts_at"),
                                item.get("ends_at"),
                                item.get("updated_at"),
                            ]
                        ),
                        "sync_timestamp": str(item.get("updated_at") or item.get("starts_at") or ""),
                        "privacy_sensitivity": "medium" if not matter_id else "high",
                    },
                )
            )
        return records


class MessageConnector:
    name = "messages"
    description = "WhatsApp ve Telegram message mirror kayıtları."
    sync_mode = "mirror_pull"
    provider_hints = ("whatsapp", "telegram")

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        records: list[ConnectorRecord] = []
        providers = [
            ("whatsapp", store.list_whatsapp_messages(office_id, limit=100) or []),
            ("messages", store.list_telegram_messages(office_id, limit=100) or []),
        ]
        for source_type, items in providers:
            for item in items:
                if not _channel_memory_claim_eligible(item):
                    continue
                matter_id = item.get("matter_id")
                records.append(
                    ConnectorRecord(
                        connector_name=self.name,
                        source_type=source_type,
                        title=str(item.get("sender") or item.get("recipient") or "Message").strip() or "Message",
                        content=str(item.get("body") or "").strip(),
                        source_ref=f"{source_type}:{item.get('provider')}:{item.get('message_ref')}",
                        occurred_at=str(item.get("sent_at") or item.get("updated_at") or "") or None,
                        tags=[source_type, "connector", "reply_needed" if item.get("reply_needed") else "informational"],
                        scope=_professional_scope(matter_id) if matter_id else "personal",
                        sensitivity="high",
                        exportability="local_only",
                        model_routing_hint="prefer_local",
                        metadata={
                            "provider": item.get("provider"),
                            "conversation_ref": item.get("conversation_ref"),
                            "message_ref": item.get("message_ref"),
                            "direction": item.get("direction"),
                            "memory_state": _channel_memory_state(item),
                            "reply_needed": bool(item.get("reply_needed")),
                            "matter_id": matter_id,
                            "epistemic_claim_hints": [
                                _claim_hint(
                                    subject_key=f"conversation:{item.get('provider')}:{item.get('conversation_ref') or item.get('message_ref')}",
                                    predicate="reply_needed",
                                    value=bool(item.get("reply_needed")),
                                    display_label="Yanıt bekliyor",
                                ),
                                _claim_hint(
                                    subject_key=f"message:{item.get('provider')}:{item.get('message_ref')}",
                                    predicate="direction",
                                    value=str(item.get("direction") or "").strip() or "unknown",
                                    display_label="Mesaj yönü",
                                ),
                            ],
                            "source_fingerprint": _json_fingerprint(
                                [
                                    item.get("provider"),
                                    item.get("message_ref"),
                                    item.get("body"),
                                    item.get("sent_at"),
                                    item.get("updated_at"),
                                ]
                            ),
                            "sync_timestamp": str(item.get("updated_at") or item.get("sent_at") or ""),
                            "privacy_sensitivity": "high",
                        },
                    )
                )
        return records


class TaskConnector:
    name = "tasks"
    description = "Yerel görev ve reminder yüzeyi."
    sync_mode = "local_scan"
    provider_hints = ("local_productivity",)

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        records: list[ConnectorRecord] = []
        for item in store.list_office_tasks(office_id) or []:
            matter_id = item.get("matter_id")
            records.append(
                ConnectorRecord(
                    connector_name=self.name,
                    source_type="tasks",
                    title=str(item.get("title") or "Task").strip() or "Task",
                    content="; ".join(
                        part
                        for part in [
                            str(item.get("title") or "").strip(),
                            f"priority={item.get('priority')}" if item.get("priority") else "",
                            f"status={item.get('status')}" if item.get("status") else "",
                            str(item.get("explanation") or "").strip(),
                        ]
                        if part
                    ),
                    source_ref=f"task:{item.get('id')}",
                    occurred_at=str(item.get("updated_at") or item.get("created_at") or "") or None,
                    tags=["task", "connector", str(item.get("status") or "open")],
                    scope=_professional_scope(matter_id) if matter_id else "personal",
                    sensitivity="medium",
                    exportability="redaction_required",
                    model_routing_hint="redaction_required",
                    metadata={
                        "task_id": item.get("id"),
                        "matter_id": matter_id,
                        "priority": item.get("priority"),
                        "status": item.get("status"),
                        "recommended_by": item.get("recommended_by"),
                        "epistemic_claim_hints": [
                            _claim_hint(
                                subject_key=f"task:{item.get('id')}",
                                predicate="status",
                                value=str(item.get("status") or "open"),
                                display_label="Görev durumu",
                            ),
                            *(
                                [
                                    _claim_hint(
                                        subject_key=f"task:{item.get('id')}",
                                        predicate="priority",
                                        value=str(item.get("priority") or "").strip(),
                                        display_label="Görev önceliği",
                                    )
                                ]
                                if str(item.get("priority") or "").strip()
                                else []
                            ),
                        ],
                        "source_fingerprint": _json_fingerprint(
                            [
                                item.get("id"),
                                item.get("title"),
                                item.get("priority"),
                                item.get("status"),
                                item.get("updated_at"),
                            ]
                        ),
                        "sync_timestamp": str(item.get("updated_at") or item.get("created_at") or ""),
                        "privacy_sensitivity": "medium",
                    },
                )
            )
        return records


class NotesConnector:
    name = "matter_notes"
    description = "Matter note ve workspace note taraması."
    sync_mode = "local_scan"
    provider_hints = ("local_productivity",)

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        records: list[ConnectorRecord] = []
        for matter in store.list_matters(office_id) or []:
            matter_id = matter.get("id")
            for note in store.list_matter_notes(office_id, int(matter_id)) or []:
                records.append(
                    ConnectorRecord(
                        connector_name=self.name,
                        source_type="notes",
                        title=f"{matter.get('title') or 'Matter'} note",
                        content=str(note.get("body") or "").strip(),
                        source_ref=f"matter-note:{matter_id}:{note.get('id')}",
                        occurred_at=str(note.get("event_at") or note.get("created_at") or "") or None,
                        tags=["notes", "connector", str(note.get("note_type") or "matter_note")],
                        scope=f"project:matter-{matter_id}",
                        sensitivity="restricted",
                        exportability="local_only",
                        model_routing_hint="local_only",
                        metadata={
                            "matter_id": matter_id,
                            "matter_title": matter.get("title"),
                            "note_id": note.get("id"),
                            "note_type": note.get("note_type"),
                            "epistemic_claim_hints": [
                                *(
                                    [
                                        _claim_hint(
                                            subject_key=f"matter_note:{matter_id}:{note.get('id')}",
                                            predicate="note_type",
                                            value=str(note.get("note_type") or "").strip(),
                                            display_label="Not türü",
                                            scope=f"project:matter-{matter_id}",
                                        )
                                    ]
                                    if str(note.get("note_type") or "").strip()
                                    else []
                                )
                            ],
                            "source_fingerprint": _json_fingerprint(
                                [matter_id, note.get("id"), note.get("body"), note.get("event_at"), note.get("created_at")]
                            ),
                            "sync_timestamp": str(note.get("created_at") or note.get("event_at") or ""),
                            "privacy_sensitivity": "restricted",
                        },
                    )
                )
        return records


class FilesConnector:
    name = "documents"
    description = "Matter belgeleri ve Google Drive mirror dosyaları."
    sync_mode = "mirror_pull"
    provider_hints = ("google", "local_documents")

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        records: list[ConnectorRecord] = []
        for matter in store.list_matters(office_id) or []:
            matter_id = matter.get("id")
            for item in store.list_matter_documents(office_id, int(matter_id)) or []:
                records.append(
                    ConnectorRecord(
                        connector_name=self.name,
                        source_type="files",
                        title=str(item.get("display_name") or item.get("filename") or "Document").strip() or "Document",
                        content="; ".join(
                            part
                            for part in [
                                str(item.get("display_name") or item.get("filename") or "").strip(),
                                str(item.get("content_type") or "").strip(),
                                str(item.get("source_type") or "").strip(),
                            ]
                            if part
                        ),
                        source_ref=f"document:{matter_id}:{item.get('id')}",
                        occurred_at=str(item.get("updated_at") or item.get("created_at") or "") or None,
                        tags=["files", "connector", str(item.get("source_type") or "document")],
                        scope=f"project:matter-{matter_id}",
                        sensitivity="restricted",
                        exportability="local_only",
                        model_routing_hint="local_only",
                        metadata={
                            "matter_id": matter_id,
                            "document_id": item.get("id"),
                            "filename": item.get("filename"),
                            "content_type": item.get("content_type"),
                            "epistemic_claim_hints": [
                                *(
                                    [
                                        _claim_hint(
                                            subject_key=f"document:{matter_id}:{item.get('id')}",
                                            predicate="content_type",
                                            value=str(item.get("content_type") or "").strip(),
                                            display_label="Belge içerik türü",
                                            scope=f"project:matter-{matter_id}",
                                        )
                                    ]
                                    if str(item.get("content_type") or "").strip()
                                    else []
                                ),
                                *(
                                    [
                                        _claim_hint(
                                            subject_key=f"document:{matter_id}:{item.get('id')}",
                                            predicate="source_type",
                                            value=str(item.get("source_type") or "").strip(),
                                            display_label="Belge kaynak türü",
                                            scope=f"project:matter-{matter_id}",
                                        )
                                    ]
                                    if str(item.get("source_type") or "").strip()
                                    else []
                                ),
                            ],
                            "source_fingerprint": _json_fingerprint(
                                [matter_id, item.get("id"), item.get("filename"), item.get("checksum"), item.get("updated_at")]
                            ),
                            "sync_timestamp": str(item.get("updated_at") or item.get("created_at") or ""),
                            "privacy_sensitivity": "restricted",
                        },
                    )
                )
        for item in store.list_drive_files(office_id, limit=100) or []:
            records.append(
                ConnectorRecord(
                    connector_name=self.name,
                    source_type="files",
                    title=str(item.get("name") or "Drive file").strip() or "Drive file",
                    content="; ".join(
                        part for part in [str(item.get("name") or "").strip(), str(item.get("mime_type") or "").strip()] if part
                    ),
                    source_ref=f"drive-file:{item.get('provider')}:{item.get('external_id')}",
                    occurred_at=str(item.get("modified_at") or item.get("updated_at") or "") or None,
                    tags=["files", "connector", "drive"],
                    scope=_professional_scope(item.get("matter_id")) if item.get("matter_id") else "professional",
                    sensitivity="high",
                    exportability="local_only",
                    model_routing_hint="prefer_local",
                    metadata={
                        "provider": item.get("provider"),
                        "external_id": item.get("external_id"),
                        "matter_id": item.get("matter_id"),
                        "web_view_link": item.get("web_view_link"),
                        "epistemic_claim_hints": [
                            *(
                                [
                                    _claim_hint(
                                        subject_key=f"drive_file:{item.get('provider')}:{item.get('external_id')}",
                                        predicate="mime_type",
                                        value=str(item.get("mime_type") or "").strip(),
                                        display_label="Drive dosya türü",
                                        scope=_professional_scope(item.get("matter_id")) if item.get("matter_id") else "professional",
                                    )
                                ]
                                if str(item.get("mime_type") or "").strip()
                                else []
                            )
                        ],
                        "source_fingerprint": _json_fingerprint(
                            [item.get("provider"), item.get("external_id"), item.get("name"), item.get("modified_at")]
                        ),
                        "sync_timestamp": str(item.get("modified_at") or item.get("updated_at") or ""),
                        "privacy_sensitivity": "high",
                    },
                )
            )
        return records


class LocationConnector:
    name = "location_events"
    description = "Kullanıcı profili, takvim lokasyonları ve local context üzerinden lokasyon/place sinyali."
    sync_mode = "local_context_scan"
    provider_hints = ("location", "google", "outlook", "local_productivity")

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        profile = store.get_user_profile(office_id) or {}
        records: list[ConnectorRecord] = []

        current_location = str(profile.get("current_location") or "").strip()
        if current_location:
            records.append(
                ConnectorRecord(
                    connector_name=self.name,
                    source_type="location_events",
                    title=f"Current place: {current_location}",
                    content="; ".join(
                        part
                        for part in [
                            current_location,
                            str(profile.get("location_preferences") or "").strip(),
                            str(profile.get("maps_preference") or "").strip(),
                        ]
                        if part
                    ),
                    source_ref=f"location-profile:current:{_infer_place_category(current_location)}:{current_location}",
                    occurred_at=str(profile.get("updated_at") or "") or None,
                    tags=["location", "profile_hint", _infer_place_category(current_location)],
                    scope="personal",
                    sensitivity="high",
                    exportability="local_only",
                    model_routing_hint="prefer_local",
                    metadata={
                        "category": _infer_place_category(current_location),
                        "area": current_location,
                        "epistemic_claim_hints": [
                            _claim_hint(
                                subject_key="user",
                                predicate="current_place",
                                value=current_location,
                                display_label="Güncel yer",
                                retrieval_eligibility="blocked",
                                sensitive=True,
                            ),
                            _claim_hint(
                                subject_key=f"place:{_infer_place_category(current_location)}:{_json_fingerprint(current_location)[:8]}",
                                predicate="category",
                                value=_infer_place_category(current_location),
                                display_label="Yer kategorisi",
                            ),
                        ],
                        "source_fingerprint": _json_fingerprint(
                            [
                                "profile_current_location",
                                current_location,
                                profile.get("location_preferences"),
                                profile.get("maps_preference"),
                                profile.get("updated_at"),
                            ]
                        ),
                        "sync_timestamp": str(profile.get("updated_at") or ""),
                        "privacy_sensitivity": "high",
                        "provider": "profile",
                    },
                )
            )

        home_base = str(profile.get("home_base") or "").strip()
        if home_base:
            records.append(
                ConnectorRecord(
                    connector_name=self.name,
                    source_type="location_events",
                    title=f"Home base: {home_base}",
                    content="Kullanıcının temel dönüş noktası veya ev/eşdeğer lokasyon ipucu.",
                    source_ref=f"location-profile:home:{home_base}",
                    occurred_at=str(profile.get("updated_at") or "") or None,
                    tags=["location", "home_base", _infer_place_category(home_base)],
                    scope="personal",
                    sensitivity="high",
                    exportability="local_only",
                    model_routing_hint="prefer_local",
                    metadata={
                        "category": _infer_place_category(home_base),
                        "area": home_base,
                        "epistemic_claim_hints": [
                            _claim_hint(
                                subject_key="user",
                                predicate="home_base",
                                value=home_base,
                                display_label="Temel dönüş noktası",
                                retrieval_eligibility="blocked",
                                sensitive=True,
                            ),
                            _claim_hint(
                                subject_key=f"place:{_infer_place_category(home_base)}:{_json_fingerprint(home_base)[:8]}",
                                predicate="category",
                                value=_infer_place_category(home_base),
                                display_label="Yer kategorisi",
                            ),
                        ],
                        "source_fingerprint": _json_fingerprint(["profile_home_base", home_base, profile.get("updated_at")]),
                        "sync_timestamp": str(profile.get("updated_at") or ""),
                        "privacy_sensitivity": "high",
                        "provider": "profile",
                    },
                )
            )

        location_preferences = str(profile.get("location_preferences") or "").strip()
        if location_preferences:
            records.append(
                ConnectorRecord(
                    connector_name=self.name,
                    source_type="location_events",
                    title="Location preference signal",
                    content=location_preferences,
                    source_ref=f"location-profile:preference:{_json_fingerprint(location_preferences)[:12]}",
                    occurred_at=str(profile.get("updated_at") or "") or None,
                    tags=["location", "preferences"],
                    scope="personal",
                    sensitivity="medium",
                    exportability="redaction_required",
                    model_routing_hint="redaction_required",
                    metadata={
                        "source_fingerprint": _json_fingerprint(["profile_location_preferences", location_preferences, profile.get("updated_at")]),
                        "sync_timestamp": str(profile.get("updated_at") or ""),
                        "privacy_sensitivity": "medium",
                        "provider": "profile",
                        "epistemic_claim_hints": [
                            _claim_hint(
                                subject_key="user",
                                predicate="location_preferences",
                                value=location_preferences,
                                display_label="Mekân tercihleri",
                            )
                        ],
                    },
                )
            )

        for item in store.list_calendar_events(office_id, limit=40) or []:
            location = str(item.get("location") or "").strip()
            if not location:
                continue
            matter_id = item.get("matter_id")
            category = _infer_place_category(location)
            records.append(
                ConnectorRecord(
                    connector_name=self.name,
                    source_type="location_events",
                    title=str(item.get("title") or "Calendar location").strip() or "Calendar location",
                    content="; ".join(
                        part
                        for part in [
                            location,
                            f"provider={item.get('provider')}" if item.get("provider") else "",
                            f"category={category}",
                        ]
                        if part
                    ),
                    source_ref=f"location-calendar:{item.get('provider')}:{item.get('external_id')}",
                    occurred_at=str(item.get("starts_at") or item.get("updated_at") or "") or None,
                    tags=["location", "calendar", category],
                    scope=_professional_scope(matter_id) if matter_id else "personal",
                    sensitivity="high" if matter_id else "medium",
                    exportability="local_only" if matter_id else "redaction_required",
                    model_routing_hint="prefer_local" if matter_id else "redaction_required",
                    metadata={
                        "provider": item.get("provider"),
                        "external_id": item.get("external_id"),
                        "matter_id": matter_id,
                        "location": location,
                        "category": category,
                        "epistemic_claim_hints": [
                            _claim_hint(
                                subject_key=f"calendar_event:{item.get('provider')}:{item.get('external_id')}",
                                predicate="location",
                                value=location,
                                display_label="Takvim konumu",
                            ),
                            _claim_hint(
                                subject_key=f"place:{category}:{_json_fingerprint(location)[:8]}",
                                predicate="category",
                                value=category,
                                display_label="Yer kategorisi",
                            ),
                        ],
                        "source_fingerprint": _json_fingerprint(
                            [
                                "calendar_location",
                                item.get("provider"),
                                item.get("external_id"),
                                location,
                                item.get("starts_at"),
                                item.get("updated_at"),
                            ]
                        ),
                        "sync_timestamp": str(item.get("updated_at") or item.get("starts_at") or ""),
                        "privacy_sensitivity": "high" if matter_id else "medium",
                    },
                )
            )

        if records:
            return records

        return [
            ConnectorRecord(
                connector_name=self.name,
                source_type="location_events",
                title="Location signal unavailable",
                content="Henüz current place veya lokasyon tercihi verisi yok. Konum sağlayıcısı bağlandığında bu connector gerçek kayıt üretecek.",
                source_ref="location:empty-state",
                occurred_at=None,
                tags=["location", "empty_state"],
                scope="personal",
                sensitivity="medium",
                exportability="redaction_required",
                model_routing_hint="redaction_required",
                metadata={
                    "empty_state": True,
                    "source_fingerprint": "location-empty-state-v2",
                    "sync_timestamp": "empty_state",
                    "privacy_sensitivity": "medium",
                    "provider": "profile",
                },
            )
        ]


class ElasticIntegrationConnector:
    name = "elastic_managed_resources"
    description = "Platform entegrasyon katmaninda yonetilen Elastic kaynaklarinin bilgi tabani aynasi."
    sync_mode = "integration_mirror"
    provider_hints = ("elastic", "elasticsearch", "platform")

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        repository = IntegrationRepository(Path(store.db_path))
        records: list[ConnectorRecord] = []
        for connection in repository.list_connections(office_id, connector_id="elastic"):
            if not bool(connection.get("enabled", True)):
                continue
            if str(connection.get("status") or "").strip().lower() in {"revoked", "disconnected", "blocked"}:
                continue
            connection_id = int(connection.get("id") or 0)
            if connection_id <= 0:
                continue
            for item in repository.list_resources(office_id, connection_id, limit=200):
                body_text = str(item.get("body_text") or item.get("search_text") or "").strip()
                title = str(item.get("title") or item.get("external_id") or "Elastic document").strip() or "Elastic document"
                attributes = dict(item.get("attributes") or {})
                metadata = {
                    "connector_id": "elastic",
                    "connection_id": connection_id,
                    "resource_kind": item.get("resource_kind"),
                    "external_id": item.get("external_id"),
                    "owner_label": item.get("owner_label") or connection.get("display_name"),
                    "index": attributes.get("index"),
                    "score": attributes.get("score"),
                    "source_url": item.get("source_url"),
                    "epistemic_claim_hints": [
                        _claim_hint(
                            subject_key=f"elastic_resource:{connection_id}:{item.get('resource_kind')}:{item.get('external_id')}",
                            predicate="resource_kind",
                            value=str(item.get("resource_kind") or "document"),
                            display_label="Elastic kaynak türü",
                            scope="professional",
                        ),
                        *(
                            [
                                _claim_hint(
                                    subject_key=f"elastic_resource:{connection_id}:{item.get('resource_kind')}:{item.get('external_id')}",
                                    predicate="index",
                                    value=str(attributes.get("index") or "").strip(),
                                    display_label="Elastic indeks",
                                    scope="professional",
                                )
                            ]
                            if str(attributes.get("index") or "").strip()
                            else []
                        ),
                    ],
                    "source_fingerprint": _json_fingerprint(
                        [
                            connection_id,
                            item.get("resource_kind"),
                            item.get("external_id"),
                            item.get("checksum"),
                            item.get("modified_at"),
                            item.get("updated_at"),
                        ]
                    ),
                    "sync_timestamp": str(item.get("synced_at") or item.get("updated_at") or ""),
                    "privacy_sensitivity": "medium",
                }
                tags = ["elastic", "connector", str(item.get("resource_kind") or "document")]
                index_name = str(attributes.get("index") or "").strip()
                if index_name:
                    tags.append(index_name)
                records.append(
                    ConnectorRecord(
                        connector_name=self.name,
                        source_type="elastic_document",
                        title=title,
                        content=body_text or title,
                        source_ref=f"elastic:{connection_id}:{item.get('resource_kind')}:{item.get('external_id')}",
                        metadata=metadata,
                        occurred_at=str(item.get("modified_at") or item.get("occurred_at") or item.get("updated_at") or "") or None,
                        tags=tags,
                        scope="professional",
                        sensitivity="medium",
                        exportability="redaction_required",
                        model_routing_hint="redaction_required",
                    )
                )
        return records


class BrowserContextConnector:
    name = "browser_context"
    description = "Tarayıcı session artifact'ları ve okuma/link bağlamı."
    sync_mode = "local_scan"
    provider_hints = ("browser", "reading_list", "web")

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        records: list[ConnectorRecord] = []
        for artifact in _recent_browser_artifacts(store, office_id):
            metadata = dict(artifact.get("metadata") or {})
            url = str(artifact.get("url") or metadata.get("url") or "").strip()
            title = str(
                metadata.get("title")
                or metadata.get("page_title")
                or metadata.get("query")
                or artifact.get("artifact_type")
                or "Browser context"
            ).strip() or "Browser context"
            if not url and not title:
                continue
            kind = _consumer_signal_kind(
                provider="browser",
                event_type=str(artifact.get("artifact_type") or ""),
                url=url,
            )
            summary_parts = [
                title,
                url,
                str(metadata.get("query") or "").strip(),
                str(artifact.get("run_goal") or "").strip(),
            ]
            scope = str(metadata.get("scope") or "personal").strip() or "personal"
            sensitivity = str(metadata.get("sensitivity") or "medium").strip() or "medium"
            claim_hints = _consumer_activity_claim_hints(
                kind=kind,
                source_ref=f"browser-artifact:{artifact.get('run_id')}:{artifact.get('id') or artifact.get('artifact_type')}",
                title=title,
                url=url,
                query=str(metadata.get("query") or "").strip(),
                category=str(metadata.get("category") or "").strip(),
                scope=scope,
                sensitivity=sensitivity,
            )
            records.append(
                ConnectorRecord(
                    connector_name=self.name,
                    source_type=kind,
                    title=title,
                    content="; ".join(part for part in summary_parts if part),
                    source_ref=f"browser-artifact:{artifact.get('run_id')}:{artifact.get('id') or artifact.get('artifact_type')}",
                    occurred_at=str(artifact.get("created_at") or "") or None,
                    tags=_consumer_signal_tags(kind),
                    scope=scope,
                    sensitivity="high" if sensitivity in {"high", "restricted"} else "medium",
                    exportability="redaction_required",
                    model_routing_hint="redaction_required",
                    metadata={
                        "artifact_type": artifact.get("artifact_type"),
                        "url": url,
                        "path": artifact.get("path"),
                        "run_id": artifact.get("run_id"),
                        "run_goal": artifact.get("run_goal"),
                        "run_title": artifact.get("run_title"),
                        "provider": "browser",
                        "signal_topic": kind,
                        "epistemic_claim_hints": claim_hints,
                        "source_fingerprint": _json_fingerprint(
                            [
                                "browser_artifact",
                                artifact.get("run_id"),
                                artifact.get("id"),
                                artifact.get("artifact_type"),
                                url,
                                metadata.get("query"),
                                artifact.get("created_at"),
                            ]
                        ),
                        "sync_timestamp": str(artifact.get("created_at") or ""),
                        "privacy_sensitivity": "medium" if sensitivity not in {"high", "restricted"} else "high",
                    },
                )
            )
        return records


class ConsumerSignalsConnector:
    name = "consumer_signals"
    description = "YouTube, okuma listesi, shopping/travel ve web-weather-places benzeri consumer context sinyalleri."
    sync_mode = "local_scan"
    provider_hints = ("youtube", "shopping", "travel", "weather", "places", "web", "consumer")

    def collect(self, *, store: Any, office_id: str) -> list[ConnectorRecord]:
        if not hasattr(store, "list_external_events"):
            return []
        records: list[ConnectorRecord] = []
        for item in store.list_external_events(office_id, limit=120) or []:
            provider = str(item.get("provider") or "").strip()
            event_type = str(item.get("event_type") or "").strip()
            metadata = dict(item.get("metadata") or {})
            url = str(metadata.get("url") or metadata.get("source_url") or "").strip()
            kind = _consumer_signal_kind(provider=provider, event_type=event_type, url=url)
            if kind == "consumer_signal" and provider not in {"browser", "youtube", "travel", "shopping", "weather", "places", "web", "consumer"}:
                continue
            title = str(item.get("title") or item.get("actor_label") or kind.replace("_", " ")).strip() or kind.replace("_", " ")
            summary_parts = [
                str(item.get("summary") or "").strip(),
                url,
                str(metadata.get("query") or "").strip(),
                str(metadata.get("category") or "").strip(),
            ]
            scope = str(metadata.get("scope") or "personal").strip() or "personal"
            sensitivity = str(metadata.get("sensitivity") or "medium").strip() or "medium"
            claim_hints = _consumer_activity_claim_hints(
                kind=kind,
                source_ref=f"external-event:{provider}:{event_type}:{item.get('external_ref') or item.get('id')}",
                title=title,
                url=url,
                query=str(metadata.get("query") or "").strip(),
                category=str(metadata.get("category") or "").strip(),
                scope=scope,
                sensitivity=sensitivity,
            )
            records.append(
                ConnectorRecord(
                    connector_name=self.name,
                    source_type=kind,
                    title=title,
                    content="; ".join(part for part in summary_parts if part),
                    source_ref=f"external-event:{provider}:{event_type}:{item.get('external_ref') or item.get('id')}",
                    occurred_at=str(item.get("source_created_at") or item.get("updated_at") or item.get("created_at") or "") or None,
                    tags=_consumer_signal_tags(kind),
                    scope=scope,
                    sensitivity="high" if sensitivity in {"high", "restricted"} else "medium",
                    exportability="redaction_required",
                    model_routing_hint="redaction_required",
                    metadata={
                        "provider": provider,
                        "event_type": event_type,
                        "external_ref": item.get("external_ref"),
                        "importance": item.get("importance"),
                        "reply_needed": bool(item.get("reply_needed")),
                        "signal_topic": kind,
                        "epistemic_claim_hints": claim_hints,
                        "source_fingerprint": _json_fingerprint(
                            [
                                provider,
                                event_type,
                                item.get("external_ref"),
                                item.get("title"),
                                item.get("summary"),
                                item.get("source_created_at"),
                            ]
                        ),
                        "sync_timestamp": str(item.get("updated_at") or item.get("source_created_at") or item.get("created_at") or ""),
                        "privacy_sensitivity": "medium" if sensitivity not in {"high", "restricted"} else "high",
                    },
                )
            )
        return records


def build_default_connector_registry() -> list[KnowledgeConnector]:
    return [
        EmailThreadConnector(),
        CalendarConnector(),
        MessageConnector(),
        NotesConnector(),
        TaskConnector(),
        FilesConnector(),
        LocationConnector(),
        BrowserContextConnector(),
        ConsumerSignalsConnector(),
        ElasticIntegrationConnector(),
    ]
