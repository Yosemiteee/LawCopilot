from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import threading
import time
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException

from .audit import AuditLogger
from .auth import parse_token, issue_token, require_role
from .config import get_settings, load_model_profiles, resolve_repo_path
from .connectors.safety import ConnectorPolicy, ConnectorSafetyWrapper
from .model_router import ModelRouter
from .observability import StructuredLogger
from .persistence import Persistence
from .rag import build_persisted_chunks, create_rag_store, score_chunk_records
from .schemas import (
    QueryIn,
    QueryJobCreateRequest,
    TokenRequest,
    ConnectorPreviewRequest,
    MatterCreateRequest,
    MatterUpdateRequest,
    MatterNoteCreateRequest,
    MatterDraftCreateRequest,
    MatterDraftGenerateRequest,
    MatterSearchRequest,
    WorkspaceRootRequest,
    WorkspaceScanRequest,
    WorkspaceSearchRequest,
    SimilarDocumentsRequest,
    WorkspaceAttachRequest,
    TaskCreateRequest,
    TaskBulkCompleteRequest,
    TaskStatusUpdateRequest,
    TaskDueUpdateRequest,
    CitationReviewRequest,
    EmailDraftCreateRequest,
    EmailDraftApproveRequest,
    EmailDraftRetractRequest,
    SocialIngestRequest,
)
from .workflows import build_activity_stream, build_chronology, build_risk_notes, build_task_recommendations, generate_matter_draft
from .workspace import (
    build_workspace_chunks,
    build_workspace_search_result,
    resolve_workspace_child,
    root_hash,
    scan_workspace_tree,
    validate_workspace_root,
)
from .similarity import find_similar_documents


def _safe_excerpt(value: str, max_len: int = 120) -> str:
    return value[:max_len].replace("\n", " ")


def _extract_text(content: bytes) -> str:
    text = content.decode("utf-8", errors="ignore").strip()
    if text:
        return text
    text = content.decode("latin-1", errors="ignore").strip()
    if text:
        return text
    raise ValueError("Dosya içeriği okunamadı.")


def _support_level(citations: list[dict]) -> str:
    if not citations:
        return "none"
    top = max(float(item.get("relevance_score", 0.0)) for item in citations)
    if top >= 0.26 and len(citations) >= 2:
        return "high"
    if top >= 0.16:
        return "medium"
    return "low"


def _citation_view(citation: dict, index: int | None = None) -> dict:
    payload = {
        "document_id": citation.get("document_id"),
        "document_name": citation.get("document_name"),
        "matter_id": citation.get("matter_id"),
        "chunk_id": citation.get("chunk_id"),
        "chunk_index": citation.get("chunk_index"),
        "excerpt": citation.get("excerpt"),
        "relevance_score": citation.get("relevance_score"),
        "source_type": citation.get("source_type"),
        "support_type": citation.get("support_type"),
        "confidence": citation.get("confidence"),
        "line_anchor": citation.get("line_anchor"),
        "page": citation.get("page"),
        "line_start": citation.get("line_start"),
        "line_end": citation.get("line_end"),
    }
    if index is not None:
        payload["index"] = index
        payload["label"] = f"[{index}]"
    return payload


def _matter_search_result(
    *,
    matter_id: int,
    payload: MatterSearchRequest,
    role: str,
    subject: str,
    sid: str,
    router: ModelRouter,
    store: Persistence,
    rag_meta: dict,
    audit: AuditLogger,
    office_id: str,
) -> dict:
    selected = router.choose(payload.query, payload.model_profile)
    rows = store.search_document_chunks(
        office_id,
        matter_id,
        document_ids=payload.document_ids,
        source_types=payload.source_types,
        filename_contains=payload.filename_contains,
    )
    if rows is None:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
    linked_workspace_rows = store.search_linked_workspace_chunks(office_id, matter_id) or []
    rows = rows + linked_workspace_rows

    citations = score_chunk_records(payload.query, rows, k=payload.limit)
    support_level = _support_level(citations)
    manual_review_required = support_level in {"none", "low"}
    related_documents_map: dict[int, dict] = {}
    for citation in citations:
        document_id = int(citation["document_id"])
        current = related_documents_map.get(document_id)
        if current is None or float(citation["relevance_score"]) > float(current["max_score"]):
            related_documents_map[document_id] = {
                "document_id": document_id,
                "document_name": citation["document_name"],
                "matter_id": matter_id,
                "max_score": citation["relevance_score"],
                "reason": "Aynı dosya kapsamında sorguyla örtüşen pasaj bulundu.",
            }

    related_documents = sorted(related_documents_map.values(), key=lambda item: item["max_score"], reverse=True)
    coverage = round(min(1.0, sum(float(c["relevance_score"]) for c in citations[:3])), 2) if citations else 0.0
    if citations:
        answer = (
            f"Bu dosya kapsamında {len(related_documents)} belge ve {len(citations)} destekleyici pasaj bulundu. "
            f"En güçlü dayanak: {citations[0]['document_name']}."
        )
    else:
        answer = "Bu dosya kapsamında sorguyu doğrudan destekleyen bir kaynak bulunamadı."

    audit_seed = f"matter:{matter_id}:{payload.query}:{subject}:{selected['profile']}"
    audit_id = hashlib.sha256(audit_seed.encode()).hexdigest()[:16]
    audit.log(
        "matter_search",
        subject=subject,
        role=role,
        session_id=sid,
        matter_id=matter_id,
        audit_id=audit_id,
        source_count=len(citations),
        document_count=len(related_documents),
    )
    return {
        "answer": answer,
        "model_profile": selected["profile"],
        "routing": selected,
        "support_level": support_level,
        "manual_review_required": manual_review_required,
        "citation_count": len(citations),
        "source_coverage": coverage,
        "generated_from": "matter_document_memory",
        "citations": [_citation_view(citation, index) for index, citation in enumerate(citations, start=1)],
        "ui_citations": [_citation_view(citation, index) for index, citation in enumerate(citations, start=1)],
        "related_documents": related_documents[:3],
        "retrieval_summary": {
            "scope": "matter",
            "matter_id": matter_id,
            "document_count": len(related_documents),
            "citation_count": len(citations),
            "top_document": citations[0]["document_name"] if citations else None,
            "warning": "Kaynak kapsami dusuk; manuel inceleme onerilir." if manual_review_required else None,
        },
        "rag_runtime": rag_meta,
        "security": {
            "role_checked": role,
            "subject": subject,
            "office_id": office_id,
            "matter_id": matter_id,
            "audit_id": audit_id,
            "retrieval_authorized": True,
        },
    }


