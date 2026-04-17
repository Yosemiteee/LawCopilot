from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import html
import ipaddress
import re
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_USER_AGENT = "LawCopilot/0.7 (+https://lawcopilot.local)"


def _clean_text(value: str, *, limit: int | None = None) -> str:
    text = " ".join(str(value or "").split())
    if limit is not None and len(text) > limit:
        return text[: max(1, limit - 1)].rstrip() + "…"
    return text


class _HTMLSignalsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta_description = ""
        self.headings: list[str] = []
        self.links: list[str] = []
        self.visible_parts: list[str] = []
        self._in_title = False
        self._capture_heading = False
        self._heading_parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): str(value or "") for key, value in attrs}
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if lowered == "title":
            self._in_title = True
            return
        if lowered in {"h1", "h2"}:
            self._capture_heading = True
            self._heading_parts = []
            return
        if lowered == "meta" and attr_map.get("name", "").lower() == "description" and not self.meta_description:
            self.meta_description = _clean_text(html.unescape(attr_map.get("content", "")), limit=280)
            return
        if lowered == "a":
            href = attr_map.get("href", "").strip()
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
            return
        if lowered == "title":
            self._in_title = False
            return
        if lowered in {"h1", "h2"} and self._capture_heading:
            heading = _clean_text(" ".join(self._heading_parts), limit=180)
            if heading:
                self.headings.append(heading)
            self._capture_heading = False
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        cleaned = _clean_text(html.unescape(data))
        if not cleaned:
            return
        if self._in_title:
            self.title_parts.append(cleaned)
            return
        if self._capture_heading:
            self._heading_parts.append(cleaned)
        self.visible_parts.append(cleaned)


def _likely_spa(html_text: str, visible_text: str) -> bool:
    lower = html_text.lower()
    if "__next" in lower or "data-reactroot" in lower or "id=\"app\"" in lower or "id='app'" in lower:
        return True
    if visible_text and len(visible_text) >= 500:
        return False
    script_count = lower.count("<script")
    body_count = len(re.findall(r"<(?:p|li|article|section|main|h1|h2|h3)\b", lower))
    return script_count >= 8 and body_count <= 4


def _build_summary(*, title: str, headings: list[str], contact_hints: list[str], social_links: list[str], render_mode: str, likely_spa: bool) -> str:
    parts: list[str] = []
    if title:
        parts.append(f"Başlık: {title}.")
    if headings:
        parts.append(f"Ana başlıklar: {', '.join(headings[:4])}.")
    if contact_hints:
        parts.append(f"İletişim ipuçları: {', '.join(contact_hints)}.")
    if social_links:
        parts.append(f"Sosyal bağlantılar bulundu: {len(social_links)} adet.")
    if likely_spa and render_mode != "browser":
        parts.append("Sayfa büyük olasılıkla JS ağırlıklı; tarayıcı render modu daha iyi sonuç verebilir.")
    return " ".join(parts).strip() or "Sayfa içeriği çıkarıldı."


def _same_domain(url: str, candidate: str) -> bool:
    left = str(urlparse(str(url or "")).hostname or "").lower()
    right = str(urlparse(str(candidate or "")).hostname or "").lower()
    return bool(left and right and left == right)


def _clean_link(url: str, candidate: str) -> str:
    raw = str(candidate or "").strip()
    if not raw or raw.startswith("#") or raw.startswith("mailto:") or raw.startswith("tel:") or raw.startswith("javascript:"):
        return ""
    absolute = urljoin(url, raw)
    parsed = urlparse(absolute)
    if str(parsed.scheme or "").lower() not in {"http", "https"}:
        return ""
    return parsed._replace(fragment="").geturl()


def _score_for_query(query: str, page: dict[str, Any]) -> int:
    tokens = [item for item in re.findall(r"[a-zA-Z0-9çğıöşüÇĞİÖŞÜ]{3,}", str(query or "").lower()) if item]
    if not tokens:
        return 0
    haystack = " ".join(
        [
            str(page.get("title") or ""),
            str(page.get("meta_description") or ""),
            " ".join(str(item) for item in list(page.get("headings") or [])[:8]),
            str(page.get("visible_text") or ""),
            str(page.get("summary") or ""),
        ]
    ).lower()
    return sum(haystack.count(token) for token in tokens)


