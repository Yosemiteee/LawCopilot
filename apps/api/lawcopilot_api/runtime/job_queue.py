from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .worker_protocol import WorkerExecutionResult, WorkerJobEnvelope


@dataclass(frozen=True)
class RuntimeJob:
    id: int
    office_id: str
    job_type: str
    worker_kind: str
    write_intent: str
    status: str
    requested_by: str
    payload: dict[str, Any]
    priority: int

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "RuntimeJob":
        return cls(
            id=int(row.get("id") or 0),
            office_id=str(row.get("office_id") or ""),
            job_type=str(row.get("job_type") or ""),
            worker_kind=str(row.get("worker_kind") or ""),
            write_intent=str(row.get("write_intent") or "read_only"),
            status=str(row.get("status") or ""),
            requested_by=str(row.get("requested_by") or ""),
            payload=dict(row.get("payload") or {}),
            priority=int(row.get("priority") or 100),
        )


class BackendJobQueue:
    def __init__(self, store: Any, office_id: str) -> None:
        self.store = store
        self.office_id = office_id

    def enqueue(
        self,
        *,
        job_type: str,
        worker_kind: str,
        requested_by: str,
        payload: dict[str, Any] | None = None,
        write_intent: str = "read_only",
        priority: int = 100,
    ) -> RuntimeJob:
        row = self.store.create_runtime_job(
            self.office_id,
            job_type=job_type,
            worker_kind=worker_kind,
            requested_by=requested_by,
            payload=payload,
            write_intent=write_intent,
            priority=priority,
        )
        return RuntimeJob.from_row(row)

    def claim(self, *, worker_kind: str, lease_owner: str) -> WorkerJobEnvelope | None:
        row = self.store.claim_runtime_job(
            self.office_id,
            worker_kind=worker_kind,
            lease_owner=lease_owner,
        )
        if not row:
            return None
        return WorkerJobEnvelope(
            job_id=int(row.get("id") or 0),
            office_id=str(row.get("office_id") or self.office_id),
            job_type=str(row.get("job_type") or ""),
            worker_kind=str(row.get("worker_kind") or worker_kind),
            write_intent=str(row.get("write_intent") or "read_only"),
            payload=dict(row.get("payload") or {}),
        )

    def complete(self, *, lease_owner: str, result: WorkerExecutionResult) -> dict[str, Any] | None:
        payload = dict(result.result or {})
        if result.backend_apply_required:
            payload["backend_apply_required"] = True
        return self.store.finish_runtime_job(
            self.office_id,
            int(result.job_id),
            lease_owner=lease_owner,
            status=result.status,
            result=payload or None,
            error=result.error,
        )

    def list(self, *, worker_kind: str | None = None, status: str | None = None, limit: int = 50) -> list[RuntimeJob]:
        rows = self.store.list_runtime_jobs(
            self.office_id,
            worker_kind=worker_kind,
            status=status,
            limit=limit,
        )
        return [RuntimeJob.from_row(row) for row in rows]
