import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

import lawcopilot_api.app as app_module
from lawcopilot_api.app import create_app
from lawcopilot_api.audit import AuditLogger
from lawcopilot_api.auth import issue_token
from lawcopilot_api.config import get_settings
from lawcopilot_api.integrations.repository import IntegrationRepository
from lawcopilot_api.integrations.service import IntegrationPlatformService as RealIntegrationPlatformService
from lawcopilot_api.persistence import Persistence


def _configure_chat_integration_env(monkeypatch, *, dry_run: bool = True) -> None:
    temp_root = tempfile.mkdtemp(prefix="lawcopilot-chat-integrations-")
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(Path(temp_root) / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(Path(temp_root) / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(Path(temp_root) / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_CONNECTOR_DRY_RUN", "true" if dry_run else "false")
    monkeypatch.setenv("LAWCOPILOT_INTEGRATION_WORKER_ENABLED", "false")
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "false")
    monkeypatch.setenv("LAWCOPILOT_BROWSER_WORKER_ENABLED", "false")
    monkeypatch.setenv("LAWCOPILOT_CONNECTOR_HTTP_TIMEOUT", "2")


def _chat_integration_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        path = request.url.path
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
            if path == "/api/auth.test":
                return httpx.Response(200, json={"ok": True, "team": "LawCopilot Slack"})
            if path == "/api/conversations.list":
                return httpx.Response(
                    200,
                    json={"ok": True, "channels": [{"id": "C123", "name": "genel", "topic": {"value": "Ofis"}}]},
                )
            if path == "/api/conversations.history":
                return httpx.Response(
                    200,
                    json={"ok": True, "messages": [{"ts": "1712563200.000100", "text": "Merhaba Slack", "user": "U123"}]},
                )
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
                                "properties": {"Name": {"title": [{"plain_text": "Muktesep notlari"}]}},
                            }
                        ]
                    },
                )
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
            if path == "/v2/user/info/":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "open_id": "open-1",
                            "display_name": "LawCopilot TikTok",
                            "bio_description": "Dava videolari",
                            "follower_count": 12,
                        },
                        "error": {"code": "ok", "message": "", "log_id": "chat-test"},
                    },
                )
        return httpx.Response(404, json={"error": f"unhandled:{host}{path}"})

    return httpx.MockTransport(handler)


def _patch_chat_integration_service(monkeypatch) -> None:
    transport = _chat_integration_transport()
    web_watch_payload = {
        "url": "https://www.resmigazete.gov.tr/",
        "final_url": "https://www.resmigazete.gov.tr/",
        "reachable": True,
        "render_mode": "cheap",
        "title": "Resmî Gazete",
        "meta_description": "Karar ve duyurular",
        "headings": ["Bugünkü kararlar"],
        "visible_text": "Bugünkü kararlar yayınlandı.",
        "summary": "Sayfa başarıyla çıkarıldı.",
        "issues": [],
        "artifacts": [],
    }

    class _ChatWebIntel:
        def extract(self, *, url: str, render_mode: str = "auto", include_screenshot: bool = True):
            if "resmigazete" in url:
                return dict(web_watch_payload)
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

    class _PatchedIntegrationPlatformService(RealIntegrationPlatformService):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("http_transport", transport)
            kwargs.setdefault("web_intel", _ChatWebIntel())
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(app_module, "IntegrationPlatformService", _PatchedIntegrationPlatformService)


def _issue_chat_bearer_token(*, role: str, subject: str | None = None) -> str:
    settings = get_settings()
    store = Persistence(Path(settings.db_path))
    actor = subject or f"{role}-chat-tester"
    token, exp, sid = issue_token(settings.jwt_secret, subject=actor, role=role, ttl_seconds=3600)
    store.store_session(sid, actor, role, datetime.fromtimestamp(exp, timezone.utc).isoformat())
    return f"Bearer {token}"


async def _call_chat_json(
    app,
    method: str,
    url: str,
    *,
    authorization: str,
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
        (b"authorization", authorization.encode("utf-8")),
    ]
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


