from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from ...auth import require_role
from ...integrations.models import (
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
from .common import build_authorizer


def create_integrations_router(*, settings, store, integration_service, knowledge_base=None) -> APIRouter:
    router = APIRouter()
    authorize = build_authorizer(jwt_secret=settings.jwt_secret, allow_header_auth=settings.allow_header_auth, store=store)

    @router.get("/integrations/catalog")
    def list_integration_catalog(
        query: str | None = None,
        category: str | None = None,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        return integration_service.list_catalog(query=query, category=category)

    @router.get("/integrations/connections")
    def list_connections(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        return integration_service.list_connections()

    @router.post("/integrations/assistant-setups/{setup_id}/desktop/prepare")
    def prepare_assistant_setup_for_desktop(
        setup_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.prepare_assistant_setup_for_desktop(setup_id, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.get("/integrations/events")
    def list_integration_events(
        connection_id: int | None = None,
        limit: int = 20,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        return integration_service.list_events(connection_id=connection_id, limit=limit)

    @router.get("/integrations/worker")
    def integration_worker_status(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        return integration_service.worker_status()

    @router.get("/integrations/ops/summary")
    def integration_launch_ops_summary(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        return integration_service.launch_ops_summary()

    @router.get("/integrations/requests")
    def list_generated_integration_requests(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        return integration_service.list_generated_requests()

    @router.get("/integrations/patterns")
    def list_connector_patterns(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        return integration_service.list_connector_patterns()

    @router.get("/integrations/connections/{connection_id}")
    def get_connection_detail(
        connection_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("intern", role)
        try:
            return integration_service.get_connection_detail(connection_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/integrations/connections/preview")
    def preview_connection(
        payload: IntegrationConnectionPayload,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.preview_connection(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/integrations/connections")
    def save_connection(
        payload: IntegrationConnectionPayload,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.save_connection(payload, actor=subject)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/integrations/connections/{connection_id}/oauth/start")
    def start_oauth_authorization(
        connection_id: int,
        payload: IntegrationOAuthStartRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.start_oauth_authorization(connection_id, payload, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/oauth/callback")
    def complete_oauth_callback(
        payload: IntegrationOAuthCallbackRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.complete_oauth_callback(payload, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/connections/{connection_id}/refresh")
    def refresh_connection_credentials(
        connection_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.refresh_connection_credentials(connection_id, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/connections/{connection_id}/revoke")
    def revoke_connection(
        connection_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.revoke_connection(connection_id, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/connections/{connection_id}/reconnect")
    def reconnect_connection(
        connection_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.reconnect_connection(connection_id, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/connections/{connection_id}/validate")
    def validate_connection(
        connection_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.validate_connection(connection_id)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/connections/{connection_id}/health")
    def health_check_connection(
        connection_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.health_check_connection(connection_id, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/connections/{connection_id}/sync")
    def sync_connection(
        connection_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            response = integration_service.sync_connection(connection_id, actor=subject)
            if knowledge_base is not None and str(response.get("connection", {}).get("connector_id") or "") == "elastic":
                knowledge_base.run_connector_sync(
                    store=store,
                    reason=f"integration_sync:elastic:{connection_id}",
                    connector_names=["elastic_managed_resources"],
                    trigger="integration_sync",
                )
            return response
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/connections/{connection_id}/sync/schedule")
    def schedule_sync_connection(
        connection_id: int,
        payload: IntegrationSyncScheduleRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.schedule_sync(connection_id, payload, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/sync/dispatch")
    def dispatch_sync_jobs(
        payload: IntegrationJobDispatchRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        return integration_service.dispatch_sync_jobs(payload, actor=subject)

    @router.delete("/integrations/connections/{connection_id}")
    def disconnect_connection(
        connection_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.disconnect_connection(connection_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/integrations/connections/{connection_id}/actions/{action_key}")
    def execute_action(
        connection_id: int,
        action_key: str,
        payload: IntegrationActionRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.execute_action(connection_id, action_key, payload, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/connections/{connection_id}/safety")
    def update_safety_settings(
        connection_id: int,
        payload: IntegrationSafetySettingsRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.update_safety_settings(connection_id, payload, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/scaffold")
    def generate_scaffold(
        payload: IntegrationScaffoldRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        _, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        return integration_service.generate_scaffold(payload)

    @router.post("/integrations/requests")
    def create_generated_integration_request(
        payload: IntegrationAutomationRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.create_integration_request(payload, actor=subject)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/integrations/requests/{connector_id}/review")
    def review_generated_integration_request(
        connector_id: str,
        payload: IntegrationGeneratedConnectorReviewRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.review_generated_connector(connector_id, payload, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/requests/{connector_id}/refresh")
    def refresh_generated_integration_request(
        connector_id: str,
        payload: IntegrationGeneratedConnectorRefreshRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.refresh_generated_connector(connector_id, payload, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/requests/{connector_id}/state")
    def update_generated_integration_request_state(
        connector_id: str,
        payload: IntegrationGeneratedConnectorStateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.set_generated_connector_enabled(connector_id, payload, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.delete("/integrations/requests/{connector_id}")
    def delete_generated_integration_request(
        connector_id: str,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ):
        subject, role, _ = authorize(x_role, authorization)
        require_role("lawyer", role)
        try:
            return integration_service.delete_generated_connector(connector_id, actor=subject)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @router.post("/integrations/webhooks/{connector_id}")
    async def ingest_integration_webhook(
        connector_id: str,
        request: Request,
    ):
        try:
            payload = await request.body()
            result = integration_service.ingest_webhook(connector_id, headers=dict(request.headers), body=payload)
            response_payload = dict(result.get("response") or {"ok": True})
            return JSONResponse(content=response_payload)
        except ValueError as exc:
            status = 404 if "not_found" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    return router
