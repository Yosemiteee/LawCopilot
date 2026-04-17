from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact_text(value: Any, *, limit: int = 500) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return " ".join(text.split())


def _slugify(value: Any) -> str:
    normalized = _normalize_text(value)
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "item"


def _contains_any_normalized(haystack: str, terms: tuple[str, ...]) -> bool:
    return any(_normalize_text(term) in haystack for term in terms if _normalize_text(term))


def _looks_like_external_profile_email_signal(*, sender: str, subject: str, snippet: str) -> bool:
    haystack = _normalize_text(" ".join(part for part in (sender, subject, snippet) if str(part or "").strip()))
    if not haystack:
        return False
    if _contains_any_normalized(haystack, EXTERNAL_PROFILE_DOCUMENT_HINTS):
        return True
    if _contains_any_normalized(haystack, EXTERNAL_PROFILE_APPLICATION_TERMS):
        return True
    if _contains_any_normalized(haystack, EXTERNAL_PROFILE_ROLE_TERMS):
        return True
    if _contains_any_normalized(haystack, EXTERNAL_PROFILE_SKILL_TERMS):
        return True
    return False


def _looks_like_user_owned_profile_message(*, body: str, direction: str) -> bool:
    if str(direction or "").strip().lower() != "outbound":
        return False
    haystack = _normalize_text(body)
    if not haystack:
        return False
    if _contains_any_normalized(haystack, EXTERNAL_PROFILE_DOCUMENT_HINTS):
        return True
    if _contains_any_normalized(haystack, EXTERNAL_PROFILE_APPLICATION_TERMS):
        return True
    if _contains_any_normalized(haystack, EXTERNAL_PROFILE_ROLE_TERMS):
        return True
    if _contains_any_normalized(haystack, EXTERNAL_PROFILE_SKILL_TERMS):
        return True
    return False


def _fingerprint(parts: list[Any]) -> str:
    seed = "|".join(str(item or "") for item in parts)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10]


INTERVIEW_MODULES: dict[str, dict[str, Any]] = {
    "goals": {
        "title": "Goals",
        "description": "Kullanıcının neyi başarmak istediği ve neden önemli olduğu.",
        "questions": [
            {
                "id": "goal_primary",
                "prompt": "Şu ara en çok neyi başarmak istiyorsun?",
                "category": "goals",
                "fact_key": "goal.primary",
                "title": "Birincil hedef",
                "help_text": "İş, sağlık, öğrenme veya kişisel düzen olabilir.",
                "examples": ["Daha düzenli çalışmak istiyorum.", "Yapay zeka alanında uzmanlaşmak istiyorum."],
            },
            {
                "id": "goal_success_metric",
                "prompt": "Bunun iyi gittiğini nasıl anlarsın?",
                "category": "goals",
                "fact_key": "goal.success_metric",
                "title": "Başarı ölçütü",
                "help_text": "Somut bir gösterge yazabilirsen sonraki öneriler daha iyi olur.",
            },
            {
                "id": "goal_obstacle",
                "prompt": "Bu hedefin önündeki en büyük engel ne?",
                "category": "constraints",
                "fact_key": "goal.primary_obstacle",
                "title": "Ana engel",
            },
        ],
    },
    "work_style": {
        "title": "Work Style",
        "description": "Planlama, enerji ve dikkat düzeni.",
        "questions": [
            {
                "id": "preferred_work_time",
                "prompt": "Genelde en verimli çalıştığın zaman aralığı hangisi?",
                "category": "routines",
                "fact_key": "work.preferred_time",
                "title": "Tercih edilen çalışma zamanı",
                "choices": [
                    {"value": "morning", "label": "Sabah"},
                    {"value": "afternoon", "label": "Öğleden sonra"},
                    {"value": "evening", "label": "Akşam"},
                    {"value": "night", "label": "Gece"},
                    {"value": "flexible", "label": "Duruma göre"},
                ],
            },
            {
                "id": "planning_style",
                "prompt": "Planlarını daha çok nasıl yürütmeyi seversin?",
                "category": "work_style",
                "fact_key": "planning.style",
                "title": "Planlama stili",
                "examples": ["Kısa günlük plan severim.", "Haftalık bakış ve net öncelikler isterim."],
            },
            {
                "id": "planning_struggle",
                "prompt": "Planlama veya takip tarafında en çok nerede zorlanıyorsun?",
                "category": "work_style",
                "fact_key": "planning.struggle_summary",
                "title": "Planlama zorluğu özeti",
            },
            {
                "id": "interruption_tolerance",
                "prompt": "Gün içinde kesintilere ne kadar açıksın?",
                "category": "work_style",
                "fact_key": "interruption.tolerance",
                "title": "Bölünme toleransı",
                "choices": [
                    {"value": "low", "label": "Düşük"},
                    {"value": "medium", "label": "Orta"},
                    {"value": "high", "label": "Yüksek"},
                ],
            },
        ],
    },
    "preferences": {
        "title": "Preferences",
        "description": "Hatırlatma ve destek tercihi.",
        "questions": [
            {
                "id": "reminder_tolerance",
                "prompt": "Hatırlatma ve takip konusunda nasıl bir yaklaşım sana uyar?",
                "category": "preferences",
                "fact_key": "reminder.tolerance",
                "title": "Hatırlatma toleransı",
                "choices": [
                    {"value": "light", "label": "Seyrek ve hafif"},
                    {"value": "balanced", "label": "Dengeli"},
                    {"value": "active", "label": "Daha aktif takip"},
                ],
            },
            {
                "id": "support_focus",
                "prompt": "Asistanın en çok hangi konuda işe yaramasını istiyorsun?",
                "category": "preferences",
                "fact_key": "assistant.support_focus",
                "title": "Destek odağı",
            },
        ],
    },
    "communication": {
        "title": "Communication",
        "description": "Asistanın nasıl konuşması ve yazması gerektiği.",
        "questions": [
            {
                "id": "communication_style",
                "prompt": "Benim sana yazarken nasıl bir ton kullanmamı istersin?",
                "category": "communication",
                "fact_key": "communication.style",
                "title": "Tercih edilen iletişim tonu",
                "choices": [
                    {"value": "concise", "label": "Kısa ve net"},
                    {"value": "balanced", "label": "Dengeli"},
                    {"value": "detailed", "label": "Detaylı"},
                ],
            },
            {
                "id": "assistant_behavior",
                "prompt": "Asistanın davranış olarak özellikle dikkat etmesini istediğin bir şey var mı?",
                "category": "assistant_preferences",
                "fact_key": "assistant.behavior",
                "title": "Asistan davranış tercihi",
            },
        ],
    },
}

CRITICAL_FACT_PRIORITIES: dict[str, float] = {
    "goal.primary": 2.4,
    "communication.style": 2.2,
    "assistant.support_focus": 2.0,
    "planning.style": 1.9,
    "work.preferred_time": 1.8,
    "reminder.tolerance": 1.7,
    "interruption.tolerance": 1.5,
}

MODULE_BASE_PRIORITIES: dict[str, float] = {
    "communication": 1.1,
    "goals": 1.05,
    "preferences": 1.0,
    "work_style": 0.95,
}

SENSITIVE_SIGNAL_PATTERNS: tuple[str, ...] = (
    "sifre",
    "şifre",
    "password",
    "iban",
    "kart",
    "kredi kart",
    "tc kimlik",
    "adresim",
    "adresim ",
    "ev adresi",
    "telefon numaram",
    "banka",
    "hesap numara",
    "hastalik",
    "hastalık",
    "tedavi",
    "tanı",
    "tani",
    "ilac",
    "ilaç",
)

EXTERNAL_PROFILE_SKILL_TERMS: tuple[str, ...] = (
    "python",
    "django",
    "fastapi",
    "flask",
    "javascript",
    "typescript",
    "react",
    "next.js",
    "node.js",
    "node",
    "postgresql",
    "postgres",
    "mysql",
    "sql server",
    "docker",
    "kubernetes",
    "aws",
    "gcp",
    "azure",
    "openai",
    "gemini",
    "figma",
    "git",
)

EXTERNAL_PROFILE_ROLE_TERMS: tuple[str, ...] = (
    "backend developer",
    "backend engineer",
    "frontend developer",
    "frontend engineer",
    "full stack developer",
    "full-stack developer",
    "software engineer",
    "software developer",
    "product manager",
    "project manager",
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "ai engineer",
    "designer",
    "lawyer",
    "attorney",
    "intern",
)

EXTERNAL_PROFILE_APPLICATION_TERMS: tuple[str, ...] = (
    "cv",
    "resume",
    "özgeçmiş",
    "ozgecmis",
    "curriculum vitae",
    "başvuru",
    "basvuru",
    "application",
    "apply",
    "interview",
    "mülakat",
    "mulakat",
    "position",
    "rol",
    "job",
    "kariyer",
    "recruiter",
    "hr",
)

EXTERNAL_PROFILE_DOCUMENT_HINTS: tuple[str, ...] = (
    "cv",
    "resume",
    "özgeçmiş",
    "ozgecmis",
    "curriculum vitae",
)

EXTERNAL_PROFILE_ALLOWED_FACT_KEYS: tuple[str, ...] = (
    "identity.professional_focus",
    "career.profile_summary",
    "career.skill_summary",
    "career.application_activity",
    "career.document_signal",
)


