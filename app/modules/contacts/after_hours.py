from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.timeutil import utc_now
from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.enums import MessageDirection, MessageKind
from app.modules.db.models.group_after_hours_settings import (
    DEFAULT_WORKING_HOURS,
    GroupAfterHoursSettings,
)
from app.realtime.chat_scope import chat_event_scope
from app.shared.request_id import generate_ulid

logger = structlog.get_logger(__name__)

_WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def is_within_working_hours(
    now_utc: datetime,
    *,
    timezone: str,
    working_hours: dict[str, Any] | None,
) -> bool:
    """Return True if ``now_utc`` falls inside configured working windows."""
    try:
        tz = ZoneInfo(timezone or "Europe/Moscow")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Europe/Moscow")

    local = now_utc.replace(tzinfo=UTC).astimezone(tz) if now_utc.tzinfo is None else now_utc.astimezone(tz)
    schedule = working_hours if isinstance(working_hours, dict) and working_hours else DEFAULT_WORKING_HOURS
    day_key = _WEEKDAY_KEYS[local.weekday()]
    windows = schedule.get(day_key) or schedule.get(day_key.upper()) or []
    if not isinstance(windows, list) or not windows:
        return False

    local_minutes = local.hour * 60 + local.minute
    for window in windows:
        if not isinstance(window, (list, tuple)) or len(window) != 2:
            continue
        start = _parse_hhmm(str(window[0]))
        end = _parse_hhmm(str(window[1]))
        if start is None or end is None:
            continue
        start_m = start[0] * 60 + start[1]
        end_m = end[0] * 60 + end[1]
        if start_m <= local_minutes < end_m:
            return True
    return False


