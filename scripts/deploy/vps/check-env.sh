#!/usr/bin/env bash
# Fail fast when deploy/.env.staging still has dev-only URLs (causes browser Network Error).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/deploy/.env.staging}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy from deploy/.env.staging template and fill secrets." >&2
  exit 1
fi

fail=0

if grep -qE '^VITE_API_BASE_URL=http://localhost' "$ENV_FILE"; then
  echo "ERROR: VITE_API_BASE_URL points to localhost — the browser cannot reach API on VPS." >&2
  fail=1
fi

if grep -qE '^CORS_ALLOWED_ORIGINS=http://localhost' "$ENV_FILE"; then
  echo "ERROR: CORS_ALLOWED_ORIGINS is localhost-only — API rejects https://chat.bttsrvvrs.org." >&2
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  echo "" >&2
  echo "Fix on VPS:" >&2
  echo "  bash scripts/deploy/vps/fix-live-chat.sh" >&2
  echo "Then hard-refresh the app (Ctrl+F5)." >&2
  exit 1
fi

echo "Env OK: VITE_* and CORS look like production URLs."