def test_assistant_thread_orchestrates_slack_connection_flow(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Connect Slack"})
    )
    assert first_status == 200
    first_setup = first_body["message"]["source_context"]["integration_setup"]
    assert first_body["message"]["generated_from"] == "assistant_integration_orchestration"
    assert first_setup["connector_id"] == "slack"
    assert first_setup["pending_field"]["key"] == "client_id"
    assert "Client ID" in first_body["message"]["content"]

    thread_id = int(first_body["thread"]["id"])

    second_status, second_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "slack-client-id"},
        )
    )
    assert second_status == 200
    assert second_body["message"]["source_context"]["integration_setup"]["pending_field"]["key"] == "client_secret"

    third_status, third_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "slack-client-secret"},
        )
    )
    assert third_status == 200
    third_setup = third_body["message"]["source_context"]["integration_setup"]
    assert third_setup["status"] == "oauth_pending"
    assert third_setup["oauth_session_state"]
    assert third_setup["authorization_url"]
    assert third_setup["capabilities"][:2] == ["Kanalları listele", "Mesajları oku"]
    last_user = next(item for item in reversed(third_body["messages"]) if item["role"] == "user")
    assert last_user["content"] == "[Gizli değer paylaşıldı: Client secret]"

    callback_status, _ = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/integrations/oauth/callback",
            authorization=authorization,
            payload={"state": third_setup["oauth_session_state"], "code": "slack-chat-code"},
        )
    )
    assert callback_status == 200

    resumed_status, resumed_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Durumu kontrol et"},
        )
    )
    assert resumed_status == 200
    assert "Slack bağlandı" in resumed_body["message"]["content"]
    assert "Son Slack mesajlarını özetle" in resumed_body["message"]["content"]
    assert resumed_body["message"]["source_context"]["integration_connection"]["auth_status"] == "authenticated"

    snapshot_status, snapshot_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Hangi entegrasyonlara erişimin var?"},
        )
    )
    assert snapshot_status == 200
    assert "Slack" in snapshot_body["message"]["content"]


def test_assistant_thread_orchestrates_notion_connection_flow(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Add Notion"})
    )
    assert first_status == 200
    thread_id = int(first_body["thread"]["id"])
    assert first_body["message"]["source_context"]["integration_setup"]["connector_id"] == "notion"
    assert first_body["message"]["source_context"]["integration_setup"]["pending_field"]["key"] == "workspace_label"

    second_status, second_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Hukuk Bilgi Merkezi"},
        )
    )
    assert second_status == 200
    assert second_body["message"]["source_context"]["integration_setup"]["pending_field"]["key"] == "integration_token"

    third_status, third_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "secret_notion_token"},
        )
    )
    assert third_status == 200
    assert "Notion bağlandı" in third_body["message"]["content"]
    assert "Son Notion sayfalarını özetle" in third_body["message"]["content"]
    last_user = next(item for item in reversed(third_body["messages"]) if item["role"] == "user")
    assert last_user["content"] == "[Gizli değer paylaşıldı: Entegrasyon anahtarı]"


def test_assistant_thread_prefers_whatsapp_setup_over_message_clarification(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    for prompt in ("whatsapp kuralım mı", "WhatsApp'ı bağlayalım", "whatsapp kurulumunu başlatalım"):
        status_code, body = asyncio.run(
            _call_chat_json(
                app,
                "POST",
                "/assistant/thread/messages",
                authorization=authorization,
                payload={"content": prompt},
            )
        )
        assert status_code == 200
        message = body["message"]
        setup = message["source_context"]["integration_setup"]
        assert message["generated_from"] == "assistant_integration_orchestration"
        assert setup["connector_id"] == "whatsapp"
        assert setup["status"] == "ready_for_desktop_action"
        assert setup["desktop_action"] == "start_whatsapp_web_link"
        assert setup["desktop_cta_label"] == "WhatsApp QR kurulumunu aç"
        assert "Mesajı hazırlamam için kime" not in message["content"]
        assert "WhatsApp" in message["content"]
        assert ("kurulum" in message["content"].lower()) or ("bağlantı" in message["content"].lower())


def test_assistant_thread_switches_from_pending_whatsapp_setup_to_google_setup(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"content": "whatsapp bağlayalım"},
        )
    )
    assert first_status == 200
    thread_id = int(first_body["thread"]["id"])
    first_setup = first_body["message"]["source_context"]["integration_setup"]
    assert first_setup["connector_id"] == "whatsapp"
    assert first_setup["status"] == "ready_for_desktop_action"

    second_status, second_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "google hesaplarını bağlayalım"},
        )
    )
    assert second_status == 200
    second_setup = second_body["message"]["source_context"]["integration_setup"]
    assert second_setup["connector_id"] == "gmail"
    assert second_setup["status"] == "collecting_input"
    assert second_setup["pending_field"]["key"] == "client_id"
    assert "WhatsApp kurulumu henüz tamamlanmış görünmüyor" not in second_body["message"]["content"]
    assert "Client ID" in second_body["message"]["content"]


