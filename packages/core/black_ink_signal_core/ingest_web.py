"""Web/forum ingestion pipeline for Black Ink Signal."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import Lead, LeadEvent, SourceRun
from .scoring import score_lead

logger = logging.getLogger("bis.ingest.web")

DOMAIN_CLASS_PENALTIES = {
    "search_result": 8,
    "forum": 0,
    "community_page": 0,
    "business_listing": 28,
    "competitor_site": 24,
    "social_public": 16,
    "irrelevant": 40,
}

STATIC_PAGE_PENALTY = 12
LISTICLE_PENALTY = 28
DIRECTORY_PENALTY = 28
RANKING_PENALTY = 24
SHOP_HOMEPAGE_PENALTY = 22
QUESTION_DISCUSSION_BONUS = 18
FORUM_DISCUSSION_BONUS = 22
RECOMMENDATION_DISCUSSION_BONUS = 20
TATTOO_PRIORITY_BONUS = 18
GENERIC_LOCAL_RECOMMENDATION_BONUS = 8
FORUM_SIGNAL_TEST_MIN_SCORE = 8
DEFAULT_MIN_SCORE = 20

STRONG_NEGATIVE_TERMS = [
    "best tattoo shops", "top 10", "expert recommendations", "directory", "listicle",
    "review roundup", "ranking article", "best in alberta", "best in edmonton",
]

SHOP_HOMEPAGE_TERMS = [
    "book now", "our artists", "our studio", "services", "gallery", "portfolio",
]

QUESTION_TERMS = ["can anyone", "any suggestions", "has anyone", "who does", "where can i", "anyone know", "does anyone know"]
RECOMMENDATION_TERMS = ["recommend", "recommendation", "recommendations", "experience with", "booked with", "has anyone used", "best place for"]
DISCUSSION_TERMS = ["forum", "thread", "discussion", "community", "comments", "reply", "replies", "question", "answers"]


def _score_adjustment(item) -> tuple[int, list[str], list[str]]:
    raw = item.raw or {}
    domain_class = raw.get("domain_class", "search_result")
    text = f"{item.title or ''} {item.body or ''}".lower()
    adjustment = -DOMAIN_CLASS_PENALTIES.get(domain_class, 0)
    bonus_reasons: list[str] = []
    penalty_reasons: list[str] = []
    if DOMAIN_CLASS_PENALTIES.get(domain_class, 0):
        penalty_reasons.append(f"domain_class:{domain_class}")

    if any(term in text for term in STRONG_NEGATIVE_TERMS):
        if "directory" in text:
            adjustment -= DIRECTORY_PENALTY
            penalty_reasons.append("directory")
        if any(t in text for t in ["best tattoo shops", "top 10", "best in alberta", "best in edmonton"]):
            adjustment -= LISTICLE_PENALTY
            penalty_reasons.append("listicle")
        if any(t in text for t in ["ranking article", "expert recommendations", "review roundup"]):
            adjustment -= RANKING_PENALTY
            penalty_reasons.append("ranking_page")

    if any(term in text for term in SHOP_HOMEPAGE_TERMS):
        adjustment -= SHOP_HOMEPAGE_PENALTY
        penalty_reasons.append("shop_homepage")

    if item.created_at is not None:
        try:
            age_days = max((datetime.now(timezone.utc) - item.created_at).days, 0)
            if age_days > 365:
                adjustment -= STATIC_PAGE_PENALTY
                penalty_reasons.append("old_static")
        except Exception:
            pass

    if domain_class in {"forum", "community_page"} and any(term in text for term in DISCUSSION_TERMS):
        adjustment += FORUM_DISCUSSION_BONUS
        bonus_reasons.append("forum_discussion")

    if any(term in text for term in QUESTION_TERMS):
        adjustment += QUESTION_DISCUSSION_BONUS
        bonus_reasons.append("question_signal")

    if any(term in text for term in RECOMMENDATION_TERMS):
        adjustment += RECOMMENDATION_DISCUSSION_BONUS
        bonus_reasons.append("recommendation_discussion")

    if raw.get("kind") == "forum_thread":
        adjustment += GENERIC_LOCAL_RECOMMENDATION_BONUS
        bonus_reasons.append("generic_local_recommendation")

    if raw.get("is_tattoo_related"):
        adjustment += TATTOO_PRIORITY_BONUS
        bonus_reasons.append("tattoo_priority")

    return adjustment, bonus_reasons, penalty_reasons


def _min_score_for_item(item) -> int:
    raw = item.raw or {}
    if raw.get("kind") == "forum_thread":
        return FORUM_SIGNAL_TEST_MIN_SCORE
    return DEFAULT_MIN_SCORE


def _build_debug_payload(item, base_score: int, bonus_reasons: list[str], penalty_reasons: list[str], final_score: int) -> dict:
    raw = dict(item.raw or {})
    raw["base_score"] = base_score
    raw["bonus_reasons"] = bonus_reasons
    raw["penalty_reasons"] = penalty_reasons
    raw["final_score"] = final_score
    return raw


def ingest_web_items(session: Session, items: list, source_run: SourceRun | None = None) -> dict:
    """Ingest normalized WebItem objects into the leads table.

    Returns stats dict: {seen, added, updated, skipped}.
    """
    stats = {"seen": 0, "added": 0, "updated": 0, "skipped": 0}

    for item in items:
        stats["seen"] += 1
        dedupe_key = item.dedupe_key

        existing = session.query(Lead).filter_by(dedupe_key=dedupe_key).first()
        if existing is not None:
            updated = False
            new_title = item.title or existing.title
            new_body = item.body or existing.body
            new_created = item.created_at or existing.created_at
            if new_title != existing.title:
                existing.title = new_title
                updated = True
            if new_body != existing.body:
                existing.body = new_body
                updated = True
            if (item.canonical_url or "") and item.canonical_url != existing.canonical_url:
                existing.canonical_url = item.canonical_url
                updated = True
            if new_created and new_created != existing.created_at:
                existing.created_at = new_created
                updated = True
            if updated:
                breakdown = score_lead(
                    title=existing.title or "",
                    body=existing.body or "",
                    subreddit=existing.subreddit or "",
                    created_at=existing.created_at,
                    score_ups=existing.score_ups,
                    num_comments=existing.num_comments,
                )
                adjustment, bonus_reasons, penalty_reasons = _score_adjustment(item)
                old_score = existing.lead_score
                final_score = max(breakdown.total + adjustment, 1)
                existing.lead_score = final_score
                existing.geo_estimate = breakdown.geo_estimate
                existing.geo_confidence = breakdown.geo_confidence
                existing.keyword_trigger = breakdown.keyword_trigger
                existing.semantic_label = breakdown.semantic_label
                existing.fetched_at = datetime.now(timezone.utc)
                existing.raw_payload = _build_debug_payload(item, breakdown.total, bonus_reasons, penalty_reasons, final_score)
                session.add(LeadEvent(
                    lead_id=existing.id,
                    event_type="score_update",
                    payload_json={"old": old_score, "new": existing.lead_score, "source": existing.source},
                ))
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
            continue

        breakdown = score_lead(
            title=item.title,
            body=item.body,
            subreddit=item.forum,
            created_at=item.created_at,
            score_ups=0,
            num_comments=0,
        )
        adjustment, bonus_reasons, penalty_reasons = _score_adjustment(item)
        final_score = max(breakdown.total + adjustment, 1)

        if final_score < _min_score_for_item(item):
            stats["skipped"] += 1
            continue

        lead = Lead(
            source=item.source,
            source_item_id=item.item_id,
            canonical_url=item.canonical_url or item.url,
            author_handle=item.author or None,
            title=item.title,
            body=item.body,
            subreddit=item.forum or None,
            created_at=item.created_at,
            fetched_at=datetime.now(timezone.utc),
            lead_score=final_score,
            lead_status="new",
            geo_estimate=breakdown.geo_estimate,
            geo_confidence=breakdown.geo_confidence,
            keyword_trigger=breakdown.keyword_trigger,
            semantic_label=breakdown.semantic_label,
            dedupe_key=dedupe_key,
            score_ups=0,
            num_comments=0,
            raw_payload=_build_debug_payload(item, breakdown.total, bonus_reasons, penalty_reasons, final_score),
        )
        session.add(lead)
        session.flush()

        session.add(LeadEvent(
            lead_id=lead.id,
            event_type="created",
            payload_json={"score": final_score, "source": item.source},
        ))
        stats["added"] += 1

    session.commit()

    if source_run:
        source_run.items_seen = stats["seen"]
        source_run.items_added = stats["added"]
        source_run.items_updated = stats["updated"]
        source_run.status = "success"
        source_run.finished_at = datetime.now(timezone.utc)
        session.commit()

    logger.info(f"Web ingest complete: {stats}")
    return stats
