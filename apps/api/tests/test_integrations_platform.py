import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
import httpx

from lawcopilot_api.app import create_app
from lawcopilot_api.api.routes.integrations import create_integrations_router
from lawcopilot_api.auth import issue_token
from lawcopilot_api.audit import AuditLogger
from lawcopilot_api.config import get_settings
from lawcopilot_api.integrations.models import (
    IntegrationActionRequest,
    IntegrationAutomationRequest,
    IntegrationConnectionPayload,
    IntegrationGeneratedConnectorRefreshRequest,
    IntegrationGeneratedConnectorReviewRequest,
    IntegrationGeneratedConnectorStateRequest,
    IntegrationJobDispatchRequest,
    IntegrationOAuthCallbackRequest,
    IntegrationOAuthStartRequest,
    IntegrationSafetySettingsRequest,
    IntegrationScaffoldRequest,
    IntegrationSyncScheduleRequest,
)
from lawcopilot_api.integrations.repository import IntegrationRepository
from lawcopilot_api.integrations.runtime import hmac_sha256
from lawcopilot_api.integrations.secret_box import CONTEXT_V1, PREFIX_V1, SecretBox, _keystream, _xor
from lawcopilot_api.integrations.service import IntegrationPlatformService
from lawcopilot_api.integrations.worker import IntegrationSyncWorker
from lawcopilot_api.persistence import Persistence


def _configure_runtime_env(monkeypatch) -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="lawcopilot-integrations-platform-"))
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(temp_root / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(temp_root / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(temp_root / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_CONNECTOR_DRY_RUN", "true")
    return temp_root


def _build_mock_provider_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        host = request.url.host or ""
        if host == "api.notion.com":
            if path == "/v1/users/me":
                return httpx.Response(200, json={"object": "user", "name": "LawCopilot Notion"})
            if path == "/v1/search":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "object": "page",
                                "id": "page-1",
                                "url": "https://notion.so/page-1",
                                "last_edited_time": "2026-04-08T08:00:00+00:00",
                                "properties": {
                                    "Name": {
                                        "title": [
                                            {"plain_text": "Dava checklisti"},
                                        ]
                                    }
                                },
                            },
                            {
                                "object": "database",
                                "id": "db-1",
                                "url": "https://notion.so/db-1",
                                "last_edited_time": "2026-04-08T09:00:00+00:00",
                                "title": [{"plain_text": "Muvekkil takip tablosu"}],
                            },
                        ]
                    },
                )
        if host == "github.com" and path == "/login/oauth/access_token":
            return httpx.Response(
                200,
                json={
                    "access_token": "github-access",
                    "refresh_token": "github-refresh",
                    "token_type": "Bearer",
                    "scope": "read:user read:org repo",
                    "expires_in": 3600,
                },
            )
        if host == "api.github.com":
            if path == "/user":
                return httpx.Response(200, json={"login": "octocat"})
            if path == "/user/repos":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 101,
                            "name": "lawcopilot",
                            "full_name": "octocat/lawcopilot",
                            "description": "Integration runtime",
                            "html_url": "https://github.com/octocat/lawcopilot",
                            "updated_at": "2026-04-08T10:00:00+00:00",
                        }
                    ],
                )
            if path == "/search/repositories":
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": 101,
                                "name": "lawcopilot",
                                "full_name": "octocat/lawcopilot",
                                "description": "Integration runtime",
                                "html_url": "https://github.com/octocat/lawcopilot",
                                "updated_at": "2026-04-08T10:00:00+00:00",
                            }
                        ]
                    },
                )
        if host == "slack.com":
            if path == "/api/oauth.v2.access":
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "access_token": "xoxb-slack-access",
                        "refresh_token": "xoxe-slack-refresh",
                        "token_type": "Bearer",
                        "scope": "channels:read,channels:history,chat:write",
                        "expires_in": 3600,
                    },
                )
            if path == "/api/auth.revoke":
                return httpx.Response(200, json={"ok": True})
            if path == "/api/auth.test":
                return httpx.Response(200, json={"ok": True, "team": "LawCopilot Slack"})
            if path == "/api/conversations.list":
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "channels": [
                            {"id": "C123", "name": "genel", "topic": {"value": "Ofis kanali"}},
                        ],
                    },
                )
            if path == "/api/conversations.history":
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "messages": [
                            {"ts": "1712563200.000100", "text": "Slack webhook ve sync testi", "user": "U123"},
                        ],
                    },
                )
            if path == "/api/chat.postMessage":
                return httpx.Response(200, json={"ok": True, "channel": "C123", "ts": "1712563200.000200"})
        if host == "open.tiktokapis.com":
            if path == "/v2/oauth/token/":
                body_text = request.content.decode("utf-8")
                assert "client_key=" in body_text
                return httpx.Response(
                    200,
                    json={
                        "access_token": "tiktok-access",
                        "refresh_token": "tiktok-refresh",
                        "token_type": "Bearer",
                        "scope": "user.info.basic,video.list",
                        "expires_in": 3600,
                    },
                )
            if path == "/v2/oauth/revoke/":
                return httpx.Response(200, json={"error": {"code": "ok", "message": ""}})
            if path == "/v2/user/info/":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "open_id": "tiktok-open-id",
                            "display_name": "LawCopilot TikTok",
                            "bio_description": "Hukuk icerikleri",
                            "follower_count": 42,
                            "video_count": 5,
                        },
                        "error": {"code": "ok", "message": "", "log_id": "unit-test"},
                    },
                )
        if host == "docs.acme.example":
            if path == "/openapi.json":
                return httpx.Response(
                    200,
                    json={
                        "openapi": "3.0.0",
                        "paths": {
                            "/channels": {"get": {"summary": "List channels"}},
                            "/channels/search": {"get": {"summary": "Search channels"}},
                        },
                        "components": {
                            "securitySchemes": {
                                "oauth": {"type": "oauth2"},
                            }
                        },
                    },
                )
            if path == "/guide":
                return httpx.Response(
                    200,
                    text="""
                    <html><body>
                    <h1>Acme Desk API</h1>
                    <p>OAuth 2.0 ile yetkilendirme yapin. channels ve messages endpointlerini kullanin.</p>
                    </body></html>
                    """,
                    headers={"content-type": "text/html"},
                )
        if host == "elastic.example.com":
            if path == "/_cluster/health":
                return httpx.Response(200, json={"cluster_name": "lawcopilot-dev", "status": "green"})
            if path == "/_sql":
                body = json.loads(request.content.decode("utf-8") or "{}") if request.content else {}
                return httpx.Response(
                    200,
                    json={
                        "columns": [
                            {"name": "title", "type": "text"},
                            {"name": "summary", "type": "text"},
                        ],
                        "rows": [
                            [
                                "Slack onboarding notu",
                                f"sql={body.get('query')}",
                            ]
                        ],
                    },
                )
            if path in {"/cases-*/_search", "/cases-archive/_search"}:
                body = json.loads(request.content.decode("utf-8") or "{}") if request.content else {}
                query_text = json.dumps(body, ensure_ascii=False)
                return httpx.Response(
                    200,
                    json={
                        "hits": {
                            "hits": [
                                {
                                    "_index": "cases-2026",
                                    "_id": "doc-1",
                                    "_score": 1.0,
                                    "_source": {
                                        "title": "Slack onboarding notu",
                                        "summary": "Elastic entegrasyonu ve Slack setup akisi",
                                        "body": f"sorgu={query_text}",
                                        "@timestamp": "2026-04-08T10:00:00+00:00",
                                    },
                                }
                            ]
                        }
                    },
                )
        return httpx.Response(404, json={"error": f"unhandled:{host}{path}"})

    return httpx.MockTransport(handler)