def test_assistant_thread_recognizes_connected_whatsapp_web_setup(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    monkeypatch.setenv("LAWCOPILOT_WHATSAPP_ENABLED", "true")
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"content": "whatsapp bağlayalım"},
        )
    )
    assert first_status == 200
    thread_id = int(first_body["thread"]["id"])

    store = Persistence(Path(get_settings().db_path))
    store.upsert_connected_account(
        get_settings().office_id,
        "whatsapp",
        account_label="Sami",
        status="connected",
        scopes=["messages:read", "messages:send"],
        connected_at="2026-04-13T10:00:00+00:00",
        manual_review_required=True,
        metadata={
            "display_phone_number": "+90 555 000 00 00",
        },
    )

    resumed_status, resumed_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Durumu kontrol et"},
        )
    )
    assert resumed_status == 200
    assert "WhatsApp bağlı" in resumed_body["message"]["content"]
    assert resumed_body["message"]["source_context"]["integration_setup"]["status"] == "completed"


def test_assistant_thread_recognizes_connected_whatsapp_web_setup_from_desktop_config(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    monkeypatch.setenv("LAWCOPILOT_WHATSAPP_ENABLED", "true")
    monkeypatch.setenv("LAWCOPILOT_WHATSAPP_CONFIGURED", "true")
    monkeypatch.setenv("LAWCOPILOT_WHATSAPP_ACCOUNT_LABEL", "Sami")
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"content": "whatsapp bağlayalım"},
        )
    )
    assert first_status == 200
    assert "WhatsApp bağlı" in first_body["message"]["content"]
    assert first_body["message"]["source_context"]["integration_setup"] is None


def test_assistant_thread_orchestrates_web_watch_tracking(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=False)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    status_code, body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"content": "Resmi Gazete sayfasını takip et"},
        )
    )
    assert status_code == 200
    assert body["message"]["generated_from"] == "assistant_integration_orchestration"
    assert "Resmî Gazete takibi bağlandı" in body["message"]["content"]
    assert body["message"]["source_context"]["integration_connection"]["connector_id"] == "web-watch"


def test_assistant_thread_orchestrates_tiktok_generated_connector(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=False)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "TikTok'u bağla"})
    )
    assert first_status == 200
    setup = first_body["message"]["source_context"]["integration_setup"]
    assert setup["connector_id"] == "tiktok"
    assert setup["pending_field"]["key"] == "client_id"
    assert "Client key" in first_body["message"]["content"]

    thread_id = int(first_body["thread"]["id"])
    second_status, second_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "tiktok-client-key"},
        )
    )
    assert second_status == 200
    assert second_body["message"]["source_context"]["integration_setup"]["pending_field"]["key"] == "client_secret"

    review_status, review_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "tiktok-client-secret"},
        )
    )
    assert review_status == 200
    assert review_body["message"]["source_context"]["integration_setup"]["status"] == "review_pending"

    oauth_status, oauth_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Onaylıyorum"},
        )
    )
    assert oauth_status == 200
    oauth_setup = oauth_body["message"]["source_context"]["integration_setup"]
    assert oauth_setup["status"] == "oauth_pending"
    assert "www.tiktok.com/v2/auth/authorize/" in str(oauth_setup["authorization_url"] or "")

    callback_status, _ = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/integrations/oauth/callback",
            authorization=authorization,
            payload={"state": oauth_setup["oauth_session_state"], "code": "tiktok-chat-code"},
        )
    )
    assert callback_status == 200

    resumed_status, resumed_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Durumu kontrol et"},
        )
    )
    assert resumed_status == 200
    assert "TikTok bağlandı" in resumed_body["message"]["content"]
    assert resumed_body["message"]["source_context"]["integration_connection"]["auth_status"] == "authenticated"


def test_assistant_thread_asks_database_provider_before_connector_selection(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Connect my database"})
    )
    assert first_status == 200
    assert "PostgreSQL" in first_body["message"]["content"]
    assert first_body["message"]["source_context"]["integration_setup"]["awaiting_provider_choice"] is True

    thread_id = int(first_body["thread"]["id"])
    second_status, second_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "PostgreSQL"},
        )
    )
    assert second_status == 200
    second_setup = second_body["message"]["source_context"]["integration_setup"]
    assert second_setup["connector_id"] == "postgresql"
    assert second_setup["pending_field"]["key"] == "connection_label"


def test_assistant_thread_routes_generic_api_intent_into_connector_setup(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    status, body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Integrate my CRM API"})
    )
    assert status == 200
    setup = body["message"]["source_context"]["integration_setup"]
    assert setup["connector_id"] == "generic-rest"
    assert setup["pending_field"]["key"] == "service_label"
    assert "Generic REST API" in body["message"]["content"]


