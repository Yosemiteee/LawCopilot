from __future__ import annotations

from typing import Any


def _account_map(store, office_id: str) -> dict[str, dict[str, Any]]:
    return {str(item.get("provider") or ""): item for item in store.list_connected_accounts(office_id)}


def build_tools_status(settings, store) -> list[dict[str, Any]]:
    accounts = _account_map(store, settings.office_id)
    workspace_root = store.get_active_workspace_root(settings.office_id)
    google_account = accounts.get("google")
    google_scopes = list(google_account.get("scopes") or settings.google_scopes or []) if google_account else list(settings.google_scopes or [])
    gmail_scopes = [scope for scope in google_scopes if "gmail" in str(scope)]
    calendar_scopes = [scope for scope in google_scopes if "calendar" in str(scope)]
    drive_scopes = [scope for scope in google_scopes if "drive" in str(scope)]
    gmail_connected = bool(settings.gmail_connected or gmail_scopes or len(store.list_email_threads(settings.office_id)) > 0)
    calendar_connected = bool(settings.calendar_connected or calendar_scopes or len(store.list_calendar_events(settings.office_id, limit=10)) > 0)
    drive_connected = bool(settings.drive_connected or drive_scopes or len(store.list_drive_files(settings.office_id, limit=10)) > 0)
    whatsapp_account = accounts.get("whatsapp")
    x_account = accounts.get("x")

    return [
        {
            "provider": "gmail",
            "account_label": settings.google_account_label or "Google Mail",
            "connected": gmail_connected,
            "status": "connected" if gmail_connected else ("pending" if google_account else "missing"),
            "scopes": gmail_scopes,
            "capabilities": ["read_threads", "draft_reply", "send_after_approval"],
            "write_enabled": any("gmail.send" in scope for scope in gmail_scopes),
            "approval_required": True,
            "connected_account": google_account,
        },
        {
            "provider": "calendar",
            "account_label": settings.google_account_label or "Google Takvim",
            "connected": calendar_connected,
            "status": "connected" if calendar_connected else ("pending" if google_account else "missing"),
            "scopes": calendar_scopes,
            "capabilities": ["read_events", "suggest_slots", "create_after_approval", "update_after_approval"],
            "write_enabled": any("calendar.events" in scope for scope in calendar_scopes),
            "approval_required": True,
            "connected_account": google_account,
        },
        {
            "provider": "drive",
            "account_label": settings.google_account_label or "Google Drive",
            "connected": drive_connected,
            "status": "connected" if drive_connected else ("pending" if google_account else "missing"),
            "scopes": drive_scopes,
            "capabilities": ["list_files", "fetch_context", "bind_reference"],
            "write_enabled": False,
            "approval_required": False,
            "connected_account": google_account,
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
            "provider": "whatsapp",
            "account_label": whatsapp_account.get("account_label") if whatsapp_account else (settings.whatsapp_account_label or "WhatsApp"),
            "connected": bool(whatsapp_account and whatsapp_account.get("status") == "connected"),
            "status": whatsapp_account.get("status") if whatsapp_account else ("connected" if settings.whatsapp_configured else "pending"),
            "scopes": list(whatsapp_account.get("scopes") or [] if whatsapp_account else []),
            "capabilities": ["read_messages", "draft_reply", "send_after_approval"],
            "write_enabled": bool(whatsapp_account and whatsapp_account.get("status") == "connected") or settings.whatsapp_configured,
            "approval_required": True,
            "connected_account": whatsapp_account,
        },
        {
            "provider": "x",
            "account_label": x_account.get("account_label") if x_account else (settings.x_account_label or "X"),
            "connected": bool(x_account and x_account.get("status") == "connected"),
            "status": x_account.get("status") if x_account else ("connected" if settings.x_configured else "pending"),
            "scopes": list(x_account.get("scopes") or [] if x_account else list(settings.x_scopes or [])),
            "capabilities": ["mentions_read", "draft_post", "send_after_approval"],
            "write_enabled": bool(x_account and x_account.get("status") == "connected") or settings.x_configured,
            "approval_required": True,
            "connected_account": x_account,
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
            "provider": "travel",
            "account_label": "Seyahat ve bilet",
            "connected": True,
            "status": "available",
            "scopes": [],
            "capabilities": ["search", "compare", "prepare_reservation"],
            "write_enabled": False,
            "approval_required": True,
            "connected_account": None,
        },
    ]
