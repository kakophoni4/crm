#!/usr/bin/env bash
# Staging / prod post-deploy smoke (API + auth + chats + optional metrics + frontend).
#
# Usage:
#   BASE_URL=https://api.staging.example.com \
#   FRONTEND_URL=https://app.staging.example.com \
#   SMOKE_EMAIL=admin@staging.example.com \
#   SMOKE_PASSWORD='ChangeMe!Staging234' \
#   METRICS_ENABLED=true \
#   ./scripts/smoke/staging_smoke.sh
#
# Dry-run (no HTTP calls — prints planned checks):
#   ./scripts/smoke/staging_smoke.sh --dry-run
#
# Exit: 0 = all checks passed, 1 = at least one failed (CI post-deploy).
set -euo pipefail

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *)
      echo "Unknown argument: $arg (supported: --dry-run)" >&2
      exit 1
      ;;
  esac
done

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required for smoke tests (install: apt install curl)" >&2
  exit 1
fi

BASE_URL="${BASE_URL:-https://api.staging.example}"
FRONTEND_URL="${FRONTEND_URL:-${APP_URL:-https://app.staging.example}}"
METRICS_ENABLED="${METRICS_ENABLED:-true}"
SMOKE_EMAIL="${SMOKE_EMAIL:-${SEED_ADMIN_EMAIL:-admin@staging.example.com}}"
SMOKE_PASSWORD="${SMOKE_PASSWORD:-${SEED_ADMIN_PASSWORD:-ChangeMe!Staging234}}"

BASE_URL="${BASE_URL%/}"
FRONTEND_URL="${FRONTEND_URL%/}"
API="${BASE_URL}/api/v1"

FAILURES=0
PASSED=0

# When ACME_CA_SERVER uses Let's Encrypt *staging* CA, curl must skip verify unless you install the staging root.
smoke_tls_insecure() {
  local v
  v="$(printf '%s' "${SMOKE_TLS_INSECURE:-}" | tr '[:upper:]' '[:lower:]')"
  case "$v" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

smoke_curl() {
  if smoke_tls_insecure; then
    curl -k "$@"
  else
    curl "$@"
  fi
}

log_ok() {
  echo "[OK]   $*"
  PASSED=$((PASSED + 1))
}

log_fail() {
  echo "[FAIL] $*" >&2
  FAILURES=$((FAILURES + 1))
}

metrics_enabled() {
  local v
  v="$(printf '%s' "$METRICS_ENABLED" | tr '[:upper:]' '[:lower:]')"
  case "$v" in
    0|false|no|off) return 1 ;;
    *) return 0 ;;
  esac
}

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Smoke dry-run (no HTTP requests)"
  echo "  BASE_URL=${BASE_URL}"
  echo "  FRONTEND_URL=${FRONTEND_URL}"
  echo "  SMOKE_EMAIL=${SMOKE_EMAIL}"
  echo "  METRICS_ENABLED=${METRICS_ENABLED}"
  if smoke_tls_insecure; then
    echo "  SMOKE_TLS_INSECURE=true (curl -k)"
  else
    echo "  SMOKE_TLS_INSECURE=false (strict TLS)"
  fi
  echo "Planned checks:"
  echo "  GET ${BASE_URL}/healthz → 200"
  echo "  GET ${BASE_URL}/readyz → status=ready"
  if metrics_enabled; then
    echo "  GET ${BASE_URL}/metrics → contains http_requests_total"
  else
    echo "  SKIP /metrics"
  fi
  echo "  POST ${API}/auth/login → access_token"
  echo "  GET ${API}/chats → 200"
  echo "  GET ${FRONTEND_URL}/ → 200 (html)"
  echo "Dry-run OK."
  exit 0
fi

# --- GET /healthz → 200 ---
echo "==> GET ${BASE_URL}/healthz"
code="$(smoke_curl -sfS --max-time 30 -o /tmp/crm_smoke_healthz.json -w '%{http_code}' "${BASE_URL}/healthz" 2>/dev/null || echo "000")"
if [[ "$code" == "200" ]]; then
  log_ok "healthz HTTP 200"
else
  log_fail "healthz expected HTTP 200, got ${code}"
fi

# --- GET /readyz → status ready ---
echo "==> GET ${BASE_URL}/readyz"
ready_body="$(smoke_curl -sfS --max-time 30 "${BASE_URL}/readyz" 2>/dev/null || true)"
ready_status="$(printf '%s' "$ready_body" | sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
if [[ "$ready_status" == "ready" ]]; then
  log_ok "readyz status=ready"
else
  log_fail "readyz expected status=ready, got '${ready_status:-<empty>}'"
fi

# --- GET /metrics (if METRICS_ENABLED) ---
if metrics_enabled; then
  echo "==> GET ${BASE_URL}/metrics (METRICS_ENABLED)"
  metrics_body="$(smoke_curl -sfS --max-time 30 "${BASE_URL}/metrics" 2>/dev/null || true)"
  if printf '%s' "$metrics_body" | grep -q 'http_requests_total'; then
    log_ok "metrics contains http_requests_total"
  else
    log_fail "metrics missing http_requests_total (or endpoint unavailable)"
  fi
else
  echo "==> SKIP /metrics (METRICS_ENABLED=false)"
fi

# --- POST /api/v1/auth/login ---
echo "==> POST ${API}/auth/login"
login_resp="$(smoke_curl -sfS --max-time 30 -X POST "${API}/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${SMOKE_EMAIL}\",\"password\":\"${SMOKE_PASSWORD}\"}" 2>/dev/null || true)"
ACCESS_TOKEN="$(printf '%s' "$login_resp" | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
if [[ -n "$ACCESS_TOKEN" ]]; then
  log_ok "auth login returned access_token"
else
  log_fail "auth login failed for ${SMOKE_EMAIL}"
fi

# --- GET /api/v1/chats with Bearer ---
if [[ -n "$ACCESS_TOKEN" ]]; then
  echo "==> GET ${API}/chats"
  chats_code="$(smoke_curl -sfS --max-time 30 -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    "${API}/chats?limit=1" 2>/dev/null || echo "000")"
  if [[ "$chats_code" == "200" ]]; then
    log_ok "GET /chats HTTP 200"
  else
    log_fail "GET /chats expected HTTP 200, got ${chats_code}"
  fi
else
  log_fail "GET /chats skipped (no token)"
fi

# --- GET frontend / → 200 HTML ---
echo "==> GET ${FRONTEND_URL}/"
fe_code="$(smoke_curl -sfS --max-time 30 -o /tmp/crm_smoke_frontend.html -w '%{http_code}' "${FRONTEND_URL}/" 2>/dev/null || echo "000")"
fe_ct="$(smoke_curl -sfSI --max-time 30 "${FRONTEND_URL}/" 2>/dev/null | tr -d '\r' | awk -F': ' 'tolower($1)=="content-type"{print tolower($2); exit}' || true)"
if [[ "$fe_code" == "200" ]] && [[ "$fe_ct" == *html* ]]; then
  log_ok "frontend HTTP 200 (text/html)"
elif [[ "$fe_code" == "200" ]]; then
  log_ok "frontend HTTP 200"
else
  log_fail "frontend expected HTTP 200, got ${fe_code}"
fi

echo ""
echo "Smoke summary: ${PASSED} passed, ${FAILURES} failed"
if [[ "$FAILURES" -gt 0 ]]; then
  exit 1
fi
echo "Staging smoke passed."
exit 0
