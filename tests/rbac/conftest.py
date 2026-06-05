from __future__ import annotations

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.shared.security.passwords import hash_password
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


def make_user(
    *,
    user_id: int,
    role: UserRole,
    department_id: int | None = None,
    group_id: int | None = None,
) -> User:
    return User(
        id=user_id,
        email=f"user{user_id}@example.com",
        password_hash="hash",
        full_name=f"User {user_id}",
        role=role,
        department_id=department_id,
        group_id=group_id,
    )


@pytest_asyncio.fixture
async def rbac_cross_group_org(
    alembic_config: object,
    test_settings: Settings,
    db_ready: None,
) -> dict[str, object]:
    """Two groups in one department — for IDOR smoke (cross-group chat access)."""
    del alembic_config
    password = "TestPass!234567"
    password_hash = hash_password(password)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM messages
                    WHERE chat_id IN (
                        SELECT id FROM chats WHERE last_message_preview LIKE 'RBAC XG %'
                    )
                    """
                ),
            )
            connection.execute(
                text("DELETE FROM chats WHERE last_message_preview LIKE 'RBAC XG %'"),
            )
            connection.execute(
                text("DELETE FROM contacts WHERE full_name LIKE 'RBAC XG %'"),
            )

            connection.execute(
                text(
                    """
                    INSERT INTO departments (name)
                    VALUES ('RBAC Cross Group Dept')
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
            )
            dept_id = connection.execute(
                text("SELECT id FROM departments WHERE name = 'RBAC Cross Group Dept'"),
            ).scalar_one()

            for group_name in ("RBAC XG Group A", "RBAC XG Group B"):
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
                    WHERE department_id = :dept_id AND name = 'RBAC XG Group A'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()
            group_b = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'RBAC XG Group B'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()

            users_spec = [
                ("rbac.xg.a@crm.local", group_a),
                ("rbac.xg.b@crm.local", group_b),
            ]
            user_ids: dict[str, int] = {}
            for email, group_id in users_spec:
                connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
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

            contact_a = connection.execute(
                text(
                    """
                    INSERT INTO contacts (full_name, assigned_department_id, created_by)
                    VALUES ('RBAC XG Contact A', :dept_id, :created_by)
                    RETURNING id
                    """
                ),
                {"dept_id": dept_id, "created_by": user_ids["rbac.xg.a@crm.local"]},
            ).scalar_one()
            contact_b = connection.execute(
                text(
                    """
                    INSERT INTO contacts (full_name, assigned_department_id, created_by)
                    VALUES ('RBAC XG Contact B', :dept_id, :created_by)
                    RETURNING id
                    """
                ),
                {"dept_id": dept_id, "created_by": user_ids["rbac.xg.b@crm.local"]},
            ).scalar_one()

            chat_a = connection.execute(
                text(
                    """
                    INSERT INTO chats (
                        contact_id, assigned_group_id, assigned_department_id,
                        status, last_message_at, last_message_preview
                    )
                    VALUES (
                        :contact_id, :gid, :dept_id, 'open', now(), 'RBAC XG chat A'
                    )
                    RETURNING id
                    """
                ),
                {"contact_id": contact_a, "gid": group_a, "dept_id": dept_id},
            ).scalar_one()
            chat_b = connection.execute(
                text(
                    """
                    INSERT INTO chats (
                        contact_id, assigned_group_id, assigned_department_id,
                        status, last_message_at, last_message_preview
                    )
                    VALUES (
                        :contact_id, :gid, :dept_id, 'open', now(), 'RBAC XG chat B'
                    )
                    RETURNING id
                    """
                ),
                {"contact_id": contact_b, "gid": group_b, "dept_id": dept_id},
            ).scalar_one()
    finally:
        engine.dispose()

    return {
        "password": password,
        "dept_id": dept_id,
        "group_a": group_a,
        "group_b": group_b,
        "chat_ids": {"a": chat_a, "b": chat_b},
        "contact_ids": {"a": contact_a, "b": contact_b},
        "emails": {
            "op_a": "rbac.xg.a@crm.local",
            "op_b": "rbac.xg.b@crm.local",
        },
    }


@pytest_asyncio.fixture
async def rbac_xg_op_a_headers(
    client: AsyncClient,
    db_ready: None,
    rbac_cross_group_org: dict[str, object],
) -> dict[str, str]:
    emails = rbac_cross_group_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_a"]), str(rbac_cross_group_org["password"]))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def rbac_xg_op_b_headers(
    client: AsyncClient,
    db_ready: None,
    rbac_cross_group_org: dict[str, object],
) -> dict[str, str]:
    emails = rbac_cross_group_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_b"]), str(rbac_cross_group_org["password"]))
    return {"Authorization": f"Bearer {token}"}
