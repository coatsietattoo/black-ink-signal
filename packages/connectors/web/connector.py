"""Generic public web/forum connector for Black Ink Signal.

Optimized for conversation discovery:
find pages where people are actively discussing, requesting, recommending,
comparing, or seeking tattoo services.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx

logger = logging.getLogger("bis.connector.web")

USER_AGENT = os.environ.get(
    "BIS_WEB_USER_AGENT",
    "BlackInkSignal/0.1 (public web research; compliance-first)",
)
REQUEST_DELAY_SECONDS = float(os.environ.get("BIS_WEB_REQUEST_DELAY", "1.0"))
MAX_TEXT_CHARS = 2000
MAX_ITEMS_PER_URL = int(os.environ.get("BIS_WEB_MAX_ITEMS_PER_URL", "20"))

DEFAULT_URLS: list[str] = [
    "https://www.google.com/search?q=tattoo+artist+Edmonton",
    "https://www.bing.com/search?q=cover+up+tattoo+Edmonton",
    "https://duckduckgo.com/html/?q=tattoo+recommendation+Edmonton",
]

DEFAULT_KEYWORDS: list[str] = [
    "looking for tattoo",
    "tattoo artist",
    "tattoo recommendation",
    "cover up",
    "coverup",
    "black and grey",
    "portrait tattoo",
    "memorial tattoo",
    "sleeve tattoo",
    "walk in tattoo",
    "edmonton",
    "yeg",
    "st albert",
    "sherwood park",
    "spruce grove",
    "leduc",
]

TATTOO_TERMS = [
    "tattoo", "tattoo artist", "cover up", "coverup", "black and grey",
    "portrait tattoo", "memorial tattoo", "sleeve tattoo", "walk in tattoo",
    "realism tattoo",
]

LOCATION_TERMS = [
    "edmonton", "yeg", "st albert", "st. albert", "sherwood park",
    "spruce grove", "leduc", "alberta",
]

STRONG_POSITIVE_TERMS = [
    "can anyone recommend",
    "looking for",
    "who does",
    "any suggestions",
    "need a tattoo artist",
    "cover up recommendation",
    "black and grey recommendation",
    "memorial tattoo recommendation",
    "booked with",
    "experience with",
    "has anyone used",
    "availability",
]

STRONG_NEGATIVE_TERMS = [
    "best tattoo shops",
    "top 10",
    "expert recommendations",
    "directory",
    "listicle",
    "review roundup",
    "ranking article",
    "best in alberta",
    "best in edmonton",
]

DISCUSSION_TERMS = [
    "forum", "thread", "discussion", "community", "comments", "posted by",
    "reply", "replies", "topic", "board", "question", "answers",
]

QUESTION_TERMS = [
    "can anyone", "anyone know", "who does", "has anyone", "is there", "where can i",
]

COMPETITOR_TERMS = [
    "our artists", "our studio", "book now", "book with us", "services",
    "portfolio", "gallery", "about our shop", "meet the artists",
]

DENY_DOMAINS = [
    "pinterest.", "yelp.", "yellowpages.", "mapquest.", "tripadvisor.",
    "foursquare.", "manta.", "zoominfo.", "wikitia.", "tumblr.",
]

COUPON_TERMS = ["coupon", "discount", "promo code", "deal", "voucher"]
IMAGE_TERMS = ["image search", "images for", "photos for"]
SEARCH_HOSTS = {
    "google": ["google."],
    "bing": ["bing.com"],
    "duckduckgo": ["duckduckgo.com"],
    "brave": ["search.brave.com"],
}

SOCIAL_HOST_FRAGMENTS = ["instagram.com", "x.com", "twitter.com", "youtube.com", "tiktok.com"]
COMMUNITY_HOST_FRAGMENTS = ["forum", "board", "community", "groups", "nextdoor", "patch.com", "quora.com"]
BUSINESS_LISTING_HOSTS = ["yelp.", "yellowpages.", "mapquest.", "tripadvisor.", "foursquare."]
COMPETITOR_HOST_TERMS = ["tattoo", "ink", "studio", "collective", "parlour", "parlor"]
NOISE_HOSTS = {"accounts.google.com", "support.google.com", "webcache.googleusercontent.com"}


@dataclass
class WebItem:
    source: str = "web"
    item_id: str = ""
    url: str = ""
    canonical_url: str = ""
    title: str = ""
    snippet: str = ""
    text: str = ""
    author: str = ""
    forum: str = ""
    created_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def body(self) -> str:
        return self.text or self.snippet or ""

    @property
    def dedupe_key(self) -> str:
        return f"{self.source}:{self.item_id}"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.links: list[dict[str, str]] = []
        self._in_title = False
        self._current_link: dict[str, str] | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            content = attrs_dict.get("content") or ""
            if name and content:
                self.meta[name] = content
        elif tag == "a":
            href = attrs_dict.get("href") or ""
            self._current_link = {"href": href, "text": ""}

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._current_link:
            self.links.append(self._current_link)
            self._current_link = None

    def handle_data(self, data):
        text = _clean_text(data)
        if not text:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
        if self._current_link is not None:
            self._current_link["text"] = f"{self._current_link['text']} {text}".strip()
        self._text_parts.append(text)

    @property
    def text(self) -> str:
        return " ".join(self._text_parts).strip()


def _clean_text(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _truncate(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    text = _clean_text(text)
    return text[:limit].strip()


def _load_urls_from_env() -> list[str]:
    raw = os.environ.get("BIS_WEB_URLS", "")
    if not raw.strip():
        return []
    try:
        if raw.strip().startswith("["):
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        logger.warning("Failed to parse BIS_WEB_URLS as JSON list; falling back to newline/comma split")
    parts = re.split(r"[\n,]", raw)
    return [p.strip() for p in parts if p.strip()]


def _load_keywords_from_env() -> list[str]:
    raw = os.environ.get("BIS_WEB_KEYWORDS", "")
    if not raw.strip():
        return []
    parts = re.split(r"\||\n|,", raw)
    return [p.strip().lower() for p in parts if p.strip()]


def _detect_search_engine(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    for name, fragments in SEARCH_HOSTS.items():
        if any(frag in host for frag in fragments):
            return name
    return None


def _looks_like_search_url(url: str) -> bool:
    return _detect_search_engine(url) is not None


def _extract_timestamp(parser: _HTMLTextExtractor, text: str) -> datetime | None:
    candidates = [
        parser.meta.get("article:published_time", ""),
        parser.meta.get("og:published_time", ""),
        parser.meta.get("publish-date", ""),
        parser.meta.get("date", ""),
        parser.meta.get("dc.date", ""),
        parser.meta.get("last-modified", ""),
    ]
    for c in candidates:
        dt = _parse_datetime(c)
        if dt:
            return dt
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})(?:[T\s](\d{2}:\d{2}(?::\d{2})?))?", text)
    if m:
        raw = m.group(1) + (f"T{m.group(2)}" if m.group(2) else "")
        return _parse_datetime(raw)
    return None


def _parse_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_url(url: str, base_url: str = "") -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith("/") and base_url:
        return urljoin(base_url, url)
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(base_url, url) if base_url else url


def _resolve_search_result_href(href: str, base_url: str = "") -> str:
    href = _normalize_url(href, base_url)
    if not href:
        return ""
    parsed = urlparse(href)
    host = parsed.netloc.lower()
    qs = parse_qs(parsed.query)
    if "google." in host:
        if parsed.path == "/url" and qs.get("q"):
            return qs["q"][0]
        if qs.get("url"):
            return qs["url"][0]
    if "bing.com" in host and qs.get("u"):
        return unquote(qs["u"][0])
    if "duckduckgo.com" in host and qs.get("uddg"):
        return unquote(qs["uddg"][0])
    return href


def _hash_id(source: str, url: str, title: str = "") -> str:
    raw = f"{source}|{url}|{title}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:20]


def _has_any(text: str, phrases: list[str]) -> bool:
    hay = (text or "").lower()
    return any(p in hay for p in phrases)


def _count_any(text: str, phrases: list[str]) -> int:
    hay = (text or "").lower()
    return sum(1 for p in phrases if p in hay)


def _classify_domain(host: str, text: str) -> str:
    h = host.lower()
    t = (text or "").lower()
    if any(d in h for d in DENY_DOMAINS):
        return "irrelevant"
    if any(s in h for s in SOCIAL_HOST_FRAGMENTS):
        return "social_public"
    if any(s in h for s in COMMUNITY_HOST_FRAGMENTS) or _has_any(t, DISCUSSION_TERMS + QUESTION_TERMS):
        return "community_page"
    if any(s in h for s in BUSINESS_LISTING_HOSTS):
        return "business_listing"
    if any(term in h for term in COMPETITOR_HOST_TERMS):
        return "competitor_site"
    if "forum" in h or "board" in h:
        return "forum"
    return "search_result"


def _is_noise_domain(host: str) -> bool:
    h = host.lower()
    return h in NOISE_HOSTS or any(d in h for d in DENY_DOMAINS)


def _conversation_flags(text: str, host: str, created_at: datetime | None) -> dict[str, Any]:
    t = (text or "").lower()
    tattoo = _has_any(t, TATTOO_TERMS)
    location = _has_any(t, LOCATION_TERMS) or _has_any(host, ["edmonton", "yeg", "stalbert", "sherwoodpark", "sprucegrove", "leduc"])
    strong_positive = _has_any(t, STRONG_POSITIVE_TERMS)
    strong_negative = _has_any(t, STRONG_NEGATIVE_TERMS)
    question_signal = _has_any(t, QUESTION_TERMS) or "?" in t
    discussion = _has_any(t, DISCUSSION_TERMS)
    competitor = _classify_domain(host, t) == "competitor_site"
    old_static = False
    if created_at is not None:
        try:
            age_days = max((datetime.now(timezone.utc) - created_at).days, 0)
            old_static = age_days > 365
        except Exception:
            old_static = False
    return {
        "has_tattoo": tattoo,
        "has_location": location,
        "strong_positive": strong_positive,
        "strong_negative": strong_negative,
        "question_signal": question_signal,
        "discussion": discussion,
        "is_competitor": competitor,
        "is_old_static": old_static,
    }


def _should_keep_candidate(title: str, snippet: str, url: str, domain_class: str, created_at: datetime | None = None) -> tuple[bool, str]:
    host = urlparse(url).netloc.lower()
    text = f"{title} {snippet} {url}"
    t = text.lower()
    flags = _conversation_flags(text, host, created_at)

    if _is_noise_domain(host):
        return False, "denylist_domain"
    if _has_any(t, COUPON_TERMS):
        return False, "coupon_page"
    if _has_any(t, IMAGE_TERMS):
        return False, "image_search_or_gallery"
    if domain_class == "irrelevant":
        return False, "classified_irrelevant"
    if not flags["has_tattoo"]:
        return False, "missing_tattoo_keyword"
    if not flags["has_location"]:
        return False, "missing_location_keyword"
    if flags["strong_negative"]:
        return False, "strong_negative_listicle_or_directory"
    if domain_class == "competitor_site" and not flags["strong_positive"]:
        return False, "competitor_without_conversation_intent"
    if not (flags["strong_positive"] or (flags["discussion"] and flags["question_signal"])):
        return False, "missing_conversation_signal"
    return True, "ok"


class WebConnector:
    def __init__(
        self,
        urls: list[str] | None = None,
        keywords: list[str] | None = None,
        request_delay: float = REQUEST_DELAY_SECONDS,
    ):
        self.urls = urls or _load_urls_from_env() or DEFAULT_URLS
        self.keywords = keywords or _load_keywords_from_env() or DEFAULT_KEYWORDS
        self.request_delay = request_delay
        self.skipped_examples: list[dict[str, str]] = []
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=20.0,
            follow_redirects=True,
        )

    def close(self):
        self._client.close()

    def _record_skip(self, reason: str, title: str, url: str):
        if len(self.skipped_examples) < 25:
            self.skipped_examples.append({"reason": reason, "title": _truncate(title, 120), "url": url})

    def _get_html(self, url: str) -> str | None:
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "xml" not in ctype:
                logger.info(f"Skipping non-HTML content: {url} ({ctype})")
                return None
            return resp.text
        except Exception as e:
            logger.error(f"Web fetch failed: {url} — {e}")
            return None
        finally:
            time.sleep(self.request_delay)

    def fetch_all(self) -> list[WebItem]:
        all_items: list[WebItem] = []
        seen: set[str] = set()
        for url in self.urls:
            items = self.fetch_url(url)
            for item in items:
                if item.dedupe_key not in seen:
                    seen.add(item.dedupe_key)
                    all_items.append(item)
        return all_items

    def fetch_url(self, url: str) -> list[WebItem]:
        html = self._get_html(url)
        if not html:
            return []
        if _looks_like_search_url(url):
            return self._parse_search_results(url, html)
        return self._parse_page_or_forum(url, html)

    def _parse_search_results(self, url: str, html: str) -> list[WebItem]:
        parser = _HTMLTextExtractor()
        parser.feed(html)
        items: list[WebItem] = []
        search_engine = _detect_search_engine(url)

        for link in parser.links:
            raw_href = link.get("href", "")
            href = _resolve_search_result_href(raw_href, url)
            text = _truncate(link.get("text", ""), 300)
            if not href or not text:
                continue
            parsed = urlparse(href)
            if parsed.scheme not in {"http", "https"}:
                continue
            host = parsed.netloc.lower()
            if _is_noise_domain(host):
                self._record_skip("denylist_domain", text, href)
                continue
            domain_class = _classify_domain(host, text)
            keep, reason = _should_keep_candidate(text, text, href, domain_class)
            if not keep:
                self._record_skip(reason, text, href)
                continue
            source = "forum" if domain_class in {"forum", "community_page"} else "web"
            item = WebItem(
                source=source,
                item_id=_hash_id(source, href, text),
                url=href,
                canonical_url=href,
                title=text,
                snippet=text,
                text=text,
                forum=host,
                raw={
                    "kind": "search_result",
                    "search_url": url,
                    "anchor_text": text,
                    "discovery_source": search_engine,
                    "destination_domain": host,
                    "domain_class": domain_class,
                    "quality_reason": reason,
                },
            )
            items.append(item)
            if len(items) >= MAX_ITEMS_PER_URL:
                break
        logger.info(f"Parsed {len(items)} conversation-led search results from {url}")
        return items

    def _parse_page_or_forum(self, url: str, html: str) -> list[WebItem]:
        parser = _HTMLTextExtractor()
        parser.feed(html)
        page_title = _truncate(parser.meta.get("og:title") or parser.title or "", 300)
        page_desc = _truncate(
            parser.meta.get("description")
            or parser.meta.get("og:description")
            or parser.text,
            MAX_TEXT_CHARS,
        )
        host = urlparse(url).netloc.lower()
        domain_class = _classify_domain(host, f"{page_title} {page_desc}")
        created_at = _extract_timestamp(parser, html)
        keep, reason = _should_keep_candidate(page_title, page_desc, url, domain_class, created_at)
        if not keep:
            self._record_skip(reason, page_title or url, url)
            logger.info(f"Skipping page {url}: {reason}")
            return []
        source = "forum" if domain_class in {"forum", "community_page"} else "web"
        item = WebItem(
            source=source,
            item_id=_hash_id(source, url, page_title or page_desc[:80]),
            url=url,
            canonical_url=url,
            title=page_title or url,
            snippet=_truncate(page_desc, 400),
            text=page_desc,
            forum=host,
            created_at=created_at,
            raw={
                "kind": "page",
                "fetched_url": url,
                "meta": parser.meta,
                "destination_domain": host,
                "domain_class": domain_class,
                "quality_reason": reason,
            },
        )
        return [item]
