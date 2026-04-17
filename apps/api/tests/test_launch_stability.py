from pathlib import Path

import pytest
from fastapi import HTTPException

from lawcopilot_api.app import create_app
from lawcopilot_api.config import get_settings
from lawcopilot_api.schemas import TokenRequest


def _route_endpoint(app, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) != path:
            continue
        if method.upper() not in getattr(route, "methods", set()):
            continue
        return route.endpoint
    raise AssertionError(f"route not found: {method} {path}")


def _apply_runtime_env(monkeypatch, tmp_path: Path, **env: str) -> None:
    monkeypatch.setenv("LAWCOPILOT_DB_PATH", str(tmp_path / "lawcopilot.db"))
    monkeypatch.setenv("LAWCOPILOT_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_STRUCTURED_LOG", str(tmp_path / "events.log.jsonl"))
    monkeypatch.setenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "false")
    monkeypatch.setenv("LAWCOPILOT_INTEGRATION_WORKER_ENABLED", "false")
    monkeypatch.setenv("LAWCOPILOT_BROWSER_WORKER_ENABLED", "false")
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_token_bootstrap_disabled_in_pilot_without_key(monkeypatch, tmp_path: Path):
    _apply_runtime_env(
        monkeypatch,
        tmp_path,
        LAWCOPILOT_ENVIRONMENT="pilot",
        LAWCOPILOT_ALLOW_LOCAL_TOKEN_BOOTSTRAP="false",
        LAWCOPILOT_BOOTSTRAP_ADMIN_KEY="",
    )
    issue_token = _route_endpoint(create_app(), "/auth/token", "POST")

    with pytest.raises(HTTPException) as exc:
        issue_token(TokenRequest(subject="pilot-user", role="lawyer"))
    assert exc.value.status_code == 403
    assert exc.value.detail == "token_bootstrap_disabled"


def test_token_bootstrap_requires_key_when_configured(monkeypatch, tmp_path: Path):
    _apply_runtime_env(
        monkeypatch,
        tmp_path,
        LAWCOPILOT_ENVIRONMENT="pilot",
        LAWCOPILOT_ALLOW_LOCAL_TOKEN_BOOTSTRAP="false",
        LAWCOPILOT_BOOTSTRAP_ADMIN_KEY="super-secret-bootstrap",
    )
    issue_token = _route_endpoint(create_app(), "/auth/token", "POST")

    with pytest.raises(HTTPException) as exc:
        issue_token(TokenRequest(subject="desktop-runtime", role="lawyer"))
    assert exc.value.status_code == 403
    assert exc.value.detail == "runtime_bootstrap_key_required"

    allowed = issue_token(
        TokenRequest(
            subject="desktop-runtime",
            role="lawyer",
            bootstrap_key="super-secret-bootstrap",
        )
    )
    assert allowed["access_token"]


def test_local_token_bootstrap_allowed_for_test_runtime(monkeypatch, tmp_path: Path):
    _apply_runtime_env(
        monkeypatch,
        tmp_path,
        LAWCOPILOT_ENVIRONMENT="test",
        LAWCOPILOT_ALLOW_LOCAL_TOKEN_BOOTSTRAP="true",
        LAWCOPILOT_BOOTSTRAP_ADMIN_KEY="",
    )
    issue_token = _route_endpoint(create_app(), "/auth/token", "POST")

    response = issue_token(TokenRequest(subject="test-user", role="lawyer"))
    assert response["access_token"]

    with pytest.raises(HTTPException) as exc:
        issue_token(TokenRequest(subject="admin-user", role="admin"))
    assert exc.value.status_code == 403
    assert exc.value.detail == "admin_bootstrap_key_required"


def test_local_token_bootstrap_allows_non_admin_without_runtime_key_even_when_admin_key_exists(monkeypatch, tmp_path: Path):
    _apply_runtime_env(
        monkeypatch,
        tmp_path,
        LAWCOPILOT_ENVIRONMENT="test",
        LAWCOPILOT_ALLOW_LOCAL_TOKEN_BOOTSTRAP="true",
        LAWCOPILOT_BOOTSTRAP_ADMIN_KEY="super-secret-bootstrap",
    )
    issue_token = _route_endpoint(create_app(), "/auth/token", "POST")

    response = issue_token(TokenRequest(subject="test-user", role="lawyer"))
    assert response["access_token"]

    with pytest.raises(HTTPException) as exc:
        issue_token(TokenRequest(subject="admin-user", role="admin"))
    assert exc.value.status_code == 403
    assert exc.value.detail == "admin_bootstrap_key_required"


def test_pytest_defaults_disable_background_workers(monkeypatch, tmp_path: Path):
    _apply_runtime_env(
        monkeypatch,
        tmp_path,
        LAWCOPILOT_ENVIRONMENT="test",
    )
    settings = get_settings()
    assert settings.integration_worker_enabled is False
    assert settings.browser_worker_enabled is False
    assert settings.personal_kb_startup_bootstrap_enabled is False
