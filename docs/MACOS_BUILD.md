# macOS App Build Guide

## Overview

This builds **Black Ink Signal** as a native macOS application (.app) that:
- Launches from the dock like any Mac app
- Starts the backend + scheduler automatically
- Shows a setup wizard on first run
- Lives in the system tray
- Requires no terminal after initial setup

---

## Prerequisites

```bash
# Node.js 18+ and npm
brew install node

# Python 3.11+
brew install python@3.12

# Icon generation (pick one)
brew install librsvg    # for rsvg-convert (recommended)
# or: brew install inkscape
# or: brew install imagemagick
```

---

## One-Time Setup

### 1. Install dependencies

```bash
cd black-ink-signal

# Python backend
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
cd ../..

# Desktop app
cd apps/desktop
npm install
cd ../..
```

### 2. Generate app icon

```bash
cd apps/desktop
./electron/generate-icon.sh
```

This creates `assets/icon.icns` (macOS), `assets/icon.png` (Linux).

> **Note**: If you don't have rsvg-convert/inkscape/imagemagick, you can also use any
> 1024x1024 PNG and convert it manually:
> ```bash
> mkdir icon.iconset
> sips -z 512 512 your-icon.png --out icon.iconset/icon_512x512.png
> # ... (see generate-icon.sh for all sizes)
> iconutil -c icns icon.iconset
> ```

---

## Build the App

```bash
cd apps/desktop

# Build frontend + package Electron app
npm run electron:build
```

This runs:
1. `vite build` — compiles the React frontend
2. `electron-builder --mac` — packages everything into a .app

### Build output

```
apps/desktop/release/
├── BlackInkSignal-1.0.0-mac-arm64.dmg    ← Apple Silicon
├── BlackInkSignal-1.0.0-mac-x64.dmg      ← Intel
├── BlackInkSignal-1.0.0-mac-arm64.zip    ← Portable (no installer)
├── mac-arm64/
│   └── Black Ink Signal.app              ← The actual app
└── mac-x64/
    └── Black Ink Signal.app
```

---

## Install

### Option A: DMG (recommended)

1. Open `BlackInkSignal-1.0.0-mac-arm64.dmg`
2. Drag **Black Ink Signal** to **Applications**
3. Eject the DMG
4. Open from Applications or Spotlight

### Option B: Direct copy

```bash
cp -r "release/mac-arm64/Black Ink Signal.app" /Applications/
```

### Option C: Run without installing

```bash
open "release/mac-arm64/Black Ink Signal.app"
```

---

## First Launch

1. **Double-click** the app icon (Applications → Black Ink Signal)
2. macOS may ask "Are you sure you want to open it?" → Click **Open**
3. **First-run setup wizard** appears:
   - Enter your Reddit OAuth credentials
   - Or click **"Skip for now"** to use demo data
4. Backend starts automatically
5. Live feed opens

---

## What Happens on Launch

```
App launches
    ├── Detects .env / Reddit credentials
    │   ├── Missing? → Show setup wizard
    │   └── Present? → Continue
    ├── Starts Python FastAPI backend (port 8787)
    ├── Waits for /health to respond OK
    ├── Starts scheduler (Reddit fetch every 5min)
    ├── Opens main window (Live Feed)
    └── Creates system tray icon
```

---

## System Tray

The app lives in your menu bar (◆ icon):
- **Double-click** tray → show window
- **Right-click** tray → Show / Quit
- **Close window** → app stays running in tray
- **Cmd+Q** → fully quits (stops backend + scheduler)

---

## Troubleshooting

### "App is damaged and can't be opened"
```bash
xattr -cr "/Applications/Black Ink Signal.app"
```

### Backend won't start
- Make sure Python 3.11+ is installed: `python3 --version`
- Make sure venv has dependencies: `cd apps/api && source .venv/bin/activate && pip install -r requirements.txt`
- Check port 8787 isn't in use: `lsof -i :8787`

### Icon not showing
- Run `./electron/generate-icon.sh` to regenerate
- Rebuild: `npm run electron:build`

### First-run setup doesn't appear
- Delete `.env` to trigger it: `rm .env`
- Or edit `.env` manually with your credentials

### Performance issues
- SQLite is single-threaded — fine for <50k leads
- If slow, try: `cd apps/api && python3 app/stress_test.py` to benchmark

---

## Development Mode

For development (hot-reload, devtools):

```bash
# Terminal 1: Vite dev server
cd apps/desktop && npm run dev

# Terminal 2: Electron (loads from vite)
cd apps/desktop && npm run electron:dev
```

---

## Architecture

```
Black Ink Signal.app/
├── Contents/
│   ├── MacOS/
│   │   └── Black Ink Signal        ← Electron binary
│   ├── Resources/
│   │   ├── app/                    ← Bundled app
│   │   │   ├── dist/              ← Compiled frontend
│   │   │   ├── electron/          ← Main process + setup
│   │   │   ├── packages/          ← Python core + connectors
│   │   │   └── apps/api/          ← FastAPI server
│   │   ├── icon.icns              ← App icon
│   │   └── app.asar               ← (or packed asar)
│   └── Info.plist
└── (code signature)
```

The app spawns Python as a child process. No system-wide Python installation is modified.

---

## Creating a Desktop Shortcut

If you installed to `/Applications`, it's already in:
- **Launchpad** (grid view)
- **Spotlight** (Cmd+Space → "Black Ink Signal")
- **Dock** (drag from Applications to dock)

To pin to dock:
1. Open the app
2. Right-click its dock icon
3. Options → Keep in Dock

---

## Updating

1. Download new `.dmg`
2. Drag to Applications (replace existing)
3. Relaunch

Your data (`data/black_ink_signal.db`) and credentials (`.env`) persist between updates.
