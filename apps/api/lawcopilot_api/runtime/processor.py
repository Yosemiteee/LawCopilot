from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any

from .job_queue import BackendJobQueue
from .worker_protocol import WorkerExecutionResult


class BackendJobProcessor:
    def __init__(
        self,
        *,
        store: Any,
        office_id: str,
        knowledge_base: Any | None = None,
        settings: Any | None = None,
        events: Any | None = None,
    ) -> None:
        self.store = store
        self.office_id = office_id
        self.knowledge_base = knowledge_base
        self.settings = settings
        self.events = events
        self.queue = BackendJobQueue(store, office_id)
        self._lock = threading.Lock()
        self._query_executor: Any | None = None
        self._claim_cursor = 0

    def enqueue_knowledge_job(
        self,
        *,
        job_type: str,
        requested_by: str,
        payload: dict[str, Any] | None = None,
        priority: int = 50,
    ) -> dict[str, Any]:
        job = self.queue.enqueue(
            job_type=job_type,
            worker_kind="knowledge_base",
            requested_by=requested_by,
            payload=payload,
            write_intent="backend_apply",
            priority=priority,
        )
        return asdict(job)

    def enqueue_query_job(
        self,
        *,
        requested_by: str,
        payload: dict[str, Any],
        priority: int = 40,
    ) -> dict[str, Any]:
        job = self.queue.enqueue(
            job_type="legacy_query",
            worker_kind="query",
            requested_by=requested_by,
            payload=payload,
            write_intent="read_only",
            priority=priority,
        )
        return asdict(job)

    def set_query_executor(self, executor: Any) -> None:
        self._query_executor = executor

    def process_pending_jobs(self, *, lease_owner: str = "backend-runtime", limit: int = 4) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return {
                "status": "busy",
                "processed_count": 0,
                "completed": [],
                "failed": [],
            }
        try:
            completed: list[dict[str, Any]] = []
            failed: list[dict[str, Any]] = []
            for _ in range(max(1, int(limit or 1))):
                envelope = self._claim_next_job(lease_owner=lease_owner)
                if envelope is None:
                    break
                try:
                    result = self._execute(
                        envelope.job_type,
                        worker_kind=envelope.worker_kind,
                        payload=dict(envelope.payload or {}),
                    )
                    final = self.queue.complete(
                        lease_owner=lease_owner,
                        result=WorkerExecutionResult(
                            job_id=envelope.job_id,
                            status="completed",
                            result=result,
                            backend_apply_required=False,
                        ),
                    )
                    if final:
                        completed.append(final)
                    if self.events is not None:
                        self.events.log(
                            "runtime_job_completed",
                            worker_kind=envelope.worker_kind,
                            job_type=envelope.job_type,
                            job_id=envelope.job_id,
                        )
                except Exception as exc:  # noqa: BLE001
                    self._mark_worker_failure(envelope.worker_kind, dict(envelope.payload or {}), str(exc))
                    final = self.queue.complete(
                        lease_owner=lease_owner,
                        result=WorkerExecutionResult(
                            job_id=envelope.job_id,
                            status="failed",
                            error=str(exc),
                        ),
                    )
                    if final:
                        failed.append(final)
                    if self.events is not None:
                        self.events.log(
                            "runtime_job_failed",
                            level="warning",
                            worker_kind=envelope.worker_kind,
                            job_type=envelope.job_type,
                            job_id=envelope.job_id,
                            error=str(exc),
                        )
            return {
                "status": "ok",
                "processed_count": len(completed) + len(failed),
                "completed": completed,
                "failed": failed,
            }
        finally:
            self._lock.release()

    def summary(self) -> dict[str, Any]:
        return self.store.summarize_runtime_jobs(self.office_id, worker_kind="knowledge_base")

    def list_jobs(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.queue.list(worker_kind="knowledge_base", status=status, limit=limit)]

    def _claim_next_job(self, *, lease_owner: str) -> Any | None:
        worker_kinds = ("query", "knowledge_base")
        start = self._claim_cursor % len(worker_kinds)
        ordered = worker_kinds[start:] + worker_kinds[:start]
        self._claim_cursor += 1
        for worker_kind in ordered:
            envelope = self.queue.claim(worker_kind=worker_kind, lease_owner=lease_owner)
            if envelope is not None:
                return envelope
        return None

    def _execute(self, job_type: str, *, worker_kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if worker_kind == "query":
            return self._execute_query_job(payload)
        if self._use_subprocess_worker():
            return self._execute_in_subprocess(job_type, payload)
        if self.knowledge_base is None:
            raise RuntimeError("Knowledge base runtime job processor not configured.")
        normalized_job_type = str(job_type or "").strip().lower()
        if normalized_job_type == "wiki_compile":
            result = self.knowledge_base.compile_wiki_brain(
                reason=str(payload.get("reason") or "queued_wiki_compile"),
                previews=bool(payload.get("previews")),
            )
            return {
                "job_type": "wiki_compile",
                "reason": str(payload.get("reason") or "queued_wiki_compile"),
                "concept_count": result.get("concept_count"),
                "updated_pages": list(result.get("updated_pages") or []),
            }
        if normalized_job_type == "knowledge_synthesis":
            result = self.knowledge_base.run_knowledge_synthesis(
                reason=str(payload.get("reason") or "queued_knowledge_synthesis")
            )
            return {
                "job_type": "knowledge_synthesis",
                "reason": str(payload.get("reason") or "queued_knowledge_synthesis"),
                "summary": dict(result.get("summary") or {}),
            }
        if normalized_job_type == "reflection":
            result = self.knowledge_base.run_reflection()
            return {
                "job_type": "reflection",
                "generated_at": result.get("generated_at"),
                "health_status": result.get("health_status"),
            }
        if normalized_job_type == "orchestration":
            result = self.knowledge_base.run_orchestration(
                store=self.store,
                settings=self.settings,
                job_names=list(payload.get("job_names") or []),
                reason=str(payload.get("reason") or "queued_orchestration"),
                force=bool(payload.get("force")),
            )
            return {
                "job_type": "orchestration",
                "reason": str(payload.get("reason") or "queued_orchestration"),
                "summary": dict((result.get("status") or {}).get("summary") or {}),
            }
        raise ValueError(f"Unsupported runtime job type: {job_type}")

    def _execute_query_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._query_executor is None:
            raise RuntimeError("Query runtime job executor not configured.")
        job_id = int(payload.get("query_job_id") or 0)
        owner = str(payload.get("owner") or "").strip()
        if job_id <= 0 or not owner:
            raise RuntimeError("Invalid query runtime job payload.")
        latest = self.store.get_query_job(job_id, owner)
        if not latest:
            return {
                "job_type": "legacy_query",
                "query_job_id": job_id,
                "status": "missing",
            }
        if latest.get("cancel_requested"):
            self.store.update_query_job_status(job_id, owner, "cancelled")
            return {
                "job_type": "legacy_query",
                "query_job_id": job_id,
                "status": "cancelled",
            }
        result = dict(self._query_executor(payload) or {})
        latest = self.store.get_query_job(job_id, owner)
        detached = bool((latest or {}).get("detached"))
        self.store.update_query_job_status(
            job_id,
            owner,
            "completed",
            result=result,
            detached=detached,
            toast_pending=detached,
        )
        return {
            "job_type": "legacy_query",
            "query_job_id": job_id,
            "status": "completed",
        }

    def _mark_worker_failure(self, worker_kind: str, payload: dict[str, Any], error: str) -> None:
        if worker_kind != "query":
            return
        job_id = int(payload.get("query_job_id") or 0)
        owner = str(payload.get("owner") or "").strip()
        if job_id <= 0 or not owner:
            return
        self.store.update_query_job_status(job_id, owner, "failed", error=error)

    def _settings_attr(self, key: str, default: Any) -> Any:
        if self.settings is None:
            return default
        return getattr(self.settings, key, default)

    def _use_subprocess_worker(self) -> bool:
        if getattr(sys, "frozen", False):
            return False
        mode = str(self._settings_attr("runtime_job_worker_mode", "inline") or "inline").strip().lower()
        return mode == "process"

    def _python_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _subprocess_payload(self, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.knowledge_base is None:
            raise RuntimeError("Knowledge base runtime job processor not configured.")
        return {
            "job_type": str(job_type or ""),
            "payload": dict(payload or {}),
            "db_path": str(self.store.db_path),
            "kb_root": str(self.knowledge_base.root_dir),
            "office_id": self.office_id,
        }

    def _execute_in_subprocess(self, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        env = os.environ.copy()
        python_root = self._python_root()
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = (
            f"{python_root}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(python_root)
        )
        timeout_seconds = int(self._settings_attr("runtime_job_subprocess_timeout_seconds", 180) or 180)
        completed = subprocess.run(
            [sys.executable, "-m", "lawcopilot_api.runtime.worker_main"],
            input=json.dumps(self._subprocess_payload(job_type, payload), ensure_ascii=False),
            capture_output=True,
            text=True,
            cwd=str(python_root),
            env=env,
            timeout=max(10, timeout_seconds),
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            detail = stderr or stdout or f"worker exited with code {completed.returncode}"
            raise RuntimeError(f"Runtime worker process failed: {detail}")
        raw = (completed.stdout or "").strip()
        if not raw:
            raise RuntimeError("Runtime worker process returned no output.")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Runtime worker process returned invalid JSON: {raw[:400]}") from exc
        if not payload.get("ok"):
            raise RuntimeError(str(payload.get("error") or "Runtime worker process failed."))
        return dict(payload.get("result") or {})
