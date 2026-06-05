from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, text

from app.modules.chats.timeutil import utc_now
from app.modules.contacts.escalation import scan_pending_escalations
from app.modules.contacts.ownership import ensure_assignment, get_owner, set_pending_inbound
from app.shared.db import get_session_factory
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_random_available_reassign(
    db_ready: None,
    ownership_org: dict[str, object],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][3])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE group_escalation_settings
                SET new_contact_reassign_strategy = 'random_available',
                    first_response_timeout_minutes = 1
                WHERE group_id = :gid
                """
            ),
            {"gid": group_id},
        )
    engine.dispose()

    session_factory = get_session_factory()
    async with session_factory() as session:
        first = await ensure_assignment(session, contact_id, group_id)
        await session.commit()
        old_owner = first.owner_user_id

    async with session_factory() as session:
        await set_pending_inbound(
            session,
            contact_id,
            group_id,
            at=utc_now() - timedelta(minutes=5),
        )
        await session.commit()

    with patch("app.modules.contacts.escalation.publish", new_callable=AsyncMock):
        async with session_factory() as session:
            await scan_pending_escalations(session)
            await session.commit()

    async with session_factory() as session:
        new_owner = await get_owner(session, contact_id, group_id)
        assert new_owner is not None
        assert new_owner != old_owner
        assert new_owner in {
            user_ids["owner.op1@crm.local"],
            user_ids["owner.op2@crm.local"],
        }
