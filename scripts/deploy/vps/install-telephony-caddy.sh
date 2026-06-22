#!/usr/bin/env bash
# Append/update the PBX WebSocket route in the matrix-caddy Caddyfile.
set -euo pipefail

PBX_DOMAIN="${PBX_DOMAIN:-pbx.bttsrvvrs.org}"
ASTERISK_HTTP_PORT="${ASTERISK_HTTP_PORT:-18088}"
CADDYFILE="${CADDYFILE:-/opt/matrix/data/caddy/Caddyfile}"
CADDY_CONTAINER="${CADDY_CONTAINER:-matrix-caddy}"
MARKER="# CRM telephony PBX"

if [[ ! -f "$CADDYFILE" ]]; then
  echo "Caddyfile not found: $CADDYFILE" >&2
  exit 1
fi

cp "$CADDYFILE" "${CADDYFILE}.bak.$(date +%Y%m%d%H%M%S)"

tmp="$(mktemp)"
awk -v marker="$MARKER" '
  $0 == marker { skip = 1; next }
  skip && $0 == "# /CRM telephony PBX" { skip = 0; next }
  !skip { print }
' "$CADDYFILE" > "$tmp"

cat >> "$tmp" <<EOF

$MARKER
$PBX_DOMAIN {
  reverse_proxy host.docker.internal:$ASTERISK_HTTP_PORT
}
# /CRM telephony PBX
EOF

mv "$tmp" "$CADDYFILE"

docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile
docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile

echo "PBX route installed: wss://$PBX_DOMAIN/ws -> 127.0.0.1:$ASTERISK_HTTP_PORT"
