#!/usr/bin/env bash
# SNI split: CRM HTTPS on app/api SNI, xray REALITY on everything else — both on public :443.
#
# Run on VPS as root from /root/crm:
#   bash scripts/deploy/vps/install-sni-split.sh
#
# BEFORE running: read docs/SNI_SPLIT_VPN_TLS.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
NGINX_SRC="$ROOT/deploy/server/nginx"
STREAM_DST="/etc/nginx/stream.conf.d/00-sni-split.conf"
SSL_SITE="/etc/nginx/sites-available/crmkanasha-ssl"
HTTP_SITE="/etc/nginx/sites-available/crmkanasha"
XRAY_CONFIG="${XRAY_CONFIG:-/usr/local/etc/xray/config.json}"
XRAY_INTERNAL_PORT="${XRAY_INTERNAL_PORT:-10443}"
CRM_SSL_PORT="${CRM_SSL_PORT:-8443}"
CERT_PRIMARY="${CERT_PRIMARY:-app.crmkanasha.org}"
CERT_ALT="${CERT_ALT:-api.crmkanasha.org}"
CERT_LIVE="/etc/letsencrypt/live/${CERT_PRIMARY}"

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

require_root() {
  [[ "$(id -u)" -eq 0 ]] || die "Run as root"
}

ensure_packages() {
  info "Installing nginx, certbot..."
  apt-get update -qq
  apt-get install -y nginx certbot python3-certbot-nginx jq
  mkdir -p /var/www/certbot /etc/nginx/stream.conf.d
}

