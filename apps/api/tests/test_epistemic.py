from __future__ import annotations

import tempfile
from pathlib import Path

from lawcopilot_api.epistemic import EpistemicService, get_precedence_policy, resolve_predicate_family
from lawcopilot_api.knowledge_base import KnowledgeBaseService
from lawcopilot_api.persistence import Persistence
from lawcopilot_api.personal_model.service import PersonalModelService


def _services():
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-epistemic-"))
    store = Persistence(temp_dir / "lawcopilot.db")
    epistemic = EpistemicService(store, "default-office")
    return temp_dir, store, epistemic


def test_resolver_prefers_explicit_claim_over_inferred_claim() -> None:
    _, _, epistemic = _services()
    artifact = epistemic.record_artifact(
        artifact_kind="chat_message",
        source_kind="chat",
        summary="Kullanici iletisim tercihini anlatiyor",
        payload={"text": "Bana kisa yaz"},
    )
    epistemic.record_claim(
        subject_key="user",
        predicate="communication.style",
        object_value_text="Detayli cevaplar",
        scope="personal",
        epistemic_basis="inferred",
        validation_state="pending",
        artifact_id=str(artifact.get("id") or ""),
    )
    epistemic.record_claim(
        subject_key="user",
        predicate="communication.style",
        object_value_text="Kisa ve net cevaplar",
        scope="personal",
        epistemic_basis="user_explicit",
        validation_state="user_confirmed",
        artifact_id=str(artifact.get("id") or ""),
        claim_id="explicit-style-claim",
    )

    resolved = epistemic.resolve_claim(
        subject_key="user",
        predicate="communication.style",
        scope="personal",
        include_blocked=True,
    )

    assert resolved["status"] == "current"
    assert resolved["current_claim"]["id"] == "explicit-style-claim"
    assert resolved["current_claim"]["object_value_text"] == "Kisa ve net cevaplar"


def test_personal_model_answer_creates_artifact_and_claim() -> None:
    _, store, epistemic = _services()
    service = PersonalModelService(store, "default-office", epistemic=epistemic)

    session = service.start_session(module_keys=["communication"], scope="personal")
    answered = service.answer_question(
        session["id"],
        answer_text="Kısa ve net",
        choice_value="concise",
        answer_kind="choice",
    )

    fact = answered["stored_facts"][0]
    artifacts = store.list_epistemic_artifacts("default-office", artifact_kind="personal_model_entry", limit=20)
    claims = store.list_epistemic_claims(
        "default-office",
        subject_key="user",
        predicate="communication.style",
        scope="personal",
        include_blocked=True,
        limit=20,
    )
    resolved = epistemic.resolve_claim(
        subject_key="user",
        predicate="communication.style",
        scope="personal",
        include_blocked=True,
    )

    assert artifacts
    assert claims
    assert claims[0]["metadata"]["fact_id"] == fact["id"]
    assert fact["epistemic_status"] == "current"
    assert fact["epistemic_claim_id"]
    assert resolved["current_claim"]["object_value_text"] == "Kısa ve net"
    assert resolved["current_claim"]["epistemic_basis"] == "user_explicit"


def test_personal_model_update_supersedes_prior_claim() -> None:
    _, store, epistemic = _services()
    service = PersonalModelService(store, "default-office", epistemic=epistemic)
    session = service.start_session(module_keys=["communication"], scope="personal")
    answered = service.answer_question(
        session["id"],
        answer_text="Kısa ve net",
        choice_value="concise",
        answer_kind="choice",
    )

    updated = service.update_fact(
        answered["stored_facts"][0]["id"],
        value_text="Detaylı ama düzenli",
        note="Yeni tercih",
    )
    claims = store.list_epistemic_claims(
        "default-office",
        subject_key="user",
        predicate="communication.style",
        scope="personal",
        include_blocked=True,
        limit=20,
    )
    resolved = epistemic.resolve_claim(
        subject_key="user",
        predicate="communication.style",
        scope="personal",
        include_blocked=True,
    )
    superseded = [item for item in claims if str(item.get("validation_state") or "") == "superseded"]

    assert updated["value_text"] == "Detaylı ama düzenli"
    assert superseded
    assert resolved["current_claim"]["object_value_text"] == "Detaylı ama düzenli"


