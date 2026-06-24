from __future__ import annotations

import pytest_asyncio
from sqlalchemy import create_engine, text

from app.shared.security.passwords import hash_password
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest_asyncio.fixture
async def ownership_org(
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
                    VALUES ('Ownership Dept')
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
            )
            dept_id = connection.execute(
                text("SELECT id FROM departments WHERE name = 'Ownership Dept'"),
            ).scalar_one()

            connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Ownership Group', :dept_id)
                    ON CONFLICT (department_id, name) DO NOTHING
                    """
                ),
                {"dept_id": dept_id},
            )
            group_id = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Ownership Group'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()

            connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Ownership Group B', :dept_id)
                    ON CONFLICT (department_id, name) DO NOTHING
                    """
                ),
                {"dept_id": dept_id},
            )
            group_b_id = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Ownership Group B'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()

            user_specs = [
                ("owner.op1@crm.local", group_id, "available", "online"),
                ("owner.op2@crm.local", group_id, "available", "online"),
                ("owner.op3@crm.local", group_id, "do_not_assign", "online"),
                ("owner.senior@crm.local", None, "available", "online"),
            ]
            user_ids: dict[str, int] = {}
            for email, gid, availability, presence in user_specs:
                existing = connection.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email},
                ).scalar_one_or_none()
                if existing is None:
                    if gid is None:
                        connection.execute(
                            text(
                                """
                                INSERT INTO users (
                                    email, username, password_hash, full_name, role,
                                    department_id, availability, presence
                                )
                                VALUES (
                                    :email, :username, :password_hash, :full_name, 'senior',
                                    :dept_id, :availability, :presence
                                )
                                """
                            ),
                            {
                                "email": email,
                                "username": email.split("@")[0],
                                "password_hash": password_hash,
                                "full_name": email.split("@")[0],
                                "dept_id": dept_id,
                                "availability": availability,
                                "presence": presence,
                            },
                        )
                    else:
                        connection.execute(
                            text(
                                """
                                INSERT INTO users (
                                    email, username, password_hash, full_name, role, group_id,
                                    department_id, availability, presence
                                )
                                VALUES (
                                    :email, :username, :password_hash, :full_name, 'user', :gid,
                                    :dept_id, :availability, :presence
                                )
                                """
                            ),
                            {
                                "email": email,
                                "username": email.split("@")[0],
                                "password_hash": password_hash,
                                "full_name": email.split("@")[0],
                                "gid": gid,
                                "dept_id": dept_id,
                                "availability": availability,
                                "presence": presence,
                            },
                        )
                else:
                    connection.execute(
                        text(
                            """
                            UPDATE users
                            SET password_hash = :password_hash,
                                role = :role,
                                group_id = :gid,
                                department_id = :dept_id,
                                availability = :availability,
                                presence = :presence,
                                status = 'active'
                            WHERE email = :email
                            """
                        ),
                        {
                            "email": email,
                            "password_hash": password_hash,
                            "role": "senior" if gid is None else "user",
                            "gid": gid,
                            "dept_id": dept_id,
                            "availability": availability,
                            "presence": presence,
                        },
                    )
                user_ids[email] = connection.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email},
                ).scalar_one()

            connection.execute(
                text("UPDATE departments SET head_user_id = :sid WHERE id = :dept_id"),
                {"sid": user_ids["owner.senior@crm.local"], "dept_id": dept_id},
            )

            connection.execute(
                text(
                    """
                    DELETE FROM message_reply_audit
                    WHERE contact_id IN (
                        SELECT id FROM contacts WHERE full_name LIKE 'Ownership Contact %'
                    )
                    """
                ),
            )
            connection.execute(
                text(
                    """
                    DELETE FROM contact_group_assignments
                    WHERE contact_id IN (
                        SELECT id FROM contacts WHERE full_name LIKE 'Ownership Contact %'
                    )
                    """
                ),
            )
            ownership_contact_filter = (
                "full_name LIKE 'Ownership Contact %'"
            )
            connection.execute(
                text(
                    f"""
                    DELETE FROM messages
                    WHERE chat_id IN (
                        SELECT id FROM chats
                        WHERE contact_id IN (
                            SELECT id FROM contacts WHERE {ownership_contact_filter}
                        )
                    )
                    """
                ),
            )
            connection.execute(
                text(
                    f"""
                    DELETE FROM lead_comments
                    WHERE lead_id IN (
                        SELECT id FROM leads
                        WHERE contact_id IN (
                            SELECT id FROM contacts WHERE {ownership_contact_filter}
                        )
                    )
                    """
                ),
            )
            connection.execute(
                text(
                    f"""
                    UPDATE chats
                    SET current_lead_id = NULL
                    WHERE contact_id IN (
                        SELECT id FROM contacts WHERE {ownership_contact_filter}
                    )
                    """
                ),
            )
            connection.execute(
                text(
                    f"""
                    DELETE FROM leads
                    WHERE contact_id IN (
                        SELECT id FROM contacts WHERE {ownership_contact_filter}
                    )
                    """
                ),
            )
            connection.execute(
                text(
                    f"""
                    DELETE FROM chats
                    WHERE contact_id IN (
                        SELECT id FROM contacts WHERE {ownership_contact_filter}
                    )
                    """
                ),
            )
            connection.execute(
                text("DELETE FROM contacts WHERE full_name LIKE 'Ownership Contact %'"),
            )

            contact_ids: list[int] = []
            for idx in range(4):
                contact_id = connection.execute(
                    text(
                        """
                        INSERT INTO contacts (full_name, created_by)
                        VALUES (:name, :created_by)
                        RETURNING id
                        """
                    ),
                    {
                        "name": f"Ownership Contact {idx}",
                        "created_by": user_ids["owner.senior@crm.local"],
                    },
                ).scalar_one()
                owner_id = user_ids["owner.op1@crm.local"]
                assignment_group = group_id if idx < 3 else group_b_id
                if idx == 1:
                    owner_id = user_ids["owner.op2@crm.local"]
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
                    {"cid": contact_id, "gid": assignment_group, "owner": owner_id},
                )
                contact_ids.append(contact_id)

            for gid, timeout, strategy in (
                (group_id, 1, "first_responder"),
                (group_b_id, 15, "first_responder"),
            ):
                connection.execute(
                    text(
                        """
                        INSERT INTO group_escalation_settings (
                            group_id,
                            first_response_timeout_minutes,
                            new_contact_reassign_strategy,
                            notify_owner_on_inbound,
                            notify_group_on_escalation
                        )
                        VALUES (:gid, :timeout, :strategy, TRUE, TRUE)
                        ON CONFLICT (group_id) DO UPDATE SET
                            first_response_timeout_minutes = (
                                EXCLUDED.first_response_timeout_minutes
                            ),
                            new_contact_reassign_strategy = (
                                EXCLUDED.new_contact_reassign_strategy
                            ),
                            notify_owner_on_inbound = EXCLUDED.notify_owner_on_inbound,
                            notify_group_on_escalation = EXCLUDED.notify_group_on_escalation
                        """
                    ),
                    {"gid": gid, "timeout": timeout, "strategy": strategy},
                )
    finally:
        engine.dispose()

    return {
        "password": password,
        "dept_id": dept_id,
        "group_id": group_id,
        "group_b_id": group_b_id,
        "user_ids": user_ids,
        "contact_ids": contact_ids,
        "emails": {
            "op1": "owner.op1@crm.local",
            "op2": "owner.op2@crm.local",
            "op3": "owner.op3@crm.local",
            "senior": "owner.senior@crm.local",
        },
    }


async def _login_ownership(client, email: str, password: str) -> str:

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


@pytest_asyncio.fixture
async def ownership_op1_headers(
    client,
    db_ready: None,
    ownership_org: dict[str, object],
) -> dict[str, str]:
    emails = ownership_org["emails"]
    assert isinstance(emails, dict)
    token = await _login_ownership(client, str(emails["op1"]), str(ownership_org["password"]))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def ownership_op2_headers(
    client,
    db_ready: None,
    ownership_org: dict[str, object],
) -> dict[str, str]:
    emails = ownership_org["emails"]
    assert isinstance(emails, dict)
    token = await _login_ownership(client, str(emails["op2"]), str(ownership_org["password"]))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def ownership_senior_headers(
    client,
    db_ready: None,
    ownership_org: dict[str, object],
) -> dict[str, str]:
    emails = ownership_org["emails"]
    assert isinstance(emails, dict)
    token = await _login_ownership(client, str(emails["senior"]), str(ownership_org["password"]))
    return {"Authorization": f"Bearer {token}"}
