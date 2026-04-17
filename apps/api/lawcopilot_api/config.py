from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ALLOWED_DEPLOYMENT_MODES = ("local-only", "cloud-assisted", "local-first-hybrid")


@dataclass(frozen=True)
class Settings:
    app_name: str = "LawCopilot"
    app_version: str = "0.7.0-pilot.2"
    office_id: str = "default-office"
    deployment_mode: str = "local-only"
    release_channel: str = "pilot"
    environment: str = "pilot"
    desktop_shell: str = "electron"
    jwt_secret: str = "dev-change-me"
    token_ttl_seconds: int = 3600
    bootstrap_admin_key: str = ""
    allow_local_token_bootstrap: bool = False
    model_profiles_path: str = "configs/model-profiles.json"
    default_model_profile: str = "cloud"
    audit_log_path: str = "artifacts/audit.log.jsonl"
    structured_log_path: str = "artifacts/events.log.jsonl"
    desktop_main_log_path: str = ""
    desktop_backend_log_path: str = ""
    db_path: str = "artifacts/lawcopilot.db"
    connector_allow_domains: tuple[str, ...] = ("example.com", "baro.org.tr")
    connector_dry_run: bool = True
    connector_http_timeout_seconds: int = 20
    connector_http_max_retries: int = 2
    connector_http_backoff_max_seconds: float = 4.0
    connector_sync_max_pages: int = 5
    integration_worker_enabled: bool = True
    integration_worker_poll_seconds: int = 15
    integration_worker_batch_size: int = 5
    integration_worker_lock_timeout_seconds: int = 300
    integration_webhook_replay_window_seconds: int = 300
    integration_assistant_setup_timeout_minutes: int = 720
    integration_secret_key_id: str = "default"
    integration_secret_previous_keys: tuple[str, ...] = ()
    max_ingest_bytes: int = 5 * 1024 * 1024
    allow_header_auth: bool = False
    expose_security_flags: bool = False
    rag_backend: str = "inmemory"
    rag_tenant_id: str = "default"
    provider_type: str = ""
    provider_base_url: str = ""
    provider_model: str = ""
    provider_api_key: str = ""
    provider_configured: bool = False
    openclaw_state_dir: str = ""
    openclaw_async_sync_enabled: bool = True
    openclaw_image: str = "openclaw-local:chromium"
    openclaw_timeout_seconds: int = 75
    google_enabled: bool = False
    google_configured: bool = False
    google_account_label: str = ""
    google_scopes: tuple[str, ...] = ()
    google_client_id_configured: bool = False
    google_client_secret_configured: bool = False
    gmail_connected: bool = False
    calendar_connected: bool = False
    drive_connected: bool = False
    outlook_enabled: bool = False
    outlook_configured: bool = False
    outlook_account_label: str = ""
    outlook_scopes: tuple[str, ...] = ()
    outlook_mail_connected: bool = False
    outlook_calendar_connected: bool = False
    telegram_enabled: bool = False
    telegram_configured: bool = False
    telegram_mode: str = "bot"
    telegram_account_label: str = ""
    telegram_bot_username: str = ""
    telegram_allowed_user_id: str = ""
    whatsapp_enabled: bool = False
    whatsapp_configured: bool = False
    whatsapp_account_label: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_display_phone_number: str = ""
    x_enabled: bool = False
    x_configured: bool = False
    x_account_label: str = ""
    x_user_id: str = ""
    x_scopes: tuple[str, ...] = ()
    x_validation_status: str = "pending"
    x_last_error: str = ""
    instagram_enabled: bool = False
    instagram_configured: bool = False
    instagram_account_label: str = ""
    instagram_page_id: str = ""
    instagram_account_id: str = ""
    instagram_username: str = ""
    instagram_scopes: tuple[str, ...] = ()
    linkedin_enabled: bool = False
    linkedin_configured: bool = False
    linkedin_mode: str = "official"
    linkedin_account_label: str = ""
    linkedin_user_id: str = ""
    linkedin_person_urn: str = ""
    linkedin_scopes: tuple[str, ...] = ()
    browser_worker_enabled: bool = True
    browser_worker_command: str = ""
    browser_profile_dir: str = "artifacts/browser/profile"
    browser_artifacts_dir: str = "artifacts/browser/artifacts"
    browser_downloads_dir: str = "artifacts/browser/downloads"
    browser_allowed_domains: tuple[str, ...] = ()
    browser_worker_timeout_seconds: int = 45
    fastapi_lifespan_enabled: bool = True
    personal_kb_enabled: bool = True
    personal_kb_root: str = "artifacts/runtime/personal-kb"
    personal_kb_excluded_patterns: tuple[str, ...] = ()
    personal_kb_search_backend: str = "sqlite_hybrid_fts_v1"
    personal_kb_dense_candidates_enabled: bool = False
    personal_kb_semantic_backend: str = "heuristic"
    personal_kb_embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    personal_kb_cross_encoder_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    personal_kb_reranker_mode: str = "local_heuristic"
    personal_kb_recommendation_cooldown_minutes: int = 180
    personal_kb_scheduler_enabled: bool = False
    personal_kb_startup_bootstrap_enabled: bool = True
    personal_kb_scheduler_poll_seconds: int = 60
    personal_kb_scheduler_trigger_interval_seconds: int = 300
    personal_kb_scheduler_reflection_interval_seconds: int = 900
    personal_kb_scheduler_connector_sync_interval_seconds: int = 600
    personal_kb_llm_article_authoring_enabled: bool = True
    personal_kb_llm_article_limit: int = 4
    runtime_job_worker_mode: str = "inline"
    runtime_job_subprocess_timeout_seconds: int = 180
    location_provider_mode: str = "desktop_file_fallback"
    location_snapshot_path: str = "artifacts/runtime/location/context.json"
    google_maps_embed_api_key: str = ""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return _repo_root()


