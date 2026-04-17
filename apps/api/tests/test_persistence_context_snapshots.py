from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lawcopilot_api.persistence import Persistence


def test_append_assistant_message_persists_context_snapshot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = Persistence(Path(tmp) / "lawcopilot.db")
        thread = store.create_assistant_thread("default-office", created_by="tester")

        message = store.append_assistant_message(
            "default-office",
            thread_id=int(thread["id"]),
            role="assistant",
            content="Merhaba",
            source_context={
                "effective_query": "Bugün ne var?",
                "assistant_context_pack": [
                    {"id": "pm:1", "predicate": "communication.style", "summary": "Kısa ve net"}
                ],
            },
        )

        snapshots = store.list_assistant_context_snapshots(
            "default-office",
            message_id=int(message["id"]),
        )

        assert len(snapshots) == 1
        assert snapshots[0]["thread_id"] == int(thread["id"])
        assert snapshots[0]["message_id"] == int(message["id"])
        assert snapshots[0]["source_context"]["snapshot_version"] == 2
        assert snapshots[0]["source_context"]["effective_query_ref"]["ref_only"] is True
        assert snapshots[0]["source_context"]["assistant_context_pack"][0]["predicate"] == "communication.style"
        assert snapshots[0]["source_context"]["assistant_context_pack"][0]["summary_ref"]["ref_only"] is True


def test_append_assistant_message_without_source_context_skips_snapshot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = Persistence(Path(tmp) / "lawcopilot.db")
        thread = store.create_assistant_thread("default-office", created_by="tester")

        message = store.append_assistant_message(
            "default-office",
            thread_id=int(thread["id"]),
            role="assistant",
            content="Merhaba",
        )

        snapshots = store.list_assistant_context_snapshots(
            "default-office",
            message_id=int(message["id"]),
        )

        assert snapshots == []


def test_context_snapshot_prunes_old_entries() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = Persistence(Path(tmp) / "lawcopilot.db")
        thread = store.create_assistant_thread("default-office", created_by="tester")
        old_created_at = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()

        first_message = store.append_assistant_message(
            "default-office",
            thread_id=int(thread["id"]),
            role="assistant",
            content="Eski bağlam",
        )
        store.append_assistant_context_snapshot(
            "default-office",
            thread_id=int(thread["id"]),
            message_id=int(first_message["id"]),
            source_context={"effective_query": "Çok eski bağlam"},
            created_at=old_created_at,
        )

        store.append_assistant_message(
            "default-office",
            thread_id=int(thread["id"]),
            role="assistant",
            content="Yeni bağlam",
            source_context={"effective_query": "Yeni sorgu"},
        )

        snapshots = store.list_assistant_context_snapshots("default-office", thread_id=int(thread["id"]))

        assert len(snapshots) == 1
        assert all(int(item["message_id"]) != int(first_message["id"]) for item in snapshots)
        assert all("effective_query_ref" in item["source_context"] for item in snapshots)
