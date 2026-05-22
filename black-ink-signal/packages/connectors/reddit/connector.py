"""Reddit public-source connector for Black Ink Signal.

Uses Reddit's public JSON endpoints (append .json to any listing URL).
No authentication required. Respects rate limits.
Public data only — no private subreddits, no user profile scraping.
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("bis.connector.reddit")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_SUBREDDITS: list[str] = [
    "tattoos",
    "tattoodesigns",
    "tattoo",
    "Edmonton",
    "alberta",
    "tattooadvice",
]

SEARCH_QUERIES: list[str] = [
    "looking for tattoo artist",
    "tattoo recommendations",
    "cover up tattoo",
    "realism tattoo",
    "black and grey tattoo",
    "first tattoo advice",
    "tattoo in edmonton",
    "best tattoo artist",
    "tattoo sleeve",
]

USER_AGENT = "BlackInkSignal/0.1 (public research; compliance-first)"
REQUEST_DELAY_SECONDS = 2.0  # polite rate limit
MAX_ITEMS_PER_FETCH = 25


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class RedditItem:
    """Normalized item from a Reddit JSON listing."""
    source: str = "reddit"
    item_id: str = ""
    subreddit: str = ""
    author: str = ""
    title: str = ""
    selftext: str = ""
    url: str = ""
    permalink: str = ""
    created_utc: float = 0.0
    score: int = 0
    num_comments: int = 0
    link_flair_text: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def created_at(self) -> datetime:
        return datetime.fromtimestamp(self.created_utc, tz=timezone.utc)

    @property
    def canonical_url(self) -> str:
        return f"https://www.reddit.com{self.permalink}" if self.permalink else self.url

    @property
    def dedupe_key(self) -> str:
        return f"reddit:{self.item_id}"

    @property
    def body(self) -> str:
        return self.selftext or ""


def _parse_listing(data: dict) -> list[RedditItem]:
    """Parse a Reddit JSON listing response into RedditItems."""
    items: list[RedditItem] = []
    children = data.get("data", {}).get("children", [])
    for child in children:
        d = child.get("data", {})
        if not d.get("id"):
            continue
        items.append(RedditItem(
            item_id=d.get("name", d["id"]),
            subreddit=d.get("subreddit", ""),
            author=d.get("author", "[deleted]"),
            title=d.get("title", ""),
            selftext=d.get("selftext", ""),
            url=d.get("url", ""),
            permalink=d.get("permalink", ""),
            created_utc=d.get("created_utc", 0),
            score=d.get("score", 0),
            num_comments=d.get("num_comments", 0),
            link_flair_text=d.get("link_flair_text", ""),
            raw=d,
        ))
    return items


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------

class RedditConnector:
    """Fetches public Reddit listings. No auth, public JSON only."""

    def __init__(
        self,
        subreddits: list[str] | None = None,
        search_queries: list[str] | None = None,
        request_delay: float = REQUEST_DELAY_SECONDS,
    ):
        self.subreddits = subreddits or DEFAULT_SUBREDDITS
        self.search_queries = search_queries or SEARCH_QUERIES
        self.request_delay = request_delay
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=15.0,
            follow_redirects=True,
        )

    def close(self):
        self._client.close()

    def _get_json(self, url: str, params: dict | None = None) -> dict | None:
        """GET a URL, return parsed JSON or None on failure."""
        try:
            resp = self._client.get(url, params=params)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "60"))
                logger.warning(f"Rate limited, sleeping {retry_after}s")
                time.sleep(retry_after)
                resp = self._client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Reddit fetch failed: {url} — {e}")
            return None

    def fetch_subreddit_new(self, subreddit: str, limit: int = MAX_ITEMS_PER_FETCH) -> list[RedditItem]:
        """Fetch newest posts from a subreddit's public JSON feed."""
        url = f"https://www.reddit.com/r/{subreddit}/new.json"
        data = self._get_json(url, params={"limit": str(limit), "raw_json": "1"})
        if data is None:
            return []
        time.sleep(self.request_delay)
        return _parse_listing(data)

    def search_subreddit(self, subreddit: str, query: str, limit: int = MAX_ITEMS_PER_FETCH) -> list[RedditItem]:
        """Search a subreddit using Reddit's public search JSON."""
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": query,
            "restrict_sr": "1",
            "sort": "new",
            "limit": str(limit),
            "raw_json": "1",
        }
        data = self._get_json(url, params=params)
        if data is None:
            return []
        time.sleep(self.request_delay)
        return _parse_listing(data)

    def fetch_all_new(self) -> list[RedditItem]:
        """Fetch new posts from all configured subreddits."""
        all_items: list[RedditItem] = []
        for sub in self.subreddits:
            items = self.fetch_subreddit_new(sub)
            logger.info(f"r/{sub}/new: {len(items)} items")
            all_items.extend(items)
        return all_items

    def search_all(self) -> list[RedditItem]:
        """Run all configured search queries across configured subreddits."""
        all_items: list[RedditItem] = []
        seen_ids: set[str] = set()
        for sub in self.subreddits:
            for query in self.search_queries:
                items = self.search_subreddit(sub, query, limit=10)
                for item in items:
                    if item.item_id not in seen_ids:
                        seen_ids.add(item.item_id)
                        all_items.append(item)
        return all_items
