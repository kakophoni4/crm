from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import StatusKind
from app.modules.leads.repository import LeadRepository

WORKFLOW_NEW = "new"
WORKFLOW_WAITING = "waiting"
WORKFLOW_ANSWERED = "answered"
WORKFLOW_DONE = "done"

_CLIENT_LABEL_FIELD = "client_label"
_CLIENT_LABEL_NEW = "new"
_CLIENT_LABEL_RETURNING = "returning"


async def apply_chat_workflow_status(
    session: AsyncSession,
    chat_id: int,
    code: str,
) -> None:
    repo = LeadRepository(session)
    status_id = await repo.get_status_id(code=code, kind=StatusKind.CHAT_LABEL)
    if status_id is None:
        return
    await repo.patch_chat_label_status(chat_id, status_id)


async def on_inbound_from_client(session: AsyncSession, chat_id: int) -> None:
    await apply_chat_workflow_status(session, chat_id, WORKFLOW_WAITING)


async def on_outbound_reply_to_client(session: AsyncSession, chat_id: int) -> None:
    await apply_chat_workflow_status(session, chat_id, WORKFLOW_ANSWERED)


async def on_lead_closed_for_chat(session: AsyncSession, chat_id: int) -> None:
    await apply_chat_workflow_status(session, chat_id, WORKFLOW_DONE)


def read_contact_client_label_code(custom_fields: dict[str, Any] | None) -> str | None:
    if not custom_fields:
        return None
    raw = custom_fields.get(_CLIENT_LABEL_FIELD)
    if raw in (_CLIENT_LABEL_NEW, _CLIENT_LABEL_RETURNING):
        return str(raw)
    return None


async def set_contact_client_label(
    session: AsyncSession,
    contact_id: int,
    label: str,
) -> None:
    from sqlalchemy import select

    from app.modules.db.models.contact import Contact

    if label not in (_CLIENT_LABEL_NEW, _CLIENT_LABEL_RETURNING):
        return
    result = await session.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if contact is None:
        return
    fields = dict(contact.custom_fields or {})
    fields[_CLIENT_LABEL_FIELD] = label
    contact.custom_fields = fields
    await session.flush()
