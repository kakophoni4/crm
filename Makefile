.PHONY: install lint test migrate run gate gate-full gate-extended contract-smoke \
	monitoring-up monitoring-down docker-build docker-build-no-cache staging-config staging-up-local

DOCKER ?= docker
DOCKER_BUILD_FLAGS ?=
DOCKER_API_TAG ?= crm-api:local
DOCKER_WORKER_TAG ?= crm-worker:local
DOCKER_FRONTEND_TAG ?= crm-frontend:local

PYTHON ?= python
PIP ?= pip

install:
	$(PIP) install -e ".[dev]"

lint:
	ruff check .

test:
	pytest -q

migrate:
	alembic upgrade head

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

gate: migrate test lint
	mypy app

gate-full: gate
	cd frontend && npm run typecheck && npm run lint && npm run test

contract-smoke:
	pytest -q tests/contract/test_openapi_schemathesis.py

gate-extended: gate-full contract-smoke

monitoring-up:
	docker compose -f docker/docker-compose.dev.yaml -f docker/docker-compose.monitoring.yaml up -d

monitoring-down:
	docker compose -f docker/docker-compose.dev.yaml -f docker/docker-compose.monitoring.yaml down

docker-build:
	$(DOCKER) build $(DOCKER_BUILD_FLAGS) -f docker/Dockerfile.backend -t $(DOCKER_API_TAG) .
	$(DOCKER) build $(DOCKER_BUILD_FLAGS) -f docker/Dockerfile.worker -t $(DOCKER_WORKER_TAG) .
	$(DOCKER) build $(DOCKER_BUILD_FLAGS) -f docker/Dockerfile.frontend -t $(DOCKER_FRONTEND_TAG) .

docker-build-no-cache:
	$(MAKE) docker-build DOCKER_BUILD_FLAGS=--no-cache

staging-config:
	docker compose -f docker/docker-compose.staging.yaml --env-file deploy/.env.staging config

staging-up-local:
	docker compose -f docker/docker-compose.staging.yaml -f docker/docker-compose.local.yaml \
		--env-file deploy/.env.staging up -d --build
