from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import StatusKind
from app.modules.db.models.status import Status
from app.shared.exceptions import ValidationError


async def ensure_status_kind(
    session: AsyncSession,
    status_id: int,
    expected: StatusKind,
) -> Status:
    result = await session.execute(select(Status).where(Status.id == status_id))
    status = result.scalar_one_or_none()
    if status is None or not status.is_active:
        raise ValidationError(message="status_id not found or inactive")
    if status.kind != expected.value:
        raise ValidationError(message=f"status_id must be a {expected.value} status")
    return status
