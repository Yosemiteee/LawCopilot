from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse


TASK_KIND_LABELS: dict[str, str] = {
    "general_research": "Genel araştırma",
    "legal_research": "Hukuk araştırması",
    "travel": "Seyahat",
    "travel_booking": "Bilet ve rezervasyon",
    "places": "Yer ve rota",
    "cinema": "Sinema ve etkinlik",
    "shopping": "Alışveriş",
    "clothing": "Kıyafet",
    "gift": "Hediye",
    "dining": "Yeme içme",
}

TASK_KIND_MARKERS: dict[str, tuple[str, ...]] = {
    "legal_research": ("emsal", "içtihat", "ictihat", "karar", "mevzuat", "kanun", "yargıtay", "danıştay", "danistay", "lexpera", "kazanci"),
    "travel_booking": ("bilet al", "rezervasyon", "rezerve", "satın al", "satin al", "otobüs bileti", "otobus bileti", "uçak bileti", "ucak bileti", "otel"),
    "travel": ("seyahat", "uçuş", "ucus", "otobüs", "otobus", "tren", "rota", "otel", "konaklama", "yolculuk"),
    "cinema": ("sinema", "film", "seans", "vizyon", "avm sinema"),
    "clothing": ("kıyafet", "kiyafet", "giyim", "kombin", "gömlek", "gomlek", "pantolon", "elbise", "ayakkabı", "ayakkabi", "ceket", "mont", "çanta", "canta"),
    "gift": ("hediye", "armağan", "armagan", "doğum günü hediyesi", "dogum gunu hediyesi", "yıl dönümü hediyesi", "yil donumu hediyesi"),
    "dining": ("restoran", "restaurant", "lokanta", "kafe", "cafe", "kahve", "kahveci", "meyhane", "bar"),
    "places": ("yakındaki", "yakindaki", "yakınımda", "yakinimda", "yakınımdaki", "yakinimdaki", "en yakın", "en yakin", "near me", "harita", "maps", "yol tarifi"),
    "shopping": ("alışveriş", "alisveris", "ürün", "urun", "mağaza", "magaza", "butik", "satın al", "satin al", "sepete", "stok"),
    "general_research": ("araştır", "arastir", "internette ara", "webde ara", "web'de ara", "öner", "oner", "bul", "bakar mısın", "bakar misin"),
}

TASK_KIND_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "travel_booking": ("travel", "general_research"),
    "travel": ("general_research",),
    "cinema": ("places", "general_research"),
    "clothing": ("shopping", "general_research"),
    "gift": ("shopping", "general_research"),
    "dining": ("places", "general_research"),
    "places": ("general_research",),
    "shopping": ("general_research",),
    "legal_research": ("general_research",),
}

GOAL_QUERY_MARKERS: tuple[str, ...] = (
    "alcam",
    "alacağım",
    "alacagim",
    "almak istiyorum",
    "ne alayım",
    "ne alayim",
    "öner",
    "oner",
    "önerir misin",
    "onerir misin",
    "bak",
    "bakar mısın",
    "bakar misin",
    "bul",
    "gideyim",
    "gidelim",
)

LOCAL_QUERY_MARKERS: tuple[str, ...] = (
    "yakındaki",
    "yakindaki",
    "yakınımdaki",
    "yakinimdaki",
    "yakınımda",
    "yakinimda",
    "yakın",
    "yakin",
    "en yakın",
    "en yakin",
    "near me",
    "yakında",
    "yakinda",
    "mağaza",
    "magaza",
    "butik",
    "avm",
    "alışveriş merkezi",
    "alisveris merkezi",
    "sinema",
    "seans",
    "rota",
    "yol tarifi",
    "harita",
)