def test_assistant_thread_collects_google_setup_and_prepares_desktop_action(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    monkeypatch.setenv("LAWCOPILOT_GOOGLE_CLIENT_ID_CONFIGURED", "true")
    monkeypatch.setenv("LAWCOPILOT_GOOGLE_CLIENT_SECRET_CONFIGURED", "true")
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Google hesabımı bağla"})
    )
    assert first_status == 200
    setup = first_body["message"]["source_context"]["integration_setup"]
    assert setup["connector_id"] == "gmail"
    assert setup["status"] == "ready_for_desktop_action"
    assert setup["setup_mode"] == "legacy_desktop"
    assert setup["deep_link_path"] == "/settings?tab=kurulum&section=integration-google"
    assert setup["pending_field"] is None
    assert setup["desktop_action"] == "start_google_auth"
    assert setup["desktop_cta_label"] == "Google izin ekranını aç"
    assert "Client ID" not in first_body["message"]["content"]
    assert "Slack" not in first_body["message"]["content"]

    thread_id = int(first_body["thread"]["id"])

    prepare_status, prepare_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            f"/integrations/assistant-setups/{setup['id']}/desktop/prepare",
            authorization=authorization,
            payload={},
        )
    )
    assert prepare_status == 200
    assert prepare_body["desktop_action"] == "start_google_auth"
    assert prepare_body["config_patch"] == {}

    settings = get_settings()
    store = Persistence(Path(settings.db_path))
    store.upsert_connected_account(
        settings.office_id,
        "google",
        account_label="Google hesabı",
        status="connected",
        scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/calendar.readonly"],
        connected_at="2026-04-08T08:00:00+00:00",
        last_sync_at="2026-04-08T08:00:00+00:00",
        manual_review_required=True,
        metadata={"source": "test"},
    )

    resumed_status, resumed_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Durumu kontrol et"},
        )
    )
    assert resumed_status == 200
    assert "Google hesabı bağlı görünüyor" in resumed_body["message"]["content"]
    assert "Son Google e-postalarını özetle" in resumed_body["message"]["content"]


def test_assistant_thread_starts_google_setup_from_semantic_phrase(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    monkeypatch.setenv("LAWCOPILOT_GOOGLE_CLIENT_ID_CONFIGURED", "true")
    monkeypatch.setenv("LAWCOPILOT_GOOGLE_CLIENT_SECRET_CONFIGURED", "true")
    _patch_chat_integration_service(monkeypatch)

    def fake_runtime_completion(runtime, prompt, events_obj=None, *, task, **meta):
        if task == "assistant_dispatch_plan":
            return {
                "text": json.dumps(
                    {
                        "kind": "integration_setup",
                        "confidence": "high",
                        "reason": "Kullanıcı Google kurulumu başlatmak istiyor.",
                    }
                )
            }
        if task == "assistant_integration_setup_plan":
            return {
                "text": json.dumps(
                    {
                        "connector_id": "google",
                        "confidence": "high",
                        "reason": "Genel Google hesabı kurulumu istiyor.",
                    }
                )
            }
        return None

    monkeypatch.setattr(app_module, "_maybe_runtime_completion", fake_runtime_completion)

    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    status, body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "google kurak"})
    )

    assert status == 200
    setup = body["message"]["source_context"]["integration_setup"]
    assert setup["connector_id"] == "gmail"
    assert setup["status"] == "ready_for_desktop_action"
    assert setup["desktop_action"] == "start_google_auth"
    assert "Slack" not in body["message"]["content"]
    assert "Google" in body["message"]["content"]


def test_assistant_thread_explains_google_setup_step_by_step_instead_of_repeating_canned_reply(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    monkeypatch.setenv("LAWCOPILOT_GOOGLE_CLIENT_ID_CONFIGURED", "true")
    monkeypatch.setenv("LAWCOPILOT_GOOGLE_CLIENT_SECRET_CONFIGURED", "true")
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Google hesabımı bağla"})
    )
    assert first_status == 200
    thread_id = int(first_body["thread"]["id"])

    follow_status, follow_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Tam anlayamadım, adım adım söyle"},
        )
    )

    assert follow_status == 200
    content = follow_body["message"]["content"]
    assert "Google hesabı kurulumunu şu sırayla tamamlayacağız" in content
    assert "Google izin ekranını aç" in content
    assert "Durumu kontrol et" in content
    assert "kurulumu henüz tamamlanmış görünmüyor" not in content


