#!/usr/bin/env bash
# Shared docker compose invocation for VPS (crmkanasha / old CPU / nginx proxy).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-deploy/.env.staging}"
COMPOSE=(
  docker compose
  -f docker/docker-compose.staging.yaml
  -f deploy/server/docker-compose.vps.yaml
  --env-file "$ENV_FILE"
)

compose() {
  "${COMPOSE[@]}" "$@"
}
