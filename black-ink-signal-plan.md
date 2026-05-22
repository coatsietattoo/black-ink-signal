# Black Ink Signal

## Positioning

Black Ink Signal is a desktop lead-intelligence system for tattoo studios. It continuously discovers high-intent public conversations about tattoos, enriches them with AI, scores likely booking opportunities, and presents them in a dark operator-style live feed.

## Important compliance note

The system should only ingest publicly accessible data and should not bypass authentication, scrape private spaces, evade platform controls, or automate mass unsolicited outreach. Some requested sources are operationally fragile or legally restricted depending on platform terms, robots rules, and anti-bot controls. The architecture should therefore treat source connectors as policy-aware modules with per-source capability flags.

Recommended source categories:
- Low-friction/public-web sources: Reddit, tattoo forums, local forums, public review sites, public classifieds, public web search results, Google Maps review pages where accessible, blog comments where public.
- Conditional/public-only sources: X/Twitter public search, public Instagram captions/comments, public TikTok captions/comments, public Facebook pages/groups, public Discord channels.
- Human-assisted or bring-your-own-export mode where needed: sources with aggressive anti-automation or contract restrictions.

## Core product goals

1. Continuous discovery of relevant tattoo-intent conversations
2. Strong ranking of high-value local leads
3. Fast operator review in a live desktop feed
4. Local-first storage and enrichment
5. Modular architecture for future CRM and automation features

## Recommended stack

### Backend
- Python 3.12+
- FastAPI for local API server
- APScheduler or Celery Beat for recurring jobs
- SQLAlchemy + Alembic
- SQLite for single-operator desktop mode
- PostgreSQL optional for multi-user/server mode
- Playwright only for sources that require browser rendering and remain compliant
- httpx + selectolax/BeautifulSoup for lightweight fetchers
- sentence-transformers or bge-small/bge-base embeddings for semantic matching
- Qdrant local or pgvector/SQLite-vss depending on deployment preference
- LiteLLM wrapper or direct provider client for LLM enrichment

### Desktop app
Preferred: Electron
- React + TypeScript frontend
- Zustand or Redux Toolkit state management
- TanStack Query for API synchronization
- Tailwind + shadcn/ui or custom component set
- Framer Motion for subtle feed transitions
- Electron main process for packaging, tray mode, notifications, and process lifecycle

Alternative:
- Tauri for smaller footprint, but Electron will be simpler if embedding local Python services and background process management.

### Storage
Default local mode:
- SQLite for relational data
- Local vector index for semantic matching
- Optional object store folder for raw snapshots / HTML / JSON blobs

## High-level architecture

1. Source Connectors
2. Ingestion Queue
3. Normalization Layer
4. Deduplication + Entity Resolution
5. Semantic Intent Engine
6. Lead Scoring Engine
7. Enrichment Layer
8. Search/API Layer
9. Desktop UI
10. Export + Notifications

### 1) Source connectors
Each connector implements a common interface:
- fetch_recent()
- normalize()
- capability metadata
- rate_limit policy
- robots/terms policy status
- checkpoint persistence

Connector metadata example:
- source_name
- access_mode: rss | html | api | browser | manual-import
- public_only: true
- auth_required: false/conditional
- robots_respected: true
- supported_entities: post, comment, thread, review
- geo_signal_strength: strong/medium/weak

### 2) Ingestion queue
Use a small job queue table or Redis-less durable queue in SQLite.
Jobs:
- source poll
- content fetch
- enrichment
- rescoring
- notification dispatch

### 3) Normalization layer
Normalize all content into a shared schema:
- source
- source_item_id
- canonical_url
- author_handle
- author_display_name
- content_type
- title
- body
- parent_context
- created_at
- fetched_at
- engagement metrics
- raw_geo_text
- media flags
- language
- visibility
- raw payload reference

### 4) Deduplication and entity resolution
Need both exact and fuzzy dedupe:
- URL canonicalization
- source/id uniqueness
- text similarity threshold
- conversation clustering for reposted screenshots / syndicated posts

### 5) Semantic intent engine
Combine:
- keyword rules
- phrase patterns
- embedding similarity against tattoo-intent exemplars
- lightweight classifier for buying intent

Intent buckets:
- looking_for_artist
- asking_recommendations
- coverup_help
- style_research
- first_tattoo_anxiety
- sleeve_project_planning
- price_quote_interest
- healing_problem_or_regret
- relocation/local_search

