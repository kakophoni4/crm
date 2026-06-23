#!/usr/bin/env bash
# Re-queue download_attachment jobs for messages stuck in pending/queued.
# Run on VPS: bash scripts/bots/retry_pending_attachments.sh
# Optional: HOURS=0 bash scripts/bots/retry_pending_attachments.sh   # no time limit
#           HOURS=168 bash scripts/bots/retry_pending_attachments.sh # last 7 days
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

HOURS="${HOURS:-72}"

if [[ "${HOURS}" == "0" ]]; then
  time_filter=""
  window_label="all time"
else
  time_filter="AND m.created_at > now() - interval '${HOURS} hours'"
  window_label="last ${HOURS}h"
fi

echo "=== Pending / queued attachments (${window_label}) ==="
count_query="
SELECT count(*)
FROM messages m
CROSS JOIN LATERAL jsonb_array_elements(coalesce(m.attachments, '[]'::jsonb)) AS t(att)
WHERE coalesce(att->>'url', '') <> ''
  AND att->>'status' IN ('pending', 'queued')
  ${time_filter};
"
total="$(
  compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -At -c "${count_query}" \
    | tr -d '\r'
)"
echo "found: ${total:-0}"

rows="$(
  compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -At -c "
SELECT m.id, ordinality - 1 AS att_idx
FROM messages m
CROSS JOIN LATERAL jsonb_array_elements(coalesce(m.attachments, '[]'::jsonb)) WITH ORDINALITY AS t(att, ordinality)
WHERE coalesce(att->>'url', '') <> ''
  AND att->>'status' IN ('pending', 'queued')
  ${time_filter}
ORDER BY m.id DESC;
" | tr -d '\r'
)"

if [[ -z "${rows// }" ]]; then
  echo "Nothing to retry."
  exit 0
fi

count=0
while IFS='|' read -r message_id att_idx; do
  [[ -z "${message_id// }" ]] && continue
  payload="{\"type\":\"download_attachment\",\"payload\":{\"message_id\":${message_id},\"attachment_index\":${att_idx},\"attempt\":0}}"
  # Redirect stdin so redis-cli does not consume the remaining lines from <<< "$rows".
  compose exec -T redis redis-cli XADD crm:bots:jobs '*' data "$payload" </dev/null >/dev/null
  echo "queued message_id=${message_id} attachment_index=${att_idx}"
  count=$((count + 1))
done <<< "$rows"

echo ""
echo "Enqueued ${count} download_attachment job(s). Watch: compose logs worker --tail 50 -f"
echo "Note: presigned bridge URLs expire after ~1h; older pending will get 403 and become failed."
