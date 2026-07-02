from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Naive UTC timestamp compatible with TIMESTAMPTZ columns via asyncpg."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
    """Normalize aware/naive datetimes for TIMESTAMP WITHOUT TIME ZONE columns."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)
