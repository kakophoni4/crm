#!/usr/bin/env bash
# Post-HTTPS hardening: CRLF fix, backup cron, optional seed cleanup, smoke checks.
# Run on VPS: bash scripts/deploy/vps/post-https-setup.sh [--clear-seed]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
ENV_FILE="${ENV_FILE:-deploy/.env.staging}"

CLEAR_SEED=0
for arg in "$@"; do
  case "$arg" in
    --clear-seed) CLEAR_SEED=1 ;;
    -h|--help)
      echo "Usage: bash scripts/deploy/vps/post-https-setup.sh [--clear-seed]"
      exit 0
      ;;
  esac
done

echo "=== 1. Fix CRLF in shell scripts ==="
find "$ROOT/scripts/deploy/vps" -name '*.sh' -exec sed -i 's/\r$//' {} +

echo "=== 2. Backup cron (daily 03:00 UTC) ==="
chmod +x "$ROOT/scripts/deploy/vps/backup.sh"
CRON_LINE="0 3 * * * $ROOT/scripts/deploy/vps/backup.sh >> /var/log/crm-backup.log 2>&1"
(crontab -l 2>/dev/null | grep -v 'deploy/vps/backup.sh' || true; echo "$CRON_LINE") | crontab -
echo "Installed: $CRON_LINE"

echo "=== 3. First backup now ==="
bash "$ROOT/scripts/deploy/vps/backup.sh"

if [[ "$CLEAR_SEED" -eq 1 ]]; then
  echo "=== 4. Clear SEED_ADMIN_* in $ENV_FILE ==="
  if [[ -f "$ENV_FILE" ]]; then
    sed -i 's/^SEED_ADMIN_EMAIL=.*/SEED_ADMIN_EMAIL=/' "$ENV_FILE"
    sed -i 's/^SEED_ADMIN_PASSWORD=.*/SEED_ADMIN_PASSWORD=/' "$ENV_FILE"
    echo "SEED_ADMIN_* cleared. Restart api if you rely on env-only seed (usually not needed after first admin exists)."
  else
    echo "Skip: $ENV_FILE not found"
  fi
else
  echo "=== 4. SEED_ADMIN (skipped) ==="
  if grep -q '^SEED_ADMIN_PASSWORD=.' "$ENV_FILE" 2>/dev/null; then
    echo "WARNING: SEED_ADMIN_PASSWORD still set. After changing admin password in UI run:"
    echo "  bash scripts/deploy/vps/post-https-setup.sh --clear-seed"
  else
    echo "SEED_ADMIN_* already empty or missing — OK"
  fi
fi

echo "=== 5. Certbot renew dry-run ==="
certbot renew --dry-run || echo "certbot dry-run failed — check /var/log/letsencrypt/"

echo "=== 6. Status ==="
bash "$ROOT/scripts/deploy/vps/status.sh"

echo ""
echo "Done. Next: bash scripts/bots/provision_test_bot.sh"
