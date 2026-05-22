"""Seed the database with realistic test leads for UI development."""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import random

_pkg_root = Path(__file__).resolve().parents[2] / "packages"
for _p in [_pkg_root / "core", _pkg_root / "connectors" / "reddit"]:
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

from black_ink_signal_core.database import get_engine, get_session_factory
from black_ink_signal_core.models import Lead, LeadEvent
from black_ink_signal_core.scoring import score_lead

SEED_POSTS = [
    {
        "title": "Looking for tattoo artist in Edmonton for a full sleeve",
        "body": "Hey everyone, I'm looking for a realism tattoo artist in Edmonton. Want to do a full sleeve, black and grey. Any recommendations? Budget isn't an issue, I want quality work.",
        "subreddit": "Edmonton",
        "author": "yeg_inkfan",
        "score_ups": 24,
        "num_comments": 18,
        "hours_ago": 2,
    },
    {
        "title": "Need a cover up tattoo - bad experience at last shop",
        "body": "I have a terrible tattoo on my forearm from a shop that closed down. It's faded and blown out. Looking for someone in the Edmonton area who specializes in coverups. Preferably realism or dark illustrative style. Need it done ASAP, I have a wedding coming up.",
        "subreddit": "Edmonton",
        "author": "coverup_needed_yeg",
        "score_ups": 31,
        "num_comments": 22,
        "hours_ago": 1,
    },
    {
        "title": "First tattoo advice - nervous but excited",
        "body": "I'm finally getting my first tattoo! I want something meaningful on my ribs. Any artists in Alberta that are good with fine line work? I'm in Edmonton but willing to travel to Calgary for the right artist.",
        "subreddit": "tattooadvice",
        "author": "first_ink_journey",
        "score_ups": 15,
        "num_comments": 12,
        "hours_ago": 4,
    },
    {
        "title": "Best black and grey realism artists in Western Canada?",
        "body": "Planning a large back piece, realistic portrait work. Looking for the best of the best in Alberta or BC. Will be multiple sessions. Money is not the issue, I want museum-quality work. Currently based in Edmonton.",
        "subreddit": "tattoos",
        "author": "realism_collector",
        "score_ups": 45,
        "num_comments": 33,
        "hours_ago": 6,
    },
    {
        "title": "Walk-in tattoo shops in Edmonton?",
        "body": "Visiting Edmonton this weekend, looking for walk-in availability. Want a small traditional piece on my arm. Any recommendations for shops that do walk-ins on Saturday?",
        "subreddit": "Edmonton",
        "author": "visiting_yeg",
        "score_ups": 8,
        "num_comments": 6,
        "hours_ago": 3,
    },
    {
        "title": "Tattoo healing issues - looking for touch up artist",
        "body": "My tattoo healed weird - some spots lost ink and it looks patchy. The original artist moved away. Anyone know someone in Edmonton who does good touch-ups? It's a medium sized piece on my thigh.",
        "subreddit": "Edmonton",
        "author": "healing_help_yeg",
        "score_ups": 12,
        "num_comments": 9,
        "hours_ago": 8,
    },
    {
        "title": "Adding to my sleeve - need artist recommendation",
        "body": "I have a half sleeve that I want to extend to a full sleeve. The style is Japanese traditional. Looking for someone in Alberta who does amazing Japanese work. My collection is getting big and I want consistency.",
        "subreddit": "alberta",
        "author": "sleeve_extension",
        "score_ups": 19,
        "num_comments": 14,
        "hours_ago": 12,
    },
    {
        "title": "Thinking about getting a tattoo quote - how much for a forearm piece?",
        "body": "Never gotten a tattoo before. Thinking about a script quote on my inner forearm, maybe 6 inches long. How much should I expect to pay in Edmonton? Any shops that won't judge a newbie?",
        "subreddit": "Edmonton",
        "author": "quote_curious",
        "score_ups": 6,
        "num_comments": 8,
        "hours_ago": 5,
    },
    {
        "title": "Just got this done - so happy!",
        "body": "Finally finished my piece after 3 sessions. So stoked with how it turned out! [photo]",
        "subreddit": "tattoos",
        "author": "happy_client",
        "score_ups": 234,
        "num_comments": 42,
        "hours_ago": 10,
    },
    {
        "title": "Tattoo meme dump",
        "body": "When your artist says 'just a little more shading' for the 4th hour straight 😂",
        "subreddit": "tattoos",
        "author": "meme_lord_ink",
        "score_ups": 1200,
        "num_comments": 89,
        "hours_ago": 14,
    },
    {
        "title": "Recommendations for geometric/dotwork in Edmonton?",
        "body": "Looking for an artist who does clean geometric and dotwork pieces. Want something on my shoulder. Located in St Albert but can drive into the city. Anyone have good experiences?",
        "subreddit": "Edmonton",
        "author": "geo_dots_yeg",
        "score_ups": 11,
        "num_comments": 7,
        "hours_ago": 7,
    },
    {
        "title": "Unhappy with my tattoo - considering removal or coverup",
        "body": "Got a tattoo 2 years ago and I've never liked it. It's on my chest, about 6x4 inches. Considering either laser removal or a coverup. Has anyone in Edmonton done the removal + coverup combo? What should I expect cost-wise for something this size?",
        "subreddit": "Edmonton",
        "author": "regret_chest_piece",
        "score_ups": 17,
        "num_comments": 21,
        "hours_ago": 3,
    },
    {
        "title": "Planning a leg sleeve - any portfolio recs?",
        "body": "Want to start a leg sleeve, neo-traditional style with flowers and animals. This will be a big project, probably 6+ sessions. Looking for portfolios to browse. Based in Sherwood Park.",
        "subreddit": "Edmonton",
        "author": "leg_sleeve_plan",
        "score_ups": 14,
        "num_comments": 11,
        "hours_ago": 9,
    },
    {
        "title": "Aftercare products discussion",
        "body": "What does everyone use for aftercare? I've been using Aquaphor but heard Saniderm is better. Thoughts?",
        "subreddit": "tattoos",
        "author": "care_bear_ink",
        "score_ups": 45,
        "num_comments": 67,
        "hours_ago": 20,
    },
    {
        "title": "ISO tattoo artist for memorial piece",
        "body": "Lost my dad last month. Want to get a memorial portrait tattoo. Needs to be realistic and well done - this is really important to me. In Edmonton. Price doesn't matter, I want the best artist for portraits.",
        "subreddit": "Edmonton",
        "author": "memorial_tribute",
        "score_ups": 28,
        "num_comments": 16,
        "hours_ago": 1,
    },
]


