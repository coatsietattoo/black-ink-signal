"""CLI runner — fetch Reddit, score, ingest into SQLite."""

import sys
import logging
from pathlib import Path

_pkg_root = Path(__file__).resolve().parents[2] / "packages"
sys.path.insert(0, str(_pkg_root / "core"))
sys.path.insert(0, str(_pkg_root / "connectors" / "reddit"))

from black_ink_signal_core.database import get_engine, get_session_factory
from black_ink_signal_core.models import SourceRun
from black_ink_signal_core.ingest import ingest_reddit_items
from connector import RedditConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("bis.fetch")


def main():
    logger.info("Starting Reddit fetch...")
    engine = get_engine()
    Session = get_session_factory(engine)

    connector = RedditConnector()
    try:
        items = connector.fetch_all_new()
        logger.info(f"Fetched {len(items)} items from Reddit")

        with Session() as session:
            run = SourceRun(source="reddit")
            session.add(run)
            session.commit()

            stats = ingest_reddit_items(session, items, source_run=run)
            logger.info(f"Ingest stats: {stats}")

    finally:
        connector.close()

    logger.info("Done.")


if __name__ == "__main__":
    main()