def _load_matter_workflow_context(store: Persistence, office_id: str, matter_id: int) -> dict | None:
    matter = store.get_matter(matter_id, office_id)
    if not matter:
        return None
    workspace_documents = store.list_matter_workspace_documents(office_id, matter_id) or []
    workspace_chunks = store.search_linked_workspace_chunks(office_id, matter_id) or []
    return {
        "matter": matter,
        "notes": store.list_matter_notes(office_id, matter_id) or [],
        "documents": (store.list_matter_documents(office_id, matter_id) or []) + workspace_documents,
        "chunks": (store.search_document_chunks(office_id, matter_id) or []) + workspace_chunks,
        "tasks": store.list_matter_tasks(office_id, matter_id) or [],
        "timeline": store.list_matter_timeline(office_id, matter_id) or [],
        "draft_events": store.list_matter_draft_events(office_id, matter_id) or [],
        "ingestion_jobs": store.list_matter_ingestion_jobs(office_id, matter_id) or [],
        "workspace_documents": workspace_documents,
        "workspace_chunks": workspace_chunks,
    }


def _require_active_workspace_document(store: Persistence, office_id: str, document_id: int, events: EventLogger, *, subject: str | None = None, role: str | None = None) -> tuple[dict, dict]:
    root = store.get_active_workspace_root(office_id)
    if not root:
        raise HTTPException(status_code=404, detail="Çalışma klasörü henüz seçilmedi.")
    record = store.get_workspace_document(office_id, document_id)
    if not record:
        raise HTTPException(status_code=404, detail="Belge bulunamadı.")
    if int(record.get("workspace_root_id") or 0) != int(root["id"]):
        events.log(
            "workspace_scope_violation_blocked",
            level="warning",
            office_id=office_id,
            workspace_root_id=root["id"],
            document_id=document_id,
            subject=subject,
            role=role,
        )
        raise HTTPException(status_code=403, detail="Belge seçili çalışma klasörü dışında kaldığı için açılamadı.")
    return root, record


def _extract_context(
    x_role: str | None,
    authorization: str | None,
    jwt_secret: str,
    store: Persistence,
    allow_header_auth: bool,
) -> tuple[str, str, str]:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        ctx = parse_token(jwt_secret, token)
        if not store.is_session_active(ctx.sid):
            raise HTTPException(status_code=401, detail="session_revoked")
        return ctx.sub, ctx.role, ctx.sid

    if not allow_header_auth:
        raise HTTPException(status_code=401, detail="missing_bearer_token")

    # Legacy fallback: keep least privilege to avoid role-escalation via headers.
    requested = (x_role or "intern").lower()
    role = "intern" if requested not in {"intern"} else requested
    return "header-user", role, "header-session"


def _ensure_draft_access(draft: dict | None, subject: str, role: str) -> dict:
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if role != "admin" and draft.get("requested_by") != subject:
        raise HTTPException(status_code=403, detail="draft_access_denied")
    return draft


def _query_result(payload: QueryIn, role: str, subject: str, sid: str, router: ModelRouter, rag, rag_meta: dict, audit: AuditLogger) -> dict:
    selected = router.choose(payload.query, payload.model_profile)
    sources = rag.search(payload.query, k=3)
    for idx, source in enumerate(sources, start=1):
        source["citation_index"] = idx
        source["citation_label"] = f"[{idx}]"

    audit_seed = f"{payload.query}:{role}:{selected['profile']}:{subject}"
    audit_id = hashlib.sha256(audit_seed.encode()).hexdigest()[:16]
    quality = 0.55 + min(0.4, len(sources) * 0.12)
    citation_quality = {
        "score": round(quality, 2),
        "grade": "A" if quality > 0.85 else "B" if quality > 0.7 else "C",
        "issues": [] if quality > 0.7 else ["low_source_overlap", "requires_manual_review"],
    }
    audit.log(
        "query",
        subject=subject,
        role=role,
        session_id=sid,
        profile=selected["profile"],
        audit_id=audit_id,
        source_count=len(sources),
    )

    if sources:
        numbered_refs = " ".join(source["citation_label"] for source in sources)
        answer = f"Sorgu işlendi. En uygun profil: {selected['profile']}. Dayanaklar: {numbered_refs}"
    else:
        answer = f"Sorgu işlendi. En uygun profil: {selected['profile']}. Kaynak bulunamadı."

    return {
        "answer": answer,
        "model_profile": selected["profile"],
        "routing": selected,
        "sources": sources,
        "retrieval_summary": {
            "source_count": len(sources),
            "top_document": sources[0]["document"] if sources else None,
            "warning": "Arama sonucu bulunamadı; manuel kaynak kontrolü önerilir." if not sources else None,
        },
        "citation_quality": citation_quality,
        "ui_citations": [
            {
                "index": source["citation_index"],
                "label": source["citation_label"],
                "document": source.get("document"),
                "line_start": source.get("line_start"),
                "line_end": source.get("line_end"),
                "line_anchor": source.get("line_anchor"),
                "chunk_id": source.get("chunk_id"),
            }
            for source in sources
        ],
        "rag_runtime": rag_meta,
        "security": {
            "role_checked": role,
            "subject": subject,
            "audit_id": audit_id,
            "retrieval_authorized": True,
        },
    }


