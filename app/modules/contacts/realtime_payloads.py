from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.contact import Contact
from app.modules.db.models.group import Group
from app.modules.db.models.user import User


async def _chat_id_for_contact_group(
    session: AsyncSession,
    contact_id: int,
    group_id: int,
) -> int | None:
    row = await session.execute(
        text(
            """
            SELECT id FROM chats
            WHERE contact_id = :cid AND assigned_group_id = :gid
            ORDER BY last_message_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ),
        {"cid": contact_id, "gid": group_id},
    )
    value = row.scalar_one_or_none()
    return int(value) if value is not None else None


async def contact_group_context(
    session: AsyncSession,
    contact_id: int,
    group_id: int,
    *,
    include_chat_id: bool = True,
) -> dict[str, Any]:
    contact = await session.get(Contact, contact_id)
    group = await session.get(Group, group_id)
    payload: dict[str, Any] = {
        "contact_id": contact_id,
        "group_id": group_id,
        "contact_full_name": contact.full_name if contact is not None else None,
        "group_name": group.name if group is not None else None,
    }
    if include_chat_id:
        payload["chat_id"] = await _chat_id_for_contact_group(session, contact_id, group_id)
    return payload


async def user_full_name(session: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = await session.get(User, user_id)
    return user.full_name if user is not None else None
