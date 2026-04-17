from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class IntegrationUiOption(BaseModel):
    value: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=240)


class IntegrationUiField(BaseModel):
    key: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]{1,79}$")
    label: str = Field(min_length=1, max_length=160)
    kind: str = Field(pattern=r"^(text|password|url|textarea|select|boolean|number)$")
    target: str = Field(default="config", pattern=r"^(config|secret)$")
    required: bool = False
    secret: bool = False
    placeholder: str = Field(default="", max_length=240)
    help_text: str = Field(default="", max_length=500)
    default: Any = None
    options: list[IntegrationUiOption] = Field(default_factory=list, max_length=24)


class IntegrationPermissionPreset(BaseModel):
    level: str = Field(pattern=r"^(read_only|read_write|admin_like)$")
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=320)
    allowed_operations: list[str] = Field(default_factory=list, max_length=20)


class IntegrationAuthConfig(BaseModel):
    client_configurable: bool = False
    supports_refresh: bool = False
    authorization_url: str | None = Field(default=None, max_length=400)
    token_url: str | None = Field(default=None, max_length=400)
    revocation_url: str | None = Field(default=None, max_length=400)
    documentation_url: str | None = Field(default=None, max_length=400)
    default_scopes: list[str] = Field(default_factory=list, max_length=40)
    scope_separator: str = Field(default=" ", max_length=8)
    pkce_required: bool = False
    token_field_map: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list, max_length=12)


class IntegrationResourceSpec(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=400)
    item_types: list[str] = Field(default_factory=list, max_length=12)
    supports_search: bool = False


class IntegrationActionSpec(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=400)
    operation: str = Field(
        pattern=(
            r"^(list_items|get_item|search|create|update|delete|send_message|read_messages|create_page|append_block|"
            r"list_databases|run_query|run_sql|insert_record|update_record|fetch_documents|upload_file|download_file)$"
        )
    )
    access: str = Field(default="read", pattern=r"^(read|write|delete|admin)$")
    approval_required: bool = False
    input_schema: dict[str, Any] = Field(default_factory=dict)
    method: str | None = Field(default=None, pattern=r"^(GET|POST|PUT|PATCH|DELETE)$")
    path: str | None = Field(default=None, max_length=400)
    response_items_path: str | None = Field(default=None, max_length=160)
    response_item_path: str | None = Field(default=None, max_length=160)
    cursor_path: str | None = Field(default=None, max_length=160)
    query_map: dict[str, str] = Field(default_factory=dict)


class IntegrationTriggerSpec(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=320)
    event_types: list[str] = Field(default_factory=list, max_length=20)


class IntegrationSyncPolicy(BaseModel):
    mode: str = Field(pattern=r"^(incremental|full|manual|webhook)$")
    default_strategy: str = Field(min_length=1, max_length=120)
    cursor_field: str | None = Field(default=None, max_length=120)
    schedule_hint_minutes: int | None = Field(default=None, ge=1, le=1440)


class IntegrationPaginationStrategy(BaseModel):
    type: str = Field(pattern=r"^(cursor|page|offset|none)$")
    cursor_param: str | None = Field(default=None, max_length=120)
    page_param: str | None = Field(default=None, max_length=120)
    page_size_param: str | None = Field(default=None, max_length=120)
    items_path: str | None = Field(default=None, max_length=160)


class IntegrationWebhookSupport(BaseModel):
    supported: bool = False
    signature_header: str | None = Field(default=None, max_length=120)
    events: list[str] = Field(default_factory=list, max_length=20)
    secret_required: bool = False


class IntegrationRateLimit(BaseModel):
    strategy: str = Field(default="unknown", pattern=r"^(header|fixed-window|unknown)$")
    requests_per_minute: int | None = Field(default=None, ge=1, le=100000)
    burst_limit: int | None = Field(default=None, ge=1, le=100000)
    retry_after_header: str | None = Field(default=None, max_length=120)


class ConnectorSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=600)
    category: str = Field(min_length=1, max_length=80)
    auth_type: str = Field(min_length=1, max_length=40)
    auth_config: IntegrationAuthConfig = Field(default_factory=IntegrationAuthConfig)
    scopes: list[str] = Field(default_factory=list, max_length=40)
    base_url: str | None = Field(default=None, max_length=400)
    resources: list[IntegrationResourceSpec] = Field(default_factory=list, max_length=20)
    actions: list[IntegrationActionSpec] = Field(default_factory=list, max_length=32)
    triggers: list[IntegrationTriggerSpec] = Field(default_factory=list, max_length=20)
    sync_policies: list[IntegrationSyncPolicy] = Field(default_factory=list, max_length=12)
    pagination_strategy: IntegrationPaginationStrategy = Field(default_factory=lambda: IntegrationPaginationStrategy(type="none"))
    webhook_support: IntegrationWebhookSupport = Field(default_factory=IntegrationWebhookSupport)
    rate_limit: IntegrationRateLimit = Field(default_factory=IntegrationRateLimit)
    ui_schema: list[IntegrationUiField] = Field(default_factory=list, max_length=32)
    permissions: list[IntegrationPermissionPreset] = Field(default_factory=list, max_length=8)
    capability_flags: dict[str, bool] = Field(default_factory=dict)
    management_mode: str = Field(default="platform", pattern=r"^(platform|legacy-desktop)$")
    default_access_level: str = Field(default="read_only", pattern=r"^(read_only|read_write|admin_like)$")
    tags: list[str] = Field(default_factory=list, max_length=20)
    docs_url: str | None = Field(default=None, max_length=400)
    setup_hint: str = Field(default="", max_length=320)


