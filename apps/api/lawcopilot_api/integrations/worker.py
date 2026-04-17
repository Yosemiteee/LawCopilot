from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .models import IntegrationJobDispatchRequest


class IntegrationSyncWorker:
    def __init__(self, *, service, poll_seconds: int = 15, batch_size: int = 5, actor: str = "integration-worker") -> None:
        self.service = service
        self.poll_seconds = max(1, int(poll_seconds))
        self.batch_size = max(1, int(batch_size))
        self.actor = actor
        self.worker_id = f"integration-worker-{uuid4().hex[:8]}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status: dict[str, Any] = {
            "worker_id": self.worker_id,
            "state": "stopped",
            "poll_seconds": self.poll_seconds,
            "batch_size": self.batch_size,
            "actor": self.actor,
            "started_at": None,
            "last_tick_at": None,
            "last_completed_at": None,
            "last_duration_ms": 0,
            "last_result_count": 0,
            "last_error": None,
            "consecutive_failures": 0,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run_forever, name="lawcopilot-integration-worker", daemon=True)
        self._thread.start()
        self._status.update({"state": "running", "started_at": _utcnow_iso()})

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._status["state"] = "stopped"

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def run_forever(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.poll_seconds)

    def tick(self) -> dict[str, Any]:
        started_at = time.monotonic()
        try:
            self.service.ensure_scheduled_sync_runs(actor=self.actor)
            result = self.service.dispatch_sync_jobs(IntegrationJobDispatchRequest(limit=self.batch_size), actor=self.actor)
            duration_ms = int((time.monotonic() - started_at) * 1000)
            self._status.update(
                {
                    "state": "running",
                    "last_tick_at": _utcnow_iso(),
                    "last_completed_at": _utcnow_iso(),
                    "last_duration_ms": duration_ms,
                    "last_result_count": int(result.get("count") or 0),
                    "last_error": None,
                    "consecutive_failures": 0,
                }
            )
            return result
        except Exception as exc:  # pragma: no cover - defensive background guard
            duration_ms = int((time.monotonic() - started_at) * 1000)
            self._status.update(
                {
                    "state": "error",
                    "last_tick_at": _utcnow_iso(),
                    "last_completed_at": _utcnow_iso(),
                    "last_duration_ms": duration_ms,
                    "last_error": str(exc),
                    "consecutive_failures": int(self._status.get("consecutive_failures") or 0) + 1,
                }
            )
            return {"items": [], "count": 0, "error": str(exc), "generated_from": "integration_sync_worker"}

    def status(self) -> dict[str, Any]:
        return {**self._status, "alive": self.is_alive()}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
