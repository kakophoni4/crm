from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.repository import AuditRepository
from app.modules.audit.sanitize import sanitize_audit_payload
from app.modules.db.models.audit_log_entry import AuditLogEntry
from app.modules.db.models.enums import AuditAction
from app.shared.request_id import get_request_id


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditRepository(session)

    async def write(
        self,
        *,
        actor_id: int | None,
        action: AuditAction,
        entity_type: str,
        entity_id: int,
        payload: dict[str, Any] | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> AuditLogEntry:
        return await self._repo.create(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=sanitize_audit_payload(payload),
            ip=ip,
            user_agent=user_agent,
            request_id=request_id or get_request_id(),
        )
