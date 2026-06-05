#!/usr/bin/env bash
# Mirror MinIO buckets to local backup dir (dev) or remote S3 (prod).
# Requires: docker, crm-minio running, bucket crm-backups (see crm-minio-init).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${MINIO_BACKUP_DIR:-./backups/minio}"
MINIO_CONTAINER="${MINIO_CONTAINER:-crm-minio}"
MINIO_ALIAS="${MINIO_ALIAS:-myminio}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://crm-minio:9000}"
MINIO_USER="${S3_ACCESS_KEY:-minio}"
MINIO_PASS="${S3_SECRET_KEY:-miniominio}"
BUCKETS="${MINIO_BACKUP_BUCKETS:-crm-files crm-backups}"

mkdir -p "$BACKUP_DIR"

if ! docker inspect "$MINIO_CONTAINER" >/dev/null 2>&1; then
  echo "Container ${MINIO_CONTAINER} not found." >&2
  exit 1
fi

# Dev: crm-net; staging compose: crm-staging-net (override via MINIO_DOCKER_NETWORK).
MINIO_DOCKER_NETWORK="${MINIO_DOCKER_NETWORK:-}"
if [[ -z "$MINIO_DOCKER_NETWORK" ]]; then
  MINIO_DOCKER_NETWORK="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' \
    "$MINIO_CONTAINER" | head -n1)"
fi
if [[ -z "$MINIO_DOCKER_NETWORK" ]]; then
  echo "Could not detect Docker network for ${MINIO_CONTAINER}; set MINIO_DOCKER_NETWORK." >&2
  exit 1
fi

TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
DEST="${BACKUP_DIR}/${TIMESTAMP}"
mkdir -p "$DEST"

for bucket in $BUCKETS; do
  echo "Mirroring ${bucket} -> ${DEST}/${bucket}"
  docker run --rm --network "$MINIO_DOCKER_NETWORK" \
    -v "${DEST}:/backup" \
    minio/mc:latest \
    sh -c "
      mc alias set ${MINIO_ALIAS} ${MINIO_ENDPOINT} ${MINIO_USER} ${MINIO_PASS} &&
      mc mirror --overwrite ${MINIO_ALIAS}/${bucket} /backup/${bucket}
    "
done

echo "OK: ${DEST}"
ln -sfn "$DEST" "${BACKUP_DIR}/latest" 2>/dev/null || true

RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
if [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] && [[ "$RETENTION_DAYS" -gt 0 ]]; then
  find "$BACKUP_DIR" -maxdepth 1 -type d -name '20*' -mtime +"$RETENTION_DAYS" -exec rm -rf {} +
fi
