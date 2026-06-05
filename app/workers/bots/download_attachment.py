from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
import structlog
from sqlalchemy import text

from app.shared.db import get_session_factory
from app.shared.storage import get_file_storage
from app.realtime.events import publish
from app.realtime.topics import CHAT_MESSAGE_ATTACHMENT_READY
from app.workers.bots.queue import enqueue

logger = structlog.get_logger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 30, 120)


async def download_attachment(_job_type: str, payload: dict[str, Any]) -> None:
    message_id = int(payload["message_id"])
    attachment_index = int(payload["attachment_index"])
    attempt = int(payload.get("attempt", 0))

    session_factory = get_session_factory()
    async with session_factory() as session:
        row = await session.execute(
            text("SELECT attachments, chat_id FROM messages WHERE id = :mid"),
            {"mid": message_id},
        )
        fetched = row.one_or_none()
        if fetched is None:
            return
        attachments, chat_id = fetched[0], int(fetched[1])
        if not attachments or attachment_index >= len(attachments):
            return

        att = dict(attachments[attachment_index])
        url = att.get("url")
        if not url or att.get("status") == "ready":
            return

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(str(url))
                response.raise_for_status()
                data = response.content
                default_mime = att.get("mime", "application/octet-stream")
                content_type = response.headers.get("content-type", default_mime)

            key = f"bot-inbound/{message_id}/{attachment_index}/{uuid4().hex}"
            storage = get_file_storage()
            await storage.upload_bytes(key, data, str(content_type))

            att["status"] = "ready"
            att["storage_key"] = key
            att.pop("url", None)
            attachments[attachment_index] = att

            await session.execute(
                text("UPDATE messages SET attachments = CAST(:att AS jsonb) WHERE id = :mid"),
                {"att": json.dumps(attachments), "mid": message_id},
            )
            await session.commit()
            await publish(
                CHAT_MESSAGE_ATTACHMENT_READY,
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "attachment_index": attachment_index,
                },
            )
        except Exception as exc:
            if attempt + 1 < MAX_ATTEMPTS:
                delay = BACKOFF_SECONDS[attempt]
                await enqueue(
                    "download_attachment",
                    {
                        "message_id": message_id,
                        "attachment_index": attachment_index,
                        "attempt": attempt + 1,
                    },
                    delay_seconds=delay,
                )
                logger.warning(
                    "download_attachment_retry",
                    message_id=message_id,
                    index=attachment_index,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                return

            att["status"] = "failed"
            att["error"] = str(exc)[:500]
            attachments[attachment_index] = att
            await session.execute(
                text("UPDATE messages SET attachments = CAST(:att AS jsonb) WHERE id = :mid"),
                {"att": json.dumps(attachments), "mid": message_id},
            )
            await session.commit()
            logger.error(
                "download_attachment_failed",
                message_id=message_id,
                index=attachment_index,
                error=str(exc),
            )
