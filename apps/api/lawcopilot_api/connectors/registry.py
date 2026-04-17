from __future__ import annotations

from typing import Any


def _account_map(store, office_id: str) -> dict[str, dict[str, Any]]:
    return {str(item.get("provider") or ""): item for item in store.list_connected_accounts(office_id)}


def build_tools_status(settings, store) -> list[dict[str, Any]]:
    accounts = _account_map(store, settings.office_id)
    workspace_root = store.get_active_workspace_root(settings.office_id)
    google_account = accounts.get("google")
    google_portability_account = accounts.get("google-portability")
    google_account_connected = bool(google_account and str(google_account.get("status") or "").strip().lower() == "connected")
    google_metadata = dict(google_account.get("metadata") or {}) if google_account else {}
    google_scopes = list(google_account.get("scopes") or settings.google_scopes or []) if google_account else list(settings.google_scopes or [])
    gmail_scopes = [scope for scope in google_scopes if "gmail" in str(scope)]
    calendar_scopes = [scope for scope in google_scopes if "calendar" in str(scope)]
    drive_scopes = [scope for scope in google_scopes if "drive" in str(scope)]
    youtube_scopes = [scope for scope in google_scopes if "youtube" in str(scope)]
    gmail_connected = bool(
        len(store.list_email_threads(settings.office_id, provider="google")) > 0
        or google_metadata.get("gmail_connected")
        or (google_account_connected and gmail_scopes)
    )
    calendar_connected = bool(
        len(store.list_calendar_events(settings.office_id, limit=10, provider="google")) > 0
        or google_metadata.get("calendar_connected")
        or (google_account_connected and calendar_scopes)
    )
    drive_connected = bool(
        len(store.list_drive_files(settings.office_id, limit=10)) > 0
        or google_metadata.get("drive_connected")
        or (google_account_connected and drive_scopes)
    )
    youtube_connected = bool(
        len(store.list_external_events(settings.office_id, provider="youtube", event_type="playlist", limit=50)) > 0
        or google_metadata.get("youtube_connected")
        or (google_account_connected and youtube_scopes)
    )
    youtube_history_connected = bool(
        len(store.list_external_events(settings.office_id, provider="youtube", event_type="history", limit=50)) > 0
        or (google_portability_account and google_portability_account.get("status") == "connected")
    )
    chrome_history_connected = bool(
        len(store.list_external_events(settings.office_id, provider="chrome", event_type="history", limit=50)) > 0
        or (google_portability_account and google_portability_account.get("status") == "connected")
    )
    outlook_account = accounts.get("outlook")
    outlook_account_connected = bool(outlook_account and str(outlook_account.get("status") or "").strip().lower() == "connected")
    outlook_metadata = dict(outlook_account.get("metadata") or {}) if outlook_account else {}
    outlook_scopes = list(outlook_account.get("scopes") or settings.outlook_scopes or []) if outlook_account else list(settings.outlook_scopes or [])
    outlook_mail_scopes = [scope for scope in outlook_scopes if "mail" in str(scope).lower()]
    outlook_calendar_scopes = [scope for scope in outlook_scopes if "calendar" in str(scope).lower()]
    outlook_mail_connected = bool(
        len(store.list_email_threads(settings.office_id, provider="outlook")) > 0
        or outlook_metadata.get("mail_connected")
        or (outlook_account_connected and outlook_mail_scopes)
    )
    outlook_calendar_connected = bool(
        len(store.list_calendar_events(settings.office_id, limit=10, provider="outlook")) > 0
        or outlook_metadata.get("calendar_connected")
        or (outlook_account_connected and outlook_calendar_scopes)
    )
    whatsapp_account = accounts.get("whatsapp")
    x_account = accounts.get("x")
    instagram_account = accounts.get("instagram")

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
            "provider": "youtube",
            "account_label": settings.google_account_label or "YouTube",
            "connected": youtube_connected,
            "status": "connected" if youtube_connected else ("pending" if google_account else "missing"),
            "scopes": youtube_scopes,
            "capabilities": ["list_playlists", "read_playlist_context", "preference_learning"],
            "write_enabled": False,
            "approval_required": False,
            "connected_account": google_account,
        },
        {
            "provider": "youtube-history",
            "account_label": (google_portability_account.get("account_label") if google_portability_account else None) or "YouTube geçmişi",
            "connected": youtube_history_connected,
            "status": "connected" if youtube_history_connected else ("pending" if google_portability_account else "missing"),
            "scopes": list(google_portability_account.get("scopes") or [] if google_portability_account else []),
            "capabilities": ["read_watch_history", "preference_learning", "topic_retrieval"],
            "write_enabled": False,
            "approval_required": False,
            "connected_account": google_portability_account,
        },
        {
            "provider": "browser-history",
            "account_label": (google_portability_account.get("account_label") if google_portability_account else None) or "Tarayıcı geçmişi",
            "connected": chrome_history_connected,
            "status": "connected" if chrome_history_connected else ("pending" if google_portability_account else "missing"),
            "scopes": list(google_portability_account.get("scopes") or [] if google_portability_account else []),
            "capabilities": ["read_browser_history", "context_retrieval", "topic_retrieval"],
            "write_enabled": False,
            "approval_required": False,
            "connected_account": google_portability_account,
        },
        {
            "provider": "outlook-mail",
            "account_label": settings.outlook_account_label or "Outlook Mail",
            "connected": outlook_mail_connected,
            "status": "connected" if outlook_mail_connected else ("pending" if outlook_account else "missing"),
            "scopes": outlook_mail_scopes,
            "capabilities": ["read_threads", "draft_reply", "send_after_approval"],
            "write_enabled": bool(outlook_account and outlook_account.get("status") == "connected"),
            "approval_required": True,
            "connected_account": outlook_account,
        },
        {
            "provider": "outlook-calendar",
            "account_label": settings.outlook_account_label or "Outlook Takvim",
            "connected": outlook_calendar_connected,
            "status": "connected" if outlook_calendar_connected else ("pending" if outlook_account else "missing"),
            "scopes": outlook_calendar_scopes,
            "capabilities": ["read_events", "suggest_slots", "create_after_approval", "update_after_approval"],
            "write_enabled": False,
            "approval_required": True,
            "connected_account": outlook_account,
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
            "connected": bool(whatsapp_account and whatsapp_account.get("status") == "connected") or settings.whatsapp_configured,
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
            "provider": "instagram",
            "account_label": instagram_account.get("account_label") if instagram_account else (settings.instagram_account_label or "Instagram"),
            "connected": bool(instagram_account and instagram_account.get("status") == "connected"),
            "status": instagram_account.get("status") if instagram_account else ("connected" if settings.instagram_configured else "pending"),
            "scopes": list(instagram_account.get("scopes") or [] if instagram_account else list(settings.instagram_scopes or [])),
            "capabilities": ["read_messages", "draft_reply", "send_after_approval"],
            "write_enabled": bool(instagram_account and instagram_account.get("status") == "connected") or settings.instagram_configured,
            "approval_required": True,
            "connected_account": instagram_account,
        },
        {
            "provider": "linkedin",
            "account_label": accounts.get("linkedin", {}).get("account_label") if accounts.get("linkedin") else (settings.linkedin_account_label or "LinkedIn"),
            "connected": bool(accounts.get("linkedin") and accounts.get("linkedin", {}).get("status") == "connected"),
            "status": accounts.get("linkedin", {}).get("status") if accounts.get("linkedin") else ("connected" if settings.linkedin_configured else "pending"),
            "scopes": list(accounts.get("linkedin", {}).get("scopes") or [] if accounts.get("linkedin") else list(settings.linkedin_scopes or [])),
            "capabilities": ["draft_post", "send_after_approval"],
            "write_enabled": bool(accounts.get("linkedin") and accounts.get("linkedin", {}).get("status") == "connected") or settings.linkedin_configured,
            "approval_required": True,
            "connected_account": accounts.get("linkedin"),
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
        {
            "provider": "weather",
            "account_label": "Hava durumu",
            "connected": True,
            "status": "available",
            "scopes": [],
            "capabilities": ["current_conditions", "forecast_support", "preference_aware_search"],
            "write_enabled": False,
            "approval_required": False,
            "connected_account": None,
        },
        {
            "provider": "places",
            "account_label": "Mekân ve rota",
            "connected": True,
            "status": "available",
            "scopes": [],
            "capabilities": ["place_search", "route_support", "map_link_preparation"],
            "write_enabled": False,
            "approval_required": False,
            "connected_account": None,
        },
    ]
