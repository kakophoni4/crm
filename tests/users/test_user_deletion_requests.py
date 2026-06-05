from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.modules.contacts.ownership import ASSIGNMENT_MANUAL_TRANSFER
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_operator_cannot_request_user_deletion(
    client: AsyncClient,
    operator_a_headers: dict[str, str],
    chats_org: dict[str, object],
    db_ready: None,
) -> None:
    user_ids = chats_org["user_ids"]
    assert isinstance(user_ids, dict)
    op_b = int(user_ids["operator.chats.b@crm.local"])
    response = await client.post(
        f"/api/v1/users/{op_b}/deletion-request",
        headers=operator_a_headers,
        json={},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_senior_other_department_gets_404_for_deletion_request(
    client: AsyncClient,
    senior_other_headers: dict[str, str],
    chats_org: dict[str, object],
    db_ready: None,
) -> None:
    user_ids = chats_org["user_ids"]
    op_a = int(user_ids["operator.chats.a@crm.local"])
    response = await client.post(
        f"/api/v1/users/{op_a}/deletion-request",
        headers=senior_other_headers,
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_approve_reassigns_cards_and_disables_user(
    client: AsyncClient,
    senior_headers: dict[str, str],
    admin_headers: dict[str, str],
    chats_org: dict[str, object],
    test_settings: object,
    db_ready: None,
) -> None:
    from app.shared.settings import Settings

    assert isinstance(test_settings, Settings)
    user_ids = chats_org["user_ids"]
    group_a = int(chats_org["group_a"])
    contact_a = int(chats_org["contact_ids"]["a"])
    op_a = int(user_ids["operator.chats.a@crm.local"])
    op_b = int(user_ids["operator.chats.b@crm.local"])

    sync_url = _sync_database_url(test_settings.database_url)
    engine = create_engine(sync_url)
    request_id: int | None = None
    try:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM user_deletion_requests WHERE target_user_id = :uid"),
                {"uid": op_a},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO contact_group_assignments (
                        contact_id, group_id, owner_user_id, assignment_source
                    )
                    VALUES (:cid, :gid, :oid, :src)
                    ON CONFLICT (contact_id, group_id) DO UPDATE SET
                        owner_user_id = EXCLUDED.owner_user_id,
                        assignment_source = EXCLUDED.assignment_source
                    """
                ),
                {
                    "cid": contact_a,
                    "gid": group_a,
                    "oid": op_a,
                    "src": ASSIGNMENT_MANUAL_TRANSFER,
                },
            )

        create = await client.post(
            f"/api/v1/users/{op_a}/deletion-request",
            headers=senior_headers,
            json={"comment": "leave queue"},
        )
        assert create.status_code == 201, create.text
        request_id = int(create.json()["id"])
        assert create.json()["state"] == "pending"

        senior_list = await client.get("/api/v1/user-deletion-requests", headers=senior_headers)
        assert senior_list.status_code == 200
        senior_ids = {int(x["id"]) for x in senior_list.json()["items"]}
        assert request_id in senior_ids

        approve = await client.post(
            f"/api/v1/user-deletion-requests/{request_id}/approve",
            headers=admin_headers,
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["state"] == "approved"

        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT status FROM users WHERE id = :id"),
                {"id": op_a},
            ).one()
            assert str(row[0]) == "disabled"

            owner = connection.execute(
                text(
                    """
                    SELECT owner_user_id
                    FROM contact_group_assignments
                    WHERE contact_id = :c AND group_id = :g
                    """
                ),
                {"c": contact_a, "g": group_a},
            ).scalar_one()
            assert int(owner) == op_b
    finally:
        if request_id is not None:
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM user_deletion_requests WHERE id = :id"),
                    {"id": request_id},
                )
                connection.execute(
                    text(
                        """
                        UPDATE users
                        SET status = 'active', group_id = :gid
                        WHERE id = :id
                        """
                    ),
                    {"gid": group_a, "id": op_a},
                )
                connection.execute(
                    text(
                        """
                        UPDATE contact_group_assignments
                        SET owner_user_id = :oid,
                            assignment_source = :src
                        WHERE contact_id = :c AND group_id = :g
                        """
                    ),
                    {
                        "oid": op_a,
                        "src": ASSIGNMENT_MANUAL_TRANSFER,
                        "c": contact_a,
                        "g": group_a,
                    },
                )
        engine.dispose()


@pytest.mark.asyncio
async def test_admin_reject_deletion_request(
    client: AsyncClient,
    senior_headers: dict[str, str],
    admin_headers: dict[str, str],
    chats_org: dict[str, object],
    test_settings: object,
    db_ready: None,
) -> None:
    from app.shared.settings import Settings

    assert isinstance(test_settings, Settings)
    user_ids = chats_org["user_ids"]
    op_b = int(user_ids["operator.chats.b@crm.local"])

    sync_url = _sync_database_url(test_settings.database_url)
    engine = create_engine(sync_url)
    request_id: int | None = None
    try:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM user_deletion_requests WHERE target_user_id = :uid"),
                {"uid": op_b},
            )

        create = await client.post(
            f"/api/v1/users/{op_b}/deletion-request",
            headers=senior_headers,
            json={},
        )
        assert create.status_code == 201, create.text
        request_id = int(create.json()["id"])

        reject = await client.post(
            f"/api/v1/user-deletion-requests/{request_id}/reject",
            headers=admin_headers,
            json={"admin_comment": "no"},
        )
        assert reject.status_code == 200, reject.text
        assert reject.json()["state"] == "rejected"
        assert reject.json()["admin_comment"] == "no"

        with engine.begin() as connection:
            st = connection.execute(
                text("SELECT status FROM users WHERE id = :id"),
                {"id": op_b},
            ).scalar_one()
            assert str(st) == "active"
    finally:
        if request_id is not None:
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM user_deletion_requests WHERE id = :id"),
                    {"id": request_id},
                )
        engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_pending_returns_409(
    client: AsyncClient,
    senior_headers: dict[str, str],
    chats_org: dict[str, object],
    test_settings: object,
    db_ready: None,
) -> None:
    from app.shared.settings import Settings

    assert isinstance(test_settings, Settings)
    user_ids = chats_org["user_ids"]
    op_b = int(user_ids["operator.chats.b@crm.local"])

    sync_url = _sync_database_url(test_settings.database_url)
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM user_deletion_requests WHERE target_user_id = :uid"),
            {"uid": op_b},
        )
    engine.dispose()

    first = await client.post(
        f"/api/v1/users/{op_b}/deletion-request",
        headers=senior_headers,
        json={},
    )
    assert first.status_code == 201, first.text
    rid = int(first.json()["id"])

    second = await client.post(
        f"/api/v1/users/{op_b}/deletion-request",
        headers=senior_headers,
        json={},
    )
    assert second.status_code == 409

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM user_deletion_requests WHERE id = :id"), {"id": rid})
    engine.dispose()
