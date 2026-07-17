from __future__ import annotations

import html
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.bots.crypto import decrypt_secret, encrypt_secret
from app.modules.chats.timeutil import utc_now
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.department import Department
from app.modules.db.models.enums import MessageDirection, UserRole, UserStatus
from app.modules.db.models.group import Group
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.notification_bot_settings import NotificationBotSettings
from app.modules.db.models.staff_notification_event import (
    StaffNotificationEvent,
    StaffNotificationKind,
    StaffNotificationStatus,
)
from app.modules.db.models.staff_escalation_policy import StaffEscalationPolicy
from app.modules.db.models.user import User
from app.modules.db.models.user_group_membership import UserGroupMembership
from app.modules.db.models.user_notification_settings import UserNotificationSettings
from app.modules.db.models.user_telegram_link import UserTelegramLink
from app.modules.notifications import telegram_api
from app.modules.rbac.role_checks import is_admin, is_department_senior, is_group_senior
from app.modules.users.memberships import list_user_group_ids
from app.shared.exceptions import Conflict, NotFound, PermissionDenied, ValidationError
from app.shared.settings import settings

logger = structlog.get_logger(__name__)

DEPT_SENIOR_EXTRA_MINUTES = 10
ADMIN_EXTRA_MINUTES = 10
DEFAULT_GROUP_SENIOR_TIMEOUT = 15


@dataclass
class ResolvedEscalationPolicy:
    timeout_minutes: int
    mute_phrases: list[str]
    source_scope: str | None = None
    updated_at: datetime | None = None
    updated_by_name: str | None = None


def _policy_phrases(row: StaffEscalationPolicy | None) -> list[str]:
    if row is None:
        return []
    return [str(p).strip() for p in (row.mute_phrases or []) if str(p).strip()]


