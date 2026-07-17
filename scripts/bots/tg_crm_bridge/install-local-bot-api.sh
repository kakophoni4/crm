#!/usr/bin/env bash
# Start Local Telegram Bot API and point tg-crm-bridge at it (files up to 100 MB).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/root/crm-bots}"
ENV_FILE="${ENV_FILE:-$INSTALL_DIR/.env}"
COMPOSE_FILE="$ROOT/deploy/server/docker-compose.telegram-bot-api.yaml"

if [[ -z "${TELEGRAM_API_ID:-}" || -z "${TELEGRAM_API_HASH:-}" ]]; then
  echo "Need TELEGRAM_API_ID and TELEGRAM_API_HASH from https://my.telegram.org" >&2
  echo "Example:" >&2
  echo "  export TELEGRAM_API_ID=12345678" >&2
  echo "  export TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef" >&2
  echo "  bash scripts/bots/tg_crm_bridge/install-local-bot-api.sh" >&2
  exit 1
fi

echo "=== Free resources (before Local Bot API) ==="
df -h / /var/lib/docker 2>/dev/null || df -h /
free -h
echo

echo "=== Starting Local Bot API on 127.0.0.1:8081 ==="
docker compose -f "$COMPOSE_FILE" up -d
docker compose -f "$COMPOSE_FILE" ps

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing bridge env: $ENV_FILE" >&2
  exit 1
fi

# Point bridge at local API; CRM worker downloads via host.docker.internal.
set_kv() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
  fi
}

set_kv TG_API_BASE "http://127.0.0.1:8081"
set_kv TG_FILE_BASE "http://host.docker.internal:8081"
set_kv TG_MAX_FILE_BYTES "104857600"

# Refresh bridge code + restart
cp "$ROOT/scripts/bots/tg_crm_bridge/main.py" "$INSTALL_DIR/main.py"
systemctl restart tg-crm-bridge
sleep 1
systemctl --no-pager --full status tg-crm-bridge || true

echo
echo "=== Done ==="
echo "Bridge now uses Local Bot API (limit 100 MB)."
echo "Test: send a ~25–80 MB document to the bot, check CRM chat +:"
echo "  journalctl -u tg-crm-bridge -n 50 --no-pager"
echo "  docker logs crm-telegram-bot-api --tail 50"
