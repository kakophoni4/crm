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
    transfer_id = req.json()["id"]
    assert req.json()["state"] == "pending_senior"

    approve = await client.post(
        f"/api/v1/contact-transfers/{transfer_id}/approve",
        headers=ownership_senior_headers,
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["state"] == "pending_recipient"

    accept = await client.post(
        f"/api/v1/contact-transfers/{transfer_id}/accept",
        headers=ownership_op2_headers,
    )
    assert accept.status_code == 200, accept.text
    assert accept.json()["state"] == "accepted"

    detail = await client.get(f"/api/v1/contacts/{contact_id}", headers=ownership_op2_headers)
    assert detail.status_code == 200, detail.text
    ownership = detail.json()["group_ownership"]
    row = next(item for item in ownership if item["group_id"] == group_id)
    assert row["owner_user_id"] == op2_id


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
    transfer_id = req.json()["id"]

    await client.post(
        f"/api/v1/contact-transfers/{transfer_id}/approve",
        headers=ownership_senior_headers,
    )
    await client.post(
        f"/api/v1/contact-transfers/{transfer_id}/accept",
        headers=ownership_op2_headers,
    )

    detail = await client.get(f"/api/v1/contacts/{contact_id}", headers=ownership_op1_headers)
    assert detail.status_code == 200
    by_group = {
        item["group_id"]: item["owner_user_id"]
        for item in detail.json()["group_ownership"]
    }
    assert by_group[group_a] == op2_id
    assert by_group[group_b] == op1_id


@pytest.mark.asyncio
async def test_list_contact_transfers_by_state(
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

    await client.post(
        f"/api/v1/contacts/{contact_id}/groups/{group_id}/transfers",
        headers=ownership_op1_headers,
        json={"to_user_id": op2_id},
    )

    senior_inbox = await client.get(
        "/api/v1/contact-transfers",
        headers=ownership_senior_headers,
        params={"state": "pending_senior", "group_id": group_id},
    )
    assert senior_inbox.status_code == 200, senior_inbox.text
    assert any(item["contact_id"] == contact_id for item in senior_inbox.json()["items"])


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
async def test_parallel_transfer_request_one_active_only(
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
    assert statuses.count(201) == 1
    assert statuses.count(409) == 1
