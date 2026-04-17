import tempfile
from pathlib import Path

from lawcopilot_api.epistemic.service import EpistemicService
from lawcopilot_api.memory_mutations import MemoryMutationService
from lawcopilot_api.persistence import Persistence
from lawcopilot_api.personal_model.service import PersonalModelService


class _KnowledgeBaseStub:
    def __init__(self) -> None:
        self.enabled = True
        self.ensure_calls = 0
        self.sync_calls: list[dict] = []

    def ensure_scaffold(self) -> None:
        self.ensure_calls += 1

    def sync_from_store(self, *, store, settings, reason: str) -> None:  # noqa: ANN001
        self.sync_calls.append({"reason": reason, "office_id": settings.office_id})


class _SettingsStub:
    office_id = "default-office"


def test_memory_mutation_service_records_external_signal_and_syncs_kb():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-memory-mutations-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    epistemic = EpistemicService(store, "default-office")
    kb = _KnowledgeBaseStub()
    service = MemoryMutationService(
        store=store,
        office_id="default-office",
        epistemic=epistemic,
        knowledge_base=kb,
        settings=_SettingsStub(),
    )

    event = service.record_external_signal(
        provider="youtube",
        event_type="video_summary",
        query="bu videoyu ozetle",
        matter_id=None,
        title="Yeni video",
        summary="Kısa özet",
        source_url="https://youtube.com/watch?v=test",
    )

    assert event is not None
    events = store.list_external_events("default-office", limit=5)
    assert events
    assert events[0]["provider"] == "youtube"
    assert kb.ensure_calls == 1
    assert kb.sync_calls[0]["reason"] == "assistant_external_signal:youtube:video_summary"


def test_personal_model_service_uses_memory_mutation_gateway_for_claim_sync():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-memory-mutations-fact-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    epistemic = EpistemicService(store, "default-office")
    gateway = MemoryMutationService(store=store, office_id="default-office", epistemic=epistemic)
    service = PersonalModelService(store, "default-office", memory_mutations=gateway)
    store.upsert_personal_model_fact(
        "default-office",
        fact_id="pmf-communication",
        session_id=None,
        category="communication",
        fact_key="communication.style",
        title="İletişim tonu",
        value_text="Kısa ve net",
        value_json={"text": "Kısa ve net"},
        confidence=0.99,
        confidence_type="explicit",
        source_entry_id=None,
        visibility="assistant_visible",
        scope="personal",
        sensitive=False,
        enabled=True,
        never_use=False,
        metadata={},
    )

    updated = service.update_fact("pmf-communication", value_text="Daha kısa ve net", enabled=True)
    resolution = epistemic.resolve_claim(subject_key="user", predicate="communication.style", scope="personal", include_blocked=True)

    assert updated["value_text"] == "Daha kısa ve net"
    assert resolution["status"] in {"current", "contested"}
    assert str((resolution.get("current_claim") or {}).get("object_value_text") or "") == "Daha kısa ve net"


def test_memory_mutation_service_updates_channel_memory_state_and_syncs_kb():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-memory-mutations-channel-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    kb = _KnowledgeBaseStub()
    service = MemoryMutationService(
        store=store,
        office_id="default-office",
        knowledge_base=kb,
        settings=_SettingsStub(),
    )
    thread = store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-memory-state",
        subject="Müvekkil görüşmesi",
        participants=["m@example.com"],
        snippet="Bu thread profile kalabilir.",
        received_at="2026-03-30T08:00:00+00:00",
        reply_needed=True,
        metadata={"sender": "Müvekkil"},
    )

    updated = service.set_channel_memory_state(
        channel_type="email_thread",
        record_id=int(thread["id"]),
        memory_state="approved_memory",
    )

    assert updated is not None
    assert updated["memory_state"] == "approved_memory"
    assert kb.ensure_calls == 1
    assert kb.sync_calls[0]["reason"] == f"channel_memory_state:email_thread:{thread['id']}:approved_memory"


def test_channel_memory_state_survives_future_upserts():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-memory-mutations-preserve-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    thread = store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-preserve-state",
        subject="İlk konu",
        participants=["m@example.com"],
        snippet="İlk özet",
        received_at="2026-03-30T08:00:00+00:00",
        reply_needed=True,
        metadata={"sender": "Müvekkil"},
    )
    store.set_channel_memory_state(
        "default-office",
        channel_type="email_thread",
        record_id=int(thread["id"]),
        memory_state="approved_memory",
    )

    updated = store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-preserve-state",
        subject="Yeni konu",
        participants=["m@example.com"],
        snippet="Yeni özet",
        received_at="2026-03-30T09:00:00+00:00",
        reply_needed=False,
        metadata={"sender": "Müvekkil", "sender_role": "Client"},
    )

    assert updated["memory_state"] == "approved_memory"
    assert updated["metadata"]["memory_state"] == "approved_memory"
    assert updated["metadata"]["sender_role"] == "Client"