async def resolve_escalation_policy(
    session: AsyncSession,
    *,
    group_id: int,
    department_id: int | None,
) -> ResolvedEscalationPolicy:
    """Pick the newest among org / department / group policies (last write wins)."""
    candidates: list[StaffEscalationPolicy] = []
    org = await session.execute(
        select(StaffEscalationPolicy)
        .where(StaffEscalationPolicy.scope == "org")
        .options(selectinload(StaffEscalationPolicy.updater))
        .limit(1),
    )
    org_row = org.scalar_one_or_none()
    if org_row is not None:
        candidates.append(org_row)
    if department_id is not None:
        dept = await session.execute(
            select(StaffEscalationPolicy)
            .where(
                StaffEscalationPolicy.scope == "department",
                StaffEscalationPolicy.department_id == department_id,
            )
            .options(selectinload(StaffEscalationPolicy.updater))
            .limit(1),
        )
        dept_row = dept.scalar_one_or_none()
        if dept_row is not None:
            candidates.append(dept_row)
    group = await session.execute(
        select(StaffEscalationPolicy)
        .where(
            StaffEscalationPolicy.scope == "group",
            StaffEscalationPolicy.group_id == group_id,
        )
        .options(selectinload(StaffEscalationPolicy.updater))
        .limit(1),
    )
    group_row = group.scalar_one_or_none()
    if group_row is not None:
        candidates.append(group_row)

    if not candidates:
        return ResolvedEscalationPolicy(
            timeout_minutes=DEFAULT_GROUP_SENIOR_TIMEOUT,
            mute_phrases=[],
            source_scope=None,
        )

    winners = sorted(
        candidates,
        key=lambda row: row.updated_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    best = winners[0]
    updater_name = best.updater.full_name if best.updater is not None else None
    return ResolvedEscalationPolicy(
        timeout_minutes=max(1, int(best.timeout_minutes or DEFAULT_GROUP_SENIOR_TIMEOUT)),
        mute_phrases=_policy_phrases(best),
        source_scope=best.scope,
        updated_at=best.updated_at,
        updated_by_name=updater_name,
    )


def _row_as_resolved(row: StaffEscalationPolicy | None) -> ResolvedEscalationPolicy:
    if row is None:
        return ResolvedEscalationPolicy(
            timeout_minutes=DEFAULT_GROUP_SENIOR_TIMEOUT,
            mute_phrases=[],
            source_scope=None,
        )
    return ResolvedEscalationPolicy(
        timeout_minutes=max(1, int(row.timeout_minutes or DEFAULT_GROUP_SENIOR_TIMEOUT)),
        mute_phrases=_policy_phrases(row),
        source_scope=row.scope,
        updated_at=row.updated_at,
        updated_by_name=row.updater.full_name if row.updater is not None else None,
    )


async def get_editable_escalation_policy(
    session: AsyncSession,
    actor: User,
) -> tuple[str, ResolvedEscalationPolicy, ResolvedEscalationPolicy]:
    """Return (scope, own_scope_values, effective_sample). Form shows effective."""
    if is_admin(actor.role):
        result = await session.execute(
            select(StaffEscalationPolicy)
            .where(StaffEscalationPolicy.scope == "org")
            .options(selectinload(StaffEscalationPolicy.updater))
            .limit(1),
        )
        row = result.scalar_one_or_none()
        own = _row_as_resolved(row)
        # Sample any group so admin sees true last-write effective.
        g_row = await session.execute(select(Group.id, Group.department_id).limit(1))
        sample = g_row.first()
        if sample is not None:
            effective = await resolve_escalation_policy(
                session,
                group_id=int(sample[0]),
                department_id=int(sample[1]) if sample[1] is not None else None,
            )
        else:
            effective = own
        return "org", own, effective

    if is_department_senior(actor.role):
        if actor.department_id is None:
            raise ValidationError(message="У старшего отдела не указан отдел")
        result = await session.execute(
            select(StaffEscalationPolicy)
            .where(
                StaffEscalationPolicy.scope == "department",
                StaffEscalationPolicy.department_id == actor.department_id,
            )
            .options(selectinload(StaffEscalationPolicy.updater))
            .limit(1),
        )
        row = result.scalar_one_or_none()
        own = _row_as_resolved(row)
        g_row = await session.execute(
            select(Group.id).where(Group.department_id == actor.department_id).limit(1),
        )
        sample_gid = g_row.scalar_one_or_none()
        if sample_gid is not None:
            effective = await resolve_escalation_policy(
                session,
                group_id=int(sample_gid),
                department_id=actor.department_id,
            )
        else:
            effective = own
        return "department", own, effective

    if is_group_senior(actor.role):
        group_ids = await list_user_group_ids(session, actor.id)
        if not group_ids:
            raise ValidationError(message="Старшему группы нужна хотя бы одна группа")
        sample_gid = int(group_ids[0])
        result = await session.execute(
            select(StaffEscalationPolicy)
            .where(
                StaffEscalationPolicy.scope == "group",
                StaffEscalationPolicy.group_id == sample_gid,
            )
            .options(selectinload(StaffEscalationPolicy.updater))
            .limit(1),
        )
        row = result.scalar_one_or_none()
        own = _row_as_resolved(row)
        group = await session.get(Group, sample_gid)
        effective = await resolve_escalation_policy(
            session,
            group_id=sample_gid,
            department_id=group.department_id if group else None,
        )
        return "group", own, effective

    raise PermissionDenied(message="Настройка эскалации недоступна для вашей роли")


async def upsert_escalation_policy(
    session: AsyncSession,
    *,
    actor: User,
    timeout_minutes: int,
    mute_phrases: list[str],
) -> tuple[str, StaffEscalationPolicy]:
    cleaned = [p.strip() for p in mute_phrases if p and str(p).strip()][:50]
    timeout = max(1, min(1440, int(timeout_minutes)))
    now = utc_now()

    if is_admin(actor.role):
        result = await session.execute(
            select(StaffEscalationPolicy).where(StaffEscalationPolicy.scope == "org").limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = StaffEscalationPolicy(scope="org")
            session.add(row)
        row.timeout_minutes = timeout
        row.mute_phrases = cleaned
        row.updated_by = actor.id
        row.updated_at = now
        await session.flush()
        await session.refresh(row)
        return "org", row

    if is_department_senior(actor.role):
        if actor.department_id is None:
            raise ValidationError(message="У старшего отдела не указан отдел")
        result = await session.execute(
            select(StaffEscalationPolicy).where(
                StaffEscalationPolicy.scope == "department",
                StaffEscalationPolicy.department_id == actor.department_id,
            ).limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = StaffEscalationPolicy(
                scope="department",
                department_id=actor.department_id,
            )
            session.add(row)
        row.timeout_minutes = timeout
        row.mute_phrases = cleaned
        row.updated_by = actor.id
        row.updated_at = now
        await session.flush()
        await session.refresh(row)
        return "department", row

    if is_group_senior(actor.role):
        group_ids = await list_user_group_ids(session, actor.id)
        if not group_ids:
            raise ValidationError(message="Старшему группы нужна хотя бы одна группа")
        last: StaffEscalationPolicy | None = None
        for gid in group_ids:
            result = await session.execute(
                select(StaffEscalationPolicy).where(
                    StaffEscalationPolicy.scope == "group",
                    StaffEscalationPolicy.group_id == gid,
                ).limit(1),
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = StaffEscalationPolicy(scope="group", group_id=gid)
                session.add(row)
            row.timeout_minutes = timeout
            row.mute_phrases = cleaned
            row.updated_by = actor.id
            row.updated_at = now
            last = row
        await session.flush()
        assert last is not None
        await session.refresh(last)
        return "group", last

    raise PermissionDenied(message="Настройка эскалации недоступна для вашей роли")


def _utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def pending_key_from(dt: datetime) -> int:
    return int(_utc_naive(dt).timestamp())


async def get_bot_settings(session: AsyncSession) -> NotificationBotSettings:
    row = await session.get(NotificationBotSettings, 1)
    if row is None:
        row = NotificationBotSettings(id=1)
        session.add(row)
        await session.flush()
        await session.refresh(row)
    return row


def global_mute_phrases(row: NotificationBotSettings) -> list[str]:
    return [str(p).strip() for p in (row.mute_phrases or []) if str(p).strip()][:50]


async def get_global_mute_phrases(session: AsyncSession) -> list[str]:
    return global_mute_phrases(await get_bot_settings(session))


async def set_global_mute_phrases(
    session: AsyncSession,
    *,
    phrases: list[str],
    actor_id: int,
) -> list[str]:
    cleaned = [str(p).strip() for p in phrases if p and str(p).strip()][:50]
    # Dedupe case-insensitively, keep first casing.
    seen: set[str] = set()
    unique: list[str] = []
    for phrase in cleaned:
        key = phrase.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(phrase)
    row = await get_bot_settings(session)
    row.mute_phrases = unique
    row.updated_by = actor_id
    row.updated_at = utc_now()
    await session.flush()
    await session.refresh(row)
    return global_mute_phrases(row)


async def get_bot_token(session: AsyncSession) -> str | None:
    row = await get_bot_settings(session)
    if not row.is_enabled or row.bot_token_encrypted is None:
        return None
    return await decrypt_secret(session, row.bot_token_encrypted)


async def save_bot_token(
    session: AsyncSession,
    *,
    token: str,
    actor_id: int,
    enabled: bool = True,
) -> NotificationBotSettings:
    token = token.strip()
    if not token or ":" not in token:
        raise ValidationError(message="Invalid Telegram bot token")
    me = await telegram_api.get_me(token)
    username = me.get("username")
    secret = secrets.token_urlsafe(24)
    row = await get_bot_settings(session)
    row.bot_token_encrypted = await encrypt_secret(session, token)
    row.bot_username = str(username) if username else None
    row.webhook_secret = secret
    row.is_enabled = enabled
    row.updated_by = actor_id
    row.updated_at = utc_now()
    await session.flush()

    if enabled:
        await register_bot_webhook(session, token=token, secret=secret)
    await session.refresh(row)
    return row


async def register_bot_webhook(
    session: AsyncSession,
    *,
    token: str | None = None,
    secret: str | None = None,
) -> str:
    """Point Telegram webhook at the public API host. Returns the URL."""
    row = await get_bot_settings(session)
    if token is None:
        if row.bot_token_encrypted is None:
            raise ValidationError(message="Сначала сохраните токен бота")
        token = await decrypt_secret(session, row.bot_token_encrypted)
    if secret is None:
        secret = row.webhook_secret
    if not secret:
        secret = secrets.token_urlsafe(24)
        row.webhook_secret = secret
        await session.flush()

    webhook_url = f"{settings.api_public_base_url}/api/v1/notification-bot/webhook"
    try:
        await telegram_api.set_webhook(token, webhook_url, secret)
    except telegram_api.TelegramBotError as exc:
        logger.warning("notification_bot_set_webhook_failed", error=str(exc), url=webhook_url)
        raise ValidationError(
            message=(
                f"Не удалось зарегистрировать webhook ({webhook_url}): {exc}. "
                "Проверьте APP_API_PUBLIC_BASE_URL (должен быть публичный URL API, "
                "например https://api.example.com)."
            ),
        ) from exc
    logger.info("notification_bot_webhook_registered", url=webhook_url)
    return webhook_url


async def set_bot_enabled(
    session: AsyncSession,
    *,
    enabled: bool,
    actor_id: int,
) -> NotificationBotSettings:
    row = await get_bot_settings(session)
    row.is_enabled = enabled
    row.updated_by = actor_id
    row.updated_at = utc_now()
    await session.flush()
    if enabled:
        if row.bot_token_encrypted is None:
            raise ValidationError(message="Сначала сохраните токен бота")
        await register_bot_webhook(session)
    await session.refresh(row)
    return row

async def get_or_create_user_settings(
    session: AsyncSession,
    user_id: int,
) -> UserNotificationSettings:
    row = await session.get(UserNotificationSettings, user_id)
    if row is not None:
        return row
    row = UserNotificationSettings(user_id=user_id)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def list_telegram_links(session: AsyncSession, user_id: int) -> list[UserTelegramLink]:
    result = await session.execute(
        select(UserTelegramLink)
        .where(UserTelegramLink.user_id == user_id)
        .order_by(UserTelegramLink.id.asc()),
    )
    return list(result.scalars().all())


async def link_telegram(
    session: AsyncSession,
    *,
    actor: User,
    telegram_user_id: int,
    telegram_username: str | None = None,
) -> UserTelegramLink:
    if telegram_user_id <= 0:
        raise ValidationError(message="telegram_user_id must be positive")

    existing_tg = await session.execute(
        select(UserTelegramLink).where(UserTelegramLink.telegram_user_id == telegram_user_id),
    )
    taken = existing_tg.scalar_one_or_none()
    if taken is not None and taken.user_id != actor.id:
        raise Conflict(message="Этот Telegram ID уже привязан к другому пользователю")

    if taken is not None and taken.user_id == actor.id:
        return taken

    links = await list_telegram_links(session, actor.id)
    if not is_admin(actor.role) and links:
        raise ValidationError(message="Можно привязать только один Telegram ID")

    link = UserTelegramLink(
        user_id=actor.id,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
    )
    session.add(link)
    await session.flush()
    await session.refresh(link)

    token = await get_bot_token(session)
    if token:
        try:
            await telegram_api.send_message(
                token,
                chat_id=telegram_user_id,
                text=(
                    "✅ <b>CRM подключена</b>\n\n"
                    "Этот чат будет получать уведомления о сообщениях и новых карточках."
                ),
            )
        except telegram_api.TelegramBotError as exc:
            logger.info("notification_link_confirm_failed", error=str(exc))
    return link


async def unlink_telegram(
    session: AsyncSession,
    *,
    actor: User,
    link_id: int,
) -> None:
    link = await session.get(UserTelegramLink, link_id)
    if link is None or link.user_id != actor.id:
        raise NotFound(message="Привязка не найдена")
    await session.delete(link)
    await session.flush()


def _ack_keyboard(event_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "✓ Прочитано", "callback_data": f"ack:{event_id}"}],
        ],
    }


def _new_card_keyboard(event_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "✓ Ознакомился", "callback_data": f"ack:{event_id}"}],
        ],
    }


