from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, text

from app.shared.storage import FileStorage, set_file_storage
from app.workers.bots.download_attachment import download_attachment
from tests.auth.conftest import _sync_database_url


class FakeStorage(FileStorage):
    async def upload_bytes(self, key: str, data: bytes, content_type: str) -> str:
        del data, content_type
        return f"https://minio.test/{key}"

    async def presign_get(self, key: str, expires: int = 3600) -> str:
        del expires
        return f"https://minio.test/presigned/{key}"


@pytest.mark.asyncio
async def test_attachment_download_updates_message(
    db_ready: None,
    test_settings,
    bots_org: dict[str, object],
) -> None:
    engine = create_engine(_sync_database_url(test_settings.database_url))
    attachments = [
        {
            "type": "photo",
            "url": "https://bot.example.com/files/photo1.jpg",
            "mime": "image/jpeg",
            "status": "pending",
        }
    ]
    try:
        with engine.begin() as connection:
            contact_id = connection.execute(
                text(
                    """
                    INSERT INTO contacts (full_name, telegram_user_id, created_by)
                    SELECT 'Att Contact', 999002, id FROM users WHERE role = 'admin' LIMIT 1
                    RETURNING id
                    """
                ),
            ).scalar_one()
            chat_id = connection.execute(
                text(
                    """
                    INSERT INTO chats (contact_id, bot_id, status)
                    VALUES (:cid, :bid, 'open')
                    RETURNING id
                    """
                ),
                {"cid": contact_id, "bid": bots_org["bot_id"]},
            ).scalar_one()
            message_id = connection.execute(
                text(
                    """
                    INSERT INTO messages (chat_id, direction, kind, attachments)
                    VALUES (:cid, 'inbound', 'image', CAST(:att AS jsonb))
                    RETURNING id
                    """
                ),
                {"cid": chat_id, "att": json.dumps(attachments)},
            ).scalar_one()
    finally:
        engine.dispose()

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.content = b"fake-image-bytes"
    mock_response.headers = {"content-type": "image/jpeg"}
    mock_response.raise_for_status = lambda: None

    set_file_storage(FakeStorage())

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        await download_attachment(
            "download_attachment",
            {"message_id": message_id, "attachment_index": 0},
        )

    engine = create_engine(_sync_database_url(test_settings.database_url))
    try:
        with engine.connect() as connection:
            stored = connection.execute(
                text("SELECT attachments FROM messages WHERE id = :mid"),
                {"mid": message_id},
            ).scalar_one()
    finally:
        engine.dispose()

    assert stored[0]["status"] == "ready"
    assert stored[0]["storage_key"].startswith("bot-inbound/")
