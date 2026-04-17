from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from lawcopilot_api.assistant import (
    build_assistant_contact_profiles,
    build_assistant_home,
    build_assistant_relationship_profiles,
)
from lawcopilot_api.persistence import Persistence


def _store(tmp_path: Path) -> Persistence:
    return Persistence(tmp_path / "contacts.db")


def test_build_assistant_relationship_profiles_selects_only_important_people(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="anne-chat",
        message_ref="wa-anne-1",
        sender="Annem",
        recipient="Sami",
        body="Çikolatayı çok severim, gelirken küçük bir kutu alırsan çok sevinirim.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={},
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="anne-chat",
        message_ref="wa-anne-2",
        sender="Sami",
        recipient="Annem",
        body="Anne, akşam uğrayacağım.",
        direction="outbound",
        sent_at=(now - timedelta(hours=2)).isoformat(),
        reply_needed=False,
        metadata={},
    )
    store.upsert_email_thread(
        office_id,
        provider="google",
        thread_ref="newsletter-1",
        subject="Büyük indirim kampanyası",
        participants=["Kampanya Bülteni <newsletter@example.com>"],
        snippet="Bugünün fırsatları burada.",
        received_at=(now - timedelta(hours=1)).isoformat(),
        unread_count=1,
        reply_needed=False,
        metadata={"sender": "Kampanya Bülteni <newsletter@example.com>", "auto_generated": True},
    )

    directory = build_assistant_contact_profiles(store, office_id)
    relationship_profiles = build_assistant_relationship_profiles(store, office_id)

    assert any(item["display_name"] == "Kampanya Bülteni" for item in directory)
    assert not any(item["display_name"] == "Kampanya Bülteni" for item in relationship_profiles)

    mother = next(item for item in relationship_profiles if item["display_name"] == "Annem")
    assert mother["relationship_hint"] == "Anne"
    assert mother["closeness"] == 5
    assert "Çikolatayı seviyor." in mother["preference_signals"]
    assert any("çikolata" in gift.lower() for gift in mother["gift_ideas"])


def test_build_assistant_relationship_profiles_do_not_treat_transactional_updates_as_preferences(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="baba-chat",
        message_ref="wa-baba-1",
        sender="Babam",
        recipient="Sami",
        body="Kığılı'dan alışveriş yaptım, kargom gelecek.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={},
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="baba-chat",
        message_ref="wa-baba-2",
        sender="Sami",
        recipient="Babam",
        body="Tamam baba, haber ver.",
        direction="outbound",
        sent_at=(now - timedelta(minutes=5)).isoformat(),
        reply_needed=False,
        metadata={},
    )

    relationship_profiles = build_assistant_relationship_profiles(store, office_id, limit=20)

    father = next(item for item in relationship_profiles if item["display_name"] == "Babam")
    assert father["preference_signals"] == []
    assert "kığılı" not in str(father.get("summary") or "").lower()
    assert "kigili" not in str(father.get("summary") or "").lower()


def test_build_assistant_contact_profiles_surface_related_profile_closeness(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        related_profiles=[
            {
                "id": "mother",
                "name": "Annem",
                "relationship": "Anne",
                "closeness": 5,
                "preferences": "Çiçek sever.",
                "notes": "",
                "important_dates": [],
            }
        ],
        important_dates=[],
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="anne-chat",
        message_ref="wa-anne-1",
        sender="Annem",
        recipient="Sami",
        body="Yarın uğrarsan sevinirim.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={"memory_state": "candidate_memory"},
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="anne-chat",
        message_ref="wa-anne-2",
        sender="Sami",
        recipient="Annem",
        body="Tamam anne, uğrayacağım.",
        direction="outbound",
        sent_at=(now - timedelta(hours=1)).isoformat(),
        reply_needed=False,
        metadata={"memory_state": "candidate_memory"},
    )

    directory = build_assistant_contact_profiles(store, office_id)

    mother = next(item for item in directory if item["related_profile_id"] == "mother")
    assert mother["related_profile_id"] == "mother"
    assert mother["closeness"] == 5


