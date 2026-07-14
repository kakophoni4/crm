#!/usr/bin/env bash
# Fix live chat updates (WebSocket) and HTTPS CORS on VPS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_FILE="$ROOT/deploy/.env.staging"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

patch_env() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

echo "=== Patch deploy/.env.staging (bttsrvvrs.org + Caddy) ==="
patch_env "CORS_ALLOWED_ORIGINS" "https://chat.bttsrvvrs.org"
patch_env "APP_PUBLIC_BASE_URL" "https://chat.bttsrvvrs.org"
patch_env "APP_API_PUBLIC_BASE_URL" "https://api.bttsrvvrs.org"
patch_env "VITE_API_BASE_URL" "https://api.bttsrvvrs.org/api/v1"
patch_env "VITE_WS_URL" "wss://api.bttsrvvrs.org/api/v1/ws"
patch_env "PBX_DOMAIN" "pbx.bttsrvvrs.org"
patch_env "TURN_REALM" "pbx.bttsrvvrs.org"

echo "=== Rebuild api, worker, frontend (WS /ws alias + correct VITE_WS_URL) ==="
compose build api worker frontend
compose up -d api worker frontend

echo ""
"$ROOT/scripts/deploy/vps/status.sh"
echo ""
echo "Done. Hard-refresh https://chat.bttsrvvrs.org (Ctrl+F5) and open a chat."
echo "WebSocket should connect without 403 in api logs."
