from __future__ import annotations

import re
from typing import Any


_NORMALIZE_MAP = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
    }
)

_ABUSE_TERMS = (
    "aptal",
    "gerzek",
    "gerizekali",
    "salak",
    "serefsiz",
    "şerefsiz",
    "ahlaksiz",
    "ahlaksız",
    "haysiyetsiz",
    "pislik",
    "rezil",
    "pic",
    "piç",
    "orospu",
    "amk",
    "aq",
    "mk",
)
_THREAT_TERMS = (
    "oldurecegim",
    "öldüreceğim",
    "oldururum",
    "öldürürüm",
    "vururum",
    "yakacagim",
    "yakacağım",
    "mahvederim",
    "seni bulacagim",
    "seni bulacağım",
    "hesabini vereceksin",
    "hesabını vereceksin",
    "savciliga veririm",
    "savcılığa veririm",
)
_ACCUSATION_TERMS = (
    "dolandirici",
    "dolandırıcı",
    "sahtekar",
    "ifsa",
    "ifşa",
    "mahkemede gorusuruz",
    "mahkemede görüşürüz",
    "dava acacagim",
    "dava açacağım",
    "suclu",
    "suçlu",
    "suc duyurusu",
    "suç duyurusu",
    "sikayet edecegim",
    "şikayet edeceğim",
)
_COMPLAINT_TERMS = (
    "magdur",
    "mağdur",
    "magduriyet",
    "mağduriyet",
    "rezalet",
    "berbat",
    "ilgisiz",
    "hizmet kotu",
    "hizmet kötü",
    "memnun degilim",
    "memnun değilim",
    "cozun",
    "çözün",
)
_QUESTION_TERMS = (
    "?",
    "ne zaman",
    "paylasir misiniz",
    "paylaşır mısınız",
    "yardim",
    "yardım",
    "donus",
    "dönüş",
)


def normalize_signal_text(value: str | None) -> str:
    lowered = str(value or "").strip().lower()
    return lowered.translate(_NORMALIZE_MAP)


def _matched_terms(normalized: str, terms: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for term in terms:
        if normalize_signal_text(term) in normalized and term not in found:
            found.append(term)
    return found


def is_social_monitoring_query(query: str) -> bool:
    normalized = normalize_signal_text(query)
    strong_triggers = (
        "sosyal medya",
        "x hesab",
        "x'te",
        "x te",
        "mention",
        "bana ne yazildi",
        "bana ne yazıldı",
        "paylasim",
        "paylaşım",
    )
    if any(token in normalized for token in strong_triggers):
        return True
    comment_triggers = (
        "yorumlar",
        "yorumlari",
        "yorumlara",
        "gelen yorum",
        "yorum yapmis",
        "yorum yapmış",
        "kim ne yorum",
        "yorumlari oku",
        "yorumları oku",
    )
    return any(token in normalized for token in comment_triggers)


def classify_social_content(
    source: str,
    handle: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_signal_text(content)
    abuse_terms = _matched_terms(normalized, _ABUSE_TERMS)
    threat_terms = _matched_terms(normalized, _THREAT_TERMS)
    accusation_terms = _matched_terms(normalized, _ACCUSATION_TERMS)
    complaint_terms = _matched_terms(normalized, _COMPLAINT_TERMS)
    question_terms = _matched_terms(normalized, _QUESTION_TERMS)
    public_source = str(source or "").strip().lower() in {"x", "linkedin", "instagram", "news"}
    lower_handle = str(handle or "").strip() or "ilgili hesap"
    visibility_note = "kamusal akışta" if public_source else "dış kanalda"
    signal_type = "engagement"
    severity = "info"
    risk_score = 0.2
    notify_user = False
    evidence_candidate = False
    reply_needed = bool(question_terms)
    tags: list[str] = []

    if threat_terms:
        signal_type = "threat"
        severity = "critical"
        risk_score = 0.96
        notify_user = True
        evidence_candidate = True
        reply_needed = False
        tags.extend(["tehdit", "acil"])
        summary = f"{lower_handle} tarafından {visibility_note} tehdit sinyali içeren bir paylaşım görüldü."
        suggested_action = "İçeriği ekran görüntüsü, bağlantı ve zaman bilgisiyle saklayıp dosyada delil olarak değerlendirebiliriz."
    elif abuse_terms:
        signal_type = "abuse"
        severity = "high"
        risk_score = 0.84
        notify_user = True
        evidence_candidate = True
        reply_needed = False
        tags.extend(["hakaret", "itibar_riski"])
        summary = f"{lower_handle} tarafından {visibility_note} hakaret/küfür sinyali taşıyan bir paylaşım görüldü."
        suggested_action = "Bu içeriği delil niteliğiyle arşivleyip gerekiyorsa ilgili dosyada değerlendirebiliriz."
    elif accusation_terms:
        signal_type = "accusation"
        severity = "high"
        risk_score = 0.74
        notify_user = True
        evidence_candidate = True
        reply_needed = False
        tags.extend(["itham", "kamusal_risk"])
        summary = f"{lower_handle} tarafından {visibility_note} dava/şikayet veya itham dili içeren bir paylaşım görüldü."
        suggested_action = "İçeriği not alıp yanıt stratejisini ve dosya etkisini birlikte değerlendirebiliriz."
    elif complaint_terms:
        signal_type = "complaint"
        severity = "medium"
        risk_score = 0.52
        notify_user = True
        evidence_candidate = False
        reply_needed = True
        tags.append("şikayet")
        summary = f"{lower_handle} tarafından izleme gerektiren bir şikayet/olumsuz geri bildirim paylaşıldı."
        suggested_action = "İstersen yanıt önceliğini çıkarıp kontrollü bir cevap yaklaşımı hazırlayabilirim."
    else:
        signal_type = "engagement"
        severity = "low" if question_terms else "info"
        risk_score = 0.24 if question_terms else 0.18
        summary = f"{lower_handle} hesabından takip edilebilir bir sosyal etkileşim kaydedildi."
        suggested_action = "İstersen son yorumları ve yanıt bekleyenleri özetleyebilirim."

    if metadata and metadata.get("manual_review_required") is True:
        notify_user = True

    if public_source and severity in {"high", "critical"}:
        risk_score = min(1.0, risk_score + 0.04)

    evidence_note = (
        "Bağlantı, ekran görüntüsü, kullanıcı adı ve zaman damgasıyla birlikte delil olarak saklanırsa hukukî değerlendirmede daha güçlü olur."
        if evidence_candidate
        else ""
    )
    if reply_needed and signal_type == "engagement":
        tags.append("yanit")

    return {
        "source": str(source or "").strip().lower() or "social",
        "handle": lower_handle,
        "category": signal_type,
        "severity": severity,
        "risk_score": round(risk_score, 2),
        "notify_user": notify_user,
        "reply_needed": reply_needed,
        "legal_signal": signal_type in {"threat", "abuse", "accusation"},
        "evidence_candidate": evidence_candidate,
        "summary": summary,
        "suggested_action": suggested_action,
        "evidence_note": evidence_note,
        "matched_terms": [*threat_terms, *abuse_terms, *accusation_terms, *complaint_terms][:8],
        "tags": tags,
    }


def social_signal_from_metadata(
    source: str,
    handle: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nested = metadata.get("social_signal") if isinstance(metadata, dict) else None
    if isinstance(nested, dict) and nested.get("category"):
        return dict(nested)
    return classify_social_content(source, handle, content, metadata=metadata)
