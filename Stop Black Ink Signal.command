#!/bin/bash
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_PORT=8787
DESKTOP_PORT=5173

find_pid_by_port() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
}

stop_pid_list() {
  local label="$1"
  shift
  local pids=("$@")
  if [[ ${#pids[@]} -eq 0 || -z "${pids[0]:-}" ]]; then
    echo "$label: not running"
    return 0
  fi

  echo "Stopping $label: ${pids[*]}"
  kill "${pids[@]}" 2>/dev/null || true
  sleep 1

  local survivors=()
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      survivors+=("$pid")
    fi
  done

  if [[ ${#survivors[@]} -gt 0 ]]; then
    echo "Force stopping $label: ${survivors[*]}"
    kill -9 "${survivors[@]}" 2>/dev/null || true
  fi

  echo "$label: stopped"
}

echo ""
echo "=== Stop Black Ink Signal ==="
echo "Project: $ROOT_DIR"
echo ""

mapfile -t api_pids < <(find_pid_by_port "$API_PORT")
mapfile -t desktop_pids < <(find_pid_by_port "$DESKTOP_PORT")

stop_pid_list "API" "${api_pids[@]:-}"
stop_pid_list "Desktop" "${desktop_pids[@]:-}"

echo ""
echo "Done."
