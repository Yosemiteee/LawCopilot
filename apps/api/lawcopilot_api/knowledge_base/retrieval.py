from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Protocol

from .semantic_models import (
    cross_encoder_backend_available,
    model_reranker_scores,
    model_semantic_scores,
    sentence_embedding_backend_available,
)
from .models import KnowledgeSearchHit


_ASCII_TRANSLATION = str.maketrans({
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
})

QUERY_TERM_SYNONYMS: dict[str, tuple[str, ...]] = {
    "mail": ("email", "eposta"),
    "email": ("mail", "eposta"),
    "eposta": ("email", "mail"),
    "yanit": ("cevap", "reply", "taslak"),
    "cevap": ("yanit", "reply", "taslak"),
    "taslak": ("draft", "yanit", "cevap"),
    "hatirla": ("ozet", "not", "gecmis"),
    "ozet": ("hatirla", "summary", "not"),
    "musteri": ("muvekkil", "client"),
    "muvekkil": ("musteri", "client"),
    "crm": ("api", "rest", "entegrasyon"),
    "api": ("rest", "endpoint", "entegrasyon"),
    "veritabani": ("database", "kayit", "query"),
    "database": ("veritabani", "kayit", "query"),
    "mesaj": ("iletisim", "yazisma"),
    "iletisim": ("mesaj", "yazisma"),
    "yazisma": ("mesaj", "iletisim"),
    "konum": ("lokasyon", "yer", "mekan"),
    "lokasyon": ("konum", "yer", "mekan"),
    "yer": ("konum", "mekan", "lokasyon"),
    "mekan": ("yer", "konum", "lokasyon"),
    "cami": ("mescit",),
    "mescit": ("cami",),
    "hatirlatma": ("reminder", "gorev", "uyari"),
    "reminder": ("hatirlatma", "gorev", "uyari"),
    "gorev": ("task", "hatirlatma", "todo"),
    "task": ("gorev", "todo"),
    "plan": ("program", "takvim"),
    "takvim": ("plan", "ajanda"),
    "ajanda": ("takvim", "plan"),
    "ulasim": ("seyahat", "tren", "metro"),
    "seyahat": ("ulasim", "tren", "metro"),
    "tren": ("ulasim", "seyahat"),
    "karar": ("gerekce", "risk"),
    "gerekce": ("karar", "risk"),
    "risk": ("karar", "gerekce"),
    "tercih": ("tarz", "stil", "aliskanlik"),
    "tarz": ("tercih", "stil"),
    "stil": ("tercih", "tarz"),
    "aliskanlik": ("tercih", "rutin"),
    "rutin": ("aliskanlik", "tercih"),
    "gecmis": ("history", "feedback", "oneri"),
    "oneri": ("recommendation", "gecmis", "feedback"),
    "feedback": ("gecmis", "oneriler"),
    "youtube": ("video", "izleme", "watch", "kanal"),
    "video": ("youtube", "izleme", "watch"),
    "izleme": ("video", "youtube", "watch"),
    "watch": ("video", "youtube", "izleme"),
    "okuma": ("reading", "kitap", "makale", "bookmark"),
    "reading": ("okuma", "kitap", "makale", "bookmark"),
    "kitap": ("okuma", "reading"),
    "makale": ("okuma", "reading", "article"),
    "bookmark": ("okuma", "reading", "saved_link"),
    "alisveris": ("shopping", "market", "grocery"),
    "alışveriş": ("shopping", "market", "grocery"),
    "shopping": ("alisveris", "alışveriş", "market"),
    "hedef": ("goal", "plan", "coach"),
    "goal": ("hedef", "plan", "coach"),
    "koc": ("coach", "mentor", "hedef"),
    "koç": ("coach", "mentor", "hedef"),
    "coach": ("koc", "koç", "mentor", "goal"),
    "mentor": ("coach", "goal", "plan"),
}

INTENT_HINT_TOKENS: dict[str, tuple[str, ...]] = {
    "decision": ("decision", "risk", "karar", "gerekce"),
    "profile": ("preference", "persona", "rutin", "ton", "stil"),
    "location": ("konum", "yakin", "rota", "yer"),
    "legal": ("legal", "matter", "muvekkil", "dosya"),
    "proactive": ("oneri", "plan", "takvim", "nudge"),
    "recent": ("recent", "bugun", "yakinda"),
    "history": ("gecmis", "feedback", "oneri"),
    "reflection": ("reflection", "drift", "celiski"),
    "memory": ("hatirla", "ozet", "preference", "wiki"),
    "consumer": ("youtube", "video", "reading", "bookmark", "shopping", "travel"),
    "coaching": ("goal", "hedef", "coach", "mentor", "progress", "habit"),
}


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _ascii_fold(value: str | None) -> str:
    return _normalize_text(value).translate(_ASCII_TRANSLATION)


def _tokenize(value: str | None) -> list[str]:
    base_tokens = [token for token in re.findall(r"[a-z0-9çğıöşü]+", _normalize_text(value)) if len(token) >= 2]
    tokens: list[str] = []
    seen: set[str] = set()
    for token in base_tokens:
        if token not in seen:
            seen.add(token)
            tokens.append(token)
        folded = _ascii_fold(token)
        if len(folded) >= 2 and folded not in seen:
            seen.add(folded)
            tokens.append(folded)
    return tokens


def _root_forms(token: str) -> list[str]:
    normalized = _ascii_fold(token)
    if len(normalized) < 4:
        return []
    roots = {normalized[:4]}
    if len(normalized) >= 6:
        roots.add(normalized[:5])
    return sorted(roots)


def _char_trigrams(value: str | None) -> list[str]:
    folded = re.sub(r"[^a-z0-9]+", "", _ascii_fold(value))
    if len(folded) < 3:
        return []
    grams = [folded[index : index + 3] for index in range(0, len(folded) - 2)]
    return list(dict.fromkeys(grams[:48]))


def _semantic_embedding_from_tokens(
    *,
    title: str,
    summary: str,
    page_text: str,
    metadata_text: str,
    token_weights: Counter[str],
) -> dict[str, float]:
    weighted = Counter[str]()
    for token, weight in token_weights.items():
        normalized = _ascii_fold(token)
        if len(normalized) < 2:
            continue
        weighted[f"tok:{normalized}"] += float(weight)
        for synonym in QUERY_TERM_SYNONYMS.get(normalized, ()):
            synonym_token = _ascii_fold(synonym)
            if len(synonym_token) >= 2:
                weighted[f"tok:{synonym_token}"] += float(weight) * 0.45
        for root in _root_forms(normalized):
            weighted[f"root:{root}"] += float(weight) * 0.22
    for trigram in _char_trigrams(f"{title} {summary}"):
        weighted[f"tri:{trigram}"] += 0.16
    for trigram in _char_trigrams(f"{page_text} {metadata_text}")[:18]:
        weighted[f"tri:{trigram}"] += 0.08
    if not weighted:
        return {}
    top_terms = sorted(weighted.items(), key=lambda item: (-item[1], item[0]))[:80]
    norm = math.sqrt(sum(value * value for _, value in top_terms))
    if norm <= 0:
        return {}
    return {key: round(value / norm, 6) for key, value in top_terms}


def _semantic_query_embedding(query: str) -> dict[str, float]:
    tokens = _tokenize(query)
    intents = _query_intents(tokens)
    expanded = _expand_query_tokens(tokens, intents)
    weights = Counter[str]()
    for token in tokens:
        weights[token] += 2.4
    for token in expanded:
        weights[token] += 1.2
    for intent in intents:
        for hint in INTENT_HINT_TOKENS.get(intent, ()):
            normalized = _ascii_fold(hint)
            if len(normalized) >= 2:
                weights[normalized] += 0.9
    return _semantic_embedding_from_tokens(
        title=query,
        summary=" ".join(expanded[:8]),
        page_text=" ".join(sorted(intents)),
        metadata_text=query,
        token_weights=weights,
    )


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    score = sum(float(weight) * float(right.get(key, 0.0)) for key, weight in left.items())
    return max(0.0, min(1.0, score))


