#!/usr/bin/env bash
# Quick check: what is lead 363 order_no 18 / nearby, and line overlap with repaired orders.
set -euo pipefail

docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT o.id, o.order_no, o.status,
       o.deleted_at IS NOT NULL AS soft_del,
       o.source_filename,
       o.total_volume, o.commission_due,
       o.created_at,
       (SELECT count(*) FROM lead_opt_order_lines ln WHERE ln.order_id = o.id) AS lines
FROM lead_opt_orders o
WHERE o.lead_id = 363
ORDER BY o.created_at, o.id;
"

echo ""
echo "=== order_no = 18 (active) ==="
docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT o.id, o.order_no, o.source_filename, o.commission_due, o.deleted_at
FROM lead_opt_orders o
WHERE o.lead_id = 363 AND o.order_no = 18;
"

echo ""
echo "=== lines of current no=18 vs repaired 178/179/249/250/253 ==="
docker exec crm-staging-postgres psql -U crm -d crm -c "
WITH target AS (
  SELECT id FROM lead_opt_orders
  WHERE lead_id = 363 AND order_no = 18 AND deleted_at IS NULL
  LIMIT 1
),
t_lines AS (
  SELECT ln.supplier_inn, ln.document_date::date AS d, round(ln.amount::numeric, 2) AS amount
  FROM lead_opt_order_lines ln
  JOIN target t ON t.id = ln.order_id
),
repaired AS (
  SELECT unnest(ARRAY[178,179,249,250,253]) AS order_id
)
SELECT r.order_id AS repaired_order,
       o.order_no AS repaired_no,
       o.source_filename,
       count(*) AS overlap_lines
FROM repaired r
JOIN lead_opt_orders o ON o.id = r.order_id
JOIN lead_opt_order_lines ln ON ln.order_id = o.id
JOIN t_lines t ON t.supplier_inn = ln.supplier_inn
              AND t.d = ln.document_date::date
              AND t.amount = round(ln.amount::numeric, 2)
GROUP BY r.order_id, o.order_no, o.source_filename
ORDER BY overlap_lines DESC;
"
