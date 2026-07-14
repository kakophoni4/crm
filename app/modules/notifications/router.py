from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.notifications import service as notif_service
from app.modules.notifications.schemas import (
    EscalationPolicyOut,
    EscalationPolicyPatchRequest,
    NotificationBotAdminOut,
    NotificationBotAdminPatchRequest,
    NotificationSettingsOut,
    NotificationSettingsPatchRequest,
    StaffNotificationEventOut,
    StaffNotificationHistoryResponse,
    TelegramLinkCreateRequest,
    TelegramLinkOut,
)
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_checks import is_admin, is_department_senior, is_group_senior
from app.shared.db import get_db
from app.shared.exceptions import PermissionDenied, ValidationError
from app.shared.security.permissions import requires_permission
from app.shared.settings import settings

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])
webhook_router = APIRouter(prefix="/api/v1/notification-bot", tags=["notification-bot"])


def _can_manage_escalation(actor: User) -> bool:
    return is_admin(actor.role) or is_department_senior(actor.role) or is_group_senior(actor.role)


def _link_out(link: Any) -> TelegramLinkOut:
    return TelegramLinkOut(
        id=link.id,
        telegram_user_id=link.telegram_user_id,
        telegram_username=link.telegram_username,
        created_at=link.created_at,
    )


def _escalation_out(
    scope: str,
    own: Any,
    effective: Any,
) -> EscalationPolicyOut:
    return EscalationPolicyOut(
        scope=scope,
        timeout_minutes=effective.timeout_minutes,
        mute_phrases=list(effective.mute_phrases),
        effective_timeout_minutes=effective.timeout_minutes,
        effective_mute_phrases=list(effective.mute_phrases),
        effective_source_scope=effective.source_scope,
        updated_at=effective.updated_at,
        updated_by_name=effective.updated_by_name,
        default_timeout_minutes=notif_service.DEFAULT_GROUP_SENIOR_TIMEOUT,
    )


