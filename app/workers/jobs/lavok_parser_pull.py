from __future__ import annotations

import hashlib

import httpx
import structlog

from app.shared.db import get_session_factory
from app.shared.redis import get_redis
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

LAVOK_PARSER_PULL_JOB_TYPE = "lavok_parser_pull"
_LOCK_KEY = "crm:lavok_parser:pull:lock"
_LOCK_TTL_SECONDS = 240
_SCHEDULE_KEY = "crm:lavok_parser:pull:scheduled"
_ETAG_KEY = "crm:lavok_parser:pull:etag"
_SHA_KEY = "crm:lavok_parser:pull:sha256"
_MAX_BYTES = 20 * 1024 * 1024


async def fetch_parser_xlsx() -> tuple[bytes | None, str | None, str]:
    """GET export xlsx. Returns (content, etag, status) where status is ok|not_modified|empty|error."""
    settings = get_settings()
    url = (settings.lavok_parser_pull_url or "").strip()
    token = (settings.lavok_parser_ingest_token or "").strip()
    if not url:
        return None, None, "empty"
    if not url.startswith(("http://", "https://")):
        logger.warning("lavok_parser_pull_bad_url")
        return None, None, "error"

    redis = get_redis()
    previous = await redis.get(_ETAG_KEY)
    headers = {"Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    if token:
        headers["X-Lavok-Ingest-Token"] = token
    if previous:
        headers["If-None-Match"] = previous.decode() if isinstance(previous, bytes) else str(previous)

    timeout = httpx.Timeout(settings.lavok_parser_pull_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
    except httpx.RequestError:
        logger.exception("lavok_parser_pull_request_failed", url=url)
        return None, None, "error"

    if response.status_code == 304:
        return None, None, "not_modified"
    if response.status_code >= 400:
        logger.warning(
            "lavok_parser_pull_http_error",
            status=response.status_code,
            url=url,
        )
        return None, None, "error"

    data = response.content or b""
    if not data:
        return None, None, "empty"
    if len(data) > _MAX_BYTES:
        logger.warning("lavok_parser_pull_too_large", size=len(data))
        return None, None, "error"
    etag = (response.headers.get("etag") or "").strip() or None
    return data, etag, "ok"


async def process_lavok_parser_pull(_job_type: str, _payload: dict[str, object]) -> None:
    del _job_type, _payload
    settings = get_settings()
    if not (settings.lavok_parser_pull_url or "").strip():
        return

    redis = get_redis()
    acquired = await redis.set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL_SECONDS)
    if not acquired:
        logger.info("lavok_parser_pull_skipped_lock")
        return

    try:
        content, etag, status = await fetch_parser_xlsx()
        if status in {"empty", "not_modified", "error"}:
            logger.info("lavok_parser_pull_skip", status=status)
            return
        assert content is not None
        digest = hashlib.sha256(content).hexdigest()
        previous_sha = await redis.get(_SHA_KEY)
        if previous_sha and (
            previous_sha.decode() if isinstance(previous_sha, bytes) else str(previous_sha)
        ) == digest:
            logger.info("lavok_parser_pull_unchanged_hash")
            if etag:
                await redis.set(_ETAG_KEY, etag)
            return

        from app.modules.lavok_parser.service import LavokParserService

        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await LavokParserService(session).ingest(content)
        await redis.set(_SHA_KEY, digest)
        if etag:
            await redis.set(_ETAG_KEY, etag)
        else:
            await redis.set(_ETAG_KEY, digest)
        logger.info(
            "lavok_parser_pull_done",
            sheets=result.sheets,
            created=result.created,
            updated=result.updated,
            upserted=result.upserted,
            bytes=len(content),
        )
    except Exception:
        logger.exception("lavok_parser_pull_failed")
    finally:
        await redis.delete(_LOCK_KEY)


async def schedule_lavok_parser_pull_if_due(*, force: bool = False) -> None:
    settings = get_settings()
    if not (settings.lavok_parser_pull_url or "").strip():
        return
    redis = get_redis()
    ttl = max(int(settings.lavok_parser_pull_interval_seconds), 60)
    if force:
        await redis.delete(_SCHEDULE_KEY)
    acquired = await redis.set(_SCHEDULE_KEY, "1", nx=True, ex=ttl)
    if not acquired:
        return
    from app.workers.jobs.queue import enqueue

    await enqueue(LAVOK_PARSER_PULL_JOB_TYPE, {})
    logger.info("lavok_parser_pull_scheduled", interval_seconds=ttl, force=force)


async def bootstrap_lavok_parser_pull() -> None:
    await schedule_lavok_parser_pull_if_due(force=True)
