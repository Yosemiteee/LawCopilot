import tempfile
from pathlib import Path

from lawcopilot_api import app as app_module
from lawcopilot_api.context_packs import AssistantContextPackService
from lawcopilot_api.observability import StructuredLogger
from lawcopilot_api.persistence import Persistence


def test_assistant_context_pack_service_combines_personal_knowledge_and_operational_entries():
    service = AssistantContextPackService()

    personal_model_context = {
        "facts": [
            {
                "id": "pmf-1",
                "fact_key": "communication.style",
                "title": "İletişim tonu",
                "value_text": "Kısa ve net",
                "scope": "personal",
                "epistemic_status": "current",
                "epistemic_basis": "user_explicit",
                "epistemic_basis_label": "kullanıcı bilgisi",
                "epistemic_retrieval_eligibility": "eligible",
                "epistemic_support_strength": "grounded",
                "epistemic_support_contaminated": False,
                "confidence_type": "explicit",
                "updated_at": "2026-04-13T10:00:00+00:00",
                "confidence": 0.99,
                "sensitive": False,
                "category": "communication",
            }
        ]
    }
    knowledge_context = {
        "resolved_claims": [
            {
                "claim_id": "ec-1",
                "subject_key": "user",
                "predicate": "goal.primary",
                "value_text": "Daha düzenli çalışmak istiyor",
                "summary_line": "- [kullanıcı bilgisi] Birincil hedef: Daha düzenli çalışmak istiyor",
                "scope": "personal",
                "status": "current",
                "basis": "user_explicit",
                "retrieval_eligibility": "eligible",
                "support_strength": "grounded",
                "support_contaminated": False,
                "updated_at": "2026-04-10T10:00:00+00:00",
                "page_key": "goals",
            }
        ],
        "supporting_records": [],
    }
    inbox = [
        {
            "id": "whatsapp-1",
            "kind": "reply_needed",
            "title": "Stok sorusu",
            "details": "Müşteri kırmızı ürün var mı diye sordu.",
            "source_type": "whatsapp_message",
            "source_ref": "wa-1",
            "provider": "whatsapp",
            "priority": "high",
            "contact_label": "Ayşe",
            "due_at": "2026-04-13T09:00:00+00:00",
        }
    ]
    calendar = [
        {
            "id": "calendar-1",
            "kind": "calendar_event",
            "title": "Tedarikçi görüşmesi",
            "details": "Yeni sezon ürünleri",
            "source_type": "calendar_event",
            "source_ref": "cal-1",
            "starts_at": "2026-04-14T09:00:00+00:00",
            "needs_preparation": True,
            "provider": "google",
        }
    ]

    pack = service.build_combined_pack(
        query="Bugün neye dikkat etmeliyim?",
        personal_model_context=personal_model_context,
        knowledge_context=knowledge_context,
        inbox=inbox,
        calendar=calendar,
        limit=12,
    )

    families = {item["family"] for item in pack}
    assert {"personal_model", "knowledge_base", "operational"} <= families
    assert all(item["assistant_visibility"] in {"visible", "blocked"} for item in pack)
    assert all(item["prompt_line"] for item in pack)
    operational_items = [item for item in pack if item["family"] == "operational"]
    assert operational_items
    assert operational_items[0]["metadata"]["memory_state"] == "operational_only"


def test_compose_assistant_thread_reply_exposes_combined_assistant_context_pack(monkeypatch):
    temp_root = tempfile.mkdtemp(prefix="lawcopilot-context-pack-")
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(Path(temp_root) / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(Path(temp_root) / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(Path(temp_root) / "events.log.jsonl"))
    store = Persistence(Path(temp_root) / "lawcopilot.db")
    settings = app_module.get_settings()
    events = StructuredLogger(Path(temp_root) / "events.log.jsonl")

    body = app_module._compose_assistant_thread_reply(
        query="Bana kısa bir yanıt ver ve bugün ne var söyle.",
        matter_id=None,
        source_refs=None,
        recent_messages=[],
        subject="context-pack-user",
        settings=settings,
        store=store,
        runtime=None,
        events=events,
        knowledge_context={
            "query": "Bana kısa bir yanıt ver ve bugün ne var söyle.",
            "summary_lines": [],
            "claim_summary_lines": [],
            "assistant_context_pack": [
                {
                    "family": "knowledge_base",
                    "prompt_line": "- [kb] Çalışma stili: Kullanıcı kısa cevapları tercih ediyor.",
                }
            ],
            "supporting_pages": [],
            "supporting_records": [],
            "decision_records": [],
            "reflections": [],
            "recent_related_feedback": [],
            "scopes": [],
            "record_type_counts": {},
            "supporting_relations": [],
            "resolved_claims": [],
            "backend": None,
            "context_selection_reasons": [],
        },
        personal_model_context={
            "query": "Bana kısa bir yanıt ver ve bugün ne var söyle.",
            "intent": {"name": "communication", "categories": ["communication"]},
            "selected_categories": ["communication"],
            "facts": [
                {
                    "id": "pmf-1",
                    "fact_key": "communication.style",
                    "title": "İletişim tonu",
                    "value_text": "Kısa ve net",
                    "scope": "personal",
                    "epistemic_status": "current",
                    "epistemic_basis": "user_explicit",
                    "epistemic_basis_label": "kullanıcı bilgisi",
                    "epistemic_retrieval_eligibility": "eligible",
                    "epistemic_support_strength": "grounded",
                    "epistemic_support_contaminated": False,
                    "confidence_type": "explicit",
                    "updated_at": "2026-04-13T10:00:00+00:00",
                    "confidence": 0.99,
                    "sensitive": False,
                    "category": "communication",
                }
            ],
            "assistant_context_pack": [
                {
                    "family": "personal_model",
                    "prompt_line": "- [kullanıcı bilgisi] İletişim tonu: Kısa ve net",
                }
            ],
            "claim_summary_lines": [],
            "summary_lines": [],
            "usage_note": "Test bağlamı",
        },
    )

    pack = body["source_context"]["assistant_context_pack"]
    assert pack
    families = {item["family"] for item in pack}
    assert "personal_model" in families
