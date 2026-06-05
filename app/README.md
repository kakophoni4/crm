# Backend (`app/`)

Developer guide for the CRM Chat Center FastAPI skeleton.

## Prerequisites

- Python 3.12+
- Docker Compose dev stack (`docker/docker-compose.dev.yaml`) for PostgreSQL and Redis
- `.env` in the repository root (copy from `.env.example`)

## Install

```bash
pip install -e ".[dev]"
```

## Run locally

```bash
docker compose -f docker/docker-compose.dev.yaml up -d
make run
```

API:

- Health: http://localhost:8000/healthz
- Swagger: http://localhost:8000/api/docs
- OpenAPI: http://localhost:8000/api/openapi.json

## Migrations

Create a revision:

```bash
alembic revision -m "describe_change"
```

Apply migrations:

```bash
make migrate
```

## Tests

```bash
make test
```

Requires Docker (testcontainers starts PostgreSQL and Redis).

## Lint

```bash
make lint
```

## Add a new module

1. Create a package under `app/modules/<name>/` or `app/core/<name>/`.
2. Add routers and wire them in `create_app()` when the module is ready.
3. Add Alembic migrations for schema changes.
4. Add service tests under `tests/`.
