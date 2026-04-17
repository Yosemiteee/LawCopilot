from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from .catalog import PERMISSIONS
from .models import ConnectorSpec, IntegrationScaffoldRequest


HTTP_METHOD_TO_OPERATION = {
    "get": "get_item",
    "post": "create",
    "put": "update",
    "patch": "update",
    "delete": "delete",
}


def generate_connector_scaffold(payload: IntegrationScaffoldRequest) -> dict[str, Any]:
    service_name = str(payload.service_name)
    openapi = _parse_openapi(payload.openapi_spec)
    docs_excerpt = str(payload.documentation_excerpt or "")
    inferred_category = _infer_category(service_name, payload.category, openapi, docs_excerpt)
    inferred_auth = _infer_auth(
        service_name,
        payload.docs_url,
        payload.openapi_url,
        payload.preferred_auth_type,
        openapi,
        docs_excerpt,
    )
    connector_id = _slugify(service_name)
    resources = _infer_resources(openapi)
    actions = _infer_actions(openapi, inferred_category)
    ui_schema = _build_ui_schema(inferred_auth)
    connector = ConnectorSpec.model_validate(
        {
            "id": connector_id,
            "name": service_name,
            "description": f"{service_name} icin yari-otomatik connector taslagi.",
            "category": inferred_category,
            "auth_type": inferred_auth,
            "auth_config": {
                "client_configurable": True,
                "supports_refresh": inferred_auth == "oauth2",
                "default_scopes": _infer_scopes(openapi),
                "notes": ["Bu taslak insan incelemesi olmadan etkinlestirilmemelidir."],
            },
            "resources": resources or [
                {
                    "key": "primary",
                    "title": "Ana kaynak",
                    "description": "OpenAPI veya dokuman ayrintisi sonrasi netlestirilecek ana nesne grubu.",
                    "item_types": ["item"],
                    "supports_search": True,
                }
            ],
            "actions": actions,
            "triggers": [],
            "sync_policies": [{"mode": "manual", "default_strategy": "Review-gated operator sync"}],
            "pagination_strategy": {"type": "cursor"},
            "webhook_support": {"supported": False},
            "rate_limit": {"strategy": "unknown"},
            "ui_schema": ui_schema,
            "permissions": [item.model_dump(mode="json") for item in PERMISSIONS],
            "capability_flags": {
                "read": True,
                "write": any(item.get("access") in {"write", "admin"} for item in actions),
                "delete": any(item.get("operation") == "delete" for item in actions),
            },
            "management_mode": "platform",
            "default_access_level": "read_only",
            "tags": ["scaffold", "review-required", "openapi-aware"],
            "docs_url": payload.docs_url or payload.openapi_url,
            "setup_hint": "Connector taslagi etkinlestirilmeden once auth, pagination, retry ve fixture testleri tamamlanmali.",
        }
    )
    validation_tests = _build_validation_tests(connector, openapi)
    mock_fixtures = _build_mock_fixtures(connector, resources)
    warnings = [
        "Scaffold ciktilari insan incelemesi olmadan production akisina alinmamalidir.",
        "Rate limit, webhook imzasi ve gercek auth contract'i saglayici dokumaniyla teyit edilmelidir.",
    ]
    if payload.docs_url and not openapi:
        warnings.append("OpenAPI spec gelmedigi icin endpoint inference dokuman anahtar kelimeleriyle sinirli kaldi.")
    return {
        "service_name": service_name,
        "inference": {
            "connector_id": connector_id,
            "category": inferred_category,
            "auth_type": inferred_auth,
            "docs_url": payload.docs_url,
            "openapi_url": payload.openapi_url,
        },
        "connector": connector.model_dump(mode="json"),
        "review_gate": {
            "required": True,
            "checklist": [
                "Scope daraltma ve least-privilege kontrolu yapildi mi?",
                "Retry/backoff ve idempotency davranisi dogrulandi mi?",
                "Yazma ve silme aksiyonlari icin insan onayi ayarlandi mi?",
                "Mock fixture, route testi ve sync smoke testi eklendi mi?",
            ],
        },
        "warnings": warnings,
        "suggested_validation_tests": validation_tests,
        "mock_fixtures": mock_fixtures,
        "generated_from": "integration_scaffold_generator_v2",
    }


