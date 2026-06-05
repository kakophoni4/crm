# Dev setup (кратко)

## Зависимости

```bash
docker compose -f docker/docker-compose.dev.yaml up -d
pip install -e ".[dev]"
cd frontend && npm ci
```

## Миграции

```bash
alembic upgrade head
```

После `pytest` с session-фикстурой `migrated_db` схема может быть на `base`. Перед API/E2E:

```bash
alembic upgrade head
```

## API (Windows)

```powershell
$env:OWNERSHIP_V2 = "true"
python scripts/run_uvicorn_win.py
```

Linux/macOS: `uvicorn app.main:app --reload` (порт 8000).

## Worker (отдельный процесс)

```bash
python -m app.workers.run
```

`WORKERS_IN_API=true` — только для one-process dev (воркеры в lifespan API).

## Frontend

```bash
cd frontend && npm run dev
```

## QA E2E ownership

API на `:8000`, затем:

```bash
python scripts/qa_e2e_ownership.py
```

Скрипт проверяет `alembic_version == head` и наличие `message_reply_audit`.

## Gate (backend)

```bash
make gate
```

Эквивалент: `alembic upgrade head`, `pytest -q`, `ruff check .`, `mypy app`.

## Gate-full (backend + frontend)

```bash
make gate-full
```

### Windows (без make)

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

## Observability (фаза 6, backend)

Переменные в `.env` (см. `.env.example`):

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `METRICS_ENABLED` | `false` | `GET /metrics` (Prometheus) |
| `LOG_PII_MASK` | `true` | маскирование PII в structlog |
| `SENTRY_DSN` | пусто | Sentry backend (опционально) |
| `SENTRY_ENVIRONMENT` | `dev` | тег environment в Sentry |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | доля транзакций (0–1) |

Локально включить метрики:

```powershell
$env:METRICS_ENABLED = "true"
python scripts/run_uvicorn_win.py
curl http://localhost:8000/metrics
```

Readiness (для k8s/compose):

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/readyz
```

Без `METRICS_ENABLED=true` эндпоинт `/metrics` отвечает **404**.

## Sentry frontend (фаза 6)

В `frontend/.env` (шаблон `frontend/.env.example`):

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `VITE_SENTRY_DSN` | пусто | Sentry browser/Vue SDK (опционально) |
| `VITE_SENTRY_ENVIRONMENT` | `dev` | тег `environment` в Sentry |

Без DSN приложение стартует как обычно; в тестах `@sentry/vue` замокан. Подробнее: [OBSERVABILITY.md](./OBSERVABILITY.md#sentry).
