from __future__ import annotations

from typing import Any

from ..policies.approval import build_approval_request


def _automation_memory_updates(automation_updates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for update in automation_updates or []:
        if not isinstance(update, dict):
            continue
        summary = str(update.get("summary") or "").strip() or "Otomasyon ayarı güncellendi."
        warnings = [str(item).strip() for item in list(update.get("warnings") or []) if str(item).strip()]
        fields: list[str] = []
        for operation in list(update.get("operations") or []):
            if not isinstance(operation, dict):
                continue
            kind = str(operation.get("op") or "").strip()
            path = str(operation.get("path") or "").strip()
            if kind == "set" and path:
                fields.append(path)
                continue
            if kind in {"add_rule", "remove_rule"}:
                fields.append("automation_rules")
        normalized_fields = [field for field in dict.fromkeys(fields) if field]
        items.append(
            {
                "kind": "automation_signal",
                "status": "stored",
                "summary": summary,
                "fields": normalized_fields or ["automation_rules"],
                "route": "/settings?tab=system&section=automation-panel",
                "action": "open_settings",
                "action_label": "Ayarı aç",
                "warnings": warnings,
            }
        )
    return items


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
    youtube_results = source_context.get("youtube_results") if isinstance(source_context.get("youtube_results"), list) else None
    video_analysis = source_context.get("video_analysis") if isinstance(source_context.get("video_analysis"), dict) else None
    website_crawl = source_context.get("website_crawl") if isinstance(source_context.get("website_crawl"), dict) else None
    travel_options = source_context.get("travel_options") if isinstance(source_context.get("travel_options"), list) else None
    weather_results = source_context.get("weather_results") if isinstance(source_context.get("weather_results"), list) else None
    place_results = source_context.get("place_results") if isinstance(source_context.get("place_results"), list) else None
    automation_updates = source_context.get("automation_updates") if isinstance(source_context.get("automation_updates"), list) else None
    pending_task = source_context.get("pending_task") if isinstance(source_context.get("pending_task"), dict) else None
    created_task = source_context.get("created_task") if isinstance(source_context.get("created_task"), dict) else None
    merged_memory_updates = list(memory_updates or [])
    merged_memory_updates.extend(_automation_memory_updates(automation_updates))

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
    elif generated_from.startswith("assistant_task_confirmation") and created_task:
        executed_tools.append(
            {
                "tool": "tasks",
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
        if youtube_results:
            executed_tools.append({"tool": "youtube-search", "mode": "read", "status": "completed", "approval_required": False})
        if video_analysis:
            executed_tools.append({"tool": "video-summary", "mode": "read", "status": "completed", "approval_required": False})
        if website_crawl:
            executed_tools.append({"tool": "web-crawl", "mode": "read", "status": "completed", "approval_required": False})
        if travel_options:
            executed_tools.append({"tool": "travel", "mode": "read", "status": "completed", "approval_required": False})
        if weather_results:
            executed_tools.append({"tool": "weather", "mode": "read", "status": "completed", "approval_required": False})
        if place_results:
            executed_tools.append({"tool": "places", "mode": "read", "status": "completed", "approval_required": False})
        if automation_updates and any(isinstance(item, dict) and item.get("operations") for item in automation_updates):
            executed_tools.append(
                {
                    "tool": "automation",
                    "mode": "prepare_write",
                    "status": "prepared",
                    "approval_required": False,
                }
            )
        if pending_task:
            executed_tools.append(
                {
                    "tool": "tasks",
                    "mode": "prepare_write",
                    "status": "prepared",
                    "approval_required": False,
                }
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
        "memory_updates": merged_memory_updates,
        "executed_tools": executed_tools,
    }
