from __future__ import annotations

from datetime import date, datetime, time as clock_time, timedelta, timezone
import hashlib
import re
import threading
import time
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException

from .audit import AuditLogger
from .auth import parse_token, issue_token, require_role
from .config import get_settings, load_model_profiles, resolve_repo_path
from .core import assistant_runtime_mode
from .connectors.safety import ConnectorPolicy, ConnectorSafetyWrapper
from .connectors.registry import build_tools_status
from .connectors.web_search import (
    build_travel_context,
    build_web_search_context,
    is_travel_booking_query,
    is_travel_query,
    is_web_search_query,
)
from .llm.direct_provider import DirectProviderLLM
from .llm.service import LLMService
from .memory import MemoryService
from .model_router import ModelRouter
from .agent_bridges.openclaw_runtime import create_openclaw_runtime
from .agent_bridges.openclaw_workspace import create_openclaw_workspace_contract
from .observability import StructuredLogger
from .persistence import Persistence
from .planner import build_thread_response_extensions
from .rag import build_persisted_chunks, create_rag_store, score_chunk_records
from .schemas import (
    AssistantActionDecisionRequest,
    AssistantActionGenerateRequest,
    AssistantCalendarEventCreateRequest,
    AssistantRuntimeProfileRequest,
    AssistantDraftSendRequest,
    AssistantDispatchReportRequest,
    AssistantThreadMessageRequest,
    GoogleSyncRequest,
    WhatsAppSyncRequest,
    XSyncRequest,
    QueryIn,
    QueryJobCreateRequest,
    TokenRequest,
    ConnectorPreviewRequest,
    MatterCreateRequest,
    MatterUpdateRequest,
    MatterNoteCreateRequest,
    MatterDraftCreateRequest,
    MatterDraftGenerateRequest,
    MatterSearchRequest,
    WorkspaceRootRequest,
    WorkspaceScanRequest,
    WorkspaceSearchRequest,
    SimilarDocumentsRequest,
    WorkspaceAttachRequest,
    UserProfileRequest,
    TaskCreateRequest,
    TaskBulkCompleteRequest,
    TaskStatusUpdateRequest,
    TaskDueUpdateRequest,
    CitationReviewRequest,
    EmailDraftCreateRequest,
    EmailDraftApproveRequest,
    EmailDraftRetractRequest,
    SocialIngestRequest,
)
from .assistant import (
    _profile_preference_text,
    build_assistant_agenda,
    build_assistant_calendar,
    build_assistant_home,
    build_assistant_inbox,
    build_suggested_actions,
    sync_connected_accounts_from_settings,
)
from .workflows import build_activity_stream, build_chronology, build_risk_notes, build_task_recommendations, generate_matter_draft
from .workspace import (
    build_workspace_chunks,
    build_workspace_search_result,
    resolve_workspace_child,
    root_hash,
    scan_workspace_tree,
    validate_workspace_root,
)
from .similarity import find_similar_documents


def _safe_excerpt(value: str, max_len: int = 120) -> str:
    return value[:max_len].replace("\n", " ")


def _extract_text(content: bytes) -> str:
    text = content.decode("utf-8", errors="ignore").strip()
    if text:
        return text
    text = content.decode("latin-1", errors="ignore").strip()
    if text:
        return text
    raise ValueError("Dosya içeriği okunamadı.")


def _support_level(citations: list[dict]) -> str:
    if not citations:
        return "none"
    top = max(float(item.get("relevance_score", 0.0)) for item in citations)
    if top >= 0.26 and len(citations) >= 2:
        return "high"
    if top >= 0.16:
        return "medium"
    return "low"


def _citation_view(citation: dict, index: int | None = None) -> dict:
    payload = {
        "document_id": citation.get("document_id"),
        "document_name": citation.get("document_name"),
        "matter_id": citation.get("matter_id"),
        "chunk_id": citation.get("chunk_id"),
        "chunk_index": citation.get("chunk_index"),
        "excerpt": citation.get("excerpt"),
        "relevance_score": citation.get("relevance_score"),
        "source_type": citation.get("source_type"),
        "support_type": citation.get("support_type"),
        "confidence": citation.get("confidence"),
        "line_anchor": citation.get("line_anchor"),
        "page": citation.get("page"),
        "line_start": citation.get("line_start"),
        "line_end": citation.get("line_end"),
    }
    if index is not None:
        payload["index"] = index
        payload["label"] = f"[{index}]"
    return payload


def _truncate_for_prompt(value: str, max_len: int = 260) -> str:
    return " ".join(str(value or "").strip().split())[:max_len]


def _legacy_source_prompt_lines(sources: list[dict]) -> list[str]:
    lines: list[str] = []
    for index, source in enumerate(sources[:4], start=1):
        lines.append(
            f"[{index}] Belge: {source.get('document')} | Sayfa: {source.get('page')} | "
            f"Satırlar: {source.get('line_start')}-{source.get('line_end')} | "
            f"Pasaj: {_truncate_for_prompt(source.get('snippet') or '')}"
        )
    return lines


def _citation_prompt_lines(citations: list[dict]) -> list[str]:
    lines: list[str] = []
    for index, citation in enumerate(citations[:5], start=1):
        lines.append(
            f"[{index}] Belge: {citation.get('document_name')} | Tür: {citation.get('source_type')} | "
            f"Güven: {citation.get('confidence')} | "
            f"Pasaj: {_truncate_for_prompt(citation.get('excerpt') or '')}"
        )
    return lines


def _runtime_generated_from(runtime_completion: dict | None, *, direct_label: str, advanced_label: str, fallback_label: str) -> str:
    if not runtime_completion:
        return fallback_label
    if str(runtime_completion.get("runtime_mode") or "") == "advanced-openclaw":
        return advanced_label
    return direct_label


def _maybe_runtime_completion(runtime, prompt: str, events: StructuredLogger | None = None, *, task: str, **meta) -> dict | None:
    if not runtime:
        return None
    try:
        completion = runtime.complete(prompt, events, task=task, **meta)
    except TypeError:
        result = runtime.complete(prompt)
        if result.ok and result.text:
            if events:
                events.log("openclaw_runtime_used", task=task, provider=result.provider, model=result.model, **meta)
            return {
                "text": result.text,
                "provider": result.provider,
                "model": result.model,
            }
        if events:
            events.log("openclaw_runtime_fallback", level="warning", task=task, error=result.error, **meta)
        return None
    return completion


def _profile_summary_lines(profile: dict | None) -> list[str]:
    if not profile:
        return []
    lines: list[str] = []
    if profile.get("display_name"):
        lines.append(f"- Kullanıcı adı / hitap: {_truncate_for_prompt(profile['display_name'], 120)}")
    if profile.get("favorite_color"):
        lines.append(f"- Sevdiği renk: {_truncate_for_prompt(profile['favorite_color'], 120)}")
    if profile.get("assistant_notes"):
        lines.append(f"- Kullanıcı profil notu: {_truncate_for_prompt(profile['assistant_notes'], 260)}")
    if profile.get("food_preferences"):
        lines.append(f"- Yeme içme tercihleri: {_truncate_for_prompt(profile['food_preferences'], 220)}")
    if profile.get("transport_preference"):
        lines.append(f"- Ulaşım tercihi: {_truncate_for_prompt(profile['transport_preference'], 180)}")
    if profile.get("weather_preference"):
        lines.append(f"- Hava tercihi: {_truncate_for_prompt(profile['weather_preference'], 180)}")
    if profile.get("travel_preferences"):
        lines.append(f"- Seyahat notları: {_truncate_for_prompt(profile['travel_preferences'], 220)}")
    if profile.get("communication_style"):
        lines.append(f"- İletişim stili: {_truncate_for_prompt(profile['communication_style'], 180)}")
    important_dates = profile.get("important_dates") or []
    if important_dates:
        compact: list[str] = []
        for item in important_dates[:4]:
            label = _truncate_for_prompt(item.get("label") or "Önemli tarih", 80)
            date_value = item.get("date") or "Tarih yok"
            notes = _truncate_for_prompt(item.get("notes") or "", 100)
            compact.append(f"{label} ({date_value})" + (f": {notes}" if notes else ""))
        lines.append(f"- Önemli tarihler: {'; '.join(compact)}")
    related_profiles = profile.get("related_profiles") or []
    if related_profiles:
        compact_related: list[str] = []
        for item in related_profiles[:4]:
            name = _truncate_for_prompt(item.get("name") or "Yakın çevre", 80)
            relationship = _truncate_for_prompt(item.get("relationship") or "", 40)
            notes = _truncate_for_prompt(item.get("notes") or item.get("preferences") or "", 100)
            label = f"{name} ({relationship})" if relationship else name
            compact_related.append(label + (f": {notes}" if notes else ""))
        lines.append(f"- Yakın çevre profilleri: {'; '.join(compact_related)}")
    return lines


def _empty_profile_payload(office_id: str) -> dict:
    return {
        "office_id": office_id,
        "display_name": "",
        "favorite_color": "",
        "food_preferences": "",
        "transport_preference": "",
        "weather_preference": "",
        "travel_preferences": "",
        "communication_style": "",
        "assistant_notes": "",
        "important_dates": [],
        "related_profiles": [],
        "created_at": None,
        "updated_at": None,
    }


def _empty_assistant_runtime_profile_payload(office_id: str) -> dict:
    return {
        "office_id": office_id,
        "assistant_name": "",
        "role_summary": "Kaynak dayanaklı hukuk çalışma asistanı",
        "tone": "Net ve profesyonel",
        "avatar_path": "",
        "soul_notes": "",
        "tools_notes": "",
        "heartbeat_extra_checks": [],
        "created_at": None,
        "updated_at": None,
    }


def _assistant_home_payload(settings, store: Persistence) -> dict[str, Any]:
    home = build_assistant_home(store, settings.office_id, settings=settings)
    onboarding = _assistant_onboarding_state(settings, store)
    merged_requires_setup = list(onboarding.get("setup_items") or []) + list(home.get("requires_setup") or [])
    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in merged_requires_setup:
        key = str(item.get("id") or "")
        if key in seen_ids:
            continue
        seen_ids.add(key)
        deduped.append(item)
    home["requires_setup"] = deduped
    home["onboarding"] = onboarding
    return home


def _should_drive_onboarding(query: str, *, prior_messages: list[dict], onboarding_state: dict[str, object], memory_updates: list[dict[str, Any]]) -> bool:
    if bool(onboarding_state.get("complete")):
        return False
    if bool(onboarding_state.get("blocked_by_setup")):
        return True
    normalized = _normalize_tr_text(query)
    if memory_updates:
        return True
    if len(prior_messages) <= 1:
        return True
    return any(token in normalized for token in ("merhaba", "selam", "benim", "bana", "senin", "adim", "ismim", "renk", "tercih", "sakaci", "samimi", "resmi"))


def _compose_assistant_onboarding_reply(query: str, *, home: dict[str, Any], onboarding_state: dict[str, object], memory_updates: list[dict[str, Any]]) -> dict[str, Any]:
    setup_items = list(onboarding_state.get("setup_items") or [])
    next_questions = list(onboarding_state.get("next_questions") or [])
    acknowledgements = [str(item.get("summary") or "").strip() for item in memory_updates if str(item.get("summary") or "").strip()]
    if setup_items:
        checklist = " ".join(f"{item.get('title')}: {item.get('details')}" for item in setup_items[:2])
        content = (
            ("Not aldım. " if acknowledgements else "")
            + "Önce ilk kurulum adımlarını tamamlayalım. "
            + checklist
            + " Hazır olduğunda Ayarlar ekranından sağlayıcını ve modelini bağla; sonra seni ve beni tanımaya sohbetten devam edeceğim."
        )
    elif next_questions:
        lead = " ".join(acknowledgements[:2]) + (" " if acknowledgements else "")
        next_reason = str(next_questions[0].get("reason") or "").strip()
        prompt_lead = "Sıradaki sorum şu:" if acknowledgements else "İlk sorum şu:"
        content = (
            f"{lead}Tam kişisel bir asistan kurmak için seni ve kendi çalışma tarzımı tek tek netleştiriyorum. "
            f"Soruları sırayla soracağım ve cevaplarını profile işleyeceğim. "
            f"{prompt_lead} {next_questions[0].get('question')}"
        )
        if next_reason:
            content = f"{content} Bunu sormamın nedeni: {next_reason}"
    else:
        content = (
            "Kurulum ana hatlarıyla tamamlandı. İstersen kendinle ilgili birkaç tercih daha paylaşabilirsin; ben de bunları kullanıcı belleğine işlerim."
        )
    return {
        "content": content.strip(),
        "assistant_summary": home.get("today_summary") or "",
        "tool_suggestions": _assistant_tool_suggestions(query, requires_setup=home.get("requires_setup") or []),
        "linked_entities": [],
        "draft_preview": None,
        "requires_approval": False,
        "generated_from": "assistant_onboarding_guide",
        "ai_provider": None,
        "ai_model": None,
        "source_context": {
            "priority_items": home.get("priority_items") or [],
            "requires_setup": home.get("requires_setup") or [],
            "onboarding": onboarding_state,
        },
    }


