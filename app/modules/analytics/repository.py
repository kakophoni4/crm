from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.schemas import OperatorStats
from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.enums import ChatStatus, MessageDirection, UserRole, UserStatus
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL

ScopeUserIds = set[int] | Literal["ALL"]

_OWNER_CHAT_JOIN = and_(
    ContactGroupAssignment.contact_id == Chat.contact_id,
    ContactGroupAssignment.group_id == Chat.assigned_group_id,
)


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_operator_stats(
        self,
        user_ids: ScopeUserIds,
        period_days: int | None,
    ) -> list[OperatorStats]:
        cutoff: datetime | None = None
        if period_days is not None:
            cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=period_days)

        user_filters = [
            User.role == UserRole.USER,
            User.status == UserStatus.ACTIVE,
        ]
        if user_ids != SCOPE_ALL:
            user_filters.append(User.id.in_(user_ids))

        operators_result = await self._session.execute(
            select(User.id, User.full_name, User.presence)
            .where(*user_filters)
            .order_by(User.full_name, User.id),
        )
        operators = operators_result.all()
        if not operators:
            return []

        operator_ids = [row[0] for row in operators]

        active_counts = await self._count_active_chats(operator_ids)
        closed_counts = await self._count_closed_chats(operator_ids, cutoff)
        avg_response = await self._avg_first_response_minutes(operator_ids, cutoff)

        return [
            OperatorStats(
                user_id=op_id,
                full_name=full_name,
                presence=presence,
                active_chats_count=active_counts.get(op_id, 0),
                closed_chats_count=closed_counts.get(op_id, 0),
                avg_first_response_minutes=avg_response.get(op_id),
            )
            for op_id, full_name, presence in operators
        ]

    async def _count_active_chats(self, operator_ids: list[int]) -> dict[int, int]:
        stmt = (
            select(ContactGroupAssignment.owner_user_id, func.count(Chat.id))
            .select_from(Chat)
            .join(ContactGroupAssignment, _OWNER_CHAT_JOIN)
            .where(
                ContactGroupAssignment.owner_user_id.in_(operator_ids),
                Chat.status.in_((ChatStatus.OPEN, ChatStatus.IN_PROGRESS)),
            )
            .group_by(ContactGroupAssignment.owner_user_id)
        )
        result = await self._session.execute(stmt)
        return {int(owner_id): int(count) for owner_id, count in result.all()}

    async def _count_closed_chats(
        self,
        operator_ids: list[int],
        cutoff: datetime | None,
    ) -> dict[int, int]:
        stmt = (
            select(ContactGroupAssignment.owner_user_id, func.count(Chat.id))
            .select_from(Chat)
            .join(ContactGroupAssignment, _OWNER_CHAT_JOIN)
            .where(
                ContactGroupAssignment.owner_user_id.in_(operator_ids),
                Chat.status == ChatStatus.CLOSED,
            )
            .group_by(ContactGroupAssignment.owner_user_id)
        )
        if cutoff is not None:
            stmt = stmt.where(Chat.updated_at >= cutoff)
        result = await self._session.execute(stmt)
        return {int(owner_id): int(count) for owner_id, count in result.all()}

    async def _avg_first_response_minutes(
        self,
        operator_ids: list[int],
        cutoff: datetime | None,
    ) -> dict[int, float]:
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
            )
        ).subquery()

        response_minutes = (
            func.extract(
                "epoch",
                per_chat_times.c.first_outbound - per_chat_times.c.first_inbound,
            )
            / 60.0
        ).label("response_minutes")

        stmt = (
            select(
                ContactGroupAssignment.owner_user_id,
                func.avg(response_minutes),
            )
            .select_from(Chat)
            .join(ContactGroupAssignment, _OWNER_CHAT_JOIN)
            .join(per_chat_times, per_chat_times.c.chat_id == Chat.id)
            .where(ContactGroupAssignment.owner_user_id.in_(operator_ids))
            .group_by(ContactGroupAssignment.owner_user_id)
        )
        if cutoff is not None:
            stmt = stmt.where(per_chat_times.c.first_inbound >= cutoff)

        result = await self._session.execute(stmt)
        return {
            int(owner_id): float(avg_minutes)
            for owner_id, avg_minutes in result.all()
            if avg_minutes is not None
        }
