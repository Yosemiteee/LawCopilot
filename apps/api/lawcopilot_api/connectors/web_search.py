from __future__ import annotations

import html
import json
import os
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


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
    return any(token in normalized for token in triggers)


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


def is_travel_booking_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    return any(token in normalized for token in ("bilet al", "rezervasyon yap", "rezerve et", "satın al", "satin al"))


def build_web_search_context(query: str, *, limit: int = 5) -> dict[str, Any]:
    results = search_web(query, limit=limit)
    summary = (
        "Güncel web sonucu bulunamadı."
        if not results
        else "Güncel web sonuçlarını topladım. İstersen bunları daraltıp en güvenilir olanları öne çıkarayım."
    )
    return {
        "query": query,
        "results": results,
        "summary": summary,
    }


def build_travel_context(query: str, *, profile_note: str = "", limit: int = 5) -> dict[str, Any]:
    augmented_query = " ".join(part for part in [query, profile_note] if part).strip()
    results = search_web(augmented_query, limit=limit)
    booking_url = results[0]["url"] if results else (
        f"https://www.google.com/travel/flights?q={quote_plus(augmented_query)}" if augmented_query else ""
    )
    return {
        "query": query,
        "search_query": augmented_query,
        "results": results,
        "booking_url": booking_url,
        "summary": (
            "İlk seçenekleri topladım. İstersen onayından sonra rezervasyon sayfasını açayım."
            if booking_url
            else "Uygun seyahat sonucu bulamadım; tarih, rota ve bütçeyi netleştirirsen yeniden bakabilirim."
        ),
    }
