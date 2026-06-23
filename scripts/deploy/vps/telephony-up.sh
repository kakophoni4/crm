#!/usr/bin/env bash
# Build/start the CRM Asterisk PBX overlay on the VPS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-deploy/.env.staging}"
ENV_CHANGED=0

env_value() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
  value="${value%\"}"
  value="${value#\"}"
  printf '%s' "$value"
}

append_env_if_missing() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    return
  fi
  printf '\n%s=%s\n' "$key" "$value" >>"$ENV_FILE"
  ENV_CHANGED=1
}

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    od -An -N24 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

public_ip() {
  curl -fsS https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}'
}

domain="$(env_value DOMAIN)"
pbx_domain="$(env_value PBX_DOMAIN)"
if [[ -z "$pbx_domain" ]]; then
  pbx_domain="pbx.${domain}"
fi

turn_password="$(env_value TURN_PASSWORD)"
if [[ -z "$turn_password" ]]; then
  turn_password="$(random_secret)"
fi

turn_public_ip="$(env_value TURN_PUBLIC_IP)"
if [[ -z "$turn_public_ip" ]]; then
  turn_public_ip="$(public_ip)"
fi

if [[ -z "$pbx_domain" || "$pbx_domain" == "pbx." ]]; then
  echo "ERROR: DOMAIN or PBX_DOMAIN must be set in $ENV_FILE before enabling TURN." >&2
  exit 1
fi
if [[ -z "$turn_public_ip" ]]; then
  echo "ERROR: Could not detect TURN_PUBLIC_IP. Add TURN_PUBLIC_IP=<server-ip> to $ENV_FILE." >&2
  exit 1
fi

append_env_if_missing PBX_DOMAIN "$pbx_domain"
append_env_if_missing TURN_REALM "$pbx_domain"
append_env_if_missing TURN_PUBLIC_IP "$turn_public_ip"
append_env_if_missing TURN_USERNAME crm
append_env_if_missing TURN_PASSWORD "$turn_password"
append_env_if_missing TURN_PORT 3478
append_env_if_missing TURN_RELAY_MIN_PORT 49160
append_env_if_missing TURN_RELAY_MAX_PORT 49200
append_env_if_missing TELEPHONY_STUN_URLS "stun:stun.l.google.com:19302"
append_env_if_missing TELEPHONY_TURN_URLS "turn:${pbx_domain}:3478?transport=udp,turn:${pbx_domain}:3478?transport=tcp"
append_env_if_missing TELEPHONY_TURN_USERNAME "$(env_value TURN_USERNAME)"
append_env_if_missing TELEPHONY_TURN_PASSWORD "$turn_password"

docker compose \
  -f docker/docker-compose.staging.yaml \
  -f deploy/server/docker-compose.vps.yaml \
  -f deploy/server/docker-compose.telephony.yaml \
  --env-file "$ENV_FILE" \
  up -d --build coturn asterisk telephony-sync

if [[ "$ENV_CHANGED" -eq 1 ]]; then
  docker compose \
    -f docker/docker-compose.staging.yaml \
    -f deploy/server/docker-compose.vps.yaml \
    -f deploy/server/docker-compose.telephony.yaml \
    --env-file "$ENV_FILE" \
    up -d --no-deps api
fi

docker compose \
  -f docker/docker-compose.staging.yaml \
  -f deploy/server/docker-compose.vps.yaml \
  -f deploy/server/docker-compose.telephony.yaml \
  --env-file "$ENV_FILE" \
  ps api coturn asterisk telephony-sync

ENV_FILE="$ENV_FILE" bash scripts/deploy/vps/telephony-sync.sh
