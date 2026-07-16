from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.chat import Chat
from app.modules.db.models.enums import ChatStatus, StatusKind
from app.modules.db.models.lead import Lead
from app.modules.db.models.lead_comment import LeadComment
from app.modules.db.models.status import Status
from app.modules.leads.cursor import CursorError, decode_lead_cursor, encode_lead_cursor


@dataclass(frozen=True)
class PipelineStatusAggregate:
    status_id: int
    code: str
    label: str
    count: int


class LeadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_open(self, contact_id: int, group_id: int) -> Lead | None:
        stmt = (
            select(Lead)
            .where(
                Lead.contact_id == contact_id,
                Lead.group_id == group_id,
                Lead.closed_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_open_for_update(self, contact_id: int, group_id: int) -> Lead | None:
        stmt = (
            select(Lead)
            .where(
                Lead.contact_id == contact_id,
                Lead.group_id == group_id,
                Lead.closed_at.is_(None),
            )
            .with_for_update()
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_open_for_chat_for_update(self, chat_id: int) -> Lead | None:
        """Open lead already bound to this chat (preferred reuse target)."""
        stmt = (
            select(Lead)
            .where(
                Lead.chat_id == chat_id,
                Lead.closed_at.is_(None),
            )
            .with_for_update()
            .order_by(Lead.id.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_open_for_bot_for_update(
        self,
        contact_id: int,
        group_id: int,
        bot_id: int,
    ) -> Lead | None:
        """Open lead for the same contact/group/bot — do not steal another bot's deal."""
        stmt = (
            select(Lead)
            .where(
                Lead.contact_id == contact_id,
                Lead.group_id == group_id,
                Lead.bot_id == bot_id,
                Lead.closed_at.is_(None),
            )
            .with_for_update()
            .order_by(Lead.id.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def bind_lead_to_chat(self, lead_id: int, chat_id: int) -> None:
        await self._session.execute(
            update(Lead).where(Lead.id == lead_id, Lead.closed_at.is_(None)).values(chat_id=chat_id),
        )

    async def get_by_id(self, lead_id: int) -> Lead | None:
        result = await self._session.execute(select(Lead).where(Lead.id == lead_id))
        return result.scalar_one_or_none()

    async def count_closed_for_contact_group(self, contact_id: int, group_id: int) -> int:
        stmt = select(func.count()).where(
            Lead.contact_id == contact_id,
            Lead.group_id == group_id,
            Lead.closed_at.is_not(None),
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_closed_for_contact(self, contact_id: int) -> int:
        stmt = select(func.count()).where(
            Lead.contact_id == contact_id,
            Lead.closed_at.is_not(None),
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    def _group_scope_filter(self, stmt: Any, group_ids: set[int] | None) -> Any:
        if group_ids is None:
            return stmt
        if not group_ids:
            return stmt.where(False)
        return stmt.where(Lead.group_id.in_(group_ids))

    async def count_open_leads(self, group_ids: set[int] | None) -> int:
        stmt = select(func.count()).select_from(Lead).where(Lead.closed_at.is_(None))
        stmt = self._group_scope_filter(stmt, group_ids)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_closed_today(self, group_ids: set[int] | None) -> int:
        closed_day = func.date(func.timezone("UTC", Lead.closed_at))
        today = func.date(func.timezone("UTC", func.now()))
        stmt = (
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.closed_at.is_not(None),
                closed_day == today,
            )
        )
        stmt = self._group_scope_filter(stmt, group_ids)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_closed_today_by_pipeline_code(
        self,
        group_ids: set[int] | None,
        code: str,
    ) -> int:
        closed_day = func.date(func.timezone("UTC", Lead.closed_at))
        today = func.date(func.timezone("UTC", func.now()))
        stmt = (
            select(func.count())
            .select_from(Lead)
            .join(Status, Status.id == Lead.status_id)
            .where(
                Lead.closed_at.is_not(None),
                closed_day == today,
                Status.code == code,
                Status.kind == StatusKind.LEAD_PIPELINE.value,
            )
        )
        stmt = self._group_scope_filter(stmt, group_ids)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_open_by_pipeline_status(
        self,
        group_ids: set[int] | None,
        *,
        limit: int | None = None,
    ) -> list[PipelineStatusAggregate]:
        stmt = (
            select(
                Lead.status_id,
                Status.code,
                Status.label,
                func.count().label("cnt"),
            )
            .join(Status, Status.id == Lead.status_id)
            .where(
                Lead.closed_at.is_(None),
                Status.kind == StatusKind.LEAD_PIPELINE,
            )
            .group_by(Lead.status_id, Status.code, Status.label)
            .order_by(func.count().desc(), Lead.status_id.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        stmt = self._group_scope_filter(stmt, group_ids)
        result = await self._session.execute(stmt)
        return [
            PipelineStatusAggregate(
                status_id=int(row.status_id),
                code=str(row.code),
                label=str(row.label),
                count=int(row.cnt),
            )
            for row in result.all()
        ]

    async def list_for_contact(
        self,
        contact_id: int,
        *,
        group_ids: set[int] | None,
        group_id: int | None,
        status_id: int | None,
        open_only: bool | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Lead], str | None]:
        stmt = (
            select(Lead)
            .where(Lead.contact_id == contact_id)
            .order_by(Lead.created_at.desc(), Lead.id.desc())
            .limit(limit + 1)
        )
        if group_ids is not None:
            if not group_ids:
                return [], None
            stmt = stmt.where(Lead.group_id.in_(group_ids))
        if group_id is not None:
            stmt = stmt.where(Lead.group_id == group_id)
        if status_id is not None:
            stmt = stmt.where(Lead.status_id == status_id)
        if open_only is True:
            stmt = stmt.where(Lead.closed_at.is_(None))
        elif open_only is False:
            stmt = stmt.where(Lead.closed_at.is_not(None))
        if cursor is not None:
            try:
                cursor_at, cursor_id = decode_lead_cursor(cursor)
            except CursorError:
                cursor_at, cursor_id = datetime.min.replace(tzinfo=None), -1
            stmt = stmt.where(
                or_(
                    Lead.created_at < cursor_at,
                    and_(Lead.created_at == cursor_at, Lead.id < cursor_id),
                ),
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_lead_cursor(last.created_at, last.id)
        return rows, next_cursor

    async def find_chat_for_lead(
        self,
        *,
        contact_id: int,
        group_id: int,
        bot_id: int | None,
    ) -> int | None:
        stmt = select(Chat.id).where(
            Chat.contact_id == contact_id,
            Chat.assigned_group_id == group_id,
        )
        if bot_id is not None:
            stmt = stmt.where(Chat.bot_id == bot_id)
        stmt = stmt.order_by(Chat.id.desc()).limit(1)
        result = await self._session.execute(stmt)
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None

    async def update_lead_fields(
        self,
        lead_id: int,
        *,
        status_id: int | None = None,
        title: str | None = None,
        comment: str | None = None,
        custom_fields: dict[str, Any] | None = None,
        only_open: bool = True,
        comment_set: bool = False,
    ) -> Lead | None:
        values: dict[str, Any] = {}
        if status_id is not None:
            values["status_id"] = status_id
        if title is not None:
            values["title"] = title
        if comment_set:
            values["comment"] = comment
        if custom_fields is not None:
            values["custom_fields"] = custom_fields
        if not values:
            return await self.get_by_id(lead_id)
        stmt = update(Lead).where(Lead.id == lead_id)
        if only_open:
            stmt = stmt.where(Lead.closed_at.is_(None))
        stmt = stmt.values(**values).returning(Lead)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_status_id(self, *, code: str, kind: StatusKind) -> int | None:
        result = await self._session.execute(
            select(Status.id).where(Status.code == code, Status.kind == kind.value).limit(1),
        )
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None

    async def get_status_kind(self, status_id: int) -> str | None:
        result = await self._session.execute(
            select(Status.kind).where(Status.id == status_id).limit(1),
        )
        return result.scalar_one_or_none()

    async def insert_lead(
        self,
        *,
        contact_id: int,
        group_id: int,
        bot_id: int | None,
        chat_id: int,
        status_id: int,
    ) -> Lead:
        lead = Lead(
            contact_id=contact_id,
            group_id=group_id,
            bot_id=bot_id,
            chat_id=chat_id,
            status_id=status_id,
        )
        self._session.add(lead)
        await self._session.flush()
        await self._session.refresh(lead)
        return lead

    async def set_chat_current_lead(self, chat_id: int, lead_id: int) -> None:
        await self._session.execute(
            update(Chat).where(Chat.id == chat_id).values(current_lead_id=lead_id),
        )

    async def clear_chat_current_lead(self, lead_id: int) -> None:
        await self._session.execute(
            update(Chat).where(Chat.current_lead_id == lead_id).values(current_lead_id=None),
        )

    async def patch_chat_label_status(self, chat_id: int, status_id: int) -> None:
        await self._session.execute(
            update(Chat).where(Chat.id == chat_id).values(status_id=status_id),
        )

    async def reopen_chat_if_closed(self, chat_id: int) -> None:
        result = await self._session.execute(
            select(Chat.status, Chat.assigned_user_id).where(Chat.id == chat_id),
        )
        row = result.one_or_none()
        if row is None or row[0] != ChatStatus.CLOSED:
            return
        new_status = ChatStatus.IN_PROGRESS if row[1] is not None else ChatStatus.OPEN
        await self._session.execute(
            update(Chat).where(Chat.id == chat_id).values(status=new_status),
        )

    async def close_lead(
        self,
        lead_id: int,
        *,
        closed_at: datetime,
        retention_expires_at: datetime | None = None,
    ) -> Lead | None:
        values: dict[str, datetime] = {"closed_at": closed_at}
        if retention_expires_at is not None:
            values["retention_expires_at"] = retention_expires_at
        result = await self._session.execute(
            update(Lead)
            .where(Lead.id == lead_id, Lead.closed_at.is_(None))
            .values(**values)
            .returning(Lead),
        )
        return result.scalar_one_or_none()

    async def update_pipeline_status(self, lead_id: int, status_id: int) -> Lead | None:
        result = await self._session.execute(
            update(Lead)
            .where(Lead.id == lead_id, Lead.closed_at.is_(None))
            .values(status_id=status_id)
            .returning(Lead),
        )
        return result.scalar_one_or_none()

    async def add_lead_comment(
        self,
        lead_id: int,
        *,
        group_id: int,
        body: str,
        created_by: int | None,
    ) -> LeadComment:
        row = LeadComment(
            lead_id=lead_id,
            group_id=group_id,
            body=body,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_comments_by_lead_ids(
        self,
        lead_ids: list[int],
        *,
        group_ids: set[int] | None = None,
    ) -> dict[int, list[LeadComment]]:
        if not lead_ids:
            return {}
        stmt = (
            select(LeadComment)
            .where(LeadComment.lead_id.in_(lead_ids))
            .order_by(LeadComment.lead_id, LeadComment.created_at.asc())
        )
        if group_ids is not None:
            if not group_ids:
                return {}
            stmt = stmt.where(LeadComment.group_id.in_(group_ids))
        result = await self._session.execute(stmt)
        grouped: dict[int, list[LeadComment]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.lead_id, []).append(row)
        return grouped

    async def list_comments_for_lead(
        self,
        lead_id: int,
        *,
        group_ids: set[int] | None = None,
    ) -> list[LeadComment]:
        stmt = (
            select(LeadComment)
            .where(LeadComment.lead_id == lead_id)
            .order_by(LeadComment.created_at.asc())
        )
        if group_ids is not None:
            if not group_ids:
                return []
            stmt = stmt.where(LeadComment.group_id.in_(group_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
