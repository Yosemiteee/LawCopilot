from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from .workflows import build_chronology
from .workflows import build_risk_notes


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _parse_profile_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _next_profile_occurrence(item: dict[str, Any], today: date) -> tuple[date, int] | None:
    base = _parse_profile_date(item.get("date"))
    if not base:
        return None
    if bool(item.get("recurring_annually", True)):
        try:
            candidate = date(today.year, base.month, base.day)
        except ValueError:
            return None
        if candidate < today:
            try:
                candidate = date(today.year + 1, base.month, base.day)
            except ValueError:
                return None
    else:
        candidate = base
        if candidate < today:
            return None
    return candidate, (candidate - today).days


def _upcoming_profile_dates(store, office_id: str, *, window_days: int) -> list[dict[str, Any]]:
    profile = store.get_user_profile(office_id)
    today = datetime.now(timezone.utc).date()
    items: list[dict[str, Any]] = []
    for index, item in enumerate(profile.get("important_dates") or [], start=1):
        resolved = _next_profile_occurrence(item, today)
        if not resolved:
            continue
        occurrence, days_until = resolved
        if days_until > window_days:
            continue
        items.append(
            {
                "id": f"profile-date-{index}",
                "label": str(item.get("label") or "Önemli tarih"),
                "notes": str(item.get("notes") or "").strip(),
                "date": occurrence.isoformat(),
                "days_until": days_until,
                "recurring_annually": bool(item.get("recurring_annually", True)),
            }
        )
    items.sort(key=lambda item: (item["days_until"], item["label"]))
    return items


def sync_connected_accounts_from_settings(settings, store) -> list[dict[str, Any]]:
    accounts: list[dict[str, Any]] = []
    if settings.provider_configured:
        accounts.append(
            store.upsert_connected_account(
                settings.office_id,
                "openclaw-codex" if settings.provider_type == "openai-codex" else settings.provider_type or "model-provider",
                account_label=settings.provider_model or settings.provider_type or "Model sağlayıcısı",
                status="connected",
                scopes=["model:generate", "workspace:analyze"],
                connected_at=datetime.now(timezone.utc).isoformat(),
                manual_review_required=False,
                metadata={"provider_type": settings.provider_type, "provider_model": settings.provider_model},
            )
        )
    if settings.google_enabled or settings.google_configured:
        accounts.append(
            store.upsert_connected_account(
                settings.office_id,
                "google",
                account_label=settings.google_account_label or "Google hesabı",
                status="connected" if settings.google_configured else "pending",
                scopes=list(settings.google_scopes),
                connected_at=datetime.now(timezone.utc).isoformat() if settings.google_configured else None,
                last_sync_at=datetime.now(timezone.utc).isoformat() if settings.google_configured else None,
                manual_review_required=True,
                metadata={
                    "gmail_connected": settings.gmail_connected,
                    "calendar_connected": settings.calendar_connected,
                },
            )
        )
    if settings.telegram_enabled or settings.telegram_configured:
        accounts.append(
            store.upsert_connected_account(
                settings.office_id,
                "telegram",
                account_label=settings.telegram_bot_username or "Telegram botu",
                status="connected" if settings.telegram_configured else "pending",
                scopes=["messages:send", "messages:read"],
                connected_at=datetime.now(timezone.utc).isoformat() if settings.telegram_configured else None,
                manual_review_required=True,
                metadata={"allowed_user_id": settings.telegram_allowed_user_id},
            )
        )
    return store.list_connected_accounts(settings.office_id)


