from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.contacts.test_contact_transfer_full_flow import _ensure_owner


@pytest.mark.asyncio
async def test_approve_transfer_wrong_version_returns_409(
    client: AsyncClient,
    ownership_org: dict[str, object],
    ownership_senior_headers: dict[str, str],
    test_settings: Settings,
    db_ready: None,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    op1_id = user_ids["owner.op1@crm.local"]
    op2_id = user_ids["owner.op2@crm.local"]

    await _ensure_owner(test_settings, contact_id, group_id, op1_id)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        transfer_id = connection.execute(
            text(
                """
                INSERT INTO contact_group_transfers (
                    contact_id, group_id, from_user_id, to_user_id, requested_by,
                    state, expires_at, version, created_at, updated_at
                )
                VALUES (
                    :cid, :gid, :from_uid, :to_uid, :from_uid,
                    'pending_senior', now() + interval '7 days', 1, now(), now()
                )
                RETURNING id
                """
            ),
            {
                "cid": contact_id,
                "gid": group_id,
                "from_uid": op1_id,
                "to_uid": op2_id,
            },
        ).scalar_one()
    engine.dispose()

    response = await client.post(
        f"/api/v1/contact-transfers/{transfer_id}/approve",
        headers=ownership_senior_headers,
        params={"expected_version": 999},
    )
    assert response.status_code == 409
