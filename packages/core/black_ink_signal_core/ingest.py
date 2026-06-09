"""Ingestion pipeline — takes raw connector items, scores, deduplicates, and stores them."""

from __future__ import annotations
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import Lead, LeadEvent, SourceRun
from .scoring import score_lead, ScoreBreakdown

logger = logging.getLogger("bis.ingest")


def ingest_reddit_items(session: Session, items: list, source_run: SourceRun | None = None) -> dict:
    """Ingest a list of RedditItem objects into the leads table.

    Returns stats dict: {seen, added, updated, skipped}.
    """
    stats = {"seen": 0, "added": 0, "updated": 0, "skipped": 0}

    for item in items:
        stats["seen"] += 1
        dedupe_key = f"reddit:{item.item_id}"

        existing = session.query(Lead).filter_by(dedupe_key=dedupe_key).first()
        if existing is not None:
            # Update score if engagement changed
            if (item.score != existing.score_ups) or (item.num_comments != existing.num_comments):
                breakdown = score_lead(
                    title=item.title,
                    body=item.body,
                    subreddit=item.subreddit,
                    created_at=item.created_at,
                    score_ups=item.score,
                    num_comments=item.num_comments,
                )
                old_score = existing.lead_score
                existing.lead_score = breakdown.total
                existing.score_ups = item.score
                existing.num_comments = item.num_comments
                if old_score != breakdown.total:
                    session.add(LeadEvent(
                        lead_id=existing.id,
                        event_type="score_update",
                        payload_json={"old": old_score, "new": breakdown.total},
                    ))
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
            continue

        # New lead — score it
        breakdown = score_lead(
            title=item.title,
            body=item.body,
            subreddit=item.subreddit,
            created_at=item.created_at,
            score_ups=item.score,
            num_comments=item.num_comments,
        )

        # Skip very low-signal items
        if breakdown.total < 5:
            stats["skipped"] += 1
            continue

        lead = Lead(
            source="reddit",
            source_item_id=item.item_id,
            canonical_url=item.canonical_url,
            author_handle=item.author,
            title=item.title,
            body=item.body,
            subreddit=item.subreddit,
            created_at=item.created_at,
            fetched_at=datetime.now(timezone.utc),
            lead_score=breakdown.total,
            lead_status="new",
            geo_estimate=breakdown.geo_estimate,
            geo_confidence=breakdown.geo_confidence,
            keyword_trigger=breakdown.keyword_trigger,
            semantic_label=breakdown.semantic_label,
            dedupe_key=dedupe_key,
            score_ups=item.score,
            num_comments=item.num_comments,
            raw_payload=item.raw if item.raw else None,
        )
        session.add(lead)
        session.flush()  # get lead.id for event

        session.add(LeadEvent(
            lead_id=lead.id,
            event_type="created",
            payload_json={"score": breakdown.total, "source": "reddit"},
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

    logger.info(f"Ingest complete: {stats}")
    return stats
