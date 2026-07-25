from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.green_api import (
    default_green_api_url,
    default_green_media_url,
    sync_green_webhook,
    whatsapp_webhook_url,
)
from app.modules.bots.hmac_util import sign_health_get, verify_inbound
from app.modules.bots.ip_allowlist import ip_allowed
from app.modules.bots.repository import BotEventInboxRepository, BotListRow, BotRepository
from app.modules.bots.schemas import (
    BotCreateRequest,
    BotCreateResponse,
    BotGroupAssignmentsRequest,
    BotHealthResponse,
    BotListResponse,
    BotResponse,
    BotSecretsResponse,
    BotUpdateRequest,
    RotateSecretResponse,
    WaBridgeBotConfig,
    WaBridgeConfigResponse,
)
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.bot import Bot
from app.modules.db.models.enums import BotChannel, BotOwnerType, UserRole
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, visible_department_ids
from app.realtime.events import publish
from app.shared.exceptions import (
    AuthenticationRequired,
    Conflict,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from app.modules.leads.service_types import DEFAULT_BOT_SERVICE_TYPES
from app.shared.settings import get_settings
from app.workers.bots.queue import enqueue

logger = structlog.get_logger(__name__)

REPLAY_WINDOW_SECONDS = 300


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat()


def _build_owner_label(
    *,
    department_name: str | None,
    assigned_group_names: list[str],
) -> str:
    dept_part = department_name or "неизвестный отдел"
    if not assigned_group_names:
        return f"Отдел: {dept_part} (не распределён)"
    if len(assigned_group_names) == 1:
        return f"Отдел: {dept_part} → {assigned_group_names[0]}"
    groups = ", ".join(assigned_group_names)
    return f"Отдел: {dept_part} → {groups}"


def _bot_channel(bot: Bot) -> BotChannel:
    raw = bot.channel if isinstance(bot.channel, BotChannel) else str(bot.channel)
    try:
        return BotChannel(raw)
    except ValueError:
        return BotChannel.TELEGRAM


def _to_response(row: BotListRow) -> BotResponse:
    bot = row.bot
    settings = get_settings()
    channel = _bot_channel(bot)
    allowlist = [str(item) for item in bot.ip_allowlist] if bot.ip_allowlist else None
    owner_label = _build_owner_label(
        department_name=row.department_name,
        assigned_group_names=row.assigned_group_names,
    )
    webhook_url = None
    if channel == BotChannel.WHATSAPP and bot.green_instance_id:
        webhook_url = whatsapp_webhook_url(settings.wa_bridge_webhook_public_base, bot.code)
    return BotResponse(
        id=bot.id,
        code=bot.code,
        name=bot.name,
        channel=channel,
        department_id=bot.department_id,
        department_name=row.department_name,
        assigned_group_ids=row.assigned_group_ids,
        assigned_group_names=row.assigned_group_names,
        owner_label=owner_label,
        owner_type=BotOwnerType(bot.owner_type),
        owner_id=bot.owner_id,
        outbound_url=bot.outbound_url,
        health_url=bot.health_url,
        ip_allowlist=allowlist,
        is_active=bot.is_active,
        green_api_url=bot.green_api_url,
        green_media_url=bot.green_media_url,
        green_instance_id=bot.green_instance_id,
        has_green_api_token=bot.green_api_token_encrypted is not None,
        whatsapp_webhook_url=webhook_url,
        service_types=list(bot.service_types or DEFAULT_BOT_SERVICE_TYPES),
        default_owner_user_id=bot.default_owner_user_id,
        default_owner_full_name=None,
        last_seen_at=_iso(bot.last_seen_at),
        last_health_status=bot.last_health_status,
        last_health_checked_at=_iso(bot.last_health_checked_at),
        created_at=_iso(bot.created_at) or "",
        updated_at=_iso(bot.updated_at) or "",
    )


class BotService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BotRepository(session)
        self._inbox = BotEventInboxRepository(session)

    async def _visible_department_ids(self, actor: User) -> set[int] | str:
        ctx = await ScopeLoader(self._session).load(actor)
        return visible_department_ids(ctx)

    async def _filter_rows(self, actor: User, rows: list[BotListRow]) -> list[BotListRow]:
        visible = await self._visible_department_ids(actor)
        if visible == SCOPE_ALL:
            return rows
        allowed = set(visible)
        return [row for row in rows if row.bot.department_id in allowed]

    async def _get_row_for_actor(self, actor: User, bot_id: int) -> BotListRow:
        row = await self._repo.get_list_row(bot_id)
        if row is None:
            raise NotFound(message="Bot not found")
        visible = await self._visible_department_ids(actor)
        if visible != SCOPE_ALL and row.bot.department_id not in set(visible):
            raise NotFound(message="Bot not found")
        return row

    async def _sync_owner_from_assignments(self, bot: Bot) -> None:
        group_ids = await self._repo.list_assigned_group_ids(bot.id)
        if len(group_ids) == 1:
            bot.owner_type = BotOwnerType.GROUP
            bot.owner_id = group_ids[0]
        else:
            bot.owner_type = BotOwnerType.DEPARTMENT
            bot.owner_id = bot.department_id

    async def list_bots(self, actor: User) -> BotListResponse:
        rows = await self._filter_rows(actor, await self._repo.list_bots_with_meta())
        return BotListResponse(items=[_to_response(row) for row in rows])

    async def get_bot(self, bot_id: int, actor: User) -> BotResponse:
        row = await self._get_row_for_actor(actor, bot_id)
        return _to_response(row)

    async def create_bot(self, body: BotCreateRequest) -> BotCreateResponse:
        department_id = body.department_id
        if department_id is None:
            if body.owner_type != BotOwnerType.DEPARTMENT:
                raise ValidationError(message="Admin must assign bot to a department")
            department_id = body.owner_id
        if department_id is None or not await self._repo.department_exists(department_id):
            raise ValidationError(message="department_id not found")

        existing = await self._repo.get_by_code(body.code)
        if existing is not None:
            raise Conflict(message="Bot code already exists")

        settings = get_settings()
        inbound_secret = body.inbound_secret
        outbound_secret = body.outbound_secret
        outbound_url = body.outbound_url
        health_url = body.health_url
        green_api_url = body.green_api_url
        green_media_url = body.green_media_url
        green_instance_id = body.green_instance_id
        green_token_enc: bytes | None = None

        if body.channel == BotChannel.WHATSAPP:
            assert green_instance_id and body.green_api_token
            inbound_secret = secrets.token_urlsafe(32)
            outbound_secret = secrets.token_urlsafe(32)
            outbound_url = settings.wa_bridge_outbound_url
            health_url = settings.wa_bridge_health_url
            green_api_url = green_api_url or default_green_api_url(green_instance_id)
            green_media_url = green_media_url or default_green_media_url(green_instance_id)
            green_token_enc = await self._repo.encrypt_green_api_token(body.green_api_token)

        assert inbound_secret and outbound_secret and outbound_url

        bot = await self._repo.create(
            code=body.code,
            name=body.name,
            department_id=department_id,
            owner_type=BotOwnerType.DEPARTMENT,
            owner_id=department_id,
            outbound_url=outbound_url,
            health_url=health_url,
            ip_allowlist=body.ip_allowlist,
            inbound_secret=inbound_secret,
            outbound_secret=outbound_secret,
            channel=body.channel,
            green_api_url=green_api_url,
            green_media_url=green_media_url,
            green_instance_id=green_instance_id,
            green_api_token_encrypted=green_token_enc,
            service_types=body.service_types,
            default_owner_user_id=body.default_owner_user_id,
        )
        await self._session.commit()

        if body.channel == BotChannel.WHATSAPP:
            await self._sync_whatsapp_webhook(bot, api_token=body.green_api_token)

        row = await self._repo.get_list_row(bot.id)
        assert row is not None
        response = _to_response(row)
        secrets_response = BotSecretsResponse(
            inbound_secret=inbound_secret,
            outbound_secret=outbound_secret,
            warning=(
                "WhatsApp: секреты хранятся в CRM, bridge подхватит автоматически."
                if body.channel == BotChannel.WHATSAPP
                else "Это единственный раз, когда секреты видны. Сохраните их в хранилище бота."
            ),
        )
        return BotCreateResponse(
            **response.model_dump(),
            secrets=secrets_response,
        )

    async def update_bot(self, bot_id: int, body: BotUpdateRequest, actor: User) -> BotResponse:
        row = await self._get_row_for_actor(actor, bot_id)
        bot = row.bot

        if body.name is not None:
            bot.name = body.name

        new_department_id = body.department_id
        if (
            new_department_id is None
            and body.owner_type == BotOwnerType.DEPARTMENT
            and body.owner_id
        ):
            new_department_id = body.owner_id

        if new_department_id is not None and new_department_id != bot.department_id:
            if actor.role != UserRole.ADMIN:
                raise PermissionDenied(message="Only admin can move bot between departments")
            if not await self._repo.department_exists(new_department_id):
                raise ValidationError(message="department_id not found")
            bot.department_id = new_department_id
            bot.owner_type = BotOwnerType.DEPARTMENT
            bot.owner_id = new_department_id
            await self._repo.replace_group_assignments(bot.id, [])
            await self._repo.sync_chats_after_group_assignment(
                bot.id,
                new_department_id,
                [],
            )

        if body.outbound_url is not None:
            bot.outbound_url = body.outbound_url
        if body.health_url is not None:
            bot.health_url = body.health_url
        if body.ip_allowlist is not None:
            bot.ip_allowlist = body.ip_allowlist
        if body.is_active is not None:
            bot.is_active = body.is_active
        if body.service_types is not None:
            bot.service_types = body.service_types
        owner_just_set: int | None = None
        if body.clear_default_owner:
            bot.default_owner_user_id = None
        elif body.default_owner_user_id is not None:
            owner = await self._session.get(User, body.default_owner_user_id)
            if owner is None:
                raise ValidationError(message="default_owner_user_id not found")
            bot.default_owner_user_id = body.default_owner_user_id
            owner_just_set = body.default_owner_user_id

        green_token_for_sync: str | None = None
        if _bot_channel(bot) == BotChannel.WHATSAPP:
            if body.green_api_url is not None:
                bot.green_api_url = body.green_api_url.strip() or None
            if body.green_media_url is not None:
                bot.green_media_url = body.green_media_url.strip() or None
            if body.green_instance_id is not None:
                bot.green_instance_id = body.green_instance_id.strip() or None
            if body.green_api_token is not None:
                bot.green_api_token_encrypted = await self._repo.encrypt_green_api_token(
                    body.green_api_token,
                )
                green_token_for_sync = body.green_api_token
            if bot.green_instance_id:
                if not bot.green_api_url:
                    bot.green_api_url = default_green_api_url(bot.green_instance_id)
                if not bot.green_media_url:
                    bot.green_media_url = default_green_media_url(bot.green_instance_id)

        await self._repo.save(bot)
        if owner_just_set is not None:
            from app.modules.contacts.ownership import apply_bot_default_owner_to_existing

            await apply_bot_default_owner_to_existing(
                self._session,
                bot_id=bot.id,
                owner_user_id=owner_just_set,
            )
        await self._session.commit()

        if _bot_channel(bot) == BotChannel.WHATSAPP and bot.green_instance_id:
            await self._sync_whatsapp_webhook(bot, api_token=green_token_for_sync)
        refreshed_row = await self._repo.get_list_row(bot.id)
        assert refreshed_row is not None
        return _to_response(refreshed_row)

    async def set_group_assignments(
        self,
        bot_id: int,
        body: BotGroupAssignmentsRequest,
        actor: User,
    ) -> BotResponse:
        row = await self._get_row_for_actor(actor, bot_id)
        bot = row.bot

        if actor.role == UserRole.ADMIN:
            pass
        elif actor.role == UserRole.SENIOR:
            if actor.department_id != bot.department_id:
                raise PermissionDenied(message="Bot is outside your department")
        else:
            raise PermissionDenied(message="Insufficient permissions")

        valid_group_ids = await self._repo.groups_in_department(body.group_ids, bot.department_id)
        if len(valid_group_ids) != len(set(body.group_ids)):
            raise ValidationError(message="All groups must belong to the bot department")

        await self._repo.replace_group_assignments(bot.id, valid_group_ids)
        await self._sync_owner_from_assignments(bot)
        await self._repo.sync_chats_after_group_assignment(
            bot.id,
            bot.department_id,
            valid_group_ids,
        )
        await self._repo.save(bot)
        await self._session.commit()
        refreshed_row = await self._repo.get_list_row(bot.id)
        assert refreshed_row is not None
        return _to_response(refreshed_row)

    async def soft_delete(self, bot_id: int, actor: User) -> BotResponse:
        row = await self._get_row_for_actor(actor, bot_id)
        bot = row.bot
        bot.is_active = False
        await self._repo.save(bot)
        await self._session.commit()
        refreshed_row = await self._repo.get_list_row(bot.id)
        assert refreshed_row is not None
        return _to_response(refreshed_row)

    async def rotate_secret(self, bot_id: int, kind: str) -> RotateSecretResponse:
        bot = await self._repo.get_by_id(bot_id)
        if bot is None:
            raise NotFound(message="Bot not found")
        new_secret = secrets.token_urlsafe(32)
        await self._repo.rotate_secret(bot, kind, new_secret)
        await self._session.commit()
        await publish(
            "bot.secret_rotated",
            {"bot_id": bot.id, "bot_code": bot.code, "kind": kind},
        )
        return RotateSecretResponse(kind=kind, secret=new_secret)  # type: ignore[arg-type]

    async def check_health(self, bot_id: int) -> BotHealthResponse:
        bot = await self._repo.get_by_id(bot_id)
        if bot is None:
            raise NotFound(message="Bot not found")
        if not bot.health_url:
            raise ValidationError(message="health_url is not configured")

        checked_at = datetime.now(UTC)
        status = "unhealthy"
        http_status: int | None = None
        try:
            secret = await self._repo.decrypt_outbound_secret(bot)
            timestamp = str(int(checked_at.timestamp()))
            signature = sign_health_get(bot.health_url, timestamp, secret)
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    bot.health_url,
                    headers={
                        "X-CRM-Timestamp": timestamp,
                        "X-CRM-Signature": signature,
                    },
                )
            http_status = response.status_code
            status = "healthy" if response.status_code == 200 else "unhealthy"
        except Exception as exc:
            logger.warning("bot_health_manual_failed", bot_id=bot_id, error=str(exc))

        previous = bot.last_health_status
        bot.last_health_status = status
        bot.last_health_checked_at = checked_at
        if status == "healthy":
            bot.last_seen_at = checked_at
        await self._repo.save(bot)
        await self._session.commit()

        if previous != status:
            await publish(
                "bot.health_changed",
                {
                    "bot_id": bot.id,
                    "bot_code": bot.code,
                    "from_status": previous,
                    "to_status": status,
                },
            )

        return BotHealthResponse(
            bot_id=bot.id,
            status=status,
            checked_at=checked_at.isoformat(),
            http_status=http_status,
        )

    async def get_wa_bridge_config(self, sync_secret: str) -> WaBridgeConfigResponse:
        settings = get_settings()
        if not sync_secret or not hmac.compare_digest(sync_secret, settings.wa_bridge_sync_secret):
            raise AuthenticationRequired(message="Unauthorized")
        items: list[WaBridgeBotConfig] = []
        for bot in await self._repo.list_active_whatsapp_bots():
            api_url = bot.green_api_url or default_green_api_url(bot.green_instance_id or "")
            media_url = bot.green_media_url or default_green_media_url(bot.green_instance_id or "")
            items.append(
                WaBridgeBotConfig(
                    bot_code=bot.code,
                    inbound_secret=await self._repo.decrypt_inbound_secret(bot),
                    outbound_secret=await self._repo.decrypt_outbound_secret(bot),
                    green_api_url=api_url,
                    green_media_url=media_url,
                    green_instance_id=str(bot.green_instance_id),
                    green_api_token=await self._repo.decrypt_green_api_token(bot),
                ),
            )
        return WaBridgeConfigResponse(items=items)

    async def _sync_whatsapp_webhook(self, bot: Bot, *, api_token: str | None) -> None:
        if not bot.green_instance_id:
            return
        settings = get_settings()
        token = api_token
        if token is None:
            if bot.green_api_token_encrypted is None:
                return
            token = await self._repo.decrypt_green_api_token(bot)
        api_url = bot.green_api_url or default_green_api_url(bot.green_instance_id)
        webhook = whatsapp_webhook_url(settings.wa_bridge_webhook_public_base, bot.code)
        try:
            await sync_green_webhook(
                api_url=api_url,
                instance_id=bot.green_instance_id,
                api_token=token,
                webhook_url=webhook,
            )
            logger.info("whatsapp_webhook_synced", bot_code=bot.code, webhook_url=webhook)
        except Exception as exc:
            logger.warning("whatsapp_webhook_sync_failed", bot_code=bot.code, error=str(exc))
            if get_settings().app_env == "dev":
                logger.info("whatsapp_webhook_sync_ignored_in_dev", bot_code=bot.code)
                return
            raise ValidationError(
                message=f"Бот сохранён, но GREEN API webhook не настроен: {exc}",
            ) from exc

    async def ingest_event(
        self,
        *,
        bot_code: str,
        event_id: str,
        timestamp: str,
        signature: str,
        body: bytes,
        payload: dict[str, Any],
        client_ip: str,
    ) -> str:
        bot = await self._repo.get_by_code(bot_code)
        if bot is None or not bot.is_active:
            await self._emit_signature_invalid(bot_code, event_id, "bot_inactive")
            raise AuthenticationRequired(message="Unauthorized")

        if not ip_allowed(client_ip, bot.ip_allowlist):
            await self._emit_signature_invalid(bot_code, event_id, "ip_denied")
            raise AuthenticationRequired(message="Unauthorized")

        try:
            ts = int(timestamp)
        except ValueError:
            await self._emit_signature_invalid(bot_code, event_id, "bad_timestamp")
            raise AuthenticationRequired(message="Unauthorized") from None

        now = int(datetime.now(UTC).timestamp())
        if abs(now - ts) > REPLAY_WINDOW_SECONDS:
            await self._emit_signature_invalid(bot_code, event_id, "timestamp_expired")
            raise AuthenticationRequired(message="Unauthorized")

        secret = await self._repo.decrypt_inbound_secret(bot)
        if not verify_inbound(event_id, timestamp, body, secret, signature):
            await self._emit_signature_invalid(bot_code, event_id, "bad_signature")
            raise AuthenticationRequired(message="Unauthorized")

        existing = await self._inbox.get_by_event_id(event_id)
        if existing is not None:
            return "duplicate"

        await self._inbox.create(
            bot_id=bot.id,
            event_id=event_id,
            payload=payload,
            signature=signature,
        )
        await self._session.commit()
        await enqueue("process_bot_event", {"event_id": event_id, "bot_id": bot.id})
        return "accepted"

    async def _emit_signature_invalid(self, bot_code: str, event_id: str, reason: str) -> None:
        logger.warning(
            "bot_signature_invalid",
            bot_code=bot_code,
            event_id=event_id,
            reason=reason,
        )
        await publish(
            "bot.signature_invalid",
            {"bot_code": bot_code, "event_id": event_id},
        )
