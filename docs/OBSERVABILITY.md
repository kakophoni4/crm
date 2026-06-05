# Observability (Phase 6 — DevOps)

Prometheus + Grafana for local development. Production Alertmanager and Loki are planned in later phases.

## Quick start

1. Start dependencies (creates network `crm-net`):

   ```bash
   docker compose -f docker/docker-compose.dev.yaml up -d
   ```

2. Enable metrics in `.env` (or rely on the `api` container in the monitoring compose, which sets `METRICS_ENABLED=true`):

   ```env
   METRICS_ENABLED=true
   ```

3. Start monitoring stack:

   ```bash
   docker compose -f docker/docker-compose.dev.yaml -f docker/docker-compose.monitoring.yaml up -d
   ```

4. Wait for `crm-api-metrics` (`api-metrics` service) health (~1–2 min on first `pip install`).

## URLs (local dev)

| Service | URL | Notes |
|---------|-----|--------|
| Grafana | http://localhost:3000 | `admin` / `admin` (override via `GRAFANA_*` in `.env`) |
| Prometheus | http://localhost:9090 | Targets: http://localhost:9090/targets |
| API metrics | http://localhost:8000/metrics | Only if `METRICS_ENABLED=true` and API on host; container `api` is scraped internally |
| Prometheus alerts | http://localhost:9090/alerts | Rules evaluate; **no notifications on dev** |

## Dashboards

- **CRM Overview** — provisioned from `docker/grafana/dashboards/crm-overview.json`
  - HTTP request rate and latency (instrumentator)
  - Bot ingest (`bot_events_ingest_total`)
  - Bot outbound failures / retries (`bot_outbound_total`)
  - WebSocket active connections and disconnect rate
  - Redis stream pending (`redis_stream_pending`, including `crm:bots:jobs`)

## Prometheus scrape

Config: `docker/prometheus/prometheus.yml`

| Job | Target | Path |
|-----|--------|------|
| `crm-api` | `api-metrics:8000` (dev) / `api:8000` (staging) | `/metrics` |
| `prometheus` | `localhost:9090` | — |