def _query_intents(tokens: list[str]) -> set[str]:
    token_set = set(tokens)
    intents: set[str] = set()
    token_prefixes = list(token_set)
    if token_set.intersection({"neden", "why", "gerekce", "gerekçe", "risk", "karar"}) or any(
        token.startswith(prefix) for token in token_prefixes for prefix in ("karar", "risk")
    ):
        intents.add("decision")
    if token_set.intersection({"tercih", "tarz", "ton", "stil", "alışkanlık", "aliskanlik", "rutin"}) or any(
        token.startswith(prefix) for token in token_prefixes for prefix in ("tercih", "rutin", "alışkan", "aliskan")
    ):
        intents.add("profile")
    if token_set.intersection({"yakın", "yakin", "konum", "yer", "mekan", "cami", "kafe", "market"}) or any(
        token.startswith(prefix) for token in token_prefixes for prefix in ("konum", "mek", "yer", "cami", "kafe", "market", "yak")
    ):
        intents.add("location")
    if token_set.intersection({"dosya", "dava", "müvekkil", "musteri", "matter", "legal", "tahliye"}) or any(
        token.startswith(prefix) for token in token_prefixes for prefix in ("dava", "dosya", "müv", "must", "legal", "tahli")
    ):
        intents.add("legal")
    if token_set.intersection({"öner", "oner", "plan", "gün", "gun", "takvim", "yoğun", "yogun"}) or any(
        token.startswith(prefix) for token in token_prefixes for prefix in ("öner", "oner", "plan", "takvim", "yoğun", "yogun")
    ):
        intents.add("proactive")
    if token_set.intersection({"son", "bugün", "today", "recent", "az", "önce", "once", "yakınlarda"}) or any(
        token.startswith(prefix) for token in token_prefixes for prefix in ("bug", "recent", "yak", "ön", "on")
    ):
        intents.add("recent")
    if token_set.intersection({"feedback", "redded", "accepted", "kabul", "öneri", "oneri", "geçmiş", "gecmis"}) or any(
        token.startswith(prefix) for token in token_prefixes for prefix in ("feedback", "redd", "kabul", "öner", "oneri", "geç", "gec")
    ):
        intents.add("history")
    if token_set.intersection({"reflection", "lint", "sağlık", "saglik", "drift", "çelişki", "celiski"}) or any(
        token.startswith(prefix) for token in token_prefixes for prefix in ("reflect", "lint", "sağ", "sag", "drift", "çeli", "celi")
    ):
        intents.add("reflection")
    if token_set.intersection({"youtube", "video", "watch", "reading", "okuma", "bookmark", "shopping", "alışveriş", "alisveris"}) or any(
        token.startswith(prefix) for token in token_prefixes for prefix in ("youtube", "video", "watch", "read", "okum", "book", "shop", "alis", "alış")
    ):
        intents.add("consumer")
    if token_set.intersection({"hedef", "goal", "koç", "koc", "coach", "mentor", "alışkanlık", "aliskanlik", "progress"}) or any(
        token.startswith(prefix) for token in token_prefixes for prefix in ("hedef", "goal", "coach", "mentor", "alış", "alis", "habit", "progress")
    ):
        intents.add("coaching")
    return intents


def _expand_query_tokens(tokens: list[str], intents: set[str]) -> list[str]:
    expanded: list[str] = []
    seen = set(tokens)
    for token in tokens:
        for synonym in QUERY_TERM_SYNONYMS.get(token, ()):
            normalized = _ascii_fold(synonym)
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            expanded.append(normalized)
    for intent in intents:
        for hint in INTENT_HINT_TOKENS.get(intent, ()):
            normalized = _ascii_fold(hint)
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            expanded.append(normalized)
    return expanded[:16]


@dataclass
class RetrievalQuery:
    query: str
    scopes: list[str]
    page_keys: list[str]
    limit: int
    include_decisions: bool
    include_reflections: bool
    metadata_filters: dict[str, Any]
    record_types: list[str]


