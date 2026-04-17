from __future__ import annotations

from typing import Callable

from fastapi import HTTPException

from ...auth import parse_token


def build_authorizer(*, jwt_secret: str, allow_header_auth: bool, store) -> Callable[[str | None, str | None], tuple[str, str, str]]:
    def authorize(x_role: str | None, authorization: str | None) -> tuple[str, str, str]:
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            ctx = parse_token(jwt_secret, token)
            if not store.is_session_active(ctx.sid):
                raise HTTPException(status_code=401, detail="session_revoked")
            return ctx.sub, ctx.role, ctx.sid

        if not allow_header_auth:
            raise HTTPException(status_code=401, detail="missing_bearer_token")

        requested = (x_role or "intern").lower()
        role = "intern" if requested not in {"intern"} else requested
        return "header-user", role, "header-session"

    return authorize
