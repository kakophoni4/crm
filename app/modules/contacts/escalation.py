from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.timeutil import utc_now
from app.modules.contacts.ownership import (
    ASSIGNMENT_AUTO_FIRST_RESPONDER,
    ASSIGNMENT_AUTO_RANDOM_AVAILABLE,
    _available_user_ids,
    reassign_owner,
)
from app.modules.contacts.realtime_payloads import contact_group_context, user_full_name
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.group_escalation_settings import GroupEscalationSettings
from app.realtime.events import publish

STRATEGY_FIRST_RESPONDER = "first_responder"
STRATEGY_RANDOM_AVAILABLE = "random_available"


def _utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


@dataclass(frozen=True)
class EscalationScanResult:
    escalated: int = 0
    reassigned: int = 0


async def get_group_settings(
    session: AsyncSession,
    group_id: int,
) -> GroupEscalationSettings:
    result = await session.execute(
        select(GroupEscalationSettings).where(GroupEscalationSettings.group_id == group_id),
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    row = GroupEscalationSettings(group_id=group_id)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


def _is_new_contact_pending(assignment: ContactGroupAssignment) -> bool:
    return assignment.last_owner_response_at is None


async def _first_responder_user_id(
    session: AsyncSession,
    contact_id: int,
    group_id: int,
) -> int | None:
    result = await session.execute(
        text(
            """
            SELECT m.sender_user_id
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            WHERE c.contact_id = :cid
              AND c.assigned_group_id = :gid
              AND m.direction = 'outbound'
              AND m.sender_user_id IS NOT NULL
            ORDER BY m.created_at ASC, m.id ASC
            LIMIT 1
            """
        ),
        {"cid": contact_id, "gid": group_id},
    )
    value = result.scalar_one_or_none()
    return int(value) if value is not None else None


async def _pick_random_available(
    session: AsyncSession,
    group_id: int,
    *,
    exclude_user_id: int | None,
) -> int | None:
    candidates = await _available_user_ids(session, group_id)
    if exclude_user_id is not None:
        candidates = [uid for uid in candidates if uid != exclude_user_id]
    if not candidates:
        return None
    return random.choice(candidates)


async def process_assignment_escalation(
    session: AsyncSession,
    assignment: ContactGroupAssignment,
    settings: GroupEscalationSettings,
    *,
    now: datetime | None = None,
) -> tuple[bool, bool]:
    """Returns (did_group_escalate, did_reassign)."""
    if assignment.pending_inbound_at is None:
        return False, False

    current = _utc_naive(now or utc_now())
    pending_at = _utc_naive(assignment.pending_inbound_at)
    timeout = timedelta(minutes=settings.first_response_timeout_minutes)
    if current - pending_at < timeout:
        return False, False

    did_escalate = False
    if assignment.escalated_to_group_at is None:
        assignment.escalated_to_group_at = current
        did_escalate = True
        if settings.notify_group_on_escalation:
            chat_row = await session.execute(
                text(
                    """
                    SELECT id FROM chats
                    WHERE contact_id = :cid AND assigned_group_id = :gid
                    ORDER BY last_message_at DESC NULLS LAST, id DESC
                    LIMIT 1
                    """
                ),
                {"cid": assignment.contact_id, "gid": assignment.group_id},
            )
            chat_id = chat_row.scalar_one_or_none()
            ctx = await contact_group_context(
                session,
                assignment.contact_id,
                assignment.group_id,
                include_chat_id=False,
            )
            if chat_id is not None:
                ctx["chat_id"] = int(chat_id)
            await publish(
                "contact.escalation.group_notify",
                {
                    **ctx,
                    "pending_since": assignment.pending_inbound_at.isoformat(),
                },
                scope={"group_id": assignment.group_id},
            )

    did_reassign = False
    if _is_new_contact_pending(assignment):
        new_owner: int | None = None
        if settings.new_contact_reassign_strategy == STRATEGY_FIRST_RESPONDER:
            new_owner = await _first_responder_user_id(
                session,
                assignment.contact_id,
                assignment.group_id,
            )
            source = ASSIGNMENT_AUTO_FIRST_RESPONDER
        else:
            new_owner = await _pick_random_available(
                session,
                assignment.group_id,
                exclude_user_id=assignment.owner_user_id,
            )
            source = ASSIGNMENT_AUTO_RANDOM_AVAILABLE

        if new_owner is not None and new_owner != assignment.owner_user_id:
            old_owner = assignment.owner_user_id
            await reassign_owner(
                session,
                assignment.contact_id,
                assignment.group_id,
                new_owner,
                source=source,
            )
            did_reassign = True
            ctx = await contact_group_context(
                session,
                assignment.contact_id,
                assignment.group_id,
            )
            old_name = await user_full_name(session, old_owner)
            new_name = await user_full_name(session, new_owner)
            payload = {
                **ctx,
                "old_owner_user_id": old_owner,
                "old_owner_full_name": old_name,
                "new_owner_user_id": new_owner,
                "new_owner_full_name": new_name,
                "reason": "timeout",
            }
            await publish(
                "contact.ownership.reassigned",
                payload,
                scope={"group_id": assignment.group_id},
            )
            if old_owner is not None and old_owner != new_owner:
                await publish(
                    "contact.ownership.reassigned",
                    {**payload, "perspective": "former_owner"},
                    scope={"user_id": old_owner},
                )
                await publish(
                    "contact.ownership.reassigned",
                    {**payload, "perspective": "new_owner"},
                    scope={"user_id": new_owner},
                )

    await session.flush()
    return did_escalate, did_reassign


async def scan_pending_escalations(session: AsyncSession) -> EscalationScanResult:
    result = await session.execute(
        select(ContactGroupAssignment).where(
            ContactGroupAssignment.pending_inbound_at.is_not(None),
        ),
    )
    assignments = list(result.scalars().all())
    escalated = 0
    reassigned = 0
    settings_cache: dict[int, GroupEscalationSettings] = {}

    for assignment in assignments:
        if assignment.group_id not in settings_cache:
            settings_cache[assignment.group_id] = await get_group_settings(
                session,
                assignment.group_id,
            )
        did_escalate, did_reassign = await process_assignment_escalation(
            session,
            assignment,
            settings_cache[assignment.group_id],
        )
        if did_escalate:
            escalated += 1
        if did_reassign:
            reassigned += 1

    return EscalationScanResult(escalated=escalated, reassigned=reassigned)
