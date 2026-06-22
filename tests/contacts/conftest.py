from __future__ import annotations

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.security.passwords import hash_password
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest_asyncio.fixture
async def contacts_org(
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
                    INSERT INTO departments (name)
                    VALUES ('Contacts Scope Dept')
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
            )
            dept_id = connection.execute(
                text("SELECT id FROM departments WHERE name = 'Contacts Scope Dept'"),
            ).scalar_one()

            for group_name in ("Contacts Group A", "Contacts Group B"):
                connection.execute(
                    text(
                        """
                        INSERT INTO groups (name, department_id)
                        VALUES (:name, :dept_id)
                        ON CONFLICT (department_id, name) DO NOTHING
                        """
                    ),
                    {"name": group_name, "dept_id": dept_id},
                )
            group_a = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Contacts Group A'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()
            group_b = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Contacts Group B'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()

            users_spec = [
                ("operator.a@crm.local", "user", group_a),
                ("operator.b@crm.local", "user", group_b),
                ("senior.contacts@crm.local", "senior", None),
            ]
            user_ids: dict[str, int] = {}
            for email, role, group_id in users_spec:
                connection.execute(
                    text(
                        """
                        DELETE FROM audit_log
                        WHERE actor_id IN (SELECT id FROM users WHERE email = :email)
                        """
                    ),
                    {"email": email},
                )
                connection.execute(
                    text(
                        """
                        DELETE FROM contact_field_changes
                        WHERE changed_by IN (SELECT id FROM users WHERE email = :email)
                        """
                    ),
                    {"email": email},
                )
                connection.execute(
                    text(
                        """
                        DELETE FROM contacts
                        WHERE created_by IN (SELECT id FROM users WHERE email = :email)
                        """
                    ),
                    {"email": email},
                )
                connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
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
                            "full_name": "Senior Contacts",
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
                user_ids[email] = connection.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email},
                ).scalar_one()

            senior_id = user_ids["senior.contacts@crm.local"]
            connection.execute(
                text("UPDATE departments SET head_user_id = :senior_id WHERE id = :dept_id"),
                {"senior_id": senior_id, "dept_id": dept_id},
            )

            connection.execute(text("DELETE FROM contacts WHERE full_name LIKE 'Scope Contact %'"))
            contacts = [
                ("Scope Contact A", group_a, user_ids["operator.a@crm.local"]),
                ("Scope Contact B", group_b, user_ids["operator.b@crm.local"]),
                ("Scope Contact Senior", group_a, senior_id),
            ]
            contact_ids: list[int] = []
            for full_name, group_id, owner_id in contacts:
                contact_id = connection.execute(
                    text(
                        """
                        INSERT INTO contacts (
                            full_name, assigned_department_id, created_by
                        )
                        VALUES (
                            :full_name, :dept_id, :created_by
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "full_name": full_name,
                        "dept_id": dept_id,
                        "created_by": senior_id,
                    },
                ).scalar_one()
                connection.execute(
                    text(
                        """
                        INSERT INTO contact_group_assignments (
                            contact_id, group_id, owner_user_id, assignment_source
                        )
                        VALUES (:cid, :gid, :owner, 'migration')
                        ON CONFLICT (contact_id, group_id) DO NOTHING
                        """
                    ),
                    {"cid": contact_id, "gid": group_id, "owner": owner_id},
                )
                contact_ids.append(contact_id)
    finally:
        engine.dispose()

    return {
        "password": password,
        "dept_id": dept_id,
        "contacts_group_a": group_a,
        "contacts_group_b": group_b,
        "user_ids": user_ids,
        "contact_ids": contact_ids,
        "emails": {
            "operator_a": "operator.a@crm.local",
            "operator_b": "operator.b@crm.local",
            "senior": "senior.contacts@crm.local",
        },
    }


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


@pytest_asyncio.fixture
async def operator_a_token(
    client: AsyncClient,
    db_ready: None,
    contacts_org: dict[str, object],
) -> str:
    emails = contacts_org["emails"]
    assert isinstance(emails, dict)
    return await _login(client, str(emails["operator_a"]), str(contacts_org["password"]))


@pytest_asyncio.fixture
async def operator_b_token(
    client: AsyncClient,
    db_ready: None,
    contacts_org: dict[str, object],
) -> str:
    emails = contacts_org["emails"]
    assert isinstance(emails, dict)
    return await _login(client, str(emails["operator_b"]), str(contacts_org["password"]))


@pytest_asyncio.fixture
async def senior_token(
    client: AsyncClient,
    db_ready: None,
    contacts_org: dict[str, object],
) -> str:
    emails = contacts_org["emails"]
    assert isinstance(emails, dict)
    return await _login(client, str(emails["senior"]), str(contacts_org["password"]))


@pytest_asyncio.fixture
async def admin_headers(
    client: AsyncClient,
    db_ready: None,
    test_settings: Settings,
) -> dict[str, str]:
    token = await _login(
        client,
        test_settings.seed_admin_email,
        test_settings.seed_admin_password,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def operator_a_headers(operator_a_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {operator_a_token}"}


@pytest_asyncio.fixture
async def senior_headers(senior_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {senior_token}"}


@pytest_asyncio.fixture
async def operator_b_headers(operator_b_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {operator_b_token}"}
