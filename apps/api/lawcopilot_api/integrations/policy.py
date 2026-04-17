from __future__ import annotations

from typing import Any

from ..policies import evaluate_execution_gateway
from .models import ConnectorSpec, IntegrationActionSpec


DESTRUCTIVE_OPERATIONS = {
    "delete",
}

WRITE_OPERATIONS = {
    "create",
    "update",
    "send_message",
    "create_page",
    "append_block",
    "insert_record",
    "update_record",
    "upload_file",
}

LOW_RISK_WRITE_OPERATIONS = {
    "update",
    "append_block",
    "update_record",
}


def _action_risk_level(action: IntegrationActionSpec) -> str:
    operation = str(action.operation or "").strip().lower()
    access = str(action.access or "").strip().lower()
    if operation in DESTRUCTIVE_OPERATIONS or access in {"delete", "admin"}:
        return "D"
    if operation in WRITE_OPERATIONS or access in {"write", "admin"}:
        return "B"
    return "A"


def _action_tool_class(action: IntegrationActionSpec) -> str:
    operation = str(action.operation or "").strip().lower()
    access = str(action.access or "").strip().lower()
    if operation in WRITE_OPERATIONS or operation in DESTRUCTIVE_OPERATIONS or access in {"write", "delete", "admin"}:
        return "write"
    return "read"


def _action_reversible(action: IntegrationActionSpec) -> bool:
    operation = str(action.operation or "").strip().lower()
    access = str(action.access or "").strip().lower()
    if operation in DESTRUCTIVE_OPERATIONS or access in {"delete", "admin"}:
        return False
    if operation in WRITE_OPERATIONS or access in {"write", "admin"}:
        return operation in LOW_RISK_WRITE_OPERATIONS
    return True


def _connection_scope(connection: dict[str, Any]) -> str:
    scopes = [str(item or "").strip().lower() for item in list(connection.get("scopes") or []) if str(item or "").strip()]
    if any(scope.startswith("legal") for scope in scopes):
        return "legal"
    if any(scope.startswith("workspace") or scope.startswith("professional") or scope.startswith("project:") for scope in scopes):
        return "professional"
    if any(scope.startswith("personal") for scope in scopes):
        return "personal"
    return "professional"


def build_safety_settings(connection: dict[str, Any], spec: ConnectorSpec) -> dict[str, Any]:
    metadata = dict(connection.get("metadata") or {})
    configured = dict(metadata.get("safety_settings") or {})
    access_level = str(connection.get("access_level") or spec.default_access_level)
    read_enabled = configured.get("read_enabled", True)
    write_enabled = configured.get("write_enabled", access_level in {"read_write", "admin_like"})
    delete_enabled = configured.get("delete_enabled", access_level == "admin_like")
    require_confirmation_for_write = configured.get("require_confirmation_for_write", True)
    require_confirmation_for_delete = configured.get("require_confirmation_for_delete", True)
    return {
        "read_enabled": bool(read_enabled),
        "write_enabled": bool(write_enabled),
        "delete_enabled": bool(delete_enabled),
        "require_confirmation_for_write": bool(require_confirmation_for_write),
        "require_confirmation_for_delete": bool(require_confirmation_for_delete),
    }


def discover_capabilities(connection: dict[str, Any], spec: ConnectorSpec) -> dict[str, Any]:
    access_level = str(connection.get("access_level") or spec.default_access_level)
    permission = next((item for item in spec.permissions if item.level == access_level), None)
    granted_operations = set(permission.allowed_operations if permission else [])
    safety_settings = build_safety_settings(connection, spec)
    auth_summary = dict(connection.get("auth_summary") or {})

    allowed_actions: list[dict[str, Any]] = []
    blocked_actions: list[dict[str, Any]] = []
    for action in spec.actions:
        decision = evaluate_action_policy(
            connection=connection,
            spec=spec,
            action=action,
            confirmed=False,
            allow_pending_confirmation=True,
        )
        item = {
            "key": action.key,
            "title": action.title,
            "operation": action.operation,
            "access": action.access,
            "requires_confirmation": bool(decision["requires_confirmation"]),
            "reason": decision["reason"],
        }
        if decision["allowed"]:
            allowed_actions.append(item)
        else:
            blocked_actions.append(item)

    return {
        "connector_id": spec.id,
        "access_level": access_level,
        "permission_summary": {
            "label": permission.label if permission else access_level,
            "description": permission.description if permission else "",
            "allowed_operations": sorted(granted_operations),
        },
        "auth_summary": auth_summary,
        "safety_settings": safety_settings,
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
    }


