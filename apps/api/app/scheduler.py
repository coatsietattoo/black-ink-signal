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
import subprocess
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
from oauth_connector import RedditOAuthConnector

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
FACEBOOK_INTERVAL_MINUTES = int(os.environ.get("BIS_FACEBOOK_INTERVAL", "0"))
FACEBOOK_SCAN_SCRIPT = Path(os.environ.get(
    "BIS_FACEBOOK_SCAN_SCRIPT",
    str(Path(__file__).resolve().parents[2] / "tools" / "mac_browser_scan_mvp.js"),
))
FACEBOOK_SCAN_TIMEOUT_SECONDS = int(os.environ.get("BIS_FACEBOOK_SCAN_TIMEOUT", "180"))

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

def _get_reddit_connector():
    """Return OAuth connector if credentials are set, else public fallback."""
    if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET and REDDIT_USERNAME and REDDIT_PASSWORD:
        logger.info("Using Reddit OAuth connector")
        return RedditOAuthConnector(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
            user_agent=os.environ.get("BIS_REDDIT_USER_AGENT", "BlackInkSignal/0.1"),
        )
    else:
        logger.info("Using Reddit public JSON connector (no OAuth credentials)")
        return RedditConnector()


def reddit_fetch_job():
    """Fetch new Reddit posts, score, and ingest."""
    logger.info("Reddit fetch starting...")
    connector = _get_reddit_connector()
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

            if stats['added'] > 0:
                notify_hot_leads(session)

    except Exception as e:
        logger.error(f"Reddit fetch failed: {e}", exc_info=True)
    finally:
        connector.close()


def facebook_browser_fetch_job():
    """Run the browser-assisted Facebook scanner via Chrome DevTools, if available."""
    if not FACEBOOK_SCAN_SCRIPT.exists():
        logger.error(f"Facebook browser scan script not found: {FACEBOOK_SCAN_SCRIPT}")
        return

    logger.info("Facebook browser scan starting...")
    try:
        env = os.environ.copy()
        env.setdefault("BIS_BROWSER_SCAN_MODE", "post")
        result = subprocess.run(
            ["node", str(FACEBOOK_SCAN_SCRIPT)],
            cwd=str(FACEBOOK_SCAN_SCRIPT.parent.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=FACEBOOK_SCAN_TIMEOUT_SECONDS,
            check=False,
        )
        if result.stdout.strip():
            logger.info(result.stdout.strip())
        if result.returncode != 0:
            if result.stderr.strip():
                logger.warning(result.stderr.strip())
            logger.warning(
                "Facebook browser scan skipped/failed. "
                "Chrome DevTools on port 9222 may be unavailable, or the scan could not ingest results."
            )
            return
        if result.stderr.strip():
            logger.info(result.stderr.strip())
        logger.info("Facebook browser scan finished successfully")
    except subprocess.TimeoutExpired:
        logger.warning(f"Facebook browser scan timed out after {FACEBOOK_SCAN_TIMEOUT_SECONDS}s")
    except Exception as e:
        logger.error(f"Facebook browser scan failed: {e}", exc_info=True)


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
    logger.info(f"Facebook browser interval: {FACEBOOK_INTERVAL_MINUTES}m")
    logger.info(f"Enrichment interval: {ENRICHMENT_INTERVAL_MINUTES}m")
    logger.info(f"LLM enrichment: {'enabled' if LLM_API_KEY else 'rule-based only'}")

    scheduler = BlockingScheduler()

    scheduler.add_job(
        reddit_fetch_job,
        trigger=IntervalTrigger(minutes=REDDIT_INTERVAL_MINUTES),
        id="reddit_fetch",
        name="Reddit public fetch",
        next_run_time=datetime.now(timezone.utc),
    )

    if FACEBOOK_INTERVAL_MINUTES > 0:
        scheduler.add_job(
            facebook_browser_fetch_job,
            trigger=IntervalTrigger(minutes=FACEBOOK_INTERVAL_MINUTES),
            id="facebook_browser_fetch",
            name="Facebook browser-assisted fetch",
            next_run_time=datetime.now(timezone.utc),
        )
    else:
        logger.info("Facebook browser scan disabled (set BIS_FACEBOOK_INTERVAL > 0 to enable)")

    scheduler.add_job(
        enrichment_job,
        trigger=IntervalTrigger(minutes=ENRICHMENT_INTERVAL_MINUTES),
        id="enrichment_batch",
        name="Lead enrichment batch",
        next_run_time=datetime.now(timezone.utc),
    )

    def shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    scheduler.start()


if __name__ == "__main__":
    main()
