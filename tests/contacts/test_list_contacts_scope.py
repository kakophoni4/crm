from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url
from tests.contacts.conftest_ownership import _login_ownership


@pytest.mark.asyncio
async def test_operator_sees_contact_via_group_assignment(
    client: AsyncClient,
    ownership_org: dict[str, object],
    test_settings: Settings,
    db_ready: None,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    emails = ownership_org["emails"]
    assert isinstance(emails, dict)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO contact_group_assignments (
                    contact_id, group_id, owner_user_id, assignment_source
                )
                VALUES (:cid, :gid, :owner, 'auto_round_robin')
                ON CONFLICT (contact_id, group_id) DO NOTHING
                """
            ),
            {
                "cid": contact_id,
                "gid": group_id,
                "owner": ownership_org["user_ids"]["owner.op2@crm.local"],
            },
        )
    engine.dispose()

    token = await _login_ownership(client, str(emails["op1"]), str(ownership_org["password"]))
    response = await client.get(
        "/api/v1/contacts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["items"]}
    assert contact_id in ids
