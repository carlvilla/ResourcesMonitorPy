#!/usr/bin/env bash
# Start the macOS Monitor stack:
#   1. Build & launch MySQL + Streamlit in Docker
#   2. Start the host-side metric collector (needs native macOS psutil access)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COLLECTOR="$SCRIPT_DIR/collector/collector.py"
PID_FILE="$SCRIPT_DIR/.collector.pid"

# ── Sanity checks ──────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
  echo "Docker not found. Please install Docker Desktop for Mac." >&2
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo "No .env found — copying from .env.example"
  cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
  echo "   Edit .env to set your API keys before running again."
fi

# ── Docker stack ───────────────────────────────────────────────────────────

echo "Building and starting Docker services…"
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d --build

echo "Waiting for MySQL to be ready…"
until docker compose -f "$SCRIPT_DIR/docker-compose.yml" \
    exec -T mysql mysqladmin ping -h 127.0.0.1 --silent 2>/dev/null; do
  sleep 2
done
echo "MySQL is ready"

# ── Collector (host-side) ──────────────────────────────────────────────────

if [[ -f "$PID_FILE" ]]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Collector already running (PID $OLD_PID), skipping."
  else
    rm -f "$PID_FILE"
  fi
fi

if [[ ! -f "$PID_FILE" ]]; then
  echo "Starting host-side metric collector…"
  # Load .env so the collector inherits DB_ vars on the host
  set -a; source "$SCRIPT_DIR/.env"; set +a
  nohup uv run "$COLLECTOR" >> "$SCRIPT_DIR/collector.log" 2>&1 &
  echo $! > "$PID_FILE"
  sleep 1
  if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Collector started (PID $(cat "$PID_FILE")) — logs: collector.log"
  else
    echo "Collector failed to start — see collector.log" >&2
    exit 1
  fi
fi

# ── Done ───────────────────────────────────────────────────────────────────

echo ""
echo "Monitor is live → http://localhost:8501"
echo "   Stop with: ./stop.sh"