#!/usr/bin/env bash
# 1) Restore РС numbers from soft-deleted испр (254) onto order 253
# 2) Re-queue all 5 repaired orders so Mole gets full Реестр again
set -euo pipefail

echo "=== state 254 crm_ids ==="
docker exec crm-staging-postgres psql -U crm -d crm -c \
  "SELECT id, crm_id, document_number, amount FROM lead_opt_order_lines WHERE order_id=254;"

echo "=== state 253 tail lines ==="
docker exec crm-staging-postgres psql -U crm -d crm -c \
  "SELECT line_no, crm_id, document_number, amount FROM lead_opt_order_lines WHERE order_id=253 AND amount IN (132600,568365) ORDER BY line_no;"

echo "=== restore 254 -> 253 ==="
docker exec crm-staging-postgres psql -U crm -d crm -v ON_ERROR_STOP=1 -c "
BEGIN;

CREATE TEMP TABLE _r254 AS
SELECT supplier_inn,
       document_date::date AS d,
       round(amount::numeric,2) AS amount,
       crm_id,
       document_number
FROM lead_opt_order_lines
WHERE order_id = 254
  AND crm_id NOT LIKE 'retired-%';

UPDATE lead_opt_order_lines
SET crm_id = 'retired-254-' || id::text
WHERE order_id = 254
  AND crm_id NOT LIKE 'retired-%';

UPDATE lead_opt_order_lines cur
SET crm_id = r.crm_id,
    document_number = r.document_number
FROM _r254 r
WHERE cur.order_id = 253
  AND cur.supplier_inn = r.supplier_inn
  AND cur.document_date::date = r.d
  AND round(cur.amount::numeric, 2) = r.amount;

SELECT line_no, document_number, crm_id, amount
FROM lead_opt_order_lines
WHERE order_id = 253 AND amount IN (132600, 568365)
ORDER BY line_no;

COMMIT;
"

echo "=== requeue 178,179,249,250,253 ==="
docker exec -e PYTHONUNBUFFERED=1 crm-staging-api python -c "
import asyncio
from sqlalchemy import text
from app.shared.db import get_session_factory
from app.modules.leads.opt.queue import enqueue_opt_submit

IDS = [178, 179, 249, 250, 253]

async def main():
    sf = get_session_factory()
    async with sf() as s:
        await s.execute(
            text(\"UPDATE lead_opt_orders SET status='queued', submission_error=NULL WHERE id = ANY(:ids)\"),
            {'ids': IDS},
        )
        await s.commit()
    for oid in IDS:
        await enqueue_opt_submit(oid)
        print('requeued', oid)

asyncio.run(main())
"

echo "DONE — wait ~30s then check Mole sums / CRM document_number"
