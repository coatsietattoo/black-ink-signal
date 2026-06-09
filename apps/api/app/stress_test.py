"""Stress test for Black Ink Signal — generates 10k+ leads and benchmarks."""

import os
import sys
import time
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add packages
_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root / "packages" / "core"))
sys.path.insert(0, str(_root / "packages" / "connectors" / "reddit"))

from black_ink_signal_core.database import get_engine, get_session_factory
from black_ink_signal_core.models import Lead, LeadEvent, SourceRun
from black_ink_signal_core.scoring import score_lead, score_band

# Seed vocabulary
TITLES = [
    "Looking for tattoo artist in Edmonton for {}",
    "Need a coverup in {}",
    "First tattoo questions - {}",
    "Memorial tattoo ideas for my {}",
    "Best {} style artists in Alberta?",
    "Planning a {} sleeve - any recommendations?",
    "Who does {} in the Edmonton area?",
    "Walk-in spots for a quick {}?",
    "How much for a {} tattoo?",
    "Unhappy with my {} - considering rework",
    "Adding to my collection - looking for {} artist",
    "ISO {} artist in YEG",
    "Tribute piece for {} - need recommendations",
    "Any {} artists around Sherwood Park?",
    "Need help with a {} design idea",
]

PROJECTS = [
    "full sleeve", "half sleeve", "back piece", "chest piece", "portrait",
    "realism", "traditional", "geometric", "Japanese", "fine line",
    "dotwork", "watercolor", "lettering", "tribal", "blackwork",
    "neo-traditional", "minimalist", "surrealism", "cover-up", "memorial",
]

LOCATIONS = ["Edmonton", "YEG", "Alberta", "Sherwood Park", "St Albert", "Red Deer", "Calgary", ""]

BODIES = [
    "Hey everyone, I've been thinking about getting {} done. Anyone have recommendations for artists in the {} area? Budget around ${}. Thanks!",
    "Looking to get a {} piece. I've seen some cool work but can't find the right artist near {}. Anyone?",
    "My friend got an amazing {} from an artist in {}. Want something similar. Any portfolios I should check?",
    "Been saving up for a {} tattoo. Ready to book ASAP in {}.",
    "Just moved to {} and looking for a good tattoo shop for {} work.",
    "First time getting inked, thinking {} style. Nervous but excited. In {} area.",
    "Need to cover up a bad tattoo on my arm. Looking for someone in {} who's good at {} coverups.",
    "Lost my dog last month, want a {} memorial piece. {} artist recommendations?",
]

SUBREDDITS = ["Edmonton", "tattoos", "tattoodesigns", "tattooadvice", "alberta", "yeg"]
AUTHORS = [f"user_{i}" for i in range(500)]


def generate_leads(count: int = 10000) -> list[dict]:
    """Generate synthetic leads."""
    leads = []
    now = datetime.now(timezone.utc)

    for i in range(count):
        project = random.choice(PROJECTS)
        location = random.choice(LOCATIONS)
        title = random.choice(TITLES).format(project)
        body = random.choice(BODIES).format(
            project,
            location or "the area",
            random.randint(100, 5000),
        )
        created_at = now - timedelta(hours=random.uniform(0.5, 168))

        leads.append({
            "title": title,
            "body": body,
            "subreddit": random.choice(SUBREDDITS),
            "author": random.choice(AUTHORS),
            "created_at": created_at,
            "score_ups": random.randint(1, 200),
            "num_comments": random.randint(0, 50),
            "item_id": f"t3_stress_{i:06d}",
        })
    return leads