class FakePostgresAdapter:
    def validate_connection(self, *, connection, secrets):
        return {"message": "PostgreSQL baglantisi dogrulandi."}

    def list_tables(self, *, connection, secrets, schema):
        return ["cases"]

    def detect_cursor_column(self, *, connection, secrets, schema, table):
        return "updated_at"

    def fetch_rows(self, *, connection, secrets, schema, table, limit, cursor_column, cursor_value):
        return [{"id": 1, "title": "CASE-1", "updated_at": "2026-04-08T11:00:00+00:00"}]

    def run_query(self, *, connection, secrets, query, params):
        return [{"ok": 1}]

    def insert_record(self, *, connection, secrets, schema, table, data):
        return {"inserted": True, "table": table, "data": data}

    def update_record(self, *, connection, secrets, schema, table, data, where):
        return {"updated": True, "table": table, "data": data, "where": where}

    def delete_record(self, *, connection, secrets, schema, table, where):
        return {"deleted": True, "table": table, "where": where}


class FakeWebIntelService:
    def __init__(self, responses_by_url: dict[str, list[dict[str, object]] | dict[str, object]]):
        self.responses_by_url = responses_by_url

    def extract(self, *, url: str, render_mode: str = "auto", include_screenshot: bool = True):
        payload = self.responses_by_url.get(url)
        if isinstance(payload, list):
            if len(payload) > 1:
                return dict(payload.pop(0))
            if payload:
                return dict(payload[0])
        if isinstance(payload, dict):
            return dict(payload)
        return {
            "url": url,
            "final_url": url,
            "reachable": False,
            "render_mode": render_mode,
            "title": "",
            "meta_description": "",
            "headings": [],
            "visible_text": "",
            "summary": "Sayfa okunamadı.",
            "issues": ["missing_fixture"],
            "artifacts": [],
        }


def _build_service(
    *,
    transport: httpx.BaseTransport | None = None,
    database_adapters: dict | None = None,
    web_intel: object | None = None,
) -> IntegrationPlatformService:
    settings = get_settings()
    store = Persistence(Path(settings.db_path))
    audit = AuditLogger(Path(settings.audit_log_path))
    return IntegrationPlatformService(
        settings=settings,
        store=store,
        audit=audit,
        db_path=Path(settings.db_path),
        http_transport=transport,
        database_adapters=database_adapters,
        web_intel=web_intel,
    )


def _build_router_test_app(
    *,
    transport: httpx.BaseTransport | None = None,
    database_adapters: dict | None = None,
    web_intel: object | None = None,
) -> FastAPI:
    settings = get_settings()
    store = Persistence(Path(settings.db_path))
    service = _build_service(transport=transport, database_adapters=database_adapters, web_intel=web_intel)
    app = FastAPI()
    app.include_router(create_integrations_router(settings=settings, store=store, integration_service=service))
    return app


def _issue_bearer_token(*, role: str) -> str:
    settings = get_settings()
    store = Persistence(Path(settings.db_path))
    token, exp, sid = issue_token(settings.jwt_secret, subject=f"{role}-tester", role=role, ttl_seconds=3600)
    store.store_session(sid, f"{role}-tester", role, datetime.fromtimestamp(exp, timezone.utc).isoformat())
    return f"Bearer {token}"


