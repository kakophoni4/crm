#!/usr/bin/env bash
# WhatsApp (GREEN API) inbound diagnostics on VPS.
# Usage: bash scripts/deploy/vps/diagnose-wa.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/deploy/.env.staging}"
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

SECRET="${WA_BRIDGE_SYNC_SECRET:?WA_BRIDGE_SYNC_SECRET not set}"
WEBHOOK_BASE="${WA_BRIDGE_WEBHOOK_PUBLIC_BASE:-https://api.${DOMAIN}/green/webhook}"

section() { echo ""; echo "========== $* =========="; }

section "Env"
echo "DOMAIN=$DOMAIN"
echo "WA_BRIDGE_WEBHOOK_PUBLIC_BASE=$WEBHOOK_BASE"

section "Bridge health (127.0.0.1:8766)"
curl -sf http://127.0.0.1:8766/crm/health && echo " OK" || echo "FAIL"

section "HTTPS webhook route"
code="$(curl -sS -o /dev/null -w '%{http_code}' \
  -X POST "https://api.${DOMAIN}/green/webhook/PLACEHOLDER" \
  -H 'Content-Type: application/json' \
  -d '{"typeWebhook":"incomingMessageReceived"}' || true)"
echo "POST https://api.${DOMAIN}/green/webhook/... → HTTP $code (404=route ok, unknown bot)"

section "CRM wa-bridge config"
CFG="$(curl -sf -H "X-Wa-Bridge-Secret: $SECRET" "http://127.0.0.1:19001/api/v1/internal/wa-bridge/config")"
echo "$CFG" | python3 -m json.tool

section "GREEN API (webhook URL + instance state)"
python3 - "$CFG" "$WEBHOOK_BASE" << 'PY'
import json
import sys

import httpx

cfg = json.loads(sys.argv[1])
expected_base = sys.argv[2].rstrip("/")
items = cfg.get("items") or []
if not items:
    print("ERROR: no WhatsApp bots in CRM")
    sys.exit(1)

for b in items:
    code = b["bot_code"]
    iid = b["green_instance_id"]
    token = b["green_api_token"]
    api = b["green_api_url"].rstrip("/")
    expected = f"{expected_base}/{code}"
    print(f"bot_code={code}")
    print(f"  expected webhook: {expected}")

    state_url = f"{api}/waInstance{iid}/getStateInstance/{token}"
    r = httpx.get(state_url, timeout=20)
    print(f"  getStateInstance: {r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        print(f"  stateInstance={r.json().get('stateInstance')}")

    settings_url = f"{api}/waInstance{iid}/getSettings/{token}"
    r2 = httpx.get(settings_url, timeout=20)
    print(f"  getSettings: {r2.status_code}")
    if r2.status_code == 200:
        s = r2.json()
        wh = s.get("webhookUrl") or s.get("webhookUrlToken") or "(empty)"
        inc = s.get("incomingWebhook")
        print(f"  webhookUrl={wh}")
        print(f"  incomingWebhook={inc}")
        if wh != expected:
            print(f"  *** MISMATCH — fix with setSettings or re-save bot in admin ***")
            print(f"  curl -X POST '{api}/waInstance{iid}/setSettings/{token}' \\")
            print("    -H 'Content-Type: application/json' \\")
            print(f"    -d '{{\"webhookUrl\":\"{expected}\",\"incomingWebhook\":\"yes\"}}'")
PY

section "Bridge logs (last 30 min, webhook hits)"
journalctl -u wa-crm-bridge --since '30 min ago' --no-pager \
  | grep -E 'GREEN webhook|POST /green|CRM accepted|CRM inbound failed|Cannot parse|Unknown WhatsApp|Unsupported GREEN' \
  || echo "(no webhook activity — GREEN is not calling your server)"

section "Worker logs (last 30 min)"
docker logs crm-staging-worker --since 30m 2>&1 | tail -20 || true

section "Done"
echo "If webhookUrl mismatch → run setSettings curl above, then send WA message from ANOTHER phone."
echo "If no POST in bridge logs → GREEN webhook URL wrong or instance not authorized."
