from __future__ import annotations

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.cursor import CursorError, decode_cursor
from app.modules.contacts.scope import contact_visibility_clause
from app.modules.db.models.audit_log_entry import AuditLogEntry
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_field_change import ContactFieldChange
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.enums import ContactStatus
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_user_ids
from app.modules.search.trgm import trgm_or_ilike, trgm_search_indexes_available


class ContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _scoped(self, stmt: Select[tuple[Contact]], ctx: ScopeContext) -> Select[tuple[Contact]]:
        clause = contact_visibility_clause(ctx)
        if clause is None:
            return stmt
        return stmt.where(clause)

    async def is_contact_visible(self, ctx: ScopeContext, contact_id: int) -> bool:
        stmt = self._scoped(select(Contact).where(Contact.id == contact_id), ctx)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def is_visible(self, ctx: ScopeContext, contact_id: int) -> bool:
        return await self.is_contact_visible(ctx, contact_id)

    async def count_created_today(self, ctx: ScopeContext) -> int:
        today = func.date(func.timezone("UTC", func.now()))
        contact_day = func.date(func.timezone("UTC", Contact.created_at))
        stmt = select(func.count()).select_from(Contact).where(contact_day == today)
        clause = contact_visibility_clause(ctx)
        if clause is not None:
            stmt = stmt.where(clause)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def get_by_id(self, contact_id: int) -> Contact | None:
        result = await self._session.execute(
            select(Contact).where(Contact.id == contact_id),
        )
        return result.scalar_one_or_none()

    async def list_contacts(
        self,
        *,
        ctx: ScopeContext,
        q: str | None,
        status: ContactStatus | None,
        assigned_user_id: int | None,
        telegram_username: str | None,
        custom_field_filters: dict[str, str],
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Contact], str | None]:
        stmt = select(Contact).order_by(Contact.id.desc()).limit(limit + 1)
        stmt = self._scoped(stmt, ctx)

        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Contact.full_name.ilike(pattern),
                    Contact.phone.ilike(pattern),
                    Contact.email.ilike(pattern),
                    Contact.telegram_username.ilike(pattern),
                ),
            )
        if status is not None:
            stmt = stmt.where(Contact.status == status)
        if assigned_user_id is not None:
            stmt = stmt.where(
                exists(
                    select(1).where(
                        ContactGroupAssignment.contact_id == Contact.id,
                        ContactGroupAssignment.owner_user_id == assigned_user_id,
                    ),
                ),
            )
        if telegram_username is not None:
            stmt = stmt.where(Contact.telegram_username == telegram_username)
        for key, value in custom_field_filters.items():
            stmt = stmt.where(Contact.custom_fields.contains({key: value}))
        if cursor is not None:
            try:
                cursor_id = decode_cursor(cursor)
            except CursorError:
                cursor_id = -1
            stmt = stmt.where(Contact.id < cursor_id)

        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            from app.modules.contacts.cursor import encode_cursor

            next_cursor = encode_cursor(rows[-1].id)
        return rows, next_cursor

    async def search_contacts(
        self,
        *,
        ctx: ScopeContext,
        q: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Contact], str | None]:
        """Global search: full_name and telegram_username only."""
        pattern = f"%{q}%"
        use_trgm = len(q) >= 2 and await trgm_search_indexes_available(self._session)
        stmt = select(Contact).where(
            trgm_or_ilike(Contact.full_name, Contact.telegram_username, pattern=pattern),
        )
        if use_trgm:
            rank = func.greatest(
                func.word_similarity(q, func.coalesce(Contact.full_name, "")),
                func.word_similarity(q, func.coalesce(Contact.telegram_username, "")),
            )
            stmt = stmt.order_by(rank.desc(), Contact.id.desc())
        else:
            stmt = stmt.order_by(Contact.id.desc())
        stmt = stmt.limit(limit + 1)
        stmt = self._scoped(stmt, ctx)
        if cursor is not None:
            try:
                cursor_id = decode_cursor(cursor)
            except CursorError:
                cursor_id = -1
            stmt = stmt.where(Contact.id < cursor_id)

        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            from app.modules.contacts.cursor import encode_cursor

            next_cursor = encode_cursor(rows[-1].id)
        return rows, next_cursor

    async def create(self, contact: Contact) -> Contact:
        self._session.add(contact)
        await self._session.flush()
        await self._session.refresh(contact)
        return contact

    async def update(self, contact: Contact) -> Contact:
        await self._session.flush()
        await self._session.refresh(contact)
        return contact

    async def record_field_changes(
        self,
        changes: list[ContactFieldChange],
    ) -> None:
        self._session.add_all(changes)
        await self._session.flush()

    async def list_field_history(
        self,
        contact_id: int,
        *,
        ctx: ScopeContext,
        limit: int,
    ) -> list[ContactFieldChange]:
        stmt = (
            select(ContactFieldChange)
            .where(ContactFieldChange.contact_id == contact_id)
            .order_by(ContactFieldChange.changed_at.desc())
            .limit(limit)
        )
        scope = visible_user_ids(ctx)
        if scope != SCOPE_ALL and isinstance(scope, set):
            stmt = stmt.where(ContactFieldChange.changed_by.in_(scope))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_entity_audit(
        self,
        contact_id: int,
        *,
        ctx: ScopeContext,
        limit: int,
    ) -> list[AuditLogEntry]:
        stmt = (
            select(AuditLogEntry)
            .where(
                AuditLogEntry.entity_type == "contact",
                AuditLogEntry.entity_id == contact_id,
            )
            .order_by(AuditLogEntry.created_at.desc())
            .limit(limit)
        )
        scope = visible_user_ids(ctx)
        if scope != SCOPE_ALL and isinstance(scope, set):
            stmt = stmt.where(AuditLogEntry.actor_id.in_(scope))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_field_changes_for_contact(self, contact_id: int) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(ContactFieldChange)
            .where(ContactFieldChange.contact_id == contact_id),
        )
        return int(result.scalar_one())