def create_app() -> FastAPI:
    settings = get_settings()
    profiles = load_model_profiles(settings.model_profiles_path)
    if settings.default_model_profile in (profiles.get("profiles", {}) or {}):
        profiles["default"] = settings.default_model_profile

    rag = create_rag_store(settings.rag_backend, tenant_id=settings.rag_tenant_id)
    rag_meta = rag.runtime_meta()
    router = ModelRouter(profiles)
    audit = AuditLogger(resolve_repo_path(settings.audit_log_path))
    events = StructuredLogger(resolve_repo_path(settings.structured_log_path))
    store = Persistence(resolve_repo_path(settings.db_path))
    connector = ConnectorSafetyWrapper(
        ConnectorPolicy(
            allowed_domains=settings.connector_allow_domains,
            dry_run=settings.connector_dry_run,
        )
    )

    app = FastAPI(title=settings.app_name, version=settings.app_version)

    @app.get("/health")
    def health():
        workspace_root = store.get_active_workspace_root(settings.office_id)
        body = {
            "ok": True,
            "service": "lawcopilot-api",
            "version": settings.app_version,
            "app_name": settings.app_name,
            "office_id": settings.office_id,
            "deployment_mode": settings.deployment_mode,
            "default_model_profile": profiles.get("default"),
            "release_channel": settings.release_channel,
            "environment": settings.environment,
            "desktop_shell": settings.desktop_shell,
            "ts": datetime.now(timezone.utc).isoformat(),
            "connector_dry_run": settings.connector_dry_run,
            "rag_backend": settings.rag_backend,
            "rag_runtime": rag_meta,
            "workspace_configured": bool(workspace_root),
            "workspace_root_name": workspace_root.get("display_name") if workspace_root else None,
            "provider_type": settings.provider_type,
            "provider_base_url": settings.provider_base_url,
            "provider_model": settings.provider_model,
            "provider_configured": settings.provider_configured,
            "telegram_enabled": settings.telegram_enabled,
            "telegram_configured": settings.telegram_configured,
            "telegram_bot_username": settings.telegram_bot_username,
            "telegram_allowed_user_id": settings.telegram_allowed_user_id,
        }
        if settings.expose_security_flags:
            body["safe_defaults"] = {
                "connector_dry_run": settings.connector_dry_run,
                "jwt_secret_default": settings.jwt_secret == "dev-change-me",
                "max_ingest_bytes": settings.max_ingest_bytes,
                "allow_header_auth": settings.allow_header_auth,
            }
        return body

    @app.get("/telemetry/health")
    def telemetry_health(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        recent = events.recent(20)
        workspace_root = store.get_active_workspace_root(settings.office_id)
        audit.log("telemetry_health_viewed", subject=subject, role=role, session_id=sid, event_count=len(recent))
        return {
            "ok": True,
            "app_name": settings.app_name,
            "version": settings.app_version,
            "release_channel": settings.release_channel,
            "environment": settings.environment,
            "deployment_mode": settings.deployment_mode,
            "default_model_profile": profiles.get("default"),
            "desktop_shell": settings.desktop_shell,
            "office_id": settings.office_id,
            "structured_log_path": settings.structured_log_path,
            "audit_log_path": settings.audit_log_path,
            "db_path": settings.db_path,
            "connector_dry_run": settings.connector_dry_run,
            "workspace_configured": bool(workspace_root),
            "workspace_root_name": workspace_root.get("display_name") if workspace_root else None,
            "provider_type": settings.provider_type,
            "provider_base_url": settings.provider_base_url,
            "provider_model": settings.provider_model,
            "provider_configured": settings.provider_configured,
            "telegram_enabled": settings.telegram_enabled,
            "telegram_configured": settings.telegram_configured,
            "telegram_bot_username": settings.telegram_bot_username,
            "telegram_allowed_user_id": settings.telegram_allowed_user_id,
            "recent_events": recent[:10],
        }

    @app.get("/telemetry/events/recent")
    def telemetry_recent_events(
        limit: int = 20,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        return {"items": events.recent(limit)}

    @app.get("/settings/model-profiles")
    def get_model_profiles(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return {
            "default": profiles.get("default"),
            "profiles": profiles.get("profiles", {}),
            "deployment_mode": settings.deployment_mode,
            "office_id": settings.office_id,
        }

    @app.get("/workspace")
    def get_workspace(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            return {"configured": False, "workspace": None, "documents": {"items": []}, "scan_jobs": {"items": []}}
        documents = store.list_workspace_documents(settings.office_id, int(root["id"]))
        scan_jobs = store.list_workspace_scan_jobs(settings.office_id, int(root["id"]))
        return {
            "configured": True,
            "workspace": root,
            "documents": {"items": documents[:10], "count": len(documents)},
            "scan_jobs": {"items": scan_jobs[:10]},
        }

    @app.put("/workspace")
    def save_workspace(
        req: WorkspaceRootRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        try:
            root_path = validate_workspace_root(req.root_path)
        except ValueError as exc:
            events.log("workspace_root_rejected", level="warning", office_id=settings.office_id, subject=subject, role=role, error=str(exc))
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        root = store.save_workspace_root(
            settings.office_id,
            req.display_name or root_path.name,
            str(root_path),
            root_hash(root_path),
        )
        audit.log("workspace_root_saved", subject=subject, role=role, session_id=sid, workspace_root_id=root["id"])
        events.log("workspace_root_selected", office_id=settings.office_id, workspace_root_id=root["id"], subject=subject, role=role)
        return {
            "workspace": root,
            "message": "Çalışma klasörü kaydedildi. Yalnız bu klasör ve alt klasörleri kullanılacak.",
        }

    @app.post("/workspace/scan")
    def scan_workspace(
        req: WorkspaceScanRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            raise HTTPException(status_code=404, detail="Çalışma klasörü henüz seçilmedi.")
        root_path = validate_workspace_root(str(root["root_path"]))
        normalized_extensions = [ext if ext.startswith(".") else f".{ext}" for ext in (req.extensions or [])]
        job = store.create_workspace_scan_job(settings.office_id, int(root["id"]))
        if not job:
            raise HTTPException(status_code=404, detail="Çalışma klasörü bulunamadı.")
        store.update_workspace_scan_job(settings.office_id, int(job["id"]), status="processing")
        events.log("workspace_scan_started", workspace_root_id=root["id"], subject=subject, role=role)
        try:
            scanned_items, stats = scan_workspace_tree(
                root_path=root_path,
                office_id=settings.office_id,
                workspace_root_id=int(root["id"]),
                max_bytes=settings.max_ingest_bytes,
                extensions=normalized_extensions or None,
            )
            seen_paths: list[str] = []
            indexed_count = 0
            for item in scanned_items:
                record = store.upsert_workspace_document(
                    settings.office_id,
                    int(root["id"]),
                    relative_path=str(item["relative_path"]),
                    display_name=str(item["display_name"]),
                    extension=str(item["extension"]),
                    content_type=item["content_type"],
                    size_bytes=int(item["size_bytes"]),
                    mtime=int(item["mtime"]),
                    checksum=str(item["checksum"]),
                    parser_status=str(item["parser_status"]),
                    indexed_status=str(item["indexed_status"]),
                    document_language=str(item["document_language"]),
                    last_error=item["error"],
                )
                seen_paths.append(str(item["relative_path"]))
                if item["indexed_status"] == "indexed":
                    chunks = build_workspace_chunks(
                        office_id=settings.office_id,
                        workspace_root_id=int(root["id"]),
                        workspace_document_id=int(record["id"]),
                        document_name=str(record["display_name"]),
                        relative_path=str(record["relative_path"]),
                        text=str(item["text"]),
                    )
                    store.replace_workspace_document_chunks(settings.office_id, int(root["id"]), int(record["id"]), chunks)
                    indexed_count += 1
                else:
                    store.replace_workspace_document_chunks(settings.office_id, int(root["id"]), int(record["id"]), [])
            if req.full_rescan:
                store.mark_missing_workspace_documents(settings.office_id, int(root["id"]), seen_paths)
            job = store.update_workspace_scan_job(
                settings.office_id,
                int(job["id"]),
                status="completed",
                files_seen=stats["files_seen"],
                files_indexed=stats["files_indexed"],
                files_skipped=stats["files_skipped"],
                files_failed=stats["files_failed"],
            )
            audit.log(
                "workspace_scan_completed",
                subject=subject,
                role=role,
                session_id=sid,
                workspace_root_id=root["id"],
                files_seen=stats["files_seen"],
                files_indexed=stats["files_indexed"],
                files_failed=stats["files_failed"],
            )
            events.log(
                "workspace_scan_completed",
                workspace_root_id=root["id"],
                subject=subject,
                role=role,
                files_seen=stats["files_seen"],
                files_indexed=indexed_count,
                files_failed=stats["files_failed"],
            )
            return {
                "workspace": root,
                "job": job,
                "stats": stats,
                "message": "Çalışma klasörü taraması tamamlandı.",
            }
        except ValueError as exc:
            job = store.update_workspace_scan_job(settings.office_id, int(job["id"]), status="failed", error=str(exc))
            events.log("workspace_scan_failed", level="warning", workspace_root_id=root["id"], subject=subject, role=role, error=str(exc))
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/workspace/scan-jobs")
    def list_workspace_scan_jobs(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            return {"configured": False, "items": []}
        return {"configured": True, "workspace_root_id": root["id"], "items": store.list_workspace_scan_jobs(settings.office_id, int(root["id"]))}

    @app.get("/workspace/documents")
    def list_workspace_documents(
        q: str | None = None,
        extension: str | None = None,
        status: str | None = None,
        path_prefix: str | None = None,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            return {"configured": False, "items": []}
        items = store.list_workspace_documents(
            settings.office_id,
            int(root["id"]),
            query_text=q,
            extension=extension,
            status=status,
            path_prefix=path_prefix,
        )
        return {"configured": True, "workspace_root_id": root["id"], "items": items}

    @app.get("/workspace/documents/{document_id}")
    def get_workspace_document(
        document_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        _, record = _require_active_workspace_document(store, settings.office_id, document_id, events, subject=subject, role=role)
        return record

    @app.get("/workspace/documents/{document_id}/chunks")
    def get_workspace_document_chunks(
        document_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        _require_active_workspace_document(store, settings.office_id, document_id, events, subject=subject, role=role)
        items = store.list_workspace_document_chunks(settings.office_id, document_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")
        return {"document_id": document_id, "items": items}

    @app.post("/workspace/search")
    def search_workspace(
        payload: WorkspaceSearchRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            raise HTTPException(status_code=404, detail="Çalışma klasörü henüz seçilmedi.")
        extensions = [ext if ext.startswith(".") else f".{ext}" for ext in (payload.extensions or [])]
        rows = store.search_workspace_document_chunks(
            settings.office_id,
            int(root["id"]),
            path_prefix=payload.path_prefix,
            extensions=extensions or None,
        )
        result = build_workspace_search_result(query=payload.query, rows=rows, limit=payload.limit)
        audit.log("workspace_search", subject=subject, role=role, session_id=sid, workspace_root_id=root["id"], source_count=result["citation_count"])
        events.log("workspace_search_executed", workspace_root_id=root["id"], subject=subject, role=role, citation_count=result["citation_count"], support_level=result["support_level"])
        return result

    @app.post("/workspace/similar-documents")
    def similar_workspace_documents(
        payload: SimilarDocumentsRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        root = store.get_active_workspace_root(settings.office_id)
        if not root:
            raise HTTPException(status_code=404, detail="Çalışma klasörü henüz seçilmedi.")
        documents = store.list_workspace_documents(settings.office_id, int(root["id"]), path_prefix=payload.path_prefix)
        if payload.document_id:
            _, source_document = _require_active_workspace_document(store, settings.office_id, payload.document_id, events, subject=subject, role=role)
            rows = store.search_workspace_document_chunks(settings.office_id, int(root["id"]))
            result = find_similar_documents(source_document=source_document, candidate_documents=documents, chunk_rows=rows, limit=payload.limit)
        else:
            if not payload.query:
                raise HTTPException(status_code=422, detail="Benzer belge araması için belge veya sorgu gerekli.")
            rows = store.search_workspace_document_chunks(settings.office_id, int(root["id"]), path_prefix=payload.path_prefix)
            result = build_workspace_search_result(query=payload.query, rows=rows, limit=payload.limit)
            result = {
                "items": [
                    {
                        "workspace_document_id": item["workspace_document_id"],
                        "belge_adi": item["document_name"],
                        "goreli_yol": item.get("relative_path"),
                        "benzerlik_puani": item["relevance_score"],
                        "neden_benzer": "Sorgu ile örtüşen belge pasajları bulundu.",
                        "klasor_baglami": item.get("relative_path") or "Klasör bilgisi kaydedilmedi.",
                        "skor_bilesenleri": {
                            "dosya_adi": 0.0,
                            "icerik": item["relevance_score"],
                            "belge_turu": 0.0,
                            "checksum": 0.0,
                            "klasor_baglami": 0.0,
                            "hukuk_terimleri": 0.0,
                            "genel_skor": item["relevance_score"],
                        },
                        "ortak_terimler": [],
                        "destekleyici_pasajlar": [item],
                        "dikkat_notlari": ["Bu sonuç sorgu benzerliğine dayanır; dosyaya bağlamadan önce pasajı inceleyin."],
                        "taslak_onerileri": ["İnceleme notu taslağı", "İç ekip özeti taslağı"],
                        "manuel_inceleme_gerekir": True,
                        "sinyaller": ["sorgu_eslesmesi"],
                    }
                    for item in result["citations"]
                ],
                "explanation": "Sorgu tabanlı yerel benzer belge taraması tamamlandı.",
                "top_terms": [],
                "manual_review_required": True,
            }
        audit.log("workspace_similarity", subject=subject, role=role, session_id=sid, workspace_root_id=root["id"], result_count=len(result["items"]))
        events.log("workspace_similarity_executed", workspace_root_id=root["id"], subject=subject, role=role, result_count=len(result["items"]))
        return result

    @app.post("/matters/{matter_id}/documents/attach-from-workspace")
    def attach_workspace_document_to_matter(
        matter_id: int,
        payload: WorkspaceAttachRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        _require_active_workspace_document(store, settings.office_id, payload.workspace_document_id, events, subject=subject, role=role)
        link = store.attach_workspace_document_to_matter(settings.office_id, matter_id, payload.workspace_document_id, subject)
        if not link:
            raise HTTPException(status_code=404, detail="Dosya veya çalışma alanı belgesi bulunamadı.")
        audit.log("workspace_document_attached", subject=subject, role=role, session_id=sid, matter_id=matter_id, workspace_document_id=payload.workspace_document_id)
        events.log("workspace_document_attached_to_matter", matter_id=matter_id, workspace_document_id=payload.workspace_document_id, subject=subject, role=role)
        return link

    @app.get("/matters/{matter_id}/workspace-documents")
    def list_matter_workspace_documents(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_workspace_documents(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        return {"matter_id": matter_id, "items": items}

    @app.post("/auth/token")
    def token(req: TokenRequest):
        if req.role == "admin":
            if settings.bootstrap_admin_key and req.bootstrap_key != settings.bootstrap_admin_key:
                raise HTTPException(status_code=403, detail="admin_bootstrap_key_required")
        jwt, exp, sid = issue_token(settings.jwt_secret, req.subject, req.role, settings.token_ttl_seconds)
        store.store_session(sid, req.subject, req.role, datetime.fromtimestamp(exp, tz=timezone.utc).isoformat())
        audit.log("token_issued", subject=req.subject, role=req.role, session_id=sid)
        return {
            "access_token": jwt,
            "token_type": "bearer",
            "expires_in": settings.token_ttl_seconds,
            "session_id": sid,
        }

    @app.post("/auth/revoke")
    def revoke_session(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        revoked = store.revoke_session(sid)
        audit.log("session_revoked", subject=subject, role=role, session_id=sid, revoked=revoked)
        return {"ok": revoked, "session_id": sid}

    @app.post("/matters")
    def create_matter(
        req: MatterCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        opened_at = req.opened_at.isoformat() if req.opened_at else None
        rec = store.create_matter(
            settings.office_id,
            req.title,
            req.reference_code,
            req.practice_area,
            req.status,
            req.summary,
            req.client_name,
            req.lead_lawyer,
            opened_at,
            subject,
        )
        audit.log(
            "matter_created",
            subject=subject,
            role=role,
            session_id=sid,
            office_id=settings.office_id,
            matter_id=rec["id"],
        )
        events.log("matter_created", office_id=settings.office_id, matter_id=rec["id"], subject=subject, role=role)
        return rec

    @app.get("/matters")
    def list_matters(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return {"office_id": settings.office_id, "items": store.list_matters(settings.office_id)}

    @app.get("/matters/{matter_id}")
    def get_matter(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        rec = store.get_matter(matter_id, settings.office_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        return rec

    @app.patch("/matters/{matter_id}")
    def update_matter(
        matter_id: int,
        req: MatterUpdateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        fields = req.model_dump(exclude_none=True)
        if "opened_at" in fields and req.opened_at is not None:
            fields["opened_at"] = req.opened_at.isoformat()
        rec = store.update_matter(settings.office_id, matter_id, fields)
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_updated", subject=subject, role=role, session_id=sid, matter_id=matter_id, updated_fields=sorted(fields.keys()))
        return rec

    @app.post("/matters/{matter_id}/notes")
    def create_matter_note(
        matter_id: int,
        req: MatterNoteCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        event_at = req.event_at.isoformat() if req.event_at else None
        rec = store.add_matter_note(settings.office_id, matter_id, req.note_type, req.body, subject, event_at)
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_note_created", subject=subject, role=role, session_id=sid, matter_id=matter_id, note_id=rec["id"], note_type=req.note_type)
        return rec

    @app.get("/matters/{matter_id}/timeline")
    def get_matter_timeline(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_timeline(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_timeline_viewed", subject=subject, role=role, session_id=sid, matter_id=matter_id, event_count=len(items))
        events.log("matter_timeline_viewed", matter_id=matter_id, subject=subject, role=role, event_count=len(items))
        return {"matter_id": matter_id, "items": items}

    @app.get("/matters/{matter_id}/chronology")
    def get_matter_chronology(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if not context:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        chronology = build_chronology(
            matter=context["matter"],
            notes=context["notes"],
            chunks=context["chunks"],
            tasks=context["tasks"],
        )
        audit.log(
            "matter_chronology_viewed",
            subject=subject,
            role=role,
            session_id=sid,
            matter_id=matter_id,
            item_count=len(chronology["items"]),
            issue_count=len(chronology["issues"]),
        )
        return chronology

    @app.get("/matters/{matter_id}/risk-notes")
    def get_matter_risk_notes(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if not context:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        chronology = build_chronology(
            matter=context["matter"],
            notes=context["notes"],
            chunks=context["chunks"],
            tasks=context["tasks"],
        )
        risk_notes = build_risk_notes(
            matter=context["matter"],
            documents=context["documents"],
            notes=context["notes"],
            tasks=context["tasks"],
            chronology=chronology,
            chunks=context["chunks"],
        )
        audit.log(
            "matter_risk_notes_viewed",
            subject=subject,
            role=role,
            session_id=sid,
            matter_id=matter_id,
            note_count=len(risk_notes["items"]),
        )
        return risk_notes

    @app.get("/matters/{matter_id}/activity")
    def get_matter_activity(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if not context:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        activity = build_activity_stream(
            matter=context["matter"],
            timeline=context["timeline"],
            notes=context["notes"],
            draft_events=context["draft_events"],
            ingestion_jobs=context["ingestion_jobs"],
        )
        audit.log(
            "matter_activity_viewed",
            subject=subject,
            role=role,
            session_id=sid,
            matter_id=matter_id,
            item_count=len(activity["items"]),
        )
        return activity

    @app.get("/matters/{matter_id}/summary")
    def get_matter_summary(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        rec = store.get_matter_summary(settings.office_id, matter_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_summary_viewed", subject=subject, role=role, session_id=sid, matter_id=matter_id)
        events.log("matter_summary_viewed", matter_id=matter_id, subject=subject, role=role)
        return rec

    @app.get("/matters/{matter_id}/tasks")
    def list_matter_tasks(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_tasks(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_tasks_listed", subject=subject, role=role, session_id=sid, matter_id=matter_id, task_count=len(items))
        return {"matter_id": matter_id, "items": items}

    @app.get("/matters/{matter_id}/task-recommendations")
    def get_matter_task_recommendations(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if not context:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        chronology = build_chronology(
            matter=context["matter"],
            notes=context["notes"],
            chunks=context["chunks"],
            tasks=context["tasks"],
        )
        risk_notes = build_risk_notes(
            matter=context["matter"],
            documents=context["documents"],
            notes=context["notes"],
            tasks=context["tasks"],
            chronology=chronology,
            chunks=context["chunks"],
        )
        recommendations = build_task_recommendations(
            matter=context["matter"],
            chronology=chronology,
            risk_notes=risk_notes,
            tasks=context["tasks"],
        )
        audit.log(
            "matter_task_recommendations_viewed",
            subject=subject,
            role=role,
            session_id=sid,
            matter_id=matter_id,
            recommendation_count=len(recommendations["items"]),
        )
        return recommendations

    @app.post("/matters/{matter_id}/drafts")
    def create_matter_draft(
        matter_id: int,
        req: MatterDraftCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        rec = store.create_matter_draft(
            settings.office_id,
            matter_id,
            req.draft_type,
            req.title,
            req.body,
            req.target_channel,
            req.to_contact,
            subject,
        )
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_draft_created", subject=subject, role=role, session_id=sid, matter_id=matter_id, draft_id=rec["id"], draft_type=req.draft_type)
        events.log("matter_draft_created", matter_id=matter_id, draft_id=rec["id"], draft_type=req.draft_type, subject=subject, role=role)
        return rec

    @app.post("/matters/{matter_id}/drafts/generate")
    def generate_workflow_draft(
        matter_id: int,
        req: MatterDraftGenerateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        context = _load_matter_workflow_context(store, settings.office_id, matter_id)
        if not context:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        chronology = build_chronology(
            matter=context["matter"],
            notes=context["notes"],
            chunks=context["chunks"],
            tasks=context["tasks"],
        )
        risk_notes = build_risk_notes(
            matter=context["matter"],
            documents=context["documents"],
            notes=context["notes"],
            tasks=context["tasks"],
            chronology=chronology,
            chunks=context["chunks"],
        )
        generated = generate_matter_draft(
            matter=context["matter"],
            draft_type=req.draft_type,
            chronology=chronology,
            risk_notes=risk_notes,
            documents=context["documents"],
            tasks=context["tasks"],
            target_channel=req.target_channel,
            to_contact=req.to_contact,
            instructions=req.instructions,
        )
        rec = store.create_matter_draft(
            settings.office_id,
            matter_id,
            req.draft_type,
            generated["title"],
            generated["body"],
            req.target_channel,
            req.to_contact,
            subject,
            source_context=generated["source_context"],
            generated_from=generated["generated_from"],
            manual_review_required=True,
        )
        if not rec:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log(
            "matter_draft_generated",
            subject=subject,
            role=role,
            session_id=sid,
            matter_id=matter_id,
            draft_id=rec["id"],
            draft_type=req.draft_type,
        )
        events.log("matter_draft_generated", matter_id=matter_id, draft_id=rec["id"], draft_type=req.draft_type, subject=subject, role=role)
        return {
            "draft": rec,
            "review_message": "Bu taslak sistem tarafından üretilmiş bir çalışma çıktısıdır. Dış kullanımdan önce insan incelemesi zorunludur.",
            "source_context": generated["source_context"],
        }

    @app.get("/matters/{matter_id}/drafts")
    def list_matter_drafts(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_drafts(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_drafts_listed", subject=subject, role=role, session_id=sid, matter_id=matter_id, draft_count=len(items))
        return {"matter_id": matter_id, "items": items}

    @app.post("/matters/{matter_id}/documents")
    async def upload_matter_document(
        matter_id: int,
        file: UploadFile = File(...),
        display_name: str | None = Form(default=None),
        source_type: str = Form(default="upload"),
        source_ref: str | None = Form(default=None),
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)

        content = await file.read()
        if len(content) > settings.max_ingest_bytes:
            raise HTTPException(status_code=413, detail="Dosya boyutu sınırı aşıldı.")

        filename = file.filename or "unnamed.txt"
        checksum = hashlib.sha256(content).hexdigest()
        document = store.create_document(
            settings.office_id,
            matter_id,
            filename,
            display_name or filename,
            file.content_type,
            source_type,
            source_ref,
            checksum,
            len(content),
        )
        if not document:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        job = store.create_ingestion_job(settings.office_id, matter_id, int(document["id"]))
        store.update_ingestion_job(settings.office_id, int(job["id"]), "processing")
        store.update_document_status(settings.office_id, int(document["id"]), "processing")
        try:
            text = _extract_text(content)
            chunks = build_persisted_chunks(
                office_id=settings.office_id,
                matter_id=matter_id,
                document_id=int(document["id"]),
                document_name=str(document["display_name"]),
                source_type=source_type,
                text=text,
            )
            if not chunks:
                raise ValueError("Belgeden indekslenecek metin parçaları çıkarılamadı.")
            chunk_count = store.replace_document_chunks(settings.office_id, matter_id, int(document["id"]), chunks)
            document = store.update_document_status(settings.office_id, int(document["id"]), "indexed")
            job = store.update_ingestion_job(settings.office_id, int(job["id"]), "indexed")
            store.record_matter_event(
                settings.office_id,
                matter_id,
                "document_indexed",
                "Dosya belgesi indekslendi",
                f"{document['display_name']} belgesi {chunk_count} parça ile indekslendi",
                document["updated_at"],
                subject,
            )
            audit.log(
                "matter_document_ingested",
                subject=subject,
                role=role,
                session_id=sid,
                matter_id=matter_id,
                document_id=document["id"],
                job_id=job["id"],
                chunk_count=chunk_count,
            )
            events.log(
                "matter_document_ingested",
                matter_id=matter_id,
                document_id=document["id"],
                job_id=job["id"],
                chunk_count=chunk_count,
                subject=subject,
                role=role,
            )
            return {
                "document": document,
                "job": job,
                "chunk_count": chunk_count,
                "rag_runtime": rag_meta,
                "security": {"role_checked": role, "subject": subject, "matter_id": matter_id, "office_id": settings.office_id},
            }
        except ValueError as exc:
            document = store.update_document_status(settings.office_id, int(document["id"]), "failed")
            job = store.update_ingestion_job(settings.office_id, int(job["id"]), "failed", error=str(exc))
            store.record_matter_event(
                settings.office_id,
                matter_id,
                "document_ingest_failed",
                "Dosya belgesi indekslenemedi",
                f"{document['display_name']} belgesi indekslenemedi: {exc}",
                document["updated_at"],
                subject,
            )
            audit.log(
                "matter_document_ingest_failed",
                subject=subject,
                role=role,
                session_id=sid,
                matter_id=matter_id,
                document_id=document["id"],
                job_id=job["id"],
                error=str(exc),
            )
            events.log(
                "matter_document_ingest_failed",
                level="warning",
                matter_id=matter_id,
                document_id=document["id"],
                job_id=job["id"],
                error=str(exc),
                subject=subject,
                role=role,
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/matters/{matter_id}/documents")
    def list_matter_documents(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_documents(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_documents_listed", subject=subject, role=role, session_id=sid, matter_id=matter_id, document_count=len(items))
        return {"matter_id": matter_id, "items": items}

    @app.get("/matters/{matter_id}/documents/{document_id}")
    def get_matter_document(
        matter_id: int,
        document_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        rec = store.get_document(settings.office_id, matter_id, document_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")
        return rec

    @app.get("/matters/{matter_id}/ingestion-jobs")
    def list_matter_ingestion_jobs(
        matter_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_matter_ingestion_jobs(settings.office_id, matter_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
        audit.log("matter_ingestion_jobs_listed", subject=subject, role=role, session_id=sid, matter_id=matter_id, job_count=len(items))
        return {"matter_id": matter_id, "items": items}

    @app.post("/matters/{matter_id}/search")
    def search_matter(
        matter_id: int,
        payload: MatterSearchRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        result = _matter_search_result(
            matter_id=matter_id,
            payload=payload,
            role=role,
            subject=subject,
            sid=sid,
            router=router,
            store=store,
            rag_meta=rag_meta,
            audit=audit,
            office_id=settings.office_id,
        )
        events.log(
            "matter_search",
            matter_id=matter_id,
            subject=subject,
            role=role,
            support_level=result["support_level"],
            citation_count=result["citation_count"],
            manual_review_required=result["manual_review_required"],
        )
        return result

    @app.get("/documents/{document_id}/chunks")
    def get_document_chunks(
        document_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_document_chunks(settings.office_id, document_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")
        return {"document_id": document_id, "items": items}

    @app.get("/documents/{document_id}/citations")
    def get_document_citations(
        document_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        document = store.get_document_global(settings.office_id, document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")
        chunks = store.list_document_chunks(settings.office_id, document_id)
        if chunks is None:
            raise HTTPException(status_code=404, detail="Belge bulunamadı.")
        citations = []
        for idx, chunk in enumerate(chunks, start=1):
            citation = {
                "document_id": document_id,
                "document_name": document.get("display_name"),
                "matter_id": document.get("matter_id"),
                "chunk_id": chunk.get("id"),
                "chunk_index": chunk.get("chunk_index"),
                "excerpt": str(chunk.get("text") or "")[:320],
                "relevance_score": 1.0,
                "source_type": document.get("source_type"),
                "support_type": "document_backed",
                "confidence": "high",
                "line_anchor": chunk.get("metadata", {}).get("line_anchor"),
                "page": chunk.get("metadata", {}).get("page"),
                "line_start": chunk.get("metadata", {}).get("line_start"),
                "line_end": chunk.get("metadata", {}).get("line_end"),
            }
            citations.append(_citation_view(citation, idx))
        return {"document_id": document_id, "matter_id": document.get("matter_id"), "items": citations}

    @app.post("/ingest")
    async def ingest(
        file: UploadFile = File(...),
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)

        content = await file.read()
        if len(content) > settings.max_ingest_bytes:
            raise HTTPException(status_code=413, detail="Dosya boyutu sınırı aşıldı.")

        digest = hashlib.sha256(content).hexdigest()
        meta = rag.add_document(file.filename or "unnamed.txt", content)
        audit.log(
            "ingest",
            subject=subject,
            role=role,
            session_id=sid,
            filename=file.filename,
            sha256=digest,
            indexed_chunks=meta["indexed_chunks"],
        )
        return {
            "filename": file.filename,
            "size": len(content),
            "sha256": digest,
            "status": "indexed",
            "chunks": meta["indexed_chunks"],
            "rag_runtime": rag_meta,
            "security": {"role_checked": role, "subject": subject},
        }

    @app.post("/query")
    def query(
        payload: QueryIn,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return _query_result(payload, role, subject, sid, router, rag, rag_meta, audit)

    @app.post("/query/jobs")
    def create_query_job(
        payload: QueryJobCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        job = store.create_query_job(subject, payload.query, payload.model_profile, payload.continue_in_background)

        def _run_job() -> None:
            time.sleep(0.2)
            latest = store.get_query_job(int(job["id"]), subject)
            if not latest or latest.get("cancel_requested"):
                store.update_query_job_status(int(job["id"]), subject, "cancelled")
                return
            try:
                result = _query_result(payload, role, subject, sid, router, rag, rag_meta, audit)
                detached = bool(latest.get("detached"))
                store.update_query_job_status(
                    int(job["id"]),
                    subject,
                    "completed",
                    result=result,
                    detached=detached,
                    toast_pending=detached,
                )
            except Exception as exc:
                store.update_query_job_status(int(job["id"]), subject, "failed", error=str(exc))

        threading.Thread(target=_run_job, daemon=True).start()
        return {
            "job_id": job["id"],
            "status": "running",
            "ui": {
                "message": "Yanıt hazırlanıyor. İstersen beklemeyi bırakıp arkaplanda devam ettirebilirsin.",
                "cancel_label": "İptal Et",
                "background_label": "Arkaplanda Devam Et",
            },
        }

    @app.get("/query/jobs")
    def list_query_jobs(
        limit: int = 20,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        items = store.list_query_jobs(subject, limit)
        summary = {
            "running": sum(1 for job in items if job.get("status") == "running"),
            "completed": sum(1 for job in items if job.get("status") == "completed"),
            "failed": sum(1 for job in items if job.get("status") == "failed"),
            "cancelled": sum(1 for job in items if job.get("status") == "cancelled"),
            "toast_pending": sum(1 for job in items if job.get("toast_pending")),
        }
        return {"items": items, "summary": summary}

    @app.get("/query/jobs/{job_id}")
    def query_job_status(
        job_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        job = store.get_query_job(job_id, subject)
        if not job:
            raise HTTPException(status_code=404, detail="Sorgu işi bulunamadı.")
        response = {
            "job_id": job["id"],
            "status": job["status"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "completed_at": job.get("completed_at"),
            "result": job.get("result"),
            "error": job.get("error"),
        }
        if job["status"] == "completed" and job.get("toast_pending"):
            response["toast"] = {
                "level": "success",
                "title": "Yanıt hazır",
                "description": "Arkaplanda çalışan AI yanıtı tamamlandı.",
                "ack_endpoint": f"/query/jobs/{job_id}/ack-toast",
            }
        return response

    @app.post("/query/jobs/{job_id}/cancel")
    def cancel_query_job(
        job_id: int,
        keep_background: bool = False,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        job = store.request_query_job_cancel(job_id, subject, keep_background)
        if not job:
            raise HTTPException(status_code=404, detail="Sorgu işi bulunamadı.")
        audit.log(
            "query_job_cancel_requested",
            subject=subject,
            role=role,
            session_id=sid,
            job_id=job_id,
            keep_background=keep_background,
        )
        if keep_background:
            return {"ok": True, "status": "detached", "message": "İşlem arkaplanda devam ediyor."}
        return {"ok": True, "status": "cancelling", "message": "İşlem iptal kuyruğuna alındı."}

    @app.post("/query/jobs/{job_id}/ack-toast")
    def acknowledge_query_job_toast(
        job_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        job = store.acknowledge_query_job_toast(job_id, subject)
        if not job:
            raise HTTPException(status_code=404, detail="Sorgu işi bulunamadı.")
        return {"ok": True, "job_id": job_id, "toast_pending": job.get("toast_pending", False)}

    @app.post("/citations/review")
    def citation_review(
        payload: CitationReviewRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)

        refs = payload.answer.count("[") + payload.answer.lower().count("kaynak")
        score = min(1.0, 0.35 + refs * 0.1)
        grade = "A" if score >= 0.9 else "B" if score >= 0.75 else "C"
        audit.log("citation_review", subject=subject, role=role, session_id=sid, score=round(score, 2), grade=grade)

        return {
            "score": round(score, 2),
            "grade": grade,
            "recommendations": [
                "Her hukuki iddiaya en az bir kaynak ekleyin.",
                "Doğrudan alıntı ve tarih alanlarını doğrulayın.",
            ],
        }

    @app.post("/connectors/preview")
    def connectors_preview(
        req: ConnectorPreviewRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        try:
            wrapped = connector.wrap_action(req.destination, req.message)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        audit.log(
            "connector_preview",
            subject=subject,
            role=role,
            session_id=sid,
            destination=req.destination,
            blocked_pii=wrapped["blocked_pii"],
        )
        events.log(
            "connector_preview",
            subject=subject,
            role=role,
            destination=req.destination,
            blocked_pii=wrapped["blocked_pii"],
            blocked_instruction=wrapped.get("blocked_instruction", False),
            status=wrapped["status"],
        )
        return wrapped

    @app.post("/tasks")
    def create_task(
        req: TaskCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        due_at = req.due_at.isoformat() if req.due_at else None
        try:
            rec = store.create_task(
                req.title,
                due_at,
                req.priority,
                subject,
                office_id=settings.office_id,
                matter_id=req.matter_id,
                origin_type=req.origin_type,
                origin_ref=req.origin_ref,
                recommended_by=req.recommended_by,
                explanation=req.explanation,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        audit.log("task_created", subject=subject, role=role, session_id=sid, task_id=rec["id"])
        events.log("task_created", task_id=rec["id"], matter_id=rec.get("matter_id"), subject=subject, role=role, priority=rec["priority"])
        return rec

    @app.get("/tasks")
    def list_tasks(
        matter_id: int | None = None,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return {"items": store.list_tasks(subject, matter_id=matter_id)}

    @app.post("/tasks/complete-bulk")
    def complete_tasks_bulk(
        req: TaskBulkCompleteRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        task_ids = sorted({int(task_id) for task_id in req.task_ids if int(task_id) > 0})
        updated_count = store.complete_tasks_bulk(task_ids, subject)
        audit.log(
            "tasks_completed_bulk",
            subject=subject,
            role=role,
            session_id=sid,
            task_count=updated_count,
            requested_count=len(task_ids),
        )
        events.log("tasks_completed_bulk", subject=subject, role=role, updated_count=updated_count, requested_count=len(task_ids))
        return {"ok": True, "updated_count": updated_count, "requested_ids": task_ids}

    @app.post("/tasks/update-status")
    def update_task_status(
        req: TaskStatusUpdateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        rec = store.update_task_status(req.task_id, req.status, subject)
        if not rec:
            raise HTTPException(status_code=404, detail="task_not_found")
        audit.log(
            "task_status_updated",
            subject=subject,
            role=role,
            session_id=sid,
            task_id=req.task_id,
            status=req.status,
        )
        events.log("task_status_updated", subject=subject, role=role, task_id=req.task_id, status=req.status, matter_id=rec.get("matter_id"))
        return {"ok": True, "task": rec}

    @app.post("/tasks/update-due")
    def update_task_due_at(
        req: TaskDueUpdateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        due_at = req.due_at.isoformat() if req.due_at else None
        rec = store.update_task_due_at(req.task_id, due_at, subject)
        if not rec:
            raise HTTPException(status_code=404, detail="task_not_found")
        audit.log(
            "task_due_updated",
            subject=subject,
            role=role,
            session_id=sid,
            task_id=req.task_id,
            due_at=due_at,
        )
        events.log("task_due_updated", subject=subject, role=role, task_id=req.task_id, due_at=due_at, matter_id=rec.get("matter_id"))
        return {"ok": True, "task": rec}

    @app.post("/email/drafts")
    def create_email_draft(
        req: EmailDraftCreateRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        try:
            rec = store.create_email_draft(
                str(req.to_email),
                req.subject,
                req.body,
                subject,
                office_id=settings.office_id,
                matter_id=req.matter_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        audit.log(
            "email_draft_created",
            subject=subject,
            role=role,
            session_id=sid,
            draft_id=rec["id"],
            to_email=_safe_excerpt(rec["to_email"]),
        )
        events.log("email_draft_created", draft_id=rec["id"], matter_id=rec.get("matter_id"), subject=subject, role=role)
        return rec

    @app.post("/email/approve")
    def approve_email_draft(
        req: EmailDraftApproveRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("admin", role)
        rec = store.approve_email_draft(req.draft_id, subject)
        if not rec:
            raise HTTPException(status_code=404, detail="draft_not_found")
        audit.log("email_draft_approved", subject=subject, role=role, session_id=sid, draft_id=req.draft_id)
        return {
            "status": rec["status"],
            "draft": rec,
            "dispatch": {
                "mode": "approval_pipeline_only",
                "external_send": "disabled_in_api",
            },
        }

    @app.post("/email/retract")
    def retract_email_draft(
        req: EmailDraftRetractRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("admin", role)
        rec = store.retract_email_draft(req.draft_id, subject, req.reason)
        if not rec:
            raise HTTPException(status_code=404, detail="draft_not_found")
        audit.log(
            "email_draft_retracted",
            subject=subject,
            role=role,
            session_id=sid,
            draft_id=req.draft_id,
            reason=_safe_excerpt(req.reason or ""),
        )
        return {"status": rec["status"], "draft": rec}

    @app.get("/email/drafts/{draft_id}/preview")
    def preview_email_draft(
        draft_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        draft = _ensure_draft_access(store.get_email_draft(draft_id), subject, role)
        body = draft.get("body") or ""
        preview = {
            "id": draft["id"],
            "to_email": draft["to_email"],
            "subject": draft["subject"],
            "status": draft["status"],
            "requested_by": draft["requested_by"],
            "approved_by": draft.get("approved_by"),
            "created_at": draft["created_at"],
            "body_preview": body[:240],
            "body_chars": len(body),
            "body_words": len([w for w in body.split() if w]),
        }
        audit.log("email_draft_previewed", subject=subject, role=role, session_id=sid, draft_id=draft_id)
        return preview

    @app.get("/email/drafts/{draft_id}/history")
    def email_draft_history(
        draft_id: int,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        draft = _ensure_draft_access(store.get_email_draft(draft_id), subject, role)
        events = store.list_email_draft_events(draft_id)
        audit.log("email_draft_history_viewed", subject=subject, role=role, session_id=sid, draft_id=draft_id, event_count=len(events))
        return {"draft": draft, "events": events}

    @app.get("/email/drafts")
    def list_email_drafts(
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        owner = None if role == "admin" else subject
        return {"items": store.list_email_drafts(owner=owner)}

    @app.post("/social/ingest")
    def social_ingest(
        req: SocialIngestRequest,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        subject, role, sid = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("lawyer", role)
        lower = req.content.lower()
        risk = 0.2
        for term in ("dava", "mahkeme", "skandal", "ifşa", "şikayet", "dolandır"):
            if term in lower:
                risk += 0.12
        rec = store.add_social_event(req.source, req.handle, req.content, min(risk, 1.0))
        audit.log("social_ingest", subject=subject, role=role, session_id=sid, event_id=rec["id"], source=req.source)
        return {"event": rec, "mode": "read_only_pipeline"}

    @app.get("/social/events")
    def social_events(
        limit: int = 20,
        x_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _, role, _ = _extract_context(x_role, authorization, settings.jwt_secret, store, settings.allow_header_auth)
        require_role("intern", role)
        return {"items": store.list_social_events(limit), "read_only": True}

    return app