def _normalize_tr_text(value: str) -> str:
    return (
        str(value or "")
        .lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def _clean_onboarding_answer(value: str, *, limit: int = 240) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    cleaned = cleaned.strip("“”\"' ")
    cleaned = cleaned.strip(" .,:;!?")
    return cleaned[:limit]


def _append_profile_note(existing: str | None, note: str) -> str:
    candidate = _clean_onboarding_answer(note, limit=260)
    if not candidate:
        return str(existing or "").strip()
    current = str(existing or "").strip()
    if _normalize_tr_text(candidate) in _normalize_tr_text(current):
        return current
    if current:
        return f"{current}\n- {candidate}"
    return candidate


def _capture_direct_onboarding_answer(
    query: str,
    *,
    onboarding_state: dict[str, object],
    prior_messages: list[dict[str, object]],
    settings,
    store: Persistence,
) -> list[dict[str, Any]]:
    if bool(onboarding_state.get("complete")) or bool(onboarding_state.get("blocked_by_setup")):
        return []

    next_questions = list(onboarding_state.get("next_questions") or [])
    if not next_questions:
        return []

    last_assistant = next(
        (
            message
            for message in reversed(prior_messages)
            if str(message.get("role") or "") == "assistant"
        ),
        None,
    )
    if not last_assistant or str(last_assistant.get("generated_from") or "") != "assistant_onboarding_guide":
        return []

    normalized = _normalize_tr_text(query)
    operational_tokens = (
        "belge",
        "dosya",
        "takvim",
        "ajanda",
        "mail",
        "e posta",
        "mesaj",
        "whatsapp",
        "telegram",
        "tweet",
        "gonderi",
        "seyahat",
        "bilet",
        "tren",
        "ara",
        "bul",
        "ozet",
        "hazirla",
        "gonder",
    )
    if (
        _extract_calendar_candidate(query)
        or _is_document_inventory_query(query)
        or is_web_search_query(query)
        or is_travel_query(query)
        or is_travel_booking_query(query)
        or any(token in normalized for token in operational_tokens)
    ):
        return []

    answer = _clean_onboarding_answer(query)
    if not answer:
        return []

    if "?" in answer and len(answer.split()) > 3:
        return []

    next_question = next_questions[0]
    field = str(next_question.get("field") or "").strip()
    if not field:
        return []

    runtime_profile = store.get_assistant_runtime_profile(settings.office_id) or _empty_assistant_runtime_profile_payload(settings.office_id)
    profile = store.get_user_profile(settings.office_id) or _empty_profile_payload(settings.office_id)

    if field == "assistant_name":
        saved = store.upsert_assistant_runtime_profile(
            settings.office_id,
            assistant_name=answer,
            role_summary=runtime_profile.get("role_summary"),
            tone=runtime_profile.get("tone"),
            avatar_path=runtime_profile.get("avatar_path"),
            soul_notes=runtime_profile.get("soul_notes"),
            tools_notes=runtime_profile.get("tools_notes"),
            heartbeat_extra_checks=runtime_profile.get("heartbeat_extra_checks") or [],
        )
        return [
            {
                "kind": "assistant_persona_signal",
                "status": "stored",
                "summary": "Asistan adı kaydedildi.",
                "fields": ["assistant_name"],
                "updated_at": saved.get("updated_at"),
            }
        ]

    if field in {"tone", "soul_notes", "role_summary"}:
        patch = {
            "assistant_name": runtime_profile.get("assistant_name"),
            "role_summary": runtime_profile.get("role_summary"),
            "tone": runtime_profile.get("tone"),
            "avatar_path": runtime_profile.get("avatar_path"),
            "soul_notes": runtime_profile.get("soul_notes"),
            "tools_notes": runtime_profile.get("tools_notes"),
            "heartbeat_extra_checks": runtime_profile.get("heartbeat_extra_checks") or [],
        }
        if field == "soul_notes":
            patch[field] = _append_profile_note(runtime_profile.get(field), answer)
        else:
            patch[field] = answer
        saved = store.upsert_assistant_runtime_profile(settings.office_id, **patch)
        return [
            {
                "kind": "assistant_persona_signal",
                "status": "stored",
                "summary": "Asistan kimliği güncellendi.",
                "fields": [field],
                "updated_at": saved.get("updated_at"),
            }
        ]

    if field in {
        "display_name",
        "favorite_color",
        "food_preferences",
        "transport_preference",
        "weather_preference",
        "travel_preferences",
        "communication_style",
        "assistant_notes",
    }:
        patch = {
            "display_name": profile.get("display_name"),
            "favorite_color": profile.get("favorite_color"),
            "food_preferences": profile.get("food_preferences"),
            "transport_preference": profile.get("transport_preference"),
            "weather_preference": profile.get("weather_preference"),
            "travel_preferences": profile.get("travel_preferences"),
            "communication_style": profile.get("communication_style"),
            "assistant_notes": profile.get("assistant_notes"),
            "important_dates": profile.get("important_dates") or [],
            "related_profiles": profile.get("related_profiles") or [],
        }
        if field == "assistant_notes":
            patch[field] = _append_profile_note(profile.get(field), answer)
        else:
            patch[field] = answer
        saved = store.upsert_user_profile(settings.office_id, **patch)
        return [
            {
                "kind": "profile_signal",
                "status": "stored",
                "summary": "Kullanıcı profiline yeni bilgi işlendi.",
                "fields": [field],
                "updated_at": saved.get("updated_at"),
            }
        ]

    return []


def _safe_local_timezone():
    return datetime.now().astimezone().tzinfo or timezone.utc


def _month_number(value: str) -> int | None:
    months = {
        "ocak": 1,
        "subat": 2,
        "mart": 3,
        "nisan": 4,
        "mayis": 5,
        "haziran": 6,
        "temmuz": 7,
        "agustos": 8,
        "eylul": 9,
        "ekim": 10,
        "kasim": 11,
        "aralik": 12,
    }
    return months.get(_normalize_tr_text(value))


def _calendar_event_cues(query: str) -> bool:
    normalized = _normalize_tr_text(query)
    cues = [
        "takvime ekle",
        "ajandaya ekle",
        "isim var",
        "toplantim",
        "toplanti var",
        "toplanti",
        "gorusmem",
        "gorusme var",
        "gorusme",
        "durusmam",
        "durusma",
        "randevum",
        "randevu",
        "seyahatim",
        "seyahat",
        "ucusum",
        "ucus",
        "dogum gunu",
        "donum",
        "planim var",
        "etkinlik",
        "gidecegim",
        "orada olacagim",
        "hatirlat",
    ]
    return any(token in normalized for token in cues)


def _extract_calendar_candidate(query: str, *, now: datetime | None = None) -> dict | None:
    if not _calendar_event_cues(query):
        return None

    local_now = (now or datetime.now(_safe_local_timezone())).astimezone(_safe_local_timezone())
    normalized = _normalize_tr_text(query)
    matched_fragments: list[str] = []
    target_date: date | None = None

    iso_match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", query)
    if iso_match:
        try:
            target_date = date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            matched_fragments.append(iso_match.group(0))
        except ValueError:
            target_date = None

    if target_date is None:
        dotted_match = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b", query)
        if dotted_match:
            year = int(dotted_match.group(3))
            if year < 100:
                year += 2000
            try:
                target_date = date(year, int(dotted_match.group(2)), int(dotted_match.group(1)))
                matched_fragments.append(dotted_match.group(0))
            except ValueError:
                target_date = None

    if target_date is None:
        month_match = re.search(
            r"\b(\d{1,2})\s+(ocak|subat|mart|nisan|mayis|haziran|temmuz|agustos|eylul|ekim|kasim|aralik)(?:['’]?[dt][ae])?(?:\s+(20\d{2}))?\b",
            normalized,
        )
        if month_match:
            year = int(month_match.group(3)) if month_match.group(3) else local_now.year
            month_number = _month_number(month_match.group(2))
            if month_number:
                try:
                    target_date = date(year, month_number, int(month_match.group(1)))
                    matched_fragments.append(month_match.group(0))
                except ValueError:
                    target_date = None

    if target_date is None:
        if "obur gun" in normalized:
            target_date = (local_now + timedelta(days=2)).date()
            matched_fragments.append("öbür gün")
        elif "yarin" in normalized:
            target_date = (local_now + timedelta(days=1)).date()
            matched_fragments.append("yarın")
        elif "bugun" in normalized:
            target_date = local_now.date()
            matched_fragments.append("bugün")

    if target_date is None:
        return None

    time_match = re.search(r"\bsaat\s*(\d{1,2})[:.](\d{2})\b", normalized)
    if not time_match:
        time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", normalized)
    meridiem_match = re.search(r"\b(sabah|ogle|oglen|ogleden sonra|aksam|gece)\s+(\d{1,2})(?:[:.](\d{2}))?\b", normalized)
    defaulted_time = False
    hour = 9
    minute = 0
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        matched_fragments.append(time_match.group(0))
    elif meridiem_match:
        label = meridiem_match.group(1)
        hour = int(meridiem_match.group(2))
        minute = int(meridiem_match.group(3) or 0)
        if label in {"ogleden sonra", "aksam", "gece"} and hour < 12:
            hour += 12
        matched_fragments.append(meridiem_match.group(0))
    else:
        defaulted_time = True

    starts_at = datetime.combine(target_date, clock_time(hour=hour, minute=minute), tzinfo=_safe_local_timezone())
    ends_at = starts_at + timedelta(hours=1)

    title = query.strip()
    for fragment in matched_fragments:
        title = re.sub(re.escape(fragment), " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\b(takvime|ajandaya|ekle|ekler misin|ekleyeyim mi|benim|var|olacak|saat)\b", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" ,.-")
    if len(title) < 4:
        title = "Takvim planı"

    needs_preparation = any(
        token in normalized
        for token in ["toplanti", "gorusme", "durusma", "randevu", "sunum", "teslim", "seyahat", "ucus"]
    )
    return {
        "title": title,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "defaulted_time": defaulted_time,
        "needs_preparation": needs_preparation,
        "source_query": query.strip(),
    }


def _is_calendar_confirmation(query: str) -> bool:
    normalized = _normalize_tr_text(query)
    return normalized in {
        "ekle",
        "evet",
        "evet ekle",
        "tamam",
        "tamam ekle",
        "olur",
        "takvime ekle",
        "ajandaya ekle",
    }


def _is_calendar_rejection(query: str) -> bool:
    normalized = _normalize_tr_text(query)
    return normalized in {"hayir", "hayır", "vazgec", "vazgeç", "ekleme", "gerek yok", "bosver"}


def _format_turkish_datetime(value: str) -> str:
    month_labels = [
        "Ocak",
        "Şubat",
        "Mart",
        "Nisan",
        "Mayıs",
        "Haziran",
        "Temmuz",
        "Ağustos",
        "Eylül",
        "Ekim",
        "Kasım",
        "Aralık",
    ]
    dt = datetime.fromisoformat(value).astimezone(_safe_local_timezone())
    return f"{dt.day} {month_labels[dt.month - 1]} {dt.year} {dt:%H:%M}"


def _pending_calendar_event(messages: list[dict]) -> dict | None:
    for item in reversed(messages):
        if item.get("role") != "assistant":
            continue
        context = item.get("source_context") or {}
        candidate = context.get("pending_calendar_event")
        if isinstance(candidate, dict):
            return candidate
    return None


def _build_summary_prompt(*, matter: dict, chronology: dict, risk_notes: dict, tasks: list[dict], documents: list[dict], fallback_summary: str) -> str:
    chronology_lines = [f"- {item['date']}: {item['event']}" for item in chronology.get("items", [])[:4]]
    risk_lines = [f"- {item['title']}: {_truncate_for_prompt(item['details'], 180)}" for item in risk_notes.get("items", [])[:4]]
    task_lines = [f"- {task['title']}" for task in tasks if task.get("status") != "completed"][:4]
    document_lines = [f"- {doc.get('display_name') or doc.get('relative_path') or doc.get('filename')}" for doc in documents[:5]]
    return "\n".join(
        [
            "LawCopilot için kısa bir dosya özeti yaz.",
            "Kurallar:",
            "- Türkçe yaz.",
            "- Yalnız verilen bağlamı kullan.",
            "- Belirsiz kısımları kesinleştirme.",
            "- En fazla iki kısa paragraf yaz.",
            "",
            f"Dosya başlığı: {matter.get('title')}",
            f"Müvekkil: {matter.get('client_name') or 'Belirtilmedi'}",
            f"Durum: {matter.get('status') or 'active'}",
            f"Mevcut kayıtlı özet: {fallback_summary}",
            "",
            "Kronoloji:",
            *(chronology_lines or ["- Açık kronoloji kaydı yok."]),
            "",
            "Risk notları:",
            *(risk_lines or ["- Belirgin risk notu yok."]),
            "",
            "Açık görevler:",
            *(task_lines or ["- Açık görev yok."]),
            "",
            "Dayanak belgeler:",
            *(document_lines or ["- İndekslenmiş belge yok."]),
        ]
    )


def _build_risk_overview_prompt(*, matter: dict, chronology: dict, risk_notes: dict) -> str:
    chronology_issues = [f"- {issue['title']}: {_truncate_for_prompt(issue['details'], 180)}" for issue in chronology.get("issues", [])[:4]]
    risk_lines = [f"- {item['title']}: {_truncate_for_prompt(item['details'], 180)}" for item in risk_notes.get("items", [])[:5]]
    return "\n".join(
        [
            "LawCopilot için kısa bir risk değerlendirme üst özeti yaz.",
            "Kurallar:",
            "- Türkçe yaz.",
            "- Hukuki görüş verme; çalışma notu tonu koru.",
            "- En fazla dört cümle yaz.",
            "- Önce en kritik doğrulama ihtiyacını söyle.",
            "",
            f"Dosya: {matter.get('title')}",
            "Kronoloji sorunları:",
            *(chronology_issues or ["- Belirgin kronoloji sorunu yok."]),
            "",
            "Risk notları:",
            *(risk_lines or ["- Belirgin risk notu yok."]),
        ]
    )


def _build_draft_prompt(
    *,
    matter: dict,
    draft_type: str,
    target_channel: str,
    to_contact: str | None,
    instructions: str | None,
    source_context: dict,
    fallback_body: str,
    profile: dict | None = None,
) -> str:
    source_sections = [
        "Belgeler:",
        *(source_context.get("documents") or ["- Bağlı belge yok."]),
        "",
        "Kronoloji:",
        *(source_context.get("chronology") or ["- Açık kronoloji kaydı yok."]),
        "",
        "Risk notları:",
        *(source_context.get("risk_notes") or ["- Risk notu yok."]),
        "",
        "Açık görevler:",
        *(source_context.get("open_tasks") or ["- Açık görev yok."]),
    ]
    return "\n".join(
        [
            "LawCopilot için dış kullanımdan önce incelenecek bir çalışma taslağı yaz.",
            "Kurallar:",
            "- Türkçe yaz.",
            "- Yalnız sağlanan bağlamı kullan.",
            "- Hukuki kesin görüş gibi yazma; çalışma taslağı tonu koru.",
            "- Uygun olduğunda madde işaretleri kullan.",
            "",
            f"Dosya: {matter.get('title')}",
            f"Taslak türü: {draft_type}",
            f"Hedef kanal: {target_channel}",
            f"Alıcı: {to_contact or 'Belirtilmedi'}",
            f"Ek yönlendirme: {instructions or 'Yok'}",
            "",
            "Kullanıcı profili:",
            *(_profile_summary_lines(profile) or ["- Belirgin kullanıcı tercihi kaydı yok."]),
            "",
            "Referans iskelet:",
            fallback_body,
            "",
            *source_sections,
        ]
    )


def _assistant_source_ref_lines(source_refs: list[dict] | None) -> list[str]:
    lines: list[str] = []
    for ref in (source_refs or [])[:8]:
        label = str(ref.get("label") or ref.get("display_name") or ref.get("name") or ref.get("relative_path") or "Adsız ek")
        ref_type = str(ref.get("type") or "ek")
        extras: list[str] = []
        if ref.get("matter_id"):
            extras.append(f"dosya #{ref['matter_id']}")
        if ref.get("relative_path"):
            extras.append(str(ref.get("relative_path")))
        if ref.get("content_type"):
            extras.append(str(ref.get("content_type")))
        status = "bağlandı" if ref.get("uploaded") or ref.get("document_id") or ref.get("id") else "yalnız ad bilgisi"
        detail = ", ".join([status, *extras]) if extras else status
        lines.append(f"- {label} ({ref_type}; {detail})")
    return lines or ["- Ek kaynak yok."]


def _assistant_source_ref_entities(source_refs: list[dict] | None) -> list[dict]:
    entities: list[dict] = []
    for ref in (source_refs or [])[:8]:
        label = str(ref.get("label") or ref.get("display_name") or ref.get("name") or ref.get("relative_path") or "Adsız ek")
        entity_id = ref.get("document_id") or ref.get("id") or label
        entities.append(
            {
                "type": str(ref.get("type") or "attachment"),
                "id": entity_id,
                "label": label,
            }
        )
    return entities


def _build_workspace_search_prompt(*, query: str, citations: list[dict], related_documents: list[dict], attention_points: list[str], missing_document_signals: list[str], draft_suggestions: list[str], fallback_answer: str) -> str:
    citation_lines = _citation_prompt_lines(citations)
    related_lines = [
        f"- {item.get('document_name')}: {_truncate_for_prompt(item.get('reason') or '', 180)}"
        for item in related_documents[:4]
    ]
    return "\n".join(
        [
            "LawCopilot için çalışma alanı aramasına kısa, kaynak dayanaklı bir Türkçe özet yaz.",
            "Kurallar:",
            "- Yalnız verilen bağlamı kullan.",
            "- En fazla üç cümle yaz.",
            "- Belirsizlik varsa açıkça belirt.",
            "- Mümkünse [1], [2] gibi atıf etiketlerini kullan.",
            "",
            f"Sorgu: {query}",
            f"Mevcut fallback özeti: {fallback_answer}",
            "",
            "Dayanak pasajlar:",
            *(citation_lines or ["- Doğrudan dayanak bulunamadı."]),
            "",
            "İlgili belgeler:",
            *(related_lines or ["- İlgili belge yok."]),
            "",
            "Dikkat noktaları:",
            *(attention_points[:4] or ["- Belirgin ek dikkat noktası yok."]),
            "",
            "Eksik belge sinyalleri:",
            *(missing_document_signals[:4] or ["- Belirgin eksik belge sinyali yok."]),
            "",
            "Taslak önerileri:",
            *(draft_suggestions[:4] or ["- Taslak önerisi yok."]),
        ]
    )


def _assistant_tool_key(query: str) -> str:
    normalized = str(query or "").lower()
    if any(token in normalized for token in ["bilet", "seyahat", "uçuş", "ucus", "otel", "rota"]):
        return "calendar"
    if any(token in normalized for token in ["internette", "webde", "web'de", "araştır", "güncel bilgi"]):
        return "runtime"
    if any(token in normalized for token in ["bugün", "yapılacak", "ajanda"]):
        return "today"
    if any(token in normalized for token in ["takvim", "yarın", "toplantı", "randevu"]):
        return "calendar"
    if any(token in normalized for token in ["benzer dosya", "çalışma alanı", "belge havuzu", "workspace"]):
        return "workspace"
    if any(token in normalized for token in ["belge", "alıntı", "pasaj", "kaynak"]):
        return "documents"
    if any(token in normalized for token in ["taslak", "mail", "e-posta", "telegram yanıt"]):
        return "drafts"
    if any(token in normalized for token in ["model", "telegram", "google", "ayar", "bağlantı", "runtime"]):
        return "runtime"
    if any(token in normalized for token in ["dosya", "müvekkil", "dava"]):
        return "matters"
    return "today"


def _assistant_tool_suggestions(query: str, *, requires_setup: list[dict[str, object]] | None = None) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    primary = _assistant_tool_key(query)
    labels = {
        "today": "Bugün",
        "calendar": "Takvim",
        "workspace": "Çalışma Alanı",
        "matters": "Dosyalar",
        "documents": "Belgeler",
        "drafts": "Taslaklar",
        "runtime": "Durum",
    }
    reasons = {
        "today": "Ajanda, iletişim ve takvim sinyalleri burada toplanır.",
        "calendar": "Yaklaşan hazırlık ve toplantılar burada görünür.",
        "workspace": "Çalışma klasörü tarama, arama ve benzer belge incelemesi burada yapılır.",
        "matters": "Dosya bağlamı ve müvekkil işi yönetimi burada tutulur.",
        "documents": "Kaynak pasajlar ve belge inceleme araçları burada bulunur.",
        "drafts": "Taslaklar, onay bekleyen dış aksiyonlar ve gönderim durumu burada görünür.",
        "runtime": "Model, Google ve Telegram bağlantı durumları burada görünür.",
    }
    suggestions.append({"tool": primary, "label": labels[primary], "reason": reasons[primary]})
    if requires_setup:
        suggestions.append({"tool": "runtime", "label": labels["runtime"], "reason": "Kurulum eksikleri önce burada tamamlanmalı."})
    return suggestions


def _assistant_onboarding_questions(settings, store: Persistence) -> list[dict[str, str]]:
    profile = store.get_user_profile(settings.office_id)
    runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
    workspace_root = store.get_active_workspace_root(settings.office_id)
    questions: list[dict[str, str]] = []
    if not workspace_root:
        questions.append(
            {
                "id": "workspace-root",
                "field": "workspace_root",
                "target": "system",
                "question": "Önce çalışma klasörünü Ayarlar ekranından seçelim. Hazır olduğunda bana haber ver.",
                "reason": "Kaynak erişimi seçili klasör ve alt klasörleriyle sınırlı.",
            }
        )
    if not settings.provider_configured:
        questions.append(
            {
                "id": "provider-setup",
                "field": "provider_type",
                "target": "system",
                "question": "Önce Ayarlar'dan bir model sağlayıcısı bağlayalım. Codex mi Gemini mi kullanmak istiyorsun?",
                "reason": "İlk sohbetten sonra modeli seçip doğrudan onunla devam edeceğim.",
            }
        )
    if settings.provider_configured and not str(settings.provider_model or "").strip():
        questions.append(
            {
                "id": "provider-model",
                "field": "provider_model",
                "target": "system",
                "question": "Bağladığın sağlayıcı için hangi modeli varsayılan kullanayım?",
                "reason": "Masaüstü açılışında ve ilk sohbetlerde bu model kullanılacak.",
            }
        )
    if not str(runtime_profile.get("assistant_name") or "").strip():
        questions.append(
            {
                "id": "assistant-name",
                "field": "assistant_name",
                "target": "assistant",
                "question": "Ben senin için nasıl bir asistan olayım? Bana bir isim ver.",
                "reason": "Bu bilgi IDENTITY.md ve ayarlardaki asistan profiline yazılacak.",
            }
        )
    if not str(runtime_profile.get("tone") or "").strip() or str(runtime_profile.get("tone") or "").strip() == "Net ve profesyonel":
        questions.append(
            {
                "id": "assistant-tone",
                "field": "tone",
                "target": "assistant",
                "question": "Nasıl konuşayım: daha şakacı, daha ciddi, daha kısa, daha sıcak, yoksa başka bir tarz mı?",
                "reason": "Konuşma tonumu ve persona notlarımı buna göre güncelleyeceğim.",
            }
        )
    if not str(runtime_profile.get("soul_notes") or "").strip():
        questions.append(
            {
                "id": "assistant-boundaries",
                "field": "soul_notes",
                "target": "assistant",
                "question": "Benden özellikle nasıl davranmamı beklersin? Daha proaktif mi olayım, daha temkinli mi olayım, hangi sınırları hep koruyayım?",
                "reason": "Asistan davranışını ve çalışma sınırlarını buna göre kuracağım.",
            }
        )
    if not str(runtime_profile.get("role_summary") or "").strip() or str(runtime_profile.get("role_summary") or "").strip() == "Kaynak dayanaklı hukuk çalışma asistanı":
        questions.append(
            {
                "id": "assistant-role",
                "field": "role_summary",
                "target": "assistant",
                "question": "Rolümü nasıl tanımlayayım? Örneğin kişisel hukuk asistanı, operasyon koçu veya daha farklı bir şey olabilir.",
                "reason": "Bu tanım AGENTS.md ve IDENTITY.md içine yansıyacak.",
            }
        )
    if not str(profile.get("display_name") or "").strip():
        questions.append(
            {
                "id": "user-name",
                "field": "display_name",
                "target": "user",
                "question": "Sana nasıl hitap edeyim?",
                "reason": "Bu bilgi USER.md ve kişisel profil kartına yazılacak.",
            }
        )
    if not str(profile.get("favorite_color") or "").strip():
        questions.append(
            {
                "id": "favorite-color",
                "field": "favorite_color",
                "target": "user",
                "question": "Hangi rengi seversin?",
                "reason": "Kişisel tercih bağlamını daha iyi kurmak istiyorum.",
            }
        )
    if not str(profile.get("communication_style") or "").strip():
        questions.append(
            {
                "id": "communication-style",
                "field": "communication_style",
                "target": "user",
                "question": "Sana kısa ve net mi, yoksa daha detaylı mı cevap vermemi istersin?",
                "reason": "Yanıt biçimimi senin tercihine göre ayarlayacağım.",
            }
        )
    if not str(profile.get("assistant_notes") or "").strip():
        questions.append(
            {
                "id": "work-rhythm",
                "field": "assistant_notes",
                "target": "user",
                "question": "Gün içinde seni en çok hangi konularda desteklememi istersin? Örneğin duruşma hazırlığı, müvekkil takibi, dosya eksikleri, seyahat planı veya aile hatırlatmaları gibi.",
                "reason": "Günlük proaktif öneri ve takip mantığını buna göre kuracağım.",
            }
        )
    if not str(profile.get("transport_preference") or "").strip():
        questions.append(
            {
                "id": "transport-preference",
                "field": "transport_preference",
                "target": "user",
                "question": "Genelde hangi ulaşım aracını tercih edersin?",
                "reason": "Ajanda, seyahat ve günlük önerilerimi buna göre şekillendireceğim.",
            }
        )
    if not str(profile.get("food_preferences") or "").strip():
        questions.append(
            {
                "id": "food-preferences",
                "field": "food_preferences",
                "target": "user",
                "question": "Yeme içme tarafında özellikle sevdiğin veya kaçındığın şeyler var mı?",
                "reason": "Kişisel hatırlatmalar ve önerilerde bunu kullanacağım.",
            }
        )
    if not str(profile.get("travel_preferences") or "").strip():
        questions.append(
            {
                "id": "travel-preferences",
                "field": "travel_preferences",
                "target": "user",
                "question": "Seyahat ederken özellikle sevdiğin bir düzen var mı? Örneğin tren, pencere kenarı, erken planlama gibi.",
                "reason": "Seyahat planı ve hazırlık önerilerini buna göre vereceğim.",
            }
        )
    if not str(profile.get("weather_preference") or "").strip():
        questions.append(
            {
                "id": "weather-preference",
                "field": "weather_preference",
                "target": "user",
                "question": "Nasıl havaları seversin veya sevmezsin?",
                "reason": "Günlük öneriler ve kişisel hatırlatma dilini buna göre kuracağım.",
            }
        )
    if not list(profile.get("related_profiles") or []):
        questions.append(
            {
                "id": "related-profiles",
                "field": "related_profiles",
                "target": "user",
                "question": "Hayatında benim bilmem gereken yakın kişiler var mı? Eşin, çocuğun, annen, baban veya düzenli ilgilendiğin biri varsa bunu da tanımak isterim.",
                "reason": "Önemli tarihleri, hatırlatmaları ve kişisel önerileri buna göre zenginleştireceğim.",
            }
        )
    if not list(profile.get("important_dates") or []):
        questions.append(
            {
                "id": "important-dates",
                "field": "important_dates",
                "target": "user",
                "question": "Unutmamı istemediğin önemli tarihler var mı? Doğum günleri, yıldönümleri, görüşmeler veya özel hatırlatmalar gibi.",
                "reason": "Takvim boşluklarını ve hazırlık önerilerini bunlara göre kuracağım.",
            }
        )
    return questions


def _assistant_onboarding_state(settings, store: Persistence) -> dict[str, object]:
    profile = store.get_user_profile(settings.office_id) or _empty_profile_payload(settings.office_id)
    runtime_profile = store.get_assistant_runtime_profile(settings.office_id) or _empty_assistant_runtime_profile_payload(settings.office_id)
    workspace_root = store.get_active_workspace_root(settings.office_id)
    questions = _assistant_onboarding_questions(settings, store)

    provider_connected = bool(settings.provider_configured and str(settings.provider_type or "").strip())
    model_selected = bool(str(settings.provider_model or "").strip())
    assistant_named = bool(str(runtime_profile.get("assistant_name") or "").strip())
    assistant_persona_defined = bool(
        str(runtime_profile.get("soul_notes") or "").strip()
        or str(runtime_profile.get("role_summary") or "").strip() not in {"", "Kaynak dayanaklı hukuk çalışma asistanı"}
        or str(runtime_profile.get("tone") or "").strip() not in {"", "Net ve profesyonel"}
    )
    user_named = bool(str(profile.get("display_name") or "").strip())
    preference_count = sum(
        1
        for field in (
            "favorite_color",
            "food_preferences",
            "transport_preference",
            "weather_preference",
            "travel_preferences",
            "communication_style",
        )
        if str(profile.get(field) or "").strip()
    )
    user_context_defined = bool(str(profile.get("assistant_notes") or "").strip()) or preference_count >= 2

    workspace_ready = bool(workspace_root)
    provider_ready = provider_connected
    model_ready = model_selected
    assistant_ready = assistant_named and assistant_persona_defined
    user_ready = user_named and user_context_defined

    setup_items: list[dict[str, object]] = []
    if not workspace_ready:
        setup_items.append(
            {
                "id": "setup-workspace",
                "title": "Çalışma klasörünü seçin",
                "details": "Masaüstü uygulaması yalnız seçilen klasör ve alt klasörlerinde çalışır.",
                "action": "open_settings",
                "route": "/settings",
            }
        )
    if not provider_connected:
        setup_items.append(
            {
                "id": "setup-provider",
                "title": "Bir model sağlayıcısı bağlayın",
                "details": "Gemini API, OpenAI API, Codex OAuth veya yerel Ollama ile başlayabilirsiniz.",
                "action": "open_settings",
                "route": "/settings",
            }
        )
    elif not model_selected:
        setup_items.append(
            {
                "id": "setup-provider-model",
                "title": "Varsayılan modeli seçin",
                "details": "Bağlanan sağlayıcıdan kullanmak istediğiniz modeli seçin.",
                "action": "open_settings",
                "route": "/settings",
            }
        )

    workspace_ready = bool(workspace_root)
    if not workspace_ready:
        stage = "workspace"
    elif not provider_ready:
        stage = "provider"
    elif not model_ready:
        stage = "model"
    elif not assistant_ready:
        stage = "assistant"
    elif not user_ready:
        stage = "user"
    else:
        stage = "complete"
    complete = workspace_ready and provider_ready and model_ready and assistant_ready and user_ready
    next_question = questions[0]["question"] if questions else ""
    summary = (
        "Kurulum tamamlandı."
        if complete
        else "Asistan ilk görüşmede önce kendi kimliğini, sonra seni, çalışma düzenini ve kişisel tercihlerini tanıyacak."
    )
    suggested_prompts = [item["question"] for item in questions[:4]]
    interview_intro = (
        "İlk açılışta asistan seninle kısa bir tanışma röportajı yapar. Soruları tek tek sorar, cevaplarını profile işler ve zamanla daha kişisel öneriler üretir."
    )
    return {
        "complete": complete,
        "stage": stage,
        "summary": summary,
        "blocked_by_setup": bool(setup_items),
        "workspace_ready": workspace_ready,
        "workspace_configured": workspace_ready,
        "provider_ready": provider_ready,
        "provider_connected": provider_connected,
        "model_ready": model_ready,
        "model_selected": model_selected,
        "assistant_ready": assistant_ready,
        "assistant_named": assistant_named,
        "assistant_persona_defined": assistant_persona_defined,
        "user_ready": user_ready,
        "user_named": user_named,
        "user_context_defined": user_context_defined,
        "provider_type": str(settings.provider_type or ""),
        "provider_model": str(settings.provider_model or ""),
        "selected_model": str(settings.provider_model or ""),
        "workspace_root_name": workspace_root.get("display_name") if workspace_root else None,
        "next_question": next_question,
        "next_questions": questions[:4],
        "setup_items": setup_items,
        "questions": questions[:8],
        "suggested_prompts": suggested_prompts,
        "interview_intro": interview_intro,
        "interview_topics": [
            "Asistanın adı, tonu ve çalışma tarzı",
            "Size nasıl hitap edeceği",
            "Renk, iletişim, ulaşım, seyahat ve yeme içme tercihleri",
            "Aile ve yakın çevre bilgileri",
            "Önemli tarihler ve rutinler",
            "Hangi işlerde proaktif davranması gerektiği",
        ],
        "starter_prompts": [
            "Tanışma görüşmesini başlatalım.",
            "Önce senin adını ve nasıl davranmanı istediğimi konuşalım.",
            "Sonra benim alışkanlıklarımı ve önemli kişileri konuşalım.",
        ],
        "profile": {
            "display_name": profile.get("display_name") or "",
            "favorite_color": profile.get("favorite_color") or "",
            "transport_preference": profile.get("transport_preference") or "",
            "communication_style": profile.get("communication_style") or "",
        },
        "assistant_profile": {
            "assistant_name": runtime_profile.get("assistant_name") or "",
            "tone": runtime_profile.get("tone") or "",
            "role_summary": runtime_profile.get("role_summary") or "",
        },
    }


def _is_onboarding_turn(query: str, prior_messages: list[dict[str, object]], onboarding_state: dict[str, object]) -> bool:
    if bool(onboarding_state.get("complete")):
        return False
    normalized = _normalize_tr_text(query)
    operational_tokens = (
        "belge",
        "dosya",
        "takvim",
        "ajanda",
        "mail",
        "e posta",
        "mesaj",
        "whatsapp",
        "telegram",
        "tweet",
        "gonderi",
        "seyahat",
        "bilet",
        "tren",
        "ara",
        "bul",
        "ozet",
        "hazirla",
        "gonder",
    )
    if (
        _extract_calendar_candidate(query)
        or _is_document_inventory_query(query)
        or is_web_search_query(query)
        or is_travel_query(query)
        or is_travel_booking_query(query)
        or any(token in normalized for token in operational_tokens)
    ):
        return False
    if not prior_messages:
        return True
    return any(
        token in normalized
        for token in (
            "merhaba",
            "selam",
            "tanisalim",
            "taniyalim",
            "sen kimsin",
            "ben kimim",
            "profil",
            "ayar",
        )
    )


def _append_onboarding_followup(
    content: str,
    onboarding_state: dict[str, object],
    *,
    memory_updates: list[dict[str, object]] | None = None,
) -> str:
    if bool(onboarding_state.get("complete")):
        return content
    next_question = str(onboarding_state.get("next_question") or "").strip()
    if not next_question:
        return content
    prefix = "Bunu da profile işledim." if memory_updates else "Kurulumu biraz daha kişiselleştirelim."
    if next_question in content:
        return content
    return f"{content}\n\n{prefix} {next_question}".strip()


def _assistant_home_context_text(home: dict, agenda: list[dict], inbox: list[dict], calendar: list[dict]) -> str:
    lines = [
        f"Günlük özet: {home.get('today_summary') or 'Özet yok.'}",
        "",
        "Öncelikli maddeler:",
    ]
    for item in home.get("priority_items", [])[:4]:
        lines.append(f"- {item.get('title')}: {_truncate_for_prompt(item.get('details') or '', 180)}")
    lines.extend(["", "Cevap bekleyen iletişimler:"])
    for item in inbox[:3]:
        lines.append(f"- {item.get('title')}: {_truncate_for_prompt(item.get('details') or '', 160)}")
    lines.extend(["", "Takvim:"])
    for item in calendar[:3]:
        lines.append(f"- {item.get('title')} ({item.get('starts_at')})")
    lines.extend(["", "Ajanda:"])
    for item in agenda[:4]:
        lines.append(f"- {item.get('title')}: {_truncate_for_prompt(item.get('details') or '', 160)}")
    return "\n".join(lines)


def _assistant_document_label(item: dict | None) -> str:
    payload = item or {}
    return str(
        payload.get("relative_path")
        or payload.get("filename")
        or payload.get("display_name")
        or payload.get("name")
        or "Belge"
    ).strip()


def _assistant_document_inventory(store: Persistence, office_id: str, matter_id: int | None) -> dict[str, object]:
    root = store.get_active_workspace_root(office_id)
    workspace_documents = store.list_workspace_documents(office_id, int(root["id"])) if root else []
    matter_documents = store.list_matter_documents(office_id, matter_id) if matter_id else []
    linked_workspace_documents = store.list_matter_workspace_documents(office_id, matter_id) if matter_id else []
    drive_files = store.list_drive_files(office_id, limit=50)

    seen_matter_keys: set[str] = set()
    compact_matter_documents: list[dict[str, object]] = []
    for item in (matter_documents or []) + (linked_workspace_documents or []):
        label = _assistant_document_label(item)
        key = f"{label}|{item.get('relative_path') or item.get('source_ref') or item.get('id') or item.get('workspace_document_id')}"
        if key in seen_matter_keys:
            continue
        seen_matter_keys.add(key)
        compact_matter_documents.append(
            {
                "label": label,
                "status": item.get("ingest_status") or item.get("indexed_status") or "ready",
            }
        )

    compact_workspace_documents = [
        {
            "label": _assistant_document_label(item),
            "status": item.get("indexed_status") or item.get("ingest_status") or "ready",
        }
        for item in (workspace_documents or [])
    ]
    compact_drive_files = [
        {
            "label": str(item.get("name") or "Drive dosyası").strip(),
            "status": "drive",
            "mime_type": item.get("mime_type") or "",
        }
        for item in (drive_files or [])
    ]

    prompt_lines = ["Belge envanteri:"]
    if root:
        prompt_lines.append(
            f"- Çalışma alanı: {_truncate_for_prompt(str(root.get('display_name') or root.get('root_path') or 'Çalışma alanı'), 140)}"
        )
    else:
        prompt_lines.append("- Çalışma alanı seçili değil.")

    prompt_lines.append("- Çalışma alanındaki son belgeler:")
    for item in compact_workspace_documents[:8]:
        prompt_lines.append(f"  - {item['label']} ({item['status']})")
    if not compact_workspace_documents:
        prompt_lines.append("  - Çalışma alanında belge görünmüyor.")

    prompt_lines.append("- Google Drive son dosyaları:")
    for item in compact_drive_files[:8]:
        prompt_lines.append(f"  - {item['label']} ({item['status']})")
    if not compact_drive_files:
        prompt_lines.append("  - Google Drive tarafında dosya görünmüyor.")

    if matter_id:
        prompt_lines.append("- Etkin dosyadaki belgeler:")
        for item in compact_matter_documents[:8]:
            prompt_lines.append(f"  - {item['label']} ({item['status']})")
        if not compact_matter_documents:
            prompt_lines.append("  - Etkin dosyada belge görünmüyor.")

    return {
        "workspace_root_name": root.get("display_name") if root else None,
        "workspace_count": len(compact_workspace_documents),
        "workspace_documents": compact_workspace_documents[:8],
        "google_drive_count": len(compact_drive_files),
        "google_drive_files": compact_drive_files[:8],
        "matter_count": len(compact_matter_documents),
        "matter_documents": compact_matter_documents[:8],
        "prompt_text": "\n".join(prompt_lines),
    }


def _is_document_inventory_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    patterns = [
        "elimde hangi belge",
        "elimde hangi belgeler",
        "hangi belge var",
        "hangi belgeler var",
        "belgeler neler",
        "belge listesi",
        "belge envanteri",
        "hangi dosyalar var",
        "hangi dokümanlar var",
        "hangi dokumanlar var",
    ]
    return any(pattern in normalized for pattern in patterns)


def _assistant_document_inventory_reply(document_inventory: dict[str, object], *, matter_id: int | None) -> str:
    workspace_documents = list(document_inventory.get("workspace_documents") or [])
    google_drive_files = list(document_inventory.get("google_drive_files") or [])
    matter_documents = list(document_inventory.get("matter_documents") or [])
    workspace_count = int(document_inventory.get("workspace_count") or 0)
    google_drive_count = int(document_inventory.get("google_drive_count") or 0)
    matter_count = int(document_inventory.get("matter_count") or 0)
    workspace_root_name = str(document_inventory.get("workspace_root_name") or "").strip()

    lines: list[str] = []
    if matter_id:
        if matter_count:
            labels = ", ".join(str(item.get("label") or "Belge") for item in matter_documents[:6])
            extra = max(0, matter_count - min(matter_count, 6))
            sentence = f"Etkin dosyada {matter_count} belge görüyorum: {labels}"
            lines.append(sentence + (f" ve {extra} belge daha." if extra else "."))
        else:
            lines.append("Etkin dosyada henüz kayıtlı belge görünmüyor.")

    if workspace_count:
        labels = ", ".join(str(item.get("label") or "Belge") for item in workspace_documents[:6])
        extra = max(0, workspace_count - min(workspace_count, 6))
        scope_label = workspace_root_name or "Çalışma alanında"
        sentence = f"{scope_label} toplam {workspace_count} belge var: {labels}"
        lines.append(sentence + (f" ve {extra} belge daha." if extra else "."))
    elif workspace_root_name:
        lines.append(f"{workspace_root_name} içinde henüz belge görünmüyor.")
    else:
        lines.append("Henüz seçili bir çalışma alanı görünmüyor, bu yüzden belge envanteri çıkaramıyorum.")

    if google_drive_count:
        labels = ", ".join(str(item.get("label") or "Drive dosyası") for item in google_drive_files[:6])
        extra = max(0, google_drive_count - min(google_drive_count, 6))
        sentence = f"Google Drive tarafında {google_drive_count} dosya görüyorum: {labels}"
        lines.append(sentence + (f" ve {extra} dosya daha." if extra else "."))

    if workspace_count or matter_count or google_drive_count:
        lines.append("İstersen bunları türüne, dosyasına veya son güncellenene göre de sıralayabilirim.")
    return " ".join(lines)


def _build_similarity_explanation_prompt(*, source_document_name: str, items: list[dict], fallback_explanation: str) -> str:
    item_lines = [
        (
            f"- Belge: {item.get('belge_adi')} | Skor: {item.get('benzerlik_puani')} | "
            f"Neden: {_truncate_for_prompt(item.get('neden_benzer') or '', 180)} | "
            f"Klasör: {item.get('klasor_baglami')}"
        )
        for item in items[:4]
    ]
    return "\n".join(
        [
            "LawCopilot için benzer belge sonuçlarını açıklayan kısa bir Türkçe özet yaz.",
            "Kurallar:",
            "- Yalnız verilen bağlamı kullan.",
            "- Benzerlik sonucunu kesin hüküm gibi sunma.",
            "- En fazla üç cümle yaz.",
            "",
            f"Kaynak belge: {source_document_name}",
            f"Mevcut fallback açıklaması: {fallback_explanation}",
            "",
            "Benzer belge adayları:",
            *(item_lines or ["- Benzer belge adayı yok."]),
        ]
    )


def _google_status_payload(settings, store: Persistence) -> dict:
    account = store.get_connected_account(settings.office_id, "google")
    scopes = list(account.get("scopes") or settings.google_scopes) if account else list(settings.google_scopes)
    account_status = str(account.get("status") or "").strip().lower() if account else ""
    metadata = dict(account.get("metadata") or {}) if account else {}
    calendar_write_ready = any(
        scope in {
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar",
        }
        for scope in scopes
    )
    gmail_connected = bool(
        settings.gmail_connected
        or metadata.get("gmail_connected")
        or any("gmail" in str(scope) for scope in scopes)
        or len(store.list_email_threads(settings.office_id)) > 0
    )
    calendar_connected = bool(
        settings.calendar_connected
        or metadata.get("calendar_connected")
        or any("calendar" in str(scope) for scope in scopes)
        or len(store.list_calendar_events(settings.office_id, limit=10)) > 0
    )
    drive_connected = bool(
        settings.drive_connected
        or metadata.get("drive_connected")
        or any("drive" in str(scope) for scope in scopes)
        or len(store.list_drive_files(settings.office_id, limit=10)) > 0
    )
    configured = bool(settings.google_configured or account_status == "connected" or scopes)
    return {
        "provider": "google",
        "configured": configured,
        "enabled": bool(settings.google_enabled or account),
        "account_label": (account.get("account_label") if account else None) or settings.google_account_label,
        "scopes": scopes,
        "gmail_connected": gmail_connected,
        "calendar_connected": calendar_connected,
        "drive_connected": drive_connected,
        "calendar_write_ready": calendar_write_ready,
        "status": account.get("status") if account else ("connected" if configured else "pending"),
        "email_thread_count": len(store.list_email_threads(settings.office_id)),
        "calendar_event_count": len(store.list_calendar_events(settings.office_id, limit=200)),
        "drive_file_count": len(store.list_drive_files(settings.office_id, limit=200)),
        "last_sync_at": account.get("last_sync_at") if account else None,
        "connected_account": account,
        "desktop_managed": True,
    }


def _telegram_status_payload(settings, store: Persistence) -> dict:
    account = store.get_connected_account(settings.office_id, "telegram")
    return {
        "provider": "telegram",
        "configured": bool(settings.telegram_configured or (account and account.get("status") == "connected")),
        "enabled": bool(settings.telegram_enabled or account),
        "account_label": (account.get("account_label") if account else None) or settings.telegram_bot_username or "Telegram botu",
        "status": account.get("status") if account else ("connected" if settings.telegram_configured else "pending"),
        "allowed_user_id": settings.telegram_allowed_user_id,
        "connected_account": account,
        "desktop_managed": True,
    }


def _whatsapp_status_payload(settings, store: Persistence) -> dict:
    account = store.get_connected_account(settings.office_id, "whatsapp")
    message_count = len(store.list_whatsapp_messages(settings.office_id, limit=200))
    metadata = dict(account.get("metadata") or {}) if account else {}
    configured = bool(settings.whatsapp_configured or (account and account.get("status") == "connected"))
    return {
        "provider": "whatsapp",
        "configured": configured,
        "enabled": bool(settings.whatsapp_enabled or account),
        "account_label": (account.get("account_label") if account else None) or settings.whatsapp_account_label or "WhatsApp hesabı",
        "phone_number_id": settings.whatsapp_phone_number_id or metadata.get("phone_number_id") or "",
        "display_phone_number": settings.whatsapp_display_phone_number or metadata.get("display_phone_number") or "",
        "status": account.get("status") if account else ("connected" if configured else "pending"),
        "message_count": message_count,
        "last_sync_at": account.get("last_sync_at") if account else None,
        "connected_account": account,
        "desktop_managed": True,
    }


def _x_status_payload(settings, store: Persistence) -> dict:
    account = store.get_connected_account(settings.office_id, "x")
    mentions = store.list_x_posts(settings.office_id, post_type="mention", limit=200)
    posts = store.list_x_posts(settings.office_id, post_type="post", limit=200)
    configured = bool(settings.x_configured or (account and account.get("status") == "connected"))
    scopes = list(account.get("scopes") or settings.x_scopes) if account else list(settings.x_scopes)
    return {
        "provider": "x",
        "configured": configured,
        "enabled": bool(settings.x_enabled or account),
        "account_label": (account.get("account_label") if account else None) or settings.x_account_label or "X hesabı",
        "user_id": settings.x_user_id or (dict(account.get("metadata") or {}).get("user_id") if account else "") or "",
        "scopes": scopes,
        "status": account.get("status") if account else ("connected" if configured else "pending"),
        "mention_count": len(mentions),
        "post_count": len(posts),
        "last_sync_at": account.get("last_sync_at") if account else None,
        "connected_account": account,
        "desktop_managed": True,
    }


def _matter_search_result(
    *,
    matter_id: int,
    payload: MatterSearchRequest,
    role: str,
    subject: str,
    sid: str,
    router: ModelRouter,
    store: Persistence,
    rag_meta: dict,
    audit: AuditLogger,
    events: StructuredLogger,
    runtime,
    office_id: str,
) -> dict:
    selected = router.choose(payload.query, payload.model_profile)
    rows = store.search_document_chunks(
        office_id,
        matter_id,
        document_ids=payload.document_ids,
        source_types=payload.source_types,
        filename_contains=payload.filename_contains,
    )
    if rows is None:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
    linked_workspace_rows = store.search_linked_workspace_chunks(office_id, matter_id) or []
    rows = rows + linked_workspace_rows

    citations = score_chunk_records(payload.query, rows, k=payload.limit)
    support_level = _support_level(citations)
    manual_review_required = support_level in {"none", "low"}
    related_documents_map: dict[int, dict] = {}
    for citation in citations:
        document_id = int(citation["document_id"])
        current = related_documents_map.get(document_id)
        if current is None or float(citation["relevance_score"]) > float(current["max_score"]):
            related_documents_map[document_id] = {
                "document_id": document_id,
                "document_name": citation["document_name"],
                "matter_id": matter_id,
                "max_score": citation["relevance_score"],
                "reason": "Aynı dosya kapsamında sorguyla örtüşen pasaj bulundu.",
            }

    related_documents = sorted(related_documents_map.values(), key=lambda item: item["max_score"], reverse=True)
    coverage = round(min(1.0, sum(float(c["relevance_score"]) for c in citations[:3])), 2) if citations else 0.0
    fallback_answer = (
        f"Bu dosya kapsamında {len(related_documents)} belge ve {len(citations)} destekleyici pasaj bulundu. "
        f"En güçlü dayanak: {citations[0]['document_name']}."
        if citations
        else "Bu dosya kapsamında sorguyu doğrudan destekleyen bir kaynak bulunamadı."
    )

    audit_seed = f"matter:{matter_id}:{payload.query}:{subject}:{selected['profile']}"
    audit_id = hashlib.sha256(audit_seed.encode()).hexdigest()[:16]
    audit.log(
        "matter_search",
        subject=subject,
        role=role,
        session_id=sid,
        matter_id=matter_id,
        audit_id=audit_id,
        source_count=len(citations),
        document_count=len(related_documents),
    )
    runtime_completion = None
    if citations:
        runtime_prompt = "\n".join(
            [
                "LawCopilot için kısa, kaynak dayanaklı bir dosya arama cevabı üret.",
                "Kurallar:",
                "- Cevabı Türkçe yaz.",
                "- Sadece aşağıdaki dayanaklardan yararlan.",
                "- Dayanak dışı kesin iddia kurma.",
                "- Mümkün olduğunda [1], [2] gibi atıf etiketlerini kullan.",
                "",
                f"Dosya sorgusu: {payload.query}",
                f"Dosya kimliği: {matter_id}",
                "",
                "Dayanak pasajlar:",
                *_citation_prompt_lines(citations),
            ]
        )
        runtime_completion = _maybe_runtime_completion(
            runtime,
            runtime_prompt,
            events,
            task="matter_search_answer",
            matter_id=matter_id,
            subject=subject,
        )
    answer = runtime_completion["text"] if runtime_completion else fallback_answer
    return {
        "answer": answer,
        "model_profile": selected["profile"],
        "routing": selected,
        "support_level": support_level,
        "manual_review_required": manual_review_required,
        "citation_count": len(citations),
        "source_coverage": coverage,
        "generated_from": _runtime_generated_from(
            runtime_completion,
            direct_label="direct_provider+matter_document_memory",
            advanced_label="openclaw_runtime+matter_document_memory",
            fallback_label="matter_document_memory",
        ),
        "ai_provider": runtime_completion["provider"] if runtime_completion else None,
        "ai_model": runtime_completion["model"] if runtime_completion else None,
        "citations": [_citation_view(citation, index) for index, citation in enumerate(citations, start=1)],
        "ui_citations": [_citation_view(citation, index) for index, citation in enumerate(citations, start=1)],
        "related_documents": related_documents[:3],
        "retrieval_summary": {
            "scope": "matter",
            "matter_id": matter_id,
            "document_count": len(related_documents),
            "citation_count": len(citations),
            "top_document": citations[0]["document_name"] if citations else None,
            "warning": "Kaynak kapsami dusuk; manuel inceleme onerilir." if manual_review_required else None,
        },
        "rag_runtime": rag_meta,
        "security": {
            "role_checked": role,
            "subject": subject,
            "office_id": office_id,
            "matter_id": matter_id,
            "audit_id": audit_id,
            "retrieval_authorized": True,
        },
    }


def _load_matter_workflow_context(store: Persistence, office_id: str, matter_id: int) -> dict | None:
    matter = store.get_matter(matter_id, office_id)
    if not matter:
        return None
    workspace_documents = store.list_matter_workspace_documents(office_id, matter_id) or []
    workspace_chunks = store.search_linked_workspace_chunks(office_id, matter_id) or []
    return {
        "matter": matter,
        "notes": store.list_matter_notes(office_id, matter_id) or [],
        "documents": (store.list_matter_documents(office_id, matter_id) or []) + workspace_documents,
        "chunks": (store.search_document_chunks(office_id, matter_id) or []) + workspace_chunks,
        "tasks": store.list_matter_tasks(office_id, matter_id) or [],
        "timeline": store.list_matter_timeline(office_id, matter_id) or [],
        "draft_events": store.list_matter_draft_events(office_id, matter_id) or [],
        "ingestion_jobs": store.list_matter_ingestion_jobs(office_id, matter_id) or [],
        "workspace_documents": workspace_documents,
        "workspace_chunks": workspace_chunks,
    }


def _generate_assistant_action_output(
    *,
    payload: AssistantActionGenerateRequest,
    subject: str,
    settings,
    store: Persistence,
    runtime,
    events: StructuredLogger,
) -> dict:
    matter = store.get_matter(int(payload.matter_id), settings.office_id) if payload.matter_id else None
    default_channel_map = {
        "send_telegram_message": "telegram",
        "send_whatsapp_message": "whatsapp",
        "post_x_update": "x",
        "reserve_travel_ticket": "travel",
    }
    target_channel = payload.target_channel or default_channel_map.get(payload.action_type, "email")
    title = payload.title or (
        f"{matter['title']} için müvekkil güncellemesi" if matter and payload.action_type == "prepare_client_update" else "Asistan taslağı"
    )
    body = payload.instructions or "İnceleme için taslak hazırlandı."
    generated_from = "assistant_agenda_engine"
    ai_provider = None
    ai_model = None

    if matter:
        workflow_context = _load_matter_workflow_context(store, settings.office_id, int(matter["id"]))
        if workflow_context:
            if payload.action_type in {"prepare_client_update", "send_email", "reply_email"}:
                draft_seed = generate_matter_draft(
                    workflow_context,
                    draft_type="client_update",
                    target_channel="email",
                    to_contact=payload.to_contact,
                    instructions=payload.instructions,
                )
            elif payload.action_type == "prepare_internal_summary":
                draft_seed = generate_matter_draft(
                    workflow_context,
                    draft_type="internal_summary",
                    target_channel="internal",
                    to_contact=payload.to_contact,
                    instructions=payload.instructions,
                )
            else:
                draft_seed = {
                    "title": title,
                    "body": body,
                    "source_context": {"documents": [], "chronology": [], "risk_notes": [], "open_tasks": []},
                }
            body = draft_seed["body"]
            title = payload.title or draft_seed["title"]
            runtime_prompt = _build_draft_prompt(
                matter=matter,
                draft_type="client_update" if payload.action_type in {"prepare_client_update", "send_email", "reply_email"} else "internal_summary",
                target_channel=target_channel,
                to_contact=payload.to_contact,
                instructions=payload.instructions,
                source_context=draft_seed.get("source_context") or {},
                fallback_body=body,
                profile=store.get_user_profile(settings.office_id),
            )
            runtime_completion = _maybe_runtime_completion(
                runtime,
                runtime_prompt,
                events,
                task="assistant_action_generate",
                matter_id=matter["id"],
                subject=subject,
            )
            if runtime_completion:
                body = runtime_completion["text"]
                generated_from = _runtime_generated_from(
                    runtime_completion,
                    direct_label="direct_provider+assistant_actions",
                    advanced_label="openclaw_runtime+assistant_actions",
                    fallback_label="assistant_agenda_engine",
                )
                ai_provider = runtime_completion["provider"]
                ai_model = runtime_completion["model"]
    elif payload.action_type == "reply_email":
        body = (
            "Merhaba,\n\nMesajınızı inceledim. İlgili dosya ve mevcut kayıtlar üzerinden kısa bir çalışma yanıtı hazırladım."
            "\n\nUygun görürseniz bunu gözden geçirip gönderebiliriz."
        )
    elif payload.action_type == "send_email":
        title = payload.title or "Asistan e-postası"
        runtime_prompt = "\n".join(
            [
                "LawCopilot için gönderime hazır kısa bir e-posta gövdesi yaz.",
                "Kurallar:",
                "- Türkçe yaz.",
                "- Sadece e-posta gövdesini yaz; konu satırı yazma.",
                "- Profesyonel ve doğal ol.",
                "- Gereksiz açıklama ekleme.",
                "",
                f"Alıcı: {payload.to_contact or 'belirtilmedi'}",
                f"Konu: {title}",
                f"Kullanıcı isteği: {payload.instructions or 'Kısa bir e-posta hazırla.'}",
                "",
                "Kullanıcı profili:",
                *(_profile_summary_lines(store.get_user_profile(settings.office_id)) or ["- Belirgin kullanıcı tercihi kaydı yok."]),
            ]
        )
        runtime_completion = _maybe_runtime_completion(
            runtime,
            runtime_prompt,
            events,
            task="assistant_email_draft_generate",
            subject=subject,
            matter_id=payload.matter_id,
        )
        if runtime_completion:
            body = runtime_completion["text"]
            generated_from = _runtime_generated_from(
                runtime_completion,
                direct_label="direct_provider+assistant_actions",
                advanced_label="openclaw_runtime+assistant_actions",
                fallback_label="assistant_agenda_engine",
            )
            ai_provider = runtime_completion["provider"]
            ai_model = runtime_completion["model"]
        else:
            body = payload.instructions or "Merhaba, kısa bir bilgilendirme paylaşmak istedim."
    elif payload.action_type == "send_whatsapp_message":
        body = payload.instructions or "Merhaba, kısa bir bilgilendirme ve geri dönüş talebi içeren WhatsApp mesajı taslağı hazırladım."
    elif payload.action_type == "post_x_update":
        body = payload.instructions or "Kısa, profesyonel ve paylaşmaya hazır bir X gönderi taslağı hazırladım."
    elif payload.action_type == "reserve_travel_ticket":
        body = payload.instructions or "Seyahat arama ve rezervasyon için onay bekleyen kısa bir hazırlık özeti oluşturdum."

    draft = store.create_outbound_draft(
        settings.office_id,
        matter_id=int(matter["id"]) if matter else None,
        draft_type=payload.action_type,
        channel=target_channel,
        to_contact=payload.to_contact,
        subject=title,
        body=body,
        source_context={"source_refs": payload.source_refs or [], "matter_title": matter["title"] if matter else None},
        generated_from=generated_from,
        ai_model=ai_model,
        ai_provider=ai_provider,
        created_by=subject,
    )
    action = store.create_assistant_action(
        settings.office_id,
        matter_id=int(matter["id"]) if matter else None,
        action_type=payload.action_type,
        title=title,
        description=body[:240],
        rationale="Asistan komutu veya ajanda sinyali üzerinden taslak aksiyon üretildi.",
        source_refs=payload.source_refs or [],
        target_channel=target_channel,
        draft_id=int(draft["id"]),
        status="pending_review",
        manual_review_required=True,
        created_by=subject,
    )
    store.add_approval_event(
        settings.office_id,
        actor=subject,
        event_type="draft_generated",
        action_id=int(action["id"]),
        outbound_draft_id=int(draft["id"]),
        note="Asistan aksiyonu için taslak üretildi.",
    )
    return {
        "action": action,
        "draft": draft,
        "generated_from": generated_from,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "manual_review_required": True,
        "message": "Taslak hazırlandı. Göndermeden önce inceleyin.",
    }


def _require_active_workspace_document(store: Persistence, office_id: str, document_id: int, events: EventLogger, *, subject: str | None = None, role: str | None = None) -> tuple[dict, dict]:
    root = store.get_active_workspace_root(office_id)
    if not root:
        raise HTTPException(status_code=404, detail="Çalışma klasörü henüz seçilmedi.")
    record = store.get_workspace_document(office_id, document_id)
    if not record:
        raise HTTPException(status_code=404, detail="Belge bulunamadı.")
    if int(record.get("workspace_root_id") or 0) != int(root["id"]):
        events.log(
            "workspace_scope_violation_blocked",
            level="warning",
            office_id=office_id,
            workspace_root_id=root["id"],
            document_id=document_id,
            subject=subject,
            role=role,
        )
        raise HTTPException(status_code=403, detail="Belge seçili çalışma klasörü dışında kaldığı için açılamadı.")
    return root, record


_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def _compact_inline_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _extract_recent_email_context(query: str, recent_messages: list[dict] | None) -> dict[str, str] | None:
    candidate_texts: list[str] = []
    query_text = _compact_inline_text(query)
    if query_text:
        candidate_texts.append(query_text)

    normalized = query_text.lower()
    should_scan_history = any(
        token in normalized
        for token in [
            "bu mail",
            "bu e-posta",
            "bu eposta",
            "maili",
            "taslak",
            "taslağa",
            "taslaga",
            "gönder",
        ]
    )
    draft_preview_context: dict[str, str] | None = None
    if should_scan_history and recent_messages:
        for item in reversed(recent_messages):
            role = str(item.get("role") or "")
            content = _compact_inline_text(str(item.get("content") or ""))
            draft_preview = item.get("draft_preview") if isinstance(item.get("draft_preview"), dict) else None
            if draft_preview and not draft_preview_context:
                draft_to = _compact_inline_text(str(draft_preview.get("to_contact") or ""))
                draft_subject = _compact_inline_text(str(draft_preview.get("subject") or ""))
                draft_body = _compact_inline_text(str(draft_preview.get("body") or ""))
                if draft_to:
                    draft_preview_context = {
                        "to_contact": draft_to,
                        "subject": draft_subject or "Kısa mesaj",
                        "body": draft_body or "Merhaba, sana kısa bir mesaj iletmek istedim. Uygun olduğunda dönüşünü bekliyorum.",
                    }
            if content:
                plain_content = re.sub(r"[*_`]+", "", content)
                if role == "assistant":
                    to_match = re.search(r"(?:alıcı|alici)\s*[:：]\s*([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", plain_content, re.IGNORECASE)
                    subject_match = re.search(r"(?:konu|başlık|baslik)\s*[:：]\s*[\"“']?([^\"”'\n|]+)", plain_content, re.IGNORECASE)
                    body_match = re.search(r"(?:metin|içerik|icerik|mesaj)\s*[:：]\s*[\"“']?(.+?)(?:”|\"|$)", plain_content, re.IGNORECASE)
                    if to_match:
                        assistant_email_context = " ".join(
                            part for part in [
                                to_match.group(1),
                                f"Konu: {_compact_inline_text(subject_match.group(1))}" if subject_match else "",
                                f"Metin: {_compact_inline_text(body_match.group(1))}" if body_match else "",
                            ] if part
                        )
                        if assistant_email_context:
                            candidate_texts.append(assistant_email_context)
                    elif any(token in plain_content.lower() for token in ["mail", "e-posta", "eposta", "konu", "başlık", "mesaj", "selam"]):
                        candidate_texts.append(plain_content)
                elif "@" in content or any(token in content.lower() for token in ["mail", "e-posta", "eposta", "konu", "başlık", "mesaj", "selam"]):
                    candidate_texts.append(content)
            if len(candidate_texts) >= 4:
                break

    if draft_preview_context:
        return draft_preview_context

    if not candidate_texts:
        return None

    merged = " ".join(candidate_texts)
    emails = _EMAIL_PATTERN.findall(merged)
    if not emails:
        return None

    explicit_subject = ""
    for text in candidate_texts:
        match = re.search(r"(?:konu|başlık)\s*[:：]\s*[\"“']?([^\"”'\n]+)", text, re.IGNORECASE)
        if match:
            explicit_subject = _compact_inline_text(match.group(1))
            break

    explicit_body = ""
    for text in candidate_texts:
        match = re.search(r"(?:mesaj|içerik|metin)\s*[:：]\s*(.+)$", text, re.IGNORECASE)
        if match:
            explicit_body = _compact_inline_text(match.group(1))
            break

    lower = merged.lower()
    fallback_subject = explicit_subject
    fallback_body = explicit_body
    if not fallback_subject:
        if "selam" in lower:
            fallback_subject = "Selam"
        elif "teşekkür" in lower:
            fallback_subject = "Teşekkür"
        elif "hatırlat" in lower:
            fallback_subject = "Hatırlatma"
        else:
            fallback_subject = "Kısa mesaj"

    if not fallback_body:
        if "selam" in lower:
            fallback_body = "Merhaba, sana selamımı iletmek istedim. İyi günler dilerim."
        elif "teşekkür" in lower:
            fallback_body = "Merhaba, desteğin için teşekkür ederim. İyi günler dilerim."
        elif "hatırlat" in lower:
            fallback_body = "Merhaba, kısa bir hatırlatma paylaşmak istedim. Uygun olduğunda dönüşünü bekliyorum."
        else:
            fallback_body = "Merhaba, sana kısa bir mesaj iletmek istedim. Uygun olduğunda dönüşünü bekliyorum."

    return {
        "to_contact": emails[0],
        "subject": fallback_subject,
        "body": fallback_body,
        "source_text": candidate_texts[-1],
    }


def _compose_assistant_thread_reply(
    *,
    query: str,
    matter_id: int | None,
    source_refs: list[dict] | None,
    recent_messages: list[dict] | None,
    subject: str,
    settings,
    store: Persistence,
    runtime,
    events: StructuredLogger,
) -> dict:
    sync_connected_accounts_from_settings(settings, store)
    home = build_assistant_home(store, settings.office_id)
    agenda = build_assistant_agenda(store, settings.office_id)
    inbox = build_assistant_inbox(store, settings.office_id)
    calendar = build_assistant_calendar(store, settings.office_id)
    document_inventory = _assistant_document_inventory(store, settings.office_id, matter_id)
    tool_suggestions = _assistant_tool_suggestions(query, requires_setup=home.get("requires_setup") or [])
    profile = store.get_user_profile(settings.office_id)
    linked_entities: list[dict] = []
    if matter_id:
        matter = store.get_matter(matter_id, settings.office_id)
        if matter:
            linked_entities.append({"type": "matter", "id": matter_id, "label": matter.get("title")})
    linked_entities.extend(_assistant_source_ref_entities(source_refs))
    google_status = _google_status_payload(settings, store)
    telegram_status = _telegram_status_payload(settings, store)
    whatsapp_status = _whatsapp_status_payload(settings, store)
    x_status = _x_status_payload(settings, store)
    if google_status.get("configured"):
        linked_entities.append({"type": "integration", "id": "google", "label": google_status.get("account_label") or "Google"})
    if telegram_status.get("configured"):
        linked_entities.append({"type": "integration", "id": "telegram", "label": telegram_status.get("account_label") or "Telegram"})
    if whatsapp_status.get("configured"):
        linked_entities.append({"type": "integration", "id": "whatsapp", "label": whatsapp_status.get("account_label") or "WhatsApp"})
    if x_status.get("configured"):
        linked_entities.append({"type": "integration", "id": "x", "label": x_status.get("account_label") or "X"})

    normalized = query.lower()
    pending_calendar = _extract_calendar_candidate(query)
    if pending_calendar:
        formatted = _format_turkish_datetime(str(pending_calendar["starts_at"]))
        timing_note = " Saati belirtmediğiniz için 09:00 varsaydım." if pending_calendar.get("defaulted_time") else ""
        return {
            "content": (
                f"Bunu {formatted} için takvime ekleyebilirim.{timing_note} "
                'Uygunsa "ekle" yazın; istemezseniz "vazgeç" diyebilirsiniz.'
            ),
            "assistant_summary": home.get("today_summary") or "",
            "tool_suggestions": _assistant_tool_suggestions("takvim", requires_setup=home.get("requires_setup") or []),
            "linked_entities": linked_entities,
            "draft_preview": None,
            "requires_approval": False,
            "generated_from": "assistant_calendar_candidate",
            "ai_provider": None,
            "ai_model": None,
            "source_context": {
                "priority_items": home.get("priority_items") or [],
                "requires_setup": home.get("requires_setup") or [],
                "source_refs": source_refs or [],
                "pending_calendar_event": {
                    **pending_calendar,
                    "matter_id": matter_id,
                    "location": None,
                },
            },
        }
    if _is_document_inventory_query(query):
        return {
            "content": _assistant_document_inventory_reply(document_inventory, matter_id=matter_id),
            "assistant_summary": home.get("today_summary") or "",
            "tool_suggestions": _assistant_tool_suggestions("belge", requires_setup=home.get("requires_setup") or []),
            "linked_entities": linked_entities,
            "draft_preview": None,
            "requires_approval": False,
            "generated_from": "assistant_document_inventory",
            "ai_provider": None,
            "ai_model": None,
            "source_context": {
                "priority_items": home.get("priority_items") or [],
                "requires_setup": home.get("requires_setup") or [],
                "source_refs": source_refs or [],
                "document_inventory": document_inventory,
            },
        }
    if is_web_search_query(query) and not is_travel_query(query):
        web_context = build_web_search_context(query)
        results = list(web_context.get("results") or [])
        if results:
            lines = ["Web'de şu sonuçları buldum:"]
            for index, item in enumerate(results[:4], start=1):
                title = str(item.get("title") or "Sonuç")
                snippet = str(item.get("snippet") or "").strip()
                url = str(item.get("url") or "").strip()
                row = f"{index}. {title}"
                if snippet:
                    row += f" — {snippet}"
                if url:
                    row += f" ({url})"
                lines.append(row)
            lines.append("İstersen bunları daraltıp en güçlü olanları senin için özetleyeyim.")
            content = "\n".join(lines)
        else:
            content = "Şu an web'de güvenilir bir sonuç toplayamadım. İstersen sorguyu biraz daha netleştir ve tekrar bakayım."
        return {
            "content": content,
            "assistant_summary": home.get("today_summary") or "",
            "tool_suggestions": [{"tool": "runtime", "label": "Durum", "reason": "Güncel araştırma ve dış kaynak desteği burada özetlenir."}],
            "linked_entities": linked_entities,
            "draft_preview": None,
            "requires_approval": False,
            "generated_from": "assistant_web_search",
            "ai_provider": None,
            "ai_model": None,
            "source_context": {
                "priority_items": home.get("priority_items") or [],
                "requires_setup": home.get("requires_setup") or [],
                "source_refs": source_refs or [],
                "web_search_results": results,
            },
        }
    if is_travel_query(query) and not is_travel_booking_query(query):
        travel_context = build_travel_context(query, profile_note=_profile_preference_text(profile))
        results = list(travel_context.get("results") or [])
        booking_url = str(travel_context.get("booking_url") or "").strip()
        content_lines = []
        if results:
            content_lines.append("Seyahat için ilk seçenekleri topladım:")
            for index, item in enumerate(results[:3], start=1):
                line = f"{index}. {item.get('title') or 'Seçenek'}"
                if item.get("snippet"):
                    line += f" — {item.get('snippet')}"
                if item.get("url"):
                    line += f" ({item.get('url')})"
                content_lines.append(line)
        if booking_url:
            content_lines.append("Uygun görürsen onayından sonra rezervasyon sayfasını açabilirim.")
        else:
            content_lines.append("Tarih, rota ve bütçeyi netleştirirsen daha iyi seçenek çıkarabilirim.")
        return {
            "content": "\n".join(content_lines),
            "assistant_summary": home.get("today_summary") or "",
            "tool_suggestions": [{"tool": "calendar", "label": "Takvim", "reason": "Seyahat önerisini takvim boşluğunla birlikte değerlendiriyorum."}],
            "linked_entities": linked_entities,
            "draft_preview": None,
            "requires_approval": False,
            "generated_from": "assistant_travel_search",
            "ai_provider": None,
            "ai_model": None,
            "source_context": {
                "priority_items": home.get("priority_items") or [],
                "requires_setup": home.get("requires_setup") or [],
                "source_refs": source_refs or [],
                "travel_options": results,
                "booking_url": booking_url,
            },
        }
    action_result = None
    if any(
        token in normalized
        for token in [
            "mail hazırla",
            "e-posta hazırla",
            "mail gönder",
            "e-posta gönder",
            "yanıtla",
            "taslaklarda",
            "taslağa",
            "taslaga",
            "bu maili",
            "bu e-postayı",
            "bu epostayı",
            "maili",
        ]
    ):
        email_context = _extract_recent_email_context(query, recent_messages)
        if email_context or matter_id:
            action_type = "reply_email" if "yanıt" in normalized else ("send_email" if email_context or not matter_id else "prepare_client_update")
            action_result = _generate_assistant_action_output(
                payload=AssistantActionGenerateRequest(
                    action_type=action_type,
                    matter_id=matter_id,
                    title=(email_context or {}).get("subject"),
                    instructions=(email_context or {}).get("body") or query,
                    target_channel="email",
                    to_contact=(email_context or {}).get("to_contact"),
                    source_refs=source_refs,
                ),
                subject=subject,
                settings=settings,
                store=store,
                runtime=runtime,
                events=events,
            )
            tool_suggestions = _assistant_tool_suggestions("taslak", requires_setup=home.get("requires_setup") or [])
    elif any(token in normalized for token in ["telegram", "mesaj hazırla"]):
        if matter_id:
            action_result = _generate_assistant_action_output(
                payload=AssistantActionGenerateRequest(
                    action_type="send_telegram_message",
                    matter_id=matter_id,
                    instructions=query,
                    target_channel="telegram",
                    source_refs=source_refs,
                ),
                subject=subject,
                settings=settings,
                store=store,
                runtime=runtime,
                events=events,
            )
            tool_suggestions = _assistant_tool_suggestions("taslak", requires_setup=home.get("requires_setup") or [])
    elif any(token in normalized for token in ["whatsapp", "whatsapptan", "whatsapp'tan"]):
        action_result = _generate_assistant_action_output(
            payload=AssistantActionGenerateRequest(
                action_type="send_whatsapp_message",
                matter_id=matter_id,
                instructions=query,
                target_channel="whatsapp",
                source_refs=source_refs,
            ),
            subject=subject,
            settings=settings,
            store=store,
            runtime=runtime,
            events=events,
        )
        tool_suggestions = _assistant_tool_suggestions("taslak", requires_setup=home.get("requires_setup") or [])
    elif any(token in normalized for token in ["x'te", "x te", "tweet", "gönderi paylaş", "post paylaş"]):
        action_result = _generate_assistant_action_output(
            payload=AssistantActionGenerateRequest(
                action_type="post_x_update",
                matter_id=matter_id,
                instructions=query,
                target_channel="x",
                source_refs=source_refs,
            ),
            subject=subject,
            settings=settings,
            store=store,
            runtime=runtime,
            events=events,
        )
        tool_suggestions = _assistant_tool_suggestions("taslak", requires_setup=home.get("requires_setup") or [])
    elif is_travel_booking_query(query):
        travel_context = build_travel_context(query, profile_note=_profile_preference_text(profile))
        travel_source_refs = list(source_refs or [])
        if travel_context.get("booking_url"):
            travel_source_refs.append(
                {
                    "type": "booking_url",
                    "label": "Rezervasyon bağlantısı",
                    "url": travel_context.get("booking_url"),
                }
            )
        action_result = _generate_assistant_action_output(
            payload=AssistantActionGenerateRequest(
                action_type="reserve_travel_ticket",
                matter_id=matter_id,
                instructions=query,
                target_channel="travel",
                source_refs=travel_source_refs,
            ),
            subject=subject,
            settings=settings,
            store=store,
            runtime=runtime,
            events=events,
        )
        tool_suggestions = _assistant_tool_suggestions("takvim", requires_setup=home.get("requires_setup") or [])

    fallback_text: str
    is_casual_prompt = any(token in normalized for token in ["merhaba", "selam", "naber", "nabuyon", "napıyon", "napiyon", "ne yapıyorsun", "nasılsın"])
    if action_result:
        draft = action_result["draft"]
        fallback_text = (
            f"Taslak hazır. {draft.get('subject') or draft.get('draft_type') or 'İleti'} için bir taslak ürettim. "
            "Göndermeden önce inceleyip onay vermeniz gerekiyor."
        )
    else:
        focus_tool = tool_suggestions[0]["label"] if tool_suggestions else "Bugün"
        fallback_text = (
            f"{home.get('today_summary') or 'Günlük özet hazır.'} "
            f"İlk odak alanı olarak {focus_tool} sekmesini öne çıkarıyorum."
        )
        if is_casual_prompt:
            tool_suggestions = []
            fallback_text = (
                "Buradayım. Çalışma alanınızı, ajandanızı ve bağlı hizmetleri izliyorum. "
                "İsterseniz bugün yapılacakları çıkarayım, bir dosyayı inceleyeyim veya bir iletişim taslağı hazırlayayım."
            )
        elif any(token in normalized for token in ["bugün", "ne var", "ajanda"]):
            top_items = [item.get("title") for item in home.get("priority_items", [])[:3] if item.get("title")]
            if top_items:
                fallback_text = "Bugün için öne çıkan işler: " + "; ".join(top_items) + "."

    runtime_prompt = "\n".join(
        [
            "LawCopilot için genel hukuk asistanı olarak tek oturumlu üst katman asistan cevabı üret.",
            "Kurallar:",
            "- Türkçe yaz.",
            "- Avukata net, kısa ve yönlendirici cevap ver.",
            "- Varsa kurulum eksiklerini açıkça belirt.",
            "- Varsa taslak üretilmişse bunun sadece inceleme/onay beklediğini söyle.",
            "- İlgili araç sekmesini öner.",
            "",
            f"Kullanıcı sorgusu: {query}",
            f"Etkin dosya kimliği: {matter_id or 'yok'}",
            "Ekli kaynaklar:",
            *_assistant_source_ref_lines(source_refs),
            "",
            _assistant_home_context_text(home, agenda, inbox, calendar[:5]),
            "",
            str(document_inventory.get("prompt_text") or "Belge envanteri görünmüyor."),
            "",
            "Önerilecek araçlar:",
            *[f"- {item['label']}: {item['reason']}" for item in tool_suggestions],
            "",
            "Fallback cevap:",
            fallback_text,
            "",
            "Kullanıcı profili:",
            *(_profile_summary_lines(store.get_user_profile(settings.office_id)) or ["- Belirgin kullanıcı tercihi kaydı yok."]),
        ]
    )
    runtime_completion = _maybe_runtime_completion(
        runtime,
        runtime_prompt,
        events,
        task="assistant_thread_reply",
        subject=subject,
        matter_id=matter_id,
    )

    draft_preview = action_result["draft"] if action_result else None
    return {
        "content": runtime_completion["text"] if runtime_completion else fallback_text,
        "assistant_summary": home.get("today_summary") or "",
        "tool_suggestions": tool_suggestions,
        "linked_entities": linked_entities,
        "draft_preview": draft_preview,
        "requires_approval": bool(action_result),
        "generated_from": _runtime_generated_from(
            runtime_completion,
            direct_label="direct_provider+assistant_thread",
            advanced_label="openclaw_runtime+assistant_thread",
            fallback_label="assistant_actions" if action_result else "assistant_home_engine",
        ),
        "ai_provider": runtime_completion["provider"] if runtime_completion else (action_result.get("ai_provider") if action_result else None),
        "ai_model": runtime_completion["model"] if runtime_completion else (action_result.get("ai_model") if action_result else None),
            "source_context": {
                "priority_items": home.get("priority_items") or [],
                "requires_setup": home.get("requires_setup") or [],
                "source_refs": source_refs or [],
                "document_inventory": document_inventory,
                "assistant_action": action_result["action"] if action_result else None,
            },
        }


def _extract_context(
    x_role: str | None,
    authorization: str | None,
    jwt_secret: str,
    store: Persistence,
    allow_header_auth: bool,
) -> tuple[str, str, str]:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        ctx = parse_token(jwt_secret, token)
        if not store.is_session_active(ctx.sid):
            raise HTTPException(status_code=401, detail="session_revoked")
        return ctx.sub, ctx.role, ctx.sid

    if not allow_header_auth:
        raise HTTPException(status_code=401, detail="missing_bearer_token")

    # Legacy fallback: keep least privilege to avoid role-escalation via headers.
    requested = (x_role or "intern").lower()
    role = "intern" if requested not in {"intern"} else requested
    return "header-user", role, "header-session"


def _ensure_draft_access(draft: dict | None, subject: str, role: str) -> dict:
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if role != "admin" and draft.get("requested_by") != subject:
        raise HTTPException(status_code=403, detail="draft_access_denied")
    return draft


def _query_result(
    payload: QueryIn,
    role: str,
    subject: str,
    sid: str,
    router: ModelRouter,
    rag,
    rag_meta: dict,
    audit: AuditLogger,
    events: StructuredLogger,
    runtime,
    profile: dict | None = None,
) -> dict:
    selected = router.choose(payload.query, payload.model_profile)
    sources = rag.search(payload.query, k=3)
    for idx, source in enumerate(sources, start=1):
        source["citation_index"] = idx
        source["citation_label"] = f"[{idx}]"

    audit_seed = f"{payload.query}:{role}:{selected['profile']}:{subject}"
    audit_id = hashlib.sha256(audit_seed.encode()).hexdigest()[:16]
    quality = 0.55 + min(0.4, len(sources) * 0.12)
    citation_quality = {
        "score": round(quality, 2),
        "grade": "A" if quality > 0.85 else "B" if quality > 0.7 else "C",
        "issues": [] if quality > 0.7 else ["low_source_overlap", "requires_manual_review"],
    }
    audit.log(
        "query",
        subject=subject,
        role=role,
        session_id=sid,
        profile=selected["profile"],
        audit_id=audit_id,
        source_count=len(sources),
    )

    if sources:
        fallback_answer = f"Yapay zeka asistanı devre dışı, sadece sistemdeki dayanak noktaları şunlardır: {' '.join(source['citation_label'] for source in sources)}"
    else:
        fallback_answer = f"Yapay zeka (Codex) yapılandırmanız kapalı veya eksik olduğundan cevap üretilemedi. Ayrıca çalışma dosyanızda sorgunuzla eşleşen hiçbir kaynak bulunamadı."
    runtime_completion = None
    if sources:
        runtime_prompt = "\n".join(
            [
                "LawCopilot için genel hukuk asistanı olarak güncel ve yardımcı bir kişisel asistan cevabı üret.",
                "Kurallar:",
                "- Cevabı Türkçe yaz.",
                "- Öncelikle aşağıdaki dayanak parçalarına bak. Eğer bağlam yeterliyse onu kullan.",
                "- Bilgi yetersizse veya genel arama/özel işlem gerekiyorsa yalnız sistemde kurulu küratörlü yetenekleri kullan.",
                "- Cevap içinde [1], [2] gibi atıf etiketlerini koru.",
                "",
                f"Kullanıcı sorgusu: {payload.query}",
                "",
                "Kullanıcı profili:",
                *(_profile_summary_lines(profile) or ["- Belirgin kullanıcı tercihi kaydı yok."]),
                "",
                "Dayanak pasajlar:",
                *_legacy_source_prompt_lines(sources),
            ]
        )
        runtime_completion = _maybe_runtime_completion(
            runtime,
            runtime_prompt,
            events,
            task="legacy_query_answer",
            subject=subject,
        )
    else:
        # Fallback to general AI knowledge without sources
        general_prompt = "\n".join(
            [
                "LawCopilot Kişisel Asistanı olarak genel bir soruya cevap veriyorsun.",
                "Sisteme yüklenmiş özel bir belge dayanağı bulunamadı.",
                "Kurallar:",
                "- Cevabı Türkçe yaz.",
                "- Eğer soru bir araç veya dış veri gerektiriyorsa mevcut küratörlü yeteneklerini kullan.",
                "- Asistan kimliğini koru ve doğrudan doğal bir şekilde yardımcı ol.",
                "- Net ve açıklayıcı ol.",
                "",
                f"Kullanıcı sorgusu: {payload.query}",
                "",
                "Kullanıcı profili:",
                *(_profile_summary_lines(profile) or ["- Belirgin kullanıcı tercihi kaydı yok."]),
            ]
        )
        runtime_completion = _maybe_runtime_completion(
            runtime,
            general_prompt,
            events,
            task="legacy_query_general_answer",
            subject=subject,
        )
        
    answer = runtime_completion["text"] if runtime_completion else fallback_answer

    return {
        "answer": answer,
        "model_profile": selected["profile"],
        "routing": selected,
        "sources": sources,
        "retrieval_summary": {
            "source_count": len(sources),
            "top_document": sources[0]["document"] if sources else None,
            "warning": "Arama sonucu bulunamadı; genel hukuki bilgilere başvuruldu." if not sources else None,
        },
        "citation_quality": citation_quality,
        "ui_citations": [
            {
                "index": source["citation_index"],
                "label": source["citation_label"],
                "document": source.get("document"),
                "line_start": source.get("line_start"),
                "line_end": source.get("line_end"),
                "line_anchor": source.get("line_anchor"),
                "chunk_id": source.get("chunk_id"),
            }
            for source in sources
        ],
        "generated_from": _runtime_generated_from(
            runtime_completion,
            direct_label="direct_provider+rag",
            advanced_label="openclaw_runtime+rag",
            fallback_label="rag",
        ) if sources else _runtime_generated_from(
            runtime_completion,
            direct_label="direct_provider",
            advanced_label="openclaw_runtime",
            fallback_label="rag",
        ),
        "ai_provider": runtime_completion["provider"] if runtime_completion else None,
        "ai_model": runtime_completion["model"] if runtime_completion else None,
        "rag_runtime": rag_meta,
        "security": {
            "role_checked": role,
            "subject": subject,
            "audit_id": audit_id,
            "retrieval_authorized": True,
        },
    }


def create_app() -> FastAPI:
    settings = get_settings()
    profiles = load_model_profiles(settings.model_profiles_path)
    if settings.default_model_profile in (profiles.get("profiles", {}) or {}):
        profiles["default"] = settings.default_model_profile

    rag = create_rag_store(settings.rag_backend, tenant_id=settings.rag_tenant_id)
    rag_meta = rag.runtime_meta()
    router = ModelRouter(profiles)
    audit = AuditLogger(resolve_repo_path(settings.audit_log_path))
    events = StructuredLogger(resolve_repo_path(settings.structured_log_path))
    store = Persistence(resolve_repo_path(settings.db_path))
    openclaw_runtime = create_openclaw_runtime(settings)
    llm_service = LLMService(
        direct_provider=DirectProviderLLM(
            provider_type=settings.provider_type,
            base_url=settings.provider_base_url,
            model=settings.provider_model,
            api_key=settings.provider_api_key,
            configured=settings.provider_configured,
        ),
        advanced_bridge=openclaw_runtime,
    )
    runtime = llm_service
    memory_service = MemoryService(store, settings.office_id)
    sync_connected_accounts_from_settings(settings, store)
    openclaw_workspace = create_openclaw_workspace_contract(settings, store, events)
    setattr(openclaw_runtime, "workspace_contract", openclaw_workspace)
    connector = ConnectorSafetyWrapper(
        ConnectorPolicy(
            allowed_domains=settings.connector_allow_domains,
            dry_run=settings.connector_dry_run,
        )
    )

    app = FastAPI(title=settings.app_name, version=settings.app_version)

    def _openclaw_workspace_status(*, sync: bool = False, include_previews: bool = False) -> dict:
        if not openclaw_workspace.enabled:
            return openclaw_workspace.status(include_previews=include_previews)
        try:
            if sync:
                openclaw_workspace.sync()
            return openclaw_workspace.status(include_previews=include_previews)
        except Exception as exc:  # noqa: BLE001
            events.log("openclaw_workspace_sync_failed", level="warning", error=str(exc))
            status = openclaw_workspace.status(include_previews=include_previews)
            status["workspace_ready"] = False
            return status

    if openclaw_workspace.enabled:
        _openclaw_workspace_status(sync=True)

    @app.get("/health")
    def health():
        workspace_root = store.get_active_workspace_root(settings.office_id)
        openclaw_status = _openclaw_workspace_status(sync=True)
        body = {
            "ok": True,
            "service": "lawcopilot-api",
            "version": settings.app_version,
            "app_name": settings.app_name,
            "office_id": settings.office_id,
            "deployment_mode": settings.deployment_mode,
            "default_model_profile": profiles.get("default"),
            "release_channel": settings.release_channel,
            "environment": settings.environment,
            "desktop_shell": settings.desktop_shell,
            "ts": datetime.now(timezone.utc).isoformat(),
            "connector_dry_run": settings.connector_dry_run,
            "rag_backend": settings.rag_backend,
            "rag_runtime": rag_meta,
            "workspace_configured": bool(workspace_root),
            "workspace_root_name": workspace_root.get("display_name") if workspace_root else None,
            "provider_type": settings.provider_type,
            "provider_base_url": settings.provider_base_url,
            "provider_model": settings.provider_model,
            "provider_configured": settings.provider_configured,
            "assistant_runtime_mode": assistant_runtime_mode(
                direct_enabled=llm_service.direct_enabled,
                advanced_enabled=llm_service.advanced_enabled,
            ),
            "openclaw_runtime_enabled": openclaw_runtime.enabled,
            "openclaw_workspace_ready": openclaw_status["workspace_ready"],
            "openclaw_bootstrap_required": openclaw_status["bootstrap_required"],
            "openclaw_last_sync_at": openclaw_status["last_sync_at"],
            "openclaw_curated_skill_count": openclaw_status["curated_skill_count"],
            "google_enabled": settings.google_enabled,
            "google_configured": settings.google_configured,
            "google_account_label": settings.google_account_label,
            "google_scopes": list(settings.google_scopes),
            "gmail_connected": settings.gmail_connected,
            "calendar_connected": settings.calendar_connected,
            "telegram_enabled": settings.telegram_enabled,
            "telegram_configured": settings.telegram_configured,
            "telegram_bot_username": settings.telegram_bot_username,
            "telegram_allowed_user_id": settings.telegram_allowed_user_id,
        }
        if settings.expose_security_flags:
            body["safe_defaults"] = {
                "connector_dry_run": settings.connector_dry_run,
                "jwt_secret_default": settings.jwt_secret == "dev-change-me",
                "max_ingest_bytes": settings.max_ingest_bytes,
                "allow_header_auth": settings.allow_header_auth,
            }
        return body

    @app.get("/telemetry/health")
    def telemetry_health(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        openclaw_status = _openclaw_workspace_status(sync=True)
        recent = events.recent(20)
        runtime_events = [
            event for event in recent
            if str(event.get("event") or "") in {
                "openclaw_runtime_used",
                "openclaw_runtime_fallback",
                "direct_provider_runtime_used",
                "direct_provider_runtime_fallback",
            }
        ]
        last_runtime = runtime_events[0] if runtime_events else None
        workspace_root = store.get_active_workspace_root(settings.office_id)
        audit.log("telemetry_health_viewed", subject=subject, role=role, session_id=sid, event_count=len(recent))
        return {
            "ok": True,
            "app_name": settings.app_name,
            "version": settings.app_version,
            "release_channel": settings.release_channel,
            "environment": settings.environment,
            "deployment_mode": settings.deployment_mode,
            "default_model_profile": profiles.get("default"),
            "desktop_shell": settings.desktop_shell,
            "office_id": settings.office_id,
            "structured_log_path": settings.structured_log_path,
            "audit_log_path": settings.audit_log_path,
            "db_path": settings.db_path,
            "connector_dry_run": settings.connector_dry_run,
            "workspace_configured": bool(workspace_root),
            "workspace_root_name": workspace_root.get("display_name") if workspace_root else None,
            "provider_type": settings.provider_type,
            "provider_base_url": settings.provider_base_url,
            "provider_model": settings.provider_model,
            "provider_configured": settings.provider_configured,
            "assistant_runtime_mode": assistant_runtime_mode(
                direct_enabled=llm_service.direct_enabled,
                advanced_enabled=llm_service.advanced_enabled,
            ),
            "openclaw_runtime_enabled": openclaw_runtime.enabled,
            "openclaw_workspace_ready": openclaw_status["workspace_ready"],
            "openclaw_bootstrap_required": openclaw_status["bootstrap_required"],
            "openclaw_last_sync_at": openclaw_status["last_sync_at"],
            "openclaw_curated_skill_count": openclaw_status["curated_skill_count"],
            "runtime_last_status": (
                "direct-provider"
                if last_runtime and str(last_runtime.get("event")) == "direct_provider_runtime_used"
                else "direct-fallback"
                if last_runtime and str(last_runtime.get("event")) == "direct_provider_runtime_fallback"
                else "codex"
                if last_runtime and str(last_runtime.get("event")) == "openclaw_runtime_used"
                else "fallback"
                if last_runtime
                else "unknown"
            ),
            "runtime_last_task": str(last_runtime.get("task") or "") if last_runtime else "",
            "runtime_last_model": str(last_runtime.get("model") or settings.provider_model or "") if last_runtime else settings.provider_model,
            "runtime_last_provider": str(last_runtime.get("provider") or settings.provider_type or "") if last_runtime else settings.provider_type,
            "google_enabled": settings.google_enabled,
            "google_configured": settings.google_configured,
            "google_account_label": settings.google_account_label,
            "google_scopes": list(settings.google_scopes),
            "gmail_connected": settings.gmail_connected,
            "calendar_connected": settings.calendar_connected,
            "connected_accounts": store.list_connected_accounts(settings.office_id),
            "recent_runtime_events": runtime_events[:8],
            "telegram_enabled": settings.telegram_enabled,
            "telegram_configured": settings.telegram_configured,
            "telegram_bot_username": settings.telegram_bot_username,
            "telegram_allowed_user_id": settings.telegram_allowed_user_id,
            "recent_events": recent[:10],
        }

    @app.get("/telemetry/events/recent")
    def telemetry_recent_events(
        limit: int = 20,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        return {"items": events.recent(limit)}

    @app.get("/settings/model-profiles")
    def get_model_profiles(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return {
            "default": profiles.get("default"),
            "profiles": profiles.get("profiles", {}),
            "deployment_mode": settings.deployment_mode,
            "office_id": settings.office_id,
        }

    @app.get("/profile")
    def get_user_profile(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return store.get_user_profile(settings.office_id) or _empty_profile_payload(settings.office_id)

    @app.get("/assistant/runtime/profile")
    def get_assistant_runtime_profile(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return store.get_assistant_runtime_profile(settings.office_id) or _empty_assistant_runtime_profile_payload(settings.office_id)

    @app.put("/assistant/runtime/profile")
    def save_assistant_runtime_profile(
        payload: AssistantRuntimeProfileRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        profile = store.upsert_assistant_runtime_profile(
            settings.office_id,
            assistant_name=payload.assistant_name,
            role_summary=payload.role_summary,
            tone=payload.tone,
            avatar_path=payload.avatar_path,
            soul_notes=payload.soul_notes,
            tools_notes=payload.tools_notes,
            heartbeat_extra_checks=[str(item).strip() for item in payload.heartbeat_extra_checks if str(item).strip()],
        )
        workspace_status = _openclaw_workspace_status(sync=True, include_previews=True)
        audit.log("assistant_runtime_profile_updated", subject=subject, role=role, session_id=sid)
        return {
            "profile": profile,
            "message": "Asistan kimliği ve bellek ayarları kaydedildi.",
            "workspace": workspace_status,
        }

    @app.get("/assistant/runtime/workspace")
    def get_assistant_runtime_workspace(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return _openclaw_workspace_status(sync=True, include_previews=True)

    @app.get("/assistant/onboarding/state")
    def get_assistant_onboarding_state(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        return _assistant_onboarding_state(settings, store)

    @app.put("/profile")
    def save_user_profile(
        payload: UserProfileRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        profile = store.upsert_user_profile(
            settings.office_id,
            display_name=payload.display_name,
            favorite_color=payload.favorite_color,
            food_preferences=payload.food_preferences,
            transport_preference=payload.transport_preference,
            weather_preference=payload.weather_preference,
            travel_preferences=payload.travel_preferences,
            communication_style=payload.communication_style,
            assistant_notes=payload.assistant_notes,
            important_dates=[item.model_dump() for item in payload.important_dates],
            related_profiles=[item.model_dump() for item in payload.related_profiles],
        )
        _openclaw_workspace_status(sync=True)
        audit.log(
            "user_profile_updated",
            subject=subject,
            role=role,
            session_id=sid,
            important_date_count=len(payload.important_dates),
            related_profile_count=len(payload.related_profiles),
        )
        return {
            "profile": profile,
            "message": "Kişisel profil kaydedildi.",
        }

    @app.get("/assistant/onboarding")
    def get_assistant_onboarding(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        state = _assistant_onboarding_state(settings, store)
        state["user_profile"] = store.get_user_profile(settings.office_id)
        state["assistant_runtime_profile"] = store.get_assistant_runtime_profile(settings.office_id)
        return state

    @app.get("/integrations/google/status")
    def get_google_status(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        return _google_status_payload(settings, store)

    @app.get("/integrations/google/drive-files")
    def list_google_drive_files(
        limit: int = 30,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        return {
            "configured": settings.google_configured,
            "connected": settings.drive_connected,
            "items": store.list_drive_files(settings.office_id, limit=max(1, min(limit, 100))),
            "generated_from": "google_drive_mirror",
        }

    @app.post("/integrations/google/oauth/start")
    def start_google_oauth(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        return {
            "ok": False,
            "managed_by": "desktop",
            "message": "Google OAuth akışı masaüstü uygulaması üzerinden başlatılır.",
            "status": _google_status_payload(settings, store),
        }

    @app.post("/integrations/google/oauth/complete")
    def complete_google_oauth(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        return {
            "ok": False,
            "managed_by": "desktop",
            "message": "Google OAuth dönüşü masaüstü uygulaması içinde tamamlanır.",
            "status": _google_status_payload(settings, store),
        }

    @app.post("/integrations/google/sync")
    def sync_google_data(
        payload: GoogleSyncRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        synced_at = payload.synced_at.isoformat() if payload.synced_at else datetime.now(timezone.utc).isoformat()
        store.upsert_connected_account(
            settings.office_id,
            "google",
            account_label=payload.account_label or settings.google_account_label or "Google hesabı",
            status="connected" if settings.google_configured else "pending",
            scopes=payload.scopes or list(settings.google_scopes),
            connected_at=synced_at if settings.google_configured else None,
            last_sync_at=synced_at,
            manual_review_required=True,
            metadata={
                "gmail_connected": settings.gmail_connected,
                "calendar_connected": settings.calendar_connected,
                "drive_connected": settings.drive_connected,
                "email_thread_count": len(payload.email_threads),
                "calendar_event_count": len(payload.calendar_events),
                "drive_file_count": len(payload.drive_files),
            },
        )
        for thread in payload.email_threads:
            thread_metadata = dict(thread.metadata or {})
            if thread.sender:
                thread_metadata["sender"] = thread.sender
            store.upsert_email_thread(
                settings.office_id,
                provider=thread.provider,
                thread_ref=thread.thread_ref,
                subject=thread.subject,
                snippet=thread.snippet,
                participants=[thread.sender] if thread.sender else None,
                received_at=thread.received_at.isoformat() if thread.received_at else None,
                unread_count=int(thread.unread_count),
                reply_needed=bool(thread.reply_needed),
                matter_id=thread.matter_id,
                metadata=thread_metadata,
            )
        for event in payload.calendar_events:
            store.upsert_calendar_event(
                settings.office_id,
                provider=event.provider,
                external_id=event.external_id,
                title=event.title,
                starts_at=event.starts_at.isoformat(),
                ends_at=event.ends_at.isoformat() if event.ends_at else None,
                location=event.location,
                matter_id=event.matter_id,
                metadata=event.metadata or {},
            )
        for drive_file in payload.drive_files:
            store.upsert_drive_file(
                settings.office_id,
                provider=drive_file.provider,
                external_id=drive_file.external_id,
                name=drive_file.name,
                mime_type=drive_file.mime_type,
                web_view_link=drive_file.web_view_link,
                modified_at=drive_file.modified_at.isoformat() if drive_file.modified_at else None,
            )
        audit.log(
            "google_sync_completed",
            subject=subject,
            role=role,
            session_id=sid,
            email_thread_count=len(payload.email_threads),
            calendar_event_count=len(payload.calendar_events),
        )
        _openclaw_workspace_status(sync=True)
        return {
            "ok": True,
            "message": "Google verileri yerel ajandaya işlendi.",
            "status": _google_status_payload(settings, store),
            "synced": {
                "email_threads": len(payload.email_threads),
                "calendar_events": len(payload.calendar_events),
                "drive_files": len(payload.drive_files),
                "synced_at": synced_at,
            },
        }

    @app.get("/integrations/whatsapp/status")
    def get_whatsapp_status(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        return _whatsapp_status_payload(settings, store)

    @app.post("/integrations/whatsapp/sync")
    def sync_whatsapp_data(
        payload: WhatsAppSyncRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        synced_at = payload.synced_at.isoformat() if payload.synced_at else datetime.now(timezone.utc).isoformat()
        store.upsert_connected_account(
            settings.office_id,
            "whatsapp",
            account_label=payload.account_label or payload.verified_name or payload.display_phone_number or "WhatsApp hesabı",
            status="connected",
            scopes=["messages:read", "messages:send"],
            connected_at=synced_at,
            last_sync_at=synced_at,
            manual_review_required=True,
            metadata={
                "phone_number_id": payload.phone_number_id,
                "display_phone_number": payload.display_phone_number,
                "verified_name": payload.verified_name,
                "note": payload.note,
                "message_count": len(payload.messages),
            },
        )
        for message in payload.messages:
            store.upsert_whatsapp_message(
                settings.office_id,
                provider=message.provider,
                conversation_ref=message.conversation_ref,
                message_ref=message.message_ref,
                sender=message.sender,
                recipient=message.recipient,
                body=message.body,
                direction=message.direction,
                sent_at=message.sent_at.isoformat() if message.sent_at else None,
                reply_needed=bool(message.reply_needed),
                matter_id=message.matter_id,
                metadata=message.metadata or {},
            )
        audit.log(
            "whatsapp_sync_completed",
            subject=subject,
            role=role,
            session_id=sid,
            message_count=len(payload.messages),
        )
        return {
            "ok": True,
            "message": "WhatsApp verileri yerel kayıtlarla eşitlendi.",
            "status": _whatsapp_status_payload(settings, store),
            "synced": {
                "messages": len(payload.messages),
                "synced_at": synced_at,
                "note": payload.note or "",
            },
        }

    @app.get("/integrations/x/status")
    def get_x_status(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        return _x_status_payload(settings, store)

    @app.post("/integrations/x/sync")
    def sync_x_data(
        payload: XSyncRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        synced_at = payload.synced_at.isoformat() if payload.synced_at else datetime.now(timezone.utc).isoformat()
        store.upsert_connected_account(
            settings.office_id,
            "x",
            account_label=payload.account_label or "X hesabı",
            status="connected",
            scopes=payload.scopes or [],
            connected_at=synced_at,
            last_sync_at=synced_at,
            manual_review_required=True,
            metadata={"user_id": payload.user_id, "mention_count": len(payload.mentions), "post_count": len(payload.posts)},
        )
        for mention in payload.mentions:
            store.upsert_x_post(
                settings.office_id,
                provider=mention.provider,
                external_id=mention.external_id,
                post_type="mention",
                author_handle=mention.author_handle,
                content=mention.content,
                posted_at=mention.posted_at.isoformat() if mention.posted_at else None,
                reply_needed=bool(mention.reply_needed),
                metadata=mention.metadata or {},
            )
        for post in payload.posts:
            store.upsert_x_post(
                settings.office_id,
                provider=post.provider,
                external_id=post.external_id,
                post_type=post.post_type,
                author_handle=post.author_handle,
                content=post.content,
                posted_at=post.posted_at.isoformat() if post.posted_at else None,
                reply_needed=bool(post.reply_needed),
                metadata=post.metadata or {},
            )
        audit.log(
            "x_sync_completed",
            subject=subject,
            role=role,
            session_id=sid,
            mention_count=len(payload.mentions),
            post_count=len(payload.posts),
        )
        return {
            "ok": True,
            "message": "X verileri yerel kayıtlarla eşitlendi.",
            "status": _x_status_payload(settings, store),
            "synced": {
                "mentions": len(payload.mentions),
                "posts": len(payload.posts),
                "synced_at": synced_at,
            },
        }

    @app.post("/assistant/calendar/events")
    def create_assistant_calendar_event(
        payload: AssistantCalendarEventCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        if payload.ends_at and payload.ends_at < payload.starts_at:
            raise HTTPException(status_code=400, detail="Bitiş saati başlangıçtan önce olamaz.")
        provider = str(payload.provider or "lawcopilot-planner").strip() or "lawcopilot-planner"
        external_id = str(payload.external_id or f"{provider}-{int(time.time() * 1000)}").strip()
        metadata = dict(payload.metadata or {})
        if payload.notes:
            metadata["notes"] = payload.notes.strip()
        event = store.upsert_calendar_event(
            settings.office_id,
            provider=provider,
            external_id=external_id,
            title=payload.title.strip(),
            starts_at=payload.starts_at.isoformat(),
            ends_at=payload.ends_at.isoformat() if payload.ends_at else None,
            attendees=[str(item).strip() for item in payload.attendees if str(item).strip()],
            location=payload.location.strip() if payload.location else None,
            matter_id=payload.matter_id,
            status=payload.status,
            needs_preparation=bool(payload.needs_preparation),
            metadata=metadata,
        )
        audit.log(
            "assistant_calendar_event_created",
            subject=subject,
            role=role,
            session_id=sid,
            provider=provider,
            external_id=external_id,
            matter_id=payload.matter_id,
        )
        _openclaw_workspace_status(sync=True)
        return {
            "event": event,
            "message": "Takvim planı kaydedildi.",
        }

    @app.get("/integrations/telegram/status")
    def get_telegram_status(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        return _telegram_status_payload(settings, store)

    @app.get("/integrations/assistant-capabilities")
    def get_assistant_capabilities(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        return {
            "agenda": True,
            "suggested_actions": True,
            "draft_first": True,
            "approval_required": True,
            "google_status": _google_status_payload(settings, store),
            "telegram_status": _telegram_status_payload(settings, store),
            "whatsapp_status": _whatsapp_status_payload(settings, store),
            "x_status": _x_status_payload(settings, store),
            "runtime_enabled": llm_service.enabled,
            "assistant_runtime_mode": llm_service.runtime_mode,
        }

    @app.get("/assistant/tools/status")
    def get_assistant_tools_status(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        return {
            "items": build_tools_status(settings, store),
            "generated_from": "connector_registry",
        }

    @app.get("/assistant/home")
    def get_assistant_home(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        home = _assistant_home_payload(settings, store)
        audit.log("assistant_home_viewed", subject=subject, role=role, session_id=sid, priority_count=len(home.get("priority_items", [])))
        return home

    @app.get("/assistant/thread")
    def get_assistant_thread(
        limit: int = 30,
        before_id: int | None = None,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        thread = store.get_or_create_assistant_thread(settings.office_id, created_by=subject)
        thread_id = int(thread["id"])
        messages = store.list_assistant_messages(
            settings.office_id,
            thread_id=thread_id,
            limit=limit,
            before_id=before_id,
        )
        total_count = store.count_assistant_messages(settings.office_id, thread_id=thread_id)
        has_more = bool(messages) and (messages[0]["id"] > 1)
        if has_more:
            first_msg_id = messages[0]["id"]
            with store._conn() as conn:
                earlier = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM assistant_messages WHERE office_id=? AND thread_id=? AND id < ?",
                    (settings.office_id, thread_id, first_msg_id),
                ).fetchone()
                has_more = bool(earlier and int(earlier["cnt"]) > 0)
        audit.log("assistant_thread_viewed", subject=subject, role=role, session_id=sid, message_count=len(messages))
        return {
            "thread": thread,
            "messages": messages,
            "has_more": has_more,
            "total_count": total_count,
            "assistant_summary": build_assistant_home(store, settings.office_id, settings=settings).get("today_summary"),
            "onboarding": _assistant_onboarding_state(settings, store),
            "generated_from": "assistant_thread_memory",
        }

    @app.post("/assistant/thread/messages")
    def post_assistant_thread_message(
        payload: AssistantThreadMessageRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        thread = store.get_or_create_assistant_thread(settings.office_id, created_by=subject)
        prior_messages = store.list_assistant_messages(settings.office_id, thread_id=int(thread["id"]), limit=24)
        linked_entities = ([{"type": "matter", "id": payload.matter_id}] if payload.matter_id else []) + _assistant_source_ref_entities(payload.source_refs)
        store.append_assistant_message(
            settings.office_id,
            thread_id=int(thread["id"]),
            role="user",
            content=payload.content.strip(),
            linked_entities=linked_entities,
            source_context={"source_refs": payload.source_refs or []},
            generated_from="assistant_thread_user",
        )
        pending_calendar = _pending_calendar_event(prior_messages)
        normalized_query = payload.content.strip()
        onboarding_before = _assistant_onboarding_state(settings, store)
        memory_updates = memory_service.capture_chat_signal(normalized_query)
        if not memory_updates:
            memory_updates = _capture_direct_onboarding_answer(
                normalized_query,
                onboarding_state=onboarding_before,
                prior_messages=prior_messages,
                settings=settings,
                store=store,
            )
        onboarding_after = _assistant_onboarding_state(settings, store)
        if pending_calendar and _is_calendar_confirmation(normalized_query):
            provider = "lawcopilot-planner"
            external_id = f"{provider}-{int(time.time() * 1000)}"
            created_event = store.upsert_calendar_event(
                settings.office_id,
                provider=provider,
                external_id=external_id,
                title=str(pending_calendar.get("title") or "Takvim planı"),
                starts_at=str(pending_calendar.get("starts_at")),
                ends_at=str(pending_calendar.get("ends_at")) if pending_calendar.get("ends_at") else None,
                location=str(pending_calendar.get("location") or "").strip() or None,
                matter_id=int(pending_calendar["matter_id"]) if pending_calendar.get("matter_id") else payload.matter_id,
                needs_preparation=bool(pending_calendar.get("needs_preparation")),
                metadata={
                    "captured_from_chat": True,
                    "source_query": pending_calendar.get("source_query"),
                },
            )
            reply = {
                "content": f'"{created_event.get("title")}" kaydını {_format_turkish_datetime(created_event["starts_at"])} için takvime ekledim.',
                "assistant_summary": build_assistant_home(store, settings.office_id, settings=settings).get("today_summary") or "",
                "tool_suggestions": _assistant_tool_suggestions("takvim"),
                "linked_entities": linked_entities + [{"type": "calendar_event", "id": created_event.get("id"), "label": created_event.get("title")}],
                "draft_preview": None,
                "requires_approval": False,
                "generated_from": "assistant_calendar_confirmation",
                "ai_provider": None,
                "ai_model": None,
                "source_context": {
                    "source_refs": payload.source_refs or [],
                    "created_calendar_event": created_event,
                },
            }
        elif pending_calendar and _is_calendar_rejection(normalized_query):
            reply = {
                "content": "Tamam, bu kaydı takvime eklemiyorum.",
                "assistant_summary": build_assistant_home(store, settings.office_id, settings=settings).get("today_summary") or "",
                "tool_suggestions": _assistant_tool_suggestions("takvim"),
                "linked_entities": linked_entities,
                "draft_preview": None,
                "requires_approval": False,
                "generated_from": "assistant_calendar_rejected",
                "ai_provider": None,
                "ai_model": None,
                "source_context": {
                    "source_refs": payload.source_refs or [],
                    "dismissed_calendar_event": pending_calendar,
                },
            }
        elif memory_updates:
            reply = _compose_assistant_onboarding_reply(
                normalized_query,
                home=_assistant_home_payload(settings, store),
                onboarding_state=onboarding_after,
                memory_updates=memory_updates,
            )
        elif _is_onboarding_turn(normalized_query, prior_messages, onboarding_before):
            reply = _compose_assistant_onboarding_reply(
                normalized_query,
                home=_assistant_home_payload(settings, store),
                onboarding_state=onboarding_after,
                memory_updates=memory_updates,
            )
        else:
            reply = _compose_assistant_thread_reply(
                query=normalized_query,
                matter_id=payload.matter_id,
                source_refs=payload.source_refs,
                recent_messages=prior_messages,
                subject=subject,
                settings=settings,
                store=store,
                runtime=runtime,
                events=events,
            )
            reply["content"] = _append_onboarding_followup(reply["content"], onboarding_after, memory_updates=memory_updates)
            reply["source_context"] = {
                **(reply.get("source_context") or {}),
                "onboarding": onboarding_after,
            }
        response_extensions = build_thread_response_extensions(
            reply=reply,
            generated_from=str(reply.get("generated_from") or ""),
            memory_updates=memory_updates,
        )
        reply["source_context"] = {
            **(reply.get("source_context") or {}),
            **response_extensions,
        }
        assistant_message = store.append_assistant_message(
            settings.office_id,
            thread_id=int(thread["id"]),
            role="assistant",
            content=reply["content"],
            linked_entities=reply["linked_entities"],
            tool_suggestions=reply["tool_suggestions"],
            draft_preview=reply["draft_preview"],
            source_context=reply["source_context"],
            requires_approval=bool(reply["requires_approval"]),
            generated_from=reply["generated_from"],
            ai_provider=reply["ai_provider"],
            ai_model=reply["ai_model"],
        )
        messages = store.list_assistant_messages(settings.office_id, thread_id=int(thread["id"]))
        audit.log("assistant_thread_message_posted", subject=subject, role=role, session_id=sid, thread_id=thread["id"])
        _openclaw_workspace_status(sync=True)
        return {
            "thread": thread,
            "messages": messages,
            "message": assistant_message,
            "assistant_summary": reply["assistant_summary"],
            "tool_suggestions": reply["tool_suggestions"],
            "linked_entities": reply["linked_entities"],
            "draft_preview": reply["draft_preview"],
            "requires_approval": reply["requires_approval"],
            "generated_from": reply["generated_from"],
            "ai_provider": reply["ai_provider"],
            "ai_model": reply["ai_model"],
            "onboarding": onboarding_after,
            **response_extensions,
        }

    @app.post("/assistant/thread/reset")
    def reset_assistant_thread(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        thread = store.reset_assistant_thread(settings.office_id, created_by=subject)
        audit.log("assistant_thread_reset", subject=subject, role=role, session_id=sid, thread_id=thread["id"])
        _openclaw_workspace_status(sync=True)
        return {
            "thread": thread,
            "messages": [],
            "message": "Asistan oturumu temizlendi.",
            "generated_from": "assistant_thread_memory",
        }

    @app.get("/assistant/inbox")
    def get_assistant_inbox(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        items = build_assistant_inbox(store, settings.office_id)
        audit.log("assistant_inbox_viewed", subject=subject, role=role, session_id=sid, item_count=len(items))
        return {"items": items, "generated_from": "assistant_agenda_engine"}

    @app.get("/assistant/agenda")
    def get_assistant_agenda(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        items = build_assistant_agenda(store, settings.office_id)
        audit.log("assistant_agenda_viewed", subject=subject, role=role, session_id=sid, item_count=len(items))
        return {"items": items, "generated_from": "assistant_agenda_engine"}

    @app.get("/assistant/calendar")
    def get_assistant_calendar(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        items = build_assistant_calendar(store, settings.office_id)
        audit.log("assistant_calendar_viewed", subject=subject, role=role, session_id=sid, item_count=len(items))
        return {
            "today": datetime.now(timezone.utc).date().isoformat(),
            "items": items,
            "generated_from": "assistant_calendar_engine",
            "google_connected": settings.google_configured and settings.calendar_connected,
        }

    @app.get("/assistant/suggested-actions")
    def get_assistant_suggested_actions(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        sync_connected_accounts_from_settings(settings, store)
        items = build_suggested_actions(store, settings.office_id, created_by=subject)
        audit.log("assistant_actions_viewed", subject=subject, role=role, session_id=sid, item_count=len(items))
        return {"items": items, "generated_from": "assistant_agenda_engine", "manual_review_required": True}

    @app.post("/assistant/actions/generate")
    def generate_assistant_action(
        payload: AssistantActionGenerateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        result = _generate_assistant_action_output(
            payload=payload,
            subject=subject,
            settings=settings,
            store=store,
            runtime=runtime,
            events=events,
        )
        action = result["action"]
        draft = result["draft"]
        audit.log("assistant_action_generated", subject=subject, role=role, session_id=sid, action_id=action["id"], draft_id=draft["id"])
        return {
            "action": action,
            "draft": draft,
            "generated_from": result["generated_from"],
            "manual_review_required": result["manual_review_required"],
            "message": result["message"],
        }

    @app.post("/assistant/actions/{action_id}/approve")
    def approve_assistant_action(
        action_id: int,
        payload: AssistantActionDecisionRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        action = store.get_assistant_action(settings.office_id, action_id)
        if not action:
            raise HTTPException(status_code=404, detail="Aksiyon bulunamadı.")
        draft = store.get_outbound_draft(settings.office_id, int(action["draft_id"])) if action.get("draft_id") else None
        action = store.update_assistant_action_status(settings.office_id, action_id, "approved")
        if draft:
            draft = store.update_outbound_draft(
                settings.office_id,
                int(draft["id"]),
                approval_status="approved",
                delivery_status="ready_to_send" if not settings.connector_dry_run else "manual_review_only",
                approved_by=subject,
                dispatch_state="ready" if not settings.connector_dry_run else "idle",
                dispatch_error=None,
            )
            action = store.update_assistant_action_status(
                settings.office_id,
                action_id,
                "approved",
                draft_id=int(draft["id"]),
                dispatch_state="ready" if not settings.connector_dry_run else "idle",
                dispatch_error=None,
            )
        store.add_approval_event(
            settings.office_id,
            actor=subject,
            event_type="approved",
            action_id=action_id,
            outbound_draft_id=int(draft["id"]) if draft else None,
            note=payload.note or "Taslak onaylandı.",
        )
        audit.log("assistant_action_approved", subject=subject, role=role, session_id=sid, action_id=action_id)
        return {
            "action": action,
            "draft": draft,
            "dispatch_mode": "manual_review_only" if settings.connector_dry_run else "ready_to_send",
            "message": "Taslak onaylandı. Son gönderim kararı hâlâ insandadır.",
        }

    @app.post("/assistant/actions/{action_id}/dismiss")
    def dismiss_assistant_action(
        action_id: int,
        payload: AssistantActionDecisionRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        action = store.update_assistant_action_status(settings.office_id, action_id, "dismissed")
        if not action:
            raise HTTPException(status_code=404, detail="Aksiyon bulunamadı.")
        store.add_approval_event(
            settings.office_id,
            actor=subject,
            event_type="dismissed",
            action_id=action_id,
            outbound_draft_id=int(action["draft_id"]) if action.get("draft_id") else None,
            note=payload.note or "Aksiyon kapatıldı.",
        )
        audit.log("assistant_action_dismissed", subject=subject, role=role, session_id=sid, action_id=action_id)
        return {"action": action, "message": "Aksiyon kapatıldı."}

    @app.get("/assistant/approvals")
    def list_assistant_approvals(
        limit: int = 20,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        actions = store.list_assistant_actions(settings.office_id, status="pending_review", limit=limit)
        items = []
        for action in actions:
            draft = store.get_outbound_draft(settings.office_id, int(action["draft_id"])) if action.get("draft_id") else None
            items.append(
                {
                    "id": f"assistant-action-{action['id']}",
                    "action_id": action["id"],
                    "draft_id": draft.get("id") if draft else None,
                    "status": action.get("status"),
                    "title": action.get("title"),
                    "action_type": action.get("action_type"),
                    "target_channel": action.get("target_channel"),
                    "manual_review_required": bool(action.get("manual_review_required")),
                    "approval_required": True,
                    "draft": draft,
                    "action": action,
                }
            )
        return {"items": items, "generated_from": "approval_registry"}

    @app.post("/assistant/approvals/{approval_id}/approve")
    def approve_assistant_approval(
        approval_id: str,
        payload: AssistantActionDecisionRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        if not approval_id.startswith("assistant-action-"):
            raise HTTPException(status_code=404, detail="Onay kaydı bulunamadı.")
        return approve_assistant_action(
            int(approval_id.replace("assistant-action-", "", 1)),
            payload,
            x_role=x_role,
            authorization=authorization,
        )

    @app.post("/assistant/approvals/{approval_id}/reject")
    def reject_assistant_approval(
        approval_id: str,
        payload: AssistantActionDecisionRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        if not approval_id.startswith("assistant-action-"):
            raise HTTPException(status_code=404, detail="Onay kaydı bulunamadı.")
        return dismiss_assistant_action(
            int(approval_id.replace("assistant-action-", "", 1)),
            payload,
            x_role=x_role,
            authorization=authorization,
        )

    @app.get("/assistant/drafts")
    def list_assistant_drafts(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        assistant_drafts = store.list_outbound_drafts(settings.office_id)
        matter_drafts = store.list_all_matter_drafts(settings.office_id)
        audit.log("assistant_drafts_viewed", subject=subject, role=role, session_id=sid, assistant_draft_count=len(assistant_drafts))
        return {
            "items": assistant_drafts,
            "matter_drafts": matter_drafts,
            "generated_from": "assistant_agenda_engine",
        }

    @app.post("/assistant/drafts/{draft_id}/send")
    def send_assistant_draft(
        draft_id: int,
        payload: AssistantDraftSendRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        draft = store.get_outbound_draft(settings.office_id, draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Taslak bulunamadı.")
        if str(draft.get("delivery_status")) == "sent" or str(draft.get("dispatch_state")) == "completed":
            raise HTTPException(status_code=409, detail="Taslak zaten gönderildi.")
        linked_action = store.get_assistant_action_by_draft_id(settings.office_id, draft_id)
        action_id = int(linked_action["id"]) if linked_action and linked_action.get("id") else None
        if str(draft.get("approval_status")) != "approved":
            draft = store.update_outbound_draft(
                settings.office_id,
                draft_id,
                approval_status="approved",
                delivery_status="ready_to_send" if not settings.connector_dry_run else "manual_review_only",
                approved_by=subject,
                dispatch_state="ready" if not settings.connector_dry_run else "idle",
                dispatch_error=None,
            )
            if linked_action and action_id:
                linked_action = store.update_assistant_action_status(
                    settings.office_id,
                    action_id,
                    "approved",
                    draft_id=draft_id,
                    dispatch_state="ready" if not settings.connector_dry_run else "idle",
                    dispatch_error=None,
                )
            store.add_approval_event(
                settings.office_id,
                actor=subject,
                event_type="approved",
                action_id=action_id,
                outbound_draft_id=draft_id,
                note=payload.note or "Taslak panelinden onaylandı.",
            )
        if settings.connector_dry_run:
            updated = store.update_outbound_draft(
                settings.office_id,
                draft_id,
                delivery_status="manual_review_only",
                approved_by=subject,
                dispatch_state="idle",
            )
            store.add_approval_event(
                settings.office_id,
                actor=subject,
                event_type="dispatch_skipped",
                action_id=action_id,
                outbound_draft_id=draft_id,
                note=payload.note or "Güvenlik nedeniyle taslak modunda bırakıldı.",
            )
            return {
                "draft": updated,
                "action": linked_action,
                "message": "Gönderim güvenlik ayarı nedeniyle taslak modunda bırakıldı.",
                "dispatch_mode": "manual_review_only",
            }
        updated = store.update_outbound_draft(
            settings.office_id,
            draft_id,
            delivery_status="ready_to_send",
            approved_by=subject,
            dispatch_state="ready",
            dispatch_error=None,
        )
        if linked_action and action_id:
            linked_action = store.update_assistant_action_status(
                settings.office_id,
                action_id,
                "approved",
                draft_id=draft_id,
                dispatch_state="ready",
                dispatch_error=None,
            )
        store.add_approval_event(
            settings.office_id,
            actor=subject,
            event_type="dispatch_ready",
            action_id=action_id,
            outbound_draft_id=draft_id,
            note=payload.note or "Taslak dış gönderime hazırlandı.",
        )
        audit.log("assistant_draft_send_requested", subject=subject, role=role, session_id=sid, draft_id=draft_id)
        return {
            "draft": updated,
            "action": linked_action,
            "message": "Taslak gönderime hazırlandı. Otomatik gönderim kapalıysa son adımı manuel doğrulayın.",
            "dispatch_mode": "ready_to_send",
        }

    @app.post("/assistant/drafts/{draft_id}/dispatch-complete")
    def complete_assistant_draft_dispatch(
        draft_id: int,
        payload: AssistantDispatchReportRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        draft = store.update_outbound_draft(
            settings.office_id,
            draft_id,
            delivery_status="sent",
            dispatch_state="completed",
            dispatch_error=None,
            external_message_id=payload.external_message_id,
            last_dispatch_at=datetime.now(timezone.utc).isoformat(),
        )
        if not draft:
            raise HTTPException(status_code=404, detail="Taslak bulunamadı.")
        if payload.action_id:
            store.update_assistant_action_status(
                settings.office_id,
                payload.action_id,
                "completed",
                dispatch_state="completed",
                dispatch_error=None,
                external_message_id=payload.external_message_id,
                last_dispatch_at=datetime.now(timezone.utc).isoformat(),
            )
        store.add_approval_event(
            settings.office_id,
            actor=subject,
            event_type="dispatch_completed",
            action_id=payload.action_id,
            outbound_draft_id=draft_id,
            note=payload.note or "Dış gönderim tamamlandı.",
        )
        audit.log("assistant_draft_dispatch_completed", subject=subject, role=role, session_id=sid, draft_id=draft_id)
        return {"draft": draft, "message": payload.note or "Dış gönderim tamamlandı."}

    @app.post("/assistant/drafts/{draft_id}/dispatch-failed")
    def fail_assistant_draft_dispatch(
        draft_id: int,
        payload: AssistantDispatchReportRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        draft = store.update_outbound_draft(
            settings.office_id,
            draft_id,
            delivery_status="failed",
            dispatch_state="failed",
            dispatch_error=payload.error or "Dış gönderim başarısız oldu.",
            last_dispatch_at=datetime.now(timezone.utc).isoformat(),
        )
        if not draft:
            raise HTTPException(status_code=404, detail="Taslak bulunamadı.")
        if payload.action_id:
            store.update_assistant_action_status(
                settings.office_id,
                payload.action_id,
                "approved",
                dispatch_state="failed",
                dispatch_error=payload.error or "Dış gönderim başarısız oldu.",
                last_dispatch_at=datetime.now(timezone.utc).isoformat(),
            )
        store.add_approval_event(
            settings.office_id,
            actor=subject,
            event_type="dispatch_failed",
            action_id=payload.action_id,
            outbound_draft_id=draft_id,
            note=payload.error or payload.note or "Dış gönderim başarısız oldu.",
        )
        audit.log("assistant_draft_dispatch_failed", subject=subject, role=role, session_id=sid, draft_id=draft_id)
        return {"draft": draft, "message": payload.error or "Dış gönderim başarısız oldu."}

    @app.post("/assistant/actions/{action_id}/dispatch-complete")
    def complete_assistant_action_dispatch(
        action_id: int,
        payload: AssistantDispatchReportRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        action = store.update_assistant_action_status(
            settings.office_id,
            action_id,
            "completed",
            dispatch_state="completed",
            dispatch_error=None,
            external_message_id=payload.external_message_id,
            last_dispatch_at=datetime.now(timezone.utc).isoformat(),
        )
        if not action:
            raise HTTPException(status_code=404, detail="Aksiyon bulunamadı.")
        store.add_approval_event(
            settings.office_id,
            actor=subject,
            event_type="dispatch_completed",
            action_id=action_id,
            outbound_draft_id=int(action["draft_id"]) if action.get("draft_id") else None,
            note=payload.note or "Aksiyon gönderimi tamamlandı.",
        )
        audit.log("assistant_action_dispatch_completed", subject=subject, role=role, session_id=sid, action_id=action_id)
        return {"action": action, "message": payload.note or "Aksiyon gönderimi tamamlandı."}

    @app.post("/assistant/actions/{action_id}/dispatch-failed")
    def fail_assistant_action_dispatch(
        action_id: int,
        payload: AssistantDispatchReportRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        action = store.update_assistant_action_status(
            settings.office_id,
            action_id,
            "approved",
            dispatch_state="failed",
            dispatch_error=payload.error or "Aksiyon gönderimi başarısız oldu.",
            last_dispatch_at=datetime.now(timezone.utc).isoformat(),
        )
        if not action:
            raise HTTPException(status_code=404, detail="Aksiyon bulunamadı.")
        store.add_approval_event(
            settings.office_id,
            actor=subject,
            event_type="dispatch_failed",
            action_id=action_id,
            outbound_draft_id=int(action["draft_id"]) if action.get("draft_id") else None,
            note=payload.error or payload.note or "Aksiyon gönderimi başarısız oldu.",
        )
        audit.log("assistant_action_dispatch_failed", subject=subject, role=role, session_id=sid, action_id=action_id)
        return {"action": action, "message": payload.error or "Aksiyon gönderimi başarısız oldu."}

    @app.get("/workspace")
    def get_workspace(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            return {"configured": False, "workspace": None, "documents": {"items": []}, "scan_jobs": {"items": []}}
        documents = store.list_workspace_documents(settings.office_id, int(root["id"]))
        scan_jobs = store.list_workspace_scan_jobs(settings.office_id, int(root["id"]))
        return {
            "configured": True,
            "workspace": root,
            "documents": {"items": documents[:10], "count": len(documents)},
            "scan_jobs": {"items": scan_jobs[:10]},
        }

    @app.put("/workspace")
    def save_workspace(
        req: WorkspaceRootRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        try:
            root_path = validate_workspace_root(req.root_path)
        except ValueError as exc:
            events.log("workspace_root_rejected", level="warning", office_id=settings.office_id, subject=subject, role=role, error=str(exc))
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            root = store.save_workspace_root(
                settings.office_id,
                req.display_name or root_path.name,
                str(root_path),
                root_hash(root_path),
            )
            audit.log("workspace_root_saved", subject=subject, role=role, session_id=sid, workspace_root_id=root["id"])
            events.log("workspace_root_selected", office_id=settings.office_id, workspace_root_id=root["id"], subject=subject, role=role)
            _openclaw_workspace_status(sync=True)
            return {
                "workspace": root,
                "message": "Çalışma klasörü kaydedildi. Yalnız bu klasör ve alt klasörleri kullanılacak.",
            }
        except Exception as exc:
            import traceback
            with open("/tmp/500_error.txt", "w") as f:
                traceback.print_exc(file=f)
            raise HTTPException(status_code=500, detail=str(exc))
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/workspace/scan")
    def scan_workspace(
        req: WorkspaceScanRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            raise HTTPException(status_code=404, detail="Çalışma klasörü henüz seçilmedi.")
        root_path = validate_workspace_root(str(root["root_path"]))
        normalized_extensions = [ext if ext.startswith(".") else f".{ext}" for ext in (req.extensions or [])]
        job = store.create_workspace_scan_job(settings.office_id, int(root["id"]))
        if not job:
            raise HTTPException(status_code=404, detail="Çalışma klasörü bulunamadı.")
        store.update_workspace_scan_job(settings.office_id, int(job["id"]), status="processing")
        events.log("workspace_scan_started", workspace_root_id=root["id"], subject=subject, role=role)
        try:
            scanned_items, stats = scan_workspace_tree(
                root_path=root_path,
                office_id=settings.office_id,
                workspace_root_id=int(root["id"]),
                max_bytes=settings.max_ingest_bytes,
                extensions=normalized_extensions or None,
            )
            seen_paths: list[str] = []
            indexed_count = 0
            for item in scanned_items:
                record = store.upsert_workspace_document(
                    settings.office_id,
                    int(root["id"]),
                    relative_path=str(item["relative_path"]),
                    display_name=str(item["display_name"]),
                    extension=str(item["extension"]),
                    content_type=item["content_type"],
                    size_bytes=int(item["size_bytes"]),
                    mtime=int(item["mtime"]),
                    checksum=str(item["checksum"]),
                    parser_status=str(item["parser_status"]),
                    indexed_status=str(item["indexed_status"]),
                    document_language=str(item["document_language"]),
                    last_error=item["error"],
                )
                seen_paths.append(str(item["relative_path"]))
                if item["indexed_status"] == "indexed":
                    chunks = build_workspace_chunks(
                        office_id=settings.office_id,
                        workspace_root_id=int(root["id"]),
                        workspace_document_id=int(record["id"]),
                        document_name=str(record["display_name"]),
                        relative_path=str(record["relative_path"]),
                        text=str(item["text"]),
                    )
                    store.replace_workspace_document_chunks(settings.office_id, int(root["id"]), int(record["id"]), chunks)
                    indexed_count += 1
                else:
                    store.replace_workspace_document_chunks(settings.office_id, int(root["id"]), int(record["id"]), [])
            if req.full_rescan:
                store.mark_missing_workspace_documents(settings.office_id, int(root["id"]), seen_paths)
            job = store.update_workspace_scan_job(
                settings.office_id,
                int(job["id"]),
                status="completed",
                files_seen=stats["files_seen"],
                files_indexed=stats["files_indexed"],
                files_skipped=stats["files_skipped"],
                files_failed=stats["files_failed"],
            )
            audit.log(
                "workspace_scan_completed",
                subject=subject,
                role=role,
                session_id=sid,
                workspace_root_id=root["id"],
                files_seen=stats["files_seen"],
                files_indexed=stats["files_indexed"],
                files_failed=stats["files_failed"],
            )
            events.log(
                "workspace_scan_completed",
                workspace_root_id=root["id"],
                subject=subject,
                role=role,
                files_seen=stats["files_seen"],
                files_indexed=indexed_count,
                files_failed=stats["files_failed"],
            )
            _openclaw_workspace_status(sync=True)
            return {
                "workspace": root,
                "job": job,
                "stats": stats,
                "message": "Çalışma klasörü taraması tamamlandı.",
            }
        except ValueError as exc:
            job = store.update_workspace_scan_job(settings.office_id, int(job["id"]), status="failed", error=str(exc))
            events.log("workspace_scan_failed", level="warning", workspace_root_id=root["id"], subject=subject, role=role, error=str(exc))
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/workspace/scan-jobs")
    def list_workspace_scan_jobs(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            return {"configured": False, "items": []}
        return {"configured": True, "workspace_root_id": root["id"], "items": store.list_workspace_scan_jobs(settings.office_id, int(root["id"]))}

    @app.get("/workspace/documents")
    def list_workspace_documents(
        q: str | None = None,
        extension: str | None = None,
        status: str | None = None,
        path_prefix: str | None = None,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            return {"configured": False, "items": []}
        items = store.list_workspace_documents(
            settings.office_id,
            int(root["id"]),
            query_text=q,
            extension=extension,
            status=status,
            path_prefix=path_prefix,
        )
        return {"configured": True, "workspace_root_id": root["id"], "items": items}

    @app.get("/workspace/documents/{document_id}")
    def get_workspace_document(
        document_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        _, record = _require_active_workspace_document(store, settings.office_id, document_id, events, subject=subject, role=role)
        return record

    @app.get("/workspace/documents/{document_id}/chunks")
    def get_workspace_document_chunks(
        document_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        _require_active_workspace_document(store, settings.office_id, document_id, events, subject=subject, role=role)
        items = store.list_workspace_document_chunks(settings.office_id, document_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")
        return {"document_id": document_id, "items": items}

    @app.post("/workspace/search")
    def search_workspace(
        payload: WorkspaceSearchRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            raise HTTPException(status_code=404, detail="Çalışma klasörü henüz seçilmedi.")
        extensions = [ext if ext.startswith(".") else f".{ext}" for ext in (payload.extensions or [])]
        rows = store.search_workspace_document_chunks(
            settings.office_id,
            int(root["id"]),
            path_prefix=payload.path_prefix,
            extensions=extensions or None,
        )
        result = build_workspace_search_result(query=payload.query, rows=rows, limit=payload.limit)
        runtime_completion = None
        if result["citations"]:
            runtime_completion = _maybe_runtime_completion(
                runtime,
                _build_workspace_search_prompt(
                    query=payload.query,
                    citations=result["citations"],
                    related_documents=result["related_documents"],
                    attention_points=result["attention_points"],
                    missing_document_signals=result["missing_document_signals"],
                    draft_suggestions=result["draft_suggestions"],
                    fallback_answer=result["answer"],
                ),
                events,
                task="workspace_search_answer",
                workspace_root_id=root["id"],
                subject=subject,
            )
        if runtime_completion:
            result["answer"] = runtime_completion["text"]
            result["generated_from"] = _runtime_generated_from(
                runtime_completion,
                direct_label="direct_provider+workspace_document_memory",
                advanced_label="openclaw_runtime+workspace_document_memory",
                fallback_label="workspace_document_memory",
            )
            result["ai_provider"] = runtime_completion["provider"]
            result["ai_model"] = runtime_completion["model"]
        else:
            result["generated_from"] = "workspace_document_memory"
            result["ai_provider"] = None
            result["ai_model"] = None
        audit.log("workspace_search", subject=subject, role=role, session_id=sid, workspace_root_id=root["id"], source_count=result["citation_count"])
        events.log(
            "workspace_search_executed",
            workspace_root_id=root["id"],
            subject=subject,
            role=role,
            citation_count=result["citation_count"],
            support_level=result["support_level"],
            generated_from=result["generated_from"],
        )
        return result

    @app.post("/workspace/similar-documents")
    def similar_workspace_documents(
        payload: SimilarDocumentsRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            raise HTTPException(status_code=404, detail="Çalışma klasörü henüz seçilmedi.")
        documents = store.list_workspace_documents(settings.office_id, int(root["id"]), path_prefix=payload.path_prefix)
        if payload.document_id:
            _, source_document = _require_active_workspace_document(store, settings.office_id, payload.document_id, events, subject=subject, role=role)
            rows = store.search_workspace_document_chunks(settings.office_id, int(root["id"]))
            result = find_similar_documents(source_document=source_document, candidate_documents=documents, chunk_rows=rows, limit=payload.limit)
        else:
            if not payload.query:
                raise HTTPException(status_code=422, detail="Benzer belge araması için belge veya sorgu gerekli.")
            rows = store.search_workspace_document_chunks(settings.office_id, int(root["id"]), path_prefix=payload.path_prefix)
            result = build_workspace_search_result(query=payload.query, rows=rows, limit=payload.limit)
            result = {
                "items": [
                    {
                        "workspace_document_id": item["workspace_document_id"],
                        "belge_adi": item["document_name"],
                        "goreli_yol": item.get("relative_path"),
                        "benzerlik_puani": item["relevance_score"],
                        "neden_benzer": "Sorgu ile örtüşen belge pasajları bulundu.",
                        "klasor_baglami": item.get("relative_path") or "Klasör bilgisi kaydedilmedi.",
                        "skor_bilesenleri": {
                            "dosya_adi": 0.0,
                            "icerik": item["relevance_score"],
                            "belge_turu": 0.0,
                            "checksum": 0.0,
                            "klasor_baglami": 0.0,
                            "hukuk_terimleri": 0.0,
                            "genel_skor": item["relevance_score"],
                        },
                        "ortak_terimler": [],
                        "destekleyici_pasajlar": [item],
                        "dikkat_notlari": ["Bu sonuç sorgu benzerliğine dayanır; dosyaya bağlamadan önce pasajı inceleyin."],
                        "taslak_onerileri": ["İnceleme notu taslağı", "İç ekip özeti taslağı"],
                        "manuel_inceleme_gerekir": True,
                        "sinyaller": ["sorgu_eslesmesi"],
                    }
                    for item in result["citations"]
                ],
                "explanation": "Sorgu tabanlı yerel benzer belge taraması tamamlandı.",
                "top_terms": [],
                "manual_review_required": True,
            }
            source_document = {"display_name": payload.query or "Sorgu tabanlı benzerlik"}
        runtime_completion = None
        if result["items"]:
            runtime_completion = _maybe_runtime_completion(
                runtime,
                _build_similarity_explanation_prompt(
                    source_document_name=str(source_document.get("display_name") or source_document.get("relative_path") or "Belge"),
                    items=result["items"],
                    fallback_explanation=result["explanation"],
                ),
                events,
                task="workspace_similarity_explanation",
                workspace_root_id=root["id"],
                subject=subject,
            )
        if runtime_completion:
            result["explanation"] = runtime_completion["text"]
            result["generated_from"] = _runtime_generated_from(
                runtime_completion,
                direct_label="direct_provider+workspace_similarity",
                advanced_label="openclaw_runtime+workspace_similarity",
                fallback_label="workspace_similarity",
            )
            result["ai_provider"] = runtime_completion["provider"]
            result["ai_model"] = runtime_completion["model"]
        else:
            result["generated_from"] = "workspace_similarity"
            result["ai_provider"] = None
            result["ai_model"] = None
        audit.log("workspace_similarity", subject=subject, role=role, session_id=sid, workspace_root_id=root["id"], result_count=len(result["items"]))
        events.log(
            "workspace_similarity_executed",
            workspace_root_id=root["id"],
            subject=subject,
            role=role,
            result_count=len(result["items"]),
            generated_from=result["generated_from"],
        )
        return result

    @app.post("/matters/{matter_id}/documents/attach-from-workspace")
    def attach_workspace_document_to_matter(
        matter_id: int,
        payload: WorkspaceAttachRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        _require_active_workspace_document(store, settings.office_id, payload.workspace_document_id, events, subject=subject, role=role)
        link = store.attach_workspace_document_to_matter(settings.office_id, matter_id, payload.workspace_document_id, subject)
        if not link:
            raise HTTPException(status_code=404, detail="Dosya veya çalışma alanı belgesi bulunamadı.")
        audit.log("workspace_document_attached", subject=subject, role=role, session_id=sid, matter_id=matter_id, workspace_document_id=payload.workspace_document_id)
        events.log("workspace_document_attached_to_matter", matter_id=matter_id, workspace_document_id=payload.workspace_document_id, subject=subject, role=role)
        return link

    @app.get("/matters/{matter_id}/workspace-documents")
    def list_matter_workspace_documents(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_workspace_documents(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        return {"matter_id": matter_id, "items": items}

    @app.post("/auth/token")
    def token(req: TokenRequest):
        if req.role == "admin":
            if settings.bootstrap_admin_key and req.bootstrap_key != settings.bootstrap_admin_key:
                raise HTTPException(status_code=403, detail="admin_bootstrap_key_required")
        jwt, exp, sid = issue_token(settings.jwt_secret, req.subject, req.role, settings.token_ttl_seconds)
        store.store_session(sid, req.subject, req.role, datetime.fromtimestamp(exp, tz=timezone.utc).isoformat())
        audit.log("token_issued", subject=req.subject, role=req.role, session_id=sid)
        return {
            "access_token": jwt,
            "token_type": "bearer",
            "expires_in": settings.token_ttl_seconds,
            "session_id": sid,
        }

    @app.post("/auth/revoke")
    def revoke_session(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        revoked = store.revoke_session(sid)
        audit.log("session_revoked", subject=subject, role=role, session_id=sid, revoked=revoked)
        return {"ok": revoked, "session_id": sid}

    @app.post("/matters")
    def create_matter(
        req: MatterCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        opened_at = req.opened_at.isoformat() if req.opened_at else None
        rec = store.create_matter(
            settings.office_id,
            req.title,
            req.reference_code,
            req.practice_area,
            req.status,
            req.summary,
            req.client_name,
            req.lead_lawyer,
            opened_at,
            subject,
        )
        audit.log(
            "matter_created",
            subject=subject,
            role=role,
            session_id=sid,
            office_id=settings.office_id,
            matter_id=rec["id"],
        )
        events.log("matter_created", office_id=settings.office_id, matter_id=rec["id"], subject=subject, role=role)
        return rec

    @app.get("/matters")
    def list_matters(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return {"office_id": settings.office_id, "items": store.list_matters(settings.office_id)}

    @app.get("/matters/{matter_id}")
    def get_matter(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        rec = store.get_matter(matter_id, settings.office_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        return rec

    @app.patch("/matters/{matter_id}")
    def update_matter(
        matter_id: int,
        req: MatterUpdateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        fields = req.model_dump(exclude_none=True)
        if "opened_at" in fields and req.opened_at is not None:
            fields["opened_at"] = req.opened_at.isoformat()
        rec = store.update_matter(settings.office_id, matter_id, fields)
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_updated", subject=subject, role=role, session_id=sid, matter_id=matter_id, updated_fields=sorted(fields.keys()))
        return rec

    @app.post("/matters/{matter_id}/notes")
    def create_matter_note(
        matter_id: int,
        req: MatterNoteCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        event_at = req.event_at.isoformat() if req.event_at else None
        rec = store.add_matter_note(settings.office_id, matter_id, req.note_type, req.body, subject, event_at)
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_note_created", subject=subject, role=role, session_id=sid, matter_id=matter_id, note_id=rec["id"], note_type=req.note_type)
        return rec

    @app.get("/matters/{matter_id}/timeline")
    def get_matter_timeline(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_timeline(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_timeline_viewed", subject=subject, role=role, session_id=sid, matter_id=matter_id, event_count=len(items))
        events.log("matter_timeline_viewed", matter_id=matter_id, subject=subject, role=role, event_count=len(items))
        return {"matter_id": matter_id, "items": items}

    @app.get("/matters/{matter_id}/chronology")
    def get_matter_chronology(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if not context:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        chronology = build_chronology(
            matter=context["matter"],
            notes=context["notes"],
            chunks=context["chunks"],
            tasks=context["tasks"],
        )
        audit.log(
            "matter_chronology_viewed",
            subject=subject,
            role=role,
            session_id=sid,
            matter_id=matter_id,
            item_count=len(chronology["items"]),
            issue_count=len(chronology["issues"]),
        )
        return chronology

    @app.get("/matters/{matter_id}/risk-notes")
    def get_matter_risk_notes(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if not context:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        chronology = build_chronology(
            matter=context["matter"],
            notes=context["notes"],
            chunks=context["chunks"],
            tasks=context["tasks"],
        )
        risk_notes = build_risk_notes(
            matter=context["matter"],
            documents=context["documents"],
            notes=context["notes"],
            tasks=context["tasks"],
            chronology=chronology,
            chunks=context["chunks"],
        )
        runtime_completion = _maybe_runtime_completion(
            runtime,
            _build_risk_overview_prompt(
                matter=context["matter"],
                chronology=chronology,
                risk_notes=risk_notes,
            ),
            events,
            task="matter_risk_overview",
            matter_id=matter_id,
            subject=subject,
        )
        if runtime_completion:
            risk_notes["ai_overview"] = runtime_completion["text"]
            risk_notes["generated_from"] = _runtime_generated_from(
                runtime_completion,
                direct_label="direct_provider+matter_workflow_engine",
                advanced_label="openclaw_runtime+matter_workflow_engine",
                fallback_label=str(risk_notes.get("generated_from") or "matter_workflow_engine"),
            )
            risk_notes["ai_provider"] = runtime_completion["provider"]
            risk_notes["ai_model"] = runtime_completion["model"]
        audit.log(
            "matter_risk_notes_viewed",
            subject=subject,
            role=role,
            session_id=sid,
            matter_id=matter_id,
            note_count=len(risk_notes["items"]),
        )
        return risk_notes

    @app.get("/matters/{matter_id}/activity")
    def get_matter_activity(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if not context:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        activity = build_activity_stream(
            matter=context["matter"],
            timeline=context["timeline"],
            notes=context["notes"],
            draft_events=context["draft_events"],
            ingestion_jobs=context["ingestion_jobs"],
        )
        audit.log(
            "matter_activity_viewed",
            subject=subject,
            role=role,
            session_id=sid,
            matter_id=matter_id,
            item_count=len(activity["items"]),
        )
        return activity

    @app.get("/matters/{matter_id}/summary")
    def get_matter_summary(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        rec = store.get_matter_summary(settings.office_id, matter_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if context:
            chronology = build_chronology(
                matter=context["matter"],
                notes=context["notes"],
                chunks=context["chunks"],
                tasks=context["tasks"],
            )
            risk_notes = build_risk_notes(
                matter=context["matter"],
                documents=context["documents"],
                notes=context["notes"],
                tasks=context["tasks"],
                chronology=chronology,
                chunks=context["chunks"],
            )
            runtime_completion = _maybe_runtime_completion(
                runtime,
                _build_summary_prompt(
                    matter=context["matter"],
                    chronology=chronology,
                    risk_notes=risk_notes,
                    tasks=context["tasks"],
                    documents=context["documents"],
                    fallback_summary=rec["summary"],
                ),
                events,
                task="matter_summary",
                matter_id=matter_id,
                subject=subject,
            )
            if runtime_completion:
                rec = {
                    **rec,
                    "summary": runtime_completion["text"],
                    "generated_from": _runtime_generated_from(
                        runtime_completion,
                        direct_label="direct_provider+matter_workflow_engine",
                        advanced_label="openclaw_runtime+matter_workflow_engine",
                        fallback_label=str(rec.get("generated_from") or "matter_workflow_engine"),
                    ),
                    "manual_review_required": True,
                    "ai_provider": runtime_completion["provider"],
                    "ai_model": runtime_completion["model"],
                }
        audit.log("matter_summary_viewed", subject=subject, role=role, session_id=sid, matter_id=matter_id)
        events.log("matter_summary_viewed", matter_id=matter_id, subject=subject, role=role)
        return rec

    @app.get("/matters/{matter_id}/tasks")
    def list_matter_tasks(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_tasks(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_tasks_listed", subject=subject, role=role, session_id=sid, matter_id=matter_id, task_count=len(items))
        return {"matter_id": matter_id, "items": items}

    @app.get("/matters/{matter_id}/task-recommendations")
    def get_matter_task_recommendations(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if not context:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        chronology = build_chronology(
            matter=context["matter"],
            notes=context["notes"],
            chunks=context["chunks"],
            tasks=context["tasks"],
        )
        risk_notes = build_risk_notes(
            matter=context["matter"],
            documents=context["documents"],
            notes=context["notes"],
            tasks=context["tasks"],
            chronology=chronology,
            chunks=context["chunks"],
        )
        recommendations = build_task_recommendations(
            matter=context["matter"],
            chronology=chronology,
            risk_notes=risk_notes,
            tasks=context["tasks"],
        )
        audit.log(
            "matter_task_recommendations_viewed",
            subject=subject,
            role=role,
            session_id=sid,
            matter_id=matter_id,
            recommendation_count=len(recommendations["items"]),
        )
        return recommendations

    @app.post("/matters/{matter_id}/drafts")
    def create_matter_draft(
        matter_id: int,
        req: MatterDraftCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        rec = store.create_matter_draft(
            settings.office_id,
            matter_id,
            req.draft_type,
            req.title,
            req.body,
            req.target_channel,
            req.to_contact,
            subject,
        )
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_draft_created", subject=subject, role=role, session_id=sid, matter_id=matter_id, draft_id=rec["id"], draft_type=req.draft_type)
        events.log("matter_draft_created", matter_id=matter_id, draft_id=rec["id"], draft_type=req.draft_type, subject=subject, role=role)
        return rec

    @app.post("/matters/{matter_id}/drafts/generate")
    def generate_workflow_draft(
        matter_id: int,
        req: MatterDraftGenerateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if not context:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        chronology = build_chronology(
            matter=context["matter"],
            notes=context["notes"],
            chunks=context["chunks"],
            tasks=context["tasks"],
        )
        risk_notes = build_risk_notes(
            matter=context["matter"],
            documents=context["documents"],
            notes=context["notes"],
            tasks=context["tasks"],
            chronology=chronology,
            chunks=context["chunks"],
        )
        generated = generate_matter_draft(
            matter=context["matter"],
            draft_type=req.draft_type,
            chronology=chronology,
            risk_notes=risk_notes,
            documents=context["documents"],
            tasks=context["tasks"],
            target_channel=req.target_channel,
            to_contact=req.to_contact,
            instructions=req.instructions,
        )
        runtime_completion = _maybe_runtime_completion(
            runtime,
            _build_draft_prompt(
                matter=context["matter"],
                draft_type=req.draft_type,
                target_channel=req.target_channel,
                to_contact=req.to_contact,
                instructions=req.instructions,
                source_context=generated["source_context"],
                fallback_body=generated["body"],
                profile=store.get_user_profile(settings.office_id),
            ),
            events,
            task="matter_draft_generation",
            matter_id=matter_id,
            subject=subject,
            draft_type=req.draft_type,
        )
        if runtime_completion:
            generated["body"] = runtime_completion["text"]
            generated["generated_from"] = _runtime_generated_from(
                runtime_completion,
                direct_label="direct_provider+matter_workflow_engine",
                advanced_label="openclaw_runtime+matter_workflow_engine",
                fallback_label=str(generated.get("generated_from") or "matter_workflow_engine"),
            )
        rec = store.create_matter_draft(
            settings.office_id,
            matter_id,
            req.draft_type,
            generated["title"],
            generated["body"],
            req.target_channel,
            req.to_contact,
            subject,
            source_context=generated["source_context"],
            generated_from=generated["generated_from"],
            manual_review_required=True,
        )
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log(
            "matter_draft_generated",
            subject=subject,
            role=role,
            session_id=sid,
            matter_id=matter_id,
            draft_id=rec["id"],
            draft_type=req.draft_type,
        )
        events.log("matter_draft_generated", matter_id=matter_id, draft_id=rec["id"], draft_type=req.draft_type, subject=subject, role=role)
        return {
            "draft": rec,
            "review_message": "Bu taslak sistem tarafından üretilmiş bir çalışma çıktısıdır. Dış kullanımdan önce insan incelemesi zorunludur.",
            "generated_from": generated["generated_from"],
            "ai_provider": runtime_completion["provider"] if runtime_completion else None,
            "ai_model": runtime_completion["model"] if runtime_completion else None,
            "source_context": generated["source_context"],
        }

    @app.get("/matters/{matter_id}/drafts")
    def list_matter_drafts(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_drafts(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_drafts_listed", subject=subject, role=role, session_id=sid, matter_id=matter_id, draft_count=len(items))
        return {"matter_id": matter_id, "items": items}

    @app.post("/matters/{matter_id}/documents")
    async def upload_matter_document(
        matter_id: int,
        file: UploadFile = File(...),
        display_name: str | None = Form(default=None),
        source_type: str = Form(default="upload"),
        source_ref: str | None = Form(default=None),
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)

        content = await file.read()
        if len(content) > settings.max_ingest_bytes:
            raise HTTPException(status_code=413, detail="Dosya boyutu sınırı aşıldı.")

        filename = file.filename or "unnamed.txt"
        checksum = hashlib.sha256(content).hexdigest()
        document = store.create_document(
            settings.office_id,
            matter_id,
            filename,
            display_name or filename,
            file.content_type,
            source_type,
            source_ref,
            checksum,
            len(content),
        )
        if not document:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        job = store.create_ingestion_job(settings.office_id, matter_id, int(document["id"]))
        store.update_ingestion_job(settings.office_id, int(job["id"]), "processing")
        store.update_document_status(settings.office_id, int(document["id"]), "processing")
        try:
            text = _extract_text(content)
            chunks = build_persisted_chunks(
                office_id=settings.office_id,
                matter_id=matter_id,
                document_id=int(document["id"]),
                document_name=str(document["display_name"]),
                source_type=source_type,
                text=text,
            )
            if not chunks:
                raise ValueError("Belgeden indekslenecek metin parçaları çıkarılamadı.")
            chunk_count = store.replace_document_chunks(settings.office_id, matter_id, int(document["id"]), chunks)
            document = store.update_document_status(settings.office_id, int(document["id"]), "indexed")
            job = store.update_ingestion_job(settings.office_id, int(job["id"]), "indexed")
            store.record_matter_event(
                settings.office_id,
                matter_id,
                "document_indexed",
                "Dosya belgesi indekslendi",
                f"{document['display_name']} belgesi {chunk_count} parça ile indekslendi",
                document["updated_at"],
                subject,
            )
            audit.log(
                "matter_document_ingested",
                subject=subject,
                role=role,
                session_id=sid,
                matter_id=matter_id,
                document_id=document["id"],
                job_id=job["id"],
                chunk_count=chunk_count,
            )
            events.log(
                "matter_document_ingested",
                matter_id=matter_id,
                document_id=document["id"],
                job_id=job["id"],
                chunk_count=chunk_count,
                subject=subject,
                role=role,
            )
            return {
                "document": document,
                "job": job,
                "chunk_count": chunk_count,
                "rag_runtime": rag_meta,
                "security": {"role_checked": role, "subject": subject, "matter_id": matter_id, "office_id": settings.office_id},
            }
        except ValueError as exc:
            document = store.update_document_status(settings.office_id, int(document["id"]), "failed")
            job = store.update_ingestion_job(settings.office_id, int(job["id"]), "failed", error=str(exc))
            store.record_matter_event(
                settings.office_id,
                matter_id,
                "document_ingest_failed",
                "Dosya belgesi indekslenemedi",
                f"{document['display_name']} belgesi indekslenemedi: {exc}",
                document["updated_at"],
                subject,
            )
            audit.log(
                "matter_document_ingest_failed",
                subject=subject,
                role=role,
                session_id=sid,
                matter_id=matter_id,
                document_id=document["id"],
                job_id=job["id"],
                error=str(exc),
            )
            events.log(
                "matter_document_ingest_failed",
                level="warning",
                matter_id=matter_id,
                document_id=document["id"],
                job_id=job["id"],
                error=str(exc),
                subject=subject,
                role=role,
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/matters/{matter_id}/documents")
    def list_matter_documents(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_documents(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_documents_listed", subject=subject, role=role, session_id=sid, matter_id=matter_id, document_count=len(items))
        return {"matter_id": matter_id, "items": items}

    @app.get("/matters/{matter_id}/documents/{document_id}")
    def get_matter_document(
        matter_id: int,
        document_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        rec = store.get_document(settings.office_id, matter_id, document_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")
        return rec

    @app.get("/matters/{matter_id}/ingestion-jobs")
    def list_matter_ingestion_jobs(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_ingestion_jobs(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_ingestion_jobs_listed", subject=subject, role=role, session_id=sid, matter_id=matter_id, job_count=len(items))
        return {"matter_id": matter_id, "items": items}

    @app.post("/matters/{matter_id}/search")
    def search_matter(
        matter_id: int,
        payload: MatterSearchRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        result = _matter_search_result(
            matter_id=matter_id,
            payload=payload,
            role=role,
            subject=subject,
            sid=sid,
            router=router,
            store=store,
            rag_meta=rag_meta,
            audit=audit,
            events=events,
            runtime=runtime,
            office_id=settings.office_id,
        )
        events.log(
            "matter_search",
            matter_id=matter_id,
            subject=subject,
            role=role,
            support_level=result["support_level"],
            citation_count=result["citation_count"],
            manual_review_required=result["manual_review_required"],
        )
        return result

    @app.get("/documents/{document_id}/chunks")
    def get_document_chunks(
        document_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_document_chunks(settings.office_id, document_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")
        return {"document_id": document_id, "items": items}

    @app.get("/documents/{document_id}/citations")
    def get_document_citations(
        document_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        document = store.get_document_global(settings.office_id, document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")
        chunks = store.list_document_chunks(settings.office_id, document_id)
        if chunks is None:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")
        citations = []
        for idx, chunk in enumerate(chunks, start=1):
            citation = {
                "document_id": document_id,
                "document_name": document.get("display_name"),
                "matter_id": document.get("matter_id"),
                "chunk_id": chunk.get("id"),
                "chunk_index": chunk.get("chunk_index"),
                "excerpt": str(chunk.get("text") or "")[:320],
                "relevance_score": 1.0,
                "source_type": document.get("source_type"),
                "support_type": "document_backed",
                "confidence": "high",
                "line_anchor": chunk.get("metadata", {}).get("line_anchor"),
                "page": chunk.get("metadata", {}).get("page"),
                "line_start": chunk.get("metadata", {}).get("line_start"),
                "line_end": chunk.get("metadata", {}).get("line_end"),
            }
            citations.append(_citation_view(citation, idx))
        return {"document_id": document_id, "matter_id": document.get("matter_id"), "items": citations}

    @app.post("/ingest")
    async def ingest(
        file: UploadFile = File(...),
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)

        content = await file.read()
        if len(content) > settings.max_ingest_bytes:
            raise HTTPException(status_code=413, detail="Dosya boyutu sınırı aşıldı.")

        digest = hashlib.sha256(content).hexdigest()
        meta = rag.add_document(file.filename or "unnamed.txt", content)
        audit.log(
            "ingest",
            subject=subject,
            role=role,
            session_id=sid,
            filename=file.filename,
            sha256=digest,
            indexed_chunks=meta["indexed_chunks"],
        )
        return {
            "filename": file.filename,
            "size": len(content),
            "sha256": digest,
            "status": "indexed",
            "chunks": meta["indexed_chunks"],
            "rag_runtime": rag_meta,
            "security": {"role_checked": role, "subject": subject},
        }

    @app.post("/query")
    def query(
        payload: QueryIn,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return _query_result(
            payload,
            role,
            subject,
            sid,
            router,
            rag,
            rag_meta,
            audit,
            events,
            runtime,
            store.get_user_profile(settings.office_id),
        )

    @app.post("/query/jobs")
    def create_query_job(
        payload: QueryJobCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        job = store.create_query_job(subject, payload.query, payload.model_profile, payload.continue_in_background)

        def _run_job() -> None:
            time.sleep(0.2)
            latest = store.get_query_job(int(job["id"]), subject)
            if not latest or latest.get("cancel_requested"):
                store.update_query_job_status(int(job["id"]), subject, "cancelled")
                return
            try:
                result = _query_result(
                    payload,
                    role,
                    subject,
                    sid,
                    router,
                    rag,
                    rag_meta,
                    audit,
                    events,
                    runtime,
                    store.get_user_profile(settings.office_id),
                )
                detached = bool(latest.get("detached"))
                store.update_query_job_status(
                    int(job["id"]),
                    subject,
                    "completed",
                    result=result,
                    detached=detached,
                    toast_pending=detached,
                )
            except Exception as exc:
                store.update_query_job_status(int(job["id"]), subject, "failed", error=str(exc))

        threading.Thread(target=_run_job, daemon=True).start()
        return {
            "job_id": job["id"],
            "status": "running",
            "ui": {
                "message": "Yanıt hazırlanıyor. İstersen beklemeyi bırakıp arkaplanda devam ettirebilirsin.",
                "cancel_label": "İptal Et",
                "background_label": "Arkaplanda Devam Et",
            },
        }

    @app.get("/query/jobs")
    def list_query_jobs(
        limit: int = 20,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_query_jobs(subject, limit)
        summary = {
            "running": sum(1 for job in items if job.get("status") == "running"),
            "completed": sum(1 for job in items if job.get("status") == "completed"),
            "failed": sum(1 for job in items if job.get("status") == "failed"),
            "cancelled": sum(1 for job in items if job.get("status") == "cancelled"),
            "toast_pending": sum(1 for job in items if job.get("toast_pending")),
        }
        return {"items": items, "summary": summary}

    @app.get("/query/jobs/{job_id}")
    def query_job_status(
        job_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        job = store.get_query_job(job_id, subject)
        if not job:
            raise HTTPException(status_code=404, detail="Sorgu işi bulunamadı.")
        response = {
            "job_id": job["id"],
            "status": job["status"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "completed_at": job.get("completed_at"),
            "result": job.get("result"),
            "error": job.get("error"),
        }
        if job["status"] == "completed" and job.get("toast_pending"):
            response["toast"] = {
                "level": "success",
                "title": "Yanıt hazır",
                "description": "Arkaplanda çalışan AI yanıtı tamamlandı.",
                "ack_endpoint": f"/query/jobs/{job_id}/ack-toast",
            }
        return response

    @app.post("/query/jobs/{job_id}/cancel")
    def cancel_query_job(
        job_id: int,
        keep_background: bool = False,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        job = store.request_query_job_cancel(job_id, subject, keep_background)
        if not job:
            raise HTTPException(status_code=404, detail="Sorgu işi bulunamadı.")
        audit.log(
            "query_job_cancel_requested",
            subject=subject,
            role=role,
            session_id=sid,
            job_id=job_id,
            keep_background=keep_background,
        )
        if keep_background:
            return {"ok": True, "status": "detached", "message": "İşlem arkaplanda devam ediyor."}
        return {"ok": True, "status": "cancelling", "message": "İşlem iptal kuyruğuna alındı."}

    @app.post("/query/jobs/{job_id}/ack-toast")
    def acknowledge_query_job_toast(
        job_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        job = store.acknowledge_query_job_toast(job_id, subject)
        if not job:
            raise HTTPException(status_code=404, detail="Sorgu işi bulunamadı.")
        return {"ok": True, "job_id": job_id, "toast_pending": job.get("toast_pending", False)}

    @app.post("/citations/review")
    def citation_review(
        payload: CitationReviewRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)

        refs = payload.answer.count("[") + payload.answer.lower().count("kaynak")
        score = min(1.0, 0.35 + refs * 0.1)
        grade = "A" if score >= 0.9 else "B" if score >= 0.75 else "C"
        audit.log("citation_review", subject=subject, role=role, session_id=sid, score=round(score, 2), grade=grade)

        return {
            "score": round(score, 2),
            "grade": grade,
            "recommendations": [
                "Her hukuki iddiaya en az bir kaynak ekleyin.",
                "Doğrudan alıntı ve tarih alanlarını doğrulayın.",
            ],
        }

    @app.post("/connectors/preview")
    def connectors_preview(
        req: ConnectorPreviewRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        try:
            wrapped = connector.wrap_action(req.destination, req.message)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        audit.log(
            "connector_preview",
            subject=subject,
            role=role,
            session_id=sid,
            destination=req.destination,
            blocked_pii=wrapped["blocked_pii"],
        )
        events.log(
            "connector_preview",
            subject=subject,
            role=role,
            destination=req.destination,
            blocked_pii=wrapped["blocked_pii"],
            blocked_instruction=wrapped.get("blocked_instruction", False),
            status=wrapped["status"],
        )
        return wrapped

    @app.post("/tasks")
    def create_task(
        req: TaskCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        due_at = req.due_at.isoformat() if req.due_at else None
        try:
            rec = store.create_task(
                req.title,
                due_at,
                req.priority,
                subject,
                office_id=settings.office_id,
                matter_id=req.matter_id,
                origin_type=req.origin_type,
                origin_ref=req.origin_ref,
                recommended_by=req.recommended_by,
                explanation=req.explanation,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        audit.log("task_created", subject=subject, role=role, session_id=sid, task_id=rec["id"])
        events.log("task_created", task_id=rec["id"], matter_id=rec.get("matter_id"), subject=subject, role=role, priority=rec["priority"])
        return rec

    @app.get("/tasks")
    def list_tasks(
        matter_id: int | None = None,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return {"items": store.list_tasks(subject, matter_id=matter_id)}

    @app.post("/tasks/complete-bulk")
    def complete_tasks_bulk(
        req: TaskBulkCompleteRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        task_ids = sorted({int(task_id) for task_id in req.task_ids if int(task_id) > 0})
        updated_count = store.complete_tasks_bulk(task_ids, subject)
        audit.log(
            "tasks_completed_bulk",
            subject=subject,
            role=role,
            session_id=sid,
            task_count=updated_count,
            requested_count=len(task_ids),
        )
        events.log("tasks_completed_bulk", subject=subject, role=role, updated_count=updated_count, requested_count=len(task_ids))
        return {"ok": True, "updated_count": updated_count, "requested_ids": task_ids}

    @app.post("/tasks/update-status")
    def update_task_status(
        req: TaskStatusUpdateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        rec = store.update_task_status(req.task_id, req.status, subject)
        if not rec:
            raise HTTPException(status_code=404, detail="task_not_found")
        audit.log(
            "task_status_updated",
            subject=subject,
            role=role,
            session_id=sid,
            task_id=req.task_id,
            status=req.status,
        )
        events.log("task_status_updated", subject=subject, role=role, task_id=req.task_id, status=req.status, matter_id=rec.get("matter_id"))
        return {"ok": True, "task": rec}

    @app.post("/tasks/update-due")
    def update_task_due_at(
        req: TaskDueUpdateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        due_at = req.due_at.isoformat() if req.due_at else None
        rec = store.update_task_due_at(req.task_id, due_at, subject)
        if not rec:
            raise HTTPException(status_code=404, detail="task_not_found")
        audit.log(
            "task_due_updated",
            subject=subject,
            role=role,
            session_id=sid,
            task_id=req.task_id,
            due_at=due_at,
        )
        events.log("task_due_updated", subject=subject, role=role, task_id=req.task_id, due_at=due_at, matter_id=rec.get("matter_id"))
        return {"ok": True, "task": rec}

    @app.post("/email/drafts")
    def create_email_draft(
        req: EmailDraftCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        try:
            rec = store.create_email_draft(
                str(req.to_email),
                req.subject,
                req.body,
                subject,
                office_id=settings.office_id,
                matter_id=req.matter_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        audit.log(
            "email_draft_created",
            subject=subject,
            role=role,
            session_id=sid,
            draft_id=rec["id"],
            to_email=_safe_excerpt(rec["to_email"]),
        )
        events.log("email_draft_created", draft_id=rec["id"], matter_id=rec.get("matter_id"), subject=subject, role=role)
        return rec

    @app.post("/email/approve")
    def approve_email_draft(
        req: EmailDraftApproveRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("admin", role)
        rec = store.approve_email_draft(req.draft_id, subject)
        if not rec:
            raise HTTPException(status_code=404, detail="draft_not_found")
        audit.log("email_draft_approved", subject=subject, role=role, session_id=sid, draft_id=req.draft_id)
        return {
            "status": rec["status"],
            "draft": rec,
            "dispatch": {
                "mode": "approval_pipeline_only",
                "external_send": "disabled_in_api",
            },
        }

    @app.post("/email/retract")
    def retract_email_draft(
        req: EmailDraftRetractRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("admin", role)
        rec = store.retract_email_draft(req.draft_id, subject, req.reason)
        if not rec:
            raise HTTPException(status_code=404, detail="draft_not_found")
        audit.log(
            "email_draft_retracted",
            subject=subject,
            role=role,
            session_id=sid,
            draft_id=req.draft_id,
            reason=_safe_excerpt(req.reason or ""),
        )
        return {"status": rec["status"], "draft": rec}

    @app.get("/email/drafts/{draft_id}/preview")
    def preview_email_draft(
        draft_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        draft = _ensure_draft_access(store.get_email_draft(draft_id), subject, role)
        body = draft.get("body") or ""
        preview = {
            "id": draft["id"],
            "to_email": draft["to_email"],
            "subject": draft["subject"],
            "status": draft["status"],
            "requested_by": draft["requested_by"],
            "approved_by": draft.get("approved_by"),
            "created_at": draft["created_at"],
            "body_preview": body[:240],
            "body_chars": len(body),
            "body_words": len([w for w in body.split() if w]),
        }
        audit.log("email_draft_previewed", subject=subject, role=role, session_id=sid, draft_id=draft_id)
        return preview

    @app.get("/email/drafts/{draft_id}/history")
    def email_draft_history(
        draft_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        draft = _ensure_draft_access(store.get_email_draft(draft_id), subject, role)
        events = store.list_email_draft_events(draft_id)
        audit.log("email_draft_history_viewed", subject=subject, role=role, session_id=sid, draft_id=draft_id, event_count=len(events))
        return {"draft": draft, "events": events}

    @app.get("/email/drafts")
    def list_email_drafts(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        owner = None if role == "admin" else subject
        return {"items": store.list_email_drafts(owner=owner)}

    @app.post("/social/ingest")
    def social_ingest(
        req: SocialIngestRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        lower = req.content.lower()
        risk = 0.2
        for term in ("dava", "mahkeme", "skandal", "ifşa", "şikayet", "dolandır"):
            if term in lower:
                risk += 0.12
        rec = store.add_social_event(req.source, req.handle, req.content, min(risk, 1.0))
        audit.log("social_ingest", subject=subject, role=role, session_id=sid, event_id=rec["id"], source=req.source)
        return {"event": rec, "mode": "read_only_pipeline"}

    @app.get("/social/events")
    def social_events(
        limit: int = 20,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return {"items": store.list_social_events(limit), "read_only": True}

    return app
