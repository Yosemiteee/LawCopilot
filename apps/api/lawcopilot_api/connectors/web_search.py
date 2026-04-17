from __future__ import annotations

import html
import json
import os
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from ..preference_rules import is_goal_discovery_query, query_suggests_local_results


_USER_AGENT = "LawCopilot/0.7 (+https://lawcopilot.local)"


def _read_json(request: Request) -> dict[str, Any]:
    with urlopen(request, timeout=15) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    return json.loads(raw or "{}")


def _read_text(request: Request) -> str:
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", errors="ignore")


def _tavily_search(query: str, *, limit: int) -> list[dict[str, str]]:
    api_key = str(os.getenv("TAVILY_API_KEY") or "").strip()
    if not api_key:
        return []
    payload = json.dumps(
        {
            "api_key": api_key,
            "query": query,
            "max_results": max(1, min(limit, 10)),
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
        }
    ).encode("utf-8")
    request = Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        },
        method="POST",
    )
    body = _read_json(request)
    items: list[dict[str, str]] = []
    for result in body.get("results") or []:
        if not isinstance(result, dict):
            continue
        url = str(result.get("url") or "").strip()
        title = str(result.get("title") or url or "Sonuç").strip()
        if not url:
            continue
        items.append(
            {
                "title": title,
                "url": url,
                "snippet": str(result.get("content") or "").strip(),
                "source": "tavily",
            }
        )
    return items


def _duckduckgo_search(query: str, *, limit: int) -> list[dict[str, str]]:
    request = Request(
        f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
        headers={"User-Agent": _USER_AGENT},
    )
    html_text = _read_text(request)
    pattern = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
    items: list[dict[str, str]] = []
    for match in pattern.finditer(html_text):
        href = html.unescape(match.group(1))
        parsed = urlparse(href)
        target = href
        if "duckduckgo.com" in parsed.netloc:
            uddg = parse_qs(parsed.query).get("uddg")
            if uddg:
                target = unquote(uddg[0])
        title = re.sub(r"<[^>]+>", " ", html.unescape(match.group(2)))
        title = " ".join(title.split())
        if not target or not title:
            continue
        items.append(
            {
                "title": title,
                "url": target,
                "snippet": "",
                "source": "duckduckgo",
            }
        )
        if len(items) >= limit:
            break
    return items


