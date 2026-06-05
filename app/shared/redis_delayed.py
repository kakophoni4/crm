from __future__ import annotations

import time
from typing import Any

# Atomically move due delayed jobs to a stream (ZREM + XADD).
PROMOTE_DELAYED_LUA = """
local delayed_key = KEYS[1]
local stream_key = KEYS[2]
local now = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local items = redis.call('ZRANGEBYSCORE', delayed_key, '-inf', now, 'LIMIT', 0, limit)
local promoted = 0
for i, raw in ipairs(items) do
  if redis.call('ZREM', delayed_key, raw) == 1 then
    redis.call('XADD', stream_key, '*', 'data', raw)
    promoted = promoted + 1
  end
end
return promoted
"""


async def promote_delayed_jobs(
    redis: Any,
    *,
    delayed_key: str,
    stream_key: str,
    limit: int = 50,
) -> int:
    """Promote due delayed jobs; returns count promoted."""
    result = await redis.eval(
        PROMOTE_DELAYED_LUA,
        2,
        delayed_key,
        stream_key,
        str(time.time()),
        str(limit),
    )
    return int(result or 0)
