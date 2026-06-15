#!/usr/bin/env bash
# Standalone Vaultwarden install — does NOT touch CRM containers or git repo.
set -euo pipefail

BW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$BW_DIR/.env"
NGINX_DIR="$BW_DIR/nginx"
STREAM_DST="/etc/nginx/stream.conf.d/00-sni-split.conf"
VAULT_DOMAIN="${VAULT_DOMAIN:-huitawarden.bttsrvvrs.org}"
CERT_PRIMARY="${CERT_PRIMARY:-chat.bttsrvvrs.org}"
CERT_ALT="${CERT_ALT:-api.bttsrvvrs.org}"
SNI_ANCHOR="${SNI_ANCHOR:-api.bttsrvvrs.org}"
NGINX_MODE="${NGINX_MODE:-auto}"
CERT_NAME=""
CERT_LIVE=""
WEBROOT="${WEBROOT:-/var/www/certbot}"

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

nginx_apply() {
  nginx -t
  if systemctl is-active --quiet nginx 2>/dev/null; then
    systemctl reload nginx
  else
    systemctl start nginx || die "nginx failed to start — run: journalctl -u nginx -n 30 --no-pager"
    systemctl enable nginx 2>/dev/null || true
  fi
}

require_root() {
  [[ "$(id -u)" -eq 0 ]] || die "Run as root"
}

