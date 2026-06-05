#!/usr/bin/env bash
# Create test bot in CRM and send one signed inbound event.
# Run on VPS: bash scripts/bots/provision_test_bot.sh
# Or: ADMIN_USER=admin@crmkanasha.org ADMIN_PASS='yourpass' bash scripts/bots/provision_test_bot.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
ENV_FILE="${ENV_FILE:-deploy/.env.staging}"
API_BASE="${API_BASE:-https://api.crmkanasha.org}"
SECRETS_DIR="${SECRETS_DIR:-$ROOT/.secrets}"
BOT_CODE="${BOT_CODE:-test_bot_1}"
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
  echo "No departments — creating 'Main'..."
  CREATE_DEPT=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE/api/v1/departments" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"Main"}')
  HTTP_DEPT=$(echo "$CREATE_DEPT" | tail -n1)
  DEPT_BODY=$(echo "$CREATE_DEPT" | sed '$d')
  if [[ "$HTTP_DEPT" != "201" ]]; then
    echo "Create department failed HTTP $HTTP_DEPT:" >&2
    echo "$DEPT_BODY" >&2
    echo "Create a department in UI (Admin → Departments) and re-run." >&2
    exit 1
  fi
  DEPT_ID=$(echo "$DEPT_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
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
    "name": "Test Bot",
    "owner_type": "department",
    "owner_id": int(os.environ["DEPT_ID"]),
    "outbound_url": "https://httpbin.org/post",
    "health_url": None,
    "inbound_secret": os.environ["INBOUND_SECRET"],
    "outbound_secret": os.environ["OUTBOUND_SECRET"],
}))
PY
)

HTTP_CODE=$(curl -s -o /tmp/bot_create.json -w "%{http_code}" -X POST "$API_BASE/api/v1/bots" \
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
    echo "No secrets file. Delete bot in UI or run: BOT_CODE=test_bot_2 bash $0" >&2
    exit 1
  fi
elif [[ "$HTTP_CODE" != "201" ]]; then
  echo "Create bot failed HTTP $HTTP_CODE:" >&2
  cat /tmp/bot_create.json >&2
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

echo "=== Send test event ==="
python3 "$ROOT/scripts/bots/send_test_event.py" \
  --api-base "$API_BASE" \
  --bot-code "$BOT_CODE" \
  --inbound-secret "$INBOUND_SECRET" \
  --text "Привет из provision_test_bot — $(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo ""
echo "=== Done ==="
echo "1. Open https://app.crmkanasha.org — chat for telegram_user_id 999888777"
echo "2. Re-send: source $ENV_OUT && python3 scripts/bots/send_test_event.py --api-base \$API_BASE --bot-code \$BOT_CODE --inbound-secret \$INBOUND_SECRET"
