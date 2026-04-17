from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr
import re
from typing import Any
from urllib.parse import quote

from .preference_rules import summarize_source_preference_rules

from .assistant_core import DEFAULT_ASSISTANT_ROLE_SUMMARY, DEFAULT_ASSISTANT_TONE
from .connectors.web_search import build_weather_context
from .policies import evaluate_execution_gateway
from .social_intelligence import social_signal_from_metadata
from .workflows import build_chronology
from .workflows import build_risk_notes


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _parse_profile_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _next_profile_occurrence(item: dict[str, Any], today: date) -> tuple[date, int] | None:
    base = _parse_profile_date(item.get("date"))
    if not base:
        return None
    if bool(item.get("recurring_annually", True)):
        try:
            candidate = date(today.year, base.month, base.day)
        except ValueError:
            return None
        if candidate < today:
            try:
                candidate = date(today.year + 1, base.month, base.day)
            except ValueError:
                return None
    else:
        candidate = base
        if candidate < today:
            return None
    return candidate, (candidate - today).days


def _related_profiles(profile: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in profile.get("related_profiles") or []:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                "id": str(raw.get("id") or "").strip(),
                "name": str(raw.get("name") or "").strip(),
                "relationship": str(raw.get("relationship") or "").strip(),
                "closeness": _normalize_related_profile_closeness(raw.get("closeness"), relationship=str(raw.get("relationship") or "").strip()),
                "preferences": str(raw.get("preferences") or "").strip(),
                "notes": str(raw.get("notes") or "").strip(),
                "important_dates": list(raw.get("important_dates") or []),
            }
        )
    return [item for item in items if item["name"]]


def _default_related_profile_closeness(relationship: str) -> int:
    normalized = _normalize_monitor_text(relationship)
    if not normalized:
        return 3
    if any(token in normalized for token in ("anne", "baba", "es", "partner", "sevgili", "cocuk", "oglum", "kizim")):
        return 5
    if any(token in normalized for token in ("kardes", "arkadas", "kuzen", "aile", "yakin dost")):
        return 4
    if any(token in normalized for token in ("avukat", "doktor", "musteri", "muvekkil", "is ortagi", "koc")):
        return 3
    return 3


def _normalize_related_profile_closeness(value: Any, *, relationship: str = "") -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = _default_related_profile_closeness(relationship)
    return max(1, min(5, numeric))


def _upcoming_profile_dates(store, office_id: str, *, window_days: int) -> list[dict[str, Any]]:
    profile = store.get_user_profile(office_id)
    today = datetime.now(timezone.utc).date()
    items: list[dict[str, Any]] = []
    for index, item in enumerate(profile.get("important_dates") or [], start=1):
        resolved = _next_profile_occurrence(item, today)
        if not resolved:
            continue
        occurrence, days_until = resolved
        if days_until > window_days:
            continue
        items.append(
            {
                "id": f"profile-date-{index}",
                "label": str(item.get("label") or "Önemli tarih"),
                "notes": str(item.get("notes") or "").strip(),
                "date": occurrence.isoformat(),
                "days_until": days_until,
                "recurring_annually": bool(item.get("recurring_annually", True)),
                "owner_name": str(profile.get("display_name") or "").strip(),
                "relationship": "self",
                "profile_type": "self",
            }
        )
    for profile_index, related in enumerate(_related_profiles(profile), start=1):
        owner_name = related["name"]
        relationship = related["relationship"]
        for date_index, item in enumerate(related.get("important_dates") or [], start=1):
            resolved = _next_profile_occurrence(item, today)
            if not resolved:
                continue
            occurrence, days_until = resolved
            if days_until > window_days:
                continue
            label = str(item.get("label") or "Önemli tarih")
            details = str(item.get("notes") or "").strip()
            if related["preferences"]:
                details = f"{details} {related['preferences']}".strip()
            elif related["notes"]:
                details = f"{details} {related['notes']}".strip()
            items.append(
                {
                    "id": f"related-profile-date-{profile_index}-{date_index}",
                    "label": f"{owner_name}: {label}" if owner_name else label,
                    "notes": details,
                    "date": occurrence.isoformat(),
                    "days_until": days_until,
                    "recurring_annually": bool(item.get("recurring_annually", True)),
                    "owner_name": owner_name,
                    "relationship": relationship,
                    "profile_type": "related",
                }
            )
    items.sort(key=lambda item: (item["days_until"], item["label"]))
    return items


def _integration_metadata_connected(metadata: dict[str, Any] | None, keys: list[str] | None = None) -> bool:
    if not metadata:
        return False
    for key in list(keys or []):
        if bool(metadata.get(key)):
            return True
    return False


def _integration_has_local_data(store, office_id: str, provider: str) -> bool:
    normalized = str(provider or "").strip().lower()
    if normalized == "google":
        return bool(
            store.list_email_threads(office_id, provider="google")
            or store.list_calendar_events(office_id, limit=10, provider="google")
            or store.list_drive_files(office_id, limit=10)
        )
    if normalized == "outlook":
        return bool(
            store.list_email_threads(office_id, provider="outlook")
            or store.list_calendar_events(office_id, limit=10, provider="outlook")
        )
    return False