def test_build_assistant_home_includes_contact_preparation_suggestion(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="anne-chat",
        message_ref="wa-anne-1",
        sender="Annem",
        recipient="Sami",
        body="Çikolatayı çok severim, kahve de alabiliriz.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={},
    )
    store.upsert_calendar_event(
        office_id,
        provider="google",
        external_id="anne-meeting",
        title="Annemle kahve",
        starts_at=(now + timedelta(days=1)).isoformat(),
        attendees=["Annem"],
        location="Kadıköy",
        needs_preparation=True,
        metadata={"notes": "Ailece görüşme"},
    )

    home = build_assistant_home(store, office_id)

    assert home["relationship_profiles"]
    suggestion = next(item for item in home["proactive_suggestions"] if item["kind"] == "contact_preparation")
    assert "Annem" in suggestion["title"]
    assert "çikolata" in suggestion["details"].lower()


def test_build_assistant_contact_profiles_include_multichannel_inference_and_recent_preview(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_email_thread(
        office_id,
        provider="google",
        thread_ref="anne-mail-1",
        subject="Yarın uğrayabilir misin?",
        participants=["Annem <annem@example.com>"],
        snippet="Çiçek de alırsan çok sevinirim.",
        received_at=(now - timedelta(hours=3)).isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Annem <annem@example.com>"},
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="anne-chat",
        message_ref="wa-anne-3",
        sender="Annem",
        recipient="Sami",
        body="Çikolatayı çok severim, gelirken unutma.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={"memory_state": "candidate_memory"},
    )

    directory = build_assistant_contact_profiles(store, office_id)

    mother = next(item for item in directory if item["display_name"] == "Annem")
    assert set(mother["channels"]) == {"email", "whatsapp"}
    assert "WhatsApp" in str(mother.get("channel_summary") or "")
    assert "E-posta" in str(mother.get("channel_summary") or "")
    assert "Çikolatayı seviyor." in list(mother.get("preference_signals") or [])
    assert any("çikolata" in item.lower() for item in list(mother.get("gift_ideas") or []))
    assert "Çikolatayı çok severim" in str(mother.get("last_inbound_preview") or "")
    assert any("düzenli temas" in item.lower() for item in list(mother.get("inference_signals") or []))
    assert "En çok görülen kanallar" in str(mother.get("persona_detail") or "")
    assert "Çikolatayı seviyor." in str(mother.get("persona_detail") or "")
    assert "Son dikkat çeken örnek" in str(mother.get("persona_detail") or "")


def test_build_assistant_contact_profiles_generate_richer_behavioral_detail_from_messages(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    samples = [
        ("Ablam", "Sami", "Yarın saat 7 gibi çıkar mısın?"),
        ("Sami", "Ablam", "Çıkarım, konumu da atarım."),
        ("Ablam", "Sami", "Şu linke de bak: https://example.com/rota"),
        ("Ablam", "Sami", "Tamam mı, anneme de haber verelim mi?"),
        ("Ablam", "Sami", "😄"),
    ]
    for index, (sender, recipient, body) in enumerate(samples):
        store.upsert_whatsapp_message(
            office_id,
            provider="whatsapp",
            conversation_ref="ablam-chat",
            message_ref=f"wa-ablam-{index}",
            sender=sender,
            recipient=recipient,
            body=body,
            direction="outbound" if sender == "Sami" else "inbound",
            sent_at=(now - timedelta(minutes=index * 10)).isoformat(),
            reply_needed=False,
            metadata={},
        )

    directory = build_assistant_contact_profiles(store, office_id)

    sister = next(item for item in directory if item["display_name"] == "Ablam")
    persona_detail = str(sister.get("persona_detail") or "")
    inference_signals = list(sister.get("inference_signals") or [])

    assert "Açıklama 5 mesaj örneğine dayanıyor." in persona_detail
    assert "Mesajların çoğu kısa ve hızlı ilerliyor" in persona_detail
    assert "Planlama, saat, buluşma ve günlük koordinasyon dili baskın görünüyor." in persona_detail
    assert "Link ve içerik paylaşımı tekrarlıyor" in persona_detail
    assert any("kısa ve hızlı" in signal.lower() for signal in inference_signals)
    assert any("link ve içerik paylaşımı" in signal.lower() for signal in inference_signals)


def test_build_assistant_contact_profiles_apply_manual_description_override(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="baran-chat",
        message_ref="wa-baran-1",
        sender="Baran",
        recipient="Sami",
        body="Akşam toplantı notlarını konuşalım.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={},
    )

    first_directory = build_assistant_contact_profiles(store, office_id)
    baran = next(item for item in first_directory if item["display_name"] == "Baran")

    store.upsert_user_profile(
        office_id,
        display_name="Sami",
        related_profiles=[],
        important_dates=[],
        contact_profile_overrides=[
            {
                "contact_id": baran["id"],
                "description": "Toplantı ve iş takibi için sık konuşulan yakın iletişim kişisi.",
                "updated_at": now.isoformat(),
            }
        ],
    )

    directory = build_assistant_contact_profiles(store, office_id)
    baran = next(item for item in directory if item["display_name"] == "Baran")
    assert baran["persona_detail"] == "Toplantı ve iş takibi için sık konuşulan yakın iletişim kişisi."
    assert baran["persona_detail_source"] == "manual"


def test_build_assistant_home_exposes_full_contact_directory_and_channel_counts(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    for index in range(6):
        store.upsert_whatsapp_message(
            office_id,
            provider="whatsapp",
            conversation_ref=f"contact-{index}",
            message_ref=f"wa-{index}",
            sender=f"Kişi {index}",
            recipient="Sami",
            body="Merhaba",
            direction="inbound",
            sent_at=(now - timedelta(minutes=index)).isoformat(),
            reply_needed=False,
            metadata={"memory_state": "candidate_memory"},
        )
    store.upsert_email_thread(
        office_id,
        provider="google",
        thread_ref="mail-1",
        subject="Kontrol",
        participants=["Müvekkil <musteri@example.com>"],
        snippet="Dosya hazır.",
        received_at=(now - timedelta(hours=2)).isoformat(),
        unread_count=1,
        reply_needed=True,
        metadata={"sender": "Müvekkil <musteri@example.com>"},
    )

    home = build_assistant_home(store, office_id)

    assert len(home["contact_directory"]) == 7
    assert home["contact_directory_summary"]["channels"]["whatsapp"] == 6
    assert home["contact_directory_summary"]["channels"]["email"] == 1


def test_build_assistant_contact_profiles_merge_whatsapp_group_and_direct_under_saved_label(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="905551234567@c.us",
        message_ref="wa-baba-direct",
        sender="Kerem",
        recipient="Sami",
        body="Akşam konuşalım.",
        direction="inbound",
        sent_at=(now - timedelta(minutes=5)).isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Babam",
            "contact_name": "Kerem",
            "from": "905551234567@c.us",
            "to": "sami@c.us",
            "memory_state": "candidate_memory",
        },
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="canim-ailem@g.us",
        message_ref="wa-baba-group",
        sender="Kerem",
        recipient="Sami",
        body="Pazar kahvaltısı bizde.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Canım Ailem",
            "group_name": "Canım Ailem",
            "is_group": True,
            "contact_name": "Kerem",
            "author": "905551234567@c.us",
            "participant": "905551234567@c.us",
            "from": "canim-ailem@g.us",
            "to": "sami@c.us",
            "memory_state": "candidate_memory",
        },
    )

    directory = build_assistant_contact_profiles(store, office_id)

    father = next(item for item in directory if item["display_name"] == "Babam")
    assert father["relationship_hint"] == "Baba"
    assert "Canım Ailem" in list(father.get("group_contexts") or [])
    assert father["source_count"] == 2
    assert father["phone_numbers"] == ["905551234567"]
    assert not any(item["display_name"] == "Kerem" and item["kind"] == "person" for item in directory)


def test_build_assistant_contact_profiles_keep_same_raw_name_separate_by_phone_identity(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="905551234567@c.us",
        message_ref="wa-baba-direct",
        sender="Kerem",
        recipient="Sami",
        body="Akşam ararım.",
        direction="inbound",
        sent_at=(now - timedelta(minutes=4)).isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Babam",
            "contact_name": "Kerem",
            "from": "905551234567@c.us",
            "to": "sami@c.us",
        },
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="905551998877@c.us",
        message_ref="wa-kerem-abi-direct",
        sender="Kerem",
        recipient="Sami",
        body="Dosyayı birazdan yolluyorum.",
        direction="inbound",
        sent_at=(now - timedelta(minutes=2)).isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Kerem Abi",
            "contact_name": "Kerem",
            "from": "905551998877@c.us",
            "to": "sami@c.us",
        },
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="aile-grubu@g.us",
        message_ref="wa-baba-group",
        sender="Kerem",
        recipient="Sami",
        body="Hafta sonu buluşalım.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Aile Grubu",
            "group_name": "Aile Grubu",
            "is_group": True,
            "contact_name": "Babam",
            "author": "905551234567@c.us",
            "participant": "905551234567@c.us",
            "from": "aile-grubu@g.us",
            "to": "sami@c.us",
        },
    )

    directory = build_assistant_contact_profiles(store, office_id)

    father = next(item for item in directory if item["display_name"] == "Babam")
    friend = next(item for item in directory if item["display_name"] == "Kerem Abi")

    assert father["phone_numbers"] == ["905551234567"]
    assert friend["phone_numbers"] == ["905551998877"]
    assert "Aile Grubu" in list(father.get("group_contexts") or [])
    assert "Aile Grubu" not in list(friend.get("group_contexts") or [])
    assert father["id"] != friend["id"]


