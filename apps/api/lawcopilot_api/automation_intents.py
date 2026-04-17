from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any


CONTACT_ROLE_TERMS = (
    "ceo",
    "cfo",
    "cto",
    "coo",
    "kurucu",
    "founder",
    "müvekkil",
    "muvekkil",
    "finans",
    "yonetim",
    "yönetim",
    "ortak",
)

CONTACT_STOPWORDS = {
    "Asistan",
    "Outlook",
    "WhatsApp",
    "Mail",
    "Mailler",
    "Mesaj",
    "Mesajlar",
    "Desktop",
    "Masaustu",
    "Masaüstü",
    "Otomasyon",
    "Heartbeat",
}

AUTOMATION_COMMAND_PHRASES = (
    "ayarla",
    "kur",
    "ac",
    "aç",
    "kapat",
    "sil",
    "kaldir",
    "kaldır",
    "iptal et",
    "devre disi",
    "devre dışı",
    "aktif et",
    "pasif et",
    "etkinlestir",
    "etkinleştir",
)

AUTO_REPLY_PHRASES = (
    "otomatik cevapla",
    "otomatik cevap ver",
    "otomatik yanitla",
    "otomatik yanit ver",
    "otomatik yanıtla",
    "otomatik yanıt ver",
    "kendin cevapla",
    "kendin yanitla",
    "kendin yanıtla",
)

NOTIFY_PHRASES = (
    "haber ver",
    "bildir",
    "uyar",
    "beni haberdar et",
    "bana yaz",
    "bana söyle",
)

REMINDER_PHRASES = (
    "hatirlat",
    "hatırlat",
    "hatirlatma",
    "hatırlatma",
)

GENERIC_MATCH_TERMS = (
    "gunaydin",
    "günaydın",
    "iyi bayramlar",
    "bayram",
    "teşekkür",
    "tesekkur",
    "acil",
)


def _normalized_text(value: str) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "’": "'",
        "“": '"',
        "”": '"',
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_text_list(values: list[str]) -> list[str]:
    items: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in items:
            continue
        items.append(value)
    return items


def _extract_phone_numbers(value: str) -> list[str]:
    matches = re.findall(r"(?:\+?\d[\d\s().-]{8,}\d)", value)
    normalized: list[str] = []
    for raw in matches:
        digits = re.sub(r"[^\d+]", "", raw)
        if digits and digits not in normalized:
            normalized.append(digits)
    return normalized


