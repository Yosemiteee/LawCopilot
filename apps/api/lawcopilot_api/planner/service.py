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
    document_inventory = source_context.get("document_inventory") if isinstance(source_context.get("document_inventory"), dict) else None
    web_search_results = source_context.get("web_search_results") if isinstance(source_context.get("web_search_results"), list) else None
    travel_options = source_context.get("travel_options") if isinstance(source_context.get("travel_options"), list) else None

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
        if document_inventory and ((document_inventory.get("workspace_count") or 0) or (document_inventory.get("matter_count") or 0)):
            executed_tools.append({"tool": "documents", "mode": "read", "status": "completed", "approval_required": False})
        if web_search_results:
            executed_tools.append({"tool": "web-search", "mode": "read", "status": "completed", "approval_required": False})
        if travel_options:
            executed_tools.append({"tool": "travel", "mode": "read", "status": "completed", "approval_required": False})
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
