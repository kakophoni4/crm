# Deploy — Docker images & staging/prod stack (Phase 7)

## URL scheme

| Surface | Staging / prod (Traefik) | Local smoke (`docker-compose.local.yaml`) |
|---------|--------------------------|-------------------------------------------|
| Frontend | `https://app.${DOMAIN}` | `http://localhost:8080` |
| API | `https://api.${DOMAIN}` | `http://localhost:8000` |
| OpenAPI | `https://api.${DOMAIN}/api/docs` | `http://localhost:8000/api/docs` |
| WebSocket | `wss://api.${DOMAIN}/ws` | `ws://localhost:8000/ws` |
| Metrics | `https://api.${DOMAIN}/metrics` (if enabled) | `http://localhost:8000/metrics` |
| Bot ingest | `POST https://api.${DOMAIN}/api/v1/bot-events` | tunnel or `http://localhost:8000/api/v1/bot-events` |

Replace `${DOMAIN}` with your base domain (e.g. `staging.example.com` → `api.staging.example.com`, `app.staging.example.com`).

## Services (staging / prod compose)

| Service | Image / build | Host ports | Notes |
|---------|---------------|------------|--------|
| `traefik` | `traefik:v3.3` | 80, 443 | Profile `with-proxy` only |
| `api` | `crm-api` (`docker/Dockerfile.backend`) | — (`8000` via `docker-compose.local.yaml`) | Migrations on start: `alembic upgrade head && uvicorn …` |
| `worker` | `crm-worker` (`docker/Dockerfile.worker`) | — | `WORKERS_IN_API=false` |
| `frontend` | `crm-frontend` (`docker/Dockerfile.frontend`) | — (`8080→80` via local overlay) | nginx static |
| `postgres` | `postgres:16-alpine` | **not published** | Volume `crm-staging-pgdata` / `crm-prod-pgdata` |
| `redis` | `redis:7-alpine` | **not published** | Internal only |
| `minio` | `minio/minio` | **not published** | Volume `crm-staging-miniodata` / `crm-prod-miniodata` |
| `minio-init` | `minio/mc` | — | Creates S3 buckets once |

Optional (merge monitoring files): `prometheus`, `grafana`, dev-only `api` scrape helper in `docker-compose.monitoring.yaml` — use staging overlay `docker-compose.monitoring.staging.yaml`.

**Not included:** `adminer`, `mailhog` (dev compose only).

## Build images locally

From the repository root:

```bash
make docker-build
```

Or with public URLs baked into the frontend:

```bash
docker build -f docker/Dockerfile.backend -t crm-api:local .
docker build -f docker/Dockerfile.worker -t crm-worker:local .
docker build -f docker/Dockerfile.frontend -t crm-frontend:local \
  --build-arg VITE_API_BASE_URL=https://api.staging.example.com/api/v1 \
  --build-arg VITE_WS_URL=wss://api.staging.example.com/ws \
  .
```

## One command — staging on a VPS

1. **DNS:** `A` records for `api.${DOMAIN}` and `app.${DOMAIN}` → VPS public IP (or wildcard `*.${DOMAIN}`).
2. **Firewall:** allow TCP `80`, `443`; do **not** expose `5432` / `6379`.
3. Copy and edit env:

```bash
cp deploy/env.staging.example deploy/.env.staging
# set DOMAIN, ACME_EMAIL, JWT_SECRET, PGCRYPTO_KEY, POSTGRES_PASSWORD, S3_SECRET_KEY, CORS, VITE_*
```

4. Deploy:

```bash
chmod +x scripts/deploy/migrate_and_up.sh
./scripts/deploy/migrate_and_up.sh staging
```

Equivalent manual flow:

```bash
docker compose -f docker/docker-compose.staging.yaml \
  --env-file deploy/.env.staging --profile with-proxy up -d --build
```

