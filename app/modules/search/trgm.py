from __future__ import annotations

from sqlalchemy import ColumnElement, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

_TRGM_INDEX_NAMES = (
    "idx_contacts_full_name_trgm",
    "idx_contacts_telegram_username_trgm",
    "idx_contacts_phone_trgm",
    "idx_contacts_email_trgm",
    "idx_chats_last_message_preview_trgm",
)

# Process-local probe cache: (names tuple, require_all) -> available.
# Invalidated only on process restart (migrations require restart/redeploy anyway).
_TRGM_INDEX_AVAILABLE_CACHE: dict[tuple[tuple[str, ...], bool], bool] = {}


async def trgm_search_indexes_available(
    session: AsyncSession,
    *,
    names: tuple[str, ...] | None = None,
    require_all: bool = False,
) -> bool:
    """True when useful pg_trgm GIN indexes exist.

    By default any matching index is enough (partial migrations still help).
    Pass require_all=True for ranking paths that need the full set.
    Result is cached in-process after the first probe for each (names, require_all).
    """
    wanted = tuple(names) if names is not None else _TRGM_INDEX_NAMES
    cache_key = (wanted, require_all)
    cached = _TRGM_INDEX_AVAILABLE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    result = await session.execute(
        text(
            """
            SELECT COUNT(*)::int
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = ANY(CAST(:names AS text[]))
            """
        ),
        {"names": list(wanted)},
    )
    count = int(result.scalar_one())
    available = count == len(wanted) if require_all else count > 0
    _TRGM_INDEX_AVAILABLE_CACHE[cache_key] = available
    return available


def trgm_ilike_match(
    column: InstrumentedAttribute[str | None],
    pattern: str,
) -> ColumnElement[bool]:
    """ILIKE predicate; accelerated by GIN (gin_trgm_ops) when migration 0024 is applied."""
    return column.ilike(pattern)


def trgm_or_ilike(
    *columns: InstrumentedAttribute[str | None],
    pattern: str,
) -> ColumnElement[bool]:
    return or_(*(trgm_ilike_match(col, pattern) for col in columns))
