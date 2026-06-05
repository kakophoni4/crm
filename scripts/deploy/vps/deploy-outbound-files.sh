#!/usr/bin/env bash
# Deploy operator->client files + UI input fixes. Run on VPS after scp from Windows.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

echo "=== Rebuild api, worker, frontend ==="
compose build api worker frontend
compose up -d api worker frontend

echo ""
echo "=== Restart Telegram bridge ==="
bash "$ROOT/scripts/bots/tg_crm_bridge/update_bridge.sh"

echo ""
echo "Migration 0040_uploaded_files runs automatically on api startup."
compose ps api worker frontend
echo "Done. Ctrl+F5 in browser."
