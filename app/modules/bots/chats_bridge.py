from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import BotOwnerType, ChatStatus, MessageDirection, MessageKind


@dataclass(frozen=True)
class IngestResult:
    contact_id: int
    chat_id: int
    message_id: int
    attachment_indices: list[int]
    duplicate: bool = False


def parse_bot_message_direction(message_data: dict[str, Any]) -> MessageDirection:
    raw = message_data.get("direction")
    if isinstance(raw, str) and raw.strip().lower() == MessageDirection.OUTBOUND.value:
        return MessageDirection.OUTBOUND
    return MessageDirection.INBOUND


def is_outbound_bot_message(message_data: dict[str, Any]) -> bool:
    return parse_bot_message_direction(message_data) == MessageDirection.OUTBOUND


def _message_kind_from_attachment(att_type: str) -> MessageKind:
    mapping = {
        "photo": MessageKind.IMAGE,
        "document": MessageKind.DOCUMENT,
        "voice": MessageKind.VOICE,
    }
    return mapping.get(att_type, MessageKind.DOCUMENT)


async def upsert_contact_from_telegram(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    telegram_username: str | None,
    first_name: str | None,
    last_name: str | None,
    created_by: int,
) -> int:
    resolved_name = " ".join(part for part in (first_name, last_name) if part) or (
        telegram_username if telegram_username else None
    )
    full_name = resolved_name or f"TG {telegram_user_id}"
    result = await session.execute(
        text(
            """
            INSERT INTO contacts (
                telegram_user_id, telegram_username, full_name, created_by
            )
            VALUES (:tg_id, :username, :full_name, :created_by)
            ON CONFLICT (telegram_user_id) DO UPDATE SET
                telegram_username = COALESCE(
                    EXCLUDED.telegram_username, contacts.telegram_username
                ),
                full_name = COALESCE(:resolved_name, contacts.full_name),
                updated_at = now()
            RETURNING id
            """
        ),
        {
            "tg_id": telegram_user_id,
            "username": telegram_username,
            "full_name": full_name,
            "resolved_name": resolved_name,
            "created_by": created_by,
        },
    )
    return int(result.scalar_one())


async def upsert_chat_for_bot(
    session: AsyncSession,
    *,
    contact_id: int,
    bot_id: int,
    owner_type: BotOwnerType,
    owner_id: int,
) -> int:
    assigned_group_id: int | None = None
    assigned_department_id: int | None = None
    if owner_type == BotOwnerType.GROUP:
        assigned_group_id = owner_id
        group_row = await session.execute(
            text("SELECT department_id FROM groups WHERE id = :gid"),
            {"gid": owner_id},
        )
        assigned_department_id = group_row.scalar_one_or_none()
    else:
        assigned_department_id = owner_id

    # One non-archived chat per contact (uq_chats_contact_active) — reuse regardless of bot_id.
    active = await session.execute(
        text(
            """
            SELECT id FROM chats
            WHERE contact_id = :cid AND status != 'archived'
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"cid": contact_id},
    )
    active_row = active.one_or_none()
    if active_row is not None:
        chat_id = int(active_row[0])
        await session.execute(
            text(
                """
                UPDATE chats
                SET bot_id = :bid,
                    assigned_group_id = :gid,
                    assigned_department_id = :did,
                    updated_at = now()
                WHERE id = :chat_id
                """
            ),
            {
                "chat_id": chat_id,
                "bid": bot_id,
                "gid": assigned_group_id,
                "did": assigned_department_id,
            },
        )
        return chat_id

    existing = await session.execute(
        text(
            """
            SELECT id FROM chats
            WHERE contact_id = :cid AND bot_id = :bid AND status = 'archived'
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"cid": contact_id, "bid": bot_id},
    )
    row = existing.one_or_none()
    if row is not None:
        chat_id = int(row[0])
        await session.execute(
            text(
                """
                UPDATE chats
                SET assigned_group_id = :gid,
                    assigned_department_id = :did,
                    status = 'open',
                    updated_at = now()
                WHERE id = :chat_id
                """
            ),
            {
                "chat_id": chat_id,
                "gid": assigned_group_id,
                "did": assigned_department_id,
            },
        )
        return chat_id

    insert = await session.execute(
        text(
            """
            INSERT INTO chats (
                contact_id, bot_id, assigned_group_id, assigned_department_id, status
            )
            VALUES (:cid, :bid, :gid, :did, :status)
            RETURNING id
            """
        ),
        {
            "cid": contact_id,
            "bid": bot_id,
            "gid": assigned_group_id,
            "did": assigned_department_id,
            "status": ChatStatus.OPEN.value,
        },
    )
    return int(insert.scalar_one())


