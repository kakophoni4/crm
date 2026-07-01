#!/usr/bin/env bash
# Quick audit before/after deploying bot service_types (0055).
# Run on the CRM server after SSH login.

set -euo pipefail

echo "=== CRM deploy path (adjust if different) ==="
CRM_ROOT="${CRM_ROOT:-/opt/crm}"
echo "CRM_ROOT=$CRM_ROOT"

echo
echo "=== Git / branch ==="
if [ -d "$CRM_ROOT/.git" ]; then
  git -C "$CRM_ROOT" status -sb
  git -C "$CRM_ROOT" log -1 --oneline
else
  echo "No git in $CRM_ROOT — set CRM_ROOT to your checkout"
fi

echo
echo "=== Running services (crm, workers, bridges) ==="
systemctl list-units --type=service --state=running 2>/dev/null \
  | grep -iE 'crm|uvicorn|gunicorn|worker|tg-crm|wa-crm|nginx' || true

echo
echo "=== Alembic head (inside API container or venv) ==="
echo "# If docker compose:"
echo "#   docker compose -f $CRM_ROOT/docker-compose.yml exec api alembic current"
echo "#   docker compose -f $CRM_ROOT/docker-compose.yml exec api alembic heads"
echo "# If systemd + venv:"
echo "#   cd $CRM_ROOT && .venv/bin/alembic current"

echo
echo "=== Bots count and service_types (needs DB access) ==="
echo "# Replace connection vars with yours from .env:"
cat <<'SQL'
psql "$DATABASE_URL" -c "
SELECT
  id,
  code,
  name,
  channel,
  is_active,
  service_types,
  department_id
FROM bots
ORDER BY code;
"

psql "$DATABASE_URL" -c "
SELECT
  custom_fields->'order'->>'service' AS service,
  COUNT(*) AS leads
FROM leads
WHERE closed_at IS NULL
GROUP BY 1
ORDER BY 2 DESC;
"

psql "$DATABASE_URL" -c "
SELECT
  b.code AS bot_code,
  l.custom_fields->'order'->>'service' AS service,
  COUNT(*) AS open_leads
FROM leads l
JOIN chats c ON c.id = l.chat_id
JOIN bots b ON b.id = c.bot_id
WHERE l.closed_at IS NULL
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
"
SQL

echo
echo "=== OPT tables (if 0054 applied) ==="
cat <<'SQL'
psql "$DATABASE_URL" -c "
SELECT COUNT(*) AS opt_orders FROM lead_opt_orders;
SELECT COUNT(*) AS opt_units FROM opt_units;
"
SQL

echo
echo "=== TG bridges (one per bot host) ==="
systemctl status tg-crm-bridge 2>/dev/null | head -5 || echo "tg-crm-bridge not on this host"
ls -la /etc/systemd/system/tg-crm-bridge*.service 2>/dev/null || true
