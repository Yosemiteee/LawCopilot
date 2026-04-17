from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from .lifecycle import claim_memory_profile
from .precedence import (
    CONSENT_PRECEDENCE,
    RETRIEVAL_RESTRICTIVENESS,
    basis_weight,
    get_precedence_policy,
    preferred_basis,
    preferred_validation,
    validation_weight,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact_text(value: Any, *, limit: int = 400) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _fingerprint(parts: list[Any]) -> str:
    seed = "|".join(str(item or "") for item in parts)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    normalized = []
    for char in text:
        normalized.append(
            {
                "ç": "c",
                "ğ": "g",
                "ı": "i",
                "ö": "o",
                "ş": "s",
                "ü": "u",
            }.get(char, char)
        )
    compact = "".join(normalized)
    compact = "".join(char if char.isalnum() else "-" for char in compact)
    compact = "-".join(part for part in compact.split("-") if part)
    return compact or "item"


RETRIEVAL_ALLOWED = {"eligible", "demoted"}


class EpistemicService:
    def __init__(self, store: Any, office_id: str, *, events: Any | None = None) -> None:
        self.store = store
        self.office_id = office_id
        self.events = events

    def record_artifact(
        self,
        *,
        artifact_kind: str,
        source_kind: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        source_ref: str | None = None,
        sensitive: bool = False,
        immutable: bool = True,
        artifact_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_artifact_id = artifact_id or f"ea-{uuid4().hex[:20]}"
        artifact = self.store.create_epistemic_artifact(
            self.office_id,
            artifact_id=resolved_artifact_id,
            artifact_kind=artifact_kind,
            source_kind=source_kind,
            source_ref=source_ref,
            summary=_compact_text(summary),
            payload=payload or {},
            provenance=provenance or {},
            sensitive=sensitive,
            immutable=immutable,
        )
        self._log("epistemic_artifact_recorded", artifact_id=resolved_artifact_id, artifact_kind=artifact_kind, source_kind=source_kind)
        return artifact

    def record_claim(
        self,
        *,
        subject_key: str,
        predicate: str,
        object_value_text: str,
        scope: str,
        epistemic_basis: str,
        validation_state: str,
        consent_class: str = "allowed",
        retrieval_eligibility: str = "eligible",
        object_value_json: dict[str, Any] | None = None,
        artifact_id: str | None = None,
        sensitive: bool = False,
        self_generated: bool = False,
        valid_from: str | None = None,
        valid_to: str | None = None,
        supersedes_claim_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        claim_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_claim_id = claim_id or self._claim_id(subject_key, predicate, scope, object_value_text)
        existing = self.store.get_epistemic_claim(self.office_id, resolved_claim_id)
        merged_metadata = dict(metadata or {})
        if existing and str(existing.get("object_value_text") or "").strip() == _compact_text(object_value_text, limit=1000):
            existing_metadata = dict(existing.get("metadata") or {})
            existing_metadata.update(merged_metadata)
            merged_metadata = existing_metadata
            epistemic_basis = self._preferred_basis(
                subject_key=subject_key,
                predicate=predicate,
                left=str(existing.get("epistemic_basis") or ""),
                right=str(epistemic_basis or ""),
            )
            validation_state = self._preferred_validation(
                subject_key=subject_key,
                predicate=predicate,
                left=str(existing.get("validation_state") or ""),
                right=str(validation_state or ""),
            )
            consent_class = self._more_restrictive_consent(str(existing.get("consent_class") or "allowed"), str(consent_class or "allowed"))
            retrieval_eligibility = self._more_restrictive_retrieval(
                str(existing.get("retrieval_eligibility") or "eligible"),
                str(retrieval_eligibility or "eligible"),
            )
            artifact_id = str(existing.get("artifact_id") or artifact_id or "").strip() or artifact_id
            sensitive = bool(existing.get("sensitive")) or sensitive
            self_generated = bool(existing.get("self_generated")) and self_generated
            valid_from = str(existing.get("valid_from") or valid_from or "").strip() or valid_from
            valid_to = str(existing.get("valid_to") or valid_to or "").strip() or valid_to
            supersedes_claim_id = str(existing.get("supersedes_claim_id") or supersedes_claim_id or "").strip() or supersedes_claim_id
        claim = self.store.create_epistemic_claim(
            self.office_id,
            claim_id=resolved_claim_id,
            artifact_id=artifact_id,
            subject_key=subject_key,
            predicate=predicate,
            object_value_text=_compact_text(object_value_text, limit=1000),
            object_value_json=object_value_json or {},
            scope=scope,
            epistemic_basis=epistemic_basis,
            validation_state=validation_state,
            consent_class=consent_class,
            retrieval_eligibility=retrieval_eligibility,
            sensitive=sensitive,
            self_generated=self_generated,
            valid_from=valid_from or _iso_now(),
            valid_to=valid_to,
            supersedes_claim_id=supersedes_claim_id,
            metadata=merged_metadata,
        )
        self._log(
            "epistemic_claim_recorded",
            claim_id=resolved_claim_id,
            subject_key=subject_key,
            predicate=predicate,
            basis=epistemic_basis,
            validation=validation_state,
            retrieval_eligibility=retrieval_eligibility,
        )
        return claim

    def resolve_claim(
        self,
        *,
        subject_key: str,
        predicate: str,
        scope: str,
        include_blocked: bool = False,
    ) -> dict[str, Any]:
        claims = self.store.list_epistemic_claims(
            self.office_id,
            subject_key=subject_key,
            predicate=predicate,
            scope=scope,
            include_blocked=include_blocked,
            limit=100,
        )
        active = [item for item in claims if self._is_active(item, include_blocked=include_blocked)]
        if not active:
            return {
                "status": "unknown",
                "subject_key": subject_key,
                "predicate": predicate,
                "scope": scope,
                "current_claim": None,
                "candidate_claims": [],
            }
        ranked_entries = [
            {
                "claim": item,
                "support": self.inspect_claim_support(claim=item),
            }
            for item in active
        ]
        ranked_entries.sort(
            key=lambda entry: self._claim_rank_with_support(entry["claim"], entry["support"]),
            reverse=True,
        )
        top_entry = ranked_entries[0]
        top = top_entry["claim"]
        top_support = top_entry["support"]
        top_value = str(top.get("object_value_text") or "").strip()
        precedence_policy = get_precedence_policy(subject_key=subject_key, predicate=predicate)
        conflicts = [
            entry["claim"]
            for entry in ranked_entries[1:]
            if str(entry["claim"].get("object_value_text") or "").strip()
            and str(entry["claim"].get("object_value_text") or "").strip() != top_value
            and (
                self._claim_rank_with_support(top, top_support)
                - self._claim_rank_with_support(entry["claim"], entry["support"])
            ) <= float(precedence_policy.contested_threshold)
        ]
        status = "contaminated" if bool(top_support.get("contaminated")) else "contested" if conflicts else "current"
        return {
            "status": status,
            "subject_key": subject_key,
            "predicate": predicate,
            "scope": scope,
            "current_claim": top,
            "current_claim_support": top_support,
            "current_claim_memory": self.describe_claim_memory(claim=top, support=top_support),
            "candidate_claims": [entry["claim"] for entry in ranked_entries[:10]],
            "contested_claims": conflicts[:5],
        }

    def sync_personal_fact(
        self,
        *,
        fact: dict[str, Any],
        raw_entry: dict[str, Any] | None,
        source_kind: str,
        basis: str,
        validation_state: str,
    ) -> dict[str, Any]:
        metadata = dict(fact.get("metadata") or {})
        raw_payload = {
            "raw_entry": raw_entry or {},
            "fact": {
                "id": fact.get("id"),
                "fact_key": fact.get("fact_key"),
                "value_text": fact.get("value_text"),
                "scope": fact.get("scope"),
                "confidence": fact.get("confidence"),
            },
        }
        raw_entry_id = (raw_entry or {}).get("id")
        artifact = self.record_artifact(
            artifact_kind="personal_model_entry",
            source_kind=source_kind,
            source_ref=f"personal-model-entry:{raw_entry_id or fact.get('id')}",
            summary=str(fact.get("title") or fact.get("fact_key") or "Personal model fact"),
            payload=raw_payload,
            provenance={
                "fact_id": fact.get("id"),
                "fact_key": fact.get("fact_key"),
                "source_entry_id": raw_entry_id,
                "confidence_type": fact.get("confidence_type"),
            },
            sensitive=bool(fact.get("sensitive")),
        )
        prior = self.resolve_claim(
            subject_key="user",
            predicate=str(fact.get("fact_key") or ""),
            scope=str(fact.get("scope") or "global"),
            include_blocked=True,
        )
        current_claim = prior.get("current_claim") if isinstance(prior, dict) else None
        current_id = str((current_claim or {}).get("id") or "").strip()
        current_value = str((current_claim or {}).get("object_value_text") or "").strip()
        next_value = str(fact.get("value_text") or "").strip()
        supersedes_claim_id = None
        if current_id and current_value and next_value and current_value != next_value:
            supersedes_claim_id = current_id
            self.store.update_epistemic_claim(
                self.office_id,
                current_id,
                validation_state="superseded",
                retrieval_eligibility="blocked" if bool(fact.get("sensitive")) else "demoted",
                valid_to=_iso_now(),
                metadata={
                    "superseded_by_fact_id": fact.get("id"),
                    "superseded_by_value": next_value,
                },
            )
        claim = self.record_claim(
            subject_key="user",
            predicate=str(fact.get("fact_key") or ""),
            object_value_text=next_value,
            object_value_json=dict(fact.get("value_json") or {}),
            scope=str(fact.get("scope") or "global"),
            epistemic_basis=basis,
            validation_state=validation_state,
            consent_class="blocked" if bool(fact.get("never_use")) else "allowed",
            retrieval_eligibility=self._personal_fact_retrieval_eligibility(fact),
            artifact_id=str(artifact.get("id") or ""),
            sensitive=bool(fact.get("sensitive")),
            self_generated=False,
            supersedes_claim_id=supersedes_claim_id,
            metadata={
                "fact_id": fact.get("id"),
                "source_entry_id": fact.get("source_entry_id"),
                "confidence_type": fact.get("confidence_type"),
                "visibility": fact.get("visibility"),
                "enabled": bool(fact.get("enabled")),
                "never_use": bool(fact.get("never_use")),
                "source_metadata": metadata,
            },
        )
        return {
            "artifact": artifact,
            "claim": claim,
            "resolution": self.resolve_claim(
                subject_key="user",
                predicate=str(fact.get("fact_key") or ""),
                scope=str(fact.get("scope") or "global"),
                include_blocked=True,
            ),
        }

    def record_assistant_output(
        self,
        *,
        kind: str,
        title: str,
        content: str,
        scope: str,
        sensitivity: str,
        metadata: dict[str, Any] | None = None,
        source_refs: list[dict[str, Any] | str] | None = None,
    ) -> dict[str, Any]:
        artifact = self.record_artifact(
            artifact_kind="assistant_output",
            source_kind="assistant_generated",
            source_ref=f"assistant-output:{kind}:{_fingerprint([title, scope, content])}",
            summary=title,
            payload={
                "kind": kind,
                "title": title,
                "content": content,
                "scope": scope,
                "sensitivity": sensitivity,
                "metadata": metadata or {},
                "source_refs": list(source_refs or []),
            },
            provenance={
                "kind": kind,
                "scope": scope,
                "sensitivity": sensitivity,
            },
            sensitive=sensitivity in {"high", "restricted"},
        )
        claim = self.record_claim(
            subject_key=f"assistant_output:{kind}",
            predicate="narrative",
            object_value_text=title,
            object_value_json={"content": content},
            scope=scope,
            epistemic_basis="assistant_generated",
            validation_state="pending",
            consent_class="preview_only",
            retrieval_eligibility="quarantined",
            artifact_id=str(artifact.get("id") or ""),
            sensitive=sensitivity in {"high", "restricted"},
            self_generated=True,
            metadata={
                "kind": kind,
                "source_refs": list(source_refs or []),
                "note": "Assistant-generated outputs are quarantined until independently supported or explicitly approved.",
                "source_metadata": metadata or {},
            },
        )
        return {"artifact": artifact, "claim": claim}

    def record_profile_claims(
        self,
        *,
        profile: dict[str, Any],
        runtime_profile: dict[str, Any] | None = None,
        source_ref: str | None = None,
    ) -> dict[str, Any]:
        runtime_payload = dict(runtime_profile or {})
        artifact = self.record_artifact(
            artifact_kind="profile_snapshot",
            source_kind="profile_snapshot",
            source_ref=source_ref or f"profile-snapshot:{self.office_id}",
            summary="Kullanıcı profil anlık görüntüsü",
            payload={"profile": dict(profile or {}), "runtime_profile": runtime_payload},
            provenance={"source_ref": source_ref},
            sensitive=True,
        )
        created_claims: list[dict[str, Any]] = []
        for field in (
            "display_name",
            "communication_style",
            "food_preferences",
            "transport_preference",
            "weather_preference",
            "travel_preferences",
            "assistant_notes",
        ):
            value = _compact_text(profile.get(field), limit=1000)
            if not value:
                continue
            created_claims.append(
                self.record_claim(
                    subject_key="user",
                    predicate=field,
                    object_value_text=value,
                    scope="personal",
                    epistemic_basis="user_explicit",
                    validation_state="user_confirmed",
                    consent_class="allowed",
                    retrieval_eligibility="blocked" if field == "assistant_notes" else "eligible",
                    artifact_id=str(artifact.get("id") or ""),
                    sensitive=field == "assistant_notes",
                    metadata={"source_ref": source_ref, "field": field, "source_kind": "profile_snapshot"},
                )
            )
        for related in list(profile.get("related_profiles") or []):
            if not isinstance(related, dict):
                continue
            name = _compact_text(related.get("name"), limit=120)
            if not name:
                continue
            relation = _compact_text(related.get("relationship"), limit=120)
            preferences = _compact_text(related.get("preferences"), limit=500)
            notes = _compact_text(related.get("notes"), limit=500)
            subject_key = f"contact:{_slugify(name)}"
            created_claims.append(
                self.record_claim(
                    subject_key=subject_key,
                    predicate="identity.name",
                    object_value_text=name,
                    scope="personal",
                    epistemic_basis="user_explicit",
                    validation_state="user_confirmed",
                    artifact_id=str(artifact.get("id") or ""),
                    metadata={"source_ref": source_ref, "field": "related_profiles.name"},
                )
            )
            if relation:
                created_claims.append(
                    self.record_claim(
                        subject_key=subject_key,
                        predicate="relationship",
                        object_value_text=relation,
                        scope="personal",
                        epistemic_basis="user_explicit",
                        validation_state="user_confirmed",
                        artifact_id=str(artifact.get("id") or ""),
                        metadata={"source_ref": source_ref, "field": "related_profiles.relationship"},
                    )
                )
            if preferences:
                created_claims.append(
                    self.record_claim(
                        subject_key=subject_key,
                        predicate="preferences",
                        object_value_text=preferences,
                        scope="personal",
                        epistemic_basis="user_explicit",
                        validation_state="user_confirmed",
                        artifact_id=str(artifact.get("id") or ""),
                        metadata={"source_ref": source_ref, "field": "related_profiles.preferences"},
                    )
                )
            if notes:
                created_claims.append(
                    self.record_claim(
                        subject_key=subject_key,
                        predicate="notes",
                        object_value_text=notes,
                        scope="personal",
                        epistemic_basis="user_explicit",
                        validation_state="user_confirmed",
                        consent_class="preview_only",
                        retrieval_eligibility="demoted",
                        artifact_id=str(artifact.get("id") or ""),
                        sensitive=True,
                        metadata={"source_ref": source_ref, "field": "related_profiles.notes"},
                    )
                )
        return {"artifact": artifact, "claims": created_claims}

    def _claim_id(self, subject_key: str, predicate: str, scope: str, object_value_text: str) -> str:
        return f"ec-{_fingerprint([subject_key, predicate, scope, object_value_text])}"

    def _is_active(self, claim: dict[str, Any], *, include_blocked: bool) -> bool:
        validation_state = str(claim.get("validation_state") or "")
        if validation_state in {"rejected", "superseded"}:
            return False
        if claim.get("valid_to"):
            return False
        if not include_blocked and str(claim.get("retrieval_eligibility") or "") not in RETRIEVAL_ALLOWED:
            return False
        return True

    def _claim_rank(self, claim: dict[str, Any]) -> float:
        subject_key = str(claim.get("subject_key") or "")
        predicate = str(claim.get("predicate") or "")
        precedence_policy = get_precedence_policy(subject_key=subject_key, predicate=predicate)
        basis_score = basis_weight(
            subject_key=subject_key,
            predicate=predicate,
            basis=str(claim.get("epistemic_basis") or ""),
        )
        validation_score = validation_weight(
            subject_key=subject_key,
            predicate=predicate,
            validation_state=str(claim.get("validation_state") or ""),
        )
        consent_class = str(claim.get("consent_class") or "allowed")
        retrieval_state = str(claim.get("retrieval_eligibility") or "eligible")
        score = (basis_score * 0.6) + (validation_score * 0.35)
        if consent_class == "blocked":
            score -= float(precedence_policy.blocked_penalty)
        elif consent_class == "preview_only":
            score -= float(precedence_policy.preview_only_penalty)
        if retrieval_state == "demoted":
            score -= float(precedence_policy.demoted_penalty)
        if retrieval_state in {"blocked", "quarantined"}:
            score -= float(precedence_policy.quarantined_penalty)
        if bool(claim.get("self_generated")):
            score -= float(precedence_policy.self_generated_penalty)
        if bool(claim.get("sensitive")):
            score -= float(precedence_policy.sensitive_penalty)
        return round(score, 4)

    def _claim_rank_with_support(self, claim: dict[str, Any], support: dict[str, Any] | None) -> float:
        score = self._claim_rank(claim)
        if not isinstance(support, dict):
            return score
        lifecycle = self.describe_claim_memory(claim=claim, support=support)
        if bool(support.get("contaminated")):
            score -= 0.55
        strength = str(support.get("support_strength") or "")
        if strength == "grounded":
            score += 0.04
        elif strength == "supported":
            score += 0.02
        elif strength == "weak" and str(claim.get("epistemic_basis") or "") in {"inferred", "assistant_generated"}:
            score -= 0.08
        memory_tier = str(lifecycle.get("memory_tier") or "").strip().lower()
        if memory_tier == "hot":
            score += 0.05
        elif memory_tier == "warm":
            score += 0.015
        elif memory_tier == "cold":
            score -= 0.04
        salience_score = float(lifecycle.get("salience_score") or 0.0)
        score += min(0.05, salience_score * 0.05)
        return round(score, 4)

    def inspect_claim_support(
        self,
        *,
        claim: dict[str, Any] | None = None,
        claim_id: str | None = None,
        _visited: set[str] | None = None,
    ) -> dict[str, Any]:
        current = dict(claim or {})
        if not current and claim_id:
            current = dict(self.store.get_epistemic_claim(self.office_id, claim_id) or {})
        resolved_claim_id = str(current.get("id") or claim_id or "").strip()
        basis = str(current.get("epistemic_basis") or "").strip()
        retrieval_eligibility = str(current.get("retrieval_eligibility") or "").strip()
        direct_self_generated = bool(current.get("self_generated")) or basis == "assistant_generated"
        if not resolved_claim_id:
            return {
                "claim_id": claim_id,
                "supporting_claim_ids": [],
                "support_chain_depth": 0,
                "external_support_count": 0,
                "self_generated_support_count": 0,
                "cycle_detected": False,
                "contaminated": False,
                "support_strength": "unknown",
                "reason_codes": [],
            }
        visited = set(_visited or set())
        if resolved_claim_id in visited:
            return {
                "claim_id": resolved_claim_id,
                "supporting_claim_ids": [],
                "support_chain_depth": 0,
                "external_support_count": 0,
                "self_generated_support_count": 0,
                "cycle_detected": True,
                "contaminated": True,
                "support_strength": "contaminated",
                "reason_codes": ["cycle_detected"],
                "direct_self_generated": direct_self_generated,
                "retrieval_eligibility": retrieval_eligibility,
            }
        metadata = dict(current.get("metadata") or {})
        supporting_claim_ids: list[str] = []
        for key in ("supporting_claim_ids", "source_claim_ids", "derived_from_claim_ids"):
            value = metadata.get(key)
            if isinstance(value, list):
                supporting_claim_ids.extend(str(item).strip() for item in value if str(item).strip())
            elif isinstance(value, str) and value.strip():
                supporting_claim_ids.append(value.strip())
        supporting_claim_ids = list(dict.fromkeys(supporting_claim_ids))
        trusted_bases = {"user_explicit", "connector_observed", "document_extracted", "user_confirmed_inference"}
        direct_external_grounding = basis in trusted_bases
        external_support_count = 0
        self_generated_support_count = 0
        max_depth = 1
        cycle_detected = False
        contaminated_child = False
        next_visited = set(visited)
        next_visited.add(resolved_claim_id)
        for supporting_id in supporting_claim_ids:
            supporting_claim = self.store.get_epistemic_claim(self.office_id, supporting_id)
            if not supporting_claim:
                continue
            child_support = self.inspect_claim_support(claim=supporting_claim, _visited=next_visited)
            child_basis = str(supporting_claim.get("epistemic_basis") or "").strip()
            child_self_generated = bool(supporting_claim.get("self_generated")) or child_basis == "assistant_generated"
            child_retrieval = str(supporting_claim.get("retrieval_eligibility") or "").strip()
            if child_self_generated or child_retrieval == "quarantined":
                self_generated_support_count += 1
            elif child_basis in trusted_bases:
                external_support_count += 1
            external_support_count += int(child_support.get("external_support_count") or 0)
            self_generated_support_count += int(child_support.get("self_generated_support_count") or 0)
            max_depth = max(max_depth, 1 + int(child_support.get("support_chain_depth") or 0))
            cycle_detected = cycle_detected or bool(child_support.get("cycle_detected"))
            contaminated_child = contaminated_child or bool(child_support.get("contaminated"))
        reason_codes: list[str] = []
        if cycle_detected:
            reason_codes.append("cycle_detected")
        if direct_self_generated and external_support_count == 0:
            reason_codes.append("self_generated_without_external_support")
        if supporting_claim_ids and external_support_count == 0 and self_generated_support_count > 0:
            reason_codes.append("assistant_only_support_chain")
        if contaminated_child and external_support_count == 0:
            reason_codes.append("contaminated_support_chain")
        contaminated = bool(reason_codes)
        if contaminated:
            support_strength = "contaminated"
        elif direct_external_grounding or external_support_count > 0:
            support_strength = "grounded" if direct_external_grounding else "supported"
        else:
            support_strength = "weak"
        return {
            "claim_id": resolved_claim_id,
            "supporting_claim_ids": supporting_claim_ids,
            "support_chain_depth": max_depth,
            "external_support_count": external_support_count,
            "self_generated_support_count": self_generated_support_count,
            "cycle_detected": cycle_detected,
            "contaminated": contaminated,
            "support_strength": support_strength,
            "reason_codes": reason_codes,
            "direct_self_generated": direct_self_generated,
            "retrieval_eligibility": retrieval_eligibility,
        }

    def describe_claim_memory(
        self,
        *,
        claim: dict[str, Any],
        support: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return claim_memory_profile(claim=claim, support=support)

    @staticmethod
    def _personal_fact_retrieval_eligibility(fact: dict[str, Any]) -> str:
        if bool(fact.get("never_use")) or not bool(fact.get("enabled", True)):
            return "blocked"
        if bool(fact.get("sensitive")):
            return "blocked"
        return "eligible"

    def _log(self, event: str, **payload: Any) -> None:
        if self.events is None:
            return
        try:
            self.events.log(event, office_id=self.office_id, **payload)
        except Exception:
            return

    @staticmethod
    def _preferred_basis(*, subject_key: str, predicate: str, left: str, right: str) -> str:
        return preferred_basis(subject_key=subject_key, predicate=predicate, left=left, right=right)

    @staticmethod
    def _preferred_validation(*, subject_key: str, predicate: str, left: str, right: str) -> str:
        return preferred_validation(subject_key=subject_key, predicate=predicate, left=left, right=right)

    @staticmethod
    def _more_restrictive_consent(left: str, right: str) -> str:
        return left if CONSENT_PRECEDENCE.get(left, 0) >= CONSENT_PRECEDENCE.get(right, 0) else right

    @staticmethod
    def _more_restrictive_retrieval(left: str, right: str) -> str:
        return left if RETRIEVAL_RESTRICTIVENESS.get(left, 0) >= RETRIEVAL_RESTRICTIVENESS.get(right, 0) else right