def prepare_scaffold_request(
    payload: IntegrationScaffoldRequest,
    *,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 20,
) -> tuple[IntegrationScaffoldRequest, dict[str, Any]]:
    hydrated = payload.model_dump(mode="json")
    warnings: list[str] = []
    fetch_summary = {
        "openapi_fetched": False,
        "docs_fetched": False,
        "sources": [],
    }

    if not str(hydrated.get("openapi_spec") or "").strip() and payload.openapi_url:
        fetched = _fetch_remote_text(str(payload.openapi_url), transport=transport, timeout_seconds=timeout_seconds)
        if fetched["text"]:
            fetch_summary["sources"].append({"kind": "openapi_url", "url": str(payload.openapi_url), "status": "fetched"})
            openapi_text = _extract_openapi_text(fetched["text"])
            if openapi_text:
                hydrated["openapi_spec"] = openapi_text
                fetch_summary["openapi_fetched"] = True
            else:
                warnings.append("OpenAPI URL cekildi fakat JSON/OpenAPI formatina donusturulemedi.")
        elif fetched["warning"]:
            warnings.append(str(fetched["warning"]))

    if (not str(hydrated.get("documentation_excerpt") or "").strip() or not str(hydrated.get("openapi_spec") or "").strip()) and payload.docs_url:
        fetched = _fetch_remote_text(str(payload.docs_url), transport=transport, timeout_seconds=timeout_seconds)
        if fetched["text"]:
            fetch_summary["sources"].append({"kind": "docs_url", "url": str(payload.docs_url), "status": "fetched"})
            excerpt = _extract_text_excerpt(fetched["text"])
            if excerpt and not str(hydrated.get("documentation_excerpt") or "").strip():
                hydrated["documentation_excerpt"] = excerpt
                fetch_summary["docs_fetched"] = True
            if not str(hydrated.get("openapi_spec") or "").strip():
                openapi_text = _extract_openapi_text(fetched["text"])
                if openapi_text:
                    hydrated["openapi_spec"] = openapi_text
                    fetch_summary["openapi_fetched"] = True
        elif fetched["warning"]:
            warnings.append(str(fetched["warning"]))

    prepared = IntegrationScaffoldRequest.model_validate(hydrated)
    return prepared, {"warnings": warnings, "fetch_summary": fetch_summary}


def _parse_openapi(raw: str | None) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _infer_auth(
    service_name: str,
    docs_url: str | None,
    openapi_url: str | None,
    preferred_auth_type: str | None,
    openapi: dict[str, Any] | None,
    documentation_excerpt: str | None = None,
) -> str:
    preferred = str(preferred_auth_type or "").strip().lower()
    if preferred:
        return preferred
    if openapi:
        security_schemes = dict(openapi.get("components", {}).get("securitySchemes") or {})
        for scheme in security_schemes.values():
            if not isinstance(scheme, dict):
                continue
            scheme_type = str(scheme.get("type") or "").lower()
            if scheme_type == "oauth2":
                return "oauth2"
            if scheme_type == "apikey":
                return "api_key"
            if scheme_type == "http" and str(scheme.get("scheme") or "").lower() == "bearer":
                return "bearer"
    haystack = " ".join([service_name, str(docs_url or ""), str(openapi_url or ""), str(documentation_excerpt or "")]).lower()
    if any(token in haystack for token in ("oauth", "auth0", "openid", "login")):
        return "oauth2"
    if any(token in haystack for token in ("postgres", "mysql", "mssql", "sql server", "sqlserver", "database", "sql", "elastic")):
        return "database"
    if "bearer" in haystack:
        return "bearer"
    return "api_key"


