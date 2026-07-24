#!/usr/bin/env bash
# Diagnostics: what OPT orders/leads may have been hard-deleted recently.
set -euo pipefail

echo "=== 1) Soft-deleted in DB (after migration 0085) ==="
docker exec crm-staging-api python scripts/opt_deleted_orders.py --list --limit 50 || true

echo ""
echo "=== 2) API/worker logs: DELETE opt-orders / opt.order.deleted (last 72h) ==="
docker logs crm-staging-api --since 72h 2>&1 | grep -Ei 'opt\.order\.deleted|DELETE.*/opt-orders/' | tail -n 80 || true
docker logs crm-staging-worker --since 72h 2>&1 | grep -Ei 'opt\.order\.deleted|lead_purge' | tail -n 40 || true

echo ""
echo "=== 3) Open leads — order counts ==="
docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT l.id AS lead_id,
       left(coalesce(l.title,''), 60) AS title,
       l.created_at::date,
       (SELECT count(*) FROM lead_opt_orders o WHERE o.lead_id = l.id AND o.deleted_at IS NULL) AS active_orders,
       (SELECT count(*) FROM lead_opt_orders o WHERE o.lead_id = l.id AND o.deleted_at IS NOT NULL) AS soft_deleted
FROM leads l
WHERE l.closed_at IS NULL
ORDER BY l.id DESC
LIMIT 40;
" || docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT l.id AS lead_id,
       left(coalesce(l.title,''), 60) AS title,
       (SELECT count(*) FROM lead_opt_orders o WHERE o.lead_id = l.id) AS orders
FROM leads l
WHERE l.closed_at IS NULL
ORDER BY l.id DESC
LIMIT 40;
"

echo ""
echo "=== 4) Restore soft-deleted (example) ==="
echo "docker exec crm-staging-api python scripts/opt_deleted_orders.py --restore ORDER_ID"
echo ""
echo "=== 5) Hard-deleted (no row left): restore from Excel in chat or from 1C by CRMid ==="
echo "Re-upload source xlsx on the lead, or ask admin to PUT/POST from Mole if crm_id known."
