"""Manual browser-assisted local conversation collector for Black Ink Signal.

This collector is intentionally conservative:
- no messaging
- no private profile scraping
- no email/phone/profile harvesting
- only visible post/comment text, URL, timestamp if visible, group/page name, and match reasons
- human review only

It is designed for manual browser sessions on high-yield local conversation surfaces.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

GROUP_TARGETS = [
    {"name": "Edmonton Tattoo Community", "url": "https://www.facebook.com/groups/edmontontattoocommunity/"},
    {"name": "Edmonton Alberta Local Businesses & Recommendations", "url": "https://www.facebook.com/groups/edmontonalbertabusinesses/"},
    {"name": "Edmonton Alberta Small Businesses and Local Services", "url": "https://www.facebook.com/groups/smallbusinessedmonton/"},
    {"name": "The ORIGINAL St. Albert Chat", "url": "https://www.facebook.com/groups/stalbertchat/"},
    {"name": "Sherwood Park Community & Area Info", "url": "https://www.facebook.com/groups/824098623424214/"},
    {"name": "Spruce Grove / Stony Plain and Parkland County Local Chat Group", "url": "https://www.facebook.com/groups/394064004082927/"},
    {"name": "Leduc Local Chat", "url": "https://www.facebook.com/groups/505641606871354/"},
    {"name": "Edmonton Moms Community Group", "url": "https://www.facebook.com/groups/edmontonmomscommunity/"},
]

INTENT_TERMS = [
    "can anyone recommend",
    "looking for",
    "who does",
    "any suggestions",
    "need a tattoo artist",
    "cover up",
    "black and grey",
    "memorial tattoo",
    "portrait tattoo",
    "availability",
    "booked out",
    "experience with",
]

LOCAL_TERMS = [
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
    "tattoo": ["tattoo", "tattoo artist", "cover up", "coverup", "black and grey", "memorial tattoo", "portrait tattoo", "ink"],
    "trades": ["plumber", "electrician", "contractor", "reno", "renovation", "roofing", "hvac"],
    "auto": ["mechanic", "car", "vehicle", "repair shop", "body shop"],
    "motorcycle": ["motorcycle", "bike", "harley", "yamaha", "bmw", "ktm"],
    "fitness": ["gym", "trainer", "fitness", "physio", "massage", "pilates", "yoga"],
    "beauty": ["hair", "lashes", "nails", "salon", "barber", "brows", "makeup"],
    "medical": ["doctor", "dentist", "clinic", "therapist", "chiropractor"],
    "parenting": ["dayhome", "childcare", "babysitter", "kids", "school", "parenting"],
    "real_estate": ["realtor", "mortgage", "landlord", "tenant", "rental", "house"],
    "job": ["job", "hiring", "career", "employment", "resume"],
}


@dataclass
class BrowserConversationItem:
    source: str = "browser_conversation"
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


def _hash_id(source: str, url: str, title: str = "") -> str:
    import hashlib
    raw = f"{source}|{url}|{title}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:20]


def _find_matches(text: str, phrases: list[str]) -> list[str]:
    hay = (text or "").lower()
    return [p for p in phrases if p in hay]


def _topic_tag(text: str) -> tuple[str, bool]:
    hay = (text or "").lower()
    best_topic = "other"
    best_score = 0
    for topic, terms in TOPIC_TERMS.items():
        score = sum(1 for t in terms if t in hay)
        if score > best_score:
            best_score = score
            best_topic = topic
    return best_topic, best_topic == "tattoo"


def build_item(group_name: str, post_url: str, title: str, text: str, timestamp_text: str | None = None) -> BrowserConversationItem | None:
    conversation_terms = _find_matches(text + " " + title, INTENT_TERMS)
    local_terms = _find_matches(text + " " + title + " " + group_name, LOCAL_TERMS)
    if not conversation_terms or not local_terms:
        return None
    topic_tag, is_tattoo_related = _topic_tag(text + " " + title)
    created_at = None
    if timestamp_text:
        try:
            created_at = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except Exception:
            created_at = None
    return BrowserConversationItem(
        source="facebook_browser" if "facebook.com" in post_url else "browser_conversation",
        item_id=_hash_id("browser_conversation", post_url, title or text[:80]),
        url=post_url,
        canonical_url=post_url,
        title=title or group_name,
        snippet=text[:500].strip(),
        text=text[:4000].strip(),
        forum=group_name,
        created_at=created_at,
        raw={
            "kind": "browser_conversation",
            "domain_class": "social_public",
            "group_name": group_name,
            "thread_url": post_url,
            "topic_tag": topic_tag,
            "is_tattoo_related": is_tattoo_related,
            "conversation_reasons": ["visible_browser_post", "conversation_intent", f"topic:{topic_tag}"],
            "conversation_intent_terms": conversation_terms,
            "local_terms": local_terms,
            "signal_test": not is_tattoo_related,
            "human_review_only": True,
        },
    )
