from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from lawcopilot_api.epistemic.service import EpistemicService
from lawcopilot_api.knowledge_base.service import KnowledgeBaseService
from lawcopilot_api.persistence import Persistence
from lawcopilot_api.runtime import BackendJobProcessor


class _KnowledgeBaseStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def compile_wiki_brain(self, *, reason: str, previews: bool) -> dict:
        self.calls.append(("wiki_compile", {"reason": reason, "previews": previews}))
        return {"concept_count": 2, "updated_pages": ["preferences"]}

    def run_knowledge_synthesis(self, *, reason: str) -> dict:
        self.calls.append(("knowledge_synthesis", {"reason": reason}))
        return {"summary": {"generated_records": 3}}

    def run_reflection(self) -> dict:
        self.calls.append(("reflection", {}))
        return {"generated_at": "2026-04-12T10:00:00+00:00", "health_status": "healthy"}

    def run_orchestration(self, *, store, settings, job_names, reason: str, force: bool) -> dict:
        self.calls.append(("orchestration", {"job_names": list(job_names), "reason": reason, "force": force}))
        return {"status": {"summary": {"completed": len(list(job_names)) or 1}}}


def test_runtime_job_processor_executes_queued_kb_jobs() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-runtime-processor-"))
    store = Persistence(temp_dir / "lawcopilot.db")
    kb = _KnowledgeBaseStub()
    processor = BackendJobProcessor(store=store, office_id="default-office", knowledge_base=kb, settings=object())

    processor.enqueue_knowledge_job(
        job_type="wiki_compile",
        requested_by="tester",
        payload={"reason": "queued_compile", "previews": True},
        priority=10,
    )
    processor.enqueue_knowledge_job(
        job_type="reflection",
        requested_by="tester",
        payload={"reason": "queued_reflection"},
        priority=20,
    )

    result = processor.process_pending_jobs(lease_owner="worker-1", limit=5)

    assert result["status"] == "ok"
    assert result["processed_count"] == 2
    assert len(result["failed"]) == 0
    assert kb.calls[0] == ("wiki_compile", {"reason": "queued_compile", "previews": True})
    assert kb.calls[1][0] == "reflection"
    summary = processor.summary()
    assert summary["queued"] == 0
    assert summary["completed"] == 2


def test_runtime_job_processor_marks_failures() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-runtime-processor-"))
    store = Persistence(temp_dir / "lawcopilot.db")
    kb = _KnowledgeBaseStub()
    processor = BackendJobProcessor(store=store, office_id="default-office", knowledge_base=kb, settings=object())

    processor.enqueue_knowledge_job(
        job_type="unsupported_job",
        requested_by="tester",
        payload={"reason": "bad"},
        priority=5,
    )

    result = processor.process_pending_jobs(lease_owner="worker-2", limit=2)

    assert result["processed_count"] == 1
    assert len(result["failed"]) == 1
    summary = processor.summary()
    assert summary["failed"] == 1


def test_runtime_job_processor_can_execute_wiki_compile_in_subprocess_mode() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-runtime-processor-subprocess-"))
    store = Persistence(temp_dir / "lawcopilot.db")
    office_id = "default-office"
    kb_root = temp_dir / "kb-root"
    epistemic = EpistemicService(store, office_id)
    knowledge_base = KnowledgeBaseService(
        kb_root,
        office_id,
        epistemic=epistemic,
        enabled=True,
        search_backend="sqlite_hybrid_fts_v1",
        dense_candidates_enabled=False,
        reranker_mode="local_heuristic",
    )
    settings = SimpleNamespace(
        runtime_job_worker_mode="process",
        runtime_job_subprocess_timeout_seconds=30,
    )
    processor = BackendJobProcessor(
        store=store,
        office_id=office_id,
        knowledge_base=knowledge_base,
        settings=settings,
    )

    processor.enqueue_knowledge_job(
        job_type="wiki_compile",
        requested_by="tester",
        payload={"reason": "subprocess_compile", "previews": False},
        priority=10,
    )

    result = processor.process_pending_jobs(lease_owner="worker-process", limit=2)

    assert result["status"] == "ok"
    assert result["processed_count"] == 1
    assert len(result["failed"]) == 0
    assert len(result["completed"]) == 1
    completed = result["completed"][0]
    assert completed["job_type"] == "wiki_compile"
    summary = processor.summary()
    assert summary["queued"] == 0
    assert summary["completed"] == 1


def test_runtime_job_processor_executes_query_jobs_and_updates_query_status() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-runtime-query-processor-"))
    store = Persistence(temp_dir / "lawcopilot.db")
    processor = BackendJobProcessor(store=store, office_id="default-office", settings=object())
    processor.set_query_executor(
        lambda payload: {
            "answer": f"Yanıt: {payload['query']}",
            "writeback_allowed": bool(payload.get("allow_writeback")),
        }
    )

    query_job = store.create_query_job("tester", "Kısa özet hazırla", None, True)
    processor.enqueue_query_job(
        requested_by="tester",
        payload={
            "query_job_id": int(query_job["id"]),
            "query": "Kısa özet hazırla",
            "model_profile": None,
            "allow_writeback": False,
            "owner": "tester",
            "role": "intern",
            "sid": "query-runtime-test",
        },
    )
    store.request_query_job_cancel(int(query_job["id"]), "tester", keep_background=True)

    result = processor.process_pending_jobs(lease_owner="worker-query", limit=2)

    assert result["status"] == "ok"
    assert result["processed_count"] == 1
    latest = store.get_query_job(int(query_job["id"]), "tester")
    assert latest is not None
    assert latest["status"] == "completed"
    assert latest["detached"] is True
    assert latest["toast_pending"] is True
    assert latest["result"]["answer"] == "Yanıt: Kısa özet hazırla"


def test_runtime_job_processor_cancels_query_jobs_before_execution() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-runtime-query-cancel-"))
    store = Persistence(temp_dir / "lawcopilot.db")
    processor = BackendJobProcessor(store=store, office_id="default-office", settings=object())
    processor.set_query_executor(lambda payload: {"answer": str(payload["query"])})

    query_job = store.create_query_job("tester", "Uzun analiz", None, False)
    processor.enqueue_query_job(
        requested_by="tester",
        payload={
            "query_job_id": int(query_job["id"]),
            "query": "Uzun analiz",
            "model_profile": None,
            "allow_writeback": False,
            "owner": "tester",
            "role": "intern",
            "sid": "query-runtime-cancel",
        },
    )
    store.request_query_job_cancel(int(query_job["id"]), "tester", keep_background=False)

    result = processor.process_pending_jobs(lease_owner="worker-query-cancel", limit=2)

    assert result["status"] == "ok"
    assert result["processed_count"] == 1
    latest = store.get_query_job(int(query_job["id"]), "tester")
    assert latest is not None
    assert latest["status"] == "cancelled"
