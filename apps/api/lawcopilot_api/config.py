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
    app_version: str = "0.7.0-pilot.1"
    office_id: str = "default-office"
    deployment_mode: str = "local-only"
    release_channel: str = "pilot"
    environment: str = "pilot"
    desktop_shell: str = "electron"
    jwt_secret: str = "dev-change-me"
    token_ttl_seconds: int = 3600
    bootstrap_admin_key: str = ""
    model_profiles_path: str = "configs/model-profiles.json"
    default_model_profile: str = "hybrid"
    audit_log_path: str = "artifacts/audit.log.jsonl"
    structured_log_path: str = "artifacts/events.log.jsonl"
    db_path: str = "artifacts/lawcopilot.db"
    connector_allow_domains: tuple[str, ...] = ("example.com", "baro.org.tr")
    connector_dry_run: bool = True
    max_ingest_bytes: int = 5 * 1024 * 1024
    allow_header_auth: bool = False
    expose_security_flags: bool = False
    rag_backend: str = "inmemory"
    rag_tenant_id: str = "default"
    provider_type: str = ""
    provider_base_url: str = ""
    provider_model: str = ""
    provider_configured: bool = False
    telegram_enabled: bool = False
    telegram_configured: bool = False
    telegram_bot_username: str = ""
    telegram_allowed_user_id: str = ""


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
    domains = tuple(
        d.strip().lower() for d in os.getenv("LAWCOPILOT_CONNECTOR_ALLOW_DOMAINS", "example.com,baro.org.tr").split(",") if d.strip()
    )
    return Settings(
        app_name=os.getenv("LAWCOPILOT_APP_NAME", "LawCopilot"),
        app_version=os.getenv("LAWCOPILOT_APP_VERSION", "0.7.0-pilot.1"),
        office_id=os.getenv("LAWCOPILOT_OFFICE_ID", "default-office"),
        deployment_mode=_normalized_deployment_mode(os.getenv("LAWCOPILOT_DEPLOYMENT_MODE", "local-only")),
        release_channel=os.getenv("LAWCOPILOT_RELEASE_CHANNEL", "pilot"),
        environment=os.getenv("LAWCOPILOT_ENVIRONMENT", "pilot"),
        desktop_shell=os.getenv("LAWCOPILOT_DESKTOP_SHELL", "electron"),
        jwt_secret=os.getenv("LAWCOPILOT_JWT_SECRET", "dev-change-me"),
        token_ttl_seconds=int(os.getenv("LAWCOPILOT_TOKEN_TTL", "3600")),
        bootstrap_admin_key=os.getenv("LAWCOPILOT_BOOTSTRAP_ADMIN_KEY", ""),
        model_profiles_path=os.getenv("LAWCOPILOT_MODEL_PROFILES", "configs/model-profiles.json"),
        default_model_profile=os.getenv("LAWCOPILOT_DEFAULT_MODEL_PROFILE", "hybrid"),
        audit_log_path=os.getenv("LAWCOPILOT_AUDIT_LOG", "artifacts/audit.log.jsonl"),
        structured_log_path=os.getenv("LAWCOPILOT_STRUCTURED_LOG", "artifacts/events.log.jsonl"),
        db_path=os.getenv("LAWCOPILOT_DB_PATH", "artifacts/lawcopilot.db"),
        connector_allow_domains=domains,
        connector_dry_run=os.getenv("LAWCOPILOT_CONNECTOR_DRY_RUN", "true").lower() != "false",
        max_ingest_bytes=int(os.getenv("LAWCOPILOT_MAX_INGEST_BYTES", str(5 * 1024 * 1024))),
        allow_header_auth=os.getenv("LAWCOPILOT_ALLOW_HEADER_AUTH", "false").lower() == "true",
        expose_security_flags=os.getenv("LAWCOPILOT_EXPOSE_SECURITY_FLAGS", "false").lower() == "true",
        rag_backend=os.getenv("LAWCOPILOT_RAG_BACKEND", "inmemory"),
        rag_tenant_id=os.getenv("LAWCOPILOT_RAG_TENANT_ID", "default"),
        provider_type=os.getenv("LAWCOPILOT_PROVIDER_TYPE", ""),
        provider_base_url=os.getenv("LAWCOPILOT_PROVIDER_BASE_URL", ""),
        provider_model=os.getenv("LAWCOPILOT_PROVIDER_MODEL", ""),
        provider_configured=os.getenv("LAWCOPILOT_PROVIDER_CONFIGURED", "false").lower() == "true",
        telegram_enabled=os.getenv("LAWCOPILOT_TELEGRAM_ENABLED", "false").lower() == "true",
        telegram_configured=os.getenv("LAWCOPILOT_TELEGRAM_CONFIGURED", "false").lower() == "true",
        telegram_bot_username=os.getenv("LAWCOPILOT_TELEGRAM_BOT_USERNAME", ""),
        telegram_allowed_user_id=os.getenv("LAWCOPILOT_TELEGRAM_ALLOWED_USER_ID", ""),
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
