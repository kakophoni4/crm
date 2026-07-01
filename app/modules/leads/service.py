from __future__ import annotations

import contextlib
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.timeutil import utc_now
from app.modules.chats.workflow_status import (
    on_lead_closed_for_chat,
    set_contact_client_label,
)
from app.modules.contacts.ownership import get_owner
from app.modules.contacts.status_automation import apply_auto_contact_status
from app.modules.db.models.contact import Contact
from app.modules.db.models.enums import StatusKind
from app.modules.db.models.lead import Lead
from app.modules.db.models.user import User
from app.modules.leads.crm_cache import invalidate_contact_crm
from app.modules.leads.pipeline_constants import (
    PIPELINE_NEW_CODE,
    PIPELINE_TERMINAL_CODES,
    PIPELINE_WON_CODE,
)
from app.modules.leads.opt.payment_guard import assert_lead_won_payment_allowed
from app.modules.leads.repository import LeadRepository
from app.modules.statuses.validation import ensure_status_kind
from app.realtime.events import publish
from app.shared.exceptions import NotFound, ValidationError
from app.shared.metrics import inc_lead_closed, inc_lead_created
from app.shared.redis import get_redis
from app.shared.settings import get_settings

_PIPELINE_NEW = PIPELINE_NEW_CODE
_CLIENT_LABEL_NEW = "new"
_CLIENT_LABEL_RETURNING = "returning"


