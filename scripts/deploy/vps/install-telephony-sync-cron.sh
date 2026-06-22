#!/usr/bin/env bash
# Install a cron job that keeps Asterisk config in sync with CRM DB.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CRON_FILE="/etc/cron.d/crm-telephony-sync"

cat > "$CRON_FILE" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
* * * * * root cd $ROOT && ENV_FILE=deploy/.env.staging bash scripts/deploy/vps/telephony-sync.sh >/var/log/crm-telephony-sync.log 2>&1
EOF

chmod 0644 "$CRON_FILE"
echo "Installed $CRON_FILE"