async def get_after_hours_settings(
    session: AsyncSession,
    group_id: int,
) -> GroupAfterHoursSettings:
    result = await session.execute(
        select(GroupAfterHoursSettings).where(GroupAfterHoursSettings.group_id == group_id),
    )
    row = result.scalar_one_or_none()
    if row is not None:
        if not row.working_hours:
            row.working_hours = dict(DEFAULT_WORKING_HOURS)
        return row
    row = GroupAfterHoursSettings(
        group_id=group_id,
        working_hours=dict(DEFAULT_WORKING_HOURS),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


@dataclass(frozen=True)
class AfterHoursOutboundJob:
    bot_id: int
    payload: dict[str, Any]
    request_id: str
    chat_id: int
    message_id: int
    text_preview: str
    scope: dict[str, int]


@dataclass
class AfterHoursScanResult:
    sent: int = 0
    skipped: int = 0
    outbounds: list[AfterHoursOutboundJob] = field(default_factory=list)


async def _has_operator_reply_since(
    session: AsyncSession,
    *,
    chat_id: int,
    since: datetime,
) -> bool:
    result = await session.execute(
        select(ChatMessage.id)
        .where(
            ChatMessage.chat_id == chat_id,
            ChatMessage.direction == MessageDirection.OUTBOUND,
            ChatMessage.sender_user_id.is_not(None),
            ChatMessage.created_at >= since,
        )
        .limit(1),
    )
    return result.scalar_one_or_none() is not None


async def _prepare_auto_reply(
    session: AsyncSession,
    *,
    assignment: ContactGroupAssignment,
    settings: GroupAfterHoursSettings,
    chat: Chat,
) -> AfterHoursOutboundJob | None:
    text = (settings.reply_text or "").strip()
    if not text:
        return None

    contact = await session.get(Contact, assignment.contact_id)
    if contact is None or chat.bot_id is None:
        return None
    if contact.telegram_user_id is None:
        logger.info(
            "after_hours_auto_reply_skipped_no_external_id",
            contact_id=assignment.contact_id,
            chat_id=chat.id,
        )
        return None

    pending_at = assignment.pending_inbound_at
    if pending_at is None:
        return None
    if await _has_operator_reply_since(session, chat_id=chat.id, since=_utc_naive(pending_at)):
        return None

    external_message_id = (
        f"after_hours:{assignment.id}:{int(_utc_naive(pending_at).timestamp())}"
    )
    message = ChatMessage(
        chat_id=chat.id,
        lead_id=chat.current_lead_id,
        direction=MessageDirection.OUTBOUND,
        kind=MessageKind.TEXT,
        text=text,
        attachments=[],
        sender_user_id=None,
        external_message_id=external_message_id,
        external_event_id=f"after_hours:{generate_ulid()}",
        reply_to_message_id=None,
    )
    session.add(message)
    await session.flush()

    chat.last_message_at = utc_now()
    chat.last_message_preview = text[:200]
    assignment.after_hours_auto_replied_at = utc_now()
    await session.flush()

    scope = await chat_event_scope(session, chat.id)
    return AfterHoursOutboundJob(
        bot_id=int(chat.bot_id),
        payload={
            "internal_id": message.id,
            "contact": {"telegram_user_id": int(contact.telegram_user_id)},
            "message": {"text": text},
            "attachments": [],
            "reply_to_external_id": None,
        },
        request_id=f"after-hours-{message.id}",
        chat_id=chat.id,
        message_id=message.id,
        text_preview=text[:200],
        scope=scope or {},
    )


async def scan_after_hours_auto_replies(session: AsyncSession) -> AfterHoursScanResult:
    now = utc_now()
    result = await session.execute(
        select(ContactGroupAssignment, GroupAfterHoursSettings)
        .join(
            GroupAfterHoursSettings,
            GroupAfterHoursSettings.group_id == ContactGroupAssignment.group_id,
        )
        .where(
            GroupAfterHoursSettings.enabled.is_(True),
            ContactGroupAssignment.pending_inbound_at.is_not(None),
        )
        .order_by(ContactGroupAssignment.pending_inbound_at.asc())
        .limit(100),
    )
    rows = result.all()
    sent = 0
    skipped = 0
    outbounds: list[AfterHoursOutboundJob] = []

    for assignment, settings in rows:
        pending_at = assignment.pending_inbound_at
        if pending_at is None:
            skipped += 1
            continue
        pending_naive = _utc_naive(pending_at)

        # Already replied for this pending cycle.
        if (
            assignment.after_hours_auto_replied_at is not None
            and _utc_naive(assignment.after_hours_auto_replied_at) >= pending_naive
        ):
            skipped += 1
            continue

        # Cooldown between auto-replies regardless of pending cycle.
        if (
            assignment.after_hours_auto_replied_at is not None
            and settings.cooldown_minutes > 0
            and _utc_naive(assignment.after_hours_auto_replied_at)
            + timedelta(minutes=int(settings.cooldown_minutes))
            > now
        ):
            skipped += 1
            continue

        if is_within_working_hours(
            now,
            timezone=settings.timezone,
            working_hours=settings.working_hours,
        ):
            skipped += 1
            continue

        delay = max(1, int(settings.delay_minutes))
        if now < pending_naive + timedelta(minutes=delay):
            skipped += 1
            continue

        chat_result = await session.execute(
            select(Chat)
            .where(
                Chat.contact_id == assignment.contact_id,
                Chat.assigned_group_id == assignment.group_id,
            )
            .order_by(Chat.id.desc())
            .limit(1),
        )
        chat = chat_result.scalar_one_or_none()
        if chat is None or chat.bot_id is None:
            skipped += 1
            continue

        job = await _prepare_auto_reply(
            session,
            assignment=assignment,
            settings=settings,
            chat=chat,
        )
        if job is None:
            skipped += 1
            continue
        outbounds.append(job)
        sent += 1
        logger.info(
            "after_hours_auto_reply_prepared",
            chat_id=job.chat_id,
            contact_id=assignment.contact_id,
            group_id=assignment.group_id,
            message_id=job.message_id,
        )

    return AfterHoursScanResult(sent=sent, skipped=skipped, outbounds=outbounds)
