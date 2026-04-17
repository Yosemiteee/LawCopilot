from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from ...auth import require_role
from ...schemas import AgentRunCreateRequest, AgentRunDecisionRequest
from .common import build_authorizer


def create_agent_router(*, settings, store, agent_runtime) -> APIRouter:
    router = APIRouter()
    authorize = build_authorizer(jwt_secret=settings.jwt_secret, allow_header_auth=settings.allow_header_auth, store=store)

    @router.post("/agent/runs")
    def create_agent_run(
        payload: AgentRunCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        if payload.matter_id and not store.get_matter(int(payload.matter_id), settings.office_id):
            raise HTTPException(status_code=404, detail="matter_not_found")
        if payload.thread_id:
            thread = store.get_assistant_thread(settings.office_id, int(payload.thread_id))
            if not thread:
                raise HTTPException(status_code=404, detail="assistant_thread_not_found")
        return agent_runtime.create_run(
            goal=payload.goal,
            created_by=subject,
            title=payload.title,
            matter_id=payload.matter_id,
            thread_id=payload.thread_id,
            source_kind=payload.source_kind,
            run_type=payload.mode or payload.run_type,
            preferred_tools=payload.preferred_tools,
            source_refs=payload.source_refs,
            render_mode=payload.strategy or payload.render_mode,
            allow_browser=payload.allow_browser,
        )

    @router.get("/agent/runs")
    def list_agent_runs(
        limit: int = 8,
        thread_id: int | None = None,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        return {"items": agent_runtime.list_run_views(limit=limit, thread_id=thread_id)}

    @router.get("/agent/runs/{run_id}")
    def get_agent_run(
        run_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        run = agent_runtime.get_run_view(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="agent_run_not_found")
        return run

    @router.get("/agent/runs/{run_id}/events")
    def get_agent_run_events(
        run_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        run = agent_runtime.get_run_view(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="agent_run_not_found")
        return {"items": agent_runtime.get_run_events(run_id), "run": run}

    @router.post("/agent/runs/{run_id}/approve")
    def approve_agent_run(
        run_id: int,
        payload: AgentRunDecisionRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        _ = payload
        result = agent_runtime.approve_run(run_id, decided_by=subject)
        if not result:
            raise HTTPException(status_code=404, detail="agent_run_not_found")
        return {"run": result}

    @router.post("/agent/runs/{run_id}/cancel")
    def cancel_agent_run(
        run_id: int,
        payload: AgentRunDecisionRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        _ = payload
        result = agent_runtime.cancel_run(run_id, decided_by=subject)
        if not result:
            raise HTTPException(status_code=404, detail="agent_run_not_found")
        return {"run": result}

    return router
