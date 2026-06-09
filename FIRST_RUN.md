# FIRST_RUN.md — Get Running in 5 Minutes

## What This Is

**Black Ink Signal** — a desktop app that monitors Reddit for potential tattoo clients in Edmonton/Alberta, scores them, and shows you a live feed of hot leads. One click to launch after setup.

---

## Requirements

- **macOS 13+** (Ventura or later)
- **Python 3.11+** — check: `python3 --version`
- **Node.js 18+** — check: `node --version`
- **npm 9+** — check: `npm --version`

If missing:
```bash
brew install python@3.12 node
```

---

## Step 1: Unzip

```bash
cd ~/Downloads
unzip black-ink-signal.zip
cd black-ink-signal
```

---

## Step 2: Install Python Dependencies

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
cd ../..
```

---

## Step 3: Install Node Dependencies

```bash
cd apps/desktop
npm install
cd ../..
```

---

## Step 4: Build the Mac App

```bash
cd apps/desktop
npm run electron:build
```

Wait ~60 seconds. When done, your app is at:

```
apps/desktop/release/mac-arm64/Black Ink Signal.app
```

(Intel Mac: `apps/desktop/release/mac-x64/Black Ink Signal.app`)

---

## Step 5: Install

**Option A — Run directly:**
```bash
open "apps/desktop/release/mac-arm64/Black Ink Signal.app"
```

**Option B — Install to Applications:**
```bash
cp -r "apps/desktop/release/mac-arm64/Black Ink Signal.app" /Applications/
```
Then find it in Launchpad or Spotlight.

**Option C — Desktop shortcut:**
```bash
cp -r "apps/desktop/release/mac-arm64/Black Ink Signal.app" ~/Desktop/
```

---

## Step 6: First Launch

1. Double-click **Black Ink Signal**
2. macOS may warn "unidentified developer" → right-click → Open → Open
3. **Setup wizard** appears:
   - Enter Reddit OAuth credentials (see below)
   - OR click **Skip for now** (uses demo data)
4. App starts. Live feed shows leads.

---

## Reddit OAuth (for real data)

1. Go to https://www.reddit.com/prefs/apps
2. Click **"create another app..."**
3. Settings:
   - Name: `BlackInkSignal`
   - Type: **script**
   - Redirect URI: `http://localhost:8787`
4. Click **"create app"**
5. Note the **client ID** (short string under app name) and **secret**
6. Enter these in the setup wizard on first launch

---

## After Setup

- **One click** to launch
- Backend starts automatically
- Scheduler fetches Reddit every 5 minutes
- Hot leads trigger desktop notifications
- Close window → app stays in menu bar tray
- Cmd+Q → fully quit

---

## Troubleshooting

### "App is damaged and can't be opened"
```bash
xattr -cr "/Applications/Black Ink Signal.app"
```

### "Cannot be opened because the developer cannot be verified"
Right-click the app → Open → Open

### Build fails
```bash
# Make sure you're in the right folder
cd apps/desktop
ls package.json  # should exist

# Make sure node_modules exists
npm install

# Try again
npm run electron:build
```

### Python not found during launch
The app looks for Python in this order:
1. `apps/api/.venv/bin/python3` (your venv)
2. `/opt/homebrew/bin/python3` (Homebrew Apple Silicon)
3. `/usr/local/bin/python3` (Homebrew Intel)
4. `/usr/bin/python3` (system)

Make sure one of these exists.

---

## Summary

```
unzip → install deps → npm run electron:build → double-click app → done
```

Total time: ~5 minutes.