def _format_inbound(contact_name: str) -> str:
    name = html.escape(contact_name or "Клиент")
    return (
        "📩 <b>Новое сообщение</b>\n"
        f"Вам поступило сообщение от <b>{name}</b>.\n\n"
        "Если отвечать не нужно — нажмите «Прочитано»."
    )


def _format_new_card(contact_name: str) -> str:
    name = html.escape(contact_name or "Клиент")
    return (
        "🆕 <b>Новая карточка</b>\n\n"
        f"Вам назначена новая карточка: <b>{name}</b>.\n"
        "Ознакомьтесь с ней в CRM."
    )


def _format_escalation(level: str, contact_name: str, preview: str | None = None) -> str:
    name = html.escape(contact_name or "Клиент")
    titles = {
        "group": "⏱ Нет ответа в группе",
        "dept": "⚠️ Эскалация: старший отдела",
        "admin": "🚨 Эскалация: администратор",
    }
    title = titles.get(level, "⏱ Эскалация")
    lines = [
        f"<b>{title}</b>",
        f"Нет ответа по контакту <b>{name}</b>",
    ]
    if preview:
        lines.append(f"\n<i>{html.escape(preview[:300])}</i>")
    lines.append("\nНажмите «Прочитано», если уведомление принято.")
    return "\n".join(lines)


