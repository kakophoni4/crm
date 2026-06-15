#!/usr/bin/env bash
# Vaultwarden via matrix-caddy (ports 80/443 on this server).
set -euo pipefail

BW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$BW_DIR/.env"
VAULT_DOMAIN="${VAULT_DOMAIN:-huitawarden.bttsrvvrs.org}"
CADDY_CONTAINER="${CADDY_CONTAINER:-matrix-caddy}"
CADDY_NETWORK="${CADDY_NETWORK:-crm-staging-net}"

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

require_root() { [[ "$(id -u)" -eq 0 ]] || die "Run as root"; }

find_caddyfile() {
  docker exec "$CADDY_CONTAINER" test -f /etc/caddy/Caddyfile 2>/dev/null \
    && echo "/etc/caddy/Caddyfile" && return
  docker inspect "$CADDY_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}'
}

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$BW_DIR/env.example" "$ENV_FILE"
    token="$(openssl rand -base64 48 | tr -d '\n')"
    sed -i "s|^ADMIN_TOKEN=.*|ADMIN_TOKEN=${token}|" "$ENV_FILE"
    sed -i "s|^DOMAIN=.*|DOMAIN=https://${VAULT_DOMAIN}|" "$ENV_FILE"
    echo "ADMIN_TOKEN: $token"
  fi
}

start_vaultwarden() {
  cd "$BW_DIR"
  docker compose -f docker-compose.caddy.yaml --env-file "$ENV_FILE" up -d --force-recreate
}

connect_networks() {
  docker network connect "$CADDY_NETWORK" "$CADDY_CONTAINER" 2>/dev/null \
    && info "Connected $CADDY_CONTAINER to $CADDY_NETWORK" \
    || info "$CADDY_CONTAINER already on $CADDY_NETWORK (or connect manually)"
}

patch_caddyfile() {
  local host_path caddyfile="/etc/caddy/Caddyfile"
  host_path="$(find_caddyfile | head -1)"
  [[ -n "$host_path" ]] || die "Cannot find Caddyfile"

  if [[ "$host_path" != "/etc/caddy/Caddyfile" ]]; then
    caddyfile="$host_path"
  else
    host_path=""
  fi

  local marker="# vaultwarden ${VAULT_DOMAIN}"
  if [[ -n "$host_path" ]] && grep -q "$marker" "$host_path" 2>/dev/null; then
    info "Caddyfile already has vaultwarden block"
    return
  fi
  if [[ -z "$host_path" ]] && docker exec "$CADDY_CONTAINER" grep -q "$marker" "$caddyfile" 2>/dev/null; then
    info "Caddyfile already has vaultwarden block"
    return
  fi

  info "Adding ${VAULT_DOMAIN} to Caddyfile..."
  local block="${marker}
${VAULT_DOMAIN} {
    reverse_proxy vaultwarden:80
}
"

  if [[ -n "$host_path" && -f "$host_path" ]]; then
    cp "$host_path" "${host_path}.bak.$(date +%Y%m%d%H%M%S)"
    printf '\n%s\n' "$block" >> "$host_path"
  else
    docker exec "$CADDY_CONTAINER" sh -c "cp $caddyfile ${caddyfile}.bak.\$(date +%Y%m%d%H%M%S)"
    printf '%s\n' "$block" | docker exec -i "$CADDY_CONTAINER" tee -a "$caddyfile" >/dev/null
  fi

  docker exec "$CADDY_CONTAINER" caddy validate --config "$caddyfile"
  docker exec "$CADDY_CONTAINER" caddy reload --config "$caddyfile"
}

verify() {
  sleep 3
  curl -sf "https://${VAULT_DOMAIN}/alive" && echo ""
}

main() {
  require_root
  docker ps --format '{{.Names}}' | grep -qx "$CADDY_CONTAINER" \
    || die "Container $CADDY_CONTAINER not running"

  ensure_env
  start_vaultwarden
  connect_networks
  patch_caddyfile
  verify
  echo "Done: https://${VAULT_DOMAIN}"
}

main "$@"
