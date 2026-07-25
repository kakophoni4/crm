from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import LateralFromClause, Subquery

from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.chat_read_state import ChatReadState


def latest_message_lateral() -> LateralFromClause:
    """Per-chat latest message via index-friendly LATERAL (chat_id, created_at DESC, id DESC)."""
    return (
        select(
            ChatMessage.id.label("max_message_id"),
            ChatMessage.direction.label("direction"),
        )
        .where(ChatMessage.chat_id == Chat.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
        .lateral()
    )


def latest_message_subquery_for_chat_ids(chat_ids: list[int]) -> Subquery:
    """Page-scoped latest message ids (DISTINCT ON), not a global GROUP BY."""
    return (
        select(
            ChatMessage.chat_id.label("chat_id"),
            ChatMessage.id.label("max_message_id"),
        )
        .where(ChatMessage.chat_id.in_(chat_ids))
        .distinct(ChatMessage.chat_id)
        .order_by(
            ChatMessage.chat_id,
            ChatMessage.created_at.desc(),
            ChatMessage.id.desc(),
        )
        .subquery()
    )


def unread_for_actor_expression(
    latest_msg: Subquery | LateralFromClause,
    read_state: Any,
) -> ColumnElement[bool]:
    """True when the actor has not read up to the latest message (chat_read_state only)."""
    return and_(
        latest_msg.c.max_message_id.isnot(None),
        or_(
            read_state.last_read_message_id.is_(None),
            read_state.last_read_message_id < latest_msg.c.max_message_id,
        ),
    )


async def unread_for_me_map(
    session: AsyncSession,
    chat_ids: list[int],
    actor_user_id: int,
) -> dict[int, bool]:
    if not chat_ids:
        return {}
    latest_msg = latest_message_subquery_for_chat_ids(chat_ids)
    read_state = aliased(ChatReadState)
    unread_expr = unread_for_actor_expression(latest_msg, read_state)
    stmt = (
        select(Chat.id, unread_expr.label("unread_for_me"))
        .select_from(Chat)
        .outerjoin(latest_msg, latest_msg.c.chat_id == Chat.id)
        .outerjoin(
            read_state,
            and_(
                read_state.chat_id == Chat.id,
                read_state.user_id == actor_user_id,
            ),
        )
        .where(Chat.id.in_(chat_ids))
    )
    result = await session.execute(stmt)
    return {int(row[0]): bool(row[1]) for row in result.all()}