def sync_connected_accounts_from_settings(settings, store) -> list[dict[str, Any]]:
    accounts: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    def _meaningful(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return True

    def _merge_metadata(existing: dict[str, Any] | None, updates: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(existing or {})
        for key, value in dict(updates or {}).items():
            if _meaningful(value):
                merged[key] = value
        return merged

    def _sync_setting_managed_account(
        provider: str,
        *,
        enabled: bool,
        configured: bool,
        account_label: str | None,
        default_label: str,
        scopes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        manual_review_required: bool = True,
        update_last_sync_on_configured: bool = False,
        configured_implies_connected: bool = True,
        connected_metadata_keys: list[str] | None = None,
    ) -> None:
        existing = store.get_connected_account(settings.office_id, provider)
        if not (enabled or configured):
            if existing:
                accounts.append(existing)
            return

        existing_status = str(existing.get("status") or "").strip().lower() if existing else ""
        was_connected = existing_status == "connected"
        merged_scopes = list(scopes or existing.get("scopes") or []) if existing else list(scopes or [])
        merged_metadata = _merge_metadata(existing.get("metadata") if existing else None, metadata)
        local_data_available = _integration_has_local_data(store, settings.office_id, provider)
        metadata_connected = _integration_metadata_connected(merged_metadata, connected_metadata_keys)
        effective_connected = bool(
            was_connected
            or metadata_connected
            or local_data_available
            or (configured and configured_implies_connected)
        )
        effective_status = "connected" if effective_connected else "pending"
        existing_label = str(existing.get("account_label") or "").strip() if existing else ""
        effective_label = str(account_label or "").strip() or existing_label or default_label
        connected_at = (
            str(existing.get("connected_at") or "").strip() if existing else ""
        ) or (now_iso if effective_connected else None)
        last_sync_at = (
            str(existing.get("last_sync_at") or "").strip() if existing else ""
        ) or (now_iso if (effective_connected and update_last_sync_on_configured and local_data_available) else None)
        accounts.append(
            store.upsert_connected_account(
                settings.office_id,
                provider,
                account_label=effective_label,
                status=effective_status,
                scopes=merged_scopes,
                connected_at=connected_at,
                last_sync_at=last_sync_at,
                manual_review_required=manual_review_required,
                metadata=merged_metadata,
            )
        )

    if settings.provider_configured:
        accounts.append(
            store.upsert_connected_account(
                settings.office_id,
                "openclaw-codex" if settings.provider_type == "openai-codex" else settings.provider_type or "model-provider",
                account_label=settings.provider_model or settings.provider_type or "Model sağlayıcısı",
                status="connected",
                scopes=["model:generate", "workspace:analyze"],
                connected_at=now_iso,
                manual_review_required=False,
                metadata={"provider_type": settings.provider_type, "provider_model": settings.provider_model},
            )
        )
    _sync_setting_managed_account(
        "google",
        enabled=settings.google_enabled,
        configured=settings.google_configured,
        account_label=settings.google_account_label,
        default_label="Google hesabı",
        scopes=list(settings.google_scopes),
        update_last_sync_on_configured=True,
        configured_implies_connected=False,
        connected_metadata_keys=["gmail_connected", "calendar_connected", "drive_connected"],
    )
    _sync_setting_managed_account(
        "outlook",
        enabled=settings.outlook_enabled,
        configured=settings.outlook_configured,
        account_label=settings.outlook_account_label,
        default_label="Outlook hesabı",
        scopes=list(settings.outlook_scopes),
        update_last_sync_on_configured=True,
        configured_implies_connected=False,
        connected_metadata_keys=["mail_connected", "calendar_connected"],
    )
    _sync_setting_managed_account(
        "telegram",
        enabled=settings.telegram_enabled,
        configured=settings.telegram_configured,
        account_label=settings.telegram_account_label or settings.telegram_bot_username,
        default_label="Telegram botu",
        scopes=["messages:send", "messages:read"],
        metadata={
            "allowed_user_id": settings.telegram_allowed_user_id,
            "mode": settings.telegram_mode,
            "account_label": settings.telegram_account_label or settings.telegram_bot_username,
        },
    )
    _sync_setting_managed_account(
        "whatsapp",
        enabled=settings.whatsapp_enabled,
        configured=settings.whatsapp_configured,
        account_label=settings.whatsapp_account_label or settings.whatsapp_display_phone_number,
        default_label="WhatsApp hesabı",
        scopes=["messages:read", "messages:send"],
        metadata={
            "phone_number_id": settings.whatsapp_phone_number_id,
            "display_phone_number": settings.whatsapp_display_phone_number,
        },
    )
    _sync_setting_managed_account(
        "x",
        enabled=settings.x_enabled,
        configured=settings.x_configured,
        account_label=settings.x_account_label,
        default_label="X hesabı",
        scopes=list(settings.x_scopes or []),
        metadata={"user_id": settings.x_user_id},
    )
    _sync_setting_managed_account(
        "instagram",
        enabled=settings.instagram_enabled,
        configured=settings.instagram_configured,
        account_label=settings.instagram_account_label or settings.instagram_username,
        default_label="Instagram hesabı",
        scopes=list(settings.instagram_scopes or []),
        metadata={
            "page_id": settings.instagram_page_id,
            "instagram_account_id": settings.instagram_account_id,
            "username": settings.instagram_username,
        },
    )
    _sync_setting_managed_account(
        "linkedin",
        enabled=settings.linkedin_enabled,
        configured=settings.linkedin_configured,
        account_label=settings.linkedin_account_label,
        default_label="LinkedIn hesabı",
        scopes=list(settings.linkedin_scopes or []),
        metadata={
            "user_id": settings.linkedin_user_id,
            "person_urn": settings.linkedin_person_urn,
            "mode": settings.linkedin_mode,
        },
    )
    return store.list_connected_accounts(settings.office_id)

def _profile_display_name(profile: dict[str, Any]) -> str:
    return str(profile.get("display_name") or "").strip()


def _profile_preference_text(profile: dict[str, Any]) -> str:
    lines = [
        str(profile.get(field) or "").strip()
        for field in [
            "assistant_notes",
            "travel_preferences",
            "transport_preference",
            "weather_preference",
            "food_preferences",
            "location_preferences",
            "prayer_habit_notes",
            "communication_style",
        ]
    ]
    lines.extend(summarize_source_preference_rules(profile.get("source_preference_rules") or [], limit=3))
    return " ".join(part for part in lines if part).lower()


def _profile_location_label(profile: dict[str, Any]) -> str:
    return str(profile.get("current_location") or profile.get("home_base") or "").strip()


def _maps_provider_key(profile: dict[str, Any]) -> str:
    normalized = str(profile.get("maps_preference") or "").strip().lower()
    if "apple" in normalized:
        return "apple"
    if "yandex" in normalized:
        return "yandex"
    return "google"


def _build_map_search_url(profile: dict[str, Any], query: str) -> str:
    compact_query = str(query or "").strip()
    if not compact_query:
        return ""
    encoded = quote(compact_query)
    provider = _maps_provider_key(profile)
    if provider == "apple":
        return f"https://maps.apple.com/?q={encoded}"
    if provider == "yandex":
        return f"https://yandex.com/maps/?text={encoded}"
    return f"https://www.google.com/maps/search/?api=1&query={encoded}"


WEATHER_CONTEXT_CACHE_TTL = timedelta(minutes=30)
WEATHER_CONTEXT_CACHE_MAX_ITEMS = 48
WEATHER_PREPARATION_EVENT_WINDOW_HOURS = 36
_WEATHER_CONTEXT_CACHE: dict[str, tuple[datetime, dict[str, Any]]] = {}
_LOCATION_VENUE_TOKENS = {
    "adliye",
    "adliyesi",
    "mahkemesi",
    "court",
    "ofis",
    "office",
    "otel",
    "hotel",
    "terminal",
    "terminali",
    "gar",
    "gari",
    "istasyon",
    "istasyonu",
    "station",
    "airport",
    "havalimani",
    "havalimanı",
    "salonu",
    "salon",
    "cami",
    "mosque",
    "kampus",
    "kampüs",
    "universitesi",
    "üniversitesi",
}


def _location_weather_focus(value: str | None) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    for separator in (" / ", "/", ",", " - ", "-", "•", "|"):
        if separator in text:
            head = text.split(separator, 1)[0].strip()
            if head:
                return head
    parts = text.split()
    if len(parts) >= 2 and _normalize_monitor_text(parts[1]) in _LOCATION_VENUE_TOKENS:
        return parts[0]
    if len(parts) >= 3 and _normalize_monitor_text(parts[2]) in _LOCATION_VENUE_TOKENS:
        return " ".join(parts[:2])
    return text


def _same_location_context(left: str | None, right: str | None) -> bool:
    left_key = _normalize_monitor_text(_location_weather_focus(left or ""))
    right_key = _normalize_monitor_text(_location_weather_focus(right or ""))
    if not left_key or not right_key:
        return False
    return left_key in right_key or right_key in left_key


def _weather_context_cache_key(query: str, profile_note: str) -> str:
    return f"{_normalize_monitor_text(query)}|{_normalize_monitor_text(profile_note)}"


def _cached_weather_context(query: str, *, profile_note: str = "", limit: int = 4) -> dict[str, Any]:
    cleaned_query = " ".join(str(query or "").split()).strip()
    if not cleaned_query:
        return {
            "query": "",
            "search_query": "",
            "results": [],
            "summary": "Hava durumu için konum bilgisi eksik.",
        }
    now = datetime.now(timezone.utc)
    cache_key = _weather_context_cache_key(cleaned_query, profile_note)
    cached = _WEATHER_CONTEXT_CACHE.get(cache_key)
    if cached and now - cached[0] <= WEATHER_CONTEXT_CACHE_TTL:
        return cached[1]
    try:
        payload = build_weather_context(cleaned_query, profile_note=profile_note, limit=limit)
    except Exception:
        payload = {
            "query": cleaned_query,
            "search_query": f"{cleaned_query} hava durumu",
            "results": [],
            "summary": "Hava durumu verisini şu an toplayamadım.",
        }
    _WEATHER_CONTEXT_CACHE[cache_key] = (now, payload)
    if len(_WEATHER_CONTEXT_CACHE) > WEATHER_CONTEXT_CACHE_MAX_ITEMS:
        oldest_keys = sorted(_WEATHER_CONTEXT_CACHE.items(), key=lambda item: item[1][0])[
            : len(_WEATHER_CONTEXT_CACHE) - WEATHER_CONTEXT_CACHE_MAX_ITEMS
        ]
        for key, _ in oldest_keys:
            _WEATHER_CONTEXT_CACHE.pop(key, None)
    return payload


def _weather_signal_summary(context: dict[str, Any]) -> dict[str, str]:
    haystack = _normalize_monitor_text(
        " ".join(
            [
                str(context.get("summary") or ""),
                str(context.get("query") or ""),
                *[
                    " ".join(
                        [
                            str(result.get("title") or ""),
                            str(result.get("snippet") or ""),
                        ]
                    )
                    for result in context.get("results") or []
                    if isinstance(result, dict)
                ],
            ]
        )
    )
    if any(token in haystack for token in ("thunderstorm", "firtina", "storm", "kuvvetli ruzgar", "kuvvetli yagis")):
        return {
            "severity": "high",
            "headline": "kuvvetli yağış veya rüzgar sinyali görünüyor",
            "advice": "Şemsiye, kapalı ayakkabı ve biraz ekstra yol süresi planlamak iyi olur.",
        }
    if any(token in haystack for token in ("yagmur", "saganak", "showers", "rain")):
        return {
            "severity": "high",
            "headline": "yağış ihtimali öne çıkıyor",
            "advice": "Şemsiye veya su geçirmez bir katman düşünmeni öneririm.",
        }
    if any(token in haystack for token in ("kar", "snow", "sleet", "buzlanma", "ice")):
        return {
            "severity": "high",
            "headline": "soğuk ve karlı hava ihtimali var",
            "advice": "Kalın katman, uygun ayakkabı ve erken çıkış planı iyi olur.",
        }
    if any(token in haystack for token in ("ruzgar", "wind", "windy")):
        return {
            "severity": "medium",
            "headline": "rüzgar etkisi görülebilir",
            "advice": "Dışarıda daha uzun kalacaksan hafif bir üst katman iyi olabilir.",
        }
    if any(token in haystack for token in ("cold", "soguk", "serin", "dusuk sicaklik", "low temperature")):
        return {
            "severity": "medium",
            "headline": "serin hava öne çıkıyor",
            "advice": "İnce bir ceket veya ek katman düşünmek iyi olur.",
        }
    if any(token in haystack for token in ("heat", "hot", "sicak", "yuksek sicaklik", "high temperature")):
        return {
            "severity": "medium",
            "headline": "sıcak hava öne çıkıyor",
            "advice": "Su, hafif giyim ve gölge planı işini kolaylaştırır.",
        }
    if any(token in haystack for token in ("sunny", "gunesli", "clear", "acik")):
        return {
            "severity": "low",
            "headline": "açık ve daha rahat bir hava görünüyor",
            "advice": "Yine de çıkıştan önce kısa bir son kontrol yapmak iyi olur.",
        }
    return {
        "severity": "medium",
        "headline": "hava koşullarını çıkıştan önce netleştirmek iyi olur",
        "advice": "İstersen kısa bir özet çıkarıp yanında ne alman gerektiğini söyleyebilirim.",
    }


def _select_upcoming_weather_event(
    calendar: list[dict[str, Any]],
    *,
    current_location: str,
    now: datetime,
) -> dict[str, Any] | None:
    candidates: list[tuple[int, datetime, dict[str, Any]]] = []
    for item in calendar:
        starts_at = _parse_dt(item.get("starts_at"))
        location = str(item.get("location") or "").strip()
        if not starts_at or not location:
            continue
        if starts_at < now or starts_at > now + timedelta(hours=WEATHER_PREPARATION_EVENT_WINDOW_HOURS):
            continue
        remote_priority = 0 if current_location and not _same_location_context(location, current_location) else 1
        candidates.append((remote_priority, starts_at, item))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _current_location_weather_suggestion(profile: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
    location_label = _profile_location_label(profile)
    if not location_label:
        return None
    focus = _location_weather_focus(location_label) or location_label
    weather_note = str(profile.get("weather_preference") or "").strip()
    query_suffix = "bugün sabah" if now.hour < 11 else "bugün"
    context = _cached_weather_context(f"{focus} {query_suffix}", profile_note=weather_note, limit=4)
    signal = _weather_signal_summary(context)
    opener = "Bugün evden çıkmadan önce" if now.hour < 11 else "Bugün"
    details = f"{opener} {focus} için {signal['headline']}. {signal['advice']}"
    return {
        "id": f"proactive-weather-local-{quote(focus, safe='')[:32]}",
        "kind": "weather_preparation",
        "title": f"{focus} için hava hazırlığını netleştirelim",
        "details": details,
        "action_label": "Hava durumunu aç",
        "prompt": (
            f"{focus} için güncel hava durumunu kısa ve net özetle. "
            "Özellikle sabah dışarı çıkarken dikkat edilmesi gerekenleri, gerekiyorsa yanında alınacak şeyleri belirt."
        ),
        "tool": "weather",
        "priority": "high" if signal["severity"] == "high" else "medium",
        "secondary_action_label": "Haritada aç",
        "secondary_action_url": _build_map_search_url(profile, location_label),
        "summary_line": f"{focus} için hava hazırlığı önerisi çıkardım.",
    }


def _calendar_weather_suggestion(
    profile: dict[str, Any],
    event: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any] | None:
    starts_at = _parse_dt(event.get("starts_at"))
    location = str(event.get("location") or "").strip()
    if not starts_at or not location:
        return None
    focus = _location_weather_focus(location) or location
    weather_note = str(profile.get("weather_preference") or "").strip()
    is_tomorrow = starts_at.date() == (now + timedelta(days=1)).date()
    is_today = starts_at.date() == now.date()
    query_time = "yarın" if is_tomorrow else "bugün" if is_today else _format_turkish_day_label(starts_at)
    context = _cached_weather_context(f"{focus} {query_time}", profile_note=weather_note, limit=4)
    signal = _weather_signal_summary(context)
    event_title = str(event.get("title") or "takvim kaydı").strip() or "takvim kaydı"
    when_label = "Yarın" if is_tomorrow else "Bugün" if is_today else _format_turkish_day_label(starts_at)
    time_label = starts_at.strftime("%H:%M")
    current_location = _profile_location_label(profile)
    travel_note = ""
    if current_location and not _same_location_context(location, current_location):
        travel_note = f" Şu anki konum bağlamın {current_location}; çıkış süresini buna göre biraz erken planlamak iyi olur."
    details = (
        f"{when_label} {focus} için {signal['headline']}. {signal['advice']} "
        f"{event_title} {time_label} civarı olduğu için hazırlığını buna göre yapalım."
        f"{travel_note}"
    ).strip()
    return {
        "id": f"proactive-weather-event-{event['id']}",
        "kind": "weather_trip_watch",
        "title": f"{event_title} için hava durumunu hesaba katalım",
        "details": details,
        "action_label": "Hava özetini çıkar",
        "prompt": (
            f"{event_title} için {location} konumunun güncel hava durumunu kontrol et. "
            f"Etkinlik zamanı {starts_at.isoformat()} olacak. "
            "Kısa özet ver, risk varsa yanında alınması gerekenleri ve çıkış planına etkisini belirt."
        ),
        "tool": "weather",
        "priority": "high" if signal["severity"] == "high" or starts_at <= now + timedelta(hours=24) else "medium",
        "secondary_action_label": "Haritada aç",
        "secondary_action_url": _build_map_search_url(profile, location),
        "summary_line": f"{when_label.lower()} {focus} için hava hazırlığı önerisi çıkardım.",
    }


def _turkish_month_name(month: int) -> str:
    months = {
        1: "Ocak",
        2: "Şubat",
        3: "Mart",
        4: "Nisan",
        5: "Mayıs",
        6: "Haziran",
        7: "Temmuz",
        8: "Ağustos",
        9: "Eylül",
        10: "Ekim",
        11: "Kasım",
        12: "Aralık",
    }
    return months.get(int(month), "Tarih")


def _format_turkish_day_label(value: datetime | date | None) -> str:
    if value is None:
        return "yakın tarih"
    base = value.date() if isinstance(value, datetime) else value
    return f"{base.day} {_turkish_month_name(base.month)}"


def _format_time_window(start: datetime | None, end: datetime | None) -> str:
    if not start:
        return "uygun zaman"
    if not end:
        return start.strftime("%H:%M")
    return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"


def _channel_label(item: dict[str, Any]) -> str:
    source_type = str(item.get("source_type") or "").strip().lower()
    provider = str(item.get("provider") or "").strip().lower()
    if source_type == "email_thread":
        if provider == "outlook":
            return "Outlook e-postası"
        if provider == "google":
            return "Gmail"
        return "e-posta"
    if source_type == "telegram_message":
        return "Telegram"
    if source_type == "whatsapp_message":
        return "WhatsApp"
    if source_type == "x_message":
        return "X DM"
    if source_type == "instagram_message":
        return "Instagram DM"
    if source_type == "linkedin_message":
        return "LinkedIn DM"
    if source_type == "x_post":
        return "X"
    if source_type == "social_event":
        return "sosyal kanal"
    return "iletişim"


def _reply_contact_label(item: dict[str, Any]) -> str:
    for key in ("contact_label", "sender", "author_handle", "title"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return "karşı taraf"


def _reply_subject_label(item: dict[str, Any]) -> str:
    value = str(item.get("thread_subject") or item.get("title") or "").strip()
    return value or "ileti"


def _relative_due_label(value: str | None) -> str:
    due_at = _parse_dt(value)
    if not due_at:
        return "yakın zamanda"
    delta = datetime.now(timezone.utc) - due_at
    total_minutes = max(1, int(delta.total_seconds() // 60))
    if total_minutes < 60:
        return f"yaklaşık {total_minutes} dakikadır"
    if total_minutes < 90:
        return "yaklaşık 1 saattir"
    total_hours = total_minutes // 60
    if total_hours < 24:
        return f"yaklaşık {total_hours} saattir"
    total_days = total_hours // 24
    if total_days == 1:
        return "yaklaşık 1 gündür"
    return f"yaklaşık {total_days} gündür"


LOW_SIGNAL_EMAIL_LABELS = {
    "CATEGORY_FORUMS",
    "CATEGORY_PROMOTIONS",
    "CATEGORY_SOCIAL",
    "CATEGORY_UPDATES",
}

LOW_SIGNAL_EMAIL_SENDER_TOKENS = (
    "no-reply",
    "noreply",
    "do-not-reply",
    "donotreply",
    "mailer-daemon",
    "newsletter",
    "notifications",
    "notification",
    "updates",
)

LOW_SIGNAL_EMAIL_TEXT_TOKENS = (
    "unsubscribe",
    "abonelikten çık",
    "abonelikten cik",
    "list-unsubscribe",
    "auto-submitted",
    "bulk",
    "bulk mail",
    "announcement",
    "duyuru",
    "bilgilendirme",
    "system notification",
    "sistem bildirimi",
    "newsletter",
    "bülten",
    "bulten",
    "kampanya",
    "indirim",
    "fırsat",
    "firsat",
    "promosyon",
    "promotion",
    "promo",
    "webinar",
    "özel teklif",
    "ozel teklif",
    "special offer",
    "limited time",
    "flash sale",
    "daha iyi fiyat",
    "best price",
    "coupon",
    "kupon",
    "günün fırsatı",
    "gunun firsati",
    "weekly digest",
    "daily digest",
    "haftalık özet",
    "haftalik ozet",
    "do not reply",
    "bu e-postayı yanıtlamayın",
    "bu e postayi yanitlamayin",
    "bu otomatik bir iletidir",
    "bu otomatik bir e-postadır",
    "bu otomatik bir e postadir",
    "this mailbox is not monitored",
    "güvenlik uyarısı",
    "guvenlik uyarisi",
    "security alert",
    "account security",
    "hesabınıza yeni uygulamalar bağlandı",
    "hesabiniza yeni uygulamalar baglandi",
    "new applications connected",
    "new application connected",
    "new app connected",
    "connected to your account",
    "planınız",
    "planiniz",
    "planın",
    "planin",
    "üyelik",
    "uyelik",
    "membership",
    "subscription",
    "renewal",
    "yenileme",
    "yenilenecek",
    "yenilenmeyecek",
    "depolama alanı",
    "depolama alani",
    "storage",
    "welcome to your",
    "release notes",
    "product update",
    "changelog",
    "book a demo",
    "schedule a demo",
    "demo",
    "introducing",
)

ACTIONABLE_EMAIL_MAX_AGE_HOURS = 7 * 24
ACTIONABLE_COMMUNICATION_SUMMARY_MAX_AGE_HOURS = 72

DIRECT_REPLY_EMAIL_TEXT_TOKENS = (
    "?",
    "yanıt",
    "yanit",
    "cevap",
    "dönüş",
    "donus",
    "geri dönüş",
    "geri donus",
    "rica",
    "lütfen",
    "lutfen",
    "inceleyebilir",
    "hazırlayabilir",
    "hazirlayabilir",
    "gözden geçir",
    "gozden gecir",
    "yardımcı olabilir",
    "yardimci olabilir",
    "müsait",
    "musait",
    "teyit",
    "confirm",
    "review",
    "reply",
    "respond",
    "can you",
    "could you",
    "please",
)

WORK_CONTEXT_EMAIL_TEXT_TOKENS = (
    "müvekkil",
    "muvekkil",
    "müşteri",
    "musteri",
    "client",
    "dosya",
    "dava",
    "duruşma",
    "durusma",
    "sözleşme",
    "sozlesme",
    "icra",
    "tebligat",
    "belge",
    "evrak",
    "petition",
    "case",
    "court",
    "contract",
    "agreement",
    "toplantı",
    "toplanti",
    "meeting",
)

PROFILE_MONITORED_ITEM_MAX_AGE_HOURS = 24 * 30
IMPORTANT_CONTACT_SELECTION_THRESHOLD = 10
IMPORTANT_CONTACT_HIGH_CONFIDENCE_THRESHOLD = 15
IMPORTANT_CONTACT_LOOKAHEAD_DAYS = 5

RELATIONSHIP_KEYWORD_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Anne", ("annem", "anne", "annemci", "mom", "mother", "mama")),
    ("Baba", ("babam", "baba", "dad", "father")),
    ("Eş", ("esim", "eşim", "karim", "karım", "kocam", "wife", "husband", "spouse")),
    ("Kızım", ("kizim", "kızım", "daughter")),
    ("Oğlum", ("oglum", "oğlum", "son")),
    ("Yakın arkadaş", ("yakin arkadasim", "yakın arkadaşım", "kankam", "dostum", "best friend", "closest friend")),
    ("Patron", ("patronum", "mudurum", "müdürüm", "yoneticim", "yöneticim", "amirim", "manager", "boss")),
    ("Kardeş", ("kardesim", "kardeşim", "ablam", "abim", "brother", "sister", "sibling")),
)

PREFERENCE_SIGNAL_LIBRARY: tuple[dict[str, Any], ...] = (
    {
        "tokens": ("çikolata", "cikolata"),
        "positive": "Çikolatayı seviyor.",
        "negative": "Çikolata pek sevmiyor.",
        "gift": "Küçük bir çikolata",
    },
    {
        "tokens": ("kahve",),
        "positive": "Kahveyi seviyor.",
        "negative": "Kahveyi pek sevmiyor.",
        "gift": "İyi bir kahve",
    },
    {
        "tokens": ("cay", "çay"),
        "positive": "Çayı seviyor.",
        "negative": "Çayı pek tercih etmiyor.",
        "gift": "Güzel bir çay",
    },
    {
        "tokens": ("cicek", "çiçek", "buket"),
        "positive": "Çiçekten hoşlanıyor.",
        "negative": "Çiçekten pek hoşlanmıyor.",
        "gift": "Küçük bir çiçek",
    },
    {
        "tokens": ("kitap", "roman"),
        "positive": "Kitabı seviyor.",
        "negative": "Kitap yerine başka hediyeleri tercih ediyor.",
        "gift": "İlgi alanına uygun bir kitap",
    },
    {
        "tokens": ("tatli", "tatlı", "dessert"),
        "positive": "Tatlıyı seviyor.",
        "negative": "Tatlıyı pek tercih etmiyor.",
        "gift": "Küçük bir tatlı",
    },
)

POSITIVE_PREFERENCE_TOKENS = (
    " sever",
    " cok sever",
    " çok sever",
    " bayilir",
    " bayılır",
    " hoslanir",
    " hoşlanır",
    " favori",
    " favorisi",
    " duskun",
    " düşkün",
)

NEGATIVE_PREFERENCE_TOKENS = (
    " sevmez",
    " hoslanmaz",
    " hoşlanmaz",
    " istemez",
    " uzak durur",
    " alerjisi",
)

TRANSACTIONAL_CONTACT_MESSAGE_TOKENS = (
    "kargo",
    "kargom",
    "teslimat",
    "gonderi",
    "gönderi",
    "siparis",
    "sipariş",
    "siparisim",
    "siparişim",
    "takip no",
    "takip numarasi",
    "takip numarası",
    "iade",
    "fatura",
    "geldi",
    "gelcek",
    "gelecek",
    "yolda",
)

LOW_SIGNAL_CONTACT_TOKENS = (
    "noreply",
    "no-reply",
    "newsletter",
    "kampanya",
    "duyuru",
    "billing",
    "support",
    "destek",
    "reklam",
    "promo",
    "tanitim",
    "tanıtım",
)

CONTACT_ROLE_INFERENCE_LIBRARY: tuple[dict[str, Any], ...] = (
    {
        "label": "Seyahat / hava yolu hesabı",
        "summary": "Uçuş, bilet ve seyahat bildirimleri gönderen kurumsal hesap.",
        "tokens": (
            "pegasus",
            "ucus",
            "uçuş",
            "bilet",
            "boarding",
            "check in",
            "check-in",
            "pnr",
            "bagaj",
            "airline",
            "flight",
            "seyahat",
            "trip",
        ),
        "domains": ("pegasus", "thy", "turkishairlines", "sunexpress", "ajet", "anadolujet"),
    },
    {
        "label": "Konaklama / rezervasyon hesabı",
        "summary": "Rezervasyon, konaklama ve giriş doğrulama bildirimleri gönderen kurumsal hesap.",
        "tokens": (
            "booking",
            "reservation",
            "rezervasyon",
            "otel",
            "hotel",
            "konaklama",
            "property",
            "guest",
            "check in",
            "check-in",
            "dogrulama kodu",
            "doğrulama kodu",
            "giris yap",
            "giriş yap",
        ),
        "domains": ("booking", "airbnb", "expedia", "agoda", "hotels"),
    },
    {
        "label": "Kargo / teslimat hesabı",
        "summary": "Gönderi, kargo ve teslimat güncellemeleri gönderen hesap.",
        "tokens": (
            "kargo",
            "teslimat",
            "gonderi",
            "gönderi",
            "shipment",
            "tracking",
            "takip no",
            "takip numarasi",
            "takip numarası",
            "delivery",
            "courier",
        ),
    },
    {
        "label": "Banka / ödeme hesabı",
        "summary": "Ödeme, kart ve hesap hareketleriyle ilgili kurumsal hesap.",
        "tokens": (
            "banka",
            "bank",
            "odeme",
            "ödeme",
            "payment",
            "iban",
            "eft",
            "havale",
            "kart",
            "ekstre",
            "hesap ozeti",
            "hesap özeti",
            "fatura",
        ),
    },
    {
        "label": "Sipariş / alışveriş hesabı",
        "summary": "Sipariş, iade veya teslim sürecini yöneten alışveriş hesabı.",
        "tokens": (
            "siparis",
            "sipariş",
            "order",
            "iade",
            "refund",
            "marketplace",
            "satici",
            "satıcı",
            "urun",
            "ürün",
            "checkout",
            "sepet",
        ),
    },
    {
        "label": "İş başvurusu / kariyer hesabı",
        "summary": "Başvuru, özgeçmiş veya görüşme sürecine ait iletişim hesabı.",
        "tokens": (
            "cv",
            "özgeçmiş",
            "ozgecmis",
            "resume",
            "başvuru",
            "basvuru",
            "application",
            "interview",
            "recruit",
            "career",
            "kariyer",
            "human resources",
            "insan kaynaklari",
            "insan kaynakları",
            "talent acquisition",
            "recruitment",
        ),
    },
    {
        "label": "Destek / müşteri hizmetleri hesabı",
        "summary": "Destek talebi veya müşteri hizmetleri için kullanılan hesap.",
        "tokens": (
            "destek",
            "support",
            "yardim",
            "yardım",
            "ticket",
            "talep",
            "case",
        ),
    },
    {
        "label": "Bülten / kampanya hesabı",
        "summary": "Duyuru, kampanya veya otomatik bülten gönderen hesap.",
        "tokens": LOW_SIGNAL_CONTACT_TOKENS,
    },
)

CONTACT_TOPIC_INFERENCE_LIBRARY: tuple[dict[str, Any], ...] = (
    {
        "label": "Seyahat ve rota planı",
        "summary": "Seyahat, rota ve yurt dışı hazırlıkları üzerine sık konuşuyorsunuz.",
        "tokens": (
            "balkan",
            "yurt disi",
            "yurt dışı",
            "ucus",
            "uçuş",
            "valiz",
            "otel",
            "rota",
            "yol",
            "hiz limit",
            "hız limit",
            "euro",
            "para birimi",
            "roaming",
            "tur",
            "seyahat",
        ),
    },
    {
        "label": "Aile planı ve organizasyon",
        "summary": "Aile planları, ziyaretler ve günlük koordinasyon üzerine sık haberleşiyorsunuz.",
        "tokens": (
            "annem",
            "babam",
            "kahvalti",
            "kahvaltı",
            "uğrar",
            "ugrar",
            "geliriz",
            "arayabilir misin",
            "arayayim",
            "arayayım",
            "musait",
            "müsait",
            "ailem",
        ),
    },
    {
        "label": "Alışveriş ve hazırlık",
        "summary": "Alışveriş, alınacaklar ve hazırlık listeleri hakkında konuşuyorsunuz.",
        "tokens": (
            "alalim",
            "alalım",
            "alacagim",
            "alacağım",
            "valizine koy",
            "liste",
            "siparis",
            "sipariş",
            "harclik",
            "harçlık",
            "masraf",
            "hazirlik",
            "hazırlık",
        ),
    },
    {
        "label": "İş ve başvuru gündemi",
        "summary": "İş, başvuru veya profesyonel süreçler hakkında düzenli konuşuyorsunuz.",
        "tokens": (
            "cv",
            "özgeçmiş",
            "ozgecmis",
            "basvuru",
            "başvuru",
            "interview",
            "müvekkil",
            "muvekkil",
            "dosya",
            "dilekce",
            "dilekçe",
        ),
    },
)


def _text_haystack(*values: object) -> str:
    return " ".join(str(value or "").strip() for value in values).lower()


def _normalize_monitor_text(value: object) -> str:
    normalized = str(value or "").strip().lower()
    translation = str.maketrans(
        {
            "ç": "c",
            "ğ": "g",
            "ı": "i",
            "ö": "o",
            "ş": "s",
            "ü": "u",
        }
    )
    return " ".join(normalized.translate(translation).split())


def _stable_contact_identifiers(value: object) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    normalized = raw.lower().strip()
    if not normalized:
        return []
    identifiers: list[str] = []

    def _push(candidate: str) -> None:
        compact = " ".join(str(candidate or "").split()).strip()
        if compact and compact not in identifiers:
            identifiers.append(compact)

    compact = normalized
    for prefix in ("mailto:", "tel:", "chat:", "whatsapp:"):
        if compact.startswith(prefix):
            compact = compact[len(prefix) :]
    if compact.startswith("https://wa.me/"):
        compact = compact.replace("https://wa.me/", "", 1)
    if compact.startswith("http://wa.me/"):
        compact = compact.replace("http://wa.me/", "", 1)

    if "@" in compact:
        local, _, domain = compact.partition("@")
        domain = domain.strip()
        local = local.strip()
        if domain in {"c.us", "s.whatsapp.net", "lid", "lid.whatsapp.net"} and local:
            _push(f"wa:{local}")
        elif domain == "g.us" and local:
            _push(f"wa-group:{local}")
        elif "." in domain and local:
            _push(f"email:{local}@{domain}")
    phone_like_text = bool(re.fullmatch(r"\+?[\d\s().-]{7,24}", compact))
    digits = "".join(character for character in compact if character.isdigit())
    if phone_like_text and 7 <= len(digits) <= 15:
        if compact.startswith("+") or compact.startswith("00") or any(character in compact for character in " -()"):
            _push(f"phone:{digits}")
        elif len(digits) <= 13:
            _push(f"phone:{digits}")
        if 10 < len(digits) <= 13:
            _push(f"phone:{digits[-10:]}")

    if compact.startswith("@") and len(compact) > 1:
        _push(f"handle:{compact}")

    if re.fullmatch(r"[a-z0-9._:/-]{4,96}", compact):
        _push(f"id:{compact}")

    return identifiers


def _contact_display_name_score(value: str) -> tuple[int, int]:
    label = str(value or "").strip()
    if not label:
        return (-100, 0)
    normalized = _normalize_monitor_text(label)
    score = 0
    if _relationship_hint_from_candidates([label]):
        score += 12
    if "@" in label:
        score -= 6
    if any(character.isdigit() for character in label):
        score -= 5
    if normalized.startswith(("wa-group:", "phone:", "email:", "id:")):
        score -= 8
    if any(token in normalized for token in LOW_SIGNAL_CONTACT_TOKENS):
        score -= 4
    if len(label.split()) >= 2:
        score += 2
    if len(label) <= 3:
        score -= 1
    return (score, len(label))


def _has_strong_contact_identifier(candidate: str) -> bool:
    normalized = _normalize_monitor_text(candidate)
    if not normalized:
        return False
    if normalized.startswith(("phone:", "email:", "wa:", "wa-group:", "handle:")):
        return True
    if normalized.startswith("id:"):
        token = normalized[3:]
        return any(character.isdigit() for character in token) or any(character in token for character in "@/._:-")
    return False


def _profile_has_inbox_positive_filters(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return False
    return bool(profile.get("inbox_watch_rules") or profile.get("inbox_keyword_rules"))


def _normalized_inbox_channels(value: object) -> set[str]:
    items = value if isinstance(value, list) else []
    normalized: set[str] = set()
    aliases = {
        "gmail": "email",
        "google": "email",
        "outlook": "email",
        "mail": "email",
        "e-posta": "email",
        "eposta": "email",
        "wp": "whatsapp",
        "twitter": "x",
        "dm": "x",
    }
    for item in items:
        token = _normalize_monitor_text(item)
        if not token:
            continue
        normalized.add(aliases.get(token, token))
    return normalized


def _channel_matches_rule(rule_channels: object, channel: str) -> bool:
    allowed = _normalized_inbox_channels(rule_channels)
    if not allowed:
        return True
    return _normalize_monitor_text(channel) in allowed


def _active_inbox_block_rules(profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    for raw in (profile or {}).get("inbox_block_rules") or []:
        if not isinstance(raw, dict):
            continue
        expires_at = _parse_dt(str(raw.get("expires_at") or "").strip())
        if expires_at and expires_at <= now:
            continue
        items.append(raw)
    return items


def _monitor_text_matches(match_value: str, candidates: list[str]) -> bool:
    target = _normalize_monitor_text(match_value)
    if not target:
        return False
    for candidate in candidates:
        normalized_candidate = _normalize_monitor_text(candidate)
        if not normalized_candidate:
            continue
        if target in normalized_candidate or normalized_candidate in target:
            return True
    return False


def _monitor_keyword_match(keyword_rules: list[dict[str, Any]], *, channel: str, haystack_values: list[str]) -> tuple[str, str] | tuple[None, None]:
    haystack = _normalize_monitor_text(" ".join(haystack_values))
    if not haystack:
        return None, None
    for rule in keyword_rules:
        if not _channel_matches_rule(rule.get("channels"), channel):
            continue
        keyword = str(rule.get("keyword") or "").strip()
        normalized_keyword = _normalize_monitor_text(keyword)
        if not normalized_keyword:
            continue
        if normalized_keyword in haystack:
            return keyword, str(rule.get("label") or keyword).strip() or keyword
    return None, None


def _monitor_rule_match(
    rules: list[dict[str, Any]],
    *,
    channel: str,
    match_type: str,
    candidates: list[str],
) -> tuple[str, str] | tuple[None, None]:
    for rule in rules:
        if str(rule.get("match_type") or "").strip() != match_type:
            continue
        if not _channel_matches_rule(rule.get("channels"), channel):
            continue
        match_value = str(rule.get("match_value") or rule.get("label") or "").strip()
        if not match_value:
            continue
        if _monitor_text_matches(match_value, candidates):
            return match_value, str(rule.get("label") or match_value).strip() or match_value
    return None, None


def _build_monitoring_decision(
    profile: dict[str, Any] | None,
    *,
    channel: str,
    actor_values: list[str],
    group_values: list[str],
    haystack_values: list[str],
    actionable: bool,
    occurred_at: str | None,
) -> dict[str, Any]:
    watch_rules = [item for item in (profile or {}).get("inbox_watch_rules") or [] if isinstance(item, dict)]
    keyword_rules = [item for item in (profile or {}).get("inbox_keyword_rules") or [] if isinstance(item, dict)]
    block_rules = _active_inbox_block_rules(profile)
    has_positive_filters = bool(watch_rules or keyword_rules)

    blocked_person_value, blocked_person_label = _monitor_rule_match(
        block_rules,
        channel=channel,
        match_type="person",
        candidates=actor_values,
    )
    blocked_group_value, blocked_group_label = _monitor_rule_match(
        block_rules,
        channel=channel,
        match_type="group",
        candidates=group_values,
    )
    if blocked_person_value or blocked_group_value:
        blocked_label = blocked_person_label or blocked_group_label or blocked_person_value or blocked_group_value or ""
        return {
            "include": False,
            "blocked": True,
            "reason_kind": "blocked",
            "reason_label": blocked_label,
            "reason_text": f"{blocked_label} için engel kuralı aktif." if blocked_label else "Engel kuralı aktif.",
            "matched_keyword": None,
            "matched_value": blocked_person_value or blocked_group_value,
            "has_positive_filters": has_positive_filters,
        }

    watch_person_value, watch_person_label = _monitor_rule_match(
        watch_rules,
        channel=channel,
        match_type="person",
        candidates=actor_values,
    )
    if watch_person_value:
        reason_label = watch_person_label or watch_person_value
        recent_ok = actionable or _is_recent_today_signal(occurred_at, max_age_hours=PROFILE_MONITORED_ITEM_MAX_AGE_HOURS)
        return {
            "include": recent_ok,
            "blocked": False,
            "reason_kind": "watch_person",
            "reason_label": reason_label,
            "reason_text": f"{reason_label} izlenen kişi listesinde." if reason_label else "İzlenen kişi eşleşti.",
            "matched_keyword": None,
            "matched_value": watch_person_value,
            "has_positive_filters": has_positive_filters,
        }

    watch_group_value, watch_group_label = _monitor_rule_match(
        watch_rules,
        channel=channel,
        match_type="group",
        candidates=group_values,
    )
    if watch_group_value:
        reason_label = watch_group_label or watch_group_value
        recent_ok = actionable or _is_recent_today_signal(occurred_at, max_age_hours=PROFILE_MONITORED_ITEM_MAX_AGE_HOURS)
        return {
            "include": recent_ok,
            "blocked": False,
            "reason_kind": "watch_group",
            "reason_label": reason_label,
            "reason_text": f"{reason_label} izlenen grup listesinde." if reason_label else "İzlenen grup eşleşti.",
            "matched_keyword": None,
            "matched_value": watch_group_value,
            "has_positive_filters": has_positive_filters,
        }

    keyword, keyword_label = _monitor_keyword_match(keyword_rules, channel=channel, haystack_values=haystack_values)
    if keyword:
        recent_ok = actionable or _is_recent_today_signal(occurred_at, max_age_hours=PROFILE_MONITORED_ITEM_MAX_AGE_HOURS)
        return {
            "include": recent_ok,
            "blocked": False,
            "reason_kind": "keyword",
            "reason_label": keyword_label or keyword,
            "reason_text": f"“{keyword_label or keyword}” anahtar kelimesi geçti.",
            "matched_keyword": keyword,
            "matched_value": keyword,
            "has_positive_filters": has_positive_filters,
        }

    if has_positive_filters:
        return {
            "include": False,
            "blocked": False,
            "reason_kind": "filtered_out",
            "reason_label": "",
            "reason_text": "",
            "matched_keyword": None,
            "matched_value": None,
            "has_positive_filters": True,
        }

    return {
        "include": actionable,
        "blocked": False,
        "reason_kind": "default_actionable" if actionable else "default_ignored",
        "reason_label": "",
        "reason_text": "",
        "matched_keyword": None,
        "matched_value": None,
        "has_positive_filters": False,
    }


def _email_sender_identity(thread: dict[str, Any]) -> tuple[str, str, str, str]:
    metadata = dict(thread.get("metadata") or {})
    participants = [str(item).strip() for item in thread.get("participants") or [] if str(item).strip()]
    raw_sender = str(metadata.get("sender") or metadata.get("from") or (participants[0] if participants else "")).strip()
    display_name, sender_email = parseaddr(raw_sender)
    display_name = str(display_name or "").strip()
    sender_email = str(sender_email or metadata.get("sender_email") or "").strip().lower()
    if not display_name and raw_sender:
        display_name = raw_sender.split("<", 1)[0].strip()
    sender_domain = sender_email.split("@", 1)[1].lower() if "@" in sender_email else ""
    return raw_sender, display_name, sender_email, sender_domain


def _email_text_signal_haystack(thread: dict[str, Any]) -> str:
    metadata = dict(thread.get("metadata") or {})
    raw_sender, display_name, sender_email, sender_domain = _email_sender_identity(thread)
    return _text_haystack(
        raw_sender,
        display_name,
        sender_email,
        sender_domain,
        metadata.get("reply_to"),
        metadata.get("sender_title"),
        metadata.get("sender_role"),
        thread.get("subject"),
        thread.get("snippet"),
        *(thread.get("participants") or []),
    )


def _has_direct_reply_signal(thread: dict[str, Any]) -> bool:
    if bool(thread.get("reply_needed")):
        return True
    haystack = _email_text_signal_haystack(thread)
    return any(token in haystack for token in DIRECT_REPLY_EMAIL_TEXT_TOKENS)


def _has_work_context_signal(thread: dict[str, Any]) -> bool:
    if thread.get("matter_id"):
        return True
    haystack = _email_text_signal_haystack(thread)
    return any(token in haystack for token in WORK_CONTEXT_EMAIL_TEXT_TOKENS)


def _has_informational_email_signal(thread: dict[str, Any]) -> bool:
    haystack = _email_text_signal_haystack(thread)
    return any(token in haystack for token in LOW_SIGNAL_EMAIL_TEXT_TOKENS)


def _looks_like_human_email_sender(thread: dict[str, Any]) -> bool:
    metadata = dict(thread.get("metadata") or {})
    raw_sender, display_name, sender_email, _ = _email_sender_identity(thread)
    sender_haystack = _text_haystack(raw_sender, display_name, sender_email, metadata.get("reply_to"))
    if any(token in sender_haystack for token in LOW_SIGNAL_EMAIL_SENDER_TOKENS):
        return False
    if bool(metadata.get("auto_generated")):
        return False
    if str(metadata.get("precedence") or "").strip().lower() in {"bulk", "list", "junk"}:
        return False
    return bool(raw_sender or sender_email)


def _is_low_signal_email_thread(thread: dict[str, Any]) -> bool:
    metadata = dict(thread.get("metadata") or {})
    labels = {str(item or "").strip().upper() for item in metadata.get("labels") or [] if str(item or "").strip()}
    haystack = _text_haystack(
        _email_text_signal_haystack(thread),
        metadata.get("precedence"),
        metadata.get("auto_submitted"),
        metadata.get("list_unsubscribe"),
    )
    score = 0
    if labels.intersection(LOW_SIGNAL_EMAIL_LABELS):
        score += 2
    if any(token in haystack for token in LOW_SIGNAL_EMAIL_SENDER_TOKENS):
        score += 1
    if any(token in haystack for token in LOW_SIGNAL_EMAIL_TEXT_TOKENS):
        score += 1
    if bool(metadata.get("auto_generated")):
        score += 1
    if str(metadata.get("precedence") or "").strip().lower() in {"bulk", "list", "junk"}:
        score += 1
    if str(metadata.get("inference_classification") or "").strip().lower() == "other":
        score += 1
    if bool(metadata.get("list_unsubscribe")):
        score += 1
    return score >= 2


def _is_recent_today_signal(value: str | None, *, max_age_hours: int = 48) -> bool:
    due_at = _parse_dt(value)
    if not due_at:
        return True
    return due_at >= datetime.now(timezone.utc) - timedelta(hours=max_age_hours)


def _is_actionable_email_thread(thread: dict[str, Any], *, max_age_hours: int = ACTIONABLE_EMAIL_MAX_AGE_HOURS) -> bool:
    importance_reason = _important_contact_reason(
        dict(thread.get("metadata") or {}).get("sender"),
        thread.get("subject"),
        thread.get("snippet"),
        dict(thread.get("metadata") or {}).get("sender_title"),
        dict(thread.get("metadata") or {}).get("sender_role"),
    )
    has_reply_signal = _has_direct_reply_signal(thread)
    has_work_context = _has_work_context_signal(thread)
    has_informational_signal = _has_informational_email_signal(thread)
    looks_human = _looks_like_human_email_sender(thread)
    if importance_reason:
        return True
    if _is_low_signal_email_thread(thread) and not has_work_context:
        return False
    if has_informational_signal and not has_work_context:
        return False
    if has_reply_signal and looks_human:
        return _is_recent_today_signal(thread.get("received_at"), max_age_hours=max_age_hours)
    if has_work_context and looks_human:
        return _is_recent_today_signal(thread.get("received_at"), max_age_hours=max_age_hours)
    if not looks_human:
        return False
    if has_informational_signal:
        return False
    if not _is_recent_today_signal(thread.get("received_at"), max_age_hours=max_age_hours):
        return False
    return True


def _email_thread_monitoring_decision(profile: dict[str, Any] | None, thread: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(thread.get("metadata") or {})
    raw_sender, display_name, sender_email, sender_domain = _email_sender_identity(thread)
    actionable = _is_actionable_email_thread(thread)
    participants = [str(item).strip() for item in thread.get("participants") or [] if str(item).strip()]
    return _build_monitoring_decision(
        profile,
        channel="email",
        actor_values=[
            raw_sender,
            display_name,
            sender_email,
            sender_domain,
            str(metadata.get("sender_title") or ""),
            str(metadata.get("sender_role") or ""),
            *participants,
        ],
        group_values=[],
        haystack_values=[
            raw_sender,
            display_name,
            sender_email,
            sender_domain,
            str(metadata.get("sender_title") or ""),
            str(metadata.get("sender_role") or ""),
            str(thread.get("subject") or ""),
            str(thread.get("snippet") or ""),
            *participants,
        ],
        actionable=actionable,
        occurred_at=str(thread.get("received_at") or ""),
    )


def _whatsapp_message_group_label(message: dict[str, Any]) -> str:
    metadata = dict(message.get("metadata") or {})
    conversation_ref = str(message.get("conversation_ref") or "").strip()
    group_name = str(metadata.get("group_name") or metadata.get("chat_name") or "").strip()
    is_group = bool(metadata.get("is_group")) or conversation_ref.endswith("@g.us")
    return group_name if is_group and group_name else ""


def _whatsapp_message_contact_label(message: dict[str, Any]) -> str:
    metadata = dict(message.get("metadata") or {})
    conversation_ref = str(message.get("conversation_ref") or "").strip()
    is_group = bool(metadata.get("is_group")) or conversation_ref.endswith("@g.us")
    if is_group:
        return (
            str(metadata.get("contact_name") or "").strip()
            or str(metadata.get("profile_name") or "").strip()
            or str(message.get("sender") or "").strip()
            or str(message.get("recipient") or "").strip()
            or conversation_ref
            or "WhatsApp"
        )
    direction = str(message.get("direction") or "").strip().lower()
    preferred_direct_label = (
        str(metadata.get("chat_name") or "").strip()
        or str(metadata.get("contact_name") or "").strip()
        or str(metadata.get("profile_name") or "").strip()
    )
    if direction == "outbound":
        return (
            preferred_direct_label
            or str(message.get("recipient") or "").strip()
            or str(message.get("sender") or "").strip()
            or conversation_ref
            or "WhatsApp"
        )
    return (
        preferred_direct_label
        or str(message.get("sender") or "").strip()
        or str(message.get("recipient") or "").strip()
        or conversation_ref
        or "WhatsApp"
    )


def _whatsapp_message_actor_label(message: dict[str, Any]) -> str:
    return _whatsapp_message_contact_label(message)


def _extract_whatsapp_phone_number(value: object) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith("tel:"):
        raw = raw[4:]
    if raw.startswith("https://wa.me/"):
        raw = raw.replace("https://wa.me/", "", 1)
    elif raw.startswith("http://wa.me/"):
        raw = raw.replace("http://wa.me/", "", 1)
    if "@" in raw:
        local, _, domain = raw.partition("@")
        domain = domain.strip()
        local = local.strip()
        if domain in {"c.us", "s.whatsapp.net"}:
            digits = "".join(character for character in local if character.isdigit())
            return digits if 7 <= len(digits) <= 15 else ""
        return ""
    if not re.fullmatch(r"\+?[\d\s().-]{7,24}", raw):
        return ""
    digits = "".join(character for character in raw if character.isdigit())
    if not (7 <= len(digits) <= 15):
        return ""
    if raw.startswith("+") or raw.startswith("00") or any(character in raw for character in " -()"):
        return digits
    return digits if len(digits) <= 13 else ""


def _extract_telegram_phone_number(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    digits = "".join(character for character in raw if character.isdigit())
    if not (7 <= len(digits) <= 15):
        return ""
    if re.fullmatch(r"\+?[\d\s().-]{7,24}", raw):
        return digits
    return digits if raw.isdigit() and len(digits) <= 13 else ""


def _whatsapp_message_phone_numbers(message: dict[str, Any]) -> list[str]:
    metadata = dict(message.get("metadata") or {})
    conversation_ref = str(message.get("conversation_ref") or "").strip()
    is_group = bool(metadata.get("is_group")) or conversation_ref.endswith("@g.us")
    candidates: list[object] = []
    if is_group:
        candidates.extend(
            [
                metadata.get("participant"),
                metadata.get("author"),
            ]
        )
    else:
        direction = str(message.get("direction") or "").strip().lower()
        candidates.extend(
            [conversation_ref]
        )
        if direction == "outbound":
            candidates.extend([metadata.get("to"), message.get("recipient")])
        else:
            candidates.extend([metadata.get("from"), message.get("sender")])
    phone_numbers: list[str] = []
    for candidate in candidates:
        digits = _extract_whatsapp_phone_number(candidate)
        if digits and digits not in phone_numbers:
            phone_numbers.append(digits)
    return phone_numbers


def _telegram_message_phone_numbers(message: dict[str, Any]) -> list[str]:
    metadata = dict(message.get("metadata") or {})
    phone_numbers: list[str] = []
    for candidate in [
        metadata.get("phone_number"),
        metadata.get("sender_phone"),
        metadata.get("recipient_phone"),
        metadata.get("contact_phone"),
        metadata.get("user_phone"),
    ]:
        digits = _extract_telegram_phone_number(candidate)
        if digits and digits not in phone_numbers:
            phone_numbers.append(digits)
    return phone_numbers


def _sanitize_contact_phone_numbers(phone_numbers: list[object] | None, candidates: list[object] | None = None) -> list[str]:
    resolved: list[str] = []
    for value in list(candidates or []) + list(phone_numbers or []):
        digits = _extract_whatsapp_phone_number(value)
        if digits and digits not in resolved:
            resolved.append(digits)
    return resolved


def _whatsapp_message_monitoring_decision(profile: dict[str, Any] | None, message: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(message.get("metadata") or {})
    group_label = _whatsapp_message_group_label(message)
    actor_label = _whatsapp_message_actor_label(message)
    actionable = bool(message.get("reply_needed"))
    return _build_monitoring_decision(
        profile,
        channel="whatsapp",
        actor_values=[
            actor_label,
            str(message.get("sender") or ""),
            str(message.get("recipient") or ""),
            str(metadata.get("profile_name") or ""),
            str(metadata.get("contact_name") or ""),
        ],
        group_values=[
            group_label,
            str(metadata.get("chat_name") or ""),
            str(metadata.get("group_name") or ""),
            str(message.get("conversation_ref") or ""),
        ],
        haystack_values=[
            actor_label,
            group_label,
            str(message.get("body") or ""),
            str(metadata.get("profile_name") or ""),
            str(metadata.get("contact_name") or ""),
        ],
        actionable=actionable,
        occurred_at=str(message.get("sent_at") or ""),
    )


def _telegram_message_group_label(message: dict[str, Any]) -> str:
    metadata = dict(message.get("metadata") or {})
    group_name = str(metadata.get("chat_title") or metadata.get("group_name") or metadata.get("chat_name") or "").strip()
    conversation_ref = str(message.get("conversation_ref") or "").strip()
    is_group = bool(metadata.get("is_group")) or conversation_ref.startswith("chat:")
    return group_name if is_group and group_name else ""


def _telegram_message_actor_label(message: dict[str, Any]) -> str:
    direction = str(message.get("direction") or "").strip().lower()
    sender = str(message.get("sender") or "").strip()
    recipient = str(message.get("recipient") or "").strip()
    if direction == "outbound":
        return recipient or sender or str(message.get("conversation_ref") or "Telegram")
    return sender or recipient or str(message.get("conversation_ref") or "Telegram")


def _telegram_message_monitoring_decision(profile: dict[str, Any] | None, message: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(message.get("metadata") or {})
    group_label = _telegram_message_group_label(message)
    actor_label = _telegram_message_actor_label(message)
    actionable = bool(message.get("reply_needed"))
    return _build_monitoring_decision(
        profile,
        channel="telegram",
        actor_values=[
            actor_label,
            str(message.get("sender") or ""),
            str(message.get("recipient") or ""),
            str(metadata.get("username") or ""),
            str(metadata.get("display_name") or ""),
        ],
        group_values=[
            group_label,
            str(message.get("conversation_ref") or ""),
            str(metadata.get("chat_title") or ""),
            str(metadata.get("group_name") or ""),
        ],
        haystack_values=[
            actor_label,
            group_label,
            str(message.get("body") or ""),
            str(metadata.get("username") or ""),
            str(metadata.get("display_name") or ""),
        ],
        actionable=actionable,
        occurred_at=str(message.get("sent_at") or ""),
    )


def _instagram_message_actor_label(message: dict[str, Any]) -> str:
    direction = str(message.get("direction") or "").strip().lower()
    sender = str(message.get("sender") or "").strip()
    recipient = str(message.get("recipient") or "").strip()
    if direction == "outbound":
        return recipient or sender or str(message.get("conversation_ref") or "Instagram")
    return sender or recipient or str(message.get("conversation_ref") or "Instagram")


def _instagram_message_monitoring_decision(profile: dict[str, Any] | None, message: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(message.get("metadata") or {})
    actor_label = _instagram_message_actor_label(message)
    actionable = bool(message.get("reply_needed"))
    return _build_monitoring_decision(
        profile,
        channel="instagram",
        actor_values=[
            actor_label,
            str(message.get("sender") or ""),
            str(message.get("recipient") or ""),
            str(metadata.get("username") or ""),
            str(metadata.get("display_name") or ""),
        ],
        group_values=[
            str(message.get("conversation_ref") or ""),
            str(metadata.get("thread_label") or ""),
        ],
        haystack_values=[
            actor_label,
            str(message.get("body") or ""),
            str(metadata.get("username") or ""),
            str(metadata.get("display_name") or ""),
        ],
        actionable=actionable,
        occurred_at=str(message.get("sent_at") or ""),
    )


def _linkedin_message_actor_label(message: dict[str, Any]) -> str:
    metadata = dict(message.get("metadata") or {})
    direction = str(message.get("direction") or "").strip().lower()
    sender = str(message.get("sender") or "").strip()
    recipient = str(message.get("recipient") or "").strip()
    chat_name = str(metadata.get("chat_name") or metadata.get("display_name") or "").strip()
    if direction == "outbound":
        return recipient or sender or chat_name or str(message.get("conversation_ref") or "LinkedIn")
    return sender or recipient or chat_name or str(message.get("conversation_ref") or "LinkedIn")


def _linkedin_message_monitoring_decision(profile: dict[str, Any] | None, message: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(message.get("metadata") or {})
    actor_label = _linkedin_message_actor_label(message)
    actionable = bool(message.get("reply_needed"))
    return _build_monitoring_decision(
        profile,
        channel="linkedin",
        actor_values=[
            actor_label,
            str(message.get("sender") or ""),
            str(message.get("recipient") or ""),
            str(metadata.get("display_name") or ""),
            str(metadata.get("chat_name") or ""),
        ],
        group_values=[
            str(message.get("conversation_ref") or ""),
            str(metadata.get("href") or ""),
        ],
        haystack_values=[
            actor_label,
            str(message.get("body") or ""),
            str(metadata.get("preview") or ""),
            str(metadata.get("display_name") or ""),
        ],
        actionable=actionable,
        occurred_at=str(message.get("sent_at") or ""),
    )


def _linkedin_actor_label(item: dict[str, Any]) -> str:
    metadata = dict(item.get("metadata") or {})
    return str(
        item.get("author_handle")
        or metadata.get("actor_name")
        or metadata.get("actor")
        or metadata.get("author")
        or "LinkedIn"
    ).strip()


def _linkedin_comment_inbox_item(comment: dict[str, Any]) -> dict[str, Any]:
    author = _linkedin_actor_label(comment)
    content = str(comment.get("content") or "").strip()
    metadata = dict(comment.get("metadata") or {})
    post_label = str(metadata.get("object_urn") or comment.get("object_urn") or "").strip()
    details = content or "Yanıt bekleyen LinkedIn yorumu."
    if post_label:
        details = f"{details} Hedef: {post_label}"
    return {
        "id": f"linkedin-comment-{comment['id']}",
        "kind": "reply_needed",
        "title": content or author,
        "details": details,
        "priority": "medium",
        "due_at": comment.get("posted_at"),
        "source_type": "linkedin_comment",
        "source_ref": comment.get("external_id"),
        "provider": "linkedin",
        "contact_label": author,
        "sender": author,
        "recipient": str(metadata.get("object_urn") or "").strip(),
        "direction": "inbound",
        "monitoring_reason": "LinkedIn gönderine gelen yorum",
        "monitoring_reason_kind": "integration",
        "memory_state": _channel_memory_state(comment),
        "matter_id": None,
        "manual_review_required": True,
        "recommended_action_ids": [],
    }


def _linkedin_post_inbox_item(post: dict[str, Any]) -> dict[str, Any]:
    author = _linkedin_actor_label(post)
    content = str(post.get("content") or "").strip()
    return {
        "id": f"linkedin-post-{post['id']}",
        "kind": "monitored_item",
        "title": content or author,
        "details": author if content else "LinkedIn gönderisi",
        "priority": "low",
        "due_at": post.get("posted_at"),
        "source_type": "linkedin_post",
        "source_ref": post.get("external_id"),
        "provider": "linkedin",
        "contact_label": author,
        "sender": author,
        "memory_state": _channel_memory_state(post),
        "matter_id": None,
        "manual_review_required": True,
        "recommended_action_ids": [],
    }


def _linkedin_message_inbox_item(message: dict[str, Any]) -> dict[str, Any]:
    contact_label = _linkedin_message_actor_label(message)
    body = str(message.get("body") or "").strip()
    metadata = dict(message.get("metadata") or {})
    return {
        "id": f"linkedin-message-{message['id']}",
        "kind": "reply_needed" if bool(message.get("reply_needed")) else "monitored_item",
        "title": body or contact_label,
        "details": contact_label if body else "Yanıt bekleyen LinkedIn mesajı.",
        "priority": "medium",
        "due_at": message.get("sent_at"),
        "source_type": "linkedin_message",
        "source_ref": message.get("message_ref"),
        "conversation_ref": message.get("conversation_ref"),
        "provider": "linkedin",
        "contact_label": contact_label,
        "sender": str(message.get("sender") or "").strip(),
        "recipient": str(message.get("recipient") or "").strip(),
        "direction": str(message.get("direction") or "").strip(),
        "href": str(metadata.get("href") or "").strip(),
        "memory_state": _channel_memory_state(message),
        "matter_id": None,
        "manual_review_required": True,
        "recommended_action_ids": [],
    }


def _monitoring_details(details: str, decision: dict[str, Any]) -> str:
    reason_text = str(decision.get("reason_text") or "").strip()
    if not reason_text:
        return str(details or "").strip()
    return _merge_importance_details(details, reason_text)


def _draft_review_title(draft: dict[str, Any]) -> str:
    subject = str(draft.get("subject") or "").strip()
    if subject:
        return f"Taslağı gözden geçir: {subject}"
    draft_type = str(draft.get("draft_type") or "taslak").replace("_", " ").strip()
    return f"{draft_type.title()} taslağını gözden geçir"


def _draft_review_details(draft: dict[str, Any]) -> str:
    channel = str(draft.get("channel") or "iletişim").strip()
    to_contact = str(draft.get("to_contact") or "").strip()
    target = f" {to_contact} için" if to_contact else ""
    approval_status = str(draft.get("approval_status") or "pending_review").strip().lower()
    status_text = "onay bekliyor" if approval_status != "approved" else "hazır"
    return f"{channel.title()}{target} hazırlanan taslak {status_text}."


def _build_today_communication_tasks(inbox: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    selected_by_thread: dict[str, dict[str, Any]] = {}
    allowed_reason_kinds = {"watch_person", "watch_group", "keyword"}

    def _priority_rank(value: str | None) -> int:
        return {"high": 0, "medium": 1, "low": 2}.get(str(value or "medium"), 1)

    def _communication_key(item: dict[str, Any]) -> str:
        source_type = str(item.get("source_type") or "").strip().lower()
        if source_type in {"email_thread", "x_post", "linkedin_comment", "linkedin_post"}:
            return f"{source_type}:{str(item.get('source_ref') or item.get('id') or '').strip()}"
        if source_type in {"whatsapp_message", "telegram_message", "x_message", "instagram_message", "linkedin_message"}:
            conversation_ref = str(item.get("conversation_ref") or "").strip()
            if conversation_ref:
                return f"{source_type}:{conversation_ref}"
            return f"{source_type}:{_text_haystack(item.get('contact_label'), item.get('sender'), item.get('recipient'))}"
        return f"{source_type}:{str(item.get('source_ref') or item.get('id') or '').strip()}"

    def _prefer_candidate(candidate: dict[str, Any], current: dict[str, Any] | None) -> bool:
        if current is None:
            return True
        candidate_due = _parse_dt(candidate.get("due_at"))
        current_due = _parse_dt(current.get("due_at"))
        if candidate_due and current_due and candidate_due != current_due:
            return candidate_due > current_due
        if candidate_due and not current_due:
            return True
        if current_due and not candidate_due:
            return False
        candidate_priority = _priority_rank(candidate.get("priority"))
        current_priority = _priority_rank(current.get("priority"))
        if candidate_priority != current_priority:
            return candidate_priority < current_priority
        return str(candidate.get("id") or "") > str(current.get("id") or "")

    for item in inbox:
        kind = str(item.get("kind") or "").strip()
        if kind in {"social_alert", "social_watch"}:
            tasks.append(item)
            continue
        if kind not in {"reply_needed", "monitored_item"}:
            continue
        if str(item.get("monitoring_reason_kind") or "").strip() not in allowed_reason_kinds:
            continue
        if not _is_recent_today_signal(
            item.get("due_at"),
            max_age_hours=ACTIONABLE_COMMUNICATION_SUMMARY_MAX_AGE_HOURS,
        ) and not str(item.get("importance_reason") or "").strip():
            continue
        channel = _channel_label(item)
        contact_label = _reply_contact_label(item)
        subject_label = _reply_subject_label(item)
        age_label = _relative_due_label(item.get("due_at"))
        source_type = str(item.get("source_type") or "").strip().lower()
        if source_type == "email_thread" and kind == "reply_needed":
            title = f"{channel}: {contact_label} için yanıt hazırla"
            details = f"{subject_label} başlıklı ileti {age_label} yanıt bekliyor. Kısa ve profesyonel e-posta dönüşü hazırlanmalı."
        elif source_type == "email_thread":
            title = f"{channel}: {contact_label} iletisini kontrol et"
            details = f"{subject_label} başlıklı ileti {age_label} izleme kurallarına takıldı. İçeriği gözden geçirmek faydalı olabilir."
        elif source_type == "telegram_message" and kind == "reply_needed":
            title = f"Telegram: {contact_label} için mesaj hazırla"
            details = f"{contact_label} ile konuşma {age_label} yanıt bekliyor. Kısa ve net Telegram cevabı hazırlanmalı."
        elif source_type == "telegram_message":
            title = f"Telegram: {contact_label} konuşmasını kontrol et"
            details = f"{contact_label} ile konuşma {age_label} izleme kurallarına takıldı. İçeriği gözden geçirmek faydalı olabilir."
        elif source_type == "whatsapp_message" and kind == "reply_needed":
            title = f"WhatsApp: {contact_label} için mesaj hazırla"
            details = f"{contact_label} ile konuşma {age_label} yanıt bekliyor. Kısa ve net WhatsApp cevabı hazırlanmalı."
        elif source_type == "whatsapp_message":
            title = f"WhatsApp: {contact_label} konuşmasını kontrol et"
            details = f"{contact_label} ile konuşma {age_label} izleme kurallarına takıldı. İçeriği gözden geçirmek faydalı olabilir."
        elif source_type == "x_message" and kind == "reply_needed":
            title = f"X DM: {contact_label} için yanıt hazırla"
            details = f"{contact_label} ile X DM konuşması {age_label} yanıt bekliyor. Kısa ve profesyonel direkt mesaj hazırlanmalı."
        elif source_type == "x_message":
            title = f"X DM: {contact_label} konuşmasını kontrol et"
            details = f"{contact_label} ile X DM konuşması {age_label} izleme kurallarına takıldı. İçeriği gözden geçirmek faydalı olabilir."
        elif source_type == "instagram_message" and kind == "reply_needed":
            title = f"Instagram: {contact_label} için yanıt hazırla"
            details = f"{contact_label} ile Instagram DM konuşması {age_label} yanıt bekliyor. Kısa ve doğal bir yanıt hazırlanmalı."
        elif source_type == "instagram_message":
            title = f"Instagram: {contact_label} konuşmasını kontrol et"
            details = f"{contact_label} ile Instagram DM konuşması {age_label} izleme kurallarına takıldı. İçeriği gözden geçirmek faydalı olabilir."
        elif source_type == "linkedin_message" and kind == "reply_needed":
            title = f"LinkedIn: {contact_label} için mesaj hazırla"
            details = f"{contact_label} ile LinkedIn DM konuşması {age_label} yanıt bekliyor. Kısa ve profesyonel bir yanıt hazırlanmalı."
        elif source_type == "linkedin_message":
            title = f"LinkedIn: {contact_label} konuşmasını kontrol et"
            details = f"{contact_label} ile LinkedIn DM konuşması {age_label} izleme kurallarına takıldı. İçeriği gözden geçirmek faydalı olabilir."
        elif source_type == "x_post":
            title = f"X: {contact_label} için yanıtı gözden geçir"
            details = f"{contact_label} tarafından gelen X iletisi {age_label} yanıt bekliyor. Kontrollü bir dönüş gerekip gerekmediğini netleştir."
        elif source_type == "linkedin_comment":
            title = f"LinkedIn: {contact_label} için yorum yanıtı hazırla"
            details = f"{contact_label} tarafından bırakılan LinkedIn yorumu {age_label} yanıt bekliyor. Kısa ve profesyonel bir yanıt hazırlanmalı."
        else:
            if kind == "reply_needed":
                title = f"{contact_label} için dönüş hazırla"
                details = f"{channel} üzerinden gelen ileti {age_label} yanıt bekliyor."
            else:
                title = f"{contact_label} kaydını kontrol et"
                details = f"{channel} üzerinden gelen ileti {age_label} izleme kurallarına takıldı."
        task = {
            "id": f"todo-{item['id']}",
            "kind": "communication_follow_up",
            "title": title,
            "details": details,
            "priority": "high" if str(item.get("priority") or "") == "high" else "medium",
            "due_at": item.get("due_at"),
            "source_type": item.get("source_type") or "assistant",
            "source_ref": item.get("source_ref"),
            "conversation_ref": item.get("conversation_ref"),
            "matter_id": item.get("matter_id"),
            "provider": item.get("provider"),
            "contact_label": item.get("contact_label"),
            "thread_subject": item.get("thread_subject"),
            "sender": item.get("sender"),
            "recipient": item.get("recipient"),
            "importance_reason": item.get("importance_reason"),
            "recommended_action_ids": list(item.get("recommended_action_ids") or []),
            "manual_review_required": True,
        }
        task_key = _communication_key(task)
        current = selected_by_thread.get(task_key)
        if _prefer_candidate(task, current):
            selected_by_thread[task_key] = task
    tasks.extend(
        sorted(
            selected_by_thread.values(),
            key=lambda item: (
                _priority_rank(item.get("priority")),
                str(item.get("due_at") or ""),
                str(item.get("title") or ""),
            ),
        )
    )
    return tasks


def _important_contact_reason(*values: object) -> str:
    haystack = " ".join(str(value or "").strip() for value in values).lower()
    if not haystack:
        return ""
    rules = [
        ("ceo", "CEO rolü geçtiği için öncelikli inceleme önerilir."),
        ("chief executive", "Üst yönetim sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("cfo", "Finans karar vericisi sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("cto", "Teknoloji lideri sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("coo", "Operasyon lideri sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("kurucu", "Kurucu / yönetici profili sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("founder", "Kurucu profili sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("genel müdür", "Üst yönetim sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("managing partner", "Ortak / yönetici rolü geçtiği için öncelikli inceleme önerilir."),
        ("partner", "Ortak / yönetici rolü geçtiği için öncelikli inceleme önerilir."),
        ("finans", "Finans tarafını ilgilendirdiği için öncelikli inceleme önerilir."),
        ("finance", "Finans tarafını ilgilendirdiği için öncelikli inceleme önerilir."),
        ("yatırımcı", "Yatırımcı ilişkisi sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("investor", "Yatırımcı ilişkisi sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("board", "Yönetim kurulu sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("müvekkil", "Müvekkil sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("muvekkil", "Müvekkil sinyali taşıdığı için öncelikli inceleme önerilir."),
        ("client", "Müvekkil / müşteri sinyali taşıdığı için öncelikli inceleme önerilir."),
    ]
    for needle, reason in rules:
        if needle in haystack:
            return reason
    return ""


def _merge_importance_details(details: str, importance_reason: str) -> str:
    base = str(details or "").strip()
    reason = str(importance_reason or "").strip()
    if not reason:
        return base
    if not base:
        return reason
    return f"{reason} {base}".strip()


def _social_item_details(signal: dict[str, Any], content: str) -> str:
    parts = [str(signal.get("summary") or "").strip()]
    evidence_note = str(signal.get("evidence_note") or "").strip()
    excerpt = str(content or "").strip()
    if evidence_note:
        parts.append(evidence_note)
    if excerpt:
        trimmed_excerpt = excerpt[:220] + ("…" if len(excerpt) > 220 else "")
        parts.append(f"İçerik: {trimmed_excerpt}")
    return " ".join(part for part in parts if part)


def _social_item_priority(signal: dict[str, Any]) -> str:
    severity = str(signal.get("severity") or "").lower()
    if severity in {"critical", "high"}:
        return "high"
    if severity == "medium":
        return "medium"
    return "low"


CHANNEL_PROFILE_MEMORY_STATES = {"candidate_memory", "approved_memory"}


def _channel_memory_state(item: dict[str, Any] | None) -> str:
    payload = dict(item or {})
    metadata = payload.get("metadata")
    metadata_obj = metadata if isinstance(metadata, dict) else {}
    state = str(payload.get("memory_state") or metadata_obj.get("memory_state") or "").strip().lower()
    if state in {"candidate_memory", "approved_memory"}:
        return state
    return "operational_only"


def _channel_profile_memory_eligible(item: dict[str, Any] | None) -> bool:
    return _channel_memory_state(item) in CHANNEL_PROFILE_MEMORY_STATES


def _x_post_inbox_item(post: dict[str, Any]) -> dict[str, Any]:
    signal = social_signal_from_metadata("x", str(post.get("author_handle") or ""), str(post.get("content") or ""), post.get("metadata") or {})
    author_handle = str(post.get("author_handle") or "X mention").strip()
    content = str(post.get("content") or "").strip()
    if signal.get("legal_signal") or signal.get("notify_user") or signal.get("evidence_candidate"):
        return {
            "id": f"x-alert-{post['id']}",
            "kind": "social_alert",
            "title": f"{author_handle} için sosyal risk uyarısı",
            "details": _social_item_details(signal, content),
            "priority": _social_item_priority(signal),
            "due_at": post.get("posted_at"),
            "source_type": "x_post",
            "source_ref": post.get("external_id"),
            "provider": "x",
            "contact_label": author_handle,
            "memory_state": _channel_memory_state(post),
            "matter_id": None,
            "manual_review_required": True,
            "recommended_action_ids": [],
        }
    if signal.get("category") == "complaint":
        return {
            "id": f"x-watch-{post['id']}",
            "kind": "social_watch",
            "title": f"{author_handle} için sosyal izleme",
            "details": _social_item_details(signal, content),
            "priority": _social_item_priority(signal),
            "due_at": post.get("posted_at"),
            "source_type": "x_post",
            "source_ref": post.get("external_id"),
            "provider": "x",
            "contact_label": author_handle,
            "memory_state": _channel_memory_state(post),
            "matter_id": None,
            "manual_review_required": True,
            "recommended_action_ids": [],
        }
    return {
        "id": f"x-{post['id']}",
        "kind": "reply_needed",
        "title": author_handle,
        "details": content or "Yanıt bekleyen X mention.",
        "priority": "medium",
        "due_at": post.get("posted_at"),
        "source_type": "x_post",
        "source_ref": post.get("external_id"),
        "provider": "x",
        "contact_label": author_handle,
        "memory_state": _channel_memory_state(post),
        "matter_id": None,
        "manual_review_required": True,
        "recommended_action_ids": [],
    }


def _x_message_inbox_item(message: dict[str, Any]) -> dict[str, Any]:
    contact_label = str(message.get("sender") or message.get("recipient") or message.get("conversation_ref") or "X DM").strip()
    body = str(message.get("body") or "").strip()
    metadata = dict(message.get("metadata") or {})
    return {
        "id": f"x-message-{message['id']}",
        "kind": "reply_needed",
        "title": body or contact_label,
        "details": contact_label if body else "Yanıt bekleyen X direkt mesajı.",
        "priority": "medium",
        "due_at": message.get("sent_at"),
        "source_type": "x_message",
        "source_ref": message.get("message_ref"),
        "provider": "x",
        "contact_label": contact_label,
        "sender": str(message.get("sender") or "").strip(),
        "recipient": str(message.get("recipient") or "").strip(),
        "direction": str(message.get("direction") or "").strip(),
        "participant_id": str(metadata.get("participant_id") or metadata.get("recipient_id") or "").strip(),
        "memory_state": _channel_memory_state(message),
        "matter_id": None,
        "manual_review_required": True,
        "recommended_action_ids": [],
    }


def _social_event_inbox_item(event: dict[str, Any]) -> dict[str, Any] | None:
    signal = social_signal_from_metadata(str(event.get("source") or ""), str(event.get("handle") or ""), str(event.get("content") or ""), event.get("metadata") or {})
    if not (signal.get("notify_user") or signal.get("evidence_candidate") or signal.get("category") == "complaint"):
        return None
    kind = "social_alert" if signal.get("legal_signal") or signal.get("evidence_candidate") else "social_watch"
    source = str(event.get("source") or "social").upper()
    handle = str(event.get("handle") or "Sosyal kanal").strip()
    return {
        "id": f"social-event-{event['id']}",
        "kind": kind,
        "title": f"{source}: {handle}",
        "details": _social_item_details(signal, str(event.get("content") or "")),
        "priority": _social_item_priority(signal),
        "due_at": event.get("created_at"),
        "source_type": "social_event",
        "source_ref": str(event.get("id") or ""),
        "matter_id": None,
        "manual_review_required": True,
        "recommended_action_ids": [],
    }


def build_social_monitoring_snapshot(store, office_id: str, *, limit: int = 10) -> dict[str, Any]:
    mentions = store.list_x_posts(office_id, post_type="mention", limit=limit)
    replies = store.list_x_posts(office_id, post_type="reply", limit=limit)
    posts = store.list_x_posts(office_id, post_type="post", limit=limit)
    linkedin_posts = store.list_linkedin_posts(office_id, limit=limit)
    linkedin_comments = store.list_linkedin_comments(office_id, limit=limit)
    events = store.list_social_events(limit=limit, office_id=office_id)
    items: list[dict[str, Any]] = []

    for post in [*mentions, *replies]:
        signal = social_signal_from_metadata("x", str(post.get("author_handle") or ""), str(post.get("content") or ""), post.get("metadata") or {})
        items.append(
            {
                "channel": "x",
                "handle": str(post.get("author_handle") or "").strip(),
                "content": str(post.get("content") or "").strip(),
                "posted_at": post.get("posted_at") or post.get("updated_at"),
                "source_ref": post.get("external_id"),
                **signal,
            }
        )

    for event in events:
        signal = social_signal_from_metadata(str(event.get("source") or ""), str(event.get("handle") or ""), str(event.get("content") or ""), event.get("metadata") or {})
        items.append(
            {
                "channel": str(event.get("source") or "social").strip().lower() or "social",
                "handle": str(event.get("handle") or "").strip(),
                "content": str(event.get("content") or "").strip(),
                "posted_at": event.get("created_at"),
                "source_ref": str(event.get("id") or ""),
                **signal,
            }
        )

    for post in linkedin_posts:
        signal = social_signal_from_metadata("linkedin", _linkedin_actor_label(post), str(post.get("content") or ""), post.get("metadata") or {})
        items.append(
            {
                "channel": "linkedin",
                "handle": _linkedin_actor_label(post),
                "content": str(post.get("content") or "").strip(),
                "posted_at": post.get("posted_at") or post.get("updated_at"),
                "source_ref": post.get("external_id"),
                **signal,
            }
        )

    for comment in linkedin_comments:
        signal = social_signal_from_metadata("linkedin", _linkedin_actor_label(comment), str(comment.get("content") or ""), comment.get("metadata") or {})
        items.append(
            {
                "channel": "linkedin",
                "handle": _linkedin_actor_label(comment),
                "content": str(comment.get("content") or "").strip(),
                "posted_at": comment.get("posted_at") or comment.get("updated_at"),
                "source_ref": comment.get("external_id"),
                **signal,
            }
        )

    items.sort(key=lambda item: str(item.get("posted_at") or ""), reverse=True)
    alerts = [
        item
        for item in items
        if item.get("legal_signal") or item.get("notify_user") or item.get("evidence_candidate")
    ]
    return {
        "counts": {
            "mentions": len(mentions),
            "replies": len(replies),
            "posts": len(posts),
            "linkedin_posts": len(linkedin_posts),
            "linkedin_comments": len(linkedin_comments),
            "alerts": len(alerts),
            "events": len(events),
        },
        "alerts": alerts[:5],
        "recent_items": items[:limit],
    }


def _find_calendar_gap(items: list[dict[str, Any]], *, window_days: int = 14, minimum_hours: int = 4) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    grouped: dict[date, list[tuple[datetime, datetime]]] = {}

    for item in items:
        starts_at = _parse_dt(item.get("starts_at"))
        if not starts_at:
            continue
        ends_at = _parse_dt(item.get("ends_at")) or (starts_at + timedelta(hours=1))
        grouped.setdefault(starts_at.date(), []).append((starts_at, ends_at))

    for offset in range(0, max(1, window_days) + 1):
        current_day = (now + timedelta(days=offset)).date()
        business_start = datetime.combine(current_day, datetime.min.time(), tzinfo=timezone.utc).replace(hour=9)
        business_end = datetime.combine(current_day, datetime.min.time(), tzinfo=timezone.utc).replace(hour=20)
        cursor = max(now + timedelta(minutes=30), business_start) if current_day == now.date() else business_start
        blocks = sorted(grouped.get(current_day, []), key=lambda item: item[0])

        if not blocks and (business_end - cursor) >= timedelta(hours=minimum_hours):
            return {
                "day": current_day.isoformat(),
                "label": _format_turkish_day_label(current_day),
                "starts_at": cursor.isoformat(),
                "ends_at": business_end.isoformat(),
                "time_window": _format_time_window(cursor, business_end),
            }

        for starts_at, ends_at in blocks:
            normalized_start = max(starts_at, business_start)
            normalized_end = min(ends_at, business_end)
            if normalized_end <= cursor:
                continue
            if normalized_start > cursor and (normalized_start - cursor) >= timedelta(hours=minimum_hours):
                return {
                    "day": current_day.isoformat(),
                    "label": _format_turkish_day_label(current_day),
                    "starts_at": cursor.isoformat(),
                    "ends_at": normalized_start.isoformat(),
                    "time_window": _format_time_window(cursor, normalized_start),
                }
            cursor = max(cursor, normalized_end)

        if business_end > cursor and (business_end - cursor) >= timedelta(hours=minimum_hours):
            return {
                "day": current_day.isoformat(),
                "label": _format_turkish_day_label(current_day),
                "starts_at": cursor.isoformat(),
                "ends_at": business_end.isoformat(),
                "time_window": _format_time_window(cursor, business_end),
            }
    return None


def _build_proactive_suggestions(
    store,
    office_id: str,
    *,
    profile: dict[str, Any],
    inbox: list[dict[str, Any]],
    calendar: list[dict[str, Any]],
    relationship_profiles: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    display_name = _profile_display_name(profile) or "orada"
    preference_text = _profile_preference_text(profile)
    location_label = _profile_location_label(profile)
    location_preferences = str(profile.get("location_preferences") or "").strip()
    prayer_habit_notes = str(profile.get("prayer_habit_notes") or "").strip()
    prayer_notifications_enabled = bool(profile.get("prayer_notifications_enabled"))
    selected_relationship_profiles = list(relationship_profiles or [])
    likes_train = "tren" in preference_text
    likes_sea = any(token in preference_text for token in ["deniz", "sahil", "kıyı", "kiyi", "tekne"])
    social_alert = next((item for item in inbox if str(item.get("kind") or "") == "social_alert"), None)
    weather_event = _select_upcoming_weather_event(calendar, current_location=location_label, now=now)

    if weather_event:
        suggestion = _calendar_weather_suggestion(profile, weather_event, now=now)
        if suggestion:
            suggestions.append(suggestion)

    if location_label and (not weather_event or not _same_location_context(weather_event.get("location"), location_label)):
        suggestion = _current_location_weather_suggestion(profile, now=now)
        if suggestion:
            suggestions.append(suggestion)

    if social_alert:
        title = str(social_alert.get("title") or "Sosyal risk uyarısı").strip()
        details = str(social_alert.get("details") or "").strip()
        suggestions.append(
            {
                "id": f"proactive-social-{social_alert['id']}",
                "kind": "social_alert",
                "title": "Sosyal içeriği delil ve risk yönünden değerlendirelim",
                "details": (
                    f"{title} öne çıktı. {details} "
                    "İstersen önce delil olarak nasıl saklanacağını, sonra kontrollü yanıt gerekip gerekmediğini netleştireyim."
                ).strip(),
                "action_label": "Sosyal riski değerlendir",
                "prompt": (
                    f"{title} için hukukî risk değerlendirmesi yap. "
                    "İçeriği delil olarak saklamak için hangi bağlantı, ekran görüntüsü ve zaman bilgisini tutmamız gerektiğini açıkla. "
                    "Varsa yanıt verilip verilmemesi konusunda kısa öneri çıkar."
                ),
                "tool": "today",
                "priority": "high",
            }
        )

    for item in calendar:
        starts_at = _parse_dt(item.get("starts_at"))
        matter_id = item.get("matter_id")
        if not starts_at or not matter_id:
            continue
        if starts_at < now or starts_at > now + timedelta(days=3):
            continue
        matter = store.get_matter(int(matter_id), office_id)
        matter_title = str(matter.get("title") or item.get("title") or "dosya")
        event_title = str(item.get("title") or "takvim kaydı")
        day_label = _format_turkish_day_label(starts_at)
        suggestions.append(
            {
                "id": f"proactive-client-update-{item['id']}",
                "kind": "draft_client_update",
                "title": f"{event_title} için müvekkil teyidi hazırlanabilir",
                "details": f"{day_label} planlı {event_title} için müvekkile kısa bir teyit e-postası taslağı hazırlayabilirim.",
                "action_label": "Taslak hazırla",
                "prompt": f"E-posta hazırla: {matter_title} için {day_label} tarihli {event_title} öncesi müvekkile kısa teyit mesajı oluştur.",
                "matter_id": int(matter_id),
                "tool": "drafts",
                "priority": "high",
            }
        )
        location = str(item.get("location") or "").strip()
        transport_preference = str(profile.get("transport_preference") or "").strip()
        if location:
            route_details = (
                f"{day_label} planlı {event_title} için konum olarak {location} görünüyor. "
                + (
                    f"{transport_preference} notunu da dikkate alarak rota ve çıkış zamanı planlayabilirim."
                    if transport_preference
                    else "İstersen çıkış saati ve rota planını birlikte netleştirebiliriz."
                )
            )
            suggestions.append(
                {
                    "id": f"proactive-route-{item['id']}",
                    "kind": "route_planning",
                    "title": f"{event_title} için rota planını hazırlayalım",
                    "details": route_details,
                    "action_label": "Rota planla",
                    "prompt": (
                        f"{event_title} için {location} konumuna gidişi planla. "
                        "Önce eksik olan çıkış noktası veya saat bilgisini netleştir. "
                        "Ardından kullanıcının ulaşım tercihlerini dikkate alarak kısa rota seçenekleri öner."
                    ),
                    "matter_id": int(matter_id),
                    "tool": "calendar",
                    "priority": "medium",
                }
            )
        break

    gap = _find_calendar_gap(calendar, window_days=14, minimum_hours=4)
    if gap and (likes_train or likes_sea or str(profile.get("travel_preferences") or "").strip()):
        preference_parts: list[str] = []
        if likes_sea:
            preference_parts.append("deniz kenarı")
        if likes_train:
            preference_parts.append("tren yolculuğu")
        preference_label = " ve ".join(preference_parts) if preference_parts else "seyahat tercihlerin"
        gap_key = f"{gap['label']}-{gap['time_window']}".lower().replace(" ", "-").replace(":", "")
        suggestions.append(
            {
                "id": f"proactive-travel-gap-{gap_key}",
                "kind": "travel_gap",
                "title": f"{gap['label']} boşluğunu birlikte netleştirelim",
                "details": (
                    f"{display_name}, takviminde {gap['time_window']} arasında uygun bir boşluk görünüyor. "
                    f"{preference_label} sevdiğini not ettim. İstersen önce bu boşluğu nasıl değerlendirmek istediğini birlikte netleştirelim, "
                    "sonra sana uygun rota veya bilet bakarım."
                ),
                "action_label": "Bu planı konuşalım",
                "prompt": (
                    f"{gap['label']} için biraz önce önerdiğin boşluğu benimle konuş. "
                    "Önce bunu neden önerdiğini açık ve kısa biçimde anlat. "
                    "Ardından bu boşluğu nasıl değerlendirmek istediğimi anlamak için gerekli soruları tek tek sor. "
                    "Henüz rota veya bilet önermeye başlama."
                ),
                "tool": "calendar",
                "priority": "medium",
            }
        )

    if location_label and location_preferences:
        discovery_query = f"{location_label} yakınında {location_preferences}"
        suggestions.append(
            {
                "id": f"proactive-nearby-discovery-{quote(location_label, safe='')[:32]}",
                "kind": "nearby_discovery",
                "title": f"{location_label} çevresinde sana uygun yerleri çıkarayım",
                "details": (
                    f"{display_name}, konum bağlamın {location_label} olarak kayıtlı. "
                    f"{location_preferences} tercihlerini dikkate alarak yakın çevre önerileri hazırlayabilirim."
                ),
                "action_label": "Yakın yerleri bul",
                "prompt": (
                    f"{location_label} yakınında kullanıcı tercihine uygun yerleri araştır. "
                    f"Öncelik: {location_preferences}. "
                    "Gerekirse bütçe, yürüyüş mesafesi ve ulaşım tercihini netleştir. "
                    "Sonra kısa aday listesi, neden uygun oldukları ve varsa harita yönlendirmesi öner."
                ),
                "tool": "places",
                "priority": "medium",
                "secondary_action_label": "Haritada aç",
                "secondary_action_url": _build_map_search_url(profile, discovery_query),
            }
        )

    if location_label and prayer_notifications_enabled:
        support_query = str(prayer_habit_notes or "özel rutin ve mekan tercihleri").strip() or "özel rutin ve mekan tercihleri"
        support_map_query = f"{location_label} {support_query}"
        prayer_details = (
            f"{display_name}, {location_label} çevresinde özel rutin veya mekan tercihlerin için yardımcı olabilirim."
        )
        if prayer_habit_notes:
            prayer_details = f"{prayer_details} Not: {prayer_habit_notes}"
        suggestions.append(
            {
                "id": f"proactive-prayer-{quote(location_label, safe='')[:32]}",
                "kind": "routine_support",
                "title": "Rutinine uygun yer ve zaman desteğini açalım",
                "details": prayer_details,
                "action_label": "Rutin desteğini aç",
                "prompt": (
                    f"{location_label} için kullanıcının şu özel rutin / mekan notunu dikkate al: {support_query}. "
                    "Önce konum bağlamının yeterli olup olmadığını kontrol et. "
                    "Sonra bu nota uygun zaman bilgisini, yakın seçenekleri ve isterse yol planı açabileceğini belirt."
                ),
                "tool": "places",
                "priority": "medium",
                "secondary_action_label": "Haritada aç",
                "secondary_action_url": _build_map_search_url(profile, support_map_query),
            }
        )

    upcoming_dates = _upcoming_profile_dates(store, office_id, window_days=10)
    related_upcoming = next((item for item in upcoming_dates if item.get("profile_type") == "related"), None)
    if related_upcoming:
        owner_name = str(related_upcoming.get("owner_name") or "yakınınız").strip()
        relationship = str(related_upcoming.get("relationship") or "").strip()
        label = str(related_upcoming.get("label") or "önemli tarih").strip()
        days_until = int(related_upcoming.get("days_until") or 0)
        date_label = _format_turkish_day_label(_parse_profile_date(str(related_upcoming.get("date") or "")))
        timing_text = "bugün" if days_until == 0 else "yarın" if days_until == 1 else f"{days_until} gün sonra"
        relationship_text = f"{relationship} " if relationship else ""
        suggestions.append(
            {
                "id": f"proactive-related-{related_upcoming['id']}",
                "kind": "family_preparation",
                "title": f"{owner_name} için hazırlık çıkarayım",
                "details": f"{relationship_text}{owner_name} ile ilgili {label} {date_label} tarihinde ({timing_text}). İstersen mesaj taslağı, hatırlatma ve kısa hazırlık listesi çıkarayım.",
                "action_label": "Hazırlığı çıkar",
                "prompt": f"{owner_name} için yaklaşan {label} konusunda kısa hazırlık listesi, takvim önerisi ve nazik mesaj taslağı hazırla.",
                "tool": "today",
                "priority": "high" if days_until <= 2 else "medium",
            }
        )

    for event in calendar:
        starts_at = _parse_dt(event.get("starts_at"))
        if not starts_at or starts_at < now or starts_at > now + timedelta(days=IMPORTANT_CONTACT_LOOKAHEAD_DAYS):
            continue
        matched_profile = next((item for item in selected_relationship_profiles if _contact_calendar_match(item, event)), None)
        if not matched_profile:
            continue
        preference_signals = [str(item).strip() for item in matched_profile.get("preference_signals") or [] if str(item).strip()]
        gift_ideas = [str(item).strip() for item in matched_profile.get("gift_ideas") or [] if str(item).strip()]
        if not preference_signals and not gift_ideas:
            continue
        contact_name = str(matched_profile.get("display_name") or "yakınınız").strip()
        relationship_hint = str(matched_profile.get("relationship_hint") or "").strip()
        event_title = str(event.get("title") or "buluşma").strip()
        day_label = _format_turkish_day_label(starts_at)
        hint_text = gift_ideas[0] if gift_ideas else preference_signals[0].rstrip(".")
        notes = [preference_signals[0]] if preference_signals else []
        if str(matched_profile.get("notes") or "").strip():
            notes.append(str(matched_profile.get("notes") or "").strip())
        suggestions.append(
            {
                "id": f"proactive-contact-{matched_profile['id']}-{event.get('id')}",
                "kind": "contact_preparation",
                "title": f"{contact_name} için küçük bir hazırlık notu çıkarayım",
                "details": (
                    f"{day_label} görünen {event_title} kaydında {relationship_hint.lower() + ' ' if relationship_hint else ''}{contact_name} ile eşleşen bir plan var. "
                    f"Profil sinyali: {notes[0] if notes else 'yakın çevre tercihi kayıtlı.'} "
                    f"İstersen {hint_text} düşünmeni de hazırlık listesine ekleyeyim."
                ).strip(),
                "action_label": "Hazırlık notu çıkar",
                "prompt": (
                    f"{contact_name} ile yaklaşan {event_title} buluşması için kısa hazırlık listesi oluştur. "
                    f"Şu profil sinyallerini dikkate al: {'; '.join(notes) if notes else 'yakın çevre tercihi kaydı var'}. "
                    "Nazik ve kısa öneriler üret; yalnızca düşük riskli pratik hazırlıklar öner."
                ),
                "tool": "calendar",
                "priority": "high" if starts_at <= now + timedelta(days=2) else "medium",
            }
        )
        break

    today_follow_ups = _build_today_communication_tasks(inbox)
    actionable_follow_ups = [item for item in today_follow_ups if str(item.get("kind") or "") == "communication_follow_up"]
    if actionable_follow_ups:
        first_item = actionable_follow_ups[0]
        channel = _channel_label(first_item)
        contact_label = _reply_contact_label(first_item)
        subject_label = _reply_subject_label(first_item)
        age_label = _relative_due_label(first_item.get("due_at"))
        provider = str(first_item.get("provider") or "").strip().lower()
        provider_hint = (
            " Outlook hesabında"
            if provider == "outlook"
            else " Gmail tarafında"
            if provider == "google"
            else ""
        )
        guidance_title = (
            f"{contact_label} için dönüşü hazırlayayım"
            if str(first_item.get("source_type") or "") != "x_post"
            else f"{contact_label} için kontrollü yanıt hazırlayayım"
        )
        guidance_prompt = (
            f"{channel} üzerinden gelen {subject_label} başlıklı iletiyi önceliklendir. "
            f"{contact_label} için kısa, profesyonel ve net bir yanıt taslağı hazırla. "
            "Önce yanıtın amacını tek cümlede söyle, sonra gönderime hazır metni çıkar."
        )
        suggestions.append(
            {
                "id": "proactive-inbox-review",
                "kind": "inbox_review",
                "title": guidance_title,
                "details": (
                    f"{channel}{provider_hint} üzerinden {contact_label} tarafından gelen "
                    f"{subject_label} {age_label} yanıt bekliyor. Hâlâ dönüş yapmadıysan önce bunu toparlayıp "
                    "istersen doğrudan göndermeye hazır bir taslak çıkarayım."
                ),
                "action_label": "Yanıt taslağını hazırla",
                "prompt": guidance_prompt,
                "tool": "drafts",
                "priority": "high" if str(first_item.get("priority") or "medium") == "high" else "medium",
            }
        )

    return suggestions[:7]


def build_assistant_onboarding(store, settings, office_id: str) -> dict[str, Any]:
    profile = store.get_user_profile(office_id)
    runtime_profile = store.get_assistant_runtime_profile(office_id)
    workspace_root = store.get_active_workspace_root(office_id)

    workspace_ready = bool(workspace_root)
    provider_ready = bool(settings.provider_configured and str(settings.provider_model or "").strip())
    assistant_ready = bool(
        str(runtime_profile.get("assistant_name") or "").strip()
        and (
            str(runtime_profile.get("soul_notes") or "").strip()
            or str(runtime_profile.get("tone") or "").strip() not in {"", DEFAULT_ASSISTANT_TONE}
            or str(runtime_profile.get("role_summary") or "").strip() not in {"", "Kaynak dayanaklı hukuk çalışma asistanı", DEFAULT_ASSISTANT_ROLE_SUMMARY}
        )
    )
    user_ready = bool(
        str(profile.get("display_name") or "").strip()
        and (
            str(profile.get("communication_style") or "").strip()
            or str(profile.get("assistant_notes") or "").strip()
        )
    )

    steps = [
        {
            "id": "workspace",
            "title": "Çalışma klasörünü bağlayın",
            "description": "Uygulama yalnız seçtiğiniz klasör ağacında çalışır.",
            "complete": workspace_ready,
            "action": "choose_workspace",
        },
        {
            "id": "provider",
            "title": "Sağlayıcı ve modeli seçin",
            "description": "Codex veya Gemini gibi sağlayıcıyı bağlayıp başlangıç modelini belirleyin.",
            "complete": provider_ready,
            "action": "connect_provider",
        },
        {
            "id": "assistant-persona",
            "title": "Asistanın kimliğini tanımlayın",
            "description": "Adı, üslubu ve kritik işlerde koruyacağı sınırları sohbetle netleştirin.",
            "complete": assistant_ready,
            "action": "open_assistant_chat",
        },
        {
            "id": "user-profile",
            "title": "Kullanıcı profilini başlatın",
            "description": "Hitap biçimi, cevap tercihi ve günlük destek alanlarını kısa tanışma ile toplayın.",
            "complete": user_ready,
            "action": "open_assistant_chat",
        },
    ]

    prompts: list[str] = []
    if not assistant_ready:
        prompts.extend(
            [
                "Önce bana nasıl seslenmemi istediğini netleştirelim.",
                "Kritik işlerde hangi sınırları korumamı istediğini söyle.",
            ]
        )
    if not user_ready:
        prompts.extend(
            [
                "Sana nasıl hitap etmemi istersin?",
                "Yanıtlarımın üslubunu birlikte ayarlayalım.",
                "Gün içinde en çok hangi işlerde destek olmamı istersin?",
            ]
        )

    return {
        "complete": all(bool(step["complete"]) for step in steps),
        "workspace_ready": workspace_ready,
        "provider_ready": provider_ready,
        "assistant_ready": assistant_ready,
        "user_ready": user_ready,
        "provider_type": settings.provider_type,
        "provider_model": settings.provider_model,
        "workspace_root_name": workspace_root.get("display_name") if workspace_root else None,
        "assistant_name": runtime_profile.get("assistant_name") or "",
        "display_name": profile.get("display_name") or "",
        "steps": steps,
        "suggested_prompts": prompts[:6],
        "generated_from": "assistant_onboarding_state",
    }


def build_assistant_inbox(store, office_id: str) -> list[dict[str, Any]]:
    profile = store.get_user_profile(office_id)
    items: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for thread in store.list_email_threads(office_id)[:80]:
        metadata = dict(thread.get("metadata") or {})
        decision = _email_thread_monitoring_decision(profile, thread)
        if not decision.get("include"):
            continue
        memory_state = _channel_memory_state(thread)
        participants = [str(item).strip() for item in thread.get("participants") or [] if str(item).strip()]
        sender = str(metadata.get("sender") or (participants[0] if participants else "")).strip()
        importance_reason = _important_contact_reason(
            sender,
            thread.get("subject"),
            thread.get("snippet"),
            metadata.get("sender_title"),
            metadata.get("sender_role"),
        )
        items.append(
            {
                "id": f"email-{thread['id']}",
                "kind": "reply_needed" if _is_actionable_email_thread(thread) else "monitored_item",
                "title": thread["subject"],
                "details": _monitoring_details(
                    _merge_importance_details(thread.get("snippet") or "Yanıt bekleyen e-posta zinciri.", importance_reason),
                    decision,
                ),
                "priority": "high" if importance_reason or decision.get("reason_kind") == "keyword" else "medium",
                "due_at": thread.get("received_at"),
                "source_type": "email_thread",
                "source_ref": thread.get("thread_ref"),
                "provider": thread.get("provider") or "email",
                "contact_label": sender or "e-posta göndereni",
                "thread_subject": thread.get("subject") or "",
                "sender": sender,
                "importance_reason": importance_reason,
                "monitoring_reason": decision.get("reason_text"),
                "monitoring_reason_kind": decision.get("reason_kind"),
                "monitoring_keyword": decision.get("matched_keyword"),
                "memory_state": memory_state,
                "unread_count": int(thread.get("unread_count") or 0),
                "matter_id": thread.get("matter_id"),
                "manual_review_required": True,
                "recommended_action_ids": [],
            }
        )
        if thread.get("thread_ref"):
            seen_refs.add(f"email:{thread['thread_ref']}")
    for message in store.list_whatsapp_messages(office_id, limit=80):
        metadata = dict(message.get("metadata") or {})
        conversation_ref = str(message.get("conversation_ref") or "").strip()
        group_label = _whatsapp_message_group_label(message)
        is_group = bool(metadata.get("is_group")) or conversation_ref.endswith("@g.us")
        actor_label = _whatsapp_message_actor_label(message)
        conversation_label = f"{group_label} > {actor_label}" if is_group and group_label and actor_label else actor_label
        body = message.get("body") or ""
        decision = _whatsapp_message_monitoring_decision(profile, message)
        if not decision.get("include"):
            continue
        memory_state = _channel_memory_state(message)
        importance_reason = _important_contact_reason(
            message.get("sender"),
            message.get("recipient"),
            body,
            metadata.get("profile_name"),
        )
        items.append(
            {
                "id": f"whatsapp-{message['id']}",
                "kind": "reply_needed" if bool(message.get("reply_needed")) else "monitored_item",
                "title": body or conversation_label,
                "details": _monitoring_details(
                    _merge_importance_details(conversation_label if body else "Yanıt bekleyen WhatsApp mesajı.", importance_reason),
                    decision,
                ),
                "priority": "high" if importance_reason or decision.get("reason_kind") == "keyword" else "medium",
                "due_at": message.get("sent_at"),
                "source_type": "whatsapp_message",
                "source_ref": message.get("message_ref"),
                "conversation_ref": conversation_ref,
                "provider": "whatsapp",
                "contact_label": conversation_label,
                "sender": str(message.get("sender") or "").strip(),
                "recipient": str(message.get("recipient") or "").strip(),
                "direction": str(message.get("direction") or "").strip(),
                "importance_reason": importance_reason,
                "monitoring_reason": decision.get("reason_text"),
                "monitoring_reason_kind": decision.get("reason_kind"),
                "monitoring_keyword": decision.get("matched_keyword"),
                "memory_state": memory_state,
                "matter_id": message.get("matter_id"),
                "manual_review_required": True,
                "recommended_action_ids": [],
            }
        )
        if message.get("message_ref"):
            seen_refs.add(f"whatsapp:{message['message_ref']}")
    for message in store.list_telegram_messages(office_id, limit=80):
        decision = _telegram_message_monitoring_decision(profile, message)
        if not decision.get("include"):
            continue
        memory_state = _channel_memory_state(message)
        conversation_label = message.get("sender") or message.get("recipient") or "Telegram konuşması"
        body = message.get("body") or ""
        items.append(
            {
                "id": f"telegram-{message['id']}",
                "kind": "reply_needed" if bool(message.get("reply_needed")) else "monitored_item",
                "title": body or conversation_label,
                "details": _monitoring_details(
                    conversation_label if body else "Yanıt bekleyen Telegram mesajı.",
                    decision,
                ),
                "priority": "high" if decision.get("reason_kind") == "keyword" else "medium",
                "due_at": message.get("sent_at"),
                "source_type": "telegram_message",
                "source_ref": message.get("message_ref"),
                "conversation_ref": message.get("conversation_ref"),
                "provider": "telegram",
                "contact_label": conversation_label,
                "sender": str(message.get("sender") or "").strip(),
                "recipient": str(message.get("recipient") or "").strip(),
                "direction": str(message.get("direction") or "").strip(),
                "monitoring_reason": decision.get("reason_text"),
                "monitoring_reason_kind": decision.get("reason_kind"),
                "monitoring_keyword": decision.get("matched_keyword"),
                "memory_state": memory_state,
                "matter_id": message.get("matter_id"),
                "manual_review_required": True,
                "recommended_action_ids": [],
            }
        )
        if message.get("message_ref"):
            seen_refs.add(f"telegram:{message['message_ref']}")
    for message in store.list_x_messages(office_id, reply_needed_only=True, limit=20):
        item = _x_message_inbox_item(message)
        item["conversation_ref"] = message.get("conversation_ref")
        items.append(item)
        if message.get("message_ref"):
            seen_refs.add(f"x-dm:{message['message_ref']}")
    for message in store.list_instagram_messages(office_id, limit=40):
        decision = _instagram_message_monitoring_decision(profile, message)
        if not decision.get("include"):
            continue
        memory_state = _channel_memory_state(message)
        contact_label = _instagram_message_actor_label(message)
        body = str(message.get("body") or "").strip()
        items.append(
            {
                "id": f"instagram-{message['id']}",
                "kind": "reply_needed" if bool(message.get("reply_needed")) else "monitored_item",
                "title": body or contact_label,
                "details": _monitoring_details(contact_label if body else "Yanıt bekleyen Instagram mesajı.", decision),
                "priority": "high" if decision.get("reason_kind") == "keyword" else "medium",
                "due_at": message.get("sent_at"),
                "source_type": "instagram_message",
                "source_ref": message.get("message_ref"),
                "conversation_ref": message.get("conversation_ref"),
                "provider": "instagram",
                "contact_label": contact_label,
                "sender": str(message.get("sender") or "").strip(),
                "recipient": str(message.get("recipient") or "").strip(),
                "direction": str(message.get("direction") or "").strip(),
                "participant_id": str(dict(message.get("metadata") or {}).get("participant_id") or "").strip(),
                "monitoring_reason": decision.get("reason_text"),
                "monitoring_reason_kind": decision.get("reason_kind"),
                "monitoring_keyword": decision.get("matched_keyword"),
                "memory_state": memory_state,
                "matter_id": None,
                "manual_review_required": True,
                "recommended_action_ids": [],
            }
        )
        if message.get("message_ref"):
            seen_refs.add(f"instagram:{message['message_ref']}")
    for message in store.list_linkedin_messages(office_id, limit=40):
        decision = _linkedin_message_monitoring_decision(profile, message)
        if not decision.get("include"):
            continue
        item = _linkedin_message_inbox_item(message)
        item["details"] = _monitoring_details(
            item["details"],
            decision,
        )
        item["priority"] = "high" if decision.get("reason_kind") == "keyword" else item.get("priority") or "medium"
        item["monitoring_reason"] = decision.get("reason_text")
        item["monitoring_reason_kind"] = decision.get("reason_kind")
        item["monitoring_keyword"] = decision.get("matched_keyword")
        items.append(item)
        if message.get("message_ref"):
            seen_refs.add(f"linkedin-message:{message['message_ref']}")
    for comment in store.list_linkedin_comments(office_id, reply_needed_only=True, limit=20):
        items.append(_linkedin_comment_inbox_item(comment))
        if comment.get("external_id"):
            seen_refs.add(f"linkedin-comment:{comment['external_id']}")
    for post in store.list_linkedin_posts(office_id, limit=12):
        items.append(_linkedin_post_inbox_item(post))
        if post.get("external_id"):
            seen_refs.add(f"linkedin-post:{post['external_id']}")
    for post_type in ("mention", "reply"):
        for post in store.list_x_posts(office_id, post_type=post_type, reply_needed_only=True, limit=20):
            items.append(_x_post_inbox_item(post))
            if post.get("external_id"):
                seen_refs.add(f"x:{post['external_id']}")
    for event in store.list_social_events(limit=20, office_id=office_id):
        external_id = str(dict(event.get("metadata") or {}).get("external_id") or "").strip()
        source = str(event.get("source") or "social").strip().lower() or "social"
        if external_id and f"{source}:{external_id}" in seen_refs:
            continue
        item = _social_event_inbox_item(event)
        if item:
            items.append(item)
    return items


def _append_unique_strings(target: list[str], values: list[str]) -> None:
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in target:
            target.append(cleaned)


def _communication_profile_id(kind: str, label: str) -> str:
    normalized = _normalize_monitor_text(label).replace(" ", "-")
    return f"{kind}:{normalized or 'profile'}"


def _related_profile_lookup(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for item in _related_profiles(profile):
        name = _normalize_monitor_text(item.get("name"))
        if name:
            items[name] = item
    return items


def _contact_profile_override_lookup(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for raw in profile.get("contact_profile_overrides") or []:
        if not isinstance(raw, dict):
            continue
        contact_id = str(raw.get("contact_id") or "").strip()
        description = str(raw.get("description") or "").strip()
        if not contact_id or not description:
            continue
        lookup[contact_id] = {
            "contact_id": contact_id,
            "description": description,
            "updated_at": str(raw.get("updated_at") or "").strip() or None,
        }
    return lookup


def _related_profile_for_display(profile: dict[str, Any], display_name: str) -> dict[str, Any] | None:
    display_key = _normalize_monitor_text(display_name)
    if not display_key:
        return None
    lookup = _related_profile_lookup(profile)
    return lookup.get(display_key)


def _relationship_hint_from_candidates(candidates: list[str]) -> str:
    haystack = " ".join(_normalize_monitor_text(item) for item in candidates if _normalize_monitor_text(item))
    if not haystack:
        return ""
    for label, keywords in RELATIONSHIP_KEYWORD_HINTS:
        if any(keyword in haystack for keyword in keywords):
            return label
    return ""


def _exact_relationship_alias(value: object) -> str:
    normalized = _normalize_monitor_text(value)
    if not normalized:
        return ""
    for label, keywords in RELATIONSHIP_KEYWORD_HINTS:
        if any(normalized == _normalize_monitor_text(keyword) for keyword in keywords):
            return label
    return ""


def _contact_domain_hints(values: list[str]) -> list[str]:
    hints: list[str] = []
    for value in values:
        candidate = str(value or "").strip().lower()
        if "@" in candidate:
            candidate = candidate.split("@", 1)[1]
        candidate = candidate.replace("mailto:", "").strip(". ")
        if not candidate:
            continue
        parts = [part for part in re.split(r"[^a-z0-9]+", candidate) if part]
        if len(parts) >= 2 and parts[-1] in {"com", "net", "org", "co", "io", "ai", "gov", "edu", "tr"}:
            parts = parts[:-1]
        if parts and parts[-1] in {"com", "net", "org", "co", "io", "ai", "gov", "edu", "tr"}:
            parts = parts[:-1]
        if parts:
            hint = parts[-1]
            if hint and hint not in hints:
                hints.append(hint)
    return hints


def _contact_role_inference(
    *,
    display_name: str,
    emails: list[str] | None = None,
    handles: list[str] | None = None,
    candidates: list[str] | None = None,
    samples: list[dict[str, Any]] | None = None,
) -> tuple[str, str] | tuple[None, None]:
    email_values = [str(item).strip() for item in (emails or []) if str(item).strip()]
    handle_values = [str(item).strip() for item in (handles or []) if str(item).strip()]
    candidate_values = [str(item).strip() for item in (candidates or []) if str(item).strip()]
    sample_texts = [str(sample.get("text") or "").strip() for sample in (samples or []) if isinstance(sample, dict) and str(sample.get("text") or "").strip()]

    core_haystack = _normalize_monitor_text(" ".join([display_name, *email_values, *handle_values, *candidate_values, *_contact_domain_hints(email_values)]))
    sample_haystack = _normalize_monitor_text(" ".join(sample_texts))
    has_service_email = bool(email_values)
    domain_hints = _contact_domain_hints(email_values)

    best_match: tuple[int, str, str] | None = None
    for config in CONTACT_ROLE_INFERENCE_LIBRARY:
        tokens = tuple(_normalize_monitor_text(token) for token in config.get("tokens") or () if str(token).strip())
        domains = tuple(_normalize_monitor_text(token) for token in config.get("domains") or () if str(token).strip())
        core_hits = sum(1 for token in tokens if token and token in core_haystack)
        sample_hits = sum(1 for token in tokens if token and token in sample_haystack) if has_service_email else 0
        domain_hits = sum(1 for token in domains if token and any(token == hint or token in hint or hint in token for hint in domain_hints))
        score = (core_hits * 4) + (sample_hits * 2) + (domain_hits * 5)
        if score <= 0:
            continue
        label = str(config["label"])
        summary = str(config["summary"])
        if not best_match or score > best_match[0]:
            best_match = (score, label, summary)

    if best_match:
        _, label, summary = best_match
        brand = str(display_name or "").strip() or (domain_hints[0] if domain_hints else "")
        if label == "Konaklama / rezervasyon hesabı" and brand:
            return label, f"{brand} üzerinden rezervasyon, konaklama veya giriş doğrulama bildirimleri gönderen kurumsal hesap."
        if label == "Seyahat / hava yolu hesabı" and brand:
            return label, f"{brand} üzerinden uçuş, bilet ve seyahat bildirimleri gönderen kurumsal hesap."
        if label == "Sipariş / alışveriş hesabı" and brand:
            return label, f"{brand} üzerinden sipariş, iade veya teslim sürecini yöneten alışveriş hesabı."
        if label == "Banka / ödeme hesabı" and brand:
            return label, f"{brand} üzerinden ödeme, kart veya hesap hareketi bildirimleri gönderen kurumsal hesap."
        return label, summary

    if has_service_email:
        domain_hint = next((item for item in domain_hints if item not in {"gmail", "hotmail", "outlook", "yahoo", "icloud"}), "")
        if domain_hint:
            return "Kurumsal e-posta hesabı", f"{domain_hint} alan adından yazan kurumsal hesap."
        return "E-posta iletişim hesabı", "E-posta üzerinden görülen kurumsal veya operasyonel hesap."

    return None, None


def _contact_topic_inference(
    *,
    samples: list[dict[str, Any]] | None = None,
    manual_profile: dict[str, Any] | None = None,
) -> list[str]:
    sample_texts = [str(sample.get("text") or "").strip() for sample in (samples or []) if isinstance(sample, dict) and str(sample.get("text") or "").strip()]
    if manual_profile:
        sample_texts.extend(
            [
                str(manual_profile.get("preferences") or "").strip(),
                str(manual_profile.get("notes") or "").strip(),
            ]
        )
    haystack = _normalize_monitor_text(" ".join(sample_texts))
    if not haystack:
        return []
    topics: list[str] = []
    for config in CONTACT_TOPIC_INFERENCE_LIBRARY:
        tokens = tuple(str(token).strip() for token in config.get("tokens") or () if str(token).strip())
        if tokens and any(token in haystack for token in tokens):
            _append_unique_strings(topics, [str(config["summary"])])
    return topics[:2]


def _communication_relationship_hint(
    profile: dict[str, Any],
    *,
    display_name: str,
    importance_reason: str,
    kind: str,
    candidates: list[str] | None = None,
    emails: list[str] | None = None,
    handles: list[str] | None = None,
    samples: list[dict[str, Any]] | None = None,
) -> str:
    display_normalized = _normalize_monitor_text(display_name)
    if display_normalized:
        for name_normalized, item in _related_profile_lookup(profile).items():
            if display_normalized == name_normalized:
                return str(item.get("relationship") or "Yakın çevre").strip() or "Yakın çevre"
    sample_channels = {
        str(sample.get("channel") or "").strip().lower()
        for sample in samples or []
        if isinstance(sample, dict) and str(sample.get("channel") or "").strip()
    }
    portable_identity = False
    for value in [display_name, *(candidates or []), *(emails or []), *(handles or [])]:
        for candidate in _stable_contact_identifiers(value):
            normalized_candidate = _normalize_monitor_text(candidate)
            if normalized_candidate.startswith(("phone:", "email:", "handle:", "wa:")):
                portable_identity = True
                break
        if portable_identity:
            break
    keyword_hint = _relationship_hint_from_candidates(
        [
            display_name,
            importance_reason,
            *[
                candidate
                for candidate in (candidates or [])
                if candidate
                and not _has_strong_contact_identifier(_normalize_monitor_text(candidate))
                and "chat:" not in _normalize_monitor_text(candidate)
            ],
        ]
    )
    exact_alias_hint = _exact_relationship_alias(display_name)
    if (
        keyword_hint in {"Anne", "Baba", "Eş", "Kızım", "Oğlum", "Kardeş", "Yakın arkadaş"}
        and not portable_identity
        and not (exact_alias_hint == keyword_hint and sample_channels and sample_channels.issubset({"whatsapp", "email"}))
    ):
        keyword_hint = ""
    if keyword_hint:
        return keyword_hint
    inferred_role, _ = _contact_role_inference(
        display_name=display_name,
        emails=emails,
        handles=handles,
        candidates=candidates,
        samples=samples,
    )
    if inferred_role:
        return inferred_role
    candidate_haystack = " ".join(_normalize_monitor_text(item) for item in [display_name, *(candidates or [])] if str(item or "").strip())
    if any(token in candidate_haystack for token in ("müvekkil", "muvekkil", "müşteri", "musteri", "client", "customer")):
        return "Muhtemel müvekkil / müşteri"
    return "Mesaj grubu" if kind == "group" else "İletişim kişisi"


def _communication_channel_compact_summary(channels: list[str]) -> str:
    normalized = [str(channel).strip().lower() for channel in channels if str(channel).strip()]
    if len(normalized) >= 2:
        labels = [_communication_channel_label(channel) for channel in normalized[:3]]
        return f"{', '.join(labels)} üzerinden temas kuruluyor."
    if "email" in normalized:
        return "E-posta üzerinden görülüyor."
    if "whatsapp" in normalized:
        return "WhatsApp üzerinden görülüyor."
    if "telegram" in normalized:
        return "Telegram üzerinden görülüyor."
    if "instagram" in normalized:
        return "Instagram üzerinden görülüyor."
    if "linkedin" in normalized:
        return "LinkedIn üzerinden görülüyor."
    if "x" in normalized:
        return "X üzerinden görülüyor."
    return "İletişim profili oluşuyor."


def _communication_persona_summary(
    *,
    kind: str,
    display_name: str,
    channels: list[str],
    importance_reason: str,
    relationship_hint: str,
    emails: list[str] | None = None,
    handles: list[str] | None = None,
    candidates: list[str] | None = None,
    samples: list[dict[str, Any]] | None = None,
    source_count: int = 0,
    group_contexts: list[str] | None = None,
) -> str:
    if importance_reason:
        return importance_reason
    if kind == "group":
        return "Takip edilen grup konuşması."
    _, inferred_summary = _contact_role_inference(
        display_name=display_name,
        emails=emails,
        handles=handles,
        candidates=candidates,
        samples=samples,
    )
    if inferred_summary:
        return inferred_summary
    close_relationships = {"Anne", "Baba", "Eş", "Kızım", "Oğlum", "Kardeş", "Yakın arkadaş", "Patron", "Yakın çevre"}
    if relationship_hint in close_relationships:
        parts = [f"{relationship_hint} olarak görünen yakın kişi."]
        if group_contexts:
            compact_groups = ", ".join(group_contexts[:2])
            parts.append(f"{compact_groups} içinde de yer alıyor.")
        parts.append(_communication_channel_compact_summary(channels))
        if source_count >= 6:
            parts.append("Sık temas edilen kişi.")
        return " ".join(part.strip() for part in parts if part.strip())
    if group_contexts:
        compact_groups = ", ".join(group_contexts[:2])
        return f"Direkt konuşma yanında {compact_groups} içinde de görünüyor."
    if relationship_hint and relationship_hint not in {"İletişim kişisi", "Muhtemel müvekkil / müşteri"}:
        return f"{relationship_hint}. {_communication_channel_compact_summary(channels)}"
    return _communication_channel_compact_summary(channels)


def _truncate_inline_text(value: str, *, limit: int = 120) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(limit - 1, 0)].rstrip()}…"


def _communication_channel_label(channel: str) -> str:
    labels = {
        "email": "E-posta",
        "whatsapp": "WhatsApp",
        "telegram": "Telegram",
        "instagram": "Instagram",
        "linkedin": "LinkedIn",
        "x": "X",
    }
    normalized = str(channel or "").strip().lower()
    return labels.get(normalized, normalized or "Kanal")


def _contact_channel_counts(entry: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in entry.get("_samples") or []:
        if not isinstance(sample, dict):
            continue
        channel = str(sample.get("channel") or "").strip().lower()
        if not channel:
            continue
        counts[channel] = counts.get(channel, 0) + 1
    for channel in entry.get("channels") or []:
        normalized = str(channel or "").strip().lower()
        if normalized and normalized not in counts:
            counts[normalized] = 1
    return counts


def _contact_channel_summary(entry: dict[str, Any]) -> str:
    counts = _contact_channel_counts(entry)
    ordered = sorted(
        counts.items(),
        key=lambda item: (-int(item[1]), _communication_channel_label(item[0])),
    )
    parts: list[str] = []
    for channel, count in ordered[:3]:
        label = _communication_channel_label(channel)
        parts.append(f"{label} {count}" if count > 1 else label)
    return ", ".join(parts)


def _contact_recent_message_preview(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    samples = [sample for sample in entry.get("_samples") or [] if isinstance(sample, dict)]
    if not samples:
        return None, None
    ordered = sorted(
        samples,
        key=lambda sample: (
            str(sample.get("occurred_at") or ""),
            str(sample.get("direction") or "") == "inbound",
        ),
        reverse=True,
    )
    recent_inbound = next(
        (
            sample
            for sample in ordered
            if str(sample.get("direction") or "").strip().lower() == "inbound"
            and str(sample.get("text") or "").strip()
        ),
        None,
    )
    selected = recent_inbound or next((sample for sample in ordered if str(sample.get("text") or "").strip()), None)
    if not selected:
        return None, None
    preview = _truncate_inline_text(str(selected.get("text") or "").strip(), limit=110)
    channel_label = _communication_channel_label(str(selected.get("channel") or ""))
    return preview or None, channel_label or None


def _contact_topic_breakdown(samples: list[dict[str, Any]] | None, *, limit: int = 2) -> list[str]:
    counts: dict[str, int] = {}
    for sample in samples or []:
        if not isinstance(sample, dict):
            continue
        normalized_text = _normalize_monitor_text(str(sample.get("text") or "").strip())
        if not normalized_text:
            continue
        for config in CONTACT_TOPIC_INFERENCE_LIBRARY:
            if any(token in normalized_text for token in config["tokens"]):
                label = str(config["label"])
                counts[label] = counts.get(label, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
    return [label for label, _count in ordered[:limit]]


def _contact_behavior_signals(entry: dict[str, Any], *, limit: int = 4) -> list[str]:
    samples = [
        sample
        for sample in entry.get("_samples") or []
        if isinstance(sample, dict) and str(sample.get("text") or "").strip()
    ]
    if not samples:
        return []

    total = len(samples)
    short_count = 0
    long_count = 0
    question_count = 0
    link_count = 0
    coordination_count = 0
    reaction_count = 0
    recent_24h_count = 0
    recent_1h_count = 0
    now = datetime.now(timezone.utc)
    coordination_tokens = (
        "yarin",
        "yarın",
        "bugun",
        "bugün",
        "aksam",
        "akşam",
        "saat",
        "konum",
        "geliyorum",
        "gelicem",
        "gelcem",
        "ugra",
        "uğra",
        "ara",
        "arayim",
        "arayayim",
        "arayacağım",
        "arayacagim",
        "buluş",
        "bulus",
        "check in",
        "check-in",
        "yolda",
        "haber ver",
        "tamam mi",
        "tamam mı",
    )

    for sample in samples:
        text = str(sample.get("text") or "").strip()
        normalized = _normalize_monitor_text(text)
        occurred_at = _parse_dt(str(sample.get("occurred_at") or "").strip())
        if occurred_at:
            age = now - occurred_at
            if age <= timedelta(hours=24):
                recent_24h_count += 1
            if age <= timedelta(hours=1):
                recent_1h_count += 1
        compact_length = len(" ".join(text.split()))
        if compact_length <= 42:
            short_count += 1
        if compact_length >= 140:
            long_count += 1
        if "?" in text or any(token in normalized for token in ("acaba", "bakabilir misin", "haber verir misin", "uygun musun", "müsait misin")):
            question_count += 1
        if re.search(r"https?://|www\.|share\.", text, flags=re.IGNORECASE):
            link_count += 1
        if any(token in normalized for token in coordination_tokens):
            coordination_count += 1
        if not re.search(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]", text):
            reaction_count += 1

    signals: list[str] = []
    if total >= 4 and short_count >= max(3, int(total * 0.55)):
        signals.append("Mesajların çoğu kısa ve hızlı ilerliyor; daha çok anlık koordinasyon ve tepki dili var.")
    if total >= 4 and coordination_count >= max(2, int(total * 0.25)):
        signals.append("Planlama, saat, buluşma ve günlük koordinasyon dili baskın görünüyor.")
    if total >= 4 and link_count >= 1:
        signals.append("Link ve içerik paylaşımı tekrarlıyor; sık sık bağlantı veya yönlendirme gönderiliyor.")
    if total >= 4 and long_count >= max(2, int(total * 0.3)):
        signals.append("Zaman zaman daha uzun açıklama veya detay veren mesajlar da geliyor.")
    if total >= 4 and question_count >= max(2, int(total * 0.25)):
        signals.append("Soru soran veya teyit isteyen mesajlar sık; cevap bekleyen bir iletişim tarzı var.")
    if total >= 4 and reaction_count >= max(2, int(total * 0.2)):
        signals.append("Kısa tepki, emoji veya tek satırlık dönüşler de sık görülüyor.")
    if recent_1h_count >= 2:
        signals.append(f"Son 1 saatte {recent_1h_count} mesaj örneği var; temas şu anda aktif.")
    elif recent_24h_count >= 3:
        signals.append(f"Son 24 saatte {recent_24h_count} mesaj örneği var; son dönemde hareketli bir yazışma görünüyor.")
    return signals[:limit]


def _communication_persona_detail(
    entry: dict[str, Any],
    *,
    manual_profile: dict[str, Any] | None,
    preference_signals: list[str],
) -> str:
    relationship_hint = str(entry.get("relationship_hint") or "").strip()
    kind = str(entry.get("kind") or "person").strip().lower() or "person"
    channel_summary = _contact_channel_summary(entry)
    source_count = int(entry.get("source_count") or 0)
    sample_count = len([sample for sample in entry.get("_samples") or [] if isinstance(sample, dict) and str(sample.get("text") or "").strip()])
    topic_labels = _contact_topic_breakdown(list(entry.get("_samples") or []), limit=2)
    behavior_signals = _contact_behavior_signals(entry, limit=5)
    recent_preview, recent_channel = _contact_recent_message_preview(entry)
    group_contexts = [str(item).strip() for item in entry.get("group_contexts") or [] if str(item).strip()]
    importance_reason = str(entry.get("_importance_reason") or "").strip()
    manual_preferences = str((manual_profile or {}).get("preferences") or "").strip()
    manual_notes = str((manual_profile or {}).get("notes") or "").strip()

    parts: list[str] = []
    if kind == "group":
        parts.append("Bu kayıt bir grup konuşması.")
    elif relationship_hint and relationship_hint not in {"İletişim kişisi", "Muhtemel müvekkil / müşteri"}:
        parts.append(f"Mesaj geçmişine göre {relationship_hint.lower()} olarak öne çıkıyor.")
    elif importance_reason:
        parts.append(_truncate_inline_text(importance_reason, limit=180))
    else:
        parts.append("Mesaj geçmişinden oluşan iletişim özeti.")

    if channel_summary:
        parts.append(f"En çok görülen kanallar: {channel_summary}.")
    if sample_count >= 12:
        parts.append(f"Bu açıklama {sample_count} mesaj örneğine dayanıyor; baskın kalıplar son yazışmalardan çıkarıldı.")
    elif sample_count >= 4:
        parts.append(f"Açıklama {sample_count} mesaj örneğine dayanıyor.")
    elif source_count >= 4:
        parts.append("Açıklama birden fazla temas kaydına dayanıyor.")
    _append_unique_strings(parts, behavior_signals)
    if topic_labels:
        parts.append(f"Mesajların baskın gündemi: {', '.join(topic_labels)}.")
    if preference_signals:
        parts.append(preference_signals[0])
    elif manual_preferences:
        parts.append(_truncate_inline_text(manual_preferences, limit=180))
    if group_contexts:
        parts.append(f"Ayrıca {', '.join(group_contexts[:2])} içinde de görünüyor.")
    if recent_preview:
        recent_source = recent_channel or "mesaj"
        parts.append(f"Son dikkat çeken örnek ({recent_source}): “{recent_preview}”")
    if manual_notes:
        parts.append(_truncate_inline_text(manual_notes, limit=180))
    return " ".join(part.strip() for part in parts if part.strip()) or "Bu kişi için detaylı açıklama henüz oluşmadı."


def _contact_inference_signals(
    entry: dict[str, Any],
    *,
    manual_profile: dict[str, Any] | None,
    preference_signals: list[str],
) -> list[str]:
    signals: list[str] = []
    topic_signals = _contact_topic_inference(samples=list(entry.get("_samples") or []), manual_profile=manual_profile)
    behavior_signals = _contact_behavior_signals(entry, limit=3)
    if preference_signals:
        _append_unique_strings(signals, preference_signals[:2])
    if manual_profile:
        closeness = _normalize_related_profile_closeness(
            manual_profile.get("closeness"),
            relationship=str(manual_profile.get("relationship") or entry.get("relationship_hint") or ""),
        )
        if closeness >= 4:
            _append_unique_strings(signals, ["Yakın çevrende; daha detaylı takip etmeye değer."])
    importance_reason = str(entry.get("_importance_reason") or "").strip()
    if importance_reason:
        _append_unique_strings(signals, [_truncate_inline_text(importance_reason, limit=120)])
    channels = list(entry.get("channels") or [])
    if len(channels) >= 2:
        labels = [_communication_channel_label(channel) for channel in channels[:3]]
        _append_unique_strings(signals, [f"{', '.join(labels)} üzerinden düzenli temas var."])
    elif channels:
        _append_unique_strings(signals, [f"İletişim çoğunlukla {_communication_channel_label(channels[0])} üzerinden ilerliyor."])
    group_contexts = [str(item).strip() for item in entry.get("group_contexts") or [] if str(item).strip()]
    if group_contexts:
        _append_unique_strings(signals, [f"{', '.join(group_contexts[:2])} içinde de birlikte görünüyor."])
    if int(entry.get("source_count") or 0) >= 6:
        _append_unique_strings(signals, ["Sık temas kurulan kişi / hesap."])
    if bool(entry.get("watch_enabled")):
        _append_unique_strings(signals, ["İzleme listesinde tutuluyor."])
    inferred_role, inferred_summary = _contact_role_inference(
        display_name=str(entry.get("display_name") or ""),
        emails=list(entry.get("emails") or []),
        handles=list(entry.get("handles") or []),
        candidates=list(entry.get("_match_candidates") or []),
        samples=list(entry.get("_samples") or []),
    )
    if topic_signals and (manual_profile or not inferred_role):
        _append_unique_strings(signals, topic_signals[:2])
    if inferred_role and inferred_summary:
        _append_unique_strings(signals, [inferred_summary])
    if behavior_signals:
        _append_unique_strings(signals, behavior_signals)
    low_signal_haystack = _normalize_monitor_text(
        " ".join(
            [
                str(entry.get("display_name") or ""),
                *(entry.get("emails") or []),
                *(entry.get("handles") or []),
            ]
        )
    )
    if not inferred_role and any(token in low_signal_haystack for token in LOW_SIGNAL_CONTACT_TOKENS):
        _append_unique_strings(signals, ["Bülten veya otomatik hesap gibi görünüyor."])
    if manual_profile and str(manual_profile.get("notes") or "").strip():
        _append_unique_strings(signals, [_truncate_inline_text(str(manual_profile.get("notes") or "").strip(), limit=120)])
    return signals[:6]


def _communication_watch_status(
    profile: dict[str, Any],
    *,
    kind: str,
    channels: list[str],
    candidates: list[str],
) -> tuple[bool, bool, str | None]:
    watch_rules = [item for item in profile.get("inbox_watch_rules") or [] if isinstance(item, dict)]
    block_rules = _active_inbox_block_rules(profile)
    active_watch = False
    blocked = False
    blocked_until: str | None = None

    for channel in channels or ["email"]:
        match_value, _ = _monitor_rule_match(
            watch_rules,
            channel=channel,
            match_type=kind,
            candidates=candidates,
        )
        if match_value:
            active_watch = True
        block_match_value, _ = _monitor_rule_match(
            block_rules,
            channel=channel,
            match_type=kind,
            candidates=candidates,
        )
        if block_match_value:
            blocked = True
            for rule in block_rules:
                if str(rule.get("match_type") or "").strip() != kind:
                    continue
                if not _channel_matches_rule(rule.get("channels"), channel):
                    continue
                rule_value = str(rule.get("match_value") or rule.get("label") or "").strip()
                if rule_value and _monitor_text_matches(rule_value, candidates):
                    blocked_until = str(rule.get("expires_at") or "").strip() or None
                    break
    return active_watch, blocked, blocked_until


def _contact_matches_name(value: str, *, aliases: list[str]) -> bool:
    haystack = _normalize_monitor_text(value)
    if not haystack:
        return False
    for alias in aliases:
        normalized_alias = _normalize_monitor_text(alias)
        if not normalized_alias:
            continue
        if normalized_alias in haystack or haystack in normalized_alias:
            return True
    return False


def _contact_preference_signals(entry: dict[str, Any], manual_profile: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    aliases = [str(entry.get("display_name") or "").strip(), str(entry.get("relationship_hint") or "").strip()]
    if manual_profile:
        aliases.extend(
            [
                str(manual_profile.get("name") or "").strip(),
                str(manual_profile.get("relationship") or "").strip(),
                str(manual_profile.get("preferences") or "").strip(),
            ]
        )

    notes: list[str] = []
    gifts: list[str] = []
    manual_text = " ".join(
        [
            str(manual_profile.get("preferences") or "").strip() if manual_profile else "",
            str(manual_profile.get("notes") or "").strip() if manual_profile else "",
        ]
    )

    for config in PREFERENCE_SIGNAL_LIBRARY:
        signal_samples = [sample for sample in entry.get("_samples") or [] if isinstance(sample, dict)]
        if manual_text:
            signal_samples.append({"text": manual_text, "direction": "note"})

        positive_found = False
        negative_found = False
        for sample in signal_samples:
            sample_text = str(sample.get("text") or "").strip()
            normalized_text = _normalize_monitor_text(sample_text)
            if not normalized_text or not any(token in normalized_text for token in config["tokens"]):
                continue
            sample_direction = str(sample.get("direction") or "").strip().lower()
            alias_required = sample_direction == "outbound"
            mentions_alias = _contact_matches_name(sample_text, aliases=aliases)
            if alias_required and not mentions_alias:
                continue
            if sample_direction == "inbound" and not mentions_alias and any(
                token in normalized_text for token in TRANSACTIONAL_CONTACT_MESSAGE_TOKENS
            ):
                continue
            if any(token in normalized_text for token in NEGATIVE_PREFERENCE_TOKENS):
                negative_found = True
                positive_found = False
                break
            if any(token in normalized_text for token in POSITIVE_PREFERENCE_TOKENS):
                positive_found = True
        if negative_found:
            notes.append(str(config["negative"]))
            continue
        if positive_found:
            notes.append(str(config["positive"]))
            gift = str(config.get("gift") or "").strip()
            if gift:
                gifts.append(gift)
    deduped_notes: list[str] = []
    deduped_gifts: list[str] = []
    _append_unique_strings(deduped_notes, notes)
    _append_unique_strings(deduped_gifts, gifts)
    return deduped_notes[:4], deduped_gifts[:3]


def _contact_selection_score(entry: dict[str, Any], *, manual_profile: dict[str, Any] | None) -> tuple[int, str]:
    if str(entry.get("kind") or "") != "person":
        return -100, "Grup kaydı detaylı profil için seçilmedi."

    relationship_hint = str(entry.get("relationship_hint") or "").strip()
    score = min(int(entry.get("source_count") or 0), 8)
    reason_parts: list[str] = []
    if manual_profile:
        score += 10
        reason_parts.append("kullanıcı profiline yakın çevre olarak eklenmiş")
        closeness = _normalize_related_profile_closeness(
            manual_profile.get("closeness"),
            relationship=str(manual_profile.get("relationship") or ""),
        )
        score += closeness * 2
        reason_parts.append(f"yakınlık puanı {closeness}/5")
    if relationship_hint and relationship_hint not in {"İletişim kişisi", "Muhtemel müvekkil / müşteri"}:
        score += 7
        reason_parts.append(f"ilişki sinyali: {relationship_hint.lower()}")
    if len(entry.get("channels") or []) >= 2:
        score += 3
        reason_parts.append("birden fazla kanalda görünüyor")
    if str(entry.get("_importance_reason") or "").strip():
        score += 4
        reason_parts.append("iletilerde önem sinyali var")
    if bool(entry.get("watch_enabled")):
        score += 3
        reason_parts.append("izleme kuralında")
    last_message_at = _parse_dt(str(entry.get("last_message_at") or "").strip())
    if last_message_at and last_message_at >= datetime.now(timezone.utc) - timedelta(days=21):
        score += 3
        reason_parts.append("son dönemde aktif")
    low_signal_haystack = _normalize_monitor_text(
        " ".join(
            [
                str(entry.get("display_name") or ""),
                *(entry.get("emails") or []),
                *(entry.get("handles") or []),
            ]
        )
    )
    if any(token in low_signal_haystack for token in LOW_SIGNAL_CONTACT_TOKENS):
        score -= 6
        reason_parts.append("düşük sinyal / bülten hesabı")
    if int(entry.get("source_count") or 0) >= 6:
        reason_parts.append("yüksek mesajlaşma hacmi")
    reason = ", ".join(reason_parts) if reason_parts else "yakın çevre sinyali zayıf"
    return score, reason


def _contact_profile_summary(
    entry: dict[str, Any],
    *,
    manual_profile: dict[str, Any] | None,
    preference_signals: list[str],
) -> str:
    parts: list[str] = []
    relationship_hint = str(entry.get("relationship_hint") or "").strip()
    topic_signals = _contact_topic_inference(samples=list(entry.get("_samples") or []), manual_profile=manual_profile)
    inferred_role, inferred_summary = _contact_role_inference(
        display_name=str(entry.get("display_name") or ""),
        emails=list(entry.get("emails") or []),
        handles=list(entry.get("handles") or []),
        candidates=list(entry.get("_match_candidates") or []),
        samples=list(entry.get("_samples") or []),
    )
    close_level = _normalize_related_profile_closeness(
        (manual_profile or {}).get("closeness") if manual_profile else None,
        relationship=str((manual_profile or {}).get("relationship") or relationship_hint or ""),
    ) if manual_profile or relationship_hint else 0
    if inferred_summary:
        parts.append(inferred_summary)
    elif relationship_hint and relationship_hint != "İletişim kişisi":
        if close_level >= 4:
            parts.append(f"{relationship_hint} olarak kayıtlı yakın kişi.")
        else:
            parts.append(f"{relationship_hint} olarak öne çıkıyor.")
    if str(entry.get("_importance_reason") or "").strip():
        parts.append(str(entry.get("_importance_reason")).strip())
    parts.append(_communication_channel_compact_summary(list(entry.get("channels") or [])))
    group_contexts = [str(item).strip() for item in entry.get("group_contexts") or [] if str(item).strip()]
    if group_contexts:
        parts.append(f"{', '.join(group_contexts[:2])} içinde de yer alıyor.")
    if int(entry.get("source_count") or 0) >= 6:
        parts.append("Sık temas var.")
    if topic_signals and (manual_profile or not inferred_summary):
        parts.append(topic_signals[0])
    if manual_profile and str(manual_profile.get("notes") or "").strip():
        parts.append(str(manual_profile.get("notes")).strip())
    if preference_signals:
        parts.append(preference_signals[0])
    return " ".join(part.strip() for part in parts if part.strip()) or "Bu kişi için profil özeti oluşturuldu."


def build_assistant_relationship_profiles(store, office_id: str, *, limit: int = 12) -> list[dict[str, Any]]:
    profile = store.get_user_profile(office_id)
    entries = _collect_assistant_contact_entries(
        store,
        office_id,
        limit=max(limit * 6, 80),
        include_operational_relationship_candidates=True,
    )
    selected: list[dict[str, Any]] = []
    for entry in entries:
        manual_profile = _related_profile_for_display(profile, str(entry.get("display_name") or ""))
        preference_signals, gift_ideas = _contact_preference_signals(entry, manual_profile)
        inference_signals = _contact_inference_signals(
            entry,
            manual_profile=manual_profile,
            preference_signals=preference_signals,
        )
        recent_preview, recent_channel = _contact_recent_message_preview(entry)
        score, selection_reason = _contact_selection_score(entry, manual_profile=manual_profile)
        relationship_hint = str(entry.get("relationship_hint") or "").strip()
        selected_for_profile = bool(manual_profile) or score >= IMPORTANT_CONTACT_SELECTION_THRESHOLD
        if not selected_for_profile:
            continue
        summary = _contact_profile_summary(entry, manual_profile=manual_profile, preference_signals=preference_signals)
        selected.append(
            {
                "id": str(entry.get("id") or ""),
                "display_name": str(entry.get("display_name") or "").strip(),
                "relationship_hint": relationship_hint or "Yakın çevre",
                "related_profile_id": str((manual_profile or {}).get("id") or "").strip() or None,
                "closeness": _normalize_related_profile_closeness(
                    (manual_profile or {}).get("closeness") if manual_profile else None,
                    relationship=str((manual_profile or {}).get("relationship") or relationship_hint or ""),
                ),
                "profile_strength": "yüksek" if score >= IMPORTANT_CONTACT_HIGH_CONFIDENCE_THRESHOLD else "orta",
                "selection_score": score,
                "selection_reason": selection_reason,
                "summary": summary,
                "channels": list(entry.get("channels") or []),
                "emails": list(entry.get("emails") or []),
                "phone_numbers": list(entry.get("phone_numbers") or []),
                "handles": list(entry.get("handles") or []),
                "watch_enabled": bool(entry.get("watch_enabled")),
                "blocked": bool(entry.get("blocked")),
                "blocked_until": entry.get("blocked_until"),
                "last_message_at": entry.get("last_message_at"),
                "source_count": int(entry.get("source_count") or 0),
                "preference_signals": preference_signals,
                "gift_ideas": gift_ideas,
                "inference_signals": inference_signals,
                "channel_summary": _contact_channel_summary(entry),
                "last_inbound_preview": recent_preview,
                "last_inbound_channel": recent_channel,
                "group_contexts": list(entry.get("group_contexts") or []),
                "important_dates": list((manual_profile or {}).get("important_dates") or []),
                "notes": str((manual_profile or {}).get("notes") or "").strip(),
                "auto_selected": not bool(manual_profile),
            }
        )
    selected.sort(
        key=lambda item: (
            int(item.get("selection_score") or 0),
            int(item.get("source_count") or 0),
            str(item.get("last_message_at") or ""),
        ),
        reverse=True,
    )
    return selected[:limit]


def _contact_calendar_match(profile: dict[str, Any], event: dict[str, Any]) -> bool:
    aliases = [
        str(profile.get("display_name") or "").strip(),
        str(profile.get("relationship_hint") or "").strip(),
        *(profile.get("emails") or []),
        *(profile.get("handles") or []),
    ]
    haystacks = [
        str(event.get("title") or "").strip(),
        str(event.get("details") or "").strip(),
        str(event.get("location") or "").strip(),
        *[str(item) for item in event.get("attendees") or []],
    ]
    metadata = event.get("metadata")
    if isinstance(metadata, dict):
        haystacks.extend(str(value) for value in metadata.values() if isinstance(value, (str, int, float)))
    return any(_contact_matches_name(haystack, aliases=aliases) for haystack in haystacks if str(haystack or "").strip())


def _collect_assistant_contact_entries(
    store,
    office_id: str,
    *,
    limit: int = 80,
    include_operational_relationship_candidates: bool = False,
) -> list[dict[str, Any]]:
    profile = store.get_user_profile(office_id)
    people: dict[str, dict[str, Any]] = {}
    groups: dict[str, dict[str, Any]] = {}
    people_aliases: dict[str, str] = {}
    group_aliases: dict[str, str] = {}

    def _entry_profile_id(kind: str, canonical_key: str, fallback_label: str) -> str:
        normalized = _normalize_monitor_text(canonical_key or fallback_label).replace(" ", "-")
        return f"{kind}:{normalized or 'profile'}"

    def _is_strong_contact_identifier(candidate: str) -> bool:
        normalized = _normalize_monitor_text(candidate)
        if not normalized:
            return False
        if normalized.startswith(("phone:", "email:", "wa:", "wa-group:", "handle:")):
            return True
        if normalized.startswith("id:"):
            token = normalized[3:]
            return any(character.isdigit() for character in token) or any(character in token for character in "@/._:-")
        return False

    def normalized_aliases(values: list[str] | None) -> tuple[list[str], list[str]]:
        raw_aliases: list[str] = []
        stable_aliases: list[str] = []
        for value in values or []:
            raw = str(value or "").strip()
            normalized_raw = _normalize_monitor_text(raw)
            if normalized_raw and normalized_raw not in raw_aliases:
                raw_aliases.append(normalized_raw)
            for candidate in _stable_contact_identifiers(raw):
                normalized = _normalize_monitor_text(candidate)
                if _is_strong_contact_identifier(normalized) and normalized not in stable_aliases:
                    stable_aliases.append(normalized)
        return raw_aliases, stable_aliases

    def _preferred_exact_relationship_key(label: str) -> str | None:
        exact_relationship = _exact_relationship_alias(label)
        normalized_label = _normalize_monitor_text(label)
        if exact_relationship and normalized_label:
            return f"relation-alias:{normalized_label}"
        return None

    def _whatsapp_saved_label_candidates(values: list[object] | None) -> list[str]:
        labels: list[str] = []
        for value in values or []:
            raw = str(value or "").strip()
            normalized = _normalize_monitor_text(raw)
            if not normalized:
                continue
            if _is_strong_contact_identifier(normalized):
                continue
            if any(character.isdigit() for character in normalized):
                continue
            if normalized in LOW_SIGNAL_CONTACT_TOKENS:
                continue
            if raw not in labels:
                labels.append(raw)
        return labels

    def _preferred_whatsapp_person_key(
        *,
        direct: bool,
        conversation_ref: str,
        label: str,
        aliases: list[object] | None = None,
        fallback_by_label: callable | None = None,
    ) -> str:
        stable_alias_keys: list[str] = []
        for value in [conversation_ref, label, *(str(value or "") for value in aliases or [])]:
            for candidate in _stable_contact_identifiers(value):
                normalized_candidate = _normalize_monitor_text(candidate)
                if normalized_candidate.startswith(("phone:", "wa:")) and normalized_candidate not in stable_alias_keys:
                    stable_alias_keys.append(normalized_candidate)
                    continue
                if normalized_candidate.startswith("id:"):
                    token = normalized_candidate[3:]
                    if (any(character.isdigit() for character in token) or any(character in token for character in "@/._:")) and normalized_candidate not in stable_alias_keys:
                        stable_alias_keys.append(normalized_candidate)
        if fallback_by_label is not None:
            resolved = str(fallback_by_label() or "").strip()
            if resolved:
                return resolved
        if stable_alias_keys:
            return stable_alias_keys[0]
        relation_key = _preferred_exact_relationship_key(label) if direct else None
        if relation_key:
            return relation_key
        normalized_ref = _normalize_monitor_text(conversation_ref)
        normalized_label = _normalize_monitor_text(label) or "contact"
        if direct:
            if normalized_label and normalized_ref and "@" not in str(conversation_ref or "") and not any(character.isdigit() for character in normalized_ref):
                return normalized_label
            return f"wa-direct:{normalized_ref or normalized_label}"
        return f"wa-group-member:{normalized_ref or 'group'}:{normalized_label}"

    def _preferred_telegram_person_key(
        *,
        direct: bool,
        conversation_ref: str,
        label: str,
        aliases: list[object] | None = None,
    ) -> str:
        stable_alias_keys: list[str] = []
        for value in [conversation_ref, label, *(str(value or "") for value in aliases or [])]:
            for candidate in _stable_contact_identifiers(value):
                normalized_candidate = _normalize_monitor_text(candidate)
                if normalized_candidate.startswith(("phone:", "handle:", "id:")) and normalized_candidate not in stable_alias_keys:
                    stable_alias_keys.append(normalized_candidate)
        if stable_alias_keys:
            return stable_alias_keys[0]
        normalized_ref = _normalize_monitor_text(conversation_ref)
        normalized_label = _normalize_monitor_text(label) or "contact"
        if direct:
            return f"tg-direct:{normalized_ref or normalized_label}"
        return f"tg-group-member:{normalized_ref or 'group'}:{normalized_label}"

    whatsapp_messages = store.list_whatsapp_messages(office_id, limit=max(80, min(limit * 12, 800)))
    whatsapp_snapshots = store.list_whatsapp_contact_snapshots(office_id, limit=max(120, min(limit * 8, 800)))
    whatsapp_saved_label_index: dict[str, set[str]] = {}

    def _register_whatsapp_saved_labels(canonical_key: str, values: list[object] | None) -> None:
        normalized_key = _normalize_monitor_text(canonical_key)
        if not normalized_key or not _is_strong_contact_identifier(normalized_key):
            return
        for label in _whatsapp_saved_label_candidates(values):
            normalized_label = _normalize_monitor_text(label)
            if not normalized_label:
                continue
            whatsapp_saved_label_index.setdefault(normalized_label, set()).add(normalized_key)

    def _resolve_whatsapp_saved_label_key(values: list[object] | None) -> str | None:
        for label in _whatsapp_saved_label_candidates(values):
            normalized_label = _normalize_monitor_text(label)
            keys = sorted(whatsapp_saved_label_index.get(normalized_label) or [])
            if len(keys) == 1:
                return keys[0]
        return None

    for snapshot in whatsapp_snapshots:
        conversation_ref = str(snapshot.get("conversation_ref") or "").strip()
        if not conversation_ref or conversation_ref == "status@broadcast":
            continue
        is_group = bool(snapshot.get("is_group")) or conversation_ref.endswith("@g.us")
        if is_group:
            continue
        metadata = dict(snapshot.get("metadata") or {})
        canonical_key = _preferred_whatsapp_person_key(
            direct=True,
            conversation_ref=conversation_ref,
            label=str(snapshot.get("display_name") or snapshot.get("profile_name") or conversation_ref),
            aliases=[
                snapshot.get("phone_number"),
                metadata.get("contact_name"),
                metadata.get("chat_name"),
                snapshot.get("profile_name"),
            ],
        )
        _register_whatsapp_saved_labels(
            canonical_key,
            [
                snapshot.get("display_name"),
                metadata.get("contact_name"),
                metadata.get("chat_name"),
            ],
        )

    for message in whatsapp_messages:
        conversation_ref = str(message.get("conversation_ref") or "").strip()
        if not conversation_ref or conversation_ref.endswith("@g.us"):
            continue
        metadata = dict(message.get("metadata") or {})
        canonical_key = _preferred_whatsapp_person_key(
            direct=True,
            conversation_ref=conversation_ref,
            label=_whatsapp_message_contact_label(message),
            aliases=[
                metadata.get("from"),
                metadata.get("to"),
                str(message.get("sender") or ""),
                str(message.get("recipient") or ""),
                *list(_whatsapp_message_phone_numbers(message)),
            ],
        )
        _register_whatsapp_saved_labels(
            canonical_key,
            [
                metadata.get("chat_name"),
                metadata.get("contact_name"),
                _whatsapp_message_contact_label(message),
            ],
        )

    def ensure_person(
        label: str,
        *,
        aliases: list[str] | None = None,
        preferred_key: str | None = None,
    ) -> dict[str, Any]:
        display_name = str(label or "").strip() or "Bilinmeyen kişi"
        alias_keys, stable_alias_keys = normalized_aliases([display_name, *(aliases or [])])
        key = next((people_aliases.get(alias) for alias in stable_alias_keys if people_aliases.get(alias)), None)
        if not key:
            normalized_display_name = _normalize_monitor_text(display_name)
            key = str(preferred_key or "").strip() or (stable_alias_keys[0] if stable_alias_keys else normalized_display_name)
        item = people.get(key)
        if item:
            if _contact_display_name_score(display_name) > _contact_display_name_score(str(item.get("display_name") or "")):
                item["display_name"] = display_name
                item["id"] = _entry_profile_id("person", str(item.get("_canonical_key") or key), display_name)
            for alias in stable_alias_keys:
                people_aliases[alias] = key
            return item
        item = {
            "id": _entry_profile_id("person", key, display_name),
            "kind": "person",
            "display_name": display_name,
            "channels": [],
            "emails": [],
            "phone_numbers": [],
            "handles": [],
            "source_count": 0,
            "last_message_at": None,
            "_importance_reason": "",
            "_match_candidates": [display_name],
            "_samples": [],
            "_group_contexts": [],
            "_canonical_key": key,
        }
        people[key] = item
        for alias in stable_alias_keys:
            people_aliases[alias] = key
        return item

    def ensure_group(label: str, *, aliases: list[str] | None = None) -> dict[str, Any]:
        display_name = str(label or "").strip() or "Bilinmeyen grup"
        _, stable_alias_keys = normalized_aliases([display_name, *(aliases or [])])
        key = next((group_aliases.get(alias) for alias in stable_alias_keys if group_aliases.get(alias)), None)
        if not key:
            key = stable_alias_keys[0] if stable_alias_keys else _normalize_monitor_text(display_name)
        item = groups.get(key)
        if item:
            for alias in stable_alias_keys:
                group_aliases[alias] = key
            return item
        item = {
            "id": _entry_profile_id("group", key, display_name),
            "kind": "group",
            "display_name": display_name,
            "channels": [],
            "emails": [],
            "phone_numbers": [],
            "handles": [],
            "source_count": 0,
            "last_message_at": None,
            "_importance_reason": "",
            "_match_candidates": [display_name],
            "_samples": [],
            "_canonical_key": key,
        }
        groups[key] = item
        for alias in stable_alias_keys:
            group_aliases[alias] = key
        return item

    def update_profile_entry(
        entry: dict[str, Any],
        *,
        channel: str,
        occurred_at: str | None,
        emails: list[str] | None = None,
        phones: list[str] | None = None,
        handles: list[str] | None = None,
        candidates: list[str] | None = None,
        importance_reason: str | None = None,
        sample_text: str | None = None,
        direction: str | None = None,
    ) -> None:
        if channel not in entry["channels"]:
            entry["channels"].append(channel)
        _append_unique_strings(entry["emails"], list(emails or []))
        _append_unique_strings(entry["phone_numbers"], list(phones or []))
        _append_unique_strings(entry["handles"], list(handles or []))
        _append_unique_strings(entry["_match_candidates"], list(candidates or []))
        _, stable_alias_keys = normalized_aliases(
            [
                str(entry.get("display_name") or ""),
                *(emails or []),
                *(phones or []),
                *(handles or []),
                *(candidates or []),
            ]
        )
        canonical_key = str(entry.get("_canonical_key") or _normalize_monitor_text(str(entry.get("display_name") or "")))
        alias_lookup = group_aliases if str(entry.get("kind") or "") == "group" else people_aliases
        for alias in stable_alias_keys:
            alias_lookup[alias] = canonical_key
        entry["source_count"] += 1
        occurred = str(occurred_at or "").strip()
        if occurred and (not entry["last_message_at"] or occurred > str(entry["last_message_at"])):
            entry["last_message_at"] = occurred
        if importance_reason and not entry["_importance_reason"]:
            entry["_importance_reason"] = importance_reason
        compact_sample = str(sample_text or "").strip()
        if compact_sample:
            entry["_samples"].append(
                {
                    "text": compact_sample,
                    "channel": channel,
                    "occurred_at": occurred,
                    "direction": str(direction or "").strip().lower(),
                }
            )

    for thread in store.list_email_threads(office_id)[: max(40, min(limit * 8, 400))]:
        raw_sender, display_name, sender_email, _ = _email_sender_identity(thread)
        label = display_name or sender_email or raw_sender
        if not label:
            continue
        importance_reason = _important_contact_reason(
            raw_sender,
            dict(thread.get("metadata") or {}).get("sender_title"),
            dict(thread.get("metadata") or {}).get("sender_role"),
        )
        person = ensure_person(
            label,
            aliases=[raw_sender, sender_email],
            preferred_key=_preferred_exact_relationship_key(label),
        )
        update_profile_entry(
            person,
            channel="email",
            occurred_at=str(thread.get("received_at") or ""),
            emails=[sender_email] if sender_email else [],
            candidates=[label, raw_sender, sender_email],
            importance_reason=importance_reason,
            sample_text=" ".join(
                part for part in [
                    str(thread.get("subject") or "").strip(),
                    str(thread.get("snippet") or "").strip(),
                ] if part
            ),
            direction="inbound",
        )

    for message in whatsapp_messages:
        group_label = _whatsapp_message_group_label(message)
        actor_label = _whatsapp_message_actor_label(message)
        message_direction = str(message.get("direction") or "").strip().lower()
        actor_party = str(message.get("recipient") or "").strip() if message_direction == "outbound" else str(message.get("sender") or "").strip()
        message_metadata = dict(message.get("metadata") or {})
        importance_reason = _important_contact_reason(
            message.get("sender"),
            message.get("recipient"),
            message_metadata.get("profile_name"),
            message_metadata.get("contact_name"),
        )
        if actor_label:
            if group_label:
                actor_candidates = [
                    actor_label,
                    actor_party,
                    str(message_metadata.get("contact_name") or ""),
                    str(message_metadata.get("profile_name") or ""),
                    str(message_metadata.get("author") or ""),
                    str(message_metadata.get("participant") or ""),
                ]
            else:
                actor_candidates = [
                    actor_label,
                    actor_party,
                    str(message_metadata.get("chat_name") or ""),
                    str(message_metadata.get("contact_name") or ""),
                    str(message_metadata.get("profile_name") or ""),
                    str(message.get("conversation_ref") or ""),
                ]
            if actor_label:
                preferred_key = _preferred_whatsapp_person_key(
                    direct=not bool(group_label),
                    conversation_ref=str(message.get("conversation_ref") or ""),
                    label=actor_label,
                    aliases=actor_candidates + list(_whatsapp_message_phone_numbers(message)),
                    fallback_by_label=(
                        lambda actor_label=actor_label, message_metadata=message_metadata: _resolve_whatsapp_saved_label_key(
                            [
                                actor_label,
                                str(message_metadata.get("contact_name") or ""),
                                str(message_metadata.get("chat_name") or ""),
                            ]
                        )
                    )
                    if group_label
                    else None,
                )
                person = ensure_person(
                    actor_label,
                    aliases=actor_candidates,
                    preferred_key=preferred_key,
                )
                update_profile_entry(
                    person,
                    channel="whatsapp",
                    occurred_at=str(message.get("sent_at") or ""),
                    phones=_whatsapp_message_phone_numbers(message),
                    candidates=actor_candidates,
                    importance_reason=importance_reason,
                    sample_text=str(message.get("body") or "").strip(),
                    direction=str(message.get("direction") or "").strip(),
                )
                if group_label:
                    _append_unique_strings(person["_group_contexts"], [group_label])
        if group_label:
            group = ensure_group(group_label, aliases=[str(message.get("conversation_ref") or "")])
            update_profile_entry(
                group,
                channel="whatsapp",
                occurred_at=str(message.get("sent_at") or ""),
                candidates=[group_label, str(message.get("conversation_ref") or "")],
                sample_text=str(message.get("body") or "").strip(),
                direction=str(message.get("direction") or "").strip(),
            )

    for snapshot in whatsapp_snapshots:
        conversation_ref = str(snapshot.get("conversation_ref") or "").strip()
        if not conversation_ref or conversation_ref == "status@broadcast":
            continue
        display_name = str(snapshot.get("display_name") or "").strip()
        profile_name = str(snapshot.get("profile_name") or "").strip()
        group_name = str(snapshot.get("group_name") or "").strip()
        phone_number = str(snapshot.get("phone_number") or "").strip()
        is_group = bool(snapshot.get("is_group")) or conversation_ref.endswith("@g.us")
        occurred_at = str(snapshot.get("last_seen_at") or "")
        metadata = dict(snapshot.get("metadata") or {})
        if is_group:
            group_label = group_name or display_name or conversation_ref
            group = ensure_group(group_label, aliases=[conversation_ref])
            update_profile_entry(
                group,
                channel="whatsapp",
                occurred_at=occurred_at,
                candidates=[group_label, conversation_ref],
            )
            continue

        contact_label = display_name or profile_name or conversation_ref
        if not contact_label:
            continue
        preferred_key = _preferred_whatsapp_person_key(
            direct=True,
            conversation_ref=conversation_ref,
            label=contact_label,
            aliases=[
                phone_number,
                profile_name,
                str(metadata.get("contact_name") or ""),
                str(metadata.get("chat_name") or ""),
            ],
        )
        person = ensure_person(
            contact_label,
            aliases=[
                conversation_ref,
                phone_number,
                profile_name,
                str(metadata.get("contact_name") or ""),
                str(metadata.get("chat_name") or ""),
            ],
            preferred_key=preferred_key,
        )
        update_profile_entry(
            person,
            channel="whatsapp",
            occurred_at=occurred_at,
            phones=[phone_number] if phone_number else [],
            candidates=[
                contact_label,
                profile_name,
                conversation_ref,
                str(metadata.get("contact_name") or ""),
                str(metadata.get("chat_name") or ""),
            ],
        )

    for message in store.list_telegram_messages(office_id, limit=max(60, min(limit * 8, 500))):
        group_label = _telegram_message_group_label(message)
        actor_label = _telegram_message_actor_label(message)
        message_direction = str(message.get("direction") or "").strip().lower()
        actor_party = str(message.get("recipient") or "").strip() if message_direction == "outbound" else str(message.get("sender") or "").strip()
        message_metadata = dict(message.get("metadata") or {})
        message_phones = _telegram_message_phone_numbers(message)
        actor_candidates = [
            actor_label,
            actor_party,
            str(message.get("conversation_ref") or ""),
            str(message_metadata.get("username") or ""),
            str(message_metadata.get("display_name") or ""),
            str(message_metadata.get("chat_title") or ""),
            *message_phones,
        ]
        if actor_label:
            preferred_key = _preferred_telegram_person_key(
                direct=not bool(group_label),
                conversation_ref=str(message.get("conversation_ref") or ""),
                label=actor_label,
                aliases=actor_candidates,
            )
            person = ensure_person(
                actor_label,
                aliases=actor_candidates,
                preferred_key=preferred_key,
            )
            update_profile_entry(
                person,
                channel="telegram",
                occurred_at=str(message.get("sent_at") or ""),
                phones=message_phones,
                handles=[actor_label] if actor_label.startswith("@") else [],
                candidates=actor_candidates,
                sample_text=str(message.get("body") or "").strip(),
                direction=str(message.get("direction") or "").strip(),
            )
            if group_label:
                _append_unique_strings(person["_group_contexts"], [group_label])
        if group_label:
            group = ensure_group(group_label, aliases=[str(message.get("conversation_ref") or "")])
            update_profile_entry(
                group,
                channel="telegram",
                occurred_at=str(message.get("sent_at") or ""),
                candidates=[group_label, str(message.get("conversation_ref") or "")],
                sample_text=str(message.get("body") or "").strip(),
                direction=str(message.get("direction") or "").strip(),
            )

    for message in store.list_x_messages(office_id, limit=max(30, min(limit * 4, 160))):
        actor_label = str(message.get("sender") or message.get("recipient") or message.get("conversation_ref") or "X").strip()
        if not actor_label:
            continue
        message_direction = str(message.get("direction") or "").strip().lower()
        actor_party = str(message.get("recipient") or "").strip() if message_direction == "outbound" else str(message.get("sender") or "").strip()
        actor_candidates = [actor_label, actor_party, str(message.get("conversation_ref") or "")]
        person = ensure_person(actor_label, aliases=actor_candidates)
        update_profile_entry(
            person,
            channel="x",
            occurred_at=str(message.get("sent_at") or ""),
            handles=[actor_label] if actor_label.startswith("@") else [],
            candidates=actor_candidates,
            sample_text=str(message.get("body") or "").strip(),
            direction=str(message.get("direction") or "").strip(),
        )
    for message in store.list_instagram_messages(office_id, limit=max(30, min(limit * 4, 160))):
        actor_label = _instagram_message_actor_label(message)
        if not actor_label:
            continue
        message_direction = str(message.get("direction") or "").strip().lower()
        actor_party = str(message.get("recipient") or "").strip() if message_direction == "outbound" else str(message.get("sender") or "").strip()
        actor_candidates = [
            actor_label,
            actor_party,
            str(message.get("conversation_ref") or ""),
        ]
        person = ensure_person(actor_label, aliases=actor_candidates)
        update_profile_entry(
            person,
            channel="instagram",
            occurred_at=str(message.get("sent_at") or ""),
            handles=[actor_label] if actor_label.startswith("@") else [],
            candidates=actor_candidates,
            sample_text=str(message.get("body") or "").strip(),
            direction=str(message.get("direction") or "").strip(),
        )
    for message in store.list_linkedin_messages(office_id, limit=max(30, min(limit * 4, 160))):
        actor_label = _linkedin_message_actor_label(message)
        if not actor_label:
            continue
        message_direction = str(message.get("direction") or "").strip().lower()
        actor_party = str(message.get("recipient") or "").strip() if message_direction == "outbound" else str(message.get("sender") or "").strip()
        actor_candidates = [
            actor_label,
            actor_party,
            str(message.get("conversation_ref") or ""),
        ]
        person = ensure_person(actor_label, aliases=actor_candidates)
        update_profile_entry(
            person,
            channel="linkedin",
            occurred_at=str(message.get("sent_at") or ""),
            handles=[actor_label] if actor_label.startswith("@") else [],
            candidates=actor_candidates,
            sample_text=str(message.get("body") or "").strip(),
            direction=str(message.get("direction") or "").strip(),
        )

    items = [*people.values(), *groups.values()]
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        active_watch, blocked, blocked_until = _communication_watch_status(
            profile,
            kind=str(item["kind"]),
            channels=list(item["channels"]),
            candidates=list(item["_match_candidates"]),
        )
        relationship_hint = _communication_relationship_hint(
            profile,
            display_name=str(item["display_name"]),
            importance_reason=str(item["_importance_reason"] or ""),
            kind=str(item["kind"]),
            candidates=list(item["_match_candidates"]),
            emails=list(item["emails"]),
            handles=list(item["handles"]),
            samples=list(item["_samples"]),
        )
        normalized_items.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "display_name": item["display_name"],
                "relationship_hint": relationship_hint,
                "persona_summary": _communication_persona_summary(
                    kind=str(item["kind"]),
                    display_name=str(item["display_name"]),
                    channels=list(item["channels"]),
                    importance_reason=str(item["_importance_reason"] or ""),
                    relationship_hint=relationship_hint,
                    emails=list(item["emails"]),
                    handles=list(item["handles"]),
                    candidates=list(item["_match_candidates"]),
                    samples=list(item["_samples"]),
                    source_count=int(item["source_count"]),
                    group_contexts=list(item.get("_group_contexts") or []),
                ),
                "channels": list(item["channels"]),
                "emails": list(item["emails"]),
                "phone_numbers": _sanitize_contact_phone_numbers(
                    list(item["phone_numbers"]),
                    candidates=list(item["_match_candidates"]),
                ),
                "handles": list(item["handles"]),
                "watch_enabled": active_watch,
                "blocked": blocked,
                "blocked_until": blocked_until,
                "last_message_at": item["last_message_at"],
                "source_count": int(item["source_count"]),
                "_importance_reason": str(item["_importance_reason"] or ""),
                "_match_candidates": list(item["_match_candidates"]),
                "_samples": list(item["_samples"]),
                "group_contexts": list(item.get("_group_contexts") or []),
            }
        )
    normalized_items.sort(
        key=lambda item: (
            str(item.get("last_message_at") or ""),
            int(item.get("source_count") or 0),
            str(item.get("display_name") or ""),
        ),
        reverse=True,
    )
    return normalized_items[:limit]


def build_assistant_contact_profiles(store, office_id: str, *, limit: int = 80) -> list[dict[str, Any]]:
    items = _collect_assistant_contact_entries(store, office_id, limit=limit)
    profile = store.get_user_profile(office_id)
    override_lookup = _contact_profile_override_lookup(profile)
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        manual_profile = _related_profile_for_display(profile, str(item.get("display_name") or ""))
        preference_signals, gift_ideas = _contact_preference_signals(item, manual_profile)
        inference_signals = _contact_inference_signals(
            item,
            manual_profile=manual_profile,
            preference_signals=preference_signals,
        )
        recent_preview, recent_channel = _contact_recent_message_preview(item)
        override = override_lookup.get(str(item.get("id") or "").strip())
        generated_persona_detail = _communication_persona_detail(
            item,
            manual_profile=manual_profile,
            preference_signals=preference_signals,
        )
        normalized_items.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "display_name": item["display_name"],
                "relationship_hint": item["relationship_hint"],
                "related_profile_id": str((manual_profile or {}).get("id") or "").strip() or None,
                "closeness": _normalize_related_profile_closeness(
                    (manual_profile or {}).get("closeness"),
                    relationship=str((manual_profile or {}).get("relationship") or item.get("relationship_hint") or ""),
                )
                if manual_profile
                else None,
                "persona_summary": item["persona_summary"],
                "persona_detail": str((override or {}).get("description") or generated_persona_detail).strip() or generated_persona_detail,
                "generated_persona_detail": generated_persona_detail,
                "persona_detail_source": "manual" if override else "generated",
                "persona_detail_updated_at": (override or {}).get("updated_at"),
                "channels": list(item["channels"]),
                "emails": list(item["emails"]),
                "phone_numbers": list(item["phone_numbers"]),
                "handles": list(item["handles"]),
                "watch_enabled": bool(item["watch_enabled"]),
                "blocked": bool(item["blocked"]),
                "blocked_until": item.get("blocked_until"),
                "last_message_at": item.get("last_message_at"),
                "source_count": int(item.get("source_count") or 0),
                "inference_signals": inference_signals,
                "preference_signals": preference_signals,
                "gift_ideas": gift_ideas,
                "channel_summary": _contact_channel_summary(item),
                "last_inbound_preview": recent_preview,
                "last_inbound_channel": recent_channel,
                "group_contexts": list(item.get("group_contexts") or []),
            }
        )
    return normalized_items[:limit]


def build_assistant_agenda(store, office_id: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    for task in store.list_office_tasks(office_id):
        due_at = _parse_dt(task.get("due_at"))
        if task.get("status") == "completed":
            continue
        if due_at and due_at < now:
            items.append(
                {
                    "id": f"task-overdue-{task['id']}",
                    "kind": "overdue_task",
                    "title": f"Geciken görev: {task['title']}",
                    "details": task.get("explanation") or "Bu görev için son tarih geçmiş durumda.",
                    "priority": "high",
                    "due_at": task.get("due_at"),
                    "source_type": "task",
                    "source_ref": str(task["id"]),
                    "matter_id": task.get("matter_id"),
                    "recommended_action_ids": [],
                    "manual_review_required": True,
                }
            )
        elif due_at and due_at <= now + timedelta(days=1):
            items.append(
                {
                    "id": f"task-soon-{task['id']}",
                    "kind": "due_today",
                    "title": f"Bugün takip et: {task['title']}",
                    "details": task.get("explanation") or "Son tarih yaklaşan görev.",
                    "priority": task.get("priority") or "medium",
                    "due_at": task.get("due_at"),
                    "source_type": "task",
                    "source_ref": str(task["id"]),
                    "matter_id": task.get("matter_id"),
                    "recommended_action_ids": [],
                    "manual_review_required": True,
                }
            )

    for event in store.list_calendar_events(office_id, limit=12):
        starts_at = _parse_dt(event.get("starts_at"))
        if starts_at and starts_at <= now + timedelta(days=1):
            items.append(
                {
                    "id": f"calendar-{event['id']}",
                    "kind": "calendar_prep",
                    "title": event["title"],
                    "details": event.get("location") or "Yaklaşan takvim kaydı için hazırlık gerekebilir.",
                    "priority": "medium",
                    "due_at": event.get("starts_at"),
                    "source_type": "calendar_event",
                    "source_ref": event.get("external_id"),
                    "matter_id": event.get("matter_id"),
                    "recommended_action_ids": [],
                    "manual_review_required": True,
                }
            )

    for personal_date in _upcoming_profile_dates(store, office_id, window_days=14):
        priority = "high" if personal_date["days_until"] <= 2 else "medium"
        if personal_date["days_until"] == 0:
            details = personal_date["notes"] or "Bugün dikkat gerektiren kişisel bir tarih var."
        elif personal_date["days_until"] == 1:
            details = personal_date["notes"] or "Yarın yaklaşan kişisel bir tarih var."
        else:
            details = personal_date["notes"] or f"{personal_date['days_until']} gün içinde yaklaşan kişisel bir tarih var."
        items.append(
            {
                "id": personal_date["id"],
                "kind": "personal_date",
                "title": personal_date["label"],
                "details": details,
                "priority": priority,
                "due_at": personal_date["date"],
                "source_type": "user_profile",
                "source_ref": personal_date["label"],
                "matter_id": None,
                "recommended_action_ids": [],
                "manual_review_required": False,
            }
        )

    for draft in store.list_outbound_drafts(office_id):
        approval_status = str(draft.get("approval_status") or "pending_review").strip().lower()
        delivery_status = str(draft.get("delivery_status") or "not_sent").strip().lower()
        if approval_status == "approved" and delivery_status in {"sent", "delivered"}:
            continue
        items.append(
            {
                "id": f"draft-review-{draft['id']}",
                "kind": "draft_review",
                "title": _draft_review_title(draft),
                "details": _draft_review_details(draft),
                "priority": "high" if approval_status != "approved" else "medium",
                "due_at": draft.get("updated_at") or draft.get("created_at"),
                "source_type": "outbound_draft",
                "source_ref": str(draft.get("id") or ""),
                "matter_id": draft.get("matter_id"),
                "recommended_action_ids": [],
                "manual_review_required": True,
            }
        )

    items.extend(_build_today_communication_tasks(build_assistant_inbox(store, office_id)))
    kind_order = {
        "overdue_task": 0,
        "due_today": 1,
        "draft_review": 2,
        "communication_follow_up": 3,
        "calendar_prep": 4,
        "social_alert": 5,
        "social_watch": 6,
        "personal_date": 7,
    }
    items.sort(
        key=lambda item: (
            kind_order.get(str(item.get("kind") or ""), 9),
            {"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority") or "medium"), 1),
            str(item.get("due_at") or ""),
        )
    )
    reserved_personal_dates = [
        item for item in items if str(item.get("kind") or "") == "personal_date"
    ][:3]
    reserved_ids = {str(item.get("id") or "") for item in reserved_personal_dates}
    selected: list[dict[str, Any]] = list(reserved_personal_dates)
    for item in items:
        item_id = str(item.get("id") or "")
        if item_id in reserved_ids:
            continue
        if len(selected) >= 20:
            break
        selected.append(item)
    selected.sort(
        key=lambda item: (
            kind_order.get(str(item.get("kind") or ""), 9),
            {"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority") or "medium"), 1),
            str(item.get("due_at") or ""),
        )
    )
    return selected[:20]


def build_assistant_calendar(store, office_id: str, *, window_days: int = 35) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=max(14, min(window_days, 62)))
    window_end = now + timedelta(days=max(7, min(window_days, 62)))
    items: list[dict[str, Any]] = []

    for event in store.list_calendar_events(office_id, limit=200):
        starts_at = _parse_dt(event.get("starts_at"))
        if not starts_at or starts_at < window_start or starts_at > window_end:
            continue
        ends_at = _parse_dt(event.get("ends_at"))
        items.append(
            {
                "id": f"calendar-{event['id']}",
                "kind": "calendar_event",
                "title": event.get("title") or "Takvim kaydı",
                "details": event.get("location") or "Takvim kaydı",
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat() if ends_at else None,
                "location": event.get("location") or "",
                "source_type": "calendar_event",
                "source_ref": event.get("external_id"),
                "matter_id": event.get("matter_id"),
                "priority": "medium",
                "all_day": "T" not in str(event.get("starts_at") or ""),
                "needs_preparation": bool(event.get("needs_preparation")),
                "provider": event.get("provider") or "lawcopilot-planner",
                "status": event.get("status") or "confirmed",
                "attendees": list(event.get("attendees") or []),
                "metadata": dict(event.get("metadata") or {}),
            }
        )

    for task in store.list_office_tasks(office_id):
        due_at = _parse_dt(task.get("due_at"))
        if task.get("status") == "completed" or not due_at:
            continue
        if due_at < window_start or due_at > window_end:
            continue
        items.append(
            {
                "id": f"task-{task['id']}",
                "kind": "task_due",
                "title": task.get("title") or "Görev",
                "details": task.get("explanation") or "Takvim içine alınmış görev",
                "starts_at": due_at.isoformat(),
                "ends_at": None,
                "location": "",
                "source_type": "task",
                "source_ref": str(task["id"]),
                "matter_id": task.get("matter_id"),
                "priority": task.get("priority") or "medium",
                "all_day": False,
                "needs_preparation": True,
                "provider": "lawcopilot",
                "status": task.get("status") or "open",
                "attendees": [],
                "metadata": {"origin_type": task.get("origin_type")},
            }
        )

    for personal_date in _upcoming_profile_dates(store, office_id, window_days=window_days):
        items.append(
            {
                "id": personal_date["id"],
                "kind": "personal_date",
                "title": personal_date["label"],
                "details": personal_date["notes"] or "Kullanıcı profilinde tanımlı önemli tarih",
                "starts_at": f"{personal_date['date']}T09:00:00+00:00",
                "ends_at": None,
                "location": "",
                "source_type": "user_profile",
                "source_ref": personal_date["label"],
                "matter_id": None,
                "priority": "medium",
                "all_day": True,
                "needs_preparation": personal_date["days_until"] <= 7,
                "provider": "user-profile",
                "status": "confirmed",
                "attendees": [],
                "metadata": {
                    "days_until": personal_date["days_until"],
                    "recurring_annually": personal_date["recurring_annually"],
                },
            }
        )

    items.sort(key=lambda item: (str(item.get("starts_at") or ""), str(item.get("title") or "")))
    return items


ASSISTANT_HOME_PRIORITY_ITEM_LIMIT = 4
ASSISTANT_HOME_SUMMARY_SENTENCE_LIMIT = 3
ASSISTANT_HOME_IMMINENT_CALENDAR_HOURS = 18


def _agenda_item_sort_key(item: dict[str, Any]) -> tuple[int, int, float, str]:
    kind_order = {
        "overdue_task": 0,
        "social_alert": 1,
        "due_today": 2,
        "communication_follow_up": 3,
        "draft_review": 4,
        "calendar_prep": 5,
        "personal_date": 6,
        "social_watch": 7,
    }
    priority_order = {"high": 0, "medium": 1, "low": 2}
    due_at = _parse_dt(item.get("due_at"))
    due_key = due_at.timestamp() if due_at else float("inf")
    return (
        kind_order.get(str(item.get("kind") or ""), 9),
        priority_order.get(str(item.get("priority") or "medium"), 1),
        due_key,
        str(item.get("title") or ""),
    )


def _assistant_home_priority_budget(kind: str) -> int:
    return {
        "overdue_task": 2,
        "due_today": 2,
        "communication_follow_up": 2,
        "draft_review": 1,
        "calendar_prep": 1,
        "social_alert": 1,
        "social_watch": 1,
        "personal_date": 1,
    }.get(kind, 1)


def _is_home_urgent_agenda_item(item: dict[str, Any], *, now: datetime) -> bool:
    kind = str(item.get("kind") or "").strip()
    due_at = _parse_dt(item.get("due_at"))
    if kind in {"overdue_task", "social_alert", "due_today", "communication_follow_up", "draft_review"}:
        return True
    if kind == "calendar_prep" and due_at:
        return due_at <= now + timedelta(hours=ASSISTANT_HOME_IMMINENT_CALENDAR_HOURS)
    if kind == "personal_date" and due_at:
        return due_at.date() <= (now + timedelta(days=1)).date()
    return False


def _is_home_supportive_agenda_item(item: dict[str, Any], *, now: datetime) -> bool:
    if _is_home_urgent_agenda_item(item, now=now):
        return False
    kind = str(item.get("kind") or "").strip()
    due_at = _parse_dt(item.get("due_at"))
    if kind in {"social_watch"}:
        return True
    if kind == "calendar_prep" and due_at:
        return due_at <= now + timedelta(days=2)
    if kind == "personal_date" and due_at:
        return due_at.date() <= (now + timedelta(days=2)).date()
    return False


def _select_assistant_home_priority_items(agenda: list[dict[str, Any]], *, now: datetime) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    kind_counts: dict[str, int] = {}

    def _append_candidates(candidates: list[dict[str, Any]]) -> None:
        for item in sorted(candidates, key=_agenda_item_sort_key):
            if len(selected) >= ASSISTANT_HOME_PRIORITY_ITEM_LIMIT:
                return
            item_id = str(item.get("id") or "").strip()
            if item_id and item_id in seen_ids:
                continue
            kind = str(item.get("kind") or "").strip()
            if kind_counts.get(kind, 0) >= _assistant_home_priority_budget(kind):
                continue
            selected.append(item)
            if item_id:
                seen_ids.add(item_id)
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

    urgent_items = [item for item in agenda if _is_home_urgent_agenda_item(item, now=now)]
    supportive_items = [item for item in agenda if _is_home_supportive_agenda_item(item, now=now)]

    _append_candidates(urgent_items)
    if len(selected) < ASSISTANT_HOME_PRIORITY_ITEM_LIMIT:
        _append_candidates(supportive_items)
    return selected[:ASSISTANT_HOME_PRIORITY_ITEM_LIMIT]


def _assistant_home_priority_payload(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in items:
        payload.append(
            {
                "id": item["id"],
                "title": item["title"],
                "details": item.get("details") or "",
                "kind": item.get("kind") or "agenda",
                "priority": item.get("priority") or "medium",
                "due_at": item.get("due_at"),
                "source_type": item.get("source_type") or "assistant",
                "source_ref": item.get("source_ref"),
            }
        )
    return payload


def _assistant_home_first_calendar_focus(calendar: list[dict[str, Any]], *, now: datetime) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for item in calendar:
        starts_at = _parse_dt(item.get("starts_at"))
        if not starts_at:
            continue
        if starts_at < now:
            continue
        if starts_at > now + timedelta(days=1):
            continue
        candidates.append(item)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            _parse_dt(item.get("starts_at")) or (now + timedelta(days=365)),
            str(item.get("title") or ""),
        ),
    )[0]


def _build_assistant_home_summary(
    *,
    agenda: list[dict[str, Any]],
    priority_items: list[dict[str, Any]],
    calendar: list[dict[str, Any]],
    drafts_pending_count: int,
    actionable_communications: int,
    social_alert_count: int,
    social_watch_count: int,
    calendar_today_count: int,
    proactive_suggestions: list[dict[str, Any]],
    location_label: str,
    prayer_notifications_enabled: bool,
    now: datetime,
) -> str:
    overdue_count = len([item for item in agenda if str(item.get("kind") or "") == "overdue_task"])
    due_today_count = len([item for item in agenda if str(item.get("kind") or "") == "due_today"])
    personal_date_count = len(
        [
            item
            for item in agenda
            if str(item.get("kind") or "") == "personal_date"
            and (_parse_dt(item.get("due_at")) or now).date() <= (now + timedelta(days=1)).date()
        ]
    )
    strongest_kinds = {
        "overdue_task",
        "social_alert",
        "due_today",
        "communication_follow_up",
        "draft_review",
    }
    strong_item_count = len(
        [item for item in priority_items if str(item.get("kind") or "") in strongest_kinds]
    )
    lines: list[str] = []
    if priority_items:
        if strong_item_count:
            lines.append(f"Bugün için {len(priority_items)} öncelikli başlık öne çıkıyor.")
        else:
            lines.append(f"Bugün için {len(priority_items)} takip başlığı öne çıkıyor.")
        if strong_item_count <= 1:
            lines.append(f"İlk odak: {priority_items[0]['title']}.")
    elif proactive_suggestions:
        lines.append("Bugün için belirgin bir acil iş görünmüyor; birkaç hazırlık önerisi çıkardım.")
    else:
        lines.append("Bugün için belirgin bir acil iş görünmüyor.")

    detail_candidates: list[str] = []
    if overdue_count:
        detail_candidates.append(
            f"Önce {overdue_count} geciken görevi toparlamak iyi olur."
        )
    if social_alert_count:
        detail_candidates.append(
            f"Sosyal akışta {social_alert_count} dikkat gerektiren hukukî risk sinyali var."
        )
    if actionable_communications:
        detail_candidates.append(
            f"Bugün {actionable_communications} iletişim konusu yanıt bekliyor."
        )
    if due_today_count and not overdue_count:
        detail_candidates.append(
            f"Takvim ve görevlerde {due_today_count} yakın teslim başlığı var."
        )
    if drafts_pending_count and strong_item_count <= 1:
        detail_candidates.append(f"{drafts_pending_count} taslak son gözden geçirmeyi bekliyor.")
    if calendar_today_count:
        detail_candidates.append(f"Bugün takvimde {calendar_today_count} kayıt var.")
    else:
        first_event = _assistant_home_first_calendar_focus(calendar, now=now)
        if first_event and strong_item_count == 0:
            first_event_dt = _parse_dt(first_event.get("starts_at"))
            first_event_label = _format_turkish_day_label(first_event_dt)
            first_event_time = _format_time_window(first_event_dt, None)
            detail_candidates.append(
                f"Yaklaşan ilk kayıt: {first_event.get('title') or 'takvim kaydı'} ({first_event_label}, {first_event_time})."
            )
    if personal_date_count and strong_item_count == 0:
        detail_candidates.append(
            f"Yakın çevre veya kişisel tarafta {personal_date_count} önemli tarih yaklaşıyor."
        )
    if social_watch_count and not social_alert_count and strong_item_count == 0:
        detail_candidates.append(
            f"Sosyal akışta {social_watch_count} izleme gerektiren geri bildirim var."
        )

    weather_suggestion = next(
        (
            item
            for item in proactive_suggestions
            if str(item.get("kind") or "").strip() in {"weather_preparation", "weather_trip_watch"}
        ),
        None,
    )
    weather_summary_line = str(weather_suggestion.get("summary_line") or "").strip() if weather_suggestion else ""
    if weather_summary_line and strong_item_count == 0:
        detail_candidates.append(weather_summary_line)

    has_location_dependent_suggestion = any(
        str(item.get("kind") or "").strip() in {"weather_preparation", "weather_trip_watch", "route_planning", "nearby_discovery"}
        for item in proactive_suggestions
    )
    if location_label and has_location_dependent_suggestion and strong_item_count == 0:
        detail_candidates.append(f"Konum bağlamı {location_label} üzerinden rota ve çevre önerilerini hazırladım.")
    if prayer_notifications_enabled and strong_item_count == 0:
        detail_candidates.append("Namaz vakti ve yakın cami desteği açık.")

    for candidate in detail_candidates:
        normalized = str(candidate or "").strip()
        if not normalized or normalized in lines:
            continue
        if len(lines) >= ASSISTANT_HOME_SUMMARY_SENTENCE_LIMIT:
            break
        lines.append(normalized)
    return " ".join(lines)


def build_assistant_home(store, office_id: str, *, settings=None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    agenda = build_assistant_agenda(store, office_id)
    inbox = build_assistant_inbox(store, office_id)
    calendar = build_assistant_calendar(store, office_id, window_days=7)
    drafts = store.list_outbound_drafts(office_id)
    connected_accounts = store.list_connected_accounts(office_id)
    profile = store.get_user_profile(office_id)
    full_contact_directory = build_assistant_contact_profiles(store, office_id, limit=80)
    contact_directory = full_contact_directory
    relationship_profiles = build_assistant_relationship_profiles(store, office_id, limit=6)
    display_name = _profile_display_name(profile)
    related_profiles = _related_profiles(profile)
    location_label = _profile_location_label(profile)
    prayer_notifications_enabled = bool(profile.get("prayer_notifications_enabled"))
    proactive_suggestions = _build_proactive_suggestions(
        store,
        office_id,
        profile=profile,
        inbox=inbox,
        calendar=calendar,
        relationship_profiles=relationship_profiles,
    )
    social_alert_count = len([item for item in agenda if str(item.get("kind") or "") == "social_alert"])
    social_watch_count = len([item for item in agenda if str(item.get("kind") or "") == "social_watch"])
    actionable_communications = len([item for item in agenda if str(item.get("kind") or "") == "communication_follow_up"])
    drafts_pending_count = len([item for item in drafts if item.get("approval_status") != "approved"])
    today_key = now.date().isoformat()
    calendar_today_count = len(
        [
            item
            for item in calendar
            if str(item.get("starts_at") or "").startswith(today_key)
        ]
    )

    priority_items = _assistant_home_priority_payload(
        _select_assistant_home_priority_items(agenda, now=now)
    )

    requires_setup: list[dict[str, Any]] = []
    if settings is not None:
        onboarding = build_assistant_onboarding(store, settings, office_id)
        for step in onboarding["steps"]:
            if step["complete"]:
                continue
            if step["id"] not in {"workspace", "provider"}:
                continue
            requires_setup.append(
                {
                    "id": f"setup-{step['id']}",
                    "title": step["title"],
                    "details": step["description"],
                    "action": "open_onboarding",
                }
            )

    today_summary = _build_assistant_home_summary(
        agenda=agenda,
        priority_items=priority_items,
        calendar=calendar,
        drafts_pending_count=drafts_pending_count,
        actionable_communications=actionable_communications,
        social_alert_count=social_alert_count,
        social_watch_count=social_watch_count,
        calendar_today_count=calendar_today_count,
        proactive_suggestions=proactive_suggestions,
        location_label=location_label,
        prayer_notifications_enabled=prayer_notifications_enabled,
        now=now,
    )

    greeting_message = (
        f"{display_name}, bugünün önceliklerini toparladım."
        if display_name
        else "Bugünün önceliklerini toparladım."
    )
    if social_alert_count:
        greeting_message = f"{greeting_message} Sosyal akışta dikkat gerektiren bir risk sinyali de var."

    contact_channel_counts: dict[str, int] = {}
    for item in full_contact_directory:
        for channel in item.get("channels") or []:
            normalized = str(channel or "").strip().lower()
            if not normalized:
                continue
            contact_channel_counts[normalized] = contact_channel_counts.get(normalized, 0) + 1

    return {
        "today_summary": today_summary,
        "display_name": display_name,
        "greeting_title": f"Selam {display_name}" if display_name else "Selam",
        "greeting_message": greeting_message,
        "counts": {
            "agenda": len(agenda),
            "inbox": actionable_communications,
            "drafts_pending": drafts_pending_count,
            "calendar_today": calendar_today_count,
        },
        "priority_items": priority_items,
        "proactive_suggestions": proactive_suggestions,
        "requires_setup": requires_setup,
        "connected_accounts": connected_accounts,
        "relationship_profiles": relationship_profiles,
        "contact_directory": contact_directory,
        "contact_directory_summary": {
            "total_accounts": len(full_contact_directory),
            "priority_profiles": len(relationship_profiles),
            "blocked_accounts": len([item for item in full_contact_directory if item.get("blocked")]),
            "watch_enabled_accounts": len([item for item in full_contact_directory if item.get("watch_enabled")]),
            "channels": contact_channel_counts,
        },
        "generated_from": "assistant_home_engine",
    }


def _risk_action_title(matter_title: str, risk_item: dict[str, Any]) -> str:
    if risk_item.get("category") == "missing_document":
        return f"{matter_title} için eksik belge talebi hazırla"
    if risk_item.get("category") == "deadline":
        return f"{matter_title} için son tarih takibini netleştir"
    return f"{matter_title} için çalışma notu hazırla"


def build_suggested_actions(store, office_id: str, *, created_by: str) -> list[dict[str, Any]]:
    existing = store.list_assistant_actions(office_id, status="suggested", limit=20)
    if existing:
        return existing

    matters = store.list_matters(office_id)[:5]
    created: list[dict[str, Any]] = []
    for matter in matters:
        tasks = store.list_matter_tasks(office_id, int(matter["id"])) or []
        open_tasks = [task for task in tasks if task.get("status") != "completed"]
        if open_tasks:
            execution = evaluate_execution_gateway(
                action_kind="prepare_client_update",
                risk_level="B",
                requires_confirmation=True,
                tool_class="write",
                scope="professional",
                suggest_only=True,
                reversible=True,
                current_stage="suggest",
                preview_summary=f"{matter['title']} için müvekkil güncellemesi",
                audit_label="assistant_suggested_action",
            )
            draft = store.create_outbound_draft(
                office_id,
                matter_id=int(matter["id"]),
                draft_type="client_update",
                channel="email",
                to_contact=matter.get("client_name") or "",
                subject=f"{matter['title']} için durum güncellemesi",
                body=(
                    f"Merhaba,\n\n{matter['title']} dosyasında şu an öne çıkan başlıklar:\n"
                    + "\n".join(f"- {task['title']}" for task in open_tasks[:3])
                    + "\n\nUygun görürseniz bu güncellemeyi gözden geçirip gönderebiliriz."
                ),
                source_context={"open_tasks": [task["title"] for task in open_tasks[:5]], "documents": []},
                generated_from="assistant_agenda_engine",
                created_by=created_by,
                approval_status="pending_review" if execution.policy_decision.preview_required else "approved",
                delivery_status="not_sent",
            )
            created.append(
                store.create_assistant_action(
                    office_id,
                    matter_id=int(matter["id"]),
                    action_type="prepare_client_update",
                    title=f"{matter['title']} için müvekkil güncellemesi hazırla",
                    description="Açık görev ve yaklaşan işler üzerinden müvekkil güncellemesi önerildi.",
                    rationale=(
                        "Dosyada açık görevler bulundu; müvekkile kısa durum özeti göndermek faydalı olabilir. "
                        f"{execution.policy_decision.reason_summary}"
                    ),
                    source_refs=[{"type": "task", "title": task["title"], "id": task["id"]} for task in open_tasks[:3]],
                    target_channel="email",
                    draft_id=int(draft["id"]),
                    status="suggested",
                    manual_review_required=execution.policy_decision.manual_review_required,
                    created_by=created_by,
                )
            )

        workflow_context = {
            "matter": matter,
            "notes": store.list_matter_notes(office_id, int(matter["id"])) or [],
            "documents": (store.list_matter_documents(office_id, int(matter["id"])) or [])
            + (store.list_matter_workspace_documents(office_id, int(matter["id"])) or []),
            "chunks": (store.search_document_chunks(office_id, int(matter["id"])) or [])
            + (store.search_linked_workspace_chunks(office_id, int(matter["id"])) or []),
            "tasks": tasks,
            "timeline": store.list_matter_timeline(office_id, int(matter["id"])) or [],
            "draft_events": store.list_matter_draft_events(office_id, int(matter["id"])) or [],
            "ingestion_jobs": store.list_matter_ingestion_jobs(office_id, int(matter["id"])) or [],
            "workspace_documents": store.list_matter_workspace_documents(office_id, int(matter["id"])) or [],
            "workspace_chunks": store.search_linked_workspace_chunks(office_id, int(matter["id"])) or [],
        }
        chronology = build_chronology(
            matter=matter,
            notes=workflow_context["notes"],
            chunks=workflow_context["chunks"],
            tasks=tasks,
        )
        risk_notes = build_risk_notes(
            matter=matter,
            documents=workflow_context["documents"],
            notes=workflow_context["notes"],
            tasks=tasks,
            chronology=chronology,
            chunks=workflow_context["chunks"],
        )
        if risk_notes.get("items"):
            top_item = risk_notes["items"][0]
            execution = evaluate_execution_gateway(
                action_kind="send_email",
                risk_level="C" if top_item.get("category") == "missing_document" else "B",
                requires_confirmation=True,
                tool_class="write",
                scope="professional",
                suggest_only=True,
                reversible=True,
                current_stage="suggest",
                preview_summary=_risk_action_title(matter["title"], top_item),
                audit_label="assistant_risk_action",
            )
            draft = store.create_outbound_draft(
                office_id,
                matter_id=int(matter["id"]),
                draft_type="missing_document_request" if top_item.get("category") == "missing_document" else "internal_summary",
                channel="email",
                to_contact=matter.get("client_name") or "",
                subject=_risk_action_title(matter["title"], top_item),
                body=f"{top_item['title']}\n\n{top_item['details']}",
                source_context={"risk_notes": [item["title"] for item in risk_notes["items"][:4]]},
                generated_from="assistant_risk_engine",
                created_by=created_by,
                approval_status="pending_review" if execution.policy_decision.preview_required else "approved",
                delivery_status="not_sent",
            )
            created.append(
                store.create_assistant_action(
                    office_id,
                    matter_id=int(matter["id"]),
                    action_type="send_email",
                    title=_risk_action_title(matter["title"], top_item),
                    description=top_item["details"],
                    rationale=(
                        "Risk ve eksik belge sinyalleri nedeniyle taslak aksiyon önerildi. "
                        f"{execution.policy_decision.reason_summary}"
                    ),
                    source_refs=[{"type": "risk_note", "title": item["title"]} for item in risk_notes["items"][:3]],
                    target_channel="email",
                    draft_id=int(draft["id"]),
                    status="suggested",
                    manual_review_required=execution.policy_decision.manual_review_required,
                    created_by=created_by,
                )
            )
    return created or existing
