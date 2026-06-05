# Docker — локальная dev-инфраструктура

`docker-compose.dev.yaml` поднимает **только зависимости** CRM Chat Center. Приложение (FastAPI, worker, frontend) запускается отдельно из IDE или терминала — см. корневой `README.md`.

## Сервисы

| Контейнер | Образ | Назначение | Порты (host) | Учётные данные (dev) |
|-----------|-------|------------|--------------|----------------------|
| `crm-postgres` | `postgres:16-alpine` | Основная БД | `5432` | user `crm`, password `crm`, DB `crm` |
| `crm-redis` | `redis:7-alpine` | Кэш, Pub/Sub, refresh-токены, ARQ | `6379` | без пароля |
| `crm-minio` | `minio/minio:latest` | S3-совместимое хранилище файлов и бэкапов | `9000` (API), `9001` (console) | `minio` / `miniominio` |
| `crm-minio-init` | `minio/mc:latest` | Однократно создаёт бакеты `crm-files`, `crm-backups` | — | — |
| `crm-adminer` | `adminer:latest` | Web UI для PostgreSQL | `8080` | сервер: `crm-postgres`, user `crm` |
| `crm-mailhog` | `mailhog/mailhog` | Перехват SMTP (reset password) | `1025` (SMTP), `8025` (web) | без auth |

> **Прод:** не публиковать порты PostgreSQL и Redis на хост и не использовать dev-пароли.

## Тома

| Volume | Сервис | Содержимое |
|--------|--------|------------|
| `crm-pgdata` | postgres | данные PostgreSQL |
| `crm-miniodata` | minio | объекты S3 |

## Команды

```bash
# из корня репозитория
docker compose -f docker/docker-compose.dev.yaml up -d
docker compose -f docker/docker-compose.dev.yaml ps
docker compose -f docker/docker-compose.dev.yaml logs -f crm-postgres

# скрипты-обёртки (копируют .env.example → .env при необходимости)
./scripts/dev.sh          # macOS / Linux
.\scripts\dev.ps1         # Windows PowerShell
```

### Проверка здоровья

```bash
docker exec crm-postgres pg_isready -U crm
docker exec crm-redis redis-cli ping
curl -f http://localhost:9000/minio/health/live

# бакеты MinIO (после успешного crm-minio-init)
docker run --rm --network crm-net minio/mc:latest sh -c \
  "mc alias set myminio http://crm-minio:9000 minio miniominio && mc ls myminio/"
```

### Сброс данных

Удаляет контейнеры **и** именованные тома (все данные БД и MinIO будут потеряны):

```bash
docker compose -f docker/docker-compose.dev.yaml down -v
```

После сброса снова выполните `up -d` — `crm-minio-init` пересоздаст бакеты.

## Сеть

Все сервисы в сети `crm-net` (имя фиксировано для отладки и `docker run --network crm-net`).

## Staging / production stack

Полный стек (API, worker, frontend, Postgres, Redis, MinIO, Traefik) — см. [`docs/DEPLOY.md`](../docs/DEPLOY.md).

```bash
cp deploy/env.staging.example deploy/.env.staging
docker compose -f docker/docker-compose.staging.yaml --env-file deploy/.env.staging --profile with-proxy config
```

Локальный smoke без Traefik:

```bash
docker compose -f docker/docker-compose.staging.yaml -f docker/docker-compose.local.yaml \
  --env-file deploy/.env.staging up -d --build
```

## Мониторинг (Prometheus + Grafana)

```bash
docker compose -f docker/docker-compose.dev.yaml -f docker/docker-compose.monitoring.yaml up -d
```

Подробности, URL, алерты и бэкапы — [`docs/OBSERVABILITY.md`](../docs/OBSERVABILITY.md).
