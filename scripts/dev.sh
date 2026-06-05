#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
COMPOSE_FILE="docker/docker-compose.dev.yaml"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "Starting dev dependencies..."
if docker compose -f "$COMPOSE_FILE" up -d --wait 2>/dev/null; then
  echo "All services reported healthy (docker compose --wait)."
else
  docker compose -f "$COMPOSE_FILE" up -d
  echo "Waiting up to 20s for healthchecks..."
  sleep 20
fi

echo ""
echo "=== CRM Chat Center — local dev URLs ==="
echo "API (run app locally):  http://localhost:8000"
echo "Adminer (PostgreSQL):   http://localhost:8080"
echo "MinIO console:          http://localhost:9001  (user: minio / miniominio)"
echo "MinIO S3 API:           http://localhost:9000"
echo "MailHog (SMTP UI):      http://localhost:8025  (SMTP: localhost:1025)"
echo "Frontend (Vite):        http://localhost:5173"
echo ""
docker compose -f "$COMPOSE_FILE" ps
