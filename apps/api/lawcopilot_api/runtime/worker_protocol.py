from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkerJobEnvelope:
    job_id: int
    office_id: str
    job_type: str
    worker_kind: str
    write_intent: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkerExecutionResult:
    job_id: int
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    backend_apply_required: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
