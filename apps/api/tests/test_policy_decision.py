from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lawcopilot_api.knowledge_base import KnowledgeBaseService
from lawcopilot_api.persistence import Persistence
from lawcopilot_api.policies.approval import build_approval_request, tool_requires_approval
from lawcopilot_api.policies import evaluate_execution_gateway, resolve_action_policy, resolve_proactive_policy


def test_action_policy_requires_confirmation_for_reviewed_write() -> None:
    decision = resolve_action_policy(
        action_kind="tool_execution",
        risk_level="medium",
        approval_policy="reviewed",
        tool_class="write",
        scope="professional",
    )

    assert decision.decision == "ask_confirm"
    assert decision.requires_confirmation is True
    assert "approval_policy_active" in decision.reason_codes
    assert "confirmation_required" in decision.reason_codes


def test_proactive_policy_silences_fatigue_prone_low_confidence_signal() -> None:
    decision = resolve_proactive_policy(
        action_kind="read_summary",
        risk_level="A",
        confidence=0.56,
        urgency="low",
        reminder_tolerance="soft",
        interruption_tolerance="low",
        recent_rejection_count=3,
        trigger_type="daily_planning",
    )

    assert decision.decision == "silence"
    assert decision.suppression_reason == "fatigue_guard_active"


def test_recommendation_payload_exposes_central_policy_decisions(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "policy-recommendations.db")
    office_id = "default-office"
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)

    payload = knowledge_base.recommend(
        store=store,
        settings=None,
        current_context="Bugün kısa ve sakin bir akış istiyorum.",
        location_context="Kadıköy",
        limit=3,
        persist=False,
    )

    assert payload["items"]
    first = payload["items"][0]
    assert first["policy_decision"]["decision"] in {"draft", "preview"}
    assert first["governor_decision"]["decision"] == "suggest"
    assert first["action_ladder"]["policy_decision"]["decision"] == first["policy_decision"]["decision"]


def test_trigger_payload_exposes_central_policy_decisions(tmp_path: Path) -> None:
    store = Persistence(tmp_path / "policy-triggers.db")
    office_id = "default-office"
    knowledge_base = KnowledgeBaseService(tmp_path / "personal-kb", office_id)

    payload = knowledge_base.evaluate_triggers(
        store=store,
        settings=None,
        now=datetime(2026, 4, 12, 8, 30, tzinfo=timezone.utc),
        persist=False,
        limit=4,
        include_suppressed=False,
    )

    assert payload["items"]
    first = payload["items"][0]
    assert first["policy_decision"]["decision"] in {"draft", "preview"}
    assert first["governor_decision"]["decision"] == "suggest"
    assert first["action_ladder"]["policy_decision"]["decision"] == first["policy_decision"]["decision"]


def test_execution_gateway_keeps_policy_and_ladder_in_sync() -> None:
    execution = evaluate_execution_gateway(
        action_kind="create_task_draft",
        risk_level="C",
        policy_label="low_risk_automatic",
        auto_allowed=True,
        scope="personal",
        suggest_only=True,
        reversible=True,
        current_stage="suggest",
        preview_summary="Görev taslağı",
        audit_label="recommendation:create_task",
    )

    assert execution.policy_decision.decision == "draft"
    assert execution.action_ladder["policy_decision"]["decision"] == "draft"
    assert execution.action_ladder["trusted_low_risk_available"] is True


def test_tool_requires_approval_uses_shared_gateway_policy() -> None:
    assert tool_requires_approval("gmail_send", write=True) is True
    assert tool_requires_approval("calendar_read", write=False) is False


def test_build_approval_request_uses_gateway_reason_summary() -> None:
    payload = build_approval_request(
        action={"id": 42, "action_type": "tool_execution", "target_channel": "assistant"},
        tool_name="gmail_send",
        title="Mesaj gonder",
    )

    assert payload["approval_required"] is True
    assert payload["reason"]
    assert isinstance(payload["reason"], str)
