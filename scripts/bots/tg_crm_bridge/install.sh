#!/usr/bin/env bash
# Install Telegram bridge on VPS and point CRM bot outbound_url at it.
# Usage: TG_BOT_TOKEN=123:ABC bash scripts/bots/tg_crm_bridge/install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/root/crm-bots}"
CRM_ROOT="${CRM_ROOT:-/root/crm}"
SECRETS_FILE="${SECRETS_FILE:-$CRM_ROOT/.secrets/test_bot_1.env}"
ENV_FILE="$INSTALL_DIR/.env"

if [[ -z "${TG_BOT_TOKEN:-}" ]]; then
  read -r -p "Telegram bot token from @BotFather: " TG_BOT_TOKEN
fi
[[ -n "$TG_BOT_TOKEN" ]] || { echo "TG_BOT_TOKEN required" >&2; exit 1; }

echo "=== Install dir $INSTALL_DIR ==="
mkdir -p "$INSTALL_DIR"
cp "$ROOT/scripts/bots/tg_crm_bridge/main.py" "$INSTALL_DIR/"
cp "$ROOT/scripts/bots/tg_crm_bridge/requirements.txt" "$INSTALL_DIR/"

if [[ ! -d "$INSTALL_DIR/venv" ]]; then
  python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

# CRM secrets
# shellcheck disable=SC1090
source "$SECRETS_FILE"

cat > "$ENV_FILE" << EOF
TG_BOT_TOKEN=$TG_BOT_TOKEN
CRM_API_BASE=${API_BASE:-https://api.crmkanasha.org}
BOT_CODE=${BOT_CODE:-test_bot_1}
INBOUND_SECRET=$INBOUND_SECRET
OUTBOUND_SECRET=$OUTBOUND_SECRET
LISTEN_HOST=0.0.0.0
LISTEN_PORT=8765
OUTBOUND_URL=http://host.docker.internal:8765/crm/cmd
HEALTH_URL=http://host.docker.internal:8765/crm/health
EOF
chmod 600 "$ENV_FILE"

echo "=== Docker worker: host.docker.internal ==="
if ! grep -q 'host.docker.internal:host-gateway' "$CRM_ROOT/deploy/server/docker-compose.vps.yaml"; then
  echo "ERROR: deploy/server/docker-compose.vps.yaml must include worker.extra_hosts." >&2
  echo "Copy updated file from repo and run: bash scripts/deploy/vps/update.sh" >&2
  exit 1
fi

if [[ "${SKIP_DOCKER:-0}" != "1" ]]; then
  echo "=== Restart CRM worker ==="
  cd "$CRM_ROOT"
  bash scripts/deploy/vps/update.sh
else
  echo "=== Skip Docker (SKIP_DOCKER=1) ==="
fi

echo "=== Update bot outbound_url in CRM ==="
ADMIN_USER="${ADMIN_USER:-admin@crmkanasha.org}"
ADMIN_PASS="${ADMIN_PASS:-}"
if [[ -z "$ADMIN_PASS" ]]; then
  read -r -s -p "CRM admin password for ${ADMIN_USER}: " ADMIN_PASS
  echo ""
fi
export ADMIN_USER ADMIN_PASS
LOGIN_JSON=$(python3 - << 'PY'
import json, os
print(json.dumps({
    "username": os.environ["ADMIN_USER"],
    "password": os.environ["ADMIN_PASS"],
}))
PY
)
LOGIN_RESP=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE:-https://api.crmkanasha.org}/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "$LOGIN_JSON")
HTTP_LOGIN=$(echo "$LOGIN_RESP" | tail -n1)
LOGIN_BODY=$(echo "$LOGIN_RESP" | sed '$d')
if [[ "$HTTP_LOGIN" != "200" ]]; then
  echo "Login failed HTTP $HTTP_LOGIN:" >&2
  echo "$LOGIN_BODY" >&2
  echo "Fix API first: curl http://127.0.0.1:19001/healthz && docker logs crm-staging-api --tail 50" >&2
  exit 1
fi
TOKEN=$(echo "$LOGIN_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

BOT_ID=$(curl -sf -H "Authorization: Bearer $TOKEN" \
  "${API_BASE:-https://api.crmkanasha.org}/api/v1/bots" \
  | python3 -c "import sys,json; print(next(i['id'] for i in json.load(sys.stdin)['items'] if i['code']=='${BOT_CODE:-test_bot_1}'))")

curl -sf -X PATCH "${API_BASE:-https://api.crmkanasha.org}/api/v1/bots/$BOT_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"outbound_url":"http://host.docker.internal:8765/crm/cmd","health_url":"http://host.docker.internal:8765/crm/health"}' \
  > /dev/null
echo "Bot $BOT_ID outbound_url updated."

echo "=== systemd service ==="
cp "$ROOT/scripts/bots/tg_crm_bridge/tg-crm-bridge.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable tg-crm-bridge
systemctl restart tg-crm-bridge
systemctl status tg-crm-bridge --no-pager

echo ""
echo "Done."
echo "1. Open your bot in Telegram, press Start, send a message"
echo "2. Open https://app.crmkanasha.org — find the chat"
echo "3. Reply in CRM — message should arrive back in Telegram"
