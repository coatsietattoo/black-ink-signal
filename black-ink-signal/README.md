# Black Ink Signal

Black Ink Signal is a compliance-first desktop lead intelligence system for tattoo studios.

## MVP v1 scope
- Reddit public-source connector
- SQLite database
- Lead scoring system
- Desktop live feed
- Manual review/contact status buttons
- No auto-messaging

## Principles
- Public sources only
- No authentication bypass
- No scraping of private spaces
- Respect rate limits and platform rules
- Human-reviewed workflow only

## Monorepo layout
- `apps/api` - FastAPI backend
- `apps/desktop` - Electron desktop shell and live feed UI
- `packages/core` - shared Python core for schema, DB, scoring
- `packages/connectors/reddit` - Reddit public-source connector stub
- `data` - local runtime data
- `docs` - architecture and compliance notes

## Quick start
Backend:
```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Desktop:
```bash
cd apps/desktop
npm install
npm run dev
```

## Current status
This repo currently includes:
- initial skeleton
- SQLite schema bootstrap
- scoring engine
- Reddit connector stub
- desktop feed scaffold
