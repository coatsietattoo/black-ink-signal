"""Lead scoring engine for Black Ink Signal.

Score range: 1-100.

Factors:
  intent_strength   0-30   keyword + semantic match quality
  geo_match         0-20   Edmonton / Alberta location signal
  recency           0-10   how fresh the post is
  project_size      0-15   signals of large / multi-session work
  urgency           0-10   emotional urgency / dissatisfaction
  engagement        0-5    upvotes / replies activity
  repeat_collector  0-5    signals of ongoing tattoo interest
  coverup_need      0-5    previous bad tattoo / coverup language
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Keyword banks
# ---------------------------------------------------------------------------

HIGH_INTENT_PHRASES: list[str] = [
    "looking for tattoo artist",
    "looking for artist",
    "tattoo recommendations",
    "recommend a tattoo",
    "best tattoo artist",
    "need tattoo ideas",
    "tattoo quote",
    "walk in tattoo",
    "book a tattoo",
    "tattoo appointment",
    "who does",
    "anyone know a good tattoo",
]

STYLE_PHRASES: list[str] = [
    "cover up tattoo",
    "coverup tattoo",
    "black and grey",
    "black and gray",
    "realism tattoo",
    "realistic tattoo",
    "tattoo sleeve",
    "half sleeve",
    "full sleeve",
    "back piece",
    "chest piece",
    "first tattoo",
]

GEO_PHRASES: list[str] = [
    "edmonton",
    "yeg",
    "alberta",
    "whyte ave",
    "st albert",
    "sherwood park",
    "spruce grove",
    "leduc",
    "red deer",
    "calgary",
]

LARGE_PROJECT_PHRASES: list[str] = [
    "sleeve",
    "half sleeve",
    "full sleeve",
    "back piece",
    "chest piece",
    "full back",
    "leg sleeve",
    "multi session",
    "multiple sessions",
    "big piece",
    "large piece",
]

URGENCY_PHRASES: list[str] = [
    "asap",
    "as soon as possible",
    "this week",
    "today",
    "tomorrow",
    "need it done",
    "urgent",
    "cancellation",
    "walk in",
    "walk-in",
]

COVERUP_PHRASES: list[str] = [
    "cover up",
    "coverup",
    "cover-up",
    "fix my tattoo",
    "bad tattoo",
    "regret",
    "tattoo removal",
    "redo",
    "rework",
    "unhappy with my tattoo",
]

LOCAL_SUBREDDITS: set[str] = {
    "edmonton", "alberta", "yeg", "edmontonsocial",
    "stalbert", "sherwoodpark",
}


def _phrase_match_count(text: str, phrases: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for p in phrases if p in text_lower)


def _hours_since(dt: datetime | None) -> float:
    if dt is None:
        return 999.0
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = (now - dt).total_seconds() / 3600
    return max(delta, 0.0)


# ---------------------------------------------------------------------------
# Score components
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    intent: int = 0
    geo: int = 0
    recency: int = 0
    project_size: int = 0
    urgency: int = 0
    engagement: int = 0
    repeat_collector: int = 0
    coverup: int = 0
    total: int = 0
    keyword_trigger: str = ""
    semantic_label: str = ""
    geo_estimate: str = ""
    geo_confidence: str = "none"


def score_lead(
    title: str = "",
    body: str = "",
    subreddit: str = "",
    created_at: datetime | None = None,
    score_ups: int | None = None,
    num_comments: int | None = None,
) -> ScoreBreakdown:
    """Return a ScoreBreakdown for a candidate lead item."""

    text = f"{title} {body}".strip()
    text_lower = text.lower()
    result = ScoreBreakdown()

    # --- Intent (0-30) ---
    high_hits = _phrase_match_count(text, HIGH_INTENT_PHRASES)
    style_hits = _phrase_match_count(text, STYLE_PHRASES)
    intent_raw = min(high_hits * 10 + style_hits * 5, 30)
    result.intent = intent_raw

    # Build keyword trigger label
    triggers: list[str] = []
    for p in HIGH_INTENT_PHRASES + STYLE_PHRASES:
        if p in text_lower:
            triggers.append(p)
    result.keyword_trigger = "; ".join(triggers[:3]) if triggers else ""

    # Semantic label (rule-based bucket for now, LLM upgrade later)
    if any(p in text_lower for p in ["looking for artist", "recommend", "who does", "best tattoo"]):
        result.semantic_label = "looking_for_artist"
    elif any(p in text_lower for p in COVERUP_PHRASES):
        result.semantic_label = "coverup_help"
    elif any(p in text_lower for p in ["first tattoo"]):
        result.semantic_label = "first_tattoo"
    elif any(p in text_lower for p in ["sleeve", "back piece", "chest piece"]):
        result.semantic_label = "large_project"
    elif style_hits > 0:
        result.semantic_label = "style_research"
    elif high_hits > 0:
        result.semantic_label = "general_intent"

    # --- Geo (0-20) ---
    geo_hits = _phrase_match_count(text, GEO_PHRASES)
    sub_lower = subreddit.lower() if subreddit else ""
    sub_is_local = sub_lower in LOCAL_SUBREDDITS

    if "edmonton" in text_lower or "yeg" in text_lower or sub_lower == "edmonton":
        result.geo = 20
        result.geo_estimate = "Edmonton"
        result.geo_confidence = "high"
    elif sub_is_local:
        result.geo = 15
        result.geo_estimate = f"r/{subreddit} (local)"
        result.geo_confidence = "medium"
    elif "alberta" in text_lower or "calgary" in text_lower:
        result.geo = 10
        result.geo_estimate = "Alberta"
        result.geo_confidence = "medium"
    elif geo_hits > 0:
        result.geo = 5
        result.geo_estimate = "Alberta region"
        result.geo_confidence = "low"
    else:
        result.geo = 0
        result.geo_estimate = ""
        result.geo_confidence = "none"

    # --- Recency (0-10) ---
    hours = _hours_since(created_at)
    if hours < 1:
        result.recency = 10
    elif hours < 6:
        result.recency = 8
    elif hours < 24:
        result.recency = 6
    elif hours < 72:
        result.recency = 3
    else:
        result.recency = 1

    # --- Project size (0-15) ---
    proj_hits = _phrase_match_count(text, LARGE_PROJECT_PHRASES)
    result.project_size = min(proj_hits * 5, 15)

    # --- Urgency (0-10) ---
    urg_hits = _phrase_match_count(text, URGENCY_PHRASES)
    result.urgency = min(urg_hits * 5, 10)

    # --- Engagement (0-5) ---
    ups = score_ups or 0
    coms = num_comments or 0
    eng = min((ups // 5) + (coms // 3), 5)
    result.engagement = eng

    # --- Repeat collector (0-5) ---
    collector_phrases = ["my tattoos", "my collection", "adding to", "next tattoo", "another tattoo"]
    col_hits = _phrase_match_count(text, collector_phrases)
    result.repeat_collector = min(col_hits * 3, 5)

    # --- Coverup (0-5) ---
    cov_hits = _phrase_match_count(text, COVERUP_PHRASES)
    result.coverup = min(cov_hits * 3, 5)

    # --- Total ---
    result.total = min(
        result.intent + result.geo + result.recency + result.project_size +
        result.urgency + result.engagement + result.repeat_collector + result.coverup,
        100,
    )

    return result


def score_band(score: int) -> str:
    if score >= 80:
        return "hot"
    elif score >= 60:
        return "strong"
    elif score >= 40:
        return "watchlist"
    else:
        return "low"