class IntegrationConnectionPayload(BaseModel):
    connector_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    connection_id: int | None = Field(default=None, gt=0)
    display_name: str | None = Field(default=None, max_length=120)
    access_level: str = Field(default="read_only", pattern=r"^(read_only|read_write|admin_like)$")
    enabled: bool = True
    mock_mode: bool = False
    scopes: list[str] = Field(default_factory=list, max_length=50)
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)

    @field_validator("display_name")
    @classmethod
    def _normalize_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(str(value or "").split()).strip()
        return cleaned or None


class IntegrationActionRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class IntegrationOAuthStartRequest(BaseModel):
    redirect_uri: str | None = Field(default=None, max_length=400)
    requested_scopes: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("redirect_uri")
    @classmethod
    def _strip_redirect(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class IntegrationOAuthCallbackRequest(BaseModel):
    state: str = Field(min_length=8, max_length=240)
    code: str | None = Field(default=None, max_length=2000)
    error: str | None = Field(default=None, max_length=2000)

    @field_validator("state", "code", "error")
    @classmethod
    def _strip_callback_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class IntegrationSyncScheduleRequest(BaseModel):
    mode: str = Field(default="incremental", pattern=r"^(incremental|full|manual|webhook)$")
    trigger_type: str = Field(default="manual", pattern=r"^(manual|scheduled|webhook|retry|system)$")
    run_now: bool = True
    force: bool = False


class IntegrationJobDispatchRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=50)


class IntegrationSafetySettingsRequest(BaseModel):
    read_enabled: bool | None = None
    write_enabled: bool | None = None
    delete_enabled: bool | None = None
    require_confirmation_for_write: bool | None = None
    require_confirmation_for_delete: bool | None = None


class IntegrationAutomationRequest(BaseModel):
    prompt: str = Field(min_length=4, max_length=4000)
    docs_url: str | None = Field(default=None, max_length=400)
    openapi_url: str | None = Field(default=None, max_length=400)
    openapi_spec: str | None = Field(default=None, max_length=200000)
    documentation_excerpt: str | None = Field(default=None, max_length=200000)
    category: str | None = Field(default=None, max_length=80)
    preferred_auth_type: str | None = Field(default=None, max_length=40)

    @field_validator(
        "prompt",
        "docs_url",
        "openapi_url",
        "openapi_spec",
        "documentation_excerpt",
        "category",
        "preferred_auth_type",
    )
    @classmethod
    def _strip_request_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class IntegrationGeneratedConnectorReviewRequest(BaseModel):
    decision: str = Field(pattern=r"^(approve|reject|archive|restore)$")
    notes: str | None = Field(default=None, max_length=2000)
    live_use_enabled: bool | None = None

    @field_validator("notes")
    @classmethod
    def _strip_review_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class IntegrationGeneratedConnectorRefreshRequest(BaseModel):
    docs_url: str | None = Field(default=None, max_length=400)
    openapi_url: str | None = Field(default=None, max_length=400)
    openapi_spec: str | None = Field(default=None, max_length=200000)
    documentation_excerpt: str | None = Field(default=None, max_length=200000)
    category: str | None = Field(default=None, max_length=80)
    preferred_auth_type: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator(
        "docs_url",
        "openapi_url",
        "openapi_spec",
        "documentation_excerpt",
        "category",
        "preferred_auth_type",
        "notes",
    )
    @classmethod
    def _strip_refresh_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class IntegrationGeneratedConnectorStateRequest(BaseModel):
    enabled: bool
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("notes")
    @classmethod
    def _strip_state_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class IntegrationScaffoldRequest(BaseModel):
    service_name: str = Field(min_length=2, max_length=120)
    docs_url: str | None = Field(default=None, max_length=400)
    openapi_url: str | None = Field(default=None, max_length=400)
    openapi_spec: str | None = Field(default=None, max_length=200000)
    documentation_excerpt: str | None = Field(default=None, max_length=200000)
    category: str | None = Field(default=None, max_length=80)
    preferred_auth_type: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator(
        "service_name",
        "docs_url",
        "openapi_url",
        "openapi_spec",
        "documentation_excerpt",
        "category",
        "preferred_auth_type",
        "notes",
    )
    @classmethod
    def _strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None
