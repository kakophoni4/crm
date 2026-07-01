from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger(__name__)

_EGRUL_SEARCH_URL = "https://egrul.nalog.ru/"
_LAST_REQUEST_AT = 0.0
_MIN_INTERVAL_SECONDS = 0.35


@dataclass(frozen=True)
class EgrulParty:
    inn: str
    kpp: str | None
    name: str
    short_name: str | None = None


def _throttle() -> None:
    global _LAST_REQUEST_AT
    now = time.monotonic()
    wait = _MIN_INTERVAL_SECONDS - (now - _LAST_REQUEST_AT)
    if wait > 0:
        time.sleep(wait)
    _LAST_REQUEST_AT = time.monotonic()


def lookup_party_by_inn_sync(inn: str, *, timeout_seconds: float = 30.0) -> EgrulParty | None:
    """Lookup legal entity by INN via public FNS EGRUL search."""
    inn = inn.strip()
    if not inn:
        return None
    _throttle()
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            search = client.post(_EGRUL_SEARCH_URL, data={"query": inn})
            search.raise_for_status()
            token = search.json().get("t")
            if not token:
                return None
            time.sleep(0.25)
            result = client.get(f"{_EGRUL_SEARCH_URL}search-result/{token}")
            result.raise_for_status()
            rows = result.json().get("rows") or []
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("egrul_lookup_failed", inn=inn, error=str(exc))
        return None

    if not rows:
        return None

    row = rows[0]
    name = str(row.get("n") or row.get("c") or "").strip()
    if not name:
        return None
    kpp_raw = row.get("p")
    kpp = str(kpp_raw).strip() if kpp_raw not in (None, "") else None
    short_name = str(row.get("c")).strip() if row.get("c") else None
    return EgrulParty(inn=inn, kpp=kpp, name=name, short_name=short_name)


async def lookup_party_by_inn(inn: str) -> EgrulParty | None:
    return await asyncio.to_thread(lookup_party_by_inn_sync, inn)
