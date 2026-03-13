from __future__ import annotations

from typing import Any


def _account_map(store, office_id: str) -> dict[str, dict[str, Any]]:
    return {str(item.get("provider") or ""): item for item in store.list_connected_accounts(office_id)}


def build_tools_status(settings, store) -> list[dict[str, Any]]:
    accounts = _account_map(store, settings.office_id)
    workspace_root = store.get_active_workspace_root(settings.office_id)
    google_scopes = list(settings.google_scopes or [])
    gmail_scopes = [scope for scope in google_scopes if "gmail" in str(scope)]
    calendar_scopes = [scope for scope in google_scopes if "calendar" in str(scope)]
    drive_scopes = [scope for scope in google_scopes if "drive" in str(scope)]

    return [
        {
            "provider": "gmail",
            "account_label": settings.google_account_label or "Google Mail",
            "connected": settings.gmail_connected,
            "status": "connected" if settings.gmail_connected else "pending",
            "scopes": gmail_scopes,
            "capabilities": ["read_threads", "draft_reply", "send_after_approval"],
            "write_enabled": any("gmail.send" in scope for scope in gmail_scopes),
            "approval_required": True,
            "connected_account": accounts.get("google"),
        },
        {
            "provider": "calendar",
            "account_label": settings.google_account_label or "Google Takvim",
            "connected": settings.calendar_connected,
            "status": "connected" if settings.calendar_connected else "pending",
            "scopes": calendar_scopes,
            "capabilities": ["read_events", "suggest_slots", "create_after_approval", "update_after_approval"],
            "write_enabled": any("calendar.events" in scope for scope in calendar_scopes),
            "approval_required": True,
            "connected_account": accounts.get("google"),
        },
        {
            "provider": "drive",
            "account_label": settings.google_account_label or "Google Drive",
            "connected": settings.drive_connected,
            "status": "connected" if settings.drive_connected else "pending",
            "scopes": drive_scopes,
            "capabilities": ["list_files", "fetch_context", "bind_reference"],
            "write_enabled": False,
            "approval_required": False,
            "connected_account": accounts.get("google"),
        },
        {
            "provider": "telegram",
            "account_label": settings.telegram_bot_username or "Telegram",
            "connected": settings.telegram_configured,
            "status": "connected" if settings.telegram_configured else "pending",
            "scopes": [],
            "capabilities": ["read_messages", "draft_reply", "send_after_approval"],
            "write_enabled": settings.telegram_configured,
            "approval_required": True,
            "connected_account": accounts.get("telegram"),
        },
        {
            "provider": "workspace",
            "account_label": workspace_root.get("display_name") if workspace_root else "Çalışma alanı",
            "connected": bool(workspace_root),
            "status": "connected" if workspace_root else "missing",
            "scopes": [],
            "capabilities": ["search", "summarize", "similarity", "matter_linking"],
            "write_enabled": False,
            "approval_required": False,
            "connected_account": None,
        },
        {
            "provider": "web-search",
            "account_label": "Web arama",
            "connected": True,
            "status": "available",
            "scopes": [],
            "capabilities": ["current_research", "recommendation_support"],
            "write_enabled": False,
            "approval_required": False,
            "connected_account": None,
        },
        {
            "provider": "social",
            "account_label": "Sosyal medya",
            "connected": False,
            "status": "planned",
            "scopes": [],
            "capabilities": ["mentions_read", "draft_post", "schedule_after_approval"],
            "write_enabled": False,
            "approval_required": True,
            "connected_account": None,
        },
        {
            "provider": "travel",
            "account_label": "Seyahat ve bilet",
            "connected": False,
            "status": "planned",
            "scopes": [],
            "capabilities": ["search", "compare", "prepare_reservation"],
            "write_enabled": False,
            "approval_required": True,
            "connected_account": None,
        },
    ]
