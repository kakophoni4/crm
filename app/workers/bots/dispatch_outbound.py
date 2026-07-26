from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.modules.bots.hmac_util import outbound_path_from_url, sign_outbound
from app.modules.bots.repository import BotOutboundLogRepository, BotRepository
from app.modules.db.models.enums import BotOutboundStatus
from app.shared.db import get_session_factory
from app.shared.metrics import inc_bot_outbound
from app.shared.request_id import generate_ulid
from app.workers.bots.queue import enqueue

logger = structlog.get_logger(__name__)

MAX_ATTEMPTS = 5
BACKOFF_SECONDS = (30, 60, 120, 300, 600)


async def dispatch_outbound_command(_job_type: str, payload: dict[str, Any]) -> None:
    log_id = int(payload["outbound_log_id"])
    session_factory = get_session_factory()

    async with session_factory() as session:
        outbound_repo = BotOutboundLogRepository(session)
        bot_repo = BotRepository(session)
        row = await outbound_repo.get_by_id(log_id)
        if row is None:
            return
        if row.status == BotOutboundStatus.SENT:
            return

        bot = await bot_repo.get_by_id(row.bot_id)
        if bot is None or not bot.is_active:
            row.status = BotOutboundStatus.FAILED
            row.last_error = "bot inactive or missing"
            await outbound_repo.save(row)
            await session.commit()
            inc_bot_outbound("failed")
            return

        secret = await bot_repo.decrypt_outbound_secret(bot)
        body_dict = {
            "command": row.command,
            "request_id": row.request_id,
            "issued_at": datetime.now(UTC).isoformat(),
            "bot_code": bot.code,
            "payload": row.payload,
        }
        body = json.dumps(body_dict, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(datetime.now(UTC).timestamp()))
        path = outbound_path_from_url(bot.outbound_url)
        signature = sign_outbound("POST", path, timestamp, body, secret)

        row.attempts += 1
        row.last_attempt_at = datetime.now(UTC)
        await outbound_repo.save(row)
        await session.commit()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    bot.outbound_url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-CRM-Request-Id": row.request_id,
                        "X-CRM-Timestamp": timestamp,
                        "X-CRM-Signature": signature,
                    },
                )
            if response.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "outbound failed",
                    request=response.request,
                    response=response,
                )
            response_payload = response.json()
            row.status = BotOutboundStatus.SENT
            row.response_payload = response_payload
            row.last_error = None
            await outbound_repo.save(row)

            # Link Telegram message_id back onto the CRM row so bot-echo ingest
            # dedupes instead of inserting a second "TG Bot" outbound bubble.
            internal_id = row.payload.get("internal_id") if isinstance(row.payload, dict) else None
            external_id = None
            if isinstance(response_payload, dict):
                raw_ext = response_payload.get("external_id") or response_payload.get(
                    "telegram_message_id"
                )
                if raw_ext is not None and str(raw_ext).strip():
                    external_id = str(raw_ext).strip()
            if internal_id is not None and external_id:
                try:
                    msg_id = int(internal_id)
                except (TypeError, ValueError):
                    msg_id = 0
                if msg_id > 0:
                    from sqlalchemy import text

                    await session.execute(
                        text(
                            """
                            UPDATE messages
                            SET external_message_id = COALESCE(external_message_id, :ext)
                            WHERE id = :mid
                              AND external_message_id IS NULL
                            """
                        ),
                        {"ext": external_id, "mid": msg_id},
                    )

            await session.commit()
            inc_bot_outbound("sent")
        except Exception as exc:
            error_text = str(exc)[:2000]
            async with session_factory() as retry_session:
                retry_row = await BotOutboundLogRepository(retry_session).get_by_id(log_id)
                if retry_row is None:
                    return
                retry_row.last_error = error_text
                if retry_row.attempts >= MAX_ATTEMPTS:
                    retry_row.status = BotOutboundStatus.FAILED
                    await BotOutboundLogRepository(retry_session).save(retry_row)
                    await retry_session.commit()
                    inc_bot_outbound("failed")
                    logger.error("dispatch_outbound_exhausted", log_id=log_id, error=error_text)
                    return

                await BotOutboundLogRepository(retry_session).save(retry_row)
                await retry_session.commit()
                delay = BACKOFF_SECONDS[min(retry_row.attempts - 1, len(BACKOFF_SECONDS) - 1)]
                await enqueue(
                    "dispatch_outbound",
                    {"outbound_log_id": log_id, "bot_id": row.bot_id},
                    delay_seconds=delay,
                )
                inc_bot_outbound("retry")
                logger.warning(
                    "dispatch_outbound_retry",
                    log_id=log_id,
                    attempts=retry_row.attempts,
                    error=error_text,
                )


async def enqueue_outbound(
    *,
    bot_id: int,
    command: str,
    payload: dict[str, Any],
    request_id: str | None = None,
) -> int:
    rid = request_id or generate_ulid()
    session_factory = get_session_factory()
    async with session_factory() as session:
        row = await BotOutboundLogRepository(session).create(
            bot_id=bot_id,
            request_id=rid,
            command=command,
            payload=payload,
        )
        await session.commit()
        log_id = row.id

    try:
        await enqueue("dispatch_outbound", {"outbound_log_id": log_id, "bot_id": bot_id})
    except Exception as exc:
        async with session_factory() as fail_session:
            failed_row = await BotOutboundLogRepository(fail_session).get_by_id(log_id)
            if failed_row is not None and failed_row.status == BotOutboundStatus.QUEUED:
                failed_row.status = BotOutboundStatus.FAILED
                failed_row.last_error = str(exc)[:2000]
                await BotOutboundLogRepository(fail_session).save(failed_row)
                await fail_session.commit()
                inc_bot_outbound("failed")
        raise
    return log_id
