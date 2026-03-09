from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
import re


PII_PATTERNS = [
    re.compile(r"\b\d{11}\b"),  # TC-like id
    re.compile(r"\bTR\d{24}\b", re.IGNORECASE),
    re.compile(r"\b\+?90\d{10}\b"),
]
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore (all|the|previous) instructions", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
    re.compile(r"developer message", re.IGNORECASE),
    re.compile(r"reveal .*secret", re.IGNORECASE),
    re.compile(r"exfiltrat", re.IGNORECASE),
    re.compile(r"send .*token", re.IGNORECASE),
    re.compile(r"<system>|</system>|BEGIN PROMPT", re.IGNORECASE),
]


@dataclass
class ConnectorPolicy:
    allowed_domains: tuple[str, ...]
    dry_run: bool = True


class ConnectorSafetyWrapper:
    def __init__(self, policy: ConnectorPolicy):
        self.policy = policy

    def validate_destination(self, destination: str) -> None:
        if "@" in destination:
            domain = destination.split("@")[-1].lower()
        else:
            parsed = urlparse(destination)
            domain = (parsed.hostname or "").lower()

        if not domain:
            raise ValueError("destination_not_allowed")

        allowed = tuple(d.lower() for d in self.policy.allowed_domains)
        domain_allowed = any(domain == d or domain.endswith(f".{d}") for d in allowed)
        if not domain_allowed:
            raise ValueError("destination_not_allowed")

    def sanitize_message(self, text: str) -> str:
        redacted = text
        for pattern in PII_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted

    def detect_unsafe_message(self, text: str) -> str | None:
        for pattern in PROMPT_INJECTION_PATTERNS:
            if pattern.search(text):
                return "unsafe_prompt_pattern"
        return None

    def wrap_action(self, destination: str, message: str) -> dict:
        self.validate_destination(destination)
        unsafe_reason = self.detect_unsafe_message(message)
        payload = self.sanitize_message(message)
        return {
            "destination": destination,
            "payload": payload,
            "blocked_pii": payload != message,
            "blocked_instruction": unsafe_reason is not None,
            "unsafe_reason": unsafe_reason,
            "dry_run": self.policy.dry_run,
            "status": "blocked_review" if unsafe_reason else ("queued_preview" if self.policy.dry_run else "ready_to_send"),
        }
