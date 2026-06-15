#!/usr/bin/env bash
# Create WhatsApp bot record in CRM and save HMAC secrets.
# Run on VPS or locally against staging/prod API:
#   bash scripts/bots/provision_whatsapp_bot.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
ENV_FILE="${ENV_FILE:-deploy/.env.staging}"
API_BASE="${API_BASE:-https://api.crmkanasha.org}"
SECRETS_DIR="${SECRETS_DIR:-$ROOT/.secrets}"
BOT_CODE="${BOT_CODE:-whatsapp_support_1}"
ENV_OUT="$SECRETS_DIR/${BOT_CODE}.env"

set -a
# shellcheck disable=SC1090
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
set +a

ADMIN_USER="${ADMIN_USER:-${SEED_ADMIN_EMAIL:-admin@crmkanasha.org}}"
ADMIN_PASS="${ADMIN_PASS:-${SEED_ADMIN_PASSWORD:-}}"

if [[ -z "$ADMIN_PASS" ]]; then
  read -r -s -p "Admin password for ${ADMIN_USER}: " ADMIN_PASS
  echo ""
fi

export ADMIN_USER ADMIN_PASS

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

echo "=== Login (${ADMIN_USER}) ==="
LOGIN_JSON=$(python3 - << 'PY'
import json, os
print(json.dumps({
    "username": os.environ["ADMIN_USER"],
    "password": os.environ["ADMIN_PASS"],
}))
PY
)
LOGIN_RESP=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE/api/v1/auth/login" \
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

echo "=== Department for bot owner ==="
DEPT_JSON=$(curl -sf -H "Authorization: Bearer $TOKEN" "$API_BASE/api/v1/departments" || echo '{"items":[]}')
DEPT_ID=$(echo "$DEPT_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['items'][0]['id'] if d.get('items') else '')")

if [[ -z "$DEPT_ID" ]]; then
  echo "No departments — create one in Admin → Departments and re-run." >&2
  exit 1
fi
echo "Using department id=$DEPT_ID"

INBOUND_SECRET=$(openssl rand -hex 24)
OUTBOUND_SECRET=$(openssl rand -hex 24)

echo "=== Create bot $BOT_CODE ==="
export BOT_CODE DEPT_ID INBOUND_SECRET OUTBOUND_SECRET
CREATE_BODY=$(python3 - << 'PY'
import json, os
print(json.dumps({
    "code": os.environ["BOT_CODE"],
    "name": "WhatsApp Support",
    "owner_type": "department",
    "owner_id": int(os.environ["DEPT_ID"]),
    "outbound_url": "http://127.0.0.1:8766/crm/cmd",
    "health_url": "http://127.0.0.1:8766/crm/health",
    "inbound_secret": os.environ["INBOUND_SECRET"],
    "outbound_secret": os.environ["OUTBOUND_SECRET"],
}))
PY
)

HTTP_CODE=$(curl -s -o /tmp/wa_bot_create.json -w "%{http_code}" -X POST "$API_BASE/api/v1/bots" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$CREATE_BODY")

if [[ "$HTTP_CODE" == "409" ]]; then
  echo "Bot $BOT_CODE already exists."
  if [[ -f "$ENV_OUT" ]]; then
    echo "Loading secrets from $ENV_OUT"
    # shellcheck disable=SC1090
    source "$ENV_OUT"
  else
    echo "Delete bot in UI or use another BOT_CODE." >&2
    exit 1
  fi
elif [[ "$HTTP_CODE" != "201" ]]; then
  echo "Create bot failed HTTP $HTTP_CODE:" >&2
  cat /tmp/wa_bot_create.json >&2
  exit 1
else
  echo "Bot created."
  cat > "$ENV_OUT" << EOF
BOT_CODE=$BOT_CODE
INBOUND_SECRET=$INBOUND_SECRET
OUTBOUND_SECRET=$OUTBOUND_SECRET
API_BASE=$API_BASE
EOF
  chmod 600 "$ENV_OUT"
  echo "Secrets saved: $ENV_OUT"
fi

echo ""
echo "=== Done ==="
echo "1. Register at https://console.green-api.com and connect a WhatsApp number (QR)"
echo "2. Copy idInstance + apiTokenInstance into install.sh"
echo "3. On VPS: GREEN_INSTANCE_ID=... GREEN_API_TOKEN=... bash scripts/bots/wa_crm_bridge/install.sh"
echo "4. Set GREEN webhook to https://YOUR_HOST/green/webhook"
