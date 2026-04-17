from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FATIGUE_TRIGGER_TYPES = {
    "daily_planning",
    "time_based",
    "end_of_day_reflection",
    "routine_deviation",
}

EXTERNAL_CONTEXT_TRIGGER_TYPES = {
    "location_context",
    "incoming_communication",
    "calendar_load",
    "time_based",
}

LOW_RISK_ACTION_KINDS = {
    "read_summary",
    "draft_message",
    "update_local_memory",
    "create_task_draft",
}

RISK_NORMALIZATION = {
    "a": "A",
    "low": "A",
    "b": "B",
    "medium": "B",
    "c": "C",
    "guarded": "C",
    "d": "D",
    "high": "D",
    "critical": "D",
}

POLICY_LABEL_BY_RISK = {
    "A": "read_only",
    "B": "ask_before_acting",
    "C": "low_risk_automatic",
    "D": "never_auto",
}

AUTO_ALLOWED_BY_RISK = {
    "A": True,
    "B": False,
    "C": True,
    "D": False,
}

REASON_LABELS = {
    "read_only_safe": "Okuma/analiz düzeyinde güvenli olduğu için doğrudan çalışabilir.",
    "approval_policy_active": "Bu yetenek için açık onay politikası tanımlı.",
    "confirmation_required": "Bu adım kullanıcı onayı olmadan ilerlememeli.",
    "preview_before_confirm": "Kullanıcıya önce önizleme gösterilip sonra onay alınmalı.",
    "preview_before_execute": "Yazma etkisi olabileceği için önce önizleme gerekir.",
    "preview_first_assistant_surface": "Asistan yüzeyinde sessiz yürütme yerine taslak/önizleme tercih ediliyor.",
    "low_risk_preview_first": "Düşük riskli olsa da önce kullanıcının görmesi daha güvenli.",
    "high_impact_action": "Bu aksiyon dış dünya veya kalıcı kayıt üzerinde etkili olabilir.",
    "sensitive_scope_guard": "Hassas scope içinde çalışan adımlarda onay çizgisi korunur.",
    "fatigue_guard_active": "Kullanıcı yorgunluğu sinyalleri nedeniyle bu öneri şimdilik bastırıldı.",
    "low_confidence_restraint": "Bağlam güveni düşük olduğu için öneri geri planda tutuldu.",
    "suggestion_budget_exceeded": "Bu turdaki öneri bütçesi dolduğu için öneri gösterilmedi.",
    "connector_health_guard_active": "Connector sağlık durumu zayıf olduğu için dış bağlam önerisi bastırıldı.",
    "reflection_guard_active": "Knowledge health dikkat istediği için düşük güvenli öneri bastırıldı.",
}


def _normalize_risk_level(value: Any) -> str:
    normalized = str(value or "A").strip().lower()
    return RISK_NORMALIZATION.get(normalized, "A")


def _normalize_approval_policy(value: Any) -> str:
    normalized = str(value or "none").strip().lower()
    return normalized or "none"


def _reason_summary(reason_codes: list[str]) -> str:
    labels = [REASON_LABELS.get(code) for code in reason_codes if REASON_LABELS.get(code)]
    if not labels:
        return "Bu karar mevcut risk, güven ve onay politikasına göre verildi."
    return " ".join(dict.fromkeys(labels))


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    risk_level: str
    policy_label: str
    requires_confirmation: bool
    auto_allowed: bool
    preview_required: bool
    trusted_low_risk_available: bool
    reversible: bool
    manual_review_required: bool
    reason_codes: tuple[str, ...]
    reason_summary: str
    suppression_reason: str | None
    execution_policy: str
    next_stage: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "risk_level": self.risk_level,
            "policy_label": self.policy_label,
            "requires_confirmation": self.requires_confirmation,
            "auto_allowed": self.auto_allowed,
            "preview_required": self.preview_required,
            "trusted_low_risk_available": self.trusted_low_risk_available,
            "reversible": self.reversible,
            "manual_review_required": self.manual_review_required,
            "reason_codes": list(self.reason_codes),
            "reason_summary": self.reason_summary,
            "suppression_reason": self.suppression_reason,
            "execution_policy": self.execution_policy,
            "next_stage": self.next_stage,
        }


