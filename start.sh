#!/usr/bin/env bash
# Start the resources Monitor stack:
#   1. Build & launch MySQL + Streamlit in Docker
#   2. Start the host-side metric collector (needs native macOS psutil access)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COLLECTOR="$SCRIPT_DIR/collector/collector.py"
PID_FILE="$SCRIPT_DIR/.collector.pid" # Collects the PID of the collector process to be able to kill it
SUDO_PID_FILE="$SCRIPT_DIR/.sudo_refresher.pid" # Background keep-alive for sudo cache (powermetrics)
DOCKER_LOGS_PID_FILE="$SCRIPT_DIR/.docker_logs.pid" # Background `docker compose logs -f` writer
DOCKER_LOGS_FILE="$SCRIPT_DIR/logs/docker_containers.log"

# ── Sanity checks ──────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
  echo "Docker not found. Please install it first in your system." >&2
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo "No .env found — copying from .env.example"
  cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
  echo "   Edit .env to set your API keys before running again."
fi

# Load .env once for the rest of the script (Docker compose, collector, final echo).
set -a; source "$SCRIPT_DIR/.env"; set +a

# ── Sudo credential cache (for powermetrics in the collector) ─────────────
# powermetrics requires root. Instead of editing /etc/sudoers.d, we prime the
# sudo credential cache once and keep it warm with a background refresher.
# stop.sh kills the refresher and runs `sudo -k` to clear the cache.

echo "Sudo permissions required to retrieve system information…" # needed for powermetrics interrupt sampling
sudo -v

if [[ -f "$SUDO_PID_FILE" ]] && kill -0 "$(cat "$SUDO_PID_FILE")" 2>/dev/null; then
  echo "Sudo refresher already running (PID $(cat "$SUDO_PID_FILE"))."
else
  ( while true; do sudo -n true 2>/dev/null || exit; sleep 60; done ) &
  echo $! > "$SUDO_PID_FILE"
  echo "Sudo refresher started (PID $(cat "$SUDO_PID_FILE"))."
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

# ── Docker container logs → file ───────────────────────────────────────────

mkdir -p "$SCRIPT_DIR/logs"
if [[ -f "$DOCKER_LOGS_PID_FILE" ]] && kill -0 "$(cat "$DOCKER_LOGS_PID_FILE")" 2>/dev/null; then
  echo "Docker log tail already running (PID $(cat "$DOCKER_LOGS_PID_FILE"))."
else
  nohup docker compose -f "$SCRIPT_DIR/docker-compose.yml" logs -f --no-color --timestamps \
    >> "$DOCKER_LOGS_FILE" 2>&1 &
  echo $! > "$DOCKER_LOGS_PID_FILE"
  echo "Docker logs → $DOCKER_LOGS_FILE (PID $(cat "$DOCKER_LOGS_PID_FILE"))"
fi

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
  nohup uv run "$COLLECTOR" >> "$SCRIPT_DIR/logs/collector.log" 2>&1 &
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
echo "Monitor is live → http://localhost:${STREAMLIT_PORT}"
echo "   Stop with: ./stop.sh"