from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile

import lawcopilot_api.assistant as assistant_module
import lawcopilot_api.app as app_module
import lawcopilot_api.automation_intents as automation_intents_module
from lawcopilot_api.assistant_core import apply_assistant_core_update, build_assistant_core_status, suggest_assistant_form_blueprint
from lawcopilot_api.app import _iter_text_deltas
from lawcopilot_api.observability import StructuredLogger
from lawcopilot_api.assistant import build_assistant_agenda
from lawcopilot_api.assistant import build_assistant_contact_profiles
from lawcopilot_api.assistant import build_assistant_home
from lawcopilot_api.assistant import build_assistant_inbox
from lawcopilot_api.assistant import build_suggested_actions
from lawcopilot_api.automation_intents import build_assistant_automation_update
from lawcopilot_api.memory.service import MemoryService
from lawcopilot_api.planner.service import build_thread_response_extensions
from lawcopilot_api.persona_text import compact_assistant_profile_value, compact_user_profile_value
from lawcopilot_api.persistence import Persistence
from lawcopilot_api.social_intelligence import is_social_monitoring_query


def test_build_assistant_inbox_prioritizes_executive_email(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-logic.db")
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-1",
        subject="CEO ile toplantı teyidi",
        participants=["ceo@example.com"],
        snippet="Yarin yonetim ekibiyle gorusecegiz.",
        received_at="2026-03-30T08:00:00+00:00",
        unread_count=0,
        reply_needed=True,
        metadata={
          "sender": "Ayse Kaya",
          "sender_title": "CEO",
        },
    )

    items = build_assistant_inbox(store, "default-office")

    assert items[0]["source_type"] == "email_thread"
    assert items[0]["priority"] == "high"
    assert "CEO" in str(items[0]["importance_reason"])
    assert "öncelikli inceleme" in str(items[0]["details"])


def test_build_assistant_core_status_exposes_generic_defaults_and_catalogs() -> None:
    payload = build_assistant_core_status(
        {
            "assistant_forms": [],
            "behavior_contract": {},
            "evolution_history": [],
        },
        coaching_goal_count=0,
    )

    assert payload["defaults"]["role_summary"] == "Kullanıcının istediğine göre şekillenen çekirdek asistan"
    assert any(item["slug"] == "life_coach" for item in payload["form_catalog"])
    assert any(item["slug"] == "goal_tracking" for item in payload["capability_catalog"])
    assert any(item["slug"] == "assistant_core" for item in payload["surface_catalog"])
    assert payload["operating_contract"]["mode"] == "general_core"
    assert payload["suggested_setup_actions"][0]["id"] == "choose-first-form"
    assert any(item["slug"] == "commerce_ops" for item in payload["form_catalog"])
    assert any(item["slug"] == "omnichannel_inbox" for item in payload["capability_catalog"])
    assert any(item["slug"] == "customer_inbox" for item in payload["surface_catalog"])


def test_build_assistant_core_status_exposes_capability_driven_operating_contract() -> None:
    payload = build_assistant_core_status(
        {
            "assistant_forms": [
                {
                    "slug": "kitap-okuma-kocu",
                    "title": "Kitap okuma koçu",
                    "active": True,
                    "custom": True,
                    "scopes": ["personal"],
                    "capabilities": ["goal_tracking", "reading_progress"],
                    "ui_surfaces": ["assistant_core", "coaching_dashboard"],
                    "supports_coaching": True,
                }
            ],
            "behavior_contract": {
                "initiative_level": "high",
                "follow_up_style": "persistent",
                "planning_depth": "deep",
            },
            "evolution_history": [],
        },
        coaching_goal_count=0,
    )

    assert payload["operating_contract"]["mode"] == "specialized"
    assert payload["operating_contract"]["primary_scope"] == "personal"
    assert payload["operating_contract"]["supports_coaching"] is True
    assert any(item["slug"] == "goal_tracking" for item in payload["capability_contracts"])
    assert any(item["slug"] == "coaching_dashboard" for item in payload["surface_contracts"])
    assert any(item["id"] == "create-first-goal" for item in payload["suggested_setup_actions"])


def test_suggest_assistant_form_blueprint_inferrs_custom_form_from_description() -> None:
    payload = suggest_assistant_form_blueprint(
        "Beni kitap okuma koçuna çevir. Her akşam hedefimi takip et ve nazik ama disiplinli ol.",
        {"assistant_forms": [], "behavior_contract": {}},
    )

    assert payload["form"]["title"] == "Kitap Okuma Koçu"
    assert "goal_tracking" in payload["form"]["capabilities"]
    assert "reading_progress" in payload["form"]["capabilities"]
    assert payload["form"]["supports_coaching"] is True
    assert payload["behavior_contract_patch"]["initiative_level"] == "high"
    assert payload["behavior_contract_patch"]["accountability_style"] == "firm"
    assert payload["confidence"] >= 0.7


def test_suggest_assistant_form_blueprint_matches_store_sales_assistant_description() -> None:
    payload = suggest_assistant_form_blueprint(
        "Beni bebek giyim mağazası için satış temsilcisine çevir. WhatsApp, Instagram ve web sitesinden gelen soruları ürün linki, stok ve varyanta bakarak cevapla.",
        {"assistant_forms": [], "behavior_contract": {}},
    )

    assert payload["form"]["title"] in {"Mağaza ve satış asistanı", "Müşteri destek asistanı"}
    assert "omnichannel_inbox" in payload["form"]["capabilities"]
    assert "catalog_grounding" in payload["form"]["capabilities"]
    assert "inventory_lookup" in payload["form"]["capabilities"]
    assert "workspace" in payload["form"]["scopes"]
    assert "catalog_panel" in payload["form"]["ui_surfaces"]
    assert payload["confidence"] >= 0.7


def test_build_assistant_inbox_keeps_whatsapp_contact_fields(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-whatsapp.db")
    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp",
        conversation_ref="conv-1",
        message_ref="msg-1",
        sender="+905551112233",
        recipient="+905554445566",
        body="Müvekkil CFO ile ilgili acil dönüş bekliyor.",
        direction="inbound",
        sent_at="2026-03-30T09:00:00+00:00",
        reply_needed=True,
        metadata={"profile_name": "Ahmet Yilmaz"},
    )

    items = build_assistant_inbox(store, "default-office")

    assert items[0]["source_type"] == "whatsapp_message"
    assert items[0]["sender"] == "+905551112233"
    assert items[0]["recipient"] == "+905554445566"
    assert items[0]["priority"] == "high"
    assert "öncelikli inceleme" in str(items[0]["importance_reason"])
    assert items[0]["memory_state"] == "operational_only"


def test_build_assistant_contact_profiles_include_operational_only_messages_in_directory(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-contact-memory-state.db")
    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp",
        conversation_ref="conv-operational",
        message_ref="msg-operational",
        sender="Operasyonel Kişi",
        recipient="Siz",
        body="Sadece operasyonel kalsın.",
        direction="inbound",
        sent_at="2026-03-30T09:00:00+00:00",
        reply_needed=True,
        metadata={"profile_name": "Operasyonel Kişi"},
    )
    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp",
        conversation_ref="conv-approved",
        message_ref="msg-approved",
        sender="Onaylı Kişi",
        recipient="Siz",
        body="Profil adayı olsun.",
        direction="inbound",
        sent_at="2026-03-30T10:00:00+00:00",
        reply_needed=True,
        metadata={"profile_name": "Onaylı Kişi", "memory_state": "candidate_memory"},
    )

    profiles = build_assistant_contact_profiles(store, "default-office", limit=20)

    display_names = {str(item.get("display_name") or "") for item in profiles}
    assert "Onaylı Kişi" in display_names
    assert "Operasyonel Kişi" in display_names


def test_build_assistant_inbox_prefers_whatsapp_contact_name_for_label(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-whatsapp-contact-label.db")
    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp",
        conversation_ref="905551112233@c.us",
        message_ref="msg-contact-label-1",
        sender="Kerem",
        recipient="Siz",
        body="Aksam ugrarim.",
        direction="inbound",
        sent_at="2026-03-30T09:00:00+00:00",
        reply_needed=True,
        metadata={"contact_name": "Babam", "chat_name": "Babam"},
    )

    items = build_assistant_inbox(store, "default-office")

    assert items[0]["source_type"] == "whatsapp_message"
    assert items[0]["contact_label"] == "Babam"


def test_build_assistant_home_deduplicates_whatsapp_follow_ups_by_conversation(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-home-whatsapp-dedupe.db")
    now = datetime.now(timezone.utc)
    recent_at = (now - timedelta(minutes=30)).isoformat()
    stale_at = (now - timedelta(days=2, hours=3)).isoformat()
    store.upsert_user_profile(
        "default-office",
        display_name="Sami",
        related_profiles=[],
        important_dates=[],
        inbox_watch_rules=[
            {
                "id": "watch-babam",
                "match_type": "person",
                "match_value": "Babam",
                "label": "Babam",
                "channels": ["whatsapp"],
            }
        ],
    )

    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp_web",
        conversation_ref="905551112233@c.us",
        message_ref="wamid-old",
        sender="Kerem",
        recipient="Siz",
        body="Eski mesaj",
        direction="inbound",
        sent_at=stale_at,
        reply_needed=True,
        metadata={"contact_name": "Babam", "chat_name": "Babam"},
    )
    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp_web",
        conversation_ref="905551112233@c.us",
        message_ref="wamid-new",
        sender="Kerem",
        recipient="Siz",
        body="Yeni mesaj",
        direction="inbound",
        sent_at=recent_at,
        reply_needed=True,
        metadata={"contact_name": "Babam", "chat_name": "Babam"},
    )

    home = build_assistant_home(store, "default-office")
    communication_items = [
        item for item in home["priority_items"] if str(item.get("kind") or "") == "communication_follow_up"
    ]

    assert home["counts"]["inbox"] == 1
    assert len(communication_items) == 1
    assert communication_items[0]["title"] == "WhatsApp: Babam için mesaj hazırla"
    assert "yaklaşık 30 dakikadır" in str(communication_items[0]["details"])
    assert "2 gündür" not in str(communication_items[0]["details"])


