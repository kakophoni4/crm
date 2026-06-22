#!/usr/bin/env bash
# Keep Asterisk config synchronized with CRM DB.
set -euo pipefail

INTERVAL="${TELEPHONY_SYNC_INTERVAL_SECONDS:-15}"

while true; do
  bash scripts/deploy/vps/telephony-sync.sh || true
  sleep "$INTERVAL"
done
