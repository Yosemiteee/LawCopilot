from __future__ import annotations

from dataclasses import dataclass


DEFAULT_BASIS_WEIGHTS: dict[str, float] = {
    "user_explicit": 1.0,
    "connector_observed": 0.9,
    "document_extracted": 0.84,
    "user_confirmed_inference": 0.8,
    "inferred": 0.55,
    "assistant_generated": 0.18,
}

DEFAULT_VALIDATION_WEIGHTS: dict[str, float] = {
    "user_confirmed": 1.0,
    "source_supported": 0.88,
    "pending": 0.52,
    "contested": 0.28,
    "rejected": 0.0,
    "superseded": 0.0,
}

CONSENT_PRECEDENCE: dict[str, int] = {
    "allowed": 0,
    "preview_only": 1,
    "blocked": 2,
}

RETRIEVAL_RESTRICTIVENESS: dict[str, int] = {
    "eligible": 0,
    "demoted": 1,
    "blocked": 2,
    "quarantined": 3,
}


@dataclass(frozen=True)
class PredicateFamilyPolicy:
    family: str
    predicate_exact: tuple[str, ...] = ()
    predicate_prefixes: tuple[str, ...] = ()
    subject_prefixes: tuple[str, ...] = ()
    basis_weights: dict[str, float] | None = None
    validation_weights: dict[str, float] | None = None
    contested_threshold: float = 0.18
    preview_only_penalty: float = 0.12
    blocked_penalty: float = 0.5
    demoted_penalty: float = 0.1
    quarantined_penalty: float = 0.35
    self_generated_penalty: float = 0.35
    sensitive_penalty: float = 0.08

    def matches(self, *, subject_key: str, predicate: str) -> bool:
        normalized_subject = str(subject_key or "").strip().lower()
        normalized_predicate = str(predicate or "").strip().lower()
        if normalized_predicate in self.predicate_exact:
            return True
        if any(normalized_predicate.startswith(prefix) for prefix in self.predicate_prefixes):
            return True
        if any(normalized_subject.startswith(prefix) for prefix in self.subject_prefixes):
            return True
        return False


