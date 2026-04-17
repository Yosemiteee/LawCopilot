import tempfile
from pathlib import Path

from lawcopilot_api.knowledge_base.connectors import EmailThreadConnector, MessageConnector
from lawcopilot_api.persistence import Persistence


def test_email_thread_connector_collects_only_approved_memory_threads():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-email-memory-state-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-operational",
        subject="Operational thread",
        participants=["a@example.com"],
        snippet="Sadece operasyonel.",
        received_at="2026-03-30T08:00:00+00:00",
        reply_needed=True,
        metadata={"sender": "A"},
    )
    store.upsert_email_thread(
        "default-office",
        provider="google",
        thread_ref="thread-approved",
        subject="Approved thread",
        participants=["b@example.com"],
        snippet="Kalıcı hafıza için onaylı.",
        received_at="2026-03-30T09:00:00+00:00",
        reply_needed=True,
        metadata={"sender": "B", "memory_state": "approved_memory"},
    )

    records = EmailThreadConnector().collect(store=store, office_id="default-office")

    assert len(records) == 1
    assert records[0].source_ref == "email-thread:google:thread-approved"
    assert records[0].metadata["memory_state"] == "approved_memory"


def test_message_connector_collects_only_approved_memory_messages():
    temp_dir = tempfile.mkdtemp(prefix="lawcopilot-message-memory-state-")
    store = Persistence(Path(temp_dir) / "lawcopilot.db")
    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp",
        conversation_ref="conv-operational",
        message_ref="msg-operational",
        sender="A",
        recipient="B",
        body="Sadece operasyonel.",
        direction="inbound",
        sent_at="2026-03-30T08:00:00+00:00",
        reply_needed=True,
        metadata={},
    )
    store.upsert_whatsapp_message(
        "default-office",
        provider="whatsapp",
        conversation_ref="conv-approved",
        message_ref="msg-approved",
        sender="C",
        recipient="D",
        body="Kalıcı hafıza için onaylı.",
        direction="inbound",
        sent_at="2026-03-30T09:00:00+00:00",
        reply_needed=True,
        metadata={"memory_state": "approved_memory"},
    )

    records = MessageConnector().collect(store=store, office_id="default-office")

    assert len(records) == 1
    assert records[0].source_ref == "whatsapp:whatsapp:msg-approved"
    assert records[0].metadata["memory_state"] == "approved_memory"
