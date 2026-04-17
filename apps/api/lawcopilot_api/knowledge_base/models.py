from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PAGE_RECORD_TYPES: dict[str, str] = {
    "persona": "person",
    "preferences": "preference",
    "routines": "routine",
    "contacts": "person",
    "projects": "project",
    "legal": "legal_matter",
    "places": "place",
    "decisions": "decision",
    "reflections": "reflection",
    "recommendations": "recommendation",
}

SUPPORTED_RECORD_TYPES = (
    "person",
    "place",
    "preference",
    "routine",
    "project",
    "goal",
    "constraint",
    "task",
    "event",
    "conversation_style",
    "recommendation",
    "decision",
    "source",
    "legal_matter",
    "obligation",
    "reflection",
    "knowledge_article",
    "insight",
)

DEFAULT_PAGE_SCOPES: dict[str, str] = {
    "persona": "personal",
    "preferences": "personal",
    "routines": "personal",
    "contacts": "global",
    "projects": "professional",
    "legal": "professional",
    "places": "personal",
    "decisions": "global",
    "reflections": "global",
    "recommendations": "global",
}

DEFAULT_PAGE_SENSITIVITY: dict[str, str] = {
    "persona": "high",
    "preferences": "high",
    "routines": "medium",
    "contacts": "high",
    "projects": "medium",
    "legal": "restricted",
    "places": "medium",
    "decisions": "medium",
    "reflections": "medium",
    "recommendations": "medium",
}

EXPORTABILITY_BY_SENSITIVITY: dict[str, str] = {
    "low": "cloud_allowed",
    "medium": "redaction_required",
    "high": "local_only",
    "restricted": "local_only",
}

MODEL_ROUTING_BY_SENSITIVITY: dict[str, str] = {
    "low": "cloud_allowed",
    "medium": "redaction_required",
    "high": "prefer_local",
    "restricted": "local_only",
}

SHAREABILITY_BY_SCOPE: dict[str, str] = {
    "personal": "private",
    "professional": "workspace_shareable",
    "global": "shareable",
}

RELATION_TYPES = (
    "prefers",
    "avoids",
    "related_to",
    "supersedes",
    "contradicts",
    "inferred_from",
    "relevant_to",
    "scoped_to",
    "supports",
    "requires_confirmation",
)


@dataclass
class KnowledgeRelation:
    relation_type: str
    target: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeSearchHit:
    page_key: str
    record_id: str
    title: str
    summary: str
    score: float
    record_type: str
    scope: str
    sensitivity: str
    exportability: str
    model_routing_hint: str
    source_refs: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str | None = None
    selection_reasons: list[str] = field(default_factory=list)


@dataclass
class ResolvedKnowledgeContext:
    query: str
    summary_lines: list[str]
    claim_summary_lines: list[str] = field(default_factory=list)
    supporting_pages: list[dict[str, Any]] = field(default_factory=list)
    supporting_records: list[dict[str, Any]] = field(default_factory=list)
    supporting_concepts: list[dict[str, Any]] = field(default_factory=list)
    knowledge_articles: list[dict[str, Any]] = field(default_factory=list)
    decision_records: list[dict[str, Any]] = field(default_factory=list)
    reflections: list[dict[str, Any]] = field(default_factory=list)
    recent_related_feedback: list[dict[str, Any]] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    record_type_counts: dict[str, int] = field(default_factory=dict)
    supporting_relations: list[dict[str, Any]] = field(default_factory=list)
    resolved_claims: list[dict[str, Any]] = field(default_factory=list)