PREDICATE_FAMILY_POLICIES: tuple[PredicateFamilyPolicy, ...] = (
    PredicateFamilyPolicy(
        family="user_preference",
        predicate_exact=(
            "communication.style",
            "communication_style",
            "assistant_tone",
            "display_name",
            "food_preferences",
            "transport_preference",
            "weather_preference",
            "travel_preferences",
            "favorite_color",
            "goal",
            "goals",
            "interruption_tolerance",
            "reminder_tolerance",
            "planning_style",
            "energy_rhythm",
        ),
        predicate_prefixes=("preference.", "goal.", "routine.", "persona."),
        subject_prefixes=("user", "profile:"),
        basis_weights={
            **DEFAULT_BASIS_WEIGHTS,
            "connector_observed": 0.74,
            "document_extracted": 0.7,
            "user_confirmed_inference": 0.92,
            "inferred": 0.45,
            "assistant_generated": 0.08,
        },
        contested_threshold=0.16,
    ),
    PredicateFamilyPolicy(
        family="contact_preference",
        predicate_exact=("identity.name", "relationship", "preferences", "notes", "communication_style"),
        predicate_prefixes=("contact.", "relationship."),
        subject_prefixes=("contact:",),
        basis_weights={
            **DEFAULT_BASIS_WEIGHTS,
            "connector_observed": 0.82,
            "document_extracted": 0.76,
            "user_confirmed_inference": 0.88,
            "inferred": 0.48,
            "assistant_generated": 0.08,
        },
        contested_threshold=0.16,
    ),
    PredicateFamilyPolicy(
        family="task_state",
        predicate_exact=("status", "due_at", "scheduled_at", "priority", "task.status", "calendar.status"),
        predicate_prefixes=("task.", "calendar.", "event."),
        subject_prefixes=("task:", "calendar:", "event:"),
        basis_weights={
            **DEFAULT_BASIS_WEIGHTS,
            "user_explicit": 0.68,
            "connector_observed": 1.0,
            "document_extracted": 0.9,
            "user_confirmed_inference": 0.62,
            "inferred": 0.35,
            "assistant_generated": 0.05,
        },
        contested_threshold=0.1,
    ),
    PredicateFamilyPolicy(
        family="action_outcome",
        predicate_exact=("narrative", "delivery.status", "action.outcome", "execution.status"),
        predicate_prefixes=("action.", "delivery.", "execution."),
        subject_prefixes=("assistant_output:", "assistant_action:", "delivery:"),
        basis_weights={
            **DEFAULT_BASIS_WEIGHTS,
            "user_explicit": 0.7,
            "connector_observed": 0.92,
            "document_extracted": 0.86,
            "user_confirmed_inference": 0.66,
            "inferred": 0.3,
            "assistant_generated": 0.1,
        },
        contested_threshold=0.1,
        self_generated_penalty=0.45,
    ),
    PredicateFamilyPolicy(
        family="location_context",
        predicate_exact=("current_place", "recent_place", "nearby_category", "location.current"),
        predicate_prefixes=("location.", "place.", "route."),
        subject_prefixes=("location:", "place:", "route:"),
        basis_weights={
            **DEFAULT_BASIS_WEIGHTS,
            "user_explicit": 0.75,
            "connector_observed": 0.98,
            "document_extracted": 0.78,
            "user_confirmed_inference": 0.68,
            "inferred": 0.4,
            "assistant_generated": 0.08,
        },
        contested_threshold=0.12,
    ),
    PredicateFamilyPolicy(
        family="recommendation_feedback",
        predicate_exact=("feedback", "accepted", "rejected", "recommendation.feedback"),
        predicate_prefixes=("recommendation.", "suggestion.", "feedback."),
        subject_prefixes=("recommendation:", "suggestion:", "feedback:"),
        basis_weights={
            **DEFAULT_BASIS_WEIGHTS,
            "connector_observed": 0.72,
            "document_extracted": 0.65,
            "user_confirmed_inference": 0.92,
            "inferred": 0.44,
            "assistant_generated": 0.12,
        },
        contested_threshold=0.14,
    ),
    PredicateFamilyPolicy(
        family="workspace_fact",
        predicate_prefixes=("workspace.", "document.", "inventory.", "order.", "product.", "case.", "matter."),
        subject_prefixes=("workspace:", "document:", "product:", "order:", "case:", "matter:"),
        basis_weights={
            **DEFAULT_BASIS_WEIGHTS,
            "user_explicit": 0.72,
            "connector_observed": 1.0,
            "document_extracted": 0.95,
            "user_confirmed_inference": 0.7,
            "inferred": 0.42,
            "assistant_generated": 0.08,
        },
        contested_threshold=0.12,
    ),
)

DEFAULT_POLICY = PredicateFamilyPolicy(family="default", basis_weights=DEFAULT_BASIS_WEIGHTS, validation_weights=DEFAULT_VALIDATION_WEIGHTS)


def resolve_predicate_family(*, subject_key: str, predicate: str) -> str:
    return get_precedence_policy(subject_key=subject_key, predicate=predicate).family


def get_precedence_policy(*, subject_key: str, predicate: str) -> PredicateFamilyPolicy:
    for policy in PREDICATE_FAMILY_POLICIES:
        if policy.matches(subject_key=subject_key, predicate=predicate):
            return policy
    return DEFAULT_POLICY


def basis_weight(*, subject_key: str, predicate: str, basis: str) -> float:
    policy = get_precedence_policy(subject_key=subject_key, predicate=predicate)
    return float((policy.basis_weights or DEFAULT_BASIS_WEIGHTS).get(str(basis or "").strip(), 0.1))


def validation_weight(*, subject_key: str, predicate: str, validation_state: str) -> float:
    policy = get_precedence_policy(subject_key=subject_key, predicate=predicate)
    return float((policy.validation_weights or DEFAULT_VALIDATION_WEIGHTS).get(str(validation_state or "").strip(), 0.2))


def preferred_basis(*, subject_key: str, predicate: str, left: str, right: str) -> str:
    return left if basis_weight(subject_key=subject_key, predicate=predicate, basis=left) >= basis_weight(subject_key=subject_key, predicate=predicate, basis=right) else right


def preferred_validation(*, subject_key: str, predicate: str, left: str, right: str) -> str:
    return (
        left
        if validation_weight(subject_key=subject_key, predicate=predicate, validation_state=left)
        >= validation_weight(subject_key=subject_key, predicate=predicate, validation_state=right)
        else right
    )