def test_profile_reconciliation_syncs_profile_fields_into_personal_facts():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-profile-reconcile-profile-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    epistemic = EpistemicService(store, "default-office")
    kb = _KnowledgeBaseStub()
    service = MemoryMutationService(
        store=store,
        office_id="default-office",
        epistemic=epistemic,
        knowledge_base=kb,
        settings=_SettingsStub(),
    )
    profile = store.upsert_user_profile(
        "default-office",
        communication_style="Kısa ve net",
        assistant_notes="Öncelikli destek alanları: belge takibi.",
        transport_preference="Tren kullanmayı severim.",
    )

    result = service.reconcile_user_profile(profile=profile, authority="profile", reason="test_profile_reconcile")
    facts = store.list_personal_model_facts("default-office", include_disabled=True, limit=20)
    fact_keys = {str(item.get("fact_key") or ""): item for item in facts}

    assert result["changed"] is True
    assert result["authority_model"] == "predicate_family_split"
    assert [item["field"] for item in result["synced_facts"]] == [
        "communication_style",
        "assistant_notes",
        "transport_preference",
    ]
    assert fact_keys["communication.style"]["value_text"] == "Kısa ve net"
    assert fact_keys["assistant.support_focus"]["value_text"] == "Öncelikli destek alanları: belge takibi."
    assert fact_keys["transport.preference"]["value_text"] == "Tren kullanmayı severim."
    assert any(item["field"] == "communication_style" for item in result["claim_projection_fields"])
    assert any(item["field"] == "maps_preference" for item in result["settings_fields"])
    assert kb.sync_calls[-1]["reason"] == "test_profile_reconcile"


def test_profile_reconciliation_hydrates_profile_from_confirmed_fact():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-profile-reconcile-fact-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    kb = _KnowledgeBaseStub()
    service = MemoryMutationService(
        store=store,
        office_id="default-office",
        knowledge_base=kb,
        settings=_SettingsStub(),
    )
    store.upsert_user_profile("default-office", display_name="Sami")
    store.upsert_personal_model_fact(
        "default-office",
        fact_id="pmf-communication-style",
        session_id=None,
        category="communication",
        fact_key="communication.style",
        title="İletişim tonu",
        value_text="Daha detaylı",
        value_json={"text": "Daha detaylı"},
        confidence=0.98,
        confidence_type="explicit",
        source_entry_id=None,
        visibility="assistant_visible",
        scope="personal",
        sensitive=False,
        enabled=True,
        never_use=False,
        metadata={"source_kind": "guided_interview"},
    )

    result = service.reconcile_user_profile(authority="fact", reason="test_fact_reconcile")
    profile = store.get_user_profile("default-office")

    assert result["changed"] is True
    assert [item["field"] for item in result["hydrated_fields"]] == ["communication_style"]
    assert profile["communication_style"] == "Daha detaylı"
    assert kb.sync_calls[-1]["reason"] == "test_fact_reconcile"


def test_profile_reconciliation_does_not_project_settings_only_fields_into_facts():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-profile-reconcile-settings-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    epistemic = EpistemicService(store, "default-office")
    service = MemoryMutationService(
        store=store,
        office_id="default-office",
        epistemic=epistemic,
        knowledge_base=_KnowledgeBaseStub(),
        settings=_SettingsStub(),
    )
    profile = store.upsert_user_profile(
        "default-office",
        communication_style="Kısa ve net",
        maps_preference="Apple Maps",
        prayer_notifications_enabled=True,
    )

    result = service.reconcile_user_profile(profile=profile, authority="profile", reason="test_settings_boundary")
    facts = store.list_personal_model_facts("default-office", include_disabled=True, limit=20)
    fact_keys = {str(item.get("fact_key") or "") for item in facts}

    assert result["changed"] is True
    assert [item["field"] for item in result["synced_facts"]] == ["communication_style"]
    assert "communication.style" in fact_keys
    assert "maps.preference" not in fact_keys
    assert any(item["field"] == "maps_preference" for item in result["settings_fields"])
    assert any(item["field"] == "prayer_notifications_enabled" for item in result["settings_fields"])