def search_web(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    cleaned = " ".join(str(query or "").split()).strip()
    if not cleaned:
        return []
    try:
        results = _tavily_search(cleaned, limit=limit)
        if results:
            return results[:limit]
    except Exception:
        pass
    try:
        return _duckduckgo_search(cleaned, limit=limit)[:limit]
    except Exception:
        return []


def _domain_from_url(url: str) -> str:
    host = str(urlparse(str(url or "")).netloc or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _matches_domain(url: str, domains: list[str]) -> bool:
    current = _domain_from_url(url)
    if not current:
        return False
    for item in domains:
        candidate = str(item or "").strip().lower()
        if not candidate:
            continue
        if current == candidate or current.endswith(f".{candidate}"):
            return True
    return False


def _dedupe_results(items: list[dict[str, str]], *, limit: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or "").strip()
        marker = url or "|".join(
            [
                str(item.get("title") or ""),
                str(item.get("snippet") or ""),
                str(item.get("source") or ""),
            ]
        )
        if not marker or marker in seen:
            continue
        seen.add(marker)
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _preferred_link_results(preferred_links: list[str], *, limit: int) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for link in preferred_links[: max(0, limit)]:
        domain = _domain_from_url(link)
        items.append(
            {
                "title": f"Tercih edilen bağlantı: {domain or link}",
                "url": link,
                "snippet": "Daha önce kaydettiğin sabit bağlantı.",
                "source": "user_preference",
            }
        )
    return items


def _search_with_preferences(
    query: str,
    *,
    limit: int,
    search_preferences: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    preferences = dict(search_preferences or {})
    preferred_domains = [str(item).strip().lower() for item in list(preferences.get("preferred_domains") or []) if str(item).strip()]
    restricted_domains = [str(item).strip().lower() for item in list(preferences.get("restricted_domains") or []) if str(item).strip()]
    preferred_links = [str(item).strip() for item in list(preferences.get("preferred_links") or []) if str(item).strip()]
    preferred_providers = [str(item).strip() for item in list(preferences.get("preferred_providers") or []) if str(item).strip()]

    candidate_queries: list[str] = []
    for domain in (restricted_domains or preferred_domains)[:3]:
        candidate_queries.append(f"site:{domain} {query}".strip())
    for provider in preferred_providers[:2]:
        candidate_queries.append(f"{query} {provider}".strip())
    candidate_queries.append(query)

    merged: list[dict[str, str]] = []
    per_query_limit = max(limit, 4)
    seen_queries: set[str] = set()
    for candidate in candidate_queries:
        compact = " ".join(str(candidate or "").split()).strip()
        if not compact or compact in seen_queries:
            continue
        seen_queries.add(compact)
        merged.extend(search_web(compact, limit=per_query_limit))

    if restricted_domains:
        merged = [item for item in merged if _matches_domain(str(item.get("url") or ""), restricted_domains)]

    merged.sort(
        key=lambda item: (
            0 if str(item.get("url") or "").strip() in preferred_links else 1,
            0 if _matches_domain(str(item.get("url") or ""), preferred_domains) else 1,
            0 if _matches_domain(str(item.get("url") or ""), restricted_domains) else 1,
            str(item.get("title") or ""),
        )
    )
    pinned = _preferred_link_results(preferred_links, limit=min(3, limit))
    return _dedupe_results([*pinned, *merged], limit=limit)


def _is_youtube_url(url: str) -> bool:
    host = str(urlparse(str(url or "")).netloc or "").lower()
    return bool(host.endswith("youtube.com") or host.endswith("youtu.be") or host == "youtube.com" or host == "youtu.be")


def extract_youtube_url(query: str) -> str | None:
    candidate = extract_query_url(query)
    if candidate and _is_youtube_url(candidate):
        return candidate
    return None


def search_youtube(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    cleaned = " ".join(str(query or "").split()).strip()
    if not cleaned:
        return []
    raw_results = search_web(f"site:youtube.com {cleaned}", limit=max(limit * 2, 6))
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_results:
        url = str(item.get("url") or "").strip()
        if not url or not _is_youtube_url(url) or url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "title": str(item.get("title") or "YouTube sonucu").strip(),
                "url": url,
                "snippet": str(item.get("snippet") or "").strip(),
                "source": str(item.get("source") or "web"),
            }
        )
        if len(items) >= limit:
            break
    return items


def is_web_search_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    triggers = (
        "internette ara",
        "webde ara",
        "web'de ara",
        "araştır",
        "güncel bilgi",
        "son haber",
        "bulur musun",
        "bakar mısın",
    )
    if any(token in normalized for token in triggers):
        return True
    return is_goal_discovery_query(normalized)


def is_youtube_search_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    triggers = (
        "youtube'da ara",
        "youtubeda ara",
        "youtube da ara",
        "youtube ara",
        "youtube videosu bul",
        "videoyu youtube'da bul",
        "youtubeden bul",
        "youtube'dan bul",
    )
    if any(token in normalized for token in triggers):
        return True
    if "youtube" in normalized and any(token in normalized for token in (" ara", " bul", "video", "kanal")):
        return True
    return False


def is_video_summary_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    summary_markers = (
        "özetle",
        "ozetle",
        "özet çıkar",
        "ozet cikar",
        "bu video ne anlatıyor",
        "videoyu anlat",
        "videoyu çöz",
        "videoyu cozumle",
        "transkript",
    )
    return bool(extract_youtube_url(query)) and any(token in normalized for token in summary_markers)


def is_website_crawl_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    crawl_markers = (
        "siteyi tara",
        "sayfayi tara",
        "sayfayı tara",
        "site taraması",
        "site taramasi",
        "tüm siteyi tara",
        "tum siteyi tara",
        "alt sayfalari tara",
        "alt sayfaları tara",
        "crawl",
        "derinlemesine incele",
        "siteyi gez",
    )
    return bool(extract_query_url(query)) and any(token in normalized for token in crawl_markers)


def is_travel_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    triggers = (
        "bilet",
        "uçuş",
        "ucus",
        "otel",
        "seyahat",
        "rota",
        "tren",
        "otobüs",
        "otobus",
        "rezervasyon",
    )
    return any(token in normalized for token in triggers)


def is_weather_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    triggers = (
        "hava durumu",
        "weather",
        "forecast",
        "kac derece",
        "kaç derece",
        "sicaklik",
        "sıcaklık",
        "hava nasil",
        "hava nasıl",
        "gunesli mi",
        "güneşli mi",
        "yagmur",
        "yağmur",
        "ruzgar",
        "rüzgar",
    )
    return any(token in normalized for token in triggers)


def is_place_search_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    triggers = (
        "yakındaki",
        "yakindaki",
        "yakınımdaki",
        "yakinimdaki",
        "yakınımda",
        "yakinimda",
        "en yakin",
        "en yakın",
        "yakında ",
        "yakinda ",
        "near me",
        "restaurant",
        "restoran",
        "lokanta",
        "kafe",
        "cafe",
        "kahveci",
        "mekan",
        "mekân",
        "cami",
        "mosque",
        "eczane",
        "pharmacy",
        "park",
        "müze",
        "muze",
        "yol tarifi",
        "nasil giderim",
        "nasıl giderim",
        "maps",
        "harita",
    )
    if any(token in normalized for token in triggers):
        return True
    local_goal_nouns = (
        "sinema",
        "mağaza",
        "magaza",
        "butik",
        "avm",
        "alışveriş merkezi",
        "alisveris merkezi",
    )
    return any(token in normalized for token in local_goal_nouns) and (
        query_suggests_local_results(normalized) or is_goal_discovery_query(normalized)
    )


def is_travel_booking_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    return any(token in normalized for token in ("bilet al", "rezervasyon yap", "rezerve et", "satın al", "satin al"))


def build_web_search_context(query: str, *, limit: int = 5, search_preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    results = _search_with_preferences(query, limit=limit, search_preferences=search_preferences)
    preference_summary = str((search_preferences or {}).get("summary") or "").strip()
    summary = (
        "Güncel web sonucu bulunamadı."
        if not results
        else "Güncel web sonuçlarını topladım. İstersen bunları daraltıp en güvenilir olanları öne çıkarayım."
    )
    if preference_summary:
        summary = f"{preference_summary}. {summary}"
    return {
        "query": query,
        "results": results,
        "summary": summary,
        "search_preferences": dict(search_preferences or {}),
    }


def build_youtube_search_context(query: str, *, limit: int = 5) -> dict[str, Any]:
    results = search_youtube(query, limit=limit)
    summary = (
        "YouTube'da uygun video bulunamadı."
        if not results
        else "YouTube'da ilgili videoları topladım. İstersen bunlardan birinin linkiyle içeriğini özetleyeyim."
    )
    return {
        "query": query,
        "results": results,
        "summary": summary,
    }


def build_travel_context(
    query: str,
    *,
    profile_note: str = "",
    limit: int = 5,
    search_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    preference_hint = str((search_preferences or {}).get("location_hint") or "").strip()
    augmented_query = " ".join(part for part in [query, preference_hint, profile_note] if part).strip()
    results = _search_with_preferences(augmented_query, limit=limit, search_preferences=search_preferences)
    preferred_links = list((search_preferences or {}).get("preferred_links") or [])
    booking_url = results[0]["url"] if results else (
        f"https://www.google.com/travel/flights?q={quote_plus(augmented_query)}" if augmented_query else ""
    )
    if preferred_links:
        booking_url = str(preferred_links[0] or booking_url).strip() or booking_url
    preference_summary = str((search_preferences or {}).get("summary") or "").strip()
    success_summary = "İlk seçenekleri topladım. İstersen onayından sonra LawCopilot içinde güvenli ödeme penceresini açayım."
    failure_summary = "Uygun seyahat sonucu bulamadım; tarih, rota ve bütçeyi netleştirirsen yeniden bakabilirim."
    if preference_summary:
        success_summary = f"{preference_summary}. {success_summary}"
        failure_summary = f"{preference_summary}. {failure_summary}"
    return {
        "query": query,
        "search_query": augmented_query,
        "results": results,
        "booking_url": booking_url,
        "summary": success_summary if booking_url else failure_summary,
        "search_preferences": dict(search_preferences or {}),
    }


def build_weather_context(query: str, *, profile_note: str = "", limit: int = 5) -> dict[str, Any]:
    base_query = " ".join(str(query or "").split()).strip()
    if not base_query:
        return {
            "query": "",
            "search_query": "",
            "results": [],
            "summary": "Hava durumu için konum veya sorgu eksik.",
        }
    augmented_query = " ".join(part for part in [base_query, profile_note] if part).strip()
    search_query = augmented_query if is_weather_query(augmented_query) else f"{augmented_query} hava durumu"
    results = search_web(search_query, limit=limit)
    return {
        "query": base_query,
        "search_query": search_query,
        "results": results,
        "summary": (
            "Hava durumu için ilk güncel sonuçları topladım."
            if results
            else "Şu an güvenilir hava durumu sonucu toplayamadım; konumu biraz daha netleştirirsen yeniden bakabilirim."
        ),
    }


def build_places_context(
    query: str,
    *,
    profile_note: str = "",
    transport_note: str = "",
    limit: int = 5,
    search_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_query = " ".join(str(query or "").split()).strip()
    if not base_query:
        return {
            "query": "",
            "search_query": "",
            "results": [],
            "map_url": "",
            "summary": "Mekân veya rota araması için sorgu eksik.",
        }
    preference_hint = str((search_preferences or {}).get("location_hint") or "").strip()
    augmented_query = " ".join(part for part in [base_query, preference_hint, profile_note, transport_note] if part).strip()
    results = _search_with_preferences(augmented_query, limit=limit, search_preferences=search_preferences)
    map_target = base_query or augmented_query
    map_url = (
        f"https://www.google.com/maps/search/?api=1&query={quote_plus(map_target)}"
        if map_target
        else ""
    )
    preference_summary = str((search_preferences or {}).get("summary") or "").strip()
    success_summary = "Yakın çevre ve rota için ilk seçenekleri topladım."
    failure_summary = "Şu an güçlü mekân sonucu çıkaramadım; semt, ihtiyaç veya bütçeyi netleştirirsen yeniden bakabilirim."
    if preference_summary:
        success_summary = f"{preference_summary}. {success_summary}"
        failure_summary = f"{preference_summary}. {failure_summary}"
    return {
        "query": base_query,
        "search_query": augmented_query,
        "results": results,
        "map_url": map_url,
        "summary": success_summary if results else failure_summary,
        "search_preferences": dict(search_preferences or {}),
    }


def extract_query_url(query: str) -> str | None:
    raw = str(query or "").strip()
    direct = re.search(r"https?://[^\s<>()]+", raw, flags=re.IGNORECASE)
    if direct:
        return direct.group(0).rstrip(".,)")
    domain = re.search(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>()]*)?\b", raw, flags=re.IGNORECASE)
    if domain and "@" not in domain.group(0):
        return f"https://{domain.group(0).rstrip('.,)')}"
    return None


def is_website_review_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    triggers = (
        "web sitem",
        "web sayfam",
        "siteyi incele",
        "siteyi yorumla",
        "sayfayi incele",
        "sayfayı incele",
        "siteye bak",
        "analiz et",
        "bakar misin",
        "bakar mısın",
        "incele",
    )
    return bool(extract_query_url(query)) and any(token in normalized for token in triggers)


def build_website_inspection_context(url: str) -> dict[str, Any]:
    cleaned = str(url or "").strip()
    if not cleaned:
        return {"url": "", "reachable": False, "summary": "İncelenecek URL bulunamadı.", "issues": ["URL eksik."]}
    request = Request(cleaned, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(request, timeout=15) as response:
            raw_bytes = response.read(120_000)
            content_type = str(response.headers.get("Content-Type") or "")
    except Exception as exc:
        return {
            "url": cleaned,
            "reachable": False,
            "summary": "Sayfa şu anda okunamadı.",
            "issues": [f"Erişim hatası: {exc}"],
        }

    html_text = raw_bytes.decode("utf-8", errors="ignore")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    title = " ".join(re.sub(r"<[^>]+>", " ", html.unescape(title_match.group(1) if title_match else "")).split())
    meta_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    meta_description = " ".join(html.unescape(meta_match.group(1) if meta_match else "").split())
    heading_matches = re.findall(r"<h[12][^>]*>(.*?)</h[12]>", html_text, flags=re.IGNORECASE | re.DOTALL)
    headings = [
        " ".join(re.sub(r"<[^>]+>", " ", html.unescape(value)).split())
        for value in heading_matches
        if " ".join(re.sub(r"<[^>]+>", " ", html.unescape(value)).split())
    ][:6]
    social_links = re.findall(
        r"https?://(?:www\.)?(?:x\.com|twitter\.com|instagram\.com|linkedin\.com|facebook\.com)/[^\s\"'<>]+",
        html_text,
        flags=re.IGNORECASE,
    )
    contact_hints: list[str] = []
    if "mailto:" in html_text.lower():
        contact_hints.append("e-posta")
    if "tel:" in html_text.lower():
        contact_hints.append("telefon")
    cleaned_body = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html_text)
    visible_text = re.sub(r"<[^>]+>", " ", cleaned_body)
    visible_text = " ".join(html.unescape(visible_text).split())
    excerpt = visible_text[:420].strip()
    issues: list[str] = []
    if not title:
        issues.append("Sayfada belirgin bir başlık bulunamadı.")
    if not meta_description:
        issues.append("Meta açıklama eksik veya okunamadı.")
    if not headings:
        issues.append("Sayfada net başlık hiyerarşisi görünmüyor.")
    if len(excerpt) < 120:
        issues.append("Sayfa metni kısa; içerik az veya JS ağırlıklı olabilir.")
    if not contact_hints:
        issues.append("İletişim bağlantısı görünmedi.")
    summary_parts: list[str] = []
    if title:
        summary_parts.append(f"Başlık: {title}.")
    if meta_description:
        summary_parts.append(meta_description)
    elif excerpt:
        summary_parts.append(excerpt[:220] + ("…" if len(excerpt) > 220 else ""))
    if social_links:
        summary_parts.append(f"Sayfada {len(social_links)} sosyal bağlantı görünüyor.")
    return {
        "url": cleaned,
        "reachable": True,
        "content_type": content_type,
        "title": title,
        "meta_description": meta_description,
        "headings": headings,
        "social_links": social_links[:8],
        "contact_hints": contact_hints,
        "excerpt": excerpt,
        "issues": issues,
        "summary": " ".join(part for part in summary_parts if part) or "Sayfayı okudum; temel içerik çıkarıldı.",
    }
