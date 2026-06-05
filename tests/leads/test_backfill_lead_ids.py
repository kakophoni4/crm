from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url


@pytest.mark.asyncio
async def test_chats_with_messages_have_lead_ids_after_backfill(
    test_settings: Settings,
    db_ready: None,
) -> None:
    """Sample audit: migration 0019 backfilled current_lead_id and messages.lead_id."""
    del db_ready
    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as conn:
            gaps = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM chats c
                    WHERE c.assigned_group_id IS NOT NULL
                      AND c.status::text != 'archived'
                      AND EXISTS (
                          SELECT 1 FROM messages m WHERE m.chat_id = c.id
                      )
                      AND (
                          c.current_lead_id IS NULL
                          OR EXISTS (
                              SELECT 1 FROM messages m
                              WHERE m.chat_id = c.id AND m.lead_id IS NULL
                          )
                      )
                    """
                ),
            ).scalar_one()
            sample = conn.execute(
                text(
                    """
                    SELECT c.id, c.current_lead_id,
                           (SELECT COUNT(*) FROM messages m
                            WHERE m.chat_id = c.id AND m.lead_id IS NULL) AS null_lead_msgs
                    FROM chats c
                    WHERE c.assigned_group_id IS NOT NULL
                      AND c.status::text != 'archived'
                      AND EXISTS (SELECT 1 FROM messages m WHERE m.chat_id = c.id)
                    ORDER BY c.id DESC
                    LIMIT 5
                    """
                ),
            ).all()
    finally:
        engine.dispose()

    assert gaps == 0, f"chats/messages missing lead_id backfill: sample={sample}"
