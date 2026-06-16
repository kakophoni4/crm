#!/usr/bin/env bash
# Install WhatsApp bridge on VPS — configs are loaded from CRM (Admin → Боты).
# Usage: bash scripts/bots/wa_crm_bridge/install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/root/crm-wa-bots}"
CRM_ROOT="${CRM_ROOT:-/root/crm}"
ENV_FILE="${ENV_FILE:-$CRM_ROOT/deploy/.env.prod}"
ENV_OUT="$INSTALL_DIR/.env"

set -a
# shellcheck disable=SC1090
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
set +a

CRM_API_BASE="${CRM_API_BASE:-http://127.0.0.1:19001}"

if [[ -z "${WA_BRIDGE_SYNC_SECRET:-}" ]]; then
  WA_BRIDGE_SYNC_SECRET=$(openssl rand -hex 24)
  echo "Generated WA_BRIDGE_SYNC_SECRET"
  if [[ -f "$ENV_FILE" ]] && ! grep -q '^WA_BRIDGE_SYNC_SECRET=' "$ENV_FILE"; then
    echo "WA_BRIDGE_SYNC_SECRET=$WA_BRIDGE_SYNC_SECRET" >> "$ENV_FILE"
    echo "Appended WA_BRIDGE_SYNC_SECRET to $ENV_FILE"
  else
    echo "Add to $ENV_FILE and restart api+worker:"
    echo "  WA_BRIDGE_SYNC_SECRET=$WA_BRIDGE_SYNC_SECRET"
  fi
fi

echo "=== Install dir $INSTALL_DIR ==="
mkdir -p "$INSTALL_DIR"
cp "$ROOT/scripts/bots/wa_crm_bridge/main.py" "$INSTALL_DIR/"
cp "$ROOT/scripts/bots/wa_crm_bridge/requirements.txt" "$INSTALL_DIR/"

if [[ ! -d "$INSTALL_DIR/venv" ]]; then
  python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

cat > "$ENV_OUT" << EOF
CRM_API_BASE=$CRM_API_BASE
WA_BRIDGE_SYNC_SECRET=$WA_BRIDGE_SYNC_SECRET
LISTEN_HOST=0.0.0.0
LISTEN_PORT=8766
EOF
chmod 600 "$ENV_OUT"

echo "=== systemd service ==="
sed "s|EnvironmentFile=.*|EnvironmentFile=$ENV_OUT|" \
  "$ROOT/scripts/bots/wa_crm_bridge/wa-crm-bridge.service" > /etc/systemd/system/wa-crm-bridge.service
systemctl daemon-reload
systemctl enable wa-crm-bridge
systemctl restart wa-crm-bridge
systemctl status wa-crm-bridge --no-pager || true

echo ""
echo "Done."
echo "1. Set WA_BRIDGE_SYNC_SECRET in CRM API env ($ENV_FILE) and restart api+worker"
echo "2. Admin → Боты → Создать → WhatsApp → вставить GREEN API idInstance + token"
echo "3. Reverse proxy /green/ → http://127.0.0.1:8766/green/"
echo "   matrix-caddy (this VPS): bash scripts/deploy/vps/patch-caddy-wa-green.sh"
echo "   Traefik: docker compose ... up -d wa-bridge-proxy"
echo "   Host nginx: deploy/server/nginx/crmkanasha-ssl.conf location /green/"
echo "4. CRM сам пропишет webhook в GREEN API при сохранении бота"
