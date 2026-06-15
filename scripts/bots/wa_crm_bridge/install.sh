#!/usr/bin/env bash
# Install WhatsApp (GREEN API) bridge on VPS and point CRM bot outbound_url at it.
# Usage:
#   GREEN_INSTANCE_ID=... GREEN_API_TOKEN=... bash scripts/bots/wa_crm_bridge/install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/root/crm-wa-bots}"
CRM_ROOT="${CRM_ROOT:-/root/crm}"
BOT_CODE="${BOT_CODE:-whatsapp_support_1}"
SECRETS_FILE="${SECRETS_FILE:-$CRM_ROOT/.secrets/${BOT_CODE}.env}"
ENV_FILE="$INSTALL_DIR/.env"

if [[ -z "${GREEN_INSTANCE_ID:-}" ]]; then
  read -r -p "GREEN API idInstance: " GREEN_INSTANCE_ID
fi
if [[ -z "${GREEN_API_TOKEN:-}" ]]; then
  read -r -p "GREEN API apiTokenInstance: " GREEN_API_TOKEN
fi
[[ -n "$GREEN_INSTANCE_ID" && -n "$GREEN_API_TOKEN" ]] || {
  echo "GREEN_INSTANCE_ID and GREEN_API_TOKEN are required" >&2
  exit 1
}

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "Secrets file not found: $SECRETS_FILE" >&2
  echo "Run first: BOT_CODE=$BOT_CODE bash scripts/bots/provision_whatsapp_bot.sh" >&2
  exit 1
fi

echo "=== Install dir $INSTALL_DIR ==="
mkdir -p "$INSTALL_DIR"
cp "$ROOT/scripts/bots/wa_crm_bridge/main.py" "$INSTALL_DIR/"
cp "$ROOT/scripts/bots/wa_crm_bridge/requirements.txt" "$INSTALL_DIR/"

if [[ ! -d "$INSTALL_DIR/venv" ]]; then
  python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

# shellcheck disable=SC1090
source "$SECRETS_FILE"

cat > "$ENV_FILE" << EOF
GREEN_API_URL=${GREEN_API_URL:-https://api.green-api.com}
GREEN_MEDIA_URL=${GREEN_MEDIA_URL:-https://media.green-api.com}
GREEN_INSTANCE_ID=$GREEN_INSTANCE_ID
GREEN_API_TOKEN=$GREEN_API_TOKEN
CRM_API_BASE=${API_BASE:-https://api.crmkanasha.org}
BOT_CODE=${BOT_CODE:-whatsapp_support_1}
INBOUND_SECRET=$INBOUND_SECRET
OUTBOUND_SECRET=$OUTBOUND_SECRET
LISTEN_HOST=0.0.0.0
LISTEN_PORT=8766
WEBHOOK_TOKEN=${WEBHOOK_TOKEN:-}
OUTBOUND_URL=http://host.docker.internal:8766/crm/cmd
HEALTH_URL=http://host.docker.internal:8766/crm/health
EOF
chmod 600 "$ENV_FILE"

echo "=== Docker worker: host.docker.internal ==="
if ! grep -q 'host.docker.internal:host-gateway' "$CRM_ROOT/deploy/server/docker-compose.vps.yaml"; then
  echo "ERROR: deploy/server/docker-compose.vps.yaml must include worker.extra_hosts." >&2
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
  exit 1
fi
TOKEN=$(echo "$LOGIN_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

BOT_ID=$(curl -sf -H "Authorization: Bearer $TOKEN" \
  "${API_BASE:-https://api.crmkanasha.org}/api/v1/bots" \
  | python3 -c "import sys,json; print(next(i['id'] for i in json.load(sys.stdin)['items'] if i['code']=='${BOT_CODE:-whatsapp_support_1}'))")

curl -sf -X PATCH "${API_BASE:-https://api.crmkanasha.org}/api/v1/bots/$BOT_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"outbound_url":"http://host.docker.internal:8766/crm/cmd","health_url":"http://host.docker.internal:8766/crm/health"}' \
  > /dev/null
echo "Bot $BOT_ID outbound_url updated."

echo "=== systemd service ==="
cp "$ROOT/scripts/bots/wa_crm_bridge/wa-crm-bridge.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable wa-crm-bridge
systemctl restart wa-crm-bridge
systemctl status wa-crm-bridge --no-pager

echo ""
echo "Done."
echo "Next:"
echo "1. Expose https://YOUR_HOST/green/webhook (nginx) OR use a tunnel for dev"
echo "2. In GREEN API console set webhookUrl to that public URL"
echo "3. Enable 'Receive notifications about incoming messages and files'"
echo "4. Send a WhatsApp message to your connected number"
echo "5. Open CRM UI — find the chat, reply — message should arrive in WhatsApp"
