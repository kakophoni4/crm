#!/usr/bin/env bash
# Persist PBX synchronization independently of the application containers.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
if [[ ! -f "$ROOT/deploy/.env.staging" ]]; then
  echo "Missing deployment environment" >&2
  exit 1
fi
if docker ps --format '{{.Names}}' | grep -qx 'crm-telephony-sync'; then
  echo "crm-telephony-sync container already runs; keep one synchronization scheduler" >&2
  exit 1
fi
if [[ -f /etc/cron.d/crm-telephony-sync ]]; then
  mv /etc/cron.d/crm-telephony-sync "/etc/cron.d/crm-telephony-sync.disabled.$(date +%Y%m%d%H%M%S)"
fi
cat > /etc/systemd/system/crm-telephony-sync.service <<EOF
[Unit]
Description=Synchronize CRM phone extensions with Asterisk
Requires=docker.service
After=docker.service
[Service]
Type=oneshot
WorkingDirectory=$ROOT
Environment=ENV_FILE=deploy/.env.staging
ExecStart=/bin/bash $ROOT/scripts/deploy/vps/telephony-sync.sh
UMask=0077
TimeoutStartSec=90
EOF
cat > /etc/systemd/system/crm-telephony-sync.timer <<'EOF'
[Unit]
Description=Keep CRM telephone accounts synchronized
[Timer]
OnBootSec=15s
OnUnitInactiveSec=5s
AccuracySec=1s
Unit=crm-telephony-sync.service
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now crm-telephony-sync.timer
systemctl start crm-telephony-sync.service
systemctl is-active --quiet crm-telephony-sync.timer
echo "PBX synchronization timer enabled (5 seconds after each run)"
