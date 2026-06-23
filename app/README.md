# Backend (`app/`)

FastAPI backend CRM Chat Center.

## Назначение

Backend обслуживает REST API, WebSocket realtime, auth/JWT, RBAC, контакты, чаты, лиды, статусы, ботов, файлы, аналитику и телефонию.

## Требования

- Python 3.12+
- PostgreSQL/Redis/MinIO из `docker/docker-compose.dev.yaml`
- `.env` в корне репозитория

## Установка

```bash
pip install -e ".[dev]"
```

## Запуск

```bash
docker compose -f docker/docker-compose.dev.yaml up -d
alembic upgrade head
python scripts/seed_dev_data.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows:

```powershell
python scripts\run_uvicorn_win.py
```

API:

- Health: http://localhost:8000/healthz
- Readiness: http://localhost:8000/readyz
- Swagger: http://localhost:8000/api/docs
- OpenAPI: http://localhost:8000/api/openapi.json

## Миграции

Создать ревизию:

```bash
alembic revision -m "describe_change"
```

Применить миграции:

```bash
alembic upgrade head
```

## Worker

```bash
python -m app.workers.run
```

В dev compose worker уже есть как `crm-worker`; после полного сброса БД примените миграции перед использованием API/worker.

## Проверки

```bash
ruff check .
mypy app
pytest -q
```

## Новый Модуль

1. Создайте пакет в `app/modules/<name>/`.
2. Вынесите схемы, router, service/repository по текущим паттернам модуля.
3. Подключите router в `app/main.py`.
4. Для изменений БД добавьте Alembic migration.
5. Добавьте тесты в `tests/<domain>/`.
6. При изменении публичного контракта обновите `docs/API_CONTRACT.md`, `docs/EVENTS.md`, `docs/DATABASE.md` или `docs/RBAC_MATRIX.md`.
