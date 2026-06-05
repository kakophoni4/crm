#!/usr/bin/env bash
# Rebuild and restart CRM stack on VPS (after git pull or file sync).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

"$ROOT/scripts/deploy/vps/check-env.sh"

echo "Building api, worker, frontend..."
compose build api worker frontend

echo "Starting stack..."
compose up -d

echo "Waiting for API health..."
for i in $(seq 1 90); do
  if curl -sf http://127.0.0.1:19001/healthz >/dev/null 2>&1; then
    echo "API healthy (${i}s)."
    break
  fi
  if [[ "$i" -eq 90 ]]; then
    echo "WARNING: API not healthy after 90s — check: docker logs crm-staging-api --tail 80" >&2
  fi
  sleep 1
done

echo ""
compose ps
echo ""
"$ROOT/scripts/deploy/vps/status.sh"
