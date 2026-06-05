#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CONF_SRC="$ROOT/deploy/server/nginx/crmkanasha.conf"
CONF_DST="/etc/nginx/sites-available/crmkanasha"

if [[ ! -f "$CONF_SRC" ]]; then
  echo "Missing $CONF_SRC" >&2
  exit 1
fi

cp "$CONF_SRC" "$CONF_DST"
ln -sf "$CONF_DST" /etc/nginx/sites-enabled/00-crmkanasha
nginx -t
systemctl reload nginx
echo "nginx OK: $CONF_DST -> sites-enabled/00-crmkanasha"
