#!/usr/bin/env bash
# Mark old pending attachments (presigned URL likely expired) as failed so UI stops spinning.
# Run on VPS: bash scripts/bots/mark_stale_pending_attachments.sh
# Optional: MIN_AGE_MINUTES=55 bash scripts/bots/mark_stale_pending_attachments.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

MIN_AGE_MINUTES="${MIN_AGE_MINUTES:-55}"

echo "=== Mark pending attachments older than ${MIN_AGE_MINUTES}m as failed ==="
compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -v ON_ERROR_STOP=1 -c "
UPDATE messages m
SET attachments = sub.new_attachments
FROM (
  SELECT
    m2.id,
    jsonb_agg(
      CASE
        WHEN elem->>'status' IN ('pending', 'queued')
         AND coalesce(elem->>'url', '') <> ''
         AND m2.created_at < now() - interval '${MIN_AGE_MINUTES} minutes'
        THEN elem || jsonb_build_object(
          'status', 'failed',
          'error', 'Ссылка на файл истекла (presigned URL). Повторная загрузка невозможна.'
        )
        ELSE elem
      END
      ORDER BY ord
    ) AS new_attachments
  FROM messages m2
  CROSS JOIN LATERAL jsonb_array_elements(coalesce(m2.attachments, '[]'::jsonb))
    WITH ORDINALITY AS t(elem, ord)
  WHERE m2.attachments::text LIKE '%\"pending\"%'
    AND m2.created_at < now() - interval '${MIN_AGE_MINUTES} minutes'
  GROUP BY m2.id
) sub
WHERE m.id = sub.id;
"

echo ""
compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" -c "
SELECT att->>'status' AS status, count(*)
FROM messages m
CROSS JOIN LATERAL jsonb_array_elements(coalesce(m.attachments, '[]'::jsonb)) AS att
WHERE att->>'status' IN ('pending', 'queued', 'failed')
GROUP BY 1 ORDER BY 1;
"