def test_assistant_file_back_creates_quarantined_claim_and_is_excluded_from_search() -> None:
    temp_dir, store, epistemic = _services()
    kb = KnowledgeBaseService(temp_dir / "personal-kb", "default-office", epistemic=epistemic)

    file_back = kb.maybe_file_back_response(
        kind="assistant_reply",
        title="Ürün stok cevabı",
        content="Kırmızı beden tükendi. Pembe seçenek hâlâ mevcut görünüyor ve müşteriye alternatif renk önerisiyle birlikte nazik bir dönüş yapılmalı.",
        metadata={"page_key": "recommendations", "record_type": "recommendation"},
        scope="personal",
        sensitivity="medium",
    )
    claims = store.list_epistemic_claims(
        "default-office",
        subject_key="assistant_output:assistant_reply",
        predicate="narrative",
        scope="personal",
        include_blocked=True,
        limit=20,
    )
    search = kb.search("Kırmızı beden tükendi mi?", scopes=["personal"], limit=8)

    assert file_back is not None
    assert claims
    assert claims[0]["self_generated"] is True
    assert claims[0]["retrieval_eligibility"] == "quarantined"
    assert search["items"] == []


def test_profile_sync_promotes_explicit_profile_claims() -> None:
    temp_dir, store, epistemic = _services()
    store.upsert_user_profile(
        "default-office",
        display_name="Sami",
        communication_style="Kısa ve net",
        transport_preference="Genelde tren kullanırım.",
        related_profiles=[
            {
                "name": "Ayşe",
                "relationship": "eş",
                "preferences": "Tarihi mekanları sever",
                "notes": "Nazik hatırlatma iyi gelir.",
            }
        ],
    )
    store.upsert_assistant_runtime_profile(
        "default-office",
        assistant_name="Ada",
        role_summary="Personal operating assistant",
        tone="Kısa ve gerekçeli",
    )
    kb = KnowledgeBaseService(temp_dir / "personal-kb", "default-office", epistemic=epistemic)

    kb.sync_from_store(store=store, reason="profile_claim_sync")

    user_claims = store.list_epistemic_claims(
        "default-office",
        subject_key="user",
        predicate="communication_style",
        scope="personal",
        include_blocked=True,
        limit=10,
    )
    resolved_user_claim = epistemic.resolve_claim(
        subject_key="user",
        predicate="communication_style",
        scope="personal",
        include_blocked=True,
    )
    contact_claims = store.list_epistemic_claims(
        "default-office",
        subject_key="contact:ayse",
        predicate="preferences",
        scope="personal",
        include_blocked=True,
        limit=10,
    )

    assert user_claims
    assert resolved_user_claim["current_claim"]["epistemic_basis"] == "user_explicit"
    assert contact_claims
    assert "Tarihi mekanları sever" in contact_claims[0]["object_value_text"]


def test_user_preferences_ingest_promotes_explicit_claim() -> None:
    temp_dir, store, epistemic = _services()
    kb = KnowledgeBaseService(temp_dir / "personal-kb", "default-office", epistemic=epistemic)

    kb.ingest(
        source_type="user_preferences",
        content="Bana kısa ve net cevap ver.",
        title="İletişim tercihi",
        metadata={"field": "communication_style", "scope": "personal"},
        occurred_at=None,
        source_ref="manual:test",
        tags=["preferences"],
    )

    resolved = epistemic.resolve_claim(
        subject_key="user",
        predicate="communication_style",
        scope="personal",
        include_blocked=True,
    )

    assert resolved["status"] == "current"
    assert resolved["current_claim"]["epistemic_basis"] == "user_explicit"


