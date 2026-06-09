# Black Ink Signal

Desktop lead intelligence system for tattoo studios. Compliance-first, public-only.

## Architecture

```
┌───────────────────────────────────────────────────────┐
│  Electron Desktop App (React + Vite)                  │
│  ├── Live Feed       ├── Lead Drawer                  │
│  ├── Filters/Search  ├── Notifications                │
│  └── Status Buttons  └── CSV Export                   │
└──────────────────────┬────────────────────────────────┘
                       │ HTTP (localhost:8787)
┌──────────────────────▼────────────────────────────────┐
│  FastAPI Backend                                       │
│  ├── /leads          ├── /search                      │
│  ├── /leads/{id}/*   ├── /enrich/batch                │
│  ├── /notifications  ├── /export/csv                  │
│  └── /stats          └── /health                      │
└──────────────────────┬────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────┐
│  Core Engine                                           │
│  ├── Scoring v2 (keyword + geo + project + urgency)   │
│  ├── Classifier (rule-based + optional LLM)           │
│  ├── Ingestion pipeline (normalize → dedupe → score)  │
│  └── Notification manager (desktop + in-app)          │
└──────────────────────┬────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────┐
│  Connectors (isolated, modular)                        │
│  └── Reddit (public JSON + OAuth2)                    │
└──────────────────────┬────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────┐
│  Storage                                               │
│  └── SQLite (leads, events, source_runs)              │
└───────────────────────────────────────────────────────┘
```

## Quick Start

### Backend
```bash
cd apps/api
pip install -r requirements.txt
export PYTHONPATH="../../packages/core:../../packages/connectors/reddit"

# Seed test data (first time)
python3 app/seed_data.py

# Start API
uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
```

### Background Scheduler
```bash
cd apps/api
export PYTHONPATH="../../packages/core:../../packages/connectors/reddit"
python3 app/scheduler.py
```

### Desktop (development)
```bash
cd apps/desktop
NODE_ENV=development npm install
npm run dev        # Vite dev server at localhost:5173
```

### Desktop (Electron)
```bash
cd apps/desktop
NODE_ENV=development npm install
npm run build                   # Build Vite
npm run electron:dev            # Dev mode with DevTools
npm run electron:build          # Package for distribution
```

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|---|---|---|
| BIS_REDDIT_CLIENT_ID | (none) | Reddit script app client ID |
| BIS_REDDIT_CLIENT_SECRET | (none) | Reddit script app secret |
| BIS_REDDIT_USERNAME | (none) | Reddit account username |
| BIS_REDDIT_PASSWORD | (none) | Reddit account password |
| BIS_REDDIT_INTERVAL | 5 | Minutes between Reddit polls |
| BIS_ENRICHMENT_INTERVAL | 2 | Minutes between enrichment batches |
| BIS_HOT_LEAD_THRESHOLD | 80 | Score threshold for notifications |
| BIS_LLM_API_KEY | (none) | OpenAI-compatible API key for deep enrichment |
| BIS_LLM_MODEL | gpt-4o-mini | LLM model for enrichment |

## Score Bands

| Score | Band | Meaning |
|---|---|---|
| 85-100 | 🔥 Hot | Explicit local buying intent |
| 80-84 | 🔥 Hot | Coverup/sleeve/memorial + local |
| 60-79 | 🟡 Strong | Style search + local, or intent + geo |
| 40-59 | 🔵 Watchlist | Intent without location |
| 1-39 | ⚫ Low | General discussion, memes, show-offs |

## Compliance

- Public sources only
- No authentication bypass
- Rate-limited (1-2s between requests)
- No automated messaging
- Manual review required before any outreach
