from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any


class BrowserWorkerClient:
    def __init__(
        self,
        *,
        enabled: bool,
        command: str,
        profile_dir: Path,
        artifacts_dir: Path,
        allowed_domains: tuple[str, ...] = (),
        timeout_seconds: int = 45,
    ) -> None:
        self.enabled = bool(enabled and str(command or "").strip())
        self.command = str(command or "").strip()
        self.profile_dir = Path(profile_dir)
        self.artifacts_dir = Path(artifacts_dir)
        self.allowed_domains = tuple(str(item or "").strip().lower() for item in allowed_domains if str(item or "").strip())
        self.timeout_seconds = max(10, int(timeout_seconds or 45))

    def extract(
        self,
        *,
        url: str,
        strategy: str = "auto",
        actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "action": "extract",
            "url": str(url or "").strip(),
            "strategy": str(strategy or "auto").strip() or "auto",
            "actions": list(actions or []),
            "profileDir": str(self.profile_dir),
            "artifactsDir": str(self.artifacts_dir),
            "allowlist": list(self.allowed_domains),
        }
        return self._run(payload)

    def _run(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        args = shlex.split(self.command)
        if not args:
            return None
        try:
            completed = subprocess.run(
                args,
                input=json.dumps(payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        raw = (completed.stdout or "").strip() or (completed.stderr or "").strip()
        if completed.returncode != 0 or not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
