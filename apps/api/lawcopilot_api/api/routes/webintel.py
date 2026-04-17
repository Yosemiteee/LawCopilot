from __future__ import annotations

from fastapi import APIRouter, Header

from ...auth import require_role
from ...schemas import WebIntelExtractRequest
from .common import build_authorizer


def create_webintel_router(*, settings, store, web_intel) -> APIRouter:
    router = APIRouter()
    authorize = build_authorizer(jwt_secret=settings.jwt_secret, allow_header_auth=settings.allow_header_auth, store=store)

    @router.post("/web/intel/extract")
    def extract_web_intel(
        payload: WebIntelExtractRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        render_mode = payload.strategy or payload.render_mode
        if not payload.allow_browser:
            render_mode = "cheap"
        result = web_intel.extract(
            url=payload.url,
            render_mode=render_mode,
            include_screenshot=payload.include_screenshot,
        )
        return result

    return router
