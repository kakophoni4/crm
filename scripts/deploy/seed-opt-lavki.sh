#!/usr/bin/env bash
# Upsert all lavki from scripts/opt_units_vane.json into Postgres.
# Run on VPS from repo root after git pull.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

JSON="$ROOT/scripts/opt_units_vane.json"
SQL="$ROOT/scripts/deploy/seed-opt-lavki.sql"

if [[ ! -f "$JSON" ]]; then
  echo "Missing $JSON — run: py scripts/opt_sync_lavki_from_xlsx.py --sql $SQL"
  exit 1
fi

if [[ ! -f "$SQL" ]]; then
  echo "Missing $SQL — run: py scripts/opt_sync_lavki_from_xlsx.py --sql $SQL"
  exit 1
fi

echo "Seeding opt_units from $SQL ..."
compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" < "$SQL"

TEST_SQL="$ROOT/scripts/fixtures/seed-opt-test-lavki.sql"
if [[ -f "$TEST_SQL" ]]; then
  echo "Seeding NAVEL test lavki from $TEST_SQL ..."
  compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" < "$TEST_SQL"
fi

echo "Done. Lavki count:"
compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -c \
  "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE category_code = 'TECH') AS tech FROM opt_units;"