def test_assistant_thread_explains_where_to_find_google_client_id(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Google hesabımı bağla"})
    )
    assert first_status == 200
    setup = first_body["message"]["source_context"]["integration_setup"]
    assert setup["pending_field"]["key"] == "client_id"
    thread_id = int(first_body["thread"]["id"])

    follow_status, follow_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Client ID'yi nereden alacağım?"},
        )
    )

    assert follow_status == 200
    content = follow_body["message"]["content"]
    assert "Google Cloud Console" in content
    assert "OAuth client ID" in content or "OAuth client" in content
    assert "Client ID değerini bana tek mesaj olarak gönder" in content
    assert "Yalnızca bu değeri tek mesaj olarak göndermen yeterli." not in content


def test_assistant_thread_advances_google_setup_after_collecting_client_values(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Google hesabımı bağla"})
    )
    assert first_status == 200
    thread_id = int(first_body["thread"]["id"])
    first_setup = first_body["message"]["source_context"]["integration_setup"]
    assert first_setup["pending_field"]["key"] == "client_id"

    second_status, second_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "test-google-client-id-for-chat-flow"},
        )
    )
    assert second_status == 200
    second_setup = second_body["message"]["source_context"]["integration_setup"]
    assert second_setup["pending_field"]["key"] == "client_secret"

    final_status, final_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "test-google-client-secret-for-chat-flow"},
        )
    )
    assert final_status == 200
    final_setup = final_body["message"]["source_context"]["integration_setup"]
    assert final_setup["status"] == "ready_for_desktop_action"
    assert final_setup["pending_field"] is None
    assert final_setup["desktop_action"] == "start_google_auth"
    assert final_setup["desktop_cta_label"] == "Google izin ekranını aç"
    assert "OAuth istemcisinin hazır olduğunu doğrula" not in final_body["message"]["content"]
    assert "Google izin ekranını aç" in final_body["message"]["content"]


def test_assistant_thread_allows_reopening_google_client_id_after_wrong_value(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Google hesabımı bağla"})
    )
    assert first_status == 200
    thread_id = int(first_body["thread"]["id"])

    second_status, second_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "test-google-client-id-wrong"},
        )
    )
    assert second_status == 200
    assert second_body["message"]["source_context"]["integration_setup"]["pending_field"]["key"] == "client_secret"

    retry_status, retry_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Yanlış istemci kimliği girmişim, tekrar gireceğim"},
        )
    )
    assert retry_status == 200
    retry_setup = retry_body["message"]["source_context"]["integration_setup"]
    assert retry_setup["status"] == "collecting_input"
    assert retry_setup["pending_field"]["key"] == "client_id"
    assert "Client ID" in retry_body["message"]["content"]


def test_assistant_thread_collects_outlook_tenant_then_client_id_and_auto_runs_ready_action(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)

    def fake_runtime_completion(runtime, prompt, events_obj=None, *, task, **meta):
        if task == "assistant_integration_followup_plan":
            prompt_text = str(prompt or "")
            if "Kullanıcı sorgusu: bağla" in prompt_text:
                return {
                    "text": json.dumps(
                        {
                            "intent": "execute_desktop_action",
                            "connector_id": "outlook-mail",
                            "field_key": "none",
                            "confidence": "high",
                            "reason": "Kullanıcı son adımı başlatmak istiyor.",
                        }
                    )
                }
        return None

    monkeypatch.setattr(app_module, "_maybe_runtime_completion", fake_runtime_completion)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Outlook hesabımı bağla"})
    )
    assert first_status == 200
    first_setup = first_body["message"]["source_context"]["integration_setup"]
    assert first_setup["connector_id"] == "outlook-mail"
    assert first_setup["pending_field"]["key"] == "client_id"
    thread_id = int(first_body["thread"]["id"])

    tenant_status, tenant_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Kiracı kimliğim 11111111-2222-3333-4444-555555555555"},
        )
    )
    assert tenant_status == 200
    tenant_setup = tenant_body["message"]["source_context"]["integration_setup"]
    assert tenant_setup["status"] == "collecting_input"
    assert tenant_setup["pending_field"]["key"] == "client_id"
    assert "Client ID" in tenant_body["message"]["content"]

    client_status, client_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
        )
    )
    assert client_status == 200
    client_setup = client_body["message"]["source_context"]["integration_setup"]
    assert client_setup["status"] == "ready_for_desktop_action"
    assert client_setup["desktop_action"] == "start_outlook_auth"

    proceed_status, proceed_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "bağla"},
        )
    )
    assert proceed_status == 200
    proceed_setup = proceed_body["message"]["source_context"]["integration_setup"]
    assert proceed_setup["desktop_action"] == "start_outlook_auth"
    assert proceed_setup["auto_run_desktop_action"] is True
    assert "Microsoft izin ekranını aç" in proceed_body["message"]["content"]

    prepare_status, prepare_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            f"/integrations/assistant-setups/{proceed_setup['id']}/desktop/prepare",
            authorization=authorization,
            payload={},
        )
    )
    assert prepare_status == 200
    assert prepare_body["desktop_action"] == "start_outlook_auth"
    assert prepare_body["config_patch"]["outlook"]["tenantId"] == "11111111-2222-3333-4444-555555555555"
    assert prepare_body["config_patch"]["outlook"]["clientId"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_assistant_thread_uses_semantic_followup_plan_for_active_whatsapp_setup(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)

    def fake_runtime_completion(runtime, prompt, events_obj=None, *, task, **meta):
        if task == "assistant_integration_followup_plan":
            return {
                "text": json.dumps(
                    {
                        "intent": "explain_current",
                        "connector_id": "whatsapp",
                        "confidence": "high",
                        "reason": "Kullanıcı aktif WhatsApp kurulumunu daha açık anlatmamı istiyor.",
                    }
                )
            }
        return None

    monkeypatch.setattr(app_module, "_maybe_runtime_completion", fake_runtime_completion)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "WhatsApp bağlayalım"})
    )
    assert first_status == 200
    thread_id = int(first_body["thread"]["id"])

    follow_status, follow_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Bana açıklasana"},
        )
    )

    assert follow_status == 200
    content = follow_body["message"]["content"]
    assert "WhatsApp kurulumunu şu sırayla tamamlayacağız" in content
    assert "WhatsApp QR kurulumunu aç" in content
    assert "QR kodu telefonundan okuttuktan sonra" in content
    assert "Google" not in content


