from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

try:
    from selectolax.parser import HTMLParser  # type: ignore
except Exception:  # noqa: BLE001
    HTMLParser = None

try:
    import trafilatura  # type: ignore
except Exception:  # noqa: BLE001
    trafilatura = None

try:
    from readability import Document as ReadabilityDocument  # type: ignore
except Exception:  # noqa: BLE001
    ReadabilityDocument = None


USER_AGENT = "LawCopilot/0.7 (+https://lawcopilot.local)"
SOCIAL_LINK_RE = re.compile(
    r"https?://(?:www\.)?(?:x\.com|twitter\.com|linkedin\.com|instagram\.com|facebook\.com|youtube\.com|github\.com)/[^\s\"'<>]+",
    re.IGNORECASE,
)


def _normalize_space(value: str, *, limit: int | None = None) -> str:
    cleaned = " ".join(str(value or "").split()).strip()
    if limit and len(cleaned) > limit:
        trimmed = cleaned[: max(0, limit - 1)].rstrip()
        cut = trimmed.rfind(" ")
        if cut > int(limit * 0.55):
            trimmed = trimmed[:cut]
        return trimmed.rstrip() + "…"
    return cleaned


def _domain_allowed(url: str, allowed_domains: tuple[str, ...]) -> bool:
    if not allowed_domains:
        return True
    domain = str(urlparse(url).hostname or "").lower()
    if not domain:
        return False
    return any(domain == item or domain.endswith(f".{item}") for item in allowed_domains)


def _fallback_extract_html(html_text: str) -> tuple[str, list[str], str, list[str]]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    title = _normalize_space(re.sub(r"<[^>]+>", " ", title_match.group(1) if title_match else ""), limit=220)
    meta_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    meta_description = _normalize_space(meta_match.group(1) if meta_match else "", limit=320)
    heading_matches = re.findall(r"<h[12][^>]*>(.*?)</h[12]>", html_text, flags=re.IGNORECASE | re.DOTALL)
    headings = [_normalize_space(re.sub(r"<[^>]+>", " ", value), limit=180) for value in heading_matches]
    cleaned_body = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html_text)
    visible_text = _normalize_space(re.sub(r"<[^>]+>", " ", cleaned_body), limit=12000)
    social_links = []
    for match in SOCIAL_LINK_RE.findall(html_text):
        if match not in social_links:
            social_links.append(match)
    return title, headings[:8], visible_text, social_links[:12]


def _extract_with_selectolax(html_text: str) -> tuple[str, list[str], str, list[str]]:
    if HTMLParser is None:
        return _fallback_extract_html(html_text)
    tree = HTMLParser(html_text)
    title_node = tree.css_first("title")
    title = _normalize_space(title_node.text() if title_node else "", limit=220)
    headings = []
    for selector in ("h1", "h2"):
        for node in tree.css(selector):
            value = _normalize_space(node.text(), limit=180)
            if value and value not in headings:
                headings.append(value)
    visible_text = _normalize_space(tree.body.text(separator=" ", strip=True) if tree.body else tree.text(separator=" ", strip=True), limit=12000)
    social_links = []
    for node in tree.css("a"):
        href = str(node.attributes.get("href") or "").strip()
        if href.startswith("http") and SOCIAL_LINK_RE.match(href) and href not in social_links:
            social_links.append(href)
    return title, headings[:8], visible_text, social_links[:12]


def _extract_main_text(url: str, html_text: str) -> str:
    if trafilatura is not None:
        try:
            extracted = trafilatura.extract(html_text, url=url, include_comments=False, include_tables=True)
        except Exception:  # noqa: BLE001
            extracted = None
        if extracted:
            return _normalize_space(extracted, limit=12000)
    if ReadabilityDocument is not None:
        try:
            summary_html = ReadabilityDocument(html_text).summary()
        except Exception:  # noqa: BLE001
            summary_html = ""
        if summary_html:
            return _extract_with_selectolax(summary_html)[2]
    return _extract_with_selectolax(html_text)[2]


def extract_web_intelligence(
    *,
    url: str,
    strategy: str = "auto",
    browser_client: Any | None = None,
    allowed_domains: tuple[str, ...] = (),
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    cleaned_url = str(url or "").strip()
    if not cleaned_url:
        return {"ok": False, "url": "", "error": "missing_url", "issues": ["URL eksik."]}
    if not _domain_allowed(cleaned_url, allowed_domains):
        return {"ok": False, "url": cleaned_url, "error": "domain_not_allowed", "issues": ["Hedef alan adı izinli değil."]}

    requested_strategy = str(strategy or "auto").strip().lower() or "auto"
    used_browser = False
    browser_payload: dict[str, Any] | None = None

    if requested_strategy == "browser" and browser_client is not None:
        browser_payload = browser_client.extract(url=cleaned_url, strategy="browser")
        used_browser = bool(browser_payload and browser_payload.get("ok"))

    request_headers = {"User-Agent": USER_AGENT}
    try:
        response = httpx.get(cleaned_url, headers=request_headers, timeout=max(5, int(timeout_seconds or 15)), follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {"ok": False, "url": cleaned_url, "error": f"fetch_failed:{exc}", "issues": [f"Erişim hatası: {exc}"]}

    html_text = response.text or ""
    title, headings, fallback_visible_text, social_links = _extract_with_selectolax(html_text)
    extracted_text = _extract_main_text(str(response.url), html_text)
    content_type = str(response.headers.get("Content-Type") or "")

    if requested_strategy in {"auto", "browser"} and browser_client is not None and not used_browser:
        looks_dynamic = ("__next" in html_text or "data-reactroot" in html_text or "id=\"app\"" in html_text or "application/json" in content_type.lower())
        if looks_dynamic:
            browser_payload = browser_client.extract(url=str(response.url), strategy="browser")
            used_browser = bool(browser_payload and browser_payload.get("ok"))

    combined_excerpt = _normalize_space(browser_payload.get("text") if browser_payload else extracted_text or fallback_visible_text, limit=1400)
    issues: list[str] = []
    if not title:
        issues.append("Sayfa başlığı zayıf veya boş.")
    if len(combined_excerpt) < 180:
        issues.append("Çıkarılabilen görünür metin sınırlı.")

    return {
        "ok": True,
        "url": cleaned_url,
        "resolved_url": str(response.url),
        "strategy": requested_strategy,
        "used_browser": used_browser,
        "title": title,
        "headings": headings,
        "content_type": content_type,
        "excerpt": combined_excerpt,
        "text": browser_payload.get("text") if browser_payload else extracted_text or fallback_visible_text,
        "social_links": social_links,
        "contact_hints": [
            hint
            for hint, present in (
                ("e-posta", "mailto:" in html_text.lower()),
                ("telefon", "tel:" in html_text.lower()),
            )
            if present
        ],
        "artifacts": list(browser_payload.get("artifacts") or []) if browser_payload else [],
        "issues": issues,
        "engine": "browser-worker" if used_browser else "httpx+extract",
    }