### 6) Lead scoring engine
Score 1-100 from weighted factors.

Suggested factors:
- Intent strength: 0-30
- Location match to Edmonton/Alberta: 0-20
- Recency: 0-10
- Project size potential: 0-15
- Emotional urgency: 0-10
- Engagement/reply activity: 0-5
- Repeat collector signal: 0-5
- Negative prior tattoo / coverup need: 0-5

Suggested score bands:
- 80-100: hot lead
- 60-79: strong lead
- 40-59: watchlist
- 1-39: low priority

### 7) AI enrichment
For each candidate lead, generate:
- intent summary
- estimated booking likelihood
- likely project size: small | medium | large | multi-session
- emotional tone
- suggested outreach angle
- style interest category
- urgency estimate
- geographic confidence note

Use strict JSON outputs with cached prompts. Keep human-readable summaries short.

### 8) Search/API layer
FastAPI endpoints:
- /health
- /sources
- /leads
- /leads/{id}
- /search
- /bookmarks
- /exports/csv
- /stats/overview
- /stats/trends
- /settings
- /jobs

### 9) Desktop UI
Main views:
- Live Feed
- Lead Detail Drawer
- Saved Leads
- Search / Filters
- Source Health
- Trends / Heatmap placeholder
- Settings

## UI design direction
Dark operator dashboard.

Palette:
- background: near-black / charcoal
- cards: graphite
- text: cool gray + warm white accents
- score colors: muted red/amber/green/cyan
- accent: ink red or electric teal, not both heavily

Layout:
- left sidebar: filters, source toggles, saved views
- center: live scrolling feed
- right drawer: expanded lead detail
- top bar: search, sync status, source health, export, notifications

Feed card fields:
- lead score badge
- platform/source tag
- keyword or semantic trigger label
- geo estimate
- timestamp
- brief intent summary
- expandable conversation preview
- save/bookmark action

## Search logic
Start with hybrid retrieval.

### Rule-based seed phrases
- looking for tattoo artist
- cover up tattoo
- black and grey tattoo
- realism tattoo
- tattoo recommendations
- need tattoo ideas
- best tattoo artist
- tattoo sleeve
- tattoo quote
- walk in tattoo
- tattoo in Edmonton
- first tattoo
- tattoo healing
- looking for artist

### Semantic matching
Maintain a library of intent exemplars, for example:
- “I’m new to Edmonton and need a good artist for a sleeve.”
- “Can anyone recommend someone for a black and grey realism piece?”
- “I want to cover an old tattoo and need ideas.”
- “Thinking about my first tattoo and nervous about design and pain.”

Use embedding similarity to catch near-matches even when exact keywords are absent.

### Geo boosting
Estimate geography from:
- explicit city mentions
- subreddit/forum locality
- profile self-description when public and allowed
- local page/group/forum scope
- review/business location context

## Source feasibility notes

### Reddit
Strong first source.
- APIs, RSS, or compliant public page parsing
- Great for recommendation threads and local subreddits
- High-value targets: r/Edmonton, r/tattoos, local style and advice threads

### Public forums and local discussion boards
Also strong.
- Easier compliance
- Often indexable by search engines
- Good for long-form project discussions

### Google Maps reviews
Useful for competitor monitoring and dissatisfaction signals, but treat access carefully.
- Reviews can reveal users discussing coverups, bad experiences, artist switching, or style preferences.

### X / Instagram / TikTok / Facebook / Discord
Possible only through compliant public-access methods and often brittle.
- Use connector capability flags.
- Support manual-review mode or low-volume search mode.
- Do not promise universal coverage.

### Craigslist / Kijiji / Marketplace-style sources
Useful for local requests and artist search behavior where public posts exist.

## Data model

### leads table
- id
- source
- source_item_id
- canonical_url
- author_handle
- title
- body
- created_at
- fetched_at
- lead_score
- lead_status
- geo_estimate
- geo_confidence
- keyword_trigger
- semantic_label
- booking_likelihood
- project_size
- tone
- urgency
- style_interest
- outreach_angle
- bookmarked
- hidden
- dedupe_key
- conversation_hash

### lead_events table
- id
- lead_id
- event_type
- payload_json
- created_at

