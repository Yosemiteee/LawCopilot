from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _iso_to_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def claim_memory_profile(
    *,
    claim: dict[str, Any],
    support: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    reference_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    basis = str(claim.get("epistemic_basis") or "").strip().lower()
    validation = str(claim.get("validation_state") or "").strip().lower()
    retrieval = str(claim.get("retrieval_eligibility") or "eligible").strip().lower()
    sensitive = bool(claim.get("sensitive"))
    self_generated = bool(claim.get("self_generated")) or basis == "assistant_generated"
    support_payload = dict(support or {})
    support_strength = str(support_payload.get("support_strength") or "").strip().lower()
    contaminated = bool(support_payload.get("contaminated"))
    external_support_count = int(support_payload.get("external_support_count") or 0)
    updated_at = _iso_to_datetime(claim.get("updated_at")) or _iso_to_datetime(claim.get("created_at")) or _iso_to_datetime(claim.get("valid_from"))
    age_days = max(0, int((reference_now - updated_at).total_seconds() // 86400)) if updated_at else None

    basis_score = {
        "user_explicit": 0.44,
        "user_confirmed_inference": 0.4,
        "connector_observed": 0.37,
        "document_extracted": 0.34,
        "inferred": 0.2,
        "assistant_generated": 0.04,
    }.get(basis, 0.16)
    validation_score = {
        "user_confirmed": 0.24,
        "source_supported": 0.2,
        "current": 0.15,
        "pending": 0.06,
        "contested": -0.1,
        "rejected": -0.45,
        "superseded": -0.4,
    }.get(validation, 0.0)
    support_score = {
        "grounded": 0.16,
        "supported": 0.1,
        "weak": -0.06,
        "contaminated": -0.34,
        "unknown": 0.0,
    }.get(support_strength or "unknown", 0.0)

    score = basis_score + validation_score + support_score
    if external_support_count > 1:
        score += min(0.08, external_support_count * 0.02)
    if retrieval == "demoted":
        score -= 0.1
    elif retrieval in {"blocked", "quarantined"}:
        score -= 0.24
    if sensitive:
        score -= 0.06
    if self_generated:
        score -= 0.18
    if contaminated:
        score -= 0.22
    if age_days is not None:
        if basis in {"user_explicit", "user_confirmed_inference"}:
            score -= min(0.14, age_days * 0.0006)
        elif basis in {"connector_observed", "document_extracted"}:
            score -= min(0.22, age_days * 0.0016)
        else:
            score -= min(0.3, age_days * 0.0024)

    salience_score = round(max(0.0, min(1.0, score)), 4)
    if validation in {"rejected", "superseded"} or contaminated or retrieval in {"blocked", "quarantined"}:
        memory_tier = "cold"
    elif salience_score >= 0.72:
        memory_tier = "hot"
    elif salience_score >= 0.34:
        memory_tier = "warm"
    else:
        memory_tier = "cold"

    stale = bool(age_days is not None and age_days >= 90 and basis not in {"user_explicit", "user_confirmed_inference"})
    return {
        "salience_score": salience_score,
        "memory_tier": memory_tier,
        "age_days": age_days,
        "stale": stale,
        "support_strength": support_strength or None,
        "contaminated": contaminated,
    }
