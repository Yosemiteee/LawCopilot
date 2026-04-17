from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from lawcopilot_api.app import create_app
from lawcopilot_api.epistemic.service import EpistemicService
from lawcopilot_api.integrations.repository import IntegrationRepository
from lawcopilot_api.knowledge_base import KnowledgeBaseService
from lawcopilot_api.knowledge_base.connectors import BrowserContextConnector, ConsumerSignalsConnector, ElasticIntegrationConnector, FilesConnector, NotesConnector
from lawcopilot_api.observability import StructuredLogger
from lawcopilot_api.persistence import Persistence
from lawcopilot_api.schemas import (
    AssistantActionDecisionRequest,
    AssistantActionGenerateRequest,
    AssistantRuntimeBlueprintRequest,
    CoachingGoalUpsertRequest,
    CoachingProgressLogRequest,
    AssistantLocationContextRequest,
    AssistantThreadMessageFeedbackRequest,
    AssistantThreadMessageStarRequest,
    GoogleEmailThreadMirrorRequest,
    GoogleSyncRequest,
    KnowledgeMemoryCorrectionRequest,
    KnowledgeBaseIngestRequest,
    KnowledgeBaseSearchRequest,
    KnowledgeSynthesisRequest,
    KnowledgeWikiCompileRequest,
    MemoryForgetRequest,
    MemoryScopeChangeRequest,
    OrchestrationRunRequest,
    QueryIn,
    RecommendationFeedbackRequest,
    RecommendationRequest,
    TokenRequest,
    TriggerEvaluationRequest,
)


os.environ.setdefault("LAWCOPILOT_ALLOW_LOCAL_TOKEN_BOOTSTRAP", "true")


class _FakeArticleRuntime:
    enabled = True
    runtime_mode = "advanced-openclaw"
    provider_type = "local-test"

    def complete(self, prompt, events=None, *, task: str, **meta):  # noqa: ANN001
        return {
            "text": json.dumps(
                {
                    "summary": "Bu kavram kullanicinin tercih ve davranis oruntulerini bir wiki article olarak ozetler.",
                    "detailed_explanation": "Derlenmis kayitlar birlikte ele alindiginda yardim stratejileri daha tutarli hale geliyor.",
                    "patterns": ["Kayitlar ayni konu etrafinda tekrarlaniyor."],
                    "inferred_insights": ["Bu article proactive help icin yuksek deger tasiyor."],
                    "cross_links": [{"key": "topic:planning-style", "title": "Planning Style", "reason": "shared evidence"}],
                    "strategy_notes": ["Preview-first plan yardimini oncele."],
                },
                ensure_ascii=False,
            ),
            "provider": "local-test",
            "model": "fake-article-writer",
            "runtime_mode": "advanced-openclaw",
        }


class _CountingArticleRuntime(_FakeArticleRuntime):
    def __init__(self) -> None:
        self.call_count = 0

    def complete(self, prompt, events=None, *, task: str, **meta):  # noqa: ANN001
        self.call_count += 1
        return super().complete(prompt, events=events, task=task, **meta)


