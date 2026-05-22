"""Enrichment worker — runs classification pipeline on leads that need it."""

from __future__ import annotations
import logging
from typing import Optional

from sqlalchemy.orm import Session

from .models import Lead, LeadEvent
from .classifier.pipeline import ClassifierPipeline

logger = logging.getLogger("bis.enrichment")


def enrich_lead(db_session: Session, lead_id: int, pipeline: ClassifierPipeline) -> bool:
    """Run AI classification on a single lead and store results."""
    lead = db_session.get(Lead, lead_id)
    if not lead:
        logger.warning(f"Lead {lead_id} not found")
        return False

    metadata = {
        "subreddit": lead.subreddit or "",
        "geo_estimate": lead.geo_estimate or "",
        "source": lead.source,
        "score_ups": lead.score_ups,
        "num_comments": lead.num_comments,
    }

    result = pipeline.classify(lead.title or "", lead.body or "", metadata)

    # Store results
    lead.intent_summary = result.intent_summary
    lead.booking_likelihood = result.booking_likelihood
    lead.project_size = result.project_size
    lead.tone = result.tone
    lead.urgency = result.urgency
    lead.style_interest = result.style_interest
    lead.outreach_angle = result.outreach_angle

    # Log enrichment event
    db_session.add(LeadEvent(
        lead_id=lead.id,
        event_type="enrichment",
        payload_json={
            "classifier": "pipeline",
            "confidence": result.confidence,
            "reason_codes": result.reason_codes,
            "booking_likelihood": result.booking_likelihood,
        },
    ))

    db_session.commit()
    logger.info(f"Enriched lead {lead_id}: likelihood={result.booking_likelihood}, tone={result.tone}, urgency={result.urgency}")
    return True


def enrich_all_pending(db_session: Session, pipeline: ClassifierPipeline, limit: int = 50) -> int:
    """Enrich all leads that haven't been classified yet."""
    leads = (
        db_session.query(Lead)
        .filter(Lead.intent_summary.is_(None))
        .filter(Lead.hidden == False)
        .order_by(Lead.lead_score.desc())
        .limit(limit)
        .all()
    )

    enriched = 0
    for lead in leads:
        if enrich_lead(db_session, lead.id, pipeline):
            enriched += 1

    logger.info(f"Enriched {enriched}/{len(leads)} pending leads")
    return enriched