ensure_packages() {
  local need=()
  command -v curl >/dev/null || need+=(curl)
  command -v nginx >/dev/null || need+=(nginx)
  command -v certbot >/dev/null || need+=(certbot)
  if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null; then
    need+=(docker.io docker-compose-plugin)
  fi

  if [[ ${#need[@]} -gt 0 ]]; then
    info "Installing packages: ${need[*]}"
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${need[@]}"
  fi

  if command -v nginx >/dev/null; then
    systemctl enable nginx
    systemctl start nginx
  fi

  mkdir -p /var/www/certbot /etc/letsencrypt
  if [[ ! -f /etc/letsencrypt/options-ssl-nginx.conf ]]; then
    if [[ -f /usr/share/certbot/options-ssl-nginx.conf ]]; then
      cp /usr/share/certbot/options-ssl-nginx.conf /etc/letsencrypt/
    elif [[ ! -f /etc/letsencrypt/options-ssl-nginx.conf ]]; then
      cat > /etc/letsencrypt/options-ssl-nginx.conf << 'EOF'
ssl_session_cache shared:le_nginx_SSL:10m;
ssl_session_timeout 1440m;
ssl_protocols TLSv1.2 TLSv1.3;
ssl_prefer_server_ciphers off;
EOF
    fi
  fi
  [[ -f /etc/letsencrypt/ssl-dhparams.pem ]] \
    || openssl dhparam -out /etc/letsencrypt/ssl-dhparams.pem 2048 2>/dev/null \
    || true
}

detect_webroot() {
  local found
  found="$(grep -rh "acme-challenge" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null \
    | grep -oE 'root[[:space:]]+[^;]+' | awk '{print $2}' | head -1 || true)"
  if [[ -n "$found" ]]; then
    WEBROOT="$found"
  fi
  mkdir -p "$WEBROOT"
  info "ACME webroot: $WEBROOT"
}

detect_cert() {
  local c name
  local candidates=("$CERT_PRIMARY" "$CERT_ALT" "chat.bttsrvvrs.org" "api.bttsrvvrs.org" "bttsrvvrs.org")

  for c in "${candidates[@]}"; do
    if [[ -f "/etc/letsencrypt/live/${c}/fullchain.pem" ]]; then
      CERT_NAME="$c"
      CERT_LIVE="/etc/letsencrypt/live/${c}"
      info "Found certificate: $CERT_NAME"
      return 0
    fi
  done

  for name in /etc/letsencrypt/live/*/; do
    [[ -f "${name}fullchain.pem" ]] || continue
    c="$(basename "$name")"
    [[ "$c" == "README" ]] && continue
    CERT_NAME="$c"
    CERT_LIVE="/etc/letsencrypt/live/${c}"
    info "Using detected certificate: $CERT_NAME"
    return 0
  done

  info "No existing Let's Encrypt certificate — will request one for ${VAULT_DOMAIN} only"
  CERT_NAME="$VAULT_DOMAIN"
  CERT_LIVE="/etc/letsencrypt/live/${VAULT_DOMAIN}"
  return 0
}

detect_nginx_mode() {
  if [[ "$NGINX_MODE" != "auto" ]]; then
    info "nginx mode: $NGINX_MODE (forced)"
    return
  fi

  if [[ -f "$STREAM_DST" ]] && grep -qE 'crm_ssl|8443' "$STREAM_DST" 2>/dev/null; then
    NGINX_MODE="sni"
  else
    NGINX_MODE="direct"
  fi
  info "nginx mode: $NGINX_MODE"
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
    echo "File: $ENV_FILE"
    echo "Admin: https://${VAULT_DOMAIN}/admin"
    echo "============================="
    echo ""
  else
    info "Using existing $ENV_FILE"
  fi
}

start_vaultwarden() {
  info "Starting Vaultwarden (CRM is not touched)..."
  cd "$BW_DIR"
  docker compose --env-file "$ENV_FILE" up -d
  sleep 3
  curl -sf "http://127.0.0.1:19180/alive" >/dev/null \
    || die "Vaultwarden not responding on 127.0.0.1:19180"
}

install_http_nginx() {
  sed "s/huitawarden.bttsrvvrs.org/${VAULT_DOMAIN}/g" \
    "$NGINX_DIR/vaultwarden-http.conf" > /etc/nginx/sites-available/vaultwarden-http
  ln -sf /etc/nginx/sites-available/vaultwarden-http /etc/nginx/sites-enabled/02-vaultwarden-http
  nginx_apply
}

cert_has_domain() {
  [[ -f "${CERT_LIVE}/fullchain.pem" ]] \
    && openssl x509 -in "${CERT_LIVE}/fullchain.pem" -noout -text 2>/dev/null \
      | grep -q "DNS:${VAULT_DOMAIN}"
}

obtain_certificate() {
  if cert_has_domain; then
    info "Certificate already includes ${VAULT_DOMAIN}"
    return
  fi

  detect_webroot

  if [[ -f "${CERT_LIVE}/fullchain.pem" ]]; then
    info "Expanding certificate ${CERT_NAME} for ${VAULT_DOMAIN}..."
    local args=(-d "$CERT_NAME" -d "$VAULT_DOMAIN")
    [[ "$CERT_ALT" != "$CERT_NAME" && -f "/etc/letsencrypt/live/${CERT_ALT}/fullchain.pem" ]] \
      && args=(-d "$CERT_ALT" "${args[@]}")
    certbot certonly --webroot -w "$WEBROOT" \
      "${args[@]}" \
      --expand --non-interactive --agree-tos \
      --email "${ACME_EMAIL:-admin@${VAULT_DOMAIN#*.}}" \
      || die "certbot expand failed — check DNS and port 80 for ${VAULT_DOMAIN}"
  else
    info "Requesting new certificate for ${VAULT_DOMAIN}..."
    certbot certonly --webroot -w "$WEBROOT" \
      -d "$VAULT_DOMAIN" \
      --non-interactive --agree-tos \
      --email "${ACME_EMAIL:-admin@${VAULT_DOMAIN#*.}}" \
      || die "certbot failed — check DNS and port 80 for ${VAULT_DOMAIN}"
    CERT_NAME="$VAULT_DOMAIN"
    CERT_LIVE="/etc/letsencrypt/live/${VAULT_DOMAIN}"
  fi
}

patch_sni_stream() {
  if [[ "$NGINX_MODE" != "sni" ]]; then
    info "Skipping SNI patch (direct nginx mode)"
    return
  fi

  [[ -f "$STREAM_DST" ]] || die "SNI split config missing: $STREAM_DST"

  if grep -q "$VAULT_DOMAIN" "$STREAM_DST"; then
    info "SNI already routes ${VAULT_DOMAIN}"
    return
  fi

  info "Adding ${VAULT_DOMAIN} to SNI map..."
  cp "$STREAM_DST" "${STREAM_DST}.bak.$(date +%Y%m%d%H%M%S)"
  if grep -q "$SNI_ANCHOR" "$STREAM_DST"; then
    sed -i "/${SNI_ANCHOR}/a\\    ${VAULT_DOMAIN}   crm_ssl;" "$STREAM_DST"
  else
    die "Cannot patch SNI — anchor domain ${SNI_ANCHOR} not found in $STREAM_DST"
  fi
  nginx_apply
}

write_ssl_nginx_config() {
  local dst="/etc/nginx/sites-available/vaultwarden-ssl"
  local template

  if [[ "$NGINX_MODE" == "sni" ]]; then
    template="$NGINX_DIR/vaultwarden-ssl.conf"
  else
    template="$NGINX_DIR/vaultwarden-ssl-direct.conf"
  fi

  [[ -f "$template" ]] || die "Missing nginx template: $template"

  sed \
    -e "s/huitawarden.bttsrvvrs.org/${VAULT_DOMAIN}/g" \
    -e "s|/etc/letsencrypt/live/chat.bttsrvvrs.org|${CERT_LIVE}|g" \
    -e "s|__CERT_FULLCHAIN__|${CERT_LIVE}/fullchain.pem|g" \
    -e "s|__CERT_PRIVKEY__|${CERT_LIVE}/privkey.pem|g" \
    "$template" > "$dst"
}

install_ssl_nginx() {
  write_ssl_nginx_config
  ln -sf /etc/nginx/sites-available/vaultwarden-ssl /etc/nginx/sites-enabled/03-vaultwarden-ssl
  rm -f /etc/nginx/sites-enabled/default
  nginx_apply
}

verify() {
  curl -sf "https://${VAULT_DOMAIN}/alive" && echo ""
  docker ps --filter name=vaultwarden
}

main() {
  require_root

  echo ""
  echo "Standalone Vaultwarden install"
  echo "  Domain: https://${VAULT_DOMAIN}"
  echo "  CRM containers: NOT modified"
  echo ""

  if [[ "${1:-}" != "-y" ]]; then
    read -r -p "Continue? [y/N] " ans
    ans="$(printf '%s' "$ans" | tr -d '\r' | tr '[:upper:]' '[:lower:]')"
    [[ "$ans" == "y" || "$ans" == "yes" ]] || { echo "Aborted."; exit 0; }
  fi

  ensure_packages
  command -v docker >/dev/null || die "docker not installed"
  command -v nginx >/dev/null || die "nginx install failed"
  command -v certbot >/dev/null || die "certbot install failed"

  detect_cert
  detect_nginx_mode

  ensure_env
  start_vaultwarden
  install_http_nginx
  obtain_certificate
  patch_sni_stream
  install_ssl_nginx
  verify

  echo ""
  echo "Done."
  echo "  Web:   https://${VAULT_DOMAIN}"
  echo "  Admin: https://${VAULT_DOMAIN}/admin"
  echo "  Token: grep ADMIN_TOKEN ${ENV_FILE}"
}

main "$@"
