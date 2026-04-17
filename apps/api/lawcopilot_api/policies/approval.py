from __future__ import annotations

from typing import Any

from .gateway import evaluate_execution_gateway


WRITE_TOOLS = {
    "gmail_send",
    "calendar_write",
    "telegram_send",
    "social_publish",
    "travel_reserve",
    "workspace_link_write",
}


def tool_requires_approval(tool_name: str, *, write: bool = True) -> bool:
    normalized = str(tool_name or "").strip().lower()
    execution = evaluate_execution_gateway(
        action_kind="tool_execution",
        risk_level="medium" if write or normalized in WRITE_TOOLS else "low",
        approval_policy="reviewed" if write or normalized in WRITE_TOOLS else "none",
        tool_class="write" if write or normalized in WRITE_TOOLS else "read",
        scope="assistant",
        suggest_only=False,
        reversible=not bool(write or normalized in WRITE_TOOLS),
    )
    return execution.policy_decision.requires_confirmation


def build_approval_request(
    *,
    action: dict[str, Any] | None = None,
    draft: dict[str, Any] | None = None,
    tool_name: str | None = None,
    title: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    action_id = int(action["id"]) if action and action.get("id") is not None else None
    draft_id = int(draft["id"]) if draft and draft.get("id") is not None else None
    action_type = str((action or {}).get("action_type") or (draft or {}).get("draft_type") or "").strip().lower()
    target_tool = str(tool_name or str((draft or {}).get("channel") or (action or {}).get("target_channel") or "assistant")).strip().lower()
    resolved_title = (
        str(title or "").strip()
        or str((action or {}).get("title") or "").strip()
        or str((draft or {}).get("subject") or (draft or {}).get("draft_type") or "Onay bekleyen aksiyon")
    )
    resolved_reason = reason or "Dış aksiyonlar kullanıcı onayı olmadan tamamlanmaz."
    if not reason and (action_type == "reserve_travel_ticket" or target_tool == "travel"):
        resolved_reason = "Onay verirsen uygulama içinde güvenli ödeme penceresini açarım."
    if not reason:
        execution = evaluate_execution_gateway(
            action_kind=action_type or "tool_execution",
            risk_level="medium" if target_tool not in {"assistant", "calendar", "task", "tasks"} else "low",
            approval_policy="reviewed",
            tool_class="write",
            scope="assistant",
            suggest_only=True,
            reversible=target_tool in {"calendar", "task", "tasks", "navigation"},
        )
        resolved_reason = execution.policy_decision.reason_summary
    return {
        "id": f"assistant-action-{action_id or draft_id or 'pending'}",
        "action_id": action_id,
        "draft_id": draft_id,
        "tool": tool_name or str((draft or {}).get("channel") or (action or {}).get("target_channel") or "assistant"),
        "title": resolved_title,
        "reason": resolved_reason,
        "status": str((action or {}).get("status") or (draft or {}).get("approval_status") or "pending_review"),
        "approval_required": True,
    }
