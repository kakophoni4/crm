"""Bind Infosled bot default owner to username deineris.

Safe to run repeatedly. Use if migration 0078/0079 already applied without the data step.

  python -m scripts.set_infosled_owner_deineris
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.shared.db import get_session_factory


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text(
                """
                UPDATE bots AS b
                SET default_owner_user_id = u.id
                FROM users AS u
                WHERE lower(u.username) = 'deineris'
                  AND u.status = 'active'
                  AND (
                    b.name ILIKE '%инфослед%'
                    OR b.name ILIKE '%infosled%'
                    OR b.code ILIKE '%infosled%'
                    OR b.code ILIKE '%info_sled%'
                    OR b.code ILIKE '%инфослед%'
                  )
                RETURNING b.id, b.code, b.name, u.username, u.full_name
                """
            ),
        )
        rows = result.fetchall()
        await session.commit()

    if not rows:
        print(
            "Ничего не обновлено. Проверьте: есть активный user username=deineris "
            "и бот с именем/кодом ИнфоСлед.",
        )
        return

    for row in rows:
        print(
            f"OK bot id={row.id} code={row.code!r} name={row.name!r} "
            f"→ owner @{row.username} ({row.full_name})",
        )


if __name__ == "__main__":
    asyncio.run(main())
