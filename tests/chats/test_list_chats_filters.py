from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.security.passwords import hash_password
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.chats.conftest import login


def _cleanup_filter_chats(connection) -> None:
    connection.execute(
        text(
            """
            DELETE FROM chat_read_state
            WHERE chat_id IN (
                SELECT id FROM chats WHERE last_message_preview LIKE 'Filter %'
            )
            """
        ),
    )
    connection.execute(
        text(
            """
            DELETE FROM leads
            WHERE contact_id IN (
                SELECT id FROM contacts WHERE full_name LIKE 'Filter Chat %'
            )
            """
        ),
    )
    connection.execute(
        text(
            """
            DELETE FROM contact_group_assignments
            WHERE contact_id IN (
                SELECT id FROM contacts WHERE full_name LIKE 'Filter Chat %'
            )
            """
        ),
    )
    connection.execute(
        text(
            """
            DELETE FROM chat_takeovers
            WHERE chat_id IN (
                SELECT id FROM chats WHERE last_message_preview LIKE 'Filter %'
            )
            """
        ),
    )
    connection.execute(
        text(
            """
            DELETE FROM messages
            WHERE chat_id IN (
                SELECT id FROM chats WHERE last_message_preview LIKE 'Filter %'
            )
            """
        ),
    )
    connection.execute(text("DELETE FROM chats WHERE last_message_preview LIKE 'Filter %'"))
    connection.execute(text("DELETE FROM contacts WHERE full_name LIKE 'Filter Chat %'"))
    connection.execute(text("DELETE FROM bots WHERE code LIKE 'filter_bot_%'"))


