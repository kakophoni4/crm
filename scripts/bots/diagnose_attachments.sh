#!/usr/bin/env bash
# Diagnose why inbound bot photos/files do not show in CRM UI.
# Run on VPS: bash scripts/bots/diagnose_attachments.sh
# Optional: BOT_CODE=stobrok_bot HOURS=48 bash scripts/bots/diagnose_attachments.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

BOT_CODE="${BOT_CODE:-}"
HOURS="${HOURS:-24}"
LIMIT="${LIMIT:-15}"

echo "=== Containers ==="
compose ps api worker minio postgres 2>/dev/null || compose ps

echo ""
echo "=== Worker recent attachment logs ==="
compose logs worker --tail 300 2>/dev/null \
  | grep -E 'download_attachment|process_bot_event|bot_event' \
  | tail -n 40 || echo "(no matching log lines — try: compose logs worker --tail 200)"

echo ""
echo "=== Postgres: bots ==="
compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -c \
  "SELECT id, code, name, is_active, department_id FROM bots ORDER BY id;"

BOT_FILTER=""
if [[ -n "$BOT_CODE" ]]; then
  BOT_FILTER="AND b.code = '${BOT_CODE//\'/}'"
  echo ""
  echo "Filtering by BOT_CODE=$BOT_CODE"
fi

echo ""
echo "=== Recent inbound messages with attachments (last ${HOURS}h) ==="
compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -c "
SELECT
  m.id AS message_id,
  b.code AS bot_code,
  m.chat_id,
  m.created_at,
  m.kind,
  left(coalesce(m.text, ''), 40) AS text_preview,
  jsonb_array_length(coalesce(m.attachments, '[]'::jsonb)) AS att_count,
  m.attachments
FROM messages m
JOIN chats c ON c.id = m.chat_id
JOIN bots b ON b.id = c.bot_id
WHERE m.direction = 'inbound'
  AND m.created_at > now() - interval '${HOURS} hours'
  AND coalesce(jsonb_array_length(m.attachments), 0) > 0
  ${BOT_FILTER}
ORDER BY m.id DESC
LIMIT ${LIMIT};
"

echo ""
echo "=== Attachment status summary (last ${HOURS}h) ==="
compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -c "
WITH expanded AS (
  SELECT
    b.code AS bot_code,
    m.id AS message_id,
    att->>'status' AS status,
    att->>'type' AS att_type,
    CASE WHEN att ? 'url' THEN 'yes' ELSE 'no' END AS has_url,
    CASE WHEN att ? 'storage_key' THEN 'yes' ELSE 'no' END AS has_storage,
    left(coalesce(att->>'error', ''), 120) AS error
  FROM messages m
  JOIN chats c ON c.id = m.chat_id
  JOIN bots b ON b.id = c.bot_id
  CROSS JOIN LATERAL jsonb_array_elements(coalesce(m.attachments, '[]'::jsonb)) AS att
  WHERE m.direction = 'inbound'
    AND m.created_at > now() - interval '${HOURS} hours'
    ${BOT_FILTER}
)
SELECT bot_code, status, att_type, has_url, has_storage, count(*) AS cnt
FROM expanded
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 2;
"

echo ""
echo "=== Failed attachments (detail) ==="
compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -c "
SELECT
  b.code,
  m.id,
  m.created_at,
  att
FROM messages m
JOIN chats c ON c.id = m.chat_id
JOIN bots b ON b.id = c.bot_id
CROSS JOIN LATERAL jsonb_array_elements(coalesce(m.attachments, '[]'::jsonb)) AS att
WHERE m.direction = 'inbound'
  AND att->>'status' = 'failed'
  AND m.created_at > now() - interval '${HOURS} hours'
  ${BOT_FILTER}
ORDER BY m.id DESC
LIMIT 10;
"

echo ""
echo "=== Bot event inbox failures (last ${HOURS}h) ==="
compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -c "
SELECT
  bei.event_id,
  b.code,
  bei.status,
  left(coalesce(bei.last_error, ''), 200) AS last_error,
  bei.received_at
FROM bot_events_inbox bei
JOIN bots b ON b.id = bei.bot_id
WHERE bei.received_at > now() - interval '${HOURS} hours'
  AND bei.status = 'failed'
  ${BOT_FILTER}
ORDER BY bei.id DESC
LIMIT 10;
"

echo ""
echo "=== Interpretation ==="
cat <<'EOF'
pending + has_url=yes  → worker still downloading or stuck (check worker logs)
failed               → CRM could not download URL (see error field / worker logs)
ready + has_storage=no → bot sent attachment without url (wrong contract)
ready + has_storage=yes → should work; if UI blank — hard-refresh, check API download_path
no rows with attachments → bot does not send payload.message.attachments[] with url
EOF

echo ""
echo "Contract reminder: each attachment needs a downloadable url, e.g."
echo '  {"type":"photo","url":"https://api.telegram.org/file/bot<token>/...","mime":"image/jpeg"}'
echo ""
echo "Reference bridge: scripts/bots/tg_crm_bridge/main.py (_build_attachments)"