def test_assistant_thread_collects_telegram_setup_and_prepares_desktop_action(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Telegram bağla"})
    )
    assert first_status == 200
    first_setup = first_body["message"]["source_context"]["integration_setup"]
    assert first_setup["connector_id"] == "telegram"
    assert first_setup["status"] == "collecting_input"
    assert first_setup["pending_field"]["key"] == "bot_token"
    assert first_setup["deep_link_path"] == "/settings?tab=kurulum&section=integration-telegram"
    assert "Bot token" in first_body["message"]["content"]
    assert "Mesajları oku" in first_setup["capabilities"]

    thread_id = int(first_body["thread"]["id"])

    second_status, second_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "123456:telegram-token"},
        )
    )
    assert second_status == 200
    second_setup = second_body["message"]["source_context"]["integration_setup"]
    assert second_setup["status"] == "collecting_input"
    assert second_setup["pending_field"]["key"] == "allowed_user_id"

    third_status, third_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "987654321"},
        )
    )
    assert third_status == 200
    third_setup = third_body["message"]["source_context"]["integration_setup"]
    assert third_setup["status"] == "ready_for_desktop_action"
    assert third_setup["desktop_action"] == "save_telegram"
    assert third_setup["desktop_cta_label"] == "Telegram ayarını kaydet"

    prepare_status, prepare_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            f"/integrations/assistant-setups/{third_setup['id']}/desktop/prepare",
            authorization=authorization,
            payload={},
        )
    )
    assert prepare_status == 200
    assert prepare_body["desktop_action"] == "save_telegram"
    assert prepare_body["config_patch"]["telegram"]["botToken"] == "123456:telegram-token"
    assert prepare_body["config_patch"]["telegram"]["allowedUserId"] == "987654321"


def test_assistant_thread_prefers_telegram_web_mode_for_personal_account_request(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Telegram kişisel hesabımı bağla, DM'lere erişsin"})
    )
    assert first_status == 200
    first_setup = first_body["message"]["source_context"]["integration_setup"]
    assert first_setup["connector_id"] == "telegram"
    assert first_setup["status"] == "ready_for_desktop_action"
    assert first_setup["desktop_action"] == "start_telegram_web_link"
    assert first_setup["desktop_cta_label"] == "Telegram Web oturumunu aç"
    assert "Bot token" not in first_body["message"]["content"]

    prepare_status, prepare_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            f"/integrations/assistant-setups/{first_setup['id']}/desktop/prepare",
            authorization=authorization,
            payload={},
        )
    )
    assert prepare_status == 200
    assert prepare_body["desktop_action"] == "start_telegram_web_link"
    assert prepare_body["config_patch"]["telegram"]["mode"] == "web"
    assert prepare_body["config_patch"]["telegram"]["webSessionName"] == "default"


