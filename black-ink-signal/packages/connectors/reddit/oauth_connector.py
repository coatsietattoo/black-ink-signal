"""Reddit OAuth2 connector — uses Reddit's script app authentication.

Falls back to public JSON if no credentials are configured.
Requires: client_id, client_secret, username, password

Setup:
1. Go to https://www.reddit.com/prefs/apps
2. Create a "script" type app
3. Note the client_id (under app name) and client_secret
4. Set env vars in .env file

Rate limits:
- Authenticated: 100 requests/minute (vs ~10/min unauthenticated)
- We use a 1-second delay between requests (conservative)
"""

from __future__ import annotations
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

import httpx

from connector import RedditItem, _parse_listing, DEFAULT_SUBREDDITS, SEARCH_QUERIES

logger = logging.getLogger("bis.connector.reddit_oauth")

OAUTH_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_API_BASE = "https://oauth.reddit.com"
REQUEST_DELAY = 1.0  # seconds between requests
MAX_ITEMS_PER_FETCH = 25


class RedditOAuthConnector:
    """Authenticated Reddit connector using script app credentials."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        user_agent: str = "BlackInkSignal/0.1 (by /u/blackinksignal)",
        subreddits: list[str] | None = None,
        search_queries: list[str] | None = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self._user_agent = user_agent
        self.subreddits = subreddits or DEFAULT_SUBREDDITS
        self.search_queries = search_queries or SEARCH_QUERIES

        self._access_token: str | None = None
        self._token_expires: float = 0

        self._client = httpx.Client(
            headers={"User-Agent": self._user_agent},
            timeout=15.0,
            follow_redirects=True,
        )

    def close(self):
        self._client.close()

    def _authenticate(self) -> bool:
        """Get OAuth2 access token."""
        try:
            resp = self._client.post(
                OAUTH_TOKEN_URL,
                auth=(self._client_id, self._client_secret),
                data={
                    "grant_type": "password",
                    "username": self._username,
                    "password": self._password,
                },
                headers={"User-Agent": self._user_agent},
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 3600) - 60
            logger.info("Reddit OAuth authenticated successfully")
            return True
        except Exception as e:
            logger.error(f"Reddit OAuth authentication failed: {e}")
            return False

    def _ensure_token(self) -> bool:
        """Ensure we have a valid access token."""
        if self._access_token and time.time() < self._token_expires:
            return True
        return self._authenticate()

    def _get_json(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Make authenticated API request."""
        if not self._ensure_token():
            return None

        url = f"{OAUTH_API_BASE}{endpoint}"
        try:
            resp = self._client.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "User-Agent": self._user_agent,
                },
            )
            if resp.status_code == 401:
                # Token expired, retry
                self._access_token = None
                if not self._ensure_token():
                    return None
                resp = self._client.get(
                    url,
                    params=params,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "User-Agent": self._user_agent,
                    },
                )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "60"))
                logger.warning(f"Rate limited, sleeping {retry_after}s")
                time.sleep(retry_after)
                resp = self._client.get(
                    url,
                    params=params,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "User-Agent": self._user_agent,
                    },
                )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Reddit OAuth request failed: {endpoint} — {e}")
            return None
        finally:
            time.sleep(REQUEST_DELAY)

    def fetch_subreddit_new(self, subreddit: str, limit: int = MAX_ITEMS_PER_FETCH) -> list[RedditItem]:
        """Fetch newest posts from a subreddit."""
        data = self._get_json(f"/r/{subreddit}/new", params={"limit": str(limit), "raw_json": "1"})
        if data is None:
            return []
        return _parse_listing(data)

    def search_subreddit(self, subreddit: str, query: str, limit: int = MAX_ITEMS_PER_FETCH) -> list[RedditItem]:
        """Search a subreddit."""
        params = {
            "q": query,
            "restrict_sr": "1",
            "sort": "new",
            "limit": str(limit),
            "raw_json": "1",
        }
        data = self._get_json(f"/r/{subreddit}/search", params=params)
        if data is None:
            return []
        return _parse_listing(data)

    def fetch_all_new(self) -> list[RedditItem]:
        """Fetch new posts from all configured subreddits."""
        all_items: list[RedditItem] = []
        for sub in self.subreddits:
            items = self.fetch_subreddit_new(sub)
            logger.info(f"r/{sub}/new (OAuth): {len(items)} items")
            all_items.extend(items)
        return all_items

    def search_all(self) -> list[RedditItem]:
        """Run all configured search queries."""
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
