from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Naive UTC timestamp compatible with TIMESTAMPTZ columns via asyncpg."""
    return datetime.now(UTC).replace(tzinfo=None)
