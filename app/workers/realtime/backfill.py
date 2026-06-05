from __future__ import annotations

"""ARQ stub: replay missed WS events on reconnect (Round 6)."""


async def backfill_missed_events(
    _ctx: object,
    *,
    user_id: int,
    since: str | None = None,
) -> dict[str, str]:
    del user_id, since
    return {"status": "not_implemented"}
