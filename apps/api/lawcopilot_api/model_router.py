from __future__ import annotations


SENSITIVE_HINTS = {
    "tc",
    "kimlik",
    "iban",
    "adres",
    "telefon",
    "saglik",
    "ceza",
    "sır",
    "müvekkil",
    "gizli",
}


class ModelRouter:
    def __init__(self, profiles: dict):
        self.profiles = profiles
        self.default = profiles.get("default", "hybrid")

    def choose(self, query: str, preferred: str | None = None) -> dict:
        catalog = self.profiles.get("profiles", {})
        if preferred and preferred in catalog:
            selected = preferred
            reason = "client_preference"
        else:
            selected, reason = self._policy_pick(query)

        details = catalog.get(selected) or catalog.get(self.default, {})
        return {"profile": selected, "reason": reason, "details": details}

    def _policy_pick(self, query: str) -> tuple[str, str]:
        text = query.lower()
        if any(hint in text for hint in SENSITIVE_HINTS):
            return "local", "sensitive_content"
        if len(text) > 500:
            return "local", "long_context"
        return self.default, "default_policy"
