from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, text

from app.modules.chats.timeutil import utc_now
from app.modules.contacts.escalation import scan_pending_escalations
from app.modules.contacts.ownership import ensure_assignment, set_pending_inbound
from app.shared.db import get_session_factory
from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_escalation_notifies_group_after_n_minutes(
    db_ready: None,
    ownership_org: dict[str, object],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])

    session_factory = get_session_factory()
    async with session_factory() as session:
        await ensure_assignment(session, contact_id, group_id)
        await set_pending_inbound(session, contact_id, group_id)
        await session.commit()

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        updated = connection.execute(
            text(
                """
                UPDATE contact_group_assignments
                SET pending_inbound_at = now() - interval '5 minutes',
                    escalated_to_group_at = NULL
                WHERE contact_id = :cid AND group_id = :gid
                RETURNING id
                """
            ),
            {"cid": contact_id, "gid": group_id},
        ).scalar_one()
        assert updated is not None

    with patch("app.modules.contacts.escalation.publish", new_callable=AsyncMock) as mock_publish:
        async with session_factory() as session:
            result = await scan_pending_escalations(session)
            await session.commit()
        assert result.escalated >= 1
        topics = [call.args[0] for call in mock_publish.await_args_list]
        assert "contact.escalation.group_notify" in topics


@pytest.mark.asyncio
async def test_reassign_first_responder(
    db_ready: None,
    ownership_org: dict[str, object],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][0])
    user_ids = ownership_org["user_ids"]
    assert isinstance(user_ids, dict)
    responder_id = user_ids["owner.op2@crm.local"]

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        chat_id = connection.execute(
            text(
                """
                INSERT INTO chats (contact_id, assigned_group_id, assigned_department_id, status)
                VALUES (:cid, :gid, :dept_id, 'open')
                RETURNING id
                """
            ),
            {
                "cid": contact_id,
                "gid": group_id,
                "dept_id": ownership_org["dept_id"],
            },
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO messages (
                    chat_id, direction, kind, text, sender_user_id
                )
                VALUES (:chat_id, 'outbound', 'text', 'first reply', :uid)
                """
            ),
            {"chat_id": chat_id, "uid": responder_id},
        )
    engine.dispose()

    session_factory = get_session_factory()
    async with session_factory() as session:
        await ensure_assignment(session, contact_id, group_id)
        await set_pending_inbound(
            session,
            contact_id,
            group_id,
            at=utc_now() - timedelta(minutes=5),
        )
        await session.execute(
            text(
                """
                UPDATE contact_group_assignments
                SET pending_inbound_at = now() - interval '5 minutes',
                    last_owner_response_at = NULL
                WHERE contact_id = :cid AND group_id = :gid
                """
            ),
            {"cid": contact_id, "gid": group_id},
        )
        await session.commit()

    with patch("app.modules.contacts.escalation.publish", new_callable=AsyncMock):
        async with session_factory() as session:
            result = await scan_pending_escalations(session)
            await session.commit()
        assert result.reassigned >= 1

    async with session_factory() as session:
        from app.modules.contacts.ownership import get_owner

        owner = await get_owner(session, contact_id, group_id)
        assert owner == responder_id


@pytest.mark.asyncio
async def test_escalation_does_not_re_escalate(
    db_ready: None,
    ownership_org: dict[str, object],
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][1])

    session_factory = get_session_factory()
    async with session_factory() as session:
        await ensure_assignment(session, contact_id, group_id)
        await session.execute(
            text(
                """
                UPDATE contact_group_assignments
                SET pending_inbound_at = now() - interval '5 minutes',
                    escalated_to_group_at = now() - interval '4 minutes'
                WHERE contact_id = :cid AND group_id = :gid
                """
            ),
            {"cid": contact_id, "gid": group_id},
        )
        await session.commit()

    with patch("app.modules.contacts.escalation.publish", new_callable=AsyncMock) as mock_publish:
        async with session_factory() as session:
            await scan_pending_escalations(session)
            await session.commit()
        group_topic = "contact.escalation.group_notify"
        group_notifies = [
            c for c in mock_publish.await_args_list if c.args[0] == group_topic
        ]
        assert len(group_notifies) == 0


@pytest.mark.asyncio
async def test_inbound_sets_pending_inbound_at(
    db_ready: None,
    ownership_org: dict[str, object],
    test_settings: Settings,
) -> None:
    group_id = int(ownership_org["group_id"])
    contact_id = int(ownership_org["contact_ids"][2])

    session_factory = get_session_factory()
    async with session_factory() as session:
        from app.modules.bots.ownership_bridge import handle_inbound_ownership

        await handle_inbound_ownership(
            session,
            contact_id=contact_id,
            group_id=group_id,
            chat_id=1,
        )
        await session.commit()

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.connect() as connection:
        pending = connection.execute(
            text(
                """
                SELECT pending_inbound_at IS NOT NULL
                FROM contact_group_assignments
                WHERE contact_id = :cid AND group_id = :gid
                """
            ),
            {"cid": contact_id, "gid": group_id},
        ).scalar_one()
    engine.dispose()
    assert pending is True
