#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HEARTBEAT_DIR="/var/lib/daily_nexus_update/heartbeats"
LOG_FILE="/var/log/daily_nexus_cleanup.log"

mkdir -p "$HEARTBEAT_DIR"
cd "$ROOT_DIR"

touch "$HEARTBEAT_DIR/cleanup.last_start"

if find ./output -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \; >> "$LOG_FILE" 2>&1; then
  touch "$HEARTBEAT_DIR/cleanup.last_success"
  exit 0
fi

/root/.local/bin/uv run python scripts/cron_notify.py \
  --job-id "cron-cleanup" \
  --message "Scheduled cleanup run failed" \
  --error "See /var/log/daily_nexus_cleanup.log for details" >> "$LOG_FILE" 2>&1 || true

exit 1