def test_build_assistant_inbox_includes_x_direct_messages(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-x-dm.db")
    store.upsert_x_message(
        "default-office",
        provider="x",
        conversation_ref="x-dm-1",
        message_ref="x-dm-msg-1",
        sender="@muvekkil",
        recipient="@lawcopilot",
        body="Dosya için bugün dönüş yapabilir misiniz?",
        direction="inbound",
        sent_at="2026-03-30T09:00:00+00:00",
        reply_needed=True,
        metadata={"participant_id": "x-user-2"},
    )

    items = build_assistant_inbox(store, "default-office")

    assert items[0]["source_type"] == "x_message"
    assert items[0]["contact_label"] == "@muvekkil"
    assert items[0]["participant_id"] == "x-user-2"


def test_build_assistant_inbox_includes_instagram_direct_messages(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-instagram-dm.db")
    store.upsert_instagram_message(
        "default-office",
        provider="instagram",
        conversation_ref="ig-conv-1",
        message_ref="ig-msg-1",
        sender="@muvekkil",
        recipient="@lawcopilot",
        body="Instagram'dan dönüş bekliyorum.",
        direction="inbound",
        sent_at="2026-03-30T09:05:00+00:00",
        reply_needed=True,
        metadata={"participant_id": "ig-user-2"},
    )

    items = build_assistant_inbox(store, "default-office")

    assert items[0]["source_type"] == "instagram_message"
    assert items[0]["contact_label"] == "@muvekkil"
    assert items[0]["participant_id"] == "ig-user-2"


def test_build_assistant_inbox_filters_low_signal_newsletters(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-newsletters.db")
    store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-newsletter",
        subject="Haftalık bülten ve kampanya özeti",
        participants=["no-reply@newsletter.example"],
        snippet="Bu e-postaları almak istemiyorsanız unsubscribe bağlantısına tıklayın.",
        received_at="2026-03-30T08:00:00+00:00",
        unread_count=1,
        reply_needed=True,
        metadata={
            "sender": "no-reply@newsletter.example",
            "labels": ["INBOX", "UNREAD", "CATEGORY_PROMOTIONS"],
        },
    )

    items = build_assistant_inbox(store, "default-office")

    assert items == []


def test_build_suggested_actions_routes_review_state_through_shared_gateway(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-suggested-actions.db")
    matter = store.create_matter(
        "default-office",
        "Gateway matter",
        None,
        None,
        "active",
        None,
        None,
        None,
        None,
        "tester",
    )
    store.create_task(
        "Müvekkil durum özeti hazırla",
        None,
        "high",
        "tester",
        office_id="default-office",
        matter_id=int(matter["id"]),
        recommended_by="workflow",
    )

    actions = build_suggested_actions(store, "default-office", created_by="tester")
    drafts = store.list_outbound_drafts("default-office")

    assert actions
    assert drafts
    assert drafts[0]["approval_status"] == "pending_review"
    assert actions[0]["manual_review_required"] is True
    assert "onay" in str(actions[0]["rationale"]).lower() or "önizleme" in str(actions[0]["rationale"]).lower()


def test_build_assistant_inbox_filters_promotional_noreply_mail(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-promotional.db")
    store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-openai-promo",
        subject="OpenAI ile yarın son: %60 daha iyi fiyat",
        participants=["OpenAI <noreply@tm.openai.com>"],
        snippet="Special offer. Unsubscribe to stop receiving these emails.",
        received_at=datetime.now(timezone.utc).isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={
            "sender": "OpenAI <noreply@tm.openai.com>",
            "labels": ["INBOX", "UNREAD", "CATEGORY_UPDATES"],
            "list_unsubscribe": "<mailto:unsubscribe@example.com>",
            "auto_generated": True,
        },
    )

    items = build_assistant_inbox(store, "default-office")

    assert items == []


def test_build_assistant_inbox_filters_security_notification_mail(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-security-mail.db")
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-security-alert",
        subject="Microsoft hesabınıza yeni uygulamalar bağlandı",
        participants=["Microsoft hesap ekibi <account-security-noreply@accountprotection.microsoft.com>"],
        snippet="Güvenlik uyarısı: hesabınızı korumak için bu bildirimi gönderiyoruz.",
        received_at=datetime.now(timezone.utc).isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={
            "sender": "Microsoft hesap ekibi <account-security-noreply@accountprotection.microsoft.com>",
        },
    )

    items = build_assistant_inbox(store, "default-office")

    assert items == []


def test_build_assistant_inbox_prefers_whatsapp_chat_name_for_direct_contact(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-whatsapp-chat-name.db")
    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp_web",
        conversation_ref="905551112233@c.us",
        message_ref="wamid-chat-name-1",
        sender="Kerem",
        recipient="Siz",
        body="Yoldayım",
        direction="inbound",
        sent_at=datetime.now(timezone.utc).isoformat(),
        reply_needed=True,
        metadata={"chat_name": "Babam", "contact_name": "Kerem"},
    )

    items = build_assistant_inbox(store, "default-office")

    assert len(items) == 1
    assert items[0]["contact_label"] == "Babam"
    assert "Kerem" not in str(items[0]["title"])


def test_build_assistant_inbox_filters_subscription_update_mail(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-subscription-mail.db")
    store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-subscription-alert",
        subject="ChatGPT planın yenilenmeyecek",
        participants=["OpenAI <noreply@tm.openai.com>"],
        snippet="Üyelik durumunuz değişti. Bu otomatik bir iletidir, lütfen yanıtlamayın.",
        received_at=datetime.now(timezone.utc).isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={
            "sender": "OpenAI <noreply@tm.openai.com>",
        },
    )

    items = build_assistant_inbox(store, "default-office")

    assert items == []


def test_build_assistant_inbox_keeps_human_legal_request_mail(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-client-request.db")
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-client-request",
        subject="Sözleşme taslağına bugün dönebilir misiniz?",
        participants=["Ayşe Kaya <ayse@example.com>"],
        snippet="Müvekkil tarafı onay bekliyor, lütfen bugün kısa dönüş rica ederim.",
        received_at=datetime.now(timezone.utc).isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={
            "sender": "Ayşe Kaya <ayse@example.com>",
        },
    )

    items = build_assistant_inbox(store, "default-office")

    assert len(items) == 1
    assert items[0]["source_type"] == "email_thread"
    assert items[0]["contact_label"] == "Ayşe Kaya <ayse@example.com>"
    assert "müvekkil" in str(items[0]["details"]).lower() or "yanıt" in str(items[0]["details"]).lower()


def test_build_assistant_agenda_turns_recent_email_into_action_item(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-agenda.db")
    recent_received_at = datetime.now(timezone.utc).isoformat()
    store.upsert_user_profile(
        "default-office",
        display_name="Sami",
        related_profiles=[],
        important_dates=[],
        inbox_watch_rules=[
            {
                "id": "watch-ayse",
                "match_type": "person",
                "match_value": "Ayşe Kaya",
                "label": "Ayşe Kaya",
                "channels": ["email"],
            }
        ],
    )
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-client-1",
        subject="Dosya güncellemesi bekliyorum",
        participants=["Ayşe Kaya <ayse@example.com>"],
        snippet="Bugün dönüş rica ediyorum.",
        received_at=recent_received_at,
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Ayşe Kaya"},
    )
    store.create_outbound_draft(
        "default-office",
        draft_type="petition",
        channel="email",
        to_contact="Ayşe Kaya",
        subject="Tahliye dilekçesi taslağı",
        body="Taslak içerik",
        generated_from="test",
        created_by="tester",
        approval_status="pending_review",
        delivery_status="not_sent",
    )

    agenda = build_assistant_agenda(store, "default-office")

    assert any(item["kind"] == "communication_follow_up" and "Outlook" in item["title"] for item in agenda)
    assert any(item["kind"] == "draft_review" and "Tahliye dilekçesi taslağı" in item["title"] for item in agenda)
    assert not any(item["kind"] == "reply_needed" for item in agenda)


def test_build_assistant_home_hides_unwatched_communications_from_today(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-home-unwatched-communications.db")
    recent_received_at = datetime.now(timezone.utc).isoformat()

    store.upsert_user_profile("default-office", display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-unwatched-1",
        subject="Bugün kısa dönüş rica ederim",
        participants=["Ayşe Kaya <ayse@example.com>"],
        snippet="Müsait olduğunda döner misin?",
        received_at=recent_received_at,
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Ayşe Kaya <ayse@example.com>"},
    )

    home = build_assistant_home(store, "default-office")

    assert not any(str(item.get("kind") or "") == "communication_follow_up" for item in home["priority_items"])


def test_build_assistant_home_keeps_keyword_matched_communications_in_today(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-home-keyword-communications.db")
    recent_received_at = datetime.now(timezone.utc).isoformat()

    store.upsert_user_profile(
        "default-office",
        display_name="Sami",
        related_profiles=[],
        important_dates=[],
        inbox_keyword_rules=[
            {
                "id": "keyword-checkin",
                "keyword": "check-in",
                "label": "Check-in",
                "channels": ["email"],
            }
        ],
    )
    store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-keyword-1",
        subject="Pegasus check-in başladı",
        participants=["Pegasus <noreply@pegasusairlines.com>"],
        snippet="Uçuşunuz için check-in yapabilirsiniz.",
        received_at=recent_received_at,
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Pegasus <noreply@pegasusairlines.com>"},
    )

    home = build_assistant_home(store, "default-office")

    assert any(str(item.get("kind") or "") == "communication_follow_up" for item in home["priority_items"])


def test_build_assistant_home_counts_only_actionable_communications(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-home.db")
    store.upsert_user_profile("default-office", display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-newsletter",
        subject="Haftalık bülten ve kampanya özeti",
        participants=["no-reply@newsletter.example"],
        snippet="unsubscribe bağlantısı aşağıdadır",
        received_at="2026-03-30T08:00:00+00:00",
        unread_count=1,
        reply_needed=True,
        metadata={
            "sender": "no-reply@newsletter.example",
            "labels": ["INBOX", "UNREAD", "CATEGORY_PROMOTIONS"],
        },
    )
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-client-2",
        subject="Müvekkil dönüş bekliyor",
        participants=["Ayşe Kaya <ayse@example.com>"],
        snippet="Bugün dönüş rica ediyorum.",
        received_at=datetime.now(timezone.utc).isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Ayşe Kaya"},
    )

    home = build_assistant_home(store, "default-office")

    assert home["counts"]["inbox"] == 0
    assert "belirgin bir acil iş görünmüyor" in home["today_summary"]
    assert "iletişim konusu yanıt bekliyor" not in home["today_summary"]


def test_build_assistant_home_keeps_today_summary_compact_when_multiple_surfaces_exist(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-home-compact.db")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    matter = store.create_matter(
        "default-office",
        "Tahliye takibi",
        None,
        None,
        "active",
        None,
        None,
        None,
        None,
        "tester",
    )
    matter_id = int(matter["id"])
    store.create_task(
        "Eksik dilekçeyi tamamla",
        (now - timedelta(hours=3)).isoformat(),
        "high",
        "tester",
        office_id="default-office",
        matter_id=matter_id,
        recommended_by="workflow",
    )
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-client-compact",
        subject="Bugün dönüş rica ediyorum",
        participants=["Ayşe Kaya <ayse@example.com>"],
        snippet="Kısa bir dönüş bekliyorum.",
        received_at=(now - timedelta(minutes=20)).isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Ayşe Kaya"},
    )
    store.create_outbound_draft(
        "default-office",
        draft_type="client_update",
        channel="email",
        to_contact="Ayşe Kaya",
        subject="Durum özeti",
        body="Taslak içerik",
        generated_from="test",
        created_by="tester",
        approval_status="pending_review",
        delivery_status="not_sent",
    )
    store.upsert_calendar_event(
        "default-office",
        provider="google",
        external_id="compact-calendar",
        title="Yarın planlama görüşmesi",
        starts_at=(now + timedelta(hours=22)).isoformat(),
        attendees=["Ayşe Kaya"],
        location="Kadıköy",
        needs_preparation=True,
        metadata={},
    )
    store.upsert_user_profile(
        "default-office",
        display_name="Sami",
        current_location="İstanbul / Kadıköy",
        prayer_notifications_enabled=True,
        related_profiles=[],
        important_dates=[],
    )

    home = build_assistant_home(store, "default-office")
    summary = home["today_summary"]

    assert len(home["priority_items"]) <= 4
    assert "geciken görevi" in summary
    assert "yanıt bekliyor" not in summary
    assert "Konum bağlamı" not in summary
    assert "Namaz vakti" not in summary
    assert "taslak" not in summary.lower()
    assert summary.count(".") <= 3


def test_build_assistant_home_adds_weather_preparation_for_current_location(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = Persistence(tmp_path / "assistant-home-weather.db")
    store.upsert_user_profile(
        "default-office",
        display_name="Sami",
        current_location="İzmir / Alsancak",
        weather_preference="Serin ve yağmursuz hava sever.",
    )

    monkeypatch.setattr(
        assistant_module,
        "build_weather_context",
        lambda query, *, profile_note="", limit=4: {
            "query": query,
            "search_query": query,
            "results": [
                {
                    "title": "İzmir bugün yağmurlu",
                    "url": "https://weather.example/izmir",
                    "snippet": "Sağanak yağış ve rüzgar bekleniyor.",
                    "source": "stub",
                }
            ],
            "summary": "İzmir için yağış sinyali var.",
        },
    )

    home = build_assistant_home(store, "default-office")

    weather_item = next(item for item in home["proactive_suggestions"] if item["kind"] == "weather_preparation")
    assert "İzmir" in weather_item["title"]
    assert "şemsiye" in weather_item["details"].lower()
    assert "hava hazırlığı" in home["today_summary"].lower()


def test_assistant_thread_external_context_filters_non_replyable_email_threads(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-thread-context.db")
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-security-alert",
        subject="Microsoft hesabınıza yeni uygulamalar bağlandı",
        participants=["Microsoft <account-security-noreply@accountprotection.microsoft.com>"],
        snippet="Güvenlik uyarısı: hesabınızı korumak için bu bildirimi gönderiyoruz.",
        received_at=datetime.now(timezone.utc).isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={
            "sender": "Microsoft <account-security-noreply@accountprotection.microsoft.com>",
        },
    )
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-client-request",
        subject="Dosya için bugün dönüş rica ederim",
        participants=["Ayşe Kaya <ayse@example.com>"],
        snippet="Müvekkil dosyası için kısa yanıt bekliyorum.",
        received_at=datetime.now(timezone.utc).isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={
            "sender": "Ayşe Kaya <ayse@example.com>",
        },
    )

    lines, metadata = app_module._assistant_thread_external_context_lines(
        query="mail tarafında cevap bekleyenleri özetle",
        recent_messages=[],
        source_refs=None,
        store=store,
        office_id="default-office",
    )

    assert metadata["external_email_items"] == 1
    assert any("Ayşe Kaya" in line for line in lines)
    assert not any("account-security-noreply" in line for line in lines)


def test_build_assistant_inbox_filters_old_non_important_email(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-old-email.db")
    old_received_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=10)
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-old-1",
        subject="Geçen hafta bilgi paylaşımı",
        participants=["Ayşe <ayse@example.com>"],
        snippet="Bilginize sunarız.",
        received_at=old_received_at.isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Ayşe <ayse@example.com>"},
    )

    items = build_assistant_inbox(store, "default-office")

    assert items == []


def test_build_assistant_inbox_keeps_old_important_email(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-old-important.db")
    old_received_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=10)
    store.upsert_email_thread(
        "default-office",
        provider="outlook",
        thread_ref="thread-old-important",
        subject="CEO onayı bekleniyor",
        participants=["Ayşe Kaya <ayse@example.com>"],
        snippet="CEO onayı için bugün de kontrol etmek istiyorum.",
        received_at=old_received_at.isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Ayşe Kaya", "sender_title": "CEO"},
    )

    items = build_assistant_inbox(store, "default-office")

    assert len(items) == 1
    assert items[0]["priority"] == "high"


def test_build_assistant_automation_update_adds_generic_auto_reply_rule() -> None:
    update = build_assistant_automation_update("Bayram mesajı gönderenlere otomatik yanıtla. Mesaj olsun: \"Teşekkür ederim, iyi bayramlar.\"")

    assert update is not None
    operations = update["operations"]
    assert any(item["path"] == "enabled" and item["value"] is True for item in operations if item["op"] == "set")
    add_rule = next(item for item in operations if item["op"] == "add_rule")
    rule = add_rule["rule"]
    assert rule["mode"] == "auto_reply"
    assert "bayram" in " ".join(rule["match_terms"]).lower()
    assert "iyi bayramlar" in str(rule["reply_text"]).lower()
    assert "otomasyon kuralını kaydettim" in str(update["summary"]).lower()


def test_build_assistant_automation_update_adds_generic_notify_rule_for_contact() -> None:
    update = build_assistant_automation_update(
        "Ahmet Yılmaz'dan gelen mailler çok önemli. Onları otomatik cevaplama, bana WhatsApp'tan haber ver."
    )

    assert update is not None
    operations = update["operations"]
    add_rule = next(item for item in operations if item["op"] == "add_rule")
    rule = add_rule["rule"]
    assert rule["mode"] == "notify"
    assert "Ahmet Yılmaz" in rule["targets"]
    assert "email" in rule["channels"]
    assert "whatsapp" in rule["channels"]
    assert not update["warnings"]


def test_build_assistant_automation_update_does_not_hijack_priority_question() -> None:
    update = build_assistant_automation_update("Ahmet Yılmaz'dan gelen mailler önemli mi?")

    assert update is None


def test_build_assistant_automation_update_creates_scheduled_reminder_rule() -> None:
    update = build_assistant_automation_update("1 dakika sonra suyu kapatmayı hatırlat.")

    assert update is not None
    add_rule = next(item for item in update["operations"] if item["op"] == "add_rule")
    rule = add_rule["rule"]
    assert rule["mode"] == "reminder"
    assert "suyu kapat" in str(rule["reply_text"]).lower()
    assert rule["reminder_at"]
    assert "hatırlatmasını kurdum" in str(update["summary"]).lower()


def test_build_assistant_automation_update_parses_explicit_clock_time_and_compacts_text(monkeypatch) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(2026, 4, 17, 12, 47, 0, tzinfo=timezone(timedelta(hours=3)))
            if tz is None:
                return base.replace(tzinfo=None)
            return base.astimezone(tz)

    monkeypatch.setattr(automation_intents_module, "datetime", FrozenDateTime)

    update = build_assistant_automation_update("12 48 de bana su içmeyi hatırlat")

    assert update is not None
    add_rule = next(item for item in update["operations"] if item["op"] == "add_rule")
    rule = add_rule["rule"]
    assert rule["mode"] == "reminder"
    assert rule["summary"] == "Su iç"
    assert rule["reply_text"] == "Su iç"
    assert rule["instruction"] == "12 48 de bana su içmeyi hatırlat"
    assert rule["reminder_at"].startswith("2026-04-17T12:48:00")
    assert update["summary"] == "Su iç hatırlatmasını kurdum."


def test_iter_text_deltas_preserves_newlines() -> None:
    text = "Ilk satir.\n\n- Madde 1\n- Madde 2"

    rebuilt = "".join(_iter_text_deltas(text, chunk_size=8))

    assert rebuilt == text


def test_onboarding_stays_in_interview_for_short_non_operational_reply() -> None:
    should_drive = app_module._should_drive_onboarding(
        "Tam bir asistan ol",
        prior_messages=[
            {"role": "assistant", "generated_from": "assistant_onboarding_guide", "content": "Sıradaki sorum: Benden en çok hangi rolde destek bekliyorsun?"}
        ],
        onboarding_state={"complete": False, "blocked_by_setup": False},
        memory_updates=[],
    )

    assert should_drive is True


def test_onboarding_meta_reply_uses_saved_assistant_name(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "onboarding-meta.db")
    settings = app_module.get_settings()
    store.upsert_assistant_runtime_profile(
        settings.office_id,
        assistant_name="Friday",
        role_summary="Tam kapsamlı profesyonel asistan",
        tone="Sıcak, Şakacı",
        avatar_path="",
        soul_notes="Kritik aksiyonlarda kullanıcı onayı iste.",
        tools_notes="",
        heartbeat_extra_checks=[],
    )
    store.upsert_user_profile(
        settings.office_id,
        display_name="Sami",
        favorite_color="",
        food_preferences="",
        transport_preference="",
        weather_preference="",
        travel_preferences="",
        communication_style="İletişimde kısa ve net bir üslup tercih eder.",
        assistant_notes="Öncelikli destek alanları: müvekkil takibi.",
        important_dates=[],
        related_profiles=[],
    )

    reply = app_module._maybe_compose_onboarding_meta_reply(
        "İsmin ne?",
        home={"today_summary": "", "priority_items": [], "requires_setup": []},
        onboarding_state={
        "complete": False,
        "blocked_by_setup": False,
        "current_question": {"question": "Yanıtlarımın üslubu nasıl olsun?"},
        "next_questions": [{"question": "Yanıtlarımın üslubu nasıl olsun?"}],
        },
        settings=settings,
        store=store,
    )

    assert reply is not None
    assert "Ben Friday." in str(reply["content"])
    assert "Yanıtlarımın üslubu nasıl olsun?" in str(reply["content"])


def test_compact_assistant_name_handles_long_correction_sentence() -> None:
    name = compact_assistant_profile_value(
        "assistant_name",
        "Hayır ya sen bana ismim ne diye sorduğunda tanışırken ismin Robot demiştim. Yani ismin Robot sadece ismin kısmı isim değil.",
    )

    assert name == "Robot"


def test_memory_capture_updates_assistant_name_from_correction_sentence(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-name-correction.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal(
        "Hayır, ismin Robot demiştim. Yani ismin Robot sadece ismin kısmı isim değil."
    )

    assert any(item["kind"] == "assistant_persona_signal" for item in updates)
    runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
    assert runtime_profile["assistant_name"] == "Robot"


def test_memory_capture_does_not_misread_embedded_name_keyword_inside_other_word(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-name-embedded-keyword.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal("Şakacı olma kısmını çıkarmanı istiyorum.")

    runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
    assert runtime_profile["assistant_name"] == ""
    assert not any("assistant_name" in list(item.get("fields") or []) for item in updates)


def test_memory_capture_compacts_assistant_name_without_command_suffixes(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-name-command-suffix.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal("Adın Canavar olmalı.")

    assert any(item["kind"] == "assistant_persona_signal" for item in updates)
    runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
    assert runtime_profile["assistant_name"] == "Canavar"


def test_compact_assistant_name_handles_make_name_phrase() -> None:
    name = compact_assistant_profile_value(
        "assistant_name",
        "İsmini Canavar yapalım.",
    )

    assert name == "Canavar"


def test_memory_capture_updates_display_name_from_explicit_update_command(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "user-name-update.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal("İsmimi Sami olarak güncelle.")

    assert any(item["kind"] == "profile_signal" for item in updates)
    profile = store.get_user_profile(settings.office_id)
    assert profile["display_name"] == "Sami"


def test_compact_user_name_handles_correction_sentence_without_capturing_complaint_tail() -> None:
    name = compact_user_profile_value(
        "display_name",
        "İsmimi Sami olarak değiştir yanlış girmişsin söylesene diye isim mi olur.",
    )

    assert name == "Sami"


def test_memory_capture_name_correction_keeps_display_name_and_ignores_false_related_profile(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "user-name-correction.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)
    store.upsert_user_profile(settings.office_id, display_name="Söylesene")

    updates = memory.capture_chat_signal(
        "İsmimi Sami olarak değiştir yanlış girmişsin söylesene diye isim mi olur."
    )

    assert any(item["kind"] == "profile_signal" for item in updates)
    profile = store.get_user_profile(settings.office_id)
    assert profile["display_name"] == "Sami"
    assert profile["related_profiles"] == []


def test_compact_transport_preference_prefers_first_mode_in_pairwise_preference() -> None:
    value = compact_user_profile_value("transport_preference", "Ulaşımda uçağı otobüse tercih ederim.")

    assert value == "Ulaşımda uçak tercih eder."


def test_compact_transport_preference_handles_yerine_pattern() -> None:
    value = compact_user_profile_value("transport_preference", "Ulaşımda otobüs yerine uçağı tercih ederim.")

    assert value == "Ulaşımda uçak tercih eder."


def test_memory_capture_transport_preference_uses_preferred_mode_not_compared_mode(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "transport-preference-pairwise.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal("Ulaşımda uçağı otobüse tercih ederim.")

    assert any(item["kind"] == "profile_signal" for item in updates)
    profile = store.get_user_profile(settings.office_id)
    assert profile["transport_preference"] == "Ulaşımda uçak tercih eder."


def test_travel_ticket_query_does_not_trigger_semantic_memory_update() -> None:
    query = "bana bilet al desen ne bileti alırsın istanbuldan muşa"

    assert app_module._looks_like_semantic_memory_update_query(query) is False


def test_resolve_assistant_action_plan_prefers_travel_booking_heuristic_over_runtime_guess(tmp_path: Path, monkeypatch) -> None:
    store = Persistence(tmp_path / "travel-ticket-plan.db")
    settings = app_module.get_settings()

    def _fail_runtime_plan(**_kwargs):
        raise AssertionError("runtime action planner should not run for explicit travel booking query")

    monkeypatch.setattr(app_module, "_assistant_runtime_action_plan", _fail_runtime_plan)

    plan = app_module._resolve_assistant_action_plan(
        query="bana bilet al desen ne bileti alırsın istanbuldan muşa",
        matter_id=None,
        recent_messages=[],
        settings=settings,
        store=store,
        runtime=object(),
        events=None,
        subject="test-user",
    )

    assert plan is not None
    assert plan["intent"] == "reserve_travel_ticket"
    assert plan["target_channel"] == "travel"
    assert plan["needs_clarification"] is False


def test_semantic_chat_memory_update_ignores_bad_location_patch_for_travel_query(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "semantic-travel-location-guard.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)
    store.upsert_user_profile(settings.office_id, display_name="Sami", current_location="Ankara")

    class FakeLLMService:
        enabled = True

        def complete(self, prompt: str, events=None, *, task: str, **meta):
            assert task == "assistant_chat_memory_semantic_extract"
            return {
                "text": json.dumps(
                    {
                        "user_profile": {
                            "current_location": "İstanbul",
                        },
                        "assistant_profile": {},
                        "reason": "Kullanıcı İstanbul'dan Muş'a bilet istedi.",
                    },
                    ensure_ascii=False,
                ),
                "provider": "test",
                "model": "fake-semantic",
                "runtime_mode": "test",
            }

    updates = app_module._capture_semantic_chat_memory_update(
        "bana bilet al desen ne bileti alırsın istanbuldan muşa",
        settings=settings,
        store=store,
        llm_service=FakeLLMService(),
        memory_service=memory,
    )

    assert updates == []
    profile = store.get_user_profile(settings.office_id)
    assert profile["current_location"] == "Ankara"


def test_semantic_chat_memory_update_changes_display_name_from_natural_command(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "semantic-user-name-update.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)
    store.upsert_user_profile(settings.office_id, display_name="Sami")

    class FakeLLMService:
        enabled = True

        def complete(self, prompt: str, events=None, *, task: str, **meta):
            assert task == "assistant_chat_memory_semantic_extract"
            assert "Artık bana Kenan diye seslenmeni istiyorum." in prompt
            return {
                "text": json.dumps(
                    {
                        "user_profile": {
                            "display_name": "Kenan",
                        },
                        "assistant_profile": {},
                        "reason": "Kullanıcı artık Kenan diye hitap edilmesini istiyor.",
                    },
                    ensure_ascii=False,
                ),
                "provider": "test",
                "model": "fake-semantic",
                "runtime_mode": "test",
            }

    updates = app_module._capture_semantic_chat_memory_update(
        "Artık bana Kenan diye seslenmeni istiyorum.",
        settings=settings,
        store=store,
        llm_service=FakeLLMService(),
        memory_service=memory,
    )

    assert any(item["kind"] == "profile_signal" for item in updates)
    profile = store.get_user_profile(settings.office_id)
    assert profile["display_name"] == "Kenan"


def test_semantic_chat_memory_update_prefers_explicit_name_from_query_over_bad_model_guess(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "semantic-user-name-correction.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)
    store.upsert_user_profile(settings.office_id, display_name="Söylesene")

    class FakeLLMService:
        enabled = True

        def complete(self, prompt: str, events=None, *, task: str, **meta):
            assert task == "assistant_chat_memory_semantic_extract"
            return {
                "text": json.dumps(
                    {
                        "user_profile": {
                            "display_name": "mi olur",
                        },
                        "assistant_profile": {},
                        "reason": "Kullanıcı adını düzeltiyor.",
                    },
                    ensure_ascii=False,
                ),
                "provider": "test",
                "model": "fake-semantic",
                "runtime_mode": "test",
            }

    updates = app_module._capture_semantic_chat_memory_update(
        "İsmimi Sami olarak değiştir yanlış girmişsin söylesene diye isim mi olur.",
        settings=settings,
        store=store,
        llm_service=FakeLLMService(),
        memory_service=memory,
    )

    assert any(item["kind"] == "profile_signal" for item in updates)
    profile = store.get_user_profile(settings.office_id)
    assert profile["display_name"] == "Sami"


def test_semantic_chat_memory_update_routes_assistant_style_to_runtime(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "semantic-assistant-style-update.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    class FakeLLMService:
        enabled = True

        def complete(self, prompt: str, events=None, *, task: str, **meta):
            assert task == "assistant_chat_memory_semantic_extract"
            return {
                "text": json.dumps(
                    {
                        "user_profile": {
                            "communication_style": "",
                        },
                        "assistant_profile": {
                            "tone": "Şakacı, Net",
                            "soul_notes": "Gereksiz uzatma yapma.",
                        },
                        "reason": "Kullanıcı asistanın daha şakacı ve net davranmasını istiyor.",
                    },
                    ensure_ascii=False,
                ),
                "provider": "test",
                "model": "fake-semantic",
                "runtime_mode": "test",
            }

    updates = app_module._capture_semantic_chat_memory_update(
        "Biraz daha komik ol ama net kal.",
        settings=settings,
        store=store,
        llm_service=FakeLLMService(),
        memory_service=memory,
    )

    assert any(item["kind"] == "assistant_persona_signal" for item in updates)
    runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
    profile = store.get_user_profile(settings.office_id)
    assert "Şakacı" in str(runtime_profile["tone"] or "")
    assert "Net" in str(runtime_profile["tone"] or "")
    assert "Gereksiz uzatma yapma" in str(runtime_profile["soul_notes"] or "")
    assert str(profile["communication_style"] or "") == ""


def test_memory_capture_does_not_create_related_profile_from_chat_signal_without_manual_entry(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "related-profile-update.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal("Annem çiçek sever ve sıcak yazıları daha çok sever.")

    profile = store.get_user_profile(settings.office_id)
    assert not any("related_profiles" in list(item.get("fields") or []) for item in updates)
    assert profile["related_profiles"] == []


def test_memory_capture_does_not_create_partner_profile_from_generic_spouse_word(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "related-profile-generic-spouse.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal("Eş diye birini otomatik kaydetmişsin, buna da bak.")

    profile = store.get_user_profile(settings.office_id)
    assert not updates
    assert profile["related_profiles"] == []


def test_memory_capture_does_not_create_partner_profile_from_possessive_reference_without_manual_entry(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "related-profile-possessive-spouse.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal("Eşim çikolatayı sever ve daha sıcak mesajlardan hoşlanır.")

    profile = store.get_user_profile(settings.office_id)
    assert not any("related_profiles" in list(item.get("fields") or []) for item in updates)
    assert profile["related_profiles"] == []


def test_user_profile_sanitizes_suspicious_generic_partner_profile(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "profile-sanitize-partner.db")
    store.upsert_user_profile(
        "default-office",
        display_name="Sami",
        related_profiles=[
            {
                "id": "partner",
                "name": "Eş",
                "relationship": "eş",
                "closeness": 5,
                "preferences": "",
                "notes": "ismimi Sami olarak değiştir yanlış girmişsin",
                "important_dates": [],
            }
        ],
        important_dates=[],
    )

    profile = store.get_user_profile("default-office")

    assert profile["related_profiles"] == []


def test_user_profile_sanitizes_suspicious_generic_sibling_profile_without_manual_source(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "profile-sanitize-sibling.db")
    store.upsert_user_profile(
        "default-office",
        display_name="Sami",
        related_profiles=[
            {
                "id": "sibling",
                "name": "Kardeş",
                "relationship": "kardeş",
                "closeness": 5,
                "preferences": "",
                "notes": 'hayır "Abim" diye kayıtlı biri var direkt numarası 08 le bitiyor',
                "important_dates": [],
            }
        ],
        important_dates=[],
    )

    profile = store.get_user_profile("default-office")

    assert profile["related_profiles"] == []


def test_memory_capture_updates_runtime_settings_from_explicit_commands(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-settings-update.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal(
        "Rolünü kişisel asistan olarak güncelle. Tonunu daha sıcak ve net yap. "
        "Rutinlerine önce kritik mesajları kontrol et yaz. "
        "Heartbeat kontrollerine takvim, taslaklar ve whatsapp izlemesi ekle."
    )

    assert any(item["kind"] == "assistant_persona_signal" for item in updates)
    runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
    role_summary = runtime_profile["role_summary"].lower()
    assert "çekirdek asistan" in role_summary
    assert "kişisel organizasyon asistanı" in role_summary
    assert "Sıcak" in runtime_profile["tone"]
    assert "Net" in runtime_profile["tone"]
    assert "kritik mesajları kontrol et" in runtime_profile["tools_notes"].lower()
    assert "takvim" in " ".join(runtime_profile["heartbeat_extra_checks"]).lower()
    assert "taslaklar" in " ".join(runtime_profile["heartbeat_extra_checks"]).lower()


def test_memory_capture_activates_assistant_form_and_behavior_contract(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-form-update.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal(
        "Sen artik benim yasam kocum ol. Daha proaktif davran, beni sıkı takip et ve detayli plan kur."
    )

    assert any(item["kind"] == "assistant_persona_signal" for item in updates)
    runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
    active_forms = [item for item in runtime_profile["assistant_forms"] if item.get("active")]
    assert any(str(item.get("slug") or "") == "life_coach" for item in active_forms)
    assert runtime_profile["behavior_contract"]["initiative_level"] == "high"
    assert runtime_profile["behavior_contract"]["planning_depth"] == "deep"
    assert runtime_profile["behavior_contract"]["follow_up_style"] == "persistent"


def test_memory_capture_creates_custom_coach_form_from_conversation(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-custom-form-update.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal("Sen artik benim kitap okuma kocum ol ve beni düzenli takip et.")

    assert any(item["kind"] == "assistant_persona_signal" for item in updates)
    runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
    active_forms = [item for item in runtime_profile["assistant_forms"] if item.get("active")]
    custom_form = next((item for item in active_forms if item.get("custom")), None)
    assert custom_form is not None
    assert custom_form["supports_coaching"] is True
    assert "goal_tracking" in list(custom_form.get("capabilities") or [])
    assert "progress_tracking" in list(custom_form.get("ui_surfaces") or [])


def test_memory_capture_activates_store_sales_form_from_conversation(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-commerce-form-update.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal(
        "Sen artık bebek giyim mağazam için satış temsilcisi gibi davran. WhatsApp, Instagram ve web sitemden gelen soruları stok ve ürün linkine bakarak cevapla."
    )

    assert any(item["kind"] == "assistant_persona_signal" for item in updates)
    runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
    active_forms = [item for item in runtime_profile["assistant_forms"] if item.get("active")]
    assert any(str(item.get("slug") or "") in {"commerce_ops", "customer_support"} for item in active_forms)
    commerce_form = next(item for item in active_forms if str(item.get("slug") or "") in {"commerce_ops", "customer_support"})
    assert "draft_support" in list(commerce_form.get("capabilities") or [])
    assert any(
        cap in list(commerce_form.get("capabilities") or [])
        for cap in ("omnichannel_inbox", "catalog_grounding", "inventory_lookup", "order_status_support")
    )
    assert "workspace" in list(commerce_form.get("scopes") or [])


def test_memory_update_reply_acknowledges_explicit_display_name_update(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "memory-update-reply.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal("İsmimi Sami olarak güncelle.")
    reply = app_module._compose_memory_update_reply(
        memory_updates=updates,
        settings=settings,
        store=store,
        linked_entities=[],
        source_refs=None,
    )

    assert "Bundan sonra sana Sami diye hitap edeceğim" in str(reply["content"])


def test_memory_capture_routes_profile_updates_to_settings_profile_tab(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "memory-update-settings-route.db")
    settings = app_module.get_settings()
    memory = MemoryService(store, settings.office_id)

    updates = memory.capture_chat_signal(
        "Otobüs bileti alacağın zaman Pamukkale'den al ve https://pamukkale.com.tr linkinden bak."
    )

    profile_update = next(item for item in updates if item["kind"] == "profile_signal")
    assert profile_update["route"] == "/settings?tab=profil&section=source-preferences"


def test_context_audit_reply_reports_last_saved_field(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-context-audit.db")
    settings = app_module.get_settings()
    store.upsert_assistant_runtime_profile(
        settings.office_id,
        assistant_name="Robot",
        role_summary="Kaynak dayanaklı hukuk çalışma asistanı",
        tone="Net ve profesyonel",
        avatar_path="",
        soul_notes="",
        tools_notes="",
        heartbeat_extra_checks=[],
    )

    reply = app_module._maybe_compose_context_audit_reply(
        "neyi kaydettin",
        prior_messages=[
            {"role": "user", "content": "İsmin Robot olsun."},
            {
                "role": "assistant",
                "content": 'Şunu kaydettim: asistan adı "Robot".',
                "source_context": {"memory_updates": [{"fields": ["assistant_name"]}]},
            },
        ],
        home={"today_summary": "", "priority_items": [], "requires_setup": []},
        settings=settings,
        store=store,
    )

    assert reply is not None
    assert 'asistan adım "Robot"' in str(reply["content"])


def test_context_audit_reply_summarizes_previous_misunderstood_message(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-misunderstanding.db")
    settings = app_module.get_settings()

    reply = app_module._maybe_compose_context_audit_reply(
        "yanlış anlaşılma neydi sana önceki mesajımda bahsettiğim",
        prior_messages=[
            {
                "role": "user",
                "content": "Hayır ya, ismin Robot demiştim. Yani ismin Robot sadece ismin kısmı isim değil.",
            },
            {"role": "assistant", "content": "Merhaba! Doğru okudum, ismim Robot Ismin."},
        ],
        home={"today_summary": "", "priority_items": [], "requires_setup": []},
        settings=settings,
        store=store,
    )

    assert reply is not None
    assert "asistanın adının sadece Robot olmasını" in str(reply["content"])


def test_onboarding_question_set_stays_focused(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "onboarding-focus.db")
    settings = app_module.get_settings()

    state = app_module._assistant_onboarding_state(settings, store)
    fields = [str(item.get("field") or "") for item in state["questions"]]

    assert "display_name" in fields
    assert "interaction_style" in fields
    assert "assistant_name" in fields
    assert "soul_notes" in fields
    assert "assistant_notes" in fields
    assert "communication_style" not in fields
    assert "tone" not in fields
    assert "role_summary" not in fields
    assert "related_profiles" not in fields
    assert "important_dates" not in fields


def test_assistant_onboarding_waits_for_model_selection_before_intro(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("LAWCOPILOT_DB_PATH", f"{tmp}/onboarding-provider-optional.db")
        monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", f"{tmp}/audit.log.jsonl")
        monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", f"{tmp}/events.log.jsonl")
        monkeypatch.delenv("LAWCOPILOT_PROVIDER_TYPE", raising=False)
        monkeypatch.delenv("LAWCOPILOT_PROVIDER_BASE_URL", raising=False)
        monkeypatch.delenv("LAWCOPILOT_PROVIDER_MODEL", raising=False)
        monkeypatch.delenv("LAWCOPILOT_PROVIDER_API_KEY", raising=False)
        monkeypatch.delenv("LAWCOPILOT_PROVIDER_CONFIGURED", raising=False)

        store = Persistence(Path(f"{tmp}/onboarding-provider-optional.db"))
        settings = app_module.get_settings()

        state = app_module._assistant_onboarding_state(settings, store)
        assert state["provider_ready"] is False
        assert state["blocked_by_setup"] is True
        assert "modelini seçelim" in str(state["summary"]).lower()
        assert "hitap" in str(state["next_question"]).lower()
        assert str(state["starter_prompts"][0]).startswith("Asistan modelini seç")


def test_onboarding_reply_prioritizes_setup_before_intro_when_model_missing(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("LAWCOPILOT_DB_PATH", f"{tmp}/onboarding-reply-priority.db")
        monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", f"{tmp}/audit.log.jsonl")
        monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", f"{tmp}/events.log.jsonl")
        monkeypatch.delenv("LAWCOPILOT_PROVIDER_TYPE", raising=False)
        monkeypatch.delenv("LAWCOPILOT_PROVIDER_BASE_URL", raising=False)
        monkeypatch.delenv("LAWCOPILOT_PROVIDER_MODEL", raising=False)
        monkeypatch.delenv("LAWCOPILOT_PROVIDER_API_KEY", raising=False)
        monkeypatch.delenv("LAWCOPILOT_PROVIDER_CONFIGURED", raising=False)

        store = Persistence(Path(f"{tmp}/onboarding-reply-priority.db"))
        settings = app_module.get_settings()
        onboarding_state = app_module._assistant_onboarding_state(settings, store)

        reply = app_module._compose_assistant_onboarding_reply(
            "Kısa bir tanışma yapalım.",
            home={"today_summary": "", "priority_items": [], "requires_setup": []},
            onboarding_state=onboarding_state,
            memory_updates=[],
            settings=settings,
            store=store,
        )

        assert "Tanışma kısmına geçmeden önce asistanın kullanacağı modeli seçelim." in str(reply["content"])
        assert "Gemini bağla" in str(reply["content"])
        assert "Sana nasıl hitap etmemi istersin?" not in str(reply["content"])


def test_compact_assistant_tone_detects_semantic_style_synonyms() -> None:
    assert compact_assistant_profile_value("tone", "Kısa net komik ol.") == "Şakacı, Kısa, Net"


def test_onboarding_prefers_current_question_mapping_for_display_name_answer(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace_root = Path(tmp) / "workspace"
        workspace_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("LAWCOPILOT_DB_PATH", f"{tmp}/onboarding-display-name.db")
        monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", f"{tmp}/audit.log.jsonl")
        monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", f"{tmp}/events.log.jsonl")

        store = Persistence(Path(f"{tmp}/onboarding-display-name.db"))
        store.save_workspace_root("default-office", "Kişisel Ofis", str(workspace_root), "workspace-hash")
        settings = app_module.get_settings()

        updates = app_module._capture_direct_onboarding_answer(
            "Bana Sami de",
            onboarding_state={
                "complete": False,
                "blocked_by_setup": False,
                "next_questions": [{"field": "display_name", "question": "Sana nasıl hitap etmemi istersin?"}],
            },
            prior_messages=[{"role": "assistant", "generated_from": "assistant_onboarding_guide"}],
            settings=settings,
            store=store,
        )

        assert updates
        assert updates[0]["fields"] == ["display_name"]
        profile = store.get_user_profile(settings.office_id)
        runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
        assert profile["display_name"] == "Sami"
        assert not str(runtime_profile.get("assistant_name") or "").strip()

        onboarding_after = app_module._assistant_onboarding_state(settings, store)
        current_question = onboarding_after["current_question"]
        assert current_question["field"] == "assistant_name"
        assert "hangi adla" in str(current_question["question"]).lower()


def test_onboarding_interaction_style_uses_llm_semantic_freeform_extraction(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace_root = Path(tmp) / "workspace"
        workspace_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("LAWCOPILOT_DB_PATH", f"{tmp}/onboarding-style-semantics.db")
        monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", f"{tmp}/audit.log.jsonl")
        monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", f"{tmp}/events.log.jsonl")

        store = Persistence(Path(f"{tmp}/onboarding-style-semantics.db"))
        store.save_workspace_root("default-office", "Kişisel Ofis", str(workspace_root), "workspace-hash")
        settings = app_module.get_settings()

        class FakeLLMService:
            enabled = True

            def complete(self, prompt: str, events=None, *, task: str, **meta):
                assert task == "assistant_onboarding_semantic_extract"
                assert "ön tanımlı etiket havuzuna zorlama" in prompt
                return {
                    "text": json.dumps(
                        {
                            "tone": "Kısa, net, hafif esprili",
                            "communication_style": "Gereksiz uzatmayan, doğal ve yerinde espri kullanan bir anlatım tercih eder.",
                            "assistant_notes": "",
                            "role_summary": "",
                            "soul_notes": "",
                            "new_descriptors": ["hafif esprili", "yerinde espri"],
                            "reason": "Kullanıcı kısa, net ve komik bir üslup istedi.",
                        },
                        ensure_ascii=False,
                    ),
                    "provider": "test",
                    "model": "fake-semantic",
                    "runtime_mode": "test",
                }

        updates = app_module._capture_direct_onboarding_answer(
            "Kısa net komik ol.",
            onboarding_state={
                "complete": False,
                "blocked_by_setup": False,
                "next_questions": [{"field": "interaction_style", "question": "Yanıtlarımın üslubu nasıl olsun?"}],
            },
            prior_messages=[{"role": "assistant", "generated_from": "assistant_onboarding_guide"}],
            settings=settings,
            store=store,
            llm_service=FakeLLMService(),
        )

        assert updates
        runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
        profile = store.get_user_profile(settings.office_id)
        assert runtime_profile["tone"] == "Kısa, net, hafif esprili"
        assert "Profesyonel" not in str(runtime_profile["tone"])
        assert str(profile["communication_style"] or "") == ""


def test_onboarding_interaction_style_falls_back_without_llm(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace_root = Path(tmp) / "workspace"
        workspace_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("LAWCOPILOT_DB_PATH", f"{tmp}/onboarding-style-fallback.db")
        monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", f"{tmp}/audit.log.jsonl")
        monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", f"{tmp}/events.log.jsonl")

        store = Persistence(Path(f"{tmp}/onboarding-style-fallback.db"))
        store.save_workspace_root("default-office", "Kişisel Ofis", str(workspace_root), "workspace-hash")
        settings = app_module.get_settings()

        updates = app_module._capture_direct_onboarding_answer(
            "Kısa net komik ol.",
            onboarding_state={
                "complete": False,
                "blocked_by_setup": False,
                "next_questions": [{"field": "interaction_style"}],
            },
            prior_messages=[{"role": "assistant", "generated_from": "assistant_onboarding_guide"}],
            settings=settings,
            store=store,
        )

        assert updates
        runtime_profile = store.get_assistant_runtime_profile(settings.office_id)
        profile = store.get_user_profile(settings.office_id)
        assert runtime_profile["tone"] == "Şakacı, Kısa, Net"
        assert str(profile["communication_style"] or "") == ""


def test_should_not_force_onboarding_for_normal_question_after_setup_complete() -> None:
    assert not app_module._should_drive_onboarding(
        "Şu an hangi modelle çalışıyorsun?",
        prior_messages=[],
        onboarding_state={
            "complete": False,
            "blocked_by_setup": False,
            "setup_complete": True,
            "starter_prompts": [
                "Kuruluma sohbetten devam edelim.",
                "Soruları tek tek sor.",
            ],
            "next_questions": [{"field": "assistant_name"}],
        },
        memory_updates=[],
    )


def test_status_snapshot_detects_runtime_status_question() -> None:
    assert app_module._wants_status_snapshot("Şu an hangi modelle çalışıyorsun?")


def test_status_snapshot_skips_project_summary_requests() -> None:
    assert not app_module._wants_status_snapshot("Projedeki son durumu özetle")


def test_semantic_route_plan_skips_project_summary_requests() -> None:
    assert not app_module._should_attempt_semantic_route_plan("Projedeki son durumu özetle", None)


def test_project_summary_request_does_not_mutate_assistant_behavior_contract() -> None:
    assert apply_assistant_core_update(
        "Projedeki son durumu özetle",
        {"behavior_contract": {}, "assistant_forms": [], "evolution_history": []},
    ) == {}


def test_explicit_assistant_style_request_updates_behavior_contract() -> None:
    patch = apply_assistant_core_update(
        "Bana kısa cevap ver ve bundan sonra daha proaktif ol.",
        {"behavior_contract": {}, "assistant_forms": [], "evolution_history": []},
    )
    assert patch["patch"]["behavior_contract"]["explanation_style"] == "concise"
    assert patch["patch"]["behavior_contract"]["initiative_level"] == "high"


def test_project_repo_query_detection_matches_repo_status_requests() -> None:
    assert app_module._is_project_repo_query("Projedeki son durumu özetle")
    assert app_module._is_project_repo_query("Bu repo için ne yaptık?")
    assert not app_module._is_project_repo_query("Bugünün genel durumunu göster")


def test_project_repo_kb_context_sanitizer_drops_personal_and_assistant_file_back_records() -> None:
    payload = app_module._sanitize_project_repo_kb_context(
        {
            "summary_lines": [
                "- [projects] Eski assistant reply",
                "- [concepts] Kişisel ilgi kaydı",
            ],
            "claim_summary_lines": [
                "- [kaynak gözlemi] Repo notu: Gerçek proje özeti",
                "- [kullanıcı bilgisi] Kişisel ilgi: Alakasız kişisel kayıt",
            ],
            "supporting_pages": [
                {"page_key": "projects", "path": "/tmp/projects.md"},
                {"page_key": "preferences", "path": "/tmp/preferences.md"},
            ],
            "supporting_records": [
                {
                    "record_id": "proj-1",
                    "page_key": "projects",
                    "title": "Repo notu",
                    "summary": "Gerçek proje özeti",
                    "scope": "professional",
                    "metadata": {"source_type": "manual_note"},
                },
                {
                    "record_id": "proj-2",
                    "page_key": "projects",
                    "title": "Eski assistant reply",
                    "summary": "Tekrarlayan cevap",
                    "scope": "professional",
                    "metadata": {"source_type": "assistant_file_back", "file_back_kind": "assistant_reply"},
                },
                {
                    "record_id": "pref-1",
                    "page_key": "preferences",
                    "title": "Kişisel ilgi",
                    "summary": "Alakasız kişisel kayıt",
                    "scope": "personal",
                    "metadata": {"source_type": "manual_note"},
                },
            ],
            "resolved_claims": [
                {
                    "page_key": "projects",
                    "record_id": "proj-1",
                    "display_label": "Repo notu",
                    "predicate": "project.summary",
                    "summary_line": "- [kaynak gözlemi] Repo notu: Gerçek proje özeti",
                },
                {
                    "page_key": "preferences",
                    "record_id": "pref-1",
                    "display_label": "Kişisel ilgi",
                    "predicate": "interest",
                    "summary_line": "- [kullanıcı bilgisi] Kişisel ilgi: Alakasız kişisel kayıt",
                },
            ],
            "decision_records": [
                {"title": "Karar", "summary": "Teknik yön", "scope": "professional"},
                {"title": "Kişisel not", "summary": "Alakasız", "scope": "personal"},
            ],
            "reflections": [
                {"title": "Yansıma", "summary": "Projeyle ilgili", "scope": "professional"},
                {"title": "Kişisel yansıma", "summary": "Alakasız", "scope": "personal"},
            ],
            "supporting_concepts": [{"title": "Kavram"}],
            "knowledge_articles": [{"title": "Makale"}],
            "scopes": ["professional", "personal"],
            "context_selection_reasons": ["page_intent_match", "semantic_article_match"],
            "record_type_counts": {"project": 1, "knowledge_article": 2},
        }
    )

    assert [item["title"] for item in payload["supporting_records"]] == ["Repo notu"]
    assert payload["supporting_pages"] == [{"page_key": "projects", "path": "/tmp/projects.md"}]
    assert [item["title"] for item in payload["decision_records"]] == ["Karar"]
    assert [item["title"] for item in payload["reflections"]] == ["Yansıma"]
    assert payload["supporting_concepts"] == []
    assert payload["knowledge_articles"] == []
    assert payload["scopes"] == ["professional"]
    assert payload["claim_summary_lines"] == ["- [kaynak gözlemi] Repo notu: Gerçek proje özeti"]
    assert len(payload["resolved_claims"]) == 1
    assert payload["context_selection_reasons"] == ["page_intent_match"]
    assert payload["record_type_counts"] == {"project": 1}
    assert payload["summary_lines"] == ["- [projects] Repo notu: Gerçek proje özeti", "- [decisions] Karar: Teknik yön"]


def test_knowledge_context_prompt_lines_prepend_verification_gate() -> None:
    lines = app_module._knowledge_context_prompt_lines(  # noqa: SLF001 - helper regression
        {
            "verification_gate": {
                "mode": "strict",
                "reason": "Sadece narrative dayanak bulundu.",
            },
            "summary_lines": ["- [projects] Repo notu: Gerçek proje özeti"],
        }
    )

    assert lines[0].startswith("- [doğrulama] Kesin ifade kullanma;")
    assert "Sadece narrative dayanak bulundu." in lines[0]


def test_document_summary_query_detects_broad_workspace_summary_request() -> None:
    assert app_module._is_document_summary_query("genel olarak elimizdeki her belgennin metnin bir özetini yaz")


def test_request_repair_query_resolves_to_previous_user_request() -> None:
    resolved = app_module._resolve_assistant_query(
        "benim isteğimi yapmadın",
        recent_messages=[
            {"role": "user", "content": "dosyaları özetle bi bakalım ellerimizde neler var"},
            {"role": "assistant", "content": "Belgeleri listeliyorum."},
        ],
    )

    assert resolved == "dosyaları özetle bi bakalım ellerimizde neler var"


def test_operational_document_summary_request_is_not_treated_as_support_preference() -> None:
    assert app_module._is_operational_task_request("elimizdeki belgelerin özetlerini çıkarsana")
    assert not app_module._looks_like_support_preference_answer("elimizdeki belgelerin özetlerini çıkarsana")


def test_compose_assistant_thread_reply_summarizes_workspace_documents(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-document-summary.db")
    settings = app_module.get_settings()
    events = StructuredLogger(tmp_path / "events.jsonl")
    workspace_root_path = tmp_path / "case_samples"
    workspace_root_path.mkdir()
    root = store.save_workspace_root(
        settings.office_id,
        "case_samples",
        str(workspace_root_path),
        hashlib.sha256(str(workspace_root_path).encode("utf-8")).hexdigest(),
    )
    document = store.upsert_workspace_document(
        settings.office_id,
        int(root["id"]),
        relative_path="01_kira_tahliye_ornek_dosya.md",
        display_name="01_kira_tahliye_ornek_dosya",
        extension=".md",
        content_type="text/markdown",
        size_bytes=128,
        mtime=1,
        checksum="doc-1",
        parser_status="parsed",
        indexed_status="indexed",
        document_language="tr",
        last_error=None,
    )
    store.replace_workspace_document_chunks(
        settings.office_id,
        int(root["id"]),
        int(document["id"]),
        [
            {
                "chunk_index": 0,
                "text": "Kiraya veren, iki kira dönemi boyunca ödeme yapılmadığını ve tahliye talebini anlattı.",
                "token_count": 14,
                "metadata_json": "{}",
            }
        ],
    )

    reply = app_module._compose_assistant_thread_reply(
        query="genel olarak elimizdeki her belgennin metnin bir özetini yaz",
        matter_id=None,
        source_refs=None,
        recent_messages=[
            {"role": "user", "content": "dosyaları özetle bi bakalım ellerimizde neler var"},
            {"role": "assistant", "content": "Belgeleri listeliyorum.", "generated_from": "assistant_document_inventory"},
        ],
        subject="tester",
        settings=settings,
        store=store,
        runtime=None,
        events=events,
    )

    assert reply["generated_from"] == "assistant_document_summary"
    assert "Elimizdeki belgeleri tek tek kısaca özetledim" in str(reply["content"])
    assert "01_kira_tahliye_ornek_dosya" in str(reply["content"])


def test_find_workspace_document_candidate_prefers_chunk_match_when_filename_is_generic(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-workspace-candidate.db")
    settings = app_module.get_settings()
    workspace_root_path = tmp_path / "workspace"
    workspace_root_path.mkdir()
    root = store.save_workspace_root(
        settings.office_id,
        "workspace",
        str(workspace_root_path),
        hashlib.sha256(str(workspace_root_path).encode("utf-8")).hexdigest(),
    )

    matched = store.upsert_workspace_document(
        settings.office_id,
        int(root["id"]),
        relative_path="docs/not-very-descriptive-a.md",
        display_name="not-very-descriptive-a",
        extension=".md",
        content_type="text/markdown",
        size_bytes=256,
        mtime=1,
        checksum="doc-a",
        parser_status="parsed",
        indexed_status="indexed",
        document_language="tr",
        last_error=None,
    )
    other = store.upsert_workspace_document(
        settings.office_id,
        int(root["id"]),
        relative_path="docs/not-very-descriptive-b.md",
        display_name="not-very-descriptive-b",
        extension=".md",
        content_type="text/markdown",
        size_bytes=256,
        mtime=1,
        checksum="doc-b",
        parser_status="parsed",
        indexed_status="indexed",
        document_language="tr",
        last_error=None,
    )
    store.replace_workspace_document_chunks(
        settings.office_id,
        int(root["id"]),
        int(matched["id"]),
        [
            {
                "chunk_index": 0,
                "text": "Kiracı iki kira dönemi ödeme yapmadı. Tahliye istemi ve temerrüt anlatıldı.",
                "token_count": 12,
                "metadata_json": "{}",
            }
        ],
    )
    store.replace_workspace_document_chunks(
        settings.office_id,
        int(root["id"]),
        int(other["id"]),
        [
            {
                "chunk_index": 0,
                "text": "Vekalet ücreti ve genel masraf kalemleri yer alıyor.",
                "token_count": 9,
                "metadata_json": "{}",
            }
        ],
    )

    document = app_module._find_workspace_document_candidate(
        store,
        settings.office_id,
        query="iki kira dönemi ödenmediği için tahliye dilekçesi hazırla",
        recent_messages=None,
        source_refs=None,
    )

    assert document is not None
    assert int(document["id"]) == int(matched["id"])


def test_compose_assistant_thread_reply_uses_workspace_passages_for_specific_document_question(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-workspace-reply.db")
    settings = app_module.get_settings()
    events = StructuredLogger(tmp_path / "events.jsonl")
    workspace_root_path = tmp_path / "workspace"
    workspace_root_path.mkdir()
    root = store.save_workspace_root(
        settings.office_id,
        "workspace",
        str(workspace_root_path),
        hashlib.sha256(str(workspace_root_path).encode("utf-8")).hexdigest(),
    )
    document = store.upsert_workspace_document(
        settings.office_id,
        int(root["id"]),
        relative_path="kiraya_iliskin_not.md",
        display_name="kiraya_iliskin_not",
        extension=".md",
        content_type="text/markdown",
        size_bytes=256,
        mtime=1,
        checksum="doc-1",
        parser_status="parsed",
        indexed_status="indexed",
        document_language="tr",
        last_error=None,
    )
    store.replace_workspace_document_chunks(
        settings.office_id,
        int(root["id"]),
        int(document["id"]),
        [
            {
                "chunk_index": 0,
                "text": "Kiraya veren, iki kira dönemi ödeme yapılmadığını ve tahliye talebini anlattı.",
                "token_count": 14,
                "metadata_json": "{}",
            }
        ],
    )

    reply = app_module._compose_assistant_thread_reply(
        query="iki kira dönemi ödenmeyen tahliye belgesinde ne vardı",
        matter_id=None,
        source_refs=None,
        recent_messages=[],
        subject="tester",
        settings=settings,
        store=store,
        runtime=None,
        events=events,
    )

    assert "Çalışma alanında buna en yakın dayanakları buldum" in str(reply["content"])
    assert "iki kira dönemi" in str(reply["content"])
    assert reply["source_context"]["workspace_search"]["citations"]


def test_generate_assistant_matter_draft_output_includes_similar_workspace_support_documents(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-workspace-support.db")
    settings = app_module.get_settings()
    events = StructuredLogger(tmp_path / "events.jsonl")
    workspace_root_path = tmp_path / "workspace"
    workspace_root_path.mkdir()
    root = store.save_workspace_root(
        settings.office_id,
        "workspace",
        str(workspace_root_path),
        hashlib.sha256(str(workspace_root_path).encode("utf-8")).hexdigest(),
    )
    primary = store.upsert_workspace_document(
        settings.office_id,
        int(root["id"]),
        relative_path="kira/tahliye-guncel.md",
        display_name="tahliye-guncel",
        extension=".md",
        content_type="text/markdown",
        size_bytes=256,
        mtime=2,
        checksum="doc-primary",
        parser_status="parsed",
        indexed_status="indexed",
        document_language="tr",
        last_error=None,
    )
    similar = store.upsert_workspace_document(
        settings.office_id,
        int(root["id"]),
        relative_path="kira/tahliye-ornek-eski.md",
        display_name="tahliye-ornek-eski",
        extension=".md",
        content_type="text/markdown",
        size_bytes=256,
        mtime=1,
        checksum="doc-similar",
        parser_status="parsed",
        indexed_status="indexed",
        document_language="tr",
        last_error=None,
    )
    store.replace_workspace_document_chunks(
        settings.office_id,
        int(root["id"]),
        int(primary["id"]),
        [
            {
                "chunk_index": 0,
                "text": "Kiracı iki kira dönemi ödeme yapmadı. Tahliye istemi hazırlanacak.",
                "token_count": 12,
                "metadata_json": "{}",
            }
        ],
    )
    store.replace_workspace_document_chunks(
        settings.office_id,
        int(root["id"]),
        int(similar["id"]),
        [
            {
                "chunk_index": 0,
                "text": "Önceki tahliye dilekçesinde iki kira dönemi temerrüt ve tahliye istemi anlatılmıştı.",
                "token_count": 14,
                "metadata_json": "{}",
            }
        ],
    )

    result = app_module._generate_assistant_matter_draft_output(
        query="iki kira dönemi ödenmeyen tahliye dilekçesi hazırla",
        matter_id=None,
        source_refs=None,
        recent_messages=[],
        subject="tester",
        settings=settings,
        store=store,
        runtime=None,
        events=events,
    )

    assert result is not None
    support_documents = list((((result or {}).get("draft") or {}).get("source_context") or {}).get("workspace_support_documents") or [])
    assert any("tahliye-ornek-eski" in str(item.get("label") or "") for item in support_documents)


def test_capture_direct_onboarding_answer_does_not_hijack_operational_document_request(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-onboarding-operational.db")
    settings = app_module.get_settings()

    updates = app_module._capture_direct_onboarding_answer(
        "elimizdeki belgelerin özetlerini çıkarsana",
        onboarding_state={
            "complete": False,
            "blocked_by_setup": False,
            "next_questions": [{"field": "assistant_notes"}],
        },
        prior_messages=[
            {
                "role": "assistant",
                "generated_from": "assistant_onboarding_guide",
                "content": "Sıradaki sorum: Gün içinde en çok hangi işlerde omuz vermemi istersin?",
            }
        ],
        settings=settings,
        store=store,
    )

    assert updates == []


def test_support_preference_detector_does_not_hijack_mail_status_question() -> None:
    assert app_module._is_operational_task_request("En son gelen mail nedir")
    assert not app_module._looks_like_support_preference_answer("En son gelen mail nedir")


def test_compose_assistant_thread_reply_keeps_casual_checkin_compact(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-casual.db")
    settings = app_module.get_settings()
    events = StructuredLogger(tmp_path / "events.jsonl")
    store.upsert_assistant_runtime_profile(
        settings.office_id,
        assistant_name="Friday",
        role_summary="Tam kapsamlı profesyonel asistan",
        tone="Sıcak, Net",
        avatar_path="",
        soul_notes="",
        tools_notes="",
        heartbeat_extra_checks=[],
    )

    reply = app_module._compose_assistant_thread_reply(
        query="hayat nasıl gidiyor",
        matter_id=None,
        source_refs=None,
        recent_messages=[],
        subject="tester",
        settings=settings,
        store=store,
        runtime=None,
        events=events,
    )

    content = str(reply["content"])
    assert "Ajanda:" not in content
    assert "Kurulum Notu" not in content
    assert "İstersen kurulumda eksik kalanları söyleyeyim" in content


def test_compose_assistant_thread_reply_strips_unsolicited_status_dump(tmp_path: Path) -> None:
    class FakeRuntime:
        def complete(self, prompt, events, *, task, **meta):
            return {
                "text": (
                    "İyiyim, bugün işler kontrol altında.\n\n"
                    "Durum Özeti:\n"
                    "• Ajanda: 0 madde.\n"
                    "• İletişim: 0 bekleyen mesaj.\n"
                    "• Taslaklar: 0 onay bekleyen belge.\n\n"
                    "İstersen kısa belge özetine geçebilirim?"
                ),
                "provider": "fake",
                "model": "fake-model",
            }

    store = Persistence(tmp_path / "assistant-status-trim.db")
    settings = app_module.get_settings()
    events = StructuredLogger(tmp_path / "events.jsonl")

    reply = app_module._compose_assistant_thread_reply(
        query="hayat nasıl gidiyor",
        matter_id=None,
        source_refs=None,
        recent_messages=[],
        subject="tester",
        settings=settings,
        store=store,
        runtime=FakeRuntime(),
        events=events,
    )

    content = str(reply["content"])
    assert "Durum Özeti" not in content
    assert "Ajanda:" not in content
    assert "İletişim:" not in content
    assert "İstersen kurulumda eksik kalanları söyleyeyim" in content


def test_integration_access_snapshot_detection_avoids_mail_content_queries() -> None:
    assert app_module._wants_integration_access_snapshot("Google hesabıma da bağlı mısın şu an?")
    assert app_module._wants_integration_access_snapshot("Neye erişimin var, Google ve Outlook bağlı mı?")
    assert not app_module._wants_integration_access_snapshot("En son gelen mail nedir")
    assert not app_module._wants_integration_access_snapshot("Son gelen e-postanın konusu ne?")


def test_recent_email_snapshot_detection_targets_latest_title_queries() -> None:
    assert app_module._wants_recent_email_snapshot("En son gelen 10 mailin başlıklarını yaz.")
    assert app_module._wants_recent_email_snapshot("Gmail tarafındaki son maillerin konusu ne?")
    assert app_module._wants_recent_email_snapshot("Son 15'er maili yaz.")
    assert app_module._recent_email_limit("Son 15'er maili yaz.") == 15
    assert not app_module._wants_recent_email_snapshot("Bu maile kısa bir yanıt hazırla.")


def test_compose_assistant_thread_reply_lists_recent_email_titles_from_local_mirror(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-recent-emails.db")
    settings = app_module.get_settings()
    events = StructuredLogger(tmp_path / "events.jsonl")

    store.upsert_connected_account(
        settings.office_id,
        "google",
        account_label="samiyusuf178@gmail.com",
        status="connected",
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        last_sync_at="2026-04-03T16:55:07+00:00",
        metadata={"gmail_connected": True},
    )
    store.upsert_connected_account(
        settings.office_id,
        "outlook",
        account_label="samiyusuf_1453@hotmail.com",
        status="connected",
        scopes=["Mail.Read"],
        last_sync_at="2026-04-03T16:55:05+00:00",
        metadata={"mail_connected": True},
    )
    store.upsert_email_thread(
        settings.office_id,
        provider="google",
        thread_ref="gmail-1",
        subject="Gmail son konu",
        participants=["Google Alerts <alerts@example.com>"],
        snippet="Yeni Gmail kaydı.",
        received_at="2026-04-03T16:54:00+00:00",
        unread_count=0,
        reply_needed=False,
        metadata={"sender": "Google Alerts <alerts@example.com>"},
    )
    store.upsert_email_thread(
        settings.office_id,
        provider="outlook",
        thread_ref="outlook-1",
        subject="Outlook son konu",
        participants=["Microsoft <account-security-noreply@accountprotection.microsoft.com>"],
        snippet="Yeni Outlook kaydı.",
        received_at="2026-04-03T16:55:00+00:00",
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Microsoft <account-security-noreply@accountprotection.microsoft.com>"},
    )

    reply = app_module._compose_assistant_thread_reply(
        query="En son gelen 10 mailin başlıklarını yaz hem gmail tarafında hem outlook",
        matter_id=None,
        source_refs=None,
        recent_messages=[],
        subject="tester",
        settings=settings,
        store=store,
        runtime=None,
        events=events,
    )

    content = str(reply["content"])
    assert reply["generated_from"] == "assistant_email_snapshot"
    assert "Yerel aynadaki son e-posta başlıkları şöyle:" in content
    assert "Gmail (samiyusuf178@gmail.com)" in content
    assert "Outlook (samiyusuf_1453@hotmail.com)" in content
    assert "Gmail son konu" in content
    assert "Outlook son konu" in content


def test_social_monitoring_query_ignores_profile_correction_text() -> None:
    assert not is_social_monitoring_query(
        "ismin Robot sadece. yanlış kaydetmişsin profilini, bu çok saçma bir yorum."
    )


def test_memory_update_reply_acknowledges_assistant_name_correction(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "assistant-memory-reply.db")
    settings = app_module.get_settings()
    store.upsert_assistant_runtime_profile(
        settings.office_id,
        assistant_name="LawCopilot",
        role_summary="",
        tone="",
        avatar_path="",
        soul_notes="",
        tools_notes="",
        heartbeat_extra_checks=[],
    )

    updates = MemoryService(store, settings.office_id).capture_chat_signal("ismin Robot sadece")
    reply = app_module._compose_memory_update_reply(
        memory_updates=updates,
        settings=settings,
        store=store,
        linked_entities=[],
        source_refs=[],
    )

    assert updates
    assert "Asistan adı artık Robot." in str(reply["content"])


def test_thread_response_extensions_expose_automation_changes_as_memory_updates() -> None:
    extensions = build_thread_response_extensions(
        reply={
            "tool_suggestions": [],
            "draft_preview": None,
            "source_context": {
                "automation_updates": [
                    {
                        "summary": "Otomasyon kuralı kaydedildi.",
                        "warnings": ["Kanal seçimini istersen daraltabilirsin."],
                        "operations": [
                            {"op": "set", "path": "desktopNotifications", "value": True},
                            {"op": "add_rule", "rule": {"summary": "Yeni kural"}},
                        ],
                    }
                ]
            },
        },
        generated_from="assistant_automation_controller",
        memory_updates=[],
    )

    updates = extensions["memory_updates"]
    assert updates
    assert updates[0]["kind"] == "automation_signal"
    assert updates[0]["route"] == "/settings?tab=system&section=automation-panel"
    assert updates[0]["warnings"] == ["Kanal seçimini istersen daraltabilirsin."]