@pytest_asyncio.fixture
async def chats_filters_org(
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
            _cleanup_filter_chats(connection)

            connection.execute(
                text(
                    """
                    INSERT INTO departments (name)
                    VALUES ('Filter Chats Dept')
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
            )
            dept_id = connection.execute(
                text("SELECT id FROM departments WHERE name = 'Filter Chats Dept'"),
            ).scalar_one()

            for group_name in ("Filter Group A", "Filter Group B"):
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
                    WHERE department_id = :dept_id AND name = 'Filter Group A'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()
            group_b = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Filter Group B'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()

            users_spec = [
                ("filter.op.a@crm.local", "user", group_a),
                ("filter.op.b@crm.local", "user", group_b),
            ]
            user_ids: dict[str, int] = {}
            for email, role, group_id in users_spec:
                existing = connection.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email},
                ).scalar_one_or_none()
                if existing is None:
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

            bot_ids: dict[str, int] = {}
            for code, owner_id in (("filter_bot_a", group_a), ("filter_bot_b", group_b)):
                bot_ids[code] = connection.execute(
                    text(
                        """
                        INSERT INTO bots (
                            code, name, owner_type, owner_id,
                            inbound_secret_encrypted, outbound_secret_encrypted, outbound_url
                        )
                        VALUES (
                            :code, :name, 'group', :owner_id,
                            '\\x00', '\\x00', 'https://example.test/outbound'
                        )
                        RETURNING id
                        """
                    ),
                    {"code": code, "name": code, "owner_id": owner_id},
                ).scalar_one()

            contact_ids: dict[str, int] = {}
            for key, full_name in (
                ("a_unread", "Filter Chat A Unread"),
                ("a_read", "Filter Chat A Read"),
                ("b_other", "Filter Chat B Other"),
            ):
                contact_ids[key] = connection.execute(
                    text(
                        """
                        INSERT INTO contacts (full_name, assigned_department_id, created_by)
                        VALUES (:full_name, :dept_id, :created_by)
                        RETURNING id
                        """
                    ),
                    {
                        "full_name": full_name,
                        "dept_id": dept_id,
                        "created_by": user_ids["filter.op.a@crm.local"],
                    },
                ).scalar_one()

            connection.execute(
                text(
                    """
                    INSERT INTO contact_group_assignments (
                        contact_id, group_id, owner_user_id, assignment_source
                    )
                    VALUES
                        (:c1, :gid, :owner_a, 'auto_round_robin'),
                        (:c2, :gid, :owner_a, 'auto_round_robin')
                    """
                ),
                {
                    "c1": contact_ids["a_unread"],
                    "c2": contact_ids["a_read"],
                    "gid": group_a,
                    "owner_a": user_ids["filter.op.a@crm.local"],
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO contact_group_assignments (
                        contact_id, group_id, owner_user_id, assignment_source
                    )
                    VALUES (:cid, :gid, :owner_b, 'auto_round_robin')
                    """
                ),
                {
                    "cid": contact_ids["b_other"],
                    "gid": group_b,
                    "owner_b": user_ids["filter.op.b@crm.local"],
                },
            )

            chat_ids: dict[str, int] = {}
            chat_specs = [
                (
                    "a_unread",
                    contact_ids["a_unread"],
                    group_a,
                    bot_ids["filter_bot_a"],
                    3,
                    "Filter unread",
                ),
                (
                    "a_read",
                    contact_ids["a_read"],
                    group_a,
                    bot_ids["filter_bot_a"],
                    0,
                    "Filter read",
                ),
                (
                    "b_other",
                    contact_ids["b_other"],
                    group_b,
                    bot_ids["filter_bot_b"],
                    1,
                    "Filter other group",
                ),
            ]
            lead_status_id = connection.execute(
                text(
                    """
                    SELECT id FROM statuses
                    WHERE kind = 'lead_pipeline'
                    ORDER BY id
                    LIMIT 1
                    """
                ),
            ).scalar_one()
            op_a_id = user_ids["filter.op.a@crm.local"]
            for key, contact_id, group_id, bot_id, _unread, preview in chat_specs:
                chat_ids[key] = connection.execute(
                    text(
                        """
                        INSERT INTO chats (
                            contact_id, bot_id, assigned_group_id, assigned_department_id,
                            status, last_message_at, last_message_preview,
                            created_at
                        )
                        VALUES (
                            :contact_id, :bot_id, :gid, :dept_id, 'open',
                            now() - (:offset || ' minutes')::interval, :preview,
                            now() - (:created_offset || ' hours')::interval
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "contact_id": contact_id,
                        "bot_id": bot_id,
                        "gid": group_id,
                        "dept_id": dept_id,
                        "preview": preview,
                        "offset": {"a_unread": 1, "a_read": 2, "b_other": 3}[key],
                        "created_offset": {"a_unread": 1, "a_read": 3, "b_other": 2}[key],
                    },
                ).scalar_one()
                lead_id = connection.execute(
                    text(
                        """
                        INSERT INTO leads (
                            contact_id, group_id, chat_id, status_id, title
                        )
                        VALUES (:cid, :gid, :chat_id, :status_id, :title)
                        RETURNING id
                        """
                    ),
                    {
                        "cid": contact_id,
                        "gid": group_id,
                        "chat_id": chat_ids[key],
                        "status_id": lead_status_id,
                        "title": preview,
                    },
                ).scalar_one()
                connection.execute(
                    text("UPDATE chats SET current_lead_id = :lid WHERE id = :cid"),
                    {"lid": lead_id, "cid": chat_ids[key]},
                )
                message_id = connection.execute(
                    text(
                        """
                        INSERT INTO messages (
                            chat_id, lead_id, direction, kind, text
                        )
                        VALUES (:cid, :lid, 'inbound', 'text', :body)
                        RETURNING id
                        """
                    ),
                    {"cid": chat_ids[key], "lid": lead_id, "body": f"{preview} body"},
                ).scalar_one()
                if key == "a_read":
                    connection.execute(
                        text(
                            """
                            INSERT INTO chat_read_state (
                                chat_id, user_id, last_read_message_id, read_at
                            )
                            VALUES (:cid, :uid, :mid, now())
                            ON CONFLICT (chat_id, user_id) DO UPDATE SET
                                last_read_message_id = EXCLUDED.last_read_message_id,
                                read_at = EXCLUDED.read_at
                            """
                        ),
                        {"cid": chat_ids[key], "uid": op_a_id, "mid": message_id},
                    )
    finally:
        engine.dispose()

    payload = {
        "password": password,
        "dept_id": dept_id,
        "group_a": group_a,
        "group_b": group_b,
        "user_ids": user_ids,
        "bot_ids": bot_ids,
        "chat_ids": chat_ids,
        "emails": {
            "op_a": "filter.op.a@crm.local",
            "op_b": "filter.op.b@crm.local",
        },
    }
    yield payload

    teardown = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with teardown.begin() as connection:
            _cleanup_filter_chats(connection)
    finally:
        teardown.dispose()


@pytest_asyncio.fixture
async def filter_op_a_headers(
    client: AsyncClient,
    db_ready: None,
    chats_filters_org: dict[str, object],
) -> dict[str, str]:
    emails = chats_filters_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_a"]), str(chats_filters_org["password"]))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def filter_op_b_headers(
    client: AsyncClient,
    db_ready: None,
    chats_filters_org: dict[str, object],
) -> dict[str, str]:
    emails = chats_filters_org["emails"]
    assert isinstance(emails, dict)
    token = await login(client, str(emails["op_b"]), str(chats_filters_org["password"]))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_chats_filter_bot_id(
    client: AsyncClient,
    db_ready: None,
    chats_filters_org: dict[str, object],
    filter_op_a_headers: dict[str, str],
) -> None:
    bot_ids = chats_filters_org["bot_ids"]
    chat_ids = chats_filters_org["chat_ids"]
    assert isinstance(bot_ids, dict)
    assert isinstance(chat_ids, dict)

    response = await client.get(
        "/api/v1/chats",
        headers=filter_op_a_headers,
        params={"bot_id": bot_ids["filter_bot_a"]},
    )
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert chat_ids["a_unread"] in ids
    assert chat_ids["a_read"] in ids
    assert chat_ids["b_other"] not in ids


@pytest.mark.asyncio
async def test_list_chats_filter_unread_only(
    client: AsyncClient,
    db_ready: None,
    chats_filters_org: dict[str, object],
    filter_op_a_headers: dict[str, str],
) -> None:
    chat_ids = chats_filters_org["chat_ids"]
    assert isinstance(chat_ids, dict)

    response = await client.get(
        "/api/v1/chats",
        headers=filter_op_a_headers,
        params={"unread_only": True},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    ids = {item["id"] for item in items}
    assert chat_ids["a_unread"] in ids
    assert chat_ids["a_read"] not in ids
    assert all(item["unread_for_me"] for item in items)


@pytest.mark.asyncio
async def test_list_chats_filter_card_owner_user_id(
    client: AsyncClient,
    db_ready: None,
    chats_filters_org: dict[str, object],
    filter_op_a_headers: dict[str, str],
) -> None:
    user_ids = chats_filters_org["user_ids"]
    chat_ids = chats_filters_org["chat_ids"]
    assert isinstance(user_ids, dict)
    assert isinstance(chat_ids, dict)
    owner_id = user_ids["filter.op.a@crm.local"]

    response = await client.get(
        "/api/v1/chats",
        headers=filter_op_a_headers,
        params={"card_owner_user_id": owner_id},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    ids = {item["id"] for item in items}
    assert chat_ids["a_unread"] in ids
    assert chat_ids["a_read"] in ids
    assert chat_ids["b_other"] not in ids
    assert all(item["card_owner_user_id"] == owner_id for item in items)


@pytest.mark.asyncio
async def test_list_chats_sort_unread_first(
    client: AsyncClient,
    db_ready: None,
    chats_filters_org: dict[str, object],
    filter_op_a_headers: dict[str, str],
) -> None:
    chat_ids = chats_filters_org["chat_ids"]
    assert isinstance(chat_ids, dict)

    response = await client.get(
        "/api/v1/chats",
        headers=filter_op_a_headers,
        params={"sort": "unread_first"},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    group_a_ids = {chat_ids["a_unread"], chat_ids["a_read"]}
    group_a_items = [item for item in items if item["id"] in group_a_ids]
    assert len(group_a_items) >= 2
    assert group_a_items[0]["id"] == chat_ids["a_unread"]
    assert group_a_items[0]["unread_for_me"] is True
    assert group_a_items[1]["unread_for_me"] is False


@pytest.mark.asyncio
async def test_list_chats_filter_bot_id_and_unread_only(
    client: AsyncClient,
    db_ready: None,
    chats_filters_org: dict[str, object],
    filter_op_a_headers: dict[str, str],
) -> None:
    bot_ids = chats_filters_org["bot_ids"]
    chat_ids = chats_filters_org["chat_ids"]
    assert isinstance(bot_ids, dict)
    assert isinstance(chat_ids, dict)

    response = await client.get(
        "/api/v1/chats",
        headers=filter_op_a_headers,
        params={"bot_id": bot_ids["filter_bot_a"], "unread_only": True},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    ids = {item["id"] for item in items}
    assert chat_ids["a_unread"] in ids
    assert chat_ids["a_read"] not in ids
    assert chat_ids["b_other"] not in ids
    assert all(item["bot_id"] == bot_ids["filter_bot_a"] for item in items)
    assert all(item["unread_for_me"] for item in items)


@pytest.mark.asyncio
async def test_list_chats_unread_for_me_uses_read_state_with_messages(
    client: AsyncClient,
    db_ready: None,
    chats_filters_org: dict[str, object],
    filter_op_a_headers: dict[str, str],
    test_settings,
) -> None:
    from sqlalchemy import create_engine, text

    from app.shared.settings import Settings
    from tests.auth.conftest import _sync_database_url

    assert isinstance(test_settings, Settings)
    chat_ids = chats_filters_org["chat_ids"]
    assert isinstance(chat_ids, dict)
    chat_id = int(chat_ids["a_read"])

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            lead_id = conn.execute(
                text("SELECT current_lead_id FROM chats WHERE id = :cid"),
                {"cid": chat_id},
            ).scalar_one()
            conn.execute(
                text(
                    """
                    INSERT INTO messages (chat_id, lead_id, direction, kind, text)
                    VALUES (:cid, :lid, 'inbound', 'text', 'needs read state')
                    """
                ),
                {"cid": chat_id, "lid": lead_id},
            )
    finally:
        engine.dispose()

    response = await client.get(
        "/api/v1/chats",
        headers=filter_op_a_headers,
    )
    assert response.status_code == 200, response.text
    row = next(item for item in response.json()["items"] if item["id"] == chat_id)
    assert "unread_count_user" not in row
    assert row["unread_for_me"] is True

    read_resp = await client.post(
        f"/api/v1/chats/{chat_id}/read",
        headers=filter_op_a_headers,
        json={},
    )
    assert read_resp.status_code == 200

    after_read = await client.get(
        "/api/v1/chats",
        headers=filter_op_a_headers,
    )
    row_after = next(item for item in after_read.json()["items"] if item["id"] == chat_id)
    assert row_after["unread_for_me"] is False


@pytest.mark.asyncio
async def test_list_chats_scope_other_group_not_visible(
    client: AsyncClient,
    db_ready: None,
    chats_filters_org: dict[str, object],
    filter_op_b_headers: dict[str, str],
) -> None:
    chat_ids = chats_filters_org["chat_ids"]
    assert isinstance(chat_ids, dict)

    response = await client.get("/api/v1/chats", headers=filter_op_b_headers)
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert chat_ids["b_other"] in ids
    assert chat_ids["a_unread"] not in ids
    assert chat_ids["a_read"] not in ids