### source_runs table
- id
- source
- started_at
- finished_at
- status
- items_seen
- items_added
- items_updated
- errors

### raw_documents table
- id
- source
- source_item_id
- raw_json
- raw_text
- html_snapshot_path
- created_at

### embeddings table / vector index
- lead_id
- content_embedding
- trigger_embedding

## Notification logic
Trigger local desktop notifications for:
- lead score >= 85
- new Alberta/Edmonton high-intent recommendation request
- coverup / bad prior tattoo with urgency
- large project signals: sleeve, realism back piece, ongoing project, multi-session

Throttle alerts to avoid noise.

## Exports
Support:
- CSV export
- JSON export
- SQLite copy / backup
- future CRM webhook connector

## Background scanning
Polling cadence by source class:
- Reddit/local forums: every 3-5 minutes
- Search-engine discovered public pages: every 15-30 minutes
- Heavier browser-rendered sources: every 30-60 minutes or manual refresh

Use source-specific checkpoints to avoid reprocessing.

## Recommended MVP scope
Build the first version around sources that are both useful and operationally sane.

### MVP sources
1. Reddit
2. Tattoo forums and public discussion boards
3. Local Edmonton forums / subreddits
4. Public classifieds/community posts
5. Public review pages / selected Google Maps review workflows where allowed

### MVP features
- Continuous polling
- Live feed UI
- Lead scoring
- AI enrichment summary
- Bookmarking
- Search/filtering
- CSV export
- Local notifications
- Source health panel

### Phase 2
- Semantic clustering of similar conversations
- Competitor mention tracking
- Public Instagram/TikTok/X connectors where compliant
- Trend dashboards
- Heatmaps
- Outreach draft assistant

### Phase 3
- CRM integration
- appointment workflow handoff
- campaign insights
- CLV prediction

## Suggested repo structure

```text
black-ink-signal/
  apps/
    desktop/                # Electron + React UI
    api/                    # FastAPI service
  packages/
    core/                   # shared schemas, scoring, models
    connectors/
      reddit/
      forums/
      local_boards/
      classifieds/
      reviews/
      twitter_public/
      instagram_public/
      tiktok_public/
      facebook_public/
      discord_public/
    enrichment/
    vector/
    export/
  data/
    sqlite/
    blobs/
    checkpoints/
  prompts/
    lead_enrichment.md
    lead_scoring.md
  docs/
    architecture.md
    compliance.md
    source-matrix.md
```

## Suggested enrichment prompt contract
Output JSON with fields:
- summary
- booking_likelihood_percent
- project_size
- tone
- urgency
- style_interest
- outreach_angle
- reason_codes

## Pseudocode pipeline

```python
for source in enabled_sources:
    items = source.fetch_recent(checkpoint=source.last_checkpoint)
    for item in items:
        doc = normalize(item)
        if is_duplicate(doc):
            continue
        seed_score = keyword_score(doc) + semantic_score(doc)
        if seed_score < MIN_DISCOVERY_THRESHOLD:
            continue
        lead = upsert_lead(doc)
        enrich_lead_async(lead.id)
        rescore_lead_async(lead.id)
        maybe_notify(lead.id)
```

## Opinionated recommendation
Do not start by trying to fully automate every named platform. That will create a brittle, legally messy system fast.

Start with a compliance-first core around Reddit + forums + local public boards + public reviews, build a strong lead model and UI, then add conditional connectors one by one behind explicit capability flags.

That gets you a product that actually works instead of a giant scraping graveyard.

## First implementation milestones

### Milestone 1: foundation
- create monorepo/app skeleton
- FastAPI service
- Electron shell + React dashboard
- SQLite schema
- lead feed with mock data

### Milestone 2: ingestion
- Reddit connector
- forum connector
- classifieds/local boards connector
- normalization + dedupe

### Milestone 3: intelligence
- semantic matcher
- scoring engine
- LLM enrichment
- notifications

### Milestone 4: operator polish
- saved views
- export
- source health
- settings
- trends cards

## Build risks
- platform anti-bot restrictions
- compliance drift if connectors are added carelessly
- noisy false positives without semantic ranking and dedupe
- local packaging complexity when shipping Python + desktop runtime

## Mitigations
- connector capability matrix
- source-by-source rate limiting
- audit logs for each fetch
- local caching and checkpointing
- human review layer before any outreach or CRM action