class LeadService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = LeadRepository(session)

    async def ensure_open_lead(
        self,
        *,
        contact_id: int,
        group_id: int,
        bot_id: int,
        chat_id: int,
    ) -> Lead:
        await self._repo.reopen_chat_if_closed(chat_id)

        existing = await self._repo.get_open_for_update(contact_id, group_id)
        if existing is not None:
            await self._repo.set_chat_current_lead(chat_id, existing.id)
            return existing

        default_status_id = await self._repo.get_status_id(
            code=_PIPELINE_NEW,
            kind=StatusKind.LEAD_PIPELINE,
        )
        if default_status_id is None:
            raise RuntimeError("lead_pipeline status 'new' is not seeded")

        prior_closed = await self._repo.count_closed_for_contact_group(contact_id, group_id)
        created = False
        lead: Lead | None = None

        async with self._session.begin_nested():
            try:
                lead = await self._repo.insert_lead(
                    contact_id=contact_id,
                    group_id=group_id,
                    bot_id=bot_id,
                    chat_id=chat_id,
                    status_id=default_status_id,
                )
                created = True
            except IntegrityError:
                lead = None

        if lead is None:
            lead = await self._repo.get_open_for_update(contact_id, group_id)
            if lead is None:
                raise RuntimeError("failed to ensure open lead after unique conflict")

        await self._repo.set_chat_current_lead(chat_id, lead.id)

        if created:
            label = _CLIENT_LABEL_RETURNING if prior_closed > 0 else _CLIENT_LABEL_NEW
            await set_contact_client_label(self._session, contact_id, label)
            inc_lead_created()
            owner_id = await get_owner(self._session, contact_id, group_id)
            scope: dict[str, int] = {"group_id": group_id}
            if owner_id is not None:
                scope["user_id"] = owner_id
            scope["chat_id"] = chat_id
            await publish(
                "lead.created",
                {
                    "lead_id": lead.id,
                    "contact_id": contact_id,
                    "group_id": group_id,
                    "chat_id": chat_id,
                    "status_id": lead.status_id,
                    "source": "inbound",
                },
                scope=scope,
            )

        return lead

    async def close_lead(self, lead_id: int, *, status_id: int, actor: User) -> Lead:
        lead = await self._repo.get_by_id(lead_id)
        if lead is None:
            raise NotFound(message="Lead not found")
        if lead.closed_at is not None:
            raise ValidationError(message="Lead is already closed")

        status = await ensure_status_kind(self._session, status_id, StatusKind.LEAD_PIPELINE)
        if status.code not in PIPELINE_TERMINAL_CODES:
            raise ValidationError(
                message="Lead can only be closed with a successful or unsuccessful sale status",
                details={"allowed_codes": sorted(PIPELINE_TERMINAL_CODES)},
            )

        if status.code == PIPELINE_WON_CODE:
            order_fields = (lead.custom_fields or {}).get("order")
            service_name = (
                order_fields.get("service") if isinstance(order_fields, dict) else None
            )
            await assert_lead_won_payment_allowed(
                self._session,
                lead_id,
                str(service_name) if service_name else None,
            )

        if lead.status_id != status_id:
            from_status_id = lead.status_id
            updated = await self._repo.update_pipeline_status(lead_id, status_id)
            if updated is None:
                raise ValidationError(message="Lead is already closed")
            lead = updated
            owner_id = await get_owner(self._session, lead.contact_id, lead.group_id)
            scope: dict[str, int] = {"group_id": lead.group_id}
            if owner_id is not None:
                scope["user_id"] = owner_id
            if lead.chat_id is not None:
                scope["chat_id"] = lead.chat_id
            await publish(
                "lead.status_changed",
                {
                    "lead_id": lead.id,
                    "contact_id": lead.contact_id,
                    "group_id": lead.group_id,
                    "from_status_id": from_status_id,
                    "to_status_id": status_id,
                },
                scope=scope,
            )

        closed_at = utc_now()
        retention_expires_at: datetime | None = None
        retention_days = get_settings().lead_retention_days
        if retention_days is not None and retention_days > 0:
            retention_expires_at = closed_at + timedelta(days=retention_days)
        closed = await self._repo.close_lead(
            lead_id,
            closed_at=closed_at,
            retention_expires_at=retention_expires_at,
        )
        if closed is None:
            raise ValidationError(message="Lead is already closed")

        inc_lead_closed()
        await self._repo.clear_chat_current_lead(lead_id)

        owner_id = await get_owner(self._session, closed.contact_id, closed.group_id)
        close_scope: dict[str, int] = {"group_id": closed.group_id}
        if owner_id is not None:
            close_scope["user_id"] = owner_id
        if closed.chat_id is not None:
            close_scope["chat_id"] = closed.chat_id
        await publish(
            "lead.closed",
            {
                "lead_id": closed.id,
                "contact_id": closed.contact_id,
                "group_id": closed.group_id,
                "chat_id": closed.chat_id,
                "closed_at": closed_at.isoformat(),
                "closed_by_user_id": actor.id,
                "status_id": closed.status_id,
            },
            scope=close_scope,
        )
        if closed.chat_id is not None:
            await on_lead_closed_for_chat(self._session, closed.chat_id)
        contact_row = await self._session.get(Contact, closed.contact_id)
        if contact_row is not None:
            await apply_auto_contact_status(self._session, contact_row)
        with contextlib.suppress(Exception):
            await invalidate_contact_crm(get_redis(), closed.contact_id)
        await self._session.refresh(closed)
        await self._session.refresh(closed, ["pipeline_status"])
        return closed

    async def patch_lead_status(self, lead_id: int, status_id: int, *, actor: User) -> Lead:
        lead = await self._repo.get_by_id(lead_id)
        if lead is None:
            raise NotFound(message="Lead not found")
        if lead.closed_at is not None:
            raise ValidationError(message="Cannot change status of a closed lead")

        status = await ensure_status_kind(self._session, status_id, StatusKind.LEAD_PIPELINE)
        if status.code in PIPELINE_TERMINAL_CODES:
            raise ValidationError(
                message="Use close lead action for successful or unsuccessful sale",
                details={"code": status.code},
            )

        from_status_id = lead.status_id
        updated = await self._repo.update_pipeline_status(lead_id, status_id)
        if updated is None:
            raise ValidationError(message="Lead is already closed")

        owner_id = await get_owner(self._session, updated.contact_id, updated.group_id)
        scope: dict[str, int] = {"group_id": updated.group_id}
        if owner_id is not None:
            scope["user_id"] = owner_id
        if updated.chat_id is not None:
            scope["chat_id"] = updated.chat_id
        await publish(
            "lead.status_changed",
            {
                "lead_id": updated.id,
                "contact_id": updated.contact_id,
                "group_id": updated.group_id,
                "from_status_id": from_status_id,
                "to_status_id": status_id,
            },
            scope=scope,
        )
        return updated
