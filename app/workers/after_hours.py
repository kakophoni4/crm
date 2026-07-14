from __future__ import annotations

import structlog

from app.modules.contacts.after_hours import scan_after_hours_auto_replies
from app.realtime.events import publish
from app.shared.db import get_session_factory
from app.shared.settings import settings
from app.workers.bots.dispatch_outbound import enqueue_outbound

logger = structlog.get_logger(__name__)


async def after_hours_scan(_job_type: str = "", _payload: dict[str, object] | None = None) -> None:
    del _job_type, _payload
    if not settings.ownership_v2:
        return

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            result = await scan_after_hours_auto_replies(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    for job in result.outbounds:
        try:
            await enqueue_outbound(
                bot_id=job.bot_id,
                command="send_message",
                payload=job.payload,
                request_id=job.request_id,
            )
            await publish(
                "chat.message.outbound.requested",
                {
                    "chat_id": job.chat_id,
                    "message_id": job.message_id,
                    "sender_user_id": None,
                    "text_preview": job.text_preview,
                    "auto_reply": True,
                },
                scope=job.scope or None,
            )
        except Exception:
            logger.exception(
                "after_hours_auto_reply_enqueue_failed",
                chat_id=job.chat_id,
                message_id=job.message_id,
                bot_id=job.bot_id,
            )

    if result.sent:
        logger.info(
            "after_hours_scan_done",
            sent=result.sent,
            skipped=result.skipped,
        )
