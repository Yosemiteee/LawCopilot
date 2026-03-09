from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch(mode=0o600)

    def _last_hash(self) -> str:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return "genesis"
        with self.path.open("rb") as f:
            lines = f.read().splitlines()
        if not lines:
            return "genesis"
        try:
            last = json.loads(lines[-1].decode("utf-8"))
            return str(last.get("record_hash", "genesis"))
        except Exception:  # noqa: BLE001
            return "genesis"

    def log(self, event: str, **data) -> str:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **data,
        }
        prev_hash = self._last_hash()
        rec["prev_hash"] = prev_hash
        payload = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        rec["record_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        line = json.dumps(rec, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return rec["ts"]
