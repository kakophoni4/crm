#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

echo "=== Docker ==="
compose ps

echo ""
echo "=== Health (local) ==="
curl -sf http://127.0.0.1:19001/healthz && echo "" || echo "API: FAIL"
curl -sf -o /dev/null -w "Frontend HTTP %{http_code}\n" http://127.0.0.1:19090/

echo ""
echo "=== Health (via nginx, HTTPS) ==="
curl -sf https://api.crmkanasha.org/healthz && echo "" || echo "api.crmkanasha.org (HTTPS): FAIL"
curl -sf -o /dev/null -w "app.crmkanasha.org HTTPS %{http_code}\n" https://app.crmkanasha.org/ || echo "app.crmkanasha.org (HTTPS): FAIL"

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
