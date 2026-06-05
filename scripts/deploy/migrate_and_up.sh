#!/usr/bin/env bash
# Run migrations then start staging/prod stack.
#
# Usage:
#   ./scripts/deploy/migrate_and_up.sh staging
#   ./scripts/deploy/migrate_and_up.sh prod
#   ./scripts/deploy/migrate_and_up.sh nginx-proxy   # host nginx + legacy CPU (VPN on 443)
#   ./scripts/deploy/migrate_and_up.sh staging --dry-run   # validate compose only
#   ./scripts/deploy/migrate_and_up.sh prod --no-build       # skip image build (GHCR / pre-built)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

STACK="${1:-staging}"
shift || true

DRY_RUN=false
NO_BUILD=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --no-build) NO_BUILD=true ;;
    *)
      echo "Unknown argument: $arg (supported: --dry-run, --no-build)" >&2
      exit 1
      ;;
  esac
done

ENV_FILE="deploy/.env.${STACK}"

case "$STACK" in
  staging|prod|nginx-proxy) ;;
  *)
    echo "Unknown stack: $STACK (use: staging | prod | nginx-proxy)" >&2
    exit 1
    ;;
esac

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ "$STACK" == "nginx-proxy" ]]; then
    echo "Missing $ENV_FILE — copy from deploy/env.nginx-proxy.example" >&2
  else
    echo "Missing $ENV_FILE — copy from deploy/env.${STACK}.example" >&2
  fi
  exit 1
fi

COMPOSE_FILES=(-f docker/docker-compose.staging.yaml)
if [[ "$STACK" == "prod" ]]; then
  COMPOSE_FILES+=(-f docker/docker-compose.prod.yaml)
fi
if [[ "$STACK" == "nginx-proxy" ]]; then
  COMPOSE_FILES+=(-f docker/docker-compose.nginx-proxy.yaml)
fi

OVERRIDE="deploy/${STACK}/docker-compose.override.yaml"
if [[ "$STACK" == "nginx-proxy" ]]; then
  OVERRIDE=""
fi
if [[ -f "$OVERRIDE" ]]; then
  COMPOSE_FILES+=(-f "$OVERRIDE")
  echo "Using compose override: $OVERRIDE"
fi

COMPOSE_BASE=(docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}")

# shellcheck disable=SC1090
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

validate_env() {
  local errors=0

  if grep -qE 'CHANGE_ME' "$ENV_FILE"; then
    echo "ERROR: $ENV_FILE still contains CHANGE_ME placeholders." >&2
    errors=$((errors + 1))
  fi

  if [[ -n "${JWT_SECRET:-}" && "${#JWT_SECRET}" -lt 32 ]]; then
    echo "ERROR: JWT_SECRET must be at least 32 characters." >&2
    errors=$((errors + 1))
  fi

  if [[ -n "${POSTGRES_PASSWORD:-}" && -n "${DATABASE_URL:-}" ]]; then
    if [[ "$DATABASE_URL" != *"${POSTGRES_PASSWORD}"* ]]; then
      echo "ERROR: DATABASE_URL password does not match POSTGRES_PASSWORD." >&2
      errors=$((errors + 1))
    fi
  fi

  if [[ -f "$OVERRIDE" && -z "${GHCR_OWNER:-}" ]]; then
    echo "ERROR: $OVERRIDE is present but GHCR_OWNER is not set in $ENV_FILE." >&2
    errors=$((errors + 1))
  fi

  if [[ "$errors" -gt 0 ]]; then
    exit 1
  fi
}

should_skip_build() {
  if [[ "$NO_BUILD" == "true" || "${SKIP_COMPOSE_BUILD:-}" == "1" ]]; then
    return 0
  fi
  if [[ -f "$OVERRIDE" ]]; then
    return 0
  fi
  case "${CRM_API_IMAGE:-}" in
    ghcr.io/*) return 0 ;;
  esac
  return 1
}

PROFILE_ARGS=()
if [[ -n "${COMPOSE_PROFILES:-}" ]]; then
  IFS=',' read -r -a _profiles <<< "${COMPOSE_PROFILES}"
  for p in "${_profiles[@]}"; do
    p="${p// /}"
    [[ -n "$p" ]] && PROFILE_ARGS+=(--profile "$p")
  done
fi

validate_env

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Validating compose config for stack=$STACK ..."
  "${COMPOSE_BASE[@]}" "${PROFILE_ARGS[@]}" config --quiet
  echo "Compose config OK for stack=$STACK"
  exit 0
fi

if should_skip_build; then
  echo "Skipping image build (GHCR override, ghcr.io image, SKIP_COMPOSE_BUILD=1, or --no-build)."
else
  echo "Building images..."
  "${COMPOSE_BASE[@]}" "${PROFILE_ARGS[@]}" build api worker frontend
fi

echo "Starting data stores..."
"${COMPOSE_BASE[@]}" "${PROFILE_ARGS[@]}" up -d postgres redis minio
"${COMPOSE_BASE[@]}" "${PROFILE_ARGS[@]}" up -d minio-init || true

echo "Waiting for postgres..."
pg_ready=false
for _ in $(seq 1 30); do
  if "${COMPOSE_BASE[@]}" exec -T postgres pg_isready -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" >/dev/null 2>&1; then
    pg_ready=true
    break
  fi
  sleep 2
done
if [[ "$pg_ready" != "true" ]]; then
  echo "ERROR: postgres not ready after 60s — check logs: docker compose … logs postgres" >&2
  exit 1
fi

echo "Running alembic upgrade head..."
"${COMPOSE_BASE[@]}" run --rm --no-deps api alembic upgrade head

echo "Starting full stack..."
"${COMPOSE_BASE[@]}" "${PROFILE_ARGS[@]}" up -d

echo ""
"${COMPOSE_BASE[@]}" "${PROFILE_ARGS[@]}" ps
