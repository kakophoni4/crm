from __future__ import annotations

import json
import os
import time

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.modules.bots.hmac_util import sign_inbound
from app.shared.security.passwords import hash_password
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url

INBOUND_SECRET = "test-inbound-secret-32chars-minimum"
OUTBOUND_SECRET = "test-outbound-secret-32chars-minimum"


def sign_event(event_id: str, timestamp: str, body: bytes, secret: str = INBOUND_SECRET) -> str:
    return sign_inbound(event_id, timestamp, body, secret)


@pytest_asyncio.fixture
async def bots_org(
    alembic_config: object,
    test_settings: Settings,
    db_ready: None,
) -> dict[str, object]:
    del alembic_config
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM bot_events_inbox"))
            connection.execute(text("DELETE FROM bot_outbound_log"))
            connection.execute(text("DELETE FROM messages WHERE external_event_id LIKE 'bot-%'"))
            connection.execute(text("DELETE FROM chats WHERE bot_id IS NOT NULL"))
            connection.execute(text("DELETE FROM contacts WHERE telegram_user_id = 999001"))
            connection.execute(text("DELETE FROM bots WHERE code = 'test_bot_a'"))

            connection.execute(
                text(
                    """
                    INSERT INTO departments (name)
                    VALUES ('Bots Test Dept')
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
            )
            dept_id = connection.execute(
                text("SELECT id FROM departments WHERE name = 'Bots Test Dept'"),
            ).scalar_one()

            key = test_settings.pgcrypto_key
            connection.execute(
                text(
                    """
                    INSERT INTO bots (
                        code, name, owner_type, owner_id, department_id,
                        inbound_secret_encrypted, outbound_secret_encrypted,
                        outbound_url, health_url, is_active
                    )
                    VALUES (
                        'test_bot_a', 'Test Bot',
                        'department', :dept_id, :dept_id,
                        pgp_sym_encrypt(:in_secret, :key),
                        pgp_sym_encrypt(:out_secret, :key),
                        'https://bot.example.com/crm/cmd',
                        'https://bot.example.com/crm/health',
                        TRUE
                    )
                    RETURNING id
                    """
                ),
                {
                    "dept_id": dept_id,
                    "in_secret": INBOUND_SECRET,
                    "out_secret": OUTBOUND_SECRET,
                    "key": key,
                },
            )
            bot_id = connection.execute(
                text("SELECT id FROM bots WHERE code = 'test_bot_a'"),
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Bots Test Group', :dept_id)
                    ON CONFLICT (department_id, name) DO NOTHING
                    """
                ),
                {"dept_id": dept_id},
            )
            group_id = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Bots Test Group'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()
    finally:
        engine.dispose()

    return {
        "bot_id": bot_id,
        "bot_code": "test_bot_a",
        "dept_id": dept_id,
        "group_id": group_id,
        "inbound_secret": INBOUND_SECRET,
        "outbound_secret": OUTBOUND_SECRET,
    }


@pytest_asyncio.fixture
async def operator_headers(
    client: AsyncClient,
    db_ready: None,
    test_settings: Settings,
) -> dict[str, str]:
    del test_settings
    email = "operator.bots@crm.local"
    password = "TestPass!234567"
    password_hash = hash_password(password)
    engine = create_engine(_sync_database_url(os.environ["DATABASE_URL"]))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO departments (name)
                    VALUES ('Bots Test Dept')
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
            )
            dept_id = connection.execute(
                text("SELECT id FROM departments WHERE name = 'Bots Test Dept'"),
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Bots Test Group', :dept_id)
                    ON CONFLICT (department_id, name) DO NOTHING
                    """
                ),
                {"dept_id": dept_id},
            )
            group_id = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Bots Test Group'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()
            connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        email, username, password_hash, full_name, role, group_id, department_id
                    )
                    VALUES (:email, :username, :ph, 'Bots Operator', 'user', :gid, :dept_id)
                    """
                ),
                {
                    "email": email,
                    "username": email.split("@")[0],
                    "ph": password_hash,
                    "gid": group_id,
                    "dept_id": dept_id,
                },
            )
    finally:
        engine.dispose()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def admin_headers(
    client: AsyncClient,
    db_ready: None,
    test_settings: Settings,
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": test_settings.seed_admin_password,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def senior_headers(
    client: AsyncClient,
    db_ready: None,
    test_settings: Settings,
) -> dict[str, str]:
    del test_settings
    email = "senior.bots@crm.local"
    password = "TestPass!234567"
    password_hash = hash_password(password)
    engine = create_engine(_sync_database_url(os.environ["DATABASE_URL"]))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO departments (name)
                    VALUES ('Bots Test Dept')
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
            )
            dept_id = connection.execute(
                text("SELECT id FROM departments WHERE name = 'Bots Test Dept'"),
            ).scalar_one()
            connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        email, username, password_hash, full_name, role, department_id
                    )
                    VALUES (:email, :username, :ph, 'Bots Senior', 'senior', :dept_id)
                    """
                ),
                {
                    "email": email,
                    "username": email.split("@")[0],
                    "ph": password_hash,
                    "dept_id": dept_id,
                },
            )
    finally:
        engine.dispose()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def build_inbound_payload(
    *,
    event_id: str = "01J5BOTEVENT0001",
    bot_code: str = "test_bot_a",
    direction: str | None = None,
    external_id: str = "msg_bot_001",
    text: str = "Hello from bot",
    telegram_user_id: int = 999001,
    ref_code: str | None = None,
) -> tuple[bytes, dict[str, str]]:
    message: dict[str, object] = {
        "external_id": external_id,
        "text": text,
        "attachments": [],
        "sent_at": "2026-05-16T12:34:55Z",
    }
    if direction is not None:
        message["direction"] = direction
    contact: dict[str, object] = {
        "telegram_user_id": telegram_user_id,
        "telegram_username": "bot_test_user",
        "first_name": "Bot",
        "last_name": "Tester",
    }
    if ref_code is not None:
        contact["ref_code"] = ref_code
    envelope = {
        "event": "message.received",
        "event_id": event_id,
        "occurred_at": "2026-05-16T12:34:56Z",
        "bot_code": bot_code,
        "payload": {
            "contact": contact,
            "message": message,
        },
    }
    body = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    headers = {
        "X-Bot-Code": bot_code,
        "X-Event-Id": event_id,
        "X-Timestamp": ts,
        "X-Signature": sign_event(event_id, ts, body),
        "Content-Type": "application/json",
    }
    return body, headers
