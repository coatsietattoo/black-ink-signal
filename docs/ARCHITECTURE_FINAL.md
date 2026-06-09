# Black Ink Signal — V1 Final Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Desktop App (Electron)                │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │ Live Feed   │  │ Lead Drawer│  │ Admin Panel      │  │
│  │ • Cards     │  │ • Detail   │  │ • Source Health   │  │
│  │ • Aging     │  │ • Scripts  │  │ • Daily Summary   │  │
│  │ • Compact   │  │ • Scoring  │  │ • Trends          │  │
│  │ • Ticker    │  │ • Booking  │  │ • Actions          │  │
│  │ • Filters   │  │ • Notes    │  │ • Backup           │  │
│  └────────────┘  └────────────┘  └──────────────────┘  │
│              React + Vite + TypeScript                   │
│              Session persistence (localStorage)          │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP (port 8787)
┌─────────────────────────┴───────────────────────────────┐
│                 FastAPI Backend (31 endpoints)           │
│  ┌─────────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │ Lead CRUD    │  │ Search   │  │ Admin Actions      │ │
│  │ Status/Notes │  │ Keyword  │  │ Fetch/Enrich/Seed  │ │
│  │ Bookmark     │  │ Semantic │  │ Rescore/Backup     │ │
│  │ Enrich       │  │ Similar  │  │ Clear/Index        │ │
│  └─────────────┘  └──────────┘  └────────────────────┘ │
│  ┌─────────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │ Stats/Daily  │  │ Scripts  │  │ Source Health       │ │
│  │ Trends       │  │ Contact  │  │ Notifications      │ │
│  │ Revenue      │  │ Generator│  │ Dedup Report       │ │
│  └─────────────┘  └──────────┘  └────────────────────┘ │
└─────────────┬──────────────┬──────────────┬─────────────┘
              │              │              │
┌─────────────┴──┐  ┌───────┴─────┐  ┌────┴──────────────┐
│ Scoring Engine  │  │ Classifier  │  │ Semantic Index     │
│ v2 (15 factors) │  │ Rules+LLM   │  │ TF-IDF + domain   │
│ Target bands    │  │ Pipeline    │  │ boost + cosine     │
│ 20k leads/sec   │  │             │  │ 10k docs in 0.3s   │
└────────────────┘  └─────────────┘  └───────────────────┘
              │              │
┌─────────────┴──┐  ┌───────┴─────┐
│ SQLite          │  │ Reddit      │
│ leads           │  │ OAuth + JSON│
│ lead_events     │  │ Connector   │
│ source_runs     │  │             │
└────────────────┘  └─────────────┘
       │
