from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.shared.storage import FileStorage, set_file_storage


class _FakeMultipartStorage(FileStorage):
    async def initiate_multipart(self, key: str, content_type: str) -> str:
        del key, content_type
        return "upload-test-id"

    async def upload_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        data: bytes,
    ) -> str:
        del key, upload_id, part_number, data
        return '"etag-1"'

    async def complete_multipart(
        self,
        key: str,
        upload_id: str,
        parts: list[tuple[int, str]],
    ) -> None:
        del key, upload_id, parts

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        del key, upload_id

    async def delete_object(self, key: str) -> None:
        del key

    async def iter_object_bytes(self, key: str, *, chunk_size: int = 1024 * 1024):
        del key, chunk_size
        yield b"hello-large-share"
        return


@pytest.mark.asyncio
async def test_large_share_forbidden_for_operator(
    client: AsyncClient,
    db_ready: None,
    operator_a_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/storage/admin/large-share/init",
        headers=operator_a_headers,
        json={
            "original_name": "dump.bin",
            "mime_type": "application/octet-stream",
            "size_bytes": 1024,
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_admin_large_share_roundtrip(
    client: AsyncClient,
    db_ready: None,
    admin_headers: dict[str, str],
) -> None:
    set_file_storage(_FakeMultipartStorage())
    try:
        init = await client.post(
            "/api/v1/storage/admin/large-share/init",
            headers=admin_headers,
            json={
                "original_name": "dump.bin",
                "mime_type": "application/octet-stream",
                "size_bytes": 5,
            },
        )
        assert init.status_code == 201, init.text
        upload_id = init.json()["id"]
        part = await client.put(
            f"/api/v1/storage/admin/large-share/{upload_id}/parts/1",
            headers={**admin_headers, "Content-Type": "application/octet-stream"},
            content=b"hello",
        )
        assert part.status_code == 200, part.text
        done = await client.post(
            f"/api/v1/storage/admin/large-share/{upload_id}/complete",
            headers=admin_headers,
        )
        assert done.status_code == 200, done.text
        body = done.json()
        assert body["share"]["max_downloads"] == 1
        assert body["share"]["url"]
        assert body["vault"]["original_name"] == "dump.bin"
        token = body["share"]["token"]
        downloaded = await client.get(f"/api/v1/public/storage/shares/{token}/file")
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == b"hello-large-share"
    finally:
        set_file_storage(FileStorage())
