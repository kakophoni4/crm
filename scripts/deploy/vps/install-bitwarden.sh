#!/usr/bin/env bash
# Deploy Vaultwarden (Bitwarden-compatible) on VPS behind nginx SNI split.
#
# Prerequisites:
#   - SNI split already installed (docs/SNI_SPLIT_VPN_TLS.md)
#   - DNS A-record: huitawarden.bttsrvvrs.org → VPS IP
#
# Run on VPS as root from repo root:
#   bash scripts/deploy/vps/install-bitwarden.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BW_DIR="$ROOT/deploy/bitwarden"
# Prefer standalone nginx bundle; fall back to deploy/server/nginx
NGINX_SRC="$BW_DIR/nginx"
[[ -d "$NGINX_SRC" ]] || NGINX_SRC="$ROOT/deploy/server/nginx"
ENV_FILE="$BW_DIR/.env"
STREAM_DST="/etc/nginx/stream.conf.d/00-sni-split.conf"
VAULT_DOMAIN="${VAULT_DOMAIN:-huitawarden.bttsrvvrs.org}"
CERT_PRIMARY="${CERT_PRIMARY:-chat.bttsrvvrs.org}"
CERT_ALT="${CERT_ALT:-api.bttsrvvrs.org}"
SNI_ANCHOR="${SNI_ANCHOR:-api.bttsrvvrs.org}"
CERT_LIVE="/etc/letsencrypt/live/${CERT_PRIMARY}"

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

require_root() {
  [[ "$(id -u)" -eq 0 ]] || die "Run as root on the VPS"
}

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    info "Creating $ENV_FILE from env.example"
    cp "$BW_DIR/env.example" "$ENV_FILE"
    token="$(openssl rand -base64 48 | tr -d '\n')"
    sed -i "s|^ADMIN_TOKEN=.*|ADMIN_TOKEN=${token}|" "$ENV_FILE"
    sed -i "s|^DOMAIN=.*|DOMAIN=https://${VAULT_DOMAIN}|" "$ENV_FILE"
    echo ""
    echo "Generated ADMIN_TOKEN (save it — shown once):"
    echo "  ${token}"
    echo ""
    echo "Admin panel: https://${VAULT_DOMAIN}/admin"
    echo ""
  else
    info "Using existing $ENV_FILE"
  fi
}

start_vaultwarden() {
  info "Starting Vaultwarden container..."
  cd "$BW_DIR"
  docker compose --env-file "$ENV_FILE" up -d
  cd "$ROOT"

  sleep 3
  curl -sf "http://127.0.0.1:19180/alive" >/dev/null \
    || die "Vaultwarden not responding on 127.0.0.1:19180"
  info "Vaultwarden healthy on localhost:19180"
}

install_http_nginx() {
  info "Installing HTTP nginx block for ${VAULT_DOMAIN}..."
  cp "$NGINX_SRC/vaultwarden-http.conf" /etc/nginx/sites-available/vaultwarden-http
  ln -sf /etc/nginx/sites-available/vaultwarden-http /etc/nginx/sites-enabled/02-vaultwarden-http
  nginx -t
  systemctl reload nginx
}

obtain_certificate() {
  if openssl x509 -in "$CERT_LIVE/fullchain.pem" -noout -text 2>/dev/null \
      | grep -q "DNS:${VAULT_DOMAIN}"; then
    info "Certificate already includes ${VAULT_DOMAIN}"
    return
  fi

  info "Expanding Let's Encrypt certificate for ${VAULT_DOMAIN}..."
  certbot certonly --webroot \
    -w /var/www/certbot \
    -d "$CERT_PRIMARY" \
    -d "$CERT_ALT" \
    -d "$VAULT_DOMAIN" \
    --expand \
    --non-interactive --agree-tos \
    --email "${ACME_EMAIL:-admin@${CERT_PRIMARY#*.}}" \
    || die "certbot failed — check DNS A-record for ${VAULT_DOMAIN}"
}

patch_sni_stream() {
  if grep -q "$VAULT_DOMAIN" "$STREAM_DST" 2>/dev/null; then
    info "SNI map already includes ${VAULT_DOMAIN}"
    return
  fi

  info "Adding ${VAULT_DOMAIN} to SNI map (CRM lines unchanged)..."
  cp "$STREAM_DST" "${STREAM_DST}.bak.$(date +%Y%m%d%H%M%S)"
  sed -i "/${SNI_ANCHOR}/a\\    ${VAULT_DOMAIN}   crm_ssl;" "$STREAM_DST"
  nginx -t && systemctl reload nginx
}

install_ssl_nginx() {
  info "Installing HTTPS nginx block for ${VAULT_DOMAIN}..."
  cp "$NGINX_SRC/vaultwarden-ssl.conf" /etc/nginx/sites-available/vaultwarden-ssl
  ln -sf /etc/nginx/sites-available/vaultwarden-ssl /etc/nginx/sites-enabled/03-vaultwarden-ssl
  nginx -t
  systemctl reload nginx
}

verify() {
  info "Verification..."
  echo ""
  curl -sf "https://${VAULT_DOMAIN}/alive" && echo "" || echo "HTTPS alive: FAIL"
  curl -sf -o /dev/null -w "Web UI HTTP %{http_code}\n" "https://${VAULT_DOMAIN}/" || echo "Web UI: FAIL"
  docker ps --filter name=vaultwarden --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  echo ""
  echo "Next steps:"
  echo "  1. Open https://${VAULT_DOMAIN}/admin — log in with ADMIN_TOKEN from $ENV_FILE"
  echo "  2. Create your account (first user becomes org admin if signups enabled)"
  echo "  3. In Bitwarden app: Settings → Self-hosted → Server URL = https://${VAULT_DOMAIN}"
}

main() {
  require_root
  cd "$ROOT"

  echo ""
  echo "Vaultwarden (Bitwarden) install — CRM is NOT redeployed"
  echo "Domain: https://${VAULT_DOMAIN}"
  echo ""
  echo "Ensure DNS A-record points to this server before continuing."
  read -r -p "Continue? [y/N] " ans
  [[ "${ans,,}" == "y" ]] || exit 0

  [[ -f "$STREAM_DST" ]] || die "SNI split not installed — run install-sni-split.sh first"
  [[ -f "$CERT_LIVE/fullchain.pem" ]] || die "CRM certificate missing — run install-sni-split.sh first"

  ensure_env
  start_vaultwarden
  install_http_nginx
  obtain_certificate
  patch_sni_stream
  install_ssl_nginx
  verify

  echo ""
  echo "Done. Docs: docs/BITWARDEN.md"
}

main "$@"
