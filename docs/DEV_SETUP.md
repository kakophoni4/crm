# Dev Setup

Краткая инструкция для локальной разработки. Production/staging живут отдельно и описаны в [`DEPLOY.md`](DEPLOY.md).

## Зависимости

- Docker Desktop или Docker Engine + Compose v2
- Python 3.12+
- Node.js 20+ / npm 10+

## Инфраструктура

```bash
docker compose -f docker/docker-compose.dev.yaml up -d
```

Windows wrapper:

```powershell
.\scripts\dev.ps1
```

Сервисы:

- PostgreSQL: `localhost:5433`, user/password/db: `crm` / `crm` / `crm`
- Redis: `localhost:6379`
- MinIO: http://localhost:9001 (`minio` / `miniominio`)
- Adminer: http://localhost:8080
- MailHog: http://localhost:8025

## Backend

```bash
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_dev_data.py
```

Windows:

```powershell
python scripts\run_uvicorn_win.py
```

macOS / Linux:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API:

- http://localhost:8000/api/docs
- http://localhost:8000/api/openapi.json
- http://localhost:8000/healthz
- http://localhost:8000/readyz

Важно: `healthz`/`readyz` проверяют доступность БД и Redis. После сброса volume схема может быть пустой, поэтому перед работой с API всегда выполняйте `alembic upgrade head`.

## Worker

В dev compose есть контейнер `crm-worker`. Если вы запускаете worker вручную:

```bash
python -m app.workers.run
```

`WORKERS_IN_API=true` используйте только для one-process dev, когда worker должен стартовать внутри lifespan API.

## Frontend

```bash
cd frontend
cp -n .env.example .env
npm ci
npm run dev
```

Windows:

```powershell
cd frontend
copy .env.example .env
npm ci
npm run dev
```

Frontend: http://localhost:5173

## Проверки

Backend:

```bash
ruff check .
mypy app
pytest -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run typecheck
npm run test
```

Полный gate:

```bash
make gate-full
```

Windows без `make`:

```powershell
alembic upgrade head
pytest -q
ruff check .
mypy app
cd frontend
npm run typecheck
npm run lint
npm run test
```

## Полезные Команды

```bash
docker compose -f docker/docker-compose.dev.yaml ps
docker compose -f docker/docker-compose.dev.yaml logs -f crm-worker
docker compose -f docker/docker-compose.dev.yaml down
docker compose -f docker/docker-compose.dev.yaml down -v
```

`down -v` удаляет данные PostgreSQL и MinIO. После него заново выполните миграции и seed.

## Observability

```bash
docker compose -f docker/docker-compose.dev.yaml -f docker/docker-compose.monitoring.yaml up -d
```

Для `/metrics` включите:

```powershell
$env:METRICS_ENABLED = "true"
python scripts\run_uvicorn_win.py
```

Подробнее: [`OBSERVABILITY.md`](OBSERVABILITY.md).
