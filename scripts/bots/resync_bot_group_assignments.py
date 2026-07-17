from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import bindparam, text

from app.modules.bots.repository import BotRepository
from app.shared.db import dispose_engine, get_session_factory


async def _resync(*, dry_run: bool) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        b.id,
                        b.code,
                        b.department_id,
                        COALESCE(
                            array_agg(bga.group_id ORDER BY bga.group_id)
                                FILTER (WHERE bga.group_id IS NOT NULL),
                            ARRAY[]::bigint[]
                        ) AS group_ids
                    FROM bots b
                    LEFT JOIN bot_group_assignments bga ON bga.bot_id = b.id
                    WHERE b.is_active IS TRUE
                    GROUP BY b.id, b.code, b.department_id
                    ORDER BY b.id
                    """
                )
            )
        ).mappings().all()

        repo = BotRepository(session)
        touched_bots = 0
        for row in rows:
            group_ids = [int(value) for value in row["group_ids"]]
            if not group_ids:
                continue
            bot_id = int(row["id"])
            move_count = await _count_chats_to_resync(session, bot_id, group_ids)
            null_owners = await _count_null_owners(session, bot_id, group_ids)
            inbox_leftovers = await _count_inbox_leftovers(
                session,
                bot_id,
                int(row["department_id"]),
                group_ids,
            )
            if move_count == 0 and null_owners == 0 and inbox_leftovers == 0:
                print(f"bot {row['code']}: already synced")
                continue
            touched_bots += 1
            print(
                f"bot {row['code']}: move={move_count} null_owners={null_owners} "
                f"inbox_leftovers={inbox_leftovers} groups={group_ids}"
            )
            if not dry_run:
                await repo.sync_chats_after_group_assignment(
                    bot_id,
                    int(row["department_id"]),
                    group_ids,
                )

        if dry_run:
            await session.rollback()
            print(f"dry run complete, bots needing repair: {touched_bots}")
        else:
            await session.commit()
            print(f"resync complete, changed bots: {touched_bots}")


async def _main_async(*, dry_run: bool) -> None:
    try:
        await _resync(dry_run=dry_run)
    finally:
        await dispose_engine()


async def _count_chats_to_resync(session, bot_id: int, group_ids: list[int]) -> int:
    result = await session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM chats
            WHERE bot_id = :bid
              AND status != 'archived'
              AND (
                assigned_group_id IS NULL
                OR assigned_group_id NOT IN :gids
              )
            """
        ).bindparams(bindparam("gids", expanding=True)),
        {"bid": bot_id, "gids": group_ids},
    )
    return int(result.scalar_one())


async def _count_null_owners(session, bot_id: int, group_ids: list[int]) -> int:
    result = await session.execute(
        text(
            """
            SELECT COUNT(DISTINCT c.contact_id)
            FROM chats c
            LEFT JOIN contact_group_assignments cga
              ON cga.contact_id = c.contact_id
             AND cga.group_id = c.assigned_group_id
            WHERE c.bot_id = :bid
              AND c.status != 'archived'
              AND c.assigned_group_id IN :gids
              AND (cga.id IS NULL OR cga.owner_user_id IS NULL)
            """
        ).bindparams(bindparam("gids", expanding=True)),
        {"bid": bot_id, "gids": group_ids},
    )
    return int(result.scalar_one())


async def _count_inbox_leftovers(
    session,
    bot_id: int,
    department_id: int,
    group_ids: list[int],
) -> int:
    result = await session.execute(
        text(
            """
            SELECT COUNT(DISTINCT c.contact_id)
            FROM chats c
            JOIN contact_group_assignments cga
              ON cga.contact_id = c.contact_id
            JOIN groups g
              ON g.id = cga.group_id
             AND g.name = '__department_inbox__'
             AND g.department_id = :did
            WHERE c.bot_id = :bid
              AND c.status != 'archived'
              AND c.assigned_group_id IN :gids
            """
        ).bindparams(bindparam("gids", expanding=True)),
        {"bid": bot_id, "did": department_id, "gids": group_ids},
    )
    return int(result.scalar_one())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Redistribute active bot chats into configured bot groups "
        "and backfill empty owners / leftover inbox rows.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would change.")
    args = parser.parse_args()
    asyncio.run(_main_async(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
