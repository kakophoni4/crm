#!/usr/bin/env bash
# Re-queue download_attachment jobs for messages stuck in pending/queued.
# Run on VPS: bash scripts/bots/retry_pending_attachments.sh
# Optional: HOURS=48 bash scripts/bots/retry_pending_attachments.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

HOURS="${HOURS:-72}"

echo "=== Pending / queued attachments (last ${HOURS}h) ==="
rows="$(
  compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -At -c "
SELECT m.id, ordinality - 1 AS att_idx
FROM messages m
CROSS JOIN LATERAL jsonb_array_elements(coalesce(m.attachments, '[]'::jsonb)) WITH ORDINALITY AS t(att, ordinality)
WHERE m.created_at > now() - interval '${HOURS} hours'
  AND att->>'status' IN ('pending', 'queued')
  AND coalesce(att->>'url', '') <> ''
ORDER BY m.id DESC;
"
)"

if [[ -z "${rows// }" ]]; then
  echo "Nothing to retry."
  exit 0
fi

count=0
while IFS='|' read -r message_id att_idx; do
  [[ -z "$message_id" ]] && continue
  payload="{\"type\":\"download_attachment\",\"payload\":{\"message_id\":${message_id},\"attachment_index\":${att_idx},\"attempt\":0}}"
  compose exec -T redis redis-cli XADD crm:bots:jobs '*' data "$payload" >/dev/null
  echo "queued message_id=${message_id} attachment_index=${att_idx}"
  count=$((count + 1))
done <<< "$rows"

echo ""
echo "Enqueued ${count} download_attachment job(s). Watch: compose logs worker --tail 50 -f"
