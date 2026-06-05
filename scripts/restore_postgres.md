# PostgreSQL restore (CRM Chat Center)

Dev stack uses container `crm-postgres`, user `crm`, database `crm`.  
**Warning:** restore overwrites data in the target database. Stop API/workers first.

## Prerequisites

1. Dev dependencies running: `docker compose -f docker/docker-compose.dev.yaml up -d`
2. Backup file: `backups/postgres/crm_YYYYMMDD_HHMMSS.dump` (custom format, `pg_dump -Fc`)
3. No active connections to `crm` (stop `crm-api-metrics`, local uvicorn, `crm-worker`)

## Step 1 — Stop consumers

```bash
docker stop crm-worker crm-api-metrics 2>/dev/null || true
# If API runs on host: stop uvicorn
```

## Step 2 — Drop and recreate database (inside container)

```bash
docker exec -it crm-postgres psql -U crm -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'crm' AND pid <> pg_backend_pid();"

docker exec -it crm-postgres psql -U crm -d postgres -c "DROP DATABASE IF EXISTS crm;"
docker exec -it crm-postgres psql -U crm -d postgres -c "CREATE DATABASE crm OWNER crm;"
```

## Step 3 — Restore from dump

From repo root (adjust path to your dump):

```bash
BACKUP=./backups/postgres/crm_20260101_030000.dump

docker exec -i crm-postgres pg_restore -U crm -d crm --no-owner --role=crm < "$BACKUP"
```

On Windows (PowerShell) — prefer `docker cp` (binary-safe):

```powershell
$Dump = ".\backups\postgres\crm_20260101_030000.dump"
docker cp $Dump crm-postgres:/tmp/restore.dump
docker exec crm-postgres pg_restore -U crm -d crm --no-owner --role=crm /tmp/restore.dump
docker exec crm-postgres rm -f /tmp/restore.dump
```

If `pg_restore` reports harmless errors about existing extensions, verify row counts:

```bash
docker exec crm-postgres psql -U crm -d crm -c "SELECT count(*) FROM users;"
```

## Step 4 — Migrations (if backup is older than code)

```bash
alembic upgrade head
```

## Step 5 — Start services

```bash
docker compose -f docker/docker-compose.dev.yaml up -d crm-worker
# API: make run  OR  monitoring stack api container
```

## Step 6 — Smoke test

- `curl http://localhost:8000/healthz`
- Login via frontend or `POST /api/v1/auth/login`

## Monthly drill (staging/prod)

1. Restore latest dump to an isolated instance (different volume / host).
2. Run migrations and smoke tests.
3. Record duration and issues in your ops log.
