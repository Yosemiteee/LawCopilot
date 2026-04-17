import tempfile
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lawcopilot_api.app import create_app
from lawcopilot_api.epistemic.service import EpistemicService
from lawcopilot_api.persistence import Persistence
from lawcopilot_api.personal_model.service import PersonalModelService


def _service():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-personal-model-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    return store, PersonalModelService(store, "default-office", epistemic=epistemic)


class _StubRuntime:
    enabled = True

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def complete(self, prompt: str, events=None, *, task: str, **meta):
        return {"text": json.dumps(self.payload, ensure_ascii=False)}


def test_interview_flow_creates_raw_entries_explicit_facts_and_follow_ups():
    _, service = _service()

    session = service.start_session(module_keys=["work_style"], scope="personal")
    assert session["current_question"]["id"] == "planning_style"

    session = service.skip_question(session["id"])
    assert session["current_question"]["id"] == "preferred_work_time"

    answer = service.answer_question(
        session["id"],
        answer_text="Duruma göre",
        choice_value="flexible",
        answer_kind="choice",
    )

    assert answer["raw_entry"]["source"] == "interview"
    assert answer["raw_entry"]["confidence_type"] == "explicit"
    assert answer["stored_facts"][0]["confidence_type"] == "explicit"
    assert answer["stored_facts"][0]["scope"] == "personal"
    assert answer["stored_facts"][0]["source_entry_id"] == answer["raw_entry"]["id"]
    assert answer["stored_facts"][0]["epistemic_status"] in {"current", "unknown"}
    assert answer["session"]["current_question"]["id"] == "preferred_work_time_flex"


