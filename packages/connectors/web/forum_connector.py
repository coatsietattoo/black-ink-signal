"""Dedicated public forum thread collector for Black Ink Signal.

Bucket A only:
- Edmonton Forum
- Alberta Dual Sport Forums
- EMRA Forums

This collector crawls public discussion threads, extracts thread-level content,
and filters for local recommendation/service-seeking conversations.
It tags tattoo-related threads instead of requiring tattoo at collection time.
"""

from __future__ import annotations

import hashlib
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
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger("bis.connector.forum")

USER_AGENT = os.environ.get(
    "BIS_WEB_USER_AGENT",
    "BlackInkSignal/0.1 (public forum research; compliance-first)",
)
REQUEST_DELAY_SECONDS = float(os.environ.get("BIS_FORUM_REQUEST_DELAY", os.environ.get("BIS_WEB_REQUEST_DELAY", "1.0")))
MAX_THREADS_PER_SOURCE = int(os.environ.get("BIS_FORUM_MAX_THREADS_PER_SOURCE", "20"))
MAX_THREAD_BODY_CHARS = 4000

DEFAULT_SOURCES = [
    {"name": "Edmonton Forum", "url": "https://www.edmon.ca/", "forum_name": "Edmonton Forum"},
    {"name": "Alberta Dual Sport Forums", "url": "https://albertadualsport.ca/forums/", "forum_name": "Alberta Dual Sport Forums"},
    {"name": "EMRA Forums", "url": "https://emra.ca/forums/index.php", "forum_name": "EMRA Forums"},
]

POSITIVE_SIGNALS = [
    "looking for",
    "recommend",
    "recommendations",
    "who does",
    "any suggestions",
    "experience with",
    "need help",
    "availability",
    "booked with",
    "does anyone know",
    "where can i find",
    "best place for",
]

LOCAL_SIGNALS = [
    "edmonton",
    "st albert",
    "st. albert",
    "sherwood park",
    "spruce grove",
    "leduc",
    "yeg",
    "alberta",
]

TOPIC_TERMS = {
    "tattoo": ["tattoo", "tattoo artist", "tattoo shop", "cover up", "coverup", "black and grey", "realism", "memorial tattoo", "ink artist"],
    "trades": ["plumber", "electrician", "contractor", "reno", "renovation", "roofing", "flooring", "hvac", "drywall", "windows", "lawn care"],
    "auto": ["mechanic", "auto", "car", "vehicle", "honda", "ford", "toyota", "repair shop", "body shop", "oil change"],
    "motorcycle": ["motorcycle", "bike", "rider", "harley", "dualsport", "dual sport", "yamaha", "bmw", "ktm"],
    "fitness": ["gym", "trainer", "fitness", "physio", "physiotherapist", "massage", "workout", "pilates", "yoga"],
    "beauty": ["hair", "hairstylist", "lashes", "nails", "esthetician", "salon", "barber", "brows", "makeup"],
    "medical": ["doctor", "dentist", "clinic", "therapist", "surgeon", "chiropractor", "medical", "healthcare", "counsellor"],
    "parenting": ["dayhome", "day home", "childcare", "babysitter", "kids", "children", "school", "pregnant", "parenting"],
    "real_estate": ["realtor", "real estate", "mortgage", "landlord", "tenant", "rent", "rental", "house", "condo"],
    "job": ["job", "hiring", "career", "resume", "interview", "employment", "work", "position"],
}

THREAD_HINTS = [
    "/thread", "/threads/", "/topic/", "/showthread", "viewtopic", "/posts/", "/permalink/"
]

NON_THREAD_PATTERNS = [
    "/register", "/login", "/members", "/whats-new", "/search", "/account", "/help", "/faq"
]


@dataclass
class ForumItem:
    source: str = "forum"
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


class _ForumHTMLParser(HTMLParser):
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


def _truncate(text: str, limit: int = MAX_THREAD_BODY_CHARS) -> str:
    return _clean_text(text)[:limit].strip()


def _hash_id(source: str, url: str, title: str = "") -> str:
    raw = f"{source}|{url}|{title}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:20]


def _normalize_url(url: str, base_url: str) -> str:
    if not url:
        return ""
    return urljoin(base_url, url.strip())


def _canonicalize_thread_url(url: str) -> str:
    if not url:
        return url
    return re.sub(r"/post-\d+/?$", "", url)


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


def _extract_timestamp(parser: _ForumHTMLParser, text: str) -> datetime | None:
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


def _has_any(text: str, phrases: list[str]) -> bool:
    t = (text or "").lower()
    return any(p in t for p in phrases)


def _find_matches(text: str, phrases: list[str]) -> list[str]:
    t = (text or "").lower()
    return [p for p in phrases if p in t]


def _count_any(text: str, phrases: list[str]) -> int:
    t = (text or "").lower()
    return sum(1 for p in phrases if p in t)


def _thread_like(url: str, anchor_text: str = "") -> bool:
    u = url.lower()
    a = (anchor_text or "").lower()
    if any(p in u for p in NON_THREAD_PATTERNS):
        return False
    if any(p in u for p in THREAD_HINTS):
        return True
    if re.search(r"/\d{4,}[-_]", u):
        return True
    if re.search(r"\b(thread|topic|post)\b", a):
        return True
    if len(a.split()) >= 4 and "?" in a:
        return True
    return len(a.split()) >= 5 and not any(x in a for x in ["log in", "register", "new posts", "forum list"])


def _topic_tag(text: str) -> tuple[str, bool]:
    hay = (text or "").lower()
    scores: dict[str, int] = {}
    for topic, terms in TOPIC_TERMS.items():
        scores[topic] = _count_any(hay, terms)
    best_topic = max(scores, key=scores.get) if scores else "other"
    if scores.get(best_topic, 0) <= 0:
        best_topic = "other"
    return best_topic, best_topic == "tattoo"


