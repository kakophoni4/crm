#!/usr/bin/env bash
# Diagnose OPT upload / API health after soft-delete deploy
set -euo pipefail

echo "=== containers ==="
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'crm-staging|NAMES' || docker ps

echo ""
echo "=== healthz ==="
curl -sf "http://127.0.0.1:${VPS_API_PORT:-19001}/healthz" && echo OK || echo FAIL

echo ""
echo "=== deleted_at column ==="
docker exec crm-staging-postgres psql -U crm -d crm -c \
  "SELECT column_name FROM information_schema.columns
   WHERE table_name='lead_opt_orders' AND column_name='deleted_at';"

echo ""
echo "=== alembic head in DB ==="
docker exec crm-staging-postgres psql -U crm -d crm -c \
  "SELECT version_num FROM alembic_version;"

echo ""
echo "=== model has deleted_at in container? ==="
docker exec crm-staging-api python -c \
  "from app.modules.db.models.lead_opt_order import LeadOptOrder; print('deleted_at' in LeadOptOrder.__table__.c)"

echo ""
echo "=== last API errors ==="
docker logs crm-staging-api --tail 120 2>&1 \
  | grep -Ei 'error|exception|traceback|opt-orders|UndefinedColumn|deleted_at' \
  | tail -n 40 || true

echo ""
echo "=== recent opt-orders HTTP ==="
docker logs crm-staging-api --tail 200 2>&1 \
  | grep -E 'opt-orders' | tail -n 30 || true
