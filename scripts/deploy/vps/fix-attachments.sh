#!/usr/bin/env bash
# Rebuild after attachment proxy changes (MinIO is internal — browser uses API download).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/deploy/vps/compose.sh"

REQUIRED=(
  "$ROOT/app/shared/storage.py"
  "$ROOT/app/modules/chats/serialization.py"
  "$ROOT/app/modules/chats/messages.py"
  "$ROOT/app/modules/chats/router.py"
  "$ROOT/app/workers/bots/download_attachment.py"
  "$ROOT/frontend/src/widgets/chat/MessageAttachment.vue"
  "$ROOT/frontend/src/widgets/chat/MessageList.vue"
  "$ROOT/frontend/src/shared/lib/attachment-blob-cache.ts"
  "$ROOT/frontend/src/features/chats/store.ts"
)

echo "=== Check files ==="
for f in "${REQUIRED[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "MISSING: $f" >&2
    echo "Upload from Windows (scp) then re-run this script." >&2
    exit 1
  fi
  echo "OK $(basename "$f")"
done

echo ""
echo "=== Rebuild api, worker, frontend ==="
compose build api worker frontend
compose up -d api worker frontend

echo ""
compose ps api worker frontend
echo ""
echo "Done. Ctrl+F5 in browser, send a NEW photo in Telegram."
echo "Debug API attachment JSON:"
echo "  curl -s -H \"Authorization: Bearer <token>\" \\"
echo "    https://api.crmkanasha.org/api/v1/chats/<chat_id>/messages?limit=5 | python3 -m json.tool"