_PROVIDER_STOPWORDS = {
    "su",
    "şu",
    "site",
    "siteler",
    "link",
    "linkten",
    "buradan",
    "oradan",
    "bundan",
    "siteden",
    "sitelerden",
    "yerden",
    "karar",
    "arama",
    "ararken",
    "bileti",
    "bilet",
    "alışveriş",
    "alisveris",
    "kıyafet",
    "kiyafet",
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _compact_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _normalize_domain(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    domain = str(parsed.netloc or parsed.path or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if "/" in domain:
        domain = domain.split("/", 1)[0]
    return domain


def _normalize_link(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if not parsed.netloc:
        return ""
    return parsed.geturl()


def _dedupe_texts(values: list[Any], *, normalizer=None, limit: int = 12) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalizer(value) if normalizer is not None else _compact_text(value)
        if not normalized:
            continue
        marker = normalized.lower()
        if marker in seen:
            continue
        seen.add(marker)
        items.append(normalized)
        if len(items) >= limit:
            break
    return items


def _extract_urls(text: str) -> list[str]:
    return _dedupe_texts(re.findall(r"https?://[^\s<>()]+", str(text or ""), flags=re.IGNORECASE), normalizer=_normalize_link, limit=8)


def _extract_domains(text: str) -> list[str]:
    matches = re.findall(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>()]*)?\b", str(text or ""), flags=re.IGNORECASE)
    domains = [_normalize_domain(item) for item in matches]
    return _dedupe_texts(domains, limit=8)


def _extract_provider_candidates(text: str) -> list[str]:
    raw_text = str(text or "")
    matches: list[str] = []
    patterns = (
        r"([a-zA-Z0-9çğıöşüÇĞİÖŞÜ&._-]{2,40})['’]?(?:den|dan)\s+(?:al|bak|ara|kullan|tercih et)",
        r"(?:önce|tercihen|özellikle|ozellikle)\s+([a-zA-Z0-9çğıöşüÇĞİÖŞÜ&._-]{2,40})",
        r"([a-zA-Z0-9çğıöşüÇĞİÖŞÜ&._-]{2,40})\s+(?:kullan|tercih et)",
    )
    for pattern in patterns:
        matches.extend(re.findall(pattern, raw_text, flags=re.IGNORECASE))
    providers = []
    for item in matches:
        candidate = _compact_text(item, limit=40).strip(" .,:;/-")
        if not candidate:
            continue
        if _normalize_text(candidate) in _PROVIDER_STOPWORDS:
            continue
        providers.append(candidate)
    return _dedupe_texts(providers, limit=6)


def infer_task_kinds(query: str) -> list[str]:
    normalized = _normalize_text(query)
    tags: set[str] = set()
    for task_kind, markers in TASK_KIND_MARKERS.items():
        if any(marker in normalized for marker in markers):
            tags.add(task_kind)
    if "clothing" in tags or "gift" in tags:
        tags.add("shopping")
    expanded = set(tags)
    for tag in list(tags):
        expanded.update(TASK_KIND_EXPANSIONS.get(tag, ()))
    return sorted(expanded)


def infer_primary_task_kind(query: str) -> str:
    normalized = _normalize_text(query)
    scored_matches: list[tuple[int, int, int, str]] = []
    for index, (task_kind, markers) in enumerate(TASK_KIND_MARKERS.items()):
        match_count = sum(1 for marker in markers if marker in normalized)
        if match_count <= 0:
            continue
        specificity_bonus = 0 if task_kind in {"general_research", "travel", "shopping", "places"} else 1
        scored_matches.append((match_count, specificity_bonus, -index, task_kind))
    if not scored_matches:
        return "general_research"
    scored_matches.sort(reverse=True)
    return scored_matches[0][3]


def query_suggests_local_results(query: str) -> bool:
    normalized = _normalize_text(query)
    return any(marker in normalized for marker in LOCAL_QUERY_MARKERS)


def is_goal_discovery_query(query: str) -> bool:
    normalized = _normalize_text(query)
    task_kinds = infer_task_kinds(normalized)
    if not task_kinds:
        return False
    explicit_search_markers = (
        "internette ara",
        "webde ara",
        "web'de ara",
        "araştır",
        "arastir",
    )
    has_specific_goal = any(task_kind != "general_research" for task_kind in task_kinds)
    return any(marker in normalized for marker in GOAL_QUERY_MARKERS) and (
        has_specific_goal or any(marker in normalized for marker in explicit_search_markers)
    )


def normalize_source_preference_rule(rule: dict[str, Any]) -> dict[str, Any]:
    task_kind = str(rule.get("task_kind") or "general_research").strip().lower() or "general_research"
    policy_mode = str(rule.get("policy_mode") or "prefer").strip().lower()
    if policy_mode not in {"prefer", "restrict"}:
        policy_mode = "prefer"
    preferred_links = _dedupe_texts(list(rule.get("preferred_links") or []), normalizer=_normalize_link, limit=8)
    preferred_domains = _dedupe_texts(
        list(rule.get("preferred_domains") or []) + [_normalize_domain(item) for item in preferred_links],
        normalizer=_normalize_domain,
        limit=12,
    )
    preferred_providers = _dedupe_texts(list(rule.get("preferred_providers") or []), limit=8)
    note = _compact_text(rule.get("note") or "", limit=280)
    label = _compact_text(rule.get("label") or TASK_KIND_LABELS.get(task_kind) or "Kaynak tercihi", limit=120)
    identifier = str(rule.get("id") or "").strip()
    if not identifier:
        digest_seed = "|".join([task_kind, policy_mode, ",".join(preferred_domains), ",".join(preferred_providers), ",".join(preferred_links)])
        identifier = f"srcpref-{hashlib.sha256(digest_seed.encode('utf-8')).hexdigest()[:10]}"
    return {
        "id": identifier,
        "label": label,
        "task_kind": task_kind,
        "policy_mode": policy_mode,
        "preferred_domains": preferred_domains,
        "preferred_links": preferred_links,
        "preferred_providers": preferred_providers,
        "note": note,
    }


def normalize_source_preference_rules(rules: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = [normalize_source_preference_rule(item) for item in list(rules or []) if isinstance(item, dict)]
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in normalized:
        marker = "|".join(
            [
                str(item.get("task_kind") or ""),
                str(item.get("policy_mode") or ""),
                ",".join(item.get("preferred_domains") or []),
                ",".join(item.get("preferred_providers") or []),
                ",".join(item.get("preferred_links") or []),
            ]
        )
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped[:24]


def summarize_source_preference_rule(rule: dict[str, Any]) -> str:
    task_label = TASK_KIND_LABELS.get(str(rule.get("task_kind") or "").strip().lower(), str(rule.get("task_kind") or "kaynak tercihi"))
    parts: list[str] = [task_label]
    providers = list(rule.get("preferred_providers") or [])
    domains = list(rule.get("preferred_domains") or [])
    links = list(rule.get("preferred_links") or [])
    if providers:
        parts.append(f"sağlayıcı: {', '.join(providers[:3])}")
    if domains:
        parts.append(f"alan adı: {', '.join(domains[:3])}")
    if links:
        parts.append(f"bağlantı: {', '.join(links[:2])}")
    if rule.get("policy_mode") == "restrict":
        parts.append("yalnız bu kaynaklarda ara")
    note = _compact_text(rule.get("note") or "", limit=120)
    if note:
        parts.append(note)
    return " | ".join(part for part in parts if part)


def summarize_source_preference_rules(rules: list[dict[str, Any]] | None, *, limit: int = 3) -> list[str]:
    return [summarize_source_preference_rule(item) for item in list(rules or [])[: max(0, limit)]]


def _task_match_score(rule_task_kind: str, inferred_task_kinds: list[str]) -> int:
    normalized_task = str(rule_task_kind or "").strip().lower()
    if normalized_task == "general_research":
        return 1
    if normalized_task in inferred_task_kinds:
        return 4
    for inferred in inferred_task_kinds:
        if normalized_task in TASK_KIND_EXPANSIONS.get(inferred, ()):
            return 2
    return 0


def resolve_source_preference_context(
    query: str,
    *,
    profile: dict[str, Any] | None = None,
    limit: int = 4,
) -> dict[str, Any]:
    normalized_rules = normalize_source_preference_rules(list((profile or {}).get("source_preference_rules") or []))
    inferred_task_kinds = infer_task_kinds(query)
    location_hint = str((profile or {}).get("current_location") or (profile or {}).get("home_base") or "").strip()
    goal_query = is_goal_discovery_query(query)
    localizable_task = any(item in inferred_task_kinds for item in ("cinema", "clothing", "gift", "shopping", "places", "dining"))
    needs_local_results = query_suggests_local_results(query) or (goal_query and localizable_task and bool(location_hint))
    matched_rules: list[dict[str, Any]] = []
    for rule in normalized_rules:
        score = _task_match_score(str(rule.get("task_kind") or ""), inferred_task_kinds)
        if score <= 0:
            continue
        matched_rules.append({**rule, "_match_score": score})
    matched_rules.sort(
        key=lambda item: (
            -int(item.get("_match_score") or 0),
            0 if str(item.get("policy_mode") or "") == "restrict" else 1,
            str(item.get("label") or ""),
        )
    )
    matched_rules = matched_rules[: max(0, limit)]
    preferred_domains = _dedupe_texts(
        [domain for item in matched_rules for domain in list(item.get("preferred_domains") or [])],
        normalizer=_normalize_domain,
        limit=12,
    )
    preferred_links = _dedupe_texts(
        [link for item in matched_rules for link in list(item.get("preferred_links") or [])],
        normalizer=_normalize_link,
        limit=8,
    )
    preferred_providers = _dedupe_texts(
        [provider for item in matched_rules for provider in list(item.get("preferred_providers") or [])],
        limit=8,
    )
    restricted_domains = _dedupe_texts(
        [
            domain
            for item in matched_rules
            if str(item.get("policy_mode") or "") == "restrict"
            for domain in list(item.get("preferred_domains") or [])
        ],
        normalizer=_normalize_domain,
        limit=12,
    )
    summary_lines = summarize_source_preference_rules(matched_rules, limit=min(limit, 3))
    explicit_general_search = any(
        marker in _normalize_text(query)
        for marker in ("internette ara", "webde ara", "web'de ara", "araştır", "arastir")
    )
    return {
        "task_kinds": inferred_task_kinds,
        "matched_rules": matched_rules,
        "preferred_domains": preferred_domains,
        "preferred_links": preferred_links,
        "preferred_providers": preferred_providers,
        "restricted_domains": restricted_domains,
        "location_hint": location_hint if needs_local_results else "",
        "needs_local_results": needs_local_results,
        "should_search": bool(inferred_task_kinds) and (
            needs_local_results
            or (goal_query and any(item != "general_research" for item in inferred_task_kinds))
            or explicit_general_search
        ),
        "summary_lines": summary_lines,
        "summary": " ; ".join(summary_lines),
        "prompt_lines": [f"- [kaynak tercihi] {line}" for line in summary_lines],
    }


def extract_source_preference_rules_from_text(
    text: str,
    *,
    existing_rules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    normalized = _normalize_text(text)
    has_instruction = any(
        phrase in normalized
        for phrase in (
            "şu sitelerden ara",
            "su sitelerden ara",
            "bu sitelerden ara",
            "hep buradan ara",
            "bundan sonra buradan ara",
            "şu linkten al",
            "su linkten al",
            "buradan al",
            "buradan bak",
            "tercih et",
            "kullan",
            "buraya bak",
            "site:",
        )
    ) or bool(re.search(r"[a-z0-9çğıöşüÇĞİÖŞÜ&._-]{2,40}['’]?(?:den|dan)\s+(?:al|bak|ara|kullan|tercih et)", str(text or ""), flags=re.IGNORECASE))
    if not has_instruction:
        return None
    task_kind = infer_primary_task_kind(text)
    preferred_links = _extract_urls(text)
    preferred_domains = _extract_domains(text)
    preferred_providers = _extract_provider_candidates(text)
    if not preferred_domains and preferred_links:
        preferred_domains = _dedupe_texts([_normalize_domain(item) for item in preferred_links], normalizer=_normalize_domain, limit=8)
    if not any((preferred_links, preferred_domains, preferred_providers)):
        return None
    policy_mode = "restrict" if any(
        phrase in normalized
        for phrase in (
            "şu sitelerden ara",
            "su sitelerden ara",
            "bu sitelerden ara",
            "yalnız bu sitelerden ara",
            "yalniz bu sitelerden ara",
            "sadece bu sitelerden ara",
            "hep buradan ara",
            "bundan sonra buradan ara",
            "sadece buradan al",
            "yalnız buradan al",
            "yalniz buradan al",
        )
    ) else "prefer"
    note = _compact_text(text, limit=220)
    rules = normalize_source_preference_rules(existing_rules)
    merged = False
    for index, item in enumerate(rules):
        if str(item.get("task_kind") or "") != task_kind or str(item.get("policy_mode") or "") != policy_mode:
            continue
        rules[index] = normalize_source_preference_rule(
            {
                **item,
                "preferred_domains": list(item.get("preferred_domains") or []) + preferred_domains,
                "preferred_links": list(item.get("preferred_links") or []) + preferred_links,
                "preferred_providers": list(item.get("preferred_providers") or []) + preferred_providers,
                "note": note if note and note != item.get("note") else item.get("note"),
            }
        )
        merged = True
        break
    if not merged:
        rules.append(
            normalize_source_preference_rule(
                {
                    "task_kind": task_kind,
                    "policy_mode": policy_mode,
                    "preferred_domains": preferred_domains,
                    "preferred_links": preferred_links,
                    "preferred_providers": preferred_providers,
                    "note": note,
                    "label": f"{TASK_KIND_LABELS.get(task_kind, 'Kaynak')} tercihi",
                }
            )
        )
    return normalize_source_preference_rules(rules)