def test_assistant_thread_collects_instagram_setup_and_prepares_desktop_action(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Instagram hesabımı bağla"})
    )
    assert first_status == 200
    first_setup = first_body["message"]["source_context"]["integration_setup"]
    assert first_setup["connector_id"] == "instagram"
    assert first_setup["status"] == "collecting_input"
    assert first_setup["pending_field"]["key"] == "client_id"
    assert first_setup["deep_link_path"] == "/settings?tab=kurulum&section=integration-instagram"
    assert "Client ID" in first_body["message"]["content"]

    thread_id = int(first_body["thread"]["id"])

    second_status, second_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "instagram-client-id"},
        )
    )
    assert second_status == 200
    assert second_body["message"]["source_context"]["integration_setup"]["pending_field"]["key"] == "client_secret"

    third_status, third_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "instagram-client-secret"},
        )
    )
    assert third_status == 200
    third_setup = third_body["message"]["source_context"]["integration_setup"]
    assert third_setup["status"] == "ready_for_desktop_action"
    assert third_setup["desktop_action"] == "start_instagram_auth"
    assert third_setup["desktop_cta_label"] == "Instagram izin ekranını aç"

    prepare_status, prepare_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            f"/integrations/assistant-setups/{third_setup['id']}/desktop/prepare",
            authorization=authorization,
            payload={},
        )
    )
    assert prepare_status == 200
    assert prepare_body["desktop_action"] == "start_instagram_auth"
    assert prepare_body["config_patch"]["instagram"]["clientId"] == "instagram-client-id"
    assert prepare_body["config_patch"]["instagram"]["clientSecret"] == "instagram-client-secret"
    assert prepare_body["config_patch"]["instagram"]["pageNameHint"] == ""


def test_assistant_thread_collects_linkedin_setup_and_prepares_desktop_action(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "LinkedIn hesabımı bağla"})
    )
    assert first_status == 200
    first_setup = first_body["message"]["source_context"]["integration_setup"]
    assert first_setup["connector_id"] == "linkedin"
    assert first_setup["status"] == "collecting_input"
    assert first_setup["pending_field"]["key"] == "client_id"
    assert first_setup["deep_link_path"] == "/settings?tab=kurulum&section=integration-linkedin"
    assert "Client ID" in first_body["message"]["content"]

    thread_id = int(first_body["thread"]["id"])

    second_status, second_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "linkedin-client-id"},
        )
    )
    assert second_status == 200
    assert second_body["message"]["source_context"]["integration_setup"]["pending_field"]["key"] == "client_secret"

    third_status, third_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "linkedin-client-secret"},
        )
    )
    assert third_status == 200
    third_setup = third_body["message"]["source_context"]["integration_setup"]
    assert third_setup["status"] == "ready_for_desktop_action"
    assert third_setup["desktop_action"] == "start_linkedin_auth"
    assert third_setup["desktop_cta_label"] == "LinkedIn izin ekranını aç"

    prepare_status, prepare_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            f"/integrations/assistant-setups/{third_setup['id']}/desktop/prepare",
            authorization=authorization,
            payload={},
        )
    )
    assert prepare_status == 200
    assert prepare_body["desktop_action"] == "start_linkedin_auth"
    assert prepare_body["config_patch"]["linkedin"]["clientId"] == "linkedin-client-id"
    assert prepare_body["config_patch"]["linkedin"]["clientSecret"] == "linkedin-client-secret"


def test_assistant_thread_prefers_linkedin_web_mode_for_dm_request(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "LinkedIn DM'lerime erişsin, kişisel hesabımı bağla"})
    )
    assert first_status == 200
    first_setup = first_body["message"]["source_context"]["integration_setup"]
    assert first_setup["connector_id"] == "linkedin"
    assert first_setup["status"] == "ready_for_desktop_action"
    assert first_setup["desktop_action"] == "start_linkedin_web_link"
    assert first_setup["desktop_cta_label"] == "LinkedIn Web oturumunu aç"
    assert "Client ID" not in first_body["message"]["content"]

    prepare_status, prepare_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            f"/integrations/assistant-setups/{first_setup['id']}/desktop/prepare",
            authorization=authorization,
            payload={},
        )
    )
    assert prepare_status == 200
    assert prepare_body["desktop_action"] == "start_linkedin_web_link"
    assert prepare_body["config_patch"]["linkedin"]["mode"] == "web"
    assert prepare_body["config_patch"]["linkedin"]["webSessionName"] == "default"