def test_claim_lifecycle_marks_explicit_recent_fact_as_hot_and_old_inference_as_cold() -> None:
    _, store, epistemic = _services()
    recent = epistemic.record_claim(
        subject_key="user",
        predicate="communication.style",
        object_value_text="Kısa ve net",
        scope="personal",
        epistemic_basis="user_explicit",
        validation_state="user_confirmed",
        metadata={},
        claim_id="claim-hot",
    )
    older = epistemic.record_claim(
        subject_key="user",
        predicate="planning.preference",
        object_value_text="Gece çalışmayı seviyor olabilir",
        scope="personal",
        epistemic_basis="inferred",
        validation_state="pending",
        retrieval_eligibility="demoted",
        metadata={},
        claim_id="claim-cold",
    )
    store.update_epistemic_claim(
        "default-office",
        "claim-cold",
        metadata={"test_case": "aged"},
    )
    row = store.get_epistemic_claim("default-office", "claim-cold")
    assert row is not None
    row["updated_at"] = "2025-01-01T00:00:00+00:00"

    hot_profile = epistemic.describe_claim_memory(
        claim=recent,
        support=epistemic.inspect_claim_support(claim=recent),
    )
    cold_profile = epistemic.describe_claim_memory(
        claim=row,
        support=epistemic.inspect_claim_support(claim=row),
    )

    assert hot_profile["memory_tier"] == "hot"
    assert cold_profile["memory_tier"] == "cold"
    assert float(hot_profile["salience_score"]) > float(cold_profile["salience_score"])
    assert "kısa ve net" in str(recent["object_value_text"]).lower()


def test_resolver_marks_assistant_only_support_chain_as_contaminated() -> None:
    _, _, epistemic = _services()
    assistant_output = epistemic.record_assistant_output(
        kind="assistant_reply",
        title="Stok cevabı taslağı",
        content="Kırmızı beden tükendi, pembe seçenek mevcut olabilir.",
        scope="professional",
        sensitivity="medium",
    )
    contaminated_claim = epistemic.record_claim(
        subject_key="product:sku-42",
        predicate="inventory.status",
        object_value_text="Kırmızı beden tükendi",
        scope="professional",
        epistemic_basis="inferred",
        validation_state="pending",
        metadata={"supporting_claim_ids": [assistant_output["claim"]["id"]]},
    )

    resolved = epistemic.resolve_claim(
        subject_key="product:sku-42",
        predicate="inventory.status",
        scope="professional",
        include_blocked=True,
    )

    assert contaminated_claim["id"] == resolved["current_claim"]["id"]
    assert resolved["status"] == "contaminated"
    assert resolved["current_claim_support"]["contaminated"] is True
    assert "assistant_only_support_chain" in resolved["current_claim_support"]["reason_codes"]


def test_claim_support_cycle_is_detected() -> None:
    _, store, epistemic = _services()
    first = epistemic.record_claim(
        claim_id="claim-a",
        subject_key="user",
        predicate="planning.style",
        object_value_text="Checklist ile çalışır",
        scope="personal",
        epistemic_basis="inferred",
        validation_state="pending",
        metadata={"supporting_claim_ids": ["claim-b"]},
    )
    second = epistemic.record_claim(
        claim_id="claim-b",
        subject_key="user",
        predicate="planning.style",
        object_value_text="Checklist ile çalışır",
        scope="personal",
        epistemic_basis="inferred",
        validation_state="pending",
        metadata={"supporting_claim_ids": ["claim-a"]},
    )

    support = epistemic.inspect_claim_support(claim_id=str(first["id"]))
    resolved = epistemic.resolve_claim(
        subject_key="user",
        predicate="planning.style",
        scope="personal",
        include_blocked=True,
    )

    assert store.get_epistemic_claim("default-office", str(second["id"])) is not None
    assert support["cycle_detected"] is True
    assert "cycle_detected" in support["reason_codes"]
    assert resolved["status"] == "contaminated"


def test_generic_message_contact_record_does_not_promote_contact_summary_claim() -> None:
    temp_dir, store, epistemic = _services()
    kb = KnowledgeBaseService(temp_dir / "personal-kb", "default-office", epistemic=epistemic)

    kb.ingest(
        source_type="messages",
        title="Ayşe",
        content="Merhaba, stokta bu ürün var mı?",
        metadata={
            "provider": "whatsapp",
            "conversation_ref": "conversation-1",
            "message_ref": "message-1",
            "reply_needed": True,
            "scope": "personal",
            "sensitivity": "high",
        },
        source_ref="messages:whatsapp:message-1",
        tags=["messages"],
    )

    claims = store.list_epistemic_claims(
        "default-office",
        subject_key="contact:ayse",
        predicate="profile.summary",
        scope="personal",
        include_blocked=True,
        limit=10,
    )

    assert claims == []


