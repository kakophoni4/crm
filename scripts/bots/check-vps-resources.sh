#!/usr/bin/env bash
# Quick VPS capacity check before raising TG file limits / Local Bot API.
set -euo pipefail

echo "=== Host ==="
hostnamectl 2>/dev/null | head -8 || uname -a
uptime
echo

echo "=== CPU / RAM ==="
nproc
free -h
echo

echo "=== Disk ==="
df -hT / /var /var/lib/docker 2>/dev/null || df -hT
echo
du -sh /var/lib/docker 2>/dev/null || true
docker system df 2>/dev/null || true
echo

echo "=== Docker containers (CPU / RAM) ==="
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' 2>/dev/null || true
echo

echo "=== MinIO volume (file storage) ==="
docker exec crm-staging-minio du -sh /data 2>/dev/null || \
  docker volume ls | grep -i minio || true
echo

echo "=== Local Bot API ==="
if docker ps --format '{{.Names}}' | grep -qx crm-telegram-bot-api; then
  docker ps --filter name=crm-telegram-bot-api --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  docker logs crm-telegram-bot-api --tail 15 2>/dev/null || true
else
  echo "crm-telegram-bot-api: not running"
fi
echo

echo "=== Bridge ==="
systemctl is-active tg-crm-bridge 2>/dev/null || echo "tg-crm-bridge: inactive/missing"
grep -E '^(TG_API_BASE|TG_FILE_BASE|TG_MAX_FILE_BYTES)=' /root/crm-bots/.env 2>/dev/null || true
echo

echo "=== CRM upload env ==="
grep -E '^MAX_UPLOAD_FILE_BYTES=' /root/crm/deploy/.env.staging 2>/dev/null || \
  echo "MAX_UPLOAD_FILE_BYTES not set in deploy/.env.staging (default 100MB after deploy)"