def _normalized_deployment_mode(value: str) -> str:
    normalized = (value or "local-only").strip().lower()
    if normalized in {"hybrid", "local-first", "local-first-hybrid"}:
        return "local-first-hybrid"
    if normalized in {"local", "local-only"}:
        return "local-only"
    if normalized in {"cloud", "cloud-assisted"}:
        return "cloud-assisted"
    return "local-only"


def get_settings() -> Settings:
    active_environment = str(os.getenv("LAWCOPILOT_ENVIRONMENT", "pilot") or "pilot").strip().lower()
    running_under_pytest = bool(str(os.getenv("PYTEST_CURRENT_TEST", "")).strip()) or "pytest" in sys.modules
    default_allow_local_token_bootstrap = "true" if running_under_pytest or active_environment in {"dev", "development", "test"} else "false"
    domains = tuple(
        d.strip().lower() for d in os.getenv("LAWCOPILOT_CONNECTOR_ALLOW_DOMAINS", "example.com,baro.org.tr").split(",") if d.strip()
    )
    browser_domains = tuple(
        d.strip().lower() for d in os.getenv("LAWCOPILOT_BROWSER_ALLOWED_DOMAINS", "").split(",") if d.strip()
    )
    personal_kb_excluded_patterns = tuple(
        pattern.strip()
        for pattern in os.getenv("LAWCOPILOT_PERSONAL_KB_EXCLUDED_PATTERNS", "").split(",")
        if pattern.strip()
    )
    return Settings(
        app_name=os.getenv("LAWCOPILOT_APP_NAME", "LawCopilot"),
        app_version=os.getenv("LAWCOPILOT_APP_VERSION", "0.7.0-pilot.2"),
        office_id=os.getenv("LAWCOPILOT_OFFICE_ID", "default-office"),
        deployment_mode=_normalized_deployment_mode(os.getenv("LAWCOPILOT_DEPLOYMENT_MODE", "local-only")),
        release_channel=os.getenv("LAWCOPILOT_RELEASE_CHANNEL", "pilot"),
        environment=os.getenv("LAWCOPILOT_ENVIRONMENT", "pilot"),
        desktop_shell=os.getenv("LAWCOPILOT_DESKTOP_SHELL", "electron"),
        jwt_secret=os.getenv("LAWCOPILOT_JWT_SECRET", "dev-change-me"),
        token_ttl_seconds=int(os.getenv("LAWCOPILOT_TOKEN_TTL", "3600")),
        bootstrap_admin_key=os.getenv("LAWCOPILOT_BOOTSTRAP_ADMIN_KEY", ""),
        allow_local_token_bootstrap=os.getenv(
            "LAWCOPILOT_ALLOW_LOCAL_TOKEN_BOOTSTRAP",
            default_allow_local_token_bootstrap,
        ).lower() == "true",
        model_profiles_path=os.getenv("LAWCOPILOT_MODEL_PROFILES", "configs/model-profiles.json"),
        default_model_profile=os.getenv("LAWCOPILOT_DEFAULT_MODEL_PROFILE", "cloud"),
        audit_log_path=os.getenv("LAWCOPILOT_AUDIT_LOG", "artifacts/audit.log.jsonl"),
        structured_log_path=os.getenv("LAWCOPILOT_STRUCTURED_LOG", "artifacts/events.log.jsonl"),
        desktop_main_log_path=os.getenv("LAWCOPILOT_DESKTOP_MAIN_LOG", ""),
        desktop_backend_log_path=os.getenv("LAWCOPILOT_DESKTOP_BACKEND_LOG", ""),
        db_path=os.getenv("LAWCOPILOT_DB_PATH", "artifacts/lawcopilot.db"),
        connector_allow_domains=domains,
        connector_dry_run=os.getenv("LAWCOPILOT_CONNECTOR_DRY_RUN", "true").lower() != "false",
        connector_http_timeout_seconds=int(os.getenv("LAWCOPILOT_CONNECTOR_HTTP_TIMEOUT", "20")),
        connector_http_max_retries=int(os.getenv("LAWCOPILOT_CONNECTOR_HTTP_MAX_RETRIES", "2")),
        connector_http_backoff_max_seconds=float(os.getenv("LAWCOPILOT_CONNECTOR_HTTP_BACKOFF_MAX_SECONDS", "4")),
        connector_sync_max_pages=int(os.getenv("LAWCOPILOT_CONNECTOR_SYNC_MAX_PAGES", "5")),
        integration_worker_enabled=os.getenv(
            "LAWCOPILOT_INTEGRATION_WORKER_ENABLED",
            "false" if running_under_pytest else "true",
        ).lower()
        != "false",
        integration_worker_poll_seconds=int(os.getenv("LAWCOPILOT_INTEGRATION_WORKER_POLL_SECONDS", "15")),
        integration_worker_batch_size=int(os.getenv("LAWCOPILOT_INTEGRATION_WORKER_BATCH_SIZE", "5")),
        integration_worker_lock_timeout_seconds=int(os.getenv("LAWCOPILOT_INTEGRATION_WORKER_LOCK_TIMEOUT_SECONDS", "300")),
        integration_webhook_replay_window_seconds=int(os.getenv("LAWCOPILOT_INTEGRATION_WEBHOOK_REPLAY_WINDOW_SECONDS", "300")),
        integration_assistant_setup_timeout_minutes=int(os.getenv("LAWCOPILOT_INTEGRATION_ASSISTANT_SETUP_TIMEOUT_MINUTES", "720")),
        integration_secret_key_id=os.getenv("LAWCOPILOT_INTEGRATION_SECRET_KEY_ID", "default").strip() or "default",
        integration_secret_previous_keys=tuple(
            item.strip()
            for item in os.getenv("LAWCOPILOT_INTEGRATION_SECRET_PREVIOUS_KEYS", "").replace("\n", ",").split(",")
            if item.strip()
        ),
        max_ingest_bytes=int(os.getenv("LAWCOPILOT_MAX_INGEST_BYTES", str(5 * 1024 * 1024))),
        allow_header_auth=os.getenv("LAWCOPILOT_ALLOW_HEADER_AUTH", "false").lower() == "true",
        expose_security_flags=os.getenv("LAWCOPILOT_EXPOSE_SECURITY_FLAGS", "false").lower() == "true",
        rag_backend=os.getenv("LAWCOPILOT_RAG_BACKEND", "inmemory"),
        rag_tenant_id=os.getenv("LAWCOPILOT_RAG_TENANT_ID", "default"),
        provider_type=os.getenv("LAWCOPILOT_PROVIDER_TYPE", ""),
        provider_base_url=os.getenv("LAWCOPILOT_PROVIDER_BASE_URL", ""),
        provider_model=os.getenv("LAWCOPILOT_PROVIDER_MODEL", ""),
        provider_api_key=os.getenv("LAWCOPILOT_PROVIDER_API_KEY", ""),
        provider_configured=os.getenv("LAWCOPILOT_PROVIDER_CONFIGURED", "false").lower() == "true",
        openclaw_state_dir=os.getenv("LAWCOPILOT_OPENCLAW_STATE_DIR", ""),
        openclaw_async_sync_enabled=os.getenv("LAWCOPILOT_OPENCLAW_ASYNC_SYNC_ENABLED", "true").lower() == "true",
        openclaw_image=os.getenv("LAWCOPILOT_OPENCLAW_IMAGE", "openclaw-local:chromium"),
        openclaw_timeout_seconds=int(os.getenv("LAWCOPILOT_OPENCLAW_TIMEOUT", "75")),
        google_enabled=os.getenv("LAWCOPILOT_GOOGLE_ENABLED", "false").lower() == "true",
        google_configured=os.getenv("LAWCOPILOT_GOOGLE_CONFIGURED", "false").lower() == "true",
        google_account_label=os.getenv("LAWCOPILOT_GOOGLE_ACCOUNT_LABEL", ""),
        google_scopes=tuple(
            scope.strip()
            for scope in os.getenv("LAWCOPILOT_GOOGLE_SCOPES", "").split(",")
            if scope.strip()
        ),
        google_client_id_configured=os.getenv("LAWCOPILOT_GOOGLE_CLIENT_ID_CONFIGURED", "false").lower() == "true",
        google_client_secret_configured=os.getenv("LAWCOPILOT_GOOGLE_CLIENT_SECRET_CONFIGURED", "false").lower() == "true",
        gmail_connected=os.getenv("LAWCOPILOT_GMAIL_CONNECTED", "false").lower() == "true",
        calendar_connected=os.getenv("LAWCOPILOT_CALENDAR_CONNECTED", "false").lower() == "true",
        drive_connected=os.getenv("LAWCOPILOT_DRIVE_CONNECTED", "false").lower() == "true",
        outlook_enabled=os.getenv("LAWCOPILOT_OUTLOOK_ENABLED", "false").lower() == "true",
        outlook_configured=os.getenv("LAWCOPILOT_OUTLOOK_CONFIGURED", "false").lower() == "true",
        outlook_account_label=os.getenv("LAWCOPILOT_OUTLOOK_ACCOUNT_LABEL", ""),
        outlook_scopes=tuple(
            scope.strip()
            for scope in os.getenv("LAWCOPILOT_OUTLOOK_SCOPES", "").split(",")
            if scope.strip()
        ),
        outlook_mail_connected=os.getenv("LAWCOPILOT_OUTLOOK_MAIL_CONNECTED", "false").lower() == "true",
        outlook_calendar_connected=os.getenv("LAWCOPILOT_OUTLOOK_CALENDAR_CONNECTED", "false").lower() == "true",
        telegram_enabled=os.getenv("LAWCOPILOT_TELEGRAM_ENABLED", "false").lower() == "true",
        telegram_configured=os.getenv("LAWCOPILOT_TELEGRAM_CONFIGURED", "false").lower() == "true",
        telegram_mode=os.getenv("LAWCOPILOT_TELEGRAM_MODE", "bot"),
        telegram_account_label=os.getenv("LAWCOPILOT_TELEGRAM_ACCOUNT_LABEL", ""),
        telegram_bot_username=os.getenv("LAWCOPILOT_TELEGRAM_BOT_USERNAME", ""),
        telegram_allowed_user_id=os.getenv("LAWCOPILOT_TELEGRAM_ALLOWED_USER_ID", ""),
        whatsapp_enabled=os.getenv("LAWCOPILOT_WHATSAPP_ENABLED", "false").lower() == "true",
        whatsapp_configured=os.getenv("LAWCOPILOT_WHATSAPP_CONFIGURED", "false").lower() == "true",
        whatsapp_account_label=os.getenv("LAWCOPILOT_WHATSAPP_ACCOUNT_LABEL", ""),
        whatsapp_phone_number_id=os.getenv("LAWCOPILOT_WHATSAPP_PHONE_NUMBER_ID", ""),
        whatsapp_display_phone_number=os.getenv("LAWCOPILOT_WHATSAPP_DISPLAY_PHONE_NUMBER", ""),
        x_enabled=os.getenv("LAWCOPILOT_X_ENABLED", "false").lower() == "true",
        x_configured=os.getenv("LAWCOPILOT_X_CONFIGURED", "false").lower() == "true",
        x_account_label=os.getenv("LAWCOPILOT_X_ACCOUNT_LABEL", ""),
        x_user_id=os.getenv("LAWCOPILOT_X_USER_ID", ""),
        x_scopes=tuple(scope.strip() for scope in os.getenv("LAWCOPILOT_X_SCOPES", "").split(",") if scope.strip()),
        x_validation_status=os.getenv("LAWCOPILOT_X_VALIDATION_STATUS", "pending"),
        x_last_error=os.getenv("LAWCOPILOT_X_LAST_ERROR", ""),
        instagram_enabled=os.getenv("LAWCOPILOT_INSTAGRAM_ENABLED", "false").lower() == "true",
        instagram_configured=os.getenv("LAWCOPILOT_INSTAGRAM_CONFIGURED", "false").lower() == "true",
        instagram_account_label=os.getenv("LAWCOPILOT_INSTAGRAM_ACCOUNT_LABEL", ""),
        instagram_page_id=os.getenv("LAWCOPILOT_INSTAGRAM_PAGE_ID", ""),
        instagram_account_id=os.getenv("LAWCOPILOT_INSTAGRAM_ACCOUNT_ID", ""),
        instagram_username=os.getenv("LAWCOPILOT_INSTAGRAM_USERNAME", ""),
        instagram_scopes=tuple(
            scope.strip() for scope in os.getenv("LAWCOPILOT_INSTAGRAM_SCOPES", "").split(",") if scope.strip()
        ),
        linkedin_enabled=os.getenv("LAWCOPILOT_LINKEDIN_ENABLED", "false").lower() == "true",
        linkedin_configured=os.getenv("LAWCOPILOT_LINKEDIN_CONFIGURED", "false").lower() == "true",
        linkedin_mode=os.getenv("LAWCOPILOT_LINKEDIN_MODE", "official"),
        linkedin_account_label=os.getenv("LAWCOPILOT_LINKEDIN_ACCOUNT_LABEL", ""),
        linkedin_user_id=os.getenv("LAWCOPILOT_LINKEDIN_USER_ID", ""),
        linkedin_person_urn=os.getenv("LAWCOPILOT_LINKEDIN_PERSON_URN", ""),
        linkedin_scopes=tuple(scope.strip() for scope in os.getenv("LAWCOPILOT_LINKEDIN_SCOPES", "").split(",") if scope.strip()),
        browser_worker_enabled=os.getenv(
            "LAWCOPILOT_BROWSER_WORKER_ENABLED",
            "false" if running_under_pytest else "true",
        ).lower()
        == "true",
        browser_worker_command=os.getenv("LAWCOPILOT_BROWSER_WORKER_COMMAND", ""),
        browser_profile_dir=os.getenv("LAWCOPILOT_BROWSER_PROFILE_DIR", "artifacts/browser/profile"),
        browser_artifacts_dir=os.getenv("LAWCOPILOT_BROWSER_ARTIFACTS_DIR", "artifacts/browser/artifacts"),
        browser_downloads_dir=os.getenv("LAWCOPILOT_BROWSER_DOWNLOADS_DIR", "artifacts/browser/downloads"),
        browser_allowed_domains=browser_domains,
        browser_worker_timeout_seconds=int(os.getenv("LAWCOPILOT_BROWSER_WORKER_TIMEOUT", "45")),
        fastapi_lifespan_enabled=os.getenv("LAWCOPILOT_FASTAPI_LIFESPAN_ENABLED", "true").lower() == "true",
        personal_kb_enabled=os.getenv("LAWCOPILOT_PERSONAL_KB_ENABLED", "true").lower() != "false",
        personal_kb_root=os.getenv("LAWCOPILOT_PERSONAL_KB_ROOT", "artifacts/runtime/personal-kb"),
        personal_kb_excluded_patterns=personal_kb_excluded_patterns,
        personal_kb_search_backend=os.getenv("LAWCOPILOT_PERSONAL_KB_SEARCH_BACKEND", "sqlite_hybrid_fts_v1"),
        personal_kb_dense_candidates_enabled=os.getenv("LAWCOPILOT_PERSONAL_KB_DENSE_CANDIDATES_ENABLED", "false").lower() == "true",
        personal_kb_semantic_backend=os.getenv("LAWCOPILOT_PERSONAL_KB_SEMANTIC_BACKEND", "heuristic").strip().lower() or "heuristic",
        personal_kb_embedding_model_name=os.getenv(
            "LAWCOPILOT_PERSONAL_KB_EMBEDDING_MODEL_NAME",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ).strip()
        or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        personal_kb_cross_encoder_model_name=os.getenv(
            "LAWCOPILOT_PERSONAL_KB_CROSS_ENCODER_MODEL_NAME",
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
        ).strip()
        or "cross-encoder/ms-marco-MiniLM-L-6-v2",
        personal_kb_reranker_mode=os.getenv("LAWCOPILOT_PERSONAL_KB_RERANKER_MODE", "local_heuristic").strip() or "local_heuristic",
        personal_kb_recommendation_cooldown_minutes=int(
            os.getenv("LAWCOPILOT_PERSONAL_KB_RECOMMENDATION_COOLDOWN_MINUTES", "180")
        ),
        personal_kb_scheduler_enabled=os.getenv("LAWCOPILOT_PERSONAL_KB_SCHEDULER_ENABLED", "false").lower() == "true",
        personal_kb_startup_bootstrap_enabled=os.getenv(
            "LAWCOPILOT_PERSONAL_KB_STARTUP_BOOTSTRAP_ENABLED",
            "false" if running_under_pytest else "true",
        ).lower() == "true",
        personal_kb_scheduler_poll_seconds=int(os.getenv("LAWCOPILOT_PERSONAL_KB_SCHEDULER_POLL_SECONDS", "60")),
        personal_kb_scheduler_trigger_interval_seconds=int(
            os.getenv("LAWCOPILOT_PERSONAL_KB_SCHEDULER_TRIGGER_INTERVAL_SECONDS", "300")
        ),
        personal_kb_scheduler_reflection_interval_seconds=int(
            os.getenv("LAWCOPILOT_PERSONAL_KB_SCHEDULER_REFLECTION_INTERVAL_SECONDS", "900")
        ),
        personal_kb_scheduler_connector_sync_interval_seconds=int(
            os.getenv("LAWCOPILOT_PERSONAL_KB_SCHEDULER_CONNECTOR_SYNC_INTERVAL_SECONDS", "600")
        ),
        personal_kb_llm_article_authoring_enabled=os.getenv(
            "LAWCOPILOT_PERSONAL_KB_LLM_ARTICLE_AUTHORING_ENABLED", "true"
        ).lower()
        != "false",
        personal_kb_llm_article_limit=int(os.getenv("LAWCOPILOT_PERSONAL_KB_LLM_ARTICLE_LIMIT", "4")),
        runtime_job_worker_mode=os.getenv("LAWCOPILOT_RUNTIME_JOB_WORKER_MODE", "inline").strip().lower() or "inline",
        runtime_job_subprocess_timeout_seconds=int(os.getenv("LAWCOPILOT_RUNTIME_JOB_SUBPROCESS_TIMEOUT_SECONDS", "180")),
        location_provider_mode=os.getenv("LAWCOPILOT_LOCATION_PROVIDER_MODE", "desktop_file_fallback"),
        location_snapshot_path=os.getenv("LAWCOPILOT_LOCATION_SNAPSHOT_PATH", "artifacts/runtime/location/context.json"),
        google_maps_embed_api_key=os.getenv("LAWCOPILOT_GOOGLE_MAPS_EMBED_API_KEY", "").strip(),
    )


def load_model_profiles(path: str) -> dict:
    candidates = [
        (_runtime_root() / path).resolve(),
        (_repo_root() / path).resolve(),
    ]
    for full in candidates:
        if full.exists():
            with full.open("r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(path)


def resolve_repo_path(path: str) -> Path:
    runtime_path = (_runtime_root() / path).resolve()
    if runtime_path.exists():
        return runtime_path
    return (_repo_root() / path).resolve()