def test_build_assistant_contact_profiles_include_whatsapp_contact_snapshots_without_messages(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_contact_snapshot(
        office_id,
        provider="whatsapp_web",
        conversation_ref="905422214908@c.us",
        display_name="Abim",
        profile_name="Kerem",
        phone_number="905422214908",
        is_group=False,
        last_seen_at=now.isoformat(),
        metadata={"chat_name": "Abim", "contact_name": "Abim", "profile_name": "Kerem"},
    )

    directory = build_assistant_contact_profiles(store, office_id)

    brother = next(item for item in directory if item["display_name"] == "Abim")
    assert brother["phone_numbers"] == ["905422214908"]
    assert "whatsapp" in brother["channels"]


def test_build_assistant_contact_profiles_do_not_merge_telegram_contact_into_whatsapp_saved_label_by_name_only(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_contact_snapshot(
        office_id,
        provider="whatsapp_web",
        conversation_ref="905422214908@c.us",
        display_name="Abim",
        profile_name="Kerem",
        phone_number="905422214908",
        is_group=False,
        last_seen_at=now.isoformat(),
        metadata={"chat_name": "Abim", "contact_name": "Abim", "profile_name": "Kerem"},
    )
    store.upsert_telegram_message(
        office_id,
        provider="telegram_web",
        conversation_ref="chat:telegram-peer-1",
        message_ref="tg-abim-unrelated",
        sender="Abim",
        recipient="Sami",
        body="Linki gördün mü?",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={"chat_name": "Abim", "display_name": "Abim", "username": ""},
    )

    directory = build_assistant_contact_profiles(store, office_id)

    abim_entries = [item for item in directory if item["display_name"] == "Abim" and item["kind"] == "person"]
    assert len(abim_entries) == 2
    whatsapp_entry = next(item for item in abim_entries if item["phone_numbers"] == ["905422214908"])
    telegram_entry = next(item for item in abim_entries if item["channels"] == ["telegram"])
    assert whatsapp_entry["channels"] == ["whatsapp"]
    assert telegram_entry["phone_numbers"] == []
    assert telegram_entry["relationship_hint"] == "İletişim kişisi"


def test_build_assistant_contact_profiles_merge_telegram_contact_into_whatsapp_when_phone_matches(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_contact_snapshot(
        office_id,
        provider="whatsapp_web",
        conversation_ref="905422214908@c.us",
        display_name="Abim",
        profile_name="Kerem",
        phone_number="905422214908",
        is_group=False,
        last_seen_at=(now - timedelta(minutes=1)).isoformat(),
        metadata={"chat_name": "Abim", "contact_name": "Abim", "profile_name": "Kerem"},
    )
    store.upsert_telegram_message(
        office_id,
        provider="telegram_web",
        conversation_ref="chat:telegram-peer-1",
        message_ref="tg-abim-same-phone",
        sender="Abim",
        recipient="Sami",
        body="Akşam arayayım.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Abim",
            "display_name": "Abim",
            "phone_number": "+90 542 221 49 08",
        },
    )

    directory = build_assistant_contact_profiles(store, office_id)

    abim_entries = [item for item in directory if item["display_name"] == "Abim" and item["kind"] == "person"]
    assert len(abim_entries) == 1
    brother = abim_entries[0]
    assert set(brother["channels"]) == {"whatsapp", "telegram"}
    assert brother["phone_numbers"] == ["905422214908"]


def test_build_assistant_contact_profiles_do_not_merge_group_member_into_saved_contact_by_profile_name_only(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_contact_snapshot(
        office_id,
        provider="whatsapp_web",
        conversation_ref="905422214908@c.us",
        display_name="Abim",
        profile_name="Kerem",
        phone_number="905422214908",
        is_group=False,
        last_seen_at=(now - timedelta(minutes=1)).isoformat(),
        metadata={"chat_name": "Abim", "contact_name": "Abim", "profile_name": "Kerem"},
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp_web",
        conversation_ref="905422214908@c.us",
        message_ref="wa-abim-direct",
        sender="Kerem",
        recipient="Sami",
        body="Akşam konuşuruz.",
        direction="inbound",
        sent_at=(now - timedelta(minutes=1)).isoformat(),
        reply_needed=False,
        metadata={"chat_name": "Abim", "contact_name": "Abim", "profile_name": "Kerem"},
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp_web",
        conversation_ref="aile-grubu@g.us",
        message_ref="wa-kerem-group",
        sender="Kerem",
        recipient="Sami",
        body="Toplantı birazdan başlıyor.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Aile Grubu",
            "group_name": "Aile Grubu",
            "is_group": True,
            "contact_name": "Kerem",
            "profile_name": "Kerem",
            "author": "270999702483145@lid",
            "participant": "270999702483145@lid",
            "from": "aile-grubu@g.us",
            "to": "905527502749@c.us",
        },
    )

    directory = build_assistant_contact_profiles(store, office_id)

    brother = next(item for item in directory if item["display_name"] == "Abim")
    group_member = next(
        item
        for item in directory
        if item["display_name"] == "Kerem" and "Aile Grubu" in list(item.get("group_contexts") or [])
    )

    assert brother["phone_numbers"] == ["905422214908"]
    assert "Aile Grubu" not in list(brother.get("group_contexts") or [])
    assert group_member["phone_numbers"] == []


def test_build_assistant_contact_profiles_merge_group_member_into_saved_contact_by_unique_saved_label(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_contact_snapshot(
        office_id,
        provider="whatsapp_web",
        conversation_ref="905422214908@c.us",
        display_name="Abim",
        profile_name="Kerem",
        phone_number="905422214908",
        is_group=False,
        last_seen_at=(now - timedelta(minutes=2)).isoformat(),
        metadata={"chat_name": "Abim", "contact_name": "Abim", "profile_name": "Kerem"},
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp_web",
        conversation_ref="aile-grubu@g.us",
        message_ref="wa-abim-group",
        sender="Kerem",
        recipient="Sami",
        body="Yarın sabah ararım.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Aile Grubu",
            "group_name": "Aile Grubu",
            "is_group": True,
            "contact_name": "Abim",
            "profile_name": "Kerem",
            "author": "270999702483145@lid",
            "participant": "270999702483145@lid",
            "from": "aile-grubu@g.us",
            "to": "905527502749@c.us",
        },
    )

    directory = build_assistant_contact_profiles(store, office_id)

    brother = next(item for item in directory if item["display_name"] == "Abim")
    assert brother["phone_numbers"] == ["905422214908"]
    assert "Aile Grubu" in list(brother.get("group_contexts") or [])
    assert not any(
        item["display_name"] == "Kerem" and "Aile Grubu" in list(item.get("group_contexts") or [])
        for item in directory
    )


def test_build_assistant_contact_profiles_snapshot_refreshes_saved_whatsapp_label(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="905422214908@c.us",
        message_ref="wa-old-label",
        sender="Kerem Abi",
        recipient="Sami",
        body="Akşam konuşuruz.",
        direction="inbound",
        sent_at=(now - timedelta(minutes=10)).isoformat(),
        reply_needed=False,
        metadata={"chat_name": "Kerem Abi", "contact_name": "Kerem Abi", "profile_name": "Kerem"},
    )
    store.upsert_whatsapp_contact_snapshot(
        office_id,
        provider="whatsapp_web",
        conversation_ref="905422214908@c.us",
        display_name="Abim",
        profile_name="Kerem",
        phone_number="905422214908",
        is_group=False,
        last_seen_at=now.isoformat(),
        metadata={"chat_name": "Abim", "contact_name": "Abim", "profile_name": "Kerem"},
    )

    directory = build_assistant_contact_profiles(store, office_id)

    brother = next(item for item in directory if item["phone_numbers"] == ["905422214908"])
    assert brother["display_name"] == "Abim"


def test_build_assistant_contact_profiles_do_not_surface_group_ids_as_phone_numbers(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="905455997865-1599387639@g.us",
        message_ref="wa-baba-group-only",
        sender="Kerem",
        recipient="Sami",
        body="Akşam görüşürüz.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Canım Ailem",
            "group_name": "Canım Ailem",
            "is_group": True,
            "contact_name": "Babam",
            "profile_name": "Kerem",
            "author": "67027360346156@lid",
            "participant": "67027360346156@lid",
            "from": "905455997865-1599387639@g.us",
            "to": "905527502749@c.us",
        },
    )

    directory = build_assistant_contact_profiles(store, office_id)

    father = next(item for item in directory if item["display_name"] == "Babam")
    assert father["phone_numbers"] == []


def test_build_assistant_contact_profiles_prefer_direct_c_us_number_over_bad_snapshot_phone(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_contact_snapshot(
        office_id,
        provider="whatsapp_web",
        conversation_ref="38765657301@c.us",
        display_name="Bosna Arkadaş",
        profile_name="Bosna Arkadaş",
        phone_number="188609311305791",
        is_group=False,
        last_seen_at=now.isoformat(),
        metadata={"chat_name": "Bosna Arkadaş", "contact_name": "Bosna Arkadaş"},
    )

    directory = build_assistant_contact_profiles(store, office_id)

    friend = next(item for item in directory if item["display_name"] == "Bosna Arkadaş")
    assert friend["phone_numbers"] == ["38765657301"]


def test_build_assistant_contact_profiles_prefer_real_turkish_number_over_internal_snapshot_id(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_contact_snapshot(
        office_id,
        provider="whatsapp_web",
        conversation_ref="905345801655@c.us",
        display_name="Türkiye Arkadaş",
        profile_name="Türkiye Arkadaş",
        phone_number="134561644208255",
        is_group=False,
        last_seen_at=now.isoformat(),
        metadata={"chat_name": "Türkiye Arkadaş", "contact_name": "Türkiye Arkadaş"},
    )

    directory = build_assistant_contact_profiles(store, office_id)

    friend = next(item for item in directory if item["display_name"] == "Türkiye Arkadaş")
    assert friend["phone_numbers"] == ["905345801655"]


def test_build_assistant_contact_profiles_do_not_surface_plain_internal_numeric_ids_as_phone_numbers(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_contact_snapshot(
        office_id,
        provider="whatsapp_web",
        conversation_ref="134561644208255@lid",
        display_name="Sedat",
        profile_name="Sedat",
        phone_number="134561644208255",
        is_group=False,
        last_seen_at=now.isoformat(),
        metadata={"chat_name": "Sedat", "contact_name": "Sedat"},
    )

    directory = build_assistant_contact_profiles(store, office_id)

    friend = next(item for item in directory if item["display_name"] == "Sedat")
    assert friend["phone_numbers"] == []


def test_build_assistant_contact_profiles_do_not_turn_regular_contact_into_client_from_message_body(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="abla-chat",
        message_ref="wa-abla-1",
        sender="Esra",
        recipient="Sami",
        body="Bugün müvekkil ile görüştüm, sonra seni ararım.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Esra",
            "contact_name": "Esra",
            "from": "905551111111@c.us",
            "to": "sami@c.us",
            "memory_state": "candidate_memory",
        },
    )

    directory = build_assistant_contact_profiles(store, office_id)

    sister = next(item for item in directory if item["display_name"] == "Esra")
    assert sister["relationship_hint"] == "İletişim kişisi"
    assert "müvekkil" not in str(sister["persona_summary"] or "").lower()


def test_build_assistant_contact_profiles_infer_airline_account_from_email_content(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_email_thread(
        office_id,
        provider="google",
        thread_ref="pegasus-1",
        subject="Pegasus uçuşunuz için online check-in başladı",
        participants=["Pegasus <noreply@pegasusairlines.com>"],
        snippet="PNR kodunuz ile check-in yapabilir, bagaj detaylarını görebilirsiniz.",
        received_at=now.isoformat(),
        unread_count=1,
        reply_needed=False,
        metadata={"sender": "Pegasus <noreply@pegasusairlines.com>"},
    )

    directory = build_assistant_contact_profiles(store, office_id)

    pegasus = next(item for item in directory if "pegasus" in str(item["display_name"]).lower())
    assert pegasus["relationship_hint"] == "Seyahat / hava yolu hesabı"
    assert "uçuş" in str(pegasus["persona_summary"] or "").lower()


def test_build_assistant_contact_profiles_infer_booking_account_from_email_content(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_email_thread(
        office_id,
        provider="google",
        thread_ref="booking-1",
        subject="Booking.com - doğrulama kodunuz",
        participants=['"Booking.com" <noreply@booking.com>'],
        snippet="Rezervasyon hesabınıza güvenli şekilde giriş yapmak için bu kodu kullanın.",
        received_at=now.isoformat(),
        unread_count=1,
        reply_needed=False,
        metadata={"sender": '"Booking.com" <noreply@booking.com>'},
    )

    directory = build_assistant_contact_profiles(store, office_id)

    booking = next(item for item in directory if "booking" in str(item["display_name"]).lower())
    assert booking["relationship_hint"] == "Konaklama / rezervasyon hesabı"
    assert "rezervasyon" in str(booking["persona_summary"] or "").lower()
    assert "kariyer" not in str(booking["persona_summary"] or "").lower()
    assert not any("bülten" in str(signal).lower() for signal in list(booking.get("inference_signals") or []))
    assert not any("sık konuşuyorsunuz" in str(signal).lower() for signal in list(booking.get("inference_signals") or []))


def test_build_assistant_contact_profiles_do_not_merge_outbound_self_identifier_into_other_contacts(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="905369112793@c.us",
        message_ref="wa-abla-outbound",
        sender="Sami",
        recipient="Ablam",
        body="Abla müsaitsen konuşalım.",
        direction="outbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Ablam",
            "contact_name": "Ablam",
            "author": "905527502749:61@c.us",
            "participant": "905527502749:61@c.us",
            "from": "905527502749@c.us",
            "to": "905369112793@c.us",
            "is_group": False,
        },
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="gulgul@g.us",
        message_ref="wa-group-other",
        sender="Baran",
        recipient="Sami",
        body="Akşam gelir misin?",
        direction="inbound",
        sent_at=(now + timedelta(minutes=1)).isoformat(),
        reply_needed=False,
        metadata={
            "chat_name": "Gül ve Gülistan tayfa",
            "group_name": "Gül ve Gülistan tayfa",
            "contact_name": "Baran",
            "author": "270999702483145@lid",
            "participant": "270999702483145@lid",
            "from": "gulgul@g.us",
            "to": "905527502749@c.us",
            "is_group": True,
        },
    )

    directory = build_assistant_contact_profiles(store, office_id)

    sister = next(item for item in directory if item["display_name"] == "Ablam")
    assert "Gül ve Gülistan tayfa" not in list(sister.get("group_contexts") or [])
    assert sister["source_count"] == 1
    assert sister["phone_numbers"] == ["905369112793"]


def test_build_assistant_contact_profiles_infer_topic_for_close_sibling_from_messages(tmp_path):
    store = _store(tmp_path)
    office_id = "default-office"
    now = datetime.now(timezone.utc)

    store.upsert_user_profile(office_id, display_name="Sami", related_profiles=[], important_dates=[])
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="905369112793@c.us",
        message_ref="wa-abla-1",
        sender="Hatice Kübra",
        recipient="Sami",
        body="Balkan turunda hız limitine dikkat edin, valize de kalın bir şey koy.",
        direction="inbound",
        sent_at=now.isoformat(),
        reply_needed=False,
        metadata={"chat_name": "Ablam", "contact_name": "Ablam", "from": "905369112793@c.us", "to": "905527502749@c.us"},
    )
    store.upsert_whatsapp_message(
        office_id,
        provider="whatsapp",
        conversation_ref="905369112793@c.us",
        message_ref="wa-abla-2",
        sender="Sami",
        recipient="Ablam",
        body="Euro ve rota işini birlikte netleştirelim.",
        direction="outbound",
        sent_at=(now - timedelta(minutes=5)).isoformat(),
        reply_needed=False,
        metadata={"chat_name": "Ablam", "contact_name": "Ablam", "from": "905527502749@c.us", "to": "905369112793@c.us"},
    )

    relationships = build_assistant_relationship_profiles(store, office_id, limit=20)

    sister = next(item for item in relationships if item["display_name"] == "Ablam")
    summary = str(sister.get("summary") or "").lower()
    assert "seyahat" in summary or "rota" in summary or "yurt dışı" in summary
