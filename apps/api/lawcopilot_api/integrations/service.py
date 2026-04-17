from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from ..connectors.registry import build_tools_status
from .catalog import PERMISSIONS, build_connector_catalog
from .models import (
    ConnectorSpec,
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
from .normalization import normalize_records_to_resources
from .oauth_runtime import (
    auth_status_from_summary,
    build_auth_summary,
    build_authorization_url,
    exchange_authorization_code,
    generate_pkce_verifier,
    generate_state_token,
    refresh_access_token,
    revoke_access_token,
    summarize_scope_permissions,
)
from .policy import build_safety_settings, discover_capabilities, evaluate_action_policy
from .repository import IntegrationRepository
from .runtime import IntegrationExecutionRuntime, IntegrationRuntimeError
from .scaffold import generate_connector_scaffold, prepare_scaffold_request
from .secret_box import SecretBox


SAFE_TEXT_CHARS = 4000

KNOWN_AUTOMATION_TARGETS = {
    "slack": {
        "service_name": "Slack",
        "docs_url": "https://api.slack.com",
        "category": "communication",
        "preferred_auth_type": "oauth2",
        "base_url": "https://slack.com/api",
        "scopes": ["channels:read", "channels:history", "chat:write"],
        "auth_config": {
            "authorization_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "revocation_url": "https://slack.com/api/auth.revoke",
            "scope_separator": ",",
            "pkce_required": False,
        },
        "resources": [
            {"key": "channels", "title": "Kanallar", "description": "Slack kanal envanteri", "item_types": ["thread"], "supports_search": True},
            {"key": "messages", "title": "Mesajlar", "description": "Slack mesaj ve thread kayitlari", "item_types": ["message"], "supports_search": True},
        ],
        "actions": [
            {"key": "list_items", "title": "Kanalları listele", "description": "Slack kanallarını listeler.", "operation": "list_items", "access": "read", "method": "GET", "path": "/conversations.list", "response_items_path": "channels"},
            {"key": "read_messages", "title": "Mesajları oku", "description": "Slack kanal mesajlarını okur.", "operation": "read_messages", "access": "read", "method": "GET", "path": "/conversations.history", "response_items_path": "messages", "query_map": {"channel": "channel"}},
            {"key": "search", "title": "Mesajlarda ara", "description": "Slack mesajları içinde metin arar.", "operation": "search", "access": "read", "method": "GET", "path": "/conversations.history", "response_items_path": "messages", "query_map": {"channel": "channel"}},
            {"key": "send_message", "title": "Mesaj gönder", "description": "Onay sonrası Slack mesajı yollar.", "operation": "send_message", "access": "write", "approval_required": True, "method": "POST", "path": "/chat.postMessage"},
        ],
        "webhook_support": {
            "supported": True,
            "signature_header": "X-Slack-Signature",
            "secret_required": True,
            "events": ["message", "app_mention", "member_joined_channel"],
        },
        "extra_ui_fields": [
            {"key": "signing_secret", "label": "Signing secret", "kind": "password", "target": "secret", "required": False, "secret": True},
        ],
    },
    "discord": {
        "service_name": "Discord",
        "docs_url": "https://discord.com/developers/docs/intro",
        "category": "communication",
        "preferred_auth_type": "oauth2",
        "base_url": "https://discord.com/api/v10",
        "scopes": ["identify", "guilds", "messages.read"],
        "auth_config": {
            "authorization_url": "https://discord.com/oauth2/authorize",
            "token_url": "https://discord.com/api/oauth2/token",
            "scope_separator": " ",
            "pkce_required": False,
        },
    },
    "jira": {
        "service_name": "Jira",
        "docs_url": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/",
        "category": "project-management",
        "preferred_auth_type": "oauth2",
        "base_url": "https://api.atlassian.com/ex/jira",
    },
    "trello": {
        "service_name": "Trello",
        "docs_url": "https://developer.atlassian.com/cloud/trello/guides/rest-api/api-introduction/",
        "category": "project-management",
        "preferred_auth_type": "oauth2",
        "base_url": "https://api.trello.com/1",
    },
    "hubspot": {
        "service_name": "HubSpot",
        "docs_url": "https://developers.hubspot.com/docs/api/overview",
        "category": "crm",
        "preferred_auth_type": "oauth2",
        "base_url": "https://api.hubapi.com",
        "auth_config": {
            "authorization_url": "https://app.hubspot.com/oauth/authorize",
            "token_url": "https://api.hubapi.com/oauth/v1/token",
            "scope_separator": " ",
            "pkce_required": False,
        },
    },
    "dropbox": {
        "service_name": "Dropbox",
        "docs_url": "https://www.dropbox.com/developers/documentation/http/documentation",
        "category": "storage",
        "preferred_auth_type": "oauth2",
        "base_url": "https://api.dropboxapi.com/2",
        "auth_config": {
            "authorization_url": "https://www.dropbox.com/oauth2/authorize",
            "token_url": "https://api.dropboxapi.com/oauth2/token",
            "scope_separator": " ",
            "pkce_required": True,
        },
    },
    "google drive": {
        "service_name": "Google Drive",
        "docs_url": "https://developers.google.com/drive/api/guides/about-sdk",
        "category": "storage",
        "preferred_auth_type": "oauth2",
    },
    "gmail": {
        "service_name": "Gmail",
        "docs_url": "https://developers.google.com/gmail/api",
        "category": "communication",
        "preferred_auth_type": "oauth2",
        "auth_config": {
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "revocation_url": "https://oauth2.googleapis.com/revoke",
            "scope_separator": " ",
            "pkce_required": True,
        },
    },
    "google calendar": {
        "service_name": "Google Calendar",
        "docs_url": "https://developers.google.com/workspace/calendar/api/guides/overview",
        "category": "calendar",
        "preferred_auth_type": "oauth2",
        "auth_config": {
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "revocation_url": "https://oauth2.googleapis.com/revoke",
            "scope_separator": " ",
            "pkce_required": True,
        },
    },
    "outlook": {
        "service_name": "Outlook",
        "docs_url": "https://learn.microsoft.com/graph/api/resources/mail-api-overview",
        "category": "communication",
        "preferred_auth_type": "oauth2",
    },
    "notion": {
        "service_name": "Notion",
        "docs_url": "https://developers.notion.com",
        "category": "knowledge-base",
        "preferred_auth_type": "bearer",
    },
    "github": {
        "service_name": "GitHub",
        "docs_url": "https://docs.github.com/rest",
        "category": "developer-tools",
        "preferred_auth_type": "oauth2",
    },
    "tiktok": {
        "service_name": "TikTok",
        "docs_url": "https://developers.tiktok.com/doc/login-kit-overview/",
        "category": "social-media",
        "preferred_auth_type": "oauth2",
        "base_url": "https://open.tiktokapis.com",
        "scopes": ["user.info.basic", "video.list"],
        "auth_config": {
            "authorization_url": "https://www.tiktok.com/v2/auth/authorize/",
            "token_url": "https://open.tiktokapis.com/v2/oauth/token/",
            "revocation_url": "https://open.tiktokapis.com/v2/oauth/revoke/",
            "scope_separator": ",",
            "pkce_required": True,
            "token_field_map": {
                "client_id": "client_key",
            },
        },
        "resources": [
            {"key": "profile", "title": "Hesap profili", "description": "TikTok hesap bilgileri ve temel istatistikler", "item_types": ["profile"], "supports_search": False},
        ],
        "actions": [
            {
                "key": "get_item",
                "title": "Profili getir",
                "description": "TikTok hesabinin temel profil ve istatistik alanlarini getirir.",
                "operation": "get_item",
                "access": "read",
                "method": "GET",
                "path": "/v2/user/info/?fields=open_id,display_name,bio_description,avatar_url,is_verified,follower_count,following_count,likes_count,video_count",
                "response_item_path": "data",
            }
        ],
        "extra_ui_fields": [
            {
                "key": "resource_path",
                "label": "Profil endpoint yolu",
                "kind": "text",
                "target": "config",
                "required": False,
                "default": "/v2/user/info/?fields=open_id,display_name,bio_description,avatar_url,is_verified,follower_count,following_count,likes_count,video_count",
                "help_text": "Varsayilan hesap profil endpoint'i kullanilir; gerekirse buradan degistirebilirsin.",
            }
        ],
    },
    "instagram": {
        "service_name": "Instagram",
        "docs_url": "https://developers.facebook.com/docs/messenger-platform/instagram",
        "category": "social-media",
        "preferred_auth_type": "oauth2",
        "base_url": "https://graph.facebook.com/v22.0",
        "scopes": ["instagram_basic", "instagram_manage_messages", "pages_manage_metadata", "pages_show_list"],
        "auth_config": {
            "authorization_url": "https://www.facebook.com/v22.0/dialog/oauth",
            "token_url": "https://graph.facebook.com/v22.0/oauth/access_token",
            "scope_separator": ",",
            "pkce_required": False,
        },
        "resources": [
            {"key": "messages", "title": "Instagram DM", "description": "Instagram Professional hesap mesaj kutusu", "item_types": ["message"], "supports_search": True},
            {"key": "profile", "title": "Hesap bilgisi", "description": "Instagram hesabı ve bağlı sayfa bilgileri", "item_types": ["profile"], "supports_search": False},
        ],
        "actions": [
            {
                "key": "read_messages",
                "title": "Mesajları oku",
                "description": "Instagram DM konuşmalarını getirir.",
                "operation": "read_messages",
                "access": "read",
                "method": "GET",
                "path": "/{page_id}/conversations",
                "response_items_path": "data",
            },
            {
                "key": "send_message",
                "title": "Mesaj gönder",
                "description": "Onay sonrası Instagram DM yanıtı yollar.",
                "operation": "send_message",
                "access": "write",
                "approval_required": True,
                "method": "POST",
                "path": "/{page_id}/messages",
            },
        ],
        "extra_ui_fields": [
            {
                "key": "page_name_hint",
                "label": "Sayfa adı ipucu",
                "kind": "text",
                "target": "config",
                "required": False,
                "placeholder": "Ofis Instagram hesabı",
                "help_text": "Meta hesabında birden fazla sayfa varsa doğru sayfayı seçmek için kullanılabilir.",
            }
        ],
    },
    "postgresql": {
        "service_name": "PostgreSQL",
        "category": "database",
        "preferred_auth_type": "database",
    },
    "mysql": {
        "service_name": "MySQL",
        "category": "database",
        "preferred_auth_type": "database",
    },
    "mssql": {
        "service_name": "SQL Server",
        "category": "database",
        "preferred_auth_type": "database",
    },
    "elastic": {
        "service_name": "Elastic",
        "category": "search-engine",
        "preferred_auth_type": "api_key",
    },
}

LEGACY_ASSISTANT_RECIPES = [
    {
        "connector_id": "drive",
        "service_name": "Google Drive",
        "aliases": ["google drive", "drive hesab", "drive bagla", "drive bağla"],
        "setup_path": "/settings?tab=kurulum&section=integration-google",
        "next_step": "Google Drive kurulumunu tamamlamak için Google izin ekranını açabileceğin kurulum ekranını aç.",
        "summary": "Google Drive bağlandığında dosyaları listeleyip ilgili içerikleri çekebilirim.",
        "capability_preview": ["Dosyaları listele", "Dosya içeriğini getir", "Dosyayı kayda bağla"],
        "review_summary": [
            "Google hesabını seçip Drive iznini ver.",
            "Kurulum tamamlandıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
        ],
        "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
        "recommended_prompts": ["Son Drive dosyalarını listele", "Drive içeriğinde ara"],
    },
    {
        "connector_id": "calendar",
        "service_name": "Google Takvim",
        "aliases": ["google takvim", "google calendar", "takvim bagla", "takvim bağla"],
        "setup_path": "/settings?tab=kurulum&section=integration-google",
        "next_step": "Google Takvim kurulumunu tamamlamak için Google izin ekranını açabileceğin kurulum ekranını aç.",
        "summary": "Google Takvim bağlandığında etkinlikleri ve uygun zamanları takip edebilirim.",
        "capability_preview": ["Etkinlikleri oku", "Uygun saat öner", "Onayla etkinlik oluştur"],
        "review_summary": [
            "Google hesabını seçip Takvim iznini ver.",
            "Kurulum tamamlandıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
        ],
        "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
        "recommended_prompts": ["Bugünkü takvimi özetle", "Uygun toplantı saatleri öner"],
    },
    {
        "connector_id": "gmail",
        "service_name": "Google hesabı",
        "aliases": ["gmail", "google hesab", "google account", "google workspace", "google mail", "google bagla", "google bağla", "google"],
        "setup_path": "/settings?tab=kurulum&section=integration-google",
        "next_step": "Google hesabı bağlantısını tamamlamak için kurulum ekranını açıp Google erişim onayını ver.",
        "summary": "Google hesabı bağlandığında e-postaları, takvim kayıtlarını ve Drive dosyalarını bana açabilirsin.",
        "capability_preview": ["E-postaları oku", "Takvimi özetle", "Drive dosyalarını listele", "Onayla yanıt hazırla"],
        "review_summary": [
            "Google hesabını seçip gerekli izinleri ver.",
            "Kurulum tamamlandıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
        ],
        "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
        "recommended_prompts": ["Son Google e-postalarını özetle", "Bugünkü takvimi göster"],
    },
    {
        "connector_id": "outlook-calendar",
        "service_name": "Outlook Takvim",
        "aliases": ["outlook takvim", "outlook calendar"],
        "setup_path": "/settings?tab=kurulum&section=integration-outlook",
        "next_step": "Outlook Takvim kurulumunu tamamlamak için kurulum ekranını açıp Microsoft iznini ver.",
        "summary": "Outlook Takvim bağlandığında etkinlikleri ve uygun zamanları takip edebilirim.",
        "capability_preview": ["Etkinlikleri oku", "Uygun saat öner", "Onayla etkinlik güncelle"],
        "review_summary": [
            "Microsoft hesabını seçip Takvim iznini ver.",
            "Kurulum tamamlandıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
        ],
        "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
        "recommended_prompts": ["Outlook takvimimi özetle", "Uygun toplantı saatleri öner"],
    },
    {
        "connector_id": "outlook-mail",
        "service_name": "Outlook hesabı",
        "aliases": ["outlook", "outlook mail", "microsoft 365", "office 365"],
        "setup_path": "/settings?tab=kurulum&section=integration-outlook",
        "next_step": "Outlook bağlantısını tamamlamak için kurulum ekranını açıp Microsoft erişim onayını ver.",
        "summary": "Outlook bağlandığında e-posta ve takvim akışını benimle yönetebilirsin.",
        "capability_preview": ["E-postaları oku", "Takvimi özetle", "Onayla yanıt hazırla"],
        "review_summary": [
            "Microsoft hesabını seçip gerekli izinleri ver.",
            "Kurulum tamamlandıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
        ],
        "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
        "recommended_prompts": ["Son Outlook e-postalarını özetle", "Bugünkü Outlook takvimini göster"],
    },
    {
        "connector_id": "telegram",
        "service_name": "Telegram",
        "aliases": ["telegram", "telegram bot", "telegram bagla", "telegram bağla"],
        "setup_path": "/settings?tab=kurulum&section=integration-telegram",
        "next_step": "Telegram bot kurulumunu tamamlamak için kurulum ekranını açıp bot bilgilerini doğrula.",
        "summary": "Telegram bağlandığında mesajları okuyup taslak yanıtlar hazırlayabilirim.",
        "capability_preview": ["Mesajları oku", "Yanıt taslağı hazırla", "Onayla gönder"],
        "review_summary": [
            "Bot token ve izin adımlarını kurulum ekranından tamamla.",
            "Kurulum tamamlandıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
        ],
        "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
        "recommended_prompts": ["Son Telegram mesajlarını özetle", "Telegram için yanıt taslağı hazırla"],
    },
    {
        "connector_id": "whatsapp",
        "service_name": "WhatsApp",
        "aliases": ["whatsapp", "whats app", "whatsapp bagla", "whatsapp bağla"],
        "setup_path": "/settings?tab=kurulum&section=integration-whatsapp",
        "next_step": "WhatsApp kurulumunu tamamlamak için kurulum ekranını açıp doğrulama adımlarını bitir.",
        "summary": "WhatsApp bağlandığında konuşmaları tarayıp yanıt taslakları hazırlayabilirim.",
        "capability_preview": ["Mesajları oku", "Konuşmaları özetle", "Onayla gönder"],
        "review_summary": [
            "Telefon doğrulama ve kanal adımlarını kurulum ekranından tamamla.",
            "Kurulum tamamlandıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
        ],
        "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
        "recommended_prompts": ["Son WhatsApp mesajlarını özetle", "WhatsApp için yanıt taslağı hazırla"],
    },
    {
        "connector_id": "x",
        "service_name": "X hesabı",
        "aliases": [" x ", "x hesab", "twitter", "x bagla", "x bağla"],
        "setup_path": "/settings?tab=kurulum&section=integration-x",
        "next_step": "X hesabı bağlantısını tamamlamak için kurulum ekranını açıp erişim onayını ver.",
        "summary": "X bağlandığında mention'ları ve mesaj akışını takip edip gönderi taslakları hazırlayabilirim.",
        "capability_preview": ["Bahsetmeleri oku", "Gönderi taslağı hazırla", "Mesajları özetle"],
        "review_summary": [
            "Hesap erişimini kurulum ekranından onayla.",
            "Kurulum tamamlandıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
        ],
        "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
        "recommended_prompts": ["X mention'larını özetle", "X için gönderi taslağı hazırla"],
    },
    {
        "connector_id": "linkedin",
        "service_name": "LinkedIn hesabı",
        "aliases": ["linkedin", "linked in", "linkedin hesab", "linkedin bagla", "linkedin bağla"],
        "setup_path": "/settings?tab=kurulum&section=integration-linkedin",
        "next_step": "LinkedIn bağlantısını tamamlamak için kurulum ekranını açıp izin adımını bitir.",
        "summary": "LinkedIn bağlandığında gönderileri ve yorum akışını izleyip paylaşım taslakları hazırlayabilirim.",
        "capability_preview": ["Gönderileri oku", "Yorumları izle", "Onayla paylaş"],
        "review_summary": [
            "LinkedIn hesap erişimini kurulum ekranından onayla.",
            "Kurulum tamamlandıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
        ],
        "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
        "recommended_prompts": ["LinkedIn yorumlarını özetle", "LinkedIn için gönderi taslağı hazırla"],
    },
    {
        "connector_id": "instagram",
        "service_name": "Instagram Professional hesabı",
        "aliases": ["instagram", "insta", "instagram hesab", "instagram bagla", "instagram bağla", "instagram dm"],
        "setup_path": "/settings?tab=kurulum&section=integration-instagram",
        "next_step": "Instagram bağlantısını tamamlamak için Meta izin ekranını açıp onay adımını bitir.",
        "summary": "Instagram bağlandığında DM mesajlarını okuyup senin onayınla yanıt taslakları hazırlayabilirim.",
        "capability_preview": ["Mesajları oku", "Mesajlarda ara", "Onayla yanıtla"],
        "review_summary": [
            "Instagram Professional hesabının bir Facebook sayfasına bağlı olması gerekir.",
            "İzin akışını tamamladıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
        ],
        "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
        "recommended_prompts": ["Son Instagram mesajlarını özetle", "Instagram için yanıt taslağı hazırla"],
    },
]


class IntegrationPlatformService:
    def __init__(self, *, settings, store, audit, db_path, http_transport=None, database_adapters=None, web_intel=None) -> None:
        self.settings = settings
        self.store = store
        self.audit = audit
        self.http_transport = http_transport
        self.web_intel = web_intel
        self.catalog = build_connector_catalog()
        self.static_catalog = dict(self.catalog)
        self.repo = IntegrationRepository(db_path)
        explicit_key = os.getenv("LAWCOPILOT_INTEGRATION_SECRET_KEY", "").strip()
        posture = "env-managed-key" if explicit_key else "jwt-derived-local-key"
        self.secret_box = SecretBox(
            explicit_key or settings.jwt_secret,
            posture=f"{getattr(settings, 'environment', 'default')}:{posture}",
            key_id=str(getattr(settings, "integration_secret_key_id", "default") or "default"),
            previous_keys=list(getattr(settings, "integration_secret_previous_keys", ()) or ()),
        )
        self.runtime = IntegrationExecutionRuntime(
            settings=settings,
            transport=http_transport,
            database_adapters=database_adapters,
            web_intel=web_intel,
        )
        self.sync_worker = None

    def attach_sync_worker(self, worker) -> None:
        self.sync_worker = worker

    def security_posture(self) -> dict[str, Any]:
        return {
            "storage_posture": self.secret_box.posture,
            "secret_key_id": self.secret_box.active_key_id,
            "secret_key_count": int(getattr(self.secret_box, "key_count", 1)),
            "connector_dry_run": bool(self.settings.connector_dry_run),
            "human_review_gate": True,
            "allowed_domains": list(self.settings.connector_allow_domains),
            "sync_worker_enabled": bool(getattr(self.settings, "integration_worker_enabled", False)),
        }

    def list_catalog(self, *, query: str | None = None, category: str | None = None) -> dict[str, Any]:
        query_text = _normalize_text(query)
        legacy_status_map = self._legacy_status_map()
        generated_rows = self._list_active_generated_rows()
        generated_specs = self._generated_connector_specs(generated_rows)
        catalog = {**self.static_catalog, **generated_specs}
        grouped_connections: dict[str, list[dict[str, Any]]] = {}
        for connection in self.repo.list_connections(self.settings.office_id):
            grouped_connections.setdefault(str(connection.get("connector_id") or ""), []).append(connection)

        items: list[dict[str, Any]] = []
        categories: set[str] = set()
        for connector_id, spec in catalog.items():
            categories.add(spec.category)
            if category and spec.category != category:
                continue
            if query_text and query_text not in _search_blob(spec):
                continue
            connections = [self._serialize_connection(item) for item in grouped_connections.get(connector_id, [])]
            legacy_status = legacy_status_map.get(connector_id)
            generated_row = next((row for row in generated_rows if str(row.get("connector_id") or "") == connector_id), None)
            items.append(
                {
                    "connector": spec.model_dump(mode="json"),
                    "connections": connections,
                    "legacy_status": legacy_status,
                    "generated_request": self._serialize_generated_connector(generated_row) if generated_row else None,
                    "installed": bool(connections or legacy_status),
                    "primary_status": self._primary_status(connections, legacy_status),
                    "source": (
                        "generated-request"
                        if generated_row
                        else "legacy-desktop"
                        if spec.management_mode == "legacy-desktop"
                        else "typed-connector-catalog"
                    ),
                }
            )
        items.sort(
            key=lambda item: (
                0 if item["installed"] else 1,
                0 if item["connector"]["management_mode"] == "platform" else 1,
                str(item["connector"]["name"]).lower(),
            )
        )
        return {
            "items": items,
            "categories": sorted(categories),
            "security": self.security_posture(),
            "generated_from": "integration_platform_catalog",
        }

    def list_connections(self) -> dict[str, Any]:
        catalog = self._effective_catalog()
        items = []
        for connection in self.repo.list_connections(self.settings.office_id):
            spec = catalog.get(str(connection.get("connector_id") or ""))
            items.append(
                {
                    "connection": self._serialize_connection(connection),
                    "connector": spec.model_dump(mode="json") if spec else None,
                    "capabilities": discover_capabilities(connection, spec) if spec else None,
                }
            )
        return {"items": items, "generated_from": "integration_platform_connections"}

    def list_generated_requests(self) -> dict[str, Any]:
        rows = self.repo.list_generated_connectors(self.settings.office_id, limit=200)
        return {
            "items": [self._serialize_generated_connector(row) for row in rows],
            "generated_from": "integration_generated_connector_requests",
        }

    def list_events(self, *, connection_id: int | None = None, limit: int = 20) -> dict[str, Any]:
        return {
            "items": self.repo.list_events(self.settings.office_id, connection_id=connection_id, limit=limit),
            "webhook_items": self.repo.list_webhook_events(self.settings.office_id, connection_id=connection_id, limit=limit),
            "worker": self.sync_worker.status() if self.sync_worker else None,
            "generated_from": "integration_platform_events",
        }

    def worker_status(self) -> dict[str, Any]:
        return {
            "worker": self.sync_worker.status() if self.sync_worker else {"state": "disabled"},
            "generated_from": "integration_worker_status",
        }

    def launch_ops_summary(self) -> dict[str, Any]:
        snapshot = self.repo.summarize_launch_metrics(self.settings.office_id)
        connections = self.repo.list_connections(self.settings.office_id)
        generated_rows = self.repo.list_generated_connectors(self.settings.office_id, limit=200)
        recent_alerts = [item for item in self.repo.list_events(self.settings.office_id, limit=25) if str(item.get("severity") or "info") in {"warning", "error"}][:8]

        degraded_connections = [
            {
                "connection_id": int(item.get("id") or 0),
                "connector_id": str(item.get("connector_id") or ""),
                "display_name": str(item.get("display_name") or item.get("connector_id") or ""),
                "health_status": str(item.get("health_status") or ""),
                "auth_status": str(item.get("auth_status") or ""),
                "sync_status": str(item.get("sync_status") or ""),
                "last_error": str(item.get("last_error") or item.get("health_message") or "").strip() or None,
            }
            for item in connections
            if str(item.get("health_status") or "") in {"invalid", "degraded", "revoked"}
            or str(item.get("sync_status") or "") in {"failed", "retry_scheduled"}
        ][:8]

        stale_threshold_minutes = max(30, int(getattr(self.settings, "integration_assistant_setup_timeout_minutes", 720) or 720))
        stale_setups = []
        for row in self.repo.list_assistant_setups(self.settings.office_id, limit=200):
            if str(row.get("status") or "") in {"completed", "cancelled", "failed", "abandoned", "expired"}:
                continue
            if not self._assistant_setup_is_stale(row):
                continue
            stale_setups.append(
                {
                    "setup_id": int(row.get("id") or 0),
                    "thread_id": int(row.get("thread_id") or 0),
                    "service_name": str(row.get("service_name") or row.get("connector_id") or "Connector"),
                    "status": str(row.get("status") or ""),
                    "updated_at": row.get("updated_at"),
                }
            )
        setup_counts = dict((snapshot.get("assistant_setups") or {}).get("counts") or {})
        oauth_counts = dict((snapshot.get("oauth_sessions") or {}).get("counts") or {})
        sync_counts = dict((snapshot.get("sync_runs") or {}).get("counts") or {})
        generated_counts = dict((snapshot.get("generated_connectors") or {}).get("counts") or {})
        setup_started = sum(int(value or 0) for value in setup_counts.values())
        setup_completed = int(setup_counts.get("completed") or 0)
        oauth_started = sum(int(value or 0) for value in oauth_counts.values())
        oauth_completed = int(oauth_counts.get("completed") or 0)
        sync_finished = int(sync_counts.get("completed") or 0) + int(sync_counts.get("failed") or 0)
        sync_success = int(sync_counts.get("completed") or 0)
        webhook_counts = dict((snapshot.get("webhooks") or {}).get("counts") or {})
        webhook_total = sum(int(value or 0) for value in webhook_counts.values())
        webhook_failed = int(webhook_counts.get("failed") or 0)
        worker = self.sync_worker.status() if self.sync_worker else {"state": "disabled"}
        setup_completion_rate = round((setup_completed / setup_started), 3) if setup_started else 1.0
        oauth_completion_rate = round((oauth_completed / oauth_started), 3) if oauth_started else 1.0
        sync_success_rate = round((sync_success / sync_finished), 3) if sync_finished else 1.0
        webhook_failure_rate = round((webhook_failed / webhook_total), 3) if webhook_total else 0.0

        readiness_checks: list[dict[str, Any]] = []
        if bool(self.settings.connector_dry_run):
            readiness_checks.append({"level": "warning", "label": "dry_run_enabled", "count": 1, "message": "Platform-managed connector'lar hala dry-run modunda."})
        if bool(getattr(self.settings, "allow_header_auth", False)):
            readiness_checks.append({"level": "critical", "label": "header_auth_enabled", "count": 1, "message": "Header auth acik; production rollout icin kapatilmasi gerekir."})
        if str(getattr(self.settings, "jwt_secret", "") or "") == "dev-change-me":
            readiness_checks.append({"level": "critical", "label": "default_jwt_secret", "count": 1, "message": "Varsayilan JWT secret kullaniliyor."})
        if str(self.secret_box.posture or "").endswith("jwt-derived-local-key"):
            readiness_checks.append({"level": "warning", "label": "local_secret_posture", "count": 1, "message": "Env-managed integration secret key tanimli degil."})
        if degraded_connections:
            readiness_checks.append({"level": "critical", "label": "degraded_connections", "count": len(degraded_connections), "message": "Hata veya retry bekleyen baglantilar var."})
        if stale_setups:
            readiness_checks.append({"level": "warning", "label": "stale_setups", "count": len(stale_setups), "message": "Uzun suredir yarim kalan kurulumlar var."})
        if str(worker.get("state") or "") == "error":
            readiness_checks.append({"level": "critical", "label": "worker_error", "count": int(worker.get("consecutive_failures") or 1), "message": "Sync worker hata durumunda."})
        if int(generated_counts.get("review_pending") or 0) > 0:
            readiness_checks.append({"level": "warning", "label": "review_pending", "count": int(generated_counts.get("review_pending") or 0), "message": "Canliya alinmayi bekleyen generated connector var."})
        if oauth_started >= 5 and oauth_completion_rate < 0.6:
            readiness_checks.append({"level": "warning", "label": "oauth_dropoff_spike", "count": oauth_started - oauth_completed, "message": "OAuth tamamlama orani dusuk; kullanici akisini kontrol edin."})
        if sync_finished >= 5 and sync_success_rate < 0.8:
            readiness_checks.append({"level": "warning" if sync_success_rate >= 0.5 else "critical", "label": "sync_failure_spike", "count": int(sync_counts.get("failed") or 0), "message": "Sync basari orani beklenenin altinda."})
        if webhook_total >= 5 and webhook_failure_rate >= 0.2:
            readiness_checks.append({"level": "warning", "label": "webhook_failures", "count": webhook_failed, "message": "Webhook hatalari arttı; signature ve provider durumunu kontrol edin."})
        if setup_started >= 5 and setup_completion_rate < 0.5:
            readiness_checks.append({"level": "warning", "label": "setup_dropoff_spike", "count": setup_started - setup_completed, "message": "Kurulum tamamlama orani dusuk; kullanici yolculugunda surtunme var."})

        return {
            "rollout": {
                "connector_dry_run": bool(self.settings.connector_dry_run),
                "integration_worker_enabled": bool(getattr(self.settings, "integration_worker_enabled", False)),
                "assistant_setup_timeout_minutes": stale_threshold_minutes,
                "allowed_domains": list(self.settings.connector_allow_domains),
            },
            "health": {
                "connection_count": len(connections),
                "generated_connector_count": len(generated_rows),
                "degraded_connections": degraded_connections,
                "stale_pending_setups": stale_setups,
                "worker": worker,
                "ready_for_launch": not any(str(item.get("level") or "") == "critical" for item in readiness_checks),
                "readiness_checks": readiness_checks,
            },
            "analytics": {
                "connector_requests": {
                    "total": len(generated_rows),
                    "top_requested": list((snapshot.get("generated_connectors") or {}).get("top_requests") or []),
                },
                "assistant_setups": {
                    "counts": setup_counts,
                    "completion_rate": setup_completion_rate,
                    "top_dropoffs": list((snapshot.get("assistant_setups") or {}).get("top_dropoffs") or []),
                },
                "oauth": {
                    "counts": oauth_counts,
                    "completion_rate": oauth_completion_rate,
                },
                "sync": {
                    "counts": sync_counts,
                    "success_rate": sync_success_rate,
                },
                "webhooks": {
                    "counts": webhook_counts,
                    "failure_rate": webhook_failure_rate,
                },
            },
            "support": {
                "recent_alerts": recent_alerts,
                "generated_review_pending": int(generated_counts.get("review_pending") or 0),
                "generated_rejected": int(generated_counts.get("rejected") or 0),
            },
            "security": self.security_posture(),
            "generated_from": "integration_launch_ops_summary",
        }

    def get_active_assistant_setup(self, thread_id: int) -> dict[str, Any] | None:
        setup = self.repo.get_active_assistant_setup(self.settings.office_id, thread_id)
        if not setup:
            return None
        serialized = self._serialize_assistant_setup(setup)
        if serialized is not None and self._assistant_setup_is_stale(setup):
            serialized = {**serialized, "stale": True}
        return serialized

    def prepare_assistant_setup_for_desktop(self, setup_id: int, *, actor: str) -> dict[str, Any]:
        setup = self.repo.get_assistant_setup(self.settings.office_id, setup_id)
        if not setup:
            raise ValueError("integration_assistant_setup_not_found")
        metadata = dict(setup.get("metadata") or {})
        if str(metadata.get("setup_mode") or "") != "legacy_desktop":
            raise ValueError("integration_assistant_setup_not_desktop_managed")
        if list(setup.get("missing_fields") or []):
            missing_labels = ", ".join(str(item.get("label") or item.get("key") or "alan") for item in list(setup.get("missing_fields") or []))
            raise ValueError(f"integration_assistant_setup_missing_fields:{missing_labels}")
        spec = self._require_connector(str(setup.get("connector_id") or ""))
        secrets_payload = self.secret_box.open_json(str(setup.get("secret_blob") or ""))
        config_patch = self._assistant_legacy_config_patch(
            spec,
            config=dict(setup.get("collected_config") or {}),
            secrets_payload=secrets_payload,
            metadata=metadata,
        )
        desktop_action, desktop_cta_label, desktop_action_help = self._assistant_legacy_desktop_action(
            spec,
            metadata=metadata,
            config=dict(setup.get("collected_config") or {}),
            secrets_payload=secrets_payload,
        )
        refreshed_metadata = {
            **metadata,
            "desktop_action": desktop_action,
            "desktop_cta_label": desktop_cta_label,
            "desktop_action_help": desktop_action_help,
            "pending_field": None,
            "next_step": desktop_action_help or metadata.get("next_step"),
        }
        updated = self.repo.upsert_assistant_setup(
            self.settings.office_id,
            thread_id=int(setup.get("thread_id") or 0),
            setup_id=int(setup["id"]),
            connector_id=str(setup.get("connector_id") or "") or None,
            connection_id=int(setup.get("connection_id") or 0) or None,
            service_name=str(setup.get("service_name") or "") or None,
            request_text=str(setup.get("request_text") or ""),
            status="ready_for_desktop_action",
            missing_fields=[],
            collected_config=dict(setup.get("collected_config") or {}),
            secret_blob=str(setup.get("secret_blob") or ""),
            metadata=refreshed_metadata,
            created_by=actor,
        )
        self._log_event(
            connector_id=str(setup.get("connector_id") or "") or None,
            connection_id=int(setup.get("connection_id") or 0) or None,
            event_type="assistant_setup_desktop_prepared",
            message="Legacy masaüstü kurulumu sohbetten hazırlanıp masaüstü akışına aktarıldı.",
            actor=actor,
            severity="info",
            data={"setup_id": int(setup["id"]), "desktop_action": desktop_action},
        )
        return {
            "setup": self._serialize_assistant_setup(updated),
            "connector": spec.model_dump(mode="json"),
            "desktop_action": desktop_action,
            "desktop_cta_label": desktop_cta_label,
            "desktop_action_help": desktop_action_help,
            "config_patch": config_patch,
            "generated_from": "assistant_integration_desktop_prepare",
        }

    def orchestrate_assistant_chat(
        self,
        *,
        thread_id: int,
        query: str,
        actor: str,
        planner_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        normalized = _normalize_text(query)
        active_setup, stale_notice = self._load_active_assistant_setup(thread_id=thread_id, actor=actor)
        if active_setup:
            if self._assistant_should_override_active_setup(active_setup, query=query, planner_hint=planner_hint):
                self.repo.complete_assistant_setup(
                    self.settings.office_id,
                    int(active_setup["id"]),
                    status="cancelled",
                    metadata={
                        **dict(active_setup.get("metadata") or {}),
                        "cancelled_by": actor,
                        "cancelled_reason": "superseded_by_new_setup",
                        "superseded_at": _utcnow_iso(),
                    },
                )
                if self._is_assistant_integration_intent(normalized):
                    return self._start_assistant_setup(thread_id=thread_id, query=query, actor=actor, planner_hint=planner_hint)
            continued_setup = {**dict(active_setup), "_planner_hint": dict(planner_hint or {})}
            return self._continue_assistant_setup(continued_setup, query=query, actor=actor)
        if stale_notice and any(token in normalized for token in ("baglandim", "durumu kontrol et", "devam", "resume")):
            return stale_notice
        if not self._is_assistant_integration_intent(normalized) and not self._assistant_requested_connector_hint(query, planner_hint=planner_hint):
            return None
        return self._start_assistant_setup(thread_id=thread_id, query=query, actor=actor, planner_hint=planner_hint)

    def _assistant_should_override_active_setup(
        self,
        setup: dict[str, Any],
        *,
        query: str,
        planner_hint: dict[str, Any] | None = None,
    ) -> bool:
        followup_intent = str((planner_hint or {}).get("followup_intent") or "").strip().lower()
        if followup_intent == "switch_setup":
            requested_connector_id = self._assistant_requested_connector_hint(query, planner_hint=planner_hint)
            active_connector_id = str(setup.get("connector_id") or "").strip().lower()
            return bool(active_connector_id and requested_connector_id and requested_connector_id != active_connector_id)
        if followup_intent in {"explain_current", "provide_value", "status_check", "execute_desktop_action", "cancel"}:
            return False
        normalized = _normalize_text(query)
        if not self._is_assistant_integration_intent(normalized) and not self._assistant_requested_connector_hint(query, planner_hint=planner_hint):
            return False
        if any(token in normalized for token in ("baglandim", "durumu kontrol et", "devam", "resume")):
            return False
        requested_connector_id = self._assistant_requested_connector_hint(query, planner_hint=planner_hint)
        if not requested_connector_id:
            return False
        active_connector_id = str(setup.get("connector_id") or "").strip().lower()
        return bool(active_connector_id and requested_connector_id != active_connector_id)

    def _load_active_assistant_setup(
        self,
        *,
        thread_id: int,
        actor: str | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        setup = self.repo.get_active_assistant_setup(self.settings.office_id, thread_id)
        if not setup:
            return None, None
        if not self._assistant_setup_is_stale(setup):
            return setup, None
        return None, self._expire_stale_assistant_setup(setup, actor=actor)

    def _assistant_setup_is_stale(self, setup: dict[str, Any]) -> bool:
        timeout_minutes = max(30, int(getattr(self.settings, "integration_assistant_setup_timeout_minutes", 720) or 720))
        status = str(setup.get("status") or "")
        if status in {"completed", "cancelled", "failed", "abandoned", "expired"}:
            return False
        if status == "oauth_pending":
            connection_id = int(setup.get("connection_id") or 0)
            if connection_id > 0:
                connection = self._optional_connection(connection_id)
                if connection and str(connection.get("auth_status") or "") == "authenticated":
                    return False
        updated_at = _parse_optional_iso(str(setup.get("updated_at") or ""))
        if not updated_at:
            return False
        return (datetime.now(timezone.utc) - updated_at).total_seconds() >= timeout_minutes * 60

    def _expire_stale_assistant_setup(self, setup: dict[str, Any], *, actor: str | None = None) -> dict[str, Any]:
        metadata = dict(setup.get("metadata") or {})
        expired = self.repo.complete_assistant_setup(
            self.settings.office_id,
            int(setup["id"]),
            status="abandoned",
            metadata={
                **metadata,
                "abandoned_reason": "stale_timeout",
                "abandoned_at": _utcnow_iso(),
            },
        )
        connector_id = str(setup.get("connector_id") or "")
        service_name = str(setup.get("service_name") or connector_id or "Bu baglanti")
        deep_link_path = metadata.get("deep_link_path")
        self._log_event(
            event_type="assistant_setup_abandoned",
            severity="warning",
            message="Yarim kalan entegrasyon kurulumu zaman asimina ugradi.",
            connector_id=connector_id or None,
            connection_id=int(setup.get("connection_id") or 0) or None,
            actor=actor or "system",
            data={"setup_id": setup.get("id"), "thread_id": setup.get("thread_id")},
        )
        return {
            "content": f"{service_name} icin onceki kurulum cok uzun sure yarim kaldigi icin kapatildi. Istersen yeniden baslayabilirim.",
            "status": "abandoned",
            "connector": self._require_connector(connector_id).model_dump(mode="json") if connector_id and connector_id in self._effective_catalog() else None,
            "connection": self._serialize_connection(self._optional_connection(int(setup.get('connection_id') or 0))) if setup.get("connection_id") else None,
            "generated_request": self._serialize_generated_connector(self.repo.get_generated_connector(self.settings.office_id, connector_id)) if connector_id else None,
            "assistant_setup": self._serialize_assistant_setup(expired),
            "authorization_url": None,
            "deep_link_path": deep_link_path,
            "suggested_replies": [f"{service_name} bağla", "Vazgeç"],
            "generated_from": "assistant_integration_orchestration",
        }

    def ingest_webhook(self, connector_id: str, *, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        spec = self._require_connector(connector_id)
        if not bool(spec.webhook_support.supported):
            raise ValueError("integration_webhook_not_supported")
        connections = [item for item in self.repo.list_connections(self.settings.office_id, connector_id=connector_id) if bool(item.get("enabled"))]
        if not connections:
            raise ValueError("integration_connection_not_found")
        last_error: str | None = None
        for connection in connections:
            secrets_payload = self._secrets_for_connection(connection)
            try:
                result = self.runtime.handle_webhook(
                    spec=spec,
                    connection=connection,
                    secrets=secrets_payload,
                    headers={str(key).lower(): str(value) for key, value in headers.items()},
                    body=body,
                )
            except IntegrationRuntimeError as exc:
                last_error = str(exc)
                continue
            event_row = self.repo.record_webhook_event(
                self.settings.office_id,
                connector_id=connector_id,
                connection_id=int(connection["id"]),
                event_id=str(result.get("event_id") or hashlib.sha256(body).hexdigest()),
                event_type=str(result.get("event_type") or "webhook"),
                status="received",
                payload=json.loads(body.decode("utf-8") or "{}"),
                request_signature=str(headers.get(spec.webhook_support.signature_header or "") or headers.get((spec.webhook_support.signature_header or "").lower()) or "") or None,
                request_timestamp=str(headers.get("X-Slack-Request-Timestamp") or headers.get("x-slack-request-timestamp") or "") or None,
            )
            if bool(event_row.get("duplicate")):
                return {
                    "connection": self._serialize_connection(connection),
                    "connector": spec.model_dump(mode="json"),
                    "webhook_event": event_row,
                    "message": "Webhook eventi zaten kuyruga alindi veya daha once islendi.",
                    "response": event_row.get("response") or {"ok": True},
                    "generated_from": "integration_webhook_ingest",
                }
            if str(event_row.get("status") or "") in {"processed", "challenge"} and event_row.get("processed_at"):
                return {
                    "connection": self._serialize_connection(connection),
                    "connector": spec.model_dump(mode="json"),
                    "webhook_event": event_row,
                    "message": "Webhook eventi daha once islenmis.",
                    "response": event_row.get("response") or {"ok": True},
                    "generated_from": "integration_webhook_ingest",
                }
            synced_at = _utcnow_iso()
            records = list(result.get("records") or [])
            for record in records:
                self.repo.upsert_record(
                    self.settings.office_id,
                    connection_id=int(connection["id"]),
                    record_type=str(record["record_type"]),
                    external_id=str(record["external_id"]),
                    title=str(record.get("title") or ""),
                    text_content=str(record.get("text_content") or ""),
                    content_hash=str(record.get("content_hash") or ""),
                    source_url=str(record.get("source_url") or "") or None,
                    permissions=record.get("permissions"),
                    tags=record.get("tags"),
                    raw=record.get("raw"),
                    normalized=record.get("normalized"),
                    synced_at=synced_at,
                )
            if records:
                resources = normalize_records_to_resources(
                    spec=spec,
                    connection=connection,
                    records=records,
                    synced_at=synced_at,
                )
                for resource in resources:
                    self.repo.upsert_resource(
                        self.settings.office_id,
                        connection_id=int(connection["id"]),
                        resource_kind=str(resource["resource_kind"]),
                        external_id=str(resource["external_id"]),
                        source_record_type=str(resource["source_record_type"]),
                        title=str(resource.get("title") or ""),
                        body_text=str(resource.get("body_text") or ""),
                        search_text=str(resource.get("search_text") or ""),
                        source_url=str(resource.get("source_url") or "") or None,
                        parent_external_id=str(resource.get("parent_external_id") or "") or None,
                        owner_label=str(resource.get("owner_label") or "") or None,
                        occurred_at=str(resource.get("occurred_at") or "") or None,
                        modified_at=str(resource.get("modified_at") or "") or None,
                        checksum=str(resource.get("checksum") or "") or None,
                        permissions=resource.get("permissions"),
                        tags=resource.get("tags"),
                        attributes=resource.get("attributes"),
                        sync_metadata=resource.get("sync_metadata"),
                        synced_at=synced_at,
                    )
            finished_event = self.repo.finish_webhook_event(
                self.settings.office_id,
                int(event_row["id"]),
                status=str(result.get("status") or "processed"),
                response=dict(result.get("response") or {"ok": True}),
            )
            self.repo.update_connection_runtime(
                self.settings.office_id,
                int(connection["id"]),
                last_sync_at=synced_at,
                sync_status="completed" if records else str(connection.get("sync_status") or "idle"),
                sync_status_message="Webhook eventi basariyla islendi.",
                last_error=None,
            )
            self._log_event(
                event_type="webhook_processed",
                message=str(result.get("message") or "Webhook eventi islendi."),
                connector_id=connector_id,
                connection_id=int(connection["id"]),
                actor="webhook",
                data={"event_id": finished_event.get("event_id"), "event_type": finished_event.get("event_type"), "record_count": len(records)},
            )
            return {
                "connection": self._serialize_connection(connection),
                "connector": spec.model_dump(mode="json"),
                "webhook_event": finished_event,
                "response": result.get("response") or {"ok": True},
                "message": str(result.get("message") or "Webhook eventi islendi."),
                "generated_from": "integration_webhook_ingest",
            }
        raise ValueError(last_error or "integration_webhook_signature_invalid")

    def get_connection_detail(self, connection_id: int) -> dict[str, Any]:
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        return {
            "connection": self._serialize_connection(connection),
            "connector": spec.model_dump(mode="json"),
            "skill": self._connector_skill_summary(spec),
            "capabilities": discover_capabilities(connection, spec),
            "safety_settings": build_safety_settings(connection, spec),
            "sync_runs": self.repo.list_sync_runs(self.settings.office_id, connection_id, limit=12),
            "record_preview": self.repo.list_records(self.settings.office_id, connection_id, limit=12),
            "resource_preview": self.repo.list_resources(self.settings.office_id, connection_id, limit=12),
            "action_runs": self.repo.list_action_runs(self.settings.office_id, connection_id, limit=12),
            "event_preview": self.repo.list_events(self.settings.office_id, connection_id=connection_id, limit=20),
            "webhook_preview": self.repo.list_webhook_events(self.settings.office_id, connection_id=connection_id, limit=20),
            "oauth_sessions": self.repo.list_oauth_sessions(self.settings.office_id, connection_id, limit=12),
            "security": self.security_posture(),
            "generated_from": "integration_platform_detail",
        }

    def assistant_skill_inventory(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for connection in self.repo.list_connections(self.settings.office_id):
            connector_id = str(connection.get("connector_id") or "")
            spec = self._effective_catalog().get(connector_id)
            if not spec:
                continue
            capabilities = discover_capabilities(connection, spec)
            skill = self._connector_skill_summary(spec) or {}
            items.append(
                {
                    **skill,
                    "connection_id": int(connection.get("id") or 0),
                    "display_name": connection.get("display_name"),
                    "enabled": bool(connection.get("enabled")),
                    "status": connection.get("status"),
                    "auth_status": connection.get("auth_status"),
                    "health_status": connection.get("health_status"),
                    "allowed_actions": [item.get("key") for item in capabilities.get("allowed_actions") or []][:16],
                    "blocked_actions": [item.get("key") for item in capabilities.get("blocked_actions") or []][:16],
                }
            )
        return items

    def preview_connection(self, payload: IntegrationConnectionPayload) -> dict[str, Any]:
        self._assert_generated_connector_usage_allowed(payload.connector_id, mock_mode=payload.mock_mode)
        spec = self._require_connector(payload.connector_id)
        display_name = payload.display_name or spec.name
        config = self._normalize_payload_dict(payload.config, limit=24)
        secrets_payload = self._normalize_payload_dict(payload.secrets, limit=24)
        requested_scopes = self._resolve_scopes(spec, payload.scopes)
        validation = self._validate_connection_payload(
            spec,
            config=config,
            secrets=secrets_payload,
            access_level=payload.access_level,
            mock_mode=payload.mock_mode,
            requested_scopes=requested_scopes,
        )
        return {
            "connector": spec.model_dump(mode="json"),
            "display_name": display_name,
            "normalized": {
                "config": validation["config"],
                "scopes": validation["scopes"],
                "access_level": validation["access_level"],
                "mock_mode": payload.mock_mode,
            },
            "validation": validation,
            "security": self.security_posture(),
            "generated_from": "integration_connection_preview",
        }

    def save_connection(self, payload: IntegrationConnectionPayload, *, actor: str) -> dict[str, Any]:
        generated_row = self._assert_generated_connector_usage_allowed(payload.connector_id, mock_mode=payload.mock_mode)
        spec = self._require_connector(payload.connector_id)
        if spec.management_mode == "legacy-desktop":
            raise ValueError("legacy_connector_managed_by_desktop")

        existing = self._optional_connection(payload.connection_id)
        existing_secrets = self._secrets_for_connection(existing) if existing else {}
        incoming_secrets = self._normalize_payload_dict(payload.secrets, limit=24)
        merged_secrets = self._merge_secret_payload(existing_secrets, incoming_secrets)
        requested_scopes = self._resolve_scopes(spec, payload.scopes or (existing.get("scopes") if existing else []))
        validation = self._validate_connection_payload(
            spec,
            config=self._normalize_payload_dict(payload.config, limit=24),
            secrets=merged_secrets,
            access_level=payload.access_level,
            mock_mode=payload.mock_mode,
            requested_scopes=requested_scopes,
        )
        if validation["status"] not in {"valid", "dry_run", "legacy-desktop", "authorization_required"}:
            raise ValueError(str(validation.get("message") or "integration_validation_failed"))

        auth_summary = self._build_connection_auth_summary(
            spec,
            requested_scopes=requested_scopes,
            secrets=merged_secrets,
            existing_summary=dict(existing.get("auth_summary") or {}) if existing else None,
        )
        auth_status = auth_status_from_summary(auth_summary)
        auth_summary["status"] = auth_status
        health_status, health_message = self._health_for_connection(validation=validation, auth_status=auth_status)
        status = self._status_for_connection(spec, validation_status=str(validation["status"]), auth_status=auth_status)
        display_name = payload.display_name or spec.name
        existing_metadata = dict(existing.get("metadata") or {}) if existing else {}
        metadata = {
            **existing_metadata,
            "warnings": list(validation.get("warnings") or []),
            "secret_keys": list(validation.get("secret_keys") or []),
            "ui_schema_version": 2,
            "safety_settings": existing_metadata.get("safety_settings") or build_safety_settings(
                {"access_level": payload.access_level, "metadata": existing_metadata},
                spec,
            ),
        }
        if generated_row:
            metadata["generated_connector"] = {
                "status": generated_row.get("status"),
                "live_use_enabled": self._generated_live_use_allowed(generated_row),
            }
        saved = self.repo.upsert_connection(
            self.settings.office_id,
            connector_id=spec.id,
            display_name=str(display_name),
            status=status,
            auth_type=spec.auth_type,
            access_level=str(validation["access_level"]),
            management_mode=spec.management_mode,
            enabled=bool(payload.enabled),
            mock_mode=bool(payload.mock_mode),
            scopes=list(validation["scopes"]),
            config=dict(validation["config"]),
            secret_blob=self.secret_box.seal_json(merged_secrets),
            health_status=health_status,
            health_message=health_message,
            auth_status=auth_status,
            auth_summary=auth_summary,
            credential_expires_at=auth_summary.get("expires_at"),
            credential_refreshed_at=auth_summary.get("last_refreshed_at"),
            credential_revoked_at=auth_summary.get("last_revoked_at"),
            last_health_check_at=None,
            last_validated_at=_utcnow_iso(),
            last_sync_at=existing.get("last_sync_at") if existing else None,
            last_error=None if health_status in {"valid", "pending"} else health_message,
            sync_status=str(existing.get("sync_status") or "idle") if existing else "idle",
            sync_status_message=existing.get("sync_status_message") if existing else None,
            cursor=dict(existing.get("cursor") or {}) if existing else {},
            metadata=metadata,
            created_by=actor,
            connection_id=payload.connection_id,
        )
        self._log_event(
            event_type="connection_saved",
            message="Entegrasyon baglantisi kaydedildi.",
            connector_id=spec.id,
            connection_id=int(saved["id"]),
            actor=actor,
            data={"auth_status": auth_status, "status": status, "scopes": requested_scopes},
        )
        return {
            "connection": self._serialize_connection(saved),
            "connector": spec.model_dump(mode="json"),
            "message": self._save_message_for_status(auth_status),
            "generated_from": "integration_connection_upsert",
        }

    def start_oauth_authorization(
        self,
        connection_id: int,
        payload: IntegrationOAuthStartRequest,
        *,
        actor: str,
    ) -> dict[str, Any]:
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        self._ensure_platform_connector(spec)
        self._ensure_oauth_connector(spec)

        redirect_uri = self._validate_redirect_uri(
            payload.redirect_uri or str(connection.get("config", {}).get("redirect_uri") or "")
        )
        requested_scopes = self._resolve_scopes(spec, payload.requested_scopes or list(connection.get("scopes") or []))
        existing_secrets = self._secrets_for_connection(connection)
        if self._field_required(spec, "client_secret") and not str(existing_secrets.get("client_secret") or "").strip():
            raise ValueError("oauth_client_secret_missing")

        state = generate_state_token()
        verifier = generate_pkce_verifier()
        authorization_url = build_authorization_url(
            spec=spec,
            connection=connection,
            state=state,
            verifier=verifier,
            redirect_uri=redirect_uri,
            requested_scopes=requested_scopes,
        )
        session = self.repo.create_oauth_session(
            self.settings.office_id,
            connection_id=connection_id,
            connector_id=spec.id,
            state=state,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            requested_scopes=requested_scopes,
            authorization_url=authorization_url,
            status="pending",
            created_by=actor,
            metadata={"connector_id": spec.id},
        )
        auth_summary = build_auth_summary(
            spec=spec,
            status="authorization_pending",
            requested_scopes=requested_scopes,
            permission_summary=summarize_scope_permissions(requested_scopes),
        )
        updated = self.repo.update_connection_runtime(
            self.settings.office_id,
            connection_id,
            status="configured",
            auth_status="authorization_pending",
            auth_summary=auth_summary,
            health_status="pending",
            health_message="OAuth yetkilendirmesi baslatildi.",
            last_health_check_at=_utcnow_iso(),
            last_error=None,
        )
        self._log_event(
            event_type="oauth_authorization_started",
            message="OAuth yetkilendirmesi baslatildi.",
            connector_id=spec.id,
            connection_id=connection_id,
            actor=actor,
            data={"scopes": requested_scopes, "redirect_uri": redirect_uri},
        )
        return {
            "connection": self._serialize_connection(updated),
            "connector": spec.model_dump(mode="json"),
            "oauth_session": session,
            "authorization_url": authorization_url,
            "message": "OAuth yetkilendirme adresi hazirlandi.",
            "generated_from": "integration_oauth_start",
        }

    def complete_oauth_callback(self, payload: IntegrationOAuthCallbackRequest, *, actor: str | None = None) -> dict[str, Any]:
        session = self.repo.get_oauth_session_by_state(self.settings.office_id, payload.state)
        if not session:
            raise ValueError("integration_oauth_session_not_found")
        connection_id = int(session["connection_id"])
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(session.get("connector_id") or connection.get("connector_id") or ""))
        self._ensure_oauth_connector(spec)
        session_status = str(session.get("status") or "").strip().lower()

        if session_status == "completed":
            self._log_event(
                event_type="oauth_callback_duplicate",
                severity="warning",
                message="OAuth callback tekrar geldi; mevcut baglanti durumu korundu.",
                connector_id=spec.id,
                connection_id=connection_id,
                actor=actor,
                data={"state": payload.state},
            )
            return {
                "connection": self._serialize_connection(connection),
                "connector": spec.model_dump(mode="json"),
                "oauth_session": session,
                "message": "OAuth callback daha once tamamlanmisti. Mevcut baglanti kullaniliyor.",
                "generated_from": "integration_oauth_callback",
            }
        if session_status in {"error", "revoked", "cancelled"}:
            self._log_event(
                event_type="oauth_callback_ignored",
                severity="warning",
                message="Tamamlanmamis OAuth oturumu tekrar callback almaya calisti.",
                connector_id=spec.id,
                connection_id=connection_id,
                actor=actor,
                data={"state": payload.state, "session_status": session_status},
            )
            raise ValueError("integration_oauth_session_not_pending")

        if payload.error:
            self.repo.finish_oauth_session(
                self.settings.office_id,
                payload.state,
                status="error",
                error=payload.error,
                metadata={"error": payload.error},
            )
            updated = self.repo.update_connection_runtime(
                self.settings.office_id,
                connection_id,
                status="degraded",
                auth_status="error",
                auth_summary=build_auth_summary(
                    spec=spec,
                    status="error",
                    requested_scopes=list(session.get("requested_scopes") or []),
                    permission_summary=summarize_scope_permissions(list(session.get("requested_scopes") or [])),
                ),
                health_status="invalid",
                health_message=payload.error,
                last_health_check_at=_utcnow_iso(),
                last_error=payload.error,
            )
            self._log_event(
                event_type="oauth_callback_failed",
                severity="error",
                message=payload.error,
                connector_id=spec.id,
                connection_id=connection_id,
                actor=actor,
                data={"state": payload.state},
            )
            raise ValueError(payload.error)

        if not payload.code:
            raise ValueError("oauth_authorization_code_missing")
        existing_secrets = self._secrets_for_connection(connection)
        try:
            token_bundle = exchange_authorization_code(
                spec=spec,
                connection=connection,
                session=session,
                code=payload.code,
                client_secret=str(existing_secrets.get("client_secret") or ""),
                transport=self.runtime.transport,
                timeout_seconds=float(getattr(self.settings, "connector_http_timeout_seconds", 20)),
            )
        except ValueError as exc:
            self.repo.finish_oauth_session(
                self.settings.office_id,
                payload.state,
                status="error",
                error=str(exc),
                metadata={"state": payload.state},
            )
            raise
        merged_secrets = self._apply_oauth_token_bundle(existing_secrets, token_bundle)
        auth_summary = build_auth_summary(
            spec=spec,
            status="authenticated",
            requested_scopes=list(session.get("requested_scopes") or []),
            granted_scopes=list(token_bundle.get("scope") or []),
            expires_at=str(token_bundle.get("expires_at") or ""),
            refresh_token_present=bool(token_bundle.get("refresh_token")),
            last_refreshed_at=str(token_bundle.get("issued_at") or ""),
            permission_summary=summarize_scope_permissions(list(token_bundle.get("scope") or [])),
        )
        completed_session = self.repo.finish_oauth_session(
            self.settings.office_id,
            payload.state,
            status="completed",
            metadata={"granted_scopes": list(token_bundle.get("scope") or [])},
        )
        updated = self.repo.update_connection_runtime(
            self.settings.office_id,
            connection_id,
            status="connected",
            enabled=True,
            auth_status="authenticated",
            auth_summary=auth_summary,
            credential_expires_at=auth_summary.get("expires_at"),
            credential_refreshed_at=auth_summary.get("last_refreshed_at"),
            health_status="valid",
            health_message="OAuth yetkilendirmesi tamamlandi.",
            last_health_check_at=_utcnow_iso(),
            last_validated_at=_utcnow_iso(),
            last_error=None,
            secret_blob=self.secret_box.seal_json(merged_secrets),
        )
        self._log_event(
            event_type="oauth_callback_completed",
            message="OAuth yetkilendirmesi tamamlandi.",
            connector_id=spec.id,
            connection_id=connection_id,
            actor=actor,
            data={"granted_scopes": list(token_bundle.get("scope") or [])},
        )
        return {
            "connection": self._serialize_connection(updated),
            "connector": spec.model_dump(mode="json"),
            "oauth_session": completed_session,
            "message": "OAuth callback basariyla tamamlandi.",
            "generated_from": "integration_oauth_callback",
        }

    def refresh_connection_credentials(self, connection_id: int, *, actor: str) -> dict[str, Any]:
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        self._ensure_platform_connector(spec)
        self._ensure_oauth_connector(spec)
        if not spec.auth_config.supports_refresh:
            raise ValueError("integration_refresh_not_supported")

        existing_secrets = self._secrets_for_connection(connection)
        refresh_token = str(existing_secrets.get("oauth_refresh_token") or existing_secrets.get("refresh_token") or "").strip()
        if not refresh_token:
            raise ValueError("oauth_refresh_token_missing")
        token_bundle = refresh_access_token(
            spec=spec,
            connection=connection,
            refresh_token=refresh_token,
            client_secret=str(existing_secrets.get("client_secret") or ""),
            transport=self.runtime.transport,
            timeout_seconds=float(getattr(self.settings, "connector_http_timeout_seconds", 20)),
        )
        merged_secrets = self._apply_oauth_token_bundle(existing_secrets, token_bundle)
        auth_summary = build_auth_summary(
            spec=spec,
            status="authenticated",
            requested_scopes=list(connection.get("scopes") or []),
            granted_scopes=list(token_bundle.get("scope") or []),
            expires_at=str(token_bundle.get("expires_at") or ""),
            refresh_token_present=bool(token_bundle.get("refresh_token")),
            last_refreshed_at=str(token_bundle.get("issued_at") or ""),
            permission_summary=summarize_scope_permissions(list(token_bundle.get("scope") or [])),
        )
        updated = self.repo.update_connection_runtime(
            self.settings.office_id,
            connection_id,
            status="connected",
            enabled=True,
            auth_status="authenticated",
            auth_summary=auth_summary,
            credential_expires_at=auth_summary.get("expires_at"),
            credential_refreshed_at=auth_summary.get("last_refreshed_at"),
            health_status="valid",
            health_message="Kimlik bilgileri yenilendi.",
            last_health_check_at=_utcnow_iso(),
            last_validated_at=_utcnow_iso(),
            last_error=None,
            secret_blob=self.secret_box.seal_json(merged_secrets),
        )
        self._log_event(
            event_type="credentials_refreshed",
            message="Kimlik bilgileri yenilendi.",
            connector_id=spec.id,
            connection_id=connection_id,
            actor=actor,
            data={"expires_at": auth_summary.get("expires_at")},
        )
        return {
            "connection": self._serialize_connection(updated),
            "connector": spec.model_dump(mode="json"),
            "message": "Kimlik bilgileri yenilendi.",
            "generated_from": "integration_credentials_refresh",
        }

    def revoke_connection(self, connection_id: int, *, actor: str) -> dict[str, Any]:
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        self._ensure_platform_connector(spec)
        existing_secrets = self._secrets_for_connection(connection)
        if spec.auth_type == "oauth2":
            access_token = str(existing_secrets.get("oauth_access_token") or existing_secrets.get("access_token") or "").strip()
            if access_token:
                try:
                    revoke_access_token(
                        spec=spec,
                        connection=connection,
                        token=access_token,
                        client_secret=str(existing_secrets.get("client_secret") or ""),
                        transport=self.runtime.transport,
                        timeout_seconds=float(getattr(self.settings, "connector_http_timeout_seconds", 20)),
                    )
                except ValueError:
                    pass
            secrets_payload = self._strip_oauth_runtime_secrets(existing_secrets)
        else:
            secrets_payload = {}
        auth_summary = build_auth_summary(
            spec=spec,
            status="revoked",
            requested_scopes=list(connection.get("scopes") or []),
            refresh_token_present=False,
            last_revoked_at=_utcnow_iso(),
            permission_summary=summarize_scope_permissions(list(connection.get("scopes") or [])),
        )
        updated = self.repo.update_connection_runtime(
            self.settings.office_id,
            connection_id,
            status="revoked",
            enabled=False,
            auth_status="revoked",
            auth_summary=auth_summary,
            credential_revoked_at=auth_summary.get("last_revoked_at"),
            health_status="revoked",
            health_message="Kimlik bilgileri iptal edildi.",
            last_health_check_at=_utcnow_iso(),
            last_error=None,
            secret_blob=self.secret_box.seal_json(secrets_payload),
            sync_status="idle",
            sync_status_message="Baglanti iptal edildi.",
        )
        self._log_event(
            event_type="connection_revoked",
            message="Kimlik bilgileri iptal edildi.",
            connector_id=spec.id,
            connection_id=connection_id,
            actor=actor,
            data={"auth_type": spec.auth_type},
        )
        return {
            "connection": self._serialize_connection(updated),
            "connector": spec.model_dump(mode="json"),
            "message": "Kimlik bilgileri iptal edildi.",
            "generated_from": "integration_revoke",
        }

    def disconnect_connection(self, connection_id: int, *, actor: str | None = None) -> dict[str, Any]:
        connection = self._require_connection(connection_id)
        updated = self.repo.update_connection_runtime(
            self.settings.office_id,
            connection_id,
            status="disconnected",
            enabled=False,
            health_status="revoked",
            health_message="Baglanti duraklatildi.",
            last_error=None,
            sync_status="idle",
            sync_status_message="Baglanti duraklatildigi icin sync islemleri beklemede.",
        )
        self._log_event(
            event_type="connection_disconnected",
            message="Baglanti duraklatildi.",
            connector_id=str(connection.get("connector_id") or ""),
            connection_id=connection_id,
            actor=actor,
        )
        return {
            "connection": self._serialize_connection(updated),
            "message": "Entegrasyon baglantisi duraklatildi.",
            "generated_from": "integration_disconnect",
        }

    def reconnect_connection(self, connection_id: int, *, actor: str) -> dict[str, Any]:
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        self._ensure_platform_connector(spec)
        validation = self._validate_connection_payload(
            spec,
            config=dict(connection.get("config") or {}),
            secrets=self._secrets_for_connection(connection),
            access_level=str(connection.get("access_level") or spec.default_access_level),
            mock_mode=bool(connection.get("mock_mode")),
            requested_scopes=list(connection.get("scopes") or self._resolve_scopes(spec, [])),
        )
        auth_summary = self._build_connection_auth_summary(
            spec,
            requested_scopes=list(connection.get("scopes") or []),
            secrets=self._secrets_for_connection(connection),
            existing_summary=dict(connection.get("auth_summary") or {}),
        )
        auth_status = auth_status_from_summary(auth_summary)
        if spec.auth_type == "oauth2" and auth_status == "revoked":
            auth_summary["status"] = "authorization_required"
            auth_status = "authorization_required"
        auth_summary["status"] = auth_status
        health_status, health_message = self._health_for_connection(validation=validation, auth_status=auth_status)
        updated = self.repo.update_connection_runtime(
            self.settings.office_id,
            connection_id,
            status=self._status_for_connection(spec, validation_status=str(validation["status"]), auth_status=auth_status),
            enabled=True,
            auth_status=auth_status,
            auth_summary=auth_summary,
            health_status=health_status,
            health_message=health_message,
            last_health_check_at=_utcnow_iso(),
            last_error=None if health_status in {"valid", "pending"} else health_message,
        )
        self._log_event(
            event_type="connection_reconnected",
            message="Baglanti yeniden etkinlestirildi.",
            connector_id=spec.id,
            connection_id=connection_id,
            actor=actor,
            data={"auth_status": auth_status},
        )
        return {
            "connection": self._serialize_connection(updated),
            "connector": spec.model_dump(mode="json"),
            "message": "Baglanti yeniden etkinlestirildi.",
            "generated_from": "integration_reconnect",
        }

    def validate_connection(self, connection_id: int) -> dict[str, Any]:
        return self._refresh_connection_state(connection_id, generated_from="integration_connection_validate", audit_reason="connection_validated")

    def health_check_connection(self, connection_id: int, *, actor: str | None = None) -> dict[str, Any]:
        return self._refresh_connection_state(
            connection_id,
            generated_from="integration_connection_health",
            audit_reason="connection_health_checked",
            actor=actor,
        )

    def update_safety_settings(
        self,
        connection_id: int,
        payload: IntegrationSafetySettingsRequest,
        *,
        actor: str,
    ) -> dict[str, Any]:
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        current_metadata = dict(connection.get("metadata") or {})
        settings_payload = build_safety_settings(connection, spec)
        for field_name, value in payload.model_dump(mode="python").items():
            if value is None:
                continue
            settings_payload[field_name] = bool(value)
        updated = self.repo.update_connection_runtime(
            self.settings.office_id,
            connection_id,
            metadata={**current_metadata, "safety_settings": settings_payload},
        )
        self._log_event(
            event_type="safety_settings_updated",
            message="Guvenlik ayarlari guncellendi.",
            connector_id=spec.id,
            connection_id=connection_id,
            actor=actor,
            data=settings_payload,
        )
        return {
            "connection": self._serialize_connection(updated),
            "connector": spec.model_dump(mode="json"),
            "safety_settings": settings_payload,
            "message": "Guvenlik ayarlari kaydedildi.",
            "generated_from": "integration_safety_settings",
        }

    def schedule_sync(
        self,
        connection_id: int,
        payload: IntegrationSyncScheduleRequest,
        *,
        actor: str,
    ) -> dict[str, Any]:
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        if spec.management_mode == "legacy-desktop":
            return {
                "connection": self._serialize_connection(connection),
                "connector": spec.model_dump(mode="json"),
                "message": spec.setup_hint or "Legacy entegrasyon masaustu akisi uzerinden senkronize edilir.",
                "generated_from": "integration_sync_legacy_redirect",
            }
        if not bool(connection.get("enabled")) and not payload.force:
            raise ValueError("integration_connection_disabled")

        active = self.repo.get_active_sync_run(self.settings.office_id, connection_id)
        if active and not payload.force:
            updated = self.repo.update_connection_runtime(
                self.settings.office_id,
                connection_id,
                sync_status=str(active.get("status") or "queued"),
                sync_status_message="Aktif bir sync isi zaten kuyrukta veya calisiyor.",
            )
            return {
                "connection": self._serialize_connection(updated),
                "connector": spec.model_dump(mode="json"),
                "sync_run": active,
                "record_count": 0,
                "message": "Aktif bir sync isi zaten kuyrukta veya calisiyor.",
                "generated_from": "integration_sync_schedule",
            }

        scheduled_for = _utcnow_iso()
        sync_run = self.repo.create_sync_run(
            self.settings.office_id,
            connection_id=connection_id,
            mode=payload.mode,
            status="queued",
            trigger_type=payload.trigger_type,
            requested_by=actor,
            run_key=f"{connection_id}:{payload.mode}",
            scheduled_for=scheduled_for,
            metadata={"connector_id": spec.id, "forced": payload.force},
        )
        updated = self.repo.update_connection_runtime(
            self.settings.office_id,
            connection_id,
            sync_status="queued",
            sync_status_message="Sync isi kuyruga alindi.",
            last_error=None,
        )
        self._log_event(
            event_type="sync_scheduled",
            message="Sync isi kuyruga alindi.",
            connector_id=spec.id,
            connection_id=connection_id,
            actor=actor,
            data={"mode": payload.mode, "trigger_type": payload.trigger_type, "run_now": payload.run_now},
        )
        if payload.run_now:
            dispatched = self._dispatch_due_sync_runs(limit=1, target_connection_id=connection_id, actor=actor)
            if dispatched:
                return dispatched[0]
        return {
            "connection": self._serialize_connection(updated),
            "connector": spec.model_dump(mode="json"),
            "sync_run": sync_run,
            "record_count": 0,
            "message": "Sync isi kuyruga alindi.",
            "generated_from": "integration_sync_schedule",
        }

    def sync_connection(self, connection_id: int, *, actor: str) -> dict[str, Any]:
        return self.schedule_sync(
            connection_id,
            IntegrationSyncScheduleRequest(mode="incremental", trigger_type="manual", run_now=True, force=False),
            actor=actor,
        )

    def dispatch_sync_jobs(self, payload: IntegrationJobDispatchRequest, *, actor: str) -> dict[str, Any]:
        items = self._dispatch_due_sync_runs(limit=payload.limit, actor=actor)
        return {
            "items": items,
            "count": len(items),
            "generated_from": "integration_sync_dispatcher",
        }

    def create_integration_request(self, payload: IntegrationAutomationRequest, *, actor: str) -> dict[str, Any]:
        seed = self._infer_request_seed(payload)
        connector_id = self._reserve_generated_connector_id(str(seed["service_name"]))
        existing_static = self.static_catalog.get(connector_id)
        if existing_static:
            return {
                "created": False,
                "connector": existing_static.model_dump(mode="json"),
                "generated_request": None,
                "scaffold": None,
                "message": f"{existing_static.name} zaten katalogda hazir.",
                "generated_from": "integration_automation_existing_connector",
            }

        scaffold = self.generate_scaffold(
            IntegrationScaffoldRequest(
                service_name=str(seed["service_name"]),
                docs_url=str(seed.get("docs_url") or "") or None,
                openapi_url=str(seed.get("openapi_url") or "") or None,
                openapi_spec=str(seed.get("openapi_spec") or "") or None,
                documentation_excerpt=str(seed.get("documentation_excerpt") or "") or None,
                category=str(seed.get("category") or "") or None,
                preferred_auth_type=str(seed.get("preferred_auth_type") or "") or None,
                notes=f"User request: {payload.prompt}",
            )
        )
        connector_payload = dict(scaffold.get("connector") or {})
        connector_payload["id"] = connector_id
        connector_payload["name"] = str(seed["service_name"])
        connector_payload["docs_url"] = str(seed.get("docs_url") or connector_payload.get("docs_url") or "") or None
        connector_payload["base_url"] = str(seed.get("base_url") or connector_payload.get("base_url") or "") or None
        connector_payload["scopes"] = list(seed.get("scopes") or connector_payload.get("scopes") or [])
        connector_payload["auth_config"] = {
            **dict(connector_payload.get("auth_config") or {}),
            **dict(seed.get("auth_config") or {}),
            "default_scopes": list(
                seed.get("scopes")
                or dict(connector_payload.get("auth_config") or {}).get("default_scopes")
                or connector_payload.get("scopes")
                or []
            ),
        }
        if seed.get("resources"):
            connector_payload["resources"] = list(seed.get("resources") or [])
        if seed.get("actions"):
            connector_payload["actions"] = list(seed.get("actions") or [])
        if seed.get("webhook_support"):
            connector_payload["webhook_support"] = dict(seed.get("webhook_support") or {})
        if connector_payload.get("base_url"):
            connector_payload["ui_schema"] = [
                {
                    **field,
                    "default": connector_payload["base_url"],
                }
                if field.get("key") == "base_url" and not field.get("default")
                else field
                for field in list(connector_payload.get("ui_schema") or [])
            ]
        if seed.get("extra_ui_fields"):
            existing_keys = {str(field.get("key") or "") for field in list(connector_payload.get("ui_schema") or [])}
            connector_payload["ui_schema"] = [
                *list(connector_payload.get("ui_schema") or []),
                *[field for field in list(seed.get("extra_ui_fields") or []) if str(field.get("key") or "") not in existing_keys],
            ]
        token_field_map = dict(connector_payload.get("auth_config") or {}).get("token_field_map") or {}
        if str(token_field_map.get("client_id") or "") == "client_key":
            connector_payload["ui_schema"] = [
                {
                    **field,
                    "label": "Client key",
                    "help_text": str(field.get("help_text") or "Saglayici panelindeki Client key degerini yaz."),
                }
                if str(field.get("key") or "") == "client_id"
                else field
                for field in list(connector_payload.get("ui_schema") or [])
            ]
        connector_payload["tags"] = self._dedupe_strings(
            [
                *(connector_payload.get("tags") or []),
                "generated-request",
                "assistant-created",
                "review-required",
            ]
        )
        connector_payload["setup_hint"] = (
            str(connector_payload.get("setup_hint") or "").strip()
            or "Asistan bu connector taslagini otomatik olusturdu. Kimlik bilgileri ve scope secimi kullanici arayuzunden tamamlanmalidir."
        )[:320]
        connector_payload["description"] = (
            str(connector_payload.get("description") or "").strip()
            or f"{seed['service_name']} icin kullanici isteginden otomatik uretilen connector taslagi."
        )[:600]
        draft_spec = ConnectorSpec.model_validate(connector_payload)
        default_resource_path = self._default_generated_resource_path(draft_spec)
        if default_resource_path:
            ui_schema = list(connector_payload.get("ui_schema") or [])
            resource_path_index = next((index for index, field in enumerate(ui_schema) if str(field.get("key") or "") == "resource_path"), None)
            if resource_path_index is None:
                ui_schema.append(
                    {
                        "key": "resource_path",
                        "label": "Kaynak yolu",
                        "kind": "text",
                        "target": "config",
                        "required": False,
                        "default": default_resource_path,
                        "help_text": "Saglayici saglik kontrolu ve varsayilan veri cekimi icin kullanilan temel endpoint yolu.",
                    }
                )
            elif not ui_schema[resource_path_index].get("default"):
                ui_schema[resource_path_index] = {
                    **dict(ui_schema[resource_path_index]),
                    "default": default_resource_path,
                }
            connector_payload["ui_schema"] = ui_schema
        spec = ConnectorSpec.model_validate(connector_payload)
        scaffold_payload = {
            **scaffold,
            "connector": spec.model_dump(mode="json"),
            "inference": {
                **dict(scaffold.get("inference") or {}),
                "connector_id": spec.id,
            },
        }
        readiness = self._generated_connector_readiness(seed=seed, scaffold=scaffold_payload, spec=spec)
        generated = self.repo.upsert_generated_connector(
            self.settings.office_id,
            connector_id=spec.id,
            service_name=spec.name,
            request_text=payload.prompt,
            status="draft_ready",
            docs_url=str(seed.get("docs_url") or "") or None,
            openapi_url=str(seed.get("openapi_url") or "") or None,
            openapi_spec=str(seed.get("openapi_spec") or "") or None,
            documentation_excerpt=str(seed.get("documentation_excerpt") or "") or None,
            spec=spec.model_dump(mode="json"),
            metadata={
                "review_gate": scaffold.get("review_gate") or {},
                "warnings": list(scaffold.get("warnings") or []),
                "seed": seed,
                "pattern_matches": list(seed.get("pattern_matches") or []),
                "fetch_summary": dict(scaffold.get("fetch_summary") or {}),
                "activation_mode": "catalog_visible",
                "skill": self._connector_skill_summary(spec),
                "readiness": readiness,
                "review": {
                    "status": "draft_ready",
                    "decision": "create",
                    "notes": "Otomatik baglayici olusturuldu; canli kullanim onayi bekleniyor.",
                    "reviewed_by": actor,
                    "reviewed_at": _utcnow_iso(),
                    "live_use_enabled": False,
                },
            },
            created_by=actor,
            enabled=True,
        )
        self._remember_connector_pattern(spec, source_kind="generated-draft", success_increment=0)
        self._log_event(
            event_type="generated_connector_created",
            message=f"{spec.name} icin otomatik connector taslagi olusturuldu.",
            connector_id=spec.id,
            connection_id=None,
            actor=actor,
            data={"status": generated.get("status"), "prompt": payload.prompt[:240]},
        )
        return {
            "created": True,
            "connector": spec.model_dump(mode="json"),
            "generated_request": self._serialize_generated_connector(generated),
            "scaffold": scaffold_payload,
            "message": self._generated_connector_created_message(spec=spec, readiness=readiness),
            "generated_from": "integration_automation_request",
        }

    def review_generated_connector(
        self,
        connector_id: str,
        payload: IntegrationGeneratedConnectorReviewRequest,
        *,
        actor: str,
    ) -> dict[str, Any]:
        row = self.repo.get_generated_connector(self.settings.office_id, connector_id)
        if not row:
            raise ValueError("integration_generated_connector_not_found")
        if payload.decision in {"reject", "archive"} and self.repo.list_connections(self.settings.office_id, connector_id=connector_id):
            raise ValueError("integration_generated_connector_has_connections")

        decision_to_status = {
            "approve": "approved",
            "reject": "rejected",
            "archive": "archived",
            "restore": "draft_ready",
        }
        next_status = decision_to_status[payload.decision]
        current_metadata = dict(row.get("metadata") or {})
        live_use_enabled = bool(payload.live_use_enabled) if payload.live_use_enabled is not None else payload.decision == "approve"
        if next_status != "approved":
            live_use_enabled = False
        review_state = {
            "decision": payload.decision,
            "status": next_status,
            "notes": payload.notes,
            "reviewed_by": actor,
            "reviewed_at": _utcnow_iso(),
            "live_use_enabled": live_use_enabled,
        }
        updated = self.repo.upsert_generated_connector(
            self.settings.office_id,
            connector_id=str(row.get("connector_id") or ""),
            service_name=str(row.get("service_name") or ""),
            request_text=str(row.get("request_text") or ""),
            status=next_status,
            docs_url=str(row.get("docs_url") or "") or None,
            openapi_url=str(row.get("openapi_url") or "") or None,
            openapi_spec=str(row.get("openapi_spec") or "") or None,
            documentation_excerpt=str(row.get("documentation_excerpt") or "") or None,
            spec=dict(row.get("spec") or {}),
            metadata={**current_metadata, "review": review_state},
            last_error=None,
            created_by=str(row.get("created_by") or actor),
            enabled=next_status not in {"archived", "rejected"},
        )
        spec = self._materialize_generated_connector(updated)
        decision_messages = {
            "approve": "Otomatik baglayici canli kullanim icin onaylandi.",
            "reject": "Otomatik baglayici reddedildi.",
            "archive": "Otomatik baglayici arsivlendi.",
            "restore": "Otomatik baglayici yeniden taslak durumuna alindi.",
        }
        self._log_event(
            event_type="generated_connector_reviewed",
            message=decision_messages[payload.decision],
            connector_id=connector_id,
            connection_id=None,
            actor=actor,
            data={"decision": payload.decision, "status": next_status, "live_use_enabled": live_use_enabled},
        )
        if payload.decision == "approve":
            materialized_spec = self._materialize_generated_connector(updated)
            if materialized_spec:
                self._remember_connector_pattern(materialized_spec, source_kind="review-approved", success_increment=1)
        return {
            "generated_request": self._serialize_generated_connector(updated),
            "connector": spec.model_dump(mode="json") if spec else None,
            "message": decision_messages[payload.decision],
            "generated_from": "integration_generated_connector_review",
        }

    def refresh_generated_connector(
        self,
        connector_id: str,
        payload: IntegrationGeneratedConnectorRefreshRequest,
        *,
        actor: str,
    ) -> dict[str, Any]:
        row = self.repo.get_generated_connector(self.settings.office_id, connector_id)
        if not row:
            raise ValueError("integration_generated_connector_not_found")
        if self.repo.list_connections(self.settings.office_id, connector_id=connector_id):
            raise ValueError("integration_generated_connector_has_connections")
        current_spec = self._materialize_generated_connector(row)
        if not current_spec:
            raise ValueError("integration_generated_connector_spec_invalid")
        scaffold = self.generate_scaffold(
            IntegrationScaffoldRequest(
                service_name=current_spec.name,
                docs_url=payload.docs_url or str(row.get("docs_url") or "") or current_spec.docs_url,
                openapi_url=payload.openapi_url or str(row.get("openapi_url") or "") or None,
                openapi_spec=payload.openapi_spec or str(row.get("openapi_spec") or "") or None,
                documentation_excerpt=payload.documentation_excerpt or str(row.get("documentation_excerpt") or "") or None,
                category=payload.category or current_spec.category,
                preferred_auth_type=payload.preferred_auth_type or current_spec.auth_type,
                notes=payload.notes or f"Regenerated by {actor}",
            )
        )
        connector_payload = dict(scaffold.get("connector") or {})
        connector_payload["id"] = current_spec.id
        connector_payload["name"] = current_spec.name
        connector_payload["tags"] = self._dedupe_strings([*(connector_payload.get("tags") or []), "regenerated"])
        regenerated_spec = ConnectorSpec.model_validate(connector_payload)
        metadata = dict(row.get("metadata") or {})
        metadata["warnings"] = list(scaffold.get("warnings") or [])
        metadata["fetch_summary"] = dict(scaffold.get("fetch_summary") or {})
        metadata["skill"] = self._connector_skill_summary(regenerated_spec)
        metadata["review"] = {
            "decision": "refresh",
            "status": "draft_ready",
            "notes": payload.notes or "Taslak yeniden uretildi; canli kullanim icin tekrar onay bekleniyor.",
            "reviewed_by": actor,
            "reviewed_at": _utcnow_iso(),
            "live_use_enabled": False,
        }
        updated = self.repo.upsert_generated_connector(
            self.settings.office_id,
            connector_id=regenerated_spec.id,
            service_name=regenerated_spec.name,
            request_text=str(row.get("request_text") or current_spec.name),
            status="draft_ready",
            docs_url=payload.docs_url or str(row.get("docs_url") or "") or current_spec.docs_url,
            openapi_url=payload.openapi_url or str(row.get("openapi_url") or "") or None,
            openapi_spec=payload.openapi_spec or str(row.get("openapi_spec") or "") or None,
            documentation_excerpt=payload.documentation_excerpt or str(row.get("documentation_excerpt") or "") or None,
            spec=regenerated_spec.model_dump(mode="json"),
            metadata=metadata,
            last_error=None,
            created_by=str(row.get("created_by") or actor),
            enabled=bool(row.get("enabled")),
        )
        self._remember_connector_pattern(regenerated_spec, source_kind="generated-refresh", success_increment=0)
        self._log_event(
            event_type="generated_connector_refreshed",
            message=f"{regenerated_spec.name} taslagi yeniden uretildi.",
            connector_id=regenerated_spec.id,
            connection_id=None,
            actor=actor,
            data={"version": updated.get("version"), "fetch_summary": scaffold.get("fetch_summary") or {}},
        )
        return {
            "generated_request": self._serialize_generated_connector(updated),
            "connector": regenerated_spec.model_dump(mode="json"),
            "message": "Otomatik baglayici taslagi yeniden uretildi ve yeniden inceleme kapisina alindi.",
            "generated_from": "integration_generated_connector_refresh",
        }

    def set_generated_connector_enabled(
        self,
        connector_id: str,
        payload: IntegrationGeneratedConnectorStateRequest,
        *,
        actor: str,
    ) -> dict[str, Any]:
        row = self.repo.get_generated_connector(self.settings.office_id, connector_id)
        if not row:
            raise ValueError("integration_generated_connector_not_found")
        if not payload.enabled and self.repo.list_connections(self.settings.office_id, connector_id=connector_id):
            raise ValueError("integration_generated_connector_has_connections")
        updated = self.repo.set_generated_connector_enabled(self.settings.office_id, connector_id, enabled=payload.enabled)
        if not updated:
            raise ValueError("integration_generated_connector_not_found")
        self._log_event(
            event_type="generated_connector_state_changed",
            message="Otomatik baglayici etkinlik durumu guncellendi.",
            connector_id=connector_id,
            connection_id=None,
            actor=actor,
            data={"enabled": payload.enabled, "notes": payload.notes},
        )
        materialized = self._materialize_generated_connector(updated)
        return {
            "generated_request": self._serialize_generated_connector(updated),
            "connector": materialized.model_dump(mode="json") if materialized else None,
            "message": "Connector katalog gorunurlugu guncellendi." if payload.enabled else "Connector katalogdan gizlendi.",
            "generated_from": "integration_generated_connector_state",
        }

    def delete_generated_connector(self, connector_id: str, *, actor: str) -> dict[str, Any]:
        row = self.repo.get_generated_connector(self.settings.office_id, connector_id)
        if not row:
            raise ValueError("integration_generated_connector_not_found")
        if self.repo.list_connections(self.settings.office_id, connector_id=connector_id):
            raise ValueError("integration_generated_connector_has_connections")
        deleted = self.repo.delete_generated_connector(self.settings.office_id, connector_id)
        if not deleted:
            raise ValueError("integration_generated_connector_not_found")
        self._log_event(
            event_type="generated_connector_deleted",
            message="Otomatik baglayici registry kaydindan silindi.",
            connector_id=connector_id,
            connection_id=None,
            actor=actor,
            data={"service_name": row.get("service_name")},
        )
        return {
            "deleted": True,
            "connector_id": connector_id,
            "message": "Otomatik baglayici kaydi silindi.",
            "generated_from": "integration_generated_connector_delete",
        }

    def list_connector_patterns(self) -> dict[str, Any]:
        return {
            "items": self.repo.list_connector_patterns(self.settings.office_id, limit=50),
            "generated_from": "integration_connector_pattern_memory",
        }

    def execute_action(self, connection_id: int, action_key: str, payload: IntegrationActionRequest, *, actor: str) -> dict[str, Any]:
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        action = next((item for item in spec.actions if item.key == action_key), None)
        if not action:
            raise ValueError("integration_action_not_found")

        policy_result = evaluate_action_policy(
            connection=connection,
            spec=spec,
            action=action,
            confirmed=bool(payload.confirmed),
        )
        status = "running"
        approval_state = "approved"
        if not policy_result["allowed"]:
            status = "requires_confirmation" if policy_result["requires_confirmation"] else "blocked"
            approval_state = "requires_confirmation" if policy_result["requires_confirmation"] else "blocked"

        action_run = self.repo.create_action_run(
            self.settings.office_id,
            connection_id=connection_id,
            action_key=action.key,
            operation=action.operation,
            status=status,
            requested_by=actor,
            approval_required=bool(policy_result["requires_confirmation"]),
            approval_state=approval_state,
            input_payload=self._normalize_payload_dict(payload.input, limit=24),
            policy_payload=policy_result,
        )
        if not policy_result["allowed"]:
            finished = self.repo.finish_action_run(
                self.settings.office_id,
                int(action_run["id"]),
                status=status,
                approval_state=approval_state,
                output_payload={"message": policy_result["reason"], "action_key": action.key},
            )
            self._log_event(
                event_type="action_blocked",
                severity="warning",
                message=policy_result["reason"],
                connector_id=spec.id,
                connection_id=connection_id,
                actor=actor,
                data={"action_key": action.key},
            )
            return {
                "action_run": finished,
                "connector": spec.model_dump(mode="json"),
                "connection": self._serialize_connection(connection),
                "message": policy_result["reason"],
                "generated_from": "integration_action_runner",
            }

        try:
            output = self._run_action(connection, spec, action, payload.input)
            finished = self.repo.finish_action_run(
                self.settings.office_id,
                int(action_run["id"]),
                status="completed",
                approval_state="approved",
                output_payload=output,
            )
            self._log_event(
                event_type="action_completed",
                message=f"{action.title} aksiyonu tamamlandi.",
                connector_id=spec.id,
                connection_id=connection_id,
                actor=actor,
                data={"action_key": action.key, "operation": action.operation},
            )
            return {
                "action_run": finished,
                "connector": spec.model_dump(mode="json"),
                "connection": self._serialize_connection(connection),
                "message": "Aksiyon tamamlandi.",
                "generated_from": "integration_action_runner",
            }
        except ValueError as exc:
            finished = self.repo.finish_action_run(
                self.settings.office_id,
                int(action_run["id"]),
                status="failed",
                approval_state="approved",
                output_payload={"message": str(exc)},
                error=str(exc),
            )
            self._log_event(
                event_type="action_failed",
                severity="error",
                message=str(exc),
                connector_id=spec.id,
                connection_id=connection_id,
                actor=actor,
                data={"action_key": action.key, "operation": action.operation},
            )
            return {
                "action_run": finished,
                "connector": spec.model_dump(mode="json"),
                "connection": self._serialize_connection(connection),
                "message": str(exc),
                "generated_from": "integration_action_runner",
            }

    def generate_scaffold(self, payload: IntegrationScaffoldRequest) -> dict[str, Any]:
        validation_warnings: list[str] = []
        for candidate_url in (payload.docs_url, payload.openapi_url):
            if not candidate_url:
                continue
            validation_warnings.extend(self._validate_remote_target(candidate_url))
        prepared_payload, enrichment = prepare_scaffold_request(
            payload,
            transport=self.http_transport,
            timeout_seconds=float(getattr(self.settings, "connector_http_timeout_seconds", 20)),
        )
        scaffold = generate_connector_scaffold(prepared_payload)
        scaffold["warnings"] = self._dedupe_strings(
            [
                *list(scaffold.get("warnings") or []),
                *validation_warnings,
                *list(enrichment.get("warnings") or []),
            ]
        )
        scaffold["fetch_summary"] = dict(enrichment.get("fetch_summary") or {})
        if scaffold.get("connector"):
            connector_payload = dict(scaffold["connector"])
            connector_payload["docs_url"] = prepared_payload.docs_url or prepared_payload.openapi_url or connector_payload.get("docs_url")
            scaffold["connector"] = connector_payload
        inference = dict(scaffold.get("inference") or {})
        inference["fetch_summary"] = dict(enrichment.get("fetch_summary") or {})
        scaffold["inference"] = inference
        return scaffold

    def _effective_catalog(self) -> dict[str, ConnectorSpec]:
        rows = self._list_active_generated_rows()
        return {**self.static_catalog, **self._generated_connector_specs(rows)}

    def _refresh_connection_state(
        self,
        connection_id: int,
        *,
        generated_from: str,
        audit_reason: str,
        actor: str | None = None,
    ) -> dict[str, Any]:
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        if spec.management_mode == "legacy-desktop":
            return {
                "connection": self._serialize_connection(connection),
                "connector": spec.model_dump(mode="json"),
                "validation": {
                    "status": "legacy-desktop",
                    "health_status": "external",
                    "message": spec.setup_hint or "Bu baglanti masaustu tarafindan yonetiliyor.",
                },
                "generated_from": generated_from,
            }

        secrets_payload = self._secrets_for_connection(connection)
        validation = self._validate_connection_payload(
            spec,
            config=dict(connection.get("config") or {}),
            secrets=secrets_payload,
            access_level=str(connection.get("access_level") or spec.default_access_level),
            mock_mode=bool(connection.get("mock_mode")),
            requested_scopes=list(connection.get("scopes") or self._resolve_scopes(spec, [])),
        )
        auth_summary = self._build_connection_auth_summary(
            spec,
            requested_scopes=list(connection.get("scopes") or []),
            secrets=secrets_payload,
            existing_summary=dict(connection.get("auth_summary") or {}),
        )
        auth_status = auth_status_from_summary(auth_summary)
        auth_summary["status"] = auth_status
        health_status, health_message = self._health_for_connection(validation=validation, auth_status=auth_status)
        runtime_validation: dict[str, Any] | None = None
        if auth_status == "authenticated" and bool(connection.get("enabled")):
            try:
                runtime_validation = self.runtime.validate_connection(
                    spec=spec,
                    connection=connection,
                    secrets=secrets_payload,
                )
                health_status = str(runtime_validation.get("health_status") or health_status)
                health_message = str(runtime_validation.get("message") or health_message)
            except IntegrationRuntimeError as exc:
                health_status = "invalid"
                health_message = str(exc)
        updated = self.repo.update_connection_runtime(
            self.settings.office_id,
            connection_id,
            status=self._status_for_connection(spec, validation_status=str(validation["status"]), auth_status=auth_status),
            auth_status=auth_status,
            auth_summary=auth_summary,
            credential_expires_at=auth_summary.get("expires_at"),
            credential_refreshed_at=auth_summary.get("last_refreshed_at"),
            credential_revoked_at=auth_summary.get("last_revoked_at"),
            health_status=health_status,
            health_message=health_message,
            last_health_check_at=_utcnow_iso(),
            last_validated_at=_utcnow_iso(),
            last_error=None if health_status in {"valid", "pending"} else health_message,
            metadata={
                **dict(connection.get("metadata") or {}),
                "warnings": list(validation.get("warnings") or []),
                "secret_keys": list(validation.get("secret_keys") or []),
            },
        )
        self._log_event(
            event_type=audit_reason,
            message=health_message,
            connector_id=spec.id,
            connection_id=connection_id,
            actor=actor,
            data={"auth_status": auth_status, "health_status": health_status},
        )
        validation_payload = {
            **validation,
            "status": auth_status if auth_status not in {"authenticated"} else validation["status"],
            "health_status": health_status,
            "message": health_message,
            "auth_summary": auth_summary,
            "runtime_validation": runtime_validation,
        }
        return {
            "connection": self._serialize_connection(updated),
            "connector": spec.model_dump(mode="json"),
            "capabilities": discover_capabilities(updated, spec),
            "validation": validation_payload,
            "generated_from": generated_from,
        }

    def _dispatch_due_sync_runs(
        self,
        *,
        limit: int,
        actor: str,
        target_connection_id: int | None = None,
    ) -> list[dict[str, Any]]:
        recovered_runs = self.repo.recover_stale_sync_runs(
            self.settings.office_id,
            lock_timeout_seconds=int(getattr(self.settings, "integration_worker_lock_timeout_seconds", 300)),
        )
        for recovered in recovered_runs[:5]:
            self._log_event(
                event_type="sync_lock_recovered",
                severity="warning",
                message="Stale sync lock yeniden kuyruga alindi.",
                connector_id=None,
                connection_id=int(recovered.get("connection_id") or 0) or None,
                actor=actor,
                data={"sync_run_id": recovered.get("id")},
            )
        due_runs = self.repo.list_due_sync_runs(self.settings.office_id, limit=max(limit * 3, limit))
        items: list[dict[str, Any]] = []
        for run in due_runs:
            if target_connection_id is not None and int(run.get("connection_id") or 0) != target_connection_id:
                continue
            if len(items) >= limit:
                break
            claimed = self.repo.claim_sync_run(
                self.settings.office_id,
                int(run["id"]),
                lock_token=f"lock-{run['id']}-{secrets.token_hex(6)}",
            )
            if not claimed or str(claimed.get("status") or "") != "running":
                continue
            items.append(self._perform_sync_run(claimed, actor=actor))
        return items

    def _perform_sync_run(self, sync_run: dict[str, Any], *, actor: str) -> dict[str, Any]:
        connection_id = int(sync_run["connection_id"])
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        try:
            if not bool(connection.get("enabled")):
                raise ValueError("integration_connection_disabled")
            auth_status = str(connection.get("auth_status") or auth_status_from_summary(connection.get("auth_summary") or {}))
            if auth_status in {"authorization_required", "authorization_pending", "expired", "revoked", "error"}:
                raise ValueError(f"integration_auth_not_ready:{auth_status}")
            synced_at = _utcnow_iso()
            sync_result = self.runtime.sync_connection(
                spec=spec,
                connection=connection,
                secrets=self._secrets_for_connection(connection),
                mode=str(sync_run.get("mode") or "incremental"),
                cursor=dict(connection.get("cursor") or {}),
            )
            records = list(sync_result.get("records") or [])
            for record in records:
                self.repo.upsert_record(
                    self.settings.office_id,
                    connection_id=connection_id,
                    record_type=str(record["record_type"]),
                    external_id=str(record["external_id"]),
                    title=str(record.get("title") or ""),
                    text_content=str(record.get("text_content") or ""),
                    content_hash=str(record.get("content_hash") or ""),
                    source_url=str(record.get("source_url") or "") or None,
                    permissions=record.get("permissions"),
                    tags=record.get("tags"),
                    raw=record.get("raw"),
                    normalized=record.get("normalized"),
                    synced_at=synced_at,
                )
            resources = normalize_records_to_resources(
                spec=spec,
                connection=connection,
                records=records,
                synced_at=synced_at,
            )
            for resource in resources:
                self.repo.upsert_resource(
                    self.settings.office_id,
                    connection_id=connection_id,
                    resource_kind=str(resource["resource_kind"]),
                    external_id=str(resource["external_id"]),
                    source_record_type=str(resource["source_record_type"]),
                    title=str(resource.get("title") or ""),
                    body_text=str(resource.get("body_text") or ""),
                    search_text=str(resource.get("search_text") or ""),
                    source_url=str(resource.get("source_url") or "") or None,
                    parent_external_id=str(resource.get("parent_external_id") or "") or None,
                    owner_label=str(resource.get("owner_label") or "") or None,
                    occurred_at=str(resource.get("occurred_at") or "") or None,
                    modified_at=str(resource.get("modified_at") or "") or None,
                    checksum=str(resource.get("checksum") or "") or None,
                    permissions=resource.get("permissions"),
                    tags=resource.get("tags"),
                    attributes=resource.get("attributes"),
                    sync_metadata=resource.get("sync_metadata"),
                    synced_at=synced_at,
                )
            cursor = {
                **dict(sync_result.get("cursor") or {}),
                "synced_at": synced_at,
                "record_count": len(records),
                "resource_count": len(resources),
                "mode": sync_run.get("mode"),
            }
            metadata = {
                "connector_id": spec.id,
                "dry_run": bool(self.settings.connector_dry_run) or bool(connection.get("mock_mode")),
                "trigger_type": sync_run.get("trigger_type"),
                **dict(sync_result.get("metadata") or {}),
            }
            partial_failure_count = int(metadata.get("partial_failure_count") or 0)
            partial_failures = list(metadata.get("partial_failures") or [])[:10]
            finished = self.repo.finish_sync_run(
                self.settings.office_id,
                int(sync_run["id"]),
                status="completed",
                item_count=len(resources),
                cursor=cursor,
                metadata=metadata,
            )
            sync_status_message = str(metadata.get("status_message") or "Son sync basariyla tamamlandi.")
            health_status = "valid"
            health_message = str(metadata.get("status_message") or "Sync tamamlandi.")
            if partial_failure_count:
                health_status = "degraded"
                health_message = f"Sync tamamlandi ancak {partial_failure_count} alt islem uyarisi olustu."
                sync_status_message = health_message
            updated = self.repo.update_connection_runtime(
                self.settings.office_id,
                connection_id,
                status="connected",
                health_status=health_status,
                health_message=health_message,
                last_health_check_at=synced_at,
                last_validated_at=synced_at,
                last_sync_at=synced_at,
                last_error=partial_failures[0] if partial_failures else None,
                cursor=cursor,
                sync_status="completed",
                sync_status_message=sync_status_message,
            )
            self._log_event(
                event_type="sync_completed",
                severity="warning" if partial_failure_count else "info",
                message=health_message,
                connector_id=spec.id,
                connection_id=connection_id,
                actor=actor,
                data={
                    "record_count": len(records),
                    "resource_count": len(resources),
                    "partial_failure_count": partial_failure_count,
                    "partial_failures": partial_failures,
                    "summary": metadata.get("summary"),
                    "page_title": metadata.get("page_title"),
                    "watch_url": metadata.get("watch_url"),
                    "change_detected": metadata.get("change_detected"),
                    "changed_count": metadata.get("changed_count"),
                    "connection_label": connection.get("display_name"),
                },
            )
            return {
                "connection": self._serialize_connection(updated),
                "connector": spec.model_dump(mode="json"),
                "sync_run": finished,
                "record_count": len(records),
                "resource_count": len(resources),
                "message": "Entegrasyon verileri normalize edilip kaydedildi.",
                "generated_from": "integration_sync_engine",
            }
        except ValueError as exc:
            attempts = int(sync_run.get("attempt_count") or 0) + 1
            max_attempts = int(sync_run.get("max_attempts") or 3)
            message = str(exc)
            if attempts < max_attempts:
                next_retry_at = (datetime.now(timezone.utc) + timedelta(minutes=min(60, 2**attempts))).isoformat()
                retried = self.repo.reschedule_sync_run(
                    self.settings.office_id,
                    int(sync_run["id"]),
                    error=message,
                    next_retry_at=next_retry_at,
                    attempt_count=attempts,
                    metadata={"connector_id": spec.id},
                )
                updated = self.repo.update_connection_runtime(
                    self.settings.office_id,
                    connection_id,
                    status="degraded",
                    health_status="invalid",
                    health_message=message,
                    last_error=message,
                    sync_status="retry_scheduled",
                    sync_status_message=f"Sync yeniden denenecek ({attempts}/{max_attempts}).",
                )
                self._log_event(
                    event_type="sync_retry_scheduled",
                    severity="warning",
                    message=message,
                    connector_id=spec.id,
                    connection_id=connection_id,
                    actor=actor,
                    data={"attempt_count": attempts, "max_attempts": max_attempts},
                )
                return {
                    "connection": self._serialize_connection(updated),
                    "connector": spec.model_dump(mode="json"),
                    "sync_run": retried,
                    "record_count": 0,
                    "resource_count": 0,
                    "message": message,
                    "generated_from": "integration_sync_engine",
                }
            finished = self.repo.finish_sync_run(
                self.settings.office_id,
                int(sync_run["id"]),
                status="failed",
                item_count=0,
                error=message,
                metadata={"connector_id": spec.id},
            )
            updated = self.repo.update_connection_runtime(
                self.settings.office_id,
                connection_id,
                status="degraded",
                health_status="invalid",
                health_message=message,
                last_error=message,
                sync_status="failed",
                sync_status_message="Sync basarisiz oldu.",
            )
            self._log_event(
                event_type="sync_failed",
                severity="error",
                message=message,
                connector_id=spec.id,
                connection_id=connection_id,
                actor=actor,
                data={"attempt_count": attempts, "max_attempts": max_attempts},
            )
            return {
                "connection": self._serialize_connection(updated),
                "connector": spec.model_dump(mode="json"),
                "sync_run": finished,
                "record_count": 0,
                "resource_count": 0,
                "message": message,
                "generated_from": "integration_sync_engine",
            }

    def _legacy_status_map(self) -> dict[str, dict[str, Any]]:
        status_items = build_tools_status(self.settings, self.store)
        mapped: dict[str, dict[str, Any]] = {}
        for item in status_items:
            provider = str(item.get("provider") or "")
            if provider not in self.catalog:
                continue
            mapped[provider] = {
                "provider": provider,
                "account_label": item.get("account_label"),
                "connected": bool(item.get("connected")),
                "status": item.get("status"),
                "scopes": list(item.get("scopes") or []),
                "capabilities": list(item.get("capabilities") or []),
                "write_enabled": bool(item.get("write_enabled")),
                "approval_required": bool(item.get("approval_required")),
                "connected_account": item.get("connected_account"),
                "desktop_managed": True,
            }
        return mapped

    def _ensure_platform_connector(self, spec: ConnectorSpec) -> None:
        if spec.management_mode == "legacy-desktop":
            raise ValueError("legacy_connector_managed_by_desktop")

    def _ensure_oauth_connector(self, spec: ConnectorSpec) -> None:
        if spec.auth_type != "oauth2":
            raise ValueError("integration_connector_not_oauth")

    def _require_connector(self, connector_id: str) -> ConnectorSpec:
        spec = self._effective_catalog().get(str(connector_id or ""))
        if not spec:
            raise ValueError("integration_connector_not_found")
        return spec

    def _optional_connection(self, connection_id: int | None) -> dict[str, Any] | None:
        if not connection_id:
            return None
        return self._require_connection(connection_id)

    def _require_connection(self, connection_id: int) -> dict[str, Any]:
        connection = self.repo.get_connection(self.settings.office_id, connection_id)
        if not connection:
            raise ValueError("integration_connection_not_found")
        return connection

    def _serialize_connection(self, connection: dict[str, Any]) -> dict[str, Any]:
        auth_summary = dict(connection.get("auth_summary") or {})
        auth_status = str(connection.get("auth_status") or auth_status_from_summary(auth_summary))
        auth_summary["status"] = auth_status
        return {
            "id": connection.get("id"),
            "connector_id": connection.get("connector_id"),
            "display_name": connection.get("display_name"),
            "status": connection.get("status"),
            "auth_type": connection.get("auth_type"),
            "access_level": connection.get("access_level"),
            "management_mode": connection.get("management_mode"),
            "enabled": bool(connection.get("enabled")),
            "mock_mode": bool(connection.get("mock_mode")),
            "scopes": list(connection.get("scopes") or []),
            "config": dict(connection.get("config") or {}),
            "health_status": connection.get("health_status"),
            "health_message": connection.get("health_message"),
            "auth_status": auth_status,
            "auth_summary": auth_summary,
            "credential_expires_at": connection.get("credential_expires_at"),
            "credential_refreshed_at": connection.get("credential_refreshed_at"),
            "credential_revoked_at": connection.get("credential_revoked_at"),
            "last_health_check_at": connection.get("last_health_check_at"),
            "last_validated_at": connection.get("last_validated_at"),
            "last_sync_at": connection.get("last_sync_at"),
            "last_error": connection.get("last_error"),
            "sync_status": connection.get("sync_status"),
            "sync_status_message": connection.get("sync_status_message"),
            "cursor": dict(connection.get("cursor") or {}),
            "metadata": dict(connection.get("metadata") or {}),
            "created_by": connection.get("created_by"),
            "created_at": connection.get("created_at"),
            "updated_at": connection.get("updated_at"),
        }

    def _primary_status(self, connections: list[dict[str, Any]], legacy_status: dict[str, Any] | None) -> str:
        if connections:
            return str(connections[0].get("status") or "configured")
        if legacy_status:
            return str(legacy_status.get("status") or "legacy")
        return "available"

    def _validate_connection_payload(
        self,
        spec: ConnectorSpec,
        *,
        config: dict[str, Any],
        secrets: dict[str, Any],
        access_level: str,
        mock_mode: bool,
        requested_scopes: list[str],
    ) -> dict[str, Any]:
        normalized_config = self._fill_defaults(spec, config)
        normalized_secrets = self._normalize_payload_dict(secrets, limit=24)
        warnings: list[str] = []
        if spec.management_mode == "legacy-desktop":
            return {
                "status": "legacy-desktop",
                "health_status": "external",
                "message": spec.setup_hint or "Legacy connector masaustu tarafindan yonetiliyor.",
                "warnings": warnings,
                "config": normalized_config,
                "access_level": access_level,
                "scopes": requested_scopes,
                "secret_keys": [],
            }

        missing_fields = []
        for field in spec.ui_schema:
            if not field.required:
                continue
            source = normalized_secrets if field.target == "secret" else normalized_config
            if spec.auth_type == "oauth2" and field.key in {"access_token", "refresh_token"}:
                continue
            if _empty_value(source.get(field.key)):
                missing_fields.append(field.label)
        if missing_fields:
            return {
                "status": "invalid",
                "health_status": "invalid",
                "message": f"Eksik zorunlu alanlar: {', '.join(missing_fields)}",
                "warnings": warnings,
                "config": normalized_config,
                "access_level": access_level,
                "scopes": requested_scopes,
                "secret_keys": sorted(normalized_secrets.keys()),
            }

        if normalized_config.get("base_url"):
            warnings.extend(self._validate_remote_target(str(normalized_config.get("base_url"))))

        if spec.id == "notion":
            token = str(normalized_secrets.get("integration_token") or "")
            if token and not token.startswith("secret_"):
                warnings.append("Notion token formatini insan incelemesiyle dogrulayin.")
        elif spec.id == "generic-rest":
            auth_mode = str(normalized_config.get("auth_mode") or "api_key")
            if auth_mode not in {"api_key", "bearer", "basic", "none"}:
                return {
                    "status": "invalid",
                    "health_status": "invalid",
                    "message": "REST auth_mode gecersiz.",
                    "warnings": warnings,
                    "config": normalized_config,
                    "access_level": access_level,
                    "scopes": requested_scopes,
                    "secret_keys": sorted(normalized_secrets.keys()),
                }
        elif spec.id in {"postgresql", "mysql", "mssql"}:
            label = {
                "postgresql": "PostgreSQL",
                "mysql": "MySQL",
                "mssql": "SQL Server",
            }[spec.id]
            default_port = {
                "postgresql": 5432,
                "mysql": 3306,
                "mssql": 1433,
            }[spec.id]
            try:
                normalized_config["port"] = int(normalized_config.get("port") or default_port)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{label} port bilgisi sayi olmali.") from exc
            if normalized_config["port"] <= 0 or normalized_config["port"] > 65535:
                raise ValueError(f"{label} port araligi gecersiz.")
        elif spec.id == "elastic":
            has_base_url = bool(str(normalized_config.get("base_url") or "").strip())
            has_cloud_id = bool(str(normalized_config.get("cloud_id") or "").strip())
            if not has_base_url and not has_cloud_id:
                return {
                    "status": "invalid",
                    "health_status": "invalid",
                    "message": "Elastic icin Temel URL veya Elastic Cloud ID gerekli.",
                    "warnings": warnings,
                    "config": normalized_config,
                    "access_level": access_level,
                    "scopes": requested_scopes,
                    "secret_keys": sorted(normalized_secrets.keys()),
                }
            has_api_key = bool(str(normalized_secrets.get("api_key") or "").strip())
            has_api_key_pair = bool(str(normalized_config.get("api_key_id") or "").strip()) and bool(str(normalized_secrets.get("api_key_secret") or "").strip())
            has_basic_auth = bool(str(normalized_config.get("username") or "").strip()) and bool(str(normalized_secrets.get("password") or "").strip())
            if not has_api_key and not has_api_key_pair and not has_basic_auth:
                warnings.append("Elastic icin API key ya da kullanici/parola girmeniz onerilir; sorgular kimlik dogrulamasi olmadan calismaz.")

        if spec.auth_type == "oauth2" and not (
            normalized_secrets.get("oauth_access_token") or normalized_secrets.get("access_token")
        ):
            return {
                "status": "authorization_required",
                "health_status": "pending",
                "message": "OAuth konfigurasyonu kayda hazir; yetkilendirme adimi bekleniyor.",
                "warnings": warnings,
                "config": normalized_config,
                "access_level": access_level,
                "scopes": requested_scopes,
                "secret_keys": sorted(normalized_secrets.keys()),
            }

        status = "dry_run" if (mock_mode or bool(self.settings.connector_dry_run)) else "valid"
        message = "Connector konfigurasyonu dogrulandi."
        if status == "dry_run":
            message = "Connector dry-run modunda dogrulandi; gercek cagrilar insan onayi sonrasi acilmalidir."
        return {
            "status": status,
            "health_status": "valid",
            "message": message,
            "warnings": warnings,
            "config": normalized_config,
            "access_level": access_level,
            "scopes": requested_scopes,
            "secret_keys": sorted(normalized_secrets.keys()),
        }

    def _normalize_payload_dict(self, payload: dict[str, Any], *, limit: int) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for index, (key, value) in enumerate((payload or {}).items()):
            if index >= limit:
                break
            cleaned_key = str(key or "").strip()
            if not cleaned_key:
                continue
            normalized[cleaned_key] = _normalize_value(value)
        return normalized

    def _fill_defaults(self, spec: ConnectorSpec, config: dict[str, Any]) -> dict[str, Any]:
        merged = dict(config or {})
        for field in spec.ui_schema:
            if field.target != "config":
                continue
            if field.key not in merged and field.default is not None:
                merged[field.key] = field.default
        if spec.base_url and not merged.get("base_url"):
            merged["base_url"] = spec.base_url
        return self._normalize_payload_dict(merged, limit=24)

    def _validate_remote_target(self, url: str) -> list[str]:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Sadece http/https tabanli endpointler destekleniyor.")
        hostname = str(parsed.hostname or "").strip().lower()
        if not hostname:
            raise ValueError("Base URL host bilgisi eksik.")
        if hostname == "localhost":
            raise ValueError("localhost ve loopback endpointleri SSRF nedeniyle reddedildi.")
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None
        if ip and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast):
            raise ValueError("Private veya lokal IP adresleri entegrasyon hedefi olarak kullanilamaz.")
        if hostname.endswith(".local"):
            raise ValueError("local TLD hedefleri entegrasyon hedefi olarak kullanilamaz.")
        warnings: list[str] = []
        allowed = [domain for domain in self.settings.connector_allow_domains if domain]
        if allowed and not any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed):
            warnings.append("Host explicit allowlist icinde degil; production rollout oncesi alan adi politikasi gozden gecirilmeli.")
        if parsed.scheme != "https":
            warnings.append("HTTPS disi endpointler sadece kontrollu local/dev baglamda kullanilmali.")
        return warnings

    def _validate_redirect_uri(self, redirect_uri: str) -> str:
        cleaned = str(redirect_uri or "").strip()
        if not cleaned:
            raise ValueError("oauth_redirect_uri_missing")
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("oauth_redirect_uri_invalid")
        hostname = str(parsed.hostname or "").strip().lower()
        if not hostname:
            raise ValueError("oauth_redirect_uri_invalid")
        if parsed.scheme == "http" and hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("oauth_redirect_uri_requires_https")
        return cleaned

    def _run_action(
        self,
        connection: dict[str, Any],
        spec: ConnectorSpec,
        action: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.runtime.execute_action(
            spec=spec,
            connection=connection,
            secrets=self._secrets_for_connection(connection),
            action=action,
            payload=self._normalize_payload_dict(payload, limit=24),
        )

    def _resolve_scopes(self, spec: ConnectorSpec, requested_scopes: list[str] | None) -> list[str]:
        allowed = list(spec.auth_config.default_scopes or spec.scopes)
        requested = [str(item or "").strip() for item in list(requested_scopes or []) if str(item or "").strip()]
        if not requested:
            requested = list(allowed)
        if allowed:
            requested = [item for item in requested if item in allowed] or list(allowed)
        deduped: list[str] = []
        for scope in requested:
            if scope not in deduped:
                deduped.append(scope)
        return deduped[:40]

    def _build_connection_auth_summary(
        self,
        spec: ConnectorSpec,
        *,
        requested_scopes: list[str],
        secrets: dict[str, Any],
        existing_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = dict(existing_summary or {})
        if spec.auth_type == "oauth2":
            access_token = str(secrets.get("oauth_access_token") or secrets.get("access_token") or "").strip()
            refresh_token = str(secrets.get("oauth_refresh_token") or secrets.get("refresh_token") or "").strip()
            expires_at = str(secrets.get("oauth_expires_at") or current.get("expires_at") or "").strip() or None
            granted_scopes = list(current.get("granted_scopes") or requested_scopes)
            status = str(current.get("status") or "authorization_required")
            if access_token:
                status = "authenticated"
            elif status not in {"revoked", "disconnected", "error"}:
                status = "authorization_required"
            summary = build_auth_summary(
                spec=spec,
                status=status,
                requested_scopes=requested_scopes,
                granted_scopes=granted_scopes,
                expires_at=expires_at,
                refresh_token_present=bool(refresh_token),
                last_refreshed_at=current.get("last_refreshed_at") or secrets.get("oauth_issued_at"),
                last_revoked_at=current.get("last_revoked_at"),
                permission_summary=summarize_scope_permissions(granted_scopes or requested_scopes),
            )
            summary["status"] = auth_status_from_summary(summary)
            return summary
        secret_present = bool(secrets) or spec.auth_type in {"none", "noauth"}
        status = "authenticated" if secret_present else str(current.get("status") or "pending")
        return build_auth_summary(
            spec=spec,
            status=status,
            requested_scopes=requested_scopes,
            granted_scopes=requested_scopes,
            permission_summary=summarize_scope_permissions(requested_scopes),
        )

    def _health_for_connection(self, *, validation: dict[str, Any], auth_status: str) -> tuple[str, str]:
        if auth_status == "authenticated":
            return str(validation["health_status"]), str(validation["message"])
        if auth_status in {"authorization_required", "authorization_pending", "pending"}:
            return "pending", "OAuth yetkilendirmesi bekleniyor."
        if auth_status == "disconnected":
            return "revoked", "Baglanti duraklatildi."
        if auth_status == "revoked":
            return "revoked", "Kimlik bilgileri iptal edildi."
        if auth_status == "expired":
            return "invalid", "Kimlik bilgisi suresi doldu; yenileme gerekli."
        if auth_status == "error":
            return "invalid", str(validation.get("message") or "Kimlik bilgisi hatali.")
        return str(validation["health_status"]), str(validation["message"])

    def _status_for_connection(self, spec: ConnectorSpec, *, validation_status: str, auth_status: str) -> str:
        if spec.management_mode == "legacy-desktop":
            return "legacy"
        if auth_status == "authenticated" and validation_status in {"valid", "dry_run"}:
            return "connected"
        if auth_status in {"authorization_required", "authorization_pending", "pending", "disconnected"}:
            return "configured"
        if auth_status == "revoked":
            return "revoked"
        if auth_status in {"expired", "error"} or validation_status == "invalid":
            return "degraded"
        return "configured"

    def _merge_secret_payload(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing or {})
        for key, value in (incoming or {}).items():
            if _empty_value(value):
                continue
            merged[str(key)] = value
        return merged

    def _secrets_for_connection(self, connection: dict[str, Any] | None) -> dict[str, Any]:
        if not connection:
            return {}
        return self.secret_box.open_json(str(connection.get("secret_blob") or ""))

    def _apply_oauth_token_bundle(self, existing_secrets: dict[str, Any], token_bundle: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing_secrets or {})
        merged["oauth_access_token"] = str(token_bundle.get("access_token") or "")
        refresh_token = str(token_bundle.get("refresh_token") or "")
        if refresh_token:
            merged["oauth_refresh_token"] = refresh_token
        elif "oauth_refresh_token" in merged:
            merged.pop("oauth_refresh_token", None)
        merged["oauth_token_type"] = str(token_bundle.get("token_type") or "Bearer")
        merged["oauth_scope"] = " ".join(str(scope) for scope in list(token_bundle.get("scope") or []))
        merged["oauth_expires_at"] = str(token_bundle.get("expires_at") or "")
        merged["oauth_issued_at"] = str(token_bundle.get("issued_at") or "")
        return merged

    def _strip_oauth_runtime_secrets(self, existing_secrets: dict[str, Any]) -> dict[str, Any]:
        retained = dict(existing_secrets or {})
        for key in [
            "oauth_access_token",
            "oauth_refresh_token",
            "oauth_token_type",
            "oauth_scope",
            "oauth_expires_at",
            "oauth_issued_at",
        ]:
            retained.pop(key, None)
        return retained

    def _field_required(self, spec: ConnectorSpec, field_key: str) -> bool:
        for field in spec.ui_schema:
            if field.key == field_key:
                return bool(field.required)
        return False

    def _save_message_for_status(self, auth_status: str) -> str:
        if auth_status in {"authorization_required", "authorization_pending"}:
            return "Entegrasyon baglantisi kaydedildi. OAuth yetkilendirmesi bekleniyor."
        return "Entegrasyon baglantisi kaydedildi."

    def _list_active_generated_rows(self) -> list[dict[str, Any]]:
        rows = self.repo.list_generated_connectors(self.settings.office_id, limit=200)
        return [
            row
            for row in rows
            if bool(row.get("enabled"))
            and str(row.get("status") or "") not in {"archived", "rejected"}
        ]

    def _assert_generated_connector_usage_allowed(self, connector_id: str, *, mock_mode: bool) -> dict[str, Any] | None:
        row = self.repo.get_generated_connector(self.settings.office_id, connector_id)
        if not row:
            return None
        status = str(row.get("status") or "")
        if status in {"rejected", "archived"} or not bool(row.get("enabled", True)):
            raise ValueError("generated_connector_not_available")
        live_requested = not bool(mock_mode or self.settings.connector_dry_run)
        if live_requested and not self._generated_live_use_allowed(row):
            raise ValueError("generated_connector_review_required_for_live_mode")
        return row

    def _generated_live_use_allowed(self, row: dict[str, Any] | None) -> bool:
        if not row:
            return False
        metadata = dict(row.get("metadata") or {})
        review = dict(metadata.get("review") or {})
        return str(row.get("status") or "") == "approved" and bool(review.get("live_use_enabled"))

    def _generated_connector_specs(self, rows: list[dict[str, Any]]) -> dict[str, ConnectorSpec]:
        specs: dict[str, ConnectorSpec] = {}
        for row in rows:
            materialized = self._materialize_generated_connector(row)
            if materialized:
                specs[materialized.id] = materialized
        return specs

    def _materialize_generated_connector(self, row: dict[str, Any] | None) -> ConnectorSpec | None:
        if not row:
            return None
        spec_payload = dict(row.get("spec") or {})
        if not spec_payload:
            return None
        try:
            return ConnectorSpec.model_validate(spec_payload)
        except Exception:
            return None

    def _serialize_generated_connector(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        spec = self._materialize_generated_connector(row)
        metadata = dict(row.get("metadata") or {})
        review = dict(metadata.get("review") or {})
        versions = self.repo.list_generated_connector_versions(
            self.settings.office_id,
            str(row.get("connector_id") or ""),
            limit=6,
        )
        return {
            "id": row.get("id"),
            "connector_id": row.get("connector_id"),
            "service_name": row.get("service_name"),
            "request_text": row.get("request_text"),
            "status": row.get("status"),
            "version": int(row.get("version") or 1),
            "enabled": bool(row.get("enabled")),
            "docs_url": row.get("docs_url"),
            "openapi_url": row.get("openapi_url"),
            "documentation_excerpt": row.get("documentation_excerpt"),
            "last_error": row.get("last_error"),
            "metadata": metadata,
            "review": review,
            "live_use_enabled": self._generated_live_use_allowed(row),
            "skill": metadata.get("skill") or (self._connector_skill_summary(spec) if spec else None),
            "versions": [
                {
                    "version": item.get("version"),
                    "status": item.get("status"),
                    "enabled": bool(item.get("enabled")),
                    "created_at": item.get("created_at"),
                }
                for item in versions
            ],
            "created_by": row.get("created_by"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "connector": spec.model_dump(mode="json") if spec else None,
        }

    def _connector_skill_summary(self, spec: ConnectorSpec | None) -> dict[str, Any] | None:
        if not spec:
            return None
        capability_groups = self._connector_capability_groups(spec)
        return {
            "name": spec.name,
            "connector_id": spec.id,
            "capabilities": [action.operation for action in spec.actions],
            "permissions": [permission.level for permission in spec.permissions],
            "ui_label": spec.name,
            "summary": self._connector_skill_summary_text(spec, capability_groups),
            "capability_groups": capability_groups,
            "capability_preview": self._connector_capability_preview(spec),
            "recommended_prompts": self._assistant_post_connect_suggestions(spec),
        }

    def _serialize_assistant_setup(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        metadata = dict(row.get("metadata") or {})
        connector_id = str(row.get("connector_id") or "").strip()
        spec = self._effective_catalog().get(connector_id) if connector_id else None
        skill = metadata.get("skill") or self._connector_skill_summary(spec)
        pending_field = dict(metadata.get("pending_field") or {})
        return {
            "id": row.get("id"),
            "thread_id": row.get("thread_id"),
            "connector_id": row.get("connector_id"),
            "connection_id": row.get("connection_id"),
            "service_name": row.get("service_name"),
            "request_text": row.get("request_text"),
            "status": row.get("status"),
            "missing_fields": list(row.get("missing_fields") or []),
            "pending_field": pending_field or None,
            "access_level": metadata.get("access_level"),
            "requested_scopes": list(metadata.get("requested_scopes") or []),
            "live_mode_requested": bool(metadata.get("live_mode_requested")),
            "generated_request_status": metadata.get("generated_request_status"),
            "generated_connector_id": metadata.get("generated_connector_id"),
            "authorization_url": metadata.get("authorization_url"),
            "oauth_session_state": metadata.get("oauth_session_state"),
            "deep_link_path": metadata.get("deep_link_path"),
            "next_step": metadata.get("next_step"),
            "setup_mode": metadata.get("setup_mode"),
            "desktop_action": metadata.get("desktop_action"),
            "desktop_cta_label": metadata.get("desktop_cta_label"),
            "desktop_action_help": metadata.get("desktop_action_help"),
            "review_summary": metadata.get("review_summary"),
            "awaiting_provider_choice": bool(metadata.get("awaiting_provider_choice")),
            "provider_options": list(metadata.get("provider_options") or []),
            "suggested_replies": list(metadata.get("suggested_replies") or []),
            "capabilities": list(metadata.get("capabilities") or (dict(skill).get("capability_preview") if isinstance(skill, dict) else []) or []),
            "skill": skill,
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def _connector_capability_groups(self, spec: ConnectorSpec) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        category_defaults = {
            "communication": ("messages", "Mesajlar", "Mesajları ve kanalları okuyup özetleyebilirim."),
            "knowledge-base": ("documents", "Belgeler", "Belgeleri, sayfaları ve notları bulup özetleyebilirim."),
            "storage": ("files", "Dosyalar", "Dosyaları listeleyip ilgili içerikleri çekebilirim."),
            "database": ("databases", "Veri kayıtları", "Tabloları ve kayıtları sorgulayıp açıklayabilirim."),
            "calendar": ("events", "Takvim", "Etkinlikleri ve tarihli kayıtları takip edebilirim."),
            "social-media": ("social", "Sosyal içerik", "Profil, içerik ve sosyal medya akışlarını takip edebilirim."),
            "project-management": ("tasks", "Görevler", "Görevleri ve durum değişimlerini takip edebilirim."),
            "crm": ("contacts", "Kişiler ve kayıtlar", "Müşteri ve iletişim kayıtlarını okuyup düzenleyebilirim."),
            "developer-tools": ("developer", "Geliştirici akışları", "Repo, issue ve teknik backlog verilerini takip edebilirim."),
            "custom-api": ("general", "Özel servis", "Bu servisin temel verilerini okuyup aksiyon alabilirim."),
            "web-monitoring": ("documents", "Web takibi", "İzlediğin sayfalardaki değişiklikleri takip edip özetleyebilirim."),
        }

        def ensure_bucket(key: str, label: str, description: str) -> dict[str, Any]:
            if key not in buckets:
                buckets[key] = {
                    "key": key,
                    "label": label,
                    "description": description,
                    "actions": [],
                    "action_keys": [],
                }
            return buckets[key]

        for action in spec.actions:
            group_key, group_label, group_description = self._connector_capability_group_for_action(spec, action.operation)
            bucket = ensure_bucket(group_key, group_label, group_description)
            bucket["actions"].append(action.title)
            bucket["action_keys"].append(action.key)

        if not buckets:
            fallback = category_defaults.get(spec.category, ("general", "Bağlantı", "Bu servisin temel verilerine erişebilirim."))
            ensure_bucket(*fallback)

        return list(buckets.values())

    def _connector_capability_group_for_action(self, spec: ConnectorSpec, operation: str) -> tuple[str, str, str]:
        if operation in {"send_message", "read_messages"} or spec.category == "communication":
            return ("messages", "Mesajlar", "Mesajları ve sohbet akışını okuyup yardımcı olabilirim.")
        if operation in {"create_page", "append_block", "fetch_documents"} or spec.category == "knowledge-base":
            return ("documents", "Belgeler", "Belgeleri, sayfaları ve notları bulup özetleyebilirim.")
        if operation in {"list_databases", "run_query", "insert_record", "update_record"} or spec.category == "database":
            return ("databases", "Veri kayıtları", "Tabloları ve kayıtları sorgulayıp açıklayabilirim.")
        if operation in {"upload_file", "download_file"} or spec.category == "storage":
            return ("files", "Dosyalar", "Dosyaları listeleyip ilgili içerikleri çekebilirim.")
        if spec.category == "calendar":
            return ("events", "Takvim", "Etkinlikleri ve tarihli kayıtları takip edebilirim.")
        if spec.category == "social-media":
            return ("social", "Sosyal içerik", "Profil, içerik ve sosyal medya akışlarını takip edebilirim.")
        if spec.category in {"project-management", "developer-tools"}:
            return ("tasks", "Görevler", "Görevleri, issue'ları ve takip listelerini yönetebilirim.")
        if spec.category == "crm":
            return ("contacts", "Kişiler ve kayıtlar", "Kişi, firma ve ilişki kayıtlarını tarayabilirim.")
        if spec.category == "web-monitoring":
            return ("documents", "Web takibi", "İzlediğin sayfalardaki değişiklikleri takip edip özetleyebilirim.")
        return ("general", "Özel servis", "Bu servisin temel verilerini okuyup aksiyon alabilirim.")

    def _connector_skill_summary_text(self, spec: ConnectorSpec, capability_groups: list[dict[str, Any]]) -> str:
        descriptions = [str(item.get("description") or "").strip() for item in capability_groups if str(item.get("description") or "").strip()]
        if descriptions:
            return f"{spec.name} ile {descriptions[0].lower()}"
        if spec.setup_hint:
            return str(spec.setup_hint).strip()
        return f"{spec.name} bağlandığında yardımcı aksiyonlar açılır."

    def _connector_capability_preview(self, spec: ConnectorSpec) -> list[str]:
        previews = [str(action.title or "").strip() for action in spec.actions if str(action.title or "").strip()]
        return previews[:4]

    def _assistant_post_connect_suggestions(self, spec: ConnectorSpec) -> list[str]:
        suggestions_by_connector = {
            "slack": ["Son Slack mesajlarını özetle", "Slack kanallarını listele"],
            "notion": ["Son Notion sayfalarını özetle", "Notion notlarında ara"],
            "gmail": ["Son Google e-postalarını özetle", "Yanıt taslağı hazırla"],
            "calendar": ["Bugünkü takvimi özetle", "Uygun toplantı saatleri öner"],
            "drive": ["Son Drive dosyalarını listele", "Drive içeriğinde ara"],
            "outlook-mail": ["Son Outlook e-postalarını özetle", "Outlook için yanıt taslağı hazırla"],
            "outlook-calendar": ["Bugünkü Outlook takvimini özetle", "Uygun toplantı saatleri öner"],
            "telegram": ["Son Telegram mesajlarını özetle", "Telegram için yanıt taslağı hazırla"],
            "whatsapp": ["Son WhatsApp mesajlarını özetle", "WhatsApp için yanıt taslağı hazırla"],
            "x": ["X mention'larını özetle", "X için gönderi taslağı hazırla"],
            "instagram": ["Son Instagram mesajlarını özetle", "Instagram için yanıt taslağı hazırla"],
            "linkedin": ["LinkedIn yorumlarını özetle", "LinkedIn için gönderi taslağı hazırla"],
            "postgresql": ["Tablolari listele", "SQL sorgusu calistir"],
            "mysql": ["Tablolari listele", "SQL sorgusu calistir"],
            "mssql": ["Tablolari listele", "SQL sorgusu calistir"],
            "elastic": ["Elastic SQL sorgusu calistir", "Indeks sagligini ozetle"],
            "generic-rest": ["Bu servisin uç noktalarını özetle", "İlk veri çekimini başlat"],
            "github": ["Açık issue'ları özetle", "Repository listesini çıkar"],
            "web-watch": ["Son değişiklikleri özetle", "Bu sayfada bugün ne değişti?"],
            "tiktok": ["TikTok profilimi özetle", "TikTok erişim kapsamını göster"],
        }
        if spec.id in suggestions_by_connector:
            return list(suggestions_by_connector[spec.id])

        groups = [str(item.get("key") or "") for item in self._connector_capability_groups(spec)]
        if "messages" in groups:
            return [f"{spec.name} mesajlarını özetle", f"{spec.name} için önemli konuları çıkar"]
        if "documents" in groups:
            return [f"{spec.name} içeriğinde ara", f"{spec.name} kaynaklarını özetle"]
        if "databases" in groups:
            return [f"{spec.name} kayıtlarını listele", f"{spec.name} sorgu önersin"]
        return [f"{spec.name} ile neler yapabileceğini özetle"]

    def _assistant_access_level_label(self, access_level: str) -> str:
        mapping = {
            "read_only": "Salt okuma",
            "read_write": "Okuma ve yazma",
            "admin_like": "Geniş yetki",
        }
        return mapping.get(access_level, access_level or "Standart erişim")

    def _assistant_requested_scope_summary(self, scopes: list[str]) -> str:
        if not scopes:
            return "Varsayilan izin seti istenecek."
        if len(scopes) <= 3:
            return ", ".join(scopes)
        visible = ", ".join(scopes[:3])
        return f"{visible} ve {len(scopes) - 3} izin daha"

    def _assistant_legacy_recipe(self, connector_id: str) -> dict[str, Any]:
        for item in LEGACY_ASSISTANT_RECIPES:
            if str(item.get("connector_id") or "") == connector_id:
                return dict(item)
        return {}

    def _assistant_match_legacy_connector(self, normalized_query: str) -> ConnectorSpec | None:
        padded = f" {normalized_query.strip()} "
        for item in LEGACY_ASSISTANT_RECIPES:
            aliases = [str(alias).strip().lower() for alias in list(item.get("aliases") or []) if str(alias).strip()]
            if not aliases:
                continue
            if any((f" {alias} " in padded) or (alias in normalized_query and len(alias) > 3) for alias in aliases):
                connector_id = str(item.get("connector_id") or "")
                if connector_id:
                    return self._require_connector(connector_id)
        return None

    def _assistant_legacy_deep_link(self, connector_id: str) -> str:
        recipe = self._assistant_legacy_recipe(connector_id)
        return str(recipe.get("setup_path") or self._assistant_deep_link(connector_id=connector_id))

    def _assistant_legacy_skill_summary(self, spec: ConnectorSpec, recipe: dict[str, Any]) -> dict[str, Any]:
        skill = dict(self._connector_skill_summary(spec) or {})
        if recipe.get("service_name"):
            skill["ui_label"] = recipe["service_name"]
        if recipe.get("summary"):
            skill["summary"] = recipe["summary"]
        if recipe.get("capability_preview"):
            skill["capability_preview"] = list(recipe.get("capability_preview") or [])
        if recipe.get("recommended_prompts"):
            skill["recommended_prompts"] = list(recipe.get("recommended_prompts") or [])
        return skill

    def _assistant_legacy_capabilities(self, connector_id: str, legacy_status: dict[str, Any] | None) -> list[str]:
        mapping = {
            "read_threads": "E-posta konularını oku",
            "draft_reply": "Yanıt taslağı hazırla",
            "send_after_approval": "Onayla gönder",
            "read_events": "Etkinlikleri oku",
            "suggest_slots": "Uygun saat öner",
            "create_after_approval": "Onayla etkinlik oluştur",
            "update_after_approval": "Onayla etkinliği güncelle",
            "list_files": "Dosyaları listele",
            "fetch_context": "Dosya içeriğini getir",
            "bind_reference": "Dosyayı kayda bağla",
            "read_messages": "Mesajları oku",
            "mentions_read": "Bahsetmeleri oku",
            "draft_post": "Gönderi taslağı hazırla",
        }
        labels = [
            mapping.get(str(item).strip(), str(item).strip())
            for item in list((legacy_status or {}).get("capabilities") or [])
            if str(item).strip()
        ]
        if labels:
            return labels[:4]
        recipe = self._assistant_legacy_recipe(connector_id)
        return [str(item).strip() for item in list(recipe.get("capability_preview") or []) if str(item).strip()][:4]

    def _assistant_legacy_connected_message(self, spec: ConnectorSpec, legacy_status: dict[str, Any] | None) -> str:
        recipe = self._assistant_legacy_recipe(spec.id)
        service_name = str(recipe.get("service_name") or spec.name)
        capability_titles = self._assistant_legacy_capabilities(spec.id, legacy_status)
        lines = [f"{service_name} bağlı görünüyor."]
        if capability_titles:
            lines.append(f"Artık şunları yapabilirim: {', '.join(capability_titles)}.")
        account_label = str((legacy_status or {}).get("account_label") or "").strip()
        if account_label:
            lines.append(f"Bağlı hesap: {account_label}.")
        suggestions = list(recipe.get("recommended_prompts") or self._assistant_post_connect_suggestions(spec))
        if suggestions:
            lines.append(f"İstersen sıradaki adım olarak '{suggestions[0]}' diyebilirsin.")
        return " ".join(lines)

    def _assistant_legacy_whatsapp_mode(self, *, query: str, metadata: dict[str, Any] | None = None) -> str:
        existing = str((metadata or {}).get("whatsapp_mode") or "").strip().lower()
        if existing in {"web", "business_cloud"}:
            return existing
        normalized = _normalize_text(query)
        if any(token in normalized for token in ("business", "cloud", "api", "meta")):
            return "business_cloud"
        return "web"

    def _assistant_legacy_telegram_mode(self, *, query: str, metadata: dict[str, Any] | None = None) -> str:
        existing = str((metadata or {}).get("telegram_mode") or "").strip().lower()
        if existing in {"bot", "web"}:
            return existing
        normalized = _normalize_text(query)
        if any(token in normalized for token in ("kisisel", "kişisel", "web", "dm", "tam hesap", "full account", "her seye", "her şeye")):
            return "web"
        return "bot"

    def _assistant_legacy_linkedin_mode(self, *, query: str, metadata: dict[str, Any] | None = None) -> str:
        existing = str((metadata or {}).get("linkedin_mode") or "").strip().lower()
        if existing in {"official", "web"}:
            return existing
        normalized = _normalize_text(query)
        if any(token in normalized for token in ("dm", "mesaj", "inbox", "web", "kisisel", "kişisel", "tam hesap", "full account")):
            return "web"
        return "official"

    def _assistant_google_oauth_client_ready(
        self,
        *,
        config: dict[str, Any] | None = None,
        secrets_payload: dict[str, Any] | None = None,
    ) -> bool:
        config = dict(config or {})
        secrets_payload = dict(secrets_payload or {})
        if str(config.get("client_id") or "").strip() and str(secrets_payload.get("client_secret") or "").strip():
            return True
        return bool(
            (self.settings.google_client_id_configured and self.settings.google_client_secret_configured)
            or (
                str(os.getenv("LAWCOPILOT_GOOGLE_CLIENT_ID", "")).strip()
                and str(os.getenv("LAWCOPILOT_GOOGLE_CLIENT_SECRET", "")).strip()
            )
        )

    def _assistant_legacy_fields(self, spec: ConnectorSpec, *, query: str, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        connector_id = str(spec.id or "")
        if connector_id in {"gmail", "calendar", "drive"}:
            if self._assistant_google_oauth_client_ready():
                return []
            return [
                {"key": "client_id", "label": "Client ID", "kind": "text", "target": "config", "required": True},
                {"key": "client_secret", "label": "Client secret", "kind": "text", "target": "secret", "required": True, "secret": True},
            ]
        if connector_id in {"outlook-mail", "outlook-calendar"}:
            return [
                {"key": "client_id", "label": "Client ID", "kind": "text", "target": "config", "required": True},
            ]
        if connector_id == "telegram":
            mode = self._assistant_legacy_telegram_mode(query=query, metadata=metadata)
            if mode == "web":
                return []
            return [
                {"key": "bot_token", "label": "Bot token", "kind": "text", "target": "secret", "required": True, "secret": True},
                {"key": "allowed_user_id", "label": "İzin verilecek Telegram kullanıcı ID", "kind": "text", "target": "config", "required": True},
            ]
        if connector_id == "whatsapp":
            mode = self._assistant_legacy_whatsapp_mode(query=query, metadata=metadata)
            if mode == "business_cloud":
                return [
                    {"key": "business_label", "label": "İşletme adı", "kind": "text", "target": "config", "required": True},
                    {"key": "phone_number_id", "label": "Phone number ID", "kind": "text", "target": "config", "required": True},
                    {"key": "access_token", "label": "Access token", "kind": "text", "target": "secret", "required": True, "secret": True},
                ]
            return []
        if connector_id == "x":
            return [
                {"key": "client_id", "label": "Client ID", "kind": "text", "target": "config", "required": True},
                {"key": "client_secret", "label": "Client secret", "kind": "text", "target": "secret", "required": True, "secret": True},
            ]
        if connector_id == "linkedin":
            mode = self._assistant_legacy_linkedin_mode(query=query, metadata=metadata)
            if mode == "web":
                return []
            return [
                {"key": "client_id", "label": "Client ID", "kind": "text", "target": "config", "required": True},
                {"key": "client_secret", "label": "Client secret", "kind": "text", "target": "secret", "required": True, "secret": True},
            ]
        if connector_id == "instagram":
            return [
                {"key": "client_id", "label": "Client ID", "kind": "text", "target": "config", "required": True},
                {"key": "client_secret", "label": "Client secret", "kind": "text", "target": "secret", "required": True, "secret": True},
            ]
        return []

    def _assistant_legacy_optional_fields(self, spec: ConnectorSpec) -> list[dict[str, Any]]:
        connector_id = str(spec.id or "")
        if connector_id in {"outlook-mail", "outlook-calendar"}:
            return [
                {
                    "key": "tenant_id",
                    "label": "Kiracı kimliği (tenant ID)",
                    "kind": "text",
                    "target": "config",
                    "required": False,
                }
            ]
        return []

    def _assistant_legacy_field_definition(
        self,
        spec: ConnectorSpec,
        *,
        field_key: str,
        query: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        for field in [*self._assistant_legacy_fields(spec, query=query, metadata=metadata), *self._assistant_legacy_optional_fields(spec)]:
            if str(field.get("key") or "").strip() == field_key:
                return dict(field)
        return None

    def _assistant_legacy_desktop_action(
        self,
        spec: ConnectorSpec,
        *,
        metadata: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        secrets_payload: dict[str, Any] | None = None,
    ) -> tuple[str | None, str | None, str | None]:
        connector_id = str(spec.id or "")
        if connector_id in {"gmail", "calendar", "drive"}:
            if not self._assistant_google_oauth_client_ready(config=config, secrets_payload=secrets_payload):
                return (
                    None,
                    None,
                    "Google hesabını bağlamak için önce kurulum ekranındaki Google bölümünü açıp OAuth istemcisinin hazır olduğunu doğrula.",
                )
            return (
                "start_google_auth",
                "Google izin ekranını aç",
                "Google hesabında izin onayını verdikten sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
            )
        if connector_id in {"outlook-mail", "outlook-calendar"}:
            return (
                "start_outlook_auth",
                "Microsoft izin ekranını aç",
                "Microsoft hesabında izin onayını verdikten sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
            )
        if connector_id == "telegram":
            mode = self._assistant_legacy_telegram_mode(query="", metadata=metadata)
            if mode == "web":
                return (
                    "start_telegram_web_link",
                    "Telegram Web oturumunu aç",
                    "Telegram Web penceresinde giriş yaptıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
                )
            return (
                "save_telegram",
                "Telegram ayarını kaydet",
                "Bot ayarı kaydedildikten sonra ilk mesajını botuna gönderip 'Durumu kontrol et' yaz.",
            )
        if connector_id == "whatsapp":
            mode = self._assistant_legacy_whatsapp_mode(query="", metadata=metadata)
            if mode == "business_cloud":
                return (
                    "save_whatsapp_business",
                    "WhatsApp Business ayarını kaydet",
                    "Meta doğrulaması tamamlanınca bu sohbete dönüp 'Durumu kontrol et' yaz.",
                )
            return (
                "start_whatsapp_web_link",
                "WhatsApp QR kurulumunu aç",
                "QR kodu telefonundan okuttuktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
            )
        if connector_id == "x":
            return (
                "start_x_auth",
                "X izin ekranını aç",
                "X hesabında izin onayını verdikten sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
            )
        if connector_id == "linkedin":
            mode = self._assistant_legacy_linkedin_mode(query="", metadata=metadata)
            if mode == "web":
                return (
                    "start_linkedin_web_link",
                    "LinkedIn Web oturumunu aç",
                    "LinkedIn Web penceresinde giriş yaptıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
                )
            return (
                "start_linkedin_auth",
                "LinkedIn izin ekranını aç",
                "LinkedIn hesabında izin onayını verdikten sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
            )
        if connector_id == "instagram":
            return (
                "start_instagram_auth",
                "Instagram izin ekranını aç",
                "Meta izin adımını tamamladıktan sonra bu sohbete dönüp 'Durumu kontrol et' yaz.",
            )
        return (None, None, None)

    def _assistant_legacy_config_patch(
        self,
        spec: ConnectorSpec,
        *,
        config: dict[str, Any],
        secrets_payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        connector_id = str(spec.id or "")
        now_iso = datetime.now(timezone.utc).isoformat()
        if connector_id in {"gmail", "calendar", "drive"}:
            client_id = str(config.get("client_id") or "").strip()
            client_secret = str(secrets_payload.get("client_secret") or "").strip()
            if not client_id and not client_secret:
                return {}
            return {
                "google": {
                    "enabled": True,
                    "clientId": client_id,
                    "clientSecret": client_secret,
                }
            }
        if connector_id in {"outlook-mail", "outlook-calendar"}:
            return {
                "outlook": {
                    "enabled": True,
                    "clientId": str(config.get("client_id") or "").strip(),
                    "tenantId": str(config.get("tenant_id") or "common").strip() or "common",
                }
            }
        if connector_id == "telegram":
            mode = self._assistant_legacy_telegram_mode(query="", metadata=metadata)
            if mode == "web":
                return {
                    "telegram": {
                        "enabled": True,
                        "mode": "web",
                        "webSessionName": str(config.get("web_session_name") or "default").strip() or "default",
                        "configuredAt": now_iso,
                        "validationStatus": "pending",
                    }
                }
            return {
                "telegram": {
                    "enabled": True,
                    "mode": "bot",
                    "botToken": str(secrets_payload.get("bot_token") or "").strip(),
                    "allowedUserId": str(config.get("allowed_user_id") or "").strip(),
                    "botUsername": str(config.get("bot_username") or "").strip(),
                    "configuredAt": now_iso,
                    "validationStatus": "pending",
                }
            }
        if connector_id == "whatsapp":
            mode = self._assistant_legacy_whatsapp_mode(query="", metadata=metadata)
            if mode == "business_cloud":
                return {
                    "whatsapp": {
                        "enabled": True,
                        "mode": "business_cloud",
                        "businessLabel": str(config.get("business_label") or "").strip(),
                        "phoneNumberId": str(config.get("phone_number_id") or "").strip(),
                        "accessToken": str(secrets_payload.get("access_token") or "").strip(),
                        "configuredAt": now_iso,
                        "validationStatus": "pending",
                    }
                }
            return {
                "whatsapp": {
                    "enabled": True,
                    "mode": "web",
                    "webSessionName": str(config.get("web_session_name") or "default").strip() or "default",
                    "configuredAt": now_iso,
                    "validationStatus": "pending",
                }
            }
        if connector_id == "x":
            return {
                "x": {
                    "enabled": True,
                    "clientId": str(config.get("client_id") or "").strip(),
                    "clientSecret": str(secrets_payload.get("client_secret") or "").strip(),
                }
            }
        if connector_id == "linkedin":
            mode = self._assistant_legacy_linkedin_mode(query="", metadata=metadata)
            if mode == "web":
                return {
                    "linkedin": {
                        "enabled": True,
                        "mode": "web",
                        "webSessionName": str(config.get("web_session_name") or "default").strip() or "default",
                        "configuredAt": now_iso,
                        "validationStatus": "pending",
                    }
                }
            return {
                "linkedin": {
                    "enabled": True,
                    "mode": "official",
                    "clientId": str(config.get("client_id") or "").strip(),
                    "clientSecret": str(secrets_payload.get("client_secret") or "").strip(),
                }
            }
        if connector_id == "instagram":
            return {
                "instagram": {
                    "enabled": True,
                    "clientId": str(config.get("client_id") or "").strip(),
                    "clientSecret": str(secrets_payload.get("client_secret") or "").strip(),
                    "pageNameHint": str(config.get("page_name_hint") or "").strip(),
                    "configuredAt": now_iso,
                    "validationStatus": "pending",
                }
            }
        return {}

    def _assistant_legacy_setup_metadata(
        self,
        spec: ConnectorSpec,
        *,
        thread_id: int,
        query: str,
        access_level: str,
        existing_metadata: dict[str, Any] | None = None,
        missing_fields: list[dict[str, Any]],
        config: dict[str, Any] | None = None,
        secrets_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        recipe = self._assistant_legacy_recipe(spec.id)
        metadata = dict(existing_metadata or {})
        if spec.id == "whatsapp":
            metadata["whatsapp_mode"] = self._assistant_legacy_whatsapp_mode(query=query, metadata=metadata)
        if spec.id == "telegram":
            metadata["telegram_mode"] = self._assistant_legacy_telegram_mode(query=query, metadata=metadata)
        if spec.id == "linkedin":
            metadata["linkedin_mode"] = self._assistant_legacy_linkedin_mode(query=query, metadata=metadata)
        desktop_action, desktop_cta_label, desktop_action_help = self._assistant_legacy_desktop_action(
            spec,
            metadata=metadata,
            config=config,
            secrets_payload=secrets_payload,
        )
        pending_field = missing_fields[0] if missing_fields else None
        metadata.update(
            {
                "access_level": access_level,
                "requested_scopes": self._assistant_scopes_for_access(spec, access_level),
                "live_mode_requested": True,
                "pending_field": pending_field,
                "setup_mode": "legacy_desktop",
                "next_step": (
                    "Kurulumu tamamlamak için sıradaki bilgiyi paylaş."
                    if pending_field
                    else str(desktop_action_help or recipe.get("next_step") or "Son adımı başlatmaya hazırım.")
                ),
                "review_summary": list(recipe.get("review_summary") or []),
                "suggested_replies": list(
                    ["Durumu kontrol et", "Vazgeç"]
                    if not pending_field
                    else []
                ),
                "deep_link_path": self._assistant_legacy_deep_link(spec.id),
                "skill": self._assistant_legacy_skill_summary(spec, recipe),
                "capabilities": self._assistant_legacy_capabilities(spec.id, None),
                "desktop_action": desktop_action,
                "desktop_cta_label": desktop_cta_label,
                "desktop_action_help": desktop_action_help,
            }
        )
        return metadata

    def _start_assistant_legacy_setup(self, *, spec: ConnectorSpec, thread_id: int, query: str, actor: str) -> dict[str, Any]:
        recipe = self._assistant_legacy_recipe(spec.id)
        legacy_status = self._legacy_status_map().get(spec.id)
        service_name = str(recipe.get("service_name") or spec.name)
        skill = self._assistant_legacy_skill_summary(spec, recipe)
        if legacy_status and bool(legacy_status.get("connected")):
            return {
                "content": self._assistant_legacy_connected_message(spec, legacy_status),
                "status": "connected",
                "connector": spec.model_dump(mode="json"),
                "connection": None,
                "generated_request": None,
                "assistant_setup": None,
                "authorization_url": None,
                "deep_link_path": self._assistant_legacy_deep_link(spec.id),
                "suggested_replies": list(recipe.get("recommended_prompts") or self._assistant_post_connect_suggestions(spec)),
                "generated_from": "assistant_integration_orchestration",
            }
        access_level = self._assistant_infer_access_level(_normalize_text(query), spec)
        missing_fields = self._assistant_legacy_fields(spec, query=query)
        metadata = self._assistant_legacy_setup_metadata(
            spec,
            thread_id=thread_id,
            query=query,
            access_level=access_level,
            existing_metadata={"skill": skill},
            missing_fields=missing_fields,
            config={},
            secrets_payload={},
        )
        pending_field = dict(metadata.get("pending_field") or {})
        setup_status = "collecting_input" if pending_field else "ready_for_desktop_action"
        created = self.repo.upsert_assistant_setup(
            self.settings.office_id,
            thread_id=thread_id,
            connector_id=spec.id,
            service_name=service_name,
            request_text=query,
            status=setup_status,
            missing_fields=missing_fields,
            collected_config={},
            secret_blob=self.secret_box.seal_json({}),
            metadata=metadata,
            created_by=actor,
        )
        setup = self._serialize_assistant_setup(created)
        if pending_field:
            content = f"{service_name} kurulumunu sohbetten birlikte tamamlayalım. {self._assistant_prompt_for_field(spec, pending_field)}"
        else:
            content = (
                f"{service_name} bağlantısı için gereken bilgileri hazırladım. "
                f"{str(metadata.get('next_step') or '')}".strip()
            )
        return {
            "content": content,
            "status": setup_status,
            "connector": spec.model_dump(mode="json"),
            "connection": None,
            "generated_request": None,
            "assistant_setup": setup,
            "authorization_url": None,
            "deep_link_path": metadata["deep_link_path"],
            "suggested_replies": list(metadata["suggested_replies"] or []),
            "generated_from": "assistant_integration_orchestration",
        }

    def _resume_assistant_legacy_setup(self, setup: dict[str, Any], *, actor: str, auto_run_desktop_action: bool = False) -> dict[str, Any]:
        connector_id = str(setup.get("connector_id") or "")
        spec = self._require_connector(connector_id)
        recipe = self._assistant_legacy_recipe(connector_id)

        def serialize(current_setup: dict[str, Any] | None) -> dict[str, Any] | None:
            payload = self._serialize_assistant_setup(current_setup)
            if auto_run_desktop_action and payload:
                return {**payload, "auto_run_desktop_action": True}
            return payload

        legacy_status = self._legacy_status_map().get(connector_id)
        if legacy_status and bool(legacy_status.get("connected")):
            completed = self.repo.complete_assistant_setup(
                self.settings.office_id,
                int(setup["id"]),
                status="completed",
                metadata={
                    **dict(setup.get("metadata") or {}),
                    "capabilities": self._assistant_legacy_capabilities(connector_id, legacy_status),
                    "suggested_replies": list(recipe.get("recommended_prompts") or self._assistant_post_connect_suggestions(spec)),
                },
            )
            return {
                "content": self._assistant_legacy_connected_message(spec, legacy_status),
                "status": "connected",
                "connector": spec.model_dump(mode="json"),
                "connection": None,
                "generated_request": None,
                "assistant_setup": serialize(completed),
                "authorization_url": None,
                "deep_link_path": self._assistant_legacy_deep_link(connector_id),
                "suggested_replies": list(recipe.get("recommended_prompts") or self._assistant_post_connect_suggestions(spec)),
                "generated_from": "assistant_integration_orchestration",
            }

        metadata = dict(setup.get("metadata") or {})
        pending_field = dict(metadata.get("pending_field") or {})
        if pending_field:
            return {
                "content": self._assistant_prompt_for_field(spec, pending_field),
                "status": "collecting_input",
                "connector": spec.model_dump(mode="json"),
                "connection": None,
                "generated_request": None,
                "assistant_setup": serialize(setup),
                "authorization_url": None,
                "deep_link_path": str(metadata.get("deep_link_path") or self._assistant_legacy_deep_link(connector_id)),
                "suggested_replies": [],
                "generated_from": "assistant_integration_orchestration",
            }
        desktop_cta_label = str(metadata.get("desktop_cta_label") or "").strip()
        desktop_action_help = str(metadata.get("desktop_action_help") or "").strip()
        if desktop_cta_label:
            content = f"{str(recipe.get('service_name') or spec.name)} için son adım hazır. Şimdi '{desktop_cta_label}' adımını başlatabilirsin."
            if desktop_action_help:
                content = f"{content} {desktop_action_help}".strip()
            return {
                "content": content,
                "status": str(setup.get("status") or "ready_for_desktop_action"),
                "connector": spec.model_dump(mode="json"),
                "connection": None,
                "generated_request": None,
                "assistant_setup": serialize(setup),
                "authorization_url": None,
                "deep_link_path": str(metadata.get("deep_link_path") or self._assistant_legacy_deep_link(connector_id)),
                "suggested_replies": list(metadata.get("suggested_replies") or recipe.get("suggested_replies") or ["Durumu kontrol et", "Vazgeç"]),
                "generated_from": "assistant_integration_orchestration",
            }
        return {
            "content": (
                f"{str(recipe.get('service_name') or spec.name)} kurulumu henüz tamamlanmış görünmüyor. "
                f"{str(metadata.get('next_step') or 'Hazır olduğunda son adımı başlatıp ardından Durumu kontrol et yazabilirsin.')}"
            ),
            "status": str(setup.get("status") or "ready_for_desktop_action"),
            "connector": spec.model_dump(mode="json"),
            "connection": None,
            "generated_request": None,
            "assistant_setup": serialize(setup),
            "authorization_url": None,
            "deep_link_path": str(metadata.get("deep_link_path") or self._assistant_legacy_deep_link(connector_id)),
            "suggested_replies": list(metadata.get("suggested_replies") or recipe.get("suggested_replies") or ["Durumu kontrol et", "Vazgeç"]),
            "generated_from": "assistant_integration_orchestration",
        }

    def _is_assistant_integration_intent(self, normalized_query: str) -> bool:
        if any(
            phrase in normalized_query
            for phrase in (
                "kuruluma sohbetten devam",
                "kuruluma devam",
                "tanisma ile devam",
                "tanismaya gec",
                "kisa bir tanisma yapalim",
            )
        ):
            return False
        verbs = (
            "connect",
            "bagla",
            "entegre",
            "integrate",
            "link",
            "ekle",
            "add",
            "kur",
            "bağla",
            "baglamak",
            "bağlamak",
            "link a new service",
            "takip et",
            "izle",
            "monitor",
            "watch",
        )
        nouns = (
            "slack",
            "notion",
            "google",
            "gmail",
            "drive",
            "calendar",
            "outlook",
            "telegram",
            "whatsapp",
            "instagram",
            "linkedin",
            "twitter",
            "github",
            "jira",
            "trello",
            "hubspot",
            "discord",
            "tiktok",
            "dropbox",
            "crm",
            "api",
            "service",
            "servis",
            "database",
            "veritabani",
            "postgres",
            "elastic",
            "entegrasyon",
            "integration",
            "workspace",
            "web",
            "website",
            "site",
            "sayfa",
            "web sayfasi",
            "web sayfası",
            "resmi gazete",
        )
        has_verb = any(verb in normalized_query for verb in verbs)
        if not has_verb:
            return False
        if self._assistant_match_legacy_connector(normalized_query) is not None:
            return True
        if any(noun in normalized_query for noun in nouns):
            return True
        service_name = self._extract_service_name_from_prompt(normalized_query, normalized_prompt=normalized_query)
        return bool(service_name and service_name.lower() not in {"custom service", "servis", "service"})

    def _is_assistant_setup_cancel(self, normalized_query: str) -> bool:
        return any(
            token in normalized_query
            for token in ("iptal", "vazgec", "vazgeç", "cancel", "stop", "bosver", "boşver")
        )

    def _is_affirmative(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("evet", "onay", "approve", "approved", "tamam", "olur", "yes"))

    def _is_negative(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("hayir", "hayır", "no", "reddet", "istemiyorum"))

    def _assistant_infer_access_level(self, normalized_query: str, spec: ConnectorSpec) -> str:
        if any(token in normalized_query for token in ("admin", "tam yetki", "full access", "genis yetki", "geniş yetki")):
            return "admin_like"
        if any(
            token in normalized_query
            for token in ("write", "yaz", "gonder", "gönder", "olustur", "oluştur", "guncelle", "güncelle")
        ):
            return "read_write"
        return spec.default_access_level

    def _assistant_scopes_for_access(self, spec: ConnectorSpec, access_level: str) -> list[str]:
        scopes = list(spec.auth_config.default_scopes or spec.scopes)
        if access_level == "admin_like":
            return scopes
        if access_level == "read_write":
            filtered = [scope for scope in scopes if "delete" not in scope.lower()]
            return filtered or scopes
        filtered = [
            scope
            for scope in scopes
            if not any(marker in scope.lower() for marker in ("write", "update", "delete", "chat:write", "send"))
        ]
        return filtered or scopes

    def _assistant_deep_link(
        self,
        *,
        connector_id: str | None,
        connection_id: int | None = None,
        setup_id: int | None = None,
    ) -> str:
        params: list[str] = []
        if connector_id:
            params.append(f"connector={connector_id}")
        if connection_id:
            params.append(f"connection={connection_id}")
        if setup_id:
            params.append(f"setup={setup_id}")
        suffix = f"?{'&'.join(params)}" if params else ""
        return f"/integrations{suffix}"

    def _assistant_prompt_for_field(self, spec: ConnectorSpec, field: dict[str, Any]) -> str:
        label = str(field.get("label") or field.get("key") or "alan")
        connector_name = spec.name
        helper = self._assistant_field_helper_text(spec, field)
        lines = [f"{connector_name} kurulumu için sıradaki bilgi: {label}."]
        if helper:
            lines.append(helper)
        lines.append("Yalnızca bu değeri tek mesaj olarak göndermen yeterli.")
        return " ".join(line for line in lines if line).strip()

    def _assistant_field_helper_text(self, spec: ConnectorSpec, field: dict[str, Any]) -> str:
        label = str(field.get("label") or field.get("key") or "")
        examples = {
            "client_id": "Servis panelindeki OAuth uygulama Client ID değerini yazabilirsin.",
            "client_secret": "Bu değer sohbet geçmişine açık metin olarak kaydedilmez; güvenli kasada mühürlenir.",
            "integration_token": "Notion integration tokenini tek satır olarak gönderebilirsin.",
            "api_key": "API anahtarını tek satır olarak gönderebilirsin.",
            "password": "Parolayı tek satır olarak gönderebilirsin.",
            "base_url": "Tam URL kullan: https://api.ornek-servis.com",
            "redirect_uri": "Redirect URI tam olarak provider panelindeki değerle eşleşmeli.",
            "workspace_label": "Örneğin: Hukuk Operasyon Workspace",
            "service_label": "Örneğin: Müvekkil CRM API",
            "connection_label": "Örneğin: Üretim PostgreSQL",
            "host": "Host veya DNS adını yazabilirsin.",
            "url": "Tam web adresini yazabilirsin. Örneğin: https://www.resmigazete.gov.tr/",
            "watch_label": "Örneğin: Resmî Gazete",
            "check_interval_minutes": "Örneğin 1440 = günde bir kez, 60 = saatte bir kez.",
            "bot_token": "BotFather üzerinden aldığın bot tokenini tek satır olarak gönderebilirsin.",
            "allowed_user_id": "Telegram kullanıcı ID değerini yazabilirsin. İstersen önce botuna bir mesaj gönderip sonra bu değeri paylaş.",
            "phone_number_id": "Meta panelindeki Phone number ID değerini yazabilirsin.",
            "business_label": "Örneğin: Hukuk Bürosu WhatsApp hattı",
            "tenant_id": "Kurumsal tenant kullanmıyorsan bu adımı atlayabiliriz; varsayılan değer 'common' olur.",
        }
        if field.get("key") == "client_id" and "client key" in _normalize_text(label):
            examples["client_id"] = "Servis panelindeki OAuth uygulama Client key değerini yazabilirsin."
        if str(spec.id or "") in {"gmail", "calendar", "drive"}:
            if field.get("key") == "client_id":
                examples["client_id"] = "Google Cloud Console içindeki OAuth istemcisinin Client ID değerini yazabilirsin."
            if field.get("key") == "client_secret":
                examples["client_secret"] = "Google Cloud Console içindeki OAuth istemcisinin Client secret değerini güvenli şekilde kaydederim; açık metin olarak saklanmaz."
        return examples.get(str(field.get("key") or ""), str(field.get("help_text") or "").strip())

    def _assistant_setup_help_intent(self, normalized_query: str) -> str | None:
        field_help_tokens = (
            "nereden al",
            "nereden bul",
            "nerede bul",
            "hangi ekrandan",
            "hangi sayfadan",
            "hangi panelden",
            "nereden girecegim",
            "nereden gireceğim",
            "nereden yapacagim",
            "nereden yapacağım",
        )
        if any(token in normalized_query for token in field_help_tokens):
            return "field_source"
        step_tokens = (
            "adim adim",
            "adım adım",
            "sirayla anlat",
            "sırayla anlat",
            "tek tek anlat",
            "detayli anlat",
            "detaylı anlat",
        )
        if any(token in normalized_query for token in step_tokens):
            return "steps"
        clarify_tokens = (
            "nasil yap",
            "nasıl yap",
            "ne yapmam lazim",
            "ne yapmam lazım",
            "tam anlayamadim",
            "tam anlayamadım",
            "anlamadim",
            "anlamadım",
            "acikla",
            "açıkla",
            "yardim et",
            "yardım et",
            "ne yapayim",
            "ne yapayım",
            "siradaki adim ne",
            "sıradaki adım ne",
            "simdi ne yapacagim",
            "şimdi ne yapacağım",
        )
        if any(token in normalized_query for token in clarify_tokens):
            return "clarify"
        return None

    def _assistant_google_setup_steps(self, *, field_key: str | None = None) -> list[str]:
        steps = [
            "Google Cloud Console'u aç.",
            "Yeni bir proje oluştur ya da mevcut projeyi seç.",
            "APIs & Services > Credentials bölümüne gir.",
        ]
        if field_key in {"client_id", "client_secret"}:
            steps.append("Create Credentials > OAuth client ID adımını aç.")
            steps.append("Gerekirse önce OAuth consent screen yapılandırmasını tamamla.")
            steps.append("Uygulama türü olarak Desktop app seç.")
            if field_key == "client_id":
                steps.append("Oluşan Client ID değerini bana tek mesaj olarak gönder.")
            else:
                steps.append("Oluşan Client secret değerini bana tek mesaj olarak gönder.")
            return steps
        steps.extend(
            [
                "Google izin ekranını aç butonuna bas.",
                "Bağlamak istediğin Google hesabını seç.",
                "Gmail, Takvim, Drive ve YouTube oynatma listesi izinlerini onayla.",
                "Bu sohbete dönüp 'Durumu kontrol et' yaz.",
            ]
        )
        return steps

    def _assistant_legacy_setup_help_text(self, spec: ConnectorSpec, setup: dict[str, Any], *, query: str) -> str:
        metadata = dict(setup.get("metadata") or {})
        recipe = self._assistant_legacy_recipe(str(spec.id or ""))
        service_name = str(recipe.get("service_name") or spec.name)
        pending_field = dict(metadata.get("pending_field") or {})
        help_intent = self._assistant_setup_help_intent(_normalize_text(query)) or "clarify"
        lines: list[str] = []

        def append_unique(text: str) -> None:
            normalized = _normalize_text(text)
            if not normalized:
                return
            if any(_normalize_text(existing) == normalized for existing in lines):
                return
            lines.append(text.strip())

        if pending_field:
            label = str(pending_field.get("label") or pending_field.get("key") or "alan")
            append_unique(f"{service_name} kurulumunu birlikte tamamlayalım. Şu an ihtiyacımız olan bilgi: {label}.")
            if str(spec.id or "") in {"gmail", "calendar", "drive"}:
                append_unique("Bunu Google Cloud Console içinden alacağız.")
                for index, step in enumerate(self._assistant_google_setup_steps(field_key=str(pending_field.get("key") or "")), start=1):
                    append_unique(f"{index}. {step}")
            else:
                helper = self._assistant_field_helper_text(spec, pending_field)
                if helper:
                    append_unique(helper)
                if help_intent == "steps":
                    append_unique("Hazır olduğunda yalnızca bu değeri tek mesaj olarak gönder; devamını ben yöneteceğim.")
                else:
                    append_unique(f"Hazır olduğunda yalnızca {label} değerini tek mesaj olarak gönder.")
            deep_link_path = str(metadata.get("deep_link_path") or "")
            if deep_link_path:
                append_unique("İstersen ilgili kurulum bölümünü de açıp alanları oradan kontrol edebilirsin.")
            return "\n".join(lines)

        append_unique(f"{service_name} kurulumunu şu sırayla tamamlayacağız:")
        if str(spec.id or "") in {"gmail", "calendar", "drive"}:
            for index, step in enumerate(self._assistant_google_setup_steps(), start=1):
                append_unique(f"{index}. {step}")
        else:
            step_index = 1
            cta_label = str(metadata.get("desktop_cta_label") or "")
            if cta_label:
                append_unique(f"{step_index}. {cta_label} butonuna bas.")
                step_index += 1
            for summary in list(metadata.get("review_summary") or recipe.get("review_summary") or []):
                append_unique(f"{step_index}. {summary}")
                step_index += 1
            desktop_action_help = str(metadata.get("desktop_action_help") or "")
            if desktop_action_help:
                append_unique(f"{step_index}. {desktop_action_help}")
                step_index += 1
            if not any("durumu kontrol et" in _normalize_text(item) for item in lines):
                append_unique(f"{step_index}. Bitince bu sohbete dönüp 'Durumu kontrol et' yaz.")
        return "\n".join(lines)

    def _assistant_query_requests_field_retry(self, normalized_query: str) -> bool:
        if not normalized_query:
            return False
        retry_tokens = (
            "yanlis",
            "yanlış",
            "hatali",
            "hatalı",
            "tekrar",
            "yeniden",
            "duzelt",
            "düzelt",
            "degistir",
            "değiştir",
            "bir daha",
        )
        return any(token in normalized_query for token in retry_tokens)

    def _assistant_query_requests_legacy_proceed(
        self,
        normalized_query: str,
        *,
        planner_hint: dict[str, Any] | None = None,
    ) -> bool:
        followup_intent = str((planner_hint or {}).get("followup_intent") or "").strip().lower()
        if followup_intent == "execute_desktop_action":
            return True
        if not normalized_query:
            return False
        proceed_tokens = (
            "bagla",
            "bağla",
            "devam et",
            "baslat",
            "başlat",
            "ac",
            "aç",
            "izin ekranini ac",
            "izin ekranını aç",
            "onay ekranini ac",
            "onay ekranını aç",
        )
        return any(token in normalized_query for token in proceed_tokens)

    def _assistant_legacy_field_key_from_query(
        self,
        spec: ConnectorSpec,
        *,
        query: str,
        metadata: dict[str, Any] | None = None,
        planner_hint: dict[str, Any] | None = None,
    ) -> str:
        planned_field_key = str((planner_hint or {}).get("field_key") or "").strip().lower()
        if planned_field_key and self._assistant_legacy_field_definition(spec, field_key=planned_field_key, query=query, metadata=metadata):
            return planned_field_key
        normalized = _normalize_text(query)
        if any(token in normalized for token in ("tenant", "kiraci", "kiracı")):
            if self._assistant_legacy_field_definition(spec, field_key="tenant_id", query=query, metadata=metadata):
                return "tenant_id"
        if any(token in normalized for token in ("client secret", "secret", "istemci gizli")):
            if self._assistant_legacy_field_definition(spec, field_key="client_secret", query=query, metadata=metadata):
                return "client_secret"
        if any(token in normalized for token in ("client id", "istemci kimligi", "istemci kimliği", "uygulama kimligi", "uygulama kimliği")):
            if self._assistant_legacy_field_definition(spec, field_key="client_id", query=query, metadata=metadata):
                return "client_id"
        if any(token in normalized for token in ("bot token", "bot anahtari", "bot anahtarı")):
            if self._assistant_legacy_field_definition(spec, field_key="bot_token", query=query, metadata=metadata):
                return "bot_token"
        return ""

    def _assistant_parse_field_value(self, field: dict[str, Any], query: str) -> Any:
        cleaned = str(query or "").strip()
        if not cleaned:
            raise ValueError("integration_setup_value_missing")
        kind = str(field.get("kind") or "text")
        field_key = str(field.get("key") or "")
        if field_key == "tenant_id":
            guid_match = re.search(
                r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
                cleaned,
            )
            if guid_match:
                return guid_match.group(0)
            return cleaned
        if field_key == "auth_mode":
            normalized = _normalize_text(cleaned)
            mapping = {
                "api key": "api_key",
                "api_key": "api_key",
                "bearer": "bearer",
                "basic": "basic",
                "none": "none",
                "kimlik dogrulama yok": "none",
            }
            for candidate, value in mapping.items():
                if candidate in normalized:
                    return value
            raise ValueError("integration_setup_auth_mode_invalid")
        if kind == "select":
            normalized = _normalize_text(cleaned)
            for option in list(field.get("options") or []):
                option_value = str(option.get("value") or "").strip()
                option_label = _normalize_text(str(option.get("label") or ""))
                if normalized == _normalize_text(option_value) or normalized == option_label or option_label in normalized:
                    return option_value
            raise ValueError("integration_setup_select_value_invalid")
        if kind == "boolean":
            normalized = _normalize_text(cleaned)
            if any(token in normalized for token in ("evet", "yes", "true", "on", "acik", "açık")):
                return True
            if any(token in normalized for token in ("hayir", "hayır", "no", "false", "off", "kapali", "kapalı")):
                return False
            raise ValueError("integration_setup_boolean_invalid")
        if kind == "number":
            match = re.search(r"-?\d+", cleaned)
            if not match:
                raise ValueError("integration_setup_number_invalid")
            return int(match.group(0))
        if kind == "url":
            match = re.search(r"https?://[^\s]+", cleaned)
            value = match.group(0) if match else cleaned
            return value.strip()
        return cleaned

    def _assistant_legacy_reopen_field(
        self,
        setup: dict[str, Any],
        *,
        spec: ConnectorSpec,
        actor: str,
        field: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = dict(setup.get("metadata") or {})
        try:
            collected_secrets = self.secret_box.open_json(str(setup.get("secret_blob") or ""))
        except ValueError:
            collected_secrets = {}
        collected_config = dict(setup.get("collected_config") or {})
        target_store = collected_secrets if str(field.get("target") or "config") == "secret" else collected_config
        target_store.pop(str(field.get("key") or ""), None)
        next_missing = self._assistant_legacy_fields(
            spec,
            query=str(setup.get("request_text") or ""),
            metadata=metadata,
        )
        next_missing = [
            item
            for item in next_missing
            if _empty_value(
                (collected_secrets if str(item.get("target") or "config") == "secret" else collected_config).get(str(item.get("key") or ""))
            )
        ]
        next_metadata = self._assistant_legacy_setup_metadata(
            spec,
            thread_id=int(setup["thread_id"]),
            query=str(setup.get("request_text") or ""),
            access_level=str(metadata.get("access_level") or spec.default_access_level or "read_only"),
            existing_metadata={**metadata},
            missing_fields=next_missing,
            config=collected_config,
            secrets_payload=collected_secrets,
        )
        next_metadata["pending_field"] = dict(field)
        next_metadata["next_step"] = "Kurulumu tamamlamak için sıradaki bilgiyi paylaş."
        updated = self.repo.upsert_assistant_setup(
            self.settings.office_id,
            thread_id=int(setup["thread_id"]),
            setup_id=int(setup["id"]),
            connector_id=spec.id,
            service_name=str(setup.get("service_name") or spec.name),
            request_text=str(setup.get("request_text") or ""),
            status="collecting_input",
            missing_fields=next_missing,
            collected_config=collected_config,
            secret_blob=self.secret_box.seal_json(collected_secrets),
            metadata=next_metadata,
            created_by=actor,
        )
        return {
            "content": self._assistant_prompt_for_field(spec, field),
            "status": "collecting_input",
            "connector": spec.model_dump(mode="json"),
            "connection": None,
            "generated_request": None,
            "assistant_setup": self._serialize_assistant_setup(updated),
            "authorization_url": None,
            "deep_link_path": dict(updated.get("metadata") or {}).get("deep_link_path"),
            "suggested_replies": [],
            "generated_from": "assistant_integration_orchestration",
        }

    def _assistant_legacy_apply_field_value(
        self,
        setup: dict[str, Any],
        *,
        spec: ConnectorSpec,
        actor: str,
        field: dict[str, Any],
        query: str,
    ) -> dict[str, Any]:
        metadata = dict(setup.get("metadata") or {})
        try:
            collected_secrets = self.secret_box.open_json(str(setup.get("secret_blob") or ""))
        except ValueError:
            collected_secrets = {}
        collected_config = dict(setup.get("collected_config") or {})
        value = self._assistant_parse_field_value(field, query)
        if str(field.get("target") or "config") == "secret":
            collected_secrets[str(field.get("key") or "")] = value
        else:
            collected_config[str(field.get("key") or "")] = value
        next_missing = self._assistant_legacy_fields(
            spec,
            query=str(setup.get("request_text") or query),
            metadata=metadata,
        )
        next_missing = [
            item
            for item in next_missing
            if _empty_value(
                (collected_secrets if str(item.get("target") or "config") == "secret" else collected_config).get(str(item.get("key") or ""))
            )
        ]
        next_metadata = self._assistant_legacy_setup_metadata(
            spec,
            thread_id=int(setup["thread_id"]),
            query=str(setup.get("request_text") or query),
            access_level=str(metadata.get("access_level") or spec.default_access_level or "read_only"),
            existing_metadata={**metadata},
            missing_fields=next_missing,
            config=collected_config,
            secrets_payload=collected_secrets,
        )
        updated = self.repo.upsert_assistant_setup(
            self.settings.office_id,
            thread_id=int(setup["thread_id"]),
            setup_id=int(setup["id"]),
            connector_id=spec.id,
            service_name=str(setup.get("service_name") or spec.name),
            request_text=str(setup.get("request_text") or ""),
            status="collecting_input" if next_missing else "ready_for_desktop_action",
            missing_fields=next_missing,
            collected_config=collected_config,
            secret_blob=self.secret_box.seal_json(collected_secrets),
            metadata=next_metadata,
            created_by=actor,
        )
        next_pending = dict((updated.get("metadata") or {}).get("pending_field") or {})
        if next_pending:
            return {
                "content": self._assistant_prompt_for_field(spec, next_pending),
                "status": "collecting_input",
                "connector": spec.model_dump(mode="json"),
                "connection": None,
                "generated_request": None,
                "assistant_setup": self._serialize_assistant_setup(updated),
                "authorization_url": None,
                "deep_link_path": dict(updated.get("metadata") or {}).get("deep_link_path"),
                "suggested_replies": [],
                "generated_from": "assistant_integration_orchestration",
            }
        return self._resume_assistant_legacy_setup(updated, actor=actor)

    def _assistant_missing_required_fields(
        self,
        spec: ConnectorSpec,
        *,
        config: dict[str, Any],
        secrets_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        normalized_config = self._fill_defaults(spec, config)
        items: list[dict[str, Any]] = []
        for field in spec.ui_schema:
            if not field.required:
                continue
            if spec.auth_type == "oauth2" and field.key in {"access_token", "refresh_token"}:
                continue
            source = secrets_payload if field.target == "secret" else normalized_config
            if not _empty_value(source.get(field.key)):
                continue
            items.append(field.model_dump(mode="json"))
        return items

    def _assistant_current_connection(self, connector_id: str) -> dict[str, Any] | None:
        rows = self.repo.list_connections(self.settings.office_id, connector_id=connector_id)
        if not rows:
            return None
        rows.sort(
            key=lambda item: (
                0 if str(item.get("auth_status") or "") == "authenticated" else 1,
                0 if bool(item.get("enabled")) else 1,
                str(item.get("updated_at") or ""),
            ),
            reverse=False,
        )
        return rows[0]

    def _assistant_resolve_connector(
        self,
        *,
        query: str,
        actor: str,
        planner_hint: dict[str, Any] | None = None,
    ) -> tuple[ConnectorSpec | None, dict[str, Any] | None, dict[str, Any] | None]:
        normalized = _normalize_text(query)
        if any(token in normalized for token in ("resmi gazete", "web sayfa", "web sayfasi", "website", "web sitesi", "site", "sayfa")) and any(
            token in normalized for token in ("takip", "izle", "monitor", "watch", "bagla", "bağla")
        ):
            return self._require_connector("web-watch"), None, None
        planned_connector_id = str((planner_hint or {}).get("connector_id") or "").strip().lower()
        if planned_connector_id:
            effective_catalog = self._effective_catalog()
            if planned_connector_id in effective_catalog:
                return self._require_connector(planned_connector_id), None, None
        legacy_spec = self._assistant_match_legacy_connector(normalized)
        if legacy_spec is not None:
            return legacy_spec, None, None
        seed = self._infer_request_seed(IntegrationAutomationRequest(prompt=query))
        if any(token in normalized for token in ("database", "veritabani", "veri tabani")) and not any(
            token in normalized for token in ("postgres", "postgresql", "mysql", "mssql", "sql server", "sqlserver", "elastic", "elasticsearch")
        ):
            return None, None, {
                "service_name": str(seed.get("service_name") or "Veritabani"),
                "request_text": query,
                "awaiting_provider_choice": True,
                "provider_options": ["postgresql", "mysql", "mssql", "elastic", "generic-rest"],
                "next_step": "Önce hangi veri kaynağını bağlayacağımızı seçelim.",
            }
        if any(token in normalized for token in ("crm api", "rest api", "custom api", "ozel api", "özel api")):
            return self._require_connector("generic-rest"), None, None
        if any(token in normalized for token in ("resmi gazete", "web sayfa", "web sayfasi", "website", "web sitesi", "site", "sayfa")):
            return self._require_connector("web-watch"), None, None
        connector_id = _slugify(str(seed.get("service_name") or ""))
        if connector_id in self._effective_catalog():
            return self._require_connector(connector_id), None, None
        generated = self.repo.get_generated_connector(self.settings.office_id, connector_id)
        if generated:
            spec = self._materialize_generated_connector(generated)
            if spec:
                return spec, self._serialize_generated_connector(generated), None
        created = self.create_integration_request(IntegrationAutomationRequest(prompt=query), actor=actor)
        connector_payload = dict(created.get("connector") or {})
        spec = ConnectorSpec.model_validate(connector_payload) if connector_payload else None
        return spec, dict(created.get("generated_request") or {}) or None, None

    def _assistant_requested_connector_hint(self, query: str, *, planner_hint: dict[str, Any] | None = None) -> str:
        planned_connector_id = str((planner_hint or {}).get("connector_id") or "").strip().lower()
        if planned_connector_id:
            return planned_connector_id
        normalized = _normalize_text(query)
        if any(token in normalized for token in ("resmi gazete", "web sayfa", "web sayfasi", "website", "web sitesi", "site", "sayfa")) and any(
            token in normalized for token in ("takip", "izle", "monitor", "watch", "bagla", "bağla")
        ):
            return "web-watch"
        legacy_spec = self._assistant_match_legacy_connector(normalized)
        if legacy_spec is not None:
            return str(legacy_spec.id or "")
        if any(token in normalized for token in ("crm api", "rest api", "custom api", "ozel api", "özel api")):
            return "generic-rest"
        if any(token in normalized for token in ("resmi gazete", "web sayfa", "web sayfasi", "website", "web sitesi", "site", "sayfa")):
            return "web-watch"
        seed = self._infer_request_seed(IntegrationAutomationRequest(prompt=query))
        connector_id = _slugify(str(seed.get("service_name") or ""))
        if connector_id in self._effective_catalog():
            return connector_id
        generated = self.repo.get_generated_connector(self.settings.office_id, connector_id)
        if generated:
            return connector_id
        return ""

    def _start_assistant_setup(
        self,
        *,
        thread_id: int,
        query: str,
        actor: str,
        planner_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        spec, generated_request, clarification = self._assistant_resolve_connector(query=query, actor=actor, planner_hint=planner_hint)
        if clarification:
            created = self.repo.upsert_assistant_setup(
                self.settings.office_id,
                thread_id=thread_id,
                request_text=query,
                status="awaiting_provider_choice",
                service_name=str(clarification.get("service_name") or ""),
                missing_fields=[],
                collected_config={},
                secret_blob=self.secret_box.seal_json({}),
                metadata=clarification,
                created_by=actor,
            )
            setup = self._serialize_assistant_setup(created)
            setup["deep_link_path"] = self._assistant_deep_link(connector_id=None, setup_id=int(created.get("id") or 0))
            return {
                "content": "Bunu hemen bağlayabilmem için önce veri kaynağını seçelim. PostgreSQL, Elastic veya Generic REST API yazabilirsin.",
                "status": "awaiting_provider_choice",
                "connector": None,
                "connection": None,
                "generated_request": None,
                "assistant_setup": setup,
                "authorization_url": None,
                "deep_link_path": setup.get("deep_link_path"),
                "suggested_replies": ["PostgreSQL", "Elastic", "Generic REST API"],
                "generated_from": "assistant_integration_orchestration",
            }

        if not spec:
            return None

        if spec.management_mode == "legacy-desktop":
            return self._start_assistant_legacy_setup(spec=spec, thread_id=thread_id, query=query, actor=actor)

        existing_connection = self._assistant_current_connection(spec.id)
        if existing_connection and str(existing_connection.get("auth_status") or "") == "authenticated" and bool(existing_connection.get("enabled")):
            capabilities = discover_capabilities(existing_connection, spec)
            return {
                "content": self._assistant_connected_message(spec=spec, connection=existing_connection, capabilities=capabilities),
                "status": "connected",
                "connector": spec.model_dump(mode="json"),
                "connection": self._serialize_connection(existing_connection),
                "generated_request": generated_request,
                "assistant_setup": None,
                "authorization_url": None,
                "deep_link_path": self._assistant_deep_link(connector_id=spec.id, connection_id=int(existing_connection["id"])),
                "suggested_replies": [],
                "generated_from": "assistant_integration_orchestration",
            }

        access_level = self._assistant_infer_access_level(_normalize_text(query), spec)
        requested_scopes = self._assistant_scopes_for_access(spec, access_level)
        seeded_config, seeded_secrets = self._assistant_seed_setup_values(spec=spec, query=query)
        base_config = {**seeded_config, **(dict(existing_connection.get("config") or {}) if existing_connection else {})}
        base_secrets = {**seeded_secrets, **(self._secrets_for_connection(existing_connection) if existing_connection else {})}
        missing_fields = self._assistant_missing_required_fields(spec, config=base_config, secrets_payload=base_secrets)
        pending_field = missing_fields[0] if missing_fields else None
        setup_metadata = {
            "access_level": access_level,
            "requested_scopes": requested_scopes,
            "live_mode_requested": not bool(self.settings.connector_dry_run),
            "generated_connector_id": generated_request.get("connector_id") if generated_request else None,
            "generated_request_status": generated_request.get("status") if generated_request else None,
            "pending_field": pending_field,
            "next_step": "Kurulumu tamamlamak icin siradaki bilgiyi paylas.",
            "skill": self._connector_skill_summary(spec),
        }
        created = self.repo.upsert_assistant_setup(
            self.settings.office_id,
            thread_id=thread_id,
            connector_id=spec.id,
            connection_id=int(existing_connection["id"]) if existing_connection else None,
            service_name=spec.name,
            request_text=query,
            status="collecting_input" if pending_field else "ready_to_save",
            missing_fields=missing_fields,
            collected_config=base_config,
            secret_blob=self.secret_box.seal_json(base_secrets),
            metadata=setup_metadata,
            created_by=actor,
        )
        created = self.repo.upsert_assistant_setup(
            self.settings.office_id,
            thread_id=thread_id,
            request_text=query,
            status=str(created.get("status") or "collecting_input"),
            connector_id=spec.id,
            connection_id=int(existing_connection["id"]) if existing_connection else None,
            service_name=spec.name,
            missing_fields=missing_fields,
            collected_config=base_config,
            secret_blob=self.secret_box.seal_json(base_secrets),
            metadata={**setup_metadata, "deep_link_path": self._assistant_deep_link(connector_id=spec.id, connection_id=int(existing_connection["id"]) if existing_connection else None, setup_id=int(created.get("id") or 0))},
            created_by=actor,
            setup_id=int(created.get("id") or 0),
        )
        setup = self._serialize_assistant_setup(created)
        if pending_field:
            prefix = f"{spec.name} bağlantısını senin için hazırladım."
            if generated_request:
                prefix += " Gerekli bağlayıcı arka planda oluşturulup kataloğa eklendi."
            return {
                "content": f"{prefix} {self._assistant_prompt_for_field(spec, pending_field)}",
                "status": "collecting_input",
                "connector": spec.model_dump(mode="json"),
                "connection": self._serialize_connection(existing_connection) if existing_connection else None,
                "generated_request": generated_request,
                "assistant_setup": setup,
                "authorization_url": None,
                "deep_link_path": setup.get("deep_link_path"),
                "suggested_replies": [],
                "generated_from": "assistant_integration_orchestration",
            }
        return self._finalize_assistant_setup(created, actor=actor)

    def _continue_assistant_setup(self, setup: dict[str, Any], *, query: str, actor: str) -> dict[str, Any]:
        normalized = _normalize_text(query)
        planner_hint: dict[str, Any] = {}
        followup_intent = ""
        if isinstance(setup.get("_planner_hint"), dict):
            planner_hint = dict(setup.get("_planner_hint") or {})
            followup_intent = str(planner_hint.get("followup_intent") or "").strip().lower()
        if self._is_assistant_setup_cancel(normalized) or followup_intent == "cancel":
            finished = self.repo.complete_assistant_setup(
                self.settings.office_id,
                int(setup["id"]),
                status="cancelled",
                metadata={**dict(setup.get("metadata") or {}), "cancelled_by": actor},
            )
            return {
                "content": "Tamam, aktif entegrasyon kurulumunu iptal ettim.",
                "status": "cancelled",
                "connector": None,
                "connection": None,
                "generated_request": None,
                "assistant_setup": self._serialize_assistant_setup(finished),
                "authorization_url": None,
                "deep_link_path": None,
                "suggested_replies": [],
                "generated_from": "assistant_integration_orchestration",
            }

        metadata = dict(setup.get("metadata") or {})
        if str(metadata.get("setup_mode") or "") == "legacy_desktop":
            spec = self._require_connector(str(setup.get("connector_id") or ""))
            recipe = self._assistant_legacy_recipe(str(spec.id or ""))
            pending_field = dict(metadata.get("pending_field") or {})
            hinted_field_key = self._assistant_legacy_field_key_from_query(
                spec,
                query=query,
                metadata=metadata,
                planner_hint=planner_hint,
            )
            hinted_field = (
                self._assistant_legacy_field_definition(spec, field_key=hinted_field_key, query=str(setup.get("request_text") or query), metadata=metadata)
                if hinted_field_key
                else None
            )
            help_intent = self._assistant_setup_help_intent(normalized)
            if followup_intent == "explain_current" and not help_intent:
                help_intent = "clarify"
            if followup_intent == "status_check":
                return self._resume_assistant_legacy_setup(setup, actor=actor)
            if pending_field:
                if help_intent:
                    return {
                        "content": self._assistant_legacy_setup_help_text(spec, setup, query=query),
                        "status": "collecting_input",
                        "connector": spec.model_dump(mode="json"),
                        "connection": None,
                        "generated_request": None,
                        "assistant_setup": self._serialize_assistant_setup(setup),
                        "authorization_url": None,
                        "deep_link_path": metadata.get("deep_link_path"),
                        "suggested_replies": [],
                        "generated_from": "assistant_integration_orchestration",
                    }
                if self._assistant_query_requests_field_retry(normalized):
                    return self._assistant_legacy_reopen_field(
                        setup,
                        spec=spec,
                        actor=actor,
                        field=hinted_field or pending_field,
                    )
                try:
                    return self._assistant_legacy_apply_field_value(
                        setup,
                        spec=spec,
                        actor=actor,
                        field=hinted_field or pending_field,
                        query=query,
                    )
                except ValueError:
                    return {
                        "content": self._assistant_prompt_for_field(spec, pending_field),
                        "status": "collecting_input",
                        "connector": spec.model_dump(mode="json"),
                        "connection": None,
                        "generated_request": None,
                        "assistant_setup": self._serialize_assistant_setup(setup),
                        "authorization_url": None,
                        "deep_link_path": metadata.get("deep_link_path"),
                        "suggested_replies": [],
                        "generated_from": "assistant_integration_orchestration",
                    }
            if help_intent:
                return {
                    "content": self._assistant_legacy_setup_help_text(spec, setup, query=query),
                    "status": str(setup.get("status") or "ready_for_desktop_action"),
                    "connector": spec.model_dump(mode="json"),
                    "connection": None,
                    "generated_request": None,
                    "assistant_setup": self._serialize_assistant_setup(setup),
                    "authorization_url": None,
                    "deep_link_path": metadata.get("deep_link_path"),
                    "suggested_replies": list(metadata.get("suggested_replies") or recipe.get("suggested_replies") or ["Durumu kontrol et", "Vazgeç"]),
                    "generated_from": "assistant_integration_orchestration",
                }
            if hinted_field:
                try:
                    return self._assistant_legacy_apply_field_value(
                        setup,
                        spec=spec,
                        actor=actor,
                        field=hinted_field,
                        query=query,
                    )
                except ValueError:
                    pass
            if self._assistant_query_requests_field_retry(normalized):
                retry_field = hinted_field or self._assistant_legacy_field_definition(
                    spec,
                    field_key="client_id",
                    query=str(setup.get("request_text") or query),
                    metadata=metadata,
                )
                if retry_field:
                    return self._assistant_legacy_reopen_field(setup, spec=spec, actor=actor, field=retry_field)
            return self._resume_assistant_legacy_setup(
                setup,
                actor=actor,
                auto_run_desktop_action=self._assistant_query_requests_legacy_proceed(normalized, planner_hint=planner_hint),
            )
        if bool(metadata.get("awaiting_provider_choice")):
            connector_id = self._assistant_provider_choice(normalized)
            if not connector_id:
                return {
                    "content": "Devam etmek icin veri kaynagini sec: PostgreSQL, Elastic veya Generic REST API.",
                    "status": "awaiting_provider_choice",
                    "connector": None,
                    "connection": None,
                    "generated_request": None,
                    "assistant_setup": self._serialize_assistant_setup(setup),
                    "authorization_url": None,
                    "deep_link_path": metadata.get("deep_link_path"),
                    "suggested_replies": ["PostgreSQL", "Elastic", "Generic REST API"],
                    "generated_from": "assistant_integration_orchestration",
                }
            spec = self._require_connector(connector_id)
            next_setup = self.repo.upsert_assistant_setup(
                self.settings.office_id,
                thread_id=int(setup["thread_id"]),
                setup_id=int(setup["id"]),
                connector_id=spec.id,
                service_name=spec.name,
                request_text=str(setup.get("request_text") or query),
                status="collecting_input",
                missing_fields=self._assistant_missing_required_fields(spec, config={}, secrets_payload={}),
                collected_config={},
                secret_blob=self.secret_box.seal_json({}),
                metadata={
                    "access_level": spec.default_access_level,
                    "requested_scopes": self._assistant_scopes_for_access(spec, spec.default_access_level),
                    "live_mode_requested": not bool(self.settings.connector_dry_run),
                    "pending_field": self._assistant_missing_required_fields(spec, config={}, secrets_payload={})[0],
                    "next_step": "Kurulumu tamamlamak için sıradaki bilgiyi paylaş.",
                    "skill": self._connector_skill_summary(spec),
                },
                created_by=actor,
            )
            next_setup = self.repo.upsert_assistant_setup(
                self.settings.office_id,
                thread_id=int(setup["thread_id"]),
                setup_id=int(next_setup["id"]),
                connector_id=spec.id,
                service_name=spec.name,
                request_text=str(setup.get("request_text") or query),
                status="collecting_input",
                missing_fields=list(next_setup.get("missing_fields") or []),
                collected_config=dict(next_setup.get("collected_config") or {}),
                secret_blob=str(next_setup.get("secret_blob") or ""),
                metadata={
                    **dict(next_setup.get("metadata") or {}),
                    "deep_link_path": self._assistant_deep_link(connector_id=spec.id, setup_id=int(next_setup["id"])),
                },
                created_by=actor,
            )
            pending_field = dict((next_setup.get("metadata") or {}).get("pending_field") or {})
            return {
                "content": f"{spec.name} bağlantısına geçiyorum. {self._assistant_prompt_for_field(spec, pending_field)}",
                "status": "collecting_input",
                "connector": spec.model_dump(mode="json"),
                "connection": None,
                "generated_request": None,
                "assistant_setup": self._serialize_assistant_setup(next_setup),
                "authorization_url": None,
                "deep_link_path": dict(next_setup.get("metadata") or {}).get("deep_link_path"),
                "suggested_replies": [],
                "generated_from": "assistant_integration_orchestration",
            }

        if str(setup.get("status") or "") == "oauth_pending":
            return self._resume_assistant_oauth_setup(setup, actor=actor)

        if bool(metadata.get("waiting_for_review_confirmation")):
            if self._is_affirmative(normalized):
                generated_connector_id = str(metadata.get("generated_connector_id") or setup.get("connector_id") or "")
                if generated_connector_id:
                    self.review_generated_connector(
                        generated_connector_id,
                        IntegrationGeneratedConnectorReviewRequest(
                            decision="approve",
                            notes="Sohbet içinden canlı kullanım onayı verildi.",
                            live_use_enabled=True,
                        ),
                        actor=actor,
                    )
                reviewed = self.repo.upsert_assistant_setup(
                    self.settings.office_id,
                    thread_id=int(setup["thread_id"]),
                    setup_id=int(setup["id"]),
                    connector_id=str(setup.get("connector_id") or "") or None,
                    connection_id=int(setup.get("connection_id") or 0) or None,
                    service_name=str(setup.get("service_name") or "") or None,
                    request_text=str(setup.get("request_text") or ""),
                    status="ready_to_save",
                    missing_fields=list(setup.get("missing_fields") or []),
                    collected_config=dict(setup.get("collected_config") or {}),
                    secret_blob=str(setup.get("secret_blob") or ""),
                    metadata={
                        **metadata,
                        "waiting_for_review_confirmation": False,
                        "review_confirmed_by": actor,
                        "next_step": "Bağlantıyı kaydedip izin ekranını açacağım.",
                    },
                    created_by=actor,
                )
                return self._finalize_assistant_setup(reviewed, actor=actor)
            if self._is_negative(normalized):
                return {
                    "content": "Tamam. Bu bağlantıyı canlı moda almıyorum. Hazır olduğunda 'Onaylıyorum' yazman yeterli.",
                    "status": "review_pending",
                    "connector": self._require_connector(str(setup.get("connector_id") or "")).model_dump(mode="json"),
                    "connection": None,
                    "generated_request": self._serialize_generated_connector(
                        self.repo.get_generated_connector(self.settings.office_id, str(setup.get("connector_id") or ""))
                    ),
                    "assistant_setup": self._serialize_assistant_setup(setup),
                    "authorization_url": None,
                    "deep_link_path": metadata.get("deep_link_path"),
                    "suggested_replies": ["Onaylıyorum", "Vazgeç"],
                    "generated_from": "assistant_integration_orchestration",
                }

        spec = self._require_connector(str(setup.get("connector_id") or ""))
        pending_field = dict(metadata.get("pending_field") or {})
        if not pending_field:
            return self._finalize_assistant_setup(setup, actor=actor)

        collected_config = dict(setup.get("collected_config") or {})
        try:
            collected_secrets = self.secret_box.open_json(str(setup.get("secret_blob") or ""))
        except ValueError:
            reset_setup = self.repo.complete_assistant_setup(
                self.settings.office_id,
                int(setup["id"]),
                status="abandoned",
                metadata={
                    **metadata,
                    "abandoned_reason": "secret_material_rotated",
                    "abandoned_by": actor,
                    "next_step": "Guvenlik anahtari degistigi icin kurulum yeniden baslatilmali.",
                },
            ) or setup
            self._log_event(
                connector_id=str(setup.get("connector_id") or "") or None,
                connection_id=int(setup.get("connection_id") or 0) or None,
                event_type="assistant_setup_secret_reset",
                message="Yarım kalan entegrasyon kurulumu secret rotasyonu nedeniyle sıfırlandı.",
                actor=actor,
                severity="warning",
                data={
                    "setup_id": int(setup["id"]),
                    "thread_id": int(setup["thread_id"]),
                    "reason": "secret_material_rotated",
                },
            )
            if self._is_assistant_integration_intent(normalized):
                restarted = self._start_assistant_setup(thread_id=int(setup["thread_id"]), query=query, actor=actor)
                restarted["content"] = (
                    "Güvenlik anahtarı yenilendiği için önceki yarım kurulum sıfırlandı. "
                    + str(restarted.get("content") or "")
                ).strip()
                return restarted
            connector_name = str(setup.get("service_name") or spec.name or "entegrasyon")
            return {
                "content": (
                    f"{connector_name} kurulumu güvenlik nedeniyle sıfırlandı. "
                    f"Yeniden başlatmak için '{connector_name} bağla' yazabilirsin."
                ),
                "status": "setup_reset",
                "connector": spec.model_dump(mode="json"),
                "connection": None,
                "generated_request": self._serialize_generated_connector(self.repo.get_generated_connector(self.settings.office_id, spec.id)),
                "assistant_setup": self._serialize_assistant_setup(reset_setup),
                "authorization_url": None,
                "deep_link_path": self._assistant_deep_link(connector_id=spec.id),
                "suggested_replies": [f"{connector_name} bağla", "Durumu kontrol et"],
                "generated_from": "assistant_integration_orchestration",
            }
        try:
            value = self._assistant_parse_field_value(pending_field, query)
        except ValueError:
            return {
                "content": self._assistant_prompt_for_field(spec, pending_field),
                "status": "collecting_input",
                "connector": spec.model_dump(mode="json"),
                "connection": self._serialize_connection(self._optional_connection(int(setup.get("connection_id") or 0))) if setup.get("connection_id") else None,
                "generated_request": self._serialize_generated_connector(self.repo.get_generated_connector(self.settings.office_id, spec.id)),
                "assistant_setup": self._serialize_assistant_setup(setup),
                "authorization_url": None,
                "deep_link_path": metadata.get("deep_link_path"),
                "suggested_replies": [],
                "generated_from": "assistant_integration_orchestration",
            }
        if str(pending_field.get("target") or "config") == "secret":
            collected_secrets[str(pending_field.get("key") or "")] = value
        else:
            collected_config[str(pending_field.get("key") or "")] = value

        missing_fields = self._assistant_missing_required_fields(spec, config=collected_config, secrets_payload=collected_secrets)
        next_pending = missing_fields[0] if missing_fields else None
        updated = self.repo.upsert_assistant_setup(
            self.settings.office_id,
            thread_id=int(setup["thread_id"]),
            setup_id=int(setup["id"]),
            connector_id=spec.id,
            connection_id=int(setup.get("connection_id") or 0) or None,
            service_name=spec.name,
            request_text=str(setup.get("request_text") or ""),
            status="collecting_input" if next_pending else "ready_to_save",
            missing_fields=missing_fields,
            collected_config=collected_config,
            secret_blob=self.secret_box.seal_json(collected_secrets),
            metadata={
                **metadata,
                "pending_field": next_pending,
                "next_step": "Kurulumu tamamlamak için sıradaki bilgiyi paylaş." if next_pending else "Bağlantıyı kaydetmeye hazırım.",
            },
            created_by=actor,
        )
        if next_pending:
            return {
                "content": self._assistant_prompt_for_field(spec, next_pending),
                "status": "collecting_input",
                "connector": spec.model_dump(mode="json"),
                "connection": None,
                "generated_request": self._serialize_generated_connector(self.repo.get_generated_connector(self.settings.office_id, spec.id)),
                "assistant_setup": self._serialize_assistant_setup(updated),
                "authorization_url": None,
                "deep_link_path": dict(updated.get("metadata") or {}).get("deep_link_path"),
                "suggested_replies": [],
                "generated_from": "assistant_integration_orchestration",
            }
        return self._finalize_assistant_setup(updated, actor=actor)

    def _finalize_assistant_setup(self, setup: dict[str, Any], *, actor: str) -> dict[str, Any]:
        spec = self._require_connector(str(setup.get("connector_id") or ""))
        metadata = dict(setup.get("metadata") or {})
        generated_row = self.repo.get_generated_connector(self.settings.office_id, spec.id)
        if generated_row and bool(metadata.get("live_mode_requested")) and not self._generated_live_use_allowed(generated_row):
            review_scopes = list(metadata.get("requested_scopes") or [])
            review_summary = [
                f"İstenecek izinler: {self._assistant_requested_scope_summary(review_scopes)}",
                "Bu bağlantı yeni üretildiği için canlı kullanıma geçmeden önce onayını almam gerekiyor.",
            ]
            gated = self.repo.upsert_assistant_setup(
                self.settings.office_id,
                thread_id=int(setup["thread_id"]),
                setup_id=int(setup["id"]),
                connector_id=spec.id,
                connection_id=int(setup.get("connection_id") or 0) or None,
                service_name=spec.name,
                request_text=str(setup.get("request_text") or ""),
                status="review_pending",
                missing_fields=list(setup.get("missing_fields") or []),
                collected_config=dict(setup.get("collected_config") or {}),
                secret_blob=str(setup.get("secret_blob") or ""),
                metadata={
                    **metadata,
                    "waiting_for_review_confirmation": True,
                    "review_summary": review_summary,
                    "next_step": "Canlı kullanıma geçmek için onay ver.",
                },
                created_by=actor,
            )
            return {
                "content": (
                    f"{spec.name} bağlantısını hazırladım. Bu bağlayıcı yeni oluşturulduğu için canlı kullanıma geçmeden önce onayını almam gerekiyor. "
                    f"{' '.join(review_summary)} Devam etmek istiyorsan 'Onaylıyorum' yaz."
                ),
                "status": "review_pending",
                "connector": spec.model_dump(mode="json"),
                "connection": None,
                "generated_request": self._serialize_generated_connector(generated_row),
                "assistant_setup": self._serialize_assistant_setup(gated),
                "authorization_url": None,
                "deep_link_path": dict(gated.get("metadata") or {}).get("deep_link_path"),
                "suggested_replies": ["Onaylıyorum", "Vazgeç"],
                "generated_from": "assistant_integration_orchestration",
            }

        connection_payload = IntegrationConnectionPayload(
            connector_id=spec.id,
            connection_id=int(setup.get("connection_id") or 0) or None,
            display_name=(
                str((setup.get("collected_config") or {}).get("watch_label") or "").strip()
                if spec.id == "web-watch"
                else str(spec.name)
            )
            or str(spec.name),
            access_level=str(metadata.get("access_level") or spec.default_access_level),
            enabled=True,
            mock_mode=bool(self.settings.connector_dry_run) or not bool(metadata.get("live_mode_requested")),
            scopes=list(metadata.get("requested_scopes") or []),
            config=dict(setup.get("collected_config") or {}),
            secrets=self.secret_box.open_json(str(setup.get("secret_blob") or "")),
        )
        saved = self.save_connection(connection_payload, actor=actor)
        connection = dict(saved.get("connection") or {})
        refreshed_setup = self.repo.upsert_assistant_setup(
            self.settings.office_id,
            thread_id=int(setup["thread_id"]),
            setup_id=int(setup["id"]),
            connector_id=spec.id,
            connection_id=int(connection.get("id") or 0) or None,
            service_name=spec.name,
            request_text=str(setup.get("request_text") or ""),
            status="oauth_pending" if spec.auth_type == "oauth2" else "connected",
            missing_fields=[],
            collected_config=dict(setup.get("collected_config") or {}),
            secret_blob=str(setup.get("secret_blob") or ""),
            metadata={
                **metadata,
                "pending_field": None,
                "deep_link_path": self._assistant_deep_link(
                    connector_id=spec.id,
                    connection_id=int(connection.get("id") or 0) or None,
                    setup_id=int(setup.get("id") or 0),
                ),
            },
            created_by=actor,
        )
        if spec.auth_type == "oauth2":
            started = self.start_oauth_authorization(
                int(connection["id"]),
                IntegrationOAuthStartRequest(
                    redirect_uri=str(connection.get("config", {}).get("redirect_uri") or ""),
                    requested_scopes=list(connection.get("scopes") or []),
                ),
                actor=actor,
            )
            oauth_setup = self.repo.upsert_assistant_setup(
                self.settings.office_id,
                thread_id=int(setup["thread_id"]),
                setup_id=int(refreshed_setup["id"]),
                connector_id=spec.id,
                connection_id=int(connection["id"]),
                service_name=spec.name,
                request_text=str(setup.get("request_text") or ""),
                status="oauth_pending",
                missing_fields=[],
                collected_config=dict(setup.get("collected_config") or {}),
                secret_blob=str(setup.get("secret_blob") or ""),
                metadata={
                    **dict(refreshed_setup.get("metadata") or {}),
                    "authorization_url": started.get("authorization_url"),
                    "oauth_session_state": dict(started.get("oauth_session") or {}).get("state"),
                    "next_step": "Son adım: izin ekranını açıp bağlantıyı onayla.",
                },
                created_by=actor,
            )
            return {
                "content": (
                    f"{spec.name} bağlantısını kaydettim. Şimdi {spec.name} izin ekranını açıp erişim onayını vermen gerekiyor. "
                    "Onayı tamamladığında bu sohbete dönüp 'Bağlandım' veya 'Durumu kontrol et' yazman yeterli."
                ),
                "status": "oauth_pending",
                "connector": spec.model_dump(mode="json"),
                "connection": started.get("connection"),
                "generated_request": self._serialize_generated_connector(generated_row),
                "assistant_setup": self._serialize_assistant_setup(oauth_setup),
                "authorization_url": started.get("authorization_url"),
                "deep_link_path": dict(oauth_setup.get("metadata") or {}).get("deep_link_path"),
                "suggested_replies": ["Bağlandım", "Durumu kontrol et"],
                "generated_from": "assistant_integration_orchestration",
            }

        checked = self.health_check_connection(int(connection["id"]), actor=actor)
        synced = None
        if spec.resources:
            try:
                synced = self.sync_connection(int(connection["id"]), actor=actor)
            except ValueError:
                synced = None
        completed = self.repo.complete_assistant_setup(
            self.settings.office_id,
            int(refreshed_setup["id"]),
            status="completed",
            metadata={
                **dict(refreshed_setup.get("metadata") or {}),
                "capabilities": [item.get("title") for item in discover_capabilities(self._require_connection(int(connection["id"])), spec).get("allowed_actions") or []][:6],
            },
        )
        return {
            "content": self._assistant_connected_message(
                spec=spec,
                connection=self._require_connection(int(connection["id"])),
                capabilities=discover_capabilities(self._require_connection(int(connection["id"])), spec),
            ),
            "status": "connected",
            "connector": spec.model_dump(mode="json"),
            "connection": checked.get("connection") or connection,
            "generated_request": self._serialize_generated_connector(generated_row),
            "assistant_setup": self._serialize_assistant_setup(completed),
            "authorization_url": None,
            "deep_link_path": dict(completed.get("metadata") or {}).get("deep_link_path") if completed else None,
            "suggested_replies": self._assistant_post_connect_suggestions(spec),
            "sync_result": synced,
            "generated_from": "assistant_integration_orchestration",
        }

    def _resume_assistant_oauth_setup(self, setup: dict[str, Any], *, actor: str) -> dict[str, Any]:
        connection_id = int(setup.get("connection_id") or 0)
        if connection_id <= 0:
            raise ValueError("integration_connection_not_found")
        connection = self._require_connection(connection_id)
        spec = self._require_connector(str(connection.get("connector_id") or ""))
        auth_status = str(connection.get("auth_status") or "")
        if auth_status == "authenticated":
            checked = self.health_check_connection(connection_id, actor=actor)
            synced = None
            if spec.resources:
                try:
                    synced = self.sync_connection(connection_id, actor=actor)
                except ValueError:
                    synced = None
            completed = self.repo.complete_assistant_setup(
                self.settings.office_id,
                int(setup["id"]),
                status="completed",
                metadata={
                    **dict(setup.get("metadata") or {}),
                    "capabilities": [item.get("title") for item in discover_capabilities(self._require_connection(connection_id), spec).get("allowed_actions") or []][:6],
                },
            )
            return {
                "content": self._assistant_connected_message(
                    spec=spec,
                    connection=self._require_connection(connection_id),
                    capabilities=discover_capabilities(self._require_connection(connection_id), spec),
                ),
                "status": "connected",
                "connector": spec.model_dump(mode="json"),
                "connection": checked.get("connection") or self._serialize_connection(connection),
                "generated_request": self._serialize_generated_connector(self.repo.get_generated_connector(self.settings.office_id, spec.id)),
                "assistant_setup": self._serialize_assistant_setup(completed),
                "authorization_url": None,
                "deep_link_path": dict(completed.get("metadata") or {}).get("deep_link_path") if completed else None,
                "suggested_replies": self._assistant_post_connect_suggestions(spec),
                "sync_result": synced,
                "generated_from": "assistant_integration_orchestration",
            }
        metadata = dict(setup.get("metadata") or {})
        return {
            "content": (
                f"{spec.name} için bağlantı onayı henüz tamamlanmamış görünüyor. "
                "İzin ekranını bitirdikten sonra 'Durumu kontrol et' yazabilir veya kurulum ekranını açabilirsin."
            ),
            "status": "oauth_pending",
            "connector": spec.model_dump(mode="json"),
            "connection": self._serialize_connection(connection),
            "generated_request": self._serialize_generated_connector(self.repo.get_generated_connector(self.settings.office_id, spec.id)),
            "assistant_setup": self._serialize_assistant_setup(setup),
            "authorization_url": metadata.get("authorization_url"),
            "deep_link_path": metadata.get("deep_link_path"),
            "suggested_replies": ["Durumu kontrol et", "Vazgeç"],
            "generated_from": "assistant_integration_orchestration",
        }

    def _assistant_provider_choice(self, normalized_query: str) -> str | None:
        if any(token in normalized_query for token in ("postgres", "postgresql", "psql")):
            return "postgresql"
        if any(token in normalized_query for token in ("mysql", "mariadb")):
            return "mysql"
        if any(token in normalized_query for token in ("mssql", "sql server", "sqlserver", "microsoft sql")):
            return "mssql"
        if any(token in normalized_query for token in ("elastic", "elasticsearch")):
            return "elastic"
        if any(token in normalized_query for token in ("rest", "api")):
            return "generic-rest"
        return None

    def _assistant_seed_setup_values(self, *, spec: ConnectorSpec, query: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if spec.id != "web-watch":
            return {}, {}
        normalized = _normalize_text(query)
        config: dict[str, Any] = {
            "render_mode": "auto",
            "notify_on_change": True,
            "check_interval_minutes": 1440,
        }
        url_match = re.search(r"https?://[^\s]+", str(query or "").strip())
        if url_match:
            config["url"] = url_match.group(0).strip().rstrip(").,")
            hostname = str(urlparse(config["url"]).hostname or "").strip()
            if hostname:
                config["watch_label"] = hostname.replace("www.", "")
        known_sites = {
            "resmi gazete": {
                "url": "https://www.resmigazete.gov.tr/",
                "watch_label": "Resmî Gazete",
                "summary_focus": "Yeni yayımlanan kararları, duyuruları ve dikkat edilmesi gereken değişiklikleri öne çıkar.",
            },
        }
        for key, preset in known_sites.items():
            if key in normalized:
                config = {**preset, **config}
                break
        if any(token in normalized for token in ("saatte bir", "her saat", "hourly")):
            config["check_interval_minutes"] = 60
        elif any(token in normalized for token in ("gunde iki", "günde iki", "12 saatte", "twice a day")):
            config["check_interval_minutes"] = 720
        elif any(token in normalized for token in ("haftalik", "haftalık", "haftada", "weekly")):
            config["check_interval_minutes"] = 10080
        elif any(token in normalized for token in ("her gun", "her gün", "gunluk", "günlük", "daily")):
            config["check_interval_minutes"] = 1440
        if "summary_focus" not in config and any(token in normalized for token in ("karar", "duyuru", "ilan", "özet", "ozet")):
            config["summary_focus"] = "Yeni kararları, duyuruları ve başlık değişimlerini özetle."
        return config, {}

    def _scheduled_sync_interval_minutes(self, spec: ConnectorSpec, connection: dict[str, Any]) -> int:
        config = dict(connection.get("config") or {})
        if spec.id == "web-watch":
            try:
                return max(5, int(config.get("check_interval_minutes") or 1440))
            except (TypeError, ValueError):
                return 1440
        policy = next((item for item in spec.sync_policies if item.mode == "incremental" and item.schedule_hint_minutes), None)
        if policy and policy.schedule_hint_minutes:
            return int(policy.schedule_hint_minutes)
        return 0

    def ensure_scheduled_sync_runs(self, *, actor: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        created: list[dict[str, Any]] = []
        for connection in self.repo.list_connections(self.settings.office_id):
            if not bool(connection.get("enabled")):
                continue
            connector_id = str(connection.get("connector_id") or "").strip()
            spec = self._effective_catalog().get(connector_id)
            if not spec or spec.management_mode != "platform":
                continue
            if self.repo.get_active_sync_run(self.settings.office_id, int(connection["id"])):
                continue
            auth_status = str(connection.get("auth_status") or auth_status_from_summary(connection.get("auth_summary") or {}))
            if spec.auth_type not in {"none", "noauth"} and auth_status != "authenticated":
                continue
            interval_minutes = self._scheduled_sync_interval_minutes(spec, connection)
            if interval_minutes <= 0:
                continue
            last_sync_at = str(connection.get("last_sync_at") or connection.get("updated_at") or "").strip()
            try:
                last_sync_dt = datetime.fromisoformat(last_sync_at) if last_sync_at else None
            except ValueError:
                last_sync_dt = None
            if last_sync_dt and last_sync_dt.tzinfo is None:
                last_sync_dt = last_sync_dt.replace(tzinfo=timezone.utc)
            if last_sync_dt and last_sync_dt + timedelta(minutes=interval_minutes) > now:
                continue
            sync_run = self.repo.create_sync_run(
                self.settings.office_id,
                connection_id=int(connection["id"]),
                mode="incremental",
                status="queued",
                trigger_type="scheduled",
                requested_by=actor,
                run_key=f"scheduled:{int(connection['id'])}:incremental",
                scheduled_for=now.isoformat(),
                metadata={"connector_id": spec.id, "scheduled": True},
            )
            self.repo.update_connection_runtime(
                self.settings.office_id,
                int(connection["id"]),
                sync_status="queued",
                sync_status_message="Planlı senkron kuyruğa alındı.",
                last_error=None,
            )
            created.append(sync_run)
        return {
            "items": created,
            "count": len(created),
            "generated_from": "integration_scheduled_sync_planner",
        }

    def _assistant_connected_message(self, *, spec: ConnectorSpec, connection: dict[str, Any], capabilities: dict[str, Any]) -> str:
        if spec.id == "web-watch":
            config = dict(connection.get("config") or {})
            watch_label = str(config.get("watch_label") or connection.get("display_name") or spec.name).strip() or spec.name
            url = str(config.get("url") or "").strip()
            interval = self._scheduled_sync_interval_minutes(spec, connection)
            if interval % 1440 == 0:
                cadence = f"{max(1, interval // 1440)} günde bir"
            elif interval % 60 == 0:
                cadence = f"{max(1, interval // 60)} saatte bir"
            else:
                cadence = f"{interval} dakikada bir"
            lines = [f"{watch_label} takibi bağlandı."]
            lines.append(f"{url or 'Bu sayfa'} adresini {cadence} kontrol edeceğim.")
            lines.append("Değişiklik olduğunda ana sayfada uyarı kartı ve özet gösterebilirim.")
            suggestions = self._assistant_post_connect_suggestions(spec)
            if suggestions:
                lines.append(f"İstersen şimdi '{suggestions[0]}' diyebilirsin.")
            return " ".join(lines)
        allowed = list(capabilities.get("allowed_actions") or [])
        capability_titles = [str(item.get("title") or item.get("operation") or "") for item in allowed[:4] if str(item.get("title") or item.get("operation") or "").strip()]
        lines = [f"{spec.name} bağlandı."]
        if capability_titles:
            lines.append(f"Artık şunları yapabilirim: {', '.join(capability_titles)}.")
        auth_summary = dict(connection.get("auth_summary") or {})
        permission_summary = [str(item).strip() for item in list(auth_summary.get("permission_summary") or []) if str(item).strip()]
        if permission_summary:
            lines.append(f"Erişim özeti: {permission_summary[0]}.")
        suggestions = self._assistant_post_connect_suggestions(spec)
        if suggestions:
            lines.append(f"İstersen sıradaki adım olarak '{suggestions[0]}' diyebilirsin.")
        return " ".join(lines)

    def _find_matching_patterns(
        self,
        *,
        service_name: str,
        category: str,
        docs_url: str | None,
    ) -> list[dict[str, Any]]:
        docs_host = ""
        if docs_url:
            docs_host = str(urlparse(docs_url).hostname or "").strip().lower()
        normalized_service = _normalize_text(service_name)
        normalized_category = _normalize_text(category)
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in self.repo.list_connector_patterns(self.settings.office_id, limit=50):
            score = 0
            row_service = _normalize_text(str(row.get("service_name") or ""))
            row_category = _normalize_text(str(row.get("category") or ""))
            row_host = _normalize_text(str(row.get("docs_host") or ""))
            if normalized_service and row_service == normalized_service:
                score += 5
            elif normalized_service and normalized_service in row_service:
                score += 3
            if normalized_category and row_category == normalized_category:
                score += 2
            if docs_host and row_host == _normalize_text(docs_host):
                score += 4
            if score <= 0:
                continue
            scored.append((score + int(row.get("success_count") or 0), row))
        scored.sort(
            key=lambda item: (
                item[0],
                int(item[1].get("success_count") or 0),
                str(item[1].get("updated_at") or ""),
            ),
            reverse=True,
        )
        return [row for _, row in scored[:5]]

    def _remember_connector_pattern(self, spec: ConnectorSpec, *, source_kind: str, success_increment: int) -> None:
        docs_host = str(urlparse(str(spec.docs_url or spec.base_url or "")).hostname or "").strip().lower() or None
        pattern_key = _slugify(f"{spec.name}-{docs_host or spec.category or spec.auth_type}")
        self.repo.upsert_connector_pattern(
            self.settings.office_id,
            pattern_key=pattern_key,
            connector_id=spec.id,
            service_name=spec.name,
            category=spec.category,
            auth_type=spec.auth_type,
            docs_host=docs_host,
            base_url=spec.base_url,
            source_kind=source_kind,
            success_increment=success_increment,
            pattern={
                "category": spec.category,
                "auth_type": spec.auth_type,
                "base_url": spec.base_url,
                "docs_url": spec.docs_url,
                "scopes": list(spec.scopes),
                "auth_config": spec.auth_config.model_dump(mode="json"),
                "resources": [resource.model_dump(mode="json") for resource in spec.resources],
                "actions": [action.model_dump(mode="json") for action in spec.actions],
                "webhook_support": spec.webhook_support.model_dump(mode="json"),
                "ui_schema": [field.model_dump(mode="json") for field in spec.ui_schema],
            },
        )

    def _infer_request_seed(self, payload: IntegrationAutomationRequest) -> dict[str, Any]:
        prompt = str(payload.prompt or "").strip()
        normalized_prompt = _normalize_text(prompt)
        seed: dict[str, Any] = {
            "service_name": "",
            "docs_url": payload.docs_url,
            "openapi_url": payload.openapi_url,
            "openapi_spec": payload.openapi_spec,
            "documentation_excerpt": payload.documentation_excerpt,
            "category": payload.category,
            "preferred_auth_type": payload.preferred_auth_type,
            "base_url": None,
            "scopes": [],
            "auth_config": {},
            "resources": [],
            "actions": [],
            "webhook_support": {},
            "extra_ui_fields": [],
            "pattern_matches": [],
        }
        for alias, target in KNOWN_AUTOMATION_TARGETS.items():
            if alias in normalized_prompt:
                seed["service_name"] = target["service_name"]
                seed["docs_url"] = seed["docs_url"] or target.get("docs_url")
                seed["category"] = seed["category"] or target.get("category")
                seed["preferred_auth_type"] = seed["preferred_auth_type"] or target.get("preferred_auth_type")
                seed["base_url"] = seed["base_url"] or target.get("base_url")
                seed["scopes"] = list(seed.get("scopes") or target.get("scopes") or [])
                seed["auth_config"] = dict(seed.get("auth_config") or target.get("auth_config") or {})
                seed["resources"] = list(target.get("resources") or [])
                seed["actions"] = list(target.get("actions") or [])
                seed["webhook_support"] = dict(target.get("webhook_support") or {})
                seed["extra_ui_fields"] = list(target.get("extra_ui_fields") or [])
                break
        if not seed["service_name"]:
            seed["service_name"] = self._extract_service_name_from_prompt(prompt, normalized_prompt=normalized_prompt)
        if not seed["service_name"] and seed["docs_url"]:
            parsed = urlparse(str(seed["docs_url"]))
            hostname = str(parsed.hostname or "").strip().lower()
            hostname = re.sub(r"^(api|developers|developer|docs)\.", "", hostname)
            base_name = hostname.split(".")[0] if hostname else ""
            if base_name:
                seed["service_name"] = " ".join(part.capitalize() for part in re.split(r"[-_]+", base_name) if part)
        if not seed["service_name"]:
            seed["service_name"] = "Custom Service"
        if not seed["category"]:
            lowered = normalized_prompt
            if any(token in lowered for token in ("message", "mail", "chat", "slack", "discord")):
                seed["category"] = "communication"
            elif any(token in lowered for token in ("calendar", "event", "meeting")):
                seed["category"] = "calendar"
            elif any(token in lowered for token in ("database", "sql", "postgres", "mysql", "mssql", "sql server", "sqlserver", "elastic")):
                seed["category"] = "database"
            else:
                seed["category"] = "custom-api"
        pattern_matches = self._find_matching_patterns(
            service_name=str(seed.get("service_name") or ""),
            category=str(seed.get("category") or ""),
            docs_url=str(seed.get("docs_url") or "") or None,
        )
        if pattern_matches:
            seed["pattern_matches"] = [
                {
                    "pattern_key": item.get("pattern_key"),
                    "service_name": item.get("service_name"),
                    "category": item.get("category"),
                    "auth_type": item.get("auth_type"),
                    "success_count": item.get("success_count"),
                }
                for item in pattern_matches
            ]
            pattern = dict(pattern_matches[0].get("pattern") or {})
            seed["category"] = seed.get("category") or pattern.get("category")
            seed["preferred_auth_type"] = seed.get("preferred_auth_type") or pattern.get("auth_type")
            seed["base_url"] = seed.get("base_url") or pattern.get("base_url")
            seed["scopes"] = list(seed.get("scopes") or pattern.get("scopes") or [])
            seed["auth_config"] = {**dict(pattern.get("auth_config") or {}), **dict(seed.get("auth_config") or {})}
            seed["resources"] = list(seed.get("resources") or pattern.get("resources") or [])
            seed["actions"] = list(seed.get("actions") or pattern.get("actions") or [])
            seed["webhook_support"] = dict(seed.get("webhook_support") or pattern.get("webhook_support") or {})
            seed["extra_ui_fields"] = list(seed.get("extra_ui_fields") or pattern.get("ui_schema") or [])
        return seed

    def _default_generated_resource_path(self, spec: ConnectorSpec) -> str | None:
        probe = self._generic_probe_action_for_spec(spec)
        if probe and str(probe.path or "").strip():
            return str(probe.path).strip()
        return None

    def _generated_connector_readiness(self, *, seed: dict[str, Any], scaffold: dict[str, Any], spec: ConnectorSpec) -> dict[str, Any]:
        pattern_matches = list(seed.get("pattern_matches") or [])
        auth_config = dict(spec.auth_config.model_dump(mode="json"))
        classification = "prompt_only_draft"
        confidence = "low"
        notes: list[str] = [
            "Canli kullanim her durumda review ve scope kontrolunden gecmelidir.",
        ]
        if any(_normalize_text(alias) == _normalize_text(str(seed.get("service_name") or "")) for alias in KNOWN_AUTOMATION_TARGETS):
            classification = "seeded_template"
            confidence = "high"
            notes.append("Saglayici icin onceden tanimli auth ve action sablonu kullanildi.")
        elif str(seed.get("openapi_spec") or "").strip() or bool((scaffold.get("fetch_summary") or {}).get("openapi_fetched")):
            classification = "openapi_inferred"
            confidence = "medium"
            notes.append("OpenAPI path ve security tanimlarindan endpoint inference yapildi.")
        elif str(seed.get("docs_url") or "").strip() or str(seed.get("documentation_excerpt") or "").strip():
            classification = "docs_inferred"
            confidence = "medium"
            notes.append("Dokuman metni uzerinden auth ve endpoint tahmini yapildi.")
        elif pattern_matches:
            classification = "pattern_reused"
            confidence = "medium"
            notes.append("Benzer basarili connector kalibindan reuse yapildi.")
        else:
            notes.append("Bu servis yalnizca prompt tabanli taslakla olusturuldu; canli oncesi dokuman/OpenAPI eklemek onerilir.")
        return {
            "classification": classification,
            "execution_confidence": confidence,
            "needs_docs_or_openapi": confidence == "low",
            "notes": notes[:4],
        }

    def _generated_connector_created_message(self, *, spec: ConnectorSpec, readiness: dict[str, Any]) -> str:
        confidence = str(readiness.get("execution_confidence") or "low")
        if confidence == "high":
            return f"{spec.name} entegrasyonu güçlü bir sağlayıcı şablonuyla kataloğa eklendi. Bağlantıyı kurup canlı kullanıma geçmeden önce yine onay alınacak."
        if confidence == "medium":
            return f"{spec.name} entegrasyonu kataloğa eklendi. Auth ve temel action yapısı hazır; canlı kullanımdan önce doğrulama ve onay gerekir."
        return f"{spec.name} entegrasyonu taslak olarak kataloğa eklendi. Bağlanabilir, ancak canlı kullanımdan önce docs/OpenAPI ile güçlendirilmesi önerilir."

    def _generic_probe_action_for_spec(self, spec: ConnectorSpec) -> Any | None:
        readable_ops = ("get_item", "list_items", "search", "fetch_documents", "read_messages")
        for operation in readable_ops:
            action = next((item for item in spec.actions if item.operation == operation and str(item.path or "").strip()), None)
            if action is not None:
                return action
        return next((item for item in spec.actions if str(item.path or "").strip()), None)

    def _extract_service_name_from_prompt(self, prompt: str, *, normalized_prompt: str | None = None) -> str:
        normalized = normalized_prompt or _normalize_text(prompt)
        tokens = re.findall(r"[a-z0-9][a-z0-9+_.-]{1,30}", normalized.replace("'", " "))
        stop_words = {
            "connect",
            "bagla",
            "bağla",
            "baglamak",
            "bağlamak",
            "entegre",
            "integrate",
            "link",
            "add",
            "ekle",
            "kur",
            "istiyorum",
            "isterim",
            "bana",
            "benim",
            "my",
            "new",
            "yeni",
            "bir",
            "the",
            "hesabim",
            "hesabım",
            "hesabi",
            "hesabı",
            "workspace",
            "servis",
            "service",
            "entegrasyon",
            "integration",
            "otomatik",
            "olarak",
            "icin",
            "için",
            "ile",
        }
        phrase_tokens: list[str] = []
        for token in tokens:
            if token in stop_words:
                if phrase_tokens:
                    break
                continue
            phrase_tokens.append(token)
            if len(phrase_tokens) >= 3:
                break
        if not phrase_tokens:
            return ""
        return " ".join(_service_display_token(token) for token in phrase_tokens)

    def _reserve_generated_connector_id(self, service_name: str) -> str:
        base = _slugify(service_name)
        if base not in self.static_catalog:
            return base
        suffix = 2
        while f"{base}-{suffix}" in self.static_catalog:
            suffix += 1
        return f"{base}-{suffix}"

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        items: list[str] = []
        for value in values:
            cleaned = str(value or "").strip()
            if cleaned and cleaned not in items:
                items.append(cleaned)
        return items

    def _log_event(
        self,
        *,
        event_type: str,
        message: str,
        connector_id: str | None,
        connection_id: int | None,
        actor: str | None,
        severity: str = "info",
        data: dict[str, Any] | None = None,
    ) -> None:
        safe_data = _sanitize_log_data(data or {})
        self.repo.log_event(
            self.settings.office_id,
            connection_id=connection_id,
            connector_id=connector_id,
            event_type=event_type,
            severity=severity,
            message=message,
            actor=actor,
            data=safe_data,
        )
        self.audit.log(
            f"integration_{event_type}",
            connector_id=connector_id,
            connection_id=connection_id,
            actor=actor,
            severity=severity,
        )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_optional_iso(value: str) -> datetime | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _service_display_token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    overrides = {
        "tiktok": "TikTok",
        "github": "GitHub",
        "linkedin": "LinkedIn",
        "whatsapp": "WhatsApp",
        "gmail": "Gmail",
        "crm": "CRM",
        "api": "API",
        "rest": "REST",
        "sql": "SQL",
        "oauth": "OAuth",
    }
    if token in overrides:
        return overrides[token]
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", token) if part)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [_normalize_value(item) for item in value[:50]]
    if isinstance(value, dict):
        return {str(key).strip(): _normalize_value(item) for key, item in list(value.items())[:50] if str(key).strip()}
    return str(value or "").strip()[:SAFE_TEXT_CHARS]


def _sanitize_log_data(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in list(value.items())[:50]:
            normalized_key = str(key or "").strip()
            if not normalized_key:
                continue
            lowered = normalized_key.lower()
            if any(token in lowered for token in ("secret", "token", "password", "authorization", "api_key", "client_secret")):
                sanitized[normalized_key] = "[redacted]"
            else:
                sanitized[normalized_key] = _sanitize_log_data(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_log_data(item) for item in value[:50]]
    return _normalize_value(value)


def _empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _search_blob(spec: ConnectorSpec) -> str:
    parts = [spec.id, spec.name, spec.description, spec.category, *spec.tags, *(action.key for action in spec.actions)]
    return _normalize_text(" ".join(parts))


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize_text(value))
    slug = slug.strip("-")
    if not slug:
        slug = "custom-service"
    return slug[:48]
