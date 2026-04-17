from __future__ import annotations

import hashlib
import json
from typing import Any


def _compact_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


PROFILE_FIELD_AUTHORITY_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "profile_field": "display_name",
        "title": "Hitap tercihi",
        "authority_mode": "settings",
        "authority_family": "identity_display",
    },
    {
        "profile_field": "favorite_color",
        "title": "Sevdiği renk",
        "authority_mode": "settings",
        "authority_family": "identity_preference",
    },
    {
        "profile_field": "communication_style",
        "title": "İletişim tonu",
        "authority_mode": "claim_projection",
        "authority_family": "communication_preference",
        "fact_key": "communication.style",
        "category": "communication",
        "scope": "personal",
        "sensitive": False,
    },
    {
        "profile_field": "assistant_notes",
        "title": "Destek odağı",
        "authority_mode": "claim_projection",
        "authority_family": "assistant_support_focus",
        "fact_key": "assistant.support_focus",
        "category": "preferences",
        "scope": "personal",
        "sensitive": False,
    },
    {
        "profile_field": "food_preferences",
        "title": "Yemek tercihleri",
        "authority_mode": "claim_projection",
        "authority_family": "lifestyle_preference",
        "fact_key": "preferences.food",
        "category": "preferences",
        "scope": "personal",
        "sensitive": False,
    },
    {
        "profile_field": "transport_preference",
        "title": "Ulaşım tercihi",
        "authority_mode": "claim_projection",
        "authority_family": "lifestyle_preference",
        "fact_key": "transport.preference",
        "category": "preferences",
        "scope": "personal",
        "sensitive": False,
    },
    {
        "profile_field": "weather_preference",
        "title": "Hava tercihi",
        "authority_mode": "claim_projection",
        "authority_family": "lifestyle_preference",
        "fact_key": "weather.preference",
        "category": "preferences",
        "scope": "personal",
        "sensitive": False,
    },
    {
        "profile_field": "travel_preferences",
        "title": "Seyahat tercihleri",
        "authority_mode": "claim_projection",
        "authority_family": "lifestyle_preference",
        "fact_key": "travel.preferences",
        "category": "preferences",
        "scope": "personal",
        "sensitive": False,
    },
    {
        "profile_field": "home_base",
        "title": "Ana yaşam alanı",
        "authority_mode": "claim_projection",
        "authority_family": "location_anchor",
        "fact_key": "location.home_base",
        "category": "routines",
        "scope": "personal",
        "sensitive": False,
    },
    {
        "profile_field": "current_location",
        "title": "Canlı konum",
        "authority_mode": "settings",
        "authority_family": "runtime_location",
    },
    {
        "profile_field": "location_preferences",
        "title": "Yakın çevre tercihleri",
        "authority_mode": "settings",
        "authority_family": "location_assistance",
    },
    {
        "profile_field": "maps_preference",
        "title": "Harita tercihi",
        "authority_mode": "settings",
        "authority_family": "navigation_tooling",
    },
    {
        "profile_field": "prayer_notifications_enabled",
        "title": "Özel rutin desteği",
        "authority_mode": "settings",
        "authority_family": "notification_rule",
    },
    {
        "profile_field": "prayer_habit_notes",
        "title": "Özel rutin notu",
        "authority_mode": "settings",
        "authority_family": "routine_assistance",
    },
    {
        "profile_field": "important_dates",
        "title": "Önemli tarihler",
        "authority_mode": "settings",
        "authority_family": "calendar_rule",
    },
    {
        "profile_field": "related_profiles",
        "title": "Yakın çevre profilleri",
        "authority_mode": "settings",
        "authority_family": "contact_management",
    },
    {
        "profile_field": "inbox_watch_rules",
        "title": "İzleme kuralları",
        "authority_mode": "settings",
        "authority_family": "channel_rule",
    },
    {
        "profile_field": "inbox_keyword_rules",
        "title": "Anahtar kelime kuralları",
        "authority_mode": "settings",
        "authority_family": "channel_rule",
    },
    {
        "profile_field": "inbox_block_rules",
        "title": "Engel kuralları",
        "authority_mode": "settings",
        "authority_family": "channel_rule",
    },
    {
        "profile_field": "source_preference_rules",
        "title": "Kaynak tercih kuralları",
        "authority_mode": "settings",
        "authority_family": "research_source_rule",
    },
)


def _build_profile_fact_mappings() -> tuple[dict[str, Any], ...]:
    return tuple(
        item
        for item in PROFILE_FIELD_AUTHORITY_REGISTRY
        if str(item.get("authority_mode") or "") == "claim_projection" and str(item.get("fact_key") or "").strip()
    )


