"""Background scheduler for Black Ink Signal.

Runs source ingestion on a configurable interval.
Uses APScheduler for reliability and clean shutdown.
Designed for single-process desktop mode.
"""

from __future__ import annotations
import os
import sys
import logging
import signal
from pathlib import Path
from datetime import datetime, timezone

# Path setup
_pkg_root = Path(__file__).resolve().parents[2] / "packages"
for _p in [_pkg_root / "core", _pkg_root / "connectors" / "reddit"]:
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from black_ink_signal_core.database import get_engine, get_session_factory
from black_ink_signal_core.models import SourceRun
from black_ink_signal_core.ingest import ingest_reddit_items
from black_ink_signal_core.enrichment import enrich_all_pending
from black_ink_signal_core.classifier.pipeline import ClassifierPipeline
from black_ink_signal_core.notifications import notify_hot_leads
from connector import RedditConnector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bis.scheduler")

# ---------------------------------------------------------------------------
# Configuration (env vars or defaults)
# ---------------------------------------------------------------------------

REDDIT_INTERVAL_MINUTES = int(os.environ.get("BIS_REDDIT_INTERVAL", "5"))
ENRICHMENT_INTERVAL_MINUTES = int(os.environ.get("BIS_ENRICHMENT_INTERVAL", "2"))
ENRICHMENT_BATCH_SIZE = int(os.environ.get("BIS_ENRICHMENT_BATCH", "20"))

# Reddit OAuth (optional — falls back to public JSON)
REDDIT_CLIENT_ID = os.environ.get("BIS_REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("BIS_REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.environ.get("BIS_REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.environ.get("BIS_REDDIT_PASSWORD", "")

# LLM (optional)
LLM_API_KEY = os.environ.get("BIS_LLM_API_KEY", "")
LLM_API_BASE = os.environ.get("BIS_LLM_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("BIS_LLM_MODEL", "gpt-4o-mini")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

engine = get_engine()
SessionFactory = get_session_factory(engine)
classifier = ClassifierPipeline(
    llm_api_key=LLM_API_KEY or None,
    llm_api_base=LLM_API_BASE,
    llm_model=LLM_MODEL,
)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def reddit_fetch_job():
    """Fetch new Reddit posts, score, and ingest."""
    logger.info("Reddit fetch starting...")
    connector = RedditConnector()
    try:
        items = connector.fetch_all_new()
        logger.info(f"Fetched {len(items)} items from Reddit")

        if not items:
            return

        with SessionFactory() as session:
            run = SourceRun(source="reddit")
            session.add(run)
            session.commit()

            stats = ingest_reddit_items(session, items, source_run=run)
            logger.info(f"Ingest: added={stats['added']} updated={stats['updated']} skipped={stats['skipped']}")

            # Notify on hot leads
            if stats['added'] > 0:
                notify_hot_leads(session)

    except Exception as e:
        logger.error(f"Reddit fetch failed: {e}", exc_info=True)
    finally:
        connector.close()


def enrichment_job():
    """Enrich leads that haven't been classified yet."""
    logger.info("Enrichment batch starting...")
    try:
        with SessionFactory() as session:
            count = enrich_all_pending(session, classifier, limit=ENRICHMENT_BATCH_SIZE)
            if count > 0:
                logger.info(f"Enriched {count} leads")
    except Exception as e:
        logger.error(f"Enrichment failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("=== Black Ink Signal Scheduler ===")
    logger.info(f"Reddit interval: {REDDIT_INTERVAL_MINUTES}m")
    logger.info(f"Enrichment interval: {ENRICHMENT_INTERVAL_MINUTES}m")
    logger.info(f"LLM enrichment: {'enabled' if LLM_API_KEY else 'rule-based only'}")

    scheduler = BlockingScheduler()

    scheduler.add_job(
        reddit_fetch_job,
        trigger=IntervalTrigger(minutes=REDDIT_INTERVAL_MINUTES),
        id="reddit_fetch",
        name="Reddit public fetch",
        next_run_time=datetime.now(timezone.utc),  # run immediately on start
    )

    scheduler.add_job(
        enrichment_job,
        trigger=IntervalTrigger(minutes=ENRICHMENT_INTERVAL_MINUTES),
        id="enrichment_batch",
        name="Lead enrichment batch",
        next_run_time=datetime.now(timezone.utc),
    )

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    scheduler.start()


if __name__ == "__main__":
    main()
