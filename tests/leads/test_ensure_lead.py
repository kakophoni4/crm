from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.chats_bridge import insert_inbound_message
from app.modules.db.models.enums import ChatStatus, StatusKind
from app.modules.db.models.user import User
from app.modules.leads.repository import LeadRepository
from app.modules.leads.service import LeadService
from app.shared.db import get_session_factory


async def _ensure(
    session: AsyncSession,
    org: dict[str, int],
) -> int:
    lead = await LeadService(session).ensure_open_lead(
        contact_id=org["contact_id"],
        group_id=org["group_id"],
        bot_id=org["bot_id"],
        chat_id=org["chat_id"],
    )
    await session.commit()
    return lead.id


@pytest.mark.asyncio
async def test_first_inbound_creates_one_lead(
    leads_org: dict[str, int],
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        lead_id = await _ensure(session, leads_org)

        count = await session.scalar(
            text(
                """
                SELECT COUNT(*) FROM leads
                WHERE contact_id = :cid AND group_id = :gid AND closed_at IS NULL
                """
            ),
            {"cid": leads_org["contact_id"], "gid": leads_org["group_id"]},
        )
        current = await session.scalar(
            text("SELECT current_lead_id FROM chats WHERE id = :cid"),
            {"cid": leads_org["chat_id"]},
        )
    assert count == 1
    assert current == lead_id


@pytest.mark.asyncio
async def test_second_inbound_reuses_open_lead(
    leads_org: dict[str, int],
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        first_id = await _ensure(session, leads_org)
        second_id = await _ensure(session, leads_org)
    assert first_id == second_id


@pytest.mark.asyncio
async def test_other_bot_same_group_gets_own_open_lead(
    leads_org: dict[str, int],
) -> None:
    """Same contact/group but different bot/chat must not reuse the other bot's deal."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        first_id = await _ensure(session, leads_org)

        other_bot_id = await session.scalar(
            text(
                """
                INSERT INTO bots (
                    code, name, owner_type, owner_id, department_id,
                    inbound_secret_encrypted, outbound_secret_encrypted, outbound_url
                )
                VALUES (
                    :code, 'Other Bot', 'group', :gid, :did,
                    '\\x00', '\\x00', 'https://example.test/outbound'
                )
                RETURNING id
                """
            ),
            {
                "code": f"other-bot-{leads_org['contact_id']}",
                "gid": leads_org["group_id"],
                "did": leads_org["dept_id"],
            },
        )
        assert other_bot_id is not None
        other_chat_id = await session.scalar(
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
                "cid": leads_org["contact_id"],
                "bid": int(other_bot_id),
                "gid": leads_org["group_id"],
                "did": leads_org["dept_id"],
            },
        )
        assert other_chat_id is not None
        await session.commit()

        second_id = (
            await LeadService(session).ensure_open_lead(
                contact_id=leads_org["contact_id"],
                group_id=leads_org["group_id"],
                bot_id=int(other_bot_id),
                chat_id=int(other_chat_id),
            )
        ).id
        await session.commit()

        current_other = await session.scalar(
            text("SELECT current_lead_id FROM chats WHERE id = :cid"),
            {"cid": int(other_chat_id)},
        )
        current_first = await session.scalar(
            text("SELECT current_lead_id FROM chats WHERE id = :cid"),
            {"cid": leads_org["chat_id"]},
        )

    assert second_id != first_id
    assert current_other == second_id
    assert current_first == first_id


@pytest.mark.asyncio
async def test_close_then_inbound_creates_new_lead_and_messages_differ(
    leads_org: dict[str, int],
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        lead_id_1 = await _ensure(session, leads_org)
        msg_1 = await insert_inbound_message(
            session,
            chat_id=leads_org["chat_id"],
            lead_id=lead_id_1,
            text_body="cycle one",
            external_message_id="leads-ext-1",
            external_event_id="leads-evt-1",
            attachments=[],
            reply_to_external_id=None,
        )
        admin = await session.get(User, 1)
        assert admin is not None
        won_status_id = await LeadRepository(session).get_status_id(
            code="won",
            kind=StatusKind.LEAD_PIPELINE,
        )
        assert won_status_id is not None
        await LeadService(session).close_lead(
            lead_id_1,
            status_id=won_status_id,
            actor=admin,
        )
        await session.commit()

    async with session_factory() as session:
        lead_id_2 = await _ensure(session, leads_org)
        assert lead_id_2 != lead_id_1

        msg_2 = await insert_inbound_message(
            session,
            chat_id=leads_org["chat_id"],
            lead_id=lead_id_2,
            text_body="cycle two",
            external_message_id="leads-ext-2",
            external_event_id="leads-evt-2",
            attachments=[],
            reply_to_external_id=None,
        )
        await session.commit()

    assert msg_1.message_id != msg_2.message_id

    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT lead_id FROM messages
                    WHERE id IN (:m1, :m2)
                    ORDER BY id
                    """
                ),
                {"m1": msg_1.message_id, "m2": msg_2.message_id},
            )
        ).all()
    assert rows[0][0] == lead_id_1
    assert rows[1][0] == lead_id_2
    assert rows[0][0] != rows[1][0]


@pytest.mark.asyncio
async def test_two_open_leads_same_group_allowed(
    leads_org: dict[str, int],
) -> None:
    """Migration 0050 dropped uq_leads_open_contact_group — multiple open leads per group are OK."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        lead_id = await _ensure(session, leads_org)
        pipeline_new = await LeadRepository(session).get_status_id(
            code="new",
            kind=StatusKind.LEAD_PIPELINE,
        )
        assert pipeline_new is not None

        second_id = await LeadRepository(session).insert_lead(
            contact_id=leads_org["contact_id"],
            group_id=leads_org["group_id"],
            bot_id=leads_org["bot_id"],
            chat_id=leads_org["chat_id"],
            status_id=pipeline_new,
        )
        await session.commit()

        open_count = await session.scalar(
            text(
                """
                SELECT COUNT(*) FROM leads
                WHERE contact_id = :cid AND group_id = :gid AND closed_at IS NULL
                """
            ),
            {"cid": leads_org["contact_id"], "gid": leads_org["group_id"]},
        )
    assert lead_id > 0
    assert second_id != lead_id
    assert open_count == 2


@pytest.mark.asyncio
async def test_inbound_reopens_closed_chat(
    leads_org: dict[str, int],
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(
            text("UPDATE chats SET status = 'closed' WHERE id = :cid"),
            {"cid": leads_org["chat_id"]},
        )
        await session.commit()

    async with session_factory() as session:
        await LeadService(session).ensure_open_lead(
            contact_id=leads_org["contact_id"],
            group_id=leads_org["group_id"],
            bot_id=leads_org["bot_id"],
            chat_id=leads_org["chat_id"],
        )
        status = await session.scalar(
            text("SELECT status::text FROM chats WHERE id = :cid"),
            {"cid": leads_org["chat_id"]},
        )
    assert status in {ChatStatus.OPEN.value, ChatStatus.IN_PROGRESS.value}
