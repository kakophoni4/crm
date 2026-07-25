#!/usr/bin/env bash
# Restore document_number + crm_id for remainder lines from soft-deleted 254 (испр)
# onto order 253 (заявка 16). Then requeue Mole.
set -euo pipefail

echo "=== before (253 lines matching испр amounts) ==="
docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT line_no, document_number, crm_id, document_date, amount
FROM lead_opt_order_lines
WHERE order_id = 253 AND amount IN (132600, 568365)
ORDER BY line_no;
"

echo ""
echo "=== apply restore from 254 ==="
docker exec crm-staging-postgres psql -U crm -d crm -v ON_ERROR_STOP=1 -c "
UPDATE lead_opt_order_lines cur
SET crm_id = old.crm_id,
    document_number = old.document_number
FROM lead_opt_order_lines old
WHERE old.order_id = 254
  AND cur.order_id = 253
  AND cur.supplier_inn = old.supplier_inn
  AND cur.document_date::date = old.document_date::date
  AND round(cur.amount::numeric, 2) = round(old.amount::numeric, 2);
"

echo ""
echo "=== after ==="
docker exec crm-staging-postgres psql -U crm -d crm -c "
SELECT line_no, document_number, crm_id, document_date, amount
FROM lead_opt_order_lines
WHERE order_id = 253 AND amount IN (132600, 568365)
ORDER BY line_no;
"

echo ""
echo "=== requeue 253 to Mole ==="
docker exec -e PYTHONUNBUFFERED=1 crm-staging-api python -c "
import asyncio
from sqlalchemy import text
from app.shared.db import get_session_factory
from app.modules.leads.opt.queue import enqueue_opt_submit

async def main():
    sf = get_session_factory()
    async with sf() as s:
        await s.execute(text(\"UPDATE lead_opt_orders SET status='queued', submission_error=NULL WHERE id=253\"))
        await s.commit()
    await enqueue_opt_submit(253)
    print('requeued 253')
asyncio.run(main())
"

echo "DONE partial restore order 253 from испр.xlsx"
