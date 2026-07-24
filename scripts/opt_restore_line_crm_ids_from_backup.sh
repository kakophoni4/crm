#!/usr/bin/env bash
# Restore old OPT line crm_id + document_number from a Postgres dump (before repair).
# Run on VPS host as root. Read-only until --apply.
#
# Usage:
#   bash scripts/opt_restore_line_crm_ids_from_backup.sh
#   bash scripts/opt_restore_line_crm_ids_from_backup.sh --apply
#   DUMP=/root/crm-backups/postgres/crm_20260724_030001.dump bash scripts/opt_restore_line_crm_ids_from_backup.sh --apply
#
set -euo pipefail

APPLY=0
REQUEUE=1
ORDERS="${ORDERS:-178,179,249,250,253}"
BACKUP_DIR="${BACKUP_DIR:-/root/crm-backups/postgres}"
DUMP="${DUMP:-}"

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --no-requeue) REQUEUE=0 ;;
    --dry-run) APPLY=0 ;;
  esac
done

echo "=== available dumps (pick one BEFORE repair ~12:43 UTC) ==="
ls -lt "$BACKUP_DIR"/crm_*.dump 2>/dev/null | head -n 15 || echo "no dumps in $BACKUP_DIR"

if [[ -z "$DUMP" ]]; then
  # Prefer latest dump from today that is older than repair, else latest overnight.
  DUMP="$(ls -1t "$BACKUP_DIR"/crm_*.dump 2>/dev/null | head -n 1 || true)"
fi
if [[ -z "$DUMP" || ! -f "$DUMP" ]]; then
  echo "ERROR: set DUMP=/path/to/crm_....dump" >&2
  exit 1
fi
echo "Using DUMP=$DUMP"
echo "ORDERS=$ORDERS apply=$APPLY requeue=$REQUEUE"

TMP_DB="crm_lines_restore_tmp"
IDS_SQL="${ORDERS}"

docker cp "$DUMP" crm-staging-postgres:/tmp/crm_restore.dump

docker exec crm-staging-postgres psql -U crm -d postgres -v ON_ERROR_STOP=1 -c \
  "DROP DATABASE IF EXISTS ${TMP_DB};"
docker exec crm-staging-postgres psql -U crm -d postgres -v ON_ERROR_STOP=1 -c \
  "CREATE DATABASE ${TMP_DB};"

# Table-only restore (may warn about deps — ok)
docker exec crm-staging-postgres pg_restore -U crm -d "$TMP_DB" \
  --no-owner --no-privileges \
  -t lead_opt_order_lines \
  /tmp/crm_restore.dump || true

echo ""
echo "=== backup line counts ==="
docker exec crm-staging-postgres psql -U crm -d "$TMP_DB" -c "
SELECT order_id, count(*) AS lines,
       count(document_number) AS with_doc_no
FROM lead_opt_order_lines
WHERE order_id IN (${IDS_SQL})
GROUP BY order_id
ORDER BY order_id;
"

echo ""
echo "=== match preview (backup crm/doc → current) ==="
docker exec crm-staging-postgres psql -U crm -d crm -c "
CREATE EXTENSION IF NOT EXISTS dblink;
"

# Cross-db update via postgres_fdw is heavy; use CSV roundtrip instead.
docker exec crm-staging-postgres psql -U crm -d "$TMP_DB" -c "
COPY (
  SELECT order_id, supplier_inn, document_date::date, amount::numeric(15,2),
         crm_id, document_number
  FROM lead_opt_order_lines
  WHERE order_id IN (${IDS_SQL})
) TO '/tmp/old_opt_lines.csv' WITH (FORMAT csv, HEADER true);
"
docker cp crm-staging-postgres:/tmp/old_opt_lines.csv /tmp/old_opt_lines.csv
docker cp /tmp/old_opt_lines.csv crm-staging-postgres:/tmp/old_opt_lines.csv

docker exec crm-staging-postgres psql -U crm -d crm -v ON_ERROR_STOP=1 <<'SQL'
DROP TABLE IF EXISTS _old_opt_lines;
CREATE TEMP TABLE _old_opt_lines (
  order_id bigint,
  supplier_inn text,
  document_date date,
  amount numeric(15,2),
  crm_id text,
  document_number text
);
COPY _old_opt_lines FROM '/tmp/old_opt_lines.csv' WITH (FORMAT csv, HEADER true);

SELECT c.order_id,
       count(*) AS current_lines,
       count(o.crm_id) AS matched_in_backup,
       count(*) FILTER (WHERE o.crm_id IS NOT NULL AND c.crm_id IS DISTINCT FROM o.crm_id) AS crm_differs,
       count(*) FILTER (WHERE o.crm_id IS NULL) AS only_in_current_new_lines
FROM lead_opt_order_lines c
LEFT JOIN _old_opt_lines o
  ON o.order_id = c.order_id
 AND o.supplier_inn = c.supplier_inn
 AND o.document_date = c.document_date::date
 AND o.amount = round(c.amount::numeric, 2)
WHERE c.order_id IN (178,179,249,250,253)
GROUP BY c.order_id
ORDER BY c.order_id;
SQL

if [[ "$APPLY" -ne 1 ]]; then
  echo ""
  echo "Dry-run only. Re-run with --apply to write crm_id/document_number back."
  docker exec crm-staging-postgres psql -U crm -d postgres -c "DROP DATABASE IF EXISTS ${TMP_DB};" || true
  exit 0
fi

echo ""
echo "=== APPLY restore crm_id + document_number ==="
docker exec crm-staging-postgres psql -U crm -d crm -v ON_ERROR_STOP=1 <<'SQL'
DROP TABLE IF EXISTS _old_opt_lines;
CREATE TEMP TABLE _old_opt_lines (
  order_id bigint,
  supplier_inn text,
  document_date date,
  amount numeric(15,2),
  crm_id text,
  document_number text
);
COPY _old_opt_lines FROM '/tmp/old_opt_lines.csv' WITH (FORMAT csv, HEADER true);

UPDATE lead_opt_order_lines c
SET crm_id = o.crm_id,
    document_number = NULLIF(o.document_number, '')
FROM _old_opt_lines o
WHERE c.order_id = o.order_id
  AND c.supplier_inn = o.supplier_inn
  AND c.document_date::date = o.document_date
  AND round(c.amount::numeric, 2) = o.amount
  AND c.order_id IN (178,179,249,250,253);

SELECT c.order_id, c.line_no, c.crm_id, c.document_number, c.amount
FROM lead_opt_order_lines c
WHERE c.order_id IN (178,179,249,250,253)
ORDER BY c.order_id, c.line_no;
SQL

if [[ "$REQUEUE" -eq 1 ]]; then
  echo ""
  echo "=== requeue Mole submit for restored orders ==="
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api python - <<'PY'
import asyncio
from sqlalchemy import text
from app.shared.db import get_session_factory
from app.modules.leads.opt.queue import enqueue_opt_submit

IDS = [178, 179, 249, 250, 253]

async def main():
    sf = get_session_factory()
    async with sf() as s:
        await s.execute(
            text("UPDATE lead_opt_orders SET status='queued', submission_error=NULL WHERE id = ANY(:ids)"),
            {"ids": IDS},
        )
        await s.commit()
    for oid in IDS:
        await enqueue_opt_submit(oid)
        print("requeued", oid)

asyncio.run(main())
PY
fi

docker exec crm-staging-postgres psql -U crm -d postgres -c "DROP DATABASE IF EXISTS ${TMP_DB};" || true
echo "DONE"