def seed():
    engine = get_engine()
    Session = get_session_factory(engine)

    now = datetime.now(timezone.utc)

    with Session() as session:
        for post in SEED_POSTS:
            created = now - timedelta(hours=post["hours_ago"])
            breakdown = score_lead(
                title=post["title"],
                body=post["body"],
                subreddit=post["subreddit"],
                created_at=created,
                score_ups=post["score_ups"],
                num_comments=post["num_comments"],
            )

            # Skip very low signal
            if breakdown.total < 5:
                print(f"  SKIP (score {breakdown.total}): {post['title'][:50]}")
                continue

            dedupe_key = f"reddit:seed_{post['author']}_{hash(post['title']) % 100000}"

            existing = session.query(Lead).filter_by(dedupe_key=dedupe_key).first()
            if existing:
                print(f"  EXISTS: {post['title'][:50]}")
                continue

            lead = Lead(
                source="reddit",
                source_item_id=f"t3_seed_{random.randint(10000, 99999)}",
                canonical_url=f"https://www.reddit.com/r/{post['subreddit']}/comments/seed_{post['author']}/",
                author_handle=post["author"],
                title=post["title"],
                body=post["body"],
                subreddit=post["subreddit"],
                created_at=created,
                fetched_at=now,
                lead_score=breakdown.total,
                lead_status="new",
                geo_estimate=breakdown.geo_estimate,
                geo_confidence=breakdown.geo_confidence,
                keyword_trigger=breakdown.keyword_trigger,
                semantic_label=breakdown.semantic_label,
                dedupe_key=dedupe_key,
                score_ups=post["score_ups"],
                num_comments=post["num_comments"],
            )
            session.add(lead)
            session.flush()
            session.add(LeadEvent(
                lead_id=lead.id,
                event_type="created",
                payload_json={"score": breakdown.total, "source": "reddit_seed"},
            ))
            print(f"  ADD (score {breakdown.total:>2}, {breakdown.semantic_label}): {post['title'][:60]}")

        session.commit()
        total = session.query(Lead).count()
        print(f"\nTotal leads in DB: {total}")


if __name__ == "__main__":
    seed()
