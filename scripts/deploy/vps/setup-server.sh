#!/usr/bin/env bash
# One-time VPS hardening: nginx, cron backup, aliases, ensure psycopg in pyproject.
# Run on server as root: bash scripts/deploy/vps/setup-server.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

echo "=== 1. psycopg for Alembic (if missing) ==="
if ! grep -q 'psycopg\[binary\]' pyproject.toml; then
  sed -i '/asyncpg/a\    "psycopg[binary]>=3.1",' pyproject.toml
  echo "Added psycopg[binary] to pyproject.toml — run: bash scripts/deploy/vps/update.sh"
else
  echo "psycopg already in pyproject.toml"
fi

echo "=== 2. nginx reverse proxy ==="
bash "$ROOT/scripts/deploy/vps/install-nginx.sh"

echo "=== 3. backup cron (daily 03:00 UTC) ==="
chmod +x "$ROOT/scripts/deploy/vps/backup.sh" \
  "$ROOT/scripts/deploy/vps/status.sh" \
  "$ROOT/scripts/deploy/vps/update.sh" \
  "$ROOT/scripts/deploy/vps/install-nginx.sh"

CRON_LINE="0 3 * * * $ROOT/scripts/deploy/vps/backup.sh >> /var/log/crm-backup.log 2>&1"
(crontab -l 2>/dev/null | grep -v 'crm/deploy/vps/backup' || true; echo "$CRON_LINE") | crontab -
echo "Cron: $CRON_LINE"

echo "=== 4. shell aliases (/root/.bashrc) ==="
MARKER='# crm-vps-aliases'
if ! grep -q "$MARKER" /root/.bashrc 2>/dev/null; then
  cat >> /root/.bashrc << EOF

$MARKER
alias crm-status='bash $ROOT/scripts/deploy/vps/status.sh'
alias crm-update='bash $ROOT/scripts/deploy/vps/update.sh'
alias crm-logs='docker logs crm-staging-api -f --tail 100'
alias crm-backup='bash $ROOT/scripts/deploy/vps/backup.sh'
EOF
  echo "Aliases added. Run: source ~/.bashrc"
fi

echo "=== 5. optional: disable seed passwords in .env (recommended after first login) ==="
if grep -q '^SEED_ADMIN_PASSWORD=.' deploy/.env.staging 2>/dev/null; then
  echo "SEED_ADMIN_* still set — clear manually after changing admin password:"
  echo "  sed -i 's/^SEED_ADMIN_EMAIL=.*/SEED_ADMIN_EMAIL=/' deploy/.env.staging"
  echo "  sed -i 's/^SEED_ADMIN_PASSWORD=.*/SEED_ADMIN_PASSWORD=/' deploy/.env.staging"
fi

echo ""
echo "Done. Quick check:"
bash "$ROOT/scripts/deploy/vps/status.sh"
