from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .retrieval import LocalHybridRetrievalBackend, SQLiteFTSRetrievalBackend


@dataclass(frozen=True)
class RetrievalPipelineConfig:
    backend: str
    pipeline: str
    dense_candidates_enabled: bool
    semantic_backend: str
    dense_candidate_backend: str
    reranker_mode: str
    embedding_model_name: str
    cross_encoder_model_name: str
    reranker_ready: bool
    vector_ready: bool


def build_retrieval_backend(
    *,
    search_backend: str,
    system_dir: Path,
    dense_candidates_enabled: bool = False,
    semantic_backend: str = "heuristic",
    embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    cross_encoder_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    reranker_mode: str = "local_heuristic",
) -> tuple[Any, RetrievalPipelineConfig]:
    normalized_search_backend = str(search_backend or "sqlite_hybrid_fts_v1").strip().lower()
    normalized_reranker_mode = str(reranker_mode or "local_heuristic").strip().lower() or "local_heuristic"
    normalized_semantic_backend = str(semantic_backend or "heuristic").strip().lower() or "heuristic"
    fallback = LocalHybridRetrievalBackend()
    if normalized_search_backend in {"sqlite_hybrid_fts_v1", "sqlite", "sqlite_hybrid", "fts"}:
        backend = SQLiteFTSRetrievalBackend(
            system_dir / "search-index.db",
            fallback_backend=fallback,
            dense_candidates_enabled=bool(dense_candidates_enabled),
            semantic_backend=normalized_semantic_backend,
            embedding_model_name=embedding_model_name,
            cross_encoder_model_name=cross_encoder_model_name,
            reranker_mode=normalized_reranker_mode,
        )
        config = RetrievalPipelineConfig(
            backend=backend.name,
            pipeline=(
                "sqlite_fts_model_semantic_rerank_v1"
                if normalized_semantic_backend == "model_local"
                else ("sqlite_fts_dense_rerank_v1" if dense_candidates_enabled else "sqlite_fts_plus_local_semantic")
            ),
            dense_candidates_enabled=bool(dense_candidates_enabled),
            semantic_backend=normalized_semantic_backend,
            dense_candidate_backend=(
                "sentence_transformer_local"
                if normalized_semantic_backend == "model_local"
                else ("local_semantic_projection" if dense_candidates_enabled else "disabled")
            ),
            reranker_mode=normalized_reranker_mode,
            embedding_model_name=embedding_model_name,
            cross_encoder_model_name=cross_encoder_model_name,
            reranker_ready=bool(getattr(backend, "reranker_hook_ready", False)),
            vector_ready=bool(getattr(backend, "vector_hook_ready", False)),
        )
        return backend, config
    backend = fallback
    config = RetrievalPipelineConfig(
        backend=backend.name,
        pipeline="local_hybrid_semantic",
        dense_candidates_enabled=bool(dense_candidates_enabled),
        semantic_backend=normalized_semantic_backend,
        dense_candidate_backend="inline_document_projection" if dense_candidates_enabled else "disabled",
        reranker_mode=normalized_reranker_mode,
        embedding_model_name=embedding_model_name,
        cross_encoder_model_name=cross_encoder_model_name,
        reranker_ready=bool(getattr(backend, "reranker_hook_ready", False)),
        vector_ready=bool(getattr(backend, "vector_hook_ready", False)),
    )
    return backend, config