def run_stress_test():
    print("=== Black Ink Signal Stress Test ===\n")

    engine = get_engine()
    Session = get_session_factory(engine)

    # Generate leads
    COUNT = 10000
    print(f"Generating {COUNT} synthetic leads...")
    t0 = time.time()
    leads_data = generate_leads(COUNT)
    t_gen = time.time() - t0
    print(f"  Generated in {t_gen:.2f}s\n")

    # Score all leads
    print("Scoring all leads...")
    t0 = time.time()
    scored = []
    for ld in leads_data:
        breakdown = score_lead(
            title=ld["title"],
            body=ld["body"],
            subreddit=ld["subreddit"],
            created_at=ld["created_at"],
            score_ups=ld["score_ups"],
            num_comments=ld["num_comments"],
        )
        scored.append((ld, breakdown))
    t_score = time.time() - t0
    print(f"  Scored in {t_score:.2f}s ({COUNT / t_score:.0f} leads/sec)\n")

    # Insert into DB
    print("Inserting into database...")
    t0 = time.time()
    batch_size = 500
    total_inserted = 0
    with Session() as s:
        for i in range(0, len(scored), batch_size):
            batch = scored[i:i + batch_size]
            for ld, breakdown in batch:
                lead = Lead(
                    source="reddit",
                    source_item_id=ld["item_id"],
                    canonical_url=f"https://reddit.com/r/{ld['subreddit']}/comments/{ld['item_id']}",
                    author_handle=ld["author"],
                    title=ld["title"],
                    body=ld["body"],
                    subreddit=ld["subreddit"],
                    created_at=ld["created_at"],
                    fetched_at=datetime.now(timezone.utc),
                    lead_score=breakdown.total,
                    lead_status="new",
                    geo_estimate=breakdown.geo_estimate,
                    geo_confidence=breakdown.geo_confidence,
                    keyword_trigger=breakdown.keyword_trigger,
                    semantic_label=breakdown.semantic_label,
                    dedupe_key=f"reddit:{ld['item_id']}",
                    score_ups=ld["score_ups"],
                    num_comments=ld["num_comments"],
                )
                s.add(lead)
                total_inserted += 1
            s.commit()
    t_insert = time.time() - t0
    print(f"  Inserted {total_inserted} in {t_insert:.2f}s ({total_inserted / t_insert:.0f} leads/sec)\n")

    # Query benchmarks
    print("Running query benchmarks...")
    with Session() as s:
        # Count
        t0 = time.time()
        total = s.query(Lead).count()
        t_count = time.time() - t0
        print(f"  COUNT(*): {total} in {t_count * 1000:.1f}ms")

        # Filtered query
        t0 = time.time()
        hot = s.query(Lead).filter(Lead.lead_score >= 80).limit(100).all()
        t_hot = time.time() - t0
        print(f"  Hot leads (score >= 80, limit 100): {len(hot)} in {t_hot * 1000:.1f}ms")

        # Full table scan
        t0 = time.time()
        all_leads = s.query(Lead).order_by(Lead.lead_score.desc()).limit(200).all()
        t_all = time.time() - t0
        print(f"  Top 200 by score: {len(all_leads)} in {t_all * 1000:.1f}ms")

        # Search
        t0 = time.time()
        results = s.query(Lead).filter(Lead.title.ilike("%coverup%")).limit(50).all()
        t_search = time.time() - t0
        print(f"  Text search 'coverup': {len(results)} in {t_search * 1000:.1f}ms")

    # Dedup test
    print("\nDuplicate handling test...")
    t0 = time.time()
    dupe_count = 0
    with Session() as s:
        for ld, _ in scored[:1000]:
            existing = s.query(Lead).filter_by(dedupe_key=f"reddit:{ld['item_id']}").first()
            if existing:
                dupe_count += 1
    t_dedup = time.time() - t0
    print(f"  Checked 1000 dupes: {dupe_count} found in {t_dedup * 1000:.1f}ms")

    # Semantic index build
    from black_ink_signal_core.semantic import TFIDFIndex
    print("\nSemantic index benchmark...")
    t0 = time.time()
    idx = TFIDFIndex()
    with Session() as s:
        all_leads = s.query(Lead).all()
        for lead in all_leads:
            idx.add(lead.id, f"{lead.title or ''} {lead.body or ''}")
    idx.build()
    t_index = time.time() - t0
    print(f"  Index built ({idx.size} docs) in {t_index:.2f}s")

    t0 = time.time()
    results = idx.search("coverup edmonton sleeve", top_k=20)
    t_search = time.time() - t0
    print(f"  Semantic search: {len(results)} results in {t_search * 1000:.1f}ms")

    # Cleanup stress data
    print("\nCleaning up stress test data...")
    t0 = time.time()
    with Session() as s:
        deleted = s.query(Lead).filter(Lead.source_item_id.like("t3_stress_%")).delete(synchronize_session=False)
        s.commit()
    t_clean = time.time() - t0
    print(f"  Deleted {deleted} leads in {t_clean:.2f}s")

    print("\n=== Summary ===")
    print(f"  Generation:   {t_gen:.2f}s ({COUNT} leads)")
    print(f"  Scoring:      {t_score:.2f}s ({COUNT / t_score:.0f}/sec)")
    print(f"  Insertion:    {t_insert:.2f}s ({total_inserted / t_insert:.0f}/sec)")
    print(f"  Hot query:    {t_hot * 1000:.1f}ms")
    print(f"  Text search:  {t_search * 1000:.1f}ms")
    print(f"  Dedup check:  {t_dedup:.2f}s (1000 checks)")
    print(f"  Index build:  {t_index:.2f}s ({idx.size} docs)")
    print(f"  Sem. search:  {t_search * 1000:.1f}ms")
    print("\n✓ All benchmarks complete.")


if __name__ == "__main__":
    run_stress_test()
