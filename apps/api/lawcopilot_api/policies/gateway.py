from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .decision import PolicyDecision, build_action_ladder, resolve_action_policy


@dataclass(frozen=True)
class ExecutionGatewayResult:
    policy_decision: PolicyDecision
    action_ladder: dict[str, Any]


def evaluate_execution_gateway(
    *,
    action_kind: str,
    risk_level: Any,
    policy_label: str | None = None,
    requires_confirmation: bool = False,
    auto_allowed: bool | None = None,
    approval_policy: str | None = None,
    tool_class: str | None = None,
    scope: str | None = None,
    suggest_only: bool = False,
    reversible: bool | None = None,
    current_stage: str = "suggest",
    preview_summary: str = "",
    audit_label: str = "execution",
) -> ExecutionGatewayResult:
    decision = resolve_action_policy(
        action_kind=action_kind,
        risk_level=risk_level,
        policy_label=policy_label,
        requires_confirmation=requires_confirmation,
        auto_allowed=auto_allowed,
        approval_policy=approval_policy,
        tool_class=tool_class,
        scope=scope,
        suggest_only=suggest_only,
        reversible=reversible,
    )
    ladder = build_action_ladder(
        current_stage=current_stage,
        policy_decision=decision,
        preview_summary=preview_summary,
        audit_label=audit_label,
    )
    return ExecutionGatewayResult(policy_decision=decision, action_ladder=ladder)