PROFILE_FACT_MAPPINGS: tuple[dict[str, Any], ...] = _build_profile_fact_mappings()


class MemoryMutationService:
    def __init__(
        self,
        *,
        store: Any,
        office_id: str,
        epistemic: Any | None = None,
        knowledge_base: Any | None = None,
        settings: Any | None = None,
        events: Any | None = None,
    ) -> None:
        self.store = store
        self.office_id = office_id
        self.epistemic = epistemic
        self.knowledge_base = knowledge_base
        self.settings = settings
        self.events = events

    def sync_personal_fact(
        self,
        *,
        fact: dict[str, Any],
        raw_entry: dict[str, Any] | None,
        source_kind: str,
        basis: str,
        validation_state: str,
    ) -> dict[str, Any] | None:
        if self.epistemic is None:
            return None
        claim = self.epistemic.sync_personal_fact(
            fact=fact,
            raw_entry=raw_entry,
            source_kind=source_kind,
            basis=basis,
            validation_state=validation_state,
        )
        self._log(
            "memory_mutation_personal_fact_synced",
            fact_id=fact.get("id"),
            fact_key=fact.get("fact_key"),
            basis=basis,
            validation_state=validation_state,
        )
        return claim

    def retire_personal_fact_claims(self, *, fact: dict[str, Any], reason: str) -> int:
        claims = self.store.list_epistemic_claims(
            self.office_id,
            subject_key="user",
            predicate=str(fact.get("fact_key") or ""),
            scope=str(fact.get("scope") or "global"),
            include_blocked=True,
            limit=50,
        )
        retired = 0
        for claim in claims:
            if str(((claim.get("metadata") or {}).get("fact_id") or "")) != str(fact.get("id") or ""):
                continue
            self.store.update_epistemic_claim(
                self.office_id,
                str(claim.get("id") or ""),
                validation_state="superseded",
                retrieval_eligibility="blocked",
                valid_to=self._iso_now(),
                metadata={"retired_reason": reason},
            )
            retired += 1
        self._log(
            "memory_mutation_personal_fact_retired",
            fact_id=fact.get("id"),
            fact_key=fact.get("fact_key"),
            retired_claims=retired,
            reason=reason,
        )
        return retired

    def record_external_signal(
        self,
        *,
        provider: str,
        event_type: str,
        query: str,
        matter_id: int | None,
        title: str | None = None,
        summary: str | None = None,
        source_url: str | None = None,
        external_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        compact_title = _compact_text(title or event_type.replace("_", " "))
        compact_summary = _compact_text(summary or "")
        payload = dict(metadata or {})
        payload.setdefault("scope", f"project:matter-{matter_id}" if matter_id is not None else "personal")
        payload.setdefault("query", query)
        payload.setdefault("captured_via", "assistant_thread")
        payload.setdefault("route_intent", event_type)
        if source_url:
            payload.setdefault("url", source_url)
            payload.setdefault("source_url", source_url)
        if not compact_summary:
            compact_summary = " | ".join(part for part in (compact_title, _compact_text(query)) if part).strip()
        fingerprint_seed = json.dumps(
            {
                "provider": provider,
                "event_type": event_type,
                "query": query,
                "title": compact_title,
                "url": source_url,
                "scope": payload.get("scope"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        event_marker = external_ref or hashlib.sha256(fingerprint_seed.encode("utf-8")).hexdigest()[:20]
        event = self.store.add_external_event(
            self.office_id,
            provider=provider,
            event_type=event_type,
            summary=compact_summary or compact_title,
            external_ref=event_marker,
            title=compact_title,
            metadata=payload,
        )
        self._log(
            "memory_mutation_external_signal_recorded",
            provider=provider,
            event_type=event_type,
            external_ref=event_marker,
        )
        if self.knowledge_base is not None and getattr(self.knowledge_base, "enabled", False):
            self.knowledge_base.ensure_scaffold()
            self.knowledge_base.sync_from_store(
                store=self.store,
                settings=self.settings,
                reason=f"assistant_external_signal:{provider}:{event_type}",
            )
        return event

    def set_channel_memory_state(
        self,
        *,
        channel_type: str,
        record_id: int,
        memory_state: str,
        sync_reason: str | None = None,
    ) -> dict[str, Any] | None:
        updated = self.store.set_channel_memory_state(
            self.office_id,
            channel_type=channel_type,
            record_id=record_id,
            memory_state=memory_state,
        )
        if updated is None:
            return None
        self._log(
            "memory_mutation_channel_memory_state_updated",
            channel_type=channel_type,
            record_id=record_id,
            memory_state=updated.get("memory_state"),
        )
        if self.knowledge_base is not None and getattr(self.knowledge_base, "enabled", False):
            self.knowledge_base.ensure_scaffold()
            self.knowledge_base.sync_from_store(
                store=self.store,
                settings=self.settings,
                reason=sync_reason or f"channel_memory_state:{channel_type}:{record_id}:{updated.get('memory_state')}",
            )
        return updated

    def reconcile_user_profile(
        self,
        *,
        profile: dict[str, Any] | None = None,
        authority: str = "profile",
        reason: str = "profile_reconciliation",
    ) -> dict[str, Any]:
        current_profile = dict(profile or self.store.get_user_profile(self.office_id) or {})
        facts = self.store.list_personal_model_facts(self.office_id, include_disabled=True, limit=400)
        fact_index: dict[str, dict[str, Any]] = {}
        for item in facts:
            fact_key = str(item.get("fact_key") or "").strip()
            if fact_key and fact_key not in fact_index:
                fact_index[fact_key] = item
        synced_facts: list[dict[str, Any]] = []
        hydrated_fields: list[dict[str, Any]] = []
        profile_patch: dict[str, Any] = {}
        normalized_authority = str(authority or "profile").strip().lower()
        authority_summary = self._profile_authority_summary()
        for mapping in PROFILE_FACT_MAPPINGS:
            field = str(mapping.get("profile_field") or "")
            fact_key = str(mapping.get("fact_key") or "")
            if not field or not fact_key:
                continue
            profile_value = _compact_text(current_profile.get(field), limit=500)
            fact = fact_index.get(fact_key)
            fact_value = _compact_text((fact or {}).get("value_text"), limit=500)
            if normalized_authority == "profile":
                if profile_value and _normalize_text(profile_value) != _normalize_text(fact_value):
                    stored_fact = self._upsert_profile_backed_fact(mapping=mapping, existing_fact=fact, value_text=profile_value, reason=reason)
                    synced_facts.append(
                        {
                            "field": field,
                            "fact_key": fact_key,
                            "fact_id": stored_fact.get("id"),
                            "direction": "profile_to_fact",
                            "title": mapping.get("title"),
                            "authority_mode": mapping.get("authority_mode"),
                            "authority_family": mapping.get("authority_family"),
                        }
                    )
                    fact_index[fact_key] = stored_fact
                continue
            if not self._fact_can_hydrate_profile(fact):
                continue
            if not fact_value or _normalize_text(profile_value) == _normalize_text(fact_value):
                continue
            profile_patch[field] = fact_value
            hydrated_fields.append(
                {
                    "field": field,
                    "fact_key": fact_key,
                    "fact_id": (fact or {}).get("id"),
                    "direction": "fact_to_profile",
                    "title": mapping.get("title"),
                    "authority_mode": mapping.get("authority_mode"),
                    "authority_family": mapping.get("authority_family"),
                }
            )
        saved_profile = current_profile
        if profile_patch:
            saved_profile = self._save_user_profile_patch(current_profile, profile_patch)
        changed = bool(synced_facts or hydrated_fields)
        if changed and self.knowledge_base is not None and getattr(self.knowledge_base, "enabled", False):
            self.knowledge_base.ensure_scaffold()
            self.knowledge_base.sync_from_store(
                store=self.store,
                settings=self.settings,
                reason=reason,
            )
        self._log(
            "memory_mutation_profile_reconciled",
            authority=normalized_authority,
            synced_fact_count=len(synced_facts),
            hydrated_field_count=len(hydrated_fields),
            changed=changed,
            reason=reason,
        )
        return {
            "authority": normalized_authority,
            "authority_model": "predicate_family_split",
            "requested_authority": normalized_authority,
            "changed": changed,
            "synced_facts": synced_facts,
            "hydrated_fields": hydrated_fields,
            **authority_summary,
            "profile": saved_profile,
        }

    def _log(self, event: str, **payload: Any) -> None:
        if self.events is None:
            return
        try:
            self.events.log(event, **payload)
        except Exception:  # noqa: BLE001
            return

    @staticmethod
    def _iso_now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    def _upsert_profile_backed_fact(
        self,
        *,
        mapping: dict[str, Any],
        existing_fact: dict[str, Any] | None,
        value_text: str,
        reason: str,
    ) -> dict[str, Any]:
        fact_key = str(mapping.get("fact_key") or "")
        scope = str(mapping.get("scope") or "personal")
        metadata = dict((existing_fact or {}).get("metadata") or {})
        metadata.update(
            {
                "source_kind": "profile_reconciliation",
                "profile_field": mapping.get("profile_field"),
                "authority_family": mapping.get("authority_family"),
                "reconciled_reason": reason,
                "reconciled_at": self._iso_now(),
            }
        )
        fact_id = str((existing_fact or {}).get("id") or f"pmf-{hashlib.sha256(f'{fact_key}|{scope}|{value_text}'.encode('utf-8')).hexdigest()[:10]}")
        stored_fact = self.store.upsert_personal_model_fact(
            self.office_id,
            fact_id=fact_id,
            session_id=None,
            category=str(mapping.get("category") or "preferences"),
            fact_key=fact_key,
            title=str(mapping.get("title") or fact_key),
            value_text=value_text,
            value_json={"text": value_text},
            confidence=float((existing_fact or {}).get("confidence") or 0.99),
            confidence_type="explicit",
            source_entry_id=None,
            visibility=str((existing_fact or {}).get("visibility") or "assistant_visible"),
            scope=scope,
            sensitive=bool(mapping.get("sensitive")),
            enabled=True if existing_fact is None else bool((existing_fact or {}).get("enabled", True)),
            never_use=False if existing_fact is None else bool((existing_fact or {}).get("never_use", False)),
            metadata=metadata,
        )
        if self.epistemic is not None:
            try:
                self.sync_personal_fact(
                    fact=stored_fact,
                    raw_entry=None,
                    source_kind="profile_reconciliation",
                    basis="user_explicit",
                    validation_state="user_confirmed",
                )
            except Exception:  # noqa: BLE001
                pass
        return stored_fact

    @staticmethod
    def _profile_authority_summary() -> dict[str, Any]:
        claim_projection_fields: list[dict[str, Any]] = []
        settings_fields: list[dict[str, Any]] = []
        for item in PROFILE_FIELD_AUTHORITY_REGISTRY:
            field_summary = {
                "field": item.get("profile_field"),
                "title": item.get("title"),
                "authority_mode": item.get("authority_mode"),
                "authority_family": item.get("authority_family"),
                "fact_key": item.get("fact_key"),
            }
            if str(item.get("authority_mode") or "") == "claim_projection":
                claim_projection_fields.append(field_summary)
            else:
                settings_fields.append(field_summary)
        return {
            "claim_projection_fields": claim_projection_fields,
            "settings_fields": settings_fields,
        }

    @staticmethod
    def _fact_can_hydrate_profile(fact: dict[str, Any] | None) -> bool:
        if not fact:
            return False
        if not bool(fact.get("enabled", True)) or bool(fact.get("never_use")):
            return False
        confidence_type = str(fact.get("confidence_type") or "").strip().lower()
        metadata = dict(fact.get("metadata") or {})
        if confidence_type == "explicit":
            return True
        return bool(metadata.get("user_confirmed"))

    def _save_user_profile_patch(self, profile: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        next_profile = {**dict(profile or {}), **dict(patch or {})}
        return self.store.upsert_user_profile(
            self.office_id,
            display_name=next_profile.get("display_name"),
            favorite_color=next_profile.get("favorite_color"),
            food_preferences=next_profile.get("food_preferences"),
            transport_preference=next_profile.get("transport_preference"),
            weather_preference=next_profile.get("weather_preference"),
            travel_preferences=next_profile.get("travel_preferences"),
            home_base=next_profile.get("home_base"),
            current_location=next_profile.get("current_location"),
            location_preferences=next_profile.get("location_preferences"),
            maps_preference=next_profile.get("maps_preference"),
            prayer_notifications_enabled=next_profile.get("prayer_notifications_enabled"),
            prayer_habit_notes=next_profile.get("prayer_habit_notes"),
            communication_style=next_profile.get("communication_style"),
            assistant_notes=next_profile.get("assistant_notes"),
            important_dates=list(next_profile.get("important_dates") or []),
            related_profiles=list(next_profile.get("related_profiles") or []),
            inbox_watch_rules=list(next_profile.get("inbox_watch_rules") or []),
            inbox_keyword_rules=list(next_profile.get("inbox_keyword_rules") or []),
            inbox_block_rules=list(next_profile.get("inbox_block_rules") or []),
            source_preference_rules=list(next_profile.get("source_preference_rules") or []),
        )
