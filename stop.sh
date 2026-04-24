#!/usr/bin/env bash
# Stop the metric collector and the Docker stack.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.collector.pid"

# ── Collector ─────────────────────────────────────────────────────────────

if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping collector (PID $PID)…"
    kill "$PID"
  else
    echo "Collector was not running."
  fi
  rm -f "$PID_FILE"
else
  echo "No collector PID file found."
fi

# ── Docker stack ───────────────────────────────────────────────────────────

echo "Stopping Docker services…"
docker compose -f "$SCRIPT_DIR/docker-compose.yml" down

echo "All services stopped."
