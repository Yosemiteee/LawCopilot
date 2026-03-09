from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from fastapi import HTTPException


ROLE_ORDER = {"intern": 1, "lawyer": 2, "admin": 3}


@dataclass
class AuthContext:
    sub: str
    role: str
    exp: int
    sid: str


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    data += "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data.encode())


def issue_token(secret: str, subject: str, role: str, ttl_seconds: int) -> tuple[str, int, str]:
    if role not in ROLE_ORDER:
        raise ValueError("invalid_role")
    now = int(time.time())
    sid = uuid.uuid4().hex
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": subject, "role": role, "iat": now, "exp": now + ttl_seconds, "sid": sid}
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}", payload["exp"], sid


def parse_token(secret: str, token: str) -> AuthContext:
    try:
        h, p, s = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid_token_format") from exc

    try:
        header = json.loads(_b64url_decode(h).decode())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="invalid_token_header") from exc
    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise HTTPException(status_code=401, detail="invalid_token_header")

    expected = _b64url_encode(hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, s):
        raise HTTPException(status_code=401, detail="invalid_token_signature")

    try:
        payload = json.loads(_b64url_decode(p).decode())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="invalid_token_payload") from exc

    role = payload.get("role", "")
    exp = int(payload.get("exp", 0))
    sid = str(payload.get("sid", ""))
    if role not in ROLE_ORDER:
        raise HTTPException(status_code=401, detail="invalid_token_role")
    if exp < int(time.time()):
        raise HTTPException(status_code=401, detail="token_expired")
    if not sid:
        raise HTTPException(status_code=401, detail="invalid_token_session")
    return AuthContext(sub=str(payload.get("sub", "unknown")), role=role, exp=exp, sid=sid)


def require_role(min_role: str, role: str) -> str:
    if ROLE_ORDER.get(role, 0) < ROLE_ORDER.get(min_role, 999):
        raise HTTPException(status_code=403, detail="insufficient_role")
    return role