def _infer_category(service_name: str, explicit: str | None, openapi: dict[str, Any] | None, documentation_excerpt: str | None = None) -> str:
    if explicit:
        return explicit
    title = " ".join([service_name, json.dumps(openapi or {}, ensure_ascii=False), str(documentation_excerpt or "")]).lower()
    if any(token in title for token in ("mail", "message", "chat", "slack", "discord")):
        return "communication"
    if any(token in title for token in ("tiktok", "instagram", "facebook", "linkedin", "twitter", "social")):
        return "social-media"
    if any(token in title for token in ("calendar", "event", "meeting")):
        return "calendar"
    if any(token in title for token in ("file", "drive", "storage", "document")):
        return "storage"
    if any(token in title for token in ("contact", "crm", "hubspot")):
        return "crm"
    if any(token in title for token in ("postgres", "mysql", "mssql", "sql server", "sqlserver", "database", "sql")):
        return "database"
    return "custom-api"


def _infer_resources(openapi: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not openapi:
        return []
    resources: dict[str, dict[str, Any]] = {}
    for path in dict(openapi.get("paths") or {}):
        name = _resource_name_from_path(path)
        if not name:
            continue
        item = resources.setdefault(
            name,
            {
                "key": name,
                "title": name.replace("-", " ").title(),
                "description": f"{name} kaynaklari",
                "item_types": [name.rstrip("s") or name],
                "supports_search": False,
            },
        )
        if re.search(r"search|query|find", path, re.IGNORECASE):
            item["supports_search"] = True
    return list(resources.values())[:12]


def _infer_actions(openapi: dict[str, Any] | None, category: str) -> list[dict[str, Any]]:
    actions: dict[str, dict[str, Any]] = {}
    if openapi:
        for path, operations in dict(openapi.get("paths") or {}).items():
            if not isinstance(operations, dict):
                continue
            for method, operation in operations.items():
                normalized_method = str(method).lower()
                if normalized_method not in HTTP_METHOD_TO_OPERATION:
                    continue
                inferred_operation = _infer_operation_for_endpoint(path=path, method=normalized_method, category=category)
                key = str(operation.get("operationId") or inferred_operation)
                access = "read"
                approval_required = False
                if inferred_operation in {"create", "update"}:
                    access = "write"
                    approval_required = True
                if inferred_operation == "delete":
                    access = "delete"
                    approval_required = True
                response_items_path = _infer_response_items_path(operation, inferred_operation)
                response_item_path = None if response_items_path else _infer_response_item_path(operation)
                actions[key] = {
                    "key": _slugify(key),
                    "title": str(operation.get("summary") or key.replace("_", " ").title()),
                    "description": str(operation.get("description") or f"{path} endpointi icin {inferred_operation} aksiyonu."),
                    "operation": inferred_operation,
                    "access": access,
                    "approval_required": approval_required,
                    "method": normalized_method.upper(),
                    "path": path,
                    "response_items_path": response_items_path,
                    "response_item_path": response_item_path,
                    "query_map": _infer_query_map(operation),
                }
    if actions:
        return list(actions.values())[:20]
    defaults = {
        "database": ["list_databases", "run_query", "insert_record", "update_record"],
        "communication": ["read_messages", "send_message", "search"],
        "storage": ["list_items", "get_item", "download_file", "upload_file"],
    }
    operations = defaults.get(category, ["list_items", "get_item", "search", "create", "update"])
    items = []
    for operation in operations:
        access = "read"
        approval_required = False
        if operation in {"create", "update", "send_message", "upload_file", "insert_record", "update_record"}:
            access = "write"
            approval_required = True
        items.append(
            {
                "key": operation,
                "title": operation.replace("_", " ").title(),
                "description": f"{operation} aksiyonu icin taslak.",
                "operation": operation,
                "access": access,
                "approval_required": approval_required,
                "method": _default_method_for_operation(operation),
            }
        )
    return items


def _infer_operation_for_endpoint(*, path: str, method: str, category: str) -> str:
    normalized_method = str(method or "").lower()
    lower_path = str(path or "").lower()
    resource_name = _resource_name_from_path(path)
    has_path_param = "{" in lower_path and "}" in lower_path
    if normalized_method == "get":
        if re.search(r"search|query|find", lower_path, re.IGNORECASE):
            return "search"
        if any(token in resource_name for token in ("message", "channel", "thread")) and category == "communication":
            return "get_item" if has_path_param else "read_messages"
        if any(token in resource_name for token in ("document", "file", "page")) and category in {"storage", "knowledge-base"}:
            return "get_item" if has_path_param else "fetch_documents"
        if any(token in resource_name for token in ("database", "table", "schema")) and category == "database":
            return "get_item" if has_path_param else "list_databases"
        return "get_item" if has_path_param else "list_items"
    if normalized_method == "post":
        if category == "communication" and any(token in lower_path for token in ("message", "postmessage", "reply", "chat")):
            return "send_message"
        if category == "database":
            return "insert_record"
        if category == "knowledge-base" and any(token in lower_path for token in ("page", "document")):
            return "create_page"
        return "create"
    if normalized_method in {"put", "patch"}:
        if category == "database":
            return "update_record"
        if category == "knowledge-base" and "block" in lower_path:
            return "append_block"
        return "update"
    if normalized_method == "delete" and category == "database":
        return "delete"
    return HTTP_METHOD_TO_OPERATION[normalized_method]


def _build_ui_schema(auth_type: str) -> list[dict[str, Any]]:
    fields = {
        "oauth2": [
            {"key": "client_id", "label": "Client ID", "kind": "text", "target": "config", "required": True},
            {"key": "client_secret", "label": "Client secret", "kind": "password", "target": "secret", "required": True, "secret": True},
            {
                "key": "redirect_uri",
                "label": "Redirect URI",
                "kind": "url",
                "target": "config",
                "required": True,
                "default": "http://localhost:3000/integrations/callback",
            },
            {"key": "base_url", "label": "Temel URL", "kind": "url", "target": "config", "required": False},
        ],
        "bearer": [
            {"key": "base_url", "label": "Temel URL", "kind": "url", "target": "config", "required": True},
            {"key": "bearer_token", "label": "Tasiyici anahtar", "kind": "password", "target": "secret", "required": True, "secret": True},
        ],
        "api_key": [
            {"key": "base_url", "label": "Temel URL", "kind": "url", "target": "config", "required": True},
            {"key": "api_key", "label": "API anahtari", "kind": "password", "target": "secret", "required": True, "secret": True},
        ],
        "database": [
            {"key": "host", "label": "Host", "kind": "text", "target": "config", "required": True},
            {"key": "username", "label": "Kullanici adi", "kind": "text", "target": "config", "required": True},
            {"key": "password", "label": "Parola", "kind": "password", "target": "secret", "required": True, "secret": True},
        ],
    }
    return fields.get(auth_type, fields["api_key"])


def _build_validation_tests(connector: ConnectorSpec, openapi: dict[str, Any] | None) -> list[dict[str, Any]]:
    tests = [
        {
            "name": "required-fields",
            "description": "Zorunlu ui_schema alanlari bosken preview invalid donmeli.",
        },
        {
            "name": "permission-gate",
            "description": "Yazma veya silme aksiyonlari acik onay olmadan bloklanmali.",
        },
        {
            "name": "sync-smoke",
            "description": "Dry-run sync en az bir normalized resource uretmeli.",
        },
    ]
    if connector.auth_type == "oauth2":
        tests.append(
            {
                "name": "oauth-lifecycle",
                "description": "Authorization start, callback, refresh ve revoke akislari denetlenmeli.",
            }
        )
    if openapi and openapi.get("paths"):
        tests.append(
            {
                "name": "path-coverage",
                "description": f"{len(dict(openapi.get('paths') or {}))} path icin en az bir fixture ve action smoke olmali.",
            }
        )
    return tests


def _build_mock_fixtures(connector: ConnectorSpec, resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fixtures = []
    for resource in resources[:4]:
        fixtures.append(
            {
                "resource_key": resource["key"],
                "response": {
                    "items": [
                        {
                            "id": f"{resource['key']}-1",
                            "title": f"Ornek {resource['title']}",
                            "updated_at": "2026-04-07T09:00:00Z",
                        }
                    ]
                },
            }
        )
    if not fixtures:
        fixtures.append(
            {
                "resource_key": "primary",
                "response": {
                    "items": [
                        {
                            "id": "primary-1",
                            "title": f"{connector.name} ornek kayit",
                        }
                    ]
                },
            }
        )
    return fixtures


def _infer_scopes(openapi: dict[str, Any] | None) -> list[str]:
    if not openapi:
        return []
    security_schemes = dict(openapi.get("components", {}).get("securitySchemes") or {})
    scopes: list[str] = []
    for scheme in security_schemes.values():
        if not isinstance(scheme, dict):
            continue
        flow_map = dict(scheme.get("flows") or {})
        for flow in flow_map.values():
            if not isinstance(flow, dict):
                continue
            scope_map = dict(flow.get("scopes") or {})
            scopes.extend(str(key) for key in scope_map if str(key).strip())
    return sorted({scope for scope in scopes if scope})[:40]


def _infer_query_map(operation: dict[str, Any]) -> dict[str, str]:
    query_map: dict[str, str] = {}
    for parameter in list(operation.get("parameters") or [])[:20]:
        if not isinstance(parameter, dict):
            continue
        if str(parameter.get("in") or "").lower() != "query":
            continue
        name = str(parameter.get("name") or "").strip()
        if name:
            query_map[name] = name
    return query_map


def _infer_response_items_path(operation: dict[str, Any], inferred_operation: str) -> str | None:
    if inferred_operation not in {"list_items", "search", "read_messages", "fetch_documents", "list_databases"}:
        return None
    if _response_has_key(operation, "results"):
        return "results"
    if _response_has_key(operation, "items"):
        return "items"
    if _response_has_key(operation, "data"):
        return "data"
    return "items"


def _infer_response_item_path(operation: dict[str, Any]) -> str | None:
    if _response_has_key(operation, "item"):
        return "item"
    if _response_has_key(operation, "data"):
        return "data"
    return None


def _response_has_key(operation: dict[str, Any], key: str) -> bool:
    responses = dict(operation.get("responses") or {})
    for response in responses.values():
        if not isinstance(response, dict):
            continue
        content = dict(response.get("content") or {})
        for media in content.values():
            if not isinstance(media, dict):
                continue
            schema = dict(media.get("schema") or {})
            properties = dict(schema.get("properties") or {})
            if key in properties:
                return True
    return False


def _default_method_for_operation(operation: str) -> str:
    if operation in {"create", "send_message", "create_page", "append_block", "insert_record", "upload_file"}:
        return "POST"
    if operation in {"update", "update_record"}:
        return "PATCH"
    if operation == "delete":
        return "DELETE"
    return "GET"


def _resource_name_from_path(path: str) -> str:
    pieces = [piece for piece in str(path or "").split("/") if piece and not piece.startswith("{")]
    if not pieces:
        return ""
    candidate = pieces[-1]
    if candidate.lower() in {"search", "query", "find"} and len(pieces) >= 2:
        candidate = pieces[-2]
    return _slugify(candidate)


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower())
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")[:64] or "connector"


def _fetch_remote_text(url: str, *, transport: httpx.BaseTransport | None, timeout_seconds: float) -> dict[str, Any]:
    cleaned = str(url or "").strip()
    if not cleaned:
        return {"text": None, "warning": None}
    try:
        with httpx.Client(transport=transport, follow_redirects=True, timeout=timeout_seconds) as client:
            response = client.get(cleaned, headers={"Accept": "application/json,text/plain,text/html;q=0.9,*/*;q=0.8"})
        response.raise_for_status()
        return {"text": response.text, "warning": None}
    except Exception as exc:  # noqa: BLE001
        parsed = urlparse(cleaned)
        host = str(parsed.hostname or cleaned)
        return {"text": None, "warning": f"{host} dokumani cekilemedi: {exc}"}


def _extract_openapi_text(text: str) -> str | None:
    cleaned = str(text or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith("{"):
        parsed = _parse_openapi(cleaned)
        if parsed and parsed.get("openapi"):
            return json.dumps(parsed, ensure_ascii=False)
    return None


def _extract_text_excerpt(text: str) -> str:
    if not text:
        return ""
    normalized = str(text)
    normalized = re.sub(r"(?is)<script.*?>.*?</script>", " ", normalized)
    normalized = re.sub(r"(?is)<style.*?>.*?</style>", " ", normalized)
    normalized = re.sub(r"(?s)<[^>]+>", " ", normalized)
    normalized = html.unescape(normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:12000]
