from __future__ import annotations

import re
from typing import Any


def _normalize(value: str) -> str:
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


def _clean_sentence(value: str, *, limit: int = 220) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    return cleaned[:limit]


def _append_note(existing: str | None, note: str) -> str:
    cleaned = _clean_sentence(note, limit=260)
    if not cleaned:
        return str(existing or "").strip()
    current = str(existing or "").strip()
    lowered = _normalize(current)
    if _normalize(cleaned) in lowered:
        return current
    if current:
        return f"{current}\n- {cleaned}"
    return f"- {cleaned}"


def _extract_match(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        value = _clean_sentence(match.group(1), limit=120).strip(" .,:;!?")
        if value:
            return value
    return None


DISPLAY_NAME_PATTERNS = [
    re.compile(r"\b(?:benim ad[ıi]m|ad[ıi]m|isim(?:im)?)[: ]+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{1,40})", re.IGNORECASE),
    re.compile(r"\bbana\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{1,40})\s+diye\s+hitap\s+et", re.IGNORECASE),
]
ASSISTANT_NAME_PATTERNS = [
    re.compile(r"\b(?:senin ad[ıi]n|ad[ıi]n)\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{1,40})\s+olsun", re.IGNORECASE),
    re.compile(r"\bsana\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{1,40})\s+diyeyim", re.IGNORECASE),
]
FAVORITE_COLOR_PATTERNS = [
    re.compile(r"\b(?:en sevdi(?:ğ|g)im renk|favori rengim)[: ]+([A-Za-zÇĞİÖŞÜçğıöşü -]{2,40})", re.IGNORECASE),
    re.compile(r"\b([A-Za-zÇĞİÖŞÜçğıöşü -]{2,40})\s+rengini\s+severim", re.IGNORECASE),
]
USER_DIRECTION_MARKERS = ("bana", "cevap", "yanit", "özet", "konus", "anlat", "iletisim", "hitap")
ASSISTANT_DIRECTION_MARKERS = ("sen ", "asistan", "cevaplarin", "yanitlarin", "tonun", "karakterin", "kisiligin")
TONE_KEYWORDS = [
    ("sakaci", "Şakacı"),
    ("samimi", "Samimi"),
    ("sicak", "Sıcak"),
    ("resmi", "Resmi"),
    ("profesyonel", "Profesyonel"),
    ("kisa", "Kısa"),
    ("detayli", "Detaylı"),
    ("direkt", "Direkt"),
    ("yaratici", "Yaratıcı"),
]
ROLE_HINTS = (
    "hukuk asistani",
    "kisisel asistan",
    "yol arkadasi",
    "calisma asistani",
    "koordinator",
)


class MemoryService:
    def __init__(self, store, office_id: str) -> None:
        self.store = store
        self.office_id = office_id

    def capture_chat_signal(self, query: str) -> list[dict[str, Any]]:
        text = _clean_sentence(query, limit=1200)
        if not text:
            return []

        profile = self.store.get_user_profile(self.office_id)
        runtime_profile = self.store.get_assistant_runtime_profile(self.office_id)
        updates: list[dict[str, Any]] = []

        profile_patch = self._extract_user_profile_patch(text, profile)
        runtime_patch = self._extract_assistant_profile_patch(text, runtime_profile)

        if profile_patch:
            saved_profile = self.store.upsert_user_profile(self.office_id, **profile_patch)
            changed_fields = [field for field in profile_patch.keys() if field != "important_dates"]
            updates.append(
                {
                    "kind": "profile_signal",
                    "status": "stored",
                    "summary": "Kullanıcıya ait yeni tercih bilgisi profile eklendi.",
                    "fields": changed_fields,
                    "updated_at": saved_profile.get("updated_at"),
                }
            )
            profile = saved_profile

        if runtime_patch:
            saved_runtime = self.store.upsert_assistant_runtime_profile(self.office_id, **runtime_patch)
            changed_fields = [field for field in runtime_patch.keys() if field != "heartbeat_extra_checks"]
            updates.append(
                {
                    "kind": "assistant_persona_signal",
                    "status": "stored",
                    "summary": "Asistan kimliği veya konuşma tarzı güncellendi.",
                    "fields": changed_fields,
                    "updated_at": saved_runtime.get("updated_at"),
                }
            )
            runtime_profile = saved_runtime

        if not updates:
            fallback_note = self._extract_fallback_profile_note(text, profile)
            if fallback_note:
                saved_profile = self.store.upsert_user_profile(
                    self.office_id,
                    display_name=profile.get("display_name"),
                    favorite_color=profile.get("favorite_color"),
                    food_preferences=profile.get("food_preferences"),
                    transport_preference=profile.get("transport_preference"),
                    weather_preference=profile.get("weather_preference"),
                    travel_preferences=profile.get("travel_preferences"),
                    communication_style=profile.get("communication_style"),
                    assistant_notes=_append_note(profile.get("assistant_notes"), fallback_note),
                    important_dates=profile.get("important_dates") or [],
                )
                updates.append(
                    {
                        "kind": "profile_signal",
                        "status": "stored",
                        "summary": "Kullanıcı tercihi serbest profil notuna eklendi.",
                        "fields": ["assistant_notes"],
                        "updated_at": saved_profile.get("updated_at"),
                    }
                )

        return updates

    def _extract_user_profile_patch(self, text: str, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize(text)
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
        }
        changed = False

        display_name = _extract_match(DISPLAY_NAME_PATTERNS, text)
        if display_name and display_name != patch["display_name"]:
            patch["display_name"] = display_name
            changed = True

        favorite_color = _extract_match(FAVORITE_COLOR_PATTERNS, text)
        if favorite_color and favorite_color != patch["favorite_color"]:
            patch["favorite_color"] = favorite_color
            changed = True

        if any(keyword in normalized for keyword in ("tren", "metro", "ucak", "uçak", "araba", "otobus", "otobüs", "taksi", "bisiklet", "vapur")) and any(
            marker in normalized for marker in ("tercih ederim", "tercih ediyorum", "genelde", "mümkünse", "mumkunse", "ulasim", "ulaşım")
        ):
            candidate = _clean_sentence(text)
            if candidate and candidate != patch["transport_preference"]:
                patch["transport_preference"] = candidate
                changed = True

        if any(keyword in normalized for keyword in ("hava", "gunesli", "güneşli", "serin", "soguk", "soğuk", "ilik", "ılık", "yagmurlu", "yağmurlu")) and any(
            marker in normalized for marker in ("severim", "hoslanirim", "hoşlanırım", "tercih ederim", "tercihim")
        ):
            candidate = _clean_sentence(text)
            if candidate and candidate != patch["weather_preference"]:
                patch["weather_preference"] = candidate
                changed = True

        if any(keyword in normalized for keyword in ("kahve", "cay", "çay", "vegan", "vejetaryen", "pizza", "burger", "tatli", "tatlı", "yemek", "yeme icme", "yeme içme")) and any(
            marker in normalized for marker in ("severim", "sevmem", "tercih ederim", "hoslanirim", "hoşlanırım", "kacinirim", "kaçınırım")
        ):
            candidate = _clean_sentence(text)
            if candidate and candidate != patch["food_preferences"]:
                patch["food_preferences"] = candidate
                changed = True

        if any(keyword in normalized for keyword in ("seyahat", "otel", "ucus", "uçuş", "bilet", "pencere", "konaklama")) and any(
            marker in normalized for marker in ("tercih ederim", "isterim", "seviyorum", "severim", "notum", "genelde")
        ):
            candidate = _clean_sentence(text)
            if candidate and candidate != patch["travel_preferences"]:
                patch["travel_preferences"] = candidate
                changed = True

        if any(keyword in normalized for keyword in ("kisa", "kısa", "detayli", "resmi", "samimi", "direkt", "net")) and any(
            marker in normalized for marker in USER_DIRECTION_MARKERS
        ):
            candidate = _clean_sentence(text)
            if candidate and candidate != patch["communication_style"]:
                patch["communication_style"] = candidate
                changed = True

        if any(marker in normalized for marker in ("ben", "bana", "benim", "hoslanirim", "hoşlanırım", "tercih ederim", "severim")):
            note_value = self._extract_fallback_profile_note(text, profile)
            if note_value:
                next_notes = _append_note(str(patch["assistant_notes"] or ""), note_value)
                if next_notes != patch["assistant_notes"]:
                    patch["assistant_notes"] = next_notes
                    changed = True

        return patch if changed else {}

    def _extract_assistant_profile_patch(self, text: str, runtime_profile: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize(text)
        patch = {
            "assistant_name": runtime_profile.get("assistant_name"),
            "role_summary": runtime_profile.get("role_summary"),
            "tone": runtime_profile.get("tone"),
            "avatar_path": runtime_profile.get("avatar_path"),
            "soul_notes": runtime_profile.get("soul_notes"),
            "tools_notes": runtime_profile.get("tools_notes"),
            "heartbeat_extra_checks": runtime_profile.get("heartbeat_extra_checks") or [],
        }
        changed = False

        assistant_name = _extract_match(ASSISTANT_NAME_PATTERNS, text)
        if assistant_name and assistant_name != patch["assistant_name"]:
            patch["assistant_name"] = assistant_name
            changed = True

        if any(marker in normalized for marker in ASSISTANT_DIRECTION_MARKERS):
            tone_labels = [label for keyword, label in TONE_KEYWORDS if keyword in normalized]
            if tone_labels:
                next_tone = ", ".join(dict.fromkeys(tone_labels))
                if next_tone != patch["tone"]:
                    patch["tone"] = next_tone
                    changed = True

            if any(hint in normalized for hint in ROLE_HINTS):
                candidate = _clean_sentence(text, limit=240)
                if candidate and candidate != patch["role_summary"]:
                    patch["role_summary"] = candidate
                    changed = True

            next_soul_notes = _append_note(str(patch["soul_notes"] or ""), text)
            if next_soul_notes != patch["soul_notes"]:
                patch["soul_notes"] = next_soul_notes
                changed = True

        return patch if changed else {}

    def _extract_fallback_profile_note(self, text: str, profile: dict[str, Any]) -> str | None:
        normalized = _normalize(text)
        if not any(marker in normalized for marker in ("tercih", "severim", "sevmem", "genelde", "hoslanirim", "hoşlanırım", "istemem")):
            return None
        existing_notes = str((profile or {}).get("assistant_notes") or "").strip()
        if _normalize(text) in _normalize(existing_notes):
            return None
        return text