class PersonalModelService:
    def __init__(
        self,
        store: Any,
        office_id: str,
        *,
        events: Any | None = None,
        epistemic: Any | None = None,
        memory_mutations: Any | None = None,
        runtime: Any | None = None,
    ) -> None:
        self.store = store
        self.office_id = office_id
        self.events = events
        self.epistemic = epistemic
        self.memory_mutations = memory_mutations
        self.runtime = runtime
        self._external_profile_learning_last_run_at = 0.0

    def overview(self, *, limit: int = 80) -> dict[str, Any]:
        self.sync_external_profile_learning()
        sessions = self.store.list_personal_model_sessions(self.office_id, limit=12)
        active_session = next((item for item in sessions if str(item.get("status") or "") in {"active", "paused"}), None)
        facts = self.store.list_personal_model_facts(self.office_id, limit=limit)
        raw_entries = self.store.list_personal_model_raw_entries(self.office_id, limit=min(limit, 60))
        suggestions = self.store.list_personal_model_suggestions(self.office_id, status="pending", limit=20)
        summary = self.profile_summary(facts=facts)
        modules = []
        latest_progress = dict((active_session or {}).get("progress") or {})
        for key, module in INTERVIEW_MODULES.items():
            total_questions = len(list(module.get("questions") or []))
            answered_count = 0
            if active_session and key in list(active_session.get("module_keys") or []):
                answered_count = int(((latest_progress.get("modules") or {}).get(key) or {}).get("answered", 0))
            else:
                answered_count = sum(1 for item in facts if str((item.get("metadata") or {}).get("module_key") or "") == key)
            modules.append(
                {
                    "key": key,
                    "title": module.get("title"),
                    "description": module.get("description"),
                    "question_count": total_questions,
                    "answered_count": answered_count,
                    "complete": answered_count >= total_questions and total_questions > 0,
                }
            )
        return {
            "generated_at": _iso_now(),
            "active_session": self._session_payload(active_session) if active_session else None,
            "sessions": [self._session_payload(item) for item in sessions],
            "modules": modules,
            "facts": [self._fact_payload(item) for item in facts],
            "raw_entries": [self._raw_entry_payload(item) for item in raw_entries],
            "pending_suggestions": [self._suggestion_payload(item) for item in suggestions],
            "profile_summary": summary,
            "usage_policy": {
                "sensitive_facts_auto_used": False,
                "explicit_and_inferred_are_separated": True,
                "disabled_facts_used": False,
                "never_use_flag_respected": True,
            },
        }

    def start_session(self, *, module_keys: list[str] | None = None, scope: str = "global", source: str = "guided_interview") -> dict[str, Any]:
        known_facts = self.store.list_personal_model_facts(self.office_id, include_disabled=True, limit=400)
        known_index = self._known_fact_index(known_facts)
        selected_modules = [key for key in list(module_keys or INTERVIEW_MODULES.keys()) if key in INTERVIEW_MODULES]
        if not selected_modules:
            selected_modules = list(INTERVIEW_MODULES.keys())
        selected_modules = self._prioritize_modules(selected_modules, known_index)
        session_id = f"pms-{_fingerprint([self.office_id, scope, selected_modules, _iso_now()])}"
        state = {
            "module_keys": selected_modules,
            "asked_question_ids": [],
            "skipped_question_ids": [],
            "answers": {},
            "follow_up_queue": [],
            "session_context": {
                "started_from": source,
                "known_fact_keys": sorted(known_index.keys()),
                "question_count_hint": self._estimated_question_total(selected_modules, known_index),
            },
        }
        current_question = self._next_question(state)
        progress = self._progress_payload(state)
        summary = {"raw_entry_count": 0, "fact_count": 0}
        session = self.store.create_personal_model_session(
            self.office_id,
            session_id=session_id,
            scope=scope,
            source=source,
            module_keys=selected_modules,
            status="active",
            current_question_id=str((current_question or {}).get("id") or ""),
            state=state,
            progress=progress,
            summary=summary,
        )
        self._log("personal_model_session_started", session_id=session_id, module_count=len(selected_modules), scope=scope)
        return self._session_payload(session)

    def pause_session(self, session_id: str) -> dict[str, Any]:
        session = self.store.update_personal_model_session(
            self.office_id,
            session_id,
            status="paused",
            paused_at=_iso_now(),
        )
        if not session:
            raise ValueError("session_not_found")
        self._log("personal_model_session_paused", session_id=session_id)
        return self._session_payload(session)

    def resume_session(self, session_id: str) -> dict[str, Any]:
        session = self.store.get_personal_model_session(self.office_id, session_id)
        if not session:
            raise ValueError("session_not_found")
        state = dict(session.get("state") or {})
        current_question = self._next_question(state)
        resumed = self.store.update_personal_model_session(
            self.office_id,
            session_id,
            status="active",
            paused_at=None,
            current_question_id=str((current_question or {}).get("id") or ""),
            state=state,
            progress=self._progress_payload(state),
        )
        self._log("personal_model_session_resumed", session_id=session_id)
        return self._session_payload(resumed or session)

    def answer_question(self, session_id: str, *, answer_text: str, choice_value: str | None = None, answer_kind: str = "text") -> dict[str, Any]:
        session = self.store.get_personal_model_session(self.office_id, session_id)
        if not session:
            raise ValueError("session_not_found")
        state = dict(session.get("state") or {})
        question = self._next_question(state)
        if not question:
            raise ValueError("session_complete")
        text = _compact_text(answer_text, limit=1000)
        if not text:
            raise ValueError("answer_required")
        entry = self.store.add_personal_model_raw_entry(
            self.office_id,
            session_id=session_id,
            module_key=str(question.get("module_key") or ""),
            question_id=str(question.get("id") or ""),
            question_text=str(question.get("prompt") or ""),
            answer_text=text,
            answer_kind=answer_kind,
            answer_value={"text": text, "choice_value": choice_value},
            source="interview",
            confidence_type="explicit",
            confidence=1.0,
            explicit=True,
            metadata={"module_key": question.get("module_key"), "question_title": question.get("title")},
        )
        asked = list(state.get("asked_question_ids") or [])
        if str(question.get("id") or "") not in asked:
            asked.append(str(question.get("id") or ""))
        answers = dict(state.get("answers") or {})
        answers[str(question.get("id") or "")] = {"text": text, "choice_value": choice_value}
        follow_ups = list(state.get("follow_up_queue") or [])
        follow_ups = [item for item in follow_ups if str(item.get("id") or "") != str(question.get("id") or "")]
        follow_ups.extend(self._adaptive_follow_ups(question, text, choice_value))
        stored_facts = []
        for fact in self._normalize_facts(
            question,
            text,
            choice_value,
            source_entry_id=int(entry.get("id")),
            session_id=session_id,
            scope=str(session.get("scope") or "global"),
        ):
            stored = self.store.upsert_personal_model_fact(self.office_id, **fact)
            stored_facts.append(stored)
            self._sync_fact_epistemics(
                fact=stored,
                raw_entry=entry,
                source_kind="guided_interview",
                basis="user_explicit",
                validation_state="user_confirmed",
            )
        state.update(
            {
                "asked_question_ids": asked,
                "answers": answers,
                "follow_up_queue": follow_ups,
                "session_context": {
                    **dict(state.get("session_context") or {}),
                    "last_answered_question_id": str(question.get("id") or ""),
                    "last_module_key": str(question.get("module_key") or ""),
                    "known_fact_keys": sorted(
                        set((state.get("session_context") or {}).get("known_fact_keys") or [])
                        | {str(item.get("fact_key") or "") for item in stored_facts if str(item.get("fact_key") or "").strip()}
                    ),
                },
            }
        )
        next_question = self._next_question(state)
        progress = self._progress_payload(state)
        summary = {
            "raw_entry_count": len(self.store.list_personal_model_raw_entries(self.office_id, session_id=session_id, limit=500)),
            "fact_count": len(self.store.list_personal_model_facts(self.office_id, limit=500)),
        }
        completed = next_question is None
        updated = self.store.update_personal_model_session(
            self.office_id,
            session_id,
            status="completed" if completed else "active",
            completed_at=_iso_now() if completed else None,
            current_question_id=str((next_question or {}).get("id") or ""),
            state=state,
            progress=progress,
            summary=summary,
        )
        self._log(
            "personal_model_question_answered",
            session_id=session_id,
            question_id=str(question.get("id") or ""),
            stored_fact_count=len(stored_facts),
            completed=completed,
        )
        profile_reconciliation = self._reconcile_profile(authority="fact", reason="personal_model_answer")
        return {
            "session": self._session_payload(updated or session),
            "raw_entry": self._raw_entry_payload(entry),
            "stored_facts": [self._fact_payload(item) for item in stored_facts],
            "next_question": self._question_payload(next_question) if next_question else None,
            "profile_summary": self.profile_summary(),
            "profile_reconciliation": profile_reconciliation,
        }

    def skip_question(self, session_id: str) -> dict[str, Any]:
        session = self.store.get_personal_model_session(self.office_id, session_id)
        if not session:
            raise ValueError("session_not_found")
        state = dict(session.get("state") or {})
        question = self._next_question(state)
        if not question:
            raise ValueError("session_complete")
        skipped = list(state.get("skipped_question_ids") or [])
        if str(question.get("id") or "") not in skipped:
            skipped.append(str(question.get("id") or ""))
        follow_ups = [item for item in list(state.get("follow_up_queue") or []) if str(item.get("id") or "") != str(question.get("id") or "")]
        state.update({"skipped_question_ids": skipped, "follow_up_queue": follow_ups})
        next_question = self._next_question(state)
        updated = self.store.update_personal_model_session(
            self.office_id,
            session_id,
            status="completed" if next_question is None else "active",
            completed_at=_iso_now() if next_question is None else None,
            current_question_id=str((next_question or {}).get("id") or ""),
            state=state,
            progress=self._progress_payload(state),
        )
        self._log("personal_model_question_skipped", session_id=session_id, question_id=str(question.get("id") or ""))
        return self._session_payload(updated or session)

    def list_facts(self, *, category: str | None = None, scope: str | None = None, include_disabled: bool = True) -> list[dict[str, Any]]:
        self.sync_external_profile_learning()
        return [self._fact_payload(item) for item in self.store.list_personal_model_facts(self.office_id, category=category, scope=scope, include_disabled=include_disabled)]

    def update_fact(
        self,
        fact_id: str,
        *,
        value_text: str | None = None,
        scope: str | None = None,
        enabled: bool | None = None,
        never_use: bool | None = None,
        sensitive: bool | None = None,
        visibility: str | None = None,
        confidence: float | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        existing = self.store.get_personal_model_fact(self.office_id, fact_id)
        if not existing:
            raise ValueError("fact_not_found")
        metadata = dict(existing.get("metadata") or {})
        history = list(metadata.get("correction_history") or [])
        change_actions: list[str] = []
        if value_text is not None and str(value_text) != str(existing.get("value_text") or ""):
            change_actions.append("manual_edit")
        if scope is not None and str(scope) != str(existing.get("scope") or ""):
            change_actions.append("scope_change")
        if enabled is not None and bool(enabled) != bool(existing.get("enabled")):
            change_actions.append("enable_toggle")
        if never_use is not None and bool(never_use) != bool(existing.get("never_use")):
            change_actions.append("never_use_toggle")
        if sensitive is not None and bool(sensitive) != bool(existing.get("sensitive")):
            change_actions.append("sensitive_toggle")
        if confidence is not None and float(confidence) != float(existing.get("confidence") or 0.0):
            change_actions.append("confidence_change")
        if note or change_actions:
            history.append(
                {
                    "action": change_actions[0] if change_actions else "manual_note",
                    "actions": change_actions,
                    "note": _compact_text(note, limit=280) if note else "",
                    "timestamp": _iso_now(),
                }
            )
        metadata["correction_history"] = history[-20:]
        if bool(sensitive if sensitive is not None else existing.get("sensitive")):
            metadata["storage_hint"] = "local_only"
            metadata["prompt_usage"] = "blocked"
        updated = self.store.update_personal_model_fact(
            self.office_id,
            fact_id,
            value_text=value_text,
            scope=scope,
            enabled=enabled,
            never_use=never_use,
            sensitive=sensitive,
            visibility=visibility,
            confidence=confidence,
            metadata=metadata,
        )
        if not updated:
            raise ValueError("fact_not_found")
        self._sync_fact_epistemics(
            fact=updated,
            raw_entry=None,
            source_kind="manual_edit",
            basis="user_explicit",
            validation_state="user_confirmed",
        )
        self._log("personal_model_fact_updated", fact_id=fact_id)
        payload = self._fact_payload(updated)
        payload["profile_reconciliation"] = self._reconcile_profile(authority="fact", reason="personal_model_fact_update")
        return payload

    def delete_fact(self, fact_id: str) -> dict[str, Any]:
        existing = self.store.get_personal_model_fact(self.office_id, fact_id)
        if not existing:
            raise ValueError("fact_not_found")
        self._retire_fact_claims(existing, reason="deleted_by_user")
        deleted = self.store.delete_personal_model_fact(self.office_id, fact_id)
        if not deleted:
            raise ValueError("fact_not_found")
        self._log("personal_model_fact_deleted", fact_id=fact_id)
        return {"deleted": True, "fact_id": fact_id}

    def retrieve_relevant_facts(self, query: str, *, scopes: list[str] | None = None, limit: int = 6) -> dict[str, Any]:
        normalized_query = _normalize_text(query)
        intent = self._detect_intent(normalized_query)
        selected_categories = list(intent.get("categories") or [])
        allowed_scopes = list(scopes or ["global", "personal"])
        facts = self.store.list_personal_model_facts(self.office_id, include_disabled=False, limit=400)
        ranked: list[tuple[float, dict[str, Any], list[str]]] = []
        for item in facts:
            if bool(item.get("never_use")) or bool(item.get("sensitive")):
                continue
            item_scope = str(item.get("scope") or "global")
            if allowed_scopes and item_scope not in allowed_scopes:
                continue
            reasons: list[str] = []
            score = 0.0
            category = str(item.get("category") or "")
            if category in selected_categories:
                score += 1.5
                reasons.append("intent_category_match")
            elif not selected_categories:
                score += 0.2
                reasons.append("fallback_profile_context")
            value_text = _normalize_text(item.get("value_text"))
            if value_text and any(token in value_text for token in normalized_query.split()):
                score += 0.55
                reasons.append("semantic_overlap")
            if str(item.get("confidence_type") or "") == "explicit":
                score += 0.3
                reasons.append("explicit_memory")
            else:
                score += 0.08
                reasons.append("approved_inference")
            score += min(0.5, float(item.get("confidence") or 0.0) * 0.4)
            if item_scope == "global":
                score += 0.05
                reasons.append("global_scope")
            if score <= 0.0:
                continue
            ranked.append((score, item, reasons))
        ranked.sort(key=lambda entry: (-entry[0], str(entry[1].get("updated_at") or ""), str(entry[1].get("fact_key") or "")), reverse=False)
        selected: list[dict[str, Any]] = []
        seen_categories: dict[str, int] = {}
        for score, item, reasons in ranked:
            category = str(item.get("category") or "")
            if seen_categories.get(category, 0) >= 2 and len(selected) >= max(2, min(limit, 4)):
                continue
            seen_categories[category] = seen_categories.get(category, 0) + 1
            payload = self._fact_payload(item)
            payload["selection_reasons"] = list(dict.fromkeys(reasons))
            payload["selection_reason_labels"] = [self._selection_reason_label(reason) for reason in list(dict.fromkeys(reasons))]
            payload["score"] = round(score, 3)
            selected.append(payload)
            if len(selected) >= max(1, min(limit, 12)):
                break
        claim_summary_lines = [
            f"- [{str(item.get('epistemic_basis_label') or 'kullanıcı bilgisi')}] {item.get('title')}: {item.get('value_text')}"
            for item in selected
            if str(item.get("epistemic_status") or "").strip().lower() == "current"
            and str(item.get("epistemic_support_strength") or "").strip().lower() in {"grounded", "supported"}
            and not bool(item.get("epistemic_support_contaminated"))
        ]
        explicit_selected = any(str(item.get("confidence_type") or "") == "explicit" for item in selected[:3])
        verification_gate = {
            "mode": "verified" if explicit_selected and claim_summary_lines
            else "cautious" if selected else "strict",
            "reason": "Açık veya doğrulanmış kişisel fact seçildi."
            if selected and explicit_selected
            else "Kişisel bağlam çoğunlukla çıkarım/yardımcı sinyal düzeyinde; kesin ifade temkinli kullanılmalı."
            if selected
            else "İlgili kişisel fact seçilmedi.",
        }
        return {
            "query": query,
            "intent": intent,
            "selected_categories": selected_categories,
            "facts": selected,
            "claim_summary_lines": claim_summary_lines,
            "summary_lines": [
                f"- [{item.get('category')}] {item.get('title')}: {item.get('value_text')}"
                for item in selected
            ],
            "usage_note": "Yalnız etkin, izinli ve hassas olmayan ilgili bilgiler seçildi.",
            "verification_gate": verification_gate,
        }

    def profile_summary(self, *, facts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        items = list(facts or self.store.list_personal_model_facts(self.office_id, include_disabled=False, limit=200))
        visible_items = [item for item in items if not bool(item.get("never_use"))]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in visible_items:
            grouped.setdefault(str(item.get("category") or "misc"), []).append(item)
        sections: list[dict[str, Any]] = []
        markdown_lines = ["# Bana Dair", ""]
        title_map = {
            "identity": "Kişisel Çerçeve",
            "career": "Profesyonel Profil",
            "goals": "Hedefler",
            "constraints": "Kısıtlar",
            "work_style": "Çalışma Tarzı",
            "routines": "Rutinler",
            "preferences": "Tercihler",
            "communication": "İletişim",
            "assistant_preferences": "Asistan Tercihleri",
        }
        for category in ("identity", "career", "goals", "constraints", "work_style", "routines", "preferences", "communication", "assistant_preferences"):
            rows = grouped.get(category) or []
            if not rows:
                continue
            title = title_map.get(category, category.replace("_", " ").title())
            sections.append(
                {
                    "category": category,
                    "title": title,
                    "facts": [self._fact_payload(item) for item in rows[:6]],
                }
            )
            markdown_lines.append(f"## {title}")
            for item in rows[:6]:
                markdown_lines.append(f"- {item.get('title')}: {item.get('value_text')}")
            markdown_lines.append("")
        guidance = [
            self._fact_payload(item)
            for item in visible_items
            if str(item.get("category") or "") in {"communication", "assistant_preferences", "preferences"}
        ][:6]
        return {
            "generated_at": _iso_now(),
            "fact_count": len(visible_items),
            "sections": sections,
            "markdown": "\n".join(markdown_lines).strip(),
            "assistant_guidance": guidance,
        }

    def sync_external_profile_learning(self, *, force: bool = False) -> dict[str, Any]:
        now_ts = datetime.now(timezone.utc).timestamp()
        if not force and now_ts - float(self._external_profile_learning_last_run_at or 0.0) < 90:
            return {"ok": True, "skipped": True, "reason": "cooldown"}
        sources = self._collect_external_profile_learning_sources()
        items = list(sources.get("items") or [])
        if not items:
            self._external_profile_learning_last_run_at = now_ts
            return {"ok": True, "skipped": True, "reason": "no_sources"}
        facts = self._derive_external_profile_facts(items)
        stored_facts: list[dict[str, Any]] = []
        for fact in facts:
            stored = self._store_external_profile_fact(fact)
            if stored:
                stored_facts.append(stored)
        self._external_profile_learning_last_run_at = now_ts
        self._log(
            "personal_model_external_profile_learning_synced",
            source_count=len(items),
            fact_count=len(stored_facts),
            provider_count=len(list(sources.get("providers") or [])),
            document_count=int(sources.get("document_count") or 0),
        )
        return {
            "ok": True,
            "skipped": False,
            "source_count": len(items),
            "fact_count": len(stored_facts),
            "providers": list(sources.get("providers") or []),
            "document_count": int(sources.get("document_count") or 0),
            "facts": [self._fact_payload(item) for item in stored_facts],
        }

    def propose_chat_facts(self, text: str, *, scope: str = "global") -> list[dict[str, Any]]:
        normalized = _normalize_text(text)
        if not normalized or len(normalized) < 8:
            return []
        candidates = self._chat_learning_candidates(text, normalized=normalized, scope=scope)
        deduped: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        all_suggestions = self.store.list_personal_model_suggestions(self.office_id, limit=240)
        existing_pending = [item for item in all_suggestions if str(item.get("status") or "") == "pending"]
        existing_fact_texts = {
            f"{str(item.get('fact_key') or '')}:{_normalize_text(item.get('value_text'))}"
            for item in self.store.list_personal_model_facts(self.office_id, limit=300)
        }
        for candidate in candidates:
            signature = f"{candidate.get('fact_key')}:{_normalize_text(candidate.get('proposed_value_text'))}"
            if signature in seen_keys or signature in existing_fact_texts:
                continue
            if self._should_suppress_suggestion(candidate, all_suggestions=all_suggestions):
                continue
            if any(
                str(item.get("id") or "") != str(candidate.get("id") or "")
                and
                str(item.get("fact_key") or "") == str(candidate.get("fact_key") or "")
                and _normalize_text(item.get("proposed_value_text")) == _normalize_text(candidate.get("proposed_value_text"))
                for item in existing_pending
            ):
                continue
            seen_keys.add(signature)
            deduped.append(candidate)
        return deduped

    def review_suggestion(self, suggestion_id: str, *, decision: str) -> dict[str, Any]:
        suggestion = self.store.get_personal_model_suggestion(self.office_id, suggestion_id)
        if not suggestion:
            raise ValueError("suggestion_not_found")
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"accept", "reject"}:
            raise ValueError("unsupported_decision")
        if normalized_decision == "reject":
            updated = self.store.update_personal_model_suggestion_status(
                self.office_id,
                suggestion_id,
                status="rejected",
                metadata={
                    **dict(suggestion.get("metadata") or {}),
                    "reviewed_at": _iso_now(),
                    "decision": "rejected",
                    "suppression_signature": self._suggestion_signature(suggestion),
                },
            )
            self._log("personal_model_suggestion_rejected", suggestion_id=suggestion_id)
            return {"decision": "rejected", "suggestion": self._suggestion_payload(updated or suggestion)}
        raw_entry = self.store.add_personal_model_raw_entry(
            self.office_id,
            session_id=None,
            module_key=str((suggestion.get("metadata") or {}).get("module_key") or "chat_learning"),
            question_id=str((suggestion.get("metadata") or {}).get("suggestion_type") or "chat_learning"),
            question_text=str(suggestion.get("prompt") or "Sohbetten çıkarılan olası bilgi"),
            answer_text=str(suggestion.get("proposed_value_text") or ""),
            answer_kind="chat_signal",
            answer_value={
                "text": str(suggestion.get("proposed_value_text") or ""),
                "source": str(suggestion.get("source") or "chat"),
                "evidence": dict(suggestion.get("evidence") or {}),
            },
            source="chat",
            confidence_type="inferred",
            confidence=float(suggestion.get("confidence") or 0.65),
            explicit=False,
            metadata={
                "approved_from_suggestion_id": suggestion_id,
                "suggestion_type": str((suggestion.get("metadata") or {}).get("suggestion_type") or "chat_learning"),
            },
        )
        fact = self.store.upsert_personal_model_fact(
            self.office_id,
            fact_id=f"pmf-{_fingerprint([suggestion.get('fact_key'), suggestion.get('scope'), suggestion.get('proposed_value_text')])}",
            session_id=None,
            category=str(suggestion.get("category") or "preferences"),
            fact_key=str(suggestion.get("fact_key") or ""),
            title=str(suggestion.get("title") or "Approved inference"),
            value_text=str(suggestion.get("proposed_value_text") or ""),
            value_json=dict(suggestion.get("proposed_value_json") or {}),
            confidence=float(suggestion.get("confidence") or 0.65),
            confidence_type="inferred",
            source_entry_id=int(raw_entry.get("id")) if raw_entry.get("id") is not None else None,
            visibility="assistant_visible",
            scope=str(suggestion.get("scope") or "global"),
            sensitive=bool(suggestion.get("sensitive")),
            enabled=True,
            never_use=False,
            metadata={
                **dict(suggestion.get("metadata") or {}),
                "approved_from_suggestion_id": suggestion_id,
                "user_confirmed": True,
                "source": str(suggestion.get("source") or "chat"),
                "evidence": dict(suggestion.get("evidence") or {}),
                "storage_hint": "local_only" if bool(suggestion.get("sensitive")) else "standard",
            },
        )
        self._sync_fact_epistemics(
            fact=fact,
            raw_entry=raw_entry,
            source_kind="chat_learning",
            basis="user_confirmed_inference",
            validation_state="user_confirmed",
        )
        updated = self.store.update_personal_model_suggestion_status(
            self.office_id,
            suggestion_id,
            status="accepted",
            metadata={
                **dict(suggestion.get("metadata") or {}),
                "reviewed_at": _iso_now(),
                "decision": "accepted",
                "accepted_fact_id": fact.get("id"),
            },
        )
        self._log("personal_model_suggestion_accepted", suggestion_id=suggestion_id, fact_id=fact.get("id"))
        return {
            "decision": "accepted",
            "fact": self._fact_payload(fact),
            "suggestion": self._suggestion_payload(updated or suggestion),
            "profile_reconciliation": self._reconcile_profile(authority="fact", reason="personal_model_suggestion_accept"),
        }

    def build_chat_consent_reply(self, suggestions: list[dict[str, Any]]) -> str:
        if not suggestions:
            return ""
        item = suggestions[0]
        reason = str(item.get("learning_reason") or "Sohbetinden bir eğilim fark ettim.")
        confidence = str(item.get("confidence_label") or "")
        return f"{reason} {item.get('prompt')} {confidence} Doğruysa evet de, yanlışsa hayır de."

    def try_handle_chat_consent_reply(self, query: str, *, prior_messages: list[dict[str, Any]]) -> dict[str, Any] | None:
        last_assistant = next((item for item in reversed(prior_messages or []) if str(item.get("role") or "") == "assistant"), None)
        source_context = dict((last_assistant or {}).get("source_context") or {})
        suggestion_ids = [str(item).strip() for item in list(source_context.get("personal_model_suggestion_ids") or []) if str(item).strip()]
        if not suggestion_ids:
            return None
        normalized = _normalize_text(query)
        if normalized in {"evet", "olur", "kaydet", "hatirla", "hatırla", "evet kaydet", "dogru", "doğru", "aynen"}:
            result = self.review_suggestion(suggestion_ids[0], decision="accept")
            fact = dict(result.get("fact") or {})
            return {
                "handled": True,
                "decision": "accept",
                "content": f"Tamam, bunu kaydettim: {fact.get('title') or 'yeni bilgi'}.",
                "fact": fact,
            }
        if normalized in {"hayir", "hayır", "kaydetme", "gerek yok", "istemiyorum", "yanlis", "yanlış", "olmasin", "olmasın"}:
            result = self.review_suggestion(suggestion_ids[0], decision="reject")
            return {
                "handled": True,
                "decision": "reject",
                "content": "Tamam, bunu kalıcı profile kaydetmiyorum.",
                "suggestion": result.get("suggestion"),
            }
        return None

    def _create_suggestion(
        self,
        *,
        source: str,
        category: str,
        fact_key: str,
        title: str,
        prompt: str,
        proposed_value_text: str,
        scope: str,
        confidence: float,
        evidence: dict[str, Any] | None,
        sensitive: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        suggestion_id = f"pmsug-{_fingerprint([source, category, fact_key, proposed_value_text])}"
        created = self.store.create_personal_model_suggestion(
            self.office_id,
            suggestion_id=suggestion_id,
            source=source,
            category=category,
            fact_key=fact_key,
            title=title,
            prompt=prompt,
            proposed_value_text=proposed_value_text,
            proposed_value_json={"text": proposed_value_text},
            confidence=confidence,
            scope=scope,
            sensitive=sensitive,
            evidence=evidence,
            metadata={"derived_from": source, **dict(metadata or {})},
        )
        self._log("personal_model_suggestion_created", suggestion_id=suggestion_id, category=category)
        return self._suggestion_payload(created)

    def _adaptive_follow_ups(self, question: dict[str, Any], answer_text: str, choice_value: str | None) -> list[dict[str, Any]]:
        question_id = str(question.get("id") or "")
        normalized = _normalize_text(answer_text)
        follow_ups: list[dict[str, Any]] = []
        if question_id == "planning_struggle" and normalized:
            follow_ups.append(
                {
                    "id": "planning_struggle_focus",
                    "module_key": "work_style",
                    "prompt": "Bu daha çok hangisine benziyor?",
                    "category": "work_style",
                    "fact_key": "planning.struggle_type",
                    "title": "Planlama zorluğu tipi",
                    "choices": [
                        {"value": "time_management", "label": "Zaman yönetimi"},
                        {"value": "motivation", "label": "Motivasyon"},
                        {"value": "distractions", "label": "Dikkat dağınıklığı"},
                        {"value": "clarity", "label": "Öncelik netliği"},
                    ],
                }
            )
        if question_id == "reminder_tolerance" and (choice_value or normalized):
            selected = choice_value or normalized
            if selected not in {"light"}:
                follow_ups.append(
                    {
                        "id": "reminder_channel",
                        "module_key": "preferences",
                        "prompt": "Hatırlatmalar geldiğinde hangisi daha iyi çalışır?",
                        "category": "preferences",
                        "fact_key": "reminder.channel",
                        "title": "Hatırlatma biçimi",
                        "choices": [
                            {"value": "brief_nudge", "label": "Kısa dürtme"},
                            {"value": "clear_task", "label": "Net görev listesi"},
                            {"value": "schedule_checkin", "label": "Saatli check-in"},
                        ],
                    }
                )
        if question_id == "preferred_work_time" and (choice_value or normalized) in {"flexible", "duruma gore", "duruma göre"}:
            follow_ups.append(
                {
                    "id": "preferred_work_time_flex",
                    "module_key": "work_style",
                    "prompt": "Esnek olduğunda bunu en çok ne belirliyor?",
                    "category": "routines",
                    "fact_key": "work.time_flexibility_driver",
                    "title": "Çalışma zamanı esneklik nedeni",
                }
            )
        return follow_ups

    def _normalize_facts(
        self,
        question: dict[str, Any],
        answer_text: str,
        choice_value: str | None,
        *,
        source_entry_id: int,
        session_id: str | None,
        scope: str,
    ) -> list[dict[str, Any]]:
        now = _iso_now()
        value_text = _compact_text(answer_text, limit=400)
        raw_value = choice_value or value_text
        question_id = str(question.get("id") or "")
        title = str(question.get("title") or question.get("prompt") or "Bilgi")
        category = str(question.get("category") or "preferences")
        fact_key = str(question.get("fact_key") or _slugify(question_id))
        confidence = 0.98
        value_json: dict[str, Any] = {"text": value_text}
        if choice_value:
            value_json["choice"] = choice_value
            value_text = self._choice_label(question, choice_value) or value_text
        metadata = {
            "module_key": question.get("module_key"),
            "question_id": question_id,
            "source_kind": "guided_interview",
            "captured_at": now,
            "correction_history": [],
        }
        if question_id == "goal_primary":
            fact_key = "goal.primary"
            category = "goals"
            title = "Birincil hedef"
        elif question_id == "goal_success_metric":
            fact_key = "goal.success_metric"
            category = "goals"
            title = "Başarı ölçütü"
        elif question_id == "goal_obstacle":
            fact_key = "goal.primary_obstacle"
            category = "constraints"
            title = "Ana engel"
        elif question_id == "planning_struggle_focus":
            category = "work_style"
            title = "Planlama zorluğu tipi"
            value_text = self._choice_label(question, choice_value or "") or value_text
        elif question_id == "reminder_channel":
            category = "preferences"
            title = "Hatırlatma biçimi"
            value_text = self._choice_label(question, choice_value or "") or value_text
        elif question_id == "communication_style":
            category = "communication"
            title = "İletişim tonu"
            value_text = self._choice_label(question, choice_value or "") or value_text
        elif question_id == "preferred_work_time":
            category = "routines"
            title = "Tercih edilen çalışma zamanı"
            value_text = self._choice_label(question, choice_value or "") or value_text
        fact_id = f"pmf-{_fingerprint([fact_key, scope, value_text])}"
        return [
            {
                "fact_id": fact_id,
                "session_id": session_id,
                "category": category,
                "fact_key": fact_key,
                "title": title,
                "value_text": value_text,
                "value_json": value_json,
                "confidence": confidence,
                "confidence_type": "explicit",
                "source_entry_id": source_entry_id,
                "visibility": "assistant_visible",
                "scope": scope,
                "sensitive": False,
                "enabled": True,
                "never_use": False,
                "metadata": metadata,
            }
        ]

    def _next_question(self, state: dict[str, Any]) -> dict[str, Any] | None:
        asked = {str(item) for item in list(state.get("asked_question_ids") or [])}
        skipped = {str(item) for item in list(state.get("skipped_question_ids") or [])}
        follow_ups = [item for item in list(state.get("follow_up_queue") or []) if str(item.get("id") or "") not in asked and str(item.get("id") or "") not in skipped]
        if follow_ups:
            next_follow_up = dict(follow_ups[0])
            next_follow_up.setdefault("module_key", next_follow_up.get("module_key") or "work_style")
            return next_follow_up
        for module_key in self._prioritize_modules(list(state.get("module_keys") or []), self._known_fact_index()):
            module = INTERVIEW_MODULES.get(module_key) or {}
            questions = [dict(item) for item in list(module.get("questions") or [])]
            questions.sort(key=lambda item: self._question_priority(item, state), reverse=True)
            for question in questions:
                question_id = str(question.get("id") or "")
                if question_id in asked or question_id in skipped:
                    continue
                if self._question_is_already_known(question, state):
                    continue
                return {
                    **question,
                    "module_key": module_key,
                }
        return None

    def _progress_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        asked = {str(item) for item in list(state.get("asked_question_ids") or [])}
        skipped = {str(item) for item in list(state.get("skipped_question_ids") or [])}
        module_progress: dict[str, Any] = {}
        answered_total = len(asked)
        skipped_total = len(skipped)
        total_questions = 0
        for module_key in list(state.get("module_keys") or []):
            module = INTERVIEW_MODULES.get(module_key) or {}
            question_ids = [
                str(item.get("id") or "")
                for item in list(module.get("questions") or [])
                if not self._question_is_already_known(item, state)
            ]
            total_questions += len(question_ids)
            module_progress[module_key] = {
                "answered": len([item for item in question_ids if item in asked]),
                "skipped": len([item for item in question_ids if item in skipped]),
                "total": len(question_ids),
            }
        total_questions += len([item for item in list(state.get("follow_up_queue") or []) if str(item.get("id") or "") in asked or str(item.get("id") or "") in skipped])
        completed_count = answered_total + skipped_total
        denominator = max(total_questions, completed_count or 1)
        return {
            "answered": answered_total,
            "skipped": skipped_total,
            "total": denominator,
            "completion_ratio": round(completed_count / denominator, 3),
            "modules": module_progress,
        }

    def _choice_label(self, question: dict[str, Any], value: str) -> str:
        for item in list(question.get("choices") or []):
            if str(item.get("value") or "") == str(value or ""):
                return str(item.get("label") or "").strip()
        return str(value or "").strip()

    def _detect_intent(self, normalized_query: str) -> dict[str, Any]:
        if any(token in normalized_query for token in ("plan", "takvim", "rutin", "program", "odak", "hedef")):
            return {"name": "planning", "categories": ["goals", "constraints", "work_style", "routines", "preferences", "career"]}
        if any(token in normalized_query for token in ("mesaj", "mail", "eposta", "iletisim", "yanit", "cevap", "yaz")):
            return {"name": "communication", "categories": ["communication", "assistant_preferences", "preferences", "identity"]}
        if any(token in normalized_query for token in ("hatirlat", "hatırlat", "takip", "unut", "bildirim")):
            return {"name": "follow_up", "categories": ["preferences", "routines", "work_style", "career"]}
        if any(token in normalized_query for token in ("cv", "resume", "özgeçmiş", "ozgecmis", "kariyer", "deneyim", "tecrube", "tecrübe", "beceri", "skill", "rol", "pozisyon", "başvuru", "basvuru", "mulakat", "mülakat")):
            return {"name": "career", "categories": ["career", "identity", "work_style", "goals"]}
        if any(token in normalized_query for token in ("calisma", "çalışma", "is", "iş", "verimli", "dikkat", "motivasyon")):
            return {"name": "work_style", "categories": ["work_style", "routines", "constraints", "goals", "career"]}
        return {"name": "general", "categories": ["identity", "career", "goals", "communication", "preferences"]}

    def _known_fact_index(self, facts: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
        rows = list(facts or self.store.list_personal_model_facts(self.office_id, include_disabled=False, limit=400))
        index: dict[str, dict[str, Any]] = {}
        for item in rows:
            if bool(item.get("never_use")):
                continue
            fact_key = str(item.get("fact_key") or "").strip()
            if not fact_key:
                continue
            current = index.get(fact_key)
            if current is None or float(item.get("confidence") or 0.0) >= float(current.get("confidence") or 0.0):
                index[fact_key] = item
        return index

    def _prioritize_modules(self, module_keys: list[str], known_index: dict[str, dict[str, Any]] | None = None) -> list[str]:
        known_index = known_index or self._known_fact_index()
        def score_module(module_key: str) -> tuple[float, str]:
            module = INTERVIEW_MODULES.get(module_key) or {}
            score = MODULE_BASE_PRIORITIES.get(module_key, 0.5)
            for question in list(module.get("questions") or []):
                fact_key = str(question.get("fact_key") or "")
                if fact_key and fact_key not in known_index:
                    score += CRITICAL_FACT_PRIORITIES.get(fact_key, 0.4)
            return (-score, module_key)
        return [item for item in sorted(dict.fromkeys(module_keys), key=lambda key: score_module(key))]

    def _estimated_question_total(self, module_keys: list[str], known_index: dict[str, dict[str, Any]] | None = None) -> int:
        known_index = known_index or self._known_fact_index()
        total = 0
        for module_key in module_keys:
            module = INTERVIEW_MODULES.get(module_key) or {}
            for question in list(module.get("questions") or []):
                fact_key = str(question.get("fact_key") or "")
                if fact_key and fact_key in known_index:
                    continue
                total += 1
        return max(total, 1)

    def _question_priority(self, question: dict[str, Any], state: dict[str, Any]) -> float:
        fact_key = str(question.get("fact_key") or "")
        score = CRITICAL_FACT_PRIORITIES.get(fact_key, 0.2)
        known_fact_keys = set((state.get("session_context") or {}).get("known_fact_keys") or []) | set(self._known_fact_index().keys())
        if fact_key and fact_key not in known_fact_keys:
            score += 0.5
        if question.get("choices"):
            score += 0.08
        return score

    def _question_is_already_known(self, question: dict[str, Any], state: dict[str, Any]) -> bool:
        fact_key = str(question.get("fact_key") or "").strip()
        if not fact_key:
            return False
        known_fact_keys = set((state.get("session_context") or {}).get("known_fact_keys") or []) | set(self._known_fact_index().keys())
        return fact_key in known_fact_keys

    def _chat_learning_candidates(self, text: str, *, normalized: str, scope: str) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        directness = self._learning_confidence(normalized)
        sensitive = self._is_sensitive_text(normalized)
        evidence = self._safe_evidence(text, sensitive=sensitive, signal="chat_message")
        if any(token in normalized for token in ("uzun mesajlari sevmem", "uzun mesaj sevmem", "kisa ve net", "kisa yaz", "uzatma", "direkt ol", "madde madde", "kisa cevap")):
            candidates.append(
                self._create_suggestion(
                    source="chat",
                    category="communication",
                    fact_key="communication.style",
                    title="Yanıt tarzı tercihi",
                    prompt="Bunu iletişim tercihin olarak hatırlamamı ister misin?",
                    proposed_value_text="Kısa ve net cevapları tercih ediyor.",
                    scope=scope,
                    confidence=min(0.92, directness + 0.12),
                    evidence=evidence,
                    sensitive=sensitive,
                    metadata={
                        "suggestion_type": "communication_style",
                        "module_key": "communication",
                        "learning_reason": "Mesajında kısa ve net anlatımı açıkça tercih ettiğini söyledin.",
                    },
                )
            )
        if any(token in normalized for token in ("detayli anlat", "detay seviyorum", "ayrintili anlat", "uzun anlat")):
            candidates.append(
                self._create_suggestion(
                    source="chat",
                    category="communication",
                    fact_key="communication.style",
                    title="Yanıt tarzı tercihi",
                    prompt="Bunu iletişim tercihin olarak kaydetmemi ister misin?",
                    proposed_value_text="Detaylı ve açıklayıcı cevapları tercih ediyor.",
                    scope=scope,
                    confidence=min(0.9, directness + 0.1),
                    evidence=evidence,
                    sensitive=sensitive,
                    metadata={
                        "suggestion_type": "communication_style",
                        "module_key": "communication",
                        "learning_reason": "Mesajında daha ayrıntılı açıklama istediğini belirttin.",
                    },
                )
            )
        time_preference = self._detect_time_preference(normalized)
        if time_preference:
            candidates.append(
                self._create_suggestion(
                    source="chat",
                    category="routines",
                    fact_key="work.preferred_time",
                    title="Çalışma zamanı tercihi",
                    prompt="Bunu çalışma düzenin için hatırlamam faydalı olur mu?",
                    proposed_value_text=time_preference,
                    scope=scope,
                    confidence=min(0.9, directness + 0.08),
                    evidence=evidence,
                    sensitive=sensitive,
                    metadata={
                        "suggestion_type": "work_time",
                        "module_key": "work_style",
                        "learning_reason": "Mesajında hangi saatlerde daha iyi çalıştığını anlattın.",
                    },
                )
            )
        reminder_preference = self._detect_reminder_preference(normalized)
        if reminder_preference:
            candidates.append(
                self._create_suggestion(
                    source="chat",
                    category="preferences",
                    fact_key="reminder.tolerance",
                    title="Takip sıklığı tercihi",
                    prompt="Hatırlatma tercihine bunu eklememi ister misin?",
                    proposed_value_text=reminder_preference,
                    scope=scope,
                    confidence=min(0.89, directness + 0.06),
                    evidence=evidence,
                    sensitive=sensitive,
                    metadata={
                        "suggestion_type": "reminder_tolerance",
                        "module_key": "preferences",
                        "learning_reason": "Mesajında ne kadar sık takip istediğini net söyledin.",
                    },
                )
            )
        if any(token in normalized for token in ("hedefim", "amacim", "amacım", "istiyorum")) and any(
            token in normalized for token in ("olmak", "gelistirmek", "geliştirmek", "duzen", "düzen", "ogrenmek", "öğrenmek")
        ):
            candidates.append(
                self._create_suggestion(
                    source="chat",
                    category="goals",
                    fact_key="goal.chat_candidate",
                    title="Yeni hedef sinyali",
                    prompt="Bunu ana hedeflerin arasına eklememi ister misin?",
                    proposed_value_text=_compact_text(text, limit=220),
                    scope=scope,
                    confidence=min(0.9, directness + 0.1),
                    evidence=evidence,
                    sensitive=sensitive,
                    metadata={
                        "suggestion_type": "goal_signal",
                        "module_key": "goals",
                        "learning_reason": "Mesajında ulaşmak istediğin bir hedefi açıkça anlattın.",
                    },
                )
            )
        if any(token in normalized for token in ("planlama", "plan yapmak", "duzen kurmak", "düzen kurmak", "zorlaniyorum", "zorlanıyorum", "ertele")):
            candidates.append(
                self._create_suggestion(
                    source="chat",
                    category="work_style",
                    fact_key="planning.chat_signal",
                    title="Planlama zorluğu sinyali",
                    prompt="Bu planlama notunu ileride sana daha iyi destek olmak için saklamamı ister misin?",
                    proposed_value_text=_compact_text(text, limit=220),
                    scope=scope,
                    confidence=min(0.86, directness + 0.04),
                    evidence=evidence,
                    sensitive=sensitive,
                    metadata={
                        "suggestion_type": "planning_signal",
                        "module_key": "work_style",
                        "learning_reason": "Mesajında planlama veya takip tarafında zorlandığını söyledin.",
                    },
                )
            )
        threshold = 0.64
        return [item for item in candidates if float(item.get("confidence") or 0.0) >= threshold]

    def _learning_confidence(self, normalized: str) -> float:
        confidence = 0.58
        if any(token in normalized for token in ("ben ", "bana ", "beni ", "benim ")):
            confidence += 0.1
        if any(token in normalized for token in ("tercih ederim", "severim", "seviyorum", "sevmem", "isterim", "istemem")):
            confidence += 0.12
        if any(token in normalized for token in ("genelde", "her zaman", "cogu zaman", "çoğu zaman")):
            confidence += 0.05
        if any(token in normalized for token in ("galiba", "sanirim", "sanırım", "bazen", "olabilir")):
            confidence -= 0.08
        return max(0.5, min(0.88, confidence))

    def _is_sensitive_text(self, normalized: str) -> bool:
        return any(token in normalized for token in SENSITIVE_SIGNAL_PATTERNS)

    def _safe_evidence(self, text: str, *, sensitive: bool, signal: str) -> dict[str, Any]:
        if sensitive:
            return {
                "signal": signal,
                "source_text_redacted": True,
                "reason": "sensitive_topic_detected",
            }
        return {
            "signal": signal,
            "source_text": _compact_text(text, limit=220),
        }

    def _detect_time_preference(self, normalized: str) -> str | None:
        if any(token in normalized for token in ("sabah daha verimliyim", "sabah calisirim", "sabah çalışırım", "sabah daha iyiyim")):
            return "Sabah saatlerinde daha verimli çalışıyor."
        if any(token in normalized for token in ("gece calisiyorum", "gece çalışıyorum", "gece daha iyi", "geceleri daha verimliyim")):
            return "Gece saatlerinde daha verimli çalışıyor."
        if any(token in normalized for token in ("aksam daha iyi", "akşam daha iyi", "aksam calisiyorum", "akşam çalışıyorum")):
            return "Akşam saatlerinde daha verimli çalışıyor."
        return None

    def _detect_reminder_preference(self, normalized: str) -> str | None:
        if any(token in normalized for token in ("beni sik hatirlatma", "beni sık hatırlatma", "cok bildirim istemem", "çok bildirim istemem", "cok ping atma", "çok ping atma")):
            return "Hatırlatmaların seyrek ve hafif olmasını tercih ediyor."
        if any(token in normalized for token in ("beni takip et", "beni dürt", "beni durt", "aktif hatirlat", "aktif hatırlat")):
            return "Daha aktif takip ve hatırlatma istiyor."
        return None

    def _suggestion_signature(self, suggestion: dict[str, Any]) -> str:
        return f"{str(suggestion.get('fact_key') or '')}:{_normalize_text(suggestion.get('proposed_value_text'))}"

    def _should_suppress_suggestion(self, candidate: dict[str, Any], *, all_suggestions: list[dict[str, Any]]) -> bool:
        signature = self._suggestion_signature(candidate)
        fact_key = str(candidate.get("fact_key") or "")
        exact_rejections = 0
        fact_key_rejections = 0
        fact_key_accepts = 0
        for item in all_suggestions:
            if str(item.get("fact_key") or "") != fact_key:
                continue
            status = str(item.get("status") or "")
            if self._suggestion_signature(item) == signature and status == "rejected":
                exact_rejections += 1
            if status == "rejected":
                fact_key_rejections += 1
            elif status == "accepted":
                fact_key_accepts += 1
        if exact_rejections >= 1:
            return True
        if fact_key_rejections >= 3 and fact_key_accepts == 0:
            return True
        adjusted = float(candidate.get("confidence") or 0.0) + min(0.08, fact_key_accepts * 0.02) - min(0.12, fact_key_rejections * 0.03)
        candidate["confidence"] = max(0.35, min(0.94, adjusted))
        return False

    @staticmethod
    def _selection_reason_label(reason: str) -> str:
        mapping = {
            "intent_category_match": "İsteğinle doğrudan ilgili",
            "fallback_profile_context": "Genel profil desteği",
            "semantic_overlap": "Cümlendeki ipuçlarıyla örtüşüyor",
            "explicit_memory": "Bunu sen açıkça söyledin",
            "approved_inference": "Daha önce onaylanan çıkarım",
            "global_scope": "Genel profilinde geçerli",
        }
        return mapping.get(reason, reason)

    def _session_payload(self, session: dict[str, Any] | None) -> dict[str, Any] | None:
        if not session:
            return None
        state = dict(session.get("state") or {})
        current_question = self._next_question(state)
        return {
            "id": session.get("id"),
            "scope": session.get("scope"),
            "source": session.get("source"),
            "module_keys": list(session.get("module_keys") or []),
            "status": session.get("status"),
            "started_at": session.get("started_at"),
            "paused_at": session.get("paused_at"),
            "completed_at": session.get("completed_at"),
            "updated_at": session.get("updated_at"),
            "progress": dict(session.get("progress") or {}),
            "summary": dict(session.get("summary") or {}),
            "session_context": dict(state.get("session_context") or {}),
            "current_question": self._question_payload(current_question),
        }

    @staticmethod
    def _question_payload(question: dict[str, Any] | None) -> dict[str, Any] | None:
        if not question:
            return None
        return {
            "id": question.get("id"),
            "module_key": question.get("module_key"),
            "prompt": question.get("prompt"),
            "title": question.get("title"),
            "help_text": question.get("help_text"),
            "examples": list(question.get("examples") or []),
            "choices": list(question.get("choices") or []),
            "category": question.get("category"),
            "fact_key": question.get("fact_key"),
            "input_mode": "choice" if question.get("choices") else "text",
            "skippable": True,
            "supports_voice_future": True,
        }

    def _collect_external_profile_learning_sources(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        providers: set[str] = set()
        email_threads = list(self.store.list_email_threads(self.office_id, provider="google", limit=12) or [])
        email_threads.extend(list(self.store.list_email_threads(self.office_id, provider="outlook", limit=12) or []))
        for thread in sorted(
            email_threads,
            key=lambda item: str(item.get("received_at") or item.get("updated_at") or ""),
            reverse=True,
        )[:16]:
            provider = str(thread.get("provider") or "email")
            providers.add(provider)
            sender = _compact_text((thread.get("metadata") or {}).get("sender") or (list(thread.get("participants") or []) or [""])[0], limit=120)
            subject = _compact_text(thread.get("subject"), limit=180)
            snippet = _compact_text(thread.get("snippet"), limit=260)
            if not subject and not snippet:
                continue
            if not _looks_like_external_profile_email_signal(sender=sender, subject=subject, snippet=snippet):
                continue
            items.append(
                {
                    "id": f"email:{provider}:{thread.get('thread_ref')}",
                    "source_kind": "connector",
                    "provider": provider,
                    "label": f"{'Gmail' if provider == 'google' else 'Outlook'} e-postası",
                    "sort_at": str(thread.get("received_at") or thread.get("updated_at") or ""),
                    "text": _compact_text(
                        "\n".join(
                            part
                            for part in (
                                f"Gönderen: {sender}" if sender else "",
                                f"Konu: {subject}" if subject else "",
                                f"Özet: {snippet}" if snippet else "",
                            )
                            if part
                        ),
                        limit=700,
                    ),
                }
            )
        channel_collectors = (
            ("whatsapp", self.store.list_whatsapp_messages, "WhatsApp"),
            ("telegram", self.store.list_telegram_messages, "Telegram"),
            ("instagram", self.store.list_instagram_messages, "Instagram"),
            ("linkedin", self.store.list_linkedin_messages, "LinkedIn"),
            ("x", self.store.list_x_messages, "X"),
        )
        for provider, loader, label in channel_collectors:
            messages = list(loader(self.office_id, limit=12) or [])
            for message in messages[:12]:
                providers.add(provider)
                body = _compact_text(message.get("body"), limit=320)
                if not body:
                    continue
                direction = str(message.get("direction") or "inbound")
                if not _looks_like_user_owned_profile_message(body=body, direction=direction):
                    continue
                actor = _compact_text(
                    (message.get("metadata") or {}).get("chat_name")
                    or (message.get("metadata") or {}).get("contact_name")
                    or message.get("sender")
                    or message.get("recipient"),
                    limit=120,
                )
                items.append(
                    {
                        "id": f"message:{provider}:{message.get('message_ref')}",
                        "source_kind": "connector",
                        "provider": provider,
                        "label": f"{label} mesajı",
                        "sort_at": str(message.get("sent_at") or message.get("updated_at") or ""),
                        "text": _compact_text(
                            "\n".join(
                                part
                                for part in (
                                    f"Yön: {'kullanıcının gönderdiği mesaj' if direction == 'outbound' else 'kullanıcıya gelen mesaj'}",
                                    f"Kişi: {actor}" if actor else "",
                                    f"İçerik: {body}",
                                )
                                if part
                            ),
                            limit=700,
                        ),
                    }
                )
        document_items = self._collect_external_profile_documents()
        for item in document_items:
            providers.add("workspace")
            items.append(item)
        items.sort(key=lambda item: str(item.get("sort_at") or ""), reverse=True)
        return {
            "items": items[:28],
            "providers": sorted(providers),
            "document_count": len(document_items),
        }

    def _collect_external_profile_documents(self) -> list[dict[str, Any]]:
        root = self.store.get_active_workspace_root(self.office_id)
        if not root:
            return []
        workspace_root_id = int(root.get("id") or 0)
        if workspace_root_id <= 0:
            return []
        candidates: dict[int, dict[str, Any]] = {}
        for hint in EXTERNAL_PROFILE_DOCUMENT_HINTS:
            for item in self.store.list_workspace_documents(
                self.office_id,
                workspace_root_id,
                query_text=hint,
                status="indexed",
                limit=6,
                include_chunk_count=True,
            ):
                candidates[int(item.get("id") or 0)] = item
        if not candidates:
            for item in self.store.list_workspace_documents(
                self.office_id,
                workspace_root_id,
                status="indexed",
                limit=60,
                include_chunk_count=True,
            ):
                joined_name = _normalize_text(f"{item.get('display_name') or ''} {item.get('relative_path') or ''}")
                if any(hint in joined_name for hint in EXTERNAL_PROFILE_DOCUMENT_HINTS):
                    candidates[int(item.get("id") or 0)] = item
        items: list[dict[str, Any]] = []
        for document in list(candidates.values())[:3]:
            document_id = int(document.get("id") or 0)
            if document_id <= 0:
                continue
            chunks = list(self.store.list_workspace_document_chunks(self.office_id, document_id) or [])
            chunk_text = _compact_text(" ".join(str(chunk.get("text") or "") for chunk in chunks[:8]), limit=4000)
            if not chunk_text:
                continue
            display_name = _compact_text(document.get("display_name") or document.get("relative_path"), limit=120)
            items.append(
                {
                    "id": f"document:{document_id}",
                    "source_kind": "document",
                    "provider": "workspace",
                    "label": f"Belge: {display_name}",
                    "sort_at": str(document.get("updated_at") or document.get("created_at") or ""),
                    "text": _compact_text(
                        "\n".join(
                            part
                            for part in (
                                f"Dosya: {display_name}" if display_name else "",
                                chunk_text,
                            )
                            if part
                        ),
                        limit=4200,
                    ),
                }
            )
        return items

    def _derive_external_profile_facts(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        runtime_facts = self._derive_external_profile_facts_with_runtime(items)
        if runtime_facts:
            return runtime_facts
        return self._derive_external_profile_facts_with_fallback(items)

    def _derive_external_profile_facts_with_runtime(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.runtime is None or not bool(getattr(self.runtime, "enabled", False)):
            return []
        rendered_sources = []
        for item in items[:14]:
            rendered_sources.append(
                "\n".join(
                    [
                        f"Kaynak ID: {item.get('id')}",
                        f"Tür: {item.get('label')}",
                        str(item.get("text") or ""),
                    ]
                )
            )
        prompt = (
            "Kullanıcının bağlı hesapları ve belgelerinden kişisel profil için işe yarar, kompakt ve kalıcı factler çıkar.\n"
            "Kurallar:\n"
            "- Yalnız kullanıcı hakkında çıkarım yap.\n"
            "- Gizli veri, e-posta adresi, telefon, tam adres, parola, kimlik numarası yazma.\n"
            "- Geçici sohbetleri değil, işe yarar ve yeniden kullanılabilir kişisel/profesyonel sinyalleri çıkar.\n"
            "- En fazla 5 fact üret.\n"
            "- Yalnız şu fact_key değerlerini kullan: "
            + ", ".join(EXTERNAL_PROFILE_ALLOWED_FACT_KEYS)
            + "\n"
            "- category yalnız identity veya career olsun.\n"
            "- value_text Türkçe, net ve kısa olsun.\n"
            "- confidence 0.0 ile 1.0 arasında olsun.\n"
            "Çıktı yalnız JSON olsun:\n"
            "{\n"
            '  "facts": [\n'
            "    {\n"
            '      "category": "career",\n'
            '      "fact_key": "career.profile_summary",\n'
            '      "title": "Profesyonel profil",\n'
            '      "value_text": "…",\n'
            '      "confidence": 0.78,\n'
            '      "evidence_refs": ["email:google:abc", "document:12"]\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Kaynaklar:\n"
            + "\n\n".join(rendered_sources)
        )
        try:
            completion = self.runtime.complete(
                prompt,
                self.events,
                task="personal_model_external_profile_learning",
                source_count=len(rendered_sources),
            )
        except Exception:  # noqa: BLE001
            return []
        payload = self._extract_json_object_from_text(str((completion or {}).get("text") or ""))
        if not payload:
            return []
        facts = []
        source_map = {str(item.get("id") or ""): item for item in items}
        for raw in list(payload.get("facts") or [])[:5]:
            if not isinstance(raw, dict):
                continue
            fact_key = str(raw.get("fact_key") or "").strip()
            if fact_key not in EXTERNAL_PROFILE_ALLOWED_FACT_KEYS:
                continue
            value_text = _compact_text(raw.get("value_text"), limit=260)
            if not value_text:
                continue
            evidence_refs = [
                str(value).strip()
                for value in list(raw.get("evidence_refs") or [])
                if str(value).strip() in source_map
            ]
            facts.append(
                self._build_external_fact_record(
                    category=str(raw.get("category") or "career").strip().lower() or "career",
                    fact_key=fact_key,
                    title=_compact_text(raw.get("title") or self._external_fact_title(fact_key), limit=80),
                    value_text=value_text,
                    confidence=max(0.45, min(0.95, float(raw.get("confidence") or 0.72))),
                    evidence_refs=evidence_refs,
                    source_map=source_map,
                )
            )
        deduped: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for fact in facts:
            if str(fact.get("fact_key") or "") in seen_keys:
                continue
            seen_keys.add(str(fact.get("fact_key") or ""))
            deduped.append(fact)
        return deduped

    def _derive_external_profile_facts_with_fallback(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        source_map = {str(item.get("id") or ""): item for item in items}
        normalized_text = _normalize_text("\n".join(str(item.get("text") or "") for item in items))
        document_refs = [str(item.get("id") or "") for item in items if str(item.get("source_kind") or "") == "document"]
        connector_refs = [str(item.get("id") or "") for item in items if str(item.get("source_kind") or "") == "connector"]
        skills = []
        for term in EXTERNAL_PROFILE_SKILL_TERMS:
            if term in normalized_text:
                label = term.replace("next.js", "Next.js").replace("node.js", "Node.js").replace("gcp", "GCP").replace("aws", "AWS")
                if label.upper() not in {"SQL SERVER"}:
                    label = label.replace("sql server", "SQL Server").replace("openai", "OpenAI").replace("gemini", "Gemini")
                if label not in skills:
                    skills.append(label)
        roles = []
        for term in EXTERNAL_PROFILE_ROLE_TERMS:
            if term in normalized_text:
                label = " ".join(part.capitalize() for part in term.split())
                if label not in roles:
                    roles.append(label)
        application_signal = any(term in normalized_text for term in EXTERNAL_PROFILE_APPLICATION_TERMS)
        facts: list[dict[str, Any]] = []
        if document_refs:
            facts.append(
                self._build_external_fact_record(
                    category="career",
                    fact_key="career.document_signal",
                    title="Belge sinyali",
                    value_text="Çalışma klasöründe CV/özgeçmiş benzeri belge bulundu; profesyonel profil çıkarımı bu belgelerden de besleniyor.",
                    confidence=0.82,
                    evidence_refs=document_refs[:3],
                    source_map=source_map,
                )
            )
        if roles or skills:
            detail_parts = []
            if roles:
                detail_parts.append(f"Öne çıkan yönelim: {', '.join(roles[:3])}.")
            if skills:
                detail_parts.append(f"Baskın araç ve beceriler: {', '.join(skills[:6])}.")
            facts.append(
                self._build_external_fact_record(
                    category="career",
                    fact_key="career.profile_summary",
                    title="Profesyonel profil",
                    value_text=_compact_text(" ".join(detail_parts), limit=260),
                    confidence=0.74 if document_refs else 0.62,
                    evidence_refs=(document_refs + connector_refs)[:4],
                    source_map=source_map,
                )
            )
        if skills:
            facts.append(
                self._build_external_fact_record(
                    category="career",
                    fact_key="career.skill_summary",
                    title="Beceri özeti",
                    value_text=_compact_text(f"Öne çıkan beceriler: {', '.join(skills[:8])}.", limit=220),
                    confidence=0.71 if document_refs else 0.6,
                    evidence_refs=(document_refs + connector_refs)[:4],
                    source_map=source_map,
                )
            )
        if application_signal:
            facts.append(
                self._build_external_fact_record(
                    category="career",
                    fact_key="career.application_activity",
                    title="Başvuru sinyali",
                    value_text="E-posta, mesaj veya belge kayıtlarında CV paylaşımı, başvuru ya da mülakat süreci sinyali görünüyor.",
                    confidence=0.68,
                    evidence_refs=(connector_refs + document_refs)[:4],
                    source_map=source_map,
                )
            )
        if roles:
            facts.append(
                self._build_external_fact_record(
                    category="identity",
                    fact_key="identity.professional_focus",
                    title="Profesyonel odak",
                    value_text=_compact_text(f"Kayıtlarda kullanıcı daha çok {', '.join(roles[:2])} çizgisinde konumlanıyor.", limit=200),
                    confidence=0.66,
                    evidence_refs=(document_refs + connector_refs)[:4],
                    source_map=source_map,
                )
            )
        return facts[:5]

    def _build_external_fact_record(
        self,
        *,
        category: str,
        fact_key: str,
        title: str,
        value_text: str,
        confidence: float,
        evidence_refs: list[str],
        source_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        source_labels = []
        source_kinds = set()
        for ref in evidence_refs:
            item = source_map.get(ref) or {}
            label = _compact_text(item.get("label"), limit=80)
            if label and label not in source_labels:
                source_labels.append(label)
            kind = str(item.get("source_kind") or "").strip().lower()
            if kind:
                source_kinds.add(kind)
        if source_kinds == {"document"}:
            source_kind = "document_extracted"
            basis = "document_extracted"
        elif source_kinds == {"connector"}:
            source_kind = "connector_observed"
            basis = "connector_observed"
        else:
            source_kind = "connector_profile_learning"
            basis = "connector_observed"
        return {
            "fact_id": f"pmf-external-{_slugify(fact_key)}",
            "category": category if category in {"identity", "career"} else "career",
            "fact_key": fact_key,
            "title": title or self._external_fact_title(fact_key),
            "value_text": value_text,
            "value_json": {"text": value_text, "evidence_refs": evidence_refs[:6]},
            "confidence": max(0.45, min(0.95, confidence)),
            "source_kind": source_kind,
            "basis": basis,
            "metadata": {
                "source_kind": source_kind,
                "source_labels": source_labels[:6],
                "evidence_refs": evidence_refs[:6],
                "learning_pipeline": "external_profile_learning_v1",
                "auto_generated": True,
                "user_confirmed": False,
            },
        }

    def _store_external_profile_fact(self, fact: dict[str, Any]) -> dict[str, Any] | None:
        fact_key = str(fact.get("fact_key") or "").strip()
        if not fact_key:
            return None
        stored = self.store.upsert_personal_model_fact(
            self.office_id,
            fact_id=str(fact.get("fact_id") or f"pmf-external-{_slugify(fact_key)}"),
            session_id=None,
            category=str(fact.get("category") or "career"),
            fact_key=fact_key,
            title=str(fact.get("title") or self._external_fact_title(fact_key)),
            value_text=str(fact.get("value_text") or ""),
            value_json=dict(fact.get("value_json") or {}),
            confidence=float(fact.get("confidence") or 0.65),
            confidence_type="inferred",
            source_entry_id=None,
            visibility="assistant_visible",
            scope="global",
            sensitive=False,
            enabled=True,
            never_use=False,
            metadata=dict(fact.get("metadata") or {}),
        )
        self._sync_fact_epistemics(
            fact=stored,
            raw_entry=None,
            source_kind=str(fact.get("source_kind") or "connector_profile_learning"),
            basis=str(fact.get("basis") or "connector_observed"),
            validation_state="connector_observed",
        )
        return stored

    @staticmethod
    def _external_fact_title(fact_key: str) -> str:
        return {
            "identity.professional_focus": "Profesyonel odak",
            "career.profile_summary": "Profesyonel profil",
            "career.skill_summary": "Beceri özeti",
            "career.application_activity": "Başvuru sinyali",
            "career.document_signal": "Belge sinyali",
        }.get(fact_key, "Profil sinyali")

    @staticmethod
    def _extract_json_object_from_text(text: str) -> dict[str, Any] | None:
        cleaned = str(text or "").strip()
        if not cleaned:
            return None
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            cleaned = fenced.group(1).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _fact_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(item.get("metadata") or {})
        sensitive = bool(item.get("sensitive"))
        confidence = float(item.get("confidence") or 0.0)
        scope = str(item.get("scope") or "global")
        source_kind = str(metadata.get("source_kind") or metadata.get("source") or "")
        resolution_status = "unknown"
        claim_id = ""
        claim_basis = ""
        claim_support_strength = ""
        claim_support_contaminated = False
        claim_retrieval_eligibility = ""
        if self.epistemic is not None:
            try:
                resolution = self.epistemic.resolve_claim(
                    subject_key="user",
                    predicate=str(item.get("fact_key") or ""),
                    scope=scope,
                    include_blocked=True,
                )
                resolution_status = str(resolution.get("status") or "unknown")
                current_claim = resolution.get("current_claim") if isinstance(resolution, dict) else None
                claim_id = str((current_claim or {}).get("id") or "")
                claim_basis = str((current_claim or {}).get("epistemic_basis") or "")
                current_support = resolution.get("current_claim_support") if isinstance(resolution, dict) else None
                claim_support_strength = str((current_support or {}).get("support_strength") or "")
                claim_support_contaminated = bool((current_support or {}).get("contaminated"))
                claim_retrieval_eligibility = str((current_claim or {}).get("retrieval_eligibility") or "")
            except Exception:  # noqa: BLE001
                resolution_status = "unknown"
        claim_basis_label = {
            "user_explicit": "kullanıcı bilgisi",
            "user_confirmed_inference": "onaylı çıkarım",
            "connector_observed": "kaynak gözlemi",
            "document_extracted": "belge kaynağı",
            "assistant_generated": "asistan kaydı",
        }.get(claim_basis, "profil bilgisi")
        resolution_label = {
            "current": "Şu an geçerli bilgi olarak kullanılıyor",
            "contested": "Bu bilgiyle çelişen başka kayıtlar da var",
            "unknown": "Bu bilgi için çözüm durumu netleşmedi",
        }.get(resolution_status, resolution_status)
        return {
            "id": item.get("id"),
            "category": item.get("category"),
            "fact_key": item.get("fact_key"),
            "title": item.get("title"),
            "value_text": item.get("value_text"),
            "value_json": dict(item.get("value_json") or {}),
            "confidence": item.get("confidence"),
            "confidence_percent": round(confidence * 100),
            "confidence_label": f"Bu bilgiden %{round(confidence * 100)} eminiz." if confidence > 0 else "Bu bilgi henüz zayıf.",
            "confidence_type": item.get("confidence_type"),
            "source_entry_id": item.get("source_entry_id"),
            "visibility": item.get("visibility"),
            "scope": item.get("scope"),
            "scope_label": {
                "personal": "Sadece özel hayatında kullanılacak",
                "workspace": "Çalışma alanında kullanılacak",
                "global": "Genel profilinde kullanılacak",
            }.get(scope, scope),
            "sensitive": bool(item.get("sensitive")),
            "enabled": bool(item.get("enabled")),
            "never_use": bool(item.get("never_use")),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "learned_at_label": item.get("updated_at") or item.get("created_at"),
            "why_known": "Bu bilgi kullanıcı tarafından açıkça verildi."
            if str(item.get("confidence_type") or "") == "explicit"
            else "Bu bilgi bir sohbetten çıkarıldı ve kullanıcı onayıyla kaydedildi.",
            "usage_label": "Bu bilgi yanıtlarda hiç kullanılmayacak."
            if bool(item.get("never_use"))
            else ("Bu bilgi hassas olduğu için yanıtlara otomatik girmez." if sensitive else "Yalnız ilgili olduğunda kullanılır."),
            "source_summary": "Kaynak özeti hassas olduğu için gizli."
            if sensitive
            else (
                "Görüşme cevabından öğrenildi."
                if source_kind == "guided_interview"
                else (
                    "Sohbet sırasında fark edildi ve onaylandı."
                    if source_kind == "chat"
                    else (
                        f"Bağlı hesaplardan gözlemlendi: {', '.join(list(metadata.get('source_labels') or [])[:3])}."
                        if source_kind == "connector_observed" and list(metadata.get("source_labels") or [])
                        else (
                            f"Belgelerden çıkarıldı: {', '.join(list(metadata.get('source_labels') or [])[:2])}."
                            if source_kind == "document_extracted" and list(metadata.get("source_labels") or [])
                            else (
                                f"Bağlı hesaplar ve belgeler birlikte değerlendirildi: {', '.join(list(metadata.get('source_labels') or [])[:4])}."
                                if source_kind == "connector_profile_learning" and list(metadata.get("source_labels") or [])
                                else "Kayıt geçmişinden türetildi."
                            )
                        )
                    )
                )
            ),
            "epistemic_status": resolution_status,
            "epistemic_status_label": resolution_label,
            "epistemic_claim_id": claim_id or None,
            "epistemic_basis": claim_basis or None,
            "epistemic_basis_label": claim_basis_label,
            "epistemic_support_strength": claim_support_strength or None,
            "epistemic_support_contaminated": claim_support_contaminated,
            "epistemic_retrieval_eligibility": claim_retrieval_eligibility or None,
            "metadata": metadata,
        }

    @staticmethod
    def _raw_entry_payload(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "session_id": item.get("session_id"),
            "module_key": item.get("module_key"),
            "question_id": item.get("question_id"),
            "question_text": item.get("question_text"),
            "answer_text": item.get("answer_text"),
            "answer_kind": item.get("answer_kind"),
            "answer_value": dict(item.get("answer_value") or {}),
            "source": item.get("source"),
            "confidence_type": item.get("confidence_type"),
            "confidence": item.get("confidence"),
            "explicit": bool(item.get("explicit")),
            "created_at": item.get("created_at"),
            "metadata": dict(item.get("metadata") or {}),
        }

    @staticmethod
    def _suggestion_payload(item: dict[str, Any] | None) -> dict[str, Any] | None:
        if not item:
            return None
        confidence = float(item.get("confidence") or 0.0)
        metadata = dict(item.get("metadata") or {})
        sensitive = bool(item.get("sensitive"))
        return {
            "id": item.get("id"),
            "source": item.get("source"),
            "category": item.get("category"),
            "fact_key": item.get("fact_key"),
            "title": item.get("title"),
            "prompt": item.get("prompt"),
            "proposed_value_text": item.get("proposed_value_text"),
            "proposed_value_json": dict(item.get("proposed_value_json") or {}),
            "confidence": item.get("confidence"),
            "confidence_percent": round(confidence * 100),
            "confidence_label": f"Bu çıkarımdan %{round(confidence * 100)} eminiz.",
            "scope": item.get("scope"),
            "sensitive": bool(item.get("sensitive")),
            "status": item.get("status"),
            "evidence": {"source_text_redacted": True} if sensitive else dict(item.get("evidence") or {}),
            "learning_reason": str(metadata.get("learning_reason") or "Mesajından bir eğilim fark edildi."),
            "why_asked": "Kalıcı olarak hatırlamadan önce onayını istiyoruz.",
            "metadata": metadata,
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }

    def _log(self, event: str, **payload: Any) -> None:
        if self.events is None:
            return
        try:
            self.events.log(event, **payload)
        except Exception:  # noqa: BLE001
            return

    def _sync_fact_epistemics(
        self,
        *,
        fact: dict[str, Any],
        raw_entry: dict[str, Any] | None,
        source_kind: str,
        basis: str,
        validation_state: str,
    ) -> None:
        try:
            if self.memory_mutations is not None:
                self.memory_mutations.sync_personal_fact(
                    fact=fact,
                    raw_entry=raw_entry,
                    source_kind=source_kind,
                    basis=basis,
                    validation_state=validation_state,
                )
            elif self.epistemic is not None:
                self.epistemic.sync_personal_fact(
                    fact=fact,
                    raw_entry=raw_entry,
                    source_kind=source_kind,
                    basis=basis,
                    validation_state=validation_state,
                )
        except Exception:  # noqa: BLE001
            return

    def _retire_fact_claims(self, fact: dict[str, Any], *, reason: str) -> None:
        try:
            if self.memory_mutations is not None:
                self.memory_mutations.retire_personal_fact_claims(fact=fact, reason=reason)
                return
        except Exception:  # noqa: BLE001
            return
        if self.epistemic is None:
            return
        claims = self.store.list_epistemic_claims(
            self.office_id,
            subject_key="user",
            predicate=str(fact.get("fact_key") or ""),
            scope=str(fact.get("scope") or "global"),
            include_blocked=True,
            limit=50,
        )
        for claim in claims:
            if str(((claim.get("metadata") or {}).get("fact_id") or "")) != str(fact.get("id") or ""):
                continue
            try:
                self.store.update_epistemic_claim(
                    self.office_id,
                    str(claim.get("id") or ""),
                    validation_state="superseded",
                    retrieval_eligibility="blocked",
                    valid_to=_iso_now(),
                    metadata={"retired_reason": reason},
                )
            except Exception:  # noqa: BLE001
                continue

    def _reconcile_profile(self, *, authority: str, reason: str) -> dict[str, Any] | None:
        if self.memory_mutations is None:
            return None
        try:
            return self.memory_mutations.reconcile_user_profile(authority=authority, reason=reason)
        except Exception:  # noqa: BLE001
            return None
