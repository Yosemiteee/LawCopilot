from __future__ import annotations

import re
from typing import Any

from ..assistant_core import apply_assistant_core_update
from ..preference_rules import extract_source_preference_rules_from_text
from ..persona_text import (
    ASSISTANT_DIRECTION_MARKERS,
    ASSISTANT_NAME_PATTERNS,
    DISPLAY_NAME_PATTERNS,
    FAVORITE_COLOR_PATTERNS,
    ROLE_HINTS,
    TONE_KEYWORDS,
    USER_DIRECTION_MARKERS,
    append_unique_note,
    clean_persona_text,
    compact_assistant_profile_value,
    compact_user_profile_value,
    contains_normalized_phrase,
    extract_match,
    merge_assistant_tone,
    merge_profile_memory_note,
    normalize_profile_memory_notes,
    normalize_persona_text,
    summarize_user_support_note,
)

RELATED_PROFILE_HINTS: dict[str, dict[str, str | tuple[str, ...]]] = {
    "anne": {
        "id": "mother",
        "name": "Anne",
        "relationship": "anne",
        "aliases": ("anne", "annem", "anam"),
        "autocreate_aliases": ("annem", "anam"),
    },
    "baba": {
        "id": "father",
        "name": "Baba",
        "relationship": "baba",
        "aliases": ("baba", "babam"),
        "autocreate_aliases": ("babam",),
    },
    "es": {
        "id": "partner",
        "name": "Eş",
        "relationship": "eş",
        "aliases": ("eş", "esim", "eşim", "partner", "karim", "kocam"),
        "autocreate_aliases": ("esim", "eşim", "karim", "kocam"),
    },
    "sevgili": {
        "id": "partner",
        "name": "Sevgili",
        "relationship": "sevgili",
        "aliases": ("sevgili", "sevgilim", "kiz arkadasim", "kız arkadaşım", "erkek arkadasim", "erkek arkadaşım"),
        "autocreate_aliases": ("sevgilim", "kiz arkadasim", "kız arkadaşım", "erkek arkadasim", "erkek arkadaşım"),
    },
    "kardes": {
        "id": "sibling",
        "name": "Kardeş",
        "relationship": "kardeş",
        "aliases": ("kardes", "kardeş", "kardesim", "kardeşim", "ablam", "abim"),
        "autocreate_aliases": ("kardesim", "kardeşim", "ablam", "abim"),
    },
    "cocuk": {
        "id": "child",
        "name": "Çocuk",
        "relationship": "çocuk",
        "aliases": ("oglum", "oğlum", "kizim", "kızım", "cocugum", "çocuğum"),
        "autocreate_aliases": ("oglum", "oğlum", "kizim", "kızım", "cocugum", "çocuğum"),
    },
    "arkadas": {
        "id": "friend",
        "name": "Arkadaş",
        "relationship": "arkadaş",
        "aliases": ("arkadas", "arkadaş", "arkadasim", "arkadaşım", "dostum"),
        "autocreate_aliases": ("arkadasim", "arkadaşım", "dostum"),
    },
    "avukat": {
        "id": "lawyer",
        "name": "Avukat",
        "relationship": "avukat",
        "aliases": ("avukat", "avukatim", "avukatım", "hukukcum", "hukukçum"),
        "autocreate_aliases": ("avukatim", "avukatım", "hukukcum", "hukukçum"),
    },
    "muvekkil": {
        "id": "client",
        "name": "Müvekkil",
        "relationship": "müvekkil",
        "aliases": ("muvekkil", "muvekkilim", "müvekkilim", "musterim", "müşterim"),
        "autocreate_aliases": ("muvekkilim", "müvekkilim", "musterim", "müşterim"),
    },
    "doktor": {
        "id": "doctor",
        "name": "Doktor",
        "relationship": "doktor",
        "aliases": ("doktor", "doktorum", "hekimim"),
        "autocreate_aliases": ("doktorum", "hekimim"),
    },
}
RELATED_PROFILE_STYLE_SIGNAL_MAP: dict[str, tuple[str, ...]] = {
    "warm": ("sicak", "sıcak", "samimi", "icten", "içten", "sefkatli", "şefkatli"),
    "polite": ("nazik", "kibar", "ince", "saygili", "saygılı"),
    "formal": ("resmi", "profesyonel", "kurumsal", "mesafeli"),
    "concise": ("kisa", "kısa", "net", "ozet", "özet"),
    "detailed": ("detayli", "detaylı", "ayrintili", "ayrıntılı", "gerekceli", "gerekçeli"),
}
RELATED_PROFILE_ITEM_SIGNAL_MAP: dict[str, tuple[str, ...]] = {
    "cikolata": ("cikolata", "çikolata"),
    "cicek": ("cicek", "çiçek"),
    "kitap": ("kitap",),
    "kahve": ("kahve",),
    "tatli": ("tatli", "tatlı"),
    "yemek": ("yemek",),
}
RELATED_PROFILE_NEGATION_HINTS = (
    "sevmez",
    "sevmiyor",
    "istemez",
    "istemiyor",
    "hoslanmaz",
    "hoşlanmaz",
    "kacinir",
    "kaçınır",
    "uygun degil",
    "uygun değil",
)
RELATED_PROFILE_PREFERENCE_HINTS = (
    "sever",
    "seviyor",
    "tercih eder",
    "tercih ediyor",
    "hoslanir",
    "hoşlanır",
    "ister",
    "istiyor",
)
RELATED_PROFILE_COMMUNICATION_HINTS = (
    "mesaj",
    "yaz",
    "yazi",
    "yazı",
    "yazilari",
    "yazıları",
    "dil",
    "uslup",
    "üslup",
    "ton",
    "hitap",
    "konus",
    "konuş",
)


