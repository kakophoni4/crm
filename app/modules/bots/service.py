from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.hmac_util import sign_health_get, verify_inbound
from app.modules.bots.ip_allowlist import ip_allowed
from app.modules.bots.repository import BotEventInboxRepository, BotRepository
from app.modules.bots.schemas import (
    BotCreateRequest,
    BotCreateResponse,
    BotHealthResponse,
    BotListResponse,
    BotResponse,
    BotSecretsResponse,
    BotUpdateRequest,
    RotateSecretResponse,
)
from app.modules.db.models.bot import Bot
from app.modules.db.models.enums import BotOwnerType
from app.realtime.events import publish
from app.shared.exceptions import (
    AuthenticationRequired,
    Conflict,
    NotFound,
    ValidationError,
)
from app.workers.bots.queue import enqueue

logger = structlog.get_logger(__name__)

REPLAY_WINDOW_SECONDS = 300


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat()


def _to_response(bot: Bot) -> BotResponse:
    allowlist = [str(item) for item in bot.ip_allowlist] if bot.ip_allowlist else None
    return BotResponse(
        id=bot.id,
        code=bot.code,
        name=bot.name,
        owner_type=BotOwnerType(bot.owner_type),
        owner_id=bot.owner_id,
        outbound_url=bot.outbound_url,
        health_url=bot.health_url,
        ip_allowlist=allowlist,
        is_active=bot.is_active,
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

    async def list_bots(self) -> BotListResponse:
        bots = await self._repo.list_bots()
        return BotListResponse(items=[_to_response(bot) for bot in bots])

    async def get_bot(self, bot_id: int) -> BotResponse:
        bot = await self._repo.get_by_id(bot_id)
        if bot is None:
            raise NotFound(message="Bot not found")
        return _to_response(bot)

    async def create_bot(self, body: BotCreateRequest) -> BotCreateResponse:
        existing = await self._repo.get_by_code(body.code)
        if existing is not None:
            raise Conflict(message="Bot code already exists")
        if not await self._repo.owner_exists(body.owner_type, body.owner_id):
            raise ValidationError(message="owner_id not found for owner_type")

        bot = await self._repo.create(
            code=body.code,
            name=body.name,
            owner_type=body.owner_type,
            owner_id=body.owner_id,
            outbound_url=body.outbound_url,
            health_url=body.health_url,
            ip_allowlist=body.ip_allowlist,
            inbound_secret=body.inbound_secret,
            outbound_secret=body.outbound_secret,
        )
        await self._session.commit()
        response = _to_response(bot)
        return BotCreateResponse(
            **response.model_dump(),
            secrets=BotSecretsResponse(
                inbound_secret=body.inbound_secret,
                outbound_secret=body.outbound_secret,
            ),
        )

    async def update_bot(self, bot_id: int, body: BotUpdateRequest) -> BotResponse:
        bot = await self._repo.get_by_id(bot_id)
        if bot is None:
            raise NotFound(message="Bot not found")

        if body.name is not None:
            bot.name = body.name
        if body.owner_type is not None:
            bot.owner_type = body.owner_type
        if body.owner_id is not None:
            owner_type = body.owner_type or BotOwnerType(bot.owner_type)
            if not await self._repo.owner_exists(owner_type, body.owner_id):
                raise ValidationError(message="owner_id not found for owner_type")
            bot.owner_id = body.owner_id
        if body.outbound_url is not None:
            bot.outbound_url = body.outbound_url
        if body.health_url is not None:
            bot.health_url = body.health_url
        if body.ip_allowlist is not None:
            bot.ip_allowlist = body.ip_allowlist
        if body.is_active is not None:
            bot.is_active = body.is_active

        await self._repo.save(bot)
        await self._session.commit()
        return _to_response(bot)

    async def soft_delete(self, bot_id: int) -> BotResponse:
        bot = await self._repo.get_by_id(bot_id)
        if bot is None:
            raise NotFound(message="Bot not found")
        bot.is_active = False
        await self._repo.save(bot)
        await self._session.commit()
        return _to_response(bot)

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
        await enqueue("process_bot_event", {"event_id": event_id})
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
