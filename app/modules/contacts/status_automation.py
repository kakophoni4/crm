"""Automatic contact lifecycle status (new / active / returning)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.chat import Chat
from app.modules.db.models.contact import Contact
from app.modules.db.models.enums import ChatStatus, ContactStatus
from app.modules.db.models.lead import Lead

_MANUAL_ONLY_STATUSES = frozenset({ContactStatus.DISABLED})
_FROZEN_STATUSES = frozenset(
    {ContactStatus.DISABLED, ContactStatus.MERGED, ContactStatus.ARCHIVED},
)


def resolve_auto_contact_status(
    *,
    closed_leads_count: int,
    other_bot_chats_count: int,
) -> ContactStatus:
    if closed_leads_count > 0:
        return ContactStatus.ACTIVE
    if other_bot_chats_count > 0:
        return ContactStatus.RETURNING
    return ContactStatus.NEW


async def _count_closed_leads(session: AsyncSession, contact_id: int) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Lead)
        .where(Lead.contact_id == contact_id, Lead.closed_at.is_not(None)),
    )
    return int(result.scalar_one() or 0)


async def _count_other_bot_chats(
    session: AsyncSession,
    contact_id: int,
    bot_id: int,
) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Chat)
        .where(
            Chat.contact_id == contact_id,
            Chat.bot_id != bot_id,
            Chat.status != ChatStatus.ARCHIVED,
        ),
    )
    return int(result.scalar_one() or 0)


async def _has_chats_in_multiple_bots(
    session: AsyncSession,
    contact_id: int,
) -> bool:
    result = await session.execute(
        select(func.count(func.distinct(Chat.bot_id)))
        .select_from(Chat)
        .where(
            Chat.contact_id == contact_id,
            Chat.status != ChatStatus.ARCHIVED,
        ),
    )
    return int(result.scalar_one() or 0) >= 2


async def apply_auto_contact_status(
    session: AsyncSession,
    contact: Contact,
    *,
    bot_id: int | None = None,
) -> bool:
    """Recompute status unless frozen (неликвидный / merged / archived). Returns True if changed."""
    if contact.status in _FROZEN_STATUSES:
        return False

    closed_leads = await _count_closed_leads(session, contact.id)
    if bot_id is not None:
        returning_signal = await _count_other_bot_chats(session, contact.id, bot_id) > 0
    else:
        returning_signal = await _has_chats_in_multiple_bots(session, contact.id)

    target = resolve_auto_contact_status(
        closed_leads_count=closed_leads,
        other_bot_chats_count=1 if returning_signal else 0,
    )
    if contact.status == target:
        return False
    contact.status = target
    return True


def validate_manual_status_change(
    current: ContactStatus,
    requested: ContactStatus | None,
) -> ContactStatus | None:
    """
    Returns status to apply, or None to trigger auto-recompute (clearing неликвидный).
    Raises ValueError if change is not allowed.
    """
    if requested is None:
        return None
    if requested == current:
        return current
    if requested in _MANUAL_ONLY_STATUSES:
        return requested
    if current in _MANUAL_ONLY_STATUSES and requested not in _MANUAL_ONLY_STATUSES:
        return None
    raise ValueError("only_illiquid_manual")