async def _links_for_user(session: AsyncSession, user_id: int) -> list[UserTelegramLink]:
    return await list_telegram_links(session, user_id)


async def _already_notified(
    session: AsyncSession,
    *,
    contact_id: int,
    group_id: int,
    pending_key: int,
    target_user_id: int,
    telegram_user_id: int,
    kind: StaffNotificationKind,
) -> bool:
    result = await session.execute(
        select(StaffNotificationEvent.id)
        .where(
            StaffNotificationEvent.contact_id == contact_id,
            StaffNotificationEvent.group_id == group_id,
            StaffNotificationEvent.pending_key == pending_key,
            StaffNotificationEvent.target_user_id == target_user_id,
            StaffNotificationEvent.telegram_user_id == telegram_user_id,
            StaffNotificationEvent.kind == kind,
        )
        .limit(1),
    )
    return result.scalar_one_or_none() is not None


async def _send_to_user(
    session: AsyncSession,
    *,
    user: User,
    kind: StaffNotificationKind,
    text: str,
    keyboard: dict[str, Any],
    contact_id: int | None,
    chat_id: int | None,
    group_id: int | None,
    department_id: int | None,
    pending_key: int | None,
    contact_name: str | None,
) -> int:
    del keyboard  # rebuilt with event id
    token = await get_bot_token(session)
    if not token:
        return 0
    links = await _links_for_user(session, user.id)
    if not links:
        return 0

    sent = 0
    for link in links:
        if (
            pending_key is not None
            and contact_id is not None
            and group_id is not None
            and await _already_notified(
                session,
                contact_id=contact_id,
                group_id=group_id,
                pending_key=pending_key,
                target_user_id=user.id,
                telegram_user_id=link.telegram_user_id,
                kind=kind,
            )
        ):
            continue

        event = StaffNotificationEvent(
            kind=kind,
            status=StaffNotificationStatus.SENT,
            contact_id=contact_id,
            chat_id=chat_id,
            group_id=group_id,
            department_id=department_id,
            target_user_id=user.id,
            telegram_user_id=link.telegram_user_id,
            pending_key=pending_key,
            contact_name=contact_name,
            body_text=text,
        )
        session.add(event)
        await session.flush()

        try:
            kb = (
                _new_card_keyboard(event.id)
                if kind == StaffNotificationKind.NEW_CARD
                else _ack_keyboard(event.id)
            )
            result = await telegram_api.send_message(
                token,
                chat_id=link.telegram_user_id,
                text=text,
                reply_markup=kb,
            )
            event.telegram_message_id = int(result.get("message_id") or 0) or None
            event.body_text = text
            sent += 1
        except telegram_api.TelegramBotError as exc:
            event.status = StaffNotificationStatus.FAILED
            event.error_text = str(exc)[:500]
            logger.warning(
                "staff_notification_send_failed",
                user_id=user.id,
                telegram_user_id=link.telegram_user_id,
                error=str(exc),
            )
        await session.flush()

        if not is_admin(user.role):
            break
    return sent