def build_assistant_inbox(store, office_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for thread in store.list_email_threads(office_id, reply_needed_only=True):
        items.append(
            {
                "id": f"email-{thread['id']}",
                "kind": "reply_needed",
                "title": thread["subject"],
                "details": thread.get("snippet") or "Yanıt bekleyen e-posta zinciri.",
                "priority": "high" if thread.get("unread_count", 0) > 0 else "medium",
                "due_at": thread.get("received_at"),
                "source_type": "email_thread",
                "source_ref": thread.get("thread_ref"),
                "matter_id": thread.get("matter_id"),
                "manual_review_required": True,
                "recommended_action_ids": [],
            }
        )
    return items


def build_assistant_agenda(store, office_id: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    for task in store.list_office_tasks(office_id):
        due_at = _parse_dt(task.get("due_at"))
        if task.get("status") == "completed":
            continue
        if due_at and due_at < now:
            items.append(
                {
                    "id": f"task-overdue-{task['id']}",
                    "kind": "overdue_task",
                    "title": f"Geciken görev: {task['title']}",
                    "details": task.get("explanation") or "Bu görev için son tarih geçmiş durumda.",
                    "priority": "high",
                    "due_at": task.get("due_at"),
                    "source_type": "task",
                    "source_ref": str(task["id"]),
                    "matter_id": task.get("matter_id"),
                    "recommended_action_ids": [],
                    "manual_review_required": True,
                }
            )
        elif due_at and due_at <= now + timedelta(days=1):
            items.append(
                {
                    "id": f"task-soon-{task['id']}",
                    "kind": "due_today",
                    "title": f"Bugün takip et: {task['title']}",
                    "details": task.get("explanation") or "Son tarih yaklaşan görev.",
                    "priority": task.get("priority") or "medium",
                    "due_at": task.get("due_at"),
                    "source_type": "task",
                    "source_ref": str(task["id"]),
                    "matter_id": task.get("matter_id"),
                    "recommended_action_ids": [],
                    "manual_review_required": True,
                }
            )

    for event in store.list_calendar_events(office_id, limit=12):
        starts_at = _parse_dt(event.get("starts_at"))
        if starts_at and starts_at <= now + timedelta(days=1):
            items.append(
                {
                    "id": f"calendar-{event['id']}",
                    "kind": "calendar_prep",
                    "title": event["title"],
                    "details": event.get("location") or "Yaklaşan takvim kaydı için hazırlık gerekebilir.",
                    "priority": "medium",
                    "due_at": event.get("starts_at"),
                    "source_type": "calendar_event",
                    "source_ref": event.get("external_id"),
                    "matter_id": event.get("matter_id"),
                    "recommended_action_ids": [],
                    "manual_review_required": True,
                }
            )

    for personal_date in _upcoming_profile_dates(store, office_id, window_days=14):
        priority = "high" if personal_date["days_until"] <= 2 else "medium"
        if personal_date["days_until"] == 0:
            details = personal_date["notes"] or "Bugün dikkat gerektiren kişisel bir tarih var."
        elif personal_date["days_until"] == 1:
            details = personal_date["notes"] or "Yarın yaklaşan kişisel bir tarih var."
        else:
            details = personal_date["notes"] or f"{personal_date['days_until']} gün içinde yaklaşan kişisel bir tarih var."
        items.append(
            {
                "id": personal_date["id"],
                "kind": "personal_date",
                "title": personal_date["label"],
                "details": details,
                "priority": priority,
                "due_at": personal_date["date"],
                "source_type": "user_profile",
                "source_ref": personal_date["label"],
                "matter_id": None,
                "recommended_action_ids": [],
                "manual_review_required": False,
            }
        )

    items.extend(build_assistant_inbox(store, office_id))
    kind_order = {
        "reply_needed": 0,
        "calendar_prep": 1,
        "personal_date": 2,
        "due_today": 3,
        "overdue_task": 4,
    }
    items.sort(
        key=lambda item: (
            kind_order.get(str(item.get("kind") or ""), 9),
            {"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority") or "medium"), 1),
            str(item.get("due_at") or ""),
        )
    )
    return items[:20]


def build_assistant_calendar(store, office_id: str, *, window_days: int = 35) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=max(7, min(window_days, 62)))
    items: list[dict[str, Any]] = []

    for event in store.list_calendar_events(office_id, limit=200):
        starts_at = _parse_dt(event.get("starts_at"))
        if not starts_at or starts_at < now - timedelta(days=1) or starts_at > window_end:
            continue
        ends_at = _parse_dt(event.get("ends_at"))
        items.append(
            {
                "id": f"calendar-{event['id']}",
                "kind": "calendar_event",
                "title": event.get("title") or "Takvim kaydı",
                "details": event.get("location") or "Takvim kaydı",
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat() if ends_at else None,
                "location": event.get("location") or "",
                "source_type": "calendar_event",
                "source_ref": event.get("external_id"),
                "matter_id": event.get("matter_id"),
                "priority": "medium",
                "all_day": "T" not in str(event.get("starts_at") or ""),
                "needs_preparation": bool(event.get("needs_preparation")),
                "provider": event.get("provider") or "lawcopilot-planner",
                "status": event.get("status") or "confirmed",
                "attendees": list(event.get("attendees") or []),
                "metadata": dict(event.get("metadata") or {}),
            }
        )

    for task in store.list_office_tasks(office_id):
        due_at = _parse_dt(task.get("due_at"))
        if task.get("status") == "completed" or not due_at:
            continue
        if due_at < now - timedelta(days=1) or due_at > window_end:
            continue
        items.append(
            {
                "id": f"task-{task['id']}",
                "kind": "task_due",
                "title": task.get("title") or "Görev",
                "details": task.get("explanation") or "Takvim içine alınmış görev",
                "starts_at": due_at.isoformat(),
                "ends_at": None,
                "location": "",
                "source_type": "task",
                "source_ref": str(task["id"]),
                "matter_id": task.get("matter_id"),
                "priority": task.get("priority") or "medium",
                "all_day": False,
                "needs_preparation": True,
                "provider": "lawcopilot",
                "status": task.get("status") or "open",
                "attendees": [],
                "metadata": {"origin_type": task.get("origin_type")},
            }
        )

    for personal_date in _upcoming_profile_dates(store, office_id, window_days=window_days):
        items.append(
            {
                "id": personal_date["id"],
                "kind": "personal_date",
                "title": personal_date["label"],
                "details": personal_date["notes"] or "Kullanıcı profilinde tanımlı önemli tarih",
                "starts_at": f"{personal_date['date']}T09:00:00+00:00",
                "ends_at": None,
                "location": "",
                "source_type": "user_profile",
                "source_ref": personal_date["label"],
                "matter_id": None,
                "priority": "medium",
                "all_day": True,
                "needs_preparation": personal_date["days_until"] <= 7,
                "provider": "user-profile",
                "status": "confirmed",
                "attendees": [],
                "metadata": {
                    "days_until": personal_date["days_until"],
                    "recurring_annually": personal_date["recurring_annually"],
                },
            }
        )

    items.sort(key=lambda item: (str(item.get("starts_at") or ""), str(item.get("title") or "")))
    return items


