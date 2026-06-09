#!/bin/bash
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT_DIR/apps/api"
DESKTOP_DIR="$ROOT_DIR/apps/desktop"
LOG_DIR="$ROOT_DIR/.launcher-logs"
API_LOG="$LOG_DIR/api.log"
DESKTOP_LOG="$LOG_DIR/desktop.log"
API_PORT=8787
DESKTOP_PORT=5173
APP_URL="http://localhost:5173"
DB_PATH="$ROOT_DIR/data/black_ink_signal.db"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NPM_BIN="${NPM_BIN:-npm}"

mkdir -p "$LOG_DIR"

auto_open() {
  if command -v open >/dev/null 2>&1; then
    open "$APP_URL" >/dev/null 2>&1 || true
  fi
}

find_pid_by_port() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1
}

start_api() {
  local api_pid
  api_pid="$(find_pid_by_port "$API_PORT")"
  if [[ -n "$api_pid" ]]; then
    echo "API: running (pid $api_pid)"
    return 0
  fi

  echo "Starting API..."
  (
    cd "$API_DIR" || exit 1
    PYTHONPATH=../../packages:../../packages/core \
    "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
  ) >>"$API_LOG" 2>&1 &

  sleep 2
  api_pid="$(find_pid_by_port "$API_PORT")"
  if [[ -n "$api_pid" ]]; then
    echo "API: running (pid $api_pid)"
  else
    echo "API: failed to start (check $API_LOG)"
  fi
}

start_desktop() {
  local desktop_pid
  desktop_pid="$(find_pid_by_port "$DESKTOP_PORT")"
  if [[ -n "$desktop_pid" ]]; then
    echo "Desktop: running (pid $desktop_pid)"
    return 0
  fi

  echo "Starting Desktop..."
  (
    cd "$DESKTOP_DIR" || exit 1
    "$NPM_BIN" run dev -- --host 127.0.0.1 --port "$DESKTOP_PORT"
  ) >>"$DESKTOP_LOG" 2>&1 &

  sleep 3
  desktop_pid="$(find_pid_by_port "$DESKTOP_PORT")"
  if [[ -n "$desktop_pid" ]]; then
    echo "Desktop: running (pid $desktop_pid)"
  else
    echo "Desktop: failed to start (check $DESKTOP_LOG)"
  fi
}

echo ""
echo "=== Black Ink Signal Launcher ==="
echo "Project: $ROOT_DIR"
echo ""

start_api
start_desktop

if [[ -f "$DB_PATH" ]]; then
  echo "Database: found"
else
  echo "Database: missing ($DB_PATH)"
fi

echo "App URL: $APP_URL"
echo "Logs:"
echo "  API: $API_LOG"
echo "  Desktop: $DESKTOP_LOG"
echo ""
echo "Opening app in browser..."
auto_open

echo "Done. You can close this window."