async def notify_owner_inbound(
    session: AsyncSession,
    *,
    contact_id: int,
    group_id: int,
    chat_id: int,
    owner_user_id: int,
    pending_at: datetime,
    message_preview: str | None = None,
) -> None:
    if _phrase_muted(message_preview, await get_global_mute_phrases(session)):
        return
    owner = await session.get(User, owner_user_id)
    if owner is None or owner.status != UserStatus.ACTIVE:
        return
    contact = await session.get(Contact, contact_id)
    name = contact.full_name if contact else "Клиент"
    group = await session.get(Group, group_id)
    text = _format_inbound(name)
    await _send_to_user(
        session,
        user=owner,
        kind=StaffNotificationKind.INBOUND_MESSAGE,
        text=text,
        keyboard=_ack_keyboard(0),
        contact_id=contact_id,
        chat_id=chat_id,
        group_id=group_id,
        department_id=group.department_id if group else None,
        pending_key=pending_key_from(pending_at),
        contact_name=name,
    )


async def notify_new_card(
    session: AsyncSession,
    *,
    contact_id: int,
    group_id: int,
    chat_id: int | None,
    owner_user_id: int,
) -> None:
    owner = await session.get(User, owner_user_id)
    if owner is None or owner.status != UserStatus.ACTIVE:
        return
    contact = await session.get(Contact, contact_id)
    name = contact.full_name if contact else "Клиент"
    group = await session.get(Group, group_id)
    text = _format_new_card(name)
    await _send_to_user(
        session,
        user=owner,
        kind=StaffNotificationKind.NEW_CARD,
        text=text,
        keyboard=_new_card_keyboard(0),
        contact_id=contact_id,
        chat_id=chat_id,
        group_id=group_id,
        department_id=group.department_id if group else None,
        pending_key=None,
        contact_name=name,
    )


