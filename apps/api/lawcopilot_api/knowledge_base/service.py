from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from itertools import combinations
import json
import math
import re
from pathlib import Path
import threading
from typing import Any

from ..assistant_core import assistant_operating_contract, build_assistant_core_status, normalize_assistant_forms, normalize_behavior_contract
from ..epistemic.lint import build_epistemic_lint_report
from ..epistemic import resolve_predicate_family
from ..policies import evaluate_execution_gateway, resolve_proactive_policy
from .connectors import ConnectorRecord, build_default_connector_registry
from .location import FileBackedLocationProvider, MockLocationProvider
from .models import (
    DEFAULT_PAGE_SCOPES,
    DEFAULT_PAGE_SENSITIVITY,
    EXPORTABILITY_BY_SENSITIVITY,
    MODEL_ROUTING_BY_SENSITIVITY,
    PAGE_RECORD_TYPES,
    ResolvedKnowledgeContext,
    SHAREABILITY_BY_SCOPE,
)
from .retrieval import RetrievalQuery
from .retrieval_factory import build_retrieval_backend


PAGE_SPECS: dict[str, str] = {
    "persona": "Kullanıcının ve asistanın kimliği, ton beklentisi ve davranış çerçevesi.",
    "preferences": "Açık ya da güçlü sinyallerle desteklenen tercih kayıtları.",
    "routines": "Tekrarlayan alışkanlıklar, zaman duyarlılıkları ve heartbeat notları.",
    "contacts": "Önemli kişiler, ilişkiler ve iletişim bağlamı.",
    "projects": "Aktif işler, bağlam kümeleri ve açık takip alanları.",
    "legal": "Hukuki dosya ve konu özetleri.",
    "places": "Yer, lokasyon ve bağlamsal mekan notları.",
    "decisions": "Öneri ve otomasyon karar kayıtlarının özet dizini.",
    "reflections": "Health check, çelişki ve kalite gözlemleri.",
    "recommendations": "Öneri geçmişi, geri bildirim ve relevance gating kayıtları.",
}

SYSTEM_FILE_ORDER = ("AGENTS.md", "SCHEMA.md", "CONTROL.md", "INDEX.md", "LOG.md", "RULES.md")
SUPPORTED_RAW_TYPES = {
    "email",
    "calendar",
    "messages",
    "whatsapp",
    "notes",
    "files",
    "pdf",
    "places",
    "location_events",
    "web_snippets",
    "user_preferences",
    "tasks",
    "reminders",
    "legal_docs",
    "decision",
    "recommendation_feedback",
    "assistant_message_feedback",
    "profile_snapshot",
    "assistant_runtime_snapshot",
    "assistant_action",
    "approval_event",
    "assistant_file_back",
    "browser_context",
    "consumer_signal",
    "youtube_history",
    "reading_list",
    "shopping_signal",
    "travel_signal",
}
PROACTIVE_HOOKS = {
    "email_reply_draft",
    "message_draft",
    "smart_reminder",
    "place_recommendation",
    "food_suggestion",
    "travel_transport_suggestion",
    "calendar_nudge",
    "daily_plan",
}
PROACTIVE_TRIGGER_TYPES = {
    "time_based",
    "calendar_load",
    "incoming_communication",
    "routine_deviation",
    "missed_obligation",
    "location_context",
    "inactivity_follow_up",
    "daily_planning",
    "end_of_day_reflection",
}
HUMAN_CONTROLLED_SIGNALS = {
    "explicit_user_correction",
    "explicit_profile",
    "explicit_runtime_profile",
    "manual_ingest",
    "manual_location_context",
}
RISK_POLICY_MATRIX = {
    "read_summary": {"level": "A", "label": "read_only", "requires_confirmation": False, "auto_allowed": True},
    "draft_message": {"level": "A", "label": "read_only", "requires_confirmation": False, "auto_allowed": True},
    "send_email": {"level": "B", "label": "ask_before_acting", "requires_confirmation": True, "auto_allowed": False},
    "send_message": {"level": "B", "label": "ask_before_acting", "requires_confirmation": True, "auto_allowed": False},
    "reserve_travel": {"level": "B", "label": "ask_before_acting", "requires_confirmation": True, "auto_allowed": False},
    "update_local_memory": {"level": "C", "label": "low_risk_automatic", "requires_confirmation": False, "auto_allowed": True},
    "create_task_draft": {"level": "C", "label": "low_risk_automatic", "requires_confirmation": False, "auto_allowed": True},
    "spend_money": {"level": "D", "label": "never_auto", "requires_confirmation": True, "auto_allowed": False},
    "legal_commitment": {"level": "D", "label": "never_auto", "requires_confirmation": True, "auto_allowed": False},
}
STALENESS_WINDOWS = {
    "persona": 180,
    "preferences": 180,
    "routines": 60,
    "contacts": 180,
    "projects": 45,
    "legal": 90,
    "places": 120,
    "decisions": 45,
    "recommendations": 21,
}
CONNECTOR_PROVIDER_MAP = {
    "google": ["email_threads", "calendar_events", "documents"],
    "outlook": ["email_threads", "calendar_events"],
    "whatsapp": ["messages"],
    "telegram": ["messages"],
    "local_productivity": ["tasks", "matter_notes"],
    "local_documents": ["documents"],
    "location": ["location_events"],
}
TRIGGER_COOLDOWN_MINUTES = {
    "time_based": 180,
    "calendar_load": 240,
    "incoming_communication": 180,
    "routine_deviation": 360,
    "missed_obligation": 240,
    "location_context": 180,
    "inactivity_follow_up": 360,
    "daily_planning": 360,
    "end_of_day_reflection": 720,
}
FEEDBACK_RELATIONSHIP_HINTS: dict[str, dict[str, str | tuple[str, ...]]] = {
    "anne": {"id": "mother", "name": "Anne", "relationship": "anne", "aliases": ("anne", "annem", "anam")},
    "baba": {"id": "father", "name": "Baba", "relationship": "baba", "aliases": ("baba", "babam")},
    "es": {"id": "partner", "name": "Eş", "relationship": "eş", "aliases": ("eş", "esim", "eşim", "partner", "karim", "kocam")},
    "sevgili": {"id": "partner", "name": "Sevgili", "relationship": "sevgili", "aliases": ("sevgili", "kiz arkadasim", "erkek arkadasim")},
    "kardes": {"id": "sibling", "name": "Kardeş", "relationship": "kardeş", "aliases": ("kardes", "kardeş", "ablam", "abim", "ablam", "abim")},
    "cocuk": {"id": "child", "name": "Çocuk", "relationship": "çocuk", "aliases": ("oglum", "oğlum", "kizim", "kızım", "cocugum", "çocuğum")},
    "arkadas": {"id": "friend", "name": "Arkadaş", "relationship": "arkadaş", "aliases": ("arkadas", "arkadaş", "dostum")},
}
FEEDBACK_STYLE_SIGNAL_MAP: dict[str, tuple[str, ...]] = {
    "warm": ("sicak", "sıcak", "samimi", "icten", "içten", "sefkatli", "şefkatli", "sevgi dolu"),
    "polite": ("nazik", "kibar", "ince", "saygili", "saygılı"),
    "formal": ("resmi", "profesyonel", "kurumsal", "mesafeli"),
    "concise": ("kisa", "kısa", "net", "ozet", "özet"),
    "detailed": ("detayli", "detaylı", "ayrintili", "ayrıntılı", "gerekceli", "gerekçeli"),
}
FEEDBACK_ITEM_SIGNAL_MAP: dict[str, tuple[str, ...]] = {
    "cikolata": ("cikolata", "çikolata"),
    "cicek": ("cicek", "çiçek"),
    "kitap": ("kitap",),
    "kahve": ("kahve",),
    "tatli": ("tatli", "tatlı", "dessert", "tatlılar"),
    "yemek": ("yemek", "aksam yemegi", "akşam yemeği"),
}
FEEDBACK_NEGATION_HINTS = (
    "sevmez",
    "sevmiyor",
    "istemez",
    "istemiyor",
    "hoslanmaz",
    "hoşlanmaz",
    "uygun degil",
    "uygun değil",
    "olmasin",
    "olmasın",
    "alma",
    "almayalim",
    "almayalım",
    "istemiyorum",
    "yanlis",
    "yanlış",
)
FEEDBACK_STYLE_CONTEXT_HINTS = ("uslup", "üslup", "ton", "dil", "mesaj", "yazis", "yazış", "yazi", "yazı")
FEEDBACK_GIFT_CONTEXT_HINTS = ("hediye", "fikir", "oner", "öner", "surpriz", "sürpriz", "gotur", "götür", "alalim", "alalım")
FEEDBACK_DERIVED_BEHAVIOR_FIELDS = ("explanation_style", "planning_depth", "initiative_level", "follow_up_style")
FEEDBACK_PROFILE_PREFIXES = ("İletişim:", "Hediye:")
FEEDBACK_PROFILE_NOTE_PREFIX = "Assistant feedback öğrenimi:"
USER_FEEDBACK_NOTE_PREFIXES = ("Yanıt tarzı:", "Takip tarzı:", "Planlama desteği:")
CONSUMER_TOPIC_RULES: dict[str, dict[str, Any]] = {
    "habit_systems": {
        "aliases": (
            "habit",
            "habits",
            "routine",
            "routines",
            "morning routine",
            "habit stacking",
            "discipline",
            "productivity",
            "focus",
            "deep work",
            "aliskanlik",
            "alışkanlık",
            "rutin",
            "verimlilik",
            "sabah rutini",
        ),
        "page_key": "routines",
        "record_type": "routine",
        "field": "consumer_interest:habit_systems",
        "title": "Alışkanlık ve sistem kurma ilgisi",
        "summary": "Kullanıcı alışkanlık, sistem kurma ve üretkenlik içeriklerine tekrar dönüyor; koçluk ve takip yardımı bu yapıya yaslanmalı.",
        "relations": [
            {"relation_type": "supports", "target": "daily_planning"},
            {"relation_type": "supports", "target": "coaching"},
        ],
    },
    "reading_learning": {
        "aliases": (
            "reading",
            "book",
            "books",
            "article",
            "articles",
            "learning",
            "learn",
            "course",
            "research",
            "okuma",
            "kitap",
            "makale",
            "öğren",
            "ogren",
            "bookmark",
            "saved link",
        ),
        "page_key": "preferences",
        "record_type": "preference",
        "field": "consumer_interest:reading_learning",
        "title": "Okuma ve öğrenme ilgisi",
        "summary": "Kullanıcı okuma, öğrenme ve bilgi derleme içeriklerine düzenli ilgi gösteriyor; okuma hedefleri ve bilgi özetleri bu eksende sunulabilir.",
        "relations": [
            {"relation_type": "supports", "target": "reading_goal"},
            {"relation_type": "supports", "target": "knowledge_capture"},
        ],
    },
    "fitness_wellbeing": {
        "aliases": (
            "fitness",
            "workout",
            "gym",
            "run",
            "running",
            "walk",
            "walking",
            "health",
            "wellbeing",
            "wellness",
            "sleep",
            "yoga",
            "meditation",
            "spor",
            "yuruyus",
            "yürüyüş",
            "saglik",
            "sağlık",
            "enerji",
            "nefes",
            "meditasyon",
        ),
        "page_key": "preferences",
        "record_type": "preference",
        "field": "consumer_interest:fitness_wellbeing",
        "title": "Sağlık ve enerji ilgisi",
        "summary": "Kullanıcı hareket, enerji ve wellbeing içeriklerine ilgi gösteriyor; plan ve hatırlatmalar bu ritmi gözetmeli.",
        "relations": [
            {"relation_type": "supports", "target": "energy_rhythm"},
            {"relation_type": "supports", "target": "coaching"},
        ],
    },
    "food_light_meal": {
        "aliases": (
            "recipe",
            "meal",
            "meals",
            "light meal",
            "healthy food",
            "grocery",
            "market",
            "shopping",
            "food",
            "alışveriş",
            "alisveris",
            "yemek",
            "hafif yemek",
            "salata",
            "corba",
            "çorba",
            "market",
        ),
        "page_key": "preferences",
        "record_type": "preference",
        "field": "consumer_interest:food_light_meal",
        "title": "Yemek ve hafif öğün sinyali",
        "summary": "Kullanıcı hafif öğün, market ve pratik yemek sinyalleri bırakıyor; yemek önerileri bunu gözetmeli.",
        "relations": [
            {"relation_type": "supports", "target": "food_suggestion"},
            {"relation_type": "relevant_to", "target": "shopping_prep"},
        ],
    },
    "travel_exploration": {
        "aliases": (
            "travel",
            "trip",
            "route",
            "navigation",
            "train",
            "metro",
            "flight",
            "hotel",
            "booking",
            "seyahat",
            "gezi",
            "rota",
            "tren",
            "ulasim",
            "ulaşım",
            "otel",
            "ucus",
            "uçuş",
        ),
        "page_key": "preferences",
        "record_type": "preference",
        "field": "consumer_interest:travel_exploration",
        "title": "Seyahat ve rota ilgisi",
        "summary": "Kullanıcı seyahat, rota ve ulaşım içeriklerine ilgi gösteriyor; yolculuk ve plan önerileri buna göre şekillenmeli.",
        "relations": [
            {"relation_type": "supports", "target": "travel_transport_suggestion"},
            {"relation_type": "relevant_to", "target": "place_recommendation"},
        ],
    },
    "weather_planning": {
        "aliases": (
            "weather",
            "forecast",
            "temperature",
            "rain",
            "umbrella",
            "storm",
            "hava",
            "yagmur",
            "yağmur",
            "ruzgar",
            "rüzgar",
            "sicak",
            "sıcak",
            "soguk",
            "soğuk",
            "mont",
            "ceket",
        ),
        "page_key": "routines",
        "record_type": "routine",
        "field": "consumer_interest:weather_planning",
        "title": "Hava ve planlama duyarlılığı",
        "summary": "Kullanıcı hava durumu sinyallerini planlarına dahil ediyor; günlük öneriler hava, rota ve kıyafet bağlamıyla birlikte şekillenmeli.",
        "relations": [
            {"relation_type": "supports", "target": "daily_planning"},
            {"relation_type": "supports", "target": "travel_transport_suggestion"},
        ],
    },
    "local_place_context": {
        "aliases": (
            "nearby",
            "yakın",
            "yakin",
            "places",
            "place",
            "maps",
            "map",
            "cafe",
            "coffee",
            "kahve",
            "restaurant",
            "lokanta",
            "workspace",
            "cowork",
            "calisma",
            "çalışma",
            "mosque",
            "cami",
            "market",
            "museum",
            "park",
        ),
        "page_key": "places",
        "record_type": "preference",
        "field": "consumer_interest:local_place_context",
        "title": "Yakın çevre ve mekan ilgisi",
        "summary": "Kullanıcı yakın çevre, mekan ve rota sinyalleri bırakıyor; yer önerileri ve lokal yönlendirmeler bu bağlamla seçilmeli.",
        "relations": [
            {"relation_type": "relevant_to", "target": "place_recommendation"},
            {"relation_type": "relevant_to", "target": "place_category:cafe"},
            {"relation_type": "relevant_to", "target": "place_category:mosque"},
        ],
    },
    "web_research_orientation": {
        "aliases": (
            "web",
            "website",
            "search",
            "research",
            "inspection",
            "crawl",
            "site",
            "article",
            "articles",
            "makale",
            "incele",
            "arastirma",
            "araştırma",
            "kaynak",
        ),
        "page_key": "preferences",
        "record_type": "preference",
        "field": "consumer_interest:web_research_orientation",
        "title": "Web araştırması eğilimi",
        "summary": "Kullanıcı karar verirken web araştırması, site incelemesi ve kaynak tarama davranışı gösteriyor; cevaplarda kaynaklı özetler öne çıkarılmalı.",
        "relations": [
            {"relation_type": "supports", "target": "knowledge_capture"},
            {"relation_type": "supports", "target": "decision_support"},
        ],
    },
    "culture_history": {
        "aliases": (
            "history",
            "historic",
            "museum",
            "museums",
            "culture",
            "art",
            "architecture",
            "tarih",
            "tarihi",
            "muze",
            "müze",
            "kultur",
            "kültür",
            "sergi",
            "sanat",
        ),
        "page_key": "places",
        "record_type": "preference",
        "field": "consumer_interest:culture_history",
        "title": "Tarih ve kültür ilgisi",
        "summary": "Kullanıcı tarih, kültür ve keşif içeriklerine ilgi gösteriyor; yer önerileri bu merakı hesaba katmalı.",
        "relations": [
            {"relation_type": "relevant_to", "target": "place_category:historic_site"},
        ],
    },
    "spiritual_routine": {
        "aliases": (
            "prayer",
            "namaz",
            "mosque",
            "cami",
            "mescit",
            "ibadet",
            "dua",
            "spiritual",
        ),
        "page_key": "routines",
        "record_type": "routine",
        "field": "consumer_interest:spiritual_routine",
        "title": "Manevi rutin duyarlılığı",
        "summary": "Kullanıcı manevi/rutin odaklı içerik ve mekan sinyalleri bırakıyor; zaman ve yer önerileri bu hassasiyeti korumalı.",
        "relations": [
            {"relation_type": "relevant_to", "target": "place_category:mosque"},
            {"relation_type": "supports", "target": "time_based"},
        ],
    },
}
CONSUMER_SOURCE_WEIGHTS = {
    "browser_context": 0.72,
    "consumer_signal": 0.84,
    "youtube_history": 1.0,
    "reading_list": 0.96,
    "shopping_signal": 1.02,
    "travel_signal": 1.04,
    "weather_context": 0.95,
    "place_interest": 1.0,
    "web_research_signal": 0.9,
}
LEARNING_SIGNAL_TYPES = {
    "consumer_learning",
    "location_pattern_learning",
    "assistant_message_feedback",
    "preference_consolidation",
    "recommendation_feedback_learning",
}
PLACE_CATEGORY_LABELS = {
    "home": "ev",
    "office": "ofis",
    "court": "mahkeme",
    "transit": "ulaşım",
    "mosque": "cami/mescit",
    "cafe": "kafe",
    "market": "market",
    "light_meal": "hafif yemek",
    "historic_site": "tarihi yer",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utcnow().isoformat()


def _iso_to_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _compact_text(value: str | None, *, limit: int = 320) -> str:
    compact = " ".join(str(value or "").strip().split())
    return compact[:limit]


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "record"


def _humanize_identifier(value: str | None) -> str:
    normalized = re.sub(r"[_:/-]+", " ", str(value or "").strip()).strip()
    if not normalized:
        return "Unknown"
    compact = " ".join(part for part in normalized.split() if part)
    return compact[:1].upper() + compact[1:]


def _fingerprint(payload: Any) -> str:
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _parse_json_object_from_text(value: str | None) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _list_files(root: Path, suffix: str) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob(f"*{suffix}") if path.is_file())


def _tokenize(value: str | None) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9çğıöşü]+", str(value or "").lower()) if len(token) >= 2]


def _semantic_normalize_text(value: str | None) -> str:
    text = str(value or "").lower().strip()
    replacements = str.maketrans({
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "İ": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
    })
    normalized = text.translate(replacements)
    normalized = re.sub(r"[^a-z0-9@.\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _split_semantic_statements(value: str | None) -> list[str]:
    parts = re.split(r"(?:\n|;)+", str(value or "").strip())
    return [part.strip() for part in parts if part and part.strip()]


def _scope_shareability(scope: str, sensitivity: str) -> str:
    normalized_scope = str(scope or "").strip()
    if normalized_scope.startswith("project:"):
        return "project_private"
    if sensitivity in {"high", "restricted"}:
        return "private"
    return SHAREABILITY_BY_SCOPE.get(normalized_scope, "shareable")


def _relation_target_candidate_keys(target: str | None) -> list[str]:
    normalized = str(target or "").strip()
    if not normalized:
        return []
    if ":" in normalized and normalized.split(":", 1)[0] in {
        "field",
        "topic",
        "project",
        "person",
        "place",
        "page",
        "record_type",
        "place_category",
        "recommendation_kind",
    }:
        return [f"{normalized.split(':', 1)[0]}:{_slugify(normalized.split(':', 1)[1])}"]
    slug = _slugify(normalized)
    candidates = [
        f"field:{slug}",
        f"topic:{slug}",
        f"project:{slug}",
        f"person:{slug}",
        f"place:{slug}",
        f"page:{slug}",
        f"record_type:{slug}",
        f"place_category:{slug}",
        f"recommendation_kind:{slug}",
    ]
    if normalized.startswith("matter:"):
        matter_id = normalized.split(":", 1)[1]
        candidates.append(f"project:matter-{_slugify(matter_id)}")
    return list(dict.fromkeys(candidates))


def _has_meaningful_location_payload(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in ("place_id", "label", "title", "area", "category", "observed_at", "started_at"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
    for key in ("latitude", "longitude", "accuracy_meters"):
        if payload.get(key) is not None:
            return True
    return False


class SafetyPolicyAgent:
    def __init__(self, service: "KnowledgeBaseService") -> None:
        self.service = service

    def classify(self, action_kind: str | None) -> dict[str, Any]:
        key = str(action_kind or "read_summary").strip()
        return dict(RISK_POLICY_MATRIX.get(key, RISK_POLICY_MATRIX["read_summary"]))


class WikiMaintainerAgent:
    def __init__(self, service: "KnowledgeBaseService") -> None:
        self.service = service

    def sync_profiles(
        self,
        profile: dict[str, Any],
        runtime_profile: dict[str, Any],
        *,
        raw_source_ref: str | None = None,
        render: bool = True,
    ) -> dict[str, Any]:
        state = self.service._load_state()
        updated_pages: list[str] = []
        contradictions: list[dict[str, Any]] = []
        now = _iso_now()
        if self.service.epistemic is not None:
            try:
                self.service.epistemic.record_profile_claims(
                    profile=profile,
                    runtime_profile=runtime_profile,
                    source_ref=raw_source_ref,
                )
            except Exception:
                pass

        def upsert(page_key: str, record: dict[str, Any]) -> None:
            nonlocal contradictions
            result = self.service._upsert_page_record(state, page_key, record)
            if result["updated"]:
                updated_pages.append(page_key)
            contradictions.extend(result["contradictions"])

        display_name = _compact_text(profile.get("display_name"), limit=120)
        if display_name:
            upsert(
                "persona",
                {
                    "id": "persona-display-name",
                    "key": "display_name",
                    "title": "Hitap tercihi",
                    "summary": f"Kullanıcıya {display_name} diye hitap edilmeli.",
                    "confidence": 1.0,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["explicit_profile"],
                    "updated_at": now,
                    "metadata": {"field": "display_name"},
                },
            )

        assistant_name = _compact_text(runtime_profile.get("assistant_name"), limit=120)
        if assistant_name:
            upsert(
                "persona",
                {
                    "id": "persona-assistant-name",
                    "key": "assistant_name",
                    "title": "Asistan adı",
                    "summary": f"Asistanın görünen adı {assistant_name}.",
                    "confidence": 1.0,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["explicit_runtime_profile"],
                    "updated_at": now,
                    "metadata": {"field": "assistant_name"},
                },
            )

        for field, label, prefix in (
            ("communication_style", "İletişim tarzı", "Kullanıcı tercih edilen iletişim tarzını şöyle tanımlıyor:"),
            ("food_preferences", "Yemek tercihleri", "Yemek tercihi notu:"),
            ("transport_preference", "Ulaşım tercihi", "Tercih edilen ulaşım biçimi:"),
            ("weather_preference", "Hava tercihi", "Hava ve iklim tercihi:"),
            ("travel_preferences", "Seyahat tercihi", "Seyahat notu:"),
            ("favorite_color", "Favori renk", "Favori renk tercihi:"),
        ):
            value = _compact_text(profile.get(field), limit=500)
            if not value:
                continue
            upsert(
                "preferences",
                {
                    "id": f"preference-{field}",
                    "key": field,
                    "title": label,
                    "summary": f"{prefix} {value}",
                    "confidence": 0.98,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["explicit_profile"],
                    "updated_at": now,
                    "metadata": {"field": field, "source": "user_profile"},
                },
            )

        assistant_notes = _compact_text(profile.get("assistant_notes"), limit=1400)
        if assistant_notes:
            upsert(
                "persona",
                {
                    "id": "persona-assistant-notes",
                    "key": "assistant_notes",
                    "title": "Destek ve çalışma beklentileri",
                    "summary": assistant_notes,
                    "confidence": 0.92,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["profile_memory"],
                    "updated_at": now,
                    "metadata": {"field": "assistant_notes"},
                },
            )

        tone = _compact_text(runtime_profile.get("tone"), limit=160)
        if tone:
            upsert(
                "persona",
                {
                    "id": "persona-tone",
                    "key": "assistant_tone",
                    "title": "Asistan tonu",
                    "summary": f"Asistan varsayılan olarak {tone} tonunda ilerlemeli.",
                    "confidence": 0.96,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["runtime_profile"],
                    "updated_at": now,
                    "metadata": {"field": "tone"},
                },
            )

        role_summary = _compact_text(runtime_profile.get("role_summary"), limit=240)
        if role_summary:
            upsert(
                "persona",
                {
                    "id": "persona-role-summary",
                    "key": "assistant_role_summary",
                    "title": "Asistan rol özeti",
                    "summary": role_summary,
                    "confidence": 0.95,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["runtime_profile"],
                    "updated_at": now,
                    "metadata": {"field": "role_summary"},
                },
            )

        soul_notes = _compact_text(runtime_profile.get("soul_notes"), limit=1800)
        if soul_notes:
            upsert(
                "persona",
                {
                    "id": "persona-soul-notes",
                    "key": "soul_notes",
                    "title": "Davranış ve sınır notları",
                    "summary": soul_notes,
                    "confidence": 0.95,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["runtime_profile"],
                    "updated_at": now,
                    "metadata": {"field": "soul_notes"},
                },
            )

        tools_notes = _compact_text(runtime_profile.get("tools_notes"), limit=1800)
        if tools_notes:
            upsert(
                "routines",
                {
                    "id": "routine-tools-notes",
                    "key": "tools_notes",
                    "title": "Çalışma ritmi",
                    "summary": tools_notes,
                    "confidence": 0.88,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["runtime_profile"],
                    "updated_at": now,
                    "metadata": {"field": "tools_notes"},
                },
            )

        for index, check in enumerate(runtime_profile.get("heartbeat_extra_checks") or [], start=1):
            label = _compact_text(check, limit=180)
            if not label:
                continue
            upsert(
                "routines",
                {
                    "id": f"routine-heartbeat-{index}",
                    "key": f"heartbeat-{_slugify(label)}",
                    "title": "Heartbeat kontrolü",
                    "summary": label,
                    "confidence": 0.84,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["runtime_profile"],
                    "updated_at": now,
                    "metadata": {"field": "heartbeat_extra_checks"},
                },
            )

        for form in normalize_assistant_forms(runtime_profile.get("assistant_forms")):
            if not form.get("active"):
                continue
            title = _compact_text(form.get("title"), limit=120) or str(form.get("slug") or "").replace("-", " ").title()
            capabilities = [str(item).strip() for item in list(form.get("capabilities") or []) if str(item).strip()]
            summary = _compact_text(form.get("summary"), limit=320) or f"Asistan çekirdeğinde {title} formu aktif."
            if capabilities:
                summary = f"{summary} Yetkinlikler: {', '.join(capabilities[:5])}."
            upsert(
                "persona",
                {
                    "id": f"assistant-form-{form.get('slug')}",
                    "key": f"assistant_form:{form.get('slug')}",
                    "title": f"Asistan formu · {title}",
                    "summary": summary,
                    "confidence": 0.97,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["runtime_profile", "assistant_form"],
                    "updated_at": now,
                    "metadata": {
                        "field": "assistant_forms",
                        "record_type": "source",
                        "scope": "global",
                        "assistant_form": True,
                        "assistant_form_slug": form.get("slug"),
                        "capabilities": capabilities,
                        "ui_surfaces": list(form.get("ui_surfaces") or []),
                    },
                },
            )

        operating_contract = assistant_operating_contract(runtime_profile)
        for capability in list(operating_contract.get("capability_contracts") or []):
            slug = str(capability.get("slug") or "").strip()
            title = _compact_text(capability.get("title"), limit=120) or slug.replace("_", " ").title()
            if not slug or not title:
                continue
            upsert(
                "persona",
                {
                    "id": f"assistant-capability-{slug}",
                    "key": f"assistant_capability:{slug}",
                    "title": f"Asistan capability · {title}",
                    "summary": _compact_text(capability.get("operating_hint") or capability.get("summary"), limit=320) or f"Asistan çekirdeğinde {title} capability'si aktif.",
                    "confidence": 0.93,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["runtime_profile", "assistant_capability"],
                    "updated_at": now,
                    "metadata": {
                        "field": "assistant_capabilities",
                        "record_type": "constraint",
                        "scope": "global",
                        "assistant_capability": True,
                        "assistant_capability_slug": slug,
                        "category": capability.get("category"),
                        "implies_surfaces": list(capability.get("implies_surfaces") or []),
                    },
                },
            )

        for surface in list(operating_contract.get("surface_contracts") or []):
            slug = str(surface.get("slug") or "").strip()
            title = _compact_text(surface.get("title"), limit=120) or slug.replace("_", " ").title()
            if not slug or not title:
                continue
            upsert(
                "persona",
                {
                    "id": f"assistant-surface-{slug}",
                    "key": f"assistant_surface:{slug}",
                    "title": f"Asistan yüzeyi · {title}",
                    "summary": _compact_text(surface.get("summary"), limit=280) or f"Asistan çekirdeğinde {title} yüzeyi görünür tutulmalı.",
                    "confidence": 0.9,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["runtime_profile", "assistant_surface"],
                    "updated_at": now,
                    "metadata": {
                        "field": "assistant_surfaces",
                        "record_type": "constraint",
                        "scope": "global",
                        "assistant_surface": True,
                        "assistant_surface_slug": slug,
                        "category": surface.get("category"),
                    },
                },
            )

        behavior_contract = normalize_behavior_contract(runtime_profile.get("behavior_contract"))
        if behavior_contract:
            contract_summary = ", ".join(
                [
                    f"proaktiflik={behavior_contract.get('initiative_level')}",
                    f"takip={behavior_contract.get('follow_up_style')}",
                    f"plan={behavior_contract.get('planning_depth')}",
                    f"hesap verilebilirlik={behavior_contract.get('accountability_style')}",
                    f"açıklama={behavior_contract.get('explanation_style')}",
                ]
            )
            upsert(
                "persona",
                {
                    "id": "assistant-behavior-contract",
                    "key": "assistant_behavior_contract",
                    "title": "Asistan çalışma kontratı",
                    "summary": f"Asistanın varsayılan çalışma kontratı: {contract_summary}.",
                    "confidence": 0.94,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["runtime_profile", "assistant_contract"],
                    "updated_at": now,
                    "metadata": {
                        "field": "behavior_contract",
                        "record_type": "constraint",
                        "scope": "global",
                    },
                },
            )

        for index, related in enumerate(profile.get("related_profiles") or [], start=1):
            name = _compact_text(related.get("name"), limit=120)
            if not name:
                continue
            relationship = _compact_text(related.get("relationship"), limit=80)
            preferences = _compact_text(related.get("preferences"), limit=400)
            notes = _compact_text(related.get("notes"), limit=400)
            summary_parts = [name]
            if relationship:
                summary_parts.append(f"ilişki: {relationship}")
            if preferences:
                summary_parts.append(f"tercihler: {preferences}")
            if notes:
                summary_parts.append(f"not: {notes}")
            upsert(
                "contacts",
                {
                    "id": f"contact-related-{index}",
                    "key": f"contact-{_slugify(name)}",
                    "title": name,
                    "summary": "; ".join(summary_parts),
                    "confidence": 0.9,
                    "status": "active",
                    "source_refs": [raw_source_ref] if raw_source_ref else [],
                    "signals": ["explicit_profile"],
                    "updated_at": now,
                    "metadata": {
                        "relationship": relationship,
                        "important_dates": list(related.get("important_dates") or []),
                    },
                },
            )

        if updated_pages:
            state["updated_at"] = now
            self.service._save_state(state)
            if render:
                self.service._render_all(state)
        return {
            "updated_pages": sorted(set(updated_pages)),
            "contradictions": contradictions,
        }

    def compile_ingest(self, normalized: dict[str, Any], *, render: bool = True) -> dict[str, Any]:
        state = self.service._load_state()
        updated_pages: list[str] = []
        contradictions: list[dict[str, Any]] = []
        source_ref = str(normalized.get("raw_path") or "")

        for page_key in normalized.get("target_pages") or []:
            record_id = f"{page_key}-{_slugify(str(normalized.get('title') or normalized.get('source_type') or 'entry'))}-{normalized['source_id'][:8]}"
            summary = str(normalized.get("summary") or "").strip()
            if not summary:
                continue
            result = self.service._upsert_page_record(
                state,
                page_key,
                {
                    "id": record_id,
                    "key": normalized.get("key") or record_id,
                    "title": str(normalized.get("title") or normalized.get("source_type") or page_key).strip(),
                    "summary": summary,
                    "confidence": float(normalized.get("confidence") or 0.65),
                    "status": "active",
                    "source_refs": [source_ref] if source_ref else [],
                    "signals": list(normalized.get("signals") or []),
                    "updated_at": _iso_now(),
                    "metadata": {
                        "source_type": normalized.get("source_type"),
                        "tags": list(normalized.get("tags") or []),
                        "metadata": dict(normalized.get("metadata") or {}),
                    },
                },
            )
            if result["updated"]:
                updated_pages.append(page_key)
            contradictions.extend(result["contradictions"])

        if updated_pages:
            state["updated_at"] = _iso_now()
            self.service._save_state(state)
            if render:
                self.service._render_all(state)
        return {
            "updated_pages": sorted(set(updated_pages)),
            "contradictions": contradictions,
        }


class IngestAgent:
    def __init__(self, service: "KnowledgeBaseService") -> None:
        self.service = service

    def ingest(
        self,
        *,
        source_type: str,
        content: str,
        title: str | None,
        metadata: dict[str, Any] | None,
        occurred_at: str | None,
        source_ref: str | None,
        tags: list[str] | None,
        render: bool = True,
    ) -> dict[str, Any]:
        self.service.ensure_scaffold()
        normalized_type = self._normalize_source_type(source_type)
        if normalized_type not in SUPPORTED_RAW_TYPES:
            raise ValueError("unsupported_source_type")
        self.service._assert_not_excluded(source_ref, metadata)

        raw_record = self._store_raw_source(
            source_type=normalized_type,
            content=content,
            title=title,
            metadata=metadata,
            occurred_at=occurred_at,
            source_ref=source_ref,
            tags=tags,
        )
        if self.service.epistemic is not None and normalized_type == "user_preferences":
            field = str((metadata or {}).get("field") or "").strip()
            value_text = _compact_text(content, limit=1000)
            if field and value_text:
                try:
                    artifact = self.service.epistemic.record_artifact(
                        artifact_kind="user_preference_signal",
                        source_kind="user_preferences",
                        source_ref=str(source_ref or f"user-preferences:{field}"),
                        summary=str(title or field),
                        payload={
                            "field": field,
                            "title": title,
                            "content": value_text,
                            "metadata": dict(metadata or {}),
                        },
                        provenance={"raw_source_id": raw_record.get("id")},
                        sensitive=bool((metadata or {}).get("sensitive")),
                    )
                    self.service.epistemic.record_claim(
                        subject_key="user",
                        predicate=field,
                        object_value_text=value_text,
                        scope=str((metadata or {}).get("scope") or "personal"),
                        epistemic_basis="user_explicit",
                        validation_state="user_confirmed",
                        consent_class="blocked" if bool((metadata or {}).get("never_use")) else "allowed",
                        retrieval_eligibility="blocked" if bool((metadata or {}).get("sensitive")) else "eligible",
                        artifact_id=str(artifact.get("id") or ""),
                        sensitive=bool((metadata or {}).get("sensitive")),
                        metadata={"source_ref": source_ref, "field": field, "source_kind": "user_preferences"},
                    )
                except Exception:
                    pass
        normalized = self._build_normalized_record(raw_record)
        self.service._write_json(
            self.service._normalized_dir() / f"{normalized['source_id']}.json",
            normalized,
        )
        compile_result = self.service.wiki_maintainer.compile_ingest(normalized, render=render)
        log_entry = self.service._append_log(
            "knowledge_ingest",
            f"{normalized_type} kaydı işlendi",
            {
                "source_id": normalized["source_id"],
                "source_type": normalized_type,
                "target_pages": normalized.get("target_pages") or [],
                "contradiction_count": len(compile_result["contradictions"]),
            },
        )
        return {
            "raw": raw_record,
            "normalized": normalized,
            "compile": compile_result,
            "log": log_entry,
        }

    def _normalize_source_type(self, source_type: str) -> str:
        normalized = _slugify(source_type).replace("-", "_")
        aliases = {
            "message": "messages",
            "message_thread": "messages",
            "whatsapp_message": "whatsapp",
            "preference": "user_preferences",
            "location_event": "location_events",
            "web_snippet": "web_snippets",
            "task": "tasks",
            "reminder": "reminders",
            "file": "files",
            "legal_doc": "legal_docs",
        }
        return aliases.get(normalized, normalized)

    def _store_raw_source(
        self,
        *,
        source_type: str,
        content: str,
        title: str | None,
        metadata: dict[str, Any] | None,
        occurred_at: str | None,
        source_ref: str | None,
        tags: list[str] | None,
    ) -> dict[str, Any]:
        occurred = str(occurred_at or _iso_now())
        compact_title = _compact_text(title or source_type, limit=180)
        payload = {
            "source_type": source_type,
            "title": compact_title,
            "content": str(content or "").strip(),
            "metadata": dict(metadata or {}),
            "occurred_at": occurred,
            "source_ref": str(source_ref or "").strip() or None,
            "tags": [str(item).strip() for item in list(tags or []) if str(item).strip()],
        }
        source_id = _fingerprint(payload)
        raw_record = {
            "id": source_id,
            **payload,
            "stored_at": _iso_now(),
        }
        stamp = _utcnow()
        raw_path = self.service.raw_dir / source_type / f"{stamp:%Y}" / f"{stamp:%m}"
        raw_path.mkdir(parents=True, exist_ok=True)
        file_path = raw_path / f"{source_id}.json"
        if not file_path.exists():
            self.service._write_json(file_path, raw_record)
        raw_record["path"] = str(file_path)
        return raw_record

    def _build_normalized_record(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        content = str(raw_record.get("content") or "")
        metadata = dict(raw_record.get("metadata") or {})
        source_type = str(raw_record.get("source_type") or "")
        title = str(raw_record.get("title") or source_type).strip()
        compact_content = self._build_summary(source_type=source_type, title=title, content=content, metadata=metadata)
        tags = [str(item).strip() for item in raw_record.get("tags") or [] if str(item).strip()]
        target_pages: list[str] = []
        signals: list[str] = []
        confidence = 0.62
        key = None

        if source_type in {"email", "messages", "whatsapp"}:
            target_pages.extend(["contacts", "projects"])
            signals.append("communication_source")
            if any(token in content.lower() for token in ("seviyorum", "tercih", "genelde", "severim")):
                target_pages.append("preferences")
                confidence = 0.68
                signals.append("preference_hint")
        elif source_type == "calendar":
            target_pages.extend(["routines", "projects"])
            confidence = 0.7
            signals.append("calendar_context")
        elif source_type in {"places", "location_events"}:
            target_pages.extend(["places", "routines"])
            confidence = 0.72
            signals.append("location_context")
        elif source_type in {"files", "pdf", "legal_docs"}:
            target_pages.extend(["legal", "projects"])
            confidence = 0.74
            signals.append("document_context")
        elif source_type in {"tasks", "reminders"}:
            target_pages.extend(["projects", "recommendations"])
            confidence = 0.7
            signals.append("task_context")
        elif source_type in {"browser_context", "reading_list"}:
            target_pages.extend(["projects", "preferences", "recommendations"])
            confidence = 0.7
            signals.extend(["consumer_context", "browser_context"])
        elif source_type in {"youtube_history", "consumer_signal"}:
            target_pages.extend(["preferences", "recommendations", "projects"])
            confidence = 0.74
            signals.extend(["consumer_context", "interest_signal"])
        elif source_type == "shopping_signal":
            target_pages.extend(["preferences", "recommendations", "projects"])
            confidence = 0.76
            signals.extend(["consumer_context", "shopping_signal"])
        elif source_type == "travel_signal":
            target_pages.extend(["preferences", "places", "recommendations", "projects"])
            confidence = 0.78
            signals.extend(["consumer_context", "travel_signal"])
        elif source_type == "user_preferences":
            target_pages.extend(["preferences", "persona"])
            confidence = 0.9
            signals.append("explicit_preference")
            key = metadata.get("field")
        elif source_type == "decision":
            target_pages.append("decisions")
            confidence = 0.96
            signals.append("decision_record")
        elif source_type == "recommendation_feedback":
            target_pages.extend(["recommendations", "reflections"])
            confidence = 0.88
            signals.append("feedback")
        elif source_type == "assistant_message_feedback":
            target_pages.extend([str(metadata.get("page_key") or "preferences"), "persona", "reflections"])
            confidence = 0.9
            signals.extend(["feedback", "assistant_message_feedback"])
            if metadata.get("message_id") is not None:
                key = f"assistant-message-feedback-{metadata.get('message_id')}"
        elif source_type in {"profile_snapshot", "assistant_runtime_snapshot"}:
            target_pages.extend(["persona", "preferences", "routines", "contacts"])
            confidence = 0.94
            signals.append("profile_snapshot")
        elif source_type == "assistant_action":
            target_pages.extend(["decisions", "projects", "recommendations"])
            confidence = 0.86
            signals.append("assistant_action_lifecycle")
            if metadata.get("action_id") is not None:
                key = f"assistant-action-{metadata.get('action_id')}"
        elif source_type == "approval_event":
            target_pages.extend(["decisions", "reflections", "recommendations"])
            confidence = 0.84
            signals.append("approval_lifecycle")
            if metadata.get("approval_event_id") is not None:
                key = f"approval-event-{metadata.get('approval_event_id')}"
        elif source_type == "assistant_file_back":
            target_pages.extend([str(metadata.get("page_key") or "projects")])
            confidence = float(metadata.get("confidence") or 0.76)
            signals.append("assistant_file_back")
            key = str(metadata.get("logical_key") or metadata.get("file_back_kind") or "") or None
        else:
            target_pages.append("projects")
            signals.append("generic_signal")

        if metadata.get("place_name") or source_type == "travel_signal":
            target_pages.append("places")
            signals.append("named_place")
        if metadata.get("contact_name") or metadata.get("participants"):
            target_pages.append("contacts")
            signals.append("named_contact")
        if metadata.get("project") or metadata.get("matter_id"):
            target_pages.append("projects")
            signals.append("named_project")

        deduped_pages = []
        seen_pages: set[str] = set()
        for page_key in target_pages:
            if page_key not in PAGE_SPECS or page_key in seen_pages:
                continue
            seen_pages.add(page_key)
            deduped_pages.append(page_key)

        return {
            "source_id": str(raw_record.get("id") or ""),
            "source_type": source_type,
            "title": title,
            "summary": compact_content or title,
            "confidence": confidence,
            "signals": signals,
            "target_pages": deduped_pages,
            "tags": tags,
            "metadata": metadata,
            "occurred_at": raw_record.get("occurred_at"),
            "raw_path": raw_record.get("path"),
            "key": key,
        }

    def _build_summary(self, *, source_type: str, title: str, content: str, metadata: dict[str, Any]) -> str:
        structured = self._parse_structured_content(content)
        if source_type == "assistant_action" and isinstance(structured, dict):
            action_type = _compact_text(structured.get("action_type"), limit=80) or _compact_text(metadata.get("action_type"), limit=80)
            target_channel = _compact_text(structured.get("target_channel"), limit=40) or _compact_text(metadata.get("target_channel"), limit=40)
            status = _compact_text(structured.get("status"), limit=40) or _compact_text(metadata.get("status"), limit=40)
            action_title = _compact_text(structured.get("title"), limit=160) or title
            summary_parts = [f"Aksiyon {action_title}"]
            if action_type:
                summary_parts.append(f"tür: {action_type}")
            if target_channel:
                summary_parts.append(f"kanal: {target_channel}")
            if status:
                summary_parts.append(f"durum: {status}")
            rationale = _compact_text(structured.get("rationale"), limit=260)
            if rationale:
                summary_parts.append(f"gerekçe: {rationale}")
            return "; ".join(summary_parts)
        if source_type == "approval_event" and isinstance(structured, dict):
            event_type = _compact_text(structured.get("event_type"), limit=60) or _compact_text(metadata.get("event_type"), limit=60) or "approval_event"
            action_id = structured.get("action_id") if structured.get("action_id") is not None else metadata.get("action_id")
            draft_id = structured.get("outbound_draft_id") if structured.get("outbound_draft_id") is not None else metadata.get("draft_id")
            note = _compact_text(structured.get("note"), limit=260)
            summary_parts = [f"Onay akışı olayı: {event_type}"]
            if action_id is not None:
                summary_parts.append(f"action #{action_id}")
            if draft_id is not None:
                summary_parts.append(f"draft #{draft_id}")
            if note:
                summary_parts.append(f"not: {note}")
            return "; ".join(summary_parts)
        if source_type == "assistant_message_feedback" and isinstance(structured, dict):
            feedback_value = _compact_text(structured.get("feedback_value"), limit=40) or _compact_text(metadata.get("feedback_value"), limit=40)
            signal_label = _compact_text(structured.get("signal_label"), limit=80) or _compact_text(metadata.get("signal_label"), limit=80)
            message_preview = _compact_text(structured.get("message_preview"), limit=160) or _compact_text(metadata.get("message_preview"), limit=160)
            summary_parts = [f"Asistan mesajı geri bildirimi: {feedback_value or 'feedback'}"]
            if signal_label:
                summary_parts.append(f"sinyal: {signal_label}")
            if message_preview:
                summary_parts.append(f"mesaj: {message_preview}")
            return "; ".join(summary_parts)
        return _compact_text(content, limit=720) or title

    @staticmethod
    def _parse_structured_content(content: str) -> dict[str, Any] | list[Any] | None:
        stripped = str(content or "").strip()
        if not stripped or stripped[0] not in "{[":
            return None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, (dict, list)) else None


class ReflectionAgent:
    def __init__(self, service: "KnowledgeBaseService") -> None:
        self.service = service

    def run(self) -> dict[str, Any]:
        self.service.ensure_scaffold()
        state = self.service._load_state()
        wiki_brain = self.service._build_wiki_brain(state)
        now = _utcnow()
        raw_files = _list_files(self.service.raw_dir, ".json")
        indexed_raw_paths = {
            source_ref
            for page in state.get("pages", {}).values()
            for record in page.get("records", [])
            for source_ref in record.get("source_refs", [])
            if source_ref
        }

        contradictions: list[dict[str, Any]] = []
        stale_items: list[dict[str, Any]] = []
        orphan_pages: list[dict[str, Any]] = []
        missing_pages: list[str] = []
        repeated_rejections: list[dict[str, Any]] = []
        schema_drift: list[str] = []
        source_page_mismatches: list[str] = []
        low_confidence_records: list[dict[str, Any]] = []
        preference_drift: list[dict[str, Any]] = []
        knowledge_gaps: list[dict[str, Any]] = []
        research_topics: list[dict[str, Any]] = []
        potential_wiki_pages: list[dict[str, Any]] = []
        prunable_records: list[dict[str, Any]] = []
        inconsistency_hotspots: list[dict[str, Any]] = []
        scope_summary: dict[str, int] = {}
        user_model_summary: list[str] = []

        for page_key, description in PAGE_SPECS.items():
            page = state.get("pages", {}).get(page_key) or {}
            records = [record for record in page.get("records", []) if isinstance(record, dict)]
            active_records = [record for record in records if str(record.get("status") or "active") == "active"]
            if not active_records:
                orphan_pages.append({"page": page_key, "reason": "No active records"})
            window_days = STALENESS_WINDOWS.get(page_key, 90)
            for record in active_records:
                updated_at = str(record.get("updated_at") or "")
                try:
                    updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                except ValueError:
                    updated_dt = now - timedelta(days=window_days + 1)
                    schema_drift.append(f"{page_key}:{record.get('id')} invalid updated_at")
                age_days = max(0, (now - updated_dt.astimezone(timezone.utc)).days)
                if age_days > window_days:
                    stale_items.append({"page": page_key, "record_id": record.get("id"), "age_days": age_days})
                if float(record.get("confidence") or 0.0) < 0.7:
                    low_confidence_records.append(
                        {
                            "page": page_key,
                            "record_id": record.get("id"),
                            "confidence": record.get("confidence"),
                            "summary": record.get("summary"),
                        }
                    )
                envelope = self.service._normalized_record_envelope(page_key, record)
                scope = str(envelope.get("scope") or "global")
                scope_summary[scope] = scope_summary.get(scope, 0) + 1
                metadata = dict(envelope.get("metadata") or {})
                correction_count = len(list(metadata.get("correction_history") or []))
                contradiction_count = int(metadata.get("repeated_contradiction_count") or 0)
                if (
                    (float(record.get("confidence") or 0.0) < 0.45 and age_days > max(30, window_days // 2))
                    or contradiction_count >= 2
                    or correction_count >= 4
                ):
                    prunable_records.append(
                        {
                            "page": page_key,
                            "record_id": record.get("id"),
                            "confidence": record.get("confidence"),
                            "age_days": age_days,
                            "correction_count": correction_count,
                            "repeated_contradiction_count": contradiction_count,
                            "summary": record.get("summary"),
                        }
                    )
            for record in records:
                if not isinstance(record, dict):
                    continue
                updated_dt = _iso_to_datetime(str(record.get("updated_at") or ""))
                age_days = max(0, (now - updated_dt).days) if updated_dt else window_days + 1
                envelope = self.service._normalized_record_envelope(page_key, record)
                metadata = dict(envelope.get("metadata") or {})
                correction_count = len(list(metadata.get("correction_history") or []))
                contradiction_count = int(metadata.get("repeated_contradiction_count") or 0)
                if (
                    str(record.get("status") or "active") != "active"
                    or float(record.get("confidence") or 0.0) < 0.45
                    or contradiction_count >= 2
                    or correction_count >= 4
                ) and (
                    age_days > max(30, window_days // 2)
                    or contradiction_count >= 2
                    or correction_count >= 4
                ):
                    marker = f"{page_key}:{record.get('id')}"
                    if marker not in {f"{item.get('page')}:{item.get('record_id')}" for item in prunable_records}:
                        prunable_records.append(
                            {
                                "page": page_key,
                                "record_id": record.get("id"),
                                "confidence": record.get("confidence"),
                                "age_days": age_days,
                                "correction_count": correction_count,
                                "repeated_contradiction_count": contradiction_count,
                                "summary": record.get("summary"),
                                "status": record.get("status"),
                            }
                        )
            active_by_key: dict[str, list[dict[str, Any]]] = {}
            for record in active_records:
                logical_key = str(record.get("key") or record.get("title") or record.get("id") or "")
                active_by_key.setdefault(logical_key, []).append(record)
            for logical_key, items in active_by_key.items():
                summaries = {str(item.get("summary") or "").strip() for item in items if str(item.get("summary") or "").strip()}
                if len(items) > 1 and len(summaries) > 1:
                    contradictions.append({"page": page_key, "key": logical_key, "record_ids": [item.get("id") for item in items]})
                    inconsistency_hotspots.append(
                        {
                            "page": page_key,
                            "key": logical_key,
                            "summary_count": len(summaries),
                            "record_count": len(items),
                        }
                    )
            all_records_by_key: dict[str, list[dict[str, Any]]] = {}
            for record in records:
                logical_key = str(record.get("key") or record.get("title") or record.get("id") or "")
                if not logical_key:
                    continue
                all_records_by_key.setdefault(logical_key, []).append(record)
            for logical_key, items in all_records_by_key.items():
                summaries = {str(item.get("summary") or "").strip() for item in items if str(item.get("summary") or "").strip()}
                if len(items) > 1 and len(summaries) > 1:
                    marker = f"{page_key}:{logical_key}"
                    if marker not in {f"{item.get('page')}:{item.get('key')}" for item in inconsistency_hotspots}:
                        inconsistency_hotspots.append(
                            {
                                "page": page_key,
                                "key": logical_key,
                                "summary_count": len(summaries),
                                "record_count": len(items),
                            }
                        )
            if page_key == "preferences":
                all_by_key: dict[str, list[dict[str, Any]]] = {}
                for record in records:
                    logical_key = str(record.get("key") or record.get("id") or "")
                    if not logical_key:
                        continue
                    all_by_key.setdefault(logical_key, []).append(record)
                for logical_key, items in all_by_key.items():
                    superseded_count = sum(1 for item in items if str(item.get("status") or "") == "superseded")
                    if superseded_count >= 1:
                        latest = max(items, key=lambda item: str(item.get("updated_at") or ""))
                        preference_drift.append(
                            {
                                "key": logical_key,
                                "superseded_count": superseded_count,
                                "latest_summary": latest.get("summary"),
                            }
                        )
            if page_key not in state.get("pages", {}):
                missing_pages.append(page_key)
                schema_drift.append(f"missing page object: {page_key}")

        recommendation_history = state.get("recommendation_history") or []
        rejection_counts: dict[str, int] = {}
        for item in recommendation_history:
            if str(item.get("outcome") or "") != "rejected":
                continue
            kind = str(item.get("kind") or "generic")
            rejection_counts[kind] = rejection_counts.get(kind, 0) + 1
        for kind, count in rejection_counts.items():
            if count >= 2:
                repeated_rejections.append({"kind": kind, "count": count})

        for raw_path in raw_files:
            raw_path_str = str(raw_path)
            if raw_path_str not in indexed_raw_paths:
                source_page_mismatches.append(f"Unindexed raw source: {raw_path_str}")
        for source_ref in sorted(indexed_raw_paths):
            if source_ref and not Path(source_ref).exists():
                source_page_mismatches.append(f"Missing source ref: {source_ref}")

        if any("contacts" in str(path) or "messages" in str(path) for path in raw_files):
            contacts_page = (state.get("pages", {}).get("contacts") or {}).get("records") or []
            if not contacts_page:
                missing_pages.append("contacts page should be populated from communication signals")
        if any("places" in str(path) for path in raw_files):
            places_page = (state.get("pages", {}).get("places") or {}).get("records") or []
            if not places_page:
                missing_pages.append("places page should be populated from location signals")

        concepts = list(wiki_brain.get("concepts") or [])
        if not concepts:
            knowledge_gaps.append(
                {
                    "kind": "missing_concept_articles",
                    "reason": "Active records mevcut ama concept article derlemesi boş.",
                }
            )
        concept_kind_counts = Counter(str(item.get("kind") or "concept") for item in concepts)
        for concept in concepts[:50]:
            if int(concept.get("backlink_count") or 0) <= 1:
                knowledge_gaps.append(
                    {
                        "kind": "thin_article",
                        "concept_key": concept.get("key"),
                        "title": concept.get("title"),
                        "reason": "Concept article tek bir backlink ile zayıf kalıyor.",
                    }
                )
            if float(concept.get("confidence") or 0.0) < 0.62:
                research_topics.append(
                    {
                        "title": concept.get("title"),
                        "concept_key": concept.get("key"),
                        "reason": "Confidence düşük; yeni source veya correction sinyaliyle güçlendirilmeli.",
                    }
                )
        if concept_kind_counts.get("topic", 0) < 2:
            potential_wiki_pages.append(
                {
                    "page_key": "concepts/topics",
                    "reason": "Topic-level article sayısı az; communication style ve planning style için ayrı article faydalı olabilir.",
                }
            )
        if repeated_rejections:
            potential_wiki_pages.append(
                {
                    "page_key": "recommendations/history",
                    "reason": "Repeated rejections arttı; ayrı recommendation fatigue summary article faydalı olabilir.",
                }
            )

        for page_key in ("persona", "preferences", "routines"):
            page = state.get("pages", {}).get(page_key) or {}
            active_records = [record for record in page.get("records", []) if str(record.get("status") or "active") == "active"]
            for record in active_records[:2]:
                user_model_summary.append(f"{page_key}: {record.get('summary')}")

        report = {
            "generated_at": _iso_now(),
            "summary": {
                "contradictions": len(contradictions),
                "stale_items": len(stale_items),
                "orphan_pages": len(orphan_pages),
                "missing_pages": len(missing_pages),
                "repeated_rejections": len(repeated_rejections),
                "schema_drift": len(schema_drift),
                "source_page_mismatches": len(source_page_mismatches),
                "low_confidence_records": len(low_confidence_records),
                "preference_drift": len(preference_drift),
                "knowledge_gaps": len(knowledge_gaps),
                "research_topics": len(research_topics),
                "potential_wiki_pages": len(potential_wiki_pages),
                "prunable_records": len(prunable_records),
                "inconsistency_hotspots": len(inconsistency_hotspots),
            },
            "contradictions": contradictions[:50],
            "stale_items": stale_items[:50],
            "orphan_pages": orphan_pages[:20],
            "missing_page_suggestions": missing_pages[:20],
            "repeated_rejections": repeated_rejections[:20],
            "schema_drift": schema_drift[:20],
            "source_page_mismatches": source_page_mismatches[:20],
            "low_confidence_records": low_confidence_records[:20],
            "preference_drift": preference_drift[:20],
            "knowledge_gaps": knowledge_gaps[:20],
            "research_topics": research_topics[:20],
            "potential_wiki_pages": potential_wiki_pages[:20],
            "prunable_records": prunable_records[:20],
            "inconsistency_hotspots": inconsistency_hotspots[:20],
            "scope_summary": scope_summary,
            "user_model_summary": user_model_summary[:8],
            "wiki_brain_summary": wiki_brain.get("summary") or {},
            "suggested_new_nodes": [
                "conversation_style_by_contact" if repeated_rejections else "goal",
                "obligation" if stale_items else "constraint",
                "knowledge_article" if knowledge_gaps else "insight",
            ],
        }
        report["recommended_kb_actions"] = self.service._recommended_kb_actions_from_reflection(report)
        report["health_status"] = self.service._reflection_health_label(report.get("summary") or {})

        report_path = self.service._reports_dir() / "knowledge-health-latest.json"
        self.service._write_json(report_path, report)
        markdown_path = self.service._reports_dir() / "knowledge-health-latest.md"
        markdown = self._render_markdown(report)
        self.service._write_text(markdown_path, markdown)

        state["last_reflection_at"] = report["generated_at"]
        state["updated_at"] = report["generated_at"]
        reflections_page = state.setdefault("pages", {}).setdefault(
            "reflections",
            {"title": "Reflections", "description": PAGE_SPECS["reflections"], "records": []},
        )
        reflection_record = {
            "id": f"reflection-{report['generated_at'][:19].replace(':', '-')}",
            "key": "latest_reflection",
            "title": "Knowledge health check",
            "summary": (
                f"Çelişki={report['summary']['contradictions']}, stale={report['summary']['stale_items']}, "
                f"orphan={report['summary']['orphan_pages']}, drift={report['summary']['schema_drift']}, "
                f"gaps={report['summary']['knowledge_gaps']}."
            ),
            "confidence": 0.9,
            "status": "active",
            "source_refs": [str(markdown_path), str(report_path)],
            "signals": ["reflection"],
            "updated_at": report["generated_at"],
            "metadata": {"report_path": str(markdown_path)},
        }
        self.service._upsert_page_record(state, "reflections", reflection_record)
        self.service._save_state(state)
        self.service._render_all(state)
        self.service._append_log("knowledge_reflection", "Knowledge base health check üretildi", report["summary"])
        return {
            **report,
            "report_path": str(markdown_path),
            "report_json_path": str(report_path),
        }

    def _render_markdown(self, report: dict[str, Any]) -> str:
        lines = [
            "# Knowledge Base Health Report",
            "",
            f"- Generated at: {report.get('generated_at')}",
            f"- Contradictions: {report['summary']['contradictions']}",
            f"- Stale items: {report['summary']['stale_items']}",
            f"- Orphan pages: {report['summary']['orphan_pages']}",
            f"- Missing page suggestions: {report['summary']['missing_pages']}",
            f"- Repeated rejections: {report['summary']['repeated_rejections']}",
            f"- Schema drift: {report['summary']['schema_drift']}",
            f"- Source/page mismatches: {report['summary']['source_page_mismatches']}",
            f"- Low confidence records: {report['summary']['low_confidence_records']}",
            f"- Preference drift: {report['summary']['preference_drift']}",
            f"- Prunable records: {report['summary']['prunable_records']}",
            f"- Inconsistency hotspots: {report['summary']['inconsistency_hotspots']}",
            "",
        ]
        for section, title in (
            ("contradictions", "Contradictions"),
            ("stale_items", "Stale Knowledge"),
            ("orphan_pages", "Orphan Pages"),
            ("missing_page_suggestions", "Missing Page Suggestions"),
            ("repeated_rejections", "Repeated Rejections"),
            ("schema_drift", "Schema Drift"),
            ("source_page_mismatches", "Source/Page Mismatches"),
            ("low_confidence_records", "Low Confidence Records"),
            ("preference_drift", "Preference Drift"),
            ("knowledge_gaps", "Knowledge Gaps"),
            ("research_topics", "Research Topics"),
            ("potential_wiki_pages", "Potential Wiki Pages"),
            ("prunable_records", "Prunable Records"),
            ("inconsistency_hotspots", "Inconsistency Hotspots"),
        ):
            lines.append(f"## {title}")
            items = report.get(section) or []
            if not items:
                lines.append("- None")
                lines.append("")
                continue
            for item in items:
                lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
            lines.append("")
        lines.append("## User Model Summary")
        for item in report.get("user_model_summary") or ["None"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Scope Summary")
        if report.get("scope_summary"):
            for key, value in (report.get("scope_summary") or {}).items():
                lines.append(f"- {key}: {value}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("## Wiki Brain Summary")
        if report.get("wiki_brain_summary"):
            for key, value in dict(report.get("wiki_brain_summary") or {}).items():
                lines.append(f"- {key}: {value}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("## Suggested New Nodes")
        for item in report.get("suggested_new_nodes") or ["None"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Recommended KB Actions")
        for item in report.get("recommended_kb_actions") or ["None"]:
            lines.append(f"- {json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else item}")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"


class RecommenderAgent:
    def __init__(self, service: "KnowledgeBaseService") -> None:
        self.service = service

    def recommend(
        self,
        *,
        store: Any,
        settings: Any | None,
        current_context: str | None,
        location_context: str | None,
        limit: int,
        persist: bool,
    ) -> dict[str, Any]:
        self.service.ensure_scaffold()
        from ..assistant import build_assistant_agenda, build_assistant_calendar, build_assistant_inbox

        now = _utcnow()
        state = self.service._load_state()
        profile = store.get_user_profile(self.service.office_id)
        agenda = build_assistant_agenda(store, self.service.office_id)
        inbox = build_assistant_inbox(store, self.service.office_id)
        calendar = build_assistant_calendar(store, self.service.office_id, window_days=7)
        pending_tasks = [item for item in store.list_office_tasks(self.service.office_id) if item.get("status") != "completed"]
        recent_actions = store.list_assistant_actions(self.service.office_id, limit=10)
        preference_controls = self._preference_controls()
        autonomy_controls = self.service._autonomy_preference_signals(state, profile=profile)
        reflection_status = self.service.reflection_status()
        connector_status = self.service.connector_sync_status(store=store)
        suggestion_budget = self.service._autonomy_suggestion_budget(
            controls=autonomy_controls,
            connector_status=connector_status,
            reflection_status=reflection_status,
        )
        assistant_core = self.service.assistant_core_status(store=store)
        coaching_dashboard = self.service.coaching_status(store=store)

        context_text = _compact_text(current_context, limit=280).lower()
        location_text = _compact_text(location_context, limit=140)
        preference_text = " ".join(
            _compact_text(profile.get(field), limit=200).lower()
            for field in (
                "assistant_notes",
                "communication_style",
                "food_preferences",
                "transport_preference",
                "travel_preferences",
            )
        )

        suggestions: list[dict[str, Any]] = []

        if inbox:
            first = inbox[0]
            kind = "email_reply_draft" if str(first.get("source_type") or "") == "email_thread" else "message_draft"
            suggestions.append(
                self._build_recommendation(
                    kind=kind,
                    suggestion=(
                        f"{str(first.get('contact_label') or first.get('title') or 'iletişim')} için kısa bir yanıt taslağı hazırlayabilirim."
                    ),
                    why_this=(
                        f"Yakın dönemde yanıt bekleyen bir iletişim sinyali var: {str(first.get('title') or '').strip() or 'yanıt bekleyen iletişim'}."
                    ),
                    confidence=0.86 if kind == "email_reply_draft" else 0.8,
                    source_basis=[first],
                    next_actions=["Taslak hazırla", "Tonunu seç", "Gerekirse gönderim için onay iste"],
                    action_kind="draft_message",
                    urgency="medium",
                    scope="professional" if first.get("matter_id") else "personal",
                    should_hold_back=False,
                )
            )

        calendar_load = len([item for item in calendar if str(item.get("starts_at") or "").startswith(now.date().isoformat())])
        if calendar_load >= 3 or len(pending_tasks) >= 5:
            suggestions.append(
                self._build_recommendation(
                    kind="daily_plan",
                    suggestion="Bugünün planını hafifletmek için kısa bir öncelik listesi çıkarabilirim.",
                    why_this=f"Takvim yükü={calendar_load}, açık görev sayısı={len(pending_tasks)}. İş yükü sinyali yüksek görünüyor.",
                    confidence=0.72,
                    source_basis=[
                        {"type": "calendar_load", "count": calendar_load},
                        {"type": "pending_tasks", "count": len(pending_tasks)},
                    ],
                    next_actions=["Yüksek öncelikleri sırala", "Akşam yükünü azalt", "İstersen görev taslağı çıkar"],
                    action_kind="create_task_draft",
                    urgency="medium",
                    scope="personal",
                    should_hold_back=False,
                )
            )

        next_event = next((item for item in calendar if item.get("location")), None)
        transport_pref = _compact_text(profile.get("transport_preference"), limit=140)
        if next_event and transport_pref:
            suggestions.append(
                self._build_recommendation(
                    kind="travel_transport_suggestion",
                    suggestion=f"{next_event.get('title') or 'yaklaşan plan'} için ulaşım seçeneğini {transport_pref} tercihine göre netleştirebilirim.",
                    why_this=f"Yaklaşan etkinlikte konum bilgisi var ve kayıtlı ulaşım tercihi bulundu: {transport_pref}.",
                    confidence=0.79,
                    source_basis=[next_event, {"type": "preference", "field": "transport_preference", "value": transport_pref}],
                    next_actions=["Rota opsiyonlarını tart", "Çıkış saatini sor", "Gerekirse rezervasyon öncesi onay iste"],
                    action_kind="reserve_travel",
                    urgency="medium",
                    scope="personal",
                    should_hold_back=False,
                )
            )

        if 18 <= now.hour <= 22 and profile.get("food_preferences"):
            suggestions.append(
                self._build_recommendation(
                    kind="food_suggestion",
                    suggestion="Akşam için kayıtlı damak zevkine uygun hafif bir yemek önerisi çıkarabilirim.",
                    why_this="Akşam saatindeyiz ve yemek tercihi kaydı mevcut. Bu öneri düşük riskli ve isteğe bağlıdır.",
                    confidence=0.63,
                    source_basis=[{"type": "preference", "field": "food_preferences", "value": profile.get("food_preferences")}],
                    next_actions=["İstersen kısa liste çıkar", "Teslimat yoksa sadece öneri sun", "Satın alma için her durumda onay iste"],
                    action_kind="read_summary",
                    urgency="low",
                    scope="personal",
                    should_hold_back=False,
                )
            )

        if (assistant_core.get("supports_coaching") or int((coaching_dashboard.get("summary") or {}).get("active_goals") or 0) > 0) and coaching_dashboard.get("due_checkins"):
            top_goal = dict((coaching_dashboard.get("due_checkins") or [])[0] or {})
            suggestions.append(
                self._build_recommendation(
                    kind="smart_reminder",
                    suggestion=f"{str(top_goal.get('title') or 'Hedef')} için bugünkü kısa ilerleme check-in'ini birlikte yapabiliriz.",
                    why_this=str(top_goal.get("why_now") or "Aktif koçluk hedefi bugün takip bekliyor."),
                    confidence=0.82,
                    source_basis=[
                        {"type": "coach_goal", "id": top_goal.get("id"), "title": top_goal.get("title")},
                        {"type": "progress_ratio", "value": top_goal.get("progress_ratio")},
                    ],
                    next_actions=["İlerleme miktarını gir", "Kısa not ekle", "İstersen yarın için hatırlatma tonunu ayarla"],
                    action_kind="create_task_draft",
                    urgency="medium",
                    scope="personal",
                    should_hold_back=False,
                )
            )

        if location_text:
            suggestions.append(
                self._build_recommendation(
                    kind="place_recommendation",
                    suggestion=f"{location_text} çevresinde sana uygun olabilecek birkaç yer önerebilirim.",
                    why_this="Lokasyon bağlamı verildi. Bu bağlam öneri için yararlı ama dış doğrulama olmadığı için öneri yumuşak tutulmalı.",
                    confidence=0.58,
                    source_basis=[{"type": "location_context", "value": location_text}],
                    next_actions=["Yakın ilgi alanlarını sor", "Dış veri olmadan iddialı öneri verme", "Harita açmadan önce onay iste"],
                    action_kind="read_summary",
                    urgency="low",
                    scope="personal",
                    should_hold_back=False,
                )
            )

        if context_text and any(token in context_text for token in ("namaz", "cami", "mescit")):
            suggestions.append(
                self._build_recommendation(
                    kind="place_recommendation",
                    suggestion="Yakındaki ibadet noktalarını gösterebilirim; önce hassasiyetini ve doğrulama isteğini netleştireyim.",
                    why_this="Dini/kültürel zaman hassasiyetleri yalnız açık sinyal varsa ele alınmalı. Mevcut bağlam açık sinyal içeriyor.",
                    confidence=0.56,
                    source_basis=[{"type": "current_context", "value": context_text}],
                    next_actions=["Önce doğrulama ihtiyacını sor", "Harita veya dış veri için onay iste", "Kesin konum iddiasında bulunma"],
                    action_kind="read_summary",
                    urgency="medium",
                    scope="personal",
                    should_hold_back=False,
                )
            )

        ranked = [
            item
            for item in suggestions
            if not self._is_rate_limited(item["kind"], preference_controls=preference_controls) and item["confidence"] >= 0.55
        ]
        for item in ranked:
            item["recent_related_feedback"] = [
                *list(item.get("recent_related_feedback") or []),
                *list(preference_controls.get("feedback", {}).get(item["kind"], [])),
            ][:5]
            if item["kind"] in preference_controls.get("boosted", set()):
                item["confidence"] = round(min(0.95, float(item["confidence"]) + 0.06), 2)
        ranked.sort(key=lambda item: (item["requires_confirmation"], -float(item["confidence"])))
        selected: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        effective_limit = max(1, min(limit, 10))
        for item in ranked:
            governor = resolve_proactive_policy(
                action_kind=str(item.get("action_kind") or "read_summary"),
                risk_level=item.get("risk_level"),
                policy_label=str(item.get("policy") or ""),
                requires_confirmation=bool(item.get("requires_confirmation")),
                auto_allowed=bool((item.get("policy_decision") or {}).get("auto_allowed", False)),
                scope=str(item.get("scope") or "personal"),
                confidence=float(item.get("confidence") or 0.0),
                urgency=str(item.get("urgency") or "low"),
                reminder_tolerance=str(autonomy_controls.get("reminder_tolerance") or "normal"),
                interruption_tolerance=str(autonomy_controls.get("interruption_tolerance") or "medium"),
                recent_rejection_count=int(autonomy_controls.get("recent_rejection_count") or 0),
                trigger_type=f"recommendation:{item.get('kind') or 'generic'}",
                connector_attention_required=int((connector_status.get("summary") or {}).get("attention_required") or 0),
                reflection_health_status=str(reflection_status.get("health_status") or ""),
                suggestion_budget_remaining=min(suggestion_budget, effective_limit) - len(selected),
                reversible=bool((item.get("action_ladder") or {}).get("reversible", False)),
            )
            item["governor_decision"] = governor.as_dict()
            if governor.decision == "silence":
                suppressed.append({**item, "suppression_reason": governor.suppression_reason})
                continue
            if len(selected) >= min(suggestion_budget, effective_limit):
                suppressed.append({**item, "suppression_reason": "suggestion_budget_exceeded"})
                continue
            selected.append(item)

        created_records: list[dict[str, Any]] = []
        if persist:
            for item in selected:
                outcome = self.service._record_recommendation(item)
                item["history_record_id"] = outcome["history_id"]
                if outcome.get("decision_record"):
                    item["decision_record"] = outcome["decision_record"]
                    created_records.append(outcome["decision_record"])

        self.service._append_log(
            "knowledge_recommendations",
            "Recommendation engine çalıştı",
            {"count": len(selected), "current_context": current_context, "location_context": location_context},
        )
        return {
            "generated_at": _iso_now(),
            "items": selected,
            "suppressed": suppressed,
            "decision_records": created_records,
            "governor": {
                "suggestion_budget": min(suggestion_budget, effective_limit),
                "interruption_tolerance": autonomy_controls.get("interruption_tolerance"),
                "reminder_tolerance": autonomy_controls.get("reminder_tolerance"),
                "recent_rejection_count": autonomy_controls.get("recent_rejection_count"),
            },
        }

    def _build_recommendation(
        self,
        *,
        kind: str,
        suggestion: str,
        why_this: str,
        confidence: float,
        source_basis: list[dict[str, Any]],
        next_actions: list[str],
        action_kind: str,
        urgency: str = "low",
        scope: str = "personal",
        should_hold_back: bool,
    ) -> dict[str, Any]:
        safety = self.service.safety_policy.classify(action_kind)
        execution = evaluate_execution_gateway(
            action_kind=action_kind,
            risk_level=safety.get("level"),
            policy_label=str(safety.get("label") or ""),
            requires_confirmation=bool(safety.get("requires_confirmation")),
            auto_allowed=bool(safety.get("auto_allowed")),
            scope=scope,
            suggest_only=True,
            reversible=action_kind in {"read_summary", "draft_message", "create_task_draft", "update_local_memory"},
            current_stage="suggest",
            preview_summary=str(suggestion or kind),
            audit_label=f"recommendation:{kind}",
        )
        policy_decision = execution.policy_decision
        recommendation_id = f"rec-{kind}-{_fingerprint([kind, suggestion, why_this])[:10]}"
        kb_context = self.service.resolve_relevant_context(
            f"{suggestion} {why_this}",
            scopes=["personal", "professional", "global"],
            limit=4,
            include_decisions=True,
            include_reflections=True,
        )
        return {
            "id": recommendation_id,
            "kind": kind,
            "suggestion": suggestion,
            "why_this": why_this,
            "confidence": round(float(confidence), 2),
            "urgency": urgency,
            "scope": scope,
            "action_kind": action_kind,
            "requires_confirmation": policy_decision.requires_confirmation,
            "source_basis": source_basis,
            "next_actions": next_actions,
            "risk_level": policy_decision.risk_level,
            "policy": policy_decision.policy_label,
            "policy_decision": policy_decision.as_dict(),
            "action_ladder": execution.action_ladder,
            "memory_scope": kb_context.get("scopes") or ["global"],
            "supporting_pages_or_records": kb_context.get("supporting_records") or [],
            "recent_related_feedback": kb_context.get("recent_related_feedback") or [],
            "explainability": {
                "short": why_this,
                "debug": {
                    "source_signals": source_basis,
                    "confidence": round(float(confidence), 2),
                    "hold_back_if": "confidence düşükse veya kaynak bağlamı güncel değilse öneri sunumu yumuşatılmalı",
                    "should_hold_back": should_hold_back,
                    "policy_decision": policy_decision.as_dict(),
                    "supporting_pages": kb_context.get("supporting_pages") or [],
                    "recent_related_feedback": kb_context.get("recent_related_feedback") or [],
                },
            },
        }

    def _preference_controls(self) -> dict[str, Any]:
        state = self.service._load_state()
        controls: dict[str, Any] = {"suppressed": set(), "boosted": set(), "feedback": {}}
        for record in ((state.get("pages") or {}).get("preferences") or {}).get("records", []):
            if not isinstance(record, dict):
                continue
            if str(record.get("status") or "active") != "active":
                continue
            metadata = dict(record.get("metadata") or {})
            kind = str(metadata.get("recommendation_kind") or metadata.get("topic") or "").strip()
            preference_type = str(metadata.get("preference_type") or "").strip()
            if not kind:
                continue
            controls.setdefault("feedback", {}).setdefault(kind, []).append(
                {
                    "id": record.get("id"),
                    "title": record.get("title"),
                    "summary": record.get("summary"),
                    "updated_at": record.get("updated_at"),
                    "preference_type": preference_type,
                }
            )
            if preference_type == "recommendation_suppression":
                controls["suppressed"].add(kind)
            elif preference_type == "proactivity_preference":
                controls["boosted"].add(kind)
        return controls

    def _is_rate_limited(self, kind: str, *, preference_controls: dict[str, Any] | None = None) -> bool:
        controls = preference_controls or self._preference_controls()
        if kind in controls.get("suppressed", set()):
            return True
        state = self.service._load_state()
        history = state.get("recommendation_history") or []
        cooldown_minutes = self.service.recommendation_cooldown_minutes
        if kind in controls.get("boosted", set()):
            cooldown_minutes = max(30, cooldown_minutes // 2)
        window = timedelta(minutes=cooldown_minutes)
        for item in reversed(history):
            if str(item.get("kind") or "") != kind:
                continue
            created_at = str(item.get("created_at") or "")
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
            if _utcnow() - created_dt <= window:
                return True
        return False


class TriggerEngineAgent:
    def __init__(self, service: "KnowledgeBaseService") -> None:
        self.service = service

    def evaluate(
        self,
        *,
        store: Any,
        settings: Any | None,
        now: datetime | None = None,
        persist: bool,
        limit: int,
        include_suppressed: bool,
        forced_types: list[str] | None = None,
    ) -> dict[str, Any]:
        self.service.ensure_scaffold()
        from ..assistant import build_assistant_calendar, build_assistant_inbox

        current_time = now or _utcnow()
        state = self.service._load_state()
        profile = store.get_user_profile(self.service.office_id)
        calendar = build_assistant_calendar(store, self.service.office_id, window_days=2)
        inbox = build_assistant_inbox(store, self.service.office_id)
        pending_tasks = [item for item in store.list_office_tasks(self.service.office_id) if str(item.get("status") or "") != "completed"]
        threads = list(store.list_assistant_threads(self.service.office_id, limit=5) or [])
        location_context = self.service.get_location_context(store=store)
        if location_context.get("current_place"):
            enriched_location = self.service.location_provider.summarize(
                current_place=dict(location_context.get("current_place") or {}),
                recent_places=list(location_context.get("recent_places") or []),
                profile=profile,
            )
            location_context = {
                **location_context,
                **enriched_location,
            }
        preference_controls = self._preference_controls(state)
        autonomy_controls = self.service._autonomy_preference_signals(state, profile=profile)
        connector_status = self.service.connector_sync_status(store=store)
        reflection_status = self.service.reflection_status()
        selected_types = {str(item).strip() for item in list(forced_types or []) if str(item).strip()}

        candidates: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        today_count = len([item for item in calendar if str(item.get("starts_at") or "").startswith(current_time.date().isoformat())])
        overdue_tasks = [
            item
            for item in pending_tasks
            if str(item.get("due_at") or "").strip() and str(item.get("due_at")) < current_time.isoformat()
        ]
        reply_needed = [item for item in inbox if str(item.get("kind") or "").strip() in {"reply_needed", "message_follow_up"}]

        def append_candidate(item: dict[str, Any]) -> None:
            if selected_types and str(item.get("trigger_type") or "") not in selected_types:
                return
            suppression_reason = self._suppression_reason(
                state,
                trigger_type=str(item.get("trigger_type") or ""),
                logical_key=str(item.get("logical_key") or ""),
                scope=str(item.get("scope") or "personal"),
                preference_controls=preference_controls,
                current_time=current_time,
            )
            if suppression_reason:
                suppressed.append({**item, "suppression_reason": suppression_reason})
                return
            candidates.append(item)

        if 7 <= current_time.hour <= 11:
            append_candidate(
                self._build_trigger(
                    trigger_type="daily_planning",
                    logical_key=f"daily-plan:{current_time.date().isoformat()}",
                    title="Günlük plan önerisi",
                    why_now="Günün aktif planlama bandındasın.",
                    why_this_user=f"Takvimde {today_count} kayıt ve {len(pending_tasks)} açık görev var.",
                    confidence=0.78 if today_count or pending_tasks else 0.58,
                    urgency="medium" if today_count or pending_tasks else "low",
                    scope="personal",
                    source_basis=[
                        {"type": "calendar_load", "count": today_count},
                        {"type": "pending_tasks", "count": len(pending_tasks)},
                    ],
                    recommended_action={
                        "kind": "daily_plan",
                        "title": "Hafifletilmiş günlük plan hazırla",
                        "stage": "suggest",
                        "next_stage": "draft",
                    },
                    requires_confirmation=False,
                )
            )

        if today_count >= 4:
            append_candidate(
                self._build_trigger(
                    trigger_type="calendar_load",
                    logical_key=f"calendar-load:{current_time.date().isoformat()}",
                    title="Yoğun takvim uyarısı",
                    why_now=f"Bugün {today_count} ayrı takvim kaydı görünüyor.",
                    why_this_user="Yoğun takvim günlerinde akşam yükünü azaltma ve önceliklendirme sinyali var.",
                    confidence=0.83,
                    urgency="high",
                    scope="professional",
                    source_basis=[{"type": "calendar_load", "count": today_count}],
                    recommended_action={
                        "kind": "calendar_nudge",
                        "title": "Takvim sadeleştirme önerisi hazırla",
                        "stage": "suggest",
                        "next_stage": "draft",
                    },
                    requires_confirmation=False,
                )
            )

        if reply_needed:
            top_item = reply_needed[0]
            append_candidate(
                self._build_trigger(
                    trigger_type="incoming_communication",
                    logical_key=f"inbox:{top_item.get('id') or top_item.get('source_ref')}",
                    title="Yanıt bekleyen iletişim",
                    why_now="Yanıt bekleyen yeni veya açık bir iletişim var.",
                    why_this_user="Daha önce kısa ve net cevap taslakları tercih edildi.",
                    confidence=0.82,
                    urgency="high" if bool(top_item.get("priority") == "high") else "medium",
                    scope="professional" if top_item.get("matter_id") else "personal",
                    source_basis=[top_item],
                    recommended_action={
                        "kind": "email_reply_draft" if str(top_item.get("source_type") or "") == "email_thread" else "message_draft",
                        "title": "Yanıt taslağı hazırla",
                        "stage": "suggest",
                        "next_stage": "draft",
                    },
                    requires_confirmation=False,
                )
            )

        if overdue_tasks:
            append_candidate(
                self._build_trigger(
                    trigger_type="missed_obligation",
                    logical_key=f"overdue:{str(overdue_tasks[0].get('id') or overdue_tasks[0].get('title') or '')}",
                    title="Geciken yükümlülük",
                    why_now=f"{len(overdue_tasks)} görev gecikmiş görünüyor.",
                    why_this_user="Açık yükümlülükler için önce taslak görev/hatırlatma önerisi sunulmalı.",
                    confidence=0.84,
                    urgency="high",
                    scope="professional" if overdue_tasks[0].get("matter_id") else "personal",
                    source_basis=overdue_tasks[:3],
                    recommended_action={
                        "kind": "smart_reminder",
                        "title": "Görev taslağı veya hatırlatma oluştur",
                        "stage": "suggest",
                        "next_stage": "draft",
                    },
                    requires_confirmation=False,
                )
            )

        routine_deviation = self._routine_deviation_signal(state, current_time=current_time, today_count=today_count, location_context=location_context)
        if routine_deviation:
            append_candidate(routine_deviation)

        for coaching_signal in self._coaching_goal_signals(store=store, current_time=current_time):
            append_candidate(coaching_signal)

        location_trigger = self._location_trigger(location_context=location_context, profile=profile, current_time=current_time)
        if location_trigger:
            append_candidate(location_trigger)

        if threads and reply_needed:
            latest_thread_updated = str(threads[0].get("updated_at") or "")
            if latest_thread_updated and latest_thread_updated < (current_time - timedelta(hours=18)).isoformat():
                append_candidate(
                    self._build_trigger(
                        trigger_type="inactivity_follow_up",
                        logical_key=f"follow-up:{threads[0].get('id')}",
                        title="Takip gerektiren sessizlik",
                        why_now="Bir süredir yeni assistant etkileşimi yok ama açık iletişim/görev sinyali sürüyor.",
                        why_this_user="Açık iletişimler beklemede kaldığında nazik takip önerileri yararlı olabilir.",
                        confidence=0.68,
                        urgency="medium",
                        scope="personal",
                        source_basis=[
                            {"type": "thread", "id": threads[0].get("id"), "updated_at": latest_thread_updated},
                            {"type": "reply_needed_count", "count": len(reply_needed)},
                        ],
                        recommended_action={
                            "kind": "smart_reminder",
                            "title": "Takip hatırlatması hazırla",
                            "stage": "suggest",
                            "next_stage": "draft",
                        },
                        requires_confirmation=False,
                    )
                )

        if 12 <= current_time.hour <= 14:
            append_candidate(
                self._build_trigger(
                    trigger_type="time_based",
                    logical_key=f"time-based:{current_time.date().isoformat()}:{current_time.hour // 2}",
                    title="Öğle bandı önerisi",
                    why_now="Öğle saatleri bağlamına girildi.",
                    why_this_user="Zaman bazlı düşük riskli öneriler günlük akışı hafifletebilir.",
                    confidence=0.57,
                    urgency="low",
                    scope="personal",
                    source_basis=[{"type": "clock", "hour": current_time.hour}],
                    recommended_action={
                        "kind": "food_suggestion",
                        "title": "Hafif yemek önerisi sun",
                        "stage": "suggest",
                        "next_stage": "draft",
                    },
                    requires_confirmation=False,
                )
            )

        if 18 <= current_time.hour <= 23 and (pending_tasks or today_count):
            append_candidate(
                self._build_trigger(
                    trigger_type="end_of_day_reflection",
                    logical_key=f"end-of-day:{current_time.date().isoformat()}",
                    title="Gün sonu kapanış önerisi",
                    why_now="Günün sonuna yaklaşılırken açık iş ve kararları toparlamak için uygun zaman.",
                    why_this_user="Akşam yükünü hafifletme ve gün sonu kapanış notu sinyali mevcut.",
                    confidence=0.76,
                    urgency="medium",
                    scope="personal",
                    source_basis=[
                        {"type": "pending_tasks", "count": len(pending_tasks)},
                        {"type": "calendar_load", "count": today_count},
                    ],
                    recommended_action={
                        "kind": "daily_plan",
                        "title": "Gün sonu reflection ve yarın planı hazırla",
                        "stage": "suggest",
                        "next_stage": "draft",
                    },
                    requires_confirmation=False,
                )
            )

        candidates.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2}.get(str(item.get("urgency") or ""), 3), -float(item.get("confidence") or 0.0)))
        suggestion_budget = self.service._autonomy_suggestion_budget(
            controls=autonomy_controls,
            connector_status=connector_status,
            reflection_status=reflection_status,
        )
        selected: list[dict[str, Any]] = []
        for item in candidates:
            governor = resolve_proactive_policy(
                action_kind=str((item.get("recommended_action") or {}).get("action_kind") or "read_summary"),
                risk_level=item.get("risk_level"),
                policy_label=str((item.get("recommended_action") or {}).get("policy") or item.get("policy") or ""),
                requires_confirmation=bool(item.get("requires_confirmation")),
                auto_allowed=bool((item.get("policy_decision") or {}).get("auto_allowed", False)),
                scope=str(item.get("scope") or "personal"),
                confidence=float(item.get("confidence") or 0.0),
                urgency=str(item.get("urgency") or "low"),
                reminder_tolerance=str(autonomy_controls.get("reminder_tolerance") or "normal"),
                interruption_tolerance=str(autonomy_controls.get("interruption_tolerance") or "medium"),
                recent_rejection_count=int(autonomy_controls.get("recent_rejection_count") or 0),
                trigger_type=str(item.get("trigger_type") or ""),
                connector_attention_required=int((connector_status.get("summary") or {}).get("attention_required") or 0),
                reflection_health_status=str(reflection_status.get("health_status") or ""),
                selected_types_forced=bool(selected_types),
                suggestion_budget_remaining=max(1, min(limit, suggestion_budget)) - len(selected),
                reversible=bool((item.get("action_ladder") or {}).get("reversible", False)),
            )
            item["governor_decision"] = governor.as_dict()
            if governor.decision == "silence":
                suppressed.append({**item, "suppression_reason": governor.suppression_reason})
                continue
            if len(selected) >= max(1, min(limit, suggestion_budget)):
                suppressed.append({**item, "suppression_reason": "suggestion_budget_exceeded"})
                continue
            selected.append(item)
        created_records: list[dict[str, Any]] = []
        if persist:
            for item in selected:
                decision_record = self.service.create_decision_record(
                    title=f"Trigger: {item['title']}",
                    summary=item["recommended_action"]["title"],
                    source_refs=list(item.get("source_basis") or []),
                    reasoning_summary=f"{item['why_now']} {item['why_this_user']}",
                    confidence=float(item.get("confidence") or 0.0),
                    user_confirmation_required=bool(item.get("requires_confirmation")),
                    possible_risks=list(item.get("possible_risks") or ["Bağlam değişmiş olabilir.", "Öneri gereksiz görülebilir."]),
                    action_kind=item["recommended_action"].get("action_kind"),
                    intent=item["trigger_type"],
                    alternatives=["Hiç öneri göstermemek", "Daha sonra tekrar denemek"],
                )
                item["decision_record"] = decision_record
                created_records.append(decision_record)
                self.service._record_trigger_event(item, emitted_at=current_time.isoformat())

        self.service._append_log(
            "proactive_trigger_evaluated",
            "Proactive trigger engine çalıştı",
            {"count": len(selected), "suppressed_count": len(suppressed), "forced_types": list(selected_types)},
        )
        return {
            "generated_at": current_time.isoformat(),
            "items": selected,
            "suppressed": suppressed if include_suppressed else [],
            "decision_records": created_records,
            "governor": {
                "suggestion_budget": suggestion_budget,
                "interruption_tolerance": autonomy_controls.get("interruption_tolerance"),
                "reminder_tolerance": autonomy_controls.get("reminder_tolerance"),
                "recent_rejection_count": autonomy_controls.get("recent_rejection_count"),
                "connector_attention_required": int((connector_status.get("summary") or {}).get("attention_required") or 0),
                "reflection_health_status": reflection_status.get("health_status"),
            },
        }

    def _build_trigger(
        self,
        *,
        trigger_type: str,
        logical_key: str,
        title: str,
        why_now: str,
        why_this_user: str,
        confidence: float,
        urgency: str,
        scope: str,
        source_basis: list[dict[str, Any] | str],
        recommended_action: dict[str, Any],
        requires_confirmation: bool,
    ) -> dict[str, Any]:
        action_kind = self._action_kind_for_trigger(recommended_action.get("kind"))
        safety = self.service.safety_policy.classify(action_kind)
        execution = evaluate_execution_gateway(
            action_kind=action_kind,
            risk_level=safety.get("level"),
            policy_label=str(safety.get("label") or ""),
            requires_confirmation=bool(requires_confirmation or safety.get("requires_confirmation")),
            auto_allowed=bool(safety.get("auto_allowed")),
            scope=scope,
            suggest_only=True,
            reversible=str(recommended_action.get("kind") or "") in {"daily_plan", "calendar_nudge", "smart_reminder", "place_recommendation"},
            current_stage=str(recommended_action.get("stage") or "suggest"),
            preview_summary=str(recommended_action.get("title") or title),
            audit_label=f"{trigger_type}:{recommended_action.get('kind') or 'suggestion'}",
        )
        policy_decision = execution.policy_decision
        kb_context = self.service.resolve_relevant_context(
            f"{title} {why_now} {why_this_user}",
            scopes=[scope, "global", "professional", "personal"],
            limit=4,
            include_decisions=True,
            include_reflections=True,
        )
        return {
            "id": f"trigger-{trigger_type}-{_fingerprint([logical_key, title])[:10]}",
            "logical_key": logical_key,
            "trigger_type": trigger_type,
            "title": title,
            "why_now": why_now,
            "why_this_user": why_this_user,
            "confidence": round(float(confidence), 2),
            "urgency": urgency,
            "scope": scope,
            "source_basis": source_basis,
            "recommended_action": {
                **recommended_action,
                "action_kind": action_kind,
                "policy": policy_decision.policy_label,
                "risk_level": policy_decision.risk_level,
                "available_next_stages": execution.action_ladder.get("available_next_stages")
                or ["draft", "preview", "approve"],
            },
            "policy_decision": policy_decision.as_dict(),
            "action_ladder": execution.action_ladder,
            "suppression_reason": None,
            "requires_confirmation": policy_decision.requires_confirmation,
            "risk_level": policy_decision.risk_level,
            "supporting_pages_or_records": kb_context.get("supporting_records") or [],
            "recent_related_feedback": kb_context.get("recent_related_feedback") or [],
            "explainability": {
                "short": f"{why_now} {why_this_user}",
                "debug": {
                    "why_now": why_now,
                    "why_this_user": why_this_user,
                    "source_basis": source_basis,
                    "policy_decision": policy_decision.as_dict(),
                    "supporting_pages": kb_context.get("supporting_pages") or [],
                },
            },
        }

    def _suppression_reason(
        self,
        state: dict[str, Any],
        *,
        trigger_type: str,
        logical_key: str,
        scope: str,
        preference_controls: dict[str, Any],
        current_time: datetime,
    ) -> str | None:
        if trigger_type in preference_controls.get("suppressed", set()):
            return "user_preference_suppressed"
        history = list(state.get("trigger_history") or [])
        cooldown_minutes = TRIGGER_COOLDOWN_MINUTES.get(trigger_type, 180)
        for item in reversed(history):
            if str(item.get("trigger_type") or "") != trigger_type:
                continue
            if str(item.get("logical_key") or "") != logical_key or str(item.get("scope") or "") != scope:
                continue
            created_at = str(item.get("emitted_at") or "")
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
            if current_time - created_dt <= timedelta(minutes=cooldown_minutes):
                return "cooldown_active"
        return None

    @staticmethod
    def _action_kind_for_trigger(kind: Any) -> str:
        normalized = str(kind or "").strip()
        if normalized in {"email_reply_draft", "message_draft", "daily_plan", "food_suggestion", "smart_reminder", "calendar_nudge"}:
            return "draft_message" if "draft" in normalized else "read_summary"
        if normalized in {"travel_transport_suggestion", "place_recommendation"}:
            return "reserve_travel"
        return "read_summary"

    def _preference_controls(self, state: dict[str, Any]) -> dict[str, Any]:
        controls: dict[str, Any] = {"suppressed": set(), "boosted": set(), "feedback": {}}
        for record in ((state.get("pages") or {}).get("preferences") or {}).get("records", []):
            if not isinstance(record, dict):
                continue
            if str(record.get("status") or "active") != "active":
                continue
            metadata = dict(record.get("metadata") or {})
            kind = str(metadata.get("recommendation_kind") or metadata.get("topic") or "").strip()
            preference_type = str(metadata.get("preference_type") or "").strip()
            if not kind:
                continue
            if preference_type == "recommendation_suppression":
                controls["suppressed"].add(kind)
            elif preference_type == "proactivity_preference":
                controls["boosted"].add(kind)
        return controls

    @staticmethod
    def _suggestion_budget(autonomy_controls: dict[str, Any]) -> int:
        budget = 4
        if str(autonomy_controls.get("interruption_tolerance") or "") == "low":
            budget -= 1
        if str(autonomy_controls.get("reminder_tolerance") or "") == "soft":
            budget -= 1
        if int(autonomy_controls.get("recent_rejection_count") or 0) >= 3:
            budget -= 1
        return max(1, budget)

    @staticmethod
    def _governor_suppression_reason(
        *,
        item: dict[str, Any],
        autonomy_controls: dict[str, Any],
        selected_types: set[str],
        ) -> str | None:
        if selected_types:
            return None
        confidence = float(item.get("confidence") or 0.0)
        trigger_type = str(item.get("trigger_type") or "")
        urgency = str(item.get("urgency") or "low")
        fatigue_trigger = trigger_type in {"daily_planning", "time_based", "end_of_day_reflection", "routine_deviation"}
        if (
            fatigue_trigger
            and str(autonomy_controls.get("reminder_tolerance") or "") == "soft"
            and int(autonomy_controls.get("recent_rejection_count") or 0) >= 2
            and urgency != "high"
        ):
            return "fatigue_guard_active"
        if confidence < 0.58 and urgency != "high":
            return "low_confidence_restraint"
        return None

    def _routine_deviation_signal(
        self,
        state: dict[str, Any],
        *,
        current_time: datetime,
        today_count: int,
        location_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        routines = [
            item
            for item in ((state.get("pages") or {}).get("routines") or {}).get("records", [])
            if isinstance(item, dict) and str(item.get("status") or "active") == "active"
        ]
        if not routines:
            return None
        bucket = "morning" if 5 <= current_time.hour < 11 else "midday" if 11 <= current_time.hour < 16 else "evening" if 16 <= current_time.hour < 21 else "night"
        frequent_patterns = list(location_context.get("frequent_patterns") or [])
        current_category = str((location_context.get("current_place") or {}).get("category") or "").strip()
        for routine in routines:
            summary = str(routine.get("summary") or "").lower()
            title = str(routine.get("title") or "")
            expected_bucket = str(((routine.get("metadata") or {}).get("time_bucket") or "")).strip() or (
                "evening" if "akşam" in summary else "morning" if "sabah" in summary else bucket
            )
            if expected_bucket != bucket:
                continue
            if today_count < 3 and current_category:
                continue
            frequent_match = next((item for item in frequent_patterns if str(item.get("time_bucket") or "") == bucket), None)
            reason = "Planlı rutin bandında yoğun takvim veya farklı konum örüntüsü görüldü."
            if frequent_match and current_category and str(frequent_match.get("category") or "") != current_category:
                reason = "Bu saat bandındaki sık yer örüntüsünden sapma görüldü."
            return self._build_trigger(
                trigger_type="routine_deviation",
                logical_key=f"routine:{routine.get('id')}:{current_time.date().isoformat()}",
                title=f"{title or 'Rutin'} için sapma uyarısı",
                why_now=reason,
                why_this_user="Kayıtlı rutin ve zaman hassasiyeti sinyali mevcut.",
                confidence=0.66,
                urgency="medium",
                scope=str(((routine.get("metadata") or {}).get("scope") or "personal")),
                source_basis=[
                    {"type": "routine_record", "id": routine.get("id"), "title": routine.get("title")},
                    {"type": "calendar_load", "count": today_count},
                    {"type": "location_context", "current_category": current_category},
                ],
                recommended_action={
                    "kind": "calendar_nudge",
                    "title": "Rutin koruyucu öneri sun",
                    "stage": "suggest",
                    "next_stage": "draft",
                },
                requires_confirmation=False,
            )
        return None

    def _location_trigger(self, *, location_context: dict[str, Any], profile: dict[str, Any], current_time: datetime) -> dict[str, Any] | None:
        current_place = dict(location_context.get("current_place") or {})
        nearby = list(location_context.get("nearby_candidates") or [])
        if not current_place or not nearby:
            return None
        top = nearby[0]
        area = str(current_place.get("area") or current_place.get("label") or "yakının")
        return self._build_trigger(
            trigger_type="location_context",
            logical_key=f"location:{current_place.get('place_id')}:{current_time.date().isoformat()}",
            title=f"{area} için bağlamsal öneri",
            why_now=f"Şu anki yer bağlamın {current_place.get('category') or 'unknown'} ve zaman dilimi {location_context.get('time_bucket') or 'current'}.",
            why_this_user=str(top.get("reason") or "Yer örüntüsü ve tercih sinyali bulundu."),
            confidence=float(top.get("confidence") or 0.6),
            urgency="low",
            scope=str(current_place.get("scope") or "personal"),
            source_basis=[
                {"type": "current_place", **current_place},
                {"type": "nearby_candidate", **top},
                {"type": "food_preferences", "value": profile.get("food_preferences")},
            ],
            recommended_action={
                "kind": "place_recommendation",
                "title": f"{top.get('title') or 'Yakın yer'} için yönlendirme hazırla",
                "stage": "suggest",
                "next_stage": "preview",
            },
            requires_confirmation=False,
        )

    def _coaching_goal_signals(self, *, store: Any, current_time: datetime) -> list[dict[str, Any]]:
        assistant_core = self.service.assistant_core_status(store=store)
        dashboard = self.service.coaching_status(store=store)
        if not assistant_core.get("supports_coaching") and int((dashboard.get("summary") or {}).get("active_goals") or 0) <= 0:
            return []
        results: list[dict[str, Any]] = []
        for item in list(dashboard.get("due_checkins") or [])[:4]:
            goal_id = str(item.get("id") or "").strip()
            cadence = str(item.get("cadence") or "").strip()
            trigger_type = "routine_deviation" if cadence in {"daily", "weekly"} else "missed_obligation"
            results.append(
                self._build_trigger(
                    trigger_type=trigger_type,
                    logical_key=f"coach:{goal_id}:{current_time.date().isoformat()}",
                    title=f"{str(item.get('title') or 'Hedef')} için check-in",
                    why_now=str(item.get("why_now") or "Koçluk hedefi bugün takip bekliyor."),
                    why_this_user=(
                        f"Bu hedef {str(item.get('cadence') or 'active')} kadansla izleniyor"
                        + (f"; kalan miktar {item.get('remaining_value_text')}" if item.get("remaining_value_text") else ".")
                    ),
                    confidence=0.8 if bool(item.get("needs_attention")) else 0.72,
                    urgency="high" if bool(item.get("needs_attention")) else "medium",
                    scope=str(item.get("scope") or "personal"),
                    source_basis=[
                        {"type": "coach_goal", "id": goal_id, "title": item.get("title")},
                        {"type": "progress_ratio", "value": item.get("progress_ratio")},
                        {"type": "next_check_in_at", "value": item.get("next_check_in_at")},
                    ],
                    recommended_action={
                        "kind": "smart_reminder",
                        "title": "İlerleme check-in'i hazırla",
                        "stage": "suggest",
                        "next_stage": "preview",
                    },
                    requires_confirmation=False,
                )
            )
        return results


class ActionAgent:
    def __init__(self, service: "KnowledgeBaseService") -> None:
        self.service = service

    def build_hook(
        self,
        hook_name: str,
        *,
        store: Any,
        settings: Any | None,
        context: dict[str, Any] | None,
        user_prompt: str | None,
        persist: bool,
    ) -> dict[str, Any]:
        self.service.ensure_scaffold()
        hook = str(hook_name or "").strip()
        if hook not in PROACTIVE_HOOKS:
            raise ValueError("unsupported_hook")
        payload = dict(context or {})
        prompt = _compact_text(user_prompt, limit=1000)
        profile = store.get_user_profile(self.service.office_id)
        safety = self.service.safety_policy.classify("draft_message" if "draft" in hook else "read_summary")

        if hook == "email_reply_draft":
            subject = _compact_text(payload.get("subject"), limit=160) or "yanıt bekleyen e-posta"
            contact = _compact_text(payload.get("contact_name"), limit=120) or "karşı taraf"
            body = f"Merhaba {contact},\n\n{subject} konusunda kısa ve net bir dönüş hazırladım. Uygun görürsen bunu birlikte son haline getirebiliriz.\n\nSelamlar"
            suggestion = {
                "title": f"{contact} için e-posta taslağı",
                "summary": "Suggest-only modunda kısa bir yanıt taslağı üretildi.",
                "draft": body,
            }
        elif hook == "message_draft":
            contact = _compact_text(payload.get("contact_name"), limit=120) or "karşı taraf"
            body = f"{contact}, notunu gördüm. Kısa bir taslak çıkardım; istersen birlikte netleştirelim."
            suggestion = {"title": f"{contact} için mesaj taslağı", "summary": "Kısa mesaj taslağı", "draft": body}
        elif hook == "smart_reminder":
            suggestion = {
                "title": "Akıllı hatırlatma önerisi",
                "summary": "Yoğunluk ve açık işler dikkate alınarak nazik bir hatırlatma üretildi.",
                "draft": _compact_text(prompt or payload.get("task") or "Bugün için en kritik işi netleştir.", limit=200),
            }
        elif hook == "place_recommendation":
            location = _compact_text(payload.get("location"), limit=120) or "yakın çevre"
            suggestion = {
                "title": f"{location} için yer önerisi",
                "summary": "Dış doğrulama olmadan yalnız suggest-only bağlam önerisi üretildi.",
                "draft": f"{location} çevresinde ilgini çekebilecek birkaç seçeneği önce kategori bazında daraltabilirim.",
            }
        elif hook == "food_suggestion":
            preference = _compact_text(profile.get("food_preferences"), limit=180) or "hafif yemek"
            suggestion = {
                "title": "Yemek önerisi",
                "summary": "Kayıtlı tercihlere göre yumuşak öneri.",
                "draft": f"Geçmiş tercihlerine göre bugün {preference} ekseninde hafif seçenekler daha uygun olabilir.",
            }
        elif hook == "travel_transport_suggestion":
            transport = _compact_text(profile.get("transport_preference"), limit=120) or "uygun ulaşım seçeneği"
            suggestion = {
                "title": "Ulaşım önerisi",
                "summary": "Suggest-only rota ve ulaşım önerisi.",
                "draft": f"Varsayılan tercihin {transport}; istersen buna göre rota ve zaman planı çıkarayım.",
            }
        elif hook == "calendar_nudge":
            suggestion = {
                "title": "Takvim odaklı dürtme",
                "summary": "Yaklaşan plan ve iş yüküne göre hafif uyarı.",
                "draft": "Takvimin yoğun görünüyor; akşam planını sadeleştirmek isteyebilirsin.",
            }
        else:
            suggestion = {
                "title": "Günlük plan önerisi",
                "summary": "Suggest-only günlük plan iskeleti.",
                "draft": "İlk blok: kritik iş, ikinci blok: iletişimler, son blok: hafif kapanış.",
            }

        decision = None
        file_back = None
        if persist:
            decision = self.service.create_decision_record(
                title=suggestion["title"],
                summary=suggestion["summary"],
                source_refs=[{"hook": hook, "context": payload}],
                reasoning_summary=f"{hook} için suggest-only yardımcı çıktı üretildi.",
                confidence=0.7,
                user_confirmation_required=bool(safety.get("requires_confirmation")),
                possible_risks=["Kullanıcı tonuna tam uymayabilir", "Dış veri doğrulanmadı"],
                action_kind="draft_message" if "draft" in hook else "read_summary",
                intent=hook,
                alternatives=["Hiç öneri sunmamak", "Sadece soru sorup bağlam toplamak"],
            )
            file_back = self.service.maybe_file_back_response(
                kind="daily_planning_output" if hook == "daily_plan" else "draft_style_learning" if "draft" in hook else "assistant_reply",
                title=suggestion["title"],
                content="\n".join([suggestion["summary"], suggestion["draft"]]).strip(),
                source_refs=[{"hook": hook, "context": payload}],
                metadata={
                    "page_key": "projects" if hook == "daily_plan" else "preferences" if "draft" in hook else "recommendations",
                    "record_type": "goal" if hook == "daily_plan" else "conversation_style" if "draft" in hook else "recommendation",
                    "scope": "personal",
                },
                scope="personal",
                sensitivity="medium" if hook == "daily_plan" else "high",
            )

        return {
            "hook": hook,
            "suggestion": suggestion,
            "requires_confirmation": bool(safety.get("requires_confirmation")),
            "risk_level": safety.get("level"),
            "policy": safety.get("label"),
            "decision_record": decision,
            "action_ladder": {
                "current_stage": "suggest",
                "available_next_stages": ["draft", "preview", "one_click_approve"],
                "manual_review_required": bool(safety.get("requires_confirmation")),
                "risk_level": safety.get("level"),
                "execution_policy": "preview_then_confirm",
                "approval_reason": "Suggest-only hook çıktıları kullanıcı onayı olmadan kalıcı dış aksiyona dönüşmez.",
                "irreversible": False,
            },
            "file_back": file_back,
        }


class KnowledgeBaseService:
    def __init__(
        self,
        root_dir: Path,
        office_id: str,
        *,
        enabled: bool = True,
        excluded_patterns: tuple[str, ...] = (),
        recommendation_cooldown_minutes: int = 180,
        search_backend: str = "sqlite_hybrid_fts_v1",
        dense_candidates_enabled: bool = False,
        semantic_backend: str = "heuristic",
        embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        cross_encoder_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        reranker_mode: str = "local_heuristic",
        location_provider_mode: str = "desktop_file_fallback",
        location_snapshot_path: Path | None = None,
        article_runtime: Any | None = None,
        runtime_events: Any | None = None,
        epistemic: Any | None = None,
        enable_llm_article_authoring: bool = True,
        llm_article_limit: int = 4,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.office_id = office_id
        self.enabled = enabled
        self.excluded_patterns = tuple(pattern for pattern in excluded_patterns if pattern)
        self.recommendation_cooldown_minutes = recommendation_cooldown_minutes
        self.base_dir = self.root_dir / _slugify(office_id)
        self.raw_dir = self.base_dir / "raw"
        self.wiki_dir = self.base_dir / "wiki"
        self.system_dir = self.base_dir / "system"
        self.retrieval_backend, self.retrieval_pipeline = build_retrieval_backend(
            search_backend=search_backend,
            system_dir=self.system_dir,
            dense_candidates_enabled=dense_candidates_enabled,
            semantic_backend=semantic_backend,
            embedding_model_name=embedding_model_name,
            cross_encoder_model_name=cross_encoder_model_name,
            reranker_mode=reranker_mode,
        )
        self.search_backend = self.retrieval_backend.name
        self.connector_registry = build_default_connector_registry()
        self.location_provider = MockLocationProvider()
        self.location_provider_mode = str(location_provider_mode or "desktop_file_fallback").strip() or "desktop_file_fallback"
        self.location_snapshot_path = Path(location_snapshot_path) if location_snapshot_path else None
        self.location_snapshot_provider = (
            FileBackedLocationProvider(self.location_snapshot_path, fallback_provider=self.location_provider)
            if self.location_snapshot_path and self.location_provider_mode in {"desktop_file_fallback", "desktop_file_only"}
            else None
        )
        self.article_runtime = article_runtime
        self.runtime_events = runtime_events
        self.epistemic = epistemic
        self.enable_llm_article_authoring = bool(enable_llm_article_authoring)
        self.llm_article_limit = max(1, int(llm_article_limit or 4))
        self._orchestration_mutex = threading.Lock()
        self._render_mutex = threading.RLock()

        self.safety_policy = SafetyPolicyAgent(self)
        self.wiki_maintainer = WikiMaintainerAgent(self)
        self.ingest_agent = IngestAgent(self)
        self.reflection_agent = ReflectionAgent(self)
        self.recommender_agent = RecommenderAgent(self)
        self.trigger_engine = TriggerEngineAgent(self)
        self.action_agent = ActionAgent(self)

    def _log_runtime_event(self, event: str, *, level: str = "info", **data: Any) -> None:
        if self.runtime_events is None:
            return
        try:
            self.runtime_events.log(event, level=level, office_id=self.office_id, **data)
        except Exception:
            return

    def ensure_scaffold(self) -> None:
        if not self.enabled:
            return
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.system_dir.mkdir(parents=True, exist_ok=True)
        self._normalized_dir().mkdir(parents=True, exist_ok=True)
        self._reports_dir().mkdir(parents=True, exist_ok=True)
        self._decisions_dir().mkdir(parents=True, exist_ok=True)
        self._concepts_dir().mkdir(parents=True, exist_ok=True)
        state = self._load_state()
        if not self._state_path().exists():
            self._save_state(state)
        if self._scaffold_artifacts_ready():
            return
        with self._render_mutex:
            state = self._load_state()
            if not self._state_path().exists():
                self._save_state(state)
            if self._scaffold_artifacts_ready():
                return
            self._render_all(state)

    def _scaffold_artifacts_ready(self) -> bool:
        required_paths = (
            self._state_path(),
            self._wiki_brain_path(),
            self._wiki_graph_path(),
            self.system_dir / "AGENTS.md",
            self.system_dir / "CONTROL.md",
            self.system_dir / "INDEX.md",
            self._concepts_dir() / "INDEX.md",
        )
        return all(path.exists() for path in required_paths)

    def wiki_brain_status(self, *, ensure: bool = False, previews: bool = False) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "concept_count": 0,
                "article_count": 0,
                "graph_edges": 0,
            }
        if ensure:
            self.ensure_scaffold()
        state = self._load_state() if self.base_dir.exists() else self._default_state()
        brain_path = self._wiki_brain_path()
        if brain_path.exists():
            try:
                brain = json.loads(self._read_text_lossy(brain_path))
            except json.JSONDecodeError:
                with self._render_mutex:
                    state = self._load_state() if self.base_dir.exists() else self._default_state()
                    brain = self._build_wiki_brain(state)
                    self._persist_wiki_brain_artifacts(brain)
        else:
            with self._render_mutex:
                if brain_path.exists():
                    brain = json.loads(self._read_text_lossy(brain_path))
                else:
                    state = self._load_state() if self.base_dir.exists() else self._default_state()
                    brain = self._build_wiki_brain(state)
                    self._persist_wiki_brain_artifacts(brain)
        concepts = list(brain.get("concepts") or [])
        graph = dict(brain.get("graph") or {})
        concept_index_path = self._concepts_dir() / "INDEX.md"
        synthesis_report_path = self._reports_dir() / "knowledge-synthesis-latest.json"
        latest_synthesis = None
        if synthesis_report_path.exists():
            try:
                latest_synthesis = json.loads(self._read_text_lossy(synthesis_report_path))
            except json.JSONDecodeError:
                latest_synthesis = None
        return {
            "enabled": True,
            "summary": dict(brain.get("summary") or {}),
            "concept_count": len(concepts),
            "article_count": len(concepts),
            "graph_edges": len(list(graph.get("edges") or [])),
            "index_path": str(concept_index_path),
            "brain_path": str(brain_path),
            "graph_path": str(self._wiki_graph_path()),
            "report_path": str(self._reports_dir() / "wiki-brain-latest.md"),
            "latest_synthesis": latest_synthesis,
            "concepts": [
                {
                    "key": item.get("key"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "path": item.get("path"),
                    "priority_score": item.get("priority_score"),
                    "authoring_mode": ((item.get("authoring") or {}).get("mode") or "unknown"),
                    "scope_summary": item.get("scope_summary"),
                    "record_type_counts": item.get("record_type_counts"),
                    "updated_at": item.get("updated_at"),
                    "preview": self._read_text_lossy(Path(str(item.get("path"))))[:1600]
                    if previews and str(item.get("path") or "").strip() and Path(str(item.get("path"))).exists()
                    else "",
                }
                for item in concepts[:12]
            ],
        }

    def compile_wiki_brain(self, *, reason: str = "manual_wiki_compile", previews: bool = False) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        self._render_all(state)
        state = self._load_state()
        state["wiki_brain"] = {
            **dict(state.get("wiki_brain") or {}),
            "last_compiled_at": _iso_now(),
            "last_compile_reason": reason,
        }
        state["updated_at"] = _iso_now()
        self._save_state(state)
        result = self.wiki_brain_status(ensure=False, previews=previews)
        self._append_log(
            "wiki_compiled",
            "Concept article ve backlink graph yeniden derlendi",
            {"reason": reason, "concept_count": result.get("concept_count"), "graph_edges": result.get("graph_edges")},
        )
        return {"reason": reason, **result}

    def status(self, *, ensure: bool = False, previews: bool = False) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "root_path": str(self.base_dir),
                "office_id": self.office_id,
                "pages": [],
                "raw_source_count": 0,
                "system_files": [],
                "last_reflection_at": None,
            }
        if ensure:
            self.ensure_scaffold()
        state = self._load_state() if self.base_dir.exists() else self._default_state()
        raw_source_count = len(_list_files(self.raw_dir, ".json")) if self.raw_dir.exists() else 0
        pages = []
        for key, description in PAGE_SPECS.items():
            path = self.wiki_dir / f"{key}.md"
            page = state.get("pages", {}).get(key) or {}
            pages.append(
                {
                    "key": key,
                    "path": str(path),
                    "title": key.title(),
                    "description": description,
                    "record_count": len(page.get("records") or []),
                    "exists": path.exists(),
                    "preview": self._read_text_lossy(path)[:1600] if previews and path.exists() else "",
                }
            )
        system_files = []
        for path in self._memory_explorer_system_files():
            system_files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "exists": path.exists(),
                    "preview": self._read_text_lossy(path)[:1600] if previews and path.exists() else "",
                }
            )
        return {
            "enabled": True,
            "root_path": str(self.base_dir),
            "office_id": self.office_id,
            "pages": pages,
            "raw_source_count": raw_source_count,
            "system_files": system_files,
            "decision_record_count": len(state.get("decision_records") or []),
            "recommendation_history_count": len(state.get("recommendation_history") or []),
            "trigger_history_count": len(state.get("trigger_history") or []),
            "connector_sync_count": len((state.get("connector_sync") or {}).get("connectors") or {}),
            "connector_sync_status": self.connector_sync_status(store=None),
            "search_backend": self.search_backend,
            "location_context_available": bool((state.get("location_context") or {}).get("current_place")),
            "orchestration_status": self.orchestration_status(),
            "memory_overview": self.memory_overview(),
            "assistant_core": self.assistant_core_status(),
            "coaching_dashboard": self.coaching_status(),
            "wiki_brain": self.wiki_brain_status(ensure=False, previews=previews),
            "last_reflection_at": state.get("last_reflection_at"),
            "reflection_status": self.reflection_status(),
            "autonomy_status": self.autonomy_status(),
            "state_path": str(self._state_path()),
        }

    def system_status(
        self,
        *,
        store: Any | None = None,
        settings: Any | None = None,
        workspace_status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        memory_overview = self.memory_overview()
        assistant_core = self.assistant_core_status(store=store)
        connector_sync = self.connector_sync_status(store=store)
        reflection = self.reflection_status()
        orchestration = self.orchestration_status()
        autonomy = self.autonomy_status(store=store, settings=settings)
        location_context = self.get_location_context(store=store)
        workspace_root = store.get_active_workspace_root(self.office_id) if store is not None and hasattr(store, "get_active_workspace_root") else None

        if bool((workspace_status or {}).get("bootstrap_required")):
            operating_posture = "bootstrap"
        elif str(reflection.get("health_status") or "") in {"attention_required", "critical"} or int((connector_sync.get("summary") or {}).get("attention_required") or 0) > 0:
            operating_posture = "stabilize"
        elif int(autonomy.get("open_loop_count") or 0) > 0:
            operating_posture = "active_assist"
        else:
            operating_posture = "steady_state"

        canonical_sources = [
            {
                "key": "assistant_identity",
                "source": "assistant_runtime_profile -> workspace/IDENTITY.md",
                "scope": "assistant",
                "status": "ready",
            },
            {
                "key": "system_contract",
                "source": "workspace/SYSTEM.md + workspace/.openclaw/system-status.json",
                "scope": "runtime_contract",
                "status": "ready" if bool((workspace_status or {}).get("system_path")) else "partial",
            },
            {
                "key": "behavior_rules",
                "source": "workspace/AGENTS.md + workspace/SOUL.md",
                "scope": "assistant",
                "status": "ready",
            },
            {
                "key": "user_profile",
                "source": "user_profile -> workspace/USER.md",
                "scope": "personal",
                "status": "ready",
            },
            {
                "key": "current_context",
                "source": "workspace/CONTEXT.md + workspace/MEMORY.md + workspace/PROGRESS.md",
                "scope": "runtime",
                "status": "ready" if workspace_status else "partial",
            },
            {
                "key": "long_term_memory",
                "source": str(self.base_dir),
                "scope": "personal_kb",
                "status": "ready" if self.enabled else "disabled",
            },
            {
                "key": "workspace_documents",
                "source": workspace_root.get("root_path") if isinstance(workspace_root, dict) else None,
                "scope": "workspace",
                "status": "ready" if workspace_root else "missing",
            },
        ]

        return {
            "generated_at": _iso_now(),
            "office_id": self.office_id,
            "operating_posture": operating_posture,
            "workspace": {
                "configured": bool(workspace_root),
                "display_name": workspace_root.get("display_name") if isinstance(workspace_root, dict) else None,
                "root_path": workspace_root.get("root_path") if isinstance(workspace_root, dict) else None,
                "runtime": workspace_status or {},
            },
            "knowledge_base": {
                "enabled": self.enabled,
                "root_path": str(self.base_dir),
                "search_backend": self.search_backend,
                "page_count": len(state.get("pages") or {}),
                "decision_record_count": len(state.get("decision_records") or []),
                "recommendation_history_count": len(state.get("recommendation_history") or []),
                "trigger_history_count": len(state.get("trigger_history") or []),
            },
            "counts": {
                "knowledge_records": int((memory_overview.get("counts") or {}).get("records") or 0),
                "connected_accounts": int((connector_sync.get("summary") or {}).get("connected_providers") or 0),
                "open_loops": int(autonomy.get("open_loop_count") or 0),
                "reflection_actions": len(list(reflection.get("recommended_kb_actions") or [])),
            },
            "assistant_core": {
                "summary": assistant_core.get("summary") or {},
                "supports_coaching": assistant_core.get("supports_coaching"),
                "active_form_count": len(list(assistant_core.get("active_forms") or [])),
            },
            "execution_policy": {
                "default": ((autonomy.get("policy") or {}).get("default_execution_policy") or "preview_then_confirm"),
                "draft_first_external_actions": True,
                "legal_scope_confirmation_required": True,
                "payment_confirmation_required": True,
                "irreversible_actions_auto": False,
            },
            "connector_sync": connector_sync,
            "reflection_status": reflection,
            "orchestration_status": orchestration,
            "autonomy_status": autonomy,
            "location_context": {
                "has_current_place": bool((location_context or {}).get("current_place")),
                "provider_status": (location_context or {}).get("provider_status"),
                "permission_state": (location_context or {}).get("permission_state"),
                "capture_mode": (location_context or {}).get("capture_mode"),
            },
            "canonical_sources": canonical_sources,
            "action_pipeline": [
                {"step": "sync_profiles_and_connectors", "source": "store + connector mirrors", "goal": "güncel veri tabanı ve hesap durumu"},
                {"step": "resolve_runtime_context", "source": "workspace markdown + KB context", "goal": "anlık öncelikleri ve hafızayı sabitle"},
                {"step": "search_local_sources", "source": "workspace + personal-kb", "goal": "yerel dayanağı öne almak"},
                {"step": "use_low_risk_tools", "source": "tool registry", "goal": "okuma/analiz düzeyinde güvenli araç kullanımı"},
                {"step": "draft_then_confirm", "source": "approval policy", "goal": "dış aksiyonları taslak ve onay akışında tutmak"},
            ],
        }

    def reflection_status(self) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        current = dict(state.get("reflection_status") or {})
        last_reflection_at = str(state.get("last_reflection_at") or current.get("last_success_at") or "").strip() or None
        cadence_seconds = self._orchestration_job_interval_seconds("reflection_pass")
        next_due_at = str(current.get("next_due_at") or "").strip() or None
        if not next_due_at and last_reflection_at:
            last_reflection_dt = _iso_to_datetime(last_reflection_at)
            if last_reflection_dt is not None:
                next_due_at = (last_reflection_dt + timedelta(seconds=cadence_seconds)).isoformat()
        next_due_dt = _iso_to_datetime(next_due_at or "")
        now = _utcnow()
        summary = dict(current.get("summary") or {})
        if not summary:
            report_path = self._reports_dir() / "knowledge-health-latest.json"
            if report_path.exists():
                try:
                    summary = dict(json.loads(self._read_text_lossy(report_path)).get("summary") or {})
                except json.JSONDecodeError:
                    summary = {}
        status_value = str(current.get("status") or ("completed" if last_reflection_at else "idle")).strip() or "idle"
        health_status = str(current.get("health_status") or self._reflection_health_label(summary)).strip() or "healthy"
        return {
            "status": status_value,
            "health_status": health_status,
            "last_started_at": current.get("last_started_at"),
            "last_attempted_at": current.get("last_attempted_at"),
            "last_completed_at": current.get("last_completed_at") or last_reflection_at,
            "last_success_at": current.get("last_success_at") or last_reflection_at,
            "last_reflection_at": last_reflection_at,
            "last_error": current.get("last_error"),
            "consecutive_failures": int(current.get("consecutive_failures") or 0),
            "retry_delay_seconds": current.get("retry_delay_seconds"),
            "next_due_at": next_due_at,
            "next_due_in_seconds": max(0, int((next_due_dt - now).total_seconds())) if next_due_dt is not None else None,
            "is_due": bool(next_due_dt is None or next_due_dt <= now),
            "summary": summary,
            "recommended_kb_actions": list(current.get("recommended_kb_actions") or []),
            "report_path": current.get("report_path"),
            "report_json_path": current.get("report_json_path"),
        }

    def autonomy_status(
        self,
        *,
        store: Any | None = None,
        settings: Any | None = None,
        now: datetime | None = None,
        persist: bool = False,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        current_time = now or _utcnow()
        state = self._load_state()
        profile = store.get_user_profile(self.office_id) if store is not None else {}
        controls = self._autonomy_preference_signals(state, profile=profile)
        connector_status = self.connector_sync_status(store=store)
        reflection_status = self.reflection_status()
        coaching_dashboard = self.coaching_status(store=store)
        pending_tasks = [
            item
            for item in (store.list_office_tasks(self.office_id) if store is not None and hasattr(store, "list_office_tasks") else [])
            if str(item.get("status") or "") != "completed"
        ]
        open_loops: list[dict[str, Any]] = []
        for item in pending_tasks[:8]:
            priority = "high" if str(item.get("priority") or "").lower() == "high" else "medium"
            open_loops.append(
                {
                    "kind": "task",
                    "title": str(item.get("title") or "Açık görev"),
                    "summary": str(item.get("explanation") or item.get("title") or "").strip(),
                    "scope": f"project:matter-{item.get('matter_id')}" if item.get("matter_id") else "personal",
                    "priority": priority,
                    "source_ref": f"task:{item.get('id')}",
                }
            )
        for item in list((coaching_dashboard.get("due_checkins") or []))[:4]:
            open_loops.append(
                {
                    "kind": "coach_checkin",
                    "title": str(item.get("title") or "Hedef check-in"),
                    "summary": str(item.get("why_now") or "Takip gerekiyor."),
                    "scope": str(item.get("scope") or "personal"),
                    "priority": "high" if bool(item.get("needs_attention")) else "medium",
                    "source_ref": f"coach:{item.get('id')}",
                }
            )
        if int((connector_status.get("summary") or {}).get("attention_required") or 0) > 0:
            open_loops.append(
                {
                    "kind": "connector_health",
                    "title": "Bağlayıcı sağlığı dikkat istiyor",
                    "summary": f"{int((connector_status.get('summary') or {}).get('attention_required') or 0)} connector dikkat gerektiriyor.",
                    "scope": "global",
                    "priority": "high" if int((connector_status.get("summary") or {}).get("retry_scheduled") or 0) > 0 else "medium",
                    "source_ref": "connector_sync_status",
                }
            )
        if reflection_status.get("is_due") or str(reflection_status.get("health_status") or "") in {"attention_required", "critical"}:
            open_loops.append(
                {
                    "kind": "reflection",
                    "title": "Knowledge reflection bekliyor",
                    "summary": "Knowledge health check tekrar çalıştırılmalı veya bulgular gözden geçirilmeli.",
                    "scope": "global",
                    "priority": "high" if reflection_status.get("is_due") else "medium",
                    "source_ref": "reflection_status",
                }
            )
        matters_now = sorted(
            open_loops,
            key=lambda item: ({"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority") or "low"), 3), str(item.get("title") or "")),
        )[:8]
        suggestion_budget = self._autonomy_suggestion_budget(controls=controls, connector_status=connector_status, reflection_status=reflection_status)
        silence_reasons: list[str] = []
        if suggestion_budget <= 1:
            silence_reasons.append("Interruption tolerance ve reminder fatigue nedeniyle aynı anda az öneri gösterilecek.")
        if str(reflection_status.get("health_status") or "") in {"attention_required", "critical"}:
            silence_reasons.append("Knowledge health dikkat gerektirdiği için düşük güvenli öneriler baskılanacak.")
        if int((connector_status.get("summary") or {}).get("attention_required") or 0) > 0:
            silence_reasons.append("Stale veya hatalı connector senkronları varken dış bağlam önerileri daha temkinli kullanılacak.")
        policy = {
            "suggestion_budget": suggestion_budget,
            "interruption_tolerance": controls.get("interruption_tolerance"),
            "reminder_tolerance": controls.get("reminder_tolerance"),
            "suppressed_topics": controls.get("suppressed_topics") or [],
            "boosted_topics": controls.get("boosted_topics") or [],
            "recent_rejection_count": int(controls.get("recent_rejection_count") or 0),
            "low_confidence_restraint": True,
            "legal_scope_confirmation_required": True,
            "default_execution_policy": "preview_then_confirm",
        }
        payload = {
            "generated_at": current_time.isoformat(),
            "status": "guarded" if silence_reasons else "active",
            "policy": policy,
            "matters_now": matters_now,
            "open_loop_count": len(open_loops),
            "reflection_health": {
                "status": reflection_status.get("health_status"),
                "is_due": reflection_status.get("is_due"),
                "recommended_action_count": len(list(reflection_status.get("recommended_kb_actions") or [])),
            },
            "connector_health": {
                "attention_required": int((connector_status.get("summary") or {}).get("attention_required") or 0),
                "retry_scheduled": int((connector_status.get("summary") or {}).get("retry_scheduled") or 0),
                "stale_connectors": int((connector_status.get("summary") or {}).get("stale_connectors") or 0),
            },
            "silence_reasons": silence_reasons,
        }
        if persist:
            persisted_state = self._load_state()
            persisted_state["autonomy_status"] = payload
            persisted_state["updated_at"] = _iso_now()
            self._save_state(persisted_state)
        return payload

    @staticmethod
    def _reflection_health_label(summary: dict[str, Any]) -> str:
        contradictions = int(summary.get("contradictions") or 0)
        stale_items = int(summary.get("stale_items") or 0)
        knowledge_gaps = int(summary.get("knowledge_gaps") or 0)
        prunable_records = int(summary.get("prunable_records") or 0)
        severity_score = (contradictions * 2) + stale_items + knowledge_gaps + prunable_records
        if severity_score >= 8:
            return "critical"
        if severity_score >= 2:
            return "attention_required"
        return "healthy"

    def _recommended_kb_actions_from_reflection(self, report: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for item in list(report.get("contradictions") or [])[:4]:
            actions.append(
                {
                    "action": "review_contradiction",
                    "priority": "high",
                    "page_key": item.get("page"),
                    "record_keys": list(item.get("record_ids") or []),
                    "reason": f"{item.get('page')} içinde çelişki bulundu.",
                }
            )
        for item in list(report.get("stale_items") or [])[:4]:
            actions.append(
                {
                    "action": "refresh_record",
                    "priority": "medium" if int(item.get("age_days") or 0) < 180 else "high",
                    "page_key": item.get("page"),
                    "record_id": item.get("record_id"),
                    "reason": f"Kayıt {int(item.get('age_days') or 0)} gündür güncellenmedi.",
                }
            )
        for item in list(report.get("knowledge_gaps") or [])[:3]:
            actions.append(
                {
                    "action": "compile_or_create_article",
                    "priority": "medium",
                    "page_key": "concepts",
                    "concept_key": item.get("concept_key") or item.get("kind"),
                    "reason": str(item.get("reason") or "Knowledge gap bulundu."),
                }
            )
        for item in list(report.get("potential_wiki_pages") or [])[:3]:
            actions.append(
                {
                    "action": "open_wiki_candidate",
                    "priority": "medium",
                    "page_key": item.get("page_key"),
                    "reason": str(item.get("reason") or "Yeni wiki page adayı üretildi."),
                }
            )
        for item in list(report.get("prunable_records") or [])[:3]:
            actions.append(
                {
                    "action": "review_prunable_record",
                    "priority": "low",
                    "page_key": item.get("page"),
                    "record_id": item.get("record_id"),
                    "reason": "Düşük güven veya yüksek düzeltme geçmişi nedeniyle prune adayı.",
                }
            )
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in actions:
            marker = json.dumps(
                [
                    item.get("action"),
                    item.get("page_key"),
                    item.get("record_id"),
                    item.get("concept_key"),
                    item.get("reason"),
                ],
                ensure_ascii=False,
                sort_keys=True,
            )
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(item)
        return deduped[:10]

    def _build_reflection_status_payload(self, report: dict[str, Any]) -> dict[str, Any]:
        generated_at = str(report.get("generated_at") or _iso_now())
        cadence_seconds = self._orchestration_job_interval_seconds("reflection_pass")
        next_due_at = (_iso_to_datetime(generated_at) or _utcnow()) + timedelta(seconds=cadence_seconds)
        summary = dict(report.get("summary") or {})
        return {
            "status": "completed",
            "health_status": str(report.get("health_status") or self._reflection_health_label(summary)),
            "last_started_at": generated_at,
            "last_attempted_at": generated_at,
            "last_completed_at": generated_at,
            "last_success_at": generated_at,
            "last_error": None,
            "consecutive_failures": 0,
            "retry_delay_seconds": 0,
            "next_due_at": next_due_at.isoformat(),
            "summary": summary,
            "recommended_kb_actions": list(report.get("recommended_kb_actions") or []),
            "report_path": report.get("report_path"),
            "report_json_path": report.get("report_json_path"),
        }

    def _autonomy_preference_signals(self, state: dict[str, Any], *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
        reminder_tolerance = "normal"
        interruption_tolerance = "medium"
        suppressed_topics: set[str] = set()
        boosted_topics: set[str] = set()
        for record in ((state.get("pages") or {}).get("preferences") or {}).get("records", []):
            if not isinstance(record, dict) or str(record.get("status") or "active") != "active":
                continue
            metadata = dict(record.get("metadata") or {})
            summary = str(record.get("summary") or "").lower()
            preference_type = str(metadata.get("preference_type") or metadata.get("field") or "").strip()
            topic = str(metadata.get("recommendation_kind") or metadata.get("topic") or "").strip()
            if preference_type == "recommendation_suppression" and topic:
                suppressed_topics.add(topic)
            if preference_type == "proactivity_preference" and topic:
                boosted_topics.add(topic)
            if preference_type == "reminder_tolerance" or "hatırlatma" in summary or "reminder" in summary:
                if any(token in summary for token in ("seyrek", "yumusak", "yumuşak", "nazik", "daha az")):
                    reminder_tolerance = "soft"
                elif any(token in summary for token in ("görünür", "goster", "aktif", "sık")):
                    reminder_tolerance = "high"
            if preference_type == "interruption_tolerance":
                if any(token in summary for token in ("düşük", "dusuk", "rahatsiz", "az böl", "az bol")):
                    interruption_tolerance = "low"
                elif any(token in summary for token in ("yüksek", "yuksek", "aktif")):
                    interruption_tolerance = "high"
        history = list(state.get("recommendation_history") or [])
        recent_rejections = [
            item
            for item in history[-12:]
            if str(item.get("outcome") or "") == "rejected"
        ]
        if recent_rejections and reminder_tolerance == "normal":
            reminder_tolerance = "soft"
        if len(recent_rejections) >= 3 and interruption_tolerance == "medium":
            interruption_tolerance = "low"
        profile_text = " ".join(
            [
                str((profile or {}).get("assistant_notes") or ""),
                str((profile or {}).get("communication_style") or ""),
            ]
        ).lower()
        if interruption_tolerance == "medium" and any(token in profile_text for token in ("kısa", "kisa", "net", "yormadan")):
            interruption_tolerance = "low"
        return {
            "reminder_tolerance": reminder_tolerance,
            "interruption_tolerance": interruption_tolerance,
            "suppressed_topics": sorted(suppressed_topics),
            "boosted_topics": sorted(boosted_topics),
            "recent_rejection_count": len(recent_rejections),
        }

    @staticmethod
    def _autonomy_suggestion_budget(
        *,
        controls: dict[str, Any],
        connector_status: dict[str, Any],
        reflection_status: dict[str, Any],
    ) -> int:
        budget = 4
        if str(controls.get("interruption_tolerance") or "") == "low":
            budget -= 1
        if str(controls.get("reminder_tolerance") or "") == "soft":
            budget -= 1
        if int(controls.get("recent_rejection_count") or 0) >= 3:
            budget -= 1
        if int((connector_status.get("summary") or {}).get("attention_required") or 0) >= 2:
            budget -= 1
        if str(reflection_status.get("health_status") or "") == "critical":
            budget -= 1
        return max(1, min(4, budget))

    def sync_from_store(self, *, store: Any, settings: Any | None = None, reason: str = "profile_sync") -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}
        self.ensure_scaffold()
        profile = store.get_user_profile(self.office_id)
        runtime_profile = store.get_assistant_runtime_profile(self.office_id)
        snapshot = {
            "profile": profile,
            "runtime_profile": runtime_profile,
            "reason": reason,
        }
        snapshot_fingerprint = _fingerprint(snapshot)
        state = self._load_state()
        last_sync_fingerprint = str(((state.get("profile_sync") or {}).get("fingerprint")) or "")
        raw_source_ref = None
        raw_compile_updated_pages: list[str] = []
        raw_compile_contradictions: list[dict[str, Any]] = []
        if snapshot_fingerprint != last_sync_fingerprint:
            if any(
                _compact_text(profile.get(field), limit=10)
                for field in ("display_name", "assistant_notes", "food_preferences", "transport_preference", "communication_style")
            ) or _compact_text(runtime_profile.get("assistant_name"), limit=10):
                raw_result = self.ingest(
                    source_type="profile_snapshot",
                    content=json.dumps(snapshot, ensure_ascii=False),
                    title="Profile snapshot",
                    metadata={"reason": reason},
                    occurred_at=_iso_now(),
                    source_ref=f"profile-sync:{snapshot_fingerprint[:10]}",
                    tags=["profile", "runtime"],
                    render=False,
                )
                raw_source_ref = str((raw_result.get("raw") or {}).get("path") or "")
                raw_compile_updated_pages.extend(list((raw_result.get("compile") or {}).get("updated_pages") or []))
                raw_compile_contradictions.extend(list((raw_result.get("compile") or {}).get("contradictions") or []))
            state = self._load_state()
            state["profile_sync"] = {"fingerprint": snapshot_fingerprint, "synced_at": _iso_now(), "reason": reason}
            self._save_state(state)
        result = self.wiki_maintainer.sync_profiles(profile, runtime_profile, raw_source_ref=raw_source_ref, render=False)
        connector_sync = self._sync_connector_records(store, reason=reason, render=False)
        operational_sync = self._sync_operational_store_records(store, reason=reason, render=False)
        preference_consolidation = self.consolidate_preference_learning(store=store, reason=f"{reason}:sync", render=False)
        combined_updated_pages = sorted(
            set(
                [
                    *raw_compile_updated_pages,
                    *(result.get("updated_pages") or []),
                    *(connector_sync.get("updated_pages") or []),
                    *(operational_sync.get("updated_pages") or []),
                    *(preference_consolidation.get("updated_pages") or []),
                ]
            )
        )
        if combined_updated_pages:
            current_state = self._load_state()
            current_state["updated_at"] = _iso_now()
            self._save_state(current_state)
            self._render_all(current_state)
        self._append_log(
            "profile_sync",
            "Profil ve runtime bilgileri knowledge base ile senkronlandı",
            {
                "reason": reason,
                "updated_pages": combined_updated_pages,
                "connector_record_count": connector_sync.get("synced_record_count", 0),
                "operational_record_count": operational_sync.get("synced_record_count", 0),
                "preference_learning_records": preference_consolidation.get("record_count", 0),
            },
        )
        return {
            "updated_pages": combined_updated_pages,
            "contradictions": [
                *raw_compile_contradictions,
                *(result.get("contradictions") or []),
                *(connector_sync.get("contradictions") or []),
                *(operational_sync.get("contradictions") or []),
            ],
            "connector_sync": connector_sync,
            "operational_sync": operational_sync,
            "preference_consolidation": preference_consolidation,
        }

    def ingest(
        self,
        *,
        source_type: str,
        content: str,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: str | None = None,
        source_ref: str | None = None,
        tags: list[str] | None = None,
        render: bool = True,
    ) -> dict[str, Any]:
        return self.ingest_agent.ingest(
            source_type=source_type,
            content=content,
            title=title,
            metadata=metadata,
            occurred_at=occurred_at,
            source_ref=source_ref,
            tags=tags,
            render=render,
        )

    def run_reflection(self) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        current_time = _utcnow()
        started_at = current_time.isoformat()
        cadence_seconds = self._orchestration_job_interval_seconds("reflection_pass")
        prior_status = dict(state.get("reflection_status") or {})
        state["reflection_status"] = {
            **prior_status,
            "status": "running",
            "last_started_at": started_at,
            "last_attempted_at": started_at,
            "health_status": str(prior_status.get("health_status") or "running"),
        }
        state["updated_at"] = _iso_now()
        self._save_state(state)
        try:
            payload = self.reflection_agent.run()
        except Exception as exc:
            failed_state = self._load_state()
            previous = dict(failed_state.get("reflection_status") or {})
            failure_count = int(previous.get("consecutive_failures") or 0) + 1
            retry_seconds = self._orchestration_retry_seconds(
                cadence_seconds=cadence_seconds,
                failure_count=failure_count,
            )
            next_due_at = (current_time + timedelta(seconds=retry_seconds)).isoformat()
            failed_state["reflection_status"] = {
                **previous,
                "status": "retry_scheduled",
                "last_completed_at": _iso_now(),
                "last_error": str(exc),
                "consecutive_failures": failure_count,
                "retry_delay_seconds": retry_seconds,
                "next_due_at": next_due_at,
                "health_status": "attention_required",
                "recommended_kb_actions": [],
            }
            failed_state["updated_at"] = _iso_now()
            self._save_state(failed_state)
            self._append_log(
                "knowledge_reflection_failed",
                "Knowledge reflection başarısız oldu",
                {"error": str(exc), "retry_delay_seconds": retry_seconds, "next_due_at": next_due_at},
            )
            self._log_runtime_event(
                "personal_kb_reflection_failed",
                level="warning",
                error=str(exc),
                retry_delay_seconds=retry_seconds,
                next_due_at=next_due_at,
                consecutive_failures=failure_count,
            )
            raise
        status_payload = self._build_reflection_status_payload(payload)
        finalized_state = self._load_state()
        finalized_state["reflection_status"] = status_payload
        finalized_state["last_reflection_at"] = payload.get("generated_at")
        finalized_state["updated_at"] = _iso_now()
        self._save_state(finalized_state)
        self.maybe_file_back_response(
            kind="reflection_output",
            title="Knowledge reflection summary",
            content=json.dumps(payload.get("summary") or {}, ensure_ascii=False),
            source_refs=[payload.get("report_path"), payload.get("report_json_path")],
            metadata={
                "page_key": "reflections",
                "record_type": "reflection",
                "scope": "global",
            },
            scope="global",
            sensitivity="medium",
        )
        self._log_runtime_event(
            "personal_kb_reflection_completed",
            health_status=status_payload.get("health_status"),
            recommended_kb_action_count=len(list(status_payload.get("recommended_kb_actions") or [])),
            report_path=status_payload.get("report_path"),
        )
        return {
            **payload,
            "status": status_payload,
        }

    def run_knowledge_synthesis(self, *, reason: str = "knowledge_synthesis") -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        history = list(state.get("recommendation_history") or [])
        trigger_history = list(state.get("trigger_history") or [])
        location_context = dict(state.get("location_context") or {})
        updated_pages: list[str] = []
        generated_records: list[tuple[str, dict[str, Any]]] = []
        generated_strategies: list[dict[str, Any]] = []
        hypotheses: list[dict[str, Any]] = []
        now = _iso_now()

        accepted_evening = [
            item
            for item in history
            if str(item.get("kind") or "") in {"daily_plan", "calendar_nudge", "food_suggestion"}
            and str(item.get("outcome") or "") == "accepted"
        ]
        if len(accepted_evening) >= 2:
            record = self._knowledge_insight_record(
                page_key="preferences",
                record_key="insight:planning_style:evening",
                title="Akşam plan önerileri olumlu karşılanıyor",
                summary="Kullanıcı akşam saatlerinde hafifletilmiş plan ve kapanış önerilerine olumlu tepki veriyor.",
                scope="personal",
                source_refs=[f"recommendation:{item.get('id')}" for item in accepted_evening[:6]],
                metadata={
                    "record_type": "insight",
                    "insight_type": "acceptance_pattern",
                    "source_basis": [f"recommendation:{item.get('id')}" for item in accepted_evening[:8]],
                    "confidence": 0.78,
                    "relations": [{"relation_type": "supports", "target": "daily_planning"}],
                },
            )
            if self._upsert_page_record(state, "preferences", record).get("updated"):
                updated_pages.append("preferences")
            generated_records.append(("preferences", record))
            strategy_record = self._knowledge_insight_record(
                page_key="recommendations",
                record_key="strategy:daily_planning:evening_priority",
                title="Akşam plan stratejisi",
                summary="Akşam saatlerinde kapanış, hafifletme ve kısa günlük plan preview'lerini öncele.",
                scope="personal",
                source_refs=[f"recommendation:{item.get('id')}" for item in accepted_evening[:6]],
                metadata={
                    "record_type": "insight",
                    "insight_type": "strategy",
                    "strategy_kind": "daily_planning_focus",
                    "source_basis": [f"recommendation:{item.get('id')}" for item in accepted_evening[:8]],
                    "confidence": 0.8,
                    "importance_score": 1.12,
                    "relations": [
                        {"relation_type": "supports", "target": "daily_plan"},
                        {"relation_type": "relevant_to", "target": "end_of_day_reflection"},
                    ],
                },
            )
            if self._upsert_page_record(state, "recommendations", strategy_record).get("updated"):
                updated_pages.append("recommendations")
            generated_records.append(("recommendations", strategy_record))
            generated_strategies.append(
                {
                    "page_key": "recommendations",
                    "record_id": strategy_record.get("id"),
                    "title": strategy_record.get("title"),
                    "summary": strategy_record.get("summary"),
                }
            )
            hypotheses.append(
                {
                    "title": "Akşam kapanış desteği yüksek değer üretiyor",
                    "summary": "Kullanıcı gün sonu plan hafifletme ve kapanış yardımlarına diğer zaman bantlarından daha sıcak yaklaşıyor olabilir.",
                    "confidence": 0.66,
                }
            )

        rejected_reminders = [
            item
            for item in history
            if str(item.get("kind") or "") in {"smart_reminder", "daily_plan"}
            and str(item.get("outcome") or "") == "rejected"
        ]
        if len(rejected_reminders) >= 2:
            record = self._knowledge_insight_record(
                page_key="preferences",
                record_key="insight:reminder_tolerance:soft",
                title="Hatırlatma yorgunluğu sinyali",
                summary="Sık veya yüksek sürtünmeli hatırlatmalar reddediliyor; daha yumuşak ve seyrek öneri dili tercih edilmeli.",
                scope="personal",
                source_refs=[f"recommendation:{item.get('id')}" for item in rejected_reminders[:6]],
                metadata={
                    "record_type": "insight",
                    "insight_type": "rejection_pattern",
                    "source_basis": [f"recommendation:{item.get('id')}" for item in rejected_reminders[:8]],
                    "confidence": 0.76,
                    "relations": [{"relation_type": "avoids", "target": "high_frequency_reminders"}],
                },
            )
            if self._upsert_page_record(state, "preferences", record).get("updated"):
                updated_pages.append("preferences")
            generated_records.append(("preferences", record))
            strategy_record = self._knowledge_insight_record(
                page_key="recommendations",
                record_key="strategy:reminder_tolerance:low_friction",
                title="Düşük sürtünmeli reminder stratejisi",
                summary="Hatırlatmalar daha seyrek, daha yumuşak tonda ve preview-first biçimde sunulmalı.",
                scope="personal",
                source_refs=[f"recommendation:{item.get('id')}" for item in rejected_reminders[:6]],
                metadata={
                    "record_type": "insight",
                    "insight_type": "strategy",
                    "strategy_kind": "reminder_fatigue_reduction",
                    "source_basis": [f"recommendation:{item.get('id')}" for item in rejected_reminders[:8]],
                    "confidence": 0.79,
                    "importance_score": 1.08,
                    "relations": [
                        {"relation_type": "avoids", "target": "high_frequency_reminders"},
                        {"relation_type": "supports", "target": "smart_reminder"},
                    ],
                },
            )
            if self._upsert_page_record(state, "recommendations", strategy_record).get("updated"):
                updated_pages.append("recommendations")
            generated_records.append(("recommendations", strategy_record))
            generated_strategies.append(
                {
                    "page_key": "recommendations",
                    "record_id": strategy_record.get("id"),
                    "title": strategy_record.get("title"),
                    "summary": strategy_record.get("summary"),
                }
            )
            hypotheses.append(
                {
                    "title": "Reminder fatigue var",
                    "summary": "Kullanıcı aynı gün içindeki sık reminder önerilerine karşı toleransı düşük olabilir.",
                    "confidence": 0.7,
                }
            )

        evening_triggers = [
            item for item in trigger_history
            if str(item.get("trigger_type") or "") in {"daily_planning", "end_of_day_reflection"}
        ]
        if len(evening_triggers) >= 2:
            record = self._knowledge_insight_record(
                page_key="routines",
                record_key="insight:routine:evening_closure",
                title="Akşam kapanış rutini",
                summary="Günün sonuna doğru plan hafifletme ve reflection önerileri daha anlamlı bir yardım yüzeyi oluşturuyor.",
                scope="personal",
                source_refs=[f"trigger:{item.get('id')}" for item in evening_triggers[-6:]],
                metadata={
                    "record_type": "insight",
                    "insight_type": "trigger_pattern",
                    "source_basis": [f"trigger:{item.get('id')}" for item in evening_triggers[-8:]],
                    "confidence": 0.68,
                    "relations": [{"relation_type": "supports", "target": "end_of_day_reflection"}],
                },
            )
            if self._upsert_page_record(state, "routines", record).get("updated"):
                updated_pages.append("routines")
            generated_records.append(("routines", record))

        frequent_patterns = list(location_context.get("frequent_patterns") or [])
        strong_pattern = next((item for item in frequent_patterns if int(item.get("count") or 0) >= 2), None)
        if strong_pattern:
            bucket = str(strong_pattern.get("time_bucket") or "current")
            category = str(strong_pattern.get("category") or "place")
            record = self._knowledge_insight_record(
                page_key="places",
                record_key=f"insight:place_pattern:{bucket}:{category}",
                title=f"{_humanize_identifier(bucket)} yer örüntüsü",
                summary=f"{bucket} saat bandında {category} tipi yerlere tekrar eden bir eğilim var.",
                scope="personal",
                source_refs=[str(item) for item in list(location_context.get("source_refs") or [])[:4]],
                metadata={
                    "record_type": "insight",
                    "insight_type": "location_pattern",
                    "source_basis": [location_context.get("provider") or location_context.get("source") or "location_context"],
                    "confidence": 0.67,
                    "category": category,
                    "time_bucket": bucket,
                    "relations": [{"relation_type": "relevant_to", "target": f"place_category:{category}"}],
                },
            )
            if self._upsert_page_record(state, "places", record).get("updated"):
                updated_pages.append("places")
            generated_records.append(("places", record))
            generated_strategies.append(
                {
                    "page_key": "places",
                    "record_id": record.get("id"),
                    "title": f"{_humanize_identifier(bucket)} konum stratejisi",
                    "summary": f"{bucket} saatlerinde {category} kategorisini proactive place recommendation içinde öncele.",
                }
            )
            hypotheses.append(
                {
                    "title": "Yer-zaman örüntüsü stabil",
                    "summary": f"{bucket} bandında {category} tipi yerlere yönelim tekrar ediyor; yakın yer yönlendirmeleri bu bağlamı kullanmalı.",
                    "confidence": 0.62,
                }
            )

        report = {
            "generated_at": now,
            "reason": reason,
            "summary": {
                "generated_records": len(generated_records),
                "updated_pages": len(sorted(set(updated_pages))),
                "generated_strategies": len(generated_strategies),
                "hypotheses": len(hypotheses),
            },
            "insights": [
                {
                    "page_key": page_key,
                    "record_id": record.get("id"),
                    "title": record.get("title"),
                    "summary": record.get("summary"),
                    "record_type": ((record.get("metadata") or {}).get("record_type") or "insight"),
                    "source_basis": list(((record.get("metadata") or {}).get("source_basis") or []))[:8],
                    "confidence": record.get("confidence"),
                }
                for page_key, record in generated_records
            ],
            "strategies": generated_strategies,
            "hypotheses": hypotheses[:8],
        }
        report_path = self._reports_dir() / "knowledge-synthesis-latest.json"
        self._write_json(report_path, report)
        markdown_path = self._reports_dir() / "knowledge-synthesis-latest.md"
        self._write_text(markdown_path, self._render_knowledge_synthesis_markdown(report))
        state["wiki_brain"] = {
            **dict(state.get("wiki_brain") or {}),
            "last_synthesis_at": now,
            "last_synthesis_summary": report.get("summary") or {},
            "report_path": str(markdown_path),
        }
        state["updated_at"] = now
        self._save_state(state)
        self._render_all(state)
        self._append_log(
            "knowledge_synthesis",
            "Knowledge synthesis loop yeni insight kayıtları üretti",
            {
                "reason": reason,
                "generated_records": len(generated_records),
                "generated_strategies": len(generated_strategies),
                "updated_pages": sorted(set(updated_pages)),
            },
        )
        return {
            **report,
            "report_path": str(markdown_path),
            "report_json_path": str(report_path),
            "updated_pages": sorted(set(updated_pages)),
        }

    def recommend(
        self,
        *,
        store: Any,
        settings: Any | None = None,
        current_context: str | None = None,
        location_context: str | None = None,
        limit: int = 3,
        persist: bool = True,
    ) -> dict[str, Any]:
        return self.recommender_agent.recommend(
            store=store,
            settings=settings,
            current_context=current_context,
            location_context=location_context,
            limit=limit,
            persist=persist,
        )

    def build_proactive_hook(
        self,
        hook_name: str,
        *,
        store: Any,
        settings: Any | None = None,
        context: dict[str, Any] | None = None,
        user_prompt: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        return self.action_agent.build_hook(
            hook_name,
            store=store,
            settings=settings,
            context=context,
            user_prompt=user_prompt,
            persist=persist,
        )

    def record_location_context(
        self,
        *,
        current_place: dict[str, Any] | None = None,
        recent_places: list[dict[str, Any]] | None = None,
        nearby_categories: list[str] | None = None,
        observed_at: str | None = None,
        source: str = "manual",
        scope: str = "personal",
        sensitivity: str = "high",
        source_ref: str | None = None,
        provider: str | None = None,
        provider_mode: str | None = None,
        provider_status: str | None = None,
        capture_mode: str | None = None,
        permission_state: str | None = None,
        privacy_mode: bool | None = None,
        capture_failure_reason: str | None = None,
        persist_raw: bool = True,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        current_payload = dict(current_place or {})
        normalized_current = None
        if _has_meaningful_location_payload(current_payload):
            current_payload.setdefault("scope", scope)
            current_payload.setdefault("sensitivity", sensitivity)
            current_payload.setdefault("observed_at", observed_at or _iso_now())
            normalized_current = self.location_provider.normalize_observation(current_payload)
        normalized_recent = [
            self.location_provider.normalize_observation(
                {
                    **dict(item or {}),
                    "scope": str(item.get("scope") or scope),
                    "sensitivity": str(item.get("sensitivity") or sensitivity),
                }
            )
            for item in list(recent_places or [])
            if isinstance(item, dict) and _has_meaningful_location_payload(item)
        ]
        if normalized_current:
            normalized_recent = [normalized_current, *normalized_recent]
        deduped_recent: list[dict[str, Any]] = []
        seen_place_ids: set[str] = set()
        for item in normalized_recent:
            marker = str(item.get("place_id") or item.get("label") or "")
            if not marker or marker in seen_place_ids:
                continue
            seen_place_ids.add(marker)
            deduped_recent.append(item)
        summary = self.location_provider.summarize(
            current_place=normalized_current,
            recent_places=deduped_recent[:8],
            profile={
                "nearby_categories": list(nearby_categories or []),
            },
        )
        provider_name = str(provider or summary.get("provider") or self.location_provider.name).strip() or self.location_provider.name
        provider_mode_value = str(provider_mode or summary.get("provider_mode") or "manual_memory").strip() or "manual_memory"
        provider_status_value = str(provider_status or summary.get("provider_status") or "manual").strip().lower() or "manual"
        capture_mode_value = str(capture_mode or summary.get("capture_mode") or "manual_memory").strip() or "manual_memory"
        permission_state_value = str(permission_state or summary.get("permission_state") or "").strip().lower() or None
        capture_failure_reason_value = _compact_text(capture_failure_reason or summary.get("capture_failure_reason"), limit=600) or None
        location_explainability = dict(summary.get("location_explainability") or {})
        if source in {"browser_geolocation", "desktop_geolocation_capture"}:
            if not provider:
                provider_name = "desktop_browser_capture_v1"
            if not provider_mode:
                provider_mode_value = "desktop_renderer_geolocation"
            if not provider_status:
                provider_status_value = "fresh"
            if not capture_mode:
                capture_mode_value = "device_capture"
            if provider_status_value == "fresh":
                permission_state_value = permission_state_value or "granted"
        if privacy_mode is not None:
            location_explainability["privacy_mode"] = bool(privacy_mode)
        if permission_state_value:
            location_explainability["permission_state"] = permission_state_value
        if provider_status_value:
            location_explainability.setdefault(
                "status_reason",
                "Konum bağlamı cihazdan alınan konum ve son kayıtlı gözlem ile güncellendi."
                if provider_status_value == "fresh"
                else f"Konum bağlamı {provider_status_value} durumunda tutuluyor.",
            )
        if capture_failure_reason_value:
            location_explainability["status_reason"] = (
                f"{str(location_explainability.get('status_reason') or '').strip()} "
                f"Son konum alma denemesi başarısız oldu: {capture_failure_reason_value}."
            ).strip()

        state = self._load_state()
        state["location_context"] = {
            **summary,
            "updated_at": _iso_now(),
            "source": source,
            "scope": scope,
            "sensitivity": sensitivity,
            "provider": provider_name,
            "provider_mode": provider_mode_value,
            "provider_status": provider_status_value,
            "capture_mode": capture_mode_value,
            "observed_at": observed_at or summary.get("observed_at") or (normalized_current or {}).get("started_at"),
            "permission_state": permission_state_value,
            "privacy_mode": bool(privacy_mode) if privacy_mode is not None else bool(summary.get("privacy_mode")),
            "capture_failure_reason": capture_failure_reason_value,
            "freshness_label": summary.get("freshness_label"),
            "freshness_minutes": summary.get("freshness_minutes"),
            "location_explainability": location_explainability,
        }
        state["updated_at"] = _iso_now()
        self._save_state(state)

        if persist_raw and (normalized_current or deduped_recent):
            location_payload = {
                "source": source,
                "scope": scope,
                "sensitivity": sensitivity,
                "current_place": normalized_current,
                "recent_places": deduped_recent[:8],
                "nearby_categories": list(nearby_categories or []),
            }
            self.ingest(
                source_type="location_events",
                title=_compact_text((normalized_current or {}).get("label"), limit=120) or "Location context update",
                content=json.dumps(location_payload, ensure_ascii=False),
                metadata={
                    "scope": scope,
                    "sensitivity": sensitivity,
                    "place_name": (normalized_current or {}).get("label"),
                    "place_category": (normalized_current or {}).get("category"),
                    "area": (normalized_current or {}).get("area"),
                    "source": source,
                },
                occurred_at=observed_at or _iso_now(),
                source_ref=source_ref or f"location-context:{source}:{_fingerprint(location_payload)[:10]}",
                tags=["location", "context", source],
            )

        if normalized_current:
            self._upsert_location_page_records(
                current_place=normalized_current,
                frequent_patterns=list(summary.get("frequent_patterns") or []),
            )
        self._append_log(
            "location_context_recorded",
            "Location/context state güncellendi",
            {
                "source": source,
                "place": (normalized_current or {}).get("label"),
                "provider_status": provider_status_value,
                "permission_state": permission_state_value,
                "nearby_candidate_count": len(list(summary.get("nearby_candidates") or [])),
            },
        )
        return state["location_context"]

    def get_location_context(self, *, store: Any | None = None) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        current = dict(state.get("location_context") or {})
        current_observed = _iso_to_datetime(str(current.get("observed_at") or current.get("updated_at") or ""))
        current_has_runtime_state = bool(
            current.get("provider_status")
            or current.get("permission_state")
            or current.get("capture_failure_reason")
            or current.get("privacy_mode")
        )
        current_is_fresh = bool(
            (current.get("current_place") or current_has_runtime_state)
            and current_observed
            and (datetime.now(timezone.utc) - current_observed) <= timedelta(minutes=90)
        )
        if (current.get("current_place") or current_has_runtime_state) and current_is_fresh:
            return current
        if store is None:
            return current
        profile = store.get_user_profile(self.office_id) or {}
        if self.location_snapshot_provider is not None:
            snapshot_context = self.location_snapshot_provider.load_context(profile=profile)
            if snapshot_context:
                state["location_context"] = {
                    **snapshot_context,
                    "updated_at": _iso_now(),
                    "scope": snapshot_context.get("scope") or "personal",
                    "sensitivity": snapshot_context.get("sensitivity") or "high",
                    "capture_mode": snapshot_context.get("capture_mode") or "snapshot_fallback",
                }
                state["updated_at"] = _iso_now()
                self._save_state(state)
                if snapshot_context.get("current_place"):
                    self._upsert_location_page_records(
                        current_place=dict(snapshot_context.get("current_place") or {}),
                        frequent_patterns=list(snapshot_context.get("frequent_patterns") or []),
                    )
                return state["location_context"]
        guessed_location = _compact_text(profile.get("current_location"), limit=160)
        if not guessed_location:
            return current
        return self.record_location_context(
            current_place={
                "place_id": f"profile-{_slugify(guessed_location)}",
                "label": guessed_location,
                "category": "user_reported_location",
                "source": "profile_hint",
                "scope": "personal",
                "sensitivity": "high",
            },
            recent_places=[],
            nearby_categories=[],
            source="profile_hint",
            persist_raw=False,
        )

    def evaluate_triggers(
        self,
        *,
        store: Any,
        settings: Any | None = None,
        now: datetime | None = None,
        persist: bool = True,
        limit: int = 4,
        include_suppressed: bool = False,
        forced_types: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.trigger_engine.evaluate(
            store=store,
            settings=settings,
            now=now,
            persist=persist,
            limit=limit,
            include_suppressed=include_suppressed,
            forced_types=forced_types,
        )

    def orchestration_status(self) -> dict[str, Any]:
        state = self._load_state()
        orchestration = dict(state.get("orchestration") or {})
        jobs = dict(orchestration.get("jobs") or {})
        now = _utcnow()
        normalized_jobs = []
        for payload in list(jobs.values())[-12:]:
            prior = dict(payload or {})
            job_name = str(prior.get("job") or "")
            cadence_seconds = int(prior.get("cadence_seconds") or self._orchestration_job_interval_seconds(job_name))
            next_due_at = str(prior.get("next_due_at") or "") or self._orchestration_next_due_at(job_name=job_name, prior=prior)
            status_value = str(prior.get("status") or "idle").strip() or "idle"
            last_started_at = _iso_to_datetime(str(prior.get("last_started_at") or prior.get("last_attempted_at") or ""))
            lock_timeout_seconds = self._orchestration_lock_timeout_seconds(job_name)
            stale_lock = bool(
                status_value == "running"
                and last_started_at
                and (now - last_started_at) > timedelta(seconds=lock_timeout_seconds)
            )
            if stale_lock:
                status_value = "retry_scheduled"
                if not next_due_at:
                    next_due_at = (now + timedelta(seconds=max(60, cadence_seconds // 2))).isoformat()
            next_due_dt = _iso_to_datetime(next_due_at)
            next_due_in_seconds = None
            if next_due_dt is not None:
                next_due_in_seconds = max(0, int((next_due_dt - now).total_seconds()))
            status_message = self._orchestration_status_message(
                job_name=job_name,
                status=status_value,
                prior=prior,
                next_due_at=next_due_at,
                now=now,
                stale_lock=stale_lock,
            )
            normalized_jobs.append(
                {
                    **prior,
                    "status": status_value,
                    "cadence_seconds": cadence_seconds,
                    "next_due_at": next_due_at,
                    "next_due_in_seconds": next_due_in_seconds,
                    "last_attempted_at": prior.get("last_attempted_at") or prior.get("last_started_at"),
                    "consecutive_failures": int(prior.get("consecutive_failures") or prior.get("failure_count") or 0),
                    "retry_delay_seconds": int(prior.get("retry_delay_seconds") or 0) or None,
                    "stale_lock": stale_lock,
                    "status_message": status_message,
                    "is_due": stale_lock or self._is_orchestration_job_due(job_name=job_name, prior={**prior, "next_due_at": next_due_at}, now=now),
                }
            )
        next_due_candidates = [
            _iso_to_datetime(str(item.get("next_due_at") or ""))
            for item in normalized_jobs
            if str(item.get("next_due_at") or "").strip()
        ]
        next_due_candidates = [item for item in next_due_candidates if item is not None]
        failed_jobs = [item for item in normalized_jobs if str(item.get("status") or "") in {"failed", "retry_scheduled"}]
        summary = {
            "total_jobs": len(normalized_jobs),
            "failed_jobs": len(failed_jobs),
            "due_jobs": sum(1 for item in normalized_jobs if bool(item.get("is_due"))),
            "retry_scheduled": sum(1 for item in normalized_jobs if str(item.get("status") or "") == "retry_scheduled"),
            "running_jobs": sum(1 for item in normalized_jobs if str(item.get("status") or "") == "running"),
            "healthy_jobs": sum(1 for item in normalized_jobs if str(item.get("status") or "") in {"completed", "idle"}),
            "attention_required": sum(1 for item in normalized_jobs if str(item.get("status") or "") not in {"completed", "idle"}),
            "next_due_at": min(next_due_candidates).isoformat() if next_due_candidates else None,
            "last_error": str(failed_jobs[0].get("last_error") or "") if failed_jobs else None,
        }
        return {
            "updated_at": orchestration.get("updated_at"),
            "last_reason": orchestration.get("last_reason"),
            "last_run_at": orchestration.get("last_run_at"),
            "jobs": normalized_jobs,
            "runs": list(orchestration.get("runs") or [])[-8:],
            "summary": summary,
        }

    def run_orchestration(
        self,
        *,
        store: Any,
        settings: Any | None,
        job_names: list[str] | None = None,
        reason: str = "manual_orchestration",
        force: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        current_time = now or _utcnow()
        requested_jobs = [str(item).strip() for item in list(job_names or []) if str(item).strip()]
        selected_jobs = requested_jobs or [
            "connector_sync",
            "reflection_pass",
            "knowledge_synthesis",
            "coaching_review",
            "trigger_evaluation",
            "stale_knowledge_check",
            "suppression_cleanup",
            "preference_consolidation",
            "daily_summary_candidates",
        ]
        if not self._orchestration_mutex.acquire(blocking=False):
            return {
                "run_id": None,
                "job_names": selected_jobs,
                "results": [],
                "status_value": "busy",
                "status": self.orchestration_status(),
            }
        state = self._load_state()
        orchestration = dict(state.get("orchestration") or {})
        job_state = dict(orchestration.get("jobs") or {})
        run_id = f"orch-{_fingerprint([reason, selected_jobs, current_time.isoformat()])[:10]}"
        run_summary = {
            "id": run_id,
            "created_at": current_time.isoformat(),
            "reason": reason,
            "job_names": selected_jobs,
            "status": "running",
        }
        results: list[dict[str, Any]] = []
        had_failures = False
        try:
            for job_name in selected_jobs:
                prior = dict(job_state.get(job_name) or {})
                cadence_seconds = self._orchestration_job_interval_seconds(job_name, settings=settings)
                lock_timeout_seconds = self._orchestration_lock_timeout_seconds(job_name, settings=settings)
                prior_started_at = _iso_to_datetime(str(prior.get("last_started_at") or prior.get("last_attempted_at") or ""))
                running_fresh = bool(
                    str(prior.get("status") or "") == "running"
                    and prior_started_at
                    and (current_time - prior_started_at) <= timedelta(seconds=lock_timeout_seconds)
                )
                if running_fresh and not force:
                    next_due_at = str(prior.get("next_due_at") or "") or (
                        current_time + timedelta(seconds=max(60, cadence_seconds // 2))
                    ).isoformat()
                    results.append({"job": job_name, "status": "skipped", "reason": "already_running", "next_due_at": next_due_at})
                    continue
                if not force and not self._is_orchestration_job_due(job_name=job_name, prior=prior, now=current_time, settings=settings):
                    next_due_at = self._orchestration_next_due_at(job_name=job_name, prior=prior, settings=settings)
                    job_state[job_name] = {
                        **prior,
                        "job": job_name,
                        "cadence_seconds": cadence_seconds,
                        "next_due_at": next_due_at,
                    }
                    results.append({"job": job_name, "status": "skipped", "reason": "interval_not_due", "next_due_at": next_due_at})
                    continue
                if str(prior.get("status") or "") == "running" and prior_started_at and not running_fresh:
                    self._append_log(
                        "orchestration_job_recovered",
                        f"{job_name} işi stale lock durumundan kurtarıldı",
                        {"reason": reason, "last_started_at": prior.get("last_started_at")},
                    )
                job_started_at = current_time.isoformat()
                job_state[job_name] = {
                    **prior,
                    "job": job_name,
                    "status": "running",
                    "last_started_at": job_started_at,
                    "last_attempted_at": job_started_at,
                    "cadence_seconds": cadence_seconds,
                }
                orchestration["jobs"] = job_state
                orchestration["updated_at"] = _iso_now()
                state["orchestration"] = orchestration
                state["updated_at"] = _iso_now()
                self._save_state(state)
                started_monotonic = datetime.now(timezone.utc)
                try:
                    if job_name == "connector_sync":
                        payload = self.run_connector_sync(store=store, reason=f"{reason}:{job_name}", trigger="scheduler")
                        summary = {
                            "synced_record_count": ((payload.get("result") or {}).get("synced_record_count") or 0),
                        }
                    elif job_name in {"reflection_pass", "stale_knowledge_check"}:
                        compile_result = self.compile_wiki_brain(reason=f"{reason}:{job_name}", previews=False)
                        payload = self.run_reflection()
                        summary = {
                            **dict(payload.get("summary") or {}),
                            "compiled_concepts": compile_result.get("concept_count"),
                        }
                    elif job_name == "knowledge_synthesis":
                        payload = self.run_knowledge_synthesis(reason=f"{reason}:{job_name}")
                        summary = payload.get("summary") or {}
                    elif job_name == "coaching_review":
                        payload = self.refresh_coaching_plan(reason=f"{reason}:{job_name}", persist=True)
                        summary = payload.get("summary") or {}
                    elif job_name == "trigger_evaluation":
                        payload = self.evaluate_triggers(
                            store=store,
                            settings=settings,
                            now=current_time,
                            persist=True,
                            limit=4,
                            include_suppressed=False,
                        )
                        summary = {"generated_count": len(payload.get("items") or [])}
                    elif job_name == "suppression_cleanup":
                        payload = self._cleanup_trigger_history(now=current_time)
                        summary = payload
                    elif job_name == "preference_consolidation":
                        payload = self.consolidate_preference_learning(store=store, reason=f"{reason}:{job_name}")
                        summary = {
                            "updated_pages": payload.get("updated_pages") or [],
                            "record_count": payload.get("record_count", 0),
                        }
                    elif job_name == "daily_summary_candidates":
                        payload = self.recommend(
                            store=store,
                            settings=settings,
                            current_context="daily summary orchestration",
                            location_context=str((self.get_location_context(store=store).get("current_place") or {}).get("label") or ""),
                            limit=2,
                            persist=False,
                        )
                        file_back = None
                        if payload.get("items"):
                            first_item = (payload.get("items") or [])[0]
                            file_back = self.maybe_file_back_response(
                                kind="daily_planning_output",
                                title=str(first_item.get("suggestion") or "Daily summary candidate"),
                                content="\n".join(
                                    [
                                        str(first_item.get("suggestion") or ""),
                                        str(first_item.get("why_this") or ""),
                                        *[str(item).strip() for item in list(first_item.get("next_actions") or []) if str(item).strip()],
                                    ]
                                ).strip(),
                                source_refs=list(first_item.get("source_basis") or []),
                                metadata={
                                    "page_key": "projects",
                                    "record_type": "goal",
                                    "scope": "personal",
                                },
                                scope="personal",
                                sensitivity="medium",
                            )
                        summary = {"candidate_count": len(payload.get("items") or [])}
                        if file_back:
                            summary["file_back_page"] = file_back.get("page_key")
                    else:
                        payload = {"warning": "unsupported_job"}
                        summary = {"warning": "unsupported_job"}
                    finished_at = _utcnow()
                    duration_ms = int(max(0.0, (finished_at - started_monotonic).total_seconds()) * 1000)
                    job_state[job_name] = {
                        "job": job_name,
                        "last_started_at": job_started_at,
                        "last_attempted_at": job_started_at,
                        "last_completed_at": _iso_now(),
                        "status": "completed",
                        "last_error": None,
                        "last_result_summary": summary,
                        "failure_count": 0,
                        "consecutive_failures": 0,
                        "retry_delay_seconds": 0,
                        "cadence_seconds": cadence_seconds,
                        "next_due_at": (current_time + timedelta(seconds=cadence_seconds)).isoformat(),
                        "last_duration_ms": duration_ms,
                    }
                    results.append({"job": job_name, "status": "completed", "summary": summary, "payload": payload})
                except Exception as exc:  # noqa: BLE001
                    had_failures = True
                    failure_count = int(prior.get("consecutive_failures") or prior.get("failure_count") or 0) + 1
                    retry_seconds = self._orchestration_retry_seconds(
                        cadence_seconds=cadence_seconds,
                        failure_count=failure_count,
                    )
                    next_retry_at = (current_time + timedelta(seconds=retry_seconds)).isoformat()
                    job_state[job_name] = {
                        "job": job_name,
                        "last_started_at": job_started_at,
                        "last_attempted_at": job_started_at,
                        "last_completed_at": _iso_now(),
                        "status": "retry_scheduled",
                        "last_error": str(exc),
                        "last_result_summary": {},
                        "failure_count": failure_count,
                        "consecutive_failures": failure_count,
                        "retry_delay_seconds": retry_seconds,
                        "cadence_seconds": cadence_seconds,
                        "next_due_at": next_retry_at,
                    }
                    results.append(
                        {
                            "job": job_name,
                            "status": "retry_scheduled",
                            "error": str(exc),
                            "retry_delay_seconds": retry_seconds,
                            "next_due_at": next_retry_at,
                        }
                    )
                    self._append_log(
                        "orchestration_job_failed",
                        f"{job_name} işi başarısız oldu",
                        {"error": str(exc), "reason": reason, "retry_delay_seconds": retry_seconds, "next_due_at": next_retry_at},
                    )
            orchestration["jobs"] = job_state
            orchestration["updated_at"] = _iso_now()
            orchestration["last_reason"] = reason
            orchestration["last_run_at"] = _iso_now()
            autonomy_snapshot = self.autonomy_status(store=store, settings=settings, now=current_time, persist=False)
            orchestration["runs"] = [
                *(list(orchestration.get("runs") or [])[-19:]),
                {
                    **run_summary,
                    "status": "completed_with_errors" if had_failures else "completed",
                    "results": results,
                    "autonomy_status": {
                        "status": autonomy_snapshot.get("status"),
                        "open_loop_count": autonomy_snapshot.get("open_loop_count"),
                    },
                },
            ]
            state["orchestration"] = orchestration
            state["autonomy_status"] = autonomy_snapshot
            state["updated_at"] = _iso_now()
            self._save_state(state)
            self._log_runtime_event(
                "personal_kb_orchestration_completed",
                level="warning" if had_failures else "info",
                reason=reason,
                job_count=len(selected_jobs),
                completed_job_count=sum(1 for item in results if str(item.get("status") or "") == "completed"),
                retry_scheduled_count=sum(1 for item in results if str(item.get("status") or "") == "retry_scheduled"),
                skipped_job_count=sum(1 for item in results if str(item.get("status") or "") == "skipped"),
            )
            return {
                "run_id": run_id,
                "job_names": selected_jobs,
                "results": results,
                "status_value": "completed_with_errors" if had_failures else "completed",
                "status": self.orchestration_status(),
                "autonomy_status": autonomy_snapshot,
            }
        finally:
            self._orchestration_mutex.release()

    def _search_compiled_concepts(
        self,
        query: str,
        *,
        wiki_brain: dict[str, Any],
        scopes: list[str] | None,
        limit: int,
        record_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        requested_record_types = {str(item).strip() for item in list(record_types or []) if str(item).strip()}
        if requested_record_types and not requested_record_types.intersection({"knowledge_article", "insight"}):
            return []
        query_tokens = set(_tokenize(query))
        query_slug = _slugify(query)
        requested_scopes = {str(item).strip() for item in list(scopes or []) if str(item).strip()}
        hits: list[dict[str, Any]] = []
        for concept in list(wiki_brain.get("concepts") or []):
            article_sections = dict(concept.get("article_sections") or {})
            searchable_parts = [
                str(concept.get("title") or ""),
                str(concept.get("summary") or ""),
                str(concept.get("kind") or ""),
                str(concept.get("key") or ""),
                str(article_sections.get("detailed_explanation") or ""),
                " ".join(str(item) for item in list(article_sections.get("patterns") or [])[:4]),
                " ".join(str(item) for item in list(article_sections.get("inferred_insights") or [])[:4]),
                " ".join(str(item.get("title") or "") for item in list(concept.get("record_refs") or [])[:6]),
            ]
            searchable_text = " ".join(searchable_parts).lower()
            searchable_slug = _slugify(searchable_text)
            reasons: list[str] = []
            score = 0.0
            title_slug = _slugify(str(concept.get("title") or concept.get("key") or ""))
            if query_slug and query_slug in title_slug:
                score += 1.4
                reasons.append("concept_title_match")
            overlap = [token for token in query_tokens if token in searchable_text or token in searchable_slug]
            if overlap:
                score += 0.24 * len(overlap)
                reasons.append("concept_token_overlap")
            kind = str(concept.get("kind") or "")
            if kind in {"field", "topic", "record_type"} and overlap:
                score += 0.18
                reasons.append("concept_kind_match")
            scope_summary = dict(concept.get("scope_summary") or {})
            if requested_scopes and scope_summary and requested_scopes.intersection(scope_summary.keys()):
                score += 0.22
                reasons.append("scope_match")
            if float(concept.get("confidence") or 0.0) >= 0.75:
                score += 0.06
                reasons.append("high_confidence")
            if float(concept.get("priority_score") or 0.0) >= 0.88:
                score += 0.12
                reasons.append("priority_weight")
            if int(concept.get("backlink_count") or 0) >= 3:
                score += 0.08
                reasons.append("knowledge_density")
            if article_sections.get("detailed_explanation") and overlap:
                score += 0.1
                reasons.append("semantic_article_match")
            if not overlap and query_slug not in title_slug:
                continue
            hits.append(
                {
                    "page_key": "concepts",
                    "record_id": concept.get("key"),
                    "title": concept.get("title"),
                    "summary": concept.get("summary"),
                    "score": round(score, 4),
                    "record_type": "knowledge_article" if kind != "topic" else "insight",
                    "scope": max(scope_summary, key=scope_summary.get) if scope_summary else "global",
                    "sensitivity": "medium",
                    "exportability": "redaction_required",
                    "model_routing_hint": "prefer_local",
                    "source_refs": list(concept.get("source_refs") or []),
                    "metadata": {
                        "kind": kind,
                        "path": concept.get("path"),
                        "scope_summary": scope_summary,
                        "record_type_counts": concept.get("record_type_counts") or {},
                        "priority_score": concept.get("priority_score"),
                        "authoring": concept.get("authoring") or {},
                        "article_sections": {
                            "summary": str(article_sections.get("summary") or ""),
                            "patterns": list(article_sections.get("patterns") or [])[:3],
                            "strategy_notes": list(article_sections.get("strategy_notes") or [])[:2],
                        },
                    },
                    "updated_at": concept.get("updated_at"),
                    "selection_reasons": list(dict.fromkeys(reasons))[:6],
                    "path": concept.get("path"),
                }
            )
        hits.sort(key=lambda item: (-float(item.get("score") or 0.0), str(item.get("title") or "")))
        return hits[: max(1, min(limit, 8))]

    def search(
        self,
        query: str,
        *,
        scopes: list[str] | None = None,
        page_keys: list[str] | None = None,
        limit: int = 8,
        include_decisions: bool = True,
        include_reflections: bool = True,
        metadata_filters: dict[str, Any] | None = None,
        record_types: list[str] | None = None,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        wiki_brain = self._build_wiki_brain(state)
        hits = self.retrieval_backend.search(
            state=state,
            request=RetrievalQuery(
                query=query,
                scopes=list(scopes or []),
                page_keys=list(page_keys or []),
                limit=limit,
                include_decisions=include_decisions,
                include_reflections=include_reflections,
                metadata_filters=dict(metadata_filters or {}),
                record_types=list(record_types or []),
            ),
            envelope_resolver=self._normalized_record_envelope,
            scope_matcher=self._scope_matches,
            epistemic_resolver=self._epistemic_resolution_for_record,
        )
        concept_hits = self._search_compiled_concepts(
            query,
            wiki_brain=wiki_brain,
            scopes=list(scopes or []),
            limit=min(limit, 6),
            record_types=list(record_types or []),
        )
        return {
            "query": query,
            "backend": self.search_backend,
            "ranking_profile": {
                "backend": self.search_backend,
                "profile": str(getattr(self.retrieval_backend, "ranking_profile", self.search_backend)),
                "vector_hook_ready": bool(getattr(self.retrieval_backend, "vector_hook_ready", False)),
                "reranker_hook_ready": bool(getattr(self.retrieval_backend, "reranker_hook_ready", False)),
                "pipeline": asdict(self.retrieval_pipeline),
            },
            "items": hits,
            "scopes": scopes or [],
            "page_keys": page_keys or [],
            "metadata_filters": metadata_filters or {},
            "record_types": record_types or [],
            "knowledge_articles": concept_hits,
            "diagnostics": {
                "result_count": len(hits),
                "knowledge_article_count": len(concept_hits),
                "record_type_mix": dict(Counter(str(item.get("record_type") or "source") for item in hits)),
                "page_mix": dict(Counter(str(item.get("page_key") or "") for item in hits)),
                "epistemic_status_mix": dict(Counter(str((item.get("metadata") or {}).get("epistemic_status") or "unknown") for item in hits)),
                "epistemic_support_mix": dict(Counter(str((item.get("metadata") or {}).get("epistemic_support_strength") or "unknown") for item in hits)),
            },
        }

    def resolve_relevant_context(
        self,
        query: str,
        *,
        scopes: list[str] | None = None,
        page_keys: list[str] | None = None,
        limit: int = 6,
        include_decisions: bool = True,
        include_reflections: bool = True,
        metadata_filters: dict[str, Any] | None = None,
        record_types: list[str] | None = None,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        search_result = self.search(
            query,
            scopes=scopes,
            page_keys=page_keys,
            limit=limit,
            include_decisions=include_decisions,
            include_reflections=include_reflections,
            metadata_filters=metadata_filters,
            record_types=record_types,
        )
        hits = list(search_result.get("items") or [])
        concept_hits = list(search_result.get("knowledge_articles") or [])
        supporting_pages = sorted({str(item.get("page_key") or "") for item in hits if str(item.get("page_key") or "")})
        decision_hits = [item for item in hits if str(item.get("record_type") or "") == "decision"]
        reflection_hits = [item for item in hits if str(item.get("record_type") or "") == "reflection"]
        recommendation_feedback = self._recent_feedback_for_query(query, scopes=scopes)
        record_type_counts = Counter(str(item.get("record_type") or "source") for item in hits)
        supporting_relations: list[dict[str, Any]] = []
        resolved_claims: list[dict[str, Any]] = []
        seen_claims: set[str] = set()
        for item in hits[:6]:
            metadata = dict(item.get("metadata") or {})
            for relation in list(metadata.get("relations") or [])[:3]:
                if not isinstance(relation, dict):
                    continue
                supporting_relations.append(
                    {
                        "page_key": item.get("page_key"),
                        "record_id": item.get("record_id"),
                        "title": item.get("title"),
                        "relation_type": relation.get("relation_type"),
                        "target": relation.get("target"),
                    }
                )
            claim_entry = self._claim_context_entry_from_hit(item)
            if not claim_entry:
                continue
            marker = str(claim_entry.get("claim_id") or f"{claim_entry.get('subject_key')}::{claim_entry.get('predicate')}::{claim_entry.get('value_text')}")
            if marker in seen_claims:
                continue
            seen_claims.add(marker)
            resolved_claims.append(claim_entry)
        claim_summary_lines = [str(item.get("summary_line") or "").strip() for item in resolved_claims[:3] if str(item.get("summary_line") or "").strip()]
        summary_lines = list(claim_summary_lines)
        for item in hits[:4]:
            line = f"- [{item.get('page_key')}] {item.get('title')}: {item.get('summary')}"
            if line not in summary_lines:
                summary_lines.append(line)
        for concept in concept_hits[:2]:
            line = f"- [concept] {concept.get('title')}: {concept.get('summary')}"
            if line not in summary_lines:
                summary_lines.append(line)
        resolved = ResolvedKnowledgeContext(
            query=query,
            summary_lines=summary_lines,
            claim_summary_lines=claim_summary_lines,
            supporting_pages=[
                {
                    "page_key": page_key,
                    "path": str(self.wiki_dir / f"{page_key}.md"),
                }
                for page_key in supporting_pages
            ],
            supporting_records=hits[:6],
            supporting_concepts=concept_hits[:6],
            knowledge_articles=concept_hits[:6],
            decision_records=decision_hits[:3],
            reflections=reflection_hits[:2],
            recent_related_feedback=recommendation_feedback,
            scopes=sorted({str(item.get("scope") or "") for item in hits if str(item.get("scope") or "")}),
            record_type_counts=dict(record_type_counts),
            supporting_relations=supporting_relations[:8],
            resolved_claims=resolved_claims[:6],
        )
        selection_reasons = sorted(
            {
                str(reason)
                for item in [*hits, *concept_hits]
                for reason in list(item.get("selection_reasons") or [])
                if str(reason).strip()
            }
        )
        if claim_summary_lines and "claim_resolved_context" not in selection_reasons:
            selection_reasons.append("claim_resolved_context")
        verification_gate = {
            "mode": "verified" if len(claim_summary_lines) >= 2 else "cautious" if len(claim_summary_lines) == 1 else "strict",
            "reason": "Birden fazla destekli current claim bulundu."
            if len(claim_summary_lines) >= 2
            else "Sınırlı sayıda destekli current claim bulundu."
            if len(claim_summary_lines) == 1
            else "Yanıt daha çok narrative/supporting record seviyesinde; kesin ifade temkinli kullanılmalı.",
        }
        if any(bool((item.get("metadata") or {}).get("epistemic_support_contaminated")) for item in hits):
            verification_gate = {
                "mode": "strict",
                "reason": "Kirli destek zinciri görülen kayıtlar bulundu; kesin ifade yerine temkinli dil kullanılmalı.",
            }
        return {
            "query": resolved.query,
            "summary_lines": resolved.summary_lines,
            "claim_summary_lines": resolved.claim_summary_lines,
            "supporting_pages": resolved.supporting_pages,
            "supporting_records": resolved.supporting_records,
            "supporting_concepts": resolved.supporting_concepts,
            "knowledge_articles": resolved.knowledge_articles,
            "decision_records": resolved.decision_records,
            "reflections": resolved.reflections,
            "recent_related_feedback": resolved.recent_related_feedback,
            "scopes": resolved.scopes,
            "record_type_counts": resolved.record_type_counts,
            "supporting_relations": resolved.supporting_relations,
            "resolved_claims": resolved.resolved_claims,
            "backend": self.search_backend,
            "context_selection_reasons": selection_reasons,
            "verification_gate": verification_gate,
        }

    def maybe_file_back_response(
        self,
        *,
        kind: str,
        title: str,
        content: str,
        source_refs: list[dict[str, Any] | str] | None = None,
        metadata: dict[str, Any] | None = None,
        scope: str | None = None,
        sensitivity: str | None = None,
    ) -> dict[str, Any] | None:
        self.ensure_scaffold()
        decision = self._should_file_back(kind=kind, content=content, metadata=metadata)
        if not decision.get("should_file_back"):
            return None
        file_metadata = dict(metadata or {})
        file_metadata.setdefault("page_key", decision.get("page_key"))
        file_metadata.setdefault("record_type", decision.get("record_type"))
        file_metadata.setdefault("scope", scope or decision.get("scope"))
        file_metadata.setdefault("sensitivity", sensitivity or decision.get("sensitivity"))
        file_metadata.setdefault("exportability", EXPORTABILITY_BY_SENSITIVITY.get(str(file_metadata.get("sensitivity") or "medium"), "redaction_required"))
        file_metadata.setdefault("model_routing_hint", MODEL_ROUTING_BY_SENSITIVITY.get(str(file_metadata.get("sensitivity") or "medium"), "redaction_required"))
        file_metadata.setdefault("file_back_kind", kind)
        file_metadata.setdefault("derived_persistence_class", "derived_artifact")
        file_metadata.setdefault("promotion_state", "pending_validation")
        file_metadata.setdefault("support_chain_gate", "independent_support_required")
        file_metadata.setdefault("source_refs", list(source_refs or []))
        ingest_result = self.ingest(
            source_type="assistant_file_back",
            content=content,
            title=title,
            metadata=file_metadata,
            occurred_at=_iso_now(),
            source_ref=f"assistant-file-back:{kind}:{_fingerprint([title, content, file_metadata.get('page_key')])[:10]}",
            tags=["assistant_file_back", kind, str(file_metadata.get("page_key") or "projects")],
        )
        if self.epistemic is not None:
            try:
                self.epistemic.record_assistant_output(
                    kind=kind,
                    title=title,
                    content=content,
                    scope=str(file_metadata.get("scope") or "global"),
                    sensitivity=str(file_metadata.get("sensitivity") or "medium"),
                    metadata=file_metadata,
                    source_refs=list(source_refs or []),
                )
            except Exception:
                pass
        return {
            "should_file_back": True,
            "page_key": file_metadata.get("page_key"),
            "record_type": file_metadata.get("record_type"),
            "scope": file_metadata.get("scope"),
            "derived_persistence_class": file_metadata.get("derived_persistence_class"),
            "promotion_state": file_metadata.get("promotion_state"),
            "ingest": ingest_result,
        }

    def consolidate_preference_learning(
        self,
        *,
        store: Any,
        reason: str = "preference_consolidation",
        render: bool = True,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        profile = store.get_user_profile(self.office_id) or {}
        history = list(state.get("recommendation_history") or [])
        updated_pages: list[str] = []
        records: list[tuple[str, dict[str, Any]]] = []
        now = _iso_now()

        reminder_rejections = [
            item for item in history
            if str(item.get("kind") or "") in {"smart_reminder", "daily_plan"} and str(item.get("outcome") or "") == "rejected"
        ]
        reminder_acceptances = [
            item for item in history
            if str(item.get("kind") or "") in {"smart_reminder", "daily_plan"} and str(item.get("outcome") or "") == "accepted"
        ]
        planning_acceptances = [
            item for item in history
            if str(item.get("kind") or "") in {"daily_plan", "calendar_nudge"} and str(item.get("outcome") or "") == "accepted"
        ]

        if profile.get("communication_style"):
            records.append(
                (
                    "preferences",
                    self._memory_preference_record(
                        page_key="preferences",
                        record_key="communication_style:global",
                        title="İletişim tarzı",
                        summary=str(profile.get("communication_style") or "").strip(),
                        scope="personal",
                        note="Profil senkronundan türetildi.",
                        source_refs=["profile_snapshot"],
                        metadata={
                            "field": "communication_style",
                            "record_type": "conversation_style",
                            "preference_type": "communication_style_learning",
                            "source_basis": ["profile_snapshot"],
                            "confidence": 0.98,
                            "recency": {"updated_at": profile.get("updated_at") or now},
                        },
                        signals=["preference_consolidation"],
                    ),
                )
            )

        if profile.get("assistant_notes"):
            records.append(
                (
                    "projects",
                    self._memory_preference_record(
                        page_key="projects",
                        record_key="goal:assistant_notes",
                        title="Operasyonel kullanıcı hedefi",
                        summary=str(profile.get("assistant_notes") or "").strip(),
                        scope="personal",
                        note="Assistant notes üzerinden operational goal/constraint kaydı üretildi.",
                        source_refs=["profile_snapshot"],
                        metadata={
                            "field": "assistant_notes",
                            "record_type": "goal",
                            "source_basis": ["profile_snapshot"],
                            "confidence": 0.8,
                            "recency": {"updated_at": profile.get("updated_at") or now},
                            "relations": [{"relation_type": "supports", "target": "daily_planning"}],
                        },
                        signals=["preference_consolidation"],
                    ),
                )
            )

        if profile.get("travel_preferences"):
            records.append(
                (
                    "preferences",
                    self._memory_preference_record(
                        page_key="preferences",
                        record_key="travel_style:global",
                        title="Seyahat tarzı",
                        summary=str(profile.get("travel_preferences") or "").strip(),
                        scope="personal",
                        note="Profil seyahat tercihlerinden türetildi.",
                        source_refs=["profile_snapshot"],
                        metadata={
                            "field": "travel_preferences",
                            "record_type": "preference",
                            "preference_type": "travel_style",
                            "source_basis": ["profile_snapshot"],
                            "confidence": 0.94,
                            "recency": {"updated_at": profile.get("updated_at") or now},
                        },
                        signals=["preference_consolidation"],
                    ),
                )
            )

        if reminder_rejections or reminder_acceptances:
            tolerance = "Hatırlatmalar seyrek ve yumuşak sunulmalı." if len(reminder_rejections) > len(reminder_acceptances) else "Hatırlatmalar görev yoğunluğu olduğunda görünür kalabilir."
            records.append(
                (
                    "preferences",
                    self._memory_preference_record(
                        page_key="preferences",
                        record_key="reminder_tolerance:global",
                        title="Hatırlatma toleransı",
                        summary=tolerance,
                        scope="personal",
                        note="Recommendation feedback geçmişinden türetildi.",
                        source_refs=[f"recommendation:{item.get('id')}" for item in (reminder_rejections + reminder_acceptances)[:4]],
                        metadata={
                            "field": "reminder_tolerance",
                            "record_type": "constraint" if len(reminder_rejections) > len(reminder_acceptances) else "preference",
                            "preference_type": "reminder_tolerance",
                            "source_basis": [f"recommendation:{item.get('id')}" for item in (reminder_rejections + reminder_acceptances)[:6]],
                            "confidence": 0.72 if len(reminder_rejections) != len(reminder_acceptances) else 0.6,
                            "rejection_count": len(reminder_rejections),
                            "acceptance_count": len(reminder_acceptances),
                        },
                        signals=["preference_consolidation"],
                    ),
                )
            )

        if planning_acceptances:
            records.append(
                (
                    "preferences",
                    self._memory_preference_record(
                        page_key="preferences",
                        record_key="planning_style:global",
                        title="Planlama tarzı",
                        summary="Yoğun günlerde hafifletilmiş ve önceliklendirilmiş plan önerileri yararlı bulunuyor.",
                        scope="personal",
                        note="Daily plan ve calendar nudge kabul geçmişinden türetildi.",
                        source_refs=[f"recommendation:{item.get('id')}" for item in planning_acceptances[:4]],
                        metadata={
                            "field": "planning_style",
                            "record_type": "preference",
                            "preference_type": "planning_style",
                            "source_basis": [f"recommendation:{item.get('id')}" for item in planning_acceptances[:6]],
                            "confidence": 0.78,
                            "acceptance_count": len(planning_acceptances),
                            "relations": [{"relation_type": "supports", "target": "daily_planning"}],
                        },
                        signals=["preference_consolidation"],
                    ),
                )
            )

        trigger_history = list(state.get("trigger_history") or [])
        evening_count = sum(
            1
            for item in trigger_history
            if str(item.get("trigger_type") or "") in {"daily_planning", "end_of_day_reflection"}
            and "T" in str(item.get("emitted_at") or "")
            and 18 <= int(str(item.get("emitted_at")).split("T", 1)[1][:2] or 0) <= 23
        )
        if evening_count >= 2:
            records.append(
                (
                    "routines",
                    self._memory_preference_record(
                        page_key="routines",
                        record_key="energy_rhythm:evening",
                        title="Akşam kapanış ritmi",
                        summary="Günün sonuna doğru kapanış, reflection ve yük hafifletme önerileri daha ilgili olabilir.",
                        scope="personal",
                        note="Trigger history örüntüsünden türetildi.",
                        source_refs=[f"trigger:{item.get('id')}" for item in trigger_history[-4:]],
                        metadata={
                            "field": "energy_rhythm",
                            "record_type": "routine",
                            "source_basis": [f"trigger:{item.get('id')}" for item in trigger_history[-6:]],
                            "confidence": 0.66,
                        },
                        signals=["preference_consolidation"],
                    ),
                )
            )

        records.extend(self._consolidate_consumer_signal_learning(store=store, now=now))
        records.extend(self._consolidate_location_pattern_learning(store=store, now=now))

        unique_records: list[tuple[str, dict[str, Any]]] = []
        seen_logical_keys: set[tuple[str, str]] = set()
        for page_key, record in records:
            logical_key = str(record.get("key") or record.get("id") or "")
            marker = (page_key, logical_key)
            if marker in seen_logical_keys:
                continue
            seen_logical_keys.add(marker)
            unique_records.append((page_key, record))
        records = unique_records

        generated_learning_signals = sorted(
            {
                str(signal).strip()
                for _, record in records
                for signal in list(record.get("signals") or [])
                if str(signal).strip()
            }
        )
        learning_categories = sorted(
            {
                str(((record.get("metadata") or {}).get("learning_source_category"))).strip()
                for _, record in records
                if str(((record.get("metadata") or {}).get("learning_source_category")) or "").strip()
            }
        )

        for page_key, record in records:
            result = self._upsert_page_record(state, page_key, record)
            if result.get("updated"):
                updated_pages.append(page_key)
        if records:
            state["updated_at"] = _iso_now()
            self._save_state(state)
            if render:
                self._render_all(state)
            self._append_log(
                "preference_consolidation",
                "Feedback, profil ve davranış sinyallerinden typed preference kayıtları güncellendi",
                {
                    "reason": reason,
                    "record_count": len(records),
                    "updated_pages": sorted(set(updated_pages)),
                    "learning_signals": generated_learning_signals,
                    "learning_categories": learning_categories,
                },
            )
        return {
            "updated_pages": sorted(set(updated_pages)),
            "record_count": len(records),
            "learning_signals": generated_learning_signals,
            "learning_categories": learning_categories,
        }

    def _consolidate_consumer_signal_learning(self, *, store: Any, now: str) -> list[tuple[str, dict[str, Any]]]:
        aggregates: dict[tuple[str, str], dict[str, Any]] = {}
        for connector in self.connector_registry:
            connector_name = str(getattr(connector, "name", "") or "").strip()
            if connector_name not in {"browser_context", "consumer_signals"}:
                continue
            try:
                collected = connector.collect(store=store, office_id=self.office_id)
            except Exception as exc:  # noqa: BLE001
                self._append_log(
                    "consumer_learning_connector_skipped",
                    f"{connector_name} consumer learning sırasında atlandı",
                    {"error": str(exc)},
                )
                continue
            for item in list(collected or []):
                source_type = str(getattr(item, "source_type", "") or "").strip()
                if source_type not in {
                    "browser_context",
                    "consumer_signal",
                    "youtube_history",
                    "reading_list",
                    "shopping_signal",
                    "travel_signal",
                    "weather_context",
                    "place_interest",
                    "web_research_signal",
                }:
                    continue
                metadata = dict(getattr(item, "metadata", {}) or {})
                scope = str(getattr(item, "scope", metadata.get("scope") or "personal")).strip() or "personal"
                normalized_text = _semantic_normalize_text(
                    " ".join(
                        part
                        for part in [
                            str(getattr(item, "title", "") or ""),
                            str(getattr(item, "content", "") or ""),
                            str(metadata.get("query") or ""),
                            str(metadata.get("category") or ""),
                            str(metadata.get("event_type") or ""),
                            str(metadata.get("signal_topic") or ""),
                            str(metadata.get("url") or ""),
                            " ".join(str(tag) for tag in list(getattr(item, "tags", []) or [])),
                        ]
                        if str(part).strip()
                    )
                )
                if not normalized_text:
                    continue
                matched_topics = [
                    topic_key
                    for topic_key, config in CONSUMER_TOPIC_RULES.items()
                    if any(_semantic_normalize_text(alias) in normalized_text for alias in list(config.get("aliases") or []))
                ]
                if not matched_topics:
                    continue
                weight = self._consumer_signal_learning_weight(source_type=source_type, metadata=metadata)
                occurred_at = _iso_to_datetime(str(getattr(item, "occurred_at", "") or metadata.get("sync_timestamp") or ""))
                source_ref = str(getattr(item, "source_ref", "") or "").strip()
                title = _compact_text(str(getattr(item, "title", "") or ""), limit=140)
                for topic_key in matched_topics:
                    aggregate = aggregates.setdefault(
                        (topic_key, scope),
                        {
                            "score": 0.0,
                            "evidence_count": 0,
                            "source_refs": [],
                            "source_markers": set(),
                            "source_types": set(),
                            "connectors": set(),
                            "sample_titles": [],
                            "last_seen_at": None,
                        },
                    )
                    marker = f"{source_type}:{source_ref}:{topic_key}"
                    if marker in aggregate["source_markers"]:
                        continue
                    aggregate["source_markers"].add(marker)
                    aggregate["score"] += weight
                    aggregate["evidence_count"] += 1
                    if source_ref:
                        aggregate["source_refs"].append(source_ref)
                    if title and title not in aggregate["sample_titles"]:
                        aggregate["sample_titles"].append(title)
                    aggregate["source_types"].add(source_type)
                    aggregate["connectors"].add(connector_name)
                    if occurred_at is not None:
                        prior_seen_at = aggregate.get("last_seen_at")
                        if prior_seen_at is None or occurred_at > prior_seen_at:
                            aggregate["last_seen_at"] = occurred_at

        records: list[tuple[str, dict[str, Any]]] = []
        for (topic_key, scope), aggregate in aggregates.items():
            if int(aggregate.get("evidence_count") or 0) < 2 and float(aggregate.get("score") or 0.0) < 1.75:
                continue
            config = dict(CONSUMER_TOPIC_RULES.get(topic_key) or {})
            page_key = str(config.get("page_key") or "preferences")
            source_refs = list(dict.fromkeys(str(item) for item in list(aggregate.get("source_refs") or []) if str(item).strip()))
            source_types = sorted(str(item) for item in list(aggregate.get("source_types") or []) if str(item).strip())
            confidence = min(
                0.92,
                round(
                    0.56
                    + min(float(aggregate.get("score") or 0.0), 3.0) * 0.09
                    + min(int(aggregate.get("evidence_count") or 0), 4) * 0.04,
                    2,
                ),
            )
            last_seen_at = aggregate.get("last_seen_at")
            records.append(
                (
                    page_key,
                    self._memory_preference_record(
                        page_key=page_key,
                        record_key=f"consumer-interest:{topic_key}:{scope}",
                        title=str(config.get("title") or _humanize_identifier(topic_key)),
                        summary=str(config.get("summary") or _humanize_identifier(topic_key)),
                        scope=scope,
                        note=None,
                        source_refs=source_refs,
                        metadata={
                            "field": str(config.get("field") or f"consumer_interest:{topic_key}"),
                            "record_type": str(config.get("record_type") or "preference"),
                            "preference_type": "consumer_interest",
                            "topic": topic_key,
                            "topic_key": topic_key,
                            "source_basis": source_refs[:8],
                            "source_types": source_types,
                            "connector_names": sorted(str(item) for item in list(aggregate.get("connectors") or []) if str(item).strip()),
                            "evidence_count": int(aggregate.get("evidence_count") or 0),
                            "weighted_signal_score": round(float(aggregate.get("score") or 0.0), 2),
                            "confidence": confidence,
                            "learning_source_category": "consumer_signal",
                            "recency": {"updated_at": last_seen_at.isoformat() if last_seen_at is not None else now},
                            "sample_titles": list(aggregate.get("sample_titles") or [])[:4],
                            "relations": list(config.get("relations") or []),
                        },
                        signals=["consumer_learning"],
                    ),
                )
            )
        return records

    def _consolidate_location_pattern_learning(self, *, store: Any, now: str) -> list[tuple[str, dict[str, Any]]]:
        location_context = self.get_location_context(store=store)
        frequent_patterns = sorted(
            [
                item
                for item in list(location_context.get("frequent_patterns") or [])
                if isinstance(item, dict) and int(item.get("count") or 0) >= 2 and str(item.get("category") or "").strip()
            ],
            key=lambda item: (-int(item.get("count") or 0), str(item.get("time_bucket") or ""), str(item.get("category") or "")),
        )
        records: list[tuple[str, dict[str, Any]]] = []
        for item in frequent_patterns[:2]:
            bucket = str(item.get("time_bucket") or "current").strip() or "current"
            category = str(item.get("category") or "place").strip() or "place"
            count = int(item.get("count") or 0)
            category_label = PLACE_CATEGORY_LABELS.get(category, _humanize_identifier(category).lower())
            source_basis = [
                str(location_context.get("provider") or location_context.get("source") or "location_context"),
                f"location-pattern:{bucket}:{category}",
            ]
            confidence = min(0.86, round(0.58 + min(count, 5) * 0.06, 2))
            records.append(
                (
                    "routines",
                    self._memory_preference_record(
                        page_key="routines",
                        record_key=f"location-pattern:{bucket}:{category}",
                        title=f"{_humanize_identifier(bucket)} bağlamı",
                        summary=f"Kullanıcı {bucket} saat bandında sıkça {category_label} tipi yerlerde bulunuyor; öneriler ve check-in'ler bu bağlama göre uyarlanmalı.",
                        scope=str(location_context.get("scope") or "personal"),
                        note=None,
                        source_refs=source_basis,
                        metadata={
                            "field": "location_pattern_preference",
                            "record_type": "routine",
                            "preference_type": "location_pattern",
                            "topic": f"{bucket}:{category}",
                            "topic_key": f"location:{bucket}:{category}",
                            "time_bucket": bucket,
                            "category": category,
                            "source_basis": source_basis,
                            "evidence_count": count,
                            "confidence": confidence,
                            "learning_source_category": "location_pattern",
                            "recency": {"updated_at": str(location_context.get("updated_at") or now)},
                            "relations": [
                                {"relation_type": "relevant_to", "target": f"place_category:{category}"},
                                {"relation_type": "supports", "target": "location_context"},
                            ],
                        },
                        signals=["location_pattern_learning"],
                    ),
                )
            )
        return records

    @staticmethod
    def _consumer_signal_learning_weight(*, source_type: str, metadata: dict[str, Any]) -> float:
        base = float(CONSUMER_SOURCE_WEIGHTS.get(str(source_type or "").strip(), 0.8))
        importance = str(metadata.get("importance") or "").strip().lower()
        if importance == "high":
            base += 0.18
        elif importance == "low":
            base -= 0.08
        if bool(metadata.get("reply_needed")):
            base += 0.06
        return round(max(0.35, min(1.4, base)), 2)

    def connector_sync_status(self, *, store: Any | None = None) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        connector_sync = dict(state.get("connector_sync") or {})
        connector_fingerprints = dict(connector_sync.get("connectors") or {})
        checkpoints = dict(connector_sync.get("checkpoints") or {})
        jobs = list(connector_sync.get("jobs") or [])
        now = _utcnow()
        accounts_by_provider = {
            str(item.get("provider") or ""): item
            for item in (store.list_connected_accounts(self.office_id) if store else [])
            if str(item.get("provider") or "")
        }
        items = []
        for connector in self.connector_registry:
            checkpoint = dict(checkpoints.get(connector.name) or {})
            provider_statuses = []
            for provider in getattr(connector, "provider_hints", ()) or ():
                account = accounts_by_provider.get(str(provider))
                account_metadata = dict((account or {}).get("metadata") or {})
                provider_statuses.append(
                    {
                        "provider": provider,
                        "connected": bool(account),
                        "account_label": account.get("account_label") if account else None,
                        "last_sync_at": account.get("last_sync_at") if account else checkpoint.get("mirror_sync_at"),
                        "status": account.get("status") if account else "disconnected",
                        "health_status": account_metadata.get("health_status") or ("valid" if account else "disconnected"),
                        "sync_status": account_metadata.get("sync_status") or (account.get("status") if account else "missing"),
                        "sync_status_message": account_metadata.get("sync_status_message") or account_metadata.get("message"),
                        "last_error": account_metadata.get("last_error"),
                        "next_retry_at": account_metadata.get("next_retry_at"),
                        "provider_mode": account_metadata.get("provider_mode") or ("desktop_managed" if provider in {"whatsapp", "telegram"} else "platform"),
                    }
                )
            connector_health = str(checkpoint.get("health_status") or self._connector_health_status(provider_statuses)).strip() or "unknown"
            connector_sync_status = str(checkpoint.get("sync_status") or self._connector_sync_status_value(provider_statuses)).strip() or "idle"
            freshness = self._connector_freshness(
                checkpoint=checkpoint,
                sync_mode=str(getattr(connector, "sync_mode", "local_scan")),
                now=now,
            )
            items.append(
                {
                    "connector": connector.name,
                    "description": getattr(connector, "description", connector.name),
                    "sync_mode": getattr(connector, "sync_mode", "local_scan"),
                    "providers": provider_statuses,
                    "last_synced_at": checkpoint.get("last_synced_at"),
                    "cursor": checkpoint.get("cursor"),
                    "checkpoint": checkpoint.get("checkpoint"),
                    "record_count": checkpoint.get("record_count", 0),
                    "synced_record_count": checkpoint.get("synced_record_count", 0),
                    "dedupe_key_count": sum(1 for key in connector_fingerprints if str(key).startswith(f"{connector.name}:")),
                    "last_reason": checkpoint.get("reason") or connector_sync.get("last_reason"),
                    "last_trigger": checkpoint.get("trigger"),
                    "health_status": connector_health,
                    "sync_status": connector_sync_status,
                    "sync_status_message": checkpoint.get("sync_status_message"),
                    "last_error": checkpoint.get("last_error"),
                    "consecutive_failures": int(checkpoint.get("consecutive_failures") or 0),
                    "next_retry_at": checkpoint.get("next_retry_at"),
                    "last_attempted_at": checkpoint.get("last_attempted_at"),
                    "last_success_at": checkpoint.get("last_success_at"),
                    "last_duration_ms": checkpoint.get("last_duration_ms"),
                    "retry_delay_minutes": checkpoint.get("retry_delay_minutes"),
                    "provider_mode": checkpoint.get("provider_mode") or getattr(connector, "sync_mode", "local_scan"),
                    "stub": getattr(connector, "sync_mode", "") == "adapter_stub",
                    "freshness_status": freshness.get("status"),
                    "freshness_minutes": freshness.get("minutes"),
                    "stale_sync": freshness.get("stale"),
                }
            )
        summary = {
            "total_connectors": len(items),
            "healthy_connectors": sum(1 for item in items if str(item.get("health_status") or "") in {"valid", "connected"}),
            "attention_required": sum(
                1
                for item in items
                if str(item.get("health_status") or "") in {"invalid", "disconnected"}
                or str(item.get("sync_status") or "") in {"retry_scheduled", "failed"}
            ),
            "retry_scheduled": sum(1 for item in items if str(item.get("sync_status") or "") == "retry_scheduled"),
            "stubs": sum(1 for item in items if bool(item.get("stub"))),
            "connected_providers": sum(
                1
                for item in items
                for provider in list(item.get("providers") or [])
                if bool(provider.get("connected"))
            ),
            "stale_connectors": sum(1 for item in items if bool(item.get("stale_sync"))),
            "fresh_connectors": sum(1 for item in items if str(item.get("freshness_status") or "") == "fresh"),
        }
        return {
            "items": items,
            "jobs": jobs[-12:],
            "updated_at": connector_sync.get("updated_at"),
            "last_reason": connector_sync.get("last_reason"),
            "summary": summary,
        }

    @staticmethod
    def _connector_health_status(provider_statuses: list[dict[str, Any]]) -> str:
        health_values = {str(item.get("health_status") or "").strip() for item in provider_statuses if str(item.get("health_status") or "").strip()}
        if not provider_statuses:
            return "unknown"
        if "invalid" in health_values or "revoked" in health_values:
            return "invalid"
        if "pending" in health_values:
            return "pending"
        if "valid" in health_values:
            return "valid"
        if any(item.get("connected") for item in provider_statuses):
            return "connected"
        return "disconnected"

    @staticmethod
    def _connector_freshness(*, checkpoint: dict[str, Any], sync_mode: str, now: datetime) -> dict[str, Any]:
        last_sync_at = str(checkpoint.get("last_success_at") or checkpoint.get("last_synced_at") or "").strip()
        last_sync_dt = _iso_to_datetime(last_sync_at)
        if last_sync_dt is None:
            return {"status": "unknown", "minutes": None, "stale": False}
        age_minutes = max(0, int((now - last_sync_dt).total_seconds() // 60))
        threshold_minutes = 360 if sync_mode == "mirror_pull" else 1440 if sync_mode == "local_scan" else 720
        if age_minutes <= max(30, threshold_minutes // 3):
            status = "fresh"
        elif age_minutes <= threshold_minutes:
            status = "aging"
        else:
            status = "stale"
        return {"status": status, "minutes": age_minutes, "stale": status == "stale"}

    @staticmethod
    def _connector_sync_status_value(provider_statuses: list[dict[str, Any]]) -> str:
        sync_values = {str(item.get("sync_status") or "").strip() for item in provider_statuses if str(item.get("sync_status") or "").strip()}
        if "retry_scheduled" in sync_values:
            return "retry_scheduled"
        if "running" in sync_values:
            return "running"
        if "completed" in sync_values or "ok" in sync_values:
            return "completed"
        if "pending" in sync_values:
            return "pending"
        return "idle"

    def assistant_core_status(self, *, store: Any | None = None) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        runtime_profile = store.get_assistant_runtime_profile(self.office_id) if store is not None else {}
        coaching_goal_count = len((state.get("coaching") or {}).get("goals") or {})
        payload = build_assistant_core_status(runtime_profile, coaching_goal_count=coaching_goal_count)
        payload["updated_at"] = runtime_profile.get("updated_at") if isinstance(runtime_profile, dict) else None
        return payload

    def memory_overview(self) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        by_scope = Counter[str]()
        by_type = Counter[str]()
        by_shareability = Counter[str]()
        recent_corrections: list[dict[str, Any]] = []
        do_not_reinfer: list[dict[str, Any]] = []
        repeated_contradictions: list[dict[str, Any]] = []
        highlighted: list[dict[str, Any]] = []
        suppressed_topics: list[str] = []
        boosted_topics: list[str] = []
        learned_topics: list[dict[str, Any]] = []
        for page_key, page in (state.get("pages") or {}).items():
            for record in list((page or {}).get("records") or []):
                if not isinstance(record, dict):
                    continue
                envelope = self._normalized_record_envelope(page_key, record)
                metadata = dict(envelope.get("metadata") or {})
                signals = {str(item).strip() for item in list(record.get("signals") or []) if str(item).strip()}
                scope = str(envelope.get("scope") or "global")
                record_type = str(envelope.get("record_type") or "source")
                shareability = str(metadata.get("shareability") or _scope_shareability(scope, str(envelope.get("sensitivity") or "medium")))
                correction_history = list(metadata.get("correction_history") or [])
                if correction_history:
                    last_correction = correction_history[-1]
                    recent_corrections.append(
                        {
                            "record_id": record.get("id"),
                            "page_key": page_key,
                            "title": record.get("title"),
                            "scope": scope,
                            "action": last_correction.get("action") or "note",
                            "timestamp": last_correction.get("timestamp") or record.get("updated_at"),
                            "status": record.get("status") or "active",
                        }
                    )
                if metadata.get("do_not_infer_again_easily"):
                    do_not_reinfer.append(
                        {
                            "record_id": record.get("id"),
                            "page_key": page_key,
                            "title": record.get("title"),
                            "scope": scope,
                            "status": record.get("status") or "active",
                        }
                    )
                if str(record.get("status") or "active") != "active":
                    continue
                by_scope[scope] += 1
                by_type[record_type] += 1
                by_shareability[shareability] += 1
                if len(highlighted) < 12:
                    highlighted.append(
                        {
                            "id": record.get("id"),
                            "page_key": page_key,
                            "title": record.get("title"),
                            "summary": record.get("summary"),
                            "scope": scope,
                            "record_type": record_type,
                            "sensitivity": envelope.get("sensitivity"),
                            "shareability": shareability,
                            "updated_at": record.get("updated_at"),
                        }
                    )
                if (
                    str(metadata.get("learning_source_category") or "").strip()
                    or signals.intersection(LEARNING_SIGNAL_TYPES)
                ):
                    learned_topics.append(
                        {
                            "record_id": record.get("id"),
                            "page_key": page_key,
                            "title": record.get("title"),
                            "summary": record.get("summary"),
                            "scope": scope,
                            "record_type": record_type,
                            "updated_at": record.get("updated_at"),
                            "confidence": record.get("confidence"),
                            "topic_key": metadata.get("topic_key") or metadata.get("topic"),
                            "source_category": metadata.get("learning_source_category") or ",".join(sorted(signals.intersection(LEARNING_SIGNAL_TYPES))),
                            "evidence_count": int(metadata.get("evidence_count") or 0),
                            "source_types": list(metadata.get("source_types") or []),
                        }
                    )
                if int(metadata.get("repeated_contradiction_count") or 0) > 0:
                    repeated_contradictions.append(
                        {
                            "record_id": record.get("id"),
                            "page_key": page_key,
                            "title": record.get("title"),
                            "count": int(metadata.get("repeated_contradiction_count") or 0),
                            "scope": scope,
                        }
                    )
                preference_type = str(metadata.get("preference_type") or "").strip()
                topic = str(metadata.get("topic") or metadata.get("recommendation_kind") or "").strip()
                if preference_type == "recommendation_suppression" and topic:
                    suppressed_topics.append(topic)
                if preference_type == "proactivity_preference" and topic:
                    boosted_topics.append(topic)
        recent_corrections.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        repeated_contradictions.sort(key=lambda item: int(item.get("count") or 0), reverse=True)
        highlighted.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        learned_topics.sort(
            key=lambda item: (
                str(item.get("updated_at") or ""),
                float(item.get("confidence") or 0.0),
                int(item.get("evidence_count") or 0),
            ),
            reverse=True,
        )
        return {
            "counts": {
                "records": sum(by_scope.values()),
                "pages": len(state.get("pages") or {}),
                "decision_records": len(state.get("decision_records") or []),
                "recommendations": len(state.get("recommendation_history") or []),
            },
            "by_scope": dict(by_scope),
            "by_type": dict(by_type),
            "by_shareability": dict(by_shareability),
            "recent_corrections": recent_corrections[:8],
            "do_not_reinfer": do_not_reinfer[:8],
            "repeated_contradictions": repeated_contradictions[:8],
            "highlighted_records": highlighted[:10],
            "suppressed_topics": sorted(set(suppressed_topics)),
            "boosted_topics": sorted(set(boosted_topics)),
            "learned_topics": learned_topics[:8],
        }

    def _memory_explorer_transparency(self) -> dict[str, Any]:
        system_files = self._memory_explorer_system_files()
        return {
            "root_path": str(self.base_dir),
            "raw_dir": str(self.raw_dir),
            "wiki_dir": str(self.wiki_dir),
            "concepts_dir": str(self._concepts_dir()),
            "reports_dir": str(self._reports_dir()),
            "normalized_dir": str(self._normalized_dir()),
            "system_dir": str(self.system_dir),
            "system_files": [
                {"id": f"system:{path.name}", "path": str(path)}
                for path in system_files
            ],
        }

    def _memory_explorer_system_files(self) -> list[Path]:
        preferred = [self.system_dir / name for name in SYSTEM_FILE_ORDER]
        discovered = sorted(self.system_dir.glob("*.md")) if self.system_dir.exists() else []
        merged: list[Path] = []
        seen: set[str] = set()
        for path in [*preferred, *discovered]:
            key = str(path.name).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(path)
        return merged

    def _memory_explorer_report_files(self) -> list[tuple[str, str, Path, str]]:
        preferred = [
            ("report:wiki-brain-latest.md", "Wiki Brain Report", self._reports_dir() / "wiki-brain-latest.md", "Concept derleme ve article raporu."),
            ("report:knowledge-health-latest.md", "Knowledge Health Report", self._reports_dir() / "knowledge-health-latest.md", "Reflection, stale ve contradiction raporu."),
        ]
        seen = {item[2].name for item in preferred}
        extras: list[tuple[str, str, Path, str]] = []
        if self._reports_dir().exists():
            for path in sorted(self._reports_dir().glob("*.md")):
                if path.name in seen:
                    continue
                extras.append(
                    (
                        f"report:{path.name}",
                        _humanize_identifier(path.stem),
                        path,
                        f"{path.name} şeffaflık raporu.",
                    )
                )
        return [*preferred, *extras]

    def _load_memory_health_report(self) -> dict[str, Any]:
        report_path = self._reports_dir() / "knowledge-health-latest.json"
        if not report_path.exists():
            return {}
        try:
            payload = json.loads(self._read_text_lossy(report_path))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _safe_parse_memory_value(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text or text[:1] not in {"{", "["}:
            return value
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return value

    def _memory_active_record_entries(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for page_key, page in (state.get("pages") or {}).items():
            for record in list((page or {}).get("records") or []):
                if not isinstance(record, dict):
                    continue
                envelope = self._normalized_record_envelope(page_key, record)
                entries.append(
                    {
                        "page_key": page_key,
                        "record": record,
                        "envelope": envelope,
                    }
                )
        return entries

    def _memory_structural_lint(self, state: dict[str, Any], wiki_brain: dict[str, Any]) -> dict[str, Any]:
        orphan_pages: list[dict[str, Any]] = []
        unbound_pages: list[dict[str, Any]] = []
        cross_link_gaps: list[dict[str, Any]] = []
        concepts = [
            item
            for item in list((wiki_brain.get("concepts") or []))
            if isinstance(item, dict) and str(item.get("key") or "").strip()
        ]
        orphan_concepts = [
            {
                "concept_key": str(item.get("key") or ""),
                "title": str(item.get("title") or _humanize_identifier(str(item.get("key") or ""))),
                "backlink_count": int(item.get("backlink_count") or 0),
            }
            for item in concepts
            if int(item.get("backlink_count") or 0) <= 0
        ]

        for page_key, description in PAGE_SPECS.items():
            page = (state.get("pages") or {}).get(page_key) or {"records": []}
            active_records = [
                item
                for item in list(page.get("records") or [])
                if isinstance(item, dict) and str(item.get("status") or "active") == "active"
            ]
            if not active_records:
                orphan_pages.append(
                    {
                        "page_key": page_key,
                        "title": str(page.get("title") or page_key.title()),
                        "reason": description,
                    }
                )
                continue
            claim_bound_records = 0
            linked_pages = Counter[str]()
            backlink_count = 0
            for record in active_records:
                envelope = self._normalized_record_envelope(page_key, record)
                if self._claim_binding_for_record(page_key, record, envelope):
                    claim_bound_records += 1
                relations = list(((envelope.get("metadata") or {}).get("relations") or []))
                for relation in relations:
                    if not isinstance(relation, dict):
                        continue
                    target = str(relation.get("target") or "").strip()
                    if target in PAGE_SPECS and target != page_key:
                        linked_pages[target] += 1
                backlink_count += len(list(((wiki_brain.get("record_backlinks") or {}).get(f"{page_key}:{record.get('id')}") or [])))
            if claim_bound_records <= 0:
                unbound_pages.append(
                    {
                        "page_key": page_key,
                        "title": str(page.get("title") or page_key.title()),
                        "active_record_count": len(active_records),
                    }
                )
            if len(active_records) >= 2 and not linked_pages and backlink_count <= 0:
                cross_link_gaps.append(
                    {
                        "page_key": page_key,
                        "title": str(page.get("title") or page_key.title()),
                        "active_record_count": len(active_records),
                    }
                )
        return {
            "summary": {
                "orphan_pages": len(orphan_pages),
                "orphan_concepts": len(orphan_concepts),
                "unbound_pages": len(unbound_pages),
                "cross_link_gaps": len(cross_link_gaps),
            },
            "orphan_pages": orphan_pages[:12],
            "orphan_concepts": orphan_concepts[:12],
            "unbound_pages": unbound_pages[:12],
            "cross_link_gaps": cross_link_gaps[:12],
        }

    def memory_explorer_lint(self) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        if not self._wiki_brain_path().exists():
            self._render_all(state)
        wiki_brain = self._load_existing_wiki_brain()
        claim_report: dict[str, Any] = {
            "generated_at": _iso_now(),
            "summary": {
                "total_claims": 0,
                "contradictions": 0,
                "stale_claims": 0,
                "weak_claims": 0,
                "superseded_claims": 0,
                "contamination_risks": 0,
            },
            "contradictions": [],
            "stale_claims": [],
            "weak_claims": [],
            "superseded_claims": [],
            "contamination_risks": [],
        }
        if self.epistemic is not None and hasattr(self.epistemic, "store"):
            claims = self.epistemic.store.list_epistemic_claims(self.office_id, include_blocked=True, limit=2500)
            claim_report = build_epistemic_lint_report(epistemic=self.epistemic, claims=claims)
            claim_report["generated_at"] = _iso_now()
        structural = self._memory_structural_lint(state, wiki_brain)
        summary = dict(claim_report.get("summary") or {})
        summary.update(dict(structural.get("summary") or {}))
        return {
            **claim_report,
            "generated_at": _iso_now(),
            "summary": summary,
            "structural": structural,
        }

    def memory_explorer_pages(self) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        if not self._wiki_brain_path().exists():
            self._render_all(state)
        wiki_brain = self._load_existing_wiki_brain()
        concepts = {
            str(item.get("key") or ""): item
            for item in list((wiki_brain.get("concepts") or []))
            if isinstance(item, dict) and str(item.get("key") or "").strip()
        }
        record_backlinks = dict((wiki_brain.get("record_backlinks") or {}))
        items: list[dict[str, Any]] = []

        for page_key, description in PAGE_SPECS.items():
            page = (state.get("pages") or {}).get(page_key) or {"records": []}
            records = [item for item in list(page.get("records") or []) if isinstance(item, dict)]
            active_records = [item for item in records if str(item.get("status") or "active") == "active"]
            scope_summary = Counter[str]()
            record_type_counts = Counter[str]()
            sensitivity_summary = Counter[str]()
            shareability_summary = Counter[str]()
            linked_pages = Counter[str]()
            claim_status_counts = Counter[str]()
            confidence_values: list[float] = []
            last_updated = None
            backlink_count = 0
            for record in active_records:
                envelope = self._normalized_record_envelope(page_key, record)
                metadata = dict(envelope.get("metadata") or {})
                scope_summary[str(envelope.get("scope") or "global")] += 1
                record_type_counts[str(envelope.get("record_type") or "source")] += 1
                sensitivity_summary[str(envelope.get("sensitivity") or "medium")] += 1
                shareability_summary[str(metadata.get("shareability") or "shareable")] += 1
                confidence_values.append(float(record.get("confidence") or 0.0))
                current_dt = _iso_to_datetime(str(record.get("updated_at") or ""))
                if current_dt and (last_updated is None or current_dt > last_updated):
                    last_updated = current_dt
                epistemic = self._epistemic_resolution_for_record(page_key, record, envelope)
                if isinstance(epistemic, dict) and str(epistemic.get("status") or "").strip():
                    claim_status_counts[str(epistemic.get("status") or "unknown")] += 1
                for concept_ref in list(record_backlinks.get(f"{page_key}:{record.get('id')}") or []):
                    concept_key = str((concept_ref or {}).get("key") or "").strip()
                    if not concept_key:
                        continue
                    backlink_count += 1
                    concept_payload = concepts.get(concept_key) or {}
                    for linked_record in list(concept_payload.get("record_refs") or []):
                        other_page = str((linked_record or {}).get("page_key") or "").strip()
                        if other_page and other_page != page_key:
                            linked_pages[other_page] += 1
            dominant_scope = scope_summary.most_common(1)[0][0] if scope_summary else DEFAULT_PAGE_SCOPES.get(page_key, "global")
            average_confidence = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else None
            items.append(
                {
                    "id": f"page:{page_key}",
                    "kind": "wiki_page",
                    "page_key": page_key,
                    "title": str((page.get("title") or page_key.title())).strip() or page_key.title(),
                    "summary": description,
                    "description": description,
                    "path": str(self.wiki_dir / f"{page_key}.md"),
                    "record_count": len(records),
                    "active_record_count": len(active_records),
                    "scope": dominant_scope,
                    "scope_summary": dict(scope_summary),
                    "record_type_counts": dict(record_type_counts),
                    "sensitivity_summary": dict(sensitivity_summary),
                    "shareability_summary": dict(shareability_summary),
                    "claim_summary": {
                        "bound_records": int(sum(claim_status_counts.values())),
                        "status_counts": dict(claim_status_counts),
                    },
                    "confidence": average_confidence,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                    "backlink_count": backlink_count,
                    "linked_pages": [
                        {
                            "id": f"page:{linked_key}",
                            "title": str(((state.get("pages") or {}).get(linked_key) or {}).get("title") or linked_key.title()),
                            "shared_backlinks": count,
                        }
                        for linked_key, count in linked_pages.most_common(6)
                    ],
                    "editable": True,
                }
            )

        for concept in list(wiki_brain.get("concepts") or []):
            if not isinstance(concept, dict):
                continue
            concept_key = str(concept.get("key") or "").strip()
            if not concept_key:
                continue
            items.append(
                {
                    "id": f"concept:{concept_key}",
                    "kind": "concept",
                    "page_key": None,
                    "title": str(concept.get("title") or _humanize_identifier(concept_key)),
                    "summary": str(concept.get("summary") or ""),
                    "description": str(concept.get("summary") or ""),
                    "path": str(concept.get("path") or self._concepts_dir() / f"{_slugify(concept_key)}.md"),
                    "record_count": int(concept.get("backlink_count") or 0),
                    "active_record_count": int(concept.get("backlink_count") or 0),
                    "scope": max(dict(concept.get("scope_summary") or {"global": 1}), key=dict(concept.get("scope_summary") or {"global": 1}).get),
                    "scope_summary": dict(concept.get("scope_summary") or {}),
                    "record_type_counts": dict(concept.get("record_type_counts") or {}),
                    "confidence": concept.get("confidence"),
                    "last_updated": concept.get("updated_at"),
                    "backlink_count": int(concept.get("backlink_count") or 0),
                    "linked_pages": [
                        {
                            "id": f"page:{linked_key}",
                            "title": str(((state.get("pages") or {}).get(linked_key) or {}).get("title") or linked_key.title()),
                            "shared_backlinks": count,
                        }
                        for linked_key, count in Counter(
                            str(item.get("page_key") or "").strip()
                            for item in list(concept.get("record_refs") or [])
                            if str(item.get("page_key") or "").strip()
                        ).most_common(6)
                    ],
                    "quality_flags": list(concept.get("quality_flags") or []),
                    "editable": False,
                }
            )

        for path in self._memory_explorer_system_files():
            items.append(
                {
                    "id": f"system:{path.name}",
                    "kind": "system_file",
                    "page_key": None,
                    "title": path.name,
                    "summary": f"{path.name} sistem şeffaflık yüzeyi.",
                    "description": f"{path.name} sistem dosyası.",
                    "path": str(path),
                    "record_count": 0,
                    "active_record_count": 0,
                    "scope": "global",
                    "confidence": None,
                    "last_updated": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat() if path.exists() else None,
                    "backlink_count": 0,
                    "linked_pages": [],
                    "editable": False,
                }
            )
        for item_id, title, path, summary in self._memory_explorer_report_files():
            items.append(
                {
                    "id": item_id,
                    "kind": "report",
                    "page_key": None,
                    "title": title,
                    "summary": summary,
                    "description": summary,
                    "path": str(path),
                    "record_count": 0,
                    "active_record_count": 0,
                    "scope": "global",
                    "confidence": None,
                    "last_updated": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat() if path.exists() else None,
                    "backlink_count": 0,
                    "linked_pages": [],
                    "editable": False,
                }
            )

        page_count = sum(1 for item in items if str(item.get("kind") or "") == "wiki_page")
        concept_count = sum(1 for item in items if str(item.get("kind") or "") == "concept")
        structural_lint = self._memory_structural_lint(state, wiki_brain)
        items.sort(
            key=lambda item: (
                {"wiki_page": 0, "concept": 1, "system_file": 2, "report": 3}.get(str(item.get("kind") or ""), 4),
                -float(item.get("confidence") or 0.0),
                -int(item.get("record_count") or 0),
                str(item.get("title") or ""),
            )
        )
        return {
            "generated_at": _iso_now(),
            "summary": {
                "total_items": len(items),
                "wiki_pages": page_count,
                "concept_articles": concept_count,
                "graph_nodes": len(list((wiki_brain.get("graph") or {}).get("nodes") or [])),
                "graph_edges": len(list((wiki_brain.get("graph") or {}).get("edges") or [])),
                "records": int((self.memory_overview().get("counts") or {}).get("records") or 0),
                **dict(structural_lint.get("summary") or {}),
            },
            "items": items,
            "structural_lint": structural_lint,
            "transparency": self._memory_explorer_transparency(),
        }

    def memory_explorer_page(self, page_id: str) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        if not self._wiki_brain_path().exists():
            self._render_all(state)
        wiki_brain = self._load_existing_wiki_brain()
        concepts = {
            str(item.get("key") or ""): item
            for item in list((wiki_brain.get("concepts") or []))
            if isinstance(item, dict) and str(item.get("key") or "").strip()
        }
        record_backlinks = dict((wiki_brain.get("record_backlinks") or {}))
        normalized_id = str(page_id or "").strip()
        if not normalized_id:
            raise ValueError("memory_page_id_required")
        if normalized_id in PAGE_SPECS:
            normalized_id = f"page:{normalized_id}"
        if normalized_id.startswith("page:"):
            page_key = normalized_id.split(":", 1)[1]
            page = (state.get("pages") or {}).get(page_key)
            if not isinstance(page, dict):
                raise ValueError("memory_page_not_found")
            records_payload: list[dict[str, Any]] = []
            page_backlinks: dict[str, dict[str, Any]] = {}
            linked_pages = Counter[str]()
            source_refs: list[str] = []
            source_basis: list[Any] = []
            scope_summary = Counter[str]()
            sensitivity_summary = Counter[str]()
            confidence_values: list[float] = []
            claim_bindings: list[dict[str, Any]] = []
            last_updated = None
            for record in sorted(
                [item for item in list(page.get("records") or []) if isinstance(item, dict)],
                key=lambda item: (str(item.get("status") or "active") != "active", str(item.get("updated_at") or "")),
            ):
                envelope = self._normalized_record_envelope(page_key, record)
                metadata = dict(envelope.get("metadata") or {})
                scope_summary[str(envelope.get("scope") or "global")] += 1
                sensitivity_summary[str(envelope.get("sensitivity") or "medium")] += 1
                confidence_values.append(float(record.get("confidence") or 0.0))
                record_dt = _iso_to_datetime(str(record.get("updated_at") or ""))
                if record_dt and (last_updated is None or record_dt > last_updated):
                    last_updated = record_dt
                source_refs.extend([str(item) for item in list(record.get("source_refs") or []) if str(item).strip()])
                source_basis.extend(list(metadata.get("source_basis") or []))
                relation_payloads = list(metadata.get("relations") or [])
                record_ref = f"{page_key}:{record.get('id')}"
                backlinks = list(record_backlinks.get(record_ref) or [])
                for concept_ref in backlinks:
                    concept_key = str((concept_ref or {}).get("key") or "").strip()
                    if not concept_key:
                        continue
                    page_backlinks[concept_key] = {
                        "id": f"concept:{concept_key}",
                        "title": str((concept_ref or {}).get("title") or concepts.get(concept_key, {}).get("title") or _humanize_identifier(concept_key)),
                        "path": str((concept_ref or {}).get("path") or concepts.get(concept_key, {}).get("path") or ""),
                        "reason": "record_backlink",
                    }
                    concept_payload = concepts.get(concept_key) or {}
                    for linked_record in list(concept_payload.get("record_refs") or []):
                        other_page = str((linked_record or {}).get("page_key") or "").strip()
                        if other_page and other_page != page_key:
                            linked_pages[other_page] += 1
                epistemic = self._epistemic_resolution_for_record(page_key, record, envelope)
                claim_binding = self._claim_binding_for_record(page_key, record, envelope, epistemic=epistemic)
                if claim_binding:
                    claim_bindings.append(claim_binding)
                records_payload.append(
                    {
                        "id": record.get("id"),
                        "key": record.get("key"),
                        "title": record.get("title"),
                        "summary": record.get("summary"),
                        "status": record.get("status") or "active",
                        "confidence": record.get("confidence"),
                        "updated_at": record.get("updated_at"),
                        "record_type": envelope.get("record_type"),
                        "scope": envelope.get("scope"),
                        "sensitivity": envelope.get("sensitivity"),
                        "exportability": envelope.get("exportability"),
                        "model_routing_hint": envelope.get("model_routing_hint"),
                        "shareability": metadata.get("shareability"),
                        "source_refs": [self._safe_parse_memory_value(item) for item in list(record.get("source_refs") or [])],
                        "source_basis": [self._safe_parse_memory_value(item) for item in list(metadata.get("source_basis") or [])],
                        "correction_history": [self._safe_parse_memory_value(item) for item in list(metadata.get("correction_history") or [])],
                        "backlinks": backlinks[:8],
                        "relations": relation_payloads[:12],
                        "epistemic": epistemic,
                        "metadata": {
                            key: value
                            for key, value in metadata.items()
                            if key
                            not in {
                                "correction_history",
                                "source_basis",
                                "relations",
                            }
                        },
                    }
                )
            markdown_path = self.wiki_dir / f"{page_key}.md"
            claim_status_counts = Counter[str](str(item.get("status") or "unknown") for item in claim_bindings)
            rendered_markdown = self._render_page_markdown(page_key, page, wiki_brain=wiki_brain)
            article_claim_bindings = self._page_article_claim_bindings(
                page_key,
                page,
                claim_bindings=claim_bindings,
                rendered_markdown=rendered_markdown,
            )
            return {
                "id": normalized_id,
                "kind": "wiki_page",
                "page_key": page_key,
                "title": str(page.get("title") or page_key.title()),
                "summary": PAGE_SPECS.get(page_key, ""),
                "description": PAGE_SPECS.get(page_key, ""),
                "path": str(markdown_path),
                "content_markdown": rendered_markdown,
                "last_updated": last_updated.isoformat() if last_updated else None,
                "confidence": round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else None,
                "scope_summary": dict(scope_summary),
                "sensitivity_summary": dict(sensitivity_summary),
                "source_refs": [self._safe_parse_memory_value(item) for item in list(dict.fromkeys(source_refs))[:24]],
                "source_basis": [self._safe_parse_memory_value(item) for item in list(dict.fromkeys(json.dumps(self._safe_parse_memory_value(item), ensure_ascii=False, sort_keys=True) for item in source_basis if item))[:24]],
                "backlinks": list(page_backlinks.values())[:12],
                "linked_pages": [
                    {
                        "id": f"page:{linked_key}",
                        "title": str(((state.get("pages") or {}).get(linked_key) or {}).get("title") or linked_key.title()),
                        "shared_backlinks": count,
                    }
                    for linked_key, count in linked_pages.most_common(10)
                ],
                "records": records_payload,
                "claim_bindings": claim_bindings[:32],
                "article_claim_bindings": article_claim_bindings[:24],
                "claim_summary": {
                    "bound_records": len(claim_bindings),
                    "status_counts": dict(claim_status_counts),
                },
                "transparency": self._memory_explorer_transparency(),
            }
        if normalized_id.startswith("concept:"):
            concept_key = normalized_id.split(":", 1)[1]
            concept = concepts.get(concept_key)
            if not isinstance(concept, dict):
                raise ValueError("memory_page_not_found")
            markdown_path = Path(str(concept.get("path") or self._concepts_dir() / f"{_slugify(concept_key)}.md"))
            linked_pages = Counter[str]()
            for item in list(concept.get("record_refs") or []):
                linked_key = str((item or {}).get("page_key") or "").strip()
                if linked_key:
                    linked_pages[linked_key] += 1
            claim_bindings = self._concept_claim_bindings(concept, state=state)
            claim_status_counts = Counter[str](str(item.get("status") or "unknown") for item in claim_bindings)
            rendered_markdown = self._render_concept_markdown(concept)
            article_claim_bindings = self._concept_article_claim_bindings(concept, claim_bindings=claim_bindings)
            return {
                "id": normalized_id,
                "kind": "concept",
                "page_key": None,
                "title": str(concept.get("title") or _humanize_identifier(concept_key)),
                "summary": str(concept.get("summary") or ""),
                "description": str(concept.get("summary") or ""),
                "path": str(markdown_path),
                "content_markdown": rendered_markdown,
                "last_updated": concept.get("updated_at"),
                "confidence": concept.get("confidence"),
                "scope_summary": dict(concept.get("scope_summary") or {}),
                "sensitivity_summary": {"dominant": concept.get("dominant_sensitivity")},
                "source_refs": [self._safe_parse_memory_value(item) for item in list(concept.get("source_refs") or [])[:24]],
                "source_basis": [self._safe_parse_memory_value(item) for item in list(concept.get("source_refs") or [])[:24]],
                "backlinks": [
                    {
                        "id": f"page:{item.get('page_key')}",
                        "title": str(((state.get("pages") or {}).get(str(item.get("page_key") or "")) or {}).get("title") or str(item.get("page_key") or "")),
                        "reason": f"{item.get('record_id')} supporting record",
                    }
                    for item in list(concept.get("record_refs") or [])[:12]
                    if str(item.get("page_key") or "").strip()
                ],
                "linked_pages": [
                    {
                        "id": f"page:{linked_key}",
                        "title": str(((state.get("pages") or {}).get(linked_key) or {}).get("title") or linked_key.title()),
                        "shared_backlinks": count,
                    }
                    for linked_key, count in linked_pages.most_common(10)
                ],
                "records": list(concept.get("record_refs") or [])[:16],
                "claim_bindings": claim_bindings[:32],
                "article_claim_bindings": article_claim_bindings[:24],
                "claim_summary": {
                    "bound_records": len(claim_bindings),
                    "status_counts": dict(claim_status_counts),
                },
                "related_concepts": list(concept.get("related_concepts") or [])[:10],
                "quality_flags": list(concept.get("quality_flags") or []),
                "article_sections": dict(concept.get("article_sections") or {}),
                "transparency": self._memory_explorer_transparency(),
            }
        if normalized_id.startswith("system:") or normalized_id.startswith("report:"):
            file_name = normalized_id.split(":", 1)[1]
            base_dir = self.system_dir if normalized_id.startswith("system:") else self._reports_dir()
            path = base_dir / file_name
            if not path.exists():
                raise ValueError("memory_page_not_found")
            content = self._read_text_lossy(path)
            return {
                "id": normalized_id,
                "kind": "system_file" if normalized_id.startswith("system:") else "report",
                "page_key": None,
                "title": file_name,
                "summary": _compact_text(content.splitlines()[0] if content else file_name, limit=160),
                "description": f"{file_name} şeffaflık yüzeyi.",
                "path": str(path),
                "content_markdown": content,
                "last_updated": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                "confidence": None,
                "scope_summary": {"global": 1},
                "sensitivity_summary": {"global": 1},
                "source_refs": [],
                "source_basis": [],
                "backlinks": [],
                "linked_pages": [],
                "records": [],
                "transparency": self._memory_explorer_transparency(),
            }
        raise ValueError("memory_page_not_found")

    def memory_explorer_graph(self, *, limit: int = 40) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        if not self._wiki_brain_path().exists():
            self._render_all(state)
        wiki_brain = self._load_existing_wiki_brain()
        base_nodes = list(((wiki_brain.get("graph") or {}).get("nodes") or []))
        base_edges = list(((wiki_brain.get("graph") or {}).get("edges") or []))
        record_backlinks = dict((wiki_brain.get("record_backlinks") or {}))
        concept_nodes = {
            str(node.get("id") or ""): {
                **node,
                "entity_type": "concept",
                "selection_reason": "wiki_brain_concept",
            }
            for node in base_nodes
            if isinstance(node, dict) and str(node.get("id") or "").strip()
        }
        nodes: dict[str, dict[str, Any]] = dict(concept_nodes)
        relation_nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = list(base_edges[: max(0, limit * 2)])
        active_records = [
            item
            for item in self._memory_active_record_entries(state)
            if str((item.get("record") or {}).get("status") or "active") == "active"
        ]
        active_records.sort(
            key=lambda item: (
                -float(((item.get("envelope") or {}).get("metadata") or {}).get("priority_score") or 0.0),
                -float(((item.get("record") or {}).get("confidence") or 0.0)),
                str((item.get("record") or {}).get("updated_at") or ""),
            )
        )
        max_records = max(12, limit)
        for entry in active_records[:max_records]:
            page_key = str(entry.get("page_key") or "")
            record = dict(entry.get("record") or {})
            envelope = dict(entry.get("envelope") or {})
            metadata = dict(envelope.get("metadata") or {})
            record_node_id = f"record:{page_key}:{record.get('id')}"
            nodes[record_node_id] = {
                "id": record_node_id,
                "title": str(record.get("title") or record.get("id") or "Kayıt"),
                "kind": str(envelope.get("record_type") or "source"),
                "entity_type": "record",
                "page_key": page_key,
                "scope": envelope.get("scope"),
                "confidence": record.get("confidence"),
                "priority_score": metadata.get("priority_score"),
                "selection_reason": "high_priority_record",
            }
            for concept in list(record_backlinks.get(f"{page_key}:{record.get('id')}") or [])[:3]:
                concept_key = str((concept or {}).get("key") or "").strip()
                if not concept_key:
                    continue
                if concept_key not in nodes:
                    nodes[concept_key] = {
                        "id": concept_key,
                        "title": str((concept or {}).get("title") or _humanize_identifier(concept_key)),
                        "kind": "concept",
                        "entity_type": "concept",
                        "selection_reason": "record_backlink",
                    }
                edges.append(
                    {
                        "source": record_node_id,
                        "target": concept_key,
                        "relation_type": "inferred_from",
                        "score": 1.0,
                    }
                )
            for relation in list(metadata.get("relations") or [])[:6]:
                if not isinstance(relation, dict):
                    continue
                target = str(relation.get("target") or "").strip()
                if not target:
                    continue
                if target in nodes:
                    target_node_id = target
                elif target in PAGE_SPECS:
                    target_node_id = f"page:{target}"
                    relation_nodes.setdefault(
                        target_node_id,
                        {
                            "id": target_node_id,
                            "title": str(((state.get("pages") or {}).get(target) or {}).get("title") or target.title()),
                            "kind": "page",
                            "entity_type": "page",
                            "selection_reason": "relation_target",
                        },
                    )
                else:
                    target_node_id = f"relation:{_slugify(target)}"
                    relation_nodes.setdefault(
                        target_node_id,
                        {
                            "id": target_node_id,
                            "title": _humanize_identifier(target),
                            "kind": "relation_target",
                            "entity_type": "reference",
                            "selection_reason": "relation_target",
                        },
                    )
                edges.append(
                    {
                        "source": record_node_id,
                        "target": target_node_id,
                        "relation_type": str(relation.get("relation_type") or "related_to"),
                        "score": 1.0,
                    }
                )
            claim_binding = self._claim_binding_for_record(page_key, record, envelope)
            if claim_binding:
                claim_id = str(claim_binding.get("current_claim_id") or "").strip()
                if claim_id:
                    claim_node_id = f"claim:{claim_id}"
                    nodes[claim_node_id] = {
                        "id": claim_node_id,
                        "title": str(claim_binding.get("record_title") or claim_binding.get("predicate") or "Claim"),
                        "kind": "claim",
                        "entity_type": "claim",
                        "page_key": page_key,
                        "scope": envelope.get("scope"),
                        "confidence": record.get("confidence"),
                        "claim_status": claim_binding.get("status"),
                        "predicate": claim_binding.get("predicate"),
                        "subject_key": claim_binding.get("subject_key"),
                        "support_strength": claim_binding.get("support_strength"),
                        "selection_reason": "resolved_claim",
                    }
                    edges.append(
                        {
                            "source": record_node_id,
                            "target": claim_node_id,
                            "relation_type": "resolves_to",
                            "score": 1.0,
                        }
                    )
                    subject_key = str(claim_binding.get("subject_key") or "").strip()
                    if subject_key:
                        subject_node_id = f"subject:{_slugify(subject_key)}"
                        relation_nodes.setdefault(
                            subject_node_id,
                            {
                                "id": subject_node_id,
                                "title": _humanize_identifier(subject_key),
                                "kind": "claim_subject",
                                "entity_type": "subject",
                                "selection_reason": "claim_subject",
                            },
                        )
                        edges.append(
                            {
                                "source": claim_node_id,
                                "target": subject_node_id,
                                "relation_type": "asserts_about",
                                "score": 1.0,
                            }
                        )
        nodes.update(relation_nodes)
        deduped_edges: list[dict[str, Any]] = []
        seen_edges: set[str] = set()
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            marker = json.dumps(
                [edge.get("source"), edge.get("target"), edge.get("relation_type")],
                ensure_ascii=False,
            )
            if marker in seen_edges:
                continue
            if str(edge.get("source") or "") not in nodes or str(edge.get("target") or "") not in nodes:
                continue
            seen_edges.add(marker)
            deduped_edges.append(edge)
        node_list = list(nodes.values())
        node_list.sort(
            key=lambda item: (
                {"concept": 0, "record": 1, "claim": 2, "subject": 3, "page": 4, "reference": 5}.get(str(item.get("entity_type") or ""), 6),
                -float(item.get("priority_score") or item.get("backlink_count") or 0.0),
                -float(item.get("confidence") or 0.0),
                str(item.get("title") or ""),
            )
        )
        trimmed_nodes = node_list[: max(limit * 2, 24)]
        allowed_ids = {str(item.get("id") or "") for item in trimmed_nodes}
        trimmed_edges = [item for item in deduped_edges if str(item.get("source") or "") in allowed_ids and str(item.get("target") or "") in allowed_ids][: max(limit * 4, 40)]
        relation_type_counts = Counter[str](str(item.get("relation_type") or "related_to") for item in trimmed_edges)
        kind_counts = Counter[str](str(item.get("kind") or "unknown") for item in trimmed_nodes)
        return {
            "generated_at": _iso_now(),
            "backend": str((wiki_brain.get("graph") or {}).get("backend") or "file_graph_v2"),
            "nodes": trimmed_nodes,
            "edges": trimmed_edges,
            "summary": {
                "node_count": len(trimmed_nodes),
                "edge_count": len(trimmed_edges),
                "kind_counts": dict(kind_counts),
                "relation_type_counts": dict(relation_type_counts),
            },
            "legend": {
                "concept": "Compiled wiki concept article",
                "record": "Typed knowledge record",
                "claim": "Resolved canonical claim",
                "subject": "Claim subject target",
                "page": "Wiki page target",
                "reference": "Derived relation target",
            },
        }

    def memory_explorer_timeline(self, *, limit: int = 80) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        events: list[dict[str, Any]] = []

        def add_event(
            *,
            event_id: str,
            timestamp: str | None,
            event_type: str,
            title: str,
            summary: str,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            stamp = str(timestamp or "").strip()
            if not stamp:
                return
            events.append(
                {
                    "id": event_id,
                    "timestamp": stamp,
                    "event_type": event_type,
                    "title": _compact_text(title, limit=180),
                    "summary": _compact_text(summary, limit=600),
                    "metadata": metadata or {},
                }
            )

        log_path = self.system_dir / "log.jsonl"
        if log_path.exists():
            for index, line in enumerate(self._read_text_lossy(log_path).splitlines()[-160:], start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                add_event(
                    event_id=f"log:{index}:{entry.get('timestamp')}",
                    timestamp=str(entry.get("timestamp") or ""),
                    event_type=str(entry.get("event_type") or "system_event"),
                    title=str(entry.get("summary") or entry.get("event_type") or "KB event"),
                    summary=json.dumps(entry.get("details") or {}, ensure_ascii=False),
                    metadata={"origin": "log"},
                )

        for page_key, page in (state.get("pages") or {}).items():
            for record in list((page or {}).get("records") or []):
                if not isinstance(record, dict):
                    continue
                add_event(
                    event_id=f"record:{page_key}:{record.get('id')}:{record.get('updated_at')}",
                    timestamp=str(record.get("updated_at") or ""),
                    event_type="knowledge_record",
                    title=f"{record.get('title') or record.get('id')}",
                    summary=str(record.get("summary") or ""),
                    metadata={
                        "page_key": page_key,
                        "record_id": record.get("id"),
                        "status": record.get("status"),
                    },
                )
                for correction in list(((record.get("metadata") or {}).get("correction_history") or [])[-4:]):
                    if not isinstance(correction, dict):
                        continue
                    add_event(
                        event_id=f"correction:{page_key}:{record.get('id')}:{correction.get('timestamp')}:{correction.get('action')}",
                        timestamp=str(correction.get("timestamp") or ""),
                        event_type=f"memory_{correction.get('action') or 'correction'}",
                        title=f"{record.get('title') or record.get('id')} · {correction.get('action') or 'memory değişikliği'}",
                        summary=str(correction.get("note") or record.get("summary") or ""),
                        metadata={
                            "page_key": page_key,
                            "record_id": record.get("id"),
                            "action": correction.get("action"),
                        },
                    )

        for item in list(state.get("recommendation_history") or [])[-80:]:
            if not isinstance(item, dict):
                continue
            add_event(
                event_id=f"recommendation:{item.get('id')}:{item.get('feedback_at') or item.get('created_at')}",
                timestamp=str(item.get("feedback_at") or item.get("created_at") or ""),
                event_type="recommendation_feedback",
                title=f"{item.get('kind') or 'recommendation'} · {item.get('outcome') or 'pending'}",
                summary=str(item.get("feedback_note") or item.get("suggestion") or item.get("why_this") or ""),
                metadata={
                    "recommendation_id": item.get("id"),
                    "outcome": item.get("outcome"),
                },
            )

        for item in list(state.get("decision_records") or [])[-40:]:
            if not isinstance(item, dict):
                continue
            add_event(
                event_id=f"decision:{item.get('id')}:{item.get('created_at')}",
                timestamp=str(item.get("created_at") or ""),
                event_type="decision_record",
                title=str(item.get("title") or "Decision"),
                summary=str(item.get("summary") or ""),
                metadata={
                    "decision_id": item.get("id"),
                    "risk_level": item.get("risk_level"),
                },
            )

        for item in list(state.get("trigger_history") or [])[-80:]:
            if not isinstance(item, dict):
                continue
            add_event(
                event_id=f"trigger:{item.get('id')}:{item.get('emitted_at')}",
                timestamp=str(item.get("emitted_at") or ""),
                event_type="trigger",
                title=str(item.get("title") or item.get("trigger_type") or "Trigger"),
                summary=f"{item.get('trigger_type') or 'trigger'} · urgency={item.get('urgency') or 'n/a'} · confidence={item.get('confidence') or 'n/a'}",
                metadata={
                    "trigger_type": item.get("trigger_type"),
                    "scope": item.get("scope"),
                    "recommended_action_kind": item.get("recommended_action_kind"),
                },
            )

        reflection = self._load_memory_health_report()
        if reflection:
            add_event(
                event_id=f"reflection:{reflection.get('generated_at')}",
                timestamp=str(reflection.get("generated_at") or ""),
                event_type="reflection_output",
                title="Knowledge reflection",
                summary=json.dumps(reflection.get("summary") or {}, ensure_ascii=False),
                metadata={
                    "health_status": reflection.get("health_status"),
                    "recommended_kb_actions": len(list(reflection.get("recommended_kb_actions") or [])),
                },
            )

        if self.epistemic is not None and hasattr(self.epistemic, "store"):
            store = self.epistemic.store
            for claim in list(store.list_epistemic_claims(self.office_id, include_blocked=True, limit=max(limit * 3, 120)))[: max(limit * 2, 80)]:
                metadata = dict(claim.get("metadata") or {})
                add_event(
                    event_id=f"claim:{claim.get('id')}:{claim.get('updated_at')}",
                    timestamp=str(claim.get("updated_at") or claim.get("created_at") or ""),
                    event_type="claim_superseded"
                    if str(claim.get("validation_state") or "").strip().lower() in {"superseded", "rejected"}
                    else "claim_update",
                    title=f"{claim.get('subject_key') or 'claim'} · {claim.get('predicate') or 'assertion'}",
                    summary=" · ".join(
                        part
                        for part in [
                            _compact_text(claim.get("object_value_text"), limit=180),
                            f"basis={claim.get('epistemic_basis') or 'unknown'}",
                            f"validation={claim.get('validation_state') or 'unknown'}",
                            f"retrieval={claim.get('retrieval_eligibility') or 'unknown'}",
                        ]
                        if str(part or "").strip()
                    ),
                    metadata={
                        "origin": "epistemic_claim",
                        "claim_id": claim.get("id"),
                        "subject_key": claim.get("subject_key"),
                        "predicate": claim.get("predicate"),
                        "basis": claim.get("epistemic_basis"),
                        "validation_state": claim.get("validation_state"),
                        "retrieval_eligibility": claim.get("retrieval_eligibility"),
                        "display_label": metadata.get("display_label"),
                    },
                )
            for snapshot in list(store.list_assistant_context_snapshots(self.office_id, limit=max(limit, 40)))[: max(limit, 40)]:
                source_context = dict(snapshot.get("source_context") or {})
                assistant_pack = list(source_context.get("assistant_context_pack") or [])
                knowledge_context = dict(source_context.get("knowledge_context") or {})
                visible_lines = [
                    str((item or {}).get("prompt_line") or "").strip()
                    for item in assistant_pack
                    if str((item or {}).get("prompt_line") or "").strip()
                ][:3]
                if not visible_lines:
                    visible_lines = [str(item).strip() for item in list(knowledge_context.get("claim_summary_lines") or []) if str(item).strip()][:3]
                add_event(
                    event_id=f"context-snapshot:{snapshot.get('id')}:{snapshot.get('created_at')}",
                    timestamp=str(snapshot.get("created_at") or ""),
                    event_type="assistant_context_snapshot",
                    title=f"Asistan bağlam anlık görüntüsü · mesaj #{snapshot.get('message_id')}",
                    summary="\n".join(visible_lines) if visible_lines else "Asistan yanıtı için bağlam paketi kaydedildi.",
                    metadata={
                        "origin": "assistant_context",
                        "thread_id": snapshot.get("thread_id"),
                        "message_id": snapshot.get("message_id"),
                        "assistant_context_count": len(assistant_pack),
                        "claim_summary_count": len(list(knowledge_context.get("claim_summary_lines") or [])),
                    },
                )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in events:
            marker = str(item.get("id") or "")
            if not marker or marker in seen:
                continue
            seen.add(marker)
            deduped.append(item)
        deduped.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        type_counts = Counter[str](str(item.get("event_type") or "unknown") for item in deduped[:limit])
        return {
            "generated_at": _iso_now(),
            "summary": {
                "total_events": len(deduped[:limit]),
                "event_type_counts": dict(type_counts),
            },
            "items": deduped[:limit],
        }

    def memory_explorer_health(self) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        if not self._wiki_brain_path().exists():
            self._render_all(state)
        wiki_brain = self._load_existing_wiki_brain()
        reflection = self._load_memory_health_report()
        entries = self._memory_active_record_entries(state)
        low_confidence_records: list[dict[str, Any]] = []
        stale_records: list[dict[str, Any]] = []
        contradiction_records: list[dict[str, Any]] = []
        prunable_records: list[dict[str, Any]] = []
        contested_claims: list[dict[str, Any]] = []
        suspicious_claims: list[dict[str, Any]] = []
        current_time = _utcnow()
        for entry in entries:
            page_key = str(entry.get("page_key") or "")
            record = dict(entry.get("record") or {})
            envelope = dict(entry.get("envelope") or {})
            metadata = dict(envelope.get("metadata") or {})
            if str(record.get("status") or "active") != "active":
                continue
            confidence = float(record.get("confidence") or 0.0)
            age_days = None
            updated_dt = _iso_to_datetime(str(record.get("updated_at") or ""))
            if updated_dt is not None:
                age_days = max(0, int((current_time - updated_dt).total_seconds() // 86400))
            if confidence < 0.62:
                low_confidence_records.append(
                    {
                        "page": page_key,
                        "record_id": record.get("id"),
                        "title": record.get("title"),
                        "confidence": round(confidence, 2),
                        "scope": envelope.get("scope"),
                    }
                )
            stale_window = int(STALENESS_WINDOWS.get(page_key, 120) or 120)
            if age_days is not None and age_days > stale_window:
                stale_records.append(
                    {
                        "page": page_key,
                        "record_id": record.get("id"),
                        "title": record.get("title"),
                        "age_days": age_days,
                        "scope": envelope.get("scope"),
                    }
                )
            contradiction_count = int(metadata.get("repeated_contradiction_count") or 0)
            if contradiction_count > 0 or metadata.get("supersedes_record_id"):
                contradiction_records.append(
                    {
                        "page": page_key,
                        "record_id": record.get("id"),
                        "title": record.get("title"),
                        "count": contradiction_count,
                        "supersedes_record_id": metadata.get("supersedes_record_id"),
                    }
                )
            correction_count = len(list(metadata.get("correction_history") or []))
            if confidence < 0.45 or correction_count >= 3:
                prunable_records.append(
                    {
                        "page": page_key,
                        "record_id": record.get("id"),
                        "title": record.get("title"),
                        "confidence": round(confidence, 2),
                        "correction_count": correction_count,
                    }
                )
            epistemic = self._epistemic_resolution_for_record(page_key, record, envelope)
            if isinstance(epistemic, dict) and str(epistemic.get("status") or "") == "contested":
                contested_claims.append(
                    {
                        "page": page_key,
                        "record_id": record.get("id"),
                        "title": record.get("title"),
                        "subject_key": epistemic.get("subject_key"),
                        "predicate": epistemic.get("predicate"),
                        "contested_count": int(epistemic.get("contested_count") or 0),
                    }
                )

        trigger_counts = Counter[str]()
        trigger_key_counts = Counter[str]()
        for item in list(state.get("trigger_history") or [])[-80:]:
            if not isinstance(item, dict):
                continue
            trigger_type = str(item.get("trigger_type") or "trigger").strip() or "trigger"
            trigger_counts[trigger_type] += 1
            logical_key = str(item.get("logical_key") or trigger_type).strip() or trigger_type
            trigger_key_counts[logical_key] += 1
        spam_risk = [
            {
                "trigger_type": trigger_type,
                "count": count,
                "reason": "Aynı trigger türü kısa dönemde tekrarlandı.",
            }
            for trigger_type, count in trigger_counts.most_common(8)
            if count >= 3
        ]
        spam_risk.extend(
            {
                "trigger_type": logical_key,
                "count": count,
                "reason": "Aynı logical_key tekrar ediyor; cooldown veya suppression gözden geçirilmeli.",
            }
            for logical_key, count in trigger_key_counts.most_common(8)
            if count >= 3 and not any(item.get("trigger_type") == logical_key for item in spam_risk)
        )
        overview = self.memory_overview()
        reflection_status = self.reflection_status()
        epistemic_claims = (
            getattr(self.epistemic, "store").list_epistemic_claims(self.office_id, include_blocked=True, limit=2000)
            if self.epistemic is not None and hasattr(self.epistemic, "store")
            else []
        )
        claim_status_counts = Counter[str](str(item.get("validation_state") or "unknown") for item in epistemic_claims)
        claim_retrieval_counts = Counter[str](str(item.get("retrieval_eligibility") or "unknown") for item in epistemic_claims)
        claim_support_strength_counts = Counter[str]()
        claim_memory_tier_counts = Counter[str]()
        contaminated_claim_count = 0
        if self.epistemic is not None:
            for item in epistemic_claims:
                support = self.epistemic.inspect_claim_support(claim=item)
                memory_profile = self.epistemic.describe_claim_memory(claim=item, support=support)
                strength = str((support or {}).get("support_strength") or "unknown")
                claim_support_strength_counts[strength] += 1
                claim_memory_tier_counts[str(memory_profile.get("memory_tier") or "unknown")] += 1
                if bool((support or {}).get("contaminated")):
                    contaminated_claim_count += 1
                    suspicious_claims.append(
                        {
                            "claim_id": item.get("id"),
                            "subject_key": item.get("subject_key"),
                            "predicate": item.get("predicate"),
                            "basis": item.get("epistemic_basis"),
                            "support_strength": strength,
                            "memory_tier": memory_profile.get("memory_tier"),
                            "salience_score": memory_profile.get("salience_score"),
                            "reason_codes": list((support or {}).get("reason_codes") or []),
                        }
                    )
        lint_report = self.memory_explorer_lint()
        structural_lint = self._memory_structural_lint(state, wiki_brain)
        merged_summary = dict(reflection.get("summary") or {})
        merged_summary.update(
            {
                "lint_contradictions": int(((lint_report.get("summary") or {}).get("contradictions") or 0)),
                "lint_weak_claims": int(((lint_report.get("summary") or {}).get("weak_claims") or 0)),
                "lint_stale_claims": int(((lint_report.get("summary") or {}).get("stale_claims") or 0)),
                "orphan_pages": int(((structural_lint.get("summary") or {}).get("orphan_pages") or 0)),
            }
        )
        return {
            "generated_at": _iso_now(),
            "summary": merged_summary,
            "reflection_status": reflection_status,
            "health_status": reflection.get("health_status") or reflection_status.get("health_status") or "unknown",
            "low_confidence_records": low_confidence_records[:20],
            "contradictions": contradiction_records[:20],
            "stale_records": stale_records[:20],
            "recommendation_spam_risk": spam_risk[:12],
            "knowledge_gaps": list(reflection.get("knowledge_gaps") or [])[:20],
            "research_topics": list(reflection.get("research_topics") or [])[:20],
            "potential_wiki_pages": list(reflection.get("potential_wiki_pages") or [])[:20],
            "prunable_records": (list(reflection.get("prunable_records") or [])[:20] or prunable_records[:20]),
            "inconsistency_hotspots": list(reflection.get("inconsistency_hotspots") or [])[:20],
            "contested_claims": contested_claims[:20],
            "suspicious_claims": suspicious_claims[:20],
            "claim_summary": {
                "total_claims": len(epistemic_claims),
                "validation_state_counts": dict(claim_status_counts),
                "retrieval_eligibility_counts": dict(claim_retrieval_counts),
                "support_strength_counts": dict(claim_support_strength_counts),
                "memory_tier_counts": dict(claim_memory_tier_counts),
                "contaminated_claims": contaminated_claim_count,
            },
            "knowledge_lint": lint_report,
            "structural_lint": structural_lint,
            "recommended_kb_actions": list(reflection.get("recommended_kb_actions") or reflection_status.get("recommended_kb_actions") or [])[:20],
            "reflection_output": {
                "generated_at": reflection.get("generated_at"),
                "user_model_summary": list(reflection.get("user_model_summary") or [])[:10],
                "wiki_brain_summary": dict(reflection.get("wiki_brain_summary") or {}),
                "suggested_new_nodes": list(reflection.get("suggested_new_nodes") or [])[:10],
            },
            "memory_overview": overview,
            "transparency": self._memory_explorer_transparency(),
        }

    def coaching_status(self, *, store: Any | None = None) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        coaching = dict(state.get("coaching") or {})
        goals = dict(coaching.get("goals") or {})
        assistant_core = self.assistant_core_status(store=store)
        progress_logs = list(coaching.get("progress_logs") or [])
        recent_logs = sorted(progress_logs, key=lambda item: str(item.get("happened_at") or ""), reverse=True)
        now = _utcnow()
        local_now = now.astimezone()
        active_goals: list[dict[str, Any]] = []
        completed_goals: list[dict[str, Any]] = []
        derived_focus: list[dict[str, Any]] = []
        due_checkins: list[dict[str, Any]] = []
        notification_candidates: list[dict[str, Any]] = []

        for goal_id, payload in goals.items():
            if not isinstance(payload, dict):
                continue
            goal = self._coaching_goal_view(goal_id, payload, progress_logs=progress_logs, now=local_now)
            if str(goal.get("status") or "active") == "completed":
                completed_goals.append(goal)
            else:
                active_goals.append(goal)
            if goal.get("needs_checkin"):
                due_checkins.append(goal)
                if goal.get("allow_desktop_notifications", True):
                    notification_candidates.append(
                        {
                            "id": f"coach-reminder:{goal_id}:{local_now.date().isoformat()}",
                            "goal_id": goal_id,
                            "title": str(goal.get("title") or "Koçluk hatırlatması"),
                            "body": (
                                f"{goal.get('title') or 'Hedef'} için bugün check-in zamanı."
                                if not goal.get("remaining_value_text")
                                else f"{goal.get('title') or 'Hedef'} için {goal.get('remaining_value_text')} kaldı."
                            ),
                            "scope": goal.get("scope"),
                            "priority": "high" if goal.get("priority_label") == "high" else "medium",
                            "notify_desktop": True,
                            "why_now": goal.get("why_now"),
                        }
                    )

        for page_key in ("projects", "routines", "preferences"):
            for record in (((state.get("pages") or {}).get(page_key) or {}).get("records") or []):
                if not isinstance(record, dict):
                    continue
                if str(record.get("status") or "active") != "active":
                    continue
                metadata = dict(record.get("metadata") or {})
                if metadata.get("coach_goal"):
                    continue
                record_type = str(metadata.get("record_type") or "")
                if record_type not in {"goal", "constraint", "routine"}:
                    continue
                derived_focus.append(
                    {
                        "page_key": page_key,
                        "record_id": record.get("id"),
                        "title": record.get("title"),
                        "summary": record.get("summary"),
                        "scope": metadata.get("scope") or self._infer_scope(page_key, metadata, record),
                        "record_type": record_type,
                        "confidence": record.get("confidence"),
                    }
                )
        derived_focus.sort(key=lambda item: str(item.get("title") or ""))
        active_goals.sort(key=lambda item: (-int(bool(item.get("needs_attention"))), -float(item.get("progress_ratio") or 0.0), str(item.get("title") or "")))
        completed_goals.sort(key=lambda item: str(item.get("completed_at") or item.get("updated_at") or ""), reverse=True)
        due_checkins.sort(key=lambda item: (-int(bool(item.get("needs_attention"))), str(item.get("next_check_in_at") or ""), str(item.get("title") or "")))

        bucket_counts = Counter[str]()
        for item in recent_logs:
            happened_at = _iso_to_datetime(str(item.get("happened_at") or ""))
            if happened_at is None:
                continue
            local_dt = happened_at.astimezone()
            bucket_counts[self._time_bucket_for_hour(local_dt.hour)] += 1
        dominant_bucket = bucket_counts.most_common(1)[0][0] if bucket_counts else None
        insights: list[str] = []
        if due_checkins:
            insights.append(f"{len(due_checkins)} hedef bugün takip bekliyor.")
        if dominant_bucket:
            insights.append(f"İlerleme kayıtları en çok {dominant_bucket} bandında geliyor.")
        if any(item.get("streak_days", 0) >= 3 for item in active_goals):
            insights.append("En az bir hedefte üç gün ve üzeri devamlılık oluştu.")
        if not active_goals and derived_focus:
            insights.append("Açık koçluk hedefi yok; mevcut knowledge içinden türetilen odak alanları var.")

        tasks_due_today = 0
        if store is not None:
            try:
                tasks_due_today = sum(
                    1
                    for item in store.list_office_tasks(self.office_id) or []
                    if str(item.get("status") or "") != "completed"
                    and str(item.get("due_at") or "").startswith(local_now.date().isoformat())
                )
            except Exception:
                tasks_due_today = 0

        summary = {
            "active_goals": len(active_goals),
            "completed_goals": len(completed_goals),
            "due_checkins": len(due_checkins),
            "progress_logs": len(progress_logs),
            "tasks_due_today": tasks_due_today,
            "attention_required": sum(1 for item in active_goals if item.get("needs_attention")),
        }
        enabled = bool(assistant_core.get("supports_coaching")) or summary["active_goals"] > 0 or summary["completed_goals"] > 0
        return {
            "enabled": enabled,
            "activation_reason": (
                "assistant_form_active"
                if assistant_core.get("supports_coaching")
                else "goal_present"
                if summary["active_goals"] > 0 or summary["completed_goals"] > 0
                else "inactive"
            ),
            "updated_at": coaching.get("updated_at") or state.get("updated_at"),
            "last_review_at": coaching.get("last_review_at"),
            "summary": summary,
            "active_goals": active_goals[:8],
            "completed_goals": completed_goals[:5],
            "due_checkins": due_checkins[:6],
            "recent_progress_logs": recent_logs[:10],
            "notification_candidates": notification_candidates[:6],
            "derived_focus_areas": derived_focus[:6],
            "insights": insights[:6],
            "plan": dict(coaching.get("last_plan") or {}),
        }

    def upsert_coaching_goal(
        self,
        *,
        title: str,
        summary: str | None = None,
        cadence: str = "daily",
        target_value: float | None = None,
        unit: str | None = None,
        goal_id: str | None = None,
        scope: str = "personal",
        sensitivity: str = "high",
        reminder_time: str | None = None,
        preferred_days: list[str] | None = None,
        target_date: str | None = None,
        allow_desktop_notifications: bool = True,
        note: str | None = None,
        source_refs: list[dict[str, Any] | str] | None = None,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        now = _iso_now()
        local_now = _utcnow().astimezone()
        normalized_title = _compact_text(title, limit=140)
        if len(normalized_title) < 3:
            raise ValueError("goal_title_too_short")
        normalized_cadence = str(cadence or "daily").strip().lower() or "daily"
        if normalized_cadence not in {"daily", "weekly", "flexible", "one_time"}:
            raise ValueError("unsupported_goal_cadence")
        normalized_scope = str(scope or "personal").strip() or "personal"
        normalized_sensitivity = str(sensitivity or "high").strip() or "high"
        normalized_days = [str(item).strip().lower() for item in list(preferred_days or []) if str(item).strip()]
        state = self._load_state()
        coaching = dict(state.get("coaching") or {})
        goals = dict(coaching.get("goals") or {})
        resolved_goal_id = str(goal_id or "").strip() or f"goal-{_slugify(normalized_title)}-{_fingerprint([normalized_title, now])[:6]}"
        previous = dict(goals.get(resolved_goal_id) or {})
        current_value = float(previous.get("current_value") or 0.0)
        next_target_value = float(target_value) if target_value is not None else (float(previous.get("target_value")) if previous.get("target_value") is not None else None)
        next_summary = _compact_text(summary or previous.get("summary") or normalized_title, limit=600)
        next_unit = _compact_text(unit or previous.get("unit") or "", limit=48)
        next_reminder = _compact_text(reminder_time or previous.get("reminder_time") or "", limit=16)
        goal_payload = {
            "id": resolved_goal_id,
            "title": normalized_title,
            "summary": next_summary,
            "cadence": normalized_cadence,
            "target_value": next_target_value,
            "current_value": current_value,
            "unit": next_unit,
            "scope": normalized_scope,
            "sensitivity": normalized_sensitivity,
            "preferred_days": normalized_days or list(previous.get("preferred_days") or []),
            "target_date": str(target_date or previous.get("target_date") or "").strip() or None,
            "reminder_time": next_reminder or None,
            "allow_desktop_notifications": bool(allow_desktop_notifications if allow_desktop_notifications is not None else previous.get("allow_desktop_notifications", True)),
            "status": str(previous.get("status") or "active"),
            "created_at": str(previous.get("created_at") or now),
            "updated_at": now,
            "last_progress_at": previous.get("last_progress_at"),
            "completed_at": previous.get("completed_at"),
            "source_refs": [str(item) if not isinstance(item, dict) else json.dumps(item, ensure_ascii=False, sort_keys=True) for item in list(source_refs or previous.get("source_refs") or [])],
            "coach_note": _compact_text(note or previous.get("coach_note") or "", limit=400) or None,
        }
        goal_payload["next_check_in_at"] = self._coaching_next_check_in_at(goal_payload, now=local_now)
        goals[resolved_goal_id] = goal_payload
        coaching["goals"] = goals
        coaching["updated_at"] = now
        state["coaching"] = coaching
        goal_record = self._coaching_goal_record(goal_payload, now=now)
        previous_page_key = self._coaching_goal_page_key(previous) if previous else None
        next_page_key = str(goal_record.get("_page_key") or "")
        if previous_page_key and previous_page_key != next_page_key:
            old_page, old_record = self._locate_record(state, target_record_id=f"coach-goal-{resolved_goal_id}", page_key=previous_page_key)
            if old_page and old_record:
                old_record["status"] = "superseded"
                old_record["superseded_at"] = now
        self._upsert_page_record(state, str(goal_record.pop("_page_key")), goal_record)
        state["updated_at"] = now
        self._save_state(state)
        self._render_all(state)
        plan = self.refresh_coaching_plan(reason="goal_upsert", persist=True)
        self._append_log(
            "coaching_goal_upserted",
            "Koçluk hedefi güncellendi",
            {
                "goal_id": resolved_goal_id,
                "title": normalized_title,
                "cadence": normalized_cadence,
                "target_value": next_target_value,
                "unit": next_unit,
            },
        )
        status = self.coaching_status()
        return {
            "goal": next((item for item in status.get("active_goals") or [] if str(item.get("id") or "") == resolved_goal_id), goal_payload),
            "dashboard": status,
            "plan": plan,
        }

    def log_coaching_progress(
        self,
        *,
        goal_id: str,
        amount: float | None = None,
        note: str | None = None,
        completed: bool = False,
        happened_at: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        coaching = dict(state.get("coaching") or {})
        goals = dict(coaching.get("goals") or {})
        goal = dict(goals.get(goal_id) or {})
        if not goal:
            raise ValueError("goal_not_found")
        now = _iso_now()
        occurred_at = str(happened_at or now).strip() or now
        increment = float(amount) if amount is not None else (1.0 if completed else 0.0)
        next_value = round(float(goal.get("current_value") or 0.0) + increment, 2)
        target_value = float(goal.get("target_value")) if goal.get("target_value") is not None else None
        next_status = str(goal.get("status") or "active")
        if completed or (target_value is not None and next_value >= target_value > 0):
            next_status = "completed"
        log_entry = {
            "id": f"coach-log-{_fingerprint([goal_id, occurred_at, increment, note, completed])[:10]}",
            "goal_id": goal_id,
            "amount": increment,
            "note": _compact_text(note or "", limit=500) or None,
            "completed": bool(completed),
            "happened_at": occurred_at,
            "resulting_value": next_value,
            "unit": goal.get("unit"),
        }
        progress_logs = list(coaching.get("progress_logs") or [])
        progress_logs.append(log_entry)
        coaching["progress_logs"] = progress_logs[-400:]
        goal["current_value"] = next_value
        goal["updated_at"] = now
        goal["last_progress_at"] = occurred_at
        goal["status"] = next_status
        if next_status == "completed":
            goal["completed_at"] = goal.get("completed_at") or occurred_at
        goal["next_check_in_at"] = self._coaching_next_check_in_at(goal, now=_iso_to_datetime(occurred_at) or _utcnow())
        goals[goal_id] = goal
        coaching["goals"] = goals
        coaching["updated_at"] = now
        state["coaching"] = coaching
        goal_record = self._coaching_goal_record(goal, now=now)
        self._upsert_page_record(state, str(goal_record.pop("_page_key")), goal_record)
        progress_record = self._coaching_progress_record(goal, log_entry)
        self._upsert_page_record(state, str(progress_record.pop("_page_key")), progress_record)
        state["updated_at"] = now
        self._save_state(state)
        self._render_all(state)
        self._append_log(
            "coaching_progress_logged",
            "Koçluk ilerleme kaydı eklendi",
            {"goal_id": goal_id, "amount": increment, "completed": completed},
        )
        plan = self.refresh_coaching_plan(reason="progress_log", persist=True)
        status = self.coaching_status()
        return {
            "goal": next((item for item in [*(status.get("active_goals") or []), *(status.get("completed_goals") or [])] if str(item.get("id") or "") == goal_id), goal),
            "progress_log": log_entry,
            "dashboard": status,
            "plan": plan,
        }

    def refresh_coaching_plan(self, *, reason: str = "manual_coaching_review", persist: bool = True) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        coaching = dict(state.get("coaching") or {})
        dashboard = self.coaching_status()
        active_goals = list(dashboard.get("active_goals") or [])
        due_checkins = list(dashboard.get("due_checkins") or [])
        recent_logs = list(dashboard.get("recent_progress_logs") or [])
        strengths: list[str] = []
        risks: list[str] = []
        strategies: list[str] = []
        hypotheses: list[str] = []

        for item in active_goals[:4]:
            if int(item.get("streak_days") or 0) >= 2:
                strengths.append(f"{item.get('title')} hedefinde devamlılık korunuyor.")
            if bool(item.get("needs_attention")):
                risks.append(f"{item.get('title')} hedefi bugün check-in bekliyor.")
        if due_checkins:
            strategies.append("Günün ilk uygun bloğunda yalnızca tek bir koçluk hedefiyle başlanmalı.")
        if any(str(item.get("cadence") or "") == "daily" for item in active_goals):
            strategies.append("Günlük hedefler için sabit saatli hatırlatma ve kısa progress girişi kullanılmalı.")
        if recent_logs:
            recent_notes = [str(item.get("note") or "").strip() for item in recent_logs[:5] if str(item.get("note") or "").strip()]
            if recent_notes:
                hypotheses.append("Kullanıcı not bıraktığında ilerleme kaydı daha anlamlı ve sürdürülebilir oluyor.")
        if not active_goals and dashboard.get("derived_focus_areas"):
            strategies.append("Önce türetilen odak alanlarından birini explicit hedefe dönüştürmek gerekiyor.")

        plan = {
            "generated_at": _iso_now(),
            "reason": reason,
            "summary": {
                "active_goals": len(active_goals),
                "due_checkins": len(due_checkins),
                "recent_progress_logs": len(recent_logs),
            },
            "focus": [
                {
                    "goal_id": item.get("id"),
                    "title": item.get("title"),
                    "progress_ratio": item.get("progress_ratio"),
                    "next_check_in_at": item.get("next_check_in_at"),
                }
                for item in active_goals[:4]
            ],
            "strengths": strengths[:5],
            "risks": risks[:5],
            "strategies": strategies[:5],
            "hypotheses": hypotheses[:5],
        }
        if persist:
            coaching["last_plan"] = plan
            coaching["last_review_at"] = plan["generated_at"]
            coaching["updated_at"] = plan["generated_at"]
            state["coaching"] = coaching
            state["updated_at"] = plan["generated_at"]
            self._save_state(state)
            self._render_all(state)
            self._append_log(
                "coaching_plan_refreshed",
                "Koçluk planı yenilendi",
                {"reason": reason, "active_goals": len(active_goals), "due_checkins": len(due_checkins)},
            )
        return plan

    @staticmethod
    def _time_bucket_for_hour(hour: int) -> str:
        if 5 <= hour < 11:
            return "morning"
        if 11 <= hour < 16:
            return "midday"
        if 16 <= hour < 21:
            return "evening"
        return "night"

    def _coaching_goal_view(
        self,
        goal_id: str,
        payload: dict[str, Any],
        *,
        progress_logs: list[dict[str, Any]],
        now: datetime,
    ) -> dict[str, Any]:
        logs = [item for item in progress_logs if str(item.get("goal_id") or "") == goal_id]
        target_value = float(payload.get("target_value")) if payload.get("target_value") is not None else None
        current_value = float(payload.get("current_value") or 0.0)
        progress_ratio = round(min(1.0, current_value / target_value), 4) if target_value and target_value > 0 else 1.0 if str(payload.get("status") or "") == "completed" else 0.0
        last_progress_at = str(payload.get("last_progress_at") or "")
        last_progress_dt = _iso_to_datetime(last_progress_at)
        last_local_dt = last_progress_dt.astimezone() if last_progress_dt else None
        updated_dt = _iso_to_datetime(str(payload.get("updated_at") or ""))
        today_logged = bool(last_local_dt and last_local_dt.date() == now.date())
        next_check_in_at = str(payload.get("next_check_in_at") or self._coaching_next_check_in_at(payload, now=now) or "")
        next_check_in_dt = _iso_to_datetime(next_check_in_at)
        needs_checkin = False
        if str(payload.get("status") or "active") == "active":
            if str(payload.get("cadence") or "") == "daily":
                needs_checkin = not today_logged and (next_check_in_dt is None or next_check_in_dt.astimezone() <= now)
            elif str(payload.get("cadence") or "") == "weekly":
                days_since = (now - last_local_dt).days if last_local_dt else 99
                needs_checkin = days_since >= 7 or (next_check_in_dt is not None and next_check_in_dt.astimezone() <= now)
            elif str(payload.get("cadence") or "") == "flexible":
                days_since = (now - last_local_dt).days if last_local_dt else 99
                needs_checkin = days_since >= 3
            elif str(payload.get("cadence") or "") == "one_time":
                due_dt = _iso_to_datetime(str(payload.get("target_date") or ""))
                needs_checkin = bool(due_dt and due_dt.astimezone() <= now and str(payload.get("status") or "") != "completed")
        streak_days = self._coaching_streak_days(logs)
        remaining_value = None
        remaining_value_text = ""
        if target_value is not None:
            remaining_value = round(max(0.0, target_value - current_value), 2)
            unit = str(payload.get("unit") or "").strip()
            remaining_value_text = f"{remaining_value:g} {unit}".strip()
        priority_label = "high" if needs_checkin else "medium" if progress_ratio < 0.4 and target_value else "low"
        summary = str(payload.get("summary") or payload.get("title") or "").strip()
        return {
            **payload,
            "id": goal_id,
            "summary": summary,
            "progress_ratio": progress_ratio,
            "progress_percent": int(round(progress_ratio * 100)),
            "remaining_value": remaining_value,
            "remaining_value_text": remaining_value_text or None,
            "last_progress_at": last_progress_at or None,
            "next_check_in_at": next_check_in_at or None,
            "needs_checkin": needs_checkin,
            "needs_attention": needs_checkin or (updated_dt is not None and (now - updated_dt.astimezone()).days >= 7),
            "streak_days": streak_days,
            "why_now": (
                f"{payload.get('title')} hedefi için bugünkü check-in henüz gelmedi."
                if needs_checkin
                else "Hedef izleniyor ve son ilerleme kaydı knowledge base'e işlendi."
            ),
            "priority_label": priority_label,
            "page_key": self._coaching_goal_page_key(payload),
        }

    def _coaching_next_check_in_at(self, goal: dict[str, Any], *, now: datetime) -> str | None:
        current_time = now.astimezone()
        reminder_time = str(goal.get("reminder_time") or "").strip()
        hour = 9
        minute = 0
        if reminder_time and ":" in reminder_time:
            try:
                hour = max(0, min(23, int(reminder_time.split(":", 1)[0])))
                minute = max(0, min(59, int(reminder_time.split(":", 1)[1])))
            except ValueError:
                hour = 9
                minute = 0
        candidate = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        cadence = str(goal.get("cadence") or "daily")
        last_progress_dt = _iso_to_datetime(str(goal.get("last_progress_at") or ""))
        if cadence == "daily":
            if candidate <= current_time or (last_progress_dt and last_progress_dt.astimezone().date() == current_time.date()):
                candidate = candidate + timedelta(days=1)
        elif cadence == "weekly":
            preferred_days = [str(item).strip().lower() for item in list(goal.get("preferred_days") or []) if str(item).strip()]
            weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            for offset in range(0, 8):
                probe = candidate + timedelta(days=offset)
                if preferred_days and weekday_names[probe.weekday()] not in preferred_days:
                    continue
                if probe <= current_time:
                    continue
                candidate = probe
                break
        elif cadence == "flexible":
            anchor = last_progress_dt.astimezone() if last_progress_dt else current_time
            candidate = anchor + timedelta(days=3)
            candidate = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
        elif cadence == "one_time":
            due_at = _iso_to_datetime(str(goal.get("target_date") or ""))
            if due_at is not None:
                return due_at.astimezone().isoformat()
        return candidate.isoformat()

    def _coaching_streak_days(self, logs: list[dict[str, Any]]) -> int:
        days = sorted(
            {
                (_iso_to_datetime(str(item.get("happened_at") or "")) or _utcnow()).astimezone().date().isoformat()
                for item in logs
            },
            reverse=True,
        )
        if not days:
            return 0
        streak = 0
        expected = None
        for value in days:
            try:
                current_day = datetime.fromisoformat(f"{value}T00:00:00+00:00").date()
            except ValueError:
                break
            if expected is None:
                expected = current_day
                streak = 1
                continue
            if current_day == expected - timedelta(days=1):
                streak += 1
                expected = current_day
                continue
            break
        return streak

    def _coaching_goal_page_key(self, goal: dict[str, Any]) -> str:
        cadence = str(goal.get("cadence") or "daily")
        return "routines" if cadence in {"daily", "weekly"} else "projects"

    def _coaching_goal_record(self, goal: dict[str, Any], *, now: str) -> dict[str, Any]:
        page_key = self._coaching_goal_page_key(goal)
        scope = str(goal.get("scope") or "personal")
        sensitivity = str(goal.get("sensitivity") or "high")
        target_value = float(goal.get("target_value")) if goal.get("target_value") is not None else None
        current_value = float(goal.get("current_value") or 0.0)
        unit = str(goal.get("unit") or "").strip()
        progress_summary = f"{current_value:g}" if not unit else f"{current_value:g} {unit}"
        if target_value is not None:
            progress_summary = f"{progress_summary} / {target_value:g} {unit}".strip()
        metadata = {
            "record_type": "routine" if page_key == "routines" else "goal",
            "scope": scope,
            "sensitivity": sensitivity,
            "shareability": _scope_shareability(scope, sensitivity),
            "coach_goal": True,
            "coach_goal_id": goal.get("id"),
            "goal_kind": "habit" if page_key == "routines" else "goal",
            "cadence": goal.get("cadence"),
            "target_value": target_value,
            "current_value": current_value,
            "unit": unit,
            "progress_ratio": round(min(1.0, current_value / target_value), 4) if target_value and target_value > 0 else None,
            "target_date": goal.get("target_date"),
            "reminder_time": goal.get("reminder_time"),
            "preferred_days": list(goal.get("preferred_days") or []),
            "coach_status": goal.get("status"),
            "allow_desktop_notifications": bool(goal.get("allow_desktop_notifications", True)),
            "source_basis": list(goal.get("source_refs") or []),
            "relations": [
                {"relation_type": "supports", "target": "daily_planning"},
                {"relation_type": "relevant_to", "target": "coaching"},
            ],
        }
        return {
            "_page_key": page_key,
            "id": f"coach-goal-{goal.get('id')}",
            "key": f"coach_goal:{goal.get('id')}",
            "title": _compact_text(str(goal.get("title") or "Koçluk hedefi"), limit=160),
            "summary": _compact_text(
                " | ".join(
                    part
                    for part in [
                        str(goal.get("summary") or "").strip(),
                        f"Kadans: {goal.get('cadence')}",
                        f"İlerleme: {progress_summary}" if progress_summary else "",
                        f"Son check-in: {goal.get('last_progress_at')}" if goal.get("last_progress_at") else "",
                    ]
                    if part
                ),
                limit=800,
            ),
            "confidence": 0.95,
            "status": "active",
            "source_refs": list(goal.get("source_refs") or []),
            "signals": ["explicit_user_correction", "coaching_goal"],
            "updated_at": now,
            "metadata": metadata,
        }

    def _coaching_progress_record(self, goal: dict[str, Any], log_entry: dict[str, Any]) -> dict[str, Any]:
        unit = str(log_entry.get("unit") or goal.get("unit") or "").strip()
        amount = float(log_entry.get("amount") or 0.0)
        summary = " | ".join(
            part
            for part in [
                f"{goal.get('title')} hedefi için ilerleme kaydı",
                f"{amount:g} {unit}".strip() if amount else "",
                str(log_entry.get("note") or "").strip(),
            ]
            if part
        )
        return {
            "_page_key": "projects",
            "id": str(log_entry.get("id") or f"coach-progress-{goal.get('id')}"),
            "key": f"coach_progress:{goal.get('id')}:{log_entry.get('happened_at')}",
            "title": _compact_text(f"{goal.get('title')} ilerleme güncellemesi", limit=160),
            "summary": _compact_text(summary, limit=800),
            "confidence": 0.9,
            "status": "active",
            "source_refs": list(goal.get("source_refs") or []),
            "signals": ["manual_progress_log", "coaching_goal"],
            "updated_at": str(log_entry.get("happened_at") or _iso_now()),
            "metadata": {
                "record_type": "event",
                "scope": str(goal.get("scope") or "personal"),
                "sensitivity": str(goal.get("sensitivity") or "high"),
                "shareability": _scope_shareability(str(goal.get("scope") or "personal"), str(goal.get("sensitivity") or "high")),
                "coach_goal_id": goal.get("id"),
                "coach_progress": True,
                "amount": amount,
                "unit": unit,
                "completed": bool(log_entry.get("completed")),
                "relations": [
                    {"relation_type": "related_to", "target": f"coach_goal:{goal.get('id')}"},
                    {"relation_type": "supports", "target": "coaching_progress"},
                ],
            },
        }

    def register_connector_push_checkpoint(
        self,
        *,
        provider: str,
        synced_at: str | None,
        stats: dict[str, Any] | None = None,
        checkpoint: dict[str, Any] | None = None,
        cursor: str | None = None,
        reason: str = "mirror_push",
        trigger: str = "integration_sync",
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        connector_sync = dict(state.get("connector_sync") or {})
        mirror_events = dict(connector_sync.get("mirror_events") or {})
        mirror_events[str(provider)] = {
            "provider": provider,
            "synced_at": synced_at or _iso_now(),
            "stats": dict(stats or {}),
            "checkpoint": dict(checkpoint or {}),
            "cursor": str(cursor or "").strip() or None,
            "reason": reason,
            "trigger": trigger,
        }
        connector_sync["mirror_events"] = mirror_events
        connector_sync["updated_at"] = _iso_now()
        connector_sync["last_reason"] = reason
        state["connector_sync"] = connector_sync
        self._save_state(state)
        return mirror_events[str(provider)]

    def run_connector_sync(
        self,
        *,
        store: Any,
        reason: str = "manual_connector_sync",
        connector_names: list[str] | None = None,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}
        self.ensure_scaffold()
        requested_names = [str(item).strip() for item in list(connector_names or []) if str(item).strip()]
        state = self._load_state()
        connector_sync = dict(state.get("connector_sync") or {})
        jobs = list(connector_sync.get("jobs") or [])
        job = {
            "id": f"sync-job-{_fingerprint([reason, requested_names, _iso_now()])[:10]}",
            "connector_names": requested_names or [connector.name for connector in self.connector_registry],
            "reason": reason,
            "trigger": trigger,
            "status": "running",
            "created_at": _iso_now(),
        }
        jobs.append(job)
        connector_sync["jobs"] = jobs[-30:]
        state["connector_sync"] = connector_sync
        self._save_state(state)

        result = self._sync_connector_records(store, reason=reason, connector_names=requested_names or None, trigger=trigger)
        state = self._load_state()
        connector_sync = dict(state.get("connector_sync") or {})
        jobs = list(connector_sync.get("jobs") or [])
        for item in jobs:
            if str(item.get("id") or "") != job["id"]:
                continue
            failed_connectors = list(result.get("failed_connectors") or [])
            item["status"] = "completed_with_errors" if failed_connectors else "completed"
            item["completed_at"] = _iso_now()
            item["synced_record_count"] = result.get("synced_record_count", 0)
            item["updated_pages"] = result.get("updated_pages") or []
            item["failed_connectors"] = failed_connectors
            break
        connector_sync["jobs"] = jobs[-30:]
        state["connector_sync"] = connector_sync
        self._save_state(state)
        failed_connectors = list((result or {}).get("failed_connectors") or [])
        self._log_runtime_event(
            "personal_kb_connector_sync_completed",
            level="warning" if failed_connectors else "info",
            reason=reason,
            trigger=trigger,
            requested_connector_count=len(job.get("connector_names") or []),
            synced_record_count=int((result or {}).get("synced_record_count") or 0),
            updated_page_count=len(list((result or {}).get("updated_pages") or [])),
            failed_connector_count=len(failed_connectors),
        )
        return {
            "job": next((item for item in jobs if str(item.get("id") or "") == job["id"]), job),
            "result": result,
            "status": self.connector_sync_status(store=store),
        }

    def apply_memory_correction(
        self,
        *,
        action: str,
        page_key: str | None = None,
        target_record_id: str | None = None,
        key: str | None = None,
        corrected_summary: str | None = None,
        scope: str | None = None,
        note: str | None = None,
        recommendation_kind: str | None = None,
        topic: str | None = None,
        source_refs: list[dict[str, Any] | str] | None = None,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        normalized_action = str(action or "").strip()
        if normalized_action not in {"correct", "forget", "change_scope", "reduce_confidence", "suppress_recommendation", "boost_proactivity"}:
            raise ValueError("unsupported_memory_correction_action")
        state = self._load_state()
        now = _iso_now()
        located_page_key, target = self._locate_record(state, target_record_id=target_record_id, page_key=page_key)
        effective_page_key = str(page_key or located_page_key or "preferences")
        source_refs_list = list(source_refs or [])
        correction_note = _compact_text(note, limit=500)
        correction_summary = _compact_text(corrected_summary, limit=800)

        if normalized_action == "forget":
            if not target or not located_page_key:
                raise ValueError("memory_record_not_found")
            target.setdefault("metadata", {}).setdefault("correction_history", []).append(
                {"action": "forget", "note": correction_note, "timestamp": now}
            )
            target.setdefault("metadata", {})["do_not_infer_again_easily"] = True
            target["status"] = "superseded"
            target["superseded_at"] = now
            state["updated_at"] = now
            self._save_state(state)
            self._render_all(state)
            self._append_log("memory_correction", "Memory record forgotten", {"record_id": target.get("id"), "page": located_page_key})
            return {
                "action": normalized_action,
                "page_key": located_page_key,
                "record_id": target.get("id"),
                "status": "forgotten",
            }

        if normalized_action == "change_scope":
            if not target or not located_page_key:
                raise ValueError("memory_record_not_found")
            next_scope = str(scope or "").strip()
            if not next_scope:
                raise ValueError("scope_required")
            target.setdefault("metadata", {}).setdefault("correction_history", []).append(
                {"action": "change_scope", "from": target.get("metadata", {}).get("scope"), "to": next_scope, "timestamp": now}
            )
            target["status"] = "superseded"
            target["superseded_at"] = now
            new_record = {
                **target,
                "id": f"{target.get('id')}-scope-{_fingerprint([next_scope, now])[:6]}",
                "status": "active",
                "updated_at": now,
                "source_refs": sorted(set([*(target.get("source_refs") or []), *[str(item) for item in source_refs_list]])),
                "metadata": {
                    **dict(target.get("metadata") or {}),
                    "scope": next_scope,
                    "correction_history": list((target.get("metadata") or {}).get("correction_history") or []),
                    "confidence_reduced_after_correction": True,
                },
            }
            self._upsert_page_record(state, located_page_key, new_record)
            state["updated_at"] = now
            self._save_state(state)
            self._render_all(state)
            return {
                "action": normalized_action,
                "page_key": located_page_key,
                "record_id": new_record.get("id"),
                "status": "updated",
                "scope": next_scope,
            }

        if normalized_action == "reduce_confidence":
            if not target or not located_page_key:
                raise ValueError("memory_record_not_found")
            current_confidence = float(target.get("confidence") or 0.7)
            target.setdefault("metadata", {}).setdefault("correction_history", []).append(
                {"action": "reduce_confidence", "note": correction_note, "timestamp": now}
            )
            target.setdefault("metadata", {})["confidence_reduced_after_correction"] = True
            target["confidence"] = round(max(0.15, current_confidence - 0.2), 2)
            target["updated_at"] = now
            state["updated_at"] = now
            self._save_state(state)
            self._render_all(state)
            return {
                "action": normalized_action,
                "page_key": located_page_key,
                "record_id": target.get("id"),
                "status": "updated",
                "confidence": target.get("confidence"),
            }

        if normalized_action == "suppress_recommendation":
            recommendation_key = str(recommendation_kind or topic or "").strip()
            if not recommendation_key:
                raise ValueError("recommendation_kind_required")
            record = self._memory_preference_record(
                page_key="preferences",
                record_key=f"recommendation-suppress:{recommendation_key}",
                title=f"{recommendation_key} öneri tercihi",
                summary=correction_summary or f"{recommendation_key} önerileri şimdilik tekrar sunulmasın.",
                scope=scope or "personal",
                note=correction_note,
                source_refs=source_refs_list,
                metadata={
                    "field": f"recommendation_suppression:{recommendation_key}",
                    "recommendation_kind": recommendation_key,
                    "preference_type": "recommendation_suppression",
                    "source_basis": source_refs_list,
                },
            )
            self._upsert_page_record(state, "preferences", record)
            state["updated_at"] = now
            self._save_state(state)
            self._render_all(state)
            return {"action": normalized_action, "page_key": "preferences", "record_id": record["id"], "status": "updated"}

        if normalized_action == "boost_proactivity":
            topic_key = str(topic or recommendation_kind or "").strip()
            if not topic_key:
                raise ValueError("topic_required")
            record = self._memory_preference_record(
                page_key="preferences",
                record_key=f"proactivity:{topic_key}",
                title=f"{topic_key} proaktiflik tercihi",
                summary=correction_summary or f"{topic_key} konusunda daha proaktif öneri sunulabilir.",
                scope=scope or "personal",
                note=correction_note,
                source_refs=source_refs_list,
                metadata={
                    "field": f"proactivity:{topic_key}",
                    "topic": topic_key,
                    "preference_type": "proactivity_preference",
                    "source_basis": source_refs_list,
                },
            )
            self._upsert_page_record(state, "preferences", record)
            state["updated_at"] = now
            self._save_state(state)
            self._render_all(state)
            return {"action": normalized_action, "page_key": "preferences", "record_id": record["id"], "status": "updated"}

        base_page_key = located_page_key or effective_page_key
        logical_key = str(key or (target or {}).get("key") or (target or {}).get("id") or "").strip()
        if not logical_key:
            raise ValueError("memory_key_required")
        if target:
            target.setdefault("metadata", {}).setdefault("correction_history", []).append(
                {"action": "correct", "note": correction_note, "timestamp": now}
            )
            target.setdefault("metadata", {})["repeated_contradiction_count"] = int(
                target.get("metadata", {}).get("repeated_contradiction_count") or 0
            ) + 1
            target["status"] = "superseded"
            target["superseded_at"] = now
        record = self._memory_preference_record(
            page_key=base_page_key,
            record_key=logical_key,
            title=str((target or {}).get("title") or logical_key),
            summary=correction_summary or str((target or {}).get("summary") or ""),
            scope=scope or str(((target or {}).get("metadata") or {}).get("scope") or self._infer_scope(base_page_key, {}, target or {})),
            note=correction_note,
            source_refs=[*(target.get("source_refs") or [])] if target else source_refs_list,
            metadata={
                **dict((target or {}).get("metadata") or {}),
                "field": str(((target or {}).get("metadata") or {}).get("field") or logical_key),
                "source_basis": source_refs_list,
                "supersedes_record_id": (target or {}).get("id"),
                "confidence_reduced_after_correction": True if target else False,
            },
        )
        self._upsert_page_record(state, base_page_key, record)
        state["updated_at"] = now
        self._save_state(state)
        self._render_all(state)
        return {
            "action": normalized_action,
            "page_key": base_page_key,
            "record_id": record["id"],
            "status": "updated",
            "scope": record.get("metadata", {}).get("scope"),
        }

    def create_decision_record(
        self,
        *,
        title: str,
        summary: str,
        source_refs: list[dict[str, Any]] | list[str] | None,
        reasoning_summary: str,
        confidence: float,
        user_confirmation_required: bool,
        possible_risks: list[str] | None,
        action_kind: str | None,
        intent: str | None = None,
        alternatives: list[str] | None = None,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        safety = self.safety_policy.classify(action_kind)
        now = _iso_now()
        decision_id = f"decision-{_slugify(title)}-{_fingerprint([title, summary, reasoning_summary])[:8]}"
        record = {
            "id": decision_id,
            "title": _compact_text(title, limit=200),
            "summary": _compact_text(summary, limit=800),
            "intent": _compact_text(intent, limit=120) if intent else None,
            "source_refs": list(source_refs or []),
            "reasoning_summary": _compact_text(reasoning_summary, limit=1200),
            "confidence": round(float(confidence), 2),
            "user_confirmation_required": bool(user_confirmation_required),
            "possible_risks": [str(item).strip() for item in list(possible_risks or []) if str(item).strip()],
            "action_kind": action_kind,
            "risk_level": safety.get("level"),
            "policy": safety.get("label"),
            "alternatives": [str(item).strip() for item in list(alternatives or []) if str(item).strip()],
            "created_at": now,
        }
        decision_path = self._decisions_dir() / f"{decision_id}.md"
        self._write_text(decision_path, self._render_decision_markdown(record))

        state = self._load_state()
        records = list(state.get("decision_records") or [])
        existing_ids = {item.get("id") for item in records if isinstance(item, dict)}
        if decision_id not in existing_ids:
            records.append({**record, "path": str(decision_path)})
            state["decision_records"] = records[-200:]
            self._upsert_page_record(
                state,
                "decisions",
                {
                    "id": decision_id,
                    "key": decision_id,
                    "title": record["title"],
                    "summary": record["summary"],
                    "confidence": record["confidence"],
                    "status": "active",
                    "source_refs": [str(decision_path)],
                    "signals": ["decision_record"],
                    "updated_at": now,
                    "metadata": {
                        "risk_level": record["risk_level"],
                        "requires_confirmation": record["user_confirmation_required"],
                    },
                },
            )
            state["updated_at"] = now
            self._save_state(state)
            self._render_all(state)
        self._append_log("decision_record_created", record["title"], {"decision_id": decision_id, "risk_level": record["risk_level"]})
        return {**record, "path": str(decision_path)}

    def record_recommendation_feedback(self, recommendation_id: str, outcome: str, note: str | None = None) -> dict[str, Any]:
        self.ensure_scaffold()
        state = self._load_state()
        history = list(state.get("recommendation_history") or [])
        updated_item = None
        for item in reversed(history):
            if str(item.get("id") or "") != recommendation_id:
                continue
            item["outcome"] = outcome
            item["feedback_note"] = _compact_text(note, limit=500)
            item["feedback_at"] = _iso_now()
            updated_item = item
            break
        if not updated_item:
            raise ValueError("recommendation_not_found")
        state["recommendation_history"] = history
        self._save_state(state)
        self._render_all(state)
        self.ingest(
            source_type="recommendation_feedback",
            content=json.dumps({"recommendation_id": recommendation_id, "outcome": outcome, "note": note}, ensure_ascii=False),
            title=f"Recommendation feedback {recommendation_id}",
            metadata={"recommendation_id": recommendation_id, "outcome": outcome},
            source_ref=f"recommendation:{recommendation_id}",
            tags=["feedback", outcome],
        )
        file_back = None
        if updated_item:
            recommendation_kind = str(updated_item.get("kind") or recommendation_id).strip() or recommendation_id
            matching_history = [
                item
                for item in history
                if str(item.get("kind") or "") == recommendation_kind and str(item.get("outcome") or "") in {"accepted", "rejected", "ignored"}
            ]
            rejection_count = sum(1 for item in matching_history if str(item.get("outcome") or "") == "rejected")
            acceptance_count = sum(1 for item in matching_history if str(item.get("outcome") or "") == "accepted")
            learned_summary = None
            preference_type = None
            if outcome == "accepted":
                learned_summary = f"{recommendation_kind} öneri türü yararlı bulundu; benzer durumlarda daha görünür kalabilir."
                preference_type = "recommendation_feedback_learning"
            elif outcome == "rejected":
                if rejection_count >= 2:
                    learned_summary = f"{recommendation_kind} önerileri tekrar tekrar reddedildi; varsayılan olarak daha seyrek ve daha yumuşak sunulmalı."
                    preference_type = "recommendation_suppression"
                else:
                    learned_summary = f"{recommendation_kind} öneri türü bu bağlamda reddedildi; daha seyrek veya daha yumuşak sunulmalı."
                    preference_type = "recommendation_feedback_learning"
            if learned_summary:
                preference_record = self._memory_preference_record(
                    page_key="preferences",
                    record_key=(
                        f"recommendation-suppress:{recommendation_kind}"
                        if preference_type == "recommendation_suppression"
                        else f"recommendation-learning:{recommendation_kind}"
                    ),
                    title=f"{recommendation_kind or 'recommendation'} feedback öğrenimi",
                    summary=learned_summary,
                    scope="personal",
                    note=_compact_text(note, limit=500),
                    source_refs=[f"recommendation:{recommendation_id}"],
                    metadata={
                        "field": (
                            f"recommendation_suppression:{recommendation_kind}"
                            if preference_type == "recommendation_suppression"
                            else f"recommendation_learning:{recommendation_kind}"
                        ),
                        "recommendation_kind": updated_item.get("kind"),
                        "feedback_outcome": outcome,
                        "preference_type": preference_type,
                        "source_basis": [f"recommendation:{recommendation_id}"],
                        "recency": {"feedback_at": updated_item.get("feedback_at")},
                        "confidence": 0.96 if outcome == "accepted" else 0.88,
                        "acceptance_count": acceptance_count,
                        "rejection_count": rejection_count,
                    },
                    signals=["recommendation_feedback_learning"],
                )
                state = self._load_state()
                self._upsert_page_record(state, "preferences", preference_record)
                state["updated_at"] = _iso_now()
                self._save_state(state)
                self._render_all(state)
            file_back = self.maybe_file_back_response(
                kind="accepted_recommendation" if outcome == "accepted" else "rejected_recommendation" if outcome == "rejected" else "preference_correction",
                title=f"Recommendation feedback: {recommendation_kind}",
                content="\n".join(
                    part
                    for part in [
                        str(updated_item.get("suggestion") or ""),
                        str(updated_item.get("why_this") or ""),
                        str(note or "").strip(),
                    ]
                    if part
                ),
                source_refs=[f"recommendation:{recommendation_id}"],
                metadata={
                    "page_key": "recommendations",
                    "record_type": "recommendation",
                    "scope": "personal",
                    "feedback_outcome": outcome,
                    "recommendation_kind": recommendation_kind,
                },
                scope="personal",
                sensitivity="high",
        )
            self._log_runtime_event(
                "pilot_recommendation_feedback",
                recommendation_id=recommendation_id,
                outcome=outcome,
                recommendation_kind=recommendation_kind,
                has_feedback_note=bool(note),
                file_back_written=bool((file_back or {}).get("should_file_back")),
            )
        return {**updated_item, "file_back": file_back} if updated_item else updated_item

    def _assistant_message_reaction_messages(
        self,
        *,
        store: Any,
        limit: int = 2000,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        feedback_messages = [dict(item) for item in list(store.list_assistant_feedback_messages(self.office_id, limit=limit) or [])]
        star_messages = [
            dict(item)
            for item in list(store.list_starred_assistant_messages(self.office_id, limit=limit) or [])
            if str(item.get("feedback_value") or "").strip().lower() not in {"liked", "disliked"}
        ]
        reaction_messages: list[dict[str, Any]] = []
        for message in feedback_messages:
            reaction_messages.append(
                {
                    **message,
                    "_reaction_kind": "feedback",
                    "_reaction_feedback_value": str(message.get("feedback_value") or "").strip().lower(),
                    "_reaction_note": _compact_text(message.get("feedback_note"), limit=500) or None,
                    "_reaction_rank": str(message.get("feedback_at") or message.get("created_at") or message.get("id") or ""),
                }
            )
        for message in star_messages:
            reaction_messages.append(
                {
                    **message,
                    "_reaction_kind": "star",
                    "_reaction_feedback_value": "liked",
                    "_reaction_note": None,
                    "_reaction_rank": str(message.get("starred_at") or message.get("created_at") or message.get("id") or ""),
                }
            )
        reaction_messages.sort(key=lambda item: str(item.get("_reaction_rank") or ""))
        return feedback_messages, reaction_messages

    def _build_assistant_message_reaction_learning(
        self,
        *,
        store: Any,
        message: dict[str, Any],
        feedback_value: str,
        note: str | None,
        signal_kind: str,
    ) -> dict[str, Any]:
        signal_profile = self._assistant_message_feedback_signal_profile(
            message,
            feedback_value=feedback_value,
            note=note,
        )
        semantic_learning = self._derive_assistant_message_feedback_semantic_learning(
            store=store,
            message=message,
            feedback_value=feedback_value,
            note=note,
            signal_profile=signal_profile,
            signal_kind=signal_kind,
        )
        preference_records = self._build_assistant_message_feedback_records(
            message=message,
            feedback_value=feedback_value,
            note=note,
            signal_profile=signal_profile,
            signal_kind=signal_kind,
        )
        preference_records.extend(list(semantic_learning.get("records") or []))
        return {
            "signal_profile": signal_profile,
            "semantic_learning": semantic_learning,
            "preference_records": preference_records,
        }

    def record_assistant_message_feedback(
        self,
        *,
        store: Any,
        message_id: int,
        feedback_value: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        normalized_feedback = str(feedback_value or "").strip().lower()
        if normalized_feedback not in {"liked", "disliked"}:
            raise ValueError("invalid_feedback_value")
        message = store.get_assistant_message(self.office_id, message_id=message_id)
        if not message:
            raise ValueError("assistant_thread_message_not_found")
        if str(message.get("role") or "") != "assistant":
            raise ValueError("assistant_feedback_requires_assistant_message")

        note_text = _compact_text(note, limit=500) or None
        learning_bundle = self._build_assistant_message_reaction_learning(
            store=store,
            message=message,
            feedback_value=normalized_feedback,
            note=note_text,
            signal_kind="feedback",
        )
        signal_profile = learning_bundle["signal_profile"]
        semantic_learning = learning_bundle["semantic_learning"]
        runtime_learning = self._apply_assistant_feedback_to_runtime_profile(
            store=store,
            message=message,
            feedback_value=normalized_feedback,
            note=note_text,
            signal_profile=signal_profile,
        )

        raw_source_ref = f"assistant-message:{message_id}"
        self.ingest(
            source_type="assistant_message_feedback",
            content=json.dumps(
                {
                    "message_id": message_id,
                    "feedback_value": normalized_feedback,
                    "note": note_text,
                    "signal_label": signal_profile.get("signal_label"),
                    "message_preview": _compact_text(message.get("content"), limit=220),
                    "generated_from": message.get("generated_from"),
                    "signal_profile": signal_profile,
                    "semantic_learning": semantic_learning,
                },
                ensure_ascii=False,
            ),
            title=f"Assistant message feedback {message_id}",
            metadata={
                "message_id": message_id,
                "feedback_value": normalized_feedback,
                "page_key": semantic_learning.get("primary_page_key") or signal_profile.get("target_page_key"),
                "signal_label": signal_profile.get("signal_label"),
                "message_preview": _compact_text(message.get("content"), limit=220),
                "semantic_target": semantic_learning.get("target_contact"),
            },
            source_ref=raw_source_ref,
            tags=["feedback", "assistant_message", normalized_feedback],
        )

        state = self._load_state()
        preference_records = list(learning_bundle.get("preference_records") or [])
        updated_pages: list[str] = []
        updated_record_ids: list[str] = []
        for page_key, record in preference_records:
            result = self._upsert_page_record(state, page_key, record)
            if result.get("updated") is False and not result.get("contradictions"):
                continue
            if page_key not in updated_pages:
                updated_pages.append(page_key)
            updated_record_ids.append(str(record.get("id") or ""))
        if updated_pages:
            state["updated_at"] = _iso_now()
            self._save_state(state)
            self._render_all(state)

        profile_learning = self._apply_assistant_feedback_to_related_profile(
            store=store,
            semantic_learning=semantic_learning,
            note=note_text,
        )
        user_profile_learning = self._apply_assistant_feedback_to_user_profile(
            store=store,
            feedback_value=normalized_feedback,
            signal_profile=signal_profile,
        )
        sync_result = self.sync_from_store(store=store, reason="assistant_message_feedback")
        file_back = self.maybe_file_back_response(
            kind="assistant_message_feedback_learning",
            title=f"Assistant message feedback: {signal_profile.get('signal_label') or message.get('generated_from') or message_id}",
            content="\n".join(
                part
                for part in [
                    f"Geri bildirim: {normalized_feedback}",
                    signal_profile.get("learning_summary"),
                    note_text,
                    _compact_text(message.get("content"), limit=360),
                ]
                if part
            ),
            source_refs=[raw_source_ref],
            metadata={
                "page_key": semantic_learning.get("primary_page_key") or signal_profile.get("target_page_key") or "preferences",
                "record_type": semantic_learning.get("primary_record_type") or "preference",
                "scope": semantic_learning.get("scope") or signal_profile.get("scope") or "personal",
                "feedback_value": normalized_feedback,
                "signal_label": signal_profile.get("signal_label"),
                "semantic_target": semantic_learning.get("target_contact"),
            },
            scope=semantic_learning.get("scope") or signal_profile.get("scope") or "personal",
            sensitivity="high",
        )
        self._log_runtime_event(
            "pilot_assistant_message_feedback",
            message_id=message_id,
            feedback_value=normalized_feedback,
            signal_label=signal_profile.get("signal_label"),
            semantic_target=semantic_learning.get("target_contact"),
            file_back_written=bool((file_back or {}).get("should_file_back")),
        )
        return {
            "message_id": message_id,
            "feedback_value": normalized_feedback,
            "signal_profile": signal_profile,
            "semantic_learning": semantic_learning,
            "updated_pages": updated_pages,
            "updated_record_ids": updated_record_ids,
            "runtime_learning": runtime_learning,
            "user_profile_learning": user_profile_learning,
            "profile_learning": profile_learning,
            "sync": sync_result,
            "file_back": file_back,
        }

    def refresh_assistant_feedback_learning(
        self,
        *,
        store: Any,
        changed_message_id: int | None = None,
    ) -> dict[str, Any]:
        self.ensure_scaffold()
        feedback_messages, reaction_messages = self._assistant_message_reaction_messages(store=store, limit=2000)
        state = self._load_state()
        removed_records = self._strip_assistant_feedback_records(state)

        updated_pages: list[str] = []
        updated_record_ids: list[str] = []
        for message in reaction_messages:
            learning_bundle = self._build_assistant_message_reaction_learning(
                store=store,
                message=message,
                feedback_value=str(message.get("_reaction_feedback_value") or "liked"),
                note=message.get("_reaction_note"),
                signal_kind=str(message.get("_reaction_kind") or "feedback"),
            )
            for page_key, record in list(learning_bundle.get("preference_records") or []):
                result = self._upsert_page_record(state, page_key, record)
                if result.get("updated") is False and not result.get("contradictions"):
                    continue
                if page_key not in updated_pages:
                    updated_pages.append(page_key)
                updated_record_ids.append(str(record.get("id") or ""))

        if removed_records or updated_pages:
            state["updated_at"] = _iso_now()
            self._save_state(state)
            self._render_all(state)

        runtime_learning = self._rebuild_assistant_feedback_runtime_profile(store=store, feedback_messages=feedback_messages)
        user_profile_learning = self._rebuild_assistant_feedback_user_profile(store=store, reaction_messages=reaction_messages)
        profile_learning = self._rebuild_assistant_feedback_related_profiles(store=store, reaction_messages=reaction_messages)
        sync_result = self.sync_from_store(store=store, reason="assistant_message_feedback_refresh")

        current_learning: dict[str, Any] | None = None
        if changed_message_id is not None:
            current_message = store.get_assistant_message(self.office_id, message_id=changed_message_id)
            current_feedback = str((current_message or {}).get("feedback_value") or "").strip().lower()
            if current_message and current_feedback in {"liked", "disliked"}:
                current_note = _compact_text(current_message.get("feedback_note"), limit=500) or None
                learning_bundle = self._build_assistant_message_reaction_learning(
                    store=store,
                    message=current_message,
                    feedback_value=current_feedback,
                    note=current_note,
                    signal_kind="feedback",
                )
                current_learning = {
                    "message_id": changed_message_id,
                    "feedback_value": current_feedback,
                    "signal_profile": learning_bundle["signal_profile"],
                    "semantic_learning": learning_bundle["semantic_learning"],
                    "summary": "Asistan mesajı geri bildirimi kanonik öğrenim durumuna işlendi.",
                }
            elif current_message and bool(current_message.get("starred")):
                learning_bundle = self._build_assistant_message_reaction_learning(
                    store=store,
                    message=current_message,
                    feedback_value="liked",
                    note=None,
                    signal_kind="star",
                )
                current_learning = {
                    "message_id": changed_message_id,
                    "feedback_value": None,
                    "starred": True,
                    "signal_profile": learning_bundle["signal_profile"],
                    "semantic_learning": learning_bundle["semantic_learning"],
                    "summary": "Asistan mesajı yıldız öğrenimi kanonik duruma işlendi.",
                }
            else:
                current_learning = {
                    "message_id": changed_message_id,
                    "feedback_value": None,
                    "starred": False,
                    "cleared": True,
                    "summary": "Asistan mesajı reaksiyon öğrenimi kaldırıldı ve durum temizlendi.",
                }

        return {
            "current_learning": current_learning,
            "feedback_message_count": len(feedback_messages),
            "reaction_message_count": len(reaction_messages),
            "removed_records": removed_records,
            "updated_pages": updated_pages,
            "updated_record_ids": updated_record_ids,
            "runtime_learning": runtime_learning,
            "user_profile_learning": user_profile_learning,
            "profile_learning": profile_learning,
            "sync": sync_result,
        }

    def _assistant_message_feedback_signal_profile(
        self,
        message: dict[str, Any],
        *,
        feedback_value: str,
        note: str | None,
    ) -> dict[str, Any]:
        content = str(message.get("content") or "").strip()
        generated_from = str(message.get("generated_from") or "").strip()
        source_context = dict(message.get("source_context") or {})
        note_text = str(note or "").lower()
        compact_content = content.lower()
        line_count = len([line for line in content.splitlines() if line.strip()])
        bullet_count = len([line for line in content.splitlines() if re.match(r"^\s*(?:[-*•]|\d+\.)", line.strip())])
        content_length = len(content)

        explanation_style = "balanced"
        if content_length >= 420 or line_count >= 5 or bullet_count >= 3:
            explanation_style = "detailed"
        elif content_length <= 170 and line_count <= 2:
            explanation_style = "concise"

        if any(token in note_text for token in ("kısa", "kisa", "özet", "ozet", "uzun olmasin", "uzun olmasın")):
            explanation_style = "concise"
        elif any(token in note_text for token in ("detay", "gerekce", "gerekçe", "daha fazla")):
            explanation_style = "detailed"

        proactive_markers = (
            "trigger",
            "recommendation",
            "daily_plan",
            "smart_reminder",
            "calendar_nudge",
            "follow_up",
            "coaching",
        )
        planning_markers = ("plan", "takvim", "görev", "gorev", "okuma", "hedef", "cadence")
        is_proactive = any(marker in generated_from for marker in proactive_markers) or any(
            key in source_context for key in ("proactive_suggestion", "why_now", "recommendation_context", "trigger")
        )
        is_planning = any(marker in generated_from for marker in ("daily_plan", "calendar_nudge", "coaching")) or any(
            marker in compact_content for marker in planning_markers
        )
        is_automation = bool(message.get("requires_approval")) or bool(message.get("tool_suggestions")) or bool(message.get("draft_preview")) or bool(source_context.get("action_ladder"))
        is_routine = is_proactive and any(marker in compact_content for marker in ("hatırlat", "rut", "okuma", "hedef", "takip"))

        signal_label = "assistant_feedback"
        target_page_key = "preferences"
        learning_summary = "Asistan mesajı için kullanıcı geri bildirimi kaydedildi."
        if is_proactive or is_routine:
            signal_label = "proactivity_and_follow_up"
            target_page_key = "routines"
            learning_summary = (
                "Kullanıcının proaktif takip ve hatırlatma tarzına verdiği sinyal güncellendi."
                if feedback_value == "liked"
                else "Kullanıcının istemediği takip ve hatırlatma yoğunluğu azaltılmalı."
            )
        elif explanation_style in {"concise", "detailed"}:
            signal_label = f"explanation_style_{explanation_style}"
            learning_summary = (
                "Kullanıcının yanıt açıklama tarzı tercihi güçlendi."
                if feedback_value == "liked"
                else "Asistan açıklama yoğunluğunu ters yönde ayarlamalı."
            )
        elif is_planning:
            signal_label = "planning_guidance"
            target_page_key = "routines"
            learning_summary = (
                "Plan ve check-in önerilerinin tonu bu geri bildirimle daha iyi ayarlanmalı."
                if feedback_value == "liked"
                else "Plan önerileri daha hafif ve isteğe bağlı sunulmalı."
            )
        elif is_automation:
            signal_label = "automation_preview"
            target_page_key = "recommendations"
            learning_summary = (
                "Düşük riskli önizleme akışları kullanıcının beklentisine göre rafine edilmeli."
                if feedback_value == "liked"
                else "Aksiyon hazırlığı daha sakin ve daha kısa önizlemelerle sunulmalı."
            )

        return {
            "scope": str(((source_context.get("knowledge_context") or {}).get("scope")) or "personal"),
            "explanation_style": explanation_style,
            "is_proactive": is_proactive,
            "is_planning": is_planning,
            "is_automation": is_automation,
            "is_routine": is_routine,
            "signal_label": signal_label,
            "target_page_key": target_page_key,
            "learning_summary": learning_summary,
        }

    def _build_assistant_message_feedback_records(
        self,
        *,
        message: dict[str, Any],
        feedback_value: str,
        note: str | None,
        signal_profile: dict[str, Any],
        signal_kind: str = "feedback",
    ) -> list[tuple[str, dict[str, Any]]]:
        message_id = int(message.get("id") or 0)
        generated_from = str(message.get("generated_from") or "assistant_thread_message").strip() or "assistant_thread_message"
        scope = str(signal_profile.get("scope") or "personal")
        source_ref = f"assistant-message:{message_id}"
        note_text = _compact_text(note, limit=500)
        signal_tag = "assistant_message_star" if signal_kind == "star" else "assistant_message_feedback"
        records: list[tuple[str, dict[str, Any]]] = []

        explanation_style = str(signal_profile.get("explanation_style") or "balanced")
        if explanation_style in {"concise", "detailed"}:
            preferred_style = explanation_style if feedback_value == "liked" else ("concise" if explanation_style == "detailed" else "detailed")
            records.append(
                (
                    "preferences",
                    self._memory_preference_record(
                        page_key="preferences",
                        record_key="assistant_explanation_style_preference",
                        title="Asistan açıklama tarzı tercihi",
                        summary=(
                            f"Kullanıcı {preferred_style} açıklama tarzına daha olumlu sinyal veriyor."
                            if feedback_value == "liked"
                            else f"Kullanıcı {explanation_style} açıklama tarzını bu bağlamda olumsuz değerlendirdi; {preferred_style} tercih edilmeli."
                        ),
                        scope=scope,
                        note=note_text,
                        source_refs=[source_ref],
                        metadata={
                            "field": "assistant_explanation_style_preference",
                            "record_type": "conversation_style",
                            "source_basis": [source_ref],
                            "feedback_value": feedback_value,
                            "preferred_style": preferred_style,
                            "confidence": 0.72 if signal_kind == "star" else 0.84,
                            "generated_from": generated_from,
                            "signal_kind": signal_kind,
                        },
                        signals=[signal_tag],
                    ),
                )
            )

        if signal_profile.get("is_proactive") or signal_profile.get("is_routine"):
            preferred_level = "high" if feedback_value == "liked" else "low"
            records.append(
                (
                    "routines",
                    self._memory_preference_record(
                        page_key="routines",
                        record_key="assistant_follow_up_preference",
                        title="Takip ve hatırlatma tercihleri",
                        summary=(
                            "Kullanıcı proaktif takip ve check-in akışlarına olumlu tepki veriyor."
                            if feedback_value == "liked"
                            else "Kullanıcı sık takip ve hatırlatma akışlarını daha düşük yoğunlukta istiyor."
                        ),
                        scope=scope,
                        note=note_text,
                        source_refs=[source_ref],
                        metadata={
                            "field": "assistant_follow_up_preference",
                            "record_type": "routine",
                            "source_basis": [source_ref],
                            "feedback_value": feedback_value,
                            "preferred_level": preferred_level,
                            "confidence": 0.76 if signal_kind == "star" else 0.88,
                            "generated_from": generated_from,
                            "signal_kind": signal_kind,
                        },
                        signals=[signal_tag],
                    ),
                )
            )

        if signal_profile.get("is_planning"):
            preferred_depth = "deep" if feedback_value == "liked" else "light"
            records.append(
                (
                    "preferences",
                    self._memory_preference_record(
                        page_key="preferences",
                        record_key="assistant_planning_style_preference",
                        title="Planlama derinliği tercihi",
                        summary=(
                            "Kullanıcı daha yapılandırılmış ve detaylı plan desteğine olumlu tepki veriyor."
                            if feedback_value == "liked"
                            else "Kullanıcı plan önerilerinin daha hafif ve özet olmasını tercih ediyor."
                        ),
                        scope=scope,
                        note=note_text,
                        source_refs=[source_ref],
                        metadata={
                            "field": "assistant_planning_style_preference",
                            "record_type": "preference",
                            "source_basis": [source_ref],
                            "feedback_value": feedback_value,
                            "preferred_depth": preferred_depth,
                            "confidence": 0.7 if signal_kind == "star" else 0.82,
                            "generated_from": generated_from,
                            "signal_kind": signal_kind,
                        },
                        signals=[signal_tag],
                    ),
                )
            )
        return records

    def _apply_assistant_feedback_to_runtime_profile(
        self,
        *,
        store: Any,
        message: dict[str, Any],
        feedback_value: str,
        note: str | None,
        signal_profile: dict[str, Any],
    ) -> dict[str, Any]:
        runtime_profile = store.get_assistant_runtime_profile(self.office_id) or {}
        current_contract = normalize_behavior_contract(runtime_profile.get("behavior_contract"))
        next_contract, changed_fields = self._apply_assistant_feedback_contract_patch(
            current_contract=current_contract,
            feedback_value=feedback_value,
            note=note,
            signal_profile=signal_profile,
        )
        if next_contract == current_contract:
            return {
                "updated": False,
                "behavior_contract": current_contract,
                "changed_fields": [],
                "summary": "Davranış kontratında yeni bir değişiklik gerekmedi.",
            }

        history = [dict(item) for item in list(runtime_profile.get("evolution_history") or [])]
        history.append(
            {
                "id": f"assistant-message-feedback-{message.get('id')}-{feedback_value}",
                "kind": "assistant_message_feedback_learning",
                "summary": (
                    f"Assistant message feedback → {', '.join(dict.fromkeys(changed_fields)) or 'behavior_contract'} güncellendi."
                ),
                "source_text": _compact_text(message.get("content"), limit=220),
                "feedback_value": feedback_value,
                "generated_from": message.get("generated_from"),
                "created_at": _iso_now(),
            }
        )
        history = history[-40:]
        saved = store.upsert_assistant_runtime_profile(
            self.office_id,
            assistant_name=runtime_profile.get("assistant_name"),
            role_summary=runtime_profile.get("role_summary"),
            tone=runtime_profile.get("tone"),
            avatar_path=runtime_profile.get("avatar_path"),
            soul_notes=runtime_profile.get("soul_notes"),
            tools_notes=runtime_profile.get("tools_notes"),
            assistant_forms=runtime_profile.get("assistant_forms") or [],
            behavior_contract=next_contract,
            evolution_history=history,
            heartbeat_extra_checks=runtime_profile.get("heartbeat_extra_checks") or [],
        )
        return {
            "updated": True,
            "behavior_contract": saved.get("behavior_contract") or next_contract,
            "changed_fields": list(dict.fromkeys(changed_fields)),
            "summary": "Asistan davranış kontratı geri bildirim sinyaline göre rafine edildi.",
        }

    def _apply_assistant_feedback_contract_patch(
        self,
        *,
        current_contract: dict[str, Any],
        feedback_value: str,
        note: str | None,
        signal_profile: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        next_contract = dict(current_contract)
        note_text = str(note or "").lower()
        changed_fields: list[str] = []
        explanation_style = str(signal_profile.get("explanation_style") or "balanced")

        if feedback_value == "liked":
            if explanation_style in {"concise", "detailed"} and next_contract.get("explanation_style") != explanation_style:
                next_contract["explanation_style"] = explanation_style
                changed_fields.append("explanation_style")
            if signal_profile.get("is_planning") and next_contract.get("planning_depth") != "deep":
                next_contract["planning_depth"] = "deep"
                changed_fields.append("planning_depth")
            if signal_profile.get("is_proactive") and next_contract.get("initiative_level") != "high":
                next_contract["initiative_level"] = "high"
                changed_fields.append("initiative_level")
                if signal_profile.get("is_routine"):
                    next_contract["follow_up_style"] = "persistent"
                    changed_fields.append("follow_up_style")
        else:
            if explanation_style == "detailed" or any(token in note_text for token in ("kısa", "kisa", "özet", "ozet")):
                if next_contract.get("explanation_style") != "concise":
                    next_contract["explanation_style"] = "concise"
                    changed_fields.append("explanation_style")
            elif explanation_style == "concise" and any(token in note_text for token in ("detay", "gerekce", "gerekçe")):
                if next_contract.get("explanation_style") != "detailed":
                    next_contract["explanation_style"] = "detailed"
                    changed_fields.append("explanation_style")
            if signal_profile.get("is_proactive") or any(token in note_text for token in ("çok sık", "cok sik", "fazla", "daha az")):
                if next_contract.get("initiative_level") != "low":
                    next_contract["initiative_level"] = "low"
                    changed_fields.append("initiative_level")
                if next_contract.get("follow_up_style") != "on_request":
                    next_contract["follow_up_style"] = "on_request"
                    changed_fields.append("follow_up_style")
            if signal_profile.get("is_planning") and next_contract.get("planning_depth") != "light":
                next_contract["planning_depth"] = "light"
                changed_fields.append("planning_depth")

        return normalize_behavior_contract(next_contract), list(dict.fromkeys(changed_fields))

    def _derive_assistant_message_feedback_semantic_learning(
        self,
        *,
        store: Any,
        message: dict[str, Any],
        feedback_value: str,
        note: str | None,
        signal_profile: dict[str, Any],
        signal_kind: str = "feedback",
    ) -> dict[str, Any]:
        note_text = _compact_text(note, limit=500)
        profile = store.get_user_profile(self.office_id) or {}
        target_contact = self._resolve_assistant_feedback_contact_target(profile=profile, message=message, note=note_text or "")
        if not target_contact:
            return {
                "target_contact": None,
                "records": [],
                "signals": [],
                "scope": str(signal_profile.get("scope") or "personal"),
                "primary_page_key": None,
                "primary_record_type": None,
                "summary": (
                    "Açıklama veya mesaj bağlamından güvenilir bir kişi hedefi çıkarılamadı."
                    if signal_kind == "feedback"
                    else "Yıldızlanan mesajdan güvenilir bir kişi hedefi çıkarılamadı."
                ),
            }

        signal_entries = self._extract_assistant_feedback_contact_signals(
            message=message,
            feedback_value=feedback_value,
            note=note_text or "",
            target_contact=target_contact,
            scope=str(signal_profile.get("scope") or "personal"),
            signal_kind=signal_kind,
        )
        records: list[tuple[str, dict[str, Any]]] = []
        signal_tag = "assistant_message_star" if signal_kind == "star" else "assistant_message_feedback"
        for entry in signal_entries:
            page_key = str(entry.get("page_key") or "contacts")
            record_key = str(entry.get("record_key") or f"contact-learning:{target_contact.get('profile_id')}")
            metadata = {
                "field": entry.get("field"),
                "record_type": entry.get("record_type") or "preference",
                "source_basis": [f"assistant-message:{message.get('id')}"],
                "feedback_value": feedback_value,
                "confidence": entry.get("confidence") or 0.72,
                "contact_id": target_contact.get("profile_id"),
                "contact_name": target_contact.get("name"),
                "relationship": target_contact.get("relationship"),
                "semantic_reason": entry.get("semantic_reason"),
                "topic_key": entry.get("topic_key"),
                "stance": entry.get("stance"),
                "signal_kind": signal_kind,
                "relations": [
                    {"relation_type": "relevant_to", "target": f"contact:{target_contact.get('profile_id')}"},
                    {"relation_type": "inferred_from", "target": f"assistant-message:{message.get('id')}"},
                ],
            }
            records.append(
                (
                    page_key,
                    self._memory_preference_record(
                        page_key=page_key,
                        record_key=record_key,
                        title=str(entry.get("title") or "Kişi öğrenimi"),
                        summary=str(entry.get("summary") or ""),
                        scope=str(signal_profile.get("scope") or "personal"),
                        note=note_text,
                        source_refs=[f"assistant-message:{message.get('id')}"],
                        metadata=metadata,
                        signals=[signal_tag],
                    ),
                )
            )

        return {
            "target_contact": target_contact,
            "records": records,
            "signals": signal_entries,
            "scope": str(signal_profile.get("scope") or "personal"),
            "primary_page_key": str(signal_entries[0].get("page_key") or "contacts") if signal_entries else None,
            "primary_record_type": str(signal_entries[0].get("record_type") or "preference") if signal_entries else None,
            "summary": (
                f"{target_contact.get('name')} için {len(signal_entries)} semantik öğrenim sinyali çıkarıldı."
                if signal_entries
                else (
                    f"{target_contact.get('name')} için yıldızdan güvenilir semantik öğrenim çıkmadı."
                    if signal_kind == "star"
                    else f"{target_contact.get('name')} için güvenilir semantik öğrenim çıkmadı."
                )
            ),
        }

    def _resolve_assistant_feedback_contact_target(
        self,
        *,
        profile: dict[str, Any],
        message: dict[str, Any],
        note: str,
    ) -> dict[str, Any] | None:
        normalized_text_parts = [
            _semantic_normalize_text(note),
            _semantic_normalize_text(message.get("content")),
        ]
        source_context = dict(message.get("source_context") or {})
        linked_entities = list(message.get("linked_entities") or [])
        context_candidates = [
            source_context.get("recipient"),
            source_context.get("to_contact"),
            (source_context.get("draft_preview") or {}).get("to_contact") if isinstance(source_context.get("draft_preview"), dict) else None,
        ]
        for entity in linked_entities:
            if not isinstance(entity, dict):
                continue
            context_candidates.append(entity.get("label"))
            context_candidates.append(entity.get("id"))
        normalized_text_parts.extend(_semantic_normalize_text(item) for item in context_candidates if str(item or "").strip())
        combined_text = " ".join(part for part in normalized_text_parts if part)
        if not combined_text:
            return None

        best_match: dict[str, Any] | None = None
        best_score = 0.0
        for item in list(profile.get("related_profiles") or []):
            if not isinstance(item, dict):
                continue
            aliases = {
                _semantic_normalize_text(item.get("id")),
                _semantic_normalize_text(item.get("name")),
                _semantic_normalize_text(item.get("relationship")),
            }
            aliases = {alias for alias in aliases if alias}
            score = 0.0
            for alias in aliases:
                if alias and alias in combined_text:
                    score = max(score, 0.74 if alias == _semantic_normalize_text(item.get("name")) else 0.7)
            if score > best_score:
                best_score = score
                best_match = {
                    "profile_id": str(item.get("id") or _slugify(str(item.get("name") or item.get("relationship") or "contact"))),
                    "name": str(item.get("name") or item.get("relationship") or "Kişi"),
                    "relationship": str(item.get("relationship") or ""),
                    "match_reason": "existing_related_profile",
                    "confidence": round(score, 2),
                }

        if best_match is not None:
            return best_match

        for relation_key, relation_meta in FEEDBACK_RELATIONSHIP_HINTS.items():
            aliases = [
                _semantic_normalize_text(alias)
                for alias in list(relation_meta.get("aliases") or [])
                if _semantic_normalize_text(alias)
            ]
            if any(alias in combined_text for alias in aliases):
                return {
                    "profile_id": str(relation_meta.get("id") or relation_key),
                    "name": str(relation_meta.get("name") or _humanize_identifier(relation_key)),
                    "relationship": str(relation_meta.get("relationship") or relation_key),
                    "match_reason": "relationship_hint",
                    "confidence": 0.72,
                }

        for candidate in context_candidates:
            label = str(candidate or "").strip()
            normalized_label = _semantic_normalize_text(label)
            if not normalized_label or "@" in normalized_label or len(normalized_label) < 3:
                continue
            return {
                "profile_id": _slugify(normalized_label),
                "name": _compact_text(label, limit=120),
                "relationship": "",
                "match_reason": "message_context_recipient",
                "confidence": 0.6,
            }
        return None

    def _extract_assistant_feedback_contact_signals(
        self,
        *,
        message: dict[str, Any],
        feedback_value: str,
        note: str,
        target_contact: dict[str, Any],
        scope: str,
        signal_kind: str = "feedback",
    ) -> list[dict[str, Any]]:
        normalized_note = _semantic_normalize_text(note)
        normalized_content = _semantic_normalize_text(message.get("content"))
        entries: list[dict[str, Any]] = []
        source_ref = f"assistant-message:{message.get('id')}"
        contact_name = str(target_contact.get("name") or "Bu kişi")
        style_labels = self._extract_assistant_feedback_style_labels(note=normalized_note, content=normalized_content, signal_kind=signal_kind)
        if style_labels:
            stance = "avoids" if feedback_value == "disliked" else "prefers"
            style_copy = ", ".join(style_labels)
            summary = (
                f"{contact_name} ile iletişimde {style_copy} ton olumlu karşılanıyor."
                if stance == "prefers"
                else f"{contact_name} ile iletişimde {style_copy} ton olumsuz sinyal aldı; farklı bir üslup seçilmeli."
            )
            entries.append(
                {
                    "page_key": "contacts",
                    "record_key": f"contact-style:{target_contact.get('profile_id')}",
                    "title": f"{contact_name} için iletişim tonu",
                    "summary": summary,
                    "record_type": "conversation_style",
                    "field": "contact_communication_style",
                    "topic_key": "communication_style",
                    "stance": stance,
                    "confidence": 0.67 if signal_kind == "star" else 0.79 if any(token in normalized_note for token in FEEDBACK_STYLE_CONTEXT_HINTS) else 0.74,
                    "semantic_reason": f"{signal_kind} + {source_ref}",
                    "profile_prefix": "İletişim",
                    "profile_statement": f"İletişim: {summary}",
                    "style_labels": list(style_labels),
                }
            )

        item_entries = self._extract_assistant_feedback_item_labels(
            note=normalized_note,
            content=normalized_content,
            feedback_value=feedback_value,
            signal_kind=signal_kind,
        )
        for item_key, item_label, stance, confidence in item_entries:
            entries.append(
                {
                    "page_key": "contacts",
                    "record_key": f"contact-gift:{target_contact.get('profile_id')}:{item_key}",
                    "title": f"{contact_name} için öneri sinyali",
                    "summary": (
                        f"{contact_name} için {item_label} önerileri olumlu karşılanıyor."
                        if stance == "prefers"
                        else f"{contact_name} için {item_label} önerilerinden kaçınılmalı."
                    ),
                    "record_type": "preference",
                    "field": "contact_item_preference",
                    "topic_key": f"gift:{item_key}",
                    "stance": stance,
                    "confidence": confidence,
                    "semantic_reason": f"{signal_kind} + {source_ref}",
                    "profile_prefix": f"Hediye: {item_label}",
                    "profile_statement": (
                        f"Hediye: {item_label} önerileri olumlu karşılanıyor."
                        if stance == "prefers"
                        else f"Hediye: {item_label} önerilerinden kaçınılmalı."
                    ),
                    "item_key": item_key,
                    "item_label": item_label,
                }
            )
        return entries

    def _extract_assistant_feedback_style_labels(self, *, note: str, content: str, signal_kind: str = "feedback") -> list[str]:
        labels: list[str] = []
        for style_key, aliases in FEEDBACK_STYLE_SIGNAL_MAP.items():
            if any(alias in note for alias in aliases):
                labels.append(self._style_label(style_key))
        if labels:
            return list(dict.fromkeys(labels))
        if any(token in note for token in FEEDBACK_STYLE_CONTEXT_HINTS) or signal_kind == "star" or not note:
            labels.extend(self._infer_style_labels_from_message_content(content))
        return list(dict.fromkeys(labels))

    def _extract_assistant_feedback_item_labels(
        self,
        *,
        note: str,
        content: str,
        feedback_value: str,
        signal_kind: str = "feedback",
    ) -> list[tuple[str, str, str, float]]:
        item_matches: list[tuple[str, str, str, float]] = []
        generic_gift_context = any(token in note for token in FEEDBACK_GIFT_CONTEXT_HINTS)
        note_has_explicit_item = any(
            alias in note
            for aliases in FEEDBACK_ITEM_SIGNAL_MAP.values()
            for alias in aliases
        )
        search_spaces = [note]
        if generic_gift_context and not note_has_explicit_item:
            search_spaces.append(content)
        if signal_kind == "star" or not note:
            search_spaces.append(content)
        for item_key, aliases in FEEDBACK_ITEM_SIGNAL_MAP.items():
            matched = any(alias in text for text in search_spaces for alias in aliases)
            if not matched:
                continue
            stance = "avoids" if feedback_value == "disliked" or any(neg in note for neg in FEEDBACK_NEGATION_HINTS) else "prefers"
            item_matches.append((item_key, self._item_label(item_key), stance, 0.62 if signal_kind == "star" else 0.77 if note else 0.68))
        return item_matches

    def _infer_style_labels_from_message_content(self, content: str) -> list[str]:
        labels: list[str] = []
        if any(token in content for token in ("canim", "canım", "sevgi", "sariliyorum", "sarılıyorum", "guzel", "güzel", "sicak", "sıcak")):
            labels.append("sıcak")
        if any(token in content for token in ("rica", "tesekkur", "teşekkür", "lutfen", "lütfen")):
            labels.append("nazik")
        if any(token in content for token in ("sayin", "sayın", "bilginize", "arz ederim")):
            labels.append("resmi")
        if len(content) <= 220:
            labels.append("kısa")
        if len(content) >= 420:
            labels.append("detaylı")
        return list(dict.fromkeys(labels))

    @staticmethod
    def _style_label(style_key: str) -> str:
        mapping = {
            "warm": "sıcak",
            "polite": "nazik",
            "formal": "resmi",
            "concise": "kısa",
            "detailed": "detaylı",
        }
        return mapping.get(style_key, _humanize_identifier(style_key).lower())

    @staticmethod
    def _item_label(item_key: str) -> str:
        mapping = {
            "cikolata": "çikolata",
            "cicek": "çiçek",
            "kitap": "kitap",
            "kahve": "kahve",
            "tatli": "tatlı",
            "yemek": "yemek",
        }
        return mapping.get(item_key, _humanize_identifier(item_key).lower())

    def _apply_assistant_feedback_to_related_profile(
        self,
        *,
        store: Any,
        semantic_learning: dict[str, Any],
        note: str | None,
    ) -> dict[str, Any]:
        target_contact = semantic_learning.get("target_contact") if isinstance(semantic_learning, dict) else None
        signal_entries = list(semantic_learning.get("signals") or []) if isinstance(semantic_learning, dict) else []
        if not isinstance(target_contact, dict) or not signal_entries:
            return {"updated": False, "summary": "İlişki profiline yazılacak yeni bir sinyal üretilmedi."}

        profile = store.get_user_profile(self.office_id) or {}
        related_profiles = [dict(item) for item in list(profile.get("related_profiles") or []) if isinstance(item, dict)]
        target_id = str(target_contact.get("profile_id") or "").strip()
        target_name = str(target_contact.get("name") or "Kişi").strip() or "Kişi"
        target_relationship = str(target_contact.get("relationship") or "").strip()
        target_index = -1
        for index, item in enumerate(related_profiles):
            if target_id and str(item.get("id") or "").strip() == target_id:
                target_index = index
                break
            if target_name and _semantic_normalize_text(item.get("name")) == _semantic_normalize_text(target_name):
                target_index = index
                break
        if target_index < 0:
            return {
                "updated": False,
                "summary": "Beğeni öğrenimi yalnız manuel eklenen yakın kişi profillerine yazılır.",
            }

        target_profile = dict(related_profiles[target_index])
        existing_preferences = str(target_profile.get("preferences") or "")
        next_preferences = existing_preferences
        for entry in signal_entries:
            statement = str(entry.get("profile_statement") or "").strip()
            prefix = str(entry.get("profile_prefix") or "").strip()
            if not statement or not prefix:
                continue
            next_preferences = self._merge_related_profile_learning_statement(next_preferences, prefix=prefix, statement=statement)
        note_summary = _compact_text(note, limit=240)
        if note_summary:
            existing_notes = str(target_profile.get("notes") or "")
            semantic_note = f"Assistant feedback öğrenimi: {note_summary}"
            if semantic_note not in existing_notes:
                target_profile["notes"] = "\n".join(part for part in [existing_notes.strip(), semantic_note] if part).strip()
        target_profile["preferences"] = next_preferences
        target_profile.setdefault("id", target_id or _slugify(target_name))
        target_profile.setdefault("name", target_name)
        target_profile.setdefault("relationship", target_relationship)
        target_profile.setdefault("closeness", self._related_profile_closeness(str(target_profile.get("relationship") or target_relationship)))
        target_profile.setdefault("important_dates", [])
        related_profiles[target_index] = target_profile

        saved_profile = self._persist_user_profile_snapshot(store=store, profile={**profile, "related_profiles": related_profiles})
        return {
            "updated": True,
            "target_profile": target_profile,
            "related_profiles": saved_profile.get("related_profiles") or related_profiles,
            "summary": f"{target_name} profiline beğeni açıklamasından öğrenim yazıldı.",
        }

    def _apply_assistant_feedback_to_user_profile(
        self,
        *,
        store: Any,
        feedback_value: str,
        signal_profile: dict[str, Any],
    ) -> dict[str, Any]:
        profile = store.get_user_profile(self.office_id) or {}
        next_notes = str(profile.get("assistant_notes") or "")
        for prefix, statement in self._assistant_feedback_user_profile_lines(
            feedback_value=feedback_value,
            signal_profile=signal_profile,
        ):
            next_notes = self._merge_related_profile_learning_statement(next_notes, prefix=prefix, statement=statement)
        next_notes = next_notes.strip()
        if next_notes == str(profile.get("assistant_notes") or "").strip():
            return {
                "updated": False,
                "assistant_notes": profile.get("assistant_notes") or "",
                "summary": "Kullanıcı profiline yazılacak yeni bir reaksiyon sinyali üretilmedi.",
            }
        saved_profile = self._persist_user_profile_snapshot(store=store, profile={**profile, "assistant_notes": next_notes})
        return {
            "updated": True,
            "assistant_notes": saved_profile.get("assistant_notes") or next_notes,
            "summary": "Kullanıcı profiline reaksiyon öğrenimi yazıldı.",
        }

    def _strip_assistant_feedback_records(self, state: dict[str, Any]) -> int:
        removed = 0
        for page in (state.get("pages") or {}).values():
            if not isinstance(page, dict):
                continue
            records = [dict(item) for item in list(page.get("records") or []) if isinstance(item, dict)]
            next_records: list[dict[str, Any]] = []
            for record in records:
                signals = {str(item).strip() for item in list(record.get("signals") or []) if str(item).strip()}
                if "assistant_message_feedback" in signals or "assistant_message_star" in signals:
                    removed += 1
                    continue
                next_records.append(record)
            page["records"] = next_records
        return removed

    def _rebuild_assistant_feedback_user_profile(
        self,
        *,
        store: Any,
        reaction_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        profile = store.get_user_profile(self.office_id) or {}
        original_notes = str(profile.get("assistant_notes") or "")
        next_notes = self._strip_feedback_derived_user_profile_notes(original_notes)

        for message in reaction_messages:
            feedback_value = str(message.get("_reaction_feedback_value") or "").strip().lower()
            if feedback_value not in {"liked", "disliked"}:
                continue
            signal_profile = self._assistant_message_feedback_signal_profile(
                message,
                feedback_value=feedback_value,
                note=message.get("_reaction_note"),
            )
            for prefix, statement in self._assistant_feedback_user_profile_lines(
                feedback_value=feedback_value,
                signal_profile=signal_profile,
            ):
                next_notes = self._merge_related_profile_learning_statement(next_notes, prefix=prefix, statement=statement)

        next_notes = next_notes.strip()
        if next_notes == original_notes.strip():
            return {
                "updated": False,
                "assistant_notes": original_notes,
                "summary": "Kullanıcı profil notları mevcut reaksiyonlarla zaten uyumlu.",
            }

        saved_profile = self._persist_user_profile_snapshot(store=store, profile={**profile, "assistant_notes": next_notes})
        return {
            "updated": True,
            "assistant_notes": saved_profile.get("assistant_notes") or next_notes,
            "summary": "Kullanıcı profil notları aktif reaksiyonlardan yeniden kuruldu.",
        }

    def _rebuild_assistant_feedback_runtime_profile(
        self,
        *,
        store: Any,
        feedback_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        runtime_profile = store.get_assistant_runtime_profile(self.office_id) or {}
        current_contract = normalize_behavior_contract(runtime_profile.get("behavior_contract"))
        base_contract = {
            key: value
            for key, value in current_contract.items()
            if key not in FEEDBACK_DERIVED_BEHAVIOR_FIELDS
        }
        next_contract = dict(base_contract)
        changed_fields: list[str] = []

        for message in feedback_messages:
            feedback_value = str(message.get("feedback_value") or "").strip().lower()
            if feedback_value not in {"liked", "disliked"}:
                continue
            signal_profile = self._assistant_message_feedback_signal_profile(
                message,
                feedback_value=feedback_value,
                note=message.get("feedback_note"),
            )
            next_contract, patch_changed_fields = self._apply_assistant_feedback_contract_patch(
                current_contract=next_contract,
                feedback_value=feedback_value,
                note=message.get("feedback_note"),
                signal_profile=signal_profile,
            )
            changed_fields.extend(patch_changed_fields)

        if next_contract == current_contract:
            return {
                "updated": False,
                "behavior_contract": current_contract,
                "changed_fields": [],
                "summary": "Davranış kontratı mevcut geri bildirimlerle zaten uyumlu.",
            }

        saved = store.upsert_assistant_runtime_profile(
            self.office_id,
            assistant_name=runtime_profile.get("assistant_name"),
            role_summary=runtime_profile.get("role_summary"),
            tone=runtime_profile.get("tone"),
            avatar_path=runtime_profile.get("avatar_path"),
            soul_notes=runtime_profile.get("soul_notes"),
            tools_notes=runtime_profile.get("tools_notes"),
            assistant_forms=runtime_profile.get("assistant_forms") or [],
            behavior_contract=next_contract,
            evolution_history=runtime_profile.get("evolution_history") or [],
            heartbeat_extra_checks=runtime_profile.get("heartbeat_extra_checks") or [],
        )
        return {
            "updated": True,
            "behavior_contract": saved.get("behavior_contract") or next_contract,
            "changed_fields": list(dict.fromkeys(changed_fields)),
            "summary": "Asistan davranış kontratı aktif geri bildirimlerden yeniden kuruldu.",
        }

    def _rebuild_assistant_feedback_related_profiles(
        self,
        *,
        store: Any,
        reaction_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        profile = store.get_user_profile(self.office_id) or {}
        original_related_profiles = [dict(item) for item in list(profile.get("related_profiles") or []) if isinstance(item, dict)]
        rebuilt_related_profiles = [
            self._strip_feedback_derived_related_profile_artifacts(dict(item))
            for item in original_related_profiles
        ]
        contact_feedback_buckets: dict[str, dict[str, Any]] = {}

        for message in reaction_messages:
            feedback_value = str(message.get("_reaction_feedback_value") or "").strip().lower()
            if feedback_value not in {"liked", "disliked"}:
                continue
            note_text = _compact_text(message.get("_reaction_note"), limit=500) or None
            learning_bundle = self._build_assistant_message_reaction_learning(
                store=store,
                message=message,
                feedback_value=feedback_value,
                note=note_text,
                signal_kind=str(message.get("_reaction_kind") or "feedback"),
            )
            semantic_learning = dict(learning_bundle.get("semantic_learning") or {})
            target_contact = semantic_learning.get("target_contact") if isinstance(semantic_learning, dict) else None
            signal_entries = list(semantic_learning.get("signals") or []) if isinstance(semantic_learning, dict) else []
            if not isinstance(target_contact, dict) or not signal_entries:
                continue
            contact_id = str(target_contact.get("profile_id") or _slugify(str(target_contact.get("name") or "contact")))
            bucket = contact_feedback_buckets.setdefault(
                contact_id,
                {
                    "target_contact": target_contact,
                    "item_signals": {},
                    "style_signals": {},
                    "notes": {},
                },
            )
            signal_rank = str(message.get("feedback_at") or message.get("created_at") or message.get("id") or "")
            for entry in signal_entries:
                field = str(entry.get("field") or "")
                stance = str(entry.get("stance") or "")
                if field == "contact_item_preference":
                    item_key = str(entry.get("item_key") or entry.get("topic_key") or "")
                    item_label = str(entry.get("item_label") or self._item_label(item_key.replace("gift:", "")))
                    if item_key:
                        previous = dict((bucket.get("item_signals") or {}).get(item_key) or {})
                        if not previous or signal_rank >= str(previous.get("rank") or ""):
                            bucket["item_signals"][item_key] = {
                                "rank": signal_rank,
                                "stance": stance,
                                "label": item_label,
                            }
                elif field == "contact_communication_style":
                    for style_label in [str(item).strip() for item in list(entry.get("style_labels") or []) if str(item).strip()]:
                        style_key = _semantic_normalize_text(style_label)
                        previous = dict((bucket.get("style_signals") or {}).get(style_key) or {})
                        if not previous or signal_rank >= str(previous.get("rank") or ""):
                            bucket["style_signals"][style_key] = {
                                "rank": signal_rank,
                                "stance": stance,
                                "label": style_label,
                            }
            note_summary = _compact_text(note_text, limit=240)
            if note_summary:
                bucket["notes"][str(message.get("id") or signal_rank or note_summary)] = {
                    "rank": signal_rank,
                    "value": note_summary,
                }

        for bucket in contact_feedback_buckets.values():
            rebuilt_related_profiles = self._apply_feedback_learning_to_related_profiles(
                related_profiles=rebuilt_related_profiles,
                target_contact=dict(bucket.get("target_contact") or {}),
                signal_entries=[],
                note=None,
                aggregated_bucket=bucket,
            )

        if rebuilt_related_profiles == original_related_profiles:
            return {
                "updated": False,
                "related_profiles": original_related_profiles,
                "summary": "İlişki profilleri mevcut geri bildirimlerle zaten uyumlu.",
            }

        saved_profile = self._persist_user_profile_snapshot(store=store, profile={**profile, "related_profiles": rebuilt_related_profiles})
        return {
            "updated": True,
            "related_profiles": saved_profile.get("related_profiles") or rebuilt_related_profiles,
            "summary": "İlişki profilleri aktif geri bildirimlerden yeniden kuruldu.",
        }

    def _apply_feedback_learning_to_related_profiles(
        self,
        *,
        related_profiles: list[dict[str, Any]],
        target_contact: dict[str, Any],
        signal_entries: list[dict[str, Any]],
        note: str | None,
        aggregated_bucket: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        next_profiles = [dict(item) for item in list(related_profiles or []) if isinstance(item, dict)]
        target_id = str(target_contact.get("profile_id") or "").strip()
        target_name = str(target_contact.get("name") or "Kişi").strip() or "Kişi"
        target_relationship = str(target_contact.get("relationship") or "").strip()
        target_index = -1
        for index, item in enumerate(next_profiles):
            if target_id and str(item.get("id") or "").strip() == target_id:
                target_index = index
                break
            if target_name and _semantic_normalize_text(item.get("name")) == _semantic_normalize_text(target_name):
                target_index = index
                break
        if target_index < 0:
            return next_profiles

        target_profile = dict(next_profiles[target_index])
        next_preferences = str(target_profile.get("preferences") or "")
        if aggregated_bucket is not None:
            feedback_lines = self._render_feedback_bucket_profile_lines(aggregated_bucket)
            next_preferences = "\n".join(
                part
                for part in [
                    next_preferences.strip(),
                    *feedback_lines,
                ]
                if str(part).strip()
            ).strip()
            note_lines = _split_semantic_statements(target_profile.get("notes"))
            sorted_notes = sorted(
                [dict(item) for item in list((aggregated_bucket.get("notes") or {}).values()) if isinstance(item, dict)],
                key=lambda item: str(item.get("rank") or ""),
            )
            for item in sorted_notes[-8:]:
                semantic_note = f"{FEEDBACK_PROFILE_NOTE_PREFIX} {str(item.get('value') or '').strip()}"
                if semantic_note and semantic_note not in note_lines:
                    note_lines.append(semantic_note)
            target_profile["notes"] = "\n".join(note_lines[-8:]).strip()
        else:
            for entry in signal_entries:
                statement = str(entry.get("profile_statement") or "").strip()
                prefix = str(entry.get("profile_prefix") or "").strip()
                if not statement or not prefix:
                    continue
                next_preferences = self._merge_related_profile_learning_statement(next_preferences, prefix=prefix, statement=statement)
            note_summary = _compact_text(note, limit=240)
            if note_summary:
                existing_notes = str(target_profile.get("notes") or "")
                semantic_note = f"{FEEDBACK_PROFILE_NOTE_PREFIX} {note_summary}"
                note_lines = _split_semantic_statements(existing_notes)
                if semantic_note not in note_lines:
                    note_lines.append(semantic_note)
                target_profile["notes"] = "\n".join(note_lines[-8:]).strip()
        target_profile["preferences"] = next_preferences

        target_profile.setdefault("id", target_id or _slugify(target_name))
        target_profile.setdefault("name", target_name)
        target_profile.setdefault("relationship", target_relationship)
        target_profile.setdefault("closeness", self._related_profile_closeness(str(target_profile.get("relationship") or target_relationship)))
        target_profile.setdefault("important_dates", [])
        next_profiles[target_index] = target_profile
        return next_profiles

    def _assistant_feedback_user_profile_lines(
        self,
        *,
        feedback_value: str,
        signal_profile: dict[str, Any],
    ) -> list[tuple[str, str]]:
        lines: list[tuple[str, str]] = []
        explanation_style = str(signal_profile.get("explanation_style") or "balanced")
        if explanation_style in {"concise", "detailed"}:
            if feedback_value == "liked":
                style_label = "kısa" if explanation_style == "concise" else "detaylı"
                lines.append(("Yanıt tarzı:", f"Yanıt tarzı: {style_label} açıklamalar olumlu karşılanıyor."))
            else:
                alternate = "detaylı" if explanation_style == "concise" else "kısa"
                lines.append(("Yanıt tarzı:", f"Yanıt tarzı: {alternate} açıklamalar daha uygun görünüyor."))

        if signal_profile.get("is_proactive") or signal_profile.get("is_routine"):
            lines.append(
                (
                    "Takip tarzı:",
                    "Takip tarzı: Proaktif takip ve hatırlatma akışları olumlu karşılanıyor."
                    if feedback_value == "liked"
                    else "Takip tarzı: Daha düşük yoğunluklu ve isteğe bağlı takip tercih ediliyor.",
                )
            )

        if signal_profile.get("is_planning"):
            lines.append(
                (
                    "Planlama desteği:",
                    "Planlama desteği: Daha yapılandırılmış plan önerileri olumlu karşılanıyor."
                    if feedback_value == "liked"
                    else "Planlama desteği: Daha hafif ve özet plan önerileri tercih ediliyor.",
                )
            )
        return lines

    @staticmethod
    def _strip_feedback_derived_user_profile_notes(notes: str | None) -> str:
        return "\n".join(
            line
            for line in _split_semantic_statements(notes)
            if not any(line.startswith(prefix) for prefix in USER_FEEDBACK_NOTE_PREFIXES)
        ).strip()

    def _render_feedback_bucket_profile_lines(self, bucket: dict[str, Any]) -> list[str]:
        lines: list[str] = []

        style_signals = [dict(item) for item in list((bucket.get("style_signals") or {}).values()) if isinstance(item, dict)]
        preferred_styles = [str(item.get("label") or "").strip() for item in style_signals if str(item.get("stance") or "") == "prefers" and str(item.get("label") or "").strip()]
        avoided_styles = [str(item.get("label") or "").strip() for item in style_signals if str(item.get("stance") or "") == "avoids" and str(item.get("label") or "").strip()]
        if preferred_styles or avoided_styles:
            style_parts: list[str] = []
            if preferred_styles:
                style_parts.append(f"{', '.join(dict.fromkeys(preferred_styles))} ton olumlu karşılanıyor")
            if avoided_styles:
                style_parts.append(f"{', '.join(dict.fromkeys(avoided_styles))} tondan kaçınılmalı")
            lines.append(f"İletişim: {'; '.join(style_parts)}.")

        item_signals = [dict(item) for item in list((bucket.get("item_signals") or {}).values()) if isinstance(item, dict)]
        preferred_items = [str(item.get("label") or "").strip() for item in item_signals if str(item.get("stance") or "") == "prefers" and str(item.get("label") or "").strip()]
        avoided_items = [str(item.get("label") or "").strip() for item in item_signals if str(item.get("stance") or "") == "avoids" and str(item.get("label") or "").strip()]
        if preferred_items or avoided_items:
            item_parts: list[str] = []
            if preferred_items:
                item_parts.append(f"{', '.join(dict.fromkeys(preferred_items))} önerileri olumlu karşılanıyor")
            if avoided_items:
                item_parts.append(f"{', '.join(dict.fromkeys(avoided_items))} önerilerinden kaçınılmalı")
            lines.append(f"Hediye: {'; '.join(item_parts)}.")

        return lines

    def _strip_feedback_derived_related_profile_artifacts(self, profile: dict[str, Any]) -> dict[str, Any]:
        next_profile = dict(profile)
        preference_lines = [
            line
            for line in _split_semantic_statements(next_profile.get("preferences"))
            if not any(line.startswith(prefix) for prefix in FEEDBACK_PROFILE_PREFIXES)
        ]
        note_lines = [
            line
            for line in _split_semantic_statements(next_profile.get("notes"))
            if not line.startswith(FEEDBACK_PROFILE_NOTE_PREFIX)
        ]
        next_profile["preferences"] = "\n".join(preference_lines).strip()
        next_profile["notes"] = "\n".join(note_lines).strip()
        return next_profile

    @staticmethod
    def _merge_related_profile_learning_statement(existing_value: str, *, prefix: str, statement: str) -> str:
        lines = _split_semantic_statements(existing_value)
        filtered = [line for line in lines if not line.startswith(prefix)]
        filtered.append(statement)
        return "\n".join(filtered[-8:])

    @staticmethod
    def _related_profile_closeness(relationship: str) -> int:
        normalized = _semantic_normalize_text(relationship)
        if not normalized:
            return 3
        if any(token in normalized for token in ("anne", "baba", "es", "partner", "sevgili", "cocuk", "oglum", "kizim")):
            return 5
        if any(token in normalized for token in ("kardes", "arkadas", "kuzen", "aile", "yakin dost")):
            return 4
        if any(token in normalized for token in ("avukat", "doktor", "musteri", "muvekkil", "is ortagi", "koc")):
            return 3
        return 3

    def _persist_user_profile_snapshot(self, *, store: Any, profile: dict[str, Any]) -> dict[str, Any]:
        saved = store.upsert_user_profile(
            self.office_id,
            display_name=profile.get("display_name"),
            favorite_color=profile.get("favorite_color"),
            food_preferences=profile.get("food_preferences"),
            transport_preference=profile.get("transport_preference"),
            weather_preference=profile.get("weather_preference"),
            travel_preferences=profile.get("travel_preferences"),
            home_base=profile.get("home_base"),
            current_location=profile.get("current_location"),
            location_preferences=profile.get("location_preferences"),
            maps_preference=profile.get("maps_preference"),
            prayer_notifications_enabled=bool(profile.get("prayer_notifications_enabled")),
            prayer_habit_notes=profile.get("prayer_habit_notes"),
            communication_style=profile.get("communication_style"),
            assistant_notes=profile.get("assistant_notes"),
            important_dates=list(profile.get("important_dates") or []),
            related_profiles=list(profile.get("related_profiles") or []),
            inbox_watch_rules=list(profile.get("inbox_watch_rules") or []),
            inbox_keyword_rules=list(profile.get("inbox_keyword_rules") or []),
            inbox_block_rules=list(profile.get("inbox_block_rules") or []),
        )
        memory_mutations = getattr(store, "_memory_mutations", None)
        if memory_mutations is not None:
            try:
                memory_mutations.reconcile_user_profile(
                    profile=saved,
                    authority="profile",
                    reason="knowledge_base_profile_snapshot",
                )
            except Exception:  # noqa: BLE001
                pass
        return saved

    def _locate_record(
        self,
        state: dict[str, Any],
        *,
        target_record_id: str | None = None,
        page_key: str | None = None,
    ) -> tuple[str | None, dict[str, Any] | None]:
        wanted_id = str(target_record_id or "").strip()
        pages = [str(page_key).strip()] if str(page_key or "").strip() else list((state.get("pages") or {}).keys())
        for candidate_page in pages:
            for record in ((state.get("pages") or {}).get(candidate_page) or {}).get("records", []):
                if not isinstance(record, dict):
                    continue
                if wanted_id and str(record.get("id") or "") != wanted_id:
                    continue
                if wanted_id:
                    return candidate_page, record
        return None, None

    def _memory_preference_record(
        self,
        *,
        page_key: str,
        record_key: str,
        title: str,
        summary: str,
        scope: str,
        note: str | None,
        source_refs: list[dict[str, Any] | str] | None,
        metadata: dict[str, Any] | None,
        signals: list[str] | None = None,
    ) -> dict[str, Any]:
        now = _iso_now()
        record_metadata = dict(metadata or {})
        record_metadata.setdefault("scope", scope)
        record_metadata.setdefault("record_type", PAGE_RECORD_TYPES.get(page_key, "source"))
        sensitivity = str(record_metadata.get("sensitivity") or self._infer_sensitivity(page_key, record_metadata))
        record_metadata.setdefault("sensitivity", sensitivity)
        record_metadata.setdefault("shareability", _scope_shareability(scope, sensitivity))
        history = list(record_metadata.get("correction_history") or [])
        if note:
            history.append({"action": "note", "note": note, "timestamp": now})
        record_metadata["correction_history"] = history
        return {
            "id": f"{record_key}-{_fingerprint([summary, scope, now])[:8]}",
            "key": record_key,
            "title": _compact_text(title, limit=160),
            "summary": _compact_text(summary, limit=800),
            "confidence": round(float(record_metadata.get("confidence") or 1.0), 2),
            "status": "active",
            "source_refs": [str(item) if not isinstance(item, dict) else json.dumps(item, ensure_ascii=False, sort_keys=True) for item in list(source_refs or [])],
            "signals": [str(item).strip() for item in list(signals or ["explicit_user_correction"]) if str(item).strip()],
            "updated_at": now,
            "metadata": record_metadata,
        }

    def _knowledge_insight_record(
        self,
        *,
        page_key: str,
        record_key: str,
        title: str,
        summary: str,
        scope: str,
        source_refs: list[dict[str, Any] | str] | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = _iso_now()
        record_metadata = dict(metadata or {})
        record_metadata.setdefault("scope", scope)
        record_metadata.setdefault("record_type", "insight")
        sensitivity = str(record_metadata.get("sensitivity") or self._infer_sensitivity(page_key, record_metadata))
        record_metadata.setdefault("sensitivity", sensitivity)
        record_metadata.setdefault("shareability", _scope_shareability(scope, sensitivity))
        record_metadata.setdefault("source_basis", [str(item) for item in list(source_refs or []) if str(item).strip()])
        record_metadata.setdefault("confidence", round(float(record_metadata.get("confidence") or 0.68), 2))
        return {
            "id": f"{record_key}-{_fingerprint([summary, scope])[:8]}",
            "key": record_key,
            "title": _compact_text(title, limit=160),
            "summary": _compact_text(summary, limit=800),
            "confidence": round(float(record_metadata.get("confidence") or 0.68), 2),
            "status": "active",
            "source_refs": [str(item) if not isinstance(item, dict) else json.dumps(item, ensure_ascii=False, sort_keys=True) for item in list(source_refs or [])],
            "signals": ["knowledge_synthesis"],
            "updated_at": now,
            "metadata": record_metadata,
        }

    def _render_knowledge_synthesis_markdown(self, report: dict[str, Any]) -> str:
        lines = [
            "# Knowledge Synthesis",
            "",
            f"- Generated at: {report.get('generated_at')}",
            f"- Reason: {report.get('reason')}",
            f"- Generated records: {(report.get('summary') or {}).get('generated_records', 0)}",
            f"- Generated strategies: {(report.get('summary') or {}).get('generated_strategies', 0)}",
            "",
            "## Insights",
        ]
        insights = list(report.get("insights") or [])
        if not insights:
            lines.append("- None")
        else:
            for item in insights:
                lines.append(
                    f"- [{item.get('page_key')}] {item.get('title')}: {item.get('summary')} | confidence={item.get('confidence')}"
                )
        lines.extend(["", "## Strategies"])
        strategies = list(report.get("strategies") or [])
        if not strategies:
            lines.append("- None")
        else:
            for item in strategies:
                lines.append(f"- [{item.get('page_key')}] {item.get('title')}: {item.get('summary')}")
        lines.extend(["", "## Hypotheses"])
        hypotheses = list(report.get("hypotheses") or [])
        if not hypotheses:
            lines.append("- None")
        else:
            for item in hypotheses:
                lines.append(f"- {item.get('title')}: {item.get('summary')} | confidence={item.get('confidence')}")
        return "\n".join(lines).rstrip() + "\n"

    def _should_file_back(self, *, kind: str, content: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
        normalized_kind = str(kind or "").strip()
        text = _compact_text(content, limit=2400)
        meta = dict(metadata or {})
        if len(text) < 80 and normalized_kind not in {"accepted_recommendation", "rejected_recommendation", "preference_correction", "reflection_output"}:
            return {"should_file_back": False}
        page_key = str(meta.get("page_key") or "")
        record_type = str(meta.get("record_type") or "")
        scope = str(meta.get("scope") or "")
        sensitivity = str(meta.get("sensitivity") or "")
        if normalized_kind in {"query_answer", "assistant_reply"}:
            page_key = page_key or ("legal" if meta.get("matter_id") else "projects")
            record_type = record_type or ("legal_matter" if meta.get("matter_id") else "source")
            scope = scope or (f"project:matter-{meta.get('matter_id')}" if meta.get("matter_id") else "professional")
            sensitivity = sensitivity or ("restricted" if meta.get("matter_id") else "medium")
            return {
                "should_file_back": True,
                "page_key": page_key,
                "record_type": record_type,
                "scope": scope,
                "sensitivity": sensitivity,
            }
        if normalized_kind in {"accepted_recommendation", "rejected_recommendation", "preference_correction"}:
            page_key = page_key or ("preferences" if normalized_kind == "preference_correction" else "recommendations")
            record_type = record_type or ("preference" if normalized_kind == "preference_correction" else "recommendation")
            scope = scope or "personal"
            sensitivity = sensitivity or "high"
            return {
                "should_file_back": True,
                "page_key": page_key,
                "record_type": record_type,
                "scope": scope,
                "sensitivity": sensitivity,
            }
        if normalized_kind in {"daily_planning_output", "reflection_output"}:
            page_key = page_key or ("reflections" if normalized_kind == "reflection_output" else "projects")
            record_type = record_type or ("reflection" if normalized_kind == "reflection_output" else "goal")
            scope = scope or "personal"
            sensitivity = sensitivity or "medium"
            return {
                "should_file_back": True,
                "page_key": page_key,
                "record_type": record_type,
                "scope": scope,
                "sensitivity": sensitivity,
            }
        if normalized_kind in {"draft_style_learning", "relationship_note"}:
            page_key = page_key or ("contacts" if normalized_kind == "relationship_note" else "preferences")
            record_type = record_type or ("person" if normalized_kind == "relationship_note" else "conversation_style")
            scope = scope or ("personal" if page_key == "contacts" else "global")
            sensitivity = sensitivity or "high"
            return {
                "should_file_back": True,
                "page_key": page_key,
                "record_type": record_type,
                "scope": scope,
                "sensitivity": sensitivity,
            }
        return {"should_file_back": False}

    def _search_records(
        self,
        state: dict[str, Any],
        *,
        query: str,
        scopes: list[str] | None,
        page_keys: list[str] | None,
        limit: int,
        include_decisions: bool,
        include_reflections: bool,
    ) -> list[dict[str, Any]]:
        requested_pages = {str(item).strip() for item in list(page_keys or []) if str(item).strip()}
        requested_scopes = [str(item).strip() for item in list(scopes or []) if str(item).strip()]
        query_tokens = set(_tokenize(query))
        hits: list[dict[str, Any]] = []
        for page_key, page in (state.get("pages") or {}).items():
            if requested_pages and page_key not in requested_pages:
                continue
            if page_key == "decisions" and not include_decisions:
                continue
            if page_key == "reflections" and not include_reflections:
                continue
            for record in page.get("records") or []:
                if not isinstance(record, dict):
                    continue
                if str(record.get("status") or "active") != "active":
                    continue
                envelope = self._normalized_record_envelope(page_key, record)
                scope = str(envelope.get("scope") or "")
                if requested_scopes and not self._scope_matches(scope, requested_scopes):
                    continue
                searchable = " ".join(
                    [
                        page_key,
                        str(record.get("title") or ""),
                        str(record.get("summary") or ""),
                        json.dumps(envelope.get("metadata") or {}, ensure_ascii=False),
                    ]
                )
                score = self._score_text_match(query_tokens, searchable)
                if score <= 0:
                    continue
                hits.append(
                    {
                        "page_key": page_key,
                        "record_id": record.get("id"),
                        "title": record.get("title"),
                        "summary": record.get("summary"),
                        "score": round(score, 4),
                        "record_type": envelope.get("record_type"),
                        "scope": scope,
                        "sensitivity": envelope.get("sensitivity"),
                        "exportability": envelope.get("exportability"),
                        "model_routing_hint": envelope.get("model_routing_hint"),
                        "source_refs": list(record.get("source_refs") or []),
                        "metadata": envelope.get("metadata") or {},
                        "updated_at": record.get("updated_at"),
                    }
                )
        hits.sort(key=lambda item: (-float(item.get("score") or 0.0), str(item.get("updated_at") or "")), reverse=False)
        return hits[: max(1, min(limit, 20))]

    @staticmethod
    def _score_text_match(query_tokens: set[str], searchable: str) -> float:
        tokens = _tokenize(searchable)
        if not tokens:
            return 0.0
        token_set = set(tokens)
        if not query_tokens:
            return 0.0
        overlap = len(query_tokens & token_set)
        if overlap == 0:
            return 0.0
        density = overlap / max(len(query_tokens), 1)
        coverage = overlap / max(len(token_set), 1)
        return density + coverage * 0.35

    @staticmethod
    def _scope_matches(record_scope: str, requested_scopes: list[str]) -> bool:
        if not requested_scopes:
            return True
        for requested in requested_scopes:
            if record_scope == requested:
                return True
            if record_scope.startswith(f"{requested}:"):
                return True
            if requested.startswith("project:") and record_scope == "professional":
                continue
        return False

    def _recent_feedback_for_query(self, query: str, *, scopes: list[str] | None = None) -> list[dict[str, Any]]:
        state = self._load_state()
        query_tokens = set(_tokenize(query))
        feedback: list[dict[str, Any]] = []
        for item in reversed(list(state.get("recommendation_history") or [])):
            if str(item.get("outcome") or "") not in {"accepted", "rejected", "ignored"}:
                continue
            searchable = " ".join([str(item.get("suggestion") or ""), str(item.get("why_this") or ""), str(item.get("kind") or "")])
            if self._score_text_match(query_tokens, searchable) <= 0:
                continue
            feedback.append(
                {
                    "id": item.get("id"),
                    "kind": item.get("kind"),
                    "outcome": item.get("outcome"),
                    "feedback_note": item.get("feedback_note"),
                    "created_at": item.get("created_at"),
                }
            )
            if len(feedback) >= 5:
                break
        return feedback

    def _infer_scope(self, page_key: str, metadata: dict[str, Any], record: dict[str, Any]) -> str:
        explicit = str(metadata.get("scope") or "").strip()
        if explicit:
            return explicit
        matter_id = metadata.get("matter_id")
        if matter_id is None:
            matter_id = (metadata.get("metadata") or {}).get("matter_id") if isinstance(metadata.get("metadata"), dict) else None
        if matter_id is not None:
            return f"project:matter-{matter_id}"
        source_type = str(metadata.get("source_type") or "")
        if source_type in {"profile_snapshot", "assistant_runtime_snapshot", "user_preferences"}:
            return "personal"
        return DEFAULT_PAGE_SCOPES.get(page_key, "global")

    def _infer_sensitivity(self, page_key: str, metadata: dict[str, Any]) -> str:
        explicit = str(metadata.get("sensitivity") or "").strip()
        if explicit:
            return explicit
        if str(metadata.get("source_type") or "") in {"legal_docs", "assistant_file_back"} and "matter_id" in json.dumps(metadata, ensure_ascii=False):
            return "restricted"
        return DEFAULT_PAGE_SENSITIVITY.get(page_key, "medium")

    def _infer_relations(self, page_key: str, metadata: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
        relations = list(metadata.get("relations") or [])
        scope = self._infer_scope(page_key, metadata, record)
        summary = str(record.get("summary") or "").lower()
        field = str(metadata.get("field") or "").strip()
        if scope:
            relations.append({"relation_type": "scoped_to", "target": scope})
        if metadata.get("source_type"):
            relations.append({"relation_type": "inferred_from", "target": str(metadata.get("source_type"))})
        if metadata.get("requires_confirmation") is True:
            relations.append({"relation_type": "requires_confirmation", "target": "user"})
        if field:
            relations.append({"relation_type": "related_to", "target": field})
        if metadata.get("matter_id") is not None:
            relations.append({"relation_type": "relevant_to", "target": f"matter:{metadata.get('matter_id')}"})
        if metadata.get("supersedes_record_id"):
            relations.append({"relation_type": "supersedes", "target": str(metadata.get("supersedes_record_id"))})
        if int(metadata.get("repeated_contradiction_count") or 0) > 0 and metadata.get("supersedes_record_id"):
            relations.append({"relation_type": "contradicts", "target": str(metadata.get("supersedes_record_id"))})
        if metadata.get("recommendation_kind"):
            relations.append({"relation_type": "supports", "target": str(metadata.get("recommendation_kind"))})
        if metadata.get("topic"):
            relations.append({"relation_type": "relevant_to", "target": str(metadata.get("topic"))})
        if any(token in summary for token in ("tercih", "sever", "seviyor", "uygun", "yararlı", "nazik", "kısa", "tren", "hafif")) and field:
            relations.append({"relation_type": "prefers", "target": field})
        if any(token in summary for token in ("istemiyor", "kaçın", "kacin", "rahatsız", "rahatsiz", "seyrek", "tekrar sunulmasın", "sunulmasin")) and field:
            relations.append({"relation_type": "avoids", "target": field})
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in relations:
            if not isinstance(item, dict):
                continue
            marker = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(item)
        return deduped

    def _compute_record_priority(self, page_key: str, metadata: dict[str, Any], record: dict[str, Any]) -> dict[str, float]:
        record_type = str(metadata.get("record_type") or PAGE_RECORD_TYPES.get(page_key, "source"))
        base_weights = {
            "decision": 0.92,
            "legal_matter": 0.9,
            "preference": 0.82,
            "conversation_style": 0.8,
            "routine": 0.78,
            "goal": 0.76,
            "constraint": 0.78,
            "recommendation": 0.7,
            "insight": 0.83,
            "knowledge_article": 0.8,
            "reflection": 0.68,
            "source": 0.58,
            "place": 0.7,
            "project": 0.74,
        }
        confidence = round(float(record.get("confidence") or metadata.get("confidence") or 0.0), 2)
        relation_count = len(list(metadata.get("relations") or []))
        source_count = len(list(record.get("source_refs") or []))
        correction_count = len(list(metadata.get("correction_history") or []))
        source_type = str(metadata.get("source_type") or "")
        self_generated = self._record_is_self_generated(metadata)
        frequency_signal = (
            source_count
            + int(metadata.get("acceptance_count") or 0)
            + int(metadata.get("rejection_count") or 0)
            + int(metadata.get("count") or 0)
            + max(0, relation_count - 1)
        )
        updated_dt = _iso_to_datetime(str(record.get("updated_at") or metadata.get("recency", {}).get("updated_at") or ""))
        age_days = max(0.0, (datetime.now(timezone.utc) - updated_dt).total_seconds() / 86400.0) if updated_dt else 365.0
        decay = min(0.72, age_days / 365.0)
        if metadata.get("record_type") in {"decision", "legal_matter"}:
            decay *= 0.65
        if str(record.get("status") or "active") != "active":
            decay = min(0.95, decay + 0.15)
        importance = (
            base_weights.get(record_type, 0.62)
            + (confidence * 0.25)
            + min(0.18, source_count * 0.03)
            + min(0.16, relation_count * 0.025)
            + min(0.18, math.log1p(max(frequency_signal, 0)) * 0.08)
            - min(0.22, correction_count * 0.05)
        )
        if self_generated:
            importance -= 0.42
            decay = min(0.95, decay + 0.18)
        if str(metadata.get("epistemic_retrieval_eligibility") or "") in {"quarantined", "blocked"}:
            importance -= 0.25
            decay = min(0.95, decay + 0.1)
        importance = round(max(0.05, min(1.9, importance)), 4)
        decay = round(max(0.0, min(0.95, decay)), 4)
        priority = round(max(0.03, importance * (1.0 - (decay * 0.55))), 4)
        return {
            "importance_score": importance,
            "decay_score": decay,
            "frequency_weight": round(min(1.0, math.log1p(max(frequency_signal, 0)) / 2.4), 4),
            "priority_score": priority,
        }

    def _normalized_record_envelope(self, page_key: str, record: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(record.get("metadata") or {})
        sensitivity = self._infer_sensitivity(page_key, metadata)
        scope = self._infer_scope(page_key, metadata, record)
        record_type = str(metadata.get("record_type") or PAGE_RECORD_TYPES.get(page_key, "source"))
        exportability = str(metadata.get("exportability") or EXPORTABILITY_BY_SENSITIVITY.get(sensitivity, "redaction_required"))
        model_routing_hint = str(metadata.get("model_routing_hint") or MODEL_ROUTING_BY_SENSITIVITY.get(sensitivity, "redaction_required"))
        shareability = str(metadata.get("shareability") or _scope_shareability(scope, sensitivity))
        metadata.setdefault("record_type", record_type)
        metadata.setdefault("scope", scope)
        metadata.setdefault("sensitivity", sensitivity)
        metadata.setdefault("exportability", exportability)
        metadata.setdefault("model_routing_hint", model_routing_hint)
        metadata.setdefault("shareability", shareability)
        metadata.setdefault("recency", {"updated_at": record.get("updated_at")})
        metadata.setdefault("confidence", round(float(record.get("confidence") or 0.0), 2))
        metadata.setdefault("correction_history", list(metadata.get("correction_history") or []))
        metadata.setdefault("self_generated", self._record_is_self_generated(metadata))
        if metadata.get("self_generated"):
            metadata.setdefault("epistemic_retrieval_eligibility", "quarantined")
        metadata["relations"] = self._infer_relations(page_key, metadata, record)
        metadata.update({key: metadata.get(key, value) for key, value in self._compute_record_priority(page_key, metadata, record).items()})
        return {
            "record_type": record_type,
            "scope": scope,
            "sensitivity": sensitivity,
            "exportability": exportability,
            "model_routing_hint": model_routing_hint,
            "shareability": shareability,
            "metadata": metadata,
        }

    @staticmethod
    def _record_is_self_generated(metadata: dict[str, Any] | None) -> bool:
        payload = dict(metadata or {})
        if bool(payload.get("self_generated")):
            return True
        source_type = str(payload.get("source_type") or "").strip().lower()
        file_back_kind = str(payload.get("file_back_kind") or "").strip().lower()
        return source_type == "assistant_file_back" and bool(file_back_kind)

    def _sync_connector_records(
        self,
        store: Any,
        *,
        reason: str,
        connector_names: list[str] | None = None,
        trigger: str = "store_sync",
        render: bool = True,
    ) -> dict[str, Any]:
        state = self._load_state()
        connector_sync = dict(state.get("connector_sync") or {})
        connector_fingerprints = dict(connector_sync.get("connectors") or {})
        checkpoints = dict(connector_sync.get("checkpoints") or {})
        mirror_events = dict(connector_sync.get("mirror_events") or {})
        updated_pages: list[str] = []
        contradictions: list[dict[str, Any]] = []
        synced_records: list[dict[str, Any]] = []
        failed_connectors: list[dict[str, Any]] = []
        requested_connectors = {str(item).strip() for item in list(connector_names or []) if str(item).strip()}
        next_fingerprints: dict[str, str] = {
            str(key): str(value)
            for key, value in connector_fingerprints.items()
            if not requested_connectors or str(key).split(":", 1)[0] not in requested_connectors
        }
        sync_started_at = _iso_now()

        for connector in self.connector_registry:
            if requested_connectors and connector.name not in requested_connectors:
                continue
            connector_started_at = _utcnow()
            prior_checkpoint = dict(checkpoints.get(connector.name) or {})
            checkpoint_base = {
                "record_count": int(prior_checkpoint.get("record_count") or 0),
                "synced_record_count": 0,
                "last_synced_at": prior_checkpoint.get("last_synced_at"),
                "cursor": prior_checkpoint.get("cursor"),
                "checkpoint": dict(prior_checkpoint.get("checkpoint") or {}),
                "last_success_at": prior_checkpoint.get("last_success_at"),
            }
            provider_events = [
                dict(mirror_events.get(provider) or {})
                for provider in getattr(connector, "provider_hints", ()) or ()
                if isinstance(mirror_events.get(provider), dict)
            ]
            latest_mirror = next(
                (
                    item
                    for item in sorted(provider_events, key=lambda payload: str(payload.get("synced_at") or ""), reverse=True)
                    if item
                ),
                {},
            )
            latest_occurred_at = None
            last_cursor = str(latest_mirror.get("cursor") or "").strip() or None
            connector_items: list[ConnectorRecord] = []
            try:
                connector_items = list(connector.collect(store=store, office_id=self.office_id) or [])
                for item in connector_items:
                    if not isinstance(item, ConnectorRecord):
                        continue
                    source_key = f"{connector.name}:{item.source_ref}"
                    next_fingerprints[source_key] = item.fingerprint
                    if item.occurred_at and (latest_occurred_at is None or str(item.occurred_at) > str(latest_occurred_at)):
                        latest_occurred_at = item.occurred_at
                        last_cursor = item.source_ref
                    if connector_fingerprints.get(source_key) == item.fingerprint:
                        continue
                    metadata = dict(item.metadata or {})
                    metadata.update(
                        {
                            "connector_name": connector.name,
                            "scope": item.scope,
                            "sensitivity": item.sensitivity,
                            "exportability": item.exportability,
                            "model_routing_hint": item.model_routing_hint,
                            "sync_reason": reason,
                        }
                    )
                    ingest_result = self.ingest(
                        source_type=item.source_type,
                        content=item.content,
                        title=item.title,
                        metadata=metadata,
                        occurred_at=item.occurred_at,
                        source_ref=item.source_ref,
                        tags=item.tags,
                        render=False,
                    )
                    updated_pages.extend(ingest_result.get("compile", {}).get("updated_pages") or [])
                    contradictions.extend(ingest_result.get("compile", {}).get("contradictions") or [])
                    synced_records.append({"connector": connector.name, "source_ref": item.source_ref, "source_type": item.source_type})
                duration_ms = int((_utcnow() - connector_started_at).total_seconds() * 1000)
                checkpoints[connector.name] = {
                    "last_synced_at": latest_occurred_at or latest_mirror.get("synced_at") or _iso_now(),
                    "cursor": str(latest_mirror.get("cursor") or "").strip() or last_cursor,
                    "checkpoint": {
                        "fingerprint_count": sum(1 for key in next_fingerprints if str(key).startswith(f"{connector.name}:")),
                        "provider_hints": list(getattr(connector, "provider_hints", ()) or ()),
                        "mirror_stats": latest_mirror.get("stats") or {},
                        "mirror_checkpoint": latest_mirror.get("checkpoint") or {},
                    },
                    "record_count": len(connector_items),
                    "synced_record_count": sum(1 for item in synced_records if str(item.get("connector") or "") == connector.name),
                    "reason": reason,
                    "trigger": trigger,
                    "mirror_sync_at": latest_mirror.get("synced_at"),
                    "health_status": "valid",
                    "sync_status": "completed",
                    "sync_status_message": "Connector sync başarıyla tamamlandı.",
                    "last_error": None,
                    "consecutive_failures": 0,
                    "next_retry_at": None,
                    "last_attempted_at": _iso_now(),
                    "last_success_at": _iso_now(),
                    "last_duration_ms": duration_ms,
                    "retry_delay_minutes": None,
                    "provider_mode": getattr(connector, "sync_mode", "local_scan"),
                }
            except Exception as exc:  # noqa: BLE001
                consecutive_failures = int(prior_checkpoint.get("consecutive_failures") or 0) + 1
                retry_delay_minutes = min(60, 2 ** min(consecutive_failures, 6))
                next_retry_at = (_utcnow() + timedelta(minutes=retry_delay_minutes)).isoformat()
                duration_ms = int((_utcnow() - connector_started_at).total_seconds() * 1000)
                checkpoints[connector.name] = {
                    **checkpoint_base,
                    "reason": reason,
                    "trigger": trigger,
                    "mirror_sync_at": latest_mirror.get("synced_at"),
                    "health_status": "invalid",
                    "sync_status": "retry_scheduled",
                    "sync_status_message": f"Connector sync başarısız oldu, {retry_delay_minutes} dakika sonra yeniden denenecek.",
                    "last_error": str(exc),
                    "consecutive_failures": consecutive_failures,
                    "next_retry_at": next_retry_at,
                    "last_attempted_at": _iso_now(),
                    "last_duration_ms": duration_ms,
                    "retry_delay_minutes": retry_delay_minutes,
                    "provider_mode": getattr(connector, "sync_mode", "local_scan"),
                }
                failed_connectors.append(
                    {
                        "connector": connector.name,
                        "error": str(exc),
                        "next_retry_at": next_retry_at,
                        "consecutive_failures": consecutive_failures,
                    }
                )
                self._append_log(
                    "connector_sync_failed",
                    f"{connector.name} connector senkronu başarısız oldu",
                    {"error": str(exc), "reason": reason, "trigger": trigger},
                )

        state = self._load_state()
        connector_sync = dict(state.get("connector_sync") or {})
        connector_sync["connectors"] = self._trim_fingerprint_map(next_fingerprints, limit=500)
        connector_sync["checkpoints"] = checkpoints
        connector_sync["last_reason"] = reason
        connector_sync["updated_at"] = _iso_now()
        connector_sync["last_started_at"] = sync_started_at
        connector_sync["last_completed_at"] = _iso_now()
        state["connector_sync"] = connector_sync
        self._save_state(state)
        if render and updated_pages:
            state["updated_at"] = _iso_now()
            self._save_state(state)
            self._render_all(state)
        return {
            "synced_record_count": len(synced_records),
            "synced_records": synced_records,
            "updated_pages": sorted(set(updated_pages)),
            "contradictions": contradictions,
            "failed_connectors": failed_connectors,
        }

    def _sync_operational_store_records(self, store: Any, *, reason: str, render: bool = True) -> dict[str, Any]:
        state = self._load_state()
        sync_state = dict(state.get("store_sync") or {})
        assistant_action_fingerprints = dict(sync_state.get("assistant_actions") or {})
        approval_event_fingerprints = dict(sync_state.get("approval_events") or {})
        updated_pages: list[str] = []
        contradictions: list[dict[str, Any]] = []
        synced_records: list[dict[str, Any]] = []

        recent_actions = list(store.list_assistant_actions(self.office_id, limit=25) or [])
        next_action_fingerprints: dict[str, str] = {}
        for action in recent_actions:
            action_id = str(action.get("id") or "").strip()
            if not action_id:
                continue
            serialized = {
                "id": action.get("id"),
                "matter_id": action.get("matter_id"),
                "action_type": action.get("action_type"),
                "title": action.get("title"),
                "description": action.get("description"),
                "rationale": action.get("rationale"),
                "source_refs": list(action.get("source_refs") or []),
                "target_channel": action.get("target_channel"),
                "draft_id": action.get("draft_id"),
                "status": action.get("status"),
                "manual_review_required": bool(action.get("manual_review_required")),
                "dispatch_state": action.get("dispatch_state"),
                "dispatch_error": action.get("dispatch_error"),
                "external_message_id": action.get("external_message_id"),
                "created_by": action.get("created_by"),
                "created_at": action.get("created_at"),
                "updated_at": action.get("updated_at"),
            }
            fingerprint = _fingerprint(serialized)
            next_action_fingerprints[action_id] = fingerprint
            if assistant_action_fingerprints.get(action_id) == fingerprint:
                continue
            ingest_result = self.ingest(
                source_type="assistant_action",
                content=json.dumps(serialized, ensure_ascii=False),
                title=f"Assistant action #{action_id}",
                metadata={
                    "reason": reason,
                    "action_id": serialized.get("id"),
                    "action_type": serialized.get("action_type"),
                    "status": serialized.get("status"),
                    "target_channel": serialized.get("target_channel"),
                    "matter_id": serialized.get("matter_id"),
                    "draft_id": serialized.get("draft_id"),
                },
                occurred_at=str(serialized.get("updated_at") or serialized.get("created_at") or _iso_now()),
                source_ref=f"assistant-action:{action_id}",
                tags=[
                    "assistant_action",
                    str(serialized.get("action_type") or "").strip() or "unknown_action",
                    str(serialized.get("status") or "").strip() or "unknown_status",
                ],
                render=False,
            )
            updated_pages.extend(ingest_result.get("compile", {}).get("updated_pages") or [])
            contradictions.extend(ingest_result.get("compile", {}).get("contradictions") or [])
            synced_records.append({"kind": "assistant_action", "id": action_id})

        recent_approval_events = list(store.list_approval_events(self.office_id, limit=25) or [])
        next_approval_fingerprints: dict[str, str] = {}
        for event in recent_approval_events:
            event_id = str(event.get("id") or "").strip()
            if not event_id:
                continue
            serialized = {
                "id": event.get("id"),
                "action_id": event.get("action_id"),
                "outbound_draft_id": event.get("outbound_draft_id"),
                "event_type": event.get("event_type"),
                "actor": event.get("actor"),
                "note": event.get("note"),
                "created_at": event.get("created_at"),
            }
            fingerprint = _fingerprint(serialized)
            next_approval_fingerprints[event_id] = fingerprint
            if approval_event_fingerprints.get(event_id) == fingerprint:
                continue
            ingest_result = self.ingest(
                source_type="approval_event",
                content=json.dumps(serialized, ensure_ascii=False),
                title=f"Approval event #{event_id}",
                metadata={
                    "reason": reason,
                    "approval_event_id": serialized.get("id"),
                    "action_id": serialized.get("action_id"),
                    "draft_id": serialized.get("outbound_draft_id"),
                    "event_type": serialized.get("event_type"),
                },
                occurred_at=str(serialized.get("created_at") or _iso_now()),
                source_ref=f"approval-event:{event_id}",
                tags=[
                    "approval_event",
                    str(serialized.get("event_type") or "").strip() or "unknown_event",
                ],
                render=False,
            )
            updated_pages.extend(ingest_result.get("compile", {}).get("updated_pages") or [])
            contradictions.extend(ingest_result.get("compile", {}).get("contradictions") or [])
            synced_records.append({"kind": "approval_event", "id": event_id})

        state = self._load_state()
        sync_state = dict(state.get("store_sync") or {})
        sync_state["assistant_actions"] = self._trim_fingerprint_map(next_action_fingerprints)
        sync_state["approval_events"] = self._trim_fingerprint_map(next_approval_fingerprints)
        sync_state["last_reason"] = reason
        sync_state["updated_at"] = _iso_now()
        state["store_sync"] = sync_state
        self._save_state(state)
        if render and updated_pages:
            state["updated_at"] = _iso_now()
            self._save_state(state)
            self._render_all(state)
        return {
            "synced_record_count": len(synced_records),
            "synced_records": synced_records,
            "updated_pages": sorted(set(updated_pages)),
            "contradictions": contradictions,
        }

    @staticmethod
    def _trim_fingerprint_map(values: dict[str, str], *, limit: int = 200) -> dict[str, str]:
        items = list(values.items())
        if len(items) <= limit:
            return dict(items)
        return dict(items[-limit:])

    def _default_state(self) -> dict[str, Any]:
        return {
            "version": 1,
            "schema_version": "lawcopilot.personal-kb.v1",
            "office_id": self.office_id,
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
            "pages": {
                key: {
                    "title": key.title(),
                    "description": description,
                    "records": [],
                }
                for key, description in PAGE_SPECS.items()
            },
            "decision_records": [],
            "recommendation_history": [],
            "last_reflection_at": None,
            "reflection_status": {},
            "profile_sync": {},
            "connector_sync": {},
            "store_sync": {},
            "trigger_history": [],
            "location_context": {},
            "orchestration": {},
            "coaching": {},
            "autonomy_status": {},
            "wiki_brain": {},
        }

    def _state_path(self) -> Path:
        return self.system_dir / "state.json"

    def _normalized_dir(self) -> Path:
        return self.system_dir / "normalized"

    def _reports_dir(self) -> Path:
        return self.system_dir / "reports"

    def _decisions_dir(self) -> Path:
        return self.wiki_dir / "decision-records"

    def _concepts_dir(self) -> Path:
        return self.wiki_dir / "concepts"

    def _wiki_brain_path(self) -> Path:
        return self._normalized_dir() / "wiki-brain.json"

    def _wiki_graph_path(self) -> Path:
        return self._normalized_dir() / "knowledge-graph.json"

    def _load_state(self) -> dict[str, Any]:
        if not self._state_path().exists():
            return self._default_state()
        try:
            loaded = json.loads(self._read_text_lossy(self._state_path()))
        except (json.JSONDecodeError, OSError):
            return self._default_state()
        if not isinstance(loaded, dict):
            return self._default_state()
        defaults = self._default_state()
        for key, value in defaults.items():
            if key not in loaded:
                loaded[key] = value if not isinstance(value, dict) else dict(value)
                continue
            current = loaded.get(key)
            if isinstance(value, dict) and not isinstance(current, dict):
                loaded[key] = dict(value)
            elif isinstance(value, list) and not isinstance(current, list):
                loaded[key] = list(value)
        return loaded

    def _upsert_location_page_records(self, *, current_place: dict[str, Any], frequent_patterns: list[dict[str, Any]]) -> None:
        state = self._load_state()
        updated = False
        current_record = {
            "id": f"place-{_slugify(str(current_place.get('place_id') or current_place.get('label') or 'current'))}",
            "key": f"place:{_slugify(str(current_place.get('place_id') or current_place.get('label') or 'current'))}",
            "title": _compact_text(str(current_place.get("label") or "Current place"), limit=120),
            "summary": _compact_text(
                f"{current_place.get('label') or 'Konum'} | kategori: {current_place.get('category') or 'unknown'} | alan: {current_place.get('area') or 'unknown'}",
                limit=280,
            ),
            "confidence": 0.82,
            "status": "active",
            "source_refs": [],
            "signals": ["location_context"],
            "updated_at": _iso_now(),
            "metadata": {
                "record_type": "place",
                "scope": str(current_place.get("scope") or "personal"),
                "sensitivity": str(current_place.get("sensitivity") or "high"),
                "category": current_place.get("category"),
                "area": current_place.get("area"),
                "time_bucket": current_place.get("time_bucket"),
                "source_basis": [current_place.get("source") or "manual"],
            },
        }
        updated = self._upsert_page_record(state, "places", current_record)["updated"] or updated
        for pattern in frequent_patterns[:4]:
            bucket = str(pattern.get("time_bucket") or "current")
            category = str(pattern.get("category") or "place")
            pattern_record = {
                "id": f"place-pattern-{_slugify(bucket)}-{_slugify(category)}",
                "key": f"place-pattern:{bucket}:{category}",
                "title": f"{bucket} yer örüntüsü",
                "summary": _compact_text(
                    f"Bu saat bandında sık görülen yer tipi {category}; tekrar sayısı {pattern.get('count') or 1}.",
                    limit=260,
                ),
                "confidence": 0.68,
                "status": "active",
                "source_refs": [],
                "signals": ["location_pattern"],
                "updated_at": _iso_now(),
                "metadata": {
                    "record_type": "place",
                    "scope": "personal",
                    "sensitivity": "high",
                    "time_bucket": bucket,
                    "category": category,
                    "count": pattern.get("count") or 1,
                },
            }
            updated = self._upsert_page_record(state, "places", pattern_record)["updated"] or updated
        if updated:
            state["updated_at"] = _iso_now()
            self._save_state(state)
            self._render_all(state)

    def _record_trigger_event(self, trigger: dict[str, Any], *, emitted_at: str) -> None:
        state = self._load_state()
        history = list(state.get("trigger_history") or [])
        history.append(
            {
                "id": trigger.get("id"),
                "trigger_type": trigger.get("trigger_type"),
                "logical_key": trigger.get("logical_key"),
                "title": trigger.get("title"),
                "scope": trigger.get("scope"),
                "confidence": trigger.get("confidence"),
                "urgency": trigger.get("urgency"),
                "recommended_action_kind": ((trigger.get("recommended_action") or {}).get("kind")),
                "emitted_at": emitted_at,
            }
        )
        state["trigger_history"] = history[-200:]
        state["updated_at"] = _iso_now()
        self._save_state(state)

    def _cleanup_trigger_history(self, *, now: datetime | None = None) -> dict[str, Any]:
        state = self._load_state()
        current_time = now or _utcnow()
        kept: list[dict[str, Any]] = []
        removed = 0
        for item in list(state.get("trigger_history") or []):
            created = datetime.fromisoformat(str(item.get("emitted_at") or _iso_now()).replace("Z", "+00:00"))
            if current_time - created.astimezone(timezone.utc) > timedelta(days=14):
                removed += 1
                continue
            kept.append(item)
        state["trigger_history"] = kept[-200:]
        state["updated_at"] = _iso_now()
        self._save_state(state)
        return {"removed": removed, "remaining": len(kept)}

    @staticmethod
    def _orchestration_job_interval_seconds(job_name: str, settings: Any | None = None) -> int:
        interval_defaults = {
            "connector_sync": int(getattr(settings, "personal_kb_scheduler_connector_sync_interval_seconds", 600) or 600),
            "reflection_pass": int(getattr(settings, "personal_kb_scheduler_reflection_interval_seconds", 900) or 900),
            "knowledge_synthesis": int(getattr(settings, "personal_kb_scheduler_reflection_interval_seconds", 900) or 900),
            "coaching_review": int(getattr(settings, "personal_kb_scheduler_trigger_interval_seconds", 300) or 300) * 2,
            "trigger_evaluation": int(getattr(settings, "personal_kb_scheduler_trigger_interval_seconds", 300) or 300),
            "stale_knowledge_check": int(getattr(settings, "personal_kb_scheduler_reflection_interval_seconds", 900) or 900),
            "suppression_cleanup": 1800,
            "preference_consolidation": 3600,
            "daily_summary_candidates": 21600,
        }
        return interval_defaults.get(job_name, 600)

    @classmethod
    def _orchestration_lock_timeout_seconds(cls, job_name: str, settings: Any | None = None) -> int:
        cadence_seconds = cls._orchestration_job_interval_seconds(job_name, settings=settings)
        return max(300, cadence_seconds * 2)

    @staticmethod
    def _orchestration_retry_seconds(*, cadence_seconds: int, failure_count: int) -> int:
        base_seconds = max(120, cadence_seconds // 2)
        return min(7200, base_seconds * max(1, failure_count))

    @staticmethod
    def _orchestration_status_message(
        *,
        job_name: str,
        status: str,
        prior: dict[str, Any],
        next_due_at: str | None,
        now: datetime,
        stale_lock: bool,
    ) -> str:
        if stale_lock:
            return f"{job_name} işi önceki stale run nedeniyle yeniden planlandı."
        if status == "running":
            return f"{job_name} şu anda çalışıyor."
        if status == "retry_scheduled":
            error = _compact_text(str(prior.get("last_error") or ""), limit=180)
            if next_due_at:
                return f"{job_name} başarısız oldu; {next_due_at} zamanında yeniden denenecek. {error}".strip()
            return f"{job_name} başarısız oldu; yeniden denenecek. {error}".strip()
        if status == "failed":
            return f"{job_name} son çalışmada başarısız oldu."
        if status == "completed":
            next_due_dt = _iso_to_datetime(next_due_at)
            if next_due_dt is not None:
                due_in_seconds = max(0, int((next_due_dt - now).total_seconds()))
                if due_in_seconds <= 0:
                    return f"{job_name} tekrar çalışmaya hazır."
            return f"{job_name} son çalışmayı tamamladı."
        if status == "skipped":
            return f"{job_name} bu turda atlandı."
        return f"{job_name} durumu: {status or 'idle'}"

    @classmethod
    def _orchestration_next_due_at(cls, *, job_name: str, prior: dict[str, Any], settings: Any | None = None) -> str | None:
        explicit_next_due = _compact_text(str(prior.get("next_due_at") or ""), limit=80)
        if explicit_next_due:
            return explicit_next_due
        last_completed_at = _compact_text(str(prior.get("last_completed_at") or ""), limit=80)
        if not last_completed_at:
            return None
        try:
            completed_dt = datetime.fromisoformat(last_completed_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
        interval_seconds = int(prior.get("cadence_seconds") or cls._orchestration_job_interval_seconds(job_name, settings=settings))
        return (completed_dt + timedelta(seconds=interval_seconds)).isoformat()

    @classmethod
    def _is_orchestration_job_due(cls, *, job_name: str, prior: dict[str, Any], now: datetime, settings: Any | None = None) -> bool:
        next_due_at = cls._orchestration_next_due_at(job_name=job_name, prior=prior, settings=settings)
        if not next_due_at:
            return True
        try:
            next_due_dt = datetime.fromisoformat(next_due_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return True
        return now >= next_due_dt

    def _save_state(self, state: dict[str, Any]) -> None:
        self._write_json(self._state_path(), state)

    def _write_json(self, path: Path, payload: dict[str, Any] | list[Any]) -> None:
        self._write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def _read_text_lossy(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="replace")

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and self._read_text_lossy(path) == content:
            return
        path.write_text(content, encoding="utf-8")

    def _append_log(self, event_type: str, summary: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_scaffold()
        entry = {
            "timestamp": _iso_now(),
            "event_type": event_type,
            "summary": _compact_text(summary, limit=240),
            "details": details or {},
        }
        log_path = self.system_dir / "log.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._render_log_markdown()
        return entry

    def _render_log_markdown(self) -> None:
        entries: list[dict[str, Any]] = []
        log_path = self.system_dir / "log.jsonl"
        if log_path.exists():
            for line in self._read_text_lossy(log_path).splitlines()[-40:]:
                if not line.strip():
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        lines = ["# LOG.md", "", "Son knowledge base olayları:", ""]
        if not entries:
            lines.append("- Kayıt yok.")
        else:
            for entry in reversed(entries):
                lines.append(f"- [{entry.get('timestamp')}] {entry.get('event_type')}: {entry.get('summary')}")
        self._write_text(self.system_dir / "LOG.md", "\n".join(lines).rstrip() + "\n")

    def _render_all(self, state: dict[str, Any]) -> None:
        with self._render_mutex:
            wiki_brain = self._build_wiki_brain(state)
            self._persist_wiki_brain_artifacts(wiki_brain)
            self._write_text(self.system_dir / "AGENTS.md", self._render_agents_markdown())
            self._write_text(self.system_dir / "SCHEMA.md", self._render_schema_markdown())
            self._write_text(self.system_dir / "CONTROL.md", self._render_control_markdown(state))
            self._write_text(self.system_dir / "RULES.md", self._render_rules_markdown())
            self._render_log_markdown()
            self._write_text(self.system_dir / "INDEX.md", self._render_index_markdown(state, wiki_brain=wiki_brain))
            for key, description in PAGE_SPECS.items():
                page = state.get("pages", {}).get(key) or {"title": key.title(), "description": description, "records": []}
                self._write_text(self.wiki_dir / f"{key}.md", self._render_page_markdown(key, page, wiki_brain=wiki_brain))

    def _persist_wiki_brain_artifacts(self, wiki_brain: dict[str, Any]) -> None:
        self._concepts_dir().mkdir(parents=True, exist_ok=True)
        self._write_json(self._wiki_brain_path(), wiki_brain)
        self._write_json(self._wiki_graph_path(), wiki_brain.get("graph") or {})
        self._write_text(self._reports_dir() / "wiki-brain-latest.md", self._render_wiki_brain_markdown(wiki_brain))
        self._write_text(self._concepts_dir() / "INDEX.md", self._render_concepts_index_markdown(wiki_brain))
        desired_files: set[str] = {"INDEX.md"}
        for concept in list(wiki_brain.get("concepts") or []):
            path = Path(str(concept.get("path") or self._concepts_dir() / f"{_slugify(str(concept.get('key') or 'concept'))}.md"))
            desired_files.add(path.name)
            self._write_text(path, self._render_concept_markdown(concept))
        for stale_path in self._concepts_dir().glob("*.md"):
            if stale_path.name in desired_files:
                continue
            stale_path.unlink(missing_ok=True)

    def _load_existing_wiki_brain(self) -> dict[str, Any]:
        path = self._wiki_brain_path()
        if not path.exists():
            return {}
        try:
            payload = json.loads(self._read_text_lossy(path))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _runtime_is_local_like(self) -> bool:
        runtime = self.article_runtime
        if runtime is None:
            return False
        runtime_mode = str(getattr(runtime, "runtime_mode", "") or "").lower()
        provider_type = str(getattr(runtime, "provider_type", "") or "").lower()
        return runtime_mode == "advanced-openclaw" or any(
            token in provider_type for token in ("local", "ollama", "llama", "openclaw")
        )

    def _can_use_llm_for_concept(self, concept: dict[str, Any]) -> bool:
        runtime = self.article_runtime
        if not self.enable_llm_article_authoring or runtime is None or not bool(getattr(runtime, "enabled", False)):
            return False
        sensitivity = str(concept.get("dominant_sensitivity") or "medium")
        exportability = str(concept.get("exportability") or "redaction_required")
        if self._runtime_is_local_like():
            return True
        return sensitivity == "low" and exportability == "cloud_allowed"

    def _concept_source_fingerprint(self, concept: dict[str, Any]) -> str:
        refs = [
            {
                "record_id": item.get("record_id"),
                "updated_at": item.get("updated_at"),
                "summary": item.get("summary"),
                "confidence": item.get("confidence"),
                "priority_score": item.get("priority_score"),
            }
            for item in list(concept.get("record_refs") or [])[:12]
        ]
        return _fingerprint(
            {
                "key": concept.get("key"),
                "summary": concept.get("summary"),
                "record_refs": refs,
                "related": [item.get("key") for item in list(concept.get("related_concepts") or [])[:6]],
            }
        )

    def _deterministic_concept_article_sections(self, concept: dict[str, Any]) -> dict[str, Any]:
        record_type_counts = dict(concept.get("record_type_counts") or {})
        scope_summary = dict(concept.get("scope_summary") or {})
        page_counts = dict(concept.get("page_counts") or {})
        related = list(concept.get("related_concepts") or [])
        relation_targets = dict(concept.get("relation_targets") or {})
        patterns: list[str] = []
        if scope_summary:
            dominant_scope = max(scope_summary, key=scope_summary.get)
            patterns.append(
                f"Baskın kapsam `{dominant_scope}` ve bu kavram {scope_summary.get(dominant_scope)} ayrı kayıtla destekleniyor."
            )
        if page_counts:
            dominant_page = max(page_counts, key=page_counts.get)
            patterns.append(
                f"En yoğun sinyal [`{dominant_page}`]({self.wiki_dir / f'{dominant_page}.md'}) sayfasında görünüyor."
            )
        if record_type_counts:
            dominant_type = max(record_type_counts, key=record_type_counts.get)
            patterns.append(f"Başlıca kayıt tipi `{dominant_type}`.")
        if related:
            patterns.append(
                "En güçlü bağlantılar: "
                + ", ".join(f"`{item.get('title')}`" for item in related[:3] if str(item.get("title") or "").strip())
                + "."
            )
        inferred_insights: list[str] = []
        if float(concept.get("priority_score") or 0.0) >= 0.9:
            inferred_insights.append("Bu kavram yardım sıralamasında yüksek öncelikli ve KB reasoning tarafında önce ele alınmalı.")
        if float(concept.get("confidence") or 0.0) >= 0.78:
            inferred_insights.append("Confidence yüksek olduğu için öneri ve explainability yüzeylerinde doğrudan dayanak olarak kullanılabilir.")
        if relation_targets:
            target_preview = ", ".join(f"`{_humanize_identifier(key)}`" for key in list(relation_targets.keys())[:3])
            inferred_insights.append(f"İlişkisel bağlar {target_preview} çevresinde yoğunlaşıyor.")
        if int(concept.get("backlink_count") or 0) <= 1:
            inferred_insights.append("Tek backlinkli ince bir article; yeni kaynaklarla desteklenmesi faydalı olur.")
        strategy_notes: list[str] = []
        title_text = str(concept.get("title") or "").lower()
        key_text = str(concept.get("key") or "").lower()
        if any(token in title_text or token in key_text for token in ("plan", "planning", "daily", "kapanis", "akşam", "aksam")):
            strategy_notes.append("Akşam ve kapanış odaklı plan önerilerinde bu kavrama öncelik ver.")
        if "communication" in key_text or "ton" in title_text or "style" in key_text:
            strategy_notes.append("Mesaj ve email taslaklarında bu article içindeki ton sinyallerini preview aşamasına yansıt.")
        if "place" in key_text or "location" in key_text or "yer" in title_text:
            strategy_notes.append("Yakındaki yer önerilerinde aynı kategori ve zaman bandı örüntülerini kullan.")
        cross_links = [
            {
                "key": item.get("key"),
                "title": item.get("title"),
                "reason": f"graph score={item.get('score')}",
            }
            for item in related[:6]
        ]
        supporting_records = list(concept.get("record_refs") or [])[:4]
        detailed_explanation = _compact_text(
            " ".join(
                part
                for part in [
                    str(concept.get("summary") or ""),
                    "Bu article, tekrar eden page records üzerinden otomatik derlendi.",
                    "Destek kayıtları: "
                    + "; ".join(
                        f"[{item.get('page_key')}] {item.get('title')}: {item.get('summary')}"
                        for item in supporting_records
                    )
                    if supporting_records
                    else "",
                ]
                if part
            ),
            limit=2200,
        )
        return {
            "summary": _compact_text(str(concept.get("summary") or ""), limit=720),
            "detailed_explanation": detailed_explanation or str(concept.get("summary") or ""),
            "patterns": patterns[:6],
            "inferred_insights": inferred_insights[:6],
            "cross_links": cross_links[:6],
            "strategy_notes": strategy_notes[:4],
        }

    def _author_concept_article_sections(self, concept: dict[str, Any], fallback_sections: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        runtime = self.article_runtime
        if runtime is None:
            return fallback_sections, {"mode": "deterministic_fallback", "reason": "runtime_unavailable"}
        prompt = "\n".join(
            [
                "Sen LawCopilot knowledge system için concept article yazan bir wiki compiler'sın.",
                "Yalnızca verilen kanıtlara dayan. Uydurma bilgi ekleme.",
                "JSON dışında hiçbir şey yazma.",
                "JSON şeması:",
                '{"summary":"...","detailed_explanation":"...","patterns":["..."],"inferred_insights":["..."],"cross_links":[{"key":"...","title":"...","reason":"..."}],"strategy_notes":["..."]}',
                "",
                f"Concept key: {concept.get('key')}",
                f"Title: {concept.get('title')}",
                f"Kind: {concept.get('kind')}",
                f"Summary: {concept.get('summary')}",
                f"Priority score: {concept.get('priority_score')}",
                f"Confidence: {concept.get('confidence')}",
                f"Dominant scope: {max(dict(concept.get('scope_summary') or {'global': 1}), key=dict(concept.get('scope_summary') or {'global': 1}).get)}",
                "Supporting records:",
                *[
                    f"- [{item.get('page_key')}] {item.get('title')}: {item.get('summary')} | confidence={item.get('confidence')}"
                    for item in list(concept.get("record_refs") or [])[:6]
                ],
                "Related concepts:",
                *[
                    f"- {item.get('key')}: {item.get('title')} | score={item.get('score')}"
                    for item in list(concept.get("related_concepts") or [])[:5]
                ],
            ]
        )
        completion = runtime.complete(
            prompt,
            self.runtime_events,
            task="knowledge_article_authoring",
            office_id=self.office_id,
            concept_key=concept.get("key"),
            sensitivity=concept.get("dominant_sensitivity"),
        )
        payload = _parse_json_object_from_text((completion or {}).get("text") if isinstance(completion, dict) else None)
        if not payload:
            return fallback_sections, {"mode": "deterministic_fallback", "reason": "invalid_runtime_payload"}
        sections = {
            "summary": _compact_text(str(payload.get("summary") or fallback_sections.get("summary") or ""), limit=900),
            "detailed_explanation": _compact_text(
                str(payload.get("detailed_explanation") or fallback_sections.get("detailed_explanation") or ""),
                limit=2800,
            ),
            "patterns": [
                _compact_text(str(item), limit=280)
                for item in list(payload.get("patterns") or fallback_sections.get("patterns") or [])[:6]
                if _compact_text(str(item), limit=280)
            ],
            "inferred_insights": [
                _compact_text(str(item), limit=280)
                for item in list(payload.get("inferred_insights") or fallback_sections.get("inferred_insights") or [])[:6]
                if _compact_text(str(item), limit=280)
            ],
            "cross_links": [
                {
                    "key": _compact_text(str(item.get("key") or ""), limit=120),
                    "title": _compact_text(str(item.get("title") or ""), limit=160),
                    "reason": _compact_text(str(item.get("reason") or ""), limit=220),
                }
                for item in list(payload.get("cross_links") or fallback_sections.get("cross_links") or [])[:6]
                if isinstance(item, dict) and str(item.get("title") or "").strip()
            ],
            "strategy_notes": [
                _compact_text(str(item), limit=280)
                for item in list(payload.get("strategy_notes") or fallback_sections.get("strategy_notes") or [])[:4]
                if _compact_text(str(item), limit=280)
            ],
        }
        return sections, {
            "mode": "llm_runtime",
            "provider": (completion or {}).get("provider"),
            "model": (completion or {}).get("model"),
            "runtime_mode": (completion or {}).get("runtime_mode"),
        }

    def _build_wiki_brain(self, state: dict[str, Any]) -> dict[str, Any]:
        previous_brain = self._load_existing_wiki_brain()
        previous_concepts = {
            str(item.get("key") or ""): item
            for item in list((previous_brain.get("concepts") or []))
            if isinstance(item, dict) and str(item.get("key") or "").strip()
        }
        concepts: dict[str, dict[str, Any]] = {}
        concept_edges: Counter[tuple[str, str]] = Counter()
        relation_edges: Counter[tuple[str, str]] = Counter()
        record_backlinks: dict[str, list[dict[str, Any]]] = {}

        for page_key, page in (state.get("pages") or {}).items():
            for record in list((page or {}).get("records") or []):
                if not isinstance(record, dict):
                    continue
                if str(record.get("status") or "active") != "active":
                    continue
                envelope = self._normalized_record_envelope(page_key, record)
                metadata = dict(envelope.get("metadata") or {})
                concept_specs = self._concept_specs_for_record(page_key=page_key, record=record, envelope=envelope)
                if not concept_specs:
                    continue
                concept_keys: list[str] = []
                backlink_payloads: list[dict[str, Any]] = []
                relation_targets: set[str] = set()
                record_ref = f"{page_key}:{record.get('id')}"
                for relation in list(metadata.get("relations") or []):
                    if not isinstance(relation, dict):
                        continue
                    relation_targets.update(_relation_target_candidate_keys(relation.get("target")))
                for spec in concept_specs:
                    concept_key = str(spec.get("key") or "").strip()
                    if not concept_key:
                        continue
                    concept_path = self._concepts_dir() / f"{_slugify(concept_key)}.md"
                    concept = concepts.setdefault(
                        concept_key,
                        {
                            "key": concept_key,
                            "title": str(spec.get("title") or _humanize_identifier(concept_key)),
                            "kind": str(spec.get("kind") or "concept"),
                            "summary_hints": [],
                            "record_refs": [],
                            "source_refs": [],
                            "scope_summary": Counter(),
                            "record_type_counts": Counter(),
                            "page_counts": Counter(),
                            "relation_targets": Counter(),
                            "sensitivity_summary": Counter(),
                            "exportability_summary": Counter(),
                            "shareability_summary": Counter(),
                            "updated_at": None,
                            "path": str(concept_path),
                        },
                    )
                    concept["summary_hints"].append(_compact_text(str(record.get("summary") or record.get("title") or ""), limit=220))
                    concept["record_refs"].append(
                        {
                            "page_key": page_key,
                            "record_id": record.get("id"),
                            "title": record.get("title"),
                            "summary": _compact_text(str(record.get("summary") or ""), limit=220),
                            "scope": envelope.get("scope"),
                            "record_type": envelope.get("record_type"),
                            "path": str(self.wiki_dir / f"{page_key}.md"),
                            "updated_at": record.get("updated_at"),
                            "confidence": record.get("confidence"),
                            "sensitivity": envelope.get("sensitivity"),
                            "exportability": envelope.get("exportability"),
                            "shareability": metadata.get("shareability"),
                            "priority_score": metadata.get("priority_score"),
                            "importance_score": metadata.get("importance_score"),
                            "frequency_weight": metadata.get("frequency_weight"),
                            "decay_score": metadata.get("decay_score"),
                        }
                    )
                    concept["source_refs"].extend([str(item) for item in list(record.get("source_refs") or []) if str(item).strip()])
                    concept["scope_summary"][str(envelope.get("scope") or "global")] += 1
                    concept["record_type_counts"][str(envelope.get("record_type") or "source")] += 1
                    concept["page_counts"][page_key] += 1
                    concept["sensitivity_summary"][str(envelope.get("sensitivity") or "medium")] += 1
                    concept["exportability_summary"][str(envelope.get("exportability") or "redaction_required")] += 1
                    concept["shareability_summary"][str(metadata.get("shareability") or "shareable")] += 1
                    current_updated_at = _iso_to_datetime(str(record.get("updated_at") or ""))
                    previous_updated_at = _iso_to_datetime(str(concept.get("updated_at") or ""))
                    if current_updated_at and (previous_updated_at is None or current_updated_at > previous_updated_at):
                        concept["updated_at"] = current_updated_at.isoformat()
                    for relation in list(metadata.get("relations") or []):
                        if not isinstance(relation, dict):
                            continue
                        target = str(relation.get("target") or "").strip()
                        if target:
                            concept["relation_targets"][target] += 1
                    concept_keys.append(concept_key)
                    backlink_payloads.append(
                        {
                            "key": concept_key,
                            "title": concept["title"],
                            "path": str(concept_path),
                        }
                    )
                if backlink_payloads:
                    record_backlinks[record_ref] = backlink_payloads
                unique_concept_keys = sorted(set(concept_keys))
                for left, right in combinations(unique_concept_keys, 2):
                    concept_edges[(left, right)] += 1
                for left in unique_concept_keys:
                    for target in relation_targets:
                        if not target or target == left:
                            continue
                        edge = tuple(sorted((left, target)))
                        relation_edges[edge] += 1

        serialized_concepts: list[dict[str, Any]] = []
        graph_nodes: list[dict[str, Any]] = []
        graph_edges: list[dict[str, Any]] = []
        adjacency: dict[str, Counter[str]] = {}
        concept_keys_available = set(concepts)
        combined_edges = {
            edge
            for edge in set(concept_edges)
            .union(set(relation_edges))
            if edge[0] in concept_keys_available and edge[1] in concept_keys_available
        }
        for left, right in sorted(combined_edges):
            cooccurrence_weight = int(concept_edges.get((left, right), 0))
            relation_weight = int(relation_edges.get((left, right), 0))
            score = round((cooccurrence_weight * 1.0) + (relation_weight * 1.35), 2)
            adjacency.setdefault(left, Counter())[right] += score
            adjacency.setdefault(right, Counter())[left] += score
            graph_edges.append(
                {
                    "source": left,
                    "target": right,
                    "relation_type": "related_to",
                    "cooccurrence_weight": cooccurrence_weight,
                    "relation_weight": relation_weight,
                    "score": score,
                }
            )
        for concept_key, payload in concepts.items():
            record_refs = list(payload.get("record_refs") or [])
            record_type_counts = Counter(payload.get("record_type_counts") or {})
            scope_summary = Counter(payload.get("scope_summary") or {})
            sensitivity_summary = Counter(payload.get("sensitivity_summary") or {})
            exportability_summary = Counter(payload.get("exportability_summary") or {})
            shareability_summary = Counter(payload.get("shareability_summary") or {})
            source_refs = sorted(set(payload.get("source_refs") or []))
            related_concepts = [
                {
                    "key": related_key,
                    "title": concepts.get(related_key, {}).get("title") or _humanize_identifier(related_key),
                    "path": str(self._concepts_dir() / f"{_slugify(related_key)}.md"),
                    "score": round(weight, 2),
                    "cooccurrence_weight": int(concept_edges.get(tuple(sorted((concept_key, related_key))), 0)),
                    "relation_weight": int(relation_edges.get(tuple(sorted((concept_key, related_key))), 0)),
                }
                for related_key, weight in adjacency.get(concept_key, Counter()).most_common(6)
            ]
            summary_hints = [item for item in list(dict.fromkeys(payload.get("summary_hints") or [])) if item][:3]
            dominant_scope = scope_summary.most_common(1)[0][0] if scope_summary else "global"
            dominant_type = record_type_counts.most_common(1)[0][0] if record_type_counts else "source"
            dominant_sensitivity = sensitivity_summary.most_common(1)[0][0] if sensitivity_summary else "medium"
            exportability = exportability_summary.most_common(1)[0][0] if exportability_summary else "redaction_required"
            shareability = shareability_summary.most_common(1)[0][0] if shareability_summary else "shareable"
            concept_summary = _compact_text(
                " ".join(
                    part
                    for part in [
                        f"{payload.get('title')} konusu {len(record_refs)} bilgi kaydında tekrar ediyor.",
                        f"Baskın kapsam {dominant_scope}.",
                        f"Başlıca kayıt tipi {dominant_type}.",
                        " ".join(summary_hints[:2]),
                    ]
                    if part
                ),
                limit=720,
            )
            confidence_values = [float(item.get("confidence") or 0.0) for item in record_refs if item.get("confidence") is not None]
            priority_values = [float(item.get("priority_score") or 0.0) for item in record_refs]
            importance_values = [float(item.get("importance_score") or 0.0) for item in record_refs]
            decay_values = [float(item.get("decay_score") or 0.0) for item in record_refs]
            frequency_values = [float(item.get("frequency_weight") or 0.0) for item in record_refs]
            confidence = round(sum(confidence_values) / max(len(confidence_values), 1), 2) if confidence_values else 0.6
            priority_score = round(max(priority_values) if priority_values else (confidence * 0.8), 4)
            importance_score = round(sum(importance_values) / max(len(importance_values), 1), 4) if importance_values else round(confidence * 0.85, 4)
            decay_score = round(sum(decay_values) / max(len(decay_values), 1), 4) if decay_values else 0.0
            frequency_weight = round(sum(frequency_values) / max(len(frequency_values), 1), 4) if frequency_values else 0.0
            quality_flags: list[str] = []
            if confidence < 0.62:
                quality_flags.append("low_confidence")
            if int(len(record_refs)) <= 1:
                quality_flags.append("thin_article")
            if decay_score >= 0.42:
                quality_flags.append("stale_support")
            serialized_concepts.append(
                {
                    "key": concept_key,
                    "title": payload.get("title"),
                    "kind": payload.get("kind"),
                    "summary": concept_summary,
                    "path": payload.get("path"),
                    "updated_at": payload.get("updated_at"),
                    "record_refs": record_refs[:12],
                    "backlink_count": len(record_refs),
                    "scope_summary": dict(scope_summary),
                    "record_type_counts": dict(record_type_counts),
                    "page_counts": dict(Counter(payload.get("page_counts") or {})),
                    "source_refs": source_refs[:12],
                    "related_concepts": related_concepts,
                    "relation_targets": dict(Counter(payload.get("relation_targets") or {})),
                    "confidence": confidence,
                    "priority_score": priority_score,
                    "importance_score": importance_score,
                    "decay_score": decay_score,
                    "frequency_weight": frequency_weight,
                    "dominant_sensitivity": dominant_sensitivity,
                    "exportability": exportability,
                    "shareability": shareability,
                    "quality_flags": quality_flags,
                }
            )
            graph_nodes.append(
                {
                    "id": concept_key,
                    "title": payload.get("title"),
                    "kind": payload.get("kind"),
                    "scope_summary": dict(scope_summary),
                    "record_type_counts": dict(record_type_counts),
                    "backlink_count": len(record_refs),
                    "confidence": confidence,
                    "priority_score": priority_score,
                }
            )
        serialized_concepts.sort(
            key=lambda item: (
                -float(item.get("priority_score") or 0.0),
                -int(item.get("backlink_count") or 0),
                -float(item.get("confidence") or 0.0),
                str(item.get("title") or ""),
            )
        )
        llm_budget = 0
        authoring_modes: Counter[str] = Counter()
        strategy_candidates: list[dict[str, Any]] = []
        for concept in serialized_concepts:
            source_fingerprint = self._concept_source_fingerprint(concept)
            previous = previous_concepts.get(str(concept.get("key") or "")) or {}
            fallback_sections = self._deterministic_concept_article_sections(concept)
            sections = fallback_sections
            authoring = {"mode": "deterministic_fallback", "reason": "default"}
            if previous and str(previous.get("source_fingerprint") or "") == source_fingerprint and isinstance(previous.get("article_sections"), dict):
                sections = dict(previous.get("article_sections") or fallback_sections)
                authoring = dict(previous.get("authoring") or {"mode": "cached"})
                authoring.setdefault("mode", "cached")
            elif self._can_use_llm_for_concept(concept) and llm_budget < self.llm_article_limit:
                authored_sections, authoring = self._author_concept_article_sections(concept, fallback_sections)
                sections = authored_sections or fallback_sections
                llm_budget += 1
            concept["source_fingerprint"] = source_fingerprint
            concept["article_sections"] = sections
            concept["authoring"] = authoring
            authoring_modes[str(authoring.get("mode") or "unknown")] += 1
            if list(sections.get("strategy_notes") or []):
                strategy_candidates.append(
                    {
                        "concept_key": concept.get("key"),
                        "title": concept.get("title"),
                        "priority_score": concept.get("priority_score"),
                        "strategy_notes": list(sections.get("strategy_notes") or [])[:3],
                    }
                )
        topic_clusters = []
        clusters_by_kind: dict[str, list[dict[str, Any]]] = {}
        for concept in serialized_concepts:
            clusters_by_kind.setdefault(str(concept.get("kind") or "concept"), []).append(concept)
        for kind, items in sorted(clusters_by_kind.items()):
            topic_clusters.append(
                {
                    "kind": kind,
                    "count": len(items),
                    "titles": [str(item.get("title") or "") for item in items[:8]],
                    "average_priority": round(
                        sum(float(item.get("priority_score") or 0.0) for item in items) / max(len(items), 1),
                        4,
                    ),
                }
            )
        return {
            "generated_at": _iso_now(),
            "summary": {
                "concept_count": len(serialized_concepts),
                "article_count": len(serialized_concepts),
                "graph_edges": len(graph_edges),
                "cluster_count": len(topic_clusters),
                "source_backlinks": sum(int(item.get("backlink_count") or 0) for item in serialized_concepts),
                "high_priority_concepts": sum(1 for item in serialized_concepts if float(item.get("priority_score") or 0.0) >= 0.9),
                "strategy_candidate_count": len(strategy_candidates),
                "authoring_modes": dict(authoring_modes),
            },
            "concepts": serialized_concepts,
            "topic_clusters": topic_clusters,
            "strategy_candidates": strategy_candidates[:12],
            "graph": {
                "backend": "file_graph_v2",
                "nodes": graph_nodes,
                "edges": graph_edges,
            },
            "record_backlinks": record_backlinks,
        }

    def _concept_specs_for_record(self, *, page_key: str, record: dict[str, Any], envelope: dict[str, Any]) -> list[dict[str, Any]]:
        metadata = dict(envelope.get("metadata") or {})
        record_type = str(envelope.get("record_type") or PAGE_RECORD_TYPES.get(page_key, "source"))
        title = _compact_text(str(record.get("title") or ""), limit=160)
        logical_key = str(record.get("key") or "").strip()
        concept_specs: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(kind: str, raw_value: str | None, display_title: str | None = None) -> None:
            value = str(raw_value or "").strip()
            if not value:
                return
            concept_key = f"{kind}:{_slugify(value)}"
            if concept_key in seen:
                return
            seen.add(concept_key)
            concept_specs.append(
                {
                    "key": concept_key,
                    "title": _compact_text(display_title or _humanize_identifier(value), limit=160),
                    "kind": kind,
                }
            )

        add("page", page_key, display_title=_humanize_identifier(page_key))
        add("record_type", record_type, display_title=_humanize_identifier(record_type))
        add("field", metadata.get("field"), display_title=_humanize_identifier(metadata.get("field")))
        add("topic", metadata.get("topic"), display_title=_humanize_identifier(metadata.get("topic")))
        add(
            "recommendation_kind",
            metadata.get("recommendation_kind"),
            display_title=_humanize_identifier(metadata.get("recommendation_kind")),
        )
        add("place_category", metadata.get("category") or metadata.get("place_category"), display_title=_humanize_identifier(metadata.get("category") or metadata.get("place_category")))
        if metadata.get("matter_id"):
            add("project", f"matter-{metadata.get('matter_id')}", display_title=f"Matter {metadata.get('matter_id')}")
        if page_key == "contacts":
            add("person", title or logical_key, display_title=title or _humanize_identifier(logical_key))
        elif page_key == "places":
            add("place", title or logical_key, display_title=title or _humanize_identifier(logical_key))
        elif page_key in {"projects", "legal"}:
            anchor = title or logical_key
            if anchor:
                add("project", anchor, display_title=anchor)
        elif page_key in {"preferences", "persona", "routines"} and (title or logical_key):
            add("topic", logical_key or title, display_title=title or _humanize_identifier(logical_key))
        return concept_specs

    def _render_wiki_brain_markdown(self, wiki_brain: dict[str, Any]) -> str:
        summary = dict(wiki_brain.get("summary") or {})
        lines = [
            "# Wiki Brain",
            "",
            f"- Generated at: {wiki_brain.get('generated_at')}",
            f"- Concepts: {summary.get('concept_count', 0)}",
            f"- Articles: {summary.get('article_count', 0)}",
            f"- Graph edges: {summary.get('graph_edges', 0)}",
            f"- Topic clusters: {summary.get('cluster_count', 0)}",
            f"- High priority concepts: {summary.get('high_priority_concepts', 0)}",
            f"- Strategy candidates: {summary.get('strategy_candidate_count', 0)}",
            "",
            "## Top Concepts",
        ]
        concepts = list(wiki_brain.get("concepts") or [])
        if not concepts:
            lines.append("- None")
        else:
            for concept in concepts[:10]:
                lines.append(
                    f"- {concept.get('title')} ({concept.get('kind')}): {concept.get('summary')} | priority={concept.get('priority_score')} | authoring={((concept.get('authoring') or {}).get('mode') or 'unknown')}"
                )
        lines.extend(["", "## Topic Clusters"])
        clusters = list(wiki_brain.get("topic_clusters") or [])
        if not clusters:
            lines.append("- None")
        else:
            for cluster in clusters:
                titles = ", ".join(list(cluster.get("titles") or [])[:5]) or "None"
                lines.append(f"- {cluster.get('kind')}: {cluster.get('count')} concept -> {titles} | avg_priority={cluster.get('average_priority')}")
        lines.extend(["", "## Strategy Candidates"])
        strategies = list(wiki_brain.get("strategy_candidates") or [])
        if not strategies:
            lines.append("- None")
        else:
            for item in strategies[:8]:
                notes = "; ".join(list(item.get("strategy_notes") or [])[:2]) or "No notes"
                lines.append(f"- {item.get('title')}: {notes}")
        return "\n".join(lines).rstrip() + "\n"

    def _render_concepts_index_markdown(self, wiki_brain: dict[str, Any]) -> str:
        lines = [
            "# Concept Index",
            "",
            "Derlenmiş knowledge article sayfaları:",
            "",
        ]
        concepts = list(wiki_brain.get("concepts") or [])
        if not concepts:
            lines.append("- Henüz concept article yok.")
            return "\n".join(lines).rstrip() + "\n"
        for concept in concepts:
            rel_path = Path(str(concept.get("path") or "")).name
            lines.append(
                f"- [{concept.get('title')}](./{rel_path}) | kind={concept.get('kind')} | backlinks={concept.get('backlink_count')} | priority={concept.get('priority_score')} | authoring={((concept.get('authoring') or {}).get('mode') or 'unknown')}"
            )
        return "\n".join(lines).rstrip() + "\n"

    def _render_concept_markdown(self, concept: dict[str, Any]) -> str:
        state = self._load_state()
        article_sections = dict(concept.get("article_sections") or {})
        authoring = dict(concept.get("authoring") or {})
        claim_bindings = self._concept_claim_bindings(concept, state=state)
        article_claim_bindings = self._concept_article_claim_bindings(concept, claim_bindings=claim_bindings)
        lines = [
            f"# {concept.get('title')}",
            "",
            f"- Key: {concept.get('key')}",
            f"- Kind: {concept.get('kind')}",
            f"- Confidence: {concept.get('confidence')}",
            f"- Priority: {concept.get('priority_score')}",
            f"- Importance: {concept.get('importance_score')}",
            f"- Decay: {concept.get('decay_score')}",
            f"- Updated at: {concept.get('updated_at') or 'unknown'}",
            f"- Backlink count: {concept.get('backlink_count') or 0}",
            f"- Scope shareability: {concept.get('shareability') or 'shareable'}",
            f"- Sensitivity: {concept.get('dominant_sensitivity') or 'medium'}",
            f"- Authoring mode: {authoring.get('mode') or 'deterministic_fallback'}",
            "",
            "## Summary",
            str(article_sections.get("summary") or concept.get("summary") or "Henüz özet yok."),
            "",
            "## Detailed Explanation",
            str(article_sections.get("detailed_explanation") or concept.get("summary") or "Henüz açıklama yok."),
            "",
            "## Scope Summary",
        ]
        scope_summary = dict(concept.get("scope_summary") or {})
        if scope_summary:
            for scope, count in scope_summary.items():
                lines.append(f"- {scope}: {count}")
        else:
            lines.append("- None")
        lines.extend(["", "## Patterns"])
        patterns = list(article_sections.get("patterns") or [])
        if patterns:
            for item in patterns:
                lines.append(f"- {item}")
        else:
            lines.append("- None")
        lines.extend(["", "## Inferred Insights"])
        inferred = list(article_sections.get("inferred_insights") or [])
        if inferred:
            for item in inferred:
                lines.append(f"- {item}")
        else:
            lines.append("- None")
        lines.extend(["", "## Related Concepts"])
        related = list(concept.get("related_concepts") or [])
        if related:
            for item in related:
                rel_name = Path(str(item.get("path") or "")).name
                lines.append(
                    f"- [{item.get('title')}](./{rel_name}) | score={item.get('score')} | cooccurrence={item.get('cooccurrence_weight')} | relation={item.get('relation_weight')}"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Cross Links"])
        cross_links = list(article_sections.get("cross_links") or [])
        if cross_links:
            for item in cross_links:
                key = str(item.get("key") or "")
                title = str(item.get("title") or key or "Unknown")
                lines.append(f"- `{key}` {title}: {item.get('reason')}")
        else:
            lines.append("- None")
        lines.extend(["", "## Strategy Notes"])
        strategy_notes = list(article_sections.get("strategy_notes") or [])
        if strategy_notes:
            for item in strategy_notes:
                lines.append(f"- {item}")
        else:
            lines.append("- None")
        lines.extend(["", "## Supporting Records"])
        record_refs = list(concept.get("record_refs") or [])
        if not record_refs:
            lines.append("- None")
        else:
            for item in record_refs[:10]:
                page_name = str(item.get("page_key") or "")
                line = (
                    f"- [{page_name}] {item.get('title')}: {item.get('summary')} | "
                    f"scope={item.get('scope')} | type={item.get('record_type')} | priority={item.get('priority_score')}"
                )
                linked_key = page_name.strip()
                record_id = str((item or {}).get("record_id") or "").strip()
                if linked_key and record_id:
                    page = (state.get("pages") or {}).get(linked_key)
                    if isinstance(page, dict):
                        record = next(
                            (
                                candidate
                                for candidate in list(page.get("records") or [])
                                if isinstance(candidate, dict) and str(candidate.get("id") or "").strip() == record_id
                            ),
                            None,
                        )
                        if isinstance(record, dict):
                            envelope = self._normalized_record_envelope(linked_key, record)
                            epistemic = self._epistemic_resolution_for_record(linked_key, record, envelope)
                            claim_binding = self._claim_binding_for_record(
                                linked_key,
                                record,
                                envelope,
                                epistemic=epistemic,
                            )
                            if claim_binding:
                                line += (
                                    f" | claim={claim_binding.get('subject_key') or 'unknown'}."
                                    f"{claim_binding.get('predicate') or 'unknown'}"
                                    f" ({claim_binding.get('status') or 'unknown'})"
                                )
                                if str(claim_binding.get("support_strength") or "").strip():
                                    line += f" | support={claim_binding.get('support_strength')}"
                                claim_refs: list[str] = []
                                current_claim_id = str(claim_binding.get("current_claim_id") or "").strip()
                                if current_claim_id:
                                    claim_refs.append(f"current={current_claim_id}")
                                for label, field in (
                                    ("supporting", "supporting_claim_ids"),
                                    ("source", "source_claim_ids"),
                                    ("derived", "derived_from_claim_ids"),
                                ):
                                    values = [str(value).strip() for value in list(claim_binding.get(field) or []) if str(value).strip()]
                                    if values:
                                        claim_refs.append(f"{label}={', '.join(values[:4])}")
                                if claim_refs:
                                    line += f" | refs={' ; '.join(claim_refs)}"
                lines.append(line)
        lines.extend(["", "## Claim Sentence Bindings"])
        if not article_claim_bindings:
            lines.append("- None")
        else:
            for item in article_claim_bindings[:16]:
                refs = ", ".join(list(item.get("claim_ids") or [])[:4]) or "none"
                lines.append(
                    f"- [{item.get('section')}] {item.get('text')} | claims={refs}"
                )
        return "\n".join(lines).rstrip() + "\n"

    def _concept_claim_bindings(self, concept: dict[str, Any], *, state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        resolved_state = state or self._load_state()
        claim_bindings: list[dict[str, Any]] = []
        for item in list(concept.get("record_refs") or []):
            linked_key = str((item or {}).get("page_key") or "").strip()
            record_id = str((item or {}).get("record_id") or "").strip()
            if not linked_key or not record_id:
                continue
            page = (resolved_state.get("pages") or {}).get(linked_key)
            if not isinstance(page, dict):
                continue
            record = next(
                (
                    candidate
                    for candidate in list(page.get("records") or [])
                    if isinstance(candidate, dict) and str(candidate.get("id") or "").strip() == record_id
                ),
                None,
            )
            if not isinstance(record, dict):
                continue
            envelope = self._normalized_record_envelope(linked_key, record)
            epistemic = self._epistemic_resolution_for_record(linked_key, record, envelope)
            claim_binding = self._claim_binding_for_record(linked_key, record, envelope, epistemic=epistemic)
            if claim_binding:
                claim_bindings.append(claim_binding)
        claim_bindings.sort(
            key=lambda item: (
                {"current": 0, "contested": 1, "unknown": 2}.get(str(item.get("status") or "").strip().lower(), 3),
                {"grounded": 0, "supported": 1, "thin": 2, "contaminated": 3}.get(str(item.get("support_strength") or "").strip().lower(), 4),
                str(item.get("predicate") or ""),
            )
        )
        return claim_bindings

    def _concept_article_claim_bindings(
        self,
        concept: dict[str, Any],
        *,
        claim_bindings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not claim_bindings:
            return []
        top_bindings = [item for item in claim_bindings if str(item.get("current_claim_id") or "").strip()]
        if not top_bindings:
            return []
        top_bindings = top_bindings[:4]
        article_sections = dict(concept.get("article_sections") or {})
        entries: list[dict[str, Any]] = []

        def add_entry(section: str, text: str) -> None:
            normalized_text = _compact_text(str(text or "").strip(), limit=520)
            if not normalized_text:
                return
            entries.append(
                {
                    "section": section,
                    "text": normalized_text,
                    "claim_ids": [str(item.get("current_claim_id") or "").strip() for item in top_bindings if str(item.get("current_claim_id") or "").strip()],
                    "subjects": [str(item.get("subject_key") or "").strip() for item in top_bindings if str(item.get("subject_key") or "").strip()],
                    "predicates": [str(item.get("predicate") or "").strip() for item in top_bindings if str(item.get("predicate") or "").strip()],
                    "support_strengths": [str(item.get("support_strength") or "").strip() for item in top_bindings if str(item.get("support_strength") or "").strip()],
                }
            )

        add_entry("summary", str(article_sections.get("summary") or concept.get("summary") or ""))
        add_entry("detailed_explanation", str(article_sections.get("detailed_explanation") or concept.get("summary") or ""))
        for item in list(article_sections.get("patterns") or [])[:4]:
            add_entry("patterns", str(item))
        for item in list(article_sections.get("inferred_insights") or [])[:4]:
            add_entry("inferred_insights", str(item))
        for item in list(article_sections.get("strategy_notes") or [])[:4]:
            add_entry("strategy_notes", str(item))
        for item in list(article_sections.get("cross_links") or [])[:4]:
            if isinstance(item, dict):
                add_entry("cross_links", f"{item.get('title') or item.get('key')}: {item.get('reason') or ''}")
        return entries

    def _page_article_claim_bindings(
        self,
        page_key: str,
        page: dict[str, Any],
        *,
        claim_bindings: list[dict[str, Any]],
        rendered_markdown: str,
    ) -> list[dict[str, Any]]:
        if not claim_bindings:
            return []
        bindings_by_record = {
            str(item.get("record_id") or "").strip(): item
            for item in claim_bindings
            if isinstance(item, dict) and str(item.get("record_id") or "").strip()
        }
        if not bindings_by_record:
            return []
        entries: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        for record in sorted(
            [item for item in list(page.get("records") or []) if isinstance(item, dict)],
            key=lambda item: (str(item.get("status") or "active") != "active", str(item.get("updated_at") or "")),
        ):
            record_id = str(record.get("id") or "").strip()
            if not record_id:
                continue
            claim_binding = bindings_by_record.get(record_id)
            if not claim_binding:
                continue
            current_claim_id = str(claim_binding.get("current_claim_id") or "").strip()
            summary_text = _compact_text(str(record.get("summary") or "").strip(), limit=520)
            if not current_claim_id or not summary_text:
                continue
            section = str(record.get("title") or record_id).strip() or record_id
            section_key = (section, current_claim_id)
            if section_key in seen_keys:
                continue
            seen_keys.add(section_key)
            anchor_text = f"- Summary: {summary_text}"
            offset_start = rendered_markdown.find(anchor_text)
            anchor = anchor_text
            if offset_start < 0:
                offset_start = rendered_markdown.find(summary_text)
                anchor = summary_text
            offset_end = (offset_start + len(anchor)) if offset_start >= 0 else None
            entries.append(
                {
                    "section": section,
                    "anchor": anchor,
                    "offset_start": offset_start if offset_start >= 0 else None,
                    "offset_end": offset_end,
                    "text": summary_text,
                    "claim_ids": [current_claim_id],
                    "subjects": [str(claim_binding.get("subject_key") or "").strip()] if str(claim_binding.get("subject_key") or "").strip() else [],
                    "predicates": [str(claim_binding.get("predicate") or "").strip()] if str(claim_binding.get("predicate") or "").strip() else [],
                    "support_strengths": [str(claim_binding.get("support_strength") or "").strip()] if str(claim_binding.get("support_strength") or "").strip() else [],
                }
            )
        return entries

    def _render_agents_markdown(self) -> str:
        lines = [
            "# AGENTS.md",
            "",
            "Bu klasör LawCopilot'un personal operating assistant memory katmanıdır.",
            "",
            "## Rol Ayrımı",
            "- `ingest_agent`: ham kaynağı immutable raw katmanına yazar, normalize eder ve compile işini tetikler.",
            "- `wiki_maintainer`: wiki sayfalarını günceller, superseded ve contradiction işaretlerini korur.",
            "- `reflection_agent`: health check üretir, stale/orphan/drift bulgularını raporlar.",
            "- `wiki_compiler`: active records üzerinden concept article, topic cluster ve backlink graph üretir.",
            "- `knowledge_synthesizer`: feedback, trigger history ve repeated patterns üzerinden yeni insight kayıtları türetir.",
            "- `recommender_agent`: relevance gating ve frequency control ile explainable öneri üretir.",
            "- `trigger_engine`: zaman, takvim, yükümlülük ve konum bağlamıyla proactive suggest-only trigger üretir.",
            "- `action_agent`: suggest-only hook çıktıları üretir; kritik aksiyonları otomatik yürütmez.",
            "- `safety_policy_agent`: aksiyon risk seviyesi, confirmation ihtiyacı ve never-auto sınırını tanımlar.",
            "",
            "## Çalışma İlkeleri",
            "- Raw katman immutable source of truth olarak korunur.",
            "- Compiled wiki kayıtlarında `confidence`, `source_refs`, `updated_at` alanları zorunludur.",
            "- Çelişen kayıt bulunduğunda eski kayıt `superseded` olur; yeni kayıt aktifleşir.",
            "- Para harcama, hukuki bağlayıcı beyan ve geri alınamaz dış aksiyonlar otomatik yapılmaz.",
            "- Dini/kültürel hassasiyetler yalnız açık sinyal veya açık izin varsa öneri bağlamına alınır.",
        ]
        return "\n".join(lines).rstrip() + "\n"

    def _render_control_markdown(self, state: dict[str, Any]) -> str:
        pages = dict(state.get("pages") or {})
        page_counts = {
            key: len(list((page or {}).get("records") or []))
            for key, page in pages.items()
            if isinstance(page, dict)
        }
        location_context = dict(state.get("location_context") or {})
        connector_sync = dict(state.get("connector_sync") or {})
        orchestration = dict(state.get("orchestration") or {})
        jobs = dict(orchestration.get("jobs") or {})
        lines = [
            "# CONTROL.md",
            "",
            "Bu dosya LawCopilot personal knowledge base için merkezi çalışma kontratını özetler.",
            "",
            "## Kanonik Kaynaklar",
            "- Asistan kimliği ve rolü: runtime profile + workspace/IDENTITY.md",
            "- Kullanıcı kimliği ve kalıcı tercihler: user profile + workspace/USER.md",
            "- Uzun vadeli açıklanabilir kayıtlar: wiki/*.md sayfaları",
            "- Concept/article ve graph katmanı: wiki/concepts/*.md + system/normalized/wiki-brain.json",
            "- Connector ve orchestration durumu: system/state.json içindeki connector_sync ve orchestration bölümleri",
            "",
            "## Aksiyon Sırası",
            "1. Önce kimlik, profil ve bağlam kaynaklarını topla.",
            "2. Sonra wiki kayıtları ve concept article katmanıyla açıklanabilir context kur.",
            "3. Ardından düşük riskli araçlar ve öneri mekanizmasını kullan.",
            "4. Dış aksiyon gerekiyorsa taslak + onay akışında kal.",
            "",
            "## Mevcut Durum Özeti",
            f"- Page sayısı: {len(page_counts)}",
            f"- Toplam kayıt: {sum(page_counts.values())}",
            f"- Decision record: {len(list(state.get('decision_records') or []))}",
            f"- Recommendation history: {len(list(state.get('recommendation_history') or []))}",
            f"- Trigger history: {len(list(state.get('trigger_history') or []))}",
            f"- Connector checkpoint sayısı: {len(dict(connector_sync.get('checkpoints') or {}))}",
            f"- Orchestration job sayısı: {len(jobs)}",
            f"- Güncel konum var mı: {'Evet' if bool(location_context.get('current_place')) else 'Hayır'}",
            "",
            "## Page Dağılımı",
        ]
        if page_counts:
            for key, count in sorted(page_counts.items()):
                lines.append(f"- {key}: {count}")
        else:
            lines.append("- Henüz kayıt yok.")
        lines.extend(
            [
                "",
                "## Güvenlik Postürü",
                "- Raw katman immutable kabul edilir.",
                "- Çelişen bilgi bulunduğunda eski kayıt superseded edilir.",
                "- Para harcama, hukuki bağlayıcı taahhüt ve geri alınamaz dış aksiyonlar otomatik yürütülmez.",
                "- Dini, kültürel veya yaşam tarzı hassasiyetleri yalnız açık sinyal ya da kayıt varsa öneri mantığına girer.",
                "",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    def _render_schema_markdown(self) -> str:
        lines = [
            "# SCHEMA.md",
            "",
            "## Klasörler",
            "- `raw/`: immutable ham veri kayıtları",
            "- `wiki/`: derlenmiş markdown knowledge sayfaları",
            "- `wiki/concepts/`: concept-based knowledge article sayfaları",
            "- `wiki/decision-records/`: explainable karar kayıtları",
            "- `system/normalized/`: derive edilmiş normalize kayıtları",
            "- `system/reports/`: reflection ve health raporları",
            "- `system/normalized/wiki-brain.json`: concept, backlink ve graph özeti",
            "- `system/state.json`: trigger history, location context ve orchestration state",
            "",
            "## Page Record Şeması",
            "- `id`: stabil kayıt kimliği",
            "- `key`: kavramsal mantıksal anahtar",
            "- `title`: kısa başlık",
            "- `summary`: derlenmiş bilgi",
            "- `confidence`: 0-1 arası güven değeri",
            "- `status`: `active` veya `superseded`",
            "- `source_refs`: ham veya türetilmiş kaynak dosya yolları",
            "- `signals`: hangi sinyallerle oluştuğu",
            "- `updated_at`: ISO timestamp",
            "- `metadata.record_type`: typed entity / record sınıfı",
            "- `metadata.scope`: personal/professional/project/global ayrımı",
            "- `metadata.sensitivity`: low/medium/high/restricted",
            "- `metadata.exportability`: local_only/redaction_required/cloud_allowed",
            "- `metadata.model_routing_hint`: local_only/prefer_local/redaction_required/cloud_allowed",
            "- `metadata.relations`: typed relation ipuçları",
            "",
            "## Wiki Brain",
            "- Active record'lar concept/article sayfalarına derlenir",
            "- Article'lar backlink, related concept ve scope summary taşır",
            "- Graph node'ları concept, edge'leri co-occurrence + typed relation etkisini taşır",
            "- Knowledge synthesis döngüsü yeni insight ve pattern kayıtları üretir",
            "",
            "## Recommendation Şeması",
            "- `suggestion`",
            "- `why_this`",
            "- `confidence`",
            "- `requires_confirmation`",
            "- `source_basis`",
            "- `next_actions`",
            "- `risk_level`",
            "",
            "## Trigger Şeması",
            "- `trigger_type`",
            "- `why_now`",
            "- `why_this_user`",
            "- `confidence`",
            "- `urgency`",
            "- `scope`",
            "- `recommended_action`",
            "- `suppression_reason`",
            "",
            "## Knowledge Synthesis Şeması",
            "- `insight_type`",
            "- `summary`",
            "- `source_basis`",
            "- `confidence`",
            "- `target_page`",
            "- `target_record_type`",
        ]
        return "\n".join(lines).rstrip() + "\n"

    def _render_rules_markdown(self) -> str:
        lines = [
            "# RULES.md",
            "",
            "## Ingest Kuralları",
            "- Önce raw kaydı yaz.",
            "- Sonra normalize et ve target page setini belirle.",
            "- Wiki güncellemesi yaparken kaynak referanslarını sakla.",
            "- Aynı key için farklı aktif özet gelirse eski kaydı supersede et ve contradiction logla.",
            "",
            "## Recommendation Kuralları",
            "- Confidence 0.55 altındaysa öneriyi bastır veya dili yumuşat.",
            "- Aynı öneri türünü cooldown süresi dolmadan tekrar üretme.",
            "- `Level B` ve üstü aksiyonlarda `requires_confirmation=true` zorunlu.",
            "- `Level D` aksiyonlar never-auto olarak işaretlenir.",
            "- Kayıtlar scope-aware tutulur; personal ve professional context ayrıştırılır.",
            "- `high` ve `restricted` sensitivity kayıtlarında local-first routing ipucu korunur.",
            "- Değerli assistant output'ları file-back ile knowledge record'a dönüştürülür.",
            "- Her render turunda concept article ve backlink index yeniden derlenir.",
            "",
            "## Reflection Kuralları",
            "- stale knowledge",
            "- orphan pages",
            "- schema drift",
            "- repeated rejected recommendation",
            "- source/page mismatch",
            "- proactive trigger spamini cooldown ve suppression ile engelle",
            "- knowledge gaps, research topics ve potential wiki pages üret",
        ]
        return "\n".join(lines).rstrip() + "\n"

    def _render_index_markdown(self, state: dict[str, Any], *, wiki_brain: dict[str, Any] | None = None) -> str:
        raw_count = len(_list_files(self.raw_dir, ".json"))
        wiki_summary = dict((wiki_brain or {}).get("summary") or {})
        lines = [
            "# INDEX.md",
            "",
            f"- Office: {self.office_id}",
            f"- Root: {self.base_dir}",
            f"- Raw source count: {raw_count}",
            f"- Decision records: {len(state.get('decision_records') or [])}",
            f"- Recommendation history: {len(state.get('recommendation_history') or [])}",
            f"- Last reflection at: {state.get('last_reflection_at') or 'never'}",
            f"- Search backend: {self.search_backend}",
            f"- Connector sync state: {len((state.get('connector_sync') or {}).get('connectors') or {})} connector",
            f"- Trigger history: {len(state.get('trigger_history') or [])}",
            f"- Location context: {'available' if (state.get('location_context') or {}).get('current_place') else 'empty'}",
            f"- Concept articles: {wiki_summary.get('article_count', 0)}",
            f"- Graph edges: {wiki_summary.get('graph_edges', 0)}",
            "",
            "## Pages",
        ]
        for key in PAGE_SPECS:
            page = state.get("pages", {}).get(key) or {}
            lines.append(
                f"- `{key}`: {len(page.get('records') or [])} kayıt -> {self.wiki_dir / f'{key}.md'}"
            )
        lines.extend(
            [
                "",
                "## Wiki Brain",
                f"- Concept index -> {self._concepts_dir() / 'INDEX.md'}",
                f"- Brain JSON -> {self._wiki_brain_path()}",
                f"- Graph JSON -> {self._wiki_graph_path()}",
                f"- Brain report -> {self._reports_dir() / 'wiki-brain-latest.md'}",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    def _render_page_markdown(self, key: str, page: dict[str, Any], *, wiki_brain: dict[str, Any] | None = None) -> str:
        records = list(page.get("records") or [])
        active = [item for item in records if str(item.get("status") or "active") == "active"]
        backlinks = dict((wiki_brain or {}).get("record_backlinks") or {})
        claim_bindings: list[dict[str, Any]] = []
        lines = [
            f"# {key.title()}",
            "",
            PAGE_SPECS.get(key, ""),
            "",
            f"- Active records: {len(active)}",
            f"- Total records: {len(records)}",
            "",
        ]
        if not records:
            lines.append("- Henüz kayıt yok.")
            return "\n".join(lines).rstrip() + "\n"
        for item in sorted(records, key=lambda record: (str(record.get("status") or "active") != "active", str(record.get("updated_at") or "")), reverse=False):
            envelope = self._normalized_record_envelope(key, item)
            lines.extend(
                [
                    f"## {item.get('title') or item.get('id')}",
                    f"- Summary: {item.get('summary') or ''}",
                    f"- Confidence: {item.get('confidence')}",
                    f"- Status: {item.get('status') or 'active'}",
                    f"- Updated at: {item.get('updated_at') or ''}",
                    f"- Record type: {envelope.get('record_type')}",
                    f"- Scope: {envelope.get('scope')}",
                    f"- Sensitivity: {envelope.get('sensitivity')}",
                    f"- Exportability: {envelope.get('exportability')}",
                    f"- Model routing: {envelope.get('model_routing_hint')}",
                    f"- Sources: {', '.join(item.get('source_refs') or []) or 'none'}",
                ]
            )
            claim_binding = self._claim_binding_for_record(key, item, envelope)
            if claim_binding:
                claim_bindings.append(claim_binding)
                lines.append(
                    f"- Claim binding: {claim_binding.get('subject_key') or 'unknown'} · {claim_binding.get('predicate') or 'unknown'} · {claim_binding.get('status') or 'unknown'}"
                )
                lines.append(f"- Claim status: {claim_binding.get('status') or 'unknown'}")
                lines.append(f"- Support quality: {claim_binding.get('support_strength') or 'unknown'}")
                claim_refs: list[str] = []
                current_claim_id = str(claim_binding.get("current_claim_id") or "").strip()
                if current_claim_id:
                    claim_refs.append(f"current={current_claim_id}")
                for label, field in (
                    ("supporting", "supporting_claim_ids"),
                    ("source", "source_claim_ids"),
                    ("derived", "derived_from_claim_ids"),
                ):
                    values = [str(value).strip() for value in list(claim_binding.get(field) or []) if str(value).strip()]
                    if values:
                        claim_refs.append(f"{label}={', '.join(values[:6])}")
                if claim_refs:
                    lines.append(f"- Claim refs: {' | '.join(claim_refs)}")
            related_concepts = list(backlinks.get(f"{key}:{item.get('id')}") or [])
            if related_concepts:
                concept_links = ", ".join(
                    f"[{concept.get('title')}](./concepts/{Path(str(concept.get('path') or '')).name})"
                    for concept in related_concepts[:6]
                )
                lines.append(f"- Linked concepts: {concept_links}")
            metadata = envelope.get("metadata") or {}
            if metadata:
                lines.append(f"- Metadata: {json.dumps(metadata, ensure_ascii=False)}")
            lines.append("")
        rendered_markdown = "\n".join(lines).rstrip() + "\n"
        article_claim_bindings = self._page_article_claim_bindings(
            key,
            page,
            claim_bindings=claim_bindings,
            rendered_markdown=rendered_markdown,
        )
        if article_claim_bindings:
            rendered_lines = rendered_markdown.rstrip().splitlines()
            rendered_lines.extend(["", "## Claim Sentence Bindings"])
            for item in article_claim_bindings[:16]:
                refs = ", ".join(list(item.get("claim_ids") or [])[:4]) or "none"
                rendered_lines.append(f"- [{item.get('section')}] {item.get('text')} | claims={refs}")
            return "\n".join(rendered_lines).rstrip() + "\n"
        return rendered_markdown

    def _render_decision_markdown(self, record: dict[str, Any]) -> str:
        lines = [
            f"# {record['title']}",
            "",
            f"- Created at: {record['created_at']}",
            f"- Intent: {record.get('intent') or 'none'}",
            f"- Confidence: {record['confidence']}",
            f"- User confirmation required: {record['user_confirmation_required']}",
            f"- Risk level: {record['risk_level']}",
            f"- Policy: {record['policy']}",
            "",
            "## Summary",
            record["summary"],
            "",
            "## Reasoning",
            record["reasoning_summary"],
            "",
            "## Source Refs",
        ]
        for item in record.get("source_refs") or []:
            lines.append(f"- {json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else item}")
        lines.extend(["", "## Alternatives"])
        alternatives = record.get("alternatives") or []
        if alternatives:
            for item in alternatives:
                lines.append(f"- {item}")
        else:
            lines.append("- None")
        lines.extend(["", "## Possible Risks"])
        risks = record.get("possible_risks") or []
        if risks:
            for item in risks:
                lines.append(f"- {item}")
        else:
            lines.append("- None")
        return "\n".join(lines).rstrip() + "\n"

    def _assert_not_excluded(self, source_ref: str | None, metadata: dict[str, Any] | None) -> None:
        haystacks = [
            _compact_text(source_ref, limit=4096).lower(),
            json.dumps(metadata or {}, ensure_ascii=False).lower(),
        ]
        for pattern in self.excluded_patterns:
            token = pattern.strip().lower()
            if not token:
                continue
            if any(token in haystack for haystack in haystacks):
                raise ValueError("source_excluded_by_policy")

    @staticmethod
    def _is_human_controlled_record(record: dict[str, Any]) -> bool:
        signals = {str(item).strip() for item in list(record.get("signals") or []) if str(item).strip()}
        if signals.intersection(HUMAN_CONTROLLED_SIGNALS):
            return True
        metadata = dict(record.get("metadata") or {})
        source_type = str(metadata.get("source_type") or "").strip()
        return source_type in {"user_preferences", "profile_snapshot", "assistant_runtime_snapshot"}

    @staticmethod
    def _epistemic_basis_for_source_type(source_type: str) -> tuple[str, str]:
        normalized = str(source_type or "").strip()
        if normalized in {"assistant_message_feedback", "recommendation_feedback"}:
            return "user_confirmed_inference", "user_confirmed"
        if normalized in {
            "email",
            "messages",
            "whatsapp",
            "calendar",
            "places",
            "location_events",
            "travel_signal",
            "shopping_signal",
            "consumer_signal",
            "browser_context",
            "reading_list",
            "youtube_history",
            "weather_context",
            "place_interest",
            "web_research_signal",
            "tasks",
            "reminders",
            "notes",
        }:
            return "connector_observed", "source_supported"
        if normalized in {"files", "pdf", "legal_docs", "elastic_document"}:
            return "document_extracted", "source_supported"
        return "inferred", "pending"

    @staticmethod
    def _epistemic_stringify_claim_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return ""
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value).strip()

    def _epistemic_mapping_for_record(
        self,
        page_key: str,
        record: dict[str, Any],
        metadata: dict[str, Any],
        scope: str,
        *,
        allow_human_controlled: bool = False,
    ) -> dict[str, Any] | None:
        source_type = str(metadata.get("source_type") or "").strip()
        nested_metadata = dict(metadata.get("metadata") or {}) if isinstance(metadata.get("metadata"), dict) else {}
        if self._record_is_self_generated(metadata):
            return None
        if source_type == "assistant_file_back":
            return None
        if (
            not allow_human_controlled
            and source_type in {"profile_snapshot", "user_preferences", "assistant_runtime_snapshot"}
        ):
            return None
        field = str(metadata.get("field") or nested_metadata.get("field") or "").strip()
        title = str(record.get("title") or "").strip()
        if page_key == "contacts" and title:
            predicate = field or ("relationship" if metadata.get("relationship") else "")
            if not predicate:
                return None
            return {
                "subject_key": f"contact:{_slugify(title)}",
                "predicate": predicate,
                "object_value_text": str(record.get("summary") or title).strip(),
                "display_label": title,
            }
        if page_key == "places" and title:
            predicate = field or ("category" if nested_metadata.get("category") else "")
            if not predicate:
                return None
            object_value_text = str(nested_metadata.get("category") or record.get("summary") or title).strip()
            return {
                "subject_key": f"place:{_slugify(str(nested_metadata.get('place_name') or title))}",
                "predicate": predicate,
                "object_value_text": object_value_text,
                "display_label": title,
            }
        if page_key in {"preferences", "routines", "persona"} and field:
            return {
                "subject_key": "user",
                "predicate": field,
                "object_value_text": str(record.get("summary") or "").strip(),
                "display_label": str(record.get("title") or field).strip(),
            }
        return None

    def _epistemic_claim_hints_for_record(
        self,
        page_key: str,
        record: dict[str, Any],
        metadata: dict[str, Any],
        scope: str,
    ) -> list[dict[str, Any]]:
        source_type = str(metadata.get("source_type") or "").strip()
        nested_metadata = dict(metadata.get("metadata") or {}) if isinstance(metadata.get("metadata"), dict) else {}
        basis, validation_state = self._epistemic_basis_for_source_type(source_type)
        sensitivity = str(metadata.get("sensitivity") or self._infer_sensitivity(page_key, metadata, record))
        default_retrieval = "blocked" if sensitivity in {"high", "restricted"} else "eligible"
        hints: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for container in (metadata, nested_metadata):
            raw_hints = container.get("epistemic_claim_hints")
            if not isinstance(raw_hints, list):
                continue
            for index, hint in enumerate(raw_hints):
                if not isinstance(hint, dict):
                    continue
                subject_key = str(hint.get("subject_key") or "").strip()
                predicate = str(hint.get("predicate") or "").strip()
                object_value_text = self._epistemic_stringify_claim_value(
                    hint.get("object_value_text") if "object_value_text" in hint else hint.get("value")
                )
                claim_scope = str(hint.get("scope") or scope).strip() or scope
                if not subject_key or not predicate or not object_value_text or not claim_scope:
                    continue
                if not self._allow_epistemic_claim_hint(
                    page_key=page_key,
                    record=record,
                    metadata=metadata,
                    hint=hint,
                    subject_key=subject_key,
                    predicate=predicate,
                    source_type=source_type,
                ):
                    continue
                marker = (subject_key, predicate, claim_scope, object_value_text)
                if marker in seen:
                    continue
                seen.add(marker)
                hints.append(
                    {
                        "subject_key": subject_key,
                        "predicate": predicate,
                        "object_value_text": object_value_text,
                        "scope": claim_scope,
                        "epistemic_basis": str(hint.get("epistemic_basis") or basis or "inferred"),
                        "validation_state": str(hint.get("validation_state") or validation_state or "pending"),
                        "consent_class": str(hint.get("consent_class") or "allowed"),
                        "retrieval_eligibility": str(hint.get("retrieval_eligibility") or default_retrieval),
                        "sensitive": bool(hint.get("sensitive")) or sensitivity in {"high", "restricted"},
                        "self_generated": bool(hint.get("self_generated")),
                        "object_value_json": hint.get("object_value_json") if isinstance(hint.get("object_value_json"), dict) else {},
                        "display_label": str(hint.get("display_label") or record.get("title") or predicate).strip(),
                        "supporting_claim_ids": list(hint.get("supporting_claim_ids") or []),
                        "source_claim_ids": list(hint.get("source_claim_ids") or []),
                        "derived_from_claim_ids": list(hint.get("derived_from_claim_ids") or []),
                        "claim_hint_key": str(hint.get("claim_hint_key") or f"{subject_key}:{predicate}:{index}").strip(),
                        "extra_metadata": dict(hint.get("metadata") or {}) if isinstance(hint.get("metadata"), dict) else {},
                    }
                )
        return hints

    @staticmethod
    def _allow_epistemic_claim_hint(
        *,
        page_key: str,
        record: dict[str, Any],
        metadata: dict[str, Any],
        hint: dict[str, Any],
        subject_key: str,
        predicate: str,
        source_type: str,
    ) -> bool:
        normalized_source_type = str(source_type or "").strip().lower()
        family = resolve_predicate_family(subject_key=subject_key, predicate=predicate)
        hint_metadata = dict(hint.get("metadata") or {}) if isinstance(hint.get("metadata"), dict) else {}
        provider = str(metadata.get("provider") or "").strip().lower()
        safe_structured_predicates = {
            "reply_needed",
            "direction",
            "status",
            "priority",
            "preparation_needed",
            "location",
            "category",
            "query",
            "topic_title",
            "url_host",
            "current_place",
            "home_base",
        }
        if normalized_source_type in {"user_preferences", "profile_snapshot", "assistant_runtime_snapshot"}:
            return True
        if provider == "profile" and family in {"user_preference", "contact_preference", "location_context"}:
            return True
        if hint_metadata.get("claim_view") == "recent_activity":
            return True
        if predicate in safe_structured_predicates:
            return True
        if family in {"task_state", "workspace_fact", "location_context", "action_outcome"}:
            return True
        if bool(hint_metadata.get("allow_profile_promotion")) and family in {"user_preference", "contact_preference"}:
            return True
        if page_key in {"preferences", "routines", "persona"} and str(record.get("title") or "").strip():
            return family == "user_preference"
        return False

    def _promote_record_to_epistemic_claim(self, page_key: str, record: dict[str, Any]) -> None:
        if self.epistemic is None:
            return
        metadata = dict((record.get("metadata") or {}))
        scope = str(metadata.get("scope") or self._infer_scope(page_key, metadata, record) or "global")
        basis, validation_state = self._epistemic_basis_for_source_type(str(metadata.get("source_type") or ""))
        claim_payloads = list(self._epistemic_claim_hints_for_record(page_key, record, metadata, scope))
        fallback_mapping = self._epistemic_mapping_for_record(page_key, record, metadata, scope)
        if fallback_mapping:
            claim_payloads.append(
                {
                    "subject_key": str(fallback_mapping.get("subject_key") or "").strip(),
                    "predicate": str(fallback_mapping.get("predicate") or "").strip(),
                    "object_value_text": str(fallback_mapping.get("object_value_text") or "").strip(),
                    "scope": scope,
                    "epistemic_basis": basis,
                    "validation_state": validation_state,
                    "consent_class": "allowed",
                    "retrieval_eligibility": "blocked"
                    if str(metadata.get("sensitivity") or "") in {"high", "restricted"}
                    else "eligible",
                    "sensitive": str(metadata.get("sensitivity") or "") in {"high", "restricted"},
                    "self_generated": False,
                    "object_value_json": {},
                    "display_label": str(fallback_mapping.get("display_label") or record.get("title") or "").strip(),
                    "supporting_claim_ids": list(metadata.get("supporting_claim_ids") or []),
                    "source_claim_ids": list(metadata.get("source_claim_ids") or []),
                    "derived_from_claim_ids": list(metadata.get("derived_from_claim_ids") or []),
                    "claim_hint_key": "heuristic_default",
                    "extra_metadata": {},
                }
            )
        if not claim_payloads:
            return
        kb_record_ref = f"{page_key}:{record.get('id')}"
        try:
            artifact = self.epistemic.record_artifact(
                artifact_kind="kb_record",
                source_kind=str(metadata.get("source_type") or "knowledge_record"),
                source_ref=f"kb-record:{kb_record_ref}",
                summary=str(record.get("title") or record.get("id") or "KB record"),
                payload={
                    "page_key": page_key,
                    "record_id": record.get("id"),
                    "record_key": record.get("key"),
                    "title": record.get("title"),
                    "summary": record.get("summary"),
                    "metadata": metadata,
                    "source_refs": list(record.get("source_refs") or []),
                },
                provenance={"kb_record_ref": kb_record_ref},
                sensitive=str(metadata.get("sensitivity") or "") in {"high", "restricted"},
                artifact_id=f"ea-kb-{_fingerprint([page_key, record.get('id')])[:16]}",
            )
            for claim_payload in claim_payloads:
                subject_key = str(claim_payload.get("subject_key") or "").strip()
                predicate = str(claim_payload.get("predicate") or "").strip()
                claim_scope = str(claim_payload.get("scope") or scope).strip() or scope
                object_value_text = str(claim_payload.get("object_value_text") or "").strip()
                if not subject_key or not predicate or not claim_scope or not object_value_text:
                    continue
                claim_hint_key = str(claim_payload.get("claim_hint_key") or "default").strip() or "default"
                existing_claims = self.epistemic.store.list_epistemic_claims(
                    self.office_id,
                    subject_key=subject_key,
                    predicate=predicate,
                    scope=claim_scope,
                    include_blocked=True,
                    limit=40,
                )
                should_skip = False
                for existing in existing_claims:
                    existing_metadata = dict(existing.get("metadata") or {})
                    existing_ref = str(existing_metadata.get("kb_record_ref") or "")
                    existing_hint_key = str(existing_metadata.get("claim_hint_key") or "default")
                    if existing_ref != kb_record_ref or existing_hint_key != claim_hint_key:
                        continue
                    if str(existing.get("object_value_text") or "").strip() == object_value_text:
                        should_skip = True
                        break
                    self.epistemic.store.update_epistemic_claim(
                        self.office_id,
                        str(existing.get("id") or ""),
                        validation_state="superseded",
                        retrieval_eligibility="demoted",
                        valid_to=_iso_now(),
                        metadata={"superseded_by_kb_record": kb_record_ref},
                    )
                if should_skip:
                    continue
                self.epistemic.record_claim(
                    subject_key=subject_key,
                    predicate=predicate,
                    object_value_text=object_value_text,
                    object_value_json=dict(claim_payload.get("object_value_json") or {}),
                    scope=claim_scope,
                    epistemic_basis=str(claim_payload.get("epistemic_basis") or basis or "inferred"),
                    validation_state=str(claim_payload.get("validation_state") or validation_state or "pending"),
                    consent_class=str(claim_payload.get("consent_class") or "allowed"),
                    retrieval_eligibility=str(claim_payload.get("retrieval_eligibility") or "eligible"),
                    artifact_id=str(artifact.get("id") or ""),
                    sensitive=bool(claim_payload.get("sensitive")),
                    self_generated=bool(claim_payload.get("self_generated")),
                    metadata={
                        "kb_record_ref": kb_record_ref,
                        "page_key": page_key,
                        "record_key": record.get("key"),
                        "source_type": metadata.get("source_type"),
                        "display_label": claim_payload.get("display_label"),
                        "claim_hint_key": claim_hint_key,
                        "supporting_claim_ids": list(claim_payload.get("supporting_claim_ids") or []),
                        "source_claim_ids": list(claim_payload.get("source_claim_ids") or []),
                        "derived_from_claim_ids": list(claim_payload.get("derived_from_claim_ids") or []),
                        **dict(claim_payload.get("extra_metadata") or {}),
                    },
                )
        except Exception:
            return

    def _epistemic_resolution_for_record(self, page_key: str, record: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any] | None:
        if self.epistemic is None:
            return None
        metadata = dict(envelope.get("metadata") or {})
        scope = str(envelope.get("scope") or "global")
        candidate_mappings: list[dict[str, Any]] = []
        if self._record_is_self_generated(metadata):
            candidate_mappings.append(
                {
                    "subject_key": f"assistant_output:{str(metadata.get('file_back_kind') or 'assistant_reply')}",
                    "predicate": "narrative",
                    "scope": scope,
                }
            )
        else:
            candidate_mappings.extend(self._epistemic_claim_hints_for_record(page_key, record, metadata, scope))
            fallback_mapping = self._epistemic_mapping_for_record(
                page_key,
                record,
                metadata,
                scope,
                allow_human_controlled=True,
            )
            if fallback_mapping:
                candidate_mappings.append(
                    {
                        "subject_key": str(fallback_mapping.get("subject_key") or "").strip(),
                        "predicate": str(fallback_mapping.get("predicate") or "").strip(),
                        "scope": scope,
                    }
                )
        ranked_entries: list[dict[str, Any]] = []
        for mapping in candidate_mappings:
            subject_key = str(mapping.get("subject_key") or "").strip()
            predicate = str(mapping.get("predicate") or "").strip()
            claim_scope = str(mapping.get("scope") or scope).strip() or scope
            if not subject_key or not predicate:
                continue
            resolved = self.epistemic.resolve_claim(
                subject_key=subject_key,
                predicate=predicate,
                scope=claim_scope,
                include_blocked=True,
            )
            current_claim = resolved.get("current_claim") if isinstance(resolved, dict) else None
            current_support = resolved.get("current_claim_support") if isinstance(resolved, dict) else None
            if not isinstance(current_claim, dict):
                continue
            ranked_entries.append(
                {
                    "mapping": mapping,
                    "resolved": resolved,
                    "current_claim": current_claim,
                    "current_support": current_support,
                }
            )
        if not ranked_entries:
            return None
        ranked_entries.sort(
            key=lambda entry: self.epistemic._claim_rank_with_support(  # type: ignore[attr-defined]
                entry["current_claim"],
                entry.get("current_support") or {},
            ),
            reverse=True,
        )
        best = ranked_entries[0]
        best_mapping = dict(best.get("mapping") or {})
        resolved = dict(best.get("resolved") or {})
        current_claim = dict(best.get("current_claim") or {})
        current_support = dict(best.get("current_support") or {})
        subject_key = str(best_mapping.get("subject_key") or current_claim.get("subject_key") or "")
        predicate = str(best_mapping.get("predicate") or current_claim.get("predicate") or "")
        return {
            "status": str(resolved.get("status") or "unknown"),
            "subject_key": subject_key,
            "predicate": predicate,
            "current_claim_id": str((current_claim or {}).get("id") or "") or None,
            "current_subject_key": str((current_claim or {}).get("subject_key") or subject_key) or None,
            "current_predicate": str((current_claim or {}).get("predicate") or predicate) or None,
            "current_basis": str((current_claim or {}).get("epistemic_basis") or "") or None,
            "current_value_text": str((current_claim or {}).get("object_value_text") or "") or None,
            "display_label": str((((current_claim or {}).get("metadata") or {}).get("display_label") or record.get("title") or predicate) or "") or None,
            "validation_state": str((current_claim or {}).get("validation_state") or "") or None,
            "consent_class": str((current_claim or {}).get("consent_class") or "") or None,
            "retrieval_eligibility": str((current_claim or {}).get("retrieval_eligibility") or "") or None,
            "contested_count": len(list(resolved.get("contested_claims") or [])),
            "support_strength": str((current_support or {}).get("support_strength") or "") or None,
            "support_contaminated": bool((current_support or {}).get("contaminated")),
            "support_cycle_detected": bool((current_support or {}).get("cycle_detected")),
            "support_reason_codes": list((current_support or {}).get("reason_codes") or []),
            "external_support_count": int((current_support or {}).get("external_support_count") or 0),
            "self_generated_support_count": int((current_support or {}).get("self_generated_support_count") or 0),
            "memory_tier": str(((resolved.get("current_claim_memory") or {}) if isinstance(resolved.get("current_claim_memory"), dict) else {}).get("memory_tier") or "") or None,
            "salience_score": float(((resolved.get("current_claim_memory") or {}) if isinstance(resolved.get("current_claim_memory"), dict) else {}).get("salience_score") or 0.0) or None,
            "age_days": ((resolved.get("current_claim_memory") or {}) if isinstance(resolved.get("current_claim_memory"), dict) else {}).get("age_days"),
        }

    @staticmethod
    def _claim_reference_ids(claim: dict[str, Any]) -> dict[str, list[str]]:
        metadata = dict(claim.get("metadata") or {})
        references: dict[str, list[str]] = {}
        for key in ("supporting_claim_ids", "source_claim_ids", "derived_from_claim_ids"):
            value = metadata.get(key)
            if isinstance(value, list):
                references[key] = [str(item).strip() for item in value if str(item).strip()]
            elif isinstance(value, str) and value.strip():
                references[key] = [value.strip()]
            else:
                references[key] = []
        return references

    def _claim_binding_for_record(
        self,
        page_key: str,
        record: dict[str, Any],
        envelope: dict[str, Any],
        *,
        epistemic: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if self.epistemic is None:
            return None
        resolved = dict(epistemic or self._epistemic_resolution_for_record(page_key, record, envelope) or {})
        claim_id = str(resolved.get("current_claim_id") or "").strip()
        if not claim_id:
            return None
        current_claim = dict(self.epistemic.store.get_epistemic_claim(self.office_id, claim_id) or {})
        if not current_claim:
            return None
        support = self.epistemic.inspect_claim_support(claim=current_claim)
        memory_profile = self.epistemic.describe_claim_memory(claim=current_claim, support=support)
        references = self._claim_reference_ids(current_claim)
        return {
            "record_id": str(record.get("id") or "").strip() or None,
            "record_key": str(record.get("key") or "").strip() or None,
            "record_title": str(record.get("title") or record.get("id") or "Kayıt"),
            "current_claim_id": claim_id,
            "subject_key": str(resolved.get("subject_key") or current_claim.get("subject_key") or "").strip() or None,
            "predicate": str(resolved.get("predicate") or current_claim.get("predicate") or "").strip() or None,
            "status": str(resolved.get("status") or current_claim.get("validation_state") or "unknown"),
            "basis": str(resolved.get("current_basis") or current_claim.get("epistemic_basis") or "").strip() or None,
            "validation_state": str(current_claim.get("validation_state") or "").strip() or None,
            "retrieval_eligibility": str(current_claim.get("retrieval_eligibility") or "").strip() or None,
            "support_strength": str((support or {}).get("support_strength") or "").strip() or None,
            "support_reason_codes": list((support or {}).get("reason_codes") or []),
            "support_contaminated": bool((support or {}).get("contaminated")),
            "support_cycle_detected": bool((support or {}).get("cycle_detected")),
            "external_support_count": int((support or {}).get("external_support_count") or 0),
            "self_generated_support_count": int((support or {}).get("self_generated_support_count") or 0),
            "memory_tier": str((memory_profile or {}).get("memory_tier") or "").strip() or None,
            "salience_score": float((memory_profile or {}).get("salience_score") or 0.0) or None,
            "age_days": (memory_profile or {}).get("age_days"),
            "supporting_claim_ids": references.get("supporting_claim_ids") or [],
            "source_claim_ids": references.get("source_claim_ids") or [],
            "derived_from_claim_ids": references.get("derived_from_claim_ids") or [],
        }

    @staticmethod
    def _epistemic_basis_context_label(basis: str) -> str:
        normalized = str(basis or "").strip().lower()
        return {
            "user_explicit": "kullanıcı bilgisi",
            "user_confirmed_inference": "onaylı çıkarım",
            "connector_observed": "kaynak gözlemi",
            "document_extracted": "belge kaynağı",
            "assistant_generated": "asistan kaydı",
        }.get(normalized, "çözülmüş kayıt")

    @classmethod
    def _claim_context_entry_from_hit(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        metadata = dict(item.get("metadata") or {})
        if str(metadata.get("epistemic_status") or "").strip().lower() != "current":
            return None
        if bool(metadata.get("epistemic_support_contaminated")):
            return None
        support_strength = str(metadata.get("epistemic_support_strength") or "").strip().lower()
        if support_strength not in {"grounded", "supported"}:
            return None
        retrieval_eligibility = str(metadata.get("epistemic_retrieval_eligibility") or "eligible").strip().lower()
        if retrieval_eligibility in {"blocked", "quarantined"}:
            return None
        value_text = str(metadata.get("epistemic_current_value") or "").strip()
        if not value_text:
            return None
        label = str(metadata.get("epistemic_display_label") or item.get("title") or metadata.get("epistemic_predicate") or "").strip()
        claim_id = str(metadata.get("epistemic_current_claim_id") or "").strip()
        basis = str(metadata.get("epistemic_basis") or "").strip()
        return {
            "claim_id": claim_id or None,
            "subject_key": str(metadata.get("epistemic_subject_key") or "").strip() or None,
            "predicate": str(metadata.get("epistemic_predicate") or "").strip() or None,
            "value_text": value_text,
            "basis": basis,
            "support_strength": support_strength,
            "display_label": label or str(item.get("title") or "").strip() or None,
            "page_key": str(item.get("page_key") or "").strip() or None,
            "record_id": str(item.get("record_id") or "").strip() or None,
            "summary_line": f"- [{cls._epistemic_basis_context_label(basis)}] {label or item.get('title')}: {value_text}",
        }

    def _upsert_page_record(self, state: dict[str, Any], page_key: str, record: dict[str, Any]) -> dict[str, Any]:
        page = state.setdefault("pages", {}).setdefault(
            page_key,
            {"title": page_key.title(), "description": PAGE_SPECS.get(page_key, ""), "records": []},
        )
        records = list(page.get("records") or [])
        updated = False
        contradictions: list[dict[str, Any]] = []
        normalized_source_refs = [str(item).strip() for item in record.get("source_refs") or [] if str(item).strip()]
        record["source_refs"] = normalized_source_refs
        envelope = self._normalized_record_envelope(page_key, record)
        record["metadata"] = envelope["metadata"]

        for existing in records:
            if str(existing.get("id") or "") != str(record.get("id") or ""):
                continue
            merged_sources = sorted(set([*(existing.get("source_refs") or []), *normalized_source_refs]))
            if (
                str(existing.get("summary") or "") == str(record.get("summary") or "")
                and merged_sources == sorted(existing.get("source_refs") or [])
                and float(existing.get("confidence") or 0.0) == float(record.get("confidence") or 0.0)
            ):
                return {"updated": False, "contradictions": []}
            existing.update(record)
            existing["source_refs"] = merged_sources
            updated = True
            page["records"] = records
            self._promote_record_to_epistemic_claim(page_key, existing)
            return {"updated": updated, "contradictions": contradictions}

        logical_key = str(record.get("key") or "")
        blocked_by_prior = False
        for existing in records:
            existing_status = str(existing.get("status") or "active")
            if existing_status != "active":
                if (
                    existing_status == "superseded"
                    and logical_key
                    and str(existing.get("key") or "") == logical_key
                    and bool(((existing.get("metadata") or {}).get("do_not_infer_again_easily")))
                    and not self._is_human_controlled_record(record)
                ):
                    blocked_by_prior = True
                continue
            if logical_key and str(existing.get("key") or "") != logical_key:
                continue
            if logical_key and str(existing.get("summary") or "") == str(record.get("summary") or ""):
                merged_sources = sorted(set([*(existing.get("source_refs") or []), *normalized_source_refs]))
                merged_signals = sorted(
                    set(
                        [
                            *(str(item).strip() for item in list(existing.get("signals") or []) if str(item).strip()),
                            *(str(item).strip() for item in list(record.get("signals") or []) if str(item).strip()),
                        ]
                    )
                )
                merged_metadata = dict(existing.get("metadata") or {})
                incoming_metadata = dict(record.get("metadata") or {})
                existing_history = list(merged_metadata.get("correction_history") or [])
                incoming_history = list(incoming_metadata.get("correction_history") or [])
                if incoming_history:
                    merged_metadata["correction_history"] = [*existing_history, *incoming_history][-20:]
                for sticky_flag in ("do_not_infer_again_easily", "repeated_contradiction_count"):
                    if sticky_flag in merged_metadata and sticky_flag not in incoming_metadata:
                        incoming_metadata[sticky_flag] = merged_metadata.get(sticky_flag)
                merged_metadata.update(incoming_metadata)
                next_confidence = max(float(existing.get("confidence") or 0.0), float(record.get("confidence") or 0.0))
                if (
                    merged_sources == sorted(existing.get("source_refs") or [])
                    and merged_signals == sorted(str(item).strip() for item in list(existing.get("signals") or []) if str(item).strip())
                    and next_confidence == float(existing.get("confidence") or 0.0)
                    and merged_metadata == dict(existing.get("metadata") or {})
                ):
                    return {"updated": False, "contradictions": contradictions}
                existing.update(record)
                existing["source_refs"] = merged_sources
                existing["signals"] = merged_signals
                existing["confidence"] = round(next_confidence, 2)
                existing["metadata"] = merged_metadata
                updated = True
                page["records"] = records
                self._promote_record_to_epistemic_claim(page_key, existing)
                return {"updated": updated, "contradictions": contradictions}
            if logical_key and str(existing.get("summary") or "") != str(record.get("summary") or ""):
                existing["status"] = "superseded"
                existing["superseded_at"] = _iso_now()
                contradictions.append(
                    {
                        "page": page_key,
                        "key": logical_key,
                        "old_record_id": existing.get("id"),
                        "new_record_id": record.get("id"),
                    }
                )
                updated = True
        if blocked_by_prior:
            self._append_log(
                "memory_reinference_blocked",
                f"{page_key} için düşük güvenli tekrar çıkarım engellendi",
                {"key": logical_key, "record_id": record.get("id")},
            )
            page["records"] = records
            return {"updated": False, "contradictions": contradictions}
        records.append(record)
        page["records"] = records
        self._promote_record_to_epistemic_claim(page_key, record)
        return {"updated": True or updated, "contradictions": contradictions}

    def _record_recommendation(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state()
        history = list(state.get("recommendation_history") or [])
        created_at = _iso_now()
        history_id = str(recommendation.get("id") or f"rec-{_fingerprint(recommendation)[:10]}")
        fingerprint = _fingerprint(
            [
                recommendation.get("kind"),
                recommendation.get("suggestion"),
                recommendation.get("why_this"),
            ]
        )
        for item in history:
            if str(item.get("fingerprint") or "") != fingerprint:
                continue
            item["seen_at"] = created_at
            state["recommendation_history"] = history[-200:]
            self._save_state(state)
            self._render_all(state)
            return {"history_id": str(item.get("id") or history_id)}

        history_item = {
            "id": history_id,
            "kind": recommendation.get("kind"),
            "suggestion": recommendation.get("suggestion"),
            "why_this": recommendation.get("why_this"),
            "confidence": recommendation.get("confidence"),
            "requires_confirmation": recommendation.get("requires_confirmation"),
            "fingerprint": fingerprint,
            "created_at": created_at,
            "outcome": "suggested",
        }
        history.append(history_item)
        state["recommendation_history"] = history[-200:]
        self._upsert_page_record(
            state,
            "recommendations",
            {
                "id": history_id,
                "key": history_id,
                "title": recommendation.get("kind") or "recommendation",
                "summary": recommendation.get("suggestion") or "",
                "confidence": float(recommendation.get("confidence") or 0.0),
                "status": "active",
                "source_refs": [],
                "signals": ["recommendation"],
                "updated_at": created_at,
                "metadata": {
                    "why_this": recommendation.get("why_this"),
                    "requires_confirmation": recommendation.get("requires_confirmation"),
                    "source_basis": list(recommendation.get("source_basis") or []),
                    "memory_scope": list(recommendation.get("memory_scope") or []),
                    "next_actions": list(recommendation.get("next_actions") or []),
                    "record_type": "recommendation",
                },
            },
        )
        state["updated_at"] = created_at
        self._save_state(state)
        self._render_all(state)
        decision_record = self.create_decision_record(
            title=f"Recommendation: {recommendation.get('kind') or 'generic'}",
            summary=str(recommendation.get("suggestion") or ""),
            source_refs=list(recommendation.get("source_basis") or []),
            reasoning_summary=str(recommendation.get("why_this") or ""),
            confidence=float(recommendation.get("confidence") or 0.0),
            user_confirmation_required=bool(recommendation.get("requires_confirmation")),
            possible_risks=["Öneri güncel bağlam değişirse isabetsiz olabilir"],
            action_kind="draft_message" if "draft" in str(recommendation.get("kind") or "") else "read_summary",
            intent=str(recommendation.get("kind") or ""),
            alternatives=["Öneri sunmadan önce ek bağlam istemek"],
        )
        return {"history_id": history_id, "decision_record": decision_record}
