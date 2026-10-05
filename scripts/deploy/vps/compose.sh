#!/usr/bin/env bash
# Shared docker compose invocation for VPS (crmkanasha / old CPU / nginx proxy).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-deploy/.env.staging}"
# docker-compose.vps.yaml binds API/frontend to docker bridge, not 127.0.0.1
VPS_API_HOST="${VPS_API_HOST:-172.17.0.1}"
VPS_API_PORT="${VPS_API_PORT:-19001}"
VPS_FRONTEND_HOST="${VPS_FRONTEND_HOST:-172.17.0.1}"
VPS_FRONTEND_PORT="${VPS_FRONTEND_PORT:-19090}"
COMPOSE=(
  docker compose
  -f docker/docker-compose.staging.yaml
  -f deploy/server/docker-compose.vps.yaml
  -f docker/docker-compose.speech.yaml
  --env-file "$ENV_FILE"
)

# A migrated shared network may belong to another project. Preserve that network.
if docker network inspect crm-staging-net >/dev/null 2>&1; then
  CRM_NETWORK_OWNER="$(docker network inspect crm-staging-net --format '{{index .Labels "com.docker.compose.project"}}')"
  if [[ "$CRM_NETWORK_OWNER" != "crm-staging" ]]; then
    COMPOSE+=(-f deploy/server/docker-compose.external-network.yaml)
  fi
fi

if docker network inspect crm-staging_speech-private >/dev/null 2>&1; then
  CRM_SPEECH_NETWORK_LABEL="$(docker network inspect crm-staging_speech-private --format '{{index .Labels "com.docker.compose.network"}}')"
  if [[ "$CRM_SPEECH_NETWORK_LABEL" != "speech-private" ]]; then
    COMPOSE+=(-f deploy/server/docker-compose.external-speech.yaml)
  fi
fi

AI_ENV_FILE="${AI_ENV_FILE:-/root/crm-ai-connection.env}"
if [[ -f "$AI_ENV_FILE" ]]; then
  COMPOSE+=(--env-file "$AI_ENV_FILE")
fi

VPN_ENV_FILE="${VPN_ENV_FILE:-/etc/crm-vpn/crm.env}"
if [[ -f "$VPN_ENV_FILE" ]]; then
  COMPOSE+=(--env-file "$VPN_ENV_FILE")
fi

compose() {
  "${COMPOSE[@]}" "$@"
}
