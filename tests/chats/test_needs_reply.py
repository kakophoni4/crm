from __future__ import annotations

from app.modules.chats.needs_reply import chat_list_needs_reply
from app.modules.db.models.enums import MessageDirection


def test_needs_reply_when_last_message_is_inbound() -> None:
    assert chat_list_needs_reply(
        escalated_at=None,
        last_direction=MessageDirection.INBOUND,
    )


def test_no_needs_reply_when_last_message_is_outbound() -> None:
    assert not chat_list_needs_reply(
        escalated_at=None,
        last_direction=MessageDirection.OUTBOUND,
    )


def test_escalated_always_needs_reply() -> None:
    from datetime import UTC, datetime

    assert chat_list_needs_reply(
        escalated_at=datetime.now(UTC),
        last_direction=MessageDirection.OUTBOUND,
    )