def _phrase_muted(text: str | None, phrases: list[Any]) -> bool:
    if not text or not phrases:
        return False
    lowered = text.casefold()
    for raw in phrases:
        phrase = str(raw or "").strip()
        if phrase and phrase.casefold() in lowered:
            return True
    return False


async def _latest_inbound_text(
    session: AsyncSession,
    chat_id: int | None,
) -> str | None:
    if chat_id is None:
        return None
    result = await session.execute(
        select(ChatMessage.text)
        .where(
            ChatMessage.chat_id == chat_id,
            ChatMessage.direction == MessageDirection.INBOUND,
        )
        .order_by(ChatMessage.id.desc())
        .limit(1),
    )
    return result.scalar_one_or_none()


async def _group_seniors(session: AsyncSession, group_id: int) -> list[User]:
    member_ids = select(UserGroupMembership.user_id).where(
        UserGroupMembership.group_id == group_id,
    )
    result = await session.execute(
        select(User).where(
            User.role == UserRole.GROUP_SENIOR,
            User.status == UserStatus.ACTIVE,
            or_(User.group_id == group_id, User.id.in_(member_ids)),
        ),
    )
    return list(result.scalars().all())


async def _dept_seniors(session: AsyncSession, department_id: int | None) -> list[User]:
    if department_id is None:
        return []
    result = await session.execute(
        select(User).where(
            User.role == UserRole.SENIOR,
            User.status == UserStatus.ACTIVE,
            User.department_id == department_id,
        ),
    )
    users = {u.id: u for u in result.scalars().all()}
    dept = await session.get(Department, department_id)
    if dept is not None and dept.head_user_id is not None:
        head = await session.get(User, dept.head_user_id)
        if head is not None and head.status == UserStatus.ACTIVE:
            users[head.id] = head
    return list(users.values())


async def _admins(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User).where(User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE),
    )
    return list(result.scalars().all())


async def cancel_pending_notifications(
    session: AsyncSession,
    *,
    contact_id: int,
    group_id: int,
) -> None:
    """Drop pending inbound alerts after a reply — do not keep cancelled noise in history."""
    result = await session.execute(
        select(StaffNotificationEvent).where(
            StaffNotificationEvent.contact_id == contact_id,
            StaffNotificationEvent.group_id == group_id,
            StaffNotificationEvent.status == StaffNotificationStatus.SENT,
            StaffNotificationEvent.kind != StaffNotificationKind.NEW_CARD,
        ),
    )
    events = list(result.scalars().all())
    if not events:
        return
    token = await get_bot_token(session)
    for event in events:
        if (
            token
            and event.telegram_user_id is not None
            and event.telegram_message_id is not None
        ):
            await telegram_api.delete_message(
                token,
                chat_id=int(event.telegram_user_id),
                message_id=int(event.telegram_message_id),
            )
        await session.delete(event)
    await session.flush()


