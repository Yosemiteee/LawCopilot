from __future__ import annotations

from functools import lru_cache
import math
from typing import Any


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dot_similarity(left: Any, right: Any) -> float:
    try:
        if hasattr(left, "tolist"):
            left = left.tolist()
        if hasattr(right, "tolist"):
            right = right.tolist()
        if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
            return 0.0
        limit = min(len(left), len(right))
        if limit <= 0:
            return 0.0
        return sum(_safe_float(left[index]) * _safe_float(right[index]) for index in range(limit))
    except Exception:
        return 0.0


@lru_cache(maxsize=4)
def _load_sentence_transformer(model_name: str) -> Any | None:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        return None
    try:
        return SentenceTransformer(model_name)
    except Exception:
        return None


@lru_cache(maxsize=4)
def _load_cross_encoder(model_name: str) -> Any | None:
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except Exception:
        return None
    try:
        return CrossEncoder(model_name)
    except Exception:
        return None


def sentence_embedding_backend_available(model_name: str) -> bool:
    return _load_sentence_transformer(str(model_name or "").strip()) is not None


def cross_encoder_backend_available(model_name: str) -> bool:
    return _load_cross_encoder(str(model_name or "").strip()) is not None


def model_semantic_scores(*, query: str, texts: list[str], model_name: str) -> list[float] | None:
    model = _load_sentence_transformer(str(model_name or "").strip())
    if model is None or not texts:
        return None
    try:
        embeddings = model.encode([query, *texts], normalize_embeddings=True, show_progress_bar=False)
    except TypeError:
        embeddings = model.encode([query, *texts], normalize_embeddings=True)
    except Exception:
        return None
    if embeddings is None or len(embeddings) < 2:
        return None
    query_embedding = embeddings[0]
    document_embeddings = embeddings[1:]
    return [max(0.0, min(1.0, _dot_similarity(query_embedding, doc_embedding))) for doc_embedding in document_embeddings]


def model_reranker_scores(*, query: str, texts: list[str], model_name: str) -> list[float] | None:
    model = _load_cross_encoder(str(model_name or "").strip())
    if model is None or not texts:
        return None
    pairs = [(query, text) for text in texts]
    try:
        scores = model.predict(pairs, show_progress_bar=False)
    except TypeError:
        scores = model.predict(pairs)
    except Exception:
        return None
    normalized: list[float] = []
    for value in list(scores):
        raw = _safe_float(value)
        probability = 1.0 / (1.0 + math.exp(-raw))
        normalized.append(max(0.0, min(1.0, probability)))
    return normalized
