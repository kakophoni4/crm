from __future__ import annotations

import hashlib
import json
from typing import Any

from redis.asyncio import Redis

CONTACT_CRM_KEY_PREFIX = "crm_summary:contact:"
DASHBOARD_CRM_KEY_PREFIX = "crm_summary:dashboard:"


def contact_crm_cache_key(contact_id: int) -> str:
    return f"{CONTACT_CRM_KEY_PREFIX}{contact_id}"


def dashboard_crm_cache_key(actor_id: int, group_ids: set[int] | None) -> str:
    if group_ids is None:
        scope_token = "all"
    else:
        parts = ",".join(str(gid) for gid in sorted(group_ids))
        scope_token = hashlib.sha256(parts.encode()).hexdigest()[:16]
    return f"{DASHBOARD_CRM_KEY_PREFIX}{actor_id}:{scope_token}"


async def get_cached_payload(redis: Redis, key: str) -> dict[str, Any] | None:
    raw = await redis.get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def set_cached_payload(
    redis: Redis,
    key: str,
    payload: dict[str, Any],
    *,
    ttl_seconds: int,
) -> None:
    await redis.set(key, json.dumps(payload, separators=(",", ":")), ex=ttl_seconds)


async def invalidate_contact_crm(redis: Redis, contact_id: int) -> None:
    await redis.delete(contact_crm_cache_key(contact_id))