def _prepare_message_attachments(
    attachments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[int], MessageKind]:
    stored_attachments: list[dict[str, Any]] = []
    pending_indices: list[int] = []
    for idx, att in enumerate(attachments):
        entry = {
            "type": att.get("type", "document"),
            "url": att.get("url"),
            "mime": att.get("mime"),
            "size_bytes": att.get("size_bytes"),
            "filename": att.get("filename"),
            "status": "pending" if att.get("url") else "ready",
        }
        stored_attachments.append(entry)
        if att.get("url"):
            pending_indices.append(idx)

    kind = MessageKind.TEXT
    if stored_attachments:
        kind = _message_kind_from_attachment(str(stored_attachments[0].get("type", "document")))
    return stored_attachments, pending_indices, kind


async def _find_message_by_external_id(
    session: AsyncSession,
    *,
    chat_id: int,
    external_message_id: str,
) -> int | None:
    row = await session.execute(
        text(
            """
            SELECT id FROM messages
            WHERE chat_id = :cid AND external_message_id = :ext
            LIMIT 1
            """
        ),
        {"cid": chat_id, "ext": external_message_id},
    )
    found = row.scalar_one_or_none()
    return int(found) if found is not None else None


async def _ingest_result_for_message(
    session: AsyncSession,
    *,
    chat_id: int,
    message_id: int,
    attachment_indices: list[int],
    duplicate: bool = False,
) -> IngestResult:
    contact_row = await session.execute(
        text("SELECT contact_id FROM chats WHERE id = :cid"),
        {"cid": chat_id},
    )
    contact_id = int(contact_row.scalar_one())
    return IngestResult(
        contact_id=contact_id,
        chat_id=chat_id,
        message_id=message_id,
        attachment_indices=attachment_indices,
        duplicate=duplicate,
    )


async def insert_bot_message(
    session: AsyncSession,
    *,
    chat_id: int,
    lead_id: int | None,
    direction: MessageDirection,
    text_body: str | None,
    external_message_id: str,
    external_event_id: str,
    attachments: list[dict[str, Any]],
    reply_to_external_id: str | None,
    sender_user_id: int | None = None,
) -> IngestResult:
    existing_id = await _find_message_by_external_id(
        session,
        chat_id=chat_id,
        external_message_id=external_message_id,
    )
    if existing_id is not None:
        return await _ingest_result_for_message(
            session,
            chat_id=chat_id,
            message_id=existing_id,
            attachment_indices=[],
            duplicate=True,
        )

    reply_to_id: int | None = None
    if reply_to_external_id:
        reply_to_id = await _find_message_by_external_id(
            session,
            chat_id=chat_id,
            external_message_id=reply_to_external_id,
        )

    stored_attachments, pending_indices, kind = _prepare_message_attachments(attachments)

    result = await session.execute(
        text(
            """
            INSERT INTO messages (
                chat_id, lead_id, direction, kind, text, attachments,
                sender_user_id, external_message_id, external_event_id, reply_to_message_id
            )
            VALUES (
                :chat_id, :lead_id, :direction, :kind, :text, CAST(:attachments AS jsonb),
                :sender_user_id, :ext_msg, :ext_evt, :reply_to
            )
            RETURNING id
            """
        ),
        {
            "chat_id": chat_id,
            "lead_id": lead_id,
            "direction": direction.value,
            "kind": kind.value,
            "text": text_body,
            "attachments": json.dumps(stored_attachments),
            "sender_user_id": sender_user_id,
            "ext_msg": external_message_id,
            "ext_evt": external_event_id,
            "reply_to": reply_to_id,
        },
    )
    message_id = int(result.scalar_one())

    preview = (text_body or "")[:200] if text_body else "[attachment]"
    await session.execute(
        text(
            """
            UPDATE chats
            SET last_message_at = now(),
                last_message_preview = :preview,
                updated_at = now()
            WHERE id = :cid
            """
        ),
        {"preview": preview, "cid": chat_id},
    )

    return await _ingest_result_for_message(
        session,
        chat_id=chat_id,
        message_id=message_id,
        attachment_indices=pending_indices,
    )


