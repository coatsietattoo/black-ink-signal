"""Black Ink Signal — FastAPI backend."""

import os
import sys
from pathlib import Path

# Add packages to path so we can import core and connectors
_pkg_root = Path(__file__).resolve().parents[2] / "packages"
for p in [_pkg_root / "core", _pkg_root / "connectors" / "reddit"]:
    _p = str(p)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from black_ink_signal_core.database import get_engine, get_session_factory
from black_ink_signal_core.models import Lead, LeadEvent, SourceRun
from black_ink_signal_core.scoring import score_band
from black_ink_signal_core.enrichment import enrich_lead, enrich_all_pending
from black_ink_signal_core.classifier.pipeline import ClassifierPipeline
from black_ink_signal_core.notifications import get_recent_notifications, notify_hot_leads

app = FastAPI(title="Black Ink Signal", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_engine = get_engine()
_Session = get_session_factory(_engine)

# Classifier pipeline — rule-based always, LLM if BIS_LLM_API_KEY is set
_classifier = ClassifierPipeline(
    llm_api_key=os.environ.get("BIS_LLM_API_KEY"),
    llm_api_base=os.environ.get("BIS_LLM_API_BASE", "https://api.openai.com/v1"),
    llm_model=os.environ.get("BIS_LLM_MODEL", "gpt-4o-mini"),
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------

class LeadOut(BaseModel):
    id: int
    source: str
    source_item_id: str
    canonical_url: Optional[str]
    author_handle: Optional[str]
    title: Optional[str]
    body: Optional[str]
    subreddit: Optional[str]
    created_at: Optional[str]
    fetched_at: str
    lead_score: int
    lead_status: str
    geo_estimate: Optional[str]
    geo_confidence: Optional[str]
    keyword_trigger: Optional[str]
    semantic_label: Optional[str]
    booking_likelihood: Optional[int]
    project_size: Optional[str]
    tone: Optional[str]
    urgency: Optional[str]
    style_interest: Optional[str]
    outreach_angle: Optional[str]
    intent_summary: Optional[str]
    bookmarked: bool
    hidden: bool
    operator_notes: Optional[str]
    score_ups: Optional[int]
    num_comments: Optional[int]
    score_band: str

    class Config:
        from_attributes = True


def _lead_to_out(lead: Lead) -> LeadOut:
    return LeadOut(
        id=lead.id,
        source=lead.source,
        source_item_id=lead.source_item_id,
        canonical_url=lead.canonical_url,
        author_handle=lead.author_handle,
        title=lead.title,
        body=lead.body,
        subreddit=lead.subreddit,
        created_at=lead.created_at.isoformat() if lead.created_at else None,
        fetched_at=lead.fetched_at.isoformat() if lead.fetched_at else "",
        lead_score=lead.lead_score,
        lead_status=lead.lead_status,
        geo_estimate=lead.geo_estimate,
        geo_confidence=lead.geo_confidence,
        keyword_trigger=lead.keyword_trigger,
        semantic_label=lead.semantic_label,
        booking_likelihood=lead.booking_likelihood,
        project_size=lead.project_size,
        tone=lead.tone,
        urgency=lead.urgency,
        style_interest=lead.style_interest,
        outreach_angle=lead.outreach_angle,
        intent_summary=lead.intent_summary,
        bookmarked=lead.bookmarked,
        hidden=lead.hidden,
        operator_notes=lead.operator_notes,
        score_ups=lead.score_ups,
        num_comments=lead.num_comments,
        score_band=score_band(lead.lead_score),
    )


@app.get("/leads", response_model=list[LeadOut])
def list_leads(
    status: Optional[str] = None,
    min_score: int = 0,
    bookmarked_only: bool = False,
    include_hidden: bool = False,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
):
    with _Session() as s:
        q = s.query(Lead)
        if not include_hidden:
            q = q.filter(Lead.hidden == False)
        if status:
            q = q.filter(Lead.lead_status == status)
        if min_score > 0:
            q = q.filter(Lead.lead_score >= min_score)
        if bookmarked_only:
            q = q.filter(Lead.bookmarked == True)
        q = q.order_by(Lead.lead_score.desc(), Lead.fetched_at.desc())
        leads = q.offset(offset).limit(limit).all()
        return [_lead_to_out(l) for l in leads]


@app.get("/leads/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int):
    with _Session() as s:
        lead = s.get(Lead, lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        return _lead_to_out(lead)


# ---------------------------------------------------------------------------
# Status actions (manual review buttons)
# ---------------------------------------------------------------------------

class StatusUpdate(BaseModel):
    status: str  # new | reviewing | contacted | saved | dismissed


@app.patch("/leads/{lead_id}/status")
def update_lead_status(lead_id: int, body: StatusUpdate):
    valid = {"new", "reviewing", "contacted", "saved", "dismissed"}
    if body.status not in valid:
        raise HTTPException(400, f"Invalid status. Must be one of: {valid}")
    with _Session() as s:
        lead = s.get(Lead, lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        old = lead.lead_status
        lead.lead_status = body.status
        s.add(LeadEvent(lead_id=lead.id, event_type="status_change", payload_json={"old": old, "new": body.status}))
        s.commit()
        return {"id": lead_id, "old_status": old, "new_status": body.status}


class BookmarkUpdate(BaseModel):
    bookmarked: bool


@app.patch("/leads/{lead_id}/bookmark")
def update_bookmark(lead_id: int, body: BookmarkUpdate):
    with _Session() as s:
        lead = s.get(Lead, lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        lead.bookmarked = body.bookmarked
        s.commit()
        return {"id": lead_id, "bookmarked": body.bookmarked}


class NoteUpdate(BaseModel):
    notes: str


@app.patch("/leads/{lead_id}/notes")
def update_notes(lead_id: int, body: NoteUpdate):
    with _Session() as s:
        lead = s.get(Lead, lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        lead.operator_notes = body.notes
        s.commit()
        return {"id": lead_id, "notes": body.notes}


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

@app.post("/leads/{lead_id}/enrich")
def enrich_single(lead_id: int):
    with _Session() as s:
        lead = s.get(Lead, lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        ok = enrich_lead(s, lead_id, _classifier)
        s.refresh(lead)
        return {
            "id": lead_id,
            "enriched": ok,
            "intent_summary": lead.intent_summary,
            "booking_likelihood": lead.booking_likelihood,
            "tone": lead.tone,
            "urgency": lead.urgency,
            "project_size": lead.project_size,
            "style_interest": lead.style_interest,
            "outreach_angle": lead.outreach_angle,
        }


@app.post("/enrich/batch")
def enrich_batch(limit: int = Query(default=20, le=100)):
    with _Session() as s:
        count = enrich_all_pending(s, _classifier, limit=limit)
        return {"enriched": count}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.get("/search", response_model=list[LeadOut])
def search_leads(
    q: str = Query(..., min_length=1),
    min_score: int = 0,
    limit: int = Query(default=50, le=200),
):
    with _Session() as s:
        query = s.query(Lead).filter(Lead.hidden == False)
        if min_score > 0:
            query = query.filter(Lead.lead_score >= min_score)
        # SQLite LIKE search across title, body, keyword_trigger, author
        pattern = f"%{q}%"
        query = query.filter(
            (Lead.title.ilike(pattern)) |
            (Lead.body.ilike(pattern)) |
            (Lead.keyword_trigger.ilike(pattern)) |
            (Lead.author_handle.ilike(pattern)) |
            (Lead.semantic_label.ilike(pattern)) |
            (Lead.intent_summary.ilike(pattern))
        )
        query = query.order_by(Lead.lead_score.desc())
        leads = query.limit(limit).all()
        return [_lead_to_out(l) for l in leads]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.get("/export/csv")
def export_csv(
    min_score: int = 0,
    status: Optional[str] = None,
    bookmarked_only: bool = False,
):
    import csv
    import io
    from starlette.responses import StreamingResponse

    with _Session() as s:
        q = s.query(Lead).filter(Lead.hidden == False)
        if min_score > 0:
            q = q.filter(Lead.lead_score >= min_score)
        if status:
            q = q.filter(Lead.lead_status == status)
        if bookmarked_only:
            q = q.filter(Lead.bookmarked == True)
        q = q.order_by(Lead.lead_score.desc())
        leads = q.all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "score", "band", "status", "source", "subreddit", "author",
        "title", "geo", "geo_confidence", "keyword_trigger", "semantic_label",
        "intent_summary", "booking_likelihood", "project_size", "tone",
        "urgency", "style_interest", "outreach_angle", "bookmarked",
        "created_at", "url",
    ])
    for l in leads:
        writer.writerow([
            l.id, l.lead_score, score_band(l.lead_score), l.lead_status,
            l.source, l.subreddit, l.author_handle, l.title,
            l.geo_estimate, l.geo_confidence, l.keyword_trigger, l.semantic_label,
            l.intent_summary, l.booking_likelihood, l.project_size, l.tone,
            l.urgency, l.style_interest, l.outreach_angle, l.bookmarked,
            l.created_at.isoformat() if l.created_at else "", l.canonical_url,
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=black_ink_signal_leads.csv"},
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@app.get("/stats")
def stats():
    with _Session() as s:
        total = s.query(Lead).count()
        hot = s.query(Lead).filter(Lead.lead_score >= 80).count()
        strong = s.query(Lead).filter(Lead.lead_score >= 60, Lead.lead_score < 80).count()
        watchlist = s.query(Lead).filter(Lead.lead_score >= 40, Lead.lead_score < 60).count()
        return {"total": total, "hot": hot, "strong": strong, "watchlist": watchlist}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@app.get("/notifications")
def list_notifications(limit: int = Query(default=20, le=50)):
    return get_recent_notifications(limit=limit)


@app.post("/notifications/trigger")
def trigger_notifications():
    """Manually trigger hot lead notifications check."""
    with _Session() as s:
        sent = notify_hot_leads(s)
        return {"notifications_sent": sent}
