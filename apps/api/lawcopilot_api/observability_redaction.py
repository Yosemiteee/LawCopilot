from __future__ import annotations

import json
from typing import Any


_EXACT_SENSITIVE_KEYS = {
    "answer",
    "answer_text",
    "authorization",
    "body",
    "content",
    "cookie",
    "message",
    "message_text",
    "output",
    "password",
    "prompt",
    "prompt_text",
    "raw_content",
    "raw_payload",
    "raw_text",
    "response",
    "response_text",
    "secret",
    "token",
    "transcript",
}

_SENSITIVE_SUBSTRINGS = (
    "access_token",
    "api_key",
    "auth_token",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "oauth",
    "password",
    "refresh_token",
    "secret",
    "session_token",
    "token",
)

_REDACTED = "[redacted]"


def _normalized_key(key: str) -> str:
    return str(key or "").strip().lower()


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalized_key(key)
    if not normalized:
        return False
    if normalized in _EXACT_SENSITIVE_KEYS:
        return True
    return any(marker in normalized for marker in _SENSITIVE_SUBSTRINGS)


def _value_size(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        return len(value)
    if isinstance(value, (bytes, bytearray)):
        return len(value)
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False))
    except Exception:
        return None


def _sanitize_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value
    return str(value)


def sanitize_observability_payload(data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if _is_sensitive_key(key):
            sanitized[key] = _REDACTED
            size = _value_size(value)
            if size is not None:
                sanitized[f"{key}_size"] = size
            sanitized[f"{key}_redacted"] = True
            continue
        if isinstance(value, dict):
            nested = sanitize_observability_payload({str(item_key): item_value for item_key, item_value in value.items()})
            if nested:
                sanitized[key] = nested
            continue
        if isinstance(value, (list, tuple, set, frozenset)):
            items = list(value)[:16]
            if any(_is_sensitive_key(key) for key in [key]):
                sanitized[key] = _REDACTED
                sanitized[f"{key}_size"] = len(list(value))
                sanitized[f"{key}_redacted"] = True
                continue
            sanitized_items: list[Any] = []
            for item in items:
                if isinstance(item, dict):
                    nested = sanitize_observability_payload({str(item_key): item_value for item_key, item_value in item.items()})
                    if nested:
                        sanitized_items.append(nested)
                elif isinstance(item, (list, tuple, set, frozenset)):
                    sanitized_items.append({"redacted_nested_collection": True, "size": len(list(item))})
                else:
                    sanitized_items.append(_sanitize_scalar(item))
            sanitized[key] = sanitized_items
            if len(list(value)) > len(items):
                sanitized[f"{key}_truncated"] = True
            continue
        sanitized[key] = _sanitize_scalar(value)
    return sanitized
