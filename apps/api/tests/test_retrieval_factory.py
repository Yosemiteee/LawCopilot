from __future__ import annotations

import tempfile
from pathlib import Path

import lawcopilot_api.knowledge_base.retrieval as retrieval_module
from lawcopilot_api.knowledge_base.retrieval_factory import build_retrieval_backend
from lawcopilot_api.knowledge_base.service import KnowledgeBaseService


def test_build_retrieval_backend_reports_pipeline_configuration() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-retrieval-factory-"))
    backend, config = build_retrieval_backend(
        search_backend="sqlite",
        system_dir=temp_dir,
        dense_candidates_enabled=True,
        reranker_mode="local_crosscheck",
    )

    assert backend.name == "sqlite_hybrid_fts_v1"
    assert config.pipeline == "sqlite_fts_dense_rerank_v1"
    assert config.dense_candidates_enabled is True
    assert config.reranker_mode == "local_crosscheck"


def test_knowledge_base_search_exposes_pipeline_metadata() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-retrieval-service-"))
    service = KnowledgeBaseService(
        temp_dir,
        "default-office",
        enabled=True,
        search_backend="sqlite",
        dense_candidates_enabled=True,
        reranker_mode="local_crosscheck",
    )

    result = service.search("mesaj tercihi", limit=4)

    assert result["ranking_profile"]["pipeline"]["dense_candidates_enabled"] is True
    assert result["ranking_profile"]["pipeline"]["reranker_mode"] == "local_crosscheck"
    assert result["ranking_profile"]["pipeline"]["backend"] == "sqlite_hybrid_fts_v1"


def test_dense_candidate_pipeline_surfaces_semantic_reranker_reason() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-retrieval-rerank-"))
    service = KnowledgeBaseService(
        temp_dir,
        "default-office",
        enabled=True,
        search_backend="sqlite",
        dense_candidates_enabled=True,
        reranker_mode="local_crosscheck",
    )
    service.ingest(
        source_type="user_preferences",
        title="E-posta tarzı",
        content="Mail yanıtları kısa, net ve nazik olmalı.",
        metadata={"field": "communication_style", "scope": "personal"},
        tags=["email", "style"],
    )

    result = service.search("mail tarzim", scopes=["personal"], limit=4)

    assert result["items"]
    assert "semantic_reranker" in result["items"][0]["selection_reasons"]


def test_retrieval_surfaces_context_metadata_ranking_reasons() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-retrieval-metadata-"))
    service = KnowledgeBaseService(
        temp_dir,
        "default-office",
        enabled=True,
        search_backend="sqlite",
        dense_candidates_enabled=True,
        reranker_mode="local_crosscheck",
    )
    service.ingest(
        source_type="profile_snapshot",
        title="İletişim tercihi",
        content="Kullanıcı kısa ve net cevapları tercih ediyor.",
        metadata={"field": "communication_style", "scope": "personal", "page_key": "preferences"},
        tags=["profile", "style"],
    )

    result = service.search("iletişim tercihim", scopes=["personal"], limit=4)

    assert result["items"]
    reasons = set(result["items"][0]["selection_reasons"])
    assert "source_type_match" in reasons or "trust_level" in reasons


def test_model_local_pipeline_uses_optional_model_backends_when_available(monkeypatch) -> None:
    monkeypatch.setattr(retrieval_module, "sentence_embedding_backend_available", lambda model_name: True)
    monkeypatch.setattr(retrieval_module, "cross_encoder_backend_available", lambda model_name: True)
    monkeypatch.setattr(
        retrieval_module,
        "model_semantic_scores",
        lambda *, query, texts, model_name: [0.91 if "kısa, net ve nazik" in text or "kisa, net ve nazik" in text else 0.08 for text in texts],
    )
    monkeypatch.setattr(
        retrieval_module,
        "model_reranker_scores",
        lambda *, query, texts, model_name: [0.87 if "kısa, net ve nazik" in text or "kisa, net ve nazik" in text else 0.04 for text in texts],
    )

    temp_dir = Path(tempfile.mkdtemp(prefix="lawcopilot-retrieval-model-local-"))
    service = KnowledgeBaseService(
        temp_dir,
        "default-office",
        enabled=True,
        search_backend="sqlite",
        dense_candidates_enabled=True,
        semantic_backend="model_local",
        reranker_mode="model_cross_encoder",
    )
    service.ingest(
        source_type="user_preferences",
        title="E-posta tarzı",
        content="Mail yanıtları kısa, net ve nazik olmalı.",
        metadata={"field": "communication_style", "scope": "personal"},
        tags=["email", "style"],
    )

    result = service.search("mail tarzim", scopes=["personal"], limit=4)

    assert result["items"]
    assert result["ranking_profile"]["pipeline"]["semantic_backend"] == "model_local"
    assert result["ranking_profile"]["pipeline"]["vector_ready"] is True
    assert result["ranking_profile"]["pipeline"]["reranker_ready"] is True
    assert "semantic_reranker" in result["items"][0]["selection_reasons"]