def test_assistant_thread_requires_review_before_live_generated_connector(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=False)
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Connect Slack"})
    )
    assert first_status == 200
    thread_id = int(first_body["thread"]["id"])

    collect_status, _ = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "slack-client-id"},
        )
    )
    assert collect_status == 200

    gated_status, gated_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "slack-client-secret"},
        )
    )
    assert gated_status == 200
    assert "onayını almam gerekiyor" in gated_body["message"]["content"].lower()
    assert gated_body["message"]["source_context"]["integration_setup"]["status"] == "review_pending"
    assert gated_body["message"]["source_context"]["integration_setup"]["authorization_url"] in {None, ""}

    approved_status, approved_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Onaylıyorum"},
        )
    )
    assert approved_status == 200
    approved_setup = approved_body["message"]["source_context"]["integration_setup"]
    assert approved_setup["status"] == "oauth_pending"
    assert approved_setup["authorization_url"]


def test_assistant_thread_recovers_from_stale_setup(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    monkeypatch.setenv("LAWCOPILOT_INTEGRATION_ASSISTANT_SETUP_TIMEOUT_MINUTES", "30")
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Connect Slack"})
    )
    assert first_status == 200
    thread_id = int(first_body["thread"]["id"])

    repo = IntegrationRepository(Path(get_settings().db_path))
    active = repo.get_active_assistant_setup(get_settings().office_id, thread_id)
    assert active is not None
    with repo._conn() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE integration_assistant_setups SET updated_at=? WHERE office_id=? AND id=?",
            ("2026-04-07T00:00:00+00:00", get_settings().office_id, int(active["id"])),
        )

    resume_status, resume_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Durumu kontrol et"},
        )
    )
    assert resume_status == 200
    assert "cok uzun sure yarim kaldigi icin kapatildi" in resume_body["message"]["content"]

    restart_status, restart_body = asyncio.run(
        _call_chat_json(
            app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Connect Slack"},
        )
    )
    assert restart_status == 200
    assert restart_body["message"]["source_context"]["integration_setup"]["pending_field"]["key"] == "client_id"


def test_assistant_thread_recovers_when_secret_key_rotates(monkeypatch):
    _configure_chat_integration_env(monkeypatch, dry_run=True)
    monkeypatch.setenv("LAWCOPILOT_INTEGRATION_SECRET_KEY", "first-secret-key")
    _patch_chat_integration_service(monkeypatch)
    app = create_app()
    authorization = _issue_chat_bearer_token(role="lawyer")

    first_status, first_body = asyncio.run(
        _call_chat_json(app, "POST", "/assistant/thread/messages", authorization=authorization, payload={"content": "Connect Slack"})
    )
    assert first_status == 200
    thread_id = int(first_body["thread"]["id"])
    settings = get_settings()
    repo = IntegrationRepository(Path(settings.db_path))
    active = repo.get_active_assistant_setup(settings.office_id, thread_id)
    assert active is not None
    old_service = RealIntegrationPlatformService(
        settings=settings,
        store=Persistence(Path(settings.db_path)),
        audit=AuditLogger(Path(settings.audit_log_path)),
        db_path=Path(settings.db_path),
    )
    updated = repo.upsert_assistant_setup(
        settings.office_id,
        thread_id=thread_id,
        setup_id=int(active["id"]),
        connector_id="slack",
        service_name="Slack",
        request_text=str(active.get("request_text") or "Connect Slack"),
        status="collecting_input",
        missing_fields=list(active.get("missing_fields") or []),
        collected_config={"client_id": "slack-client-id"},
        secret_blob=old_service.secret_box.seal_json({"client_secret": "slack-client-secret"}),
        metadata={
            **dict(active.get("metadata") or {}),
            "pending_field": {
                "key": "workspace_label",
                "label": "Workspace etiketi",
                "kind": "text",
                "target": "config",
                "required": True,
            },
        },
        created_by="lawyer-chat-tester",
    )
    assert updated["status"] == "collecting_input"

    monkeypatch.setenv("LAWCOPILOT_INTEGRATION_SECRET_KEY", "rotated-secret-key")
    _patch_chat_integration_service(monkeypatch)
    restarted_app = create_app()

    resumed_status, resumed_body = asyncio.run(
        _call_chat_json(
            restarted_app,
            "POST",
            "/assistant/thread/messages",
            authorization=authorization,
            payload={"thread_id": thread_id, "content": "Connect Slack"},
        )
    )
    assert resumed_status == 200
    assert "yarım kurulum sıfırlandı" in resumed_body["message"]["content"]
    assert resumed_body["message"]["source_context"]["integration_setup"]["pending_field"]["key"] == "client_id"