def build_assistant_home(store, office_id: str) -> dict[str, Any]:
    agenda = build_assistant_agenda(store, office_id)
    inbox = build_assistant_inbox(store, office_id)
    calendar = build_assistant_calendar(store, office_id, window_days=7)
    drafts = store.list_outbound_drafts(office_id)
    connected_accounts = store.list_connected_accounts(office_id)

    priority_items: list[dict[str, Any]] = []
    for item in agenda[:6]:
        priority_items.append(
            {
                "id": item["id"],
                "title": item["title"],
                "details": item.get("details") or "",
                "kind": item.get("kind") or "agenda",
                "priority": item.get("priority") or "medium",
                "due_at": item.get("due_at"),
                "source_type": item.get("source_type") or "assistant",
                "source_ref": item.get("source_ref"),
            }
        )

    requires_setup: list[dict[str, Any]] = []
    providers = {str(item.get("provider") or "") for item in connected_accounts}
    if "google" not in providers:
        requires_setup.append(
            {
                "id": "setup-google",
                "title": "Google hesabını bağlayın",
                "details": "Gmail ve Takvim sinyalleri günlük ajandaya taşınsın.",
                "action": "open_settings",
            }
        )
    if "telegram" not in providers:
        requires_setup.append(
            {
                "id": "setup-telegram",
                "title": "Telegram bağlantısını tamamlayın",
                "details": "Asistan Telegram üzerinden gelen iş akışlarını da izleyebilsin.",
                "action": "open_settings",
            }
        )

    today_summary_lines = [
        f"Bugün {len(agenda)} ajanda maddesi, {len(inbox)} cevap bekleyen iletişim ve {len([item for item in drafts if item.get('approval_status') != 'approved'])} onay bekleyen taslak var."
    ]
    if calendar:
        first_event = calendar[0]
        today_summary_lines.append(
            f"Yaklaşan ilk kayıt: {first_event.get('title')} ({first_event.get('starts_at') or 'zaman bilgisi yok'})."
        )
    if priority_items:
        today_summary_lines.append(f"Öne çıkan ilk iş: {priority_items[0]['title']}.")

    return {
        "today_summary": " ".join(today_summary_lines),
        "counts": {
            "agenda": len(agenda),
            "inbox": len(inbox),
            "drafts_pending": len([item for item in drafts if item.get("approval_status") != "approved"]),
            "calendar_today": len(calendar),
        },
        "priority_items": priority_items,
        "requires_setup": requires_setup,
        "connected_accounts": connected_accounts,
        "generated_from": "assistant_home_engine",
    }


def _risk_action_title(matter_title: str, risk_item: dict[str, Any]) -> str:
    if risk_item.get("category") == "missing_document":
        return f"{matter_title} için eksik belge talebi hazırla"
    if risk_item.get("category") == "deadline":
        return f"{matter_title} için son tarih takibini netleştir"
    return f"{matter_title} için çalışma notu hazırla"


