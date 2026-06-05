from __future__ import annotations

from typing import Any

from sqlalchemy import case, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.enums import MessageDirection


def _utc_today() -> Any:
    return func.date(func.timezone("UTC", func.now()))


def _utc_day(column: Any) -> Any:
    return func.date(func.timezone("UTC", column))


class DashboardMetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _chat_group_scope(self, stmt: Select[Any], group_ids: set[int] | None) -> Select[Any]:
        if group_ids is None:
            return stmt
        if not group_ids:
            return stmt.where(false())
        return stmt.where(Chat.assigned_group_id.in_(group_ids))

    async def count_chats_today(self, group_ids: set[int] | None) -> int:
        stmt = (
            select(func.count())
            .select_from(Chat)
            .where(_utc_day(Chat.created_at) == _utc_today())
        )
        stmt = self._chat_group_scope(stmt, group_ids)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def avg_first_response_minutes_today(self, group_ids: set[int] | None) -> float | None:
        first_inbound = func.min(
            case(
                (ChatMessage.direction == MessageDirection.INBOUND, ChatMessage.created_at),
                else_=None,
            ),
        ).label("first_inbound")
        first_outbound = func.min(
            case(
                (ChatMessage.direction == MessageDirection.OUTBOUND, ChatMessage.created_at),
                else_=None,
            ),
        ).label("first_outbound")

        per_chat_times = (
            select(
                ChatMessage.chat_id,
                first_inbound,
                first_outbound,
            )
            .group_by(ChatMessage.chat_id)
            .having(
                first_inbound.isnot(None),
                first_outbound.isnot(None),
                first_outbound >= first_inbound,
                _utc_day(first_inbound) == _utc_today(),
            )
        ).subquery()

        response_minutes = (
            func.extract(
                "epoch",
                per_chat_times.c.first_outbound - per_chat_times.c.first_inbound,
            )
            / 60.0
        )

        stmt = (
            select(func.avg(response_minutes))
            .select_from(Chat)
            .join(per_chat_times, per_chat_times.c.chat_id == Chat.id)
        )
        stmt = self._chat_group_scope(stmt, group_ids)
        result = await self._session.execute(stmt)
        avg = result.scalar_one_or_none()
        if avg is None:
            return None
        return float(avg)
