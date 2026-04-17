from __future__ import annotations

import tempfile
from pathlib import Path

from lawcopilot_api.persistence import Persistence
from lawcopilot_api.runtime import BackendJobQueue, WorkerExecutionResult


def test_backend_job_queue_claims_single_job_once_and_finishes_result() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-runtime-jobs-"))
    store = Persistence(temp_dir / "lawcopilot.db")
    queue = BackendJobQueue(store, "default-office")

    first = queue.enqueue(
        job_type="compile_wiki",
        worker_kind="compiler",
        requested_by="backend",
        payload={"page_key": "preferences"},
        write_intent="backend_apply",
        priority=10,
    )
    second = queue.enqueue(
        job_type="rerank_candidates",
        worker_kind="retrieval",
        requested_by="backend",
        payload={"query": "kısa mesaj tercihi"},
        write_intent="read_only",
        priority=20,
    )

    claimed = queue.claim(worker_kind="compiler", lease_owner="worker-1")
    assert claimed is not None
    assert claimed.job_id == first.id
    assert claimed.write_intent == "backend_apply"

    duplicate_claim = queue.claim(worker_kind="compiler", lease_owner="worker-2")
    assert duplicate_claim is None

    completed = queue.complete(
        lease_owner="worker-1",
        result=WorkerExecutionResult(
            job_id=claimed.job_id,
            status="completed",
            result={"compiled": True},
            backend_apply_required=True,
        ),
    )
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["result"]["backend_apply_required"] is True

    retrieval_claim = queue.claim(worker_kind="retrieval", lease_owner="worker-3")
    assert retrieval_claim is not None
    assert retrieval_claim.job_id == second.id


def test_runtime_job_queue_orders_by_priority() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-runtime-jobs-"))
    store = Persistence(temp_dir / "lawcopilot.db")
    queue = BackendJobQueue(store, "default-office")

    queue.enqueue(job_type="low", worker_kind="compiler", requested_by="backend", priority=50)
    high = queue.enqueue(job_type="high", worker_kind="compiler", requested_by="backend", priority=5)

    claimed = queue.claim(worker_kind="compiler", lease_owner="worker-1")

    assert claimed is not None
    assert claimed.job_id == high.id
