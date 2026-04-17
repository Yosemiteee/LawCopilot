from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


_UNSET = object()


class IntegrationRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS integration_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    connector_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    auth_type TEXT NOT NULL,
                    access_level TEXT NOT NULL,
                    management_mode TEXT NOT NULL DEFAULT 'platform',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    mock_mode INTEGER NOT NULL DEFAULT 0,
                    scopes_json TEXT NOT NULL DEFAULT '[]',
                    config_json TEXT NOT NULL DEFAULT '{}',
                    secret_blob TEXT NOT NULL DEFAULT '',
                    health_status TEXT NOT NULL DEFAULT 'unknown',
                    health_message TEXT,
                    auth_status TEXT NOT NULL DEFAULT 'pending',
                    auth_summary_json TEXT NOT NULL DEFAULT '{}',
                    credential_expires_at TEXT,
                    credential_refreshed_at TEXT,
                    credential_revoked_at TEXT,
                    last_health_check_at TEXT,
                    last_validated_at TEXT,
                    last_sync_at TEXT,
                    last_error TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'idle',
                    sync_status_message TEXT,
                    cursor_json TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_integration_connections_office
                ON integration_connections (office_id, connector_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS integration_oauth_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    connection_id INTEGER NOT NULL,
                    connector_id TEXT NOT NULL,
                    state TEXT NOT NULL UNIQUE,
                    code_verifier TEXT NOT NULL DEFAULT '',
                    redirect_uri TEXT,
                    requested_scopes_json TEXT NOT NULL DEFAULT '[]',
                    authorization_url TEXT,
                    status TEXT NOT NULL,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    error TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (connection_id) REFERENCES integration_connections(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_integration_oauth_sessions_connection
                ON integration_oauth_sessions (connection_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS integration_sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    connection_id INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    trigger_type TEXT NOT NULL DEFAULT 'manual',
                    status TEXT NOT NULL,
                    requested_by TEXT,
                    run_key TEXT,
                    item_count INTEGER NOT NULL DEFAULT 0,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    scheduled_for TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    next_retry_at TEXT,
                    lock_token TEXT,
                    locked_at TEXT,
                    error TEXT,
                    cursor_json TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (connection_id) REFERENCES integration_connections(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_integration_sync_runs_connection
                ON integration_sync_runs (connection_id, started_at DESC);

                CREATE TABLE IF NOT EXISTS integration_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    connection_id INTEGER NOT NULL,
                    record_type TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT,
                    text_content TEXT,
                    content_hash TEXT,
                    source_url TEXT,
                    permissions_json TEXT NOT NULL DEFAULT '{}',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    normalized_json TEXT NOT NULL DEFAULT '{}',
                    synced_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (connection_id) REFERENCES integration_connections(id) ON DELETE CASCADE,
                    UNIQUE (connection_id, record_type, external_id)
                );

                CREATE INDEX IF NOT EXISTS idx_integration_records_connection
                ON integration_records (connection_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS integration_resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    connection_id INTEGER NOT NULL,
                    resource_kind TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    source_record_type TEXT NOT NULL,
                    title TEXT,
                    body_text TEXT,
                    search_text TEXT,
                    source_url TEXT,
                    parent_external_id TEXT,
                    owner_label TEXT,
                    occurred_at TEXT,
                    modified_at TEXT,
                    checksum TEXT,
                    permissions_json TEXT NOT NULL DEFAULT '{}',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    attributes_json TEXT NOT NULL DEFAULT '{}',
                    sync_metadata_json TEXT NOT NULL DEFAULT '{}',
                    synced_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (connection_id) REFERENCES integration_connections(id) ON DELETE CASCADE,
                    UNIQUE (connection_id, resource_kind, external_id)
                );

                CREATE INDEX IF NOT EXISTS idx_integration_resources_connection
                ON integration_resources (connection_id, resource_kind, updated_at DESC);

                CREATE TABLE IF NOT EXISTS integration_action_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    connection_id INTEGER NOT NULL,
                    action_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    approval_required INTEGER NOT NULL DEFAULT 0,
                    approval_state TEXT NOT NULL DEFAULT 'not_required',
                    input_json TEXT NOT NULL DEFAULT '{}',
                    output_json TEXT NOT NULL DEFAULT '{}',
                    policy_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (connection_id) REFERENCES integration_connections(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_integration_action_runs_connection
                ON integration_action_runs (connection_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS integration_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    connection_id INTEGER,
                    connector_id TEXT,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'info',
                    message TEXT NOT NULL,
                    actor TEXT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (connection_id) REFERENCES integration_connections(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_integration_events_connection
                ON integration_events (connection_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS integration_generated_connectors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    connector_id TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    request_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    docs_url TEXT,
                    openapi_url TEXT,
                    openapi_spec TEXT,
                    documentation_excerpt TEXT,
                    spec_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    last_error TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, connector_id)
                );

                CREATE INDEX IF NOT EXISTS idx_integration_generated_connectors_office
                ON integration_generated_connectors (office_id, status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS integration_generated_connector_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    connector_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    spec_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, connector_id, version)
                );

                CREATE INDEX IF NOT EXISTS idx_integration_generated_connector_versions_connector
                ON integration_generated_connector_versions (office_id, connector_id, version DESC);

                CREATE TABLE IF NOT EXISTS integration_connector_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    pattern_key TEXT NOT NULL,
                    connector_id TEXT,
                    service_name TEXT NOT NULL,
                    category TEXT,
                    auth_type TEXT,
                    docs_host TEXT,
                    base_url TEXT,
                    source_kind TEXT NOT NULL DEFAULT 'generated',
                    success_count INTEGER NOT NULL DEFAULT 0,
                    pattern_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    UNIQUE (office_id, pattern_key)
                );

                CREATE INDEX IF NOT EXISTS idx_integration_connector_patterns_lookup
                ON integration_connector_patterns (office_id, service_name, category, success_count DESC, updated_at DESC);

                CREATE TABLE IF NOT EXISTS integration_assistant_setups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    thread_id INTEGER NOT NULL,
                    connector_id TEXT,
                    connection_id INTEGER,
                    service_name TEXT,
                    request_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    missing_fields_json TEXT NOT NULL DEFAULT '[]',
                    collected_config_json TEXT NOT NULL DEFAULT '{}',
                    secret_blob TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (connection_id) REFERENCES integration_connections(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_integration_assistant_setups_thread
                ON integration_assistant_setups (office_id, thread_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS integration_webhook_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    connection_id INTEGER,
                    connector_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    request_signature TEXT,
                    request_timestamp TEXT,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    response_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    received_at TEXT NOT NULL,
                    processed_at TEXT,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (connection_id) REFERENCES integration_connections(id) ON DELETE CASCADE,
                    UNIQUE (office_id, connector_id, event_id)
                );

                CREATE INDEX IF NOT EXISTS idx_integration_webhook_events_connection
                ON integration_webhook_events (connection_id, received_at DESC);
                """
            )
            self._ensure_backcompat_columns(conn)
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_integration_sync_runs_queue
                ON integration_sync_runs (office_id, status, scheduled_for)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_integration_sync_runs_run_key
                ON integration_sync_runs (office_id, connection_id, run_key, status)
                """
            )

    def _ensure_backcompat_columns(self, conn: sqlite3.Connection) -> None:
        self._ensure_column(conn, "integration_connections", "auth_status TEXT NOT NULL DEFAULT 'pending'")
        self._ensure_column(conn, "integration_connections", "auth_summary_json TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column(conn, "integration_connections", "credential_expires_at TEXT")
        self._ensure_column(conn, "integration_connections", "credential_refreshed_at TEXT")
        self._ensure_column(conn, "integration_connections", "credential_revoked_at TEXT")
        self._ensure_column(conn, "integration_connections", "last_health_check_at TEXT")
        self._ensure_column(conn, "integration_connections", "sync_status TEXT NOT NULL DEFAULT 'idle'")
        self._ensure_column(conn, "integration_connections", "sync_status_message TEXT")

        self._ensure_column(conn, "integration_sync_runs", "trigger_type TEXT NOT NULL DEFAULT 'manual'")
        self._ensure_column(conn, "integration_sync_runs", "requested_by TEXT")
        self._ensure_column(conn, "integration_sync_runs", "run_key TEXT")
        self._ensure_column(conn, "integration_sync_runs", "attempt_count INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "integration_sync_runs", "max_attempts INTEGER NOT NULL DEFAULT 3")
        self._ensure_column(conn, "integration_sync_runs", "scheduled_for TEXT")
        self._ensure_column(conn, "integration_sync_runs", "next_retry_at TEXT")
        self._ensure_column(conn, "integration_sync_runs", "lock_token TEXT")
        self._ensure_column(conn, "integration_sync_runs", "locked_at TEXT")

        self._ensure_column(conn, "integration_action_runs", "policy_json TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column(conn, "integration_generated_connectors", "version INTEGER NOT NULL DEFAULT 1")
        self._ensure_column(conn, "integration_generated_connectors", "enabled INTEGER NOT NULL DEFAULT 1")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column_def: str) -> None:
        columns = self._table_columns(conn, table)
        column_name = column_def.split(" ", 1)[0]
        if column_name in columns:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_office(self, conn: sqlite3.Connection, office_id: str) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO offices (id, name, deployment_mode, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (office_id, "Varsayilan Ofis", "local-only", self._now()),
        )

    def _decode_json_field(self, row: dict[str, Any], source: str, target: str, *, default: Any) -> dict[str, Any]:
        raw = row.pop(source, None)
        if raw in (None, ""):
            row[target] = default
            return row
        try:
            row[target] = json.loads(raw)
        except json.JSONDecodeError:
            row[target] = default
        return row

    def _decode_connection(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "scopes_json", "scopes", default=[])
        row = self._decode_json_field(row, "config_json", "config", default={})
        row = self._decode_json_field(row, "cursor_json", "cursor", default={})
        row = self._decode_json_field(row, "metadata_json", "metadata", default={})
        row = self._decode_json_field(row, "auth_summary_json", "auth_summary", default={})
        row["enabled"] = bool(row.get("enabled"))
        row["mock_mode"] = bool(row.get("mock_mode"))
        return row

    def _decode_oauth_session(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "requested_scopes_json", "requested_scopes", default=[])
        row = self._decode_json_field(row, "metadata_json", "metadata", default={})
        return row

    def _decode_sync_run(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "cursor_json", "cursor", default={})
        row = self._decode_json_field(row, "metadata_json", "metadata", default={})
        return row

    def _decode_record(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "permissions_json", "permissions", default={})
        row = self._decode_json_field(row, "tags_json", "tags", default=[])
        row = self._decode_json_field(row, "raw_json", "raw", default={})
        row = self._decode_json_field(row, "normalized_json", "normalized", default={})
        return row

    def _decode_resource(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "permissions_json", "permissions", default={})
        row = self._decode_json_field(row, "tags_json", "tags", default=[])
        row = self._decode_json_field(row, "attributes_json", "attributes", default={})
        row = self._decode_json_field(row, "sync_metadata_json", "sync_metadata", default={})
        return row

    def _decode_action_run(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "input_json", "input", default={})
        row = self._decode_json_field(row, "output_json", "output", default={})
        row = self._decode_json_field(row, "policy_json", "policy", default={})
        row["approval_required"] = bool(row.get("approval_required"))
        return row

    def _decode_event(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "data_json", "data", default={})
        return row

    def _decode_generated_connector(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "spec_json", "spec", default={})
        row = self._decode_json_field(row, "metadata_json", "metadata", default={})
        row["enabled"] = bool(row.get("enabled", 1))
        row["version"] = int(row.get("version") or 1)
        return row

    def _decode_generated_connector_version(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "spec_json", "spec", default={})
        row = self._decode_json_field(row, "metadata_json", "metadata", default={})
        row["enabled"] = bool(row.get("enabled", 1))
        row["version"] = int(row.get("version") or 1)
        return row

    def _decode_connector_pattern(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "pattern_json", "pattern", default={})
        row["success_count"] = int(row.get("success_count") or 0)
        return row

    def _decode_webhook_event(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "payload_json", "payload", default={})
        row = self._decode_json_field(row, "response_json", "response", default={})
        return row

    def _decode_assistant_setup(self, row: dict[str, Any]) -> dict[str, Any]:
        row = self._decode_json_field(row, "missing_fields_json", "missing_fields", default=[])
        row = self._decode_json_field(row, "collected_config_json", "collected_config", default={})
        row = self._decode_json_field(row, "metadata_json", "metadata", default={})
        return row

    def list_connections(self, office_id: str, *, connector_id: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if connector_id:
                rows = conn.execute(
                    "SELECT * FROM integration_connections WHERE office_id=? AND connector_id=? ORDER BY updated_at DESC",
                    (office_id, connector_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM integration_connections WHERE office_id=? ORDER BY updated_at DESC",
                    (office_id,),
                ).fetchall()
        return [self._decode_connection(dict(row)) for row in rows]

    def get_connection(self, office_id: str, connection_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM integration_connections WHERE office_id=? AND id=?",
                (office_id, connection_id),
            ).fetchone()
        return self._decode_connection(dict(row)) if row else None

    def upsert_connection(
        self,
        office_id: str,
        *,
        connector_id: str,
        display_name: str,
        status: str,
        auth_type: str,
        access_level: str,
        management_mode: str,
        enabled: bool,
        mock_mode: bool,
        scopes: list[str],
        config: dict[str, Any],
        secret_blob: str,
        health_status: str,
        health_message: str | None,
        auth_status: str = "pending",
        auth_summary: dict[str, Any] | None = None,
        credential_expires_at: str | None = None,
        credential_refreshed_at: str | None = None,
        credential_revoked_at: str | None = None,
        last_health_check_at: str | None = None,
        last_validated_at: str | None = None,
        last_sync_at: str | None = None,
        last_error: str | None = None,
        sync_status: str = "idle",
        sync_status_message: str | None = None,
        cursor: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
        connection_id: int | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            if connection_id:
                existing = conn.execute(
                    "SELECT id FROM integration_connections WHERE office_id=? AND id=?",
                    (office_id, connection_id),
                ).fetchone()
                if not existing:
                    raise ValueError("integration_connection_not_found")
                conn.execute(
                    """
                    UPDATE integration_connections
                    SET connector_id=?, display_name=?, status=?, auth_type=?, access_level=?, management_mode=?,
                        enabled=?, mock_mode=?, scopes_json=?, config_json=?, secret_blob=?, health_status=?,
                        health_message=?, auth_status=?, auth_summary_json=?, credential_expires_at=?,
                        credential_refreshed_at=?, credential_revoked_at=?, last_health_check_at=?,
                        last_validated_at=?, last_sync_at=?, last_error=?, sync_status=?, sync_status_message=?,
                        cursor_json=?, metadata_json=?, updated_at=?
                    WHERE office_id=? AND id=?
                    """,
                    (
                        connector_id,
                        display_name,
                        status,
                        auth_type,
                        access_level,
                        management_mode,
                        1 if enabled else 0,
                        1 if mock_mode else 0,
                        json.dumps(scopes or [], ensure_ascii=False),
                        json.dumps(config or {}, ensure_ascii=False),
                        secret_blob,
                        health_status,
                        health_message,
                        auth_status,
                        json.dumps(auth_summary or {}, ensure_ascii=False),
                        credential_expires_at,
                        credential_refreshed_at,
                        credential_revoked_at,
                        last_health_check_at,
                        last_validated_at,
                        last_sync_at,
                        last_error,
                        sync_status,
                        sync_status_message,
                        json.dumps(cursor or {}, ensure_ascii=False) if cursor is not None else None,
                        json.dumps(metadata or {}, ensure_ascii=False),
                        now,
                        office_id,
                        connection_id,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM integration_connections WHERE office_id=? AND id=?",
                    (office_id, connection_id),
                ).fetchone()
                return self._decode_connection(dict(row)) if row else {}

            conn.execute(
                """
                INSERT INTO integration_connections (
                    office_id, connector_id, display_name, status, auth_type, access_level, management_mode,
                    enabled, mock_mode, scopes_json, config_json, secret_blob, health_status, health_message,
                    auth_status, auth_summary_json, credential_expires_at, credential_refreshed_at, credential_revoked_at,
                    last_health_check_at, last_validated_at, last_sync_at, last_error, sync_status, sync_status_message,
                    cursor_json, metadata_json, created_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    connector_id,
                    display_name,
                    status,
                    auth_type,
                    access_level,
                    management_mode,
                    1 if enabled else 0,
                    1 if mock_mode else 0,
                    json.dumps(scopes or [], ensure_ascii=False),
                    json.dumps(config or {}, ensure_ascii=False),
                    secret_blob,
                    health_status,
                    health_message,
                    auth_status,
                    json.dumps(auth_summary or {}, ensure_ascii=False),
                    credential_expires_at,
                    credential_refreshed_at,
                    credential_revoked_at,
                    last_health_check_at,
                    last_validated_at,
                    last_sync_at,
                    last_error,
                    sync_status,
                    sync_status_message,
                    json.dumps(cursor or {}, ensure_ascii=False) if cursor is not None else None,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    created_by,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM integration_connections WHERE office_id=? ORDER BY id DESC LIMIT 1",
                (office_id,),
            ).fetchone()
        return self._decode_connection(dict(row)) if row else {}

    def update_connection_runtime(
        self,
        office_id: str,
        connection_id: int,
        *,
        status: Any = _UNSET,
        enabled: Any = _UNSET,
        health_status: Any = _UNSET,
        health_message: Any = _UNSET,
        auth_status: Any = _UNSET,
        auth_summary: Any = _UNSET,
        credential_expires_at: Any = _UNSET,
        credential_refreshed_at: Any = _UNSET,
        credential_revoked_at: Any = _UNSET,
        last_health_check_at: Any = _UNSET,
        last_validated_at: Any = _UNSET,
        last_sync_at: Any = _UNSET,
        last_error: Any = _UNSET,
        sync_status: Any = _UNSET,
        sync_status_message: Any = _UNSET,
        cursor: Any = _UNSET,
        metadata: Any = _UNSET,
        secret_blob: Any = _UNSET,
    ) -> dict[str, Any]:
        fields: list[str] = ["updated_at=?"]
        values: list[Any] = [self._now()]
        if status is not _UNSET:
            fields.append("status=?")
            values.append(status)
        if enabled is not _UNSET:
            fields.append("enabled=?")
            values.append(1 if enabled else 0)
        if health_status is not _UNSET:
            fields.append("health_status=?")
            values.append(health_status)
        if health_message is not _UNSET:
            fields.append("health_message=?")
            values.append(health_message)
        if auth_status is not _UNSET:
            fields.append("auth_status=?")
            values.append(auth_status)
        if auth_summary is not _UNSET:
            fields.append("auth_summary_json=?")
            values.append(json.dumps(auth_summary or {}, ensure_ascii=False))
        if credential_expires_at is not _UNSET:
            fields.append("credential_expires_at=?")
            values.append(credential_expires_at)
        if credential_refreshed_at is not _UNSET:
            fields.append("credential_refreshed_at=?")
            values.append(credential_refreshed_at)
        if credential_revoked_at is not _UNSET:
            fields.append("credential_revoked_at=?")
            values.append(credential_revoked_at)
        if last_health_check_at is not _UNSET:
            fields.append("last_health_check_at=?")
            values.append(last_health_check_at)
        if last_validated_at is not _UNSET:
            fields.append("last_validated_at=?")
            values.append(last_validated_at)
        if last_sync_at is not _UNSET:
            fields.append("last_sync_at=?")
            values.append(last_sync_at)
        if last_error is not _UNSET:
            fields.append("last_error=?")
            values.append(last_error)
        if sync_status is not _UNSET:
            fields.append("sync_status=?")
            values.append(sync_status)
        if sync_status_message is not _UNSET:
            fields.append("sync_status_message=?")
            values.append(sync_status_message)
        if cursor is not _UNSET:
            fields.append("cursor_json=?")
            values.append(json.dumps(cursor or {}, ensure_ascii=False) if cursor is not None else None)
        if metadata is not _UNSET:
            fields.append("metadata_json=?")
            values.append(json.dumps(metadata or {}, ensure_ascii=False))
        if secret_blob is not _UNSET:
            fields.append("secret_blob=?")
            values.append(secret_blob)
        values.extend([office_id, connection_id])
        with self._conn() as conn:
            conn.execute(f"UPDATE integration_connections SET {', '.join(fields)} WHERE office_id=? AND id=?", tuple(values))
            row = conn.execute(
                "SELECT * FROM integration_connections WHERE office_id=? AND id=?",
                (office_id, connection_id),
            ).fetchone()
        return self._decode_connection(dict(row)) if row else {}

    def create_oauth_session(
        self,
        office_id: str,
        *,
        connection_id: int,
        connector_id: str,
        state: str,
        code_verifier: str,
        redirect_uri: str | None,
        requested_scopes: list[str],
        authorization_url: str,
        status: str,
        created_by: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            conn.execute(
                """
                INSERT INTO integration_oauth_sessions (
                    office_id, connection_id, connector_id, state, code_verifier, redirect_uri,
                    requested_scopes_json, authorization_url, status, created_by, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    connection_id,
                    connector_id,
                    state,
                    code_verifier,
                    redirect_uri,
                    json.dumps(requested_scopes or [], ensure_ascii=False),
                    authorization_url,
                    status,
                    created_by,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            row = conn.execute(
                "SELECT * FROM integration_oauth_sessions WHERE state=?",
                (state,),
            ).fetchone()
        return self._decode_oauth_session(dict(row)) if row else {}

    def get_oauth_session_by_state(self, office_id: str, state: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM integration_oauth_sessions WHERE office_id=? AND state=?",
                (office_id, state),
            ).fetchone()
        return self._decode_oauth_session(dict(row)) if row else None

    def finish_oauth_session(
        self,
        office_id: str,
        state: str,
        *,
        status: str,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE integration_oauth_sessions
                SET status=?, completed_at=?, error=?, metadata_json=?
                WHERE office_id=? AND state=?
                """,
                (
                    status,
                    now,
                    error,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    office_id,
                    state,
                ),
            )
            row = conn.execute(
                "SELECT * FROM integration_oauth_sessions WHERE office_id=? AND state=?",
                (office_id, state),
            ).fetchone()
        return self._decode_oauth_session(dict(row)) if row else {}

    def list_oauth_sessions(self, office_id: str, connection_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM integration_oauth_sessions
                WHERE office_id=? AND connection_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (office_id, connection_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._decode_oauth_session(dict(row)) for row in rows]

    def get_active_sync_run(self, office_id: str, connection_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM integration_sync_runs
                WHERE office_id=? AND connection_id=? AND status IN ('queued', 'retry_scheduled', 'running')
                ORDER BY id DESC
                LIMIT 1
                """,
                (office_id, connection_id),
            ).fetchone()
        return self._decode_sync_run(dict(row)) if row else None

    def create_sync_run(
        self,
        office_id: str,
        *,
        connection_id: int,
        mode: str,
        status: str,
        trigger_type: str = "manual",
        requested_by: str | None = None,
        run_key: str | None = None,
        scheduled_for: str | None = None,
        attempt_count: int = 0,
        max_attempts: int = 3,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            active_statuses = ("queued", "retry_scheduled", "running")
            existing = None
            if run_key:
                existing = conn.execute(
                    """
                    SELECT * FROM integration_sync_runs
                    WHERE office_id=? AND connection_id=? AND run_key=? AND status IN ('queued', 'retry_scheduled', 'running')
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (office_id, connection_id, run_key),
                ).fetchone()
            else:
                existing = conn.execute(
                    """
                    SELECT * FROM integration_sync_runs
                    WHERE office_id=? AND connection_id=? AND mode=? AND status IN ('queued', 'retry_scheduled', 'running')
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (office_id, connection_id, mode),
                ).fetchone()
            if existing and status in active_statuses:
                return self._decode_sync_run(dict(existing))
            conn.execute(
                """
                INSERT INTO integration_sync_runs (
                    office_id, connection_id, mode, trigger_type, status, requested_by, run_key,
                    attempt_count, max_attempts, scheduled_for, started_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    connection_id,
                    mode,
                    trigger_type,
                    status,
                    requested_by,
                    run_key,
                    max(0, attempt_count),
                    max(1, max_attempts),
                    scheduled_for,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            row = conn.execute(
                "SELECT * FROM integration_sync_runs WHERE office_id=? AND connection_id=? ORDER BY id DESC LIMIT 1",
                (office_id, connection_id),
            ).fetchone()
        return self._decode_sync_run(dict(row)) if row else {}

    def claim_sync_run(self, office_id: str, sync_run_id: int, *, lock_token: str) -> dict[str, Any] | None:
        now = self._now()
        stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with self._conn() as conn:
            current = conn.execute(
                "SELECT * FROM integration_sync_runs WHERE office_id=? AND id=?",
                (office_id, sync_run_id),
            ).fetchone()
            if not current:
                return None
            current_row = dict(current)
            if str(current_row.get("status") or "") not in {"queued", "retry_scheduled"}:
                return self._decode_sync_run(current_row)
            active_other = conn.execute(
                """
                SELECT id FROM integration_sync_runs
                WHERE office_id=? AND connection_id=? AND id<>? AND status='running'
                  AND COALESCE(locked_at, started_at) > ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (office_id, current_row.get("connection_id"), sync_run_id, stale_cutoff),
            ).fetchone()
            if active_other:
                return self._decode_sync_run(current_row)
            conn.execute(
                """
                UPDATE integration_sync_runs
                SET status='running', lock_token=?, locked_at=?, started_at=?
                WHERE office_id=? AND id=?
                """,
                (lock_token, now, now, office_id, sync_run_id),
            )
            row = conn.execute(
                "SELECT * FROM integration_sync_runs WHERE office_id=? AND id=?",
                (office_id, sync_run_id),
            ).fetchone()
        return self._decode_sync_run(dict(row)) if row else None

    def recover_stale_sync_runs(self, office_id: str, *, lock_timeout_seconds: int) -> list[dict[str, Any]]:
        if lock_timeout_seconds <= 0:
            return []
        stale_before = (datetime.now(timezone.utc) - timedelta(seconds=max(1, lock_timeout_seconds))).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM integration_sync_runs
                WHERE office_id=? AND status='running' AND COALESCE(locked_at, started_at) <= ?
                ORDER BY id ASC
                """,
                (office_id, stale_before),
            ).fetchall()
            recovered: list[dict[str, Any]] = []
            retry_at = self._now()
            for row in rows:
                item = dict(row)
                error = str(item.get("error") or "").strip()
                if "stale_lock_recovered" not in error:
                    error = f"{error}; stale_lock_recovered".strip("; ").strip()
                conn.execute(
                    """
                    UPDATE integration_sync_runs
                    SET status='retry_scheduled', error=?, next_retry_at=?, scheduled_for=?,
                        lock_token=NULL, locked_at=NULL
                    WHERE office_id=? AND id=?
                    """,
                    (error or "stale_lock_recovered", retry_at, retry_at, office_id, item["id"]),
                )
                updated = conn.execute(
                    "SELECT * FROM integration_sync_runs WHERE office_id=? AND id=?",
                    (office_id, item["id"]),
                ).fetchone()
                if updated:
                    recovered.append(self._decode_sync_run(dict(updated)))
        return recovered

    def reschedule_sync_run(
        self,
        office_id: str,
        sync_run_id: int,
        *,
        error: str,
        next_retry_at: str,
        attempt_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE integration_sync_runs
                SET status='retry_scheduled', error=?, next_retry_at=?, scheduled_for=?, attempt_count=?,
                    lock_token=NULL, locked_at=NULL, metadata_json=?
                WHERE office_id=? AND id=?
                """,
                (
                    error,
                    next_retry_at,
                    next_retry_at,
                    max(0, attempt_count),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    office_id,
                    sync_run_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM integration_sync_runs WHERE office_id=? AND id=?",
                (office_id, sync_run_id),
            ).fetchone()
        return self._decode_sync_run(dict(row)) if row else {}

    def finish_sync_run(
        self,
        office_id: str,
        sync_run_id: int,
        *,
        status: str,
        item_count: int = 0,
        error: str | None = None,
        cursor: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        finished_at = self._now()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE integration_sync_runs
                SET status=?, item_count=?, finished_at=?, error=?, cursor_json=?, metadata_json=?,
                    lock_token=NULL, locked_at=NULL
                WHERE office_id=? AND id=?
                """,
                (
                    status,
                    item_count,
                    finished_at,
                    error,
                    json.dumps(cursor or {}, ensure_ascii=False) if cursor is not None else None,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    office_id,
                    sync_run_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM integration_sync_runs WHERE office_id=? AND id=?",
                (office_id, sync_run_id),
            ).fetchone()
        return self._decode_sync_run(dict(row)) if row else {}

    def list_due_sync_runs(self, office_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        now = self._now()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM integration_sync_runs
                WHERE office_id=?
                  AND status IN ('queued', 'retry_scheduled')
                  AND COALESCE(scheduled_for, started_at) <= ?
                ORDER BY COALESCE(scheduled_for, started_at) ASC, id ASC
                LIMIT ?
                """,
                (office_id, now, max(1, min(limit, 100))),
            ).fetchall()
        return [self._decode_sync_run(dict(row)) for row in rows]

    def list_sync_runs(self, office_id: str, connection_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM integration_sync_runs WHERE office_id=? AND connection_id=? ORDER BY started_at DESC LIMIT ?",
                (office_id, connection_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._decode_sync_run(dict(row)) for row in rows]

    def upsert_record(
        self,
        office_id: str,
        *,
        connection_id: int,
        record_type: str,
        external_id: str,
        title: str | None,
        text_content: str | None,
        content_hash: str | None,
        source_url: str | None,
        permissions: dict[str, Any] | None,
        tags: list[str] | None,
        raw: dict[str, Any] | None,
        normalized: dict[str, Any] | None,
        synced_at: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            conn.execute(
                """
                INSERT INTO integration_records (
                    office_id, connection_id, record_type, external_id, title, text_content, content_hash, source_url,
                    permissions_json, tags_json, raw_json, normalized_json, synced_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(connection_id, record_type, external_id) DO UPDATE SET
                    title=excluded.title,
                    text_content=excluded.text_content,
                    content_hash=excluded.content_hash,
                    source_url=excluded.source_url,
                    permissions_json=excluded.permissions_json,
                    tags_json=excluded.tags_json,
                    raw_json=excluded.raw_json,
                    normalized_json=excluded.normalized_json,
                    synced_at=excluded.synced_at,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    connection_id,
                    record_type,
                    external_id,
                    title,
                    text_content,
                    content_hash,
                    source_url,
                    json.dumps(permissions or {}, ensure_ascii=False),
                    json.dumps(tags or [], ensure_ascii=False),
                    json.dumps(raw or {}, ensure_ascii=False),
                    json.dumps(normalized or {}, ensure_ascii=False),
                    synced_at,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM integration_records WHERE connection_id=? AND record_type=? AND external_id=?",
                (connection_id, record_type, external_id),
            ).fetchone()
        return self._decode_record(dict(row)) if row else {}

    def list_records(self, office_id: str, connection_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM integration_records WHERE office_id=? AND connection_id=? ORDER BY updated_at DESC LIMIT ?",
                (office_id, connection_id, max(1, min(limit, 200))),
            ).fetchall()
        return [self._decode_record(dict(row)) for row in rows]

    def upsert_resource(
        self,
        office_id: str,
        *,
        connection_id: int,
        resource_kind: str,
        external_id: str,
        source_record_type: str,
        title: str | None,
        body_text: str | None,
        search_text: str | None,
        source_url: str | None,
        parent_external_id: str | None,
        owner_label: str | None,
        occurred_at: str | None,
        modified_at: str | None,
        checksum: str | None,
        permissions: dict[str, Any] | None,
        tags: list[str] | None,
        attributes: dict[str, Any] | None,
        sync_metadata: dict[str, Any] | None,
        synced_at: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            conn.execute(
                """
                INSERT INTO integration_resources (
                    office_id, connection_id, resource_kind, external_id, source_record_type, title, body_text,
                    search_text, source_url, parent_external_id, owner_label, occurred_at, modified_at, checksum,
                    permissions_json, tags_json, attributes_json, sync_metadata_json, synced_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(connection_id, resource_kind, external_id) DO UPDATE SET
                    source_record_type=excluded.source_record_type,
                    title=excluded.title,
                    body_text=excluded.body_text,
                    search_text=excluded.search_text,
                    source_url=excluded.source_url,
                    parent_external_id=excluded.parent_external_id,
                    owner_label=excluded.owner_label,
                    occurred_at=excluded.occurred_at,
                    modified_at=excluded.modified_at,
                    checksum=excluded.checksum,
                    permissions_json=excluded.permissions_json,
                    tags_json=excluded.tags_json,
                    attributes_json=excluded.attributes_json,
                    sync_metadata_json=excluded.sync_metadata_json,
                    synced_at=excluded.synced_at,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    connection_id,
                    resource_kind,
                    external_id,
                    source_record_type,
                    title,
                    body_text,
                    search_text,
                    source_url,
                    parent_external_id,
                    owner_label,
                    occurred_at,
                    modified_at,
                    checksum,
                    json.dumps(permissions or {}, ensure_ascii=False),
                    json.dumps(tags or [], ensure_ascii=False),
                    json.dumps(attributes or {}, ensure_ascii=False),
                    json.dumps(sync_metadata or {}, ensure_ascii=False),
                    synced_at,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM integration_resources
                WHERE connection_id=? AND resource_kind=? AND external_id=?
                """,
                (connection_id, resource_kind, external_id),
            ).fetchone()
        return self._decode_resource(dict(row)) if row else {}

    def list_resources(
        self,
        office_id: str,
        connection_id: int,
        *,
        resource_kind: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if resource_kind:
                rows = conn.execute(
                    """
                    SELECT * FROM integration_resources
                    WHERE office_id=? AND connection_id=? AND resource_kind=?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (office_id, connection_id, resource_kind, max(1, min(limit, 200))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM integration_resources
                    WHERE office_id=? AND connection_id=?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (office_id, connection_id, max(1, min(limit, 200))),
                ).fetchall()
        return [self._decode_resource(dict(row)) for row in rows]

    def create_action_run(
        self,
        office_id: str,
        *,
        connection_id: int,
        action_key: str,
        operation: str,
        status: str,
        requested_by: str,
        approval_required: bool,
        approval_state: str,
        input_payload: dict[str, Any] | None = None,
        policy_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            conn.execute(
                """
                INSERT INTO integration_action_runs (
                    office_id, connection_id, action_key, operation, status, requested_by,
                    approval_required, approval_state, input_json, output_json, policy_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    connection_id,
                    action_key,
                    operation,
                    status,
                    requested_by,
                    1 if approval_required else 0,
                    approval_state,
                    json.dumps(input_payload or {}, ensure_ascii=False),
                    json.dumps({}, ensure_ascii=False),
                    json.dumps(policy_payload or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM integration_action_runs WHERE office_id=? AND connection_id=? ORDER BY id DESC LIMIT 1",
                (office_id, connection_id),
            ).fetchone()
        return self._decode_action_run(dict(row)) if row else {}

    def finish_action_run(
        self,
        office_id: str,
        action_run_id: int,
        *,
        status: str,
        approval_state: str,
        output_payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE integration_action_runs
                SET status=?, approval_state=?, output_json=?, error=?, updated_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    status,
                    approval_state,
                    json.dumps(output_payload or {}, ensure_ascii=False),
                    error,
                    now,
                    office_id,
                    action_run_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM integration_action_runs WHERE office_id=? AND id=?",
                (office_id, action_run_id),
            ).fetchone()
        return self._decode_action_run(dict(row)) if row else {}

    def list_action_runs(self, office_id: str, connection_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM integration_action_runs WHERE office_id=? AND connection_id=? ORDER BY created_at DESC LIMIT ?",
                (office_id, connection_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._decode_action_run(dict(row)) for row in rows]

    def log_event(
        self,
        office_id: str,
        *,
        connection_id: int | None,
        connector_id: str | None,
        event_type: str,
        severity: str,
        message: str,
        actor: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            conn.execute(
                """
                INSERT INTO integration_events (
                    office_id, connection_id, connector_id, event_type, severity, message, actor, data_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    connection_id,
                    connector_id,
                    event_type,
                    severity,
                    message,
                    actor,
                    json.dumps(data or {}, ensure_ascii=False),
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM integration_events
                WHERE office_id=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (office_id,),
            ).fetchone()
        return self._decode_event(dict(row)) if row else {}

    def list_events(self, office_id: str, connection_id: int | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if connection_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM integration_events
                    WHERE office_id=?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (office_id, max(1, min(limit, 200))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM integration_events
                    WHERE office_id=? AND connection_id=?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (office_id, connection_id, max(1, min(limit, 200))),
                ).fetchall()
        return [self._decode_event(dict(row)) for row in rows]

    def upsert_generated_connector(
        self,
        office_id: str,
        *,
        connector_id: str,
        service_name: str,
        request_text: str,
        status: str,
        docs_url: str | None,
        openapi_url: str | None,
        openapi_spec: str | None,
        documentation_excerpt: str | None,
        spec: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        last_error: str | None = None,
        created_by: str | None = None,
        enabled: bool | None = None,
        ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            existing = conn.execute(
                "SELECT id, version, enabled FROM integration_generated_connectors WHERE office_id=? AND connector_id=?",
                (office_id, connector_id),
            ).fetchone()
            if existing:
                current = dict(existing)
                conn.execute(
                    """
                    UPDATE integration_generated_connectors
                    SET service_name=?, request_text=?, status=?, version=?, enabled=?, docs_url=?, openapi_url=?, openapi_spec=?,
                        documentation_excerpt=?, spec_json=?, metadata_json=?, last_error=?, updated_at=?
                    WHERE office_id=? AND connector_id=?
                    """,
                    (
                        service_name,
                        request_text,
                        status,
                        int(current.get("version") or 1) + 1,
                        1 if (enabled if enabled is not None else bool(current.get("enabled", 1))) else 0,
                        docs_url,
                        openapi_url,
                        openapi_spec,
                        documentation_excerpt,
                        json.dumps(spec or {}, ensure_ascii=False),
                        json.dumps(metadata or {}, ensure_ascii=False),
                        last_error,
                        now,
                        office_id,
                        connector_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO integration_generated_connectors (
                        office_id, connector_id, service_name, request_text, status, version, enabled, docs_url, openapi_url,
                        openapi_spec, documentation_excerpt, spec_json, metadata_json, last_error,
                        created_by, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        office_id,
                        connector_id,
                        service_name,
                        request_text,
                        status,
                        1,
                        1 if (enabled if enabled is not None else status not in {"archived", "rejected"}) else 0,
                        docs_url,
                        openapi_url,
                        openapi_spec,
                        documentation_excerpt,
                        json.dumps(spec or {}, ensure_ascii=False),
                        json.dumps(metadata or {}, ensure_ascii=False),
                        last_error,
                        created_by,
                        now,
                        now,
                    ),
                )
            row = conn.execute(
                """
                SELECT * FROM integration_generated_connectors
                WHERE office_id=? AND connector_id=?
                """,
                (office_id, connector_id),
            ).fetchone()
            if row:
                row_dict = dict(row)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO integration_generated_connector_versions (
                        office_id, connector_id, version, status, enabled, spec_json, metadata_json, created_by, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        office_id,
                        connector_id,
                        int(row_dict.get("version") or 1),
                        str(row_dict.get("status") or ""),
                        1 if bool(row_dict.get("enabled", 1)) else 0,
                        str(row_dict.get("spec_json") or "{}"),
                        str(row_dict.get("metadata_json") or "{}"),
                        created_by or str(row_dict.get("created_by") or "") or None,
                        now,
                    ),
                )
        return self._decode_generated_connector(dict(row)) if row else {}

    def get_generated_connector(self, office_id: str, connector_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM integration_generated_connectors
                WHERE office_id=? AND connector_id=?
                """,
                (office_id, connector_id),
            ).fetchone()
        return self._decode_generated_connector(dict(row)) if row else None

    def list_generated_connectors(
        self,
        office_id: str,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM integration_generated_connectors
                    WHERE office_id=? AND status=?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (office_id, status, max(1, min(limit, 500))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM integration_generated_connectors
                    WHERE office_id=?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (office_id, max(1, min(limit, 500))),
                ).fetchall()
        return [self._decode_generated_connector(dict(row)) for row in rows]

    def list_generated_connector_versions(self, office_id: str, connector_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM integration_generated_connector_versions
                WHERE office_id=? AND connector_id=?
                ORDER BY version DESC
                LIMIT ?
                """,
                (office_id, connector_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._decode_generated_connector_version(dict(row)) for row in rows]

    def set_generated_connector_enabled(self, office_id: str, connector_id: str, *, enabled: bool) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE integration_generated_connectors
                SET enabled=?, updated_at=?
                WHERE office_id=? AND connector_id=?
                """,
                (1 if enabled else 0, self._now(), office_id, connector_id),
            )
            row = conn.execute(
                """
                SELECT * FROM integration_generated_connectors
                WHERE office_id=? AND connector_id=?
                """,
                (office_id, connector_id),
            ).fetchone()
        return self._decode_generated_connector(dict(row)) if row else None

    def delete_generated_connector(self, office_id: str, connector_id: str) -> bool:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM integration_generated_connector_versions WHERE office_id=? AND connector_id=?",
                (office_id, connector_id),
            )
            deleted = conn.execute(
                "DELETE FROM integration_generated_connectors WHERE office_id=? AND connector_id=?",
                (office_id, connector_id),
            ).rowcount
        return bool(deleted)

    def upsert_connector_pattern(
        self,
        office_id: str,
        *,
        pattern_key: str,
        connector_id: str | None,
        service_name: str,
        category: str | None,
        auth_type: str | None,
        docs_host: str | None,
        base_url: str | None,
        source_kind: str,
        pattern: dict[str, Any],
        success_increment: int = 0,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            existing = conn.execute(
                "SELECT id, success_count FROM integration_connector_patterns WHERE office_id=? AND pattern_key=?",
                (office_id, pattern_key),
            ).fetchone()
            if existing:
                current = dict(existing)
                conn.execute(
                    """
                    UPDATE integration_connector_patterns
                    SET connector_id=?, service_name=?, category=?, auth_type=?, docs_host=?, base_url=?, source_kind=?,
                        success_count=?, pattern_json=?, updated_at=?, last_used_at=?
                    WHERE office_id=? AND pattern_key=?
                    """,
                    (
                        connector_id,
                        service_name,
                        category,
                        auth_type,
                        docs_host,
                        base_url,
                        source_kind,
                        int(current.get("success_count") or 0) + max(success_increment, 0),
                        json.dumps(pattern or {}, ensure_ascii=False),
                        now,
                        now,
                        office_id,
                        pattern_key,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO integration_connector_patterns (
                        office_id, pattern_key, connector_id, service_name, category, auth_type, docs_host, base_url,
                        source_kind, success_count, pattern_json, created_at, updated_at, last_used_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        office_id,
                        pattern_key,
                        connector_id,
                        service_name,
                        category,
                        auth_type,
                        docs_host,
                        base_url,
                        source_kind,
                        max(success_increment, 0),
                        json.dumps(pattern or {}, ensure_ascii=False),
                        now,
                        now,
                        now,
                    ),
                )
            row = conn.execute(
                "SELECT * FROM integration_connector_patterns WHERE office_id=? AND pattern_key=?",
                (office_id, pattern_key),
            ).fetchone()
        return self._decode_connector_pattern(dict(row)) if row else {}

    def list_connector_patterns(self, office_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM integration_connector_patterns
                WHERE office_id=?
                ORDER BY success_count DESC, COALESCE(last_used_at, updated_at) DESC
                LIMIT ?
                """,
                (office_id, max(1, min(limit, 200))),
            ).fetchall()
        return [self._decode_connector_pattern(dict(row)) for row in rows]

    def get_active_assistant_setup(self, office_id: str, thread_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM integration_assistant_setups
                WHERE office_id=? AND thread_id=? AND status NOT IN ('completed', 'cancelled', 'failed', 'abandoned', 'expired')
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (office_id, thread_id),
            ).fetchone()
        return self._decode_assistant_setup(dict(row)) if row else None

    def list_assistant_setups(
        self,
        office_id: str,
        *,
        statuses: tuple[str, ...] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                rows = conn.execute(
                    f"""
                    SELECT * FROM integration_assistant_setups
                    WHERE office_id=? AND status IN ({placeholders})
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ?
                    """,
                    (office_id, *statuses, max(1, min(limit, 1000))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM integration_assistant_setups
                    WHERE office_id=?
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ?
                    """,
                    (office_id, max(1, min(limit, 1000))),
                ).fetchall()
        return [self._decode_assistant_setup(dict(row)) for row in rows]

    def get_assistant_setup(self, office_id: str, setup_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM integration_assistant_setups WHERE office_id=? AND id=?",
                (office_id, setup_id),
            ).fetchone()
        return self._decode_assistant_setup(dict(row)) if row else None

    def upsert_assistant_setup(
        self,
        office_id: str,
        *,
        thread_id: int,
        request_text: str,
        status: str,
        connector_id: str | None = None,
        connection_id: int | None = None,
        service_name: str | None = None,
        missing_fields: list[dict[str, Any]] | None = None,
        collected_config: dict[str, Any] | None = None,
        secret_blob: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
        setup_id: int | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            existing = None
            if setup_id:
                existing = conn.execute(
                    "SELECT * FROM integration_assistant_setups WHERE office_id=? AND id=?",
                    (office_id, setup_id),
                ).fetchone()
            if existing is None:
                existing = conn.execute(
                    """
                    SELECT * FROM integration_assistant_setups
                    WHERE office_id=? AND thread_id=? AND status NOT IN ('completed', 'cancelled', 'failed', 'abandoned', 'expired')
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """,
                    (office_id, thread_id),
                ).fetchone()
            if existing:
                current = dict(existing)
                conn.execute(
                    """
                    UPDATE integration_assistant_setups
                    SET connector_id=?, connection_id=?, service_name=?, request_text=?, status=?, missing_fields_json=?,
                        collected_config_json=?, secret_blob=?, metadata_json=?, updated_at=?, completed_at=?
                    WHERE office_id=? AND id=?
                    """,
                    (
                        connector_id if connector_id is not None else current.get("connector_id"),
                        connection_id if connection_id is not None else current.get("connection_id"),
                        service_name if service_name is not None else current.get("service_name"),
                        request_text or current.get("request_text") or "",
                        status,
                        json.dumps(missing_fields if missing_fields is not None else json.loads(current.get("missing_fields_json") or "[]"), ensure_ascii=False),
                        json.dumps(collected_config if collected_config is not None else json.loads(current.get("collected_config_json") or "{}"), ensure_ascii=False),
                        secret_blob if secret_blob is not None else str(current.get("secret_blob") or ""),
                        json.dumps(metadata if metadata is not None else json.loads(current.get("metadata_json") or "{}"), ensure_ascii=False),
                        now,
                        now if status in {"completed", "cancelled", "failed"} else None,
                        office_id,
                        int(current["id"]),
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM integration_assistant_setups WHERE office_id=? AND id=?",
                    (office_id, int(current["id"])),
                ).fetchone()
            else:
                conn.execute(
                    """
                    INSERT INTO integration_assistant_setups (
                        office_id, thread_id, connector_id, connection_id, service_name, request_text, status,
                        missing_fields_json, collected_config_json, secret_blob, metadata_json, created_by, created_at, updated_at, completed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        office_id,
                        thread_id,
                        connector_id,
                        connection_id,
                        service_name,
                        request_text,
                        status,
                        json.dumps(missing_fields or [], ensure_ascii=False),
                        json.dumps(collected_config or {}, ensure_ascii=False),
                        secret_blob or "",
                        json.dumps(metadata or {}, ensure_ascii=False),
                        created_by,
                        now,
                        now,
                        now if status in {"completed", "cancelled", "failed"} else None,
                    ),
                )
                row = conn.execute(
                    """
                    SELECT * FROM integration_assistant_setups
                    WHERE office_id=? AND thread_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (office_id, thread_id),
                ).fetchone()
        return self._decode_assistant_setup(dict(row)) if row else {}

    def complete_assistant_setup(
        self,
        office_id: str,
        setup_id: int,
        *,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM integration_assistant_setups WHERE office_id=? AND id=?",
                (office_id, setup_id),
            ).fetchone()
            if not row:
                return None
            current = dict(row)
            next_metadata = metadata if metadata is not None else json.loads(current.get("metadata_json") or "{}")
            conn.execute(
                """
                UPDATE integration_assistant_setups
                SET status=?, metadata_json=?, updated_at=?, completed_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    status,
                    json.dumps(next_metadata or {}, ensure_ascii=False),
                    self._now(),
                    self._now(),
                    office_id,
                    setup_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM integration_assistant_setups WHERE office_id=? AND id=?",
                (office_id, setup_id),
            ).fetchone()
        return self._decode_assistant_setup(dict(updated)) if updated else None

    def summarize_launch_metrics(self, office_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            setup_rows = conn.execute(
                """
                SELECT service_name, connector_id, status, metadata_json, updated_at
                FROM integration_assistant_setups
                WHERE office_id=?
                ORDER BY updated_at DESC
                """,
                (office_id,),
            ).fetchall()
            oauth_rows = conn.execute(
                """
                SELECT connector_id, status, created_at, completed_at
                FROM integration_oauth_sessions
                WHERE office_id=?
                ORDER BY created_at DESC
                """,
                (office_id,),
            ).fetchall()
            sync_rows = conn.execute(
                """
                SELECT connection_id, status, trigger_type, started_at, finished_at, error
                FROM integration_sync_runs
                WHERE office_id=?
                ORDER BY started_at DESC
                """,
                (office_id,),
            ).fetchall()
            webhook_rows = conn.execute(
                """
                SELECT connector_id, status, error, received_at
                FROM integration_webhook_events
                WHERE office_id=?
                ORDER BY received_at DESC
                """,
                (office_id,),
            ).fetchall()
            generated_rows = conn.execute(
                """
                SELECT connector_id, service_name, status, enabled, updated_at
                FROM integration_generated_connectors
                WHERE office_id=?
                ORDER BY updated_at DESC
                """,
                (office_id,),
            ).fetchall()

        decoded_setups = [self._decode_assistant_setup(dict(row)) for row in setup_rows]
        setup_status_counts: dict[str, int] = {}
        connector_request_counts: dict[str, int] = {}
        dropoff_counts: dict[str, int] = {}
        for row in decoded_setups:
            status = str(row.get("status") or "unknown")
            setup_status_counts[status] = setup_status_counts.get(status, 0) + 1
            service_name = str(row.get("service_name") or row.get("connector_id") or "Connector")
            connector_request_counts[service_name] = connector_request_counts.get(service_name, 0) + 1
            if status in {"cancelled", "failed", "abandoned", "expired"}:
                metadata = dict(row.get("metadata") or {})
                pending_field = dict(metadata.get("pending_field") or {})
                key = str(pending_field.get("key") or pending_field.get("label") or status).strip() or status
                dropoff_counts[key] = dropoff_counts.get(key, 0) + 1

        oauth_status_counts: dict[str, int] = {}
        for row in oauth_rows:
            status = str(row["status"] or "unknown")
            oauth_status_counts[status] = oauth_status_counts.get(status, 0) + 1

        sync_status_counts: dict[str, int] = {}
        for row in sync_rows:
            status = str(row["status"] or "unknown")
            sync_status_counts[status] = sync_status_counts.get(status, 0) + 1

        webhook_status_counts: dict[str, int] = {}
        for row in webhook_rows:
            status = str(row["status"] or "unknown")
            webhook_status_counts[status] = webhook_status_counts.get(status, 0) + 1

        generated_status_counts: dict[str, int] = {}
        generated_request_counts: dict[str, int] = {}
        for row in generated_rows:
            status = str(row["status"] or "unknown")
            generated_status_counts[status] = generated_status_counts.get(status, 0) + 1
            service_name = str(row["service_name"] or row["connector_id"] or "Connector")
            generated_request_counts[service_name] = generated_request_counts.get(service_name, 0) + 1

        combined_request_counts = dict(connector_request_counts)
        for key, value in generated_request_counts.items():
            combined_request_counts[key] = combined_request_counts.get(key, 0) + int(value or 0)

        return {
            "assistant_setups": {
                "counts": setup_status_counts,
                "top_dropoffs": [
                    {"field": key, "count": count}
                    for key, count in sorted(dropoff_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
                ],
            },
            "oauth_sessions": {"counts": oauth_status_counts},
            "sync_runs": {"counts": sync_status_counts},
            "webhooks": {"counts": webhook_status_counts},
            "generated_connectors": {
                "counts": generated_status_counts,
                "top_requests": [
                    {"service_name": key, "count": count}
                    for key, count in sorted(combined_request_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
                ],
            },
        }

    def record_webhook_event(
        self,
        office_id: str,
        *,
        connector_id: str,
        event_id: str,
        event_type: str,
        status: str,
        payload: dict[str, Any] | None,
        connection_id: int | None = None,
        request_signature: str | None = None,
        request_timestamp: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_office(conn, office_id)
            existing = conn.execute(
                """
                SELECT * FROM integration_webhook_events
                WHERE office_id=? AND connector_id=? AND event_id=?
                """,
                (office_id, connector_id, event_id),
            ).fetchone()
            if existing:
                row = self._decode_webhook_event(dict(existing))
                row["duplicate"] = True
                return row
            conn.execute(
                """
                INSERT OR IGNORE INTO integration_webhook_events (
                    office_id, connection_id, connector_id, event_id, event_type, request_signature,
                    request_timestamp, status, payload_json, response_json, error, received_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    connection_id,
                    connector_id,
                    event_id,
                    event_type,
                    request_signature,
                    request_timestamp,
                    status,
                    json.dumps(payload or {}, ensure_ascii=False),
                    json.dumps({}, ensure_ascii=False),
                    error,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM integration_webhook_events
                WHERE office_id=? AND connector_id=? AND event_id=?
                """,
                (office_id, connector_id, event_id),
            ).fetchone()
        decoded = self._decode_webhook_event(dict(row)) if row else {}
        if decoded:
            decoded["duplicate"] = False
        return decoded

    def finish_webhook_event(
        self,
        office_id: str,
        webhook_event_id: int,
        *,
        status: str,
        response: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE integration_webhook_events
                SET status=?, response_json=?, error=?, processed_at=?
                WHERE office_id=? AND id=?
                """,
                (
                    status,
                    json.dumps(response or {}, ensure_ascii=False),
                    error,
                    self._now(),
                    office_id,
                    webhook_event_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM integration_webhook_events WHERE office_id=? AND id=?",
                (office_id, webhook_event_id),
            ).fetchone()
        return self._decode_webhook_event(dict(row)) if row else {}

    def list_webhook_events(self, office_id: str, *, connection_id: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if connection_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM integration_webhook_events
                    WHERE office_id=?
                    ORDER BY received_at DESC
                    LIMIT ?
                    """,
                    (office_id, max(1, min(limit, 200))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM integration_webhook_events
                    WHERE office_id=? AND connection_id=?
                    ORDER BY received_at DESC
                    LIMIT ?
                    """,
                    (office_id, connection_id, max(1, min(limit, 200))),
                ).fetchall()
        return [self._decode_webhook_event(dict(row)) for row in rows]
