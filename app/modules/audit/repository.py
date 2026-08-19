from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.audit_log_entry import AuditLogEntry
from app.modules.db.models.enums import AuditAction


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        actor_id: int | None,
        action: AuditAction,
        entity_type: str,
        entity_id: int,
        payload: dict[str, object],
        ip: str | None,
        user_agent: str | None,
        request_id: str | None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_for_entity(
        self,
        *,
        entity_type: str,
        entity_id: int,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        result = await self._session.execute(
            select(AuditLogEntry)
            .where(
                AuditLogEntry.entity_type == entity_type,
                AuditLogEntry.entity_id == entity_id,
            )
            .order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
            .limit(limit),
        )
        return list(result.scalars().all())
