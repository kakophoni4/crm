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
  --env-file "$ENV_FILE"
)

compose() {
  "${COMPOSE[@]}" "$@"
}