def resolve_action_policy(
    *,
    action_kind: str | None = None,
    risk_level: Any = None,
    policy_label: str | None = None,
    requires_confirmation: bool = False,
    auto_allowed: bool | None = None,
    approval_policy: str | None = None,
    tool_class: str | None = None,
    scope: str | None = None,
    suggest_only: bool = False,
    reversible: bool | None = None,
) -> PolicyDecision:
    normalized_risk = _normalize_risk_level(risk_level)
    normalized_policy = str(policy_label or POLICY_LABEL_BY_RISK.get(normalized_risk) or "read_only").strip() or "read_only"
    normalized_approval = _normalize_approval_policy(approval_policy)
    effective_requires_confirmation = bool(requires_confirmation or normalized_approval != "none" or normalized_risk in {"B", "D"})
    effective_auto_allowed = AUTO_ALLOWED_BY_RISK.get(normalized_risk, True) if auto_allowed is None else bool(auto_allowed)
    normalized_tool_class = str(tool_class or "read").strip().lower() or "read"
    normalized_scope = str(scope or "global").strip().lower() or "global"
    effective_reversible = bool(reversible) if reversible is not None else (
        normalized_tool_class == "read" or str(action_kind or "").strip().lower() in LOW_RISK_ACTION_KINDS
    )

    reason_codes: list[str] = []
    if normalized_approval != "none":
        reason_codes.append("approval_policy_active")
    if effective_requires_confirmation:
        reason_codes.append("confirmation_required")
    if normalized_risk in {"B", "D"}:
        reason_codes.append("high_impact_action")
    if normalized_scope in {"legal", "professional"} and effective_requires_confirmation:
        reason_codes.append("sensitive_scope_guard")

    if suggest_only:
        if effective_requires_confirmation:
            decision = "preview"
            next_stage = "preview"
            reason_codes.append("preview_before_confirm")
        elif normalized_tool_class == "read" and str(action_kind or "").strip().lower() == "read_summary":
            decision = "draft"
            next_stage = "draft"
            reason_codes.append("preview_first_assistant_surface")
        elif effective_auto_allowed and effective_reversible:
            decision = "draft"
            next_stage = "draft"
            reason_codes.append("low_risk_preview_first")
        else:
            decision = "preview"
            next_stage = "preview"
            reason_codes.append("preview_before_execute")
    else:
        if effective_requires_confirmation:
            decision = "ask_confirm"
            next_stage = "preview"
        elif normalized_tool_class == "read":
            decision = "execute"
            next_stage = "execute"
            reason_codes.append("read_only_safe")
        else:
            decision = "preview"
            next_stage = "preview"
            reason_codes.append("preview_before_execute")

    preview_required = decision in {"preview", "ask_confirm"} or effective_requires_confirmation or normalized_tool_class != "read"
    trusted_low_risk_available = bool(
        effective_auto_allowed and normalized_risk in {"A", "C"} and effective_reversible
    )
    manual_review_required = bool(effective_requires_confirmation or normalized_approval in {"reviewed", "explicit"})
    execution_policy = "preview_then_confirm" if preview_required else "direct_safe_execution"
    return PolicyDecision(
        decision=decision,
        risk_level=normalized_risk,
        policy_label=normalized_policy,
        requires_confirmation=effective_requires_confirmation,
        auto_allowed=effective_auto_allowed,
        preview_required=preview_required,
        trusted_low_risk_available=trusted_low_risk_available,
        reversible=effective_reversible,
        manual_review_required=manual_review_required,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        reason_summary=_reason_summary(reason_codes),
        suppression_reason=None,
        execution_policy=execution_policy,
        next_stage=next_stage,
    )