class MemoryService:
    def __init__(self, store, office_id: str, knowledge_base=None, memory_mutations=None) -> None:
        self.store = store
        self.office_id = office_id
        self.knowledge_base = knowledge_base
        self.memory_mutations = memory_mutations

    def capture_chat_signal(self, query: str) -> list[dict[str, Any]]:
        text = clean_persona_text(query, limit=1200)
        if not text:
            return []

        profile = self.store.get_user_profile(self.office_id)
        runtime_profile = self.store.get_assistant_runtime_profile(self.office_id)
        updates: list[dict[str, Any]] = []

        profile_patch = self._extract_user_profile_patch(text, profile)
        runtime_patch = self._extract_assistant_profile_patch(text, runtime_profile)

        if profile_patch:
            saved_profile = self.store.upsert_user_profile(self.office_id, **profile_patch)
            profile_reconciliation = self._reconcile_profile(saved_profile, reason="chat_profile_signal")
            changed_fields = self._changed_fields(profile_patch, profile, ignored_fields={"important_dates"})
            if changed_fields:
                updates.append(
                    {
                        "kind": "profile_signal",
                        "status": "stored",
                        "summary": self._memory_update_summary("profile_signal", changed_fields),
                        "fields": changed_fields,
                        "route": self._settings_route_for_update("profile_signal", changed_fields),
                        "action": "open_settings",
                        "action_label": "Ayarı aç",
                        "updated_at": saved_profile.get("updated_at"),
                        "profile_reconciliation": profile_reconciliation,
                    }
                )
            profile = saved_profile

        if runtime_patch:
            saved_runtime = self.store.upsert_assistant_runtime_profile(self.office_id, **runtime_patch)
            changed_fields = self._changed_fields(runtime_patch, runtime_profile)
            if changed_fields:
                updates.append(
                    {
                        "kind": "assistant_persona_signal",
                        "status": "stored",
                        "summary": self._memory_update_summary("assistant_persona_signal", changed_fields),
                        "fields": changed_fields,
                        "route": self._settings_route_for_update("assistant_persona_signal", changed_fields),
                        "action": "open_settings",
                        "action_label": "Ayarı aç",
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
                    assistant_notes=merge_profile_memory_note(profile.get("assistant_notes"), fallback_note),
                    important_dates=profile.get("important_dates") or [],
                )
                updates.append(
                    {
                        "kind": "profile_signal",
                        "status": "stored",
                        "summary": self._memory_update_summary("profile_signal", ["assistant_notes"]),
                        "fields": ["assistant_notes"],
                        "route": self._settings_route_for_update("profile_signal", ["assistant_notes"]),
                        "action": "open_settings",
                        "action_label": "Ayarı aç",
                        "updated_at": saved_profile.get("updated_at"),
                        "profile_reconciliation": self._reconcile_profile(saved_profile, reason="chat_profile_signal"),
                    }
                )

        if updates and self.knowledge_base is not None:
            try:
                self.knowledge_base.sync_from_store(store=self.store, reason="memory_capture")
            except Exception:  # noqa: BLE001
                pass

        return updates

    def _reconcile_profile(self, profile: dict[str, Any], *, reason: str) -> dict[str, Any] | None:
        if self.memory_mutations is None:
            return None
        try:
            return self.memory_mutations.reconcile_user_profile(
                profile=profile,
                authority="profile",
                reason=reason,
            )
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _changed_fields(
        patch: dict[str, Any],
        previous: dict[str, Any] | None,
        *,
        ignored_fields: set[str] | None = None,
    ) -> list[str]:
        baseline = previous or {}
        ignored = ignored_fields or set()
        changed: list[str] = []
        for field, value in patch.items():
            if field in ignored:
                continue
            if value != baseline.get(field):
                changed.append(field)
        return changed

    @staticmethod
    def _memory_update_summary(kind: str, fields: list[str]) -> str:
        field_set = set(fields)
        if kind == "assistant_persona_signal":
            if field_set == {"assistant_name"}:
                return "Asistan adı güncellendi."
            if "assistant_forms" in field_set:
                return "Asistan çekirdeği yeni bir forma göre güncellendi."
            if "behavior_contract" in field_set:
                return "Asistanın çalışma kontratı güncellendi."
            if field_set and field_set <= {"tools_notes", "heartbeat_extra_checks"}:
                return "Asistan rutinleri güncellendi."
            return "Asistan profili güncellendi."
        if field_set == {"display_name"}:
            return "Hitap tercihi güncellendi."
        if field_set == {"source_preference_rules"}:
            return "Kaynak ve sağlayıcı tercihleri güncellendi."
        if field_set == {"related_profiles"}:
            return "İlgili kişi profili güncellendi."
        if field_set == {"assistant_notes"}:
            return "Profil belleği güncellendi."
        return "Kullanıcı profili güncellendi."

    @staticmethod
    def _settings_route_for_update(kind: str, fields: list[str]) -> str:
        field_set = set(fields)
        if kind == "assistant_persona_signal":
            if "assistant_forms" in field_set or "behavior_contract" in field_set:
                return "/settings?tab=assistant&section=assistant-core-forms"
            if field_set and field_set <= {"tools_notes", "heartbeat_extra_checks"}:
                return "/settings?tab=assistant&section=assistant-advanced-routines"
            return "/settings?tab=assistant&section=assistant-runtime"
        if "source_preference_rules" in field_set:
            return "/settings?tab=profil&section=source-preferences"
        if "related_profiles" in field_set:
            return "/settings?tab=iletisim&section=related-profiles"
        return "/settings?tab=profil&section=personal-profile"

    def _extract_user_profile_patch(self, text: str, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_persona_text(text)
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
            "source_preference_rules": profile.get("source_preference_rules") or [],
        }
        changed = False
        structured_preference_changed = False

        explicit_display_name = compact_user_profile_value("display_name", self._extract_explicit_user_field_value(text, "display_name") or "")
        if explicit_display_name and explicit_display_name != patch["display_name"]:
            patch["display_name"] = explicit_display_name
            changed = True
            structured_preference_changed = True

        if not explicit_display_name:
            display_name_match = extract_match(DISPLAY_NAME_PATTERNS, text)
            display_name = compact_user_profile_value("display_name", display_name_match or "")
            if display_name and display_name != patch["display_name"]:
                patch["display_name"] = display_name
                changed = True

        explicit_favorite_color = compact_user_profile_value("favorite_color", self._extract_explicit_user_field_value(text, "favorite_color") or "")
        if explicit_favorite_color and explicit_favorite_color != patch["favorite_color"]:
            patch["favorite_color"] = explicit_favorite_color
            changed = True
            structured_preference_changed = True

        favorite_color = extract_match(FAVORITE_COLOR_PATTERNS, text)
        favorite_color = compact_user_profile_value("favorite_color", favorite_color or "")
        if favorite_color and favorite_color != patch["favorite_color"]:
            patch["favorite_color"] = favorite_color
            changed = True

        explicit_transport = compact_user_profile_value("transport_preference", self._extract_explicit_user_field_value(text, "transport_preference") or "")
        if explicit_transport and explicit_transport != patch["transport_preference"]:
            patch["transport_preference"] = explicit_transport
            changed = True
            structured_preference_changed = True

        if any(keyword in normalized for keyword in ("tren", "metro", "ucak", "uçak", "araba", "otobus", "otobüs", "taksi", "bisiklet", "vapur")) and any(
            marker in normalized for marker in ("tercih ederim", "tercih ediyorum", "genelde", "mümkünse", "mumkunse", "ulasim", "ulaşım")
        ):
            candidate = compact_user_profile_value("transport_preference", text)
            if candidate and candidate != patch["transport_preference"]:
                patch["transport_preference"] = candidate
                changed = True
                structured_preference_changed = True

        explicit_weather = compact_user_profile_value("weather_preference", self._extract_explicit_user_field_value(text, "weather_preference") or "")
        if explicit_weather and explicit_weather != patch["weather_preference"]:
            patch["weather_preference"] = explicit_weather
            changed = True
            structured_preference_changed = True

        if any(keyword in normalized for keyword in ("hava", "gunesli", "güneşli", "serin", "soguk", "soğuk", "ilik", "ılık", "yagmurlu", "yağmurlu")) and any(
            marker in normalized for marker in ("severim", "hoslanirim", "hoşlanırım", "tercih ederim", "tercihim")
        ):
            candidate = compact_user_profile_value("weather_preference", text)
            if candidate and candidate != patch["weather_preference"]:
                patch["weather_preference"] = candidate
                changed = True
                structured_preference_changed = True

        explicit_food = compact_user_profile_value("food_preferences", self._extract_explicit_user_field_value(text, "food_preferences") or "")
        if explicit_food and explicit_food != patch["food_preferences"]:
            patch["food_preferences"] = explicit_food
            changed = True
            structured_preference_changed = True

        if any(keyword in normalized for keyword in ("kahve", "cay", "çay", "vegan", "vejetaryen", "pizza", "burger", "tatli", "tatlı", "yemek", "yeme icme", "yeme içme")) and any(
            marker in normalized for marker in ("severim", "sevmem", "tercih ederim", "hoslanirim", "hoşlanırım", "kacinirim", "kaçınırım")
        ):
            candidate = compact_user_profile_value("food_preferences", text)
            if candidate and candidate != patch["food_preferences"]:
                patch["food_preferences"] = candidate
                changed = True
                structured_preference_changed = True

        explicit_travel = compact_user_profile_value("travel_preferences", self._extract_explicit_user_field_value(text, "travel_preferences") or "")
        if explicit_travel and explicit_travel != patch["travel_preferences"]:
            patch["travel_preferences"] = explicit_travel
            changed = True
            structured_preference_changed = True

        if any(keyword in normalized for keyword in ("seyahat", "otel", "ucus", "uçuş", "bilet", "pencere", "konaklama")) and any(
            marker in normalized for marker in ("tercih ederim", "isterim", "seviyorum", "severim", "notum", "genelde")
        ):
            candidate = compact_user_profile_value("travel_preferences", text)
            if candidate and candidate != patch["travel_preferences"]:
                patch["travel_preferences"] = candidate
                changed = True
                structured_preference_changed = True

        explicit_communication_style = compact_user_profile_value("communication_style", self._extract_explicit_user_field_value(text, "communication_style") or "")
        if explicit_communication_style and explicit_communication_style != patch["communication_style"]:
            patch["communication_style"] = explicit_communication_style
            changed = True
            structured_preference_changed = True

        if any(keyword in normalized for keyword in ("kisa", "kısa", "detayli", "resmi", "samimi", "direkt", "net")) and any(
            marker in normalized for marker in USER_DIRECTION_MARKERS
        ):
            candidate = compact_user_profile_value("communication_style", text)
            if candidate and candidate != patch["communication_style"]:
                patch["communication_style"] = candidate
                changed = True
                structured_preference_changed = True

        explicit_assistant_notes = self._extract_explicit_user_field_value(text, "assistant_notes")
        if explicit_assistant_notes:
            candidate = compact_user_profile_value("assistant_notes", explicit_assistant_notes) or clean_persona_text(explicit_assistant_notes, limit=2400)
            if candidate and candidate != patch["assistant_notes"]:
                patch["assistant_notes"] = candidate
                changed = True
                structured_preference_changed = True

        if any(marker in normalized for marker in ("ben", "bana", "benim", "hoslanirim", "hoşlanırım", "tercih ederim", "severim")):
            note_value = self._extract_fallback_profile_note(text, profile)
            if note_value and (not structured_preference_changed or note_value.startswith("Öncelikli destek alanları:")):
                next_notes = merge_profile_memory_note(str(patch["assistant_notes"] or ""), note_value)
                if next_notes != patch["assistant_notes"]:
                    patch["assistant_notes"] = next_notes
                    changed = True

        extracted_source_rules = extract_source_preference_rules_from_text(
            text,
            existing_rules=list(patch.get("source_preference_rules") or []),
        )
        if extracted_source_rules is not None and extracted_source_rules != list(patch.get("source_preference_rules") or []):
            patch["source_preference_rules"] = extracted_source_rules
            changed = True
            structured_preference_changed = True

        extracted_related_profiles = self._extract_related_profile_updates(
            text,
            existing_profiles=list(patch.get("related_profiles") or []),
        )
        if extracted_related_profiles != list(patch.get("related_profiles") or []):
            patch["related_profiles"] = extracted_related_profiles
            changed = True

        patch["assistant_notes"] = normalize_profile_memory_notes(patch["assistant_notes"])

        return patch if changed else {}

    def _extract_assistant_profile_patch(self, text: str, runtime_profile: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_persona_text(text)
        patch = {
            "assistant_name": runtime_profile.get("assistant_name"),
            "role_summary": runtime_profile.get("role_summary"),
            "tone": runtime_profile.get("tone"),
            "avatar_path": runtime_profile.get("avatar_path"),
            "soul_notes": runtime_profile.get("soul_notes"),
            "tools_notes": runtime_profile.get("tools_notes"),
            "assistant_forms": runtime_profile.get("assistant_forms") or [],
            "behavior_contract": runtime_profile.get("behavior_contract") or {},
            "evolution_history": runtime_profile.get("evolution_history") or [],
            "heartbeat_extra_checks": runtime_profile.get("heartbeat_extra_checks") or [],
        }
        changed = False

        explicit_assistant_name = compact_assistant_profile_value("assistant_name", self._extract_explicit_assistant_field_value(text, "assistant_name") or "")
        if explicit_assistant_name and explicit_assistant_name != patch["assistant_name"]:
            patch["assistant_name"] = explicit_assistant_name
            changed = True

        assistant_name_hint = any(
            marker in normalized
            for marker in (
                "senin adin",
                "senin ismin",
                "asistan adin",
                "asistanin adini",
                "asistan ismin",
            )
        ) or bool(re.search(r"\b(?:adin|ismin)\b", normalized))
        if not explicit_assistant_name:
            assistant_name_match = extract_match(ASSISTANT_NAME_PATTERNS, text) if assistant_name_hint else None
            assistant_name = compact_assistant_profile_value("assistant_name", assistant_name_match or "")
            if assistant_name and assistant_name != patch["assistant_name"]:
                patch["assistant_name"] = assistant_name
                changed = True

        explicit_role_summary = compact_assistant_profile_value("role_summary", self._extract_explicit_assistant_field_value(text, "role_summary") or "")
        if explicit_role_summary and explicit_role_summary != patch["role_summary"]:
            patch["role_summary"] = explicit_role_summary
            changed = True

        explicit_tone_raw = self._extract_explicit_assistant_field_value(text, "tone") or ""
        explicit_tone = compact_assistant_profile_value("tone", explicit_tone_raw)
        if explicit_tone and explicit_tone != patch["tone"]:
            patch["tone"] = merge_assistant_tone(patch["tone"], explicit_tone_raw)
            changed = True

        explicit_soul_notes = compact_assistant_profile_value("soul_notes", self._extract_explicit_assistant_field_value(text, "soul_notes") or "")
        if explicit_soul_notes:
            next_soul_notes = explicit_soul_notes
            if next_soul_notes != patch["soul_notes"]:
                patch["soul_notes"] = next_soul_notes
                changed = True

        explicit_tools_notes = self._extract_explicit_assistant_field_value(text, "tools_notes")
        if explicit_tools_notes:
            normalized_tools_notes = clean_persona_text(explicit_tools_notes, limit=2400)
            if normalized_tools_notes and normalized_tools_notes != patch["tools_notes"]:
                patch["tools_notes"] = normalized_tools_notes
                changed = True

        explicit_avatar_path = self._extract_explicit_assistant_field_value(text, "avatar_path")
        if explicit_avatar_path:
            normalized_avatar_path = clean_persona_text(explicit_avatar_path, limit=800)
            if normalized_avatar_path and normalized_avatar_path != patch["avatar_path"]:
                patch["avatar_path"] = normalized_avatar_path
                changed = True

        explicit_heartbeat_checks = self._extract_explicit_heartbeat_checks(text, patch["heartbeat_extra_checks"])
        if explicit_heartbeat_checks is not None and explicit_heartbeat_checks != patch["heartbeat_extra_checks"]:
            patch["heartbeat_extra_checks"] = explicit_heartbeat_checks
            changed = True

        implicit_routine = self._extract_implicit_assistant_routine(text, patch["heartbeat_extra_checks"])
        if implicit_routine is not None:
            next_tools_notes = append_unique_note(str(patch["tools_notes"] or ""), implicit_routine["note"])
            if next_tools_notes != patch["tools_notes"]:
                patch["tools_notes"] = next_tools_notes
                changed = True
            next_checks = implicit_routine["checks"]
            if next_checks != patch["heartbeat_extra_checks"]:
                patch["heartbeat_extra_checks"] = next_checks
                changed = True

        if any(marker in normalized for marker in ASSISTANT_DIRECTION_MARKERS):
            next_tone = compact_assistant_profile_value("tone", text)
            if next_tone and any(label == next_tone or label in next_tone for _keyword, label in TONE_KEYWORDS):
                merged_tone = merge_assistant_tone(patch["tone"], text)
                if merged_tone != patch["tone"]:
                    patch["tone"] = merged_tone
                    changed = True

            if any(hint in normalized for hint in ROLE_HINTS):
                candidate = compact_assistant_profile_value("role_summary", text)
                if candidate and candidate != patch["role_summary"]:
                    patch["role_summary"] = candidate
                    changed = True

            next_soul_notes = append_unique_note(
                str(patch["soul_notes"] or ""),
                compact_assistant_profile_value("soul_notes", text),
            )
            if next_soul_notes != patch["soul_notes"]:
                patch["soul_notes"] = next_soul_notes
                changed = True

        core_update = apply_assistant_core_update(text, runtime_profile)
        if core_update:
            for field, value in dict(core_update.get("patch") or {}).items():
                if patch.get(field) != value:
                    patch[field] = value
                    changed = True

        return patch if changed else {}

    def _extract_fallback_profile_note(self, text: str, profile: dict[str, Any]) -> str | None:
        if self._is_non_memory_question(text) or not self._looks_like_support_priority_statement(text):
            return None
        existing_notes = str((profile or {}).get("assistant_notes") or "").strip()
        note = summarize_user_support_note(text)
        if not note:
            return None
        normalized = normalize_persona_text(text)
        if not note.startswith("Öncelikli destek alanları:") and not any(
            marker in normalized for marker in ("tercih", "severim", "sevmem", "genelde", "hoslanirim", "hoşlanırım", "istemem")
        ):
            return None
        if normalize_persona_text(note) in normalize_persona_text(existing_notes):
            return None
        return note

    @staticmethod
    def _is_non_memory_question(text: str) -> bool:
        normalized = normalize_persona_text(text)
        if not normalized:
            return False
        explicit_memory_markers = (
            "guncelle",
            "degistir",
            "kaydet",
            "ekle",
            "not et",
            "profil notuma",
            "destek notuma",
            "yardim notuma",
            "oncelikli destek notuma",
        )
        if any(marker in normalized for marker in explicit_memory_markers):
            return False

        question_like = "?" in text or bool(
            re.search(
                r"\b(mi|mı|mu|mü|misin|mısın|musun|müsün|miyim|mıyım|muyum|müyüm|nedir|neydi|hangi|hangisi|kim|kime|kimi|nasil|nasil|neden|niye|kac|kaç|nerede|ne zaman)\b",
                normalized,
            )
        )
        if not question_like:
            return False

        capability_checks = (
            "erisebiliyor musun",
            "ulasabiliyor musun",
            "bakabiliyor musun",
            "gorebiliyor musun",
            "acabiliyor musun",
            "bagli misin",
            "bagli mi",
            "var mi",
            "goruyor musun",
            "okuyabiliyor musun",
            "senkronize oldu mu",
        )
        operational_hints = (
            "su an",
            "simdi",
            "mevcut",
            "mail",
            "e-posta",
            "takvim",
            "drive",
            "google",
            "outlook",
            "whatsapp",
            "telegram",
            "x hesab",
            "erisim",
            "baglanti",
        )
        return any(marker in normalized for marker in capability_checks) or any(hint in normalized for hint in operational_hints)

    @staticmethod
    def _looks_like_support_priority_statement(text: str) -> bool:
        normalized = normalize_persona_text(text)
        if not normalized or MemoryService._is_non_memory_question(text):
            return False

        support_tokens = (
            "muvekkil",
            "müvekkil",
            "mail",
            "e posta",
            "e-posta",
            "mesaj",
            "takvim",
            "durusma",
            "duruşma",
            "taslak",
            "son tarih",
            "dosya eksik",
            "belge envanter",
            "belge",
            "iletisim",
            "iletişim",
        )
        if not any(token in normalized for token in support_tokens):
            return False

        intent_cues = (
            "destek ol",
            "yardimci ol",
            "yardımcı ol",
            "yardim et",
            "yardım et",
            "omuz ver",
            "takip et",
            "hatirlat",
            "hatırlat",
            "uyar",
            "onceliklendir",
            "önceliklendir",
            "oncelikli",
            "öncelikli",
            "onceligim",
            "önceliğim",
            "konusunda",
            "konularinda",
            "konularında",
            "one cikar",
            "öne çıkar",
            "odaklan",
            "ilgilen",
            "onemli",
            "önemli",
            "kritik",
        )
        if any(cue in normalized for cue in intent_cues):
            return True

        compact = re.sub(r"[.,;:!?]+", " ", normalized)
        words = [item for item in compact.split() if item]
        if len(words) <= 2:
            return False
        return False

    @staticmethod
    def _extract_explicit_value(text: str, keywords: tuple[str, ...], *, limit: int = 240) -> str | None:
        normalized = normalize_persona_text(text)
        if not any(marker in normalized for marker in ("guncelle", "degistir", "yap", "kaydet", "olsun", "ekle", "yaz", "kaldir", "sil", "cikar", "temizle")):
            return None
        keyword_pattern = "|".join(sorted((re.escape(item) for item in keywords), key=len, reverse=True))
        keyword_boundary = rf"(?<![A-Za-zÇĞİÖŞÜçğıöşü])(?:{keyword_pattern})(?![A-Za-zÇĞİÖŞÜçğıöşü])"
        patterns = [
            rf"{keyword_boundary}\s*(?::|=)?\s*(.+?)(?=\s+(?:olarak\s+)?(?:g[uü]ncelle|de[gğ]i[sş]tir|yap|kaydet|olsun|ekle|yaz)\b|[.!?]|$)",
            rf"{keyword_boundary}\s*(?:olarak\s+)?(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            candidate = clean_persona_text(match.group(1), limit=limit)
            if candidate:
                return candidate
        return None

    def _extract_explicit_user_field_value(self, text: str, field: str) -> str | None:
        field_keywords: dict[str, tuple[str, ...]] = {
            "display_name": ("adımı", "ismimi", "hitabımı"),
            "favorite_color": ("favori rengimi", "en sevdiğim rengi", "renk tercihimi", "rengimi"),
            "food_preferences": ("yeme içme tercihimi", "yemek tercihimi", "beslenme tercihimi"),
            "transport_preference": ("ulaşım tercihimi", "ulasim tercihimi", "ulaşımımı", "ulasimimi"),
            "weather_preference": ("hava tercihimi", "iklim tercihimi"),
            "travel_preferences": ("seyahat tercihimi", "yolculuk tercihimi"),
            "communication_style": ("iletişim stilimi", "iletisim stilimi", "iletişim tarzımı", "iletisim tarzimi", "üslubumu", "uslubumu", "cevap stilimi", "yanıt stilimi"),
            "assistant_notes": ("profil notuma", "destek notuma", "yardım notuma", "yardim notuma", "öncelikli destek notuma", "oncelikli destek notuma"),
        }
        return self._extract_explicit_value(text, field_keywords.get(field, ()))

    def _extract_explicit_assistant_field_value(self, text: str, field: str) -> str | None:
        field_keywords: dict[str, tuple[str, ...]] = {
            "assistant_name": ("adını", "adini", "ismini", "asistan adını", "asistanin adini"),
            "role_summary": ("rolünü", "rolunu", "görevini", "gorevini", "asistan rolünü", "asistan rolunu"),
            "tone": ("tonunu", "üslubunu", "uslubunu", "konuşma tarzını", "konusma tarzini", "dilini"),
            "avatar_path": ("avatar yolunu", "avatarını", "avatarini", "profil resmi yolunu"),
            "soul_notes": ("davranış notuna", "davranis notuna", "sınırlarına", "sinirlarina", "kurallarına", "kurallarina"),
            "tools_notes": ("rutinlerine", "operasyon notuna", "araç notuna", "arac notuna", "tools notuna", "çalışma notuna", "calisma notuna"),
        }
        return self._extract_explicit_value(text, field_keywords.get(field, ()), limit=2400 if field in {"soul_notes", "tools_notes"} else 240)

    def _extract_explicit_heartbeat_checks(self, text: str, existing_checks: list[str] | None) -> list[str] | None:
        raw_value = self._extract_explicit_value(
            text,
            (
                "heartbeat kontrollerine",
                "heartbeat'e",
                "heartbeate",
                "ekstra kontrollere",
                "rutin kontrollere",
                "kontrol listene",
            ),
            limit=800,
        )
        if not raw_value:
            return None
        normalized = normalize_persona_text(text)
        items = [
            clean_persona_text(
                re.sub(r"^(?:bir de|ve|ile|şunu|şunları|bunları)\s+", "", chunk, flags=re.IGNORECASE),
                limit=120,
            )
            for chunk in re.split(r",|;|\s+ve\s+", raw_value)
        ]
        normalized_items = [item for item in items if item]
        if not normalized_items:
            return None
        current = [str(item).strip() for item in list(existing_checks or []) if str(item).strip()]
        if any(marker in normalized for marker in ("kaldir", "kaldır", "sil", "cikar", "çıkar", "temizle")):
            remove_keys = {normalize_persona_text(item) for item in normalized_items}
            next_items = [item for item in current if normalize_persona_text(item) not in remove_keys]
            return next_items
        merged = list(current)
        for item in normalized_items:
            if normalize_persona_text(item) in {normalize_persona_text(existing_item) for existing_item in merged}:
                continue
            merged.append(item)
        return merged

    @staticmethod
    def _extract_implicit_assistant_routine(text: str, existing_checks: list[str] | None) -> dict[str, Any] | None:
        normalized = normalize_persona_text(text)
        if not normalized or MemoryService._is_non_memory_question(text):
            return None

        schedule_markers = (
            "her sabah",
            "her gun",
            "her gün",
            "gunluk",
            "günlük",
            "her hafta",
            "haftalik",
            "haftalık",
            "her aksam",
            "her akşam",
        )
        action_markers = (
            "bana yaz",
            "bana mesaj at",
            "mesaj at",
            "yaz",
            "gonder",
            "gönder",
            "ilet",
            "hatirlat",
            "hatırlat",
            "bildir",
            "raporla",
            "ozetle",
            "özetle",
            "kontrol et",
        )
        if not any(marker in normalized for marker in schedule_markers):
            return None
        if not any(marker in normalized for marker in action_markers):
            return None

        note = clean_persona_text(text, limit=260)
        if not note:
            return None

        channel = ""
        if any(token in normalized for token in ("whatsapp", "wp")):
            channel = "WhatsApp"
        elif "telegram" in normalized:
            channel = "Telegram"
        elif any(token in normalized for token in ("mail", "e-posta", "outlook")):
            channel = "E-posta"

        focus = ""
        if any(token in normalized for token in ("yapilacak", "yapılacak", "todo", "gorev", "görev")):
            focus = "Yapılacaklar"
        elif any(token in normalized for token in ("mail", "e-posta", "outlook")):
            focus = "Yeni iletiler"
        elif any(token in normalized for token in ("takvim", "ajanda")):
            focus = "Takvim özeti"

        compact_check_parts = ["Zamanlanmış rutin"]
        if focus:
            compact_check_parts.append(focus)
        if channel:
            compact_check_parts.append(channel)
        compact_check = " / ".join(compact_check_parts)

        current = [str(item).strip() for item in list(existing_checks or []) if str(item).strip()]
        if normalize_persona_text(compact_check) not in {normalize_persona_text(item) for item in current}:
            current.append(compact_check)

        return {
            "note": note,
            "checks": current,
        }

    def _extract_related_profile_updates(
        self,
        text: str,
        *,
        existing_profiles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized = normalize_persona_text(text)
        if not normalized or self._is_non_memory_question(text):
            return list(existing_profiles or [])

        next_profiles = [dict(item) for item in list(existing_profiles or []) if isinstance(item, dict)]
        changed = False
        sentences = [
            clean_persona_text(chunk, limit=280)
            for chunk in re.split(r"[.!?\n;]+", text)
            if clean_persona_text(chunk, limit=280)
        ]

        for sentence in sentences:
            if "?" in sentence:
                continue
            target = self._resolve_related_profile_target(sentence=sentence, existing_profiles=next_profiles)
            if target is None:
                continue
            learning = self._derive_related_profile_learning(sentence)
            if not learning.get("preference_lines") and not learning.get("note"):
                continue

            target_index = -1
            target_id = str(target.get("id") or "").strip()
            target_name = str(target.get("name") or "").strip()
            for index, item in enumerate(next_profiles):
                if target_id and str(item.get("id") or "").strip() == target_id:
                    target_index = index
                    break
                if target_name and normalize_persona_text(str(item.get("name") or "")) == normalize_persona_text(target_name):
                    target_index = index
                    break
            if target_index < 0:
                continue

            target_profile = dict(next_profiles[target_index])
            next_preferences = str(target_profile.get("preferences") or "")
            for prefix, statement in list(learning.get("preference_lines") or []):
                next_preferences = self._merge_prefixed_statement(next_preferences, prefix=prefix, statement=statement)
            if next_preferences != str(target_profile.get("preferences") or ""):
                target_profile["preferences"] = next_preferences
                changed = True

            note_value = str(learning.get("note") or "").strip()
            if note_value:
                note_lines = [line for line in str(target_profile.get("notes") or "").splitlines() if line.strip()]
                if note_value not in note_lines:
                    note_lines.append(note_value)
                    target_profile["notes"] = "\n".join(note_lines[-8:]).strip()
                    changed = True

            target_profile.setdefault("id", target_id or normalize_persona_text(target_name).replace(" ", "-"))
            target_profile.setdefault("name", target_name or "Kişi")
            target_profile.setdefault("relationship", str(target.get("relationship") or ""))
            target_profile.setdefault("closeness", self._related_profile_closeness(str(target_profile.get("relationship") or target.get("relationship") or "")))
            target_profile.setdefault("important_dates", [])
            next_profiles[target_index] = target_profile

        return next_profiles if changed else list(existing_profiles or [])

    def _resolve_related_profile_target(
        self,
        *,
        sentence: str,
        existing_profiles: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        normalized_sentence = normalize_persona_text(sentence)
        if not normalized_sentence:
            return None

        for item in list(existing_profiles or []):
            if not isinstance(item, dict):
                continue
            aliases = {
                normalize_persona_text(str(item.get("id") or "")),
                normalize_persona_text(str(item.get("name") or "")),
                normalize_persona_text(str(item.get("relationship") or "")),
            }
            aliases = {alias for alias in aliases if alias}
            if any(contains_normalized_phrase(normalized_sentence, alias) for alias in aliases):
                return {
                    "id": str(item.get("id") or normalize_persona_text(str(item.get("name") or "kisi")).replace(" ", "-")),
                    "name": str(item.get("name") or item.get("relationship") or "Kişi"),
                    "relationship": str(item.get("relationship") or ""),
                }

        for relation_meta in RELATED_PROFILE_HINTS.values():
            aliases = [
                normalize_persona_text(alias)
                for alias in list(relation_meta.get("autocreate_aliases") or relation_meta.get("aliases") or [])
                if normalize_persona_text(alias)
            ]
            if any(contains_normalized_phrase(normalized_sentence, alias) for alias in aliases):
                return {
                    "id": str(relation_meta.get("id") or "contact"),
                    "name": str(relation_meta.get("name") or "Kişi"),
                    "relationship": str(relation_meta.get("relationship") or ""),
                }
        return None

    def _derive_related_profile_learning(self, sentence: str) -> dict[str, Any]:
        normalized_sentence = normalize_persona_text(sentence)
        cleaned_sentence = clean_persona_text(sentence, limit=240)
        if not normalized_sentence or not cleaned_sentence:
            return {"preference_lines": [], "note": None}

        preference_lines: list[tuple[str, str]] = []
        is_negative = any(contains_normalized_phrase(normalized_sentence, token) for token in RELATED_PROFILE_NEGATION_HINTS)
        has_preference_signal = any(contains_normalized_phrase(normalized_sentence, token) for token in RELATED_PROFILE_PREFERENCE_HINTS) or is_negative
        has_communication_context = any(contains_normalized_phrase(normalized_sentence, token) for token in RELATED_PROFILE_COMMUNICATION_HINTS)

        style_labels: list[str] = []
        for style_key, aliases in RELATED_PROFILE_STYLE_SIGNAL_MAP.items():
            if any(contains_normalized_phrase(normalized_sentence, alias) for alias in aliases):
                style_labels.append(self._style_label(style_key))
        if has_communication_context and style_labels:
            style_copy = ", ".join(dict.fromkeys(style_labels))
            preference_lines.append(
                (
                    "İletişim",
                    (
                        f"İletişim: {style_copy} tondan kaçınılmalı."
                        if is_negative
                        else f"İletişim: {style_copy} ton olumlu karşılanıyor."
                    ),
                )
            )

        for item_key, aliases in RELATED_PROFILE_ITEM_SIGNAL_MAP.items():
            if not any(contains_normalized_phrase(normalized_sentence, alias) for alias in aliases):
                continue
            item_label = self._item_label(item_key)
            prefix = f"Hediye: {item_label}"
            preference_lines.append(
                (
                    prefix,
                    (
                        f"Hediye: {item_label} önerilerinden kaçınılmalı."
                        if is_negative
                        else f"Hediye: {item_label} önerileri olumlu karşılanıyor."
                    ),
                )
            )

        note = None
        if not preference_lines and has_preference_signal:
            note = cleaned_sentence
        elif not preference_lines and any(token in normalized_sentence for token in ("kaynak", "site", "link", "ara", "bak", "kullan")):
            note = cleaned_sentence

        return {
            "preference_lines": preference_lines,
            "note": note,
        }

    @staticmethod
    def _merge_prefixed_statement(existing_value: str, *, prefix: str, statement: str) -> str:
        lines = [line.strip() for line in str(existing_value or "").splitlines() if line.strip()]
        filtered = [line for line in lines if not line.startswith(prefix)]
        filtered.append(statement)
        return "\n".join(filtered[-8:]).strip()

    @staticmethod
    def _style_label(style_key: str) -> str:
        mapping = {
            "warm": "sıcak",
            "polite": "nazik",
            "formal": "resmi",
            "concise": "kısa",
            "detailed": "detaylı",
        }
        return mapping.get(style_key, style_key)

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
        return mapping.get(item_key, item_key)

    @staticmethod
    def _related_profile_closeness(relationship: str) -> int:
        normalized = normalize_persona_text(relationship)
        if not normalized:
            return 3
        if any(token in normalized for token in ("anne", "baba", "es", "partner", "sevgili", "cocuk", "oglum", "kizim")):
            return 5
        if any(token in normalized for token in ("kardes", "arkadas", "kuzen", "aile", "yakin dost")):
            return 4
        if any(token in normalized for token in ("avukat", "doktor", "musteri", "muvekkil", "is ortagi", "koc")):
            return 3
        return 3
