#!/usr/bin/env bash
# Rebuild and restart CRM stack on VPS (after git pull or file sync).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

bash "$ROOT/scripts/deploy/vps/check-env.sh"

echo "Building api, worker, frontend, speech..."
compose build api worker frontend speech

echo "Starting stack..."
compose up -d

echo "Waiting for API health..."
for i in $(seq 1 90); do
  if curl -sf "http://${VPS_API_HOST}:${VPS_API_PORT}/healthz" >/dev/null 2>&1; then
    echo "API healthy (${i}s)."
    break
  fi
  if [[ "$i" -eq 90 ]]; then
    echo "WARNING: API not healthy after 90s — check: docker logs crm-staging-api --tail 80" >&2
  fi
  sleep 1
done

echo "Checking speech from API..."
compose exec -T api python - <<'PYTHON'
import time
import httpx
from app.shared.settings import get_settings

url = get_settings().speech_service_url.rstrip('/') + '/health'
with httpx.Client(timeout=3, trust_env=False) as client:
    for attempt in range(30):
        try:
            response = client.get(url)
            response.raise_for_status()
            if response.json().get('ok') is True:
                print('Speech reachable from API.')
                break
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(2)
    else:
        raise SystemExit('ERROR: API cannot reach speech. Check Compose networks and speech logs.')
PYTHON

echo ""
compose ps
echo ""
bash "$ROOT/scripts/deploy/vps/status.sh"
