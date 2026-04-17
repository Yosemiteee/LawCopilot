from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .observability_redaction import sanitize_observability_payload


class StructuredLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch(mode=0o600)

    def log(self, event: str, *, level: str = "info", **data: Any) -> str:
        sanitized = sanitize_observability_payload(data)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **sanitized,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record["ts"]

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        items: list[dict[str, Any]] = []
        for line in reversed(lines[-max(1, min(limit, 200)) :]):
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items

    def query(
        self,
        *,
        limit: int = 100,
        since_seconds: int | None = None,
        event_names: Iterable[str] | None = None,
        event_prefixes: Iterable[str] | None = None,
        levels: Iterable[str] | None = None,
        max_scan_lines: int = 5000,
    ) -> list[dict[str, Any]]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return []
        if limit <= 0:
            return []

        normalized_events = {str(item).strip() for item in list(event_names or []) if str(item).strip()}
        normalized_prefixes = tuple(str(item).strip() for item in list(event_prefixes or []) if str(item).strip())
        normalized_levels = {str(item).strip().lower() for item in list(levels or []) if str(item).strip()}
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=since_seconds) if since_seconds and since_seconds > 0 else None

        lines = self.path.read_text(encoding="utf-8").splitlines()
        scanned = lines[-max(1, min(max_scan_lines, 50000)) :]
        items: list[dict[str, Any]] = []
        for line in reversed(scanned):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_name = str(payload.get("event") or "").strip()
            if normalized_events and event_name not in normalized_events:
                continue
            if normalized_prefixes and not any(event_name.startswith(prefix) for prefix in normalized_prefixes):
                continue
            level = str(payload.get("level") or "").strip().lower()
            if normalized_levels and level not in normalized_levels:
                continue
            if cutoff is not None:
                timestamp = _parse_ts(payload.get("ts"))
                if timestamp is None or timestamp < cutoff:
                    continue
            items.append(payload)
            if len(items) >= limit:
                break
        return items


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