def test_precedence_policy_prefers_user_explicit_for_user_preference_family() -> None:
    _, _, epistemic = _services()
    epistemic.record_claim(
        subject_key="user",
        predicate="communication_style",
        object_value_text="Uzun ve detaylı cevaplar",
        scope="personal",
        epistemic_basis="connector_observed",
        validation_state="source_supported",
        claim_id="connector-preference",
    )
    epistemic.record_claim(
        subject_key="user",
        predicate="communication_style",
        object_value_text="Kısa ve net cevaplar",
        scope="personal",
        epistemic_basis="user_explicit",
        validation_state="user_confirmed",
        claim_id="explicit-preference",
    )

    resolved = epistemic.resolve_claim(
        subject_key="user",
        predicate="communication_style",
        scope="personal",
        include_blocked=True,
    )

    assert resolve_predicate_family(subject_key="user", predicate="communication_style") == "user_preference"
    assert get_precedence_policy(subject_key="user", predicate="communication_style").family == "user_preference"
    assert resolved["current_claim"]["id"] == "explicit-preference"


def test_precedence_policy_prefers_connector_observation_for_workspace_fact_family() -> None:
    _, _, epistemic = _services()
    epistemic.record_claim(
        subject_key="product:sku-42",
        predicate="inventory.status",
        object_value_text="Kırmızı beden stokta var",
        scope="professional",
        epistemic_basis="assistant_generated",
        validation_state="pending",
        self_generated=True,
        retrieval_eligibility="quarantined",
        claim_id="assistant-narrative-stock",
    )
    epistemic.record_claim(
        subject_key="product:sku-42",
        predicate="inventory.status",
        object_value_text="Kırmızı beden tükendi",
        scope="professional",
        epistemic_basis="connector_observed",
        validation_state="source_supported",
        claim_id="connector-stock",
    )

    resolved = epistemic.resolve_claim(
        subject_key="product:sku-42",
        predicate="inventory.status",
        scope="professional",
        include_blocked=True,
    )

    assert resolve_predicate_family(subject_key="product:sku-42", predicate="inventory.status") == "workspace_fact"
    assert resolved["status"] == "current"
    assert resolved["current_claim"]["id"] == "connector-stock"


def test_safe_structured_connector_hint_is_promoted_to_claim() -> None:
    temp_dir, store, epistemic = _services()
    kb = KnowledgeBaseService(temp_dir / "personal-kb", "default-office", epistemic=epistemic)

    kb.ingest(
        source_type="tasks",
        title="Görev durum kaydı",
        content="Durum: in_progress",
        metadata={
            "scope": "personal",
            "epistemic_claim_hints": [
                {
                    "subject_key": "task:42",
                    "predicate": "status",
                    "object_value_text": "in_progress",
                    "display_label": "Görev durumu",
                }
            ],
        },
        source_ref="task:test:42",
        tags=["tasks"],
    )

    claims = store.list_epistemic_claims(
        "default-office",
        subject_key="task:42",
        predicate="status",
        scope=None,
        include_blocked=True,
        limit=10,
    )

    assert claims
    assert claims[0]["epistemic_basis"] == "connector_observed"


def test_unsafe_contact_preference_hint_from_connector_is_not_promoted() -> None:
    temp_dir, store, epistemic = _services()
    kb = KnowledgeBaseService(temp_dir / "personal-kb", "default-office", epistemic=epistemic)

    kb.ingest(
        source_type="messages",
        title="Ayşe mesajı",
        content="Bebek hediyesi olarak çikolata önerildi.",
        metadata={
            "scope": "personal",
            "provider": "whatsapp",
            "epistemic_claim_hints": [
                {
                    "subject_key": "contact:ayse",
                    "predicate": "preferences",
                    "object_value_text": "Çikolatayı sever",
                    "display_label": "Kişi tercihi",
                }
            ],
        },
        source_ref="messages:test:unsafe-contact-preference",
        tags=["messages"],
    )

    claims = store.list_epistemic_claims(
        "default-office",
        subject_key="contact:ayse",
        predicate="preferences",
        scope="personal",
        include_blocked=True,
        limit=10,
    )

    assert claims == []
