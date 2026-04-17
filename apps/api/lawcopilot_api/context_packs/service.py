from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..preference_rules import resolve_source_preference_context


def _compact_text(value: Any, *, limit: int = 220) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _freshness_bucket(value: Any, *, stable: bool = False) -> str:
    if stable:
        return "stable"
    parsed = _parse_dt(value)
    if parsed is None:
        return "unknown"
    age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    if age.total_seconds() < 0:
        return "hot"
    if age.days <= 3:
        return "hot"
    if age.days <= 30:
        return "warm"
    return "stale"


class AssistantContextPackService:
    def build_profile_preference_pack(
        self,
        *,
        query: str,
        profile: dict[str, Any] | None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        context = resolve_source_preference_context(query, profile=profile, limit=limit)
        entries: list[dict[str, Any]] = []
        for item in list(context.get("matched_rules") or [])[: max(0, limit)]:
            summary = str(item.get("note") or "").strip()
            title = str(item.get("label") or "Kaynak tercihi").strip() or "Kaynak tercihi"
            providers = list(item.get("preferred_providers") or [])
            domains = list(item.get("preferred_domains") or [])
            links = list(item.get("preferred_links") or [])
            compact_parts: list[str] = []
            if providers:
                compact_parts.append(f"sağlayıcı: {', '.join(providers[:3])}")
            if domains:
                compact_parts.append(f"alan adı: {', '.join(domains[:3])}")
            if links:
                compact_parts.append(f"bağlantı: {', '.join(links[:2])}")
            if summary:
                compact_parts.append(summary)
            compact_summary = " | ".join(part for part in compact_parts if part)
            entries.append(
                {
                    "id": f"profile-rule:{item.get('id')}",
                    "family": "profile_preferences",
                    "item_kind": "source_preference_rule",
                    "source_type": "user_profile_rule",
                    "source_ref": str(item.get("id") or ""),
                    "subject_key": "user",
                    "predicate": str(item.get("task_kind") or ""),
                    "title": title,
                    "summary": compact_summary,
                    "scope": "personal",
                    "claim_status": "settings",
                    "basis": "user_explicit",
                    "freshness": "stable",
                    "assistant_visibility": "visible",
                    "why_visible": "Kullanıcı bu iş türü için hangi kaynakların tercih edilmesi gerektiğini açıkça belirtti.",
                    "why_blocked": "",
                    "retrieval_eligibility": "eligible",
                    "sensitive": False,
                    "memory_tier": "stable",
                    "profile_kind": "source_preference",
                    "support_strength": "explicit",
                    "priority": 0.95 if str(item.get("policy_mode") or "") == "restrict" else 0.85,
                    "prompt_line": (
                        f"- [kaynak tercihi] {title}: {compact_summary}"
                        if compact_summary
                        else f"- [kaynak tercihi] {title}"
                    ),
                    "metadata": {
                        "policy_mode": item.get("policy_mode"),
                        "preferred_domains": domains,
                        "preferred_links": links,
                        "preferred_providers": providers,
                    },
                }
            )
        return entries

    def build_personal_model_pack(
        self,
        *,
        context: dict[str, Any] | None,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        payload = dict(context or {})
        entries: list[dict[str, Any]] = []
        for item in list(payload.get("facts") or [])[: max(0, limit)]:
            fact_key = str(item.get("fact_key") or "").strip()
            title = str(item.get("title") or fact_key or "Kişisel bilgi").strip()
            value_text = str(item.get("value_text") or "").strip()
            claim_status = str(item.get("epistemic_status") or "unknown").strip() or "unknown"
            retrieval_eligibility = str(item.get("epistemic_retrieval_eligibility") or "eligible").strip() or "eligible"
            support_contaminated = bool(item.get("epistemic_support_contaminated"))
            support_strength = str(item.get("epistemic_support_strength") or "").strip()
            sensitive = bool(item.get("sensitive"))
            blocked_reason = ""
            visible = True
            if sensitive:
                visible = False
                blocked_reason = "Hassas olduğu için yanıtlara otomatik girmez."
            elif retrieval_eligibility == "blocked":
                visible = False
                blocked_reason = "Retrieval politikası bu bilgiyi şu an engelliyor."
            elif support_contaminated:
                visible = False
                blocked_reason = "Dayanak zinciri kirli göründüğü için geri planda tutuluyor."
            prompt_basis = str(item.get("epistemic_basis_label") or "kullanıcı bilgisi").strip()
            entries.append(
                {
                    "id": f"pm:{item.get('id')}",
                    "family": "personal_model",
                    "item_kind": "personal_fact",
                    "source_type": "personal_model_fact",
                    "source_ref": str(item.get("id") or ""),
                    "subject_key": "user",
                    "predicate": fact_key,
                    "title": title,
                    "summary": value_text,
                    "scope": str(item.get("scope") or "global"),
                    "claim_status": claim_status,
                    "basis": str(item.get("epistemic_basis") or ""),
                    "freshness": _freshness_bucket(item.get("updated_at"), stable=str(item.get("confidence_type") or "") == "explicit"),
                    "assistant_visibility": "visible" if visible else "blocked",
                    "why_visible": "Kullanıcı tarafından verilmiş ve kişisel bağlam için ilgili bir bilgi."
                    if visible
                    else "",
                    "why_blocked": blocked_reason,
                    "retrieval_eligibility": retrieval_eligibility,
                    "sensitive": sensitive,
                    "memory_tier": "warm" if str(item.get("confidence_type") or "") == "explicit" else "hot",
                    "profile_kind": "user_profile",
                    "support_strength": support_strength or None,
                    "priority": round(float(item.get("score") or item.get("confidence") or 0.0), 3),
                    "prompt_line": f"- [{prompt_basis}] {title}: {value_text}" if value_text else f"- [{prompt_basis}] {title}",
                    "metadata": {
                        "category": item.get("category"),
                        "confidence_type": item.get("confidence_type"),
                        "epistemic_claim_id": item.get("epistemic_claim_id"),
                    },
                }
            )
        return entries

    def build_knowledge_pack(
        self,
        *,
        context: dict[str, Any] | None,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        payload = dict(context or {})
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in list(payload.get("resolved_claims") or [])[: max(0, limit)]:
            claim_id = str(item.get("claim_id") or "").strip()
            marker = claim_id or f"{item.get('subject_key')}::{item.get('predicate')}::{item.get('value_text')}"
            if marker in seen:
                continue
            seen.add(marker)
            claim_status = str(item.get("status") or "unknown").strip() or "unknown"
            support_strength = str(item.get("support_strength") or "").strip()
            support_contaminated = bool(item.get("support_contaminated"))
            retrieval_eligibility = str(item.get("retrieval_eligibility") or "eligible").strip() or "eligible"
            visible = retrieval_eligibility != "blocked" and not support_contaminated
            summary_line = str(item.get("summary_line") or "").strip()
            entries.append(
                {
                    "id": f"kb-claim:{marker}",
                    "family": "knowledge_base",
                    "item_kind": "resolved_claim",
                    "source_type": "epistemic_claim",
                    "source_ref": claim_id,
                    "subject_key": str(item.get("subject_key") or ""),
                    "predicate": str(item.get("predicate") or ""),
                    "title": str(item.get("title") or item.get("predicate") or "KB claim"),
                    "summary": str(item.get("value_text") or item.get("summary") or "").strip(),
                    "scope": str(item.get("scope") or "global"),
                    "claim_status": claim_status,
                    "basis": str(item.get("basis") or ""),
                    "freshness": _freshness_bucket(item.get("updated_at")),
                    "assistant_visibility": "visible" if visible else "blocked",
                    "why_visible": "Çözülmüş knowledge claim'i mevcut sorguya dayanak olarak seçildi." if visible else "",
                    "why_blocked": "Claim blocked veya contaminated olduğu için arka planda tutuluyor." if not visible else "",
                    "retrieval_eligibility": retrieval_eligibility,
                    "sensitive": bool(item.get("sensitive")),
                    "memory_tier": "warm",
                    "profile_kind": "knowledge_claim",
                    "support_strength": support_strength or None,
                    "priority": round(float(item.get("score") or 0.0), 3),
                    "prompt_line": summary_line or f"- [kb] {str(item.get('title') or item.get('predicate') or 'Kayıt')}: {str(item.get('value_text') or '').strip()}",
                    "metadata": {
                        "page_key": item.get("page_key"),
                        "support_contaminated": support_contaminated,
                    },
                }
            )
        if entries:
            return entries
        for item in list(payload.get("supporting_records") or [])[: max(0, limit)]:
            title = str(item.get("title") or "").strip()
            summary = str(item.get("summary") or "").strip()
            page_key = str(item.get("page_key") or "knowledge").strip() or "knowledge"
            marker = f"{page_key}:{item.get('record_id')}"
            if marker in seen:
                continue
            seen.add(marker)
            entries.append(
                {
                    "id": f"kb-record:{marker}",
                    "family": "knowledge_base",
                    "item_kind": "supporting_record",
                    "source_type": "knowledge_record",
                    "source_ref": str(item.get("record_id") or ""),
                    "subject_key": "",
                    "predicate": "",
                    "title": title or "KB kaydı",
                    "summary": summary,
                    "scope": str(item.get("scope") or "global"),
                    "claim_status": "narrative",
                    "basis": "",
                    "freshness": _freshness_bucket(item.get("updated_at")),
                    "assistant_visibility": "visible",
                    "why_visible": "Bu kayıt knowledge base içinde destekleyici anlatı olarak seçildi.",
                    "why_blocked": "",
                    "retrieval_eligibility": "narrative_only",
                    "sensitive": False,
                    "memory_tier": "warm",
                    "profile_kind": "knowledge_record",
                    "support_strength": None,
                    "priority": round(float(item.get("score") or 0.0), 3),
                    "prompt_line": f"- [{page_key}] {title}: {summary}" if title and summary else f"- [{page_key}] {title or summary or 'KB kaydı'}",
                    "metadata": {"page_key": page_key},
                }
            )
        return entries

    def build_operational_pack(
        self,
        *,
        inbox: list[dict[str, Any]] | None = None,
        calendar: list[dict[str, Any]] | None = None,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for item in list(inbox or [])[: max(0, limit)]:
            title = str(item.get("title") or item.get("contact_label") or "İletişim kaydı").strip()
            details = _compact_text(item.get("details") or "", limit=140)
            memory_state = str(item.get("memory_state") or "operational_only").strip() or "operational_only"
            visible_reason = "Güncel iletişim ve operasyon takibi için etkin durumda."
            if memory_state == "candidate_memory":
                visible_reason = "Güncel operasyon bağlamında görünür; ayrıca hafıza adayı olarak işaretli."
            elif memory_state == "approved_memory":
                visible_reason = "Güncel operasyon bağlamında görünür; ayrıca kalıcı hafıza için onaylı."
            entries.append(
                {
                    "id": f"op:{item.get('id')}",
                    "family": "operational",
                    "item_kind": str(item.get("kind") or "inbox_item"),
                    "source_type": str(item.get("source_type") or "inbox_item"),
                    "source_ref": str(item.get("source_ref") or item.get("id") or ""),
                    "subject_key": "",
                    "predicate": "",
                    "title": title,
                    "summary": details,
                    "scope": "operational",
                    "claim_status": "operational",
                    "basis": "connector_observed",
                    "freshness": _freshness_bucket(item.get("due_at")),
                    "assistant_visibility": "visible",
                    "why_visible": visible_reason,
                    "why_blocked": "",
                    "retrieval_eligibility": "operational",
                    "sensitive": False,
                    "memory_tier": "hot",
                    "profile_kind": "contact_profile" if item.get("contact_label") else "operational",
                    "support_strength": "grounded",
                    "priority": 1.0 if str(item.get("priority") or "") == "high" else 0.6,
                    "prompt_line": f"- [operasyon] {title}: {details}" if details else f"- [operasyon] {title}",
                    "metadata": {
                        "provider": item.get("provider"),
                        "contact_label": item.get("contact_label"),
                        "memory_state": memory_state,
                    },
                }
            )
        remaining = max(0, limit - len(entries))
        for item in list(calendar or [])[:remaining]:
            title = str(item.get("title") or "Takvim kaydı").strip()
            details = _compact_text(item.get("details") or item.get("location") or "", limit=120)
            entries.append(
                {
                    "id": f"op:{item.get('id')}",
                    "family": "operational",
                    "item_kind": str(item.get("kind") or "calendar_event"),
                    "source_type": str(item.get("source_type") or "calendar_event"),
                    "source_ref": str(item.get("source_ref") or item.get("id") or ""),
                    "subject_key": "",
                    "predicate": "",
                    "title": title,
                    "summary": details,
                    "scope": "operational",
                    "claim_status": "operational",
                    "basis": "connector_observed",
                    "freshness": _freshness_bucket(item.get("starts_at")),
                    "assistant_visibility": "visible",
                    "why_visible": "Yakın zamanlı takvim veya görev bağlamı olduğu için eklendi.",
                    "why_blocked": "",
                    "retrieval_eligibility": "operational",
                    "sensitive": False,
                    "memory_tier": "hot",
                    "profile_kind": "operational",
                    "support_strength": "grounded",
                    "priority": 0.8 if bool(item.get("needs_preparation")) else 0.5,
                    "prompt_line": f"- [takvim] {title}: {details}" if details else f"- [takvim] {title}",
                    "metadata": {
                        "starts_at": item.get("starts_at"),
                        "provider": item.get("provider"),
                    },
                }
            )
        return entries

    def build_combined_pack(
        self,
        *,
        query: str,
        profile: dict[str, Any] | None = None,
        personal_model_context: dict[str, Any] | None = None,
        knowledge_context: dict[str, Any] | None = None,
        inbox: list[dict[str, Any]] | None = None,
        calendar: list[dict[str, Any]] | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        entries = (
            self.build_profile_preference_pack(query=query, profile=profile, limit=max(1, limit // 4))
            + self.build_personal_model_pack(context=personal_model_context, limit=max(1, limit // 3))
            + self.build_knowledge_pack(context=knowledge_context, limit=max(1, limit // 3))
            + self.build_operational_pack(inbox=inbox, calendar=calendar, limit=max(1, limit // 3))
        )
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in entries:
            marker = "|".join(
                [
                    str(item.get("family") or ""),
                    str(item.get("source_type") or ""),
                    str(item.get("source_ref") or ""),
                    str(item.get("predicate") or ""),
                    str(item.get("summary") or ""),
                ]
            )
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(item)
        deduped.sort(
            key=lambda item: (
                0 if str(item.get("assistant_visibility") or "") == "visible" else 1,
                -float(item.get("priority") or 0.0),
                {"hot": 0, "warm": 1, "stable": 2, "stale": 3, "unknown": 4}.get(str(item.get("freshness") or "unknown"), 4),
                str(item.get("title") or ""),
            )
        )
        return deduped[: max(1, limit)]

    def prompt_lines(self, entries: list[dict[str, Any]] | None, *, limit: int = 6) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        for item in list(entries or [])[: max(0, limit)]:
            line = str(item.get("prompt_line") or "").strip()
            if not line or line in seen:
                continue
            seen.add(line)
            lines.append(line)
        return lines
