#!/usr/bin/env bash
# Stop the metric collector and the Docker stack.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.collector.pid"
SUDO_PID_FILE="$SCRIPT_DIR/.sudo_refresher.pid"
DOCKER_LOGS_PID_FILE="$SCRIPT_DIR/.docker_logs.pid"

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

# ── Sudo refresher ─────────────────────────────────────────────────────────

if [[ -f "$SUDO_PID_FILE" ]]; then
  SUDO_PID=$(cat "$SUDO_PID_FILE")
  if kill -0 "$SUDO_PID" 2>/dev/null; then
    echo "Stopping sudo refresher (PID $SUDO_PID)…"
    kill "$SUDO_PID" 2>/dev/null || true
  fi
  rm -f "$SUDO_PID_FILE"
fi
sudo -k 2>/dev/null || true

# ── Docker log tail ────────────────────────────────────────────────────────

if [[ -f "$DOCKER_LOGS_PID_FILE" ]]; then
  DLOG_PID=$(cat "$DOCKER_LOGS_PID_FILE")
  if kill -0 "$DLOG_PID" 2>/dev/null; then
    echo "Stopping Docker log tail (PID $DLOG_PID)…"
    kill "$DLOG_PID" 2>/dev/null || true
  fi
  rm -f "$DOCKER_LOGS_PID_FILE"
fi

# ── Docker stack ───────────────────────────────────────────────────────────

echo "Stopping Docker services…"
docker compose -f "$SCRIPT_DIR/docker-compose.yml" down

echo "All services stopped."
