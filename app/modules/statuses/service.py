from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import StatusKind
from app.modules.db.models.lead import Lead
from app.modules.db.models.status import Status
from app.modules.leads.pipeline_constants import PIPELINE_PROTECTED_DELETE_CODES
from app.modules.statuses.repository import StatusRepository
from app.modules.statuses.schemas import (
    StatusCreateRequest,
    StatusListResponse,
    StatusOut,
    StatusUpdateRequest,
)
from app.shared.exceptions import Conflict, NotFound, ValidationError


class StatusService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = StatusRepository(session)
        self._session = session

    async def list_statuses(
        self,
        *,
        include_inactive: bool,
        kind: StatusKind | None = None,
    ) -> StatusListResponse:
        rows = await self._repo.list_all(active_only=not include_inactive, kind=kind)
        return StatusListResponse(items=[StatusOut.model_validate(row) for row in rows])

    async def create_status(self, body: StatusCreateRequest) -> StatusOut:
        status_kind = StatusKind(body.kind)
        existing = await self._repo.get_by_code_and_kind(body.code, status_kind)
        if existing is not None:
            raise Conflict(
                message=f"Status code '{body.code}' already exists for kind '{body.kind}'",
                details={"code": body.code, "kind": body.kind},
            )

        status = Status(
            code=body.code,
            kind=body.kind,
            label=body.label,
            color=body.color,
            sort_order=body.sort_order,
        )
        try:
            created = await self._repo.add(status)
            await self._repo.commit()
        except IntegrityError as exc:
            await self._repo.rollback()
            raise Conflict(
                message=f"Status code '{body.code}' already exists for kind '{body.kind}'",
                details={"code": body.code, "kind": body.kind},
            ) from exc
        return StatusOut.model_validate(created)

    async def update_status(self, status_id: int, body: StatusUpdateRequest) -> StatusOut:
        status = await self._repo.get_by_id(status_id)
        if status is None:
            raise NotFound(message="Status not found", details={"id": status_id})

        if body.label is not None:
            status.label = body.label
        if body.color is not None:
            status.color = body.color
        if body.sort_order is not None:
            status.sort_order = body.sort_order

        await self._session.flush()
        await self._repo.commit()
        await self._session.refresh(status)
        return StatusOut.model_validate(status)

    async def _count_leads_for_status(self, status_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Lead).where(Lead.status_id == status_id),
        )
        return int(result.scalar_one())

    async def delete_status(self, status_id: int) -> StatusOut:
        status = await self._repo.get_by_id(status_id)
        if status is None:
            raise NotFound(message="Status not found", details={"id": status_id})

        status_kind = StatusKind(status.kind)
        if status_kind == StatusKind.LEAD_PIPELINE:
            if status.code in PIPELINE_PROTECTED_DELETE_CODES:
                raise ValidationError(
                    message=(
                        "Системный этап воронки нельзя удалить "
                        f"({', '.join(sorted(PIPELINE_PROTECTED_DELETE_CODES))}). "
                        "Можно изменить только название и порядок."
                    ),
                    details={"code": status.code},
                )
            lead_count = await self._count_leads_for_status(status_id)
            if lead_count > 0:
                raise Conflict(
                    message=f"Нельзя удалить этап: на нём {lead_count} сделок",
                    details={"lead_count": lead_count},
                )
            deleted = StatusOut.model_validate(status)
            await self._session.delete(status)
            await self._repo.commit()
            return deleted

        if not status.is_active:
            raise Conflict(message="Status is already inactive", details={"id": status_id})

        status.is_active = False
        await self._session.flush()
        await self._repo.commit()
        await self._session.refresh(status)
        return StatusOut.model_validate(status)
