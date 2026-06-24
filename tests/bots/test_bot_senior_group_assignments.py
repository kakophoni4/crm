from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_senior_assigns_bot_to_groups(
    client: AsyncClient,
    db_ready: None,
    senior_headers: dict[str, str],
    bots_org: dict[str, object],
    admin_headers: dict[str, str],
) -> None:
    dept_id = bots_org["dept_id"]
    group_id = bots_org["group_id"]
    create = await client.post(
        "/api/v1/bots",
        headers=admin_headers,
        json={
            "code": "dept_pool_bot",
            "name": "Dept Pool Bot",
            "department_id": dept_id,
            "outbound_url": "https://example.com/cmd",
            "inbound_secret": "a" * 32,
            "outbound_secret": "b" * 32,
        },
    )
    assert create.status_code == 201, create.text
    bot_id = create.json()["id"]

    response = await client.put(
        f"/api/v1/bots/{bot_id}/group-assignments",
        headers=senior_headers,
        json={"group_ids": [group_id]},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["assigned_group_ids"] == [group_id]
    assert group_id in data["assigned_group_ids"]
    assert "→" in data["owner_label"]

    clear = await client.put(
        f"/api/v1/bots/{bot_id}/group-assignments",
        headers=senior_headers,
        json={"group_ids": []},
    )
    assert clear.status_code == 200, clear.text
    assert clear.json()["assigned_group_ids"] == []


@pytest.mark.asyncio
async def test_bot_group_change_updates_existing_chats(
    client: AsyncClient,
    db_ready: None,
    senior_headers: dict[str, str],
    bots_org: dict[str, object],
    admin_headers: dict[str, str],
    test_settings,
) -> None:
    dept_id = bots_org["dept_id"]
    old_group_id = bots_org["group_id"]
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Bots Test Group B', :dept_id)
                    ON CONFLICT (department_id, name) DO NOTHING
                    """
                ),
                {"dept_id": dept_id},
            )
            new_group_id = connection.execute(
                text(
                    """
                    SELECT id FROM groups
                    WHERE department_id = :dept_id AND name = 'Bots Test Group B'
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO contacts (telegram_user_id, full_name, created_by)
                    VALUES (999002, 'Bot Move Contact', 1)
                    ON CONFLICT (telegram_user_id) DO NOTHING
                    """
                ),
            )
            contact_id = connection.execute(
                text("SELECT id FROM contacts WHERE telegram_user_id = 999002"),
            ).scalar_one()
    finally:
        engine.dispose()

    create = await client.post(
        "/api/v1/bots",
        headers=admin_headers,
        json={
            "code": "move_sync_bot",
            "name": "Move Sync Bot",
            "department_id": dept_id,
            "outbound_url": "https://example.com/cmd",
            "inbound_secret": "a" * 32,
            "outbound_secret": "b" * 32,
        },
    )
    assert create.status_code == 201, create.text
    bot_id = create.json()["id"]

    await client.put(
        f"/api/v1/bots/{bot_id}/group-assignments",
        headers=senior_headers,
        json={"group_ids": [old_group_id]},
    )

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO chats (
                        contact_id, bot_id, assigned_group_id, assigned_department_id, status
                    )
                    VALUES (:cid, :bid, :gid, :did, 'open')
                    """
                ),
                {
                    "cid": contact_id,
                    "bid": bot_id,
                    "gid": old_group_id,
                    "did": dept_id,
                },
            )
    finally:
        engine.dispose()

    moved = await client.put(
        f"/api/v1/bots/{bot_id}/group-assignments",
        headers=senior_headers,
        json={"group_ids": [new_group_id]},
    )
    assert moved.status_code == 200, moved.text

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT assigned_group_id FROM chats
                    WHERE bot_id = :bid AND contact_id = :cid
                    """
                ),
                {"bid": bot_id, "cid": contact_id},
            ).one()
            assert int(row[0]) == int(new_group_id)
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_bot_group_change_distributes_unassigned_chats_to_multiple_groups(
    client: AsyncClient,
    db_ready: None,
    senior_headers: dict[str, str],
    bots_org: dict[str, object],
    admin_headers: dict[str, str],
    test_settings,
) -> None:
    dept_id = int(bots_org["dept_id"])
    group_a_id = int(bots_org["group_id"])
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO groups (name, department_id)
                    VALUES ('Bots Test Group C', :dept_id)
                    ON CONFLICT (department_id, name) DO NOTHING
                    """
                ),
                {"dept_id": dept_id},
            )
            group_b_id = int(
                connection.execute(
                    text(
                        """
                        SELECT id FROM groups
                        WHERE department_id = :dept_id AND name = 'Bots Test Group C'
                        """
                    ),
                    {"dept_id": dept_id},
                ).scalar_one()
            )
            contact_id = int(
                connection.execute(
                    text(
                        """
                        INSERT INTO contacts (telegram_user_id, full_name, created_by)
                        VALUES (999004, 'Bot Multi Group Contact', 1)
                        ON CONFLICT (telegram_user_id) DO UPDATE SET full_name = EXCLUDED.full_name
                        RETURNING id
                        """
                    ),
                ).scalar_one()
            )
    finally:
        engine.dispose()

    create = await client.post(
        "/api/v1/bots",
        headers=admin_headers,
        json={
            "code": "multi_group_sync_bot",
            "name": "Multi Group Sync Bot",
            "department_id": dept_id,
            "outbound_url": "https://example.com/cmd",
            "inbound_secret": "a" * 32,
            "outbound_secret": "b" * 32,
        },
    )
    assert create.status_code == 201, create.text
    bot_id = int(create.json()["id"])

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO chats (
                        contact_id, bot_id, assigned_group_id, assigned_department_id, status
                    )
                    VALUES (:cid, :bid, NULL, :did, 'open')
                    """
                ),
                {"cid": contact_id, "bid": bot_id, "did": dept_id},
            )
    finally:
        engine.dispose()

    assigned = await client.put(
        f"/api/v1/bots/{bot_id}/group-assignments",
        headers=senior_headers,
        json={"group_ids": [group_a_id, group_b_id]},
    )
    assert assigned.status_code == 200, assigned.text

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as connection:
            group_id = connection.execute(
                text(
                    """
                    SELECT assigned_group_id FROM chats
                    WHERE bot_id = :bid AND contact_id = :cid
                    """
                ),
                {"bid": bot_id, "cid": contact_id},
            ).scalar_one()
    finally:
        engine.dispose()

    assert int(group_id) in {group_a_id, group_b_id}
