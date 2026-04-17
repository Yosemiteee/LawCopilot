import tempfile
from pathlib import Path

from lawcopilot_api.connectors import web_search as web_search_module
from lawcopilot_api.memory.service import MemoryService
from lawcopilot_api.persistence import Persistence
from lawcopilot_api.preference_rules import (
    extract_source_preference_rules_from_text,
    resolve_source_preference_context,
)


def test_extract_source_preference_rule_from_text():
    rules = extract_source_preference_rules_from_text(
        "Otobüs bileti alacağın zaman Pamukkale'den al ve https://pamukkale.com.tr linkinden bak.",
        existing_rules=[],
    )

    assert rules is not None
    assert rules[0]["task_kind"] == "travel_booking"
    assert "pamukkale.com.tr" in rules[0]["preferred_domains"]
    assert "https://pamukkale.com.tr" in rules[0]["preferred_links"]
    assert any("pamukkale" in str(item).lower() for item in rules[0]["preferred_providers"])


def test_resolve_source_preference_context_matches_profile_rules():
    profile = {
        "current_location": "İzmir / Alsancak",
        "source_preference_rules": [
            {
                "task_kind": "cinema",
                "policy_mode": "restrict",
                "preferred_domains": ["beyazperde.com"],
                "preferred_links": [],
                "preferred_providers": ["Beyazperde"],
                "note": "Sinema bakarken önce bunu kullan.",
            }
        ],
    }

    context = resolve_source_preference_context("Bu akşam sinema bak bana", profile=profile)

    assert context["matched_rules"]
    assert context["restricted_domains"] == ["beyazperde.com"]
    assert context["preferred_providers"] == ["Beyazperde"]
    assert context["location_hint"] == "İzmir / Alsancak"


def test_resolve_source_preference_context_does_not_force_search_for_generic_advice():
    context = resolve_source_preference_context(
        "İletişim tarzıma uygun kısa bir yanıt öner.",
        profile={},
    )

    assert context["task_kinds"] == ["general_research"]
    assert context["should_search"] is False


def test_build_web_search_context_honors_restricted_domains_and_pinned_links(monkeypatch):
    def fake_search_web(query: str, *, limit: int = 5):  # noqa: ARG001
        if "site:lexpera.com.tr" in query:
            return [
                {
                    "title": "Lexpera karar",
                    "url": "https://lexpera.com.tr/karar/123",
                    "snippet": "Lexpera sonucu",
                    "source": "fake",
                }
            ]
        return [
            {
                "title": "Lexpera karar",
                "url": "https://lexpera.com.tr/karar/123",
                "snippet": "Lexpera sonucu",
                "source": "fake",
            },
            {
                "title": "Başka site",
                "url": "https://ornek.com/karar/456",
                "snippet": "Başka sonuç",
                "source": "fake",
            },
        ]

    monkeypatch.setattr(web_search_module, "search_web", fake_search_web)

    context = web_search_module.build_web_search_context(
        "emsal karar araştır",
        search_preferences={
            "restricted_domains": ["lexpera.com.tr"],
            "preferred_links": ["https://lexpera.com.tr/favori"],
            "preferred_domains": ["lexpera.com.tr"],
            "preferred_providers": ["Lexpera"],
            "summary": "Hukuk araştırmasında Lexpera öncelikli",
        },
        limit=4,
    )

    results = list(context.get("results") or [])
    assert results[0]["url"] == "https://lexpera.com.tr/favori"
    assert all(
        item["url"] == "https://lexpera.com.tr/favori" or "lexpera.com.tr" in item["url"]
        for item in results
    )


def test_memory_service_captures_source_preference_rule_from_chat():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-source-preferences-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    service = MemoryService(store, "default-office")

    updates = service.capture_chat_signal(
        "Karar ararken şu sitelerden ara: lexpera.com.tr ve kazanci.com.tr. Gerekirse https://lexpera.com.tr linkinden başla."
    )
    profile = store.get_user_profile("default-office")

    assert any("source_preference_rules" in list(item.get("fields") or []) for item in updates)
    assert profile["source_preference_rules"]
    assert profile["source_preference_rules"][0]["task_kind"] == "legal_research"
    assert "lexpera.com.tr" in profile["source_preference_rules"][0]["preferred_domains"]
