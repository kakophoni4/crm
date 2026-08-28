from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import quote

from fastapi.responses import StreamingResponse

from app.modules.storage.repository import increment_share_download_standalone
from app.shared.storage import get_file_storage


def attachment_headers(filename: str, size_bytes: int | None = None) -> dict[str, str]:
    ascii_name = filename.encode("ascii", "ignore").decode() or "file"
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
        ),
        "Cache-Control": "no-store",
    }
    if size_bytes is not None and size_bytes >= 0:
        headers["Content-Length"] = str(size_bytes)
    return headers


def stream_stored_file(
    *,
    storage_key: str,
    filename: str,
    content_type: str,
    size_bytes: int | None = None,
    share_id: int | None = None,
) -> StreamingResponse:
    storage = get_file_storage()

    async def chunks() -> AsyncIterator[bytes]:
        completed = False
        try:
            async for chunk in storage.iter_object_bytes(storage_key):
                yield chunk
            completed = True
        finally:
            if completed and share_id is not None:
                await increment_share_download_standalone(share_id)

    return StreamingResponse(
        chunks(),
        media_type=content_type or "application/octet-stream",
        headers=attachment_headers(filename, size_bytes),
    )