def _passes_intent_filter(title: str, text: str, forum_name: str) -> tuple[bool, list[str], str, bool, list[str], list[str]]:
    hay = f"{title} {text} {forum_name}".lower()
    reasons: list[str] = []
    local_terms = _find_matches(hay, LOCAL_SIGNALS)
    if local_terms:
        reasons.append("local_signal")
    else:
        return False, ["missing_local_signal"], "other", False, [], []
    conversation_terms = _find_matches(hay, POSITIVE_SIGNALS)
    if conversation_terms:
        reasons.append("conversation_intent")
    else:
        return False, ["missing_conversation_intent"], "other", False, [], local_terms
    topic_tag, is_tattoo_related = _topic_tag(hay)
    reasons.append(f"topic:{topic_tag}")
    if is_tattoo_related:
        reasons.append("tattoo_related")
    return True, reasons, topic_tag, is_tattoo_related, conversation_terms, local_terms


class ForumConnector:
    def __init__(self, sources: list[dict[str, str]] | None = None, request_delay: float = REQUEST_DELAY_SECONDS):
        self.sources = sources or DEFAULT_SOURCES
        self.request_delay = request_delay
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=20.0,
            follow_redirects=True,
        )
        self.stats = {
            "threads_scanned": 0,
            "threads_passing_filters": 0,
            "topic_breakdown": {},
            "tattoo_related_count": 0,
            "per_source": {},
            "skipped_examples": [],
        }

    def close(self):
        self._client.close()

    def _record_skip(self, reason: str, title: str, url: str):
        if len(self.stats["skipped_examples"]) < 20:
            self.stats["skipped_examples"].append({"reason": reason, "title": _truncate(title, 160), "url": url})

    def _get_html(self, url: str) -> str | None:
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype:
                return None
            return resp.text
        except Exception as e:
            logger.error(f"Forum fetch failed: {url} — {e}")
            return None
        finally:
            time.sleep(self.request_delay)

    def fetch_all(self) -> list[ForumItem]:
        items: list[ForumItem] = []
        seen: set[str] = set()
        for source in self.sources:
            source_items = self.fetch_source(source)
            for item in source_items:
                if item.dedupe_key not in seen:
                    seen.add(item.dedupe_key)
                    items.append(item)
        return items

    def fetch_source(self, source: dict[str, str]) -> list[ForumItem]:
        url = source["url"]
        forum_name = source["forum_name"]
        html = self._get_html(url)
        if not html:
            return []

        parser = _ForumHTMLParser()
        parser.feed(html)
        candidates: list[tuple[str, str]] = []
        for link in parser.links:
            href = _canonicalize_thread_url(_normalize_url(link.get("href", ""), url))
            text = _clean_text(link.get("text", ""))
            if not href or not text:
                continue
            if urlparse(href).netloc != urlparse(url).netloc:
                continue
            if _thread_like(href, text):
                candidates.append((href, text))

        deduped_candidates: list[tuple[str, str]] = []
        seen_urls: set[str] = set()
        for href, text in candidates:
            if href in seen_urls:
                continue
            seen_urls.add(href)
            deduped_candidates.append((href, text))
            if len(deduped_candidates) >= MAX_THREADS_PER_SOURCE:
                break

        self.stats["per_source"][forum_name] = {"thread_candidates": len(deduped_candidates), "threads_scanned": 0, "passed": 0}

        items: list[ForumItem] = []
        for thread_url, thread_label in deduped_candidates:
            item = self._fetch_thread(thread_url, forum_name, thread_label)
            self.stats["threads_scanned"] += 1
            self.stats["per_source"][forum_name]["threads_scanned"] += 1
            if item is None:
                continue
            self.stats["threads_passing_filters"] += 1
            self.stats["per_source"][forum_name]["passed"] += 1
            topic = item.raw.get("topic_tag", "other")
            self.stats["topic_breakdown"][topic] = self.stats["topic_breakdown"].get(topic, 0) + 1
            if item.raw.get("is_tattoo_related"):
                self.stats["tattoo_related_count"] += 1
            items.append(item)
        return items

    def _fetch_thread(self, thread_url: str, forum_name: str, fallback_title: str) -> ForumItem | None:
        html = self._get_html(thread_url)
        if not html:
            self._record_skip("fetch_failed", fallback_title, thread_url)
            return None

        parser = _ForumHTMLParser()
        parser.feed(html)
        title = _truncate(parser.meta.get("og:title") or parser.title or fallback_title, 300)
        text = _truncate(parser.meta.get("description") or parser.meta.get("og:description") or parser.text, MAX_THREAD_BODY_CHARS)
        created_at = _extract_timestamp(parser, html)
        keep, reasons, topic_tag, is_tattoo_related, conversation_terms, local_terms = _passes_intent_filter(title, text, forum_name)
        if not keep:
            self._record_skip(reasons[0] if reasons else "filtered_out", title, thread_url)
            return None

        return ForumItem(
            source="forum",
            item_id=_hash_id("forum", thread_url, title),
            url=thread_url,
            canonical_url=thread_url,
            title=title,
            snippet=_truncate(text, 500),
            text=text,
            forum=forum_name,
            created_at=created_at,
            raw={
                "kind": "forum_thread",
                "domain_class": "forum",
                "forum_name": forum_name,
                "thread_url": thread_url,
                "conversation_reasons": reasons,
                "conversation_intent_terms": conversation_terms,
                "local_terms": local_terms,
                "topic_tag": topic_tag,
                "is_tattoo_related": is_tattoo_related,
                "signal_test": not is_tattoo_related,
                "thread_label": fallback_title,
            },
        )