def evaluate_action_policy(
    *,
    connection: dict[str, Any],
    spec: ConnectorSpec,
    action: IntegrationActionSpec,
    confirmed: bool,
    allow_pending_confirmation: bool = False,
) -> dict[str, Any]:
    access_level = str(connection.get("access_level") or spec.default_access_level)
    permission = next((item for item in spec.permissions if item.level == access_level), None)
    granted_operations = set(permission.allowed_operations if permission else [])
    safety_settings = build_safety_settings(connection, spec)
    auth_summary = dict(connection.get("auth_summary") or {})
    auth_status = str(auth_summary.get("status") or "")

    if not bool(connection.get("enabled", True)):
        return _decision(False, "Baglanti devre disi.", False, access_level, safety_settings)
    if str(connection.get("status") or "").lower() in {"revoked", "disconnected"}:
        return _decision(False, "Baglanti aktif degil.", False, access_level, safety_settings)
    if auth_status in {"authorization_required", "expired", "revoked", "error"}:
        return _decision(False, f"Kimlik durumu uygun degil: {auth_status or 'bilinmiyor'}.", False, access_level, safety_settings)

    if action.operation not in granted_operations and action.access not in granted_operations:
        return _decision(False, "Bu aksiyon erisim seviyeniz icin kapali.", False, access_level, safety_settings)

    if action.access == "read" and not safety_settings["read_enabled"]:
        return _decision(False, "Okuma aksiyonlari guvenlik politikasiyla kapatildi.", False, access_level, safety_settings)
    if action.access in {"write", "admin"} and not safety_settings["write_enabled"]:
        return _decision(False, "Yazma aksiyonlari guvenlik politikasiyla kapatildi.", False, access_level, safety_settings)
    if action.access == "delete" and not safety_settings["delete_enabled"]:
        return _decision(False, "Silme aksiyonlari guvenlik politikasiyla kapatildi.", False, access_level, safety_settings)

    if action.access == "delete" and not spec.capability_flags.get("delete", False):
        return _decision(False, "Connector silme kabiliyeti sunmuyor.", False, access_level, safety_settings)
    if action.access in {"write", "admin"} and not spec.capability_flags.get("write", False):
        return _decision(False, "Connector yazma kabiliyeti sunmuyor.", False, access_level, safety_settings)
    if action.access == "read" and not spec.capability_flags.get("read", True):
        return _decision(False, "Connector okuma kabiliyeti sunmuyor.", False, access_level, safety_settings)

    operation = str(action.operation or "").strip().lower()
    access = str(action.access or "").strip().lower()
    requires_confirmation = bool(action.approval_required)
    if operation in DESTRUCTIVE_OPERATIONS or access == "delete":
        requires_confirmation = bool(True or safety_settings["require_confirmation_for_delete"])
    elif operation in WRITE_OPERATIONS or access in {"write", "admin"}:
        requires_confirmation = bool(requires_confirmation or safety_settings["require_confirmation_for_write"])

    execution = evaluate_execution_gateway(
        action_kind=operation or "tool_execution",
        risk_level=_action_risk_level(action),
        approval_policy="reviewed" if requires_confirmation else "none",
        tool_class=_action_tool_class(action),
        scope=_connection_scope(connection),
        suggest_only=False,
        reversible=_action_reversible(action),
        current_stage="execute",
        preview_summary=action.title,
        audit_label=f"integration:{spec.id}:{action.key}",
    )
    policy_decision = execution.policy_decision

    if policy_decision.requires_confirmation and not confirmed and not allow_pending_confirmation:
        return _decision(
            False,
            "Bu aksiyon icin acik onay gerekli.",
            True,
            access_level,
            safety_settings,
            policy_decision=policy_decision.as_dict(),
        )

    reason = policy_decision.reason_summary if not policy_decision.requires_confirmation or confirmed else "Aksiyon onay bekliyor."
    return _decision(
        True,
        reason,
        bool(policy_decision.requires_confirmation),
        access_level,
        safety_settings,
        policy_decision=policy_decision.as_dict(),
    )


def _decision(
    allowed: bool,
    reason: str,
    requires_confirmation: bool,
    access_level: str,
    safety_settings: dict[str, Any],
    *,
    policy_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "reason": reason,
        "requires_confirmation": requires_confirmation,
        "access_level": access_level,
        "safety_settings": safety_settings,
        "policy_decision": policy_decision or {},
    }
