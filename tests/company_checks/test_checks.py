from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from app.modules.lavok_parser import checks
from app.shared.exceptions import AppError, ValidationError


def test_parser_url_and_job_path(monkeypatch):
    monkeypatch.setattr(checks.settings, "lavok_parser_ingest_token", "test")
    monkeypatch.setattr(checks.settings, "lavok_parser_checks_url", "")
    monkeypatch.setattr(
        checks.settings, "lavok_parser_pull_url", "http://127.0.0.1:8788/lavok/export.xlsx"
    )
    assert checks.base_url() == "http://127.0.0.1:8788/lavok/checks"
    with pytest.raises(ValidationError):
        checks.job_path("../another-user")


@pytest.mark.asyncio
async def test_chunk_download_rejects_changed_file(monkeypatch):
    monkeypatch.setattr(checks.settings, "lavok_parser_checks_url", "http://parser/lavok/checks")
    monkeypatch.setattr(checks.settings, "lavok_parser_ingest_token", "test")
    calls = []

    async def handler(request):
        calls.append(request)
        assert request.headers["X-Lavok-Owner"] == "crm-user:42"
        if len(calls) == 1:
            return httpx.Response(
                206,
                headers={"Content-Range": "bytes 0-16383/20000", "ETag": "one"},
                content=b"x" * 16384,
            )
        return httpx.Response(
            206,
            headers={"Content-Range": "bytes 16384-19999/20000", "ETag": "two"},
            content=b"y" * 3616,
        )

    original = httpx.AsyncClient
    with (
        patch.object(
            checks.httpx,
            "AsyncClient",
            side_effect=lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
        ),
        pytest.raises(AppError, match="изменился"),
    ):
        await checks.fetch_result(SimpleNamespace(id=42), "a" * 32)


@pytest.mark.asyncio
async def test_chunk_download_preserves_exact_bytes(monkeypatch):
    monkeypatch.setattr(checks.settings, "lavok_parser_checks_url", "http://parser/lavok/checks")
    monkeypatch.setattr(checks.settings, "lavok_parser_ingest_token", "test")
    payload = b"xlsx" * 6000

    def handler(request):
        start, end = map(int, request.headers["Range"].removeprefix("bytes=").split("-"))
        end = min(end, len(payload) - 1)
        return httpx.Response(
            206,
            headers={"Content-Range": f"bytes {start}-{end}/{len(payload)}", "ETag": "one"},
            content=payload[start : end + 1],
        )

    original = httpx.AsyncClient
    with patch.object(
        checks.httpx,
        "AsyncClient",
        side_effect=lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    ):
        assert await checks.fetch_result(SimpleNamespace(id=42), "a" * 32) == payload


@pytest.mark.asyncio
async def test_authenticated_multipart_upload():
    app = FastAPI()
    app.include_router(checks.router)
    dep = checks.router.routes[0].dependant.dependencies[0].call
    app.dependency_overrides[dep] = lambda: SimpleNamespace(id=42)
    job = dict(
        id="a" * 32,
        filename="input.xlsx",
        status="queued",
        created_at="2026-10-14",
        updated_at="2026-10-14",
        total=1,
        completed=0,
        checks_done=0,
        checks_total=9,
        failed_checks=0,
        rejected_rows=0,
        duplicates=0,
        input_rows=1,
        progress=0,
    )
    mocked = AsyncMock(return_value=job)
    with patch.object(checks, "request", mocked):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://crm"
        ) as client:
            response = await client.post(
                "/api/v1/lavok-parser/checks", files={"file": ("input.xlsx", b"file-data")}
            )
            assert response.status_code == 202
    assert mocked.call_args.kwargs["content"] == b"file-data"
    assert mocked.call_args.args[0].id == 42