def test_knowledge_base_sync_from_store_creates_scaffold(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        transport_preference="Genelde tren kullanırım.",
        food_preferences="Akşamları hafif yemekleri tercih ederim.",
        communication_style="Kısa, net ve sıcak.",
        assistant_notes="Akşam planımı mümkünse hafiflet.",
        related_profiles=[
            {
                "id": "partner",
                "name": "Ayşe",
                "relationship": "eş",
                "preferences": "Tarihi mekanları sever",
                "notes": "Nazik hatırlatma iyi gelir.",
                "important_dates": [],
            }
        ],
    )
    store.upsert_assistant_runtime_profile(
        office_id,
        assistant_name="Ada",
        role_summary="Personal operating assistant",
        tone="Kısa ve gerekçeli",
        soul_notes="Kritik aksiyonlarda onay iste.",
        tools_notes="Her sabah ajandayı ve açık taslakları tara.",
        heartbeat_extra_checks=["Yoğun takvim günlerini işaretle"],
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    result = knowledge_base.sync_from_store(store=store, reason="test_sync")
    status = knowledge_base.status(ensure=False, previews=False)

    assert "persona" in result["updated_pages"]
    assert status["raw_source_count"] >= 1
    assert (knowledge_base.base_dir / "raw").exists()
    assert (knowledge_base.base_dir / "wiki" / "persona.md").exists()
    assert (knowledge_base.base_dir / "system" / "AGENTS.md").exists()
    assert (knowledge_base.base_dir / "system" / "CONTROL.md").exists()

    page_counts = {item["key"]: item["record_count"] for item in status["pages"]}
    assert page_counts["persona"] >= 3
    assert page_counts["preferences"] >= 2
    assert page_counts["routines"] >= 1
    assert page_counts["contacts"] >= 1


def test_sync_from_store_batches_wiki_render_to_single_pass(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        food_preferences="Akşamları hafif yemekleri tercih ederim.",
        communication_style="Kısa ve net.",
    )
    store.upsert_assistant_runtime_profile(
        office_id,
        assistant_name="Ada",
        role_summary="Personal operating assistant",
        tone="Kısa ve gerekçeli",
    )
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    knowledge_base.ensure_scaffold()

    render_calls: list[int] = []
    original_render_all = knowledge_base._render_all

    def _counted_render(state):  # noqa: ANN001
        render_calls.append(1)
        return original_render_all(state)

    knowledge_base._render_all = _counted_render  # type: ignore[method-assign]
    knowledge_base.sync_from_store(store=store, reason="batched_render_test")

    assert len(render_calls) == 1


def _route_endpoint(app, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) != path:
            continue
        if method.upper() not in getattr(route, "methods", set()):
            continue
        return route.endpoint
    raise AssertionError(f"route not found: {method} {path}")


def test_knowledge_base_api_flow(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    ingest_kb = _route_endpoint(app, "/assistant/knowledge-base/ingest", "POST")
    get_recommendations = _route_endpoint(app, "/assistant/recommendations", "POST")
    submit_feedback = _route_endpoint(app, "/assistant/recommendations/{recommendation_id}/feedback", "POST")
    run_reflection = _route_endpoint(app, "/assistant/knowledge-base/reflection", "POST")
    get_kb = _route_endpoint(app, "/assistant/knowledge-base", "GET")

    token_body = issue_token(TokenRequest(subject="tester", role="lawyer"))
    token = token_body["access_token"]
    authorization = f"Bearer {token}"

    ingest_res = ingest_kb(
        KnowledgeBaseIngestRequest(
            source_type="user_preferences",
            title="Ulaşım tercihi",
            content="Genelde trenle seyahat etmeyi seviyorum.",
            metadata={"field": "travel_preferences"},
            tags=["travel", "preferences"],
        ),
        authorization=authorization,
    )
    assert "preferences" in ingest_res["compile"]["updated_pages"]

    rec_res = get_recommendations(
        RecommendationRequest(
            current_context="Bugün namaz vakti için yakınımda bir yer var mı?",
            location_context="Kadıköy",
            limit=3,
            persist=True,
        ),
        authorization=authorization,
    )
    recommendations = rec_res["items"]
    assert recommendations
    assert recommendations[0]["explainability"]["short"]

    feedback_res = submit_feedback(
        recommendations[0]["id"],
        RecommendationFeedbackRequest(outcome="rejected", note="Şimdilik istemiyorum."),
        authorization=authorization,
    )
    assert feedback_res["outcome"] == "rejected"

    reflection_res = run_reflection(authorization=authorization)
    assert "summary" in reflection_res

    kb_body = get_kb(previews=False, authorization=authorization)
    assert kb_body["enabled"] is True

    recent_events = StructuredLogger(tmp_path / "events.log.jsonl").query(limit=40, since_seconds=3600)
    event_names = {str(item.get("event") or "") for item in recent_events}
    assert "pilot_recommendation_feedback" in event_names
    assert "personal_kb_reflection_completed" in event_names
    assert kb_body["raw_source_count"] >= 1
    assert any(page["key"] == "preferences" and page["record_count"] >= 1 for page in kb_body["pages"])


def test_assistant_message_feedback_updates_runtime_contract_and_kb(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_assistant_runtime_profile(
        office_id,
        assistant_name="Ada",
        role_summary="Genel amaçlı çekirdek asistan",
        tone="Net ve sıcak",
        assistant_forms=[],
        behavior_contract={},
        evolution_history=[],
        heartbeat_extra_checks=[],
    )
    thread = store.create_assistant_thread(office_id, created_by="tester", title="Asistan")
    message = store.append_assistant_message(
        office_id,
        thread_id=int(thread["id"]),
        role="assistant",
        content="Bugün için detaylı plan hazırladım.\n- Okuma hedefini kontrol et\n- Kısa yürüyüş ekle\n- Akşam değerlendirmesi yap",
        linked_entities=[],
        tool_suggestions=[],
        draft_preview=None,
        source_context={"why_now": "Due check-in", "action_ladder": {"current_stage": "suggest"}},
        requires_approval=False,
        generated_from="daily_plan",
        ai_provider="test",
        ai_model="test-model",
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    result = knowledge_base.record_assistant_message_feedback(
        store=store,
        message_id=int(message["id"]),
        feedback_value="disliked",
        note="Daha kısa ve daha az takip istiyorum.",
    )
    runtime_profile = store.get_assistant_runtime_profile(office_id)
    state = knowledge_base._load_state()

    assert result["feedback_value"] == "disliked"
    assert runtime_profile["behavior_contract"]["explanation_style"] == "concise"
    assert runtime_profile["behavior_contract"]["initiative_level"] == "low"
    assert runtime_profile["behavior_contract"]["follow_up_style"] == "on_request"
    preference_keys = {
        str(record.get("key") or "")
        for record in ((state.get("pages") or {}).get("preferences") or {}).get("records", [])
        if isinstance(record, dict)
    }
    routine_keys = {
        str(record.get("key") or "")
        for record in ((state.get("pages") or {}).get("routines") or {}).get("records", [])
        if isinstance(record, dict)
    }
    assert "assistant_explanation_style_preference" in preference_keys
    assert "assistant_follow_up_preference" in routine_keys


def test_assistant_message_feedback_api_route_persists_feedback(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "lawcopilot.db"
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(db_path))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    store = Persistence(db_path)
    thread = store.create_assistant_thread("default-office", created_by="tester", title="Asistan")
    message = store.append_assistant_message(
        "default-office",
        thread_id=int(thread["id"]),
        role="assistant",
        content="İstersen sana akşam için kısa bir plan çıkarayım.",
        linked_entities=[],
        tool_suggestions=[],
        draft_preview=None,
        source_context={"why_now": "Evening planning"},
        requires_approval=False,
        generated_from="smart_reminder",
        ai_provider="test",
        ai_model="test-model",
    )

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    update_feedback = _route_endpoint(app, "/assistant/thread/messages/{message_id}/feedback", "PATCH")

    token_body = issue_token(TokenRequest(subject="tester", role="intern"))
    authorization = f"Bearer {token_body['access_token']}"

    response = update_feedback(
        int(message["id"]),
        AssistantThreadMessageFeedbackRequest(feedback_value="liked"),
        authorization=authorization,
    )

    assert response["message"]["feedback_value"] == "liked"
    assert response["assistant_runtime_profile"]["behavior_contract"]["initiative_level"] == "high"
    assert response["memory_overview"]["counts"]["records"] >= 1


def test_assistant_message_feedback_reason_updates_contact_profile_and_contacts_page(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        related_profiles=[
            {
                "id": "mother",
                "name": "Anne",
                "relationship": "anne",
                "preferences": "",
                "notes": "",
                "important_dates": [],
            }
        ],
    )
    thread = store.create_assistant_thread(office_id, created_by="tester", title="Asistan")
    message = store.append_assistant_message(
        office_id,
        thread_id=int(thread["id"]),
        role="assistant",
        content="Annene şöyle yazabilirsin: Canım annem, düşündüğümde yüzüm gülüyor. İstersen yanına küçük bir çiçek de al.",
        linked_entities=[{"type": "contact", "id": "mother", "label": "Anne"}],
        tool_suggestions=[],
        draft_preview=None,
        source_context={"recipient": "Anne"},
        requires_approval=False,
        generated_from="message_draft",
        ai_provider="test",
        ai_model="test-model",
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    result = knowledge_base.record_assistant_message_feedback(
        store=store,
        message_id=int(message["id"]),
        feedback_value="liked",
        note="Anneme sıcak ve nazik yazman çok iyi olmuş, çiçek önerin de uygundu.",
    )
    profile = store.get_user_profile(office_id)
    state = knowledge_base._load_state()
    mother = next(item for item in profile["related_profiles"] if str(item.get("id")) == "mother")
    contact_records = ((state.get("pages") or {}).get("contacts") or {}).get("records", [])
    contact_keys = {str(item.get("key") or "") for item in contact_records if isinstance(item, dict)}

    assert result["semantic_learning"]["target_contact"]["profile_id"] == "mother"
    assert "İletişim: Anne ile iletişimde sıcak, nazik ton olumlu karşılanıyor." in str(mother.get("preferences") or "")
    assert "Hediye: çiçek önerileri olumlu karşılanıyor." in str(mother.get("preferences") or "")
    assert "contact-style:mother" in contact_keys
    assert "contact-gift:mother:cicek" in contact_keys


def test_assistant_message_feedback_without_note_uses_message_content_for_contact_learning(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        related_profiles=[
            {
                "id": "mother",
                "name": "Anne",
                "relationship": "anne",
                "preferences": "",
                "notes": "",
                "important_dates": [],
            }
        ],
    )
    thread = store.create_assistant_thread(office_id, created_by="tester", title="Asistan")
    message = store.append_assistant_message(
        office_id,
        thread_id=int(thread["id"]),
        role="assistant",
        content="Annene kısa ve sıcak bir not yazıp yanına küçük bir çiçek alabilirsin.",
        linked_entities=[{"type": "contact", "id": "mother", "label": "Anne"}],
        tool_suggestions=[],
        draft_preview=None,
        source_context={"recipient": "Anne"},
        requires_approval=False,
        generated_from="message_draft",
        ai_provider="test",
        ai_model="test-model",
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    result = knowledge_base.record_assistant_message_feedback(
        store=store,
        message_id=int(message["id"]),
        feedback_value="liked",
        note=None,
    )
    profile = store.get_user_profile(office_id)
    mother = next(item for item in profile["related_profiles"] if str(item.get("id")) == "mother")

    assert result["semantic_learning"]["target_contact"]["profile_id"] == "mother"
    assert "Hediye: çiçek önerileri olumlu karşılanıyor." in str(mother.get("preferences") or "")
    assert "İletişim: Anne ile iletişimde sıcak, kısa ton olumlu karşılanıyor." in str(mother.get("preferences") or "")
    assert "Yanıt tarzı: kısa açıklamalar olumlu karşılanıyor." in str(profile.get("assistant_notes") or "")


def test_assistant_feedback_does_not_autocreate_generic_related_profile(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        related_profiles=[],
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    result = knowledge_base._apply_assistant_feedback_to_related_profile(
        store=store,
        semantic_learning={
            "target_contact": {
                "profile_id": "sibling",
                "name": "Kardeş",
                "relationship": "kardeş",
            },
            "signals": [
                {
                    "profile_prefix": "İletişim",
                    "profile_statement": "İletişim: sıcak ton olumlu karşılanıyor.",
                }
            ],
        },
        note='hayır "Abim" diye kayıtlı biri var direkt numarası 08 ile bitiyor',
    )

    profile = store.get_user_profile(office_id)

    assert result["updated"] is False
    assert profile["related_profiles"] == []


def test_assistant_message_feedback_reason_replaces_conflicting_contact_item_learning(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        related_profiles=[
            {
                "id": "mother",
                "name": "Anne",
                "relationship": "anne",
                "preferences": "Hediye: çikolata önerileri olumlu karşılanıyor.",
                "notes": "",
                "important_dates": [],
            }
        ],
    )
    thread = store.create_assistant_thread(office_id, created_by="tester", title="Asistan")
    message = store.append_assistant_message(
        office_id,
        thread_id=int(thread["id"]),
        role="assistant",
        content="Annen için çikolata alıp sıcak bir not ekleyebilirsin.",
        linked_entities=[{"type": "contact", "id": "mother", "label": "Anne"}],
        tool_suggestions=[],
        draft_preview=None,
        source_context={"recipient": "Anne"},
        requires_approval=False,
        generated_from="message_draft",
        ai_provider="test",
        ai_model="test-model",
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    knowledge_base.record_assistant_message_feedback(
        store=store,
        message_id=int(message["id"]),
        feedback_value="disliked",
        note="Annem çikolatayı sevmiyor, bunu bir daha önermeyelim.",
    )
    profile = store.get_user_profile(office_id)
    mother = next(item for item in profile["related_profiles"] if str(item.get("id")) == "mother")

    assert "Hediye: çikolata önerilerinden kaçınılmalı." in str(mother.get("preferences") or "")
    assert "Hediye: çikolata önerileri olumlu karşılanıyor." not in str(mother.get("preferences") or "")


def test_assistant_message_star_api_route_updates_and_clears_profile_learning(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "lawcopilot.db"
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(db_path))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    store = Persistence(db_path)
    store.upsert_user_profile(
        "default-office",
        display_name="Sami",
        related_profiles=[
            {
                "id": "mother",
                "name": "Anne",
                "relationship": "anne",
                "preferences": "",
                "notes": "",
                "important_dates": [],
            }
        ],
    )
    thread = store.create_assistant_thread("default-office", created_by="tester", title="Asistan")
    message = store.append_assistant_message(
        "default-office",
        thread_id=int(thread["id"]),
        role="assistant",
        content="Annene kısa ve sıcak bir not yazıp yanına küçük bir çiçek alabilirsin.",
        linked_entities=[{"type": "contact", "id": "mother", "label": "Anne"}],
        tool_suggestions=[],
        draft_preview=None,
        source_context={"recipient": "Anne"},
        requires_approval=False,
        generated_from="message_draft",
        ai_provider="test",
        ai_model="test-model",
    )

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    update_star = _route_endpoint(app, "/assistant/thread/messages/{message_id}/starred", "PATCH")

    token_body = issue_token(TokenRequest(subject="tester", role="intern"))
    authorization = f"Bearer {token_body['access_token']}"

    starred = update_star(
        int(message["id"]),
        AssistantThreadMessageStarRequest(starred=True),
        authorization=authorization,
    )
    profile = store.get_user_profile("default-office")
    mother = next(item for item in profile["related_profiles"] if str(item.get("id")) == "mother")

    assert starred["message"]["starred"] is True
    assert starred["learning"]["starred"] is True
    assert "Hediye: çiçek önerileri olumlu karşılanıyor." in str(mother.get("preferences") or "")
    assert "Yanıt tarzı: kısa açıklamalar olumlu karşılanıyor." in str(profile.get("assistant_notes") or "")

    unstarred = update_star(
        int(message["id"]),
        AssistantThreadMessageStarRequest(starred=False),
        authorization=authorization,
    )
    cleared_profile = store.get_user_profile("default-office")
    cleared_mother = next(item for item in cleared_profile["related_profiles"] if str(item.get("id")) == "mother")

    assert unstarred["message"]["starred"] is False
    assert unstarred["learning"]["cleared"] is True
    assert "Hediye: çiçek önerileri olumlu karşılanıyor." not in str(cleared_mother.get("preferences") or "")
    assert "Yanıt tarzı:" not in str(cleared_profile.get("assistant_notes") or "")


def test_assistant_message_feedback_api_route_reconciles_cleared_feedback(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "lawcopilot.db"
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(db_path))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    store = Persistence(db_path)
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        related_profiles=[
            {
                "id": "mother",
                "name": "Anne",
                "relationship": "anne",
                "preferences": "",
                "notes": "",
                "important_dates": [],
            }
        ],
    )
    thread = store.create_assistant_thread(office_id, created_by="tester", title="Asistan")
    message = store.append_assistant_message(
        office_id,
        thread_id=int(thread["id"]),
        role="assistant",
        content="Annene sıcak bir mesaj yazıp küçük bir çiçek önerebilirim.",
        linked_entities=[{"type": "contact", "id": "mother", "label": "Anne"}],
        tool_suggestions=[],
        draft_preview=None,
        source_context={"recipient": "Anne", "why_now": "Daily check-in"},
        requires_approval=False,
        generated_from="daily_plan",
        ai_provider="test",
        ai_model="test-model",
    )

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    update_feedback = _route_endpoint(app, "/assistant/thread/messages/{message_id}/feedback", "PATCH")

    token_body = issue_token(TokenRequest(subject="tester", role="intern"))
    authorization = f"Bearer {token_body['access_token']}"

    liked = update_feedback(
        int(message["id"]),
        AssistantThreadMessageFeedbackRequest(
            feedback_value="liked",
            note="Anneme sıcak yazman iyiydi, çiçek önerin de uygundu.",
        ),
        authorization=authorization,
    )

    assert liked["message"]["feedback_value"] == "liked"
    assert liked["assistant_runtime_profile"]["behavior_contract"]["initiative_level"] == "high"

    cleared = update_feedback(
        int(message["id"]),
        AssistantThreadMessageFeedbackRequest(feedback_value="none"),
        authorization=authorization,
    )

    runtime_profile = store.get_assistant_runtime_profile(office_id)
    profile = store.get_user_profile(office_id)
    mother = next(item for item in profile["related_profiles"] if str(item.get("id")) == "mother")
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    state = knowledge_base._load_state()
    contact_records = ((state.get("pages") or {}).get("contacts") or {}).get("records", [])
    contact_keys = {str(item.get("key") or "") for item in contact_records if isinstance(item, dict)}

    assert cleared["message"]["feedback_value"] is None
    assert cleared["message"]["feedback_note"] is None
    assert cleared["learning"]["cleared"] is True
    assert cleared["assistant_runtime_profile"]["behavior_contract"] == runtime_profile["behavior_contract"]
    assert "initiative_level" not in runtime_profile["behavior_contract"]
    assert "follow_up_style" not in runtime_profile["behavior_contract"]
    assert "İletişim:" not in str(mother.get("preferences") or "")
    assert "Hediye:" not in str(mother.get("preferences") or "")
    assert "Assistant feedback öğrenimi:" not in str(mother.get("notes") or "")
    assert "contact-style:mother" not in contact_keys
    assert "contact-gift:mother:cicek" not in contact_keys


def test_assistant_message_feedback_api_route_replaces_prior_note_learning_for_same_message(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "lawcopilot.db"
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(db_path))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    store = Persistence(db_path)
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        related_profiles=[
            {
                "id": "mother",
                "name": "Anne",
                "relationship": "anne",
                "preferences": "",
                "notes": "",
                "important_dates": [],
            }
        ],
    )
    thread = store.create_assistant_thread(office_id, created_by="tester", title="Asistan")
    message = store.append_assistant_message(
        office_id,
        thread_id=int(thread["id"]),
        role="assistant",
        content="Annene sıcak bir mesaj yazıp küçük bir çiçek önerebilirim.",
        linked_entities=[{"type": "contact", "id": "mother", "label": "Anne"}],
        tool_suggestions=[],
        draft_preview=None,
        source_context={"recipient": "Anne"},
        requires_approval=False,
        generated_from="message_draft",
        ai_provider="test",
        ai_model="test-model",
    )

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    update_feedback = _route_endpoint(app, "/assistant/thread/messages/{message_id}/feedback", "PATCH")
    token_body = issue_token(TokenRequest(subject="tester", role="intern"))
    authorization = f"Bearer {token_body['access_token']}"

    update_feedback(
        int(message["id"]),
        AssistantThreadMessageFeedbackRequest(
            feedback_value="liked",
            note="Anneme sıcak yazman iyiydi, çiçek önerin de uygundu.",
        ),
        authorization=authorization,
    )
    updated = update_feedback(
        int(message["id"]),
        AssistantThreadMessageFeedbackRequest(
            feedback_value="liked",
            note="Anneme sıcak yazman iyiydi ama bu sefer çikolata önerin daha uygundu.",
        ),
        authorization=authorization,
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    state = knowledge_base._load_state()
    profile = store.get_user_profile(office_id)
    mother = next(item for item in profile["related_profiles"] if str(item.get("id")) == "mother")
    contact_records = ((state.get("pages") or {}).get("contacts") or {}).get("records", [])
    contact_keys = {str(item.get("key") or "") for item in contact_records if isinstance(item, dict)}
    feedback_note_lines = [
        line
        for line in str(mother.get("notes") or "").splitlines()
        if line.startswith("Assistant feedback öğrenimi:")
    ]

    assert updated["message"]["feedback_note"] == "Anneme sıcak yazman iyiydi ama bu sefer çikolata önerin daha uygundu."
    assert "Hediye: çikolata önerileri olumlu karşılanıyor." in str(mother.get("preferences") or "")
    assert "Hediye: çiçek önerileri olumlu karşılanıyor." not in str(mother.get("preferences") or "")
    assert "contact-gift:mother:cikolata" in contact_keys
    assert "contact-gift:mother:cicek" not in contact_keys
    assert len(feedback_note_lines) == 1


def test_assistant_message_feedback_api_route_accumulates_multiple_liked_items_for_same_contact(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "lawcopilot.db"
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(db_path))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    store = Persistence(db_path)
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        related_profiles=[
            {
                "id": "mother",
                "name": "Anne",
                "relationship": "anne",
                "preferences": "",
                "notes": "",
                "important_dates": [],
            }
        ],
    )
    thread = store.create_assistant_thread(office_id, created_by="tester", title="Asistan")
    first_message = store.append_assistant_message(
        office_id,
        thread_id=int(thread["id"]),
        role="assistant",
        content="Annene küçük bir çiçek alabilirsin.",
        linked_entities=[{"type": "contact", "id": "mother", "label": "Anne"}],
        tool_suggestions=[],
        draft_preview=None,
        source_context={"recipient": "Anne"},
        requires_approval=False,
        generated_from="message_draft",
        ai_provider="test",
        ai_model="test-model",
    )
    second_message = store.append_assistant_message(
        office_id,
        thread_id=int(thread["id"]),
        role="assistant",
        content="Annen için kaliteli bir çikolata düşünebilirsin.",
        linked_entities=[{"type": "contact", "id": "mother", "label": "Anne"}],
        tool_suggestions=[],
        draft_preview=None,
        source_context={"recipient": "Anne"},
        requires_approval=False,
        generated_from="message_draft",
        ai_provider="test",
        ai_model="test-model",
    )

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    update_feedback = _route_endpoint(app, "/assistant/thread/messages/{message_id}/feedback", "PATCH")
    token_body = issue_token(TokenRequest(subject="tester", role="intern"))
    authorization = f"Bearer {token_body['access_token']}"

    update_feedback(
        int(first_message["id"]),
        AssistantThreadMessageFeedbackRequest(
            feedback_value="liked",
            note="Annem için çiçek önerin iyiydi.",
        ),
        authorization=authorization,
    )
    update_feedback(
        int(second_message["id"]),
        AssistantThreadMessageFeedbackRequest(
            feedback_value="liked",
            note="Çikolata önerin de çok uygundu.",
        ),
        authorization=authorization,
    )

    profile = store.get_user_profile(office_id)
    mother = next(item for item in profile["related_profiles"] if str(item.get("id")) == "mother")

    assert "Hediye: çiçek, çikolata önerileri olumlu karşılanıyor." in str(mother.get("preferences") or "")

    update_feedback(
        int(first_message["id"]),
        AssistantThreadMessageFeedbackRequest(feedback_value="none"),
        authorization=authorization,
    )
    profile = store.get_user_profile(office_id)
    mother = next(item for item in profile["related_profiles"] if str(item.get("id")) == "mother")

    assert "Hediye: çikolata önerileri olumlu karşılanıyor." in str(mother.get("preferences") or "")
    assert "çiçek, çikolata" not in str(mother.get("preferences") or "")


def test_sync_from_store_backfills_assistant_action_history(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"

    draft = store.create_outbound_draft(
        office_id,
        draft_type="send_email",
        channel="email",
        to_contact="ayse@example.com",
        subject="Kısa durum notu",
        body="Merhaba, kısa bir durum notu paylaşmak istedim.",
        created_by="tester",
    )
    action = store.create_assistant_action(
        office_id,
        action_type="send_email",
        title="Ayşe'ye kısa durum notu",
        description="E-posta taslağı hazırlandı.",
        rationale="Gelen talep için kısa ve nazik bir yanıt önerildi.",
        source_refs=[{"type": "thread", "id": 1}],
        target_channel="email",
        draft_id=int(draft["id"]),
        status="pending_review",
        created_by="tester",
    )
    store.add_approval_event(
        office_id,
        actor="tester",
        event_type="approved",
        action_id=int(action["id"]),
        outbound_draft_id=int(draft["id"]),
        note="Uygun göründü.",
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    result = knowledge_base.sync_from_store(store=store, reason="action_backfill")
    status = knowledge_base.status(ensure=False, previews=False)

    assert result["operational_sync"]["synced_record_count"] >= 2
    assert (knowledge_base.base_dir / "raw" / "assistant_action").exists()
    assert (knowledge_base.base_dir / "raw" / "approval_event").exists()
    assert any(page["key"] == "decisions" and page["record_count"] >= 1 for page in status["pages"])
    assert any(page["key"] == "recommendations" and page["record_count"] >= 1 for page in status["pages"])


def test_action_routes_emit_decision_records(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    generate_action = _route_endpoint(app, "/assistant/actions/generate", "POST")
    approve_action = _route_endpoint(app, "/assistant/actions/{action_id}/approve", "POST")
    get_kb = _route_endpoint(app, "/assistant/knowledge-base", "GET")

    token_body = issue_token(TokenRequest(subject="kb-lawyer", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    generated = generate_action(
        AssistantActionGenerateRequest(
            action_type="send_email",
            target_channel="email",
            to_contact="ayse@example.com",
            title="Kısa güncelleme",
            instructions="Ayşe'ye kısa ve net bir durum güncellemesi hazırla.",
            source_refs=[],
        ),
        authorization=authorization,
    )
    assert generated["decision_record"]["risk_level"] == "B"
    assert generated["policy_guardrails"]["requires_confirmation"] is True
    assert generated["explainability"]["risk_level"] == "B"
    assert generated["action_ladder"]["current_stage"] == "draft"
    assert generated["knowledge_context"]["backend"] == "sqlite_hybrid_fts_v1"
    assert generated["action_ladder"]["preview_required_before_execute"] is True
    assert Path(generated["decision_record"]["path"]).exists()

    approved = approve_action(
        int(generated["action"]["id"]),
        AssistantActionDecisionRequest(note="Önce ben kontrol ettim, gönderime hazırlayabilirsin."),
        authorization=authorization,
    )
    assert approved["decision_record"]["confidence"] == 1.0
    assert approved["action"]["status"] == "approved"
    assert approved["action_ladder"]["current_stage"] == "one_click_approve"
    assert approved["explainability"]["source_basis"]

    kb_body = get_kb(previews=False, authorization=authorization)
    assert kb_body["raw_source_count"] >= 2
    assert any(page["key"] == "decisions" and page["record_count"] >= 2 for page in kb_body["pages"])


def test_connector_sync_dedupes_incremental_records(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_email_thread(
        office_id,
        provider="gmail",
        thread_ref="thread-1",
        subject="Akşam planı",
        participants=["ayse@example.com"],
        snippet="Akşam planını hafifletelim ve tren seçeneğini konuşalım.",
        received_at="2026-04-07T08:00:00+00:00",
        reply_needed=True,
    )
    store.create_task(
        "Akşam planı gözden geçir",
        "2026-04-07T17:30:00+00:00",
        "medium",
        "tester",
        office_id=office_id,
        explanation="Yoğun günlerde akşam yükünü azalt.",
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    first = knowledge_base.sync_from_store(store=store, reason="connector_sync")
    second = knowledge_base.sync_from_store(store=store, reason="connector_sync_repeat")
    status = knowledge_base.status(ensure=False, previews=False)

    assert first["connector_sync"]["synced_record_count"] >= 2
    assert second["connector_sync"]["synced_record_count"] == 0
    assert status["connector_sync_count"] >= 2


def test_connector_claim_hints_feed_claim_backed_context_summary(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_calendar_event(
        office_id,
        provider="google",
        external_id="evt-1",
        title="Müşteri görüşmesi",
        starts_at="2026-04-07T10:00:00+00:00",
        ends_at="2026-04-07T11:00:00+00:00",
        location="Kadıköy mağaza",
        status="confirmed",
        needs_preparation=True,
    )
    epistemic = EpistemicService(store, office_id)
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id, epistemic=epistemic)

    sync = knowledge_base.run_connector_sync(store=store, reason="claim_hint_sync")
    resolved = knowledge_base.resolve_relevant_context("Müşteri görüşmesi", scopes=["personal"], limit=6)
    claim_resolution = epistemic.resolve_claim(
        subject_key="calendar_event:google:evt-1",
        predicate="status",
        scope="personal",
        include_blocked=True,
    )

    assert sync["result"]["synced_record_count"] >= 1
    assert claim_resolution["status"] == "current"
    assert claim_resolution["current_claim"]["epistemic_basis"] == "connector_observed"
    assert any("Takvim durumu: confirmed" in line for line in resolved["claim_summary_lines"])
    assert any(item.get("predicate") == "status" for item in resolved["resolved_claims"])
    assert "claim_resolved_context" in resolved["context_selection_reasons"]


def test_connector_sync_ingests_managed_elastic_resources(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    repository = IntegrationRepository(tmp_path / "lawcopilot.db")
    connection = repository.upsert_connection(
        office_id,
        connector_id="elastic",
        display_name="Elastic lake",
        status="connected",
        auth_type="api_key",
        access_level="read_only",
        management_mode="platform",
        enabled=True,
        mock_mode=False,
        scopes=["indices:read"],
        config={"index_pattern": "cases-*"},
        secret_blob="{}",
        health_status="valid",
        health_message="ok",
        created_by="tester",
    )
    repository.upsert_resource(
        office_id,
        connection_id=int(connection["id"]),
        resource_kind="document",
        external_id="doc-1",
        source_record_type="document",
        title="Elastic onboarding kaydi",
        body_text="Slack ve Elastic setup notlari",
        search_text="Slack ve Elastic setup notlari",
        source_url=None,
        parent_external_id=None,
        owner_label="Elastic lake",
        occurred_at="2026-04-08T10:00:00+00:00",
        modified_at="2026-04-08T10:00:00+00:00",
        checksum="abc123",
        permissions={"access_level": "read_only"},
        tags=["elastic", "cases-2026"],
        attributes={"index": "cases-2026", "score": 1.0},
        sync_metadata={},
        synced_at="2026-04-08T10:00:00+00:00",
    )

    records = ElasticIntegrationConnector().collect(store=store, office_id=office_id)
    assert records
    assert records[0].title == "Elastic onboarding kaydi"
    claim_hints = records[0].metadata["epistemic_claim_hints"]
    assert any(hint["predicate"] == "resource_kind" for hint in claim_hints)
    assert any(hint["predicate"] == "index" for hint in claim_hints)


def test_files_connector_emits_structured_claim_hints_for_documents_and_drive_files(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "files-connector.db")
    office_id = "default-office"
    matter = store.create_matter(
        office_id,
        "Demo matter",
        None,
        None,
        "active",
        None,
        None,
        None,
        None,
        "tester",
    )
    store.create_document(
        office_id,
        int(matter["id"]),
        "invoice.pdf",
        "Invoice",
        "application/pdf",
        "upload",
        None,
        "checksum-1",
        1234,
    )
    store.upsert_drive_file(
        office_id,
        provider="google",
        external_id="drive-1",
        name="Catalog",
        mime_type="application/vnd.google-apps.document",
        modified_at="2026-04-09T09:00:00+00:00",
        matter_id=int(matter["id"]),
    )

    records = FilesConnector().collect(store=store, office_id=office_id)

    assert records
    document_record = next(item for item in records if item.source_ref.startswith("document:"))
    drive_record = next(item for item in records if item.source_ref.startswith("drive-file:"))
    document_hints = document_record.metadata["epistemic_claim_hints"]
    drive_hints = drive_record.metadata["epistemic_claim_hints"]
    assert any(hint["predicate"] == "content_type" for hint in document_hints)
    assert any(hint["predicate"] == "source_type" for hint in document_hints)
    assert any(hint["predicate"] == "mime_type" for hint in drive_hints)


def test_notes_connector_emits_structured_claim_hints_for_note_type(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "notes-connector.db")
    office_id = "default-office"
    matter = store.create_matter(
        office_id,
        "Demo matter",
        None,
        None,
        "active",
        None,
        None,
        None,
        None,
        "tester",
    )
    store.add_matter_note(
        office_id,
        int(matter["id"]),
        "call_log",
        "Müşteri yarın tekrar aranacak.",
        "tester",
        "2026-04-09T10:00:00+00:00",
    )

    records = NotesConnector().collect(store=store, office_id=office_id)

    assert records
    note_record = next(item for item in records if item.source_ref.startswith(f"matter-note:{matter['id']}:"))
    note_hints = note_record.metadata["epistemic_claim_hints"]
    assert any(hint["predicate"] == "note_type" for hint in note_hints)


def test_file_back_respects_scope_and_search_filters(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    personal = knowledge_base.ingest(
        source_type="user_preferences",
        title="Yemek tercihi",
        content="Akşamları hafif yemekleri ve kısa yürüyüşleri tercih ediyorum.",
        metadata={"field": "food_preferences", "scope": "personal"},
        tags=["preferences"],
    )
    scoped_file_back = knowledge_base.maybe_file_back_response(
        kind="assistant_reply",
        title="Tahliye stratejisi",
        content=(
            "Kiraya veren vekili için tahliye dosyasında kısa bir yol haritası çıkarıldı. "
            "Öncelik mevcut deliller, kira ödeme geçmişi ve sonraki duruşma hazırlığı olmalı."
        ),
        metadata={"matter_id": 42},
        scope="project:matter-42",
        sensitivity="restricted",
    )

    personal_hits = knowledge_base.search("hafif yemek", scopes=["personal"], limit=5)
    professional_hits = knowledge_base.search("tahliye hazırlığı", scopes=["project:matter-42"], limit=5)
    isolated_hits = knowledge_base.search("hafif yemek", scopes=["project:matter-42"], limit=5)

    assert "preferences" in personal["compile"]["updated_pages"]
    assert scoped_file_back is not None
    assert personal_hits["items"]
    assert professional_hits["items"]
    assert all(item["scope"] == "project:matter-42" for item in professional_hits["items"])
    assert isolated_hits["items"] == []


def test_query_and_search_routes_expose_kb_contract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    ingest_kb = _route_endpoint(app, "/assistant/knowledge-base/ingest", "POST")
    search_kb = _route_endpoint(app, "/assistant/knowledge-base/search", "POST")
    query = _route_endpoint(app, "/query", "POST")
    run_reflection = _route_endpoint(app, "/assistant/knowledge-base/reflection", "POST")
    home = _route_endpoint(app, "/assistant/home", "GET")

    token_body = issue_token(TokenRequest(subject="kb-user", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    ingest_kb(
        KnowledgeBaseIngestRequest(
            source_type="user_preferences",
            title="Ulaşım tercihi",
            content="Genelde tren yolculuğunu severim ve kalabalık olmayan rotaları tercih ederim.",
            metadata={"field": "transport_preference", "scope": "personal"},
            tags=["transport", "preferences"],
        ),
        authorization=authorization,
    )
    ingest_kb(
        KnowledgeBaseIngestRequest(
            source_type="assistant_file_back",
            title="Tahliye dosyası notu",
            content=(
                "Tahliye dosyasında sonraki adım duruşma hazırlığı ve ödeme geçmişi kontrolü olmalı. "
                "Müvekkil iletişimi kısa ve profesyonel tutulmalı."
            ),
            metadata={"matter_id": 17, "scope": "project:matter-17", "page_key": "legal", "record_type": "legal_matter"},
            tags=["legal", "matter"],
        ),
        authorization=authorization,
    )

    search_body = search_kb(
        KnowledgeBaseSearchRequest(query="tren", scopes=["personal"], limit=5),
        authorization=authorization,
    )
    query_body = query(
        QueryIn(query="Ulaşım tercihimi kısaca hatırlat"),
        authorization=authorization,
    )
    run_reflection(authorization=authorization)
    home_body = home(authorization=authorization)

    assert search_body["backend"] == "sqlite_hybrid_fts_v1"
    assert search_body["items"]
    assert search_body["items"][0]["scope"] == "personal"
    assert query_body["knowledge_context"]["supporting_records"]
    assert query_body["assistant_context_pack"]
    assert query_body["explainability"]["why_this"]
    assert "personal" in query_body["explainability"]["memory_scope"]
    assert query_body["file_back"] is None
    assert query_body["writeback_allowed"] is False
    assert "knowledge_health_summary" in home_body
    assert "assistant_known_profile" in home_body


def test_query_writeback_requires_explicit_opt_in(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    ingest_kb = _route_endpoint(app, "/assistant/knowledge-base/ingest", "POST")
    query = _route_endpoint(app, "/query", "POST")

    token_body = issue_token(TokenRequest(subject="writeback-query", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    ingest_kb(
        KnowledgeBaseIngestRequest(
            source_type="user_preferences",
            title="Ulaşım tercihi",
            content="Genelde uzun mesafede tren tercih ederim.",
            metadata={"scope": "personal", "page_key": "preferences", "record_type": "preference"},
            tags=["preference"],
        ),
        authorization=authorization,
    )

    default_body = query(
        QueryIn(query="Ulaşım tercihimi kısaca hatırlat"),
        authorization=authorization,
    )
    opt_in_body = query(
        QueryIn(query="Ulaşım tercihimi kısaca hatırlat", allow_writeback=True),
        authorization=authorization,
    )

    assert default_body["file_back"] is None
    assert default_body["writeback_allowed"] is False
    assert opt_in_body["file_back"] is not None
    assert opt_in_body["writeback_allowed"] is True
    assert opt_in_body["assistant_context_pack"]


def test_google_sync_route_updates_connector_status_and_checkpoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    google_sync = _route_endpoint(app, "/integrations/google/sync", "POST")
    connector_status = _route_endpoint(app, "/assistant/connectors/sync-status", "GET")
    search_kb = _route_endpoint(app, "/assistant/knowledge-base/search", "POST")

    token_body = issue_token(TokenRequest(subject="sync-user", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    sync_response = google_sync(
        GoogleSyncRequest(
            account_label="Google hesabim",
            email_threads=[
                GoogleEmailThreadMirrorRequest(
                    provider="google",
                    thread_ref="thread-42",
                    subject="Akşam planı",
                    snippet="Akşam planını hafifletelim ve tren seçeneğini konuşalım.",
                    sender="ayse@example.com",
                )
            ],
            synced_at="2026-04-07T18:00:00+00:00",
            cursor="gmail-history-42",
            checkpoint={"history_id": "42"},
        ),
        authorization=authorization,
    )

    status_body = connector_status(authorization=authorization)
    assert sync_response["knowledge_base_sync"]["result"]["synced_record_count"] >= 0
    assert sync_response["knowledge_base_sync"]["result"]["failed_connectors"] == []
    email_connector = next(item for item in status_body["items"] if item["connector"] == "email_threads")
    assert email_connector["cursor"] == "gmail-history-42"
    assert email_connector["checkpoint"]["mirror_checkpoint"]["history_id"] == "42"


def test_runtime_blueprint_route_returns_custom_form_suggestion(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    route = _route_endpoint(app, "/assistant/runtime/core/blueprint", "POST")
    token_body = issue_token(TokenRequest(subject="blueprint-user", role="intern"))
    authorization = f"Bearer {token_body['access_token']}"

    payload = route(
        AssistantRuntimeBlueprintRequest(description="Beni kitap okuma koçuna çevir. Her akşam hedefimi takip et."),
        authorization=authorization,
    )

    assert payload["form"]["custom"] is True
    assert "goal_tracking" in payload["form"]["capabilities"]
    assert "reading_progress" in payload["form"]["capabilities"]
    assert payload["form"]["supports_coaching"] is True
    assert payload["confidence"] >= 0.7


def test_search_route_supports_metadata_filters_and_record_types(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    ingest_kb = _route_endpoint(app, "/assistant/knowledge-base/ingest", "POST")
    search_kb = _route_endpoint(app, "/assistant/knowledge-base/search", "POST")

    token_body = issue_token(TokenRequest(subject="search-user", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    ingest_kb(
        KnowledgeBaseIngestRequest(
            source_type="assistant_file_back",
            title="Nazik ton tercihi",
            content="E-posta yanıtlarında kısa, nazik ve profesyonel ton tercih edilmeli.",
            metadata={
                "page_key": "preferences",
                "record_type": "preference",
                "scope": "personal",
                "field": "communication_style",
                "connector_name": "manual_memory",
            },
            tags=["preferences"],
        ),
        authorization=authorization,
    )

    filtered = search_kb(
        KnowledgeBaseSearchRequest(
            query="nazik",
            scopes=["personal"],
            page_keys=["preferences"],
            metadata_filters={"metadata": {"field": "communication_style"}},
            record_types=["preference"],
            limit=5,
        ),
        authorization=authorization,
    )

    assert filtered["items"]
    assert all(item["record_type"] == "preference" for item in filtered["items"])
    assert all(item["metadata"]["metadata"]["field"] == "communication_style" for item in filtered["items"])


def test_wiki_brain_routes_expose_compile_and_synthesis(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    ingest_kb = _route_endpoint(app, "/assistant/knowledge-base/ingest", "POST")
    get_wiki = _route_endpoint(app, "/assistant/knowledge-base/wiki", "GET")
    compile_wiki = _route_endpoint(app, "/assistant/knowledge-base/wiki/compile", "POST")
    run_synthesis = _route_endpoint(app, "/assistant/knowledge-base/synthesis", "POST")

    token_body = issue_token(TokenRequest(subject="wiki-user", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    ingest_kb(
        KnowledgeBaseIngestRequest(
            source_type="assistant_file_back",
            title="Planlama notu",
            content="Gun sonu kapanis ve hafifletilmis plan ozetleri daha yararli oluyor.",
            metadata={"page_key": "projects", "record_type": "goal", "scope": "personal"},
            tags=["planning", "daily"],
        ),
        authorization=authorization,
    )

    compile_body = compile_wiki(KnowledgeWikiCompileRequest(reason="unit_compile", previews=True), authorization=authorization)
    wiki_body = get_wiki(previews=False, authorization=authorization)
    synthesis_body = run_synthesis(KnowledgeSynthesisRequest(reason="unit_synthesis"), authorization=authorization)

    assert compile_body["concept_count"] >= 1
    assert wiki_body["summary"]["concept_count"] >= 1
    assert wiki_body["concepts"]
    assert "summary" in synthesis_body
    assert Path(synthesis_body["report_path"]).exists()


def test_memory_correction_route_updates_scope_and_forget(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    ingest_kb = _route_endpoint(app, "/assistant/knowledge-base/ingest", "POST")
    search_kb = _route_endpoint(app, "/assistant/knowledge-base/search", "POST")
    correct_memory = _route_endpoint(app, "/assistant/memory/corrections", "POST")

    token_body = issue_token(TokenRequest(subject="memory-user", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    ingest_kb(
        KnowledgeBaseIngestRequest(
            source_type="user_preferences",
            title="Ton tercihi",
            content="Kısa ve nazik bir ton istiyorum.",
            metadata={"field": "communication_style", "scope": "personal"},
            tags=["preferences", "tone"],
        ),
        authorization=authorization,
    )
    initial_search = search_kb(
        KnowledgeBaseSearchRequest(query="nazik ton", scopes=["personal"], page_keys=["preferences"], limit=5),
        authorization=authorization,
    )
    record_id = initial_search["items"][0]["record_id"]

    scoped = correct_memory(
        KnowledgeMemoryCorrectionRequest(
            action="change_scope",
            page_key="preferences",
            target_record_id=record_id,
            scope="professional",
            note="Bu tercih iş bağlamında geçerli.",
        ),
        authorization=authorization,
    )
    professional_search = search_kb(
        KnowledgeBaseSearchRequest(query="nazik ton", scopes=["professional"], page_keys=["preferences"], limit=5),
        authorization=authorization,
    )
    forgotten = correct_memory(
        KnowledgeMemoryCorrectionRequest(
            action="forget",
            page_key="preferences",
            target_record_id=scoped["record_id"],
            note="Bu kaydı artık tutma.",
        ),
        authorization=authorization,
    )
    after_forget = search_kb(
        KnowledgeBaseSearchRequest(query="nazik ton", scopes=["professional"], page_keys=["preferences"], limit=5),
        authorization=authorization,
    )

    assert scoped["scope"] == "professional"
    assert scoped["knowledge_context"]["supporting_records"]
    assert professional_search["items"]
    assert forgotten["status"] == "forgotten"
    assert after_forget["items"] == []


def test_trigger_engine_location_and_cooldown_behavior(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        food_preferences="Oglen ve aksam hafif yemekleri severim.",
        assistant_notes="Gerektiginde yakin cami veya kafe oner.",
    )
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    knowledge_base.record_location_context(
        current_place={
            "place_id": "station-1",
            "label": "Kadikoy Iskele",
            "category": "station",
            "area": "Kadikoy",
            "started_at": "2026-04-08T12:10:00+00:00",
            "tags": ["historic"],
        },
        recent_places=[
            {
                "place_id": "office-1",
                "label": "Moda Ofis",
                "category": "office",
                "area": "Kadikoy",
                "started_at": "2026-04-07T09:00:00+00:00",
            },
            {
                "place_id": "home-1",
                "label": "Ev",
                "category": "home",
                "area": "Kadikoy",
                "started_at": "2026-04-07T19:30:00+00:00",
            },
        ],
        source="test_fixture",
    )

    first = knowledge_base.evaluate_triggers(
        store=store,
        settings=None,
        now=datetime(2026, 4, 8, 12, 15, tzinfo=timezone.utc),
        persist=True,
        limit=5,
        include_suppressed=True,
        forced_types=["location_context"],
    )
    second = knowledge_base.evaluate_triggers(
        store=store,
        settings=None,
        now=datetime(2026, 4, 8, 13, 0, tzinfo=timezone.utc),
        persist=False,
        limit=5,
        include_suppressed=True,
        forced_types=["location_context"],
    )

    assert first["items"]
    location_item = first["items"][0]
    assert location_item["trigger_type"] == "location_context"
    assert location_item["why_now"]
    assert location_item["why_this_user"]
    assert location_item["recommended_action"]["stage"] == "suggest"
    assert location_item["decision_record"]["risk_level"] == location_item["risk_level"]
    assert second["items"] == []
    assert second["suppressed"]
    assert second["suppressed"][0]["suppression_reason"] == "cooldown_active"


def test_location_and_orchestration_routes_expose_trigger_contract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    update_location = _route_endpoint(app, "/assistant/location/context", "POST")
    get_location = _route_endpoint(app, "/assistant/location/context", "GET")
    evaluate_triggers = _route_endpoint(app, "/assistant/triggers/evaluate", "POST")
    run_orchestration = _route_endpoint(app, "/assistant/orchestration/run", "POST")
    orchestration_status = _route_endpoint(app, "/assistant/orchestration/status", "GET")

    token_body = issue_token(TokenRequest(subject="trigger-user", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    updated = update_location(
        AssistantLocationContextRequest(
            current_place={
                "place_id": "home-1",
                "label": "Ev",
                "category": "home",
                "area": "Kadikoy",
                "started_at": "2026-04-08T18:10:00+00:00",
            },
            recent_places=[
                {
                    "place_id": "office-1",
                    "label": "Ofis",
                    "category": "office",
                    "area": "Kadikoy",
                    "started_at": "2026-04-08T09:15:00+00:00",
                }
            ],
            source="ui_test",
            nearby_categories=["light_meal", "market"],
        ),
        authorization=authorization,
    )
    location_context = get_location(authorization=authorization)
    trigger_payload = evaluate_triggers(
        TriggerEvaluationRequest(forced_types=["location_context"], include_suppressed=True, limit=4, persist=True),
        authorization=authorization,
    )
    orchestration = run_orchestration(
        OrchestrationRunRequest(job_names=["trigger_evaluation", "suppression_cleanup"], reason="test_run", force=True),
        authorization=authorization,
    )
    status = orchestration_status(authorization=authorization)

    assert updated["location_context"]["current_place"]["label"] == "Ev"
    assert location_context["nearby_candidates"]
    assert trigger_payload["items"] or trigger_payload["suppressed"]
    if trigger_payload["items"]:
        assert trigger_payload["items"][0]["explainability"]["short"]
    assert orchestration["results"]
    assert any(item["job"] == "trigger_evaluation" for item in orchestration["results"])
    assert status["jobs"]


def test_search_hits_include_selection_reasons_and_trigger_context(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ingest(
        source_type="assistant_file_back",
        title="Takvim yogunluk notu",
        content="Yogun takvim gunlerinde gunluk plan ve sakinlestirme onerileri daha ilgili oluyor.",
        metadata={
            "page_key": "recommendations",
            "record_type": "recommendation",
            "scope": "personal",
            "field": "planning_style",
        },
        tags=["planning", "calendar"],
    )
    knowledge_base.create_decision_record(
        title="Takvim karari",
        summary="Yogun takvimde gunluk plan onerisi one cikarildi.",
        source_refs=["unit:test"],
        reasoning_summary="Takvim yogunluk sorgularinda recommendation ve decision katmani one alinmali.",
        confidence=0.82,
        user_confirmation_required=False,
        possible_risks=["Baglam degismis olabilir."],
        action_kind="read_summary",
        intent="calendar_load",
        alternatives=["Oneri gostermemek"],
    )

    search = knowledge_base.search("neden yogun takvim onerisi", scopes=["personal", "global"], limit=5)
    resolved = knowledge_base.resolve_relevant_context("neden yogun takvim onerisi", scopes=["personal", "global"], limit=5)

    assert search["items"]
    assert search["items"][0]["selection_reasons"]
    assert resolved["context_selection_reasons"]
    assert resolved["record_type_counts"]


def test_search_recent_history_intents_prioritize_recommendation_records(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ingest(
        source_type="assistant_file_back",
        title="Genel planning tercihi",
        content="Planlarda fazla detay yerine kisa ve net ozetler tercih ediliyor.",
        metadata={
            "page_key": "preferences",
            "record_type": "preference",
            "scope": "personal",
            "field": "planning_style",
        },
        tags=["planning"],
    )
    knowledge_base.ingest(
        source_type="assistant_file_back",
        title="Son oneriler gecmisi",
        content="Son reddedilen ve kabul edilen oneriler gunluk plan ve reminder davranisini etkiliyor.",
        metadata={
            "page_key": "recommendations",
            "record_type": "recommendation",
            "scope": "personal",
            "field": "recommendation_feedback",
            "connector_name": "messages",
        },
        tags=["history", "recent"],
    )

    search = knowledge_base.search("son oneriler gecmisi", scopes=["personal", "global"], limit=5)

    assert search["items"]
    assert search["items"][0]["page_key"] == "recommendations"
    assert "page_intent_match" in search["items"][0]["selection_reasons"]


def test_location_connector_uses_profile_and_calendar_context(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        current_location="Kadikoy Iskele",
        home_base="Moda",
        location_preferences="Aksam ev yakininda hafif yemek ve sakin yerler iyi gelir.",
    )
    store.upsert_calendar_event(
        office_id,
        provider="google",
        external_id="calendar-1",
        title="Adliye gorusmesi",
        starts_at="2026-04-08T09:00:00+00:00",
        ends_at="2026-04-08T10:00:00+00:00",
        location="Anadolu Adliyesi",
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    result = knowledge_base.sync_from_store(store=store, reason="location_sync")
    status = knowledge_base.connector_sync_status(store=store)
    location_connector = next(item for item in status["items"] if item["connector"] == "location_events")

    assert result["connector_sync"]["synced_record_count"] >= 1
    assert location_connector["stub"] is False
    assert location_connector["record_count"] >= 2


def test_memory_correction_reduce_confidence_and_reinference_guard(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ensure_scaffold()
    state = knowledge_base._load_state()
    knowledge_base._upsert_page_record(
        state,
        "preferences",
        {
            "id": "pref-tone-1",
            "key": "communication_style",
            "title": "Ton tercihi",
            "summary": "Kisa ve nazik ton tercih ediliyor.",
            "confidence": 0.91,
            "status": "active",
            "source_refs": ["manual:test"],
            "signals": ["assistant_inference"],
            "updated_at": "2026-04-08T09:00:00+00:00",
            "metadata": {"field": "communication_style", "scope": "personal"},
        },
    )
    knowledge_base._save_state(state)
    knowledge_base._render_all(state)

    reduced = knowledge_base.apply_memory_correction(
        action="reduce_confidence",
        page_key="preferences",
        target_record_id="pref-tone-1",
        note="Bu kayit kesin degil.",
    )
    forgotten = knowledge_base.apply_memory_correction(
        action="forget",
        page_key="preferences",
        target_record_id="pref-tone-1",
        note="Bu cikarimi tekrar yapma.",
    )

    state = knowledge_base._load_state()
    blocked = knowledge_base._upsert_page_record(
        state,
        "preferences",
        {
            "id": "pref-tone-2",
            "key": "communication_style",
            "title": "Ton tercihi",
            "summary": "Kisa ve nazik ton tercih ediliyor.",
            "confidence": 0.74,
            "status": "active",
            "source_refs": ["inference:test"],
            "signals": ["assistant_inference"],
            "updated_at": "2026-04-08T10:00:00+00:00",
            "metadata": {"field": "communication_style", "scope": "personal"},
        },
    )
    overview = knowledge_base.memory_overview()

    assert reduced["confidence"] == 0.71
    assert forgotten["status"] == "forgotten"
    assert blocked["updated"] is False
    assert overview["recent_corrections"]
    assert overview["do_not_reinfer"]


def test_preference_consolidation_builds_typed_records_and_overview(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.upsert_user_profile(
        office_id,
        communication_style="Kisa, nazik ve profesyonel.",
        assistant_notes="Yogun gunlerde plani hafiflet ve aksamlari kapanis ozeti ver.",
        travel_preferences="Tren ve sakin rota tercihi baskin.",
    )
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    recommendation = {
        "id": "rec-daily-plan",
        "kind": "daily_plan",
        "suggestion": "Aksam icin hafifletilmis plan oner.",
        "why_this": "Yogun takvim ve kapanis ihtiyaci var.",
        "confidence": 0.84,
        "requires_confirmation": False,
        "source_basis": [],
        "next_actions": ["Taslak hazirla"],
        "memory_scope": ["personal"],
    }
    knowledge_base._record_recommendation(recommendation)
    knowledge_base.record_recommendation_feedback("rec-daily-plan", "accepted", note="Bu tarz planlar yararli.")

    result = knowledge_base.consolidate_preference_learning(store=store, reason="unit_test")
    overview = knowledge_base.memory_overview()

    assert result["record_count"] >= 3
    assert "preferences" in result["updated_pages"]
    assert overview["by_type"].get("conversation_style", 0) >= 1
    assert overview["by_type"].get("goal", 0) >= 1
    assert any(item["title"] == "Planlama tarzı" for item in overview["highlighted_records"])


def test_sync_from_store_semantically_learns_consumer_signals_without_duplicate_growth(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    run = store.create_agent_run(
        office_id,
        title="Lifestyle research",
        goal="Collect habit and meal preference signals",
        created_by="tester",
        status="completed",
        source_kind="assistant",
        run_type="investigation",
    )
    store.create_browser_session_artifact(
        office_id,
        run_id=int(run["id"]),
        artifact_type="bookmark",
        url="https://www.youtube.com/watch?v=habit123",
        metadata={
            "title": "Habit stacking systems",
            "query": "habit stacking productivity youtube",
            "scope": "personal",
        },
    )
    store.create_browser_session_artifact(
        office_id,
        run_id=int(run["id"]),
        artifact_type="bookmark",
        url="https://example.com/light-meal-ideas",
        metadata={
            "title": "Light meal grocery ideas",
            "query": "light meal grocery ideas",
            "scope": "personal",
        },
    )
    store.add_external_event(
        office_id,
        provider="youtube",
        event_type="watch_history",
        summary="User watched a productivity video about morning routines and habit stacking.",
        external_ref="yt:habit123",
        title="Morning routine video",
        metadata={"url": "https://www.youtube.com/watch?v=habit123", "scope": "personal"},
    )
    store.add_external_event(
        office_id,
        provider="shopping",
        event_type="saved_list",
        summary="User saved a light meal grocery list for the evening.",
        external_ref="shopping:list:1",
        title="Light meal grocery list",
        metadata={"category": "light meal", "scope": "personal"},
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    first_sync = knowledge_base.sync_from_store(store=store, reason="semantic_consumer_learning")
    second_sync = knowledge_base.sync_from_store(store=store, reason="semantic_consumer_learning_repeat")
    state = knowledge_base._load_state()
    overview = knowledge_base.memory_overview()

    routine_records = [
        record
        for record in ((state.get("pages") or {}).get("routines") or {}).get("records", [])
        if isinstance(record, dict) and str(record.get("status") or "active") == "active"
    ]
    preference_records = [
        record
        for record in ((state.get("pages") or {}).get("preferences") or {}).get("records", [])
        if isinstance(record, dict) and str(record.get("status") or "active") == "active"
    ]
    habit_records = [record for record in routine_records if str(record.get("key") or "") == "consumer-interest:habit_systems:personal"]
    meal_records = [record for record in preference_records if str(record.get("key") or "") == "consumer-interest:food_light_meal:personal"]

    assert first_sync["preference_consolidation"]["record_count"] >= 2
    assert second_sync["preference_consolidation"]["record_count"] >= 2
    assert len(habit_records) == 1
    assert len(meal_records) == 1
    assert any(item["title"] == "Alışkanlık ve sistem kurma ilgisi" for item in overview["learned_topics"])
    assert any(item["title"] == "Yemek ve hafif öğün sinyali" for item in overview["learned_topics"])


def test_sync_from_store_semantically_learns_weather_places_and_web_signals(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    store.add_external_event(
        office_id,
        provider="weather",
        event_type="weather_search",
        summary="User checked whether Kadıköy evening would be rainy and if a coat is needed.",
        external_ref="weather:kadikoy-evening",
        title="Kadıköy evening weather",
        metadata={"query": "Kadıköy akşam hava durumu mont gerekir mi", "scope": "personal"},
    )
    store.add_external_event(
        office_id,
        provider="weather",
        event_type="weather_search",
        summary="User checked tomorrow morning temperature and umbrella need.",
        external_ref="weather:kadikoy-morning",
        title="Kadıköy morning weather",
        metadata={"query": "Kadıköy sabah hava yağmur şemsiye gerekir mi", "scope": "personal"},
    )
    store.add_external_event(
        office_id,
        provider="places",
        event_type="places_search",
        summary="User searched nearby quiet cafe and mosque options around Moda.",
        external_ref="places:moda-nearby",
        title="Moda nearby cafe",
        metadata={"query": "Moda yakın sakin kahveci ve cami", "scope": "personal", "map_url": "https://example.test/maps"},
    )
    store.add_external_event(
        office_id,
        provider="places",
        event_type="places_search",
        summary="User searched nearby workspace cafe and market options.",
        external_ref="places:moda-workspace",
        title="Moda workspace cafe",
        metadata={"query": "Moda yakın çalışma kahvesi ve market", "scope": "personal", "map_url": "https://example.test/maps-2"},
    )
    store.add_external_event(
        office_id,
        provider="web",
        event_type="web_search",
        summary="User researched articles and sites about habit stacking systems.",
        external_ref="web:habit-research",
        title="Habit stacking research",
        metadata={"query": "habit stacking research articles", "scope": "personal", "url": "https://example.test/habit"},
    )
    store.add_external_event(
        office_id,
        provider="web",
        event_type="website_inspection",
        summary="User inspected a site that explains sustainable reading systems and routines.",
        external_ref="web:reading-systems",
        title="Reading systems site",
        metadata={"query": "reading systems site inspection", "scope": "personal", "url": "https://example.test/reading"},
    )

    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    first_sync = knowledge_base.sync_from_store(store=store, reason="extended_consumer_learning")
    second_sync = knowledge_base.sync_from_store(store=store, reason="extended_consumer_learning_repeat")
    state = knowledge_base._load_state()
    overview = knowledge_base.memory_overview()

    routine_records = [
        record
        for record in ((state.get("pages") or {}).get("routines") or {}).get("records", [])
        if isinstance(record, dict) and str(record.get("status") or "active") == "active"
    ]
    place_records = [
        record
        for record in ((state.get("pages") or {}).get("places") or {}).get("records", [])
        if isinstance(record, dict) and str(record.get("status") or "active") == "active"
    ]
    preference_records = [
        record
        for record in ((state.get("pages") or {}).get("preferences") or {}).get("records", [])
        if isinstance(record, dict) and str(record.get("status") or "active") == "active"
    ]

    assert first_sync["preference_consolidation"]["record_count"] >= 3
    assert second_sync["preference_consolidation"]["record_count"] >= 3
    assert any(str(record.get("key") or "") == "consumer-interest:weather_planning:personal" for record in routine_records)
    assert any(str(record.get("key") or "") == "consumer-interest:local_place_context:personal" for record in place_records)
    assert any(str(record.get("key") or "") == "consumer-interest:web_research_orientation:personal" for record in preference_records)
    assert any(item["title"] == "Hava ve planlama duyarlılığı" for item in overview["learned_topics"])
    assert any(item["title"] == "Yakın çevre ve mekan ilgisi" for item in overview["learned_topics"])
    assert any(item["title"] == "Web araştırması eğilimi" for item in overview["learned_topics"])


def test_connector_sync_failure_schedules_retry_and_preserves_job_status(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)

    class FailingConnector:
        name = "failing_connector"
        description = "Patlayan test connector"
        sync_mode = "mirror_pull"
        provider_hints = ("google",)

        def collect(self, *, store, office_id):  # noqa: ANN001
            raise RuntimeError("connector exploded")

    knowledge_base.connector_registry = [FailingConnector()]
    result = knowledge_base.run_connector_sync(store=store, reason="unit_failure", trigger="scheduler")
    status = knowledge_base.connector_sync_status(store=store)
    item = status["items"][0]

    assert result["job"]["status"] == "completed_with_errors"
    assert result["result"]["failed_connectors"][0]["connector"] == "failing_connector"
    assert item["health_status"] == "invalid"
    assert item["sync_status"] == "retry_scheduled"
    assert item["consecutive_failures"] == 1
    assert item["next_retry_at"]
    assert "yeniden denenecek" in str(item["sync_status_message"] or "")


def test_location_context_reads_desktop_snapshot_fallback(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    snapshot_path = tmp_path / "desktop-location.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "source": "desktop_fixture",
                "scope": "personal",
                "sensitivity": "high",
                "observed_at": "2026-04-08T18:05:00+00:00",
                "current_place": {
                    "place_id": "kadikoy-rhtm",
                    "label": "Kadikoy Rihtim",
                    "category": "transit",
                    "area": "Kadikoy",
                    "latitude": 40.991,
                    "longitude": 29.025,
                    "tags": ["historic"],
                },
                "recent_places": [
                    {
                        "place_id": "moda-home",
                        "label": "Moda Ev",
                        "category": "home",
                        "area": "Kadikoy",
                        "started_at": "2026-04-08T08:00:00+00:00",
                    }
                ],
                "nearby_categories": ["historic_site", "light_meal"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    knowledge_base = KnowledgeBaseService(
        tmp_path / "personal-kb",
        office_id,
        location_snapshot_path=snapshot_path,
        location_provider_mode="desktop_file_fallback",
    )

    context = knowledge_base.get_location_context(store=store)

    assert context["provider"] == "desktop_location_snapshot_v1"
    assert context["provider_mode"] == "desktop_file_snapshot"
    assert context["current_place"]["label"] == "Kadikoy Rihtim"
    assert context["nearby_candidates"]
    assert context["navigation_handoff"]["available"] is True
    assert "maps_url" in context["nearby_candidates"][0]["navigation_prep"]


def test_preference_consolidation_writes_location_pattern_learning_into_memory_overview(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)
    knowledge_base.ensure_scaffold()
    state = knowledge_base._load_state()
    state["location_context"] = {
        "scope": "personal",
        "source": "desktop_fixture",
        "provider": "desktop_location_snapshot_v1",
        "updated_at": "2026-04-08T18:05:00+00:00",
        "frequent_patterns": [
            {"time_bucket": "evening", "category": "cafe", "count": 3},
            {"time_bucket": "morning", "category": "transit", "count": 2},
        ],
    }
    knowledge_base._save_state(state)

    result = knowledge_base.consolidate_preference_learning(store=store, reason="location_pattern_test")
    state = knowledge_base._load_state()
    overview = knowledge_base.memory_overview()
    location_records = [
        record
        for record in ((state.get("pages") or {}).get("routines") or {}).get("records", [])
        if isinstance(record, dict) and str(record.get("key") or "") == "location-pattern:evening:cafe"
    ]

    assert result["record_count"] >= 2
    assert len(location_records) == 1
    assert location_records[0]["metadata"]["learning_source_category"] == "location_pattern"
    assert any(item["topic_key"] == "location:evening:cafe" for item in overview["learned_topics"])


def test_location_context_handles_permission_denied_without_fabricating_place(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")

    context = knowledge_base.record_location_context(
        current_place={},
        recent_places=[],
        nearby_categories=["cafe"],
        observed_at="2026-04-08T18:45:00+00:00",
        source="browser_geolocation",
        scope="personal",
        sensitivity="high",
        provider="desktop_browser_capture_v1",
        provider_mode="desktop_renderer_geolocation",
        provider_status="permission_denied",
        capture_mode="device_capture",
        permission_state="denied",
        capture_failure_reason="Konum izni reddedildi.",
        persist_raw=False,
    )

    assert context["current_place"] is None
    assert context["provider_status"] == "permission_denied"
    assert context["permission_state"] == "denied"
    assert context["capture_failure_reason"] == "Konum izni reddedildi."
    assert context["location_explainability"]["permission_state"] == "denied"
    assert "Konum izni" in str(context["location_explainability"]["status_reason"])


def test_location_snapshot_permission_denied_fallback_degrades_cleanly(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    snapshot_path = tmp_path / "desktop-location-degraded.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "source": "desktop_fixture",
                "scope": "personal",
                "sensitivity": "high",
                "observed_at": "2026-04-08T18:05:00+00:00",
                "provider": "desktop_browser_capture_v1",
                "provider_mode": "desktop_renderer_geolocation",
                "provider_status": "permission_denied",
                "capture_mode": "device_capture",
                "permission_state": "denied",
                "capture_failure_reason": "Konum izni reddedildi.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    knowledge_base = KnowledgeBaseService(
        tmp_path / "personal-kb",
        "default-office",
        location_snapshot_path=snapshot_path,
        location_provider_mode="desktop_file_fallback",
    )

    context = knowledge_base.get_location_context(store=store)

    assert context["current_place"] is None
    assert context["provider_status"] == "permission_denied"
    assert context["permission_state"] == "denied"
    assert context["navigation_handoff"]["available"] is False
    assert "konum izni verilmedi" in str(context["location_explainability"]["status_reason"]).lower()


def test_orchestration_skips_jobs_until_due(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)

    first = knowledge_base.run_orchestration(
        store=store,
        settings=None,
        job_names=["suppression_cleanup"],
        reason="first",
        force=True,
        now=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
    )
    second = knowledge_base.run_orchestration(
        store=store,
        settings=None,
        job_names=["suppression_cleanup"],
        reason="second",
        force=False,
        now=datetime(2026, 4, 8, 10, 1, tzinfo=timezone.utc),
    )

    assert first["results"][0]["status"] == "completed"
    assert second["results"][0]["status"] == "skipped"
    assert second["results"][0]["reason"] == "interval_not_due"


def test_home_and_memory_overview_routes_expose_final_contract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    store = Persistence(tmp_path / "lawcopilot.db")
    store.upsert_user_profile(
        "default-office",
        display_name="Sami",
        communication_style="Kisa ve sicak.",
        assistant_notes="Yogun gunlerde hafifletilmis plan seviyorum.",
        food_preferences="Hafif aksam yemegi",
        current_location="Kadikoy",
    )

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    home = _route_endpoint(app, "/assistant/home", "GET")
    memory_overview = _route_endpoint(app, "/assistant/memory/overview", "GET")
    system_status = _route_endpoint(app, "/assistant/system/status", "GET")

    token_body = issue_token(TokenRequest(subject="home-user", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    home_body = home(authorization=authorization)
    overview_body = memory_overview(authorization=authorization)
    system_body = system_status(authorization=authorization)

    assert home_body["memory_overview"]["counts"]["records"] >= 1
    assert "proactive_control_state" in home_body
    assert "recommendation_history_summary" in home_body
    assert home_body["assistant_system_status"]["knowledge_base"]["enabled"] is True
    assert "shareability" in home_body["assistant_known_profile"]["preferences"][0]
    assert overview_body["by_scope"]
    assert system_body["execution_policy"]["draft_first_external_actions"] is True
    assert any(item["key"] == "long_term_memory" for item in system_body["canonical_sources"])
    assert any(item["key"] == "system_contract" for item in system_body["canonical_sources"])


def test_search_semantic_expansion_bridges_mail_and_eposta(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ingest(
        source_type="assistant_file_back",
        title="E-posta tarzı tercihi",
        content="Eposta yanitlari kisa, sicak ve gerektiginde iki maddelik olmalı.",
        metadata={
            "page_key": "preferences",
            "record_type": "conversation_style",
            "scope": "personal",
            "field": "communication_style",
        },
        tags=["email", "style"],
    )

    search = knowledge_base.search("mail tarzim neydi", scopes=["personal"], limit=5)

    assert search["items"]
    assert search["items"][0]["page_key"] == "preferences"
    assert "semantic_expansion" in search["items"][0]["selection_reasons"]


def test_search_ranking_profile_and_metadata_match_surface(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ingest(
        source_type="assistant_file_back",
        title="Iletisim tarzi",
        content="Communication style tercihi: kisa, nazik ve profesyonel cevaplar.",
        metadata={
            "page_key": "preferences",
            "record_type": "preference",
            "scope": "personal",
            "field": "communication_style",
            "connector_name": "manual_memory",
            "confidence": 0.91,
        },
        tags=["preferences", "style"],
    )
    knowledge_base.ingest(
        source_type="assistant_file_back",
        title="Genel not",
        content="Style guide notu.",
        metadata={
            "page_key": "recommendations",
            "record_type": "recommendation",
            "scope": "personal",
            "confidence": 0.2,
        },
        tags=["style"],
    )

    search = knowledge_base.search("communication style ozet", scopes=["personal"], limit=5)

    assert search["ranking_profile"]["profile"] == "sqlite_hybrid_fts_semantic_v3"
    assert search["ranking_profile"]["vector_hook_ready"] is True
    assert search["items"]
    assert search["items"][0]["page_key"] == "preferences"
    assert search["items"][0]["metadata"]["metadata"]["field"] == "communication_style"


def test_browser_geolocation_updates_location_capture_mode(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")

    context = knowledge_base.record_location_context(
        current_place={
            "place_id": "device-1",
            "label": "Cihaz konumu",
            "category": "device_location",
            "latitude": 40.991,
            "longitude": 29.026,
            "accuracy_meters": 48,
            "tags": ["device_capture"],
        },
        recent_places=[],
        nearby_categories=["cafe", "transit"],
        source="browser_geolocation",
        scope="personal",
        sensitivity="high",
        persist_raw=False,
    )

    assert context["provider"] == "desktop_browser_capture_v1"
    assert context["provider_mode"] == "desktop_renderer_geolocation"
    assert context["capture_mode"] == "device_capture"
    assert context["permission_state"] == "granted"
    assert context["current_place"]["accuracy_meters"] == 48


def test_connector_sync_status_exposes_summary_counts(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ensure_scaffold()
    state = knowledge_base._load_state()
    state["connector_sync"] = {
        "updated_at": "2026-04-08T12:00:00+00:00",
        "connectors": {},
        "checkpoints": {
            "email_threads": {
                "health_status": "invalid",
                "sync_status": "retry_scheduled",
                "consecutive_failures": 2,
            },
            "calendar_events": {
                "health_status": "valid",
                "sync_status": "completed",
            },
        },
        "jobs": [],
    }
    knowledge_base._save_state(state)

    status = knowledge_base.connector_sync_status(store=None)

    assert status["summary"]["total_connectors"] >= 2
    assert status["summary"]["attention_required"] >= 1
    assert status["summary"]["retry_scheduled"] >= 1


def test_orchestration_status_tracks_due_and_failures(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ensure_scaffold()
    state = knowledge_base._load_state()
    state["orchestration"] = {
        "jobs": {
            "trigger_evaluation": {
                "job": "trigger_evaluation",
                "status": "failed",
                "failure_count": 2,
                "last_completed_at": "2026-04-08T09:00:00+00:00",
                "cadence_seconds": 300,
                "last_error": "timeout",
            },
            "connector_sync": {
                "job": "connector_sync",
                "status": "completed",
                "last_completed_at": "2026-04-08T11:59:00+00:00",
                "cadence_seconds": 600,
            },
        }
    }
    knowledge_base._save_state(state)

    status = knowledge_base.orchestration_status()
    failed_job = next(item for item in status["jobs"] if item["job"] == "trigger_evaluation")

    assert status["summary"]["failed_jobs"] >= 1
    assert status["summary"]["due_jobs"] >= 1
    assert failed_job["is_due"] is True
    assert failed_job["next_due_at"]


def test_orchestration_failure_schedules_retry_with_status_message(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")

    def _fail_reflection():
        raise RuntimeError("reflection timeout")

    knowledge_base.run_reflection = _fail_reflection  # type: ignore[method-assign]

    result = knowledge_base.run_orchestration(
        store=store,
        settings=None,
        job_names=["reflection_pass"],
        reason="unit_failure",
        force=True,
        now=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
    )
    status = knowledge_base.orchestration_status()
    job = next(item for item in status["jobs"] if item["job"] == "reflection_pass")

    assert result["results"][0]["status"] == "retry_scheduled"
    assert status["summary"]["retry_scheduled"] >= 1
    assert job["status"] == "retry_scheduled"
    assert job["retry_delay_seconds"] >= 120
    assert "yeniden denenecek" in str(job["status_message"])


def test_orchestration_skips_job_when_running_lock_is_fresh(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ensure_scaffold()
    state = knowledge_base._load_state()
    state["orchestration"] = {
        "jobs": {
            "suppression_cleanup": {
                "job": "suppression_cleanup",
                "status": "running",
                "last_started_at": "2026-04-08T10:00:00+00:00",
                "cadence_seconds": 1800,
            }
        }
    }
    knowledge_base._save_state(state)

    result = knowledge_base.run_orchestration(
        store=store,
        settings=None,
        job_names=["suppression_cleanup"],
        reason="manual",
        force=False,
        now=datetime(2026, 4, 8, 10, 2, tzinfo=timezone.utc),
    )

    assert result["results"][0]["status"] == "skipped"
    assert result["results"][0]["reason"] == "already_running"


def test_action_routes_expose_launch_hardened_action_ladder(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    generate_action = _route_endpoint(app, "/assistant/actions/generate", "POST")

    token_body = issue_token(TokenRequest(subject="launch-user", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"
    generated = generate_action(
        AssistantActionGenerateRequest(
            action_type="create_task",
            target_channel="task",
            title="Gorev taslagi",
            instructions="Yarin sabah icin kisa bir gorev taslagi hazirla.",
            source_refs=[],
        ),
        authorization=authorization,
    )

    ladder = generated["action_ladder"]
    assert ladder["trusted_low_risk_available"] is True
    assert ladder["preview_required_before_execute"] is True
    assert ladder["preview_summary"]
    assert ladder["undo_strategy"]
    assert ladder["execution_policy"] == "preview_then_confirm"
    assert ladder["approval_reason"]
    assert ladder["irreversible"] is False


def test_wiki_brain_compiles_concept_articles_and_context(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ingest(
        source_type="user_preferences",
        title="Iletisim tarzi",
        content="Kisa, nazik ve net bir iletisim tarzi tercih ediyorum.",
        metadata={"field": "communication_style", "scope": "personal"},
        tags=["preferences", "tone"],
    )
    knowledge_base.maybe_file_back_response(
        kind="daily_planning_output",
        title="Aksam plani",
        content="Aksam icin hafifletilmis plan, kisa kapanis notu ve sakin bir rota yararli olabilir.",
        metadata={"page_key": "projects", "record_type": "goal", "scope": "personal"},
        scope="personal",
        sensitivity="medium",
    )

    compiled = knowledge_base.compile_wiki_brain(reason="unit_test", previews=True)
    resolved = knowledge_base.resolve_relevant_context("iletisim tarzi ve aksam plani", scopes=["personal"], limit=6)

    assert compiled["concept_count"] >= 3
    assert (knowledge_base.base_dir / "wiki" / "concepts" / "INDEX.md").exists()
    assert compiled["concepts"]
    first_concept_path = Path(compiled["concepts"][0]["path"])
    assert first_concept_path.exists()
    assert "## Supporting Records" in first_concept_path.read_text(encoding="utf-8")
    assert resolved["knowledge_articles"]
    assert resolved["supporting_concepts"]
    assert resolved["context_selection_reasons"]


def test_knowledge_synthesis_creates_insight_records_and_reports(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base._record_recommendation(
        {
            "id": "rec-evening-1",
            "kind": "daily_plan",
            "suggestion": "Aksam icin hafifletilmis plan oner.",
            "why_this": "Yogun gunlerde bu tur plan faydali.",
            "confidence": 0.84,
            "requires_confirmation": False,
            "source_basis": [],
            "next_actions": ["Plan taslagi hazirla"],
            "memory_scope": ["personal"],
        }
    )
    knowledge_base.record_recommendation_feedback("rec-evening-1", "accepted", note="Bu tarz plan yararli.")
    knowledge_base._record_recommendation(
        {
            "id": "rec-evening-2",
            "kind": "calendar_nudge",
            "suggestion": "Gun sonu kapanis notu oner.",
            "why_this": "Aksam saatlerinde kapanis iyi geliyor.",
            "confidence": 0.81,
            "requires_confirmation": False,
            "source_basis": [],
            "next_actions": ["Kapanis notu hazirla"],
            "memory_scope": ["personal"],
        }
    )
    knowledge_base.record_recommendation_feedback("rec-evening-2", "accepted", note="Aksam kapanisi faydali.")
    knowledge_base._record_trigger_event(
        {
            "id": "tr-evening-1",
            "trigger_type": "daily_planning",
            "logical_key": "daily-planning",
            "title": "Aksam plan trigger",
            "scope": "personal",
            "confidence": 0.72,
            "urgency": "medium",
            "recommended_action": {"kind": "daily_plan"},
        },
        emitted_at="2026-04-08T18:00:00+00:00",
    )
    knowledge_base._record_trigger_event(
        {
            "id": "tr-evening-2",
            "trigger_type": "end_of_day_reflection",
            "logical_key": "end-of-day",
            "title": "Gun sonu reflection",
            "scope": "personal",
            "confidence": 0.7,
            "urgency": "low",
            "recommended_action": {"kind": "daily_plan"},
        },
        emitted_at="2026-04-08T20:00:00+00:00",
    )

    synthesis = knowledge_base.run_knowledge_synthesis(reason="unit_test")
    overview = knowledge_base.memory_overview()

    assert synthesis["summary"]["generated_records"] >= 2
    assert synthesis["summary"]["generated_strategies"] >= 1
    assert Path(synthesis["report_path"]).exists()
    assert Path(synthesis["report_json_path"]).exists()
    assert overview["by_type"].get("insight", 0) >= 2
    assert any(item["page_key"] in {"preferences", "routines"} for item in synthesis["insights"])
    assert synthesis["strategies"]
    assert synthesis["hypotheses"]


def test_reflection_reports_wiki_gaps_research_topics_and_potential_pages(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base._record_recommendation(
        {
            "id": "rec-reminder-1",
            "kind": "smart_reminder",
            "suggestion": "Kisa reminder onerisi",
            "why_this": "Acik gorev var.",
            "confidence": 0.6,
            "requires_confirmation": False,
            "source_basis": [],
            "next_actions": ["Reminder taslagi"],
            "memory_scope": ["personal"],
        }
    )
    knowledge_base.record_recommendation_feedback("rec-reminder-1", "rejected", note="Sik reminder istemiyorum.")
    knowledge_base._record_recommendation(
        {
            "id": "rec-reminder-2",
            "kind": "smart_reminder",
            "suggestion": "Bir reminder daha",
            "why_this": "Gorev gecikiyor.",
            "confidence": 0.58,
            "requires_confirmation": False,
            "source_basis": [],
            "next_actions": ["Reminder taslagi"],
            "memory_scope": ["personal"],
        }
    )
    knowledge_base.record_recommendation_feedback("rec-reminder-2", "rejected", note="Bu tur oneriler yorucu.")

    report = knowledge_base.run_reflection()

    assert "knowledge_gaps" in report
    assert "research_topics" in report
    assert "potential_wiki_pages" in report
    assert report["summary"]["knowledge_gaps"] >= 1
    assert report["summary"]["potential_wiki_pages"] >= 1


def test_reflection_status_updates_last_reflection_and_recommended_actions(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ensure_scaffold()
    state = knowledge_base._load_state()
    knowledge_base._upsert_page_record(
        state,
        "preferences",
        {
            "id": "pref-stale-reflection",
            "key": "stale_reflection_pref",
            "title": "Eski tercih",
            "summary": "Bu kayıt artık güncel olmayabilir.",
            "confidence": 0.3,
            "status": "active",
            "source_refs": ["manual:test"],
            "signals": ["assistant_inference"],
            "updated_at": "2024-01-01T00:00:00+00:00",
            "metadata": {
                "field": "misc",
                "scope": "personal",
                "record_type": "preference",
                "correction_history": [{"action": "correct"}] * 4,
            },
        },
    )
    knowledge_base._save_state(state)
    knowledge_base._render_all(state)

    report = knowledge_base.run_reflection()
    status = knowledge_base.reflection_status()

    assert report["status"]["status"] == "completed"
    assert status["last_reflection_at"] == report["generated_at"]
    assert status["next_due_at"]
    assert status["summary"]["prunable_records"] >= 1
    assert status["recommended_kb_actions"]


def test_wiki_brain_uses_llm_authored_article_sections_when_runtime_available(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(
        tmp_path / "personal-kb",
        "default-office",
        article_runtime=_FakeArticleRuntime(),
        enable_llm_article_authoring=True,
        llm_article_limit=2,
    )
    knowledge_base.ingest(
        source_type="assistant_file_back",
        title="Planlama stili",
        content="Kullanici aksamlari kisa kapanis planlari ile daha rahat ilerliyor.",
        metadata={
            "page_key": "preferences",
            "record_type": "preference",
            "scope": "personal",
            "field": "planning_style",
            "sensitivity": "low",
            "exportability": "cloud_allowed",
        },
    )

    compiled = knowledge_base.compile_wiki_brain(reason="llm_article_test", previews=True)
    concept_path = Path(compiled["concepts"][0]["path"])
    concept_body = concept_path.read_text(encoding="utf-8")

    assert compiled["summary"]["authoring_modes"]["llm_runtime"] >= 1
    assert "## Detailed Explanation" in concept_body
    assert "## Strategy Notes" in concept_body
    assert "Preview-first plan yardimini oncele." in concept_body


def test_ensure_scaffold_is_idempotent_after_initial_article_render(tmp_path: Path) -> None:
    runtime = _CountingArticleRuntime()
    knowledge_base = KnowledgeBaseService(
        tmp_path / "personal-kb",
        "default-office",
        article_runtime=runtime,
        enable_llm_article_authoring=True,
        llm_article_limit=2,
    )
    knowledge_base.ingest(
        source_type="assistant_file_back",
        title="Planlama stili",
        content="Kullanici aksamlari kisa kapanis planlari ile daha rahat ilerliyor.",
        metadata={
            "page_key": "preferences",
            "record_type": "preference",
            "scope": "personal",
            "field": "planning_style",
            "sensitivity": "low",
            "exportability": "cloud_allowed",
        },
    )

    initial_calls = runtime.call_count

    knowledge_base.ensure_scaffold()
    knowledge_base.ensure_scaffold()

    assert initial_calls >= 1
    assert runtime.call_count == initial_calls


def test_wiki_brain_status_persists_rebuilt_brain_once_when_artifact_missing(tmp_path: Path) -> None:
    runtime = _CountingArticleRuntime()
    knowledge_base = KnowledgeBaseService(
        tmp_path / "personal-kb",
        "default-office",
        article_runtime=runtime,
        enable_llm_article_authoring=True,
        llm_article_limit=2,
    )
    knowledge_base.ingest(
        source_type="assistant_file_back",
        title="Planlama stili",
        content="Kullanici aksamlari kisa kapanis planlari ile daha rahat ilerliyor.",
        metadata={
            "page_key": "preferences",
            "record_type": "preference",
            "scope": "personal",
            "field": "planning_style",
            "sensitivity": "low",
            "exportability": "cloud_allowed",
        },
    )
    original_calls = runtime.call_count
    knowledge_base._wiki_brain_path().unlink()

    first_status = knowledge_base.wiki_brain_status(ensure=False, previews=False)
    rebuilt_calls = runtime.call_count
    second_status = knowledge_base.wiki_brain_status(ensure=False, previews=False)

    assert first_status["concept_count"] >= 1
    assert second_status["concept_count"] == first_status["concept_count"]
    assert rebuilt_calls > original_calls
    assert runtime.call_count == rebuilt_calls


def test_semantic_retrieval_matches_synonyms_and_priority(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ensure_scaffold()
    state = knowledge_base._load_state()
    knowledge_base._upsert_page_record(
        state,
        "preferences",
        {
            "id": "pref-mail-style",
            "key": "mail_style",
            "title": "Mail cevap tarzı",
            "summary": "E-posta yanitlarinda kisa, net ve nazik taslaklar tercih ediliyor.",
            "confidence": 0.91,
            "status": "active",
            "source_refs": ["manual:test"],
            "signals": ["explicit_profile"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "field": "communication_style",
                "scope": "personal",
                "record_type": "conversation_style",
            },
        },
    )
    knowledge_base._upsert_page_record(
        state,
        "preferences",
        {
            "id": "pref-random",
            "key": "random_note",
            "title": "Rastgele not",
            "summary": "Bahce bitkileri icin sulama plani notu.",
            "confidence": 0.44,
            "status": "active",
            "source_refs": ["manual:test"],
            "signals": ["assistant_inference"],
            "updated_at": "2025-01-01T00:00:00+00:00",
            "metadata": {
                "field": "misc",
                "scope": "personal",
                "record_type": "source",
                "correction_history": [{"action": "reduce_confidence"}] * 3,
            },
        },
    )
    knowledge_base._save_state(state)
    knowledge_base._render_all(state)

    search = knowledge_base.search("eposta reply tonu", scopes=["personal"], limit=4)

    assert search["items"]
    assert search["items"][0]["record_id"] == "pref-mail-style"
    assert any(
        reason in search["items"][0]["selection_reasons"]
        for reason in ("semantic_vector_match", "semantic_reranker", "semantic_expansion")
    )
    assert search["diagnostics"]["result_count"] >= 1


def test_consumer_context_connectors_collect_browser_and_external_signals(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    office_id = "default-office"
    run = store.create_agent_run(
        office_id,
        title="Reading research",
        goal="Gather reading and video signals",
        created_by="tester",
        status="completed",
        source_kind="assistant",
        run_type="investigation",
    )
    store.create_browser_session_artifact(
        office_id,
        run_id=int(run["id"]),
        artifact_type="bookmark",
        url="https://www.youtube.com/watch?v=test123",
        metadata={
            "title": "Morning habit systems",
            "query": "habit stacking youtube",
            "scope": "personal",
        },
    )
    store.add_external_event(
        office_id,
        provider="youtube",
        event_type="watch_history",
        summary="User watched a morning routine productivity video.",
        external_ref="yt:test123",
        title="Morning routine video",
        metadata={"url": "https://www.youtube.com/watch?v=test123", "scope": "personal"},
    )

    browser_records = BrowserContextConnector().collect(store=store, office_id=office_id)
    consumer_records = ConsumerSignalsConnector().collect(store=store, office_id=office_id)

    assert any(item.source_type in {"youtube_history", "reading_list"} for item in browser_records)
    assert any(item.source_type == "youtube_history" for item in consumer_records)
    assert any((item.metadata or {}).get("epistemic_claim_hints") for item in browser_records)
    assert any((item.metadata or {}).get("epistemic_claim_hints") for item in consumer_records)

    epistemic = EpistemicService(store, office_id)
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id, epistemic=epistemic)
    result = knowledge_base.sync_from_store(store=store, reason="consumer_sync")
    search = knowledge_base.search("youtube video aliskanligi", scopes=["personal"], limit=5)
    resolved = knowledge_base.resolve_relevant_context("habit stacking youtube", scopes=["personal"], limit=5)
    query_claims = store.list_epistemic_claims(office_id, predicate="query", scope="personal", include_blocked=True, limit=20)

    assert result["connector_sync"]["synced_record_count"] >= 1
    assert any(item["page_key"] in {"projects", "preferences", "contacts", "places", "recommendations", "routines"} for item in search["items"])
    assert query_claims
    assert any("Araştırma sorgusu" in line or "İçerik başlığı" in line for line in list(resolved.get("claim_summary_lines") or []))
    assert "claim_resolved_context" in list(resolved.get("context_selection_reasons") or [])


def test_connector_sync_status_marks_stale_connectors(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ensure_scaffold()
    state = knowledge_base._load_state()
    state["connector_sync"] = {
        "checkpoints": {
            "email_threads": {
                "last_success_at": "2026-04-01T00:00:00+00:00",
                "last_synced_at": "2026-04-01T00:00:00+00:00",
                "sync_status": "completed",
                "health_status": "valid",
            }
        }
    }
    knowledge_base._save_state(state)

    status = knowledge_base.connector_sync_status(store=None)
    item = next(entry for entry in status["items"] if entry["connector"] == "email_threads")

    assert item["freshness_status"] == "stale"
    assert item["stale_sync"] is True
    assert status["summary"]["stale_connectors"] >= 1


def test_status_recovers_from_invalid_utf8_state_file(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ensure_scaffold()
    knowledge_base._state_path().write_bytes(b'{"pages": "\x9f"}')

    status = knowledge_base.status(ensure=False, previews=False)

    assert status["enabled"] is True
    assert status["pages"]
    assert status["decision_record_count"] == 0


def test_reflection_marks_prunable_records_and_inconsistency_hotspots(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ensure_scaffold()
    state = knowledge_base._load_state()
    knowledge_base._upsert_page_record(
        state,
        "preferences",
        {
            "id": "pref-old-low",
            "key": "meal_style",
            "title": "Yemek tercihi",
            "summary": "Agir yemekleri seviyor.",
            "confidence": 0.22,
            "status": "active",
            "source_refs": ["manual:test"],
            "signals": ["assistant_inference"],
            "updated_at": "2024-01-01T00:00:00+00:00",
            "metadata": {
                "field": "meal_preferences",
                "scope": "personal",
                "repeated_contradiction_count": 2,
                "correction_history": [{"action": "correct"}] * 4,
            },
        },
    )
    knowledge_base._upsert_page_record(
        state,
        "preferences",
        {
            "id": "pref-old-low-2",
            "key": "meal_style",
            "title": "Yemek tercihi",
            "summary": "Aksam hafif yemekleri tercih ediyor.",
            "confidence": 0.72,
            "status": "active",
            "source_refs": ["manual:test"],
            "signals": ["explicit_profile"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"field": "meal_preferences", "scope": "personal"},
        },
    )
    knowledge_base._save_state(state)
    knowledge_base._render_all(state)

    report = knowledge_base.run_reflection()

    assert report["summary"]["prunable_records"] >= 1
    assert report["summary"]["inconsistency_hotspots"] >= 1
    assert report["prunable_records"]


def test_location_snapshot_exposes_lifecycle_and_device_context(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "desktop-location-device.json"
    observed_at = datetime.now(timezone.utc).isoformat()
    snapshot_path.write_text(
        json.dumps(
            {
                "observed_at": observed_at,
                "scope": "personal",
                "sensitivity": "high",
                "current_place": {
                    "place_id": "kadikoy-rihtim",
                    "label": "Kadikoy Rihtim",
                    "category": "transit",
                    "area": "Kadikoy",
                },
                "device_context": {
                    "activity_state": "idle",
                    "idle_minutes": 42,
                    "active_hours": [8, 9, 10],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = Persistence(tmp_path / "lawcopilot.db")
    knowledge_base = KnowledgeBaseService(
        tmp_path / "personal-kb",
        "default-office",
        location_snapshot_path=snapshot_path,
        location_provider_mode="desktop_file_fallback",
    )

    context = knowledge_base.get_location_context(store=store)

    assert context["device_context"]["activity_state"] == "idle"
    assert context["context_composition"]["lifecycle_stage"] == "fresh_snapshot"
    assert context["context_composition"]["has_current_place"] is True


def test_scaffold_render_recovers_from_non_utf8_concept_index(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    knowledge_base.ensure_scaffold()
    corrupted_index_path = knowledge_base.base_dir / "wiki" / "concepts" / "INDEX.md"
    corrupted_index_path.parent.mkdir(parents=True, exist_ok=True)
    corrupted_index_path.write_bytes(b"# broken\n\xba\xba\xba")

    state = knowledge_base._load_state()
    knowledge_base._render_all(state)
    status = knowledge_base.status(ensure=False, previews=True)

    assert corrupted_index_path.read_text(encoding="utf-8").startswith("#")
    assert status["enabled"] is True


def test_coaching_goal_lifecycle_updates_dashboard_and_records(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")

    created = knowledge_base.upsert_coaching_goal(
        title="Her sabah 20 sayfa oku",
        summary="Okuma aliskanligi icin sabah check-in yap.",
        cadence="daily",
        target_value=100,
        unit="sayfa",
        reminder_time="08:00",
        source_refs=["manual:test"],
    )

    dashboard = created["dashboard"]
    assert dashboard["summary"]["active_goals"] == 1
    assert dashboard["active_goals"][0]["title"] == "Her sabah 20 sayfa oku"

    logged = knowledge_base.log_coaching_progress(
        goal_id=str(dashboard["active_goals"][0]["id"]),
        amount=20,
        note="Bugun ilk bolumu okudum.",
    )

    assert float(logged["goal"]["current_value"]) == 20.0
    assert logged["dashboard"]["summary"]["progress_logs"] >= 1

    state = knowledge_base._load_state()
    routine_records = ((state.get("pages") or {}).get("routines") or {}).get("records") or []
    project_records = ((state.get("pages") or {}).get("projects") or {}).get("records") or []
    assert any((record.get("metadata") or {}).get("coach_goal") for record in routine_records if isinstance(record, dict))
    assert any((record.get("metadata") or {}).get("coach_progress") for record in project_records if isinstance(record, dict))


def test_coaching_due_checkin_generates_trigger_and_recommendation(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    created = knowledge_base.upsert_coaching_goal(
        title="Aksam kitabi takip et",
        summary="Her gun aksam ilerleme gir.",
        cadence="daily",
        target_value=50,
        unit="sayfa",
        reminder_time="08:00",
        source_refs=["manual:test"],
    )
    goal_id = str(created["dashboard"]["active_goals"][0]["id"])
    state = knowledge_base._load_state()
    state.setdefault("coaching", {}).setdefault("goals", {}).setdefault(goal_id, {})["next_check_in_at"] = "2026-04-08T06:00:00+00:00"
    state["updated_at"] = "2026-04-08T06:00:00+00:00"
    knowledge_base._save_state(state)

    triggers = knowledge_base.evaluate_triggers(
        store=store,
        settings=None,
        now=datetime.fromisoformat("2026-04-08T09:00:00+00:00"),
        persist=True,
        limit=6,
        include_suppressed=True,
    )
    recommendations = knowledge_base.recommend(
        store=store,
        settings=None,
        current_context="Bugunku hedeflerimi toparla",
        location_context=None,
        limit=5,
        persist=False,
    )

    assert any("check-in" in str(item.get("title") or "").lower() for item in triggers["items"])
    assert any("check-in" in str(item.get("suggestion") or "").lower() for item in recommendations["items"])

    second = knowledge_base.evaluate_triggers(
        store=store,
        settings=None,
        now=datetime.fromisoformat("2026-04-08T09:05:00+00:00"),
        persist=True,
        limit=6,
        include_suppressed=True,
    )
    assert not second["items"]
    assert any(item.get("suppression_reason") == "cooldown_active" for item in second["suppressed"])


def test_autonomy_governor_reduces_low_value_trigger_spam_after_rejections(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office")
    for index in range(3):
        recommendation = {
            "id": f"reminder-fatigue-{index}",
            "kind": "smart_reminder",
            "suggestion": f"Hatırlatma önerisi {index}",
            "why_this": f"Açık görev bulundu {index}.",
            "confidence": 0.62,
            "requires_confirmation": False,
            "source_basis": [],
            "next_actions": ["Hatırlatma hazırla"],
            "memory_scope": ["personal"],
        }
        knowledge_base._record_recommendation(recommendation)
        knowledge_base.record_recommendation_feedback(recommendation["id"], "rejected", note="Daha az öneri istiyorum.")

    trigger_payload = knowledge_base.evaluate_triggers(
        store=store,
        settings=None,
        now=datetime.fromisoformat("2026-04-08T12:30:00+00:00"),
        persist=False,
        include_suppressed=True,
        limit=4,
    )
    autonomy = knowledge_base.autonomy_status(store=store)

    assert not trigger_payload["items"]
    assert any(item.get("suppression_reason") == "fatigue_guard_active" for item in trigger_payload["suppressed"])
    assert autonomy["policy"]["suggestion_budget"] <= 2


def test_coaching_routes_return_home_dashboard(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    upsert_goal = _route_endpoint(app, "/assistant/coaching/goals", "POST")
    log_progress = _route_endpoint(app, "/assistant/coaching/goals/{goal_id}/progress", "POST")
    get_home = _route_endpoint(app, "/assistant/home", "GET")

    token_body = issue_token(TokenRequest(subject="coach-user", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    created = upsert_goal(
        CoachingGoalUpsertRequest(
            title="Her sabah oku",
            summary="Okuma hedefi",
            cadence="daily",
            target_value=120,
            unit="sayfa",
            reminder_time="08:00",
        ),
        authorization=authorization,
    )
    goal_id = str(((created.get("dashboard") or {}).get("active_goals") or [])[0]["id"])
    progress = log_progress(
        goal_id,
        CoachingProgressLogRequest(amount=15, note="Bugun ilerledim."),
        authorization=authorization,
    )
    home = get_home(authorization=authorization)

    assert progress["goal"]["current_value"] == 15.0
    assert home["assistant_core"]["summary"]["supports_coaching"] is True
    assert any(item["slug"] == "goal_tracking" for item in home["assistant_core"]["capability_contracts"])
    assert any(item["slug"] == "coaching_dashboard" for item in home["assistant_core"]["surface_contracts"])
    assert home["coaching_dashboard"]["summary"]["active_goals"] >= 1
    assert home["coaching_dashboard"]["active_goals"][0]["title"]


def test_memory_explorer_methods_expose_pages_graph_timeline_and_health(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office", epistemic=epistemic)
    first = knowledge_base.ingest(
        source_type="assistant_file_back",
        title="Anneye mesaj tonu",
        content="Annemle yazisirken sicak, kisa ve dusunceli mesajlar daha iyi calisiyor.",
        metadata={
            "page_key": "preferences",
            "record_type": "conversation_style",
            "scope": "personal",
            "field": "communication_style:mother",
        },
        source_ref="assistant-message:42",
        tags=["feedback", "communication"],
    )
    knowledge_base.ingest(
        source_type="assistant_runtime_snapshot",
        title="Soul note",
        content="Kritik aksiyonlardan once preview goster ve nedenini acikla.",
        metadata={
            "page_key": "persona",
            "record_type": "person",
            "scope": "personal",
            "field": "soul_notes",
        },
        source_ref="runtime:soul",
        tags=["runtime", "soul"],
    )
    knowledge_base.ingest(
        source_type="assistant_runtime_snapshot",
        title="Heartbeat check",
        content="Aksam gun kapanisinda plan ve okuma hedefini tekrar hatirlat.",
        metadata={
            "page_key": "routines",
            "record_type": "routine",
            "scope": "personal",
            "field": "heartbeat_evening",
        },
        source_ref="runtime:heartbeat",
        tags=["runtime", "heartbeat"],
    )
    knowledge_base.ingest(
        source_type="user_preferences",
        title="Iletisim tercihi",
        content="Bana kisa ve net cevap ver.",
        metadata={
            "page_key": "preferences",
            "record_type": "conversation_style",
            "scope": "personal",
            "field": "communication_style",
        },
        source_ref="manual:preference",
        tags=["preference"],
    )

    record_id = next(
        item["id"]
        for item in (((knowledge_base._load_state().get("pages") or {}).get("preferences") or {}).get("records") or [])
        if isinstance(item, dict) and str(item.get("status") or "active") == "active"
    )
    knowledge_base.apply_memory_correction(
        action="correct",
        page_key="preferences",
        target_record_id=str(record_id),
        corrected_summary="Annemle mesajlarda sicak ama hediyeyi zorlamayan kisa bir ton daha iyi.",
        note="Begeni aciklamasindan semantic correction",
        source_refs=["assistant-feedback:1"],
    )
    reflection = knowledge_base.run_reflection()
    (knowledge_base.system_dir / "SOUL.md").write_text("# SOUL\n\nPreview-first davran.\n", encoding="utf-8")
    (knowledge_base.system_dir / "HEARTBEAT.md").write_text("# HEARTBEAT\n\nAksam check-in yap.\n", encoding="utf-8")
    (knowledge_base._reports_dir() / "automation-notes.md").write_text("# Automation Notes\n\nRutin takip acik.\n", encoding="utf-8")

    pages = knowledge_base.memory_explorer_pages()
    page_detail = knowledge_base.memory_explorer_page("page:preferences")
    graph = knowledge_base.memory_explorer_graph(limit=18)
    timeline = knowledge_base.memory_explorer_timeline(limit=40)
    health = knowledge_base.memory_explorer_health()
    concept_details = [
        knowledge_base.memory_explorer_page(str(item["id"]))
        for item in list(pages.get("items") or [])
        if str(item.get("id") or "").startswith("concept:")
    ]

    assert any(item["id"] == "page:preferences" for item in pages["items"])
    assert any(item["id"].startswith("concept:") for item in pages["items"])
    assert any(item["id"] == "system:AGENTS.md" for item in pages["items"])
    assert any(item["id"] == "system:SOUL.md" for item in pages["items"])
    assert any(item["id"] == "system:HEARTBEAT.md" for item in pages["items"])
    assert any(item["id"] == "report:automation-notes.md" for item in pages["items"])
    assert page_detail["content_markdown"].startswith("# Preferences")
    assert page_detail["records"]
    assert any(item["id"].startswith("concept:") for item in page_detail["backlinks"])
    assert graph["nodes"]
    assert any(str(item.get("entity_type") or "") == "record" for item in graph["nodes"])
    assert any(str(item.get("entity_type") or "") == "claim" for item in graph["nodes"])
    assert any(str(item.get("relation_type") or "") in {"inferred_from", "scoped_to", "prefers"} for item in graph["edges"])
    assert any(str(item.get("relation_type") or "") == "resolves_to" for item in graph["edges"])
    assert any(item["event_type"].startswith("memory_") for item in timeline["items"])
    assert any(item["event_type"] == "reflection_output" for item in timeline["items"])
    assert health["recommended_kb_actions"]
    assert health["reflection_output"]["generated_at"] == reflection["generated_at"]
    assert "wiki_dir" in health["transparency"]
    assert concept_details
    assert any(list(item.get("claim_bindings") or []) for item in concept_details)


def test_memory_explorer_concept_exposes_claim_bindings_for_explicit_record(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office", epistemic=epistemic)
    knowledge_base.ingest(
        source_type="user_preferences",
        title="İletişim tercihi",
        content="Bana kısa ve net cevap ver.",
        metadata={
            "page_key": "preferences",
            "record_type": "conversation_style",
            "scope": "personal",
            "field": "communication_style",
        },
        source_ref="manual:pref",
        tags=["preference"],
    )

    concept_page = knowledge_base.memory_explorer_page("concept:topic:communication-style")

    assert concept_page["claim_bindings"]
    assert any(
        isinstance(item, dict)
        and str(item.get("predicate") or "") == "communication_style"
        and str(item.get("support_strength") or "") == "grounded"
        for item in list(concept_page.get("claim_bindings") or [])
    )
    assert concept_page["article_claim_bindings"]
    assert any(
        isinstance(item, dict)
        and str(item.get("section") or "") == "summary"
        and list(item.get("claim_ids") or [])
        for item in list(concept_page.get("article_claim_bindings") or [])
    )
    assert "## Claim Sentence Bindings" in str(concept_page.get("content_markdown") or "")
    assert "claim=user.communication_style (current)" in str(concept_page.get("content_markdown") or "")


def test_memory_explorer_exposes_epistemic_resolution_for_explicit_record(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office", epistemic=epistemic)
    knowledge_base.ingest(
        source_type="user_preferences",
        title="İletişim tercihi",
        content="Bana kısa ve net cevap ver.",
        metadata={
            "page_key": "preferences",
            "record_type": "conversation_style",
            "scope": "personal",
            "field": "communication_style",
        },
        source_ref="manual:pref",
        tags=["preference"],
    )

    page_detail = knowledge_base.memory_explorer_page("page:preferences")
    pages = knowledge_base.memory_explorer_pages()
    health = knowledge_base.memory_explorer_health()
    epistemic = next(
        item.get("epistemic")
        for item in list(page_detail.get("records") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    )

    assert epistemic
    assert epistemic["status"] == "current"
    assert epistemic["predicate"] == "communication_style"
    assert epistemic["support_strength"] == "grounded"
    assert epistemic["memory_tier"] == "hot"
    assert float(epistemic["salience_score"]) > 0.7
    assert any(
        isinstance(item, dict) and str(item.get("predicate") or "") == "communication_style"
        for item in list(page_detail.get("claim_bindings") or [])
    )
    assert page_detail["article_claim_bindings"]
    assert any(
        isinstance(item, dict)
        and str(item.get("section") or "") == "İletişim tercihi"
        and list(item.get("claim_ids") or [])
        for item in list(page_detail.get("article_claim_bindings") or [])
    )
    page_item = next(item for item in list(pages.get("items") or []) if item["id"] == "page:preferences")
    assert ((page_item.get("claim_summary") or {}).get("status_counts") or {}).get("current") == 1
    assert "Claim binding:" in str(page_detail.get("content_markdown") or "")
    assert "## Claim Sentence Bindings" in str(page_detail.get("content_markdown") or "")
    assert "claims=" in str(page_detail.get("content_markdown") or "")
    assert health["claim_summary"]["total_claims"] >= 1
    assert ((health["claim_summary"] or {}).get("memory_tier_counts") or {}).get("hot", 0) >= 1


def test_memory_explorer_page_renders_current_compiled_markdown_when_file_is_stale(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", "default-office", epistemic=epistemic)
    knowledge_base.ingest(
        source_type="user_preferences",
        title="İletişim tercihi",
        content="Bana kısa ve net cevap ver.",
        metadata={
            "page_key": "preferences",
            "record_type": "conversation_style",
            "scope": "personal",
            "field": "communication_style",
        },
        source_ref="manual:pref",
        tags=["preference"],
    )
    stale_path = knowledge_base.wiki_dir / "preferences.md"
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text("# Preferences\n\n- stale export\n", encoding="utf-8")

    page_detail = knowledge_base.memory_explorer_page("page:preferences")

    assert "stale export" not in str(page_detail.get("content_markdown") or "")
    assert "Claim binding:" in str(page_detail.get("content_markdown") or "")


def test_memory_explorer_health_reports_contaminated_claims(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    kb = KnowledgeBaseService(tmp_path / "personal-kb", "default-office", epistemic=epistemic)
    output = epistemic.record_assistant_output(
        kind="assistant_reply",
        title="Taslak stok cevabı",
        content="Kırmızı bitti gibi görünüyor.",
        scope="professional",
        sensitivity="medium",
    )
    epistemic.record_claim(
        subject_key="product:sku-42",
        predicate="inventory.status",
        object_value_text="Kırmızı bitti",
        scope="professional",
        epistemic_basis="inferred",
        validation_state="pending",
        metadata={"supporting_claim_ids": [output["claim"]["id"]]},
    )

    health = kb.memory_explorer_health()

    assert int((health["claim_summary"] or {}).get("contaminated_claims") or 0) >= 1
    assert ((health["claim_summary"] or {}).get("memory_tier_counts") or {}).get("cold", 0) >= 1
    assert any("assistant_only_support_chain" in list(item.get("reason_codes") or []) for item in (health.get("suspicious_claims") or []))
    assert int((((health.get("knowledge_lint") or {}).get("summary") or {}).get("contamination_risks") or 0) >= 1)
    assert "structural_lint" in health


def test_memory_explorer_timeline_includes_claim_and_context_snapshot_events(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    kb = KnowledgeBaseService(tmp_path / "personal-kb", "default-office", epistemic=epistemic)
    kb.ingest(
        source_type="user_preferences",
        title="İletişim tercihi",
        content="Bana kısa ve net cevap ver.",
        metadata={
            "page_key": "preferences",
            "record_type": "conversation_style",
            "scope": "personal",
            "field": "communication_style",
        },
        source_ref="manual:pref",
        tags=["preference"],
    )
    thread = store.create_assistant_thread("default-office", created_by="tester", title="Asistan")
    store.append_assistant_message(
        "default-office",
        thread_id=int(thread["id"]),
        role="assistant",
        content="Kısa ve net cevap vereceğim.",
        linked_entities=[],
        tool_suggestions=[],
        draft_preview=None,
        source_context={
            "assistant_context_pack": [
                {
                    "id": "pm:communication",
                    "prompt_line": "- [kullanıcı bilgisi] İletişim tercihi: Kısa ve net",
                }
            ]
        },
        requires_approval=False,
        generated_from="assistant_reply",
        ai_provider="test",
        ai_model="test-model",
    )

    timeline = kb.memory_explorer_timeline(limit=80)
    event_types = {str(item.get("event_type") or "") for item in list(timeline.get("items") or [])}

    assert "claim_update" in event_types
    assert "assistant_context_snapshot" in event_types


def test_connector_observed_preferences_promote_grounded_claim_and_search_reason(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    kb = KnowledgeBaseService(tmp_path / "personal-kb", "default-office", epistemic=epistemic)

    record = kb._memory_preference_record(
        page_key="preferences",
        record_key="communication_style:messages",
        title="Mesaj tonu sinyali",
        summary="Müşteri kısa ve net mesajları tercih ediyor.",
        scope="personal",
        note=None,
        source_refs=["messages:thread-1"],
        metadata={
            "source_type": "messages",
            "record_type": "conversation_style",
            "sensitivity": "medium",
            "field": "communication_style",
            "connector_name": "messages",
            "confidence": 0.74,
        },
        signals=["communication_source", "preference_hint"],
    )
    state = kb._load_state()
    kb._upsert_page_record(state, "preferences", record)
    kb._save_state(state)
    kb._render_all(state)

    resolved = epistemic.resolve_claim(
        subject_key="user",
        predicate="communication_style",
        scope="personal",
        include_blocked=True,
    )
    search = kb.search("müşteri mesaj tonu kısa ve net", scopes=["personal"], page_keys=["preferences"], limit=6)

    assert resolved["status"] == "current"
    assert resolved["current_claim"]["epistemic_basis"] == "connector_observed"
    assert resolved["current_claim_support"]["support_strength"] == "grounded"
    assert search["items"]
    assert "epistemic_grounded" in list(search["items"][0].get("selection_reasons") or [])
    assert ((search["items"][0].get("metadata") or {}).get("epistemic_support_strength")) == "grounded"


def test_search_excludes_contaminated_claim_backed_records(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "lawcopilot.db")
    epistemic = EpistemicService(store=store, office_id="default-office")
    kb = KnowledgeBaseService(tmp_path / "personal-kb", "default-office", epistemic=epistemic)

    output = epistemic.record_assistant_output(
        kind="assistant_reply",
        title="Stok cevabı taslağı",
        content="Kırmızı beden tükendi olabilir.",
        scope="professional",
        sensitivity="medium",
    )
    record = kb._memory_preference_record(
        page_key="preferences",
        record_key="inventory_status:sku42",
        title="Stok durumu",
        summary="Kırmızı beden tükendi.",
        scope="professional",
        note=None,
        source_refs=["assistant-output:inventory"],
        metadata={
            "field": "inventory_status",
            "record_type": "preference",
            "source_type": "inferred_memory",
            "confidence": 0.66,
            "supporting_claim_ids": [str(output["claim"]["id"] or "")],
        },
        signals=["semantic_learning"],
    )
    state = kb._load_state()
    kb._upsert_page_record(state, "preferences", record)
    kb._save_state(state)
    kb._render_all(state)

    page = kb.memory_explorer_page("page:preferences")
    epistemic_payload = next(
        item.get("epistemic")
        for item in list(page.get("records") or [])
        if isinstance(item, dict) and str(item.get("key") or "") == "inventory_status:sku42"
    )
    search = kb.search("kırmızı beden stok durumu", scopes=["professional"], limit=6)

    assert epistemic_payload
    assert epistemic_payload["status"] == "contaminated"
    assert epistemic_payload["support_contaminated"] is True
    assert search["items"] == []


def test_memory_explorer_routes_expose_transparent_memory_contract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ROOT", str(tmp_path / "personal-kb"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true")

    app = create_app()
    issue_token = _route_endpoint(app, "/auth/token", "POST")
    ingest = _route_endpoint(app, "/assistant/knowledge-base/ingest", "POST")
    memory_pages = _route_endpoint(app, "/memory/pages", "GET")
    memory_page = _route_endpoint(app, "/memory/page/{page_id}", "GET")
    memory_graph = _route_endpoint(app, "/memory/graph", "GET")
    memory_timeline = _route_endpoint(app, "/memory/timeline", "GET")
    memory_health = _route_endpoint(app, "/memory/health", "GET")
    memory_edit = _route_endpoint(app, "/memory/edit", "POST")
    memory_forget = _route_endpoint(app, "/memory/forget", "POST")
    memory_change_scope = _route_endpoint(app, "/memory/change-scope", "POST")

    token_body = issue_token(TokenRequest(subject="memory-user", role="lawyer"))
    authorization = f"Bearer {token_body['access_token']}"

    ingest(
        KnowledgeBaseIngestRequest(
            source_type="assistant_file_back",
            title="Rutin notu",
            content="Heartbeat: aksam kapanisinda oku, planla ve reflection al.",
            metadata={
                "page_key": "routines",
                "record_type": "routine",
                "scope": "personal",
                "field": "heartbeat_evening",
            },
            source_ref="runtime:heartbeat",
            tags=["heartbeat"],
        ),
        authorization=authorization,
    )
    ingest(
        KnowledgeBaseIngestRequest(
            source_type="assistant_file_back",
            title="Iletisim tercihi",
            content="Annemle mesajlarda kisa ve sicak ton daha iyi.",
            metadata={
                "page_key": "preferences",
                "record_type": "conversation_style",
                "scope": "personal",
                "field": "communication_style:mother",
            },
            source_ref="assistant-feedback:2",
            tags=["preference"],
        ),
        authorization=authorization,
    )

    pages_body = memory_pages(authorization=authorization)
    preference_page = memory_page("page:preferences", authorization=authorization)
    record_id = str((preference_page.get("records") or [])[0]["id"])
    edit_result = memory_edit(
        KnowledgeMemoryCorrectionRequest(
            action="reduce_confidence",
            page_key="preferences",
            target_record_id=record_id,
            note="Henüz tam emin değilim.",
        ),
        authorization=authorization,
    )
    scoped_result = memory_change_scope(
        MemoryScopeChangeRequest(
            page_key="preferences",
            target_record_id=record_id,
            scope="workspace",
            note="Bu bilgi workspace tarafında daha anlamlı.",
        ),
        authorization=authorization,
    )
    forgot_result = memory_forget(
        MemoryForgetRequest(
            page_key="preferences",
            target_record_id=str(scoped_result["record_id"]),
            note="Bu çıkarımı artık kullanma.",
        ),
        authorization=authorization,
    )
    graph_body = memory_graph(limit=18, authorization=authorization)
    timeline_body = memory_timeline(limit=40, authorization=authorization)
    health_body = memory_health(authorization=authorization)

    assert any(item["id"] == "page:preferences" for item in pages_body["items"])
    assert pages_body["transparency"]["wiki_dir"]
    assert preference_page["records"]
    assert edit_result["memory_overview"]["counts"]["records"] >= 1
    assert scoped_result["scope"] == "workspace"
    assert forgot_result["status"] == "forgotten"
    assert graph_body["nodes"]
    assert timeline_body["items"]
    assert "recommended_kb_actions" in health_body
