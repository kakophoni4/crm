#!/usr/bin/env bash
# Legacy minimal smoke (healthz + frontend). Prefer: scripts/smoke/staging_smoke.sh
# Post-deploy smoke checks (API healthz + frontend HTTP 200).
# Usage:
#   STAGING_SMOKE_API_URL=https://api.example.com \
#   STAGING_SMOKE_APP_URL=https://app.example.com \
#   ./scripts/deploy/post_deploy_smoke.sh
set -euo pipefail

API_URL="${STAGING_SMOKE_API_URL:-${1:-http://localhost:8000}}"
APP_URL="${STAGING_SMOKE_APP_URL:-${2:-http://localhost:8080}}"
API_URL="${API_URL%/}"
APP_URL="${APP_URL%/}"

echo "Smoke: GET ${API_URL}/healthz"
curl -sfS --max-time 30 "${API_URL}/healthz" >/dev/null

echo "Smoke: GET ${APP_URL}/"
code="$(curl -sfS --max-time 30 -o /dev/null -w '%{http_code}' "${APP_URL}/")"
if [[ "$code" != "200" ]]; then
  echo "Expected HTTP 200 from frontend, got ${code}" >&2
  exit 1
fi

echo "Post-deploy smoke passed."
