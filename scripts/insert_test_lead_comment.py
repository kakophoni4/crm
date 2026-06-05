"""One-off: insert probe comment for lead 7 (dev)."""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.shared.db import get_session_factory


async def main() -> None:
    async with get_session_factory()() as session:
        await session.execute(
            text(
                """
                INSERT INTO lead_comments (lead_id, group_id, body)
                SELECT l.id, l.group_id, 'probe'
                FROM leads l
                WHERE l.id = 7
                  AND NOT EXISTS (
                    SELECT 1 FROM lead_comments lc WHERE lc.lead_id = 7
                  )
                """,
            ),
        )
        await session.execute(text("UPDATE leads SET comment = 'probe' WHERE id = 7"))
        await session.commit()
        count = await session.scalar(text("SELECT COUNT(*) FROM lead_comments WHERE lead_id = 7"))
        print("lead_comments for lead 7:", count)


if __name__ == "__main__":
    asyncio.run(main())