def build_suggested_actions(store, office_id: str, *, created_by: str) -> list[dict[str, Any]]:
    existing = store.list_assistant_actions(office_id, status="suggested", limit=20)
    if existing:
        return existing

    matters = store.list_matters(office_id)[:5]
    created: list[dict[str, Any]] = []
    for matter in matters:
        tasks = store.list_matter_tasks(office_id, int(matter["id"])) or []
        open_tasks = [task for task in tasks if task.get("status") != "completed"]
        if open_tasks:
            draft = store.create_outbound_draft(
                office_id,
                matter_id=int(matter["id"]),
                draft_type="client_update",
                channel="email",
                to_contact=matter.get("client_name") or "",
                subject=f"{matter['title']} için durum güncellemesi",
                body=(
                    f"Merhaba,\n\n{matter['title']} dosyasında şu an öne çıkan başlıklar:\n"
                    + "\n".join(f"- {task['title']}" for task in open_tasks[:3])
                    + "\n\nUygun görürseniz bu güncellemeyi gözden geçirip gönderebiliriz."
                ),
                source_context={"open_tasks": [task["title"] for task in open_tasks[:5]], "documents": []},
                generated_from="assistant_agenda_engine",
                created_by=created_by,
                approval_status="pending_review",
                delivery_status="not_sent",
            )
            created.append(
                store.create_assistant_action(
                    office_id,
                    matter_id=int(matter["id"]),
                    action_type="prepare_client_update",
                    title=f"{matter['title']} için müvekkil güncellemesi hazırla",
                    description="Açık görev ve yaklaşan işler üzerinden müvekkil güncellemesi önerildi.",
                    rationale="Dosyada açık görevler bulundu; müvekkile kısa durum özeti göndermek faydalı olabilir.",
                    source_refs=[{"type": "task", "title": task["title"], "id": task["id"]} for task in open_tasks[:3]],
                    target_channel="email",
                    draft_id=int(draft["id"]),
                    status="suggested",
                    manual_review_required=True,
                    created_by=created_by,
                )
            )

        workflow_context = {
            "matter": matter,
            "notes": store.list_matter_notes(office_id, int(matter["id"])) or [],
            "documents": (store.list_matter_documents(office_id, int(matter["id"])) or [])
            + (store.list_matter_workspace_documents(office_id, int(matter["id"])) or []),
            "chunks": (store.search_document_chunks(office_id, int(matter["id"])) or [])
            + (store.search_linked_workspace_chunks(office_id, int(matter["id"])) or []),
            "tasks": tasks,
            "timeline": store.list_matter_timeline(office_id, int(matter["id"])) or [],
            "draft_events": store.list_matter_draft_events(office_id, int(matter["id"])) or [],
            "ingestion_jobs": store.list_matter_ingestion_jobs(office_id, int(matter["id"])) or [],
            "workspace_documents": store.list_matter_workspace_documents(office_id, int(matter["id"])) or [],
            "workspace_chunks": store.search_linked_workspace_chunks(office_id, int(matter["id"])) or [],
        }
        chronology = build_chronology(
            matter=matter,
            notes=workflow_context["notes"],
            chunks=workflow_context["chunks"],
            tasks=tasks,
        )
        risk_notes = build_risk_notes(
            matter=matter,
            documents=workflow_context["documents"],
            notes=workflow_context["notes"],
            tasks=tasks,
            chronology=chronology,
            chunks=workflow_context["chunks"],
        )
        if risk_notes.get("items"):
            top_item = risk_notes["items"][0]
            draft = store.create_outbound_draft(
                office_id,
                matter_id=int(matter["id"]),
                draft_type="missing_document_request" if top_item.get("category") == "missing_document" else "internal_summary",
                channel="email",
                to_contact=matter.get("client_name") or "",
                subject=_risk_action_title(matter["title"], top_item),
                body=f"{top_item['title']}\n\n{top_item['details']}",
                source_context={"risk_notes": [item["title"] for item in risk_notes["items"][:4]]},
                generated_from="assistant_risk_engine",
                created_by=created_by,
                approval_status="pending_review",
                delivery_status="not_sent",
            )
            created.append(
                store.create_assistant_action(
                    office_id,
                    matter_id=int(matter["id"]),
                    action_type="send_email",
                    title=_risk_action_title(matter["title"], top_item),
                    description=top_item["details"],
                    rationale="Risk ve eksik belge sinyalleri nedeniyle taslak aksiyon önerildi.",
                    source_refs=[{"type": "risk_note", "title": item["title"]} for item in risk_notes["items"][:3]],
                    target_channel="email",
                    draft_id=int(draft["id"]),
                    status="suggested",
                    manual_review_required=True,
                    created_by=created_by,
                )
            )
    return created or existing
