from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Persistence:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS offices (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    deployment_mode TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS matters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    reference_code TEXT,
                    practice_area TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    summary TEXT,
                    client_name TEXT,
                    lead_lawyer TEXT,
                    opened_at TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS matter_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matter_id INTEGER NOT NULL,
                    note_type TEXT NOT NULL,
                    body TEXT NOT NULL,
                    event_at TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS matter_timeline_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matter_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    details TEXT,
                    event_at TEXT NOT NULL,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matter_id INTEGER NOT NULL,
                    office_id TEXT NOT NULL,
                    draft_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    target_channel TEXT NOT NULL,
                    to_contact TEXT,
                    source_context_json TEXT,
                    generated_from TEXT,
                    manual_review_required INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL,
                    approved_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    matter_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    content_type TEXT,
                    source_type TEXT NOT NULL,
                    source_ref TEXT,
                    checksum TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    ingest_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    office_id TEXT NOT NULL,
                    matter_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    matter_id INTEGER NOT NULL,
                    document_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workspace_roots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    root_path_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workspace_scan_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    workspace_root_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    files_seen INTEGER NOT NULL DEFAULT 0,
                    files_indexed INTEGER NOT NULL DEFAULT 0,
                    files_skipped INTEGER NOT NULL DEFAULT 0,
                    files_failed INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (workspace_root_id) REFERENCES workspace_roots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workspace_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL,
                    workspace_root_id INTEGER NOT NULL,
                    relative_path TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    content_type TEXT,
                    size_bytes INTEGER NOT NULL,
                    mtime INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    parser_status TEXT NOT NULL,
                    indexed_status TEXT NOT NULL,
                    document_language TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (workspace_root_id) REFERENCES workspace_roots(id) ON DELETE CASCADE,
                    UNIQUE (workspace_root_id, relative_path)
                );

                CREATE TABLE IF NOT EXISTS workspace_document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_document_id INTEGER NOT NULL,
                    office_id TEXT NOT NULL,
                    workspace_root_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY (workspace_document_id) REFERENCES workspace_documents(id) ON DELETE CASCADE,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (workspace_root_id) REFERENCES workspace_roots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workspace_matter_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matter_id INTEGER NOT NULL,
                    workspace_document_id INTEGER NOT NULL,
                    linked_by TEXT NOT NULL,
                    linked_at TEXT NOT NULL,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE,
                    FOREIGN KEY (workspace_document_id) REFERENCES workspace_documents(id) ON DELETE CASCADE,
                    UNIQUE (matter_id, workspace_document_id)
                );

                CREATE TABLE IF NOT EXISTS draft_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL DEFAULT 'default-office',
                    matter_id INTEGER,
                    title TEXT NOT NULL,
                    due_at TEXT,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    origin_type TEXT,
                    origin_ref TEXT,
                    recommended_by TEXT,
                    explanation TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS email_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    office_id TEXT NOT NULL DEFAULT 'default-office',
                    matter_id INTEGER,
                    to_email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'draft_ready',
                    requested_by TEXT NOT NULL,
                    approved_by TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
                    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS email_draft_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (draft_id) REFERENCES email_drafts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS social_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    handle TEXT NOT NULL,
                    content TEXT NOT NULL,
                    risk_score REAL NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS query_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner TEXT NOT NULL,
                    status TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    model_profile TEXT,
                    continue_in_background INTEGER NOT NULL DEFAULT 1,
                    detached INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    error TEXT,
                    toast_pending INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_matters_office ON matters (office_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_drafts_matter ON drafts (matter_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_timeline_matter ON matter_timeline_events (matter_id, event_at DESC);
                CREATE INDEX IF NOT EXISTS idx_documents_matter ON documents (matter_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks (document_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_document_chunks_scope ON document_chunks (office_id, matter_id, document_id);
                CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_matter ON ingestion_jobs (matter_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_workspace_roots_office ON workspace_roots (office_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_workspace_scan_jobs_root ON workspace_scan_jobs (workspace_root_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_workspace_documents_root ON workspace_documents (workspace_root_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_workspace_document_chunks_doc ON workspace_document_chunks (workspace_document_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_workspace_document_chunks_scope ON workspace_document_chunks (workspace_root_id, workspace_document_id);
                CREATE INDEX IF NOT EXISTS idx_workspace_matter_links_matter ON workspace_matter_links (matter_id, workspace_document_id);
                """
            )
            self._ensure_column(conn, "tasks", "office_id", "TEXT NOT NULL DEFAULT 'default-office'")
            self._ensure_column(conn, "tasks", "matter_id", "INTEGER")
            self._ensure_column(conn, "tasks", "origin_type", "TEXT")
            self._ensure_column(conn, "tasks", "origin_ref", "TEXT")
            self._ensure_column(conn, "tasks", "recommended_by", "TEXT")
            self._ensure_column(conn, "tasks", "explanation", "TEXT")
            self._ensure_column(conn, "tasks", "updated_at", "TEXT")
            self._ensure_column(conn, "matter_notes", "event_at", "TEXT")
            self._ensure_column(conn, "drafts", "source_context_json", "TEXT")
            self._ensure_column(conn, "drafts", "generated_from", "TEXT")
            self._ensure_column(conn, "drafts", "manual_review_required", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "email_drafts", "office_id", "TEXT NOT NULL DEFAULT 'default-office'")
            self._ensure_column(conn, "email_drafts", "matter_id", "INTEGER")
            self._ensure_column(conn, "email_drafts", "review_status", "TEXT NOT NULL DEFAULT 'draft_ready'")
            self._ensure_default_office(conn, "default-office", "Varsayilan Ofis", "local-only")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_matter ON tasks (matter_id, id DESC)")
            conn.execute("UPDATE matter_notes SET event_at=COALESCE(event_at, created_at)")
            conn.execute("UPDATE tasks SET updated_at=COALESCE(updated_at, created_at)")

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
        if column_name in self._table_columns(conn, table_name):
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    def _ensure_default_office(self, conn: sqlite3.Connection, office_id: str, name: str, deployment_mode: str) -> None:
        row = conn.execute("SELECT id FROM offices WHERE id=?", (office_id,)).fetchone()
        if row:
            return
        conn.execute(
            "INSERT INTO offices (id, name, deployment_mode, created_at) VALUES (?, ?, ?, ?)",
            (office_id, name, deployment_mode, self._now()),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def _get_matter_row(self, conn: sqlite3.Connection, matter_id: int, office_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM matters WHERE id=? AND office_id=?",
            (matter_id, office_id),
        ).fetchone()

    def _add_matter_timeline_event(
        self,
        conn: sqlite3.Connection,
        matter_id: int,
        event_type: str,
        title: str,
        details: str | None,
        event_at: str | None,
        created_by: str | None,
    ) -> dict[str, Any]:
        ts = event_at or self._now()
        cur = conn.execute(
            """
            INSERT INTO matter_timeline_events (matter_id, event_type, title, details, event_at, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (matter_id, event_type, title, details, ts, created_by, self._now()),
        )
        row = conn.execute("SELECT * FROM matter_timeline_events WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def store_session(self, session_id: str, subject: str, role: str, expires_at: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (session_id, subject, role, created_at, expires_at, revoked) VALUES (?, ?, ?, ?, ?, 0)",
                (session_id, subject, role, self._now(), expires_at),
            )

    def is_session_active(self, session_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT expires_at FROM sessions WHERE session_id=? AND revoked=0",
                (session_id,),
            ).fetchone()
            if row is None:
                return False
            try:
                expires_at = datetime.fromisoformat(str(row["expires_at"]))
            except ValueError:
                return False
            return expires_at > datetime.now(timezone.utc)

    def revoke_session(self, session_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("UPDATE sessions SET revoked=1 WHERE session_id=?", (session_id,))
            return cur.rowcount > 0

    def create_matter(
        self,
        office_id: str,
        title: str,
        reference_code: str | None,
        practice_area: str | None,
        status: str,
        summary: str | None,
        client_name: str | None,
        lead_lawyer: str | None,
        opened_at: str | None,
        created_by: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            cur = conn.execute(
                """
                INSERT INTO matters (
                    office_id, title, reference_code, practice_area, status, summary,
                    client_name, lead_lawyer, opened_at, created_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    office_id,
                    title,
                    reference_code,
                    practice_area,
                    status,
                    summary,
                    client_name,
                    lead_lawyer,
                    opened_at,
                    created_by,
                    now,
                    now,
                ),
            )
            matter_id = int(cur.lastrowid)
            self._add_matter_timeline_event(
                conn,
                matter_id,
                "matter_created",
                "Dosya oluşturuldu",
                f"{title} oluşturuldu",
                opened_at or now,
                created_by,
            )
            row = self._get_matter_row(conn, matter_id, office_id)
            return dict(row) if row else {}

    def list_matters(self, office_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM matters WHERE office_id=? ORDER BY updated_at DESC, id DESC",
                (office_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_matter(self, matter_id: int, office_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            return self._row_to_dict(self._get_matter_row(conn, matter_id, office_id))

    def update_matter(self, office_id: str, matter_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "title",
            "reference_code",
            "practice_area",
            "status",
            "summary",
            "client_name",
            "lead_lawyer",
            "opened_at",
        }
        updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if not updates:
            return self.get_matter(matter_id, office_id)
        updates["updated_at"] = self._now()
        assignments = ", ".join(f"{key}=?" for key in updates)
        params = [updates[key] for key in updates] + [matter_id, office_id]
        with self._conn() as conn:
            row = self._get_matter_row(conn, matter_id, office_id)
            if not row:
                return None
            conn.execute(f"UPDATE matters SET {assignments} WHERE id=? AND office_id=?", params)
            updated = self._get_matter_row(conn, matter_id, office_id)
            return dict(updated) if updated else None

    def add_matter_note(
        self,
        office_id: str,
        matter_id: int,
        note_type: str,
        body: str,
        created_by: str,
        event_at: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            cur = conn.execute(
                """
                INSERT INTO matter_notes (matter_id, note_type, body, event_at, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (matter_id, note_type, body, event_at or self._now(), created_by, self._now()),
            )
            note = conn.execute("SELECT * FROM matter_notes WHERE id=?", (cur.lastrowid,)).fetchone()
            conn.execute(
                "UPDATE matters SET updated_at=? WHERE id=? AND office_id=?",
                (self._now(), matter_id, office_id),
            )
            self._add_matter_timeline_event(
                conn,
                matter_id,
                "note_added",
                "Dosya notu eklendi",
                body[:240],
                event_at,
                created_by,
            )
            return dict(note) if note else None

    def list_matter_notes(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                "SELECT * FROM matter_notes WHERE matter_id=? ORDER BY event_at DESC, id DESC",
                (matter_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_matter_timeline(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT * FROM matter_timeline_events
                WHERE matter_id=?
                ORDER BY event_at DESC, id DESC
                """,
                (matter_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_matter_summary(self, office_id: str, matter_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            counts = {
                "notes": conn.execute("SELECT COUNT(*) AS c FROM matter_notes WHERE matter_id=?", (matter_id,)).fetchone()["c"],
                "tasks": conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE matter_id=?", (matter_id,)).fetchone()["c"],
                "drafts": conn.execute("SELECT COUNT(*) AS c FROM drafts WHERE matter_id=?", (matter_id,)).fetchone()["c"],
            }
            latest_timeline = conn.execute(
                "SELECT * FROM matter_timeline_events WHERE matter_id=? ORDER BY event_at DESC, id DESC LIMIT 3",
                (matter_id,),
            ).fetchall()
            summary_text = matter["summary"] or (
                f"{matter['title']} dosyası için çalışma özeti. "
                f"Not sayısı: {counts['notes']}, görev sayısı: {counts['tasks']}, taslak sayısı: {counts['drafts']}."
            )
            return {
                "matter": dict(matter),
                "summary": summary_text,
                "counts": counts,
                "latest_timeline": [dict(row) for row in latest_timeline],
                "generated_from": "matter_record" if matter["summary"] else "matter_record_and_counts",
                "manual_review_required": matter["summary"] is None,
            }

    def create_matter_draft(
        self,
        office_id: str,
        matter_id: int,
        draft_type: str,
        title: str,
        body: str,
        target_channel: str,
        to_contact: str | None,
        created_by: str,
        *,
        source_context: dict[str, Any] | None = None,
        generated_from: str | None = None,
        manual_review_required: bool = True,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            cur = conn.execute(
                """
                INSERT INTO drafts (
                    matter_id, office_id, draft_type, title, body, status,
                    target_channel, to_contact, source_context_json, generated_from,
                    manual_review_required, created_by, approved_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    matter_id,
                    office_id,
                    draft_type,
                    title,
                    body,
                    target_channel,
                    to_contact,
                    json.dumps(source_context, ensure_ascii=False) if source_context else None,
                    generated_from,
                    1 if manual_review_required else 0,
                    created_by,
                    now,
                    now,
                ),
            )
            draft_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO draft_events (draft_id, event_type, actor, note, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    draft_id,
                    "draft_generated" if generated_from else "draft_created",
                    created_by,
                    f"{draft_type} taslağı oluşturuldu",
                    now,
                ),
            )
            conn.execute(
                "UPDATE matters SET updated_at=? WHERE id=? AND office_id=?",
                (now, matter_id, office_id),
            )
            self._add_matter_timeline_event(
                conn,
                matter_id,
                "draft_created",
                "Dosya taslağı oluşturuldu",
                title,
                now,
                created_by,
            )
            row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
            return self._decode_draft(dict(row)) if row else None

    def list_matter_drafts(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                "SELECT * FROM drafts WHERE matter_id=? AND office_id=? ORDER BY updated_at DESC, id DESC",
                (matter_id, office_id),
            ).fetchall()
            return [self._decode_draft(dict(row)) for row in rows]

    def list_matter_draft_events(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT e.*, d.title AS draft_title, d.draft_type
                FROM draft_events e
                JOIN drafts d ON d.id = e.draft_id
                WHERE d.matter_id=? AND d.office_id=?
                ORDER BY e.created_at DESC, e.id DESC
                """,
                (matter_id, office_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_active_workspace_root(self, office_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM workspace_roots
                WHERE office_id=? AND status='active'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (office_id,),
            ).fetchone()
            return dict(row) if row else None

    def save_workspace_root(self, office_id: str, display_name: str, root_path: str, root_path_hash: str) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            existing = conn.execute(
                "SELECT id FROM workspace_roots WHERE office_id=? AND root_path_hash=?",
                (office_id, root_path_hash),
            ).fetchone()
            conn.execute("UPDATE workspace_roots SET status='inactive', updated_at=? WHERE office_id=?", (now, office_id))
            if existing:
                conn.execute(
                    """
                    UPDATE workspace_roots
                    SET display_name=?, root_path=?, status='active', updated_at=?
                    WHERE id=?
                    """,
                    (display_name, root_path, now, existing["id"]),
                )
                row = conn.execute("SELECT * FROM workspace_roots WHERE id=?", (existing["id"],)).fetchone()
                return dict(row)
            cur = conn.execute(
                """
                INSERT INTO workspace_roots (office_id, display_name, root_path, root_path_hash, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (office_id, display_name, root_path, root_path_hash, now, now),
            )
            row = conn.execute("SELECT * FROM workspace_roots WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row)

    def create_workspace_scan_job(self, office_id: str, workspace_root_id: int) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            root = conn.execute(
                "SELECT * FROM workspace_roots WHERE id=? AND office_id=?",
                (workspace_root_id, office_id),
            ).fetchone()
            if not root:
                return None
            cur = conn.execute(
                """
                INSERT INTO workspace_scan_jobs (
                    office_id, workspace_root_id, status, files_seen, files_indexed, files_skipped, files_failed, error, created_at, updated_at
                )
                VALUES (?, ?, 'queued', 0, 0, 0, 0, NULL, ?, ?)
                """,
                (office_id, workspace_root_id, now, now),
            )
            row = conn.execute("SELECT * FROM workspace_scan_jobs WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row) if row else None

    def update_workspace_scan_job(
        self,
        office_id: str,
        job_id: int,
        *,
        status: str,
        files_seen: int | None = None,
        files_indexed: int | None = None,
        files_skipped: int | None = None,
        files_failed: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            current = conn.execute(
                "SELECT * FROM workspace_scan_jobs WHERE id=? AND office_id=?",
                (job_id, office_id),
            ).fetchone()
            if not current:
                return None
            conn.execute(
                """
                UPDATE workspace_scan_jobs
                SET status=?, files_seen=?, files_indexed=?, files_skipped=?, files_failed=?, error=?, updated_at=?
                WHERE id=? AND office_id=?
                """,
                (
                    status,
                    files_seen if files_seen is not None else current["files_seen"],
                    files_indexed if files_indexed is not None else current["files_indexed"],
                    files_skipped if files_skipped is not None else current["files_skipped"],
                    files_failed if files_failed is not None else current["files_failed"],
                    error,
                    self._now(),
                    job_id,
                    office_id,
                ),
            )
            row = conn.execute("SELECT * FROM workspace_scan_jobs WHERE id=? AND office_id=?", (job_id, office_id)).fetchone()
            return dict(row) if row else None

    def list_workspace_scan_jobs(self, office_id: str, workspace_root_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM workspace_scan_jobs
                WHERE office_id=? AND workspace_root_id=?
                ORDER BY updated_at DESC, id DESC
                """,
                (office_id, workspace_root_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_workspace_document(
        self,
        office_id: str,
        workspace_root_id: int,
        *,
        relative_path: str,
        display_name: str,
        extension: str,
        content_type: str | None,
        size_bytes: int,
        mtime: int,
        checksum: str,
        parser_status: str,
        indexed_status: str,
        document_language: str,
        last_error: str | None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO workspace_documents (
                    office_id, workspace_root_id, relative_path, display_name, extension, content_type, size_bytes, mtime,
                    checksum, parser_status, indexed_status, document_language, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_root_id, relative_path) DO UPDATE SET
                    display_name=excluded.display_name,
                    extension=excluded.extension,
                    content_type=excluded.content_type,
                    size_bytes=excluded.size_bytes,
                    mtime=excluded.mtime,
                    checksum=excluded.checksum,
                    parser_status=excluded.parser_status,
                    indexed_status=excluded.indexed_status,
                    document_language=excluded.document_language,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (
                    office_id,
                    workspace_root_id,
                    relative_path,
                    display_name,
                    extension,
                    content_type,
                    size_bytes,
                    mtime,
                    checksum,
                    parser_status,
                    indexed_status,
                    document_language,
                    last_error,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM workspace_documents WHERE workspace_root_id=? AND relative_path=?",
                (workspace_root_id, relative_path),
            ).fetchone()
            return dict(row) if row else {}

    def mark_missing_workspace_documents(self, office_id: str, workspace_root_id: int, seen_relative_paths: list[str]) -> int:
        with self._conn() as conn:
            query = """
                UPDATE workspace_documents
                SET indexed_status='missing', updated_at=?
                WHERE office_id=? AND workspace_root_id=?
            """
            params: list[Any] = [self._now(), office_id, workspace_root_id]
            if seen_relative_paths:
                placeholders = ",".join(["?"] * len(seen_relative_paths))
                query += f" AND relative_path NOT IN ({placeholders})"
                params.extend(seen_relative_paths)
            cur = conn.execute(query, params)
            return cur.rowcount

    def replace_workspace_document_chunks(
        self,
        office_id: str,
        workspace_root_id: int,
        workspace_document_id: int,
        chunks: list[dict[str, Any]],
    ) -> int:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM workspace_document_chunks WHERE office_id=? AND workspace_root_id=? AND workspace_document_id=?",
                (office_id, workspace_root_id, workspace_document_id),
            )
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO workspace_document_chunks (
                        workspace_document_id, office_id, workspace_root_id, chunk_index, text, token_count, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workspace_document_id,
                        office_id,
                        workspace_root_id,
                        chunk["chunk_index"],
                        chunk["text"],
                        chunk["token_count"],
                        chunk["metadata_json"],
                    ),
                )
            return len(chunks)

    def get_workspace_document(self, office_id: str, workspace_document_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT d.*, r.display_name AS workspace_root_name, r.root_path
                FROM workspace_documents d
                JOIN workspace_roots r ON r.id = d.workspace_root_id
                WHERE d.office_id=? AND d.id=?
                """,
                (office_id, workspace_document_id),
            ).fetchone()
            return dict(row) if row else None

    def list_workspace_documents(
        self,
        office_id: str,
        workspace_root_id: int,
        *,
        query_text: str | None = None,
        extension: str | None = None,
        status: str | None = None,
        path_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = """
                SELECT d.*, COUNT(c.id) AS chunk_count
                FROM workspace_documents d
                LEFT JOIN workspace_document_chunks c ON c.workspace_document_id = d.id
                WHERE d.office_id=? AND d.workspace_root_id=?
            """
            params: list[Any] = [office_id, workspace_root_id]
            if query_text:
                pattern = f"%{query_text}%"
                query += " AND (d.display_name LIKE ? OR d.relative_path LIKE ?)"
                params.extend([pattern, pattern])
            if extension:
                query += " AND d.extension=?"
                params.append(extension)
            if status:
                query += " AND d.indexed_status=?"
                params.append(status)
            if path_prefix:
                query += " AND d.relative_path LIKE ?"
                params.append(f"{path_prefix.rstrip('/')}%")
            query += " GROUP BY d.id ORDER BY d.updated_at DESC, d.id DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def list_workspace_document_chunks(self, office_id: str, workspace_document_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            document = self.get_workspace_document(office_id, workspace_document_id)
            if not document:
                return None
            rows = conn.execute(
                """
                SELECT c.*, d.display_name, d.relative_path, d.extension
                FROM workspace_document_chunks c
                JOIN workspace_documents d ON d.id = c.workspace_document_id
                WHERE c.office_id=? AND c.workspace_document_id=?
                ORDER BY c.chunk_index ASC
                """,
                (office_id, workspace_document_id),
            ).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                try:
                    item["metadata"] = json.loads(str(item.get("metadata_json") or "{}"))
                except json.JSONDecodeError:
                    item["metadata"] = {}
                items.append(item)
            return items

    def search_workspace_document_chunks(
        self,
        office_id: str,
        workspace_root_id: int,
        *,
        path_prefix: str | None = None,
        extensions: list[str] | None = None,
        workspace_document_id: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            query = """
                SELECT
                    c.id,
                    c.workspace_document_id AS document_id,
                    c.workspace_root_id,
                    c.office_id,
                    c.chunk_index,
                    c.text,
                    c.token_count,
                    c.metadata_json,
                    d.display_name,
                    d.relative_path,
                    d.extension,
                    d.content_type,
                    d.checksum,
                    'workspace' AS source_type,
                    NULL AS matter_id
                FROM workspace_document_chunks c
                JOIN workspace_documents d ON d.id = c.workspace_document_id
                WHERE c.office_id=? AND c.workspace_root_id=? AND d.indexed_status='indexed'
            """
            params: list[Any] = [office_id, workspace_root_id]
            if workspace_document_id is not None:
                query += " AND c.workspace_document_id=?"
                params.append(workspace_document_id)
            if path_prefix:
                query += " AND d.relative_path LIKE ?"
                params.append(f"{path_prefix.rstrip('/')}%")
            if extensions:
                placeholders = ",".join(["?"] * len(extensions))
                query += f" AND d.extension IN ({placeholders})"
                params.extend(extensions)
            query += " ORDER BY c.workspace_document_id ASC, c.chunk_index ASC"
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def attach_workspace_document_to_matter(self, office_id: str, matter_id: int, workspace_document_id: int, linked_by: str) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            document = conn.execute(
                "SELECT * FROM workspace_documents WHERE office_id=? AND id=?",
                (office_id, workspace_document_id),
            ).fetchone()
            if not document:
                return None
            conn.execute(
                """
                INSERT OR IGNORE INTO workspace_matter_links (matter_id, workspace_document_id, linked_by, linked_at)
                VALUES (?, ?, ?, ?)
                """,
                (matter_id, workspace_document_id, linked_by, now),
            )
            self._add_matter_timeline_event(
                conn,
                matter_id,
                "workspace_document_attached",
                "Çalışma alanı belgesi bağlandı",
                str(document["display_name"]),
                now,
                linked_by,
            )
            row = conn.execute(
                """
                SELECT l.*, d.display_name, d.relative_path, d.extension, d.indexed_status
                FROM workspace_matter_links l
                JOIN workspace_documents d ON d.id = l.workspace_document_id
                WHERE l.matter_id=? AND l.workspace_document_id=?
                """,
                (matter_id, workspace_document_id),
            ).fetchone()
            return dict(row) if row else None

    def list_matter_workspace_documents(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT l.*, d.display_name, d.relative_path, d.extension, d.indexed_status, d.workspace_root_id
                FROM workspace_matter_links l
                JOIN workspace_documents d ON d.id = l.workspace_document_id
                WHERE l.matter_id=?
                ORDER BY l.linked_at DESC, l.id DESC
                """,
                (matter_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def search_linked_workspace_chunks(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT
                    c.id,
                    c.workspace_document_id AS document_id,
                    c.workspace_root_id,
                    c.office_id,
                    c.chunk_index,
                    c.text,
                    c.token_count,
                    c.metadata_json,
                    d.display_name,
                    d.relative_path,
                    d.extension,
                    d.content_type,
                    d.checksum,
                    'workspace' AS source_type,
                    ? AS matter_id
                FROM workspace_document_chunks c
                JOIN workspace_documents d ON d.id = c.workspace_document_id
                JOIN workspace_matter_links l ON l.workspace_document_id = d.id
                WHERE d.office_id=? AND l.matter_id=? AND d.indexed_status='indexed'
                ORDER BY c.workspace_document_id ASC, c.chunk_index ASC
                """,
                (matter_id, office_id, matter_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_document(
        self,
        office_id: str,
        matter_id: int,
        filename: str,
        display_name: str,
        content_type: str | None,
        source_type: str,
        source_ref: str | None,
        checksum: str,
        size_bytes: int,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            cur = conn.execute(
                """
                INSERT INTO documents (
                    office_id, matter_id, filename, display_name, content_type, source_type, source_ref,
                    checksum, size_bytes, ingest_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (
                    office_id,
                    matter_id,
                    filename,
                    display_name,
                    content_type,
                    source_type,
                    source_ref,
                    checksum,
                    size_bytes,
                    now,
                    now,
                ),
            )
            document_id = int(cur.lastrowid)
            self._add_matter_timeline_event(
                conn,
                matter_id,
                "document_registered",
                "Dosya belgesi kaydedildi",
                display_name,
                now,
                None,
            )
            row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            return dict(row) if row else None

    def get_document(self, office_id: str, matter_id: int, document_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id=? AND office_id=? AND matter_id=?",
                (document_id, office_id, matter_id),
            ).fetchone()
            return dict(row) if row else None

    def get_document_global(self, office_id: str, document_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id=? AND office_id=?",
                (document_id, office_id),
            ).fetchone()
            return dict(row) if row else None

    def list_matter_documents(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT d.*, COUNT(c.id) AS chunk_count
                FROM documents d
                LEFT JOIN document_chunks c ON c.document_id = d.id
                WHERE d.office_id=? AND d.matter_id=?
                GROUP BY d.id
                ORDER BY d.updated_at DESC, d.id DESC
                """,
                (office_id, matter_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_document_status(self, office_id: str, document_id: int, status: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE documents SET ingest_status=?, updated_at=? WHERE id=? AND office_id=?",
                (status, self._now(), document_id, office_id),
            )
            row = conn.execute("SELECT * FROM documents WHERE id=? AND office_id=?", (document_id, office_id)).fetchone()
            return dict(row) if row else None

    def record_matter_event(
        self,
        office_id: str,
        matter_id: int,
        event_type: str,
        title: str,
        details: str | None,
        event_at: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            return self._add_matter_timeline_event(conn, matter_id, event_type, title, details, event_at, created_by)

    def create_ingestion_job(self, office_id: str, matter_id: int, document_id: int) -> dict[str, Any]:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO ingestion_jobs (office_id, matter_id, document_id, status, error, created_at, updated_at)
                VALUES (?, ?, ?, 'queued', NULL, ?, ?)
                """,
                (office_id, matter_id, document_id, now, now),
            )
            row = conn.execute("SELECT * FROM ingestion_jobs WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row)

    def update_ingestion_job(
        self,
        office_id: str,
        job_id: int,
        status: str,
        *,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE ingestion_jobs SET status=?, error=?, updated_at=? WHERE id=? AND office_id=?",
                (status, error, self._now(), job_id, office_id),
            )
            row = conn.execute("SELECT * FROM ingestion_jobs WHERE id=? AND office_id=?", (job_id, office_id)).fetchone()
            return dict(row) if row else None

    def list_matter_ingestion_jobs(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                """
                SELECT j.*, d.display_name AS document_name, d.filename
                FROM ingestion_jobs j
                JOIN documents d ON d.id = j.document_id
                WHERE j.office_id=? AND j.matter_id=?
                ORDER BY j.updated_at DESC, j.id DESC
                """,
                (office_id, matter_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def replace_document_chunks(
        self,
        office_id: str,
        matter_id: int,
        document_id: int,
        chunks: list[dict[str, Any]],
    ) -> int:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM document_chunks WHERE office_id=? AND matter_id=? AND document_id=?",
                (office_id, matter_id, document_id),
            )
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO document_chunks (
                        document_id, office_id, matter_id, chunk_index, text, token_count, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        office_id,
                        matter_id,
                        chunk["chunk_index"],
                        chunk["text"],
                        chunk["token_count"],
                        chunk["metadata_json"],
                    ),
                )
            return len(chunks)

    def list_document_chunks(self, office_id: str, document_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            document = conn.execute(
                "SELECT * FROM documents WHERE id=? AND office_id=?",
                (document_id, office_id),
            ).fetchone()
            if not document:
                return None
            rows = conn.execute(
                """
                SELECT c.*, d.display_name, d.filename, d.source_type
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.document_id=? AND c.office_id=?
                ORDER BY c.chunk_index ASC
                """,
                (document_id, office_id),
            ).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                try:
                    item["metadata"] = json.loads(str(item.get("metadata_json") or "{}"))
                except json.JSONDecodeError:
                    item["metadata"] = {}
                items.append(item)
            return items

    def search_document_chunks(
        self,
        office_id: str,
        matter_id: int,
        *,
        document_ids: list[int] | None = None,
        source_types: list[str] | None = None,
        filename_contains: str | None = None,
    ) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            query = """
                SELECT c.*, d.display_name, d.filename, d.source_type, d.content_type, d.source_ref
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.office_id=? AND c.matter_id=? AND d.ingest_status='indexed'
            """
            params: list[Any] = [office_id, matter_id]
            if document_ids:
                placeholders = ",".join(["?"] * len(document_ids))
                query += f" AND c.document_id IN ({placeholders})"
                params.extend(document_ids)
            if source_types:
                placeholders = ",".join(["?"] * len(source_types))
                query += f" AND d.source_type IN ({placeholders})"
                params.extend(source_types)
            if filename_contains:
                query += " AND (d.filename LIKE ? OR d.display_name LIKE ?)"
                pattern = f"%{filename_contains}%"
                params.extend([pattern, pattern])
            query += " ORDER BY c.document_id ASC, c.chunk_index ASC"
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def create_task(
        self,
        title: str,
        due_at: str | None,
        priority: str,
        owner: str,
        *,
        office_id: str = "default-office",
        matter_id: int | None = None,
        origin_type: str | None = None,
        origin_ref: str | None = None,
        recommended_by: str | None = None,
        explanation: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            if matter_id is not None and not self._get_matter_row(conn, matter_id, office_id):
                raise ValueError("Dosya bulunamadı.")
            now = self._now()
            cur = conn.execute(
                """
                INSERT INTO tasks (
                    office_id, matter_id, title, due_at, priority, status, owner,
                    origin_type, origin_ref, recommended_by, explanation, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
                """,
                (office_id, matter_id, title, due_at, priority, owner, origin_type, origin_ref, recommended_by, explanation, now, now),
            )
            task_id = cur.lastrowid
            if matter_id is not None:
                self._add_matter_timeline_event(
                    conn,
                    matter_id,
                    "task_created",
                    "Dosya görevi oluşturuldu",
                    title,
                    due_at,
                    owner,
                )
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(row)

    def list_matter_tasks(self, office_id: str, matter_id: int) -> list[dict[str, Any]] | None:
        with self._conn() as conn:
            matter = self._get_matter_row(conn, matter_id, office_id)
            if not matter:
                return None
            rows = conn.execute(
                "SELECT * FROM tasks WHERE office_id=? AND matter_id=? ORDER BY updated_at DESC, id DESC",
                (office_id, matter_id),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_tasks(self, owner: str, matter_id: int | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if matter_id is None:
                rows = conn.execute("SELECT * FROM tasks WHERE owner=? ORDER BY id DESC", (owner,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE owner=? AND matter_id=? ORDER BY id DESC",
                    (owner, matter_id),
                ).fetchall()
            return [dict(r) for r in rows]

    def complete_tasks_bulk(self, task_ids: list[int], owner: str) -> int:
        if not task_ids:
            return 0
        placeholders = ",".join(["?"] * len(task_ids))
        params = [*task_ids, owner]
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM tasks WHERE id IN ({placeholders}) AND owner=? AND status!='completed'",
                params,
            ).fetchall()
            cur = conn.execute(
                f"UPDATE tasks SET status='completed', updated_at=? WHERE id IN ({placeholders}) AND owner=? AND status!='completed'",
                [self._now(), *params],
            )
            for row in rows:
                if row["matter_id"] is not None:
                    self._add_matter_timeline_event(
                        conn,
                        int(row["matter_id"]),
                        "task_completed",
                        "Dosya görevi tamamlandı",
                        str(row["title"]),
                        self._now(),
                        owner,
                    )
            return int(cur.rowcount or 0)

    def update_task_status(self, task_id: int, status: str, owner: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
            if not row:
                return None
            conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=? AND owner=?", (status, self._now(), task_id, owner))
            if row["matter_id"] is not None:
                self._add_matter_timeline_event(
                    conn,
                    int(row["matter_id"]),
                    "task_status_updated",
                    "Dosya görevi durumu değişti",
                    f"{row['title']} -> {status}",
                    self._now(),
                    owner,
                )
            updated = conn.execute("SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
            return dict(updated) if updated else None

    def update_task_due_at(self, task_id: int, due_at: str | None, owner: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
            if not row:
                return None
            conn.execute("UPDATE tasks SET due_at=?, updated_at=? WHERE id=? AND owner=?", (due_at, self._now(), task_id, owner))
            if row["matter_id"] is not None:
                self._add_matter_timeline_event(
                    conn,
                    int(row["matter_id"]),
                    "task_due_updated",
                    "Dosya görevi tarihi güncellendi",
                    f"{row['title']} -> {due_at or 'temizlendi'}",
                    due_at or self._now(),
                    owner,
                )
            updated = conn.execute("SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
            return dict(updated) if updated else None

    @staticmethod
    def _decode_draft(row: dict[str, Any]) -> dict[str, Any]:
        if row.get("source_context_json"):
            try:
                row["source_context"] = json.loads(row["source_context_json"])
            except json.JSONDecodeError:
                row["source_context"] = None
        else:
            row["source_context"] = None
        row["manual_review_required"] = bool(row.get("manual_review_required"))
        row.pop("source_context_json", None)
        return row

    def create_query_job(self, owner: str, query_text: str, model_profile: str | None, continue_in_background: bool) -> dict:
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO query_jobs (owner, status, query_text, model_profile, continue_in_background, created_at, updated_at)
                VALUES (?, 'running', ?, ?, ?, ?, ?)
                """,
                (owner, query_text, model_profile, 1 if continue_in_background else 0, now, now),
            )
            row = conn.execute("SELECT * FROM query_jobs WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._decode_query_job(dict(row))

    def get_query_job(self, job_id: int, owner: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            return self._decode_query_job(dict(row)) if row else None

    def list_query_jobs(self, owner: str, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM query_jobs WHERE owner=? ORDER BY id DESC LIMIT ?",
                (owner, max(1, min(limit, 100))),
            ).fetchall()
            return [self._decode_query_job(dict(row)) for row in rows]

    def update_query_job_status(
        self,
        job_id: int,
        owner: str,
        status: str,
        *,
        result: dict | None = None,
        error: str | None = None,
        detached: bool | None = None,
        toast_pending: bool | None = None,
    ) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            if not row:
                return None
            current = dict(row)
            result_json = json.dumps(result, ensure_ascii=False) if result is not None else current.get("result_json")
            detached_val = current["detached"] if detached is None else (1 if detached else 0)
            toast_val = current["toast_pending"] if toast_pending is None else (1 if toast_pending else 0)
            completed_at = self._now() if status in {"completed", "cancelled", "failed"} else None
            conn.execute(
                """
                UPDATE query_jobs
                SET status=?, result_json=?, error=?, detached=?, toast_pending=?, updated_at=?, completed_at=COALESCE(?, completed_at)
                WHERE id=? AND owner=?
                """,
                (status, result_json, error, detached_val, toast_val, self._now(), completed_at, job_id, owner),
            )
            updated = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            return self._decode_query_job(dict(updated)) if updated else None

    def request_query_job_cancel(self, job_id: int, owner: str, keep_background: bool) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            if not row:
                return None
            if keep_background:
                conn.execute(
                    "UPDATE query_jobs SET detached=1, updated_at=? WHERE id=? AND owner=?",
                    (self._now(), job_id, owner),
                )
            else:
                conn.execute(
                    "UPDATE query_jobs SET cancel_requested=1, updated_at=? WHERE id=? AND owner=?",
                    (self._now(), job_id, owner),
                )
            updated = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            return self._decode_query_job(dict(updated)) if updated else None

    def acknowledge_query_job_toast(self, job_id: int, owner: str) -> dict | None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE query_jobs SET toast_pending=0, updated_at=? WHERE id=? AND owner=?",
                (self._now(), job_id, owner),
            )
            row = conn.execute("SELECT * FROM query_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            return self._decode_query_job(dict(row)) if row else None

    @staticmethod
    def _decode_query_job(row: dict) -> dict:
        if row.get("result_json"):
            try:
                row["result"] = json.loads(row["result_json"])
            except json.JSONDecodeError:
                row["result"] = None
        else:
            row["result"] = None
        row["continue_in_background"] = bool(row.get("continue_in_background"))
        row["detached"] = bool(row.get("detached"))
        row["cancel_requested"] = bool(row.get("cancel_requested"))
        row["toast_pending"] = bool(row.get("toast_pending"))
        row.pop("result_json", None)
        return row

    def _add_email_event(self, conn: sqlite3.Connection, draft_id: int, event_type: str, actor: str, note: str | None = None) -> None:
        conn.execute(
            "INSERT INTO email_draft_events (draft_id, event_type, actor, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (draft_id, event_type, actor, note, self._now()),
        )

    def create_email_draft(
        self,
        to_email: str,
        subject: str,
        body: str,
        requested_by: str,
        *,
        office_id: str = "default-office",
        matter_id: int | None = None,
    ) -> dict:
        with self._conn() as conn:
            self._ensure_default_office(conn, office_id, "Varsayilan Ofis", "local-only")
            if matter_id is not None and not self._get_matter_row(conn, matter_id, office_id):
                raise ValueError("Dosya bulunamadı.")
            cur = conn.execute(
                """
                INSERT INTO email_drafts (office_id, matter_id, to_email, subject, body, status, review_status, requested_by, created_at)
                VALUES (?, ?, ?, ?, ?, 'draft', 'draft_ready', ?, ?)
                """,
                (office_id, matter_id, to_email, subject, body, requested_by, self._now()),
            )
            draft_id = int(cur.lastrowid)
            self._add_email_event(conn, draft_id, "draft_created", requested_by, "Taslak oluşturuldu")
            if matter_id is not None:
                self._add_matter_timeline_event(
                    conn,
                    matter_id,
                    "external_draft_created",
                    "Email draft created",
                    subject,
                    self._now(),
                    requested_by,
                )
            row = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            return dict(row)

    def approve_email_draft(self, draft_id: int, approved_by: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            if not row:
                return None
            if row["status"] != "draft":
                return dict(row)
            conn.execute(
                "UPDATE email_drafts SET status='approved', review_status='approved', approved_by=? WHERE id=?",
                (approved_by, draft_id),
            )
            self._add_email_event(conn, draft_id, "approved", approved_by, "Taslak onaylandı")
            updated = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            return dict(updated) if updated else None

    def retract_email_draft(self, draft_id: int, actor: str, note: str | None = None) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            if not row:
                return None
            if row["status"] != "approved":
                return dict(row)
            conn.execute(
                "UPDATE email_drafts SET status='draft', review_status='draft_ready', approved_by=NULL WHERE id=?",
                (draft_id,),
            )
            self._add_email_event(conn, draft_id, "retracted", actor, note or "Tek tık geri çekme")
            updated = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            return dict(updated) if updated else None

    def get_email_draft(self, draft_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
            return dict(row) if row else None

    def list_email_drafts(self, owner: str | None = None) -> list[dict]:
        with self._conn() as conn:
            if owner:
                rows = conn.execute(
                    "SELECT * FROM email_drafts WHERE requested_by=? ORDER BY id DESC",
                    (owner,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM email_drafts ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]

    def list_email_draft_events(self, draft_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM email_draft_events WHERE draft_id=? ORDER BY id DESC",
                (draft_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def add_social_event(self, source: str, handle: str, content: str, risk_score: float) -> dict:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO social_events (source, handle, content, risk_score, created_at) VALUES (?, ?, ?, ?, ?)",
                (source, handle, content, risk_score, self._now()),
            )
            row = conn.execute("SELECT * FROM social_events WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row)

    def list_social_events(self, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM social_events ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
            return [dict(r) for r in rows]