def resolve_proactive_policy(
    *,
    action_kind: str | None = None,
    risk_level: Any = None,
    policy_label: str | None = None,
    requires_confirmation: bool = False,
    auto_allowed: bool | None = None,
    scope: str | None = None,
    confidence: float = 0.0,
    urgency: str | None = None,
    reminder_tolerance: str | None = None,
    interruption_tolerance: str | None = None,
    recent_rejection_count: int = 0,
    trigger_type: str | None = None,
    connector_attention_required: int = 0,
    reflection_health_status: str | None = None,
    selected_types_forced: bool = False,
    suggestion_budget_remaining: int | None = None,
    reversible: bool | None = None,
) -> PolicyDecision:
    base = resolve_action_policy(
        action_kind=action_kind,
        risk_level=risk_level,
        policy_label=policy_label,
        requires_confirmation=requires_confirmation,
        auto_allowed=auto_allowed,
        approval_policy=None,
        tool_class="read" if str(action_kind or "").strip().lower() == "read_summary" else "write",
        scope=scope,
        suggest_only=True,
        reversible=reversible,
    )
    normalized_urgency = str(urgency or "low").strip().lower() or "low"
    normalized_trigger_type = str(trigger_type or "").strip()
    normalized_reminder_tolerance = str(reminder_tolerance or "normal").strip().lower() or "normal"
    normalized_interruption_tolerance = str(interruption_tolerance or "medium").strip().lower() or "medium"
    normalized_reflection = str(reflection_health_status or "").strip().lower()
    effective_confidence = float(confidence or 0.0)

    suppression_reason: str | None = None
    reason_codes = list(base.reason_codes)

    if not selected_types_forced:
        if suggestion_budget_remaining is not None and suggestion_budget_remaining <= 0 and normalized_urgency != "high":
            suppression_reason = "suggestion_budget_exceeded"
        elif (
            normalized_trigger_type in FATIGUE_TRIGGER_TYPES
            and normalized_reminder_tolerance == "soft"
            and int(recent_rejection_count or 0) >= 2
            and normalized_urgency != "high"
        ):
            suppression_reason = "fatigue_guard_active"
        elif normalized_reflection in {"attention_required", "critical"} and effective_confidence < 0.72 and normalized_urgency != "high":
            suppression_reason = "reflection_guard_active"
        elif (
            normalized_trigger_type in EXTERNAL_CONTEXT_TRIGGER_TYPES
            and int(connector_attention_required or 0) >= 2
            and effective_confidence < 0.7
            and normalized_urgency != "high"
        ):
            suppression_reason = "connector_health_guard_active"
        elif effective_confidence < 0.58 and normalized_urgency != "high":
            suppression_reason = "low_confidence_restraint"
        elif normalized_interruption_tolerance == "low" and normalized_urgency == "low" and int(recent_rejection_count or 0) >= 4:
            suppression_reason = "fatigue_guard_active"

    decision = "silence" if suppression_reason else "suggest"
    if suppression_reason:
        reason_codes.append(suppression_reason)

    return PolicyDecision(
        decision=decision,
        risk_level=base.risk_level,
        policy_label=base.policy_label,
        requires_confirmation=base.requires_confirmation,
        auto_allowed=base.auto_allowed,
        preview_required=base.preview_required,
        trusted_low_risk_available=base.trusted_low_risk_available,
        reversible=base.reversible,
        manual_review_required=base.manual_review_required,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        reason_summary=_reason_summary(reason_codes),
        suppression_reason=suppression_reason,
        execution_policy=base.execution_policy,
        next_stage=base.next_stage,
    )


def build_action_ladder(
    *,
    current_stage: str,
    policy_decision: PolicyDecision,
    preview_summary: str,
    audit_label: str,
    future_stage: str = "trusted_auto_execution",
) -> dict[str, Any]:
    normalized_stage = str(current_stage or "suggest").strip() or "suggest"
    next_steps_map = {
        "suggest": ["draft", "preview", "approve"],
        "draft": ["preview", "approve"],
        "preview": ["approve", "execute"],
        "ask_confirm": ["approve"],
        "approve": ["execute"],
        "one_click_approve": ["execute"],
        "execute": [],
        "trusted_auto_execution": [],
    }
    available_next_stages = list(next_steps_map.get(normalized_stage, []))
    preferred_next = str(policy_decision.next_stage or "").strip()
    if preferred_next and preferred_next not in available_next_stages and preferred_next != normalized_stage:
        available_next_stages.insert(0, preferred_next)
    available_next_stages = list(dict.fromkeys(available_next_stages))

    return {
        "current_stage": normalized_stage,
        "available_next_stages": available_next_stages,
        "manual_review_required": policy_decision.manual_review_required,
        "auto_execution_eligible": bool(policy_decision.decision == "execute" and policy_decision.auto_allowed),
        "future_stage": future_stage,
        "policy_label": policy_decision.policy_label,
        "risk_level": policy_decision.risk_level,
        "trusted_low_risk_available": policy_decision.trusted_low_risk_available,
        "reversible": policy_decision.reversible,
        "preview_required_before_execute": policy_decision.preview_required,
        "preview_summary": preview_summary,
        "audit_label": audit_label,
        "undo_strategy": "Onay ve dispatch kayıtları decision trail üzerinde tutulur; reversible akışlar yeniden taslak oluşturarak geri alınır.",
        "trusted_execution_note": "Düşük riskli akışlarda dahi preview ve kullanıcı onayı korunur." if policy_decision.preview_required else "Düşük riskli, geri alınabilir ve güvenli akışlarda otomasyon ilerleyebilir.",
        "execution_policy": policy_decision.execution_policy,
        "approval_reason": policy_decision.reason_summary,
        "irreversible": not bool(policy_decision.reversible),
        "policy_decision": policy_decision.as_dict(),
    }
