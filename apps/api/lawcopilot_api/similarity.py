from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
from typing import Any

from .rag import score_chunk_records, tokenize

LEGAL_KEYWORDS = {
    "tahliye",
    "kira",
    "itiraz",
    "icra",
    "dava",
    "talep",
    "sozlesme",
    "temerrut",
    "alacak",
    "tazminat",
    "velayet",
    "kaza",
    "iscilik",
    "noter",
    "ihtar",
    "mahkeme",
    "fesih",
    "dekont",
    "dilekce",
    "savunma",
}
STOP_WORDS = {"the", "and", "ile", "icin", "ve", "bir", "dosya", "belge"}


def _filename_tokens(name: str) -> set[str]:
    return tokenize(name.replace(".", " ").replace("_", " ").replace("-", " "))


def _folder_tokens(relative_path: str | None) -> set[str]:
    if not relative_path:
        return set()
    parts = list(PurePosixPath(relative_path).parts[:-1])
    return set().union(*(tokenize(part.replace("_", " ").replace("-", " ")) for part in parts)) if parts else set()


def _folder_label(relative_path: str | None) -> str:
    if not relative_path:
        return "Klasör bilgisi kaydedilmedi."
    parent = str(PurePosixPath(relative_path).parent)
    return "Kök klasör" if parent in {".", ""} else parent


