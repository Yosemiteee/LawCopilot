from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from lawcopilot_api.epistemic import EpistemicService
from lawcopilot_api.persistence import Persistence


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "epistemic_eval_cases.json"


def _services():
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-epistemic-eval-"))
    store = Persistence(temp_dir / "lawcopilot.db")
    epistemic = EpistemicService(store, "default-office")
    return store, epistemic


def _load_cases() -> list[dict]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return list(payload.get("cases") or [])


@pytest.mark.parametrize("case", _load_cases(), ids=lambda item: str(item.get("id") or "case"))
def test_epistemic_eval_cases(case: dict) -> None:
    store, epistemic = _services()
    for artifact in list(case.get("artifacts") or []):
        epistemic.record_artifact(
            artifact_id=artifact.get("id"),
            artifact_kind=str(artifact.get("artifact_kind") or "test_artifact"),
            source_kind=str(artifact.get("source_kind") or "test"),
            summary=str(artifact.get("summary") or "fixture"),
            payload=dict(artifact.get("payload") or {}),
            provenance=dict(artifact.get("provenance") or {}),
            source_ref=artifact.get("source_ref"),
            sensitive=bool(artifact.get("sensitive")),
        )
    for claim in list(case.get("claims") or []):
        epistemic.record_claim(
            claim_id=claim.get("id"),
            artifact_id=claim.get("artifact_id"),
            subject_key=str(claim.get("subject_key") or ""),
            predicate=str(claim.get("predicate") or ""),
            object_value_text=str(claim.get("object_value_text") or ""),
            object_value_json=dict(claim.get("object_value_json") or {}),
            scope=str(claim.get("scope") or "global"),
            epistemic_basis=str(claim.get("epistemic_basis") or "inferred"),
            validation_state=str(claim.get("validation_state") or "pending"),
            consent_class=str(claim.get("consent_class") or "allowed"),
            retrieval_eligibility=str(claim.get("retrieval_eligibility") or "eligible"),
            sensitive=bool(claim.get("sensitive")),
            self_generated=bool(claim.get("self_generated")),
            metadata=dict(claim.get("metadata") or {}),
        )

    resolution = epistemic.resolve_claim(
        subject_key=str(case.get("resolve", {}).get("subject_key") or ""),
        predicate=str(case.get("resolve", {}).get("predicate") or ""),
        scope=str(case.get("resolve", {}).get("scope") or "global"),
        include_blocked=bool(case.get("resolve", {}).get("include_blocked", True)),
    )

    expectation = dict(case.get("expect") or {})
    if "status" in expectation:
        assert resolution["status"] == expectation["status"]
    if "current_claim_id" in expectation:
        assert str((resolution.get("current_claim") or {}).get("id") or "") == str(expectation["current_claim_id"])
    if "support_contaminated" in expectation:
        assert bool((resolution.get("current_claim_support") or {}).get("contaminated")) is bool(expectation["support_contaminated"])
    if "support_reason_code" in expectation:
        assert str(expectation["support_reason_code"]) in list((resolution.get("current_claim_support") or {}).get("reason_codes") or [])

    stored_claims = store.list_epistemic_claims("default-office", include_blocked=True, limit=50)
    assert stored_claims
