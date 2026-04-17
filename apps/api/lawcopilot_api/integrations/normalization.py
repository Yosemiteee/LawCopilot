from __future__ import annotations

import hashlib
from typing import Any

from .models import ConnectorSpec


RESOURCE_KIND_MAP = {
    "page": "documents",
    "database": "database_records",
    "block": "documents",
    "table": "database_records",
    "row": "database_records",
    "document": "documents",
    "index": "files",
    "endpoint": "files",
    "message": "messages",
    "thread": "messages",
    "event": "events",
    "task": "tasks",
    "contact": "contacts",
    "file": "files",
}


def normalize_records_to_resources(
    *,
    spec: ConnectorSpec,
    connection: dict[str, Any],
    records: list[dict[str, Any]],
    synced_at: str,
) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for record in records:
        record_type = str(record.get("record_type") or "record")
        resource_kind = RESOURCE_KIND_MAP.get(record_type, "documents")
        title = str(record.get("title") or record.get("external_id") or spec.name)
        body_text = str(record.get("text_content") or "")
        source_url = str(record.get("source_url") or "")
        normalized = dict(record.get("normalized") or {})
        attributes = {
            "connector_id": spec.id,
            "record_type": record_type,
            "access_level": connection.get("access_level"),
            **normalized,
        }
        search_text = " ".join(
            part
            for part in [
                title,
                body_text,
                str(normalized.get("summary") or ""),
                " ".join(str(tag) for tag in record.get("tags") or []),
            ]
            if part
        ).strip()
        checksum = str(record.get("content_hash") or "")
        if not checksum:
            checksum = hashlib.sha256(f"{record.get('external_id')}:{title}:{body_text}".encode("utf-8")).hexdigest()
        resources.append(
            {
                "resource_kind": resource_kind,
                "external_id": str(record.get("external_id") or ""),
                "source_record_type": record_type,
                "title": title,
                "body_text": body_text,
                "search_text": search_text,
                "source_url": source_url or None,
                "parent_external_id": str(normalized.get("parent_external_id") or "") or None,
                "owner_label": str(normalized.get("owner_label") or connection.get("display_name") or spec.name),
                "occurred_at": str(normalized.get("occurred_at") or normalized.get("event_at") or "") or None,
                "modified_at": str(normalized.get("modified_at") or synced_at),
                "checksum": checksum,
                "permissions": dict(record.get("permissions") or {}),
                "tags": list(record.get("tags") or []),
                "attributes": attributes,
                "sync_metadata": {
                    "synced_at": synced_at,
                    "connector_id": spec.id,
                    "connection_id": connection.get("id"),
                },
                "synced_at": synced_at,
            }
        )
    return resources
