from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.schemas import ChatReferralResponse
from app.modules.chats.service import ChatService
from app.modules.db.models.bot import Bot
from app.modules.db.models.chat import Chat
from app.modules.db.models.contact_referral import ContactReferral
from app.modules.db.models.contact_referral_code import ContactReferralCode
from app.modules.db.models.enums import BotChannel
from app.modules.db.models.user import User
from app.modules.referrals.codes import (
    build_referral_url,
    extract_ref_code,
    generate_referral_code,
    normalize_ref_code,
)
from app.shared.exceptions import NotFound


class ReferralService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_chat_referral(self, actor: User, chat_id: int) -> ChatReferralResponse:
        await ChatService(self._session).get_chat(actor, chat_id)
        chat = await self._session.get(Chat, chat_id)
        if chat is None or chat.bot_id is None:
            return ChatReferralResponse(enabled=False)
        bot = await self._session.get(Bot, chat.bot_id)
        if bot is None or not bot.referrals_enabled:
            return ChatReferralResponse(enabled=False)
        channel = bot.channel if isinstance(bot.channel, str) else str(bot.channel)
        if channel != BotChannel.TELEGRAM:
            return ChatReferralResponse(enabled=False)
        code = await self._ensure_code(contact_id=chat.contact_id, bot_id=bot.id)
        count = await self._count_referrals(referrer_contact_id=chat.contact_id, bot_id=bot.id)
        return ChatReferralResponse(
            enabled=True,
            url=build_referral_url(bot.telegram_username, code),
            code=code,
            count=count,
        )

    async def maybe_attribute(
        self,
        *,
        bot: Bot,
        referred_contact_id: int,
        inner: dict | None,
    ) -> None:
        if not bot.referrals_enabled:
            return
        code = extract_ref_code(inner)
        if not code:
            return
        owner = await self._session.execute(
            select(ContactReferralCode).where(ContactReferralCode.code == code),
        )
        row = owner.scalar_one_or_none()
        if row is None or row.bot_id != bot.id or row.contact_id == referred_contact_id:
            return
        stmt = (
            insert(ContactReferral)
            .values(
                bot_id=bot.id,
                referrer_contact_id=row.contact_id,
                referred_contact_id=referred_contact_id,
                code=code,
            )
            .on_conflict_do_nothing(index_elements=["bot_id", "referred_contact_id"])
        )
        await self._session.execute(stmt)

    async def _ensure_code(self, *, contact_id: int, bot_id: int) -> str:
        existing = await self._session.execute(
            select(ContactReferralCode).where(
                ContactReferralCode.contact_id == contact_id,
                ContactReferralCode.bot_id == bot_id,
            ),
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            return row.code
        for _ in range(8):
            candidate = generate_referral_code()
            stmt = (
                insert(ContactReferralCode)
                .values(contact_id=contact_id, bot_id=bot_id, code=candidate)
                .on_conflict_do_nothing()
                .returning(ContactReferralCode.code)
            )
            inserted = (await self._session.execute(stmt)).scalar_one_or_none()
            if inserted is not None:
                return str(inserted)
            again = await self._session.execute(
                select(ContactReferralCode.code).where(
                    ContactReferralCode.contact_id == contact_id,
                    ContactReferralCode.bot_id == bot_id,
                ),
            )
            found = again.scalar_one_or_none()
            if found is not None:
                return str(found)
        raise NotFound(message="Не удалось создать реферальный код")

    async def _count_referrals(self, *, referrer_contact_id: int, bot_id: int) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(ContactReferral)
            .where(
                ContactReferral.referrer_contact_id == referrer_contact_id,
                ContactReferral.bot_id == bot_id,
            ),
        )
        return int(result.scalar_one() or 0)


def parse_ref_code(raw: str | None) -> str | None:
    return normalize_ref_code(raw)
