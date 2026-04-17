from __future__ import annotations

from fastapi import APIRouter, Header

from ...auth import require_role
from ...schemas import VideoAnalyzeRequest
from ...videointel import analyze_video_url
from .common import build_authorizer


def create_video_router(*, settings, store) -> APIRouter:
    router = APIRouter()
    authorize = build_authorizer(jwt_secret=settings.jwt_secret, allow_header_auth=settings.allow_header_auth, store=store)

    @router.post("/videos/analyze")
    def analyze_video(
        payload: VideoAnalyzeRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        return analyze_video_url(
            payload.url,
            transcript_text=payload.transcript_text,
            max_segments=payload.max_segments,
        )

    return router
