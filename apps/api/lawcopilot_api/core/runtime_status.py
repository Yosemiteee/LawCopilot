from __future__ import annotations


def assistant_runtime_mode(*, direct_enabled: bool, advanced_enabled: bool) -> str:
    if direct_enabled:
        return "direct-provider"
    if advanced_enabled:
        return "advanced-openclaw"
    return "fallback-only"
