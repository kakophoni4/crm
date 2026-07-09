-- Renumber OPT applications per lead: 1, 2, 3… by created_at (fixes gaps after deletes).
-- Run: docker exec -i crm-staging-postgres psql -U crm -d crm < scripts/deploy/renumber-opt-orders.sql

WITH numbered AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY lead_id ORDER BY created_at ASC, id ASC
        )::INT AS new_no
    FROM lead_opt_orders
)
UPDATE lead_opt_orders AS o
SET order_no = numbered.new_no
FROM numbered
WHERE o.id = numbered.id;

-- Check a specific deal (replace 220):
-- SELECT id, lead_id, order_no, status, source_filename, created_at
-- FROM lead_opt_orders WHERE lead_id = 220 ORDER BY order_no;