async def insert_inbound_message(
    session: AsyncSession,
    *,
    chat_id: int,
    lead_id: int | None,
    text_body: str | None,
    external_message_id: str,
    external_event_id: str,
    attachments: list[dict[str, Any]],
    reply_to_external_id: str | None,
) -> IngestResult:
    return await insert_bot_message(
        session,
        chat_id=chat_id,
        lead_id=lead_id,
        direction=MessageDirection.INBOUND,
        text_body=text_body,
        external_message_id=external_message_id,
        external_event_id=external_event_id,
        attachments=attachments,
        reply_to_external_id=reply_to_external_id,
        sender_user_id=None,
    )


async def insert_outbound_message(
    session: AsyncSession,
    *,
    chat_id: int,
    lead_id: int | None,
    text_body: str | None,
    external_message_id: str,
    external_event_id: str,
    attachments: list[dict[str, Any]],
    reply_to_external_id: str | None,
) -> IngestResult:
    return await insert_bot_message(
        session,
        chat_id=chat_id,
        lead_id=lead_id,
        direction=MessageDirection.OUTBOUND,
        text_body=text_body,
        external_message_id=external_message_id,
        external_event_id=external_event_id,
        attachments=attachments,
        reply_to_external_id=reply_to_external_id,
        sender_user_id=None,
    )


async def get_chat_current_lead_id(session: AsyncSession, chat_id: int) -> int | None:
    row = await session.execute(
        text("SELECT current_lead_id FROM chats WHERE id = :cid"),
        {"cid": chat_id},
    )
    lead_id = row.scalar_one_or_none()
    return int(lead_id) if lead_id is not None else None


async def update_contact_telegram_fields(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    telegram_username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> None:
    full_name = " ".join(part for part in (first_name, last_name) if part)
    await session.execute(
        text(
            """
            UPDATE contacts
            SET telegram_username = COALESCE(:username, telegram_username),
                full_name = COALESCE(NULLIF(:full_name, ''), full_name),
                updated_at = now()
            WHERE telegram_user_id = :tg_id
            """
        ),
        {
            "tg_id": telegram_user_id,
            "username": telegram_username,
            "full_name": full_name or None,
        },
    )


async def update_inbound_message_edited(
    session: AsyncSession,
    *,
    bot_id: int,
    external_message_id: str,
    text_body: str | None,
) -> bool:
    result = await session.execute(
        text(
            """
            UPDATE messages m
            SET text = COALESCE(:text, m.text)
            FROM chats c
            WHERE m.chat_id = c.id
              AND c.bot_id = :bot_id
              AND m.external_message_id = :ext
              AND m.direction = 'inbound'
            RETURNING m.id
            """
        ),
        {"text": text_body, "bot_id": bot_id, "ext": external_message_id},
    )
    return result.scalar_one_or_none() is not None
