from __future__ import annotations

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.security.passwords import hash_password
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url

_TEST_EMAILS = (
    "operator.chats.a@crm.local",
    "operator.chats.b@crm.local",
    "senior.chats@crm.local",
    "senior.other@crm.local",
)
_CHATS_CONTACT_PATTERN = "Chat Contact %"


@pytest_asyncio.fixture
async def chats_org(
    alembic_config: object,
    test_settings: Settings,
    db_ready: None,
) -> dict[str, object]:
    del alembic_config
    password = "TestPass!234567"
    password_hash = hash_password(password)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM chat_takeovers
                    WHERE chat_id IN (
                        SELECT id FROM chats
                        WHERE contact_id IN (
                            SELECT id FROM contacts WHERE full_name LIKE :pattern
                        )
                    )
                    """
                ),
                {"pattern": _CHATS_CONTACT_PATTERN},
            )
            connection.execute(
                text(
                    """
                    DELETE FROM messages
                    WHERE chat_id IN (
                        SELECT id FROM chats
                        WHERE contact_id IN (
                            SELECT id FROM contacts WHERE full_name LIKE :pattern
                        )
                    )
                    """
                ),
                {"pattern": _CHATS_CONTACT_PATTERN},
            )
            connection.execute(
                text(
                    """
                    DELETE FROM leads
                    WHERE contact_id IN (
                        SELECT id FROM contacts WHERE full_name LIKE :pattern
                    )
                    """
                ),
                {"pattern": _CHATS_CONTACT_PATTERN},
            )
            connection.execute(
                text(
                    """
                    DELETE FROM chats
                    WHERE contact_id IN (
                        SELECT id FROM contacts WHERE full_name LIKE :pattern
                    )
                    """
                ),
                {"pattern": _CHATS_CONTACT_PATTERN},
            )
            connection.execute(
                text("DELETE FROM contacts WHERE full_name LIKE :pattern"),
                {"pattern": _CHATS_CONTACT_PATTERN},
            )

            for dept_name in ("Chats Dept A", "Chats Dept B"):
                connection.execute(
                    text(
                        """
                        INSERT INTO departments (name)
                        VALUES (:name)
                        ON CONFLICT (name) DO NOTHING
                        """
                    ),
                    {"name": dept_name},
                )
            dept_a = connection.execute(
                text("SELECT id FROM departments WHERE name = 'Chats Dept A'"),
            ).scalar_one()
            dept_b = connection.execute(
                text("SELECT id FROM departments WHERE name = 'Chats Dept B'"),
            ).scalar_one()

            connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Chats Group A', :dept_id)
                    ON CONFLICT (department_id, name) DO NOTHING
                    """
                ),
                {"dept_id": dept_a},
            )
            group_a = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Chats Group A'
                    """
                ),
                {"dept_id": dept_a},
            ).scalar_one()

            users_spec = [
                ("operator.chats.a@crm.local", "user", group_a, dept_a),
                ("operator.chats.b@crm.local", "user", group_a, dept_a),
                ("senior.chats@crm.local", "senior", None, dept_a),
                ("senior.other@crm.local", "senior", None, dept_b),
            ]
            user_ids: dict[str, int] = {}
            for email, role, group_id, dept_id in users_spec:
                existing = connection.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email},
                ).scalar_one_or_none()
                if existing is None:
                    if role == "senior":
                        connection.execute(
                            text(
                                """
                                INSERT INTO users (
                                    email, username, password_hash, full_name,
                                    role, department_id, group_id
                                )
                                VALUES (
                                    :email, :username, :password_hash, :full_name,
                                    'senior', :dept_id, NULL
                                )
                                """
                            ),
                            {
                                "email": email,
                                "username": email.split("@")[0],
                                "password_hash": password_hash,
                                "full_name": email.split("@")[0],
                                "dept_id": dept_id,
                            },
                        )
                    else:
                        connection.execute(
                            text(
                                """
                                INSERT INTO users (
                                    email, username, password_hash, full_name,
                                    role, group_id, department_id
                                )
                                VALUES (
                                    :email, :username, :password_hash, :full_name,
                                    'user', :group_id, :dept_id
                                )
                                """
                            ),
                            {
                                "email": email,
                                "username": email.split("@")[0],
                                "password_hash": password_hash,
                                "full_name": email.split("@")[0],
                                "group_id": group_id,
                                "dept_id": dept_id,
                            },
                        )
                else:
                    connection.execute(
                        text(
                            """
                            UPDATE users
                            SET password_hash = :password_hash,
                                role = :role,
                                group_id = :group_id,
                                department_id = :dept_id,
                                status = 'active'
                            WHERE email = :email
                            """
                        ),
                        {
                            "email": email,
                            "password_hash": password_hash,
                            "role": role,
                            "group_id": group_id,
                            "dept_id": dept_id,
                        },
                    )
                user_ids[email] = connection.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email},
                ).scalar_one()

            senior_a = user_ids["senior.chats@crm.local"]
            connection.execute(
                text("UPDATE departments SET head_user_id = :sid WHERE id = :dept_id"),
                {"sid": senior_a, "dept_id": dept_a},
            )

            contact_ids: dict[str, int] = {}
            for key, full_name, _assigned_user in (
                ("a", "Chat Contact A", user_ids["operator.chats.a@crm.local"]),
                ("b", "Chat Contact B", user_ids["operator.chats.b@crm.local"]),
                ("dept_b", "Chat Contact DeptB", user_ids["senior.other@crm.local"]),
            ):
                dept_id = dept_a if key != "dept_b" else dept_b
                contact_ids[key] = connection.execute(
                    text(
                        """
                        INSERT INTO contacts (
                            full_name, assigned_department_id, created_by
                        )
                        VALUES (:full_name, :dept_id, :created_by)
                        RETURNING id
                        """
                    ),
                    {
                        "full_name": full_name,
                        "dept_id": dept_id,
                        "created_by": senior_a,
                    },
                ).scalar_one()

            chat_ids: dict[str, int] = {}
            for key, contact_id in contact_ids.items():
                assigned = user_ids["operator.chats.a@crm.local"]
                dept_id = dept_a
                group_id = group_a
                if key == "b":
                    assigned = user_ids["operator.chats.b@crm.local"]
                elif key == "dept_b":
                    assigned = user_ids["senior.other@crm.local"]
                    dept_id = dept_b
                    group_id = None
                chat_ids[key] = connection.execute(
                    text(
                        """
                        INSERT INTO chats (
                            contact_id, last_handled_by_user_id, assigned_group_id,
                            assigned_department_id, status, last_message_at, last_message_preview
                        )
                        VALUES (
                            :contact_id, :uid, :gid, :dept_id, 'open', now(), :preview
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "contact_id": contact_id,
                        "uid": assigned,
                        "gid": group_id,
                        "dept_id": dept_id,
                        "preview": f"Preview {key}",
                    },
                ).scalar_one()
    finally:
        engine.dispose()

    return {
        "password": password,
        "dept_a": dept_a,
        "dept_b": dept_b,
        "group_a": group_a,
        "user_ids": user_ids,
        "contact_ids": contact_ids,
        "chat_ids": chat_ids,
        "emails": {
            "operator_a": "operator.chats.a@crm.local",
            "operator_b": "operator.chats.b@crm.local",
            "senior": "senior.chats@crm.local",
            "senior_other": "senior.other@crm.local",
        },
    }


async def login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


@pytest_asyncio.fixture
async def operator_a_headers(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
) -> dict[str, str]:
    emails = chats_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["operator_a"]), str(chats_org["password"]))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def operator_b_headers(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
) -> dict[str, str]:
    emails = chats_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["operator_b"]), str(chats_org["password"]))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def senior_headers(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
) -> dict[str, str]:
    emails = chats_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["senior"]), str(chats_org["password"]))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def senior_other_headers(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
) -> dict[str, str]:
    emails = chats_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["senior_other"]), str(chats_org["password"]))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(
    client: AsyncClient,
    db_ready: None,
    test_settings: Settings,
) -> dict[str, str]:
    token = await login(
        client,
        test_settings.seed_admin_email,
        test_settings.seed_admin_password,
    )
    return {"Authorization": f"Bearer {token}"}
