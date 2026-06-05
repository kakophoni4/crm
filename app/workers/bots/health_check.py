from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.modules.bots.hmac_util import sign_health_get
from app.modules.bots.repository import BotRepository
from app.realtime.events import publish
from app.shared.db import get_session_factory

logger = structlog.get_logger(__name__)


async def bot_health_check(_job_type: str, payload: dict[str, Any]) -> None:
    bot_id = int(payload["bot_id"])
    session_factory = get_session_factory()

    async with session_factory() as session:
        bot_repo = BotRepository(session)
        bot = await bot_repo.get_by_id(bot_id)
        if bot is None or not bot.is_active:
            return

        health_url = bot.health_url
        if not health_url:
            return

        previous_status = bot.last_health_status
        new_status = "unhealthy"
        checked_at = datetime.now(UTC)

        try:
            secret = await bot_repo.decrypt_outbound_secret(bot)
            timestamp = str(int(checked_at.timestamp()))
            signature = sign_health_get(health_url, timestamp, secret)
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    health_url,
                    headers={
                        "X-CRM-Timestamp": timestamp,
                        "X-CRM-Signature": signature,
                    },
                )
            new_status = "healthy" if response.status_code == 200 else "unhealthy"
        except Exception as exc:
            logger.warning("bot_health_check_failed", bot_id=bot_id, error=str(exc))
            new_status = "unhealthy"

        bot.last_health_status = new_status
        bot.last_health_checked_at = checked_at
        bot.last_seen_at = checked_at if new_status == "healthy" else bot.last_seen_at
        await bot_repo.save(bot)
        await session.commit()

        if previous_status != new_status:
            await publish(
                "bot.health_changed",
                {
                    "bot_id": bot.id,
                    "bot_code": bot.code,
                    "from_status": previous_status,
                    "to_status": new_status,
                },
            )


async def schedule_all_health_checks() -> None:
    from app.workers.bots.queue import enqueue

    session_factory = get_session_factory()
    async with session_factory() as session:
        bots = await BotRepository(session).list_bots()
        active = [b for b in bots if b.is_active and b.health_url]
        await session.commit()

    for bot in active:
        await enqueue("bot_health_check", {"bot_id": bot.id})
