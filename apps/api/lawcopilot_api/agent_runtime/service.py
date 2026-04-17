from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from ..connectors.web_search import (
    extract_youtube_url,
    extract_query_url,
    is_place_search_query,
    is_travel_query,
    is_video_summary_query,
    is_weather_query,
    is_web_search_query,
    is_website_crawl_query,
    is_website_review_query,
    is_youtube_search_query,
)
from ..memory import MemoryService
from ..policies import evaluate_execution_gateway
from ..social_intelligence import is_social_monitoring_query
from ..tools import ToolRegistry


@dataclass(frozen=True)
class PlannedTool:
    name: str
    title: str
    role: str
    payload: dict[str, Any]
    rationale: str


def _clean_text(value: str, *, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _is_personal_dates_query(normalized: str) -> bool:
    triggers = (
        "dogum gunu",
        "yildonumu",
        "yil donumu",
        "onemli tarih",
        "hatirlat",
        "hatirlatma",
        "kutlama",
        "birthday",
        "anniversary",
    )
    return any(token in normalized for token in triggers)


def _parse_json_object_from_text(value: str) -> dict[str, Any] | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    candidates = [cleaned]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(cleaned[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


class AgentRuntimeService:
    def __init__(
        self,
        *,
        settings: Any,
        store: Any,
        events: Any,
        audit: Any,
        tool_registry: ToolRegistry,
        memory_service: MemoryService | None = None,
        semantic_runtime: Any | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.events = events
        self.audit = audit
        self.tool_registry = tool_registry
        self.memory_service = memory_service
        self.semantic_runtime = semantic_runtime

    @staticmethod
    def _tool_policy_decision(spec: Any) -> Any:
        return evaluate_execution_gateway(
            action_kind="tool_execution",
            risk_level=getattr(spec, "risk_level", "low"),
            approval_policy=getattr(spec, "approval_policy", "none"),
            tool_class=getattr(spec, "tool_class", "read"),
            scope="assistant",
            suggest_only=False,
            reversible=bool(getattr(spec, "idempotent", False) or getattr(spec, "tool_class", "") == "read"),
            current_stage="execute",
            preview_summary=str(getattr(spec, "title", "") or getattr(spec, "name", "") or "Tool execution"),
            audit_label=f"agent-runtime:{getattr(spec, 'name', 'tool')}",
        ).policy_decision

    def _maybe_semantic_completion(self, prompt: str, *, task: str, **meta: Any) -> dict[str, Any] | None:
        runtime = self.semantic_runtime
        if runtime is None:
            return None
        try:
            completion = runtime.complete(prompt, self.events, task=task, **meta)
        except TypeError:
            result = runtime.complete(prompt)
            if getattr(result, "ok", False) and getattr(result, "text", ""):
                return {
                    "text": result.text,
                    "provider": getattr(result, "provider", ""),
                    "model": getattr(result, "model", ""),
                }
            return None
        except Exception:  # noqa: BLE001
            return None
        if isinstance(completion, dict):
            return completion
        return None

    def _semantic_plan_prompt(
        self,
        *,
        goal: str,
        matter_id: int | None,
        source_refs: list[dict[str, Any]] | None,
        render_mode: str,
        allow_browser: bool,
    ) -> str:
        target_url = self._extract_source_url(source_refs)
        return "\n".join(
            [
                "LawCopilot agent runtime için araç planı üret.",
                "Yalnız JSON döndür.",
                "Şema:",
                "{",
                '  "primary_tool": "web.inspect|web.crawl|travel.search|weather.search|places.search|web.search|youtube.search|video.analyze|social.monitor|assistant.profile_dates|assistant.home|assistant.inbox|assistant.calendar|matter.search|workspace.search|none",',
                '  "supplemental_tools": ["assistant.home","assistant.inbox","assistant.calendar","assistant.profile_dates","matter.search","workspace.search","web.search","youtube.search","social.monitor"],',
                '  "confidence": "low|medium|high",',
                '  "reason": "string"',
                "}",
                "Kurallar:",
                "- Kullanıcının niyetini anla; araç adını yalnız görev gerçekten onu gerektiriyorsa seç.",
                "- Tek sayfa inceleme gerekiyorsa web.inspect, aynı alan adı içinde çok sayfa tarama gerekiyorsa web.crawl seç.",
                "- YouTube video araması için youtube.search, belirli video özetleme için video.analyze seç.",
                "- Hava durumu, yakın mekan, rota, seyahat, sosyal sinyal, kişisel tarih ve belge arama ihtiyaçlarını ayır.",
                "- matter_id varsa ve dosya dayanağı anlamlıysa matter.search ekleyebilirsin.",
                "- Çalışma alanı belgesi araması gerekiyorsa workspace.search ekleyebilirsin.",
                "- Belirsiz ama araştırma isteyen genel isteklerde web.search seç.",
                "- Emin değilsen primary_tool=none seç.",
                "",
                f"Görev: {goal}",
                f"Matter kimliği: {matter_id or 'yok'}",
                f"Kaynak URL: {target_url or 'yok'}",
                f"Render mode: {render_mode}",
                f"Browser izinli: {bool(allow_browser)}",
            ]
        )

    def _semantic_tool_plan(
        self,
        *,
        goal: str,
        matter_id: int | None,
        source_refs: list[dict[str, Any]] | None,
        render_mode: str,
        allow_browser: bool,
    ) -> list[PlannedTool] | None:
        completion = self._maybe_semantic_completion(
            self._semantic_plan_prompt(
                goal=goal,
                matter_id=matter_id,
                source_refs=source_refs,
                render_mode=render_mode,
                allow_browser=allow_browser,
            ),
            task="agent_runtime_tool_plan",
            matter_id=matter_id,
        )
        if not completion:
            return None
        payload = _parse_json_object_from_text(str(completion.get("text") or ""))
        if not payload:
            return None
        confidence = str(payload.get("confidence") or "").strip().lower()
        if confidence not in {"medium", "high"}:
            return None

        primary = str(payload.get("primary_tool") or "").strip()
        supported = {
            "web.inspect",
            "web.crawl",
            "travel.search",
            "weather.search",
            "places.search",
            "web.search",
            "youtube.search",
            "video.analyze",
            "social.monitor",
            "assistant.profile_dates",
            "assistant.home",
            "assistant.inbox",
            "assistant.calendar",
            "matter.search",
            "workspace.search",
        }
        if primary not in supported:
            return None

        selected_names = [primary]
        for item in payload.get("supplemental_tools") or []:
            tool_name = str(item or "").strip()
            if tool_name in supported and tool_name not in selected_names:
                selected_names.append(tool_name)

        planned: list[PlannedTool] = []
        for tool_name in selected_names:
            if tool_name == "matter.search" and not matter_id:
                continue
            planned.append(
                self._planned_tool_from_name(
                    tool_name,
                    query=goal,
                    matter_id=matter_id,
                    source_refs=source_refs,
                    render_mode=self._resolve_render_mode(render_mode=render_mode, allow_browser=allow_browser),
                )
            )
        return planned or None

    def create_run(
        self,
        *,
        goal: str,
        created_by: str,
        title: str | None = None,
        matter_id: int | None = None,
        thread_id: int | None = None,
        source_kind: str = "assistant",
        run_type: str = "investigation",
        preferred_tools: list[str] | None = None,
        source_refs: list[dict[str, Any]] | None = None,
        render_mode: str = "auto",
        allow_browser: bool = True,
    ) -> dict[str, Any]:
        title = _clean_text(title or goal, limit=90) or "LawCopilot agent run"
        run = self.store.create_agent_run(
            self.settings.office_id,
            title=title,
            goal=goal,
            created_by=created_by,
            status="planning",
            matter_id=matter_id,
            thread_id=thread_id,
            source_kind=source_kind,
            run_type=run_type,
            summary={"status_line": "Plan oluşturuluyor."},
        )
        run_id = int(run["id"])
        self.store.create_agent_step(
            self.settings.office_id,
            run_id=run_id,
            step_index=1,
            role="planner",
            title="Görev planı oluşturuldu",
            status="completed",
            rationale="İstek uygun araçlara ve kontrollü adımlara ayrıldı.",
            input_payload={
                "goal": goal,
                "matter_id": matter_id,
                "preferred_tools": preferred_tools or [],
                "source_refs": source_refs or [],
                "render_mode": render_mode,
                "allow_browser": bool(allow_browser),
            },
            output_payload={"planned_tools": []},
        )
        memory_updates = self._capture_memory(goal, run_id=run_id)
        plan = self._build_plan(
            goal,
            matter_id=matter_id,
            preferred_tools=preferred_tools,
            source_refs=source_refs,
            render_mode=render_mode,
            allow_browser=allow_browser,
        )
        steps = self.store.list_agent_steps(self.settings.office_id, run_id=run_id)
        if steps:
            self.store.update_agent_step(
                self.settings.office_id,
                int(steps[0]["id"]),
                output_payload={"planned_tools": [item.name for item in plan]},
            )
        self.store.update_agent_run(
            self.settings.office_id,
            run_id,
            status="running",
            summary={
                "status_line": "Araçlar çalıştırılıyor.",
                "planned_tools": [item.name for item in plan],
                "memory_events": len(memory_updates),
                "source_refs": source_refs or [],
            },
        )

        collected_outputs: list[dict[str, Any]] = []
        collected_citations: list[dict[str, Any]] = []
        collected_artifacts: list[dict[str, Any]] = []
        approval_requests: list[dict[str, Any]] = []
        executed_tools: list[dict[str, Any]] = []

        for offset, item in enumerate(plan, start=2):
            step = self.store.create_agent_step(
                self.settings.office_id,
                run_id=run_id,
                step_index=offset,
                role=item.role,
                title=item.title,
                status="running",
                rationale=item.rationale,
                input_payload=item.payload,
            )
            step_id = int(step["id"])
            spec = self.tool_registry.get(item.name)
            if spec is None:
                self.store.update_agent_step(
                    self.settings.office_id,
                    step_id,
                    status="failed",
                    error=f"unknown_tool:{item.name}",
                )
                continue
            invocation = self.store.create_tool_invocation(
                self.settings.office_id,
                run_id=run_id,
                step_id=step_id,
                tool_name=spec.name,
                tool_class=spec.tool_class,
                risk_level=spec.risk_level,
                approval_policy=spec.approval_policy,
                status="running",
                input_payload=item.payload,
                approval_required=self._tool_policy_decision(spec).requires_confirmation,
            )
            tool_policy = self._tool_policy_decision(spec)
            if tool_policy.decision == "ask_confirm":
                self.store.update_tool_invocation(
                    self.settings.office_id,
                    int(invocation["id"]),
                    status="pending_approval",
                    approval_required=True,
                )
                self.store.update_agent_step(
                    self.settings.office_id,
                    step_id,
                    status="awaiting_approval",
                    output_payload={},
                )
                approval = self.store.create_run_approval_request(
                    self.settings.office_id,
                    run_id=run_id,
                    step_id=step_id,
                    tool_invocation_id=int(invocation["id"]),
                    approval_kind="tool_execution",
                    title=f"{spec.title} onayı",
                    reason=tool_policy.reason_summary,
                    created_by=created_by,
                    payload={"tool_name": spec.name, "input": item.payload},
                )
                approval_requests.append(approval)
                collected_outputs.append(
                    {
                        "tool": spec.name,
                        "title": spec.title,
                        "status": "pending_approval",
                        "summary": "Araç çalıştırılmadan önce açık onay bekleniyor.",
                        "output": {},
                    }
                )
                continue
            try:
                result = self.tool_registry.execute(spec.name, item.payload)
            except Exception as exc:  # noqa: BLE001
                self.store.update_tool_invocation(
                    self.settings.office_id,
                    int(invocation["id"]),
                    status="failed",
                    error=str(exc),
                )
                self.store.update_agent_step(
                    self.settings.office_id,
                    step_id,
                    status="failed",
                    error=str(exc),
                    output_payload={},
                )
                collected_outputs.append({"tool": spec.name, "status": "failed", "error": str(exc)})
                continue

            updated_invocation = self.store.update_tool_invocation(
                self.settings.office_id,
                int(invocation["id"]),
                status="completed",
                output_payload=result,
                approval_required=tool_policy.requires_confirmation,
            )
            self.store.update_agent_step(
                self.settings.office_id,
                step_id,
                status="completed",
                output_payload=result,
            )
            for artifact in list(result.get("artifacts") or []):
                stored = self.store.create_browser_session_artifact(
                    self.settings.office_id,
                    run_id=run_id,
                    step_id=step_id,
                    artifact_type=str(artifact.get("artifact_type") or artifact.get("type") or "artifact"),
                    path=artifact.get("path"),
                    url=artifact.get("url"),
                    sha256=artifact.get("sha256"),
                    metadata=artifact,
                )
                collected_artifacts.append(stored)
            citations = [item for item in list(result.get("citations") or []) if isinstance(item, dict)]
            collected_citations.extend(citations[:8])
            collected_outputs.append(
                {
                    "tool": spec.name,
                    "title": spec.title,
                    "status": "completed",
                    "summary": result.get("summary"),
                    "output": result,
                }
            )
            if updated_invocation:
                executed_tools.append(updated_invocation)

        status = "awaiting_approval" if approval_requests else "completed"
        review = self._build_review(
            outputs=collected_outputs,
            citations=collected_citations,
            approvals=approval_requests,
            artifacts=collected_artifacts,
        )
        self.store.create_agent_step(
            self.settings.office_id,
            run_id=run_id,
            step_index=len(plan) + 2,
            role="critic",
            title="Çıktı kalitesi değerlendirildi",
            status="completed",
            rationale="Araç çıktıları, dayanak seviyesi ve insan onayı gereksinimi gözden geçirildi.",
            input_payload={
                "completed_tools": review["completed_tool_count"],
                "failed_tools": review["failed_tool_count"],
                "approval_count": review["approval_count"],
                "citation_count": review["citation_count"],
                "artifact_count": review["artifact_count"],
            },
            output_payload=review,
        )
        summary = self._build_summary(
            goal,
            outputs=collected_outputs,
            citations=collected_citations,
            approvals=approval_requests,
            review=review,
        )
        result_payload = {
            "answer": summary["answer"],
            "source_backed": bool(collected_citations),
            "support_level": review["support_level"],
            "confidence": review["confidence"],
            "execution_posture": review["execution_posture"],
            "review_summary": review["review_summary"],
            "review_notes": review["review_notes"],
            "citations": collected_citations[:8],
            "artifacts": collected_artifacts[:12],
            "tool_outputs": collected_outputs,
            "approval_requests": approval_requests,
            "source_refs": source_refs or [],
        }
        updated = self.store.update_agent_run(
            self.settings.office_id,
            run_id,
            status=status,
            summary=summary,
            result=result_payload,
            approval_required=bool(approval_requests),
        )
        self.audit.log(
            "agent_run_created",
            office_id=self.settings.office_id,
            run_id=run_id,
            created_by=created_by,
            run_type=run_type,
            source_kind=source_kind,
            approval_required=bool(approval_requests),
        )
        self.events.log(
            "agent_run_completed" if status == "completed" else "agent_run_awaiting_approval",
            run_id=run_id,
            status=status,
            tool_count=len(executed_tools),
            citation_count=len(collected_citations),
            artifact_count=len(collected_artifacts),
        )
        return self.get_run_view(int(updated["id"]) if updated else run_id)

    def get_run_view(self, run_id: int) -> dict[str, Any]:
        bundle = self.get_run_bundle(run_id)
        if not bundle:
            return {}
        run = dict(bundle.get("run") or {})
        summary_payload = run.get("summary") if isinstance(run.get("summary"), dict) else {}
        result_payload = run.get("result") if isinstance(run.get("result"), dict) else {}
        run["summary_payload"] = summary_payload
        run["result_payload"] = result_payload
        run["summary_status_line"] = str(summary_payload.get("status_line") or "").strip() or None
        run["summary"] = str(summary_payload.get("answer") or summary_payload.get("status_line") or run.get("goal") or "").strip()
        run["final_output"] = str(result_payload.get("answer") or result_payload.get("final_output") or "").strip()
        run["support_level"] = str(result_payload.get("support_level") or "").strip() or None
        run["confidence"] = str(result_payload.get("confidence") or summary_payload.get("confidence") or "").strip() or None
        run["execution_posture"] = str(result_payload.get("execution_posture") or summary_payload.get("execution_posture") or "").strip() or None
        run["review_summary"] = str(result_payload.get("review_summary") or summary_payload.get("review_summary") or "").strip() or None
        run["review_notes"] = [
            str(item).strip()
            for item in list(result_payload.get("review_notes") or summary_payload.get("review_notes") or [])
            if str(item).strip()
        ]
        run["source_backed"] = bool(result_payload.get("source_backed"))
        run["citations"] = list(result_payload.get("citations") or [])
        run["artifacts"] = [self._artifact_view(item) for item in list(bundle.get("artifacts") or result_payload.get("artifacts") or [])]
        run["steps"] = list(bundle.get("steps") or [])
        run["tool_invocations"] = [self._tool_invocation_view(item) for item in list(bundle.get("tool_invocations") or [])]
        run["approval_requests"] = [self._approval_view(item) for item in list(bundle.get("approval_requests") or result_payload.get("approval_requests") or [])]
        run["memory_events"] = list(bundle.get("memory_events") or [])
        run["result_status"] = str(run.get("status") or "").strip() or None
        return run

    def list_run_views(self, *, limit: int = 12, thread_id: int | None = None) -> list[dict[str, Any]]:
        items = self.store.list_agent_runs(self.settings.office_id, limit=limit, thread_id=thread_id)
        return [self.get_run_view(int(item["id"])) for item in items if item.get("id") is not None]

    def get_run_bundle(self, run_id: int) -> dict[str, Any]:
        run = self.store.get_agent_run(self.settings.office_id, run_id)
        if not run:
            return {}
        return {
            "run": run,
            "steps": self.store.list_agent_steps(self.settings.office_id, run_id=run_id),
            "tool_invocations": self.store.list_tool_invocations(self.settings.office_id, run_id=run_id),
            "approval_requests": self.store.list_run_approval_requests(self.settings.office_id, run_id=run_id),
            "artifacts": self.store.list_browser_session_artifacts(self.settings.office_id, run_id=run_id),
            "memory_events": self.store.list_memory_events(self.settings.office_id, run_id=run_id),
        }

    def get_run_events(self, run_id: int) -> list[dict[str, Any]]:
        return self.store.list_agent_run_events(self.settings.office_id, run_id=run_id)

    def cancel_run(self, run_id: int, *, decided_by: str) -> dict[str, Any] | None:
        bundle = self.get_run_bundle(run_id)
        if not bundle:
            return None
        for approval in list(bundle.get("approval_requests") or []):
            if str(approval.get("status") or "") != "pending":
                continue
            self.store.decide_run_approval_request(
                self.settings.office_id,
                int(approval["id"]),
                status="cancelled",
                decided_by=decided_by,
            )
            tool_invocation_id = approval.get("tool_invocation_id")
            if tool_invocation_id is not None:
                self.store.update_tool_invocation(
                    self.settings.office_id,
                    int(tool_invocation_id),
                    status="cancelled",
                    error="cancelled_by_user",
                )
            step_id = approval.get("step_id")
            if step_id is not None:
                self.store.update_agent_step(
                    self.settings.office_id,
                    int(step_id),
                    status="cancelled",
                    output_payload={},
                    error="cancelled_by_user",
                )
        self.audit.log("agent_run_cancelled", office_id=self.settings.office_id, run_id=run_id, actor=decided_by)
        return self.store.update_agent_run(
            self.settings.office_id,
            run_id,
            status="cancelled",
            summary={"status_line": "Çalıştırma kullanıcı tarafından durduruldu."},
            result={"cancelled_by": decided_by, "approval_requests": self.store.list_run_approval_requests(self.settings.office_id, run_id=run_id)},
            approval_required=False,
        )

    def approve_run(self, run_id: int, *, decided_by: str) -> dict[str, Any] | None:
        bundle = self.get_run_bundle(run_id)
        if not bundle:
            return None
        approvals = list(bundle.get("approval_requests") or [])
        tool_invocations = {
            int(item["id"]): item
            for item in list(bundle.get("tool_invocations") or [])
            if item.get("id") is not None
        }
        steps = {
            int(item["id"]): item
            for item in list(bundle.get("steps") or [])
            if item.get("id") is not None
        }
        executed_after_approval = 0
        for approval in approvals:
            if str(approval.get("status") or "") == "pending":
                self.store.decide_run_approval_request(
                    self.settings.office_id,
                    int(approval["id"]),
                    status="approved",
                    decided_by=decided_by,
                )
                tool_invocation_id = approval.get("tool_invocation_id")
                if tool_invocation_id is None:
                    continue
                invocation = tool_invocations.get(int(tool_invocation_id))
                if not invocation:
                    continue
                step = steps.get(int(invocation.get("step_id") or 0)) if invocation.get("step_id") is not None else None
                self._execute_existing_invocation(
                    run_id=run_id,
                    invocation=invocation,
                    step=step,
                )
                executed_after_approval += 1
        outputs, citations, artifacts, pending_approvals, refreshed_bundle = self._collect_execution_state(run_id)
        review = self._build_review(
            outputs=outputs,
            citations=citations,
            approvals=pending_approvals,
            artifacts=artifacts,
        )
        self.store.create_agent_step(
            self.settings.office_id,
            run_id=run_id,
            step_index=len(list(refreshed_bundle.get("steps") or [])) + 1,
            role="critic",
            title="Onay sonrası çıktı değerlendirildi",
            status="completed",
            rationale="Onaylanan araç adımlarının sonucu ve dayanak seviyesi yeniden gözden geçirildi.",
            input_payload={
                "executed_after_approval": executed_after_approval,
                "approval_count": len(approvals),
                "citation_count": len(citations),
            },
            output_payload=review,
        )
        run = dict(refreshed_bundle.get("run") or {})
        previous_result = run.get("result") if isinstance(run.get("result"), dict) else {}
        summary = self._build_summary(
            str(run.get("goal") or ""),
            outputs=outputs,
            citations=citations,
            approvals=pending_approvals,
            review=review,
        )
        updated = self.store.update_agent_run(
            self.settings.office_id,
            run_id,
            status="completed" if not pending_approvals else "awaiting_approval",
            summary=summary,
            result={
                **previous_result,
                "answer": summary["answer"],
                "source_backed": bool(citations),
                "support_level": review["support_level"],
                "confidence": review["confidence"],
                "execution_posture": review["execution_posture"],
                "review_summary": review["review_summary"],
                "review_notes": review["review_notes"],
                "citations": citations[:8],
                "artifacts": artifacts[:12],
                "tool_outputs": outputs,
                "approval_requests": self.store.list_run_approval_requests(self.settings.office_id, run_id=run_id),
                "source_refs": list(previous_result.get("source_refs") or []),
            },
            approval_required=bool(pending_approvals),
        )
        self.audit.log("agent_run_approved", office_id=self.settings.office_id, run_id=run_id, actor=decided_by)
        self.events.log(
            "agent_run_approved",
            run_id=run_id,
            executed_after_approval=executed_after_approval,
            pending_approval_count=len(pending_approvals),
            citation_count=len(citations),
        )
        return self.get_run_view(int(updated["id"]) if updated else run_id)

    def _execute_existing_invocation(
        self,
        *,
        run_id: int,
        invocation: dict[str, Any],
        step: dict[str, Any] | None,
    ) -> None:
        invocation_id = int(invocation["id"])
        tool_name = str(invocation.get("tool_name") or "").strip()
        spec = self.tool_registry.get(tool_name)
        if spec is None:
            self.store.update_tool_invocation(
                self.settings.office_id,
                invocation_id,
                status="failed",
                error=f"unknown_tool:{tool_name}",
            )
            if step and step.get("id") is not None:
                self.store.update_agent_step(
                    self.settings.office_id,
                    int(step["id"]),
                    status="failed",
                    output_payload={},
                    error=f"unknown_tool:{tool_name}",
                )
            return

        payload = dict(invocation.get("input") or {})
        tool_policy = self._tool_policy_decision(spec)
        self.store.update_tool_invocation(
            self.settings.office_id,
            invocation_id,
            status="running",
            approval_required=tool_policy.requires_confirmation,
        )
        if step and step.get("id") is not None:
            self.store.update_agent_step(
                self.settings.office_id,
                int(step["id"]),
                status="running",
                output_payload=dict(step.get("output") or {}),
            )
        try:
            result = self.tool_registry.execute(spec.name, payload)
        except Exception as exc:  # noqa: BLE001
            self.store.update_tool_invocation(
                self.settings.office_id,
                invocation_id,
                status="failed",
                error=str(exc),
            )
            if step and step.get("id") is not None:
                self.store.update_agent_step(
                    self.settings.office_id,
                    int(step["id"]),
                    status="failed",
                    output_payload={},
                    error=str(exc),
                )
            return

        self.store.update_tool_invocation(
            self.settings.office_id,
            invocation_id,
            status="completed",
            output_payload=result,
            approval_required=tool_policy.requires_confirmation,
        )
        if step and step.get("id") is not None:
            self.store.update_agent_step(
                self.settings.office_id,
                int(step["id"]),
                status="completed",
                output_payload=result,
            )
        for artifact in list(result.get("artifacts") or []):
            self.store.create_browser_session_artifact(
                self.settings.office_id,
                run_id=run_id,
                step_id=int(step["id"]) if step and step.get("id") is not None else None,
                artifact_type=str(artifact.get("artifact_type") or artifact.get("type") or "artifact"),
                path=artifact.get("path"),
                url=artifact.get("url"),
                sha256=artifact.get("sha256"),
                metadata=artifact,
            )

    def _collect_execution_state(
        self,
        run_id: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        bundle = self.get_run_bundle(run_id)
        outputs: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []
        for invocation in list(bundle.get("tool_invocations") or []):
            tool_name = str(invocation.get("tool_name") or "").strip()
            spec = self.tool_registry.get(tool_name)
            title = spec.title if spec else tool_name
            status = str(invocation.get("status") or "").strip() or "pending"
            output = dict(invocation.get("output") or {})
            summary = ""
            if status == "completed":
                summary = str(output.get("summary") or "").strip()
                citations.extend([item for item in list(output.get("citations") or []) if isinstance(item, dict)][:8])
            elif status == "pending_approval":
                summary = "Araç çalıştırılmadan önce açık onay bekleniyor."
            elif status == "failed":
                summary = str(invocation.get("error") or "Araç adımı başarısız oldu.").strip()
            outputs.append(
                {
                    "tool": tool_name,
                    "title": title,
                    "status": status,
                    "summary": summary,
                    "output": output,
                }
            )
        pending_approvals = [
            item
            for item in list(bundle.get("approval_requests") or [])
            if str(item.get("status") or "").strip() == "pending"
        ]
        artifacts = list(bundle.get("artifacts") or [])
        return outputs, citations, artifacts, pending_approvals, bundle

    def _capture_memory(self, goal: str, *, run_id: int) -> list[dict[str, Any]]:
        if not self.memory_service:
            return []
        updates = self.memory_service.capture_chat_signal(goal)
        for item in updates:
            self.store.add_memory_event(
                self.settings.office_id,
                run_id=run_id,
                memory_scope=str(item.get("kind") or "profile"),
                event_type=str(item.get("status") or "stored"),
                summary=str(item.get("summary") or "Bellek güncellendi."),
                payload=item,
                entity_key="assistant_profile" if item.get("kind") == "assistant_persona_signal" else "user_profile",
            )
        return updates

    def _build_plan(
        self,
        goal: str,
        *,
        matter_id: int | None,
        preferred_tools: list[str] | None,
        source_refs: list[dict[str, Any]] | None,
        render_mode: str,
        allow_browser: bool,
    ) -> list[PlannedTool]:
        query = str(goal or "").strip()
        normalized = _normalize_text(query)
        requested_render_mode = self._resolve_render_mode(render_mode=render_mode, allow_browser=allow_browser)
        inferred_url = self._extract_source_url(source_refs)
        inspect_url = extract_query_url(query) or inferred_url
        youtube_url = extract_youtube_url(query) or (inspect_url if extract_youtube_url(inspect_url or "") else None)
        if preferred_tools:
            return [
                self._planned_tool_from_name(
                    name,
                    query=query,
                    matter_id=matter_id,
                    source_refs=source_refs,
                    render_mode=requested_render_mode,
                )
                for name in preferred_tools
            ]
        semantic_planned = self._semantic_tool_plan(
            goal=query,
            matter_id=matter_id,
            source_refs=source_refs,
            render_mode=requested_render_mode,
            allow_browser=allow_browser,
        )
        if semantic_planned:
            return semantic_planned
        planned: list[PlannedTool] = []
        if youtube_url and is_video_summary_query(query):
            planned.append(
                PlannedTool(
                    name="video.analyze",
                    title="YouTube videosunu özetle",
                    role="researcher",
                    payload={"url": youtube_url, "max_segments": 24},
                    rationale="Belirli YouTube videosu için özet veya transcript çözümleme istendi.",
                )
            )
        elif is_youtube_search_query(query):
            planned.append(
                PlannedTool(
                    name="youtube.search",
                    title="YouTube'da video ara",
                    role="researcher",
                    payload={"query": query, "limit": 5},
                    rationale="İstek YouTube üzerinde video araması gerektiriyor.",
                )
            )
        elif inspect_url and is_website_crawl_query(query):
            planned.append(
                PlannedTool(
                    name="web.crawl",
                    title="Siteyi tara",
                    role="researcher",
                    payload={"url": inspect_url, "query": query, "max_pages": 4, "render_mode": requested_render_mode},
                    rationale="İstek aynı alan adı içinde çok sayfalı site taraması gerektiriyor.",
                )
            )
        elif inspect_url and (is_website_review_query(query) or "site" in normalized or "sayfa" in normalized):
            planned.append(
                PlannedTool(
                    name="web.inspect",
                    title="Web sayfasını incele",
                    role="researcher",
                    payload={"url": inspect_url, "render_mode": requested_render_mode, "include_screenshot": allow_browser},
                    rationale="URL verildiği için doğrudan sayfa inceleme planlandı.",
                )
            )
        elif is_travel_query(query):
            planned.append(
                PlannedTool(
                    name="travel.search",
                    title="Seyahat seçeneklerini araştır",
                    role="researcher",
                    payload={"query": query, "limit": 5},
                    rationale="İstek seyahat ve rota/bilet araştırması gerektiriyor.",
                )
            )
        elif is_weather_query(query):
            planned.append(
                PlannedTool(
                    name="weather.search",
                    title="Hava durumunu araştır",
                    role="researcher",
                    payload={"query": query, "limit": 5},
                    rationale="İstek hava durumu ve dış ortam bilgisi gerektiriyor.",
                )
            )
        elif is_place_search_query(query):
            planned.append(
                PlannedTool(
                    name="places.search",
                    title="Mekân ve rota seçeneklerini araştır",
                    role="researcher",
                    payload={"query": query, "limit": 5},
                    rationale="İstek yakın çevre, mekân veya yol tarifi bağlamı gerektiriyor.",
                )
            )
        elif is_web_search_query(query):
            planned.append(
                PlannedTool(
                    name="web.search",
                    title="Güncel web araştırması",
                    role="researcher",
                    payload={"query": query, "limit": 5},
                    rationale="İstek güncel web araştırması gerektiriyor.",
                )
            )
        if _is_personal_dates_query(normalized):
            planned.append(
                PlannedTool(
                    name="assistant.profile_dates",
                    title="Yaklaşan kişisel tarihleri oku",
                    role="executor",
                    payload={"window_days": 30, "limit": 12},
                    rationale="İstek kişisel takvim ve önemli tarih bağlamını gerektiriyor.",
                )
            )
        if matter_id:
            planned.append(
                PlannedTool(
                    name="matter.search",
                    title="Dosya dayanaklarını tara",
                    role="researcher",
                    payload={"matter_id": matter_id, "query": query, "limit": 5},
                    rationale="Matter bağlamı verildiği için dosya içi dayanak taranıyor.",
                )
            )
        elif any(token in normalized for token in ("belge", "dosya", "workspace", "calisma alani", "çalışma alanı")):
            planned.append(
                PlannedTool(
                    name="workspace.search",
                    title="Çalışma alanını tara",
                    role="researcher",
                    payload={"query": query, "limit": 5},
                    rationale="İstek çalışma alanı belgelerini de incelemeyi gerektiriyor.",
                )
            )
        if is_social_monitoring_query(query):
            planned.append(
                PlannedTool(
                    name="social.monitor",
                    title="Sosyal sinyalleri özetle",
                    role="researcher",
                    payload={"limit": 10},
                    rationale="İstek sosyal medya ve dış risk sinyallerini kapsıyor.",
                )
            )
        if any(token in normalized for token in ("bugun", "bugün", "ajanda", "takvim", "onay", "iletisim", "iletişim")):
            planned.extend(
                [
                    PlannedTool("assistant.home", "Günlük özeti oku", "executor", {}, "Asistan özeti bağlamı güçlendirir."),
                    PlannedTool("assistant.inbox", "İletişim sinyallerini oku", "executor", {}, "Inbox durumu istekle ilişkili olabilir."),
                    PlannedTool("assistant.calendar", "Takvimi oku", "executor", {"window_days": 14}, "Takvim görünümü istekle ilişkili olabilir."),
                ]
            )
        if not planned:
            planned.extend(
                [
                    PlannedTool("assistant.home", "Günlük özeti oku", "executor", {}, "Varsayılan çalışma bağlamı çıkarılıyor."),
                    PlannedTool("web.search", "Web araştırması", "researcher", {"query": query, "limit": 5}, "Genel araştırma isteği için güvenli başlangıç."),
                ]
            )
        seen: set[str] = set()
        deduped: list[PlannedTool] = []
        for item in planned:
            key = f"{item.name}:{item.payload.get('url') or item.payload.get('query') or ''}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _planned_tool_from_name(
        self,
        name: str,
        *,
        query: str,
        matter_id: int | None,
        source_refs: list[dict[str, Any]] | None,
        render_mode: str,
    ) -> PlannedTool:
        if name == "web.inspect":
            target_url = extract_query_url(query) or self._extract_source_url(source_refs)
            if not target_url:
                return PlannedTool(
                    "web.search",
                    "Web araştırması",
                    "researcher",
                    {"query": query, "limit": 5},
                    "Web inceleme aracı için URL bulunamadı; güvenli fallback olarak web araştırması seçildi.",
                )
            return PlannedTool(
                name,
                "Web sayfasını incele",
                "researcher",
                {
                    "url": target_url,
                    "render_mode": render_mode,
                    "include_screenshot": render_mode == "browser",
                },
                "Tercih edilen araç kullanıcı tarafından istendi.",
            )
        if name == "web.crawl":
            target_url = extract_query_url(query) or self._extract_source_url(source_refs)
            if not target_url:
                return PlannedTool(
                    "web.search",
                    "Web araştırması",
                    "researcher",
                    {"query": query, "limit": 5},
                    "Site taraması için URL bulunamadı; güvenli fallback olarak web araştırması seçildi.",
                )
            return PlannedTool(
                name,
                "Siteyi tara",
                "researcher",
                {"url": target_url, "query": query, "max_pages": 4, "render_mode": render_mode},
                "Tercih edilen araç kullanıcı tarafından istendi.",
            )
        if name == "video.analyze":
            target_url = extract_youtube_url(query) or self._extract_source_url(source_refs)
            if not target_url:
                return PlannedTool(
                    "youtube.search",
                    "YouTube'da video ara",
                    "researcher",
                    {"query": query, "limit": 5},
                    "Video çözümleme için YouTube linki bulunamadı; önce arama yapılıyor.",
                )
            return PlannedTool(
                name,
                "YouTube videosunu özetle",
                "researcher",
                {"url": target_url, "max_segments": 24},
                "Tercih edilen araç kullanıcı tarafından istendi.",
            )
        if name == "youtube.search":
            return PlannedTool(name, "YouTube'da video ara", "researcher", {"query": query, "limit": 5}, "Tercih edilen araç kullanıcı tarafından istendi.")
        if name == "matter.search":
            return PlannedTool(name, "Dosya dayanaklarını tara", "researcher", {"matter_id": matter_id, "query": query, "limit": 5}, "Tercih edilen araç kullanıcı tarafından istendi.")
        if name == "workspace.search":
            return PlannedTool(name, "Çalışma alanını tara", "researcher", {"query": query, "limit": 5}, "Tercih edilen araç kullanıcı tarafından istendi.")
        if name == "assistant.calendar":
            return PlannedTool(name, "Takvimi oku", "executor", {"window_days": 14}, "Tercih edilen araç kullanıcı tarafından istendi.")
        if name == "assistant.profile_dates":
            return PlannedTool(name, "Yaklaşan kişisel tarihleri oku", "executor", {"window_days": 30, "limit": 12}, "Tercih edilen araç kullanıcı tarafından istendi.")
        if name == "assistant.inbox":
            return PlannedTool(name, "İletişim sinyallerini oku", "executor", {}, "Tercih edilen araç kullanıcı tarafından istendi.")
        if name == "travel.search":
            return PlannedTool(name, "Seyahat seçeneklerini araştır", "researcher", {"query": query, "limit": 5}, "Tercih edilen araç kullanıcı tarafından istendi.")
        if name == "weather.search":
            return PlannedTool(name, "Hava durumunu araştır", "researcher", {"query": query, "limit": 5}, "Tercih edilen araç kullanıcı tarafından istendi.")
        if name == "places.search":
            return PlannedTool(name, "Mekân ve rota seçeneklerini araştır", "researcher", {"query": query, "limit": 5}, "Tercih edilen araç kullanıcı tarafından istendi.")
        if name == "social.monitor":
            return PlannedTool(name, "Sosyal sinyalleri özetle", "researcher", {"limit": 10}, "Tercih edilen araç kullanıcı tarafından istendi.")
        return PlannedTool("web.search", "Web araştırması", "researcher", {"query": query, "limit": 5}, "Tercih edilen araç veya güvenli varsayılan.")

    def _build_summary(
        self,
        goal: str,
        *,
        outputs: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        approvals: list[dict[str, Any]],
        review: dict[str, Any],
    ) -> dict[str, Any]:
        lines = [f"Görev işlendi: {_clean_text(goal, limit=180)}."]
        completed = [item for item in outputs if item.get("status") == "completed"]
        failed = [item for item in outputs if item.get("status") == "failed"]
        if completed:
            tool_labels = ", ".join(str(item.get("title") or item.get("tool") or "") for item in completed[:5] if str(item.get("title") or item.get("tool") or ""))
            if tool_labels:
                lines.append(f"Kullanılan araçlar: {tool_labels}.")
        if citations:
            lines.append(f"{len(citations)} kaynaklı dayanak bulundu.")
        else:
            lines.append("Güçlü kaynak dayanağı bulunamadı; sonuç kısmen yorumsal olabilir.")
        if failed:
            lines.append(f"{len(failed)} araç adımı tamamlanamadı.")
        if approvals:
            lines.append(f"{len(approvals)} adım açık onay bekliyor.")
        review_summary = str(review.get("review_summary") or "").strip()
        if review_summary:
            lines.append(review_summary)
        answer = " ".join(lines).strip()
        return {
            "status_line": "Koşu tamamlandı." if not approvals else "Koşu onay bekliyor.",
            "answer": answer,
            "citation_count": len(citations),
            "approval_count": len(approvals),
            "confidence": review.get("confidence"),
            "execution_posture": review.get("execution_posture"),
            "review_summary": review_summary,
            "review_notes": list(review.get("review_notes") or []),
        }

    def _build_review(
        self,
        *,
        outputs: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        approvals: list[dict[str, Any]],
        artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        completed = [item for item in outputs if item.get("status") == "completed"]
        failed = [item for item in outputs if item.get("status") == "failed"]
        citation_count = len(citations)
        approval_count = len(approvals)
        artifact_count = len(artifacts)

        if citation_count >= 2:
            support_level = "high"
        elif citation_count == 1:
            support_level = "medium"
        else:
            support_level = "low"

        if approval_count:
            confidence = "low"
        elif failed and support_level == "high":
            confidence = "medium"
        elif failed:
            confidence = "low"
        elif support_level == "high":
            confidence = "high"
        elif support_level == "medium":
            confidence = "medium"
        elif completed:
            confidence = "low"
        else:
            confidence = "low"

        execution_posture = "ask" if approval_count or confidence == "low" else "suggest" if confidence == "medium" else "auto"

        notes: list[str] = []
        if citation_count >= 2:
            notes.append("Yanıt birden fazla dayanakla destekleniyor.")
        elif citation_count == 1:
            notes.append("Yanıt tek bir dayanakla destekleniyor; teyit önerilir.")
        else:
            notes.append("Belge veya web dayanağı zayıf; sonucu doğrulamadan işlem yapılmamalı.")
        if failed:
            notes.append("Bazı araç adımları tamamlanamadı.")
        if approval_count:
            notes.append("Yan etki oluşturabilecek adımlar için açık kullanıcı onayı gerekiyor.")
        elif execution_posture == "auto":
            notes.append("Mevcut çıktı düşük riskli ilerleme için yeterli görünüyor.")
        else:
            notes.append("Çıktı taslak veya öneri olarak sunulmalı.")
        if artifact_count:
            notes.append(f"{artifact_count} çıktı kaydı üretildi.")

        review_summary = {
            "ask": "İnsan onayı olmadan ilerlemek uygun değil.",
            "suggest": "Çıktı öneri olarak güçlü, ancak son karar kullanıcıda kalmalı.",
            "auto": "Çıktı güvenli ve yeterince destekli; düşük riskli ilerleme uygun.",
        }[execution_posture]

        return {
            "support_level": support_level,
            "confidence": confidence,
            "execution_posture": execution_posture,
            "review_summary": review_summary,
            "review_notes": notes,
            "completed_tool_count": len(completed),
            "failed_tool_count": len(failed),
            "approval_count": approval_count,
            "citation_count": citation_count,
            "artifact_count": artifact_count,
        }

    @staticmethod
    def _artifact_view(item: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(item.get("metadata") or {})
        kind = str(item.get("artifact_type") or item.get("kind") or metadata.get("artifact_type") or "artifact").strip()
        label = str(metadata.get("label") or metadata.get("title") or kind.replace("_", " ").title()).strip()
        text_excerpt = str(metadata.get("text_excerpt") or metadata.get("summary") or item.get("url") or item.get("path") or "").strip()
        return {
            **item,
            "kind": kind,
            "label": label,
            "text_excerpt": text_excerpt,
        }

    @staticmethod
    def _tool_invocation_view(item: dict[str, Any]) -> dict[str, Any]:
        return {
            **item,
            "tool": item.get("tool_name"),
            "metadata": item.get("output") if isinstance(item.get("output"), dict) else {},
        }

    @staticmethod
    def _approval_view(item: dict[str, Any]) -> dict[str, Any]:
        payload = dict(item.get("payload") or {})
        return {
            **item,
            "tool": payload.get("tool_name") or item.get("tool"),
            "approval_required": True,
        }

    @staticmethod
    def _extract_source_url(source_refs: list[dict[str, Any]] | None) -> str:
        for item in source_refs or []:
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("url") or item.get("href") or item.get("link") or "").strip()
            if candidate:
                return candidate
        return ""

    @staticmethod
    def _resolve_render_mode(*, render_mode: str, allow_browser: bool) -> str:
        normalized = str(render_mode or "auto").strip().lower()
        if not allow_browser:
            return "cheap"
        if normalized in {"cheap", "browser"}:
            return normalized
        return "auto"


def _normalize_text(value: str) -> str:
    return (
        str(value or "")
        .lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )
