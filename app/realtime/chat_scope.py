from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def chat_event_scope(session: AsyncSession, chat_id: int) -> dict[str, int]:
    row = await session.execute(
        text(
            """
            SELECT assigned_group_id, assigned_department_id
            FROM chats
            WHERE id = :cid
            """
        ),
        {"cid": chat_id},
    )
    fetched = row.one_or_none()
    if fetched is None:
        return {}

    group_id, department_id = fetched[0], fetched[1]
    scope: dict[str, int] = {}
    # Prefer group scope for operators; keep department for seniors / inbox chats.
    if group_id is not None:
        scope["group_id"] = int(group_id)
    if department_id is not None:
        scope["department_id"] = int(department_id)
    return scope
