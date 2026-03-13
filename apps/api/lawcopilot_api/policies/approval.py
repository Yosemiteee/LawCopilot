from __future__ import annotations

from typing import Any


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
    if write:
        return True
    return normalized in WRITE_TOOLS


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
    resolved_title = (
        str(title or "").strip()
        or str((action or {}).get("title") or "").strip()
        or str((draft or {}).get("subject") or (draft or {}).get("draft_type") or "Onay bekleyen aksiyon")
    )
    return {
        "id": f"assistant-action-{action_id or draft_id or 'pending'}",
        "action_id": action_id,
        "draft_id": draft_id,
        "tool": tool_name or str((draft or {}).get("channel") or (action or {}).get("target_channel") or "assistant"),
        "title": resolved_title,
        "reason": reason or "Dış aksiyonlar kullanıcı onayı olmadan tamamlanmaz.",
        "status": str((action or {}).get("status") or (draft or {}).get("approval_status") or "pending_review"),
        "approval_required": True,
    }
