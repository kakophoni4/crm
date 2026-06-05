from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.enums import MessageDirection, StatusKind, UserRole
from app.modules.db.models.lead import Lead
from app.modules.db.models.status import Status
from app.modules.db.models.user import User
from app.modules.leads.dashboard_metrics import _utc_day, _utc_today
from app.modules.leads.pipeline_constants import PIPELINE_LOST_CODE, PIPELINE_WON_CODE


@dataclass(frozen=True)
class OperatorDashboardRow:
    user_id: int
    display_name: str
    chats_today_count: int
    avg_response_minutes: float | None
    closed_won_today_count: int
    closed_lost_today_count: int
    open_leads_count: int


class OperatorDashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_operator_rows(
        self,
        *,
        operator_user_ids: list[int],
        group_ids: set[int],
    ) -> list[OperatorDashboardRow]:
        if not operator_user_ids or not group_ids:
            return []

        users_result = await self._session.execute(
            select(User.id, User.full_name, User.username)
            .where(
                User.id.in_(operator_user_ids),
                User.role == UserRole.USER.value,
            )
            .order_by(User.full_name.asc(), User.username.asc()),
        )
        users = list(users_result.all())
        if not users:
            return []

        rows: list[OperatorDashboardRow] = []
        for user_id, full_name, username in users:
            display = (full_name or "").strip() or (username or "").strip() or f"#{user_id}"
            rows.append(
                OperatorDashboardRow(
                    user_id=int(user_id),
                    display_name=display,
                    chats_today_count=await self._count_chats_today_for_owner(
                        int(user_id),
                        group_ids,
                    ),
                    avg_response_minutes=await self._avg_response_minutes_today_for_sender(
                        int(user_id),
                        group_ids,
                    ),
                    closed_won_today_count=await self._count_closed_today_for_owner(
                        int(user_id),
                        group_ids,
                        PIPELINE_WON_CODE,
                    ),
                    closed_lost_today_count=await self._count_closed_today_for_owner(
                        int(user_id),
                        group_ids,
                        PIPELINE_LOST_CODE,
                    ),
                    open_leads_count=await self._count_open_leads_for_owner(
                        int(user_id),
                        group_ids,
                    ),
                ),
            )
        return rows

    def _owner_join(self) -> ColumnElement[bool]:
        return and_(
            ContactGroupAssignment.contact_id == Lead.contact_id,
            ContactGroupAssignment.group_id == Lead.group_id,
        )

    async def _count_open_leads_for_owner(self, owner_user_id: int, group_ids: set[int]) -> int:
        stmt = (
            select(func.count())
            .select_from(Lead)
            .join(ContactGroupAssignment, self._owner_join())
            .where(
                Lead.closed_at.is_(None),
                Lead.group_id.in_(group_ids),
                ContactGroupAssignment.owner_user_id == owner_user_id,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def _count_closed_today_for_owner(
        self,
        owner_user_id: int,
        group_ids: set[int],
        status_code: str,
    ) -> int:
        closed_day = _utc_day(Lead.closed_at)
        stmt = (
            select(func.count())
            .select_from(Lead)
            .join(Status, Status.id == Lead.status_id)
            .join(ContactGroupAssignment, self._owner_join())
            .where(
                Lead.closed_at.is_not(None),
                closed_day == _utc_today(),
                Lead.group_id.in_(group_ids),
                Status.code == status_code,
                Status.kind == StatusKind.LEAD_PIPELINE.value,
                ContactGroupAssignment.owner_user_id == owner_user_id,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def _count_chats_today_for_owner(self, owner_user_id: int, group_ids: set[int]) -> int:
        stmt = (
            select(func.count())
            .select_from(Chat)
            .join(
                ContactGroupAssignment,
                and_(
                    ContactGroupAssignment.contact_id == Chat.contact_id,
                    ContactGroupAssignment.group_id == Chat.assigned_group_id,
                ),
            )
            .where(
                _utc_day(Chat.created_at) == _utc_today(),
                Chat.assigned_group_id.in_(group_ids),
                ContactGroupAssignment.owner_user_id == owner_user_id,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def _avg_response_minutes_today_for_sender(
        self,
        sender_user_id: int,
        group_ids: set[int],
    ) -> float | None:
        first_inbound = func.min(
            case(
                (ChatMessage.direction == MessageDirection.INBOUND, ChatMessage.created_at),
                else_=None,
            ),
        ).label("first_inbound")
        first_outbound = func.min(
            case(
                (
                    and_(
                        ChatMessage.direction == MessageDirection.OUTBOUND,
                        ChatMessage.sender_user_id == sender_user_id,
                    ),
                    ChatMessage.created_at,
                ),
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
            .where(Chat.assigned_group_id.in_(group_ids))
        )
        result = await self._session.execute(stmt)
        avg = result.scalar_one_or_none()
        if avg is None:
            return None
        return float(avg)
