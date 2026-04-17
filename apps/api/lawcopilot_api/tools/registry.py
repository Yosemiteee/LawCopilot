from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Callable

from ..assistant import build_assistant_calendar, build_assistant_home, build_assistant_inbox, build_social_monitoring_snapshot
from ..connectors.web_search import (
    build_places_context,
    build_travel_context,
    build_weather_context,
    build_web_search_context,
    build_youtube_search_context,
)
from ..integrations.models import (
    IntegrationAutomationRequest,
    IntegrationConnectionPayload,
    IntegrationGeneratedConnectorReviewRequest,
    IntegrationOAuthStartRequest,
)
from ..preference_rules import resolve_source_preference_context
from ..rag import score_chunk_records
from ..videointel import analyze_video_url


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    tool_class: str
    risk_level: str
    approval_policy: str
    idempotent: bool
    timeout_seconds: int
    allowed_scopes: tuple[str, ...]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["label"] = self.title
        payload["kind"] = self.tool_class
        payload["available"] = True
        return payload


@dataclass
class ToolExecutionContext:
    settings: Any
    store: Any
    events: Any
    web_intel: Any
    integration_service: Any = None


def _call_context_builder(builder: Callable[..., dict[str, Any]], /, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return builder(*args, **kwargs)
    except TypeError as exc:
        if "search_preferences" not in str(exc):
            raise
        fallback_kwargs = dict(kwargs)
        fallback_kwargs.pop("search_preferences", None)
        return builder(*args, **fallback_kwargs)


def _persist_tool_learning_signal(
    *,
    ctx: ToolExecutionContext,
    provider: str,
    event_type: str,
    query: str,
    summary: str,
    title: str | None = None,
    source_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not hasattr(ctx.store, "add_external_event"):
        return
    payload = dict(metadata or {})
    payload.setdefault("scope", "personal")
    payload.setdefault("query", query)
    payload.setdefault("captured_via", "tool_registry")
    if source_url:
        payload.setdefault("url", source_url)
        payload.setdefault("source_url", source_url)
    fingerprint_seed = json.dumps(
        {
            "provider": provider,
            "event_type": event_type,
            "query": query,
            "title": title,
            "source_url": source_url,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    external_ref = hashlib.sha256(fingerprint_seed.encode("utf-8")).hexdigest()[:20]
    try:
        ctx.store.add_external_event(
            ctx.settings.office_id,
            provider=provider,
            event_type=event_type,
            title=title,
            summary=summary,
            external_ref=external_ref,
            metadata=payload,
        )
    except Exception as exc:  # noqa: BLE001
        if getattr(ctx, "events", None) is not None:
            ctx.events.log(
                "tool_learning_signal_failed",
                level="warning",
                provider=provider,
                event_type=event_type,
                error=str(exc),
            )


def _assistant_home_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    home = build_assistant_home(ctx.store, ctx.settings.office_id, settings=ctx.settings)
    return {
        "summary": str(home.get("today_summary") or "Günlük özet hazır."),
        "home": home,
        "artifacts": [],
        "citations": [],
    }


def _assistant_inbox_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    items = build_assistant_inbox(ctx.store, ctx.settings.office_id)
    return {
        "summary": f"{len(items)} iletişim sinyali toplandı.",
        "items": items,
        "artifacts": [],
        "citations": [],
    }


def _assistant_calendar_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    window_days = int(payload.get("window_days") or 35)
    items = build_assistant_calendar(ctx.store, ctx.settings.office_id, window_days=window_days)
    return {
        "summary": f"{len(items)} takvim kaydı değerlendirildi.",
        "items": items,
        "artifacts": [],
        "citations": [],
    }


def _assistant_profile_dates_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    window_days = int(payload.get("window_days") or 30)
    limit = max(1, min(int(payload.get("limit") or 12), 24))
    calendar_items = build_assistant_calendar(ctx.store, ctx.settings.office_id, window_days=window_days)
    items = [item for item in calendar_items if str(item.get("kind") or "") == "personal_date"][:limit]
    return {
        "summary": f"{len(items)} yaklaşan kişisel tarih bulundu." if items else "Yaklaşan kişisel tarih bulunmadı.",
        "items": items,
        "artifacts": [],
        "citations": [],
    }


def _web_search_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    profile = ctx.store.get_user_profile(ctx.settings.office_id)
    context = build_web_search_context(
        query,
        limit=int(payload.get("limit") or 5),
        search_preferences=resolve_source_preference_context(query, profile=profile),
    )
    results = list(context.get("results") or [])
    first_result = results[0] if results else {}
    _persist_tool_learning_signal(
        ctx=ctx,
        provider="web",
        event_type="web_search",
        query=query,
        title=str(first_result.get("title") or "Web araması"),
        summary=str(context.get("summary") or "Web arama tamamlandı."),
        source_url=str(first_result.get("url") or "").strip() or None,
        metadata={"category": "web_research", "result_count": len(results)},
    )
    citations = [
        {
            "label": f"[{index}]",
            "document_name": item.get("title"),
            "excerpt": item.get("snippet") or item.get("url"),
            "source_type": "web_search",
            "url": item.get("url"),
        }
        for index, item in enumerate(context.get("results") or [], start=1)
    ]
    return {
        "summary": str(context.get("summary") or "Web arama tamamlandı."),
        "results": context.get("results") or [],
        "artifacts": [],
        "citations": citations,
    }


def _youtube_search_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    context = build_youtube_search_context(query, limit=int(payload.get("limit") or 5))
    results = list(context.get("results") or [])
    first_result = results[0] if results else {}
    _persist_tool_learning_signal(
        ctx=ctx,
        provider="youtube",
        event_type="youtube_search",
        query=query,
        title=str(first_result.get("title") or "YouTube araması"),
        summary=str(context.get("summary") or "YouTube arama tamamlandı."),
        source_url=str(first_result.get("url") or "").strip() or None,
        metadata={"category": "youtube", "result_count": len(results)},
    )
    citations = [
        {
            "label": f"[{index}]",
            "document_name": item.get("title"),
            "excerpt": item.get("snippet") or item.get("url"),
            "source_type": "youtube_search",
            "url": item.get("url"),
        }
        for index, item in enumerate(context.get("results") or [], start=1)
    ]
    return {
        "summary": str(context.get("summary") or "YouTube arama tamamlandı."),
        "results": context.get("results") or [],
        "artifacts": [],
        "citations": citations,
    }


def _travel_search_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    profile = ctx.store.get_user_profile(ctx.settings.office_id)
    search_preferences = resolve_source_preference_context(query, profile=profile)
    context = _call_context_builder(
        build_travel_context,
        query,
        profile_note=str(profile.get("travel_preferences") or "").strip(),
        limit=int(payload.get("limit") or 5),
        search_preferences=search_preferences,
    )
    results = list(context.get("results") or [])
    first_result = results[0] if results else {}
    _persist_tool_learning_signal(
        ctx=ctx,
        provider="travel",
        event_type="travel_search",
        query=query,
        title=str(first_result.get("title") or "Seyahat araması"),
        summary=str(context.get("summary") or "Seyahat seçenekleri derlendi."),
        source_url=str(first_result.get("url") or context.get("booking_url") or "").strip() or None,
        metadata={"category": "travel", "result_count": len(results), "booking_url": context.get("booking_url")},
    )
    citations = [
        {
            "label": f"[{index}]",
            "document_name": item.get("title"),
            "excerpt": item.get("snippet") or item.get("url"),
            "source_type": "travel_search",
            "url": item.get("url"),
        }
        for index, item in enumerate(context.get("results") or [], start=1)
    ]
    return {
        "summary": str(context.get("summary") or "Seyahat seçenekleri derlendi."),
        "results": context.get("results") or [],
        "booking_url": context.get("booking_url"),
        "artifacts": [],
        "citations": citations,
    }


def _weather_search_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    profile = ctx.store.get_user_profile(ctx.settings.office_id)
    context = build_weather_context(
        query,
        profile_note=str(profile.get("weather_preference") or "").strip(),
        limit=int(payload.get("limit") or 5),
    )
    results = list(context.get("results") or [])
    first_result = results[0] if results else {}
    _persist_tool_learning_signal(
        ctx=ctx,
        provider="weather",
        event_type="weather_search",
        query=query,
        title=str(first_result.get("title") or "Hava durumu araması"),
        summary=str(context.get("summary") or "Hava durumu araştırması tamamlandı."),
        source_url=str(first_result.get("url") or "").strip() or None,
        metadata={"category": "weather", "result_count": len(results)},
    )
    citations = [
        {
            "label": f"[{index}]",
            "document_name": item.get("title"),
            "excerpt": item.get("snippet") or item.get("url"),
            "source_type": "weather_search",
            "url": item.get("url"),
        }
        for index, item in enumerate(context.get("results") or [], start=1)
    ]
    return {
        "summary": str(context.get("summary") or "Hava durumu araştırması tamamlandı."),
        "results": context.get("results") or [],
        "artifacts": [],
        "citations": citations,
    }


def _places_search_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    profile = ctx.store.get_user_profile(ctx.settings.office_id)
    search_preferences = resolve_source_preference_context(query, profile=profile)
    context = _call_context_builder(
        build_places_context,
        query,
        profile_note=str(profile.get("food_preferences") or "").strip(),
        transport_note=str(profile.get("transport_preference") or "").strip(),
        limit=int(payload.get("limit") or 5),
        search_preferences=search_preferences,
    )
    results = list(context.get("results") or [])
    first_result = results[0] if results else {}
    _persist_tool_learning_signal(
        ctx=ctx,
        provider="places",
        event_type="places_search",
        query=query,
        title=str(first_result.get("title") or "Mekân araması"),
        summary=str(context.get("summary") or "Mekân ve rota araştırması tamamlandı."),
        source_url=str(first_result.get("url") or context.get("map_url") or "").strip() or None,
        metadata={"category": "places", "result_count": len(results), "map_url": context.get("map_url")},
    )
    citations = [
        {
            "label": f"[{index}]",
            "document_name": item.get("title"),
            "excerpt": item.get("snippet") or item.get("url"),
            "source_type": "places_search",
            "url": item.get("url"),
        }
        for index, item in enumerate(context.get("results") or [], start=1)
    ]
    return {
        "summary": str(context.get("summary") or "Mekân ve rota araştırması tamamlandı."),
        "results": context.get("results") or [],
        "map_url": context.get("map_url"),
        "artifacts": [],
        "citations": citations,
    }


def _web_inspect_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    result = ctx.web_intel.extract(
        url=str(payload.get("url") or ""),
        render_mode=str(payload.get("render_mode") or "auto"),
        include_screenshot=bool(payload.get("include_screenshot", True)),
    )
    citations = []
    if result.get("visible_text"):
        citations.append(
            {
                "label": "[1]",
                "document_name": result.get("title") or result.get("url"),
                "excerpt": str(result.get("visible_text") or "")[:360],
                "source_type": "website",
                "url": result.get("final_url") or result.get("url"),
            }
        )
    return {
        "summary": str(result.get("summary") or "Web sayfası incelendi."),
        "inspection": result,
        "artifacts": list(result.get("artifacts") or []),
        "citations": citations,
    }


def _web_crawl_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    result = ctx.web_intel.crawl(
        url=str(payload.get("url") or ""),
        query=str(payload.get("query") or ""),
        max_pages=int(payload.get("max_pages") or 4),
        render_mode=str(payload.get("render_mode") or "cheap"),
        include_screenshot=bool(payload.get("include_screenshot", False)),
    )
    citations = [
        {
            "label": f"[{index}]",
            "document_name": item.get("title") or item.get("url"),
            "excerpt": item.get("excerpt") or item.get("summary"),
            "source_type": "website_crawl",
            "url": item.get("url"),
        }
        for index, item in enumerate(result.get("pages") or [], start=1)
    ]
    return {
        "summary": str(result.get("summary") or "Site taraması tamamlandı."),
        "crawl": result,
        "artifacts": [],
        "citations": citations,
    }


def _video_analyze_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    result = analyze_video_url(
        str(payload.get("url") or ""),
        transcript_text=payload.get("transcript_text"),
        max_segments=int(payload.get("max_segments") or 24),
    )
    return {
        "summary": str(result.get("summary") or "Video çözümlemesi tamamlandı."),
        "analysis": result,
        "artifacts": [],
        "citations": list(result.get("citations") or []),
    }


def _matter_search_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    matter_id = int(payload.get("matter_id") or 0)
    query = str(payload.get("query") or "").strip()
    rows = ctx.store.search_document_chunks(
        ctx.settings.office_id,
        matter_id,
        document_ids=payload.get("document_ids"),
        source_types=payload.get("source_types"),
        filename_contains=payload.get("filename_contains"),
    ) or []
    citations = score_chunk_records(query, rows, k=min(8, max(1, int(payload.get("limit") or 5))))
    summary = "Dosya kapsamlı belge araması tamamlandı." if citations else "Bu dosyada güçlü dayanak bulunamadı."
    return {
        "summary": summary,
        "results": citations,
        "artifacts": [],
        "citations": citations,
    }


def _workspace_search_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    workspace_root = ctx.store.get_active_workspace_root(ctx.settings.office_id)
    if not workspace_root:
        return {"summary": "Aktif çalışma alanı bulunamadı.", "results": [], "artifacts": [], "citations": []}
    rows = ctx.store.search_workspace_document_chunks(
        ctx.settings.office_id,
        int(workspace_root["id"]),
        path_prefix=payload.get("path_prefix"),
        extensions=payload.get("extensions"),
        workspace_document_id=payload.get("workspace_document_id"),
    )
    query = str(payload.get("query") or "").strip()
    citations = score_chunk_records(query, rows, k=min(8, max(1, int(payload.get("limit") or 5))))
    return {
        "summary": "Çalışma alanı araması tamamlandı." if citations else "Çalışma alanında güçlü dayanak bulunamadı.",
        "results": citations,
        "artifacts": [],
        "citations": citations,
    }


def _social_monitor_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    snapshot = build_social_monitoring_snapshot(ctx.store, ctx.settings.office_id, limit=int(payload.get("limit") or 10))
    return {
        "summary": str(snapshot.get("summary") or "Sosyal sinyaller toplandı."),
        "snapshot": snapshot,
        "artifacts": [],
        "citations": [],
    }


def _integration_request_connector_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    if ctx.integration_service is None:
        return {"summary": "Integration service kullanılamıyor.", "artifacts": [], "citations": []}
    result = ctx.integration_service.create_integration_request(
        IntegrationAutomationRequest(
            prompt=str(payload.get("prompt") or ""),
            docs_url=payload.get("docs_url"),
            openapi_url=payload.get("openapi_url"),
            openapi_spec=payload.get("openapi_spec"),
            documentation_excerpt=payload.get("documentation_excerpt"),
            category=payload.get("category"),
            preferred_auth_type=payload.get("preferred_auth_type"),
        ),
        actor=str(payload.get("actor") or "assistant-tool"),
    )
    return {"summary": str(result.get("message") or "Connector isteği işlendi."), "result": result, "artifacts": [], "citations": []}


def _integration_get_connector_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    if ctx.integration_service is None:
        return {"summary": "Integration service kullanılamıyor.", "artifacts": [], "citations": []}
    connector_id = str(payload.get("connector_id") or "").strip()
    catalog = ctx.integration_service.list_catalog(query=connector_id or None, category=payload.get("category"))
    item = next((candidate for candidate in catalog.get("items") or [] if str(candidate.get("connector", {}).get("id") or "") == connector_id), None)
    summary = f"{connector_id} connector kaydı bulundu." if item else "Connector bulunamadı."
    return {"summary": summary, "item": item, "catalog": catalog, "artifacts": [], "citations": []}


def _integration_review_connector_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    if ctx.integration_service is None:
        return {"summary": "Integration service kullanılamıyor.", "artifacts": [], "citations": []}
    result = ctx.integration_service.review_generated_connector(
        str(payload.get("connector_id") or ""),
        IntegrationGeneratedConnectorReviewRequest(
            decision=str(payload.get("decision") or "approve"),
            notes=str(payload.get("notes") or "") or None,
            live_use_enabled=bool(payload.get("live_use_enabled")),
        ),
        actor=str(payload.get("actor") or "assistant-tool"),
    )
    return {"summary": str(result.get("message") or "Connector review tamamlandı."), "result": result, "artifacts": [], "citations": []}


def _integration_preview_connection_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    if ctx.integration_service is None:
        return {"summary": "Integration service kullanılamıyor.", "artifacts": [], "citations": []}
    result = ctx.integration_service.preview_connection(IntegrationConnectionPayload(**payload))
    return {"summary": str(result.get("validation", {}).get("message") or "Bağlantı önizlemesi hazır."), "result": result, "artifacts": [], "citations": []}


def _integration_save_connection_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    if ctx.integration_service is None:
        return {"summary": "Integration service kullanılamıyor.", "artifacts": [], "citations": []}
    actor = str(payload.pop("actor", "") or "assistant-tool")
    result = ctx.integration_service.save_connection(IntegrationConnectionPayload(**payload), actor=actor)
    return {"summary": str(result.get("message") or "Bağlantı kaydedildi."), "result": result, "artifacts": [], "citations": []}


def _integration_start_oauth_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    if ctx.integration_service is None:
        return {"summary": "Integration service kullanılamıyor.", "artifacts": [], "citations": []}
    result = ctx.integration_service.start_oauth_authorization(
        int(payload.get("connection_id") or 0),
        IntegrationOAuthStartRequest(
            redirect_uri=payload.get("redirect_uri"),
            requested_scopes=list(payload.get("requested_scopes") or []),
        ),
        actor=str(payload.get("actor") or "assistant-tool"),
    )
    return {"summary": str(result.get("message") or "OAuth akışı başlatıldı."), "result": result, "artifacts": [], "citations": []}


def _integration_sync_now_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    if ctx.integration_service is None:
        return {"summary": "Integration service kullanılamıyor.", "artifacts": [], "citations": []}
    result = ctx.integration_service.sync_connection(int(payload.get("connection_id") or 0), actor=str(payload.get("actor") or "assistant-tool"))
    return {"summary": str(result.get("message") or "Sync tamamlandı."), "result": result, "artifacts": [], "citations": []}


def _integration_get_connection_status_tool(payload: dict[str, Any], ctx: ToolExecutionContext) -> dict[str, Any]:
    if ctx.integration_service is None:
        return {"summary": "Integration service kullanılamıyor.", "artifacts": [], "citations": []}
    detail = ctx.integration_service.get_connection_detail(int(payload.get("connection_id") or 0))
    summary = str(detail.get("connection", {}).get("health_message") or detail.get("connection", {}).get("status") or "Bağlantı durumu alındı.")
    return {"summary": summary, "detail": detail, "artifacts": [], "citations": []}


def _tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="assistant.home",
            title="Asistan Özeti",
            description="Ajanda, inbox ve onay kuyruklarından günlük özet çıkarır.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=10,
            allowed_scopes=("office", "assistant"),
            input_schema={},
            output_schema={"home": "object"},
            tags=("assistant", "agenda"),
        ),
        ToolSpec(
            name="assistant.inbox",
            title="İletişim Kutusu",
            description="Gmail, Outlook, WhatsApp, X ve diğer iletişim sinyallerini okur.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=10,
            allowed_scopes=("office", "assistant", "external"),
            input_schema={},
            output_schema={"items": "array"},
            tags=("assistant", "inbox"),
        ),
        ToolSpec(
            name="assistant.calendar",
            title="Takvim Görünümü",
            description="Takvim kayıtlarını ve RSVP sinyallerini değerlendirir.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=10,
            allowed_scopes=("office", "assistant", "calendar"),
            input_schema={"window_days": "integer"},
            output_schema={"items": "array"},
            tags=("assistant", "calendar"),
        ),
        ToolSpec(
            name="assistant.profile_dates",
            title="Kişisel Tarihler",
            description="Kullanıcı profiline kaydedilmiş yaklaşan önemli tarihleri toplar.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=10,
            allowed_scopes=("assistant", "profile", "calendar"),
            input_schema={"window_days": "integer", "limit": "integer"},
            output_schema={"items": "array"},
            tags=("assistant", "profile"),
        ),
        ToolSpec(
            name="web.search",
            title="Web Arama",
            description="Güncel web sonuçlarını toplar.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=20,
            allowed_scopes=("external_web",),
            input_schema={"query": "string", "limit": "integer"},
            output_schema={"results": "array"},
            tags=("web", "research"),
        ),
        ToolSpec(
            name="youtube.search",
            title="YouTube Arama",
            description="YouTube üzerinde ilgili videoları araştırır.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=20,
            allowed_scopes=("external_web", "video"),
            input_schema={"query": "string", "limit": "integer"},
            output_schema={"results": "array"},
            tags=("youtube", "research", "video"),
        ),
        ToolSpec(
            name="travel.search",
            title="Seyahat Araştırması",
            description="Seyahat seçeneklerini ve rezervasyon bağlantısını toplar.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=20,
            allowed_scopes=("travel", "external_web", "profile"),
            input_schema={"query": "string", "limit": "integer"},
            output_schema={"results": "array", "booking_url": "string"},
            tags=("travel", "research"),
        ),
        ToolSpec(
            name="weather.search",
            title="Hava Durumu Araştırması",
            description="Hava durumu ve kısa dış ortam bağlamı için güncel sonuç toplar.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=20,
            allowed_scopes=("weather", "external_web", "profile"),
            input_schema={"query": "string", "limit": "integer"},
            output_schema={"results": "array"},
            tags=("weather", "research"),
        ),
        ToolSpec(
            name="places.search",
            title="Mekân ve Rota Araştırması",
            description="Yakındaki mekânları, uygun seçenekleri ve harita bağlantısını toplar.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=20,
            allowed_scopes=("places", "external_web", "profile"),
            input_schema={"query": "string", "limit": "integer"},
            output_schema={"results": "array", "map_url": "string"},
            tags=("places", "research"),
        ),
        ToolSpec(
            name="web.inspect",
            title="Web Sayfası İnceleme",
            description="Sayfayı render ederek veya ucuz modda inceleyip metin, başlık ve artifact çıkarır.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=30,
            allowed_scopes=("external_web",),
            input_schema={"url": "string", "render_mode": "string", "include_screenshot": "boolean"},
            output_schema={"inspection": "object", "artifacts": "array"},
            tags=("web", "browser"),
        ),
        ToolSpec(
            name="web.crawl",
            title="Site Taraması",
            description="Aynı alan adındaki sayfaları yüzeysel tarayıp ilgili alt sayfaları toplar.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=35,
            allowed_scopes=("external_web",),
            input_schema={"url": "string", "query": "string", "max_pages": "integer", "render_mode": "string"},
            output_schema={"crawl": "object"},
            tags=("web", "crawl", "browser"),
        ),
        ToolSpec(
            name="video.analyze",
            title="Video Özetleme",
            description="YouTube video transkriptini çözümleyip alıntı üretir.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=30,
            allowed_scopes=("video", "external_web"),
            input_schema={"url": "string", "transcript_text": "string", "max_segments": "integer"},
            output_schema={"analysis": "object"},
            tags=("youtube", "video", "summary"),
        ),
        ToolSpec(
            name="matter.search",
            title="Dosya İçi Arama",
            description="Matter kapsamındaki belgelerde dayanak parçaları bulur.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=12,
            allowed_scopes=("matter", "documents"),
            input_schema={"matter_id": "integer", "query": "string", "limit": "integer"},
            output_schema={"results": "array"},
            tags=("matter", "citations"),
        ),
        ToolSpec(
            name="workspace.search",
            title="Çalışma Alanı Arama",
            description="Aktif çalışma alanı belgelerinde dayanak parçaları bulur.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=12,
            allowed_scopes=("workspace", "documents"),
            input_schema={"query": "string", "limit": "integer"},
            output_schema={"results": "array"},
            tags=("workspace", "citations"),
        ),
        ToolSpec(
            name="social.monitor",
            title="Sosyal İzleme",
            description="Sosyal medya risk ve etkileşim sinyallerini özetler.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=10,
            allowed_scopes=("external", "social"),
            input_schema={"limit": "integer"},
            output_schema={"snapshot": "object"},
            tags=("social", "risk"),
        ),
        ToolSpec(
            name="integrations.request_connector",
            title="Connector İsteği",
            description="Doğal dil veya OpenAPI girdisinden connector üretir.",
            tool_class="write",
            risk_level="medium",
            approval_policy="reviewed",
            idempotent=False,
            timeout_seconds=20,
            allowed_scopes=("assistant", "integrations"),
            input_schema={"prompt": "string"},
            output_schema={"result": "object"},
            tags=("integrations", "generator"),
        ),
        ToolSpec(
            name="integrations.get_connector",
            title="Connector Bul",
            description="Catalog veya generated registry içinden connector arar.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=10,
            allowed_scopes=("assistant", "integrations"),
            input_schema={"connector_id": "string"},
            output_schema={"item": "object"},
            tags=("integrations", "catalog"),
        ),
        ToolSpec(
            name="integrations.review_connector",
            title="Connector Review",
            description="Generated connector review kararı verir.",
            tool_class="write",
            risk_level="high",
            approval_policy="reviewed",
            idempotent=False,
            timeout_seconds=15,
            allowed_scopes=("assistant", "integrations"),
            input_schema={"connector_id": "string", "decision": "string"},
            output_schema={"result": "object"},
            tags=("integrations", "governance"),
        ),
        ToolSpec(
            name="integrations.preview_connection",
            title="Bağlantı Önizle",
            description="Connector konfigürasyonunu doğrular.",
            tool_class="read",
            risk_level="medium",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=15,
            allowed_scopes=("assistant", "integrations"),
            input_schema={"connector_id": "string"},
            output_schema={"result": "object"},
            tags=("integrations", "validation"),
        ),
        ToolSpec(
            name="integrations.save_connection",
            title="Bağlantıyı Kaydet",
            description="Connector bağlantısını güvenli kasada saklar.",
            tool_class="write",
            risk_level="high",
            approval_policy="reviewed",
            idempotent=False,
            timeout_seconds=15,
            allowed_scopes=("assistant", "integrations"),
            input_schema={"connector_id": "string"},
            output_schema={"result": "object"},
            tags=("integrations", "connect"),
        ),
        ToolSpec(
            name="integrations.start_oauth",
            title="OAuth Başlat",
            description="Platform-managed connector için OAuth akışını başlatır.",
            tool_class="write",
            risk_level="medium",
            approval_policy="reviewed",
            idempotent=False,
            timeout_seconds=15,
            allowed_scopes=("assistant", "integrations"),
            input_schema={"connection_id": "integer"},
            output_schema={"result": "object"},
            tags=("integrations", "oauth"),
        ),
        ToolSpec(
            name="integrations.sync_now",
            title="Şimdi Sync Et",
            description="Bağlı connector için manuel sync çalıştırır.",
            tool_class="write",
            risk_level="medium",
            approval_policy="reviewed",
            idempotent=False,
            timeout_seconds=30,
            allowed_scopes=("assistant", "integrations"),
            input_schema={"connection_id": "integer"},
            output_schema={"result": "object"},
            tags=("integrations", "sync"),
        ),
        ToolSpec(
            name="integrations.get_connection_status",
            title="Bağlantı Durumu",
            description="Bağlı connector için sağlık ve sync durumunu getirir.",
            tool_class="read",
            risk_level="low",
            approval_policy="none",
            idempotent=True,
            timeout_seconds=10,
            allowed_scopes=("assistant", "integrations"),
            input_schema={"connection_id": "integer"},
            output_schema={"detail": "object"},
            tags=("integrations", "status"),
        ),
    )


class ToolRegistry:
    def __init__(self, ctx: ToolExecutionContext) -> None:
        self.ctx = ctx
        self._specs = {item.name: item for item in _tool_specs()}
        self._executors: dict[str, Callable[[dict[str, Any], ToolExecutionContext], dict[str, Any]]] = {
            "assistant.home": _assistant_home_tool,
            "assistant.inbox": _assistant_inbox_tool,
            "assistant.calendar": _assistant_calendar_tool,
            "assistant.profile_dates": _assistant_profile_dates_tool,
            "web.search": _web_search_tool,
            "youtube.search": _youtube_search_tool,
            "travel.search": _travel_search_tool,
            "weather.search": _weather_search_tool,
            "places.search": _places_search_tool,
            "web.inspect": _web_inspect_tool,
            "web.crawl": _web_crawl_tool,
            "video.analyze": _video_analyze_tool,
            "matter.search": _matter_search_tool,
            "workspace.search": _workspace_search_tool,
            "social.monitor": _social_monitor_tool,
            "integrations.request_connector": _integration_request_connector_tool,
            "integrations.get_connector": _integration_get_connector_tool,
            "integrations.review_connector": _integration_review_connector_tool,
            "integrations.preview_connection": _integration_preview_connection_tool,
            "integrations.save_connection": _integration_save_connection_tool,
            "integrations.start_oauth": _integration_start_oauth_tool,
            "integrations.sync_now": _integration_sync_now_tool,
            "integrations.get_connection_status": _integration_get_connection_status_tool,
        }

    def list_tools(self) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in self._specs.values()]

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(str(name or "").strip())

    def execute(self, name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        spec = self.get(name)
        if not spec:
            raise KeyError(f"unknown_tool:{name}")
        executor = self._executors.get(spec.name)
        if executor is None:
            raise KeyError(f"missing_executor:{name}")
        return executor(payload or {}, self.ctx)


def create_tool_registry(*, settings: Any, store: Any, events: Any, web_intel: Any, integration_service: Any = None) -> ToolRegistry:
    return ToolRegistry(
        ToolExecutionContext(
            settings=settings,
            store=store,
            events=events,
            web_intel=web_intel,
            integration_service=integration_service,
        )
    )
