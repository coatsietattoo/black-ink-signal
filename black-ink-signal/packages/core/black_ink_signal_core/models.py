"""SQLAlchemy models for Black Ink Signal."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, JSON,
    ForeignKey, Index, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(64), nullable=False, index=True)
    source_item_id = Column(String(256), nullable=False)
    canonical_url = Column(Text, nullable=True)
    author_handle = Column(String(256), nullable=True)
    author_display_name = Column(String(256), nullable=True)
    title = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    parent_context = Column(Text, nullable=True)
    subreddit = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Scoring
    lead_score = Column(Integer, nullable=False, default=0)
    lead_status = Column(String(32), nullable=False, default="new")  # new | reviewing | contacted | saved | dismissed
    geo_estimate = Column(String(128), nullable=True)
    geo_confidence = Column(String(16), nullable=True)  # high | medium | low | none
    keyword_trigger = Column(String(256), nullable=True)
    semantic_label = Column(String(128), nullable=True)

    # AI enrichment (nullable until enrichment runs)
    booking_likelihood = Column(Integer, nullable=True)
    project_size = Column(String(32), nullable=True)
    tone = Column(String(64), nullable=True)
    urgency = Column(String(32), nullable=True)
    style_interest = Column(String(128), nullable=True)
    outreach_angle = Column(Text, nullable=True)
    intent_summary = Column(Text, nullable=True)

    # Operator actions
    bookmarked = Column(Boolean, nullable=False, default=False)
    hidden = Column(Boolean, nullable=False, default=False)
    operator_notes = Column(Text, nullable=True)
    booked_value = Column(String(64), nullable=True)  # small|half_day|full_day|sleeve_project|custom:NNN

    # Dedup
    dedupe_key = Column(String(512), nullable=False, unique=True)

    # Engagement
    score_ups = Column(Integer, nullable=True)
    num_comments = Column(Integer, nullable=True)

    # Raw payload ref
    raw_payload = Column(JSON, nullable=True)

    events = relationship("LeadEvent", back_populates="lead", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_leads_score_status", "lead_score", "lead_status"),
        Index("ix_leads_source_item", "source", "source_item_id"),
    )


class LeadEvent(Base):
    __tablename__ = "lead_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)  # status_change | score_update | enrichment | note
    payload_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    lead = relationship("Lead", back_populates="events")


class SourceRun(Base):
    __tablename__ = "source_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(64), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=False, default="running")  # running | success | error
    items_seen = Column(Integer, nullable=False, default=0)
    items_added = Column(Integer, nullable=False, default=0)
    items_updated = Column(Integer, nullable=False, default=0)
    errors = Column(Text, nullable=True)
    checkpoint = Column(Text, nullable=True)


def init_db(db_path: str = "data/black_ink_signal.db"):
    """Create engine and bootstrap all tables."""
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    return engine