The `api-metrics` service in `docker-compose.monitoring.yaml` exists so Prometheus can scrape without binding port 8000 on the host. If you run uvicorn locally instead, stop `api-metrics` and change the scrape target to `host.docker.internal:8000` (Docker Desktop on Windows/macOS). On **staging/prod**, Prometheus scrapes the real `api` container from `docker-compose.staging.yaml` (see [Staging / production validation](#staging--production-validation)).

Optional later: `redis_exporter` — uncomment the job in `prometheus.yml`.

## Alert rules

File: `docker/prometheus/alerts.yml`

| Alert | Condition (summary) |
|-------|---------------------|
| `BotOutboundFailureRateHigh` | >10% `bot_outbound_total{status="failed"}` over 5m |
| `RedisStreamDepthHigh` | `redis_stream_pending{stream="crm:bots:jobs"}` > 100 for 10m |
| `WsDisconnectRate` | `rate(ws_disconnect_total[5m])` > 10/s |
| `ApiErrorRate5xx` | >1% HTTP 5xx (`http_requests_total{status=~"5.."}`) over 5m |

**Dev:** `alerting.alertmanagers` is empty — alerts appear in the Prometheus UI only (no email/Telegram).  
**Prod:** see [Production wiring](#production-wiring) below; do not use `admin/admin` Grafana credentials.

## Production wiring

1. Copy examples (**no secrets in git**):

   ```bash
   cp deploy/docker-compose.monitoring.prod.yaml.example deploy/prod/docker-compose.monitoring.override.yaml
   cp docker/alertmanager/alertmanager.yml.example docker/alertmanager/alertmanager.yml
   ```

   `docker/prometheus/prometheus.prod.yml` is committed (Alertmanager target + smoke rules). Edit only `alertmanager.yml` on the host.

2. Edit `docker/alertmanager/alertmanager.yml` — configure `receivers` (webhook, email). File is **gitignored**. Use `alertmanager.yml.example` as the template.

3. Start stack (staging example):

   ```bash
   docker compose -f docker/docker-compose.staging.yaml \
     -f docker/docker-compose.monitoring.yaml \
     -f docker/docker-compose.monitoring.staging.yaml \
     -f deploy/prod/docker-compose.monitoring.override.yaml \
     --env-file deploy/.env.staging --profile with-proxy up -d
   ```

4. Verify — see [Staging / production validation](#staging--production-validation).

5. Recommended env (API/worker in `deploy/.env.staging` / `.env.prod`): `METRICS_ENABLED=true`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT=staging|production`, strong `GRAFANA_ADMIN_PASSWORD`.

Files:

| File | Purpose |
|------|---------|
| `deploy/docker-compose.monitoring.prod.yaml.example` | Alertmanager + Prometheus prod config mounts (copy to `deploy/prod/…`) |
| `docker/docker-compose.monitoring.prod.yaml.example` | Same overlay when merging from `docker/` only |
| `docker/prometheus/prometheus.prod.yml` | `alertmanagers: [alertmanager:9093]`, scrape `api:8000` |
| `docker/prometheus/alerts.smoke.yml` | `ObservabilitySmokeTest` for AM routing checks (optional on prod) |
| `docker/alertmanager/alertmanager.yml.example` | Route/receivers template → copy to `alertmanager.yml` |

## Staging / production validation

Run on the **WAVE-2 VPS** after `migrate_and_up.sh staging` (or prod). No secrets in the repository — configure on the host only.

### 1. Bootstrap monitoring (one-time)

```bash
cd /opt/crm-chat-center   # STAGING_PATH
cp deploy/docker-compose.monitoring.prod.yaml.example deploy/prod/docker-compose.monitoring.override.yaml
cp docker/alertmanager/alertmanager.yml.example docker/alertmanager/alertmanager.yml
# Edit alertmanager.yml: uncomment webhook_configs or email_configs for staging-smoke / oncall
```

Ensure in `deploy/.env.staging`: `METRICS_ENABLED=true`, `SENTRY_DSN` (backend), `GRAFANA_ADMIN_PASSWORD`, `GRAFANA_ROOT_URL=https://grafana.<DOMAIN>`.

Frontend Sentry: set `VITE_SENTRY_DSN` in env and **rebuild** `crm-frontend` (baked at build time). See [`DEPLOY.md`](DEPLOY.md) § Sentry DSN rotation.

Bring up monitoring:

```bash
docker compose -f docker/docker-compose.staging.yaml \
  -f docker/docker-compose.monitoring.yaml \
  -f docker/docker-compose.monitoring.staging.yaml \
  -f deploy/prod/docker-compose.monitoring.override.yaml \
  --env-file deploy/.env.staging --profile with-proxy up -d
```

### 2. Prometheus targets UP

| Target | Expected |
|--------|----------|
| `crm-api` → `api:8000` | **UP** (`METRICS_ENABLED=true`) |
| `prometheus` | **UP** |
| Alertmanager (Status → Configuration) | **UP** at `alertmanager:9093` |

```bash
curl -s "http://127.0.0.1:9090/api/v1/targets" | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

Expose `:9090` only via SSH tunnel or internal firewall — do not publish Prometheus to the public internet without auth.

### 3. Firing alert smoke test

Rule `ObservabilitySmokeTest` in `docker/prometheus/alerts.smoke.yml` fires after ~1m.

1. Open Prometheus → **Alerts** — `ObservabilitySmokeTest` = **Firing**.
2. Open Alertmanager → **Alerts** — same alert grouped; check **Silences** empty.
3. If `staging-smoke` receiver has a webhook, confirm delivery; otherwise AM UI is enough for ✅.

On **production**, remove `alerts.smoke.yml` from the Prometheus volume list in `deploy/prod/docker-compose.monitoring.override.yaml` if you do not want a permanent test alert.

### 4. Sentry (staging)

| Check | Command / action |
|-------|------------------|
| DSN set | `docker exec crm-staging-api printenv SENTRY_DSN` — non-empty (value not logged in docs) |
| Environment | `SENTRY_ENVIRONMENT=staging` |
| Test event | Trigger a handled 500 or temporary `capture_exception` in maintenance; confirm event in Sentry UI with `environment:staging` |
| PII scrub | Event extras must not contain `password`, `inbound_secret`, raw tokens (`app/shared/sentry.py`) |

Without a project DSN, Sentry stays disabled — set DSN in `deploy/.env.staging` and restart `api` + rebuild `frontend` for `VITE_SENTRY_DSN`.

### 5. Grafana — CRM Overview on staging

Dashboard JSON: `docker/grafana/dashboards/crm-overview.json` (provisioned when using `docker-compose.monitoring.yaml`).

| Step | Action |
|------|--------|
| 1 | Open Grafana (`GRAFANA_ROOT_URL` or SSH tunnel to `:3000`) |
| 2 | Login with `GRAFANA_ADMIN_*` from env (not `admin/admin`) |
| 3 | **Dashboards** → browse → **CRM Overview** |
| 4 | Time range **Last 1 hour**; generate API traffic (`staging_smoke.sh`) |
| 5 | Panels: HTTP rate, `bot_*`, `ws_*`, `redis_stream_pending` show data |
| 6 | Optional leads panels: add `rate(crm_leads_created_total[5m])`, `rate(crm_leads_closed_total[5m])` |

Screenshot checklist for QA: [`docs/teams/07_qa.md`](teams/07_qa.md) §10 (OBS WAVE-2).

### 6. Backup restore drill (staging)

Procedure: [`scripts/restore_postgres.md`](../scripts/restore_postgres.md). On staging use `POSTGRES_CONTAINER=crm-staging-postgres`.

**Monthly drill:** restore latest `backups/postgres/crm_*.dump` to an **isolated** DB/volume (or dev host), run `alembic upgrade head`, `staging_smoke.sh`. Record outcome in QA §10 — do not overwrite production/staging live DB during business hours.

**Last drill (dev stand-in, 2026-05-18):** ✅ backup → drop/create → `pg_restore` → `users=1` → `alembic upgrade head` (`0026`). Details: [`docs/teams/07_qa.md`](teams/07_qa.md) §10 OBS WAVE-2.

### 7. Backup cron (staging VPS)

```cron
0 3 * * * cd /opt/crm-chat-center && \
  POSTGRES_CONTAINER=crm-staging-postgres \
  MINIO_CONTAINER=crm-staging-minio \
  MINIO_ENDPOINT=http://crm-staging-minio:9000 \
  ./scripts/backup_postgres.sh && \
  POSTGRES_CONTAINER=crm-staging-postgres \
  MINIO_CONTAINER=crm-staging-minio \
  MINIO_ENDPOINT=http://crm-staging-minio:9000 \
  ./scripts/backup_minio.sh >>/var/log/crm-backup.log 2>&1
```

## Verify

```bash
# Compose merge valid
docker compose -f docker/docker-compose.dev.yaml -f docker/docker-compose.monitoring.yaml config

# Targets UP (crm-api should be 1/1)
curl -s http://localhost:9090/api/v1/targets | head -c 500

# Metrics from host API (if METRICS_ENABLED=true)
curl -s http://localhost:8000/metrics | head

# Grafana health
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health
```

## Backups

Scripts (no cron container in compose — schedule on the host):

| Script | Purpose |
|--------|---------|
| `scripts/backup_postgres.sh` | `pg_dump` via `crm-postgres` |
| `scripts/backup_postgres.ps1` | Same for Windows |
| `scripts/backup_minio.sh` | `mc mirror` buckets to `MINIO_BACKUP_DIR` |
| `scripts/restore_postgres.md` | Restore procedure |

Example cron (Linux, daily 03:00):

```cron
0 3 * * * cd /path/to/repo && ./scripts/backup_postgres.sh && ./scripts/backup_minio.sh
```

**Staging VPS** (`docker-compose.staging.yaml` container names):

```cron
0 3 * * * cd /opt/crm-chat-center && \
  POSTGRES_CONTAINER=crm-staging-postgres \
  MINIO_CONTAINER=crm-staging-minio \
  MINIO_ENDPOINT=http://crm-staging-minio:9000 \
  ./scripts/backup_postgres.sh && \
  POSTGRES_CONTAINER=crm-staging-postgres \
  MINIO_CONTAINER=crm-staging-minio \
  MINIO_ENDPOINT=http://crm-staging-minio:9000 \
  ./scripts/backup_minio.sh >>/var/log/crm-backup.log 2>&1
```

Environment variables: see `.env.example` (`BACKUP_DIR`, `MINIO_BACKUP_DIR`, `BACKUP_RETENTION_DAYS`, …).

## Sentry

Errors are independent of Prometheus. Backend and frontend use separate DSNs (recommended).

### Backend

Set in repo root `.env` (see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `SENTRY_DSN` | empty | Enable SDK when set |
| `SENTRY_ENVIRONMENT` | `dev` | `environment` tag |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Performance sampling (0–1) |

Implementation: `app/shared/sentry.py` (`before_send` scrubs tokens/secrets in extras and request bodies).

### Frontend

Set in `frontend/.env` (see `frontend/.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_SENTRY_DSN` | empty | Enable `@sentry/vue` when set |
| `VITE_SENTRY_ENVIRONMENT` | `dev` | `environment` tag (falls back to Vite `MODE`) |

Initialization: `frontend/src/main.ts` → `initSentry(app, router)` before mount. Includes Vue Router tracing and the Vue `errorHandler` via `@sentry/vue` (`sendDefaultPii: false`). `beforeSend` redacts query `token` / auth params and strips `user.email` from events.

Vitest mocks `@sentry/vue` globally (`tests/setup/sentry-mock.ts`); unit tests cover scrubbing and no-op boot without DSN.

## Stop

```bash
docker compose -f docker/docker-compose.dev.yaml -f docker/docker-compose.monitoring.yaml down
```

Volumes `crm-prometheus-data` and `crm-grafana-data` retain time-series and Grafana state.
