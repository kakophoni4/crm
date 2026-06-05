from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.chats_bridge import insert_inbound_message
from app.modules.db.models.user import User
from app.modules.leads.service import LeadService
from app.shared.db import get_session_factory
from tests.auth.conftest import _sync_database_url


async def _insert_probe_inbound(
    leads_org: dict[str, int],
    *,
    external_message_id: str,
    external_event_id: str,
    text_body: str,
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        assert isinstance(session, AsyncSession)
        admin = await session.get(User, 1)
        assert admin is not None
        lead = await LeadService(session).ensure_open_lead(
            contact_id=leads_org["contact_id"],
            group_id=leads_org["group_id"],
            bot_id=leads_org["bot_id"],
            chat_id=leads_org["chat_id"],
        )
        await insert_inbound_message(
            session,
            chat_id=leads_org["chat_id"],
            lead_id=lead.id,
            text_body=text_body,
            external_message_id=external_message_id,
            external_event_id=external_event_id,
            attachments=[],
            reply_to_external_id=None,
        )
        await session.commit()


def _cleanup_leads_org_messages(test_settings, chat_id: int) -> None:
    from app.shared.settings import Settings

    assert isinstance(test_settings, Settings)
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM messages WHERE chat_id = :cid"),
                {"cid": chat_id},
            )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_inbound_updates_chat_preview_without_legacy_unread_column(
    leads_org: dict[str, int],
    test_settings,
) -> None:
    """After phase-2 DROP unread_count_user, inbound still updates last_message_* on chat."""
    try:
        await _insert_probe_inbound(
            leads_org,
            external_message_id="unread-cutover-ext-1",
            external_event_id="unread-cutover-evt-1",
            text_body="cutover probe",
        )

        engine = create_engine(_sync_database_url(test_settings.database_url))
        try:
            with engine.connect() as conn:
                preview = conn.execute(
                    text(
                        "SELECT last_message_preview FROM chats WHERE id = :cid",
                    ),
                    {"cid": leads_org["chat_id"]},
                ).scalar_one()
                has_legacy_col = conn.execute(
                    text(
                        """
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'chats'
                          AND column_name = 'unread_count_user'
                        """
                    ),
                ).fetchone()
        finally:
            engine.dispose()

        assert preview == "cutover probe"
        assert has_legacy_col is None
    finally:
        _cleanup_leads_org_messages(test_settings, leads_org["chat_id"])
