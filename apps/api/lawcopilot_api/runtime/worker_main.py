from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..epistemic.service import EpistemicService
from ..knowledge_base.service import KnowledgeBaseService
from ..persistence import Persistence


def _execute(job_type: str, *, payload: dict[str, Any], db_path: str, kb_root: str, office_id: str) -> dict[str, Any]:
    settings = get_settings()
    store = Persistence(Path(db_path))
    epistemic = EpistemicService(store, office_id)
    knowledge_base = KnowledgeBaseService(
        Path(kb_root),
        office_id,
        epistemic=epistemic,
        enabled=True,
        search_backend=settings.personal_kb_search_backend,
        dense_candidates_enabled=settings.personal_kb_dense_candidates_enabled,
        semantic_backend=str(settings.personal_kb_semantic_backend or "heuristic"),
        embedding_model_name=str(
            settings.personal_kb_embedding_model_name or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
        cross_encoder_model_name=str(
            settings.personal_kb_cross_encoder_model_name or "cross-encoder/ms-marco-MiniLM-L-6-v2"
        ),
        reranker_mode=settings.personal_kb_reranker_mode,
    )
    normalized_job_type = str(job_type or "").strip().lower()
    if normalized_job_type == "wiki_compile":
        result = knowledge_base.compile_wiki_brain(
            reason=str(payload.get("reason") or "queued_wiki_compile"),
            previews=bool(payload.get("previews")),
        )
        return {
            "job_type": "wiki_compile",
            "reason": str(payload.get("reason") or "queued_wiki_compile"),
            "concept_count": result.get("concept_count"),
            "updated_pages": list(result.get("updated_pages") or []),
        }
    if normalized_job_type == "knowledge_synthesis":
        result = knowledge_base.run_knowledge_synthesis(
            reason=str(payload.get("reason") or "queued_knowledge_synthesis")
        )
        return {
            "job_type": "knowledge_synthesis",
            "reason": str(payload.get("reason") or "queued_knowledge_synthesis"),
            "summary": dict(result.get("summary") or {}),
        }
    if normalized_job_type == "reflection":
        result = knowledge_base.run_reflection()
        return {
            "job_type": "reflection",
            "generated_at": result.get("generated_at"),
            "health_status": result.get("health_status"),
        }
    if normalized_job_type == "orchestration":
        result = knowledge_base.run_orchestration(
            store=store,
            settings=settings,
            job_names=list(payload.get("job_names") or []),
            reason=str(payload.get("reason") or "queued_orchestration"),
            force=bool(payload.get("force")),
        )
        return {
            "job_type": "orchestration",
            "reason": str(payload.get("reason") or "queued_orchestration"),
            "summary": dict((result.get("status") or {}).get("summary") or {}),
        }
    raise ValueError(f"Unsupported runtime job type: {job_type}")


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw or "{}")
        result = _execute(
            str(payload.get("job_type") or ""),
            payload=dict(payload.get("payload") or {}),
            db_path=str(payload.get("db_path") or ""),
            kb_root=str(payload.get("kb_root") or ""),
            office_id=str(payload.get("office_id") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    sys.stdout.write(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