async def acknowledge_event(
    session: AsyncSession,
    *,
    event_id: int,
    actor_telegram_user_id: int | None = None,
    actor_user_id: int | None = None,
) -> StaffNotificationEvent:
    event = await session.get(StaffNotificationEvent, event_id)
    if event is None:
        raise NotFound(message="Notification not found")
    if event.status != StaffNotificationStatus.SENT:
        return event

    if actor_telegram_user_id is not None and event.telegram_user_id != actor_telegram_user_id:
        raise ValidationError(message="Not your notification")
    if actor_user_id is not None and event.target_user_id != actor_user_id:
        raise ValidationError(message="Not your notification")

    event.status = StaffNotificationStatus.ACKED
    event.acked_at = utc_now()

    if event.contact_id and event.group_id and event.kind != StaffNotificationKind.NEW_CARD:
        assignment = await session.execute(
            select(ContactGroupAssignment).where(
                ContactGroupAssignment.contact_id == event.contact_id,
                ContactGroupAssignment.group_id == event.group_id,
            ),
        )
        row = assignment.scalar_one_or_none()
        if row is not None:
            row.staff_notify_acked_at = utc_now()
            row.staff_notify_acked_by = event.target_user_id

    token = await get_bot_token(session)
    if token and event.telegram_user_id and event.telegram_message_id:
        await telegram_api.delete_message(
            token,
            chat_id=int(event.telegram_user_id),
            message_id=int(event.telegram_message_id),
        )
    await session.flush()
    return event


async def scan_staff_notification_escalations(session: AsyncSession) -> dict[str, int]:
    """Escalate unanswered inbound notifications: group senior → dept senior → admin."""
    if not await get_bot_token(session):
        return {"group": 0, "dept": 0, "admin": 0}

    now = utc_now()
    result = await session.execute(
        select(ContactGroupAssignment)
        .where(
            ContactGroupAssignment.pending_inbound_at.is_not(None),
            ContactGroupAssignment.staff_notify_acked_at.is_(None),
        )
        .order_by(ContactGroupAssignment.pending_inbound_at.asc())
        .limit(80),
    )
    rows = list(result.scalars().all())
    counts = {"group": 0, "dept": 0, "admin": 0}

    for assignment in rows:
        pending_at = assignment.pending_inbound_at
        if pending_at is None:
            continue
        pending_naive = _utc_naive(pending_at)
        pkey = pending_key_from(pending_at)
        age = now - pending_naive

        group = await session.get(Group, assignment.group_id)
        contact = await session.get(Contact, assignment.contact_id)
        name = contact.full_name if contact else "Клиент"

        from app.modules.db.models.chat import Chat

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
        preview = await _latest_inbound_text(session, chat.id if chat else None)

        # --- group seniors (timeout/mute from scoped policy, last write wins) ---
        seniors = await _group_seniors(session, assignment.group_id)
        policy = await resolve_escalation_policy(
            session,
            group_id=assignment.group_id,
            department_id=group.department_id if group else None,
        )
        timeout = policy.timeout_minutes
        any_group_sent = assignment.staff_notify_group_senior_at is not None
        global_muted = await get_global_mute_phrases(session)
        muted = _phrase_muted(preview, global_muted) or _phrase_muted(
            preview,
            policy.mute_phrases,
        )
        if not muted and age >= timedelta(minutes=timeout):
            for senior in seniors:
                n = await _send_to_user(
                    session,
                    user=senior,
                    kind=StaffNotificationKind.ESCALATION_GROUP_SENIOR,
                    text=_format_escalation("group", name, preview),
                    keyboard=_ack_keyboard(0),
                    contact_id=assignment.contact_id,
                    chat_id=chat.id if chat else None,
                    group_id=assignment.group_id,
                    department_id=group.department_id if group else None,
                    pending_key=pkey,
                    contact_name=name,
                )
                if n:
                    counts["group"] += n
                    any_group_sent = True
        if any_group_sent and assignment.staff_notify_group_senior_at is None:
            assignment.staff_notify_group_senior_at = now

        # If no group seniors exist, start dept timer after group timeout
        group_anchor = assignment.staff_notify_group_senior_at
        if group_anchor is None and not seniors and not muted:
            if age >= timedelta(minutes=timeout):
                assignment.staff_notify_group_senior_at = now
                group_anchor = now

        # --- dept seniors (+10 after group senior wave) ---
        if (
            group_anchor is not None
            and assignment.staff_notify_acked_at is None
            and assignment.staff_notify_dept_senior_at is None
            and now >= _utc_naive(group_anchor) + timedelta(minutes=DEPT_SENIOR_EXTRA_MINUTES)
        ):
            # Skip if any group-senior event was acked
            acked = await session.execute(
                select(StaffNotificationEvent.id)
                .where(
                    StaffNotificationEvent.contact_id == assignment.contact_id,
                    StaffNotificationEvent.group_id == assignment.group_id,
                    StaffNotificationEvent.pending_key == pkey,
                    StaffNotificationEvent.kind == StaffNotificationKind.ESCALATION_GROUP_SENIOR,
                    StaffNotificationEvent.status == StaffNotificationStatus.ACKED,
                )
                .limit(1),
            )
            if acked.scalar_one_or_none() is None:
                for senior in await _dept_seniors(
                    session,
                    group.department_id if group else None,
                ):
                    n = await _send_to_user(
                        session,
                        user=senior,
                        kind=StaffNotificationKind.ESCALATION_DEPT_SENIOR,
                        text=_format_escalation("dept", name, preview),
                        keyboard=_ack_keyboard(0),
                        contact_id=assignment.contact_id,
                        chat_id=chat.id if chat else None,
                        group_id=assignment.group_id,
                        department_id=group.department_id if group else None,
                        pending_key=pkey,
                        contact_name=name,
                    )
                    counts["dept"] += n
                assignment.staff_notify_dept_senior_at = now

        # --- admins (+10 after dept senior, if not acked) ---
        dept_anchor = assignment.staff_notify_dept_senior_at
        if (
            dept_anchor is not None
            and assignment.staff_notify_acked_at is None
            and assignment.staff_notify_admin_at is None
            and now >= _utc_naive(dept_anchor) + timedelta(minutes=ADMIN_EXTRA_MINUTES)
        ):
            acked = await session.execute(
                select(StaffNotificationEvent.id)
                .where(
                    StaffNotificationEvent.contact_id == assignment.contact_id,
                    StaffNotificationEvent.group_id == assignment.group_id,
                    StaffNotificationEvent.pending_key == pkey,
                    StaffNotificationEvent.kind == StaffNotificationKind.ESCALATION_DEPT_SENIOR,
                    StaffNotificationEvent.status == StaffNotificationStatus.ACKED,
                )
                .limit(1),
            )
            if acked.scalar_one_or_none() is None:
                for admin in await _admins(session):
                    n = await _send_to_user(
                        session,
                        user=admin,
                        kind=StaffNotificationKind.ESCALATION_ADMIN,
                        text=_format_escalation("admin", name, preview),
                        keyboard=_ack_keyboard(0),
                        contact_id=assignment.contact_id,
                        chat_id=chat.id if chat else None,
                        group_id=assignment.group_id,
                        department_id=group.department_id if group else None,
                        pending_key=pkey,
                        contact_name=name,
                    )
                    counts["admin"] += n
                assignment.staff_notify_admin_at = now

        await session.flush()

    return counts