def _top_terms(texts: list[str], limit: int = 5) -> list[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        for token in tokenize(text):
            if len(token) >= 4 and token not in STOP_WORDS:
                counts[token] += 1
    return [token for token, _ in counts.most_common(limit)]


def _round_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _score_overlap(left: set[str], right: set[str]) -> float:
    union = len(left | right) or 1
    return _round_score(len(left & right) / union)


def _build_supporting_query(source_tokens: set[str], shared_terms: set[str], source_rows: list[dict[str, Any]]) -> str:
    if shared_terms:
        return " ".join(sorted(shared_terms)[:12])
    source_excerpt = " ".join(str(row.get("text") or "")[:160] for row in source_rows[:2]).strip()
    return source_excerpt or " ".join(sorted(source_tokens)[:12])


def _score_breakdown(*, filename_overlap: float, content_overlap: float, type_score: float, checksum_score: float, folder_score: float, legal_score: float) -> dict[str, float]:
    total = checksum_score or (
        filename_overlap * 0.18 +
        content_overlap * 0.44 +
        type_score * 0.08 +
        folder_score * 0.14 +
        legal_score * 0.16
    )
    return {
        "dosya_adi": _round_score(filename_overlap),
        "icerik": _round_score(content_overlap),
        "belge_turu": _round_score(type_score),
        "checksum": _round_score(checksum_score),
        "klasor_baglami": _round_score(folder_score),
        "hukuk_terimleri": _round_score(legal_score),
        "genel_skor": _round_score(total),
    }


def _signal_list(shared_terms: set[str], *, extension: str, checksum_match: bool, folder_match: bool, legal_term_overlap: set[str]) -> list[str]:
    signals = ["yerel_benzerlik", "calisma_alani"]
    if extension:
        signals.append(f"uzanti:{extension}")
    if folder_match:
        signals.append("klasor_baglami")
    if shared_terms:
        signals.append(f"ortak_terim:{','.join(sorted(shared_terms)[:4])}")
    if legal_term_overlap:
        signals.append(f"hukuk_terimi:{','.join(sorted(legal_term_overlap)[:4])}")
    if checksum_match:
        signals.append("checksum_eslesmesi")
    return signals


def _attention_notes(*, checksum_match: bool, folder_score: float, type_score: float, support_count: int, total_score: float) -> list[str]:
    notes: list[str] = []
    if checksum_match:
        notes.append("Checksum eşleşmesi bulundu; aynı belgenin kopyası veya sürümü olabilir.")
    if folder_score < 0.2 and total_score >= 0.45:
        notes.append("İçerik benzerliği yüksek ama klasör bağlamı farklı; yanlış dosyaya bağlamadan önce kontrol edin.")
    if type_score == 0.0:
        notes.append("Belge türü farklı; içerik yakın olsa bile format ve kullanım amacı değişebilir.")
    if support_count == 0:
        notes.append("Destekleyici pasaj zayıf; benzerlik sonucu ek belge ile doğrulanmalı.")
    if not notes:
        notes.append("Benzerlik sonucu açıklanabilir sinyallerle üretildi; yine de insan incelemesi gerekir.")
    return notes


def _draft_suggestions(*, checksum_match: bool, legal_term_overlap: set[str], attention_notes: list[str]) -> list[str]:
    suggestions = ["İç ekip özeti taslağı", "İlk dosya değerlendirmesi taslağı"]
    if checksum_match:
        suggestions.append("Mükerrer belge inceleme notu")
    if {"eksik", "dekont", "sozlesme", "dilekce"} & legal_term_overlap:
        suggestions.append("Belge talep listesi taslağı")
    if any("kontrol" in note.lower() or "doğr" in note.lower() for note in attention_notes):
        suggestions.append("İnceleme notu taslağı")
    # preserve order and uniqueness
    seen: set[str] = set()
    ordered: list[str] = []
    for item in suggestions:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered[:4]


def find_similar_documents(*, source_document: dict[str, Any], candidate_documents: list[dict[str, Any]], chunk_rows: list[dict[str, Any]], limit: int = 5) -> dict[str, Any]:
    document_ids = {int(doc["id"]) for doc in candidate_documents}
    document_chunks: dict[int, list[dict[str, Any]]] = {document_id: [] for document_id in document_ids}
    for row in chunk_rows:
        document_id = int(row.get("document_id") or 0)
        if document_id in document_chunks:
            document_chunks[document_id].append(row)

    source_id = int(source_document["id"])
    source_chunks = document_chunks.get(source_id, [])
    source_texts = [str(row.get("text") or "") for row in source_chunks]
    source_body_tokens = set().union(*(tokenize(text) for text in source_texts)) if source_texts else set()
    source_name_tokens = _filename_tokens(str(source_document.get("display_name") or source_document.get("relative_path") or ""))
    source_folder_tokens = _folder_tokens(str(source_document.get("relative_path") or ""))
    source_tokens = source_body_tokens | source_name_tokens | source_folder_tokens

    items = []
    for candidate in candidate_documents:
        candidate_id = int(candidate["id"])
        if candidate_id == source_id:
            continue

        candidate_rows = document_chunks.get(candidate_id, [])
        candidate_texts = [str(row.get("text") or "") for row in candidate_rows]
        candidate_body_tokens = set().union(*(tokenize(text) for text in candidate_texts)) if candidate_texts else set()
        candidate_name_tokens = _filename_tokens(str(candidate.get("display_name") or candidate.get("relative_path") or ""))
        candidate_folder_tokens = _folder_tokens(str(candidate.get("relative_path") or ""))
        candidate_tokens = candidate_body_tokens | candidate_name_tokens | candidate_folder_tokens

        content_overlap = _score_overlap(source_body_tokens, candidate_body_tokens)
        filename_overlap = _score_overlap(source_name_tokens, candidate_name_tokens)
        folder_overlap = _score_overlap(source_folder_tokens, candidate_folder_tokens)
        type_score = 1.0 if str(candidate.get("extension") or "") == str(source_document.get("extension") or "") else 0.0
        legal_term_overlap = LEGAL_KEYWORDS & source_tokens & candidate_tokens
        legal_score = min(1.0, len(legal_term_overlap) * 0.25)
        checksum_match = str(candidate.get("checksum") or "") == str(source_document.get("checksum") or "")
        checksum_score = 1.0 if checksum_match else 0.0

        score_breakdown = _score_breakdown(
            filename_overlap=filename_overlap,
            content_overlap=content_overlap,
            type_score=type_score,
            checksum_score=checksum_score,
            folder_score=folder_overlap,
            legal_score=legal_score,
        )
        total_score = score_breakdown["genel_skor"]
        if total_score <= 0:
            continue

        shared_terms = (source_tokens & candidate_tokens) - STOP_WORDS
        support_query = _build_supporting_query(source_tokens, shared_terms, source_chunks)
        supporting = score_chunk_records(support_query, candidate_rows, k=3)
        folder_label = _folder_label(str(candidate.get("relative_path") or ""))
        folder_match = folder_overlap >= 0.35

        why = []
        if checksum_match:
            why.append("Checksum eşleşti; belge birebir aynı veya çok yakın kopya görünüyor.")
        if filename_overlap >= 0.25:
            why.append("Dosya adı ve başlık terimleri benziyor.")
        if content_overlap >= 0.22:
            why.append("Metin içeriğinde güçlü örtüşme var.")
        if folder_match:
            why.append(f"Aynı klasör bağlamı içinde duruyor: {folder_label}.")
        elif folder_overlap > 0:
            why.append(f"Klasör yapısında kısmi bağ var: {folder_label}.")
        if legal_term_overlap:
            why.append("Ortak hukuk terimleri bulundu.")
        if supporting:
            why.append("Destekleyici pasajlar dayanak üretti.")
        if not why:
            why.append("Yerel sinyaller aynı konu etrafında kümeleniyor.")

        attention_notes = _attention_notes(
            checksum_match=checksum_match,
            folder_score=folder_overlap,
            type_score=type_score,
            support_count=len(supporting),
            total_score=total_score,
        )
        draft_suggestions = _draft_suggestions(
            checksum_match=checksum_match,
            legal_term_overlap=legal_term_overlap,
            attention_notes=attention_notes,
        )

        items.append(
            {
                "workspace_document_id": candidate_id,
                "belge_adi": candidate.get("display_name") or candidate.get("relative_path"),
                "goreli_yol": candidate.get("relative_path"),
                "benzerlik_puani": total_score,
                "neden_benzer": " ".join(why),
                "klasor_baglami": folder_label,
                "skor_bilesenleri": score_breakdown,
                "ortak_terimler": sorted(shared_terms)[:8],
                "destekleyici_pasajlar": supporting,
                "dikkat_notlari": attention_notes,
                "taslak_onerileri": draft_suggestions,
                "manuel_inceleme_gerekir": True,
                "sinyaller": _signal_list(
                    shared_terms,
                    extension=str(candidate.get("extension") or ""),
                    checksum_match=checksum_match,
                    folder_match=folder_match,
                    legal_term_overlap=legal_term_overlap,
                ),
            }
        )

    items.sort(
        key=lambda item: (
            item["benzerlik_puani"],
            item["skor_bilesenleri"]["icerik"],
            item["skor_bilesenleri"]["klasor_baglami"],
        ),
        reverse=True,
    )
    top_terms = _top_terms(source_texts, 6)
    return {
        "items": items[:limit],
        "explanation": "Sonuçlar seçilen çalışma klasörü içindeki dosya adı, içerik, belge türü, checksum ve klasör bağlamı sinyalleriyle üretildi.",
        "top_terms": top_terms,
        "manual_review_required": True,
    }
