from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.modules.contacts.ownership import ensure_assignment, get_owner, reassign_owner
from app.shared.db import get_session_factory
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_transfer_does_not_affect_other_group(
    db_ready: None,
    ownership_org: dict[str, object],
    test_settings: Settings,
) -> None:
    group_a = int(ownership_org["group_id"])
    group_b = int(ownership_org["group_b_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    owner_a = user_ids["owner.op1@crm.local"]
    owner_b = user_ids["owner.op2@crm.local"]

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
            {"cid": contact_id, "gid": group_b, "owner": owner_a},
        )
    engine.dispose()

    session_factory = get_session_factory()
    async with session_factory() as session:
        await ensure_assignment(session, contact_id, group_a)
        await reassign_owner(
            session,
            contact_id,
            group_a,
            owner_b,
            source="manual_transfer",
        )
        await session.commit()

    async with session_factory() as session:
        assert await get_owner(session, contact_id, group_a) == owner_b
        other_owner = await get_owner(session, contact_id, group_b)
        assert other_owner == owner_a
        assert other_owner != owner_b


@pytest.mark.asyncio
async def test_owner_reply_clears_pending(
    db_ready: None,
    ownership_org: dict[str, object],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await ensure_assignment(session, contact_id, group_id)
        await session.commit()
        owner_id = int(result.owner_user_id)

    async with session_factory() as session:
        from app.modules.contacts.ownership import record_owner_outbound, set_pending_inbound

        await set_pending_inbound(session, contact_id, group_id)
        await record_owner_outbound(session, contact_id, group_id, owner_id)
        await session.commit()

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT pending_inbound_at, last_owner_response_at IS NOT NULL
                FROM contact_group_assignments
                WHERE contact_id = :cid AND group_id = :gid
                """
            ),
            {"cid": contact_id, "gid": group_id},
        ).one()
    engine.dispose()
    assert row[0] is None
    assert row[1] is True
