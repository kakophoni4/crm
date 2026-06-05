#!/usr/bin/env bash
# Resume TG bridge setup after install.sh failed at login (Docker already done).
# Usage: SKIP_DOCKER=1 bash scripts/bots/tg_crm_bridge/finish_setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export SKIP_DOCKER=1
exec bash "$ROOT/scripts/bots/tg_crm_bridge/install.sh"
