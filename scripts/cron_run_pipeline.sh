#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HEARTBEAT_DIR="/var/lib/daily_nexus_update/heartbeats"
LOG_FILE="/var/log/daily_nexus_update.log"

mkdir -p "$HEARTBEAT_DIR"
cd "$ROOT_DIR"

touch "$HEARTBEAT_DIR/pipeline.last_start"

if /root/.local/bin/uv run python -m app.cli --topics tech finance crypto geopolitics --publish-to-youtube >> "$LOG_FILE" 2>&1; then
  touch "$HEARTBEAT_DIR/pipeline.last_success"
  exit 0
fi

/root/.local/bin/uv run python scripts/cron_notify.py \
  --job-id "cron-pipeline" \
  --message "Scheduled pipeline run failed" \
  --error "See /var/log/daily_nexus_update.log for details" >> "$LOG_FILE" 2>&1 || true

exit 1