async def _call_asgi_json(
    app,
    method: str,
    url: str,
    *,
    role: str | None = None,
    authorization: str | None = None,
    payload: dict | None = None,
):
    if "?" in url:
        path, query = url.split("?", 1)
    else:
        path, query = url, ""
    body = b""
    headers = [
        (b"host", b"testserver"),
        (b"accept", b"application/json"),
    ]
    if authorization:
        headers.append((b"authorization", authorization.encode("utf-8")))
    elif role:
        headers.append((b"x-role", role.encode("utf-8")))
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers.append((b"content-type", b"application/json"))
        headers.append((b"content-length", str(len(body)).encode("ascii")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query.encode("utf-8"),
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }
    messages = []
    request_sent = False

    async def receive():
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    await asyncio.wait_for(app(scope, receive, send), timeout=10)
    start = next(message for message in messages if message["type"] == "http.response.start")
    raw_body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    parsed = json.loads(raw_body.decode("utf-8")) if raw_body else None
    return int(start["status"]), parsed


def _find_endpoint(app: FastAPI, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method.upper() in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"route_not_found:{method}:{path}")


def _github_payload() -> IntegrationConnectionPayload:
    return IntegrationConnectionPayload(
        connector_id="github",
        display_name="Musteri GitHub org",
        access_level="read_write",
        enabled=True,
        mock_mode=True,
        config={
            "workspace_label": "Musteri GitHub org",
            "client_id": "github-client-id",
            "redirect_uri": "http://localhost:3000/integrations/callback",
        },
        secrets={"client_secret": "github-client-secret"},
    )


def _legacy_secret_token(secret_material: str, payload: dict[str, object]) -> str:
    import base64
    import hashlib
    import hmac

    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = b"legacy-sealedbox"
    key = hashlib.sha256(CONTEXT_V1 + secret_material.encode("utf-8")).digest()
    ciphertext = _xor(raw, _keystream(key, nonce, len(raw)))
    mac = hmac.new(key, CONTEXT_V1 + nonce + ciphertext, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(nonce + ciphertext + mac).decode("ascii").rstrip("=")
    return f"{PREFIX_V1}:{token}"


def test_secret_box_supports_rotation_and_legacy_payloads():
    legacy_payload = {"client_secret": "legacy-secret", "access_token": "token-1"}
    legacy_token = _legacy_secret_token("old-secret-key", legacy_payload)

    rotated = SecretBox(
        "new-secret-key",
        posture="test:env-managed-key",
        key_id="2026-q2",
        previous_keys=["old-secret-key"],
    )
    assert rotated.open_json(legacy_token) == legacy_payload

    sealed = rotated.seal_json({"client_secret": "new-secret"})
    assert sealed.startswith("lcintsec:v2:2026-q2:")
    assert rotated.open_json(sealed)["client_secret"] == "new-secret"


def test_integration_platform_service_catalog_and_sync(monkeypatch):
    _configure_runtime_env(monkeypatch)
    service = _build_service(transport=_build_mock_provider_transport())

    catalog = service.list_catalog()
    connector_ids = {item["connector"]["id"] for item in catalog["items"]}
    assert {"notion", "github", "generic-rest", "postgresql", "mysql", "mssql", "elastic"}.issubset(connector_ids)

    preview_payload = IntegrationConnectionPayload(
        connector_id="notion",
        display_name="Muvekkil bilgi merkezi",
        access_level="read_write",
        enabled=True,
        mock_mode=True,
        config={
            "workspace_label": "Muvekkil bilgi merkezi",
            "base_url": "https://api.notion.com/v1",
            "notion_version": "2022-06-28",
        },
        secrets={"integration_token": "secret_mock_token"},
    )
    preview = service.preview_connection(preview_payload)
    assert preview["validation"]["status"] == "dry_run"

    saved = service.save_connection(preview_payload, actor="lawyer-tester")
    connection_id = int(saved["connection"]["id"])

    validated = service.validate_connection(connection_id)
    assert validated["validation"]["health_status"] == "valid"

    synced = service.sync_connection(connection_id, actor="lawyer-tester")
    assert synced["record_count"] >= 2

    detail = service.get_connection_detail(connection_id)
    assert detail["record_preview"]
    assert detail["resource_preview"]
    assert detail["sync_runs"]
    assert detail["event_preview"]

    action = service.execute_action(
        connection_id,
        "search",
        IntegrationActionRequest(input={"query": "dava"}, confirmed=False),
        actor="lawyer-tester",
    )
    assert action["action_run"]["status"] == "completed"
    assert action["action_run"]["policy"]["policy_decision"]["decision"] == "execute"

    scaffold = service.generate_scaffold(
        IntegrationScaffoldRequest(
            service_name="Acme CRM",
            docs_url="https://docs.acmecrm.example/api",
            category="custom-api",
        )
    )
    assert scaffold["connector"]["id"] == "acme-crm"


def test_integration_platform_service_supports_elastic_search_and_sync(monkeypatch):
    _configure_runtime_env(monkeypatch)
    service = _build_service(transport=_build_mock_provider_transport())

    payload = IntegrationConnectionPayload(
        connector_id="elastic",
        display_name="Elastic veri golu",
        access_level="read_only",
        enabled=True,
        mock_mode=False,
        config={
            "cluster_label": "Elastic veri golu",
            "base_url": "https://elastic.example.com",
            "index_pattern": "cases-*",
            "search_fields": "title^3,summary,body",
            "result_size": 12,
        },
        secrets={"api_key": "encoded-elastic-key"},
    )

    preview = service.preview_connection(payload)
    assert preview["validation"]["health_status"] == "valid"

    saved = service.save_connection(payload, actor="lawyer-tester")
    connection_id = int(saved["connection"]["id"])

    validated = service.validate_connection(connection_id)
    assert "green" in str(validated["validation"]["message"])

    synced = service.sync_connection(connection_id, actor="lawyer-tester")
    assert synced["record_count"] == 1

    detail = service.get_connection_detail(connection_id)
    assert detail["resource_preview"]
    assert detail["resource_preview"][0]["title"] == "Slack onboarding notu"

    action = service.execute_action(
        connection_id,
        "search",
        IntegrationActionRequest(input={"query": "slack onboarding", "index": "cases-archive"}, confirmed=False),
        actor="lawyer-tester",
    )
    assert action["action_run"]["status"] == "completed"
    output = action["action_run"]["output"]
    assert output["count"] == 1
    assert output["items"][0]["title"] == "Slack onboarding notu"

    sql_action = service.execute_action(
        connection_id,
        "run_sql",
        IntegrationActionRequest(input={"query": 'SELECT title, summary FROM "cases-*"'}, confirmed=False),
        actor="lawyer-tester",
    )
    assert sql_action["action_run"]["status"] == "completed"
    sql_output = sql_action["action_run"]["output"]
    assert sql_output["count"] == 1
    assert sql_output["items"][0]["title"] == "Slack onboarding notu"


def test_integration_platform_service_rejects_non_readonly_elastic_sql(monkeypatch):
    _configure_runtime_env(monkeypatch)
    monkeypatch.setenv("LAWCOPILOT_CONNECTOR_DRY_RUN", "false")
    service = _build_service(transport=_build_mock_provider_transport())

    saved = service.save_connection(
        IntegrationConnectionPayload(
            connector_id="elastic",
            display_name="Elastic veri golu",
            access_level="read_only",
            enabled=True,
            mock_mode=False,
            config={
                "cluster_label": "Elastic veri golu",
                "base_url": "https://elastic.example.com",
                "index_pattern": "cases-*",
            },
            secrets={"api_key": "encoded-elastic-key"},
        ),
        actor="lawyer-tester",
    )
    connection_id = int(saved["connection"]["id"])

    failed_action = service.execute_action(
        connection_id,
        "run_sql",
        IntegrationActionRequest(input={"query": 'DELETE FROM "cases-*"'}, confirmed=False),
        actor="lawyer-tester",
    )
    assert failed_action["action_run"]["status"] == "failed"
    assert failed_action["message"] == "elastic_sql_not_allowed"
    assert failed_action["action_run"]["error"] == "elastic_sql_not_allowed"


def test_integration_repository_migrates_legacy_sync_runs_without_scheduled_for(monkeypatch):
    temp_root = _configure_runtime_env(monkeypatch)
    db_path = temp_root / "lawcopilot.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE offices (id TEXT PRIMARY KEY, name TEXT, deployment_mode TEXT, created_at TEXT)")
        conn.execute(
            """
            CREATE TABLE integration_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                office_id TEXT NOT NULL,
                connection_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    repo = IntegrationRepository(db_path)
    with repo._conn() as conn:  # noqa: SLF001 - schema verification for regression coverage
        columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(integration_sync_runs)").fetchall()}
        indexes = {str(row["name"]) for row in conn.execute("PRAGMA index_list(integration_sync_runs)").fetchall()}

    assert "scheduled_for" in columns
    assert "idx_integration_sync_runs_queue" in indexes


def test_sync_run_deduplication_and_stale_lock_recovery(monkeypatch):
    _configure_runtime_env(monkeypatch)
    service = _build_service(transport=_build_mock_provider_transport())
    settings = get_settings()
    repo = IntegrationRepository(Path(settings.db_path))

    saved = service.save_connection(_github_payload(), actor="lawyer-tester")
    connection_id = int(saved["connection"]["id"])

    first = repo.create_sync_run(
        settings.office_id,
        connection_id=connection_id,
        mode="incremental",
        status="queued",
        run_key=f"{connection_id}:incremental",
        metadata={"source": "test"},
    )
    duplicate = repo.create_sync_run(
        settings.office_id,
        connection_id=connection_id,
        mode="incremental",
        status="queued",
        run_key=f"{connection_id}:incremental",
        metadata={"source": "test"},
    )
    assert int(first["id"]) == int(duplicate["id"])

    claimed = repo.claim_sync_run(settings.office_id, int(first["id"]), lock_token="lock-1")
    assert claimed["status"] == "running"

    queued = repo.create_sync_run(
        settings.office_id,
        connection_id=connection_id,
        mode="full",
        status="queued",
        run_key=f"{connection_id}:full",
        metadata={"source": "test"},
    )
    blocked = repo.claim_sync_run(settings.office_id, int(queued["id"]), lock_token="lock-2")
    assert blocked["status"] == "queued"

    stale_at = "2026-04-08T08:00:00+00:00"
    with repo._conn() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE integration_sync_runs SET locked_at=?, started_at=? WHERE office_id=? AND id=?",
            (stale_at, stale_at, settings.office_id, int(first["id"])),
        )
    recovered = repo.recover_stale_sync_runs(settings.office_id, lock_timeout_seconds=1)
    assert recovered
    assert any(int(item["id"]) == int(first["id"]) and item["status"] == "retry_scheduled" for item in recovered)


def test_oauth_lifecycle_sync_policy_and_scaffold_v2(monkeypatch):
    _configure_runtime_env(monkeypatch)
    service = _build_service(transport=_build_mock_provider_transport())

    saved = service.save_connection(_github_payload(), actor="lawyer-tester")
    connection_id = int(saved["connection"]["id"])
    assert saved["connection"]["auth_status"] == "authorization_required"

    started = service.start_oauth_authorization(
        connection_id,
        IntegrationOAuthStartRequest(redirect_uri="http://localhost:3000/integrations/callback"),
        actor="lawyer-tester",
    )
    assert "github.com/login/oauth/authorize" in started["authorization_url"]
    state = str(started["oauth_session"]["state"])

    completed = service.complete_oauth_callback(
        IntegrationOAuthCallbackRequest(state=state, code="mock-code"),
        actor="lawyer-tester",
    )
    assert completed["connection"]["auth_status"] == "authenticated"

    checked = service.health_check_connection(connection_id, actor="lawyer-tester")
    assert checked["validation"]["health_status"] == "valid"

    safety = service.update_safety_settings(
        connection_id,
        IntegrationSafetySettingsRequest(write_enabled=False),
        actor="lawyer-tester",
    )
    assert safety["safety_settings"]["write_enabled"] is False

    blocked_action = service.execute_action(
        connection_id,
        "create",
        IntegrationActionRequest(input={"title": "Issue"}, confirmed=True),
        actor="lawyer-tester",
    )
    assert blocked_action["action_run"]["status"] == "blocked"

    queued = service.schedule_sync(
        connection_id,
        IntegrationSyncScheduleRequest(mode="incremental", trigger_type="manual", run_now=False),
        actor="lawyer-tester",
    )
    assert queued["sync_run"]["status"] == "queued"

    dispatched = service.dispatch_sync_jobs(
        IntegrationJobDispatchRequest(limit=2),
        actor="lawyer-tester",
    )
    assert dispatched["count"] >= 1

    refreshed = service.refresh_connection_credentials(connection_id, actor="lawyer-tester")
    assert refreshed["connection"]["auth_status"] == "authenticated"

    revoked = service.revoke_connection(connection_id, actor="lawyer-tester")
    assert revoked["connection"]["auth_status"] == "revoked"

    reconnected = service.reconnect_connection(connection_id, actor="lawyer-tester")
    assert reconnected["connection"]["status"] == "configured"

    detail = service.get_connection_detail(connection_id)
    assert detail["oauth_sessions"]
    assert detail["capabilities"]["blocked_actions"]
    write_action = next(item for item in detail["capabilities"]["blocked_actions"] if item["key"] == "create")
    assert "authorization_required" in str(write_action["reason"]).lower()

    scaffold = service.generate_scaffold(
        IntegrationScaffoldRequest(
            service_name="Docs API",
            openapi_spec=json.dumps(
                {
                    "openapi": "3.0.0",
                    "paths": {
                        "/documents": {"get": {"summary": "List documents"}, "post": {"summary": "Create document"}},
                        "/documents/search": {"get": {"summary": "Search documents"}},
                    },
                    "components": {
                        "securitySchemes": {
                            "oauth": {"type": "oauth2"},
                        }
                    },
                }
            ),
        )
    )
    assert scaffold["inference"]["auth_type"] == "oauth2"
    assert scaffold["suggested_validation_tests"]
    assert scaffold["mock_fixtures"]
    inferred_operations = {item["operation"] for item in scaffold["connector"]["actions"]}
    assert "fetch_documents" in inferred_operations
    assert "search" in inferred_operations
    assert "create" in inferred_operations


def test_integration_policy_payload_exposes_central_policy_decision(monkeypatch):
    _configure_runtime_env(monkeypatch)
    service = _build_service(transport=_build_mock_provider_transport())

    preview_payload = IntegrationConnectionPayload(
        connector_id="notion",
        display_name="Muvekkil bilgi merkezi",
        access_level="read_write",
        enabled=True,
        mock_mode=True,
        scopes=["workspace"],
        config={
            "workspace_label": "Muvekkil bilgi merkezi",
            "base_url": "https://api.notion.com/v1",
            "notion_version": "2022-06-28",
        },
        secrets={"integration_token": "secret_mock_token"},
    )
    saved = service.save_connection(preview_payload, actor="lawyer-tester")
    connection_id = int(saved["connection"]["id"])

    read_action = service.execute_action(
        connection_id,
        "search",
        IntegrationActionRequest(input={"query": "dava"}, confirmed=False),
        actor="lawyer-tester",
    )
    assert read_action["action_run"]["policy"]["policy_decision"]["decision"] == "execute"
    assert read_action["action_run"]["policy"]["policy_decision"]["risk_level"] == "A"

    write_action = service.execute_action(
        connection_id,
        "append_block",
        IntegrationActionRequest(input={"block_id": "page-1", "children": [{"object": "block", "type": "paragraph"}]}, confirmed=False),
        actor="lawyer-tester",
    )
    assert write_action["action_run"]["status"] == "requires_confirmation"
    assert write_action["action_run"]["policy"]["policy_decision"]["decision"] == "ask_confirm"
    assert write_action["action_run"]["policy"]["policy_decision"]["risk_level"] == "B"


def test_duplicate_oauth_callback_is_idempotent(monkeypatch):
    _configure_runtime_env(monkeypatch)
    service = _build_service(transport=_build_mock_provider_transport())

    saved = service.save_connection(_github_payload(), actor="lawyer-tester")
    connection_id = int(saved["connection"]["id"])
    started = service.start_oauth_authorization(
        connection_id,
        IntegrationOAuthStartRequest(redirect_uri="http://localhost:3000/integrations/callback"),
        actor="lawyer-tester",
    )
    state = str(started["oauth_session"]["state"])

    first = service.complete_oauth_callback(
        IntegrationOAuthCallbackRequest(state=state, code="mock-code"),
        actor="lawyer-tester",
    )
    second = service.complete_oauth_callback(
        IntegrationOAuthCallbackRequest(state=state, code="mock-code-duplicate"),
        actor="lawyer-tester",
    )

    assert first["connection"]["auth_status"] == "authenticated"
    assert second["connection"]["auth_status"] == "authenticated"
    assert "daha once tamamlanmisti" in second["message"]
    detail = service.get_connection_detail(connection_id)
    assert any(item["event_type"] == "oauth_callback_duplicate" for item in detail["event_preview"])


def test_automation_request_creates_generated_connector_and_oauth_flow(monkeypatch):
    _configure_runtime_env(monkeypatch)
    service = _build_service(transport=_build_mock_provider_transport())

    created = service.create_integration_request(
        IntegrationAutomationRequest(prompt="Slack workspace'imizi bagla ve mesajlari okuyup yazsin."),
        actor="lawyer-tester",
    )
    assert created["created"] is True
    assert created["connector"]["id"] == "slack"
    assert created["generated_request"]["status"] == "draft_ready"

    catalog = service.list_catalog(query="slack")
    slack_item = next(item for item in catalog["items"] if item["connector"]["id"] == "slack")
    assert slack_item["source"] == "generated-request"
    assert slack_item["generated_request"]["service_name"] == "Slack"

    preview_payload = IntegrationConnectionPayload(
        connector_id="slack",
        display_name="Slack hukuk workspace",
        access_level="read_write",
        enabled=True,
        mock_mode=True,
        config={
            "client_id": "slack-client-id",
            "redirect_uri": "http://localhost:3000/integrations/callback",
            "base_url": "https://slack.com/api",
        },
        secrets={"client_secret": "slack-client-secret"},
    )
    preview = service.preview_connection(preview_payload)
    assert preview["validation"]["status"] == "authorization_required"

    saved = service.save_connection(preview_payload, actor="lawyer-tester")
    connection_id = int(saved["connection"]["id"])
    started = service.start_oauth_authorization(
        connection_id,
        IntegrationOAuthStartRequest(redirect_uri="http://localhost:3000/integrations/callback"),
        actor="lawyer-tester",
    )
    assert "slack.com/oauth/v2/authorize" in started["authorization_url"]

    completed = service.complete_oauth_callback(
        IntegrationOAuthCallbackRequest(state=str(started["oauth_session"]["state"]), code="slack-mock-code"),
        actor="lawyer-tester",
    )
    assert completed["connection"]["auth_status"] == "authenticated"


def test_automation_request_creates_tiktok_connector_with_oauth_and_health(monkeypatch):
    _configure_runtime_env(monkeypatch)
    monkeypatch.setenv("LAWCOPILOT_CONNECTOR_DRY_RUN", "false")
    service = _build_service(transport=_build_mock_provider_transport())

    created = service.create_integration_request(
        IntegrationAutomationRequest(prompt="TikTok'u bagla ve hesabimi takip et."),
        actor="lawyer-tester",
    )
    assert created["created"] is True
    assert created["connector"]["id"] == "tiktok"
    assert created["connector"]["auth_type"] == "oauth2"
    assert created["connector"]["category"] == "social-media"
    client_field = next(item for item in created["connector"]["ui_schema"] if item["key"] == "client_id")
    assert client_field["label"] == "Client key"

    service.review_generated_connector(
        "tiktok",
        IntegrationGeneratedConnectorReviewRequest(
            decision="approve",
            notes="TikTok generated connector canli kullanim icin onaylandi.",
            live_use_enabled=True,
        ),
        actor="lawyer-tester",
    )

    saved = service.save_connection(
        IntegrationConnectionPayload(
            connector_id="tiktok",
            display_name="TikTok hesabim",
            access_level="read_only",
            enabled=True,
            mock_mode=False,
            config={
                "client_id": "tiktok-client-key",
                "client_secret": "ignored-in-config",
                "redirect_uri": "http://localhost:3000/integrations/callback",
                "base_url": "https://open.tiktokapis.com",
            },
            secrets={"client_secret": "tiktok-client-secret"},
        ),
        actor="lawyer-tester",
    )
    connection_id = int(saved["connection"]["id"])
    started = service.start_oauth_authorization(
        connection_id,
        IntegrationOAuthStartRequest(redirect_uri="http://localhost:3000/integrations/callback"),
        actor="lawyer-tester",
    )
    assert "www.tiktok.com/v2/auth/authorize/" in started["authorization_url"]
    assert "client_key=tiktok-client-key" in started["authorization_url"]

    completed = service.complete_oauth_callback(
        IntegrationOAuthCallbackRequest(state=str(started["oauth_session"]["state"]), code="tiktok-mock-code"),
        actor="lawyer-tester",
    )
    assert completed["connection"]["auth_status"] == "authenticated"

    health = service.health_check_connection(connection_id, actor="lawyer-tester")
    assert health["connection"]["health_status"] == "valid"
    synced = service.sync_connection(connection_id, actor="lawyer-tester")
    assert synced["record_count"] >= 1


def test_automation_request_marks_prompt_only_connectors_as_low_confidence(monkeypatch):
    _configure_runtime_env(monkeypatch)
    service = _build_service(transport=_build_mock_provider_transport())

    created = service.create_integration_request(
        IntegrationAutomationRequest(prompt="Moonbase hesabimi bagla"),
        actor="lawyer-tester",
    )

    readiness = dict((created.get("generated_request") or {}).get("metadata", {}).get("readiness") or {})
    assert readiness["execution_confidence"] == "low"
    assert readiness["needs_docs_or_openapi"] is True
    assert "docs/OpenAPI" in created["message"]


def test_slack_sync_handles_pagination_retries_and_partial_failures(monkeypatch):
    _configure_runtime_env(monkeypatch)
    counters = {"conversations_list": 0, "history_c1": 0, "history_c2": 0, "history_c3": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        path = request.url.path
        if host == "slack.com" and path == "/api/oauth.v2.access":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "access_token": "xoxb-slack-access",
                    "refresh_token": "xoxe-slack-refresh",
                    "token_type": "Bearer",
                    "scope": "channels:read,channels:history,chat:write",
                    "expires_in": 3600,
                },
            )
        if host == "slack.com" and path == "/api/conversations.list":
            counters["conversations_list"] += 1
            if counters["conversations_list"] == 1:
                return httpx.Response(429, json={"ok": False, "error": "ratelimited"}, headers={"Retry-After": "0"})
            cursor = str(request.url.params.get("cursor") or "")
            if cursor == "page-2":
                return httpx.Response(200, json={"ok": True, "channels": [{"id": "C3", "name": "alerts"}]})
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "channels": [{"id": "C1", "name": "general"}, {"id": "C2", "name": "cases"}],
                    "response_metadata": {"next_cursor": "page-2"},
                },
            )
        if host == "slack.com" and path == "/api/conversations.history":
            channel = str(request.url.params.get("channel") or "")
            cursor = str(request.url.params.get("cursor") or "")
            if channel == "C1":
                counters["history_c1"] += 1
                if cursor == "history-2":
                    return httpx.Response(200, json={"ok": True, "messages": [{"ts": "1712563200.000200", "text": "page-2", "user": "U2"}]})
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "messages": [{"ts": "1712563200.000100", "text": "page-1", "user": "U1"}],
                        "response_metadata": {"next_cursor": "history-2"},
                    },
                )
            if channel == "C2":
                counters["history_c2"] += 1
                return httpx.Response(500, json={"ok": False, "error": "internal_error"})
            if channel == "C3":
                counters["history_c3"] += 1
                return httpx.Response(200, json={"ok": True, "messages": [{"ts": "1712563200.000300", "text": "alerts", "user": "U3"}]})
        return httpx.Response(404, json={"error": f"unhandled:{host}{path}"})

    service = _build_service(transport=httpx.MockTransport(handler))
    service.create_integration_request(
        IntegrationAutomationRequest(prompt="Slack workspace'imizi bagla"),
        actor="lawyer-tester",
    )
    saved = service.save_connection(
        IntegrationConnectionPayload(
            connector_id="slack",
            display_name="Slack hukuk workspace",
            access_level="read_write",
            enabled=True,
            mock_mode=True,
            config={
                "client_id": "slack-client-id",
                "redirect_uri": "http://localhost:3000/integrations/callback",
                "base_url": "https://slack.com/api",
            },
            secrets={"client_secret": "slack-client-secret"},
        ),
        actor="lawyer-tester",
    )
    connection_id = int(saved["connection"]["id"])
    started = service.start_oauth_authorization(
        connection_id,
        IntegrationOAuthStartRequest(redirect_uri="http://localhost:3000/integrations/callback"),
        actor="lawyer-tester",
    )
    service.complete_oauth_callback(
        IntegrationOAuthCallbackRequest(state=str(started["oauth_session"]["state"]), code="slack-code"),
        actor="lawyer-tester",
    )
    service.schedule_sync(
        connection_id,
        IntegrationSyncScheduleRequest(mode="incremental", trigger_type="manual", run_now=False),
        actor="lawyer-tester",
    )
    dispatched = service.dispatch_sync_jobs(IntegrationJobDispatchRequest(limit=5), actor="lawyer-tester")
    assert dispatched["count"] >= 1

    result = dispatched["items"][0]
    assert result["connection"]["health_status"] == "degraded"
    assert "alt islem uyarisi" in str(result["connection"]["health_message"] or "")
    detail = service.get_connection_detail(connection_id)
    latest_sync = detail["sync_runs"][0]
    assert latest_sync["metadata"]["partial_failure_count"] == 1
    assert counters["conversations_list"] >= 2
    assert counters["history_c1"] >= 2
    assert counters["history_c2"] >= 1
    assert len(detail["record_preview"]) >= 4


def test_launch_ops_summary_and_office_isolation(monkeypatch):
    temp_root = _configure_runtime_env(monkeypatch)
    transport = _build_mock_provider_transport()

    monkeypatch.setenv("LAWCOPILOT_OFFICE_ID", "office-a")
    service_a = _build_service(transport=transport)
    service_a.create_integration_request(
        IntegrationAutomationRequest(prompt="Slack workspace'imizi bagla"),
        actor="lawyer-a",
    )
    saved = service_a.save_connection(
        IntegrationConnectionPayload(
            connector_id="slack",
            display_name="Slack hukuk workspace",
            access_level="read_write",
            enabled=True,
            mock_mode=True,
            config={
                "client_id": "slack-client-id",
                "redirect_uri": "http://localhost:3000/integrations/callback",
                "base_url": "https://slack.com/api",
            },
            secrets={"client_secret": "slack-client-secret"},
        ),
        actor="lawyer-a",
    )
    connection_id = int(saved["connection"]["id"])
    started = service_a.start_oauth_authorization(
        connection_id,
        IntegrationOAuthStartRequest(redirect_uri="http://localhost:3000/integrations/callback"),
        actor="lawyer-a",
    )
    service_a.complete_oauth_callback(
        IntegrationOAuthCallbackRequest(state=str(started["oauth_session"]["state"]), code="slack-code"),
        actor="lawyer-a",
    )

    summary = service_a.launch_ops_summary()
    assert summary["analytics"]["connector_requests"]["top_requested"][0]["service_name"] == "Slack"
    assert summary["analytics"]["oauth"]["counts"]["completed"] >= 1
    assert summary["health"]["connection_count"] >= 1

    repo = IntegrationRepository(temp_root / "lawcopilot.db")
    active_setup = repo.upsert_assistant_setup(
        "office-a",
        thread_id=42,
        request_text="Connect Slack",
        status="collecting",
        connector_id="slack",
        service_name="Slack",
        missing_fields=[{"key": "client_id", "label": "Client ID"}],
        metadata={"pending_field": {"key": "client_id", "label": "Client ID"}},
        created_by="lawyer-a",
    )
    stale_updated_at = "2026-04-07T00:00:00+00:00"
    with repo._conn() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE integration_assistant_setups SET updated_at=? WHERE office_id=? AND id=?",
            (stale_updated_at, "office-a", int(active_setup["id"])),
        )
    summary_with_stale = service_a.launch_ops_summary()
    assert summary_with_stale["health"]["stale_pending_setups"]

    monkeypatch.setenv("LAWCOPILOT_OFFICE_ID", "office-b")
    service_b = _build_service(transport=transport)
    catalog_b = service_b.list_catalog(query="slack")
    assert catalog_b["items"] == []
    assert service_b.list_generated_requests()["items"] == []


def test_launch_ops_summary_flags_insecure_rollout_controls(monkeypatch):
    _configure_runtime_env(monkeypatch)
    monkeypatch.setenv("LAWCOPILOT_ALLOW_HEADER_AUTH", "true")
    monkeypatch.setenv("LAWCOPILOT_JWT_SECRET", "dev-change-me")
    monkeypatch.delenv("LAWCOPILOT_INTEGRATION_SECRET_KEY", raising=False)
    service = _build_service(transport=_build_mock_provider_transport())

    summary = service.launch_ops_summary()
    labels = {item["label"] for item in summary["health"]["readiness_checks"]}
    assert "dry_run_enabled" in labels
    assert "header_auth_enabled" in labels
    assert "default_jwt_secret" in labels
    assert "local_secret_posture" in labels


def test_generated_connector_requires_review_for_live_mode(monkeypatch):
    _configure_runtime_env(monkeypatch)
    monkeypatch.setenv("LAWCOPILOT_CONNECTOR_DRY_RUN", "false")
    service = _build_service(transport=_build_mock_provider_transport())

    service.create_integration_request(
        IntegrationAutomationRequest(prompt="Slack workspace'imizi bagla"),
        actor="lawyer-tester",
    )
    payload = IntegrationConnectionPayload(
        connector_id="slack",
        display_name="Slack hukuk workspace",
        access_level="read_write",
        enabled=True,
        mock_mode=False,
        config={
            "client_id": "slack-client-id",
            "redirect_uri": "http://localhost:3000/integrations/callback",
            "base_url": "https://slack.com/api",
        },
        secrets={"client_secret": "slack-client-secret"},
    )

    with pytest.raises(ValueError, match="generated_connector_review_required_for_live_mode"):
        service.save_connection(payload, actor="lawyer-tester")

    reviewed = service.review_generated_connector(
        "slack",
        IntegrationGeneratedConnectorReviewRequest(decision="approve", notes="Canli kullanim icin guvenli bulundu.", live_use_enabled=True),
        actor="lawyer-tester",
    )
    assert reviewed["generated_request"]["status"] == "approved"
    assert reviewed["generated_request"]["live_use_enabled"] is True

    saved = service.save_connection(payload, actor="lawyer-tester")
    assert saved["connection"]["mock_mode"] is False


def test_scaffold_fetch_pattern_memory_and_generated_registry_admin(monkeypatch):
    _configure_runtime_env(monkeypatch)
    service = _build_service(transport=_build_mock_provider_transport())

    scaffold = service.generate_scaffold(
        IntegrationScaffoldRequest(
            service_name="Acme Desk",
            docs_url="https://docs.acme.example/guide",
            openapi_url="https://docs.acme.example/openapi.json",
        )
    )
    assert scaffold["fetch_summary"]["openapi_fetched"] is True
    assert scaffold["fetch_summary"]["docs_fetched"] is True
    assert scaffold["inference"]["auth_type"] == "oauth2"

    created = service.create_integration_request(
        IntegrationAutomationRequest(
            prompt="Acme Desk bagla",
            docs_url="https://docs.acme.example/guide",
            openapi_url="https://docs.acme.example/openapi.json",
        ),
        actor="lawyer-tester",
    )
    connector_id = str(created["connector"]["id"])
    reviewed = service.review_generated_connector(
        connector_id,
        IntegrationGeneratedConnectorReviewRequest(decision="approve", notes="Pattern hafizasina alinabilir.", live_use_enabled=True),
        actor="lawyer-tester",
    )
    assert reviewed["generated_request"]["status"] == "approved"

    patterns = service.list_connector_patterns()
    assert any(item["service_name"] == "Acme Desk" for item in patterns["items"])

    refreshed = service.refresh_generated_connector(
        connector_id,
        IntegrationGeneratedConnectorRefreshRequest(notes="OpenAPI tekrar cekilsin."),
        actor="lawyer-tester",
    )
    assert refreshed["generated_request"]["status"] == "draft_ready"
    assert refreshed["generated_request"]["version"] >= 2
    assert refreshed["generated_request"]["versions"]

    disabled = service.set_generated_connector_enabled(
        connector_id,
        IntegrationGeneratedConnectorStateRequest(enabled=False, notes="Katalogdan gizle."),
        actor="lawyer-tester",
    )
    assert disabled["generated_request"]["enabled"] is False

    with pytest.raises(ValueError, match="generated_connector_not_available"):
        service.preview_connection(
            IntegrationConnectionPayload(
                connector_id=connector_id,
                display_name="Acme Desk",
                access_level="read_only",
                enabled=True,
                mock_mode=True,
                config={"base_url": "https://api.acme.example"},
                secrets={"client_secret": "secret"},
            )
        )

    enabled = service.set_generated_connector_enabled(
        connector_id,
        IntegrationGeneratedConnectorStateRequest(enabled=True),
        actor="lawyer-tester",
    )
    assert enabled["generated_request"]["enabled"] is True

    recreated = service.create_integration_request(
        IntegrationAutomationRequest(
            prompt="Acme Desk mesajlarini bagla",
            docs_url="https://docs.acme.example/guide",
            openapi_url="https://docs.acme.example/openapi.json",
        ),
        actor="lawyer-tester",
    )
    assert recreated["generated_request"]["metadata"]["pattern_matches"]

    deleted = service.delete_generated_connector(connector_id, actor="lawyer-tester")
    assert deleted["deleted"] is True
    catalog = service.list_catalog(query="Acme Desk")
    assert not any(item["connector"]["id"] == connector_id for item in catalog["items"])


def test_integrations_routes_support_oauth_and_sync_flow(monkeypatch):
    _configure_runtime_env(monkeypatch)
    full_app = create_app()
    route_paths = {route.path for route in full_app.routes}
    assert "/integrations/catalog" in route_paths
    assert "/integrations/requests" in route_paths
    assert "/integrations/patterns" in route_paths
    assert "/integrations/requests/{connector_id}/review" in route_paths
    assert "/integrations/requests/{connector_id}/refresh" in route_paths
    assert "/integrations/requests/{connector_id}/state" in route_paths
    assert "/integrations/requests/{connector_id}" in route_paths
    assert "/integrations/connections/{connection_id}/oauth/start" in route_paths
    assert "/integrations/connections/{connection_id}/sync/schedule" in route_paths
    assert "/integrations/sync/dispatch" in route_paths
    assert "/integrations/worker" in route_paths
    assert "/integrations/ops/summary" in route_paths
    assert "/integrations/webhooks/{connector_id}" in route_paths
    app = _build_router_test_app(transport=_build_mock_provider_transport())
    lawyer_auth = _issue_bearer_token(role="lawyer")
    intern_auth = _issue_bearer_token(role="intern")

    catalog_route = _find_endpoint(app, "/integrations/catalog", "GET")
    request_route = _find_endpoint(app, "/integrations/requests", "POST")
    request_list_route = _find_endpoint(app, "/integrations/requests", "GET")
    patterns_route = _find_endpoint(app, "/integrations/patterns", "GET")
    review_route = _find_endpoint(app, "/integrations/requests/{connector_id}/review", "POST")
    refresh_generated_route = _find_endpoint(app, "/integrations/requests/{connector_id}/refresh", "POST")
    state_generated_route = _find_endpoint(app, "/integrations/requests/{connector_id}/state", "POST")
    delete_generated_route = _find_endpoint(app, "/integrations/requests/{connector_id}", "DELETE")
    save_route = _find_endpoint(app, "/integrations/connections", "POST")
    start_oauth_route = _find_endpoint(app, "/integrations/connections/{connection_id}/oauth/start", "POST")
    callback_route = _find_endpoint(app, "/integrations/oauth/callback", "POST")
    schedule_route = _find_endpoint(app, "/integrations/connections/{connection_id}/sync/schedule", "POST")
    dispatch_route = _find_endpoint(app, "/integrations/sync/dispatch", "POST")
    detail_route = _find_endpoint(app, "/integrations/connections/{connection_id}", "GET")
    events_route = _find_endpoint(app, "/integrations/events", "GET")
    ops_summary_route = _find_endpoint(app, "/integrations/ops/summary", "GET")

    catalog = catalog_route(x_role=None, authorization=intern_auth)
    assert any(item["connector"]["id"] == "github" for item in catalog["items"])

    created = request_route(
        IntegrationAutomationRequest(prompt="Slack workspace'imizi bagla"),
        x_role=None,
        authorization=lawyer_auth,
    )
    assert created["connector"]["id"] == "slack"

    reviewed = review_route(
        "slack",
        IntegrationGeneratedConnectorReviewRequest(decision="approve", notes="UI uzerinden onay"),
        x_role=None,
        authorization=lawyer_auth,
    )
    assert reviewed["generated_request"]["status"] == "approved"

    generated_requests = request_list_route(x_role=None, authorization=intern_auth)
    assert generated_requests["items"]
    patterns = patterns_route(x_role=None, authorization=intern_auth)
    assert isinstance(patterns["items"], list)

    saved = save_route(_github_payload(), x_role=None, authorization=lawyer_auth)
    connection_id = int(saved["connection"]["id"])

    started = start_oauth_route(
        connection_id,
        IntegrationOAuthStartRequest(redirect_uri="http://localhost:3000/integrations/callback", requested_scopes=["read:user"]),
        x_role=None,
        authorization=lawyer_auth,
    )
    state = str(started["oauth_session"]["state"])

    completed = callback_route(
        IntegrationOAuthCallbackRequest(state=state, code="mock-route-code"),
        x_role=None,
        authorization=lawyer_auth,
    )
    assert completed["connection"]["auth_status"] == "authenticated"

    scheduled = schedule_route(
        connection_id,
        IntegrationSyncScheduleRequest(mode="incremental", trigger_type="manual", run_now=False, force=False),
        x_role=None,
        authorization=lawyer_auth,
    )
    assert scheduled["sync_run"]["status"] == "queued"

    dispatched = dispatch_route(
        IntegrationJobDispatchRequest(limit=3),
        x_role=None,
        authorization=lawyer_auth,
    )
    assert dispatched["count"] >= 1

    detail = detail_route(connection_id, x_role=None, authorization=intern_auth)
    assert detail["resource_preview"]
    assert detail["event_preview"]
    assert detail["oauth_sessions"]

    refreshed_generated = refresh_generated_route(
        "slack",
        IntegrationGeneratedConnectorRefreshRequest(notes="Route uzerinden yeniden scaffold et."),
        x_role=None,
        authorization=lawyer_auth,
    )
    assert refreshed_generated["generated_request"]["status"] == "draft_ready"

    disabled_generated = state_generated_route(
        "slack",
        IntegrationGeneratedConnectorStateRequest(enabled=False, notes="Route testi"),
        x_role=None,
        authorization=lawyer_auth,
    )
    assert disabled_generated["generated_request"]["enabled"] is False

    enabled_generated = state_generated_route(
        "slack",
        IntegrationGeneratedConnectorStateRequest(enabled=True),
        x_role=None,
        authorization=lawyer_auth,
    )
    assert enabled_generated["generated_request"]["enabled"] is True

    deleted_generated = delete_generated_route("slack", x_role=None, authorization=lawyer_auth)
    assert deleted_generated["deleted"] is True

    events = events_route(connection_id=connection_id, limit=20, x_role=None, authorization=intern_auth)
    assert events["items"]
    ops_summary = ops_summary_route(x_role=None, authorization=intern_auth)
    assert ops_summary["generated_from"] == "integration_launch_ops_summary"
    assert "analytics" in ops_summary


def test_slack_webhook_ingestion_and_worker_tick(monkeypatch):
    _configure_runtime_env(monkeypatch)
    transport = _build_mock_provider_transport()
    service = _build_service(transport=transport)

    created = service.create_integration_request(
        IntegrationAutomationRequest(prompt="Slack workspace bagla ve event webhook kur"),
        actor="lawyer-tester",
    )
    assert created["connector"]["id"] == "slack"

    service.review_generated_connector(
        "slack",
        IntegrationGeneratedConnectorReviewRequest(decision="approve", live_use_enabled=True),
        actor="lawyer-tester",
    )
    saved = service.save_connection(
        IntegrationConnectionPayload(
            connector_id="slack",
            display_name="Slack hukuk workspace",
            access_level="read_write",
            enabled=True,
            mock_mode=True,
            config={
                "client_id": "slack-client-id",
                "redirect_uri": "http://localhost:3000/integrations/callback",
                "base_url": "https://slack.com/api",
            },
            secrets={"client_secret": "slack-client-secret", "signing_secret": "slack-signing-secret"},
        ),
        actor="lawyer-tester",
    )
    connection_id = int(saved["connection"]["id"])
    started = service.start_oauth_authorization(
        connection_id,
        IntegrationOAuthStartRequest(redirect_uri="http://localhost:3000/integrations/callback"),
        actor="lawyer-tester",
    )
    service.complete_oauth_callback(
        IntegrationOAuthCallbackRequest(state=str(started["oauth_session"]["state"]), code="slack-code"),
        actor="lawyer-tester",
    )

    worker = IntegrationSyncWorker(service=service, poll_seconds=1, batch_size=2)
    service.attach_sync_worker(worker)
    scheduled = service.schedule_sync(
        connection_id,
        IntegrationSyncScheduleRequest(mode="incremental", trigger_type="scheduled", run_now=False),
        actor="lawyer-tester",
    )
    assert scheduled["sync_run"]["status"] == "queued"
    tick = worker.tick()
    assert tick["count"] >= 1
    worker_status = worker.status()
    assert worker_status["alive"] is False
    assert worker_status["last_duration_ms"] >= 0

    webhook_body = {
        "event_id": "Ev123",
        "type": "event_callback",
        "event": {
            "type": "message",
            "channel": "C123",
            "user": "U123",
            "text": "Webhook mesaji",
            "ts": "1712563200.000300",
        },
    }
    raw_body = json.dumps(webhook_body).encode("utf-8")
    monkeypatch.setattr("lawcopilot_api.integrations.runtime.time.time", lambda: 1712563200)
    timestamp = "1712563200"
    signature_payload = f"v0:{timestamp}:{raw_body.decode('utf-8')}".encode("utf-8")
    signature = f"v0={hmac_sha256(b'slack-signing-secret', signature_payload)}"
    webhook = service.ingest_webhook(
        "slack",
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
        },
        body=raw_body,
    )
    assert webhook["webhook_event"]["status"] == "processed"
    duplicate = service.ingest_webhook(
        "slack",
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
        },
        body=raw_body,
    )
    assert "zaten kuyruga alindi" in duplicate["message"]

    detail = service.get_connection_detail(connection_id)
    assert detail["webhook_preview"]
    assert len(detail["webhook_preview"]) == 1
    assert any(item["source_record_type"] == "message" for item in detail["resource_preview"])


@pytest.mark.parametrize(
    ("connector_id", "port", "schema"),
    [
        ("postgresql", 5432, "public"),
        ("mysql", 3306, "lawcopilot"),
        ("mssql", 1433, "dbo"),
    ],
)
def test_database_runtime_uses_database_adapter(monkeypatch, connector_id: str, port: int, schema: str):
    _configure_runtime_env(monkeypatch)
    service = _build_service(database_adapters={connector_id: FakePostgresAdapter()})

    saved = service.save_connection(
        IntegrationConnectionPayload(
            connector_id=connector_id,
            display_name="Ofis veri ambari",
            access_level="read_write",
            enabled=True,
            mock_mode=True,
            config={
                "connection_label": "Ofis veri ambari",
                "host": "db.example.com",
                "port": port,
                "database": "lawcopilot",
                "schema": schema,
                "username": "readonly",
                "table_allowlist": "cases",
            },
            secrets={"password": "secret"},
        ),
        actor="lawyer-tester",
    )
    connection_id = int(saved["connection"]["id"])

    checked = service.health_check_connection(connection_id, actor="lawyer-tester")
    assert checked["validation"]["health_status"] == "valid"

    synced = service.sync_connection(connection_id, actor="lawyer-tester")
    assert synced["record_count"] >= 2

    query = service.execute_action(
        connection_id,
        "run_query",
        IntegrationActionRequest(input={"query": "SELECT 1"}, confirmed=False),
        actor="lawyer-tester",
    )
    assert query["action_run"]["status"] == "completed"


def test_web_watch_connector_sync_action_and_scheduled_worker(monkeypatch):
    _configure_runtime_env(monkeypatch)
    web_intel = FakeWebIntelService(
        {
            "https://www.resmigazete.gov.tr/": [
                {
                    "url": "https://www.resmigazete.gov.tr/",
                    "final_url": "https://www.resmigazete.gov.tr/",
                    "reachable": True,
                    "render_mode": "cheap",
                    "title": "Resmî Gazete",
                    "meta_description": "Güncel karar ve duyurular",
                    "headings": ["Bugünkü kararlar"],
                    "visible_text": "Bugünkü kararlar ve duyurular yayınlandı.",
                    "summary": "Sayfa başarıyla çıkarıldı.",
                    "issues": [],
                    "artifacts": [],
                },
                {
                    "url": "https://www.resmigazete.gov.tr/",
                    "final_url": "https://www.resmigazete.gov.tr/",
                    "reachable": True,
                    "render_mode": "cheap",
                    "title": "Resmî Gazete",
                    "meta_description": "Güncel karar ve duyurular",
                    "headings": ["Bugünkü kararlar"],
                    "visible_text": "Bugünkü kararlar ve duyurular yayınlandı.",
                    "summary": "Sayfa başarıyla çıkarıldı.",
                    "issues": [],
                    "artifacts": [],
                },
                {
                    "url": "https://www.resmigazete.gov.tr/",
                    "final_url": "https://www.resmigazete.gov.tr/",
                    "reachable": True,
                    "render_mode": "cheap",
                    "title": "Resmî Gazete",
                    "meta_description": "Yeni karar metinleri eklendi",
                    "headings": ["Yeni karar", "Duyuru"],
                    "visible_text": "Yeni karar ve duyuru metni yayımlandı.",
                    "summary": "Sayfa başarıyla çıkarıldı.",
                    "issues": [],
                    "artifacts": [],
                },
            ]
        }
    )
    service = _build_service(web_intel=web_intel)

    saved = service.save_connection(
        IntegrationConnectionPayload(
            connector_id="web-watch",
            display_name="Resmî Gazete",
            access_level="read_only",
            enabled=True,
            mock_mode=False,
            config={
                "watch_label": "Resmî Gazete",
                "url": "https://www.resmigazete.gov.tr/",
                "check_interval_minutes": 60,
                "render_mode": "cheap",
                "notify_on_change": True,
                "summary_focus": "Yeni kararları öne çıkar.",
            },
            secrets={},
        ),
        actor="lawyer-tester",
    )
    connection_id = int(saved["connection"]["id"])

    checked = service.health_check_connection(connection_id, actor="lawyer-tester")
    assert checked["validation"]["health_status"] == "valid"

    first_sync = service.sync_connection(connection_id, actor="lawyer-tester")
    assert first_sync["sync_run"]["status"] == "completed"
    detail = service.get_connection_detail(connection_id)
    assert detail["resource_preview"]
    assert detail["resource_preview"][0]["title"] == "Resmî Gazete"

    action = service.execute_action(
        connection_id,
        "fetch_documents",
        IntegrationActionRequest(input={}, confirmed=False),
        actor="lawyer-tester",
    )
    assert action["action_run"]["status"] == "completed"

    second_sync = service.sync_connection(connection_id, actor="lawyer-tester")
    assert second_sync["sync_run"]["status"] == "completed"
    third_sync = service.sync_connection(connection_id, actor="lawyer-tester")
    assert third_sync["sync_run"]["status"] == "completed"
    detail_after = service.get_connection_detail(connection_id)
    assert any("değişiklik" in str(event["message"]).lower() or "degisiklik" in str(event["message"]).lower() for event in detail_after["event_preview"])

    repo = IntegrationRepository(Path(get_settings().db_path))
    repo.update_connection_runtime(
        get_settings().office_id,
        connection_id,
        last_sync_at="2026-04-01T00:00:00+00:00",
    )
    worker = IntegrationSyncWorker(service=service, poll_seconds=1, batch_size=3)
    service.attach_sync_worker(worker)
    tick = worker.tick()
    assert tick["count"] >= 1