def _extract_email_targets(value: str) -> list[str]:
    return _normalize_text_list(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", value))


def _extract_handles(value: str) -> list[str]:
    return _normalize_text_list(re.findall(r"@\w{2,32}", value))


def _extract_quoted_phrases(value: str) -> list[str]:
    phrases = re.findall(r"""["'“”‘’]([^"'“”‘’]{2,160})["'“”‘’]""", value)
    cleaned: list[str] = []
    for raw in phrases:
        candidate = re.sub(r"\s+", " ", raw).strip(" ,.;:-")
        if not candidate:
            continue
        cleaned.append(candidate)
    return _normalize_text_list(cleaned)


def _extract_capitalized_entities(value: str) -> list[str]:
    matches = re.findall(r"\b(?:[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü.-]+)(?:\s+(?:[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü.-]+)){0,2}\b", value)
    items: list[str] = []
    for raw in matches:
        candidate = str(raw or "").strip()
        normalized = _normalized_text(candidate)
        if not candidate or candidate in CONTACT_STOPWORDS:
            continue
        if normalized in {item.lower() for item in CONTACT_STOPWORDS}:
            continue
        if len(candidate.split()) == 1 and not raw.isupper():
            continue
        items.append(candidate)
    return _normalize_text_list(items)


def _extract_role_targets(normalized_query: str) -> list[str]:
    hits: list[str] = []
    for term in CONTACT_ROLE_TERMS:
        if term in normalized_query:
            label = term.upper() if term in {"ceo", "cfo", "cto", "coo"} else term.capitalize()
            if label not in hits:
                hits.append(label)
    return hits


def _extract_contact_targets(query: str) -> list[str]:
    normalized_query = _normalized_text(query)
    combined = (
        _extract_phone_numbers(query)
        + _extract_email_targets(query)
        + _extract_handles(query)
        + _extract_capitalized_entities(query)
        + _extract_role_targets(normalized_query)
    )
    return _normalize_text_list(combined)[:8]


def _extract_explicit_message(query: str) -> str:
    quoted = _extract_quoted_phrases(query)
    if quoted:
        return quoted[-1]
    tail_match = re.search(r"(?:şöyle yaz|su sekilde yaz|şu şekilde yaz|mesaj olsun|yanit olsun|yanıt olsun)\s*[:：-]\s*(.+)$", query, re.IGNORECASE)
    if tail_match:
        return re.sub(r"\s+", " ", tail_match.group(1)).strip()
    return ""


def _extract_match_terms(query: str) -> list[str]:
    normalized = _normalized_text(query)
    terms = [item for item in _extract_quoted_phrases(query) if len(item.split()) <= 6]
    for candidate in GENERIC_MATCH_TERMS:
        if _normalized_text(candidate) in normalized and candidate not in terms:
            if _normalized_text(candidate) == "gunaydin":
                terms.append("günaydın")
            elif _normalized_text(candidate) == "tesekkur":
                terms.append("teşekkür")
            else:
                terms.append(candidate)
    return _normalize_text_list(terms)[:6]


def _extract_channels(normalized_query: str, *, default_to_whatsapp: bool = False) -> list[str]:
    channels: list[str] = []
    if "whatsapp" in normalized_query or "mesaj" in normalized_query:
        channels.append("whatsapp")
    if "telegram" in normalized_query:
        channels.append("telegram")
    if any(token in normalized_query for token in ("mail", "e-posta", "email", "outlook")):
        channels.append("email")
    if "x" in normalized_query or "tweet" in normalized_query:
        channels.append("x")
    if not channels and default_to_whatsapp:
        channels.append("whatsapp")
    return _normalize_text_list(channels)


def _has_automation_command(normalized_query: str) -> bool:
    return any(item in normalized_query for item in AUTOMATION_COMMAND_PHRASES)


def _has_auto_reply_intent(normalized_query: str) -> bool:
    return any(item in normalized_query for item in AUTO_REPLY_PHRASES)


def _has_notify_intent(normalized_query: str) -> bool:
    return any(item in normalized_query for item in NOTIFY_PHRASES)


def _extract_relative_count(raw: str) -> int:
    value = _normalized_text(raw)
    word_map = {
        "bir": 1,
        "iki": 2,
        "uc": 3,
        "dort": 4,
        "bes": 5,
        "alti": 6,
        "yedi": 7,
        "sekiz": 8,
        "dokuz": 9,
        "on": 10,
    }
    if value.isdigit():
        return int(value)
    return word_map.get(value, 0)


def _extract_reminder_at(query: str) -> str:
    normalized = _normalized_text(query)
    now = datetime.now().astimezone()

    relative_match = re.search(
        r"\b(\d{1,3}|bir|iki|uc|üç|dort|dört|bes|beş|alti|altı|yedi|sekiz|dokuz|on)\s*"
        r"(dk|dakika|saat|gun|gün|hafta)\s*sonra\b",
        normalized,
        re.IGNORECASE,
    )
    if relative_match:
        amount = _extract_relative_count(relative_match.group(1))
        unit = _normalized_text(relative_match.group(2))
        if amount > 0:
            delta = {
                "dk": timedelta(minutes=amount),
                "dakika": timedelta(minutes=amount),
                "saat": timedelta(hours=amount),
                "gun": timedelta(days=amount),
                "gün": timedelta(days=amount),
                "hafta": timedelta(days=amount * 7),
            }.get(unit)
            if delta:
                return (now + delta).isoformat()

    absolute_match = re.search(
        r"\b(?:bugun|bugün)?\s*(\d{1,2})(?:[:.\s])(\d{2})\s*(?:de|da|te|ta)?\b",
        normalized,
        re.IGNORECASE,
    )
    if absolute_match:
        hour = int(absolute_match.group(1))
        minute = int(absolute_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target = target + timedelta(days=1)
            return target.isoformat()

    if "yarin" in normalized or "yarın" in normalized:
        target = now + timedelta(days=1)
        hour = 9
        minute = 0
        time_match = re.search(r"\b(\d{1,2})[:.](\d{2})\b", normalized)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
        elif "aksam" in normalized or "akşam" in normalized:
            hour = 20
        elif "ogle" in normalized or "öğle" in normalized:
            hour = 12
        elif "sabah" in normalized:
            hour = 9
        return target.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()
    return ""


def _finalize_reminder_text(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    candidate = re.sub(
        r"\b(?:yarin|yarın|bugun|bugün)\b",
        " ",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"\b(?:\d{1,2}(?:[:.\s])\d{2}\s*(?:de|da|te|ta)?|\d{1,3}\s*(?:dk|dakika|saat|gun|gün|hafta)\s*sonra)\b",
        " ",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"^\s*(?:kullaniciya|kullanıcıya|bana|beni|bizi|sana|size)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"\b(?:gerektigini|gerektiğini|gerektigi|gerektiği)\b",
        " ",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"\b(?:hatirlat|hatırlat|hatirlatma|hatırlatma|soyle|söyle|de|diye|lutfen|lütfen|mesaj|gonder|gönder|at)\b",
        " ",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r"\s+", " ", candidate).strip(" ,.;:-")
    if not candidate:
        return ""
    parts = candidate.split()
    if parts:
        last = parts[-1]
        for suffix in ("meyi", "mayı", "mesi", "ması", "mayi", "mesi"):
            if last.lower().endswith(suffix) and len(last) > len(suffix) + 1:
                parts[-1] = last[: -len(suffix)]
                break
    candidate = " ".join(parts).strip(" ,.;:-")
    if not candidate:
        return ""
    return candidate[:1].upper() + candidate[1:240]


def _extract_reminder_text(query: str) -> str:
    explicit = _extract_explicit_message(query)
    if explicit:
        return _finalize_reminder_text(explicit)
    candidate = re.sub(
        r"\b(\d{1,3}|bir|iki|uc|üç|dort|dört|bes|beş|alti|altı|yedi|sekiz|dokuz|on)\s*"
        r"(dk|dakika|saat|gun|gün|hafta)\s*sonra\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r"\byarin\b|\byarın\b", " ", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\b(sabah|ogle|öğle|aksam|akşam|gece)\b", " ", candidate, flags=re.IGNORECASE)
    candidate = re.sub(
        r"\b(bana|beni|lutfen|lütfen|diye|soyle|şöyle|bir|mesaj|gonder|gönder|at|hatirlat|hatırlat)\b",
        " ",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r"\b\d{1,2}(?:[:.\s])\d{2}\s*(?:de|da|te|ta)?\b", " ", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s+", " ", candidate).strip(" ,.;:-")
    return _finalize_reminder_text(candidate)


def _has_reminder_intent(normalized_query: str) -> bool:
    return any(item in normalized_query for item in REMINDER_PHRASES)


def _operation_set(path: str, value: Any) -> dict[str, Any]:
    return {"op": "set", "path": path, "value": value}


def _operation_add_rule(rule: dict[str, Any]) -> dict[str, Any]:
    return {"op": "add_rule", "rule": rule}


def _operation_remove_rule(match_texts: list[str]) -> dict[str, Any] | None:
    cleaned = _normalize_text_list(match_texts)
    if not cleaned:
        return None
    return {"op": "remove_rule", "match_texts": cleaned}


def _channel_label(channels: list[str]) -> str:
    if not channels:
        return "Genel"
    label_map = {
        "whatsapp": "WhatsApp",
        "telegram": "Telegram",
        "email": "E-posta",
        "outlook": "Outlook",
        "x": "X",
        "generic": "Genel",
    }
    return " / ".join(label_map.get(item, item.capitalize()) for item in channels[:2])


def _build_rule_summary(*, mode: str, channels: list[str], targets: list[str], match_terms: list[str]) -> str:
    channel_label = _channel_label(channels)
    if mode == "reminder":
        return "Tek seferlik hatırlatma"
    if mode == "notify":
        if targets and match_terms:
            return f"{channel_label}'ta {targets[0]} veya \"{match_terms[0]}\" içeren iletileri bana bildir."
        if targets:
            return f"{channel_label}'ta {targets[0]} kaynaklı iletileri bana bildir."
        if match_terms:
            return f"{channel_label}'ta \"{match_terms[0]}\" içeren iletileri bana bildir."
        return f"{channel_label}'ta seçili iletileri bana bildir."
    if targets and match_terms:
        return f"{channel_label}'ta {targets[0]} veya \"{match_terms[0]}\" içeren iletileri kısa ve otomatik yanıtla."
    if targets:
        return f"{channel_label}'ta {targets[0]} kaynaklı iletileri kısa ve otomatik yanıtla."
    if match_terms:
        return f"{channel_label}'ta \"{match_terms[0]}\" içeren iletileri kısa ve otomatik yanıtla."
    return f"{channel_label}'ta seçili iletileri kısa ve otomatik yanıtla."


def build_assistant_automation_update(query: str) -> dict[str, Any] | None:
    original = str(query or "").strip()
    if not original:
        return None
    normalized = _normalized_text(original)
    operations: list[dict[str, Any]] = []
    warnings: list[str] = []

    disable_requested = any(token in normalized for token in ("kapat", "sil", "kaldir", "kaldır", "iptal et", "devre disi", "devre dışı"))
    skip_auto_reply_requested = any(
        token in normalized
        for token in ("otomatik cevaplama", "otomatik yanitlama", "otomatik yanıtlama", "cevaplama", "yanitlama", "yanıtlama")
    )
    auto_reply_requested = _has_auto_reply_intent(normalized)
    notify_requested = _has_notify_intent(normalized)
    reminder_requested = _has_reminder_intent(normalized)
    reminder_at = _extract_reminder_at(original)
    reminder_text = _extract_reminder_text(original)
    automation_related = (
        "otomasyon" in normalized
        or "heartbeat" in normalized
        or auto_reply_requested
        or notify_requested
        or (reminder_requested and bool(reminder_at))
    )

    if not automation_related or (
        not _has_automation_command(normalized)
        and not auto_reply_requested
        and not notify_requested
        and not (reminder_requested and bool(reminder_at))
    ):
        return None

    targets = _extract_contact_targets(original)
    match_terms = _extract_match_terms(original)
    important_requested = "onemli" in normalized or "önemli" in normalized
    mode = "notify"
    if auto_reply_requested and not skip_auto_reply_requested:
        mode = "auto_reply"
    elif notify_requested or skip_auto_reply_requested or important_requested:
        mode = "notify"
    channels = _extract_channels(normalized, default_to_whatsapp=mode == "auto_reply")
    explicit_message = _extract_explicit_message(original)

    if reminder_requested and reminder_at:
        reminder_body = reminder_text or explicit_message
        if not reminder_body:
            return {
                "mode": "assistant_heartbeat",
                "summary": "Hatırlatma için neyi not etmem gerektiğini biraz daha net yazman gerekiyor.",
                "warnings": ["Örneğin: 10 dakika sonra suyu kapatmayı hatırlat."],
                "needs_clarification": True,
                "operations": [],
            }
        reminder_summary = f"{reminder_body} hatırlatmasını kurdum."
        rule = {
            "summary": reminder_body,
            "instruction": original,
            "mode": "reminder",
            "channels": ["generic"],
            "targets": [],
            "match_terms": [],
            "reply_text": reminder_body,
            "reminder_at": reminder_at,
            "active": True,
        }
        operations.extend(
            [
                _operation_set("enabled", True),
                _operation_set("autoSyncConnectedServices", True),
                _operation_set("desktopNotifications", True),
                _operation_add_rule(rule),
            ]
        )
        return {
            "mode": "assistant_heartbeat",
            "summary": reminder_summary,
            "warnings": [],
            "needs_clarification": False,
            "operations": operations,
        }

    if disable_requested:
        match_texts = targets + match_terms + channels
        operation = _operation_remove_rule(match_texts)
        if operation:
            operations.append(operation)
            summary = "Eşleşen otomasyon kuralını kaldırdım."
        else:
            operations.append(_operation_set("enabled", False))
            summary = "Masaüstü otomasyonunu kapattım."
        return {
            "mode": "assistant_heartbeat",
            "summary": summary,
            "warnings": [],
            "needs_clarification": False,
            "operations": operations,
        }

    if not targets and not match_terms:
        return {
            "mode": "assistant_heartbeat",
            "summary": "Otomasyon kuralı için hedefi daha net yazman gerekiyor.",
            "warnings": ["Kişi, numara, kanal veya tetik ifade belirtirsen kuralı güvenli biçimde kaydederim."],
            "needs_clarification": True,
            "operations": [],
        }

    rule = {
        "summary": _build_rule_summary(mode=mode, channels=channels, targets=targets, match_terms=match_terms),
        "instruction": original,
        "mode": mode,
        "channels": channels,
        "targets": targets,
        "match_terms": match_terms,
        "reply_text": explicit_message if mode == "auto_reply" else "",
        "active": True,
    }
    operations.extend(
        [
            _operation_set("enabled", True),
            _operation_set("autoSyncConnectedServices", True),
            _operation_set("desktopNotifications", True),
            _operation_add_rule(rule),
        ]
    )

    if mode == "auto_reply" and not rule["reply_text"]:
        warnings.append("Ayrıca örnek bir yanıt metni yazarsan aynı kurala sabit cevap da ekleyebilirim.")

    return {
        "mode": "assistant_heartbeat",
        "summary": f"Otomasyon kuralını kaydettim: {rule['summary']}",
        "warnings": warnings,
        "needs_clarification": False,
        "operations": operations,
    }


def build_assistant_automation_update_from_plan(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        return None
    if str(plan.get("intent") or "").strip() != "configure_automation":
        return None

    mode = _normalized_text(str(plan.get("mode") or "notify"))
    if mode not in {"notify", "auto_reply", "disable", "reminder"}:
        mode = "notify"

    targets = _normalize_text_list([str(item).strip() for item in list(plan.get("targets") or []) if str(item).strip()])[:8]
    match_terms = _normalize_text_list([str(item).strip() for item in list(plan.get("match_terms") or []) if str(item).strip()])[:6]
    channels = _normalize_text_list([_normalized_text(str(item).strip()) for item in list(plan.get("channels") or []) if str(item).strip()])[:4]
    reply_text = re.sub(r"\s+", " ", str(plan.get("reply_text") or "").strip())
    instruction = re.sub(r"\s+", " ", str(plan.get("instructions") or "").strip())
    reminder_at = re.sub(r"\s+", " ", str(plan.get("reminder_at") or "").strip())
    warnings = _normalize_text_list([str(item).strip() for item in list(plan.get("warnings") or []) if str(item).strip()])
    operations: list[dict[str, Any]] = []

    if mode == "auto_reply" and not channels:
        channels = ["whatsapp"]
    if mode == "reminder":
        if not reminder_at:
            return {
                "mode": "assistant_heartbeat",
                "summary": "Hatırlatmayı ne zaman çalıştırmam gerektiği eksik.",
                "warnings": warnings or ["Örneğin: 10 dakika sonra veya yarın sabah 09:00 gibi bir zaman belirt."],
                "needs_clarification": True,
                "operations": [],
            }
        reminder_body = reply_text or instruction
        if not reminder_body:
            return {
                "mode": "assistant_heartbeat",
                "summary": "Hatırlatmada neyi söylemem gerektiği eksik.",
                "warnings": warnings or ["Hatırlatma metnini de açıkça yazarsan doğrudan kaydederim."],
                "needs_clarification": True,
                "operations": [],
            }
        reminder_body = _finalize_reminder_text(reminder_body)
        rule = {
            "summary": reminder_body,
            "instruction": instruction or reminder_body,
            "mode": "reminder",
            "channels": ["generic"],
            "targets": [],
            "match_terms": [],
            "reply_text": reminder_body,
            "reminder_at": reminder_at,
            "active": True,
        }
        operations.extend(
            [
                _operation_set("enabled", True),
                _operation_set("autoSyncConnectedServices", True),
                _operation_set("desktopNotifications", True),
                _operation_add_rule(rule),
            ]
        )
        return {
            "mode": "assistant_heartbeat",
            "summary": f"{reminder_body} hatırlatmasını kurdum.",
            "warnings": _normalize_text_list(warnings),
            "needs_clarification": False,
            "operations": operations,
        }

    if mode == "disable":
        operation = _operation_remove_rule(targets + match_terms + channels)
        if operation:
            operations.append(operation)
            summary = "Eşleşen otomasyon kuralını kaldırdım."
        else:
            operations.append(_operation_set("enabled", False))
            summary = "Masaüstü otomasyonunu kapattım."
        return {
            "mode": "assistant_heartbeat",
            "summary": summary,
            "warnings": warnings,
            "needs_clarification": False,
            "operations": operations,
        }

    if not targets and not match_terms:
        return {
            "mode": "assistant_heartbeat",
            "summary": "Otomasyon kuralı için hedefi daha net yazman gerekiyor.",
            "warnings": warnings
            or ["Kişi, numara, kanal veya tetik ifade belirtirsen kuralı güvenli biçimde kaydederim."],
            "needs_clarification": True,
            "operations": [],
        }

    rule = {
        "summary": _build_rule_summary(mode=mode, channels=channels, targets=targets, match_terms=match_terms),
        "instruction": instruction or _build_rule_summary(mode=mode, channels=channels, targets=targets, match_terms=match_terms),
        "mode": mode,
        "channels": channels,
        "targets": targets,
        "match_terms": match_terms,
        "reply_text": reply_text if mode == "auto_reply" else "",
        "active": True,
    }
    operations.extend(
        [
            _operation_set("enabled", True),
            _operation_set("autoSyncConnectedServices", True),
            _operation_set("desktopNotifications", True),
            _operation_add_rule(rule),
        ]
    )
    if mode == "auto_reply" and not rule["reply_text"]:
        warnings.append("Ayrıca örnek bir yanıt metni yazarsan aynı kurala sabit cevap da ekleyebilirim.")

    return {
        "mode": "assistant_heartbeat",
        "summary": f"Otomasyon kuralını kaydettim: {rule['summary']}",
        "warnings": _normalize_text_list(warnings),
        "needs_clarification": False,
        "operations": operations,
    }
