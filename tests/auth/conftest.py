from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from alembic import command
from app.shared.db import db_ping
from app.shared.security.passwords import hash_password
from app.shared.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]

no_db = os.getenv("CRM_TEST_SKIP_DB", "").lower() in {"1", "true", "yes"}


def _sync_database_url(database_url: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://"):
        if database_url.startswith(prefix):
            return "postgresql+psycopg://" + database_url.removeprefix(prefix)
    return database_url


@pytest.fixture(scope="session")
def alembic_config(test_settings: Settings) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _sync_database_url(test_settings.database_url))
    return cfg


@pytest.fixture(scope="session")
def migrated_db(alembic_config: Config, test_settings: Settings) -> Iterator[None]:
    if no_db:
        yield
        return

    command.upgrade(alembic_config, "head")
    yield
    command.downgrade(alembic_config, "base")


@pytest_asyncio.fixture(autouse=True)
async def _reset_login_rate_limits() -> None:
    from app.modules.auth.rate_limit import (
        reset_in_memory_login_rate_limits,
        reset_redis_login_rate_limits,
    )

    reset_in_memory_login_rate_limits()
    await reset_redis_login_rate_limits()
    yield
    reset_in_memory_login_rate_limits()
    await reset_redis_login_rate_limits()


@pytest_asyncio.fixture
async def db_ready(migrated_db: None, alembic_config: Config) -> None:
    if no_db:
        pytest.skip("CRM_TEST_SKIP_DB is set")
    from app.shared.db import dispose_engine
    from app.shared.redis import close_redis

    command.upgrade(alembic_config, "head")
    await dispose_engine()
    await close_redis()
    if not await db_ping():
        pytest.skip("PostgreSQL not available")


@pytest.fixture
def admin_credentials(test_settings: Settings) -> dict[str, str]:
    return {
        "username": "admin",
        "password": test_settings.seed_admin_password,
    }


@pytest_asyncio.fixture
async def auth_user(
    client: AsyncClient,
    db_ready: None,
    admin_credentials: dict[str, str],
) -> dict[str, object]:
    response = await client.post("/api/v1/auth/login", json=admin_credentials)
    if response.status_code != 200:
        pytest.skip(f"Admin login unavailable: {response.status_code} {response.text}")
    payload = response.json()
    return {
        "username": admin_credentials["username"],
        "email": payload["user"]["email"],
        "password": admin_credentials["password"],
        "access_token": payload["access_token"],
        "refresh_token": payload["refresh_token"],
        "user": payload["user"],
    }


@pytest_asyncio.fixture
async def extra_user(
    alembic_config: Config,
    test_settings: Settings,
    db_ready: None,
) -> dict[str, str]:
    email = "operator.auth.test@crm.local"
    username = "operator_auth_test"
    password = "TestPass!234567"
    password_hash = hash_password(password)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO departments (name)
                    VALUES ('Auth Test Dept')
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
            )
            dept_id = connection.execute(
                text("SELECT id FROM departments WHERE name = 'Auth Test Dept'"),
            ).scalar_one()

            connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Auth Test Group', :dept_id)
                    ON CONFLICT (department_id, name) DO NOTHING
                    """
                ),
                {"dept_id": dept_id},
            )
            group_id = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Auth Test Group'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()

            connection.execute(
                text("DELETE FROM users WHERE email = :email"),
                {"email": email},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        email, username, password_hash, full_name, role, group_id
                    )
                    VALUES (
                        :email, :username, :password_hash, 'Auth Test User', 'user', :group_id
                    )
                    """
                ),
                {
                    "email": email,
                    "username": username,
                    "password_hash": password_hash,
                    "group_id": group_id,
                },
            )
    finally:
        engine.dispose()

    return {"username": username, "password": password}