┌──────┴─────────┐
│ Scheduler       │
│ APScheduler     │
│ Reddit: 5min    │
│ Enrich: 2min    │
└────────────────┘
```

## API Endpoints (31)

### Core
| # | Method | Path | Description |
|---|--------|------|-------------|
| 1 | GET | `/health` | Health check |
| 2 | GET | `/leads` | List leads (filtered, paginated) |
| 3 | GET | `/leads/{id}` | Single lead with score breakdown |
| 4 | PATCH | `/leads/{id}/status` | Update status (8 options) |
| 5 | PATCH | `/leads/{id}/bookmark` | Toggle bookmark |
| 6 | PATCH | `/leads/{id}/notes` | Update operator notes |
| 7 | POST | `/leads/{id}/enrich` | Enrich single lead |
| 8 | POST | `/enrich/batch` | Batch enrichment |
| 9 | PATCH | `/leads/{id}/booked-value` | Set booked value |

### Search
| # | Method | Path | Description |
|---|--------|------|-------------|
| 10 | GET | `/search` | Keyword search (LIKE) |
| 11 | GET | `/search/semantic` | TF-IDF semantic search |
| 12 | GET | `/leads/{id}/similar` | Find similar leads |
| 13 | GET | `/leads/{id}/scripts` | Generate 3 contact scripts |

### Analytics
| # | Method | Path | Description |
|---|--------|------|-------------|
| 14 | GET | `/export/csv` | CSV export with filters |
| 15 | GET | `/stats` | Quick stats (hot/strong/watchlist) |
| 16 | GET | `/stats/daily` | Daily summary + top keywords/sources |
| 17 | GET | `/stats/trends` | Trend engine (rising keywords, peak times, geo) |
| 18 | GET | `/stats/revenue` | Revenue from booked leads |

### Notifications
| # | Method | Path | Description |
|---|--------|------|-------------|
| 19 | GET | `/notifications` | Recent notification history |
| 20 | POST | `/notifications/trigger` | Manual notification check |

### Operations
| # | Method | Path | Description |
|---|--------|------|-------------|
| 21 | GET | `/sources/health` | Source health dashboard |
| 22 | POST | `/admin/fetch-reddit` | Trigger Reddit fetch |
| 23 | POST | `/admin/enrich` | Trigger enrichment batch |
| 24 | POST | `/admin/seed` | Insert demo leads |
| 25 | POST | `/admin/rescore` | Rescore all leads |
| 26 | POST | `/admin/rebuild-index` | Rebuild semantic index |
| 27 | POST | `/admin/backup` | Create timestamped DB backup |
| 28 | GET | `/admin/backup/download` | Download DB file |
| 29 | GET | `/admin/dedup-report` | Dedup strategy + stats |
| 30 | DELETE | `/admin/clear-demo` | Remove seed data |
| 31 | DELETE | `/admin/clear-all` | Remove all data |

## Performance Benchmarks (10,015 leads)

| Operation | Result |
|-----------|--------|
| Scoring | 19,803 leads/sec |
| DB insertion | 12,512 leads/sec |
| COUNT(*) | 4.8ms |
| Hot leads query | 2.9ms |
| Text search | 2.3ms |
| Dedup check (1k) | 231ms |
| Semantic index build | 0.32s |
| Semantic search | 42.7ms |

## Deployment Checklist

### Prerequisites
- [ ] macOS 13+ / Linux / Windows 10+
- [ ] Python 3.11+ with pip
- [ ] Node.js 18+ with npm
- [ ] Reddit "script" app credentials

### Setup
- [ ] Clone repository
- [ ] `cp .env.example .env` and configure
- [ ] `cd apps/api && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- [ ] `cd apps/desktop && npm install`
- [ ] Verify: `curl http://127.0.0.1:8787/health`

### Reddit OAuth
- [ ] Create app at https://www.reddit.com/prefs/apps (type: script)
- [ ] Set BIS_REDDIT_CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD, USER_AGENT in .env
- [ ] Test: `curl -X POST http://127.0.0.1:8787/admin/fetch-reddit`

### Launch
- [ ] Terminal 1: `uvicorn app.main:app --port 8787 --reload`
- [ ] Terminal 2: `python3 app/scheduler.py`
- [ ] Terminal 3: `npm run dev` (browser) or `npm run electron:dev` (desktop)

### Verify
- [ ] `/health` returns ok
- [ ] `/sources/health` shows OAuth configured
- [ ] Scheduler logs show successful fetches
- [ ] Hot leads appear in feed
- [ ] Notifications fire for score >= 80

### Backups
- [ ] Create initial backup: `POST /admin/backup`
- [ ] Schedule regular backups (cron or manual)
- [ ] Test restore: copy backup → `data/black_ink_signal.db`

## Production Readiness

### ✅ Ready
- Scoring engine: 15 factors, 20k/sec, tested against target bands
- Dedup: source:item_id key, unique constraint, engagement-aware updates
- Database: SQLite with proper indices, auto-migration, backup system
- Error handling: graceful API errors, frontend error banner, auto-retry
- Onboarding: guided setup when missing credentials
- Session persistence: filters, view, compact mode survive restart
- Performance: 10k+ leads tested, all queries < 50ms

### ⚠ Production recommendations
- **Rate limiting**: Add FastAPI rate limiting for admin endpoints
- **Auth**: Add API key or session auth for admin endpoints
- **HTTPS**: Put behind nginx with SSL for any network exposure
- **WAL mode**: Enable SQLite WAL for concurrent reads: `PRAGMA journal_mode=WAL`
- **Monitoring**: Add structured logging (JSON) and health check endpoint for uptime
- **Reddit user agent**: Use unique, descriptive user agent to avoid blocks
- **Backup rotation**: Current: 10 backups kept. Consider daily off-site backup

### 🔲 Future V2 candidates
- Multi-source: Instagram, Facebook groups, Google My Business
- CRM integration: export to booking systems
- Team mode: multiple operators with role-based access
- Dashboard: visual charts (Chart.js or Recharts)
- Webhook notifications: Slack, Discord, email
- AI-powered script generation (LLM-based, not rule-based)
- Mobile companion app
- A/B test contact scripts with response tracking