def _validate_web_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    scheme = str(parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError("unsupported_scheme")
    if not parsed.netloc:
        raise ValueError("missing_host")
    hostname = str(parsed.hostname or "").strip().lower()
    if not hostname:
        raise ValueError("missing_host")
    if hostname in {"localhost"} or hostname.endswith(".local"):
        raise ValueError("private_host_blocked")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
    ):
        raise ValueError("private_host_blocked")
    return parsed.geturl()


def _cheap_extract(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            raw_bytes = response.read(250_000)
            final_url = str(getattr(response, "url", url) or url)
            content_type = str(response.headers.get("Content-Type") or "")
    except HTTPError as exc:
        return {
            "url": url,
            "final_url": url,
            "reachable": False,
            "render_mode": "cheap",
            "content_type": "",
            "title": "",
            "meta_description": "",
            "headings": [],
            "visible_text": "",
            "links": [],
            "social_links": [],
            "contact_hints": [],
            "likely_spa": False,
            "issues": [f"http_error:{exc.code}"],
            "artifacts": [],
            "summary": f"Sayfa okunamadı (HTTP {exc.code}).",
        }
    except (URLError, TimeoutError, ValueError) as exc:
        return {
            "url": url,
            "final_url": url,
            "reachable": False,
            "render_mode": "cheap",
            "content_type": "",
            "title": "",
            "meta_description": "",
            "headings": [],
            "visible_text": "",
            "links": [],
            "social_links": [],
            "contact_hints": [],
            "likely_spa": False,
            "issues": [f"transport_error:{exc}"],
            "artifacts": [],
            "summary": "Sayfaya erişilemedi.",
        }

    html_text = raw_bytes.decode("utf-8", errors="ignore")
    parser = _HTMLSignalsParser()
    parser.feed(html_text)
    visible_text = _clean_text(" ".join(parser.visible_parts), limit=5000)
    normalized_links = [urljoin(final_url, item) for item in parser.links[:120]]
    social_links = [
        link for link in normalized_links
        if any(host in (urlparse(link).netloc or "").lower() for host in ("x.com", "twitter.com", "linkedin.com", "instagram.com", "facebook.com", "youtube.com"))
    ][:10]
    contact_hints: list[str] = []
    if "mailto:" in html_text.lower():
        contact_hints.append("e-posta")
    if "tel:" in html_text.lower():
        contact_hints.append("telefon")
    if re.search(r"\b(iletisim|contact|bize ulasin|ulaşın)\b", html_text, re.IGNORECASE):
        contact_hints.append("iletişim sayfası")
    deduped_contact_hints = list(dict.fromkeys(contact_hints))
    title = _clean_text(" ".join(parser.title_parts), limit=180)
    headings = list(dict.fromkeys(parser.headings))[:8]
    likely_spa = _likely_spa(html_text, visible_text)
    return {
        "url": url,
        "final_url": final_url,
        "reachable": True,
        "render_mode": "cheap",
        "content_type": content_type,
        "title": title,
        "meta_description": parser.meta_description,
        "headings": headings,
        "visible_text": visible_text,
        "links": normalized_links[:40],
        "social_links": social_links,
        "contact_hints": deduped_contact_hints,
        "likely_spa": likely_spa,
        "issues": [],
        "artifacts": [],
        "summary": _build_summary(
            title=title,
            headings=headings,
            contact_hints=deduped_contact_hints,
            social_links=social_links,
            render_mode="cheap",
            likely_spa=likely_spa,
        ),
    }


@dataclass
class WebIntelService:
    browser_client: Any | None = None

    def extract(self, *, url: str, render_mode: str = "auto", include_screenshot: bool = True) -> dict[str, Any]:
        cleaned = str(url or "").strip()
        if not cleaned:
            return {"url": "", "reachable": False, "summary": "İncelenecek URL bulunamadı.", "issues": ["URL eksik."], "artifacts": []}
        try:
            normalized_url = _validate_web_url(cleaned)
        except ValueError as exc:
            reason = str(exc or "invalid_url")
            return {
                "url": cleaned,
                "reachable": False,
                "summary": "Yalnızca http veya https ile başlayan geçerli web adresleri incelenebilir.",
                "issues": [reason],
                "artifacts": [],
            }
        cheap = _cheap_extract(normalized_url)
        if render_mode == "cheap" or not self.browser_client:
            return cheap
        if render_mode == "browser" or cheap.get("likely_spa"):
            browser_result = self.browser_client.extract(
                normalized_url,
                include_screenshot=include_screenshot,
                preferred_mode="browser",
            )
            if browser_result.get("ok"):
                payload = dict(browser_result.get("payload") or {})
                payload.setdefault("url", normalized_url)
                payload.setdefault("render_mode", "browser")
                payload.setdefault("likely_spa", bool(cheap.get("likely_spa")))
                payload.setdefault("issues", [])
                payload.setdefault("artifacts", [])
                if not payload.get("summary"):
                    payload["summary"] = _build_summary(
                        title=str(payload.get("title") or cheap.get("title") or ""),
                        headings=list(payload.get("headings") or []),
                        contact_hints=list(payload.get("contact_hints") or []),
                        social_links=list(payload.get("social_links") or []),
                        render_mode="browser",
                        likely_spa=bool(payload.get("likely_spa")),
                    )
                return payload
            cheap["issues"] = list(cheap.get("issues") or []) + [str(browser_result.get("error") or "browser_extract_failed")]
        return cheap

    def crawl(
        self,
        *,
        url: str,
        query: str = "",
        max_pages: int = 4,
        render_mode: str = "cheap",
        include_screenshot: bool = False,
    ) -> dict[str, Any]:
        root = self.extract(url=url, render_mode=render_mode, include_screenshot=include_screenshot)
        if not bool(root.get("reachable")):
            return {
                "url": str(url or "").strip(),
                "reachable": False,
                "summary": str(root.get("summary") or "Site taraması başlatılamadı."),
                "issues": list(root.get("issues") or []),
                "pages": [],
                "page_count": 0,
            }
        root_url = str(root.get("final_url") or root.get("url") or url).strip()
        candidate_links: list[str] = []
        seen_links: set[str] = {root_url}
        for item in list(root.get("links") or [])[:40]:
            cleaned = _clean_link(root_url, str(item or ""))
            if not cleaned or cleaned in seen_links or not _same_domain(root_url, cleaned):
                continue
            seen_links.add(cleaned)
            candidate_links.append(cleaned)

        pages: list[dict[str, Any]] = []
        root_page = {
            "url": root_url,
            "title": str(root.get("title") or "").strip(),
            "summary": str(root.get("summary") or "").strip(),
            "headings": list(root.get("headings") or [])[:6],
            "excerpt": _clean_text(str(root.get("visible_text") or ""), limit=420),
            "score": _score_for_query(query, root),
        }
        pages.append(root_page)

        fetched_pages: list[dict[str, Any]] = []
        budget = max(1, min(int(max_pages or 4), 6))
        for candidate_url in candidate_links[: max(3, budget * 2)]:
            extracted = self.extract(url=candidate_url, render_mode="cheap", include_screenshot=False)
            if not bool(extracted.get("reachable")):
                continue
            fetched_pages.append(
                {
                    "url": str(extracted.get("final_url") or extracted.get("url") or candidate_url).strip(),
                    "title": str(extracted.get("title") or "").strip(),
                    "summary": str(extracted.get("summary") or "").strip(),
                    "headings": list(extracted.get("headings") or [])[:6],
                    "excerpt": _clean_text(str(extracted.get("visible_text") or ""), limit=420),
                    "score": _score_for_query(query, extracted),
                }
            )

        fetched_pages.sort(key=lambda item: (int(item.get("score") or 0), len(str(item.get("excerpt") or ""))), reverse=True)
        pages.extend(fetched_pages[: max(0, budget - 1)])

        titles = [str(item.get("title") or "").strip() for item in pages if str(item.get("title") or "").strip()]
        summary_parts = [
            f"{len(pages)} sayfa tarandı.",
            f"Ana sayfa: {root_page['title'] or root_url}.",
        ]
        if len(pages) > 1 and titles[1:]:
            summary_parts.append("Öne çıkan alt sayfalar: " + "; ".join(titles[1:4]) + ".")
        if query:
            summary_parts.append("Tarama kullanıcı sorusuna göre en ilgili sayfaları öne aldı.")
        return {
            "url": root_url,
            "reachable": True,
            "summary": " ".join(summary_parts).strip(),
            "issues": list(root.get("issues") or []),
            "pages": pages,
            "page_count": len(pages),
            "links_considered": len(candidate_links),
        }


def extract_web_intelligence(url: str, *, render_mode: str = "auto", browser_client: Any | None = None, include_screenshot: bool = True) -> dict[str, Any]:
    return WebIntelService(browser_client=browser_client).extract(
        url=url,
        render_mode=render_mode,
        include_screenshot=include_screenshot,
    )
