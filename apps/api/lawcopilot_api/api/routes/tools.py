from __future__ import annotations

from fastapi import APIRouter, Header

from ...auth import require_role
from .common import build_authorizer


def create_tools_router(*, settings, store, tool_registry) -> APIRouter:
    router = APIRouter()
    authorize = build_authorizer(jwt_secret=settings.jwt_secret, allow_header_auth=settings.allow_header_auth, store=store)

    @router.get("/tools")
    def list_tools(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        return {"items": tool_registry.list_tools(), "generated_from": "typed_tool_registry"}

    return router
