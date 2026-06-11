#!/usr/bin/env python3
"""Reset local admin password to ChangeMe!234567."""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.shared.db import get_engine
from app.shared.security.passwords import hash_password

PASSWORD = "ChangeMe!234567"


async def main() -> None:
    engine = get_engine()
    password_hash = hash_password(PASSWORD)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE users SET password_hash = :h, status = 'active' "
                "WHERE username = 'admin' OR email = 'admin@crm.local'",
            ),
            {"h": password_hash},
        )
    await engine.dispose()
    print(f"OK: admin password reset to {PASSWORD!r}")


if __name__ == "__main__":
    asyncio.run(main())
