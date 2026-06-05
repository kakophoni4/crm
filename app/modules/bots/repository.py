from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.crypto import decrypt_secret, encrypt_secret
from app.modules.db.models.bot import Bot
from app.modules.db.models.bot_event_inbox import BotEventInbox
from app.modules.db.models.bot_outbound_log import BotOutboundLog
from app.modules.db.models.enums import BotOutboundStatus, BotOwnerType


class BotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_bots(self) -> list[Bot]:
        result = await self._session.execute(select(Bot).order_by(Bot.code))
        return list(result.scalars().all())

    async def get_by_id(self, bot_id: int) -> Bot | None:
        return await self._session.get(Bot, bot_id)

    async def get_by_code(self, code: str) -> Bot | None:
        result = await self._session.execute(select(Bot).where(Bot.code == code))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        code: str,
        name: str,
        owner_type: BotOwnerType,
        owner_id: int,
        outbound_url: str,
        health_url: str | None,
        ip_allowlist: list[str] | None,
        inbound_secret: str,
        outbound_secret: str,
    ) -> Bot:
        inbound_enc = await encrypt_secret(self._session, inbound_secret)
        outbound_enc = await encrypt_secret(self._session, outbound_secret)
        bot = Bot(
            code=code,
            name=name,
            owner_type=owner_type,
            owner_id=owner_id,
            outbound_url=outbound_url,
            health_url=health_url,
            ip_allowlist=ip_allowlist,
            inbound_secret_encrypted=inbound_enc,
            outbound_secret_encrypted=outbound_enc,
        )
        self._session.add(bot)
        await self._session.flush()
        return bot

    async def save(self, bot: Bot) -> Bot:
        await self._session.flush()
        return bot

    async def decrypt_inbound_secret(self, bot: Bot) -> str:
        return await decrypt_secret(self._session, bot.inbound_secret_encrypted)

    async def decrypt_outbound_secret(self, bot: Bot) -> str:
        return await decrypt_secret(self._session, bot.outbound_secret_encrypted)

    async def rotate_secret(self, bot: Bot, kind: str, new_secret: str) -> None:
        encrypted = await encrypt_secret(self._session, new_secret)
        if kind == "inbound":
            bot.inbound_secret_encrypted = encrypted
        else:
            bot.outbound_secret_encrypted = encrypted
        await self._session.flush()

    async def owner_exists(self, owner_type: BotOwnerType, owner_id: int) -> bool:
        table = "departments" if owner_type == BotOwnerType.DEPARTMENT else "groups"
        result = await self._session.execute(
            text(f"SELECT 1 FROM {table} WHERE id = :oid LIMIT 1"),
            {"oid": owner_id},
        )
        return result.scalar_one_or_none() is not None


class BotEventInboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_event_id(self, event_id: str) -> BotEventInbox | None:
        result = await self._session.execute(
            select(BotEventInbox).where(BotEventInbox.event_id == event_id),
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        bot_id: int,
        event_id: str,
        payload: dict[str, Any],
        signature: str,
    ) -> BotEventInbox:
        row = BotEventInbox(
            bot_id=bot_id,
            event_id=event_id,
            payload=payload,
            signature=signature,
            status="received",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_for_processing(self, event_id: str) -> BotEventInbox | None:
        return await self.get_by_event_id(event_id)

    async def mark_processing(self, row: BotEventInbox) -> None:
        row.status = "processing"
        await self._session.flush()

    async def mark_done(self, row: BotEventInbox) -> None:
        row.status = "done"
        row.processed_at = datetime.now(UTC)
        await self._session.flush()

    async def mark_failed(self, row: BotEventInbox, error: str) -> None:
        row.status = "failed"
        row.last_error = error[:2000]
        row.processed_at = datetime.now(UTC)
        await self._session.flush()


class BotOutboundLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, log_id: int) -> BotOutboundLog | None:
        return await self._session.get(BotOutboundLog, log_id)

    async def get_by_request_id(self, request_id: str) -> BotOutboundLog | None:
        result = await self._session.execute(
            select(BotOutboundLog).where(BotOutboundLog.request_id == request_id),
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        bot_id: int,
        request_id: str,
        command: str,
        payload: dict[str, Any],
    ) -> BotOutboundLog:
        row = BotOutboundLog(
            bot_id=bot_id,
            request_id=request_id,
            command=command,
            payload=payload,
            status=BotOutboundStatus.QUEUED,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def save(self, row: BotOutboundLog) -> None:
        await self._session.flush()