def test_question_engine_skips_already_known_fact_and_moves_to_next_gap():
    store, service = _service()
    store.upsert_personal_model_fact(
        "default-office",
        fact_id="pmf-known-communication",
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

    session = service.start_session(module_keys=["communication"], scope="personal")

    assert session["current_question"]["id"] == "assistant_behavior"


def test_retrieval_uses_only_relevant_non_sensitive_enabled_facts():
    store, service = _service()
    store.upsert_personal_model_fact(
        "default-office",
        fact_id="fact-communication-explicit",
        session_id=None,
        category="communication",
        fact_key="communication.style",
        title="İletişim tonu",
        value_text="Kısa ve net cevaplar",
        value_json={"text": "Kısa ve net cevaplar"},
        confidence=0.98,
        confidence_type="explicit",
        source_entry_id=None,
        visibility="assistant_visible",
        scope="personal",
        sensitive=False,
        enabled=True,
        never_use=False,
        metadata={},
    )
    store.upsert_personal_model_fact(
        "default-office",
        fact_id="fact-communication-sensitive",
        session_id=None,
        category="communication",
        fact_key="communication.private_secret",
        title="Hassas iletişim notu",
        value_text="Asla kullanma",
        value_json={"text": "Asla kullanma"},
        confidence=0.8,
        confidence_type="explicit",
        source_entry_id=None,
        visibility="assistant_visible",
        scope="personal",
        sensitive=True,
        enabled=True,
        never_use=False,
        metadata={},
    )
    store.upsert_personal_model_fact(
        "default-office",
        fact_id="fact-preferences-disabled",
        session_id=None,
        category="preferences",
        fact_key="reminder.tolerance",
        title="Hatırlatma tercihi",
        value_text="Daha aktif takip",
        value_json={"text": "Daha aktif takip"},
        confidence=0.75,
        confidence_type="inferred",
        source_entry_id=None,
        visibility="assistant_visible",
        scope="personal",
        sensitive=False,
        enabled=False,
        never_use=False,
        metadata={},
    )
    service.update_fact(
        "fact-communication-explicit",
        value_text="Kısa ve net cevaplar",
        note="Explicit fact claim substrate'e yazildi",
        enabled=True,
    )

    result = service.retrieve_relevant_facts("Anneme kısa bir mesaj yaz", scopes=["personal", "global"], limit=6)

    titles = [item["title"] for item in result["facts"]]
    assert "İletişim tonu" in titles
    assert "Hassas iletişim notu" not in titles
    assert "Hatırlatma tercihi" not in titles
    assert result["intent"]["name"] == "communication"
    assert result["facts"][0]["selection_reasons"]
    assert result["claim_summary_lines"]
    assert "İletişim tonu" in result["claim_summary_lines"][0]
    assert result["verification_gate"]["mode"] == "verified"


def test_consent_flow_requires_review_and_supports_update_delete():
    _, service = _service()
    suggestions = service.propose_chat_facts("Kısa ve net cevap seviyorum.", scope="personal")
    assert suggestions

    prior_messages = [
        {
            "role": "assistant",
            "source_context": {
                "personal_model_suggestion_ids": [suggestions[0]["id"]],
            },
        }
    ]
    consent_result = service.try_handle_chat_consent_reply("evet", prior_messages=prior_messages)
    assert consent_result
    assert consent_result["handled"] is True
    assert consent_result["decision"] == "accept"

    facts = service.list_facts(scope="personal")
    accepted = next((item for item in facts if item["fact_key"] == suggestions[0]["fact_key"]), None)
    assert accepted
    assert accepted["confidence_type"] == "inferred"
    assert accepted["metadata"]["user_confirmed"] is True
    assert accepted["source_entry_id"] is not None

    updated = service.update_fact(
        accepted["id"],
        value_text="Daha da kısa ve doğrudan cevaplar",
        note="Kullanıcı bunu düzeltti",
        enabled=True,
    )
    assert updated["value_text"] == "Daha da kısa ve doğrudan cevaplar"
    assert updated["metadata"]["correction_history"][-1]["action"] == "manual_edit"

    deleted = service.delete_fact(accepted["id"])
    assert deleted["deleted"] is True
    assert not service.list_facts(scope="personal")


def test_chat_learning_is_natural_and_rejection_suppresses_duplicates():
    _, service = _service()

    first = service.propose_chat_facts("Ben uzun mesajları sevmem, bana kısa ve net yaz.", scope="personal")

    assert first
    assert first[0]["fact_key"] == "communication.style"
    assert "kısa ve net" in str(first[0]["proposed_value_text"] or "").lower()
    assert "Mesajında" in str(first[0]["learning_reason"] or "")

    rejected = service.review_suggestion(first[0]["id"], decision="reject")
    assert rejected["decision"] == "rejected"

    second = service.propose_chat_facts("Ben uzun mesajları sevmem, bana kısa ve net yaz.", scope="personal")
    assert second == []


def test_sensitive_chat_learning_redacts_evidence_and_stays_out_of_retrieval():
    _, service = _service()

    suggestions = service.propose_chat_facts("Şifremi paylaşmam ama bana kısa yaz.", scope="personal")

    assert suggestions
    assert suggestions[0]["sensitive"] is True
    assert suggestions[0]["evidence"]["source_text_redacted"] is True

    accepted = service.review_suggestion(suggestions[0]["id"], decision="accept")
    assert accepted["fact"]["sensitive"] is True

    retrieval = service.retrieve_relevant_facts("Bana kısa bir mesaj hazırla", scopes=["personal"], limit=5)
    assert retrieval["facts"] == []


def test_external_profile_learning_surfaces_connected_account_and_document_facts_in_overview():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-personal-model-external-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    runtime = _StubRuntime(
        {
            "facts": [
                {
                    "category": "career",
                    "fact_key": "career.profile_summary",
                    "title": "Profesyonel profil",
                    "value_text": "Backend geliştirici çizgisinde; Python, FastAPI ve PostgreSQL tarafı belirgin.",
                    "confidence": 0.84,
                    "evidence_refs": ["email:google:thread-1", "document:1"],
                },
                {
                    "category": "career",
                    "fact_key": "career.application_activity",
                    "title": "Başvuru sinyali",
                    "value_text": "Kayıtlarda CV paylaşımı ve iş başvurusu süreci sinyali görünüyor.",
                    "confidence": 0.79,
                    "evidence_refs": ["email:google:thread-1"],
                },
            ]
        }
    )
    service = PersonalModelService(store, "default-office", epistemic=epistemic, runtime=runtime)
    root = store.save_workspace_root("default-office", "Workspace", temp_dir, "root-hash")
    document = store.upsert_workspace_document(
        "default-office",
        int(root["id"]),
        relative_path="docs/cv-sami.pdf",
        display_name="cv-sami.pdf",
        extension=".pdf",
        content_type="application/pdf",
        size_bytes=1024,
        mtime=1,
        checksum="cv-checksum",
        parser_status="parsed",
        indexed_status="indexed",
        document_language="tr",
        last_error=None,
    )
    store.replace_workspace_document_chunks(
        "default-office",
        int(root["id"]),
        int(document["id"]),
        [
            {
                "chunk_index": 0,
                "text": "Sami Yılmaz Backend Developer Python FastAPI PostgreSQL Docker",
                "token_count": 12,
                "metadata_json": "{}",
            }
        ],
    )
    store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-1",
        subject="Senior Backend Engineer application",
        participants=["HR <jobs@example.com>"],
        snippet="Your CV has been received for the Python backend role.",
        received_at="2026-04-16T09:00:00+00:00",
        unread_count=1,
        reply_needed=False,
        metadata={"sender": "HR <jobs@example.com>"},
    )

    overview = service.overview()

    assert any(item["fact_key"] == "career.profile_summary" for item in overview["facts"])
    assert "## Profesyonel Profil" in overview["profile_summary"]["markdown"]
    summary_fact = next(item for item in overview["facts"] if item["fact_key"] == "career.profile_summary")
    assert "Gmail e-postası" in str(summary_fact["source_summary"] or "")
    assert "Belge:" in str(summary_fact["source_summary"] or "")


