from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Protocol


WORD_RE = re.compile(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9_]{2,}")


@dataclass
class Chunk:
    chunk_id: str
    document: str
    text: str
    page: int
    line_start: int
    line_end: int
    embedding: set[str]


def tokenize(text: str) -> set[str]:
    return {t.lower() for t in WORD_RE.findall(text)}


def chunk_text(text: str, lines_per_chunk: int = 12) -> Iterable[dict[str, Any]]:
    lines = text.splitlines()
    if not lines:
        return
    page = 1
    chunk_index = 0
    for i in range(0, len(lines), lines_per_chunk):
        part_lines = lines[i : i + lines_per_chunk]
        if not part_lines:
            continue
        chunk_index += 1
        line_start = i + 1
        line_end = i + len(part_lines)
        part = "\n".join(part_lines)
        yield {
            "chunk_index": chunk_index,
            "text": part,
            "token_count": len(tokenize(part)),
            "metadata": {
                "page": page,
                "line_start": line_start,
                "line_end": line_end,
            },
        }
        page += 1


def build_persisted_chunks(
    *,
    office_id: str,
    matter_id: int,
    document_id: int,
    document_name: str,
    source_type: str,
    text: str,
) -> list[dict[str, Any]]:
    built: list[dict[str, Any]] = []
    for chunk in chunk_text(text):
        meta = dict(chunk["metadata"])
        meta["line_anchor"] = f"{document_name}#L{meta['line_start']}"
        meta["source_type"] = source_type
        meta["document_name"] = document_name
        built.append(
            {
                "document_id": document_id,
                "office_id": office_id,
                "matter_id": matter_id,
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
                "token_count": chunk["token_count"],
                "metadata_json": json.dumps(meta, ensure_ascii=False),
            }
        )
    return built


def score_chunk_records(query: str, chunk_rows: list[dict[str, Any]], k: int = 5) -> list[dict[str, Any]]:
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in chunk_rows:
        chunk_tokens = tokenize(str(row.get("text") or ""))
        inter = len(q_tokens & chunk_tokens)
        union = len(q_tokens | chunk_tokens) or 1
        score = inter / union
        if score <= 0:
            continue
        meta_raw = row.get("metadata_json")
        metadata = meta_raw if isinstance(meta_raw, dict) else json.loads(meta_raw or "{}")
        support_type = "document_backed" if score >= 0.16 else "weak_support"
        confidence = "high" if score >= 0.26 else "medium" if score >= 0.16 else "low"
        scored.append(
            (
                score,
                {
                    "chunk_id": row.get("id"),
                    "chunk_index": row.get("chunk_index"),
                    "document_id": row.get("document_id"),
                    "document_name": row.get("display_name") or row.get("filename"),
                    "matter_id": row.get("matter_id"),
                    "office_id": row.get("office_id"),
                    "excerpt": str(row.get("text") or "")[:320],
                    "relevance_score": round(score, 4),
                    "source_type": row.get("source_type") or metadata.get("source_type") or "upload",
                    "support_type": support_type,
                    "confidence": confidence,
                    "metadata": metadata,
                    "line_anchor": metadata.get("line_anchor"),
                    "page": metadata.get("page"),
                    "line_start": metadata.get("line_start"),
                    "line_end": metadata.get("line_end"),
                },
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored[:k]]


class RAGStore(Protocol):
    def add_document(self, filename: str, content: bytes) -> dict: ...

    def search(self, query: str, k: int = 3) -> list[dict]: ...

    def runtime_meta(self) -> dict: ...


class InMemoryRAGStore:
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []

    def runtime_meta(self) -> dict:
        return {
            "backend": "inmemory",
            "mode": "default",
            "ready": True,
            "warning": None,
        }

    def add_document(self, filename: str, content: bytes) -> dict:
        text = content.decode("utf-8", errors="ignore")
        count = 0
        for chunk in chunk_text(text):
            part = chunk["text"]
            if not part.strip():
                continue
            meta = chunk["metadata"]
            digest = hashlib.sha256(f"{filename}:{meta['line_start']}:{meta['line_end']}:{part[:60]}".encode()).hexdigest()[:16]
            self._chunks.append(
                Chunk(
                    chunk_id=digest,
                    document=filename,
                    text=part,
                    page=int(meta["page"]),
                    line_start=int(meta["line_start"]),
                    line_end=int(meta["line_end"]),
                    embedding=tokenize(part),
                )
            )
            count += 1
        return {"indexed_chunks": count, "document": filename}

    def search(self, query: str, k: int = 3) -> list[dict]:
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scored = []
        for chunk in self._chunks:
            inter = len(q_tokens & chunk.embedding)
            union = len(q_tokens | chunk.embedding) or 1
            score = inter / union
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, c in scored[:k]:
            out.append(
                {
                    "document": c.document,
                    "page": c.page,
                    "line_start": c.line_start,
                    "line_end": c.line_end,
                    "line_anchor": f"{c.document}#L{c.line_start}",
                    "score": round(score, 4),
                    "snippet": c.text[:220],
                    "chunk_id": c.chunk_id,
                }
            )
        return out


class PgVectorTransitionStore:
    """Transition-safe store.

    Stage-0/1 behavior keeps retrieval functional with in-memory indexing,
    while exposing pgvector migration metadata expected by downstream clients.
    """

    def __init__(self, tenant_id: str = "default", requested_backend: str = "pgvector-transition") -> None:
        self._delegate = InMemoryRAGStore()
        self._tenant_id = tenant_id
        self._requested_backend = requested_backend

    def runtime_meta(self) -> dict:
        fallback_mode = self._requested_backend == "pgvector"
        return {
            "backend": "pgvector-transition",
            "mode": "fallback" if fallback_mode else "transition",
            "ready": True,
            "warning": (
                "pgvector requested but transition backend is active; embeddings are currently kept in-memory"
                if fallback_mode
                else "pgvector transition backend active"
            ),
            "tenant_id": self._tenant_id,
            "migration_phase": "stage-1-dual-write-ready",
        }

    def add_document(self, filename: str, content: bytes) -> dict:
        base = self._delegate.add_document(filename, content)
        base["backend"] = "pgvector-transition"
        base["tenant_id"] = self._tenant_id
        base["migration_phase"] = "stage-1-dual-write-ready"
        return base

    def search(self, query: str, k: int = 3) -> list[dict]:
        rows = self._delegate.search(query, k=k)
        for row in rows:
            row["backend"] = "pgvector-transition"
            row["tenant_id"] = self._tenant_id
        return rows

    @staticmethod
    def bootstrap_sql() -> str:
        return """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunks (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  document_name TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  page INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding VECTOR(768) NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_tenant ON rag_chunks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
  ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
""".strip()


def create_rag_store(backend: str = "inmemory", tenant_id: str = "default") -> RAGStore:
    normalized = (backend or "inmemory").strip().lower()
    if normalized in {"pgvector", "pgvector-transition"}:
        return PgVectorTransitionStore(tenant_id=tenant_id, requested_backend=normalized)
    return InMemoryRAGStore()
