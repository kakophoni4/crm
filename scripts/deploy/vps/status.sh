#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

API_PUBLIC="${BASE_URL:-${SMOKE_API_URL:-https://api.bttsrvvrs.org}}"
FRONTEND_PUBLIC="${FRONTEND_URL:-${SMOKE_APP_URL:-https://chat.bttsrvvrs.org}}"
# Strip trailing /api/v1 if present in env
API_PUBLIC="${API_PUBLIC%/api/v1}"
API_PUBLIC="${API_PUBLIC%/}"

echo "=== Docker ==="
compose ps

echo ""
echo "=== Health (docker bridge ${VPS_API_HOST}) ==="
curl -sf "http://${VPS_API_HOST}:${VPS_API_PORT}/healthz" && echo "" || echo "API: FAIL"
curl -sf -o /dev/null -w "Frontend HTTP %{http_code}\n" "http://${VPS_FRONTEND_HOST}:${VPS_FRONTEND_PORT}/"

echo ""
echo "=== Health (via Caddy, HTTPS) ==="
curl -sf "${API_PUBLIC}/healthz" && echo "" || echo "${API_PUBLIC}/healthz: FAIL"
curl -sf -o /dev/null -w "${FRONTEND_PUBLIC} HTTPS %{http_code}\n" "${FRONTEND_PUBLIC}/" || echo "${FRONTEND_PUBLIC} (HTTPS): FAIL"

echo ""
echo "=== Vaultwarden (Bitwarden) ==="
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx vaultwarden; then
  curl -sf http://127.0.0.1:19180/alive && echo "" || echo "vaultwarden local: FAIL"
  curl -sf https://huitawarden.bttsrvvrs.org/alive && echo "" || echo "huitawarden.bttsrvvrs.org (HTTPS): FAIL"
else
  echo "vaultwarden: not running (install: bash scripts/deploy/vps/install-bitwarden.sh)"
fi

echo ""
echo "=== Port 443 listeners (SNI split) ==="
ss -tlnp 2>/dev/null | grep ':443' || echo "nothing on :443"
