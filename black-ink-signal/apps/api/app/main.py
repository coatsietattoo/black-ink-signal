"""Black Ink Signal — FastAPI backend."""

import os
import sys
import csv
import io
from pathlib import Path
from datetime import datetime, timezone, timedelta

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
from black_ink_signal_core.ingest import ingest_reddit_items
from black_ink_signal_core.scoring import score_lead as _score_lead_fn

app = FastAPI(title="Black Ink Signal", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_engine = get_engine()
_Session = get_session_factory(_engine)

# Auto-migrate: add booked_value column if missing
try:
    import sqlalchemy as _sa
    with _engine.connect() as _conn:
        _cols = [row[1] for row in _conn.execute(_sa.text("PRAGMA table_info(leads)")).fetchall()]
        if "booked_value" not in _cols:
            _conn.execute(_sa.text("ALTER TABLE leads ADD COLUMN booked_value TEXT"))
            _conn.commit()
except Exception:
    pass

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
    booked_value: Optional[str]
    score_ups: Optional[int]
    num_comments: Optional[int]
    score_band: str
    score_breakdown: Optional[dict]

    class Config:
        from_attributes = True


def _lead_to_out(lead: Lead) -> LeadOut:
    # Compute live score breakdown
    breakdown = _score_lead_fn(
        title=lead.title or "",
        body=lead.body or "",
        subreddit=lead.subreddit or "",
        created_at=lead.created_at,
        score_ups=lead.score_ups,
        num_comments=lead.num_comments,
    )
    breakdown_dict = {
        "base_intent": breakdown.base_intent,
        "geo_bonus": breakdown.geo_bonus,
        "project_bonus": breakdown.project_bonus,
        "urgency_bonus": breakdown.urgency_bonus,
        "engagement_bonus": breakdown.engagement_bonus,
        "recency_bonus": breakdown.recency_bonus,
        "collector_bonus": breakdown.collector_bonus,
        "coverup_bonus": breakdown.coverup_bonus,
        "memorial_bonus": breakdown.memorial_bonus,
        "penalty": breakdown.penalty,
        "total": breakdown.total,
        "keyword_trigger": breakdown.keyword_trigger,
        "semantic_label": breakdown.semantic_label,
        "geo_estimate": breakdown.geo_estimate,
        "geo_confidence": breakdown.geo_confidence,
    }

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
        booked_value=lead.booked_value,
        score_ups=lead.score_ups,
        num_comments=lead.num_comments,
        score_band=score_band(lead.lead_score),
        score_breakdown=breakdown_dict,
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
    valid = {"new", "reviewing", "contacted", "saved", "dismissed", "bad_match", "booked", "follow_up"}
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


@app.get("/stats/daily")
def daily_summary():
    """Daily summary: leads today, top sources, top keywords, status breakdown."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    with _Session() as s:
        # Leads fetched today
        today_leads = s.query(Lead).filter(Lead.fetched_at >= today_start).all()

        hot_today = [l for l in today_leads if l.lead_score >= 80]
        strong_today = [l for l in today_leads if 60 <= l.lead_score < 80]

        # Status breakdown (all leads)
        all_leads = s.query(Lead).filter(Lead.hidden == False).all()
        status_counts = {}
        for l in all_leads:
            status_counts[l.lead_status] = status_counts.get(l.lead_status, 0) + 1

        # Top keywords today
        keyword_counts: dict[str, int] = {}
        for l in today_leads:
            if l.keyword_trigger:
                for kw in l.keyword_trigger.split(";"):
                    kw = kw.strip()
                    if kw:
                        keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        top_keywords = sorted(keyword_counts.items(), key=lambda x: -x[1])[:10]

        # Top subreddits today
        sub_counts: dict[str, int] = {}
        for l in today_leads:
            if l.subreddit:
                sub_counts[l.subreddit] = sub_counts.get(l.subreddit, 0) + 1
        top_sources = sorted(sub_counts.items(), key=lambda x: -x[1])[:5]

        # Semantic labels today
        label_counts: dict[str, int] = {}
        for l in today_leads:
            if l.semantic_label:
                label_counts[l.semantic_label] = label_counts.get(l.semantic_label, 0) + 1
        top_intents = sorted(label_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "date": today_start.strftime("%Y-%m-%d"),
        "leads_today": len(today_leads),
        "hot_today": len(hot_today),
        "strong_today": len(strong_today),
        "status_breakdown": status_counts,
        "top_keywords": [{"keyword": k, "count": v} for k, v in top_keywords],
        "top_sources": [{"source": k, "count": v} for k, v in top_sources],
        "top_intents": [{"intent": k, "count": v} for k, v in top_intents],
    }


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


# ---------------------------------------------------------------------------
# Source Health
# ---------------------------------------------------------------------------

@app.get("/sources/health")
def source_health():
    """Return health status for all configured sources."""
    reddit_oauth = bool(
        os.environ.get("BIS_REDDIT_CLIENT_ID") and
        os.environ.get("BIS_REDDIT_CLIENT_SECRET")
    )

    with _Session() as s:
        # Last Reddit run
        last_run = (
            s.query(SourceRun)
            .filter(SourceRun.source == "reddit")
            .order_by(SourceRun.started_at.desc())
            .first()
        )

        # Recent runs (last 24h)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_runs = (
            s.query(SourceRun)
            .filter(SourceRun.source == "reddit", SourceRun.started_at >= cutoff)
            .all()
        )

        total_added_24h = sum(r.items_added or 0 for r in recent_runs)
        total_errors_24h = sum(1 for r in recent_runs if r.status == "error")

        # Enrichment status
        unenriched = s.query(Lead).filter(Lead.intent_summary.is_(None), Lead.hidden == False).count()
        total_leads = s.query(Lead).count()

    return {
        "reddit": {
            "oauth_configured": reddit_oauth,
            "connector_mode": "oauth" if reddit_oauth else "public_json",
            "last_fetch": last_run.started_at.isoformat() if last_run else None,
            "last_fetch_status": last_run.status if last_run else None,
            "last_fetch_items_seen": last_run.items_seen if last_run else 0,
            "last_fetch_items_added": last_run.items_added if last_run else 0,
            "last_fetch_errors": last_run.errors if last_run else None,
            "runs_24h": len(recent_runs),
            "added_24h": total_added_24h,
            "errors_24h": total_errors_24h,
        },
        "enrichment": {
            "llm_configured": bool(os.environ.get("BIS_LLM_API_KEY")),
            "mode": "llm+rules" if os.environ.get("BIS_LLM_API_KEY") else "rules_only",
            "pending": unenriched,
        },
        "scheduler": {
            "reddit_interval_min": int(os.environ.get("BIS_REDDIT_INTERVAL", "5")),
            "enrichment_interval_min": int(os.environ.get("BIS_ENRICHMENT_INTERVAL", "2")),
        },
        "database": {
            "total_leads": total_leads,
        },
    }


# ---------------------------------------------------------------------------
# Admin Actions
# ---------------------------------------------------------------------------

@app.post("/admin/fetch-reddit")
def admin_fetch_reddit():
    """Manually trigger a Reddit fetch now."""
    try:
        from connector import RedditConnector
        try:
            from oauth_connector import RedditOAuthConnector
        except ImportError:
            RedditOAuthConnector = None

        cid = os.environ.get("BIS_REDDIT_CLIENT_ID", "")
        csec = os.environ.get("BIS_REDDIT_CLIENT_SECRET", "")
        uname = os.environ.get("BIS_REDDIT_USERNAME", "")
        pwd = os.environ.get("BIS_REDDIT_PASSWORD", "")

        if cid and csec and uname and pwd and RedditOAuthConnector:
            connector = RedditOAuthConnector(
                client_id=cid, client_secret=csec,
                username=uname, password=pwd,
                user_agent=os.environ.get("BIS_REDDIT_USER_AGENT", "BlackInkSignal/0.1"),
            )
        else:
            connector = RedditConnector()

        items = connector.fetch_all_new()
        connector.close()

        with _Session() as session:
            run = SourceRun(source="reddit")
            session.add(run)
            session.commit()
            stats = ingest_reddit_items(session, items, source_run=run)

        return {"status": "ok", "items_fetched": len(items), **stats}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/admin/enrich")
def admin_enrich(limit: int = Query(default=50, le=200)):
    """Manually trigger enrichment batch."""
    with _Session() as s:
        count = enrich_all_pending(s, _classifier, limit=limit)
        return {"enriched": count}


@app.post("/admin/seed")
def admin_seed():
    """Seed demo leads into the database."""
    import importlib.util
    seed_path = Path(__file__).parent / "seed_data.py"
    spec = importlib.util.spec_from_file_location("seed_data", seed_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.seed()
    with _Session() as s:
        total = s.query(Lead).count()
    return {"status": "ok", "total_leads": total}


@app.post("/admin/rescore")
def admin_rescore():
    """Rescore all leads with current scoring engine."""
    updated = 0
    with _Session() as s:
        leads = s.query(Lead).all()
        for lead in leads:
            r = _score_lead_fn(
                title=lead.title or "",
                body=lead.body or "",
                subreddit=lead.subreddit or "",
                created_at=lead.created_at,
                score_ups=lead.score_ups,
                num_comments=lead.num_comments,
            )
            if lead.lead_score != r.total:
                lead.lead_score = r.total
                lead.geo_estimate = r.geo_estimate
                lead.geo_confidence = r.geo_confidence
                lead.keyword_trigger = r.keyword_trigger
                lead.semantic_label = r.semantic_label
                updated += 1
        s.commit()
    return {"rescored": len(leads), "changed": updated}


@app.delete("/admin/clear-demo")
def admin_clear_demo():
    """Remove all seed/demo leads (source_item_id starts with t3_seed_)."""
    with _Session() as s:
        demo_leads = s.query(Lead).filter(Lead.source_item_id.like("t3_seed_%")).all()
        count = len(demo_leads)
        for lead in demo_leads:
            s.delete(lead)
        s.commit()
    return {"deleted": count}


@app.delete("/admin/clear-all")
def admin_clear_all():
    """Delete ALL leads. Use with caution."""
    with _Session() as s:
        count = s.query(Lead).count()
        s.query(LeadEvent).delete()
        s.query(Lead).delete()
        s.query(SourceRun).delete()
        s.commit()
    return {"deleted": count}


@app.get("/admin/dedup-report")
def dedup_report():
    """Show how deduplication works and current stats."""
    with _Session() as s:
        total_leads = s.query(Lead).count()
        unique_sources = s.query(Lead.source_item_id).distinct().count()

        # Count skipped items from recent source runs
        recent_runs = (
            s.query(SourceRun)
            .filter(SourceRun.source == "reddit")
            .order_by(SourceRun.started_at.desc())
            .limit(20)
            .all()
        )
        total_seen = sum(r.items_seen or 0 for r in recent_runs)
        total_added = sum(r.items_added or 0 for r in recent_runs)
        total_updated = sum(r.items_updated or 0 for r in recent_runs)
        total_skipped = total_seen - total_added - total_updated

    return {
        "method": "dedupe_key = source:item_id (e.g. reddit:t3_abc123)",
        "description": "Each lead has a unique dedupe_key. On ingestion, if a lead with the same key exists: "
                        "if engagement changed, the score is recalculated (counted as 'updated'); "
                        "otherwise the item is skipped. Items scoring below 5 are filtered out entirely.",
        "database": {
            "total_leads": total_leads,
            "unique_source_ids": unique_sources,
        },
        "recent_runs": {
            "runs_checked": len(recent_runs),
            "total_seen": total_seen,
            "total_added": total_added,
            "total_updated": total_updated,
            "total_skipped": total_skipped,
            "dedup_rate": f"{(total_skipped / total_seen * 100):.1f}%" if total_seen > 0 else "n/a",
        },
    }


# ---------------------------------------------------------------------------
# Contact Script Generator
# ---------------------------------------------------------------------------

def _generate_scripts(lead) -> dict:
    """Generate 3 human-written reply options for a lead (rule-based, no LLM needed)."""
    name = lead.author_handle or "there"
    title = lead.title or ""
    label = (lead.semantic_label or "").lower()
    city = lead.geo_estimate or "your area"
    style = lead.style_interest or "your style"
    project = lead.project_size or "your project"

    # Determine context tokens
    is_coverup = "coverup" in label or "cover" in title.lower()
    is_memorial = "memorial" in label or "memorial" in title.lower() or "tribute" in title.lower()
    is_first = "first" in label or "first tattoo" in title.lower()
    is_sleeve = "sleeve" in title.lower() or "large" in label
    is_seeking = "looking" in label or "artist" in label or "seeking" in label

    # Build context-aware scripts
    if is_memorial:
        soft = (f"Hey {name}, I saw your post about the memorial piece. That kind of work is really personal "
                f"and I'd want to make sure it's done right. Happy to chat about ideas whenever you're ready — no rush.")
        direct = (f"Hi {name}, memorial tattoos are something I take a lot of care with. I'd love to sit down "
                  f"and talk through your vision. Want to set up a free consultation?")
        casual = (f"Yo {name}, just saw your post. Memorial pieces are some of my favorite work to do — "
                  f"there's something about getting that story right on skin. Hit me up if you want to talk designs.")
    elif is_coverup:
        soft = (f"Hey {name}, I noticed you're looking into a cover-up. Those can be tricky but also really "
                f"rewarding when done right. I've done a few similar pieces — happy to take a look if you want.")
        direct = (f"Hi {name}, cover-ups are a specialty of mine. I can usually work with most existing pieces. "
                  f"Send me a photo and I'll give you honest feedback on what's possible.")
        casual = (f"Yo {name}, cover-ups are actually my jam. The puzzle of turning something old into something "
                  f"great is half the fun. Drop me a pic and let's figure it out.")
    elif is_first:
        soft = (f"Hey {name}, congrats on thinking about your first tattoo! It's totally normal to have a ton of questions. "
                f"I'm around if you want to talk through sizing, placement, style — whatever's on your mind.")
        direct = (f"Hi {name}, first tattoos are exciting! I've walked a lot of people through their first piece. "
                  f"Happy to do a quick free consult to help you figure out exactly what you want.")
        casual = (f"Yo {name}, first tattoo hype! Everyone's nervous before their first one and then they're "
                  f"already planning the second one by the time they leave. Let's make it a good one.")
    elif is_sleeve:
        soft = (f"Hey {name}, saw your post about the sleeve. Big projects like that are my favorite — "
                f"there's room to really build something that flows. Happy to chat about concepts.")
        direct = (f"Hi {name}, I specialize in larger pieces and full sleeves. Let's set up a consultation "
                  f"to map out the design, timeline, and sessions. No commitment.")
        casual = (f"Yo {name}, a full sleeve? Now we're talking. That's the kind of project I live for. "
                  f"Let's grab a coffee and sketch some ideas.")
    elif is_seeking:
        soft = (f"Hey {name}, I saw you're looking for an artist in {city}. I'd love to chat about "
                f"what you have in mind — always happy to show portfolio work that matches your vibe.")
        direct = (f"Hi {name}, I'm an artist based in {city} and your project sounds like a great fit. "
                  f"Check out my portfolio and let me know if you'd like to set up a consultation.")
        casual = (f"Yo {name}, artist in {city} here 👋 Saw your post and your idea sounds sick. "
                  f"Check my work and hit me up if it vibes.")
    else:
        soft = (f"Hey {name}, I came across your post and it sounds like you have a cool idea in mind. "
                f"I'd be happy to chat about it — no pressure, just seeing if I can help.")
        direct = (f"Hi {name}, I'm a tattoo artist in {city} and I think I could do great work on what you're describing. "
                  f"Want to set up a quick consultation?")
        casual = (f"Yo {name}, just spotted your post. Sounds like a fun project — "
                  f"I'm always down to talk tattoo ideas. DM me if you want to jam on it.")

    return {
        "soft": {"label": "Soft / Helpful", "text": soft},
        "direct": {"label": "Direct Consultation", "text": direct},
        "casual": {"label": "Funny / Casual", "text": casual},
    }


@app.get("/leads/{lead_id}/scripts")
def lead_scripts(lead_id: int):
    """Generate 3 contact script options for a lead."""
    with _Session() as s:
        lead = s.query(Lead).filter_by(id=lead_id).first()
        if not lead:
            raise HTTPException(404, "Lead not found")
        return _generate_scripts(lead)


# ---------------------------------------------------------------------------
# Booked Value
# ---------------------------------------------------------------------------

VALID_BOOKED_VALUES = {"small", "half_day", "full_day", "sleeve_project"}


class BookedValueUpdate(BaseModel):
    value: str  # small|half_day|full_day|sleeve_project|custom:NNN


@app.patch("/leads/{lead_id}/booked-value")
def update_booked_value(lead_id: int, body: BookedValueUpdate):
    """Set estimated value when a lead is booked."""
    val = body.value.strip()
    # Validate
    if val not in VALID_BOOKED_VALUES and not val.startswith("custom:"):
        raise HTTPException(400, f"Invalid value. Use: {', '.join(sorted(VALID_BOOKED_VALUES))} or custom:<amount>")
    if val.startswith("custom:"):
        try:
            int(val.split(":", 1)[1])
        except ValueError:
            raise HTTPException(400, "Custom value must be custom:<integer_amount>")

    with _Session() as s:
        lead = s.query(Lead).filter_by(id=lead_id).first()
        if not lead:
            raise HTTPException(404, "Lead not found")
        lead.booked_value = val
        s.add(LeadEvent(
            lead_id=lead_id,
            event_type="booked_value",
            payload_json={"value": val},
        ))
        s.commit()
    return {"id": lead_id, "booked_value": val}


@app.get("/stats/revenue")
def revenue_stats():
    """Revenue summary from booked leads."""
    VALUE_MAP = {
        "small": 150,
        "half_day": 500,
        "full_day": 1000,
        "sleeve_project": 3000,
    }
    with _Session() as s:
        booked = s.query(Lead).filter(Lead.lead_status == "booked", Lead.booked_value.isnot(None)).all()
        total_value = 0
        breakdown = {}
        for lead in booked:
            val = lead.booked_value
            if val in VALUE_MAP:
                amount = VALUE_MAP[val]
            elif val.startswith("custom:"):
                amount = int(val.split(":", 1)[1])
            else:
                amount = 0
            total_value += amount
            breakdown[val] = breakdown.get(val, 0) + 1

        return {
            "booked_count": len(booked),
            "estimated_revenue": total_value,
            "breakdown": breakdown,
            "value_map": VALUE_MAP,
        }


# ---------------------------------------------------------------------------
# Backup / Export
# ---------------------------------------------------------------------------

from fastapi.responses import FileResponse
import shutil


@app.post("/admin/backup")
def backup_database():
    """Create a timestamped backup of the SQLite database."""
    proj_root = Path(__file__).resolve().parents[3]
    db_rel = os.environ.get("BIS_DB_PATH", "data/black_ink_signal.db")
    db_path = proj_root / db_rel
    if not db_path.exists():
        db_path = Path(db_rel)  # Try as absolute / CWD-relative
    if not db_path.exists():
        raise HTTPException(404, "Database file not found")

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"black_ink_signal_{ts}.db"
    shutil.copy2(str(db_path), str(backup_path))

    # Clean old backups (keep last 10)
    backups = sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[10:]:
        old.unlink()

    return {
        "status": "ok",
        "backup_path": str(backup_path),
        "backup_size_kb": round(backup_path.stat().st_size / 1024, 1),
        "backups_kept": min(len(backups), 10),
    }


@app.get("/admin/backup/download")
def download_database():
    """Download the current database file."""
    proj_root = Path(__file__).resolve().parents[3]
    db_rel = os.environ.get("BIS_DB_PATH", "data/black_ink_signal.db")
    db_path = proj_root / db_rel
    if not db_path.exists():
        db_path = Path(db_rel)
    if not db_path.exists():
        raise HTTPException(404, "Database file not found")
    return FileResponse(
        str(db_path),
        media_type="application/x-sqlite3",
        filename=f"black_ink_signal_{datetime.now(timezone.utc).strftime('%Y%m%d')}.db",
    )