@router.get("/me", response_model=NotificationSettingsOut)
async def get_my_notification_settings(
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_READ_OWN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationSettingsOut:
    uset = await notif_service.get_or_create_user_settings(db, actor.id)
    links = await notif_service.list_telegram_links(db, actor.id)
    bot = await notif_service.get_bot_settings(db)
    phrases = [str(p) for p in (uset.mute_phrases or []) if str(p).strip()]
    return NotificationSettingsOut(
        group_senior_timeout_minutes=uset.group_senior_timeout_minutes,
        mute_phrases=phrases,
        telegram_links=[_link_out(x) for x in links],
        bot_username=bot.bot_username,
        bot_enabled=bool(bot.is_enabled and bot.bot_token_encrypted),
        can_link_multiple=is_admin(actor.role),
        can_view_history=is_admin(actor.role) or is_department_senior(actor.role),
        can_manage_bot=is_admin(actor.role),
        can_manage_escalation=_can_manage_escalation(actor),
    )


@router.patch("/me", response_model=NotificationSettingsOut)
async def patch_my_notification_settings(
    body: NotificationSettingsPatchRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_READ_OWN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationSettingsOut:
    # Escalation timeout/mute moved to /escalation-policy.
    if body.group_senior_timeout_minutes is not None or body.mute_phrases is not None:
        raise ValidationError(
            message="Таймаут и фразы эскалации настраиваются в блоке эскалации",
        )
    return await get_my_notification_settings(actor, db)


@router.get("/escalation-policy", response_model=EscalationPolicyOut)
async def get_escalation_policy(
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_READ_OWN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EscalationPolicyOut:
    if not _can_manage_escalation(actor):
        raise PermissionDenied(message="Настройка эскалации недоступна для вашей роли")
    scope, own, effective = await notif_service.get_editable_escalation_policy(db, actor)
    return _escalation_out(scope, own, effective)


@router.patch("/escalation-policy", response_model=EscalationPolicyOut)
async def patch_escalation_policy(
    body: EscalationPolicyPatchRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_READ_OWN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EscalationPolicyOut:
    if not _can_manage_escalation(actor):
        raise PermissionDenied(message="Настройка эскалации недоступна для вашей роли")
    scope, _row = await notif_service.upsert_escalation_policy(
        db,
        actor=actor,
        timeout_minutes=body.timeout_minutes,
        mute_phrases=body.mute_phrases,
    )
    scope2, own, effective = await notif_service.get_editable_escalation_policy(db, actor)
    return _escalation_out(scope2 or scope, own, effective)


@router.post("/me/telegram-links", response_model=TelegramLinkOut, status_code=201)
async def create_telegram_link(
    body: TelegramLinkCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_READ_OWN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TelegramLinkOut:
    link = await notif_service.link_telegram(
        db,
        actor=actor,
        telegram_user_id=body.telegram_user_id,
    )
    return _link_out(link)


@router.delete("/me/telegram-links/{link_id}", status_code=204)
async def delete_telegram_link(
    link_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_READ_OWN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await notif_service.unlink_telegram(db, actor=actor, link_id=link_id)


@router.get("/history", response_model=StaffNotificationHistoryResponse)
async def notification_history(
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_READ_OWN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    status: str | None = Query(default=None),
) -> StaffNotificationHistoryResponse:
    if not (is_admin(actor.role) or is_department_senior(actor.role)):
        raise PermissionDenied(message="История доступна старшему отдела и админам")

    from app.modules.db.models.staff_notification_event import StaffNotificationEvent

    stmt = select(StaffNotificationEvent).order_by(StaffNotificationEvent.id.desc())
    if is_department_senior(actor.role) and not is_admin(actor.role):
        if actor.department_id is None:
            return StaffNotificationHistoryResponse(items=[], next_cursor=None)
        stmt = stmt.where(StaffNotificationEvent.department_id == actor.department_id)
    if status:
        stmt = stmt.where(StaffNotificationEvent.status == status)
    if cursor is not None:
        stmt = stmt.where(StaffNotificationEvent.id < cursor)
    stmt = stmt.limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    next_cursor = rows[limit].id if len(rows) > limit else None
    rows = rows[:limit]

    items: list[StaffNotificationEventOut] = []
    for row in rows:
        target_name = None
        if row.target_user is not None:
            target_name = row.target_user.full_name
        items.append(
            StaffNotificationEventOut(
                id=row.id,
                kind=row.kind.value if hasattr(row.kind, "value") else str(row.kind),
                status=row.status.value if hasattr(row.status, "value") else str(row.status),
                contact_id=row.contact_id,
                chat_id=row.chat_id,
                group_id=row.group_id,
                department_id=row.department_id,
                target_user_id=row.target_user_id,
                target_user_name=target_name,
                telegram_user_id=row.telegram_user_id,
                contact_name=row.contact_name,
                body_text=row.body_text,
                created_at=row.created_at,
                acked_at=row.acked_at,
                cancelled_at=row.cancelled_at,
            ),
        )
    return StaffNotificationHistoryResponse(items=items, next_cursor=next_cursor)


@router.get("/bot", response_model=NotificationBotAdminOut)
async def get_notification_bot(
    actor: Annotated[User, Depends(requires_permission(Permission.BOTS_MANAGE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationBotAdminOut:
    if not is_admin(actor.role):
        raise PermissionDenied(message="Только администратор")
    bot = await notif_service.get_bot_settings(db)
    base = settings.app_public_base_url.rstrip("/")
    return NotificationBotAdminOut(
        is_enabled=bot.is_enabled,
        bot_username=bot.bot_username,
        has_token=bot.bot_token_encrypted is not None,
        updated_at=bot.updated_at,
        webhook_hint=f"{base}/api/v1/notification-bot/webhook",
    )


@router.patch("/bot", response_model=NotificationBotAdminOut)
async def patch_notification_bot(
    body: NotificationBotAdminPatchRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.BOTS_MANAGE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationBotAdminOut:
    if not is_admin(actor.role):
        raise PermissionDenied(message="Только администратор")
    if body.bot_token:
        await notif_service.save_bot_token(
            db,
            token=body.bot_token,
            actor_id=actor.id,
            enabled=True if body.is_enabled is None else body.is_enabled,
        )
    elif body.is_enabled is not None:
        bot = await notif_service.get_bot_settings(db)
        bot.is_enabled = body.is_enabled
        bot.updated_by = actor.id
        await db.flush()
    return await get_notification_bot(actor, db)


@webhook_router.post("/webhook")
async def notification_bot_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    bot = await notif_service.get_bot_settings(db)
    if not bot.is_enabled or not bot.webhook_secret:
        return {"ok": True}
    if x_telegram_bot_api_secret_token != bot.webhook_secret:
        return {"ok": True}
    payload = await request.json()
    if isinstance(payload, dict):
        await notif_service.handle_bot_update(db, payload)
    return {"ok": True}


__all__ = ["router", "webhook_router"]
