from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from .models import ConnectorSpec


def generate_state_token() -> str:
    return secrets.token_urlsafe(24)


def generate_pkce_verifier() -> str:
    return secrets.token_urlsafe(48)


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(str(verifier or "").encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorization_url(
    *,
    spec: ConnectorSpec,
    connection: dict[str, Any],
    state: str,
    verifier: str,
    redirect_uri: str,
    requested_scopes: list[str],
) -> str:
    authorization_url = str(spec.auth_config.authorization_url or "").strip()
    if not authorization_url:
        raise ValueError("oauth_authorization_url_missing")
    config = dict(connection.get("config") or {})
    client_id = str(config.get("client_id") or "").strip()
    if not client_id:
        raise ValueError("oauth_client_id_missing")

    separator = spec.auth_config.scope_separator or " "
    client_id_key = _oauth_field_name(spec, "client_id", "client_id")
    redirect_uri_key = _oauth_field_name(spec, "redirect_uri", "redirect_uri")
    response_type_key = _oauth_field_name(spec, "response_type", "response_type")
    scope_key = _oauth_field_name(spec, "scope", "scope")
    state_key = _oauth_field_name(spec, "state", "state")
    params = {
        client_id_key: client_id,
        redirect_uri_key: redirect_uri,
        response_type_key: "code",
        scope_key: separator.join(requested_scopes),
        state_key: state,
    }
    if spec.auth_config.pkce_required:
        params[_oauth_field_name(spec, "code_challenge", "code_challenge")] = pkce_challenge(verifier)
        params[_oauth_field_name(spec, "code_challenge_method", "code_challenge_method")] = "S256"
    return f"{authorization_url}?{urlencode(params)}"
def build_auth_summary(
    *,
    spec: ConnectorSpec,
    status: str,
    requested_scopes: list[str],
    granted_scopes: list[str] | None = None,
    expires_at: str | None = None,
    refresh_token_present: bool = False,
    last_refreshed_at: str | None = None,
    last_revoked_at: str | None = None,
    permission_summary: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "auth_type": spec.auth_type,
        "supports_refresh": bool(spec.auth_config.supports_refresh),
        "requested_scopes": list(requested_scopes),
        "granted_scopes": list(granted_scopes or requested_scopes),
        "expires_at": expires_at,
        "refresh_token_present": bool(refresh_token_present),
        "last_refreshed_at": last_refreshed_at,
        "last_revoked_at": last_revoked_at,
        "permission_summary": list(permission_summary or []),
    }


def summarize_scope_permissions(scopes: list[str]) -> list[str]:
    summary: list[str] = []
    for scope in scopes:
        normalized = str(scope or "").strip()
        if not normalized:
            continue
        if "write" in normalized or normalized.endswith(":write") or normalized.endswith(".write"):
            summary.append(f"Yazma erisimi: {normalized}")
        elif "delete" in normalized:
            summary.append(f"Silme erisimi: {normalized}")
        else:
            summary.append(f"Okuma erisimi: {normalized}")
    return summary


def auth_status_from_summary(summary: dict[str, Any] | None) -> str:
    data = dict(summary or {})
    status = str(data.get("status") or "pending")
    expires_at = str(data.get("expires_at") or "").strip()
    if status == "authenticated" and expires_at:
        try:
            parsed = datetime.fromisoformat(expires_at)
        except ValueError:
            return status
        if parsed <= datetime.now(timezone.utc):
            return "expired"
    return status


def exchange_authorization_code(
    *,
    spec: ConnectorSpec,
    connection: dict[str, Any],
    session: dict[str, Any],
    code: str,
    client_secret: str | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 20,
) -> dict[str, Any]:
    token_url = str(spec.auth_config.token_url or "").strip()
    if not token_url:
        raise ValueError("oauth_token_url_missing")
    config = dict(connection.get("config") or {})
    client_id = str(config.get("client_id") or "").strip()
    client_secret = str(client_secret or session.get("client_secret") or config.get("client_secret") or "").strip()
    redirect_uri = str(session.get("redirect_uri") or config.get("redirect_uri") or "").strip()
    if not client_id:
        raise ValueError("oauth_client_id_missing")
    grant_type_key = _oauth_field_name(spec, "grant_type", "grant_type")
    code_key = _oauth_field_name(spec, "code", "code")
    client_id_key = _oauth_field_name(spec, "client_id", "client_id")
    redirect_uri_key = _oauth_field_name(spec, "redirect_uri", "redirect_uri")
    client_secret_key = _oauth_field_name(spec, "client_secret", "client_secret")
    payload = {
        grant_type_key: "authorization_code",
        code_key: code,
        client_id_key: client_id,
        redirect_uri_key: redirect_uri,
    }
    if client_secret:
        payload[client_secret_key] = client_secret
    verifier = str(session.get("code_verifier") or "").strip()
    if verifier:
        payload[_oauth_field_name(spec, "code_verifier", "code_verifier")] = verifier
    return _request_token_bundle(token_url=token_url, payload=payload, transport=transport, timeout_seconds=timeout_seconds)


def refresh_access_token(
    *,
    spec: ConnectorSpec,
    connection: dict[str, Any],
    refresh_token: str,
    client_secret: str | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 20,
) -> dict[str, Any]:
    token_url = str(spec.auth_config.token_url or "").strip()
    if not token_url:
        raise ValueError("oauth_token_url_missing")
    config = dict(connection.get("config") or {})
    client_id = str(config.get("client_id") or "").strip()
    client_secret = str(client_secret or config.get("client_secret") or "").strip()
    grant_type_key = _oauth_field_name(spec, "grant_type", "grant_type")
    refresh_token_key = _oauth_field_name(spec, "refresh_token", "refresh_token")
    client_id_key = _oauth_field_name(spec, "client_id", "client_id")
    client_secret_key = _oauth_field_name(spec, "client_secret", "client_secret")
    payload = {
        grant_type_key: "refresh_token",
        refresh_token_key: refresh_token,
        client_id_key: client_id,
    }
    if client_secret:
        payload[client_secret_key] = client_secret
    return _request_token_bundle(token_url=token_url, payload=payload, transport=transport, timeout_seconds=timeout_seconds)


def revoke_access_token(
    *,
    spec: ConnectorSpec,
    connection: dict[str, Any],
    token: str,
    client_secret: str | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 20,
) -> dict[str, Any]:
    revocation_url = str(spec.auth_config.revocation_url or "").strip()
    if not revocation_url:
        return {"revoked": False, "reason": "revocation_not_configured"}
    config = dict(connection.get("config") or {})
    client_id = str(config.get("client_id") or "").strip()
    client_secret = str(client_secret or config.get("client_secret") or "").strip()
    payload = {_oauth_field_name(spec, "token", "token"): token}
    if client_id:
        payload[_oauth_field_name(spec, "client_id", "client_id")] = client_id
    if client_secret:
        payload[_oauth_field_name(spec, "client_secret", "client_secret")] = client_secret
    with httpx.Client(transport=transport, timeout=timeout_seconds, follow_redirects=True) as client:
        response = client.post(revocation_url, data=payload, headers={"User-Agent": "LawCopilot-OAuth/1.0"})
    if response.status_code >= 400:
        raise ValueError(f"oauth_revocation_failed:{response.status_code}")
    return {"revoked": True, "status_code": response.status_code}


def _request_token_bundle(
    *,
    token_url: str,
    payload: dict[str, Any],
    transport: httpx.BaseTransport | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    with httpx.Client(transport=transport, timeout=timeout_seconds, follow_redirects=True) as client:
        response = client.post(
            token_url,
            data=payload,
            headers={
                "Accept": "application/json",
                "User-Agent": "LawCopilot-OAuth/1.0",
            },
        )
    if response.status_code >= 400:
        raise ValueError(f"oauth_token_exchange_failed:{response.status_code}")
    try:
        raw_payload = response.json()
    except ValueError as exc:
        raise ValueError("oauth_token_response_invalid_json") from exc
    return _normalize_token_bundle(raw_payload)


def _normalize_token_bundle(raw_payload: dict[str, Any]) -> dict[str, Any]:
    issued_at = datetime.now(timezone.utc)
    expires_in = raw_payload.get("expires_in")
    expires_at = raw_payload.get("expires_at")
    if expires_at:
        normalized_expires_at = str(expires_at)
    elif expires_in not in {None, ""}:
        try:
            normalized_expires_at = (issued_at + timedelta(seconds=int(expires_in))).isoformat()
        except (TypeError, ValueError):
            normalized_expires_at = None
    else:
        normalized_expires_at = None
    scope_value = raw_payload.get("scope") or raw_payload.get("scopes") or []
    if isinstance(scope_value, str):
        scope_list = [item for item in scope_value.replace(",", " ").split(" ") if item]
    elif isinstance(scope_value, list):
        scope_list = [str(item) for item in scope_value if str(item).strip()]
    else:
        scope_list = []
    return {
        "access_token": str(raw_payload.get("access_token") or ""),
        "refresh_token": str(raw_payload.get("refresh_token") or ""),
        "token_type": str(raw_payload.get("token_type") or "Bearer"),
        "scope": scope_list,
        "expires_at": normalized_expires_at,
        "issued_at": issued_at.isoformat(),
        "raw": raw_payload,
    }


def _oauth_field_name(spec: ConnectorSpec, field: str, default: str) -> str:
    mapping = dict(spec.auth_config.token_field_map or {})
    candidate = str(mapping.get(field) or "").strip()
    return candidate or default
