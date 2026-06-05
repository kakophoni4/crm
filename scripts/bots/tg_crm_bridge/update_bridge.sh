#!/usr/bin/env bash
# Copy updated bridge code and restart (after scp from Windows).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/root/crm-bots}"
SRC="$ROOT/scripts/bots/tg_crm_bridge/main.py"

cp "$SRC" "$INSTALL_DIR/main.py"
systemctl restart tg-crm-bridge
systemctl status tg-crm-bridge --no-pager
echo "Bridge updated from $SRC"
