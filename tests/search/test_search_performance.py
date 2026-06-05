# ruff: noqa: RUF001 — Cyrillic literals required for Russian FTS perf smoke.
from __future__ import annotations

import os
import time

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.shared.settings import Settings
from tests.auth.conftest import _sync_database_url

_SKIP_CI = os.getenv("CI", "").lower() in {"1", "true", "yes"} or os.getenv(
    "GITHUB_ACTIONS",
    "",
).lower() in {"1", "true", "yes"}


def _p95_ms(samples_ms: list[float]) -> float:
    ordered = sorted(samples_ms)
    index = max(0, int(len(ordered) * 0.95) - 1)
    return ordered[index]


@pytest.mark.skipif(
    _SKIP_CI,
    reason="local search perf smoke; skipped in CI (flaky on shared runners)",
)
@pytest.mark.asyncio
async def test_chat_search_p95_under_500ms(
    client: AsyncClient,
    db_ready: None,
    chats_org: dict[str, object],
    operator_a_headers: dict[str, str],
    test_settings: Settings,
) -> None:
    chat_id = chats_org["chat_ids"]["a"]
    assert isinstance(chat_id, int)
    needle = "договорпоставкиperf"

    engine = create_engine(_sync_database_url(test_settings.database_url))
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO messages (chat_id, direction, kind, text)
                VALUES (:chat_id, 'inbound', 'text', :body)
                """
            ),
            {"chat_id": chat_id, "body": f"Текст про {needle} для perf smoke"},
        )
    engine.dispose()

    warmup = await client.get(
        "/api/v1/chats/search",
        headers=operator_a_headers,
        params={"q": "договор", "scope": "group"},
    )
    assert warmup.status_code == 200, warmup.text

    durations_ms: list[float] = []
    for _ in range(100):
        started = time.perf_counter()
        response = await client.get(
            "/api/v1/chats/search",
            headers=operator_a_headers,
            params={"q": "договор", "scope": "group", "limit": 20},
        )
        durations_ms.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 200, response.text

    p95 = _p95_ms(durations_ms)
    assert p95 < 500, (
        f"p95={p95:.1f}ms exceeds 500ms (min={min(durations_ms):.1f}, "
        f"max={max(durations_ms):.1f}, median={sorted(durations_ms)[49]:.1f})"
    )
