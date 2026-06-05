#!/usr/bin/env bash
# Inventory what's on the VPS before CRM deploy (Jitsi, Element, nginx, docker, xray).
# Run as root: bash scripts/deploy/vps/audit-server.sh
set -euo pipefail

echo "========== HOST =========="
hostname -f 2>/dev/null || hostname
echo "IP: $(hostname -I | awk '{print $1}')"
uname -a
echo ""

echo "========== DISK / RAM =========="
df -h / /var/lib/docker 2>/dev/null || df -h /
free -h
echo ""

echo "========== LISTEN PORTS (80,443,8443,10443,19001,19090) =========="
ss -tlnp | grep -E ':80|:443|:8443|:10443|:19001|:19090' || echo "(none of these)"
echo ""

echo "========== DOCKER CONTAINERS =========="
if command -v docker >/dev/null 2>&1; then
  docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
else
  echo "docker not installed"
fi
echo ""

echo "========== DOCKER COMPOSE PROJECTS (guess) =========="
for d in /root /opt /home/* /srv; do
  [[ -d "$d" ]] || continue
  find "$d" -maxdepth 3 \( -name 'docker-compose*.yml' -o -name 'docker-compose*.yaml' \) 2>/dev/null
done | sort -u | head -40
echo ""

echo "========== JITSI / ELEMENT / MATRIX (paths) =========="
find /root /opt /etc/nginx /srv -maxdepth 4 \( \
  -iname '*jitsi*' -o -iname '*element*' -o -iname '*matrix*' -o -iname '*synapse*' \
\) 2>/dev/null | head -30
echo ""

echo "========== NGINX SITES =========="
if command -v nginx >/dev/null 2>&1; then
  nginx -t 2>&1 || true
  echo "--- sites-enabled ---"
  ls -la /etc/nginx/sites-enabled/ 2>/dev/null || true
  echo "--- server_name (all vhosts) ---"
  grep -rh 'server_name' /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null | sort -u || true
  echo "--- stream (443 SNI) ---"
  ls -la /etc/nginx/stream.conf.d/ 2>/dev/null || echo "no stream.conf.d"
else
  echo "nginx not installed"
fi
echo ""

echo "========== SYSTEMD (jitsi, element, matrix, xray, crm) =========="
systemctl list-units --type=service --all 2>/dev/null | grep -iE 'jitsi|element|matrix|synapse|xray|crm|nginx|docker' || true
echo ""

echo "========== CERTBOT DOMAINS =========="
certbot certificates 2>/dev/null || echo "certbot not installed or no certs"
echo ""

echo "========== CRM already here? =========="
[[ -d /root/crm ]] && ls -la /root/crm | head -5 || echo "no /root/crm"
[[ -f /root/crm/deploy/.env.staging ]] && echo "deploy/.env.staging: present" || echo "deploy/.env.staging: missing"
echo ""

echo "========== GIT =========="
command -v git >/dev/null && git --version || echo "git not installed"
[[ -d /root/crm/.git ]] && (cd /root/crm && git remote -v && git log -1 --oneline) || echo "no git repo in /root/crm"
echo ""
echo "Done. Save this output before changing anything."
