from __future__ import annotations

from app.workers.jobs.lavok_parser_pull import _MAX_BYTES


def test_pull_max_bytes() -> None:
    assert _MAX_BYTES >= 1_000_000