async def handle_bot_update(session: AsyncSession, update: dict[str, Any]) -> None:
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        data = str(callback.get("data") or "")
        from_user = callback.get("from") or {}
        tg_id = from_user.get("id")
        cb_id = callback.get("id")
        token = await get_bot_token(session)
        if data.startswith("ack:") and tg_id is not None:
            try:
                event_id = int(data.split(":", 1)[1])
                await acknowledge_event(
                    session,
                    event_id=event_id,
                    actor_telegram_user_id=int(tg_id),
                )
                if token and cb_id:
                    await telegram_api.answer_callback_query(
                        token,
                        callback_query_id=str(cb_id),
                        text="Отмечено как прочитано",
                    )
            except Exception as exc:
                logger.info("notification_ack_failed", error=str(exc))
                if token and cb_id:
                    await telegram_api.answer_callback_query(
                        token,
                        callback_query_id=str(cb_id),
                        text="Не удалось отметить",
                    )
        return

    message = update.get("message")
    if not isinstance(message, dict):
        return
    text = str(message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    token = await get_bot_token(session)
    if not token:
        return

    if text.startswith("/start"):
        await telegram_api.send_message(
            token,
            chat_id=int(chat_id),
            text=(
                "👋 <b>Бот уведомлений CRM</b>\n\n"
                "Бот закрытый: уведомления приходят только после привязки в личном кабинете.\n\n"
                f"Ваш Telegram ID:\n<code>{int(chat_id)}</code>\n\n"
                "Скопируйте его и вставьте в CRM → <b>Уведомления</b> → «Привязать Telegram»."
            ),
        )
        return

    await telegram_api.send_message(
        token,
        chat_id=int(chat_id),
        text=(
            "Этот бот только для уведомлений CRM.\n"
            f"Ваш ID: <code>{int(chat_id)}</code>\n"
            "Привяжите его во вкладке «Уведомления»."
        ),
    )
