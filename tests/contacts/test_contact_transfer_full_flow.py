from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


async def _ensure_owner(
    test_settings: Settings,
    contact_id: int,
    group_id: int,
    owner_id: int,
) -> None:
    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO contact_group_assignments (
                    contact_id, group_id, owner_user_id, assignment_source
                )
                VALUES (:cid, :gid, :owner, 'auto_round_robin')
                ON CONFLICT (contact_id, group_id) DO UPDATE
                SET owner_user_id = EXCLUDED.owner_user_id
                """
            ),
            {"cid": contact_id, "gid": group_id, "owner": owner_id},
        )
    engine.dispose()


@pytest.mark.asyncio
async def test_contact_transfer_full_flow(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_op1_headers: dict[str, str],
    ownership_op2_headers: dict[str, str],
    ownership_senior_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op1_id = user_ids["owner.op1@crm.local"]
    op2_id = user_ids["owner.op2@crm.local"]

    await _ensure_owner(test_settings, contact_id, group_id, op1_id)

    req = await client.post(
        f"/api/v1/contacts/{contact_id}/groups/{group_id}/transfers",
        headers=ownership_op1_headers,
        json={"to_user_id": op2_id, "comment": "vacation handoff"},
    )
    assert req.status_code == 201, req.text
    assert req.json()["state"] == "accepted"

    detail = await client.get(f"/api/v1/contacts/{contact_id}", headers=ownership_op2_headers)
    assert detail.status_code == 200, detail.text
    ownership = detail.json()["group_ownership"]
    row = next(item for item in ownership if item["group_id"] == group_id)
    assert row["owner_user_id"] == op2_id


@pytest.mark.asyncio
async def test_senior_force_assigns_card_to_self(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_senior_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op1_id = user_ids["owner.op1@crm.local"]
    senior_id = user_ids["owner.senior@crm.local"]

    await _ensure_owner(test_settings, contact_id, group_id, op1_id)

    response = await client.post(
        f"/api/v1/contacts/{contact_id}/groups/{group_id}/transfers",
        headers=ownership_senior_headers,
        json={"to_user_id": senior_id, "force": True},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "accepted"
    assert body["to_user_id"] == senior_id

    detail = await client.get(f"/api/v1/contacts/{contact_id}", headers=ownership_senior_headers)
    assert detail.status_code == 200, detail.text
    ownership = detail.json()["group_ownership"]
    row = next(item for item in ownership if item["group_id"] == group_id)
    assert row["owner_user_id"] == senior_id


@pytest.mark.asyncio
async def test_senior_force_assigns_card_in_group(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_senior_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op1_id = user_ids["owner.op1@crm.local"]
    op2_id = user_ids["owner.op2@crm.local"]

    await _ensure_owner(test_settings, contact_id, group_id, op1_id)

    response = await client.post(
        f"/api/v1/contacts/{contact_id}/groups/{group_id}/transfers",
        headers=ownership_senior_headers,
        json={"to_user_id": op2_id, "force": True, "comment": "rebalance"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "accepted"
    assert body["force_assigned"] is True
    assert body["from_user_id"] == op1_id
    assert body["to_user_id"] == op2_id

    detail = await client.get(f"/api/v1/contacts/{contact_id}", headers=ownership_senior_headers)
    assert detail.status_code == 200, detail.text
    ownership = detail.json()["group_ownership"]
    row = next(item for item in ownership if item["group_id"] == group_id)
    assert row["owner_user_id"] == op2_id


@pytest.mark.asyncio
async def test_senior_force_moves_bot_card_between_assigned_groups(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_senior_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    dept_id = int(ownership_org["dept_id"])
    source_group_id = int(ownership_org["group_id"])
    target_group_id = int(ownership_org["group_b_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    source_owner_id = int(user_ids["owner.op1@crm.local"])

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        password_hash = connection.execute(
            text("SELECT password_hash FROM users WHERE id = :uid"),
            {"uid": source_owner_id},
        ).scalar_one()
        target_user_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        email, username, password_hash, full_name, role,
                        group_id, department_id, availability, presence, status
                    )
                    VALUES (
                        'owner.groupb@crm.local', 'owner.groupb', :password_hash,
                        'owner.groupb', 'user', :target_gid, :dept_id,
                        'available', 'online', 'active'
                    )
                    ON CONFLICT (email) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        group_id = EXCLUDED.group_id,
                        department_id = EXCLUDED.department_id,
                        availability = EXCLUDED.availability,
                        presence = EXCLUDED.presence,
                        status = EXCLUDED.status
                    RETURNING id
                    """
                ),
                {
                    "password_hash": password_hash,
                    "target_gid": target_group_id,
                    "dept_id": dept_id,
                },
            ).scalar_one()
        )
        bot_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO bots (
                        code, name, channel, owner_type, owner_id, department_id,
                        inbound_secret_encrypted, outbound_secret_encrypted, outbound_url
                    )
                    VALUES (
                        'transfer_same_bot', 'Transfer Same Bot', 'telegram',
                        'department', :dept_id, :dept_id, '\\x01', '\\x02',
                        'https://example.com/out'
                    )
                    ON CONFLICT (code) DO UPDATE SET
                        department_id = EXCLUDED.department_id,
                        owner_id = EXCLUDED.owner_id
                    RETURNING id
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()
        )
        connection.execute(
            text("DELETE FROM bot_group_assignments WHERE bot_id = :bid"),
            {"bid": bot_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO bot_group_assignments (bot_id, group_id)
                VALUES (:bid, :source_gid), (:bid, :target_gid)
                """
            ),
            {
                "bid": bot_id,
                "source_gid": source_group_id,
                "target_gid": target_group_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO contact_group_assignments (
                    contact_id, group_id, owner_user_id, assignment_source
                )
                VALUES (:cid, :gid, :owner, 'auto_round_robin')
                ON CONFLICT (contact_id, group_id) DO UPDATE
                SET owner_user_id = EXCLUDED.owner_user_id
                """
            ),
            {
                "cid": contact_id,
                "gid": source_group_id,
                "owner": source_owner_id,
            },
        )
        status_id = int(
            connection.execute(
                text("SELECT id FROM statuses WHERE code = 'new' AND kind = 'lead_pipeline'"),
            ).scalar_one()
        )
        chat_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO chats (
                        contact_id, bot_id, assigned_group_id, assigned_department_id, status
                    )
                    VALUES (:cid, :bid, :gid, :did, 'open')
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_id,
                    "bid": bot_id,
                    "gid": source_group_id,
                    "did": dept_id,
                },
            ).scalar_one()
        )
        lead_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO leads (contact_id, group_id, bot_id, chat_id, status_id, title)
                    VALUES (:cid, :gid, :bid, :chat_id, :status_id, 'Transfer lead')
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_id,
                    "gid": source_group_id,
                    "bid": bot_id,
                    "chat_id": chat_id,
                    "status_id": status_id,
                },
            ).scalar_one()
        )
        connection.execute(
            text("UPDATE chats SET current_lead_id = :lead_id WHERE id = :chat_id"),
            {"lead_id": lead_id, "chat_id": chat_id},
        )
    engine.dispose()

    response = await client.post(
        f"/api/v1/contacts/{contact_id}/groups/{source_group_id}/transfers",
        headers=ownership_senior_headers,
        json={
            "to_user_id": target_user_id,
            "target_group_id": target_group_id,
            "force": True,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "accepted"
    assert body["group_id"] == target_group_id
    assert body["to_user_id"] == target_user_id

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT c.assigned_group_id, c.assigned_department_id, l.group_id,
                       cga.owner_user_id
                FROM chats c
                JOIN leads l ON l.id = c.current_lead_id
                JOIN contact_group_assignments cga
                  ON cga.contact_id = c.contact_id
                 AND cga.group_id = :target_gid
                WHERE c.id = :chat_id
                """
            ),
            {"chat_id": chat_id, "target_gid": target_group_id},
        ).one()
    engine.dispose()

    assert int(row[0]) == target_group_id
    assert int(row[1]) == dept_id
    assert int(row[2]) == target_group_id
    assert int(row[3]) == target_user_id


@pytest.mark.asyncio
async def test_cross_group_transfer_rejects_group_not_assigned_to_chat_bot(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_senior_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    dept_id = int(ownership_org["dept_id"])
    source_group_id = int(ownership_org["group_id"])
    target_group_id = int(ownership_org["group_b_id"])
    contact_id = int(ownership_org["contact_ids"][1])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    source_owner_id = int(user_ids["owner.op2@crm.local"])

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        password_hash = connection.execute(
            text("SELECT password_hash FROM users WHERE id = :uid"),
            {"uid": source_owner_id},
        ).scalar_one()
        target_user_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        email, username, password_hash, full_name, role,
                        group_id, department_id, availability, presence, status
                    )
                    VALUES (
                        'owner.groupb.blocked@crm.local', 'owner.groupb.blocked',
                        :password_hash, 'owner.groupb.blocked', 'user',
                        :target_gid, :dept_id, 'available', 'online', 'active'
                    )
                    ON CONFLICT (email) DO UPDATE SET
                        group_id = EXCLUDED.group_id,
                        department_id = EXCLUDED.department_id,
                        status = EXCLUDED.status
                    RETURNING id
                    """
                ),
                {
                    "password_hash": password_hash,
                    "target_gid": target_group_id,
                    "dept_id": dept_id,
                },
            ).scalar_one()
        )
        bot_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO bots (
                        code, name, channel, owner_type, owner_id, department_id,
                        inbound_secret_encrypted, outbound_secret_encrypted, outbound_url
                    )
                    VALUES (
                        'transfer_source_only_bot', 'Transfer Source Only Bot',
                        'telegram', 'department', :dept_id, :dept_id,
                        '\\x01', '\\x02', 'https://example.com/out'
                    )
                    ON CONFLICT (code) DO UPDATE SET
                        department_id = EXCLUDED.department_id,
                        owner_id = EXCLUDED.owner_id
                    RETURNING id
                    """
                ),
                {"dept_id": dept_id},
            ).scalar_one()
        )
        connection.execute(
            text("DELETE FROM bot_group_assignments WHERE bot_id = :bid"),
            {"bid": bot_id},
        )
        connection.execute(
            text(
                "INSERT INTO bot_group_assignments (bot_id, group_id) VALUES (:bid, :gid)"
            ),
            {"bid": bot_id, "gid": source_group_id},
        )
        chat_id = int(
            connection.execute(
                text(
                    """
                    INSERT INTO chats (
                        contact_id, bot_id, assigned_group_id, assigned_department_id, status
                    )
                    VALUES (:cid, :bid, :gid, :did, 'open')
                    RETURNING id
                    """
                ),
                {
                    "cid": contact_id,
                    "bid": bot_id,
                    "gid": source_group_id,
                    "did": dept_id,
                },
            ).scalar_one()
        )
    engine.dispose()

    await _ensure_owner(test_settings, contact_id, source_group_id, source_owner_id)

    response = await client.post(
        f"/api/v1/contacts/{contact_id}/groups/{source_group_id}/transfers",
        headers=ownership_senior_headers,
        json={
            "to_user_id": target_user_id,
            "target_group_id": target_group_id,
            "force": True,
        },
    )
    assert response.status_code == 422, response.text

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.connect() as connection:
        group_id = connection.execute(
            text("SELECT assigned_group_id FROM chats WHERE id = :chat_id"),
            {"chat_id": chat_id},
        ).scalar_one()
    engine.dispose()
    assert int(group_id) == source_group_id


@pytest.mark.asyncio
async def test_non_owner_cannot_request_transfer(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_op1_headers: dict[str, str],
    ownership_op2_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op1_id = user_ids["owner.op1@crm.local"]

    await _ensure_owner(test_settings, contact_id, group_id, op1_id)

    response = await client.post(
        f"/api/v1/contacts/{contact_id}/groups/{group_id}/transfers",
        headers=ownership_op2_headers,
        json={"to_user_id": op1_id},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_contact_transfer_does_not_affect_other_group(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_op1_headers: dict[str, str],
    ownership_op2_headers: dict[str, str],
    ownership_senior_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    group_a = int(ownership_org["group_id"])
    group_b = int(ownership_org["group_b_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op1_id = user_ids["owner.op1@crm.local"]
    op2_id = user_ids["owner.op2@crm.local"]

    await _ensure_owner(test_settings, contact_id, group_a, op1_id)
    await _ensure_owner(test_settings, contact_id, group_b, op1_id)

    req = await client.post(
        f"/api/v1/contacts/{contact_id}/groups/{group_a}/transfers",
        headers=ownership_op1_headers,
        json={"to_user_id": op2_id},
    )
    assert req.status_code == 201, req.text
    assert req.json()["state"] == "accepted"

    detail = await client.get(f"/api/v1/contacts/{contact_id}", headers=ownership_op1_headers)
    assert detail.status_code == 200
    by_group = {
        item["group_id"]: item["owner_user_id"]
        for item in detail.json()["group_ownership"]
    }
    assert by_group[group_a] == op2_id
    assert by_group[group_b] == op1_id


@pytest.mark.asyncio
async def test_list_contact_transfers_includes_completed_transfer(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_op1_headers: dict[str, str],
    ownership_senior_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][1])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op1_id = user_ids["owner.op1@crm.local"]
    op2_id = user_ids["owner.op2@crm.local"]

    await _ensure_owner(test_settings, contact_id, group_id, op1_id)

    created = await client.post(
        f"/api/v1/contacts/{contact_id}/groups/{group_id}/transfers",
        headers=ownership_op1_headers,
        json={"to_user_id": op2_id},
    )
    assert created.status_code == 201, created.text
    transfer_id = created.json()["id"]

    senior_inbox = await client.get(
        "/api/v1/contact-transfers",
        headers=ownership_senior_headers,
        params={"state": "pending_senior", "group_id": group_id},
    )
    assert senior_inbox.status_code == 200, senior_inbox.text
    assert not any(item["id"] == transfer_id for item in senior_inbox.json()["items"])

    completed = await client.get(
        "/api/v1/contact-transfers",
        headers=ownership_senior_headers,
        params={"state": "accepted", "group_id": group_id},
    )
    assert completed.status_code == 200, completed.text
    items = completed.json()["items"]
    matched = next(item for item in items if item["id"] == transfer_id)
    assert matched["contact_id"] == contact_id
    assert matched.get("contact_name")
    assert matched.get("group_name")
    assert matched.get("from_user_name")
    assert matched.get("to_user_name")


@pytest.mark.asyncio
async def test_legacy_chat_transfer_routes_removed(
    client: AsyncClient,
    db_ready: None,
    ownership_op1_headers: dict[str, str],
) -> None:
    for path, body in (
        ("/api/v1/chats/1/transfer/request", {"to_user_id": 2, "reason": "handoff"}),
        ("/api/v1/chats/1/transfers", {"to_user_id": 2}),
        ("/api/v1/chats/transfers/1/approve", None),
    ):
        response = await client.post(
            path,
            headers=ownership_op1_headers,
            json=body,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_parallel_transfer_requests_both_succeed(
    client: AsyncClient,
    db_ready: None,
    ownership_org: dict[str, object],
    ownership_op1_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][2])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op1_id = user_ids["owner.op1@crm.local"]
    op2_id = user_ids["owner.op2@crm.local"]

    await _ensure_owner(test_settings, contact_id, group_id, op1_id)

    async def _request_transfer() -> int:
        response = await client.post(
            f"/api/v1/contacts/{contact_id}/groups/{group_id}/transfers",
            headers=ownership_op1_headers,
            json={"to_user_id": op2_id},
        )
        return response.status_code

    statuses = await asyncio.gather(_request_transfer(), _request_transfer())
    assert statuses.count(201) == 2
