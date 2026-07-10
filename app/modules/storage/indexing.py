from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.contact import Contact
from app.modules.db.models.enums import MessageDirection
from app.modules.db.models.user import User
from app.modules.chats.timeutil import to_naive_utc
from app.modules.storage.repository import StorageRepository

logger = structlog.get_logger(__name__)


async def index_message_attachments(session: AsyncSession, *, message_id: int) -> None:
    message = await session.get(ChatMessage, message_id)
    if message is None:
        return
    # Raw SQL updates (download worker) bypass the identity map — always reload.
    await session.refresh(message)
    chat = await session.get(Chat, message.chat_id)
    if chat is None or chat.assigned_group_id is None:
        return

    contact = await session.get(Contact, chat.contact_id)
    contact_name = contact.full_name if contact is not None else "Клиент"

    sender_display_name: str
    sender_user_id: int | None = None
    sender_contact_id: int | None = None
    direction = (
        "inbound"
        if message.direction == MessageDirection.INBOUND
        else "outbound"
    )

    if message.direction == MessageDirection.INBOUND:
        sender_display_name = contact_name or "Клиент"
        sender_contact_id = chat.contact_id
    else:
        if message.sender_user_id is not None:
            sender = await session.get(User, message.sender_user_id)
            sender_display_name = sender.full_name if sender is not None else "Оператор"
            sender_user_id = message.sender_user_id
        else:
            sender_display_name = "Оператор"

    repo = StorageRepository(session)
    attachments: list[dict[str, Any]] = message.attachments or []
    for idx, att in enumerate(attachments):
        if att.get("status") not in (None, "ready"):
            continue
        storage_key = att.get("storage_key")
        if not storage_key:
            continue
        file_id = att.get("file_id")
        original_name = str(att.get("filename") or att.get("name") or "file")
        mime_type = str(att.get("mime") or "application/octet-stream")
        size_bytes = int(att.get("size_bytes") or att.get("size") or 0)
        try:
            async with session.begin_nested():
                await repo.upsert_group_chat_file(
                    group_id=chat.assigned_group_id,
                    chat_id=chat.id,
                    message_id=message.id,
                    attachment_index=idx,
                    file_id=int(file_id) if file_id is not None else None,
                    storage_key=str(storage_key),
                    original_name=original_name,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                    direction=direction,
                    sender_user_id=sender_user_id,
                    sender_contact_id=sender_contact_id,
                    sender_display_name=sender_display_name,
                    created_at=to_naive_utc(message.created_at),
                )
        except Exception as exc:
            logger.warning(
                "group_chat_file_index_failed",
                message_id=message_id,
                attachment_index=idx,
                error=str(exc),
            )


async def backfill_group_chat_files(session: AsyncSession, *, limit: int = 300) -> int:
    """Index ready chat attachments that never made it into group_chat_files."""
    result = await session.execute(
        text(
            """
            SELECT m.id
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            WHERE c.assigned_group_id IS NOT NULL
              AND jsonb_typeof(m.attachments) = 'array'
              AND jsonb_array_length(m.attachments) > 0
              AND EXISTS (
                SELECT 1
                FROM jsonb_array_elements(m.attachments) AS att
                WHERE coalesce(att->>'status', 'ready') = 'ready'
                  AND nullif(att->>'storage_key', '') IS NOT NULL
              )
              AND (
                SELECT count(*)::int
                FROM group_chat_files g
                WHERE g.message_id = m.id
              ) < (
                SELECT count(*)::int
                FROM jsonb_array_elements(m.attachments) AS att
                WHERE coalesce(att->>'status', 'ready') = 'ready'
                  AND nullif(att->>'storage_key', '') IS NOT NULL
              )
            ORDER BY m.id DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    message_ids = [int(row[0]) for row in result.all()]
    for message_id in message_ids:
        await index_message_attachments(session, message_id=message_id)
    if message_ids:
        logger.info("group_chat_files_backfill", indexed_messages=len(message_ids))
    return len(message_ids)
