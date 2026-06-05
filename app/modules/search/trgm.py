from __future__ import annotations

from sqlalchemy import ColumnElement, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

_TRGM_INDEX_NAMES = (
    "idx_contacts_full_name_trgm",
    "idx_contacts_telegram_username_trgm",
    "idx_chats_last_message_preview_trgm",
)


async def trgm_search_indexes_available(session: AsyncSession) -> bool:
    result = await session.execute(
        text(
            """
            SELECT COUNT(*)::int
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = ANY(CAST(:names AS text[]))
            """
        ),
        {"names": list(_TRGM_INDEX_NAMES)},
    )
    return int(result.scalar_one()) == len(_TRGM_INDEX_NAMES)


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
