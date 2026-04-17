from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def build_epistemic_lint_report(
    *,
    epistemic: Any,
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    contradictions: list[dict[str, Any]] = []
    stale_claims: list[dict[str, Any]] = []
    weak_claims: list[dict[str, Any]] = []
    superseded_claims: list[dict[str, Any]] = []
    contamination_risks: list[dict[str, Any]] = []

    for claim in claims:
        subject_key = str(claim.get("subject_key") or "").strip()
        predicate = str(claim.get("predicate") or "").strip()
        scope = str(claim.get("scope") or "global").strip() or "global"
        if subject_key and predicate:
            grouped[(subject_key, predicate, scope)].append(claim)

        support = epistemic.inspect_claim_support(claim=claim)
        memory = epistemic.describe_claim_memory(claim=claim, support=support)
        validation_state = str(claim.get("validation_state") or "unknown").strip().lower()
        retrieval = str(claim.get("retrieval_eligibility") or "eligible").strip().lower()
        support_strength = str((support or {}).get("support_strength") or "unknown").strip().lower()
        age_days = memory.get("age_days")
        payload = {
            "claim_id": claim.get("id"),
            "subject_key": claim.get("subject_key"),
            "predicate": claim.get("predicate"),
            "scope": claim.get("scope"),
            "value_text": claim.get("object_value_text"),
            "basis": claim.get("epistemic_basis"),
            "validation_state": claim.get("validation_state"),
            "retrieval_eligibility": claim.get("retrieval_eligibility"),
            "support_strength": support_strength,
            "age_days": age_days,
            "reason_codes": list((support or {}).get("reason_codes") or []),
        }

        if validation_state in {"superseded", "rejected"} or claim.get("valid_to"):
            superseded_claims.append(payload)
            continue

        if bool((support or {}).get("contaminated")) or bool((support or {}).get("cycle_detected")):
            contamination_risks.append(payload)

        if epistemic._is_active(claim, include_blocked=True):  # type: ignore[attr-defined]
            stale_threshold = 30 if validation_state == "pending" else 180
            try:
                if age_days is not None and int(age_days) >= stale_threshold:
                    stale_claims.append(payload)
            except (TypeError, ValueError):
                pass
            if support_strength in {"weak", "unknown"} or retrieval == "demoted" or validation_state == "pending":
                weak_claims.append(payload)

    for (subject_key, predicate, scope), group in grouped.items():
        active = [claim for claim in group if epistemic._is_active(claim, include_blocked=True)]  # type: ignore[attr-defined]
        distinct_values = {
            str(item.get("object_value_text") or "").strip()
            for item in active
            if str(item.get("object_value_text") or "").strip()
        }
        if len(distinct_values) <= 1:
            continue
        resolved = epistemic.resolve_claim(subject_key=subject_key, predicate=predicate, scope=scope, include_blocked=True)
        status = str(resolved.get("status") or "").strip().lower()
        if status not in {"contested", "contaminated"}:
            continue
        contradictions.append(
            {
                "subject_key": subject_key,
                "predicate": predicate,
                "scope": scope,
                "status": status,
                "value_count": len(distinct_values),
                "values": sorted(distinct_values)[:6],
                "current_claim_id": ((resolved.get("current_claim") or {}) if isinstance(resolved.get("current_claim"), dict) else {}).get("id"),
                "contested_claim_ids": [
                    str(item.get("id") or "")
                    for item in list(resolved.get("contested_claims") or [])
                    if str(item.get("id") or "").strip()
                ][:6],
            }
        )

    summary = {
        "total_claims": len(claims),
        "contradictions": len(contradictions),
        "stale_claims": len(stale_claims),
        "weak_claims": len(weak_claims),
        "superseded_claims": len(superseded_claims),
        "contamination_risks": len(contamination_risks),
        "basis_counts": dict(Counter(str(item.get("epistemic_basis") or "unknown") for item in claims)),
        "validation_counts": dict(Counter(str(item.get("validation_state") or "unknown") for item in claims)),
    }
    return {
        "generated_at": None,
        "summary": summary,
        "contradictions": contradictions[:20],
        "stale_claims": stale_claims[:20],
        "weak_claims": weak_claims[:20],
        "superseded_claims": superseded_claims[:20],
        "contamination_risks": contamination_risks[:20],
    }
