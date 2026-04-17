from __future__ import annotations

import re


def normalize_persona_text(value: str) -> str:
    return (
        str(value or "")
        .lower()
        .replace("i̇", "i")
        .replace("\u0307", "")
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def clean_persona_text(value: str, *, limit: int = 240) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    cleaned = cleaned.strip("“”\"' ")
    cleaned = cleaned.strip(" .,:;!?")
    return cleaned[:limit]


def contains_normalized_phrase(text: str, phrase: str) -> bool:
    normalized_text = normalize_persona_text(text)
    normalized_phrase = normalize_persona_text(phrase)
    if not normalized_text or not normalized_phrase:
        return False
    pattern = re.escape(normalized_phrase).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", normalized_text) is not None


def extract_match(patterns: list[re.Pattern[str]], text: str, *, limit: int = 120) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        value = clean_persona_text(match.group(1), limit=limit)
        if value:
            return value
    return None


def append_unique_note(existing: str | None, note: str) -> str:
    candidate = clean_persona_text(note, limit=260)
    if not candidate:
        return str(existing or "").strip()
    current = str(existing or "").strip()
    if normalize_persona_text(candidate) in normalize_persona_text(current):
        return current
    if current:
        return f"{current}\n- {candidate}"
    return candidate


def normalize_profile_memory_notes(value: str | None) -> str:
    support_areas: list[str] = []
    normalized_lines: list[str] = []
    seen_lines: set[str] = set()

    for raw_line in str(value or "").splitlines():
        cleaned = clean_persona_text(re.sub(r"^[-*]\s*", "", raw_line), limit=260)
        if not cleaned:
            continue
        extracted_support = _extract_support_areas(cleaned)
        if cleaned.lower().startswith("öncelikli destek alanları:") or extracted_support:
            support_areas.extend(extracted_support)
            if extracted_support:
                continue
        comparable = normalize_persona_text(re.sub(r"[.!?]+$", "", cleaned))
        if comparable in seen_lines:
            continue
        seen_lines.add(comparable)
        normalized_lines.append(_ensure_sentence(cleaned))

    merged_support = list(dict.fromkeys(support_areas))
    if merged_support:
        normalized_lines.insert(0, f"Öncelikli destek alanları: {_join_terms(merged_support)}.")

    return "\n".join(normalized_lines)


def merge_profile_memory_note(existing: str | None, note: str) -> str:
    current = str(existing or "").strip()
    candidate = clean_persona_text(note, limit=260)
    if not candidate:
        return normalize_profile_memory_notes(current)
    combined = f"{current}\n{candidate}" if current else candidate
    return normalize_profile_memory_notes(combined)


DISPLAY_NAME_PATTERNS = [
    re.compile(r"\b(?:benim ad[ıi]m|ad[ıi]m|ismim)[: ]+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{1,40})", re.IGNORECASE),
    re.compile(r"\bbana\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{1,40})\s+diye\s+hitap\s+et", re.IGNORECASE),
    re.compile(r"\bbana\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{1,40})\s+de\b", re.IGNORECASE),
    re.compile(r"\bbana\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{1,40})\s+diye\s+seslen", re.IGNORECASE),
    re.compile(
        r"\b(?:ad[ıi]m[ıi]|ismim[ıi]|hitab[ıi]m[ıi])\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{0,40}?)(?=\s+(?:olarak\s+)?(?:g[uü]ncelle|de[gğ]i[sş]tir|yap|kaydet|olsun)\b|[.!?,]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:benim\s+)?(?:ad[ıi]m|ismim)\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{0,40}?)(?=\s+(?:diye|olarak|sadece|demistim|demiştim|kalsin|kalsın|yeterli)\b|[.!?,]|$)",
        re.IGNORECASE,
    ),
]
ASSISTANT_NAME_PATTERNS = [
    re.compile(r"\b(?:senin ad[ıi]n|ad[ıi]n)\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{1,40})\s+olsun", re.IGNORECASE),
    re.compile(r"\bsana\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{1,40})\s+diyeyim", re.IGNORECASE),
    re.compile(
        r"\b(?:ad[ıi]n[ıi]|ismin[ıi]|asistan(?:[ıi]n)?\s+ad[ıi]n[ıi])\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{0,40}?)(?=\s+(?:olarak\s+)?(?:g[uü]ncelle|de[gğ]i[sş]tir|yap|kaydet|olsun)\b|[.!?,]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:senin\s+)?(?:ad[ıi]n|ismin)\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{0,40}?)(?=\s+(?:olsun|olmali|olmalı|olacak|olucak|kalsin|kalsın|diye|de|olarak|sadece|demistim|demiştim|yeterli|yap|g[uü]ncelle|de[gğ]i[sş]tir|istiyorum|isterim)\b|[.!?,]|$)",
        re.IGNORECASE,
    ),
]
EXPLICIT_USER_NAME_UPDATE_PATTERNS = [
    re.compile(
        r"\b(?:ad[ıi]m[ıi]|ismim[ıi]|hitab[ıi]m[ıi])\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{0,40}?)(?=\s+(?:olarak\s+)?(?:g[uü]ncelle|de[gğ]i[sş]tir|yap|kaydet|olsun|kalsin|kalsın)\b)",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:art[ıi]k\s+|bundan\s+sonra\s+)?bana\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{0,40}?)\s+diye\s+(?:seslen|hitap\s+et|hitap|de)\b", re.IGNORECASE),
]
EXPLICIT_ASSISTANT_NAME_UPDATE_PATTERNS = [
    re.compile(
        r"\b(?:ad[ıi]n[ıi]|ismin[ıi]|asistan(?:[ıi]n)?\s+ad[ıi]n[ıi])\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{0,40}?)(?=\s+(?:olarak\s+)?(?:g[uü]ncelle|de[gğ]i[sş]tir|yap|kaydet|olsun|kalsin|kalsın)\b)",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:art[ıi]k\s+)?sana\s+([A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü' -]{0,40}?)\s+diyeyim\b", re.IGNORECASE),
]
FAVORITE_COLOR_PATTERNS = [
    re.compile(r"\b(?:en sevdi(?:ğ|g)im renk|favori rengim)[: ]+([A-Za-zÇĞİÖŞÜçğıöşü -]{2,40})", re.IGNORECASE),
    re.compile(r"\bsevdi(?:ğ|g)im\s+renk(?:im)?\s+(?:genelde\s+)?([A-Za-zÇĞİÖŞÜçğıöşü -]{2,40})", re.IGNORECASE),
    re.compile(r"\b([A-Za-zÇĞİÖŞÜçğıöşü -]{2,40})\s+rengini\s+severim", re.IGNORECASE),
]
ROLE_SUMMARY_PATTERNS = [
    re.compile(r"\b(?:rol(?:u|ü|um|üm|un|ün)|gorev(?:in|im)?)\s*(?::|olarak)?\s*(.+?)(?:\s+olsun|\s+olur|\s+ol|$)", re.IGNORECASE),
]
USER_DIRECTION_MARKERS = ("bana", "cevap", "yanit", "özet", "konus", "anlat", "iletisim", "iletişim", "hitap", "uslubum", "üslubum", "stilim", "tonum", "dilim")
ASSISTANT_DIRECTION_MARKERS = (
    "sen ",
    "asistan",
    "cevaplarin",
    "yanitlarin",
    "tonun",
    "tonunu",
    "karakterin",
    "kisiligin",
    "uslubunu",
    "üslubünü",
    "üslubunu",
    "tarzini",
    "tarzını",
    "dilini",
    "rolunu",
    "rolünü",
    "davranisini",
    "davranışını",
    "ciddisin",
    "resmisin",
    "soguksun",
    "soğuksun",
    "fazla ciddi",
    "fazla resmi",
    "fazla soguk",
    "fazla soğuk",
    "daha az ciddi",
    "daha sicak",
    "daha sıcak",
    "daha az sakaci",
    "daha az şakaci",
    "daha az şakacı",
    "sakaci ol",
    "şakacı ol",
    "daha sıcak ol",
    "daha sicak ol",
)
TONE_KEYWORDS = [
    ("sakaci", "Şakacı"),
    ("komik", "Şakacı"),
    ("esprili", "Şakacı"),
    ("eglenceli", "Şakacı"),
    ("mizahli", "Şakacı"),
    ("samimi", "Samimi"),
    ("dogal", "Samimi"),
    ("arkadasca", "Samimi"),
    ("rahat", "Samimi"),
    ("icten", "Samimi"),
    ("sicak", "Sıcak"),
    ("yumusak", "Sıcak"),
    ("cana yakin", "Sıcak"),
    ("resmi", "Resmi"),
    ("profesyonel", "Profesyonel"),
    ("kisa", "Kısa"),
    ("oz", "Kısa"),
    ("detayli", "Detaylı"),
    ("ayrintili", "Detaylı"),
    ("direkt", "Direkt"),
    ("dogrudan", "Direkt"),
    ("yaratici", "Yaratıcı"),
    ("net", "Net"),
    ("acik", "Net"),
    ("ciddi", "Ciddi"),
    ("sakin", "Sakin"),
    ("nazik", "Nazik"),
    ("kibar", "Nazik"),
]
ROLE_HINT_LABELS = [
    ("kisisel hukuk asistani", "Kişisel hukuk asistanı"),
    ("hukuk calisma asistani", "Hukuk çalışma asistanı"),
    ("hukuk asistani", "Hukuk asistanı"),
    ("kisisel asistan", "Kişisel asistan"),
    ("operasyon kocu", "Operasyon koçu"),
    ("koordinator", "Koordinatör"),
    ("yol arkadasi", "Yol arkadaşı"),
    ("calisma asistani", "Çalışma asistanı"),
]
ROLE_HINTS = tuple(key for key, _label in ROLE_HINT_LABELS)
NAME_LEADING_NOISE = {
    "benim",
    "senin",
    "bana",
    "sana",
    "yani",
    "hayir",
    "hayır",
    "evet",
    "tamam",
    "artık",
    "artik",
    "bu",
    "su",
    "şu",
    "sadece",
    "neyse",
    "yanlis",
    "yanlış",
    "girmissin",
    "girmişsin",
    "soylesene",
    "söylesene",
    "onu",
    "o",
    "adim",
    "adım",
    "adimi",
    "adımı",
    "isim",
    "ismim",
    "ismimi",
    "ismimı",
    "adin",
    "adın",
    "adini",
    "adını",
    "ismin",
    "ismini",
    "hitabimi",
    "hitabımı",
}
NAME_BOUNDARY_WORDS = {
    "adim",
    "adım",
    "adimi",
    "adımı",
    "isim",
    "ismim",
    "ismimi",
    "adin",
    "adın",
    "adini",
    "adını",
    "ismin",
    "ismini",
    "sadece",
    "diye",
    "de",
    "olarak",
    "olsun",
    "olmali",
    "olmalı",
    "olacak",
    "olucak",
    "yap",
    "yapalim",
    "yapalım",
    "guncelle",
    "güncelle",
    "degistir",
    "değiştir",
    "istiyorum",
    "isterim",
    "kalsin",
    "kalsın",
    "yeterli",
    "mi",
    "mı",
    "mu",
    "mü",
    "olur",
    "demistim",
    "demiştim",
    "kismi",
    "kısmı",
    "kisim",
    "degil",
    "değil",
    "ismi",
    "adi",
    "adı",
    "q",
    "ne",
    "nedir",
    "neydi",
}


def compact_user_profile_value(field: str, value: str) -> str:
    cleaned = clean_persona_text(value)
    if not cleaned:
        return ""
    if field == "display_name":
        return extract_explicit_user_name_update(cleaned) or _compact_name(cleaned, DISPLAY_NAME_PATTERNS)
    if field == "favorite_color":
        candidate = extract_match(FAVORITE_COLOR_PATTERNS, cleaned, limit=40) or cleaned
        return clean_persona_text(candidate, limit=40).lower()
    if field == "communication_style":
        return _compact_communication_style(cleaned)
    if field == "transport_preference":
        return _compact_transport_preference(cleaned)
    if field == "food_preferences":
        return _compact_food_preferences(cleaned)
    if field == "travel_preferences":
        return _compact_travel_preferences(cleaned)
    if field == "weather_preference":
        return _compact_weather_preference(cleaned)
    if field == "assistant_notes":
        return summarize_user_support_note(cleaned)
    return cleaned


def compact_assistant_profile_value(field: str, value: str) -> str:
    cleaned = clean_persona_text(value)
    if not cleaned:
        return ""
    if field == "assistant_name":
        return extract_explicit_assistant_name_update(cleaned) or _compact_name(cleaned, ASSISTANT_NAME_PATTERNS)
    if field == "tone":
        return _compact_tone(cleaned)
    if field == "role_summary":
        return _compact_role_summary(cleaned)
    if field == "soul_notes":
        return _compact_soul_notes(cleaned)
    return cleaned


def summarize_user_support_note(value: str) -> str:
    cleaned = clean_persona_text(value, limit=220)
    if not cleaned:
        return ""
    support_areas = _extract_support_areas(cleaned)
    if support_areas:
        return f"Öncelikli destek alanları: {_join_terms(support_areas)}."
    return _to_user_preference_statement(cleaned)


def extract_explicit_user_name_update(value: str) -> str:
    candidate = extract_match(EXPLICIT_USER_NAME_UPDATE_PATTERNS, value, limit=40)
    return _compact_name_candidate(candidate or "")


def extract_explicit_assistant_name_update(value: str) -> str:
    candidate = extract_match(EXPLICIT_ASSISTANT_NAME_UPDATE_PATTERNS, value, limit=40)
    return _compact_name_candidate(candidate or "")


def _compact_name(value: str, patterns: list[re.Pattern[str]]) -> str:
    candidate = extract_match(patterns, value, limit=40) or clean_persona_text(value, limit=40)
    return _compact_name_candidate(candidate)


def _compact_name_candidate(candidate: str) -> str:
    candidate = re.sub(r"\b(?:bana|sana)\b", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(
        r"\b(?:diye\s+)?(?:hitap\s+et|diyeyim|olsun|olur|seslen(?:ebilirsin|in)?|diyebilirsin)\b",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = clean_persona_text(candidate, limit=40)
    words: list[str] = []
    for part in candidate.split():
        cleaned_part = clean_persona_text(part, limit=40)
        normalized_part = normalize_persona_text(cleaned_part).strip("'")
        if not normalized_part:
            continue
        if not words and normalized_part in NAME_LEADING_NOISE:
            continue
        if words and normalized_part in NAME_BOUNDARY_WORDS:
            break
        if normalized_part in NAME_BOUNDARY_WORDS:
            continue
        words.append(cleaned_part)
    if not words:
        return ""
    if len(words) == 1:
        return (words[0][0].upper() + words[0][1:])[:40]
    return " ".join(word[0].upper() + word[1:] if word else "" for word in words)[:40]


def _compact_tone(value: str) -> str:
    normalized = normalize_persona_text(value)
    if any(
        keyword in normalized
        for keyword in (
            "fazla ciddi",
            "ciddisin",
            "fazla resmi",
            "resmisin",
            "fazla soguk",
            "soguksun",
            "daha az ciddi",
            "daha az resmi",
            "daha az soguk",
        )
    ):
        return "Samimi, Sıcak, Net"

    blocked_labels: set[str] = set()
    labels: list[str] = []

    for keyword, label in TONE_KEYWORDS:
        negative_markers = (
            f"{keyword} degil",
            f"{keyword} olma",
            f"{keyword} olmasin",
            f"{keyword} istemem",
            f"{keyword} istemiyorum",
            f"{keyword} sevmem",
            f"daha az {keyword}",
            f"az {keyword}",
            f"fazla {keyword}",
        )
        if any(marker in normalized for marker in negative_markers):
            blocked_labels.add(label)
            continue
        if keyword in normalized and label not in labels:
            labels.append(label)

    labels = [label for label in labels if label not in blocked_labels]
    if labels:
        return ", ".join(dict.fromkeys(labels))
    trimmed = re.sub(r"^(?:biraz|daha)\s+", "", value, flags=re.IGNORECASE)
    return clean_persona_text(trimmed, limit=80)


def merge_assistant_tone(current: str | None, value: str) -> str:
    normalized = normalize_persona_text(value)
    if not normalized:
        return clean_persona_text(str(current or ""), limit=80)

    ordered_labels = ["Samimi", "Sıcak", "Net", "Şakacı", "Profesyonel", "Resmi", "Direkt", "Detaylı", "Kısa", "Nazik", "Ciddi", "Sakin", "Yaratıcı"]

    def parse_labels(source: str | None) -> list[str]:
        text = str(source or "")
        labels: list[str] = []
        for label in ordered_labels:
            if normalize_persona_text(label) in normalize_persona_text(text):
                labels.append(label)
        return labels

    labels = parse_labels(current)
    if not labels:
        compacted = _compact_tone(value)
        return compacted

    blocked_labels: set[str] = set()
    removals: list[tuple[str, str]] = [
        ("sakaci", "Şakacı"),
        ("resmi", "Resmi"),
        ("ciddi", "Ciddi"),
        ("soguk", "Sıcak"),
        ("samimi", "Samimi"),
    ]
    for keyword, label in removals:
        if any(marker in normalized for marker in (f"daha az {keyword}", f"az {keyword}", f"{keyword} olma", f"{keyword}ligi azalt", f"{keyword}liği azalt", f"fazla {keyword}")):
            labels = [item for item in labels if item != label]
            blocked_labels.add(label)
            if keyword in {"resmi", "ciddi", "soguk"}:
                for replacement in ("Samimi", "Sıcak", "Net"):
                    if replacement not in labels:
                        labels.append(replacement)

    additions = [label for keyword, label in TONE_KEYWORDS if keyword in normalized]
    for label in additions:
        if label in blocked_labels:
            continue
        if label not in labels:
            labels.append(label)

    if not labels:
        return _compact_tone(value)

    sorted_labels = [label for label in ordered_labels if label in labels]
    return ", ".join(sorted_labels)


def _compact_role_summary(value: str) -> str:
    normalized = normalize_persona_text(value)
    if "tam bir asistan" in normalized or "tam asistan" in normalized:
        return "Tam kapsamlı profesyonel asistan"
    for key, label in ROLE_HINT_LABELS:
        if key in normalized:
            return label
    candidate = extract_match(ROLE_SUMMARY_PATTERNS, value, limit=120) or value
    candidate = re.sub(r"^(?:rol(?:u|ü|um|üm|un|ün)|gorev(?:in|im)?)\s*(?::|olarak)?\s*", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\b(?:olsun|olur|ol)\b$", "", candidate, flags=re.IGNORECASE)
    candidate = clean_persona_text(candidate, limit=120)
    return candidate[0].upper() + candidate[1:] if candidate else ""


def _compact_communication_style(value: str) -> str:
    normalized = normalize_persona_text(value)
    styles = []
    for keyword, label in (
        ("kisa", "kısa"),
        ("oz", "özlü"),
        ("net", "net"),
        ("acik", "açık"),
        ("detayli", "detaylı"),
        ("resmi", "resmi"),
        ("samimi", "samimi"),
        ("dogal", "doğal"),
        ("arkadasca", "arkadaşça"),
        ("direkt", "direkt"),
        ("profesyonel", "profesyonel"),
        ("sicak", "sıcak"),
        ("nazik", "nazik"),
        ("kibar", "nazik"),
        ("komik", "şakacı"),
        ("sakaci", "şakacı"),
        ("esprili", "şakacı"),
    ):
        if keyword in normalized:
            styles.append(label)
    styles = list(dict.fromkeys(styles))
    if styles:
        return f"İletişimde {_join_terms(styles)} bir üslup tercih eder."
    return f"İletişim tercihi: {_trimmed_fragment(value)}."


def _compact_transport_preference(value: str) -> str:
    normalized = normalize_persona_text(value)
    preferred_mode = _extract_preferred_transport_mode(normalized)
    if preferred_mode:
        prefix = "Ulaşımda mümkünse " if any(marker in normalized for marker in ("mumkunse", "mümkünse", "genelde")) else "Ulaşımda "
        if any(marker in normalized for marker in ("kacinirim", "kaçınırım", "istemem", "sevmem")):
            return f"{prefix}{preferred_mode} kullanmaktan kaçınır."
        return f"{prefix}{preferred_mode} tercih eder."
    modes = []
    for keyword, label in (
        ("tren", "tren"),
        ("metro", "metro"),
        ("ucak", "uçak"),
        ("araba", "araba"),
        ("otobus", "otobüs"),
        ("taksi", "taksi"),
        ("bisiklet", "bisiklet"),
        ("vapur", "vapur"),
    ):
        if keyword in normalized:
            modes.append(label)
    modes = list(dict.fromkeys(modes))
    if modes:
        prefix = "Ulaşımda mümkünse " if any(marker in normalized for marker in ("mumkunse", "mümkünse", "genelde")) else "Ulaşımda "
        if any(marker in normalized for marker in ("kacinirim", "kaçınırım", "istemem", "sevmem")):
            return f"{prefix}{_join_terms(modes)} kullanmaktan kaçınır."
        return f"{prefix}{_join_terms(modes)} tercih eder."
    return f"Ulaşım tercihi: {_trimmed_fragment(value)}."


TRANSPORT_MODE_MATCHERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("tren", re.compile(r"(?<![a-z0-9])tren(?:i|e|den|le)?(?![a-z0-9])")),
    ("metro", re.compile(r"(?<![a-z0-9])metro(?:yu|ya|dan|yla)?(?![a-z0-9])")),
    ("uçak", re.compile(r"(?<![a-z0-9])uca(?:k|g)(?:i|a|tan|la)?(?![a-z0-9])")),
    ("araba", re.compile(r"(?<![a-z0-9])araba(?:yi|ya|dan|yla)?(?![a-z0-9])")),
    ("otobüs", re.compile(r"(?<![a-z0-9])otobus(?:u|e|ten|le)?(?![a-z0-9])")),
    ("taksi", re.compile(r"(?<![a-z0-9])taksi(?:yi|ye|den|yle)?(?![a-z0-9])")),
    ("bisiklet", re.compile(r"(?<![a-z0-9])bisiklet(?:i|e|ten|le)?(?![a-z0-9])")),
    ("vapur", re.compile(r"(?<![a-z0-9])vapur(?:u|a|dan|la)?(?![a-z0-9])")),
)


def _extract_preferred_transport_mode(normalized: str) -> str:
    if "tercih" not in normalized:
        return ""
    mentions = _find_transport_mentions(normalized)
    if len(mentions) < 2:
        return ""
    preference_index = normalized.find("tercih")
    prior_mentions = [item for item in mentions if item["start"] < preference_index]
    if len(prior_mentions) < 2:
        return ""
    earlier = prior_mentions[-2]
    later = prior_mentions[-1]
    bridge = normalized[earlier["end"] : later["start"]]
    if any(token in bridge for token in (" yerine ", " degil ", " değil ")):
        return str(later["label"])
    return str(earlier["label"])


def _find_transport_mentions(normalized: str) -> list[dict[str, int | str]]:
    mentions: list[dict[str, int | str]] = []
    for label, pattern in TRANSPORT_MODE_MATCHERS:
        for match in pattern.finditer(normalized):
            mentions.append(
                {
                    "label": label,
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    mentions.sort(key=lambda item: (int(item["start"]), -(int(item["end"]) - int(item["start"]))))
    unique: list[dict[str, int | str]] = []
    occupied: list[tuple[int, int]] = []
    for item in mentions:
        start = int(item["start"])
        end = int(item["end"])
        if any(not (end <= occ_start or start >= occ_end) for occ_start, occ_end in occupied):
            continue
        occupied.append((start, end))
        unique.append(item)
    return unique


def _compact_food_preferences(value: str) -> str:
    normalized = normalize_persona_text(value)
    items = []
    for keyword, label in (
        ("kahve", "kahve"),
        ("cay", "çay"),
        ("vegan", "vegan seçenekler"),
        ("vejetaryen", "vejetaryen seçenekler"),
        ("pizza", "pizza"),
        ("burger", "burger"),
        ("tatli", "tatlı"),
    ):
        if keyword in normalized:
            items.append(label)
    items = list(dict.fromkeys(items))
    if items:
        if any(marker in normalized for marker in ("kacinirim", "kaçınırım", "istemem")):
            return f"Yeme içmede {_join_terms(items)} konusunda temkinlidir."
        if "sevmem" in normalized:
            return f"Yeme içmede {_join_terms(items)} sevmez."
        if "tercih" in normalized:
            return f"Yeme içmede {_join_terms(items)} tercih eder."
        return f"Yeme içmede {_join_terms(items)} sever."
    return f"Yeme içme tercihi: {_trimmed_fragment(value)}."


def _compact_travel_preferences(value: str) -> str:
    normalized = normalize_persona_text(value)
    items = []
    for keyword, label in (
        ("tren", "tren yolculuğu"),
        ("ucak", "uçuş planı"),
        ("pencere", "pencere kenarı"),
        ("erken", "erken planlama"),
        ("otel", "otel seçimi"),
        ("konaklama", "konaklama düzeni"),
        ("deniz", "deniz kenarı"),
    ):
        if keyword in normalized:
            items.append(label)
    items = list(dict.fromkeys(items))
    if items:
        return f"Seyahatte {_join_terms(items)} tercih eder."
    return f"Seyahat tercihi: {_trimmed_fragment(value)}."


def _compact_weather_preference(value: str) -> str:
    normalized = normalize_persona_text(value)
    descriptors = []
    for keyword, label in (
        ("gunesli", "güneşli"),
        ("serin", "serin"),
        ("ilik", "ılık"),
        ("soguk", "soğuk"),
        ("sicak", "sıcak"),
        ("yagmurlu", "yağmurlu"),
        ("bulutlu", "bulutlu"),
    ):
        if keyword in normalized:
            descriptors.append(label)
    descriptors = list(dict.fromkeys(descriptors))
    if descriptors:
        if any(marker in normalized for marker in ("sevmem", "istemem", "kacinirim", "kaçınırım")):
            return f"{_join_terms(descriptors).capitalize()} havayı sevmez."
        return f"{_join_terms(descriptors).capitalize()} havayı sever."
    return f"Hava tercihi: {_trimmed_fragment(value)}."


def _compact_soul_notes(value: str) -> str:
    normalized = normalize_persona_text(value)
    notes = []
    if any(keyword in normalized for keyword in ("fazla ciddi", "ciddisin", "fazla resmi", "resmisin", "fazla soguk", "soguksun")):
        notes.append("Gereksiz resmi ve sert tondan kaçın.")
    if "proaktif" in normalized:
        notes.append("Proaktif ilerle.")
    if any(keyword in normalized for keyword in ("temkinli", "dikkatli")):
        notes.append("Temkinli ilerle.")
    if any(keyword in normalized for keyword in ("onay", "haber ver", "danis", "danış")):
        notes.append("Kritik aksiyonlarda kullanıcı onayı iste.")
    if any(keyword in normalized for keyword in ("sinir", "sınır", "yetki")):
        notes.append("Yetki sınırlarını açıkça koru.")
    if any(keyword in normalized for keyword in ("kaynak", "dayanak")):
        notes.append("Kaynak dayanağı olmayan kesin hüküm kurma.")
    if any(keyword in normalized for keyword in ("belirsiz", "emin degil", "emin değil")):
        notes.append("Belirsizlik varsa açıkça belirt.")
    if any(keyword in normalized for keyword in ("takip", "hatirlat", "hatırlat")):
        notes.append("Takip ve hatırlatmalarda düzenli ol.")
    notes = list(dict.fromkeys(notes))
    if notes:
        return " ".join(notes)[:260]
    return ""


def _extract_support_areas(value: str) -> list[str]:
    normalized = normalize_persona_text(value)
    areas = []
    has_document_inventory = "belge envanter" in normalized or "envanter" in normalized
    for keyword, label in (
        ("durusma", "duruşma hazırlığı"),
        ("muvekkil", "müvekkil takibi"),
        ("dosya eksik", "dosya eksikleri"),
        ("belge envanter", "belge envanteri"),
        ("envanter", "belge envanteri"),
        ("belge", "belge takibi"),
        ("takvim", "takvim takibi"),
        ("ajanda", "ajanda takibi"),
        ("seyahat plan", "seyahat planı"),
        ("hatirlat", "hatırlatmalar"),
        ("tarih", "kişisel tarih hatırlatmaları"),
        ("aile", "aile hatırlatmaları"),
        ("taslak", "taslak takibi"),
        ("onay", "onay bekleyen işler"),
        ("mail", "e-posta takibi"),
        ("e posta", "e-posta takibi"),
        ("e-posta", "e-posta takibi"),
        ("mesaj", "iletişim takibi"),
        ("iletisim", "iletişim takibi"),
    ):
        if keyword == "belge" and has_document_inventory:
            continue
        if keyword in normalized:
            areas.append(label)
    return list(dict.fromkeys(areas))


def _to_user_preference_statement(value: str) -> str:
    statement = clean_persona_text(value, limit=180)
    replacements = (
        (r"\bisterim\b", "ister"),
        (r"\bistiyorum\b", "ister"),
        (r"\bseverim\b", "sever"),
        (r"\bseviyorum\b", "sever"),
        (r"\bsevmem\b", "sevmez"),
        (r"\btercih ederim\b", "tercih eder"),
        (r"\btercih ediyorum\b", "tercih eder"),
        (r"\bhoşlanırım\b", "hoşlanır"),
        (r"\bhoslanirim\b", "hoşlanır"),
        (r"\bkaçınırım\b", "kaçınır"),
        (r"\bkacinirim\b", "kaçınır"),
        (r"\bistemem\b", "istemez"),
    )
    for pattern, replacement in replacements:
        statement = re.sub(pattern, replacement, statement, flags=re.IGNORECASE)
    statement = re.sub(r"\bbenim için\b", "", statement, flags=re.IGNORECASE)
    statement = re.sub(r"\bben\b", "", statement, flags=re.IGNORECASE)
    statement = re.sub(r"\bbana\b", "kendisine", statement, flags=re.IGNORECASE)
    return _ensure_sentence(statement)


def _trimmed_fragment(value: str) -> str:
    fragment = clean_persona_text(value, limit=140)
    fragment = re.sub(r"^(?:bana|benim için|genelde|gün içinde|ozellikle|özellikle)\s+", "", fragment, flags=re.IGNORECASE)
    return fragment[0].lower() + fragment[1:] if fragment else ""


def _ensure_sentence(value: str) -> str:
    cleaned = clean_persona_text(value, limit=220)
    if not cleaned:
        return ""
    cleaned = cleaned[0].upper() + cleaned[1:]
    if cleaned.endswith("."):
        return cleaned
    return f"{cleaned}."


def _join_terms(items: list[str]) -> str:
    unique_items = [item for item in dict.fromkeys(items) if item]
    if not unique_items:
        return ""
    if len(unique_items) == 1:
        return unique_items[0]
    if len(unique_items) == 2:
        return f"{unique_items[0]} ve {unique_items[1]}"
    return ", ".join(unique_items[:-1]) + f" ve {unique_items[-1]}"
