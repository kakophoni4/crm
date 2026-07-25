from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.unread import unread_for_me_map
from app.shared.db import get_session_factory
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_unread_for_me_map_page_scoped(
    leads_org: dict[str, int],
    test_settings,
) -> None:
    """Unread map uses page-scoped latest message ids, not a global aggregate."""
    chat_id = leads_org["chat_id"]
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM chat_read_state WHERE chat_id = :cid"),
                {"cid": chat_id},
            )
            conn.execute(
                text("DELETE FROM messages WHERE chat_id = :cid"),
                {"cid": chat_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO messages (chat_id, direction, kind, text)
                    VALUES (:cid, 'inbound', 'text', 'older'),
                           (:cid, 'inbound', 'text', 'newer')
                    """
                ),
                {"cid": chat_id},
            )
            latest_id = conn.execute(
                text(
                    """
                    SELECT id FROM messages
                    WHERE chat_id = :cid
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"cid": chat_id},
            ).scalar_one()
    finally:
        engine.dispose()

    session_factory = get_session_factory()
    async with session_factory() as session:
        assert isinstance(session, AsyncSession)
        unread = await unread_for_me_map(session, [chat_id], actor_user_id=1)

    assert unread[chat_id] is True

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO chat_read_state (chat_id, user_id, last_read_message_id)
                    VALUES (:cid, 1, :mid)
                    ON CONFLICT (chat_id, user_id) DO UPDATE
                    SET last_read_message_id = EXCLUDED.last_read_message_id
                    """
                ),
                {"cid": chat_id, "mid": latest_id},
            )
    finally:
        engine.dispose()

    async with session_factory() as session:
        assert isinstance(session, AsyncSession)
        unread = await unread_for_me_map(session, [chat_id], actor_user_id=1)

    assert unread[chat_id] is False

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM chat_read_state WHERE chat_id = :cid"),
                {"cid": chat_id},
            )
            conn.execute(
                text("DELETE FROM messages WHERE chat_id = :cid"),
                {"cid": chat_id},
            )
    finally:
        engine.dispose()
