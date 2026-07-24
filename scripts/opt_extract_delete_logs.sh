#!/usr/bin/env bash
# Extract OPT order DELETE events (lead_id / order_id) from API logs.
set -euo pipefail

SINCE="${1:-168h}"
OUT="${2:-/tmp/opt_delete_events.txt}"

echo "Scanning crm-staging-api logs since ${SINCE} ..."
{
  echo "# DELETE opt-orders from access/app logs since ${SINCE}"
  docker logs crm-staging-api --since "$SINCE" 2>&1 \
    | grep -Ei 'DELETE.*/leads/[0-9]+/opt-orders/[0-9]+|opt\.order\.deleted|"lead_id".*"order_id"' \
    | tee /dev/stderr \
    | sed -nE 's/.*\/leads\/([0-9]+)\/opt-orders\/([0-9]+).*/lead=\1 order=\2/p'
} | tee "$OUT"

echo ""
echo "Unique lead/order pairs:"
grep -E '^lead=' "$OUT" | sort -u || true
echo ""
echo "Saved: $OUT"
echo "Also try nginx/caddy if present:"
echo "  grep -REi 'DELETE.*/opt-orders/' /var/log/nginx /var/log/caddy 2>/dev/null | tail"
