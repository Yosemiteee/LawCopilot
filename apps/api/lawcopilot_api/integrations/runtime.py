from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any
from urllib.parse import urljoin

import httpx

from .models import ConnectorSpec, IntegrationActionSpec


class IntegrationRuntimeError(ValueError):
    pass


def _host_label(url: str) -> str:
    hostname = str(urlparse(str(url or "")).hostname or "").strip().lower()
    return hostname or "web"


class IntegrationExecutionRuntime:
    def __init__(
        self,
        *,
        settings,
        transport: httpx.BaseTransport | None = None,
        database_adapters: dict[str, Any] | None = None,
        web_intel: Any | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.database_adapters = database_adapters or {}
        self.web_intel = web_intel

    def validate_connection(self, *, spec: ConnectorSpec, connection: dict[str, Any], secrets: dict[str, Any]) -> dict[str, Any]:
        if spec.id == "web-watch":
            extracted = self._extract_web_page(connection=connection)
            if not bool(extracted.get("reachable")):
                raise IntegrationRuntimeError(self._safe_text(extracted.get("summary") or "Web sayfasına erişilemedi."))
            page_title = self._safe_text(extracted.get("title") or connection.get("display_name") or spec.name)
            return {
                "health_status": "valid",
                "message": f"Web sayfası doğrulandı: {page_title}",
                "metadata": {
                    "page_title": page_title,
                    "final_url": extracted.get("final_url") or extracted.get("url"),
                },
            }
        if spec.id == "notion":
            data = self._request_json(spec, connection, secrets, "GET", "/users/me")
            return {
                "health_status": "valid",
                "message": f"Notion baglantisi dogrulandi: {self._safe_text(data.get('name') or data.get('object') or spec.name)}",
                "metadata": {"subject": data},
            }
        if spec.id == "slack":
            data = self._request_json(spec, connection, secrets, "POST", "/auth.test")
            if not bool(data.get("ok")):
                raise IntegrationRuntimeError(self._provider_message("Slack", data))
            return {
                "health_status": "valid",
                "message": f"Slack workspace dogrulandi: {self._safe_text(data.get('team') or spec.name)}",
                "metadata": {"subject": data},
            }
        if spec.id == "github":
            data = self._request_json(spec, connection, secrets, "GET", "/user")
            return {
                "health_status": "valid",
                "message": f"GitHub hesabi dogrulandi: {self._safe_text(data.get('login') or spec.name)}",
                "metadata": {"subject": data},
            }
        if spec.id == "elastic":
            data = self._request_json(spec, connection, secrets, "GET", "/_cluster/health")
            return {
                "health_status": "valid",
                "message": f"Elastic cluster durumu: {self._safe_text(data.get('status') or 'unknown')}",
                "metadata": {"subject": data},
            }
        if spec.id in {"postgresql", "mysql", "mssql"}:
            adapter = self._database_adapter(spec.id)
            payload = adapter.validate_connection(connection=connection, secrets=secrets)
            return {
                "health_status": "valid",
                "message": str(payload.get("message") or f"{spec.name} baglantisi dogrulandi."),
                "metadata": payload,
            }
        probe_action = self._generic_probe_action(spec)
        path = str((probe_action.path if probe_action else None) or self._generic_action_path(connection, spec))
        method = str((probe_action.method if probe_action else None) or "GET").upper()
        data = self._request_json(spec, connection, secrets, method, path)
        items_path = (
            probe_action.response_items_path
            if probe_action and probe_action.response_items_path
            else (probe_action.response_item_path if probe_action and probe_action.response_item_path else "items")
        )
        item_count = len(self._coerce_items(data, items_path=items_path))
        return {
            "health_status": "valid",
            "message": f"{spec.name} hedefi dogrulandi.",
            "metadata": {"item_count": item_count},
        }

    def sync_connection(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        mode: str,
        cursor: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if spec.id == "web-watch":
            return self._sync_web_watch(spec=spec, connection=connection, cursor=cursor or {})
        if spec.id == "notion":
            return self._sync_notion(spec=spec, connection=connection, secrets=secrets, cursor=cursor or {})
        if spec.id == "slack":
            return self._sync_slack(spec=spec, connection=connection, secrets=secrets, cursor=cursor or {})
        if spec.id == "github":
            return self._sync_github(spec=spec, connection=connection, secrets=secrets, cursor=cursor or {})
        if spec.id == "elastic":
            return self._sync_elastic(spec=spec, connection=connection, secrets=secrets, cursor=cursor or {})
        if spec.id in {"postgresql", "mysql", "mssql"}:
            return self._sync_sql_database(spec=spec, connection=connection, secrets=secrets, cursor=cursor or {}, mode=mode)
        return self._sync_generic_rest(spec=spec, connection=connection, secrets=secrets, cursor=cursor or {})

    def execute_action(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        action: IntegrationActionSpec,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if spec.id == "web-watch":
            return self._execute_web_watch_action(spec=spec, connection=connection, action=action, payload=payload)
        if spec.id == "notion":
            return self._execute_notion_action(spec=spec, connection=connection, secrets=secrets, action=action, payload=payload)
        if spec.id == "slack":
            return self._execute_slack_action(spec=spec, connection=connection, secrets=secrets, action=action, payload=payload)
        if spec.id == "github":
            return self._execute_github_action(spec=spec, connection=connection, secrets=secrets, action=action, payload=payload)
        if spec.id == "elastic":
            return self._execute_elastic_action(spec=spec, connection=connection, secrets=secrets, action=action, payload=payload)
        if spec.id in {"postgresql", "mysql", "mssql"}:
            return self._execute_sql_database_action(spec=spec, connection=connection, secrets=secrets, action=action, payload=payload)
        return self._execute_generic_http_action(spec=spec, connection=connection, secrets=secrets, action=action, payload=payload)

    def handle_webhook(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        headers: dict[str, str],
        body: bytes,
    ) -> dict[str, Any]:
        if spec.id != "slack":
            raise IntegrationRuntimeError("webhook_not_supported_for_connector")
        self._verify_slack_signature(secrets=secrets, headers=headers, body=body)
        payload = json.loads(body.decode("utf-8") or "{}")
        event = dict(payload.get("event") or {})
        event_type = str(event.get("type") or payload.get("type") or "webhook")
        if str(payload.get("type") or "") == "url_verification":
            return {
                "status": "challenge",
                "event_id": str(payload.get("event_id") or ""),
                "event_type": "url_verification",
                "response": {"challenge": payload.get("challenge")},
                "records": [],
                "message": "Slack challenge yaniti hazirlandi.",
            }
        records: list[dict[str, Any]] = []
        if event_type == "message":
            channel_id = str(event.get("channel") or "")
            event_id = str(payload.get("event_id") or f"{channel_id}:{event.get('ts')}")
            records.append(
                {
                    "record_type": "message",
                    "external_id": event_id,
                    "title": event.get("user") or channel_id or "Slack message",
                    "text_content": str(event.get("text") or ""),
                    "content_hash": hashlib.sha256(body).hexdigest(),
                    "source_url": None,
                    "permissions": {"connector_id": spec.id, "access_level": connection.get("access_level")},
                    "tags": ["slack", "webhook", channel_id] if channel_id else ["slack", "webhook"],
                    "raw": payload,
                    "normalized": {
                        "record_type": "message",
                        "channel_id": channel_id,
                        "owner_label": connection.get("display_name") or spec.name,
                        "occurred_at": self._slack_ts_to_iso(event.get("ts")),
                        "summary": str(event.get("text") or "")[:500],
                    },
                }
            )
        return {
            "status": "processed",
            "event_id": str(payload.get("event_id") or hashlib.sha256(body).hexdigest()),
            "event_type": event_type,
            "response": {"ok": True},
            "records": records,
            "message": f"Slack webhook islendi: {event_type}",
        }

    def _sync_notion(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        cursor: dict[str, Any],
    ) -> dict[str, Any]:
        last_cursor = str(cursor.get("last_edited_time") or "")
        items = []
        max_cursor = last_cursor
        provider_cursor = str(cursor.get("provider_cursor") or "")
        page_count = 0
        while page_count < self._max_sync_pages():
            body = {"page_size": 100}
            if provider_cursor:
                body["start_cursor"] = provider_cursor
            data = self._request_json(
                spec,
                connection,
                secrets,
                "POST",
                "/search",
                json_body=body,
            )
            page_results = list(data.get("results") or [])
            for item in page_results:
                edited = str(item.get("last_edited_time") or "")
                if last_cursor and edited and edited <= last_cursor:
                    continue
                items.append(item)
                if edited and edited > max_cursor:
                    max_cursor = edited
            page_count += 1
            next_cursor = str(data.get("next_cursor") or "").strip()
            if not bool(data.get("has_more")) or not next_cursor:
                provider_cursor = ""
                break
            provider_cursor = next_cursor
        records = [self._record_from_notion_item(spec, connection, item) for item in items]
        return {
            "records": records,
            "cursor": {
                "last_edited_time": max_cursor or last_cursor,
                "provider_cursor": provider_cursor,
                "synced_at": self._utcnow_iso(),
            },
            "metadata": {
                "result_count": len(records),
                "provider": "notion",
                "page_count": page_count,
                "has_more": bool(provider_cursor),
            },
        }

    def _sync_web_watch(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        cursor: dict[str, Any],
    ) -> dict[str, Any]:
        extracted = self._extract_web_page(connection=connection)
        if not bool(extracted.get("reachable")):
            raise IntegrationRuntimeError(self._safe_text(extracted.get("summary") or "İzlenen sayfa okunamadı."))
        content = self._web_watch_text(extracted)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        previous_hash = str(cursor.get("content_hash") or "")
        changed = content_hash != previous_hash
        synced_at = self._utcnow_iso()
        page_title = self._safe_text(extracted.get("title") or connection.get("display_name") or spec.name)
        url = str(extracted.get("final_url") or extracted.get("url") or connection.get("config", {}).get("url") or "")
        summary = self._web_watch_summary(extracted=extracted, connection=connection, changed=changed)
        record = {
            "record_type": "document",
            "external_id": f"web-watch:{connection.get('id')}",
            "title": page_title,
            "text_content": content,
            "content_hash": content_hash,
            "source_url": url or None,
            "permissions": {"connector_id": spec.id, "access_level": connection.get("access_level")},
            "tags": ["web-watch", _host_label(url), "changed" if changed else "unchanged"],
            "raw": extracted,
            "normalized": {
                "record_type": "document",
                "owner_label": connection.get("display_name") or page_title,
                "summary": summary,
                "modified_at": synced_at,
                "watch_label": str(connection.get("config", {}).get("watch_label") or connection.get("display_name") or page_title),
            },
        }
        return {
            "records": [record],
            "cursor": {
                "content_hash": content_hash,
                "synced_at": synced_at,
                "last_changed_at": synced_at if changed or not previous_hash else cursor.get("last_changed_at"),
                "page_title": page_title,
                "url": url,
            },
            "metadata": {
                "provider": "web-watch",
                "changed_count": 1 if changed else 0,
                "change_detected": bool(changed),
                "page_title": page_title,
                "summary": summary,
                "watch_url": url,
                "status_message": summary,
            },
        }

    def _sync_slack(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        cursor: dict[str, Any],
    ) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        latest_ts = str(cursor.get("latest_message_ts") or "")
        max_ts = latest_ts
        partial_failures: list[str] = []
        channels: list[dict[str, Any]] = []
        channel_cursor = ""
        channel_page_count = 0
        while channel_page_count < self._max_sync_pages():
            channel_payload = self._request_json(
                spec,
                connection,
                secrets,
                "GET",
                "/conversations.list",
                params={
                    "limit": 200,
                    "types": "public_channel,private_channel",
                    **({"cursor": channel_cursor} if channel_cursor else {}),
                },
            )
            page_channels = [dict(item) for item in list(channel_payload.get("channels") or []) if isinstance(item, dict)]
            channels.extend(page_channels)
            channel_page_count += 1
            next_cursor = str(self._get_path(channel_payload, "response_metadata.next_cursor") or "").strip()
            if not next_cursor or next_cursor == channel_cursor:
                break
            channel_cursor = next_cursor
        history_page_limit = max(1, min(3, self._max_sync_pages()))
        for channel in channels[:50]:
            channel_id = str(channel.get("id") or "")
            if not channel_id:
                continue
            records.append(self._record_from_slack_channel(spec, connection, channel))
            history_cursor = ""
            history_page_count = 0
            while history_page_count < history_page_limit:
                history_params = {"channel": channel_id, "limit": 200}
                if latest_ts:
                    history_params["oldest"] = latest_ts
                if history_cursor:
                    history_params["cursor"] = history_cursor
                try:
                    history = self._request_json(
                        spec,
                        connection,
                        secrets,
                        "GET",
                        "/conversations.history",
                        params=history_params,
                    )
                except IntegrationRuntimeError as exc:
                    partial_failures.append(f"{channel_id}: {exc}")
                    break
                for message in list(history.get("messages") or []):
                    ts = str(message.get("ts") or "")
                    if ts and ts > max_ts:
                        max_ts = ts
                    records.append(self._record_from_slack_message(spec, connection, channel, message))
                history_page_count += 1
                next_history_cursor = str(self._get_path(history, "response_metadata.next_cursor") or "").strip()
                if not next_history_cursor or next_history_cursor == history_cursor:
                    break
                history_cursor = next_history_cursor
        return {
            "records": records,
            "cursor": {
                "latest_message_ts": max_ts or latest_ts,
                "synced_at": self._utcnow_iso(),
            },
            "metadata": {
                "channel_count": len(channels),
                "provider": "slack",
                "channel_page_count": channel_page_count,
                "partial_failure_count": len(partial_failures),
                "partial_failures": partial_failures[:10],
            },
        }

    def _sync_github(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        cursor: dict[str, Any],
    ) -> dict[str, Any]:
        last_updated = str(cursor.get("updated_at") or "")
        records: list[dict[str, Any]] = []
        max_updated = last_updated
        page = max(1, int(cursor.get("page") or 1))
        page_count = 0
        while page_count < self._max_sync_pages():
            data = self._request_json(spec, connection, secrets, "GET", "/user/repos", params={"per_page": 100, "page": page})
            page_items = self._coerce_items(data)
            for repo in page_items:
                updated_at = str(repo.get("updated_at") or "")
                if last_updated and updated_at and updated_at <= last_updated:
                    continue
                if updated_at and updated_at > max_updated:
                    max_updated = updated_at
                records.append(self._record_from_github_repo(spec, connection, repo))
            page_count += 1
            if len(page_items) < 100:
                break
            page += 1
        return {
            "records": records,
            "cursor": {"updated_at": max_updated or last_updated, "page": page, "synced_at": self._utcnow_iso()},
            "metadata": {"provider": "github", "page_count": page_count},
        }

    def _sync_elastic(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        cursor: dict[str, Any],
    ) -> dict[str, Any]:
        index_pattern = self._elastic_index_pattern(connection)
        cursor_field = str(spec.sync_policies[0].cursor_field or "@timestamp") if spec.sync_policies else "@timestamp"
        last_value = str(cursor.get("last_value") or "")
        query: dict[str, Any] = {"size": max(1, min(100, self._elastic_result_size(connection, fallback=100))), "sort": [{cursor_field: {"order": "asc"}}], "query": {"match_all": {}}}
        if last_value:
            query["query"] = {"range": {cursor_field: {"gt": last_value}}}
        payload = self._request_json(spec, connection, secrets, "POST", f"/{index_pattern}/_search", json_body=query)
        records: list[dict[str, Any]] = []
        max_value = last_value
        for hit in list(payload.get("hits", {}).get("hits") or []):
            source = dict(hit.get("_source") or {})
            modified = str(source.get(cursor_field) or "")
            if modified and modified > max_value:
                max_value = modified
            records.append(self._record_from_elastic_hit(spec, connection, hit))
        return {
            "records": records,
            "cursor": {"last_value": max_value or last_value, "cursor_field": cursor_field, "synced_at": self._utcnow_iso()},
            "metadata": {"provider": "elastic", "index_pattern": index_pattern},
        }

    def _sync_sql_database(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        cursor: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        adapter = self._database_adapter(spec.id)
        config = dict(connection.get("config") or {})
        schema = self._sql_schema(spec.id, connection)
        allowlist = self._split_lines(config.get("table_allowlist") or "")
        tables = allowlist or adapter.list_tables(connection=connection, secrets=secrets, schema=schema)
        records: list[dict[str, Any]] = []
        last_seen = str(cursor.get("last_seen") or "")
        max_seen = last_seen
        for table_name in tables[:10]:
            safe_table = self._safe_identifier(table_name, field_name="table")
            cursor_column = adapter.detect_cursor_column(connection=connection, secrets=secrets, schema=schema, table=safe_table)
            rows = adapter.fetch_rows(
                connection=connection,
                secrets=secrets,
                schema=schema,
                table=safe_table,
                limit=100,
                cursor_column=cursor_column,
                cursor_value=last_seen if mode == "incremental" else None,
            )
            records.append(self._record_from_table(spec, connection, schema=schema, table=safe_table))
            for row in rows:
                seen_value = str(row.get(cursor_column) or "") if cursor_column else ""
                if seen_value and seen_value > max_seen:
                    max_seen = seen_value
                records.append(self._record_from_row(spec, connection, table=safe_table, row=row))
        return {
            "records": records,
            "cursor": {"last_seen": max_seen or last_seen, "synced_at": self._utcnow_iso()},
            "metadata": {"provider": spec.id, "table_count": len(tables)},
        }

    def _sync_generic_rest(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        cursor: dict[str, Any],
    ) -> dict[str, Any]:
        action = next((item for item in spec.actions if item.operation in {"list_items", "search", "fetch_documents", "read_messages"}), None)
        if action is None:
            action = next((item for item in spec.actions if item.operation == "get_item"), None)
        if action is None:
            action = IntegrationActionSpec(
                key="list_items",
                title="Listele",
                description="Varsayilan listeleme aksiyonu",
                operation="list_items",
            )
        path = str(action.path or self._generic_action_path(connection, spec))
        items_path = action.response_items_path or action.response_item_path or spec.pagination_strategy.items_path or "items"
        method = action.method or "GET"
        items: list[dict[str, Any]] = []
        cursor_state = dict(cursor or {})
        page_count = 0
        page_size = 100
        while page_count < self._max_sync_pages():
            params = dict(self._query_from_action(action, {}))
            json_body: dict[str, Any] | None = None
            if spec.pagination_strategy.page_size_param:
                if method.upper() == "GET":
                    params[spec.pagination_strategy.page_size_param] = page_size
                else:
                    json_body = {spec.pagination_strategy.page_size_param: page_size}
            if spec.pagination_strategy.type == "cursor" and spec.pagination_strategy.cursor_param and cursor_state.get("cursor"):
                if method.upper() == "GET":
                    params[str(spec.pagination_strategy.cursor_param)] = cursor_state.get("cursor")
                else:
                    json_body = {**dict(json_body or {}), str(spec.pagination_strategy.cursor_param): cursor_state.get("cursor")}
            elif spec.pagination_strategy.type == "page" and spec.pagination_strategy.page_param:
                params[str(spec.pagination_strategy.page_param)] = int(cursor_state.get("page") or 1)
            elif spec.pagination_strategy.type == "offset" and spec.pagination_strategy.page_param:
                params[str(spec.pagination_strategy.page_param)] = int(cursor_state.get("offset") or 0)
            data = self._request_json(
                spec,
                connection,
                secrets,
                method,
                path,
                params=params or None,
                json_body=json_body,
            )
            page_items = self._coerce_items(data, items_path=items_path)
            items.extend(page_items)
            page_count += 1
            if not self._advance_pagination_state(spec=spec, cursor_state=cursor_state, payload=data, page_item_count=len(page_items), page_size=page_size):
                break
        records = [self._record_from_generic_item(spec, connection, item) for item in items]
        return {
            "records": records,
            "cursor": {**cursor_state, "synced_at": self._utcnow_iso()},
            "metadata": {"provider": "generic-http", "item_count": len(records), "page_count": page_count},
        }

    def _execute_notion_action(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        action: IntegrationActionSpec,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if action.operation == "search":
            items: list[dict[str, Any]] = []
            next_cursor = ""
            page_count = 0
            while page_count < self._max_sync_pages():
                body = {"query": payload.get("query") or "", "page_size": 100}
                if next_cursor:
                    body["start_cursor"] = next_cursor
                data = self._request_json(spec, connection, secrets, "POST", "/search", json_body=body)
                items.extend(self._record_from_notion_item(spec, connection, item) for item in list(data.get("results") or []))
                page_count += 1
                next_cursor = str(data.get("next_cursor") or "").strip()
                if not bool(data.get("has_more")) or not next_cursor:
                    break
            return {"items": items, "count": len(items), "generated_from": "provider_http"}
        if action.operation == "get_item":
            external_id = str(payload.get("external_id") or payload.get("page_id") or "")
            if not external_id:
                raise IntegrationRuntimeError("notion_external_id_required")
            path = f"/pages/{external_id}"
            if str(payload.get("kind") or "").lower() == "database":
                path = f"/databases/{external_id}"
            item = self._request_json(spec, connection, secrets, "GET", path)
            return {"item": self._record_from_notion_item(spec, connection, item), "generated_from": "provider_http"}
        if action.operation == "create_page":
            body = payload if payload else {}
            item = self._request_json(spec, connection, secrets, "POST", "/pages", json_body=body)
            return {"item": self._record_from_notion_item(spec, connection, item), "generated_from": "provider_http"}
        if action.operation == "append_block":
            block_id = str(payload.get("external_id") or payload.get("block_id") or "")
            children = list(payload.get("children") or payload.get("blocks") or [])
            if not block_id or not children:
                raise IntegrationRuntimeError("notion_block_id_and_children_required")
            data = self._request_json(
                spec,
                connection,
                secrets,
                "PATCH",
                f"/blocks/{block_id}/children",
                json_body={"children": children},
            )
            return {"item": data, "generated_from": "provider_http"}
        if action.operation == "update":
            external_id = str(payload.get("external_id") or payload.get("page_id") or "")
            if not external_id:
                raise IntegrationRuntimeError("notion_external_id_required")
            data = self._request_json(spec, connection, secrets, "PATCH", f"/pages/{external_id}", json_body=payload)
            return {"item": self._record_from_notion_item(spec, connection, data), "generated_from": "provider_http"}
        return self._execute_generic_http_action(spec=spec, connection=connection, secrets=secrets, action=action, payload=payload)

    def _execute_web_watch_action(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        action: IntegrationActionSpec,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        extracted = self._extract_web_page(connection=connection)
        if not bool(extracted.get("reachable")):
            raise IntegrationRuntimeError(self._safe_text(extracted.get("summary") or "İzlenen sayfa okunamadı."))
        page_title = self._safe_text(extracted.get("title") or connection.get("display_name") or spec.name)
        item = {
            "title": page_title,
            "summary": self._web_watch_summary(extracted=extracted, connection=connection, changed=True),
            "url": extracted.get("final_url") or extracted.get("url"),
            "visible_text": self._safe_text(extracted.get("visible_text") or "", limit=6000),
            "headings": list(extracted.get("headings") or []),
            "render_mode": extracted.get("render_mode"),
        }
        if action.operation == "search":
            query = self._safe_text(payload.get("query") or "")
            text = f"{item['title']} {item['summary']} {item['visible_text']}".lower()
            matches = bool(query) and query.lower() in text
            return {
                "items": [item] if matches else [],
                "count": 1 if matches else 0,
                "generated_from": "web_watch_runtime",
            }
        return {"item": item, "generated_from": "web_watch_runtime"}

    def _execute_slack_action(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        action: IntegrationActionSpec,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if action.operation in {"read_messages", "search"}:
            channel = str(payload.get("channel") or payload.get("channel_id") or "")
            limit = max(1, min(200, int(payload.get("limit") or 100)))
            params = {"limit": limit}
            if channel:
                items: list[dict[str, Any]] = []
                next_cursor = ""
                page_count = 0
                while page_count < self._max_sync_pages():
                    request_params = {**params, "channel": channel}
                    if next_cursor:
                        request_params["cursor"] = next_cursor
                    data = self._request_json(spec, connection, secrets, "GET", "/conversations.history", params=request_params)
                    items.extend(
                        self._record_from_slack_message(spec, connection, {"id": channel}, item)
                        for item in list(data.get("messages") or [])
                    )
                    page_count += 1
                    next_cursor = str(self._get_path(data, "response_metadata.next_cursor") or "").strip()
                    if not next_cursor:
                        break
            else:
                items = []
                next_cursor = ""
                page_count = 0
                while page_count < self._max_sync_pages():
                    request_params = {"limit": limit}
                    if next_cursor:
                        request_params["cursor"] = next_cursor
                    data = self._request_json(spec, connection, secrets, "GET", "/conversations.list", params=request_params)
                    items.extend(self._record_from_slack_channel(spec, connection, item) for item in list(data.get("channels") or []))
                    page_count += 1
                    next_cursor = str(self._get_path(data, "response_metadata.next_cursor") or "").strip()
                    if not next_cursor:
                        break
            if action.operation == "search" and payload.get("query"):
                query = self._safe_text(payload.get("query"))
                items = [item for item in items if query.lower() in self._safe_text(item.get("text_content") or item.get("title") or "").lower()]
            return {"items": items, "count": len(items), "generated_from": "provider_http"}
        if action.operation == "send_message":
            channel = str(payload.get("channel") or payload.get("channel_id") or "")
            text = str(payload.get("text") or payload.get("message") or "")
            if not channel or not text:
                raise IntegrationRuntimeError("slack_channel_and_text_required")
            data = self._request_json(spec, connection, secrets, "POST", "/chat.postMessage", json_body={"channel": channel, "text": text})
            if not bool(data.get("ok")):
                raise IntegrationRuntimeError(self._provider_message("Slack", data))
            return {"item": data, "generated_from": "provider_http"}
        return self._execute_generic_http_action(spec=spec, connection=connection, secrets=secrets, action=action, payload=payload)

    def _execute_github_action(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        action: IntegrationActionSpec,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if action.operation == "list_items":
            data = self._request_json(spec, connection, secrets, "GET", "/user/repos", params={"per_page": 100, "page": 1})
            items = [self._record_from_github_repo(spec, connection, repo) for repo in self._coerce_items(data)]
            return {"items": items, "count": len(items), "generated_from": "provider_http"}
        if action.operation == "get_item":
            owner = str(payload.get("owner") or "")
            repo = str(payload.get("repo") or payload.get("name") or "")
            if not owner or not repo:
                raise IntegrationRuntimeError("github_owner_and_repo_required")
            item = self._request_json(spec, connection, secrets, "GET", f"/repos/{owner}/{repo}")
            return {"item": self._record_from_github_repo(spec, connection, item), "generated_from": "provider_http"}
        if action.operation == "search":
            query = str(payload.get("query") or "").strip()
            data = self._request_json(spec, connection, secrets, "GET", "/search/repositories", params={"q": query, "per_page": 50})
            items = [self._record_from_github_repo(spec, connection, repo) for repo in list(data.get("items") or [])]
            return {"items": items, "count": len(items), "generated_from": "provider_http", "query": query}
        if action.operation == "create":
            owner = str(payload.get("owner") or "")
            repo = str(payload.get("repo") or "")
            title = str(payload.get("title") or "")
            if not owner or not repo or not title:
                raise IntegrationRuntimeError("github_issue_fields_required")
            item = self._request_json(
                spec,
                connection,
                secrets,
                "POST",
                f"/repos/{owner}/{repo}/issues",
                json_body={"title": title, "body": payload.get("body")},
            )
            return {"item": item, "generated_from": "provider_http"}
        if action.operation == "update":
            owner = str(payload.get("owner") or "")
            repo = str(payload.get("repo") or "")
            issue_number = payload.get("issue_number")
            if not owner or not repo or not issue_number:
                raise IntegrationRuntimeError("github_issue_update_fields_required")
            item = self._request_json(
                spec,
                connection,
                secrets,
                "PATCH",
                f"/repos/{owner}/{repo}/issues/{issue_number}",
                json_body={key: value for key, value in payload.items() if key not in {"owner", "repo", "issue_number"}},
            )
            return {"item": item, "generated_from": "provider_http"}
        return self._execute_generic_http_action(spec=spec, connection=connection, secrets=secrets, action=action, payload=payload)

    def _execute_elastic_action(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        action: IntegrationActionSpec,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        index_pattern = str(payload.get("index") or self._elastic_index_pattern(connection))
        if action.operation in {"search", "run_query"}:
            body = self._elastic_query_body(connection=connection, payload=payload, operation=action.operation)
            data = self._request_json(spec, connection, secrets, "POST", f"/{index_pattern}/_search", json_body=body)
            items = [self._record_from_elastic_hit(spec, connection, hit) for hit in list(data.get("hits", {}).get("hits") or [])]
            return {
                "items": items,
                "count": len(items),
                "raw": data,
                "query_body": body,
                "generated_from": "provider_http",
            }
        if action.operation == "run_sql":
            query = self._elastic_sql_query(payload)
            fetch_size = self._elastic_sql_fetch_size(payload, fallback=self._elastic_result_size(connection))
            body: dict[str, Any] = {
                "query": query,
                "fetch_size": fetch_size,
            }
            if isinstance(payload.get("filter"), dict):
                body["filter"] = dict(payload.get("filter") or {})
            data = self._request_json(spec, connection, secrets, "POST", "/_sql", json_body=body)
            items = self._elastic_sql_rows(data)
            return {
                "items": items,
                "count": len(items),
                "raw": data,
                "sql_query": query,
                "generated_from": "provider_http",
            }
        if action.operation == "get_item":
            external_id = str(payload.get("external_id") or payload.get("id") or "")
            index = str(payload.get("index") or index_pattern)
            item = self._request_json(spec, connection, secrets, "GET", f"/{index}/_doc/{external_id}")
            return {"item": self._record_from_elastic_hit(spec, connection, item), "generated_from": "provider_http"}
        if action.operation == "insert_record":
            index = str(payload.get("index") or index_pattern)
            item = self._request_json(spec, connection, secrets, "POST", f"/{index}/_doc", json_body=payload.get("document") or payload)
            return {"item": item, "generated_from": "provider_http"}
        if action.operation == "update_record":
            index = str(payload.get("index") or index_pattern)
            external_id = str(payload.get("external_id") or payload.get("id") or "")
            item = self._request_json(
                spec,
                connection,
                secrets,
                "POST",
                f"/{index}/_update/{external_id}",
                json_body={"doc": payload.get("document") or payload.get("doc") or {}},
            )
            return {"item": item, "generated_from": "provider_http"}
        if action.operation == "delete":
            index = str(payload.get("index") or index_pattern)
            external_id = str(payload.get("external_id") or payload.get("id") or "")
            item = self._request_json(spec, connection, secrets, "DELETE", f"/{index}/_doc/{external_id}")
            return {"item": item, "generated_from": "provider_http"}
        return self._execute_generic_http_action(spec=spec, connection=connection, secrets=secrets, action=action, payload=payload)

    def _execute_sql_database_action(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        action: IntegrationActionSpec,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        adapter = self._database_adapter(spec.id)
        schema = self._sql_schema(spec.id, connection)
        if action.operation == "list_databases":
            tables = adapter.list_tables(connection=connection, secrets=secrets, schema=schema)
            items = [{"schema": schema, "table": table} for table in tables]
            return {"items": items, "count": len(items), "generated_from": "provider_db"}
        if action.operation == "run_query":
            query = str(payload.get("query") or "").strip()
            rows = adapter.run_query(connection=connection, secrets=secrets, query=query, params=payload.get("params") or [])
            return {"items": rows, "count": len(rows), "generated_from": "provider_db"}
        table = self._safe_identifier(payload.get("table") or "", field_name="table")
        if action.operation == "insert_record":
            return {"item": adapter.insert_record(connection=connection, secrets=secrets, schema=schema, table=table, data=dict(payload.get("record") or {})), "generated_from": "provider_db"}
        if action.operation == "update_record":
            return {
                "item": adapter.update_record(
                    connection=connection,
                    secrets=secrets,
                    schema=schema,
                    table=table,
                    data=dict(payload.get("record") or {}),
                    where=dict(payload.get("where") or {}),
                ),
                "generated_from": "provider_db",
            }
        if action.operation == "delete":
            return {
                "item": adapter.delete_record(
                    connection=connection,
                    secrets=secrets,
                    schema=schema,
                    table=table,
                    where=dict(payload.get("where") or {}),
                ),
                "generated_from": "provider_db",
            }
        raise IntegrationRuntimeError(f"unsupported_{spec.id}_operation:{action.operation}")

    def _execute_generic_http_action(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        action: IntegrationActionSpec,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        method = action.method or self._default_method_for_operation(action.operation)
        path = action.path or self._generic_action_path(connection, spec, payload=payload)
        params = self._query_from_action(action, payload)
        json_body: dict[str, Any] | None = None
        if method in {"POST", "PUT", "PATCH"}:
            json_body = dict(payload or {})
        data = self._request_json(spec, connection, secrets, method, path, params=params or None, json_body=json_body)
        if action.operation in {"list_items", "search", "read_messages", "fetch_documents", "list_databases", "run_query"}:
            items_path = action.response_items_path or spec.pagination_strategy.items_path or "items"
            items = self._coerce_items(data, items_path=items_path)
            normalized = [self._record_from_generic_item(spec, connection, item) for item in items]
            return {"items": normalized, "count": len(normalized), "generated_from": "provider_http"}
        if action.operation in {"get_item", "download_file"}:
            item_path = action.response_item_path or "item"
            item = self._get_path(data, item_path) if item_path else data
            return {"item": item, "generated_from": "provider_http"}
        return {"item": data, "generated_from": "provider_http"}

    def _request_json(
        self,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
        form_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        request_headers = self._build_headers(spec=spec, connection=connection, secrets=secrets)
        request_headers.update(headers or {})
        url = self._absolute_url(connection, spec, path)
        timeout_seconds = float(getattr(self.settings, "connector_http_timeout_seconds", 20))
        max_retries = int(getattr(self.settings, "connector_http_max_retries", 2))
        max_backoff = float(getattr(self.settings, "connector_http_backoff_max_seconds", 4))
        with httpx.Client(transport=self.transport, timeout=timeout_seconds, follow_redirects=True) as client:
            last_error: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    response = client.request(
                        method.upper(),
                        url,
                        headers=request_headers,
                        params=params,
                        json=json_body,
                        data=form_body,
                    )
                except httpx.HTTPError as exc:
                    last_error = exc
                    if attempt >= max_retries:
                        raise IntegrationRuntimeError(f"http_transport_error:{exc}") from exc
                    time.sleep(min(max_backoff, 0.25 * (2**attempt)))
                    continue
                if self._retryable_status(response.status_code) and attempt < max_retries:
                    delay = self._retry_delay_seconds(response=response, attempt=attempt, max_backoff=max_backoff)
                    time.sleep(delay)
                    continue
                if response.status_code >= 400:
                    raise IntegrationRuntimeError(self._normalize_http_error(spec.name, response))
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type or response.text.strip().startswith(("{", "[")):
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise IntegrationRuntimeError(f"invalid_json_response:{spec.id}") from exc
                    provider_error = self._provider_payload_error(spec, payload)
                    if provider_error:
                        raise IntegrationRuntimeError(provider_error)
                    return payload
                return {"body": response.text, "status_code": response.status_code}
        if last_error:
            raise IntegrationRuntimeError(f"http_transport_error:{last_error}") from last_error
        raise IntegrationRuntimeError("http_request_failed")

    def _build_headers(self, *, spec: ConnectorSpec, connection: dict[str, Any], secrets: dict[str, Any]) -> dict[str, str]:
        headers = {"User-Agent": "LawCopilot-IntegrationRuntime/1.0"}
        config = dict(connection.get("config") or {})
        if spec.id == "notion":
            token = str(secrets.get("integration_token") or secrets.get("bearer_token") or "").strip()
            if not token:
                raise IntegrationRuntimeError("notion_token_missing")
            headers["Authorization"] = f"Bearer {token}"
            headers["Notion-Version"] = str(config.get("notion_version") or "2022-06-28")
        elif spec.id == "slack":
            token = str(secrets.get("oauth_access_token") or secrets.get("access_token") or "").strip()
            if not token:
                raise IntegrationRuntimeError("oauth_access_token_missing")
            headers["Authorization"] = f"Bearer {token}"
        elif spec.id == "github":
            token = str(secrets.get("oauth_access_token") or secrets.get("access_token") or "").strip()
            if not token:
                raise IntegrationRuntimeError("oauth_access_token_missing")
            headers["Authorization"] = f"Bearer {token}"
            headers["Accept"] = "application/vnd.github+json"
        elif spec.id == "elastic":
            api_key = str(secrets.get("api_key") or "").strip()
            api_key_id = str(config.get("api_key_id") or "").strip()
            api_key_secret = str(secrets.get("api_key_secret") or "").strip()
            username = str(config.get("username") or "").strip()
            password = str(secrets.get("password") or "").strip()
            if api_key:
                headers["Authorization"] = f"ApiKey {api_key}"
            elif api_key_id and api_key_secret:
                token = base64.b64encode(f"{api_key_id}:{api_key_secret}".encode("utf-8")).decode("ascii")
                headers["Authorization"] = f"ApiKey {token}"
            elif username and password:
                token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
                headers["Authorization"] = f"Basic {token}"
            else:
                raise IntegrationRuntimeError("elastic_credentials_missing")
        elif spec.auth_type == "oauth2":
            token = str(secrets.get("oauth_access_token") or secrets.get("access_token") or "").strip()
            if not token:
                raise IntegrationRuntimeError("oauth_access_token_missing")
            headers["Authorization"] = f"Bearer {token}"
        elif spec.auth_type == "bearer":
            token = str(secrets.get("bearer_token") or secrets.get("integration_token") or "").strip()
            if not token:
                raise IntegrationRuntimeError("bearer_token_missing")
            headers["Authorization"] = f"Bearer {token}"
        elif spec.auth_type == "api_key":
            api_key = str(secrets.get("api_key") or "").strip()
            header_name = str(config.get("api_key_header") or "X-API-Key").strip()
            if not api_key:
                raise IntegrationRuntimeError("api_key_missing")
            headers[header_name] = api_key
        elif spec.auth_type == "multi":
            auth_mode = str(config.get("auth_mode") or "api_key").strip()
            if auth_mode == "api_key":
                api_key = str(secrets.get("api_key") or "").strip()
                if not api_key:
                    raise IntegrationRuntimeError("api_key_missing")
                headers[str(config.get("api_key_header") or "X-API-Key")] = api_key
            elif auth_mode == "bearer":
                token = str(secrets.get("bearer_token") or "").strip()
                if not token:
                    raise IntegrationRuntimeError("bearer_token_missing")
                headers["Authorization"] = f"Bearer {token}"
            elif auth_mode == "basic":
                username = str(config.get("username") or "").strip()
                password = str(secrets.get("password") or "").strip()
                if not username or not password:
                    raise IntegrationRuntimeError("basic_auth_credentials_missing")
                token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
                headers["Authorization"] = f"Basic {token}"
        return headers

    def _extract_web_page(self, *, connection: dict[str, Any]) -> dict[str, Any]:
        if self.web_intel is None:
            raise IntegrationRuntimeError("web_watch_runtime_unavailable")
        config = dict(connection.get("config") or {})
        url = str(config.get("url") or "").strip()
        if not url:
            raise IntegrationRuntimeError("web_watch_url_missing")
        render_mode = str(config.get("render_mode") or "auto").strip() or "auto"
        try:
            return dict(self.web_intel.extract(url=url, render_mode=render_mode, include_screenshot=False) or {})
        except ValueError as exc:
            raise IntegrationRuntimeError(str(exc)) from exc

    def _web_watch_text(self, extracted: dict[str, Any]) -> str:
        parts = [
            self._safe_text(extracted.get("title") or ""),
            self._safe_text(extracted.get("meta_description") or "", limit=500),
            " | ".join(str(item) for item in list(extracted.get("headings") or [])[:8]),
            self._safe_text(extracted.get("visible_text") or "", limit=8000),
        ]
        return "\n\n".join(part for part in parts if part).strip()

    def _web_watch_summary(self, *, extracted: dict[str, Any], connection: dict[str, Any], changed: bool) -> str:
        config = dict(connection.get("config") or {})
        focus = self._safe_text(config.get("summary_focus") or "", limit=240)
        title = self._safe_text(extracted.get("title") or connection.get("display_name") or "İzlenen sayfa")
        prefix = f"{title} sayfasında yeni değişiklik bulundu." if changed else f"{title} sayfasında yeni değişiklik görünmüyor."
        base = self._safe_text(extracted.get("summary") or "", limit=420)
        if focus:
            return self._safe_text(f"{prefix} {base} Odak: {focus}", limit=520)
        return self._safe_text(f"{prefix} {base}", limit=520)

    def _elastic_index_pattern(self, connection: dict[str, Any]) -> str:
        return str(connection.get("config", {}).get("index_pattern") or "cases-*").strip() or "cases-*"

    def _elastic_result_size(self, connection: dict[str, Any], *, fallback: int = 10) -> int:
        raw_value = connection.get("config", {}).get("result_size")
        try:
            parsed = int(raw_value)
        except (TypeError, ValueError):
            return fallback
        return max(1, min(200, parsed))

    def _elastic_search_fields(self, connection: dict[str, Any]) -> list[str]:
        raw = str(connection.get("config", {}).get("search_fields") or "").strip()
        if not raw:
            return []
        fields = [item.strip() for item in raw.replace("\n", ",").split(",")]
        return [item for item in fields if item]

    def _elastic_cloud_base_url(self, cloud_id: str) -> str | None:
        value = str(cloud_id or "").strip()
        if not value or ":" not in value:
            return None
        _, encoded = value.split(":", 1)
        padded = encoded + ("=" * (-len(encoded) % 4))
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
        parts = decoded.split("$")
        if len(parts) < 2:
            return None
        host = str(parts[0] or "").strip()
        es_cluster = str(parts[1] or "").strip()
        if not host or not es_cluster:
            return None
        return f"https://{es_cluster}.{host}"

    def _elastic_query_body(
        self,
        *,
        connection: dict[str, Any],
        payload: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        raw_query = payload.get("query")
        if isinstance(raw_query, dict):
            body = dict(raw_query)
        elif operation == "run_query" and isinstance(payload.get("body"), dict):
            body = dict(payload.get("body") or {})
        elif isinstance(payload.get("dsl"), dict):
            body = dict(payload.get("dsl") or {})
        else:
            query_text = str(raw_query or payload.get("text") or "*").strip() or "*"
            fields = self._elastic_search_fields(connection)
            query_clause: dict[str, Any]
            if fields and query_text not in {"*", ""}:
                query_clause = {
                    "multi_match": {
                        "query": query_text,
                        "fields": fields,
                        "type": "best_fields",
                    }
                }
            else:
                query_clause = {"query_string": {"query": query_text}}
            body = {
                "query": query_clause,
                "size": self._elastic_result_size(connection),
            }
        if "size" not in body:
            body["size"] = self._elastic_result_size(connection)
        return body

    def _elastic_sql_query(self, payload: dict[str, Any]) -> str:
        raw_query = str(payload.get("query") or payload.get("sql") or "").strip()
        if not raw_query:
            raise IntegrationRuntimeError("elastic_sql_query_required")
        normalized = raw_query.rstrip().rstrip(";").strip()
        if not normalized:
            raise IntegrationRuntimeError("elastic_sql_query_required")
        if ";" in normalized:
            raise IntegrationRuntimeError("elastic_sql_multiple_statements_not_allowed")
        if not self._is_safe_elastic_sql(normalized):
            raise IntegrationRuntimeError("elastic_sql_not_allowed")
        return normalized

    def _elastic_sql_fetch_size(self, payload: dict[str, Any], *, fallback: int = 10) -> int:
        raw_value = payload.get("fetch_size") or payload.get("size") or fallback
        try:
            parsed = int(raw_value)
        except (TypeError, ValueError):
            return max(1, min(500, fallback))
        return max(1, min(500, parsed))

    def _is_safe_elastic_sql(self, query: str) -> bool:
        first_token = re.match(r"^\s*([a-zA-Z_]+)", str(query or ""))
        if not first_token:
            return False
        operation = first_token.group(1).lower()
        return operation in {"select", "show", "describe", "desc", "explain"}

    def _elastic_sql_rows(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        columns = [dict(item) for item in list(payload.get("columns") or []) if isinstance(item, dict)]
        column_names = [str(item.get("name") or f"column_{index + 1}") for index, item in enumerate(columns)]
        items: list[dict[str, Any]] = []
        for row in list(payload.get("rows") or []):
            if isinstance(row, list):
                items.append({column_names[index] if index < len(column_names) else f"column_{index + 1}": value for index, value in enumerate(row)})
        return items

    def _absolute_url(self, connection: dict[str, Any], spec: ConnectorSpec, path: str) -> str:
        config = dict(connection.get("config") or {})
        base_url = str(config.get("base_url") or spec.base_url or "").strip()
        if spec.id == "elastic" and not base_url:
            base_url = str(self._elastic_cloud_base_url(str(config.get("cloud_id") or "")) or "").strip()
        if not base_url:
            raise IntegrationRuntimeError("base_url_missing")
        target = path if str(path).startswith("http") else urljoin(base_url.rstrip("/") + "/", str(path).lstrip("/"))
        return target

    def _generic_action_path(self, connection: dict[str, Any], spec: ConnectorSpec, payload: dict[str, Any] | None = None) -> str:
        config = dict(connection.get("config") or {})
        path = str(config.get("resource_path") or "/items")
        mapping = {**config, **dict(payload or {})}
        for key, value in list(mapping.items()):
            path = path.replace("{" + str(key) + "}", str(value))
        return path

    def _query_from_action(self, action: IntegrationActionSpec, payload: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for target, source in dict(action.query_map or {}).items():
            if source in payload and payload[source] not in {None, ""}:
                params[target] = payload[source]
        if not params and payload.get("query") and action.operation == "search":
            params["query"] = payload.get("query")
        return params

    def _coerce_items(self, data: Any, *, items_path: str | None = None) -> list[dict[str, Any]]:
        payload = self._get_path(data, items_path) if items_path else data
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "results", "data", "channels", "messages"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [dict(item) for item in value if isinstance(item, dict)]
            return [payload]
        return []

    def _get_path(self, data: Any, path: str | None) -> Any:
        if not path:
            return data
        current = data
        for part in str(path).split("."):
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
                continue
            if isinstance(current, list) and part.isdigit():
                index = int(part)
                current = current[index] if 0 <= index < len(current) else None
                continue
            return None
        return current

    def _infer_next_cursor(self, payload: Any) -> str | None:
        for path in ("next_cursor", "response_metadata.next_cursor", "_scroll_id", "meta.next_cursor"):
            value = self._get_path(payload, path)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _normalize_http_error(self, provider: str, response: httpx.Response) -> str:
        detail = response.text
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = self._provider_message(provider, payload)
        except ValueError:
            detail = response.text.strip()[:400]
        return f"{provider.lower()}_http_error:{response.status_code}:{detail or 'request_failed'}"

    def _retryable_status(self, status_code: int) -> bool:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    def _retry_delay_seconds(self, *, response: httpx.Response, attempt: int, max_backoff: float) -> float:
        retry_after = str(response.headers.get("Retry-After") or "").strip()
        if retry_after:
            try:
                return min(max_backoff, max(0.1, float(retry_after)))
            except ValueError:
                pass
        rate_limit_reset = str(response.headers.get("X-RateLimit-Reset") or response.headers.get("x-ratelimit-reset") or "").strip()
        if rate_limit_reset.isdigit():
            delay = max(0.1, float(rate_limit_reset) - time.time())
            return min(max_backoff, delay)
        return min(max_backoff, max(0.1, 0.25 * (2**attempt)))

    def _provider_payload_error(self, spec: ConnectorSpec, payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        if spec.id == "slack" and payload.get("ok") is False:
            return self._provider_message("Slack", payload)
        if spec.id == "tiktok":
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                code = str(error_payload.get("code") or "").strip().lower()
                if code and code != "ok":
                    return self._provider_message("TikTok", error_payload)
            elif isinstance(error_payload, str) and error_payload.strip():
                return self._provider_message("TikTok", {"error": error_payload})
        if payload.get("ok") is False or payload.get("success") is False:
            return self._provider_message(spec.name, payload)
        status_value = str(payload.get("status") or "").strip().lower()
        if status_value in {"error", "failed", "failure"}:
            return self._provider_message(spec.name, payload)
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            code = str(error_payload.get("code") or error_payload.get("type") or "").strip().lower()
            if code and code not in {"0", "ok", "success"}:
                return self._provider_message(spec.name, error_payload)
        elif isinstance(error_payload, str) and error_payload.strip():
            return self._provider_message(spec.name, {"error": error_payload})
        return None

    def _advance_pagination_state(
        self,
        *,
        spec: ConnectorSpec,
        cursor_state: dict[str, Any],
        payload: Any,
        page_item_count: int,
        page_size: int,
    ) -> bool:
        strategy = spec.pagination_strategy
        if strategy.type == "cursor":
            next_cursor = self._infer_next_cursor(payload)
            if not next_cursor or next_cursor == str(cursor_state.get("cursor") or ""):
                cursor_state["cursor"] = None
                return False
            cursor_state["cursor"] = next_cursor
            return True
        if strategy.type == "page":
            current_page = max(1, int(cursor_state.get("page") or 1))
            if page_item_count < page_size:
                cursor_state["page"] = current_page
                return False
            cursor_state["page"] = current_page + 1
            return True
        if strategy.type == "offset":
            current_offset = max(0, int(cursor_state.get("offset") or 0))
            if page_item_count <= 0:
                cursor_state["offset"] = current_offset
                return False
            cursor_state["offset"] = current_offset + page_item_count
            return page_item_count >= page_size
        return False

    def _generic_probe_action(self, spec: ConnectorSpec) -> IntegrationActionSpec | None:
        readable_ops = ("get_item", "list_items", "search", "fetch_documents", "read_messages")
        for operation in readable_ops:
            action = next((item for item in spec.actions if item.operation == operation and str(item.path or "").strip()), None)
            if action is not None:
                return action
        return next((item for item in spec.actions if str(item.path or "").strip()), None)

    def _max_sync_pages(self) -> int:
        return max(1, int(getattr(self.settings, "connector_sync_max_pages", 5)))

    def _provider_message(self, provider: str, payload: dict[str, Any]) -> str:
        for key in ("error_description", "error", "message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return f"{provider}: {value.strip()}"
        return f"{provider}: request_failed"

    def _record_from_notion_item(self, spec: ConnectorSpec, connection: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        external_id = str(item.get("id") or "")
        record_type = str(item.get("object") or "page")
        title = self._notion_title(item)
        summary = self._safe_text(item.get("url") or item.get("last_edited_time") or record_type)
        return self._base_record(
            spec=spec,
            connection=connection,
            record_type=record_type,
            external_id=external_id,
            title=title,
            text_content=summary,
            raw=item,
            normalized={
                "summary": summary,
                "modified_at": item.get("last_edited_time"),
                "source_url": item.get("url"),
            },
            source_url=str(item.get("url") or "") or None,
        )

    def _record_from_slack_channel(self, spec: ConnectorSpec, connection: dict[str, Any], channel: dict[str, Any]) -> dict[str, Any]:
        channel_id = str(channel.get("id") or "")
        topic = str(channel.get("topic", {}).get("value") or "")
        return self._base_record(
            spec=spec,
            connection=connection,
            record_type="thread",
            external_id=channel_id,
            title=str(channel.get("name") or channel_id),
            text_content=topic,
            raw=channel,
            normalized={"summary": topic, "channel_id": channel_id},
        )

    def _record_from_slack_message(
        self,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        channel: dict[str, Any],
        message: dict[str, Any],
    ) -> dict[str, Any]:
        channel_id = str(channel.get("id") or message.get("channel") or "")
        ts = str(message.get("ts") or "")
        return self._base_record(
            spec=spec,
            connection=connection,
            record_type="message",
            external_id=f"{channel_id}:{ts}" if channel_id or ts else hashlib.sha256(json.dumps(message, sort_keys=True).encode("utf-8")).hexdigest(),
            title=str(message.get("user") or channel_id or "Slack message"),
            text_content=str(message.get("text") or ""),
            raw=message,
            normalized={
                "summary": str(message.get("text") or "")[:500],
                "occurred_at": self._slack_ts_to_iso(ts),
                "channel_id": channel_id,
            },
        )

    def _record_from_github_repo(self, spec: ConnectorSpec, connection: dict[str, Any], repo: dict[str, Any]) -> dict[str, Any]:
        return self._base_record(
            spec=spec,
            connection=connection,
            record_type="document",
            external_id=str(repo.get("id") or repo.get("full_name") or ""),
            title=str(repo.get("full_name") or repo.get("name") or "repository"),
            text_content=str(repo.get("description") or ""),
            raw=repo,
            normalized={
                "summary": str(repo.get("description") or ""),
                "source_url": repo.get("html_url"),
                "modified_at": repo.get("updated_at"),
            },
            source_url=str(repo.get("html_url") or "") or None,
        )

    def _record_from_elastic_hit(self, spec: ConnectorSpec, connection: dict[str, Any], hit: dict[str, Any]) -> dict[str, Any]:
        source = dict(hit.get("_source") or hit)
        external_id = str(hit.get("_id") or source.get("id") or "")
        title = str(source.get("title") or source.get("name") or external_id or "Elastic document")
        text = self._safe_text(source.get("body") or source.get("text") or source.get("summary") or json.dumps(source, ensure_ascii=False))
        return self._base_record(
            spec=spec,
            connection=connection,
            record_type="document",
            external_id=external_id,
            title=title,
            text_content=text,
            raw=hit,
            normalized={
                "summary": text[:500],
                "modified_at": source.get("@timestamp") or source.get("updated_at"),
                "index": hit.get("_index") or source.get("_index"),
                "score": hit.get("_score"),
            },
        )

    def _record_from_table(self, spec: ConnectorSpec, connection: dict[str, Any], *, schema: str, table: str) -> dict[str, Any]:
        return self._base_record(
            spec=spec,
            connection=connection,
            record_type="table",
            external_id=f"{schema}.{table}",
            title=table,
            text_content=f"{schema}.{table} tablo snapshoti",
            raw={"schema": schema, "table": table},
            normalized={"summary": f"{schema}.{table} tablo ozeti"},
        )

    def _record_from_row(self, spec: ConnectorSpec, connection: dict[str, Any], *, table: str, row: dict[str, Any]) -> dict[str, Any]:
        external_id = self._generic_external_id(row)
        summary = self._safe_text(json.dumps(row, ensure_ascii=False))
        return self._base_record(
            spec=spec,
            connection=connection,
            record_type="row",
            external_id=f"{table}:{external_id}",
            title=str(row.get("id") or row.get("uuid") or table),
            text_content=summary,
            raw=row,
            normalized={"summary": summary[:500], "table": table, "modified_at": row.get("updated_at")},
        )

    def _record_from_generic_item(self, spec: ConnectorSpec, connection: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        record_type = self._default_record_type(spec)
        external_id = self._generic_external_id(item)
        title = str(item.get("title") or item.get("name") or item.get("subject") or external_id)
        text = self._safe_text(item.get("body") or item.get("description") or item.get("text") or json.dumps(item, ensure_ascii=False))
        source_url = str(item.get("url") or item.get("html_url") or "") or None
        return self._base_record(
            spec=spec,
            connection=connection,
            record_type=record_type,
            external_id=external_id,
            title=title,
            text_content=text,
            raw=item,
            normalized={
                "summary": text[:500],
                "modified_at": item.get("updated_at") or item.get("modified_at") or item.get("created_at"),
                "source_url": source_url,
            },
            source_url=source_url,
        )

    def _base_record(
        self,
        *,
        spec: ConnectorSpec,
        connection: dict[str, Any],
        record_type: str,
        external_id: str,
        title: str,
        text_content: str,
        raw: dict[str, Any],
        normalized: dict[str, Any],
        source_url: str | None = None,
    ) -> dict[str, Any]:
        return {
            "record_type": record_type,
            "external_id": external_id,
            "title": title,
            "text_content": text_content,
            "content_hash": hashlib.sha256(f"{record_type}:{external_id}:{text_content}".encode("utf-8")).hexdigest(),
            "source_url": source_url,
            "permissions": {"access_level": connection.get("access_level"), "connector_id": spec.id},
            "tags": [spec.id, spec.category, record_type],
            "raw": raw,
            "normalized": normalized,
        }

    def _database_adapter(self, connector_id: str):
        adapter = self.database_adapters.get(connector_id)
        if adapter is not None:
            return adapter
        if connector_id == "postgresql":
            return PsycopgPostgresAdapter()
        if connector_id == "mysql":
            return PyMySqlAdapter()
        if connector_id == "mssql":
            return PyTdsMssqlAdapter()
        raise IntegrationRuntimeError(f"database_adapter_not_found:{connector_id}")

    def _sql_schema(self, connector_id: str, connection: dict[str, Any]) -> str:
        config = dict(connection.get("config") or {})
        if connector_id == "postgresql":
            return self._safe_identifier(config.get("schema") or "public", field_name="schema")
        if connector_id == "mysql":
            return self._safe_identifier(config.get("schema") or config.get("database") or "", field_name="schema")
        if connector_id == "mssql":
            return self._safe_identifier(config.get("schema") or "dbo", field_name="schema")
        raise IntegrationRuntimeError(f"unsupported_sql_connector:{connector_id}")

    def _notion_title(self, item: dict[str, Any]) -> str:
        title = item.get("title")
        if isinstance(title, list) and title:
            return self._safe_text(" ".join(str(part.get("plain_text") or "") for part in title if isinstance(part, dict))) or "Untitled"
        properties = dict(item.get("properties") or {})
        for value in properties.values():
            if not isinstance(value, dict):
                continue
            title_value = value.get("title")
            if isinstance(title_value, list) and title_value:
                return self._safe_text(" ".join(str(part.get("plain_text") or "") for part in title_value if isinstance(part, dict))) or "Untitled"
        return self._safe_text(item.get("url") or item.get("id") or "Untitled")

    def _generic_external_id(self, item: dict[str, Any]) -> str:
        for key in ("id", "external_id", "uuid", "key", "slug"):
            value = item.get(key)
            if value not in {None, ""}:
                return str(value)
        return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:32]

    def _default_record_type(self, spec: ConnectorSpec) -> str:
        if spec.resources and spec.resources[0].item_types:
            return str(spec.resources[0].item_types[0])
        return "document"

    def _split_lines(self, value: str) -> list[str]:
        items: list[str] = []
        for part in str(value or "").replace(",", "\n").splitlines():
            cleaned = part.strip()
            if cleaned:
                items.append(cleaned)
        return items

    def _safe_identifier(self, value: Any, *, field_name: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cleaned):
            raise IntegrationRuntimeError(f"unsafe_{field_name}_identifier")
        return cleaned

    def _verify_slack_signature(self, *, secrets: dict[str, Any], headers: dict[str, str], body: bytes) -> None:
        import hmac

        signing_secret = str(secrets.get("signing_secret") or "").strip()
        if not signing_secret:
            raise IntegrationRuntimeError("slack_signing_secret_missing")
        timestamp = str(headers.get("x-slack-request-timestamp") or "")
        signature = str(headers.get("x-slack-signature") or "")
        if not timestamp or not signature:
            raise IntegrationRuntimeError("slack_signature_headers_missing")
        try:
            request_time = int(timestamp)
        except ValueError as exc:
            raise IntegrationRuntimeError("slack_signature_timestamp_invalid") from exc
        replay_window_seconds = max(60, int(getattr(self.settings, "integration_webhook_replay_window_seconds", 300)))
        if abs(int(time.time()) - request_time) > replay_window_seconds:
            raise IntegrationRuntimeError("slack_signature_replay_window_exceeded")
        base = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
        digest = hmac_sha256(signing_secret.encode("utf-8"), base)
        expected = f"v0={digest}"
        if not hmac.compare_digest(signature, expected):
            raise IntegrationRuntimeError("slack_signature_invalid")

    def _slack_ts_to_iso(self, value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromtimestamp(float(text), timezone.utc).isoformat()
        except ValueError:
            return None

    def _safe_text(self, value: Any, *, limit: int = 4000) -> str:
        return str(value or "").strip()[: max(1, int(limit or 4000))]

    def _default_method_for_operation(self, operation: str) -> str:
        if operation in {"create", "send_message", "create_page", "append_block", "insert_record", "upload_file"}:
            return "POST"
        if operation in {"update", "update_record"}:
            return "PATCH"
        if operation == "delete":
            return "DELETE"
        return "GET"

    def _utcnow_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class PsycopgPostgresAdapter:
    def validate_connection(self, *, connection: dict[str, Any], secrets: dict[str, Any]) -> dict[str, Any]:
        rows = self.run_query(connection=connection, secrets=secrets, query="SELECT 1 AS ok", params=[])
        return {"message": "PostgreSQL baglantisi dogrulandi.", "rows": rows}

    def list_tables(self, *, connection: dict[str, Any], secrets: dict[str, Any], schema: str) -> list[str]:
        rows = self.run_query(
            connection=connection,
            secrets=secrets,
            query=(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name"
            ),
            params=[schema],
        )
        return [str(row.get("table_name") or "") for row in rows if str(row.get("table_name") or "").strip()]

    def detect_cursor_column(self, *, connection: dict[str, Any], secrets: dict[str, Any], schema: str, table: str) -> str | None:
        rows = self.run_query(
            connection=connection,
            secrets=secrets,
            query=(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "AND column_name IN ('updated_at', 'modified_at', 'created_at') "
                "ORDER BY CASE column_name WHEN 'updated_at' THEN 1 WHEN 'modified_at' THEN 2 ELSE 3 END"
            ),
            params=[schema, table],
        )
        for row in rows:
            name = str(row.get("column_name") or "").strip()
            if name:
                return name
        return None

    def fetch_rows(
        self,
        *,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        schema: str,
        table: str,
        limit: int,
        cursor_column: str | None,
        cursor_value: str | None,
    ) -> list[dict[str, Any]]:
        query = f'SELECT * FROM "{schema}"."{table}"'
        params: list[Any] = []
        if cursor_column and cursor_value:
            query += f' WHERE "{cursor_column}" > %s'
            params.append(cursor_value)
        query += " ORDER BY 1 LIMIT %s"
        params.append(limit)
        return self.run_query(connection=connection, secrets=secrets, query=query, params=params)

    def run_query(
        self,
        *,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        query: str,
        params: list[Any],
    ) -> list[dict[str, Any]]:
        if not str(query or "").strip():
            raise IntegrationRuntimeError("postgres_query_required")
        if not self._is_safe_query(query):
            raise IntegrationRuntimeError("postgres_query_not_allowed")
        module = self._driver_module()
        kwargs = self._connect_kwargs(connection=connection, secrets=secrets)
        conn = module.connect(**kwargs)
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(query, list(params or []))
                columns = [str(item[0]) for item in list(getattr(cursor, "description", []) or [])]
                if not columns:
                    conn.commit()
                    return []
                return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
            finally:
                cursor.close()
        finally:
            conn.close()

    def insert_record(
        self,
        *,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        schema: str,
        table: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if not data:
            raise IntegrationRuntimeError("postgres_insert_payload_required")
        columns = [self._safe_identifier(key) for key in data]
        placeholders = ", ".join(["%s"] * len(columns))
        quoted_columns = ", ".join(f'"{col}"' for col in columns)
        query = f'INSERT INTO "{schema}"."{table}" ({quoted_columns}) VALUES ({placeholders})'
        self.run_query(connection=connection, secrets=secrets, query=query, params=[data[col] for col in columns])
        return {"inserted": True, "table": table}

    def update_record(
        self,
        *,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        schema: str,
        table: str,
        data: dict[str, Any],
        where: dict[str, Any],
    ) -> dict[str, Any]:
        if not data or not where:
            raise IntegrationRuntimeError("postgres_update_payload_required")
        set_cols = [self._safe_identifier(key) for key in data]
        where_cols = [self._safe_identifier(key) for key in where]
        set_clause = ", ".join(f'"{col}" = %s' for col in set_cols)
        where_clause = " AND ".join(f'"{col}" = %s' for col in where_cols)
        query = f'UPDATE "{schema}"."{table}" SET {set_clause} WHERE {where_clause}'
        params = [data[col] for col in set_cols] + [where[col] for col in where_cols]
        self.run_query(connection=connection, secrets=secrets, query=query, params=params)
        return {"updated": True, "table": table}

    def delete_record(
        self,
        *,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        schema: str,
        table: str,
        where: dict[str, Any],
    ) -> dict[str, Any]:
        if not where:
            raise IntegrationRuntimeError("postgres_delete_where_required")
        where_cols = [self._safe_identifier(key) for key in where]
        where_clause = " AND ".join(f'"{col}" = %s' for col in where_cols)
        query = f'DELETE FROM "{schema}"."{table}" WHERE {where_clause}'
        self.run_query(connection=connection, secrets=secrets, query=query, params=[where[col] for col in where_cols])
        return {"deleted": True, "table": table}

    def _driver_module(self):
        try:
            import psycopg  # type: ignore

            return psycopg
        except Exception:
            try:
                import psycopg2  # type: ignore

                return psycopg2
            except Exception as exc:
                raise IntegrationRuntimeError("postgres_driver_unavailable") from exc

    def _connect_kwargs(self, *, connection: dict[str, Any], secrets: dict[str, Any]) -> dict[str, Any]:
        config = dict(connection.get("config") or {})
        return {
            "host": str(config.get("host") or "").strip(),
            "port": int(config.get("port") or 5432),
            "dbname": str(config.get("database") or "").strip(),
            "user": str(config.get("username") or "").strip(),
            "password": str(secrets.get("password") or "").strip(),
            "sslmode": str(config.get("ssl_mode") or "require").strip(),
        }

    def _is_safe_query(self, query: str) -> bool:
        cleaned = str(query or "").strip().lower()
        return bool(re.match(r"^(select|with|insert|update|delete)\b", cleaned))

    def _safe_identifier(self, value: str) -> str:
        cleaned = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cleaned):
            raise IntegrationRuntimeError("unsafe_sql_identifier")
        return cleaned


class PyMySqlAdapter:
    def validate_connection(self, *, connection: dict[str, Any], secrets: dict[str, Any]) -> dict[str, Any]:
        rows = self.run_query(connection=connection, secrets=secrets, query="SELECT 1 AS ok", params=[])
        return {"message": "MySQL baglantisi dogrulandi.", "rows": rows}

    def list_tables(self, *, connection: dict[str, Any], secrets: dict[str, Any], schema: str) -> list[str]:
        rows = self.run_query(
            connection=connection,
            secrets=secrets,
            query=(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name"
            ),
            params=[schema],
        )
        return [str(row.get("table_name") or "") for row in rows if str(row.get("table_name") or "").strip()]

    def detect_cursor_column(self, *, connection: dict[str, Any], secrets: dict[str, Any], schema: str, table: str) -> str | None:
        rows = self.run_query(
            connection=connection,
            secrets=secrets,
            query=(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "AND column_name IN ('updated_at', 'modified_at', 'created_at') "
                "ORDER BY CASE column_name WHEN 'updated_at' THEN 1 WHEN 'modified_at' THEN 2 ELSE 3 END"
            ),
            params=[schema, table],
        )
        for row in rows:
            name = str(row.get("column_name") or "").strip()
            if name:
                return name
        return None

    def fetch_rows(
        self,
        *,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        schema: str,
        table: str,
        limit: int,
        cursor_column: str | None,
        cursor_value: str | None,
    ) -> list[dict[str, Any]]:
        query = f"SELECT * FROM {self._qualified_table(schema, table)}"
        params: list[Any] = []
        if cursor_column and cursor_value:
            query += f" WHERE {self._quote(cursor_column)} > %s"
            params.append(cursor_value)
        query += " ORDER BY 1 LIMIT %s"
        params.append(limit)
        return self.run_query(connection=connection, secrets=secrets, query=query, params=params)

    def run_query(self, *, connection: dict[str, Any], secrets: dict[str, Any], query: str, params: list[Any]) -> list[dict[str, Any]]:
        if not str(query or "").strip():
            raise IntegrationRuntimeError("mysql_query_required")
        if not self._is_safe_query(query):
            raise IntegrationRuntimeError("mysql_query_not_allowed")
        module = self._driver_module()
        conn = module.connect(**self._connect_kwargs(connection=connection, secrets=secrets, module=module))
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(query, list(params or []))
                description = list(getattr(cursor, "description", []) or [])
                if not description:
                    conn.commit()
                    return []
                rows = cursor.fetchall()
                if rows and isinstance(rows[0], dict):
                    return [dict(row) for row in rows]
                columns = [str(item[0]) for item in description]
                return [dict(zip(columns, row, strict=False)) for row in rows]
            finally:
                cursor.close()
        finally:
            conn.close()

    def insert_record(self, *, connection: dict[str, Any], secrets: dict[str, Any], schema: str, table: str, data: dict[str, Any]) -> dict[str, Any]:
        if not data:
            raise IntegrationRuntimeError("mysql_insert_payload_required")
        columns = [self._safe_identifier(key) for key in data]
        placeholders = ", ".join(["%s"] * len(columns))
        quoted_columns = ", ".join(self._quote(col) for col in columns)
        query = f"INSERT INTO {self._qualified_table(schema, table)} ({quoted_columns}) VALUES ({placeholders})"
        self.run_query(connection=connection, secrets=secrets, query=query, params=[data[col] for col in columns])
        return {"inserted": True, "table": table}

    def update_record(
        self,
        *,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        schema: str,
        table: str,
        data: dict[str, Any],
        where: dict[str, Any],
    ) -> dict[str, Any]:
        if not data or not where:
            raise IntegrationRuntimeError("mysql_update_payload_required")
        set_cols = [self._safe_identifier(key) for key in data]
        where_cols = [self._safe_identifier(key) for key in where]
        set_clause = ", ".join(f"{self._quote(col)} = %s" for col in set_cols)
        where_clause = " AND ".join(f"{self._quote(col)} = %s" for col in where_cols)
        query = f"UPDATE {self._qualified_table(schema, table)} SET {set_clause} WHERE {where_clause}"
        params = [data[col] for col in set_cols] + [where[col] for col in where_cols]
        self.run_query(connection=connection, secrets=secrets, query=query, params=params)
        return {"updated": True, "table": table}

    def delete_record(self, *, connection: dict[str, Any], secrets: dict[str, Any], schema: str, table: str, where: dict[str, Any]) -> dict[str, Any]:
        if not where:
            raise IntegrationRuntimeError("mysql_delete_where_required")
        where_cols = [self._safe_identifier(key) for key in where]
        where_clause = " AND ".join(f"{self._quote(col)} = %s" for col in where_cols)
        query = f"DELETE FROM {self._qualified_table(schema, table)} WHERE {where_clause}"
        self.run_query(connection=connection, secrets=secrets, query=query, params=[where[col] for col in where_cols])
        return {"deleted": True, "table": table}

    def _driver_module(self):
        try:
            import pymysql  # type: ignore

            return pymysql
        except Exception as exc:
            raise IntegrationRuntimeError("mysql_driver_unavailable") from exc

    def _connect_kwargs(self, *, connection: dict[str, Any], secrets: dict[str, Any], module: Any) -> dict[str, Any]:
        config = dict(connection.get("config") or {})
        ssl_mode = str(config.get("ssl_mode") or "prefer").strip().lower()
        kwargs: dict[str, Any] = {
            "host": str(config.get("host") or "").strip(),
            "port": int(config.get("port") or 3306),
            "database": str(config.get("database") or "").strip(),
            "user": str(config.get("username") or "").strip(),
            "password": str(secrets.get("password") or "").strip(),
            "cursorclass": module.cursors.DictCursor,
            "charset": "utf8mb4",
            "autocommit": False,
        }
        if ssl_mode == "disable":
            kwargs["ssl_disabled"] = True
        else:
            kwargs["ssl"] = {}
        return kwargs

    def _qualified_table(self, schema: str, table: str) -> str:
        safe_table = self._safe_identifier(table)
        safe_schema = self._safe_identifier(schema)
        return f"{self._quote(safe_schema)}.{self._quote(safe_table)}"

    def _quote(self, value: str) -> str:
        return f"`{self._safe_identifier(value)}`"

    def _is_safe_query(self, query: str) -> bool:
        cleaned = str(query or "").strip().lower()
        return bool(re.match(r"^(select|with|insert|update|delete)\b", cleaned))

    def _safe_identifier(self, value: str) -> str:
        cleaned = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cleaned):
            raise IntegrationRuntimeError("unsafe_sql_identifier")
        return cleaned


class PyTdsMssqlAdapter:
    def validate_connection(self, *, connection: dict[str, Any], secrets: dict[str, Any]) -> dict[str, Any]:
        rows = self.run_query(connection=connection, secrets=secrets, query="SELECT 1 AS ok", params=[])
        return {"message": "SQL Server baglantisi dogrulandi.", "rows": rows}

    def list_tables(self, *, connection: dict[str, Any], secrets: dict[str, Any], schema: str) -> list[str]:
        rows = self.run_query(
            connection=connection,
            secrets=secrets,
            query=(
                "SELECT TABLE_NAME AS table_name FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
            ),
            params=[schema],
        )
        return [str(row.get("table_name") or "") for row in rows if str(row.get("table_name") or "").strip()]

    def detect_cursor_column(self, *, connection: dict[str, Any], secrets: dict[str, Any], schema: str, table: str) -> str | None:
        rows = self.run_query(
            connection=connection,
            secrets=secrets,
            query=(
                "SELECT COLUMN_NAME AS column_name FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                "AND COLUMN_NAME IN ('updated_at', 'modified_at', 'created_at') "
                "ORDER BY CASE COLUMN_NAME WHEN 'updated_at' THEN 1 WHEN 'modified_at' THEN 2 ELSE 3 END"
            ),
            params=[schema, table],
        )
        for row in rows:
            name = str(row.get("column_name") or "").strip()
            if name:
                return name
        return None

    def fetch_rows(
        self,
        *,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        schema: str,
        table: str,
        limit: int,
        cursor_column: str | None,
        cursor_value: str | None,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(500, int(limit)))
        query = f"SELECT TOP {safe_limit} * FROM {self._qualified_table(schema, table)}"
        params: list[Any] = []
        if cursor_column and cursor_value:
            query += f" WHERE {self._quote(cursor_column)} > %s"
            params.append(cursor_value)
            query += f" ORDER BY {self._quote(cursor_column)} ASC"
        else:
            query += " ORDER BY 1"
        return self.run_query(connection=connection, secrets=secrets, query=query, params=params)

    def run_query(self, *, connection: dict[str, Any], secrets: dict[str, Any], query: str, params: list[Any]) -> list[dict[str, Any]]:
        if not str(query or "").strip():
            raise IntegrationRuntimeError("mssql_query_required")
        if not self._is_safe_query(query):
            raise IntegrationRuntimeError("mssql_query_not_allowed")
        module = self._driver_module()
        conn = module.connect(**self._connect_kwargs(connection=connection, secrets=secrets))
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(query, list(params or []))
                description = list(getattr(cursor, "description", []) or [])
                if not description:
                    conn.commit()
                    return []
                rows = cursor.fetchall()
                if rows and isinstance(rows[0], dict):
                    return [dict(row) for row in rows]
                columns = [str(item[0]) for item in description]
                return [dict(zip(columns, row, strict=False)) for row in rows]
            finally:
                cursor.close()
        finally:
            conn.close()

    def insert_record(self, *, connection: dict[str, Any], secrets: dict[str, Any], schema: str, table: str, data: dict[str, Any]) -> dict[str, Any]:
        if not data:
            raise IntegrationRuntimeError("mssql_insert_payload_required")
        columns = [self._safe_identifier(key) for key in data]
        placeholders = ", ".join(["%s"] * len(columns))
        quoted_columns = ", ".join(self._quote(col) for col in columns)
        query = f"INSERT INTO {self._qualified_table(schema, table)} ({quoted_columns}) VALUES ({placeholders})"
        self.run_query(connection=connection, secrets=secrets, query=query, params=[data[col] for col in columns])
        return {"inserted": True, "table": table}

    def update_record(
        self,
        *,
        connection: dict[str, Any],
        secrets: dict[str, Any],
        schema: str,
        table: str,
        data: dict[str, Any],
        where: dict[str, Any],
    ) -> dict[str, Any]:
        if not data or not where:
            raise IntegrationRuntimeError("mssql_update_payload_required")
        set_cols = [self._safe_identifier(key) for key in data]
        where_cols = [self._safe_identifier(key) for key in where]
        set_clause = ", ".join(f"{self._quote(col)} = %s" for col in set_cols)
        where_clause = " AND ".join(f"{self._quote(col)} = %s" for col in where_cols)
        query = f"UPDATE {self._qualified_table(schema, table)} SET {set_clause} WHERE {where_clause}"
        params = [data[col] for col in set_cols] + [where[col] for col in where_cols]
        self.run_query(connection=connection, secrets=secrets, query=query, params=params)
        return {"updated": True, "table": table}

    def delete_record(self, *, connection: dict[str, Any], secrets: dict[str, Any], schema: str, table: str, where: dict[str, Any]) -> dict[str, Any]:
        if not where:
            raise IntegrationRuntimeError("mssql_delete_where_required")
        where_cols = [self._safe_identifier(key) for key in where]
        where_clause = " AND ".join(f"{self._quote(col)} = %s" for col in where_cols)
        query = f"DELETE FROM {self._qualified_table(schema, table)} WHERE {where_clause}"
        self.run_query(connection=connection, secrets=secrets, query=query, params=[where[col] for col in where_cols])
        return {"deleted": True, "table": table}

    def _driver_module(self):
        try:
            import pytds  # type: ignore

            return pytds
        except Exception as exc:
            raise IntegrationRuntimeError("mssql_driver_unavailable") from exc

    def _connect_kwargs(self, *, connection: dict[str, Any], secrets: dict[str, Any]) -> dict[str, Any]:
        config = dict(connection.get("config") or {})
        kwargs: dict[str, Any] = {
            "server": str(config.get("host") or "").strip(),
            "port": int(config.get("port") or 1433),
            "database": str(config.get("database") or "").strip(),
            "user": str(config.get("username") or "").strip(),
            "password": str(secrets.get("password") or "").strip(),
            "as_dict": True,
        }
        cafile = str(config.get("ssl_ca_file") or "").strip()
        if cafile:
            kwargs["cafile"] = cafile
        return kwargs

    def _qualified_table(self, schema: str, table: str) -> str:
        return f"{self._quote(schema)}.{self._quote(table)}"

    def _quote(self, value: str) -> str:
        return f"[{self._safe_identifier(value)}]"

    def _is_safe_query(self, query: str) -> bool:
        cleaned = str(query or "").strip().lower()
        return bool(re.match(r"^(select|with|insert|update|delete)\b", cleaned))

    def _safe_identifier(self, value: str) -> str:
        cleaned = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cleaned):
            raise IntegrationRuntimeError("unsafe_sql_identifier")
        return cleaned


def hmac_sha256(secret: bytes, payload: bytes) -> str:
    import hmac

    return hmac.new(secret, payload, hashlib.sha256).hexdigest()
