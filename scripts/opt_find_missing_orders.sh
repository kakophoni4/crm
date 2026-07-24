#!/usr/bin/env bash
# Find leads that likely lost OPT orders (xlsx in chat, zero active orders).
set -euo pipefail

echo "=== DELETE / soft-delete events in API logs (7d) ==="
docker logs crm-staging-api --since 168h 2>&1 \
  | grep -Ei 'opt\.order\.deleted|DELETE.*/leads/.*/opt-orders/' \
  | tail -n 120 || true

echo ""
echo "=== Leads with spreadsheet attachments but 0 active OPT orders ==="
docker exec crm-staging-postgres psql -U crm -d crm -c "
WITH xlsx_leads AS (
  SELECT DISTINCT m.lead_id
  FROM messages m
  CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(m.attachments)='array' THEN m.attachments ELSE '[]'::jsonb END
  ) att
  WHERE m.lead_id IS NOT NULL
    AND (
      lower(coalesce(att->>'filename', att->>'name','')) LIKE '%.xlsx'
      OR lower(coalesce(att->>'filename', att->>'name','')) LIKE '%.xlsm'
      OR lower(coalesce(att->>'filename', att->>'name','')) LIKE '%.xls'
    )
)
SELECT l.id AS lead_id,
       l.created_at::date,
       left(coalesce(l.title,''), 50) AS title,
       (SELECT count(*) FROM lead_opt_orders o
         WHERE o.lead_id=l.id AND o.deleted_at IS NULL) AS active_orders,
       (SELECT count(*) FROM lead_opt_orders o
         WHERE o.lead_id=l.id AND o.deleted_at IS NOT NULL) AS soft_deleted,
       (SELECT string_agg(DISTINCT left(coalesce(att->>'filename', att->>'name'), 40), ' | ')
          FROM messages m2
          CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(m2.attachments)='array' THEN m2.attachments ELSE '[]'::jsonb END
          ) att
          WHERE m2.lead_id = l.id
            AND (
              lower(coalesce(att->>'filename', att->>'name','')) LIKE '%.xlsx'
              OR lower(coalesce(att->>'filename', att->>'name','')) LIKE '%.xlsm'
              OR lower(coalesce(att->>'filename', att->>'name','')) LIKE '%.xls'
            )
       ) AS xlsx_names
FROM leads l
JOIN xlsx_leads x ON x.lead_id = l.id
WHERE l.closed_at IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM lead_opt_orders o
    WHERE o.lead_id = l.id AND o.deleted_at IS NULL
  )
ORDER BY l.id DESC
LIMIT 60;
"

echo ""
echo "=== Failed OPT orders still in DB (not deleted) ==="
docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT id, lead_id, order_no, status, buyer_inn,
       round(commission_due::numeric,2) AS commission,
       left(coalesce(submission_error,''), 80) AS err,
       updated_at
FROM lead_opt_orders
WHERE deleted_at IS NULL AND status='failed'
ORDER BY updated_at DESC
LIMIT 30;
"