**Production** (Let's Encrypt production CA, `restart: always`, memory limits):

```bash
cp deploy/env.prod.example deploy/.env.prod
./scripts/deploy/migrate_and_up.sh prod
```

```bash
docker compose -f docker/docker-compose.staging.yaml -f docker/docker-compose.prod.yaml \
  --env-file deploy/.env.prod --profile with-proxy up -d --build
```

Windows:

```powershell
.\scripts\deploy\migrate_and_up.ps1 staging
```

### TLS notes

- **Staging VPS:** `ACME_CA_SERVER=https://acme-staging-v02.api.letsencrypt.org/directory` (fake certs, safe for tests).
- **Production:** omit `ACME_CA_SERVER` in `deploy/.env.prod` (prod override uses production Let's Encrypt).
- **Local smoke:** merge `docker-compose.local.yaml` (no Traefik); HTTP on `localhost:8000` / `8080`.

### Monitoring overlay

```bash
docker compose -f docker/docker-compose.staging.yaml \
  -f docker/docker-compose.monitoring.yaml \
  -f docker/docker-compose.monitoring.staging.yaml \
  --env-file deploy/.env.staging --profile with-proxy up -d
```

Prometheus scrapes `api:8000/metrics` on `crm-staging-net`.

## Bot events on dev (no public VPS)

External bots must reach `POST /api/v1/bot-events` over HTTPS.

| Method | Use when |
|--------|----------|
| **cloudflared** | Quick tunnel to local API: `cloudflared tunnel --url http://localhost:8000` → use printed HTTPS URL + `/api/v1/bot-events` |
| **ngrok** | `ngrok http 8000` → `https://<id>.ngrok.io/api/v1/bot-events` |
| **Staging VPS** | Permanent `https://api.${DOMAIN}/api/v1/bot-events` |

## Validate compose (no real Let's Encrypt)

```bash
cp deploy/env.staging.example deploy/.env.staging
# replace CHANGE_ME_* placeholders with dummy 32+ char secrets

docker compose -f docker/docker-compose.staging.yaml --env-file deploy/.env.staging config
docker compose -f docker/docker-compose.staging.yaml -f docker/docker-compose.local.yaml \
  --env-file deploy/.env.staging config
```

Local smoke run:

```bash
# deploy/.env.staging: unset COMPOSE_PROFILES (no Traefik), CORS_ALLOWED_ORIGINS=http://localhost:8080
# VITE_* pointing to http://localhost:8000
docker compose -f docker/docker-compose.staging.yaml -f docker/docker-compose.local.yaml \
  --env-file deploy/.env.staging up -d --build
curl -sf http://localhost:8000/healthz
curl -sf -o /dev/null -w "%{http_code}" http://localhost:8080/
```

## Up / down

```bash
# Staging + Traefik
docker compose -f docker/docker-compose.staging.yaml \
  --env-file deploy/.env.staging --profile with-proxy up -d

docker compose -f docker/docker-compose.staging.yaml \
  --env-file deploy/.env.staging --profile with-proxy down

# Production
docker compose -f docker/docker-compose.staging.yaml -f docker/docker-compose.prod.yaml \
  --env-file deploy/.env.prod --profile with-proxy down

# Remove data volumes (destructive)
docker compose -f docker/docker-compose.staging.yaml --env-file deploy/.env.staging down -v
```

## Required environment

See `deploy/env.staging.example` and `deploy/env.prod.example`. Minimum:

| Variable | Notes |
|----------|--------|
| `DOMAIN` | Base domain for Traefik `Host()` rules |
| `ACME_EMAIL` | Let's Encrypt registration (with `with-proxy` profile) |
| `JWT_SECRET` | Min 32 characters |
| `PGCRYPTO_KEY` | Encryption key for sensitive DB fields |
| `POSTGRES_PASSWORD` | DB password |
| `DATABASE_URL` | `postgresql+asyncpg://…@postgres:5432/crm` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `S3_SECRET_KEY` | MinIO root password in stack |
| `CORS_ALLOWED_ORIGINS` | e.g. `https://app.${DOMAIN}` |
| `VITE_API_BASE_URL`, `VITE_WS_URL` | Frontend build args |

Recommended: `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `METRICS_ENABLED=true`, `OWNERSHIP_V2=true`, `WORKERS_IN_API=false`.

Staging only: `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` (clear after first login).

### Sentry DSN rotation

Backend and frontend use **separate** DSNs (recommended: two Sentry projects or one project with two DSN keys).

| Surface | Variable | Where applied |
|---------|----------|---------------|
| API / worker | `SENTRY_DSN` | `deploy/.env.staging` / `deploy/.env.prod` — restart `api` + `worker` |
| SPA | `VITE_SENTRY_DSN` | Same env files as **build args** — requires **rebuild** `crm-frontend` image |

**Rotate backend DSN (no frontend rebuild):**

1. In [Sentry](https://sentry.io) → Project → **Settings → Client Keys (DSN)** → create a new key or revoke the compromised key.
2. Update `SENTRY_DSN` in `deploy/.env.staging` (or `.env.prod`) on the VPS — do not commit the value.
3. Restart consumers:  
   `docker compose -f docker/docker-compose.staging.yaml --env-file deploy/.env.staging up -d api worker`
4. Confirm: trigger a test error; old DSN must stop receiving events after revoke.

**Rotate frontend DSN:**

1. Create/rotate key in the Sentry **frontend** project.
2. Set `VITE_SENTRY_DSN` (and `VITE_SENTRY_ENVIRONMENT` if needed) in env.
3. Rebuild and redeploy frontend only:  
   `docker compose … build frontend && docker compose … up -d frontend`  
   (or GHCR pipeline with updated `STAGING_VITE_SENTRY_DSN` repository variable).
4. Hard-refresh browser / clear service worker cache if events still hit the old project.

**Rotate both at once:** update all four vars (`SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `VITE_SENTRY_DSN`, `VITE_SENTRY_ENVIRONMENT`), restart `api`/`worker`, rebuild `frontend`.

**Check on staging (WAVE-2 VPS):**

```bash
docker exec crm-staging-api printenv SENTRY_ENVIRONMENT   # expect: staging
docker exec crm-staging-api sh -c 'test -n "$SENTRY_DSN" && echo SENTRY_DSN=set || echo SENTRY_DSN=empty'
```

Details: [`OBSERVABILITY.md`](OBSERVABILITY.md) § Staging / production validation.

## Image tags

| Image | Dockerfile | Port |
|-------|------------|------|
| `crm-api` | `docker/Dockerfile.backend` | 8000 |
| `crm-worker` | `docker/Dockerfile.worker` | — |
| `crm-frontend` | `docker/Dockerfile.frontend` | 80 |

Registry (GHCR, after merge to `main` or tag `v*`):

| Image | Tags |
|-------|------|
| `ghcr.io/<owner>/crm-api` | `<sha>`, `latest`, `vX.Y.Z` (on git tag) |
| `ghcr.io/<owner>/crm-worker` | same |
| `ghcr.io/<owner>/crm-frontend` | same |

`<owner>` — lowercase GitHub org or user. Package visibility: set **public** or grant the VPS `docker login ghcr.io` with a PAT (`read:packages`).

Dev dependencies only (`adminer`, `mailhog`, host-published Postgres) — [`docker/README.md`](../docker/README.md) and `docker-compose.dev.yaml`.

## CI/CD (GitHub Actions)

| Workflow | File | Trigger |
|----------|------|---------|
| **CI** | `.github/workflows/ci.yml` | PR + push `main` — tests, lint; **Docker build verify on PR only** (no push) |
| **Docker Build** | `.github/workflows/docker-build.yml` | Push `main`, tags `v*`, manual — build & push to GHCR (`GITHUB_TOKEN`) |
| **Deploy Staging** | `.github/workflows/deploy-staging.yml` | After successful Docker Build on `main`, or `workflow_dispatch` |
| **Deploy Production** | `.github/workflows/deploy-prod.yml` | `workflow_dispatch` + **environment `production`** (manual approval) |

### GitHub secrets (repository)

**Do not commit** private keys or `.env` files. Add under **Settings → Secrets and variables → Actions**:

| Secret | Used by | Description |
|--------|---------|-------------|
| `STAGING_SSH_HOST` | Deploy Staging | VPS hostname or IP |
| `STAGING_SSH_USER` | Deploy Staging | SSH user (e.g. `deploy`) |
| `STAGING_SSH_KEY` | Deploy Staging | Private key (PEM), full file contents |
| `STAGING_PATH` | Deploy Staging | Absolute path to repo clone on VPS (e.g. `/opt/crm-chat-center`) |
| `STAGING_SMOKE_API_URL` | Deploy Staging (optional) | Override smoke URL, e.g. `https://api.staging.example.com` |
| `STAGING_SMOKE_APP_URL` | Deploy Staging (optional) | Override smoke URL, e.g. `https://app.staging.example.com` |
| `PROD_SSH_HOST` | Deploy Production | Production VPS host |
| `PROD_SSH_USER` | Deploy Production | SSH user |
| `PROD_SSH_KEY` | Deploy Production | Private key |
| `PROD_PATH` | Deploy Production | Repo path on prod VPS |
| `PROD_SMOKE_API_URL` | Deploy Production (optional) | Smoke API base URL |
| `PROD_SMOKE_APP_URL` | Deploy Production (optional) | Smoke app URL |

`GITHUB_TOKEN` is provided by Actions for GHCR push (workflow sets `packages: write`).

### GitHub variables (optional)

| Variable | Used by | Description |
|----------|---------|-------------|
| `STAGING_VITE_API_BASE_URL` | Docker Build | Frontend build arg |
| `STAGING_VITE_WS_URL` | Docker Build | Frontend build arg |
| `STAGING_VITE_SENTRY_DSN` | Docker Build | Optional |
| `STAGING_VITE_SENTRY_ENVIRONMENT` | Docker Build | Default `staging` |

### Staging VPS setup for CD

1. Clone repo to `STAGING_PATH`.
2. `cp deploy/env.staging.example deploy/.env.staging` and configure secrets + `DOMAIN`.
3. `cp deploy/staging/docker-compose.override.yaml.example deploy/staging/docker-compose.override.yaml` — set `GHCR_OWNER` / `CRM_IMAGE_TAG` in `deploy/.env.staging` or in the override file.
4. `docker login ghcr.io` on the VPS (PAT with `read:packages` if images are private).
5. First boot: `./scripts/deploy/migrate_and_up.sh staging` (or manual `compose up`).
6. Later deploys: automatic via **Deploy Staging** (`pull` + `up -d`) or manual on host:

```bash
cd "$STAGING_PATH"
docker compose -f docker/docker-compose.staging.yaml \
  -f deploy/staging/docker-compose.override.yaml \
  --env-file deploy/.env.staging --profile with-proxy pull api worker frontend
docker compose -f docker/docker-compose.staging.yaml \
  -f deploy/staging/docker-compose.override.yaml \
  --env-file deploy/.env.staging --profile with-proxy up -d
./scripts/smoke/staging_smoke.sh
```

### Post-deploy smoke

**Primary (фаза 7):** `scripts/smoke/staging_smoke.sh` (или `staging_smoke.ps1` на Windows).

Проверки: `/healthz`, `/readyz`, `/metrics` (если `METRICS_ENABLED`), login, `GET /api/v1/chats`, frontend `/` → exit **0/1** для CI.

| Env | Default | Описание |
|-----|---------|----------|
| `BASE_URL` | `https://api.staging.example` | API без `/api/v1` |
| `FRONTEND_URL` | `https://app.staging.example` | SPA |
| `SMOKE_EMAIL` / `SMOKE_PASSWORD` | `SEED_ADMIN_*` или staging seed | Учётка для login |
| `METRICS_ENABLED` | `true` | `false` — пропуск `/metrics` |

В GitHub Actions можно задать `STAGING_SMOKE_API_URL` / `STAGING_SMOKE_APP_URL` — workflow экспортирует их как `BASE_URL` / `FRONTEND_URL`.

Legacy (минимальный): `scripts/deploy/post_deploy_smoke.sh` — только healthz + frontend.

UAT заказчика: [`scripts/smoke/uat_checklist.md`](../scripts/smoke/uat_checklist.md). Документация оператора: [`docs/user/README.md`](user/README.md).

## Первый реальный админ в prod

> Выполняйте в окно обслуживания. Полный restore БД на staging **не** входит в smoke — только dump/cron по [`OBSERVABILITY.md`](OBSERVABILITY.md).

### 1. Смена пароля seed-админа

После первого `alembic upgrade head` на prod создаётся пользователь из миграции `0004_seed_admin` **только если** заданы `SEED_ADMIN_EMAIL` и `SEED_ADMIN_PASSWORD` при **первом** запуске. На prod в `deploy/.env.prod` держите seed **пустым** после bootstrap.

1. Временно задайте сильный `SEED_ADMIN_PASSWORD` только на первом деплое **или** создайте админа через API (ниже).
2. Войдите в UI: `POST /api/v1/auth/login` → смените пароль: `POST /api/v1/auth/me/password`.
3. В `deploy/.env.prod` **очистите** `SEED_ADMIN_EMAIL` и `SEED_ADMIN_PASSWORD`; перезапустите `api` (без повторного destructive seed).

```bash
API=https://api.${DOMAIN}/api/v1
curl -sS -X POST "$API/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"admin@yourcompany.com","password":"OLD_SEED_PASSWORD"}' \
  | tee /tmp/login.json
TOKEN=$(jq -r .access_token /tmp/login.json)
curl -sS -X POST "$API/auth/me/password" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"current_password":"OLD_SEED_PASSWORD","new_password":"NEW_STRONG_PASSWORD_HERE"}'
```

### 2. Организация: отдел → группа → пользователи

Под admin-токеном (`Bearer`):

```bash
API=https://api.${DOMAIN}/api/v1
TOKEN="<access_token>"

# Отдел
curl -sS -X POST "$API/departments" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Продажи"}'
# → запомните department id (например 1)

# Группа
curl -sS -X POST "$API/groups" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Поток A","department_id":1}'

# Senior
curl -sS -X POST "$API/users" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"senior@yourcompany.com","full_name":"Старший","password":"Temp!ChangeMe1","role":"senior","group_id":1}'

# Оператор
curl -sS -X POST "$API/users" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"operator@yourcompany.com","full_name":"Оператор","password":"Temp!ChangeMe2","role":"user","group_id":1}'
```

Далее senior создаёт пользователей в своём отделе через API/UI в рамках RBAC.

### 3. Ротация `JWT_SECRET`

1. Сгенерируйте новый секрет: `openssl rand -hex 32`.
2. Обновите `JWT_SECRET` в `deploy/.env.prod`.
3. `docker compose … up -d api worker` — **все** активные access/refresh станут недействительны; пользователи перелогиниваются.
4. Запланируйте окно; не ротируйте без предупреждения операторов.

### 4. Ротация `PGCRYPTO_KEY`

Ключ шифрует чувствительные поля в БД. Смена **не** тривиальна: требуется re-encrypt данных (скрипт миграции ключей — вне v1). На prod:

- задайте ключ **один раз** до появления production-данных;
- храните backup ключа в secret manager;
- при компрометации — эскалация к Backend + DBA (не только смена env).

### 5. Проверка после bootstrap

```bash
BASE_URL=https://api.${DOMAIN} FRONTEND_URL=https://app.${DOMAIN} \
  SMOKE_EMAIL=admin@yourcompany.com SMOKE_PASSWORD='NEW_STRONG_PASSWORD_HERE' \
  ./scripts/smoke/staging_smoke.sh
```

### Rollback

Pin app images to a known-good tag (previous commit SHA or release tag), then pull and restart **without** `--build`:

```bash
# On VPS — example: rollback to commit abc1234 or release v1.2.0
export CRM_IMAGE_TAG=abc1234   # or v1.2.0
# In deploy/.env.staging set CRM_*_IMAGE=ghcr.io/<owner>/crm-*:${CRM_IMAGE_TAG}
# or only CRM_IMAGE_TAG if using deploy/staging/docker-compose.override.yaml

docker compose -f docker/docker-compose.staging.yaml \
  -f deploy/staging/docker-compose.override.yaml \
  --env-file deploy/.env.staging --profile with-proxy pull api worker frontend
docker compose -f docker/docker-compose.staging.yaml \
  -f deploy/staging/docker-compose.override.yaml \
  --env-file deploy/.env.staging --profile with-proxy up -d
./scripts/smoke/staging_smoke.sh
```

Production: same pattern with `docker-compose.prod.yaml`, `deploy/.env.prod`, and workflow input `version` on **Deploy Production**.

### Production environment protection

In **Settings → Environments → production**: enable **Required reviewers** before **Deploy Production** runs. Workflow is a skeleton: trigger manually, pass image tag (`version` input).

## Weak points / ops notes

1. **First API start waits on Postgres** — `api` runs `alembic upgrade head` only after `postgres` is healthy; slow disks or wrong `DATABASE_URL` delay or fail boot (check `docker compose logs api`).
2. **Double migration** — `migrate_and_up.sh` runs Alembic before `up`, and the API container runs it again on start (idempotent, but adds startup time).
3. **Worker image build** — standalone `Dockerfile.worker`; for deploy scripts still keep `compose build api worker frontend` order for consistent cache/use of shared dependencies.
4. **Traefik ACME** — ports 80/443 must reach the VPS; stale `acme.json` from another domain blocks cert issuance.
5. **Let's Encrypt staging certs** — browsers show untrusted warnings; use production CA only on prod.
6. **GHCR private images** — VPS must `docker login ghcr.io`; failed login leaves old local images running after `up -d`.
7. **Frontend URL bake-in** — `crm-frontend` embeds `VITE_*` at build time; changing API domain requires rebuild with new vars, not only compose env.
