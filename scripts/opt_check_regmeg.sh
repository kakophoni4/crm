#!/usr/bin/env bash
# Inspect Dima @regmeg / lead 345 situation
set -euo pipefail

docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT l.id, l.closed_at IS NOT NULL AS is_closed, l.closed_at,
       c.full_name, c.telegram_username,
       (SELECT count(*) FROM lead_opt_orders o WHERE o.lead_id=l.id AND o.deleted_at IS NULL) AS active,
       (SELECT count(*) FROM lead_opt_orders o WHERE o.lead_id=l.id AND o.deleted_at IS NOT NULL) AS soft_del,
       (SELECT round(coalesce(sum(o.commission_due),0)::numeric,2)
          FROM lead_opt_orders o WHERE o.lead_id=l.id AND o.deleted_at IS NULL) AS commission
FROM leads l
JOIN contacts c ON c.id=l.contact_id
WHERE c.telegram_username ILIKE '%regmeg%'
ORDER BY l.id DESC;
"

echo ""
echo "=== Orders on lead 345 (active) ==="
docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT id, order_no, status, buyer_inn, round(total_volume::numeric,2) AS volume,
       round(commission_due::numeric,2) AS commission, source_filename, deleted_at
FROM lead_opt_orders
WHERE lead_id=345
ORDER BY order_no;
"

echo ""
echo "=== Soft-deleted for regmeg leads ==="
docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT o.id, o.lead_id, o.order_no, o.status, o.buyer_inn,
       round(o.commission_due::numeric,2) AS commission,
       o.source_filename, o.deleted_at, o.deleted_by, u.full_name AS deleted_by_name
FROM lead_opt_orders o
JOIN leads l ON l.id=o.lead_id
JOIN contacts c ON c.id=l.contact_id
LEFT JOIN users u ON u.id=o.deleted_by
WHERE c.telegram_username ILIKE '%regmeg%'
  AND o.deleted_at IS NOT NULL
ORDER BY o.deleted_at DESC;
"

echo ""
echo "=== DELETE logs for leads 345/512/344/244 ==="
docker logs crm-staging-api --since 168h 2>&1 \
  | grep -E 'DELETE /api/v1/leads/(345|512|344|244)/opt-orders/' || echo "(no deletes in api logs)"
