# Docker — Локальная Dev-Инфраструктура

`docker-compose.dev.yaml` поднимает зависимости CRM Chat Center и вспомогательные сервисы для разработки. Backend API и frontend запускаются отдельно, worker в dev compose доступен как контейнер `crm-worker`.

## Сервисы

| Контейнер | Образ | Назначение | Порты host | Dev-доступ |
|---|---|---|---|---|
| `crm-postgres` | `postgres:16-alpine` | PostgreSQL | `5433 -> 5432` | user/password/db: `crm` / `crm` / `crm` |
| `crm-redis` | `redis:7-alpine` | Redis cache, Pub/Sub, queues, WS tickets | `6379` | без пароля |
| `crm-minio` | `minio/minio` | S3-compatible storage | `9000`, `9001` | `minio` / `miniominio` |
| `crm-minio-init` | `minio/mc` | Создаёт buckets `crm-files`, `crm-backups` | нет | одноразовый init |
| `crm-adminer` | `adminer` | Web UI для PostgreSQL | `8080` | server: `crm-postgres` |
| `crm-mailhog` | `mailhog/mailhog` | SMTP catcher | `1025`, `8025` | без auth |
| `crm-asterisk` | local Dockerfile | Dev PBX for SIP/WebRTC | `5060`, `8088`, `10000-10100/udp` | static dev config |
| `crm-worker` | `python:3.12-slim` | Background jobs | нет | использует внутренние `crm-postgres`, `crm-redis` |

Production не должен публиковать PostgreSQL/Redis на host и не должен использовать dev-пароли.

## Запуск

```bash
docker compose -f docker/docker-compose.dev.yaml up -d
docker compose -f docker/docker-compose.dev.yaml ps
```

Windows wrapper:

```powershell
.\scripts\dev.ps1
```

macOS/Linux wrapper:

```bash
./scripts/dev.sh
```

После первого запуска или `down -v` примените миграции из корня репозитория:

```bash
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_dev_data.py
```

Если worker успел стартовать до миграций и пишет ошибки о missing relation, после `alembic upgrade head` перезапустите его:

```bash
docker compose -f docker/docker-compose.dev.yaml restart crm-worker
```

## Проверка

```bash
docker exec crm-postgres pg_isready -U crm -d crm
docker exec crm-redis redis-cli ping
curl -f http://localhost:9000/minio/health/live
docker compose -f docker/docker-compose.dev.yaml logs -f crm-worker
```

MinIO buckets:

```bash
docker run --rm --network crm-net minio/mc:latest sh -c \
  "mc alias set myminio http://crm-minio:9000 minio miniominio && mc ls myminio/"
```

## Volumes

| Volume | Сервис | Содержимое |
|---|---|---|
| `crm-pgdata` | PostgreSQL | БД |
| `crm-miniodata` | MinIO | S3 objects |

Сброс всех dev-данных:

```bash
docker compose -f docker/docker-compose.dev.yaml down -v
```

После сброса заново выполните `up -d`, `alembic upgrade head` и seed.

## Сеть

Все сервисы dev compose подключены к сети `crm-net`. Это имя фиксировано, чтобы можно было запускать одноразовые диагностические контейнеры через `docker run --network crm-net`.

## Monitoring

```bash
docker compose -f docker/docker-compose.dev.yaml -f docker/docker-compose.monitoring.yaml up -d
```

Подробнее: [`docs/OBSERVABILITY.md`](../docs/OBSERVABILITY.md).

## Staging / Production

Полный стек см. в [`docs/DEPLOY.md`](../docs/DEPLOY.md) и compose-файлах:

- `docker/docker-compose.staging.yaml`
- `docker/docker-compose.prod.yaml`
- `deploy/prod/docker-compose.override.yaml.example`

Локальный smoke без Traefik:

```bash
docker compose -f docker/docker-compose.staging.yaml -f docker/docker-compose.local.yaml \
  --env-file deploy/.env.staging up -d --build
```

## Telephony Dev PBX

`crm-asterisk` включён в `docker-compose.dev.yaml` для SIP/WebRTC разработки.

- SIP over WebSocket: `ws://localhost:8088/ws`
- SIP UDP/TCP: `localhost:5060`
- RTP media: `10000-10100/udp`
- Static smoke-test extension: `7001` / `dev-webrtc-7001`

Операторы должны использовать внутренние WebRTC extensions, выданные CRM API. Checked-in `extensions.conf` возвращает `501` для outbound calls, пока реальный Bitcall trunk не настроен на стороне PBX.