class KnowledgeRetrievalBackend(Protocol):
    name: str

    def search(
        self,
        *,
        state: dict[str, Any],
        request: RetrievalQuery,
        envelope_resolver: Callable[[str, dict[str, Any]], dict[str, Any]],
        scope_matcher: Callable[[str, list[str]], bool],
        epistemic_resolver: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> list[dict[str, Any]]:
        ...


def _datetime_or_none(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _json_marker(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class LocalHybridRetrievalBackend:
    name = "local_hybrid_bm25_v1"
    ranking_profile = "local_hybrid_semantic_v3"
    vector_hook_ready = False
    reranker_hook_ready = False

    page_weight_defaults = {
        "persona": 1.04,
        "preferences": 1.08,
        "routines": 1.03,
        "contacts": 1.01,
        "projects": 1.06,
        "legal": 1.08,
        "decisions": 1.02,
        "reflections": 1.0,
        "recommendations": 1.0,
        "places": 1.0,
    }

    def search(
        self,
        *,
        state: dict[str, Any],
        request: RetrievalQuery,
        envelope_resolver: Callable[[str, dict[str, Any]], dict[str, Any]],
        scope_matcher: Callable[[str, list[str]], bool],
        epistemic_resolver: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> list[dict[str, Any]]:
        documents = self.collect_documents(
            state=state,
            request=request,
            envelope_resolver=envelope_resolver,
            scope_matcher=scope_matcher,
            epistemic_resolver=epistemic_resolver,
        )
        if not documents:
            return []
        return self.score_documents(documents=documents, request=request)

    def collect_documents(
        self,
        *,
        state: dict[str, Any],
        request: RetrievalQuery,
        envelope_resolver: Callable[[str, dict[str, Any]], dict[str, Any]],
        scope_matcher: Callable[[str, list[str]], bool],
        epistemic_resolver: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        requested_pages = {str(item).strip() for item in request.page_keys if str(item).strip()}
        requested_scopes = [str(item).strip() for item in request.scopes if str(item).strip()]
        requested_record_types = {str(item).strip() for item in request.record_types if str(item).strip()}
        requested_metadata = {
            str(key).strip(): value
            for key, value in dict(request.metadata_filters or {}).items()
            if str(key).strip()
        }

        for page_key, page in (state.get("pages") or {}).items():
            if requested_pages and page_key not in requested_pages:
                continue
            if page_key == "decisions" and not request.include_decisions:
                continue
            if page_key == "reflections" and not request.include_reflections:
                continue
            for record in page.get("records") or []:
                if not isinstance(record, dict):
                    continue
                if str(record.get("status") or "active") != "active":
                    continue
                envelope = envelope_resolver(page_key, record)
                scope = str(envelope.get("scope") or "")
                if requested_scopes and not scope_matcher(scope, requested_scopes):
                    continue
                record_type = str(envelope.get("record_type") or "")
                if requested_record_types and record_type not in requested_record_types:
                    continue
                metadata = dict(envelope.get("metadata") or {})
                metadata.setdefault("source_type", str(metadata.get("source_type") or "knowledge_record"))
                epistemic = epistemic_resolver(page_key, record, envelope) if epistemic_resolver is not None else None
                if isinstance(epistemic, dict):
                    metadata["epistemic_status"] = str(epistemic.get("status") or "")
                    metadata["epistemic_basis"] = str(epistemic.get("current_basis") or "")
                    metadata["epistemic_validation_state"] = str(epistemic.get("validation_state") or "")
                    metadata["epistemic_consent_class"] = str(epistemic.get("consent_class") or "")
                    metadata["epistemic_retrieval_eligibility"] = str(epistemic.get("retrieval_eligibility") or "")
                    metadata["epistemic_current_claim_id"] = str(epistemic.get("current_claim_id") or "")
                    metadata["epistemic_subject_key"] = str(epistemic.get("current_subject_key") or epistemic.get("subject_key") or "")
                    metadata["epistemic_predicate"] = str(epistemic.get("current_predicate") or epistemic.get("predicate") or "")
                    metadata["epistemic_current_value"] = str(epistemic.get("current_value_text") or "")
                    metadata["epistemic_display_label"] = str(epistemic.get("display_label") or "")
                    metadata["epistemic_support_strength"] = str(epistemic.get("support_strength") or "")
                    metadata["epistemic_support_contaminated"] = bool(epistemic.get("support_contaminated"))
                    metadata["epistemic_external_support_count"] = int(epistemic.get("external_support_count") or 0)
                    metadata["epistemic_self_generated_support_count"] = int(epistemic.get("self_generated_support_count") or 0)
                    metadata["epistemic_memory_tier"] = str(epistemic.get("memory_tier") or "")
                    metadata["epistemic_salience_score"] = float(epistemic.get("salience_score") or 0.0)
                    metadata["epistemic_age_days"] = epistemic.get("age_days")
                retrieval_eligibility = str(metadata.get("epistemic_retrieval_eligibility") or "eligible").strip().lower()
                if retrieval_eligibility in {"blocked", "quarantined"} and str(requested_metadata.get("epistemic_retrieval_eligibility") or "").strip().lower() not in {
                    "blocked",
                    "quarantined",
                }:
                    continue
                contaminated = bool(metadata.get("epistemic_support_contaminated"))
                if contaminated and str(requested_metadata.get("epistemic_status") or "").strip().lower() != "contaminated":
                    continue
                if not self._metadata_matches(metadata, requested_metadata):
                    continue
                documents.append(
                    self._build_document(page_key=page_key, record=record, envelope=envelope, metadata=metadata)
                )
        return documents

    def score_documents(
        self,
        *,
        documents: list[dict[str, Any]],
        request: RetrievalQuery,
        extra_scores: dict[str, float] | None = None,
        extra_reason_map: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        query_tokens = _tokenize(request.query)
        if not query_tokens:
            return []
        query_text = _normalize_text(request.query)
        query_intents = _query_intents(query_tokens)
        expanded_query_tokens = _expand_query_tokens(query_tokens, query_intents)
        avg_length = sum(doc["doc_length"] for doc in documents) / max(len(documents), 1)
        dfs = self._document_frequencies(documents)
        scored: list[tuple[float, dict[str, Any]]] = []
        for document in documents:
            score, hit = self._score_document(
                document=document,
                request=request,
                query_tokens=query_tokens,
                expanded_query_tokens=expanded_query_tokens,
                query_text=query_text,
                query_intents=query_intents,
                dfs=dfs,
                total_docs=len(documents),
                avg_length=avg_length,
                extra_score=float((extra_scores or {}).get(str(document.get("doc_key") or ""), 0.0)),
                extra_reasons=list((extra_reason_map or {}).get(str(document.get("doc_key") or ""), [])),
            )
            if score <= 0:
                continue
            scored.append((score, hit))

        scored.sort(
            key=lambda item: (
                -item[0],
                -self._updated_rank(item[1].get("updated_at")),
                str(item[1].get("title") or ""),
            )
        )
        return self._diversify_hits(
            [item for _, item in scored],
            limit=max(1, min(request.limit, 20)),
            query_intents=query_intents,
        )

    def _score_document(
        self,
        *,
        document: dict[str, Any],
        request: RetrievalQuery,
        query_tokens: list[str],
        expanded_query_tokens: list[str],
        query_text: str,
        query_intents: set[str],
        dfs: Counter[str],
        total_docs: int,
        avg_length: float,
        extra_score: float = 0.0,
        extra_reasons: list[str] | None = None,
    ) -> tuple[float, dict[str, Any]]:
        bm25_score = self._bm25_score(query_tokens, document, dfs, total_docs, avg_length)
        expansion_bonus = self._expanded_bm25_score(
            expanded_query_tokens=expanded_query_tokens,
            document=document,
            dfs=dfs,
            total_docs=total_docs,
            avg_length=avg_length,
        )
        if bm25_score <= 0 and extra_score <= 0 and expansion_bonus <= 0:
            return 0.0, {}
        score = bm25_score + extra_score
        reasons: list[str] = list(extra_reasons or [])
        if bm25_score > 0.6:
            reasons.append("token_overlap")
        score += expansion_bonus
        if expansion_bonus > 0:
            reasons.append("semantic_expansion")
        phrase_bonus = self._phrase_bonus(query_text, document)
        score += phrase_bonus
        if phrase_bonus > 0:
            reasons.append("exact_phrase")
        scope_bonus = self._scope_bonus(request.scopes, document)
        score += scope_bonus
        if scope_bonus > 0:
            reasons.append("scope_match")
        page_intent_bonus = self._page_intent_bonus(query_tokens, document["page_key"])
        score += page_intent_bonus
        if query_intents and self._page_matches_intent(document["page_key"], query_intents):
            reasons.append("page_intent_match")
        intent_bonus = self._intent_bonus(query_intents, document["page_key"], document["metadata"])
        score += intent_bonus
        if intent_bonus > 0:
            reasons.append("query_intent_match")
        relation_bonus = self._relation_bonus(query_intents, document["metadata"])
        score += relation_bonus
        if relation_bonus > 0:
            reasons.append("relation_match")
        semantic_bonus = self._semantic_vector_bonus(document=document, request=request)
        score += semantic_bonus
        if semantic_bonus > 0:
            reasons.append("semantic_vector_match")
        source_bonus = self._source_type_bonus(query_intents, document["metadata"])
        score += source_bonus
        if source_bonus > 0:
            reasons.append("source_type_match")
        trust_bonus = self._trust_level_bonus(document["metadata"])
        score += trust_bonus
        if trust_bonus > 0:
            reasons.append("trust_level")
        support_bonus = self._epistemic_support_bonus(document["metadata"])
        score += support_bonus
        if support_bonus > 0:
            reasons.append("epistemic_grounded")
        support_penalty = self._epistemic_support_penalty(document["metadata"])
        score -= support_penalty
        if support_penalty > 0:
            reasons.append("epistemic_penalty")
        consent_penalty = self._consent_penalty(document["metadata"])
        score -= consent_penalty
        if consent_penalty > 0:
            reasons.append("consent_restriction")
        memory_bonus = self._epistemic_memory_bonus(document["metadata"])
        score += memory_bonus
        if memory_bonus > 0:
            reasons.append("memory_tier_bonus")
        memory_penalty = self._epistemic_memory_penalty(document["metadata"])
        score -= memory_penalty
        if memory_penalty > 0:
            reasons.append("memory_tier_penalty")
        metadata_bonus = self._metadata_keyword_bonus(query_tokens, document["metadata"])
        score += metadata_bonus
        if metadata_bonus > 0:
            reasons.append("metadata_match")
        confidence_bonus = self._confidence_bonus(document["metadata"])
        score += confidence_bonus
        if confidence_bonus > 0:
            reasons.append("high_confidence")
        low_confidence_penalty = self._low_confidence_penalty(document["metadata"])
        score -= low_confidence_penalty
        if low_confidence_penalty > 0:
            reasons.append("low_confidence_penalty")
        priority_bonus = self._priority_bonus(document["metadata"])
        score += priority_bonus
        if priority_bonus > 0:
            reasons.append("priority_weight")
        decay_penalty = self._decay_penalty(document["metadata"])
        score -= decay_penalty
        if decay_penalty > 0:
            reasons.append("decay_penalty")
        correction_penalty = self._correction_penalty(document["metadata"])
        score -= correction_penalty
        if correction_penalty > 0:
            reasons.append("correction_history_penalty")
        freshness_bonus = self._freshness_bonus(document["updated_at"])
        score += freshness_bonus
        if freshness_bonus > 0:
            reasons.append("freshness")
        recent_bonus = self._recent_intent_bonus(query_intents, document["updated_at"])
        score += recent_bonus
        if recent_bonus > 0:
            reasons.append("recent_activity_match")
        diversity_bonus = self._diversity_intent_bonus(query_intents, document)
        score += diversity_bonus
        if diversity_bonus > 0:
            reasons.append("result_diversity")
        score *= self.page_weight_defaults.get(document["page_key"], 1.0)
        hit = self._build_hit(document=document, score=score, reasons=reasons)
        return score, hit

    @staticmethod
    def _metadata_matches(metadata: dict[str, Any], requested_metadata: dict[str, Any]) -> bool:
        if not requested_metadata:
            return True
        for key, expected in requested_metadata.items():
            actual = metadata.get(key)
            if isinstance(expected, (list, tuple, set)):
                normalized = {str(item).strip() for item in expected if str(item).strip()}
                if str(actual).strip() not in normalized:
                    return False
                continue
            if isinstance(expected, dict):
                if not isinstance(actual, dict):
                    return False
                for child_key, child_expected in expected.items():
                    if str(actual.get(child_key)).strip() != str(child_expected).strip():
                        return False
                continue
            if str(actual).strip() != str(expected).strip():
                return False
        return True

    @staticmethod
    def _epistemic_support_bonus(metadata: dict[str, Any]) -> float:
        strength = str(metadata.get("epistemic_support_strength") or "").strip().lower()
        status = str(metadata.get("epistemic_status") or "").strip().lower()
        if status == "current" and strength == "grounded":
            return 0.1
        if strength == "supported":
            return 0.05
        return 0.0

    @staticmethod
    def _epistemic_support_penalty(metadata: dict[str, Any]) -> float:
        if bool(metadata.get("epistemic_support_contaminated")):
            return 0.45
        strength = str(metadata.get("epistemic_support_strength") or "").strip().lower()
        status = str(metadata.get("epistemic_status") or "").strip().lower()
        if status == "contested":
            return 0.08
        if strength == "weak":
            return 0.05
        return 0.0

    @staticmethod
    def _source_type_bonus(query_intents: set[str], metadata: dict[str, Any]) -> float:
        source_type = str(metadata.get("source_type") or "").strip().lower()
        if not source_type:
            return 0.0
        if "profile" in query_intents and source_type in {"user_preferences", "profile_snapshot", "assistant_runtime_snapshot"}:
            return 0.08
        if "location" in query_intents and source_type in {"location_events", "browser_context", "consumer_signal"}:
            return 0.05
        if "consumer" in query_intents and source_type in {"consumer_signal", "youtube_history", "reading_list", "shopping_signal", "travel_signal"}:
            return 0.05
        if "recent" in query_intents and source_type in {"messages", "email", "whatsapp", "telegram", "x_message", "instagram_message"}:
            return 0.03
        if source_type in {"profile_snapshot", "user_preferences"}:
            return 0.02
        return 0.0

    @staticmethod
    def _trust_level_bonus(metadata: dict[str, Any]) -> float:
        basis = str(metadata.get("epistemic_basis") or "").strip().lower()
        validation = str(metadata.get("epistemic_validation_state") or "").strip().lower()
        if basis == "user_explicit" and validation in {"user_confirmed", "source_supported"}:
            return 0.08
        if basis in {"connector_observed", "document_extracted"} and validation in {"source_supported", "user_confirmed"}:
            return 0.05
        if basis == "user_confirmed_inference":
            return 0.04
        return 0.0

    @staticmethod
    def _consent_penalty(metadata: dict[str, Any]) -> float:
        consent_class = str(metadata.get("epistemic_consent_class") or "").strip().lower()
        if consent_class == "blocked":
            return 0.2
        if consent_class == "preview_only":
            return 0.08
        return 0.0

    @staticmethod
    def _epistemic_memory_bonus(metadata: dict[str, Any]) -> float:
        tier = str(metadata.get("epistemic_memory_tier") or "").strip().lower()
        salience = float(metadata.get("epistemic_salience_score") or 0.0)
        if tier == "hot":
            return round(0.03 + min(0.05, salience * 0.05), 4)
        if tier == "warm":
            return round(0.01 + min(0.025, salience * 0.03), 4)
        return 0.0

    @staticmethod
    def _epistemic_memory_penalty(metadata: dict[str, Any]) -> float:
        tier = str(metadata.get("epistemic_memory_tier") or "").strip().lower()
        age_days = metadata.get("epistemic_age_days")
        if tier == "cold":
            return 0.06
        try:
            if age_days is not None and int(age_days) >= 180:
                return 0.03
        except (TypeError, ValueError):
            return 0.0
        return 0.0

    def _build_document(
        self,
        *,
        page_key: str,
        record: dict[str, Any],
        envelope: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        title = str(record.get("title") or "")
        summary = str(record.get("summary") or "")
        page_text = " ".join(
            [
                page_key,
                str(metadata.get("field") or ""),
                str(metadata.get("connector_name") or ""),
                str(metadata.get("topic") or ""),
                str(metadata.get("recommendation_kind") or ""),
            ]
        )
        metadata_text = json.dumps(metadata, ensure_ascii=False)
        title_tokens = _tokenize(title)
        summary_tokens = _tokenize(summary)
        page_tokens = _tokenize(page_text)
        metadata_tokens = _tokenize(metadata_text)
        token_weights = Counter[str]()
        for token in title_tokens:
            token_weights[token] += 3
        for token in summary_tokens:
            token_weights[token] += 2
        for token in page_tokens:
            token_weights[token] += 1
        for token in metadata_tokens:
            token_weights[token] += 1
        doc_length = max(1, sum(token_weights.values()))
        doc_key = str(record.get("id") or f"{page_key}:{_hash_marker(title, summary, metadata)}")
        semantic_embedding = _semantic_embedding_from_tokens(
            title=title,
            summary=summary,
            page_text=page_text,
            metadata_text=metadata_text,
            token_weights=token_weights,
        )
        return {
            "doc_key": doc_key,
            "page_key": page_key,
            "record_id": record.get("id"),
            "title": title,
            "summary": summary,
            "record_type": envelope.get("record_type"),
            "scope": envelope.get("scope"),
            "sensitivity": envelope.get("sensitivity"),
            "exportability": envelope.get("exportability"),
            "model_routing_hint": envelope.get("model_routing_hint"),
            "source_refs": list(record.get("source_refs") or []),
            "metadata": metadata,
            "updated_at": record.get("updated_at"),
            "search_blob": self._search_blob(" ".join([title, summary, page_text, metadata_text])),
            "page_text": page_text,
            "metadata_text": metadata_text,
            "token_weights": token_weights,
            "doc_length": doc_length,
            "semantic_embedding": semantic_embedding,
            "epistemic_status": metadata.get("epistemic_status"),
            "epistemic_support_strength": metadata.get("epistemic_support_strength"),
        }

    @staticmethod
    def _search_blob(value: str) -> str:
        normalized = _normalize_text(value)
        folded = _ascii_fold(normalized)
        return normalized if folded == normalized else f"{normalized} {folded}"

    @staticmethod
    def _document_frequencies(documents: list[dict[str, Any]]) -> Counter[str]:
        frequencies = Counter[str]()
        for document in documents:
            frequencies.update(set(document["token_weights"].keys()))
        return frequencies

    @staticmethod
    def _bm25_score(
        query_tokens: list[str],
        document: dict[str, Any],
        dfs: Counter[str],
        total_docs: int,
        avg_length: float,
    ) -> float:
        k1 = 1.5
        b = 0.75
        score = 0.0
        token_weights: Counter[str] = document["token_weights"]
        for token in query_tokens:
            tf = float(token_weights.get(token, 0))
            if tf <= 0:
                continue
            df = float(dfs.get(token, 0))
            idf = math.log(((total_docs - df + 0.5) / (df + 0.5)) + 1.0)
            denominator = tf + k1 * (1.0 - b + b * (document["doc_length"] / max(avg_length, 1.0)))
            score += idf * ((tf * (k1 + 1.0)) / max(denominator, 1e-6))
        return score

    @classmethod
    def _expanded_bm25_score(
        cls,
        *,
        expanded_query_tokens: list[str],
        document: dict[str, Any],
        dfs: Counter[str],
        total_docs: int,
        avg_length: float,
    ) -> float:
        if not expanded_query_tokens:
            return 0.0
        return cls._bm25_score(expanded_query_tokens, document, dfs, total_docs, avg_length) * 0.35

    @staticmethod
    def _phrase_bonus(query_text: str, document: dict[str, Any]) -> float:
        if not query_text:
            return 0.0
        if query_text in str(document["search_blob"]):
            return 1.2
        return 0.0

    @staticmethod
    def _scope_bonus(scopes: list[str], document: dict[str, Any]) -> float:
        scope = str(document.get("scope") or "")
        if not scopes:
            return 0.0
        normalized_scopes = [str(item).strip() for item in scopes if str(item).strip()]
        primary_scope = normalized_scopes[0] if normalized_scopes else ""
        if primary_scope and scope == primary_scope:
            return 0.38
        if scope in normalized_scopes:
            return 0.28
        if "global" in normalized_scopes and scope == "global":
            return 0.12
        if any(str(item).startswith("project:") for item in normalized_scopes) and scope == "professional":
            return 0.1
        if any(str(item).startswith("project:") for item in scopes) and scope == "professional":
            return 0.08
        return 0.0

    @staticmethod
    def _page_intent_bonus(query_tokens: list[str], page_key: str) -> float:
        token_set = set(query_tokens)
        if page_key in {"decisions", "reflections"} and token_set.intersection({"neden", "why", "risk", "karar", "gerekce", "gerekçe", "reddedildi"}):
            return 0.42
        if page_key in {"preferences", "persona", "routines"} and token_set.intersection({"tercih", "ton", "stil", "rutin", "aliskanlik", "alışkanlık"}):
            return 0.36
        if page_key in {"legal", "projects"} and token_set.intersection({"dosya", "müvekkil", "musteri", "matter", "tahliye", "kira", "legal"}):
            return 0.34
        if page_key == "contacts" and token_set.intersection({"kişi", "kisi", "iletisim", "mesaj", "mail"}):
            return 0.22
        if page_key in {"recommendations", "reflections"} and token_set.intersection({"feedback", "redded", "kabul", "geçmiş", "gecmis"}):
            return 0.28
        if page_key == "places" and token_set.intersection({"yakın", "yakin", "konum", "yer", "rota", "navigasyon"}):
            return 0.34
        return 0.0

    @staticmethod
    def _page_matches_intent(page_key: str, query_intents: set[str]) -> bool:
        page_matches = {
            "decision": {"decisions", "recommendations", "reflections"},
            "profile": {"persona", "preferences", "routines", "contacts"},
            "location": {"places", "recommendations", "routines"},
            "legal": {"legal", "projects", "decisions"},
            "proactive": {"recommendations", "projects", "routines", "reflections"},
            "history": {"recommendations", "reflections", "decisions"},
            "reflection": {"reflections", "decisions"},
            "recent": {"recommendations", "decisions", "projects", "places"},
        }
        return any(page_key in page_matches.get(intent, set()) for intent in query_intents)

    @staticmethod
    def _intent_bonus(query_intents: set[str], page_key: str, metadata: dict[str, Any]) -> float:
        if not query_intents:
            return 0.0
        bonus = 0.0
        field = str(metadata.get("field") or "").strip().lower()
        connector = str(metadata.get("connector_name") or "").strip().lower()
        if "history" in query_intents and page_key == "recommendations":
            bonus += 0.12
        if "history" in query_intents and field in {"recommendation_feedback", "recommendation_outcome"}:
            bonus += 0.12
        if "reflection" in query_intents and page_key == "reflections":
            bonus += 0.16
        if "recent" in query_intents and connector in {"calendar", "messages", "email", "location_events"}:
            bonus += 0.08
        if "location" in query_intents and field in {"current_place", "recent_places", "nearby_categories"}:
            bonus += 0.1
        if "decision" in query_intents and str(metadata.get("record_type") or "") == "decision":
            bonus += 0.12
        if "consumer" in query_intents and connector in {"browser_context", "consumer_signals"}:
            bonus += 0.14
        if "consumer" in query_intents and str(metadata.get("signal_topic") or "") in {"youtube_history", "reading_list", "shopping_signal", "travel_signal"}:
            bonus += 0.12
        if "coaching" in query_intents and page_key in {"projects", "routines", "preferences"}:
            bonus += 0.14
        return bonus

    @staticmethod
    def _relation_bonus(query_intents: set[str], metadata: dict[str, Any]) -> float:
        relations = list(metadata.get("relations") or [])
        if not relations or not query_intents:
            return 0.0
        relation_targets = {
            str(item.get("relation_type") or "").strip().lower()
            for item in relations
            if isinstance(item, dict)
        }
        if "decision" in query_intents and "requires_confirmation" in relation_targets:
            return 0.18
        if "profile" in query_intents and relation_targets.intersection({"scoped_to", "related_to"}):
            return 0.12
        if "location" in query_intents and relation_targets.intersection({"scoped_to", "relevant_to"}):
            return 0.1
        if "history" in query_intents and relation_targets.intersection({"supports", "supersedes", "contradicts"}):
            return 0.14
        return 0.0

    @staticmethod
    def _metadata_keyword_bonus(query_tokens: list[str], metadata: dict[str, Any]) -> float:
        keywords = {
            str(metadata.get("field") or "").strip().lower(),
            str(metadata.get("connector_name") or "").strip().lower(),
            str(metadata.get("topic") or "").strip().lower(),
            str(metadata.get("recommendation_kind") or "").strip().lower(),
            str(metadata.get("signal_topic") or "").strip().lower(),
            str(metadata.get("provider") or "").strip().lower(),
        }
        normalized_keywords = {token for keyword in keywords for token in _tokenize(keyword) if token}
        if not normalized_keywords:
            return 0.0
        overlap = normalized_keywords.intersection(set(query_tokens))
        if not overlap:
            return 0.0
        return min(0.14, 0.05 + len(overlap) * 0.03)

    @staticmethod
    def _semantic_vector_bonus(document: dict[str, Any], request: RetrievalQuery) -> float:
        similarity = _cosine_similarity(_semantic_query_embedding(request.query), dict(document.get("semantic_embedding") or {}))
        if similarity <= 0.08:
            return 0.0
        return round(min(0.68, similarity * 0.82), 4)

    @staticmethod
    def _confidence_bonus(metadata: dict[str, Any]) -> float:
        confidence = float(metadata.get("confidence") or 0.0)
        if confidence >= 0.9:
            return 0.08
        if confidence >= 0.75:
            return 0.04
        return 0.0

    @staticmethod
    def _priority_bonus(metadata: dict[str, Any]) -> float:
        priority = float(metadata.get("priority_score") or 0.0)
        importance = float(metadata.get("importance_score") or 0.0)
        frequency_weight = float(metadata.get("frequency_weight") or 0.0)
        if priority <= 0 and importance <= 0:
            return 0.0
        return round(min(0.22, (priority * 0.08) + (importance * 0.03) + (frequency_weight * 0.05)), 4)

    @staticmethod
    def _decay_penalty(metadata: dict[str, Any]) -> float:
        decay = float(metadata.get("decay_score") or 0.0)
        if decay <= 0.35:
            return 0.0
        return round(min(0.1, decay * 0.09), 4)

    @staticmethod
    def _low_confidence_penalty(metadata: dict[str, Any]) -> float:
        confidence = float(metadata.get("confidence") or 0.0)
        if confidence and confidence < 0.35:
            return 0.05
        return 0.0

    @staticmethod
    def _correction_penalty(metadata: dict[str, Any]) -> float:
        repeated = int(metadata.get("repeated_contradiction_count") or 0)
        history_size = len(list(metadata.get("correction_history") or []))
        if repeated >= 2:
            return 0.12
        if history_size >= 3:
            return 0.06
        return 0.0

    @staticmethod
    def _recent_intent_bonus(query_intents: set[str], updated_at: str | None) -> float:
        if "recent" not in query_intents and "history" not in query_intents:
            return 0.0
        updated_dt = _datetime_or_none(updated_at)
        if not updated_dt:
            return 0.0
        age_hours = max(0.0, (datetime.now(timezone.utc) - updated_dt).total_seconds() / 3600.0)
        if age_hours <= 12:
            return 0.22
        if age_hours <= 72:
            return 0.12
        if age_hours <= 168:
            return 0.05
        return 0.0

    @staticmethod
    def _freshness_bonus(updated_at: str | None) -> float:
        updated_dt = _datetime_or_none(updated_at)
        if not updated_dt:
            return 0.0
        age_days = max(0.0, (datetime.now(timezone.utc) - updated_dt).total_seconds() / 86400.0)
        if age_days <= 2:
            return 0.18
        if age_days <= 14:
            return 0.1
        if age_days <= 60:
            return 0.04
        return 0.0

    @staticmethod
    def _updated_rank(updated_at: str | None) -> float:
        updated_dt = _datetime_or_none(updated_at)
        if not updated_dt:
            return 0.0
        return updated_dt.timestamp()

    @staticmethod
    def _diversity_intent_bonus(query_intents: set[str], document: dict[str, Any]) -> float:
        page_key = str(document.get("page_key") or "")
        if "history" in query_intents and page_key in {"recommendations", "decisions"}:
            return 0.06
        if "reflection" in query_intents and page_key == "reflections":
            return 0.08
        if "location" in query_intents and page_key == "places":
            return 0.08
        if "consumer" in query_intents and page_key in {"preferences", "projects", "places"}:
            return 0.08
        if "coaching" in query_intents and page_key in {"projects", "routines", "preferences"}:
            return 0.08
        return 0.0

    @staticmethod
    def _diversify_hits(hits: list[dict[str, Any]], *, limit: int, query_intents: set[str] | None = None) -> list[dict[str, Any]]:
        if len(hits) <= limit:
            return hits[:limit]
        diversified: list[dict[str, Any]] = []
        remaining = list(hits)
        seeded_page_groups = {
            "decision": {"decisions", "recommendations", "reflections"},
            "profile": {"preferences", "persona", "routines", "contacts"},
            "location": {"places", "recommendations"},
            "history": {"recommendations", "decisions", "reflections"},
            "reflection": {"reflections", "decisions"},
            "legal": {"legal", "projects", "decisions"},
            "proactive": {"recommendations", "projects", "routines"},
            "consumer": {"preferences", "projects", "places", "contacts"},
            "coaching": {"projects", "routines", "preferences", "recommendations"},
        }
        for intent in query_intents or set():
            page_group = seeded_page_groups.get(intent, set())
            if not page_group:
                continue
            seeded = next((item for item in remaining if str(item.get("page_key") or "") in page_group), None)
            if seeded is None:
                continue
            diversified.append(seeded)
            remaining.remove(seeded)
            if len(diversified) >= limit:
                return diversified[:limit]
        page_counts = Counter[str]()
        record_type_counts = Counter[str]()
        scope_counts = Counter[str]()
        for item in diversified:
            page_counts[str(item.get("page_key") or "")] += 1
            record_type_counts[str(item.get("record_type") or "")] += 1
            scope_counts[str(item.get("scope") or "")] += 1
        while remaining and len(diversified) < limit:
            next_index = 0
            best_score = None
            for index, item in enumerate(remaining):
                page_penalty = max(0, page_counts[str(item.get("page_key") or "")] - 0) * 0.16
                record_type_penalty = max(0, record_type_counts[str(item.get("record_type") or "")] - 0) * 0.1
                scope_penalty = max(0, scope_counts[str(item.get("scope") or "")] - 0) * 0.06
                adjusted_score = float(item.get("score") or 0.0) - page_penalty - record_type_penalty - scope_penalty
                if best_score is None or adjusted_score > best_score:
                    best_score = adjusted_score
                    next_index = index
            selected = remaining.pop(next_index)
            diversified.append(selected)
            page_counts[str(selected.get("page_key") or "")] += 1
            record_type_counts[str(selected.get("record_type") or "")] += 1
            scope_counts[str(selected.get("scope") or "")] += 1
        return diversified

    @staticmethod
    def _build_hit(*, document: dict[str, Any], score: float, reasons: list[str]) -> dict[str, Any]:
        reason_priority = {
            "page_intent_match": 0,
            "query_intent_match": 1,
            "relation_match": 2,
            "scope_match": 3,
            "source_type_match": 4,
            "trust_level": 5,
            "exact_phrase": 6,
            "token_overlap": 7,
            "freshness": 8,
            "recent_activity_match": 9,
            "high_confidence": 10,
            "result_diversity": 11,
            "semantic_vector_match": 12,
            "semantic_reranker": 13,
            "semantic_expansion": 14,
            "epistemic_grounded": 15,
            "priority_weight": 16,
            "metadata_match": 17,
            "fts_primary_hit": 18,
            "fts_match": 19,
            "local_index": 20,
            "epistemic_penalty": 21,
            "correction_history_penalty": 22,
            "low_confidence_penalty": 23,
            "decay_penalty": 24,
        }
        deduped_reasons: list[str] = []
        seen: set[str] = set()
        for reason in reasons:
            normalized = str(reason).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped_reasons.append(normalized)
        deduped_reasons.sort(key=lambda item: (reason_priority.get(item, 50), item))
        selected_reasons = deduped_reasons[:6]
        # Grounded support is a core explainability signal; don't let it drop out
        # of the visible reason list just because lexical/semantic hints filled the cap.
        if "epistemic_grounded" in deduped_reasons and "epistemic_grounded" not in selected_reasons:
            if selected_reasons:
                selected_reasons[-1] = "epistemic_grounded"
            else:
                selected_reasons = ["epistemic_grounded"]
            selected_reasons = list(dict.fromkeys(selected_reasons))
        hit = KnowledgeSearchHit(
            page_key=document["page_key"],
            record_id=document["record_id"],
            title=document["title"],
            summary=document["summary"],
            score=round(score, 4),
            record_type=document["record_type"],
            scope=document["scope"],
            sensitivity=document["sensitivity"],
            exportability=document["exportability"],
            model_routing_hint=document["model_routing_hint"],
            source_refs=document["source_refs"],
            metadata=document["metadata"],
            updated_at=document["updated_at"],
            selection_reasons=selected_reasons,
        )
        return asdict(hit)


class SQLiteFTSRetrievalBackend:
    name = "sqlite_hybrid_fts_v1"
    ranking_profile = "sqlite_hybrid_fts_semantic_v3"

    def __init__(
        self,
        index_path: Path,
        *,
        fallback_backend: LocalHybridRetrievalBackend | None = None,
        dense_candidates_enabled: bool = False,
        semantic_backend: str = "heuristic",
        embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        cross_encoder_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        reranker_mode: str = "local_heuristic",
    ) -> None:
        self.index_path = Path(index_path)
        self.fallback_backend = fallback_backend or LocalHybridRetrievalBackend()
        self._fts_ready: bool | None = None
        self.dense_candidates_enabled = bool(dense_candidates_enabled)
        self.semantic_backend = str(semantic_backend or "heuristic").strip().lower() or "heuristic"
        self.embedding_model_name = str(embedding_model_name or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2").strip() or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        self.cross_encoder_model_name = str(cross_encoder_model_name or "cross-encoder/ms-marco-MiniLM-L-6-v2").strip() or "cross-encoder/ms-marco-MiniLM-L-6-v2"
        self.reranker_mode = str(reranker_mode or "local_heuristic").strip().lower() or "local_heuristic"
        self.vector_hook_ready = (
            sentence_embedding_backend_available(self.embedding_model_name)
            if self.semantic_backend == "model_local"
            else True
        )
        self.reranker_hook_ready = (
            cross_encoder_backend_available(self.cross_encoder_model_name)
            if self.reranker_mode in {"model_cross_encoder", "cross_encoder"}
            else True
        )

    def search(
        self,
        *,
        state: dict[str, Any],
        request: RetrievalQuery,
        envelope_resolver: Callable[[str, dict[str, Any]], dict[str, Any]],
        scope_matcher: Callable[[str, list[str]], bool],
        epistemic_resolver: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> list[dict[str, Any]]:
        documents = self.fallback_backend.collect_documents(
            state=state,
            request=request,
            envelope_resolver=envelope_resolver,
            scope_matcher=scope_matcher,
            epistemic_resolver=epistemic_resolver,
        )
        if not documents:
            return []
        try:
            fts_scores = self._fts_scores(documents=documents, request=request)
        except sqlite3.Error:
            return self.fallback_backend.score_documents(documents=documents, request=request)
        semantic_scores = self._semantic_scores(documents=documents, request=request)
        if not fts_scores and not semantic_scores:
            return self.fallback_backend.score_documents(documents=documents, request=request)
        candidate_doc_keys = self._candidate_doc_keys(
            documents=documents,
            request=request,
            fts_scores=fts_scores,
            semantic_scores=semantic_scores,
        )
        if candidate_doc_keys:
            candidate_documents = [doc for doc in documents if str(doc.get("doc_key") or "") in candidate_doc_keys]
        else:
            candidate_documents = list(documents)
        extra_scores: dict[str, float] = {}
        extra_reasons: dict[str, list[str]] = {}
        reranker_scores = self._reranker_scores(
            documents=candidate_documents,
            request=request,
            semantic_scores=semantic_scores,
            fts_scores=fts_scores,
        )
        for doc in candidate_documents:
            doc_key = str(doc.get("doc_key") or "")
            fts_score = float(fts_scores.get(doc_key, 0.0))
            semantic_score = float(semantic_scores.get(doc_key, 0.0))
            reranker_score = float(reranker_scores.get(doc_key, 0.0))
            fused_score = round((fts_score * 0.52) + (semantic_score * 0.66) + (reranker_score * 0.92), 4)
            if fused_score <= 0:
                continue
            reasons = []
            if fts_score > 0:
                reasons.extend(["fts_match", "local_index"])
                if fts_score >= 0.8:
                    reasons.append("fts_primary_hit")
            if semantic_score > 0:
                reasons.append("semantic_reranker")
                if semantic_score >= 0.38:
                    reasons.append("semantic_vector_match")
            if reranker_score > 0:
                reasons.append("semantic_reranker")
            extra_scores[doc_key] = fused_score
            extra_reasons[doc_key] = reasons
        ranked = self.fallback_backend.score_documents(
            documents=candidate_documents,
            request=request,
            extra_scores=extra_scores,
            extra_reason_map=extra_reasons,
        )
        return ranked

    def _candidate_doc_keys(
        self,
        *,
        documents: list[dict[str, Any]],
        request: RetrievalQuery,
        fts_scores: dict[str, float],
        semantic_scores: dict[str, float],
    ) -> set[str]:
        if not documents:
            return set()
        if not self.dense_candidates_enabled:
            ordered_fts = [key for key, _ in sorted(fts_scores.items(), key=lambda item: (-item[1], item[0]))[: max(request.limit * 4, 16)]]
            if ordered_fts:
                return set(ordered_fts)
            ordered_semantic = [key for key, _ in sorted(semantic_scores.items(), key=lambda item: (-item[1], item[0]))[: max(request.limit * 4, 16)]]
            return set(ordered_semantic) if ordered_semantic else {str(doc.get("doc_key") or "") for doc in documents}
        ordered_fts = [key for key, _ in sorted(fts_scores.items(), key=lambda item: (-item[1], item[0]))[: max(request.limit * 4, 18)]]
        ordered_dense = [key for key, _ in sorted(semantic_scores.items(), key=lambda item: (-item[1], item[0]))[: max(request.limit * 5, 22)]]
        candidate_keys = set(ordered_fts)
        candidate_keys.update(ordered_dense)
        if not candidate_keys:
            return {str(doc.get("doc_key") or "") for doc in documents}
        return candidate_keys

    def _reranker_scores(
        self,
        *,
        documents: list[dict[str, Any]],
        request: RetrievalQuery,
        semantic_scores: dict[str, float],
        fts_scores: dict[str, float],
    ) -> dict[str, float]:
        if not documents:
            return {}
        if self.reranker_mode in {"model_cross_encoder", "cross_encoder"}:
            model_scores = model_reranker_scores(
                query=request.query,
                texts=[self._document_semantic_text(item) for item in documents],
                model_name=self.cross_encoder_model_name,
            )
            if model_scores:
                reranked: dict[str, float] = {}
                for document, score in zip(documents, model_scores):
                    doc_key = str(document.get("doc_key") or "")
                    reranked[doc_key] = round(min(0.94, max(0.0, float(score))), 4)
                return reranked
        query_text = _ascii_fold(request.query)
        query_tokens = _tokenize(request.query)
        query_token_set = set(query_tokens)
        reranker_scores: dict[str, float] = {}
        for document in documents:
            doc_key = str(document.get("doc_key") or "")
            search_blob = str(document.get("search_blob") or "")
            title = _ascii_fold(str(document.get("title") or ""))
            summary = _ascii_fold(str(document.get("summary") or ""))
            metadata = dict(document.get("metadata") or {})
            token_weights: Counter[str] = document.get("token_weights") or Counter()
            overlap = len(query_token_set.intersection(set(token_weights.keys())))
            overlap_score = min(0.32, overlap * 0.06)
            exact_hint = 0.18 if query_text and (query_text in title or query_text in summary or query_text in search_blob) else 0.0
            semantic_hint = min(0.28, float(semantic_scores.get(doc_key, 0.0)) * 0.55)
            lexical_hint = min(0.22, float(fts_scores.get(doc_key, 0.0)) * 0.16)
            epistemic_hint = 0.0
            if str(metadata.get("epistemic_status") or "").strip().lower() == "current":
                epistemic_hint += 0.06
            if str(metadata.get("epistemic_support_strength") or "").strip().lower() == "grounded":
                epistemic_hint += 0.05
            if str(metadata.get("epistemic_memory_tier") or "").strip().lower() == "hot":
                epistemic_hint += 0.03
            reranker_scores[doc_key] = round(min(0.88, overlap_score + exact_hint + semantic_hint + lexical_hint + epistemic_hint), 4)
        return reranker_scores

    def _semantic_scores(self, *, documents: list[dict[str, Any]], request: RetrievalQuery) -> dict[str, float]:
        if self.semantic_backend == "model_local":
            model_scores = model_semantic_scores(
                query=request.query,
                texts=[self._document_semantic_text(item) for item in documents],
                model_name=self.embedding_model_name,
            )
            if model_scores:
                return {
                    str(document.get("doc_key") or ""): round(min(0.82, max(0.0, float(score)) * 0.96), 4)
                    for document, score in zip(documents, model_scores)
                    if float(score) > 0.08
                }
        query_embedding = _semantic_query_embedding(request.query)
        if not query_embedding:
            return {}
        scores: dict[str, float] = {}
        for document in documents:
            similarity = _cosine_similarity(query_embedding, dict(document.get("semantic_embedding") or {}))
            if similarity <= 0.06:
                continue
            scores[str(document.get("doc_key") or "")] = round(min(0.72, similarity * 0.92), 4)
        return scores

    def _fts_scores(self, *, documents: list[dict[str, Any]], request: RetrievalQuery) -> dict[str, float]:
        query_tokens = _tokenize(request.query)
        if not query_tokens:
            return {}
        query_intents = _query_intents(query_tokens)
        expanded_tokens = _expand_query_tokens(query_tokens, query_intents)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.index_path) as conn:
            conn.row_factory = sqlite3.Row
            if not self._ensure_schema(conn):
                return {}
            self._sync_index(conn, documents)
            fts_query = self._build_fts_query(query_tokens=query_tokens, expanded_tokens=expanded_tokens)
            rows = conn.execute(
                """
                SELECT documents_fts.doc_key, bm25(documents_fts, 2.4, 1.8, 0.8, 0.3) AS rank
                FROM documents_fts
                WHERE documents_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, max(20, min(len(documents), request.limit * 8))),
            ).fetchall()
        scores: dict[str, float] = {}
        for row in rows:
            doc_key = str(row["doc_key"] or "")
            raw_rank = float(row["rank"] or 0.0)
            normalized = round(1.35 / (1.0 + max(raw_rank, 0.0)), 4)
            scores[doc_key] = max(scores.get(doc_key, 0.0), normalized)
        return scores

    @staticmethod
    def _build_fts_query(*, query_tokens: list[str], expanded_tokens: list[str]) -> str:
        groups: list[str] = []
        expansion_pool = list(expanded_tokens)
        seen: set[str] = set()
        for token in list(dict.fromkeys(query_tokens))[:8]:
            variants = [token]
            token_root = token[:3]
            for candidate in expansion_pool:
                if candidate in variants:
                    continue
                if candidate.startswith(token_root) or token.startswith(candidate[:3]):
                    variants.append(candidate)
                if len(variants) >= 3:
                    break
            group_terms: list[str] = []
            for item in variants:
                normalized = str(item or "").strip()
                if not normalized:
                    continue
                group_terms.append(f'"{normalized}"')
                prefix_token = re.sub(r"[^a-z0-9]", "", _ascii_fold(normalized))
                if len(prefix_token) >= 5:
                    group_terms.append(f"{prefix_token[:8]}*")
            deduped_terms = list(dict.fromkeys(group_terms))
            group = " OR ".join(term for term in deduped_terms if term)
            if not group or group in seen:
                continue
            seen.add(group)
            groups.append(f"({group})")
        if not groups:
            return " ".join(f'"{token}"' for token in list(dict.fromkeys(query_tokens))[:8])
        return " AND ".join(groups)

    def _ensure_schema(self, conn: sqlite3.Connection) -> bool:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_key TEXT PRIMARY KEY,
                page_key TEXT NOT NULL,
                record_id TEXT,
                title TEXT,
                summary TEXT,
                record_type TEXT,
                scope TEXT,
                sensitivity TEXT,
                exportability TEXT,
                model_routing_hint TEXT,
                source_refs_json TEXT,
                metadata_json TEXT,
                updated_at TEXT,
                search_blob TEXT,
                page_text TEXT,
                metadata_text TEXT,
                doc_length INTEGER NOT NULL,
                embedding_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        columns = {
            str(row[1]): True
            for row in conn.execute("PRAGMA table_info(documents)").fetchall()
        }
        if "embedding_json" not in columns:
            conn.execute("ALTER TABLE documents ADD COLUMN embedding_json TEXT NOT NULL DEFAULT '{}'")
        if self._fts_ready is False:
            return False
        if self._fts_ready is None:
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                        doc_key UNINDEXED,
                        title,
                        summary,
                        search_blob,
                        metadata_text,
                        tokenize='unicode61'
                    )
                    """
                )
            except sqlite3.OperationalError:
                self._fts_ready = False
                return False
            self._fts_ready = True
        return True

    def _sync_index(self, conn: sqlite3.Connection, documents: list[dict[str, Any]]) -> None:
        marker = hashlib.sha1(
            _json_marker(
                [
                    {
                        "doc_key": doc["doc_key"],
                        "updated_at": doc.get("updated_at"),
                        "scope": doc.get("scope"),
                        "page_key": doc.get("page_key"),
                        "record_type": doc.get("record_type"),
                        "search_blob": doc.get("search_blob"),
                        "embedding_json": doc.get("semantic_embedding") or {},
                    }
                    for doc in documents
                ]
            ).encode("utf-8")
        ).hexdigest()
        existing = conn.execute("SELECT value FROM meta WHERE key='state_marker'").fetchone()
        if existing and str(existing["value"] or "") == marker:
            return
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM documents_fts")
        conn.executemany(
            """
            INSERT INTO documents (
                doc_key, page_key, record_id, title, summary, record_type, scope, sensitivity,
                exportability, model_routing_hint, source_refs_json, metadata_json, updated_at,
                search_blob, page_text, metadata_text, doc_length, embedding_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    doc["doc_key"],
                    doc["page_key"],
                    doc.get("record_id"),
                    doc.get("title"),
                    doc.get("summary"),
                    doc.get("record_type"),
                    doc.get("scope"),
                    doc.get("sensitivity"),
                    doc.get("exportability"),
                    doc.get("model_routing_hint"),
                    _json_marker(doc.get("source_refs") or []),
                    _json_marker(doc.get("metadata") or {}),
                    doc.get("updated_at"),
                    doc.get("search_blob"),
                    doc.get("page_text"),
                    doc.get("metadata_text"),
                    int(doc.get("doc_length") or 1),
                    _json_marker(doc.get("semantic_embedding") or {}),
                )
                for doc in documents
            ],
        )
        conn.executemany(
            """
            INSERT INTO documents_fts (doc_key, title, summary, search_blob, metadata_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    doc["doc_key"],
                    doc.get("title"),
                    doc.get("summary"),
                    doc.get("search_blob"),
                    doc.get("metadata_text"),
                )
                for doc in documents
            ],
        )
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('state_marker', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (marker,),
        )
        conn.commit()

    @staticmethod
    def _document_semantic_text(document: dict[str, Any]) -> str:
        parts = [
            str(document.get("title") or "").strip(),
            str(document.get("summary") or "").strip(),
            str(document.get("page_text") or "").strip(),
        ]
        metadata = dict(document.get("metadata") or {})
        for key in (
            "epistemic_display_label",
            "epistemic_current_value",
            "field",
            "connector_name",
            "topic",
            "record_type",
        ):
            value = str(metadata.get(key) or "").strip()
            if value:
                parts.append(value)
        return " ; ".join(part for part in parts if part)


def _hash_marker(*parts: Any) -> str:
    return hashlib.sha1(_json_marker(list(parts)).encode("utf-8")).hexdigest()[:12]