def test_external_profile_learning_fallback_extracts_cv_and_skills_without_runtime():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-personal-model-fallback-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    service = PersonalModelService(store, "default-office", epistemic=epistemic)
    root = store.save_workspace_root("default-office", "Workspace", temp_dir, "root-hash")
    document = store.upsert_workspace_document(
        "default-office",
        int(root["id"]),
        relative_path="resume.pdf",
        display_name="resume.pdf",
        extension=".pdf",
        content_type="application/pdf",
        size_bytes=1024,
        mtime=1,
        checksum="resume-checksum",
        parser_status="parsed",
        indexed_status="indexed",
        document_language="tr",
        last_error=None,
    )
    store.replace_workspace_document_chunks(
        "default-office",
        int(root["id"]),
        int(document["id"]),
        [
            {
                "chunk_index": 0,
                "text": "Software Engineer Python FastAPI React PostgreSQL Docker",
                "token_count": 10,
                "metadata_json": "{}",
            }
        ],
    )
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-2",
        subject="Interview for backend role",
        participants=["Recruiter <jobs@example.com>"],
        snippet="We reviewed your resume and would like to continue.",
        received_at="2026-04-16T11:00:00+00:00",
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Recruiter <jobs@example.com>"},
    )

    result = service.sync_external_profile_learning(force=True)
    fact_keys = {item["fact_key"] for item in result["facts"]}

    assert "career.document_signal" in fact_keys
    assert "career.skill_summary" in fact_keys
    assert "career.application_activity" in fact_keys
    retrieval = service.retrieve_relevant_facts("CV ve becerilerim hakkında ne biliyorsun?", scopes=["global", "personal"], limit=6)
    assert any(item["fact_key"] == "career.skill_summary" for item in retrieval["facts"])


def test_external_profile_learning_ignores_inbound_family_shopping_messages_and_non_profile_emails():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-personal-model-owned-signals-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    service = PersonalModelService(store, "default-office")

    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp",
        conversation_ref="family-group",
        message_ref="wa-baba-shopping",
        sender="Babam",
        recipient="Aile",
        body="Kığılı'dan alışveriş yaptım, kargom gelecek.",
        direction="inbound",
        sent_at="2026-04-16T10:00:00+00:00",
        reply_needed=False,
        metadata={"chat_name": "Aile Grubu"},
    )
    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp",
        conversation_ref="career-chat",
        message_ref="wa-career-outbound",
        sender="Sami",
        recipient="Ayşe",
        body="Python backend rolü için CV'mi ve FastAPI tecrübemi birazdan göndereceğim.",
        direction="outbound",
        sent_at="2026-04-16T10:05:00+00:00",
        reply_needed=False,
        metadata={"chat_name": "Ayşe"},
    )
    store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="shopping-mail",
        subject="Siparişiniz kargoya verildi",
        participants=["shop@example.com"],
        snippet="Kığılı siparişiniz yarın teslim edilecek.",
        received_at="2026-04-16T11:00:00+00:00",
        unread_count=1,
        reply_needed=False,
        metadata={"sender": "Kiğılı <shop@example.com>"},
    )

    sources = service._collect_external_profile_learning_sources()
    labels = [str(item.get("label") or "") for item in sources["items"]]
    texts = [str(item.get("text") or "") for item in sources["items"]]

    assert all("Kığılı'dan alışveriş yaptım" not in text for text in texts)
    assert all("Siparişiniz kargoya verildi" not in text for text in texts)
    assert any("Python backend rolü için CV'mi" in text for text in texts)
    assert any("WhatsApp mesajı" in label for label in labels)


