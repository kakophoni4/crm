#!/usr/bin/env bash
# Backup PostgreSQL (dev: docker container crm-postgres).
# Schedule via cron, e.g. 0 3 * * * /path/to/repo/scripts/backup_postgres.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${BACKUP_DIR:-./backups/postgres}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-crm-postgres}"
POSTGRES_USER="${POSTGRES_USER:-crm}"
POSTGRES_DB="${POSTGRES_DB:-crm}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
OUTFILE="${BACKUP_DIR}/crm_${TIMESTAMP}.dump"

if ! docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1; then
  echo "Container ${POSTGRES_CONTAINER} not found. Start dev stack first." >&2
  exit 1
fi

echo "Dumping ${POSTGRES_DB} -> ${OUTFILE}"
docker exec "$POSTGRES_CONTAINER" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc >"$OUTFILE"
chmod 600 "$OUTFILE"
echo "OK: $(du -h "$OUTFILE" | cut -f1)"

if [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] && [[ "$RETENTION_DAYS" -gt 0 ]]; then
  find "$BACKUP_DIR" -name 'crm_*.dump' -type f -mtime +"$RETENTION_DAYS" -delete
  echo "Pruned dumps older than ${RETENTION_DAYS} days"
fi
