from __future__ import annotations

import warnings

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import StatusKind
from app.modules.db.models.status import Status


class StatusRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(
        self,
        *,
        active_only: bool,
        kind: StatusKind | None = None,
    ) -> list[Status]:
        stmt = select(Status).order_by(Status.sort_order.asc(), Status.id.asc())
        if active_only:
            stmt = stmt.where(Status.is_active.is_(True))
        if kind is not None:
            stmt = stmt.where(Status.kind == kind.value)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, status_id: int) -> Status | None:
        result = await self._session.execute(select(Status).where(Status.id == status_id))
        return result.scalar_one_or_none()

    async def get_by_code_and_kind(self, code: str, kind: StatusKind) -> Status | None:
        result = await self._session.execute(
            select(Status).where(Status.code == code, Status.kind == kind.value),
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Status | None:
        warnings.warn(
            "get_by_code is deprecated; use get_by_code_and_kind",
            DeprecationWarning,
            stacklevel=2,
        )
        result = await self._session.execute(
            select(Status).where(Status.code == code).limit(1),
        )
        return result.scalar_one_or_none()

    async def add(self, status: Status) -> Status:
        self._session.add(status)
        await self._session.flush()
        await self._session.refresh(status)
        return status

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
