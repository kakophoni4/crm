#!/usr/bin/env bash
# Rebuild and restart CRM stack on VPS (after git pull or file sync).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

echo "Building api, worker, frontend..."
compose build api worker frontend

echo "Starting stack..."
compose up -d

echo ""
compose ps
echo ""
"$ROOT/scripts/deploy/vps/status.sh"
