from __future__ import annotations

from typing import Any

from ..policies.approval import build_approval_request


def build_thread_response_extensions(
    *,
    reply: dict[str, Any],
    generated_from: str,
    memory_updates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tool_suggestions = list(reply.get("tool_suggestions") or [])
    proposed_actions: list[dict[str, Any]] = []
    approval_requests: list[dict[str, Any]] = []
    executed_tools: list[dict[str, Any]] = []
    source_context = dict(reply.get("source_context") or {})
    action = source_context.get("assistant_action") if isinstance(source_context.get("assistant_action"), dict) else None
    draft = reply.get("draft_preview") if isinstance(reply.get("draft_preview"), dict) else None

    for item in tool_suggestions:
        proposed_actions.append(
            {
                "tool": str(item.get("tool") or ""),
                "label": str(item.get("label") or ""),
                "reason": str(item.get("reason") or ""),
                "type": "navigation",
            }
        )

    if draft:
        proposed_actions.append(
            {
                "tool": str(draft.get("channel") or "assistant"),
                "label": str(draft.get("subject") or draft.get("draft_type") or "Taslak"),
                "reason": "Asistan dış aksiyon için inceleme bekleyen bir taslak hazırladı.",
                "type": "draft",
                "draft_id": draft.get("id"),
            }
        )

    if reply.get("requires_approval") or action or draft:
        approval_requests.append(build_approval_request(action=action, draft=draft))

    if generated_from.startswith("assistant_calendar_confirmation"):
        executed_tools.append(
            {
                "tool": "calendar",
                "mode": "write",
                "status": "completed",
                "approval_required": False,
            }
        )
    else:
        executed_tools.extend(
            [
                {"tool": "agenda", "mode": "read", "status": "completed", "approval_required": False},
                {"tool": "inbox", "mode": "read", "status": "completed", "approval_required": False},
                {"tool": "calendar", "mode": "read", "status": "completed", "approval_required": False},
            ]
        )
        if draft:
            executed_tools.append(
                {
                    "tool": str(draft.get("channel") or "assistant"),
                    "mode": "prepare_write",
                    "status": "drafted",
                    "approval_required": True,
                }
            )

    return {
        "proposed_actions": proposed_actions,
        "approval_requests": approval_requests,
        "memory_updates": memory_updates or [],
        "executed_tools": executed_tools,
    }
