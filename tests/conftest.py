from __future__ import annotations

pytest_plugins = [
    "tests.auth.conftest",
    "tests.contacts.conftest",
    "tests.contacts.conftest_ownership",
    "tests.chats.conftest",
    "tests.bots.conftest",
    "tests.leads.conftest",
]

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.shared import db as db_module
from app.shared.db import dispose_engine, get_db
from app.shared.exceptions import (
    AppError,
    AuthenticationRequired,
    Conflict,
    NotFound,
    PermissionDenied,
    RateLimited,
    ValidationError,
)
from app.shared.redis import close_redis
from app.shared.request_id import get_request_id
from app.shared.settings import Settings, get_settings


def _asyncpg_url(sync_url: str) -> str:
    if sync_url.startswith("postgresql+asyncpg://"):
        return sync_url
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
        if sync_url.startswith(prefix):
            return "postgresql+asyncpg://" + sync_url.removeprefix(prefix)
    return sync_url


def _docker_available() -> bool:
    try:
        import docker
    except ImportError:
        return False
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


def _local_test_settings() -> Settings:
    return Settings(
        database_url=_asyncpg_url(
            os.getenv("DATABASE_URL", "postgresql+asyncpg://crm:crm@localhost:5433/crm"),
        ),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        jwt_secret="test_jwt_secret_with_minimum_32_chars",
        cors_allowed_origins=["http://localhost:5173"],
        log_json=True,
        log_level="INFO",
    )


def _settings_from_containers(postgres_url: str, redis_host: str, redis_port: int) -> Settings:
    return Settings(
        database_url=_asyncpg_url(postgres_url),
        redis_url=f"redis://{redis_host}:{redis_port}/0",
        jwt_secret="test_jwt_secret_with_minimum_32_chars",
        cors_allowed_origins=["http://localhost:5173"],
        log_json=True,
        log_level="INFO",
    )


@pytest.fixture(scope="session")
def test_settings() -> Iterator[Settings]:
    use_local = os.getenv("CRM_TEST_USE_LOCAL", "").lower() in {"1", "true", "yes"}
    if use_local or not _docker_available():
        yield _local_test_settings()
        return

    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    with (
        PostgresContainer("postgres:16-alpine") as postgres,
        RedisContainer("redis:7-alpine") as redis,
    ):
        yield _settings_from_containers(
            postgres.get_connection_url(),
            redis.get_container_host_ip(),
            int(redis.get_exposed_port(6379)),
        )


@pytest.fixture(scope="session", autouse=True)
def _configure_test_env(test_settings: Settings) -> Iterator[None]:
    os.environ["DATABASE_URL"] = test_settings.database_url
    os.environ["REDIS_URL"] = test_settings.redis_url
    os.environ["JWT_SECRET"] = test_settings.jwt_secret
    os.environ["LOG_JSON"] = "true"
    os.environ["LOG_LEVEL"] = "INFO"
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _register_error_routes(application: FastAPI) -> None:
    error_map: dict[str, type[AppError]] = {
        "validation": ValidationError,
        "authentication": AuthenticationRequired,
        "permission": PermissionDenied,
        "not_found": NotFound,
        "conflict": Conflict,
        "rate_limited": RateLimited,
    }

    @application.get("/test/errors/{kind}")
    async def raise_error(kind: str) -> None:
        error_cls = error_map.get(kind)
        if error_cls is None:
            raise NotFound(message=f"Unknown error kind: {kind}")
        raise error_cls(message=f"Test {kind} error", details={"kind": kind})

    class ValidateBody(BaseModel):
        email: str

    @application.post("/test/validate")
    async def validate_body(_body: ValidateBody) -> dict[str, str]:
        return {"ok": "true"}

    probe_logger = structlog.get_logger("test.request_id")

    @application.get("/test/request-id")
    async def request_id_probe() -> dict[str, str]:
        probe_logger.info("request_id_probe", request_id=get_request_id())
        return {"ok": "true"}


@pytest_asyncio.fixture
async def app(test_settings: Settings) -> AsyncIterator[FastAPI]:
    get_settings.cache_clear()
    os.environ["DATABASE_URL"] = test_settings.database_url
    os.environ["REDIS_URL"] = test_settings.redis_url
    get_settings.cache_clear()

    await dispose_engine()
    await close_redis()

    application = create_app()
    _register_error_routes(application)
    yield application

    await close_redis()
    await dispose_engine()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        session_factory = db_module.get_session_factory()
        session = session_factory()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client

    app.dependency_overrides.clear()
