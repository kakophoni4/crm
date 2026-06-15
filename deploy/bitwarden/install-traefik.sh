#!/usr/bin/env bash
# Vaultwarden via CRM Traefik — when host ports 80/443 are already used by docker-proxy.
set -euo pipefail

BW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$BW_DIR/.env"
VAULT_DOMAIN="${VAULT_DOMAIN:-huitawarden.bttsrvvrs.org}"
COMPOSE_FILE="$BW_DIR/docker-compose.traefik.yaml"
TRAEFIK_NETWORK="${TRAEFIK_NETWORK:-crm-staging-net}"

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

require_root() {
  [[ "$(id -u)" -eq 0 ]] || die "Run as root"
}

check_traefik() {
  docker ps --format '{{.Names}}' | grep -qE 'traefik|crm-staging-traefik' \
    || die "Traefik container not running"
  docker network inspect "$TRAEFIK_NETWORK" >/dev/null 2>&1 \
    || die "Docker network $TRAEFIK_NETWORK not found — run: docker network ls"
  ss -tlnp | grep -q ':443.*docker-proxy' \
    || info "Warning: port 443 may not be Traefik"
}

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$BW_DIR/env.example" "$ENV_FILE"
    token="$(openssl rand -base64 48 | tr -d '\n')"
    sed -i "s|^ADMIN_TOKEN=.*|ADMIN_TOKEN=${token}|" "$ENV_FILE"
    sed -i "s|^DOMAIN=.*|DOMAIN=https://${VAULT_DOMAIN}|" "$ENV_FILE"
    echo ""
    echo "=== SAVE THIS ADMIN TOKEN ==="
    echo "$token"
    echo "============================="
  else
    info "Using existing $ENV_FILE"
  fi
}

disable_host_nginx() {
  if systemctl is-active --quiet nginx 2>/dev/null; then
    info "Stopping host nginx (conflicts with Traefik on :80/:443)..."
    systemctl stop nginx
    systemctl disable nginx 2>/dev/null || true
  fi
  rm -f /etc/nginx/sites-enabled/02-vaultwarden-http \
        /etc/nginx/sites-enabled/03-vaultwarden-ssl 2>/dev/null || true
}

start_vaultwarden() {
  [[ -f "$COMPOSE_FILE" ]] || die "Missing $COMPOSE_FILE"
  cd "$BW_DIR"
  info "Recreating vaultwarden on Traefik network (CRM not restarted)..."
  docker compose -f docker-compose.yaml --env-file "$ENV_FILE" down 2>/dev/null || true
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
  sleep 5
}

verify() {
  info "Waiting for Traefik + certificate (up to 60s)..."
  local i
  for i in $(seq 1 12); do
    if curl -sf "https://${VAULT_DOMAIN}/alive" >/dev/null 2>&1; then
      curl -sf "https://${VAULT_DOMAIN}/alive" && echo ""
      docker ps --filter name=vaultwarden --format 'table {{.Names}}\t{{.Status}}'
      return 0
    fi
    sleep 5
  done
  echo "HTTPS not ready yet. Check:"
  echo "  docker logs crm-staging-traefik --tail 50"
  echo "  docker logs vaultwarden --tail 30"
  docker ps --filter name=vaultwarden
}

main() {
  require_root
  echo ""
  echo "Vaultwarden via Traefik (no host nginx)"
  echo "  Domain: https://${VAULT_DOMAIN}"
  echo "  CRM: NOT modified"
  echo ""

  if [[ "${1:-}" != "-y" ]]; then
    read -r -p "Continue? [y/N] " ans
    ans="$(printf '%s' "$ans" | tr -d '\r' | tr '[:upper:]' '[:lower:]')"
    [[ "$ans" == "y" || "$ans" == "yes" ]] || { echo "Aborted."; exit 0; }
  fi

  command -v docker >/dev/null || die "docker not installed"
  check_traefik
  ensure_env
  disable_host_nginx
  start_vaultwarden
  verify

  echo ""
  echo "Done."
  echo "  Web:   https://${VAULT_DOMAIN}"
  echo "  Admin: https://${VAULT_DOMAIN}/admin"
}

main "$@"
