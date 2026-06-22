#!/usr/bin/env bash
# Build/start the CRM Asterisk PBX overlay on the VPS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-deploy/.env.staging}"

docker compose \
  -f docker/docker-compose.staging.yaml \
  -f deploy/server/docker-compose.vps.yaml \
  -f deploy/server/docker-compose.telephony.yaml \
  --env-file "$ENV_FILE" \
  up -d --build asterisk telephony-sync

docker compose \
  -f docker/docker-compose.staging.yaml \
  -f deploy/server/docker-compose.vps.yaml \
  -f deploy/server/docker-compose.telephony.yaml \
  --env-file "$ENV_FILE" \
  ps asterisk telephony-sync

ENV_FILE="$ENV_FILE" bash scripts/deploy/vps/telephony-sync.sh