ensure_stream_block() {
  if grep -q 'stream.conf.d' /etc/nginx/nginx.conf 2>/dev/null; then
    return
  fi
  info "Adding stream {} block to /etc/nginx/nginx.conf"
  cat >> /etc/nginx/nginx.conf << 'EOF'

# CRM SNI split (443 → CRM TLS or xray)
stream {
    include /etc/nginx/stream.conf.d/*.conf;
}
EOF
}

install_http_nginx() {
  info "Installing HTTP nginx (port 80, ACME webroot)..."
  cp "$NGINX_SRC/crmkanasha.conf" "$HTTP_SITE"
  ln -sf "$HTTP_SITE" /etc/nginx/sites-enabled/00-crmkanasha
  nginx -t
  systemctl enable nginx
  systemctl reload nginx
}

obtain_certificates() {
  if [[ -f "$CERT_LIVE/fullchain.pem" ]]; then
    info "Certificate already exists: $CERT_LIVE"
    return
  fi
  info "Obtaining Let's Encrypt certificate (HTTP-01 on port 80)..."
  certbot certonly --webroot \
    -w /var/www/certbot \
    -d "$CERT_PRIMARY" \
    -d "$CERT_ALT" \
    --non-interactive --agree-tos \
    --email "${ACME_EMAIL:-admin@${CERT_PRIMARY#*.}}" \
    || die "certbot failed — check DNS and port 80"
}

patch_xray_listen() {
  [[ -f "$XRAY_CONFIG" ]] || die "xray config not found: $XRAY_CONFIG"

  if ss -tlnp | grep -q ":443.*xray"; then
    info "xray still bound to :443 — patching to 127.0.0.1:${XRAY_INTERNAL_PORT}"
    cp "$XRAY_CONFIG" "${XRAY_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"

    # Replace "port": 443 with internal port (keep other fields).
    if command -v jq >/dev/null 2>&1; then
      tmp="$(mktemp)"
      jq --argjson p "$XRAY_INTERNAL_PORT" '
        .inbounds |= map(
          if .port == 443 then . + {"listen": "127.0.0.1", "port": $p} else . end
        )
      ' "$XRAY_CONFIG" > "$tmp" && mv "$tmp" "$XRAY_CONFIG"
    else
      sed -i "s/\"port\": 443/\"port\": ${XRAY_INTERNAL_PORT}/" "$XRAY_CONFIG"
      sed -i 's/"listen": "0.0.0.0"/"listen": "127.0.0.1"/' "$XRAY_CONFIG" || true
    fi

    systemctl restart xray
    sleep 2
    ss -tlnp | grep -q ":443.*xray" && die "xray still on :443 after restart — fix config manually"
    ss -tlnp | grep -q ":${XRAY_INTERNAL_PORT}.*xray" || die "xray not listening on 127.0.0.1:${XRAY_INTERNAL_PORT}"
    info "xray now on 127.0.0.1:${XRAY_INTERNAL_PORT}"
  else
    info "xray not on :443 (already internal?) — skipping patch"
    ss -tlnp | grep -q ":${XRAY_INTERNAL_PORT}" || \
      die "Expected xray on 127.0.0.1:${XRAY_INTERNAL_PORT} — set manually in $XRAY_CONFIG"
  fi
}

install_stream_and_ssl() {
  info "Installing SNI stream dispatcher on :443..."
  cp "$NGINX_SRC/stream-sni.conf" "$STREAM_DST"

  info "Installing CRM TLS on 127.0.0.1:${CRM_SSL_PORT}..."
  cp "$NGINX_SRC/crmkanasha-ssl.conf" "$SSL_SITE"
  ln -sf "$SSL_SITE" /etc/nginx/sites-enabled/01-crmkanasha-ssl

  if [[ ! -f "$CERT_LIVE/fullchain.pem" ]]; then
    die "Missing cert: $CERT_LIVE/fullchain.pem — run certbot first"
  fi

  nginx -t
  systemctl reload nginx
}

enable_http_redirect() {
  info "Enabling HTTP → HTTPS redirect..."
  cp "$NGINX_SRC/crmkanasha-redirect.conf" "$HTTP_SITE"
  nginx -t
  systemctl reload nginx
}

update_crm_env() {
  local env_file="$ROOT/deploy/.env.staging"
  [[ -f "$env_file" ]] || { info "No $env_file — skip env update"; return; }

  info "Updating $env_file for HTTPS..."
  sed -i 's|^CORS_ALLOWED_ORIGINS=.*|CORS_ALLOWED_ORIGINS=https://app.crmkanasha.org|' "$env_file"
  sed -i 's|^VITE_API_BASE_URL=.*|VITE_API_BASE_URL=https://api.crmkanasha.org/api/v1|' "$env_file"
  sed -i 's|^VITE_WS_URL=.*|VITE_WS_URL=wss://api.crmkanasha.org/ws|' "$env_file"

  info "Rebuilding frontend (VITE_* baked at build time)..."
  bash "$ROOT/scripts/deploy/vps/update.sh"
}

verify() {
  info "Verification..."
  echo ""
  echo "--- listeners ---"
  ss -tlnp | grep -E ':443|:80|:8443|:10443' || true
  echo ""
  echo "--- CRM HTTPS ---"
  curl -sf "https://${CERT_PRIMARY}/" -o /dev/null -w "app: HTTP %{http_code}\n" || echo "app HTTPS: FAIL"
  curl -sf "https://${CERT_ALT}/healthz" && echo "" || echo "api HTTPS: FAIL"
  echo ""
  echo "--- VPN path (TCP to :443, non-CRM SNI goes to xray) ---"
  echo "Test VPN client manually — REALITY should still connect to $(hostname -I | awk '{print $1}'):443"
  echo ""
  bash "$ROOT/scripts/deploy/vps/status.sh" || true
}

certbot_renew_hook() {
  local hook="/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh"
  mkdir -p "$(dirname "$hook")"
  cat > "$hook" << 'EOF'
#!/bin/bash
nginx -t && systemctl reload nginx
EOF
  chmod +x "$hook"
}

main() {
  require_root
  cd "$ROOT"

  echo ""
  echo "SNI split install — CRM HTTPS + xray REALITY on same :443"
  echo "Domain: ${CERT_PRIMARY}, ${CERT_ALT}"
  echo "xray internal port: ${XRAY_INTERNAL_PORT}"
  echo ""
  read -r -p "Continue? [y/N] " ans
  [[ "${ans,,}" == "y" ]] || exit 0

  ensure_packages
  ensure_stream_block
  install_http_nginx
  obtain_certificates

  echo ""
  echo ">>> Next: xray moves off public :443 (~5 sec VPN drop)"
  read -r -p "Patch xray and enable SNI split now? [y/N] " ans2
  [[ "${ans2,,}" == "y" ]] || { echo "Stopped after certs. Run again or continue manually."; exit 0; }

  patch_xray_listen
  install_stream_and_ssl
  enable_http_redirect
  certbot_renew_hook

  read -r -p "Update .env.staging and rebuild frontend? [y/N] " ans3
  [[ "${ans3,,}" == "y" ]] && update_crm_env

  verify
  echo ""
  echo "Done. Docs: docs/SNI_SPLIT_VPN_TLS.md"
}

main "$@"
