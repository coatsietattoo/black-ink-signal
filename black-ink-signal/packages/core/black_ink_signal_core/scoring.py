"""Lead scoring engine for Black Ink Signal — v2.

Redesigned to surface high-value local leads aggressively.

Target score bands:
  85-100  Explicit local buying intent (artist search + Edmonton)
  80-95   Coverup / sleeve / memorial + local
  75-90   Style search + local
  55-75   Tattoo intent without location
  25-55   General discussion
  <20     Meme / no intent

Architecture:
  Base intent score (0-50)  — what do they want?
  Geo multiplier            — are they local?
  Project bonus (0-15)      — how big is the job?
  Urgency bonus (0-10)      — how soon?
  Engagement bonus (0-5)    — is the thread active?
  Recency bonus (0-8)       — is it fresh? (boost, not dominate)
  Penalties                 — meme / show-off / aftercare-only
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Keyword banks
# ---------------------------------------------------------------------------

# Tier 1: Explicit buying intent — someone actively looking to book
BUYING_INTENT: list[str] = [
    "looking for tattoo artist",
    "looking for artist",
    "looking for a tattoo",
    "looking for someone",
    "recommend a tattoo",
    "tattoo recommendations",
    "who does",
    "anyone know a good tattoo",
    "anyone know a tattoo",
    "best tattoo artist",
    "best tattoo shop",
    "book a tattoo",
    "tattoo appointment",
    "want to get a tattoo",
    "want to get tattooed",
    "need a tattoo artist",
    "where should i get",
    "where can i get",
    "iso tattoo",
    "in search of tattoo",
    "need tattoo ideas",
    "looking for portfolio",
    "portfolio recs",
    "any portfolio",
    "can anyone recommend",
    "does anyone know",
]

# Tier 2: Strong project signals — specific work they want done
PROJECT_INTENT: list[str] = [
    "cover up tattoo",
    "coverup tattoo",
    "cover up",
    "coverup",
    "cover-up",
    "black and grey",
    "black and gray",
    "realism tattoo",
    "realistic tattoo",
    "realism artist",
    "portrait tattoo",
    "tattoo sleeve",
    "half sleeve",
    "full sleeve",
    "back piece",
    "chest piece",
    "leg sleeve",
    "first tattoo",
    "memorial tattoo",
    "tribute tattoo",
    "memorial piece",
    "in memory of",
    "lost my",  # memorial signal
    "passed away",  # memorial signal
    "japanese tattoo",
    "traditional tattoo",
    "neo traditional",
    "geometric tattoo",
    "fine line tattoo",
    "dotwork",
    "watercolor tattoo",
    "script tattoo",
    "lettering tattoo",
    "tattoo quote",
    "tattoo cost",
    "how much for a tattoo",
    "how much does a tattoo",
]

# Tier 3: Moderate intent — price/quote interest, healing issues
MODERATE_INTENT: list[str] = [
    "tattoo price",
    "walk in tattoo",
    "walk-in tattoo",
    "touch up",
    "tattoo touch up",
    "fix my tattoo",
    "bad tattoo",
    "tattoo regret",
    "unhappy with my tattoo",
    "tattoo healing",
    "tattoo faded",
    "tattoo blown out",
    "redo my tattoo",
    "rework",
]

# Geo signals
GEO_EDMONTON: list[str] = [
    "edmonton",
    "yeg",
    "whyte ave",
    "whyte avenue",
    "jasper ave",
    "124 street",
    "mill woods",
    "windermere",
    "south edmonton",
    "west edmonton",
    "north edmonton",
]

GEO_METRO: list[str] = [
    "st albert",
    "st. albert",
    "sherwood park",
    "spruce grove",
    "stony plain",
    "leduc",
    "beaumont",
    "fort saskatchewan",
    "devon",
    "nisku",
]

GEO_ALBERTA: list[str] = [
    "alberta",
    "calgary",
    "red deer",
    "lethbridge",
    "medicine hat",
    "grande prairie",
    "airdrie",
    "banff",
    "canmore",
]

LOCAL_SUBREDDITS: set[str] = {
    "edmonton", "yeg", "edmontonsocial",
    "stalbert", "sherwoodpark",
    "alberta",
}

# Large project indicators
LARGE_PROJECT: list[str] = [
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
    "thigh piece",
    "rib piece",
    "ongoing project",
]

# Urgency signals
URGENCY: list[str] = [
    "asap",
    "as soon as possible",
    "this week",
    "this weekend",
    "today",
    "tomorrow",
    "need it done",
    "urgent",
    "cancellation",
    "walk in",
    "walk-in",
    "coming up",
    "before my",
    "deadline",
]

# Coverup-specific (stacks with project intent)
COVERUP_SPECIFIC: list[str] = [
    "cover up",
    "coverup",
    "cover-up",
    "bad tattoo",
    "regret",
    "blown out",
    "faded",
    "fix my tattoo",
    "unhappy with",
    "terrible tattoo",
    "tattoo removal",
    "redo",
    "rework",
]

# Memorial-specific (stacks with project intent)
MEMORIAL_SPECIFIC: list[str] = [
    "memorial",
    "tribute",
    "in memory",
    "lost my",
    "passed away",
    "honor ",
    "honour ",
    "remembrance",
    " rip ",
    "r.i.p",
    "rest in peace",
]

# Negative / noise signals
NOISE_PHRASES: list[str] = [
    "just got this",
    "just finished",
    "so happy with",
    "finally done",
    "healed up",
    "fresh ink",
    "new ink",
    "meme",
    "lol",
    "😂",
    "💀",
    "shitpost",
    "aftercare",
    "saniderm",
    "aquaphor",
    "second skin",
    "a&d ointment",
]

# Repeat collector
COLLECTOR_PHRASES: list[str] = [
    "my tattoos",
    "my collection",
    "adding to",
    "next tattoo",
    "another tattoo",
    "my sleeve",
    "continuing",
    "extending",
]


def _has_any(text: str, phrases: list[str]) -> bool:
    return any(p in text for p in phrases)


def _match_count(text: str, phrases: list[str]) -> int:
    return sum(1 for p in phrases if p in text)


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
    base_intent: int = 0
    geo_bonus: int = 0
    project_bonus: int = 0
    urgency_bonus: int = 0
    engagement_bonus: int = 0
    recency_bonus: int = 0
    collector_bonus: int = 0
    coverup_bonus: int = 0
    memorial_bonus: int = 0
    penalty: int = 0
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
    """Score a lead 1-100. Designed to surface high-value local buying intent."""

    text = f"{title} {body}".strip()
    t = text.lower()
    result = ScoreBreakdown()

    # =====================================================================
    # BASE INTENT (0-50)
    # =====================================================================
    buying_hits = _match_count(t, BUYING_INTENT)
    project_hits = _match_count(t, PROJECT_INTENT)
    moderate_hits = _match_count(t, MODERATE_INTENT)

    if buying_hits >= 2:
        result.base_intent = 50
    elif buying_hits == 1 and project_hits >= 1:
        result.base_intent = 48
    elif buying_hits == 1:
        result.base_intent = 42
    elif project_hits >= 2:
        result.base_intent = 40
    elif project_hits == 1 and moderate_hits >= 1:
        result.base_intent = 38
    elif project_hits == 1:
        result.base_intent = 35
    elif moderate_hits >= 2:
        result.base_intent = 32
    elif moderate_hits == 1:
        result.base_intent = 28
    else:
        # Weak / no signal
        result.base_intent = 8

    # Build keyword trigger label
    triggers: list[str] = []
    for p in BUYING_INTENT + PROJECT_INTENT + MODERATE_INTENT:
        if p in t and p not in triggers:
            triggers.append(p)
    result.keyword_trigger = "; ".join(triggers[:4]) if triggers else ""

    # Semantic label — priority ordered
    if _has_any(t, MEMORIAL_SPECIFIC):
        result.semantic_label = "memorial"
    elif _has_any(t, COVERUP_SPECIFIC) and not _has_any(t, ["aftercare"]):
        result.semantic_label = "coverup_help"
    elif _has_any(t, ["looking for artist", "recommend", "who does", "best tattoo", "iso tattoo", "anyone know"]):
        result.semantic_label = "looking_for_artist"
    elif "first tattoo" in t:
        result.semantic_label = "first_tattoo"
    elif _has_any(t, ["sleeve", "back piece", "chest piece", "leg sleeve"]):
        result.semantic_label = "large_project"
    elif _has_any(t, ["black and grey", "black and gray", "realism", "portrait", "japanese", "traditional", "geometric", "fine line", "dotwork"]):
        result.semantic_label = "style_research"
    elif _has_any(t, ["quote", "cost", "price", "how much"]):
        result.semantic_label = "pricing_inquiry"
    elif _has_any(t, ["touch up", "heal", "faded", "blown out"]):
        result.semantic_label = "touchup_need"
    elif buying_hits > 0 or project_hits > 0 or moderate_hits > 0:
        result.semantic_label = "general_intent"
    else:
        result.semantic_label = ""

    # =====================================================================
    # GEO BONUS (0-25)
    # Geo bonus scales with intent: buying intent gets full geo,
    # style/moderate intent gets reduced geo to avoid over-promoting
    # style research into the hot band.
    # =====================================================================
    sub_lower = subreddit.lower() if subreddit else ""
    sub_is_local = sub_lower in LOCAL_SUBREDDITS

    # Determine raw geo tier
    _geo_raw = 0
    if _has_any(t, GEO_EDMONTON) or sub_lower in {"edmonton", "yeg"}:
        _geo_raw = 25
        result.geo_estimate = "Edmonton"
        result.geo_confidence = "high"
    elif _has_any(t, GEO_METRO) or sub_lower in {"stalbert", "sherwoodpark"}:
        _geo_raw = 22
        result.geo_estimate = "Edmonton metro"
        result.geo_confidence = "high"
    elif sub_is_local and sub_lower == "alberta":
        _geo_raw = 15
        result.geo_estimate = "Alberta (subreddit)"
        result.geo_confidence = "medium"
    elif _has_any(t, ["alberta"]):
        _geo_raw = 15
        result.geo_estimate = "Alberta"
        result.geo_confidence = "medium"
    elif _has_any(t, GEO_ALBERTA):
        _geo_raw = 10
        result.geo_estimate = "Alberta region"
        result.geo_confidence = "low"
    else:
        _geo_raw = 0
        result.geo_estimate = ""
        result.geo_confidence = "none"

    # Scale: buying intent = full geo; project/moderate = 80%; weak = 60%
    if buying_hits >= 1:
        result.geo_bonus = _geo_raw
    elif project_hits >= 1 or moderate_hits >= 1:
        result.geo_bonus = int(_geo_raw * 0.80)
    else:
        result.geo_bonus = int(_geo_raw * 0.60)

    # =====================================================================
    # PROJECT SIZE BONUS (0-15)
    # =====================================================================
    proj_hits = _match_count(t, LARGE_PROJECT)
    if proj_hits >= 3:
        result.project_bonus = 15
    elif proj_hits == 2:
        result.project_bonus = 12
    elif proj_hits == 1:
        result.project_bonus = 8
    else:
        result.project_bonus = 0

    # =====================================================================
    # URGENCY BONUS (0-10)
    # =====================================================================
    urg_hits = _match_count(t, URGENCY)
    if urg_hits >= 2:
        result.urgency_bonus = 10
    elif urg_hits == 1:
        result.urgency_bonus = 6
    else:
        result.urgency_bonus = 0

    # =====================================================================
    # COVERUP BONUS (0-8) — stacks with base intent
    # =====================================================================
    cov_hits = _match_count(t, COVERUP_SPECIFIC)
    if cov_hits >= 3:
        result.coverup_bonus = 8
    elif cov_hits >= 2:
        result.coverup_bonus = 6
    elif cov_hits == 1:
        result.coverup_bonus = 4
    else:
        result.coverup_bonus = 0

    # =====================================================================
    # MEMORIAL BONUS (0-8) — stacks with base intent
    # =====================================================================
    mem_hits = _match_count(t, MEMORIAL_SPECIFIC)
    if mem_hits >= 2:
        result.memorial_bonus = 8
    elif mem_hits == 1:
        result.memorial_bonus = 5
    else:
        result.memorial_bonus = 0

    # =====================================================================
    # ENGAGEMENT BONUS (0-5)
    # =====================================================================
    ups = score_ups or 0
    coms = num_comments or 0
    eng = min((ups // 5) + (coms // 3), 5)
    result.engagement_bonus = eng

    # =====================================================================
    # RECENCY BONUS (0-8) — boost, not dominate
    # =====================================================================
    hours = _hours_since(created_at)
    if hours < 1:
        result.recency_bonus = 8
    elif hours < 3:
        result.recency_bonus = 6
    elif hours < 6:
        result.recency_bonus = 5
    elif hours < 12:
        result.recency_bonus = 4
    elif hours < 24:
        result.recency_bonus = 3
    elif hours < 48:
        result.recency_bonus = 2
    elif hours < 72:
        result.recency_bonus = 1
    else:
        result.recency_bonus = 0

    # =====================================================================
    # COLLECTOR BONUS (0-5)
    # =====================================================================
    col_hits = _match_count(t, COLLECTOR_PHRASES)
    result.collector_bonus = min(col_hits * 3, 5)

    # =====================================================================
    # PENALTIES
    # =====================================================================
    noise_hits = _match_count(t, NOISE_PHRASES)
    if noise_hits >= 3:
        result.penalty = 40
    elif noise_hits >= 2:
        result.penalty = 25
    elif noise_hits == 1:
        # Only penalize if there's no real intent signal
        if result.base_intent <= 25:
            result.penalty = 15
        else:
            result.penalty = 5

    # =====================================================================
    # TOTAL
    # =====================================================================
    raw = (
        result.base_intent
        + result.geo_bonus
        + result.project_bonus
        + result.urgency_bonus
        + result.coverup_bonus
        + result.memorial_bonus
        + result.engagement_bonus
        + result.recency_bonus
        + result.collector_bonus
        - result.penalty
    )
    result.total = max(min(raw, 100), 1)

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