@pytest.mark.skip(reason="Sandboxed TestClient lifespan is currently nondeterministic; service and UI tests cover the same personal-model behavior.")
def test_personal_model_api_endpoints_flow(monkeypatch):
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-personal-model-api-"))
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(temp_dir / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(temp_dir / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(temp_dir / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_ALLOW_HEADER_AUTH", "true")
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "false")
    monkeypatch.setenv("LAWCOPILOT_INTEGRATION_WORKER_ENABLED", "false")
    monkeypatch.setenv("LAWCOPILOT_OPENCLAW_STATE_DIR", "")

    headers = {"x-role": "intern"}
    with TestClient(create_app()) as client:
        overview_before = client.get("/assistant/personal-model", headers=headers)
        assert overview_before.status_code == 200
        assert overview_before.json()["facts"] == []

        started = client.post(
            "/assistant/personal-model/interviews/start",
            headers=headers,
            json={"module_keys": ["communication"], "scope": "personal"},
        )
        assert started.status_code == 200
        session_id = started.json()["session"]["id"]
        assert started.json()["session"]["current_question"]["id"] == "communication_style"

        answered = client.post(
            f"/assistant/personal-model/interviews/{session_id}/answer",
            headers=headers,
            json={"answer_text": "Kısa ve net", "choice_value": "concise", "answer_kind": "choice"},
        )
        assert answered.status_code == 200
        assert answered.json()["stored_facts"][0]["fact_key"] == "communication.style"

        retrieval = client.post(
            "/assistant/personal-model/retrieval/preview",
            headers=headers,
            json={"query": "Bana kısa bir mesaj yaz", "scopes": ["personal"], "limit": 6},
        )
        assert retrieval.status_code == 200
        body = retrieval.json()
        assert body["intent"]["name"] == "communication"
        assert any(item["fact_key"] == "communication.style" for item in body["facts"])
        assert body["assistant_context_pack"]
        assert body["assistant_context_pack"][0]["family"] == "personal_model"
        assert body["assistant_context_pack"][0]["predicate"] == "communication.style"


@pytest.mark.skip(reason="Sandboxed TestClient lifespan is currently nondeterministic; service and UI tests cover the same personal-model behavior.")
def test_assistant_thread_uses_personal_model_and_requires_consent_before_learning(monkeypatch):
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-personal-model-thread-"))
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(temp_dir / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(temp_dir / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(temp_dir / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_ALLOW_HEADER_AUTH", "true")
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "false")
    monkeypatch.setenv("LAWCOPILOT_INTEGRATION_WORKER_ENABLED", "false")
    monkeypatch.setenv("LAWCOPILOT_OPENCLAW_STATE_DIR", "")

    headers = {"x-role": "intern"}
    with TestClient(create_app()) as client:
        started = client.post(
            "/assistant/personal-model/interviews/start",
            headers=headers,
            json={"module_keys": ["communication"], "scope": "personal"},
        )
        session_id = started.json()["session"]["id"]
        answered = client.post(
            f"/assistant/personal-model/interviews/{session_id}/answer",
            headers=headers,
            json={"answer_text": "Kısa ve net", "choice_value": "concise", "answer_kind": "choice"},
        )
        assert answered.status_code == 200

        reply = client.post(
            "/assistant/thread/messages",
            headers=headers,
            json={"content": "Anneme kısa bir mesaj yaz"},
        )
        assert reply.status_code == 200
        reply_body = reply.json()
        assert any(
            item.get("fact_key") == "communication.style"
            for item in list(((reply_body.get("personal_model_context") or {}).get("facts") or []))
        )

        suggestion_reply = client.post(
            "/assistant/thread/messages",
            headers=headers,
            json={"thread_id": reply_body["thread"]["id"], "content": "Kısa ve net cevap seviyorum."},
        )
        assert suggestion_reply.status_code == 200
        suggestion_body = suggestion_reply.json()
        assert suggestion_body["personal_model_suggestions"]

        consent_reply = client.post(
            "/assistant/thread/messages",
            headers=headers,
            json={"thread_id": reply_body["thread"]["id"], "content": "evet"},
        )
        assert consent_reply.status_code == 200
        consent_body = consent_reply.json()
        assert consent_body["generated_from"] == "assistant_personal_model_consent"
        assert "kaydettim" in str((consent_body.get("message") or {}).get("content") or "").lower()
