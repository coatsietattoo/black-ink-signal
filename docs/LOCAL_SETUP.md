# Local Setup Guide (macOS)

Complete instructions to run Black Ink Signal on your Mac.

## Prerequisites

- macOS 13+ (Ventura or later)
- Python 3.11+ (`python3 --version`)
- Node.js 18+ (`node --version`)
- npm 9+ (`npm --version`)

If missing:
```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python
brew install python@3.12

# Node
brew install node
```

---

## 1. Clone / navigate to the project

```bash
cd /path/to/black-ink-signal
```

---

## 2. Install Python dependencies

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Install Node dependencies

```bash
cd apps/desktop
npm install
```

For Electron (native desktop app):
```bash
npm install electron electron-builder --save-dev
```

---

## 4. Configure environment

```bash
# From project root
cp .env.example .env
```

Edit `.env` with your values. At minimum, configure Reddit OAuth for real data.

---

## 5. Reddit OAuth Setup

1. Go to https://www.reddit.com/prefs/apps
2. Click **"create another app..."**
3. Fill in:
   - **name:** BlackInkSignal
   - **type:** script
   - **redirect uri:** http://localhost:8787 (doesn't matter for script apps)
4. Click **"create app"**
5. Note your credentials:
   - **client_id** — shown under the app name (short string)
   - **client_secret** — labeled "secret"
6. Add to your `.env`:

```env
BIS_REDDIT_CLIENT_ID=your_client_id
BIS_REDDIT_CLIENT_SECRET=your_secret
BIS_REDDIT_USERNAME=your_reddit_username
BIS_REDDIT_PASSWORD=your_reddit_password
BIS_REDDIT_USER_AGENT=BlackInkSignal/0.1 (by /u/your_username)
```

> ⚠️ Use a dedicated Reddit account, not your personal one.

---

## 6. Start the Backend

```bash
cd apps/api
source .venv/bin/activate
export PYTHONPATH="../../packages/core:../../packages/connectors/reddit"

# Load env vars
set -a; source ../../.env; set +a

# Start API server
uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
```

Verify: http://127.0.0.1:8787/health → `{"status":"ok","version":"0.1.0"}`

---

## 7. Start the Scheduler

Open a new terminal:
```bash
cd apps/api
source .venv/bin/activate
export PYTHONPATH="../../packages/core:../../packages/connectors/reddit"
set -a; source ../../.env; set +a

python3 app/scheduler.py
```

You should see:
```
=== Black Ink Signal Scheduler ===
Reddit interval: 5m
Enrichment interval: 2m
Scheduler running. Press Ctrl+C to stop.
```

---

## 8. Start the Desktop App

### Browser mode (development)
```bash
cd apps/desktop
npm run dev
```
Open http://localhost:5173

### Electron mode (native desktop)
```bash
cd apps/desktop
npm run build
npm run electron:dev
```

### Packaged app
```bash
cd apps/desktop
npm run electron:build
# Output in apps/desktop/release/
```

---

## 9. Database Location

SQLite file lives at:
```
black-ink-signal/data/black_ink_signal.db
```

To inspect:
```bash
sqlite3 data/black_ink_signal.db
.tables
SELECT count(*) FROM leads;
SELECT lead_score, title FROM leads ORDER BY lead_score DESC LIMIT 10;
```

---

## 10. Seed / Reset Data

### Seed demo leads
```bash
cd apps/api
source .venv/bin/activate
export PYTHONPATH="../../packages/core:../../packages/connectors/reddit"
python3 app/seed_data.py
```

### Reset database (fresh start)
```bash
rm data/black_ink_signal.db
# Restart the API — tables auto-create on boot
```

### Clear notification history
```bash
rm -rf data/notifications/
```

---

## 11. Troubleshooting

### Reddit returns 403
- You're missing OAuth credentials, or they're wrong
- Check `.env` has all 4 Reddit vars uncommented and correct
- Verify at https://www.reddit.com/prefs/apps that the app exists
- Try from a residential IP (some cloud IPs are blocked)

### API won't start
- Check Python path: `echo $PYTHONPATH` should include both `packages/core` and `packages/connectors/reddit`
- Check venv is activated: `which python3` should point to `.venv/bin/python3`
- Check port 8787 isn't in use: `lsof -i :8787`

### Frontend can't reach API
- Backend must be running on port 8787
- Check CORS (should be allow_origins=["*"] for local dev)
- Check browser console for errors

### No leads appearing
- Run seed: `python3 app/seed_data.py`
- Or wait for scheduler to fetch from Reddit
- Check scheduler logs for errors

### Electron won't start
- Run `npm run build` first (Electron loads from `dist/`)
- Check `electron` is installed: `npx electron --version`

### Scoring seems off
- Run the test suite: `python3 -c "from black_ink_signal_core.scoring import score_lead; ..."`
- Check if data was scored with old v1 engine — rescore all leads via API

---

## Quick Launch (all-in-one)

Three terminals:

```bash
# Terminal 1: API
cd black-ink-signal/apps/api
source .venv/bin/activate && set -a && source ../../.env && set +a
export PYTHONPATH="../../packages/core:../../packages/connectors/reddit"
uvicorn app.main:app --port 8787 --reload

# Terminal 2: Scheduler
cd black-ink-signal/apps/api
source .venv/bin/activate && set -a && source ../../.env && set +a
export PYTHONPATH="../../packages/core:../../packages/connectors/reddit"
python3 app/scheduler.py

# Terminal 3: Desktop
cd black-ink-signal/apps/desktop
npm run dev
```

Open http://localhost:5173 — you're live.
